"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Bell, Check, History } from "lucide-react";

import { useAuth } from "@/components/auth/AuthProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { fetchAuth } from "@/lib/api/auth";
import { readCoachFeedWithRetry } from "@/lib/finnCoachFeedRead.mjs";
import { coachFeedDetailsHref } from "@/lib/finnCoachFeedLinks.mjs";
import { coachFeedDiscussionQuestion } from "@/lib/finnCommandSearch";

const FEED_PAGE_SIZE = 50;

export default function FinnCoachFeed({ onDiscuss }) {
  const { user, sessionChecked } = useAuth();
  const { t, locale } = useTranslation();
  const copy = t.coachFeed;
  const [items, setItems] = useState([]);
  const [itemsOwner, setItemsOwner] = useState(null);
  const [itemsLocale, setItemsLocale] = useState(null);
  const [history, setHistory] = useState(false);
  const [error, setError] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState(false);
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
      const response = await readCoachFeedWithRetry(
        () => fetchAuth(`/api/assistant/feed?history=${history ? "true" : "false"}&limit=${history ? FEED_PAGE_SIZE + 1 : FEED_PAGE_SIZE}`, {
          method: "GET", forceFresh: true,
        }),
        { isCurrent: () => generation === requestGenerationRef.current &&
          ownerRef.current === requestedOwner && localeRef.current === requestedLocale },
      );
      if (generation === requestGenerationRef.current &&
          ownerRef.current === requestedOwner && localeRef.current === requestedLocale) {
        const page = Array.isArray(response) ? response : [];
        setItems(history ? page.slice(0, FEED_PAGE_SIZE) : page);
        setHasMore(history && page.length > FEED_PAGE_SIZE);
        setMoreError(false);
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

  const loadMore = async () => {
    const last = items[items.length - 1];
    if (!history || !hasMore || loadingMore || !last?.id || !last?.created_at) return;
    const requestedOwner = user?.id;
    const requestedLocale = locale;
    const generation = ++requestGenerationRef.current;
    setLoadingMore(true);
    setMoreError(false);
    try {
      const params = new URLSearchParams({ history: "true", limit: String(FEED_PAGE_SIZE + 1),
        before_created_at: last.created_at, before_id: last.id });
      const page = await fetchAuth(`/api/assistant/feed?${params.toString()}`, {
        method: "GET", forceFresh: true,
      });
      if (generation !== requestGenerationRef.current || ownerRef.current !== requestedOwner ||
          localeRef.current !== requestedLocale) return;
      const rows = Array.isArray(page) ? page : [];
      setItems((current) => {
        const known = new Set(current.map((item) => item.id));
        return [...current, ...rows.slice(0, FEED_PAGE_SIZE).filter((item) => !known.has(item.id))];
      });
      setHasMore(rows.length > FEED_PAGE_SIZE);
    } catch {
      if (generation === requestGenerationRef.current) setMoreError(true);
    } finally {
      if (generation === requestGenerationRef.current) setLoadingMore(false);
    }
  };

  useEffect(() => {
    setLoadingMore(false);
    setMoreError(false);
    if (!user?.id) {
      setItems([]);
      setItemsOwner(null);
      setItemsLocale(null);
      return undefined;
    }
    void refresh();
    const timer = window.setInterval(() => {
      if (!history && document.visibilityState === "visible") void refresh();
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
      if (history) setItems((current) => current.map((item) => item.id === id
        ? { ...item, status: action === "read" ? "read" : action } : item));
      else await refresh();
    } catch (error) {
      if (error?.status === 404) {
        // A score refresh or expired proposal can close an item between the
        // list request and the click. Reload the owner's active feed instead
        // of leaving an obsolete action and a generic error on screen.
        await refresh();
        return;
      }
      setError(true);
    }
  };

  const discuss = (item) => {
    onDiscuss?.(item.id, coachFeedDiscussionQuestion(item, locale), item);
    void setStatus(item.id, "read");
  };

  const scopedItems = itemsOwner === user?.id && itemsLocale === locale ? items : [];
  const visible = error ? [] : history ? scopedItems : scopedItems.slice(0, 3);
  const initialLoadPending = sessionChecked && Boolean(user?.id) && !error &&
    (itemsOwner !== user.id || itemsLocale !== locale);
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
      {initialLoadPending ? <p role="status" className="py-6 text-sm text-slate-500">{copy.loading}</p> : null}
      {!error && !initialLoadPending && visible.length === 0 ? <p className="py-6 text-sm text-slate-500">{copy.empty}</p> : null}
      <div className="divide-y divide-slate-100 dark:divide-slate-800">
        {visible.map((item) => (
          <article key={item.id} className="flex flex-col gap-3 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-bold text-slate-950 dark:text-slate-50">{item.title}</h3>
                {item.symbol ? <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">{["plan_review", "position_risk", "improvement_suggestion"].includes(item.event_type) && item.evidence?.trading_pair ? item.evidence.trading_pair : item.symbol}</span> : null}
              </div>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{item.description}</p>
              <time className="mt-1 block text-xs text-slate-400" dateTime={item.created_at}>
                {new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.created_at))}
              </time>
              {["plan_review", "position_risk"].includes(item.event_type) && item.source_observed_at ? (
                <time className="mt-1 block text-xs text-slate-400" dateTime={item.source_observed_at}>
                  {item.event_type === "position_risk" ? copy.valuationSource : copy.quoteSource}: {new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(item.source_observed_at))} UTC
                </time>
              ) : null}
            </div>
            {item.status === "unread" || item.status === "read" ? (
              <div className="flex shrink-0 flex-wrap items-center gap-3">
                {!item.event_type.endsWith("_report_ready") ? (
                  <button type="button" onClick={() => discuss(item)} className="inline-flex items-center gap-1 text-sm font-semibold text-blue-600 hover:underline">
                    {copy.discuss}<ArrowRight size={15} />
                  </button>
                ) : null}
                {item.event_type !== "proposal_pending" ? (
                  <a href={coachFeedDetailsHref(item)}
                    className="text-sm text-slate-600 hover:underline dark:text-slate-300">{item.event_type.endsWith("_report_ready") ? copy.viewReport : copy.details}</a>
                ) : null}
                <button type="button" onClick={() => void setStatus(item.id, "handled")}
                  className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"><Check size={14} />{copy.handled}</button>
              </div>
            ) : null}
          </article>
        ))}
      </div>
      {history && hasMore && !error ? (
        <button type="button" onClick={() => void loadMore()} disabled={loadingMore}
          className="mt-4 rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold text-blue-600 disabled:opacity-50 dark:border-slate-700">
          {loadingMore ? copy.loading : copy.loadMore}
        </button>
      ) : null}
      {moreError ? <p role="status" className="mt-2 text-sm text-amber-700">{copy.error}</p> : null}
    </section>
  );
}
