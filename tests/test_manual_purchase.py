"""
Manual purchase entry engine: POST /purchases/manual, /purchases/check-duplicate, /purchases/medicine-search.

Pinned rules: one transaction (a bad line saves nothing); server recalculates every amount; duplicate supplier invoice
refused (also the retry guard); same batch -> that batch grows, new batch -> new row (medicine details copied), same batch
with another expiry -> refused; free units add to stock and lower the unit cost; ledger/dashboard/list stay consistent;
other shops see nothing.
"""
import os
import sys
import unittest
from datetime import date, timedelta

os.environ.setdefault("ENABLE_SCHEDULER", "0")
os.environ["AI_USAGE_LOG_ENABLED"] = "0"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app as app_module
import dependencies
import models
import purchase_entry

FUTURE = date.today() + timedelta(days=400)


def line(**kw):
    base = {"product_name": "NEWMED 500", "batch_number": "B1", "expiry_date": str(FUTURE), "quantity": 10,
            "free_quantity": 0, "purchase_rate": 50.0, "discount_percent": 0, "gst_rate": 12.0, "mrp": 90.0}
    base.update(kw)
    return base


class TestManualPurchase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False)
        db = self.S()
        for uid in (1, 2):
            db.add(models.User(id=uid, shop_name="S%d" % uid, owner_name="O", email="mp%d@test.invalid" % uid, password="x",
                               default_gst_percentage=12.0))
        db.add(models.Supplier(id=1, user_id=1, name="Alpha Pharma"))
        db.add(models.Supplier(id=2, user_id=2, name="Other"))
        db.add(models.Product(id=1, user_id=1, category="allopathy", product_name="DOLO 650", brand="Micro Labs",
                              composition="Paracetamol 650", batch_number="D1", quantity=20, unit_price=100.0,
                              purchase_price=60.0, tablets_per_strip=15, units_per_pack=15, gst_percentage=12.0,
                              gst_rate=12.0, hsn_code="3004", pack_size_label="strip of 15",
                              expiry_date=FUTURE))
        db.add(models.MedicineCatalog(id=1, product_name="AUGMENTIN 625", brand="GSK", hsn_code="3004", gst_rate=12.0,
                                      tablets_per_strip=10, units_per_pack=10, composition="Amoxicillin + Clavulanic"))
        db.commit()
        db.close()
        self.uid = 1

        def get_db():
            d = self.S()
            try:
                yield d
            finally:
                d.close()

        def current_user():
            d = self.S()
            return dependencies.AuthenticatedUser(d.get(models.User, self.uid))

        self.overrides = {dependencies.get_db: get_db, dependencies.get_current_user: current_user}
        app_module.app.dependency_overrides.update(self.overrides)
        self.c = TestClient(app_module.app, raise_server_exceptions=False)

    def tearDown(self):
        for k in self.overrides:
            app_module.app.dependency_overrides.pop(k, None)

    def post(self, items, inv="INV-1", status="UNPAID", **kw):
        body = {"supplier_id": 1, "invoice_number": inv, "invoice_date": str(date.today()), "payment_status": status, "items": items}
        body.update(kw)
        return self.c.post("/purchases/manual", json=body)

    def rows(self, name=None):
        d = self.S()
        try:
            q = d.query(models.Product).filter(models.Product.user_id == 1)
            if name:
                q = q.filter(models.Product.product_name == name)
            return q.order_by(models.Product.id).all()
        finally:
            d.close()

    def counts(self):
        d = self.S()
        try:
            return (d.query(models.PurchaseInvoice).count(), d.query(models.PurchaseItem).count(),
                    d.query(models.InventoryTransaction).count(), sum(p.quantity for p in d.query(models.Product).all()))
        finally:
            d.close()

    # ---- calculations
    def test_line_math_discount_gst_free(self):
        c = purchase_entry.calc_line(10, 2, 50.0, 10, 12)
        self.assertEqual((c["gross"], c["discount"], c["taxable"], c["gst"], c["total"]), (500.0, 50.0, 450.0, 54.0, 504.0))
        self.assertEqual(c["received_qty"], 12)
        self.assertEqual(c["net_unit_cost"], 37.5)               # 450 / 12 units received
        z = purchase_entry.calc_line(3, 0, 33.33, 0, 0)          # 0% GST must stay 0
        self.assertEqual((z["taxable"], z["gst"], z["total"]), (99.99, 0.0, 99.99))
        h = purchase_entry.calc_line(1, 0, 2.675, 0, 0)          # half-up to the paisa
        self.assertEqual(h["taxable"], 2.68)

    # ---- posting
    def test_new_medicine_creates_document_stock_ledger_and_totals(self):
        r = self.post([line(product_name="NEWMED 500", brand="Acme", composition="Zinc", hsn_code="3004")])
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertEqual(body["totals"]["total"], 560.0)         # 500 + 12%
        self.assertEqual(body["voucher_no"], "PUR-%05d" % body["id"])
        p = self.rows("NEWMED 500")[0]
        self.assertEqual((p.quantity, p.unit_price, p.batch_number, p.brand, p.composition), (10, 90.0, "B1", "Acme", "Zinc"))
        self.assertEqual(self.counts()[:3], (1, 1, 1))
        led = self.c.get("/suppliers/1/ledger").json()
        self.assertEqual(led["balance_payable"], 560.0)
        lst = self.c.get("/purchases/list").json()
        self.assertEqual(lst["items"][0]["invoice_number"], "INV-1")
        self.assertEqual(lst["summary"]["outstanding_payables"], 560.0)
        self.assertEqual(self.c.get("/purchases/dashboard").json()["pending_supplier_payables"], 560.0)

    def test_paid_invoice_owes_nothing(self):
        self.assertEqual(self.post([line()], status="PAID").status_code, 201)
        self.assertEqual(self.c.get("/suppliers/1/ledger").json()["balance_payable"], 0.0)

    def test_existing_medicine_new_batch_copies_master_and_makes_one_new_row(self):
        r = self.post([line(product_name="DOLO 650", product_id=1, batch_number="D2", mrp=110.0, gst_rate=5.0)])
        self.assertEqual(r.status_code, 201, r.text)
        rows = self.rows("DOLO 650")
        self.assertEqual(len(rows), 2)
        new = rows[1]
        self.assertEqual((new.batch_number, new.quantity, new.brand, new.composition, new.units_per_pack, new.gst_rate),
                         ("D2", 10, "Micro Labs", "Paracetamol 650", 15, 5.0))
        self.assertEqual(rows[0].quantity, 20)                   # old batch untouched

    def test_existing_batch_same_expiry_is_updated_not_duplicated(self):
        r = self.post([line(product_name="dolo 650", batch_number="d1", expiry_date=str(FUTURE), quantity=5, mrp=105.0)])
        self.assertEqual(r.status_code, 201, r.text)
        rows = self.rows("DOLO 650")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].quantity, rows[0].unit_price, rows[0].expiry_date), (25, 105.0, FUTURE))
        self.assertFalse(r.json()["lines"][0]["new_batch"])

    def test_same_batch_other_expiry_is_refused_and_nothing_saved(self):
        before = self.counts()
        r = self.post([line(product_name="DOLO 650", batch_number="D1", expiry_date=str(FUTURE + timedelta(days=60)))])
        self.assertEqual(r.status_code, 400)
        self.assertIn("already exists with expiry", r.text)
        self.assertEqual(self.counts(), before)

    def test_free_quantity_adds_stock_and_lowers_unit_cost(self):
        r = self.post([line(quantity=10, free_quantity=2, discount_percent=10)])
        self.assertEqual(r.status_code, 201, r.text)
        p = self.rows("NEWMED 500")[0]
        self.assertEqual(p.quantity, 12)
        self.assertEqual(p.purchase_price, 37.5)
        d = self.S()
        it = d.query(models.PurchaseItem).first()
        d.close()
        self.assertEqual((it.quantity, it.purchase_price), (12, 37.5))
        self.assertEqual(r.json()["totals"]["total"], 504.0)

    def test_gst_zero_is_kept(self):
        self.assertEqual(self.post([line(gst_rate=0)]).status_code, 201)
        p = self.rows("NEWMED 500")[0]
        self.assertEqual((p.gst_rate, p.gst_percentage), (0.0, 0.0))

    def test_two_lines_same_batch_on_one_bill_merge(self):
        r = self.post([line(quantity=4), line(quantity=6)])
        self.assertEqual(r.status_code, 201, r.text)
        rows = self.rows("NEWMED 500")
        self.assertEqual((len(rows), rows[0].quantity), (1, 10))

    def test_catalog_medicine_becomes_shop_batch(self):
        r = self.post([line(product_name="AUGMENTIN 625", brand="GSK", units_per_pack=10, composition="Amoxicillin + Clavulanic")])
        self.assertEqual(r.status_code, 201, r.text)
        p = self.rows("AUGMENTIN 625")[0]
        self.assertEqual((p.quantity, p.units_per_pack), (10, 10))

    # ---- refusals
    def test_duplicate_supplier_invoice_refused_and_retry_does_not_double_stock(self):
        self.assertEqual(self.post([line()]).status_code, 201)
        after_first = self.counts()
        for inv in ("INV-1", " inv-1 "):
            r = self.post([line()], inv=inv)
            self.assertEqual(r.status_code, 409)
            self.assertIn("DUPLICATE_INVOICE", r.text)
        self.assertEqual(self.counts(), after_first)
        chk = self.c.get("/purchases/check-duplicate?supplier_id=1&invoice_number=INV-1").json()
        self.assertTrue(chk["is_duplicate"])
        self.assertFalse(self.c.get("/purchases/check-duplicate?supplier_id=1&invoice_number=NOPE").json()["is_duplicate"])

    def test_failure_on_second_line_rolls_everything_back(self):
        before = self.counts()
        r = self.post([line(), line(product_name="OTHER MED", expiry_date=str(date.today() - timedelta(days=3)))])
        self.assertEqual(r.status_code, 400)
        self.assertIn("expired", r.text)
        self.assertEqual(self.counts(), before)
        r = self.post([line(), line(product_name="LOWMRP", mrp=10.0)])           # MRP below cost: refused by the shared rule
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.counts(), before)

    def test_expected_total_mismatch_is_refused(self):
        before = self.counts()
        r = self.post([line()], expected_total=999.0)
        self.assertEqual((r.status_code), 409)
        self.assertIn("TOTAL_MISMATCH", r.text)
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.post([line()], expected_total=560.0).status_code, 201)

    def test_validation_errors(self):
        for bad in (line(quantity=0), line(batch_number=" "), line(mrp=0), line(gst_rate=40), line(discount_percent=101),
                    line(purchase_rate=-1), line(free_quantity=-1)):
            self.assertEqual(self.post([bad]).status_code, 422, bad)
        self.assertEqual(self.post([]).status_code, 422)
        self.assertEqual(self.post([line()], invoice_date=str(date.today() + timedelta(days=30))).status_code, 400)

    def test_other_shops_supplier_and_medicine_are_refused(self):
        self.assertEqual(self.post([line()], supplier_id=2).status_code, 404)
        self.assertEqual(self.post([line(product_id=999)]).status_code, 404)
        self.uid = 2
        self.assertEqual(self.c.get("/purchases/medicine-search?q=dolo").json(), [])

    # ---- search
    def test_medicine_search_shop_first_then_catalog(self):
        res = self.c.get("/purchases/medicine-search?q=dolo").json()
        self.assertEqual(res[0]["source"], "shop")
        self.assertEqual(res[0]["batches"], [])          # batch data is never suggested (a new purchase has its own batch)
        self.assertEqual(res[0]["last_purchase_rate"], 60.0)
        cat = self.c.get("/purchases/medicine-search?q=augmentin").json()
        self.assertEqual((cat[0]["source"], cat[0]["catalog_id"]), ("catalog", 1))
        self.assertEqual(self.c.get("/purchases/medicine-search?q=d").json(), [])


class TestManualPurchasePage(unittest.TestCase):
    def _read(self, rel):
        with open(os.path.join(os.path.dirname(__file__), "..", rel), encoding="utf-8") as f:
            return f.read()

    def test_landing_has_fourth_action_in_order(self):
        html = self._read("web/purchases.html")
        order = [html.index(x) for x in ("Scan / Upload Bill", "Search Medicine", "Direct Excel / CSV Import", "Add Manually")]
        self.assertEqual(order, sorted(order))
        self.assertIn("Enter supplier invoice and medicine details manually in a spreadsheet-style form.", html)
        self.assertIn("purchase_entry.html", self._read("web/js/purchases_page.js"))

    def test_entry_page_wiring(self):
        html = self._read("web/purchase_entry.html")
        for needle in ("purchase_entry_core.js", "purchase_entry.js", "Save Purchase", "Save as Draft", "pe-supplier", "pe-invoice-no"):
            self.assertIn(needle, html)


if __name__ == "__main__":
    unittest.main()
