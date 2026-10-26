"""
P0 tax and report fixes (web audit 2026-10-26).

  1. A 0 % GST medicine is billed at 0 % (it used to fall back to 12 %). Only a missing rate uses the shop default; an
     old row whose two rate columns disagree (one left at 0) uses the non-zero one.
  2. Profit = taxable value (GST excluded) - real batch cost of what was sold, net of returns; a loose tablet costs
     pack cost / tablets per strip; lines without a purchase price are left out and reported, never counted as free.
  3. Sales and GST reports subtract sales returns made in the period, and use the GST saved on each bill line.
In-memory SQLite, sessions like the app's (no autoflush), test login.
"""
import os
import sys
import unittest
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

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
import tax_reports

FUT = date.today() + timedelta(days=300)


def prod(pid, uid, name, gst=12.0, gst_rate=None, cost=60.0, mrp=100.0, qty=50, tabs=10):
    return models.Product(id=pid, user_id=uid, category="A", product_name=name, batch_number="B%d" % pid, quantity=qty, unit_price=mrp,
                          purchase_price=cost, tablets_per_strip=tabs, loose_tablet_price=round(mrp / tabs, 2) if tabs else None,
                          gst_percentage=gst, gst_rate=gst if gst_rate is None else gst_rate, hsn_code="3004", expiry_date=FUT)


class TestTaxAndProfit(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False)
        db = self.S()
        for uid in (1, 2):
            db.add(models.User(id=uid, shop_name="S%d" % uid, owner_name="O", email="tx%d@test.invalid" % uid, password="x", default_gst_percentage=12.0))
        db.add_all([
            prod(1, 1, "DOLO 650", gst=12.0),
            prod(2, 1, "EXEMPT MED", gst=0.0),                       # a genuinely exempt medicine
            prod(3, 1, "OLD ROW", gst=0.0, gst_rate=5.0),            # legacy row: one column left at 0
            prod(4, 1, "NO COST", gst=12.0, cost=0.0),
            prod(5, 2, "OTHER SHOP", gst=12.0),
        ])
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

    def sell(self, *lines, **kw):
        items = [{"product_id": p, "quantity": q, "unit_price": price, "unit_type": unit} for p, q, price, unit in lines]
        for extra, it in zip(kw.get("gst", []), items):
            if extra is not None:
                it["gst_percentage"] = extra
        r = self.c.post("/sales", json={"items": items, "payment_method": "CASH", "idempotency_key": uuid.uuid4().hex})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def lines(self, sale_id):
        d = self.S()
        try:
            return d.query(models.SaleItem).filter(models.SaleItem.sale_id == sale_id).order_by(models.SaleItem.id).all()
        finally:
            d.close()

    def ret(self, sale_id, item_id, qty):
        r = self.c.post("/returns", json={"sale_id": sale_id, "reason": "x", "items": [{"sale_item_id": item_id, "quantity": qty}]})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    # ---- 1. GST rate
    def test_exempt_medicine_is_billed_at_zero_gst(self):
        sale = self.sell((2, 1, 100.0, "strip"))
        self.assertEqual((sale["tax_amount"], sale["total_amount"]), (0.0, 100.0))
        ln = self.lines(sale["id"])[0]
        self.assertEqual((ln.gst_percentage, ln.gst_amount, ln.cgst_amount, ln.sgst_amount), (0.0, 0.0, 0.0, 0.0))

    def test_mixed_bill_taxes_each_line_at_its_own_rate(self):
        sale = self.sell((1, 2, 100.0, "strip"), (2, 1, 100.0, "strip"))
        self.assertEqual((sale["tax_amount"], sale["total_amount"]), (24.0, 324.0))

    def test_rate_sent_by_the_screen_wins_and_zero_is_respected(self):
        sale = self.sell((1, 1, 100.0, "strip"), gst=[0.0])
        self.assertEqual(self.lines(sale["id"])[0].gst_percentage, 0.0)

    def test_legacy_row_with_one_rate_column_left_at_zero_uses_the_other(self):
        sale = self.sell((3, 1, 100.0, "strip"))
        self.assertEqual(self.lines(sale["id"])[0].gst_percentage, 5.0)

    def test_rate_helpers(self):
        self.assertEqual(tax_reports.gst_value(0, 12), 0.0)
        self.assertEqual(tax_reports.gst_value(None, "", 5), 5.0)
        self.assertEqual(tax_reports.gst_value(None), 12.0)
        P = lambda a, b: SimpleNamespace(gst_percentage=a, gst_rate=b)
        self.assertEqual(tax_reports.product_gst_rate(P(0.0, 0.0)), 0.0)
        self.assertEqual(tax_reports.product_gst_rate(P(None, None), 18.0), 18.0)
        self.assertEqual(tax_reports.product_gst_rate(P(0.0, 12.0)), 12.0)
        self.assertEqual(tax_reports.product_gst_rate(P(5.0, None)), 5.0)

    def test_exempt_medicine_added_through_inventory_keeps_zero(self):
        r = self.c.post("/inventory/batch-add", json={"items": [{"product_name": "ZERO ADD", "batch_number": "Z9", "quantity": 5, "purchase_price": 10.0,
                                                                 "mrp": 20.0, "gst_rate": 0.0, "expiry_date": FUT.isoformat()}]})
        self.assertEqual(r.status_code, 200, r.text)
        d = self.S()
        p = d.query(models.Product).filter(models.Product.product_name == "ZERO ADD").one()
        d.close()
        self.assertEqual((p.gst_rate, p.gst_percentage), (0.0, 0.0))

    # ---- 2. profit
    def test_profit_uses_taxable_value_real_cost_loose_units_and_returns(self):
        sale = self.sell((1, 4, 100.0, "strip"), (2, 1, 100.0, "strip"), (1, 5, 10.0, "loose_tablet"))
        first = self.lines(sale["id"])[0]
        self.ret(sale["id"], first.id, 2)                       # 2 of the 4 strips come back
        pm = self.c.get("/reports/analytics?period=today").json()["profit_metrics"]
        # revenue ex-GST: 2 strips x 100 + exempt 100 + 5 tablets x 10 = 350; cost: 2x60 + 60 + 5 x 6 = 210
        self.assertEqual((pm["gross_revenue"], pm["cogs"], pm["gross_profit"], pm["margin_percent"]), (350.0, 210.0, 140.0, 40.0))
        self.assertEqual((pm["lines_counted"], pm["lines_total"], pm["revenue_without_cost"]), (3, 3, 0.0))

    def test_lines_without_a_purchase_price_are_left_out_not_counted_as_free(self):
        self.sell((1, 1, 100.0, "strip"), (4, 1, 100.0, "strip"))
        pm = self.c.get("/reports/analytics?period=today").json()["profit_metrics"]
        self.assertEqual((pm["gross_revenue"], pm["cogs"], pm["gross_profit"], pm["revenue_without_cost"]), (100.0, 60.0, 40.0, 100.0))
        self.assertEqual((pm["lines_counted"], pm["lines_total"]), (1, 2))

    def test_loss_is_shown_not_clamped_to_zero(self):
        self.sell((1, 1, 50.0, "strip"))                          # sold below cost (60)
        self.assertEqual(self.c.get("/reports/analytics?period=today").json()["profit_metrics"]["gross_profit"], -10.0)

    def test_dashboard_month_profit_uses_the_same_rule(self):
        sale = self.sell((1, 2, 100.0, "strip"), (1, 10, 10.0, "loose_tablet"))
        stats = self.c.get("/dashboard/stats").json()
        today = self.c.get("/reports/analytics?period=today").json()["profit_metrics"]["gross_profit"]
        self.assertEqual(today, 2 * 100 + 100 - (2 * 60 + 60))     # 120
        self.assertEqual((stats["net_profit"], stats["today_profit"]), (today, today))

    # ---- 3. returns-aware sales and GST reports
    def test_gst_summary_subtracts_returns_and_uses_saved_line_tax(self):
        sale = self.sell((1, 4, 100.0, "strip"), (2, 1, 100.0, "strip"))      # 448 + 100 = 548, GST 48
        first = self.lines(sale["id"])[0]
        self.ret(sale["id"], first.id, 1)                                      # refund 112 incl. 12 GST
        g = self.c.get("/reports/gst-financial-summary?preset=current_month").json()
        self.assertEqual((g["gross_sales"], g["total_returns"], g["total_sales"]), (548.0, 112.0, 436.0))
        self.assertEqual((g["gross_output_gst"], g["returned_output_gst"], g["total_output_gst"]), (48.0, 12.0, 36.0))
        self.assertEqual(g["return_count"], 1)
        by_rate = {h["gst_rate"]: h for h in g["hsn_summary"]}
        self.assertEqual((by_rate[12.0]["taxable_amount"], by_rate[12.0]["total_tax"], by_rate[12.0]["quantity"]), (300.0, 36.0, 3))
        self.assertEqual((by_rate[0.0]["taxable_amount"], by_rate[0.0]["total_tax"]), (100.0, 0.0))

    def test_analytics_sales_and_gst_snapshot_are_net_of_returns(self):
        sale = self.sell((1, 2, 100.0, "strip"))                              # 224, GST 24
        self.ret(sale["id"], self.lines(sale["id"])[0].id, 2)                  # fully returned
        a = self.c.get("/reports/analytics?period=today").json()
        sm, gm = a["sales_metrics"], a["gst_metrics"]
        self.assertEqual((sm["total_sales"], sm["total_returns"], sm["net_sales"], sm["return_count"]), (224.0, 224.0, 0.0, 1))
        self.assertEqual((gm["gross_output_gst"], gm["returned_output_gst"], gm["output_gst"]), (24.0, 24.0, 0.0))
        self.assertEqual(a["profit_metrics"]["gross_profit"], 0.0)

    def test_input_gst_comes_from_purchase_invoices_by_invoice_date(self):
        self.c.post("/suppliers", json={"name": "Sup"})
        r = self.c.post("/purchases/manual", json={"supplier_id": 1, "invoice_number": "P-1", "invoice_date": date.today().isoformat(),
                                                    "items": [{"product_name": "DOLO 650", "batch_number": "B1", "expiry_date": FUT.isoformat(),
                                                               "quantity": 10, "purchase_rate": 50, "gst_rate": 12, "mrp": 100}]})
        self.assertEqual(r.status_code, 201, r.text)
        g = self.c.get("/reports/gst-financial-summary?preset=current_month").json()
        self.assertEqual((g["total_purchases"], g["total_input_gst"], g["total_purchase_invoices"]), (560.0, 60.0, 1))
        self.assertEqual(self.c.get("/reports/analytics?period=today").json()["gst_metrics"]["input_gst"], 60.0)

    def test_gstr1_and_gstr3b_are_net_of_returns_and_3b_works_with_purchases(self):
        sale = self.sell((1, 4, 100.0, "strip"))                              # taxable 400, GST 48
        self.ret(sale["id"], self.lines(sale["id"])[0].id, 1)                  # -100 taxable, -12 GST
        self.c.post("/suppliers", json={"name": "Sup"})
        self.c.post("/purchases/manual", json={"supplier_id": 1, "invoice_number": "P-1", "invoice_date": date.today().isoformat(),
                                               "items": [{"product_name": "DOLO 650", "batch_number": "B1", "expiry_date": FUT.isoformat(),
                                                          "quantity": 10, "purchase_rate": 50, "gst_rate": 12, "mrp": 100}]})
        g1 = self.c.get("/api/gst/gstr1-summary").json()
        self.assertEqual((g1["credit_notes"]["count"], g1["credit_notes"]["taxable_value"], g1["credit_notes"]["total_tax"]), (1, 100.0, 12.0))
        self.assertEqual((g1["net_totals"]["taxable_value"], g1["net_totals"]["total_output_tax"]), (300.0, 36.0))
        self.assertEqual((g1["hsn_summary"][0]["taxable_value"], g1["hsn_summary"][0]["gst_amount"], g1["hsn_summary"][0]["total_quantity"]), (300.0, 36.0, 3))
        r3 = self.c.get("/api/gst/gstr3b-summary")
        self.assertEqual(r3.status_code, 200, r3.text)                        # used to crash: PurchaseInvoice has no "subtotal"
        g3 = r3.json()
        self.assertEqual((g3["section_3_1_outward_supplies"]["taxable_value"], g3["section_3_1_outward_supplies"]["total_tax"]), (300.0, 36.0))
        self.assertEqual((g3["section_4_eligible_itc"]["purchase_subtotal"], g3["section_4_eligible_itc"]["total_itc"]), (500.0, 60.0))
        self.assertEqual(g3["section_5_net_liability"]["total_net_payable"], 0.0)

    def test_reports_never_include_another_pharmacys_sales(self):
        self.uid = 2
        self.sell((5, 3, 100.0, "strip"))
        self.uid = 1
        g = self.c.get("/reports/gst-financial-summary?preset=current_month").json()
        self.assertEqual((g["total_sales"], g["total_output_gst"]), (0.0, 0.0))
        self.assertEqual(self.c.get("/reports/analytics?period=today").json()["sales_metrics"]["total_sales"], 0.0)


class TestReportPageWiring(unittest.TestCase):
    def test_reports_page_shows_real_gst_not_a_12_percent_estimate(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "web", "js", "reports.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertNotIn("12 / 112", js)
        self.assertIn("gst_metrics", js)
        self.assertIn("net_sales", js)


if __name__ == "__main__":
    unittest.main()
