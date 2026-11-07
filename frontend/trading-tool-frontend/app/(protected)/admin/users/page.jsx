"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "@/app/providers/I18nProvider";
import { fetchAdminUsers, fetchAdminUserUsage, updateAdminUser } from "@/lib/api/admin";
import { formatCurrency as formatIntlCurrency, formatDateTime } from "@/lib/i18n";
import { 
  Users, 
  Search, 
  Filter, 
  Zap, 
  Mail, 
  Calendar,
  Clock,
  Settings2,
  RefreshCcw,
  XCircle,
} from "lucide-react";

const PLAN_BADGES = {
  basis: "bg-blue-50 text-blue-600 border-blue-100",
  pro: "bg-indigo-50 text-indigo-600 border-indigo-100",
  premium: "bg-purple-50 text-purple-600 border-purple-100",
  free: "bg-slate-50 text-slate-600 border-slate-100"
};
const PAGE_SIZE = 50;

function formatCurrency(value, locale) {
  const amount = Number(value || 0);
  const decimals = amount > 0 && amount < 0.01 ? 6 : 2;
  return formatIntlCurrency(amount, locale, "EUR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatActivityDate(value, locale, fallback) {
  return value ? formatDateTime(value, locale, { dateStyle: "medium", timeStyle: "short" }) : fallback;
}

export default function AdminUsersDashboard() {
  const { t, locale } = useTranslation();
  const copy = t.adminUsersPage;
  const [users, setUsers] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [filterPlan, setFilterPlan] = useState("all");
  const [editingUser, setEditingUser] = useState(null);
  const [usageUser, setUsageUser] = useState(null);
  const [usageDetail, setUsageDetail] = useState(null);
  const [usageLoading, setUsageLoading] = useState(false);
  const [usageError, setUsageError] = useState(false);
  const requestIdRef = useRef(0);
  const usageRequestIdRef = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(0);
      setDebouncedSearch(searchTerm.trim());
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  const loadUsers = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    try {
      const data = await fetchAdminUsers({
        offset: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        search: debouncedSearch,
        plan: filterPlan,
      });
      if (requestId === requestIdRef.current) {
        setUsers(data.items);
        setTotal(data.total);
        setError(null);
      }
    } catch (err) {
      console.error("Admingebruikers laden mislukt", err);
      if (requestId === requestIdRef.current) setError(copy.loadError);
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  }, [page, debouncedSearch, filterPlan, copy.loadError]);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  const handleUpdateUser = async (userId, updates) => {
    try {
      await updateAdminUser(userId, updates);
      // Reload users to get fresh data
      await loadUsers();
      setEditingUser(null);
    } catch (err) {
      alert(copy.updateError);
    }
  };

  const openUsage = async (user) => {
    const requestId = ++usageRequestIdRef.current;
    setUsageUser(user);
    setUsageDetail(null);
    setUsageError(false);
    setUsageLoading(true);
    try {
      const detail = await fetchAdminUserUsage(user.id);
      if (usageRequestIdRef.current === requestId) setUsageDetail(detail);
    } catch {
      if (usageRequestIdRef.current === requestId) setUsageError(true);
    } finally {
      if (usageRequestIdRef.current === requestId) setUsageLoading(false);
    }
  };

  const closeUsage = () => {
    usageRequestIdRef.current += 1;
    setUsageUser(null);
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  if (loading) return (
      <div className="p-10 flex flex-col items-center justify-center min-h-[60vh]">
      <div className="w-12 h-12 border-4 border-slate-900/10 border-t-slate-900 rounded-full animate-spin mb-4" />
      <p className="text-slate-400 font-black uppercase tracking-widest text-[10px] italic">{copy.loading}</p>
    </div>
  );

  return (
    <div className="p-8 max-w-[1700px] mx-auto animate-fade-in bg-[#fcfcfd] min-h-screen">
      {/* 🏔️ HEADER */}
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-10">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2.5 bg-slate-900 text-white rounded-xl shadow-2xl shadow-slate-900/30">
              <Users size={22} />
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
          <button 
            onClick={() => void loadUsers()}
            className="px-6 py-3 bg-white border border-slate-200 rounded-2xl font-black text-[10px] uppercase tracking-widest text-slate-600 hover:border-slate-900 hover:text-slate-900 transition-all shadow-sm flex items-center gap-2 active:scale-95"
          >
            <RefreshCcw size={14} />
            {copy.refresh}
          </button>
        </div>
      </div>

      {/* 🔍 FILTERS */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="relative col-span-2">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
          <input 
            type="text" 
            placeholder={copy.searchPlaceholder}
            className="w-full pl-12 pr-4 py-4 bg-white border border-slate-100 rounded-2xl text-sm font-bold focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition-all shadow-sm"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="relative">
          <Filter className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
          <select 
            className="w-full pl-12 pr-4 py-4 bg-white border border-slate-100 rounded-2xl text-sm font-black uppercase tracking-widest appearance-none focus:outline-none transition-all shadow-sm italic cursor-pointer"
            value={filterPlan}
            onChange={(e) => { setPage(0); setFilterPlan(e.target.value); }}
          >
            <option value="all">{copy.allPlans}</option>
            <option value="free">{copy.planLabels.free}</option>
            <option value="basis">{copy.planLabels.basis}</option>
            <option value="pro">{copy.planLabels.pro}</option>
            <option value="premium">{copy.planLabels.premium}</option>
          </select>
        </div>
      </div>

      {/* 📋 USER TABLE */}
      {error && <p role="alert" className="mb-4 rounded-xl bg-rose-50 p-4 text-sm text-rose-700">{error}</p>}
      <div className="bg-white border border-slate-100 rounded-[32px] shadow-sm overflow-hidden">
        <div className="px-8 py-5 border-b border-slate-100 bg-slate-50/60">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-[11px] text-slate-500 font-medium">
            <p><span className="font-black text-violet-500 uppercase tracking-widest">{copy.infoBadges.background}</span> {copy.infoBackground}</p>
            <p><span className="font-black text-rose-500 uppercase tracking-widest">{copy.infoBadges.blocked}</span> {copy.infoBlocked}</p>
            <p><span className="font-black text-blue-500 uppercase tracking-widest">{copy.infoBadges.mtd}</span> {copy.infoMtd}</p>
          </div>
          <p className="mt-3 text-xs text-slate-500">{copy.activityExplanation}</p>
        </div>
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-50 bg-slate-50/30">
              <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.user}</th>
              <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.planStatus}</th>
              <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.aiLimit}</th>
              <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.table.activity}</th>
              <th className="px-8 py-5 text-right font-black text-slate-400"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {users.map((user) => (
              <tr key={user.id} className="group hover:bg-slate-50/50 transition-colors">
                <td className="px-8 py-6">
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-400 group-hover:bg-slate-900 group-hover:text-white transition-all">
                      <Mail size={18} />
                    </div>
                    <div>
                      <p className="text-sm font-black text-slate-900 italic tracking-tight">{user.email}</p>
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5 mt-0.5">
                        {user.first_name ? `${user.first_name} ${user.last_name || ""}` : copy.unknownUser}
                      </p>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-6 font-bold">
                  <div className="flex flex-col gap-2">
                    <span className={`px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest border w-fit italic ${PLAN_BADGES[user.ai_plan] || PLAN_BADGES.free}`}>
                      {copy.planLabels[user.ai_plan] || user.ai_plan}
                    </span>
                    <div className="flex items-center gap-2">
                      <div className={`w-1.5 h-1.5 rounded-full ${user.is_active ? 'bg-green-500' : 'bg-rose-500'}`} />
                      <span className="text-[10px] font-black uppercase tracking-widest text-slate-500 italic">
                        {user.is_active ? copy.statusActive : copy.statusBlocked}
                      </span>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-6 font-bold">
                  <div>
                    <div className="flex justify-between items-center mb-2">
                       <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest italic">{copy.dailyLimit}</span>
                       <span className="text-[11px] font-black text-slate-900">{user.ai_requests_used_day} / {user.ai_requests_limit_day}</span>
                    </div>
                    <div className="h-1.5 w-full bg-slate-50 rounded-full overflow-hidden">
                      <div 
                        className={`h-full rounded-full transition-all duration-500 ${
                          (user.ai_requests_used_day / user.ai_requests_limit_day) > 0.8 ? 'bg-rose-500' : 'bg-blue-600'
                        }`}
                        style={{ width: `${Math.min(100, (user.ai_requests_used_day / user.ai_requests_limit_day) * 100)}%` }}
                      />
                    </div>
                    <p className="text-[9px] font-black uppercase text-blue-400 mt-2 italic">{copy.costMtd}: {formatCurrency(user.usage_month_eur, locale)}</p>
                    {user.unpriced_requests_month > 0 && <p className="mt-1 text-[9px] font-bold text-amber-700">{copy.unpricedRequests.replace("{count}", user.unpriced_requests_month)}</p>}
                    <p className="text-[9px] font-black uppercase text-emerald-500 mt-1 italic">{copy.today}: {formatCurrency(user.usage_today_eur, locale)}</p>
                    <p className="text-[9px] font-black uppercase text-violet-400 mt-1 italic">{copy.background}: {formatCurrency(user.background_usage_month_eur, locale)}</p>
                    <p className="text-[9px] font-black uppercase text-rose-500 mt-1 italic">{copy.blocked}: {user.blocked_requests_month} / {formatCurrency(user.blocked_estimated_cost_month_eur, locale)} {copy.estimate}</p>
                  </div>
                </td>
                <td className="px-6 py-6 font-bold">
                   <div className="space-y-1.5">
                      <div className="flex items-center gap-2 text-[10px] font-black text-slate-500 uppercase tracking-widest italic">
                        <Clock size={12} className="text-slate-300" />
                        {copy.lastLogin}: <span className="text-slate-900">{formatActivityDate(user.last_login_at, locale, copy.never)}</span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] font-black text-slate-500 uppercase tracking-widest italic">
                        <Calendar size={12} className="text-slate-300" />
                        {copy.appActivity}: <span className="text-slate-900">{formatActivityDate(user.last_app_activity_at, locale, copy.notYetMeasured)}</span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] font-black text-slate-500 uppercase tracking-widest italic">
                        <Zap size={12} className="text-slate-300" />
                        {copy.activeDays}: <span className="text-slate-900">{user.active_days_30d ?? 0}</span>
                      </div>
                      <div className="text-[10px] font-bold text-slate-500">{copy.interactiveAi}: <span className="text-slate-900">{formatActivityDate(user.last_interactive_ai_at, locale, copy.noUsage)}</span></div>
                      <div className="text-[10px] font-bold text-slate-500">{copy.automaticAi}: <span className="text-slate-900">{formatActivityDate(user.last_background_ai_at, locale, copy.noUsage)}</span></div>
                      <div className="text-[10px] font-bold text-slate-500">{copy.otherAi}: <span className="text-slate-900">{formatActivityDate(user.last_other_ai_at, locale, copy.noUsage)}</span></div>
                   </div>
                </td>
                <td className="px-8 py-6 text-right">
                   <button
                    type="button"
                    onClick={() => void openUsage(user)}
                    className="mr-2 rounded-xl border border-blue-100 px-3 py-2 text-xs font-bold text-blue-700 hover:bg-blue-50"
                   >
                     {copy.usageDetails}
                   </button>
                   <button 
                    onClick={() => setEditingUser(user)}
                    className="p-2.5 hover:bg-slate-100 rounded-xl transition-all text-slate-400 hover:text-slate-900 active:scale-90 border border-transparent hover:border-slate-200"
                   >
                     <Settings2 size={18} />
                   </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && (
          <div className="p-20 text-center">
             <div className="inline-flex p-4 bg-slate-50 rounded-full text-slate-300 mb-4">
                <Search size={32} />
             </div>
             <p className="text-slate-400 font-black uppercase tracking-widest text-xs italic">{copy.noUsersFound}</p>
          </div>
        )}
      </div>

      {total > 0 && (
        <div className="mt-5 flex items-center justify-between gap-4 text-sm text-slate-600">
          <span>{copy.pagination?.showing || "Showing"} {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} {copy.pagination?.of || "of"} {total}</span>
          <div className="flex items-center gap-3">
            <button type="button" disabled={page === 0} onClick={() => setPage((value) => value - 1)} className="rounded-xl border border-slate-200 px-4 py-2 disabled:opacity-40">{copy.pagination?.previous || "Previous"}</button>
            <span>{page + 1} / {totalPages}</span>
            <button type="button" disabled={page + 1 >= totalPages} onClick={() => setPage((value) => value + 1)} className="rounded-xl border border-slate-200 px-4 py-2 disabled:opacity-40">{copy.pagination?.next || "Next"}</button>
          </div>
        </div>
      )}

      {usageUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" role="dialog" aria-modal="true" aria-label={copy.usageTitle}>
          <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-black text-slate-900">{copy.usageTitle}</h2>
                <p className="text-sm text-slate-500">{usageUser.email} · {copy.usagePeriod}</p>
              </div>
              <button type="button" onClick={closeUsage} aria-label={copy.close} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><XCircle size={20} /></button>
            </div>
            {usageLoading && <p className="text-sm text-slate-500">{copy.usageLoading}</p>}
            {usageError && <p role="alert" className="text-sm text-rose-700">{copy.usageError}</p>}
            {usageDetail && (
              <>
                <div className="mb-6 grid grid-cols-2 gap-3 rounded-2xl bg-slate-50 p-4 text-sm md:grid-cols-3">
                  <p><span className="block text-slate-500">{copy.costMtd}</span><strong>{formatCurrency(usageDetail.cost_month_eur, locale)}</strong></p>
                  <p><span className="block text-slate-500">{copy.today}</span><strong>{formatCurrency(usageDetail.cost_today_eur, locale)}</strong></p>
                  <p><span className="block text-slate-500">{copy.usageRequests}</span><strong>{usageDetail.requests_month}</strong></p>
                  <p><span className="block text-slate-500">{copy.usageRequestsToday}</span><strong>{usageDetail.requests_today}</strong></p>
                  <p><span className="block text-slate-500">{copy.inputTokens}</span><strong>{usageDetail.input_tokens_month.toLocaleString(locale)}</strong></p>
                  <p><span className="block text-slate-500">{copy.outputTokens}</span><strong>{usageDetail.output_tokens_month.toLocaleString(locale)}</strong></p>
                </div>
                {usageDetail.unpriced_requests_month > 0 && <p className="mb-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{copy.unpricedRequests.replace("{count}", usageDetail.unpriced_requests_month)} {copy.unpricedExplanation}</p>}
                {[[copy.usageByFeature, usageDetail.by_feature, copy.usageFeatureLabels], [copy.usageBySource, usageDetail.by_source, copy.usageSourceLabels]].map(([title, rows, labels]) => (
                  <section key={title} className="mb-6">
                    <h3 className="mb-2 font-bold text-slate-900">{title}</h3>
                    {rows.length === 0 ? <p className="text-sm text-slate-500">{copy.noUsage}</p> : (
                      <div className="overflow-x-auto rounded-xl border border-slate-100">
                        <table className="w-full text-left text-sm">
                          <thead className="bg-slate-50 text-slate-500"><tr><th className="p-3">{copy.usageCategory}</th><th className="p-3">{copy.usageRequests}</th><th className="p-3">{copy.inputTokens}</th><th className="p-3">{copy.outputTokens}</th><th className="p-3">{copy.costMtd}</th></tr></thead>
                          <tbody>{rows.map((row) => <tr key={row.category} className="border-t border-slate-100"><td className="p-3">{labels[row.category] || labels.other}</td><td className="p-3">{row.requests}</td><td className="p-3">{row.input_tokens.toLocaleString(locale)}</td><td className="p-3">{row.output_tokens.toLocaleString(locale)}</td><td className="p-3">{formatCurrency(row.cost_eur, locale)}</td></tr>)}</tbody>
                        </table>
                      </div>
                    )}
                  </section>
                ))}
                <p className="text-xs text-slate-500">{copy.usagePrivacyNote}</p>
              </>
            )}
          </div>
        </div>
      )}

      {/* 🛠️ EDIT MODAL */}
      {editingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="bg-white w-full max-w-lg rounded-[32px] shadow-2xl overflow-hidden animate-slide-up border border-slate-100">
            <div className="p-8 border-b border-slate-50 flex justify-between items-start">
               <div>
                 <h2 className="text-xl font-black text-slate-900 italic tracking-tight mb-1">{copy.editUser}</h2>
                 <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{editingUser.email}</p>
               </div>
               <button 
                onClick={() => setEditingUser(null)}
                className="p-2 hover:bg-slate-50 rounded-xl text-slate-400 transition-colors"
               >
                 <XCircle size={20} />
               </button>
            </div>
            
            <div className="p-8 space-y-8">
               {/* PLAN SELECT */}
               <div>
                  <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-4 block italic">{copy.plan}</label>
                  <div className="grid grid-cols-2 gap-3">
                    {['basis', 'pro', 'premium'].map((plan) => (
                      <button 
                        key={plan}
                        onClick={() => handleUpdateUser(editingUser.id, { ai_plan: plan })}
                        className={`px-4 py-3 rounded-2xl text-[10px] font-black uppercase tracking-widest border transition-all italic ${
                          editingUser.ai_plan === plan 
                            ? 'bg-slate-900 border-slate-900 text-white' 
                            : 'bg-white border-slate-100 text-slate-400 hover:border-slate-900 hover:text-slate-900'
                        }`}
                      >
                        {copy.planLabels[plan] || plan}
                      </button>
                    ))}
                  </div>
               </div>

               {/* QUOTA */}
               <div>
                  <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-4 block italic">{copy.dailyLimitLong}</label>
                  <div className="flex items-center gap-4">
                    <input 
                      type="range" 
                      min="10" 
                      max="2000" 
                      step="10"
                      className="flex-1 accent-slate-900 cursor-pointer h-2 bg-slate-100 rounded-full appearance-none"
                      value={editingUser.ai_requests_limit_day}
                      onChange={(e) => setEditingUser({...editingUser, ai_requests_limit_day: parseInt(e.target.value)})}
                      onMouseUp={() => handleUpdateUser(editingUser.id, { ai_requests_limit_day: editingUser.ai_requests_limit_day })}
                    />
                    <div className="px-4 py-2 bg-slate-50 rounded-xl font-black text-xs text-slate-900 italic">
                      {editingUser.ai_requests_limit_day}
                    </div>
                  </div>
               </div>

               {/* STATUS */}
               <div className="flex items-center justify-between p-6 bg-slate-50 rounded-[24px]">
                  <div>
                    <h4 className="text-[11px] font-black text-slate-900 uppercase tracking-widest italic mb-1">{copy.access}</h4>
                    <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">{copy.toggleAccess}</p>
                  </div>
                  <button 
                    onClick={() => handleUpdateUser(editingUser.id, { is_active: !editingUser.is_active })}
                    className={`px-5 py-2.5 rounded-xl font-black text-[10px] uppercase tracking-widest transition-all italic ${
                      editingUser.is_active 
                        ? 'bg-green-100 text-green-700 border border-green-200' 
                        : 'bg-rose-100 text-rose-700 border border-rose-200'
                    }`}
                  >
                    {editingUser.is_active ? copy.statusActive.toUpperCase() : copy.statusBlocked.toUpperCase()}
                  </button>
               </div>
            </div>

            <div className="p-8 bg-slate-50/50 border-t border-slate-50">
               <button 
                onClick={() => setEditingUser(null)}
                className="w-full py-4 bg-slate-900 text-white rounded-2xl font-black text-[11px] uppercase tracking-widest italic shadow-xl shadow-slate-900/20 active:scale-[0.98] transition-all"
               >
                 {copy.close}
               </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
