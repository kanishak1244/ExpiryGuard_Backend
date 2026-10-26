"""
Documents & OCR review workspace: original file retrieval, read-only review, corrections, confirm through the purchase engine.

Pinned rules: the original upload is served only to its pharmacy and survives OCR failure / a wiped server disk (durable copy);
the review view and saving corrections never post stock; Confirm & Add to Stock goes through the purchase engine in one
transaction, flips the document to Verified only with the stock, and cannot post twice; a Verified document cannot be edited
or re-OCR'd; corrections are not silently overwritten by a re-run.
"""
import json
import os
import sys
import unittest
from datetime import date, timedelta
from unittest import mock

os.environ.setdefault("ENABLE_SCHEDULER", "0")
os.environ["AI_USAGE_LOG_ENABLED"] = "0"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app as app_module
import dependencies
import document_storage
import models
from routes import document_archive_routes as dar

JPEG = b"\xFF\xD8\xFF\xE0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n%fake\n" + b"0" * 64
FUT = (date.today() + timedelta(days=400)).isoformat()


def ocr_item(n=0, **kw):
    it = {"product_name": "MEDICINE %d TAB" % n, "hsn_code": "3004", "gst_rate": 12.0, "batch_number": "B%04d" % n,
          "expiry_date": FUT, "quantity": 10, "free_qty": 0, "purchase_price": 100.0, "mrp": 150.0, "discount_percent": 0,
          "total_price": 1000.0, "field_flags": {}}
    it.update(kw)
    return it


class TestDocumentReview(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False)
        db = self.S()
        for uid in (1, 2):
            db.add(models.User(id=uid, shop_name="S%d" % uid, owner_name="O", email="dr%d@test.invalid" % uid, password="x",
                               default_gst_percentage=12.0))
        db.add(models.Supplier(id=1, user_id=1, name="Alpha Pharma"))
        db.add(models.Supplier(id=2, user_id=2, name="Other Shop Supplier"))
        db.commit()
        db.close()
        self.uid = 1
        self.created_files = []

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
        for f in self.created_files:
            try:
                os.remove(f)
            except OSError:
                pass
        document_storage._transport = None
        for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "DOCUMENT_STORAGE_BUCKET"):
            os.environ.pop(k, None)

    # ---- helpers
    def upload(self, data=JPEG, name="bill.jpg", ctype="image/jpeg"):
        r = self.c.post("/documents/upload", files={"file": (name, data, ctype)})
        self.assertEqual(r.status_code, 201, r.text)
        doc = r.json()
        self.created_files.append(os.path.join(str(dar.DOCUMENTS_DIR), os.path.basename(doc["file_path"])))
        return doc

    def set_ocr(self, doc_id, items=None, supplier_id=1, invoice_no="INV-100", date_s=None, status="Needs Review", **extra):
        d = self.S()
        doc = d.get(models.Document, doc_id)
        data = {"supplier_name": "Alpha Pharma", "invoice_number": invoice_no, "invoice_date": date_s or date.today().isoformat(),
                "total_amount": 1120.0, "items": items if items is not None else [ocr_item(0)]}
        data.update(extra)
        doc.ocr_raw_json = json.dumps(data)
        doc.ocr_status = status
        doc.supplier_id = supplier_id
        doc.invoice_number = invoice_no
        doc.invoice_date = date.fromisoformat(data["invoice_date"])
        doc.total_amount = data["total_amount"]
        d.commit()
        d.close()

    def counts(self):
        d = self.S()
        try:
            return (d.query(models.PurchaseInvoice).count(), d.query(models.InventoryTransaction).count(),
                    sum(p.quantity for p in d.query(models.Product).all()), d.query(models.Product).count())
        finally:
            d.close()

    def status(self, doc_id):
        d = self.S()
        try:
            return d.get(models.Document, doc_id).ocr_status
        finally:
            d.close()

    # ---- original file
    def test_original_image_and_pdf_are_served_exactly_and_privately(self):
        for data, name, ctype, media in ((JPEG, "a.jpg", "image/jpeg", "image/jpeg"), (PNG, "b.png", "image/png", "image/png"),
                                         (PDF, "c.pdf", "application/pdf", "application/pdf")):
            doc = self.upload(data, name, ctype)
            r = self.c.get("/documents/%d/file" % doc["id"])
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.content, data)
            self.assertTrue(r.headers["content-type"].startswith(media))
            self.assertIn("no-store", r.headers["cache-control"])
            self.assertEqual(r.headers["x-content-type-options"], "nosniff")
            again = TestClient(app_module.app, raise_server_exceptions=False).get("/documents/%d/file" % doc["id"])   # "after refresh / other device"
            self.assertEqual(again.content, data)

    def test_other_pharmacy_and_anonymous_cannot_read_the_original(self):
        doc = self.upload()
        self.uid = 2
        for path in ("file", "review"):
            self.assertEqual(self.c.get("/documents/%d/%s" % (doc["id"], path)).status_code, 404)
        self.assertEqual(self.c.put("/documents/%d/review-data" % doc["id"], json={"header": {}, "items": []}).status_code, 404)
        self.assertEqual(self.c.post("/documents/%d/confirm-review" % doc["id"]).status_code, 404)
        app_module.app.dependency_overrides.pop(dependencies.get_current_user, None)
        anon = TestClient(app_module.app, raise_server_exceptions=False)
        self.assertIn(anon.get("/documents/%d/file" % doc["id"]).status_code, (401, 403))

    def _fake_remote(self):
        store = {}

        def handler(request: httpx.Request):
            path = request.url.path
            if request.method == "POST":
                if store.get("__fail__"):
                    return httpx.Response(500, text="boom")
                store[path] = request.content
                return httpx.Response(200, json={})
            if request.method == "GET":
                return httpx.Response(200, content=store[path]) if path in store else httpx.Response(404, json={})
            return httpx.Response(200, json={})

        document_storage._transport = httpx.MockTransport(handler)
        os.environ["SUPABASE_URL"] = "https://example.invalid"
        os.environ["SUPABASE_SERVICE_KEY"] = "test-key"
        return store

    def test_original_survives_a_wiped_server_disk_when_durable_storage_is_configured(self):
        store = self._fake_remote()
        doc = self.upload()
        self.assertTrue(any(k.endswith(os.path.basename(doc["file_path"])) for k in store))
        os.remove(self.created_files[-1])                                  # the host disk was reset by a redeploy
        r = self.c.get("/documents/%d/file" % doc["id"])
        self.assertEqual((r.status_code, r.content), (200, JPEG))
        self.assertTrue(os.path.exists(self.created_files[-1]))            # restored for OCR too

    def test_without_durable_storage_a_lost_file_is_reported_not_faked(self):
        doc = self.upload()
        os.remove(self.created_files[-1])
        r = self.c.get("/documents/%d/file" % doc["id"])
        self.assertEqual(r.status_code, 404)
        self.assertIn("durable storage is not configured", r.text)

    def test_failed_durable_upload_saves_nothing(self):
        store = self._fake_remote()
        store["__fail__"] = True
        r = self.c.post("/documents/upload", files={"file": ("bill.jpg", JPEG, "image/jpeg")})
        self.assertEqual(r.status_code, 503)
        d = self.S()
        self.assertEqual(d.query(models.Document).count(), 0)
        d.close()

    def test_upload_validation(self):
        self.assertEqual(self.c.post("/documents/upload", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code, 400)
        self.assertEqual(self.c.post("/documents/upload", files={"file": ("x.jpg", b"notajpeg", "image/jpeg")}).status_code, 400)

    # ---- OCR failure
    def test_ocr_failure_keeps_the_original_and_a_failed_rerun_keeps_the_old_reading(self):
        doc = self.upload()
        with mock.patch.object(dar, "scan_invoice", return_value={"success": False, "error": "unreadable"}):
            r = self.c.post("/documents/%d/ocr" % doc["id"])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["ocr_status"], "Failed")
        self.assertEqual(self.c.get("/documents/%d/file" % doc["id"]).content, JPEG)
        v = self.c.get("/documents/%d/review" % doc["id"]).json()
        self.assertTrue(v["failed"])
        self.assertFalse(v["can_confirm"])
        self.set_ocr(doc["id"])                                          # a good reading exists now
        with mock.patch.object(dar, "scan_invoice", return_value={"success": False, "error": "unreadable"}):
            r = self.c.post("/documents/%d/ocr" % doc["id"])
        self.assertEqual(r.status_code, 502)
        self.assertEqual(self.c.get("/documents/%d/review" % doc["id"]).json()["line_count"], 1)

    # ---- review is read-only
    def test_review_shows_header_supplier_lines_and_changes_nothing(self):
        doc = self.upload()
        self.set_ocr(doc["id"], items=[ocr_item(0), ocr_item(1, batch_number="", mrp=None, expiry_date="")])
        before = (self.counts(), self.status(doc["id"]))
        v = self.c.get("/documents/%d/review" % doc["id"]).json()
        self.assertEqual(v["supplier_status"], "linked")
        self.assertEqual(v["supplier"]["name"], "Alpha Pharma")
        self.assertEqual(v["line_count"], 2)
        self.assertEqual(v["lines"][0]["match"]["status"], "new")
        fields = {b["field"] for b in v["lines"][1]["blocking"]}
        self.assertTrue({"batch_number", "expiry_date", "mrp"} <= fields)           # missing critical fields are flagged, not invented
        self.assertFalse(v["can_confirm"])
        self.assertEqual((self.counts(), self.status(doc["id"])), before)

    def test_unlinked_supplier_blocks_confirm_with_a_clear_reason(self):
        doc = self.upload()
        self.set_ocr(doc["id"], supplier_id=None)
        v = self.c.get("/documents/%d/review" % doc["id"]).json()
        self.assertEqual(v["supplier_status"], "needs_matching")
        self.assertTrue(any(b["field"] == "supplier" for b in v["blocking"]))
        r = self.c.post("/documents/%d/confirm-review" % doc["id"])
        self.assertEqual(r.status_code, 422)
        self.assertIn("REVIEW_INCOMPLETE", r.text)

    # ---- corrections
    def test_corrections_persist_keep_the_ocr_reading_and_post_nothing(self):
        doc = self.upload()
        self.set_ocr(doc["id"], items=[ocr_item(0, batch_number="", mrp=None)], supplier_id=None)
        before = self.counts()
        body = {"header": {"supplier_id": 1, "invoice_number": "INV-FIXED", "invoice_date": date.today().isoformat(), "total_amount": 1120.0},
                "items": [ocr_item(0, batch_number="FIX1", mrp=150.0)]}
        r = self.c.put("/documents/%d/review-data" % doc["id"], json=body)
        self.assertEqual(r.status_code, 200, r.text)
        v = r.json()
        self.assertTrue(v["corrected"])
        self.assertTrue(v["can_confirm"], v["blocking"])
        again = self.c.get("/documents/%d/review" % doc["id"]).json()
        self.assertEqual((again["invoice_number"], again["lines"][0]["batch_number"], again["supplier"]["name"]), ("INV-FIXED", "FIX1", "Alpha Pharma"))
        d = self.S()
        raw = json.loads(d.get(models.Document, doc["id"]).ocr_raw_json)
        d.close()
        self.assertEqual(raw["items"][0]["batch_number"], "")                 # original OCR reading untouched
        self.assertEqual(raw["corrected"]["items"][0]["batch_number"], "FIX1")
        self.assertEqual(self.counts(), before)

    def test_corrections_validate_supplier_and_date(self):
        doc = self.upload()
        self.set_ocr(doc["id"])
        self.assertEqual(self.c.put("/documents/%d/review-data" % doc["id"], json={"header": {"supplier_id": 2}, "items": []}).status_code, 404)
        self.assertEqual(self.c.put("/documents/%d/review-data" % doc["id"], json={"header": {"invoice_date": "31/12/2026"}, "items": []}).status_code, 400)

    def test_rerun_ocr_does_not_overwrite_corrections_without_force(self):
        doc = self.upload()
        self.set_ocr(doc["id"])
        self.c.put("/documents/%d/review-data" % doc["id"], json={"header": {"supplier_id": 1, "invoice_number": "X1"}, "items": [ocr_item(0)]})
        r = self.c.post("/documents/%d/ocr" % doc["id"])
        self.assertEqual(r.status_code, 409)
        self.assertIn("HAS_CORRECTIONS", r.text)
        new = {"success": True, "data": {"invoice_number": "NEW", "items": [ocr_item(5)], "supplier_name": "Alpha Pharma"}}
        with mock.patch.object(dar, "scan_invoice", return_value=new):
            self.assertEqual(self.c.post("/documents/%d/ocr?force=true" % doc["id"]).status_code, 200)
        d = self.S()
        raw = json.loads(d.get(models.Document, doc["id"]).ocr_raw_json)
        d.close()
        self.assertNotIn("corrected", raw)
        self.assertEqual(raw["previous_corrections"]["invoice_number"], "X1")

    # ---- confirm
    def test_confirm_posts_purchase_stock_ledger_and_verifies_once(self):
        doc = self.upload()
        self.set_ocr(doc["id"], items=[ocr_item(0), ocr_item(1, quantity=5, free_qty=1, discount_percent=10)])
        r = self.c.post("/documents/%d/confirm-review" % doc["id"], json={"acknowledge_warnings": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.status(doc["id"]), "Verified")
        self.assertEqual(self.counts()[0], 1)
        d = self.S()
        qty = {p.product_name: p.quantity for p in d.query(models.Product).all()}
        pdoc = {p.document_id for p in d.query(models.Product).all()}
        d.close()
        self.assertEqual(qty, {"MEDICINE 0 TAB": 10, "MEDICINE 1 TAB": 6})
        self.assertEqual(pdoc, {doc["id"]})
        led = self.c.get("/suppliers/1/ledger").json()
        self.assertEqual(led["balance_payable"], r.json()["total_amount"])
        self.assertEqual(self.c.get("/purchases/list").json()["total"], 1)
        after = self.counts()
        again = self.c.post("/documents/%d/confirm-review" % doc["id"], json={"acknowledge_warnings": True})
        self.assertEqual(again.status_code, 409)
        self.assertIn("ALREADY_VERIFIED", again.text)
        self.assertEqual(self.counts(), after)                                 # no second posting

    def test_failed_confirm_leaves_the_document_for_retry(self):
        doc = self.upload()
        self.set_ocr(doc["id"])
        self.c.post("/purchases/manual", json={"supplier_id": 1, "invoice_number": "INV-100", "invoice_date": date.today().isoformat(),
                                               "items": [{"product_name": "OTHER", "batch_number": "O1", "expiry_date": FUT, "quantity": 1,
                                                          "purchase_rate": 10, "gst_rate": 12, "mrp": 20}]})
        before = self.counts()
        v = self.c.get("/documents/%d/review" % doc["id"]).json()
        self.assertFalse(v["can_confirm"])                                       # duplicate supplier invoice is a blocking problem
        r = self.c.post("/documents/%d/confirm-review" % doc["id"])
        self.assertEqual(r.status_code, 422)
        self.assertEqual((self.counts(), self.status(doc["id"])), (before, "Needs Review"))
        self.c.put("/documents/%d/review-data" % doc["id"], json={"header": {"supplier_id": 1, "invoice_number": "INV-200",
                                                                              "invoice_date": date.today().isoformat()}, "items": [ocr_item(0)]})
        self.assertEqual(self.c.post("/documents/%d/confirm-review" % doc["id"], json={"acknowledge_warnings": True}).status_code, 200)

    def test_total_difference_and_below_cost_need_acknowledgement(self):
        doc = self.upload()
        self.set_ocr(doc["id"], total_amount=5000.0)
        r = self.c.post("/documents/%d/confirm-review" % doc["id"])
        self.assertEqual(r.status_code, 409)
        self.assertIn("NEEDS_ACKNOWLEDGEMENT", r.text)
        self.assertEqual(self.counts()[0], 0)
        self.assertEqual(self.c.post("/documents/%d/confirm-review" % doc["id"], json={"acknowledge_warnings": True}).status_code, 200)

    def test_verified_document_cannot_be_edited_or_rerun(self):
        doc = self.upload()
        self.set_ocr(doc["id"])
        self.assertEqual(self.c.post("/documents/%d/confirm-review" % doc["id"], json={"acknowledge_warnings": True}).status_code, 200)
        r = self.c.put("/documents/%d/review-data" % doc["id"], json={"header": {"invoice_number": "HACK"}, "items": []})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.c.post("/documents/%d/ocr" % doc["id"]).status_code, 409)
        v = self.c.get("/documents/%d/review" % doc["id"]).json()
        self.assertEqual((v["verified"], v["can_edit"], v["can_confirm"]), (True, False, False))
        self.assertEqual(self.c.get("/documents/%d/file" % doc["id"]).status_code, 200)   # the original stays available

    def test_legacy_confirm_cannot_double_post(self):
        doc = self.upload()
        good = {"items": [{"product_name": "LEGACY MED", "batch_number": "L1", "quantity": 3, "purchase_price": 10.0, "mrp": 20.0,
                           "hsn_code": "3004", "expiry_date": FUT}]}
        self.assertEqual(self.c.post("/documents/%d/confirm" % doc["id"], json=good).status_code, 200)
        before = self.counts()
        self.assertEqual(self.c.post("/documents/%d/confirm" % doc["id"], json=good).status_code, 409)
        self.assertEqual(self.counts(), before)

    def test_hsn_and_gst_fill_each_other_and_one_of_them_is_required(self):
        doc = self.upload()
        self.set_ocr(doc["id"], items=[ocr_item(0, hsn_code="", gst_rate=12.0), ocr_item(1, hsn_code="3004", gst_rate=None),
                                       ocr_item(2, hsn_code="", gst_rate=None)])
        v = self.c.get("/documents/%d/review" % doc["id"]).json()
        a, b, c = v["lines"]
        self.assertEqual((a["hsn_code"], a["gst_rate"]), ("3004", 12.0))
        self.assertIn("filled in", a["tax_filled"])
        self.assertEqual((b["hsn_code"], b["gst_rate"]), ("3004", 12.0))
        self.assertTrue(any(x["field"] == "gst_rate" for x in c["blocking"]))
        self.assertFalse(v["can_confirm"])
        self.set_ocr(doc["id"], items=[ocr_item(0, hsn_code="", gst_rate=12.0), ocr_item(1, hsn_code="3004", gst_rate=None)])
        r = self.c.post("/documents/%d/confirm-review" % doc["id"], json={"acknowledge_warnings": True})
        self.assertEqual(r.status_code, 200, r.text)
        d = self.S()
        prods = {p.product_name: (p.hsn_code, p.gst_rate) for p in d.query(models.Product).all()}
        d.close()
        self.assertEqual(set(prods.values()), {("3004", 12.0)})



class TestDocumentReviewPage(unittest.TestCase):
    """Static wiring of the Documents page (the screen itself is exercised in the browser)."""

    def _read(self, rel):
        with open(os.path.join(os.path.dirname(__file__), "..", rel), encoding="utf-8") as f:
            return f.read()

    def test_workspace_has_original_left_summary_table_and_the_three_actions(self):
        html = self._read("web/documents.html")
        order = [html.index(x) for x in ('aria-label="Original supplier bill"', 'aria-label="Extracted invoice data"')]
        self.assertEqual(order, sorted(order))
        for needle in ('id="dr-preview"', 'id="dr-lines"', "Edit Bill Details", "← Back", "Confirm &amp; Add to Stock", "drConfirm()", "drEdit()",
                       "js/doc_review.js"):
            self.assertIn(needle, html)
        ws = html[html.index('id="dr-workspace"'):html.index("<!-- SPLIT-VIEW REVIEW")]
        self.assertNotIn("<input", ws)                                   # the review itself has no editable fields

    def test_editor_saves_corrections_only_and_asks_before_discarding(self):
        html = self._read("web/documents.html")
        self.assertIn("saveCorrections()", html)
        self.assertNotIn("submitDocumentConfirmation", html)             # the editor can no longer post stock
        self.assertIn("/review-data", html)
        self.assertIn("unsaved changes", html)

    def test_original_is_loaded_with_the_login_not_a_public_url(self):
        js = self._read("web/js/doc_review.js")
        self.assertIn("/documents/' + id + '/file'", js)
        self.assertIn("getHeaders", js)
        self.assertIn("createObjectURL", js)


if __name__ == "__main__":
    unittest.main()
