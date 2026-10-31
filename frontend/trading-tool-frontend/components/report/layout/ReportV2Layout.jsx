"use client";

import { useTranslation } from '@/app/providers/I18nProvider';
import { formatDateTime } from '@/lib/i18n';
import { parseUtcMoment, reportMarketLabel, scoreSourceSnapshot } from '@/lib/report/reportSourceSnapshot.mjs';

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

function Section({ title, prose, children }) {
  return <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
    <h2 className="text-xl font-bold text-slate-950">{title}</h2>
    {prose && <p className="mt-3 whitespace-pre-line text-base leading-relaxed text-slate-700">{prose}</p>}
    {children}
  </section>;
}

export default function ReportV2Layout({ report, isPrint = false }) {
  const { locale, t } = useTranslation();
  const language = String(locale || 'nl').slice(0, 2);
  const copy = {
    nl: { retrospective: 'Terugblik', portfolio: 'Portfolio', analysis: 'Analyse', plan: 'Mijn plan', automation: 'Automatisering', outlook: 'Vooruitblik', paper: 'Paper', live: 'Live', total: 'Totale waarde', cash: 'Cash', positions: 'In posities', result: 'Resultaat', budget: 'Botbudgetlimiet', unknown: 'Onbekend', noBots: 'Geen bots op het rapportmoment', noPlans: 'Geen opgeslagen plannen', noComparison: 'Geen vergelijkbare vorige momentopname', benchmark: 'Benchmark', market: 'Markt', macro: 'Macro', technical: 'Technisch', timeframe: 'Analyse-tijdsframe', frequency: 'Aankoopritme', amount: 'Basisbedrag per uitvoering', fixed: 'Vast bedrag', curve: 'Scoregestuurd bedrag', conditions: 'Benchmarkvoorwaarde', noConditions: 'Geen scorevoorwaarde', decision: 'Laatste beslissing', noDecision: 'Geen opgeslagen beslissing', observed: 'Bronmoment', zones: ['Zwaar onder druk', 'Onder druk', 'Geen duidelijke richting', 'De markt trekt aan', 'Sterke markt'], weekly: 'wekelijks', monthly: 'maandelijks', daily: 'dagelijks', day: 'dag', position: 'Positie', stop: 'Stop', target: 'Eerste doel', exit: 'Exitbewaking' },
    en: { retrospective: 'Looking back', portfolio: 'Portfolio', analysis: 'Analysis', plan: 'My plan', automation: 'Automation', outlook: 'Looking ahead', paper: 'Paper', live: 'Live', total: 'Total value', cash: 'Cash', positions: 'In positions', result: 'Result', budget: 'Bot budget limit', unknown: 'Unknown', noBots: 'No bots at report time', noPlans: 'No saved plans', noComparison: 'No comparable earlier snapshot', benchmark: 'Benchmark', market: 'Market', macro: 'Macro', technical: 'Technical', timeframe: 'Analysis timeframe', frequency: 'Purchase schedule', amount: 'Base amount per execution', fixed: 'Fixed amount', curve: 'Score based amount', conditions: 'Benchmark condition', noConditions: 'No score condition', decision: 'Last decision', noDecision: 'No saved decision', observed: 'Source time', zones: ['Severe pressure', 'Pressure', 'No clear direction', 'Market strengthening', 'Strong market'], weekly: 'weekly', monthly: 'monthly', daily: 'daily', day: 'day', position: 'Position', stop: 'Stop', target: 'First target', exit: 'Exit monitoring' },
    de: { retrospective: 'Rückblick', portfolio: 'Portfolio', analysis: 'Analyse', plan: 'Mein Plan', automation: 'Automatisierung', outlook: 'Ausblick', paper: 'Paper', live: 'Live', total: 'Gesamtwert', cash: 'Guthaben', positions: 'In Positionen', result: 'Ergebnis', budget: 'Bot-Budgetlimit', unknown: 'Unbekannt', noBots: 'Keine Bots zum Berichtszeitpunkt', noPlans: 'Keine gespeicherten Pläne', noComparison: 'Keine vergleichbare frühere Momentaufnahme', benchmark: 'Benchmark', market: 'Markt', macro: 'Makro', technical: 'Technisch', timeframe: 'Analyse-Zeitrahmen', frequency: 'Kaufplan', amount: 'Basisbetrag je Ausführung', fixed: 'Fester Betrag', curve: 'Scoreabhängiger Betrag', conditions: 'Benchmarkbedingung', noConditions: 'Keine Scorebedingung', decision: 'Letzte Entscheidung', noDecision: 'Keine gespeicherte Entscheidung', observed: 'Quellzeit', zones: ['Starker Druck', 'Unter Druck', 'Keine klare Richtung', 'Markt zieht an', 'Starker Markt'], weekly: 'wöchentlich', monthly: 'monatlich', daily: 'täglich', day: 'Tag', position: 'Position', stop: 'Stop', target: 'Erstes Ziel', exit: 'Exitüberwachung' },
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
  const timestamp = (value) => { const moment = parseUtcMoment(value); return moment ? `${formatDateTime(moment, locale, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })} UTC` : c.unknown; };
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
  return <div className={`mx-auto max-w-[1100px] space-y-6 pb-20 ${isPrint ? 'print:space-y-4' : ''}`}>
    <Section title={c.retrospective} prose={prose.retrospective}>
      {(v2.comparison?.changes || []).length > 0 && <div className="mt-4 space-y-2 text-sm text-slate-600">{v2.comparison.changes.map((change, i) => <p key={`${change.asset}-${i}`}>{change.asset}: {change.fact === 'benchmark_score' ? `${change.before} → ${change.after}` : `${change.before ? c.benchmark : c.unknown} → ${change.after ? c.benchmark : c.unknown}`}</p>)}</div>}
    </Section>
    <Section title={c.portfolio} prose={prose.portfolio}>
      <div className="mt-5 grid gap-4 md:grid-cols-2">{['paper', 'live'].map((environment) => { const data = v2.portfolio?.[environment] || {}; const total = data.global || {}; return <div key={environment} className="rounded-xl border border-slate-200 p-4"><h3 className="font-bold">{c[environment]}</h3><div className="mt-3 grid grid-cols-2 gap-3 text-sm"><p>{c.total}<br /><strong>{money(total.total_equity)}</strong></p><p>{c.cash}<br /><strong>{money(total.cash_balance)}</strong></p><p>{c.positions}<br /><strong>{money(total.current_position_value)}</strong></p><p>{c.result}<br /><strong>{money(number(total.realized_pnl) !== null && number(total.unrealized_pnl) !== null ? total.realized_pnl + total.unrealized_pnl : null)}</strong></p></div><p className="mt-3 text-xs text-slate-500">{c.budget}: {money(total.total_budget_limit)}</p>{(data.bots || []).map((bot) => <p key={bot.bot_id} className="mt-2 border-t pt-2 text-sm">{bot.name || bot.symbol} · {c.total}: {money(bot.equity)} · {c.cash}: {money(bot.cash_eur)}</p>)}</div>; })}</div>
    </Section>
    <Section title={c.analysis} prose={prose.analysis}>
      <div className="mt-5 space-y-4">{assets.map((asset, index) => { const score = number(asset.benchmark_score); const parts = asset.reported_scores || {}; return <div key={`${reportMarketLabel(asset)}-${index}`} className="rounded-xl border border-slate-200 p-4"><h3 className="font-bold">{reportMarketLabel(asset)} · {c.benchmark}: {score === null ? c.unknown : `${score}/100`}</h3><ScoreScale score={score} labels={c.zones} unknown={c.unknown} /><div className="mt-4 grid grid-cols-3 gap-2 text-sm"><p>{c.market}: {number(parts.market_score) ?? c.unknown}</p><p>{c.macro}: {number(parts.macro_score) ?? c.unknown}</p><p>{c.technical}: {number(parts.technical_score) ?? c.unknown}</p></div>{['market', 'macro', 'technical'].map((category) => <div key={category} className="mt-2 text-xs text-slate-600"><strong>{c[category]}:</strong> {(asset.configured_indicators?.[category] || []).length ? (asset.configured_indicators[category] || []).map((name) => { const evidence = asset.verified_indicator_evidence?.[category]?.[name]; const parts = [name, measured(evidence?.value), number(evidence?.score) === null ? c.unknown : `${evidence.score}/100`, evidence?.source_observed_at ? `${c.observed}: ${timestamp(evidence.source_observed_at)}` : null]; return parts.filter(Boolean).join(' · '); }).join('; ') : c.unknown}</div>)}</div>; })}</div>
    </Section>
    <Section title={c.plan} prose={prose.plan}>
      <div className="mt-5 space-y-4">{plans.flatMap((asset) => (asset.setups || []).map((setup) => { const strategies = (asset.strategies || []).filter((row) => row.setup_id === setup.id); const hasCondition = number(setup.min_benchmark_score) !== null || number(setup.max_benchmark_score) !== null; return <div key={`${asset.pair || asset.symbol}-${setup.id}`} className="rounded-xl border border-slate-200 p-4"><h3 className="font-bold">{setup.name || asset.pair || asset.symbol}</h3><p className="mt-2 text-sm">{asset.pair || asset.symbol} · {c.timeframe}: {setup.timeframe || c.unknown}</p>{setup.setup_type === 'dca' && <p className="text-sm">{c.frequency}: {cadence(setup)}</p>}<p className="text-sm">{c.conditions}: {hasCondition ? `${setup.min_benchmark_score ?? 0}–${setup.max_benchmark_score ?? 100}` : c.noConditions}</p>{strategies.map((strategy) => <p key={strategy.id} className="mt-2 border-t pt-2 text-sm">{strategy.name} · {strategy.execution_mode === 'custom' ? c.curve : c.fixed} · {c.amount}: {money(strategy.base_amount)}{strategy.execution_mode === 'custom' && Array.isArray(strategy.decision_curve?.points) ? ` · ${strategy.decision_curve.points.map((point) => `${point.x}→${Math.round(point.y * 100)}%`).join(', ')}` : ''}</p>)}</div>; }))}{plans.every((asset) => !(asset.setups || []).length) && <p>{c.noPlans}</p>}</div>
    </Section>
    <Section title={c.automation} prose={prose.automation}>
      <div className="mt-5 space-y-4">{bots.length ? bots.map((bot) => { const decision = bot.latest_decision; const reason = (decision?.block_code && t?.botPage?.focus?.riskCodes?.[decision.block_code]) || (decision?.reason_key && traderCopy.reasons?.[decision.reason_key]) || decision?.reason; return <div key={bot.bot_id} className="rounded-xl border border-slate-200 p-4"><h3 className="font-bold">{bot.bot_name || bot.strategy_name || bot.symbol} · {bot.is_live ? c.live : c.paper} · {bot.is_active ? traderCopy.active : traderCopy.paused}</h3><p className="mt-2 text-sm">{bot.trading_pair || bot.symbol} · {c.position}: {number(bot.position_qty) ?? c.unknown} · {c.total}: {money(bot.position_value_eur)}</p>{number(bot.position_qty) > 0 && <p className="text-sm">{c.stop}: {number(bot.stop_loss) === null ? c.unknown : `${bot.stop_loss} ${bot.level_currency || ''}`} · {c.target}: {number(bot.first_target) === null ? c.unknown : `${bot.first_target} ${bot.level_currency || ''}`} · {c.exit}: {traderCopy.monitoring?.[bot.exit_monitoring] || traderCopy.monitoring?.unknown || c.unknown}</p>}<p className="mt-2 text-sm">{c.decision}: {decision ? `${traderCopy.actions?.[decision.action] || traderCopy.actions?.other || c.unknown} · ${timestamp(decision.at)}${reason ? ` · ${reason}` : ''}` : c.noDecision}</p></div>; }) : <p>{c.noBots}</p>}</div>
    </Section>
    <Section title={c.outlook} prose={prose.outlook_v2} />
  </div>;
}
