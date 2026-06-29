"use client";

import React, { useState, useEffect } from "react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { fetchAdminAiStats } from "@/lib/api/admin";
import { 
  Zap, 
  TrendingUp, 
  DollarSign, 
  Activity, 
  Users, 
  PieChart as PieChartIcon, 
  BarChart3, 
  ShieldCheck,
  AlertTriangle,
  AlertOctagon,
  Cpu,
  ArrowUpRight,
  ArrowDownRight,
  Target,
  Clock,
  PiggyBank,
  BrainCircuit,
  Hash,
  XCircle
} from "lucide-react";
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer, 
  Cell,
  PieChart,
  Pie,
  Legend
} from "recharts";

const MODE_COLORS = {
  "cache_exact": "#10b981",
  "cache_semantic": "#3b82f6",
  "full_ai": "#f59e0b",
  "fallback": "#ef4444"
};

function humanizeKey(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function getModeLabel(mode, copy) {
  return copy?.modeLabels?.[mode] || humanizeKey(mode);
}

function getSourceLabel(source, copy) {
  return copy?.sourceLabels?.[source] || humanizeKey(source);
}

function getSourceHint(source, copy) {
  return copy?.sourceHints?.[source] || copy?.unknownSource || humanizeKey(source);
}

function getEntryPointLabel(entryPoint, copy) {
  const value = String(entryPoint || "unclassified");
  if (value === "unclassified") return copy?.entryPointLabels?.unclassified || humanizeKey(value);
  if (value === "scheduled_job") return copy?.entryPointLabels?.scheduledJob || humanizeKey(value);
  return value
    .replaceAll("assistant_service:", copy?.entryPointPrefixes?.assistantService || "Finn / ")
    .replaceAll("report_service:", copy?.entryPointPrefixes?.reportService || "Reports / ")
    .replaceAll("_task", copy?.entryPointLabels?.taskSuffix || " task")
    .replaceAll("_", " ");
}

function getSeverityLabel(severity, copy) {
  return copy?.severityLabels?.[severity] || humanizeKey(severity);
}

function getAnomalyTypeLabel(type, copy) {
  return copy?.anomalyTypeLabels?.[type] || humanizeKey(type);
}

function getRejectionReasonLabel(reason, copy) {
  return copy?.rejectionReasons?.[reason] || humanizeKey(reason);
}

function getPlanLabel(plan, copy) {
  return copy?.planLabels?.[plan] || humanizeKey(plan);
}

function getFeaturePurposeLabel(purpose, copy) {
  const normalized = String(purpose || "").replace(/^chat_/, "");
  return copy?.featurePurposeLabels?.[normalized] || humanizeKey(normalized);
}

export default function AdminAiDashboard() {
  const { t } = useTranslation();
  const copy = t.adminAiPage;
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    setLoading(true);
    try {
      const data = await fetchAdminAiStats();
      setStats(data);
    } catch (err) {
      console.error("Admin AI-statistieken laden mislukt", err);
      setError(copy.loadError);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return (
    <div className="p-10 flex flex-col items-center justify-center min-h-[60vh]">
      <div className="w-12 h-12 border-4 border-blue-600/20 border-t-blue-600 rounded-full animate-spin mb-4" />
      <p className="text-slate-400 font-bold uppercase tracking-widest text-xs italic">{copy.loading}</p>
    </div>
  );

  if (error) return (
    <div className="p-10 text-center">
      <div className="inline-flex p-4 bg-rose-50 rounded-full text-rose-500 mb-4">
        <ShieldCheck size={32} />
      </div>
      <h1 className="text-2xl font-black text-slate-900 mb-2 italic">{copy.noAccess}</h1>
      <p className="text-slate-500 max-w-md mx-auto">{error}</p>
    </div>
  );

  const { 
    overview, 
    top_users, 
    feature_breakdown, 
    source_breakdown,
    top_entry_points,
    mode_distribution, 
    latency_stats, 
    user_distribution, 
    heavy_user_impact_pct 
  } = stats;

  const rejectionData = Object.entries(overview.rejection_breakdown || {}).map(([reason, count]) => ({
    reason: getRejectionReasonLabel(reason, copy),
    count
  }));

  return (
    <div className="p-8 max-w-[1700px] mx-auto animate-fade-in bg-[#fcfcfd] min-h-screen">
      {/* 🏔️ HEADER */}
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-10">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2.5 bg-slate-900 text-white rounded-xl shadow-2xl shadow-slate-900/30">
              <BrainCircuit size={22} />
            </div>
            <h1 className="text-3xl font-black text-slate-900 tracking-tight italic">
              {copy.titlePrefix} <span className="text-blue-600">{copy.titleAccent}</span>
            </h1>
          </div>
          <p className="text-slate-500 font-medium max-w-2xl text-sm">
            {copy.subtitle}
          </p>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="px-5 py-2.5 bg-blue-600 text-white rounded-2xl flex items-center gap-3 shadow-lg shadow-blue-600/20">
             <div className="w-2.5 h-2.5 rounded-full bg-blue-200 animate-pulse" />
             <span className="text-[11px] font-black uppercase tracking-widest italic">{copy.monitoringActive}</span>
          </div>
          <button 
            onClick={loadStats}
            className="px-6 py-3 bg-white border border-slate-200 rounded-2xl font-black text-[10px] uppercase tracking-widest text-slate-600 hover:border-blue-600 hover:text-blue-600 transition-all shadow-sm active:scale-95"
          >
            {copy.refresh}
          </button>
        </div>
      </div>

      {/* 📊 SUMMARY RIBBON */}
      {/* 📊 SUMMARY RIBBON */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-7 gap-6 mb-10">
        <MetricCard 
          title={copy.metrics.mtdResult} 
          value={`€${overview.total_profit_month_eur.toFixed(2)}`} 
          icon={<DollarSign size={18} className="text-green-500" />}
          trend="positive"
          subtitle={`${((overview.total_profit_month_eur / (overview.total_revenue_month_eur || 1)) * 100).toFixed(1)}% ${copy.metrics.grossMargin}`}
        />
        <MetricCard 
          title={copy.metrics.exactHits} 
          value={overview.exact_hits} 
          icon={<Hash size={18} className="text-emerald-500" />}
          subtitle={copy.metrics.queryHashMatch}
          trend="positive"
        />
        <MetricCard 
          title={copy.metrics.semanticHits} 
          value={overview.semantic_hits} 
          icon={<BrainCircuit size={18} className="text-blue-500" />}
          subtitle={copy.metrics.vectorMatch}
          trend="positive"
        />
        <MetricCard 
          title={copy.metrics.avgLatency} 
          value={`${overview.avg_latency_ms.toFixed(0)} ms`} 
          icon={<Clock size={18} className="text-amber-500" />}
          subtitle={copy.metrics.platformAverage}
          trend={overview.avg_latency_ms < 500 ? "positive" : "negative"}
        />
        <MetricCard 
          title={copy.metrics.avgCostPerCall} 
          value={`€${overview.avg_cost_per_full_request.toFixed(4)}`} 
          icon={<Zap size={18} className="text-violet-500" />}
          subtitle={copy.metrics.nonCachedOnly}
          trend="neutral"
        />
        <MetricCard 
          title={copy.metrics.blockedAiCost} 
          value={`€${overview.blocked_estimated_cost_month_eur.toFixed(2)}`} 
          icon={<AlertOctagon size={18} className="text-rose-500" />}
          subtitle={`${overview.blocked_requests_month} ${copy.metrics.quotaBlockedAttempts}`}
          trend={overview.blocked_requests_month > 0 ? "negative" : "positive"}
        />
        <MetricCard 
          title={copy.metrics.totalSavings} 
          value={`€${overview.total_savings_month_eur.toFixed(2)}`} 
          icon={<PiggyBank size={18} className="text-blue-600" />}
          subtitle={copy.metrics.savedAiCost}
          trend="positive"
          isHighlight
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6 mb-10">
        <MiniSourceCard label={copy.sourceCards.liveUsers} value={`€${overview.live_user_cost_month_eur.toFixed(2)}`} tone="emerald" />
        <MiniSourceCard label={copy.sourceCards.qaSmoke} value={`€${overview.qa_cost_month_eur.toFixed(2)}`} tone="amber" />
        <MiniSourceCard label={copy.sourceCards.backgroundJobs} value={`€${overview.background_cost_month_eur.toFixed(2)}`} tone="violet" />
        <MiniSourceCard label={copy.sourceCards.stagingUsers} value={`€${overview.staging_cost_month_eur.toFixed(2)}`} tone="blue" />
      </div>

      <div className="mb-10 p-5 bg-slate-50 border border-slate-100 rounded-[28px]">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Object.keys(copy.sourceLabels || {}).map((key) => (
            <div key={key} className="bg-white border border-slate-100 rounded-2xl p-4">
              <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 italic">{getSourceLabel(key, copy)}</p>
              <p className="text-sm font-bold text-slate-600 mt-2">{getSourceHint(key, copy)}</p>
            </div>
          ))}
        </div>
      </div>

      {/* ⚠️ REAL-TIME ANOMALY ALERT PANEL */}
      <div className="mb-10 p-8 bg-white border border-slate-100 rounded-[32px] shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-rose-50 text-rose-600 rounded-2xl">
              <AlertTriangle size={20} className="animate-pulse" />
            </div>
            <div>
              <h3 className="text-sm font-black text-slate-900 uppercase tracking-wider italic">
                {copy.anomalies.title}
              </h3>
              <p className="text-slate-400 text-xs">{copy.anomalies.subtitle}</p>
            </div>
          </div>
          <span className="px-4 py-1.5 bg-slate-100 rounded-xl text-[10px] font-black uppercase text-slate-500 tracking-widest">
            {stats.anomalies?.length || 0} {copy.anomalies.detectedIncidents}
          </span>
        </div>

        {stats.anomalies && stats.anomalies.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-h-[400px] overflow-y-auto pr-2">
            {stats.anomalies.map((anomaly, idx) => {
              const severityColors = {
                critical: "bg-rose-50 border-rose-100 text-rose-800",
                high: "bg-orange-50 border-orange-100 text-orange-800",
                warning: "bg-amber-50 border-amber-100 text-amber-800",
              };
              const severityBadge = {
                critical: "bg-rose-200 text-rose-900",
                high: "bg-orange-200 text-orange-900",
                warning: "bg-amber-200 text-amber-900",
              };
              return (
                <div 
                  key={idx} 
                  className={`p-5 border rounded-2xl flex gap-4 transition-all hover:shadow-md ${severityColors[anomaly.severity] || "bg-slate-50 border-slate-100 text-slate-800"}`}
                >
                  <div className="mt-1 flex-shrink-0">
                    {anomaly.type === "budget_breach" && <DollarSign size={20} className="text-rose-600" />}
                    {anomaly.type === "parser_recovery" && <Cpu size={20} className="text-amber-600" />}
                    {anomaly.type === "hallucination_risk" && <BrainCircuit size={20} className="text-orange-600" />}
                    {anomaly.type === "safety_guardrail_trigger" && <ShieldCheck size={20} className="text-blue-600" />}
                  </div>
                  <div className="flex-grow">
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`px-2 py-0.5 rounded text-[8px] font-black uppercase tracking-widest ${severityBadge[anomaly.severity] || "bg-slate-200 text-slate-800"}`}>
                        {getSeverityLabel(anomaly.severity, copy)}
                      </span>
                      <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 italic">
                        {getAnomalyTypeLabel(anomaly.type, copy)}
                      </span>
                    </div>
                    <p className="text-xs font-black leading-relaxed tracking-tight italic">{anomaly.message}</p>
                    {anomaly.details && (
                      <div className="mt-3 bg-white/40 p-2.5 rounded-lg border border-black/5 flex flex-wrap gap-x-4 gap-y-1.5">
                        {anomaly.details.email && (
                          <div className="text-[10px] font-black text-slate-500 uppercase tracking-wider">
                            {copy.anomalies.email}: <span className="text-slate-800 lowercase font-bold">{anomaly.details.email}</span>
                          </div>
                        )}
                        {anomaly.details.trace_id && (
                          <div className="text-[10px] font-black text-slate-500 uppercase tracking-wider">
                            {copy.anomalies.trace}: <span className="text-slate-800 font-mono text-[9px]">{anomaly.details.trace_id.slice(0, 16)}...</span>
                          </div>
                        )}
                        {anomaly.details.confidence_score !== undefined && (
                          <div className="text-[10px] font-black text-slate-500 uppercase tracking-wider">
                            {copy.anomalies.confidence}: <span className="text-slate-800 font-bold">{anomaly.details.confidence_score}%</span>
                          </div>
                        )}
                        {anomaly.details.response_time_ms && (
                          <div className="text-[10px] font-black text-slate-500 uppercase tracking-wider">
                            {copy.anomalies.latency}: <span className="text-slate-800 font-bold">{anomaly.details.response_time_ms}ms</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="p-10 border border-dashed border-slate-200 rounded-2xl flex flex-col items-center justify-center text-slate-400">
            <ShieldCheck size={48} className="text-emerald-500 stroke-1 mb-3 animate-pulse" />
            <p className="text-xs font-black uppercase tracking-widest text-emerald-600">{copy.anomalies.normalStatus}</p>
            <p className="text-[10px] font-semibold text-slate-400 mt-1 uppercase tracking-widest">{copy.anomalies.noActiveAnomalies}</p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-8 mb-10">
        {/* 📉 MODE PERFORMANCE MIX */}
        <div className="p-8 bg-white border border-slate-100 rounded-[32px] shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-[11px] font-black text-slate-900 uppercase tracking-[0.2em] flex items-center gap-2">
              <PieChartIcon size={14} className="text-blue-600" />
              {copy.sections.gatewaySelectionMix}
            </h3>
          </div>
          <div className="h-[280px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={mode_distribution}
                  cx="50%"
                  cy="50%"
                  innerRadius={70}
                  outerRadius={100}
                  paddingAngle={8}
                  dataKey="count"
                  nameKey="mode"
                >
                  {mode_distribution.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={MODE_COLORS[entry.mode] || '#cbd5e1'} stroke="none" />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ borderRadius: '24px', border: 'none', boxShadow: '0 25px 50px -12px rgb(0 0 0 / 0.15)' }}
                  formatter={(val, name) => [val, getModeLabel(name, copy)]}
                />
                <Legend verticalAlign="bottom" height={36} iconType="circle" formatter={(v) => getModeLabel(v, copy)} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* ⚡ LATENCY HUD */}
        <div className="p-8 bg-white border border-slate-100 rounded-[32px] shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-[11px] font-black text-slate-900 uppercase tracking-[0.2em] flex items-center gap-2">
              <Clock size={14} className="text-amber-500" />
              {copy.sections.latencyResponseMap}
            </h3>
          </div>
          <div className="space-y-6">
            {latency_stats.sort((a,b) => b.avg_ms - a.avg_ms).map((item, idx) => (
              <div key={idx}>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest italic">{getModeLabel(item.mode, copy)}</span>
                  <span className="text-[11px] font-black text-slate-900">{item.avg_ms.toFixed(0)}ms</span>
                </div>
                <div className="h-2 w-full bg-slate-50 rounded-full overflow-hidden">
                  <div 
                    className="h-full rounded-full bg-gradient-to-r"
                    style={{ 
                      width: `${Math.min(100, (item.avg_ms / 3000) * 100)}%`,
                      backgroundColor: MODE_COLORS[item.mode] || '#cbd5e1'
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 🔍 CACHE REJECTION ANALYTICS */}
        <div className="p-8 bg-white border border-slate-100 rounded-[32px] shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-[11px] font-black text-slate-900 uppercase tracking-[0.2em] flex items-center gap-2">
              <XCircle size={14} className="text-rose-500" />
              {copy.sections.rejectionAnalysis}
            </h3>
          </div>
          {rejectionData.length > 0 ? (
            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={rejectionData}>
                  <XAxis dataKey="reason" axisLine={false} tickLine={false} fontSize={10} fontWeight="black" />
                  <YAxis hide />
                  <Tooltip 
                     cursor={{ fill: '#f8fafc' }}
                     contentStyle={{ borderRadius: '24px', border: 'none', boxShadow: '0 25px 50px -12px rgb(0 0 0 / 0.15)' }}
                  />
                  <Bar dataKey="count" fill="#e2e8f0" radius={[8, 8, 8, 8]} barSize={40}>
                    {rejectionData.map((entry, index) => (
                      <Cell key={index} fill={entry.reason === 'context mismatch' ? '#ef4444' : '#64748b'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
             <div className="h-[280px] flex flex-col items-center justify-center text-slate-300">
               <ShieldCheck size={48} strokeWidth={1} />
               <p className="text-[10px] font-black uppercase tracking-widest mt-4 italic">{copy.sections.noRejectionsToday}</p>
             </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 mb-10">
        <div className="p-8 bg-white border border-slate-100 rounded-[32px] shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-[11px] font-black text-slate-900 uppercase tracking-[0.2em] flex items-center gap-2">
              <Activity size={14} className="text-emerald-600" />
              {copy.sections.spendBySource}
            </h3>
          </div>
          <div className="space-y-4">
            {source_breakdown.map((item, idx) => (
              <div key={`${item.source}-${idx}`} className="border border-slate-100 rounded-2xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-black text-slate-900 italic tracking-tight">{getSourceLabel(item.source, copy)}</p>
                  <span className="text-sm font-black text-slate-900">€{item.total_cost.toFixed(2)}</span>
                </div>
                <p className="text-[11px] text-slate-500 font-medium mb-3">{getSourceHint(item.source, copy)}</p>
                <div className="flex items-center justify-between text-[10px] font-black uppercase tracking-widest text-slate-400">
                  <span>{item.total_requests} {copy.requests}</span>
                  <span>{item.unique_users} {copy.users}</span>
                  <span>{item.percentage.toFixed(1)}%</span>
                </div>
                <div className="flex items-center justify-between text-[10px] font-black uppercase tracking-widest text-rose-400 mt-2">
                  <span>{item.blocked_requests} {copy.blocked}</span>
                  <span>€{item.blocked_estimated_cost.toFixed(2)} {copy.estimate}</span>
                </div>
                <div className="h-2 w-full bg-slate-50 rounded-full overflow-hidden mt-3">
                  <div
                    className="h-full bg-slate-900 rounded-full"
                    style={{ width: `${Math.min(100, item.percentage)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="p-8 bg-white border border-slate-100 rounded-[32px] shadow-sm overflow-hidden">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-[11px] font-black text-slate-900 uppercase tracking-[0.2em] flex items-center gap-2">
              <Target size={14} className="text-violet-600" />
              {copy.sections.costliestEntryPoints}
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-slate-50">
                  <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.entryPoint}</th>
                  <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.source}</th>
                  <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.mtdCost}</th>
                  <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.blocked}</th>
                  <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.avgPerCall}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {top_entry_points.map((item, idx) => (
                  <tr key={`${item.entry_point}-${idx}`} className="group hover:bg-slate-50/50 transition-colors">
                    <td className="py-5 pr-4">
                      <p className="text-sm font-black text-slate-900 italic tracking-tight">{getEntryPointLabel(item.entry_point, copy)}</p>
                      <p className="text-[10px] font-medium text-slate-500 mt-1">{getSourceHint(item.source, copy)}</p>
                      <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">{item.total_requests} {copy.calls}</p>
                    </td>
                    <td className="py-5">
                      <span className="px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest border bg-slate-50 text-slate-600 border-slate-100">
                        {getSourceLabel(item.source, copy)}
                      </span>
                    </td>
                    <td className="py-5">
                      <span className="text-sm font-black text-slate-900">€{item.total_cost.toFixed(2)}</span>
                    </td>
                    <td className="py-5">
                      <div className="text-[10px] font-black uppercase tracking-widest text-rose-500">
                        <div>{item.blocked_requests} {copy.hits}</div>
                        <div>€{item.blocked_estimated_cost.toFixed(2)} {copy.estimate}</div>
                      </div>
                    </td>
                    <td className="py-5">
                      <span className="px-2.5 py-1.5 bg-slate-50 text-slate-700 font-mono text-xs font-bold rounded-xl border border-slate-100/50">
                        €{item.avg_cost.toFixed(6)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* 💰 FEATURE COST EFFICIENCY GRID */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
         <div className="p-8 bg-white border border-slate-100 rounded-[32px] shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-[11px] font-black text-slate-900 uppercase tracking-[0.2em] flex items-center gap-2">
              <BarChart3 size={14} className="text-slate-900" />
              {copy.sections.profitabilityTierDistribution}
            </h3>
          </div>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={user_distribution}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="bucket" axisLine={false} tickLine={false} fontSize={10} fontWeight="black" />
                <YAxis axisLine={false} tickLine={false} fontSize={10} fontWeight="bold" />
                <Tooltip 
                   contentStyle={{ borderRadius: '24px', border: 'none', boxShadow: '0 25px 50px -12px rgb(0 0 0 / 0.15)' }}
                />
                <Bar dataKey="count" fill="#1e293b" radius={[12, 12, 12, 12]} barSize={60} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* TOP USERS PROFITABILITY */}
        <div className="p-8 bg-white border border-slate-100 rounded-[32px] shadow-sm overflow-hidden">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-[11px] font-black text-slate-900 uppercase tracking-[0.2em] flex items-center gap-2">
              <Users size={14} className="text-blue-600" />
              {copy.sections.unitEconomicsPerUser}
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-slate-50">
                  <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.partner}</th>
                  <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.netMargin}</th>
                  <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.status}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {top_users.map((user, idx) => (
                  <tr key={idx} className="group hover:bg-slate-50/50 transition-colors">
                    <td className="py-5 pr-4">
                       <p className="text-sm font-black text-slate-900 italic tracking-tight truncate max-w-[180px]" title={user.email}>{user.email}</p>
                       <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">{getPlanLabel(user.plan, copy)} {copy.assetTier}</p>
                    </td>
                    <td className="py-5">
                      <div className={`text-sm font-black flex items-center gap-1 ${user.profit_month_eur > 0 ? 'text-green-600' : 'text-rose-600'}`}>
                        €{user.profit_month_eur.toFixed(2)}
                        {user.profit_month_eur > 50 && <ArrowUpRight size={14} strokeWidth={3} />}
                      </div>
                      <div className="flex flex-col">
                        <p className="text-[9px] font-black uppercase text-slate-300 italic">{copy.monthShort}: €{user.usage_month_eur.toFixed(2)}</p>
                        <p className="text-[9px] font-black uppercase text-blue-400 italic">{copy.today}: €{user.usage_today_eur.toFixed(2)}</p>
                        <p className="text-[9px] font-black uppercase text-violet-400 italic">{copy.background}: €{user.background_usage_month_eur.toFixed(2)}</p>
                        <p className="text-[9px] font-black uppercase text-emerald-500 italic">{copy.interactive}: €{user.interactive_usage_month_eur.toFixed(2)}</p>
                        <p className="text-[9px] font-black uppercase text-rose-500 italic">{copy.blocked}: {user.blocked_requests_month} / €{user.blocked_estimated_cost_month_eur.toFixed(2)} {copy.estimate}</p>
                      </div>
                    </td>
                    <td className="py-5">
                      {user.requests_today >= user.requests_limit ? (
                        <div className="flex items-center gap-2 px-3 py-1.5 bg-rose-50 text-rose-600 rounded-xl w-fit">
                          <AlertTriangle size={12} strokeWidth={3} />
                          <span className="text-[9px] font-black uppercase tracking-widest italic">{copy.overQuota}</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 text-blue-600 rounded-xl w-fit">
                          <Target size={12} strokeWidth={3} />
                          <span className="text-[9px] font-black uppercase tracking-widest italic">{copy.optimized}</span>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* 🚀 FEATURE ECONOMICS TABLE */}
      <div className="mt-10 p-8 bg-white border border-slate-100 rounded-[32px] shadow-sm overflow-hidden">
        <div className="flex items-center justify-between mb-8">
          <h3 className="text-[11px] font-black text-slate-900 uppercase tracking-[0.2em] flex items-center gap-2">
            <Zap size={14} className="text-violet-500" />
            {copy.sections.featureEconomics}
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-50">
                <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.featureType}</th>
                <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.usageVolume}</th>
                <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.totalCostMtd}</th>
                <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.avgCostPerCall}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {feature_breakdown.map((item, idx) => (
                <tr key={idx} className="group hover:bg-slate-50/50 transition-colors">
                  <td className="py-5 pr-4">
                    <p className="text-sm font-black text-slate-900 italic tracking-tight uppercase">{getFeaturePurposeLabel(item.purpose, copy)}</p>
                    <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">{copy.activeOrchestrationModel}</p>
                  </td>
                  <td className="py-5">
                    <div className="text-sm font-black text-slate-900 flex items-center gap-2">
                      {item.total_requests}
                      <span className="text-[10px] font-bold text-slate-400">{copy.calls}</span>
                    </div>
                  </td>
                  <td className="py-5">
                    <span className="text-sm font-black text-slate-900">€{item.total_cost.toFixed(4)}</span>
                  </td>
                  <td className="py-5">
                    <span className="px-2.5 py-1.5 bg-slate-50 text-slate-700 font-mono text-xs font-bold rounded-xl border border-slate-100/50">
                      €{item.avg_cost.toFixed(6)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ title, value, icon, subtitle, trend, isHighlight }) {
  return (
    <div className={`p-5 lg:p-6 border rounded-[32px] transition-all relative overflow-hidden group ${
      isHighlight 
        ? 'bg-blue-600 border-blue-600 text-white shadow-xl shadow-blue-600/30' 
        : 'bg-white border-slate-100 shadow-sm hover:shadow-xl hover:shadow-slate-200/50 text-slate-900'
    }`}>
      <div className="flex items-center justify-between mb-8">
        <p className={`text-[10px] font-black uppercase tracking-[0.2em] italic ${
          isHighlight ? 'text-blue-100' : 'text-slate-400'
        }`}>{title}</p>
        <div className={`p-2.5 rounded-2xl shadow-sm transition-all ${
          isHighlight ? 'bg-blue-500 text-white' : 'bg-slate-50 text-slate-900 group-hover:bg-slate-900 group-hover:text-white'
        }`}>
          {icon}
        </div>
      </div>
      <div className="flex items-end justify-between">
        <div className="relative z-10 w-full overflow-hidden">
          <h2 className={`text-xl lg:text-2xl xl:text-3xl font-black tracking-tight italic truncate ${isHighlight ? 'text-white' : 'text-slate-900'}`} title={value}>{value}</h2>
          <p className={`text-[10px] font-bold mt-2 uppercase tracking-widest ${
            isHighlight ? 'text-blue-200' : 'text-slate-400'
          }`}>{subtitle}</p>
        </div>
        {trend && !isHighlight && (
          <div className={`p-2 rounded-xl scale-110 ${
            trend === 'positive' ? 'bg-green-50 text-green-600' : 'bg-rose-50 text-rose-600'
          }`}>
            {trend === 'positive' ? <ArrowUpRight size={18} strokeWidth={3} /> : <ArrowDownRight size={18} strokeWidth={3} />}
          </div>
        )}
      </div>
      
      {/* Decorative Gradient for highlight */}
      {isHighlight && (
        <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 blur-[60px] rounded-full -translate-y-1/2 translate-x-1/2" />
      )}
    </div>
  );
}

function MiniSourceCard({ label, value, tone = "slate" }) {
  const toneClasses = {
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-100",
    amber: "bg-amber-50 text-amber-700 border-amber-100",
    violet: "bg-violet-50 text-violet-700 border-violet-100",
    blue: "bg-blue-50 text-blue-700 border-blue-100",
    slate: "bg-slate-50 text-slate-700 border-slate-100",
  };

  return (
    <div className={`p-5 border rounded-[24px] ${toneClasses[tone] || toneClasses.slate}`}>
      <p className="text-[10px] font-black uppercase tracking-[0.2em] italic opacity-80">{label}</p>
      <p className="text-2xl font-black tracking-tight mt-3">{value}</p>
    </div>
  );
}
