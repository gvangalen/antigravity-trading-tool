"use client";

import { useEffect, useRef, useState } from "react";
import { Link as LinkIcon, RefreshCcw } from "lucide-react";
import ExchangeSettingsForm from "@/components/bot/ExchangeSettingsForm";
import { useModal } from "@/components/modal/ModalProvider";
import Drawer from "@/components/ui/Drawer";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatCurrency } from "@/lib/i18n";

export default function SystemConnectivity() {
  const { showSnackbar } = useModal();
  const { t, locale } = useTranslation();
  const [exchanges, setExchanges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const exchangeFormRef = useRef(null);
  const copy = t?.dashboard?.systemConnectivity || {};

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
      throw new Error(err.detail || copy.saveError);
    }
    await fetchExchanges();
  };

  const closeDrawer = () => {
    if (exchangeFormRef.current?.isSubmitting?.()) return;
    setIsDrawerOpen(false);
  };

  const handleOpenSettings = () => {
    setIsDrawerOpen(true);
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
        {isConnected ? copy.manageButton : copy.connectButton}
      </button>

      <div className="flex items-center gap-3">
        {exchanges.map((ex, idx) => (
          <div key={idx} className="hidden md:flex items-center gap-2 px-3 py-1.5 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-lg">
             <span className="text-[9px] font-black text-slate-400 uppercase">{ex.exchange}</span>
             <span className="text-[11px] font-black text-slate-900 dark:text-white">
               {formatCurrency(Number(ex.total_eur ?? 0), locale, "EUR", { maximumFractionDigits: 0 })}
             </span>
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

      <Drawer
        isOpen={isDrawerOpen}
        onClose={closeDrawer}
        isCloseBlocked={() => Boolean(exchangeFormRef.current?.isSubmitting?.())}
        title={copy.manageTitle}
        subtitle={exchanges.length > 0 ? copy.statusConnected : copy.statusDisconnected}
        description={exchanges.length > 0 ? copy.contextConnected : copy.contextDisconnected}
        width="max-w-2xl"
      >
        <ExchangeSettingsForm
          ref={exchangeFormRef}
          onSave={handleSave}
          onCancel={closeDrawer}
          onSaved={(status) => {
            showSnackbar(status?.message || copy.statusConnected, "success");
            setIsDrawerOpen(false);
          }}
        />
      </Drawer>
    </div>
  );
}
