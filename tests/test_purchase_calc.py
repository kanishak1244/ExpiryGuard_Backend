"""
Purchase invoice calculation: one Decimal engine (purchase_calc), used by manual entry, OCR review, drafts and posting.

Regression for the JANTA MEDICAL STORE bill: a printed invoice total of 887.00 was shown as 923.46 because the bill's
invoice-level discount (35.18) was extracted but never applied; GST was charged on the gross lines. Tests A-M below.
No test hard-codes that invoice: the same engine handles every structure, the figures are inputs.
"""
import json
import os
import random
import sys
import unittest
import uuid
from datetime import date, timedelta
from decimal import Decimal

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
import purchase_calc as pc
import purchase_entry
from routes import document_archive_routes as dar

FUT = (date.today() + timedelta(days=400)).isoformat()
JPEG = b"\xFF\xD8\xFF\xE0" + b"\x00" * 64
JANTA_AMOUNTS = [105.60, 233.30, 157.88, 194.74, 187.96]


def L(qty=1, rate=100.0, gst=12.0, **kw):
    d = {"qty": qty, "rate": rate, "gst_rate": gst}
    d.update(kw)
    return d


class TestCalculationEngine(unittest.TestCase):
    # ---- B: no discount
    def test_b_no_discount(self):
        c = pc.calc_invoice([L(10, 50.0, 12), L(2, 33.33, 12)])
        t = c["totals"]
        self.assertEqual((t["gross"], t["discount"], t["taxable"], t["tax"], t["payable"]), (566.66, 0.0, 566.66, 68.0, 634.66))
        self.assertEqual(t["cgst"] + t["sgst"], t["tax"])

    # ---- A: the JANTA structure through the engine (figures are inputs, not special-cased)
    def test_a_invoice_level_discount_before_gst_reconciles_to_the_printed_total(self):
        lines = [L(1, a, 5) for a in JANTA_AMOUNTS]
        c = pc.calc_invoice(lines, invoice_discount_amount=35.18, round_to_rupee=True)
        t = c["totals"]
        self.assertEqual((t["gross"], t["invoice_discount"], t["taxable"]), (879.48, 35.18, 844.30))
        self.assertEqual((t["cgst"], t["sgst"], t["tax"]), (21.11, 21.11, 42.22))
        self.assertEqual((t["total_before_round"], t["round_off"], t["payable"]), (886.52, 0.48, 887.0))
        rec = pc.reconcile(c, {"total": 887.0, "discount": 35.18, "taxable": 844.30, "cgst": 21.10, "sgst": 21.10, "subtotal": 879.48})
        self.assertEqual((rec["status"], rec["difference"]), ("PASS", 0.0))
        self.assertTrue(all(x["ok"] for x in rec["components"]))
        # the old behaviour (discount ignored, GST on the gross) is what produced the wrong total
        wrong = pc.calc_invoice(lines)["totals"]["payable"]
        self.assertNotEqual(wrong, 887.0)
        self.assertAlmostEqual(wrong, 923.46, delta=0.02)
        bad = pc.reconcile(pc.calc_invoice(lines), {"total": 887.0, "discount": 35.18})
        self.assertEqual(bad["status"], "REVIEW")
        self.assertIn("discount", " ".join(bad["likely_causes"]).lower())

    # ---- C: item-level discounts (percent and fixed) with different tax rates
    def test_c_item_level_discounts_and_mixed_rates(self):
        c = pc.calc_invoice([L(10, 50.0, 12, disc_percent=10), L(5, 100.0, 5, disc_amount=25)])
        a, b = c["lines"]
        self.assertEqual((a["gross"], a["line_discount"], a["taxable"], a["tax"]), (500.0, 50.0, 450.0, 54.0))
        self.assertEqual((b["gross"], b["line_discount"], b["taxable"], b["tax"]), (500.0, 25.0, 475.0, 23.75))
        self.assertEqual(c["totals"]["payable"], 1002.75)

    # ---- D: invoice-level discount shared over the lines
    def test_d_invoice_discount_is_shared_in_proportion_and_adds_up_exactly(self):
        c = pc.calc_invoice([L(1, 100.0, 12), L(1, 300.0, 12)], invoice_discount_amount=40)
        self.assertEqual([x["invoice_discount_share"] for x in c["lines"]], [10.0, 30.0])
        self.assertEqual((c["totals"]["taxable"], c["totals"]["tax"], c["totals"]["payable"]), (360.0, 43.2, 403.2))
        pct = pc.calc_invoice([L(1, 100.0, 12), L(1, 300.0, 12)], invoice_discount_percent=10)
        self.assertEqual(pct["totals"]["payable"], 403.2)
        odd = pc.calc_invoice([L(1, 10.0), L(1, 10.0), L(1, 10.0)], invoice_discount_amount=0.10)
        self.assertEqual(round(sum(x["invoice_discount_share"] for x in odd["lines"]), 2), 0.10)       # no lost paisa

    def test_d2_discount_shared_across_different_tax_rates_taxes_each_group_after_discount(self):
        c = pc.calc_invoice([L(1, 100.0, 5), L(1, 100.0, 18)], invoice_discount_amount=20)
        g = {x["rate"]: x for x in c["tax_groups"]}
        self.assertEqual((g[5.0]["taxable"], g[5.0]["tax"], g[18.0]["taxable"], g[18.0]["tax"]), (90.0, 4.5, 90.0, 16.2))

    # ---- E: GST-inclusive prices
    def test_e_inclusive_prices_do_not_get_gst_added_again(self):
        c = pc.calc_invoice([L(1, 112.0, 12)], prices_include_gst=True)
        self.assertEqual((c["totals"]["taxable"], c["totals"]["tax"], c["totals"]["payable"]), (100.0, 12.0, 112.0))
        ex = pc.calc_invoice([L(1, 112.0, 12)])
        self.assertEqual(ex["totals"]["payable"], 125.44)
        d = pc.calc_invoice([L(1, 112.0, 12)], prices_include_gst=True, invoice_discount_amount=11.2)
        self.assertEqual((d["totals"]["taxable"], d["totals"]["payable"]), (90.0, 100.8))

    # ---- F: mixed GST rates, exempt and zero-rated
    def test_f_mixed_rates_are_taxed_separately(self):
        c = pc.calc_invoice([L(1, 100.0, 5), L(1, 100.0, 18), L(1, 100.0, 0)])
        rates = {x["rate"]: x["tax"] for x in c["tax_groups"]}
        self.assertEqual(rates, {0.0: 0.0, 5.0: 5.0, 18.0: 18.0})
        self.assertEqual(c["totals"]["payable"], 323.0)

    # ---- G: IGST
    def test_g_interstate_uses_igst_only(self):
        c = pc.calc_invoice([L(1, 100.0, 5), L(1, 100.0, 18)], interstate=True)
        t = c["totals"]
        self.assertEqual((t["cgst"], t["sgst"], t["igst"], t["tax"], t["payable"]), (0.0, 0.0, 23.0, 23.0, 223.0))

    # ---- H: round-off
    def test_h_round_off_is_reported_not_hidden(self):
        up = pc.calc_invoice([L(1, 100.4, 0)], round_to_rupee=True)["totals"]
        down = pc.calc_invoice([L(1, 100.6, 0)], round_to_rupee=True)["totals"]
        self.assertEqual((up["payable"], up["round_off"]), (100.0, -0.4))
        self.assertEqual((down["payable"], down["round_off"]), (101.0, 0.4))
        half = pc.calc_invoice([L(1, 100.5, 0)], round_to_rupee=True)["totals"]
        self.assertEqual(half["payable"], 101.0)                                             # half rounds up
        exact = pc.calc_invoice([L(1, 100.4, 0)])["totals"]
        self.assertEqual((exact["payable"], exact["round_off"]), (100.4, 0.0))               # no rounding unless asked

    def test_h2_other_charges_with_and_without_gst(self):
        c = pc.calc_invoice([L(1, 100.0, 12)], other_charges=50, other_charges_gst=18)
        t = c["totals"]
        self.assertEqual((t["other_charges"], t["tax"], t["payable"]), (59.0, 21.0, 59.0 + 100.0 + 12.0))
        self.assertEqual(pc.calc_invoice([L(1, 100.0, 12)], other_charges=50)["totals"]["payable"], 162.0)

    def test_free_units_cost_nothing_and_lower_the_unit_cost(self):
        c = pc.calc_invoice([L(10, 50.0, 12, free=2, disc_percent=10)])
        ln = c["lines"][0]
        self.assertEqual((ln["received_qty"], ln["taxable"], ln["net_unit_cost"]), (12, 450.0, 37.5))

    # ---- reconciliation explains itself and tolerance is configurable
    def test_reconcile_names_the_component_that_differs(self):
        c = pc.calc_invoice([L(1, 100.0, 12)])
        rec = pc.reconcile(c, {"total": 130.0, "taxable": 100.0, "cgst": 6.0, "sgst": 6.0, "igst": 0.0, "other": 10.0})
        self.assertEqual(rec["status"], "REVIEW")
        self.assertEqual(rec["difference"], -18.0)
        bad = [x["key"] for x in rec["components"] if not x["ok"]]
        self.assertIn("other", bad)
        self.assertTrue(any("Other charges" in x for x in rec["likely_causes"]))
        self.assertEqual(pc.reconcile(c, None)["status"], "NO_PRINTED_TOTAL")

    def test_tolerance_is_configurable_and_a_material_error_is_not_hidden(self):
        c = pc.calc_invoice([L(1, 100.0, 0)])
        self.assertEqual(pc.reconcile(c, {"total": 100.9})["status"], "PASS")               # default tolerance ₹1
        self.assertEqual(pc.reconcile(c, {"total": 101.5})["status"], "REVIEW")
        os.environ["PURCHASE_RECON_TOLERANCE"] = "0.10"
        try:
            self.assertEqual(pc.reconcile(c, {"total": 100.9})["status"], "REVIEW")
            self.assertEqual(pc.reconcile(c, {"total": 100.05})["status"], "PASS")
        finally:
            os.environ.pop("PURCHASE_RECON_TOLERANCE")

    def test_infer_tax_mode_only_from_the_printed_taxable_amount(self):
        self.assertIs(pc.infer_tax_mode(879.48, 35.18, 844.30, [5.0]), False)
        self.assertIs(pc.infer_tax_mode(112.0, 0, 100.0, [12.0]), True)
        self.assertIsNone(pc.infer_tax_mode(100.0, 0, 55.0, [12.0]))
        self.assertIsNone(pc.infer_tax_mode(100.0, 0, None, [12.0]))

    # ---- M: boundaries and properties
    def test_m_invalid_financial_data_is_rejected(self):
        bad = [dict(lines=[L(-1)]), dict(lines=[L(1, -5)]), dict(lines=[L(1, 5, 40)]), dict(lines=[L(1, 5, 12, disc_percent=101)]),
               dict(lines=[L(1, 5)], invoice_discount_amount=999), dict(lines=[L(1, 5)], invoice_discount_amount=1, invoice_discount_percent=1),
               dict(lines=[L(1, 5)], other_charges=-1), dict(lines=[L("x")]), dict(lines=[L(1, float("nan"))]), dict(lines=[L(1, 10 ** 12)])]
        for b in bad:
            lines = b.pop("lines")
            with self.assertRaises(pc.CalcError, msg=str(b)):
                pc.calc_invoice(lines, **b)

    def test_m_zero_and_large_amounts(self):
        z = pc.calc_invoice([L(0, 100.0, 12)])["totals"]
        self.assertEqual((z["gross"], z["tax"], z["payable"]), (0.0, 0.0, 0.0))
        big = pc.calc_invoice([L(1000, 999999.99, 12)])["totals"]
        self.assertEqual(big["gross"], 999999990.0)
        self.assertEqual(big["payable"], float(Decimal("999999990.00") * Decimal("1.12")))
        self.assertEqual(pc.calc_invoice([L(3, 0.1, 0)])["totals"]["gross"], 0.3)             # no binary-float drift

    def test_m_properties_hold_for_random_invoices(self):
        rng = random.Random(20261026)
        for _ in range(300):
            lines = [L(rng.randint(0, 50), round(rng.uniform(0, 900), 2), rng.choice([0, 5, 12, 18, 28]),
                       disc_percent=rng.choice([0, 0, 5, 12.5]), disc_amount=rng.choice([0, 0, 3.5])) for _ in range(rng.randint(1, 8))]
            net = sum(Decimal(str(x["gross"])) - Decimal(str(x["line_discount"])) for x in pc.calc_invoice(lines)["lines"])
            kw = dict(invoice_discount_amount=round(float(net) * rng.choice([0, 0.05, 0.3]), 2), other_charges=rng.choice([0, 25]),
                      interstate=rng.random() < 0.3, prices_include_gst=rng.random() < 0.3, round_to_rupee=rng.random() < 0.5)
            c = pc.calc_invoice(lines, **kw)
            t = c["totals"]
            D = Decimal
            self.assertEqual(sum(D(str(x["invoice_discount_share"])) for x in c["lines"]), D(str(t["invoice_discount"])))
            self.assertEqual(D(str(t["cgst"])) + D(str(t["sgst"])) + D(str(t["igst"])), D(str(t["tax"])))
            if kw["interstate"]:
                self.assertEqual((t["cgst"], t["sgst"]), (0.0, 0.0))
            self.assertEqual(sum(D(str(g["taxable"])) for g in c["tax_groups"]), D(str(t["taxable"])))
            self.assertEqual(D(str(t["taxable"])) + D(str(t["tax"])) + D(str(kw["other_charges"])), D(str(t["total_before_round"])))
            self.assertEqual(D(str(t["total_before_round"])) + D(str(t["round_off"])), D(str(t["payable"])))
            self.assertGreaterEqual(t["payable"], 0)
            self.assertLessEqual(abs(t["round_off"]), 0.5)
            self.assertTrue(all(x["taxable"] >= 0 for x in c["lines"]))


# ---------------------------------------------------------------------------------------------------- integration
def ocr_line(amount, gst=5.0, name=None, **kw):
    it = {"product_name": name or "MED %s" % amount, "hsn_code": "3004", "gst_rate": gst, "batch_number": "B%d" % int(amount * 100), "expiry_date": FUT,
          "quantity": 1, "free_qty": 0, "purchase_price": amount, "mrp": amount * 2, "discount_percent": 0, "total_price": amount, "field_flags": {}}
    it.update(kw)
    return it


class TestInvoiceWorkflow(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False)
        db = self.S()
        db.add(models.User(id=1, shop_name="S", owner_name="O", email="pc@test.invalid", password="x", default_gst_percentage=12.0))
        db.add(models.Supplier(id=1, user_id=1, name="Janta Medical Store"))
        db.commit()
        db.close()
        self.files = []

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
        self.c = TestClient(app_module.app, raise_server_exceptions=False)

    def tearDown(self):
        for k in self.overrides:
            app_module.app.dependency_overrides.pop(k, None)
        for f in self.files:
            try:
                os.remove(f)
            except OSError:
                pass

    def doc(self, items, header=None, total=887.0, invoice_no="J-1"):
        r = self.c.post("/documents/upload", files={"file": ("bill.jpg", JPEG, "image/jpeg")})
        self.assertEqual(r.status_code, 201, r.text)
        doc = r.json()
        self.files.append(os.path.join(str(dar.DOCUMENTS_DIR), os.path.basename(doc["file_path"])))
        data = {"supplier_name": "JANTA MEDICAL STORE", "invoice_number": invoice_no, "invoice_date": date.today().isoformat(), "total_amount": total, "items": items}
        data.update(header or {})
        d = self.S()
        x = d.get(models.Document, doc["id"])
        x.ocr_raw_json = json.dumps(data)
        x.ocr_status, x.supplier_id, x.invoice_number, x.invoice_date, x.total_amount = "Needs Review", 1, invoice_no, date.today(), total
        d.commit()
        d.close()
        return doc["id"]

    JANTA_HEADER = {"subtotal": 879.48, "discount_amount": 35.18, "taxable_amount": 844.30, "cgst_amount": 21.10, "sgst_amount": 21.10, "total_amount": 887.0}

    def review(self, doc_id):
        return self.c.get("/documents/%d/review" % doc_id).json()

    def state(self):
        d = self.S()
        try:
            return (d.query(models.PurchaseInvoice).count(), d.query(models.InventoryTransaction).count(), sum(p.quantity for p in d.query(models.Product).all()))
        finally:
            d.close()

    # ---- A through the real workflow: review, confirm, posted amounts
    def test_a_janta_bill_reconciles_confirms_and_posts_887(self):
        doc = self.doc([ocr_line(a) for a in JANTA_AMOUNTS], self.JANTA_HEADER)
        v = self.review(doc)
        self.assertEqual((v["computed"]["total"], v["computed"]["discount"], v["computed"]["taxable"]), (887.0, 35.18, 844.3))
        self.assertEqual((v["reconciliation"]["status"], v["reconciliation"]["difference"]), ("PASS", 0.0))
        self.assertFalse(v["total_differs"])
        self.assertTrue(v["can_confirm"], v["blocking"])
        r = self.c.post("/documents/%d/confirm-review" % doc, json={"acknowledge_warnings": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["total_amount"], 887.0)
        self.assertNotEqual(r.json()["total_amount"], 923.46)
        led = self.c.get("/suppliers/1/ledger").json()["balance_payable"]
        self.assertEqual(led, 887.0)
        d = self.S()
        costs = sorted(round(p.purchase_price, 2) for p in d.query(models.Product).all())
        raw = json.loads(d.get(models.Document, doc).ocr_raw_json)
        d.close()
        self.assertAlmostEqual(sum(costs), 844.30, delta=0.03)                        # stock cost is after the discount
        self.assertEqual(raw["calculation"]["totals"]["payable"], 887.0)               # how it was calculated is kept
        self.assertEqual(raw["calculation"]["policy"]["tax_mode"], "exclusive")

    def test_a2_without_the_discount_in_the_header_the_bill_is_flagged_not_forced(self):
        header = dict(self.JANTA_HEADER)
        header.pop("discount_amount")
        doc = self.doc([ocr_line(a) for a in JANTA_AMOUNTS], header)
        v = self.review(doc)
        self.assertTrue(v["total_differs"])
        self.assertEqual(v["reconciliation"]["status"], "REVIEW")
        self.assertAlmostEqual(v["computed"]["total"], 923.46, delta=0.5)          # 923.46 before the fix; rupee-rounded here
        self.assertTrue(any(not c["ok"] for c in v["reconciliation"]["components"]))
        r = self.c.post("/documents/%d/confirm-review" % doc, json={"acknowledge_warnings": True})
        self.assertEqual(r.status_code, 409)
        self.assertIn("RECONCILIATION_FAILED", r.text)
        self.assertEqual(self.state(), (0, 0, 0))                                         # nothing posted

    def test_discount_is_never_applied_twice(self):
        lines = [ocr_line(100.0, gst=12, discount_percent=10), ocr_line(100.0, gst=12, name="OTHER", discount_percent=10)]
        header = {"subtotal": 200.0, "discount_amount": 20.0, "taxable_amount": 180.0, "total_amount": 201.6}
        doc = self.doc(lines, header, total=202.0)
        v = self.review(doc)
        self.assertEqual((v["computed"]["discount"], v["computed"]["taxable"]), (20.0, 180.0))        # lines carry it: header not added again
        self.assertTrue(any("not applied a second time" in n for n in v["notes"]))
        conflict = self.doc([ocr_line(100.0, gst=12, discount_percent=10)], {"subtotal": 100.0, "discount_amount": 50.0, "total_amount": 50.0}, total=50.0, invoice_no="J-2")
        v2 = self.review(conflict)
        self.assertEqual(v2["computed"]["discount"], 10.0)
        self.assertTrue(any("Conflicting discounts" in n for n in v2["notes"]))
        self.assertTrue(v2["total_differs"])

    def test_inclusive_and_interstate_are_inferred_only_from_the_bill_figures(self):
        incl = self.doc([ocr_line(112.0, gst=12, name="INCL")], {"subtotal": 112.0, "taxable_amount": 100.0, "cgst_amount": 6.0, "sgst_amount": 6.0, "total_amount": 112.0}, total=112.0)
        v = self.review(incl)
        self.assertEqual((v["calculation_policy"]["tax_mode"], v["computed"]["total"]), ("inclusive", 112.0))
        igst = self.doc([ocr_line(100.0, gst=18, name="IGSTMED")], {"subtotal": 100.0, "taxable_amount": 100.0, "igst_amount": 18.0, "total_amount": 118.0}, total=118.0, invoice_no="J-3")
        v = self.review(igst)
        self.assertEqual((v["calculation_policy"]["supply"], v["computed"]["igst"], v["computed"]["cgst"]), ("inter-state", 18.0, 0.0))
        unclear = self.doc([ocr_line(100.0, gst=12, name="UNCL")], {"subtotal": 100.0, "taxable_amount": 55.0, "total_amount": 112.0}, total=112.0, invoice_no="J-4")
        self.assertTrue(any("whether its rates include GST" in n for n in self.review(unclear)["notes"]))

    # ---- I: editing recalculates every dependent value
    def test_i_edits_recalculate_everything(self):
        doc = self.doc([ocr_line(100.0, gst=12, name="EDITME")], {"subtotal": 100.0, "total_amount": 112.0}, total=112.0)
        self.assertEqual(self.review(doc)["computed"]["total"], 112.0)
        item = ocr_line(100.0, gst=12, name="EDITME", quantity=3, purchase_price=80.0, discount_percent=10)
        r = self.c.put("/documents/%d/review-data" % doc, json={"header": {"supplier_id": 1, "invoice_number": "J-1", "invoice_date": date.today().isoformat(),
                                                                          "total_amount": 241.92}, "items": [item]})
        self.assertEqual(r.status_code, 200, r.text)
        v = r.json()
        self.assertEqual((v["computed"]["gross"], v["computed"]["discount"], v["computed"]["taxable"], v["computed"]["total"]), (240.0, 24.0, 216.0, 241.92))
        self.assertEqual(v["reconciliation"]["status"], "PASS")
        item2 = dict(item, gst_rate=5.0)
        v = self.c.put("/documents/%d/review-data" % doc, json={"header": {"supplier_id": 1, "invoice_number": "J-1", "invoice_date": date.today().isoformat(),
                                                                          "total_amount": 241.92}, "items": [item2]}).json()
        self.assertEqual(v["computed"]["total"], 226.8)
        self.assertEqual(v["reconciliation"]["status"], "REVIEW")                          # printed 241.92 no longer matches
        v = self.c.put("/documents/%d/review-data" % doc, json={"header": {"supplier_id": 1, "invoice_number": "J-1", "invoice_date": date.today().isoformat(),
                                                                          "total_amount": 226.8, "discount_amount": 0, "other_amount": 10}, "items": [item2]}).json()
        self.assertEqual((v["computed"]["other_charges"], v["computed"]["total"]), (10.0, 236.8))

    # ---- J: OCR errors trigger review
    def test_j_ocr_errors_cannot_slip_through(self):
        missing_rate = ocr_line(100.0, purchase_price=None)
        wrong_qty = ocr_line(100.0, name="WQ", quantity=0)
        doc = self.doc([missing_rate, wrong_qty], total=500.0)
        v = self.review(doc)
        fields = {(b["field"]) for b in v["blocking"]}
        self.assertTrue(any("purchase_price" in f for f in fields))
        self.assertTrue(any("quantity" in f for f in fields))
        self.assertFalse(v["can_confirm"])
        r = self.c.post("/documents/%d/confirm-review" % doc)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.state(), (0, 0, 0))
        misread_total = self.doc([ocr_line(100.0, gst=12, name="MT")], total=11200.0, invoice_no="J-9")      # 112.00 read as 11200
        v = self.review(misread_total)
        self.assertTrue(v["total_differs"])
        self.assertEqual(self.c.post("/documents/%d/confirm-review" % misread_total).status_code, 409)

    def test_override_needs_a_reason_and_is_audited_and_cannot_post_twice(self):
        doc = self.doc([ocr_line(100.0, gst=12, name="OVR")], total=999.0, invoice_no="J-5")
        too_short = self.c.post("/documents/%d/confirm-review" % doc, json={"override_reason": "ok"})
        self.assertEqual(too_short.status_code, 409)
        ok = self.c.post("/documents/%d/confirm-review" % doc, json={"override_reason": "Supplier confirmed the printed total is wrong"})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["total_amount"], 112.0)                                   # the calculated total is posted, not the printed one
        d = self.S()
        raw = json.loads(d.get(models.Document, doc).ocr_raw_json)
        d.close()
        a = raw["override_audit"][0]
        self.assertEqual((a["by"], a["printed_total"], a["calculated_total"], a["difference"]), (1, 999.0, 112.0, -887.0))
        self.assertTrue(a["at"])
        after = self.state()
        again = self.c.post("/documents/%d/confirm-review" % doc, json={"override_reason": "Supplier confirmed the printed total is wrong"})
        self.assertEqual(again.status_code, 409)
        self.assertEqual(self.state(), after)

    # ---- L: duplicate confirmation
    def test_l_repeated_confirmation_cannot_duplicate_stock_or_ledger(self):
        doc = self.doc([ocr_line(a) for a in JANTA_AMOUNTS], self.JANTA_HEADER)
        first = self.c.post("/documents/%d/confirm-review" % doc, json={"acknowledge_warnings": True})
        self.assertEqual(first.status_code, 200, first.text)
        after = self.state()
        ledger = self.c.get("/suppliers/1/ledger").json()["balance_payable"]
        for _ in range(3):
            self.assertEqual(self.c.post("/documents/%d/confirm-review" % doc, json={"acknowledge_warnings": True}).status_code, 409)
        self.assertEqual((self.state(), self.c.get("/suppliers/1/ledger").json()["balance_payable"]), (after, ledger))

    # ---- K: manual entry, drafts and the preview endpoint all use the same engine
    def manual(self, **kw):
        body = {"supplier_id": 1, "invoice_number": "M-1", "invoice_date": date.today().isoformat(),
                "items": [{"product_name": "ALPHA TAB", "batch_number": "A1", "expiry_date": FUT, "quantity": 10, "purchase_rate": 50, "gst_rate": 12, "mrp": 90, "discount_percent": 10},
                          {"product_name": "BETA TAB", "batch_number": "B1", "expiry_date": FUT, "quantity": 4, "purchase_rate": 100, "gst_rate": 5, "mrp": 150}]}
        body.update(kw)
        return body

    def calc_body(self, m):
        return {"items": [{"quantity": i["quantity"], "free_quantity": i.get("free_quantity", 0), "purchase_rate": i["purchase_rate"],
                           "discount_percent": i.get("discount_percent", 0), "gst_rate": i["gst_rate"]} for i in m["items"]],
                **{k: m[k] for k in ("invoice_discount_percent", "invoice_discount_amount", "other_charges", "interstate", "prices_include_gst", "round_to_rupee") if k in m}}

    def test_k_preview_draft_and_posting_agree(self):
        m = self.manual(invoice_discount_amount=30, other_charges=20, round_to_rupee=True)
        preview = self.c.post("/purchases/calc", json=self.calc_body(m)).json()
        draft = self.c.post("/purchases/drafts", json={"supplier_id": 1, "invoice_number": "M-1", "payload": {"header": {"invoice": {"discount": "30", "other": "20", "round": True}},
                                                                                                           "rows": [{"name": "ALPHA TAB", "qty": "10", "rate": "50"}]}}).json()
        reopened = self.c.get("/purchases/drafts/%d" % draft["id"]).json()
        self.assertEqual(reopened["payload"]["header"]["invoice"], {"discount": "30", "other": "20", "round": True})      # invoice inputs survive reopening
        r = self.c.post("/purchases/manual", json=dict(m, draft_id=draft["id"], expected_total=preview["totals"]["payable"]))
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["total_amount"], preview["totals"]["payable"])
        self.assertEqual(r.json()["reconciliation"]["status"], "NO_PRINTED_TOTAL")
        self.assertEqual(self.c.get("/suppliers/1/ledger").json()["balance_payable"], preview["totals"]["payable"])
        d = self.S()
        snap = json.loads(d.get(models.PurchaseDraft, draft["id"]).payload)["calculation"]
        d.close()
        self.assertEqual(snap["totals"]["payable"], preview["totals"]["payable"])                    # draft keeps how it was calculated
        self.assertEqual(snap["inputs"]["invoice_discount_amount"], 30)

    def test_screen_and_server_cannot_disagree_silently(self):
        m = self.manual(invoice_discount_amount=30)
        r = self.c.post("/purchases/manual", json=dict(m, expected_total=1.0))
        self.assertEqual(r.status_code, 409)
        self.assertIn("TOTAL_MISMATCH", r.text)
        self.assertEqual(self.state(), (0, 0, 0))

    def test_posted_totals_follow_the_discount_structure(self):
        m = self.manual(invoice_discount_percent=10)
        r = self.c.post("/purchases/manual", json=m)
        self.assertEqual(r.status_code, 201, r.text)
        # lines: 450 (12 %) and 400 (5 %); 10 % bill discount -> 405 + 360 taxable; tax 48.60 + 18.00
        self.assertEqual((r.json()["totals"]["taxable"], r.json()["totals"]["gst"], r.json()["total_amount"]), (765.0, 66.6, 831.6))

    def test_m_api_rejects_invalid_financial_input(self):
        m = self.manual()
        for patch in ({"invoice_discount_amount": -5}, {"other_charges": -1}, {"invoice_discount_percent": 150}, {"invoice_discount_amount": 5000}):
            r = self.c.post("/purchases/manual", json=dict(m, **patch))
            self.assertIn(r.status_code, (400, 422), patch)
        both = self.c.post("/purchases/calc", json=dict(self.calc_body(m), invoice_discount_percent=5, invoice_discount_amount=5))
        self.assertEqual(both.status_code, 422)
        neg = self.c.post("/purchases/calc", json={"items": [{"quantity": -1, "purchase_rate": 5, "gst_rate": 12}]})
        self.assertEqual(neg.status_code, 422)
        self.assertEqual(self.state(), (0, 0, 0))

    def test_existing_manual_totals_are_unchanged_without_invoice_level_inputs(self):
        r = self.c.post("/purchases/manual", json=self.manual())
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["total_amount"], 450 * 1.12 + 400 * 1.05)


class TestCalcPageWiring(unittest.TestCase):
    def _read(self, rel):
        with open(os.path.join(os.path.dirname(__file__), "..", rel), encoding="utf-8") as f:
            return f.read()

    def test_manual_screen_shows_server_totals_and_invoice_level_inputs(self):
        js, html = self._read("web/js/purchase_entry.js"), self._read("web/purchase_entry.html")
        self.assertIn("/purchases/calc", js)
        self.assertNotIn("peCalcTotals(state.rows)", js)               # the totals panel no longer computes its own total
        for needle in ("pe-inv-disc", "pe-inv-other", "pe-inv-incl", "pe-inv-igst", "pe-inv-round", "pe-t-round"):
            self.assertIn(needle, html)

    def test_review_screen_shows_reconciliation_and_asks_for_a_reason(self):
        js = self._read("web/js/doc_review.js")
        self.assertIn("override_reason", js)
        self.assertIn("drReconHtml", js)


if __name__ == "__main__":
    unittest.main()
