"use client";

import { useState, useEffect } from "react";
import { Zap, Link as LinkIcon, RefreshCcw, ShieldCheck, XCircle } from "lucide-react";
import { useModal } from "@/components/modal/ModalProvider";
import ExchangeSettingsForm from "@/components/bot/ExchangeSettingsForm";

export default function SystemConnectivity() {
  const { openConfirm, close: closeModal } = useModal();
  const [exchanges, setExchanges] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchExchanges = async () => {
    try {
      const res = await fetch("/api/exchange/balances");
      if (res.ok) {
        const data = await res.json();
        setExchanges(data);
      }
    } catch (err) {
      console.error("Failed to fetch exchange status", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExchanges();
  }, []);

  const handleSave = async (payload) => {
    const res = await fetch("/api/exchange/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to save keys");
    }
    await fetchExchanges();
    closeModal();
  };

  const handleOpenSettings = () => {
    openConfirm({
      title: "Exchangeverbinding beheren",
      statusLabel: exchanges.length > 0 ? "Verbonden" : "Nog niet gekoppeld",
      context: exchanges.length > 0
        ? "Je beheert de gekoppelde exchange-sleutels voor deze omgeving."
        : "Je koppelt een exchange zodat Finn en bots order- en portfolioinformatie kunnen gebruiken.",
      impact: "Alleen de exchange-instellingen van deze omgeving worden bijgewerkt.",
      safety: "Controleer goed of je de juiste omgeving gebruikt. Live- en staging-sleutels blijven gescheiden.",
      consequence: "Na opslaan vernieuwt de verbindingsstatus direct in dit scherm.",
      description: <ExchangeSettingsForm onSave={handleSave} onCancel={closeModal} />,
      icon: <Zap size={20} />,
      tone: "info"
    });
  };

  const isConnected = exchanges.length > 0;

  return (
    <div className="flex items-center gap-6">
      <button
        onClick={handleOpenSettings}
        className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border text-[11px] font-black uppercase tracking-widest transition-all shadow-sm active:scale-95 ${
          isConnected 
          ? 'bg-emerald-50 border-emerald-100 text-emerald-600 hover:bg-emerald-100 hover:shadow-emerald-600/5' 
          : 'bg-blue-50 border-blue-100 text-blue-600 hover:bg-blue-100 hover:shadow-blue-600/5'
        }`}
      >
        <LinkIcon size={14} />
        {isConnected ? 'Beheer exchange' : 'Koppel exchange'}
      </button>

      <div className="flex items-center gap-3">
        {exchanges.map((ex, idx) => (
          <div key={idx} className="hidden md:flex items-center gap-2 px-3 py-1.5 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-lg">
             <span className="text-[9px] font-black text-slate-400 uppercase">{ex.exchange}</span>
             <span className="text-[11px] font-black text-slate-900 dark:text-white">€{ex.total_eur.toLocaleString()}</span>
          </div>
        ))}
        
        {isConnected && (
          <button 
            onClick={fetchExchanges}
            disabled={loading}
            className={`p-2 rounded-lg bg-slate-100 dark:bg-slate-900 text-secondary hover:text-blue-600 transition-all ${loading ? 'animate-spin' : ''}`}
          >
            <RefreshCcw size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
