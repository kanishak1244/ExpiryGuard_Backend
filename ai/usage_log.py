"""
Gemini cost logging: numbers and IDs only.

Never stores images, bill contents, OCR text, medicine names, customer data, API keys or full responses.
Recording is non-blocking (bounded in-memory queue + one background writer thread with its own DB session)
and never raises, so a logging failure cannot break a scan.
"""
import logging
import os
import queue
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Prices are configurable so a Google price change needs an env change, not a deploy of code.
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


PRICE_INPUT_USD_PER_M = _env_float("GEMINI_PRICE_INPUT_USD_PER_M", 0.25)
PRICE_OUTPUT_USD_PER_M = _env_float("GEMINI_PRICE_OUTPUT_USD_PER_M", 1.50)
USD_INR = _env_float("USD_INR", 90.0)

QUEUE_MAX = 2000

BACKEND_FEATURES = {
    "invoice_read", "invoice_second_pass", "scan_label", "scan_multi_item",
    "ai_chat_classify", "ai_chat_answer", "migration_pdf",
}
PHONE_FEATURES = {"quick_batch"}
ALL_FEATURES = BACKEND_FEATURES | PHONE_FEATURES
OUTCOMES = {"success", "error", "timeout", "cache_hit"}


def new_event_id() -> str:
    return uuid.uuid4().hex


def new_bill_id() -> str:
    return uuid.uuid4().hex


def _int(v: Any) -> Optional[int]:
    try:
        if v is None or isinstance(v, bool):
            return None
        return max(0, int(v))
    except (TypeError, ValueError):
        return None


def compute_cost(prompt_tokens: Optional[int], output_tokens: Optional[int],
                 thought_tokens: Optional[int]) -> Optional[Dict[str, float]]:
    """Thinking tokens are billed as output. Returns None when no usage numbers exist (so averages skip it)."""
    p, o, t = _int(prompt_tokens), _int(output_tokens), _int(thought_tokens)
    if p is None and o is None and t is None:
        return None
    usd = ((p or 0) * PRICE_INPUT_USD_PER_M + ((o or 0) + (t or 0)) * PRICE_OUTPUT_USD_PER_M) / 1_000_000
    return {"usd": usd, "inr": usd * USD_INR}


def usage_from_response(response: Any) -> Dict[str, Optional[int]]:
    """Read token counts from a google-genai response; all None when usage_metadata is missing."""
    out = {"prompt_tokens": None, "output_tokens": None, "thought_tokens": None, "total_tokens": None}
    try:
        um = getattr(response, "usage_metadata", None)
        if um is None:
            return out
        out["prompt_tokens"] = _int(getattr(um, "prompt_token_count", None))
        out["output_tokens"] = _int(getattr(um, "candidates_token_count", None))
        out["thought_tokens"] = _int(getattr(um, "thoughts_token_count", None))
        out["total_tokens"] = _int(getattr(um, "total_token_count", None))
    except Exception:
        pass
    return out


_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=QUEUE_MAX)
_writer_lock = threading.Lock()
_writer: Optional[threading.Thread] = None


def _write_row(row: Dict[str, Any]) -> None:
    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        if db.query(models.AiUsageLog.id).filter(models.AiUsageLog.event_id == row["event_id"]).first():
            return
        db.add(models.AiUsageLog(**row))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("ai_usage_log write failed: %s", type(exc).__name__)
    finally:
        db.close()


def _writer_loop() -> None:
    while True:
        row = _queue.get()
        try:
            _write_row(row)
        except Exception:
            pass
        finally:
            _queue.task_done()


def _ensure_writer() -> None:
    global _writer
    if _writer is not None and _writer.is_alive():
        return
    with _writer_lock:
        if _writer is not None and _writer.is_alive():
            return
        _writer = threading.Thread(target=_writer_loop, name="ai-usage-writer", daemon=True)
        _writer.start()


def flush(timeout: float = 5.0) -> None:
    """Wait for queued rows to be written (tests / shutdown)."""
    done = threading.Event()

    def _wait():
        _queue.join()
        done.set()

    threading.Thread(target=_wait, daemon=True).start()
    done.wait(timeout)


def build_row(*, feature: str, outcome: str, shop_id: Optional[int] = None, model: Optional[str] = None,
              source: str = "backend", usage: Optional[Dict[str, Optional[int]]] = None,
              call_no: Optional[int] = None, bill_id: Optional[str] = None, rows: Optional[int] = None,
              pages: Optional[int] = None, strips: Optional[int] = None, latency_ms: Optional[int] = None,
              event_id: Optional[str] = None, zero_cost: bool = False) -> Dict[str, Any]:
    usage = usage or {}
    p, o, t = usage.get("prompt_tokens"), usage.get("output_tokens"), usage.get("thought_tokens")
    if zero_cost:  # cache hit: no Gemini call was made
        cost: Optional[Dict[str, float]] = {"usd": 0.0, "inr": 0.0}
        p = o = t = 0
        total = 0
    else:
        cost = compute_cost(p, o, t)
        total = usage.get("total_tokens")
    return {
        "event_id": event_id or new_event_id(),
        "created_at": datetime.utcnow(),
        "shop_id": _int(shop_id),
        "feature": str(feature)[:32],
        "model": (str(model)[:64] if model else None),
        "source": source if source in ("backend", "phone") else "backend",
        "outcome": outcome if outcome in OUTCOMES else "error",
        "call_no": _int(call_no),
        "prompt_tokens": p,
        "output_tokens": o,
        "thought_tokens": t,
        "total_tokens": total,
        "cost_inr": cost["inr"] if cost else None,
        "cost_usd": cost["usd"] if cost else None,
        "price_in_per_m": PRICE_INPUT_USD_PER_M if cost else None,
        "price_out_per_m": PRICE_OUTPUT_USD_PER_M if cost else None,
        "usd_inr": USD_INR if cost else None,
        "bill_id": (str(bill_id)[:40] if bill_id else None),
        "rows": _int(rows),
        "pages": _int(pages),
        "strips": _int(strips),
        "latency_ms": _int(latency_ms),
    }


def logging_enabled() -> bool:
    """Kill switch: AI_USAGE_LOG_ENABLED=0 stops all recording (tests set this so they never touch a real DB)."""
    return os.getenv("AI_USAGE_LOG_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def record(**kwargs: Any) -> None:
    """Queue one usage event. Never raises and never blocks the caller."""
    try:
        if not logging_enabled():
            return
        row = build_row(**kwargs)
        _ensure_writer()
        _queue.put_nowait(row)
    except queue.Full:
        logger.warning("ai_usage_log queue full; event dropped")
    except Exception as exc:
        logger.warning("ai_usage_log record failed: %s", type(exc).__name__)


def record_response(response: Any, **kwargs: Any) -> None:
    """Convenience: read usage from a Gemini response and record it."""
    try:
        record(usage=usage_from_response(response), **kwargs)
    except Exception:
        pass
