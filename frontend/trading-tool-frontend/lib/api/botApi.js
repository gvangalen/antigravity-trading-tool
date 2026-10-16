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
  const data = await handleApi(fetchAuth(`/api/bot/configs`, { forceFresh: true }));
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
    fetchAuth(`/api/bot/paper/reassess`, {
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

export const fetchAllBotTrades = async (limit = 50, offset = 0) => {
  const data = await handleApi(fetchAuth(`/api/bot/trades/all?${buildQuery({ limit, offset })}`, { forceFresh: true }));
  return {
    items: ensureArray(data?.items),
    has_more: data?.has_more === true,
    next_offset: data?.next_offset ?? null,
  };
};

export const fetchFinnTradeReviews = async (limit = 50, offset = 0) => {
  const query = buildQuery({ limit, offset });
  return handleApi(fetchAuth(`/api/bot/trade-reviews?${query}`));
};

export const fetchFinnTradeReview = async (reviewId) => {
  if (!reviewId) throw new Error("reviewId is verplicht");
  return handleApi(fetchAuth(`/api/bot/trade-reviews/${encodeURIComponent(reviewId)}`));
};

export const saveFinnTradeReviewNote = async (reviewId, note) => {
  if (!reviewId) throw new Error("reviewId is verplicht");
  return handleApi(fetchAuth(`/api/bot/trade-reviews/${encodeURIComponent(reviewId)}/note`, {
    method: "PUT",
    body: JSON.stringify({ note }),
  }));
};

export const fetchFinnTradeChart = (reviewId) => handleApi(fetchAuth(`/api/bot/trade-reviews/${encodeURIComponent(reviewId)}/chart`));
export const analyzeFinnTradeReview = (reviewId) => handleApi(fetchAuth(`/api/bot/trade-reviews/${encodeURIComponent(reviewId)}/analyze`, { method: "POST" }));
export const fetchFinnTradeMessages = (reviewId) => handleApi(fetchAuth(`/api/bot/trade-reviews/${encodeURIComponent(reviewId)}/messages`));
export const askFinnTradeReview = (reviewId, question) => handleApi(fetchAuth(`/api/bot/trade-reviews/${encodeURIComponent(reviewId)}/messages`, { method: "POST", body: JSON.stringify({ question }) }));
export const uploadFinnTradeScreenshot = (reviewId, file) => handleApi(fetchAuth(`/api/bot/trade-reviews/${encodeURIComponent(reviewId)}/screenshot`, { method: "PUT", headers: { "Content-Type": "image/png" }, body: file }));
export const deleteFinnTradeScreenshot = (reviewId) => handleApi(fetchAuth(`/api/bot/trade-reviews/${encodeURIComponent(reviewId)}/screenshot`, { method: "DELETE" }));
export const fetchFinnTradeScreenshot = async (reviewId) => {
  const response = await fetchAuth(`/api/bot/trade-reviews/${encodeURIComponent(reviewId)}/screenshot`, { forceFresh: true });
  if (!(response instanceof Response)) throw new Error("Screenshot response is ongeldig");
  return response.blob();
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

export const previewManualOrder = async ({
  bot_id,
  symbol = "BTC",
  side,
  quantity,
  price,
  price_currency,
  value_eur,
}) => {
  if (!bot_id) throw new Error("bot_id is verplicht");
  if (!side) throw new Error("side is verplicht");

  const preview = await fetchAuth(`/api/orders/preview`, {
    method: "POST",
    body: JSON.stringify({
      bot_id,
      symbol,
      side,
      quantity: toNumber(quantity, 0),
      price: toNumber(price, 0),
      price_currency,
      value_eur: toNumber(value_eur, 0),
    }),
  });
  // A setup-match refusal is an expected, structured preview. Keep its
  // explanation and order identity so the modal can show why confirmation is
  // disabled. Other API failures still use the normal error path.
  if (preview?.blocked === true) {
    return preview;
  }
  if (preview?.ok === false) throw new Error(preview.error || "API error");
  return preview;
};

export const fetchPaperPriceEur = (botId) =>
  handleApi(fetchAuth(`/api/bot/${encodeURIComponent(botId)}/paper-price-eur`, { method: "GET" }));

export const createManualOrder = async ({
  bot_id,
  symbol = "BTC",
  side,
  quantity,
  price,
  price_currency,
  paper_preview_token,
  value_eur,
  idempotency_key,
  risk_acknowledged = false,
  live_preflight_token,
  live_preflight_action_id,
  setup_block_acknowledged = false,
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
        price_currency,
        paper_preview_token,
        value_eur: toNumber(value_eur, undefined),
        idempotency_key,
        risk_acknowledged,
        live_preflight_token,
        live_preflight_action_id,
        setup_block_acknowledged,
      }),
    })
  );
};

export const preflightManualOrder = async ({
  bot_id,
  symbol = "BTC",
  side,
  quantity,
  price,
  value_eur,
  idempotency_key,
  risk_acknowledged = true,
  live_preflight_token,
  live_preflight_action_id,
  setup_block_acknowledged = false,
}) => {
  if (!bot_id) throw new Error("bot_id is verplicht");
  if (!side) throw new Error("side is verplicht");

  const qty = toNumber(quantity, null);
  const pr = toNumber(price, null);

  if (qty === null || qty <= 0) throw new Error("quantity ongeldig");
  if (pr === null || pr <= 0) throw new Error("price ongeldig");

  try {
    return await handleApi(
      fetchAuth(`/api/orders/manual/preflight`, {
        method: "POST",
        body: JSON.stringify({
          bot_id,
          symbol,
          side,
          quantity: qty,
          price: pr,
          value_eur: toNumber(value_eur, undefined),
          idempotency_key,
          risk_acknowledged,
          live_preflight_token,
          live_preflight_action_id,
          setup_block_acknowledged,
        }),
      })
    );
  } catch (err) {
    let parsed = null;
    try {
      parsed = JSON.parse(err?.body || "{}");
    } catch {
      parsed = null;
    }
    const detail = parsed?.detail && typeof parsed.detail === "object"
      ? parsed.detail
      : { message: parsed?.detail || err?.message || "Live preflight mislukt" };
    return {
      ok: false,
      blocked: true,
      status: err?.status,
      ...detail,
    };
  }
};

/* =====================================================
   📈 11. PORTFOLIO BALANCE HISTORY
===================================================== */

export const fetchPortfolioBalanceHistory = async ({
  bucket = "1h",
  limit = 500,
  is_live = null,
} = {}) => {
  const query = buildQuery({ bucket, limit, is_live });

  const data = await handleApi(
    fetchAuth(`/api/portfolio/balance-history?${query}`)
  );

  return ensureArray(data);
};

export const fetchPortfolioSummary = async (environment = null) => {
  const query = buildQuery({ environment });
  return handleApi(fetchAuth(`/api/portfolio/summary${query ? `?${query}` : ""}`, { forceFresh: true }));
};

export const saveLiveCashAllocations = async (allocations) => handleApi(fetchAuth(
  "/api/portfolio/live-cash-allocations",
  { method: "PUT", body: JSON.stringify({ allocations }) },
));

export const fetchVerifiedPortfolioHistory = async (environment = "paper") => {
  const query = buildQuery({ environment, bucket: "1h", limit: 720 });
  return handleApi(fetchAuth(`/api/portfolio/value-history?${query}`, { forceFresh: true }));
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

/* =====================================================
   🔁 13. BOT BACKTEST
===================================================== */

export const runBotBacktest = async (bot_id, scenario = "default") => {
  if (!bot_id) throw new Error("bot_id is verplicht");

  return handleApi(
    fetchAuth(`/api/backtest/bot/${bot_id}?scenario=${scenario}`, {
      method: "POST",
    })
  );
};
