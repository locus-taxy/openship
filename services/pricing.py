"""
Pricing service: fetches model prices from ai-model-pricing.com once on first use,
held in memory indefinitely. Refresh via invalidate_cache() (POST /auth/me/pricing/refresh).
"""

import logging
from typing import Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

_PRICING_URL = "https://ai-model-pricing.com/api/v1/pricing.json"
_cache: Optional[List[Dict]] = None

# Map our internal provider names → API provider names
_PROVIDER_MAP: Dict[str, str] = {
    "gemini": "google",
    "openai": "openai",
    "anthropic": "anthropic",
    "mistral": "mistral",
}

# Map our internal provider names → preferred platform key in pricing entries
_PLATFORM_MAP: Dict[str, str] = {
    "gemini": "google_ai_studio",
    "openai": "openai",
    "anthropic": "anthropic",
    "mistral": "mistral",
}

# Fallback platform order when native platform has no pricing
_FALLBACK_PLATFORMS = ["openrouter", "bedrock", "azure_openai"]

# Hardcoded prices (input, output) per 1M tokens — used when the API is unreachable.
# Keyed by (provider, model_id_or_alias).
_HARDCODED: Dict[Tuple[str, str], Tuple[float, float]] = {
    # Gemini
    ("gemini", "gemini-2.5-pro"): (1.25, 10.0),
    ("gemini", "gemini-2.5-flash"): (0.30, 2.5),
    ("gemini", "gemini-2.5-flash-lite"): (0.10, 0.4),
    ("gemini", "gemini-2.0-flash"): (0.10, 0.4),
    ("gemini", "gemini-2.0-flash-lite"): (0.075, 0.3),
    # OpenAI
    ("openai", "gpt-4o-mini"): (0.15, 0.6),
    ("openai", "gpt-4o"): (2.50, 10.0),
    # Anthropic
    ("anthropic", "claude-3-5-haiku-latest"): (0.80, 4.0),
    ("anthropic", "claude-3-5-sonnet-latest"): (3.00, 15.0),
    ("anthropic", "claude-3-opus-latest"): (15.0, 75.0),
    # Mistral
    ("mistral", "mistral-small-latest"): (0.15, 0.6),
    ("mistral", "mistral-large-latest"): (0.50, 1.5),
}

def _get_models() -> List[Dict]:
    global _cache
    if _cache is not None:
        return _cache
    try:
        resp = httpx.get(_PRICING_URL, timeout=10)
        resp.raise_for_status()
        _cache = resp.json().get("models", [])
        logger.info("Pricing data loaded: %d models", len(_cache))
    except Exception as exc:
        logger.warning("Could not fetch pricing data (%s) — falling back to hardcoded prices", exc)
        if _cache is None:
            _cache = []
    return _cache

def _pick_price(entry: Dict, platform: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Extract (input, output) per 1M tokens from a model entry.
    Tries the native platform first (standard tier, then any tier),
    then falls back through _FALLBACK_PLATFORMS.
    """

    def _from_platform(plt: str) -> Tuple[Optional[float], Optional[float]]:
        prices = [
            p
            for p in entry.get("pricing", [])
            if p.get("platform") == plt and p.get("modality") == "text"
        ]
        for p in prices:
            if p.get("tier") == "standard":
                return p.get("input_per_1m_tokens"), p.get("output_per_1m_tokens")
        for p in prices:
            return p.get("input_per_1m_tokens"), p.get("output_per_1m_tokens")
        return None, None

    inp, out = _from_platform(platform)
    if inp is not None:
        return inp, out

    for fallback in _FALLBACK_PLATFORMS:
        if fallback == platform:
            continue
        inp, out = _from_platform(fallback)
        if inp is not None:
            return inp, out

    return None, None

def _resolve(provider: str, model: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Internal: return (input, output, matched_model_id).

    Match strategy (in order):
    1. Exact match on model_id or native-platform alias
    2. Forward-prefix: model is a versioned variant of a base entry
       e.g. "gemini-2.5-pro-preview-05-06" → "gemini-2.5-pro"
    3. Reverse-prefix: strip "-latest" and find a dated API entry
       e.g. "claude-3-5-haiku-latest" → "claude-3-5-haiku-20241022"
    4. Hardcoded fallback (API unreachable)
    """
    api_provider = _PROVIDER_MAP.get(provider)
    platform = _PLATFORM_MAP.get(provider)
    if not api_provider or not platform:
        return None, None, None

    model_base = model[: -len("-latest")] if model.endswith("-latest") else model

    best_forward_entry: Optional[Dict] = None
    best_forward_len: int = 0
    best_reverse_entry: Optional[Dict] = None
    best_reverse_len: int = 0

    for entry in _get_models():
        if entry.get("provider") != api_provider:
            continue

        entry_id: str = entry.get("model_id", "")
        aliases: Dict[str, str] = entry.get("aliases", {})

        if model in (entry_id, aliases.get(platform, "")):
            inp, out = _pick_price(entry, platform)
            if inp is not None:
                return inp, out, entry_id

        if model.startswith(entry_id + "-") and len(entry_id) > best_forward_len:
            best_forward_entry = entry
            best_forward_len = len(entry_id)

        if entry_id.startswith(model_base + "-") and len(entry_id) > best_reverse_len:
            best_reverse_entry = entry
            best_reverse_len = len(entry_id)

    if best_forward_entry is not None:
        inp, out = _pick_price(best_forward_entry, platform)
        if inp is not None:
            return inp, out, best_forward_entry.get("model_id")

    if best_reverse_entry is not None:
        inp, out = _pick_price(best_reverse_entry, platform)
        if inp is not None:
            return inp, out, best_reverse_entry.get("model_id")

    # Last resort: hardcoded table
    inp, out = _HARDCODED.get((provider, model), (None, None))
    return inp, out, (model if inp is not None else None)

def lookup_model_price(provider: str, model: str) -> Tuple[Optional[float], Optional[float]]:
    """Return (input_per_1m_usd, output_per_1m_usd). Used for cost computation."""
    inp, out, _ = _resolve(provider, model)
    return inp, out

def lookup_model_info(provider: str, model: str) -> Dict:
    """Return full pricing info including the matched model name. Used by the API endpoint."""
    inp, out, matched = _resolve(provider, model)
    return {
        "input_per_1m_usd": inp,
        "output_per_1m_usd": out,
        "matched_model_id": matched,
        "found": inp is not None,
    }

def invalidate_cache() -> None:
    global _cache
    _cache = None
