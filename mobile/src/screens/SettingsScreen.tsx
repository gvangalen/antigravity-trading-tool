import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { theme } from '../constants/theme';

export function SettingsScreen() {
  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.content}>
        <Text style={styles.title}>Settings</Text>
        <View style={styles.card}>
          <Text style={styles.label}>App</Text>
          <Text style={styles.value}>Tradamind Mobile</Text>

          <Text style={styles.label}>Version</Text>
          <Text style={styles.value}>1.0.0</Text>

          <Text style={styles.label}>Backend status</Text>
          <Text style={styles.value}>Placeholder</Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    padding: theme.spacing.lg,
  },
  content: {
    gap: theme.spacing.lg,
    padding: theme.spacing.lg,
  },
  label: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: '900',
    marginTop: theme.spacing.md,
    textTransform: 'uppercase',
  },
  safeArea: {
    backgroundColor: theme.colors.background,
    flex: 1,
  },
  title: {
    color: theme.colors.text,
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: 0,
  },
  value: {
    color: theme.colors.text,
    fontSize: 17,
    fontWeight: '800',
    marginTop: 4,
  },
});
