"""
Purchase Management screen: GET /purchases/list, GET /purchases/detail/{id} and the page wiring.

Pinned rules:
  - the list shows only this shop's saved purchases, newest first, one server-side page at a time
  - search (supplier / invoice no. / PUR-00012), supplier, status and date filters work
  - paid / outstanding are given only where certain (PAID, UNPAID); PARTIAL is null, never guessed
  - the summary payables equal the supplier ledger / dashboard numbers
  - listing or opening a purchase never changes stock or writes anything
  - Add Inventory opens purchases.html; the page offers the three actions
In-memory SQLite, sessions like the app's (no autoflush), test login.
"""
import os
import re
import sys
import unittest
from datetime import date, timedelta

os.environ.setdefault("ENABLE_SCHEDULER", "0")
os.environ["AI_USAGE_LOG_ENABLED"] = "0"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app as app_module
import dependencies
import models


class TestPurchaseManagement(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False)
        db = self.S()
        for uid in (1, 2):
            db.add(models.User(id=uid, shop_name="S%d" % uid, owner_name="O", email="pm%d@test.invalid" % uid, password="x",
                               default_gst_percentage=12.0))
        db.add(models.Product(id=1, user_id=1, category="A", product_name="DOLO 650", batch_number="D1", quantity=50,
                              unit_price=100.0, purchase_price=60.0, tablets_per_strip=10, gst_percentage=12.0,
                              gst_rate=12.0, hsn_code="3004", expiry_date=date.today() + timedelta(days=300)))
        db.add(models.Supplier(id=1, user_id=1, name="Alpha Pharma"))
        db.add(models.Supplier(id=2, user_id=1, name="Beta Distributors"))
        db.add(models.Supplier(id=3, user_id=2, name="Other Shop Supplier"))
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

    def _purchase(self, sid, inv_no, total, status="UNPAID", days_ago=0, lines=1):
        body = {"supplier_id": sid, "invoice_number": inv_no, "invoice_date": str(date.today() - timedelta(days=days_ago)),
                "total_amount": total, "tax_amount": round(total * 0.1, 2), "payment_status": status,
                "items": [{"product_id": 1, "batch_number": "D1", "quantity": 1, "purchase_price": 60.0, "mrp": 100.0,
                           "gst_rate": 12.0, "expiry_date": str(date.today() + timedelta(days=300))}] * lines}
        r = self.c.post("/purchases", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def _stock(self):
        d = self.S()
        try:
            return d.get(models.Product, 1).quantity
        finally:
            d.close()

    def test_saved_purchases_appear_newest_first_with_supplier_and_item_count(self):
        self._purchase(1, "A-1", 1000.0, days_ago=5)
        self._purchase(2, "B-1", 500.0, status="PAID", days_ago=1, lines=2)
        res = self.c.get("/purchases/list").json()
        self.assertEqual(res["total"], 2)
        self.assertEqual([r["invoice_number"] for r in res["items"]], ["B-1", "A-1"])
        first = res["items"][0]
        self.assertEqual(first["supplier_name"], "Beta Distributors")
        self.assertEqual(first["items_count"], 2)
        self.assertEqual(first["voucher_no"], "PUR-%05d" % first["id"])

    def test_paid_and_outstanding_only_where_certain(self):
        self._purchase(1, "P", 100.0, status="PAID")
        self._purchase(1, "U", 200.0, status="UNPAID")
        self._purchase(1, "H", 300.0, status="PARTIAL")
        by = {r["invoice_number"]: r for r in self.c.get("/purchases/list").json()["items"]}
        self.assertEqual((by["P"]["paid_amount"], by["P"]["outstanding_amount"]), (100.0, 0.0))
        self.assertEqual((by["U"]["paid_amount"], by["U"]["outstanding_amount"]), (0.0, 200.0))
        self.assertEqual((by["H"]["paid_amount"], by["H"]["outstanding_amount"]), (None, None))

    def test_search_and_filters(self):
        a = self._purchase(1, "INV-ALPHA-9", 1000.0, days_ago=40)
        self._purchase(2, "XB-77", 500.0, status="PAID", days_ago=2)
        get = lambda qs: self.c.get("/purchases/list?" + qs).json()
        self.assertEqual(get("q=alpha")["total"], 1)                       # supplier name
        self.assertEqual(get("q=xb-77")["total"], 1)                       # invoice number
        self.assertEqual(get("q=PUR-%05d" % a)["items"][0]["invoice_number"], "INV-ALPHA-9")   # internal reference
        self.assertEqual(get("supplier_id=2")["total"], 1)
        self.assertEqual(get("status=paid")["total"], 1)
        self.assertEqual(get("date_from=%s" % (date.today() - timedelta(days=10)))["total"], 1)
        self.assertEqual(get("date_to=%s" % (date.today() - timedelta(days=10)))["total"], 1)
        self.assertEqual(get("q=nothing-like-this")["total"], 0)
        self.assertEqual(self.c.get("/purchases/list?date_from=2026-02-01&date_to=2026-01-01").status_code, 400)
        self.assertEqual(self.c.get("/purchases/list?status=bogus").status_code, 422)
        self.assertEqual(self.c.get("/purchases/list?page_size=1000").status_code, 422)

    def test_pagination_is_server_side(self):
        for i in range(5):
            self._purchase(1, "N-%d" % i, 10.0 + i, days_ago=i)
        p1 = self.c.get("/purchases/list?page=1&page_size=2").json()
        p3 = self.c.get("/purchases/list?page=3&page_size=2").json()
        self.assertEqual((p1["total"], len(p1["items"]), p1["page"]), (5, 2, 1))
        self.assertEqual(len(p3["items"]), 1)
        self.assertEqual(p1["summary"]["documents"], 5)                       # summary covers all filtered rows, not the page
        self.assertEqual(self.c.get("/purchases/list?page=9&page_size=2").json()["items"], [])

    def test_summary_matches_ledger_and_dashboard(self):
        self._purchase(1, "I-1", 1000.0)
        self._purchase(2, "I-2", 400.0)
        self._purchase(2, "I-3", 999.0, status="PAID")
        self.c.post("/supplier-payments", json={"supplier_id": 1, "amount_paid": 1000.0})
        s = self.c.get("/purchases/list").json()["summary"]
        led1 = self.c.get("/suppliers/1/ledger").json()["balance_payable"]
        led2 = self.c.get("/suppliers/2/ledger").json()["balance_payable"]
        self.assertEqual((led1, led2), (0.0, 400.0))
        self.assertEqual(s["outstanding_payables"], 400.0)
        self.assertEqual(s["suppliers_with_balance"], 1)
        self.assertEqual(s["total_value"], 2399.0)
        self.assertEqual(s["outstanding_payables"], self.c.get("/purchases/dashboard").json()["pending_supplier_payables"])

    def test_other_shops_purchases_are_invisible(self):
        mine = self._purchase(1, "MINE", 100.0)
        self.uid = 2
        self.assertEqual(self.c.get("/purchases/list").json()["total"], 0)
        self.assertEqual(self.c.get("/purchases/detail/%d" % mine).status_code, 404)
        self.assertEqual(self.c.get("/purchases/list?supplier_id=1").json()["total"], 0)

    def test_requires_login(self):
        app_module.app.dependency_overrides.pop(dependencies.get_current_user, None)
        c = TestClient(app_module.app, raise_server_exceptions=False)
        self.assertIn(c.get("/purchases/list").status_code, (401, 403))
        self.assertIn(c.get("/purchases/detail/1").status_code, (401, 403))

    def test_viewing_never_changes_stock_or_ledger(self):
        pid = self._purchase(1, "V-1", 100.0)
        stock = self._stock()
        d = self.S()
        counts = (d.query(models.PurchaseInvoice).count(), d.query(models.InventoryTransaction).count(),
                  d.query(models.SupplierPayment).count())
        d.close()
        for _ in range(3):
            self.assertEqual(self.c.get("/purchases/list").status_code, 200)
            self.assertEqual(self.c.get("/purchases/detail/%d" % pid).status_code, 200)
        d = self.S()
        after = (d.query(models.PurchaseInvoice).count(), d.query(models.InventoryTransaction).count(),
                 d.query(models.SupplierPayment).count())
        d.close()
        self.assertEqual(self._stock(), stock)
        self.assertEqual(after, counts)

    def test_detail_has_medicine_names(self):
        pid = self._purchase(1, "D-1", 100.0)
        d = self.c.get("/purchases/detail/%d" % pid).json()
        self.assertEqual(d["supplier_name"], "Alpha Pharma")
        self.assertEqual(d["items"][0]["product_name"], "DOLO 650")
        self.assertEqual(d["items"][0]["batch_number"], "D1")


class TestPurchaseManagementPage(unittest.TestCase):
    """Static wiring checks of the web files (the screen itself is exercised in the browser)."""

    def _read(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_add_inventory_opens_purchase_management_not_a_workflow(self):
        js = self._read("web/js/add_inventory_flow.js")
        m = re.search(r"function openAddInventoryModal\(\) \{(.*?)\n\}", js, re.S)
        self.assertIsNotNone(m)
        self.assertIn("purchases.html", m.group(1))
        self.assertNotIn("createAddInventoryModalDOM", m.group(1))
        self.assertNotIn("showSearchMedicineStep", m.group(1))
        self.assertIn("function openAddInventoryWorkflow(", js)

    def test_page_has_the_three_actions_in_order_and_list(self):
        html = self._read("web/purchases.html")
        order = [html.index(x) for x in ("Scan / Upload Bill", "Search Medicine", "Direct Excel / CSV Import")]
        self.assertEqual(order, sorted(order))
        self.assertLess(order[-1], html.index('id="pm-tbody"'))
        for needle in ("Purchase Management", "Manage supplier invoices, add medicines to inventory, and track purchase history.",
                       "pmScanBill()", "pmSearchMedicine()", "pmImportSheet()", "Clear filters", "js/purchases_page.js"):
            self.assertIn(needle, html)

    def test_actions_open_existing_workflows(self):
        js = self._read("web/js/purchases_page.js")
        self.assertIn("documents.html", js)
        self.assertIn("openAddInventoryWorkflow('search')", js)
        self.assertIn("openAddInventoryWorkflow('import')", js)
        self.assertIn("/purchases/list", js)
        self.assertIn("beforeunload", js)

    def test_every_page_loads_the_new_script_versions(self):
        for name in os.listdir(os.path.join(ROOT, "web")):
            if name.endswith(".html") and name != "purchases.html":
                html = self._read("web/" + name)
                for script in ("add_inventory_flow", "nav"):
                    for ver in re.findall(r"js/%s\.js\?v=([0-9.]+)" % script, html):
                        self.assertEqual(ver, "9.5", (name, script))


if __name__ == "__main__":
    unittest.main()
