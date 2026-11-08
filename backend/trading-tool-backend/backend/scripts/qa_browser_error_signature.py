"""Reduce protected browser failures to fixed, non-identifying QA codes.

The input may contain fixture data, URLs, query strings, and browser stack text.
Only the literal values declared below may leave this module in an artifact.
"""

from __future__ import annotations

import re
from pathlib import Path


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

_BUNDLE_FRAME = re.compile(
    r"https://tradamind\.com/_next/static/chunks/"
    r"(?P<relative>(?:[A-Za-z0-9_()\-]+/)*[A-Za-z0-9._-]+\.js)"
    r":(?P<line>[1-9][0-9]{0,6}):(?P<column>[1-9][0-9]{0,7})(?=[\s)]|$)"
)
_MINIFIED_CALL = re.compile(
    r"^TypeError:\s+(?:\(0,\s*(?P<wrapped_base>[A-Za-z_$])\."
    r"(?P<wrapped_member>[A-Za-z_$][A-Za-z0-9_$]?)\)|"
    r"(?P<plain_base>[A-Za-z_$])\."
    r"(?P<plain_member>[A-Za-z_$][A-Za-z0-9_$]?))"
    r" is not a function(?:\r?\n|$)"
)
_DEFAULT_BUNDLE_ROOT = (
    Path(__file__).resolve().parents[4]
    / "frontend/trading-tool-frontend/out/_next/static/chunks"
)


def _static_bundle_location(stack: str, bundle_root: Path) -> dict[str, str | int]:
    """Accept coordinates only for an actual checkout-owned JS bundle."""
    for match in _BUNDLE_FRAME.finditer(stack):
        path = bundle_root / match.group("relative")
        try:
            if not path.is_file() or not path.resolve().is_relative_to(bundle_root.resolve()):
                continue
            line = int(match.group("line"))
            column = int(match.group("column"))
            lines = path.read_text(encoding="utf-8").splitlines()
            if line > len(lines) or column > len(lines[line - 1]) + 1:
                continue
        except (OSError, UnicodeError):
            continue
        return {"bundle_basename": path.name, "line": line, "column": column}
    return {}


def _minified_call(message: str) -> str | None:
    match = _MINIFIED_CALL.match(message)
    if not match:
        return None
    if match.group("wrapped_base"):
        return f"(0,{match.group('wrapped_base')}.{match.group('wrapped_member')})"
    return f"{match.group('plain_base')}.{match.group('plain_member')}"


def classify_browser_error(
    error: object, *, stack: object = None, bundle_root: Path | None = None,
) -> dict[str, str | int]:
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
    signature: dict[str, str | int] = {"kind": kind, "stack_area": area}
    if area in {"next_runtime", "next_chunk"}:
        location = _static_bundle_location(frames, bundle_root or _DEFAULT_BUNDLE_ROOT)
        signature.update(location)
        if kind == "js_non_callable" and location:
            call = _minified_call(message)
            if call is not None:
                signature["minified_call"] = call
    return signature


def append_bounded_signature(
    signatures: list[dict[str, str | int]], signature: dict[str, str | int],
) -> None:
    """Keep at most three distinct fixed-code signatures per browser event class."""
    if signature not in signatures and len(signatures) < 3:
        signatures.append(signature)
