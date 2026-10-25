"""
Held bills: hold a bill, list it, resume it (the resume route used to return HTTP 500 because its response model
did not match what crud.resume_held_bill returns). In-memory SQLite, test login, no live database.
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


class TestHeldBillResume(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine)
        db = self.S()
        db.add(models.User(id=1, shop_name="Shop", owner_name="O", email="o@test.invalid", password="x",
                           default_gst_percentage=12.0))
        db.add(models.Product(id=1, user_id=1, category="Allopathy", product_name="DOLO 650", batch_number="D1",
                              quantity=20, unit_price=30.0, purchase_price=20.0, tablets_per_strip=15,
                              expiry_date=date.today() + timedelta(days=300), gst_percentage=12.0))
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

    def test_hold_then_resume_returns_the_bill_and_its_lines(self):
        payload = {
            "customer_name": "Ramesh", "payment_method": "CASH", "discount_value": 0.0,
            "items": [{"product_id": 1, "product_name": "DOLO 650", "quantity": 2, "unit_type": "strip",
                       "unit_price": 30.0, "discount": 10.0, "batch_number": "D1", "gst_percentage": 12.0}],
        }
        r = self.c.post("/billing/held", json=payload)
        self.assertIn(r.status_code, (200, 201), r.text)
        held_id = r.json()["id"]

        listed = self.c.get("/billing/held")
        self.assertEqual(listed.status_code, 200, listed.text)

        res = self.c.post(f"/billing/held/{held_id}/resume")
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["held_bill"]["id"], held_id)
        self.assertEqual(len(body["items"]), 1)
        item = body["items"][0]
        self.assertEqual((item["product_id"], item["requested_quantity"], item["batch_number"]), (1, 2, "D1"))
        self.assertEqual(item["discount"], 10.0)
        self.assertTrue(item["is_sufficient"])
        self.assertFalse(body["has_stock_shortage"])

    def test_a_held_bill_can_be_loaded_again_until_it_is_saved(self):
        # Resuming only loads the lines into the cart; the held bill stays HELD until the sale is saved.
        payload = {"items": [{"product_id": 1, "quantity": 1, "unit_price": 30.0}]}
        held_id = self.c.post("/billing/held", json=payload).json()["id"]
        self.assertEqual(self.c.post(f"/billing/held/{held_id}/resume").status_code, 200)
        self.assertEqual(self.c.post(f"/billing/held/{held_id}/resume").status_code, 200)
        self.assertEqual(self.c.post("/billing/held/99999/resume").status_code, 404)


if __name__ == "__main__":
    unittest.main()
