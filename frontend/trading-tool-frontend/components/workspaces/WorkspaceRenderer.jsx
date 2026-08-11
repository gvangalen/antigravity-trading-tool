"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAsset } from "@/app/providers/AssetProvider";
import AssetWorkspace from "@/components/workspaces/asset/AssetWorkspace";
import AssetWorkspaceV3 from "@/components/workspaces/asset/AssetWorkspaceV3";

const WORKSPACE_TABS = new Set(["market", "macro", "technical"]);

function normalizeTab(tab, fallback = "market") {
  if (tab === "overview" || tab === "ai" || tab === "conclusion") {
    return "market";
  }

  return WORKSPACE_TABS.has(tab) ? tab : fallback;
}

function normalizeSymbol(symbol, fallback = "BTC") {
  const value = String(symbol || fallback).trim().toUpperCase();
  return value || fallback;
}

export default function WorkspaceRenderer({ tab = "market", canonicalizeLegacy = false }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryString = searchParams.toString();
  const { selectedAsset, setSelectedAsset } = useAsset();
  const resolvedTab = normalizeTab(searchParams.get("tab") || tab, tab);
  const resolvedSymbol = normalizeSymbol(
    searchParams.get("symbol") || searchParams.get("asset") || selectedAsset || "BTC"
  );
  const variant = searchParams.get("variant") === "legacy" ? "legacy" : "v3";
  const hasExplicitSymbol = Boolean(searchParams.get("symbol") || searchParams.get("asset"));
  const hasCanonicalSymbol = searchParams.get("symbol") === resolvedSymbol;
  const hasCanonicalTab = searchParams.get("tab") === resolvedTab;

  useEffect(() => {
    if (resolvedSymbol && resolvedSymbol !== selectedAsset) {
      setSelectedAsset(resolvedSymbol);
    }
  }, [resolvedSymbol, selectedAsset, setSelectedAsset]);

  useEffect(() => {
    if (pathname === "/asset") {
      if (hasCanonicalSymbol && hasCanonicalTab && !searchParams.get("asset")) return;

      const params = new URLSearchParams(queryString);
      params.set("symbol", resolvedSymbol);
      params.set("tab", resolvedTab);
      params.delete("asset");
      router.replace(`/asset?${params.toString()}`, { scroll: false });
      return;
    }

    if (!canonicalizeLegacy) return;

    const params = new URLSearchParams(queryString);
    params.set("symbol", resolvedSymbol);
    params.set("tab", resolvedTab);
    router.replace(`/asset?${params.toString()}`, { scroll: false });
  }, [
    canonicalizeLegacy,
    hasExplicitSymbol,
    hasCanonicalSymbol,
    hasCanonicalTab,
    pathname,
    queryString,
    resolvedSymbol,
    resolvedTab,
    router,
    searchParams,
    variant,
  ]);

  if (variant === "legacy") {
    return <AssetWorkspace initialTab={resolvedTab} />;
  }

  return <AssetWorkspaceV3 initialTab={resolvedTab} variant="v3" />;
}
