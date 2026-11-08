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


@pytest.mark.parametrize("call,expected_call", [
    ("(0,r.A)", "(0,r.A)"),
    ("r.A", "r.A"),
])
def test_known_bundle_coordinate_and_strict_minified_call(tmp_path, call, expected_call):
    bundle = tmp_path / "app" / "(protected)" / "bot" / "page-a1b2c3.js"
    bundle.parent.mkdir(parents=True)
    bundle.write_text("var r=123456789;\n", encoding="utf-8")
    result = classify_browser_error(
        f"TypeError: {call} is not a function\nprivate fixture token",
        stack=("at https://tradamind.com/_next/static/chunks/"
               "app/(protected)/bot/page-a1b2c3.js:1:5\nprivate owner ID"),
        bundle_root=tmp_path,
    )
    assert result == {
        "kind": "js_non_callable", "stack_area": "next_chunk",
        "bundle_basename": "page-a1b2c3.js", "line": 1, "column": 5,
        "minified_call": expected_call,
    }
    assert not any(secret in json.dumps(result) for secret in ("private", "fixture", "token", "owner"))


@pytest.mark.parametrize("message,stack,location_expected", [
    ("TypeError: private.Secret is not a function",
     "at https://tradamind.com/_next/static/chunks/page-known.js:1:5", True),
    ("TypeError: (0,r.A) is not a function",
     "at https://tradamind.com/_next/static/chunks/page-known.js?token=private:1:5", False),
    ("TypeError: (0,r.A) is not a function",
     "at https://evil.example/_next/static/chunks/page-known.js:1:5", False),
    ("TypeError: (0,r.A) is not a function",
     "at https://tradamind.com/_next/static/chunks/page-missing.js:1:5", False),
    ("TypeError: (0,r.A) is not a function",
     "at https://tradamind.com/_next/static/chunks/page-known.js:1:999999", False),
])
def test_untrusted_or_unverifiable_location_never_exports_bundle_data(
    tmp_path, message, stack, location_expected,
):
    (tmp_path / "page-known.js").write_text("var r=123456789;\n", encoding="utf-8")
    result = classify_browser_error(message, stack=stack, bundle_root=tmp_path)
    assert ("bundle_basename" in result) is location_expected
    assert "minified_call" not in result
    assert "private" not in json.dumps(result)
    assert "token" not in json.dumps(result)
