import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import crud
from models import Base, Product, User
from crud import create_sale_transaction, get_billing_search_products, is_batch_expired, local_today
from schemas import SaleCreate, SaleItemCreate


class TestExpiryRule(unittest.TestCase):
    def test_date_rule_is_the_default(self):
        self.assertEqual(crud.EXPIRY_RULE, "date")
        today = date(2026, 10, 16)
        self.assertFalse(is_batch_expired(date(2026, 10, 16), today))  # sellable on its expiry date
        self.assertTrue(is_batch_expired(date(2026, 10, 15), today))
        self.assertTrue(is_batch_expired(date(2026, 10, 1), today))
        self.assertFalse(is_batch_expired(date(2027, 3, 1), today))
        self.assertTrue(is_batch_expired("2026-09-30", today))         # ISO strings from search rows

    def test_month_end_rule_when_switched_on(self):
        old = crud.EXPIRY_RULE
        crud.EXPIRY_RULE = "month_end"
        try:
            today = date(2026, 10, 16)
            self.assertFalse(is_batch_expired(date(2026, 10, 1), today))  # stored as 1st: valid all October
            self.assertTrue(is_batch_expired(date(2026, 9, 30), today))
        finally:
            crud.EXPIRY_RULE = old

    def test_missing_expiry_is_not_treated_as_expired(self):
        self.assertFalse(is_batch_expired(None))


class TestExpiredBatchBlockAndFefo(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.user = User(id=1, shop_name="Test Pharma", owner_name="Tester", email="t@t.com",
                         password="pw", default_gst_percentage=12.0)
        self.session.add(self.user)
        today = local_today()
        self.session.add_all([
            Product(id=1, user_id=1, product_name="DOLO 650", category="Allopathy", batch_number="OLD1",
                    expiry_date=today - timedelta(days=1), quantity=5, unit_price=30.0, tablets_per_strip=15),
            Product(id=2, user_id=1, product_name="DOLO 650", category="Allopathy", batch_number="NOW1",
                    expiry_date=today + timedelta(days=20), quantity=5, unit_price=30.0, tablets_per_strip=15),
            Product(id=3, user_id=1, product_name="DOLO 650", category="Allopathy", batch_number="LATE1",
                    expiry_date=date(today.year + 1, 6, 1), quantity=5, unit_price=30.0, tablets_per_strip=15),
            Product(id=4, user_id=1, product_name="DOLO 650", category="Allopathy", batch_number="EMPTY",
                    expiry_date=today + timedelta(days=5), quantity=0, unit_price=30.0, tablets_per_strip=15),
        ])
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def _sale(self, product_id):
        return SaleCreate(
            items=[SaleItemCreate(product_id=product_id, quantity=1, unit_price=30.0, unit_type="strip",
                                  tablets_per_strip=15)],
            payment_method="CASH", discount_type="flat", discount_value=0.0,
        )

    def test_selling_expired_batch_is_refused_and_stock_unchanged(self):
        with self.assertRaises(HTTPException) as ctx:
            create_sale_transaction(db=self.session, sale_data=self._sale(1), user_id=1, current_user=self.user)
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("Expired batch cannot be sold", ctx.exception.detail)
        self.assertIn("OLD1", ctx.exception.detail)
        self.assertEqual(self.session.get(Product, 1).quantity, 5)

    def test_valid_batch_sells(self):
        bill = create_sale_transaction(db=self.session, sale_data=self._sale(2), user_id=1, current_user=self.user)
        self.assertIsNotNone(bill)
        self.assertEqual(self.session.get(Product, 2).quantity, 4)

    def test_search_puts_expired_last_and_marks_fefo_batch(self):
        rows = get_billing_search_products(self.session, user_id=1, query="dolo", limit=10)
        by_batch = {r["batch_number"]: r for r in rows}
        self.assertTrue(by_batch["OLD1"]["is_expired"])
        self.assertFalse(by_batch["NOW1"]["is_expired"])
        # FEFO: earliest non-expired batch WITH stock (NOW1); not the expired one, not the empty one
        self.assertTrue(by_batch["NOW1"]["fefo_first"])
        self.assertFalse(by_batch["LATE1"]["fefo_first"])
        self.assertFalse(by_batch["OLD1"]["fefo_first"])
        self.assertFalse(by_batch["EMPTY"]["fefo_first"])
        self.assertEqual(sum(1 for r in rows if r["fefo_first"]), 1)
        self.assertEqual(rows[-1]["batch_number"], "OLD1")  # expired batch listed last


if __name__ == "__main__":
    unittest.main()
