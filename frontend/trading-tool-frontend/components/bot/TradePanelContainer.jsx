"use client";

import { useEffect, useRef, useState } from "react";
import { useModal } from "@/components/modal/ModalProvider";
import TradePanel from "./TradePanel";
import OrderPreviewModal from "./OrderPreviewModal";
import { fetchTradePlan, createManualOrder, preflightManualOrder, previewManualOrder } from "@/lib/api/botApi";
import { fetchLatestPrice } from "@/lib/api/market";
import { fetchPaperPriceEur } from "@/lib/api/botApi";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";
import { useTranslation } from "@/app/providers/I18nProvider";
import { getBotApiErrorMessage } from "@/lib/bot/botApiErrorMessage.mjs";
import { manualTradeAvailableQuote } from "@/lib/bot/manualTradeBudget.mjs";

export default function TradePanelContainer({
  bot,
  decision,
  portfolio,
  onManualTrade,
}) {

  const { showSnackbar } = useModal();
  const { t } = useTranslation();
  const copy = t?.botPage?.tradePanel || {};
  const tradingDisabled = Boolean(
    bot?.is_active === false ||
    bot?.is_paused === true ||
    String(bot?.status || "").toLowerCase() === "paused"
  );
  const botId = bot?.id;
  const decisionId = decision?.id;
  const tradeSymbol = (
    bot?.strategy?.setup?.symbol ||
    bot?.strategy?.symbol ||
    bot?.symbol ||
    decision?.symbol ||
    ""
  ).toUpperCase();

  const [price, setPrice] = useState(null);
  const priceFetchingRef = useRef(false);

  const [availableQuote, setAvailableQuote] = useState(0);
  const [balanceBase, setBalanceBase] = useState(0);

  const [watchLevels, setWatchLevels] = useState({});
  const [strategy, setStrategy] = useState({});

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  /* =====================================================
     PREVIEW STATE
  ===================================================== */
  
  const [showPreview, setShowPreview] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [draftOrder, setDraftOrder] = useState(null);

  /* =====================================================
     BOT CAPITAL
  ===================================================== */

  useEffect(() => {

    if (!bot) return;

    /* ---------- WATCH LEVELS ---------- */

    setWatchLevels({
      breakout: decision?.watch_levels?.breakout_trigger ?? null,
      pullback: decision?.watch_levels?.pullback_zone ?? null,
    });

    /* ---------- BUDGET LIMITS ---------- */

    const dailyLimit = Number(
    bot?.budget?.daily_limit_eur ?? bot?.budget_daily_limit_eur ?? 0
  );
  const totalBudget = Number(
    bot?.budget?.total_eur ?? bot?.budget_total_eur ?? 0
  );
  const maxOrder = Number(
    bot?.budget?.max_order_eur ?? bot?.budget_max_order_eur ?? 0
  );

  const todaySpent = Number(
    portfolio?.stats?.today_spent_eur ?? portfolio?.stats?.today_spent ?? 0
  );
  const invested = Number(
    portfolio?.stats?.invested_eur ?? portfolio?.stats?.executed_cash ?? 0
  );

    /* ---------- INVESTED AMOUNT ---------- */

    const investedAmount = Math.abs(Number(
      portfolio?.stats?.net_executed_cash_delta_eur ??
      portfolio?.stats?.invested_eur ??
      portfolio?.stats?.invested ??
      bot?.stats?.invested ??
      0
    ));

    /* ---------- CALCULATE CAPS ---------- */

    const { available } = manualTradeAvailableQuote({
      totalBudget, invested, dailyLimit, todaySpent, maxOrder,
      isLive: Boolean(bot?.is_live), paperCash: portfolio?.stats?.paper_cash_eur,
    });
    setAvailableQuote(available);

    /* ---------- BTC HOLDINGS ---------- */

    const btcHoldings = Number(
      portfolio?.stats?.net_qty ??
      portfolio?.holdings?.btc ??
      portfolio?.wallet?.base_balance ??
      0
    );

    setBalanceBase(btcHoldings);

  }, [
    bot?.budget?.total_eur,
    bot?.budget_total_eur,
    bot?.budget?.daily_limit_eur,
    bot?.budget_daily_limit_eur,
    bot?.budget?.max_order_eur,
    bot?.budget_max_order_eur,
    bot?.is_live,
    portfolio?.stats?.net_executed_cash_delta_eur,
    portfolio?.stats?.invested_eur,
    portfolio?.stats?.net_qty,
    portfolio?.stats?.paper_cash_eur,
    portfolio?.stats?.today_spent_eur,
    portfolio?.stats?.today_spent,
    decision
  ]);

  /* =====================================================
     LOAD STRATEGY PLAN
  ===================================================== */

  useEffect(() => {

    if (!decisionId) return;

    loadPlan();

  }, [decisionId]);

  async function loadPlan() {

    try {

      const plan = await fetchTradePlan(decisionId);

      setStrategy({
        stop_loss: plan?.stop_loss?.price ?? null,
        targets: Array.isArray(plan?.targets)
          ? plan.targets.map((t) => t.price)
          : [],
      });

    } catch (err) {

      console.error("Plan load error:", err);

    }

  }

  /* =====================================================
     PRICE POLLING
  ===================================================== */

  useVisibilityPolling(loadPrice, {
    enabled: Boolean(botId && tradeSymbol),
    intervalMs: 60000,
    backgroundIntervalMs: 300000,
    runImmediately: true,
    deps: [botId, tradeSymbol],
  });

  async function loadPrice() {
    if (priceFetchingRef.current) return;
    priceFetchingRef.current = true;

    try {

      const latest = bot?.is_live
        ? await fetchLatestPrice(tradeSymbol, { forceFresh: true })
        : await fetchPaperPriceEur(botId);

      const nextPrice = bot?.is_live ? latest?.price : latest?.price_eur;
      if (nextPrice) {
        setPrice(Number(nextPrice));
      } else {
        setPrice(null);
      }

    } catch (err) {

      console.error("Price load error:", err);
      setPrice(null);

    } finally {
      priceFetchingRef.current = false;
    }

  }

  /* =====================================================
     ORDER HANDLER
  ===================================================== */

  async function handleOrderRequest(order) {
    if (tradingDisabled) {
      showSnackbar(copy.pausedBotTradingBlocked, "warning");
      return;
    }
    const preflightToken =
      order.live_preflight_token ||
      order.live_preflight_action_id ||
      decision?.live_preflight_token ||
      decision?.live_preflight_action_id ||
      decision?.live_preflight?.token ||
      decision?.preflight?.token ||
      null;
    const idempotencyKey =
      order.idempotency_key ||
      (typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
    const safeOrder = {
      ...order,
      idempotency_key: idempotencyKey,
      risk_acknowledged: Boolean(bot?.is_live),
      setup_block_acknowledged: Boolean(order.setup_block_acknowledged),
      live_preflight_token: preflightToken,
    };
    setDraftOrder(safeOrder);
    await refreshPreview(safeOrder);
    setShowPreview(true);
  }

  async function refreshPreview(order = draftOrder) {
    if (!order) return;
    try {
      setLoading(true);
      const payload = {
        bot_id: botId,
        symbol: tradeSymbol,
        side: order.side,
        quantity: order.quantity,
        price: order.orderType === "market" ? price : order.price,
        price_currency: bot?.is_live ? bot?.base_currency : "EUR",
        value_eur: order.value_eur,
        idempotency_key: order.idempotency_key,
        risk_acknowledged: order.risk_acknowledged,
        live_preflight_token: order.live_preflight_token,
        live_preflight_action_id: order.live_preflight_action_id,
        setup_block_acknowledged: order.setup_block_acknowledged,
      };
      const data = bot?.is_live
        ? await preflightManualOrder(payload)
        : await previewManualOrder(payload);
      setPreviewData({
        symbol: payload.symbol,
        side: payload.side,
        quantity: payload.quantity,
        price: payload.price,
        notional_eur: Number(payload.quantity || 0) * Number(payload.price || 0),
        is_live: Boolean(bot?.is_live),
        bot_id: botId,
        strategy_id: bot?.strategy?.id || bot?.strategy_id || decision?.strategy_id || null,
        setup_id: bot?.strategy?.setup?.id || bot?.setup_id || decision?.setup_id || null,
        ...data,
      });
    } catch (err) {
      console.error("Preview error:", err);
      setPreviewData({
        ok: false,
        blocked: true,
        symbol: tradeSymbol,
        side: order.side,
        bot_id: botId,
        is_live: Boolean(bot?.is_live),
        message: getBotApiErrorMessage(err, copy.previewFailed),
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirmOrder() {
    if (tradingDisabled) {
      setShowPreview(false);
      showSnackbar(copy.pausedBotTradingBlocked, "warning");
      return;
    }
    if (!previewData || !draftOrder) return;
    setError(null);

    try {
      setLoading(true);

      /* ---------- CREATE ORDER ---------- */

      const result = await createManualOrder({
        bot_id: botId,
        symbol: tradeSymbol,
        side: draftOrder.side,
        quantity: previewData.quantity,
        price: previewData.price,
        price_currency: previewData.price_currency,
        paper_preview_token: previewData.paper_preview_token,
        value_eur: previewData.gross_eur ?? previewData.notional_eur,
        idempotency_key: draftOrder.idempotency_key,
        risk_acknowledged: draftOrder.risk_acknowledged,
        live_preflight_token: draftOrder.live_preflight_token,
        live_preflight_action_id: draftOrder.live_preflight_action_id,
        setup_block_acknowledged: draftOrder.setup_block_acknowledged,
      });

      // The exchange may accept an order before any fill exists. Balances come
      // from the refreshed server portfolio, never from the requested amount.
      onManualTrade?.(result);
      setShowPreview(false);

      const status = String(result?.status || "").toLowerCase();
      if (status === "filled") {
        showSnackbar(
          `${draftOrder.side === "buy" ? copy.buySuccess : copy.sellSuccess} ${copy.orderPlacedSuccess}`,
          "success"
        );
      } else if (["sent", "partially_filled", "partial"].includes(status)) {
        showSnackbar(copy.orderAwaitingExchange, "info");
      } else if (["sending", "unknown_exchange_state"].includes(status)) {
        showSnackbar(copy.orderStateUnknown, "warning");
      } else {
        showSnackbar(copy.orderNotFilled, "warning");
      }
      
      window.dispatchEvent(new Event("portfolio:updated"));

    } catch (err) {
      const message = getBotApiErrorMessage(err, copy.orderFailed);
      showSnackbar(message, "danger");
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  async function handleAcknowledgeSetupBlock() {
    if (!draftOrder) return;
    const acknowledged = {
      ...draftOrder,
      setup_block_acknowledged: true,
    };
    setDraftOrder(acknowledged);
    await refreshPreview(acknowledged);
  }

  /* =====================================================
     PRICE LOADING STATE
  ===================================================== */

  if (!tradeSymbol) {
    return (
      <div className="p-4 text-sm font-semibold text-amber-700 dark:text-amber-300">
        {copy.missingBotContext}
      </div>
    );
  }

  if (!price) {
    return (
      <div className="p-4 text-sm text-gray-500">
        {copy.loadingMarketPrice}
      </div>
    );
  }

  /* =====================================================
     UI
  ===================================================== */

  return (
    <>
      <TradePanel
        price={price}
        availableQuote={availableQuote}
        balanceBase={balanceBase}
        quoteSymbol={bot?.is_live ? (bot?.base_currency || "EUR") : "EUR"}
        baseSymbol={tradeSymbol}
        symbol={tradeSymbol}
        watchLevels={watchLevels}
        strategy={strategy}
        loading={loading}
        error={error}
        disabled={tradingDisabled}
        paperMarketOnly={!bot?.is_live}
        disabledReason={copy.pausedBotTradingBlocked}
        onSubmit={handleOrderRequest}
      />

      {showPreview && (
        <OrderPreviewModal
          preview={previewData}
          loading={loading}
          botName={bot?.name || `Bot #${botId}`}
          currencySymbol={bot?.is_live && bot?.base_currency === "USD" ? "$" : "€"}
          onConfirm={handleConfirmOrder}
          onAcknowledgeSetupBlock={handleAcknowledgeSetupBlock}
          onCancel={() => setShowPreview(false)}
          onRefresh={refreshPreview}
        />
      )}
    </>
  );
}
