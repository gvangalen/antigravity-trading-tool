"use client";

import { useEffect, useState } from "react";
import TradePanel from "./TradePanel";
import { fetchTradePlan, createManualOrder } from "@/lib/api/botApi";
import { fetchLatestBTC } from "@/lib/api/market";

export default function TradePanelContainer({
  bot,
  decision,
  portfolio,
  onManualTrade,
}) {

  const botId = bot?.id;
  const decisionId = decision?.id;

  const [price, setPrice] = useState(null);

  const [balanceQuote, setBalanceQuote] = useState(0);
  const [balanceBase, setBalanceBase] = useState(0);

  const [watchLevels, setWatchLevels] = useState({});
  const [strategy, setStrategy] = useState({});

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

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

    /* ---------- TOTAL BOT BUDGET ---------- */

    const totalBudget = Number(
      bot?.budget?.total_eur ??
      bot?.budget_total_eur ??
      0
    );

    /* ---------- INVESTED AMOUNT ---------- */

    const invested = Math.abs(Number(
      portfolio?.stats?.net_executed_cash_delta_eur ??
      portfolio?.stats?.invested_eur ??
      portfolio?.stats?.invested ??
      bot?.stats?.invested ??
      0
    ));

    /* ---------- AVAILABLE CAPITAL ---------- */

    const availableBudget = Math.max(0, totalBudget - invested);

    setBalanceQuote(availableBudget);

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

  async function handleOrder(order) {

    setError(null);

    try {

      setLoading(true);

      const effectivePrice =
        order.orderType === "market"
          ? price
          : Number(order.price);

      let quantity = Number(order.quantity ?? 0);
      let valueEur = Number(order.value_eur ?? 0);

      /* ---------- SIZE CONVERSION ---------- */

      if (order.size_mode === "quote") {
        quantity = valueEur / effectivePrice;
      } else {
        valueEur = quantity * effectivePrice;
      }

      /* ---------- VALIDATION ---------- */

      if (!quantity || quantity <= 0) {
        throw new Error("Quantity is verplicht");
      }

      if (order.side === "buy" && valueEur > balanceQuote) {
        throw new Error("Onvoldoende budget beschikbaar");
      }

      if (order.side === "sell" && quantity > balanceBase) {
        throw new Error("Onvoldoende BTC");
      }

      /* ---------- CREATE ORDER ---------- */

      await createManualOrder({
        bot_id: botId,
        symbol: "BTC",
        side: order.side,
        quantity: quantity,
        price: effectivePrice,
      });

      /* ---------- REFRESH LOCAL BALANCE ---------- */

      if (order.side === "buy") {
        setBalanceQuote((prev) => Math.max(0, prev - valueEur));
        setBalanceBase((prev) => prev + quantity);
      }

      if (order.side === "sell") {
        setBalanceQuote((prev) => prev + valueEur);
        setBalanceBase((prev) => Math.max(0, prev - quantity));
      }

      onManualTrade?.(order);

    } catch (err) {

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
    <TradePanel
      price={price}
      balanceQuote={balanceQuote}
      balanceBase={balanceBase}
      quoteSymbol="EUR"
      baseSymbol="BTC"
      watchLevels={watchLevels}
      strategy={strategy}
      loading={loading}
      error={error}
      onSubmit={handleOrder}
    />
  );

}
