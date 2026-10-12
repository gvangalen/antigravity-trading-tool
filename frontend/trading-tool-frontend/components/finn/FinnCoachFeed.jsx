"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Bell, Check, History } from "lucide-react";

import { useAuth } from "@/components/auth/AuthProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { fetchAuth } from "@/lib/api/auth";

export default function FinnCoachFeed({ onDiscuss }) {
  const { user, sessionChecked } = useAuth();
  const { t, locale } = useTranslation();
  const copy = t.coachFeed;
  const [items, setItems] = useState([]);
  const [itemsOwner, setItemsOwner] = useState(null);
  const [itemsLocale, setItemsLocale] = useState(null);
  const [history, setHistory] = useState(false);
  const [error, setError] = useState(false);
  const requestGenerationRef = useRef(0);
  const ownerRef = useRef(user?.id);
  const localeRef = useRef(locale);
  ownerRef.current = user?.id;
  localeRef.current = locale;

  const refresh = useCallback(async () => {
    if (!sessionChecked || !user?.id) return;
    const requestedOwner = user.id;
    const requestedLocale = locale;
    const generation = ++requestGenerationRef.current;
    try {
      const response = await fetchAuth(`/api/assistant/feed?history=${history ? "true" : "false"}&limit=50`, {
        method: "GET", forceFresh: true,
      });
      if (generation === requestGenerationRef.current &&
          ownerRef.current === requestedOwner && localeRef.current === requestedLocale) {
        setItems(Array.isArray(response) ? response : []);
        setItemsOwner(requestedOwner);
        setItemsLocale(requestedLocale);
        setError(false);
      }
    } catch {
      if (generation === requestGenerationRef.current &&
          ownerRef.current === requestedOwner && localeRef.current === requestedLocale) {
        setError(true);
      }
    }
  }, [history, locale, sessionChecked, user?.id]);

  useEffect(() => {
    if (!user?.id) {
      setItems([]);
      setItemsOwner(null);
      setItemsLocale(null);
      return undefined;
    }
    void refresh();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, 60000);
    return () => {
      requestGenerationRef.current += 1;
      window.clearInterval(timer);
    };
  }, [refresh, user?.id]);

  const setStatus = async (id, action) => {
    try {
      await fetchAuth(`/api/assistant/feed/${encodeURIComponent(id)}/${action}`, {
        method: "POST", body: JSON.stringify({}),
      });
      await refresh();
    } catch {
      setError(true);
    }
  };

  const discuss = (item) => {
    void setStatus(item.id, "read");
    onDiscuss?.(item.id, `${copy.discussQuery} ${item.evidence?.subject || item.title}`);
  };

  const scopedItems = itemsOwner === user?.id && itemsLocale === locale ? items : [];
  const visible = history ? scopedItems : scopedItems.slice(0, 3);
  return (
    <section aria-label={copy.title} className="rounded-[28px] border border-slate-200/80 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-[#0f172a] lg:p-7">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <span className="rounded-xl bg-blue-50 p-2 text-blue-600 dark:bg-blue-950/40"><Bell size={20} /></span>
          <div>
            <h2 className="text-xl font-bold text-slate-950 dark:text-slate-50">{copy.title}</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">{copy.subtitle}</p>
          </div>
        </div>
        <button type="button" onClick={() => setHistory((value) => !value)} className="inline-flex items-center gap-2 text-sm font-semibold text-blue-600 hover:underline">
          <History size={15} />{history ? copy.active : copy.all}
        </button>
      </div>
      {error ? <p role="status" className="py-4 text-sm text-amber-700">{copy.error}</p> : null}
      {!error && visible.length === 0 ? <p className="py-6 text-sm text-slate-500">{copy.empty}</p> : null}
      <div className="divide-y divide-slate-100 dark:divide-slate-800">
        {visible.map((item) => (
          <article key={item.id} className="flex flex-col gap-3 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-bold text-slate-950 dark:text-slate-50">{item.title}</h3>
                {item.symbol ? <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">{item.symbol}</span> : null}
              </div>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{item.description}</p>
              <time className="mt-1 block text-xs text-slate-400" dateTime={item.updated_at}>
                {new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.updated_at))}
              </time>
            </div>
            {item.status === "unread" || item.status === "read" ? (
              <div className="flex shrink-0 flex-wrap items-center gap-3">
                <button type="button" onClick={() => discuss(item)} className="inline-flex items-center gap-1 text-sm font-semibold text-blue-600 hover:underline">
                  {copy.discuss}<ArrowRight size={15} />
                </button>
                {item.event_type !== "proposal_pending" ? (
                  <a href={item.subject_type === "setup"
                    ? `/setup?symbol=${encodeURIComponent(item.symbol || "")}&setup_id=${encodeURIComponent(item.subject_id || "")}`
                    : item.subject_type === "bot"
                      ? `/bot?symbol=${encodeURIComponent(item.symbol || "")}&bot_id=${encodeURIComponent(item.subject_id || "")}`
                      : `/asset?symbol=${encodeURIComponent(item.symbol || "")}`}
                    className="text-sm text-slate-600 hover:underline dark:text-slate-300">{copy.details}</a>
                ) : null}
                <button type="button" onClick={() => void setStatus(item.id, "handled")}
                  className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"><Check size={14} />{copy.handled}</button>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
