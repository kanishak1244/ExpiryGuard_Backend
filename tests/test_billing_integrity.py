"""
Billing integrity (in-memory SQLite, test login, no live database):
rounding, discount order, GST split, expired / out-of-stock refusal, near-expiry, idempotent retries, payments,
credit rules, and that the saved invoice, the printed PDF and the sales list agree on the total.
"""
import inspect
import io
import os
import sys
import unittest
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

os.environ.setdefault("ENABLE_SCHEDULER", "0")
os.environ["AI_USAGE_LOG_ENABLED"] = "0"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app as app_module
import crud
import dependencies
import models
from schemas import SaleCreate, SaleItemCreate

D = Decimal


def money(x):
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


class TestRounding(unittest.TestCase):
    def test_half_up_not_banker_or_binary(self):
        self.assertEqual(crud._round_half_up(2.675, 2), 2.68)   # round(2.675, 2) is 2.67
        self.assertEqual(crud._round_half_up(1.005, 2), 1.01)   # round(1.005, 2) is 1.0
        self.assertEqual(crud._round_half_up(0.285, 2), 0.29)
        self.assertEqual(crud._round_half_up(2.5), 3)
        self.assertEqual(crud._round_half_up(-2.675, 2), -2.68)
        self.assertEqual(crud._round_half_up(10, 2), 10.0)


class Base(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine)
        db = self.S()
        db.add(models.User(id=1, shop_name="Shop A", owner_name="O", email="a@test.invalid", password="x",
                           default_gst_percentage=12.0, gstin="27AAAAA0000A1Z5"))
        today = date.today()
        db.add(models.Product(id=1, user_id=1, category="Allopathy", product_name="DOLO 650", batch_number="OK1",
                              quantity=10, unit_price=100.0, purchase_price=60.0, tablets_per_strip=10,
                              expiry_date=today + timedelta(days=300), gst_percentage=12.0, gst_rate=12.0))
        db.add(models.Product(id=2, user_id=1, category="Allopathy", product_name="OLD MED", batch_number="EXP1",
                              quantity=10, unit_price=50.0, purchase_price=30.0, tablets_per_strip=10,
                              expiry_date=today - timedelta(days=3), gst_percentage=12.0, gst_rate=12.0))
        db.add(models.Product(id=3, user_id=1, category="Allopathy", product_name="NEAR MED", batch_number="NEAR1",
                              quantity=10, unit_price=40.0, purchase_price=25.0, tablets_per_strip=10,
                              expiry_date=today + timedelta(days=20), gst_percentage=5.0, gst_rate=5.0))
        db.add(models.Customer(id=1, user_id=1, name="Ramesh", phone="9000000001", pending_amount=0.0))
        db.commit()
        db.close()

        def get_db():
            d = self.S()
            try:
                yield d
            finally:
                d.close()

        def current_user():
            d = self.S()
            return dependencies.AuthenticatedUser(d.get(models.User, 1))

        self.overrides = {dependencies.get_db: get_db, dependencies.get_current_user: current_user}
        app_module.app.dependency_overrides.update(self.overrides)
        self.client = TestClient(app_module.app, raise_server_exceptions=False)

    def tearDown(self):
        for k in self.overrides:
            app_module.app.dependency_overrides.pop(k, None)

    def sell(self, items, **kw):
        db = self.S()
        try:
            user = db.get(models.User, 1)
            data = SaleCreate(items=[SaleItemCreate(**i) for i in items], payment_method=kw.pop("payment_method", "CASH"),
                              **kw)
            return crud.create_sale_transaction(db, data, 1, current_user=user)
        finally:
            db.close()

    def stock(self, pid):
        db = self.S()
        try:
            return db.get(models.Product, pid).quantity
        finally:
            db.close()


class TestSaleMath(Base):
    def test_line_and_bill_discount_then_gst_match_an_independent_decimal_calculation(self):
        # 3 x 100.00, line discount Rs 10, bill discount 5%, GST 12% (prices are tax-exclusive in DawaiFlow)
        sale = self.sell([dict(product_id=1, quantity=3, unit_price=100.0, discount=10.0, batch_number="OK1",
                               gst_percentage=12.0)], discount_type="percent", discount_value=5.0)
        gross = money(3 * 100)
        taxable = gross - money(10)
        bill_disc = money(taxable * D("0.05"))
        final_taxable = taxable - bill_disc
        cgst = money(final_taxable * D("0.06"))
        self.assertAlmostEqual(sale.total_taxable_value, float(final_taxable), places=2)
        self.assertAlmostEqual(sale.total_cgst, float(cgst), places=2)
        self.assertAlmostEqual(sale.total_sgst, float(cgst), places=2)
        self.assertAlmostEqual(sale.total_amount, float(final_taxable + cgst * 2), places=2)

    def test_gst_split_is_half_each_and_rounded_per_line(self):
        sale = self.sell([dict(product_id=1, quantity=1, unit_price=33.33, batch_number="OK1", gst_percentage=12.0),
                          dict(product_id=3, quantity=1, unit_price=40.0, batch_number="NEAR1", gst_percentage=5.0)])
        per_line = [money(money(33.33) * D("0.06")), money(money(40) * D("0.025"))]
        self.assertAlmostEqual(sale.total_cgst, float(sum(per_line)), places=2)
        self.assertEqual(round(sale.total_cgst, 2), round(sale.total_sgst, 2))
        self.assertAlmostEqual(sale.total_amount, round(sale.total_taxable_value + sale.total_cgst * 2, 2), places=2)

    def test_the_total_is_never_negative_and_discounts_are_bounded(self):
        with self.assertRaises(HTTPException) as e1:
            self.sell([dict(product_id=1, quantity=1, unit_price=100.0, discount=150.0, batch_number="OK1")])
        self.assertEqual(e1.exception.status_code, 400)           # line discount above the line price
        with self.assertRaises(HTTPException) as e2:
            self.sell([dict(product_id=1, quantity=1, unit_price=100.0, batch_number="OK1")],
                      discount_type="flat", discount_value=500.0)
        self.assertEqual(e2.exception.status_code, 400)           # bill discount above the taxable subtotal
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):                  # a percentage above 100 is refused at the door
            SaleCreate(items=[SaleItemCreate(product_id=1, quantity=1)], payment_method="CASH",
                       discount_type="percent", discount_value=150.0)
        self.assertEqual(self.stock(1), 10)                       # nothing was deducted by the refused bills

    def test_price_above_mrp_is_refused(self):
        with self.assertRaises(HTTPException) as e:
            self.sell([dict(product_id=1, quantity=1, unit_price=100.5, batch_number="OK1")])
        self.assertIn("PRICE_ABOVE_MRP", str(e.exception.detail))


class TestBatchesAndStock(Base):
    def test_expired_batch_cannot_be_sold_and_stock_is_untouched(self):
        with self.assertRaises(HTTPException) as e:
            self.sell([dict(product_id=2, quantity=1, unit_price=50.0, batch_number="EXP1")])
        self.assertEqual(e.exception.status_code, 422)
        self.assertEqual(self.stock(2), 10)

    def test_near_expiry_batch_is_still_sellable(self):
        sale = self.sell([dict(product_id=3, quantity=2, unit_price=40.0, batch_number="NEAR1")])
        self.assertEqual(self.stock(3), 8)
        self.assertGreater(sale.total_amount, 0)

    def test_selling_more_than_the_stock_is_refused_and_rolled_back(self):
        with self.assertRaises(HTTPException):
            self.sell([dict(product_id=1, quantity=1, unit_price=100.0, batch_number="OK1"),
                       dict(product_id=3, quantity=11, unit_price=40.0, batch_number="NEAR1")])
        self.assertEqual((self.stock(1), self.stock(3)), (10, 10))   # the first, valid line was not kept either

    def test_a_valid_alternative_batch_is_honoured_and_never_silently_swapped(self):
        db = self.S()
        db.add(models.Product(id=4, user_id=1, category="Allopathy", product_name="DOLO 650", batch_number="OK2",
                              quantity=5, unit_price=100.0, purchase_price=60.0, tablets_per_strip=10,
                              expiry_date=date.today() + timedelta(days=500), gst_percentage=12.0, gst_rate=12.0))
        db.commit()
        db.close()
        self.sell([dict(product_id=4, quantity=2, unit_price=100.0, batch_number="OK2")])
        self.assertEqual((self.stock(1), self.stock(4)), (10, 3))

    def test_stock_rows_are_locked_while_a_bill_is_saved(self):
        # Two terminals selling the same batch rely on row locks (Postgres). SQLite has no row locks, so the
        # behaviour itself cannot be exercised here; this pins down that the lock is requested.
        src = inspect.getsource(crud.create_sale_transaction)
        self.assertIn("with_for_update", src)


class TestRetryAndIdempotency(Base):
    def test_same_idempotency_key_saves_once_and_deducts_stock_once(self):
        item = [dict(product_id=1, quantity=2, unit_price=100.0, batch_number="OK1")]
        first = self.sell(item, idempotency_key="df_sale_test_key_1")
        again = self.sell(item, idempotency_key="df_sale_test_key_1")   # a retry after a slow or lost response
        self.assertEqual(first.id, again.id)
        self.assertEqual(first.bill_number, again.bill_number)
        self.assertEqual(self.stock(1), 8)
        db = self.S()
        self.assertEqual(db.query(models.Sale).count(), 1)
        db.close()

    def test_bill_numbers_are_unique(self):
        numbers = {self.sell([dict(product_id=1, quantity=1, unit_price=100.0, batch_number="OK1")]).bill_number
                   for _ in range(8)}
        self.assertEqual(len(numbers), 8)


class TestPayments(Base):
    def test_cash_upi_card_are_accepted(self):
        for method in ("CASH", "UPI", "CARD"):
            sale = self.sell([dict(product_id=1, quantity=1, unit_price=100.0, batch_number="OK1")], payment_method=method)
            self.assertEqual(sale.payment_method, method)

    def test_credit_needs_a_customer_and_is_recorded_against_them(self):
        with self.assertRaises(HTTPException) as e:
            self.sell([dict(product_id=1, quantity=1, unit_price=100.0, batch_number="OK1")], payment_method="CREDIT")
        self.assertEqual(e.exception.status_code, 400)
        sale = self.sell([dict(product_id=1, quantity=1, unit_price=100.0, batch_number="OK1")],
                         payment_method="CREDIT", customer_name="Ramesh")
        db = self.S()
        self.assertAlmostEqual(db.get(models.Customer, 1).pending_amount, sale.total_amount, places=2)
        db.close()

    def test_split_payment_must_add_up_to_the_bill(self):
        item = [dict(product_id=1, quantity=1, unit_price=100.0, batch_number="OK1")]
        total = round(100 * 1.12, 2)
        ok = self.sell(item, payment_method="SPLIT",
                       payments=[dict(payment_method="CASH", amount=50.0), dict(payment_method="UPI", amount=total - 50.0)])
        self.assertAlmostEqual(ok.total_amount, total, places=2)
        with self.assertRaises(HTTPException):
            self.sell(item, payment_method="SPLIT",
                      payments=[dict(payment_method="CASH", amount=50.0), dict(payment_method="UPI", amount=10.0)])


class TestInvoiceAgreesEverywhere(Base):
    def test_saved_total_equals_pdf_and_sales_list(self):
        sale = self.sell([dict(product_id=1, quantity=3, unit_price=100.0, discount=7.5, batch_number="OK1"),
                          dict(product_id=3, quantity=2, unit_price=40.0, batch_number="NEAR1")],
                         discount_type="percent", discount_value=3.0)
        pdf = self.client.get(f"/billing/{sale.id}/pdf")
        self.assertEqual(pdf.status_code, 200, pdf.text[:200])
        text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf.content)).pages)
        self.assertIn(f"{sale.total_amount:.2f}", text)
        listed = self.client.get("/sales?skip=0&limit=5")
        self.assertEqual(listed.status_code, 200)
        rows = listed.json() if isinstance(listed.json(), list) else listed.json().get("items", [])
        self.assertAlmostEqual(next(r for r in rows if r["id"] == sale.id)["total_amount"], sale.total_amount, places=2)


if __name__ == "__main__":
    unittest.main()
