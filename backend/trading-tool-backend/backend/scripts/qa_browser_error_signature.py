"""Reduce protected browser failures to fixed, non-identifying QA codes.

The input may contain fixture data, URLs, query strings, and browser stack text.
Only the literal values declared below may leave this module in an artifact.
"""

from __future__ import annotations

import re


_ERROR_PATTERNS = (
    ("react_hydration", re.compile(r"hydration failed|hydrating", re.I)),
    ("react_hook_order", re.compile(r"rendered (?:more|fewer) hooks|invalid hook call", re.I)),
    ("react_invalid_child", re.compile(r"objects are not valid as a react child", re.I)),
    ("react_minified", re.compile(r"minified react error", re.I)),
    ("next_chunk_load", re.compile(r"chunkloaderror|loading chunk .* failed", re.I)),
    ("next_client_exception", re.compile(r"application error: a client-side exception", re.I)),
    ("js_null_property", re.compile(r"cannot read properties of null", re.I)),
    ("js_undefined_property", re.compile(r"cannot read properties of undefined", re.I)),
    ("js_non_callable", re.compile(r"\bis not a function\b", re.I)),
    ("js_type_error", re.compile(r"\bTypeError\b")),
    ("js_reference_error", re.compile(r"\bReferenceError\b")),
    ("js_range_error", re.compile(r"\bRangeError\b")),
    ("js_syntax_error", re.compile(r"\bSyntaxError\b")),
    ("network_fetch_error", re.compile(r"\bFailed to fetch\b|\bNetworkError\b", re.I)),
)

_STACK_AREAS = (
    ("bot_focus_view", ("BotFocusView.jsx", "BotFocusView.tsx")),
    ("bot_page", ("/bot/page.jsx", "/bot/page.tsx")),
    ("bot_data_hook", ("useBotData.js", "useBotData.ts")),
    ("onboarding_hook", ("useOnboarding.js", "useOnboarding.ts")),
    ("next_runtime", ("/_next/static/chunks/webpack-", "/_next/static/chunks/main-")),
    ("next_chunk", ("/_next/static/chunks/",)),
)


def classify_browser_error(error: object, *, stack: object = None) -> dict[str, str]:
    """Return only allowlisted codes; never return or log the supplied text."""
    message = str(error or "")
    frames = str(stack or "")
    kind = next((code for code, pattern in _ERROR_PATTERNS if pattern.search(message)), "other")
    area = next(
        (code for code, markers in _STACK_AREAS
         if any(marker in frames for marker in markers)),
        "unavailable",
    )
    if area == "unavailable":
        if "https://tradamind.com/" in frames:
            area = "same_origin_other"
        elif re.search(r"https?://", frames):
            area = "external_or_unknown_origin"
    return {"kind": kind, "stack_area": area}


def append_bounded_signature(signatures: list[dict[str, str]], signature: dict[str, str]) -> None:
    """Keep at most three distinct fixed-code signatures per browser event class."""
    if signature not in signatures and len(signatures) < 3:
        signatures.append(signature)
