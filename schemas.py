from datetime import datetime
from typing import List, Literal, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, model_validator, field_validator


# ---------------- USER SCHEMAS ---------------- #

class UserCreate(BaseModel):
    shop_name: str
    owner_name: str
    email: str
    password: str
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class User(BaseModel):
    id: int
    email: str
    shop_name: str
    owner_name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    drug_license_no: Optional[str] = None
    logo_url: Optional[str] = None
    terms_and_conditions: Optional[str] = None
    
    default_payment_method: str = "CASH"
    invoice_prefix: str = "INV"
    show_gst_breakdown: bool = True
    show_hsn: bool = True
    show_batch_expiry: bool = True
    show_customer_info: bool = True
    
    expiry_alerts_enabled: bool = True
    low_stock_alerts_enabled: bool = True
    billing_notifications_enabled: bool = True
    delete_confirmation_required: bool = True
    auto_save_enabled: bool = True
    preferred_language: str = "en"
    preferred_theme: str = "light"
    
    # Session & RBAC metadata
    staff_id: Optional[int] = None
    role: Optional[str] = "OWNER"
    name: Optional[str] = None
    is_owner: bool = True
    permissions: Optional[List[str]] = None

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    shop_name: Optional[str] = None
    owner_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    drug_license_no: Optional[str] = None
    logo_url: Optional[str] = None
    terms_and_conditions: Optional[str] = None
    
    default_payment_method: Optional[str] = None
    invoice_prefix: Optional[str] = None
    show_gst_breakdown: Optional[bool] = None
    show_hsn: Optional[bool] = None
    show_batch_expiry: Optional[bool] = None
    show_customer_info: Optional[bool] = None
    
    expiry_alerts_enabled: Optional[bool] = None
    low_stock_alerts_enabled: Optional[bool] = None
    billing_notifications_enabled: Optional[bool] = None
    delete_confirmation_required: Optional[bool] = None
    auto_save_enabled: Optional[bool] = None
    preferred_language: Optional[str] = None
    preferred_theme: Optional[str] = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


# ---------------- TOKEN SCHEMAS ---------------- #

class Token(BaseModel):
    access_token: str
    token_type: str


# ---------------- PRODUCT SCHEMAS ---------------- #

class ProductBase(BaseModel):
    product_name: str
    brand: Optional[str] = None
    category: str

    hsn_code: Optional[str] = "3004"
    gst_rate: Optional[float] = 12.0

    batch_number: Optional[str] = None
    quantity: int = Field(default=0)

    # Retail selling price (support both unit_price and price aliases)
    unit_price: float = Field(default=0, ge=0)
    price: Optional[float] = Field(default=None, ge=0)

    # Supplier purchase price.
    purchase_price: float = Field(default=0, ge=0)

    total_price: float = Field(default=0, ge=0)
    manufacturing_date: Optional[Any] = None
    expiry_date: Any

    days_remaining: int = 0
    status: str = "Safe"

    image_path: Optional[str] = None
    ocr_text: Optional[str] = None

    pack_size_label: Optional[str] = None
    composition: Optional[str] = None
    verified: bool = False
    pack_size_verified: bool = False
    price_last_updated: Optional[datetime] = None

    units_per_pack: Optional[int] = None
    price_per_unit: Optional[float] = None
    is_countable: bool = True
    needs_review: bool = False

    # Supplier & Document Traceability Fields
    supplier_id: Optional[int] = None
    document_id: Optional[int] = None
    invoice_number: Optional[str] = None
    barcode: Optional[str] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    product_name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    barcode: Optional[str] = None

    hsn_code: Optional[str] = None
    gst_rate: Optional[float] = None

    batch_number: Optional[str] = None
    quantity: Optional[int] = Field(default=None, gt=0)

    unit_price: Optional[float] = Field(default=None, ge=0)
    price: Optional[float] = Field(default=None, ge=0)
    total_price: Optional[float] = Field(default=None, ge=0)

    manufacturing_date: Optional[Any] = None
    expiry_date: Optional[Any] = None

    days_remaining: Optional[int] = None
    status: Optional[str] = None

    image_path: Optional[str] = None
    ocr_text: Optional[str] = None

    units_per_pack: Optional[int] = None
    price_per_unit: Optional[float] = None


class BulkGstUpdate(BaseModel):
    hsn_code: str
    gst_rate: float = Field(ge=0.0, le=28.0)


class Product(ProductBase):
    id: int
    user_id: int
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[int] = None

    class Config:
        from_attributes = True


# ---------------- INVENTORY SOFT-DELETE & RECOVERY SCHEMAS ---------------- #

class InventoryDeleteRequest(BaseModel):
    stock_ids: Optional[List[int]] = None
    product_ids: Optional[List[int]] = None

    def get_ids(self) -> List[int]:
        return self.stock_ids or self.product_ids or []


class InventoryDeleteAllRequest(BaseModel):
    confirm: bool = Field(default=False, description="Explicit confirmation flag to delete all stock")


class InventoryRestoreRequest(BaseModel):
    stock_ids: Optional[List[int]] = None
    product_ids: Optional[List[int]] = None

    def get_ids(self) -> List[int]:
        return self.stock_ids or self.product_ids or []


class DeletedProductResponse(BaseModel):
    id: int
    user_id: int
    product_name: str
    brand: Optional[str] = None
    category: str
    batch_number: Optional[str] = None
    quantity: int
    unit_price: float = 0.0
    purchase_price: float = 0.0
    expiry_date: Any
    days_remaining: int = 0
    status: str = "Safe"
    is_deleted: bool = True
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[int] = None
    days_until_permanent_delete: int = 60

    class Config:
        from_attributes = True


# ---------------- MEDICINE CATALOG SCHEMAS ---------------- #

class MedicineCatalogResponse(BaseModel):
    id: int
    product_name: str
    brand: Optional[str] = None
    category: str = "allopathy"
    hsn_code: str = "3004"
    gst_rate: float = 12.0
    default_price: float = 0.0
    tablets_per_strip: Optional[int] = 10
    units_per_pack: Optional[int] = None
    price_per_unit: Optional[float] = None
    is_countable: bool = True
    needs_review: bool = False
    pack_size_label: Optional[str] = None
    composition: Optional[str] = None
    verified: bool = False

    class Config:
        from_attributes = True


class InventoryAddRequest(BaseModel):
    catalog_id: Optional[int] = None
    product_name: str
    brand: Optional[str] = None
    category: Optional[str] = "allopathy"
    hsn_code: Optional[str] = "3004"
    gst_rate: Optional[float] = 12.0
    batch_number: str
    quantity: int = Field(gt=0)
    purchase_price: float = Field(ge=0.0)
    unit_price: float = Field(ge=0.0)
    units_per_pack: Optional[int] = None
    expiry_date: str
    manufacturing_date: Optional[str] = None
    supplier_id: Optional[int] = None
    document_id: Optional[int] = None
    invoice_number: Optional[str] = None
    duplicate_mode: Optional[str] = "auto" # "auto", "increment", "separate"


class CustomMedicineCreate(BaseModel):
    product_name: str = Field(min_length=2)
    brand: Optional[str] = None
    category: Optional[str] = "allopathy"
    composition: Optional[str] = None
    hsn_code: Optional[str] = "3004"
    gst_rate: Optional[float] = 12.0
    default_price: Optional[float] = 0.0
    tablets_per_strip: Optional[int] = 10
    pack_size_label: Optional[str] = None


class BatchInventoryAddRequest(BaseModel):
    items: List[InventoryAddRequest] = Field(min_length=1)


class DuplicateBatchCheckRequest(BaseModel):
    product_name: str
    batch_number: str


# ---------------- SELL / PURCHASE SCHEMAS ---------------- #

class TransactionCreate(BaseModel):
    product_id: int = Field(gt=0)
    transaction_type: Literal["sell", "purchase"]

    quantity: int = Field(
        gt=0,
        description="Number of units being sold or purchased.",
    )

    unit_price: float = Field(
        ge=0,
        description="Price per unit in rupees.",
    )

    discount_type: Optional[Literal["flat", "percent"]] = None
    discount_value: Optional[float] = Field(
        default=None,
        ge=0,
        description="Flat rupee discount or percentage discount.",
    )

    @model_validator(mode="after")
    def validate_discount(self):
        if self.transaction_type == "purchase":
            if self.discount_type is not None or self.discount_value is not None:
                raise ValueError("Discount is only supported for sell transactions.")

        if self.discount_type is None and self.discount_value is not None:
            raise ValueError("discount_type is required when discount_value is provided.")

        if self.discount_type is not None and self.discount_value is None:
            raise ValueError("discount_value is required when discount_type is provided.")

        if (
            self.discount_type == "percent"
            and self.discount_value is not None
            and self.discount_value > 100
        ):
            raise ValueError("Percentage discount cannot be greater than 100.")

        return self


class TransactionResponse(BaseModel):
    id: int
    transaction_id: str
    shop_id: int
    product_id: int
    transaction_type: str
    quantity: int
    unit_price: float
    discount_type: Optional[str] = None
    discount_value: Optional[float] = None
    final_price: float
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------- PHARMACY POS / GST BILL SCHEMAS ---------------- #

class SaleItemCreate(BaseModel):
    product_id: int = Field(gt=0)

    # Number of strips or individual loose tablets.
    quantity: int = Field(gt=0, default=1)

    # Leave null to use the saved product price automatically.
    # A pharmacist may override it at the counter.
    unit_price: Optional[float] = Field(default=None, ge=0.0)

    # "strip" means whole strip/pack; "loose_tablet" / "pill" means individual tablets.
    unit_type: Literal["strip", "loose_tablet", "loose", "pack", "unit", "pill"] = "strip"

    # Number of loose tablets/units contained in 1 full strip/pack.
    tablets_per_strip: Optional[int] = Field(default=None, gt=0)
    units_per_pack: Optional[int] = Field(default=None, gt=0)

    # Optional batch selection. Backend will confirm that it belongs to this shop.
    batch_number: Optional[str] = None

    # Optional per-line discount. It is applied before GST.
    discount: float = Field(default=0.0, ge=0.0)

    # Optional GST override. If absent, backend uses product GST, then shop default GST.
    gst_percentage: Optional[float] = Field(default=None, ge=0.0, le=100.0)


class SaleItemResponse(BaseModel):
    id: int
    product_id: Optional[int] = None
    product_name: str
    hsn_code: Optional[str] = "3004"
    quantity: int
    unit_type: str
    unit_price: float
    discount: float
    gst_percentage: float
    gst_amount: float
    taxable_value: float = 0.0
    cgst_rate: float = 0.0
    cgst_amount: float = 0.0
    sgst_rate: float = 0.0
    sgst_amount: float = 0.0
    igst_rate: float = 0.0
    igst_amount: float = 0.0
    total_with_tax: float = 0.0
    total_price: float
    batch_number: Optional[str] = None

    class Config:
        from_attributes = True


class PaymentAllocation(BaseModel):
    payment_method: Literal["CASH", "UPI", "CARD", "CREDIT"]
    amount: float = Field(gt=0.0)

    @field_validator('payment_method', mode='before')
    @classmethod
    def normalize_method(cls, v):
        if isinstance(v, str):
            v_clean = v.strip().upper()
            if v_clean == "PENDING":
                return "CREDIT"
            return v_clean
        return v


class PaymentAllocationResponse(BaseModel):
    id: Optional[int] = None
    payment_method: str
    amount: float

    class Config:
        from_attributes = True


class SaleCreate(BaseModel):
    items: List[SaleItemCreate] = Field(min_length=1)

    payment_method: Literal["CASH", "UPI", "CARD", "CREDIT", "PENDING", "SPLIT"] = "CASH"
    payments: Optional[List[PaymentAllocation]] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    notes: Optional[str] = None

    # Intra-state (CGST+SGST) by default. Set to True for IGST.
    is_interstate: bool = False

    # Bill-level discount, applied after line discounts and before GST.
    discount_type: Optional[Literal["flat", "percent"]] = None
    discount_value: float = Field(default=0.0, ge=0.0)

    # Optional prescription details. They are printed only when supplied.
    doctor_name: Optional[str] = None
    doctor_reg_no: Optional[str] = None

    # Optional held bill reference to mark completed upon checkout
    held_bill_id: Optional[int] = None

    # Concurrency & Idempotency Key (e.g. df_sale_1725849200_abc123)
    idempotency_key: Optional[str] = None

    @field_validator('payment_method', mode='before')
    @classmethod
    def normalize_payment_method(cls, v):
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @model_validator(mode="after")
    def validate_bill_discount(self):
        if self.discount_type is None and self.discount_value != 0:
            raise ValueError(
                "discount_type is required when discount_value is greater than 0."
            )

        if self.discount_type == "percent" and self.discount_value > 100:
            raise ValueError("Percentage discount cannot be greater than 100.")

        return self


class SaleUpdateDesktop(BaseModel):
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    payment_method: Optional[Literal["CASH", "UPI", "CARD", "CREDIT", "PENDING"]] = None
    notes: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_reg_no: Optional[str] = None


class SaleResponse(BaseModel):
    id: int
    bill_number: str
    subtotal: float
    discount_amount: float
    tax_amount: float
    total_amount: float

    # GST Compliance Summaries
    is_interstate: bool = False
    total_taxable_value: float = 0.0
    total_cgst: float = 0.0
    total_sgst: float = 0.0
    total_igst: float = 0.0
    tax_summary: Optional[List[dict]] = None
    pdf_url: Optional[str] = None

    gst_number: Optional[str] = None
    gst_percentage: float
    discount_type: Optional[str] = None
    discount_value: float

    payment_method: str
    is_split_payment: bool = False
    payments: Optional[List[PaymentAllocationResponse]] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    notes: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_reg_no: Optional[str] = None

    # Multi-User Staff Attribution
    staff_id: Optional[int] = None
    staff_name: Optional[str] = None

    items: Optional[List[SaleItemResponse]] = None

    # completed, partially_returned, or returned
    return_status: str
    created_at: datetime
    is_exported: bool = False
    exported_at: Optional[datetime] = None

    # Historical Migration metadata
    is_historical: bool = False
    transaction_source: str = "LIVE_BILLING"
    migration_id: Optional[int] = None
    original_bill_number: Optional[str] = None
    idempotency_key: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------- SALE RETURN SCHEMAS ---------------- #

class SaleReturnItemCreate(BaseModel):
    sale_item_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class SaleReturnCreate(BaseModel):
    items: List[SaleReturnItemCreate] = Field(min_length=1)
    reason: Optional[str] = Field(default=None, max_length=500)


class SaleReturnItemResponse(BaseModel):
    id: int
    sale_item_id: int
    product_id: int
    quantity: int
    unit_price: float
    return_total: float

    class Config:
        from_attributes = True


class SaleReturnResponse(BaseModel):
    id: int
    sale_id: int
    user_id: int
    reason: Optional[str] = None
    refund_amount: float
    created_at: datetime
    items: List[SaleReturnItemResponse] = []

    class Config:
        from_attributes = True


# ---------------- HSN TAX RATE SCHEMAS ---------------- #

class HsnTaxRateBase(BaseModel):
    hsn_code: str = Field(min_length=2, max_length=10)
    description: str
    gst_rate: float = Field(ge=0.0, le=28.0)
    category: Optional[str] = "pharma"
    is_life_saving: bool = False

class HsnTaxRateCreate(HsnTaxRateBase):
    pass

class HsnTaxRateResponse(HsnTaxRateBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class HsnLookupResponse(BaseModel):
    hsn_code: str
    gst_rate: float
    description: str
    is_mapped: bool
    is_life_saving: bool = False
    needs_manual_review: bool = False

class UnmappedHsnLogResponse(BaseModel):
    id: int
    hsn_code: str
    product_name: Optional[str] = None
    user_id: Optional[int] = None
    entered_gst_rate: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True
# ---------------- FCM & NOTIFICATION SCHEMAS ---------------- #

class FCMTokenRequest(BaseModel):
    user_id: int
    token: str


class NotificationSettingsCreate(BaseModel):
    enabled: bool
    notify_before_days: int
    reminder_frequency: str
    notification_time: str
    sound: bool
    vibration: bool


class NotificationSettingsResponse(NotificationSettingsCreate):
    id: int

    class Config:
        from_attributes = True


# ---------------- INVOICE SCANNER SCHEMAS ---------------- #

class InvoiceItem(BaseModel):
    product_name: str
    brand: str
    category: str
    quantity: int
    unit: str
    unit_price: float
    total_price: float
    batch_number: str
    manufacturing_date: str
    expiry_date: str
    confidence: float
    notes: str


class InvoiceData(BaseModel):
    supplier_name: str
    invoice_number: str
    invoice_date: str
    items: List[InvoiceItem]


class InvoiceScanResponse(BaseModel):
    success: bool
    data: Optional[InvoiceData] = None
    error: Optional[str] = None
# ==========================================
# EXPIRYGUARD TRANSACTION & BULK PURCHASE SCHEMAS
# ==========================================

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime

# --- SELL SCHEMAS ---
class SellItemRequest(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, default=1)
    unit_type: Optional[str] = "strip"
    tablets_per_strip: Optional[int] = None

class SellTransactionRequest(BaseModel):
    items: List[SellItemRequest]
    discount_amount: Optional[float] = 0.0
    payment_method: Optional[str] = "CASH"

class SellItemResponse(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price: float
    total_price: float

class BillResponse(BaseModel):
    bill_number: str
    subtotal: float
    discount_amount: float
    total_amount: float
    created_at: datetime
    items: List[SellItemResponse]

# --- PURCHASE SCHEMAS ---
class BulkPurchaseItemRequest(BaseModel):
    product_name: str = Field(min_length=1)
    brand: Optional[str] = None
    category: Optional[str] = "General"
    batch_number: Optional[str] = None

    quantity: int = Field(gt=0, default=1)

    # Amount paid to supplier, extracted from the invoice.
    purchase_price: float = Field(ge=0.0, default=0.0)

    # Retail price charged to the customer.
    # Keep 0 when it is unknown; never guess it from an invoice.
    selling_price: float = Field(ge=0.0, default=0.0)# ---------------- POS / COUNTER SALES SCHEMAS ---------------- #
    manufacturing_date: Optional[date] = None
    expiry_date: date

class BulkPurchaseRequest(BaseModel):
    items: List[BulkPurchaseItemRequest]
    supplier_name: Optional[str] = None
    invoice_number: Optional[str] = None
class MultiScanItemResponse(BaseModel):
    product_name: str
    brand: Optional[str] = None
    matched_inventory_id: Optional[int] = None
    price: Optional[float] = None
    strip_price: Optional[float] = None
    tablets_per_strip: Optional[int] = None
    units_per_pack: Optional[int] = None
    loose_tablet_price: Optional[float] = None
    quantity: int = 1
    confidence: float = 0.0
    matched: bool = False
    needs_review: bool = True
    reason: Optional[str] = None
    match_status: str = "NOT_FOUND"  # MATCHED, MULTIPLE_MATCHES, NOT_FOUND, LOW_CONFIDENCE
    match_type: Optional[str] = "NONE"  # EXACT_CODE, EXACT_NAME_SPECS, FUZZY_NAME, NONE
    detected_name: Optional[str] = None
    brand_name: Optional[str] = None
    generic_name: Optional[str] = None
    detected_code: Optional[str] = None
    detected_strength: Optional[str] = None
    detected_form: Optional[str] = None
    detected_pack_size: Optional[str] = None
    detected_batch: Optional[str] = None
    detected_expiry: Optional[str] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[str] = None
    days_remaining: Optional[int] = None
    stock: Optional[int] = None
    loose_tablet_stock: Optional[int] = 0
    total_tablets: Optional[int] = None
    requires_batch_selection: bool = False
    batches_available: List[Dict[str, Any]] = []
    possible_matches: List[Dict[str, Any]] = []
    batch_confidence: Optional[float] = 0.0
    engine: Optional[str] = "GEMINI_AI"
    engine_label: Optional[str] = "Dawaiflow AI"
    engine_performance: Optional[str] = None


class MultiScanResponse(BaseModel):
    success: bool
    items: List[MultiScanItemResponse]
    total_price: float
    needs_review: bool
    detected_barcodes: List[str] = []
    error: Optional[str] = None
    primary_engine: Optional[str] = "Dawaiflow AI"
    gemini_latency: Optional[float] = 0.0
    ocr_latency: Optional[float] = 0.0
    total_latency: Optional[float] = 0.0
    performance_breakdown: Optional[Dict[str, float]] = None


# ---------------- INVENTORY IMPORT SCHEMAS ---------------- #

class ImportPreviewResponse(BaseModel):
    preview_id: str
    filename: str
    total_rows: int
    file_headers: List[str]
    detected_mapping: Dict[str, str]
    unmapped_columns: List[str]
    preview_data: List[Dict[str, Any]]

class ImportConfirmRequest(BaseModel):
    preview_id: str
    column_mapping: Dict[str, str]
    on_duplicate: Optional[Literal["skip", "update", "overwrite"]] = "skip"

class ImportWarningItem(BaseModel):
    row: int
    product_name: str
    message: str

class ImportErrorItem(BaseModel):
    row: int
    raw_data: Dict[str, Any]
    reason: str

class ImportSummaryResponse(BaseModel):
    total_rows_processed: int
    rows_imported: int
    rows_updated: int
    rows_skipped: int
    warnings_count: int
    errors_count: int
    warnings: List[ImportWarningItem]
    errors: List[ImportErrorItem]


# ---------------- CUSTOMER SCHEMAS ---------------- #

class CustomerBase(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    fixed_discount_percent: float = Field(default=0.0, ge=0.0, le=100.0)

class CustomerCreate(CustomerBase):
    pass

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    fixed_discount_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)

class CustomerResponse(CustomerBase):
    id: int
    user_id: int
    pending_amount: float = 0.0
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------- SALE RETURN SCHEMAS ---------------- #

class SaleReturnItemCreate(BaseModel):
    sale_item_id: int = Field(gt=0)
    quantity: int = Field(gt=0)

class SaleReturnCreate(BaseModel):
    sale_id: Optional[int] = Field(default=None, gt=0)
    reason: Optional[str] = "Customer Return"
    items: List[SaleReturnItemCreate] = Field(min_length=1)

class SaleReturnItemResponse(BaseModel):
    id: int
    sale_item_id: int
    product_id: int
    quantity: int
    unit_price: float
    return_total: float

    class Config:
        from_attributes = True

class SaleReturnResponse(BaseModel):
    id: int
    sale_id: int
    bill_number: Optional[str] = None
    reason: Optional[str] = None
    return_amount: float
    created_at: datetime
    items: List[SaleReturnItemResponse] = []

    class Config:
        from_attributes = True


# ---------------- SUPPLIER SCHEMAS ---------------- #

class SupplierBase(BaseModel):
    name: str = Field(min_length=2)
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    state: Optional[str] = "Delhi"
    payment_terms: Optional[str] = "Net 30"
    notes: Optional[str] = None
    status: str = "Active"


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    state: Optional[str] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class SupplierResponse(SupplierBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    total_purchases: Optional[float] = 0.0
    purchase_count: Optional[int] = 0
    last_purchase_date: Optional[str] = None

    class Config:
        from_attributes = True


class SupplierMatchResponse(BaseModel):
    status: str  # "exact_match", "multiple_matches", "no_match"
    extracted_name: Optional[str] = None
    extracted_gstin: Optional[str] = None
    match_type: Optional[str] = None
    matched_supplier: Optional[SupplierResponse] = None
    candidate_matches: List[SupplierResponse] = []
    message: str


# ---------------- DOCUMENT SCHEMAS ---------------- #

class DocumentBase(BaseModel):
    title: str
    doc_type: str = "purchase_invoice"
    supplier_id: Optional[int] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[Any] = None
    total_amount: Optional[float] = 0.0
    item_count: Optional[int] = 0
    notes: Optional[str] = None


class DocumentCreate(DocumentBase):
    pass


class DocumentResponse(DocumentBase):
    id: int
    user_id: int
    file_path: str
    file_type: str
    file_size: int
    ocr_raw_json: Optional[str] = None
    ocr_status: str = "Processing"
    supplier_name: Optional[str] = None
    extracted_supplier_name: Optional[str] = None
    supplier_match: Optional[Union[SupplierMatchResponse, Dict[str, Any]]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentItemVerify(BaseModel):
    product_name: str
    brand: Optional[str] = None
    category: Optional[str] = "allopathy"
    batch_number: Optional[str] = None
    quantity: int = Field(gt=0)
    unit_price: float = Field(default=0.0, ge=0.0)
    purchase_price: float = Field(default=0.0, ge=0.0)
    hsn_code: Optional[str] = "3004"
    gst_rate: Optional[float] = 12.0
    manufacturing_date: Optional[str] = None
    expiry_date: str


class DocumentConfirmRequest(BaseModel):
    supplier_id: Optional[int] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    total_amount: Optional[float] = 0.0
    items: List[DocumentItemVerify] = Field(min_length=1)


class PilotLeadCreate(BaseModel):
    full_name: str
    pharmacy_name: str
    city: str
    phone: str
    current_billing_method: str
    bills_per_day: str
    biggest_problem: Optional[str] = None

    @field_validator("full_name", "pharmacy_name", "city", "phone", "current_billing_method", "bills_per_day")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("Field cannot be empty.")
        return str(v).strip()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        import re
        clean = re.sub(r"[^\d+]", "", str(v).strip())
        if len(clean) < 10:
            raise ValueError("Please provide a valid phone number (at least 10 digits).")
        return clean


class PilotLeadResponse(BaseModel):
    id: int
    full_name: str
    pharmacy_name: str
    city: str
    phone: str
    current_billing_method: str
    bills_per_day: str
    biggest_problem: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# ERP PRIORITY 1 SCHEMAS
# ==========================================

from datetime import date

class PurchaseItemCreate(BaseModel):
    product_id: int
    batch_number: str
    quantity: int
    purchase_price: float
    mrp: float
    gst_rate: float
    expiry_date: date

class PurchaseItemResponse(BaseModel):
    id: int
    purchase_invoice_id: int
    product_id: int
    batch_number: str
    quantity: int
    purchase_price: float
    mrp: float
    gst_rate: float
    expiry_date: date

    class Config:
        from_attributes = True

class PurchaseInvoiceCreate(BaseModel):
    supplier_id: int
    invoice_number: str
    invoice_date: date
    total_amount: float
    tax_amount: float
    payment_status: str  # PAID, UNPAID, PARTIAL
    items: List[PurchaseItemCreate]

class PurchaseInvoiceResponse(BaseModel):
    id: int
    user_id: int
    supplier_id: int
    invoice_number: str
    invoice_date: date
    total_amount: float
    tax_amount: float
    payment_status: str
    created_at: datetime
    updated_at: datetime
    items: List[PurchaseItemResponse]

    class Config:
        from_attributes = True

class SupplierPaymentCreate(BaseModel):
    supplier_id: int
    amount_paid: float
    payment_method: str  # CASH, UPI, BANK_TRANSFER, CHEQUE
    notes: Optional[str] = None

class SupplierPaymentResponse(BaseModel):
    id: int
    user_id: int
    supplier_id: int
    amount_paid: float
    payment_method: str
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class CustomerPaymentCreate(BaseModel):
    customer_id: int
    sale_id: Optional[int] = None
    amount_paid: float
    payment_method: str  # CASH, UPI, CARD

class CustomerPaymentResponse(BaseModel):
    id: int
    user_id: int
    customer_id: int
    sale_id: Optional[int] = None
    amount_paid: float
    payment_method: str
    created_at: datetime

    class Config:
        from_attributes = True

class PurchaseReturnItemCreate(BaseModel):
    product_id: int
    batch_number: str
    quantity: int
    purchase_price: float

class PurchaseReturnItemResponse(BaseModel):
    id: int
    purchase_return_id: int
    product_id: int
    batch_number: str
    quantity: int
    purchase_price: float

    class Config:
        from_attributes = True

class PurchaseReturnCreate(BaseModel):
    supplier_id: int
    purchase_invoice_id: Optional[int] = None
    total_returned_value: float
    reason: Optional[str] = None
    items: List[PurchaseReturnItemCreate]

class PurchaseReturnResponse(BaseModel):
    id: int
    user_id: int
    supplier_id: int
    purchase_invoice_id: Optional[int] = None
    total_returned_value: float
    reason: Optional[str] = None
    created_at: datetime
    items: List[PurchaseReturnItemResponse]

    class Config:
        from_attributes = True


class StaffMemberCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    role: str = "PHARMACIST"
    status: str = "ACTIVE"
    permissions: Optional[List[str]] = None


class StaffMemberUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    permissions: Optional[List[str]] = None


class StaffPasswordReset(BaseModel):
    new_password: str = Field(min_length=4)


class StaffMemberResponse(BaseModel):
    id: int
    user_id: int
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    role: str
    status: str
    permissions: Optional[List[str]] = None
    last_login: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class StaffCredentialResponse(BaseModel):
    staff_id: int
    name: str
    username: str
    password: Optional[str] = None
    role: str
    status: str

    class Config:
        from_attributes = True


class StaffCredentialUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None


class StoreBranchCreate(BaseModel):
    branch_name: str
    code: Optional[str] = "BR-01"
    address: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    is_main: bool = False
    status: str = "ACTIVE"


class StoreBranchUpdate(BaseModel):
    branch_name: Optional[str] = None
    code: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    is_main: Optional[bool] = None
    status: Optional[str] = None


class StoreBranchResponse(BaseModel):
    id: int
    user_id: int
    branch_name: str
    code: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    is_main: bool = False
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------- SMART RESTOCK & INVENTORY INTELLIGENCE SCHEMAS ---------------- #

class SmartRestockSummary(BaseModel):
    critical_restock: int = 0
    restock_soon: int = 0
    expiry_risk: int = 0
    slow_moving: int = 0
    dead_stock: int = 0
    overstock: int = 0
    healthy: int = 0
    total_at_risk_value: float = 0.0


class SmartRestockItem(BaseModel):
    rank: int
    product_id: int
    product_name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    batch_number: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    
    priority_level: str  # CRITICAL_RESTOCK, RESTOCK_SOON, EXPIRY_RISK, SLOW_MOVING, DEAD_STOCK, OVERSTOCK, HEALTHY
    priority_score: int  # 0 to 100
    recommendation_type: str  # RESTOCK_NOW, RESTOCK_SOON, RETURN_DISTRIBUTOR, PRIORITIZE_FEFO, CLEARANCE_DISCOUNT, STOP_PURCHASING, REDUCE_ORDER, MONITOR
    
    current_stock: int
    daily_demand: float
    days_of_stock: Optional[float] = None
    
    supplier_lead_time_days: int = 5
    safety_stock: int = 0
    reorder_point: int = 0
    suggested_order_quantity: int = 0
    
    unit_price: float = 0.0
    purchase_price: float = 0.0
    inventory_value: float = 0.0
    at_risk_value: float = 0.0
    
    expiry_date: Optional[str] = None
    days_to_expiry: Optional[int] = None
    at_risk_expiry_qty: int = 0
    
    confidence: str = "HIGH"  # HIGH, MEDIUM, LOW
    confidence_reason: Optional[str] = None
    reason: str
    recommended_action: str
    debug_info: Optional[Dict[str, Any]] = None


class InventoryIntelligenceResponse(BaseModel):
    generated_at: str
    summary: SmartRestockSummary
    recommendations: List[SmartRestockItem]
    needs_attention: List[Dict[str, Any]] = []
    
    # Backward compatibility fields for legacy clients
    total_products: int = 0
    total_stock_value: float = 0.0
    expired_count: int = 0
    expired_value: float = 0.0
    expiring_7d_count: int = 0
    expiring_30d_count: int = 0
    expiring_30d_value: float = 0.0
    expiring_60d_count: int = 0
    expiring_90d_count: int = 0
    expiring_90d_value: float = 0.0
    low_stock_count: int = 0
    out_of_stock_count: int = 0
    dead_stock_count: int = 0
    dead_stock_value: float = 0.0
    low_stock_items: List[Dict[str, Any]] = []
    expiring_items: List[Dict[str, Any]] = []
    expired_items: List[Dict[str, Any]] = []
    dead_stock_items: List[Dict[str, Any]] = []


class SmartRestockConfigUpdate(BaseModel):
    safety_stock_days: Optional[int] = 5
    default_lead_time_days: Optional[int] = 5
    target_coverage_days: Optional[int] = 30
    weight_urgency: Optional[float] = 0.35
    weight_velocity: Optional[float] = 0.25
    weight_lead_time: Optional[float] = 0.15
    weight_sales_importance: Optional[float] = 0.10
    weight_consistency: Optional[float] = 0.10
    weight_impact: Optional[float] = 0.05


# ---------------- CA CONNECT SCHEMAS ---------------- #

class CaProfileCreate(BaseModel):
    ca_email: str
    ca_name: Optional[str] = None
    ca_phone: Optional[str] = None

    @field_validator('ca_email', mode='before')
    @classmethod
    def clean_email(cls, v):
        if isinstance(v, str):
            return v.strip().lower()
        return v


class CaProfileResponse(BaseModel):
    id: int
    user_id: int
    ca_email: str
    ca_name: Optional[str] = None
    ca_phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_shared_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CaShareRequest(BaseModel):
    ca_email: Optional[str] = None
    reports: List[str] = Field(min_length=1, description="List of report keys to include: gst_summary, sales_register, purchase_register, hsn_summary, input_output_gst, pnl_summary")
    date_range_preset: Optional[str] = Field(default="this_month", description="today, this_week, this_month, previous_month, this_quarter, financial_year, custom")
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    custom_message: Optional[str] = None


class CaShareLogResponse(BaseModel):
    id: int
    user_id: int
    sender_email: Optional[str] = None
    ca_email: str
    reports_shared: List[str]
    date_range_label: str
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    status: str
    sent_at: datetime
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class GstFinancialReportResponse(BaseModel):
    pharmacy_name: str
    owner_name: str
    gstin: Optional[str] = None
    date_range_label: str
    start_date: str
    end_date: str
    total_sales: float = 0.0
    total_purchases: float = 0.0
    total_taxable_value: float = 0.0
    total_output_gst: float = 0.0
    total_input_gst: float = 0.0
    net_gst_payable: float = 0.0
    total_bills: int = 0
    total_purchase_invoices: int = 0
    gross_profit: float = 0.0
    gst_rate_breakdown: List[Dict[str, Any]] = []
    hsn_summary: List[Dict[str, Any]] = []
    recent_sales_register: List[Dict[str, Any]] = []
    recent_purchase_register: List[Dict[str, Any]] = []


# ==========================================
# THERMAL POS PRINTING SCHEMAS
# ==========================================

class PrinterDeviceCreate(BaseModel):
    device_name: str = Field(..., min_length=1, max_length=100)
    printer_system_name: str = Field(..., min_length=1, max_length=150)
    connection_type: str = "USB"  # USB, BLUETOOTH, NETWORK
    paper_size: str = "80mm"      # 58mm, 80mm
    is_default: bool = True
    settings_json: Optional[str] = None


class PrinterDeviceUpdate(BaseModel):
    device_name: Optional[str] = None
    printer_system_name: Optional[str] = None
    connection_type: Optional[str] = None
    paper_size: Optional[str] = None
    is_default: Optional[bool] = None
    settings_json: Optional[str] = None


class PrinterDeviceResponse(BaseModel):
    id: int
    user_id: int
    device_name: str
    printer_system_name: str
    connection_type: str
    paper_size: str
    is_default: bool
    is_online: bool
    last_seen_at: Optional[datetime] = None
    settings_json: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PrintJobCreate(BaseModel):
    sale_id: int
    printer_id: Optional[int] = None
    copies: int = 1
    force_print_again: bool = False
    paper_size: Optional[str] = None


class PrintJobResponse(BaseModel):
    id: int
    user_id: int
    printer_id: Optional[int] = None
    sale_id: Optional[int] = None
    invoice_number: str
    status: str
    copies: int
    paper_size: str
    created_at: datetime
    claimed_at: Optional[datetime] = None
    printed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    retry_count: int = 0
    error_message: Optional[str] = None
    printer_name: Optional[str] = None

    class Config:
        from_attributes = True


class PrintJobStatusUpdate(BaseModel):
    job_id: int
    status: str  # PRINTING, PRINTED, FAILED
    error_message: Optional[str] = None


class PrinterStatusSummaryResponse(BaseModel):
    has_printer: bool
    has_online_printer: bool
    default_printer: Optional[PrinterDeviceResponse] = None
    online_count: int
    pending_jobs_count: int
    status_label: str  # "Ready", "Print Pending", "Printer Offline", "No Printer Setup"
    status_color: str  # "green", "yellow", "red", "grey"


# ---------------- HELD BILL SCHEMAS ---------------- #

class HeldBillItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    product_name: Optional[str] = None
    quantity: int = Field(gt=0, default=1)
    unit_type: Optional[str] = "strip"
    unit_price: Optional[float] = Field(default=None, ge=0.0)
    discount: float = Field(default=0.0, ge=0.0)
    tablets_per_strip: Optional[int] = Field(default=None, gt=0)
    batch_number: Optional[str] = None
    expiry_date: Optional[str] = None
    hsn_code: Optional[str] = None
    gst_percentage: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    estimated_line_total: Optional[float] = None

    @field_validator("unit_type", mode="before")
    @classmethod
    def normalize_unit_type(cls, v):
        if not v:
            return "strip"
        v_clean = str(v).strip().lower()
        if v_clean in ["strip", "pack"]:
            return "strip"
        if v_clean in ["loose", "loose_tablet", "loose_tablets", "tablet", "tablets", "unit", "pill", "pills"]:
            return "loose_tablet"
        return v_clean


class HeldBillItemResponse(BaseModel):
    id: int
    held_bill_id: int
    product_id: int
    product_name: str
    quantity: int
    unit_type: str
    unit_price: float
    discount: float
    tablets_per_strip: Optional[int] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[str] = None
    hsn_code: Optional[str] = None
    gst_percentage: float
    estimated_line_total: float

    class Config:
        from_attributes = True


class HeldBillCreate(BaseModel):
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_reg_no: Optional[str] = None
    payment_method: Optional[str] = "CASH"
    split_payments: Optional[List[PaymentAllocation]] = None
    is_interstate: bool = False
    discount_type: Optional[str] = None
    discount_value: float = Field(default=0.0, ge=0.0)
    notes: Optional[str] = None
    items: List[HeldBillItemCreate] = Field(min_length=1)

    @field_validator("discount_type", mode="before")
    @classmethod
    def normalize_discount_type(cls, v):
        if not v:
            return None
        v_clean = str(v).strip().lower()
        if v_clean in ["flat", "percent"]:
            return v_clean
        return None


class HeldBillResponse(BaseModel):
    id: int
    held_bill_number: str
    status: str
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_reg_no: Optional[str] = None
    payment_method: Optional[str] = None
    split_payments: Optional[List[PaymentAllocationResponse]] = None
    is_interstate: bool = False
    discount_type: Optional[str] = None
    discount_value: float = 0.0
    estimated_subtotal: float = 0.0
    estimated_discount: float = 0.0
    estimated_tax: float = 0.0
    estimated_total: float = 0.0
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    completed_sale_id: Optional[int] = None
    items: List[HeldBillItemResponse] = []

    class Config:
        from_attributes = True


class HeldBillResumeItem(BaseModel):
    product_id: int
    product_name: str
    requested_quantity: int
    available_stock: int  # in requested unit_type (strips or loose tablets)
    is_sufficient: bool
    unit_type: str
    unit_price: float
    discount: float
    tablets_per_strip: Optional[int] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[str] = None
    hsn_code: Optional[str] = None
    gst_percentage: float
    estimated_line_total: float


class HeldBillResumeResponse(BaseModel):
    held_bill: HeldBillResponse
    items: List[HeldBillResumeItem]
    has_stock_shortage: bool


