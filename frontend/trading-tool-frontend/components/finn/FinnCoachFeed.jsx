"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Bell, Bot, FileText, MoreHorizontal } from "lucide-react";

import { useAuth } from "@/components/auth/AuthProvider";
import { useTranslation } from "@/app/providers/I18nProvider";
import { fetchAuth } from "@/lib/api/auth";
import { coachFeedHistoryCursor, readCoachFeedWithRetry } from "@/lib/finnCoachFeedRead.mjs";
import { coachFeedDetailsHref } from "@/lib/finnCoachFeedLinks.mjs";
import { visibleCoachFeedItems } from "@/lib/finnCoachFeedVisible.mjs";
import { canDiscussFeedItem, canUpdateFeedStatus } from "@/lib/finnCoachFeedActions.mjs";
import { coachFeedPresentation, coachFeedTime } from "@/lib/finnCoachFeedPresentation.mjs";
import { coachFeedDiscussionQuestion } from "@/lib/finnCommandSearch";

const FEED_PAGE_SIZE = 50;

function FeedActionMenu({ item, copy, onDiscuss, onMarkRead, showDiscuss, showMarkRead }) {
  const menuRef = useRef(null);
  useEffect(() => {
    const closeOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) menuRef.current.open = false;
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);

  return (
    <details ref={menuRef} className="relative shrink-0" onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false;
    }} onKeyDown={(event) => {
      if (event.key === "Escape") {
        menuRef.current.open = false;
        menuRef.current.querySelector("summary")?.focus();
      }
    }}>
      <summary aria-label={`${copy.moreActions}: ${item.title}`}
        className="flex size-9 cursor-pointer list-none items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600 dark:text-slate-300 dark:hover:bg-slate-800 [&::-webkit-details-marker]:hidden">
        <MoreHorizontal size={21} aria-hidden="true" />
      </summary>
      <div className="absolute right-0 top-full z-30 mt-1 min-w-48 rounded-xl border border-slate-200 bg-white p-1 shadow-lg dark:border-slate-700 dark:bg-slate-900">
        {showMarkRead ? <button type="button" onClick={() => { menuRef.current.open = false; onMarkRead(); }}
          className="block w-full rounded-lg px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800">{copy.handled}</button> : null}
        {showDiscuss ? <button type="button" onClick={() => { menuRef.current.open = false; onDiscuss(); }}
          className="block w-full rounded-lg px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800">{copy.discuss}</button> : null}
      </div>
    </details>
  );
}

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
    const cursor = coachFeedHistoryCursor(last);
    if (!history || !hasMore || loadingMore || !cursor) return;
    const requestedOwner = user?.id;
    const requestedLocale = locale;
    const generation = ++requestGenerationRef.current;
    setLoadingMore(true);
    setMoreError(false);
    try {
      const params = new URLSearchParams({ history: "true", limit: String(FEED_PAGE_SIZE + 1), ...cursor });
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
  };

  const scopedItems = itemsOwner === user?.id && itemsLocale === locale ? items : [];
  const visible = error ? [] : history ? scopedItems : visibleCoachFeedItems(scopedItems);
  const initialLoadPending = sessionChecked && Boolean(user?.id) && !error &&
    (itemsOwner !== user.id || itemsLocale !== locale);
  return (
    <section aria-label={copy.title} className="rounded-[28px] border border-slate-200/80 bg-white px-5 py-4 shadow-sm dark:border-slate-800 dark:bg-[#0f172a] lg:px-7 lg:py-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <span className="rounded-xl bg-blue-50 p-2.5 text-blue-600 dark:bg-blue-950/40"><Bell size={20} aria-hidden="true" /></span>
          <h2 className="text-xl font-bold text-slate-950 dark:text-slate-50">{copy.title}</h2>
        </div>
        <button type="button" onClick={() => setHistory((value) => !value)} className="inline-flex items-center gap-1.5 text-sm font-semibold text-blue-600 hover:underline">
          {history ? copy.active : copy.all}<ArrowRight size={16} aria-hidden="true" />
        </button>
      </div>
      {error ? <p role="status" className="py-4 text-sm text-amber-700">{copy.error}</p> : null}
      {initialLoadPending ? <p role="status" className="py-6 text-sm text-slate-500">{copy.loading}</p> : null}
      {!error && !initialLoadPending && visible.length === 0 ? <p className="py-6 text-sm text-slate-500">{copy.empty}</p> : null}
      <div className="divide-y divide-slate-200 dark:divide-slate-800">
        {visible.map((item) => {
          const isReport = item.event_type?.endsWith("_report_ready");
          const isProposal = item.event_type === "proposal_pending";
          const presentation = coachFeedPresentation(item, copy);
          const moment = coachFeedTime(item, locale, copy);
          const title = item.event_type === "daily_report_ready" && moment.label.startsWith(`${copy.today} ·`)
            ? copy.reportReadyTitle : presentation.title;
          const canDiscuss = canDiscussFeedItem(item, history);
          const canMarkRead = canUpdateFeedStatus(item);
          const showMarkRead = item.status === "unread";
          const showMenu = showMarkRead || (canDiscuss && !isProposal);
          const Icon = item.subject_type === "bot" || item.event_type === "bot_decision" ? Bot
            : isReport || item.subject_type === "report" ? FileText : Bell;
          return (
            <article key={item.id} className="grid grid-cols-[36px_minmax(0,1fr)] gap-x-3 gap-y-2 py-4 sm:grid-cols-[40px_minmax(0,1fr)_auto] sm:items-center sm:gap-x-4">
              <Icon size={27} strokeWidth={1.8} className="mt-1 text-slate-900 dark:text-slate-100 sm:mt-0" aria-hidden="true" />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  {item.status === "unread" ? <span className="size-2.5 shrink-0 rounded-full bg-blue-600"><span className="sr-only">{copy.unread}</span></span> : null}
                  <h3 className="text-base font-bold text-slate-950 dark:text-slate-50">{title}</h3>
                  {presentation.badge ? <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">{presentation.badge}</span> : null}
                </div>
                {!isReport && presentation.description ? <p className="mt-0.5 line-clamp-2 text-sm text-slate-600 dark:text-slate-300">{presentation.description}</p> : null}
                <time className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400" dateTime={moment.value}>
                  {moment.label}
                </time>
              </div>
              <div className="col-start-2 flex items-center gap-2 sm:col-start-3 sm:row-start-1 sm:justify-self-end">
                {isProposal && canDiscuss ? (
                  <button type="button" onClick={() => discuss(item)} className="inline-flex items-center gap-1 whitespace-nowrap text-sm font-semibold text-blue-600 hover:underline">
                    {copy.discuss}<ArrowRight size={16} aria-hidden="true" />
                  </button>
                ) : (
                  <a href={coachFeedDetailsHref(item)}
                    onClick={(event) => {
                      if (!isReport || item.status !== "unread") return;
                      event.preventDefault();
                      void setStatus(item.id, "read").finally(() => {
                        window.location.assign(coachFeedDetailsHref(item));
                      });
                    }}
                    className="inline-flex items-center gap-1 whitespace-nowrap text-sm font-semibold text-blue-600 hover:underline">
                    {item.event_type === "data_blocked" && item.subject_type === "bot" && item.evidence?.missing_indicators
                      ? copy.reviewManualBuy : isReport ? copy.viewReport : item.event_type === "bot_decision" ? copy.viewBotDetails : copy.details}
                    <ArrowRight size={16} aria-hidden="true" />
                  </a>
                )}
                {showMenu ? <FeedActionMenu item={item} copy={copy}
                  showDiscuss={canDiscuss && !isProposal} showMarkRead={showMarkRead}
                  onDiscuss={() => discuss(item)} onMarkRead={() => void setStatus(item.id, "read")} /> : null}
              </div>
            </article>
          );
        })}
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
