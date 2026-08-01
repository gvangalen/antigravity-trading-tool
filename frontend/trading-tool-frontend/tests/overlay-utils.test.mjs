import test from "node:test";
import assert from "node:assert/strict";

import {
  applyBodyScrollLock,
  createBodyScrollSnapshot,
  createOverlayStack,
  restoreBodyScrollLock,
} from "../components/ui/overlayUtils.js";

test("overlay stack returns the most recent entry", () => {
  const stack = createOverlayStack();
  stack.add({ id: "drawer" });
  stack.add({ id: "dialog" });

  assert.deepEqual(stack.top(), { id: "dialog" });

  stack.remove("dialog");
  assert.deepEqual(stack.top(), { id: "drawer" });
  assert.equal(stack.size(), 1);
});

test("body scroll lock snapshot restores previous inline styles", () => {
  const doc = {
    body: {
      style: {
        overflow: "auto",
        paddingRight: "4px",
      },
    },
  };

  const snapshot = createBodyScrollSnapshot(doc);
  applyBodyScrollLock(doc, 18);

  assert.equal(doc.body.style.overflow, "hidden");
  assert.equal(doc.body.style.paddingRight, "18px");

  restoreBodyScrollLock(doc, snapshot);

  assert.equal(doc.body.style.overflow, "auto");
  assert.equal(doc.body.style.paddingRight, "4px");
});
