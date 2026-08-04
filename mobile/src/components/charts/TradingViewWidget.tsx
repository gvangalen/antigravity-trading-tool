import { useMemo, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { WebView } from 'react-native-webview';

import {
  buildTradingViewWidgetUrl,
  parseTradingViewIntervalFromUrl,
  type TradingViewInterval,
  toTradingViewSymbol,
  toTradingViewTheme,
} from '../../lib/tradingView';
import { preferenceColors, useAppPreferences } from '../../preferences/AppPreferencesProvider';

type TradingViewWidgetProps = {
  interval: TradingViewInterval;
  onIntervalChange?: (interval: TradingViewInterval) => void;
  symbol: string;
};

export function TradingViewWidget({ interval, onIntervalChange, symbol }: TradingViewWidgetProps) {
  const { appearance } = useAppPreferences();
  const colors = preferenceColors(appearance);
  const [webviewError, setWebviewError] = useState<string | null>(null);

  const source = useMemo(
    () => ({
      uri: buildTradingViewWidgetUrl({
        interval,
        symbol: toTradingViewSymbol(symbol),
        theme: toTradingViewTheme(appearance),
      }),
    }),
    [appearance, interval, symbol],
  );

  return (
    <View style={[styles.frame, { backgroundColor: colors.backgroundSoft, borderColor: colors.border }]}>
      <WebView
        source={source}
        originWhitelist={['*']}
        javaScriptEnabled
        domStorageEnabled
        sharedCookiesEnabled
        thirdPartyCookiesEnabled
        injectedJavaScript={`
          (function () {
            var lastHref = '';
            function emitHref() {
              try {
                var href = window.location.href || '';
                if (href && href !== lastHref) {
                  lastHref = href;
                  window.ReactNativeWebView.postMessage(JSON.stringify({
                    type: 'tv:href',
                    payload: { href: href }
                  }));
                }
              } catch (error) {
                // Ignore bridge errors.
              }
            }
            emitHref();
            setInterval(emitHref, 1000);
          })();
          true;
        `}
        onError={(event) => {
          setWebviewError(event.nativeEvent.description || 'WebView failed to load the TradingView chart.');
        }}
        onHttpError={(event) => {
          setWebviewError(`TradingView HTTP error ${event.nativeEvent.statusCode}`);
        }}
        onLoadStart={() => setWebviewError(null)}
        onMessage={(event) => {
          try {
            const message = JSON.parse(event.nativeEvent.data);
            if (message?.type === 'tv:href') {
              const nextInterval = parseTradingViewIntervalFromUrl(message?.payload?.href || '');
              if (nextInterval) {
                onIntervalChange?.(nextInterval);
              }
            }
          } catch {
            // Ignore malformed bridge messages.
          }
        }}
        scrollEnabled={false}
        bounces={false}
        showsHorizontalScrollIndicator={false}
        showsVerticalScrollIndicator={false}
        style={styles.webview}
      />
      {webviewError ? (
        <View style={[styles.debugOverlay, { backgroundColor: `${colors.backgroundSoft}F2` }]}>
          <Text style={[styles.debugTitle, { color: colors.text }]}>TradingView chart unavailable</Text>
          <Text style={[styles.debugBody, { color: colors.textDim }]}>{webviewError}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    borderRadius: 20,
    borderWidth: 1,
    height: 420,
    overflow: 'hidden',
  },
  debugOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
    gap: 8,
  },
  debugBody: {
    fontSize: 13,
    lineHeight: 18,
    textAlign: 'center',
  },
  debugTitle: {
    fontSize: 15,
    fontWeight: '700',
    textAlign: 'center',
  },
  webview: {
    backgroundColor: 'transparent',
    flex: 1,
  },
});
