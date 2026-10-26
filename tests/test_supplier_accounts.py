"""
Supplier create / payment / ledger.

Before: POST /suppliers crashed (arguments in the wrong order), POST /supplier-payments crashed (argument mismatch),
the ledger endpoint returned the bare supplier row, and no balance existed anywhere. These tests pin the rules:
  - a supplier can be created (same name again returns the existing one) and edited
  - a payment needs a positive amount and an own supplier
  - the ledger lists purchases, payments and returns with a running balance; a PAID invoice owes nothing
  - another shop's supplier is never visible
In-memory SQLite, sessions like the app's (no autoflush), test login.
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


class TestSupplierAccounts(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False)
        db = self.S()
        for uid in (1, 2):
            db.add(models.User(id=uid, shop_name="S%d" % uid, owner_name="O", email="s%d@test.invalid" % uid, password="x",
                               default_gst_percentage=12.0))
        db.add(models.Product(id=1, user_id=1, category="A", product_name="DOLO", batch_number="D1", quantity=50,
                              unit_price=100.0, purchase_price=60.0, tablets_per_strip=10, gst_percentage=12.0,
                              gst_rate=12.0, hsn_code="3004", expiry_date=date.today() + timedelta(days=300)))
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

    def _supplier(self, name="Sup A", **extra):
        r = self.c.post("/suppliers", json=dict(name=name, **extra))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _purchase(self, sid, inv_no, total, status="UNPAID"):
        body = {"supplier_id": sid, "invoice_number": inv_no, "invoice_date": str(date.today()), "total_amount": total,
                "tax_amount": 0.0, "payment_status": status,
                "items": [{"product_id": 1, "batch_number": "D1", "quantity": 1, "purchase_price": 60.0, "mrp": 100.0,
                           "gst_rate": 12.0, "expiry_date": str(date.today() + timedelta(days=300))}]}
        r = self.c.post("/purchases", json=body)
        self.assertEqual(r.status_code, 200, r.text)

    def test_create_supplier_and_same_name_returns_existing(self):
        a = self._supplier("Sup A", phone="999")
        b = self._supplier("  sup a ")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(a["name"], "Sup A")

    def test_update_supplier(self):
        sid = self._supplier()["id"]
        r = self.c.put(f"/suppliers/{sid}", json={"phone": "12345", "payment_terms": "Net 15"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["phone"], "12345")
        self.assertEqual(r.json()["payment_terms"], "Net 15")

    def test_payment_validation(self):
        sid = self._supplier()["id"]
        for body in ({"supplier_id": sid, "amount_paid": 0}, {"supplier_id": sid, "amount_paid": -5}, {"supplier_id": sid},
                     {"amount_paid": 10}):
            r = self.c.post("/supplier-payments", json=body)
            self.assertEqual(r.status_code, 400, (body, r.text))
        self.assertEqual(self.c.post("/supplier-payments", json={"supplier_id": 999, "amount_paid": 10}).status_code, 404)

    def test_ledger_running_balance(self):
        sid = self._supplier()["id"]
        self._purchase(sid, "INV-1", 1000.0)
        self._purchase(sid, "INV-2", 500.0, status="PAID")        # settled at entry: owes nothing
        r = self.c.post("/supplier-payments", json={"supplier_id": sid, "amount_paid": 400.0, "payment_method": "upi"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["payment_method"], "UPI")
        led = self.c.get(f"/suppliers/{sid}/ledger").json()
        self.assertEqual(led["name"], "Sup A")
        self.assertEqual(led["total_purchased"], 1500.0)
        self.assertEqual(led["total_paid"], 400.0)
        self.assertEqual(led["balance_payable"], 600.0)
        self.assertEqual([e["type"] for e in led["entries"]].count("PURCHASE"), 2)
        self.assertEqual(led["entries"][-1]["balance"], 600.0)

    def test_return_reduces_balance_and_dashboard_matches(self):
        sid = self._supplier()["id"]
        self._purchase(sid, "INV-1", 1000.0)
        r = self.c.post("/purchases/returns", json={"supplier_id": sid, "total_returned_value": 100.0, "reason": "damaged",
                                                    "items": [{"product_id": 1, "batch_number": "D1", "quantity": 1,
                                                               "purchase_price": 60.0}]})
        self.assertEqual(r.status_code, 201, r.text)
        self.c.post("/supplier-payments", json={"supplier_id": sid, "amount_paid": 300.0})
        led = self.c.get(f"/suppliers/{sid}/ledger").json()
        self.assertEqual(led["balance_payable"], 600.0)
        dash = self.c.get("/purchases/dashboard").json()
        self.assertEqual(dash["pending_supplier_payables"], 600.0)

    def test_other_shops_supplier_is_invisible(self):
        self.uid = 2
        other = self._supplier("Other Shop Sup")["id"]
        self.uid = 1
        self.assertEqual(self.c.get(f"/suppliers/{other}/ledger").status_code, 404)
        self.assertEqual(self.c.post("/supplier-payments", json={"supplier_id": other, "amount_paid": 10}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
