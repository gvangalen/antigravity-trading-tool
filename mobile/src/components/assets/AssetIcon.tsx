import { useMemo, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';

function fallbackColor(symbol: string) {
  const upper = symbol.toUpperCase();
  if (upper === 'BTC') return '#F7931A';
  if (upper === 'ETH') return '#627EEA';
  if (upper === 'SOL') return '#111827';
  if (upper === 'XRP') return '#0F172A';
  return theme.colors.accent;
}

function logoUrl(symbol: string) {
  return `https://assets.coincap.io/assets/icons/${symbol.toLowerCase()}@2x.png`;
}

export function AssetIcon({
  compact = false,
  logoUrl: providedLogoUrl,
  size,
  symbol,
}: {
  compact?: boolean;
  logoUrl?: string | null;
  size?: number;
  symbol: string;
}) {
  const [failed, setFailed] = useState(false);
  const upper = symbol.toUpperCase();
  const resolvedSize = size ?? (compact ? 34 : 48);
  const borderRadius = compact ? theme.radius.pill : theme.radius.lg;
  const uri = useMemo(() => providedLogoUrl || logoUrl(upper), [providedLogoUrl, upper]);

  if (failed || !upper) {
    return (
      <View
        style={[
          styles.fallback,
          {
            backgroundColor: fallbackColor(upper),
            borderRadius,
            height: resolvedSize,
            width: resolvedSize,
          },
        ]}
      >
        <Text style={[styles.fallbackText, { fontSize: compact ? 16 : 22 }]}>{upper.slice(0, 1) || '?'}</Text>
      </View>
    );
  }

  return (
    <View
      style={[
        styles.imageWrap,
        {
          borderRadius,
          height: resolvedSize,
          width: resolvedSize,
        },
      ]}
    >
      <Image
        onError={() => setFailed(true)}
        source={{ uri }}
        style={{ height: resolvedSize, width: resolvedSize }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  fallback: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  fallbackText: {
    color: theme.colors.white,
    fontWeight: '900',
  },
  imageWrap: {
    overflow: 'hidden',
  },
});
