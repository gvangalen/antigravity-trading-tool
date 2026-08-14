"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import WorkspaceRenderer from "@/components/workspaces/WorkspaceRenderer";

export default function AssetPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const onboardingMode = searchParams.get("onboarding") === "1";
    if (!onboardingMode) return;

    const symbol = String(searchParams.get("symbol") || searchParams.get("asset") || "BTC").toUpperCase();
    router.replace(`/onboarding/analysis?onboarding=1&step=analysis&symbol=${encodeURIComponent(symbol)}`);
  }, [router, searchParams]);

  return <WorkspaceRenderer tab="market" />;
}
