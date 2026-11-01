"""
Manual purchase: medicine-master suggestions (GET /purchases/medicine-search).

Pinned rules: the master is every medicine ever registered in the shop (zero stock, expired, no live batch included) plus the
catalog; prefix matches first; a medicine appears once; only reusable data and reference prices come back, never a batch
number, expiry or quantity; other shops' medicines never appear; a large master stays fast.
"""
import time
import unittest
from datetime import date, timedelta

import models
import purchase_entry
from tests import test_document_review as _doc


class TestMedicineMasterSearch(unittest.TestCase):
    setUp, tearDown = _doc.TestDocumentReview.setUp, _doc.TestDocumentReview.tearDown

    def add(self, name, batch="B1", qty=10, uid=1, days=400, rate=20.0, mrp=35.0, brand="Acme", deleted=False):
        d = self.S()
        d.add(models.Product(user_id=uid, product_name=name, brand=brand, category="Tablet", batch_number=batch, quantity=qty,
                             unit_price=mrp, purchase_price=rate, gst_rate=5.0, gst_percentage=5.0, hsn_code="3004",
                             expiry_date=date.today() + timedelta(days=days), is_deleted=deleted))
        d.commit()
        d.close()

    def search(self, q, limit=12, uid=1):
        d = self.S()
        try:
            return purchase_entry.search_medicines(d, uid, q, limit)
        finally:
            d.close()

    def names(self, q, **kw):
        return [m["product_name"] for m in self.search(q, **kw)]

    def test_in_stock_zero_stock_expired_and_no_live_batch_are_all_suggested(self):
        self.add("Antacid M", qty=25)                       # in stock
        self.add("Antacid R", qty=0)                        # out of stock
        self.add("Antacid Plus", qty=40, days=-30)          # only batch expired
        self.add("Antacid Gel", qty=0, days=-90)            # expired AND empty: no live batch at all
        self.assertEqual(sorted(self.names("antacid")), ["Antacid Gel", "Antacid M", "Antacid Plus", "Antacid R"])

    def test_new_medicine_returns_nothing_and_short_text_is_ignored(self):
        self.add("Antacid M")
        self.assertEqual(self.search("zzqx new medicine"), [])
        self.assertEqual(self.search("a"), [])

    def test_prefix_matches_come_first_and_case_is_ignored(self):
        for n in ("Cold Antacid", "ANTACID Z", "Antacid A", "Gastro antacid syrup"):
            self.add(n)
        got = self.names("antac")
        self.assertEqual(got[:2], ["Antacid A", "ANTACID Z"])
        self.assertEqual(set(got[2:]), {"Cold Antacid", "Gastro antacid syrup"})

    def test_one_row_per_medicine_even_with_many_batches(self):
        for i in range(30):
            self.add("Crocin 650", batch="C%d" % i)
        self.assertEqual(self.names("crocin"), ["Crocin 650"])

    def test_selecting_never_carries_batch_expiry_or_quantity(self):
        self.add("Dolo 650", batch="OLD-BATCH-9", qty=77, days=123, rate=21.5, mrp=33.0)
        m = self.search("dolo")[0]
        self.assertEqual((m["last_purchase_rate"], m["mrp"], m["selling_rate"], m["brand"]), (21.5, 33.0, 33.0, "Acme"))
        self.assertEqual(m["batches"], [])
        flat = str(m)
        for secret in ("OLD-BATCH-9", "77", "expiry", "quantity"):
            self.assertNotIn(secret, flat.replace("'selling_rate'", ""), secret)
        for key in ("batch_number", "expiry_date", "quantity", "free_quantity"):
            self.assertNotIn(key, m)

    def test_reference_price_comes_from_the_newest_record_that_has_one(self):
        self.add("Rate Med", batch="R1", rate=10.0, mrp=20.0)
        self.add("Rate Med", batch="R2", rate=0.0, mrp=0.0)           # newest record has no prices
        m = self.search("rate med")[0]
        self.assertEqual((m["last_purchase_rate"], m["mrp"]), (10.0, 20.0))

    def test_other_shops_and_deleted_records_never_appear_but_the_catalog_does(self):
        self.add("Secret Med", uid=2)
        self.add("Deleted Med", deleted=True)
        d = self.S()
        d.add(models.MedicineCatalog(product_name="Catalogonly 500", brand="Cat Co", category="allopathy", default_price=12.0))
        d.commit()
        d.close()
        self.assertEqual(self.names("secret"), [])
        self.assertEqual(self.names("deleted med"), [])
        got = self.search("catalogonly")
        self.assertEqual((got[0]["source"], got[0]["mrp"], got[0]["batches"]), ("catalog", 12.0, []))

    def test_shop_medicine_hides_the_same_name_from_the_catalog(self):
        self.add("Same Name")
        d = self.S()
        d.add(models.MedicineCatalog(product_name="same name", category="allopathy", default_price=1.0))
        d.commit()
        d.close()
        self.assertEqual(len(self.search("same name")), 1)

    def test_wildcard_characters_are_literal(self):
        self.add("Percent 5% Med")
        self.add("Percent Other")
        self.assertEqual(self.names("5%"), ["Percent 5% Med"])
        self.assertEqual(self.names("%%"), [])

    def test_limit_is_respected(self):
        for i in range(40):
            self.add("Bulk Med %02d" % i)
        self.assertEqual(len(self.search("bulk", limit=12)), 12)

    def test_large_master_stays_fast(self):
        d = self.S()
        rows = [dict(user_id=1, product_name="Medname %05d" % i, brand="Brand %d" % (i % 97), category="Tablet",
                     batch_number="B%d" % i, quantity=i % 5, unit_price=10.0, purchase_price=5.0, gst_rate=5.0,
                     gst_percentage=5.0, hsn_code="3004", expiry_date=date.today() + timedelta(days=300), is_deleted=False)
                for i in range(50000)]
        d.bulk_insert_mappings(models.Product, rows)
        d.commit()
        d.close()
        self.add("Antacid Needle")
        t0 = time.perf_counter()
        got = self.names("antacid")
        took = time.perf_counter() - t0
        self.assertEqual(got, ["Antacid Needle"])
        t0 = time.perf_counter()
        many = self.search("medname 004")
        took2 = time.perf_counter() - t0
        self.assertEqual(len(many), 12)
        print("50,000 medicines (SQLite, no trigram index): rare term %.0f ms, common term %.0f ms" % (took * 1000, took2 * 1000))
        self.assertLess(max(took, took2), 1.5)


del _doc

if __name__ == "__main__":
    unittest.main()
