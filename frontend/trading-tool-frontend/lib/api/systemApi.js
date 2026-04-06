import { fetchAuth } from "@/lib/api/auth";

/**
 * 🚀 Bootstrap AI agents na onboarding
 */
export const bootstrapAgents = async () => {
  const res = await fetchAuth("/api/system/bootstrap-agents", {
    method: "POST",
  });

  return res;
};
