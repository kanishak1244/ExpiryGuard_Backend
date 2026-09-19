from datetime import date
import unittest
from services.gst_calculator import calculate_gst_due_dates, add_months, get_quarter_info


class TestGstCalculator(unittest.TestCase):

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

        # For August 2026 period (ref_date Sep 18):
        # GSTR-1 -> 2026-09-11
        # GSTR-3B -> 2026-09-20
        self.assertEqual(returns["GSTR-1"]["due_date"], "2026-09-11")
        self.assertEqual(returns["GSTR-3B"]["due_date"], "2026-09-20")

    def test_qrmp_category_x_due_dates(self):
        res = calculate_gst_due_dates(
            filing_type="qrmp",
            state_category="X",
            ref_date=date(2026, 9, 18)  # Q2 (Jul-Sep 2026), q_end 2026-09-30
        )
        self.assertTrue(res["is_configured"])
        self.assertEqual(res["filing_type"], "qrmp")
        self.assertEqual(res["state_category"], "X")

        returns = {r["return_type"]: r for r in res["returns"]}
        self.assertEqual(returns["GSTR-1"]["due_date"], "2026-10-13")
        self.assertEqual(returns["GSTR-3B"]["due_date"], "2026-10-22")  # Category X = 22nd

    def test_qrmp_category_y_due_dates(self):
        res = calculate_gst_due_dates(
            filing_type="qrmp",
            state_category="Y",
            ref_date=date(2026, 9, 18)
        )
        self.assertTrue(res["is_configured"])
        self.assertEqual(res["state_category"], "Y")

        returns = {r["return_type"]: r for r in res["returns"]}
        self.assertEqual(returns["GSTR-3B"]["due_date"], "2026-10-24")  # Category Y = 24th

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


if __name__ == "__main__":
    unittest.main()
