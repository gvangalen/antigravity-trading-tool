import { StatusTone } from '../constants/theme';

export type DomainScore = {
  label: 'Macro' | 'Market' | 'Technical' | 'Setup';
  score: number;
  trend: string;
  summary: string;
  tone: StatusTone;
};

export const mockDomainScores: DomainScore[] = [
  {
    label: 'Macro',
    score: 68,
    trend: 'Supportive',
    summary: 'Liquidity backdrop is neutral to constructive.',
    tone: 'accent',
  },
  {
    label: 'Market',
    score: 74,
    trend: 'Improving',
    summary: 'Risk appetite is recovering, but volume is not euphoric.',
    tone: 'success',
  },
  {
    label: 'Technical',
    score: 71,
    trend: 'Trend intact',
    summary: 'Momentum supports the plan while price holds the entry zone.',
    tone: 'success',
  },
  {
    label: 'Setup',
    score: 63,
    trend: 'Waiting',
    summary: 'Setup is valid, but entry quality still needs confirmation.',
    tone: 'warning',
  },
];

export const mockBriefing = {
  asset: 'BTC',
  status: 'Constructive, not aggressive',
  summary:
    'Market and technical scores support the current plan, but the setup is still waiting for a cleaner entry.',
  risk: 'Entry is close to resistance. Avoid increasing size before confirmation.',
  nextAction: 'Review setup',
  updatedAt: '09:42',
};

export const mockMarketSnapshot = {
  symbol: 'BTC',
  price: '$68,420',
  change24h: '+1.8%',
  volume: 'Healthy',
  interpretation: 'Price is constructive above the weekly entry band.',
  tone: 'success' as StatusTone,
};

export const mockStrategy = {
  symbol: 'BTC',
  bias: 'Bullish, selective',
  confidence: 72,
  status: 'Valid, entry pending',
  entryZone: '$67,800 - $68,600',
  targets: ['$70,200', '$72,000', '$74,500'],
  invalidation: '$66,900',
  explanation:
    'The plan remains valid while BTC holds the entry band. Risk/reward improves after confirmation instead of chasing the current candle.',
};

export const mockBotDecision = {
  botName: 'BTC Weekly Strategy Bot',
  action: 'Hold / wait',
  confidence: 69,
  amount: '€0',
  guardrail: 'Buy blocked until setup confirmation improves.',
  reason: 'The bot sees constructive trend, but entry quality is not clean enough for new allocation.',
  tone: 'warning' as StatusTone,
};

export const mockDraft = {
  type: 'Strategy Draft',
  asset: 'SOL',
  title: 'SOL Pullback Strategy',
  purpose: 'Prepare a selective trade plan for a controlled pullback.',
  parameters: ['Entry: $145.50', 'Targets: $160 / $180', 'Stop: $135', 'Base: €100'],
  risk: 'Targets are assumed from current market structure. Review before saving.',
};

export const mockWarning = {
  severity: 'Caution',
  title: 'Strategy needs confirmation',
  body: 'The current setup is not invalidated, but the entry is too close to resistance for aggressive sizing.',
  nextStep: 'Wait for confirmation or reduce planned size.',
};

export const mockPrompts = [
  'Wat is het belangrijkste risico nu?',
  'Leg mijn setup uit',
  'Hoe staat mijn portfolio ervoor?',
  'Vat mijn daily report samen',
];

export const mockWatchlistAssets = [
  { symbol: 'BTC', score: 71, setup: 'Entry pending', change: '+1.8%', tone: 'success' as StatusTone },
  { symbol: 'ETH', score: 64, setup: 'Watch pullback', change: '+0.9%', tone: 'accent' as StatusTone },
  { symbol: 'SOL', score: 58, setup: 'Needs confirmation', change: '-0.4%', tone: 'warning' as StatusTone },
];

export const mockPortfolioStatus = {
  totalValue: '€24,860',
  pnl: '+€420 today',
  cash: '18% cash',
  exposure: '62% crypto exposure',
  activeTrades: '2 active trades',
  botStatus: '1 bot monitoring, no execution pending',
};

export const mockReportHighlights = [
  { title: 'Market posture', value: 'Constructive but selective', tone: 'accent' as StatusTone },
  { title: 'Main risk', value: 'Chasing entries near resistance', tone: 'warning' as StatusTone },
  { title: 'Reflection', value: 'Waiting is aligned with the current setup', tone: 'success' as StatusTone },
];
