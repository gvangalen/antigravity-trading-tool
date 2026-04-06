"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import AILoader from "@/components/ui/AILoader";

export default function AuthGuard({ children }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  // ✅ Tijdens auth check altijd loader (voorkomt flicker / race issues)
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <AILoader text="Aan het laden…" />
      </div>
    );
  }

  // ✅ Na loading: geen user = redirect loopt
  if (!user) return null;

  return <>{children}</>;
}
