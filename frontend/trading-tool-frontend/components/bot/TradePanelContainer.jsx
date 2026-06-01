"use client";

import { useEffect, useRef, useState } from "react";
import { useModal } from "@/components/modal/ModalProvider";
import TradePanel from "./TradePanel";
import OrderPreviewModal from "./OrderPreviewModal";
import { fetchTradePlan, createManualOrder, preflightManualOrder, previewManualOrder } from "@/lib/api/botApi";
import { fetchLatestPrice } from "@/lib/api/market";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";

export default function TradePanelContainer({
  bot,
  decision,
  portfolio,
  onManualTrade,
}) {

  const { showSnackbar } = useModal();
  const botId = bot?.id;
  const decisionId = decision?.id;
  const tradeSymbol = (
    bot?.strategy?.setup?.symbol ||
    bot?.strategy?.symbol ||
    bot?.symbol ||
    decision?.symbol ||
    "BTC"
  ).toUpperCase();

  const [price, setPrice] = useState(null);
  const priceFetchingRef = useRef(false);

  const [balanceQuote, setBalanceQuote] = useState(0);
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

    const remainingTotal = Math.max(0, totalBudget - invested);
    const remainingDaily = dailyLimit > 0 ? Math.max(0, dailyLimit - todaySpent) : Infinity;

    // Available for trade is the tightest of all limits
    let cappedAvailable = remainingTotal;
    if (remainingDaily < cappedAvailable) cappedAvailable = remainingDaily;
    if (maxOrder > 0 && maxOrder < cappedAvailable) cappedAvailable = maxOrder;

    setBalanceQuote(remainingTotal);
    setAvailableQuote(cappedAvailable);

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
    portfolio?.stats?.net_executed_cash_delta_eur,
    portfolio?.stats?.invested_eur,
    portfolio?.stats?.net_qty,
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
    enabled: Boolean(botId),
    intervalMs: 60000,
    backgroundIntervalMs: 300000,
    runImmediately: true,
    deps: [botId, tradeSymbol],
  });

  async function loadPrice() {
    if (priceFetchingRef.current) return;
    priceFetchingRef.current = true;

    try {

      const latest = await fetchLatestPrice(tradeSymbol, { forceFresh: true });

      if (latest?.price) {
        setPrice(Number(latest.price));
      }

    } catch (err) {

      console.error("Price load error:", err);

    } finally {
      priceFetchingRef.current = false;
    }

  }

  /* =====================================================
     ORDER HANDLER
  ===================================================== */

  async function handleOrderRequest(order) {
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
        message: err.message || "Order preview mislukt",
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirmOrder() {
    if (!previewData || !draftOrder) return;
    setError(null);

    try {
      setLoading(true);

      /* ---------- CREATE ORDER ---------- */

      await createManualOrder({
        bot_id: botId,
        symbol: tradeSymbol,
        side: draftOrder.side,
        quantity: previewData.quantity,
        price: previewData.price,
        value_eur: previewData.gross_eur ?? previewData.notional_eur,
        idempotency_key: draftOrder.idempotency_key,
        risk_acknowledged: draftOrder.risk_acknowledged,
        live_preflight_token: draftOrder.live_preflight_token,
        live_preflight_action_id: draftOrder.live_preflight_action_id,
        setup_block_acknowledged: draftOrder.setup_block_acknowledged,
      });

      /* ---------- REFRESH LOCAL BALANCE ---------- */

      if (draftOrder.side === "buy") {
        setBalanceQuote((prev) => Math.max(0, prev - previewData.gross_eur));
        setBalanceBase((prev) => prev + previewData.quantity);
      }

      if (draftOrder.side === "sell") {
        setBalanceQuote((prev) => prev + previewData.gross_eur);
        setBalanceBase((prev) => Math.max(0, prev - previewData.quantity));
      }

      onManualTrade?.(draftOrder);
      setShowPreview(false);

      showSnackbar(
        `${draftOrder.side === "buy" ? "Koop" : "Verkoop"} order succesvol geplaatst!`,
        "success"
      );
      
      window.dispatchEvent(new Event("portfolio:updated"));

    } catch (err) {
      showSnackbar(err.message || "Order mislukt", "danger");
      setError(err.message || "Order mislukt");
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

  /* =====================================================
     AGGRESSIVE SCROLL SYNC (FOR SAFARI)
  ===================================================== */
  useEffect(() => {
    const sync = () => {
      const el = document.getElementById("tp-final-v2155");
      if (el) {
        el.style.position = "relative";
        el.style.height = "auto";
        el.style.display = "block";
      }
    };
    window.addEventListener("scroll", sync);
    sync();
    return () => window.removeEventListener("scroll", sync);
  }, []);

  if (!price) {
    return (
      <div className="p-4 text-sm text-gray-500">
        Marktprijs laden...
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
        balanceQuote={balanceQuote}
        availableQuote={availableQuote}
        balanceBase={balanceBase}
        quoteSymbol={bot?.base_currency || "EUR"}
        baseSymbol={tradeSymbol}
        symbol={tradeSymbol}
        watchLevels={watchLevels}
        strategy={strategy}
        loading={loading}
        error={error}
        onSubmit={handleOrderRequest}
      />

      {showPreview && (
        <OrderPreviewModal
          preview={previewData}
          loading={loading}
          botName={bot?.name || `Bot #${botId}`}
          currencySymbol={bot?.base_currency === "USD" ? "$" : "€"}
          onConfirm={handleConfirmOrder}
          onAcknowledgeSetupBlock={handleAcknowledgeSetupBlock}
          onCancel={() => setShowPreview(false)}
          onRefresh={refreshPreview}
        />
      )}
    </>
  );
}
