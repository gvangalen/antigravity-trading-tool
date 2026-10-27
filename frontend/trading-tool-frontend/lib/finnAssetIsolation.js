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
  // A user-scoped URL or workspace selection is already a valid FINN context.
  // Preference hydration may continue in the background without blocking it.
  if (selectedAsset) return "resolved";
  if (isAuthenticated && !preferencesHydrated) return "loading";
  return "unconfigured";
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

export function resolveFinnBotContextSymbol({ bot = null, routeSymbol = null, selectedAsset = null } = {}) {
  const botSymbol = bot?.strategy?.setup?.symbol || bot?.symbol || bot?.strategy?.symbol;
  return resolveFinnContextSymbol({
    urlSymbol: botSymbol || routeSymbol,
    activeSetupSymbol: bot?.strategy?.setup?.symbol,
    selectedAsset,
  });
}

export function resolveFinnBotPageContext({ search = "", activeBot = null, selectedAsset = null } = {}) {
  const params = new URLSearchParams(search);
  const requestedBotId = Number(params.get("bot_id"));
  const routeBotId = Number.isSafeInteger(requestedBotId) && requestedBotId > 0 ? requestedBotId : null;
  const selectedBot = routeBotId && Number(activeBot?.id || activeBot?.bot_id) !== routeBotId
    ? null : activeBot;
  const botId = routeBotId || Number(selectedBot?.id || selectedBot?.bot_id) || null;
  return {
    botId,
    bot: selectedBot,
    symbol: resolveFinnBotContextSymbol({
      bot: selectedBot,
      routeSymbol: normalizeScopedAssetSymbol(params.get("symbol") || params.get("asset")),
      selectedAsset,
    }),
  };
}

export function resolveFinnSubmissionContext({
  pathname,
  livePageContext,
  latestAssistantState = null,
  commandContext = {},
  chatAssetOverride = null,
  locale,
  query = "",
  autoSubmitCommand = false,
  originalCommandQuery = "",
} = {}) {
  const base = latestAssistantState?.current_flow
    ? { ...livePageContext, ...latestAssistantState }
    : { ...livePageContext };
  const request = {
    ...base,
    ...commandContext,
    locale,
    symbol: chatAssetOverride || commandContext.symbol || base.symbol,
  };
  if (pathname === "/bot") {
    const explicitBotId = Number(commandContext.bot_id);
    const explicitBotName = String(commandContext.bot_name || "").trim();
    const explicitBotAction = autoSubmitCommand
      && originalCommandQuery === query
      && commandContext.finn_subject_type === "bot"
      && Number.isSafeInteger(explicitBotId) && explicitBotId > 0
      && explicitBotName && String(query).toLocaleLowerCase().includes(explicitBotName.toLocaleLowerCase());
    // A named bot action from a clicked card keeps its explicit target. For
    // ordinary chat, the visible URL outranks old flow and asset selection.
    const focused = explicitBotAction ? commandContext : livePageContext;
    request.bot_id = focused.bot_id || null;
    request.symbol = focused.symbol || null;
    request.quote_currency = focused.quote_currency || null;
    request.setup_id = focused.setup_id || null;
    request.strategy_id = focused.strategy_id || null;
  }
  request.quote_currency = commandContext.quote_currency || (
    String(request.symbol || "").toUpperCase() === String(livePageContext?.symbol || "").toUpperCase()
      ? livePageContext?.quote_currency || null : null
  );
  return request;
}

export function shouldBlockFinnSubmission({
  isAuthenticated = false,
  assetStatus = "unconfigured",
} = {}) {
  return Boolean(isAuthenticated && assetStatus === "loading");
}
