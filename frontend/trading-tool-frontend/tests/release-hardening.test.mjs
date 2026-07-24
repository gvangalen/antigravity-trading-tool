import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (path) =>
  readFile(new URL(`../${path}`, import.meta.url), "utf8");

const [
  botPage,
  botAgentCard,
  botScores,
  myPlanWorkflow,
  assetWorkspace,
  tradeContainer,
  orderPreview,
  navBar,
  indicatorConfigModal,
  rootLayout,
  staticServer,
] = await Promise.all([
  readSource("app/(protected)/bot/page.jsx"),
  readSource("components/bot/BotAgentCard.jsx"),
  readSource("components/bot/BotScores.jsx"),
  readSource("components/workflows/MyPlanWorkflow.jsx"),
  readSource("components/workspaces/asset/AssetWorkspaceV3.jsx"),
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

test("ties automation context scores to the selected execution chain", () => {
  assert.match(botPage, /<BotScores[\s\S]*?bot=\{activeBot\}/);
  assert.match(botPage, /strategies=\{strategies\}/);
  assert.match(botPage, /setups=\{setups\}/);
  assert.match(botPage, /bots=\{bots\}/);
  assert.match(botScores, /resolveBotExecutionChain\(/);
  assert.match(botScores, /readLinkedSetupScore\(/);
  assert.match(botScores, /const hasSetupMismatch = setupScore !== null && setupScore < 40/);
  assert.match(botScores, /key: "plan"/);
  assert.match(botScores, /key: "market"/);
  assert.match(botScores, /key: "macro"/);
  assert.match(botScores, /key: "technical"/);
  assert.match(botScores, /key: "setup"/);
  assert.match(botScores, /copy\.cannotAssess/);
  assert.match(botScores, /recommendedSetup/);
  assert.match(botScores, /copy\.betterMatchTitle/);
  assert.match(botScores, /copy\.currentChainHint/);
  assert.match(botScores, /lg:grid-cols-4/);
  assert.match(botScores, /copy\.reviewPlanAction/);
});

test("keeps my plan linked to concrete bot activation state", () => {
  assert.match(myPlanWorkflow, /fetchBotConfigs/);
  assert.match(myPlanWorkflow, /fetchActiveSetup\(activeSymbol\)/);
  assert.match(myPlanWorkflow, /const marketBestPlan = useMemo/);
  assert.match(myPlanWorkflow, /copy\.bestForMarket/);
  assert.match(myPlanWorkflow, /bot:\s*plan\.strategy \? botByStrategyId\.get/);
  assert.match(myPlanWorkflow, /copy\.botActive/);
  assert.match(myPlanWorkflow, /copy\.botPaused/);
  assert.match(myPlanWorkflow, /copy\.noBotLinked/);
  assert.match(myPlanWorkflow, /bot_id=/);
  assert.match(myPlanWorkflow, /action=new_bot/);
  assert.match(myPlanWorkflow, /strategy_id=/);
});

test("prefills automation bot creation from my plan context", () => {
  assert.match(botPage, /searchParams\.get\("strategy_id"\)/);
  assert.match(botPage, /searchParams\.get\("plan_name"\)/);
  assert.match(botPage, /strategies\.find\(\(strategy\) => strategy\.id === requestedStrategyId\)/);
  assert.match(botPage, /strategy_id: matchingStrategy\?\.id \?\? null/);
  assert.match(botPage, /const isPlanActivation = Boolean\(initialValues\?\.strategy_id\)/);
  assert.match(botPage, /copy\.createFromPlanTitle/);
});

test("shows the best current plan candidate on the analysis bridge", () => {
  assert.match(assetWorkspace, /workspace\?\.daily\?\.setup\?\.active_setups/);
  assert.match(assetWorkspace, /fetchActiveSetup\(activeSymbol\)/);
  assert.match(assetWorkspace, /if \(!matchingSetups\.length\)/);
  assert.match(assetWorkspace, /const linkedMatch = matchingSetups\.find/);
  assert.match(assetWorkspace, /const runtimeMatch = runtimeSetupId == null/);
  assert.match(assetWorkspace, /strategy\?\.setup_id \?\? strategy\?\.setup\?\.id/);
  assert.match(assetWorkspace, /displayName:\s*linkedStrategy\?\.name \|\|\s*bestMatch\?\.name \|\|\s*marketBestSetup\?\.name/);
  assert.match(assetWorkspace, /candidate=\{hasScoreData \? planBridgeCandidate : null\}/);
  assert.doesNotMatch(assetWorkspace, /setup=\{hasScoreData \? setup : null\}/);
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
