"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { getOnboardingStatus } from "@/lib/api/onboarding";

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
  const onboardingCheckInFlight = useRef(false);

  // Routes that don't need auth
  const publicRoutes = ["/", "/login", "/register", "/forgot-password", "/reset-password", "/print", "/daily-report"];
  const isPublicRoute = publicRoutes.some(route => pathname === route || pathname.startsWith("/public/"));
  const debug = (...args) => {
    if (process.env.NODE_ENV === "development") console.log(...args);
  };

  const checkOnboardingStatus = useCallback(async () => {
    if (onboardingCheckInFlight.current) return;
    if (!user || isPublicRoute) {
      setCheckingOnboarding(false);
      return;
    }

    onboardingCheckInFlight.current = true;
    setCheckingOnboarding(true);
    try {
      const status = await getOnboardingStatus();
      
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

      debug("🧭 AuthGuard Onboarding Sync:", {
        isComplete,
        pathname,
        nextRoute,
        sameRoute,
      });

      if (!isComplete && !pathname.startsWith("/onboarding") && !sameRoute) {
        debug("🚧 AuthGuard: Onboarding niet compleet -> naar next_route", nextRoute);
        setRedirectingToOnboarding(true);
        router.replace(nextRoute);
        return;
      }

      setRedirectingToOnboarding(false);

    } catch (err) {
      console.error("💥 AuthGuard: Onboarding check gefaald", err);
    } finally {
      onboardingCheckInFlight.current = false;
      setCheckingOnboarding(false);
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
