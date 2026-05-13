import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '../auth/AuthProvider';
import { CardShell } from '../components/cards/CardShell';
import { StatusChip } from '../components/layout/StatusChip';
import { API_BASE_URL } from '../services/apiClient';
import { theme } from '../constants/theme';

export function LoginScreen() {
  const { error, loading, login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const canSubmit = email.trim().length > 3 && password.length > 0 && !loading;

  async function handleLogin() {
    if (!canSubmit) return;
    await login(email, password);
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.keyboard}
      >
        <View style={styles.container}>
          <View>
            <StatusChip label="Tradamind Mobile" tone="accent" />
            <Text style={styles.title}>Welkom terug bij FINN.</Text>
            <Text style={styles.subtitle}>
              Log in om je assistant, watchlist, setups, portfolio en reports met echte backenddata te laden.
            </Text>
          </View>

          <CardShell emphasis="primary">
            <Text style={styles.formLabel}>Email</Text>
            <TextInput
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              onChangeText={setEmail}
              placeholder="you@tradamind.com"
              placeholderTextColor={theme.colors.textDim}
              style={styles.input}
              textContentType="username"
              value={email}
            />

            <Text style={styles.formLabel}>Password</Text>
            <TextInput
              autoCapitalize="none"
              onChangeText={setPassword}
              placeholder="Password"
              placeholderTextColor={theme.colors.textDim}
              secureTextEntry
              style={styles.input}
              textContentType="password"
              value={password}
            />

            {error ? <Text style={styles.error}>{error}</Text> : null}

            <Pressable
              disabled={!canSubmit}
              onPress={handleLogin}
              style={({ pressed }) => [
                styles.button,
                (!canSubmit || loading) && styles.disabled,
                pressed && styles.pressed,
              ]}
            >
              {loading ? (
                <ActivityIndicator color={theme.colors.white} />
              ) : (
                <Text style={styles.buttonText}>Log in</Text>
              )}
            </Pressable>
          </CardShell>

          <Text style={styles.meta}>API: {API_BASE_URL}</Text>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  button: {
    alignItems: 'center',
    backgroundColor: theme.colors.accent,
    borderRadius: theme.radius.button,
    justifyContent: 'center',
    marginTop: theme.spacing.lg,
    minHeight: 50,
  },
  buttonText: {
    color: theme.colors.white,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  container: {
    flex: 1,
    gap: theme.spacing.xl,
    justifyContent: 'center',
    padding: theme.spacing.lg,
  },
  disabled: {
    opacity: 0.45,
  },
  error: {
    color: theme.colors.danger,
    fontSize: theme.typography.small,
    fontWeight: '800',
    lineHeight: 19,
    marginTop: theme.spacing.md,
  },
  formLabel: {
    color: theme.colors.textDim,
    fontSize: theme.typography.label,
    fontWeight: '900',
    letterSpacing: 1.5,
    marginBottom: theme.spacing.xs,
    marginTop: theme.spacing.md,
    textTransform: 'uppercase',
  },
  input: {
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    color: theme.colors.text,
    fontSize: theme.typography.body,
    fontWeight: '700',
    minHeight: 50,
    paddingHorizontal: theme.spacing.md,
  },
  keyboard: {
    flex: 1,
  },
  meta: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '700',
    textAlign: 'center',
  },
  pressed: {
    opacity: 0.86,
    transform: [{ scale: 0.99 }],
  },
  safeArea: {
    backgroundColor: theme.colors.background,
    flex: 1,
  },
  subtitle: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.body,
    fontWeight: '600',
    lineHeight: 23,
    marginTop: theme.spacing.md,
  },
  title: {
    color: theme.colors.text,
    fontSize: 34,
    fontWeight: '900',
    lineHeight: 39,
    marginTop: theme.spacing.md,
  },
});
