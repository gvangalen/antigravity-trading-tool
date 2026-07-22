import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (path) =>
  readFile(new URL(`../${path}`, import.meta.url), "utf8");

const [botPage, tradeContainer, orderPreview, navBar, indicatorConfigModal] = await Promise.all([
  readSource("app/(protected)/bot/page.jsx"),
  readSource("components/bot/TradePanelContainer.jsx"),
  readSource("components/bot/OrderPreviewModal.jsx"),
  readSource("components/ui/NavBar.jsx"),
  readSource("components/scoring/IndicatorConfigModal.jsx"),
]);

test("opens trading only through the explicit bot action", () => {
  assert.match(botPage, /setTradePanelBotId\(\(currentId\)\s*=>\s*currentId\s*===\s*bot\.id\s*\?\s*null\s*:\s*bot\.id\)/);
  assert.match(botPage, /tradePanelBotId\s*===\s*activeBot\?\.id/);
  assert.match(botPage, /event\.stopPropagation\(\)/);
});

test("blocks every supported paused bot representation", () => {
  assert.match(tradeContainer, /bot\?\.is_active\s*===\s*false/);
  assert.match(tradeContainer, /bot\?\.is_paused\s*===\s*true/);
  assert.match(tradeContainer, /toLowerCase\(\)\s*===\s*"paused"/);
  assert.match(tradeContainer, /async function handleOrderRequest\([^)]*\)[\s\S]*?if \(tradingDisabled\)/);
  assert.match(tradeContainer, /async function handleConfirmOrder\(\)[\s\S]*?if \(tradingDisabled\)/);
});

test("requires explicit confirmation for a live order", () => {
  assert.match(orderPreview, /liveIntentConfirmed/);
  assert.match(orderPreview, /!isLive\s*\|\|\s*liveIntentConfirmed/);
  assert.doesNotMatch(orderPreview, /assistantChat|OpenAI|specialist/i);
});

test("keeps administrator navigation role-gated", () => {
  assert.match(navBar, /user\?\.role\s*===\s*['"]admin['"]/);
});

test("reads indicator configuration copy from the shared dictionary namespace", () => {
  assert.match(
    indicatorConfigModal,
    /t\.legacyComponents\.indicatorConfigModal/
  );
  assert.doesNotMatch(indicatorConfigModal, /t\.scoring\.indicatorConfigModal/);
});
