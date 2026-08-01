"use client";

export function createOverlayStack() {
  const overlays = [];

  return {
    add(entry) {
      overlays.push(entry);
      return entry;
    },
    remove(id) {
      const index = overlays.findIndex((entry) => entry.id === id);
      if (index >= 0) overlays.splice(index, 1);
    },
    top() {
      return overlays[overlays.length - 1] || null;
    },
    size() {
      return overlays.length;
    },
  };
}

export function createBodyScrollSnapshot(doc) {
  return {
    overflow: doc.body.style.overflow,
    paddingRight: doc.body.style.paddingRight,
  };
}

export function getScrollbarCompensation(win, doc) {
  return Math.max(0, win.innerWidth - doc.documentElement.clientWidth);
}

export function applyBodyScrollLock(doc, scrollbarCompensation) {
  const snapshot = createBodyScrollSnapshot(doc);
  doc.body.style.overflow = "hidden";
  if (scrollbarCompensation > 0) {
    doc.body.style.paddingRight = `${scrollbarCompensation}px`;
  }
  return snapshot;
}

export function restoreBodyScrollLock(doc, snapshot) {
  doc.body.style.overflow = snapshot?.overflow || "";
  doc.body.style.paddingRight = snapshot?.paddingRight || "";
}
