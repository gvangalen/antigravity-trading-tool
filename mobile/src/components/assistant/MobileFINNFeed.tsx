import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { translate } from '../../i18n';
import type { AppLanguage } from '../../preferences/AppPreferencesProvider';
import type { MobileCoachFeedItem } from '../../services/tradamindApi';
import { triggerHaptic } from '../../utils/haptics';

type Props = {
  events: MobileCoachFeedItem[];
  onArchive: (eventId: string) => void;
  onDiscuss: (event: MobileCoachFeedItem) => void;
  onToggleHistory: () => void;
  history: boolean;
  language: AppLanguage;
};

export function MobileFINNFeed({ events, onArchive, onDiscuss, onToggleHistory, history, language }: Props) {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.heading}>{translate(language, 'finn.feedTitle')}</Text>
        <Pressable onPress={onToggleHistory} accessibilityRole="button">
          <Text style={styles.link}>{translate(language, history ? 'finn.feedCurrent' : 'finn.feedAll')}</Text>
        </Pressable>
      </View>
      {events.length === 0 ? (
        <Text style={styles.empty}>{translate(language, 'finn.feedEmpty')}</Text>
      ) : events.map((item) => (
        <View key={item.id} style={styles.item}>
          <View style={styles.row}>
            <Text style={styles.title}>{item.title}</Text>
            {item.symbol ? <Text style={styles.symbol}>{item.symbol}</Text> : null}
          </View>
          <Text style={styles.description}>{item.description}</Text>
          <Text style={styles.time}>{new Date(item.created_at).toLocaleString(language)}</Text>
          {item.status === 'unread' || item.status === 'read' ? (
            <View style={styles.actions}>
              <Pressable onPress={async () => { await triggerHaptic('selection'); onDiscuss(item); }} accessibilityRole="button">
                <Text style={styles.link}>{translate(language, 'finn.feedDiscuss')}</Text>
              </Pressable>
              <Pressable onPress={async () => { await triggerHaptic('selection'); onArchive(item.id); }} accessibilityRole="button">
                <Text style={styles.secondary}>{translate(language, 'finn.feedHandled')}</Text>
              </Pressable>
            </View>
          ) : null}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: theme.colors.surface, borderRadius: theme.radius.lg, padding: theme.spacing.md, gap: 10 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  heading: { color: theme.colors.text, fontSize: 17, fontWeight: '800' },
  item: { borderTopWidth: 1, borderTopColor: theme.colors.border, paddingTop: 12, gap: 5 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { color: theme.colors.text, fontWeight: '700', flexShrink: 1 },
  symbol: { color: theme.colors.accent, fontSize: 12, fontWeight: '700' },
  description: { color: theme.colors.text, fontSize: 13, lineHeight: 19 },
  time: { color: theme.colors.text, opacity: 0.55, fontSize: 11 },
  actions: { flexDirection: 'row', gap: 18, paddingTop: 6 },
  link: { color: theme.colors.accent, fontWeight: '700', fontSize: 13 },
  secondary: { color: theme.colors.text, opacity: 0.65, fontSize: 13 },
  empty: { color: theme.colors.text, opacity: 0.65, paddingVertical: 12 },
});
