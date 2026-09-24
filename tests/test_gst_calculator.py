from datetime import date
import unittest
from services.gst_calculator import (
    calculate_gst_due_dates,
    add_months,
    get_quarter_info,
    calculate_gross_amount,
    calculate_line_discount,
    calculate_taxable_amount,
    calculate_gst_breakdown,
    calculate_line_item_financials,
    calculate_tax_summary,
)


class TestGstCalculator(unittest.TestCase):

    # --------------------------------------------------------------------------
    # 1. GST Return Due Date & Compliance Tests
    # --------------------------------------------------------------------------

    def test_add_months_year_boundary(self):
        d = date(2026, 12, 15)
        res = add_months(d, 1)
        self.assertEqual(res, date(2027, 1, 15))

        d2 = date(2026, 1, 31)
        res2 = add_months(d2, 1)
        self.assertEqual(res2, date(2026, 2, 28))

    def test_get_quarter_info(self):
        q1 = get_quarter_info(date(2026, 5, 10))
        self.assertEqual(q1["quarter_code"], "2026-Q1")
        self.assertEqual(q1["quarter_end"], date(2026, 6, 30))

        q4 = get_quarter_info(date(2026, 2, 10))
        self.assertEqual(q4["quarter_code"], "2025-Q4")
        self.assertEqual(q4["quarter_end"], date(2026, 3, 31))

    def test_unset_gst_config(self):
        res = calculate_gst_due_dates(filing_type=None, ref_date=date(2026, 9, 18))
        self.assertFalse(res["is_configured"])
        self.assertEqual(res["returns"], [])
        self.assertIsNone(res["next_due_return"])

    def test_monthly_filing_due_dates(self):
        res = calculate_gst_due_dates(
            filing_type="monthly",
            state_category="X",
            ref_date=date(2026, 9, 18)
        )
        self.assertTrue(res["is_configured"])
        self.assertEqual(res["filing_type"], "monthly")

        returns = {r["return_type"]: r for r in res["returns"]}
        self.assertIn("GSTR-1", returns)
        self.assertIn("GSTR-3B", returns)

        self.assertEqual(returns["GSTR-1"]["due_date"], "2026-09-11")
        self.assertEqual(returns["GSTR-3B"]["due_date"], "2026-09-20")

    def test_qrmp_category_x_due_dates(self):
        res = calculate_gst_due_dates(
            filing_type="qrmp",
            state_category="X",
            ref_date=date(2026, 9, 18)
        )
        self.assertTrue(res["is_configured"])
        self.assertEqual(res["filing_type"], "qrmp")
        self.assertEqual(res["state_category"], "X")

        returns = {r["return_type"]: r for r in res["returns"]}
        self.assertEqual(returns["GSTR-1"]["due_date"], "2026-10-13")
        self.assertEqual(returns["GSTR-3B"]["due_date"], "2026-10-22")

    def test_qrmp_category_y_due_dates(self):
        res = calculate_gst_due_dates(
            filing_type="qrmp",
            state_category="Y",
            ref_date=date(2026, 9, 18)
        )
        self.assertTrue(res["is_configured"])
        self.assertEqual(res["state_category"], "Y")

        returns = {r["return_type"]: r for r in res["returns"]}
        self.assertEqual(returns["GSTR-3B"]["due_date"], "2026-10-24")

    def test_admin_due_date_override(self):
        overrides = [
            {
                "return_type": "GSTR1",
                "period": "2026-08",
                "extended_due_date": "2026-09-15"
            }
        ]
        res = calculate_gst_due_dates(
            filing_type="monthly",
            ref_date=date(2026, 9, 10),
            overrides=overrides
        )
        returns = {r["return_type"]: r for r in res["returns"]}
        self.assertEqual(returns["GSTR-1"]["due_date"], "2026-09-15")

    # --------------------------------------------------------------------------
    # 2. Line Item GST & Financial Calculation Tests
    # --------------------------------------------------------------------------

    def test_no_discount_intrastate(self):
        # 10 units @ Rs. 100.00, GST 12%
        res = calculate_line_item_financials(
            quantity=10,
            unit_price=100.0,
            discount_percent=0.0,
            allocated_invoice_discount=0.0,
            gst_rate=12.0,
            is_interstate=False
        )
        self.assertEqual(res["gross_amount"], 1000.0)
        self.assertEqual(res["line_discount"], 0.0)
        self.assertEqual(res["taxable_amount"], 1000.0)
        self.assertEqual(res["cgst_rate"], 6.0)
        self.assertEqual(res["cgst_amount"], 60.0)
        self.assertEqual(res["sgst_rate"], 6.0)
        self.assertEqual(res["sgst_amount"], 60.0)
        self.assertEqual(res["igst_amount"], 0.0)
        self.assertEqual(res["total_gst_amount"], 120.0)
        self.assertEqual(res["final_total"], 1120.0)

    def test_line_item_discount_only(self):
        # 5 units @ Rs. 200.00, 10% line discount, GST 18%
        res = calculate_line_item_financials(
            quantity=5,
            unit_price=200.0,
            discount_percent=10.0,
            allocated_invoice_discount=0.0,
            gst_rate=18.0,
            is_interstate=False
        )
        self.assertEqual(res["gross_amount"], 1000.0)
        self.assertEqual(res["line_discount"], 100.0)
        self.assertEqual(res["taxable_amount"], 900.0)
        self.assertEqual(res["cgst_amount"], 81.0)
        self.assertEqual(res["sgst_amount"], 81.0)
        self.assertEqual(res["total_gst_amount"], 162.0)
        self.assertEqual(res["final_total"], 1062.0)

    def test_both_line_and_invoice_discounts(self):
        # Gross = 1000.0, Line Disc = 100.0, Invoice Disc = 50.0 -> Taxable = 850.0
        res = calculate_line_item_financials(
            quantity=10,
            unit_price=100.0,
            discount_percent=10.0,
            allocated_invoice_discount=50.0,
            gst_rate=12.0,
            is_interstate=False
        )
        self.assertEqual(res["gross_amount"], 1000.0)
        self.assertEqual(res["line_discount"], 100.0)
        self.assertEqual(res["allocated_invoice_discount"], 50.0)
        self.assertEqual(res["taxable_amount"], 850.0)
        self.assertEqual(res["cgst_amount"], 51.0)
        self.assertEqual(res["sgst_amount"], 51.0)
        self.assertEqual(res["total_gst_amount"], 102.0)
        self.assertEqual(res["final_total"], 952.0)

    def test_interstate_igst(self):
        # Interstate transaction: 10 units @ 100.0, GST 12% -> IGST 12% (120.0)
        res = calculate_line_item_financials(
            quantity=10,
            unit_price=100.0,
            gst_rate=12.0,
            is_interstate=True
        )
        self.assertEqual(res["cgst_amount"], 0.0)
        self.assertEqual(res["sgst_amount"], 0.0)
        self.assertEqual(res["igst_rate"], 12.0)
        self.assertEqual(res["igst_amount"], 120.0)
        self.assertEqual(res["total_gst_amount"], 120.0)
        self.assertEqual(res["final_total"], 1120.0)

    def test_decimal_prices_and_rounding(self):
        # 3 units @ Rs. 33.33, 5% line discount, GST 5%
        # Gross = 99.99, Line Disc = 5.00 -> Taxable = 94.99
        res = calculate_line_item_financials(
            quantity=3,
            unit_price=33.33,
            discount_percent=5.0,
            gst_rate=5.0
        )
        self.assertEqual(res["gross_amount"], 99.99)
        self.assertEqual(res["line_discount"], 5.0)
        self.assertEqual(res["taxable_amount"], 94.99)
        self.assertEqual(res["cgst_amount"], 2.37)
        self.assertEqual(res["sgst_amount"], 2.37)
        self.assertEqual(res["total_gst_amount"], 4.74)
        self.assertEqual(res["final_total"], 99.73)

    def test_tax_summary_grouping(self):
        item1 = calculate_line_item_financials(quantity=10, unit_price=100, gst_rate=12.0)
        item2 = calculate_line_item_financials(quantity=5, unit_price=200, gst_rate=12.0)
        item3 = calculate_line_item_financials(quantity=2, unit_price=500, gst_rate=18.0)

        summary = calculate_tax_summary([item1, item2, item3])
        summary_by_rate = {s["gst_rate"]: s for s in summary}

        self.assertIn(12.0, summary_by_rate)
        self.assertIn(18.0, summary_by_rate)

        # 12% group: Taxable 2000.0, CGST 120.0, SGST 120.0, Total Tax 240.0
        self.assertEqual(summary_by_rate[12.0]["taxable_value"], 2000.0)
        self.assertEqual(summary_by_rate[12.0]["total_tax"], 240.0)

        # 18% group: Taxable 1000.0, CGST 90.0, SGST 90.0, Total Tax 180.0
        self.assertEqual(summary_by_rate[18.0]["taxable_value"], 1000.0)
        self.assertEqual(summary_by_rate[18.0]["total_tax"], 180.0)


if __name__ == "__main__":
    unittest.main()
