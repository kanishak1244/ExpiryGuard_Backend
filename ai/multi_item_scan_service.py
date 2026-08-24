import json
import mimetypes
import os
import time
import re
from pathlib import Path

from google.genai import types

from ai.gemini_service import client


MULTI_ITEM_PROMPT = """
You are a pharmacy counter vision scanner.

The image contains multiple medicine boxes, strips, or bottles placed together.

Detect every distinct medicine visible in the image.

Return ONLY valid JSON. Do not return Markdown or explanations.

Return exactly this structure:

{
  "items": [
    {
      "product_name": "",
      "brand": "",
      "quantity": 1,
      "observed_price": null,
      "confidence": 0.0,
      "needs_review": false,
      "reason": ""
    }
  ]
}

Rules:

1. Return one object for every distinct medicine.
2. If the same medicine appears multiple times, combine them into one item and increase quantity.
3. Default quantity is 1 when only one medicine is visible.
4. Count duplicate visible packages carefully.
5. Read the medicine name from the package.
6. Read the brand when visible.
7. Read the printed price only as observed_price.
8. Never invent a price.
9. Use null when the price is not visible.
10. Confidence must be between 0.0 and 1.0.
11. Set needs_review to true when the medicine is blurry, overlapping, partially hidden, or uncertain.
12. Do not guess an unreadable medicine name.
13. Do not include batch numbers, expiry dates, phone numbers, or unrelated text.
14. If no medicine can be detected, return an empty items array.
"""


def _clean_json_text(text: str) -> str:
    """Removes accidental Markdown fences from Gemini output."""
    cleaned = text.strip()

    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    return cleaned.strip()


def _safe_quantity(value) -> int:
    try:
        quantity = int(value)
        return max(quantity, 1)
    except (TypeError, ValueError):
        return 1


def _safe_confidence(value) -> float:
    try:
        confidence = float(value)
        return min(max(confidence, 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_price(value):
    if value is None or value == "":
        return None

    try:
        price = float(value)
        return max(price, 0.0)
    except (TypeError, ValueError):
        return None


def _normalize_item(item: dict) -> dict:
    if not isinstance(item, dict):
        return {
            "product_name": "",
            "brand": "",
            "quantity": 1,
            "observed_price": None,
            "confidence": 0.0,
            "needs_review": True,
            "reason": "Invalid AI item format",
        }

    product_name = item.get("product_name") or ""
    brand = item.get("brand") or ""
    confidence = _safe_confidence(item.get("confidence"))

    return {
        "product_name": str(product_name).strip(),
        "brand": str(brand).strip(),
        "quantity": _safe_quantity(item.get("quantity")),
        "observed_price": _safe_price(item.get("observed_price")),
        "confidence": confidence,
        "needs_review": bool(item.get("needs_review")) or confidence < 0.70,
        "reason": str(item.get("reason") or "").strip(),
    }


def scan_multi_item(image_path: str) -> dict:
    """
    Scans one image containing multiple medicines.

    This function only identifies medicines.
    Inventory matching and prices must be handled by the FastAPI route.
    """

    image_file = Path(image_path)

    if not image_file.exists():
        return {
            "success": False,
            "items": [],
            "error": "Image file not found.",
        }

    mime_type, _ = mimetypes.guess_type(str(image_file))
    mime_type = mime_type or "image/jpeg"

    if mime_type not in {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/jpg",
    }:
        return {
            "success": False,
            "items": [],
            "error": "Only JPG, PNG, and WEBP images are supported.",
        }

    try:
        image_bytes = image_file.read_bytes()

        model_name = os.getenv(
            "GEMINI_MULTI_SCAN_MODEL",
            "gemini-3.1-flash-lite",
        )

        response = None
        last_error = None
        start_time = time.time()

        candidate_models = [model_name, "gemini-3.5-flash-lite", "gemini-flash-lite-latest"]
        # De-duplicate while preserving order
        candidate_models = list(dict.fromkeys(candidate_models))

        for target_model in candidate_models:
            for attempt in range(2):
                try:
                    config = types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json",
                    )
                    # Disable thinking budget if available for maximum speed
                    try:
                        config.thinking_config = types.ThinkingConfig(thinking_budget=0)
                    except Exception:
                        pass

                    response = client.models.generate_content(
                        model=target_model,
                        contents=[
                            MULTI_ITEM_PROMPT,
                            types.Part.from_bytes(
                                data=image_bytes,
                                mime_type=mime_type,
                            ),
                        ],
                        config=config,
                    )
                    elapsed = time.time() - start_time
                    print(f"[AI SCAN] Successfully scanned with {target_model} in {elapsed:.2f}s")
                    break

                except Exception as exc:
                    last_error = str(exc)
                    print(f"[AI SCAN WARNING] Model {target_model} attempt {attempt+1} failed: {exc}")
                    temporary_error = any(
                        code in last_error
                        for code in ("503", "429", "500", "UNAVAILABLE")
                    )

                    if not temporary_error:
                        break

                    time.sleep(0.5 * (2 ** attempt))

            if response is not None:
                break

        if response is None:
            raise RuntimeError(
                last_error or "Gemini did not return a response."
            )

        raw_text = response.text or ""
        cleaned_text = _clean_json_text(raw_text)
        parsed = json.loads(cleaned_text)

        raw_items = parsed.get("items", [])

        if not isinstance(raw_items, list):
            raise ValueError("Gemini returned an invalid items array.")

        items = [
            _normalize_item(item)
            for item in raw_items
        ]

        items = [
            item for item in items
            if item["product_name"]
        ]

        return {
            "success": True,
            "items": items,
            "error": None,
        }

    except json.JSONDecodeError:
        return {
            "success": False,
            "items": [],
            "error": "Gemini returned invalid JSON.",
        }

    except Exception as exc:
        return {
            "success": False,
            "items": [],
            "error": str(exc),
        }