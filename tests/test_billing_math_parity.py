"""
The screen's arithmetic (web/js/billing_math.js, run with Node) must give the same taxable value, GST and total as
the server (crud.create_sale_transaction) for the same bill, to the paisa. 250 random bills with line discounts,
bill discounts and mixed GST rates (including 0%). Skipped when Node is not installed.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import unittest
from datetime import date, timedelta

os.environ.setdefault("ENABLE_SCHEDULER", "0")
os.environ["AI_USAGE_LOG_ENABLED"] = "0"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import crud
import models
from schemas import SaleCreate, SaleItemCreate

JS_RUNNER = r"""
const m = require(process.argv[1]);
const bills = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = bills.map(b => {
  const items = b.lines.map(l => ({ rate: l.rate, quantity: l.qty, discountPercent: l.disc, gstRate: l.gst }));
  const c = m.billComputeLines(items, b.billDisc);
  return { discounts: c.lines.map(l => l.lineDisc), taxable: c.netTaxable, gst: c.totalGst, total: c.grandTotal };
});
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class TestScreenMatchesServer(unittest.TestCase):
    def test_250_random_bills_match_to_the_paisa(self):
        rng = random.Random(20261025)
        bills = []
        for _ in range(250):
            lines = [dict(rate=round(rng.uniform(1, 900), 2), qty=rng.randint(1, 9),
                          disc=rng.choice([0, 0, 2.5, 5, 7.33, 10, 12.5, 18, 33.3]), gst=rng.choice([0, 5, 12, 18, 28]))
                     for _ in range(rng.randint(1, 6))]
            bills.append(dict(lines=lines, billDisc=rng.choice([0, 0, 1, 2.5, 5, 7.5, 10, 12.34])))

        proc = subprocess.run(["node", "-e", JS_RUNNER, os.path.join(ROOT, "web", "js", "billing_math.js")],
                              input=json.dumps(bills), capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        screen = json.loads(proc.stdout)

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(engine, "connect")
        def _fn(conn, _rec):
            conn.create_function("greatest", 2, max)

        models.Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        db.add(models.User(id=1, shop_name="S", owner_name="O", email="o@test.invalid", password="x",
                           default_gst_percentage=12.0))
        db.commit()
        user = db.get(models.User, 1)
        pid = 0
        mismatches = []
        for bill, shown in zip(bills, screen):
            items = []
            for line, rupees in zip(bill["lines"], shown["discounts"]):
                pid += 1
                db.add(models.Product(id=pid, user_id=1, category="A", product_name=f"M{pid}", batch_number=f"B{pid}",
                                      quantity=1000, unit_price=line["rate"], purchase_price=1.0, tablets_per_strip=10,
                                      expiry_date=date.today() + timedelta(days=400), gst_percentage=line["gst"],
                                      gst_rate=line["gst"]))
                items.append(SaleItemCreate(product_id=pid, quantity=line["qty"], unit_price=line["rate"],
                                            unit_type="strip", batch_number=f"B{pid}", discount=rupees,
                                            gst_percentage=line["gst"]))
            db.commit()
            sale = crud.create_sale_transaction(
                db, SaleCreate(items=items, payment_method="CASH",
                               discount_type="percent" if bill["billDisc"] else None, discount_value=bill["billDisc"]),
                1, current_user=user)
            server = (round(sale.total_taxable_value, 2), round(sale.tax_amount, 2), round(sale.total_amount, 2))
            if server != (shown["taxable"], shown["gst"], shown["total"]):
                mismatches.append((bill, shown, server))
        db.close()
        self.assertEqual(mismatches[:2], [], f"{len(mismatches)} of 250 bills differ (first two shown)")


if __name__ == "__main__":
    unittest.main()
