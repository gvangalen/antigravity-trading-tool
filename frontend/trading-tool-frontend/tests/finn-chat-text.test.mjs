import assert from "node:assert/strict";
import test from "node:test";

import { parseFinnChatText } from "../lib/finnChatText.mjs";

test("FINN chat formats paired emphasis without showing markdown markers", () => {
  assert.deepEqual(parseFinnChatText("Eerst **wachten op bevestiging**.\nDan herzien."), [
    { text: "Eerst ", bold: false },
    { text: "wachten op bevestiging", bold: true },
    { text: ".\nDan herzien.", bold: false },
  ]);
});

test("unpaired markers remain literal text", () => {
  assert.deepEqual(parseFinnChatText("Dit is **nog open"), [
    { text: "Dit is **nog open", bold: false },
  ]);
});

test("FINN headings render as emphasis instead of raw hash markers", () => {
  assert.deepEqual(parseFinnChatText("## Conclusie\n**Sterk:** de niveaus zijn opgeslagen."), [
    { text: "Conclusie", bold: true },
    { text: "\n", bold: false },
    { text: "Sterk:", bold: true },
    { text: " de niveaus zijn opgeslagen.", bold: false },
  ]);
});

test("FINN renders single-star setup names without exposing markers", () => {
  assert.deepEqual(parseFinnChatText("De match voor *BTC Breakout Full* is onbewezen."), [
    { text: "De match voor ", bold: false },
    { text: "BTC Breakout Full", bold: true },
    { text: " is onbewezen.", bold: false },
  ]);
  assert.deepEqual(parseFinnChatText("Risico = 2 * 3 * 4"), [
    { text: "Risico = 2 * 3 * 4", bold: false },
  ]);
});
