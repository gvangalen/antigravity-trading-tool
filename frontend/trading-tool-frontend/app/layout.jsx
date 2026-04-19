import "@/styles/globals.css";
import AppProviders from "@/app/providers/AppProviders";
import AuthGuard from "@/components/auth/AuthGuard";
import { BRANDING } from "@/lib/branding";

export const metadata = {
  title: `${BRANDING.APP_NAME} — ${BRANDING.APP_SLOGAN} Trading Discipline Engine`,
  description: BRANDING.META_DESCRIPTION,
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "https://www.tradamind.com"),
  manifest: "/manifest.json",
  themeColor: "#2F6BFF",
  alternates: {
    canonical: "/",
  },
  viewport: {
    width: "device-width",
    initialScale: 1,
    maximumScale: 1,
    userScalable: false,
    viewportFit: "cover",
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: BRANDING.APP_NAME,
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="nl">
      <head>
        <link rel="apple-touch-icon" href="/icon-192x192.png" />
      </head>
      <body>
        <AppProviders>
          <AuthGuard>
            {children}
          </AuthGuard>
        </AppProviders>
      </body>
    </html>
  );
}
