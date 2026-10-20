"""
Pharmacy Documents & Invoice OCR Archive routes (web app "Documents" page and desktop app).

Restored from app.py as it was before the modularisation refactor (commit 526c298), which moved other
routes into routes/ but left these out: upload, list, detail, AI OCR, confirm-into-stock, delete, and the
authenticated file download for uploaded documents. Behaviour is unchanged; helpers live in crud.py.
"""

import json
import logging
import mimetypes
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from dependencies import get_db, get_current_user, AuthenticatedUser, limiter
import models
import schemas
import crud
from ai.invoice_service import scan_invoice

logger = logging.getLogger("expiryguard.routes.document_archive")

router = APIRouter(tags=["Documents & Invoice OCR Archive"])

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_BASE_DIR = (BASE_DIR / "uploads").resolve()
DOCUMENTS_DIR = (UPLOADS_BASE_DIR / "documents").resolve()
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_DOC_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE_10MB = 10 * 1024 * 1024


def _validate_file_magic(file_bytes: bytes, ext: str):
    """Reject files whose content does not match their extension."""
    ext = ext.lower()
    if ext in (".jpg", ".jpeg") and not file_bytes.startswith(b"\xFF\xD8\xFF"):
        raise HTTPException(status_code=400, detail="Invalid JPEG image file signature.")
    if ext == ".png" and not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=400, detail="Invalid PNG image file signature.")
    if ext == ".webp" and not (file_bytes.startswith(b"RIFF") and b"WEBP" in file_bytes[:16]):
        raise HTTPException(status_code=400, detail="Invalid WEBP image file signature.")
    if ext == ".pdf" and not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid PDF document file signature.")


def _document_response(doc, extracted_name=None, supplier_match=None):
    res = schemas.DocumentResponse.model_validate(doc, from_attributes=True)
    res.supplier_name = doc.supplier.name if doc.supplier else None
    if extracted_name is not None:
        res.extracted_supplier_name = extracted_name
    if supplier_match is not None:
        res.supplier_match = supplier_match
    return res


@router.get("/api/uploads/{file_path:path}")
@router.get("/uploads/{file_path:path}")
def serve_authenticated_upload(
    file_path: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Authenticated download of an uploaded file; only the owning pharmacy can read its documents."""
    clean_relative = file_path.lstrip("/\\")
    if ".." in clean_relative or "\\" in clean_relative:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path structure.")
    try:
        target_path = (UPLOADS_BASE_DIR / clean_relative).resolve()
        target_path.relative_to(UPLOADS_BASE_DIR)
    except Exception:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    filename = target_path.name
    possible_file_paths = [
        f"/uploads/documents/{filename}",
        f"/uploads/{filename}",
        f"/api/uploads/documents/{filename}",
        f"/api/uploads/{filename}",
        f"uploads/documents/{filename}",
        f"uploads/{filename}",
        clean_relative,
        filename,
    ]
    doc = db.query(models.Document).filter(models.Document.file_path.in_(possible_file_paths)).first()

    # Tenant isolation: files in the documents folder must belong to the current pharmacy.
    if target_path.is_relative_to(DOCUMENTS_DIR):
        if not doc or doc.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    elif doc and doc.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    media_type, _ = mimetypes.guess_type(str(target_path))
    return FileResponse(path=target_path, media_type=media_type or "application/octet-stream", filename=filename)


@router.post("/documents/upload", response_model=schemas.DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = "purchase_invoice",
    title: Optional[str] = None,
    supplier_id: Optional[int] = None,
    invoice_number: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Upload a pharmacy document (PDF or image) and create its Document record."""
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension '{file_ext}'. Allowed types: {', '.join(sorted(ALLOWED_DOC_EXTENSIONS))}",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(file_bytes) > MAX_FILE_SIZE_10MB:
        raise HTTPException(status_code=413, detail="File is larger than 10 MB.")
    _validate_file_magic(file_bytes, file_ext)

    unique_name = f"doc_{uuid.uuid4().hex[:16]}{file_ext}"
    target_path = (DOCUMENTS_DIR / unique_name).resolve()
    if not target_path.is_relative_to(DOCUMENTS_DIR):
        raise HTTPException(status_code=400, detail="Invalid target path.")
    with open(target_path, "wb") as buffer:
        buffer.write(file_bytes)

    return crud.create_document(
        db=db,
        user_id=current_user.id,
        title=(title or file.filename or "Document").strip(),
        doc_type=doc_type,
        file_path=f"/uploads/documents/{unique_name}",
        file_type=file.content_type or "application/octet-stream",
        file_size=len(file_bytes),
        supplier_id=supplier_id,
        invoice_number=invoice_number,
    )


@router.post("/documents/{document_id}/ocr", response_model=schemas.DocumentResponse)
@limiter.limit("15/minute")
def trigger_document_ocr(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Run AI OCR on an uploaded invoice and match its supplier (never creates a supplier silently)."""
    doc = crud.get_document_detail(db=db, document_id=document_id, user_id=current_user.id)
    full_path = DOCUMENTS_DIR / Path(doc.file_path).name
    if not full_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Document file not found on server. Please upload the document again.",
        )

    logger.info("[OCR:ENDPOINT] Document #%s OCR started", document_id)
    ocr_res = scan_invoice(str(full_path), user_id=current_user.id)
    supplier_match_info = None
    extracted_name = None

    if ocr_res.get("success"):
        data = ocr_res.get("data", {})
        doc.ocr_status = "Needs Review"
        if data.get("invoice_number"):
            doc.invoice_number = data.get("invoice_number").strip()
        if data.get("invoice_date"):
            try:
                doc.invoice_date = datetime.strptime(data.get("invoice_date").strip(), "%Y-%m-%d").date()
            except Exception as d_err:
                logger.info("[OCR:ENDPOINT] Could not parse invoice date %r: %s", data.get("invoice_date"), d_err)
        if data.get("total_amount") is not None:
            doc.total_amount = float(data.get("total_amount") or 0.0)
        if data.get("items"):
            doc.item_count = len(data.get("items"))

        if data.get("supplier_name"):
            s_name = data.get("supplier_name").strip()
            extracted_name = s_name
            match_res = crud.find_matching_suppliers(
                db=db,
                user_id=current_user.id,
                extracted_name=s_name,
                extracted_gstin=data.get("supplier_gstin"),
            )
            supplier_match_info = match_res
            data["supplier_match"] = match_res
            if match_res.get("status") == "exact_match" and match_res.get("matched_supplier"):
                matched_s = (
                    db.query(models.Supplier)
                    .filter(
                        models.Supplier.id == match_res["matched_supplier"]["id"],
                        models.Supplier.user_id == current_user.id,
                    )
                    .first()
                )
                if matched_s:
                    doc.supplier_id = matched_s.id
                    for field, key in (("gstin", "supplier_gstin"), ("phone", "supplier_phone"),
                                       ("email", "supplier_email"), ("address", "supplier_address")):
                        if not getattr(matched_s, field) and data.get(key):
                            setattr(matched_s, field, data.get(key).strip())
                    db.add(matched_s)
            else:
                doc.supplier_id = None

        doc.ocr_raw_json = json.dumps(data, default=str)
    else:
        doc.ocr_status = "Failed"
        doc.ocr_raw_json = json.dumps({"error": ocr_res.get("error", "Unknown OCR failure"), "items": []}, default=str)

    db.commit()
    db.refresh(doc)
    return _document_response(doc, extracted_name, supplier_match_info)


@router.get("/documents", response_model=List[schemas.DocumentResponse])
def list_documents(
    query: Optional[str] = None,
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    supplier_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List pharmacy documents with filters and supplier info."""
    return crud.get_documents(
        db=db, user_id=current_user.id, query=query, doc_type=doc_type, status=status, supplier_id=supplier_id
    )


@router.get("/documents/{document_id}", response_model=schemas.DocumentResponse)
def get_document_detail(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Single document with OCR JSON and supplier-match information."""
    doc = crud.get_document_detail(db=db, document_id=document_id, user_id=current_user.id)
    extracted_name = None
    supplier_match = None
    if doc.ocr_raw_json:
        try:
            parsed = json.loads(doc.ocr_raw_json)
            s_name = parsed.get("supplier_name")
            if s_name:
                extracted_name = s_name.strip()
                supplier_match = crud.find_matching_suppliers(
                    db=db,
                    user_id=current_user.id,
                    extracted_name=s_name,
                    extracted_gstin=parsed.get("supplier_gstin"),
                )
                if (
                    not doc.supplier_id
                    and supplier_match.get("status") == "exact_match"
                    and supplier_match.get("matched_supplier")
                ):
                    doc.supplier_id = supplier_match["matched_supplier"]["id"]
                    db.commit()
                    db.refresh(doc)
        except Exception as e:
            logger.info("[DOC:DETAIL] Supplier match evaluation notice: %s", e)
    return _document_response(doc, extracted_name, supplier_match)


@router.post("/documents/{document_id}/confirm")
def confirm_document(
    document_id: int,
    confirm_req: schemas.DocumentConfirmRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Confirm reviewed invoice items into stock, with supplier and invoice traceability."""
    return crud.confirm_document_and_update_stock(
        db=db, document_id=document_id, user_id=current_user.id, confirm_req=confirm_req
    )


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Delete a document record."""
    return crud.delete_document(db=db, document_id=document_id, user_id=current_user.id)
