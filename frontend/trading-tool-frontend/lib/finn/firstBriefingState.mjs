export function firstBriefingPhase(context) {
  if (!context?.is_first_dashboard) return null;
  const source = String(context.response_source || "").toLowerCase();
  const status = String(context.generation_status || "").toLowerCase();
  if (status === "ready" && source === "cached_ai") return "saved";
  if (source === "stale_while_revalidate" || status === "stale_while_revalidate") return "updating";
  if (["pending", "queued", "generating", "retry_scheduled"].includes(status)) return "generating";
  return "plan_summary";
}

export function canCacheMissionControl(missionControl) {
  const context = missionControl?.first_dashboard_context;
  // The onboarding briefing already has a durable owner-scoped server record.
  // A browser copy can belong to an older plan version and flash on refresh.
  return !context?.is_first_dashboard;
}
