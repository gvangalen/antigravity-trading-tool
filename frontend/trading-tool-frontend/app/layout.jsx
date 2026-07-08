import "@/styles/globals.css";
import AppProviders from "@/app/providers/AppProviders";
import AuthGuard from "@/components/auth/AuthGuard";
import InstallPWA from "@/components/ui/InstallPWA";
import CacheKiller from "@/components/ui/CacheKiller";
import { BRANDING } from "@/lib/branding";
import { getLocaleBootScript, resolveServerFallbackLocale } from "@/lib/i18n";

const STALE_APP_RECOVERY_VERSION = "2026-07-08-copy-chunk-recovery";

export const metadata = {
  title: `${BRANDING.APP_NAME} — ${BRANDING.APP_SLOGAN} Trading Discipline Engine`,
  description: BRANDING.META_DESCRIPTION,
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "https://www.tradamind.com"),
  manifest: "/manifest.json",
  alternates: {
    canonical: "/",
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: BRANDING.APP_NAME,
  },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#2F6BFF",
};

function StaleAppRecoveryScript() {
  const script = `
(function () {
  var VERSION = ${JSON.stringify(STALE_APP_RECOVERY_VERSION)};
  var VERSION_KEY = "tradamind_app_cache_version";
  var RECOVERY_KEY = "tradamind_app_cache_recovered_" + VERSION;

  function shouldRecover(reason) {
    var text = String(reason || "");
    return /copy|ChunkLoadError|Loading chunk|Cannot find module|page-6ba98bbaffeb4e74|Minified React error/i.test(text);
  }

  async function clearStaleApp(reason) {
    try {
      if (window.sessionStorage && sessionStorage.getItem(RECOVERY_KEY)) return;
      if (window.sessionStorage) sessionStorage.setItem(RECOVERY_KEY, "1");

      if ("serviceWorker" in navigator && navigator.serviceWorker.getRegistrations) {
        var registrations = await navigator.serviceWorker.getRegistrations();
        await Promise.all(registrations.map(function (registration) {
          return registration.unregister();
        }));
      }

      if (window.caches && caches.keys) {
        var cacheNames = await caches.keys();
        await Promise.all(cacheNames.map(function (cacheName) {
          return caches.delete(cacheName);
        }));
      }

      if (window.localStorage) localStorage.setItem(VERSION_KEY, VERSION);
    } catch (error) {
      // Best effort only: recovery must never block the app from loading.
    }

    window.location.reload();
  }

  try {
    var previousVersion = window.localStorage && localStorage.getItem(VERSION_KEY);
    if (previousVersion && previousVersion !== VERSION) {
      clearStaleApp("build-version-change");
    } else if (window.localStorage) {
      localStorage.setItem(VERSION_KEY, VERSION);
    }
  } catch (error) {
    // Ignore storage failures in private browsing or locked-down browsers.
  }

  window.__TRADAMIND_CLEAR_STALE_APP__ = clearStaleApp;

  window.addEventListener("error", function (event) {
    var reason = [
      event && event.message,
      event && event.filename,
      event && event.error && event.error.message,
      event && event.error && event.error.stack
    ].filter(Boolean).join(" ");

    if (shouldRecover(reason)) clearStaleApp(reason);
  }, true);

  window.addEventListener("unhandledrejection", function (event) {
    var value = event && event.reason;
    var reason = value ? (value.stack || value.message || String(value)) : "";
    if (shouldRecover(reason)) clearStaleApp(reason);
  });
})();`;

  return <script dangerouslySetInnerHTML={{ __html: script }} />;
}

export default function RootLayout({ children }) {
  const fallbackLocale = resolveServerFallbackLocale();

  return (
    <html lang={fallbackLocale} suppressHydrationWarning>
      <head>
        <link rel="apple-touch-icon" href="/icon-192x192.png" />
        <StaleAppRecoveryScript />
        <script dangerouslySetInnerHTML={{ __html: getLocaleBootScript() }} />
      </head>
      <body className="bg-background text-foreground transition-colors duration-300 selection:bg-blue-600/30">
        <CacheKiller />
        <AppProviders>
          <AuthGuard>
            {children}
          </AuthGuard>
          <InstallPWA />
        </AppProviders>
      </body>
    </html>
  );
}
