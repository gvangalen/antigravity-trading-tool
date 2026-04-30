"use client";

import { useState } from "react";
import { Shield, Zap, Info, CheckCircle2, AlertCircle } from "lucide-react";

const EXCHANGES = [
  { id: "bybit", name: "Bybit", logo: "🚀", description: "Recommended for high-speed AI execution" },
  { id: "bitvavo", name: "Bitvavo", logo: "🏦", description: "Simple EUR gateway for direct trading" },
];

export default function ExchangeSettingsForm({ onSave, onCancel }) {
  const [step, setStep] = useState(1);
  const [selectedExchange, setSelectedExchange] = useState(null);
  const [form, setForm] = useState({
    api_key: "",
    api_secret: "",
    api_passphrase: "",
  });
  const [testing, setTesting] = useState(false);
  const [status, setStatus] = useState(null);

  const handleConnect = async () => {
    setTesting(true);
    setStatus(null);
    try {
      await onSave({
        exchange_name: selectedExchange.id,
        ...form
      });
      setStatus({ type: "success", message: "Successfully connected to " + selectedExchange.name });
    } catch (err) {
      setStatus({ type: "error", message: err?.message || "Connection failed. Please check your keys." });
    } finally {
      setTesting(false);
    }
  };

  if (step === 1) {
    return (
      <div className="space-y-6 p-2">
        <div className="grid grid-cols-1 gap-4">
          {EXCHANGES.map((ex) => (
            <button
              key={ex.id}
              onClick={() => { setSelectedExchange(ex); setStep(2); }}
              className="group relative flex items-center gap-5 p-5 bg-slate-50 dark:bg-slate-900 border-2 border-slate-100 dark:border-slate-800 rounded-[1.5rem] hover:border-blue-600 transition-all text-left"
            >
              <div className="w-12 h-12 rounded-xl bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700 flex items-center justify-center text-2xl shadow-sm">
                {ex.logo}
              </div>
              <div>
                <div className="text-sm font-black text-slate-900 dark:text-white uppercase tracking-wider">{ex.name}</div>
                <div className="text-[11px] font-medium text-slate-400 dark:text-slate-500">{ex.description}</div>
              </div>
              <div className="absolute right-6 opacity-0 group-hover:opacity-100 transition-opacity">
                <Zap size={16} className="text-blue-600" />
              </div>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 p-2 animate-fade-in">
      <div className="flex items-center gap-4 p-4 bg-blue-50/50 dark:bg-blue-900/10 border-2 border-blue-600/10 rounded-2xl">
        <div className="w-10 h-10 rounded-lg bg-blue-600 text-white flex items-center justify-center text-xl shadow-lg shadow-blue-600/20">
          {selectedExchange.logo}
        </div>
        <div>
           <div className="text-[10px] font-black text-blue-600 dark:text-blue-400 uppercase tracking-widest">Selected Node</div>
           <div className="text-sm font-black text-slate-900 dark:text-white uppercase">{selectedExchange.name}</div>
        </div>
        <button 
          onClick={() => setStep(1)}
          className="ml-auto text-[9px] font-black text-slate-400 uppercase tracking-tighter hover:text-slate-600 underline"
        >
          Change
        </button>
      </div>

      <div className="space-y-5">
        <div className="space-y-2">
          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">API Key</label>
          <input 
            type="text" 
            placeholder="Paste your API key here"
            className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground focus:border-blue-600 outline-none transition-all"
            value={form.api_key}
            onChange={e => setForm({...form, api_key: e.target.value})}
          />
        </div>

        <div className="space-y-2">
          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">API Secret</label>
          <input 
            type="password" 
            placeholder="Paste your API secret here"
            className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground focus:border-blue-600 outline-none transition-all"
            value={form.api_secret}
            onChange={e => setForm({...form, api_secret: e.target.value})}
          />
        </div>

        {selectedExchange.id === 'bybit' && (
          <div className="space-y-2">
            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Passphrase (Optional)</label>
            <input 
              type="password" 
              placeholder="API Passphrase if required"
              className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground focus:border-blue-600 outline-none transition-all"
              value={form.api_passphrase}
              onChange={e => setForm({...form, api_passphrase: e.target.value})}
            />
          </div>
        )}
      </div>

      <div className="p-4 bg-slate-50 dark:bg-slate-900/50 border-2 border-slate-100 dark:border-slate-800 rounded-2xl space-y-3">
         <div className="flex items-center gap-3">
            <Shield size={16} className="text-emerald-500" />
            <span className="text-[10px] font-black text-slate-600 dark:text-slate-400 uppercase tracking-widest">Security Protocol</span>
         </div>
         <p className="text-[11px] font-medium text-slate-400 leading-relaxed italic">
           Keys are encrypted with AES-256 before storage. We recommend enabling "Withdrawals: Disabled" for this API key on your exchange for maximum safety.
         </p>
      </div>

      {status && (
        <div className={`p-4 rounded-xl flex items-center gap-3 animate-slide-up ${status.type === 'success' ? 'bg-emerald-50 text-emerald-700 border border-emerald-100' : 'bg-red-50 text-red-700 border border-red-100'}`}>
          {status.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span className="text-xs font-bold">{status.message}</span>
        </div>
      )}

      <div className="flex items-center gap-4">
         <button 
           onClick={onCancel}
           className="flex-1 py-4 text-[10px] font-black text-slate-400 uppercase tracking-widest hover:text-slate-600 transition-colors"
         >
           Cancel
         </button>
         <button 
           onClick={handleConnect}
           disabled={testing || !form.api_key || !form.api_secret}
           className="flex-[2] bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-4 rounded-2xl text-[10px] font-black uppercase tracking-[0.2em] shadow-lg shadow-blue-600/20 transition-all active:scale-95 flex items-center justify-center gap-2"
         >
           {testing ? (
             <div className="w-4 h-4 border-2 border-white/30 border-t-white animate-spin rounded-full" />
           ) : (
             <Zap size={14} />
           )}
           {testing ? "Testing Connection..." : "Verify & Connect"}
         </button>
      </div>
    </div>
  );
}
