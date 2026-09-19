"""
Profit Calculator Engine for DawaiFlow Pharmacy ERP.
Computes real-time profit for today's sales based on item sale price and cost price.
Excludes items without a valid tracked cost price (cost_price is None or <= 0).
"""

from typing import List, Dict, Any, Optional


def calculate_today_profit(items: List[Dict[str, Any]]) -> float:
    """
    Calculates total profit from a list of sold items.
    
    Each item dict is expected to have:
      - 'unit_price': float (sale price per unit)
      - 'cost_price': Optional[float] (purchase/cost price per unit)
      - 'quantity': int
      - 'returned_quantity': int (default 0)
      - 'total_price': Optional[float] (override for line total if provided)
    
    If cost_price is None or <= 0, the item is excluded from profit calculation
    rather than guessing or outputting an inaccurate figure.
    """
    total_profit = 0.0

    for item in items:
        cost_price = item.get("cost_price")
        
        # Exclude items where cost price is missing, None, or <= 0
        if cost_price is None or cost_price <= 0:
            continue

        quantity = item.get("quantity") or 0
        returned_quantity = item.get("returned_quantity") or 0
        net_qty = max(0, quantity - returned_quantity)

        if net_qty <= 0:
            continue

        unit_price = item.get("unit_price") or 0.0
        line_total = item.get("total_price")
        if line_total is None or line_total == 0.0:
            line_total = unit_price * net_qty

        cost_total = cost_price * net_qty
        item_profit = line_total - cost_total
        total_profit += item_profit

    return round(float(total_profit), 2)
