"use client";

import { useState, useEffect } from "react";
import { Zap, Link as LinkIcon, RefreshCcw, ShieldCheck, XCircle } from "lucide-react";
import Modal from "@/components/ui/Modal";
import ExchangeSettingsForm from "@/components/bot/ExchangeSettingsForm";

export default function SystemConnectivity() {
  const [exchanges, setExchanges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);

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
    setShowModal(false);
  };

  const isConnected = exchanges.length > 0;

  return (
    <div className="flex items-center gap-6">
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'}`} />
        <span className="text-[10px] font-black text-secondary dark:text-slate-500 uppercase tracking-widest">
          {isConnected ? 'Exchange Linked' : 'Simulated Environment'}
        </span>
      </div>

      <button
        onClick={() => setShowModal(true)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-[10px] font-black uppercase tracking-widest transition-all ${
          isConnected 
          ? 'bg-emerald-50 border-emerald-100 text-emerald-600 hover:bg-emerald-100' 
          : 'bg-blue-50 border-blue-100 text-blue-600 hover:bg-blue-100'
        }`}
      >
        <LinkIcon size={12} />
        {isConnected ? 'Manage Exchange' : 'Connect Exchange'}
      </button>

      {/* BALANCE PILLS */}
      {exchanges.map((ex, idx) => (
        <div key={idx} className="hidden md:flex items-center gap-2 px-3 py-1.5 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-lg">
           <span className="text-[9px] font-black text-slate-400 uppercase">{ex.exchange}</span>
           <span className="text-[11px] font-black text-slate-900 dark:text-white">€{ex.total_eur.toLocaleString()}</span>
        </div>
      ))}

      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title={
          <div className="flex items-center gap-3">
             <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-lg shadow-blue-600/20">
                <Zap size={20} />
             </div>
             <div>
                <h3 className="text-xl font-black text-slate-900 dark:text-white tracking-tight">Exchange Connection</h3>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Global Asset Synchronization</p>
             </div>
          </div>
        }
      >
        <ExchangeSettingsForm 
          onSave={handleSave} 
          onCancel={() => setShowModal(false)} 
        />
      </Modal>
    </div>
  );
}
