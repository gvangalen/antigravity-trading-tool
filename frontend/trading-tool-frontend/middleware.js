import { NextResponse } from "next/server";

export async function middleware(req) {
  const url = req.nextUrl.clone();
  const path = url.pathname;

  const isDev = process.env.NODE_ENV === "development";

  if (isDev) console.log("⛔ MIDDLEWARE HIT:", path);

  // =====================================================
  // Skip system & static files
  // =====================================================
  if (
    path.startsWith("/api") ||
    path.startsWith("/_next") ||
    path.startsWith("/favicon") ||
    /\.(png|jpg|jpeg|svg|webp|ico|css|js|map)$/.test(path)
  ) {
    return NextResponse.next();
  }

  // =====================================================
  // ✅ PUBLIC TOKEN ROUTES (PDF / PRINT / SHARE)
  // =====================================================
  // Required for Playwright & public report viewing
  if (
    path.startsWith("/print") ||        // ✅ PDF render
    path.startsWith("/daily-report") ||
    path.startsWith("/public/report")
  ) {
    if (isDev) console.log("🟢 Token route toegestaan:", path);
    return NextResponse.next();
  }

  // =====================================================
  // Public auth pages
  // =====================================================
  const publicRoutes = ["/login", "/register"];

  if (publicRoutes.includes(path)) {
    if (isDev) console.log("➡️ Public route toegestaan:", path);
    return NextResponse.next();
  }

  // =====================================================
  // Token check
  // =====================================================
  const token = req.cookies.get("access_token")?.value;

  if (isDev) console.log("🍪 Token aanwezig?", token ? "JA" : "NEE");

  // 🔥 ROOT FIX → voorkomt hydration errors
  if (path === "/") {
    url.pathname = token ? "/dashboard" : "/login";
    return NextResponse.redirect(url);
  }

  if (!token) {
    if (isDev) console.log("❌ GEEN token → redirect naar login");
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  // =====================================================
  // Onboarding status check
  // =====================================================
  let onboarding = null;
  const apiUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  try {
    if (isDev) console.log("🔍 Fetch onboarding status…");

    const res = await fetch(`${apiUrl}/api/onboarding/status`, {
      method: "GET",
      headers: {
        cookie: req.headers.get("cookie") || "",
      },
      cache: "no-store",
    });

    if (isDev) console.log("📡 Backend response:", res.status);

    if (res.status === 401) {
      if (isDev) console.log("❌ Backend zegt 401 → redirect login");
      url.pathname = "/login";
      return NextResponse.redirect(url);
    }

    onboarding = await res.json();

    if (isDev) console.log("📦 Onboarding JSON:", onboarding);

  } catch (err) {
    console.log("💥 Onboarding fetch error:", err);
    return NextResponse.next();
  }

  const onboardingComplete =
    onboarding?.has_setup &&
    onboarding?.has_technical &&
    onboarding?.has_macro &&
    onboarding?.has_market &&
    onboarding?.has_strategy;

  if (isDev) console.log("🎯 Onboarding compleet?", onboardingComplete);

  const allowedDuringOnboarding = [
    "/onboarding",
    "/setup",
    "/technical",
    "/macro",
    "/market",
    "/strategy"
  ];

  // =====================================================
  // Onboarding NOT complete
  // =====================================================
  if (!onboardingComplete) {
    if (allowedDuringOnboarding.some((route) => path.startsWith(route))) {
      if (isDev) console.log("🟢 Toegestane onboarding route:", path);
      return NextResponse.next();
    }

    if (isDev) console.log("🔴 Onboarding NIET klaar → redirect");
    url.pathname = "/onboarding";
    return NextResponse.redirect(url);
  }

  // =====================================================
  // Block onboarding if already completed
  // =====================================================
  if (onboardingComplete && path.startsWith("/onboarding")) {
    if (isDev) console.log("🚫 Onboarding klaar → dashboard");
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }

  if (isDev) console.log("🟢 Normaal doorgelaten:", path);
  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Run middleware on everything except:
     * - Next internals
     * - static files
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
