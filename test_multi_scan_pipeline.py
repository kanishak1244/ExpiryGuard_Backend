import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure backend root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import _match_inventory_items, _normalise_product_name
from ai.multi_item_scan_service import scan_multi_item, validate_multi_item_data


class MockProduct:
    def __init__(self, id, product_name, brand=None, barcode=None, unit_price=50.0, quantity=10, pack_size_label=None, batch_number="B1", expiry_date=None):
        self.id = id
        self.product_name = product_name
        self.brand = brand
        self.barcode = barcode
        self.unit_price = unit_price
        self.quantity = quantity
        self.pack_size_label = pack_size_label
        self.batch_number = batch_number
        self.expiry_date = expiry_date


class TestMultiScanPipeline(unittest.TestCase):
    def setUp(self):
        self.inventory = [
            MockProduct(1, "Dolo 650 Tablet", brand="Micro Labs", barcode="8901234567890", unit_price=30.0, pack_size_label="15 tablets"),
            MockProduct(2, "Dolo 500 Tablet", brand="Micro Labs", barcode="8901234567891", unit_price=25.0, pack_size_label="10 tablets"),
            MockProduct(3, "Azithral 500mg Tablet", brand="Alembic", barcode="8902222222222", unit_price=120.0),
            MockProduct(4, "Augmentin 625 Duo", brand="GSK", barcode="8903333333333", unit_price=200.0),
            MockProduct(5, "Pan 40 Tablet", brand="Alkem", barcode="8904444444444", unit_price=90.0),
            MockProduct(6, "Paracetamol 500mg", brand="Cipla", barcode=None, unit_price=15.0),
            MockProduct(7, "Paracetamol 500mg", brand="Sun Pharma", barcode=None, unit_price=18.0),
        ]

    # Scenario 1 & 2: 4 & 5 medicines in one image
    def test_multi_medicine_extraction_validation(self):
        data_4 = {
            "items": [
                {"name": "Dolo 650", "code": None, "strength": "650mg", "form": "tablet", "pack_size": "15"},
                {"name": "Azithral 500", "code": "8902222222222", "strength": "500mg", "form": "tablet", "pack_size": None},
                {"name": "Pan 40", "code": None, "strength": "40mg", "form": "tablet", "pack_size": "10"},
                {"name": "Augmentin 625", "code": None, "strength": "625mg", "form": "tablet", "pack_size": "6"},
            ]
        }
        self.assertTrue(validate_multi_item_data(data_4))
        self.assertEqual(len(data_4["items"]), 4)

        data_5 = {
            "items": data_4["items"] + [{"name": "Crocin Advance", "code": None, "strength": "500mg", "form": "tablet", "pack_size": "10"}]
        }
        self.assertTrue(validate_multi_item_data(data_5))
        self.assertEqual(len(data_5["items"]), 5)

    # Scenario 3: Duplicate medicine packages
    def test_duplicate_packages_matching(self):
        detected_1 = {"name": "Dolo 650", "code": None, "strength": "650mg", "form": "tablet", "pack_size": None}
        detected_2 = {"name": "Dolo 650", "code": None, "strength": "650mg", "form": "tablet", "pack_size": None}
        
        status1, type1, prod1, *rest1 = _match_inventory_items(self.inventory, detected_1)
        status2, type2, prod2, *rest2 = _match_inventory_items(self.inventory, detected_2)

        self.assertEqual(status1, "MATCHED")
        self.assertEqual(status2, "MATCHED")
        self.assertEqual(prod1.id, prod2.id)

    # Scenario 4: Medicine with visible barcode (Priority 1 exact match)
    def test_priority1_exact_barcode_match(self):
        detected = {"name": "Some Blurry Name", "code": "8901234567890", "strength": None, "form": None, "pack_size": None}
        status, match_type, product, possible, *rest = _match_inventory_items(self.inventory, detected)
        self.assertEqual(status, "MATCHED")
        self.assertEqual(match_type, "EXACT_CODE")
        self.assertEqual(product.id, 1)
        self.assertEqual(product.product_name, "Dolo 650 Tablet")

    # Scenario 5: Medicine with unreadable barcode but readable name (Priority 2 match)
    def test_priority2_exact_name_specs_match(self):
        detected = {"name": "Azithral 500mg", "code": None, "strength": "500mg", "form": "Tablet", "pack_size": None}
        status, match_type, product, possible, *rest = _match_inventory_items(self.inventory, detected)
        self.assertEqual(status, "MATCHED")
        self.assertEqual(match_type, "EXACT_NAME_SPECS")
        self.assertEqual(product.id, 3)

    # Scenario 6: Medicine not present in inventory (NOT_FOUND, no hallucinated match)
    def test_not_found_medicine(self):
        detected = {"name": "Completely Nonexistent Drug XYZ 999", "code": "0000000000", "strength": None, "form": None, "pack_size": None}
        status, match_type, product, possible, *rest = _match_inventory_items(self.inventory, detected)
        self.assertEqual(status, "NOT_FOUND")
        self.assertIsNone(product)
        self.assertEqual(len(possible), 0)

    # Scenario 7: Two inventory products with similar names (MULTIPLE_MATCHES disambiguation)
    def test_multiple_matches_disambiguation(self):
        detected = {"name": "Paracetamol 500mg", "code": None, "strength": None, "form": None, "pack_size": None}
        status, match_type, product, possible, *rest = _match_inventory_items(self.inventory, detected)
        self.assertEqual(status, "MULTIPLE_MATCHES")
        self.assertIsNone(product)
        self.assertGreaterEqual(len(possible), 2)
        # Verify both Cipla and Sun Pharma products are in possible list
        brands = [p.brand for p in possible]
        self.assertIn("Cipla", brands)
        self.assertIn("Sun Pharma", brands)

    # Scenario 8: Partially visible medicine / Safe Fuzzy (Priority 3)
    def test_safe_fuzzy_and_low_confidence(self):
        # Slightly noisy or incomplete name
        detected = {"name": "Augmentn 625 Du", "code": None, "strength": None, "form": None, "pack_size": None}
        status, match_type, product, possible, *rest = _match_inventory_items(self.inventory, detected)
        self.assertIn(status, {"MATCHED", "LOW_CONFIDENCE"})
        self.assertEqual(product.id, 4)

    # Scenario 9: Gemini failure (Graceful failure, no fallback invocation)
    @patch("ai.multi_item_scan_service.client.models.generate_content")
    @patch("ai.multi_item_scan_service.Path.exists", return_value=True)
    @patch("ai.multi_item_scan_service.Path.read_bytes", return_value=b"fake_image_bytes")
    @patch("ai.multi_item_scan_service.optimize_image")
    def test_gemini_failure_handling(self, mock_opt, mock_read, mock_exists, mock_gen):
        mock_gen.side_effect = Exception("500 Internal Server Error from AI API")
        res = scan_multi_item("fake.jpg")
        self.assertFalse(res["success"])
        self.assertEqual(len(res["items"]), 0)
        self.assertIn("500", res["error"])

    # Scenario 10: Empty or malformed Gemini response
    @patch("ai.multi_item_scan_service.client.models.generate_content")
    @patch("ai.multi_item_scan_service.Path.exists", return_value=True)
    @patch("ai.multi_item_scan_service.Path.read_bytes", return_value=b"fake_image_bytes")
    @patch("ai.multi_item_scan_service.optimize_image")
    def test_empty_or_invalid_gemini_response(self, mock_opt, mock_read, mock_exists, mock_gen):
        mock_response = MagicMock()
        mock_response.text = '{"items": []}'
        mock_response.usage_metadata = None
        mock_gen.return_value = mock_response

        res = scan_multi_item("fake.jpg")
        self.assertTrue(res["success"])
        self.assertEqual(len(res["items"]), 0)


if __name__ == "__main__":
    unittest.main()
