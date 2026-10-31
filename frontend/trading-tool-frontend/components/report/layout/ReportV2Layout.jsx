"use client";

import { getDictionary, useTranslation } from '@/app/providers/I18nProvider';
import { formatDateTime } from '@/lib/i18n';
import { parseUtcMoment, reportMarketLabel, scoreSourceSnapshot } from '@/lib/report/reportSourceSnapshot.mjs';
import { reportV2AnalysisParagraphs, reportV2Change, reportV2IndicatorName, reportV2Locale } from '@/lib/report/reportV2Presentation.mjs';

const ZONES = [
  { min: 0, max: 25, width: 25, color: 'bg-rose-200' },
  { min: 26, max: 45, width: 20, color: 'bg-orange-200' },
  { min: 46, max: 60, width: 15, color: 'bg-amber-100' },
  { min: 61, max: 75, width: 15, color: 'bg-teal-100' },
  { min: 76, max: 100, width: 25, color: 'bg-emerald-200' },
];

const number = (value) => typeof value === 'number' && Number.isFinite(value) ? value : null;

function ScoreScale({ score, labels, unknown }) {
  const current = number(score);
  return <div className="mt-4">
    <div className="relative flex h-5 overflow-hidden rounded-md" aria-label={current === null ? unknown : `${current}/100`}>
      {ZONES.map((zone) => <div key={zone.min} className={`${zone.color} border-r border-white last:border-r-0`} style={{ width: `${zone.width}%` }} />)}
    </div>
    {current !== null && <div className="relative h-3" aria-hidden="true"><span className="absolute top-0 h-3 w-0.5 bg-slate-950" style={{ left: `${Math.max(0, Math.min(100, current))}%` }} /></div>}
    <div className="grid grid-cols-5 gap-1 text-center text-[10px] leading-tight text-slate-600 sm:text-xs">
      {ZONES.map((zone, index) => <span key={zone.min}>{zone.min}–{zone.max}<br />{labels[index]}</span>)}
    </div>
  </div>;
}

function Section({ title, prose, proseParagraphs, children, keepTogether = false }) {
  return <section className={`rounded-2xl border border-slate-200 bg-white p-5 sm:p-7 ${keepTogether ? 'break-inside-avoid' : ''}`}>
    <h2 className="break-after-avoid text-xl font-bold text-slate-950">{title}</h2>
    {proseParagraphs?.length ? <div className="mt-3 space-y-3">{proseParagraphs.map((paragraph, index) => <p key={index} className="break-inside-avoid whitespace-pre-line text-base leading-relaxed text-slate-700">{paragraph}</p>)}</div>
      : prose && <p className="mt-3 break-inside-avoid whitespace-pre-line text-base leading-relaxed text-slate-700">{prose}</p>}
    {children}
  </section>;
}

export default function ReportV2Layout({ report, isPrint = false }) {
  const { locale } = useTranslation();
  const language = reportV2Locale(report, locale);
  const t = getDictionary(language);
  const copy = {
    nl: { retrospective: 'Terugblik', portfolio: 'Portfolio', analysis: 'Analyse', plan: 'Mijn plan', automation: 'Automatisering', outlook: 'Vooruitblik', paper: 'Paper', live: 'Live', total: 'Totale waarde', positionValue: 'Positiewaarde', cash: 'Kassaldo', positions: 'In posities', result: 'Resultaat', budget: 'Botbudgetlimiet', unknown: 'Onbekend', noBots: 'Geen bots op het rapportmoment', noPlans: 'Geen opgeslagen plannen', noComparison: 'Geen vergelijkbare vorige momentopname', benchmark: 'Benchmark', market: 'Markt', macro: 'Macro', technical: 'Technisch', timeframe: 'Analyse-tijdsframe', frequency: 'Aankoopritme', amount: 'Basisbedrag per uitvoering', fixed: 'Vast bedrag', curve: 'Scoregestuurd bedrag', conditions: 'Benchmarkvoorwaarde', noConditions: 'Geen scorevoorwaarde', decision: 'Laatste beslissing', noDecision: 'Geen opgeslagen beslissing', observed: 'Bronmoment', zones: ['Zwaar onder druk', 'Onder druk', 'Geen duidelijke richting', 'De markt trekt aan', 'Sterke markt'], weekly: 'wekelijks', monthly: 'maandelijks', daily: 'dagelijks', day: 'dag', position: 'Positie', stop: 'Stop', target: 'Eerste doel', exit: 'Verkoopbewaking', available: 'beschikbaar', unavailable: 'niet beschikbaar', sourceDetails: 'Bronnen en berekening', noScore: 'Nog geen complete score', noIndicators: 'Geen indicatoren ingesteld', score: 'Score', botReason: 'Bekijk de bot voor de reden' },
    en: { retrospective: 'Looking back', portfolio: 'Portfolio', analysis: 'Analysis', plan: 'My plan', automation: 'Automation', outlook: 'Looking ahead', paper: 'Paper', live: 'Live', total: 'Total value', positionValue: 'Position value', cash: 'Cash', positions: 'In positions', result: 'Result', budget: 'Bot budget limit', unknown: 'Unknown', noBots: 'No bots at report time', noPlans: 'No saved plans', noComparison: 'No comparable earlier snapshot', benchmark: 'Benchmark', market: 'Market', macro: 'Macro', technical: 'Technical', timeframe: 'Analysis timeframe', frequency: 'Purchase schedule', amount: 'Base amount per execution', fixed: 'Fixed amount', curve: 'Score based amount', conditions: 'Benchmark condition', noConditions: 'No score condition', decision: 'Last decision', noDecision: 'No saved decision', observed: 'Source time', zones: ['Severe pressure', 'Pressure', 'No clear direction', 'Market strengthening', 'Strong market'], weekly: 'weekly', monthly: 'monthly', daily: 'daily', day: 'day', position: 'Position', stop: 'Stop', target: 'First target', exit: 'Exit monitoring', available: 'available', unavailable: 'unavailable', sourceDetails: 'Sources and calculation', noScore: 'No complete score yet', noIndicators: 'No indicators configured', score: 'Score', botReason: 'View the bot for the reason' },
    de: { retrospective: 'Rückblick', portfolio: 'Portfolio', analysis: 'Analyse', plan: 'Mein Plan', automation: 'Automatisierung', outlook: 'Ausblick', paper: 'Paper', live: 'Live', total: 'Gesamtwert', positionValue: 'Positionswert', cash: 'Guthaben', positions: 'In Positionen', result: 'Ergebnis', budget: 'Bot-Budgetlimit', unknown: 'Unbekannt', noBots: 'Keine Bots zum Berichtszeitpunkt', noPlans: 'Keine gespeicherten Pläne', noComparison: 'Keine vergleichbare frühere Momentaufnahme', benchmark: 'Benchmark', market: 'Markt', macro: 'Makro', technical: 'Technisch', timeframe: 'Analyse-Zeitrahmen', frequency: 'Kaufplan', amount: 'Basisbetrag je Ausführung', fixed: 'Fester Betrag', curve: 'Scoreabhängiger Betrag', conditions: 'Benchmarkbedingung', noConditions: 'Keine Scorebedingung', decision: 'Letzte Entscheidung', noDecision: 'Keine gespeicherte Entscheidung', observed: 'Quellzeit', zones: ['Starker Druck', 'Unter Druck', 'Keine klare Richtung', 'Markt zieht an', 'Starker Markt'], weekly: 'wöchentlich', monthly: 'monatlich', daily: 'täglich', day: 'Tag', position: 'Position', stop: 'Stop', target: 'Erstes Ziel', exit: 'Exitüberwachung', available: 'verfügbar', unavailable: 'nicht verfügbar', sourceDetails: 'Quellen und Berechnung', noScore: 'Noch keine vollständige Bewertung', noIndicators: 'Keine Indikatoren eingerichtet', score: 'Bewertung', botReason: 'Grund beim Bot ansehen' },
  }[language] || null;
  const c = copy || { unknown: 'Unknown', zones: [] };
  const traderCopy = t?.pages?.report?.traderStatus || {};
  const snapshot = scoreSourceSnapshot(report) || {};
  const v2 = snapshot.report_v2 || {};
  const prose = v2.sections || {};
  const assets = Array.isArray(snapshot.assets) ? snapshot.assets : [];
  const plans = Array.isArray(v2.plans) ? v2.plans : [];
  const bots = Array.isArray(v2.automation?.bots) ? v2.automation.bots : [];
  const money = (value) => number(value) === null ? c.unknown : new Intl.NumberFormat(language, { style: 'currency', currency: 'EUR' }).format(value);
  const measured = (value) => number(value) !== null
    ? new Intl.NumberFormat(language, { maximumFractionDigits: 2 }).format(value)
    : typeof value === 'string' && value.trim() ? value.trim() : c.unknown;
  const timestamp = (value) => { const moment = parseUtcMoment(value); return moment ? `${formatDateTime(moment, language, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })} UTC` : c.unknown; };
  const cadence = (setup) => {
    const frequency = String(setup.dca_frequency || '').toLowerCase();
    if (frequency === 'weekly') {
      const weekdays = {
        nl: ['maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag'],
        en: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
        de: ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'],
      };
      const day = Number(setup.dca_day);
      return `${c.weekly}${day >= 1 && day <= 7 ? ` · ${weekdays[language]?.[day - 1] || day}` : ''}`;
    }
    if (frequency === 'monthly') return `${c.monthly}${setup.dca_month_day == null ? '' : ` · ${c.day} ${setup.dca_month_day}`}`;
    if (frequency === 'daily') return c.daily;
    return c.unknown;
  };
  const indicatorLabels = t?.traderProfile?.analysisOnboardingStep?.indicatorNames || {};
  const changeLabels = {
    benchmark_score: c.benchmark,
    benchmark_availability: c.benchmark,
    market_score: c.market,
    macro_score: c.macro,
    technical_score: c.technical,
    available: c.available,
    unavailable: c.unavailable,
  };
  const evidenceLine = (asset, category) => {
    const names = asset.configured_indicators?.[category] || [];
    if (!names.length) return c.noIndicators;
    return names.map((name) => {
      const evidence = asset.verified_indicator_evidence?.[category]?.[name];
      return `${reportV2IndicatorName(name, indicatorLabels)}: ${number(evidence?.score) === null ? c.unknown : `${evidence.score}/100`}${evidence?.source_observed_at ? ` · ${c.observed}: ${timestamp(evidence.source_observed_at)}` : ''}`;
    }).join('; ');
  };
  const reportDate = /^\d{4}-\d{2}-\d{2}$/.test(String(report?.report_date || ''))
    ? new Intl.DateTimeFormat(language, { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${report.report_date}T12:00:00Z`))
    : null;
  return <div className={`mx-auto max-w-[1100px] space-y-6 pb-20 ${isPrint ? 'print:space-y-4' : ''}`}>
    <header className="break-after-avoid pb-1"><h1 className="text-3xl font-bold text-slate-950">{t?.pages?.report?.types?.daily}</h1>{reportDate && <p className="mt-1 text-sm text-slate-600">{reportDate}</p>}</header>
    <Section title={c.retrospective} prose={prose.retrospective}>
      {(v2.comparison?.changes || []).length > 0 && <div className="mt-4 space-y-2 text-sm text-slate-600">{v2.comparison.changes.map((change, i) => <p key={`${change.asset}-${i}`}>{reportV2Change(change, changeLabels)}</p>)}</div>}
    </Section>
    <Section title={c.portfolio} prose={prose.portfolio}>
      <div className="mt-5 grid gap-4 md:grid-cols-2 print:grid-cols-2 print:break-inside-avoid">{['paper', 'live'].map((environment) => { const data = v2.portfolio?.[environment] || {}; const total = data.global || {}; return <div key={environment} className="break-inside-avoid rounded-xl border border-slate-200 p-4"><h3 className="font-bold">{c[environment]}</h3><div className="mt-3 grid grid-cols-2 gap-3 text-sm"><p>{c.total}<br /><strong>{money(total.total_equity)}</strong></p><p>{c.cash}<br /><strong>{money(total.cash_balance)}</strong></p><p>{c.positions}<br /><strong>{money(total.current_position_value)}</strong></p><p>{c.result}<br /><strong>{money(number(total.realized_pnl) !== null && number(total.unrealized_pnl) !== null ? total.realized_pnl + total.unrealized_pnl : null)}</strong></p></div><p className="mt-3 text-xs text-slate-500">{c.budget}: {money(total.total_budget_limit)}</p>{(data.bots || []).map((bot) => <p key={bot.bot_id} className="mt-2 border-t pt-2 text-sm">{bot.name || bot.symbol} · {c.total}: {money(bot.equity)} · {c.cash}: {money(bot.cash_eur)}</p>)}</div>; })}</div>
    </Section>
    <Section title={c.analysis} proseParagraphs={reportV2AnalysisParagraphs(prose.analysis, language)}>
      <div className="mt-5 space-y-3">
        {assets.map((asset, index) => {
          const score = number(asset.benchmark_score);
          const parts = asset.reported_scores || {};
          return <div key={`${reportMarketLabel(asset)}-${index}`} className="break-inside-avoid rounded-xl border border-slate-200 p-4">
            <h3 className="font-bold">{reportMarketLabel(asset)} · {score === null ? c.noScore : `${c.benchmark} ${measured(score)}/100`}</h3>
            {score !== null && <ScoreScale score={score} labels={c.zones} unknown={c.unknown} />}
            <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
              <p>{c.market}: {number(parts.market_score) ?? '—'}</p>
              <p>{c.macro}: {number(parts.macro_score) ?? '—'}</p>
              <p>{c.technical}: {number(parts.technical_score) ?? '—'}</p>
            </div>
            <details className="mt-3 text-xs text-slate-600 print:hidden">
              <summary className="cursor-pointer font-medium">{c.sourceDetails}</summary>
              {['market', 'macro', 'technical'].map((category) => <p key={category} className="mt-2"><strong>{c[category]}:</strong> {evidenceLine(asset, category)}</p>)}
            </details>
            {score !== null && <p className="mt-2 hidden text-xs text-slate-600 print:block">{['market', 'macro', 'technical'].filter((category) => (asset.configured_indicators?.[category] || []).length).map((category) => `${c[category]}: ${(asset.configured_indicators[category] || []).map((name) => reportV2IndicatorName(name, indicatorLabels)).join(', ')}`).join(' · ')}</p>}
          </div>;
        })}
      </div>
    </Section>
    <Section title={c.plan} prose={prose.plan}>
      <div className="mt-5 space-y-4">{plans.flatMap((asset) => (asset.setups || []).map((setup) => { const strategies = (asset.strategies || []).filter((row) => row.setup_id === setup.id); const hasCondition = number(setup.min_benchmark_score) !== null || number(setup.max_benchmark_score) !== null; return <div key={`${asset.pair || asset.symbol}-${setup.id}`} className="break-inside-avoid rounded-xl border border-slate-200 p-4"><h3 className="font-bold">{setup.name || asset.pair || asset.symbol}</h3><p className="mt-2 text-sm">{asset.pair || asset.symbol} · {c.timeframe}: {setup.timeframe || c.unknown}</p>{setup.setup_type === 'dca' && <p className="text-sm">{c.frequency}: {cadence(setup)}</p>}<p className="text-sm">{c.conditions}: {hasCondition ? `${setup.min_benchmark_score ?? 0}–${setup.max_benchmark_score ?? 100}` : c.noConditions}</p>{strategies.map((strategy) => <p key={strategy.id} className="mt-2 border-t pt-2 text-sm">{strategy.name} · {strategy.execution_mode === 'custom' ? c.curve : c.fixed} · {c.amount}: {money(strategy.base_amount)}{strategy.execution_mode === 'custom' && Array.isArray(strategy.decision_curve?.points) ? ` · ${strategy.decision_curve.points.map((point) => `${point.x}→${Math.round(point.y * 100)}%`).join(', ')}` : ''}</p>)}</div>; }))}{plans.every((asset) => !(asset.setups || []).length) && <p>{c.noPlans}</p>}</div>
    </Section>
    <Section title={c.automation} prose={prose.automation}>
      <div className="mt-5 space-y-4">{bots.length ? bots.map((bot) => { const decision = bot.latest_decision; const reason = (decision?.block_code && t?.botPage?.focus?.riskCodes?.[decision.block_code]) || (decision?.reason_key && traderCopy.reasons?.[decision.reason_key]) || (decision?.reason ? c.botReason : null); return <div key={bot.bot_id} className="break-inside-avoid rounded-xl border border-slate-200 p-4"><h3 className="font-bold">{bot.bot_name || bot.strategy_name || bot.symbol} · {bot.is_live ? c.live : c.paper} · {bot.is_active ? traderCopy.active : traderCopy.paused}</h3><p className="mt-2 text-sm">{bot.trading_pair || bot.symbol} · {c.position}: {number(bot.position_qty) === null ? c.unknown : measured(bot.position_qty)} · {c.positionValue}: {money(bot.position_value_eur)}</p>{number(bot.position_qty) > 0 && <p className="text-sm">{c.stop}: {number(bot.stop_loss) === null ? c.unknown : `${measured(bot.stop_loss)} ${bot.level_currency || ''}`} · {c.target}: {number(bot.first_target) === null ? c.unknown : `${measured(bot.first_target)} ${bot.level_currency || ''}`} · {c.exit}: {traderCopy.monitoring?.[bot.exit_monitoring] || traderCopy.monitoring?.unknown || c.unknown}</p>}<p className="mt-2 text-sm">{c.decision}: {decision ? `${traderCopy.actions?.[decision.action] || traderCopy.actions?.other || c.unknown} · ${timestamp(decision.at)}${reason ? ` · ${reason}` : ''}` : c.noDecision}</p></div>; }) : <p>{c.noBots}</p>}</div>
    </Section>
    <Section title={c.outlook} prose={prose.outlook_v2} keepTogether />
  </div>;
}
