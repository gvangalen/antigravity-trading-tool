'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowDownRight, ArrowUpRight, Brain, ChevronRight, FileText, Loader2, RefreshCw } from 'lucide-react';
import { useTranslation } from '@/app/providers/I18nProvider';
import { fetchFinnTradeReview, fetchFinnTradeReviews, fetchFinnExchangeTradeImports, fetchFinnExchangeImportFills, syncFinnExchangeTradeImport, createFinnExchangeTradeReview, saveFinnTradeReviewNote, saveFinnTradeReviewLesson, fetchFinnTradeChart, analyzeFinnTradeReview, fetchFinnTradeMessages, askFinnTradeReview, uploadFinnTradeScreenshot, deleteFinnTradeScreenshot, fetchFinnTradeScreenshot } from '@/lib/api/botApi';
import BybitDerivativeReviews from './BybitDerivativeReviews';

const number = (value) => Number(value) || 0;

function formatMoney(value, locale, digits = 2) {
  return new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR', maximumFractionDigits: digits }).format(number(value));
}

function formatQuote(value, currency, locale) {
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 8 }).format(number(value))} ${currency || ''}`.trim();
}

function formatDate(value, locale) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

function sourceLabel(sources, copy) {
  const value = Array.isArray(sources) ? sources : [];
  return value.map((source) => source === 'manual' ? copy.manual : source === 'bot' ? copy.bot : String(source).replace(/^./, (letter) => letter.toUpperCase())).join(' + ');
}

const isExchangeReview = (origin) => origin === 'exchange_user_attested' || origin === 'bybit_derivative_user_attested';

function PlanFacts({ plan, copy }) {
  const label = (key) => copy.planFields?.[key] || key.replaceAll('_', ' ').replace(/([a-z])([A-Z])/g, '$1 $2');
  const value = (item, depth = 0) => {
    if (item == null || item === '') return null;
    if (Array.isArray(item)) return <ul className="mt-1 list-disc space-y-1 pl-5">{item.map((part, index) => <li key={index}>{value(part, depth + 1)}</li>)}</ul>;
    if (typeof item === 'object' && depth < 3) return <dl className="mt-1 space-y-1">{Object.entries(item).map(([key, part]) => <div key={key}><dt className="inline font-semibold">{label(key)}: </dt><dd className="inline">{value(part, depth + 1)}</dd></div>)}</dl>;
    return String(item);
  };
  return <dl className="mt-4 space-y-3 text-sm leading-relaxed text-slate-700 dark:text-slate-300">{Object.entries(plan).map(([key, item]) => <div key={key}><dt className="font-bold text-slate-900 dark:text-white">{label(key)}</dt><dd>{value(item)}</dd></div>)}</dl>;
}

function TradeChart({ chart, copy, locale }) {
  const candles = chart?.candles || [];
  if (candles.length < 2) return null;
  const markerTimes = chart.markers || [];
  const minTime = new Date(candles[0].at).getTime();
  const maxTime = new Date(candles[candles.length - 1].end).getTime();
  const prices = [...candles.flatMap((c) => [number(c.low), number(c.high)]), ...markerTimes.map((m) => number(m.price_eur))].filter((n) => n > 0);
  const low = Math.min(...prices);
  const high = Math.max(...prices);
  const x = (at) => 70 + ((new Date(at).getTime() - minTime) / Math.max(maxTime - minTime, 1)) * 600;
  const y = (price) => 195 - ((number(price) - low) / Math.max(high - low, 0.000001)) * 160;
  const ticks = [low, (low + high) / 2, high];
  return <div className="mt-3 overflow-x-auto rounded-xl bg-slate-50 p-3 dark:bg-slate-900">
    <svg role="img" aria-label={copy.chartTitle} viewBox="0 0 700 245" className="min-w-[600px] w-full">
      {ticks.map((price) => <g key={price}><line x1="70" x2="670" y1={y(price)} y2={y(price)} stroke="#cbd5e1" strokeDasharray="3 4" /><text x="4" y={y(price) + 4} fill="#64748b" fontSize="10">{formatMoney(price, locale, 2)}</text></g>)}
      <line x1="70" x2="670" y1="205" y2="205" stroke="#94a3b8" />
      <text x="70" y="229" fill="#64748b" fontSize="10">{formatDate(candles[0].at, locale)}</text>
      <text x="670" y="229" textAnchor="end" fill="#64748b" fontSize="10">{formatDate(candles[candles.length - 1].end, locale)}</text>
      {candles.map((c, i) => <g key={`${c.at}-${i}`}><line x1={x(c.at)} x2={x(c.at)} y1={y(c.high)} y2={y(c.low)} stroke="#64748b" strokeWidth="1" /><line x1={x(c.at)} x2={x(c.at)} y1={y(c.open)} y2={y(c.close)} stroke={number(c.close) >= number(c.open) ? '#059669' : '#e11d48'} strokeWidth="3" /></g>)}
      {markerTimes.map((m) => <g key={m.ledger_id}><circle cx={x(m.at)} cy={y(m.price_eur)} r="6" fill={m.side === 'buy' ? '#2563eb' : '#f59e0b'} stroke="white" strokeWidth="2" /><title>{`${m.side} · ${m.at} · €${m.price_eur}`}</title></g>)}
    </svg>
    <p className="text-xs text-slate-500">{copy.chartSource}: {chart.source} {chart.provider_symbol} · {chart.timeframe}. {copy.chartMarkers}</p>
  </div>;
}

function ExecutionTimeline({ fills, copy, locale }) {
  const events = fills.map((fill, index) => ({
    id: fill.exchange_fill_id ?? fill.derivative_execution_id ?? index,
    at: new Date(fill.at).getTime(),
    side: fill.side,
    label: `${fill.side === 'buy' ? copy.buy : copy.sell} ${fill.qty} · ${formatDate(fill.at, locale)}`,
  })).filter((fill) => Number.isFinite(fill.at));
  if (events.length < 2) return null;
  const first = Math.min(...events.map((event) => event.at));
  const last = Math.max(...events.map((event) => event.at));
  const sampled = events.length > 80 ? [...events.slice(0, 40), ...events.slice(-40)] : events;
  const x = (at, index) => first === last
    ? 35 + (index / Math.max(sampled.length - 1, 1)) * 630
    : 35 + ((at - first) / (last - first)) * 630;
  return <div className="mt-3 overflow-x-auto rounded-xl bg-slate-50 p-3 dark:bg-slate-900">
    <svg role="img" aria-label={copy.executionTimeline} viewBox="0 0 700 100" className="min-w-[460px] w-full">
      <line x1="35" x2="665" y1="45" y2="45" stroke="#94a3b8" strokeWidth="2" />
      {sampled.map((event, index) => <g key={`${event.id}-${index}`}><line x1={x(event.at, index)} x2={x(event.at, index)} y1="35" y2="55" stroke={event.side === 'buy' ? '#2563eb' : '#f59e0b'} strokeWidth="2" /><circle cx={x(event.at, index)} cy="45" r="5" fill={event.side === 'buy' ? '#2563eb' : '#f59e0b'} stroke="white" strokeWidth="1.5" /><title>{event.label}</title></g>)}
      <text x="35" y="82" fill="#64748b" fontSize="10">{formatDate(first, locale)}</text>
      <text x="665" y="82" textAnchor="end" fill="#64748b" fontSize="10">{formatDate(last, locale)}</text>
    </svg>
    <p className="text-xs text-slate-500">{copy.executionTimelineNote}{events.length > sampled.length ? ` ${copy.executionTimelineSampled.replace('{shown}', String(sampled.length)).replace('{total}', String(events.length))}` : ''}</p>
  </div>;
}

function ReviewDetail({ review, onClose, onSaved, copy, locale }) {
  const [note, setNote] = useState(review.note || '');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [noteError, setNoteError] = useState(false);
  const [lessonText, setLessonText] = useState(review.lesson?.status === 'active' ? review.lesson.lesson_text : '');
  const [lessonBusy, setLessonBusy] = useState(false);
  const [lessonError, setLessonError] = useState(false);
  const [lessonSaved, setLessonSaved] = useState(false);
  const [chart, setChart] = useState(null);
  const [chartState, setChartState] = useState('loading');
  const [imageUrl, setImageUrl] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [analysis, setAnalysis] = useState(review.analysis_json || null);
  const [analysisStatus, setAnalysisStatus] = useState(review.analysis_status);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState('');
  const [messages, setMessages] = useState([]);
  const [hasOlderMessages, setHasOlderMessages] = useState(false);
  const [loadingOlderMessages, setLoadingOlderMessages] = useState(false);
  const [question, setQuestion] = useState('');
  const fills = Array.isArray(review.fills) ? review.fills : [];
  const plan = review.plan_snapshot && typeof review.plan_snapshot === 'object' ? review.plan_snapshot : null;
  const originalPlanVerified = Boolean(plan) && review.plan_status === 'entry_order_plan_recorded';
  const isDerivative = review.origin === 'bybit_derivative_user_attested';
  const isExchange = review.origin === 'exchange_user_attested' || isDerivative;
  const isPaper = !isExchange && String(review.execution_environment).toLowerCase() === 'paper';
  const cashLegs = Array.isArray(review.cash_legs_by_currency) ? review.cash_legs_by_currency : [];
  const feeLegs = Array.isArray(review.fee_legs_by_currency) ? review.fee_legs_by_currency : [];
  const metricCards = isDerivative
    ? [[copy.derivativePosition, `${copy.derivativeDirection?.[review.direction] || review.direction || ''} · ${copy.derivativeCategory?.[review.derivative_category] || review.derivative_category || ''}`],
      [copy.derivativeContracts, String(review.entry_qty ?? copy.exchangeResultUnavailable)],
      [copy.derivativeNativePnl, review.native_pnl == null ? copy.exchangeResultUnavailable : formatQuote(review.native_pnl, review.settle_currency, locale)],
      [copy.derivativeFees, feeLegs.length ? feeLegs.map((leg) => formatQuote(leg.amount, leg.currency, locale)).join(' · ') : copy.exchangeResultUnavailable]]
    : isExchange
    ? [[copy.quantity, String(review.entry_qty)],
      [copy.exchangeResult, review.pnl_eur_before_fees == null ? copy.exchangeResultUnavailable : formatMoney(review.pnl_eur_before_fees, locale)],
      [copy.exchangeCashLegs, cashLegs.length ? cashLegs.map((leg) => `${leg.currency}: ${copy.buy} ${formatQuote(leg.buy_cost, leg.currency, locale)} / ${copy.sell} ${formatQuote(leg.sell_proceeds, leg.currency, locale)}`).join(' · ') : copy.exchangeResultUnavailable]]
    : [[isPaper ? copy.paperEntry : copy.entry, formatMoney(review.entry_price_eur, locale, 4)],
      [isPaper ? copy.paperExit : copy.exit, formatMoney(review.exit_price_eur, locale, 4)],
      [copy.quantity, String(review.entry_qty)],
      [isPaper ? copy.paperResult : copy.result, formatMoney(review.pnl_eur_before_fees, locale)]];

  useEffect(() => {
    let active = true;
    if (!isExchange) fetchFinnTradeChart(review.id).then((result) => { if (active) { setChart(result.chart); setChartState(result.status); } }).catch(() => { if (active) setChartState('failed'); });
    else setChartState('unavailable');
    fetchFinnTradeMessages(review.id).then((result) => { if (active) { const rows = Array.isArray(result) ? result : []; setMessages(rows); setHasOlderMessages(rows.length === 100); } }).catch(() => { if (active) setAiError(copy.aiHistoryError); });
    return () => { active = false; };
  }, [review.id, isExchange, copy.aiHistoryError]);

  useEffect(() => {
    if (!['loading', 'failed'].includes(chartState)) return undefined;
    const timer = window.setInterval(() => {
      fetchFinnTradeChart(review.id).then((result) => {
        setChart(result.chart);
        setChartState(result.status);
      }).catch(() => setChartState('failed'));
    }, chartState === 'loading' ? 15000 : 30000);
    return () => window.clearInterval(timer);
  }, [review.id, chartState]);

  useEffect(() => {
    setAnalysis(review.analysis_json || null);
    setAnalysisStatus(review.analysis_status);
  }, [review.analysis_json, review.analysis_status]);

  useEffect(() => {
    setLessonText(review.lesson?.status === 'active' ? review.lesson.lesson_text : '');
  }, [review.id, review.lesson?.lesson_text, review.lesson?.status]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      fetchFinnTradeReview(review.id).then((fresh) => {
        if (fresh.analysis_status !== analysisStatus) {
          fetchFinnTradeMessages(review.id).then((history) => {
            const rows = Array.isArray(history) ? history : [];
            setMessages(rows);
            setHasOlderMessages(rows.length === 100);
          }).catch(() => setAiError(copy.aiHistoryError));
        }
        setAnalysis(fresh.analysis_json || null);
        setAnalysisStatus(fresh.analysis_status);
      }).catch(() => {});
    }, ['pending', 'running'].includes(analysisStatus) ? 15000 : 30000);
    return () => window.clearInterval(timer);
  }, [review.id, analysisStatus, copy.aiHistoryError]);

  useEffect(() => {
    let active = true;
    let url;
    setImageUrl(null);
    if (review.has_screenshot) fetchFinnTradeScreenshot(review.id).then((blob) => { url = URL.createObjectURL(blob); if (active) setImageUrl(url); else URL.revokeObjectURL(url); }).catch(() => { if (active) setUploadError(copy.screenshotError); });
    return () => { active = false; if (url) URL.revokeObjectURL(url); };
  }, [review.id, review.screenshot_sha256, review.has_screenshot, copy.screenshotError]);

  async function refreshReview() {
    const updated = await fetchFinnTradeReview(review.id);
    onSaved(updated);
    try {
      const history = await fetchFinnTradeMessages(review.id);
      const rows = Array.isArray(history) ? history : [];
      setMessages(rows);
      setHasOlderMessages(rows.length === 100);
    } catch { setAiError(copy.aiHistoryError); }
  }

  async function uploadScreenshot(file) {
    if (!file) return;
    if (file.type !== 'image/png' || file.size > 3 * 1024 * 1024) { setUploadError(copy.screenshotType); return; }
    setUploading(true); setUploadError('');
    try { await uploadFinnTradeScreenshot(review.id, file); await refreshReview(); }
    catch { setUploadError(copy.screenshotError); }
    finally { setUploading(false); }
  }

  async function removeScreenshot() {
    setUploading(true); setUploadError('');
    try { await deleteFinnTradeScreenshot(review.id); await refreshReview(); }
    catch { setUploadError(copy.screenshotError); }
    finally { setUploading(false); }
  }

  async function analyze() {
    setAiBusy(true); setAiError('');
    try { const result = await analyzeFinnTradeReview(review.id); setAnalysis(result.analysis); setAnalysisStatus(result.status); if (result.status === 'unavailable' || result.status === 'failed') setAiError(result.reason || copy.aiError); }
    catch { setAiError(copy.aiError); }
    finally { setAiBusy(false); }
  }

  async function ask() {
    if (!question.trim()) return;
    setAiBusy(true); setAiError('');
    try { await askFinnTradeReview(review.id, question.trim()); setQuestion(''); const result = await fetchFinnTradeMessages(review.id); const rows = Array.isArray(result) ? result : []; setMessages(rows); setHasOlderMessages(rows.length === 100); }
    catch { setAiError(copy.aiError); }
    finally { setAiBusy(false); }
  }

  async function saveNote() {
    setSaving(true);
    setSaved(false);
    setNoteError(false);
    try {
      const updated = await saveFinnTradeReviewNote(review.id, note.slice(0, 2000));
      setSaved(true);
      onSaved(updated);
      try {
        const history = await fetchFinnTradeMessages(review.id);
        const rows = Array.isArray(history) ? history : [];
        setMessages(rows);
        setHasOlderMessages(rows.length === 100);
      } catch { setAiError(copy.aiHistoryError); }
    } catch (error) {
      console.error('Could not save FINN trade review note:', error);
      setNoteError(true);
    } finally {
      setSaving(false);
    }
  }

  async function loadOlderMessages() {
    if (loadingOlderMessages || !hasOlderMessages || !messages.length) return;
    setLoadingOlderMessages(true);
    setAiError('');
    try {
      const older = await fetchFinnTradeMessages(review.id, messages[0].id);
      const rows = Array.isArray(older) ? older : [];
      setMessages((current) => {
        const known = new Set(current.map((item) => item.id));
        return [...rows.filter((item) => !known.has(item.id)), ...current];
      });
      setHasOlderMessages(rows.length === 100);
    } catch { setAiError(copy.aiHistoryError); }
    finally { setLoadingOlderMessages(false); }
  }

  async function saveLesson(value) {
    setLessonBusy(true);
    setLessonError(false);
    setLessonSaved(false);
    try {
      const updated = await saveFinnTradeReviewLesson(review.id, value.trim());
      onSaved(updated);
      setLessonText(updated.lesson?.status === 'active' ? updated.lesson.lesson_text : '');
      setLessonSaved(true);
    } catch {
      setLessonError(true);
    } finally {
      setLessonBusy(false);
    }
  }

  return (
    <div className="min-w-0 max-w-full overflow-hidden rounded-[26px] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-black uppercase tracking-[0.18em] text-blue-600 dark:text-blue-400">{review.execution_environment === 'live' ? copy.live : copy.paper} · {isExchange ? review.exchange_name : sourceLabel(review.execution_sources, copy)} · #{review.id}</p>
          <h3 className="mt-1 text-2xl font-black text-slate-950 dark:text-white">{review.symbol}</h3>
          <p className="mt-1 text-sm text-slate-500">{formatDate(review.entry_at, locale)} → {formatDate(review.exit_at, locale)}</p>
          {isExchange && <p className="mt-2 inline-flex rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-800 dark:bg-amber-950/50 dark:text-amber-200">{copy.userConfirmedClosure}</p>}
        </div>
        <button type="button" onClick={onClose} className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-600 dark:border-slate-700 dark:text-slate-300">{copy.close}</button>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
        {metricCards.map(([label, value]) => (
          <div key={label} className="rounded-2xl bg-slate-50 p-4 dark:bg-slate-900"><p className="text-xs font-medium text-slate-500">{label}</p><p className="mt-1 font-black text-slate-900 dark:text-white">{value}</p></div>
        ))}
      </div>
      <p className="mt-2 text-xs text-slate-500">{isDerivative ? copy.derivativeResultNote : isExchange ? copy.exchangeResultNote : isPaper ? copy.paperResultNote : copy.resultNote}</p>

      <div className="mt-7 grid gap-5">
        <div className="min-w-0 break-words rounded-2xl border border-slate-200 p-5 dark:border-slate-800">
          <h4 className="flex items-center gap-2 text-sm font-black text-slate-900 dark:text-white"><FileText size={17} /> {originalPlanVerified ? copy.plan : plan ? copy.planUnverified : copy.plan}</h4>
          {plan ? <><PlanFacts plan={plan} copy={copy} />{!originalPlanVerified && <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">{copy.planUnverifiedHint}</p>}</> : <p className="mt-3 text-sm text-slate-500">{isExchange ? copy.externalNoPlan : copy.noPlan}</p>}
        </div>
        <div className="min-w-0 rounded-2xl border border-slate-200 p-5 dark:border-slate-800">
          <h4 className="text-sm font-black text-slate-900 dark:text-white">{copy.executionEvidence}</h4>
          {isExchange ? <ExecutionTimeline fills={fills} copy={copy} locale={locale} /> : chartState === 'ready' && chart ? <TradeChart chart={chart} copy={copy} locale={locale} /> : <p className="mt-2 text-xs leading-relaxed text-slate-500">{chartState === 'loading' ? copy.loading : copy.chartFallback}</p>}
          <ol className="mt-4 space-y-2">
            {fills.map((fill, index) => <li key={isDerivative ? `${fill.derivative_execution_id}-${fill.role}-${index}` : isExchange ? fill.exchange_fill_id : fill.ledger_id} className="flex items-center gap-3 rounded-xl bg-slate-50 px-3 py-2 text-xs dark:bg-slate-900">
              <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${fill.side === 'buy' ? 'bg-blue-100 text-blue-700' : 'bg-amber-100 text-amber-700'}`}>{fill.side === 'buy' ? <ArrowDownRight size={16} /> : <ArrowUpRight size={16} />}</span>
              <span className="min-w-0 flex-1"><strong>{fill.side === 'buy' ? copy.buy : copy.sell} {fill.qty} {isDerivative ? copy.derivativeContracts : review.symbol}</strong><br /><span className="text-slate-500">{formatDate(fill.at, locale)}{isDerivative && fill.role ? ` · ${copy.derivativeRole?.[fill.role] || fill.role}` : ''}</span></span>
              <span className="font-bold">{isExchange ? formatQuote(fill.price_quote, fill.quote_currency, locale) : fill.price_eur ? formatMoney(fill.price_eur, locale, 4) : formatMoney(number(fill.cash_eur) / number(fill.qty), locale, 4)}</span>
            </li>)}
          </ol>
        </div>
      </div>

      <div className="mt-5 rounded-2xl border border-slate-200 p-5 dark:border-slate-800">
        <h4 className="text-sm font-black text-slate-900 dark:text-white">{copy.screenshotTitle}</h4>
        <p className="mt-2 text-xs text-slate-500">{copy.screenshotHint}</p>
        {imageUrl && <img src={imageUrl} alt={copy.screenshotAlt} className="mt-3 max-h-96 max-w-full rounded-xl border border-slate-200 object-contain dark:border-slate-700" />}
        <div className="mt-3 flex flex-wrap items-center gap-2"><label className="cursor-pointer rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold text-white">{uploading ? copy.loading : copy.screenshotUpload}<input type="file" accept="image/png" disabled={uploading} onChange={(event) => uploadScreenshot(event.target.files?.[0])} className="sr-only" /></label>{review.has_screenshot && <button type="button" onClick={removeScreenshot} disabled={uploading} className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold dark:border-slate-700">{copy.screenshotRemove}</button>}</div>
        {uploadError && <p role="alert" className="mt-2 text-xs text-red-600">{uploadError}</p>}
      </div>

      <div className="mt-5 rounded-2xl border border-slate-200 p-5 dark:border-slate-800">
        <label htmlFor={`trade-note-${review.id}`} className="text-sm font-black text-slate-900 dark:text-white">{copy.note}</label>
        <textarea id={`trade-note-${review.id}`} value={note} onChange={(event) => { setNote(event.target.value); setSaved(false); }} maxLength={2000} rows={3} placeholder={copy.notePlaceholder} className="mt-3 w-full rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-900 outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
        <p className="mt-1 text-xs text-slate-500">{copy.noteResetHint}</p>
        <div className="mt-2 flex items-center gap-3"><button type="button" onClick={saveNote} disabled={saving || note === (review.note || '')} className="rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold text-white disabled:opacity-50">{saving ? copy.loading : copy.saveNote}</button>{saved && <span className="text-xs text-emerald-600">{copy.saved}</span>}{noteError && <span role="alert" className="text-xs text-red-600">{copy.noteError}</span>}</div>
      </div>

      <div className="mt-5 rounded-2xl border border-slate-200 p-5 dark:border-slate-800">
        <label htmlFor={`trade-lesson-${review.id}`} className="text-sm font-black text-slate-900 dark:text-white">{copy.lessonTitle}</label>
        <p className="mt-2 text-xs text-slate-500">{copy.lessonHint}</p>
        <textarea id={`trade-lesson-${review.id}`} value={lessonText} onChange={(event) => { setLessonText(event.target.value); setLessonSaved(false); }} maxLength={500} rows={2} placeholder={copy.lessonPlaceholder} className="mt-3 w-full rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-900 outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
        {analysis?.suggested_lesson && <div className="mt-3 rounded-xl bg-blue-50 p-3 text-xs text-blue-950 dark:bg-blue-950/40 dark:text-blue-100"><strong>{copy.lessonSuggestion}</strong><p className="mt-1">{analysis.suggested_lesson}</p><button type="button" onClick={() => { setLessonText(analysis.suggested_lesson); setLessonSaved(false); }} className="mt-2 font-bold underline">{copy.lessonUseSuggestion}</button></div>}
        {review.lesson?.status === 'active' && <p className="mt-2 text-xs text-emerald-700 dark:text-emerald-300">{copy.lessonConfirmed.replace('{date}', formatDate(review.lesson.confirmed_at, locale))}</p>}
        {review.lesson?.status === 'active' && review.lesson.evidence_revision !== review.input_revision && <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">{copy.lessonOlderEvidence}</p>}
        <div className="mt-3 flex flex-wrap items-center gap-3"><button type="button" onClick={() => saveLesson(lessonText)} disabled={lessonBusy || !lessonText.trim() || (lessonText.trim() === (review.lesson?.status === 'active' ? review.lesson.lesson_text : '') && review.lesson?.evidence_revision === review.input_revision)} className="rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold text-white disabled:opacity-50">{lessonBusy ? copy.loading : copy.lessonSave}</button>{review.lesson?.status === 'active' && <button type="button" onClick={() => saveLesson('')} disabled={lessonBusy} className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-slate-600 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300">{copy.lessonWithdraw}</button>}{lessonSaved && <span className="text-xs text-emerald-600">{copy.saved}</span>}{lessonError && <span role="alert" className="text-xs text-red-600">{copy.lessonError}</span>}</div>
      </div>

      <div className="mt-5 rounded-2xl bg-[#111f3c] p-5 text-white">
        <h4 className="flex items-center gap-2 text-lg font-black"><Brain size={19} /> {copy.aiTitle}</h4>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-blue-100">{copy.aiIntro}</p>
        {analysis ? <div className="mt-4 space-y-3 text-sm"><p className="font-semibold">{analysis.summary}</p>{analysis.prior_lesson && <div className="rounded-xl border border-blue-300/30 bg-blue-300/10 p-3"><p className="text-xs font-bold uppercase tracking-wide text-blue-200">{copy.priorLessonLabel.replace('{id}', String(analysis.prior_lesson.review_id))}</p><p className="mt-1">{analysis.prior_lesson.lesson_text}</p><p className="mt-2 text-xs text-blue-200">{copy.priorLessonConfirmed.replace('{date}', formatDate(analysis.prior_lesson.confirmed_at, locale))}</p>{analysis.prior_lesson.comparison && <p className="mt-2 text-xs text-blue-100">{analysis.prior_lesson.comparison}</p>}</div>}<ul className="space-y-2">{analysis.observations?.map((item, index) => <li key={index} className="rounded-xl border border-white/20 p-3">{item.text}<small className="mt-1 block text-blue-200">{copy.aiEvidence}: {item.evidence_ids?.join(', ')}</small></li>)}</ul><p className="text-blue-200">{copy.aiUncertainty}: {analysis.uncertainty}</p><p>{analysis.question}</p></div> : <p className="mt-4 text-sm text-blue-200">{analysisStatus === 'running' ? copy.aiRunning : copy.aiPending} {copy.aiQueueHint}</p>}
        <button type="button" onClick={analyze} disabled={aiBusy || analysisStatus === 'running'} className="mt-4 rounded-xl bg-white px-4 py-2 text-xs font-bold text-blue-950 disabled:opacity-50">{aiBusy ? copy.loading : copy.aiRefresh}</button>
        {aiError && <p role="alert" className="mt-2 text-xs text-rose-200">{aiError}</p>}
        <div className="mt-5 border-t border-white/20 pt-4"><h5 className="text-sm font-bold">{copy.aiDialogue}</h5><p className="mt-1 text-xs text-blue-200">{copy.aiDialogueHint}</p>{hasOlderMessages && <button type="button" onClick={loadOlderMessages} disabled={loadingOlderMessages} className="mt-3 rounded-lg border border-white/30 px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50">{loadingOlderMessages ? copy.loading : copy.aiLoadOlder}</button>}<div className="mt-3 max-h-60 space-y-2 overflow-auto">{messages.map((message) => { let structured; try { structured = message.role === 'finn' ? JSON.parse(message.content) : null; } catch { structured = null; } return <div key={message.id} className="rounded-xl border border-white/20 p-3 text-sm"><div className="flex flex-wrap items-center gap-2"><strong>{message.role === 'finn' ? 'FINN' : copy.aiUserQuestion}:</strong>{message.is_current_evidence === false && <span className="rounded-full bg-amber-400/20 px-2 py-0.5 text-xs font-bold text-amber-100">{message.evidence_status === 'source_removed' ? copy.aiSourceRemoved : copy.aiOlderEvidence}</span>}</div>{structured ? <div className="mt-1 space-y-2"><span className="block">{structured.summary}</span>{structured.prior_lesson && <span className="block rounded-lg border border-blue-200/30 bg-blue-300/10 p-2"><strong>{copy.priorLessonLabel.replace('{id}', String(structured.prior_lesson.review_id))}</strong><span className="mt-1 block">{structured.prior_lesson.lesson_text}</span><small className="mt-1 block text-blue-200">{copy.priorLessonConfirmed.replace('{date}', formatDate(structured.prior_lesson.confirmed_at, locale))}</small>{structured.prior_lesson.comparison && <small className="mt-1 block text-blue-100">{structured.prior_lesson.comparison}</small>}</span>}{Array.isArray(structured.observations) && structured.observations.map((item, index) => <span key={index} className="block rounded-lg border border-white/15 p-2">{item.text}<small className="mt-1 block text-blue-200">{copy.aiEvidence}: {item.evidence_ids?.join(', ')}</small></span>)}<span className="block text-blue-200">{copy.aiUncertainty}: {structured.uncertainty}</span>{structured.question && <span className="block">{structured.question}</span>}</div> : message.content}</div>; })}</div><div className="mt-3 flex gap-2"><input value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={1000} placeholder={copy.aiQuestion} className="min-w-0 flex-1 rounded-xl border border-white/30 bg-white/10 px-3 py-2 text-sm text-white placeholder:text-blue-200" /><button type="button" onClick={ask} disabled={aiBusy || !question.trim()} className="rounded-xl bg-blue-500 px-4 py-2 text-xs font-bold disabled:opacity-50">{copy.aiAsk}</button></div></div>
      </div>
    </div>
  );
}

function ReflectionOverview({ weekly, copy, weeklySummary, rolloutDisabled, loading, error, openReview }) {
  const trades = number(weekly.trades);
  const analyzed = number(weekly.analyzed);
  const patterns = Array.isArray(weekly.patterns) ? weekly.patterns : [];
  const lessons = Array.isArray(weekly.confirmed_lesson_repetitions) ? weekly.confirmed_lesson_repetitions : [];
  const hasFindings = patterns.length > 0;

  return (
    <div className="rounded-[28px] border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-950 sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-black uppercase tracking-[0.22em] text-blue-600 dark:text-blue-400">{copy.weekPattern}</p>
          <h3 className="mt-2 text-xl font-black text-slate-950 dark:text-white">{copy.overviewTitle}</h3>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600 dark:text-slate-300">{copy.overviewDescription}</p>
        </div>
        {!loading && !error && !rolloutDisabled && <span className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-bold text-blue-700 dark:bg-blue-950/40 dark:text-blue-200">{weeklySummary}</span>}
      </div>
      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        {[[copy.overviewClosed, trades], [copy.overviewAnalyzed, analyzed], [copy.overviewWithPlan, number(weekly.plans)]].map(([label, value]) => (
          <div key={label} className="rounded-2xl bg-slate-50 px-4 py-4 dark:bg-slate-900">
            <span className="block text-2xl font-black text-slate-950 dark:text-white">{loading || error || rolloutDisabled ? '—' : value}</span>
            <span className="mt-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</span>
          </div>
        ))}
      </div>
      <div className="mt-6 border-t border-slate-100 pt-5 dark:border-slate-800">
        <h4 className="text-sm font-black text-slate-900 dark:text-white">{copy.overviewFindings}</h4>
        <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          {loading ? copy.loading : error ? copy.error : rolloutDisabled ? copy.rolloutDisabled : trades === 0 ? copy.weekNoTrades : !hasFindings ? copy.overviewNoFindings : copy.overviewEvidence}
        </p>
        {hasFindings && !rolloutDisabled && <div className="mt-4 grid gap-3 md:grid-cols-2">
          {patterns.map((pattern) => <div key={pattern.theme} className="rounded-2xl border border-slate-200 p-4 dark:border-slate-800">
            <strong className="text-sm text-slate-900 dark:text-white">{copy.themes?.[pattern.theme] || pattern.theme}</strong>
            <p className="mt-1 text-xs text-slate-500">{pattern.count} {pattern.count === 1 ? copy.weekTrade : copy.weekTrades}</p>
            {pattern.example && <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">{pattern.example}</p>}
            <p className="mt-2 text-xs text-slate-500">{pattern.basis === 'plan_record' ? copy.overviewPlanBasis : copy.overviewAnalysisBasis}</p>
            <div className="mt-3 flex flex-wrap gap-2">{pattern.review_ids.map((id) => <button key={id} type="button" onClick={() => openReview(id)} className="rounded-full bg-blue-50 px-2 py-1 text-xs font-bold text-blue-700 dark:bg-blue-950/40 dark:text-blue-200">#{id}</button>)}</div>
          </div>)}
        </div>}
        {lessons.map((pattern) => <div key={pattern.review_ids.join('-')} className="mt-4 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm dark:border-blue-900 dark:bg-blue-950/30">
          <strong className="text-slate-900 dark:text-white">{copy.weekLessonRepeat}</strong>
          <p className="mt-1 text-slate-800 dark:text-slate-100">{pattern.lesson_text}</p>
          <p className="mt-2 text-xs text-slate-500">{copy.weekLessonNote} · {pattern.count} {pattern.count === 1 ? copy.weekTrade : copy.weekTrades}</p>
          <div className="mt-2 flex flex-wrap gap-2">{pattern.review_ids.map((id) => <button key={id} type="button" onClick={() => openReview(id)} className="text-xs font-bold text-blue-600 underline">#{id}</button>)}</div>
        </div>)}
        {weekly.patterns_truncated && <p className="mt-3 text-xs text-amber-600">{copy.weekTruncated}</p>}
      </div>
    </div>
  );
}

export default function FinnTradeReviews() {
  const router = useRouter();
  const { t, locale } = useTranslation();
  const copy = t.pages.report.finn.tradeReviews;
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [weekly, setWeekly] = useState({ trades: 0, plans: 0, notes: 0 });
  const [excluded, setExcluded] = useState({});
  const [selected, setSelected] = useState(null);
  const [deepLinkLoading, setDeepLinkLoading] = useState(false);
  const [deepLinkError, setDeepLinkError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [rolloutDisabled, setRolloutDisabled] = useState(null);
  const [exchangeImports, setExchangeImports] = useState([]);
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState(false);
  const [syncingExchange, setSyncingExchange] = useState(null);
  const [importFillPage, setImportFillPage] = useState(null);
  const [importFillsLoadingMore, setImportFillsLoadingMore] = useState(false);
  const [selectedImportFills, setSelectedImportFills] = useState([]);
  const [closureConfirmed, setClosureConfirmed] = useState(false);
  const [sameAccountConfirmed, setSameAccountConfirmed] = useState(false);
  const [creatingExchangeReview, setCreatingExchangeReview] = useState(false);
  const [exchangeReviewError, setExchangeReviewError] = useState(false);
  const pairingKey = useRef(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const openRequest = useRef(0);
  const detailRef = useRef(null);
  const reviewIdParam = useSearchParams().get('trade_review_id');

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const result = await fetchFinnTradeReviews(50, 0);
      setRolloutDisabled(result?.status === 'disabled');
      setItems(Array.isArray(result?.items) ? result.items : []);
      setTotal(number(result?.total));
      setWeekly(result?.weekly || { trades: 0, plans: 0, notes: 0 });
      setExcluded(result?.excluded || {});
    } catch (loadError) {
      console.error('FINN trade reviews could not load:', loadError);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const loadImports = useCallback(async () => {
    setImportLoading(true);
    try {
      const result = await fetchFinnExchangeTradeImports();
      setExchangeImports(Array.isArray(result?.sources) ? result.sources : []);
      setImportError(false);
    } catch {
      setImportError(true);
    } finally {
      setImportLoading(false);
    }
  }, []);

  useEffect(() => {
    if (rolloutDisabled === false) loadImports();
    if (rolloutDisabled === true) {
      setExchangeImports([]);
      setImportFillPage(null);
      setImportError(false);
    }
  }, [loadImports, rolloutDisabled]);

  async function syncExchange(exchangeName) {
    setSyncingExchange(exchangeName);
    setImportError(false);
    try { await syncFinnExchangeTradeImport(exchangeName); setImportFillPage(null); await loadImports(); }
    catch { setImportError(true); }
    finally { setSyncingExchange(null); }
  }

  async function openImportFills(sourceId) {
    if (importFillPage?.source_id === sourceId) { setImportFillPage(null); return; }
    setImportError(false);
    try { setImportFillPage(await fetchFinnExchangeImportFills(sourceId)); }
    catch { setImportError(true); }
  }

  async function loadMoreImportFills() {
    if (!importFillPage?.next_cursor || importFillsLoadingMore) return;
    setImportFillsLoadingMore(true);
    try {
      const page = await fetchFinnExchangeImportFills(importFillPage.source_id, 50, importFillPage.next_cursor);
      setImportFillPage((current) => current?.source_id === page.source_id
        ? { ...page, items: [...(current.items || []), ...(page.items || [])] } : current);
    } catch { setImportError(true); }
    finally { setImportFillsLoadingMore(false); }
  }

  function toggleImportFill(fill, source) {
    if (fill.review_id) return;
    setSelectedImportFills((current) => current.some((item) => item.id === fill.id)
      ? current.filter((item) => item.id !== fill.id)
      : [...current, { ...fill, source_id: source.id, exchange_name: source.exchange_name }]);
    setClosureConfirmed(false);
    setSameAccountConfirmed(false);
    setExchangeReviewError(false);
    pairingKey.current = null;
  }

  async function createExchangeReview() {
    if (!pairingKey.current) pairingKey.current = crypto.randomUUID();
    setCreatingExchangeReview(true);
    setExchangeReviewError(false);
    try {
      const result = await createFinnExchangeTradeReview(
        selectedImportFills.map((fill) => fill.id), sameAccountConfirmed, pairingKey.current,
      );
      setSelectedImportFills([]);
      setClosureConfirmed(false);
      setSameAccountConfirmed(false);
      setImportFillPage(null);
      pairingKey.current = null;
      await Promise.all([load(), loadImports()]);
      router.replace(`/report?trade_review_id=${result.review_id}`, { scroll: false });
    } catch { setExchangeReviewError(true); }
    finally { setCreatingExchangeReview(false); }
  }

  useEffect(() => {
    if (selected) detailRef.current?.focus({ preventScroll: true });
  }, [selected?.id]);

  useEffect(() => {
    const rawId = reviewIdParam;
    setSelected(null);
    setDeepLinkError(false);
    if (!rawId || !/^\d{1,12}$/.test(rawId)) { setDeepLinkLoading(false); return; }
    const id = Number(rawId);
    const requestId = ++openRequest.current;
    setDeepLinkLoading(true);
    fetchFinnTradeReview(id).then((detail) => {
      if (requestId === openRequest.current) setSelected(detail);
    }).catch(() => {
      if (requestId === openRequest.current) setDeepLinkError(true);
    }).finally(() => {
      if (requestId === openRequest.current) setDeepLinkLoading(false);
    });
    return () => { openRequest.current += 1; };
  }, [reviewIdParam]);

  const weeklySummary = copy.weekSummary
    .replace('{trades}', String(number(weekly.trades)))
    .replace('{plans}', String(number(weekly.plans)))
    .replace('{notes}', String(number(weekly.notes)));
  const selectedSourceIds = new Set(selectedImportFills.map((fill) => fill.source_id));
  const selectedExchanges = new Set(selectedImportFills.map((fill) => fill.exchange_name));
  const hasBuy = selectedImportFills.some((fill) => fill.side === 'buy');
  const hasSell = selectedImportFills.some((fill) => fill.side === 'sell');
  const needsSameAccount = selectedSourceIds.size > 1;
  const canConfirmExchange = hasBuy && hasSell && selectedExchanges.size === 1 && closureConfirmed
    && (!needsSameAccount || sameAccountConfirmed);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const result = await fetchFinnTradeReviews(50, items.length);
      setItems((current) => [...current, ...(Array.isArray(result?.items) ? result.items : [])]);
      setTotal(number(result?.total));
      setWeekly(result?.weekly || weekly);
    } catch (loadError) {
      console.error('FINN trade review page could not load:', loadError);
      setError(true);
    } finally {
      setLoadingMore(false);
    }
  }

  function openReview(id) {
    if (selected?.id === id) {
      openRequest.current += 1;
      setSelected(null);
      router.replace('/report', { scroll: false });
      return;
    }
    setSelected(null);
    setDeepLinkLoading(true);
    router.replace(`/report?trade_review_id=${id}`, { scroll: false });
  }

  return (
    <section aria-labelledby="finn-trades-title" className="my-8 min-w-0 space-y-5">
      <div className="rounded-[28px] bg-[#111f3c] px-6 py-8 text-white sm:px-8">
        <p className="text-[11px] font-black uppercase tracking-[0.2em] text-blue-200">{copy.eyebrow}</p>
        <h2 id="finn-trades-title" className="mt-2 text-3xl font-black tracking-tight">{copy.title}</h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-blue-100">{copy.description}</p>
      </div>
      <ReflectionOverview weekly={weekly} copy={copy} weeklySummary={weeklySummary} rolloutDisabled={rolloutDisabled} loading={loading} error={error} openReview={openReview} />
      <div className="grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(260px,320px)_minmax(0,1fr)]">
      <div className="min-w-0 overflow-hidden rounded-[28px] border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
        <div className="border-b border-slate-100 px-6 py-5 dark:border-slate-800 sm:px-8">
          <h3 className="text-lg font-black text-slate-950 dark:text-white">{copy.dossiersTitle}</h3>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">{copy.dossiersDescription}</p>
        </div>
        <div className="px-6 py-6 sm:px-8">
          {rolloutDisabled === false && <details className="mb-5 rounded-xl border border-slate-200 text-xs dark:border-slate-800">
            <summary className="cursor-pointer px-4 py-3 font-black text-slate-900 dark:text-white">{copy.exchangeImportTitle}</summary>
            <div className="border-t border-slate-100 p-4 dark:border-slate-800">
            <p className="mb-4 rounded-xl bg-blue-50 px-4 py-3 leading-relaxed text-blue-900 dark:bg-blue-950/40 dark:text-blue-100">{copy.limitedHistory}</p>
            <p className="mt-1 leading-relaxed text-slate-600 dark:text-slate-300">{copy.exchangeImportIntro}</p>
            {importLoading && <p role="status" className="mt-2 text-slate-500">{copy.loading}</p>}
            {importError && <p role="alert" className="mt-2 text-red-600">{copy.exchangeImportError}</p>}
            {!importLoading && exchangeImports.length === 0 && <p className="mt-2 text-slate-500">{copy.exchangeImportEmpty}</p>}
            {exchangeImports.map((source, index) => <div key={`${source.exchange_name}-${source.id || index}`} className="mt-3 rounded-lg bg-slate-50 p-3 dark:bg-slate-900">
              <div className="flex flex-wrap items-center justify-between gap-2"><strong className="capitalize">{source.exchange_name}</strong><button type="button" onClick={() => syncExchange(source.exchange_name)} disabled={Boolean(syncingExchange)} className="rounded-lg border border-blue-400 px-2 py-1 font-bold text-blue-700 disabled:opacity-50 dark:text-blue-300">{syncingExchange === source.exchange_name ? copy.loading : copy.exchangeImportSync}</button></div>
              <p className="mt-1 text-slate-600 dark:text-slate-300">{copy.exchangeImportStates?.[source.status] || source.status} · {source.imported_fills || 0} {copy.exchangeImportFills}</p>
              {source.imported_movements > 0 && <p className="mt-1 text-slate-500">{source.imported_movements} {copy.exchangeImportMovements}{source.unsupported_movements > 0 ? ` · ${source.unsupported_movements} ${copy.exchangeImportUnsupported}` : ''}</p>}
              <p className="mt-1 text-slate-500">{copy.exchangeImportLimits?.[source.history_limit]}</p>
              {source.coverage_through_at && <p className="text-slate-500">{copy.exchangeImportThrough}: {formatDate(source.coverage_through_at, locale)}</p>}
              {source.last_error_code && <p className="text-amber-700 dark:text-amber-300">{copy.exchangeImportError}: {source.last_error_code}</p>}
              {source.id && <button type="button" onClick={() => openImportFills(source.id)} className="mt-2 font-bold text-blue-600 underline dark:text-blue-300">{importFillPage?.source_id === source.id ? copy.exchangeImportHideFills : copy.exchangeImportShowFills}</button>}
              {importFillPage?.source_id === source.id && <div className="mt-2 max-h-64 space-y-1 overflow-auto"><p className="text-slate-500">{copy.exchangeImportEvidenceOnly}</p>{importFillPage.items?.map((fill) => <label key={fill.id} className={`flex items-start gap-2 rounded border border-slate-200 p-2 dark:border-slate-700 ${fill.review_id ? 'opacity-60' : 'cursor-pointer'}`}><input type="checkbox" className="mt-0.5" checked={selectedImportFills.some((item) => item.id === fill.id)} onChange={() => toggleImportFill(fill, source)} disabled={Boolean(fill.review_id)} /><span><strong>{fill.side === 'buy' ? copy.buy : copy.sell} {fill.qty} {fill.symbol}</strong> · {formatQuote(fill.cost_quote, fill.quote_currency, locale)}<br />{formatDate(fill.traded_at, locale)}{fill.review_id && <span className="block text-slate-500">{copy.exchangeAlreadyReviewed} #{fill.review_id}</span>}</span></label>)}{importFillPage.next_cursor && <button type="button" onClick={loadMoreImportFills} disabled={importFillsLoadingMore} className="font-bold text-blue-600 underline disabled:opacity-50">{importFillsLoadingMore ? copy.loading : copy.exchangeImportLoadMore}</button>}</div>}
            </div>)}
            {selectedImportFills.length > 0 && <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50 p-4 text-slate-800 dark:border-blue-900 dark:bg-blue-950/30 dark:text-slate-100">
              <h4 className="font-black">{copy.exchangePairTitle}</h4>
              <p className="mt-1">{copy.exchangePairSelected.replace('{count}', String(selectedImportFills.length))}</p>
              <p className="mt-1 text-slate-600 dark:text-slate-300">{copy.exchangePairHint}</p>
              <div className="mt-2 flex flex-wrap gap-1">{selectedImportFills.map((fill) => <button key={fill.id} type="button" onClick={() => toggleImportFill(fill, { id: fill.source_id, exchange_name: fill.exchange_name })} className="rounded-full border border-blue-300 px-2 py-1 text-[11px] dark:border-blue-700">{fill.side === 'buy' ? copy.buy : copy.sell} {fill.qty} {fill.symbol} · {formatDate(fill.traded_at, locale)} ×</button>)}</div>
              {needsSameAccount && <label className="mt-3 flex items-start gap-2"><input type="checkbox" className="mt-0.5" checked={sameAccountConfirmed} onChange={(event) => setSameAccountConfirmed(event.target.checked)} /><span>{copy.exchangeSameAccountConfirm}</span></label>}
              <label className="mt-3 flex items-start gap-2"><input type="checkbox" className="mt-0.5" checked={closureConfirmed} onChange={(event) => setClosureConfirmed(event.target.checked)} /><span>{copy.exchangeClosureConfirm}</span></label>
              {(!hasBuy || !hasSell) && <p className="mt-2 text-amber-700 dark:text-amber-300">{copy.exchangeNeedBuySell}</p>}
              {selectedExchanges.size > 1 && <p className="mt-2 text-amber-700 dark:text-amber-300">{copy.exchangeOneExchange}</p>}
              {exchangeReviewError && <p role="alert" className="mt-2 text-red-700 dark:text-red-300">{copy.exchangeCreateError}</p>}
              <button type="button" disabled={!canConfirmExchange || creatingExchangeReview} onClick={createExchangeReview} className="mt-3 rounded-lg bg-blue-600 px-4 py-2 font-bold text-white disabled:opacity-50">{creatingExchangeReview ? copy.loading : copy.exchangeCreateReview}</button>
            </div>}
            {exchangeImports.some((source) => source.exchange_name === 'bybit') && <BybitDerivativeReviews copy={copy} locale={locale} onCreated={async (reviewId) => {
              await load();
              router.replace(`/report?trade_review_id=${reviewId}`, { scroll: false });
            }} />}
            </div>
          </details>}
          {deepLinkLoading && <p role="status" className="mb-4 text-sm text-slate-500">{copy.loading}</p>}
          {deepLinkError && <p role="alert" className="mb-4 text-sm text-red-600">{copy.error}</p>}
          {loading ? <p role="status" className="flex items-center gap-2 text-sm text-slate-500"><Loader2 size={16} className="animate-spin" /> {copy.loading}</p> : error ? <p role="alert" className="text-sm text-red-600">{copy.error}</p> : (
            <>
              <div className="mb-4 flex items-center justify-between gap-3"><h3 className="text-sm font-black text-slate-900 dark:text-white">{copy.all} <span className="ml-1 text-slate-400">{total}</span></h3><button type="button" onClick={load} className="flex items-center gap-1.5 text-xs font-bold text-blue-600"><RefreshCw size={14} /> {copy.refresh}</button></div>
              {items.length === 0 ? <p className="rounded-xl bg-slate-50 p-5 text-sm text-slate-600 dark:bg-slate-900 dark:text-slate-300">{rolloutDisabled ? copy.rolloutDisabled : copy.empty}</p> : <div className="grid gap-2">{items.map((item) => <button key={item.id} type="button" onClick={() => openReview(item.id)} className={`flex items-center gap-3 rounded-2xl border p-4 text-left transition hover:border-blue-400 ${selected?.id === item.id ? 'border-blue-500 bg-blue-50/50 dark:bg-blue-950/20' : 'border-slate-200 dark:border-slate-800'}`}>
                <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${item.pnl_eur_before_fees == null ? 'bg-blue-50 text-blue-600' : number(item.pnl_eur_before_fees) >= 0 ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'}`}>{item.pnl_eur_before_fees == null ? <FileText size={19} /> : number(item.pnl_eur_before_fees) >= 0 ? <ArrowUpRight size={19} /> : <ArrowDownRight size={19} />}</span>
                <span className="min-w-0 flex-1"><strong className="block text-sm text-slate-900 dark:text-white">{item.symbol} · {item.execution_environment === 'live' ? copy.live : copy.paper}</strong><span className="block text-xs text-slate-500">{isExchangeReview(item.origin) ? item.exchange_name : sourceLabel(item.execution_sources, copy)} · #{item.id}<br />{formatDate(item.exit_at, locale)}{isExchangeReview(item.origin) && <><br />{copy.userConfirmedClosure}</>}</span></span>
                <span className="text-right"><strong className="block text-sm text-slate-900 dark:text-white">{item.pnl_eur_before_fees == null ? copy.exchangeResultUnavailable : formatMoney(item.pnl_eur_before_fees, locale)}</strong><span className="text-xs text-blue-600">{copy.open}</span></span><ChevronRight size={15} className="text-slate-400" />
              </button>)}</div>}
              {items.length < total && <button type="button" onClick={loadMore} disabled={loadingMore} className="mt-4 rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-blue-600 disabled:opacity-50 dark:border-slate-700">{loadingMore ? copy.loading : copy.more}</button>}
              {(number(excluded.legacy_or_ambiguous) > 0 || number(excluded.inconsistent) > 0) && <p className="mt-4 text-xs text-amber-700 dark:text-amber-300">{copy.excluded}</p>}

            </>
          )}
        </div>
      </div>
      <div ref={detailRef} tabIndex={-1} className="min-w-0 outline-none">
        {selected ? <ReviewDetail key={selected.id} review={selected} onClose={() => { openRequest.current += 1; setSelected(null); router.replace('/report', { scroll: false }); }} onSaved={async (updated) => { setSelected((current) => current?.id === updated.id ? updated : current); await load(); }} copy={copy} locale={locale} /> : <div className="rounded-[26px] border border-dashed border-slate-300 bg-white p-8 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-950">{deepLinkLoading ? copy.loading : deepLinkError ? copy.error : copy.selectHint || copy.open}</div>}
      </div>
      </div>
    </section>
  );
}
