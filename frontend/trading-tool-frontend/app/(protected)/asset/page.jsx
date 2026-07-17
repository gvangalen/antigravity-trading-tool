"use client";

import { useSearchParams } from "next/navigation";
import WorkspaceRenderer from "@/components/workspaces/WorkspaceRenderer";
import DashboardPage from "@/app/(protected)/dashboard/page";

export default function AssetPage() {
  const searchParams = useSearchParams();
  const queryTab = searchParams.get("tab");
  const variant = searchParams.get("variant");

  if (variant !== "v3" && (!queryTab || queryTab === "overview")) {
    return <DashboardPage />;
  }

  return <WorkspaceRenderer tab="market" />;
}
