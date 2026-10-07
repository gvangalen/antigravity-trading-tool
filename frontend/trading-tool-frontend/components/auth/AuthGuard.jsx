"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { getCachedOnboardingStatus, getOnboardingStatus } from "@/lib/api/onboarding";

/**
 * 🛡️ AuthGuard
 * Client-side protection for routes.
 * Replaces Next.js Middleware for static exports (Native App).
 */
export default function AuthGuard({ children }) {
  const { user, loading, sessionChecked } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [checkingOnboarding, setCheckingOnboarding] = useState(true);
  const [redirectingToOnboarding, setRedirectingToOnboarding] = useState(false);
  const onboardingCheckVersion = useRef(0);
  const verifiedComplete = useRef(false);
  const verifiedUserId = useRef(null);

  // Routes that don't need auth
  const publicRoutes = ["/", "/login", "/register", "/forgot-password", "/reset-password", "/print", "/daily-report"];
  const isPublicRoute = publicRoutes.some(route => pathname === route || pathname.startsWith("/public/"));
  const debug = (...args) => {
    if (process.env.NODE_ENV === "development") console.log(...args);
  };

  const checkOnboardingStatus = useCallback(async () => {
    const checkVersion = ++onboardingCheckVersion.current;
    if (!user || isPublicRoute) {
      setCheckingOnboarding(false);
      return;
    }

    // A route transition must not hide an already verified workspace behind
    // another network status read. The fresh, user-scoped cache is only an
    // optimistic render; the server response below still enforces redirects.
    const cached = getCachedOnboardingStatus(30_000);
    const cachedComplete = cached?.onboarding_complete === true || cached?.phases_completed?.complete === true;
    const cachedNextPath = cached?.next_route
      ? new URL(cached.next_route, window.location.origin).pathname
      : null;
    const cachedAllowsCurrentStep = Boolean(cachedNextPath && cachedNextPath === pathname);
    const cachedAllowsSavedBot = pathname.startsWith("/bot") && Boolean(cached?.has_strategy);
    const canRenderWhileChecking = (
      (verifiedComplete.current && verifiedUserId.current === user.id)
      || cachedComplete || cachedAllowsCurrentStep || cachedAllowsSavedBot
    );
    setCheckingOnboarding(!canRenderWhileChecking);
    if (canRenderWhileChecking) setRedirectingToOnboarding(false);
    try {
      const status = await getOnboardingStatus();
      if (checkVersion !== onboardingCheckVersion.current) return;
      
      const isComplete = status?.onboarding_complete ?? status?.phases_completed?.complete ?? (
        status?.has_profile &&
        status?.has_asset &&
        status?.has_market &&
        status?.has_macro &&
        status?.has_setup &&
        status?.has_technical &&
        status?.has_strategy &&
        status?.has_bot
      );
      verifiedComplete.current = Boolean(isComplete);
      verifiedUserId.current = user.id;

      const nextRoute = status?.next_route || "/onboarding/profile";
      const nextUrl = new URL(nextRoute, window.location.origin);
      const nextPathname = nextUrl.pathname;
      const currentParams = new URLSearchParams(window.location.search);
      currentParams.sort();
      const currentRoute = `${pathname}${currentParams.toString() ? `?${currentParams.toString()}` : ""}`;
      const nextParams = new URLSearchParams(nextUrl.search);
      nextParams.sort();
      const normalizedNextRoute = `${nextPathname}${nextParams.toString() ? `?${nextParams.toString()}` : ""}`;
      const sameRoute = currentRoute === normalizedNextRoute;
      // Setup management remains available after a setup is persisted. This
      // lets users inspect or correct their own plan before the later bot
      // onboarding phase is complete.
      const canManageSavedSetup = pathname.startsWith("/setup") && Boolean(status?.has_setup);
      // A saved strategy unlocks Automation. Creating the bot completes that
      // phase, but the user still needs to visit the explicit finish screen.
      // Redirecting /bot to that screen here hides Automation after it renders.
      const canManageBot = pathname.startsWith("/bot") && Boolean(status?.has_strategy);

      debug("🧭 AuthGuard Onboarding Sync:", {
        isComplete,
        pathname,
        nextRoute,
        sameRoute,
      });

      if (!isComplete && !pathname.startsWith("/onboarding") && !sameRoute && !canManageSavedSetup && !canManageBot) {
        debug("🚧 AuthGuard: Onboarding niet compleet -> naar next_route", nextRoute);
        setRedirectingToOnboarding(true);
        router.replace(nextRoute);
        return;
      }

      setRedirectingToOnboarding(false);

    } catch (err) {
      if (checkVersion === onboardingCheckVersion.current) {
        console.error("💥 AuthGuard: Onboarding check gefaald", err);
      }
    } finally {
      if (checkVersion === onboardingCheckVersion.current) {
        setCheckingOnboarding(false);
      }
    }
  }, [user, isPublicRoute, pathname, router]);

  useEffect(() => {
    debug("🛡️ AuthGuard check:", { user: !!user, loading, sessionChecked, pathname });
    if (loading || !sessionChecked) return;

    if (!user && !isPublicRoute) {
      debug("🔒 AuthGuard: Geen gebruiker -> naar login");
      router.push(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }

    if (user && !isPublicRoute) {
      checkOnboardingStatus();
    } else {
      setCheckingOnboarding(false);
    }
  }, [
    user,
    loading,
    sessionChecked,
    pathname,
    isPublicRoute,
    router,
    checkOnboardingStatus,
  ]);

  // Show nothing while loading session ONLY for protected routes
  if ((loading || !sessionChecked) && !isPublicRoute) {
    debug("🛡️ AuthGuard showing loading spinner...", { loading, sessionChecked, isPublicRoute });
    return (
      <div className="min-h-screen bg-[#020617] flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if ((!isPublicRoute && checkingOnboarding) || redirectingToOnboarding) {
    return (
      <div className="min-h-screen bg-[#020617] flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return <>{children}</>;
}
