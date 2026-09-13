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
    UniqueConstraint,
    func,
    text,
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
        Index("idx_products_user_deleted", "user_id", "is_deleted"),
        Index("idx_products_user_name_prefix", "user_id", "product_name"),
        Index("idx_products_user_brand_prefix", "user_id", "brand"),
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
    barcode = Column(String, nullable=True, index=True)

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
    reminder_frequency = Column(String, default="twice_weekly")
    notification_time = Column(String, default="09:00")
    digest_enabled = Column(Boolean, default=True, nullable=False)
    digest_days = Column(String, default="Tuesday,Friday", nullable=True)
    digest_time = Column(String, default="09:00", nullable=True)
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

    is_split_payment = Column(Boolean, default=False, nullable=False)

    # Multi-User Staff Attribution
    staff_id = Column(Integer, ForeignKey("staff_members.id", ondelete="SET NULL"), nullable=True, index=True)
    staff_name = Column(String, nullable=True)

    # Data Migration & Historical Billing
    is_historical = Column(Boolean, default=False, nullable=False, index=True)
    transaction_source = Column(String(50), default="LIVE_BILLING", nullable=False, index=True)  # LIVE_BILLING, IMPORTED_HISTORICAL
    migration_id = Column(Integer, ForeignKey("data_migrations.id", ondelete="SET NULL"), nullable=True, index=True)
    original_bill_number = Column(String(100), nullable=True, index=True)

    # Export Status
    is_exported = Column(Boolean, default=False, nullable=False, index=True)
    exported_at = Column(DateTime, nullable=True, index=True)

    # Concurrency & Idempotency Protection
    idempotency_key = Column(String(128), nullable=True, index=True)

    # Relationships
    user = relationship("User", back_populates="sales")
    staff = relationship("StaffMember")
    migration = relationship("DataMigration", back_populates="sales")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    payments = relationship("SalePayment", back_populates="sale", cascade="all, delete-orphan")
    returns = relationship(
        "SaleReturn",
        back_populates="sale",
        cascade="all, delete-orphan",
    )


class SalePayment(Base):
    """
    Individual payment allocation for a sale (CASH, UPI, CARD, CREDIT).
    Supports single payment and split-payment transactions atomically.
    """
    __tablename__ = "sale_payments"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    payment_method = Column(String, nullable=False)  # CASH, UPI, CARD, CREDIT
    amount = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    sale = relationship("Sale", back_populates="payments")
    user = relationship("User")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)  # Nullable for historical legacy imports

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

    # Historical Migration metadata
    is_historical = Column(Boolean, default=False, nullable=False, index=True)
    migration_id = Column(Integer, ForeignKey("data_migrations.id", ondelete="SET NULL"), nullable=True, index=True)

    # Relationships
    sale = relationship("Sale", back_populates="items")
    product = relationship("Product")
    migration = relationship("DataMigration")
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
    notification_status = Column(String, default="PENDING")
    notification_error = Column(Text, nullable=True)
    notified_at = Column(DateTime, nullable=True)
    notification_provider = Column(String, nullable=True)


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


class StaffMember(Base):
    __tablename__ = "staff_members"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    username = Column(String, nullable=True, index=True)
    password = Column(String, nullable=True)  # bcrypt hashed password
    encrypted_password = Column(Text, nullable=True)  # Fernet encrypted password for Owner-only retrieval
    role = Column(String, nullable=False, default="PHARMACIST")  # OWNER, PHARMACIST, BILLING_STAFF, INVENTORY_STAFF
    status = Column(String, nullable=False, default="ACTIVE")  # ACTIVE, INACTIVE
    permissions_json = Column(Text, nullable=True)  # Optional JSON list of custom permission overrides
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class StoreBranch(Base):
    __tablename__ = "store_branches"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    branch_name = Column(String, nullable=False)
    code = Column(String, nullable=True, default="BR-01")
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    is_main = Column(Boolean, default=False)
    status = Column(String, nullable=False, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class CaProfile(Base):
    __tablename__ = "ca_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    ca_email = Column(String, nullable=False)
    ca_name = Column(String, nullable=True)
    ca_phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")


class CaShareLog(Base):
    __tablename__ = "ca_share_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    sender_email = Column(String, nullable=True)
    ca_email = Column(String, nullable=False)
    reports_shared = Column(Text, nullable=False)  # JSON formatted list of report names
    date_range_label = Column(String, nullable=False, default="Custom Range")
    date_range_start = Column(DateTime, nullable=True)
    date_range_end = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="SENT", index=True)  # SENT, FAILED
    sent_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)

    user = relationship("User")


class UserGoogleOAuth(Base):
    __tablename__ = "user_google_oauth"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    google_email = Column(String, nullable=False)
    encrypted_refresh_token = Column(Text, nullable=False)
    scopes = Column(Text, nullable=True)
    connected_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")


class PrinterDevice(Base):
    __tablename__ = "printer_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    device_name = Column(String, nullable=False)  # User-friendly label (e.g. "Counter 1 Thermal Printer")
    printer_system_name = Column(String, nullable=False)  # OS spooler name (e.g. "POS-80", "XP-58", "Microsoft Print to PDF")
    connection_type = Column(String, nullable=False, default="USB")  # USB, BLUETOOTH, NETWORK
    paper_size = Column(String, nullable=False, default="80mm")  # 58mm, 80mm
    is_default = Column(Boolean, nullable=False, default=True)
    is_online = Column(Boolean, nullable=False, default=False)
    last_seen_at = Column(DateTime, nullable=True)

    # Detailed hardware configuration (JSON string)
    # { "copies": 1, "cut_paper": true, "open_cash_drawer": false, "character_encoding": "CP437", "auto_print": false }
    settings_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    print_jobs = relationship("PrintJob", back_populates="printer", cascade="all, delete-orphan")


class PrintJob(Base):
    __tablename__ = "print_jobs"
    __table_args__ = (
        Index("idx_print_jobs_user_status", "user_id", "status"),
        Index("idx_print_jobs_sale", "sale_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    printer_id = Column(Integer, ForeignKey("printer_devices.id"), nullable=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=True, index=True)
    invoice_number = Column(String, nullable=False, index=True)

    # Statuses: PENDING, PRINTING, PRINTED, FAILED, CANCELLED
    status = Column(String, nullable=False, default="PENDING", index=True)

    copies = Column(Integer, nullable=False, default=1)
    paper_size = Column(String, nullable=False, default="80mm")  # 58mm, 80mm

    # Frozen JSON payload of finalized bill + shop details (guarantees zero recalculation discrepancies)
    payload_json = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    claimed_at = Column(DateTime, nullable=True)
    printed_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)

    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)

    user = relationship("User")
    printer = relationship("PrinterDevice", back_populates="print_jobs")
    sale = relationship("Sale")


class HeldBill(Base):
    """
    Temporarily parked draft bills allowing pharmacists to serve other customers.
    Holding a bill NEVER deducts inventory, creates a Sale, or affects reports.
    """
    __tablename__ = "held_bills"
    __table_args__ = (
        Index("idx_held_bills_user_status", "user_id", "status"),
        Index("idx_held_bills_created_at", "created_at"),
        UniqueConstraint("user_id", "held_bill_number", name="uq_held_bills_user_bill_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    held_bill_number = Column(String, index=True, nullable=False)

    # Statuses: HELD, RESUMED, COMPLETED, CANCELLED
    status = Column(String, nullable=False, default="HELD", index=True)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)

    doctor_name = Column(String, nullable=True)
    doctor_reg_no = Column(String, nullable=True)

    payment_method = Column(String, default="CASH")
    is_interstate = Column(Boolean, default=False)

    discount_type = Column(String, nullable=True)  # "flat", "percent"
    discount_value = Column(Float, nullable=False, default=0.0)

    # Estimated figures (used for display, recalculated on resume)
    estimated_subtotal = Column(Float, nullable=False, default=0.0)
    estimated_discount = Column(Float, nullable=False, default=0.0)
    estimated_tax = Column(Float, nullable=False, default=0.0)
    estimated_total = Column(Float, nullable=False, default=0.0)

    notes = Column(Text, nullable=True)

    # Full cart state snapshot (raw JSON of cart items, customer, doctor, settings)
    snapshot_json = Column(Text, nullable=True)
    split_payments_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resumed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    completed_sale_id = Column(Integer, ForeignKey("sales.id"), nullable=True)

    user = relationship("User")
    customer = relationship("Customer")
    items = relationship("HeldBillItem", back_populates="held_bill", cascade="all, delete-orphan")
    completed_sale = relationship("Sale")

    @property
    def split_payments(self):
        if self.split_payments_json:
            try:
                import json
                return json.loads(self.split_payments_json)
            except Exception:
                return None
        return None


class HeldBillItem(Base):
    """Line items preserved in a held bill for zero-loss restoration."""
    __tablename__ = "held_bill_items"

    id = Column(Integer, primary_key=True, index=True)
    held_bill_id = Column(Integer, ForeignKey("held_bills.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    product_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_type = Column(String, nullable=False, default="strip")  # "strip", "loose_tablet"
    unit_price = Column(Float, nullable=False)
    discount = Column(Float, default=0.0)

    tablets_per_strip = Column(Integer, nullable=True, default=10)
    batch_number = Column(String, nullable=True)
    expiry_date = Column(String, nullable=True)
    hsn_code = Column(String, nullable=True, default="3004")
    gst_percentage = Column(Float, default=0.0)

    estimated_line_total = Column(Float, nullable=False, default=0.0)

    held_bill = relationship("HeldBill", back_populates="items")
    product = relationship("Product")


class BackupRecord(Base):
    """Metadata tracking for database snapshots and backups."""
    __tablename__ = "backup_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    backup_id = Column(String, unique=True, index=True, nullable=False)  # UUID string
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size_bytes = Column(Integer, default=0, nullable=False)
    backup_type = Column(String, default="MANUAL", nullable=False)  # MANUAL, AUTOMATIC, PRE_RESTORE_SAFETY
    status = Column(String, default="SUCCESS", nullable=False)  # SUCCESS, FAILED, RESTORED
    backup_version = Column(Integer, default=1, nullable=False)
    schema_version = Column(Integer, default=1, nullable=False)
    app_version = Column(String, default="1.0.0", nullable=False)
    checksum_sha256 = Column(String, nullable=False)
    record_counts_json = Column(Text, nullable=True)  # JSON string of table counts
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, nullable=True)
    created_by_name = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User")


class RestoreLog(Base):
    """Audit log tracking database restore operations."""
    __tablename__ = "restore_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    backup_id = Column(String, nullable=False)
    safety_backup_id = Column(String, nullable=True)
    initiated_by_name = Column(String, nullable=True)
    status = Column(String, default="STARTED", nullable=False)  # STARTED, VALIDATING, RESTORED, FAILED, ROLLED_BACK
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    verification_summary_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    user = relationship("User")


class DataMigration(Base):
    """Tracks historical data migration batches from legacy pharmacy software."""
    __tablename__ = "data_migrations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    migration_code = Column(String(50), unique=True, index=True, nullable=False)  # e.g. MG-20260907-001
    migration_type = Column(String(50), default="OLD_BILLS", nullable=False)  # OLD_BILLS, MEDICINES, SUPPLIERS, CUSTOMERS, INVENTORY
    source_software = Column(String(50), default="OTHER")  # MARG, VYAPAR, TALLY, PHARMA_RACK, OTHER
    file_name = Column(String(255), nullable=False)
    file_format = Column(String(20), nullable=False)  # PDF, CSV, XLSX
    file_size_bytes = Column(Integer, default=0)

    status = Column(String(50), default="PREVIEW", nullable=False, index=True)  # PREVIEW, PROCESSING, COMPLETED, FAILED, ROLLED_BACK

    # Real-Time Processing Stages & Live Progress
    current_stage = Column(String(50), default="uploading", nullable=False)
    current_stage_label = Column(String(100), default="Uploading document", nullable=False)
    current_message = Column(String(255), default="DAWAI FLOW AI is preparing your document...", nullable=False)
    processed_count = Column(Integer, default=0, nullable=False)
    total_count = Column(Integer, default=0, nullable=False)
    is_large_file = Column(Boolean, default=False, nullable=False)

    total_records_detected = Column(Integer, default=0)
    total_records_parsed = Column(Integer, default=0)
    total_records_imported = Column(Integer, default=0)
    total_duplicates_skipped = Column(Integer, default=0)
    total_errors = Column(Integer, default=0)
    total_amount_imported = Column(Float, default=0.0)

    progress_percentage = Column(Integer, default=0)
    preview_data_json = Column(Text, nullable=True)  # JSON snapshot of parsed preview
    summary_notes = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    rolled_back_at = Column(DateTime, nullable=True)

    user = relationship("User")
    sales = relationship("Sale", back_populates="migration")
    errors = relationship("MigrationError", back_populates="migration", cascade="all, delete-orphan")


class MigrationError(Base):
    """Detailed error / warning record for problematic migration rows."""
    __tablename__ = "migration_errors"

    id = Column(Integer, primary_key=True, index=True)
    migration_id = Column(Integer, ForeignKey("data_migrations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    row_number = Column(Integer, nullable=True)
    bill_identifier = Column(String(100), nullable=True)
    error_type = Column(String(50), default="PARSE_ERROR")  # PARSE_ERROR, DUPLICATE_BILL, INVALID_DATE, INVALID_AMOUNT, MEDICINE_NOT_FOUND
    raw_record_json = Column(Text, nullable=True)
    reason = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    migration = relationship("DataMigration", back_populates="errors")
    user = relationship("User")


