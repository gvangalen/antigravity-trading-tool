import assert from "node:assert/strict";
import test from "node:test";

import { toSnackbarMessage } from "../lib/ui/snackbarMessage.js";

test("formats FastAPI validation details before rendering a snackbar", () => {
  assert.equal(
    toSnackbarMessage({ loc: ["body", "email"], msg: "Email is already registered", type: "value_error" }),
    "Email is already registered"
  );
  assert.equal(toSnackbarMessage([{ msg: "Missing field" }]), "Missing field");
});

test("uses a safe fallback for unrenderable snackbar values", () => {
  assert.equal(toSnackbarMessage({ loc: ["body"], type: "value_error" }), "Er is iets misgegaan.");
});
