"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import WorkspaceRenderer from "@/components/workspaces/WorkspaceRenderer";
import { canonicalAssetPairSearch } from "@/lib/setup/assetPairLink.mjs";

export default function AssetPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const canonicalQuery = canonicalAssetPairSearch(searchParams.toString());

  useEffect(() => {
    if (canonicalQuery) {
      router.replace(`/asset?${canonicalQuery}`);
      return;
    }
    const onboardingMode = searchParams.get("onboarding") === "1";
    if (!onboardingMode) return;

    const symbol = String(searchParams.get("symbol") || searchParams.get("asset") || "BTC").toUpperCase();
    router.replace(`/onboarding/analysis?onboarding=1&step=analysis&symbol=${encodeURIComponent(symbol)}`);
  }, [canonicalQuery, router, searchParams]);

  return canonicalQuery ? null : <WorkspaceRenderer tab="market" />;
}
