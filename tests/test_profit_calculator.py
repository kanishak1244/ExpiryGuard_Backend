import unittest
from services.profit_calculator import calculate_today_profit


class TestProfitCalculator(unittest.TestCase):
    """
    Unit test suite for DawaiFlow Profit Today calculation engine.
    Ensures missing cost-price items are excluded and returns/net-quantities are handled accurately.
    """

    def test_standard_profit_calculation(self):
        items = [
            {"unit_price": 100.0, "cost_price": 70.0, "quantity": 2, "returned_quantity": 0, "total_price": 200.0},
            {"unit_price": 50.0, "cost_price": 30.0, "quantity": 5, "returned_quantity": 0, "total_price": 250.0}
        ]
        # Item 1 profit: 200 - (70 * 2) = 60.0
        # Item 2 profit: 250 - (30 * 5) = 100.0
        # Total profit: 160.0
        self.assertEqual(calculate_today_profit(items), 160.0)

    def test_missing_cost_price_excluded(self):
        items = [
            {"unit_price": 100.0, "cost_price": 70.0, "quantity": 1, "returned_quantity": 0, "total_price": 100.0},
            {"unit_price": 150.0, "cost_price": None, "quantity": 2, "returned_quantity": 0, "total_price": 300.0},  # Excluded!
            {"unit_price": 200.0, "cost_price": 0.0, "quantity": 1, "returned_quantity": 0, "total_price": 200.0}   # Excluded!
        ]
        # Only item 1 contributes: 100 - 70 = 30.0
        self.assertEqual(calculate_today_profit(items), 30.0)

    def test_returned_quantities_handling(self):
        items = [
            {"unit_price": 100.0, "cost_price": 60.0, "quantity": 5, "returned_quantity": 2, "total_price": 300.0}
        ]
        # Net quantity: 3. Line total: 300. Cost total: 60 * 3 = 180. Profit: 120.0
        self.assertEqual(calculate_today_profit(items), 120.0)

    def test_empty_or_zero_quantity(self):
        self.assertEqual(calculate_today_profit([]), 0.0)
        items = [{"unit_price": 100.0, "cost_price": 50.0, "quantity": 0, "returned_quantity": 0}]
        self.assertEqual(calculate_today_profit(items), 0.0)


if __name__ == "__main__":
    unittest.main()
