import React, { useEffect, useRef } from 'react';
import { Animated, Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { MobileIntelligenceEvent } from '../../services/tradamindApi';
import { triggerHaptic } from '../../utils/haptics';

type MobileFINNFeedProps = {
  events: MobileIntelligenceEvent[];
  onArchive: (eventId: number) => void;
  onDiscuss: (event: MobileIntelligenceEvent) => void;
};

export function MobileFINNFeed({ events, onArchive, onDiscuss }: MobileFINNFeedProps) {
  const pulseAnim = useRef(new Animated.Value(0.4)).current;

  // Gentle breathing pulse animation for the active radar indicator
  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, {
          toValue: 1.0,
          duration: 1200,
          useNativeDriver: true,
        }),
        Animated.timing(pulseAnim, {
          toValue: 0.4,
          duration: 1200,
          useNativeDriver: true,
        }),
      ])
    ).start();
  }, [pulseAnim]);

  // Prioritize Critical, then Warning, then Info events
  const severityOrder: Record<string, number> = { critical: 1, warning: 2, info: 3 };
  const sortedEvents = [...events].sort((a, b) => {
    const orderA = severityOrder[a.severity] || 99;
    const orderB = severityOrder[b.severity] || 99;
    return orderA - orderB;
  });

  return (
    <View style={styles.container}>
      <View style={styles.feedHeader}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Text style={{ color: theme.colors.accent, fontWeight: '900' }}>{'>_'}</Text>
          <Text style={styles.feedTitle}>FINN LIVE INTELLIGENCE TERMINAL</Text>
        </View>
        <Text style={styles.feedSubtitle}>MISSION CONTROL</Text>
      </View>

      <View style={styles.eventList}>
        {!events || events.length === 0 ? (
          <View style={styles.emptyStateBox}>
            <Text style={styles.emptyStateText}>Geen actieve risico-meldingen. Cockpit draait stabiel.</Text>
          </View>
        ) : (
          sortedEvents.map((item, index) => {
            // Resolve severity colors
            let severityColor = theme.colors.success;
            let severityBg = theme.colors.successSoft;
            let severityLabel = 'INFO';

            if (item.severity === 'critical') {
              severityColor = theme.colors.danger;
              severityBg = theme.colors.dangerSoft;
              severityLabel = 'CRITICAL';
            } else if (item.severity === 'warning') {
              severityColor = theme.colors.warning;
              severityBg = theme.colors.warningSoft;
              severityLabel = 'WARNING';
            } else if (item.severity === 'info') {
              severityColor = theme.colors.accent;
              severityBg = theme.colors.accentSoft;
            }

            return (
              <View key={`${item.id}-${index}`} style={styles.terminalCard}>
                <View style={styles.terminalCardHeader}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
                    <Text style={styles.terminalCardTitle} numberOfLines={1}>{item.title}</Text>
                    {item.symbol && (
                      <View style={styles.terminalSymbolBadge}>
                        <Text style={styles.terminalSymbolText}>{item.symbol}</Text>
                      </View>
                    )}
                  </View>
                  <Pressable
                    onPress={async () => {
                      await triggerHaptic('selection');
                      onArchive(item.id);
                    }}
                    style={({ pressed }) => [styles.archiveBtn, pressed && styles.pressed]}
                  >
                    <Text style={styles.archiveText}>✕</Text>
                  </Pressable>
                </View>

                <Text style={styles.description} numberOfLines={2}>
                  {item.description}
                </Text>

                {/* Discuss Button */}
                <Pressable
                  onPress={async () => {
                    await triggerHaptic('selection');
                    onDiscuss(item);
                  }}
                  style={({ pressed }) => [
                    styles.discussButton,
                    pressed && styles.pressed,
                  ]}
                >
                  <Text style={styles.discussText}>💬 Bespreek met FINN</Text>
                </Pressable>
              </View>
            );
          })
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  terminalCard: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderWidth: 1,
    borderRadius: theme.radius.lg,
    padding: theme.spacing.md,
  },
  terminalCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.xs,
  },
  terminalCardTitle: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: '900',
  },
  terminalSymbolBadge: {
    backgroundColor: '#EFF6FF',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  terminalSymbolText: {
    color: '#3B82F6',
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.5,
  },
  actionContainer: {
    flexDirection: 'row',
    marginTop: theme.spacing.sm,
  },
  archiveBtn: {
    alignItems: 'center',
    height: 24,
    justifyContent: 'center',
    width: 24,
  },
  archiveText: {
    color: theme.colors.textDim,
    fontSize: 20,
    fontWeight: '300',
    lineHeight: 20,
  },
  badge: {
    borderRadius: theme.radius.xs,
    paddingHorizontal: theme.spacing.xs,
    paddingVertical: 3,
  },
  badgeText: {
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1,
  },
  cardHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.xs,
  },
  container: {
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.md,
    marginTop: theme.spacing.xs,
    paddingHorizontal: theme.spacing.xs,
  },
  description: {
    color: theme.colors.textSoft,
    fontSize: theme.typography.small,
    fontWeight: '500',
    lineHeight: 18,
    marginTop: 3,
  },
  discussButton: {
    backgroundColor: 'transparent',
    borderRadius: theme.radius.xs,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xxs,
  },
  discussText: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  eventList: {
    gap: theme.spacing.xs,
  },
  feedHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: theme.spacing.xs,
    marginBottom: 4,
  },
  feedTitle: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 2,
  },
  feedSubtitle: {
    color: theme.colors.textDim,
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  emptyStateBox: {
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.border,
    borderWidth: 1,
    borderRadius: theme.radius.lg,
    padding: theme.spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyStateText: {
    color: theme.colors.textDim,
    fontSize: 11,
    fontWeight: '700',
    fontStyle: 'italic',
    textTransform: 'uppercase',
    letterSpacing: 1,
    textAlign: 'center',
  },
  pressed: {
    opacity: 0.75,
  },
  radarDot: {
    backgroundColor: theme.colors.danger,
    borderRadius: theme.radius.pill,
    height: 8,
    width: 8,
  },
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.body,
    fontWeight: '900',
    lineHeight: 20,
  },
});
