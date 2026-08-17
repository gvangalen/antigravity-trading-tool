export function normalizeScopedAssetSymbol(value) {
  const normalized = String(value || "").trim().toUpperCase();
  return /^[A-Z0-9._:-]{1,20}$/.test(normalized) ? normalized : null;
}

export function resolveScopedAssetStatus({
  isPublicAuthRoute = false,
  sessionChecked = false,
  isAuthenticated = false,
  preferencesHydrated = false,
  selectedAsset = null,
} = {}) {
  if (isPublicAuthRoute) return selectedAsset ? "resolved" : "unconfigured";
  if (!sessionChecked) return "loading";
  if (isAuthenticated && !preferencesHydrated) return "loading";
  return selectedAsset ? "resolved" : "unconfigured";
}

export function resolveFinnContextSymbol({
  urlSymbol = null,
  activeSetupSymbol = null,
  selectedAsset = null,
} = {}) {
  return (
    normalizeScopedAssetSymbol(urlSymbol) ||
    normalizeScopedAssetSymbol(activeSetupSymbol) ||
    normalizeScopedAssetSymbol(selectedAsset) ||
    null
  );
}

export function shouldBlockFinnSubmission({
  isAuthenticated = false,
  assetStatus = "unconfigured",
} = {}) {
  return Boolean(isAuthenticated && assetStatus === "loading");
}
