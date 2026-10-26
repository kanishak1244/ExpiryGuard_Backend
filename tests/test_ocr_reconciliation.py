"""
Scanned-invoice reconciliation: the printed total, the GST rate of every line and the verdict (synthetic bills only).

Pinned rules: an unread printed total is unknown (None / "not read"), never ₹0.00 and never replaced by the calculated total;
every line's GST rate comes from a named source (bill line, this shop's stock, a dated HSN table) or the line is blocked;
no silent 0 % or default rate; HSN-derived and uncertain rates need the user's acknowledgement; saving corrections never posts
stock; a bill is confirmed exactly once and a refused confirmation keeps the corrected draft.
"""
import json
import unittest
from datetime import date

import gst_resolver
import models
from tests import test_document_review as _doc

ocr_item = _doc.ocr_item
_Base = _doc.TestDocumentReview

NEW = date.today().isoformat()          # after the 22 Sep 2025 slab change: 5 / 18 %
OLD = "2025-06-01"                      # before it: 12 % still existed


class TestOcrReconciliation(unittest.TestCase):
    setUp, tearDown = _Base.setUp, _Base.tearDown
    upload, set_ocr, counts, status = _Base.upload, _Base.set_ocr, _Base.counts, _Base.status

    def view(self, doc_id):
        return self.c.get("/documents/%d/review" % doc_id).json()

    def confirm(self, doc_id, **body):
        return self.c.post("/documents/%d/confirm-review" % doc_id, json=body or None)

    # ---- printed total
    def test_missing_printed_total_is_not_zero_and_blocks_confirmation(self):
        for missing in (None, 0, 0.0):
            doc = self.upload()
            self.set_ocr(doc["id"], items=[ocr_item(0, gst_rate=5.0)], total_amount=missing)
            v = self.view(doc["id"])
            self.assertIsNone(v["printed_total"])
            self.assertEqual(v["reconciliation"]["state"], "MISSING_PRINTED_TOTAL")
            self.assertIsNone(v["reconciliation"]["difference"])        # no "difference = calculated total"
            self.assertFalse(v["can_confirm"])
            r = self.confirm(doc["id"], acknowledge_warnings=True)
            self.assertEqual(r.status_code, 422)
            self.assertEqual((self.counts()[0], self.status(doc["id"])), (0, "Needs Review"))

    def test_entering_the_printed_total_unblocks_and_matches(self):
        doc = self.upload()
        self.set_ocr(doc["id"], items=[ocr_item(0, gst_rate=5.0)], total_amount=None)
        self.c.put("/documents/%d/review-data" % doc["id"], json={"header": {"supplier_id": 1, "invoice_number": "INV-100", "invoice_date": NEW, "total_amount": 1050.0}, "items": [ocr_item(0, gst_rate=5.0)]})
        v = self.view(doc["id"])
        self.assertEqual((v["printed_total"], v["reconciliation"]["state"], v["can_confirm"]), (1050.0, "MATCHED", True))

    def test_matched_and_mismatch_states_report_printed_calculated_and_difference(self):
        doc = self.upload()
        self.set_ocr(doc["id"], items=[ocr_item(0, gst_rate=5.0)], total_amount=1050.0)
        r = self.view(doc["id"])["reconciliation"]
        self.assertEqual((r["state"], r["printed_total"], r["calculated_total"]), ("MATCHED", 1050.0, 1050.0))
        self.set_ocr(doc["id"], items=[ocr_item(0, gst_rate=5.0)], total_amount=1200.0)
        v = self.view(doc["id"])
        r = v["reconciliation"]
        self.assertEqual((r["state"], r["printed_total"], r["calculated_total"], r["difference"]), ("MISMATCH", 1200.0, 1050.0, -150.0))
        self.assertTrue(v["total_differs"])
        self.assertEqual(self.confirm(doc["id"]).status_code, 409)            # needs a reason, never silent

    # ---- GST rate
    def test_unreadable_rate_is_blocked_not_zero_or_default(self):
        doc = self.upload()
        self.set_ocr(doc["id"], items=[ocr_item(0, gst_rate=None, hsn_code="")], total_amount=1000.0)
        v = self.view(doc["id"])
        ln = v["lines"][0]
        self.assertIsNone(ln["gst_rate"])
        self.assertTrue(any(b["field"] == "gst_rate" for b in ln["blocking"]))
        self.assertEqual(v["reconciliation"]["state"], "MISSING_TAX_INFO")
        self.assertFalse(v["can_confirm"])

    def test_invalid_rate_is_rejected(self):
        doc = self.upload()
        self.set_ocr(doc["id"], items=[ocr_item(0, gst_rate=7.0)], total_amount=1070.0)
        ln = self.view(doc["id"])["lines"][0]
        self.assertIsNone(ln["gst_rate"])
        self.assertIn("not a GST rate", ln["gst_error"])

    def test_hsn_rate_is_dated_and_needs_acknowledgement(self):
        for when, rate in ((OLD, 12.0), (NEW, 5.0)):
            base = self.counts()[0]
            doc = self.upload()
            self.set_ocr(doc["id"], items=[ocr_item(0, gst_rate=None, hsn_code="3004")], date_s=when, invoice_no="H-" + when,
                         total_amount=round(1000 * (1 + rate / 100), 2))
            ln = self.view(doc["id"])["lines"][0]
            self.assertEqual((ln["gst_rate"], ln["gst_source"], ln["gst_needs_ack"]), (rate, "hsn_table", True))
            self.assertEqual(self.confirm(doc["id"]).status_code, 409)         # not confirmed until the user accepts the rate
            self.assertEqual(self.counts()[0], base)
            self.assertEqual(self.confirm(doc["id"], acknowledge_warnings=True).status_code, 200)

    def test_uncertain_ocr_rate_is_not_treated_as_verified(self):
        doc = self.upload()
        self.set_ocr(doc["id"], items=[ocr_item(0, gst_rate=5.0, field_flags={"gst_rate": "unclear"})], total_amount=1050.0)
        ln = self.view(doc["id"])["lines"][0]
        self.assertEqual((ln["gst_source"], ln["gst_needs_ack"]), ("invoice_line_uncertain", True))

    def test_rate_printed_on_the_line_wins_and_is_recorded(self):
        doc = self.upload()
        self.set_ocr(doc["id"], items=[ocr_item(0, gst_rate=18.0)], total_amount=1180.0)
        ln = self.view(doc["id"])["lines"][0]
        self.assertEqual((ln["gst_rate"], ln["gst_source"], ln["gst_needs_ack"]), (18.0, "invoice_line", False))

    def test_this_shops_stock_supplies_a_missing_rate_but_not_when_it_disagrees_with_itself(self):
        d = self.S()
        for i, rate in enumerate((5.0, 5.0)):
            d.add(models.Product(user_id=1, product_name="KNOWN TAB", batch_number="K%d" % i, quantity=1, category="Medicine", unit_price=10, purchase_price=5,
                                 gst_rate=rate, gst_percentage=rate, expiry_date=date(2030, 1, 1)))
        d.commit()
        res = gst_resolver.resolve(d, 1, {"product_name": "known tab", "gst_rate": None, "hsn_code": ""}, NEW)
        self.assertEqual((res["rate"], res["source"]), (5.0, "product_master"))
        d.add(models.Product(user_id=1, product_name="KNOWN TAB", batch_number="K9", quantity=1, category="Medicine", unit_price=10, purchase_price=5,
                             gst_rate=18.0, gst_percentage=18.0, expiry_date=date(2030, 1, 1)))
        d.commit()
        res = gst_resolver.resolve(d, 1, {"product_name": "KNOWN TAB", "gst_rate": None, "hsn_code": ""}, NEW)
        d.close()
        self.assertIsNone(res["rate"])                                          # ambiguous: nothing assumed
        self.assertIn("different GST rates", res["error"])

    def test_user_typed_rate_is_verified(self):
        doc = self.upload()
        item = ocr_item(0, gst_rate=18.0, gst_verified=True)
        self.set_ocr(doc["id"], items=[item], total_amount=1180.0)
        ln = self.view(doc["id"])["lines"][0]
        self.assertEqual((ln["gst_source"], ln["gst_needs_ack"]), ("user_verified", False))

    # ---- editing, drafts, confirmation
    def test_editing_a_figure_recalculates_immediately_and_posts_nothing(self):
        doc = self.upload()
        self.set_ocr(doc["id"], items=[ocr_item(0, gst_rate=5.0)], total_amount=1050.0)
        before = self.counts()
        self.assertEqual(self.view(doc["id"])["reconciliation"]["state"], "MATCHED")
        self.c.put("/documents/%d/review-data" % doc["id"], json={"header": {"supplier_id": 1, "invoice_number": "INV-100", "invoice_date": NEW}, "items": [ocr_item(0, gst_rate=5.0, quantity=20, total_price=2000.0)]})
        r = self.view(doc["id"])["reconciliation"]
        self.assertEqual((r["state"], r["calculated_total"]), ("MISMATCH", 2100.0))
        self.assertEqual(self.counts(), before)                                  # saving corrections never posts stock or payables
        d = self.S()
        raw = json.loads(d.get(models.Document, doc["id"]).ocr_raw_json)
        d.close()
        self.assertEqual(raw["items"][0]["quantity"], 10)                       # the original OCR result is preserved

    def test_confirm_exactly_once_and_a_refused_confirm_keeps_the_corrections(self):
        doc = self.upload()
        self.set_ocr(doc["id"], items=[ocr_item(0, gst_rate=5.0)], total_amount=None)
        self.c.put("/documents/%d/review-data" % doc["id"], json={"header": {"supplier_id": 1, "invoice_number": "INV-100", "invoice_date": NEW}, "items": [ocr_item(0, gst_rate=5.0, product_name="CORRECTED TAB")]})
        self.assertEqual(self.confirm(doc["id"]).status_code, 422)               # no printed total yet
        self.assertEqual(self.view(doc["id"])["lines"][0]["product_name"], "CORRECTED TAB")
        self.c.put("/documents/%d/review-data" % doc["id"], json={"header": {"supplier_id": 1, "invoice_number": "INV-100", "invoice_date": NEW, "total_amount": 1050.0}, "items": [ocr_item(0, gst_rate=5.0, product_name="CORRECTED TAB")]})
        self.assertEqual(self.confirm(doc["id"]).status_code, 200)
        after = self.counts()
        self.assertEqual(self.confirm(doc["id"]).status_code, 409)
        self.assertEqual(self.counts(), after)


del _Base, _doc          # so the loader does not collect the borrowed test class a second time


if __name__ == "__main__":
    unittest.main()
