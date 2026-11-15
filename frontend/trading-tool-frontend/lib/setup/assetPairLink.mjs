export function canonicalAssetPairSearch(search) {
  const params = new URLSearchParams(String(search || "").replace(/^\?/, ""));
  const pair = /^([A-Z0-9._-]+)\/(EUR|USD|USDT)$/.exec(
    String(params.get("symbol") || "").trim().toUpperCase(),
  );
  if (!pair) return null;
  params.set("symbol", pair[1]);
  params.set("quote", pair[2]);
  return params.toString();
}
