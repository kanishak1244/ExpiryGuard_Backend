from datetime import date, datetime, timedelta
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


def add_months(sourcedate: date, months: int) -> date:
    """Safely add months handling year boundary transitions."""
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def get_quarter_info(target_date: date) -> Dict[str, Any]:
    """
    Returns quarter code (Q1-Q4), quarter months, and quarter end date.
    Q1: Apr-Jun, Q2: Jul-Sep, Q3: Oct-Dec, Q4: Jan-Mar
    """
    month = target_date.month
    year = target_date.year

    if month in [4, 5, 6]:
        q_code = f"{year}-Q1"
        m1, m2, m3 = 4, 5, 6
        q_end = date(year, 6, 30)
    elif month in [7, 8, 9]:
        q_code = f"{year}-Q2"
        m1, m2, m3 = 7, 8, 9
        q_end = date(year, 9, 30)
    elif month in [10, 11, 12]:
        q_code = f"{year}-Q3"
        m1, m2, m3 = 10, 11, 12
        q_end = date(year, 12, 31)
    else:  # 1, 2, 3
        q_code = f"{year - 1}-Q4"
        m1, m2, m3 = 1, 2, 3
        q_end = date(year, 3, 31)

    return {
        "quarter_code": q_code,
        "m1": m1,
        "m2": m2,
        "m3": m3,
        "quarter_end": q_end,
    }


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

    returns = []
    override_map = {}
    if overrides:
        for ov in overrides:
            key = f"{ov.get('return_type')}_{ov.get('period')}"
            override_map[key] = ov.get("extended_due_date")

    if filing_type == "monthly":
        prev_month_date = add_months(ref_date, -1)
        period_str = prev_month_date.strftime("%Y-%m")

        # GSTR-1: 11th of month following period
        gstr1_month = add_months(prev_month_date, 1)
        gstr1_due = date(gstr1_month.year, gstr1_month.month, 11)
        ov_gstr1 = override_map.get(f"GSTR1_{period_str}")
        if ov_gstr1:
            gstr1_due = datetime.strptime(str(ov_gstr1), "%Y-%m-%d").date() if isinstance(ov_gstr1, str) else ov_gstr1

        # GSTR-3B: 20th of month following period
        gstr3b_month = add_months(prev_month_date, 1)
        gstr3b_due = date(gstr3b_month.year, gstr3b_month.month, 20)
        ov_gstr3b = override_map.get(f"GSTR3B_{period_str}")
        if ov_gstr3b:
            gstr3b_due = datetime.strptime(str(ov_gstr3b), "%Y-%m-%d").date() if isinstance(ov_gstr3b, str) else ov_gstr3b

        returns.append({
            "return_type": "GSTR-1",
            "period": period_str,
            "period_label": prev_month_date.strftime("%B %Y"),
            "due_date": gstr1_due.isoformat(),
            "due_date_formatted": gstr1_due.strftime("%d %b %Y"),
            "description": "Monthly Outward Supplies Return",
        })

        returns.append({
            "return_type": "GSTR-3B",
            "period": period_str,
            "period_label": prev_month_date.strftime("%B %Y"),
            "due_date": gstr3b_due.isoformat(),
            "due_date_formatted": gstr3b_due.strftime("%d %b %Y"),
            "description": "Monthly Summary & Tax Payment Return",
        })

    else:  # QRMP
        q_info = get_quarter_info(ref_date)
        q_code = q_info["quarter_code"]
        q_end = q_info["quarter_end"]
        next_m = add_months(q_end, 1)

        # GSTR-1 (Quarterly): 13th of month after quarter
        gstr1_due = date(next_m.year, next_m.month, 13)
        ov_gstr1 = override_map.get(f"GSTR1_{q_code}")
        if ov_gstr1:
            gstr1_due = datetime.strptime(str(ov_gstr1), "%Y-%m-%d").date() if isinstance(ov_gstr1, str) else ov_gstr1

        # GSTR-3B (Quarterly): 22nd (Category X) or 24th (Category Y) of month after quarter
        gstr3b_day = 22 if state_cat == "X" else 24
        gstr3b_due = date(next_m.year, next_m.month, gstr3b_day)
        ov_gstr3b = override_map.get(f"GSTR3B_{q_code}")
        if ov_gstr3b:
            gstr3b_due = datetime.strptime(str(ov_gstr3b), "%Y-%m-%d").date() if isinstance(ov_gstr3b, str) else ov_gstr3b

        returns.append({
            "return_type": "GSTR-1",
            "period": q_code,
            "period_label": f"Quarter ({q_code})",
            "due_date": gstr1_due.isoformat(),
            "due_date_formatted": gstr1_due.strftime("%d %b %Y"),
            "description": "Quarterly GSTR-1 / IFF Return",
        })

        returns.append({
            "return_type": "GSTR-3B",
            "period": q_code,
            "period_label": f"Quarter ({q_code})",
            "due_date": gstr3b_due.isoformat(),
            "due_date_formatted": gstr3b_due.strftime("%d %b %Y"),
            "description": f"Quarterly Summary Return (Category {state_cat})",
        })

        # PMT-06 Monthly Tax Payments for M1 and M2
        m1_date = date(q_end.year if q_info["m1"] <= 12 else q_end.year - 1, q_info["m1"], 1)
        pmt1_due_month = add_months(m1_date, 1)
        pmt1_due = date(pmt1_due_month.year, pmt1_due_month.month, 25)

        m2_date = date(q_end.year if q_info["m2"] <= 12 else q_end.year - 1, q_info["m2"], 1)
        pmt2_due_month = add_months(m2_date, 1)
        pmt2_due = date(pmt2_due_month.year, pmt2_due_month.month, 25)

        returns.append({
            "return_type": "PMT-06 (M1)",
            "period": m1_date.strftime("%Y-%m"),
            "period_label": m1_date.strftime("%B %Y"),
            "due_date": pmt1_due.isoformat(),
            "due_date_formatted": pmt1_due.strftime("%d %b %Y"),
            "description": "Monthly Tax Payment Challan (Month 1)",
        })

        returns.append({
            "return_type": "PMT-06 (M2)",
            "period": m2_date.strftime("%Y-%m"),
            "period_label": m2_date.strftime("%B %Y"),
            "due_date": pmt2_due.isoformat(),
            "due_date_formatted": pmt2_due.strftime("%d %b %Y"),
            "description": "Monthly Tax Payment Challan (Month 2)",
        })

    # Calculate days remaining, urgency, and color codes for each return
    processed_returns = []
    for ret in returns:
        due_dt = datetime.strptime(ret["due_date"], "%Y-%m-%d").date()
        days_left = (due_dt - ref_date).days

        if days_left > 5:
            urgency = "low"
            color = "green"
            badge = f"Due in {days_left} days"
        elif 2 <= days_left <= 5:
            urgency = "medium"
            color = "orange"
            badge = f"Due in {days_left} days"
        elif 0 <= days_left < 2:
            urgency = "high"
            color = "red"
            badge = "Due Today" if days_left == 0 else "Due Tomorrow"
        else:
            urgency = "overdue"
            color = "red"
            badge = f"Overdue by {abs(days_left)} days"

        ret_copy = dict(ret)
        ret_copy.update({
            "days_remaining": days_left,
            "urgency": urgency,
            "color_code": color,
            "badge_label": badge,
        })
        processed_returns.append(ret_copy)

    processed_returns.sort(key=lambda x: x["days_remaining"])
    next_due = processed_returns[0] if processed_returns else None

    return {
        "is_configured": True,
        "filing_type": filing_type,
        "state_category": state_cat,
        "portal_url": "https://www.gst.gov.in",
        "returns": processed_returns,
        "next_due_return": next_due,
    }
