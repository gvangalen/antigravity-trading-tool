const SUPPORTED_ONBOARDING_ASSETS = ["BTC", "ETH", "SOL", "ADA", "DOT"];

export function normalizeOnboardingAsset(value) {
  const normalized = String(value || "").trim().toUpperCase();
  return SUPPORTED_ONBOARDING_ASSETS.includes(normalized) ? normalized : "";
}

export function readOnboardingAssetPreference(preferences = {}) {
  return normalizeOnboardingAsset(
    preferences.onboarding_asset || preferences.selected_asset || preferences.active_asset
  );
}

export function buildOnboardingAssetPreferencePatch(asset) {
  const normalized = normalizeOnboardingAsset(asset);
  if (!normalized) return {};
  return {
    onboarding_asset: normalized,
    selected_asset: normalized,
  };
}

export function getSupportedOnboardingAssets() {
  return [...SUPPORTED_ONBOARDING_ASSETS];
}
