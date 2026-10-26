"""
Where the original uploaded supplier invoices live.

Every upload is written to the server's uploads folder (OCR reads it from there). That folder is NOT durable on hosts
whose disk is wiped on every deploy (e.g. a Railway service without a volume), so a second, durable copy is kept in
private object storage when it is configured:

    SUPABASE_URL                 e.g. https://xxxx.supabase.co
    SUPABASE_SERVICE_KEY         service-role key (server side only, never sent to a browser)
    DOCUMENT_STORAGE_BUCKET      private bucket name (default "documents")

The object key is derived from the owner and the stored file name (documents/<user_id>/<file name>), so the document
record needs no extra column: the durable reference is (bucket, key). Files are only ever served through the
authenticated /documents/{id}/file route; the bucket must stay private (no public URLs).

When no remote storage is configured the app behaves as before (local disk only) and says so in `describe()`.
The original bytes are written once and never rewritten by OCR.
"""
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

import httpx

logger = logging.getLogger("expiryguard.document_storage")

_TIMEOUT = httpx.Timeout(20.0, connect=8.0)
_transport = None            # tests inject an httpx.MockTransport here


class StorageError(Exception):
    pass


def _cfg():
    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_SERVICE_KEY") or "").strip()
    bucket = (os.getenv("DOCUMENT_STORAGE_BUCKET") or "documents").strip()
    if url and key:
        return url, key, bucket
    return None


def remote_enabled() -> bool:
    return _cfg() is not None


def describe() -> dict:
    return {"remote": remote_enabled(), "backend": "supabase-storage" if remote_enabled() else "local-disk-only"}


def object_key(user_id: int, file_name: str) -> str:
    return f"documents/{int(user_id)}/{Path(file_name).name}"


def _client() -> httpx.Client:
    return httpx.Client(timeout=_TIMEOUT, transport=_transport)


def _headers(key: str, content_type: Optional[str] = None) -> dict:
    h = {"Authorization": f"Bearer {key}", "apikey": key}
    if content_type:
        h["Content-Type"] = content_type
    return h


def put_remote(user_id: int, file_name: str, data: bytes, content_type: str) -> bool:
    """Store the durable copy. Returns False when remote storage is not configured; raises StorageError on failure."""
    cfg = _cfg()
    if not cfg:
        return False
    url, key, bucket = cfg
    obj = object_key(user_id, file_name)
    try:
        with _client() as c:
            r = c.post(f"{url}/storage/v1/object/{bucket}/{obj}", content=data,
                       headers={**_headers(key, content_type or "application/octet-stream"), "x-upsert": "false"})
    except httpx.HTTPError as exc:
        logger.error("document storage upload failed: %s", exc)
        raise StorageError("The durable storage service could not be reached.") from exc
    if r.status_code not in (200, 201):
        logger.error("document storage upload rejected: %s %s", r.status_code, r.text[:200])
        raise StorageError("The durable storage service refused the file.")
    return True


def get_remote(user_id: int, file_name: str) -> Optional[bytes]:
    """The durable copy, or None when it is not there / not configured."""
    cfg = _cfg()
    if not cfg:
        return None
    url, key, bucket = cfg
    try:
        with _client() as c:
            r = c.get(f"{url}/storage/v1/object/{bucket}/{object_key(user_id, file_name)}", headers=_headers(key))
    except httpx.HTTPError as exc:
        logger.error("document storage download failed: %s", exc)
        raise StorageError("The durable storage service could not be reached.") from exc
    if r.status_code == 200:
        return r.content
    if r.status_code in (400, 404):
        return None
    raise StorageError("The durable storage service returned an error.")


def delete_remote(user_id: int, file_name: str) -> None:
    """Used only to roll back a failed upload; documents are never deleted by OCR."""
    cfg = _cfg()
    if not cfg:
        return
    url, key, bucket = cfg
    try:
        with _client() as c:
            c.delete(f"{url}/storage/v1/object/{bucket}/{object_key(user_id, file_name)}", headers=_headers(key))
    except httpx.HTTPError:
        logger.warning("could not remove %s from remote storage", file_name)


def read_original(local_dir: Path, user_id: int, file_name: str) -> Tuple[Optional[Path], Optional[bytes]]:
    """
    Find the original: the local file first; if the disk lost it (redeploy) restore it from the durable copy and
    write it back locally. Returns (path, None) or (None, bytes) or (None, None) when it is gone everywhere.
    """
    name = Path(file_name).name
    path = (local_dir / name).resolve()
    if path.is_file() and path.is_relative_to(local_dir):
        return path, None
    data = get_remote(user_id, name)
    if data is None:
        return None, None
    try:
        local_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path, None
    except OSError:
        return None, data
