"use client";

import { useState } from "react";
import { Shield, Zap, Info, CheckCircle2, AlertCircle } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";

const EXCHANGES = [
  { id: "bybit", name: "Bybit", logo: "🚀", descriptionKey: "bybitDescription" },
  { id: "bitvavo", name: "Bitvavo", logo: "🏦", descriptionKey: "bitvavoDescription" },
];

export default function ExchangeSettingsForm({ onSave, onCancel }) {
  const { t } = useTranslation();
  const copy = t?.botPage?.exchangeSettings || {};
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
      setStatus({
        type: "success",
        message: copy.statusSuccess.replace(
          "{exchange}",
          selectedExchange.name
        ),
      });
    } catch (err) {
      setStatus({
        type: "error",
        message: err?.message || copy.statusError,
      });
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
                <div className="text-[11px] font-medium text-slate-400 dark:text-slate-500">{copy[ex.descriptionKey] || ex.name}</div>
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
           <div className="text-[10px] font-black text-blue-600 dark:text-blue-400 uppercase tracking-widest">{copy.selectedNode}</div>
           <div className="text-sm font-black text-slate-900 dark:text-white uppercase">{selectedExchange.name}</div>
        </div>
        <button 
          onClick={() => setStep(1)}
          className="ml-auto text-[9px] font-black text-slate-400 uppercase tracking-tighter hover:text-slate-600 underline"
        >
          {copy.change}
        </button>
      </div>

      <div className="space-y-5">
        <div className="space-y-2">
          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">{copy.apiKeyLabel}</label>
          <input 
            type="text" 
            placeholder={copy.apiKeyPlaceholder}
            className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground focus:border-blue-600 outline-none transition-all"
            value={form.api_key}
            onChange={e => setForm({...form, api_key: e.target.value})}
          />
        </div>

        <div className="space-y-2">
          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">{copy.apiSecretLabel}</label>
          <input 
            type="password" 
            placeholder={copy.apiSecretPlaceholder}
            className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground focus:border-blue-600 outline-none transition-all"
            value={form.api_secret}
            onChange={e => setForm({...form, api_secret: e.target.value})}
          />
        </div>

        {selectedExchange.id === 'bybit' && (
          <div className="space-y-2">
            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">{copy.passphraseLabel}</label>
            <input 
              type="password" 
              placeholder={copy.passphrasePlaceholder}
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
            <span className="text-[10px] font-black text-slate-600 dark:text-slate-400 uppercase tracking-widest">{copy.securityTitle}</span>
         </div>
         <p className="text-[11px] font-medium text-slate-400 leading-relaxed italic">
           {copy.securityBody}
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
           {copy.cancel}
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
           {testing ? copy.testing : copy.submit}
        </button>
      </div>
    </div>
  );
}
