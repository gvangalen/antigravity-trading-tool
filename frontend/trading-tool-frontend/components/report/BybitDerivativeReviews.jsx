'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { createFinnBybitDerivativeReview, fetchFinnBybitDerivativeEpisodes, fetchFinnBybitDerivativeStreams, fetchFinnBybitDerivatives, syncFinnBybitDerivatives } from '@/lib/api/botApi';

const formatDate = (value, locale) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
};
const formatNumber = (value, locale) => new Intl.NumberFormat(locale, { maximumFractionDigits: 8 }).format(Number(value) || 0);

export default function BybitDerivativeReviews({ copy, locale, onCreated }) {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState(false);
  const [opened, setOpened] = useState(null);
  const [streams, setStreams] = useState([]);
  const [streamsMore, setStreamsMore] = useState(false);
  const [streamsHasMore, setStreamsHasMore] = useState(false);
  const [streamFilter, setStreamFilter] = useState(null);
  const [episodes, setEpisodes] = useState([]);
  const [episodeTotal, setEpisodeTotal] = useState(0);
  const [evidenceCursor, setEvidenceCursor] = useState(null);
  const [nextEvidenceCursor, setNextEvidenceCursor] = useState(null);
  const [episodesLoading, setEpisodesLoading] = useState(false);
  const [episodesMore, setEpisodesMore] = useState(false);
  const [episodesError, setEpisodesError] = useState(false);
  const [selected, setSelected] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(false);
  const requestKey = useRef(null);
  const requestSerial = useRef(0);

  const loadSources = useCallback(async () => {
    try {
      const data = await fetchFinnBybitDerivatives();
      setSources(Array.isArray(data?.sources) ? data.sources : []);
      setError(false);
    } catch { setError(true); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadSources(); }, [loadSources]);

  async function sync() {
    const visibleRequest = requestSerial.current;
    setSyncing(true); setError(false);
    try {
      await syncFinnBybitDerivatives();
      await loadSources();
      if (opened && requestSerial.current === visibleRequest) await openEpisodes(opened, true, streamFilter);
    } catch { setError(true); }
    finally { setSyncing(false); }
  }

  async function openEpisodes(source, force = false, stream = null) {
    const requestId = ++requestSerial.current;
    const key = `${source.source_id}:${source.category}`;
    if (!force && opened && `${opened.source_id}:${opened.category}` === key) {
      setOpened(null); setEpisodes([]); setStreams([]); setStreamFilter(null); return;
    }
    setOpened(source); setEpisodes([]); setEpisodeTotal(0); setEpisodesLoading(true); setEpisodesError(false);
    setEvidenceCursor(null); setNextEvidenceCursor(null);
    setStreams([]); setStreamsHasMore(false); setStreamsMore(false); setEpisodesMore(false);
    setStreamFilter(stream);
    setSelected(null); setConfirmed(false); requestKey.current = null;
    try {
      const [data, streamData] = await Promise.all([
        fetchFinnBybitDerivativeEpisodes(source.source_id, source.category, 50, 0, stream),
        fetchFinnBybitDerivativeStreams(source.source_id, source.category),
      ]);
      if (requestSerial.current !== requestId) return;
      setEpisodes(Array.isArray(data?.items) ? data.items : []);
      setEpisodeTotal(Number(data?.total) || 0);
      setNextEvidenceCursor(data?.next_evidence_before || null);
      setStreams(Array.isArray(streamData?.items) ? streamData.items : []);
      setStreamsHasMore(Boolean(streamData?.has_more));
    } catch { if (requestSerial.current === requestId) { setEpisodesError(true); setEpisodes([]); } }
    finally { if (requestSerial.current === requestId) setEpisodesLoading(false); }
  }

  async function loadMoreStreams() {
    if (!opened || streamsMore || !streamsHasMore) return;
    const requestId = requestSerial.current;
    setStreamsMore(true);
    try {
      const data = await fetchFinnBybitDerivativeStreams(opened.source_id, opened.category, 50, streams.length);
      if (requestSerial.current !== requestId) return;
      setStreams((current) => [...current, ...(Array.isArray(data?.items) ? data.items : [])]);
      setStreamsHasMore(Boolean(data?.has_more));
    } catch { if (requestSerial.current === requestId) setEpisodesError(true); }
    finally { if (requestSerial.current === requestId) setStreamsMore(false); }
  }

  async function loadMore() {
    if (!opened || episodesMore || episodes.length >= episodeTotal) return;
    const requestId = requestSerial.current;
    setEpisodesMore(true); setEpisodesError(false);
    try {
      const data = await fetchFinnBybitDerivativeEpisodes(opened.source_id, opened.category, 50, episodes.length, streamFilter, evidenceCursor);
      if (requestSerial.current !== requestId) return;
      setEpisodes((current) => [...current, ...(Array.isArray(data?.items) ? data.items : [])]);
      setEpisodeTotal(Number(data?.total) || 0);
    } catch { if (requestSerial.current === requestId) setEpisodesError(true); }
    finally { if (requestSerial.current === requestId) setEpisodesMore(false); }
  }

  async function loadOlderEvidence() {
    if (!opened || !nextEvidenceCursor || episodesLoading) return;
    const requestId = ++requestSerial.current;
    const cursor = nextEvidenceCursor;
    setEpisodesLoading(true); setEpisodesError(false); setSelected(null); setConfirmed(false);
    setEpisodes([]); setEpisodeTotal(0); setEvidenceCursor(cursor); setNextEvidenceCursor(null);
    try {
      const data = await fetchFinnBybitDerivativeEpisodes(opened.source_id, opened.category, 50, 0, streamFilter, cursor);
      if (requestSerial.current !== requestId) return;
      setEpisodes(Array.isArray(data?.items) ? data.items : []);
      setEpisodeTotal(Number(data?.total) || 0);
      setNextEvidenceCursor(data?.next_evidence_before || null);
    } catch { if (requestSerial.current === requestId) setEpisodesError(true); }
    finally { if (requestSerial.current === requestId) setEpisodesLoading(false); }
  }

  function selectEpisode(episode, source) {
    setSelected((current) => current?.episode_key === episode.episode_key ? null : {
      ...episode, source_id: source.source_id, category: source.category,
    });
    setConfirmed(false); setCreateError(false); requestKey.current = null;
  }

  async function createReview() {
    if (!selected || !confirmed || creating || !selected.execution_preview?.length ||
        selected.execution_preview.length !== selected.slices?.length) return;
    if (!requestKey.current) requestKey.current = crypto.randomUUID();
    const visibleRequest = requestSerial.current;
    setCreating(true); setCreateError(false);
    try {
      const result = await createFinnBybitDerivativeReview(selected, requestKey.current);
      setSelected(null); setConfirmed(false); requestKey.current = null;
      await loadSources();
      if (opened && requestSerial.current === visibleRequest) await openEpisodes(opened, true, streamFilter);
      onCreated(result.review_id);
    } catch { setCreateError(true); }
    finally { setCreating(false); }
  }

  return <div className="mt-4 rounded-xl border border-slate-200 p-4 text-xs dark:border-slate-800">
    <h3 className="font-black text-slate-900 dark:text-white">{copy.derivativeTitle}</h3>
    <p className="mt-1 leading-relaxed text-slate-600 dark:text-slate-300">{copy.derivativeIntro}</p>
    <button type="button" onClick={sync} disabled={syncing || loading} className="mt-3 rounded-lg border border-blue-400 px-2 py-1 font-bold text-blue-700 disabled:opacity-50 dark:text-blue-300">{syncing ? copy.loading : copy.exchangeImportSync}</button>
    {loading && <p role="status" className="mt-2 text-slate-500">{copy.loading}</p>}
    {error && <p role="alert" className="mt-2 text-red-600">{copy.derivativeError}</p>}
    {!loading && !error && sources.length === 0 && <p className="mt-2 text-slate-500">{copy.derivativeEmpty}</p>}
    {sources.map((source) => <div key={`${source.source_id}:${source.category}`} className="mt-3 rounded-lg bg-slate-50 p-3 dark:bg-slate-900">
      <p><strong>{copy.derivativeCategory?.[source.category] || source.category}</strong> · {copy.exchangeImportStates?.[source.status] || source.status}</p>
      <p className="mt-1 text-slate-500">{source.trade_executions || 0} {copy.exchangeImportFills} · {source.unresolved_orders || 0} {copy.derivativeUnresolvedOrders} · {source.material_events || 0} {copy.derivativeMaterialEvents}</p>
      {source.coverage_through_at && <p className="mt-1 text-slate-500">{copy.exchangeImportThrough}: {formatDate(source.coverage_through_at, locale)}</p>}
      {source.source_id && <button type="button" onClick={() => openEpisodes(source)} className="mt-2 font-bold text-blue-600 underline dark:text-blue-300">{opened?.source_id === source.source_id && opened?.category === source.category ? copy.derivativeHideEpisodes : copy.derivativeShowEpisodes}</button>}
      {opened?.source_id === source.source_id && opened?.category === source.category && <div className="mt-3 space-y-2">
        {streams.length > 0 && <div className="flex flex-wrap gap-1" aria-label={copy.derivativeStreams}>
          <button type="button" onClick={() => openEpisodes(source, true)} className={`rounded-full border px-2 py-1 ${!streamFilter ? 'border-blue-500 font-bold text-blue-700 dark:text-blue-300' : 'border-slate-300 dark:border-slate-700'}`}>{copy.derivativeAllStreams}</button>
          {streams.map((stream) => <button key={`${stream.symbol}:${stream.position_idx}`} type="button" onClick={() => openEpisodes(source, true, stream)} className={`rounded-full border px-2 py-1 ${streamFilter?.symbol === stream.symbol && streamFilter?.position_idx === stream.position_idx ? 'border-blue-500 font-bold text-blue-700 dark:text-blue-300' : 'border-slate-300 dark:border-slate-700'}`}>{stream.symbol} · {copy.derivativePositionIndex} {stream.position_idx}</button>)}
          {streamsHasMore && <button type="button" onClick={loadMoreStreams} disabled={streamsMore} className="font-bold text-blue-600 underline disabled:opacity-50">{streamsMore ? copy.loading : copy.exchangeImportLoadMore}</button>}
        </div>}
        {episodesLoading && <p role="status">{copy.loading}</p>}
        {episodesError && <p role="alert" className="text-red-600">{copy.derivativeError}</p>}
        {!episodesLoading && !episodesError && episodes.length === 0 && <p className="text-slate-500">{nextEvidenceCursor ? copy.derivativeNoClosedHere : copy.derivativeNoClosed}</p>}
        {episodes.map((episode) => <button key={episode.episode_key} type="button" onClick={() => selectEpisode(episode, source)} className={`block w-full rounded-lg border p-3 text-left ${selected?.episode_key === episode.episode_key ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30' : 'border-slate-200 dark:border-slate-700'}`}>
          <strong>{episode.symbol} · {copy.derivativeDirection?.[episode.direction] || episode.direction}</strong>
          <span className="mt-1 block text-slate-500">{formatDate(episode.entry_at, locale)} → {formatDate(episode.exit_at, locale)} · {episode.slices?.length || 0} {copy.derivativeSlices}</span>
          {episode.review_id && <span className="mt-1 block text-slate-500">{copy.exchangeAlreadyReviewed} #{episode.review_id}</span>}
        </button>)}
        {!episodesError && episodes.length < episodeTotal && <button type="button" onClick={loadMore} disabled={episodesMore} className="font-bold text-blue-600 underline disabled:opacity-50">{episodesMore ? copy.loading : copy.exchangeImportLoadMore}</button>}
        {nextEvidenceCursor && !episodesLoading && <button type="button" onClick={loadOlderEvidence} className="block font-bold text-blue-600 underline dark:text-blue-300">{copy.derivativeOlderEvidence}</button>}
      </div>}
    </div>)}
    {selected && <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950/30">
      <h4 className="font-black">{selected.symbol} · {copy.derivativeDirection?.[selected.direction] || selected.direction}</h4>
      <p className="mt-1 text-slate-600 dark:text-slate-300">{copy.derivativeSelectionHint}</p>
      <p className="mt-2 text-slate-600 dark:text-slate-300">{copy.derivativeCategory?.[selected.category] || selected.category} · {copy.derivativePositionIndex}: {selected.position_idx} · {copy.derivativeNativePnl}: {copy.exchangeResultUnavailable}</p>
      <ol className="mt-3 max-h-64 space-y-2 overflow-auto" aria-label={copy.derivativeSelectedExecutions}>
        {(selected.execution_preview || []).map((part, index) => <li key={`${part.execution_id}-${part.role}-${index}`} className="rounded-lg border border-blue-200 bg-white p-2 dark:border-blue-800 dark:bg-slate-900">
          <strong>{copy.derivativeRole?.[part.role] || part.role} · {formatNumber(part.allocated_qty, locale)} {copy.derivativeContracts}</strong>
          <span className="block text-slate-500">{formatDate(part.at, locale)} · {part.side === 'buy' ? copy.buy : copy.sell} · {formatNumber(part.price_quote, locale)} {part.quote_currency || ''}</span>
          <span className="block break-all text-slate-500">{copy.derivativeExecution}: {part.exec_id} · {copy.derivativeOrder}: {part.order_id}</span>
          <span className="block text-slate-500">{copy.derivativeRawExecution}: {formatNumber(part.raw_exec_qty, locale)} {copy.derivativeContracts} · {copy.derivativeSettlement}: {part.settle_currency}</span>
          {part.fee_amount_raw_execution != null && <span className="block text-slate-500">{copy.derivativeFeeRaw}: {formatNumber(part.fee_amount_raw_execution, locale)} {part.fee_currency || ''}</span>}
        </li>)}
      </ol>
      <p className="mt-2 text-amber-800 dark:text-amber-200">{copy.derivativeEvidenceUncertain}</p>
      {selected.history_truncated && <p role="alert" className="mt-2 rounded-lg border border-amber-400 bg-amber-100 p-2 font-bold text-amber-900 dark:bg-amber-950 dark:text-amber-100">{copy.derivativeHistoryTruncated}</p>}
      <label className="mt-3 flex items-start gap-2"><input type="checkbox" checked={confirmed} disabled={!selected.execution_preview?.length || selected.execution_preview.length !== selected.slices?.length} onChange={(event) => setConfirmed(event.target.checked)} className="mt-0.5" /><span>{copy.derivativeClosureConfirm}</span></label>
      {createError && <p role="alert" className="mt-2 text-red-700 dark:text-red-300">{copy.derivativeCreateError}</p>}
      <button type="button" disabled={!confirmed || creating || Boolean(selected.review_id) || !selected.execution_preview?.length || selected.execution_preview.length !== selected.slices?.length} onClick={createReview} className="mt-3 rounded-lg bg-blue-600 px-4 py-2 font-bold text-white disabled:opacity-50">{creating ? copy.loading : copy.exchangeCreateReview}</button>
    </div>}
  </div>;
}
