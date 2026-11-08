"""The protected browser diagnostic must never publish browser error text."""

import json

import pytest

from backend.scripts.qa_browser_error_signature import (
    append_bounded_signature,
    classify_browser_error,
)


@pytest.mark.parametrize("message,stack,expected", [
    ("TypeError: Cannot read properties of undefined (reading 'secret')",
     "at https://tradamind.com/_next/static/chunks/app/bot/page.js?token=private",
     {"kind": "js_undefined_property", "stack_area": "next_chunk"}),
    ("Hydration failed because of private content",
     "at BotFocusView.jsx?fixture=private",
     {"kind": "react_hydration", "stack_area": "bot_focus_view"}),
    ("ChunkLoadError: Loading chunk private failed",
     "at https://tradamind.com/_next/static/chunks/webpack-private.js",
     {"kind": "next_chunk_load", "stack_area": "next_runtime"}),
    ("private fixture name, token and account state",
     "at https://evil.example/path?token=private",
     {"kind": "other", "stack_area": "external_or_unknown_origin"}),
    ("ReferenceError: private is not defined", "",
     {"kind": "js_reference_error", "stack_area": "unavailable"}),
])
def test_classifier_emits_only_fixed_codes(message, stack, expected):
    result = classify_browser_error(message, stack=stack)
    assert result == expected
    serialized = json.dumps(result)
    assert "private" not in serialized
    assert "secret" not in serialized
    assert "token" not in serialized


def test_signatures_are_distinct_and_bounded():
    signatures = []
    for kind in ("first", "first", "second", "third", "fourth"):
        append_bounded_signature(signatures, {"kind": kind, "stack_area": "unavailable"})
    assert [item["kind"] for item in signatures] == ["first", "second", "third"]
