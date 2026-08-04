import { StatusTone } from '../constants/theme';
import { DomainScore } from '../types/scores';
import { AssistantInsightResponse, MobileOverviewResponse } from './tradamindApi';

type UnknownRecord = Record<string, unknown>;
const EMPTY_VALUE = '—';

export function mapAssistantInsightToBriefing(insight?: AssistantInsightResponse) {
  if (!insight) return { asset: '', status: EMPTY_VALUE, summary: '', risk: '', nextAction: '', updatedAt: nowLabel() };

  const marketInsight = insightText(insight.market_insight);
  const botInsight = insightText(insight.bot_insight);
  const context = insightText(insight.context_detected);

  return {
    asset: insight.context_detected?.symbol || '',
    status: context || EMPTY_VALUE,
    summary: insight.greeting || marketInsight || '',
    risk: botInsight || '',
    nextAction: '',
    updatedAt: nowLabel(),
  };
}

export function mapAssistantInsightCard(insight?: AssistantInsightResponse) {
  const marketInsight = insightText(insight?.market_insight);
  const botInsight = insightText(insight?.bot_insight);

  return {
    body: marketInsight || botInsight || '',
    title: insight?.greeting || '',
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

  const activeAsset = overview.watchlist[0]?.symbol || insight?.context_detected?.symbol || '';
  const activeBots = overview.portfolio.active_bots_count;
  const totalProfit = overview.portfolio.total_profit_pct;
  const risk =
    activeBots > 0
      ? `${activeBots}`
      : EMPTY_VALUE;

  return {
    asset: activeAsset,
    status: totalProfit >= 0 ? 'Mobile overview live' : 'Portfolio needs attention',
    summary: `${overview.finn_briefing.greeting} ${overview.finn_briefing.summary}`.trim(),
    risk,
    nextAction: overview.finn_briefing.suggested_actions[0] || '',
    updatedAt: nowLabel(),
  };
}

export function mapMobileOverviewPrompts(overview?: MobileOverviewResponse) {
  const actions = overview?.finn_briefing.suggested_actions.filter(Boolean) ?? [];
  return actions.length > 0 ? actions.slice(0, 4) : [];
}

export function mapMobileOverviewMarket(overview?: MobileOverviewResponse, symbol?: string) {
  const asset =
    overview?.watchlist.find((item) => item.symbol === symbol) ??
    overview?.watchlist[0];

  if (!asset) {
    return {
      change24h: EMPTY_VALUE,
      interpretation: '',
      price: EMPTY_VALUE,
      symbol: symbol || '',
      tone: 'neutral' as StatusTone,
      volume: EMPTY_VALUE,
    };
  }

  const change = asset.change_24h;
  const tone = typeof change === 'number' ? (change >= 0 ? 'success' : 'warning') : 'neutral';
  const compositeScore = Math.round(
    (asset.macro_score + asset.market_score + asset.technical_score + asset.setup_score) / 4,
  );

  return {
    change24h: typeof change === 'number' ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}%` : EMPTY_VALUE,
    interpretation: '',
    price: typeof asset.price === 'number' ? formatMoney(asset.price, 'USD') : EMPTY_VALUE,
    symbol: asset.symbol,
    tone: tone as StatusTone,
    volume: EMPTY_VALUE,
  };
}

export function mapMobileOverviewDecision(overview?: MobileOverviewResponse) {
  const asset = overview?.watchlist[0];
  if (!asset) {
    return {
      reason: '',
      score: 0,
      state: EMPTY_VALUE,
    };
  }

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
    reason: '',
    score,
    state,
  };
}

export function mapMobileOverviewBotDecision(overview?: MobileOverviewResponse) {
  const bot = overview?.active_bots.find((item) => item.is_active) ?? overview?.active_bots[0];
  if (!bot) {
    return {
      action: EMPTY_VALUE,
      amount: EMPTY_VALUE,
      botName: EMPTY_VALUE,
      confidence: 0,
      guardrail: '',
      reason: '',
      tone: 'neutral' as StatusTone,
    };
  }

  const profit = typeof bot.profit_pct === 'number' ? `${bot.profit_pct >= 0 ? '+' : ''}${bot.profit_pct.toFixed(2)}%` : EMPTY_VALUE;

  return {
    action: bot.is_active ? 'Monitor' : 'Inactive',
    amount: formatMoney(bot.invested_eur, 'EUR'),
    botName: bot.name,
    confidence: clampScore(bot.profit_pct === null || bot.profit_pct === undefined ? 50 : 50 + bot.profit_pct),
    guardrail: '',
    reason: `${formatMoney(bot.position_value_eur ?? bot.invested_eur, 'EUR')} · ${profit}`,
    tone: bot.is_active ? ('accent' as StatusTone) : ('neutral' as StatusTone),
  };
}

export function mapMobileOverviewPortfolio(overview?: MobileOverviewResponse) {
  if (!overview) {
    return { activeTrades: EMPTY_VALUE, botStatus: EMPTY_VALUE, cash: EMPTY_VALUE, exposure: EMPTY_VALUE, pnl: EMPTY_VALUE, totalValue: EMPTY_VALUE };
  }

  const invested = overview.portfolio.total_invested_eur;
  const balance = overview.portfolio.total_balance_eur;
  const exposure = balance > 0 ? Math.round((invested / balance) * 100) : 0;
  const pnl = overview.portfolio.total_profit_pct;

  return {
    activeTrades: `${overview.active_bots.length}`,
    botStatus: `${overview.portfolio.active_bots_count}`,
    cash: `${Math.max(0, 100 - exposure)}%`,
    exposure: `${exposure}%`,
    pnl: `${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%`,
    totalValue: formatMoney(balance, 'EUR'),
  };
}

export function mapMasterDecision(master?: UnknownRecord) {
  const rawScore = readNumber(master, ['master_score', 'score', 'value'], Number.NaN);
  const score = Number.isFinite(rawScore) ? clampScore(rawScore) : 0;
  const state =
    readString(master, ['bias', 'outlook', 'trend', 'state'], '') ||
    (Number.isFinite(rawScore)
      ? score >= 70
        ? 'Risk-on, selective'
        : score >= 50
          ? 'Neutral, wait for confirmation'
          : 'Risk-off'
      : EMPTY_VALUE);

  return {
    reason:
      readString(master, ['summary', 'reason', 'explanation'], '') ||
      '',
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
    const fallback = { score: 0, summary: '', trend: EMPTY_VALUE };
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
    change24h: Number.isFinite(change) ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}%` : EMPTY_VALUE,
    interpretation:
      readString(latest, ['interpretation', 'summary'], '') ||
      '',
    price: Number.isFinite(price) ? formatMoney(price) : EMPTY_VALUE,
    symbol,
    tone: tone as StatusTone,
    volume: Number.isFinite(volume) ? compactNumber(volume) : EMPTY_VALUE,
  };
}

export function mapWatchlistAssets(symbols?: string[], scores?: UnknownRecord, latest?: UnknownRecord) {
  const list = symbols && symbols.length > 0 ? symbols : [];
  if (list.length === 0) return [];
  const master = mapMasterDecision(scores);
  const change = mapMarketSnapshot(list[0] ?? '', latest).change24h;

  return list.slice(0, 6).map((symbol, index) => {
    const fallback = { change: EMPTY_VALUE, score: 0, setup: EMPTY_VALUE, tone: 'neutral' as StatusTone };
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
  if (!strategy) {
    return {
      bias: EMPTY_VALUE,
      confidence: 0,
      entryZone: EMPTY_VALUE,
      explanation: '',
      invalidation: EMPTY_VALUE,
      status: EMPTY_VALUE,
      symbol: '',
      targets: [],
    };
  }

  const symbol = readString(strategy, ['symbol', 'asset', 'ticker'], '');
  const targets = readArray(strategy, ['targets', 'take_profit_targets', 'take_profits']).map(String);
  const confidence = clampScore(readNumber(strategy, ['confidence', 'confidence_score', 'score'], 0));

  return {
    bias: readString(strategy, ['bias', 'direction', 'market_bias'], EMPTY_VALUE),
    confidence,
    entryZone:
      readString(strategy, ['entry_zone', 'entry', 'entry_price'], '') ||
      rangeLabel(strategy, ['entry_min', 'entry_low'], ['entry_max', 'entry_high']) ||
      EMPTY_VALUE,
    explanation:
      readString(strategy, ['explanation', 'summary', 'reasoning', 'description'], '') ||
      '',
    invalidation:
      readString(strategy, ['invalidation', 'stop_loss', 'stop'], '') ||
      EMPTY_VALUE,
    status: readString(strategy, ['status', 'state'], EMPTY_VALUE),
    symbol,
    targets: targets.length > 0 ? targets : [],
  };
}

export function mapBotDecision(botSource?: unknown) {
  const bot = firstObject(botSource);
  if (!bot) {
    return {
      action: EMPTY_VALUE,
      amount: EMPTY_VALUE,
      botName: EMPTY_VALUE,
      confidence: 0,
      guardrail: '',
      reason: '',
      tone: 'neutral' as StatusTone,
    };
  }

  const action = readString(bot, ['action', 'decision', 'recommendation'], EMPTY_VALUE);
  const confidence = clampScore(readNumber(bot, ['confidence', 'confidence_score'], 0));
  const reasons = readArray(bot, ['reasons', 'reason_json']).map(String).filter(Boolean);
  const amount = readNumber(bot, ['amount_eur', 'final_amount_eur', 'requested_amount_eur'], NaN);
  const amountLabel =
    readString(bot, ['amount', 'final_amount', 'requested_amount'], '') ||
    (Number.isFinite(amount) ? formatMoney(amount, 'EUR') : EMPTY_VALUE);

  return {
    action,
    amount: amountLabel,
    botName: readString(bot, ['bot_name', 'name', 'strategy_name'], EMPTY_VALUE),
    confidence,
    guardrail:
      readString(bot, ['guardrail', 'guardrails_result', 'guardrail_result', 'guardrail_reason', 'guardrails'], '') ||
      '',
    reason:
      readString(bot, ['reason', 'summary', 'explanation'], '') ||
      reasons.slice(0, 2).join(' ') ||
      '',
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
    return { activeTrades: EMPTY_VALUE, botStatus: EMPTY_VALUE, cash: EMPTY_VALUE, exposure: EMPTY_VALUE, pnl: EMPTY_VALUE, totalValue: EMPTY_VALUE };
  }

  const exposure = total > 0 && cash > 0 ? Math.max(0, Math.round(((total - cash) / total) * 100)) : null;

  return {
    activeTrades: `${readNumber(firstObject(portfolioItems), ['active_trades', 'trades_count'], portfolioItems.length)}`,
    botStatus: `${botItems.length || 0}`,
    cash: cash > 0 ? `${formatMoney(cash)}` : EMPTY_VALUE,
    exposure: exposure === null ? EMPTY_VALUE : `${exposure}%`,
    pnl: readString(firstObject(portfolioItems), ['pnl_label', 'daily_pnl'], EMPTY_VALUE),
    totalValue: formatMoney(total),
  };
}

export function mapReport(report?: UnknownRecord) {
  if (!report) {
    return {
      body: '',
      highlights: [],
      title: '',
    };
  }

  const title =
    readString(report, ['title', 'headline'], '') ||
    readString(report, ['summary', 'executive_summary'], '');
  const body =
    readString(report, ['ai_commentary', 'commentary', 'summary', 'content'], '') ||
    '';

  const highlights = [
    {
      title: 'Conclusion',
      value: firstText(report, ['conclusions', 'key_conclusions', 'takeaways']) || title,
      tone: 'accent' as StatusTone,
    },
    {
      title: 'Risk',
      value: firstText(report, ['risks', 'risk_notes', 'warnings']) || '',
      tone: 'warning' as StatusTone,
    },
    {
      title: 'Reflection',
      value: firstText(report, ['reflection', 'notes']) || '',
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
  if (!Number.isFinite(value) || value <= 0) return EMPTY_VALUE;
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
