"""
Purchase price and MRP are different values and are never mixed (in-memory SQLite, no live database).

products.unit_price is the MRP per strip/pack and the selling basis; purchase_price is cost only.
"""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import crud
import models
from models import Base, Product, User, Supplier
from schemas import (
    ProductCreate,
    SaleCreate,
    SaleItemCreate,
    PurchaseInvoiceCreate,
    PurchaseItemCreate,
    DocumentConfirmRequest,
    DocumentItemVerify,
)
from services import import_service

FUTURE = (date.today() + timedelta(days=400)).isoformat()


class MrpRulesBase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(id=1, shop_name="Test Pharma", owner_name="T", email="t@t.com", password="pw",
                         default_gst_percentage=12.0)
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def assert_refused(self, code, fn, *args, **kwargs):
        with self.assertRaises(HTTPException) as ctx:
            fn(*args, **kwargs)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertTrue(str(ctx.exception.detail).startswith(code), ctx.exception.detail)
        return ctx.exception


class TestManualEntry(MrpRulesBase):
    def product(self, **kw):
        base = dict(product_name="DOLO 650", batch_number="B1", quantity=10, expiry_date=FUTURE)
        base.update(kw)
        return ProductCreate(**base)

    def test_both_values_saved_separately(self):
        p = crud.create_product(self.db, self.product(mrp=30.0, purchase_price=22.0), 1)
        self.assertEqual(p.unit_price, 30.0)      # MRP
        self.assertEqual(p.purchase_price, 22.0)  # cost

    def test_missing_or_zero_mrp_is_refused(self):
        self.assert_refused("MRP_REQUIRED", crud.create_product, self.db, self.product(purchase_price=22.0), 1)
        self.assert_refused("MRP_REQUIRED", crud.create_product, self.db, self.product(mrp=0, purchase_price=22.0), 1)
        self.assertEqual(self.db.query(Product).count(), 0)

    def test_old_app_copying_purchase_price_into_price_is_refused(self):
        # Older app: no "mrp" field, selling price silently set to the purchase price.
        self.assert_refused("MRP_REQUIRED", crud.create_product, self.db,
                            self.product(unit_price=22.0, purchase_price=22.0), 1)

    def test_old_app_with_real_selling_price_still_works(self):
        p = crud.create_product(self.db, self.product(unit_price=30.0, purchase_price=22.0), 1)
        self.assertEqual(p.unit_price, 30.0)

    def test_mrp_below_purchase_needs_confirmation(self):
        self.assert_refused("MRP_BELOW_COST", crud.create_product, self.db,
                            self.product(mrp=20.0, purchase_price=22.0), 1)
        p = crud.create_product(self.db, self.product(mrp=20.0, purchase_price=22.0,
                                                      confirm_mrp_below_cost=True), 1)
        self.assertEqual(p.unit_price, 20.0)

    def test_update_also_requires_mrp(self):
        p = crud.create_product(self.db, self.product(mrp=30.0, purchase_price=22.0), 1)
        self.assert_refused("MRP_REQUIRED", crud.update_product, self.db, p.id,
                            self.product(mrp=0, unit_price=0, purchase_price=22.0), 1)
        self.assertEqual(self.db.get(Product, p.id).unit_price, 30.0)


class TestPurchaseInvoiceAndOcr(MrpRulesBase):
    def setUp(self):
        super().setUp()
        self.db.add(Supplier(id=1, user_id=1, name="Gupta Enterprises"))
        self.db.add(Product(id=5, user_id=1, category="Allopathy", product_name="PAN 40", batch_number="P1", quantity=0,
                            unit_price=0.0, expiry_date=date.today() + timedelta(days=300)))
        self.db.commit()

    def invoice(self, mrp, **kw):
        return PurchaseInvoiceCreate(
            supplier_id=1, invoice_number="INV1", invoice_date=date.today(), total_amount=100.0,
            tax_amount=0.0, payment_status="PAID",
            items=[PurchaseItemCreate(product_id=5, batch_number="P1", quantity=10, purchase_price=80.0,
                                      mrp=mrp, gst_rate=12.0, expiry_date=date.today() + timedelta(days=300))],
            **kw,
        )

    def test_purchase_invoice_uses_mrp_not_purchase_price(self):
        crud.create_purchase_invoice(self.db, self.invoice(120.0), 1)
        prod = self.db.get(Product, 5)
        self.assertEqual(prod.unit_price, 120.0)
        self.assertEqual(prod.purchase_price, 80.0)

    def test_purchase_invoice_without_mrp_is_refused(self):
        self.assert_refused("MRP_REQUIRED", crud.create_purchase_invoice, self.db, self.invoice(0.0), 1)

    def test_purchase_invoice_mrp_below_cost_needs_confirmation(self):
        self.assert_refused("MRP_BELOW_COST", crud.create_purchase_invoice, self.db, self.invoice(70.0), 1)

    def _doc(self):
        d = models.Document(user_id=1, title="bill", doc_type="purchase_invoice", file_path="/x", file_type="image/jpeg",
                            file_size=1, ocr_status="Needs Review")
        self.db.add(d)
        self.db.commit()
        return d

    def test_invoice_ocr_without_mrp_is_refused(self):
        d = self._doc()
        req = DocumentConfirmRequest(items=[DocumentItemVerify(product_name="AZEE 500", batch_number="AZ1", quantity=2,
                                                               purchase_price=90.0, unit_price=0.0,
                                                               expiry_date=FUTURE)])
        self.assert_refused("MRP_REQUIRED", crud.confirm_document_and_update_stock, self.db, d.id, 1, req)

    def test_invoice_ocr_purchase_rate_copied_as_selling_is_refused(self):
        d = self._doc()
        req = DocumentConfirmRequest(items=[DocumentItemVerify(product_name="AZEE 500", batch_number="AZ1", quantity=2,
                                                               purchase_price=90.0, unit_price=90.0,
                                                               expiry_date=FUTURE)])
        self.assert_refused("MRP_REQUIRED", crud.confirm_document_and_update_stock, self.db, d.id, 1, req)

    def test_invoice_ocr_with_mrp_saves_mrp(self):
        d = self._doc()
        req = DocumentConfirmRequest(items=[DocumentItemVerify(product_name="AZEE 500", batch_number="AZ1", quantity=2,
                                                               purchase_price=90.0, mrp=125.0,
                                                               expiry_date=FUTURE)])
        crud.confirm_document_and_update_stock(self.db, d.id, 1, req)
        prod = self.db.query(Product).filter(Product.product_name == "AZEE 500").one()
        self.assertEqual(prod.unit_price, 125.0)
        self.assertEqual(prod.purchase_price, 90.0)


class TestImport(unittest.TestCase):
    MAP = {"product_name": "name", "price": "mrp", "purchase_price": "rate", "batch_number": "batch",
           "quantity": "qty", "expiry_date": "exp"}

    def row(self, **kw):
        base = {"name": "DOLO 650", "mrp": 30.0, "rate": 22.0, "batch": "B1", "qty": 5, "exp": FUTURE}
        base.update(kw)
        return import_service.validate_and_normalize_row(base, self.MAP, 2)

    def test_rate_column_is_purchase_price(self):
        self.assertIn("rate", import_service.COLUMN_ALIASES["purchase_price"]) if hasattr(
            import_service, "COLUMN_ALIASES") else None
        data, _warn, err = self.row()
        self.assertIsNone(err)
        self.assertEqual(data["unit_price"], 30.0)
        self.assertEqual(data["purchase_price"], 22.0)

    def test_missing_mrp_row_is_rejected(self):
        data, _w, err = self.row(mrp=None)
        self.assertIsNone(data)
        self.assertIn("price", err.lower())

    def test_missing_purchase_price_is_not_invented(self):
        data, warnings, err = self.row(rate=None)
        self.assertIsNone(err)
        self.assertEqual(data["purchase_price"], 0.0)
        self.assertTrue(any("left empty" in w for w in warnings))

    def test_mrp_below_purchase_row_is_rejected(self):
        data, _w, err = self.row(mrp=20.0, rate=22.0)
        self.assertIsNone(data)
        self.assertIn("lower than the purchase price", err)


class TestBillingUsesMrp(MrpRulesBase):
    def setUp(self):
        super().setUp()
        exp = date.today() + timedelta(days=300)
        self.db.add_all([
            Product(id=1, user_id=1, category="Allopathy", product_name="DOLO 650", batch_number="A", quantity=10, unit_price=30.0,
                    purchase_price=22.0, tablets_per_strip=15, expiry_date=exp),
            Product(id=2, user_id=1, category="Allopathy", product_name="NO MRP", batch_number="Z", quantity=10, unit_price=0.0,
                    purchase_price=22.0, tablets_per_strip=10, expiry_date=exp),
        ])
        self.db.commit()

    def sale(self, pid, price=None, unit_type="strip"):
        return SaleCreate(items=[SaleItemCreate(product_id=pid, quantity=1, unit_price=price, unit_type=unit_type,
                                                tablets_per_strip=15)],
                          payment_method="CASH", discount_type="flat", discount_value=0.0)

    def test_bill_charges_mrp_not_purchase_price(self):
        bill = crud.create_sale_transaction(db=self.db, sale_data=self.sale(1), user_id=1, current_user=self.user)
        self.assertEqual(bill.items[0].unit_price, 30.0)

    def test_price_above_mrp_is_refused(self):
        self.assert_refused("PRICE_ABOVE_MRP", crud.create_sale_transaction, db=self.db,
                            sale_data=self.sale(1, price=35.0), user_id=1, current_user=self.user)
        self.assertEqual(self.db.get(Product, 1).quantity, 10)

    def test_price_below_mrp_is_allowed(self):
        bill = crud.create_sale_transaction(db=self.db, sale_data=self.sale(1, price=28.0), user_id=1,
                                            current_user=self.user)
        self.assertEqual(bill.items[0].unit_price, 28.0)

    def test_loose_tablet_capped_at_mrp_per_tablet(self):
        self.assert_refused("PRICE_ABOVE_MRP", crud.create_sale_transaction, db=self.db,
                            sale_data=self.sale(1, price=2.50, unit_type="loose_tablet"), user_id=1,
                            current_user=self.user)  # MRP per tablet = 30 / 15 = 2.00

    def test_batch_without_mrp_cannot_be_billed(self):
        self.assert_refused("MRP_REQUIRED", crud.create_sale_transaction, db=self.db, sale_data=self.sale(2),
                            user_id=1, current_user=self.user)


class TestPriceReview(MrpRulesBase):
    def test_flags_suspicious_batches_without_changing_them(self):
        exp = date.today() + timedelta(days=300)
        self.db.add_all([
            Product(user_id=1, category="Allopathy", product_name="OK", batch_number="1", quantity=1, unit_price=30, purchase_price=20, expiry_date=exp),
            Product(user_id=1, category="Allopathy", product_name="NOMRP", batch_number="2", quantity=1, unit_price=0, purchase_price=20, expiry_date=exp),
            Product(user_id=1, category="Allopathy", product_name="SAME", batch_number="3", quantity=1, unit_price=20, purchase_price=20, expiry_date=exp),
            Product(user_id=1, category="Allopathy", product_name="BELOW", batch_number="4", quantity=1, unit_price=15, purchase_price=20, expiry_date=exp),
            Product(user_id=1, category="Allopathy", product_name="NOCOST", batch_number="5", quantity=1, unit_price=30, purchase_price=0, expiry_date=exp),
        ])
        self.db.commit()
        r = crud.get_price_review(self.db, 1)
        reasons = {i["product_name"]: i["reason"] for i in r["items"]}
        self.assertEqual(reasons, {
            "NOMRP": "mrp_missing",
            "SAME": "mrp_equals_purchase",
            "BELOW": "mrp_below_purchase",
            "NOCOST": "purchase_missing",
        })
        # Read-only: nothing changed.
        self.assertEqual(self.db.query(Product).filter(Product.product_name == "SAME").one().unit_price, 20)



class TestWebAddStockRoute(MrpRulesBase):
    """The restored web Add Stock route (/inventory/batch-add): all lines checked before anything is saved."""

    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        from sqlalchemy.pool import StaticPool
        import app as app_module
        import dependencies

        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        S = sessionmaker(bind=self.engine)
        s = S()
        s.add(User(id=1, shop_name="T", owner_name="T", email="w@t.com", password="pw"))
        s.commit()
        s.close()
        self.S = S

        def gdb():
            d = S()
            try:
                yield d
            finally:
                d.close()

        class U:
            id = 1
            staff_id = None

        self.app = app_module.app
        self.overrides = {dependencies.get_db: gdb, dependencies.get_current_user: lambda: U()}
        self.app.dependency_overrides.update(self.overrides)
        self.client = TestClient(self.app)

    def tearDown(self):
        for k in self.overrides:
            self.app.dependency_overrides.pop(k, None)
        super().tearDown()

    def line(self, name, mrp, cost=20.0, **kw):
        d = {"product_name": name, "batch_number": "B" + name, "quantity": 5, "purchase_price": cost,
             "mrp": mrp, "expiry_date": FUTURE}
        d.update(kw)
        return d

    def test_one_line_without_mrp_saves_nothing(self):
        r = self.client.post("/inventory/batch-add", json={"items": [self.line("A", 30.0), self.line("B", 0)]})
        self.assertEqual(r.status_code, 422)
        self.assertIn("MRP_REQUIRED", r.text)
        self.assertEqual(self.S().query(Product).count(), 0)

    def test_valid_lines_save_mrp_and_cost(self):
        r = self.client.post("/inventory/batch-add", json={"items": [self.line("A", 30.0), self.line("B", 45.0)]})
        self.assertEqual(r.status_code, 200, r.text)
        rows = {p.product_name: (p.unit_price, p.purchase_price) for p in self.S().query(Product).all()}
        self.assertEqual(rows, {"A": (30.0, 20.0), "B": (45.0, 20.0)})

    def test_price_review_endpoint(self):
        self.client.post("/inventory/batch-add", json={"items": [self.line("LOW", 15.0, confirm_mrp_below_cost=True)]})
        r = self.client.get("/inventory/price-review")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["counts"]["mrp_below_purchase"], 1)

if __name__ == "__main__":
    unittest.main()
