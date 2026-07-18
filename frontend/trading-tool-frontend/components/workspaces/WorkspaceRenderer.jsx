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
  const { selectedAsset } = useAsset();
  const resolvedTab = normalizeTab(searchParams.get("tab") || tab, tab);
  const resolvedSymbol = normalizeSymbol(
    searchParams.get("symbol") || searchParams.get("asset") || selectedAsset || "BTC"
  );
  const variant = searchParams.get("variant") === "legacy" ? "legacy" : "v3";

  useEffect(() => {
    if (!canonicalizeLegacy || pathname === "/asset") return;

    const params = new URLSearchParams(queryString);
    params.set("symbol", resolvedSymbol);
    params.set("tab", resolvedTab);
    router.replace(`/asset?${params.toString()}`, { scroll: false });
  }, [canonicalizeLegacy, pathname, queryString, resolvedSymbol, resolvedTab, router]);

  if (variant === "legacy") {
    return <AssetWorkspace initialTab={resolvedTab} />;
  }

  return <AssetWorkspaceV3 initialTab={resolvedTab} variant="v3" />;
}
