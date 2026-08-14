const POPULAR_ONBOARDING_ASSETS = ["BTC", "ETH", "AAPL", "MSFT"];

export function normalizeOnboardingAsset(value) {
  return String(value || "").trim().toUpperCase();
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
  return [...POPULAR_ONBOARDING_ASSETS];
}
