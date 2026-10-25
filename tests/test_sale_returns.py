"""
Sales returns: ONE return path (crud.process_sale_return_atomic) behind every route.

Before: POST /returns and /sale-returns always crashed (HTTP 500), and POST /billing/returns accepted unlimited repeat
returns (a bill of 4 strips took two returns of 3 and stock rose above what had been sold). These tests pin the rules:
  - the sum of all returns of a line never exceeds what was sold; a refused return writes nothing
  - refund = the line's own total with GST, shared per unit; the completing return gets the exact remainder
  - stock goes back to the batch it was sold from (strips to quantity, loose tablets to loose stock)
  - return_status is "returned" only when every line is fully returned
  - an unpaid credit bill lowers the customer's balance; a settled one does not
In-memory SQLite, sessions like the app's (no autoflush), test login.
"""
import os
import sys
import unittest
import uuid
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


def _prod(pid, uid, name, batch, qty, mrp=100.0, gst=12.0, tabs=10, loose=0):
    return models.Product(id=pid, user_id=uid, category="Allopathy", product_name=name, batch_number=batch, quantity=qty,
                          unit_price=mrp, purchase_price=60.0, tablets_per_strip=tabs, gst_percentage=gst, gst_rate=gst,
                          hsn_code="3004", loose_tablet_stock=loose, expiry_date=date.today() + timedelta(days=300))


class TestSaleReturns(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False)
        db = self.S()
        for uid in (1, 2):
            db.add(models.User(id=uid, shop_name="S%d" % uid, owner_name="O", email="r%d@test.invalid" % uid, password="x",
                               default_gst_percentage=12.0))
        db.add_all([
            _prod(1, 1, "DOLO 650", "D1", 20),
            _prod(2, 1, "DOLO 650", "D2", 20),                      # same medicine, another batch
            _prod(3, 1, "ODD PRICE", "O1", 20, mrp=11.11, gst=5.0),
            _prod(4, 1, "LOOSE MED", "L1", 10, mrp=100.0, tabs=10),
            _prod(5, 2, "OTHER", "X1", 10),
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
        self.n = 0

    def tearDown(self):
        for k in self.overrides:
            app_module.app.dependency_overrides.pop(k, None)

    # ---- helpers
    def sell(self, pid=1, qty=4, price=100.0, batch="D1", unit="strip", disc=0.0, **extra):
        self.n += 1
        body = {"items": [{"product_id": pid, "quantity": qty, "unit_price": price, "unit_type": unit, "batch_number": batch, "discount": disc}],
                "payment_method": "CASH", "idempotency_key": "ret-" + uuid.uuid4().hex}
        body.update(extra)
        r = self.c.post("/sales", json=body)
        self.assertEqual(r.status_code, 201, r.text)
        j = r.json()
        return j["id"], j["items"][0]["id"], j

    def stock(self, pid):
        d = self.S()
        try:
            p = d.get(models.Product, pid)
            return p.quantity, p.loose_tablet_stock
        finally:
            d.close()

    def sale_row(self, sid):
        d = self.S()
        try:
            s = d.get(models.Sale, sid)
            return s.return_status, s.total_returned_amount
        finally:
            d.close()

    def count_returns(self):
        d = self.S()
        try:
            return d.query(models.SaleReturn).count()
        finally:
            d.close()

    def ret(self, sid, item, qty, route="/billing/returns"):
        if route == "/api/sales/returns":
            body = {"sale_id": sid, "reason": "t", "items": [{"sale_item_id": item, "return_quantity": qty}]}
        else:
            body = {"sale_id": sid, "reason": "t", "items": [{"sale_item_id": item, "quantity": qty}]}
        return self.c.post(route, json=body)

    # ---- every route works and ends in the same rules
    def test_all_four_routes_work_and_restore_stock(self):
        for route in ("/billing/returns", "/returns", "/sale-returns", "/api/sales/returns"):
            sid, item, _ = self.sell(qty=2)
            before = self.stock(1)[0]
            r = self.ret(sid, item, 1, route)
            self.assertEqual(r.status_code, 200, "%s: %s" % (route, r.text))
            self.assertEqual(self.stock(1)[0], before + 1, route)

    def test_billing_returns_keeps_its_response_shape(self):
        sid, item, sale = self.sell(qty=2)
        j = self.ret(sid, item, 1).json()
        for k in ("id", "sale_id", "bill_number", "return_amount", "created_at", "items"):
            self.assertIn(k, j)
        self.assertEqual(j["bill_number"], sale["bill_number"])
        self.assertEqual(j["items"][0]["quantity"], 1)

    # ---- cumulative limit
    def test_a_line_can_never_be_returned_more_than_it_was_sold(self):
        sid, item, _ = self.sell(qty=4)
        start = self.stock(1)[0]                                   # 16 after the sale
        self.assertEqual(self.ret(sid, item, 3).status_code, 200)
        self.assertEqual(self.stock(1)[0], start + 3)
        for route in ("/billing/returns", "/returns", "/api/sales/returns"):
            r = self.ret(sid, item, 3, route)
            self.assertEqual(r.status_code, 400, route)
            self.assertIn("Max available return quantity is 1", r.text)
        self.assertEqual(self.stock(1)[0], start + 3)              # not inflated
        self.assertEqual(self.sale_row(sid)[0], "partially_returned")
        self.assertEqual(self.ret(sid, item, 1).status_code, 200)
        self.assertEqual(self.sale_row(sid)[0], "returned")
        r = self.ret(sid, item, 1)
        self.assertEqual(r.status_code, 400)
        self.assertIn("already been fully returned", r.text)
        self.assertEqual(self.stock(1)[0], start + 4)              # exactly what was sold, back in stock

    def test_a_refused_return_writes_nothing(self):
        sid, item, _ = self.sell(qty=4)
        start, rows = self.stock(1)[0], self.count_returns()
        # two lines of one request: the first is fine, the second does not exist
        r = self.c.post("/api/sales/returns", json={"sale_id": sid, "items": [{"sale_item_id": item, "return_quantity": 2}, {"sale_item_id": 99999, "return_quantity": 1}]})
        self.assertEqual(r.status_code, 404)
        # the same line twice in one request adds up: 3 + 3 > 4
        r = self.c.post("/api/sales/returns", json={"sale_id": sid, "items": [{"sale_item_id": item, "return_quantity": 3}, {"sale_item_id": item, "return_quantity": 3}]})
        self.assertEqual(r.status_code, 400)
        self.assertEqual((self.stock(1)[0], self.count_returns(), self.sale_row(sid)), (start, rows, ("completed", 0.0)))

    def test_bad_quantities_are_refused(self):
        sid, item, _ = self.sell(qty=4)
        for q in (0, -1):
            self.assertIn(self.ret(sid, item, q, "/returns").status_code, (400, 422))
            self.assertIn(self.ret(sid, item, q, "/billing/returns").status_code, (400, 422))
        r = self.c.post("/returns", json={"sale_id": sid, "items": [{"sale_item_id": item, "quantity": 1.5}]})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.c.post("/returns", json={"items": []}).status_code, 400)       # no sale id
        self.assertEqual(self.c.post("/api/sales/returns", json={"sale_id": sid, "items": []}).status_code, 400)

    def test_full_return_in_one_request_marks_returned(self):
        sid, item, _ = self.sell(qty=3)
        self.assertEqual(self.ret(sid, item, 3).status_code, 200)
        self.assertEqual(self.sale_row(sid)[0], "returned")

    # ---- refund maths
    def test_refund_is_the_lines_own_total_with_gst_and_discount_shared_per_unit(self):
        sid, item, sale = self.sell(qty=3, price=100.0, disc=30.0)         # (300 - 30) x 1.12 = 302.40
        self.assertAlmostEqual(sale["total_amount"], 302.40, places=2)
        a = self.ret(sid, item, 1).json()["return_amount"]
        b = self.ret(sid, item, 2).json()["return_amount"]
        self.assertAlmostEqual(a, 100.80, places=2)
        self.assertAlmostEqual(a + b, 302.40, places=2)                    # nothing lost, nothing extra
        self.assertAlmostEqual(self.sale_row(sid)[1], 302.40, places=2)

    def test_uneven_paisa_goes_to_the_return_that_completes_the_line(self):
        sid, item, sale = self.sell(pid=3, qty=3, price=11.11, batch="O1")
        total = sale["total_amount"]
        parts = [self.ret(sid, item, 1).json()["return_amount"] for _ in range(3)]
        self.assertAlmostEqual(sum(parts), total, places=2)
        self.assertEqual(parts[0], parts[1])
        self.assertAlmostEqual(parts[2], total - parts[0] - parts[1], places=2)

    # ---- stock goes back to the right place
    def test_stock_returns_to_the_batch_that_was_sold(self):
        sid, item, _ = self.sell(pid=2, qty=2, batch="D2")
        d1, d2 = self.stock(1)[0], self.stock(2)[0]
        self.ret(sid, item, 2)
        self.assertEqual((self.stock(1)[0], self.stock(2)[0]), (d1, d2 + 2))
        db = self.S()
        try:
            self.assertEqual(db.query(models.InventoryTransaction).filter_by(transaction_type="return", product_id=2).count(), 1)
        finally:
            db.close()

    def test_loose_tablets_go_back_to_loose_stock_not_strips(self):
        sid, item, _ = self.sell(pid=4, qty=5, price=10.0, batch="L1", unit="loose_tablet")
        strips, loose = self.stock(4)
        self.assertEqual((strips, loose), (9, 5))                          # one strip opened
        self.ret(sid, item, 2)
        self.assertEqual(self.stock(4), (9, 7))

    # ---- credit customers
    def test_unpaid_credit_bill_lowers_the_balance_and_a_settled_one_does_not(self):
        sid, item, sale = self.sell(qty=2, payment_method="CREDIT", customer_name="Ramesh", customer_phone="9000000001")
        d = self.S()
        try:
            cust = d.query(models.Customer).filter_by(user_id=1, name="Ramesh").first()
            cid, owed = cust.id, cust.pending_amount
        finally:
            d.close()
        self.assertAlmostEqual(owed, 224.0, places=2)
        self.ret(sid, item, 1)
        d = self.S()
        try:
            self.assertAlmostEqual(d.get(models.Customer, cid).pending_amount, 112.0, places=2)
        finally:
            d.close()
        # the customer paid the bill, then returns the rest: the balance must not go below what is really owed
        d = self.S()
        try:
            d.get(models.Sale, sid).payment_status = "PAID"
            d.get(models.Customer, cid).pending_amount = 0.0
            d.commit()
        finally:
            d.close()
        self.ret(sid, item, 1)
        d = self.S()
        try:
            self.assertEqual(d.get(models.Customer, cid).pending_amount, 0.0)
        finally:
            d.close()

    # ---- tenancy
    def test_another_pharmacy_cannot_return_my_bill(self):
        sid, item, _ = self.sell(qty=2)
        before = self.stock(1)[0]
        self.uid = 2
        for route in ("/billing/returns", "/returns", "/api/sales/returns"):
            self.assertEqual(self.ret(sid, item, 1, route).status_code, 404, route)
        self.uid = 1
        self.assertEqual(self.stock(1)[0], before)


if __name__ == "__main__":
    unittest.main()
