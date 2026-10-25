"""
Counter Sale (many walk-in customers on the billing screen): lifecycle, stock and invoice safety.
In-memory SQLite, test login, no live database.

  READY       "Finish customer": saved as a held bill with the COUNTER marker. Never deducts stock, never makes a sale.
  CONVERTED   exactly one regular invoice (normal numbering, normal stock deduction) linked back to the transaction.
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


def _prod(pid, uid, name, batch, days, qty, mrp=100.0, gst=12.0):
    return models.Product(id=pid, user_id=uid, category="Allopathy", product_name=name, batch_number=batch, quantity=qty,
                          unit_price=mrp, purchase_price=60.0, tablets_per_strip=10, gst_percentage=gst, gst_rate=gst,
                          hsn_code="3004", expiry_date=date.today() + timedelta(days=days))


class TestCounterSale(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(self.engine)
        self.S = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False)   # like the app's sessions
        db = self.S()
        for uid in (1, 2):
            db.add(models.User(id=uid, shop_name="S%d" % uid, owner_name="O", email="cs%d@test.invalid" % uid, password="x",
                               default_gst_percentage=12.0))
        db.add_all([
            _prod(1, 1, "DOLO 650", "D1", 300, 10),
            _prod(2, 1, "CROCIN", "C1", 300, 50, mrp=40.0, gst=5.0),
            _prod(3, 1, "OLD STOCK", "O1", -3, 10),
            _prod(4, 2, "OTHER SHOP", "X1", 300, 10),
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

    # ---- helpers
    def line(self, pid=1, qty=2, price=100.0, disc=0.0, batch="D1", pct=None):
        return {"product_id": pid, "quantity": qty, "unit_type": "strip", "unit_price": price, "discount": disc,
                "batch_number": batch, "discount_percent": pct}

    def finish(self, lines, ref="1", txn=None, **extra):
        body = {"txn_id": txn or uuid.uuid4().hex, "ref": ref, "items": lines}
        body.update(extra)
        r = self.c.post("/billing/counter", json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def stock(self, pid):
        d = self.S()
        try:
            return d.get(models.Product, pid).quantity
        finally:
            d.close()

    def sales_count(self):
        d = self.S()
        try:
            return d.query(models.Sale).count()
        finally:
            d.close()

    # ---- lifecycle
    def test_finish_customer_is_ready_and_touches_neither_stock_nor_sales(self):
        t = self.finish([self.line(qty=3)], ref="A7")
        self.assertEqual((t["status"], t["ref"], t["items_count"]), ("READY", "A7", 1))
        self.assertEqual(self.stock(1), 10)
        self.assertEqual(self.sales_count(), 0)

    def test_retry_with_the_same_transaction_id_never_duplicates(self):
        txn = uuid.uuid4().hex
        a = self.finish([self.line()], txn=txn)
        b = self.finish([self.line()], txn=txn)
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(self.c.get("/billing/counter").json()["total"], 1)

    def test_counter_rows_stay_out_of_the_retail_held_bills_list_and_cannot_be_resumed_there(self):
        t = self.finish([self.line()])
        self.assertEqual(self.c.get("/billing/held").json(), [])
        self.assertEqual(self.c.get("/billing/held/count").json()["count"], 0)
        r = self.c.post("/billing/held/%d/resume" % t["id"])
        self.assertEqual(r.status_code, 400)

    def test_list_is_paginated_filtered_and_private(self):
        ids = [self.finish([self.line(qty=1)], ref="R-%d" % i)["id"] for i in range(7)]
        page = self.c.get("/billing/counter", params={"limit": 3, "skip": 3}).json()
        self.assertEqual((page["total"], len(page["items"])), (7, 3))
        self.assertEqual([x["id"] for x in page["items"]], [ids[3], ids[2], ids[1]])      # newest first
        self.assertEqual(self.c.get("/billing/counter", params={"search": "R-5"}).json()["total"], 1)
        self.uid = 2
        self.assertEqual(self.c.get("/billing/counter").json()["total"], 0)
        self.assertEqual(self.c.get("/billing/counter/%d" % ids[0]).status_code, 404)
        self.assertEqual(self.c.post("/billing/counter/%d/convert" % ids[0], json={}).status_code, 404)

    def test_reopen_data_has_the_typed_discount_and_the_live_batch(self):
        t = self.finish([self.line(qty=2, disc=10.0, pct=5.0)])
        d = self.c.get("/billing/counter/%d" % t["id"]).json()
        it = d["items"][0]
        self.assertEqual((it["discount"], it["discount_percent"], it["batch_number"]), (10.0, 5.0, "D1"))
        self.assertEqual((it["live"]["mrp"], it["live"]["stock"], it["live"]["is_expired"]), (100.0, 10, False))

    def test_edited_version_replaces_the_old_one_which_stays_as_history(self):
        a = self.finish([self.line(qty=1)])
        b = self.finish([self.line(qty=4)], replaces_id=a["id"])
        ready = self.c.get("/billing/counter", params={"status": "READY"}).json()
        self.assertEqual([x["id"] for x in ready["items"]], [b["id"]])
        self.assertEqual(self.c.get("/billing/counter", params={"status": "CANCELLED"}).json()["total"], 1)

    # ---- conversion
    def test_convert_makes_one_invoice_deducts_stock_once_and_links_back(self):
        t = self.finish([self.line(1, qty=3, disc=30.0), self.line(2, qty=5, price=40.0, batch="C1")], ref="B2")
        r = self.c.post("/billing/counter/%d/convert" % t["id"], json={"payment_method": "UPI"})
        self.assertEqual(r.status_code, 200, r.text)
        out = r.json()
        self.assertFalse(out["already_converted"])
        self.assertEqual((self.stock(1), self.stock(2)), (7, 45))
        self.assertEqual(self.sales_count(), 1)
        self.assertEqual(out["transaction"]["status"], "CONVERTED")
        self.assertEqual(out["transaction"]["completed_sale_id"], out["sale_id"])
        self.assertEqual(out["transaction"]["invoice_number"], out["bill_number"])
        # (3x100 - 30) x 1.12 + (5x40) x 1.05 = 302.4 + 210.0
        self.assertAlmostEqual(out["total_amount"], 512.4, places=2)
        self.assertAlmostEqual(t["total"], out["total_amount"], places=2)      # the READY total is the invoice amount
        d = self.S()
        try:
            sale = d.get(models.Sale, out["sale_id"])
            self.assertIn("Counter Sale B2", sale.notes)
            self.assertEqual(sale.payment_method, "UPI")
        finally:
            d.close()

    def test_convert_twice_or_after_a_lost_answer_gives_the_same_invoice_and_deducts_once(self):
        t = self.finish([self.line(qty=4)])
        a = self.c.post("/billing/counter/%d/convert" % t["id"], json={}).json()
        b = self.c.post("/billing/counter/%d/convert" % t["id"], json={}).json()
        self.assertTrue(b["already_converted"])
        self.assertEqual((a["sale_id"], a["bill_number"]), (b["sale_id"], b["bill_number"]))
        self.assertEqual(self.stock(1), 6)
        self.assertEqual(self.sales_count(), 1)

    def test_failed_conversion_changes_nothing_and_can_be_retried_after_fixing(self):
        t = self.finish([self.line(qty=3), self.line(3, qty=1, batch="O1")])       # the second line is an expired batch
        r = self.c.post("/billing/counter/%d/convert" % t["id"], json={})
        self.assertIn(r.status_code, (400, 409, 422), r.text)
        self.assertEqual((self.stock(1), self.stock(3), self.sales_count()), (10, 10, 0))
        d = self.c.get("/billing/counter/%d" % t["id"]).json()
        self.assertEqual((d["status"], len(d["items"]), d["items"][0]["quantity"]), ("READY", 2, 3))
        # the cashier removes the expired line and finishes the customer again (replacing the old version)
        t2 = self.finish([self.line(qty=3)], txn=uuid.uuid4().hex, replaces_id=t["id"])
        ok = self.c.post("/billing/counter/%d/convert" % t2["id"], json={})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual((self.stock(1), self.sales_count()), (7, 1))

    def test_two_customers_competing_for_the_same_stock_the_second_is_refused_and_stays_ready(self):
        a = self.finish([self.line(qty=8)], ref="1")
        b = self.finish([self.line(qty=8)], ref="2")
        self.assertEqual(self.c.post("/billing/counter/%d/convert" % a["id"], json={}).status_code, 200)
        r = self.c.post("/billing/counter/%d/convert" % b["id"], json={})
        self.assertGreaterEqual(r.status_code, 400)
        self.assertEqual(self.stock(1), 2)                       # never negative, never deducted twice
        self.assertEqual(self.c.get("/billing/counter/%d" % b["id"]).json()["status"], "READY")

    def test_price_above_mrp_is_refused_and_not_silently_changed(self):
        t = self.finish([self.line(qty=1, price=150.0)])
        r = self.c.post("/billing/counter/%d/convert" % t["id"], json={})
        self.assertEqual(r.status_code, 422)
        self.assertIn("PRICE_ABOVE_MRP", r.text)
        self.assertEqual(self.c.get("/billing/counter/%d" % t["id"]).json()["items"][0]["unit_price"], 150.0)

    def test_totals_equal_a_normal_invoice_for_the_same_lines(self):
        lines = [self.line(1, qty=2, price=100.0, disc=20.0), self.line(2, qty=3, price=40.0, batch="C1", disc=6.0)]
        t = self.finish(lines)
        conv = self.c.post("/billing/counter/%d/convert" % t["id"], json={}).json()
        normal = self.c.post("/sales", json={"items": [dict(product_id=l["product_id"], quantity=l["quantity"], unit_price=l["unit_price"],
                                                           unit_type="strip", batch_number=l["batch_number"], discount=l["discount"])
                                                      for l in lines], "payment_method": "CASH", "idempotency_key": "plain-1"})
        self.assertEqual(normal.status_code, 201, normal.text)
        self.assertAlmostEqual(conv["total_amount"], normal.json()["total_amount"], places=2)
        self.assertAlmostEqual(t["total"], conv["total_amount"], places=2)

    def test_invoice_numbers_are_unique_across_many_conversions(self):
        nums = set()
        for i in range(15):
            t = self.finish([self.line(2, qty=1, price=40.0, batch="C1")], ref=str(i))
            nums.add(self.c.post("/billing/counter/%d/convert" % t["id"], json={}).json()["bill_number"])
        self.assertEqual(len(nums), 15)
        self.assertEqual(self.stock(2), 35)

    # ---- cancel
    def test_cancel_ready_then_it_cannot_be_converted_and_a_converted_one_cannot_be_cancelled(self):
        a = self.finish([self.line()])
        self.assertEqual(self.c.delete("/billing/counter/%d" % a["id"]).json()["status"], "CANCELLED")
        self.assertEqual(self.c.post("/billing/counter/%d/convert" % a["id"], json={}).status_code, 409)
        b = self.finish([self.line()])
        self.c.post("/billing/counter/%d/convert" % b["id"], json={})
        self.assertEqual(self.c.delete("/billing/counter/%d" % b["id"]).status_code, 409)
        self.assertEqual(self.stock(1), 8)                       # only the converted one (2 strips) was deducted

    def test_validation(self):
        for body in ({"txn_id": "short", "ref": "1", "items": [self.line()]}, {"txn_id": uuid.uuid4().hex, "ref": "", "items": [self.line()]},
                     {"txn_id": uuid.uuid4().hex, "ref": "1", "items": []}, {"txn_id": "bad id with spaces!", "ref": "1", "items": [self.line()]}):
            self.assertEqual(self.c.post("/billing/counter", json=body).status_code, 422, body)
        r = self.c.post("/billing/counter", json={"txn_id": uuid.uuid4().hex, "ref": "1", "items": [self.line(pid=999)]})
        self.assertEqual(r.status_code, 404)                      # a medicine that is not in this pharmacy
        r = self.c.post("/billing/counter", json={"txn_id": uuid.uuid4().hex, "ref": "1", "items": [self.line(pid=4, batch="X1")]})
        self.assertEqual(r.status_code, 404)                      # another pharmacy's medicine


if __name__ == "__main__":
    unittest.main()
