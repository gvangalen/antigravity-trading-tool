"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { API_BASE_URL } from "@/lib/config";

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
  const [onboardingComplete, setOnboardingComplete] = useState(false);

  // Routes that don't need auth
  const publicRoutes = ["/", "/login", "/register", "/print", "/daily-report"];
  const isPublicRoute = publicRoutes.some(route => pathname === route || pathname.startsWith("/public/"));

  useEffect(() => {
    console.log("🛡️ AuthGuard check:", { user: !!user, loading, sessionChecked, pathname });
    if (loading || !sessionChecked) return;

    // 1. Check Authentication
    if (!user && !isPublicRoute) {
      console.log("🔒 AuthGuard: Geen gebruiker -> naar login");
      router.push("/login");
      return;
    }

    // 2. Check Onboarding if user exists
    if (user && !isPublicRoute) {
      // Only re-fetch or re-check if not already definitively complete
      if (!onboardingComplete) {
        checkOnboardingStatus();
      } else {
        // If already complete, we just need to make sure we aren't stuck on /onboarding
        if (pathname.startsWith("/onboarding")) {
          console.log("✅ AuthGuard: Onboarding al klaar -> naar dashboard");
          router.push("/dashboard");
        }
        setCheckingOnboarding(false);
      }
    } else {
      setCheckingOnboarding(false);
    }
  }, [user, loading, sessionChecked, pathname, isPublicRoute, onboardingComplete]);

  async function checkOnboardingStatus() {
    // Avoid double-fetching
    if (!checkingOnboarding && onboardingComplete) return;

    setCheckingOnboarding(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/onboarding/status`, {
        credentials: "include",
      });

      if (res.status === 401) {
        router.push("/login");
        return;
      }

      const status = await res.json();
      
      // ✅ Use explicit master flag from backend if available, fallback to manual check
      const isComplete = status?.onboarding_complete ?? (
        status?.has_setup &&
        status?.has_technical &&
        status?.has_macro &&
        status?.has_market &&
        status?.has_strategy
      );

      console.log("🧭 AuthGuard Onboarding Sync:", { isComplete, pathname });
      setOnboardingComplete(isComplete);

      // Redirect logic
      if (!isComplete && 
          !pathname.startsWith("/onboarding") && 
          !pathname.startsWith("/setup") && 
          !pathname.startsWith("/technical") && 
          !pathname.startsWith("/macro") && 
          !pathname.startsWith("/market") && 
          !pathname.startsWith("/strategy")) {
        console.log("🚧 AuthGuard: Onboarding niet compleet -> naar /onboarding");
        router.push("/onboarding");
      } else if (isComplete && pathname.startsWith("/onboarding")) {
        console.log("✅ AuthGuard: Onboarding al klaar -> naar dashboard");
        router.push("/dashboard");
      }

    } catch (err) {
      console.error("💥 AuthGuard: Onboarding check gefaald", err);
    } finally {
      setCheckingOnboarding(false);
    }
  }

  // Show nothing while loading session ONLY for protected routes
  if ((loading || !sessionChecked) && !isPublicRoute) {
    console.log("🛡️ AuthGuard showing loading spinner...", { loading, sessionChecked, isPublicRoute });
    return (
      <div className="min-h-screen bg-[#020617] flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return <>{children}</>;
}
