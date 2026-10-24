"use client";

import React, { Suspense, useState, useEffect, useLayoutEffect, useRef } from "react";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { cancelFinnV2Proposal, cancelFinnV2Run, confirmAndExecuteFinnV2Proposal, getAssistantPreferences, getFinnV2Conversations, getFinnV2ConversationDetail, updateAssistantPreferences, assistantChatStream, abortAssistantChatStream, fetchFinnV2Proposal, fetchFinnV2Run, waitForFinnV2TerminalSse } from "@/lib/api/ai";
import { Send, Shield, Loader2, X, Bot, ListChecks, CheckCircle2, Plus, Search, SlidersHorizontal, History, Maximize2, Minimize2, Square } from "lucide-react";
import { useAsset } from "@/app/providers/AssetProvider";
import { useAuth } from "@/components/auth/AuthProvider";
import { useWatchlist } from "@/hooks/useWatchlist";
import { useModal } from "@/components/modal/ModalProvider";
import { fetchSetups } from "@/lib/api/setups";
import { fetchStrategies } from "@/lib/api/strategy";
import { fetchBotConfigs } from "@/lib/api/botApi";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import { useActiveBot } from "@/app/providers/ActiveBotProvider";
import { actionButtonStyles } from "@/components/ui/actionButtonStyles";
import { getAssistantSessionId, trackAssistantEvent } from "@/lib/api/assistantAnalytics";
import { normalizeScopedAssetSymbol, resolveFinnBotPageContext, resolveFinnContextSymbol, shouldBlockFinnSubmission } from "@/lib/finnAssetIsolation";
import { normalizeTraderProfilePreferences } from "@/lib/traderProfileOptions";
import { useTranslation } from "@/app/providers/I18nProvider";
import FinnCommandCenter from "@/components/finn/FinnCommandCenter";
import { FINN_ASSETS, resolveFeedDraftQuery, shouldAttachFeedContext } from "@/lib/finnCommandSearch";
import { getActiveSetupId } from "@/lib/setup/activeSetup";
import { indicatorDisplayName } from "@/lib/indicators/configuredIndicatorRows.mjs";
import { formatDraftCardValue, formatExecutionMode } from "@/lib/contractValueFormatter.mjs";
import { clearActiveFinnConversation, readActiveFinnConversation, writeActiveFinnConversation } from "@/lib/finnActiveConversation.mjs";
import { parseFinnChatText } from "@/lib/finnChatText.mjs";
import { finnSubmissionLocale } from "@/lib/finnChatLocale.mjs";
import { inactiveProposalIds, isFinnProposalCorrection, mapBackendSessionMessages, retireEarlierFinnProposalCards, retireFinnProposalCards, setupDraftFrequencyLabel, suspendedProposalIds, suspendFinnProposalCards, verifiedPaperBotStrategy } from "@/lib/finnProposalCardState.mjs";
import { clarificationQuestionChoices, draftConversationCopy, draftQuestionChoices, hasConfirmableDraft, isCollectingDraft, isOpenClarification } from "@/lib/finnDraftConversation.mjs";

const INDICATOR_MODAL_OPEN_EVENT = "finn-indicator-config:open";
const INDICATOR_MODAL_COMPLETED_EVENT = "finn-indicator-config:completed";
const FINN_RECENT_CONVERSATIONS_STORAGE_KEY = "finn-recent-conversations:v1";
const MAX_RECENT_FINN_CONVERSATIONS = 3;
const ACTIVE_FINN_SESSION_ID_KEY = "active_finn_session_id";

function publicFinnExecutionError(value) {
  const reason = String(value || "").replace(/^\d{3}:\s*/, "").trim();
  if (/^Deze setup is nog gekoppeld aan strategie /.test(reason)) return reason;
  if (/^Deze strategie is nog gekoppeld aan paper-bot /.test(reason)) return reason;
  return "Dat lukte niet. Ik heb niets gewijzigd.";
}

function normalizeFinnSessionId(value) {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return normalized || null;
}

function isFinnV2ConversationId(value) {
  return typeof value === "string" && value.startsWith("finn-v2-conv-");
}

function scopedRecentConversationStorageKey(userId) {
  const scope = String(userId || "anonymous").trim() || "anonymous";
  return `${FINN_RECENT_CONVERSATIONS_STORAGE_KEY}:${scope}`;
}

function sanitizeMessageForPersistence(message) {
  if (!message || typeof message.text !== "string") return null;
  const text = message.text.trim();
  if (!text) return null;

  return {
    role: message.role === "user" ? "user" : "assistant",
    text,
    isError: Boolean(message.isError),
    timestamp: message.timestamp || null,
  };
}

function getRecentConversationTitle(messages = []) {
  const latestUserMessage = [...messages].reverse().find((message) => message?.role === "user" && message?.text);
  if (latestUserMessage?.text) {
    return latestUserMessage.text;
  }

  const latestAssistantMessage = [...messages].reverse().find((message) => message?.text);
  if (latestAssistantMessage?.text) {
    return latestAssistantMessage.text;
  }

  return "Verdergaan met FINN";
}

function formatRecentConversationTime(timestamp) {
  if (!timestamp) return "";

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";

  return new Intl.DateTimeFormat("nl-NL", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function getDictionaryValue(dictionary, path) {
  return String(path || "")
    .split(".")
    .filter(Boolean)
    .reduce((current, part) => (current && typeof current === "object" ? current[part] : undefined), dictionary);
}

function interpolateTranslation(template, vars = {}) {
  if (typeof template !== "string") return template;
  return template.replace(/\{(\w+)\}/g, (_, key) => {
    const value = vars[key];
    return value === undefined || value === null ? "" : String(value);
  });
}

function normalizeVisibleBriefing(value) {
  const seen = new Set();
  return String(value || "")
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => {
      if (!line || /^(?:NOT_REVIEWED_YET|not_reviewed_yet)$/i.test(line)) return false;
      const key = line.toLocaleLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .join("\n");
}

function createAssistantTranslator(t) {
  const assistantCopy = t?.assistant || {};
  return (path, fallback = "", vars = {}) => interpolateTranslation(getDictionaryValue(assistantCopy, path) ?? fallback, vars);
}

function buildAssistantUiText(at) {
  return {
    activeBriefing: at("uiText.activeBriefing"),
    briefingSaved: at("uiText.briefingSaved"),
    briefingUpdating: at("uiText.briefingUpdating"),
    briefingGeneratingLabel: at("uiText.briefingGeneratingLabel"),
    briefingPlanSummary: at("uiText.briefingPlanSummary"),
    defensivePosture: at("uiText.defensivePosture"),
    alignedTo: at("uiText.alignedTo"),
    workspaceOverview: at("uiText.workspaceOverview"),
    loadingWorkspace: at("uiText.loadingWorkspace"),
    todayFirst: at("uiText.todayFirst"),
    why: at("uiText.why"),
    noActions: at("uiText.noActions"),
    noReviews: at("uiText.noReviews"),
    noPerformance: at("uiText.noPerformance"),
    noHistory: at("uiText.noHistory"),
    workspaceSummary: at("uiText.workspaceSummary"),
    workspaceStatusMarket: at("uiText.workspaceStatusMarket"),
    workspaceStatusReviews: at("uiText.workspaceStatusReviews"),
    workspaceStatusRisks: at("uiText.workspaceStatusRisks"),
    workspaceStatusOpen: at("uiText.workspaceStatusOpen"),
    workspaceActionNeeded: at("uiText.workspaceActionNeeded"),
    workspaceOnTrack: at("uiText.workspaceOnTrack"),
    workspacePrimaryAction: at("uiText.workspacePrimaryAction"),
    workspaceQueue: at("uiText.workspaceQueue"),
    workspaceDetails: at("uiText.workspaceDetails"),
    workspaceSectionToday: at("uiText.workspaceSectionToday"),
    workspaceSectionReviews: at("uiText.workspaceSectionReviews"),
    workspaceSectionRisks: at("uiText.workspaceSectionRisks"),
    workspaceSectionPerformance: at("uiText.workspaceSectionPerformance"),
    workspaceSectionHistory: at("uiText.workspaceSectionHistory"),
    workspaceSectionMore: at("uiText.workspaceSectionMore"),
    workspaceSummaryToday: at("uiText.workspaceSummaryToday"),
    workspaceSummaryReviews: at("uiText.workspaceSummaryReviews"),
    workspaceSummaryRisks: at("uiText.workspaceSummaryRisks"),
    workspaceSummaryPerformance: at("uiText.workspaceSummaryPerformance"),
    workspaceSummaryHistory: at("uiText.workspaceSummaryHistory"),
    workspaceFirstDashboardHeadline: at("uiText.workspaceFirstDashboardHeadline"),
    workspaceFirstDashboardSupport: at("uiText.workspaceFirstDashboardSupport"),
    workspaceFirstDashboardHint: at("uiText.workspaceFirstDashboardHint"),
    workspaceFirstDashboardLabel: at("uiText.workspaceFirstDashboardLabel"),
    workspaceBuildingHeadline: at("uiText.workspaceBuildingHeadline"),
    workspaceBuildingSupport: at("uiText.workspaceBuildingSupport"),
    workspaceBuildingHint: at("uiText.workspaceBuildingHint"),
    workspaceBuildingLabel: at("uiText.workspaceBuildingLabel"),
    readOnlyMode: at("uiText.readOnlyMode"),
    paperMode: at("uiText.paperMode"),
    conceptMode: at("uiText.conceptMode"),
    retry: at("uiText.retry"),
    inputPlaceholder: at("uiText.inputPlaceholder"),
    composerAsset: at("uiText.composerAsset"),
    composerIndicator: at("uiText.composerIndicator"),
    composerMenu: at("uiText.composerMenu"),
    composerInstruction: at("uiText.composerInstruction"),
    recentConversations: at("uiText.recentConversations"),
    backendSessions: at("uiText.backendSessions"),
    continueConversation: at("uiText.continueConversation"),
    newConversation: at("uiText.newConversation"),
    setupWizard: at("uiText.setupWizard"),
    startGuide: at("uiText.startGuide"),
    decisionReviewFallback: at("uiText.decisionReviewFallback"),
    openExecutionConsole: at("uiText.openExecutionConsole"),
    nextSteps: at("uiText.nextSteps"),
    finnOverview: at("uiText.finnOverview"),
    memoryV2: at("uiText.memoryV2"),
    whyFinnBrakes: at("uiText.whyFinnBrakes"),
    decisionExplain: at("uiText.decisionExplain"),
    whyThis: at("uiText.whyThis"),
    whyNow: at("uiText.whyNow"),
    whatNow: at("uiText.whatNow"),
    doNotDo: at("uiText.doNotDo"),
    firstThis: at("uiText.firstThis"),
    thenReview: at("uiText.thenReview"),
    canWait: at("uiText.canWait"),
    rhythmToday: at("uiText.rhythmToday"),
    behaviorDiscipline: at("uiText.behaviorDiscipline"),
    markDone: at("uiText.markDone"),
    reviewLater: at("uiText.reviewLater"),
    finnBrakesBecause: at("uiText.finnBrakesBecause"),
    chooseSetup: at("uiText.chooseSetup"),
    chooseStrategy: at("uiText.chooseStrategy"),
    chooseIndicatorNode: at("uiText.chooseIndicatorNode"),
    planDeviation: at("uiText.planDeviation"),
    overrideConfirmed: at("uiText.overrideConfirmed"),
    overrideRequired: at("uiText.overrideRequired"),
    planDeviationTitle: at("uiText.planDeviationTitle"),
    safeRoute: at("uiText.safeRoute"),
    missingStill: at("uiText.missingStill"),
    invalid: at("uiText.invalid"),
    confirm: at("uiText.confirm"),
    behavioralMemoryCheck: at("uiText.behavioralMemoryCheck"),
    consciousConfirmationNeeded: at("uiText.consciousConfirmationNeeded"),
    consciouslyContinue: at("uiText.consciouslyContinue"),
    reviewFirst: at("uiText.reviewFirst"),
    tradeReview: at("uiText.tradeReview"),
    finnActionNeedsConfirmation: at("uiText.finnActionNeedsConfirmation"),
    context: at("uiText.context"),
    impact: at("uiText.impact"),
    safety: at("uiText.safety"),
    afterThis: at("uiText.afterThis"),
    aiCommandCenter: at("uiText.aiCommandCenter"),
    reasoningChains: at("uiText.reasoningChains"),
    actionCanceled: at("uiText.actionCanceled"),
    actionSucceeded: at("uiText.actionSucceeded"),
    asset: at("uiText.asset"),
    setupType: at("uiText.setupType"),
    marketCondition: at("uiText.marketCondition"),
    marketConditionConfirmedStrength: at("uiText.marketConditionConfirmedStrength"),
    marketConditionBalancedPullback: at("uiText.marketConditionBalancedPullback"),
    marketConditionEarlyDip: at("uiText.marketConditionEarlyDip"),
    dcaParameters: at("uiText.dcaParameters"),
    scoreThresholds: at("uiText.scoreThresholds"),
    scoreThresholdsMissing: at("uiText.scoreThresholdsMissing"),
    baseBudget: at("uiText.baseBudget"),
    entryTarget: at("uiText.entryTarget"),
    stopLoss: at("uiText.stopLoss"),
    takeProfitTargets: at("uiText.takeProfitTargets"),
    dcaMultiplierMode: at("uiText.dcaMultiplierMode"),
    targetAsset: at("uiText.targetAsset"),
    noDetailedParameters: at("uiText.noDetailedParameters"),
    loadingShort: at("uiText.loadingShort"),
    edit: at("uiText.edit"),
    cancel: at("uiText.cancel"),
    approve: at("uiText.approve"),
    actionCheck: at("uiText.actionCheck"),
    actionCheckBody: at("uiText.actionCheckBody"),
    proposedAction: at("uiText.proposedAction"),
    conceptReview: at("uiText.conceptReview"),
    activeConcept: at("uiText.activeConcept"),
    dcaFrequency: at("uiText.dcaFrequency"),
    chooseAmount: at("uiText.chooseAmount"),
    optional: at("uiText.optional"),
    required: at("uiText.required"),
    botName: at("uiText.botName"),
    safetyProfile: at("uiText.safetyProfile"),
    budget: at("uiText.budget"),
    environment: at("uiText.environment"),
    mode: at("uiText.mode"),
    liveReal: at("uiText.liveReal"),
    paperSandbox: at("uiText.paperSandbox"),
    newConcept: at("uiText.newConcept"),
    setupConceptSuffix: at("uiText.setupConceptSuffix"),
    strategyConceptSuffix: at("uiText.strategyConceptSuffix"),
    botConceptSuffix: at("uiText.botConceptSuffix"),
    conceptSuffix: at("uiText.conceptSuffix"),
    debugReasoning: at("uiText.debugReasoning"),
    confidence: at("uiText.confidence"),
    risk: at("uiText.risk"),
    detected: at("uiText.detected"),
    safe: at("uiText.safe"),
    coaching: at("uiText.coaching"),
    general: at("uiText.general"),
    riskLow: at("uiText.riskLow"),
    riskMedium: at("uiText.riskMedium"),
    riskHigh: at("uiText.riskHigh"),
    riskActive: at("uiText.riskActive"),
    riskConservative: at("uiText.riskConservative"),
    riskBalanced: at("uiText.riskBalanced"),
    operational: at("uiText.operational"),
    daily: at("uiText.daily"),
    weekly: at("uiText.weekly"),
    monthly: at("uiText.monthly"),
    notAvailable: at("uiText.notAvailable"),
    missingSetupForStrategy: at("uiText.missingSetupForStrategy"),
    missingStrategyForBot: at("uiText.missingStrategyForBot"),
    draftSetupApproved: at("uiText.draftSetupApproved"),
    draftStrategyApproved: at("uiText.draftStrategyApproved"),
    draftBotApproved: at("uiText.draftBotApproved"),
    draftApproveError: at("uiText.draftApproveError"),
    paperExecutionPendingVerification: at("uiText.paperExecutionPendingVerification"),
    botDecisionPaperExecuted: at("uiText.botDecisionPaperExecuted"),
    botDecisionSkippedVerified: at("uiText.botDecisionSkippedVerified"),
    defaultBotName: at("uiText.defaultBotName"),
    riskAgent: at("uiText.riskAgent", "Risico-agent"),
    whyLabelPrefix: at("uiText.whyLabelPrefix", "Waarom"),
    whyBlocked: at("uiText.whyBlocked", "Waarom blokkeert dit?"),
    portfolioAssetFallback: at("uiText.portfolioAssetFallback", "Portfolio"),
    riskStackTitleSuffix: at("uiText.riskStackTitleSuffix", "risico stapelt"),
    riskStackExplainLabelSuffix: at("uiText.riskStackExplainLabelSuffix", "risico-uitleg"),
    riskStackPrompt: at("uiText.riskStackPrompt", "Welke risico's stapelen nu voor {asset}?"),
    liveBotsNeedAttention: at("uiText.liveBotsNeedAttention", "live bots vragen aandacht"),
  };
}

function buildIndicatorModalRequest(envelope, fallbackSymbol) {
  const draft = envelope?.draft;
  const isIndicatorConfig =
    draft?.draft_kind === "indicator_config" ||
    envelope?.intent === "indicator_config" ||
    envelope?.flow === "indicator_config";

  if (!isIndicatorConfig || !draft || draft.operation === "delete") return null;

  const category = draft.category || envelope?.category || "technical";
  const rawIndicatorName = draft.indicator || draft.payload?.indicator || draft.node;
  const indicatorName = typeof rawIndicatorName === "string"
    ? rawIndicatorName.replace(/^.*\(([^)]+)\)\s*$/, "$1").trim()
    : rawIndicatorName;
  if (!indicatorName) return null;

  const symbol = draft.symbol || envelope?.selected_entity?.asset || fallbackSymbol || "BTC";
  const label = draft.display_name || indicatorDisplayName(indicatorName);

  return {
    category,
    indicatorName,
    title: label,
    assetSymbol: symbol,
    responseText: `Ik heb ${label} voor ${symbol} klaargezet. Controleer de instellingen om hem toe te voegen.`,
  };
}

function getSetupMarketConditionLabel(condition, uiText) {
  const current = uiText?.marketConditionOptions?.[condition]?.title;
  if (current) return current;
  switch (condition) {
    case "confirmed_strength":
      return uiText.marketConditionConfirmedStrength;
    case "balanced_pullback":
      return uiText.marketConditionBalancedPullback;
    case "early_dip":
      return uiText.marketConditionEarlyDip;
    default:
      return condition || "—";
  }
}

function inferSetupMarketConditionFromScores(payload = {}) {
  const minimum = payload?.min_benchmark_score;
  const maximum = payload?.max_benchmark_score;
  if (minimum == null || maximum == null) return null;
  const bands = [
    [0, 25, "heavy_pressure"], [26, 45, "pressure"],
    [46, 60, "no_direction"], [61, 75, "gaining_strength"],
    [76, 100, "strong"],
  ];
  return bands.find(([min, max]) => Number(minimum) === min && Number(maximum) === max)?.[2] || "custom";
}

function humanizeFinnContextValue(value, fallback = "") {
  const raw = String(value || "").trim();
  if (!raw) return fallback;

  const normalized = raw.toLowerCase();
  const timeframeMap = {
    "1d": "Day",
    day: "Day",
    daily: "Day",
    "1w": "Week",
    week: "Week",
    weekly: "Week",
    "1m": "Month",
    month: "Month",
    monthly: "Month",
    overview: "Overview",
    workflow: "Workflow",
    market: "Market",
    macro: "Macro",
    technical: "Technical",
    setups: "Setups",
    setup: "Setups",
    strategies: "Strategies",
    strategy: "Strategies",
    bots: "Bots",
    bot: "Bots",
    reports: "Reports",
    report: "Reports",
  };

  if (timeframeMap[normalized]) return timeframeMap[normalized];
  if (raw === raw.toUpperCase() && raw.length <= 5) return raw;

  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

function getFinnWorkspaceLabel(pathname, locale) {
  const normalizedLocale = String(locale || "nl").toLowerCase();
  const labels = normalizedLocale.startsWith("en")
    ? { asset: "Analysis", setup: "My Plan", bot: "Automation", report: "Reflection", portfolio: "Portfolio" }
    : normalizedLocale.startsWith("de")
      ? { asset: "Analyse", setup: "Mein Plan", bot: "Automatisierung", report: "Reflexion", portfolio: "Portfolio" }
      : { asset: "Analyse", setup: "Mijn Plan", bot: "Automatisering", report: "Reflectie", portfolio: "Portfolio" };

  if (pathname?.startsWith("/setup") || pathname?.startsWith("/strategy")) return labels.setup;
  if (pathname?.startsWith("/bot")) return labels.bot;
  if (pathname?.startsWith("/report")) return labels.report;
  if (pathname?.startsWith("/portfolio")) return labels.portfolio;
  return labels.asset;
}

function compactFinnTimeframe(value) {
  const normalized = String(value || "1D").trim().toLowerCase();
  if (["day", "daily", "1d"].includes(normalized)) return "1D";
  if (["week", "weekly", "1w"].includes(normalized)) return "1W";
  if (["month", "monthly", "1m"].includes(normalized)) return "1M";
  return String(value || "1D").toUpperCase();
}

function AIAssistantContent({
  isOpen,
  setIsOpen,
  persistent = false,
  previewSectionsOnly = false,
  className = "",
  modal = false,
  dock = false,
  expanded = false,
  onToggleExpanded,
  onCommandComplete,
  queryValue,
  onQueryChange,
  autoFocusComposer = false,
  commandRequest = null,
  closeLabel = null,
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { selectedAsset: globalSymbol, assetStatus, setSelectedAsset } = useAsset();
  const { user } = useAuth();
  const router = useRouter();
  const watchlist = useWatchlist();
  const { showSnackbar } = useModal();
  const { t, locale } = useTranslation();

  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const messagesRef = useRef(messages);
  const [preferences, setPreferences] = useState({});
  const [activeState, setActiveState] = useState(null);
  const [finnDraft, setFinnDraft] = useState(null);
  const [executingAction, setExecutingAction] = useState(false);
  const [recentConversations, setRecentConversations] = useState([]);
  const [showComposerMenu, setShowComposerMenu] = useState(false);
  const [manualCommandRequest, setManualCommandRequest] = useState(null);
  const [showSessionMenu, setShowSessionMenu] = useState(false);
  const [chatAssetOverride, setChatAssetOverride] = useState(null);
  const [activeFinnSessionId, setActiveFinnSessionId] = useState(null);
  const [availableFinnSessions, setAvailableFinnSessions] = useState([]);

  const messagesEndRef = useRef(null);
  const scrollRef = useRef(null);
  const composerInputRef = useRef(null);
  const commandCenterRef = useRef(null);
  const handledContextRequestRef = useRef(null);
  const usedFeedRequestRef = useRef(null);
  const activeStreamIdRef = useRef(null);
  const pendingRunRef = useRef(null);
  const stopRequestedStreamIdRef = useRef(null);
  const profileTelemetryKeyRef = useRef("");
  const sharedSessionRestoreRef = useRef(false);
  const forceNewFinnConversationRef = useRef(false);
  const activeFinnSessionIdRef = useRef(null);
  const [feedDraftEdit, setFeedDraftEdit] = useState(null);
  const [consumedFeedNonce, setConsumedFeedNonce] = useState(null);
  useEffect(() => { messagesRef.current = messages; }, [messages]);
  const at = createAssistantTranslator(t);
  const isFeedHandoff = Boolean(
    commandRequest?.mode === "chat" && commandRequest?.context?.feed_item_id,
  );
  const activeQuery = resolveFeedDraftQuery(
    commandRequest, queryValue !== undefined ? queryValue : query,
    feedDraftEdit, consumedFeedNonce,
  );
  const updateQuery = onQueryChange || setQuery;
  const isSimpleFinnModal = modal || dock;
  const effectiveCommandRequest = manualCommandRequest || commandRequest;
  const isCommandSearchOpen = isSimpleFinnModal && ["asset", "indicator", "all"].includes(effectiveCommandRequest?.mode);
  const latestMessage = messages[messages.length - 1];
  const hasActiveFinnV2GuidedTurn = latestMessage?.role === "assistant"
    && latestMessage?.isComplete !== false
    && (isCollectingDraft(latestMessage) || isOpenClarification(latestMessage));
  const stashedComposerDraftRef = useRef(null);
  const updateVisibleQuery = (value) => {
    if (isFeedHandoff) setFeedDraftEdit({ nonce: commandRequest?.nonce, value });
    updateQuery(value);
  };
  const leaveCommandSearch = () => {
    setManualCommandRequest(null);
    onCommandComplete?.();
    updateVisibleQuery(stashedComposerDraftRef.current ?? "");
    stashedComposerDraftRef.current = null;
    composerInputRef.current?.focus();
  };
  const enterCommandSearch = (mode) => {
    stashedComposerDraftRef.current = activeQuery;
    updateVisibleQuery("");
    setShowComposerMenu(false);
    setManualCommandRequest({ mode, nonce: `menu:${Date.now()}` });
  };
  useLayoutEffect(() => {
    const input = composerInputRef.current;
    if (!input || !isOpen) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
  }, [activeQuery, isOpen]);
  const userScopedRecentConversationStorageKey = React.useMemo(
    () => scopedRecentConversationStorageKey(user?.id),
    [user?.id],
  );
  const readBrowserFinnConversation = () => (
    typeof window === "undefined" ? null : readActiveFinnConversation(window.sessionStorage, user?.id)
  );

  const composerMenuCopy = {
    asset: at("uiText.composerAsset"),
    indicator: at("uiText.composerIndicator"),
    placeholder: at("uiText.composerInstruction"),
    menu: at("uiText.composerMenu"),
  };

  const uiText = buildAssistantUiText(at);

  useEffect(() => {
    setPreferences({});
    setMessages([]);
    setActiveState(null);
    setFinnDraft(null);
    setRecentConversations([]);
    setActiveFinnSessionId(null);
    activeFinnSessionIdRef.current = null;
    setAvailableFinnSessions([]);
    setChatAssetOverride(null);
    handledContextRequestRef.current = null;
    sharedSessionRestoreRef.current = false;
  }, [user?.id]);

  useEffect(() => {
    const handleIndicatorModalCompleted = (event) => {
      const { indicator, assetSymbol, category, source } = event?.detail || {};
      if (source !== "finn") return;

      const label = String(indicator || "").toUpperCase();
      const symbol =
        normalizeScopedAssetSymbol(assetSymbol) ||
        normalizeScopedAssetSymbol(searchParams.get("symbol") || searchParams.get("asset")) ||
        normalizeScopedAssetSymbol(globalSymbol);
      if (!symbol) return;
      const categoryLabel = String(category || "technical").toLowerCase();

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: `${label} is toegevoegd aan ${symbol} ${categoryLabel.charAt(0).toUpperCase()}${categoryLabel.slice(1)}.`,
          intent: "indicator_configured",
          isComplete: true,
        },
      ]);

      emitFinnRefreshSignals();
    };

    window.addEventListener(INDICATOR_MODAL_COMPLETED_EVENT, handleIndicatorModalCompleted);
    return () => window.removeEventListener(INDICATOR_MODAL_COMPLETED_EVENT, handleIndicatorModalCompleted);
  }, [globalSymbol, searchParams]);

  useEffect(() => {
    if (!isOpen) return;
    trackAssistantEvent({
      event_name: "finn_overlay_opened",
      page: pathname || "/assistant",
      surface: "finn_overlay",
      asset: globalSymbol || null,
      user_id: user?.id || null,
      flow_type: "finn_overlay",
    });
    trackAssistantEvent({
      event_name: "screen_view",
      page: pathname || "/assistant",
      surface: "finn_overlay",
      asset: globalSymbol || null,
      user_id: user?.id || null,
      flow_type: "finn_overlay",
    });
  }, [isOpen, pathname, globalSymbol, user?.id]);

  const normalizeStreamingText = (text) => {
    if (!text || text.length < 8) return text;
    const evenLength = text.length - (text.length % 2);
    if (evenLength < 8) return text;
    let paired = 0;
    for (let i = 0; i < evenLength; i += 2) {
      if (text[i] === text[i + 1]) paired += 1;
    }
    const pairCount = evenLength / 2;
    if (paired / pairCount < 0.8) return text;
    let normalized = "";
    for (let i = 0; i < evenLength; i += 2) {
      normalized += text[i];
    }
    return normalized + (text.length % 2 ? text[text.length - 1] : "");
  };

  // 🧭 Onboarding Context
  useEffect(() => {
    if (!isOpen) return;
    setShowComposerMenu(false);
  }, [isOpen, pathname]);

  useEffect(() => {
    if (!isOpen || previewSectionsOnly || !autoFocusComposer) return;
    const frame = window.requestAnimationFrame(() => {
      composerInputRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [isOpen, previewSectionsOnly, autoFocusComposer]);

  const traderProfile = normalizeTraderProfilePreferences(preferences || {});
  const traderTypes = traderProfile.trader_types || [];
  const profileTimeframes = traderProfile.primary_timeframes || [];
  const profileAssetFocus = traderProfile.asset_focus || [];
  const profileGoals = traderProfile.investment_goals_list || [];
  const profileExperience = traderProfile.experience_levels || [];
  const profileRisk = traderProfile.risk_profiles || [];
  const hasTraderProfile = [
    traderTypes,
    profileTimeframes,
    profileAssetFocus,
    profileGoals,
    profileExperience,
    profileRisk,
  ].some((list) => Array.isArray(list) && list.length > 0);

  const traderTypeLabelMap = {
    investor: at("labels.traderTypes.investor"),
    dca_investor: at("labels.traderTypes.dca_investor"),
    swing_trader: at("labels.traderTypes.swing_trader"),
    day_trader: at("labels.traderTypes.day_trader"),
    scalper: at("labels.traderTypes.scalper"),
    hybrid: at("labels.traderTypes.hybrid"),
  };

  const riskLabelMap = {
    conservative: at("labels.risk.conservative"),
    balanced: at("labels.risk.balanced"),
    aggressive: at("labels.risk.aggressive"),
  };

  const assetFocusLabelMap = {
    bitcoin: at("labels.assetFocus.bitcoin"),
    crypto_general: at("labels.assetFocus.crypto_general"),
    stocks: at("labels.assetFocus.stocks"),
    etfs: at("labels.assetFocus.etfs"),
    forex: at("labels.assetFocus.forex"),
    commodities: at("labels.assetFocus.commodities"),
  };

  const buildTraderProfileUiSummary = () => {
    if (!hasTraderProfile) return "";
    const leadType = traderTypes.map((type) => traderTypeLabelMap[type]).filter(Boolean).slice(0, 2).join(" + ");
    const leadTimeframes = profileTimeframes.map((tf) => String(tf).toUpperCase()).slice(0, 2).join("/");
    const leadRisk = profileRisk.map((risk) => riskLabelMap[risk]).filter(Boolean)[0];
    const leadAsset = profileAssetFocus.map((asset) => assetFocusLabelMap[asset]).filter(Boolean)[0];
    return [leadType, leadTimeframes, leadRisk || leadAsset].filter(Boolean).join(" • ");
  };

  const profileSummaryLabel = buildTraderProfileUiSummary();

  // 🛰️ Active Entities Context (Phase 2 Sync)
  let activeSetup = null;
  let focusedBotId = null;
  let activeBot = null;

  try {
    const setupCtx = useActiveSetup();
    activeSetup = setupCtx?.activeSetup;
    focusedBotId = setupCtx?.focusedBotId;
  } catch (e) {
    console.warn("ActiveSetup context not ready:", e);
  }

  try {
    const botCtx = useActiveBot();
    activeBot = botCtx?.activeBot;
  } catch (e) {
    console.warn("ActiveBot context not ready:", e);
  }

  const getContext = () => {
    const botPage = pathname === "/bot";
    // Bot selection uses replaceState, so Next's searchParams can lag the
    // bot that is already open on screen. Read the visible URL at submission.
    const routeParams = botPage && typeof window !== "undefined"
      ? new URLSearchParams(window.location.search) : searchParams;
    const routeSymbol = normalizeScopedAssetSymbol(routeParams.get("symbol") || routeParams.get("asset"));
    const botContext = botPage ? resolveFinnBotPageContext({
      search: routeParams.toString(), activeBot, selectedAsset: globalSymbol,
    }) : null;
    const contextualBot = botPage ? botContext.bot : activeBot;
    const contextualSetup = botPage ? contextualBot?.strategy?.setup || null : activeSetup;
    const contextualStrategy = botPage ? contextualBot?.strategy || null : null;
    const resolvedWorkspaceSymbol = botPage ? botContext.symbol : resolveFinnContextSymbol({
      urlSymbol: routeSymbol,
      activeSetupSymbol: contextualSetup?.symbol,
      selectedAsset: globalSymbol,
    });

    const pageMap = {
      "/dashboard": t?.nav?.dashboard || "Dashboard",
      "/": t?.nav?.dashboard || "Dashboard",
      "/asset": t?.nav?.analysis || "Analysis",
      "/market": t?.nav?.market || "Market",
      "/macro": t?.nav?.macro || "Macro",
      "/technical": t?.nav?.technical || "Technical",
      "/setup": t?.nav?.setups || "Setups",
      "/strategy": t?.nav?.strategies || "Strategies",
      "/onboarding": t?.onboarding?.title || "Onboarding",
      "/bot": t?.nav?.bots || "Bots",
      "/report": t?.nav?.reports || "Reports",
    };

    return {
      page: pathname,
      locale,
      page_type: pageMap[pathname] || t?.common?.unknown || "Unknown",
      symbol: resolvedWorkspaceSymbol,
      asset_resolution_status: assetStatus,
      timeframe:
        searchParams.get("tf") ||
        searchParams.get("interval") ||
        (pathname.includes("dashboard") || pathname === "/"
          ? t?.common?.week || "Week"
          : t?.common?.day || "Day"),
      setup_id: getActiveSetupId(contextualSetup),
      setup_type: contextualSetup?.setup_type || contextualSetup?.type || null,
      setup_symbol: contextualSetup?.symbol || null,
      setup_timeframe: contextualSetup?.timeframe || null,
      bot_id: botPage ? botContext.botId : focusedBotId || null,
      strategy_id: contextualStrategy?.id || contextualSetup?.strategy_id || null,
      setup_name: botPage ? contextualSetup?.name || null : searchParams.get("name") || contextualSetup?.name || null,
      finn_draft: finnDraft,
    };
  };

  const context = getContext();
  useEffect(() => {
    setChatAssetOverride(null);
  }, [pathname, context.bot_id, context.symbol]);
  const currentConversationStorageKey = React.useMemo(() => {
    const userScope = String(user?.id || "anonymous");
    const section = String(context.page_type || pathname || "overview").toLowerCase();
    const asset = normalizeScopedAssetSymbol(context.symbol || globalSymbol) || "UNKNOWN";
    const timeframe = String(context.timeframe || "Day").toLowerCase();
    return `${userScope}:${section}:${asset}:${timeframe}`;
  }, [user?.id, context.page_type, context.symbol, context.timeframe, pathname, globalSymbol]);

  const getLatestAssistantState = () => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const state = messages[i]?.state;
      if (messages[i]?.role === "assistant" && state?.current_flow) {
        return state;
      }
    }
    return null;
  };

  const getFlowProgress = (state) => {
    if (!state || !state.current_flow || state.current_flow === "none") return null;

    const flowSlots = {
      user_onboarding: ["experience_level", "risk_profile", "investment_goals"],
      setup_creation: ["symbol", "setup_type", "timeframe", "market_condition"],
      strategy_creation: ["setup_id", "base_amount_eur", "execution_mode", "risk_profile"],
      bot_creation: ["name", "budget_total_eur", "budget_daily_limit_eur"],
      macro_analysis_walkthrough: ["symbol"],
      technical_analysis_walkthrough: ["symbol"],
      risk_check: ["symbol", "proposed_size"],
      navigate_to_page: ["target_page"]
    };

    const slots = flowSlots[state.current_flow] || [];
    if (slots.length === 0) return null;

    // Calculate filled slots (only filter keys that are defined in the active flow's slots list!)
    const filledSlots = slots.filter(k => state.slots && state.slots[k] !== undefined && state.slots[k] !== null && state.slots[k] !== "");

    // Determine effective total slots (taking conditional parameters into account)
    let totalSlots = slots.length;
    const setupType = state.slots?.setup_type;
    if (state.current_flow === "setup_creation" && setupType === "trade") {
      totalSlots = 4; // symbol, setup_type, timeframe, market_condition
    }
    if (state.current_flow === "setup_creation" && setupType === "dca") {
      totalSlots = 5; // symbol, setup_type, timeframe, dca_frequency, market_condition
    }
    if (state.current_flow === "strategy_creation" && setupType === "dca") {
      totalSlots = 4; // setup, amount, execution mode, risk profile
    }

    const percentage = Math.min(Math.round((filledSlots.length / totalSlots) * 100), 100);
    return {
      filled: filledSlots.length,
      total: totalSlots,
      percentage,
      flowLabel: state.current_flow.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")
    };
  };

  const parseSuggestedActions = (text) => {
    if (!text) return [];

    const headerRegex = /(?:Volgende stappen|Suggested actions|Proactieve volgacties):/i;
    const match = text.match(headerRegex);
    if (!match) return [];

    const headerIndex = match.index;
    const sectionText = text.substring(headerIndex + match[0].length);

    const lines = sectionText.split("\n");
    const suggestions = [];

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("-") || trimmed.startsWith("*")) {
        const label = trimmed.substring(1).trim();
        if (label) suggestions.push(label);
      } else if (/^\d+\./.test(trimmed)) {
        const label = trimmed.replace(/^\d+\./, "").trim();
        if (label) suggestions.push(label);
      } else if (trimmed.length > 0 && suggestions.length > 0) {
        break;
      }
    }
    return suggestions.slice(0, 4);
  };

  const stripSuggestedActionsSection = (text) => {
    if (!text) return text;

    const headerRegex = /(?:Volgende stappen|Suggested actions|Proactieve volgacties):/i;
    const match = text.match(headerRegex);
    if (!match || match.index === undefined) return text;

    return text.slice(0, match.index).trim();
  };

  function emitFinnRefreshSignals() {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("finn-refresh-requested"));
    }
    router.refresh();
  }

  useEffect(() => {
    const handleTrigger = (e) => {
      const {
        query: queryText,
        hiddenPrompt,
        openAssistant,
        metric,
        symbol,
        timeframe,
        assistantFlow,
        assistantSuppressRestore,
      } = e.detail || {};
      if (openAssistant) {
        setIsOpen(true);
      }
      if (metric) setIsOpen(true);
      if (assistantSuppressRestore && assistantFlow) {
        if (assistantFlow === "strategy_creation") {
          setFinnDraft(null);
          setActiveState(null);
          setMessages((prev) =>
            prev.filter(
              (message) =>
                message?.flow !== "strategy_creation" &&
                message?.intent !== "strategy_creation" &&
                !message?.restoredFinnDraft
            )
          );
        }
      }
      if (hiddenPrompt) {
        handleChat(hiddenPrompt, true);
        return;
      }
      if (queryText) {
        handleChat(queryText);
      }
    };

    window.addEventListener("finn-action-trigger", handleTrigger);
    return () => window.removeEventListener("finn-action-trigger", handleTrigger);
  }, [messages, handleChat]);

  useEffect(() => {
    if (isOpen && Object.keys(preferences).length === 0) {
      getAssistantPreferences().then(res => setPreferences(res.preferences || {}));
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || previewSectionsOnly || isFeedHandoff || sharedSessionRestoreRef.current) return;
    sharedSessionRestoreRef.current = true;

    (async () => {
      try {
        const prefResponse = await getAssistantPreferences();
        const nextPreferences = prefResponse?.preferences || {};
        setPreferences((current) => (Object.keys(current || {}).length ? current : nextPreferences));

        const browserSessionId = readBrowserFinnConversation();
        const preferredSessionId = normalizeFinnSessionId(nextPreferences?.[ACTIVE_FINN_SESSION_ID_KEY]);
        const sessions = await getFinnV2Conversations();
        setAvailableFinnSessions(Array.isArray(sessions) ? sessions : []);
        const latestSessionId = normalizeFinnSessionId(sessions?.[0]?.id);
        const candidates = [...new Set([browserSessionId, preferredSessionId, latestSessionId]
          .filter(isFinnV2ConversationId))];
        for (const candidateId of candidates) {
          try {
            const detail = await getFinnV2ConversationDetail(candidateId);
            activeFinnSessionIdRef.current = candidateId;
            setActiveFinnSessionId(candidateId);
            setMessages((current) => (current.length > 0 ? current : mapBackendSessionMessages(detail?.messages)));
            return;
          } catch (error) {
            console.warn("FINN-gesprek niet meer beschikbaar:", candidateId, error);
          }
        }
      } catch (error) {
        console.warn("Kon gedeelde FINN-sessie niet laden:", error);
      }
    })();
  }, [isOpen, previewSectionsOnly, isFeedHandoff]);

  const persistActiveFinnSessionId = async (sessionId) => {
    const normalized = normalizeFinnSessionId(sessionId);
    if (!isFinnV2ConversationId(normalized)) return;
    activeFinnSessionIdRef.current = normalized;
    setActiveFinnSessionId(normalized);
    if (typeof window !== "undefined") {
      writeActiveFinnConversation(window.sessionStorage, user?.id, normalized);
    }
    getFinnV2Conversations()
      .then((sessions) => setAvailableFinnSessions(Array.isArray(sessions) ? sessions : []))
      .catch((error) => console.warn("Kon FINN-gespreksgeschiedenis niet laden:", error));
    try {
      await updateAssistantPreferences({
        [ACTIVE_FINN_SESSION_ID_KEY]: normalized,
      });
    } catch (error) {
      console.warn("Kon actieve FINN-sessie niet bewaren:", error);
    }
  };

  const startNewFinnConversation = async () => {
    // Starting a fresh conversation abandons an unsubmitted feed selection.
    // A later unrelated question must not inherit that item's identity.
    usedFeedRequestRef.current = commandRequest?.nonce;
    setConsumedFeedNonce(commandRequest?.nonce);
    setFeedDraftEdit(null);
    updateQuery("");
    // State updates are asynchronous; this marker prevents an immediate send
    // from reusing the previous conversation id from the current render.
    forceNewFinnConversationRef.current = true;
    activeFinnSessionIdRef.current = null;
    setActiveFinnSessionId(null);
    if (typeof window !== "undefined") {
      clearActiveFinnConversation(window.sessionStorage, user?.id);
    }
    setFinnDraft(null);
    setActiveState(null);
    setMessages([]);
    try {
      await updateAssistantPreferences({
        [ACTIVE_FINN_SESSION_ID_KEY]: null,
      });
    } catch (error) {
      console.warn("Kon actieve FINN-sessie niet resetten:", error);
    }
  };

  const restoreFinnSession = async (sessionId) => {
    const normalized = normalizeFinnSessionId(sessionId);
    if (!isFinnV2ConversationId(normalized)) return;
    try {
      const detail = await getFinnV2ConversationDetail(normalized);
      await persistActiveFinnSessionId(normalized);
      setFinnDraft(null);
      setActiveState(null);
      setMessages(mapBackendSessionMessages(detail?.messages));
    } catch (error) {
      console.warn("Kon FINN-sessie niet herstellen:", error);
    }
  };

  const retireProposalCards = (proposalIds) => {
    if (!proposalIds.size) return;
    setMessages((prev) => retireFinnProposalCards(prev, proposalIds));
  };

  const refreshProposalCards = async ({ clarificationRequired = false } = {}) => {
    const proposalIds = [...new Set(messagesRef.current.flatMap((message) =>
      (message.actions || [])
        .filter((action) => action?.type === "v2_proposal" && action.proposal_id)
        .map((action) => action.proposal_id)
    ))];
    if (!proposalIds.length) return;
    const results = await Promise.allSettled(proposalIds.map(fetchFinnV2Proposal));
    retireProposalCards(inactiveProposalIds(proposalIds, results));
    const suspended = suspendedProposalIds(proposalIds, results, clarificationRequired);
    if (suspended.size) {
      setMessages((prev) => suspendFinnProposalCards(prev, suspended));
    }
  };

  async function pollPendingFinnV2Run(runId, streamId) {
    const terminalStatuses = new Set(["completed", "blocked", "failed", "canceled", "unavailable", "downgraded", "rejected", "clarification_required"]);
    const sseController = new AbortController();
    let sseTerminal = null;
    let sseFinished = false;
    void waitForFinnV2TerminalSse(runId, { signal: sseController.signal })
      .then((run) => { sseTerminal = run; })
      .catch((error) => {
        if (error?.name !== "AbortError") console.warn("FINN V2 SSE fallback naar polling:", error);
      })
      .finally(() => { sseFinished = true; });
    const completeTerminal = async (run) => {
      if (activeStreamIdRef.current !== streamId) return;
      if (["failed", "unavailable"].includes(String(run?.status || "").toLowerCase())) {
        // Keep diagnostics out of FINN's answer. A failed run can otherwise
        // look identical to client polling exhaustion in the visible chat.
        // Keep the typed failure visible in text-only browser log collectors.
        // This contains no user message or account data.
        console.warn(
          `FINN V2 terminal failure run_id=${runId} status=${run.status} error_code=${run.error_code || "none"}`
        );
      }
      const verified = run?.response;
      const projection = run?.runtime_trace?.terminal_projection || run?.runtime_trace || {};
      const setupDraft = projection?.setup_draft || null;
      const draftOperations = [
        "create_strategy", "create_bot",
        "watchlist_add", "watchlist_remove",
        "create_indicator_configuration", "update_indicator_configuration", "delete_indicator_configuration",
      ];
      const initialOperationId = projection?.initial_operation_id;
      const finalOperationId = projection?.final_operation_id;
      const operationId = draftOperations.includes(initialOperationId) ? initialOperationId : finalOperationId;
      const persistedActionDraft = projection?.action_draft || null;
      const actionDraft = persistedActionDraft || (draftOperations.includes(operationId)
        ? {
            operation_id: operationId,
            draft_status: verified?.proposal_id ? "complete" : "collecting",
            supplied_inputs: projection?.supplied_inputs || {},
            missing_inputs: projection?.missing_inputs || [],
            requested_slot: projection?.missing_inputs?.[0] || null,
            canonical_target: projection?.canonical_target || null,
        }
        : null);
      let resolvedSetupName = actionDraft?.supplied_inputs?.setup_name || activeSetup?.name || null;
      let resolvedSetupSymbol = null;
      let resolvedSetupTimeframe = null;
      let resolvedStrategyName = actionDraft?.supplied_inputs?.strategy_name || null;
      let verifiedBotStrategyName = null;
      let resolvedBotName = activeBot?.name || null;
      let immutableProposalState = null;
      try {
        if (operationId?.includes("setup") || operationId?.includes("strategy") || operationId?.includes("bot")) {
          const [ownerSetups, ownerStrategies, ownerBots, proposalSummary] = await Promise.all([
            fetchSetups(),
            fetchStrategies(),
            fetchBotConfigs(),
            verified?.proposal_id ? fetchFinnV2Proposal(verified.proposal_id) : Promise.resolve(null),
          ]);
          immutableProposalState = proposalSummary;
          const setupId = actionDraft?.supplied_inputs?.setup_id || projection?.supplied_inputs?.setup_id;
          const strategyId = actionDraft?.supplied_inputs?.strategy_id || projection?.supplied_inputs?.strategy_id;
          const botId = actionDraft?.supplied_inputs?.bot_id || projection?.supplied_inputs?.bot_id;
          const matchedBot = ownerBots.find((item) => Number(item.id || item.bot_id) === Number(botId));
          const linkedStrategyId = strategyId || matchedBot?.strategy_id;
          const verifiedBotStrategy = operationId === "create_bot" ? verifiedPaperBotStrategy({
            target: immutableProposalState?.target,
            draftStrategyId: strategyId,
            ownerStrategies,
          }) : null;
          const matchedStrategy = operationId === "create_bot"
            ? verifiedBotStrategy
            : ownerStrategies.find((item) => Number(item.id || item.strategy_id) === Number(linkedStrategyId));
          if (verifiedBotStrategy) verifiedBotStrategyName = verifiedBotStrategy.name || null;
          const linkedSetupId = setupId || matchedStrategy?.setup_id;
          const matchedSetup = ownerSetups.find((item) => Number(item.id || item.setup_id) === Number(linkedSetupId));
          resolvedSetupName = matchedSetup?.name
            || matchedStrategy?.setup_name
            || resolvedSetupName;
          resolvedSetupSymbol = matchedSetup?.symbol || matchedSetup?.asset || null;
          resolvedSetupTimeframe = matchedSetup?.timeframe || null;
          resolvedStrategyName = matchedStrategy?.name || resolvedStrategyName;
          resolvedBotName = matchedBot?.name || resolvedBotName;
        }
      } catch (error) {
        console.warn("FINN kon gekoppelde conceptnamen niet verversen:", error);
      }
      if (activeStreamIdRef.current !== streamId) return;
      const visibleActionDraft = actionDraft
        ? {
            ...actionDraft,
            supplied_inputs: {
              ...(actionDraft.supplied_inputs || {}),
              ...(resolvedSetupName ? { setup_name: resolvedSetupName } : {}),
              ...(resolvedSetupSymbol && !actionDraft?.supplied_inputs?.symbol ? { symbol: resolvedSetupSymbol } : {}),
              ...(resolvedSetupTimeframe && !actionDraft?.supplied_inputs?.timeframe ? { timeframe: resolvedSetupTimeframe } : {}),
              ...(operationId === "create_bot"
                ? { strategy_name: verifiedBotStrategyName }
                : resolvedStrategyName ? { strategy_name: resolvedStrategyName } : {}),
            },
          }
        : null;
      const terminalText = verified?.content || "Ik kan deze FINN V2-run nu niet veilig afronden.";
      const requiresNamedTargetReview = [
        "delete_setup", "delete_strategy", "delete_bot", "deactivate_bot",
        "activate_paper_bot", "activate_live_bot",
      ].includes(operationId);
      const reviewedTargetName = immutableProposalState?.review_target_name || null;
      setMessages((prev) => retireEarlierFinnProposalCards(
        prev, streamId, verified?.proposal_id,
      ).map((message) => (
        message.streamId === streamId
          ? {
              ...message,
              text: terminalText,
              intent: String(run?.mode || "unavailable").toLowerCase(),
              flow: run?.status === "completed" ? "finn_v2_visible" : "finn_v2_visible_terminal_failed",
              state: {
                ...(message.state || {}),
                current_flow: run?.status === "completed" ? "finn_v2_visible" : "finn_v2_visible_terminal_failed",
                run_id: runId,
                run_status: run?.status,
                clarification: projection?.clarification || null,
                setup_draft: setupDraft,
                action_draft: visibleActionDraft,
              },
              setupDraft,
              actionDraft: visibleActionDraft,
              reasoning: null,
              canConfirm: Boolean(verified?.confirmation_required && verified?.proposal_id
                && (operationId !== "create_bot" || verifiedBotStrategyName)
                && (!requiresNamedTargetReview || reviewedTargetName)),
              confirmationSuspended: Boolean(verified?.proposal_id && (
                (operationId === "create_bot" && !verifiedBotStrategyName)
                || (requiresNamedTargetReview && !reviewedTargetName)
              )),
              actions: verified?.proposal_id ? [{
                type: "v2_proposal",
                proposal_id: verified.proposal_id,
                requires_confirmation: Boolean(verified.confirmation_required),
                mode: verified.mode,
                display_context: {
                  // Confirmation runs outside the chat stream. Preserve the
                  // server-issued conversation so the next demonstrative turn
                  // starts from the verified action-result boundary.
                  conversation_id: projection?.conversation_id || run?.conversation_id || null,
                  run_id: runId,
                  operation_id: operationId || projection?.final_operation_id,
                  review_target_name: reviewedTargetName,
                  name: actionDraft?.supplied_inputs?.name
                    || setupDraft?.supplied_inputs?.name
                    || projection?.action_result?.canonical_name
                    || (operationId?.includes("setup") ? resolvedSetupName : null)
                    || (operationId?.includes("strategy") ? resolvedStrategyName : null)
                    || (operationId?.includes("bot") ? resolvedBotName : null)
                    || null,
                  symbol: actionDraft?.supplied_inputs?.symbol || setupDraft?.supplied_inputs?.symbol || projection?.canonical_target || activeSetup?.symbol || null,
                  timeframe: actionDraft?.supplied_inputs?.timeframe || setupDraft?.supplied_inputs?.timeframe || null,
                  setup_name: resolvedSetupName,
                  strategy_name: operationId === "create_bot" ? verifiedBotStrategyName : resolvedStrategyName,
                  supplied_inputs: projection?.supplied_inputs || {},
                  before_state: immutableProposalState?.before_state || {},
                  requested_state: immutableProposalState?.requested_state || projection?.supplied_inputs?.changed_fields || {},
                  target_revision: immutableProposalState?.target_revision || null,
                  snapshot_timestamp: immutableProposalState?.snapshot_timestamp || null,
                  changed_fields: immutableProposalState?.requested_state || projection?.supplied_inputs?.changed_fields || {},
                  safety_mode: operationId === "create_bot" ? "Paper · niet-live" : null,
                },
              }] : [],
              isComplete: true,
            }
          : message
      )));
      await refreshProposalCards({ clarificationRequired: run?.status === "clarification_required" });
      if (activeStreamIdRef.current === streamId) {
        activeStreamIdRef.current = null;
        if (pendingRunRef.current?.streamId === streamId) pendingRunRef.current = null;
        setLoading(false);
      }
    };
    for (let attempt = 0; attempt < 60; attempt += 1) {
      if (activeStreamIdRef.current !== streamId) {
        sseController.abort();
        return;
      }
      if (sseTerminal) {
        await completeTerminal(sseTerminal);
        return;
      }
      try {
        const run = await fetchFinnV2Run(runId);
        if (activeStreamIdRef.current !== streamId) {
          sseController.abort();
          return;
        }
        if (!terminalStatuses.has(String(run?.status || "").toLowerCase())) {
          const delayMs = Math.min(1000 + attempt * 250, 3000);
          await new Promise((resolve) => window.setTimeout(resolve, delayMs));
          continue;
        }

        await completeTerminal(run);
        sseController.abort();
        return;
      } catch (error) {
        if (attempt === 59) {
          console.warn("FINN V2 pending run kon niet worden opgehaald:", error);
        }
      }
      // Keep pending delivery responsive without continuously hammering the run endpoint.
      if (sseFinished && !sseTerminal && attempt === 59) {
        console.warn("FINN V2 SSE sloot zonder terminale projectie; polling bleef de fallback.");
      }
      const delayMs = Math.min(250 + attempt * 50, 1000);
      await new Promise((resolve) => window.setTimeout(resolve, delayMs));
    }
    sseController.abort();
    if (activeStreamIdRef.current === streamId) {
      console.warn("FINN V2 terminal polling exhausted", { run_id: runId });
      await refreshProposalCards();
      setMessages((prev) => prev.map((message) => message.streamId === streamId
        ? { ...message, text: "FINN kon dit antwoord niet afronden. Probeer het opnieuw.", isError: true, isComplete: true }
        : message));
      activeStreamIdRef.current = null;
      if (pendingRunRef.current?.streamId === streamId) pendingRunRef.current = null;
      setLoading(false);
    }
  }

  const stopCurrentResponse = async () => {
    const streamId = activeStreamIdRef.current;
    const pendingRunId = (!streamId || pendingRunRef.current?.streamId === streamId)
      ? pendingRunRef.current?.runId : null;
    if (streamId && !pendingRunId) {
      // The request may already be creating a server run. Keep the stream
      // alive until its envelope gives us the id needed to cancel that run.
      if (stopRequestedStreamIdRef.current === streamId) return;
      stopRequestedStreamIdRef.current = streamId;
      setMessages((current) => current.map((message) => message.streamId === streamId
        ? { ...message, text: at("uiText.stoppingResponse"), isComplete: false }
        : message));
      return;
    }
    stopRequestedStreamIdRef.current = null;
    activeStreamIdRef.current = null;
    abortAssistantChatStream();
    if (streamId) {
      setMessages((current) => current.map((message) => message.streamId === streamId
        ? { ...message, text: at("uiText.stoppingResponse"), isComplete: false, actions: [], draft: null }
        : message));
    }
    if (pendingRunId) {
      let recordedRun = null;
      try {
        const canceled = await cancelFinnV2Run(pendingRunId);
        recordedRun = canceled?.run || null;
      } catch {
        // The worker may have finalized before Stop reached the server.
        // Read that terminal result instead of showing a local-only stop.
        try { recordedRun = await fetchFinnV2Run(pendingRunId); } catch {}
      }
      if (recordedRun && !["completed", "blocked", "failed", "canceled", "unavailable", "downgraded", "rejected", "clarification_required"]
        .includes(recordedRun.status)) {
        // The terminal contract can win before the worker's run row is
        // visible in a separate transaction. Keep showing "stopping" until
        // the authoritative terminal projection arrives.
        try {
          recordedRun = await waitForFinnV2TerminalSse(pendingRunId, {
            signal: AbortSignal.timeout(8000),
          });
        } catch {
          try { recordedRun = await fetchFinnV2Run(pendingRunId); } catch {}
        }
      }
      const savedText = recordedRun?.response?.content;
      const terminal = ["completed", "blocked", "failed", "canceled", "unavailable", "downgraded", "rejected", "clarification_required"]
        .includes(recordedRun?.status);
      if (streamId) setMessages((current) => current.map((message) => message.streamId === streamId
        ? {
            ...message,
            text: terminal && typeof savedText === "string" && savedText.trim()
              ? savedText : at("uiText.stopStatusUnknown"),
            isComplete: true,
            isStopped: recordedRun?.status === "canceled",
            isError: !terminal || ["failed", "unavailable", "rejected"].includes(recordedRun?.status),
            actions: [],
            draft: null,
          }
        : message));
    }
    if (!streamId || pendingRunRef.current?.streamId === streamId) pendingRunRef.current = null;
    if (!activeStreamIdRef.current) setLoading(false);
  };

  async function handleChat(directQuery, isSilent = false, overrideContext = null, retryMessageIndex = null) {
    if (loading || activeStreamIdRef.current) return;
    const nextQuery = directQuery !== undefined ? directQuery : activeQuery;
    if (!nextQuery.trim()) return;
    if (shouldBlockFinnSubmission({ isAuthenticated: Boolean(user?.id), assetStatus })) {
      showSnackbar("FINN wacht nog op je accountcontext. Probeer het zo opnieuw.", "warning");
      return;
    }

    setLoading(true);
    if (retryMessageIndex !== null) {
      setMessages((current) => current.filter((_, index) => index !== retryMessageIndex && index !== retryMessageIndex - 1));
    }
    if (isFinnProposalCorrection(nextQuery)) {
      const openIds = new Set(messagesRef.current.flatMap((message) =>
        (message.actions || [])
          .filter((action) => action?.type === "v2_proposal" && action.proposal_id)
          .map((action) => action.proposal_id)
      ));
      if (openIds.size) setMessages((prev) => suspendFinnProposalCards(prev, openIds));
    }
    if (!isSilent) {
      if (isFeedHandoff) setConsumedFeedNonce(commandRequest?.nonce);
      updateQuery("");
    }

    if (!isSilent) {
      setMessages(prev => [...prev, { role: "user", text: nextQuery }]);
    }

    const streamId = `stream-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    stopRequestedStreamIdRef.current = null;
    activeStreamIdRef.current = streamId;

    // Append initial empty assistant bubble
    setMessages(prev => [...prev, {
      role: "assistant",
      text: "",
      isComplete: false,
      streamId,
      retryQuery: nextQuery,
    }]);

    try {
      const cleanHistory = [
        ...messages.filter((m, index) => index !== retryMessageIndex && index !== retryMessageIndex - 1 && !m.isError && !m.isStopped && m.text?.trim()).map(m => ({ role: m.role, text: m.text })),
        { role: "user", text: nextQuery }
      ];

      const latestAssistantState = overrideContext || activeState || getLatestAssistantState();
      const baseRequestContext = latestAssistantState?.current_flow
        ? { ...context, ...latestAssistantState }
        : context;
      const commandContext = { ...(commandRequest?.context || {}) };
      if (commandContext.feed_item_id) {
        const attachFeed = shouldAttachFeedContext(
          commandRequest, nextQuery, usedFeedRequestRef.current,
        );
        usedFeedRequestRef.current = commandRequest?.nonce;
        if (!attachFeed) delete commandContext.feed_item_id;
      }
      // The language selector updates <html lang> synchronously. Read it at
      // submission so a just-switched UI cannot send a stale render locale.
      const submissionLocale = finnSubmissionLocale(
        locale, typeof document === "undefined" ? null : document.documentElement.lang,
      );
      const requestContext = { ...baseRequestContext, ...commandContext, locale: submissionLocale,
        symbol: pathname === "/bot" && baseRequestContext.bot_id
          ? baseRequestContext.symbol
          : chatAssetOverride || commandContext.symbol || baseRequestContext.symbol };
      if (pathname === "/bot" && context.bot_id) {
        requestContext.bot_id = context.bot_id;
        requestContext.symbol = context.symbol;
        requestContext.setup_id = context.setup_id;
        requestContext.strategy_id = context.strategy_id;
      }
      const analyticsSessionId = getAssistantSessionId(user?.id || "anonymous");
      const chatSessionId = forceNewFinnConversationRef.current
        ? "new"
        : activeFinnSessionIdRef.current || activeFinnSessionId || readBrowserFinnConversation() || "new";
      forceNewFinnConversationRef.current = false;

      await assistantChatStream(
        nextQuery,
        requestContext,
        cleanHistory,
        (token) => {
          // onChunk
          if (activeStreamIdRef.current !== streamId || stopRequestedStreamIdRef.current === streamId) return;
          setMessages(prev => {
            const copy = [...prev];
            const msgIndex = copy.findIndex(message => message.streamId === streamId);
            if (msgIndex >= 0 && copy[msgIndex].role === "assistant" && copy[msgIndex].isComplete === false) {
              copy[msgIndex] = {
                ...copy[msgIndex],
                text: normalizeStreamingText(`${copy[msgIndex].text || ""}${token || ""}`),
              };
            }
            return copy;
          });
        },
        async (envelope) => {
          // onEnvelope
          if (activeStreamIdRef.current !== streamId) return;
          await persistActiveFinnSessionId(envelope?.session_id || chatSessionId);
          if (activeStreamIdRef.current !== streamId) return;
          const pendingRunId = envelope?.state?.run_id || envelope?.response_trace?.run_id;
          if (stopRequestedStreamIdRef.current === streamId) {
            stopRequestedStreamIdRef.current = null;
            if (pendingRunId) {
              pendingRunRef.current = { streamId, runId: pendingRunId };
              await stopCurrentResponse();
              return;
            }
            // A legacy response finished before it exposed a cancellable run.
            // Show its actual answer below instead of claiming it was stopped.
          }
          if (envelope?.state?.current_flow === "finn_v2_visible_pending" && pendingRunId) {
            pendingRunRef.current = { streamId, runId: pendingRunId };
            setMessages(prev => prev.map((message) => (
              message.streamId === streamId
                ? {
                    ...message,
                    text: at("draftCards.checking", "Even controleren…"),
                    intent: envelope.intent,
                    flow: envelope.flow,
                    state: envelope.state,
                    isComplete: false,
                  }
                : message
            )));
            void pollPendingFinnV2Run(pendingRunId, streamId);
            return;
          }
          const originalResponse = envelope?.response || "";
          const sanitizedResponse = stripSuggestedActionsSection(originalResponse);
          const indicatorModalRequest = buildIndicatorModalRequest(envelope, requestContext?.symbol || globalSymbol || "BTC");
          const extractedSuggestedActions =
            Array.isArray(envelope?.suggested_actions) && envelope.suggested_actions.length > 0
              ? envelope.suggested_actions
              : parseSuggestedActions(originalResponse);
          const latestProposalId = (Array.isArray(envelope?.actions) ? envelope.actions : [])
            .find((action) => action?.type === "v2_proposal")?.proposal_id;
          setMessages(prev => {
            const copy = [...retireEarlierFinnProposalCards(prev, streamId, latestProposalId)];
            const msgIndex = copy.findIndex(message => message.streamId === streamId);
            if (msgIndex >= 0 && copy[msgIndex].role === "assistant") {
              copy[msgIndex] = {
                ...copy[msgIndex],
                text: indicatorModalRequest?.responseText || sanitizedResponse,
                intent: envelope.intent,
                flow: envelope.flow,
                action: indicatorModalRequest ? null : envelope.action,
                draft: indicatorModalRequest ? null : envelope.draft,
                actions: indicatorModalRequest
                  ? []
                  : Array.isArray(envelope.actions)
                    ? envelope.actions
                    : envelope.action
                      ? [envelope.action]
                      : [],
                missingFields: indicatorModalRequest ? [] : (envelope.missing_fields || []),
                invalidFields: indicatorModalRequest ? [] : (envelope.invalid_fields || []),
                nextQuestion: indicatorModalRequest ? null : (envelope.next_question || null),
                canConfirm: indicatorModalRequest ? false : envelope.can_confirm,
                suggestedActions: indicatorModalRequest ? [] : extractedSuggestedActions,
                reviewLinks: indicatorModalRequest ? [] : (Array.isArray(envelope.review_links) ? envelope.review_links : []),
                reasoning: envelope.reasoning,
                state: indicatorModalRequest ? null : (envelope.state || null),
                summary: envelope.summary || null,
                riskSummary: envelope.risk_summary || null,
                nextBestAction: envelope.next_best_action || null,
                reviewReason: envelope.review_reason || null,
                isError: envelope?.state?.current_flow === "finn_v2_visible_failed" || envelope?.intent === "unavailable",
                isComplete: true,
              };
            }
            return copy;
          });
          try {
            await refreshProposalCards();
          } finally {
            if (activeStreamIdRef.current === streamId) {
              activeStreamIdRef.current = null;
              setLoading(false);
            }
          }

          if (indicatorModalRequest && typeof window !== "undefined") {
            window.dispatchEvent(
              new CustomEvent(INDICATOR_MODAL_OPEN_EVENT, {
                detail: {
                  category: indicatorModalRequest.category,
                  indicatorName: indicatorModalRequest.indicatorName,
                  title: indicatorModalRequest.title,
                  source: "finn",
                },
              })
            );
          }

          if (envelope?.flow === "decision_review" || envelope?.intent === "decision_review") {
            trackAssistantEvent({
              event_name: "decision_review_used",
              session_id: analyticsSessionId,
              page: pathname || "/assistant",
              surface: "finn_overlay",
              asset: requestContext?.symbol || globalSymbol || null,
              flow_type: "decision_review",
            });
          }
          if (envelope?.flow === "priority_engine" || envelope?.intent === "priority_engine") {
            trackAssistantEvent({
              event_name: "priority_engine_used",
              session_id: analyticsSessionId,
              page: pathname || "/assistant",
              surface: "finn_overlay",
              asset: requestContext?.symbol || globalSymbol || null,
              flow_type: "priority_engine",
            });
          }

          const transactionalFlows = ["plan_creation", "strategy_creation", "bot_creation", "indicator_config"];
          const legacyTransactionalFlows = ["setup_creation"];

          if (["plan_creation_cancelled", "strategy_creation_cancelled", "bot_creation_cancelled", "indicator_config_cancelled"].includes(envelope.intent)) {
            setFinnDraft(null);
            setActiveState(null);
          } else if (indicatorModalRequest) {
            setFinnDraft(null);
            setActiveState(null);
          } else if (transactionalFlows.includes(envelope.flow)) {
            setFinnDraft(envelope.draft || null);
          } else if (
            legacyTransactionalFlows.includes(envelope?.state?.current_flow) ||
            legacyTransactionalFlows.includes(envelope.flow) ||
            !envelope?.draft
          ) {
            // Prevent old modern drafts from visually "sticking" under a new legacy setup conversation.
            setFinnDraft(null);
          }

          if (
            envelope.state &&
            envelope.state.current_flow !== "none" &&
            (
              envelope.state.status === "collecting" ||
              envelope.state.pending_behavioral_memory_friction ||
              envelope.next_question === "behavioral_memory_ack"
            )
          ) {
            setActiveState({ ...envelope.state, can_confirm: envelope.can_confirm });
          } else {
            setActiveState(null);
          }
        },
        (errorMessage) => {
          // onError
          if (activeStreamIdRef.current !== streamId) return;
          if (stopRequestedStreamIdRef.current === streamId) stopRequestedStreamIdRef.current = null;
          setMessages(prev => {
            const copy = [...prev];
            const msgIndex = copy.findIndex(message => message.streamId === streamId);
            if (msgIndex >= 0 && copy[msgIndex].role === "assistant") {
              copy[msgIndex] = {
                ...copy[msgIndex],
                text: "⚠️ " + errorMessage,
                isError: true,
                isComplete: true,
              };
            }
            return copy;
          });
          activeStreamIdRef.current = null;
        },
        2,
        chatSessionId,
      );
    } catch (err) {
      if (activeStreamIdRef.current !== streamId) return;
      setMessages(prev => {
        const copy = [...prev];
        const msgIndex = copy.findIndex(message => message.streamId === streamId);
        if (msgIndex >= 0 && copy[msgIndex].role === "assistant") {
          copy[msgIndex] = {
            ...copy[msgIndex],
            text: "⚠️ Analyse ophalen mislukt. Probeer het opnieuw.",
            isError: true,
            isComplete: true,
          };
        }
        return copy;
      });
      activeStreamIdRef.current = null;
    } finally {
      if (stopRequestedStreamIdRef.current === streamId && activeStreamIdRef.current === streamId) {
        stopRequestedStreamIdRef.current = null;
        setMessages((current) => current.map((message) => message.streamId === streamId
          ? { ...message, text: at("uiText.stopStatusUnknown"), isComplete: true, isError: true }
          : message));
        activeStreamIdRef.current = null;
      }
      if (activeStreamIdRef.current === null) {
        setLoading(false);
      }
    }
  };

  const handleCancelDraft = async (index) => {
    const message = messages[index];
    const proposalId = (message?.actions || []).find((action) => action?.type === "v2_proposal")?.proposal_id;
    setExecutingAction(true);
    try {
      if (proposalId) await cancelFinnV2Proposal(proposalId);
      setMessages(prev => prev.map((m, idx) => {
        const messageProposalId = (m?.actions || []).find((action) => action?.type === "v2_proposal")?.proposal_id;
        if (idx !== index && (!proposalId || messageProposalId !== proposalId)) return m;
        return {
        ...m,
        text: at("draftCards.cancelledResponse", "Voorstel geannuleerd. Er is niets gewijzigd."),
        actions: [],
        setupDraft: null,
        actionDraft: null,
        state: { ...(m.state || {}), setup_draft: null, action_draft: null },
        draftCanceled: true,
        };
      }));
      showSnackbar(at("draftCards.cancelledToast", "Voorstel geannuleerd"), "info");
    } catch (error) {
      showSnackbar(at("draftCards.cancelFailed", "Dit voorstel kon niet worden geannuleerd."), "error");
    } finally {
      setExecutingAction(false);
    }
  };

  const handleExecuteAction = async (action) => {
    if (!action) return;
    setExecutingAction(true);

    try {
      if (action.type === "v2_proposal") {
        const latestProposal = await fetchFinnV2Proposal(action.proposal_id);
        if (!["draft", "pending_confirmation"].includes(latestProposal?.status)) {
          retireProposalCards(new Set([action.proposal_id]));
          showSnackbar("Dit voorstel is niet meer bevestigbaar.", "info");
          return;
        }
        const reviewedName = action.display_context?.review_target_name;
        if (reviewedName && latestProposal.review_target_name !== reviewedName) {
          retireProposalCards(new Set([action.proposal_id]));
          showSnackbar("Dit voorstel verwijst niet meer naar dezelfde naam. Vraag FINN om een nieuw voorstel.", "info");
          return;
        }
        const result = await confirmAndExecuteFinnV2Proposal(
          action.proposal_id, reviewedName || latestProposal.review_target_name,
        );
        const execution = result?.execution || {};
        if (!["succeeded", "already_executed"].includes(execution.status)) {
          throw new Error(publicFinnExecutionError(execution.error_codes?.[0]));
        }
        const displayContext = action.display_context || {};
        // Execution is the authoritative post-confirmation boundary. A card
        // can have been rendered from a delayed stream projection, whereas
        // the execution response is bound to the proposal's actual run.
        let confirmedConversationId = normalizeFinnSessionId(
          execution.conversation_id || displayContext.conversation_id,
        );
        if (!isFinnV2ConversationId(confirmedConversationId) && displayContext.run_id) {
          // The execution endpoint normally returns this identity. Re-read
          // its committed run if an older delivery envelope omitted it.
          try {
            const confirmedRun = await fetchFinnV2Run(displayContext.run_id);
            confirmedConversationId = normalizeFinnSessionId(
              confirmedRun?.conversation_id
              || confirmedRun?.runtime_trace?.conversation_id
              || confirmedRun?.runtime_trace?.terminal_projection?.conversation_id,
            );
          } catch (error) {
            console.warn("Kon bevestigde FINN-conversatie niet opnieuw laden:", error);
          }
        }
        if (isFinnV2ConversationId(confirmedConversationId)) {
          // Do not rely on an earlier stream envelope after a confirmation:
          // bind the composer to the conversation that owns this execution.
          await persistActiveFinnSessionId(confirmedConversationId);
        }
        const operationId = displayContext.operation_id || execution.operation_id || "";
        const suppliedInputs = displayContext.supplied_inputs || {};
        const canonicalEntity = execution.action_result?.canonical_entity || {};
        const operationLabel = operationId.includes("bot") ? "Paper-bot" : operationId.includes("strategy") ? "Strategie" : operationId.includes("setup") ? "Setup" : operationId.includes("indicator_configuration") ? "Indicator" : operationId.startsWith("watchlist_") ? "Watchlist" : "Actie";
        const resultName = execution.action_result?.canonical_name
          || canonicalEntity.name
          || suppliedInputs.name
          || displayContext.name
          || `Je ${operationLabel.toLowerCase()}`;
        const resultVerb = operationId.startsWith("delete_") ? "verwijderd" : operationId.startsWith("update_") || operationId === "deactivate_bot" ? "bijgewerkt" : "opgeslagen";
        const categoryLabel = ({ technical: "Technisch bewijs", macro: "Macro", market: "Marktindicatoren" })[suppliedInputs.category] || suppliedInputs.category;
        const analysisResultText = operationId.startsWith("watchlist_")
          ? `${suppliedInputs.asset || execution.action_result?.canonical_name || "De asset"} is ${operationId === "watchlist_remove" ? "uit je watchlist verwijderd" : "aan je watchlist toegevoegd"}.`
          : operationId.includes("indicator_configuration")
            ? `${indicatorDisplayName(suppliedInputs.indicator || execution.action_result?.canonical_name)} is ${operationId.startsWith("delete_") ? "verwijderd uit" : operationId.startsWith("update_") ? "bijgewerkt in" : "toegevoegd aan"} ${categoryLabel || "je analyse"}${suppliedInputs.asset ? ` voor ${suppliedInputs.asset}` : ""}.`
            : null;
        const terminalText = analysisResultText || (execution.status === "already_executed"
          ? `${operationLabel} ‘${resultName}’ was al ${resultVerb}.`
          : `${operationLabel} ‘${resultName}’ is ${resultVerb}.`);
        setMessages((prev) => prev.map((message) => {
          const ownsProposal = (message.actions || []).some((candidate) => candidate?.proposal_id === action.proposal_id);
          if (!ownsProposal) return message;
          return {
            ...message,
            text: terminalText,
            intent: "finn_v2_proposal_execution",
            isComplete: true,
            actions: [],
            setupDraft: null,
            actionDraft: null,
            state: { ...(message.state || {}), setup_draft: null, action_draft: null },
          };
        }));
        emitFinnRefreshSignals();
        return;
      }
      throw new Error("Dit oudere actievoorstel kan niet meer worden bevestigd. Vraag FINN om een nieuw voorstel.");
    } catch (err) {
      console.error("Finn action failed", err);
      setMessages(prev => [...prev, {
        role: "assistant",
        text: action.type === "v2_proposal"
          ? publicFinnExecutionError(err?.message)
          : action.type === "refresh_daily_scores"
          ? "Ik kon de daily scores nog niet verversen. Probeer het zo opnieuw."
          : action.type === "generate_bot_decision"
          ? "Ik kon de bot-decision nog niet genereren. Controleer de bot en probeer opnieuw."
          : ["skip_bot_decision", "paper_execute_bot_decision", "live_preflight_bot_decision"].includes(action.type)
          ? "Ik kon deze bot-decision actie nog niet veilig afronden. Controleer de status en probeer opnieuw."
          : "Ik kon dit plan nog niet aanmaken. Controleer de velden en probeer opnieuw.",
        isError: true,
      }]);
    } finally {
      setExecutingAction(false);
    }
  };

  const draftActionButtons = (message, messageIndex, noun) => {
    const proposal = (message.actions || []).find((action) => action?.type === "v2_proposal");
    if (!proposal) {
      return (
        <button type="button" onClick={() => commandCenterRef.current?.focus?.()} className={actionButtonStyles({ variant: "primary", className: "justify-center rounded-xl px-4 py-2.5 text-xs" })}>
          {at("draftCards.continue", "Verder invullen")}
        </button>
      );
    }
    return (
      <>
        <button type="button" onClick={() => void handleExecuteAction(proposal)} disabled={loading || executingAction || message.confirmationSuspended} className={actionButtonStyles({ variant: "primary", className: "min-w-[120px] justify-center rounded-xl px-4 py-2.5 text-xs" })}>
          {executingAction ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />} {at("draftCards.confirm", "Bevestigen")}
        </button>
        <button type="button" onClick={() => {
          const question = at("draftCards.adjustQuestion", "Wat wil je in dit voorstel wijzigen?");
          setMessages(prev => prev.at(-1)?.text === question ? prev : [...prev, {
            role: "assistant", text: question, state: message.state, isComplete: true,
          }]);
          composerInputRef.current?.focus?.();
        }} disabled={loading || executingAction} className="rounded-xl px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-900">{at("draftCards.adjust", "Aanpassen")}</button>
        <button type="button" onClick={() => void handleCancelDraft(messageIndex)} disabled={executingAction} className="rounded-xl px-3 py-2 text-xs font-semibold text-slate-400 hover:text-slate-700 dark:hover:text-slate-200">{at("draftCards.cancel", "Annuleren")}</button>
      </>
    );
  };

  const waivedDraftRules = (messageIndex, operationId) => {
    const turns = messages.slice(0, messageIndex).filter((item) => item.role === "user");
    const normalized = (item) => String(item?.text || "").trim().toLowerCase().replace(/[.!\s]+$/, "");
    const waiverPattern = operationId === "create_setup"
      ? /^(?:maak voorstel zonder deze voorwaarden|begin nieuw voorstel zonder eerdere voorwaarden|make proposal without these conditions|start new proposal without previous conditions|vorschlag ohne diese bedingungen erstellen|neuen vorschlag ohne vorherige bedingungen beginnen|(?:ja,?\s+)?(?:laat|schrap|verwijder)\s+(?:die|deze|beide|alle)\s+(?:voorwaarden|handelsvoorwaarden|regels)\s+(?:maar\s+)?weg)$/
      : /^(?:maak strategievoorstel zonder deze automatische regels(?:[.;]\s*(?:laat (?:alleen )?.+\sweg(?:[.;]\s*.*)?|ik geef expliciet toestemming om alleen de stijgende 1d-trendvoorwaarde en de limiet van \w+ trades per dag weg te laten[.;]\s*behoud de eerder opgegeven vaste prijzen, naam, basisbedrag en risicostijl[.;]\s*dit is geen koopopdracht))?|begin nieuw strategievoorstel zonder eerdere regels|make strategy proposal without these automatic rules|start new strategy proposal without previous rules|strategieentwurf ohne diese automatischen regeln erstellen|neuen strategieentwurf ohne vorherige regeln beginnen)$/;
    const waiverIndex = turns.findLastIndex((item) => waiverPattern.test(normalized(item)));
    if (waiverIndex < 0) return null;
    const freshRequest = operationId === "create_setup"
      ? /^\s*(?:maak|create|erstelle)\b.+\b(?:nieuwe?|new)\b.+\b(?:setup|plan)\b/i
      : /^\s*(?:maak|create|erstelle)\b.+\b(?:nieuwe?|new)\b.+\b(?:strategie|strategy)\b/i;
    if (turns.slice(waiverIndex + 1).some((item) => freshRequest.test(String(item.text || "")))) return null;
    const original = turns.slice(0, waiverIndex).reverse().find((item) => /(?:extra voorwaarden|extra regels|additional conditions|additional rules)\s*:|ik wil daarnaast alleen handelen bij/i.test(String(item.text || "")));
    const omitted = String(original?.text || "").match(/(?:(?:extra voorwaarden|extra regels|additional conditions|additional rules)\s*:|ik wil daarnaast alleen handelen bij)\s*([^.!?\n]+)/i)?.[1]?.trim().replace(/\s+en\s+maximaal\s+/i, "; maximaal ");
    return omitted || true;
  };

  const renderV2SetupDraftCard = (message, messageIndex) => {
    if (message?.draftCanceled || message?.draftExecuted) return null;
    const draft = message.setupDraft || message.state?.setup_draft;
    if (!draft || draft.operation_id !== "create_setup") return null;
    if (!hasConfirmableDraft(message)) return null;
    const supplied = draft.supplied_inputs || {};
    const humanValue = (value) => {
      if (typeof value !== "string" && typeof value !== "number") return null;
      const normalized = String(value).trim();
      return normalized ? at(`valueLabels.${normalized.toLowerCase()}`, normalized) : null;
    };
    const contextLine = [supplied.symbol, supplied.timeframe, humanValue(supplied.setup_type)].filter(Boolean).join(" · ");
    const frequency = setupDraftFrequencyLabel(supplied, humanValue);
    const labels = { name: "naam", setup_type: "type", symbol: "asset", timeframe: "timeframe", dca_frequency: "frequentie", dca_day: "weekdag", dca_month_day: "dag van de maand", min_investment: "minimuminvestering", dca_amount_mode: "bedragregel", base_amount: "basisbedrag", score_source: "totale benchmark (markt + macro + technisch)", low_threshold: "grens lage/middenscore", high_threshold: "grens midden/hoge score", low_score_percent: "percentage lage score", mid_score_percent: "percentage middenscore", high_score_percent: "percentage hoge score" };
    const missing = (draft.missing_inputs || []).map((field) => at(`draftCards.inputs.${field}`, labels[field] || field));
    const euro = (value) => new Intl.NumberFormat(locale || "nl-NL", { style: "currency", currency: "EUR" }).format(Number(value));
    const scoreLabels = {
      benchmark_score: at("dcaDraft.benchmarkSource", "eigen benchmark (markt + macro + technisch)"),
    };
    const isSmartDca = supplied.setup_type === "dca" && supplied.dca_amount_mode === "score_bands";
    const omittedRules = waivedDraftRules(messageIndex, "create_setup");
    return (
      <div className="mt-4 min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-950/45">
        <div className="text-[11px] font-bold text-slate-900 dark:text-slate-100">{at("draftCards.setupTitle", "Concept setup")}</div>
        <div className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{at("draftCards.unsaved", "Nog niet opgeslagen")}</div>
        <div className="mt-4 min-w-0">
          <h3 className="truncate text-base font-bold text-slate-950 dark:text-white">{supplied.name || at("draftCards.newSetup", "Nieuwe setup")}</h3>
          {contextLine && <p className="mt-1 break-words text-xs text-slate-500 dark:text-slate-400">{contextLine}</p>}
        </div>
        {frequency && <p className="mt-3 text-sm text-slate-700 dark:text-slate-200">{at("draftCards.frequency", "Frequentie")}: <span className="font-semibold">{frequency}</span></p>}
        {supplied.min_investment != null && supplied.min_investment !== "" && <p className="mt-1 text-sm text-slate-700 dark:text-slate-200">{at("draftCards.minimumInvestment", "Minimuminvestering")}: <span className="font-semibold">{euro(supplied.min_investment)}</span></p>}
        {supplied.setup_type === "dca" && supplied.base_amount != null && <p className="mt-2 text-sm font-semibold text-slate-700 dark:text-slate-200">{at("dcaDraft.baseAmount", "Basisbedrag (100%): {amount}", { amount: euro(supplied.base_amount) })}</p>}
        {isSmartDca && <div className="mt-3 rounded-xl border border-blue-200 bg-blue-50/70 p-3 text-sm text-slate-800 dark:border-blue-900 dark:bg-blue-950/30 dark:text-slate-200">
          <p className="font-semibold">{at("dcaDraft.smartTitle", "Smart DCA · scoregestuurde bedragen")}</p>
          <p className="mt-1">{at("dcaDraft.scoreSource", "Scorebron: {source}", { source: scoreLabels[supplied.score_source] || at("dcaDraft.sourceMissing", "nog te kiezen") })}</p>
          {supplied.score_source === "benchmark_score" && <p className="mt-1 text-xs">{at("dcaDraft.benchmarkWeights", "De weging volgt je actuele instellingen in Analyse (standaard ieder ⅓). Wijzigingen beïnvloeden toekomstige bedragen. Alle drie scores zijn nodig op de beslisdatum.")}</p>}
          {supplied.base_amount != null && supplied.low_threshold != null && supplied.high_threshold != null && supplied.low_score_percent != null && supplied.mid_score_percent != null && supplied.high_score_percent != null && <ul className="mt-2 space-y-1">
            <li>{at("dcaDraft.below", "Score onder {threshold}: {percent}% = {amount}", { threshold: supplied.low_threshold, percent: supplied.low_score_percent, amount: euro(supplied.base_amount * supplied.low_score_percent / 100) })}</li>
            <li>{at("dcaDraft.between", "Score {low} tot onder {high}: {percent}% = {amount}", { low: supplied.low_threshold, high: supplied.high_threshold, percent: supplied.mid_score_percent, amount: euro(supplied.base_amount * supplied.mid_score_percent / 100) })}</li>
            <li>{at("dcaDraft.above", "Score vanaf {threshold}: {percent}% = {amount}", { threshold: supplied.high_threshold, percent: supplied.high_score_percent, amount: euro(supplied.base_amount * supplied.high_score_percent / 100) })}</li>
          </ul>}
          <p className="mt-2 text-xs">{at("dcaDraft.safetyNote", "Dit zijn geplande bedragen. Een ontbrekende score of veiligheidslimiet kan een aankoop tegenhouden of verlagen.")}</p>
        </div>}
        {supplied.setup_type === "dca" && <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{at("dcaDraft.planOnly", "Bevestigen slaat de setup en strategie op. Er wordt geen bot gestart en geen aankoop gedaan.")}</p>}
        {omittedRules && <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">{typeof omittedRules === "string" ? at("draftCards.waivedRulesNamed", "Niet opgeslagen: {rules}.", { rules: omittedRules }) : at("draftCards.waivedSetupRules", "De extra handelsvoorwaarden uit je eerdere verzoek zijn op jouw keuze weggelaten. Alleen de getoonde setupvelden worden opgeslagen.")}</p>}
        {missing.length > 0 && <p className="mt-4 rounded-xl bg-slate-50 px-3 py-2.5 text-sm text-slate-700 dark:bg-slate-900/70 dark:text-slate-200">{at("draftCards.missingFields", "Nog nodig: {fields}.", { fields: missing.join(", ") })}</p>}
        <div className="mt-4 flex flex-wrap items-center gap-2">{draftActionButtons(message, messageIndex, "setup")}</div>
      </div>
    );
  };

  const renderV2ActionDraftCard = (message, messageIndex) => {
    if (message?.draftCanceled || message?.draftExecuted) return null;
    const draft = message.actionDraft || message.state?.action_draft;
    const operationId = draft?.operation_id;
    const indicatorOperations = ["create_indicator_configuration", "update_indicator_configuration", "delete_indicator_configuration"];
    const watchlistOperations = ["watchlist_add", "watchlist_remove"];
    if (!draft || !["create_strategy", "create_bot", ...indicatorOperations, ...watchlistOperations].includes(operationId)) return null;
    if (!hasConfirmableDraft(message)) return null;
    const isStrategy = operationId === "create_strategy";
    const isBot = operationId === "create_bot";
    const isIndicator = indicatorOperations.includes(operationId);
    const isWatchlist = watchlistOperations.includes(operationId);
    const omittedRules = isStrategy ? waivedDraftRules(messageIndex, "create_strategy") : null;
    const supplied = draft.supplied_inputs || {};
    const context = (message.actions || []).find((action) => action?.type === "v2_proposal")?.display_context || {};
    const linkedName = isStrategy ? supplied.setup_name || context.setup_name || at("draftCards.objectSetup", "Setup") : supplied.strategy_name || context.strategy_name || at("draftCards.objectStrategy", "Strategie");
    const contextLine = isStrategy
      ? [supplied.symbol || context.symbol, supplied.timeframe || context.timeframe, at("draftCards.linkedToName", "gekoppeld aan {name}", { name: linkedName })].filter(Boolean).join(" · ")
      : isBot
        ? `Paper · ${at("draftCards.linkedToName", "gekoppeld aan {name}", { name: linkedName })}`
        : [supplied.asset || context.symbol, isIndicator ? ({ technical: at("draftCards.technicalEvidence", "Technisch bewijs"), macro: "Macro", market: at("draftCards.marketIndicators", "Marktindicatoren") }[supplied.category] || supplied.category) : "Watchlist"].filter(Boolean).join(" · ");
    const labels = { name: "naam", setup_id: "setup", strategy_id: "strategie", symbol: "asset", timeframe: "timeframe", execution_mode: "uitvoering", base_amount: "bedrag", entry: "entry", stop_loss: "stop-loss", targets: "targets", price_currency: "valuta koersniveaus", risk_profile: "risico", budget_total_eur: "budget", dca_amount_mode: "bedragregel", score_source: "totale benchmark", low_threshold: "grens lage/middenscore", high_threshold: "grens midden/hoge score", low_score_percent: "percentage lage score", mid_score_percent: "percentage middenscore", high_score_percent: "percentage hoge score" };
    const missing = (draft.missing_inputs || []).map((field) => at(`draftCards.inputs.${field}`, labels[field] || field));
    const formatValue = (value) => formatDraftCardValue(value, locale);
    const euro = (value) => new Intl.NumberFormat(locale || "nl-NL", { style: "currency", currency: "EUR" }).format(Number(value));
    const dcaBand = (percent) => supplied.base_amount != null && percent != null
      ? `${percent}% · ${euro(supplied.base_amount * percent / 100)}`
      : null;
    const rows = isStrategy
      ? supplied.setup_type === "dca"
        ? [[at("draftCards.fieldAmountRule", "Bedragregel"), supplied.dca_amount_mode === "score_bands" ? "Smart DCA" : supplied.dca_amount_mode === "fixed" ? at("draftCards.fixedAmount", "Vast bedrag") : null],
          [at("draftCards.dcaAmountCalculation", ({ en: "Amount calculation", de: "Betragsberechnung" }[locale] || "Bedragberekening")), formatExecutionMode(supplied.execution_mode, locale)],
          [at("draftCards.fieldBaseAmount", "Basisbedrag (100%)"), supplied.base_amount != null ? euro(supplied.base_amount) : null],
          [at("draftCards.fieldRiskStyle", "Risicostijl"),
            at("draftCards.dcaRiskNotApplicable", ({ en: "Not a setting on a DCA strategy", de: "Keine Einstellung einer DCA-Strategie" }[locale] || "Geen instelling van een DCA-strategie"))],
          [at("draftCards.fieldScoreSource", "Scorebron"), supplied.score_source === "benchmark_score" ? at("draftCards.benchmarkSource", "Totale benchmark (markt, macro en technisch)") : null],
          [supplied.low_threshold != null ? at("draftCards.fieldScoreBelow", "Score onder {threshold}", { threshold: supplied.low_threshold }) : at("draftCards.fieldLowScore", "Lage score"), dcaBand(supplied.low_score_percent)],
          [supplied.low_threshold != null && supplied.high_threshold != null ? at("draftCards.fieldScoreBetween", "Score {low} tot onder {high}", { low: supplied.low_threshold, high: supplied.high_threshold }) : at("draftCards.fieldMidScore", "Middenscore"), dcaBand(supplied.mid_score_percent)],
          [supplied.high_threshold != null ? at("draftCards.fieldScoreFrom", "Score vanaf {threshold}", { threshold: supplied.high_threshold }) : at("draftCards.fieldHighScore", "Hoge score"), dcaBand(supplied.high_score_percent)]]
        : [[at("draftCards.fieldExecution", "Uitvoering"), [formatExecutionMode(supplied.execution_mode, locale), supplied.base_amount ? euro(supplied.base_amount) : null].filter(Boolean).join(" · ")],
          ["Entry", supplied.entry != null ? `${formatValue(supplied.entry)} ${supplied.price_currency || "EUR"}` : null],
          ["Stop-loss", supplied.stop_loss != null ? `${formatValue(supplied.stop_loss)} ${supplied.price_currency || "EUR"}` : null],
          ["Targets", supplied.targets?.length ? `${supplied.targets.map(formatValue).join(", ")} ${supplied.price_currency || "EUR"}` : null],
          [at("draftCards.fieldRisk", "Risico"), supplied.risk_profile]]
      : isBot
        ? [[({ en: "Bot budget limit", de: "Bot-Budgetlimit" }[locale] || "Botbudgetlimiet"), supplied.budget_total_eur ? `€${supplied.budget_total_eur}` : null],
          [({ en: "Virtual Paper starting capital", de: "Virtuelles Paper-Startkapital" }[locale] || "Virtueel Paper-startkapitaal"), supplied.paper_initial_cash_eur ? `€${supplied.paper_initial_cash_eur}` : null]]
        : isIndicator
          ? [[at("draftCards.fieldIndicator", "Indicator"), supplied.indicator ? indicatorDisplayName(supplied.indicator) : null], [at("draftCards.fieldCategory", "Categorie"), ({ technical: at("draftCards.technicalEvidence", "Technisch bewijs"), macro: "Macro", market: at("draftCards.marketIndicators", "Marktindicatoren") }[supplied.category] || supplied.category)], [at("draftCards.fieldWeight", "Weging"), supplied.weight]]
          : [];
    const title = isStrategy
      ? at("draftCards.strategyTitle", "Concept strategie")
      : isBot
        ? at("draftCards.botTitle", "Concept paper-bot")
        : isIndicator
          ? operationId === "delete_indicator_configuration" ? at("draftCards.indicatorDelete", "Indicator verwijderen") : at("draftCards.indicatorTitle", "Concept indicator")
          : operationId === "watchlist_remove" ? at("draftCards.watchlistRemove", "Uit watchlist verwijderen") : at("draftCards.watchlistAdd", "Aan watchlist toevoegen");
    const objectName = supplied.name
      || (isIndicator ? indicatorDisplayName(supplied.indicator) : null)
      || (isWatchlist ? supplied.asset || context.symbol : null)
      || (isStrategy ? at("draftCards.newStrategy", "Nieuwe strategie") : at("draftCards.newBot", "Nieuwe paper-bot"));
    return (
      <div className="mt-4 min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-950/45">
        <div className="text-[11px] font-bold text-slate-900 dark:text-slate-100">{title}</div>
        <div className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{at("draftCards.unsaved", "Nog niet opgeslagen")}</div>
        <div className="mt-4 min-w-0">
          <h3 className="truncate text-base font-bold text-slate-950 dark:text-white">{objectName}</h3>
          <p className="mt-1 break-words text-xs text-slate-500 dark:text-slate-400">{contextLine}</p>
        </div>
        <dl className="mt-4 divide-y divide-slate-100 text-sm dark:divide-slate-800">
          {rows.filter(([, value]) => value !== undefined && value !== null && value !== "").map(([label, value]) => (
            <div key={label} className="flex min-w-0 items-start justify-between gap-4 py-2 first:pt-0 last:pb-0"><dt className="shrink-0 text-slate-500 dark:text-slate-400">{label}</dt><dd className="min-w-0 break-words text-right font-semibold text-slate-800 dark:text-slate-100">{formatValue(value)}</dd></div>
          ))}
        </dl>
        {isStrategy && supplied.setup_type !== "dca" && supplied.price_currency === "USD" && <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">{at("draftCards.usdLevelsPaperHold", "De koersniveaus zijn in USD. Een gekoppelde bot wacht met automatische uitvoering totdat een betrouwbare omrekening naar EUR beschikbaar is.")}</p>}
        {isStrategy && omittedRules && <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">{typeof omittedRules === "string" ? at("draftCards.waivedRulesNamed", "Niet opgeslagen: {rules}.", { rules: omittedRules }) : at("draftCards.waivedStrategyRules", "De extra automatische regels uit je eerdere verzoek zijn op jouw keuze weggelaten. Alleen de getoonde strategievelden worden opgeslagen.")}</p>}
        {isStrategy && supplied.setup_type === "dca" && <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">{at("draftCards.dcaStrategyOnly", "Bevestigen slaat alleen deze extra strategie op onder de bestaande DCA-setup. Er wordt geen bot gestart en geen aankoop gedaan.")} {at("draftCards.dcaBotModeSeparate", ({ en: "Manual or automatic operation is set on a bot, not on this strategy.", de: "Manueller oder automatischer Betrieb wird am Bot eingestellt, nicht an dieser Strategie." }[locale] || "Handmatige of automatische uitvoering stel je bij een bot in, niet bij deze strategie."))}</p>}
        {isBot && <p className="mt-4 flex items-center gap-2 text-xs font-semibold text-emerald-700 dark:text-emerald-300"><Shield size={13} />{at("draftCards.noLiveTrading", "Geen live trading")}</p>}
        {missing.length > 0 && <p className="mt-4 rounded-xl bg-slate-50 px-3 py-2.5 text-sm text-slate-700 dark:bg-slate-900/70 dark:text-slate-200">{at("draftCards.missingFields", "Nog nodig: {fields}.", { fields: missing.join(", ") })}</p>}
        <div className="mt-4 flex flex-wrap items-center gap-2">{draftActionButtons(message, messageIndex, isStrategy ? "strategie" : isBot ? "paper-bot" : isIndicator ? "indicator" : "watchlist")}</div>
      </div>
    );
  };

  const renderDraftQuestionChoices = (message, messageIndex) => {
    if (message.isComplete === false || (!isCollectingDraft(message) && !isOpenClarification(message)) || message.draftCanceled || message.draftExecuted) return null;
    if (messages.slice(messageIndex + 1).some((later) => later.role === "user")) return null;
    const choices = isOpenClarification(message)
      ? clarificationQuestionChoices(message)
      : draftQuestionChoices(message, locale);
    const copy = draftConversationCopy(locale);
    return (
      <div className="mt-3 space-y-2" aria-label={choices.length ? copy.hint : copy.freeTextHint}>
        {choices.map((choice) => (
          <button
            key={`${messageIndex}-${choice.reply}`}
            type="button"
            onClick={() => void handleChat(choice.reply, false, message.state)}
            disabled={loading || executingAction}
            className="flex w-full min-w-0 items-center rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm font-semibold text-slate-800 transition-colors hover:border-blue-400 hover:bg-blue-50 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:border-blue-600 dark:hover:bg-blue-950/30"
          >
            {choice.label}
          </button>
        ))}
        {choices.length > 0 && <button
          type="button"
          onClick={() => commandCenterRef.current?.focus?.()}
          className="flex w-full items-center rounded-xl border border-dashed border-slate-300 px-4 py-3 text-left text-sm font-medium text-slate-600 hover:border-blue-400 hover:text-blue-700 dark:border-slate-700 dark:text-slate-300"
        >{copy.other}</button>}
        <p className="text-xs text-slate-500 dark:text-slate-400">{choices.length ? copy.hint : copy.freeTextHint}</p>
      </div>
    );
  };

  const renderBehavioralMemoryAckCard = (message) => {
    const friction = message.state?.pending_behavioral_memory_friction || message.state?.memory_friction || null;
    const requiresAck = Boolean(
      friction?.requires_ack &&
      !friction?.acknowledged &&
      (
        message.nextQuestion === "behavioral_memory_ack" ||
        (message.missingFields || []).includes("behavioral_memory_ack") ||
        message.state?.status === "blocked_by_behavioral_memory"
      )
    );
    if (!requiresAck) return null;

    const evidence = Array.isArray(friction.evidence) ? friction.evidence : [];
    const ackPhrase = friction.ack_phrase || "bewust doorgaan";

    return (
      <div className="mt-4 rounded-2xl border border-amber-200 dark:border-amber-900/50 bg-amber-50/90 dark:bg-amber-950/25 p-4 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">
            <Shield size={14} />
            {uiText.behavioralMemoryCheck}
          </div>
          <span className="shrink-0 rounded-full border border-amber-200 dark:border-amber-900/60 bg-white/80 dark:bg-slate-950/40 px-2 py-1 text-[9px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">
            {uiText.consciousConfirmationNeeded}
          </span>
        </div>

        <div className="space-y-1">
          <div className="text-sm font-black text-slate-950 dark:text-slate-50">
            {at("behavioralMemory.slowsDown")}
          </div>
          <p className="text-xs font-semibold leading-relaxed text-amber-900 dark:text-amber-100">
            {friction.message || at("behavioralMemory.patternCaution")}
          </p>
        </div>

        {evidence.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-[9px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">
              {at("behavioralMemory.evidence")}
            </div>
            <div className="grid grid-cols-1 gap-1">
              {evidence.slice(0, 4).map((item, index) => (
                <div
                  key={`${item}-${index}`}
                  className="rounded-lg border border-amber-100 dark:border-amber-900/40 bg-white/75 dark:bg-slate-950/35 px-2.5 py-2 text-[11px] font-bold leading-snug text-slate-800 dark:text-slate-100"
                >
                  {item}
                </div>
              ))}
            </div>
          </div>
        )}

        {friction.safe_alternative && (
          <p className="text-[11px] font-bold leading-snug text-slate-700 dark:text-slate-200">
            {uiText.safeRoute}: {friction.safe_alternative}
          </p>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
          <button
            onClick={() => handleChat(ackPhrase, false, message.state)}
            disabled={loading || executingAction}
            className="flex items-center justify-center gap-2 rounded-xl bg-amber-600 px-3 py-2.5 text-[10px] font-black uppercase tracking-widest text-white shadow-lg shadow-amber-600/15 transition-colors hover:bg-amber-700 disabled:opacity-60"
          >
            <Shield size={14} />
            {uiText.consciouslyContinue}
          </button>
          <button
            onClick={() => handleChat("Welke bot-decisions moet ik eerst reviewen?", false, {})}
            disabled={loading || executingAction}
            className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-950/40 px-3 py-2.5 text-[10px] font-black uppercase tracking-widest text-slate-700 dark:text-slate-200 transition-colors hover:border-slate-300 dark:hover:border-slate-700 disabled:opacity-60"
          >
            <ListChecks size={14} />
            {uiText.reviewFirst}
          </button>
        </div>
      </div>
    );
  };

  const renderInlineActionCard = (message) => {
    if (isCollectingDraft(message)) return null;
    const actions = Array.isArray(message.actions) ? message.actions : [];
    const actionOnly = actions.filter((action) => (
      action?.requires_confirmation && action.type === "v2_proposal"
    ));
    const dedicatedDraftOperation = message.setupDraft?.operation_id
      || message.actionDraft?.operation_id
      || message.state?.setup_draft?.operation_id
      || message.state?.action_draft?.operation_id;
    const hasDedicatedDraftCard = [
      "create_setup", "create_strategy", "create_bot",
      "watchlist_add", "watchlist_remove",
      "create_indicator_configuration", "update_indicator_configuration", "delete_indicator_configuration",
    ].includes(dedicatedDraftOperation);
    if (actionOnly.length === 0 || message.draft || hasDedicatedDraftCard) return null;
    const displayContext = actionOnly[0]?.display_context || {};
    const operationId = displayContext.operation_id || "";
    const isUpdate = operationId.startsWith("update_") || operationId === "deactivate_bot";
    const isDelete = operationId.startsWith("delete_");
    const isWatchlistAction = ["watchlist_add", "watchlist_remove"].includes(operationId);
    const isIndicatorAction = ["create_indicator_configuration", "update_indicator_configuration", "delete_indicator_configuration"].includes(operationId);
    const suppliedInputs = displayContext.supplied_inputs || {};
    const namedTargetReview = [
      "delete_setup", "delete_strategy", "delete_bot", "deactivate_bot",
      "activate_paper_bot", "activate_live_bot",
    ].includes(operationId);
    const verifiedTargetName = namedTargetReview ? displayContext.review_target_name : null;
    const objectType = operationId.includes("strategy") ? at("draftCards.objectStrategy", "Strategie") : operationId.includes("bot") ? at("draftCards.objectBot", "Paper-bot") : operationId.includes("setup") ? at("draftCards.objectSetup", "Setup") : at("draftCards.objectProposal", "Voorstel");
    const objectName = verifiedTargetName || displayContext.name
      || (operationId.includes("setup") ? activeSetup?.name : null)
      || (operationId.includes("strategy") ? displayContext.strategy_name || activeSetup?.strategy_name : null)
      || (operationId.includes("bot") ? displayContext.bot_name || activeBot?.name : null)
      || at("draftCards.thisObject", "deze {object}", { object: objectType.toLowerCase() });
    const linkedName = operationId.includes("strategy") ? displayContext.setup_name || activeSetup?.name : operationId.includes("bot") ? displayContext.strategy_name || activeBot?.strategy_name : null;
    const fieldLabels = { name: at("draftCards.fieldName", "Naam"), timeframe: at("draftCards.fieldTimeframe", "Timeframe"), base_amount: at("draftCards.fieldAmount", "Bedrag"), stop_loss: "Stop-loss", entry: "Entry", targets: "Targets", risk_profile: at("draftCards.fieldRisk", "Risico"), budget_total_eur: at("draftCards.fieldBudget", "Budget"), cadence: at("draftCards.fieldCadence", "Frequentie") };
    const changedRows = Object.entries(displayContext.requested_state || displayContext.changed_fields || {}).filter(([, value]) => value !== null && value !== undefined).map(([field, value]) => {
      const previous = displayContext.before_state?.[field];
      return { label: fieldLabels[field] || field.replace(/_/g, " "), previous, value: Array.isArray(value) ? value.join(", ") : value };
    });
    const isDomainProposal = isUpdate || isDelete;
    const contextParts = [
      verifiedTargetName || displayContext.name,
      displayContext.symbol,
      displayContext.timeframe,
      displayContext.safety_mode,
    ].filter(Boolean);

    if (isWatchlistAction || isIndicatorAction) {
      const asset = suppliedInputs.asset || displayContext.symbol;
      const indicator = indicatorDisplayName(suppliedInputs.indicator);
      const category = ({ technical: at("draftCards.technicalEvidence", "Technisch bewijs"), macro: "Macro", market: at("draftCards.marketIndicators", "Marktindicatoren") })[suppliedInputs.category] || suppliedInputs.category;
      const title = isWatchlistAction
        ? operationId === "watchlist_remove" ? at("draftCards.watchlistRemove", "Uit watchlist verwijderen") : at("draftCards.watchlistAdd", "Aan watchlist toevoegen")
        : operationId === "delete_indicator_configuration" ? at("draftCards.indicatorDelete", "Indicator verwijderen") : operationId === "update_indicator_configuration" ? at("draftCards.indicatorUpdate", "Indicator wijzigen") : at("draftCards.indicatorAdd", "Indicator toevoegen");
      const summary = isWatchlistAction
        ? at(operationId === "watchlist_remove" ? "draftCards.watchlistRemoveSummary" : "draftCards.watchlistAddSummary", "{asset} aan je watchlist toevoegen", { asset: asset || "Asset" })
        : at(operationId === "delete_indicator_configuration" ? "draftCards.indicatorDeleteSummary" : operationId === "update_indicator_configuration" ? "draftCards.indicatorUpdateSummary" : "draftCards.indicatorAddSummary", "{indicator} toevoegen aan {category}{assetSuffix}", {
            indicator: indicator || at("draftCards.fieldIndicator", "Indicator"),
            category: category || at("draftCards.analysis", "je analyse"),
            assetSuffix: asset ? at("draftCards.assetSuffix", " voor {asset}", { asset }) : "",
          });
      return (
        <div className="mt-4 min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-950/45">
          <div className="text-[11px] font-bold text-slate-900 dark:text-slate-100">{title}</div>
          <div className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{at("draftCards.unsaved", "Nog niet opgeslagen")}</div>
          <h3 className="mt-4 break-words text-base font-bold text-slate-950 dark:text-white">{summary}</h3>
          {isIndicatorAction && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{[asset, category].filter(Boolean).join(" · ")}</p>}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {actionOnly.map((action, index) => (
              <button type="button" key={`${action.type}-${action.id || index}`} onClick={() => void handleExecuteAction(action)} disabled={loading || executingAction || message.confirmationSuspended} className={actionButtonStyles({ variant: operationId.startsWith("delete_") ? "danger" : "primary", className: "min-w-[120px] justify-center rounded-xl px-4 py-2.5 text-xs" })}>
                {executingAction ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />} {operationId.startsWith("delete_") ? at("draftCards.delete", "Verwijderen") : at("draftCards.confirm", "Bevestigen")}
              </button>
            ))}
            <button type="button" onClick={() => void handleCancelDraft(messages.indexOf(message))} disabled={executingAction} className="rounded-xl px-3 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-900">{at("draftCards.cancel", "Annuleren")}</button>
          </div>
        </div>
      );
    }

    if (isDomainProposal) {
      return (
        <div className="mt-4 min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-950/45">
          <div className="text-[11px] font-bold text-slate-900 dark:text-slate-100">{isDelete ? at("draftCards.deleteObject", "{object} verwijderen", { object: objectType }) : at("draftCards.changeObject", "{object} wijzigen", { object: objectType })}</div>
          <div className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{at("draftCards.notExecuted", "Nog niet uitgevoerd")}</div>
          <h3 className="mt-4 break-words text-base font-bold text-slate-950 dark:text-white">{isDelete ? at("draftCards.deleteObjectQuestion", "{object} “{name}” verwijderen?", { object: objectType, name: objectName }) : objectName}</h3>
          {linkedName && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{at("draftCards.linkedTo", "Gekoppeld aan")} {linkedName}</p>}
          {isUpdate && changedRows.length > 0 && (
            <dl className="mt-4 divide-y divide-slate-100 text-sm dark:divide-slate-800">
              {changedRows.map((row) => (
                <div key={row.label} className="flex min-w-0 items-start justify-between gap-4 py-2 first:pt-0 last:pb-0">
                  <dt className="shrink-0 text-slate-500 dark:text-slate-400">{row.label}</dt>
                  <dd className="min-w-0 break-words text-right font-semibold text-slate-800 dark:text-slate-100">{row.previous !== null && row.previous !== undefined && row.previous !== "" ? `${row.previous} → ${row.value}` : row.value}</dd>
                </div>
              ))}
            </dl>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {actionOnly.map((action, index) => (
              <button type="button" key={`${action.type}-${action.id || index}`} onClick={() => void handleExecuteAction(action)} disabled={loading || executingAction || message.confirmationSuspended || (namedTargetReview && !verifiedTargetName)} className={actionButtonStyles({ variant: isDelete ? "danger" : "primary", className: "min-w-[120px] justify-center rounded-xl px-4 py-2.5 text-xs" })}>
                {executingAction ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />} {isDelete ? at("draftCards.delete", "Verwijderen") : at("draftCards.confirm", "Bevestigen")}
              </button>
            ))}
            <button type="button" onClick={() => void handleCancelDraft(messages.indexOf(message))} disabled={executingAction} className="rounded-xl px-3 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-900">{at("draftCards.cancel", "Annuleren")}</button>
          </div>
        </div>
      );
    }

    return (
      <div className="mt-4 rounded-2xl border border-blue-200 dark:border-blue-900/50 bg-blue-50/70 dark:bg-blue-950/20 p-4 space-y-3">
        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-blue-600 dark:text-blue-300">
          <ListChecks size={13} />
          {uiText.finnActionNeedsConfirmation}
        </div>
        <div className="grid gap-2">
          <div className="rounded-xl border border-blue-100 dark:border-blue-900/40 bg-white/80 dark:bg-slate-950/35 px-3 py-2">
            <div className="text-[8px] font-black uppercase tracking-[0.22em] text-blue-500 dark:text-blue-300">{uiText.context}</div>
            <p className="mt-1 text-[11px] font-semibold text-slate-700 dark:text-slate-200">
              {contextParts.length > 0 ? contextParts.join(" · ") : "FINN voorstel"}
            </p>
          </div>
          <div className="rounded-xl border border-blue-100 dark:border-blue-900/40 bg-white/80 dark:bg-slate-950/35 px-3 py-2">
            <div className="text-[8px] font-black uppercase tracking-[0.22em] text-blue-500 dark:text-blue-300">{uiText.impact}</div>
            <p className="mt-1 text-[11px] font-semibold text-slate-700 dark:text-slate-200">
              {operationId === "activate_live_bot"
                ? at("inlineAction.activateLiveEffect", "Je activeert bot {name} in Live-modus na bevestiging.", { name: verifiedTargetName })
                : operationId === "activate_paper_bot"
                  ? at("inlineAction.activatePaperEffect", "Je activeert bot {name} in Paper-modus na bevestiging.", { name: verifiedTargetName })
                  : at("inlineAction.updatesAfterConfirm")}
            </p>
          </div>
          <div className="rounded-xl border border-blue-100 dark:border-blue-900/40 bg-white/80 dark:bg-slate-950/35 px-3 py-2">
            <div className="text-[8px] font-black uppercase tracking-[0.22em] text-blue-500 dark:text-blue-300">{uiText.safety}</div>
            <p className="mt-1 text-[11px] font-semibold text-slate-700 dark:text-slate-200">
              {at("inlineAction.noLiveTrades")}
            </p>
          </div>
          <div className="rounded-xl border border-blue-100 dark:border-blue-900/40 bg-white/80 dark:bg-slate-950/35 px-3 py-2">
            <div className="text-[8px] font-black uppercase tracking-[0.22em] text-blue-500 dark:text-blue-300">{uiText.afterThis}</div>
            <p className="mt-1 text-[11px] font-semibold text-slate-700 dark:text-slate-200">
              {at("inlineAction.afterConfirmation")}
            </p>
          </div>
        </div>
        <div className="space-y-2">
          {actionOnly.map((action, index) => (
            <button
              key={`${action.type}-${action.id || index}`}
              onClick={() => handleExecuteAction(action)}
              disabled={loading || executingAction || message.confirmationSuspended || (namedTargetReview && !verifiedTargetName)}
              className={actionButtonStyles({
                variant: "primary",
                className: "w-full justify-center gap-2 px-4 py-3 rounded-xl text-[11px] tracking-widest shadow-sm",
              })}
            >
              {executingAction ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
              {action.label || uiText.confirm}
            </button>
          ))}
        </div>
        <p className="text-[10px] font-semibold text-blue-700/80 dark:text-blue-200/80 leading-snug">
          {at("inlineAction.confirmationFooter")}
        </p>
      </div>
    );
  };

  const scrollAssistantViewport = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollAssistantViewport();
  }, [messages, loading, activeState]);

  const progress = activeState ? getFlowProgress(activeState) : null;
  const activeStep = progress ? Math.min(progress.filled + 1, progress.total) : 1;
  const workspaceContextLabel = getFinnWorkspaceLabel(pathname, locale) || humanizeFinnContextValue(context.page_type, "Workspace");
  const finnContextLabel = [workspaceContextLabel, context.symbol || "BTC"]
    .filter(Boolean)
    .join(" · ");
  const compactFinnHeader = [
    "FINN",
    workspaceContextLabel,
    String((pathname === "/bot" && context.bot_id ? context.symbol : chatAssetOverride || context.symbol) || globalSymbol || "BTC").toUpperCase(),
  ].filter(Boolean);
  const finnModeLabel =
    activeState?.current_flow && activeState.current_flow !== "none"
      ? uiText.conceptMode
      : pathname?.includes("/portfolio")
      ? uiText.paperMode
      : uiText.readOnlyMode;
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.sessionStorage.getItem(userScopedRecentConversationStorageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      setRecentConversations(Array.isArray(parsed) ? parsed : []);
    } catch (error) {
      console.warn("Kon recente FINN-gesprekken niet laden:", error);
      setRecentConversations([]);
    }
  }, [userScopedRecentConversationStorageKey]);

  useEffect(() => {
    if (typeof window === "undefined" || loading) return;

    const persistedMessages = messages
      .map(sanitizeMessageForPersistence)
      .filter(Boolean);

    if (persistedMessages.length === 0) return;

    const title = getRecentConversationTitle(persistedMessages);
    const nextConversation = {
      id: `${currentConversationStorageKey}:${title.toLowerCase()}`,
      storageKey: currentConversationStorageKey,
      title: title.length > 88 ? `${title.slice(0, 85)}...` : title,
      updatedAt: new Date().toISOString(),
      messages: persistedMessages,
    };

    setRecentConversations((prev) => {
      const merged = [
        nextConversation,
        ...prev.filter((item) => item?.id !== nextConversation.id),
      ].slice(0, 12);

      try {
        window.sessionStorage.setItem(userScopedRecentConversationStorageKey, JSON.stringify(merged));
      } catch (error) {
        console.warn("Kon recente FINN-gesprekken niet bewaren:", error);
      }

      return merged;
    });
  }, [messages, loading, currentConversationStorageKey, userScopedRecentConversationStorageKey]);

  const recentFinnSessionItems = availableFinnSessions.slice(0, MAX_RECENT_FINN_CONVERSATIONS);

  const showSimpleFinnHistory = true;

  useEffect(() => {
    if (!isOpen || !hasTraderProfile) return;
    const key = `${pathname || "/assistant"}:${globalSymbol || context.symbol || "BTC"}:${profileSummaryLabel}`;
    if (profileTelemetryKeyRef.current === key) return;
    profileTelemetryKeyRef.current = key;
    trackAssistantEvent({
      event_name: "finn_profile_context_used",
      page: pathname || "/assistant",
      surface: "finn_overlay",
      asset: globalSymbol || context.symbol || null,
      flow_type: "profile_context",
      next_best_action: profileSummaryLabel,
    });
  }, [isOpen, hasTraderProfile, pathname, globalSymbol, context.symbol, profileSummaryLabel]);

  useEffect(() => {
    if (!isOpen || !commandRequest?.nonce || commandRequest.mode !== "chat") return;
    // Selecting a feed item starts a separate discussion. It cannot inherit
    // an older conversation's pending proposal or selected plan.
    if (isFeedHandoff && commandRequest.newConversation) {
      forceNewFinnConversationRef.current = true;
      activeFinnSessionIdRef.current = null;
      sharedSessionRestoreRef.current = true;
      setActiveFinnSessionId(null);
      setActiveState(null);
      setFinnDraft(null);
      setMessages([]);
    }
    if (commandRequest.query !== undefined) updateQuery(commandRequest.query);
  }, [commandRequest?.nonce, isOpen]);

  useEffect(() => {
    if (!isOpen || !commandRequest?.nonce || !["asset", "indicator", "all"].includes(commandRequest.mode)) return;
    if (stashedComposerDraftRef.current === null) stashedComposerDraftRef.current = activeQuery;
    updateQuery("");
  }, [commandRequest?.nonce, isOpen]);

  useEffect(() => {
    if (!isOpen || !commandRequest?.autoSubmit || !commandRequest?.query) return;
    if (handledContextRequestRef.current === commandRequest.nonce) return;
    handledContextRequestRef.current = commandRequest.nonce;
    handleChat(commandRequest.query);
  }, [commandRequest?.nonce, isOpen]);

  if (!isOpen) return null;

  const shellClassName = persistent
    ? previewSectionsOnly
      ? "relative w-full bg-card dark:bg-[#0f172a] flex flex-col"
      : "relative h-[70dvh] w-full bg-card dark:bg-[#0f172a] flex flex-col lg:h-full"
    : dock
      ? "relative h-full w-full overflow-hidden bg-card dark:bg-[#0f172a] flex flex-col"
    : modal
      ? `relative max-h-[82vh] w-[min(960px,calc(100vw-2rem))] overflow-hidden rounded-[32px] border border-slate-200 bg-card shadow-2xl transition-all duration-300 dark:border-slate-800 dark:bg-[#0f172a] flex flex-col ${
          isOpen ? "translate-y-0 opacity-100 scale-100" : "translate-y-4 opacity-0 scale-[0.98]"
        }`
      : `fixed top-0 right-0 h-full bg-card dark:bg-[#0f172a] border-l border-slate-200 dark:border-slate-800 z-[70] shadow-2xl transition-all duration-300 flex flex-col ${
          isOpen ? "translate-x-0" : "translate-x-full"
        } w-full md:w-[400px]`;

  return (
    <aside className={`${shellClassName} ${className}`.trim()}>
      {/* HEADER */}
      <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-card dark:bg-[#0f172a] relative z-10 shadow-sm flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-lg shadow-blue-600/30">
             <Bot size={20} />
          </div>
          <div>
            {isSimpleFinnModal ? (
              <>
                <h2 className="text-sm font-black text-foreground dark:text-slate-100 tracking-tight">
                  FINN
                </h2>
                <div className="mt-0.5 flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                  <span>{compactFinnHeader[1]}</span>
                  <span aria-hidden="true">·</span>
                  <select
                    aria-label={at("uiText.assetContext")}
                    value={(pathname === "/bot" && context.bot_id ? context.symbol : chatAssetOverride || context.symbol) || globalSymbol || ""}
                    disabled={pathname === "/bot" && Boolean(context.bot_id)}
                    onChange={(event) => setChatAssetOverride(event.target.value || null)}
                    className="max-w-24 cursor-pointer bg-transparent font-semibold text-slate-600 outline-none disabled:cursor-default dark:text-slate-300"
                  >
                    {!FINN_ASSETS.some((asset) => asset.symbol === (pathname === "/bot" && context.bot_id ? context.symbol : chatAssetOverride || context.symbol || globalSymbol)) ? (
                      <option value={(pathname === "/bot" && context.bot_id ? context.symbol : chatAssetOverride || context.symbol) || globalSymbol || ""}>{(pathname === "/bot" && context.bot_id ? context.symbol : chatAssetOverride || context.symbol) || globalSymbol || "—"}</option>
                    ) : null}
                    {FINN_ASSETS.map((asset) => <option key={asset.symbol} value={asset.symbol}>{asset.symbol}</option>)}
                  </select>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-black text-foreground dark:text-slate-100 tracking-tight">FINN</h2>
                      {!previewSectionsOnly ? (
                        <span className="text-[9px] font-black uppercase tracking-widest bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 rounded">{finnModeLabel}</span>
                      ) : null}
                </div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="text-[10px] font-bold text-secondary dark:text-slate-500 uppercase tracking-widest leading-none">
                    {finnContextLabel}
                  </span>
                </div>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1">
          {isSimpleFinnModal ? (
            <>
              <button type="button" onClick={() => setShowSessionMenu((current) => !current)}
                aria-label={uiText.backendSessions} aria-expanded={showSessionMenu}
                className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-900">
                <History size={18} />
              </button>
              <button type="button" onClick={() => { setShowSessionMenu(false); void startNewFinnConversation(); }}
                aria-label={uiText.newConversation}
                className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-900">
                <Plus size={18} />
              </button>
              {dock && onToggleExpanded ? (
                <button type="button" onClick={onToggleExpanded}
                  aria-label={expanded ? at("uiText.shrinkChat") : at("uiText.expandChat")}
                  className="hidden rounded-lg p-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-900 xl:inline-flex">
                  {expanded ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
                </button>
              ) : null}
            </>
          ) : null}
          {!persistent ? (
            <button type="button" onClick={() => setIsOpen(false)}
              aria-label={closeLabel || at("uiText.closeChat")}
              className="rounded-lg p-2 text-secondary hover:bg-slate-50 hover:text-slate-900 dark:hover:bg-slate-900 dark:hover:text-slate-100">
              <X size={18} />
            </button>
          ) : null}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto no-scrollbar scroll-smooth" ref={scrollRef}>



        {/* SECTION 1 — FINN POSTURE & BRIEFING */}


        {/* SECTION 1B — FINN Mission Control */}


        {!previewSectionsOnly && (
        <>
        {/* MESSAGES AREA */}
        {showSimpleFinnHistory ? (
        <div className={`space-y-4 ${isSimpleFinnModal ? "p-5 pb-8" : "p-6 pb-20"}`}>
          {isSimpleFinnModal && showSessionMenu && (
            <div className="space-y-2 rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-center justify-between gap-3">
                <div className="px-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
                  {uiText.backendSessions}
                </div>
                <button
                  type="button"
                  onClick={() => { setShowSessionMenu(false); void startNewFinnConversation(); }}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-slate-600 transition hover:border-blue-200 hover:text-blue-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                >
                  {uiText.newConversation}
                </button>
              </div>
              {recentFinnSessionItems.map((session) => {
                const isActiveSession = session?.id === activeFinnSessionId;
                return (
                  <button
                    key={session.id}
                    type="button"
                    onClick={() => { setShowSessionMenu(false); void restoreFinnSession(session.id); }}
                    className={`flex w-full items-center justify-between gap-3 rounded-2xl border px-3 py-3 text-left transition ${
                      isActiveSession
                        ? "border-blue-200 bg-blue-50 dark:border-blue-900/60 dark:bg-blue-950/20"
                        : "border-slate-200 bg-white hover:border-blue-200 hover:bg-blue-50/40 dark:border-slate-800 dark:bg-slate-900/40 dark:hover:border-blue-900/40 dark:hover:bg-blue-950/10"
                    }`}
                  >
                    <span className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-700 dark:text-slate-200">
                      {session.title || "FINN gesprek"}
                    </span>
                    <span className="shrink-0 text-[10px] font-semibold text-slate-400 dark:text-slate-500">
                      {formatRecentConversationTime(session.updated_at)}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {isSimpleFinnModal && messages.length === 0 && !loading && !isCommandSearchOpen && (
            <div className="space-y-3 py-5">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{at("uiText.emptyChatTitle")}</h3>
              <p className="text-sm text-slate-500 dark:text-slate-400">{at("uiText.emptyChatHint")}</p>
              <div className="grid gap-2">
                {[
                  ["uiText.starterPlan", "uiText.starterPlanPrompt"],
                  ["uiText.starterAttention", "uiText.starterAttentionPrompt"],
                  ["uiText.starterScore", "uiText.starterScorePrompt"],
                ].map(([labelKey, promptKey]) => (
                  <button key={labelKey} type="button" onClick={() => handleChat(at(promptKey))}
                    className="rounded-xl border border-slate-200 px-4 py-3 text-left text-sm font-medium text-slate-700 transition hover:border-blue-300 hover:text-blue-700 dark:border-slate-800 dark:text-slate-200">
                    {at(labelKey)}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`${m.role === "user" ? "max-w-[90%] rounded-2xl px-4 py-3" : "w-full"} ${
                m.role === "user"
                  ? "bg-blue-600 text-white shadow-lg shadow-blue-600/10"
                  : m.isError
                    ? "text-rose-700 dark:text-rose-300"
                    : "text-foreground dark:text-slate-100"
                }`}>
                <p className="whitespace-pre-line text-[15px] leading-7">
                  {m.role === "assistant"
                    ? parseFinnChatText(m.text).map((part, index) => part.bold
                      ? <strong key={index}>{part.text}</strong>
                      : <React.Fragment key={index}>{part.text}</React.Fragment>)
                    : m.text}
                </p>
                {m.role === "assistant" && m.isComplete !== false && Array.isArray(m.reviewLinks) && m.reviewLinks.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {m.reviewLinks.filter((link) => Number.isSafeInteger(link?.review_id) && link.review_id > 0).slice(0, 5).map((link) => (
                      <button key={link.review_id} type="button" onClick={() => router.push(`/report?trade_review_id=${link.review_id}`)} className="rounded-lg border border-blue-300 px-3 py-1.5 text-xs font-bold text-blue-700 hover:bg-blue-50 dark:text-blue-300 dark:hover:bg-blue-950/30">
                        {uiText.tradeReview} #{link.review_id}
                      </button>
                    ))}
                  </div>
                )}
                {m.isError && m.retryQuery ? (
                  <button type="button" onClick={() => handleChat(m.retryQuery, false, null, i)}
                    className="mt-2 text-sm font-semibold text-blue-600 hover:underline dark:text-blue-400">
                    {uiText.retry}
                  </button>
                ) : null}













                {m.draft && m.draftCanceled && m.isComplete !== false && (
                  <div className="mt-3 p-3 bg-slate-100/50 dark:bg-slate-950/20 border border-dashed border-slate-200 dark:border-slate-800/80 rounded-xl text-center text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                    {at("draftStatus.canceled")}
                  </div>
                )}
                {m.draft && m.draftExecuted && m.isComplete !== false && (
                  <div className="mt-3 p-3 bg-emerald-500/10 dark:bg-emerald-950/20 border border-emerald-500/30 rounded-xl text-center text-[10px] text-emerald-600 dark:text-emerald-400 font-black uppercase tracking-widest flex items-center justify-center gap-1.5 animate-pulse">
                    {at("draftStatus.saved")}
                  </div>
                )}
                {m.proposalRetired && m.isComplete !== false && (
                  <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
                    {at("draftStatus.proposalRetired")}
                  </div>
                )}
                {m.confirmationSuspended && !m.proposalRetired && m.isComplete !== false && (
                  <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
                    {at("draftStatus.proposalSuspended")}
                  </div>
                )}
                {renderBehavioralMemoryAckCard(m)}
                {renderDraftQuestionChoices(m, i)}
                {renderV2SetupDraftCard(m, i)}
                {renderV2ActionDraftCard(m, i)}

                {renderInlineActionCard(m)}
                {m.isError && !isSimpleFinnModal && (
                  <button
                    onClick={() => handleChat(messages[i-1]?.text)}
                    className="mt-2 text-[10px] font-bold uppercase tracking-widest underline hover:text-rose-900 dark:hover:text-rose-100"
                  >
                    {uiText.retry}
                  </button>
                )}
              </div>
            </div>
          ))}



          {loading && (
            <div role="status" className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <Loader2 size={16} className="animate-spin" />
              {at("uiText.working")}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
        ) : null}
        </>
        )}
      </div>

      {/* INPUT AREA */}
      {!previewSectionsOnly && (
      <div className="p-6 bg-card dark:bg-[#0f172a] border-t border-slate-100 dark:border-slate-800 shadow-[0_-10px_20px_-10px_rgba(0,0,0,0.05)] relative z-10 flex-shrink-0">
        {pathname?.includes("/admin") && activeState && activeState.current_flow && activeState.current_flow !== "none" && progress && (
          <div className="mb-4 p-4 bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-800/80 rounded-2xl flex flex-col gap-2.5">
            <div className="flex items-center justify-between text-xs font-medium text-slate-700 dark:text-slate-300">
              <span className="font-semibold">{progress.flowLabel === "Setup Creation" ? uiText.setupWizard : progress.flowLabel}</span>
              <span className="text-slate-400 dark:text-slate-500">Stap {activeStep} van {progress.total}</span>
            </div>
            <div className="w-full h-1 bg-slate-100 dark:bg-slate-900 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-600 dark:bg-blue-500 rounded-full transition-all duration-500 ease-out"
                style={{ width: `${progress.percentage}%` }}
              />
            </div>
          </div>
        )}
          {isCommandSearchOpen ? (
            <FinnCommandCenter
              ref={commandCenterRef}
              isOpen={isOpen}
              query={activeQuery}
              request={effectiveCommandRequest}
              onQueryChange={updateVisibleQuery}
              onAskFinn={() => {
                const question = activeQuery;
                setManualCommandRequest(null);
                onCommandComplete?.();
                stashedComposerDraftRef.current = null;
                handleChat(question);
              }}
              onClose={leaveCommandSearch}
              watchlist={watchlist}
            />
          ) : null}
          {isCommandSearchOpen ? (
            <button type="button" onClick={leaveCommandSearch}
              className="mb-3 text-sm font-medium text-blue-600 hover:underline dark:text-blue-400">
              {at("uiText.backToChat")}
            </button>
          ) : null}
          <div className="relative group">
          {isSimpleFinnModal && showComposerMenu ? (
            <div className="absolute bottom-[calc(100%+10px)] left-0 z-20 w-60 overflow-hidden rounded-2xl border border-slate-200 bg-white p-1.5 shadow-xl shadow-slate-900/10 dark:border-slate-800 dark:bg-slate-950">
              <button
                type="button"
                onClick={() => {
                  enterCommandSearch("asset");
                }}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold text-slate-800 transition hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-900"
              >
                <Search size={17} className="text-slate-500" />
                {composerMenuCopy.asset}
              </button>
              <button
                type="button"
                onClick={() => {
                  enterCommandSearch("indicator");
                }}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold text-slate-800 transition hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-900"
              >
                <SlidersHorizontal size={17} className="text-slate-500" />
                {composerMenuCopy.indicator}
              </button>
            </div>
          ) : null}
          {isSimpleFinnModal ? (
            <button
              type="button"
              aria-label={composerMenuCopy.menu}
              aria-expanded={showComposerMenu}
              onClick={() => setShowComposerMenu((current) => !current)}
              className="absolute left-2.5 top-1/2 z-10 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <Plus size={22} className={`transition-transform ${showComposerMenu ? "rotate-45" : ""}`} />
            </button>
          ) : null}
          <textarea
            ref={composerInputRef}
            rows={1}
            value={activeQuery}
            onChange={(e) => {
              setShowComposerMenu(false);
              if (isFeedHandoff) setFeedDraftEdit({
                nonce: commandRequest?.nonce, value: e.target.value,
              });
              updateQuery(e.target.value);
            }}
            onKeyDown={(event) => {
              if (loading || activeStreamIdRef.current) return;
              if (isCommandSearchOpen && event.key === "Escape") { event.preventDefault(); leaveCommandSearch(); return; }
              if (!hasActiveFinnV2GuidedTurn && isSimpleFinnModal && isCommandSearchOpen && commandCenterRef.current?.handleKeyDown(event)) return;
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                handleChat();
              }
            }}
            placeholder={isSimpleFinnModal ? composerMenuCopy.placeholder : uiText.inputPlaceholder}
            className={`block max-h-40 min-h-[56px] w-full resize-none overflow-y-auto rounded-2xl border border-slate-100 bg-[var(--color-border-subtle)] py-4 pr-14 text-[15px] leading-6 text-foreground outline-none transition-all focus:border-blue-600/20 focus:bg-white focus:ring-4 focus:ring-blue-600/5 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:focus:bg-slate-800 ${isSimpleFinnModal ? "pl-14" : "pl-6"}`}
          />
          <button
            onClick={() => {
              if (loading) { stopCurrentResponse(); return; }
              if (!hasActiveFinnV2GuidedTurn && isSimpleFinnModal && isCommandSearchOpen && commandCenterRef.current?.submitPrimary()) return;
              handleChat();
            }}
            aria-label={loading ? at("uiText.stopResponse") : at("uiText.sendMessage")}
            disabled={!loading && !activeQuery.trim()}
            className="absolute bottom-3 right-3 rounded-xl bg-blue-600 p-2 text-white shadow-lg transition-all hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? <Square size={18} fill="currentColor" /> : <Send size={18} />}
          </button>
        </div>
      </div>
      )}
    </aside>
  );
}

export default function AIAssistant(props) {
  return (
    <Suspense fallback={null}>
      <AIAssistantContent {...props} />
    </Suspense>
  );
}
