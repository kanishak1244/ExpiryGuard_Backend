"""
GET /billing/catalog: the compact batch list the billing screen searches locally.
  - only the signed-in pharmacy's live (not deleted) batches; another pharmacy's never appear
  - no purchase price in it (billing staff use it)
  - same field names as /billing/search-products; expired batches included (the screen blocks them)
  - gzip when the client accepts it; never cached by shared caches
In-memory SQLite, test login, no live database.
"""
import gzip
import json
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
import crud
import dependencies
import models


def _p(pid, uid, name, batch, days, qty=10, deleted=False):
    return models.Product(id=pid, user_id=uid, category="Allopathy", product_name=name, batch_number=batch, quantity=qty,
                          unit_price=30.0, purchase_price=19.0, tablets_per_strip=10, gst_percentage=12.0, gst_rate=12.0,
                          hsn_code="3004", expiry_date=date.today() + timedelta(days=days), is_deleted=deleted)


class TestBillingCatalog(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine)
        db = self.S()
        for uid in (1, 2):
            db.add(models.User(id=uid, shop_name="S%d" % uid, owner_name="O", email="c%d@test.invalid" % uid, password="x",
                               default_gst_percentage=12.0))
        db.add_all([
            _p(1, 1, "DOLO 650", "D1", 200),
            _p(2, 1, "DOLO 650", "D-OLD", -5),
            _p(3, 1, "CROCIN", "C1", 100, qty=0),
            _p(4, 1, "GONE", "G1", 100, deleted=True),
            _p(5, 2, "OTHER SHOP MED", "X1", 100),
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

    def rows(self, data):
        return [dict(zip(data["columns"], r)) for r in data["rows"]]

    def test_only_this_pharmacys_live_batches(self):
        data = self.c.get("/billing/catalog").json()
        names = {(r["product_name"], r["batch_number"]) for r in self.rows(data)}
        self.assertEqual(names, {("DOLO 650", "D1"), ("DOLO 650", "D-OLD"), ("CROCIN", "C1")})
        self.assertTrue(data["complete"])
        self.assertEqual(data["count"], 3)
        self.uid = 2
        other = self.rows(self.c.get("/billing/catalog").json())
        self.assertEqual([r["product_name"] for r in other], ["OTHER SHOP MED"])

    def test_no_purchase_price_and_search_field_names(self):
        data = self.c.get("/billing/catalog").json()
        self.assertNotIn("purchase_price", data["columns"])
        for k in ("id", "product_name", "batch_number", "quantity", "unit_price", "expiry_date", "gst_percentage", "hsn_code"):
            self.assertIn(k, data["columns"])
        r = self.rows(data)[0]
        self.assertEqual(r["unit_price"], 30.0)
        self.assertRegex(r["expiry_date"], r"^\d{4}-\d{2}-\d{2}")

    def test_gzip_when_accepted_and_not_cacheable(self):
        db = self.S()
        db.add_all([_p(100 + i, 1, "BULK %04d" % i, "B%04d" % i, 300) for i in range(300)])
        db.commit()
        db.close()
        r = self.c.get("/billing/catalog", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("content-encoding"), "gzip")
        self.assertIn("no-store", r.headers.get("cache-control", ""))
        self.assertEqual(r.json()["count"], 303)                 # the client decodes it transparently

    def test_row_limit_marks_incomplete(self):
        old = crud.BILLING_CATALOG_MAX_ROWS
        crud.BILLING_CATALOG_MAX_ROWS = 2
        try:
            data = self.c.get("/billing/catalog").json()
        finally:
            crud.BILLING_CATALOG_MAX_ROWS = old
        self.assertFalse(data["complete"])
        self.assertEqual(data["count"], 2)


if __name__ == "__main__":
    unittest.main()
