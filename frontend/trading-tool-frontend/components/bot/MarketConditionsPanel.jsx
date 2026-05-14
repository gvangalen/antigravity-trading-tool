"use client";

import {
  BarChart3,
  AlertTriangle,
  Target,
  Zap,
  TrendingUp,
  Layers,
  Sparkles
} from "lucide-react";

/* =====================================================
   HELPERS
===================================================== */

const clamp = (v, min = 0, max = 100) => {
  const n = Number(v);
  if (isNaN(n)) return min;
  return Math.min(max, Math.max(min, n));
};

const safeMultiplier = (v) => {
  const n = Number(v);
  if (isNaN(n) || n <= 0) return 1;
  return n;
};

/* =====================================================
   LABELS
===================================================== */

const getPressureLabel = (v) => {
  if (v < 30) return "Calm market";
  if (v < 50) return "Neutral pressure";
  if (v < 70) return "Moderate pressure";
  if (v < 85) return "High pressure";
  return "Extreme pressure";
};

const getTransitionRiskLabel = (v) => {
  if (v < 30) return "Stable regime";
  if (v < 50) return "Minor shifts possible";
  if (v < 70) return "Regime pressure building";
  if (v < 85) return "High transition risk";
  return "Regime change risk";
};

const getSetupQualityLabel = (v) => {
  if (v < 30) return "Weak setups";
  if (v < 50) return "Mixed setups";
  if (v < 70) return "Decent setups";
  if (v < 85) return "High quality";
  return "Very strong setups";
};

const getVolatilityLabel = (v) => {
  if (v < 25) return "Very calm";
  if (v < 50) return "Normal";
  if (v < 70) return "Volatile";
  if (v < 85) return "High volatility";
  return "Extreme volatility";
};

const getTrendStrengthLabel = (v) => {
  if (v < 30) return "Weak trend";
  if (v < 50) return "Sideways";
  if (v < 70) return "Trending";
  if (v < 85) return "Strong trend";
  return "Very strong trend";
};

const getExposureLabel = (v) => {
  const value = v / 100; // Convert back to 0-2 range
  if (value < 0.7) return "Defensive";
  if (value < 0.95) return "Reduced size";
  if (value <= 1.05) return "Normal size";
  if (value <= 1.25) return "Increased size";
  return "Aggressive size";
};

const getExposureColor = (v) => {
  const value = v / 100; // Convert back to 0-2 range
  if (value < 0.7) return "bg-red-500";
  if (value < 0.95) return "bg-orange-500";
  if (value <= 1.05) return "bg-gray-500";
  if (value <= 1.25) return "bg-blue-500";
  return "bg-purple-500";
};

/* =====================================================
   BAR COMPONENT
===================================================== */

function Bar({ icon, label, value, color, getLabel, onClick }) {

  const blocks = 10;
  const safeValue = clamp(value);
  const filled = Math.round((safeValue / 100) * blocks);
  const status = getLabel(safeValue);

  return (
    <div 
      className="flex items-center gap-6 text-[10px] w-full group py-2.5 transition-all hover:bg-slate-100/50 dark:hover:bg-slate-800/50 px-3 rounded-xl"
    >

      {/* icon */}
      <span className="w-6 flex items-center justify-center text-secondary group-hover:text-blue-600 transition-colors">
        {icon}
      </span>

      {/* label */}
      <span className="w-48 font-black uppercase tracking-widest text-muted group-hover:text-slate-900 dark:group-hover:text-slate-100 transition-colors leading-none">
        {label}
      </span>

      {/* bar container (THE 'BALKJES') - SOLID & FIXED VISIBILITY */}
      <div className="flex-1 min-w-[120px] flex gap-1.5 h-3 items-center">
        {[...Array(blocks)].map((_, i) => (
          <div
            key={i}
            className={`flex-1 h-full rounded-[1px] transition-all duration-300 ${
              i < filled
                ? `${color} opacity-100 shadow-sm shadow-blue-900/10`
                : "bg-slate-200/50 dark:bg-slate-800"
            }`}
          />
        ))}
      </div>

      {/* score */}
      <div className="w-24 text-right font-mono font-black tabular-nums">
        <span className="text-foreground text-sm">{safeValue.toString().padStart(2, '0')}</span>
        <span className="text-slate-300 dark:text-slate-600 text-[10px] ml-1.5 opacity-40">/ 100</span>
      </div>

      {/* status badge */}
      <div className="w-64 flex items-center justify-end gap-2">
        <button 
          onClick={(e) => {
            e.stopPropagation();
            if (onClick) onClick();
          }}
          className="opacity-0 group-hover:opacity-100 flex items-center gap-1 px-2.5 py-1 rounded-lg bg-blue-50 dark:bg-blue-900/40 text-[9px] font-black uppercase tracking-wider text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800 transition-all hover:scale-105 active:scale-95 shadow-sm"
        >
          <Sparkles size={10} /> Ask FINN
        </button>
        <span className="px-3 py-1 rounded-lg bg-card dark:bg-slate-800 border border-slate-100 dark:border-slate-700 text-[9px] font-black uppercase tracking-widest text-muted shadow-sm group-hover:border-blue-600/30 group-hover:text-blue-600 transition-all">
          {status}
        </span>
      </div>

    </div>
  );
}

/* =====================================================
   MAIN COMPONENT
===================================================== */

export default function MarketConditionsInline({
  health = 50,
  transitionRisk = 20,
  pressure = 50,
  volatility = 50,
  trendStrength = 50,
  multiplier = 1,
  symbol = "BTC",
}) {

  const safeHealth = clamp(health);
  const safeRisk = clamp(transitionRisk);
  const safePressure = clamp(pressure);
  const safeVolatility = clamp(volatility);
  const safeTrend = clamp(trendStrength);
  const safeMulti = safeMultiplier(multiplier);

  const exposureLabel = getExposureLabel(safeMulti * 100);
  const exposureColor = getExposureColor(safeMulti * 100);

  /* multiplier → score schaal */
  const exposureScore = clamp(safeMulti * 100);

  const triggerAI = (metric) => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent('finn-action-trigger', {
        detail: { metric, symbol, timeframe: '1W' }
      }));
    }
  };

  return (

    <div className="flex flex-col gap-2 w-full">

      {/* MARKET PRESSURE */}

      <Bar
        icon={<BarChart3 size={16} />}
        label="Market pressure"
        value={safePressure}
        color="bg-blue-500"
        getLabel={getPressureLabel}
        onClick={() => triggerAI('market_pressure')}
      />

      {/* TRANSITION RISK */}

      <Bar
        icon={<AlertTriangle size={16} />}
        label="Transition risk"
        value={safeRisk}
        color="bg-orange-500"
        getLabel={getTransitionRiskLabel}
        onClick={() => triggerAI('transition_risk')}
      />

      {/* SETUP QUALITY */}

      <Bar
        icon={<Target size={16} />}
        label="Setup quality"
        value={safeHealth}
        color="bg-emerald-500"
        getLabel={getSetupQualityLabel}
        onClick={() => triggerAI('setup_quality')}
      />

      {/* MARKET VOLATILITY */}

      <Bar
        icon={<Zap size={16} />}
        label="Market volatility"
        value={safeVolatility}
        color="bg-purple-500"
        getLabel={getVolatilityLabel}
        onClick={() => triggerAI('market_volatility')}
      />

      {/* TREND STRENGTH */}

      <Bar
        icon={<TrendingUp size={16} />}
        label="Trend strength"
        value={safeTrend}
        color="bg-indigo-500"
        getLabel={getTrendStrengthLabel}
        onClick={() => triggerAI('trend_strength')}
      />

      {/* POSITION SIZE (UPDATED) */}

      <Bar
        icon={<Layers size={16} />}
        label="Position size"
        value={exposureScore}
        color={exposureColor}
        getLabel={() => exposureLabel}
        onClick={() => triggerAI('position_size')}
      />

    </div>
  );
}
