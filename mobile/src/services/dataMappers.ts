import { StatusTone } from '../constants/theme';
import { DomainScore } from '../types/scores';
import { AssistantInsightResponse, MobileOverviewResponse } from './tradamindApi';

type UnknownRecord = Record<string, unknown>;

export function mapAssistantInsightToBriefing(insight?: AssistantInsightResponse) {
  if (!insight) return { asset: 'BTC', status: 'Wachten op data', summary: 'Nog geen actieve FINN-context beschikbaar.', risk: 'Dat kan normaal zijn vlak na verversen of in een rustige sessie.', nextAction: 'Ververs of vraag Finn om context', updatedAt: nowLabel() };

  const marketInsight = insightText(insight.market_insight);
  const botInsight = insightText(insight.bot_insight);
  const context = insightText(insight.context_detected);

  return {
    asset: insight.context_detected?.symbol || 'BTC',
    status: context || 'Live Finn context',
    summary: insight.greeting || marketInsight || 'Nog geen samenvatting beschikbaar.',
    risk: botInsight || 'Mobile blijft read-only voor execution. Review context eerst voordat je iets bevestigt.',
    nextAction: 'Vraag Finn om de volgende stap',
    updatedAt: nowLabel(),
  };
}

export function mapAssistantInsightCard(insight?: AssistantInsightResponse) {
  const marketInsight = insightText(insight?.market_insight);
  const botInsight = insightText(insight?.bot_insight);

  return {
    body: marketInsight || botInsight || 'Nog geen samenvatting beschikbaar.',
    title: insight?.greeting || 'Finn leest je huidige tradingcontext.',
  };
}

export function mapAssistantInsightDetails(insight?: AssistantInsightResponse) {
  return {
    bot: insightText(insight?.bot_insight),
    context: insightText(insight?.context_detected),
    market: insightText(insight?.market_insight),
  };
}

export function mapMobileOverviewBriefing(overview?: MobileOverviewResponse, insight?: AssistantInsightResponse) {
  if (!overview) return mapAssistantInsightToBriefing(insight);

  const activeAsset = overview.watchlist[0]?.symbol || insight?.context_detected?.symbol || 'BTC';
  const activeBots = overview.portfolio.active_bots_count;
  const totalProfit = overview.portfolio.total_profit_pct;
  const risk =
    activeBots > 0
      ? `${activeBots} actieve bot${activeBots === 1 ? '' : 's'} in read-only mobile review. Geen execution vanuit FINN.`
      : 'Geen actieve bot-exposure in de mobile overview. Gebruik FINN alleen voor analyse en voorbereiding.';

  return {
    asset: activeAsset,
    status: totalProfit >= 0 ? 'Mobile overview live' : 'Portfolio needs attention',
    summary: `${overview.finn_briefing.greeting} ${overview.finn_briefing.summary}`.trim(),
    risk,
    nextAction: overview.finn_briefing.suggested_actions[0] || 'Vraag Finn om de volgende stap',
    updatedAt: nowLabel(),
  };
}

export function mapMobileOverviewPrompts(overview?: MobileOverviewResponse) {
  const actions = overview?.finn_briefing.suggested_actions.filter(Boolean) ?? [];
  return actions.length > 0 ? actions.slice(0, 4) : ['Leg mijn setup uit', 'Wat is het grootste risico?'];
}

export function mapMobileOverviewMarket(overview?: MobileOverviewResponse, symbol?: string) {
  const asset =
    overview?.watchlist.find((item) => item.symbol === symbol) ??
    overview?.watchlist[0];

  if (!asset) return { change24h: 'n/a', interpretation: 'Geen data', price: 'n/a', symbol: symbol || 'BTC', tone: 'neutral' as StatusTone, volume: 'n/a' };

  const change = asset.change_24h;
  const tone = typeof change === 'number' ? (change >= 0 ? 'success' : 'warning') : 'neutral';
  const compositeScore = Math.round(
    (asset.macro_score + asset.market_score + asset.technical_score + asset.setup_score) / 4,
  );

  return {
    change24h: typeof change === 'number' ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}%` : 'n/a',
    interpretation: `${asset.symbol} mobile context is live. Composite score ${compositeScore}, setup score ${Math.round(asset.setup_score)}.`,
    price: typeof asset.price === 'number' ? formatMoney(asset.price, 'USD') : 'n/a',
    symbol: asset.symbol,
    tone: tone as StatusTone,
    volume: 'Mobile overview',
  };
}

export function mapMobileOverviewDecision(overview?: MobileOverviewResponse) {
  const asset = overview?.watchlist[0];
  if (!asset) return mapMasterDecision(undefined);

  const score = clampScore(
    (asset.macro_score + asset.market_score + asset.technical_score + asset.setup_score) / 4,
  );
  const state =
    asset.macro_label ||
    (score >= 70
      ? 'Constructive, selective'
      : score >= 50
        ? 'Neutral, wait for confirmation'
        : 'Defensive, review risk');

  return {
    reason: `${asset.symbol} blends macro ${Math.round(asset.macro_score)}, market ${Math.round(asset.market_score)}, technical ${Math.round(asset.technical_score)} and setup ${Math.round(asset.setup_score)} from the mobile overview.`,
    score,
    state,
  };
}

export function mapMobileOverviewBotDecision(overview?: MobileOverviewResponse) {
  const bot = overview?.active_bots.find((item) => item.is_active) ?? overview?.active_bots[0];
  if (!bot) return { action: 'Geen actie', amount: 'n/a', botName: 'Geen actieve bot', confidence: 0, guardrail: 'Geen data.', reason: 'Geen bot geconfigureerd.', tone: 'neutral' as StatusTone };

  const liveLabel = bot.is_live ? 'Live bot' : 'Paper/read-only bot';
  const profit = typeof bot.profit_pct === 'number' ? `${bot.profit_pct >= 0 ? '+' : ''}${bot.profit_pct.toFixed(2)}%` : 'n/a';

  return {
    action: bot.is_active ? 'Monitor' : 'Inactive',
    amount: formatMoney(bot.invested_eur, 'EUR'),
    botName: bot.name,
    confidence: clampScore(bot.profit_pct === null || bot.profit_pct === undefined ? 50 : 50 + bot.profit_pct),
    guardrail: `${liveLabel}. FINN toont context, maar voert geen orders uit op mobiel.`,
    reason: `${bot.symbol} bot exposure is ${formatMoney(bot.position_value_eur ?? bot.invested_eur, 'EUR')} with current PnL ${profit}.`,
    tone: bot.is_active ? ('accent' as StatusTone) : ('neutral' as StatusTone),
  };
}

export function mapMobileOverviewPortfolio(overview?: MobileOverviewResponse) {
  if (!overview) return { activeTrades: 'Geen data', botStatus: 'Geen data', cash: 'n/a', exposure: 'n/a', pnl: 'n/a', totalValue: 'n/a' };

  const invested = overview.portfolio.total_invested_eur;
  const balance = overview.portfolio.total_balance_eur;
  const exposure = balance > 0 ? Math.round((invested / balance) * 100) : 0;
  const pnl = overview.portfolio.total_profit_pct;

  return {
    activeTrades: `${overview.active_bots.length} bot${overview.active_bots.length === 1 ? '' : 's'} loaded`,
    botStatus: `${overview.portfolio.active_bots_count} active bot${overview.portfolio.active_bots_count === 1 ? '' : 's'}, read-only mobile context`,
    cash: `${Math.max(0, 100 - exposure)}% unallocated`,
    exposure: `${exposure}% bot exposure`,
    pnl: `${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}% total bot PnL`,
    totalValue: formatMoney(balance, 'EUR'),
  };
}

export function mapMasterDecision(master?: UnknownRecord) {
  const score = clampScore(readNumber(master, ['master_score', 'score', 'value'], 71));
  const state =
    readString(master, ['bias', 'outlook', 'trend', 'state'], '') ||
    (score >= 70 ? 'Risk-on, selective' : score >= 50 ? 'Neutral, wait for confirmation' : 'Risk-off');

  return {
    reason:
      readString(master, ['summary', 'reason', 'explanation'], '') ||
      'Master score blends macro, market, technical and setup context for the active asset.',
    score,
    state,
  };
}

export function mapDailyScores(scores?: UnknownRecord): DomainScore[] {
  const domains: Array<[DomainScore['label'], string[]]> = [
    ['Macro', ['macro', 'macro_score']],
    ['Market', ['market', 'market_score']],
    ['Technical', ['technical', 'technical_score']],
    ['Setup', ['setup', 'setup_score']],
  ];

  return domains.map(([label, keys], index) => {
    const raw = firstRecord(scores, keys);
    const fallback = { score: 0, summary: 'Geen data', trend: 'n/a' };
    const value = clampScore(
      readNumber(raw, ['score', 'value', 'normalized_score'], readNumber(scores, keys, fallback.score)),
    );

    return {
      label,
      score: value,
      summary:
        readString(raw, ['interpretation', 'summary', 'explanation'], '') ||
        fallback.summary,
      tone: toneForScore(value),
      trend:
        readString(raw, ['trend', 'bias', 'status'], '') ||
        fallback.trend,
    };
  });
}

export function mapMarketSnapshot(symbol: string, latest?: UnknownRecord) {
  const price = readNumber(latest, ['price', 'close', 'last_price', 'current_price'], NaN);
  const change = readNumber(latest, ['change_24h', 'percent_change_24h', 'price_change_percentage_24h'], NaN);
  const volume = readNumber(latest, ['volume', 'volume_24h', 'total_volume'], NaN);
  const tone = Number.isFinite(change) ? (change >= 0 ? 'success' : 'warning') : 'neutral';

  return {
    change24h: Number.isFinite(change) ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}%` : 'n/a',
    interpretation:
      readString(latest, ['interpretation', 'summary'], '') ||
      `${symbol} market context is loaded from the backend when available.`,
    price: Number.isFinite(price) ? formatMoney(price) : 'n/a',
    symbol,
    tone: tone as StatusTone,
    volume: Number.isFinite(volume) ? compactNumber(volume) : 'n/a',
  };
}

export function mapWatchlistAssets(symbols?: string[], scores?: UnknownRecord, latest?: UnknownRecord) {
  const list = symbols && symbols.length > 0 ? symbols : ['BTC'];
  const master = mapMasterDecision(scores);
  const change = mapMarketSnapshot(list[0] ?? 'BTC', latest).change24h;

  return list.slice(0, 6).map((symbol, index) => {
    const fallback = { change: 'n/a', score: 0, setup: 'Geen data', tone: 'neutral' as StatusTone };
    return {
      change: index === 0 ? change : fallback.change,
      score: index === 0 ? master.score : fallback.score,
      setup: index === 0 ? master.state : fallback.setup,
      symbol,
      tone: index === 0 ? toneForScore(master.score) : fallback.tone,
    };
  });
}

export function mapStrategy(strategySource?: unknown, setupSource?: unknown) {
  const strategy = firstObject(strategySource) ?? firstObject(setupSource);
  if (!strategy) return { bias: 'n/a', confidence: 0, entryZone: 'n/a', explanation: 'Geen strategie gevonden.', invalidation: 'n/a', status: 'n/a', symbol: 'BTC', targets: [] };

  const symbol = readString(strategy, ['symbol', 'asset', 'ticker'], 'BTC');
  const targets = readArray(strategy, ['targets', 'take_profit_targets', 'take_profits']).map(String);
  const confidence = clampScore(readNumber(strategy, ['confidence', 'confidence_score', 'score'], 0));

  return {
    bias: readString(strategy, ['bias', 'direction', 'market_bias'], 'n/a'),
    confidence,
    entryZone:
      readString(strategy, ['entry_zone', 'entry', 'entry_price'], '') ||
      rangeLabel(strategy, ['entry_min', 'entry_low'], ['entry_max', 'entry_high']) ||
      'n/a',
    explanation:
      readString(strategy, ['explanation', 'summary', 'reasoning', 'description'], '') ||
      'Geen strategie gevonden.',
    invalidation:
      readString(strategy, ['invalidation', 'stop_loss', 'stop'], '') ||
      'n/a',
    status: readString(strategy, ['status', 'state'], 'n/a'),
    symbol,
    targets: targets.length > 0 ? targets : [],
  };
}

export function mapBotDecision(botSource?: unknown) {
  const bot = firstObject(botSource);
  if (!bot) return { action: 'Geen actie', amount: 'n/a', botName: 'Geen actieve bot', confidence: 0, guardrail: 'Geen data.', reason: 'Geen bot geconfigureerd.', tone: 'neutral' as StatusTone };

  const action = readString(bot, ['action', 'decision', 'recommendation'], 'Geen actie');
  const confidence = clampScore(readNumber(bot, ['confidence', 'confidence_score'], 0));
  const reasons = readArray(bot, ['reasons', 'reason_json']).map(String).filter(Boolean);
  const amount = readNumber(bot, ['amount_eur', 'final_amount_eur', 'requested_amount_eur'], NaN);
  const amountLabel =
    readString(bot, ['amount', 'final_amount', 'requested_amount'], '') ||
    (Number.isFinite(amount) ? formatMoney(amount, 'EUR') : 'n/a');

  return {
    action,
    amount: amountLabel,
    botName: readString(bot, ['bot_name', 'name', 'strategy_name'], 'Bot'),
    confidence,
    guardrail:
      readString(bot, ['guardrail', 'guardrails_result', 'guardrail_result', 'guardrail_reason', 'guardrails'], '') ||
      'Read-only mobile review. No execution is available in this client.',
    reason:
      readString(bot, ['reason', 'summary', 'explanation'], '') ||
      reasons.slice(0, 2).join(' ') ||
      'Geen reden gevonden.',
    tone: toneForAction(action, confidence),
  };
}

export function mapPortfolioStatus(portfolios?: unknown, balances?: unknown, botConfigs?: unknown) {
  const balanceItems = asArray(balances);
  const portfolioItems = asArray(portfolios);
  const botItems = asArray(botConfigs);
  const total = sumFields([...balanceItems, ...portfolioItems], ['value_eur', 'value', 'total_value', 'balance_eur']);
  const cash = sumFields(balanceItems, ['cash', 'cash_eur', 'available_eur', 'free']);

  if (total <= 0 && portfolioItems.length === 0 && balanceItems.length === 0) {
    return { activeTrades: 'Geen data', botStatus: 'Geen data', cash: 'n/a', exposure: 'n/a', pnl: 'n/a', totalValue: 'n/a' };
  }

  const exposure = total > 0 && cash > 0 ? Math.max(0, Math.round(((total - cash) / total) * 100)) : null;

  return {
    activeTrades: `${readNumber(firstObject(portfolioItems), ['active_trades', 'trades_count'], portfolioItems.length)} active trades`,
    botStatus: `${botItems.length || 0} bot${botItems.length === 1 ? '' : 's'} configured, read-only status`,
    cash: cash > 0 ? `${formatMoney(cash)} cash` : 'n/a',
    exposure: exposure === null ? 'n/a' : `${exposure}% exposure`,
    pnl: readString(firstObject(portfolioItems), ['pnl_label', 'daily_pnl'], 'n/a'),
    totalValue: formatMoney(total),
  };
}

export function mapReport(report?: UnknownRecord) {
  if (!report) {
    return {
      body:
        'The morning read favors patience: market structure is supportive, setup confirmation is incomplete, and portfolio exposure is already meaningful.',
      highlights: [],
      title: 'BTC remains constructive, but not urgent.',
    };
  }

  const title =
    readString(report, ['title', 'headline'], '') ||
    readString(report, ['summary', 'executive_summary'], 'Daily intelligence is ready.');
  const body =
    readString(report, ['ai_commentary', 'commentary', 'summary', 'content'], '') ||
    'FINN loaded the latest report. Open details from desktop for the full report body.';

  const highlights = [
    {
      title: 'Conclusion',
      value: firstText(report, ['conclusions', 'key_conclusions', 'takeaways']) || title,
      tone: 'accent' as StatusTone,
    },
    {
      title: 'Risk',
      value: firstText(report, ['risks', 'risk_notes', 'warnings']) || 'Review setup invalidation before taking action.',
      tone: 'warning' as StatusTone,
    },
    {
      title: 'Reflection',
      value: firstText(report, ['reflection', 'notes']) || 'Use FINN to translate this report into setup context.',
      tone: 'success' as StatusTone,
    },
  ];

  return { body, highlights, title };
}

export function nowLabel() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function firstObject(value: unknown): UnknownRecord | undefined {
  if (Array.isArray(value)) return value.find(isRecord);
  return isRecord(value) ? value : undefined;
}

function insightText(value: Record<string, string> | null | undefined) {
  if (!value) return '';
  return (
    value.summary ||
    value.insight ||
    value.message ||
    value.status ||
    value.context ||
    Object.values(value).find((item) => typeof item === 'string' && item.trim()) ||
    ''
  );
}

function firstRecord(source: UnknownRecord | undefined, keys: string[]) {
  for (const key of keys) {
    const value = source?.[key];
    if (isRecord(value)) return value;
  }
  return undefined;
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asArray(value: unknown): UnknownRecord[] {
  if (Array.isArray(value)) return value.filter(isRecord);
  if (isRecord(value)) return [value];
  return [];
}

function readString(source: UnknownRecord | undefined, keys: string[], fallback = '') {
  for (const key of keys) {
    const value = source?.[key];
    if (typeof value === 'string' && value.trim()) return value;
    if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  }
  return fallback;
}

function readNumber(source: UnknownRecord | undefined, keys: string[], fallback = 0) {
  for (const key of keys) {
    const value = source?.[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && Number.isFinite(Number(value))) return Number(value);
  }
  return fallback;
}

function readArray(source: UnknownRecord | undefined, keys: string[]) {
  for (const key of keys) {
    const value = source?.[key];
    if (Array.isArray(value)) return value;
    if (typeof value === 'string' && value.includes(',')) return value.split(',').map((item) => item.trim());
  }
  return [];
}

function firstText(source: UnknownRecord, keys: string[]) {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === 'string' && value.trim()) return value;
    if (Array.isArray(value) && value.length > 0) return String(value[0]);
  }
  return '';
}

function rangeLabel(source: UnknownRecord, lowKeys: string[], highKeys: string[]) {
  const low = readString(source, lowKeys);
  const high = readString(source, highKeys);
  return low && high ? `${low} - ${high}` : '';
}

function toneForScore(score: number): StatusTone {
  if (score >= 70) return 'success';
  if (score >= 55) return 'accent';
  if (score >= 40) return 'warning';
  return 'danger';
}

function toneForAction(action: string, confidence: number): StatusTone {
  const normalized = action.toLowerCase();
  if (normalized.includes('hold') || normalized.includes('wait') || normalized.includes('skip')) return 'warning';
  return toneForScore(confidence);
}

function clampScore(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function sumFields(items: UnknownRecord[], fields: string[]) {
  return items.reduce((total, item) => total + readNumber(item, fields, 0), 0);
}

function formatMoney(value: number, currency?: 'EUR' | 'USD') {
  if (!Number.isFinite(value) || value <= 0) return 'n/a';
  const currencyCode = currency ?? (value > 1000 ? 'EUR' : 'USD');
  return new Intl.NumberFormat('nl-NL', {
    currency: currencyCode,
    maximumFractionDigits: value > 1000 ? 0 : 2,
    style: 'currency',
  }).format(value);
}

function compactNumber(value: number) {
  return new Intl.NumberFormat('en', {
    maximumFractionDigits: 1,
    notation: 'compact',
  }).format(value);
}
