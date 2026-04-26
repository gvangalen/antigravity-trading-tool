"use client";

import React, { useState, useEffect } from "react";
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

const MODE_LABELS = {
  "cache_exact": "Exact Hit",
  "cache_semantic": "Semantic Hit",
  "full_ai": "Full AI Call",
  "fallback": "Platform Fallback"
};

const MODE_COLORS = {
  "cache_exact": "#10b981",
  "cache_semantic": "#3b82f6",
  "full_ai": "#f59e0b",
  "fallback": "#ef4444"
};

export default function AdminAiDashboard() {
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
      console.error("Failed to load admin AI stats", err);
      setError("Je hebt geen admin rechten of de API is offline.");
    } finally {
      setLoading(false);
    }
  };

  if (loading) return (
    <div className="p-10 flex flex-col items-center justify-center min-h-[60vh]">
      <div className="w-12 h-12 border-4 border-blue-600/20 border-t-blue-600 rounded-full animate-spin mb-4" />
      <p className="text-slate-400 font-bold uppercase tracking-widest text-xs italic">Syncing Vector Intelligence...</p>
    </div>
  );

  if (error) return (
    <div className="p-10 text-center">
      <div className="inline-flex p-4 bg-rose-50 rounded-full text-rose-500 mb-4">
        <ShieldCheck size={32} />
      </div>
      <h1 className="text-2xl font-black text-slate-900 mb-2 italic">Access Denied</h1>
      <p className="text-slate-500 max-w-md mx-auto">{error}</p>
    </div>
  );

  const { 
    overview, 
    top_users, 
    feature_breakdown, 
    mode_distribution, 
    latency_stats, 
    user_distribution, 
    heavy_user_impact_pct 
  } = stats;

  const rejectionData = Object.entries(overview.rejection_breakdown || {}).map(([reason, count]) => ({
    reason: reason.replace('_', ' '),
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
              AI Gateway <span className="text-blue-600">Phase 3 Infrastructure</span>
            </h1>
          </div>
          <p className="text-slate-500 font-medium max-w-2xl text-sm">
            Semantic Intelligence enabled. Using FAISS Vector Engine with text-embedding-3-small (1536 dims).
          </p>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="px-5 py-2.5 bg-blue-600 text-white rounded-2xl flex items-center gap-3 shadow-lg shadow-blue-600/20">
             <div className="w-2.5 h-2.5 rounded-full bg-blue-200 animate-pulse" />
             <span className="text-[11px] font-black uppercase tracking-widest italic">Semantic Engine Online</span>
          </div>
          <button 
            onClick={loadStats}
            className="px-6 py-3 bg-white border border-slate-200 rounded-2xl font-black text-[10px] uppercase tracking-widest text-slate-600 hover:border-blue-600 hover:text-blue-600 transition-all shadow-sm active:scale-95"
          >
            Refresh Intel
          </button>
        </div>
      </div>

      {/* 📊 SUMMARY RIBBON */}
      {/* 📊 SUMMARY RIBBON */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6 gap-6 mb-10">
        <MetricCard 
          title="MTD Profit" 
          value={`€${overview.total_profit_month_eur.toFixed(2)}`} 
          icon={<DollarSign size={18} className="text-green-500" />}
          trend="positive"
          subtitle={`${((overview.total_profit_month_eur / (overview.total_revenue_month_eur || 1)) * 100).toFixed(1)}% Gross Margin`}
        />
        <MetricCard 
          title="Exact Hits" 
          value={overview.exact_hits} 
          icon={<Hash size={18} className="text-emerald-500" />}
          subtitle="Query Hash match"
          trend="positive"
        />
        <MetricCard 
          title="Semantic Hits" 
          value={overview.semantic_hits} 
          icon={<BrainCircuit size={18} className="text-blue-500" />}
          subtitle="Vector Similarity match"
          trend="positive"
        />
        <MetricCard 
          title="Avg Latency" 
          value={`${overview.avg_latency_ms.toFixed(0)} ms`} 
          icon={<Clock size={18} className="text-amber-500" />}
          subtitle="Full platform average"
          trend={overview.avg_latency_ms < 500 ? "positive" : "negative"}
        />
        <MetricCard 
          title="Avg Cost / AI Call" 
          value={`€${overview.avg_cost_per_full_request.toFixed(4)}`} 
          icon={<Zap size={18} className="text-violet-500" />}
          subtitle="Non-cached only"
          trend="neutral"
        />
        <MetricCard 
          title="Total Savings" 
          value={`€${overview.total_savings_month_eur.toFixed(2)}`} 
          icon={<PiggyBank size={18} className="text-blue-600" />}
          subtitle="Saved AI Costs"
          trend="positive"
          isHighlight
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-8 mb-10">
        {/* 📉 MODE PERFORMANCE MIX */}
        <div className="p-8 bg-white border border-slate-100 rounded-[32px] shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-[11px] font-black text-slate-900 uppercase tracking-[0.2em] flex items-center gap-2">
              <PieChartIcon size={14} className="text-blue-600" />
              Gateway Selection Mix
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
                  formatter={(val, name) => [val, MODE_LABELS[name] || name]}
                />
                <Legend verticalAlign="bottom" height={36} iconType="circle" formatter={(v) => MODE_LABELS[v] || v} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* ⚡ LATENCY HUD */}
        <div className="p-8 bg-white border border-slate-100 rounded-[32px] shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-[11px] font-black text-slate-900 uppercase tracking-[0.2em] flex items-center gap-2">
              <Clock size={14} className="text-amber-500" />
              Latency Response Map (ms)
            </h3>
          </div>
          <div className="space-y-6">
            {latency_stats.sort((a,b) => b.avg_ms - a.avg_ms).map((item, idx) => (
              <div key={idx}>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest italic">{MODE_LABELS[item.mode] || item.mode}</span>
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
              Rejection Safety Analytics
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
               <p className="text-[10px] font-black uppercase tracking-widest mt-4 italic">No Rejections Today</p>
             </div>
          )}
        </div>
      </div>

      {/* 💰 FEATURE COST EFFICIENCY GRID */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
         <div className="p-8 bg-white border border-slate-100 rounded-[32px] shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-[11px] font-black text-slate-900 uppercase tracking-[0.2em] flex items-center gap-2">
              <BarChart3 size={14} className="text-slate-900" />
              Profitability Tier Distribution
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
              Unit Economics Per User
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-slate-50">
                  <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">Partner</th>
                  <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">Net Margin</th>
                  <th className="pb-4 text-[9px] font-black text-slate-400 uppercase tracking-[0.2em]">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {top_users.map((user, idx) => (
                  <tr key={idx} className="group hover:bg-slate-50/50 transition-colors">
                    <td className="py-5 pr-4">
                       <p className="text-sm font-black text-slate-900 italic tracking-tight truncate max-w-[180px]" title={user.email}>{user.email}</p>
                       <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">{user.plan} asset tier</p>
                    </td>
                    <td className="py-5">
                      <div className={`text-sm font-black flex items-center gap-1 ${user.profit_month_eur > 0 ? 'text-green-600' : 'text-rose-600'}`}>
                        €{user.profit_month_eur.toFixed(2)}
                        {user.profit_month_eur > 50 && <ArrowUpRight size={14} strokeWidth={3} />}
                      </div>
                      <div className="flex flex-col">
                        <p className="text-[9px] font-black uppercase text-slate-300 italic">Mnd: €{user.usage_month_eur.toFixed(2)}</p>
                        <p className="text-[9px] font-black uppercase text-blue-400 italic">Vandaag: €{user.usage_today_eur.toFixed(2)}</p>
                      </div>
                    </td>
                    <td className="py-5">
                      {user.requests_today >= user.requests_limit ? (
                        <div className="flex items-center gap-2 px-3 py-1.5 bg-rose-50 text-rose-600 rounded-xl w-fit">
                          <AlertTriangle size={12} strokeWidth={3} />
                          <span className="text-[9px] font-black uppercase tracking-widest italic">Over Quota</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 text-blue-600 rounded-xl w-fit">
                          <Target size={12} strokeWidth={3} />
                          <span className="text-[9px] font-black uppercase tracking-widest italic">Optimized</span>
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
