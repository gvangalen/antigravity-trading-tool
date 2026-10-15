"use client";

import { useEffect, useRef, useState } from "react";
import { Link as LinkIcon, RefreshCcw } from "lucide-react";
import ExchangeSettingsForm from "@/components/bot/ExchangeSettingsForm";
import { useModal } from "@/components/modal/ModalProvider";
import Drawer from "@/components/ui/Drawer";
import { useTranslation } from "@/app/providers/I18nProvider";
import { formatCurrency } from "@/lib/i18n";
import { fetchAuth } from "@/lib/api/auth";

function exchangeErrorMessage(error, fallback) {
  try {
    const detail = JSON.parse(error?.body || "{}").detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  } catch {}
  return error?.message || fallback;
}

export default function SystemConnectivity({ variant = "default" }) {
  const { showSnackbar } = useModal();
  const { t, locale } = useTranslation();
  const [exchanges, setExchanges] = useState([]);
  const [connections, setConnections] = useState([]);
  const [statusError, setStatusError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [disconnecting, setDisconnecting] = useState("");
  const exchangeFormRef = useRef(null);
  const copy = t?.dashboard?.systemConnectivity || {};

  const fetchExchanges = async () => {
    try {
      setStatusError(false);
      const statusData = await fetchAuth("/api/exchange/status", { forceFresh: true });
      setConnections(Array.isArray(statusData) ? statusData : []);
      if (variant !== "bot") {
        try {
          const balances = await fetchAuth("/api/exchange/balances", { forceFresh: true });
          setExchanges(Array.isArray(balances) ? balances : []);
        } catch {
          setExchanges([]);
        }
      }
    } catch (err) {
      setStatusError(true);
      console.error("Failed to fetch exchange status", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExchanges();
  }, []);

  const handleSave = async (payload) => {
    await fetchAuth("/api/exchange/keys", {
      method: "POST",
      body: JSON.stringify(payload),
    }).catch((error) => { throw new Error(exchangeErrorMessage(error, copy.saveError)); });
    await fetchExchanges();
  };

  const closeDrawer = () => {
    if (exchangeFormRef.current?.isSubmitting?.()) return;
    setIsDrawerOpen(false);
  };

  const disconnectExchange = async (exchangeName) => {
    setDisconnecting(exchangeName);
    try {
      await fetchAuth(`/api/exchange/keys/${encodeURIComponent(exchangeName)}`, {
        method: "DELETE",
      });
      await fetchExchanges();
      showSnackbar(copy.disconnected?.replace("{exchange}", exchangeName) || copy.statusDisconnected, "success");
    } catch (error) {
      showSnackbar(exchangeErrorMessage(error, copy.disconnectError), "error");
    } finally {
      setDisconnecting("");
    }
  };

  const handleOpenSettings = () => {
    setIsDrawerOpen(true);
  };

  const isConnected = connections.length > 0;

  return (
    <div className={variant === "bot" ? "flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900" : "flex items-center gap-6"}>
      {variant === "bot" && (
        <div>
          <div className="text-[10px] font-black uppercase tracking-widest text-blue-700">{t?.botPage?.focus?.exchangeTitle}</div>
          <div className="mt-1 text-sm font-bold text-slate-900 dark:text-white">
            {statusError ? t?.botPage?.focus?.exchangeUnknown : isConnected ? connections.map((connection) => connection.exchange).join(", ") : t?.botPage?.focus?.exchangeMissing}
          </div>
          <p className="mt-1 text-xs text-slate-500">{t?.botPage?.focus?.exchangeDescription}</p>
        </div>
      )}
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

      {variant !== "bot" && <div className="flex items-center gap-3">
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
      </div>}

      <Drawer
        isOpen={isDrawerOpen}
        onClose={closeDrawer}
        isCloseBlocked={() => Boolean(exchangeFormRef.current?.isSubmitting?.())}
        title={copy.manageTitle}
        subtitle={isConnected ? copy.statusConnected : copy.statusDisconnected}
        description={isConnected ? copy.contextConnected : copy.contextDisconnected}
        width="max-w-2xl"
      >
        {connections.length > 0 && <div className="mb-5 space-y-2">
          <p className="text-xs font-bold text-slate-600 dark:text-slate-300">{copy.connectedExchanges}</p>
          {connections.map((connection) => <div key={connection.exchange} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-700">
            <span className="text-sm font-bold text-slate-900 dark:text-white">{connection.exchange}</span>
            <button type="button" disabled={Boolean(disconnecting)} onClick={() => disconnectExchange(connection.exchange)} className="text-xs font-bold text-red-700 disabled:opacity-50 dark:text-red-300">
              {disconnecting === connection.exchange ? copy.disconnecting : copy.disconnectButton}
            </button>
          </div>)}
          <p className="text-xs text-slate-500">{copy.switchExchangeHint}</p>
        </div>}
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
