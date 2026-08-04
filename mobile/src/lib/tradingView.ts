export type MobileChartTimeframe = '15m' | '1h' | '4h' | '1d';

import type { TradingViewTheme } from './tradingViewConfig';

export {
  ANALYSIS_CHART_INTERVAL_KEY,
  buildTradingViewEmbedConfig,
  buildTradingViewWidgetUrl,
  DEFAULT_TRADINGVIEW_INTERVAL,
  normalizeTradingViewInterval,
  parseTradingViewIntervalFromUrl,
  toTradingViewInterval,
  toTradingViewSymbol,
  toTradingViewTheme,
} from './tradingViewConfig';
export type { TradingViewInterval } from './tradingViewConfig';

export function buildTradingViewWidgetHtml(options: {
  interval: string;
  symbol: string;
  theme: TradingViewTheme;
}) {
  const config = {
    autosize: true,
    symbol: options.symbol,
    interval: options.interval,
    timezone: 'Etc/UTC',
    theme: options.theme,
    style: '1',
    locale: 'en',
    hide_top_toolbar: false,
    hide_side_toolbar: true,
    allow_symbol_change: false,
    save_image: false,
    calendar: false,
    studies: [],
    support_host: 'https://www.tradingview.com',
  };

  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta
      name="viewport"
      content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no"
    />
    <style>
      html, body {
        margin: 0;
        padding: 0;
        width: 100%;
        height: 100%;
        overflow: hidden;
        background: transparent;
      }

      #chart-root, .tradingview-widget-container, .tradingview-widget-container__widget {
        width: 100%;
        height: 100%;
      }
    </style>
  </head>
  <body>
    <div id="chart-root" class="tradingview-widget-container">
      <div class="tradingview-widget-container__widget"></div>
    </div>
    <script>
      (function () {
        var widgetConfig = ${JSON.stringify(config)};
        var widgetMounted = false;

        function report(type, payload) {
          try {
            if (window.ReactNativeWebView && window.ReactNativeWebView.postMessage) {
              window.ReactNativeWebView.postMessage(JSON.stringify({ type: type, payload: payload }));
            }
          } catch (error) {
            // Ignore postMessage failures inside the embedded document.
          }
        }

        function mountWidget() {
          if (widgetMounted) return;
          widgetMounted = true;

          var script = document.createElement('script');
          script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
          script.async = true;
          script.text = JSON.stringify(widgetConfig);
          script.onload = function () {
            report('tv:loaded', { symbol: widgetConfig.symbol, interval: widgetConfig.interval });
          };
          script.onerror = function (event) {
            report('tv:error', { stage: 'script', message: 'TradingView script failed to load.' });
          };
          document.body.appendChild(script);
        }

        window.addEventListener('error', function (event) {
          report('tv:error', {
            stage: 'window',
            message: event && event.message ? event.message : 'Unknown TradingView error',
          });
        });

        document.addEventListener('DOMContentLoaded', mountWidget);
        window.addEventListener('load', mountWidget);
        setTimeout(mountWidget, 0);
      })();
    </script>
  </body>
</html>`;
}
