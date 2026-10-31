'use client';

import { useTranslation } from '@/app/providers/I18nProvider';
import { parseUtcMoment, reportMarketLabel, scoreSourceSnapshot } from '@/lib/report/reportSourceSnapshot.mjs';

const LOCALES = { nl: 'nl-NL', en: 'en-GB', de: 'de-DE' };

function dateTime(value, locale, timeZone) {
  const date = parseUtcMoment(value);
  if (!date) return null;
  return new Intl.DateTimeFormat(LOCALES[locale] || LOCALES.nl, {
    timeZone, day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(date);
}

function amount(value, locale, currency = 'EUR') {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  try {
    return new Intl.NumberFormat(LOCALES[locale] || LOCALES.nl, {
      style: 'currency', currency, maximumFractionDigits: 2,
    }).format(Number(value));
  } catch {
    return `${Number(value).toFixed(2)} ${currency}`;
  }
}

export default function DailyTraderStatus({ report, status, loading, error, onRefresh }) {
  const { t, locale } = useTranslation();
  const copy = t.pages.report.traderStatus;
  const reportSnapshot = scoreSourceSnapshot(report);
  const reportAt = reportSnapshot?.observed_at || report?.generated_at || report?.created_at;
  const reportLocal = dateTime(reportAt, locale, 'Europe/Amsterdam');
  const reportUtc = dateTime(reportAt, locale, 'UTC');
  const currentAt = dateTime(status?.observed_at, locale, 'Europe/Amsterdam');
  const reportEpoch = parseUtcMoment(reportAt)?.getTime() ?? NaN;
  const securitiesOutside = (reportSnapshot?.assets || [])
    .filter((asset) => asset.market_session_at_report === 'outside_regular_hours')
    .map((asset) => asset.symbol);
  const bots = status?.bots || [];
  const openPositions = bots.filter((bot) => bot.position_qty != null && bot.position_qty !== 0);

  return (
    <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 text-slate-900 md:p-6" aria-label={copy.title}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold">{copy.title}</h3>
          <p className="mt-1 text-sm text-slate-600">{copy.separation}</p>
        </div>
        <button type="button" onClick={onRefresh} disabled={loading}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-blue-700 disabled:opacity-50">
          {loading ? copy.loading : copy.refresh}
        </button>
      </div>

      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-600">
        <span>{copy.reportAt}: {reportLocal || '—'} {reportLocal && '(Europe/Amsterdam)'}</span>
        <span>{copy.utcAt}: {reportUtc || '—'} {reportUtc && 'UTC'}</span>
        <span>{copy.currentAt}: {currentAt || '—'} {currentAt && '(Europe/Amsterdam)'}</span>
      </div>
      {securitiesOutside.length > 0 && (
        <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
          {copy.outsideHours.replace('{assets}', securitiesOutside.join(', '))}
        </p>
      )}
      {error && <p className="mt-4 text-sm text-amber-800">{copy.loadError}</p>}
      {!error && !loading && bots.length === 0 && <p className="mt-4 text-sm text-slate-600">{copy.noBots}</p>}
      {!error && status && (
        <div className="mt-5 space-y-4">
          <p className="text-sm font-semibold">{copy.openPositions}: {openPositions.length}</p>
          {openPositions.length === 0 && <p className="text-sm text-slate-600">{copy.noOpenPositions}</p>}
          {bots.map((bot) => {
            const decision = bot.latest_decision;
            const decisionReason = (decision?.block_code && t?.botPage?.focus?.riskCodes?.[decision.block_code])
              || (decision?.reason_key && copy.reasons?.[decision.reason_key])
              || decision?.reason;
            const decisionAt = dateTime(decision?.at, locale, 'Europe/Amsterdam');
            const decisionEpoch = parseUtcMoment(decision?.at)?.getTime() ?? NaN;
            const decisionPredatesReport = Number.isFinite(decisionEpoch) && Number.isFinite(reportEpoch) && decisionEpoch < reportEpoch;
            const lastRun = dateTime(bot.last_run, locale, 'Europe/Amsterdam');
            const priceAt = dateTime(bot.price_source_at, locale, 'Europe/Amsterdam');
            const monitoring = copy.monitoring[bot.exit_monitoring] || copy.monitoring.unknown;
            return (
              <div key={bot.bot_id} className="rounded-xl border border-slate-200 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-semibold">{bot.bot_name || bot.symbol} · {reportMarketLabel(bot)} · {bot.is_live ? copy.live : copy.paper} · {bot.is_active ? copy.active : copy.paused}</div>
                  <a className="text-sm font-semibold text-blue-700 hover:underline"
                    href={`/bot?symbol=${encodeURIComponent(bot.symbol || '')}&bot_id=${encodeURIComponent(bot.bot_id)}`}>
                    {copy.viewBot}
                  </a>
                </div>
                <div className="mt-2 grid gap-2 text-sm text-slate-700 md:grid-cols-2">
                  <p>{copy.position}: {bot.position_qty == null ? copy.unknown : `${Number(bot.position_qty).toLocaleString(LOCALES[locale] || LOCALES.nl)} ${bot.symbol}`}</p>
                  <p>{copy.positionValue}: {amount(bot.position_value_eur, locale)}</p>
                  {bot.position_qty != null && bot.position_qty !== 0 && (
                    <>
                      <p>{copy.stop}: {amount(bot.stop_loss, locale, bot.level_currency || 'EUR')}</p>
                      <p>{copy.firstTarget}: {amount(bot.first_target, locale, bot.level_currency || 'EUR')}</p>
                      <p className="md:col-span-2">{copy.exitStatus}: {monitoring}</p>
                    </>
                  )}
                  <p>{copy.lastAssessment}: {lastRun || copy.unknown}</p>
                  <p>{copy.priceSource}: {priceAt || copy.unknown}</p>
                </div>
                <div className="mt-3 border-t border-slate-100 pt-3 text-sm text-slate-700">
                  <strong>{copy.latestDecision}:</strong> {decision
                    ? `${copy.actions[decision.action] || copy.actions.other} · ${decisionAt || copy.unknown}${decisionReason ? ` · ${decisionReason}` : ''}`
                    : copy.noDecision}
                  {decision?.at && Number.isFinite(reportEpoch) && new Date(decision.at).getTime() > reportEpoch && (
                    <span className="ml-2 text-blue-700">{copy.afterReport}</span>
                  )}
                  {decisionPredatesReport && <p className="mt-2 text-amber-800">{copy.beforeReportDecision}</p>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
