"""
Permissions and Role-Based Access Control (RBAC) definitions for Dawaiflow.
"""

from typing import Set, Dict, Optional
import json

# Permission Constants
# 1. Billing & Sales
PERM_BILL_CREATE = "BILL_CREATE"
PERM_BILL_VIEW = "BILL_VIEW"
PERM_BILL_DELETE = "BILL_DELETE"
PERM_BILL_HELD = "BILL_HELD"

# 2. Inventory & Catalog
PERM_INVENTORY_VIEW = "INVENTORY_VIEW"
PERM_INVENTORY_CREATE = "INVENTORY_CREATE"
PERM_INVENTORY_EDIT = "INVENTORY_EDIT"
PERM_INVENTORY_DELETE = "INVENTORY_DELETE"

# 3. Purchases & Restock
PERM_PURCHASE_VIEW = "PURCHASE_VIEW"
PERM_PURCHASE_CREATE = "PURCHASE_CREATE"
PERM_PURCHASE_RETURN = "PURCHASE_RETURN"

# 4. Customers & Khata
PERM_CUSTOMER_VIEW = "CUSTOMER_VIEW"
PERM_CUSTOMER_CREATE = "CUSTOMER_CREATE"
PERM_CUSTOMER_EDIT = "CUSTOMER_EDIT"
PERM_KHATA_VIEW = "KHATA_VIEW"
PERM_KHATA_PAYMENT = "KHATA_PAYMENT"

# 5. Suppliers
PERM_SUPPLIER_VIEW = "SUPPLIER_VIEW"
PERM_SUPPLIER_CREATE = "SUPPLIER_CREATE"
PERM_SUPPLIER_EDIT = "SUPPLIER_EDIT"

# 6. Reports & Analytics
PERM_REPORT_VIEW = "REPORT_VIEW"
PERM_REPORT_EXPORT = "REPORT_EXPORT"

# 7. Sales History
PERM_SALES_HISTORY_VIEW = "SALES_HISTORY_VIEW"
PERM_SALES_HISTORY_EXPORT = "SALES_HISTORY_EXPORT"

# 8. GST / Tax Reports
PERM_GST_VIEW = "GST_VIEW"

# 9. Accounting
PERM_ACCOUNTING_VIEW = "ACCOUNTING_VIEW"

# 10. Staff Management
PERM_STAFF_VIEW = "STAFF_VIEW"
PERM_STAFF_MANAGE = "STAFF_MANAGE"

# 11. Settings & Store Config
PERM_SETTINGS_VIEW = "SETTINGS_VIEW"
PERM_SETTINGS_EDIT = "SETTINGS_EDIT"

# 12. AI Assistant
PERM_AI_ASSISTANT = "AI_ASSISTANT"

# 13. Customer Outstanding
PERM_CUSTOMER_OUTSTANDING_VIEW = "CUSTOMER_OUTSTANDING_VIEW"

# All defined permissions
ALL_PERMISSIONS: Set[str] = {
    PERM_BILL_CREATE,
    PERM_BILL_VIEW,
    PERM_BILL_DELETE,
    PERM_BILL_HELD,
    PERM_INVENTORY_VIEW,
    PERM_INVENTORY_CREATE,
    PERM_INVENTORY_EDIT,
    PERM_INVENTORY_DELETE,
    PERM_PURCHASE_VIEW,
    PERM_PURCHASE_CREATE,
    PERM_PURCHASE_RETURN,
    PERM_CUSTOMER_VIEW,
    PERM_CUSTOMER_CREATE,
    PERM_CUSTOMER_EDIT,
    PERM_CUSTOMER_OUTSTANDING_VIEW,
    PERM_KHATA_VIEW,
    PERM_KHATA_PAYMENT,
    PERM_SUPPLIER_VIEW,
    PERM_SUPPLIER_CREATE,
    PERM_SUPPLIER_EDIT,
    PERM_REPORT_VIEW,
    PERM_REPORT_EXPORT,
    PERM_SALES_HISTORY_VIEW,
    PERM_SALES_HISTORY_EXPORT,
    PERM_GST_VIEW,
    PERM_ACCOUNTING_VIEW,
    PERM_STAFF_VIEW,
    PERM_STAFF_MANAGE,
    PERM_SETTINGS_VIEW,
    PERM_SETTINGS_EDIT,
    PERM_AI_ASSISTANT,
}

# Standard Roles
ROLE_OWNER = "OWNER"
ROLE_ACCOUNTANT = "ACCOUNTANT"
ROLE_PHARMACIST = "PHARMACIST"
ROLE_BILLING_STAFF = "BILLING_STAFF"
ROLE_INVENTORY_STAFF = "INVENTORY_STAFF"

# Normalizing role strings
def normalize_role(role_name: Optional[str]) -> str:
    if not role_name:
        return ROLE_PHARMACIST
    norm = role_name.strip().upper().replace(" ", "_").replace("-", "_")
    if norm in ["OWNER", "ADMIN"]:
        return ROLE_OWNER
    if norm in ["ACCOUNTANT", "ACCOUNTS", "ACCOUNTING", "CA", "BOOKKEEPER", "FINANCE"]:
        return ROLE_ACCOUNTANT
    if norm in ["PHARMACIST"]:
        return ROLE_PHARMACIST
    if norm in ["BILLING_STAFF", "BILLING_MANAGER", "BILLING", "CASHIER"]:
        return ROLE_BILLING_STAFF
    if norm in ["INVENTORY_STAFF", "STORE_ASSISTANT", "INVENTORY", "STORE_STAFF", "STOCK_MANAGER"]:
        return ROLE_INVENTORY_STAFF
    return norm

# Base Role -> Permissions mapping
ROLE_DEFAULT_PERMISSIONS: Dict[str, Set[str]] = {
    ROLE_OWNER: {"*"} | ALL_PERMISSIONS,
    
    ROLE_ACCOUNTANT: {
        PERM_REPORT_VIEW,
        PERM_REPORT_EXPORT,
        PERM_SALES_HISTORY_VIEW,
        PERM_SALES_HISTORY_EXPORT,
        PERM_KHATA_VIEW,
        PERM_KHATA_PAYMENT,
        PERM_CUSTOMER_VIEW,
        PERM_CUSTOMER_OUTSTANDING_VIEW,
        PERM_SUPPLIER_VIEW,
        PERM_PURCHASE_VIEW,
        PERM_GST_VIEW,
        PERM_ACCOUNTING_VIEW,
        PERM_INVENTORY_VIEW,
    },
    
    ROLE_PHARMACIST: {
        PERM_BILL_CREATE,
        PERM_BILL_VIEW,
        PERM_BILL_HELD,
        PERM_INVENTORY_VIEW,
        PERM_CUSTOMER_VIEW,
        PERM_CUSTOMER_CREATE,
        PERM_CUSTOMER_EDIT,
        PERM_AI_ASSISTANT,
    },
    
    ROLE_BILLING_STAFF: {
        PERM_BILL_CREATE,
        PERM_BILL_VIEW,
        PERM_BILL_HELD,
        PERM_SALES_HISTORY_VIEW,
        PERM_INVENTORY_VIEW,
        PERM_CUSTOMER_VIEW,
        PERM_CUSTOMER_CREATE,
        PERM_CUSTOMER_EDIT,
    },
    
    ROLE_INVENTORY_STAFF: {
        PERM_INVENTORY_VIEW,
        PERM_INVENTORY_CREATE,
        PERM_INVENTORY_EDIT,
        PERM_INVENTORY_DELETE,
        PERM_PURCHASE_VIEW,
        PERM_PURCHASE_CREATE,
        PERM_PURCHASE_RETURN,
        PERM_SUPPLIER_VIEW,
        PERM_SUPPLIER_CREATE,
        PERM_SUPPLIER_EDIT,
    },
}

def get_role_permissions(role: str, custom_permissions_json: Optional[str] = None) -> Set[str]:
    """
    Computes effective permissions for a given role, taking into account
    any custom permission overrides stored as JSON.
    """
    normalized = normalize_role(role)
    perms = set(ROLE_DEFAULT_PERMISSIONS.get(normalized, ROLE_DEFAULT_PERMISSIONS[ROLE_PHARMACIST]))
    
    if custom_permissions_json:
        try:
            custom_list = json.loads(custom_permissions_json)
            if isinstance(custom_list, list):
                perms.update(custom_list)
        except Exception:
            pass
            
    return perms
