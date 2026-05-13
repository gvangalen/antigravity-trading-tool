import { AssistantEnvelope, AssistantHistoryMessage, AssistantRuntimeContext } from '../types/assistant';
import { apiClient } from './apiClient';

export type AssistantInsightResponse = {
  greeting: string;
  bot_insight?: Record<string, string> | null;
  market_insight?: Record<string, string> | null;
  context_detected?: Record<string, string> | null;
  suggested_actions?: string[];
};

export type MobileOverviewAsset = {
  symbol: string;
  price?: number | null;
  change_24h?: number | null;
  macro_score: number;
  technical_score: number;
  market_score: number;
  setup_score: number;
};

export type MobileOverviewBot = {
  bot_id: number;
  name: string;
  symbol: string;
  is_active: boolean;
  is_live: boolean;
  invested_eur: number;
  position_value_eur?: number | null;
  profit_pct?: number | null;
};

export type MobileOverviewPortfolio = {
  total_balance_eur: number;
  total_invested_eur: number;
  total_profit_pct: number;
  active_bots_count: number;
};

export type MobileOverviewFinnBriefing = {
  greeting: string;
  summary: string;
  suggested_actions: string[];
};

export type MobileOverviewResponse = {
  user_id: number;
  portfolio: MobileOverviewPortfolio;
  watchlist: MobileOverviewAsset[];
  active_bots: MobileOverviewBot[];
  finn_briefing: MobileOverviewFinnBriefing;
  intelligence_events?: MobileIntelligenceEvent[] | null;
};

export type MobileIntelligenceEvent = {
  id: number;
  type: string;
  symbol?: string | null;
  title: string;
  description: string;
  severity: string;
  created_at: string;
};

export type WatchlistResponse = string[];

export type DailyScoresResponse = Record<string, unknown>;
export type MasterScoreResponse = Record<string, unknown>;
export type MarketLatestResponse = Record<string, unknown>;
export type MarketChartPoint = {
  id: number;
  symbol: string;
  date: string;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  change?: number | null;
  volume?: number | null;
  created_at: string;
};
export type SetupResponse = Record<string, unknown> | Record<string, unknown>[];
export type StrategyResponse = Record<string, unknown> | Record<string, unknown>[];
export type BotResponse = Record<string, unknown> | Record<string, unknown>[];
export type PortfolioResponse = Record<string, unknown> | Record<string, unknown>[];
export type MobileReportHighlight = {
  category?: string | null;
  name?: string | null;
  value?: string | number | null;
  score?: string | number | null;
  interpretation?: string | null;
};

export type MobileReportResponse = {
  _status?: string;
  report_date?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  generated_at?: string | null;
  executive_summary_compact?: string | null;
  market_analysis_compact?: string | null;
  outlook_compact?: string | null;
  kpi_metrics?: Record<string, unknown> | null;
  highlights?: MobileReportHighlight[];
  best_setup?: unknown;
  top_setups?: unknown[];
  bot_snapshot?: unknown;
  active_strategy?: unknown;
  watchlist?: unknown[];
};

export type ReportResponse = Record<string, unknown>;

export const assistantApi = {
  insight(context: AssistantRuntimeContext) {
    return apiClient.post<AssistantInsightResponse>('/api/assistant/insight', context);
  },

  chat(query: string, context: AssistantRuntimeContext, history?: AssistantHistoryMessage[]) {
    return apiClient.post<AssistantEnvelope>('/api/assistant/chat', {
      context,
      history,
      query,
    });
  },
};

export const mobileApi = {
  overview() {
    return apiClient.get<MobileOverviewResponse>('/api/dashboard/mobile-overview');
  },
};

export const intelligenceApi = {
  watchlist() {
    return apiClient.get<WatchlistResponse>('/api/watchlist');
  },

  marketLatest(symbol: string) {
    return apiClient.get<MarketLatestResponse>(`/api/market_data/${encodeURIComponent(symbol)}/latest`);
  },

  marketChart7d(symbol: string) {
    return apiClient.get<MarketChartPoint[]>('/api/market_data/7d', { symbol });
  },

  dailyScores(symbol: string) {
    return apiClient.get<DailyScoresResponse>('/api/scores/daily', { symbol });
  },

  masterScore(symbol: string) {
    return apiClient.get<MasterScoreResponse>('/api/ai/master_score', { symbol });
  },

  activeSetups(symbol?: string) {
    return apiClient.get<SetupResponse>('/api/setups/active', { symbol });
  },

  topSetups() {
    return apiClient.get<SetupResponse>('/api/setups/top');
  },

  activeStrategyToday() {
    return apiClient.get<StrategyResponse>('/api/strategies/active-today');
  },

  lastStrategy() {
    return apiClient.get<StrategyResponse>('/api/strategies/last');
  },

  botToday(symbol: string) {
    return apiClient.get<BotResponse>('/api/bot/today', { symbol });
  },

  skipBotToday(payload: { bot_id: number; report_date?: string | null }) {
    return apiClient.post<BotResponse>('/api/bot/skip', payload);
  },

  markBotExecuted(payload: { bot_id: number; decision_id: number }) {
    return apiClient.post<BotResponse>('/api/bot/mark_executed', payload);
  },

  botConfigs() {
    return apiClient.get<BotResponse>('/api/bot/configs');
  },

  botPortfolios() {
    return apiClient.get<PortfolioResponse>('/api/bot/portfolios');
  },

  exchangeBalances() {
    return apiClient.get<PortfolioResponse>('/api/exchange/balances');
  },

  balanceHistory(options?: { bucket?: string; limit?: number; is_live?: boolean | null }) {
    return apiClient.get<PortfolioResponse>('/api/portfolio/balance-history', options);
  },

  latestDailyReport(symbol?: string, format?: 'mobile') {
    return apiClient.get<MobileReportResponse>('/api/report/daily/latest', { format, symbol });
  },

  latestDailyReportFull(symbol?: string) {
    return apiClient.get<ReportResponse>('/api/report/daily/latest', { symbol });
  },

  latestWeeklyReport(format?: 'mobile') {
    return apiClient.get<MobileReportResponse>('/api/report/weekly/latest', { format });
  },

  latestWeeklyReportFull() {
    return apiClient.get<ReportResponse>('/api/report/weekly/latest');
  },

  latestMonthlyReport(format?: 'mobile') {
    return apiClient.get<MobileReportResponse>('/api/report/monthly/latest', { format });
  },

  latestMonthlyReportFull() {
    return apiClient.get<ReportResponse>('/api/report/monthly/latest');
  },

  latestQuarterlyReport(format?: 'mobile') {
    return apiClient.get<MobileReportResponse>('/api/report/quarterly/latest', { format });
  },

  latestQuarterlyReportFull() {
    return apiClient.get<ReportResponse>('/api/report/quarterly/latest');
  },
};

export async function optionalApi<T>(promise: Promise<T>): Promise<T | undefined> {
  try {
    return await promise;
  } catch {
    return undefined;
  }
}
