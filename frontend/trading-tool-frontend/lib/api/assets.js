import { fetchAuth } from "@/lib/api/auth";

export async function searchAssets(query, options = {}) {
  const {
    assetClasses = ["crypto", "stock"],
    limit = 8,
  } = options;

  const normalizedQuery = String(query || "").trim();
  if (!normalizedQuery) return [];

  const params = new URLSearchParams({
    q: normalizedQuery,
    asset_classes: assetClasses.join(","),
    limit: String(limit),
  });

  return await fetchAuth(`/api/assets/search?${params.toString()}`, {
    method: "GET",
  });
}
