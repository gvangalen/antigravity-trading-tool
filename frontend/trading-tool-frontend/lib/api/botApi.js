"use client";

import { fetchAuth } from "@/lib/api/auth";

/**
 * Trading Bot API — FINAL (HARDENED v3)
 * --------------------------------------------------
 * ✅ Safe parsing
 * ✅ Trade plan fallback
 * ✅ Watch levels support
 * ✅ Type safety
 * ✅ Error handling
 */

/* =====================================================
   🛟 Helpers
===================================================== */

const ensureArray = (v) => (Array.isArray(v) ? v : []);
const ensureObject = (v) => (v && typeof v === "object" ? v : {});

const toNumber = (v, fallback = 0) => {
  const n = Number(v);
  return isNaN(n) ? fallback : n;
};

const buildQuery = (params) =>
  new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== null)
      .map(([k, v]) => [k, String(v)])
  ).toString();

const handleApi = async (promise) => {
  const res = await promise;
  if (res && res.ok === false) {
    throw new Error(res.error || "API error");
  }
  return res;
};

/* =====================================================
   🤖 1. BOT CONFIGS
===================================================== */

export const fetchBotConfigs = async () => {
  const data = await handleApi(fetchAuth(`/api/bot/configs`));
  return ensureArray(data);
};

export const createBotConfig = async (payload) => {
  if (!payload?.name) throw new Error("Bot naam is verplicht");
  if (!payload?.strategy_id) throw new Error("strategy_id is verplicht");

  return handleApi(
    fetchAuth(`/api/bot/configs`, {
      method: "POST",
      body: JSON.stringify(payload),
    })
  );
};

export const updateBotConfig = async (bot_id, payload = {}) => {
  if (!bot_id) throw new Error("bot_id is verplicht");

  return handleApi(
    fetchAuth(`/api/bot/configs/${bot_id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    })
  );
};

export const deleteBotConfig = async (bot_id) => {
  if (!bot_id) throw new Error("bot_id is verplicht");

  return handleApi(
    fetchAuth(`/api/bot/configs/${bot_id}`, {
      method: "DELETE",
    })
  );
};

/* =====================================================
   📄 2. BOT TODAY (🔥 FIXED)
===================================================== */

export const fetchBotToday = async () => {
  const data = await handleApi(fetchAuth(`/api/bot/today`));

  if (!data || typeof data !== "object") return null;

  const decisions = ensureArray(data.decisions).map((d) => {
    const rawPlan = ensureObject(d.trade_plan);

    return {
      ...d,

      // 🔥 SAFE TRADE PLAN
      trade_plan: {
        entry_plan: ensureArray(rawPlan.entry_plan),
        stop_loss: ensureObject(rawPlan.stop_loss),
        targets: ensureArray(rawPlan.targets),
        risk: ensureObject(rawPlan.risk),
      },

      // 🔥 WATCH LEVELS FIX
      watch_levels: ensureObject(d.watch_levels),

      // 🔥 NUMERIC SAFETY
      amount_eur: toNumber(d.amount_eur),
      requested_amount_eur: toNumber(d.requested_amount_eur),
    };
  });

  return {
    ...data,
    scores: ensureObject(data.scores),
    decisions,
    orders: ensureArray(data.orders),
    executions: ensureArray(data.executions),
  };
};

/* =====================================================
   📜 3. BOT HISTORY
===================================================== */

export const fetchBotHistory = async (days = 30) => {
  const query = buildQuery({ days });
  const data = await handleApi(fetchAuth(`/api/bot/history?${query}`));
  return ensureArray(data);
};

/* =====================================================
   📊 4. BOT PORTFOLIOS
===================================================== */

export const fetchBotPortfolios = async () => {
  const data = await handleApi(fetchAuth(`/api/bot/portfolios`));
  return ensureArray(data);
};

/* =====================================================
   🔁 5. GENERATE BOT DECISION
===================================================== */

export const generateBotDecision = async ({ bot_id, report_date = null }) => {
  if (!bot_id) throw new Error("bot_id is verplicht");

  return handleApi(
    fetchAuth(`/api/bot/generate/today`, {
      method: "POST",
      body: JSON.stringify({
        bot_id,
        ...(report_date && { report_date }),
      }),
    })
  );
};

/* =====================================================
   ✅ 6. MARK EXECUTED
===================================================== */

export const markBotExecuted = async ({ bot_id, decision_id }) => {
  if (!bot_id) throw new Error("bot_id is verplicht");
  if (!decision_id) throw new Error("decision_id is verplicht");

  return handleApi(
    fetchAuth(`/api/bot/mark_executed`, {
      method: "POST",
      body: JSON.stringify({ bot_id, decision_id }),
    })
  );
};

/* =====================================================
   ⏭️ 7. SKIP BOT
===================================================== */

export const skipBotToday = async ({ bot_id, report_date = null }) => {
  if (!bot_id) throw new Error("bot_id is verplicht");

  return handleApi(
    fetchAuth(`/api/bot/skip`, {
      method: "POST",
      body: JSON.stringify({
        bot_id,
        ...(report_date && { report_date }),
      }),
    })
  );
};

/* =====================================================
   📈 8. BOT TRADES (🔥 SAFE)
===================================================== */

export const fetchBotTrades = async (bot_id, limit = 50) => {
  if (!bot_id) throw new Error("bot_id is verplicht");

  const query = buildQuery({ bot_id, limit });

  const data = await handleApi(fetchAuth(`/api/bot/trades?${query}`));

  return ensureArray(data).map((t) => ({
    ...t,
    qty: toNumber(t.qty),
    price: toNumber(t.price),
    amount_eur: toNumber(t.amount_eur),
  }));
};

/* =====================================================
   📊 9. TRADE PLAN (GET)
===================================================== */

export const fetchTradePlan = async (decision_id) => {
  if (!decision_id) throw new Error("decision_id is verplicht");

  const data = await handleApi(
    fetchAuth(`/api/bot/trade-plan/${decision_id}`)
  );

  return {
    entry_plan: ensureArray(data.entry_plan),
    stop_loss: ensureObject(data.stop_loss),
    targets: ensureArray(data.targets),
    risk: ensureObject(data.risk),
  };
};

/* =====================================================
   💾 9B. TRADE PLAN (SAVE)
===================================================== */

export const saveTradePlan = async (decision_id, payload = {}) => {
  if (!decision_id) throw new Error("decision_id is verplicht");

  const safePayload = {
    entry_plan: ensureArray(payload.entry_plan).map((e) => ({
      type: e?.type || "limit",
      price: toNumber(e?.price),
    })),
    stop_loss: {
      price: toNumber(payload.stop_loss?.price),
    },
    targets: ensureArray(payload.targets).map((t, i) => ({
      label: t?.label || `TP${i + 1}`,
      price: toNumber(t?.price),
    })),
    risk: {
      rr: toNumber(payload.risk?.rr),
      risk_eur: toNumber(payload.risk?.risk_eur),
    },
  };

  const data = await handleApi(
    fetchAuth(`/api/bot/trade-plan/${decision_id}`, {
      method: "POST",
      body: JSON.stringify(safePayload),
    })
  );

  return ensureObject(data);
};

/* =====================================================
   🟢 10. MANUAL ORDER (🔥 SAFE)
===================================================== */

export const createManualOrder = async ({
  bot_id,
  symbol = "BTC",
  side,
  quantity,
  price,
}) => {
  if (!bot_id) throw new Error("bot_id is verplicht");
  if (!side) throw new Error("side is verplicht");

  const qty = toNumber(quantity, null);
  const pr = toNumber(price, null);

  if (qty === null || qty <= 0) throw new Error("quantity ongeldig");
  if (pr === null || pr <= 0) throw new Error("price ongeldig");

  return handleApi(
    fetchAuth(`/api/orders/manual`, {
      method: "POST",
      body: JSON.stringify({
        bot_id,
        symbol,
        side,
        quantity: qty,
        price: pr,
      }),
    })
  );
};

/* =====================================================
   📈 11. PORTFOLIO BALANCE HISTORY
===================================================== */

export const fetchPortfolioBalanceHistory = async ({
  bucket = "1h",
  limit = 500,
} = {}) => {
  const query = buildQuery({ bucket, limit });

  const data = await handleApi(
    fetchAuth(`/api/portfolio/balance-history?${query}`)
  );

  return ensureArray(data);
};

/* =====================================================
   📈 12. BOT BALANCE HISTORY
===================================================== */

export const fetchBotBalanceHistory = async ({
  bot_id,
  bucket = "1h",
  limit = 500,
} = {}) => {
  if (!bot_id) throw new Error("bot_id is verplicht");

  const query = buildQuery({ bot_id, bucket, limit });

  const data = await handleApi(
    fetchAuth(`/api/bot/balance-history?${query}`)
  );

  return ensureArray(data);
};
