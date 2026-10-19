"""
Routes restored from the pre-refactor app.py (routes/restored_routes.py): they exist again and the main pilot
flows work end to end. In-memory SQLite and a test login; nothing touches the live database.
"""
import os
import re
import sys
import unittest
from datetime import date, timedelta

os.environ.setdefault("ENABLE_SCHEDULER", "0")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app as app_module
import crud
import dependencies
import models
from schemas import SaleCreate, SaleItemCreate

ROUTES_FILE = os.path.join(os.path.dirname(__file__), "..", "routes", "restored_routes.py")
EXP = date.today() + timedelta(days=300)


class TestRestoredRoutesExist(unittest.TestCase):
    def test_no_restored_route_returns_404(self):
        src = open(ROUTES_FILE, encoding="utf-8").read()
        paths = re.findall(r'@router\.(get|post|put|delete|patch)\("([^"]+)"', src)
        self.assertGreater(len(paths), 90)
        client = TestClient(app_module.app, raise_server_exceptions=False)
        missing = []
        for method, path in paths:
            if path == "/hsn/rates" and method == "get":
                continue  # public reference list; reads the configured database
            r = getattr(client, method)(re.sub(r"\{[^}]+\}", "1", path), headers={"accept": "application/json"})
            if r.status_code == 404 and "Not Found" in r.text and len(r.text) < 40:
                missing.append(f"{method.upper()} {path}")
        self.assertEqual(missing, [])


class TestPilotFlows(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        # Postgres has GREATEST(); give the in-memory SQLite the same function.
        from sqlalchemy import event

        @event.listens_for(self.engine, "connect")
        def _sqlite_functions(conn, _record):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine)
        db = self.S()
        user = models.User(id=1, shop_name="Pilot Pharmacy", owner_name="Owner", email="o@test.invalid",
                           password="x", default_gst_percentage=12.0)
        db.add(user)
        db.add(models.Product(id=1, user_id=1, category="Allopathy", product_name="DOLO 650", batch_number="D1",
                              quantity=10, unit_price=30.0, purchase_price=20.0, tablets_per_strip=15,
                              expiry_date=EXP))
        db.add(models.Customer(id=1, user_id=1, name="Ramesh", phone="9000000001", pending_amount=0.0))
        db.add(models.Supplier(id=1, user_id=1, name="Gupta Enterprises"))
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

    def _sale(self, payment="CASH", customer=None):
        db = self.S()
        u = db.get(models.User, 1)
        sale = crud.create_sale_transaction(
            db,
            SaleCreate(items=[SaleItemCreate(product_id=1, quantity=2, unit_type="strip", tablets_per_strip=15)],
                       payment_method=payment, discount_type="flat", discount_value=0.0,
                       customer_name=customer),
            1, current_user=u)
        ids = (sale.id, sale.items[0].id)
        db.close()
        return ids

    def test_sale_return_restores_stock(self):
        sale_id, item_id = self._sale()
        r = self.c.post("/billing/returns", json={"sale_id": sale_id, "items": [{"sale_item_id": item_id, "quantity": 1}]})
        self.assertIn(r.status_code, (200, 201), r.text)
        self.assertEqual(self.S().get(models.Product, 1).quantity, 9)  # 10 - 2 sold + 1 returned
        self.assertEqual(self.c.get("/billing/returns/today").status_code, 200)

    def test_khata_settle_and_customer_payment(self):
        sale_id, _ = self._sale(payment="CREDIT", customer="Ramesh")
        r = self.c.post(f"/sales/{sale_id}/settle")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.S().get(models.Sale, sale_id).payment_status, "PAID")
        r = self.c.post("/customers/1/payments", json={"customer_id": 1, "amount_paid": 10.0, "payment_method": "CASH"})
        self.assertIn(r.status_code, (200, 201), r.text)
        self.assertEqual(self.c.get("/customers/1/payments").status_code, 200)

    def test_supplier_payment(self):
        r = self.c.post("/suppliers/1/payments", json={"supplier_id": 1, "amount_paid": 100.0, "payment_method": "UPI"})
        self.assertIn(r.status_code, (200, 201), r.text)
        self.assertEqual(self.c.get("/suppliers/1/payments").status_code, 200)

    def test_printers_and_print_job(self):
        r = self.c.post("/printers/register", json={"device_name": "Counter", "printer_system_name": "BT-58",
                                                     "connection_type": "BLUETOOTH", "paper_size": "58mm"})
        self.assertIn(r.status_code, (200, 201), r.text)
        self.assertEqual(self.c.get("/printers").status_code, 200)
        self.assertEqual(self.c.get("/printers/status").status_code, 200)
        sale_id, _ = self._sale()
        r = self.c.post("/print-jobs", json={"sale_id": sale_id})
        self.assertIn(r.status_code, (200, 201), r.text)

    def test_expiry_marked_returns_and_settings(self):
        self.assertEqual(self.c.get("/expiry/summary").status_code, 200)
        self.assertEqual(self.c.get("/expiry/items").status_code, 200)
        r = self.c.post("/returns/marked", json={"product_id": 1, "return_qty": 1})
        self.assertIn(r.status_code, (200, 201), r.text)
        self.assertEqual(self.c.get("/returns/marked").status_code, 200)
        self.assertEqual(self.c.get("/notifications/settings").status_code, 200)

    def test_inventory_delete_and_restore(self):
        r = self.c.post("/inventory/delete", json={"stock_ids": [1]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(self.S().get(models.Product, 1).is_deleted)
        self.assertEqual(self.c.get("/inventory/deleted").status_code, 200)
        r = self.c.post("/inventory/restore", json={"stock_ids": [1]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(self.S().get(models.Product, 1).is_deleted)

    def test_profile_and_reports(self):
        r = self.c.get("/user/profile")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["shop_name"], "Pilot Pharmacy")
        self.assertEqual(self.c.get("/reports/summary").status_code, 200)

    def test_bulk_purchase_enforces_mrp(self):
        base = {"product_name": "AZEE 500", "batch_number": "AZ9", "quantity": 3, "purchase_price": 90.0,
                "expiry_date": EXP.isoformat(), "gst_rate": 5.0, "hsn_code": "3004"}
        r = self.c.post("/transaction/purchase/bulk", json={"items": [dict(base)]})
        self.assertEqual(r.status_code, 422)
        self.assertIn("MRP_REQUIRED", r.text)
        r = self.c.post("/transaction/purchase/bulk", json={"items": [dict(base, mrp=125.0)]})
        self.assertIn(r.status_code, (200, 201), r.text)
        p = self.S().query(models.Product).filter(models.Product.product_name == "AZEE 500").one()
        self.assertEqual((p.unit_price, p.purchase_price, p.gst_rate), (125.0, 90.0, 5.0))


if __name__ == "__main__":
    unittest.main()
