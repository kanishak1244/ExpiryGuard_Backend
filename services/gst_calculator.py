from datetime import date, datetime
import calendar
from typing import Dict, List, Optional, Any

CATEGORY_X_STATES = {
    "MH", "GJ", "KA", "TN", "KL", "AP", "TS", "GA", "CG", "MP",
    "UT", "DH", "DD", "LA", "PY", "AN", "LD"
}

CATEGORY_Y_STATES = {
    "DL", "HR", "PB", "UP", "RJ", "BR", "WB", "HP", "JK", "AS",
    "OR", "JH", "SK", "AR", "NL", "MN", "MZ", "TR", "ML"
}


# ==============================================================================
# 1. CORE GST & INVOICE FINANCIAL CALCULATIONS
# ==============================================================================

def calculate_gross_amount(quantity: float, unit_price: float) -> float:
    """Stage 1: Calculate gross amount before any discounts or taxes."""
    return round(quantity * unit_price, 2)


def calculate_line_discount(gross_amount: float, discount_percent: float) -> float:
    """Stage 2a: Calculate line-item discount amount."""
    if discount_percent <= 0:
        return 0.0
    return round(gross_amount * (discount_percent / 100.0), 2)


def calculate_taxable_amount(
    gross_amount: float,
    line_discount: float,
    allocated_invoice_discount: float = 0.0
) -> float:
    """Stage 3: Calculate net taxable value after applying line & invoice discounts."""
    taxable = gross_amount - line_discount - allocated_invoice_discount
    return round(max(0.0, taxable), 2)


def calculate_gst_breakdown(
    taxable_amount: float,
    gst_rate: float,
    is_interstate: bool = False
) -> Dict[str, float]:
    """
    Stages 4 & 5: Calculate GST tax breakdown.
    Splits into CGST + SGST for intrastate transactions or IGST for interstate.
    """
    if gst_rate <= 0 or taxable_amount <= 0:
        return {
            "cgst_rate": 0.0,
            "cgst_amount": 0.0,
            "sgst_rate": 0.0,
            "sgst_amount": 0.0,
            "igst_rate": 0.0,
            "igst_amount": 0.0,
            "total_gst_amount": 0.0,
        }

    if is_interstate:
        igst_rate = float(gst_rate)
        igst_amount = round(taxable_amount * (igst_rate / 100.0), 2)
        return {
            "cgst_rate": 0.0,
            "cgst_amount": 0.0,
            "sgst_rate": 0.0,
            "sgst_amount": 0.0,
            "igst_rate": igst_rate,
            "igst_amount": igst_amount,
            "total_gst_amount": igst_amount,
        }
    else:
        half_rate = round(gst_rate / 2.0, 2)
        cgst_amount = round(taxable_amount * (half_rate / 100.0), 2)
        sgst_amount = round(taxable_amount * (half_rate / 100.0), 2)
        total_gst = round(cgst_amount + sgst_amount, 2)
        return {
            "cgst_rate": half_rate,
            "cgst_amount": cgst_amount,
            "sgst_rate": half_rate,
            "sgst_amount": sgst_amount,
            "igst_rate": 0.0,
            "igst_amount": 0.0,
            "total_gst_amount": total_gst,
        }


def calculate_line_item_financials(
    quantity: float,
    unit_price: float,
    discount_percent: float = 0.0,
    allocated_invoice_discount: float = 0.0,
    gst_rate: float = 12.0,
    is_interstate: bool = False
) -> Dict[str, Any]:
    """
    Complete 8-stage financial pipeline for a single item line:
    1. Gross amount
    2. Discounts
    3. Taxable amount
    4. GST
    5. CGST/SGST or IGST
    6. Rounding
    7. Final total
    8. Structured result
    """
    gross = calculate_gross_amount(quantity, unit_price)
    line_disc = calculate_line_discount(gross, discount_percent)
    taxable = calculate_taxable_amount(gross, line_disc, allocated_invoice_discount)
    gst_info = calculate_gst_breakdown(taxable, gst_rate, is_interstate)

    total_tax = gst_info["total_gst_amount"]
    final_total = round(taxable + total_tax, 2)

    return {
        "gross_amount": gross,
        "line_discount": line_disc,
        "allocated_invoice_discount": allocated_invoice_discount,
        "total_discount": round(line_disc + allocated_invoice_discount, 2),
        "taxable_amount": taxable,
        "gst_rate": gst_rate,
        "cgst_rate": gst_info["cgst_rate"],
        "cgst_amount": gst_info["cgst_amount"],
        "sgst_rate": gst_info["sgst_rate"],
        "sgst_amount": gst_info["sgst_amount"],
        "igst_rate": gst_info["igst_rate"],
        "igst_amount": gst_info["igst_amount"],
        "total_gst_amount": total_tax,
        "final_total": final_total,
    }


def calculate_tax_summary(items_financials: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generates tax summary grouped by GST percentage rate."""
    summary_dict: Dict[float, Dict[str, Any]] = {}

    for item in items_financials:
        rate_key = float(item["gst_rate"])
        if rate_key not in summary_dict:
            summary_dict[rate_key] = {
                "gst_rate": rate_key,
                "taxable_value": 0.0,
                "cgst_amount": 0.0,
                "sgst_amount": 0.0,
                "igst_amount": 0.0,
                "total_tax": 0.0,
            }

        summary_dict[rate_key]["taxable_value"] = round(
            summary_dict[rate_key]["taxable_value"] + item["taxable_amount"], 2
        )
        summary_dict[rate_key]["cgst_amount"] = round(
            summary_dict[rate_key]["cgst_amount"] + item["cgst_amount"], 2
        )
        summary_dict[rate_key]["sgst_amount"] = round(
            summary_dict[rate_key]["sgst_amount"] + item["sgst_amount"], 2
        )
        summary_dict[rate_key]["igst_amount"] = round(
            summary_dict[rate_key]["igst_amount"] + item["igst_amount"], 2
        )
        summary_dict[rate_key]["total_tax"] = round(
            summary_dict[rate_key]["total_tax"] + item["total_gst_amount"], 2
        )

    return list(summary_dict.values())


# ==============================================================================
# 2. GST DUE DATE & COMPLIANCE CALCULATION ENGINE
# ==============================================================================

def add_months(sourcedate: date, months: int) -> date:
    """Safely add months handling year boundary transitions."""
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def get_quarter_info(target_date: date) -> Dict[str, Any]:
    """Returns quarter code (Q1-Q4), quarter months, and quarter end date."""
    month = target_date.month
    year = target_date.year

    if month in [4, 5, 6]:
        return {"quarter_code": f"{year}-Q1", "m1": 4, "m2": 5, "m3": 6, "quarter_end": date(year, 6, 30)}
    elif month in [7, 8, 9]:
        return {"quarter_code": f"{year}-Q2", "m1": 7, "m2": 8, "m3": 9, "quarter_end": date(year, 9, 30)}
    elif month in [10, 11, 12]:
        return {"quarter_code": f"{year}-Q3", "m1": 10, "m2": 11, "m3": 12, "quarter_end": date(year, 12, 31)}
    else:
        return {"quarter_code": f"{year - 1}-Q4", "m1": 1, "m2": 2, "m3": 3, "quarter_end": date(year, 3, 31)}


def _calculate_monthly_due_dates(ref_date: date, override_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    prev_month = add_months(ref_date, -1)
    period_str = prev_month.strftime("%Y-%m")
    period_label = prev_month.strftime("%B %Y")
    next_month = add_months(prev_month, 1)

    # GSTR-1: 11th of month following period
    gstr1_due = date(next_month.year, next_month.month, 11)
    ov_gstr1 = override_map.get(f"GSTR1_{period_str}")
    if ov_gstr1:
        gstr1_due = datetime.strptime(str(ov_gstr1), "%Y-%m-%d").date() if isinstance(ov_gstr1, str) else ov_gstr1

    # GSTR-3B: 20th of month following period
    gstr3b_due = date(next_month.year, next_month.month, 20)
    ov_gstr3b = override_map.get(f"GSTR3B_{period_str}")
    if ov_gstr3b:
        gstr3b_due = datetime.strptime(str(ov_gstr3b), "%Y-%m-%d").date() if isinstance(ov_gstr3b, str) else ov_gstr3b

    return [
        {
            "return_type": "GSTR-1",
            "period": period_str,
            "period_label": period_label,
            "due_date": gstr1_due.isoformat(),
            "due_date_formatted": gstr1_due.strftime("%d %b %Y"),
            "description": "Monthly Outward Supplies Return",
        },
        {
            "return_type": "GSTR-3B",
            "period": period_str,
            "period_label": period_label,
            "due_date": gstr3b_due.isoformat(),
            "due_date_formatted": gstr3b_due.strftime("%d %b %Y"),
            "description": "Monthly Summary & Tax Payment Return",
        },
    ]


def _calculate_qrmp_due_dates(ref_date: date, state_cat: str, override_map: Dict[str, Any]) -> List[Dict[str, Any]]:
    q_info = get_quarter_info(ref_date)
    q_code = q_info["quarter_code"]
    q_end = q_info["quarter_end"]
    next_m = add_months(q_end, 1)

    # GSTR-1 (Quarterly): 13th of month after quarter
    gstr1_due = date(next_m.year, next_m.month, 13)
    ov_gstr1 = override_map.get(f"GSTR1_{q_code}")
    if ov_gstr1:
        gstr1_due = datetime.strptime(str(ov_gstr1), "%Y-%m-%d").date() if isinstance(ov_gstr1, str) else ov_gstr1

    # GSTR-3B (Quarterly): 22nd (Cat X) or 24th (Cat Y) of month after quarter
    gstr3b_day = 22 if state_cat == "X" else 24
    gstr3b_due = date(next_m.year, next_m.month, gstr3b_day)
    ov_gstr3b = override_map.get(f"GSTR3B_{q_code}")
    if ov_gstr3b:
        gstr3b_due = datetime.strptime(str(ov_gstr3b), "%Y-%m-%d").date() if isinstance(ov_gstr3b, str) else ov_gstr3b

    returns = [
        {
            "return_type": "GSTR-1",
            "period": q_code,
            "period_label": f"Quarter ({q_code})",
            "due_date": gstr1_due.isoformat(),
            "due_date_formatted": gstr1_due.strftime("%d %b %Y"),
            "description": "Quarterly GSTR-1 / IFF Return",
        },
        {
            "return_type": "GSTR-3B",
            "period": q_code,
            "period_label": f"Quarter ({q_code})",
            "due_date": gstr3b_due.isoformat(),
            "due_date_formatted": gstr3b_due.strftime("%d %b %Y"),
            "description": f"Quarterly Summary Return (Category {state_cat})",
        },
    ]

    # PMT-06 Monthly Tax Payments for M1 and M2
    m1_date = date(q_end.year if q_info["m1"] <= 12 else q_end.year - 1, q_info["m1"], 1)
    pmt1_due_month = add_months(m1_date, 1)
    pmt1_due = date(pmt1_due_month.year, pmt1_due_month.month, 25)

    m2_date = date(q_end.year if q_info["m2"] <= 12 else q_end.year - 1, q_info["m2"], 1)
    pmt2_due_month = add_months(m2_date, 1)
    pmt2_due = date(pmt2_due_month.year, pmt2_due_month.month, 25)

    returns.extend([
        {
            "return_type": "PMT-06 (M1)",
            "period": m1_date.strftime("%Y-%m"),
            "period_label": m1_date.strftime("%B %Y"),
            "due_date": pmt1_due.isoformat(),
            "due_date_formatted": pmt1_due.strftime("%d %b %Y"),
            "description": "Monthly Tax Payment Challan (Month 1)",
        },
        {
            "return_type": "PMT-06 (M2)",
            "period": m2_date.strftime("%Y-%m"),
            "period_label": m2_date.strftime("%B %Y"),
            "due_date": pmt2_due.isoformat(),
            "due_date_formatted": pmt2_due.strftime("%d %b %Y"),
            "description": "Monthly Tax Payment Challan (Month 2)",
        },
    ])

    return returns


def _process_return_urgency(returns: List[Dict[str, Any]], ref_date: date) -> List[Dict[str, Any]]:
    processed = []
    for ret in returns:
        due_dt = datetime.strptime(ret["due_date"], "%Y-%m-%d").date()
        days_left = (due_dt - ref_date).days

        if days_left > 5:
            urgency, color, badge = "low", "green", f"Due in {days_left} days"
        elif 2 <= days_left <= 5:
            urgency, color, badge = "medium", "orange", f"Due in {days_left} days"
        elif 0 <= days_left < 2:
            urgency, color = "high", "red"
            badge = "Due Today" if days_left == 0 else "Due Tomorrow"
        else:
            urgency, color = "overdue", "red"
            badge = f"Overdue by {abs(days_left)} days"

        ret_copy = dict(ret)
        ret_copy.update({
            "days_remaining": days_left,
            "urgency": urgency,
            "color_code": color,
            "badge_label": badge,
        })
        processed.append(ret_copy)

    processed.sort(key=lambda x: x["days_remaining"])
    return processed


def calculate_gst_due_dates(
    filing_type: Optional[str],
    state_category: Optional[str] = "X",
    ref_date: Optional[date] = None,
    overrides: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Calculates GST return due dates without network or blocking DB operations.
    Returns clean dictionary with configuration status, returns list, and urgency.
    """
    if not ref_date:
        ref_date = date.today()

    if not filing_type or filing_type.lower() not in ["monthly", "qrmp"]:
        return {
            "is_configured": False,
            "filing_type": None,
            "state_category": state_category or "X",
            "message": "GST filing settings not configured. Please select Monthly or QRMP filing.",
            "returns": [],
            "next_due_return": None,
        }

    filing_type = filing_type.lower()
    state_cat = (state_category or "X").upper()
    if state_cat not in ["X", "Y"]:
        state_cat = "X"

    override_map = {}
    if overrides:
        for ov in overrides:
            key = f"{ov.get('return_type')}_{ov.get('period')}"
            override_map[key] = ov.get("extended_due_date")

    if filing_type == "monthly":
        raw_returns = _calculate_monthly_due_dates(ref_date, override_map)
    else:
        raw_returns = _calculate_qrmp_due_dates(ref_date, state_cat, override_map)

    processed_returns = _process_return_urgency(raw_returns, ref_date)
    next_due = processed_returns[0] if processed_returns else None

    return {
        "is_configured": True,
        "filing_type": filing_type,
        "state_category": state_cat,
        "portal_url": "https://www.gst.gov.in",
        "returns": processed_returns,
        "next_due_return": next_due,
    }
