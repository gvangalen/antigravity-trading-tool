"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAsset } from "@/app/providers/AssetProvider";
import AssetWorkspace from "@/components/workspaces/asset/AssetWorkspace";

const WORKSPACE_TABS = new Set(["overview", "market", "macro", "technical", "ai"]);

function normalizeTab(tab, fallback = "overview") {
  return WORKSPACE_TABS.has(tab) ? tab : fallback;
}

function normalizeSymbol(symbol, fallback = "BTC") {
  const value = String(symbol || fallback).trim().toUpperCase();
  return value || fallback;
}

export default function WorkspaceRenderer({ tab = "overview", canonicalizeLegacy = false }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryString = searchParams.toString();
  const { selectedAsset } = useAsset();
  const resolvedTab = normalizeTab(searchParams.get("tab") || tab, tab);
  const resolvedSymbol = normalizeSymbol(
    searchParams.get("symbol") || searchParams.get("asset") || selectedAsset || "BTC"
  );

  useEffect(() => {
    if (!canonicalizeLegacy || pathname === "/asset") return;

    const params = new URLSearchParams(queryString);
    params.set("symbol", resolvedSymbol);
    params.set("tab", resolvedTab);
    router.replace(`/asset?${params.toString()}`, { scroll: false });
  }, [canonicalizeLegacy, pathname, queryString, resolvedSymbol, resolvedTab, router]);

  return <AssetWorkspace initialTab={resolvedTab} />;
}
