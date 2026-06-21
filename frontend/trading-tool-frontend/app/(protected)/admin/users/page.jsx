"use client";

import React, { useState, useEffect } from "react";
import { fetchAdminUsers, updateAdminUser } from "@/lib/api/admin";
import { 
  Users, 
  Search, 
  Filter, 
  MoreVertical, 
  Shield, 
  ShieldCheck, 
  ShieldAlert,
  Zap, 
  Mail, 
  Calendar,
  Clock,
  ArrowUpRight,
  Settings2,
  RefreshCcw,
  CheckCircle2,
  XCircle,
  AlertCircle
} from "lucide-react";

const PLAN_BADGES = {
  basis: "bg-blue-50 text-blue-600 border-blue-100",
  pro: "bg-indigo-50 text-indigo-600 border-indigo-100",
  premium: "bg-purple-50 text-purple-600 border-purple-100",
  free: "bg-slate-50 text-slate-600 border-slate-100"
};

function formatCurrency(value) {
  return `€${Number(value || 0).toFixed(2)}`;
}

export default function AdminUsersDashboard() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [filterPlan, setFilterPlan] = useState("all");
  const [editingUser, setEditingUser] = useState(null);

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    setLoading(true);
    try {
      const data = await fetchAdminUsers();
      setUsers(data);
    } catch (err) {
      console.error("Failed to load admin users", err);
      setError("Je hebt geen admin rechten of de API is offline.");
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateUser = async (userId, updates) => {
    try {
      await updateAdminUser(userId, updates);
      // Reload users to get fresh data
      loadUsers();
      setEditingUser(null);
    } catch (err) {
      alert("Fout bij het updaten van de gebruiker.");
    }
  };

  const filteredUsers = users.filter(user => {
    const matchesSearch = user.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         (user.first_name && user.first_name.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesPlan = filterPlan === "all" || user.ai_plan === filterPlan;
    return matchesSearch && matchesPlan;
  });

  if (loading) return (
    <div className="p-10 flex flex-col items-center justify-center min-h-[60vh]">
      <div className="w-12 h-12 border-4 border-slate-900/10 border-t-slate-900 rounded-full animate-spin mb-4" />
      <p className="text-slate-400 font-black uppercase tracking-widest text-[10px] italic">Accessing User Directories...</p>
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
              User <span className="text-blue-600">Intelligence Management</span>
            </h1>
          </div>
          <p className="text-slate-500 font-medium max-w-2xl text-sm">
            Monitor activity, manage AI quotas and control platform access for all registered intelligence partners.
          </p>
        </div>
        
        <div className="flex items-center gap-4">
          <button 
            onClick={loadUsers}
            className="px-6 py-3 bg-white border border-slate-200 rounded-2xl font-black text-[10px] uppercase tracking-widest text-slate-600 hover:border-slate-900 hover:text-slate-900 transition-all shadow-sm flex items-center gap-2 active:scale-95"
          >
            <RefreshCcw size={14} />
            Refresh Directory
          </button>
        </div>
      </div>

      {/* 🔍 FILTERS */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="relative col-span-2">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
          <input 
            type="text" 
            placeholder="Search email or partner name..."
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
            onChange={(e) => setFilterPlan(e.target.value)}
          >
            <option value="all">All Intelligence Plans</option>
            <option value="basis">Basis Tier</option>
            <option value="pro">Pro Tier</option>
            <option value="premium">Premium Tier</option>
          </select>
        </div>
      </div>

      {/* 📋 USER TABLE */}
      <div className="bg-white border border-slate-100 rounded-[32px] shadow-sm overflow-hidden">
        <div className="px-8 py-5 border-b border-slate-100 bg-slate-50/60">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-[11px] text-slate-500 font-medium">
            <p><span className="font-black text-violet-500 uppercase tracking-widest">Background</span> zijn automatische rapporten, agent-runs en Celery-jobs voor deze user.</p>
            <p><span className="font-black text-rose-500 uppercase tracking-widest">Blocked</span> laat zien hoeveel AI-verkeer op quota stukliep en wat dat ongeveer had gekost.</p>
            <p><span className="font-black text-blue-500 uppercase tracking-widest">MTD</span> blijft de echte succesvolle spend; blocked staat er bewust los naast.</p>
          </div>
        </div>
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-50 bg-slate-50/30">
              <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Intelligence Partner</th>
              <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Plan & Status</th>
              <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">AI Intelligence Quota</th>
              <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Activity Map</th>
              <th className="px-8 py-5 text-right font-black text-slate-400"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {filteredUsers.map((user) => (
              <tr key={user.id} className="group hover:bg-slate-50/50 transition-colors">
                <td className="px-8 py-6">
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-400 group-hover:bg-slate-900 group-hover:text-white transition-all">
                      <Mail size={18} />
                    </div>
                    <div>
                      <p className="text-sm font-black text-slate-900 italic tracking-tight">{user.email}</p>
                      <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5 mt-0.5">
                        {user.first_name ? `${user.first_name} ${user.last_name || ""}` : "Unidentified Partner"}
                      </p>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-6 font-bold">
                  <div className="flex flex-col gap-2">
                    <span className={`px-3 py-1 rounded-lg text-[9px] font-black uppercase tracking-widest border w-fit italic ${PLAN_BADGES[user.ai_plan] || PLAN_BADGES.free}`}>
                      {user.ai_plan} Tier
                    </span>
                    <div className="flex items-center gap-2">
                      <div className={`w-1.5 h-1.5 rounded-full ${user.is_active ? 'bg-green-500' : 'bg-rose-500'}`} />
                      <span className="text-[10px] font-black uppercase tracking-widest text-slate-500 italic">
                        {user.is_active ? 'Secure Access' : 'Access Revoked'}
                      </span>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-6 font-bold">
                  <div>
                    <div className="flex justify-between items-center mb-2">
                       <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest italic">Daily Load</span>
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
                    <p className="text-[9px] font-black uppercase text-blue-400 mt-2 italic">MTD Cost: {formatCurrency(user.usage_month_eur)}</p>
                    <p className="text-[9px] font-black uppercase text-emerald-500 mt-1 italic">Today: {formatCurrency(user.usage_today_eur)}</p>
                    <p className="text-[9px] font-black uppercase text-violet-400 mt-1 italic">Background: {formatCurrency(user.background_usage_month_eur)}</p>
                    <p className="text-[9px] font-black uppercase text-rose-500 mt-1 italic">Blocked: {user.blocked_requests_month} / {formatCurrency(user.blocked_estimated_cost_month_eur)} est.</p>
                  </div>
                </td>
                <td className="px-6 py-6 font-bold">
                   <div className="space-y-1.5">
                      <div className="flex items-center gap-2 text-[10px] font-black text-slate-500 uppercase tracking-widest italic">
                        <Clock size={12} className="text-slate-300" />
                        Last Seen: <span className="text-slate-900">{user.last_login_at ? new Date(user.last_login_at).toLocaleDateString() : "Never"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] font-black text-slate-500 uppercase tracking-widest italic">
                        <Calendar size={12} className="text-slate-300" />
                        Joined: <span className="text-slate-900">{user.created_at ? new Date(user.created_at).toLocaleDateString() : "Unknown"}</span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] font-black text-slate-500 uppercase tracking-widest italic">
                        <Zap size={12} className="text-slate-300" />
                        AI Activity: <span className="text-slate-900">{user.last_ai_activity_at ? new Date(user.last_ai_activity_at).toLocaleDateString() : "No usage"}</span>
                      </div>
                   </div>
                </td>
                <td className="px-8 py-6 text-right">
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
        {filteredUsers.length === 0 && (
          <div className="p-20 text-center">
             <div className="inline-flex p-4 bg-slate-50 rounded-full text-slate-300 mb-4">
                <Search size={32} />
             </div>
             <p className="text-slate-400 font-black uppercase tracking-widest text-xs italic">No Intelligence Partners Found</p>
          </div>
        )}
      </div>

      {/* 🛠️ EDIT MODAL */}
      {editingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="bg-white w-full max-w-lg rounded-[32px] shadow-2xl overflow-hidden animate-slide-up border border-slate-100">
            <div className="p-8 border-b border-slate-50 flex justify-between items-start">
               <div>
                 <h2 className="text-xl font-black text-slate-900 italic tracking-tight mb-1">Modify Personnel File</h2>
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
                  <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-4 block italic">Intelligence Tier</label>
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
                        {plan}
                      </button>
                    ))}
                  </div>
               </div>

               {/* QUOTA */}
               <div>
                  <label className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-4 block italic">Daily Request Limit</label>
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
                    <h4 className="text-[11px] font-black text-slate-900 uppercase tracking-widest italic mb-1">Access Protocol</h4>
                    <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">Toggle binary platform status</p>
                  </div>
                  <button 
                    onClick={() => handleUpdateUser(editingUser.id, { is_active: !editingUser.is_active })}
                    className={`px-5 py-2.5 rounded-xl font-black text-[10px] uppercase tracking-widest transition-all italic ${
                      editingUser.is_active 
                        ? 'bg-green-100 text-green-700 border border-green-200' 
                        : 'bg-rose-100 text-rose-700 border border-rose-200'
                    }`}
                  >
                    {editingUser.is_active ? 'ACTIVE' : 'LOCKED'}
                  </button>
               </div>
            </div>

            <div className="p-8 bg-slate-50/50 border-t border-slate-50">
               <button 
                onClick={() => setEditingUser(null)}
                className="w-full py-4 bg-slate-900 text-white rounded-2xl font-black text-[11px] uppercase tracking-widest italic shadow-xl shadow-slate-900/20 active:scale-[0.98] transition-all"
               >
                 Confirm Parameters
               </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
