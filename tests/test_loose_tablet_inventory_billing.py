import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Product, User
from crud import deduct_product_stock, create_sale_transaction
from schemas import SaleCreate, SaleItemCreate

class TestLooseTabletInventoryBilling(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

        # Dummy shop user
        self.user = User(
            id=1,
            shop_name="Test Pharma",
            owner_name="Tester",
            email="test@test.com",
            password="pw",
            default_gst_percentage=12.0,
        )
        self.session.add(self.user)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_case_a_989_strips_sell_4_loose(self):
        """Case A: 989 strips * 10 tablets/strip, sell 4 loose tablets.
        Result: 988 strips, 6 loose tablets. Total = 9886.
        """
        prod = Product(
            user_id=1,
            product_name="CILACAR 5",
            category="Allopathy",
            expiry_date=date(2027, 12, 31),
            batch_number="B1",
            quantity=989,
            loose_tablet_stock=0,
            tablets_per_strip=10,
            unit_price=100.0,
            loose_tablet_price=10.0,
        )
        self.session.add(prod)
        self.session.commit()

        res = deduct_product_stock(
            product=prod,
            quantity=4,
            unit_type="loose_tablet",
            tablets_per_strip_override=10,
        )
        self.session.commit()
        self.session.refresh(prod)

        self.assertEqual(prod.quantity, 988)
        self.assertEqual(prod.loose_tablet_stock, 6)
        self.assertEqual(prod.quantity * 10 + prod.loose_tablet_stock, 9886)
        self.assertEqual(res["remaining_strips"], 988)
        self.assertEqual(res["remaining_loose"], 6)
        self.assertEqual(res["total_remaining_tablets"], 9886)

    def test_case_b_1_strip_sell_10_loose(self):
        """Case B: 1 strip * 10 tablets/strip, sell 10 loose tablets.
        Result: 0 strips, 0 loose tablets. Total = 0.
        """
        prod = Product(
            user_id=1,
            product_name="CILACAR 5",
            category="Allopathy",
            expiry_date=date(2027, 12, 31),
            batch_number="B2",
            quantity=1,
            loose_tablet_stock=0,
            tablets_per_strip=10,
            unit_price=100.0,
        )
        self.session.add(prod)
        self.session.commit()

        deduct_product_stock(
            product=prod,
            quantity=10,
            unit_type="loose_tablet",
            tablets_per_strip_override=10,
        )
        self.session.commit()
        self.session.refresh(prod)

        self.assertEqual(prod.quantity, 0)
        self.assertEqual(prod.loose_tablet_stock, 0)
        self.assertEqual(prod.quantity * 10 + prod.loose_tablet_stock, 0)

    def test_case_c_1_strip_sell_11_loose_fail(self):
        """Case C: 1 strip * 10 tablets/strip, sell 11 loose tablets.
        Result: Fails with Insufficient stock HTTPException (400).
        """
        prod = Product(
            user_id=1,
            product_name="CILACAR 5",
            category="Allopathy",
            expiry_date=date(2027, 12, 31),
            batch_number="B3",
            quantity=1,
            loose_tablet_stock=0,
            tablets_per_strip=10,
            unit_price=100.0,
        )
        self.session.add(prod)
        self.session.commit()

        with self.assertRaises(HTTPException) as cm:
            deduct_product_stock(
                product=prod,
                quantity=11,
                unit_type="loose_tablet",
                tablets_per_strip_override=10,
            )
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Insufficient", cm.exception.detail)

    def test_case_d_0_strips_5_loose_sell_4(self):
        """Case D: 0 strips, 5 loose tablets, sell 4 loose tablets.
        Result: 0 strips, 1 loose tablet.
        """
        prod = Product(
            user_id=1,
            product_name="CILACAR 5",
            category="Allopathy",
            expiry_date=date(2027, 12, 31),
            batch_number="B4",
            quantity=0,
            loose_tablet_stock=5,
            tablets_per_strip=10,
            unit_price=100.0,
        )
        self.session.add(prod)
        self.session.commit()

        deduct_product_stock(
            product=prod,
            quantity=4,
            unit_type="loose_tablet",
            tablets_per_strip_override=10,
        )
        self.session.commit()
        self.session.refresh(prod)

        self.assertEqual(prod.quantity, 0)
        self.assertEqual(prod.loose_tablet_stock, 1)

    def test_case_e_0_strips_5_loose_sell_6_fail(self):
        """Case E: 0 strips, 5 loose tablets, sell 6 loose tablets.
        Result: Fails with Insufficient stock HTTPException (400).
        """
        prod = Product(
            user_id=1,
            product_name="CILACAR 5",
            category="Allopathy",
            expiry_date=date(2027, 12, 31),
            batch_number="B5",
            quantity=0,
            loose_tablet_stock=5,
            tablets_per_strip=10,
            unit_price=100.0,
        )
        self.session.add(prod)
        self.session.commit()

        with self.assertRaises(HTTPException) as cm:
            deduct_product_stock(
                product=prod,
                quantity=6,
                unit_type="loose_tablet",
                tablets_per_strip_override=10,
            )
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Insufficient", cm.exception.detail)

    def test_case_f_2_strips_3_loose_sell_13(self):
        """Case F: 2 strips * 10 + 3 loose tablets (total 23), sell 13 loose tablets.
        Existing loose: 3. Need: 10 more tabs -> break 1 strip -> 1 strip remains, +10 loose = 13 loose - 13 = 0 loose.
        Result: 1 strip, 0 loose tablets. (Total = 10).
        """
        prod = Product(
            user_id=1,
            product_name="CILACAR 5",
            category="Allopathy",
            expiry_date=date(2027, 12, 31),
            batch_number="B6",
            quantity=2,
            loose_tablet_stock=3,
            tablets_per_strip=10,
            unit_price=100.0,
        )
        self.session.add(prod)
        self.session.commit()

        deduct_product_stock(
            product=prod,
            quantity=13,
            unit_type="loose_tablet",
            tablets_per_strip_override=10,
        )
        self.session.commit()
        self.session.refresh(prod)

        self.assertEqual(prod.quantity, 1)
        self.assertEqual(prod.loose_tablet_stock, 0)
        self.assertEqual(prod.quantity * 10 + prod.loose_tablet_stock, 10)

    def test_case_g_sell_complete_strip_leaves_loose_untouched(self):
        """Case G: Sell 1 complete strip. Strips decrement by 1, loose tablets remain untouched.
        """
        prod = Product(
            user_id=1,
            product_name="CILACAR 5",
            category="Allopathy",
            expiry_date=date(2027, 12, 31),
            batch_number="B7",
            quantity=5,
            loose_tablet_stock=7,
            tablets_per_strip=10,
            unit_price=100.0,
        )
        self.session.add(prod)
        self.session.commit()

        deduct_product_stock(
            product=prod,
            quantity=1,
            unit_type="strip",
            tablets_per_strip_override=10,
        )
        self.session.commit()
        self.session.refresh(prod)

        self.assertEqual(prod.quantity, 4)
        self.assertEqual(prod.loose_tablet_stock, 7)

    def test_case_h_create_sale_transaction_atomic(self):
        """Case H: End-to-end create_sale_transaction atomic stock deduction.
        """
        prod1 = Product(
            id=101,
            user_id=1,
            product_name="CILACAR 5",
            category="Allopathy",
            expiry_date=date(2027, 12, 31),
            batch_number="B101",
            quantity=10,
            loose_tablet_stock=0,
            tablets_per_strip=10,
            unit_price=100.0,
            loose_tablet_price=10.0,
            is_deleted=False,
        )
        prod2 = Product(
            id=102,
            user_id=1,
            product_name="PARACETAMOL",
            category="Allopathy",
            expiry_date=date(2027, 12, 31),
            batch_number="B102",
            quantity=2,
            loose_tablet_stock=2,
            tablets_per_strip=10,
            unit_price=20.0,
            loose_tablet_price=2.0,
            is_deleted=False,
        )
        self.session.add_all([prod1, prod2])
        self.session.commit()

        sale_in = SaleCreate(
            items=[
                SaleItemCreate(
                    product_id=101,
                    quantity=4,
                    unit_price=10.0,
                    unit_type="loose_tablet",
                    tablets_per_strip=10,
                ),
                SaleItemCreate(
                    product_id=102,
                    quantity=1,
                    unit_price=20.0,
                    unit_type="strip",
                    tablets_per_strip=10,
                ),
            ],
            payment_method="CASH",
            discount_type="flat",
            discount_value=0.0,
        )

        bill = create_sale_transaction(
            db=self.session,
            sale_data=sale_in,
            user_id=1,
            current_user=self.user,
        )
        self.assertIsNotNone(bill)
        self.assertEqual(len(bill.items), 2)

        self.session.refresh(prod1)
        self.session.refresh(prod2)

        # prod1 had 10 strips, sold 4 loose -> 9 strips, 6 loose
        self.assertEqual(prod1.quantity, 9)
        self.assertEqual(prod1.loose_tablet_stock, 6)

        # prod2 had 2 strips, 2 loose, sold 1 strip -> 1 strip, 2 loose
        self.assertEqual(prod2.quantity, 1)
        self.assertEqual(prod2.loose_tablet_stock, 2)

    def test_case_j_cilacar_batch_disambiguation(self):
        """Case J: CILACAR 5 scenario with two batches:
        Batch 1: 'KC825013' with quantity=1110, loose=0
        Batch 2: 'KCB25013' with quantity=0, loose=0
        Selling loose tablets from the in-stock batch succeeds.
        """
        b1 = Product(
            id=280550,
            user_id=1,
            product_name="CILACAR 5",
            category="Allopathy",
            expiry_date=date(2027, 12, 31),
            batch_number="KC825013",
            quantity=1110,
            loose_tablet_stock=0,
            tablets_per_strip=10,
            unit_price=115.0,
            loose_tablet_price=11.5,
            is_deleted=False,
        )
        b2 = Product(
            id=280557,
            user_id=1,
            product_name="CILACAR 5",
            category="Allopathy",
            expiry_date=date(2027, 12, 31),
            batch_number="KCB25013",
            quantity=0,
            loose_tablet_stock=0,
            tablets_per_strip=10,
            unit_price=115.0,
            loose_tablet_price=11.5,
            is_deleted=False,
        )
        self.session.add_all([b1, b2])
        self.session.commit()

        # Deduct 4 loose tablets from batch 1 (in-stock)
        deduct_product_stock(
            product=b1,
            quantity=4,
            unit_type="loose_tablet",
            tablets_per_strip_override=10,
        )
        self.session.commit()
        self.session.refresh(b1)

        self.assertEqual(b1.quantity, 1109)
        self.assertEqual(b1.loose_tablet_stock, 6)
        self.assertEqual(b1.quantity * 10 + b1.loose_tablet_stock, 11096)

if __name__ == "__main__":
    unittest.main()
