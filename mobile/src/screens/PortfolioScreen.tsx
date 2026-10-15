import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ScreenContainer } from '../components/layout/ScreenContainer';
import { useApiResource } from '../hooks/useApiResource';
import { translate } from '../i18n';
import { preferenceColors, useAppPreferences } from '../preferences/AppPreferencesProvider';
import { intelligenceApi, type PortfolioOverviewBot, type PortfolioOverviewResponse } from '../services/tradamindApi';
import { useFinnOverlay } from '../contexts/FinnOverlayContext';

type Environment = 'paper' | 'live';
type DetailTab = 'positions' | 'transactions' | 'limits';
type Trade = { id: number; side: string; qty: number; symbol: string; amount_eur: number | null; executed_at: string | null };
const isKnown = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

export function PortfolioScreen() {
  const { appearance, language } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const { openFinn } = useFinnOverlay();
  const [environment, setEnvironment] = useState<Environment>('paper');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>('positions');
  const [trades, setTrades] = useState<Trade[]>([]);
  const [tradesLoading, setTradesLoading] = useState(false);
  const [tradesError, setTradesError] = useState(false);
  const fetchOverview = useCallback(() => intelligenceApi.portfolioSummary(environment), [environment]);
  const overview = useApiResource<PortfolioOverviewResponse | null>({ fallbackData: null, fetcher: fetchOverview });
  const data = overview.data?.data;
  const bots = data?.bots ?? [];
  const selected = bots.find((bot) => bot.bot_id === selectedId);
  const global = data?.global;
  const valuationAvailable = Boolean(data?.valuation_available);
  const result = valuationAvailable && isKnown(global?.realized_pnl) && isKnown(global?.unrealized_pnl)
    ? global.realized_pnl + global.unrealized_pnl : null;
  const locale = language === 'de' ? 'de-DE' : language === 'nl' ? 'nl-NL' : 'en-US';
  const money = (value: number | null | undefined) => isKnown(value)
    ? new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR', maximumFractionDigits: 2 }).format(value)
    : '—';
  const time = (value: string | null | undefined) => value
    ? new Date(value).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' }) : null;
  const label = (key: string) => translate(language, `portfolio.v2.${key}` as Parameters<typeof translate>[1]);

  useEffect(() => { setSelectedId(null); setTrades([]); }, [environment]);
  useEffect(() => {
    if (!selectedId || detailTab !== 'transactions') return;
    let active = true;
    setTradesLoading(true);
    setTradesError(false);
    intelligenceApi.botTrades(selectedId)
      .then((items) => { if (active) setTrades(Array.isArray(items) ? items : []); })
      .catch(() => { if (active) { setTrades([]); setTradesError(true); } })
      .finally(() => { if (active) setTradesLoading(false); });
    return () => { active = false; };
  }, [selectedId, detailTab]);

  const status = data?.valuation_status === 'unreconciled_live' ? label('unreconciled')
    : data?.valuation_status === 'unfunded' ? label('unfunded')
      : data?.valuation_status === 'missing_price' ? label('missingPrice') : null;

  return <ScreenContainer refreshing={overview.refreshing} onRefresh={overview.refresh}>
    <View style={styles.header}>
      <Text style={[styles.title, { color: colors.text }]}>{translate(language, 'workspace.portfolio')}</Text>
      <View style={[styles.switch, { borderColor: colors.border }]}>
        {(['paper', 'live'] as Environment[]).map((item) => <Pressable key={item}
          accessibilityRole="button" accessibilityState={{ selected: environment === item }}
          onPress={() => setEnvironment(item)} style={[styles.switchButton, environment === item && { backgroundColor: colors.accent }]}>
          <Text style={{ color: environment === item ? '#fff' : colors.text }}>{label(item)}</Text>
        </Pressable>)}
      </View>
    </View>
    <Text style={[styles.note, { color: colors.textDim }]}>{environment === 'paper' ? label('paperMoney') : label('liveAttribution')}</Text>
    {overview.error && <Text style={[styles.notice, { color: colors.danger }]}>{label('loadError')}</Text>}
    {status && <Text style={[styles.notice, { color: colors.warning }]}>{status}</Text>}
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <View style={styles.metricGrid}>
        <Metric label={label('total')} value={money(valuationAvailable ? global?.total_equity : null)} colors={colors} />
        <Metric label={label('cash')} value={money(global?.cash_balance)} colors={colors} />
        <Metric label={label('positions')} value={money(global?.current_position_value)} colors={colors} />
        <Metric label={label('result')} value={money(result)} colors={colors} />
      </View>
      <Text style={[styles.small, { color: colors.textDim }]}>{label('readAt')}: {time(data?.read_at) ?? label('unknown')}</Text>
      {data?.valuation_as_of && <Text style={[styles.small, { color: colors.textDim }]}>{label('asOf')}: {time(data.valuation_as_of)}</Text>}
    </View>
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={[styles.sectionTitle, { color: colors.text }]}>{label('history')}</Text>
      <Text style={[styles.small, { color: colors.textDim }]}>{label('historyHint')}</Text>
      <Text style={[styles.notice, { color: colors.textDim }]}>{label('noHistory')}</Text>
    </View>
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <Text style={[styles.sectionTitle, { color: colors.text }]}>{label('byBot')}</Text>
      {bots.length === 0 && <Text style={[styles.notice, { color: colors.textDim }]}>{label('noBots')}</Text>}
      {bots.map((bot) => <Pressable key={bot.bot_id} onPress={() => { setSelectedId(bot.bot_id); setDetailTab('positions'); }}
        style={[styles.botRow, { borderColor: colors.border }]} accessibilityRole="button" accessibilityLabel={`${label('details')}: ${bot.name ?? bot.symbol}`}>
        <View style={styles.botName}><Text style={[styles.botTitle, { color: colors.text }]}>{bot.name || bot.symbol}</Text>
          <Text style={[styles.small, { color: colors.textDim }]}>{bot.symbol} · {label(environment)}</Text>
          <Text style={[styles.small, { color: colors.textDim }]}>{label('cash')}: {money(bot.cash_eur)} · {label('positions')}: {money(bot.position_value_eur)}</Text></View>
        <View style={styles.botValue}><Text style={[styles.botTitle, { color: colors.text }]}>{money(bot.equity)}</Text>
          <Text style={[styles.small, { color: colors.textDim }]}>{label('result')}: {money(bot.result_eur)}</Text></View>
      </Pressable>)}
    </View>
    {selected && <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <View style={styles.header}><Text style={[styles.sectionTitle, { color: colors.text }]}>{selected.name || selected.symbol}</Text>
        <Pressable onPress={() => setSelectedId(null)} accessibilityRole="button"><Text style={{ color: colors.accent }}>{label('close')}</Text></Pressable></View>
      <View style={styles.tabs}>{(['positions', 'transactions', 'limits'] as DetailTab[]).map((tab) => <Pressable key={tab} onPress={() => setDetailTab(tab)}
        accessibilityRole="button" accessibilityState={{ selected: detailTab === tab }} style={[styles.tab, { borderColor: colors.border }, detailTab === tab && { backgroundColor: colors.accent }]}>
        <Text style={{ color: detailTab === tab ? '#fff' : colors.text }}>{label(tab)}</Text></Pressable>)}</View>
      {detailTab === 'positions' && <View style={styles.detail}>
        <Text style={{ color: colors.text }}>{label('asset')}: {selected.symbol}</Text>
        <Text style={{ color: colors.text }}>{label('quantity')}: {isKnown(selected.position_qty) ? selected.position_qty.toLocaleString(locale) : '—'}</Text>
        <Text style={{ color: colors.text }}>{label('value')}: {money(selected.position_value_eur)}</Text>
        {selected.position_qty === 0 && <Text style={{ color: colors.textDim }}>{label('noPosition')}</Text>}
        {isKnown(selected.position_qty) && selected.position_qty > 0 && selected.price_quote_currency && selected.price_quote_currency !== 'EUR' &&
          <Text style={{ color: colors.textDim }}>{label('foreignQuote')}: {selected.price_quote_currency}. {label('conversionNeeded')}</Text>}
      </View>}
      {detailTab === 'transactions' && <View style={styles.detail}>{tradesLoading ? <Text style={{ color: colors.textDim }}>{label('loadingTransactions')}</Text>
        : tradesError ? <Text style={{ color: colors.danger }}>{label('transactionsError')}</Text>
        : trades.length ? trades.map((trade) => <Text key={trade.id} style={{ color: colors.text }}>
        {trade.side === 'buy' ? label('buy') : trade.side === 'sell' ? label('sell') : trade.side} · {trade.qty} {trade.symbol} · {money(trade.amount_eur)} · {time(trade.executed_at)}
      </Text>) : <Text style={{ color: colors.textDim }}>{label('noTransactions')}</Text>}</View>}
      {detailTab === 'limits' && <View style={styles.detail}><Text style={{ color: colors.text }}>{label('budget')}: {money(selected.budget_total_eur)}</Text>
        <Text style={{ color: colors.textDim }}>{label('budgetHint')}</Text></View>}
      <Pressable onPress={() => openFinn({ prefill: `Bespreek mijn opgeslagen botportfolio ${selected.name || selected.symbol}. Leg de bekende bedragen en ontbrekende gegevens uit.`,
        source: 'portfolio-bot', symbol: selected.symbol || undefined })} accessibilityRole="button" style={styles.finnButton}>
        <Text style={{ color: colors.accent, fontWeight: '700' }}>{label('discuss')}</Text>
      </Pressable>
    </View>}
  </ScreenContainer>;
}

function Metric({ label, value, colors }: { label: string; value: string; colors: ReturnType<typeof preferenceColors> }) {
  return <View style={styles.metric}><Text style={[styles.small, { color: colors.textDim }]}>{label}</Text>
    <Text style={[styles.metricValue, { color: colors.text }]}>{value}</Text></View>;
}

const styles = StyleSheet.create({
  header: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', gap: 12 },
  title: { fontSize: 28, fontWeight: '700' },
  switch: { borderWidth: 1, borderRadius: 12, flexDirection: 'row', padding: 3 },
  switchButton: { paddingHorizontal: 14, paddingVertical: 9, borderRadius: 9 },
  note: { fontSize: 12, marginTop: 10, marginBottom: 16 },
  card: { borderRadius: 18, borderWidth: 1, padding: 18, marginBottom: 16 },
  metricGrid: { flexDirection: 'row', flexWrap: 'wrap' },
  metric: { width: '50%', paddingBottom: 16 },
  metricValue: { fontSize: 21, fontWeight: '700', marginTop: 4 },
  sectionTitle: { fontSize: 18, fontWeight: '700', marginBottom: 8 },
  small: { fontSize: 12 },
  notice: { fontSize: 13, marginTop: 16, lineHeight: 20 },
  botRow: { flexDirection: 'row', justifyContent: 'space-between', borderTopWidth: 1, paddingVertical: 14, gap: 12 },
  botName: { flex: 1 }, botValue: { alignItems: 'flex-end' }, botTitle: { fontSize: 14, fontWeight: '600' },
  tabs: { flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginTop: 14 },
  tab: { borderWidth: 1, borderRadius: 9, paddingHorizontal: 10, paddingVertical: 8 },
  detail: { gap: 9, marginTop: 16 }, finnButton: { marginTop: 20 },
});
