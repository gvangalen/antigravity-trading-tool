'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowDownRight, ArrowUpRight, Brain, ChevronRight, FileText, Loader2, RefreshCw } from 'lucide-react';
import { useTranslation } from '@/app/providers/I18nProvider';
import { fetchFinnTradeReview, fetchFinnTradeReviews, saveFinnTradeReviewNote, fetchFinnTradeChart, analyzeFinnTradeReview, fetchFinnTradeMessages, askFinnTradeReview, uploadFinnTradeScreenshot, deleteFinnTradeScreenshot, fetchFinnTradeScreenshot } from '@/lib/api/botApi';

const number = (value) => Number(value) || 0;

function formatMoney(value, locale, digits = 2) {
  return new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR', maximumFractionDigits: digits }).format(number(value));
}

function formatDate(value, locale) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

function sourceLabel(sources, copy) {
  const value = Array.isArray(sources) ? sources : [];
  return value.map((source) => source === 'manual' ? copy.manual : copy.bot).join(' + ');
}

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

function ReviewDetail({ review, onClose, onSaved, copy, locale }) {
  const [note, setNote] = useState(review.note || '');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [noteError, setNoteError] = useState(false);
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
  const [question, setQuestion] = useState('');
  const fills = Array.isArray(review.fills) ? review.fills : [];
  const plan = review.plan_snapshot && typeof review.plan_snapshot === 'object' ? review.plan_snapshot : null;

  useEffect(() => {
    let active = true;
    fetchFinnTradeChart(review.id).then((result) => { if (active) { setChart(result.chart); setChartState(result.status); } }).catch(() => { if (active) setChartState('failed'); });
    fetchFinnTradeMessages(review.id).then((result) => { if (active) setMessages(Array.isArray(result) ? result : []); }).catch(() => {});
    return () => { active = false; };
  }, [review.id]);

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
    if (!['pending', 'running'].includes(analysisStatus)) return undefined;
    const timer = window.setInterval(() => {
      fetchFinnTradeReview(review.id).then((fresh) => {
        setAnalysis(fresh.analysis_json || null);
        setAnalysisStatus(fresh.analysis_status);
      }).catch(() => {});
    }, 15000);
    return () => window.clearInterval(timer);
  }, [review.id, analysisStatus]);

  useEffect(() => {
    let active = true;
    let url;
    setImageUrl(null);
    if (review.has_screenshot) fetchFinnTradeScreenshot(review.id).then((blob) => { url = URL.createObjectURL(blob); if (active) setImageUrl(url); else URL.revokeObjectURL(url); }).catch(() => { if (active) setUploadError(copy.screenshotError); });
    return () => { active = false; if (url) URL.revokeObjectURL(url); };
  }, [review.id, review.screenshot_sha256, review.has_screenshot, copy.screenshotError]);

  async function refreshReview() { const updated = await fetchFinnTradeReview(review.id); setMessages([]); onSaved(updated); }

  async function uploadScreenshot(file) {
    if (!file) return;
    if (file.type !== 'image/png' || file.size > 3 * 1024 * 1024) { setUploadError(copy.screenshotType); return; }
    if (messages.length > 0 && !window.confirm(copy.resetConfirm)) return;
    setUploading(true); setUploadError('');
    try { await uploadFinnTradeScreenshot(review.id, file); await refreshReview(); }
    catch { setUploadError(copy.screenshotError); }
    finally { setUploading(false); }
  }

  async function removeScreenshot() {
    if (messages.length > 0 && !window.confirm(copy.resetConfirm)) return;
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
    try { await askFinnTradeReview(review.id, question.trim()); setQuestion(''); const result = await fetchFinnTradeMessages(review.id); setMessages(Array.isArray(result) ? result : []); }
    catch { setAiError(copy.aiError); }
    finally { setAiBusy(false); }
  }

  async function saveNote() {
    if (messages.length > 0 && !window.confirm(copy.resetConfirm)) return;
    setSaving(true);
    setSaved(false);
    setNoteError(false);
    try {
      const updated = await saveFinnTradeReviewNote(review.id, note.slice(0, 2000));
      setSaved(true);
      setMessages([]);
      onSaved(updated);
    } catch (error) {
      console.error('Could not save FINN trade review note:', error);
      setNoteError(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-w-0 max-w-full overflow-hidden rounded-[26px] border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-black uppercase tracking-[0.18em] text-blue-600 dark:text-blue-400">{review.execution_environment === 'live' ? copy.live : copy.paper} · {sourceLabel(review.execution_sources, copy)} · #{review.id}</p>
          <h3 className="mt-1 text-2xl font-black text-slate-950 dark:text-white">{review.symbol}</h3>
          <p className="mt-1 text-sm text-slate-500">{formatDate(review.entry_at, locale)} → {formatDate(review.exit_at, locale)}</p>
        </div>
        <button type="button" onClick={onClose} className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-600 dark:border-slate-700 dark:text-slate-300">{copy.close}</button>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
        {[[copy.entry, formatMoney(review.entry_price_eur, locale, 4)], [copy.exit, formatMoney(review.exit_price_eur, locale, 4)], [copy.quantity, String(review.entry_qty)], [copy.result, formatMoney(review.pnl_eur_before_fees, locale)]].map(([label, value]) => (
          <div key={label} className="rounded-2xl bg-slate-50 p-4 dark:bg-slate-900"><p className="text-xs font-medium text-slate-500">{label}</p><p className="mt-1 font-black text-slate-900 dark:text-white">{value}</p></div>
        ))}
      </div>
      <p className="mt-2 text-xs text-slate-500">{copy.resultNote}</p>

      <div className="mt-7 grid gap-5">
        <div className="min-w-0 break-words rounded-2xl border border-slate-200 p-5 dark:border-slate-800">
          <h4 className="flex items-center gap-2 text-sm font-black text-slate-900 dark:text-white"><FileText size={17} /> {copy.plan}</h4>
          {plan ? <PlanFacts plan={plan} copy={copy} /> : <p className="mt-3 text-sm text-slate-500">{copy.noPlan}</p>}
        </div>
        <div className="min-w-0 rounded-2xl border border-slate-200 p-5 dark:border-slate-800">
          <h4 className="text-sm font-black text-slate-900 dark:text-white">{copy.executionEvidence}</h4>
          {chartState === 'ready' && chart ? <TradeChart chart={chart} copy={copy} locale={locale} /> : <p className="mt-2 text-xs leading-relaxed text-slate-500">{chartState === 'loading' ? copy.loading : copy.chartFallback}</p>}
          <ol className="mt-4 space-y-2">
            {fills.map((fill) => <li key={fill.ledger_id} className="flex items-center gap-3 rounded-xl bg-slate-50 px-3 py-2 text-xs dark:bg-slate-900">
              <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${fill.side === 'buy' ? 'bg-blue-100 text-blue-700' : 'bg-amber-100 text-amber-700'}`}>{fill.side === 'buy' ? <ArrowDownRight size={16} /> : <ArrowUpRight size={16} />}</span>
              <span className="min-w-0 flex-1"><strong>{fill.side === 'buy' ? copy.buy : copy.sell} {fill.qty} {review.symbol}</strong><br /><span className="text-slate-500">{formatDate(fill.at, locale)}</span></span>
              <span className="font-bold">{fill.price_eur ? formatMoney(fill.price_eur, locale, 4) : formatMoney(number(fill.cash_eur) / number(fill.qty), locale, 4)}</span>
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

      <div className="mt-5 rounded-2xl bg-[#111f3c] p-5 text-white">
        <h4 className="flex items-center gap-2 text-lg font-black"><Brain size={19} /> {copy.aiTitle}</h4>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-blue-100">{copy.aiIntro}</p>
        {analysis ? <div className="mt-4 space-y-3 text-sm"><p className="font-semibold">{analysis.summary}</p><ul className="space-y-2">{analysis.observations?.map((item, index) => <li key={index} className="rounded-xl border border-white/20 p-3">{item.text}<small className="mt-1 block text-blue-200">{copy.aiEvidence}: {item.evidence_ids?.join(', ')}</small></li>)}</ul><p className="text-blue-200">{copy.aiUncertainty}: {analysis.uncertainty}</p><p>{analysis.question}</p></div> : <p className="mt-4 text-sm text-blue-200">{analysisStatus === 'running' ? copy.aiRunning : copy.aiPending} {copy.aiQueueHint}</p>}
        <button type="button" onClick={analyze} disabled={aiBusy || analysisStatus === 'running'} className="mt-4 rounded-xl bg-white px-4 py-2 text-xs font-bold text-blue-950 disabled:opacity-50">{aiBusy ? copy.loading : copy.aiRefresh}</button>
        {aiError && <p role="alert" className="mt-2 text-xs text-rose-200">{aiError}</p>}
        <div className="mt-5 border-t border-white/20 pt-4"><h5 className="text-sm font-bold">{copy.aiDialogue}</h5><p className="mt-1 text-xs text-blue-200">{copy.aiDialogueHint}</p><div className="mt-3 max-h-60 space-y-2 overflow-auto">{messages.map((message) => { let structured; try { structured = message.role === 'finn' ? JSON.parse(message.content) : null; } catch { structured = null; } return <p key={message.id} className="rounded-xl border border-white/20 p-3 text-sm"><strong>{message.role === 'finn' ? 'FINN' : copy.note}:</strong> {structured ? <span className="mt-1 block space-y-2"><span className="block">{structured.summary}</span>{Array.isArray(structured.observations) && structured.observations.map((item, index) => <span key={index} className="block rounded-lg border border-white/15 p-2">{item.text}<small className="mt-1 block text-blue-200">{copy.aiEvidence}: {item.evidence_ids?.join(', ')}</small></span>)}<span className="block text-blue-200">{copy.aiUncertainty}: {structured.uncertainty}</span>{structured.question && <span className="block">{structured.question}</span>}</span> : message.content}</p>; })}</div><div className="mt-3 flex gap-2"><input value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={1000} placeholder={copy.aiQuestion} className="min-w-0 flex-1 rounded-xl border border-white/30 bg-white/10 px-3 py-2 text-sm text-white placeholder:text-blue-200" /><button type="button" onClick={ask} disabled={aiBusy || !question.trim()} className="rounded-xl bg-blue-500 px-4 py-2 text-xs font-bold disabled:opacity-50">{copy.aiAsk}</button></div></div>
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
  const [rolloutDisabled, setRolloutDisabled] = useState(false);
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
    <section aria-labelledby="finn-trades-title" className="my-8 grid min-w-0 items-start gap-5 xl:grid-cols-[minmax(260px,320px)_minmax(0,1fr)]">
      <div className="min-w-0 overflow-hidden rounded-[28px] border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
        <div className="bg-[#111f3c] px-6 py-7 text-white sm:px-8">
          <p className="text-[11px] font-black uppercase tracking-[0.2em] text-blue-200">{copy.eyebrow}</p>
          <h2 id="finn-trades-title" className="mt-2 text-2xl font-black tracking-tight">{copy.title}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-blue-100">{copy.description}</p>
        </div>
        <div className="px-6 py-6 sm:px-8">
          <div className="mb-5 rounded-xl bg-blue-50 px-4 py-3 text-xs leading-relaxed text-blue-900 dark:bg-blue-950/40 dark:text-blue-100">{copy.limitedHistory}</div>
          {deepLinkLoading && <p role="status" className="mb-4 text-sm text-slate-500">{copy.loading}</p>}
          {deepLinkError && <p role="alert" className="mb-4 text-sm text-red-600">{copy.error}</p>}
          {loading ? <p role="status" className="flex items-center gap-2 text-sm text-slate-500"><Loader2 size={16} className="animate-spin" /> {copy.loading}</p> : error ? <p role="alert" className="text-sm text-red-600">{copy.error}</p> : (
            <>
              <div className="mb-4 flex items-center justify-between gap-3"><h3 className="text-sm font-black text-slate-900 dark:text-white">{copy.all} <span className="ml-1 text-slate-400">{total}</span></h3><button type="button" onClick={load} className="flex items-center gap-1.5 text-xs font-bold text-blue-600"><RefreshCw size={14} /> {copy.refresh}</button></div>
              {items.length === 0 ? <p className="rounded-xl bg-slate-50 p-5 text-sm text-slate-600 dark:bg-slate-900 dark:text-slate-300">{rolloutDisabled ? copy.rolloutDisabled : copy.empty}</p> : <div className="grid gap-2">{items.map((item) => <button key={item.id} type="button" onClick={() => openReview(item.id)} className={`flex items-center gap-3 rounded-2xl border p-4 text-left transition hover:border-blue-400 ${selected?.id === item.id ? 'border-blue-500 bg-blue-50/50 dark:bg-blue-950/20' : 'border-slate-200 dark:border-slate-800'}`}>
                <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${number(item.pnl_eur_before_fees) >= 0 ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'}`}>{number(item.pnl_eur_before_fees) >= 0 ? <ArrowUpRight size={19} /> : <ArrowDownRight size={19} />}</span>
                <span className="min-w-0 flex-1"><strong className="block text-sm text-slate-900 dark:text-white">{item.symbol} · {item.execution_environment === 'live' ? copy.live : copy.paper}</strong><span className="block text-xs text-slate-500">{sourceLabel(item.execution_sources, copy)} · #{item.id}<br />{formatDate(item.exit_at, locale)}</span></span>
                <span className="text-right"><strong className="block text-sm text-slate-900 dark:text-white">{formatMoney(item.pnl_eur_before_fees, locale)}</strong><span className="text-xs text-blue-600">{copy.open}</span></span><ChevronRight size={15} className="text-slate-400" />
              </button>)}</div>}
              {items.length < total && <button type="button" onClick={loadMore} disabled={loadingMore} className="mt-4 rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-blue-600 disabled:opacity-50 dark:border-slate-700">{loadingMore ? copy.loading : copy.more}</button>}
              {(number(excluded.legacy_or_ambiguous) > 0 || number(excluded.inconsistent) > 0) && <p className="mt-4 text-xs text-amber-700 dark:text-amber-300">{copy.excluded}</p>}
              <div className="mt-6 border-t border-slate-100 pt-5 dark:border-slate-800"><p className="text-xs font-black uppercase tracking-[0.16em] text-blue-600 dark:text-blue-400">{copy.weekPattern}</p><p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{rolloutDisabled ? copy.rolloutDisabled : number(weekly.trades) > 0 ? weeklySummary : copy.weekNoTrades}</p>{number(weekly.trades) > 0 && <p className="mt-1 text-xs text-slate-500">{number(weekly.analyzed)} {copy.weekAnalyzed} · {number(weekly.pending)} {copy.weekPending} · {number(weekly.unavailable)} {copy.weekUnavailable}</p>}{Array.isArray(weekly.patterns) && weekly.patterns.map((pattern) => <div key={pattern.theme} className="mt-3 rounded-xl bg-slate-50 p-3 text-xs dark:bg-slate-900"><strong>{copy.themes?.[pattern.theme] || pattern.theme}</strong> · {pattern.count} {pattern.count === 1 ? copy.weekTrade : copy.weekTrades}<div className="mt-1 flex flex-wrap gap-2">{pattern.review_ids.map((id) => <button key={id} type="button" onClick={() => openReview(id)} className="font-bold text-blue-600 underline">#{id}</button>)}</div></div>)}{weekly.patterns_truncated && <p className="mt-2 text-xs text-amber-600">{copy.weekTruncated}</p>}</div>
            </>
          )}
        </div>
      </div>
      <div ref={detailRef} tabIndex={-1} className="min-w-0 outline-none">
        {selected ? <ReviewDetail key={selected.id} review={selected} onClose={() => { openRequest.current += 1; setSelected(null); router.replace('/report', { scroll: false }); }} onSaved={async (updated) => { setSelected((current) => current?.id === updated.id ? updated : current); await load(); }} copy={copy} locale={locale} /> : <div className="rounded-[26px] border border-dashed border-slate-300 bg-white p-8 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-950">{deepLinkLoading ? copy.loading : deepLinkError ? copy.error : copy.selectHint || copy.open}</div>}
      </div>
    </section>
  );
}
