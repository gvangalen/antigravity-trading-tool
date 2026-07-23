import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (path) =>
  readFile(new URL(`../${path}`, import.meta.url), "utf8");

const [
  botPage,
  botAgentCard,
  tradeContainer,
  orderPreview,
  navBar,
  indicatorConfigModal,
  rootLayout,
  staticServer,
] = await Promise.all([
  readSource("app/(protected)/bot/page.jsx"),
  readSource("components/bot/BotAgentCard.jsx"),
  readSource("components/bot/TradePanelContainer.jsx"),
  readSource("components/bot/OrderPreviewModal.jsx"),
  readSource("components/ui/NavBar.jsx"),
  readSource("components/scoring/IndicatorConfigModal.jsx"),
  readSource("app/layout.jsx"),
  readSource("server.js"),
]);

test("opens trading only through the explicit bot action", () => {
  assert.match(botPage, /setTradePanelBotId\(\(currentId\)\s*=>\s*currentId\s*===\s*bot\.id\s*\?\s*null\s*:\s*bot\.id\)/);
  assert.match(botPage, /tradePanelBotId\s*===\s*activeBot\?\.id/);
  assert.match(botPage, /event\.stopPropagation\(\)/);
  assert.match(botPage, /onTrade=\{\(\)\s*=>\s*toggleTradePanel\(\)\}/);
  assert.match(botAgentCard, /aria-pressed=\{tradeActive\}/);
  assert.match(botAgentCard, /<Wallet size=\{14\}/);
});

test("aligns the desktop trade panel with the selected bot row", () => {
  assert.match(botPage, /botListColumnRef/);
  assert.match(botPage, /botRowRefs\.current\.get\(String\(tradePanelBotId\)\)/);
  assert.match(botPage, /row\.getBoundingClientRect\(\)\.top\s*-\s*column\.getBoundingClientRect\(\)\.top/);
  assert.match(botPage, /--trade-panel-offset/);
  assert.match(botPage, /lg:mt-\[var\(--trade-panel-offset\)\]/);
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

test("recovers a failed navigation chunk with a cache-busting reload", () => {
  assert.match(rootLayout, /ChunkLoadError\|Loading chunk\|Cannot find module/);
  assert.match(rootLayout, /RECOVERY_COOLDOWN_MS\s*=\s*30000/);
  assert.match(rootLayout, /searchParams\.set\("__tm_recover"/);
  assert.match(rootLayout, /window\.location\.replace/);
});

test("keeps route documents fresh while caching immutable build assets", () => {
  assert.match(staticServer, /relativePath\.startsWith\('_next\/static\/'\)/);
  assert.match(staticServer, /max-age=31536000, immutable/);
  assert.match(staticServer, /no-store, no-cache, must-revalidate/);
});
