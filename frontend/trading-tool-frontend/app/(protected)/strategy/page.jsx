"use client";

import StrategiesWorkspaceSection from "@/components/my-plan/StrategiesWorkspaceSection";

export default function StrategyPage() {
  // Strategies are a first-class child of a setup. Keep this route reachable
  // so one setup can own and manage more than one owner-scoped strategy.
  return <StrategiesWorkspaceSection />;
}
