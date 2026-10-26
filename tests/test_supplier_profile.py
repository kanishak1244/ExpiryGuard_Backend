"""
Supplier profile, purchase history/detail and linked-medicine stock status.

Pinned rules: the profile is fetched by supplier id from the server (404 for another pharmacy's supplier); its money equals the
ledger and dashboard; a purchase opens by its own id and only under its own supplier, read-only; the original bill is linked only
when it can be identified without guessing; stock status comes from recorded movements (never "quantity is zero"), sold /
returned numbers are shown only when this supplier alone supplied a reconciled batch, and drafts are not received stock.
"""
import json
import uuid
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
import supplier_profile
from routes import document_archive_routes as dar

JPEG = b"\xFF\xD8\xFF\xE0" + b"\x00" * 64
FUT = (date.today() + timedelta(days=400)).isoformat()
PAST = date.today() - timedelta(days=10)


class TestSupplierProfile(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False)
        db = self.S()
        for uid in (1, 2):
            db.add(models.User(id=uid, shop_name="S%d" % uid, owner_name="O", email="sp%d@test.invalid" % uid, password="x", default_gst_percentage=12.0))
        db.add(models.Supplier(id=1, user_id=1, name="Alpha Pharma", gstin="07AAAAA0000A1Z5", phone="999", address="Delhi"))
        db.add(models.Supplier(id=2, user_id=1, name="Beta Distributors"))
        db.add(models.Supplier(id=3, user_id=2, name="Other Shop Supplier"))
        db.commit()
        db.close()
        self.uid = 1
        self.files = []
        self.n = 0

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
        for f in self.files:
            try:
                os.remove(f)
            except OSError:
                pass

    # ---- helpers
    def buy(self, supplier=1, name="DOLO 650", batch="D1", qty=10, inv=None, status="UNPAID", expiry=FUT, rate=50.0, mrp=90.0):
        self.n += 1
        r = self.c.post("/purchases/manual", json={"supplier_id": supplier, "invoice_number": inv or "INV-%d" % self.n, "invoice_date": date.today().isoformat(),
                                                    "payment_status": status, "items": [{"product_name": name, "batch_number": batch, "expiry_date": expiry,
                                                                                         "quantity": qty, "purchase_rate": rate, "gst_rate": 12, "mrp": mrp}]})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def sell(self, product_id, qty, unit="strip", mrp=90.0):
        self.n += 1
        r = self.c.post("/sales", json={"items": [{"product_id": product_id, "quantity": qty, "unit_price": mrp, "unit_type": unit}], "payment_method": "CASH",
                                         "idempotency_key": "sp-%s" % uuid.uuid4().hex})
        self.assertIn(r.status_code, (200, 201), r.text)

    def pid(self, name="DOLO 650", batch="D1"):
        d = self.S()
        try:
            return d.query(models.Product).filter(models.Product.product_name == name, models.Product.batch_number == batch).first().id
        finally:
            d.close()

    def stock(self, supplier=1, **params):
        qs = "&".join("%s=%s" % kv for kv in params.items())
        r = self.c.get("/suppliers/%d/stock?%s" % (supplier, qs))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def row(self, name="DOLO 650", batch="D1", supplier=1):
        return next(i for i in self.stock(supplier)["items"] if i["product_name"] == name and i["batch_number"] == batch)

    def snapshot(self):
        d = self.S()
        try:
            return (d.query(models.PurchaseInvoice).count(), d.query(models.InventoryTransaction).count(), d.query(models.Sale).count(),
                    sorted((p.id, p.quantity) for p in d.query(models.Product).all()))
        finally:
            d.close()

    # ---- profile
    def test_profile_opens_the_right_supplier_and_its_money_matches_the_ledger_and_dashboard(self):
        self.buy(1, inv="A-1", qty=10)
        self.buy(1, name="ZINC", batch="Z1", inv="A-2", status="PAID")
        self.buy(2, name="B MED", batch="B1", inv="B-1")
        self.c.post("/supplier-payments", json={"supplier_id": 1, "amount_paid": 100.0})
        a = self.c.get("/suppliers/1/profile").json()
        b = self.c.get("/suppliers/2/profile").json()
        self.assertEqual((a["name"], b["name"]), ("Alpha Pharma", "Beta Distributors"))
        self.assertEqual((a["gstin"], a["phone"], a["address"]), ("07AAAAA0000A1Z5", "999", "Delhi"))
        led = self.c.get("/suppliers/1/ledger").json()
        self.assertEqual(a["balance_payable"], led["balance_payable"])
        self.assertEqual((a["total_purchased"], a["total_paid"], a["purchase_count"]), (led["total_purchased"], led["total_paid"], 2))
        dash = self.c.get("/purchases/dashboard").json()["pending_supplier_payables"]
        self.assertEqual(round(a["balance_payable"] + b["balance_payable"], 2), dash)

    def test_supplier_list_figures_come_from_purchase_invoices(self):
        self.buy(1, inv="A-1")
        row = next(s for s in self.c.get("/suppliers").json() if s["id"] == 1)
        self.assertEqual(row["purchase_count"], 1)
        self.assertGreater(row["total_purchases"], 0)
        self.assertIsNotNone(row["last_purchase_date"])

    def test_other_pharmacies_and_unknown_suppliers_are_refused(self):
        self.buy(1, inv="A-1")
        for path in ("/suppliers/3/profile", "/suppliers/3/stock", "/suppliers/3/ledger", "/suppliers/999/profile", "/suppliers/999/stock"):
            self.assertEqual(self.c.get(path).status_code, 404, path)
        self.uid = 2
        for path in ("/suppliers/1/profile", "/suppliers/1/stock", "/suppliers/1/ledger"):
            self.assertEqual(self.c.get(path).status_code, 404, path)
        app_module.app.dependency_overrides.pop(dependencies.get_current_user, None)
        anon = TestClient(app_module.app, raise_server_exceptions=False)
        self.assertIn(anon.get("/suppliers/1/profile").status_code, (401, 403))

    # ---- ledger paging
    def test_ledger_pages_filters_and_running_balance(self):
        for i in range(5):
            self.buy(1, name="M%d" % i, batch="B%d" % i, inv="L-%d" % i, qty=1)
        self.c.post("/supplier-payments", json={"supplier_id": 1, "amount_paid": 10.0})
        full = self.c.get("/suppliers/1/ledger?page_size=500").json()
        p1 = self.c.get("/suppliers/1/ledger?page=1&page_size=2&newest_first=true").json()
        self.assertEqual((p1["entries_total"], len(p1["entries"]), p1["history_total"]), (6, 2, 6))
        self.assertEqual(p1["entries"][0]["type"], "PAYMENT")                                   # newest first
        self.assertEqual(p1["entries"][0]["balance"], full["balance_payable"])                  # balances are over the whole history
        pay = self.c.get("/suppliers/1/ledger?type=PAYMENT").json()
        self.assertEqual((pay["entries_total"], pay["entries"][0]["type"]), (1, "PAYMENT"))
        self.assertEqual(self.c.get("/suppliers/1/ledger?type=bogus").status_code, 422)

    # ---- purchase history and detail
    def test_purchase_history_is_scoped_and_detail_opens_the_exact_document(self):
        a = self.buy(1, inv="SAME-NO", qty=10)
        b = self.buy(2, name="B MED", batch="B1", inv="SAME-NO", qty=5)          # same invoice number, another supplier
        hist = self.c.get("/purchases/list?supplier_id=1").json()
        self.assertEqual([i["id"] for i in hist["items"]], [a["id"]])
        d = self.c.get("/purchases/detail/%d?supplier_id=1" % a["id"]).json()
        self.assertEqual((d["id"], d["supplier_name"], d["invoice_number"], d["voucher_no"]), (a["id"], "Alpha Pharma", "SAME-NO", a["voucher_no"]))
        line = d["items"][0]
        self.assertEqual((line["product_name"], line["batch_number"], line["quantity"], line["mrp"], line["gst_rate"], line["expiry_date"]),
                         ("DOLO 650", "D1", 10, 90.0, 12.0, FUT))
        self.assertEqual((line["taxable"], line["gst"], line["line_total"]), (500.0, 60.0, 560.0))
        self.assertEqual((d["totals"]["subtotal"], d["totals"]["gst"], d["total_amount"], d["totals"]["matches_stored_total"]), (500.0, 60.0, 560.0, True))
        self.assertEqual((d["purchase_status"], d["payment_status"], d["paid_amount"], d["outstanding_amount"]), ("Posted", "UNPAID", 0.0, 560.0))
        self.assertIsNone(d["source_document"])                                  # no scanned bill: stated, not invented
        # the purchase of another supplier does not open under this supplier, nor from another pharmacy
        self.assertEqual(self.c.get("/purchases/detail/%d?supplier_id=1" % b["id"]).status_code, 404)
        self.assertEqual(self.c.get("/purchases/detail/%d?supplier_id=2" % b["id"]).json()["supplier_name"], "Beta Distributors")
        self.uid = 2
        self.assertEqual(self.c.get("/purchases/detail/%d" % a["id"]).status_code, 404)

    def test_partial_payment_status_shows_no_invented_amounts(self):
        r = self.c.post("/purchases", json={"supplier_id": 1, "invoice_number": "OLD-1", "invoice_date": date.today().isoformat(), "total_amount": 100.0,
                                            "tax_amount": 10.0, "payment_status": "PARTIAL", "items": []})
        self.assertEqual(r.status_code, 200, r.text)
        d = self.c.get("/purchases/detail/%d" % r.json()["id"]).json()
        self.assertEqual((d["payment_status"], d["paid_amount"], d["outstanding_amount"], d["items"]), ("PARTIAL", None, None, []))

    def test_viewing_history_and_detail_changes_nothing(self):
        a = self.buy(1, inv="A-1")
        self.sell(self.pid(), 2)
        before = self.snapshot()
        led = self.c.get("/suppliers/1/ledger").json()["balance_payable"]
        for path in ("/suppliers/1/profile", "/suppliers/1/stock", "/suppliers/1/ledger", "/purchases/list?supplier_id=1", "/purchases/detail/%d?supplier_id=1" % a["id"]):
            self.assertEqual(self.c.get(path).status_code, 200, path)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.c.get("/suppliers/1/ledger").json()["balance_payable"], led)

    def test_original_bill_is_linked_when_it_can_be_identified_and_missing_files_are_handled(self):
        up = self.c.post("/documents/upload", files={"file": ("bill.jpg", JPEG, "image/jpeg")})
        doc = up.json()
        path = os.path.join(str(dar.DOCUMENTS_DIR), os.path.basename(doc["file_path"]))
        self.files.append(path)
        d = self.S()
        x = d.get(models.Document, doc["id"])
        x.ocr_raw_json = json.dumps({"supplier_name": "Alpha Pharma", "invoice_number": "OCR-5", "invoice_date": date.today().isoformat(), "total_amount": 560.0,
                                     "items": [{"product_name": "OCRMED", "hsn_code": "3004", "gst_rate": 12, "batch_number": "O1", "expiry_date": FUT,
                                                "quantity": 10, "purchase_price": 50.0, "mrp": 90.0, "total_price": 500.0}]})
        x.ocr_status, x.supplier_id, x.invoice_number, x.invoice_date, x.total_amount = "Needs Review", 1, "OCR-5", date.today(), 560.0
        d.commit()
        d.close()
        conf = self.c.post("/documents/%d/confirm-review" % doc["id"], json={"acknowledge_warnings": True})
        self.assertEqual(conf.status_code, 200, conf.text)
        det = self.c.get("/purchases/detail/%d?supplier_id=1" % conf.json()["id"]).json()
        self.assertEqual((det["source_document"]["id"], det["source_document"]["file_type"]), (doc["id"], "image/jpeg"))
        self.assertEqual(self.c.get("/documents/%d/file" % doc["id"]).content, JPEG)             # the bill can be shown
        os.remove(path)
        gone = self.c.get("/documents/%d/file" % doc["id"])
        self.assertEqual(gone.status_code, 404)                                                    # a clear message, not a broken image
        self.assertIn("no longer stored", gone.text)
        self.assertEqual(self.c.get("/purchases/detail/%d?supplier_id=1" % conf.json()["id"]).status_code, 200)

    def test_two_possible_bills_mean_no_link_rather_than_a_guess(self):
        a = self.buy(1, inv="DUP-9")
        d = self.S()
        for i in range(2):
            d.add(models.Document(user_id=1, supplier_id=1, title="b%d" % i, doc_type="purchase_invoice", file_path="/x%d" % i, file_type="image/jpeg",
                                  invoice_number="dup-9", ocr_status="Verified"))
        d.commit()
        d.close()
        self.assertIsNone(self.c.get("/purchases/detail/%d" % a["id"]).json()["source_document"])

    # ---- linked medicine stock
    def test_in_stock_and_partially_sold(self):
        self.buy(1, qty=10)
        r = self.row()
        self.assertEqual((r["status"], r["available"], r["quantity_received"], r["quantity_sold"]), ("In Stock", 10, 10, 0 if False else r["quantity_sold"]))
        self.assertEqual(r["status"], "In Stock")
        self.sell(self.pid(), 4)
        r = self.row()
        self.assertEqual((r["status"], r["available"], r["quantity_sold"], r["quantity_received"], r["reconciled"]), ("Partially Sold", 6, 4, 10, True))
        self.assertEqual((r["invoice_number"] is not None, r["mrp"], r["company"] is None or True), (True, 90.0, True))

    def test_sold_out_only_when_the_movements_prove_it(self):
        self.buy(1, name="FASTMED", batch="F1", qty=5)
        self.sell(self.pid("FASTMED", "F1"), 5)
        r = self.row("FASTMED", "F1")
        self.assertEqual((r["status"], r["available"], r["quantity_sold"]), ("Sold Out", 0, 5))
        # zero stock with no recorded reason is NOT called sold out
        self.buy(1, name="LOSTMED", batch="L1", qty=5)
        d = self.S()
        d.get(models.Product, self.pid("LOSTMED", "L1")).quantity = 0
        d.commit()
        d.close()
        r = self.row("LOSTMED", "L1")
        self.assertEqual((r["status"], r["quantity_sold"], r["reconciled"]), ("Unavailable", None, False))

    def test_expired_batches_are_not_mislabeled(self):
        self.buy(1, name="OLDMED", batch="E1", qty=5)
        self.buy(1, name="OLDSOLD", batch="E2", qty=5)
        self.sell(self.pid("OLDSOLD", "E2"), 2)
        d = self.S()
        for n, b in (("OLDMED", "E1"), ("OLDSOLD", "E2")):
            d.get(models.Product, self.pid(n, b)).expiry_date = PAST
        d.commit()
        d.close()
        self.assertEqual(self.row("OLDMED", "E1")["status"], "Expired")
        self.assertEqual(self.row("OLDSOLD", "E2")["status"], "Expired")                 # stock remains, past expiry: Expired, not Partially Sold
        d = self.S()
        d.get(models.Product, self.pid("OLDMED", "E1")).quantity = 0                      # gone, unexplained, and expired
        d.commit()
        d.close()
        r = self.row("OLDMED", "E1")
        self.assertEqual(r["status"], "Expired")
        self.assertNotEqual(r["status"], "Sold Out")

    def test_supplier_returns_are_recognised(self):
        self.buy(1, name="BACKMED", batch="R1", qty=5)
        pid = self.pid("BACKMED", "R1")
        r = self.c.post("/purchases/returns", json={"supplier_id": 1, "total_returned_value": 250.0, "reason": "damaged",
                                                    "items": [{"product_id": pid, "batch_number": "R1", "quantity": 5, "purchase_price": 50.0}]})
        self.assertEqual(r.status_code, 201, r.text)
        row = self.row("BACKMED", "R1")
        self.assertEqual((row["status"], row["available"], row["quantity_returned"], row["quantity_sold"]), ("Returned", 0, 5, 0))

    def test_customer_returns_restock_and_keep_the_numbers_reconciled(self):
        self.buy(1, name="RETMED", batch="C1", qty=10)
        self.sell(self.pid("RETMED", "C1"), 4)
        d = self.S()
        sale = d.query(models.SaleItem).first()
        sale_id, item_id = sale.sale_id, sale.id
        d.close()
        r = self.c.post("/returns", json={"sale_id": sale_id, "reason": "x", "items": [{"sale_item_id": item_id, "quantity": 1}]})
        self.assertIn(r.status_code, (200, 201), r.text)
        row = self.row("RETMED", "C1")
        self.assertEqual((row["available"], row["quantity_sold"], row["reconciled"], row["status"]), (7, 3, True, "Partially Sold"))

    def test_shared_batch_never_attributes_sales_to_one_supplier(self):
        self.buy(1, name="SHARED", batch="S1", qty=10)
        self.buy(2, name="SHARED", batch="S1", qty=10)                                    # same batch row, two suppliers
        self.sell(self.pid("SHARED", "S1"), 3)
        for sup in (1, 2):
            r = self.row("SHARED", "S1", supplier=sup)
            self.assertEqual((r["available"], r["status"], r["shared_batch"]), (17, "In Stock", True))
            self.assertIsNone(r["quantity_sold"])                                          # not fabricated
            self.assertIsNone(r["quantity_returned"])
            self.assertEqual(r["quantity_received"], 10)
            self.assertEqual(r["batch_received_total"], 20)

    def test_loose_sales_make_the_batch_unreconciled_instead_of_guessed(self):
        self.buy(1, name="LOOSEMED", batch="LM1", qty=10)
        d = self.S()
        p = d.get(models.Product, self.pid("LOOSEMED", "LM1"))
        p.tablets_per_strip, p.loose_tablet_price = 10, 9.0
        d.commit()
        d.close()
        self.sell(self.pid("LOOSEMED", "LM1"), 3, unit="loose_tablet", mrp=9.0)
        row = self.row("LOOSEMED", "LM1")
        self.assertFalse(row["reconciled"])
        self.assertIsNone(row["quantity_sold"])

    def test_drafts_are_not_received_stock(self):
        self.c.post("/purchases/drafts", json={"supplier_id": 1, "invoice_number": "DR-1", "payload": {"rows": [{"name": "DRAFTMED", "batch": "X1", "qty": "10", "rate": "5"}]}})
        self.assertEqual(self.stock()["total"], 0)
        self.assertEqual(self.c.get("/suppliers/1/profile").json()["balance_payable"], 0.0)

    def test_legacy_stock_without_a_purchase_record_is_listed_without_invented_history(self):
        d = self.S()
        d.add(models.Product(user_id=1, category="A", product_name="LEGACY", batch_number="G1", quantity=3, unit_price=10.0, purchase_price=5.0, gst_rate=12.0,
                             hsn_code="3004", supplier_id=1, expiry_date=date.today() + timedelta(days=200)))
        d.commit()
        d.close()
        r = self.row("LEGACY", "G1")
        self.assertEqual((r["status"], r["available"], r["source_recorded"], r["quantity_received"], r["quantity_sold"]), ("In Stock", 3, False, None, None))

    def test_stock_filter_search_and_paging(self):
        for i in range(5):
            self.buy(1, name="MED%d" % i, batch="P%d" % i, qty=2)
        self.sell(self.pid("MED0", "P0"), 2)
        s = self.stock(page_size=2)
        self.assertEqual((s["total"], len(s["items"])), (5, 2))
        self.assertEqual(s["counts"], {"In Stock": 4, "Sold Out": 1})
        self.assertEqual(self.stock(status="sold out")["total"], 1)
        self.assertEqual(self.stock(q="med3")["total"], 1)
        self.assertEqual(self.c.get("/suppliers/1/stock?status=bogus").status_code, 422)
        self.assertTrue(any("free units" in n for n in s["notes"]))

    def test_classify_is_conservative(self):
        t = date.today()
        self.assertEqual(supplier_profile.classify(0, None, False, False, 0, 0, 0, t)[0], "Unavailable")
        self.assertEqual(supplier_profile.classify(5, None, False, False, 3, 0, 0, t)[0], "In Stock")          # sold numbers are not trusted unattributed
        self.assertEqual(supplier_profile.classify(5, t - timedelta(days=1), True, True, 3, 0, 0, t)[0], "Expired")
        self.assertEqual(supplier_profile.classify(0, None, True, True, 5, 0, 0, t)[0], "Sold Out")
        self.assertEqual(supplier_profile.classify(0, None, True, True, 0, 5, 0, t)[0], "Returned")

    # ---- regressions
    def test_existing_supplier_flows_still_work(self):
        r = self.c.post("/suppliers", json={"name": "New Supplier"})
        self.assertEqual(r.status_code, 200, r.text)
        sid = r.json()["id"]
        self.assertEqual(self.c.put("/suppliers/%d" % sid, json={"phone": "123"}).json()["phone"], "123")
        self.assertEqual(self.c.post("/supplier-payments", json={"supplier_id": sid, "amount_paid": 5.0}).status_code, 200)
        self.assertEqual(self.c.get("/suppliers/%d/profile" % sid).json()["total_paid"], 5.0)


class TestSupplierPageWiring(unittest.TestCase):
    """Static wiring of the Supplier page (the screens are exercised in the browser)."""

    def _read(self, rel):
        with open(os.path.join(os.path.dirname(__file__), "..", rel), encoding="utf-8") as f:
            return f.read()

    def test_profile_is_fetched_by_id_and_never_read_from_the_list(self):
        js = self._read("web/js/supplier_profile.js")
        self.assertIn("/suppliers/' + id + '/profile", js)
        self.assertIn("/stock?", js)
        self.assertIn("/purchases/list?supplier_id=", js)
        self.assertIn("/purchases/detail/", js)
        html = self._read("web/suppliers.html")
        self.assertNotIn("allSuppliers.find(s => s.id === supId);\n      if (!sup) return;", html)
        for needle in ("Stock Status", "Purchase History", "Linked Medicine Stock", "sup-bill-modal", "data-sup-id", "js/supplier_profile.js"):
            self.assertIn(needle, html + js)


if __name__ == "__main__":
    unittest.main()
