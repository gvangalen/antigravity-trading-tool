"use client";

import { useModal } from "@/components/modal/ModalProvider";
import { TradingSlider } from "@/components/ui/Slider";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowUpCircle,
  ArrowDownCircle,
  CheckCircle2,
  XCircle,
} from "lucide-react";

/* =========================
   Helpers
========================= */

const num = (v, d = null) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
};

const fmt = (v, digits = 2) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("nl-NL", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
};

const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

/* ===================================================== */

export default function TradePanel({
  price = 66744,
  balanceQuote = 0,
  balanceBase = 0,
  availableQuote = balanceQuote,
  quoteSymbol = "EUR",
  baseSymbol = "BTC",
  strategy = {},
  symbol = "BTC",
  loading = false,
  error = null,
  onSubmit,
}) {

  const { showSnackbar } = useModal();

  const [side, setSide] = useState("buy");
  const [orderType, setOrderType] = useState("limit");
  const [orderPrice, setOrderPrice] = useState(null);

  const [amountPct, setAmountPct] = useState(0);
  const [sizeMode, setSizeMode] = useState("quote");

  const [amountQuoteInput, setAmountQuoteInput] = useState("");
  const [amountBaseInput, setAmountBaseInput] = useState("");

  const [tpPrice, setTpPrice] = useState("");
  const [slPrice, setSlPrice] = useState("");

  const useTpSl = orderType === "tpsl";

  /* =========================
     Strategy defaults
  ========================= */

  const strategyStop = useMemo(() => {
    const s = strategy?.stop_loss;
    if (!s) return null;
    return typeof s === "object" ? num(s.price, null) : num(s, null);
  }, [strategy]);

  const strategyTarget = useMemo(() => {
    const t = strategy?.targets?.[0];
    if (!t) return null;
    return typeof t === "object" ? num(t.price, null) : num(t, null);
  }, [strategy]);

  useEffect(() => {
    if (!useTpSl) return;

    if (slPrice === "" && strategyStop) setSlPrice(String(strategyStop));
    if (tpPrice === "" && strategyTarget) setTpPrice(String(strategyTarget));

  }, [useTpSl, strategyStop, strategyTarget]);

  /* =========================
     Effective price
  ========================= */

  const effectivePrice = useMemo(() => {
    if (orderType === "market") return num(price, null);
    return num(orderPrice, null);
  }, [orderType, price, orderPrice]);

  useEffect(() => {

    const live = num(price, null);
    if (!live) return;

    if (orderType === "market") return;

    const current = num(orderPrice, null);
    if (!current || current <= 0) {
      setOrderPrice(live);
    }

  }, [price, orderType]);

  /* =========================
     Max qty
  ========================= */

  const maxQtyBase = useMemo(() => {

    const p = num(effectivePrice, null);
    if (!p) return 0;

    return side === "buy"
      ? Math.max(0, num(availableQuote, 0) / p)
      : Math.max(0, num(balanceBase, 0));

  }, [side, availableQuote, balanceBase, effectivePrice]);

  const qtyFromPct = useMemo(() => {
    return (maxQtyBase * clamp(amountPct, 0, 100)) / 100;
  }, [maxQtyBase, amountPct]);

  /* =========================
     Quantity base
  ========================= */

  const qtyBase = useMemo(() => {

    const p = num(effectivePrice, null);
    if (!p) return 0;

    if (sizeMode === "base" && amountBaseInput !== "")
      return Math.max(0, num(amountBaseInput, 0));

    if (sizeMode === "quote" && amountQuoteInput !== "")
      return Math.max(0, num(amountQuoteInput, 0) / p);

    return qtyFromPct;

  }, [
    effectivePrice,
    sizeMode,
    amountBaseInput,
    amountQuoteInput,
    qtyFromPct,
  ]);

  const orderValueQuote = useMemo(() => {

    const p = num(effectivePrice, null);
    if (!p) return null;

    return qtyBase * p;

  }, [qtyBase, effectivePrice]);

  /* =========================
     Balance check
  ========================= */

  const hasBalance = useMemo(() => {

    if (side === "buy") return num(availableQuote, 0) > 0;
    return num(balanceBase, 0) > 0;

  }, [side, availableQuote, balanceBase]);

  /* =========================
     Validation
  ========================= */

  const validation = useMemo(() => {

    if (!hasBalance)
      return { ok: false, reason: "Geen beschikbaar saldo" };

    const p = num(effectivePrice, null);
    const q = num(qtyBase, null);

    if (!p) return { ok: false, reason: "Geen geldige prijs" };
    if (!q || q <= 0) return { ok: false, reason: "Aantal is 0" };

    const v = num(orderValueQuote, null);

    if (side === "buy") {
      if (v == null) return { ok: false, reason: "Orderwaarde onbekend" };
      if (v > num(availableQuote, 0))
        return { ok: false, reason: "Onvoldoende saldo" };
    }

    if (side === "sell" && q > num(balanceBase, 0))
      return { ok: false, reason: "Onvoldoende BTC" };

    return { ok: true };

  }, [
    hasBalance,
    effectivePrice,
    qtyBase,
    orderValueQuote,
    balanceBase,
    side,
  ]);

  const canSubmit = validation.ok && !loading;

  /* =========================
     Sync slider -> input
  ========================= */

  useEffect(() => {

    const p = num(effectivePrice, null);
    if (!p || p <= 0) return;

    if (maxQtyBase <= 0) return;

    if (amountPct === 0) return;

    if (sizeMode === "base") {

      if (amountBaseInput === "") {
        const q = qtyFromPct;
        setAmountBaseInput(q > 0 ? String(Number(q.toFixed(6))) : "");
      }

    } else {

      if (amountQuoteInput === "") {
        const v = qtyFromPct * p;
        setAmountQuoteInput(v > 0 ? String(Number(v.toFixed(2))) : "");
      }

    }

  }, [
    qtyFromPct,
    effectivePrice,
    sizeMode,
    maxQtyBase,
    amountPct,
    amountBaseInput,
    amountQuoteInput
  ]);

  /* =========================
     Submit
  ========================= */

  const handleSubmit = async () => {
    if (!canSubmit) return;

    const p = num(effectivePrice, null);
    const q = num(qtyBase, null);
    const v = num(orderValueQuote, null);

    try {
      await onSubmit?.({
        symbol,
        side,
        orderType,
        quantity: q,
        value_eur: v,
        size_mode: sizeMode,
        price: p,
        tp: useTpSl ? num(tpPrice, null) : null,
        sl: useTpSl ? num(slPrice, null) : null,
      });

      // Clear local state only if needed, but usually we wait for confirm
      // For now we don't clear here so the modal can show the details
    } catch (err) {
      console.error("❌ Draft error:", err);
    }
  };

  /* =========================
     UI
  ========================= */

  return (
    <div data-test-version="v4" className="trade-panel-final-v2 animate-fade-in p-8 space-y-8 !relative !top-0 border-4 border-red-600">
      <div className="flex justify-between items-end border-b-2 border-slate-100 pb-6">
        <div>
           <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-1">Status</div>
           <h2 className="text-2xl font-black text-foreground tracking-tighter uppercase leading-none">Trade</h2>
        </div>

        <div className="text-right">
          <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-1">Beschikbaar Saldo</div>
          <div className="flex items-center gap-2 justify-end">
             {side === "buy"
               ? (
                 <div className="flex flex-col items-end">
                    <div className="text-lg font-black text-blue-600 tracking-tighter">{fmt(availableQuote)} <span className="text-[10px] opacity-60 ml-0.5">{quoteSymbol}</span></div>
                    {availableQuote < balanceQuote && (
                      <div className="text-[8px] font-bold text-orange-500 uppercase tracking-tighter">Capped by budget limits</div>
                    )}
                 </div>
               )
               : <div className="text-lg font-black text-emerald-600 tracking-tighter">{fmt(balanceBase,6)} <span className="text-[10px] opacity-60 ml-0.5">{baseSymbol}</span></div>
             }
          </div>
        </div>
      </div>

      {/* BUY SELL TOGGLE */}
      <div className="trade-segment">
        <button
          type="button"
          onClick={() => setSide("buy")}
          className={side === "buy" ? "active-buy" : ""}
        >
          <ArrowUpCircle size={14} className={side === "buy" ? "" : "opacity-40"} />
          Kopen
        </button>

        <button
          type="button"
          onClick={() => setSide("sell")}
          className={side === "sell" ? "active-sell" : ""}
        >
          <ArrowDownCircle size={14} className={side === "sell" ? "" : "opacity-40"} />
          Verkopen
        </button>
      </div>

      {/* PRICE SECTION */}
      <div className="trade-surface">
        <div className="flex items-center justify-between mb-2">
           <label className="text-[10px] font-black text-secondary uppercase tracking-widest">Order Prijs</label>
           <div className="text-[9px] font-bold text-blue-600/60 uppercase">Live: {fmt(price)}</div>
        </div>
        <input
          type="number"
          value={orderType === "market" ? num(price,"") : orderPrice ?? ""}
          disabled={orderType === "market"}
          onChange={(e) => setOrderPrice(Number(e.target.value))}
          className="trade-input"
        />
      </div>

      {/* AMOUNT */}

      {/* AMOUNT SECTION */}
      <div className="trade-surface">
        <div className="flex items-center justify-between mb-2">
           <label className="text-[10px] font-black text-secondary uppercase tracking-widest">Aantal</label>
           <div className="flex gap-2">
              <button onClick={() => setSizeMode("quote")} className={`text-[9px] font-black uppercase tracking-tighter px-2 py-0.5 rounded ${sizeMode === 'quote' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-400'}`}>{quoteSymbol}</button>
              <button onClick={() => setSizeMode("base")} className={`text-[9px] font-black uppercase tracking-tighter px-2 py-0.5 rounded ${sizeMode === 'base' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-400'}`}>{baseSymbol}</button>
           </div>
        </div>

        {sizeMode === "quote"
          ? (
            <input
              type="number"
              value={amountQuoteInput}
              onChange={(e)=>setAmountQuoteInput(e.target.value)}
              className="trade-input"
              placeholder={`Bedrag in ${quoteSymbol}`}
            />
          )
          : (
            <input
              type="number"
              value={amountBaseInput}
              onChange={(e)=>setAmountBaseInput(e.target.value)}
              className="trade-input"
              placeholder={`Grootte in ${baseSymbol}`}
            />
          )
        }

        <div className="py-4">
          <TradingSlider
            value={amountPct}
            steps={[0,25,50,75,100]}
            onChange={(v)=>{
              if (!hasBalance) return;
              setAmountPct(v);
              setAmountQuoteInput("");
              setAmountBaseInput("");
            }}
          />
        </div>

        <div className="flex justify-between items-center bg-white/50 p-3 rounded-xl border border-slate-100/50">
           <div className="flex flex-col">
              <span className="text-[9px] font-black text-secondary uppercase">Verwacht</span>
              <span className="text-xs font-black text-slate-900">{fmt(qtyBase,6)} <span className="opacity-40">{baseSymbol}</span></span>
           </div>
           <div className="text-right">
              <span className="text-[9px] font-black text-secondary uppercase">Max</span>
              <div className="text-xs font-bold text-slate-600">{fmt(maxQtyBase,6)}</div>
           </div>
        </div>

        {!hasBalance && (
          <div className="flex items-center gap-2 p-3 bg-rose-50 text-rose-600 rounded-xl border border-rose-100 text-[10px] font-black uppercase tracking-widest">
            <XCircle size={14}/> {side === "buy" ? `Onvoldoende ${quoteSymbol}` : `Onvoldoende ${baseSymbol}`}
          </div>
        )}
      </div>

      {/* ORDER VALUE SUMMARY */}
      <div className="bg-slate-900 rounded-2xl p-6 flex items-center justify-between border-b-4 border-black">
        <div className="flex items-center gap-3">
           <div className="w-1.5 h-10 bg-blue-500 rounded-full" />
           <div>
              <div className="text-[10px] font-black text-secondary uppercase tracking-widest mb-1">Totale Orderwaarde</div>
              <div className="text-2xl font-black text-white tracking-tighter">
                {orderValueQuote == null ? "—" : `${fmt(orderValueQuote)} ${quoteSymbol}`}
              </div>
           </div>
        </div>
      </div>

      {/* VALIDATION */}

      <div className="text-xs">

        {validation.ok
          ? (
            <span className="trade-badge-ok flex items-center gap-1">
              <CheckCircle2 size={14}/> Klaar om te plaatsen
            </span>
          )
          : (
            <span className="trade-badge-bad flex items-center gap-1">
              <XCircle size={14}/> {validation.reason}
            </span>
          )
        }

      </div>

      {/* ACTION */}

      <button
        type="button"
        onClick={handleSubmit}
        disabled={!canSubmit}
        className={`trade-submit ${side==="buy"?"buy":"sell"}`}
      >
        {loading ? "Plaatsen..." : "Plaats order"}
      </button>

    </div>
  );
}
