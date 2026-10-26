"""
Purchase drafts: save / list / reopen / edit / delete / finalize.

Pinned rules: a draft is stored on the server and survives a new session; saving, editing, deleting or listing it never
changes stock, supplier balance, the purchase list, the dashboard or the ledger; the same draft keeps its identity across
saves (stale saves refused); an OCR draft points at the scanned bill and is not duplicated; deleting a draft never deletes
the bill; finalizing posts exactly once through the purchase engine and only then turns the draft FINALIZED; a failed
finalization leaves the draft open; other pharmacies see nothing.
"""
import json
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
from routes import document_archive_routes as dar

JPEG = b"\xFF\xD8\xFF\xE0" + b"\x00" * 64
FUT = (date.today() + timedelta(days=400)).isoformat()


def row(**kw):
    r = {"name": "NEWMED 500", "company": "Acme", "batch": "B1", "expiry": "12/30", "qty": "10", "free": "2", "rate": "50", "disc": "10",
         "gst": "12", "mrp": "90", "productId": None, "catalogId": None}
    r.update(kw)
    return r


class TestPurchaseDrafts(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False)
        db = self.S()
        for uid in (1, 2):
            db.add(models.User(id=uid, shop_name="S%d" % uid, owner_name="O", email="pd%d@test.invalid" % uid, password="x", default_gst_percentage=12.0))
        db.add(models.Supplier(id=1, user_id=1, name="Alpha Pharma"))
        db.add(models.Supplier(id=2, user_id=2, name="Other Shop Supplier"))
        db.commit()
        db.close()
        self.uid = 1
        self.files = []

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
    def save(self, rows=None, supplier_id=1, inv="INV-D1", **kw):
        body = {"supplier_id": supplier_id, "invoice_number": inv, "invoice_date": date.today().isoformat(),
                "payload": {"header": {"supplierName": "Alpha Pharma", "invoiceNo": inv}, "rows": rows if rows is not None else [row()]}}
        body.update(kw)
        return self.c.post("/purchases/drafts", json=body)

    def money_state(self):
        d = self.S()
        try:
            return (d.query(models.PurchaseInvoice).count(), d.query(models.PurchaseItem).count(), d.query(models.InventoryTransaction).count(),
                    d.query(models.Product).count(), sum(p.quantity for p in d.query(models.Product).all()))
        finally:
            d.close()

    def views(self):
        led = self.c.get("/suppliers/1/ledger").json()["balance_payable"]
        lst = self.c.get("/purchases/list").json()
        dash = self.c.get("/purchases/dashboard").json()
        return led, lst["total"], lst["summary"]["total_value"], lst["summary"]["outstanding_payables"], dash["pending_supplier_payables"], dash["month_purchases"]

    def post_manual(self, draft_id=None, inv="INV-D1", rows=None):
        item = {"product_name": "NEWMED 500", "batch_number": "B1", "expiry_date": FUT, "quantity": 10, "free_quantity": 2,
                "purchase_rate": 50, "discount_percent": 10, "gst_rate": 12, "mrp": 90}
        body = {"supplier_id": 1, "invoice_number": inv, "invoice_date": date.today().isoformat(), "items": rows or [item]}
        if draft_id:
            body["draft_id"] = draft_id
        return self.c.post("/purchases/manual", json=body)

    def upload_ocr_doc(self):
        r = self.c.post("/documents/upload", files={"file": ("bill.jpg", JPEG, "image/jpeg")})
        self.assertEqual(r.status_code, 201, r.text)
        doc = r.json()
        self.files.append(os.path.join(str(dar.DOCUMENTS_DIR), os.path.basename(doc["file_path"])))
        d = self.S()
        x = d.get(models.Document, doc["id"])
        x.ocr_raw_json = json.dumps({"supplier_name": "Alpha Pharma", "invoice_number": "OCR-9", "invoice_date": date.today().isoformat(), "total_amount": 560.0,
                                     "items": [{"product_name": "OCRMED 250", "hsn_code": "3004", "gst_rate": 12, "batch_number": "O1", "expiry_date": FUT,
                                                "quantity": 10, "purchase_price": 50.0, "mrp": 90.0, "total_price": 500.0}]})
        x.ocr_status = "Needs Review"
        x.supplier_id = 1
        x.invoice_number = "OCR-9"
        x.invoice_date = date.today()
        x.total_amount = 560.0
        d.commit()
        d.close()
        return doc["id"]

    # ---- saving
    def test_incomplete_draft_saves_and_empty_one_is_refused(self):
        r = self.save(rows=[], inv=None, supplier_id=1)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d["status"], d["line_count"], d["estimated_total"], d["supplier_name"]), ("DRAFT", 0, None, "Alpha Pharma"))
        self.assertEqual(d["reference"], "DRAFT-%05d" % d["id"])
        self.assertEqual(self.c.post("/purchases/drafts", json={"payload": {"rows": [{"name": "", "batch": ""}]}}).status_code, 400)

    def test_complete_but_unfinalized_draft_changes_nothing_that_is_posted(self):
        before, views = self.money_state(), self.views()
        d = self.save().json()
        self.assertEqual(d["line_count"], 1)
        self.assertEqual(d["estimated_total"], 504.0)                    # 10 x 50 less 10%, plus 12% GST (the free units cost nothing)
        self.save(rows=[row(), row(name="SECOND MED", batch="S1")], inv="INV-D2")
        self.assertEqual(self.money_state(), before)
        self.assertEqual(self.views()[:1] + self.views()[1:2], views[:1] + views[1:2])
        self.assertEqual(self.views(), views)                           # ledger, list, totals, payables, dashboard: all unchanged

    def test_draft_survives_a_new_session_and_restores_every_value(self):
        d = self.save(rows=[row(), row(name="SECOND MED", batch="S9", qty="3")]).json()
        fresh = TestClient(app_module.app, raise_server_exceptions=False)         # "after refresh / re-login"
        got = fresh.get("/purchases/drafts/%d" % d["id"]).json()
        self.assertEqual(got["payload"]["rows"][1]["batch"], "S9")
        self.assertEqual((got["payload"]["rows"][0]["free"], got["payload"]["rows"][0]["disc"]), ("2", "10"))
        self.assertEqual((got["supplier_id"], got["invoice_number"], got["version"]), (1, "INV-D1", 1))

    # ---- listing and count
    def test_drafts_are_listed_counted_and_searchable(self):
        a = self.save(inv="INV-A").json()
        self.save(inv="INV-B", supplier_id=None, rows=[row()])
        lst = self.c.get("/purchases/drafts").json()
        self.assertEqual((lst["total"], lst["draft_count"]), (2, 2))
        by = {i["invoice_number"]: i for i in lst["items"]}
        self.assertIsNone(by["INV-B"]["supplier_name"])
        self.assertEqual(self.c.get("/purchases/drafts?q=alpha").json()["total"], 1)
        self.assertEqual(self.c.get("/purchases/drafts?q=inv-b").json()["total"], 1)
        self.assertEqual(self.c.get("/purchases/drafts?q=DRAFT-%05d" % a["id"]).json()["items"][0]["invoice_number"], "INV-A")
        self.assertEqual(self.c.get("/purchases/drafts?date_from=%s" % (date.today() + timedelta(days=2))).json()["total"], 0)
        self.assertEqual(self.c.get("/purchases/drafts?page=1&page_size=1").json()["items"].__len__(), 1)
        self.assertEqual(self.c.get("/purchases/list").json()["summary"]["draft_count"], 2)

    # ---- editing the same draft
    def test_saving_again_keeps_the_identity_and_bumps_the_version(self):
        d = self.save().json()
        again = self.c.post("/purchases/drafts", json={"draft_id": d["id"], "expected_version": 1, "supplier_id": 1, "invoice_number": "INV-D1",
                                                      "payload": {"rows": [row(), row(name="ADDED", batch="A1")]}}).json()
        self.assertEqual((again["id"], again["version"], again["line_count"]), (d["id"], 2, 2))
        self.assertEqual(self.c.get("/purchases/drafts").json()["total"], 1)             # no duplicate draft
        stale = self.c.post("/purchases/drafts", json={"draft_id": d["id"], "expected_version": 1, "supplier_id": 1, "payload": {"rows": [row()]}})
        self.assertEqual(stale.status_code, 409)
        self.assertIn("DRAFT_CHANGED", stale.text)
        self.assertEqual(self.c.get("/purchases/drafts/%d" % d["id"]).json()["line_count"], 2)   # the stale save changed nothing

    def test_a_failed_save_keeps_the_earlier_saved_draft(self):
        d = self.save().json()
        bad = self.c.post("/purchases/drafts", json={"draft_id": d["id"], "supplier_id": 2, "payload": {"rows": [row()]}})
        self.assertEqual(bad.status_code, 404)                                              # another shop's supplier
        got = self.c.get("/purchases/drafts/%d" % d["id"]).json()
        self.assertEqual((got["supplier_id"], got["version"]), (1, 1))

    # ---- delete
    def test_delete_draft_removes_only_the_draft(self):
        d = self.save().json()
        before = self.money_state()
        self.assertEqual(self.c.delete("/purchases/drafts/%d" % d["id"]).status_code, 200)
        self.assertEqual(self.c.get("/purchases/drafts/%d" % d["id"]).status_code, 404)
        self.assertEqual(self.c.get("/purchases/drafts").json()["draft_count"], 0)
        self.assertEqual(self.money_state(), before)

    # ---- OCR drafts
    def test_ocr_draft_keeps_the_link_is_not_duplicated_and_does_not_verify(self):
        doc_id = self.upload_ocr_doc()
        before, views = self.money_state(), self.views()
        r = self.c.post("/documents/%d/save-draft" % doc_id)
        self.assertEqual(r.status_code, 200, r.text)
        draft = r.json()["draft"]
        self.assertEqual((draft["source"], draft["document_id"], draft["status"], draft["line_count"]), ("OCR", doc_id, "DRAFT", 1))
        self.assertEqual(draft["estimated_total"], 560.0)
        again = self.c.post("/documents/%d/save-draft" % doc_id, json={"header": {"supplier_id": 1, "invoice_number": "OCR-9B", "invoice_date": date.today().isoformat()},
                                                                       "items": [{"product_name": "OCRMED 250", "batch_number": "O1", "expiry_date": FUT, "quantity": 20,
                                                                                  "purchase_price": 50.0, "mrp": 90.0, "gst_rate": 12, "hsn_code": "3004"}]})
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual((again.json()["draft"]["id"], again.json()["draft"]["version"]), (draft["id"], 2))
        self.assertEqual(self.c.get("/purchases/drafts").json()["total"], 1)                  # still one draft for this bill
        review = self.c.get("/documents/%d/review" % doc_id).json()
        self.assertEqual((review["status"], review["draft"]["id"], review["invoice_number"], review["lines"][0]["quantity"]), ("Needs Review", draft["id"], "OCR-9B", 20.0))
        self.assertEqual(self.c.get("/documents/%d/file" % doc_id).content, JPEG)             # the original is untouched
        self.assertEqual(self.money_state(), before)
        self.assertEqual(self.views(), views)

    def test_delete_ocr_draft_and_delete_bill_never_break_each_other(self):
        doc_id = self.upload_ocr_doc()
        draft = self.c.post("/documents/%d/save-draft" % doc_id).json()["draft"]
        self.assertEqual(self.c.delete("/purchases/drafts/%d" % draft["id"]).status_code, 200)
        self.assertEqual(self.c.get("/documents/%d" % doc_id).status_code, 200)               # the bill and its file stay
        self.assertEqual(self.c.get("/documents/%d/file" % doc_id).status_code, 200)
        self.c.post("/documents/%d/save-draft" % doc_id)
        self.assertEqual(self.c.delete("/documents/%d" % doc_id).status_code, 200)            # deleting the bill takes its draft along
        self.assertEqual(self.c.get("/purchases/drafts").json()["total"], 0)

    def test_ocr_draft_can_be_saved_when_ocr_failed_but_not_after_verification(self):
        r = self.c.post("/documents/upload", files={"file": ("bill.jpg", JPEG, "image/jpeg")})
        doc = r.json()
        self.files.append(os.path.join(str(dar.DOCUMENTS_DIR), os.path.basename(doc["file_path"])))
        self.assertEqual(self.c.post("/documents/%d/save-draft" % doc["id"], json={"header": {"supplier_id": 1, "invoice_number": "HAND-1"}, "items": []}).status_code, 200)
        d = self.S()
        d.get(models.Document, doc["id"]).ocr_status = "Verified"
        d.commit()
        d.close()
        self.assertEqual(self.c.post("/documents/%d/save-draft" % doc["id"]).status_code, 409)

    # ---- finalizing
    def test_manual_draft_finalizes_exactly_once(self):
        d = self.save().json()
        r = self.post_manual(draft_id=d["id"])
        self.assertEqual(r.status_code, 201, r.text)
        got = self.c.get("/purchases/drafts/%d" % d["id"]).json()
        self.assertEqual((got["status"], got["purchase_invoice_id"], got["purchase_voucher_no"]), ("FINALIZED", r.json()["id"], r.json()["voucher_no"]))
        stock = self.money_state()
        again = self.post_manual(draft_id=d["id"], inv="INV-OTHER")                    # a retry / second tab, even with another invoice no.
        self.assertEqual(again.status_code, 409)
        self.assertIn("DRAFT_FINALIZED", again.text)
        self.assertEqual(self.post_manual(draft_id=d["id"]).status_code, 409)           # same invoice no.: the duplicate guard too
        self.assertEqual(self.money_state(), stock)
        self.assertEqual(self.c.get("/purchases/drafts").json()["draft_count"], 0)
        self.assertEqual(self.c.get("/purchases/drafts?status=FINALIZED").json()["total"], 1)
        edit = self.c.post("/purchases/drafts", json={"draft_id": d["id"], "supplier_id": 1, "payload": {"rows": [row()]}})
        self.assertEqual(edit.status_code, 409)
        self.assertEqual(self.c.delete("/purchases/drafts/%d" % d["id"]).status_code, 409)   # kept as history
        led = self.c.get("/suppliers/1/ledger").json()["balance_payable"]
        self.assertEqual(led, r.json()["total_amount"])                               # only now does the supplier owe anything

    def test_failed_finalization_keeps_the_draft_open_for_retry(self):
        d = self.save().json()
        expired = {"product_name": "NEWMED 500", "batch_number": "B1", "expiry_date": (date.today() - timedelta(days=5)).isoformat(), "quantity": 1,
                   "purchase_rate": 10, "gst_rate": 12, "mrp": 20}
        before = self.money_state()
        self.assertEqual(self.post_manual(draft_id=d["id"], rows=[expired]).status_code, 400)
        self.assertEqual(self.money_state(), before)
        self.assertEqual(self.c.get("/purchases/drafts/%d" % d["id"]).json()["status"], "DRAFT")
        self.assertEqual(self.post_manual(draft_id=d["id"]).status_code, 201)

    def test_ocr_draft_is_finalized_by_the_confirm(self):
        doc_id = self.upload_ocr_doc()
        draft = self.c.post("/documents/%d/save-draft" % doc_id).json()["draft"]
        r = self.c.post("/documents/%d/confirm-review" % doc_id, json={"acknowledge_warnings": True})
        self.assertEqual(r.status_code, 200, r.text)
        got = self.c.get("/purchases/drafts/%d" % draft["id"]).json()
        self.assertEqual((got["status"], got["purchase_invoice_id"]), ("FINALIZED", r.json()["id"]))
        self.assertEqual(self.c.post("/documents/%d/save-draft" % doc_id).status_code, 409)
        stock = self.money_state()
        self.assertEqual(self.c.post("/documents/%d/confirm-review" % doc_id, json={"acknowledge_warnings": True}).status_code, 409)
        self.assertEqual(self.money_state(), stock)

    # ---- access control
    def test_other_pharmacies_and_anonymous_users_see_nothing(self):
        d = self.save().json()
        doc_id = self.upload_ocr_doc()
        self.uid = 2
        self.assertEqual(self.c.get("/purchases/drafts/%d" % d["id"]).status_code, 404)
        self.assertEqual(self.c.delete("/purchases/drafts/%d" % d["id"]).status_code, 404)
        self.assertEqual(self.c.get("/purchases/drafts").json()["total"], 0)
        self.assertEqual(self.c.post("/purchases/drafts", json={"draft_id": d["id"], "payload": {"rows": [row()]}}).status_code, 404)
        self.assertEqual(self.c.post("/documents/%d/save-draft" % doc_id).status_code, 404)
        app_module.app.dependency_overrides.pop(dependencies.get_current_user, None)
        anon = TestClient(app_module.app, raise_server_exceptions=False)
        for fn in (lambda: anon.get("/purchases/drafts"), lambda: anon.post("/purchases/drafts", json={"payload": {}}), lambda: anon.get("/purchases/drafts/1")):
            self.assertIn(fn().status_code, (401, 403))

    def test_other_pharmacy_cannot_finalize_my_draft(self):
        d = self.save().json()
        self.uid = 2
        r = self.c.post("/purchases/manual", json={"supplier_id": 2, "invoice_number": "X", "invoice_date": date.today().isoformat(), "draft_id": d["id"],
                                                   "items": [{"product_name": "MM", "batch_number": "B", "expiry_date": FUT, "quantity": 1, "purchase_rate": 1, "gst_rate": 12, "mrp": 2}]})
        self.assertEqual(r.status_code, 404)
        self.uid = 1
        self.assertEqual(self.c.get("/purchases/drafts/%d" % d["id"]).json()["status"], "DRAFT")


class TestPurchaseDraftPages(unittest.TestCase):
    """Static wiring of the pages (the screens themselves are exercised in the browser)."""

    def _read(self, rel):
        with open(os.path.join(os.path.dirname(__file__), "..", rel), encoding="utf-8") as f:
            return f.read()

    def test_every_applicable_editor_has_a_visible_save_as_draft(self):
        entry = self._read("web/purchase_entry.html")
        self.assertGreaterEqual(entry.count("Save as Draft"), 2)                         # header bar and bottom bar
        self.assertLess(entry.index("Save as Draft"), entry.index('id="pe-errors"'))      # visible without scrolling
        docs = self._read("web/documents.html")
        self.assertIn("Save as Draft", docs)
        self.assertIn("drSaveDraft()", docs)

    def test_landing_has_all_purchases_and_drafts_tabs_and_four_actions(self):
        html = self._read("web/purchases.html")
        for needle in ("All Purchases", "Drafts", "pm-tab-drafts", "Scan / Upload Bill", "Search Medicine", "Direct Excel / CSV Import", "Add Manually"):
            self.assertIn(needle, html)
        js = self._read("web/js/purchases_page.js")
        self.assertIn("/purchases/drafts", js)
        self.assertIn("purchase_entry.html?draft=", js)

    def test_entry_page_saves_drafts_on_the_server_not_in_the_browser(self):
        js = self._read("web/js/purchase_entry.js")
        self.assertIn("/purchases/drafts", js)
        self.assertIn("draft_id", self._read("web/js/purchase_entry_core.js"))


if __name__ == "__main__":
    unittest.main()
