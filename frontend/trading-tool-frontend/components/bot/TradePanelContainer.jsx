"use client";

import { useEffect, useState } from "react";
import { useModal } from "@/components/modal/ModalProvider";
import TradePanel from "./TradePanel";
import OrderPreviewModal from "./OrderPreviewModal";
import { fetchTradePlan, createManualOrder, previewManualOrder } from "@/lib/api/botApi";
import { fetchLatestBTC } from "@/lib/api/market";

export default function TradePanelContainer({
  bot,
  decision,
  portfolio,
  onManualTrade,
}) {

  const { showSnackbar } = useModal();
  const botId = bot?.id;
  const decisionId = decision?.id;

  const [price, setPrice] = useState(null);

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

  useEffect(() => {

    if (!botId) return;

    loadPrice();

    const interval = setInterval(loadPrice, 60000);

    return () => clearInterval(interval);

  }, [botId]);

  async function loadPrice() {

    try {

      const btc = await fetchLatestBTC();

      if (btc?.price) {
        setPrice(Number(btc.price));
      }

    } catch (err) {

      console.error("Price load error:", err);

    }

  }

  /* =====================================================
     ORDER HANDLER
  ===================================================== */

  async function handleOrderRequest(order) {
    setDraftOrder(order);
    await refreshPreview(order);
    setShowPreview(true);
  }

  async function refreshPreview(order = draftOrder) {
    if (!order) return;
    try {
      setLoading(true);
      const data = await previewManualOrder({
        bot_id: botId,
        symbol: "BTC",
        side: order.side,
        quantity: order.quantity,
        price: order.orderType === "market" ? price : order.price,
        value_eur: order.value_eur,
      });
      setPreviewData(data);
    } catch (err) {
      console.error("Preview error:", err);
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
        symbol: "BTC",
        side: draftOrder.side,
        quantity: previewData.quantity,
        price: previewData.price,
        value_eur: previewData.gross_eur,
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

  /* =====================================================
     PRICE LOADING STATE
  ===================================================== */

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
        baseSymbol="BTC"
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
          currencySymbol={bot?.base_currency === "USD" ? "$" : "€"}
          onConfirm={handleConfirmOrder}
          onCancel={() => setShowPreview(false)}
          onRefresh={refreshPreview}
        />
      )}
    </>
  );
}
