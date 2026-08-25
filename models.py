from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    shop_name = Column(String, nullable=False)
    owner_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    # Pharmacy GST details and default rate for new bills.
    gst_number = Column(String, nullable=True)
    gstin = Column(String, nullable=True, default="07AABCE1234F1Z5")
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    default_gst_percentage = Column(Float, default=12.0, nullable=False)
    
    # Extended Pharmacy Profile & License Fields
    drug_license_no = Column(String, nullable=True, default="DL-2026-PHARMA-01")
    logo_url = Column(String, nullable=True)
    terms_and_conditions = Column(Text, nullable=True, default="1. Goods once sold will not be taken back without original bill.\n2. Expiry dates checked at sales time.")
    
    # Billing Preferences
    default_payment_method = Column(String, default="CASH", nullable=False)
    invoice_prefix = Column(String, default="INV", nullable=False)
    show_gst_breakdown = Column(Boolean, default=True, nullable=False)
    show_hsn = Column(Boolean, default=True, nullable=False)
    show_batch_expiry = Column(Boolean, default=True, nullable=False)
    show_customer_info = Column(Boolean, default=True, nullable=False)
    
    # Notification & System Preferences
    expiry_alerts_enabled = Column(Boolean, default=True, nullable=False)
    low_stock_alerts_enabled = Column(Boolean, default=True, nullable=False)
    billing_notifications_enabled = Column(Boolean, default=True, nullable=False)
    delete_confirmation_required = Column(Boolean, default=True, nullable=False)
    auto_save_enabled = Column(Boolean, default=True, nullable=False)
    preferred_language = Column(String, default="en", nullable=False)
    preferred_theme = Column(String, default="light", nullable=False)

    products = relationship("Product", back_populates="owner", foreign_keys="[Product.user_id]")
    sales = relationship("Sale", back_populates="user")
    sale_returns = relationship("SaleReturn", back_populates="user")
    customers = relationship("Customer", back_populates="user")
    notification_settings = relationship(
        "NotificationSettings",
        back_populates="user",
        uselist=False,
    )
    transactions = relationship(
        "InventoryTransaction",
        back_populates="shop",
    )


class MedicineCatalog(Base):
    """
    Global reference/lookup medicine catalog table.
    Used purely for search and autocomplete when adding stock or creating bills.
    Contains NO shop-specific inventory stock quantities or batch numbers.
    """
    __tablename__ = "medicine_catalog"
    __table_args__ = (
        Index("idx_catalog_name", "product_name"),
        Index("idx_catalog_brand", "brand"),
        Index("idx_catalog_comp", "composition"),
    )

    id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String, nullable=False, index=True)
    brand = Column(String, nullable=True)
    category = Column(String, nullable=False, default="allopathy")
    hsn_code = Column(String, nullable=False, default="3004")
    gst_rate = Column(Float, nullable=False, default=12.0)
    default_price = Column(Float, default=0.0, nullable=False)
    tablets_per_strip = Column(Integer, nullable=True, default=10)
    units_per_pack = Column(Integer, nullable=True)
    price_per_unit = Column(Float, nullable=True)
    is_countable = Column(Boolean, default=True, nullable=False)
    needs_review = Column(Boolean, default=False, nullable=False)
    pack_size_label = Column(String, nullable=True)
    composition = Column(String, nullable=True)
    verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("idx_products_user_name", "user_id", "product_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    product_name = Column(String, nullable=False)
    brand = Column(String, nullable=True)
    category = Column(String, nullable=False)
    batch_number = Column(String, nullable=True)
    quantity = Column(Integer, default=1, nullable=False)

    # Indian GST & HSN Fields
    hsn_code = Column(String, nullable=False, default="3004")
    gst_rate = Column(Float, nullable=False, default=12.0)

    # Price paid to the supplier from an invoice.
    purchase_price = Column(Float, default=0, nullable=False)

    # Current/default retail selling price per unit (strip).
    unit_price = Column(Float, default=0, nullable=False)
    # Per-tablet / per-pill calculated price
    price_per_unit = Column(Float, nullable=True)
    units_per_pack = Column(Integer, nullable=True)
    is_countable = Column(Boolean, default=True, nullable=False)
    needs_review = Column(Boolean, default=False, nullable=False)
    gst_percentage = Column(Float, default=12.0, nullable=False)

    # Needed for strip-versus-loose-tablet billing.
    tablets_per_strip = Column(Integer, nullable=True)
    loose_tablet_price = Column(Float, nullable=True)
    # Tablets from opened strips. Sealed strip stock remains in quantity.
    loose_tablet_stock = Column(Integer, default=0, nullable=False)
    total_price = Column(Float, default=0, nullable=False)
    manufacturing_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=False)

    days_remaining = Column(Integer, default=0)
    status = Column(String, default="Safe")

    image_path = Column(String, nullable=True)
    ocr_text = Column(String, nullable=True)

    # Data Trust & Master Verification Fields
    pack_size_label = Column(String, nullable=True)
    composition = Column(String, nullable=True)
    verified = Column(Boolean, default=False, nullable=False)
    pack_size_verified = Column(Boolean, default=False, nullable=False)
    price_last_updated = Column(DateTime, default=datetime.utcnow)

    # Supplier & Document Traceability Fields
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True, index=True)
    invoice_number = Column(String, nullable=True, index=True)

    # Soft-Delete & 60-Day Recovery Fields
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True, index=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    owner = relationship("User", back_populates="products", foreign_keys=[user_id])
    supplier = relationship("Supplier", back_populates="products")
    document = relationship("Document", back_populates="products")
    transactions = relationship(
        "InventoryTransaction",
        back_populates="product",
    )


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"

    id = Column(Integer, primary_key=True, index=True)

    # Human-readable ID for bills, e.g. TXN-20260731-AB12CD34
    transaction_id = Column(String, unique=True, index=True, nullable=False)

    # shop_id represents the logged-in user in the current architecture.
    shop_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    # "sell" or "purchase"
    transaction_type = Column(String, nullable=False)

    quantity = Column(Integer, default=1)

    # Retail selling price used when creating customer bills.
    unit_price = Column(Float, default=0)

    # Supplier purchase price extracted from an invoice.
    purchase_price = Column(Float, default=0)

    total_price = Column(Float, default=0)

    discount_type = Column(String, nullable=True)
    discount_value = Column(Float, nullable=True)

    final_price = Column(Float, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    shop = relationship("User", back_populates="transactions")
    product = relationship("Product", back_populates="transactions")


class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    enabled = Column(Boolean, default=True)
    notify_before_days = Column(Integer, default=7)
    reminder_frequency = Column(String, default="daily")
    notification_time = Column(String, default="08:00")
    sound = Column(Boolean, default=True)
    vibration = Column(Boolean, default=True)

    user = relationship("User", back_populates="notification_settings")


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    token = Column(String, nullable=False)

    user = relationship("User")


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    bill_number = Column(String, unique=True, index=True, nullable=False)
    gst_number = Column(String, nullable=True)
    gst_percentage = Column(Float, nullable=False, default=0.0)

    discount_type = Column(String, nullable=True)

    discount_value = Column(Float, nullable=False, default=0.0)

    doctor_name = Column(String, nullable=True)

    doctor_reg_no = Column(String, nullable=True)

    return_status = Column(
        String,
        nullable=False,
        default="completed",
    )
    # Financial Summaries
    subtotal = Column(Float, nullable=False, default=0.0)
    discount_amount = Column(Float, nullable=False, default=0.0)
    tax_amount = Column(Float, nullable=False, default=0.0)
    total_amount = Column(Float, nullable=False, default=0.0)

    # GST Compliance Fields
    is_interstate = Column(Boolean, default=False)
    total_taxable_value = Column(Float, nullable=False, default=0.0)
    total_cgst = Column(Float, nullable=False, default=0.0)
    total_sgst = Column(Float, nullable=False, default=0.0)
    total_igst = Column(Float, nullable=False, default=0.0)
    tax_summary_json = Column(Text, nullable=True)

    # Quick Counter Defaults (Nullable for Desktop completion later)
    payment_method = Column(String, default="CASH")  # CASH, UPI, CARD, CREDIT, PENDING
    payment_status = Column(String, default="PAID", nullable=False, index=True)  # PAID, PENDING, SETTLED
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    # Metadata
    is_completed_on_mobile = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="sales")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    returns = relationship(
    "SaleReturn",
    back_populates="sale",
    cascade="all, delete-orphan",
)

class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    # Frozen snapshot data
    product_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    discount = Column(Float, default=0.0)
    total_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=True, default=0.0)
    batch_number = Column(String, nullable=True)
    # strip or loose_tablet
    unit_type = Column(String, nullable=False, default="strip")

    # Snapshot values used for this exact bill item.
    tablets_per_strip = Column(Integer, nullable=True)
    hsn_code = Column(String, nullable=False, default="3004")
    gst_percentage = Column(Float, nullable=False, default=0.0)
    gst_amount = Column(Float, nullable=False, default=0.0)

    # Detailed GST Breakdown
    taxable_value = Column(Float, nullable=False, default=0.0)
    cgst_rate = Column(Float, nullable=False, default=0.0)
    cgst_amount = Column(Float, nullable=False, default=0.0)
    sgst_rate = Column(Float, nullable=False, default=0.0)
    sgst_amount = Column(Float, nullable=False, default=0.0)
    igst_rate = Column(Float, nullable=False, default=0.0)
    igst_amount = Column(Float, nullable=False, default=0.0)
    total_with_tax = Column(Float, nullable=False, default=0.0)

    # Relationships
    sale = relationship("Sale", back_populates="items")
    product = relationship("Product")
    return_items = relationship("SaleReturnItem", back_populates="sale_item")
class SaleReturn(Base):
    __tablename__ = "sale_returns"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Optional reason entered by the pharmacist.
    reason = Column(Text, nullable=True)

    # Sum of all returned line totals in this return action.
    return_amount = Column(Float, nullable=False, default=0.0)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    sale = relationship("Sale", back_populates="returns")
    user = relationship("User", back_populates="sale_returns")
    items = relationship(
        "SaleReturnItem",
        back_populates="sale_return",
        cascade="all, delete-orphan",
    )


class SaleReturnItem(Base):
    __tablename__ = "sale_return_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_return_id = Column(
        Integer,
        ForeignKey("sale_returns.id"),
        nullable=False,
        index=True,
    )
    sale_item_id = Column(
        Integer,
        ForeignKey("sale_items.id"),
        nullable=False,
        index=True,
    )
    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )

    # Quantity returned to the same batch’s stock.
    quantity = Column(Integer, nullable=False)

    # Frozen per-unit amount refunded for this return.
    unit_price = Column(Float, nullable=False)
    return_total = Column(Float, nullable=False)

    sale_return = relationship("SaleReturn", back_populates="items")
    sale_item = relationship("SaleItem", back_populates="return_items")
    product = relationship("Product")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    name = Column(String, nullable=False)
    phone = Column(String, index=True, nullable=False)
    email = Column(String, nullable=True)
    address = Column(String, nullable=True)

    # Fixed patient discount auto-applied on future bills (e.g., 10.0 for 10%)
    fixed_discount_percent = Column(Float, default=0.0, nullable=False)
    # Total outstanding / credit balance pending collection
    pending_amount = Column(Float, default=0.0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="customers")


class HsnTaxRate(Base):
    """
    Reference table for Indian GST rates mapped to HSN codes.
    Easily expandable as GST council rates or HSN classifications change.
    """
    __tablename__ = "hsn_tax_rates"

    id = Column(Integer, primary_key=True, index=True)
    hsn_code = Column(String(10), unique=True, index=True, nullable=False)
    description = Column(String, nullable=False)
    gst_rate = Column(Float, nullable=False)
    category = Column(String, nullable=True, default="pharma")
    is_life_saving = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UnmappedHsnLog(Base):
    """
    Logs unknown or unmapped HSN codes encountered during billing or stock addition
    so admin can review and add them to hsn_tax_rates.
    """
    __tablename__ = "unmapped_hsn_logs"

    id = Column(Integer, primary_key=True, index=True)
    hsn_code = Column(String(10), index=True, nullable=False)
    product_name = Column(String, nullable=True)
    user_id = Column(Integer, nullable=True)
    entered_gst_rate = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ==========================================
# SUPPLIER & DOCUMENT MANAGEMENT MODELS
# ==========================================

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    name = Column(String, nullable=False, index=True)
    contact_person = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    gstin = Column(String, nullable=True, index=True)
    state = Column(String, nullable=True, default="Delhi")
    payment_terms = Column(String, nullable=True, default="Net 30")
    notes = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="Active")  # Active, Inactive

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    documents = relationship("Document", back_populates="supplier")
    products = relationship("Product", back_populates="supplier")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=True, index=True)

    title = Column(String, nullable=False)
    doc_type = Column(String, nullable=False, default="purchase_invoice")  # purchase_invoice, supplier_bill, sales_invoice, medicine_doc, scanned_bill, other
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # application/pdf, image/jpeg, image/png
    file_size = Column(Integer, default=0)

    invoice_number = Column(String, nullable=True, index=True)
    invoice_date = Column(Date, nullable=True)
    total_amount = Column(Float, default=0.0)
    item_count = Column(Integer, default=0)

    ocr_raw_json = Column(Text, nullable=True)
    ocr_status = Column(String, nullable=False, default="Processing")  # Processing, Needs Review, Verified, Failed, Archived
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    supplier = relationship("Supplier", back_populates="documents")
    products = relationship("Product", back_populates="document")


class PilotLead(Base):
    __tablename__ = "pilot_leads"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    pharmacy_name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    current_billing_method = Column(String, nullable=False)  # Paper / Manual, Marg ERP, MargBooks, Other
    bills_per_day = Column(String, nullable=False)  # Under 50, 50–100, 100–200, 200+
    biggest_problem = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ==========================================
# ERP PRIORITY 1 MODULES
# ==========================================

class PurchaseInvoice(Base):
    __tablename__ = "purchase_invoices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)

    invoice_number = Column(String, nullable=False, index=True)
    invoice_date = Column(Date, nullable=False)
    total_amount = Column(Float, nullable=False, default=0.0)
    tax_amount = Column(Float, nullable=False, default=0.0)
    payment_status = Column(String, nullable=False, default="UNPAID")  # PAID, UNPAID, PARTIAL
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    supplier = relationship("Supplier")
    items = relationship("PurchaseItem", back_populates="invoice", cascade="all, delete-orphan")


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id = Column(Integer, primary_key=True, index=True)
    purchase_invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    batch_number = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    purchase_price = Column(Float, nullable=False, default=0.0)
    mrp = Column(Float, nullable=False, default=0.0)
    gst_rate = Column(Float, nullable=False, default=12.0)
    expiry_date = Column(Date, nullable=False)

    invoice = relationship("PurchaseInvoice", back_populates="items")
    product = relationship("Product")


class SupplierPayment(Base):
    __tablename__ = "supplier_payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)

    amount_paid = Column(Float, nullable=False)
    payment_method = Column(String, nullable=False, default="CASH")  # CASH, UPI, BANK_TRANSFER, CHEQUE
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    supplier = relationship("Supplier")


class CustomerPayment(Base):
    __tablename__ = "customer_payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=True, index=True)

    amount_paid = Column(Float, nullable=False)
    payment_method = Column(String, nullable=False, default="CASH")  # CASH, UPI, CARD
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    customer = relationship("Customer")
    sale = relationship("Sale")


class PurchaseReturn(Base):
    __tablename__ = "purchase_returns"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    purchase_invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), nullable=True, index=True)

    total_returned_value = Column(Float, nullable=False, default=0.0)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    supplier = relationship("Supplier")
    invoice = relationship("PurchaseInvoice")
    items = relationship("PurchaseReturnItem", back_populates="purchase_return", cascade="all, delete-orphan")


class PurchaseReturnItem(Base):
    __tablename__ = "purchase_return_items"

    id = Column(Integer, primary_key=True, index=True)
    purchase_return_id = Column(Integer, ForeignKey("purchase_returns.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    batch_number = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    purchase_price = Column(Float, nullable=False, default=0.0)

    purchase_return = relationship("PurchaseReturn", back_populates="items")
    product = relationship("Product")