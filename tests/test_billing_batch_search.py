"""
Batch cell of the billing grid: GET /billing/search-batches.
  - batches of ONE medicine (exact name) so the cashier never gets a batch of another medicine
  - batch number typed without a medicine: partial match, each row carries its medicine name
  - earliest expiry first, expired last and flagged; other pharmacies' batches never appear; empty query returns nothing
In-memory SQLite, test login, no live database.
"""
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


def _product(pid, user, name, batch, days, qty=10, mrp=25.0, deleted=False):
    return models.Product(id=pid, user_id=user, category="Allopathy", product_name=name, batch_number=batch, quantity=qty,
                          unit_price=mrp, purchase_price=10.0, tablets_per_strip=10, gst_percentage=12.0, gst_rate=12.0,
                          expiry_date=date.today() + timedelta(days=days), is_deleted=deleted)


class TestBatchSearch(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine)
        db = self.S()
        for uid in (1, 2):
            db.add(models.User(id=uid, shop_name="Shop%d" % uid, owner_name="O", email="o%d@test.invalid" % uid, password="x",
                               default_gst_percentage=12.0))
        db.add_all([
            _product(1, 1, "DOLO 650", "D-LATE", 400),
            _product(2, 1, "DOLO 650", "D-SOON", 30),
            _product(3, 1, "DOLO 650", "D-OLD", -20),
            _product(4, 1, "CROCIN 500", "C-1", 200),
            _product(5, 1, "CROCIN 500", "D-9", 90),            # a CROCIN batch whose number also contains "D-"
            _product(6, 2, "DOLO 650", "D-OTHER-SHOP", 100),     # another pharmacy
            _product(7, 1, "DOLO 650", "D-DELETED", 100, deleted=True),
        ])
        db.commit()
        db.close()

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

    def get(self, **params):
        r = self.c.get("/billing/search-batches", params=params)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_batches_of_one_medicine_earliest_expiry_first_expired_last(self):
        rows = self.get(product_name="dolo 650")
        self.assertEqual([r["batch_number"] for r in rows], ["D-SOON", "D-LATE", "D-OLD"])
        self.assertEqual([r["is_expired"] for r in rows], [False, False, True])
        self.assertTrue(all(r["product_name"] == "DOLO 650" for r in rows))

    def test_typed_text_narrows_the_batches_of_that_medicine(self):
        rows = self.get(product_name="DOLO 650", query="soon")
        self.assertEqual([r["batch_number"] for r in rows], ["D-SOON"])

    def test_batch_number_without_a_medicine_returns_matches_with_their_medicine(self):
        rows = self.get(query="D-")
        self.assertEqual({(r["batch_number"], r["product_name"]) for r in rows},
                         {("D-LATE", "DOLO 650"), ("D-SOON", "DOLO 650"), ("D-OLD", "DOLO 650"), ("D-9", "CROCIN 500")})

    def test_never_returns_another_pharmacys_or_a_deleted_batch(self):
        names = {r["batch_number"] for r in self.get(query="D-")} | {r["batch_number"] for r in self.get(product_name="DOLO 650")}
        self.assertNotIn("D-OTHER-SHOP", names)
        self.assertNotIn("D-DELETED", names)

    def test_empty_search_returns_nothing(self):
        self.assertEqual(self.get(query=""), [])
        self.assertEqual(self.get(), [])

    def test_row_has_what_the_screen_needs_to_fill_the_line(self):
        r = self.get(query="C-1")[0]
        for k in ("id", "product_name", "batch_number", "expiry_date", "quantity", "unit_price", "gst_percentage", "tablets_per_strip"):
            self.assertIn(k, r)
        self.assertEqual(r["unit_price"], 25.0)

    def test_limit_is_respected(self):
        self.assertEqual(len(self.get(query="D-", limit=2)), 2)
        r = self.c.get("/billing/search-batches", params={"query": "D-", "limit": 500})
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
