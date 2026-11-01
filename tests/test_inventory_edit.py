"""
Live Inventory "Edit" (PATCH /products/{id}/details): partial, ownership-checked, duplicate-safe, and visible after a refresh.
"""
import unittest
from datetime import date, timedelta

import models
from tests import test_document_review as _doc

FUT = (date.today() + timedelta(days=400)).isoformat()
FUT2 = (date.today() + timedelta(days=700)).isoformat()


class TestInventoryEdit(unittest.TestCase):
    setUp, tearDown = _doc.TestDocumentReview.setUp, _doc.TestDocumentReview.tearDown

    def add(self, uid=1, name="GLIMDA MV1", batch="B1", **kw):
        d = self.S()
        p = models.Product(user_id=uid, product_name=name, brand="Acme", category="Tablet", batch_number=batch, quantity=10,
                           unit_price=100.0, purchase_price=60.0, gst_rate=5.0, gst_percentage=5.0, hsn_code="3004",
                           expiry_date=date.today() + timedelta(days=400), image_path="img/keep.jpg", ocr_text="keep ocr",
                           supplier_id=1 if uid == 1 else 2, invoice_number="INV-1", **kw)
        d.add(p)
        d.commit()
        pid = p.id
        d.close()
        return pid

    def row(self, pid):
        d = self.S()
        try:
            return d.get(models.Product, pid)
        finally:
            d.close()

    def patch(self, pid, **body):
        return self.c.patch("/products/%d/details" % pid, json=body)

    def test_mrp_batch_and_expiry_edit_persist_and_nothing_else_changes(self):
        pid = self.add()
        r = self.patch(pid, mrp=120.0, batch_number="NEW-77", expiry_date=FUT2)
        self.assertEqual(r.status_code, 200, r.text)
        p = self.row(pid)                                                     # a fresh read = "after a page refresh"
        self.assertEqual((p.unit_price, p.batch_number, str(p.expiry_date)), (120.0, "NEW-77", FUT2))
        self.assertEqual((p.product_name, p.brand, p.quantity, p.purchase_price, p.gst_rate), ("GLIMDA MV1", "Acme", 10, 60.0, 5.0))
        self.assertEqual((p.image_path, p.ocr_text, p.supplier_id, p.invoice_number), ("img/keep.jpg", "keep ocr", 1, "INV-1"))
        self.assertEqual(p.total_price, 1200.0)
        self.assertEqual(r.json()["batch_number"], "NEW-77")

    def test_every_editable_field(self):
        pid = self.add()
        r = self.patch(pid, product_name="GLIMDA M2", brand="Beta", category="Capsule", composition="Glimepiride",
                       pack_size_label="10 tabs", tablets_per_strip=10, units_per_pack=10, quantity=25,
                       purchase_price=70.0, mrp=130.0, loose_tablet_price=13.0, gst_rate=18.0, hsn_code="30049099")
        self.assertEqual(r.status_code, 200, r.text)
        p = self.row(pid)
        self.assertEqual((p.product_name, p.brand, p.category, p.composition), ("GLIMDA M2", "Beta", "Capsule", "Glimepiride"))
        self.assertEqual((p.pack_size_label, p.tablets_per_strip, p.quantity, p.purchase_price, p.unit_price),
                         ("10 tabs", 10, 25, 70.0, 130.0))
        self.assertEqual((p.gst_rate, p.gst_percentage, p.hsn_code, p.loose_tablet_price), (18.0, 18.0, "30049099", 13.0))

    def test_only_the_edited_batch_changes(self):
        a, b = self.add(batch="A1"), self.add(batch="A2")
        self.assertEqual(self.patch(a, mrp=150.0).status_code, 200)
        self.assertEqual((self.row(a).unit_price, self.row(b).unit_price), (150.0, 100.0))

    def test_other_shops_batch_is_not_reachable(self):
        mine, theirs = self.add(uid=1), self.add(uid=2, name="OTHER")
        self.assertEqual(self.patch(theirs, mrp=999.0).status_code, 404)
        self.assertEqual(self.row(theirs).unit_price, 100.0)
        self.assertEqual(self.patch(999999, mrp=5.0).status_code, 404)
        self.assertEqual(self.patch(mine, mrp=101.0).status_code, 200)

    def test_duplicate_batch_of_the_same_medicine_is_refused(self):
        a, b = self.add(batch="X1"), self.add(batch="X2")
        r = self.patch(b, batch_number="x1")
        self.assertEqual(r.status_code, 409)
        self.assertIn("DUPLICATE_BATCH", r.text)
        self.assertEqual(self.row(b).batch_number, "X2")                       # nothing half-saved
        self.assertEqual(self.patch(b, batch_number="X3").status_code, 200)
        other = self.add(name="DIFFERENT MED", batch="Q1")                     # same batch text on another medicine is fine
        self.assertEqual(self.patch(other, batch_number="X3").status_code, 200)

    def test_mrp_below_cost_needs_confirmation(self):
        pid = self.add()
        r = self.patch(pid, mrp=40.0)
        self.assertEqual(r.status_code, 422)
        self.assertIn("MRP_BELOW_COST", r.text)
        self.assertEqual(self.row(pid).unit_price, 100.0)
        self.assertEqual(self.patch(pid, mrp=40.0, confirm_mrp_below_cost=True).status_code, 200)
        self.assertEqual(self.row(pid).unit_price, 40.0)

    def test_validation(self):
        pid = self.add()
        for body in ({"product_name": "  "}, {"hsn_code": "ab12"}, {"hsn_code": "12"}, {"expiry_date": "not a date"},
                     {"quantity": -1}, {"gst_rate": 99}, {"mrp": 0}):
            self.assertIn(self.patch(pid, **body).status_code, (400, 422), body)
        p = self.row(pid)
        self.assertEqual((p.product_name, p.unit_price, p.quantity, p.hsn_code), ("GLIMDA MV1", 100.0, 10, "3004"))


del _doc

if __name__ == "__main__":
    unittest.main()
