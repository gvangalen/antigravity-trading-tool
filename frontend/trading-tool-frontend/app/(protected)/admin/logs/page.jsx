"use client";

import React, { useCallback, useRef, useState } from "react";
import { fetchAdminLogs, analyzeAdminLogs } from "@/lib/api/admin";
import { useVisibilityPolling } from "@/hooks/useVisibilityPolling";
import { 
  FileText, 
  Search, 
  Filter, 
  Terminal, 
  AlertCircle, 
  Info, 
  AlertTriangle, 
  ShieldAlert,
  RefreshCcw,
  BrainCircuit,
  Clock,
  Database,
  Globe,
  Settings,
  ChevronDown,
  X
} from "lucide-react";

const LEVEL_CONFIG = {
  info: { icon: <Info size={14} />, color: "text-blue-500", bg: "bg-blue-50/50", border: "border-blue-100" },
  warning: { icon: <AlertTriangle size={14} />, color: "text-yellow-500", bg: "bg-yellow-50/50", border: "border-yellow-100" },
  error: { icon: <AlertCircle size={14} />, color: "text-red-500", bg: "bg-red-50/50", border: "border-red-100" },
  critical: { icon: <ShieldAlert size={14} />, color: "text-rose-600", bg: "bg-rose-50/50", border: "border-rose-100" }
};

const SOURCE_ICONS = {
  auth: <Settings size={12} />,
  api: <Globe size={12} />,
  db: <Database size={12} />,
  ai: <BrainCircuit size={12} />,
  backend: <Terminal size={12} />
};

export default function AdminLogsPage() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [filters, setFilters] = useState({
    level: "",
    source: "",
    search: ""
  });
  const isFetchingRef = useRef(false);

  const loadLogs = useCallback(async () => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    try {
      const data = await fetchAdminLogs(filters, { forceFresh: true });
      setLogs(data);
    } catch (err) {
      console.error("Logs laden mislukt", err);
    } finally {
      setLoading(false);
      isFetchingRef.current = false;
    }
  }, [filters]);

  useVisibilityPolling(loadLogs, {
    intervalMs: 10000,
    backgroundIntervalMs: 60000,
    runImmediately: true,
    deps: [filters.level, filters.source, filters.search],
  });

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setAnalysis(null);
    try {
      const result = await analyzeAdminLogs();
      setAnalysis(result);
    } catch (err) {
      alert("Analyse uitvoeren mislukt. Controleer de logs.");
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="p-8 max-w-[1700px] mx-auto animate-fade-in bg-[#fcfcfd] min-h-screen">
      {/* 🏔️ HEADER */}
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-10">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2.5 bg-slate-900 text-white rounded-xl shadow-2xl shadow-slate-900/30">
              <FileText size={22} />
            </div>
            <h1 className="text-3xl font-black text-slate-900 tracking-tight italic">
              Systeem <span className="text-blue-600">logs</span>
            </h1>
          </div>
          <p className="text-slate-500 font-medium max-w-2xl text-sm">
            Realtime overzicht van platformactiviteiten, beveiligingsmeldingen en interne systeemsignalen.
          </p>
        </div>
        
        <div className="flex items-center gap-4">
          <button 
            onClick={handleAnalyze}
            disabled={analyzing}
            className="px-6 py-3 bg-blue-600 text-white rounded-2xl font-black text-[10px] uppercase tracking-widest hover:bg-blue-700 transition-all shadow-lg shadow-blue-600/20 flex items-center gap-2 active:scale-95 disabled:opacity-50"
          >
            {analyzing ? <RefreshCcw size={14} className="animate-spin" /> : <BrainCircuit size={14} />}
            Analyseer fouten
          </button>
          <button 
            onClick={loadLogs}
            className="px-6 py-3 bg-white border border-slate-200 rounded-2xl font-black text-[10px] uppercase tracking-widest text-slate-600 hover:border-slate-900 hover:text-slate-900 transition-all shadow-sm flex items-center gap-2 active:scale-95"
          >
            <RefreshCcw size={14} />
            Vernieuwen
          </button>
        </div>
      </div>

      {/* 🧠 AI ANALYSIS PANEL */}
      {analysis && (
        <div className="mb-8 p-8 bg-slate-900 rounded-[32px] text-white shadow-2xl animate-slide-up relative overflow-hidden">
          <div className="absolute top-0 right-0 p-8">
            <button onClick={() => setAnalysis(null)} className="text-slate-500 hover:text-white transition-colors">
              <X size={20} />
            </button>
          </div>
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-blue-500/20 text-blue-400 rounded-lg">
              <BrainCircuit size={20} />
            </div>
            <h2 className="text-lg font-black italic tracking-tight">AI-diagnoserapport</h2>
            <span className={`ml-4 px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-[0.2em] ${
              analysis.severity === 'critical' ? 'bg-rose-500 text-white' : 
              analysis.severity === 'high' ? 'bg-orange-500 text-white' : 'bg-blue-500 text-white'
            }`}>
              {analysis.severity} prioriteit
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
            <div className="space-y-2">
              <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Hoofdoorzaak</p>
              <p className="text-sm font-bold text-slate-200 leading-relaxed">{analysis.root_cause}</p>
            </div>
            <div className="space-y-2">
              <p className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Impact</p>
              <p className="text-sm font-bold text-slate-200 leading-relaxed">{analysis.what_is_broken}</p>
            </div>
            <div className="space-y-2 col-span-2">
              <p className="text-[10px] font-black text-blue-400 uppercase tracking-widest">Voorgestelde fix</p>
              <div className="p-4 bg-slate-800/50 rounded-2xl border border-slate-700/50">
                <p className="text-sm font-mono text-blue-100">{analysis.suggested_fix}</p>
              </div>
            </div>
          </div>
          <div className="mt-6 pt-6 border-t border-slate-800 flex items-center gap-6">
             <div className="flex items-center gap-2">
                <span className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Categorie:</span>
                <span className="text-[10px] font-black text-white uppercase tracking-widest">{analysis.category}</span>
             </div>
             <div className="flex items-center gap-2">
                <span className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Actie:</span>
                <span className="text-[10px] font-black text-white uppercase tracking-widest">{analysis.action_type}</span>
             </div>
          </div>
        </div>
      )}

      {/* 🔍 FILTERS */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="relative col-span-2">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
          <input 
            type="text" 
            placeholder="Zoek op logregel of inhoud..."
            className="w-full pl-12 pr-4 py-4 bg-white border border-slate-100 rounded-2xl text-sm font-bold focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition-all shadow-sm"
            value={filters.search}
            onChange={(e) => setFilters({...filters, search: e.target.value})}
          />
        </div>
        <div className="relative">
          <Filter className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
          <select 
            className="w-full pl-12 pr-4 py-4 bg-white border border-slate-100 rounded-2xl text-sm font-black uppercase tracking-widest appearance-none focus:outline-none transition-all shadow-sm italic cursor-pointer"
            value={filters.level}
            onChange={(e) => setFilters({...filters, level: e.target.value})}
          >
            <option value="">Alle niveaus</option>
            <option value="info">Info</option>
            <option value="warning">Waarschuwingen</option>
            <option value="error">Alleen fouten</option>
            <option value="critical">Alleen kritiek</option>
          </select>
        </div>
        <div className="relative">
          <Terminal className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
          <select 
            className="w-full pl-12 pr-4 py-4 bg-white border border-slate-100 rounded-2xl text-sm font-black uppercase tracking-widest appearance-none focus:outline-none transition-all shadow-sm italic cursor-pointer"
            value={filters.source}
            onChange={(e) => setFilters({...filters, source: e.target.value})}
          >
            <option value="">Alle bronnen</option>
            <option value="auth">Auth</option>
            <option value="api">API</option>
            <option value="ai">AI</option>
            <option value="market_data">Marktdata</option>
            <option value="db">Database</option>
          </select>
        </div>
      </div>

      {/* 📋 LOGS TABLE */}
      <div className="bg-white border border-slate-100 rounded-[32px] shadow-sm overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-50 bg-slate-50/30">
              <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Tijdstip</th>
              <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Bron</th>
              <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Niveau</th>
              <th className="px-6 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Melding</th>
              <th className="px-8 py-5 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Endpoint</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {logs.map((log) => {
              const cfg = LEVEL_CONFIG[log.level] || LEVEL_CONFIG.info;
              return (
                <tr key={log.id} className="group hover:bg-slate-50/50 transition-colors">
                  <td className="px-8 py-5">
                    <div className="flex items-center gap-2 text-[11px] font-bold text-slate-900 tabular-nums">
                      <Clock size={12} className="text-slate-300" />
                      {new Date(log.created_at).toLocaleTimeString()}
                      <span className="text-slate-300 font-medium ml-1">
                        {new Date(log.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-5">
                    <div className="flex items-center gap-2 px-2.5 py-1.5 bg-slate-50 rounded-lg w-fit border border-slate-100">
                      <span className="text-slate-400">{SOURCE_ICONS[log.source] || <Terminal size={12} />}</span>
                      <span className="text-[10px] font-black uppercase tracking-widest text-slate-600">{log.source}</span>
                    </div>
                  </td>
                  <td className="px-6 py-5">
                    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border w-fit font-black text-[9px] uppercase tracking-widest italic ${cfg.bg} ${cfg.border} ${cfg.color}`}>
                      {cfg.icon}
                      {log.level}
                    </div>
                  </td>
                  <td className="px-6 py-5">
                    <p className="text-xs font-bold text-slate-900 max-w-xl truncate group-hover:whitespace-normal group-hover:overflow-visible transition-all">
                      {log.message}
                    </p>
                  </td>
                  <td className="px-8 py-5">
                    {log.endpoint ? (
                      <code className="text-[10px] font-mono font-bold text-blue-600 bg-blue-50 px-2 py-1 rounded-md">
                        {log.endpoint}
                      </code>
                    ) : (
                      <span className="text-[9px] font-black text-slate-300 uppercase tracking-widest">Interne service</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {logs.length === 0 && !loading && (
          <div className="p-20 text-center">
             <div className="inline-flex p-4 bg-slate-50 rounded-full text-slate-300 mb-4">
                <Search size={32} />
             </div>
             <p className="text-slate-400 font-black uppercase tracking-widest text-xs italic">Geen systeemactiviteit gevonden</p>
          </div>
        )}
        {loading && (
           <div className="p-20 text-center flex flex-col items-center">
              <div className="w-10 h-10 border-4 border-slate-100 border-t-blue-600 rounded-full animate-spin mb-4" />
              <p className="text-slate-400 font-black uppercase tracking-widest text-[9px] italic">Logs synchroniseren...</p>
           </div>
        )}
      </div>
    </div>
  );
}
