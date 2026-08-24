import json
import mimetypes
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env")

client = genai.Client(api_key=API_KEY)

PROMPT = """
You are an expert product label reader.

Extract ONLY the following information from the product label.

Return ONLY valid JSON.

Rules:

1. product_name
2. brand
3. batch_number
4. manufacturing_date
5. expiry_date

Date Rules:

• If a complete date exists:
  Return as YYYY-MM-DD.

Example:
25/11/2027 → 2027-11-25

25-11-2027 → 2027-11-25

25 Nov 2027 → 2027-11-25

• If ONLY month and year exist:

11/2027
Nov 2027
November 2027

Return:

2027-11-01

(The first day of that month.)

• Ignore:
MRP
Price
Weight
Barcode
Phone numbers
Customer care numbers
License numbers

Return null if a field is missing.

Output exactly:

{
  "product_name": "...",
  "brand": "...",
  "batch_number": "...",
  "manufacturing_date": "...",
  "expiry_date": "..."
}
"""

def scan_label(image_path: str) -> dict:
    """
    Scan a product label using Gemini Vision.

    Returns:
    {
        "success": bool,
        "needs_manual_review": bool,
        "data": {
            "product_name": ...,
            "brand": ...,
            "batch_number": ...,
            "manufacturing_date": ...,
            "expiry_date": ...,
            "missing_fields": [...]
        },
        "error": None | str
    }
    """

    image_file = Path(image_path)

    if not image_file.exists():
        return {
            "success": False,
            "needs_manual_review": True,
            "data": None,
            "error": "Image file not found."
        }

    mime_type, _ = mimetypes.guess_type(image_file)

    if mime_type is None:
        mime_type = "image/jpeg"

    image_bytes = image_file.read_bytes()

    for attempt in range(3):

        try:

            config = types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
            )
            try:
                config.thinking_config = types.ThinkingConfig(thinking_budget=0)
            except Exception:
                pass

            response = client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=[
                    PROMPT,
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type=mime_type,
                    ),
                ],
                config=config,
            )

            data = json.loads(response.text)

            required_fields = [
                "product_name",
                "brand",
                "batch_number",
                "manufacturing_date",
                "expiry_date",
            ]

            missing_fields = []

            for field in required_fields:

                value = data.get(field)

                if value is None:
                    missing_fields.append(field)

                elif isinstance(value, str) and value.strip() == "":
                    data[field] = None
                    missing_fields.append(field)

            data["missing_fields"] = missing_fields

            return {
                "success": True,
                "needs_manual_review": len(missing_fields) > 0,
                "data": data,
                "error": None,
            }

        except Exception as e:

            error = str(e)

            if "429" in error and attempt < 2:
                time.sleep(2 ** attempt)
                continue

            return {
                "success": False,
                "needs_manual_review": True,
                "data": None,
                "error": error,
            }