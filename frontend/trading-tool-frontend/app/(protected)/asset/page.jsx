"use client";

import { useSearchParams } from "next/navigation";
import WorkspaceRenderer from "@/components/workspaces/WorkspaceRenderer";
import DashboardPage from "@/app/(protected)/dashboard/page";

export default function AssetPage() {
  const searchParams = useSearchParams();
  const queryTab = searchParams.get("tab");

  if (!queryTab || queryTab === "overview") {
    return <DashboardPage />;
  }

  return <WorkspaceRenderer tab={queryTab} />;
}
