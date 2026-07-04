import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional


def generate_cache_key(*args: Any, **kwargs: Any) -> str:
    """Generate a deterministic cache key from function arguments."""
    raw = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def now_utc() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc)


def format_currency(amount: float, currency: str = "USD") -> str:
    """Format a number as currency string."""
    return f"{currency} {amount:,.2f}"


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format a ratio as percentage string."""
    return f"{value * 100:.{decimals}f}%"


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def truncate_string(text: str, max_length: int = 500) -> str:
    """Truncate string to max_length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def chunk_list(lst: list, chunk_size: int) -> list[list]:
    """Split a list into chunks of specified size."""
    return [lst[i : i + chunk_size] for i in range(0, len(lst), chunk_size)]


def serialize_for_json(obj: Any) -> Any:
    """JSON-serialize helper for non-standard types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")