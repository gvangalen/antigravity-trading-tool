import React, { useEffect, useRef } from 'react';
import { Animated, Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { MobileIntelligenceEvent } from '../../services/tradamindApi';
import { triggerHaptic } from '../../utils/haptics';
import { CardShell } from '../cards/CardShell';

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

  if (!events || events.length === 0) {
    return null;
  }

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
        <Animated.View style={[styles.radarDot, { opacity: pulseAnim }]} />
        <Text style={styles.feedTitle}>LIVE INTELLIGENCE COCKPIT</Text>
      </View>

      <View style={styles.eventList}>
        {sortedEvents.map((item) => {
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
            <CardShell key={item.id} emphasis="primary">
              <View style={styles.cardHeader}>
                <View style={[styles.badge, { backgroundColor: severityBg }]}>
                  <Text style={[styles.badgeText, { color: severityColor }]}>
                    {severityLabel} {item.symbol ? `· ${item.symbol}` : ''}
                  </Text>
                </View>

                {/* Dismiss / Archive Button */}
                <Pressable
                  onPress={async () => {
                    await triggerHaptic('selection');
                    onArchive(item.id);
                  }}
                  style={({ pressed }) => [styles.archiveBtn, pressed && styles.pressed]}
                >
                  <Text style={styles.archiveText}>×</Text>
                </Pressable>
              </View>

              <Text style={styles.title} numberOfLines={1}>
                {item.title}
              </Text>
              
              <Text style={styles.description} numberOfLines={1}>
                {item.description}
              </Text>

              {/* Action Chip Container */}
              <View style={styles.actionContainer}>
                <Pressable
                  onPress={async () => {
                    await triggerHaptic('selection');
                    onDiscuss(item);
                  }}
                  style={({ pressed }) => [
                    styles.discussButton,
                    { borderColor: `${severityColor}80` },
                    pressed && styles.pressed,
                  ]}
                >
                  <Text style={[styles.discussText, { color: severityColor }]}>
                    Bespreek met FINN
                  </Text>
                </Pressable>
              </View>
            </CardShell>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
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
    gap: theme.spacing.xs,
    paddingLeft: theme.spacing.xxs,
  },
  feedTitle: {
    color: theme.colors.textDim,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 2,
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
