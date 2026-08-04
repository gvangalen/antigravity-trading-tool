import { useEffect, useState } from 'react';
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
import { theme } from '../constants/theme';
import { translate } from '../i18n';
import { useAppPreferences } from '../preferences/AppPreferencesProvider';
import { authApi } from '../services/authApi';
import { API_BASE_URL } from '../services/apiClient';
import { triggerHaptic } from '../utils/haptics';

type HealthState = 'checking' | 'online' | 'offline';
const IS_LOCAL_DEV_API = /127\.0\.0\.1|localhost|192\.168\./.test(API_BASE_URL);
const DEV_PREFILL_EMAIL =
  process.env.EXPO_PUBLIC_SIMULATOR_AUTO_LOGIN_EMAIL?.trim() ||
  (IS_LOCAL_DEV_API ? 'gerrit@example.com' : '');
const DEV_PREFILL_PASSWORD =
  process.env.EXPO_PUBLIC_SIMULATOR_AUTO_LOGIN_PASSWORD?.trim() ||
  (IS_LOCAL_DEV_API ? 'test123' : '');

export function LoginScreen() {
  const { error, loading, login } = useAuth();
  const { language } = useAppPreferences();
  const [healthState, setHealthState] = useState<HealthState>('checking');
  const [email, setEmail] = useState(DEV_PREFILL_EMAIL);
  const [password, setPassword] = useState(DEV_PREFILL_PASSWORD);
  const [passwordVisible, setPasswordVisible] = useState(false);

  const canSubmit = email.trim().length > 3 && password.length > 0 && !loading;

  useEffect(() => {
    let mounted = true;
    const fallback = setTimeout(() => {
      if (mounted) setHealthState('offline');
    }, 4500);

    authApi
      .health()
      .then(() => {
        if (mounted) setHealthState('online');
      })
      .catch(() => {
        if (mounted) setHealthState('offline');
      });

    return () => {
      mounted = false;
      clearTimeout(fallback);
    };
  }, []);

  async function handleLogin() {
    if (!canSubmit) return;
    await triggerHaptic('selection');
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
            <View style={styles.topRow}>
              <StatusChip compact label={translate(language, 'login.mobile')} tone="accent" />
              <StatusChip
                compact
                label={
                  healthState === 'checking'
                    ? translate(language, 'login.syncing')
                    : healthState === 'online'
                      ? translate(language, 'login.apiLive')
                      : translate(language, 'login.apiOffline')
                }
                tone={healthState === 'online' ? 'success' : healthState === 'offline' ? 'danger' : 'warning'}
              />
            </View>
            <Text style={styles.title}>{translate(language, 'login.title')}</Text>
            <Text style={styles.subtitle}>
              {translate(language, 'login.subtitle')}
            </Text>
          </View>

          <CardShell emphasis="primary">
            <Text style={styles.formLabel}>{translate(language, 'login.email')}</Text>
            <TextInput
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              onChangeText={setEmail}
              onSubmitEditing={() => password.length > 0 && handleLogin()}
              placeholder="you@tradamind.com"
              placeholderTextColor={theme.colors.textDim}
              returnKeyType="next"
              style={styles.input}
              textContentType="username"
              value={email}
            />

            <Text style={styles.formLabel}>{translate(language, 'login.password')}</Text>
            <View style={styles.passwordRow}>
              <TextInput
                autoCapitalize="none"
                onChangeText={setPassword}
                onSubmitEditing={handleLogin}
                placeholder={translate(language, 'login.passwordPlaceholder')}
                placeholderTextColor={theme.colors.textDim}
                returnKeyType="done"
                secureTextEntry={!passwordVisible}
                style={styles.passwordInput}
                textContentType="password"
                value={password}
              />
              <Pressable
                accessibilityLabel={
                  passwordVisible
                    ? translate(language, 'login.hidePassword')
                    : translate(language, 'login.showPassword')
                }
                onPress={async () => {
                  await triggerHaptic('selection');
                  setPasswordVisible((visible) => !visible);
                }}
                style={({ pressed }) => [styles.passwordToggle, pressed && styles.pressed]}
              >
                <Text style={styles.toggleText}>
                  {passwordVisible
                    ? translate(language, 'login.hidePassword')
                    : translate(language, 'login.showPassword')}
                </Text>
              </Pressable>
            </View>

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
                <Text style={styles.buttonText}>
                  {healthState === 'offline'
                    ? translate(language, 'login.retryLogin')
                    : translate(language, 'login.logIn')}
                </Text>
              )}
            </Pressable>

            <View style={styles.securityRow}>
              <Text style={styles.securityText}>{translate(language, 'login.bearerAuth')}</Text>
              <Text style={styles.securityDivider}>·</Text>
              <Text style={styles.securityText}>{translate(language, 'login.secureTokenStorage')}</Text>
              <Text style={styles.securityDivider}>·</Text>
              <Text style={styles.securityText}>{translate(language, 'login.autoRefresh')}</Text>
            </View>
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
  passwordInput: {
    color: theme.colors.text,
    flex: 1,
    fontSize: theme.typography.body,
    fontWeight: '700',
    minHeight: 50,
    paddingHorizontal: theme.spacing.md,
  },
  passwordRow: {
    alignItems: 'center',
    backgroundColor: theme.colors.backgroundSoft,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    flexDirection: 'row',
  },
  passwordToggle: {
    alignItems: 'center',
    borderLeftColor: theme.colors.border,
    borderLeftWidth: 1,
    justifyContent: 'center',
    minHeight: 50,
    paddingHorizontal: theme.spacing.md,
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
  securityDivider: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '900',
  },
  securityRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.xs,
    marginTop: theme.spacing.md,
  },
  securityText: {
    color: theme.colors.textDim,
    fontSize: theme.typography.small,
    fontWeight: '800',
  },
  toggleText: {
    color: theme.colors.accent,
    fontSize: theme.typography.small,
    fontWeight: '900',
  },
  title: {
    color: theme.colors.text,
    fontSize: 28,
    fontWeight: '900',
    lineHeight: 33,
    marginTop: theme.spacing.md,
  },
  topRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
});
