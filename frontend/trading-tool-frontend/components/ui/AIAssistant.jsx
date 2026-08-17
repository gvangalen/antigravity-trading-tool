"use client";

import React, { Suspense, useState, useEffect, useLayoutEffect, useRef } from "react";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { assistantChat, executeAssistantAction, fetchAssistantInsight, getAssistantPreferences, getAssistantSessionDetail, getAssistantSessions, updateAssistantPreferences, assistantChatStream, executePendingAction, fetchFinnState, fetchFinnMissionControl } from "@/lib/api/ai";
import { Send, Zap, Brain, Shield, BarChart3, Loader2, X, MessageSquare, Target, Activity, FileText, Bot, ChevronDown, ListChecks, Terminal, Sparkles, CheckCircle2, Plus, Search, SlidersHorizontal } from "lucide-react";
import useIntelligenceEvents from "@/hooks/useIntelligenceEvents";
import { useOnboarding } from "@/hooks/useOnboarding";
import { ChatSkeleton } from "@/components/dashboard/DashboardSkeleton";
import { useAsset } from "@/app/providers/AssetProvider";
import { useAuth } from "@/components/auth/AuthProvider";
import { useWatchlist } from "@/hooks/useWatchlist";
import { useModal } from "@/components/modal/ModalProvider";
import { saveNewSetup, fetchSetups } from "@/lib/api/setups";
import { createStrategy, fetchStrategies } from "@/lib/api/strategy";
import { createBotConfig, fetchBotConfigs } from "@/lib/api/botApi";
import { getIndicatorConfig } from "@/lib/api/indicatorConfig";
import { fetchMacroData } from "@/lib/api/macro";
import { initializeAsset } from "@/lib/api/market";
import { technicalDataAll } from "@/lib/api/technical";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import { useActiveBot } from "@/app/providers/ActiveBotProvider";
import SetupForm from "@/components/setup/SetupForm";
import StrategyForm from "@/components/strategy/StrategyForm";
import AddBotForm from "@/components/bot/AddBotForm";
import { actionButtonStyles } from "@/components/ui/actionButtonStyles";
import Drawer from "@/components/ui/Drawer";
import { getAssistantSessionId, trackAssistantEvent } from "@/lib/api/assistantAnalytics";
import { normalizeScopedAssetSymbol, resolveFinnContextSymbol, shouldBlockFinnSubmission } from "@/lib/finnAssetIsolation";
import { normalizeTraderProfilePreferences } from "@/lib/traderProfileOptions";
import { useTranslation } from "@/app/providers/I18nProvider";
import FinnCommandCenter from "@/components/finn/FinnCommandCenter";
import { FINN_ASSETS } from "@/lib/finnCommandSearch";
import { getWorkspaceSnapshot, subscribeWorkspaceSnapshot } from "@/lib/workspaceSnapshotStore";

const INDICATOR_MODAL_OPEN_EVENT = "finn-indicator-config:open";
const INDICATOR_MODAL_COMPLETED_EVENT = "finn-indicator-config:completed";
const FINN_RECENT_CONVERSATIONS_STORAGE_KEY = "finn-recent-conversations:v1";
const MAX_RECENT_FINN_CONVERSATIONS = 3;
const ACTIVE_FINN_SESSION_ID_KEY = "active_finn_session_id";

function normalizeFinnSessionId(value) {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return normalized || null;
}

function scopedRecentConversationStorageKey(userId) {
  const scope = String(userId || "anonymous").trim() || "anonymous";
  return `${FINN_RECENT_CONVERSATIONS_STORAGE_KEY}:${scope}`;
}

function mapBackendSessionMessages(messages = []) {
  return (Array.isArray(messages) ? messages : [])
    .filter((message) => typeof message?.content === "string" && message.content.trim())
    .map((message) => ({
      role: message.role === "user" ? "user" : "assistant",
      text: message.content,
      isComplete: true,
    }));
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

function createAssistantTranslator(t) {
  const assistantCopy = t?.assistant || {};
  return (path, fallback = "", vars = {}) => interpolateTranslation(getDictionaryValue(assistantCopy, path) ?? fallback, vars);
}

function buildAssistantUiText(at) {
  return {
    activeBriefing: at("uiText.activeBriefing"),
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
    missionControlUnavailable: at("uiText.missionControlUnavailable"),
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
  const label = draft.display_name || String(indicatorName).toUpperCase();

  return {
    category,
    indicatorName,
    title: label,
    assetSymbol: symbol,
    responseText: `Ik heb ${label} voor ${symbol} klaargezet. Controleer de instellingen om hem toe te voegen.`,
  };
}

function getSetupMarketConditionLabel(condition, uiText) {
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
  const minMacro = Number(payload?.min_macro_score);
  const maxMacro = Number(payload?.max_macro_score);
  const minTechnical = Number(payload?.min_technical_score);
  const maxTechnical = Number(payload?.max_technical_score);
  const minMarket = Number(payload?.min_market_score);
  const maxMarket = Number(payload?.max_market_score);

  if ([minMacro, maxMacro, minTechnical, maxTechnical, minMarket, maxMarket].some((value) => Number.isNaN(value))) {
    return null;
  }

  if (minMacro === 40 && maxMacro === 100 && minTechnical === 55 && maxTechnical === 100 && minMarket === 35 && maxMarket === 100) {
    return "confirmed_strength";
  }
  if (minMacro === 30 && maxMacro === 70 && minTechnical === 40 && maxTechnical === 80 && minMarket === 20 && maxMarket === 60) {
    return "balanced_pullback";
  }
  if (minMacro === 10 && maxMacro === 65 && minTechnical === 20 && maxTechnical === 75 && minMarket === 10 && maxMarket === 55) {
    return "early_dip";
  }

  return null;
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
  queryValue,
  onQueryChange,
  autoFocusComposer = false,
  eventsEnabled = true,
  commandRequest = null,
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { selectedAsset: globalSymbol, assetStatus, setSelectedAsset } = useAsset();
  const { user } = useAuth();
  const router = useRouter();
  const watchlist = useWatchlist();
  const { showSnackbar } = useModal();
  const { t, locale } = useTranslation();
  const governanceCopy = t?.pages?.report?.finn?.governance || {};
  const { events, loading: eventsLoading, archiveEvent } = useIntelligenceEvents({
    enabled: eventsEnabled,
  });
  
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [preferences, setPreferences] = useState({});
  const [insight, setInsight] = useState(null);
  const [insightLoading, setInsightLoading] = useState(false);
  const [stableBriefingText, setStableBriefingText] = useState("");
  const [workspaceSnapshot, setWorkspaceSnapshot] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [activeState, setActiveState] = useState(null);
  const [contextMetric, setContextMetric] = useState(null);
  const [finnDraft, setFinnDraft] = useState(null);
  const [missionControl, setMissionControl] = useState(null);
  const [missionControlLoadError, setMissionControlLoadError] = useState(null);
  const [missionControlLoading, setMissionControlLoading] = useState(false);
  const [executingAction, setExecutingAction] = useState(false);
  const [missionDetailSection, setMissionDetailSection] = useState("");
  const [recentConversations, setRecentConversations] = useState([]);
  const [showComposerMenu, setShowComposerMenu] = useState(false);
  const [draftDrawer, setDraftDrawer] = useState(null);
  const [activeFinnSessionId, setActiveFinnSessionId] = useState(null);
  const [availableFinnSessions, setAvailableFinnSessions] = useState([]);
  
  const messagesEndRef = useRef(null);
  const scrollRef = useRef(null);
  const composerInputRef = useRef(null);
  const commandCenterRef = useRef(null);
  const draftFormRef = useRef(null);
  const handledContextRequestRef = useRef(null);
  const loadedFinnStateRef = useRef(false);
  const insightCacheKeyRef = useRef("");
  const missionControlCacheKeyRef = useRef("");
  const activeStreamIdRef = useRef(null);
  const profileTelemetryKeyRef = useRef("");
  const missionControlRequestRef = useRef(null);
  const missionControlRequestKeyRef = useRef("");
  const insightRequestRef = useRef(null);
  const insightRequestKeyRef = useRef("");
  const finnStateRequestRef = useRef(null);
  const sharedSessionRestoreRef = useRef(false);
  const [showReasoning, setShowReasoning] = useState(false);
  const at = createAssistantTranslator(t);
  const activeQuery = queryValue !== undefined ? queryValue : query;
  const updateQuery = onQueryChange || setQuery;
  const isSimpleFinnModal = modal;
  const activeVariant = searchParams.get("variant") === "legacy" ? "legacy" : "v3";
  const isAssetAnalysisPage = pathname === "/asset";
  const userScopedRecentConversationStorageKey = React.useMemo(
    () => scopedRecentConversationStorageKey(user?.id),
    [user?.id],
  );

  const composerMenuCopy = {
    asset: at("uiText.composerAsset"),
    indicator: at("uiText.composerIndicator"),
    placeholder: at("uiText.composerInstruction"),
    menu: at("uiText.composerMenu"),
  };

  const humanizeSurfaceStatus = (value) => {
    const raw = String(value || "").toLowerCase();
    if (!raw) return at("surfaceStatus.quiet");
    if (raw.includes("active")) return at("surfaceStatus.active");
    if (raw.includes("quiet")) return at("surfaceStatus.quiet");
    if (raw.includes("early")) return at("surfaceStatus.early");
    if (raw.includes("high")) return at("surfaceStatus.high");
    if (raw.includes("stable")) return at("surfaceStatus.stable");
    if (raw.includes("guarded")) return at("surfaceStatus.guarded");
    if (raw.includes("defensive")) return at("surfaceStatus.defensive");
    if (raw.includes("balanced")) return at("surfaceStatus.balanced");
    return value;
  };

  const uiText = buildAssistantUiText(at);

  useEffect(() => {
    setPreferences({});
    setMessages([]);
    setInsight(null);
    setStableBriefingText("");
    setWorkspaceSnapshot(null);
    setLastUpdated(null);
    setActiveState(null);
    setContextMetric(null);
    setFinnDraft(null);
    setMissionControl(null);
    setMissionControlLoadError(null);
    setMissionControlLoading(false);
    setRecentConversations([]);
    setDraftDrawer(null);
    setActiveFinnSessionId(null);
    setAvailableFinnSessions([]);
    handledContextRequestRef.current = null;
    loadedFinnStateRef.current = false;
    insightCacheKeyRef.current = "";
    missionControlCacheKeyRef.current = "";
    missionControlRequestRef.current = null;
    missionControlRequestKeyRef.current = "";
    insightRequestRef.current = null;
    insightRequestKeyRef.current = "";
    finnStateRequestRef.current = null;
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

      loadInsight();
      loadMissionControl();
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
  const { stepStatus, onboardingComplete, dashboardReady } = useOnboarding();
  const isOnboarding = (pathname.includes("onboarding") || !onboardingComplete) && pathname !== "/dashboard";

  useEffect(() => {
    if (!isOpen) return;
    setShowComposerMenu(false);
    setMissionDetailSection("");
    if (pathname !== "/asset") {
      setStableBriefingText("");
    }
  }, [isOpen, pathname]);

  useEffect(() => {
    if (!isOpen || previewSectionsOnly || !autoFocusComposer) return;
    const frame = window.requestAnimationFrame(() => {
      composerInputRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [isOpen, previewSectionsOnly, autoFocusComposer]);

  const getMetricTitle = (metric) => {
    const titles = {
      transition_risk: at("metricTitles.transition_risk"),
      setup_quality: at("metricTitles.setup_quality"),
      market_pressure: at("metricTitles.market_pressure"),
      structural_cycle: at("metricTitles.structural_cycle"),
      position_size: at("metricTitles.position_size"),
      trend_strength: at("metricTitles.trend_strength"),
    };
    return titles[metric] || at("metricTitles.default");
  };

  const getMetricAnalysisText = (metric, symbol = "BTC", tf = "1W") => {
    switch (metric) {
      case "transition_risk":
        return at("metricAnalysis.transition_risk", "", { symbol, tf });
      case "setup_quality":
        return at("metricAnalysis.setup_quality", "", { symbol, tf });
      case "market_pressure":
        return at("metricAnalysis.market_pressure", "", { symbol, tf });
      case "structural_cycle":
        return at("metricAnalysis.structural_cycle", "", { symbol, tf });
      case "position_size":
        return at("metricAnalysis.position_size", "", { symbol, tf });
      case "trend_strength":
        return at("metricAnalysis.trend_strength", "", { symbol, tf });
      default:
        return at("metricAnalysis.default", "", { symbol, tf });
    }
  };

  const reviewIdentityKey = (item) => {
    if (!item || typeof item !== "object") return null;
    if (item.decision_id) return `decision:${item.decision_id}`;
    const sourceDecisionId = item?.source_ids?.decision_id;
    if (sourceDecisionId) return `decision:${sourceDecisionId}`;
    const botId = item?.bot_id || item?.source_ids?.bot_id;
    const asset = String(item?.asset || item?.source_ids?.asset || "").trim().toUpperCase();
    const issueType = String(item?.type || item?.status || item?.resolve_state || item?.label || "review").trim().toLowerCase();
    if (botId) return `bot:${botId}:${asset}:${issueType}`;
    return item?.id || `${asset}:${issueType}:${item?.title || item?.reason || "review"}`;
  };

  const isReviewCandidate = (item) => {
    const type = String(item?.type || "").toLowerCase();
    const status = String(item?.status || item?.resolve_state || "").toLowerCase();
    return Boolean(
      item?.decision_id ||
      type.includes("bot_decision") ||
      status.includes("review") ||
      String(item?.title || "").toLowerCase().includes("review")
    );
  };

  const getOpenReviewCandidates = (currentMissionControl) => {
    return [
      ...((currentMissionControl?.bot_review_queue || []).filter(Boolean)),
      ...((currentMissionControl?.workqueue || []).filter((item) => isReviewCandidate(item))),
    ];
  };

  const countUniqueReviewCandidates = (currentMissionControl) => {
    const seen = new Set();
    let count = 0;
    for (const item of getOpenReviewCandidates(currentMissionControl)) {
      const key = reviewIdentityKey(item);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      count += 1;
    }
    return count;
  };

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

  const normalizeListValue = (value) => {
    if (Array.isArray(value)) return value.filter(Boolean);
    if (typeof value === "string" && value.trim()) return [value];
    return [];
  };

  const isInvestorLike = traderTypes.some((type) => ["investor", "dca_investor"].includes(type));
  const isSwingLike = traderTypes.includes("swing_trader");
  const isIntradayLike = traderTypes.some((type) => ["day_trader", "scalper"].includes(type));
  const isConservative = profileRisk.includes("conservative");
  const isBeginner = profileExperience.includes("beginner");

  const buildTraderProfileUiSummary = () => {
    if (!hasTraderProfile) return "";
    const leadType = traderTypes.map((type) => traderTypeLabelMap[type]).filter(Boolean).slice(0, 2).join(" + ");
    const leadTimeframes = profileTimeframes.map((tf) => String(tf).toUpperCase()).slice(0, 2).join("/");
    const leadRisk = profileRisk.map((risk) => riskLabelMap[risk]).filter(Boolean)[0];
    const leadAsset = profileAssetFocus.map((asset) => assetFocusLabelMap[asset]).filter(Boolean)[0];
    return [leadType, leadTimeframes, leadRisk || leadAsset].filter(Boolean).join(" • ");
  };

  const profileSummaryLabel = buildTraderProfileUiSummary();
  const behaviorFlagLabelMap = {
    fomo: "FOMO",
    overtrades: at("labels.behaviorFlags.overtrades"),
    leverage_seeking: at("labels.behaviorFlags.leverage_seeking"),
    holds_losers_too_long: at("labels.behaviorFlags.holds_losers_too_long"),
    takes_profit_too_early: at("labels.behaviorFlags.takes_profit_too_early"),
  };

  const humanizeBehaviorFlagLabel = (flag, fallbackLabel = "") =>
    fallbackLabel || behaviorFlagLabelMap[String(flag || "").trim()] || String(flag || "").replace(/_/g, " ");

  const pickPrimaryProfileHabitAlignment = (sourceMissionControl = null) => {
    if (!sourceMissionControl || typeof sourceMissionControl !== "object") return null;
    return (
      sourceMissionControl?.profile_habit_alignment?.primary_alignment ||
      sourceMissionControl?.priority_engine?.profile_habit_alignment?.primary_alignment ||
      sourceMissionControl?.portfolio_operating_system?.governance_layer?.profile_habit_alignment?.primary_alignment ||
      null
    );
  };

  const scoreMissionForProfile = (item) => {
    if (!item) return 0;
    let score = 0;
    const asset = String(item.asset || item.symbol || "").toLowerCase();
    const setupType = String(item.setup_type || item.setupType || item.type || "").toLowerCase();
    const timeframe = String(item.setup_timeframe || item.timeframe || item.tf || "").toLowerCase();
    const title = String(item.title || "").toLowerCase();
    const reason = String(item.reason || item.summary || "").toLowerCase();

    if (profileAssetFocus.includes("bitcoin") && asset === "btc") score += 3;
    if (profileAssetFocus.includes("crypto_general") && ["btc", "eth", "sol"].includes(asset)) score += 2;
    if (profileTimeframes.length > 0 && timeframe) {
      if (profileTimeframes.includes(timeframe)) score += 3;
      else if (profileTimeframes.map((tf) => tf.replace("1", "")).includes(timeframe.replace("1", ""))) score += 2;
    }
    if (traderTypes.includes("dca_investor") && (setupType.includes("dca") || title.includes("dca") || reason.includes("dca"))) score += 4;
    if (isSwingLike && (timeframe.includes("4h") || timeframe.includes("1d") || title.includes("swing"))) score += 3;
    if (isIntradayLike && (timeframe.includes("5m") || timeframe.includes("15m") || timeframe.includes("1h"))) score += 3;
    if (isInvestorLike && (timeframe.includes("1w") || timeframe.includes("1m"))) score += 2;
    if (isConservative && (String(item.status || "").toLowerCase().includes("blocked") || reason.includes("risico"))) score += 2;
    if (isBeginner && isReviewCandidate(item)) score += 1;
    return score;
  };

  const buildBriefingText = (sourceInsight) => {
    const openReviews = countUniqueReviewCandidates(missionControl);
    const blockedCount = Number(missionControl?.summary?.blocked_count || 0);
    const greetingName = user?.first_name || "Trader";
    const primaryItem = primaryCoachingItem || missionControl?.bot_review_queue?.[0] || missionControl?.workqueue?.[0] || null;
    const symbol = String(
      isAssetAnalysisPage
        ? context?.symbol || globalSymbol || primaryItem?.asset || "BTC"
        : primaryItem?.asset || context?.symbol || globalSymbol || "BTC"
    ).trim().toUpperCase();
    const postureLabel = String(
      missionControl?.summary?.posture ||
      sourceInsight?.market_insight?.posture ||
      sourceInsight?.bot_insight?.posture ||
      ""
    ).toLowerCase();
    const cycleLabel = String(
      sourceInsight?.market_insight?.structural_cycle ||
      sourceInsight?.market_insight?.cycle ||
      sourceInsight?.market_insight?.regime ||
      ""
    ).toLowerCase();
    const nowHour = new Date().getHours();

    const greetingKey = nowHour < 12 ? "morning" : nowHour < 18 ? "afternoon" : "evening";
    const greetingLine = `${at(`briefing.greeting.${greetingKey}`, "", { name: greetingName })} ${greetingName}.`;

    let marketLine = at("briefing.market.default", "", { symbol });
    if (isInvestorLike) {
      marketLine = cycleLabel.includes("correction") || postureLabel.includes("defensive") || postureLabel.includes("action_required")
        ? at("briefing.market.investor.correction", "", { symbol })
        : at("briefing.market.investor.steady", "", { symbol });
    } else if (isSwingLike) {
      marketLine = cycleLabel.includes("correction") || postureLabel.includes("defensive") || postureLabel.includes("action_required")
        ? at("briefing.market.swing.correction", "", { symbol })
        : at("briefing.market.swing.steady", "", { symbol });
    } else if (isIntradayLike) {
      marketLine = cycleLabel.includes("correction") || postureLabel.includes("defensive") || postureLabel.includes("action_required")
        ? at("briefing.market.intraday.correction", "", { symbol })
        : at("briefing.market.intraday.steady", "", { symbol });
    } else if (cycleLabel.includes("correction") || postureLabel.includes("defensive") || postureLabel.includes("action_required")) {
      marketLine = at("briefing.market.generic.correction", "", { symbol });
    } else if (cycleLabel.includes("recovery") || postureLabel.includes("stable")) {
      marketLine = at("briefing.market.generic.recovery", "", { symbol });
    } else if (cycleLabel.includes("distribution")) {
      marketLine = at("briefing.market.generic.distribution", "", { symbol });
    }

    const reviewCount = Math.max(openReviews || 0, isReviewCandidate(primaryItem) ? 1 : 0);
    let reviewLine = at("briefing.review.none");
    if (reviewCount === 1) {
      reviewLine = at("briefing.review.one");
    } else if (reviewCount > 1) {
      reviewLine = at("briefing.review.many", "", { count: reviewCount });
    } else if (blockedCount > 0) {
      reviewLine = blockedCount === 1
        ? at("briefing.review.blockingOne")
        : at("briefing.review.blockingMany", "", { count: blockedCount });
    }

    const beginTarget = primaryItem
      ? humanizeMissionTitle(primaryItem).replace(/^Review\s+/i, "Review ")
      : blockedCount > 0
        ? at("briefing.begin.blockingIssue")
        : at("briefing.begin.nextSafeStep");
    const beginLine = at("briefing.begin.prefix", "", { target: beginTarget });

    return [greetingLine, marketLine, reviewLine, beginLine].filter(Boolean).join("\n");
  };

  const buildSnapshotBriefingText = (snapshot) => {
    const greetingName = user?.first_name || "Trader";
    const symbol = String(
      snapshot?.symbol ||
      snapshot?.asset?.symbol ||
      context?.symbol ||
      globalSymbol ||
      "BTC"
    ).trim().toUpperCase();
    const nowHour = new Date().getHours();
    const greetingKey = nowHour < 12 ? "morning" : nowHour < 18 ? "afternoon" : "evening";
    const greetingLine = `${at(`briefing.greeting.${greetingKey}`, "", { name: greetingName })} ${greetingName}.`;
    const finnSnapshot = snapshot?.finn || {};
    const freshness = finnSnapshot?.freshness || {};
    const headline = String(finnSnapshot?.headline || finnSnapshot?.summary || "").trim();
    const riskSummary = String(finnSnapshot?.risk_summary || "").trim();
    const asOfLine = freshness?.as_of
      ? `Laatste analyse van ${new Date(freshness.as_of).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.`
      : "Laatste analyse uit je opgeslagen snapshot.";

    if (headline) {
      return [
        greetingLine,
        headline,
        riskSummary || asOfLine,
        freshness?.stale ? "Nieuwe marktgegevens worden op de achtergrond verwerkt." : asOfLine,
      ]
        .filter(Boolean)
        .join("\n");
    }

    return [
      greetingLine,
      at("briefing.market.default", "", { symbol }),
      "Laatste analyse nog niet beschikbaar.",
      "Nieuwe marktgegevens worden verwerkt.",
    ].join("\n");
  };

  // Helper to get nested insight consistently
  const getInsightField = (block, field) => {
    return insight?.[block]?.[field] || insight?.[block.replace('_insight', '')]?.[field];
  };

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
    const routeSymbol = normalizeScopedAssetSymbol(searchParams.get("symbol") || searchParams.get("asset"));
    const resolvedWorkspaceSymbol = resolveFinnContextSymbol({
      urlSymbol: routeSymbol,
      activeSetupSymbol: activeSetup?.symbol,
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
      page_type: pageMap[pathname] || t?.common?.unknown || "Unknown",
      symbol: resolvedWorkspaceSymbol,
      asset_resolution_status: assetStatus,
      timeframe:
        searchParams.get("tf") ||
        searchParams.get("interval") ||
        (pathname.includes("dashboard") || pathname === "/"
          ? t?.common?.week || "Week"
          : t?.common?.day || "Day"),
      setup_id: activeSetup?.id || activeSetup?.setup_id || null,
      setup_type: activeSetup?.setup_type || activeSetup?.type || null,
      setup_symbol: activeSetup?.symbol || null,
      setup_timeframe: activeSetup?.timeframe || null,
      bot_id: activeBot?.id || activeBot?.bot_id || focusedBotId || null,
      strategy_id: activeSetup?.strategy_id || null,
      setup_name: searchParams.get("name") || activeSetup?.name || t?.common?.none || "None",
      finn_draft: finnDraft,
    };
  };

  const context = getContext();
  const skipNextFinnRestoreRef = useRef(null);
  const currentConversationStorageKey = React.useMemo(() => {
    const userScope = String(user?.id || "anonymous");
    const section = String(context.page_type || pathname || "overview").toLowerCase();
    const asset = normalizeScopedAssetSymbol(context.symbol || globalSymbol) || "UNKNOWN";
    const timeframe = String(context.timeframe || "Day").toLowerCase();
    return `${userScope}:${section}:${asset}:${timeframe}`;
  }, [user?.id, context.page_type, context.symbol, context.timeframe, pathname, globalSymbol]);

  useEffect(() => {
    insightCacheKeyRef.current = `finn-insight:${currentConversationStorageKey}`;
    const missionControlSymbol = normalizeScopedAssetSymbol(globalSymbol || context.symbol) || "UNKNOWN";
    missionControlCacheKeyRef.current = `finn-mission-control:${currentConversationStorageKey}:${pathname || "/assistant"}:${missionControlSymbol}`;
  }, [currentConversationStorageKey, pathname, globalSymbol, context.symbol]);

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

  const normalizeFollowUpActions = (items = []) => {
    if (!Array.isArray(items)) return [];
    return items
      .map((item) => {
        if (typeof item === "string") {
          return { label: item, prompt: item, handoff: "chat", type: "chat_prompt" };
        }
        const prompt = item?.prompt || item?.label || item?.title;
        if (!prompt) return null;
        return {
          label: item.label || prompt,
          prompt,
          handoff: item.handoff || item.flow || "chat",
          type: item.type || "chat_prompt",
          requiresConfirmation: Boolean(item.requires_confirmation),
          source: item.source,
        };
      })
      .filter(Boolean)
      .slice(0, 5);
  };

  const getSetupFlowSlots = (state = {}) => {
    const rawSlots = state?.slots || {};
    return {
      symbol: rawSlots.symbol || state?.asset || state?.symbol || null,
      setup_type: rawSlots.setup_type || state?.setup_type || null,
      timeframe: rawSlots.timeframe || state?.timeframe || null,
      name: rawSlots.name || state?.name || null,
      dca_frequency: rawSlots.dca_frequency || state?.dca_frequency || null,
      dca_day: rawSlots.dca_day || state?.dca_day || null,
      dca_month_day: rawSlots.dca_month_day || state?.dca_month_day || null,
      market_condition: rawSlots.market_condition || state?.market_condition || null,
    };
  };

  const getMissingSetupSlots = (slots = {}) => {
    const missing = [];
    if (!slots.setup_type) {
      missing.push("setup_type");
      return missing;
    }
    if (!slots.timeframe) {
      missing.push("timeframe");
    }
    if (!slots.name) {
      missing.push("name");
    }
    if (String(slots.setup_type || "").toLowerCase() === "dca") {
      if (!slots.dca_frequency) {
        missing.push("dca_frequency");
      } else if (slots.dca_frequency === "weekly" && !slots.dca_day) {
        missing.push("dca_day");
      } else if (slots.dca_frequency === "monthly" && !slots.dca_month_day) {
        missing.push("dca_month_day");
      }
    }
    if (!slots.market_condition) {
      missing.push("market_condition");
    }
    return missing;
  };

  const getEffectiveSetupNextQuestion = (state = {}) => {
    const slots = getSetupFlowSlots(state);
    const missing = getMissingSetupSlots(slots);
    const declaredNext = state?.next_question || null;

    if (missing.length === 0) {
      return declaredNext;
    }
    if (declaredNext && missing.includes(declaredNext)) {
      return declaredNext;
    }
    if (
      declaredNext &&
      [
        "min_macro_score",
        "max_macro_score",
        "min_technical_score",
        "max_technical_score",
        "min_market_score",
        "max_market_score",
      ].includes(declaredNext) &&
      missing.includes("market_condition")
    ) {
      return "market_condition";
    }
    return missing[0];
  };

  const getStrategyFlowSlots = (state = {}) => {
    const rawSlots = state?.slots || {};
    return {
      symbol: rawSlots.symbol || state?.asset || state?.symbol || null,
      setup_id: rawSlots.setup_id || state?.setup_id || null,
      setup_name: rawSlots.setup_name || state?.setup_name || null,
      setup_type: rawSlots.setup_type || state?.setup_type || null,
      timeframe: rawSlots.timeframe || state?.timeframe || null,
      name: rawSlots.name || rawSlots.strategy_name || state?.name || state?.strategy_name || null,
      base_amount: rawSlots.base_amount || rawSlots.base_amount_eur || state?.base_amount || state?.base_amount_eur || null,
      base_amount_eur: rawSlots.base_amount_eur || rawSlots.base_amount || state?.base_amount_eur || state?.base_amount || null,
      execution_mode: rawSlots.execution_mode || state?.execution_mode || null,
      risk_profile: rawSlots.risk_profile || rawSlots.risk_mode || state?.risk_profile || state?.risk_mode || null,
      risk_mode: rawSlots.risk_mode || rawSlots.risk_profile || state?.risk_mode || state?.risk_profile || null,
      entry_type: rawSlots.entry_type || state?.entry_type || null,
      entry: rawSlots.entry || state?.entry || null,
      stop_loss: rawSlots.stop_loss || state?.stop_loss || null,
      targets: rawSlots.targets || state?.targets || null,
      automation: rawSlots.automation || state?.automation || null,
    };
  };

  const getMissingStrategySlots = (slots = {}) => {
    const missing = [];
    if (!slots.setup_id) {
      missing.push("setup_id");
      return missing;
    }
    if (!slots.base_amount_eur && !slots.base_amount) {
      missing.push("strategy.base_amount_eur");
      return missing;
    }
    if (!slots.execution_mode) {
      missing.push("strategy.execution_mode");
      return missing;
    }
    if (!slots.risk_profile && !slots.risk_mode) {
      missing.push("strategy.risk_profile");
    }
    return missing;
  };

  const getEffectiveStrategyNextQuestion = (state = {}) => {
    const slots = getStrategyFlowSlots(state);
    const missing = getMissingStrategySlots(slots);
    const declaredNext = state?.next_question || null;

    if (missing.length === 0) {
      return declaredNext;
    }
    if (declaredNext && missing.includes(declaredNext)) {
      return declaredNext;
    }
    if (declaredNext === "base_amount" && missing.includes("strategy.base_amount_eur")) {
      return "strategy.base_amount_eur";
    }
    return missing[0];
  };

  const getBotFlowSlots = (state = {}) => {
    const rawSlots = state?.slots || {};
    return {
      symbol: rawSlots.symbol || state?.asset || state?.symbol || null,
      name: rawSlots.name || state?.name || null,
      strategy_id: rawSlots.strategy_id || state?.strategy_id || null,
      budget_total_eur: rawSlots.budget_total_eur || state?.budget_total_eur || null,
      budget_daily_limit_eur: rawSlots.budget_daily_limit_eur || state?.budget_daily_limit_eur || null,
    };
  };

  const getMissingBotSlots = (slots = {}) => {
    const missing = [];
    if (!slots.name) {
      missing.push("name");
    }
    if (!slots.budget_total_eur) {
      missing.push("budget_total_eur");
    }
    if (!slots.budget_daily_limit_eur) {
      missing.push("budget_daily_limit_eur");
    }
    return missing;
  };

  const getEffectiveBotNextQuestion = (state = {}) => {
    const slots = getBotFlowSlots(state);
    const missing = getMissingBotSlots(slots);
    const declaredNext = state?.next_question || null;

    if (missing.length === 0) {
      return declaredNext;
    }
    if (declaredNext && missing.includes(declaredNext)) {
      return declaredNext;
    }
    return missing[0];
  };

  const buildTransactionalFollowUpActions = (message) => {
    const state = message?.state;
    if (!state?.current_flow) return [];
    const flow = state.current_flow;
    const slots =
      flow === "strategy_creation"
        ? getStrategyFlowSlots(state)
        : flow === "bot_creation"
          ? getBotFlowSlots(state)
        : getSetupFlowSlots(state);
    const nextQuestion =
      flow === "strategy_creation"
        ? getEffectiveStrategyNextQuestion(state)
        : flow === "bot_creation"
          ? getEffectiveBotNextQuestion(state)
        : getEffectiveSetupNextQuestion(state);
    const symbol = slots.symbol || context.symbol || globalSymbol || "BTC";

    if (!["setup_creation", "strategy_creation", "bot_creation"].includes(flow)) return [];

    if (flow === "strategy_creation") {
      const bySlot = {
        setup_id: [
          {
            label: at("followUps.strategy.chooseSetup", "Gebruik mijn setup"),
            prompt: at(
              "followUps.strategy.chooseSetupPrompt",
              `Gebruik mijn bestaande ${symbol} setup als basis voor deze strategie.`
            ),
          },
        ],
        "strategy.base_amount_eur": [
          {
            label: at("followUps.strategy.amount100", "100 euro per keer"),
            prompt: at("followUps.strategy.amount100Prompt", "Gebruik 100 euro per uitvoering."),
          },
          {
            label: at("followUps.strategy.amount250", "250 euro per keer"),
            prompt: at("followUps.strategy.amount250Prompt", "Gebruik 250 euro per uitvoering."),
          },
        ],
        base_amount: [
          {
            label: at("followUps.strategy.amount100", "100 euro per keer"),
            prompt: at("followUps.strategy.amount100Prompt", "Gebruik 100 euro per uitvoering."),
          },
          {
            label: at("followUps.strategy.amount250", "250 euro per keer"),
            prompt: at("followUps.strategy.amount250Prompt", "Gebruik 250 euro per uitvoering."),
          },
        ],
        "strategy.execution_mode": [
          {
            label: at("followUps.strategy.executionManual", "Handmatig uitvoeren"),
            prompt: at("followUps.strategy.executionManualPrompt", "Voer deze strategie handmatig uit."),
          },
          {
            label: at("followUps.strategy.executionAutomatic", "Automatisch uitvoeren"),
            prompt: at("followUps.strategy.executionAutomaticPrompt", "Laat deze strategie automatisch meelopen via een bot."),
          },
        ],
        "strategy.risk_profile": [
          {
            label: at("followUps.strategy.riskConservative", "Conservatief"),
            prompt: at("followUps.strategy.riskConservativePrompt", "Gebruik een conservatief risicoprofiel."),
          },
          {
            label: at("followUps.strategy.riskBalanced", "Gebalanceerd"),
            prompt: at("followUps.strategy.riskBalancedPrompt", "Gebruik een gebalanceerd risicoprofiel."),
          },
          {
            label: at("followUps.strategy.riskAggressive", "Agressief"),
            prompt: at("followUps.strategy.riskAggressivePrompt", "Gebruik een agressief risicoprofiel."),
          },
        ],
      };

      if (state?.status === "collecting" && nextQuestion && bySlot[nextQuestion]) {
        return normalizeFollowUpActions(bySlot[nextQuestion]);
      }

      if (state?.status === "collecting") {
        return [];
      }

      if (state?.can_confirm) {
        return normalizeFollowUpActions([
          {
            label: at("followUps.strategy.review", "Strategie controleren"),
            prompt: at("followUps.strategy.reviewPrompt", "Controleer de strategie en maak hem aan als alles klopt."),
          },
        ]);
      }

      if (message?.intent === "strategy_created") {
        return normalizeFollowUpActions([
          at("followUps.strategy.review", `Bekijk je strategie voor ${symbol}`),
          at("followUps.strategy.nextBot", `Ga door naar bot voor ${symbol}`),
        ]);
      }

      return [];
    }

    if (flow === "bot_creation") {
      const bySlot = {
        name: [
          {
            label: at("followUps.bot.defaultName", `${symbol} Bot`),
            prompt: at("followUps.bot.defaultNamePrompt", `Noem de bot ${symbol} Bot.`),
          },
        ],
        budget_total_eur: [
          {
            label: at("followUps.bot.totalBudget250", "250 euro totaal"),
            prompt: at("followUps.bot.totalBudget250Prompt", "Gebruik 250 euro als totaal budget."),
          },
          {
            label: at("followUps.bot.totalBudget500", "500 euro totaal"),
            prompt: at("followUps.bot.totalBudget500Prompt", "Gebruik 500 euro als totaal budget."),
          },
        ],
        budget_daily_limit_eur: [
          {
            label: at("followUps.bot.dailyLimit25", "25 euro per dag"),
            prompt: at("followUps.bot.dailyLimit25Prompt", "Gebruik 25 euro als daglimiet."),
          },
          {
            label: at("followUps.bot.dailyLimit50", "50 euro per dag"),
            prompt: at("followUps.bot.dailyLimit50Prompt", "Gebruik 50 euro als daglimiet."),
          },
        ],
      };

      if (state?.status === "collecting" && nextQuestion && bySlot[nextQuestion]) {
        return normalizeFollowUpActions(bySlot[nextQuestion]);
      }

      if (state?.status === "collecting") {
        return [];
      }

      if (message?.intent === "bot_created") {
        return normalizeFollowUpActions([
          at("followUps.bot.review", `Bekijk je bot voor ${symbol}`),
          at("followUps.bot.goDashboard", "Ga naar dashboard"),
        ]);
      }

      return [];
    }

    const setupType = String(slots.setup_type || "").toLowerCase();
    const marketConditionActions = [
      { label: uiText.followUpConfirmedStrength, prompt: uiText.followUpConfirmedStrengthPrompt.replace("{symbol}", symbol) },
      { label: uiText.followUpBalancedPullback, prompt: uiText.followUpBalancedPullbackPrompt.replace("{symbol}", symbol) },
      { label: uiText.followUpEarlyDip, prompt: uiText.followUpEarlyDipPrompt.replace("{symbol}", symbol) },
    ];

    const bySlot = {
      setup_type: [
        { label: uiText.followUpChooseDca, prompt: uiText.followUpChooseDcaPrompt.replace("{symbol}", symbol) },
        { label: uiText.followUpChooseTrade, prompt: uiText.followUpChooseTradePrompt.replace("{symbol}", symbol) },
      ],
      dca_frequency: [
        { label: uiText.followUpDaily, prompt: uiText.followUpDailyPrompt },
        { label: uiText.followUpWeekly, prompt: uiText.followUpWeeklyPrompt },
        { label: uiText.followUpMonthly, prompt: uiText.followUpMonthlyPrompt },
      ],
      dca_day: [
        { label: uiText.followUpMonday, prompt: uiText.followUpMondayPrompt },
        { label: uiText.followUpTuesday, prompt: uiText.followUpTuesdayPrompt },
        { label: uiText.followUpWednesday, prompt: uiText.followUpWednesdayPrompt },
      ],
      dca_month_day: [
        { label: uiText.followUpFirstOfMonth, prompt: uiText.followUpFirstOfMonthPrompt },
        { label: uiText.followUpFifthOfMonth, prompt: uiText.followUpFifthOfMonthPrompt },
        { label: uiText.followUpFifteenthOfMonth, prompt: uiText.followUpFifteenthOfMonthPrompt },
      ],
      timeframe:
        setupType === "dca"
          ? [
              { label: uiText.followUpWeeklyTimeframe, prompt: uiText.followUpWeeklyTimeframePrompt },
              { label: uiText.followUpMonthlyTimeframe, prompt: uiText.followUpMonthlyTimeframePrompt },
            ]
          : [
              { label: uiText.followUpFourHourTimeframe, prompt: uiText.followUpFourHourTimeframePrompt },
              { label: uiText.followUpDailyTimeframe, prompt: uiText.followUpDailyTimeframePrompt },
            ],
      name: [
        {
          label: uiText.followUpNameSetup,
          prompt: setupType === "dca"
            ? uiText.followUpNameDcaExample.replace("{symbol}", symbol)
            : uiText.followUpNameTradeExample.replace("{symbol}", symbol),
        },
      ],
      market_condition: marketConditionActions,
      min_macro_score: marketConditionActions,
      max_macro_score: marketConditionActions,
      min_technical_score: marketConditionActions,
      max_technical_score: marketConditionActions,
      min_market_score: marketConditionActions,
      max_market_score: [
        { label: uiText.followUpFinalizeSetup, prompt: uiText.followUpFinalizeSetupPrompt },
      ],
    };

    if (state?.status === "collecting" && nextQuestion && bySlot[nextQuestion]) {
      return normalizeFollowUpActions(bySlot[nextQuestion]);
    }

    if (state?.status === "collecting") {
      return [];
    }

    if (message?.intent === "plan_created" || message?.intent === "setup_created") {
      return normalizeFollowUpActions([
        `Bekijk je setup voor ${symbol}`,
        `Ga door naar strategie voor ${symbol}`,
      ]);
    }

    return [];
  };

  const getMessageFollowUpActions = (message) => {
    if (Array.isArray(message?.actions) && message.actions.some((action) => action?.requires_confirmation)) {
      return [];
    }
    const transactionalActions = buildTransactionalFollowUpActions(message);
    if (transactionalActions.length > 0) {
      return transactionalActions;
    }
    if (
      ["setup_creation", "strategy_creation", "bot_creation"].includes(message?.state?.current_flow) &&
      message?.state?.status === "collecting"
    ) {
      return [];
    }
    const controllerAction = message?.state?.analysis?.agent_controller?.primary_action || message?.state?.agent_controller?.primary_action;
    const structured = message?.state?.analysis?.follow_up_actions;
    if (Array.isArray(structured) && structured.length > 0) {
      return normalizeFollowUpActions([controllerAction, ...structured].filter(Boolean));
    }
    if (Array.isArray(message?.suggestedActions) && message.suggestedActions.length > 0) {
      return normalizeFollowUpActions([controllerAction, ...message.suggestedActions].filter(Boolean));
    }
    return normalizeFollowUpActions([controllerAction, ...parseSuggestedActions(message?.text)].filter(Boolean));
  };

  const getMessageSummary = (message) => (
    message?.summary ||
    message?.state?.analysis?.summary ||
    message?.analysis?.summary ||
    null
  );

  const getMessageRiskSummary = (message) => (
    message?.riskSummary ||
    message?.risk_summary ||
    message?.state?.analysis?.risk_summary ||
    message?.analysis?.risk_summary ||
    null
  );

  const getMessageNextBestAction = (message) => (
    message?.nextBestAction ||
    message?.next_best_action ||
    message?.state?.analysis?.next_best_action ||
    message?.analysis?.next_best_action ||
    message?.state?.analysis?.operator_next_step ||
    message?.analysis?.operator_next_step ||
    null
  );

  const getMessageReviewReason = (message) => (
    message?.reviewReason ||
    message?.review_reason ||
    message?.state?.analysis?.review_reason ||
    message?.analysis?.review_reason ||
    null
  );

  const shouldRenderOperatorReadout = (message) => {
    if (message?.role !== "assistant" || message?.isComplete === false) return false;
    if (getMessageOperatorResolution(message)) return false;
    const intent = message?.intent || message?.flow || message?.state?.current_flow || "";
    if (["decision_review", "plan_adherence_review"].includes(intent)) return false;
    const summary = getMessageSummary(message);
    const risk = getMessageRiskSummary(message);
    const next = getMessageNextBestAction(message);
    const reason = getMessageReviewReason(message);
    return Boolean(risk || next || reason || (summary && summary !== message?.text));
  };

  const getBriefingFollowUpActions = () => {
    return normalizeFollowUpActions(
      insight?.follow_up_actions ||
      insight?.state?.analysis?.follow_up_actions ||
      insight?.suggested_actions ||
      []
    );
  };

  const getMissionOpenActions = () => {
    return normalizeFollowUpActions([
      missionControl?.agent_controller?.primary_action,
      ...(missionControl?.open_actions || []),
    ].filter(Boolean));
  };

  const followUpLabel = (handoff) => {
    const labels = {
      indicator_config: uiText.configLabel,
      daily_score_refresh: uiText.confirmLabel,
      maintenance_action: uiText.confirmLabel,
      bot_decision: uiText.proposalLabel,
      bot_decision_review: uiText.reviewLabel,
      bot_execution_decision: uiText.confirmLabel,
      bot_execution_console: uiText.executeLabel,
      indicator_insight: uiText.insightLabel,
      plan_status: uiText.statusLabel,
      daily_coach: uiText.coachLabel,
      behavioral_memory: uiText.memoryLabel,
      weekly_reflection: uiText.reflectLabel,
      mission_control: uiText.controlLabel,
    };
    return labels[handoff] || uiText.openLabel;
  };

  const followUpIcon = (handoff) => {
    if (handoff === "indicator_config") return <ListChecks size={11} className="text-blue-500 shrink-0" />;
    if (handoff === "daily_score_refresh" || handoff === "maintenance_action") return <Activity size={11} className="text-emerald-500 shrink-0" />;
    if (handoff === "bot_decision") return <Bot size={11} className="text-violet-500 shrink-0" />;
    if (handoff === "bot_decision_review") return <ListChecks size={11} className="text-violet-500 shrink-0" />;
    if (handoff === "bot_execution_decision") return <Shield size={11} className="text-rose-500 shrink-0" />;
    if (handoff === "bot_execution_console") return <Shield size={11} className="text-rose-500 shrink-0" />;
    if (handoff === "indicator_insight") return <Brain size={11} className="text-amber-500 shrink-0" />;
    if (handoff === "resolve_mission_item") return <CheckCircle2 size={11} className="text-emerald-500 shrink-0" />;
    if (handoff === "snooze_mission_item") return <Activity size={11} className="text-slate-500 shrink-0" />;
    return <Zap size={11} className="text-amber-500 shrink-0" />;
  };

  const buildMissionActionContext = (action = {}, sourceItem = null) => {
    const payload = action?.payload && typeof action.payload === "object" ? action.payload : {};
    const item = sourceItem && typeof sourceItem === "object" ? sourceItem : {};
    const hasMissionContext = Boolean(
      payload.current_flow ||
      payload.decision_id ||
      payload.bot_id ||
      item.decision_id ||
      item.bot_id
    );
    if (!hasMissionContext) return null;
    return {
      current_flow: payload.current_flow || item.current_flow || "bot_decision_review",
      asset: payload.asset || item.asset || globalSymbol || null,
      bot_id: payload.bot_id || item.bot_id || item.asset_bot_id || null,
      decision_id: payload.decision_id || item.decision_id || null,
      bot_name: payload.bot_name || item.bot_name || item.friendly_bot_name || null,
      setup_id: payload.setup_id || item.setup_id || null,
      strategy_id: payload.strategy_id || item.strategy_id || null,
      page_type: context.page_type,
      symbol: payload.asset || item.asset || context.symbol || globalSymbol || null,
      timeframe: context.timeframe,
    };
  };

  const missionBotDisplayName = (item = {}) => {
    const explicitName = String(item?.bot_name || item?.friendly_bot_name || "").trim();
    const asset = String(item?.asset || context.symbol || globalSymbol || "").trim().toUpperCase();
    const setupType = String(item?.setup_type || "").trim().toLowerCase();
    const setupName = String(item?.setup_name || "").trim();
    if (explicitName) return explicitName;
    if (setupType === "dca" && asset) return `je ${asset} DCA-bot`;
    if (setupType === "trade" && asset) return `je ${asset} trade-bot`;
    if (setupName && asset) return `je ${asset} bot voor ${setupName}`;
    if (asset) return `je ${asset} bot`;
    return "deze bot";
  };

  const humanizeMissionTitle = (item = {}) => {
    const rawTitle = String(item?.title || "").trim();
    const botLabel = missionBotDisplayName(item);
    const setupName = String(item?.setup_name || "").trim();
    if (/review bot-decision/i.test(rawTitle) || item?.type === "bot_decision" || item?.decision_id) {
      if (setupName) return `Review ${botLabel} voor ${setupName}`;
      return `Review ${botLabel}`;
    }
    return rawTitle || uiText.firstNextStep;
  };

  const humanizeMissionReason = (item = {}) => {
    const botName = missionBotDisplayName(item);
    const summary = String(item?.summary || item?.reason || "").trim();
    const action = String(item?.action || "").toLowerCase();
    if (summary.includes("geen orderbedrag") || action === "hold") {
      return `${botName} wacht nu op review. Controleer of wachten nog klopt.`;
    }
    if (summary && /^([A-Z]{2,10}):/i.test(summary)) {
      return `Controleer de open stap voor ${botName}.`;
    }
    return summary || `Controleer de open stap voor ${botName}.`;
  };

  const humanizeBehavioralPriorityBadge = (item = {}) => {
    const bias = String(item?.behavioral_priority_bias || "").toLowerCase();
    if (bias === "up") return "extra reviewgewicht";
    if (bias === "down") return "impuls geremd";
    return "";
  };

  const behavioralPriorityBadgeTone = (item = {}) => {
    const bias = String(item?.behavioral_priority_bias || "").toLowerCase();
    if (bias === "up") {
      return "bg-amber-50 text-amber-700 border-amber-200/80 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-900/50";
    }
    if (bias === "down") {
      return "bg-rose-50 text-rose-700 border-rose-200/80 dark:bg-rose-950/30 dark:text-rose-300 dark:border-rose-900/50";
    }
    return "";
  };

  const humanizeActionLabel = (action = {}, sourceItem = null) => {
    const handoff = action?.handoff || action?.type;
    const botName = missionBotDisplayName(sourceItem || action);
    if (handoff === "bot_decision_review") return `Leg ${botName} uit`;
    if (handoff === "bot_decision") return `Nieuwe stap voor ${botName}`;
    if (handoff === "bot_execution_decision") return `Volgende stap voor ${botName}`;
    return action?.label || uiText.openLabel;
  };

  const openExecutionConsole = (action = {}) => {
    const botId = action.bot_id || action.botId || action.asset_bot_id || action.payload?.bot_id || null;
    const symbol = action.asset || action.symbol || action.payload?.symbol || globalSymbol || "BTC";

    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("execution-guardrail-handoff", {
        detail: {
          botId,
          symbol,
          focus: "trade",
          source: action.source || "finn",
        },
      }));
    }

    router.push(botId ? `/bot?bot_id=${botId}&focus=trade` : `/bot?symbol=${symbol}&focus=trade`);
    setIsOpen(false);
  };

  function emitFinnRefreshSignals() {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("finn-refresh-requested"));
    }
    router.refresh();
  }

  const handleFollowUpAction = async (action, sourceItem = null) => {
    if (action?.handoff === "bot_execution_console" || action?.type === "open_bot_execution_console") {
      trackAssistantEvent({
        event_name: "next_best_action_clicked",
        page: pathname || "/assistant",
        surface: "finn_overlay",
        asset: action?.asset || globalSymbol || null,
        flow_type: action?.handoff || "bot_execution_console",
        next_best_action: action?.label || action?.prompt || null,
      });
      openExecutionConsole(action);
      return;
    }
    if (!action?.prompt) return;
    const overrideContext = buildMissionActionContext(action, sourceItem);
    trackAssistantEvent({
      event_name: "next_best_action_clicked",
      page: pathname || "/assistant",
      surface: "finn_overlay",
      asset: action?.asset || globalSymbol || null,
      flow_type: action?.handoff || "chat",
      next_best_action: action?.label || action?.prompt || null,
    });
    await handleChat(action.prompt, false, overrideContext);
  };

  const buildExecutionConsoleAction = (action, res) => {
    const botId = action?.payload?.bot_id || action?.bot_id || res?.bot_id || null;
    const symbol = action?.payload?.symbol || action?.asset || res?.symbol || globalSymbol || "BTC";
    if (!botId && !symbol) return null;
    return {
      label: uiText.openExecutionConsole,
      handoff: "bot_execution_console",
      type: "open_bot_execution_console",
      bot_id: botId,
      symbol,
      asset: symbol,
      source: "live_preflight",
    };
  };

  const buildAgentHandoffAuditAction = (action, controller) => {
    if (!action?.prompt || !controller?.dominant_agent) return null;
    return {
      id: `agent-handoff-${controller.dominant_agent}-${Date.now()}`,
      type: "agent_controller_handoff",
      label: `Volg ${controller.dominant_label || controller.dominant_agent}`,
      payload: {
        agent_controller: controller,
        primary_action: action,
        dominant_agent: controller.dominant_agent,
        asset: action.asset,
      },
      risk_level: "low",
      requires_confirmation: false,
      autonomy_level: "user_initiated",
      guardrails: {
        requires_confirmation: false,
        can_execute_without_user: false,
        writes_trading_config: false,
        executes_order: false,
      },
    };
  };

  const logAgentHandoff = async (action, controller) => {
    // Security: client-built handoff audit payloads are not executable. The
    // server must issue an action_id before any Finn action can be confirmed.
    return;
  };

  const handleAgentControllerAction = async (action, controller) => {
    await logAgentHandoff(action, controller);
    await handleFollowUpAction(action);
  };

  const renderFollowUpButtons = (actions, compact = false, sourceItem = null) => (
    <div className={`flex flex-wrap gap-2 ${compact ? "" : "mt-4 pt-3 border-t border-slate-100/50 dark:border-slate-800/50"}`}>
      {!compact && (
        <span className="w-full text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
          {uiText.nextSteps}
        </span>
      )}
      {actions.map((action, idx) => (
        <button
          key={`${action.prompt}-${idx}`}
          onClick={() => handleFollowUpAction(action, sourceItem)}
          className={`group inline-flex items-center gap-2 rounded-xl border transition-all active:scale-[0.98] text-left ${
            compact
              ? "border-blue-100 dark:border-blue-900/40 bg-white/80 dark:bg-slate-950/50 px-3 py-2 text-[10px] font-black uppercase tracking-wider text-blue-700 dark:text-blue-300 shadow-sm hover:border-blue-300 dark:hover:border-blue-700 hover:bg-blue-50 dark:hover:bg-blue-950/40"
              : "px-3 py-2 text-[11px] font-bold bg-white dark:bg-slate-950 hover:bg-blue-50 dark:hover:bg-blue-950/30 text-blue-600 dark:text-blue-400 hover:text-blue-700 border-slate-100 dark:border-slate-800 hover:border-blue-200 dark:hover:border-blue-900/40 hover:-translate-y-0.5 hover:shadow-sm"
          }`}
        >
          {followUpIcon(action.handoff)}
          <span className={compact ? "normal-case tracking-normal text-[11px] leading-tight" : ""}>
            {humanizeActionLabel(action, sourceItem)}
          </span>
          {action.handoff && action.handoff !== "chat" && (
            <span className="rounded-md bg-blue-100 dark:bg-blue-900/50 px-1.5 py-0.5 text-[8px] font-black uppercase tracking-widest text-blue-500 dark:text-blue-300">
              {followUpLabel(action.handoff)}
            </span>
          )}
        </button>
      ))}
    </div>
  );

  const missionResolveLabel = (state) => ({
    needs_user_confirmation: "actie nodig",
    waiting_for_data: "wacht op data",
    monitor_today: "monitor",
    resolved: "klaar",
    skipped: "overgeslagen",
    snoozed: "later",
  }[state] || state || "open");

  const behavioralStatusLabel = (status) => ({
    not_enough_data: "te weinig data",
    early_signal: "stabiel",
    attention: "aandacht",
  }[status] || status || "onbekend");

  const behavioralTone = (status) => {
    if (status === "attention") return "border-amber-100 dark:border-amber-900/50 bg-amber-50/50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300";
    if (status === "not_enough_data") return "border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/40 text-slate-500 dark:text-slate-400";
    return "border-emerald-100 dark:border-emerald-900/50 bg-emerald-50/50 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300";
  };

  const agentVerdictTone = (verdict = {}) => {
    const status = String(verdict.status || "").toLowerCase();
    const priority = String(verdict.priority || "").toLowerCase();
    if (priority === "high" || status.includes("block") || status.includes("attention") || status.includes("intervened")) {
      return "border-rose-100 dark:border-rose-900/50 bg-rose-50/55 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300";
    }
    if (priority === "medium" || status.includes("need") || status.includes("missing") || status.includes("waiting") || status.includes("review")) {
      return "border-amber-100 dark:border-amber-900/50 bg-amber-50/55 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300";
    }
    return "border-emerald-100 dark:border-emerald-900/50 bg-emerald-50/55 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300";
  };

  const agentVerdictIcon = (agent = "") => {
    if (agent.includes("macro") || agent.includes("technical")) return <BarChart3 size={11} />;
    if (agent.includes("risk") || agent.includes("execution")) return <Shield size={11} />;
    if (agent.includes("strategy")) return <Target size={11} />;
    if (agent.includes("memory")) return <Brain size={11} />;
    return <Activity size={11} />;
  };

  const getMessageAgentVerdicts = (message) => {
    const state = message?.state || {};
    const analysis = state.analysis || message?.analysis || {};
    return (
      state.agent_verdicts ||
      analysis.agent_verdicts ||
      message?.agent_verdicts ||
      []
    );
  };

  const getMessageAgentController = (message) => {
    const state = message?.state || {};
    const analysis = state.analysis || message?.analysis || {};
    return state.agent_controller || analysis.agent_controller || message?.agent_controller || null;
  };

  const getMessagePortfolioRisk = (message) => {
    const state = message?.state || {};
    const analysis = state.analysis || message?.analysis || {};
    return state.portfolio_risk || analysis.portfolio_risk || message?.portfolio_risk || null;
  };

  const getMessageBehavioralAnalysis = (message) => {
    const state = message?.state || {};
    const analysis = state.analysis || message?.analysis || {};
    const intent = message?.intent || state?.intent || null;
    const flow = message?.flow || state?.current_flow || null;
    const hasBehavioralShape = (
      analysis?.behavioral_profile ||
      analysis?.trend ||
      analysis?.week_over_week ||
      analysis?.memory_cards ||
      analysis?.risk_flags ||
      analysis?.habit_cards ||
      analysis?.signals
    );
    if (!hasBehavioralShape && !["behavioral_intelligence", "behavioral_memory", "weekly_reflection"].includes(intent) && !["behavioral_intelligence", "behavioral_memory", "weekly_reflection"].includes(flow)) {
      return null;
    }
    return analysis;
  };

  const getMessageExecutionReview = (message) => {
    const state = message?.state || {};
    const analysis = state.analysis || message?.analysis || {};
    return state.execution_review || analysis.execution_review || message?.execution_review || null;
  };

  const getMessageOperatorResolution = (message) => {
    const state = message?.state || {};
    const analysis = state.analysis || message?.analysis || {};
    return (
      state.operator_resolution ||
      analysis.operator_resolution ||
      analysis.action_follow_through ||
      message?.operatorResolution ||
      message?.operator_resolution ||
      null
    );
  };

  const getMessageDecisionReview = (message) => {
    const state = message?.state || {};
    const analysis = state.analysis || message?.analysis || {};
    const intent = message?.intent || state?.intent || null;
    if (intent === "decision_review" || state?.current_flow === "decision_review" || analysis?.decision_status) {
      return analysis;
    }
    return null;
  };

  const getMessagePlanAdherenceReview = (message) => {
    const state = message?.state || {};
    const analysis = state.analysis || message?.analysis || {};
    const intent = message?.intent || state?.intent || null;
    if (intent === "plan_adherence_review" || state?.current_flow === "plan_adherence_review" || analysis?.adherence_status) {
      return analysis;
    }
    return null;
  };

  const getMessageOutcomeTracking = (message) => {
    const state = message?.state || {};
    const analysis = state.analysis || message?.analysis || {};
    const intent = message?.intent || state?.intent || null;
    if (intent === "outcome_tracking" || state?.current_flow === "outcome_tracking" || analysis?.behavior_pattern || analysis?.sample_size !== undefined) {
      return analysis;
    }
    return null;
  };

  const getMessagePriorityEngine = (message) => {
    const state = message?.state || {};
    const analysis = state.analysis || message?.analysis || {};
    const intent = message?.intent || state?.intent || null;
    if (intent === "priority_engine" || state?.current_flow === "priority_engine" || analysis?.top_priorities) {
      return analysis;
    }
    return null;
  };

  const getMessageMemoryV2 = (message) => {
    const state = message?.state || {};
    const analysis = state.analysis || message?.analysis || {};
    const intent = message?.intent || state?.intent || null;
    if (intent === "behavioral_memory" || state?.current_flow === "behavioral_memory" || analysis?.memory_pattern) {
      return analysis?.memory_v2 || analysis;
    }
    return null;
  };

  const getMessagePortfolioOperatingSystem = (message) => {
    const state = message?.state || {};
    const analysis = state.analysis || message?.analysis || {};
    const intent = message?.intent || state?.intent || null;
    if (intent === "portfolio_operating_system" || state?.current_flow === "portfolio_operating_system" || analysis?.operating_posture) {
      return analysis;
    }
    return null;
  };

  const renderAgentController = (controller, compact = false) => {
    if (!controller?.dominant_agent) return null;
    const score = Number(controller.dominant_score || 0);
    const tone = score >= 90
      ? "border-rose-100 dark:border-rose-900/50 bg-rose-50/60 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300"
      : score >= 65
        ? "border-amber-100 dark:border-amber-900/50 bg-amber-50/60 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300"
        : "border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/45 text-slate-600 dark:text-slate-300";
    return (
      <div className={`${compact ? "mt-2" : "mt-3"} rounded-xl border px-3 py-2 ${tone}`}>
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest">
            <Brain size={11} />
            {at("cards.mainConclusion")}
          </span>
          <span className="rounded-full bg-white/75 dark:bg-slate-950/40 px-2 py-0.5 text-[8px] font-black uppercase tracking-widest">
            {controller.dominant_label || controller.dominant_agent}
          </span>
        </div>
        <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">
          {controller.reason || controller.next_action || at("cards.agentRankingFallback")}
        </p>
        {!compact && controller.next_action && (
          <p className="mt-1 text-[8px] font-black uppercase tracking-widest opacity-75">
            {controller.next_action}
          </p>
        )}
        {controller.primary_item_id && (
          <p className="mt-1 text-[8px] font-black uppercase tracking-widest opacity-65">
            {at("cards.accountability")}: {controller.primary_item_id}
          </p>
        )}
        {controller.primary_action?.prompt && (
          <button
            type="button"
            onClick={() => handleAgentControllerAction(controller.primary_action, controller)}
            className="mt-2 inline-flex items-center gap-2 rounded-lg bg-white/80 dark:bg-slate-950/45 px-2.5 py-1.5 text-[9px] font-black uppercase tracking-widest shadow-sm transition hover:bg-white dark:hover:bg-slate-950"
          >
            {followUpIcon(controller.primary_action.handoff)}
            {controller.primary_action.label || controller.primary_action.prompt}
          </button>
        )}
      </div>
    );
  };

  const renderBehavioralIntelligenceCard = (analysis) => {
    if (!analysis) return null;

    const profile = analysis.behavioral_profile || null;
    const trend = analysis.trend || analysis.week_over_week || analysis.month_over_month || null;
    const riskFlags = Array.isArray(analysis.risk_flags) ? analysis.risk_flags : [];
    const habitCards = Array.isArray(analysis.habit_cards) ? analysis.habit_cards : [];
    const memoryCards = Array.isArray(analysis.memory_cards) ? analysis.memory_cards : [];
    const signals = Array.isArray(analysis.signals) ? analysis.signals : [];
    const balanceScore = analysis.behavioral_balance_score;

    if (!profile && !trend && riskFlags.length === 0 && habitCards.length === 0 && memoryCards.length === 0 && signals.length === 0) {
      return null;
    }

    const signalCards = riskFlags.length > 0 ? riskFlags : (memoryCards.length > 0 ? memoryCards : signals);

    return (
      <div className="mt-3 rounded-2xl border border-violet-100 dark:border-violet-900/40 bg-violet-50/60 dark:bg-violet-950/20 p-4 space-y-4 text-violet-900 dark:text-violet-100">
        <div className="flex items-center justify-between gap-3">
          <span className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-violet-700 dark:text-violet-300">
            <Brain size={13} />
            {at("cards.behavioralIntelligence")}
          </span>
          {balanceScore !== undefined && balanceScore !== null && (
            <span className="rounded-full border border-violet-200 dark:border-violet-900/50 bg-white/80 dark:bg-slate-950/40 px-2 py-1 text-[9px] font-black uppercase tracking-widest text-violet-700 dark:text-violet-300">
              {balanceScore}/100
            </span>
          )}
        </div>

        {profile && (
          <div className="rounded-xl border border-white/70 dark:border-slate-900/40 bg-white/75 dark:bg-slate-950/35 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[9px] font-black uppercase tracking-widest text-violet-700 dark:text-violet-300">
                {profile.label}
              </span>
              {profile.confidence && (
                <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                  {profile.confidence}
                </span>
              )}
            </div>
            <p className="mt-2 text-xs font-semibold leading-relaxed text-slate-700 dark:text-slate-200">
              {profile.summary}
            </p>
          </div>
        )}

        {trend?.summary && (
          <div className="rounded-xl border border-white/70 dark:border-slate-900/40 bg-white/75 dark:bg-slate-950/35 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest text-violet-700 dark:text-violet-300">
                <Activity size={11} />
                {at("cards.trend")}
              </span>
              {(trend.status || trend.momentum) && (
                <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                  {trend.status || trend.momentum}
                </span>
              )}
            </div>
            <p className="mt-2 text-xs font-semibold leading-relaxed text-slate-700 dark:text-slate-200">
              {trend.summary}
            </p>
          </div>
        )}

        {signalCards.length > 0 && (
          <div className="space-y-2">
            <div className="text-[9px] font-black uppercase tracking-widest text-violet-700 dark:text-violet-300">
              {at("cards.whatFinnWatching")}
            </div>
            {signalCards.slice(0, 3).map((item, index) => (
              <div
                key={`${item.id || item.type || item.label || "signal"}-${index}`}
                className="rounded-xl border border-white/70 dark:border-slate-900/40 bg-white/75 dark:bg-slate-950/35 p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[9px] font-black uppercase tracking-widest text-violet-700 dark:text-violet-300">
                    {item.label || item.type || at("cards.signal")}
                  </span>
                  {(item.severity || item.confidence) && (
                    <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                      {item.severity || item.confidence}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-xs font-semibold leading-relaxed text-slate-700 dark:text-slate-200">
                  {item.summary || item.message}
                </p>
              </div>
            ))}
          </div>
        )}

        {habitCards.length > 0 && (
          <div className="space-y-2">
            <div className="text-[9px] font-black uppercase tracking-widest text-violet-700 dark:text-violet-300">
              {at("cards.workStyleRecognized")}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {habitCards.slice(0, 4).map((card) => (
                <div
                  key={card.id || card.label}
                  className="rounded-xl border border-white/70 dark:border-slate-900/40 bg-white/75 dark:bg-slate-950/35 p-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[9px] font-black uppercase tracking-widest text-violet-700 dark:text-violet-300">
                      {card.label}
                    </span>
                    {card.status && (
                      <span className="text-[8px] font-black uppercase tracking-widest opacity-70">
                        {card.status}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-xs font-semibold leading-relaxed text-slate-700 dark:text-slate-200">
                    {card.summary}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderAgentVerdicts = (verdicts, compact = false) => {
    const items = Array.isArray(verdicts) ? verdicts.filter(Boolean).slice(0, compact ? 4 : 6) : [];
    if (items.length === 0) return null;
    return (
      <div className={`${compact ? "mt-2" : "mt-4 pt-3 border-t border-slate-100/60 dark:border-slate-800/60"} space-y-2`}>
        {!compact && (
          <div className="flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
            <Brain size={11} className="text-blue-500" />
            Controlelagen
          </div>
        )}
        <div className={`grid gap-1.5 ${compact ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2"}`}>
          {items.map((verdict, index) => (
            <div
              key={`${verdict.agent || verdict.label || "agent"}-${index}`}
              className={`rounded-xl border px-2.5 py-2 ${agentVerdictTone(verdict)}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 min-w-0 text-[9px] font-black uppercase tracking-widest">
                  {agentVerdictIcon(verdict.agent || verdict.label || "")}
                  <span className="truncate">{verdict.label || verdict.agent || "Agent"}</span>
                </span>
                <span className="shrink-0 rounded-full bg-white/75 dark:bg-slate-950/40 px-1.5 py-0.5 text-[7px] font-black uppercase tracking-widest">
                  {verdict.status || "unknown"}
                </span>
              </div>
              <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">
                {verdict.reason || verdict.next_action || "Geen toelichting beschikbaar."}
              </p>
              {!compact && verdict.next_action && (
                <p className="mt-1 text-[8px] font-black uppercase tracking-widest opacity-75">
                  {verdict.next_action}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderPortfolioRisk = (portfolioRisk, compact = false) => {
    if (!portfolioRisk?.status || portfolioRisk.status === "balanced" || portfolioRisk.status === "no_assets") {
      return null;
    }

    const ignoreToday = Array.isArray(portfolioRisk.ignore_today_assets) ? portfolioRisk.ignore_today_assets.slice(0, compact ? 2 : 3) : [];
    const liveHotspots = Array.isArray(portfolioRisk.live_bot_hotspots) ? portfolioRisk.live_bot_hotspots.slice(0, compact ? 2 : 3) : [];
    const rankedConflicts = Array.isArray(portfolioRisk.ranked_conflicts) ? portfolioRisk.ranked_conflicts.slice(0, compact ? 2 : 3) : [];

    if (ignoreToday.length === 0 && liveHotspots.length === 0 && rankedConflicts.length === 0) {
      return null;
    }

    const tone = portfolioRisk.status === "high_attention"
      ? "border-rose-100 dark:border-rose-900/50 bg-rose-50/60 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300"
      : portfolioRisk.status === "needs_data" || portfolioRisk.status === "watch" || portfolioRisk.status === "concentrated"
        ? "border-amber-100 dark:border-amber-900/50 bg-amber-50/60 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300"
        : "border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/45 text-slate-600 dark:text-slate-300";

    return (
      <div className={`${compact ? "mt-2" : "mt-4"} rounded-xl border px-3 py-3 ${tone}`}>
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest">
            <Shield size={11} />
            {at("cards.portfolioRisk")}
          </span>
          <span className="rounded-full bg-white/75 dark:bg-slate-950/40 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest">
            {portfolioRisk.status}
          </span>
        </div>
        {portfolioRisk.message && (
          <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">
            {portfolioRisk.message}
          </p>
        )}

        {ignoreToday.length > 0 && (
          <div className="mt-2">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">
              {at("cards.betterIgnoreToday")}
            </div>
            <div className="mt-1 space-y-1">
              {ignoreToday.map((item) => (
                <div key={`ignore-${item.asset}`} className="rounded-lg bg-white/70 dark:bg-slate-950/35 px-2.5 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[9px] font-black uppercase tracking-widest">{item.asset}</span>
                    <span className="text-[7px] font-black uppercase tracking-widest opacity-70">
                      {at("cards.score")} {item.risk_score}
                    </span>
                  </div>
                  <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{item.reason}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {liveHotspots.length > 0 && (
          <div className="mt-2">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">
              {at("cards.liveBotHotspots")}
            </div>
            <div className="mt-1 space-y-1">
              {liveHotspots.map((item) => (
                <div key={`hotspot-${item.asset}`} className="rounded-lg bg-white/70 dark:bg-slate-950/35 px-2.5 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[9px] font-black uppercase tracking-widest">{item.asset}</span>
                    <span className="text-[7px] font-black uppercase tracking-widest opacity-70">
                      {item.live_bot_count} {at("cards.live")}
                    </span>
                  </div>
                  <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{item.summary}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {!compact && rankedConflicts.length > 0 && (
          <div className="mt-2">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">
              {at("cards.topConflicts")}
            </div>
            <div className="mt-1 space-y-1">
              {rankedConflicts.map((item, index) => (
                <div key={`conflict-${item.asset || "portfolio"}-${index}`} className="rounded-lg bg-white/70 dark:bg-slate-950/35 px-2.5 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[9px] font-black uppercase tracking-widest">{item.asset || at("cards.portfolio")}</span>
                    <span className="text-[7px] font-black uppercase tracking-widest opacity-70">
                      {item.severity || item.risk_level || at("cards.review")}
                    </span>
                  </div>
                  <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{item.reason}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderMissionControlV3Surface = () => {
    const priorityEngine = missionControl?.priority_engine;
    const memoryV2 = missionControl?.memory_v2;
    const portfolioOS = missionControl?.portfolio_operating_system;
    const governanceSummary = missionControl?.governance_events_summary;

    if (!priorityEngine && !memoryV2 && !portfolioOS && !governanceSummary) {
      return null;
    }

    const phaseCards = [
      {
        key: "p1",
        label: "Beslischeck",
        value: governanceSummary?.decision_review_count || 0,
        tone: "text-blue-600 dark:text-blue-300",
        status: (governanceSummary?.decision_review_count || 0) > 0 ? "active" : "quiet",
        icon: <FileText size={11} className="text-blue-500" />,
      },
      {
        key: "p2",
        label: "Plantrouw",
        value: governanceSummary?.plan_adherence_count || 0,
        tone: "text-rose-600 dark:text-rose-300",
        status: (governanceSummary?.plan_adherence_count || 0) > 0 ? "active" : "quiet",
        icon: <Shield size={11} className="text-rose-500" />,
      },
      {
        key: "p3",
        label: "Outcome-tracking",
        value: governanceSummary?.outcome_tracking_count || 0,
        tone: "text-emerald-600 dark:text-emerald-300",
        status: (governanceSummary?.outcome_tracking_count || 0) > 0 ? "active" : "early",
        icon: <BarChart3 size={11} className="text-emerald-500" />,
      },
      {
        key: "p4",
        label: "Portfolio-intelligence",
        value: governanceSummary?.portfolio_intelligence_count || 0,
        tone: "text-amber-700 dark:text-amber-300",
        status: missionControl?.portfolio_risk?.status || "quiet",
        icon: <Activity size={11} className="text-amber-500" />,
      },
      {
        key: "p5",
        label: "Prioriteitenmotor",
        value: Array.isArray(priorityEngine?.top_priorities) ? priorityEngine.top_priorities.length : 0,
        tone: "text-violet-600 dark:text-violet-300",
        status: priorityEngine?.headline ? "active" : "quiet",
        icon: <Target size={11} className="text-violet-500" />,
      },
      {
        key: "p6",
        label: uiText.memoryV2,
        value: memoryV2?.supporting_evidence_count || 0,
        tone: "text-fuchsia-600 dark:text-fuchsia-300",
        status: memoryV2?.confidence_level || "early",
        icon: <Brain size={11} className="text-fuchsia-500" />,
      },
      {
        key: "p7",
        label: uiText.portfolioOverview,
        value: Array.isArray(portfolioOS?.next_best_actions) ? portfolioOS.next_best_actions.length : 0,
        tone: "text-cyan-600 dark:text-cyan-300",
        status: portfolioOS?.operating_posture || "quiet",
        icon: <Bot size={11} className="text-cyan-500" />,
      },
    ];

    return (
      <div className="rounded-2xl border border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/40 p-3 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-1.5 text-[8px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
              <Terminal size={11} className="text-cyan-500" />
              {uiText.finnOverview}
            </div>
            <p className="mt-1 text-[11px] font-black text-slate-900 dark:text-slate-100 leading-snug">
              {portfolioOS?.control_plane?.headline || priorityEngine?.headline || uiText.portfolioOverviewSummary}
            </p>
            {primaryProfileHabitAlignment && (
              <div className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-amber-200/80 bg-amber-50 px-2.5 py-1 text-[7px] font-black uppercase tracking-widest text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/25 dark:text-amber-300">
                <Shield size={10} />
                {(governanceCopy.behavioralBrake || uiText.behavioralBrakeShort)}: {primaryBehaviorLabel}
              </div>
            )}
          </div>
          {portfolioOS?.operating_posture && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/40 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-cyan-700 dark:text-cyan-300">
              {humanizeSurfaceStatus(portfolioOS.operating_posture)}
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {phaseCards.map((card) => (
            <div key={card.key} className="rounded-xl border border-slate-100 dark:border-slate-800 bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1 text-[7px] font-black uppercase tracking-widest text-slate-400">
                  {card.icon}
                  <span className="truncate">{card.label}</span>
                </span>
                <span className={`text-[10px] font-black tabular-nums ${card.tone}`}>{card.value}</span>
              </div>
              <div className="mt-1 text-[7px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
                {humanizeSurfaceStatus(card.status)}
              </div>
            </div>
          ))}
        </div>

        {priorityEngine && (
          <div className="rounded-xl border border-violet-100 dark:border-violet-900/50 bg-violet-50/50 dark:bg-violet-950/15 px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <span className="inline-flex items-center gap-1.5 text-[8px] font-black uppercase tracking-widest text-violet-700 dark:text-violet-300">
                <Target size={11} />
                {governanceCopy.priorityEngine || uiText.priorityEngine}
              </span>
              <span className="text-[7px] font-black uppercase tracking-widest text-violet-700 dark:text-violet-300">
                {priorityEngine.open_counts?.high_priority_count || 0} {(governanceCopy.priorityHigh || uiText.priorityHigh)}
              </span>
            </div>
            {primaryBehaviorRule && (
              <div className="mt-2 rounded-lg border border-amber-200/80 bg-white/80 px-2.5 py-2 dark:border-amber-900/40 dark:bg-slate-950/35">
                <div className="text-[7px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">
                  {uiText.whyFinnBrakes}
                </div>
                <p className="mt-1 text-[9px] font-semibold leading-snug text-slate-600 dark:text-slate-300">
                  {primaryBehaviorRule}
                </p>
              </div>
            )}
            {priorityEngine.why_now && (
              <p className="mt-1 text-[10px] font-semibold text-slate-600 dark:text-slate-300 leading-snug">
                {priorityEngine.why_now}
              </p>
            )}
            {Array.isArray(priorityEngine.top_priorities) && priorityEngine.top_priorities.length > 0 && (
              <div className="mt-2 space-y-1.5">
                {priorityEngine.top_priorities.slice(0, 3).map((item, index) => (
                  <div key={`${item.id || item.title}-${index}`} className="rounded-lg bg-white/80 dark:bg-slate-950/40 px-2.5 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] font-black text-slate-900 dark:text-slate-100 leading-tight">{item.title}</span>
                      <div className="flex flex-col items-end gap-1">
                        <span className="text-[7px] font-black uppercase tracking-widest text-violet-700 dark:text-violet-300">
                          {item.lane || item.priority}
                        </span>
                        {humanizeBehavioralPriorityBadge(item) && (
                          <span className={`rounded-full border px-2 py-0.5 text-[7px] font-black uppercase tracking-widest ${behavioralPriorityBadgeTone(item)}`}>
                            {humanizeBehavioralPriorityBadge(item)}
                          </span>
                        )}
                      </div>
                    </div>
                    {(item.why_now || item.source_reason) && (
                      <p className="mt-1 text-[9px] font-semibold text-slate-500 dark:text-slate-400 leading-snug">
                        {item.why_now || item.source_reason}
                      </p>
                    )}
                    {buildPriorityDrillIn(item) && (
                      <button
                        type="button"
                        onClick={() => buildPriorityDrillIn(item)?.run()}
                        className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-violet-200 dark:border-violet-900/50 bg-white/80 dark:bg-slate-950/50 px-2 py-1 text-[8px] font-black uppercase tracking-widest text-violet-700 dark:text-violet-300"
                      >
                        <Target size={10} />
                        {buildPriorityDrillIn(item)?.label}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {(memoryV2 || portfolioOS) && (
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
            {memoryV2 && (
              <div className="rounded-xl border border-fuchsia-100 dark:border-fuchsia-900/50 bg-fuchsia-50/50 dark:bg-fuchsia-950/15 px-3 py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-1.5 text-[8px] font-black uppercase tracking-widest text-fuchsia-700 dark:text-fuchsia-300">
                    <Brain size={11} />
                    {uiText.memoryV2}
                  </span>
                  <span className="text-[7px] font-black uppercase tracking-widest text-fuchsia-700 dark:text-fuchsia-300">
                    {humanizeSurfaceStatus(memoryV2.confidence_level || "early")}
                  </span>
                </div>
                {memoryV2.memory_pattern && (
                  <p className="mt-1 text-[10px] font-black text-slate-900 dark:text-slate-100 leading-snug">
                    {memoryV2.memory_pattern}
                  </p>
                )}
                {memoryV2.behavioral_cost && (
                  <p className="mt-1 text-[9px] font-semibold text-slate-500 dark:text-slate-400 leading-snug">
                    {memoryV2.behavioral_cost}
                  </p>
                )}
                {memoryV2.recommended_rule && (
                  <div className="mt-2 rounded-lg bg-white/80 dark:bg-slate-950/40 px-2.5 py-2">
                    <div className="text-[7px] font-black uppercase tracking-widest text-fuchsia-700 dark:text-fuchsia-300">
                      {governanceCopy.recommendedRule}
                    </div>
                    <p className="mt-1 text-[9px] font-semibold text-slate-600 dark:text-slate-300 leading-snug">
                      {memoryV2.recommended_rule}
                    </p>
                  </div>
                )}
              </div>
            )}

            {portfolioOS && (
              <div className="rounded-xl border border-cyan-100 dark:border-cyan-900/50 bg-cyan-50/50 dark:bg-cyan-950/15 px-3 py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-1.5 text-[8px] font-black uppercase tracking-widest text-cyan-700 dark:text-cyan-300">
                    <Bot size={11} />
                    {governanceCopy.portfolioOperatingSystem}
                  </span>
                  <span className="text-[7px] font-black uppercase tracking-widest text-cyan-700 dark:text-cyan-300">
                    {humanizeSurfaceStatus(portfolioOS.operating_posture)}
                  </span>
                </div>
                {portfolioOS.control_plane?.why_now && (
                  <p className="mt-1 text-[9px] font-semibold text-slate-500 dark:text-slate-400 leading-snug">
                    {portfolioOS.control_plane.why_now}
                  </p>
                )}
                {portfolioOS.control_plane?.habit_override && (
                  <div className="mt-2 rounded-lg bg-white/80 dark:bg-slate-950/40 px-2.5 py-2">
                    <div className="text-[7px] font-black uppercase tracking-widest text-cyan-700 dark:text-cyan-300">
                      {governanceCopy.behaviorRuleNow}
                    </div>
                    <p className="mt-1 text-[9px] font-semibold text-slate-600 dark:text-slate-300 leading-snug">
                      {portfolioOS.control_plane.habit_override}
                    </p>
                  </div>
                )}
                {Array.isArray(portfolioOS.next_best_actions) && portfolioOS.next_best_actions.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {portfolioOS.next_best_actions.slice(0, 3).map((item, index) => (
                      <div key={`${item}-${index}`} className="rounded-lg bg-white/80 dark:bg-slate-950/40 px-2.5 py-2 text-[9px] font-semibold text-slate-700 dark:text-slate-200">
                        {item}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderExecutionReviewCard = (review, compact = false) => {
    if (!review?.title || !review?.summary) return null;

    const tone = review.status === "blocked" || review.status === "needs_review"
      ? "border-rose-100 dark:border-rose-900/50 bg-rose-50/60 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300"
      : review.status === "waiting_for_data" || review.status === "attention" || review.status === "partial_data"
        ? "border-amber-100 dark:border-amber-900/50 bg-amber-50/60 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300"
        : "border-blue-100 dark:border-blue-900/50 bg-blue-50/60 dark:bg-blue-950/20 text-blue-700 dark:text-blue-300";

    const whyThis = Array.isArray(review.why_this) ? review.why_this.slice(0, compact ? 2 : 3) : [];
    const whatNext = Array.isArray(review.what_next) ? review.what_next.slice(0, compact ? 2 : 3) : [];
    const evidence = Array.isArray(review.evidence) ? review.evidence.slice(0, compact ? 3 : 5) : [];
    const actions = normalizeFollowUpActions(review.actions || []);

    return (
      <div className={`${compact ? "mt-2" : "mt-4"} rounded-xl border px-3 py-3 ${tone}`}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest">
              <FileText size={11} />
              {uiText.decisionExplain}
            </div>
            <p className="mt-1 text-[11px] font-black leading-snug text-slate-900 dark:text-slate-100">
              {review.title}
            </p>
          </div>
          {review.status && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/40 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest">
              {review.status}
            </span>
          )}
        </div>

        <p className="mt-2 text-[10px] font-semibold leading-snug opacity-90">
          {review.summary}
        </p>

        {whyThis.length > 0 && (
          <div className="mt-3">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{uiText.whyThis}</div>
            <div className="mt-1 space-y-1">
              {whyThis.map((item, index) => (
                <p key={`why-${index}`} className="text-[10px] font-semibold leading-snug opacity-90">
                  {item}
                </p>
              ))}
            </div>
          </div>
        )}

        {review.why_now && (
          <div className="mt-3">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{uiText.whyNow}</div>
            <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{review.why_now}</p>
          </div>
        )}

        {whatNext.length > 0 && (
          <div className="mt-3">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{uiText.whatNow}</div>
            <div className="mt-1 space-y-1">
              {whatNext.map((item, index) => (
                <p key={`next-${index}`} className="text-[10px] font-semibold leading-snug opacity-90">
                  {item}
                </p>
              ))}
            </div>
          </div>
        )}

        {review.do_not_do && (
          <div className="mt-3 rounded-lg border border-white/70 dark:border-slate-900/40 bg-white/70 dark:bg-slate-950/30 px-2.5 py-2">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{uiText.doNotDo}</div>
            <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{review.do_not_do}</p>
          </div>
        )}

        {evidence.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {evidence.map((item, index) => (
              <span
                key={`${item.label || "evidence"}-${index}`}
                className="rounded-full bg-white/80 dark:bg-slate-950/40 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest"
              >
                {item.label}: {item.value}
              </span>
            ))}
          </div>
        )}

        {actions.length > 0 && (
          <div className="mt-3">
            {renderFollowUpButtons(actions, true)}
          </div>
        )}
      </div>
    );
  };

  const renderOperatorResolutionCard = (resolution) => {
    if (!resolution?.title || !resolution?.summary) return null;

    const tone = resolution.status === "resolved"
      ? "border-emerald-100 dark:border-emerald-900/50 bg-emerald-50/60 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300"
      : resolution.status === "skipped" || resolution.status === "snoozed"
        ? "border-amber-100 dark:border-amber-900/50 bg-amber-50/60 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300"
        : "border-blue-100 dark:border-blue-900/50 bg-blue-50/60 dark:bg-blue-950/20 text-blue-700 dark:text-blue-300";

    const whatChanged = Array.isArray(resolution.what_changed) ? resolution.what_changed.slice(0, 3) : [];
    const whatNext = Array.isArray(resolution.what_next) ? resolution.what_next.slice(0, 3) : [];

    return (
      <div className={`mt-4 rounded-xl border px-3 py-3 ${tone}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest">
            <CheckCircle2 size={11} />
            {at("cards.actionFollowThrough")}
          </div>
          {resolution.status && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/40 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest">
              {resolution.status}
            </span>
          )}
        </div>
        <p className="mt-1 text-[11px] font-black leading-snug text-slate-900 dark:text-slate-100">
          {resolution.title}
        </p>
        <p className="mt-2 text-[10px] font-semibold leading-snug opacity-90">
          {resolution.summary}
        </p>

        {whatChanged.length > 0 && (
          <div className="mt-3">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{at("cards.whatChanged")}</div>
            <div className="mt-1 space-y-1">
              {whatChanged.map((item, index) => (
                <p key={`changed-${index}`} className="text-[10px] font-semibold leading-snug opacity-90">
                  {item}
                </p>
              ))}
            </div>
          </div>
        )}

        {whatNext.length > 0 && (
          <div className="mt-3">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{at("cards.nextSafeStep")}</div>
            <div className="mt-1 space-y-1">
              {whatNext.map((item, index) => (
                <p key={`follow-${index}`} className="text-[10px] font-semibold leading-snug opacity-90">
                  {item}
                </p>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderOperatorReadoutCard = (message) => {
    if (!shouldRenderOperatorReadout(message)) return null;

    const summary = getMessageSummary(message);
    const risk = getMessageRiskSummary(message);
    const next = getMessageNextBestAction(message);
    const reason = getMessageReviewReason(message);
    const intent = message?.intent || message?.flow || message?.state?.current_flow || "context_explain";
    const tone = ["general_help", "product_help"].includes(intent)
      ? "border-sky-100 dark:border-sky-900/50 bg-sky-50/60 dark:bg-sky-950/20 text-sky-700 dark:text-sky-300"
      : ["mission_control_explain", "priority_engine"].includes(intent)
        ? "border-violet-100 dark:border-violet-900/50 bg-violet-50/60 dark:bg-violet-950/20 text-violet-700 dark:text-violet-300"
        : "border-slate-200 dark:border-slate-800 bg-white/75 dark:bg-slate-950/35 text-slate-700 dark:text-slate-300";

    return (
      <div className={`mt-3 rounded-xl border px-3 py-3 ${tone}`}>
        <div className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest">
          <Shield size={11} />
          {at("cards.operatorReadout")}
        </div>
        {summary && summary !== message?.text && (
          <p className="mt-1 text-[11px] font-black leading-snug text-slate-900 dark:text-slate-100">
            {summary}
          </p>
        )}
        {reason && (
          <p className="mt-2 text-[10px] font-semibold leading-snug opacity-90">
            {reason}
          </p>
        )}
        {(risk || next) && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
            {risk && (
              <div className="rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
                <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{at("cards.riskFrame")}</div>
                <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{risk}</p>
              </div>
            )}
            {next && (
              <div className="rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
                <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{at("cards.nextStep")}</div>
                <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{next}</p>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderDecisionReviewV3Card = (analysis) => {
    if (!analysis?.decision_status) return null;
    const tone = analysis.decision_status === "block"
      ? "border-rose-100 dark:border-rose-900/50 bg-rose-50/60 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300"
      : analysis.decision_status === "modify" || analysis.decision_status === "insufficient_context"
        ? "border-amber-100 dark:border-amber-900/50 bg-amber-50/60 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300"
        : "border-emerald-100 dark:border-emerald-900/50 bg-emerald-50/60 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300";
    const checks = Array.isArray(analysis.checks) ? analysis.checks.slice(0, 4) : [];
    const blockers = Array.isArray(analysis.top_blockers) ? analysis.top_blockers.slice(0, 3) : [];
    const changes = Array.isArray(analysis.recommended_changes) ? analysis.recommended_changes.slice(0, 3) : [];
    return (
      <div className={`mt-3 rounded-xl border px-3 py-3 ${tone}`}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest">
              <FileText size={11} />
              {at("cards.decisionReview")}
            </div>
            <p className="mt-1 text-[11px] font-black leading-snug text-slate-900 dark:text-slate-100">
              {analysis.headline || uiText.decisionReviewFallback}
            </p>
          </div>
          <span className="rounded-full bg-white/80 dark:bg-slate-950/40 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest">
            {analysis.decision_status}
          </span>
        </div>
        {analysis.risk_summary && (
          <p className="mt-2 text-[10px] font-semibold leading-snug opacity-90">
            {analysis.risk_summary}
          </p>
        )}
        {analysis.summary && (
          <p className="mt-2 text-[10px] font-semibold leading-snug opacity-90">
            {analysis.summary}
          </p>
        )}
        {checks.length > 0 && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
            {checks.map((check) => (
              <div key={check.id || check.label} className="rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[8px] font-black uppercase tracking-widest">{check.label}</span>
                  <span className="text-[7px] font-black uppercase tracking-widest opacity-70">{check.status}</span>
                </div>
                <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{check.detail}</p>
              </div>
            ))}
          </div>
        )}
        {blockers.length > 0 && (
          <div className="mt-3">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{at("cards.mainBlockers")}</div>
            <div className="mt-1 space-y-1">
              {blockers.map((item, index) => (
                <p key={`decision-blocker-${index}`} className="text-[10px] font-semibold leading-snug opacity-90">{item}</p>
              ))}
            </div>
          </div>
        )}
        {changes.length > 0 && (
          <div className="mt-3 rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{at("cards.recommendedAdjustment")}</div>
            <div className="mt-1 space-y-1">
              {changes.map((item, index) => (
                <p key={`decision-change-${index}`} className="text-[10px] font-semibold leading-snug opacity-90">{item}</p>
              ))}
            </div>
          </div>
        )}
        {(analysis.review_reason || analysis.operator_next_step || analysis.next_best_action) && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
            {analysis.review_reason && (
              <div className="rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
                <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{at("cards.whyNow")}</div>
                <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{analysis.review_reason}</p>
              </div>
            )}
            {(analysis.operator_next_step || analysis.next_best_action) && (
              <div className="rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
                <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{at("cards.nextStep")}</div>
                <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{analysis.operator_next_step || analysis.next_best_action}</p>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderPlanAdherenceCard = (analysis) => {
    if (!analysis?.adherence_status) return null;
    const tone = analysis.adherence_status === "in_plan"
      ? "border-emerald-100 dark:border-emerald-900/50 bg-emerald-50/60 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300"
      : analysis.adherence_status === "insufficiently_justified"
        ? "border-amber-100 dark:border-amber-900/50 bg-amber-50/60 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300"
        : "border-rose-100 dark:border-rose-900/50 bg-rose-50/60 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300";
    return (
      <div className={`mt-3 rounded-xl border px-3 py-3 ${tone}`}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest">
              <Shield size={11} />
              {at("cards.planAdherence")}
            </div>
            <p className="mt-1 text-[11px] font-black leading-snug text-slate-900 dark:text-slate-100">
              {analysis.headline || at("cards.planAdherenceFallback")}
            </p>
          </div>
          <span className="rounded-full bg-white/80 dark:bg-slate-950/40 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest">
            {analysis.adherence_status}
          </span>
        </div>
        {analysis.adherence_reason && (
          <p className="mt-2 text-[10px] font-semibold leading-snug opacity-90">{analysis.adherence_reason}</p>
        )}
        {analysis.summary && (
          <p className="mt-2 text-[10px] font-semibold leading-snug opacity-90">{analysis.summary}</p>
        )}
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-2">
          {analysis.threatened_rule && (
            <div className="rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
              <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{at("cards.threatenedRule")}</div>
              <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{analysis.threatened_rule}</p>
            </div>
          )}
          {analysis.discipline_score !== undefined && analysis.discipline_score !== null && (
            <div className="rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
              <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{at("cards.disciplineScore")}</div>
              <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{analysis.discipline_score}/100</p>
            </div>
          )}
          {analysis.week_delta && (
            <div className="rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
              <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{at("cards.weekOverWeek")}</div>
              <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{analysis.week_delta}</p>
            </div>
          )}
        </div>
        {analysis.suggested_recovery_step && (
          <div className="mt-3 rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{at("cards.recoveryStep")}</div>
            <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{analysis.suggested_recovery_step}</p>
          </div>
        )}
      </div>
    );
  };

  const renderOutcomeTrackingCard = (analysis) => {
    if (!analysis?.historical_result_summary && analysis?.sample_size === undefined) return null;
    return (
      <div className="mt-3 rounded-xl border border-emerald-100 dark:border-emerald-900/50 bg-emerald-50/60 dark:bg-emerald-950/20 px-3 py-3 text-emerald-700 dark:text-emerald-300">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest">
              <BarChart3 size={11} />
              {at("cards.outcomeTracking")}
            </div>
            <p className="mt-1 text-[11px] font-black leading-snug text-slate-900 dark:text-slate-100">
              {analysis.headline || at("cards.outcomeTrackingFallback")}
            </p>
          </div>
          {analysis.sample_size !== undefined && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/40 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest">
              n={analysis.sample_size}
            </span>
          )}
        </div>
        {analysis.historical_result_summary && (
          <p className="mt-2 text-[10px] font-semibold leading-snug opacity-90">{analysis.historical_result_summary}</p>
        )}
        {analysis.net_effect && (
          <p className="mt-2 text-[10px] font-semibold leading-snug opacity-90">{analysis.net_effect}</p>
        )}
        {analysis.confidence_note && (
          <p className="mt-2 text-[9px] font-black uppercase tracking-widest opacity-70">{analysis.confidence_note}</p>
        )}
        {analysis.operator_next_step && (
          <div className="mt-3 rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{at("cards.nextStep")}</div>
            <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{analysis.operator_next_step}</p>
          </div>
        )}
      </div>
    );
  };

  const renderPriorityEngineCard = (analysis) => {
    const priorities = Array.isArray(analysis?.top_priorities) ? analysis.top_priorities.slice(0, 3) : [];
    if (!analysis?.headline && priorities.length === 0) return null;
    return (
      <div className="mt-3 rounded-xl border border-violet-100 dark:border-violet-900/50 bg-violet-50/60 dark:bg-violet-950/20 px-3 py-3 text-violet-700 dark:text-violet-300">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest">
              <Target size={11} />
              {at("cards.priorityEngine")}
            </div>
            <p className="mt-1 text-[11px] font-black leading-snug text-slate-900 dark:text-slate-100">
              {analysis.headline || at("cards.priorityEngineFallback")}
            </p>
          </div>
          {analysis.open_counts?.high_priority_count !== undefined && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/40 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest">
              {analysis.open_counts.high_priority_count} {at("cards.high")}
            </span>
          )}
        </div>
        {analysis.why_now && (
          <p className="mt-2 text-[10px] font-semibold leading-snug opacity-90">{analysis.why_now}</p>
        )}
        {priorities.length > 0 && (
          <div className="mt-3 space-y-1.5">
            {priorities.map((item, index) => (
              <div key={`${item.id || item.title}-${index}`} className="rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-black leading-tight text-slate-900 dark:text-slate-100">{item.title}</span>
                  <span className="text-[7px] font-black uppercase tracking-widest opacity-70">{item.lane || item.priority}</span>
                </div>
                {(item.why_now || item.source_reason) && (
                  <p className="mt-1 text-[9px] font-semibold leading-snug opacity-90">{item.why_now || item.source_reason}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderMemoryV2Card = (analysis) => {
    if (!analysis?.memory_pattern) return null;
    return (
      <div className="mt-3 rounded-xl border border-fuchsia-100 dark:border-fuchsia-900/50 bg-fuchsia-50/60 dark:bg-fuchsia-950/20 px-3 py-3 text-fuchsia-700 dark:text-fuchsia-300">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest">
              <Brain size={11} />
              {uiText.memoryV2}
            </div>
            <p className="mt-1 text-[11px] font-black leading-snug text-slate-900 dark:text-slate-100">
              {analysis.memory_pattern}
            </p>
          </div>
          <span className="rounded-full bg-white/80 dark:bg-slate-950/40 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest">
            {humanizeSurfaceStatus(analysis.confidence_level || "early")}
          </span>
        </div>
        {analysis.behavioral_cost && (
          <p className="mt-2 text-[10px] font-semibold leading-snug opacity-90">{analysis.behavioral_cost}</p>
        )}
        {analysis.recommended_rule && (
          <div className="mt-3 rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2">
            <div className="text-[8px] font-black uppercase tracking-widest opacity-70">{governanceCopy.recommendedRule}</div>
            <p className="mt-1 text-[10px] font-semibold leading-snug opacity-90">{analysis.recommended_rule}</p>
          </div>
        )}
      </div>
    );
  };

  const renderPortfolioOperatingSystemCard = (analysis) => {
    const nextActions = Array.isArray(analysis?.next_best_actions) ? analysis.next_best_actions.slice(0, 3) : [];
    if (!analysis?.operating_posture && nextActions.length === 0) return null;
    return (
      <div className="mt-3 rounded-xl border border-cyan-100 dark:border-cyan-900/50 bg-cyan-50/60 dark:bg-cyan-950/20 px-3 py-3 text-cyan-700 dark:text-cyan-300">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest">
              <Bot size={11} />
              {governanceCopy.portfolioOperatingSystem}
            </div>
            <p className="mt-1 text-[11px] font-black leading-snug text-slate-900 dark:text-slate-100">
              {analysis.control_plane?.headline || governanceCopy.headlineFallback}
            </p>
          </div>
          {analysis.operating_posture && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/40 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest">
              {humanizeSurfaceStatus(analysis.operating_posture)}
            </span>
          )}
        </div>
        {analysis.control_plane?.why_now && (
          <p className="mt-2 text-[10px] font-semibold leading-snug opacity-90">{analysis.control_plane.why_now}</p>
        )}
        {nextActions.length > 0 && (
          <div className="mt-3 space-y-1.5">
            {nextActions.map((item, index) => (
              <div key={`${item}-${index}`} className="rounded-lg bg-white/80 dark:bg-slate-950/35 px-2.5 py-2 text-[10px] font-semibold leading-snug opacity-90">
                {item}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const missionWorkqueueSections = () => {
    if (Array.isArray(missionControl?.workqueue_groups) && missionControl.workqueue_groups.length > 0) {
      return missionControl.workqueue_groups.map((group) => ({
        key: group.key,
        title: group.label || missionControl?.workqueue_labels?.[group.key] || group.key,
        tone: group.key === "first" ? "rose" : group.key === "review" ? "amber" : "slate",
        items: Array.isArray(group.items) ? group.items : [],
      })).filter((section) => section.items.length > 0);
    }

    const items = Array.isArray(missionControl?.workqueue) ? missionControl.workqueue : [];
    const first = [];
    const review = [];
    const later = [];

    items.forEach((item) => {
      const state = item.resolve_state || item.status;
      if (state === "needs_user_confirmation" || state === "waiting_for_data" || item.freshness?.status === "stale") {
        first.push(item);
      } else if (state === "monitor_today" || item.type === "blocked_plan" || item.type === "blocker_explanation") {
        review.push(item);
      } else {
        later.push(item);
      }
    });

    return [
      { key: "first", title: uiText.firstThis, tone: "rose", items: first },
      { key: "review", title: uiText.thenReview, tone: "amber", items: review },
      { key: "later", title: uiText.canWait, tone: "slate", items: later },
    ].filter((section) => section.items.length > 0);
  };

  const missionSectionTone = (tone) => {
    if (tone === "rose") return "border-rose-100 dark:border-rose-900/50 bg-rose-50/45 dark:bg-rose-950/15";
    if (tone === "amber") return "border-amber-100 dark:border-amber-900/50 bg-amber-50/45 dark:bg-amber-950/15";
    return "border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/40";
  };

  const missionItemTone = (item) => {
    if ((item.resolve_state || item.status) === "needs_user_confirmation") return "border-blue-100 dark:border-blue-900/50 bg-blue-50/50 dark:bg-blue-950/20";
    if ((item.resolve_state || item.status) === "waiting_for_data") return "border-amber-100 dark:border-amber-900/50 bg-amber-50/50 dark:bg-amber-950/20";
    return "border-slate-100 dark:border-slate-800 bg-white/70 dark:bg-slate-950/30";
  };

  const missionPrimaryAction = (item) => item.next_best_action?.prompt ? item.next_best_action : item.resolve_action;

  const coachingLoopAction = (item) => item?.action || null;

  const missionIdentityKey = (item) => {
    if (!item || typeof item !== "object") return null;
    if (item.decision_id) return `decision:${item.decision_id}`;
    const sourceDecisionId = item.source_ids?.decision_id;
    if (sourceDecisionId) return `decision:${sourceDecisionId}`;
    const botId = item.bot_id || item.source_ids?.bot_id;
    const asset = String(item.asset || item.source_ids?.asset || "").trim().toUpperCase();
    const issueType = String(item.type || item.status || item.resolve_state || item.label || "item").trim().toLowerCase();
    if (botId) return `bot:${botId}:${asset}:${issueType}`;
    return item.id || `${asset}:${issueType}:${item.title || item.reason || "item"}`;
  };

  const dedupeMissionItems = (items = [], seen = new Set(), limit = Infinity) => {
    const unique = [];
    for (const item of items) {
      if (!item) continue;
      const key = missionIdentityKey(item);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      unique.push(item);
      if (unique.length >= limit) break;
    }
    return unique;
  };

  const isReviewMissionItem = (item) => {
    const type = String(item?.type || "").toLowerCase();
    const status = String(item?.status || item?.resolve_state || "").toLowerCase();
    return Boolean(
      item?.decision_id ||
      type.includes("bot_decision") ||
      status.includes("review") ||
      String(item?.title || "").toLowerCase().includes("review")
    );
  };

  const isRiskMissionItem = (item) => {
    const type = String(item?.type || "").toLowerCase();
    const status = String(item?.status || item?.resolve_state || "").toLowerCase();
    return [
      "blocked_plan",
      "portfolio_risk_stack",
      "portfolio_live_hotspot",
      "blocker_explanation",
      "data_gap",
      "indicator_gap",
    ].includes(type) || [
      "blocked",
      "blocked_by_data",
      "stacked_risk",
      "live_hotspot",
      "waiting_for_data",
      "monitor_today",
    ].includes(status);
  };

  const humanizePlanHealthTitle = (plan = {}) => {
    const asset = String(plan?.asset || context.symbol || globalSymbol || "BTC").trim().toUpperCase();
    const status = String(plan?.status || "").toLowerCase();
    if (status === "blocked") return `${asset} wacht op vrijgave`;
    if (status === "data_missing") return `${asset} mist nog data`;
    return `${asset} vraagt aandacht`;
  };

  const humanizePlanHealthReason = (plan = {}) => {
    const asset = String(plan?.asset || context.symbol || globalSymbol || "BTC").trim().toUpperCase();
    const status = String(plan?.status || "").toLowerCase();
    if (status === "blocked") {
      return plan?.reason || `${asset} staat klaar, maar wordt nu nog geblokkeerd door je setup- of risicoregels.`;
    }
    if (status === "data_missing") {
      return plan?.reason || `${asset} mist nog score- of indicatorcontext voordat Finn dit veilig kan vrijgeven.`;
    }
    return plan?.reason || `${asset} vraagt eerst een korte controle voordat je verdergaat.`;
  };

  const humanizeRiskClusterTitle = (item = {}) => {
    const asset = String(item?.asset || context.symbol || globalSymbol || "BTC").trim().toUpperCase();
    const type = String(item?.type || "").toLowerCase();
    const title = String(item?.title || "").toLowerCase();
    if (type === "blocked_plan" || title.includes("vrijgave")) {
      return `${asset} staat nu op pauze`;
    }
    if (type === "portfolio_risk_stack" || title.includes("risico stapelt")) {
      return `${asset} risico ligt te hoog`;
    }
    if (type === "agent_verdict" || title.includes("agent")) {
      return `${asset} vraagt extra check`;
    }
    if (type === "portfolio_live_hotspot") {
      return `${asset} live bots vragen aandacht`;
    }
    return item?.title || `${asset} vraagt aandacht`;
  };

  const humanizeRiskClusterReason = (item = {}) => {
    const asset = String(item?.asset || context.symbol || globalSymbol || "BTC").trim().toUpperCase();
    const type = String(item?.type || "").toLowerCase();
    const reason = String(item?.reason || "").trim();
    if (type === "blocked_plan") {
      return reason || `Macro of je setup houdt nieuwe ${asset}-actie vandaag nog tegen.`;
    }
    if (type === "portfolio_risk_stack") {
      return reason || `${asset} stapelt nu risico doordat meerdere regels tegelijk tegen je werken.`;
    }
    if (type === "portfolio_live_hotspot") {
      return reason || `${asset} heeft live bots die extra aandacht vragen voordat je verdergaat.`;
    }
    if (type === "agent_verdict") {
      return reason || `${asset} krijgt nu een remsignaal uit je controles.`;
    }
    return reason || `${asset} vraagt nu eerst extra controle.`;
  };

  const humanizeMissionBadge = (item = {}, section = "") => {
    const raw = String(item?.priority || item?.status || "").toLowerCase();
    const type = String(item?.type || "").toLowerCase();

    if (section === "risk") {
      if (type === "blocked_plan" || raw.includes("block")) return "nu niet";
      if (type === "portfolio_risk_stack" || raw.includes("stack")) return "extra risico";
      if (type === "agent_verdict") return "extra check";
      if (raw.includes("high")) return "oppassen";
      if (raw.includes("medium") || raw.includes("wait")) return "let op";
      return "risico";
    }

    if (raw.includes("high")) return "nu";
    if (raw.includes("medium")) return "straks";
    if (raw.includes("review")) return "review";
    if (raw.includes("block")) return "geblokkeerd";
    return item?.priority || item?.status || null;
  };

  const buildRiskClusters = (items = []) => {
    const grouped = new Map();

    items.forEach((item) => {
      if (!item) return;
      const asset = String(item.asset || context.symbol || globalSymbol || "BTC").trim().toUpperCase();
      const type = String(item.type || "").toLowerCase();
      const groupKey = type === "blocked_plan"
        ? `${asset}:blocked`
        : type === "portfolio_risk_stack"
          ? `${asset}:stack`
          : type === "portfolio_live_hotspot"
            ? `${asset}:hotspot`
            : type === "agent_verdict"
              ? `${asset}:agent`
              : `${asset}:${type || "risk"}`;

      const current = grouped.get(groupKey);
      if (!current) {
        grouped.set(groupKey, {
          ...item,
          asset,
          id: `risk-cluster:${groupKey}`,
          title: humanizeRiskClusterTitle({ ...item, asset }),
          reason: humanizeRiskClusterReason({ ...item, asset }),
        });
        return;
      }

      const reasons = [current.reason, humanizeRiskClusterReason({ ...item, asset })]
        .filter(Boolean)
        .filter((value, index, array) => array.indexOf(value) === index);
      current.reason = reasons[0];

      const priorities = [current.priority, item.priority].filter(Boolean);
      if (priorities.includes("high")) current.priority = "high";
      else if (priorities.includes("medium")) current.priority = "medium";

      if (!current.next_best_action && item.next_best_action) {
        current.next_best_action = item.next_best_action;
      }
    });

    return Array.from(grouped.values()).slice(0, 4);
  };

  const humanizeHistoryTitle = (item = {}) => {
    const asset = String(item?.asset || context.symbol || globalSymbol || "BTC").trim().toUpperCase();
    const label = String(item?.label || item?.type || "").toLowerCase();
    const outcome = String(item?.outcome || "").toLowerCase();
    const status = String(item?.status || "").toLowerCase();

    if (label.includes("review") || outcome.includes("review")) return `${asset} review bekeken`;
    if (label.includes("blok") || outcome.includes("blok")) return `${asset} blokkade bekeken`;
    if (status === "snoozed" || outcome.includes("later")) return `${asset} punt uitgesteld`;
    if (status === "resolved" || status === "executed") return `${asset} stap afgerond`;
    if (status === "failed") return `${asset} stap mislukte`;
    return `${asset} Finn-stap bijgewerkt`;
  };

  const humanizeHistoryReason = (item = {}) => {
    const outcome = String(item?.outcome || "").trim();
    const status = String(item?.status || "").toLowerCase();
    if (outcome) return outcome;
    if (status === "snoozed") return uiText.historyReasonSnoozed;
    if (status === "resolved" || status === "executed") return uiText.historyReasonResolved;
    if (status === "failed") return uiText.historyReasonFailed;
    return uiText.historyReasonRecent;
  };

  const humanizeHistoryStatus = (item = {}) => {
    const status = String(item?.status || "").toLowerCase();
    if (status === "executed" || status === "resolved") return uiText.historyStatusResolved;
    if (status === "snoozed") return uiText.historyStatusSnoozed;
    if (status === "failed") return uiText.historyStatusFailed;
    return uiText.historyStatusRecent;
  };

  const buildMissionOverlaySections = () => {
    const seen = new Set();

    const priorityCandidates = [
      ...(missionControl?.coaching_loop?.daily_priority_stack || []),
      ...(missionControl?.workqueue || []).filter((item) => {
        const state = String(item?.resolve_state || item?.status || "").toLowerCase();
        return [
          "needs_user_confirmation",
          "review_ready",
          "blocked",
          "blocked_by_data",
          "waiting_for_data",
        ].includes(state);
      }),
    ].filter(Boolean).sort((a, b) => scoreMissionForProfile(b) - scoreMissionForProfile(a));
    const todayItems = dedupeMissionItems(priorityCandidates, seen, 3);

    const reviewCandidates = getOpenReviewCandidates(missionControl).filter(Boolean).sort((a, b) => scoreMissionForProfile(b) - scoreMissionForProfile(a));
    const totalReviewCount = countUniqueReviewCandidates(missionControl);
    const allReviewItems = dedupeMissionItems(reviewCandidates, new Set(), 6);
    const todayReviewKeys = new Set(
      todayItems.filter((item) => isReviewCandidate(item)).map((item) => reviewIdentityKey(item))
    );
    const reviewItems = allReviewItems.filter((item) => !todayReviewKeys.has(reviewIdentityKey(item)));

    const blockedPlans = (missionControl?.plan_health || [])
      .filter((item) => item?.status && item.status !== "active")
      .map((item) => ({
        ...item,
        id: `plan-health:${item.asset}:${item.status}:${item.setup?.id || "none"}`,
        type: item.status === "data_missing" ? "data_gap" : "blocked_plan",
        title: humanizePlanHealthTitle(item),
        reason: humanizePlanHealthReason(item),
      }));

    const verdictRiskItems = (missionControl?.agent_verdicts || [])
      .filter((verdict) => {
        const status = String(verdict?.status || "").toLowerCase();
        return !["clear", "quiet", "ready", "no_open_decision", "no_decision", "stable"].includes(status);
      })
      .slice(0, 3)
      .map((verdict, index) => ({
        id: `verdict:${verdict.agent || index}`,
        type: "agent_verdict",
        asset: verdict.asset || context.symbol || globalSymbol || null,
        title: verdict.label || uiText.riskAgent,
        reason: verdict.reason,
        status: verdict.status,
        next_best_action: verdict.next_action
          ? {
              type: "chat_prompt",
              label: verdict.label ? `${uiText.whyLabelPrefix} ${verdict.label}?` : uiText.whyBlocked,
              prompt: verdict.next_action,
              handoff: "daily_coach",
              requires_confirmation: false,
            }
          : null,
      }));

    const portfolioRiskItems = [
      ...((missionControl?.portfolio_risk?.risk_stacks || []).slice(0, 3).map((stack, index) => {
        const asset = String(stack.asset || uiText.portfolioAssetFallback || "BTC").toUpperCase();
        const promptTemplate = uiText.riskStackPrompt || "Welke risico's stapelen nu voor {asset}?";

        return {
          id: `risk-stack:${stack.asset || index}`,
          type: "portfolio_risk_stack",
          asset: stack.asset,
          title: `${asset} ${uiText.riskStackTitleSuffix || ""}`.trim(),
          reason: stack.reason,
          risk_score: stack.risk_score,
          next_best_action: {
            type: "chat_prompt",
            label: `${asset} ${uiText.riskStackExplainLabelSuffix || ""}`.trim(),
            prompt: interpolateTranslation(promptTemplate, { asset }),
            handoff: "daily_coach",
            requires_confirmation: false,
          },
        };
      }) || []),
      ...((missionControl?.portfolio_risk?.live_bot_hotspots || []).slice(0, 2).map((hotspot, index) => ({
        id: `live-hotspot:${hotspot.asset || index}`,
        type: "portfolio_live_hotspot",
        asset: hotspot.asset,
        title: `${String(hotspot.asset || uiText.portfolioAssetFallback).toUpperCase()} ${uiText.liveBotsNeedAttention}`,
        reason: hotspot.summary || hotspot.reason,
        risk_score: hotspot.risk_score,
      })) || []),
    ];

    const riskCandidates = [...blockedPlans, ...portfolioRiskItems, ...verdictRiskItems]
      .filter(Boolean)
      .sort((a, b) => scoreMissionForProfile(b) - scoreMissionForProfile(a));
    const riskItems = buildRiskClusters(dedupeMissionItems(riskCandidates, seen, 8));

    const performanceCards = [];
    if (missionControl?.day_log) {
      const resolvedCount = missionControl.day_log.resolved_count || 0;
      const snoozedCount = missionControl.day_log.snoozed_count || 0;
      let rhythmSummary = null;
      if (resolvedCount > 0 && snoozedCount > 0) {
        rhythmSummary = uiText.rhythmSummaryMixed;
      } else if (resolvedCount > 0) {
        rhythmSummary = uiText.rhythmSummaryDone;
      } else if (snoozedCount > 0) {
        rhythmSummary = uiText.rhythmSummarySnoozed;
      } else if ((missionControl.day_log.handled_count || 0) > 0) {
        rhythmSummary = uiText.rhythmSummaryActive;
      }

      if (rhythmSummary) {
        performanceCards.push({
          key: "day-log",
          title: uiText.rhythmToday,
          summary: rhythmSummary,
          tone: "neutral",
        });
      }
    }
    if (missionControl?.behavioral_insight?.coaching) {
      performanceCards.push({
        key: "behavior",
        title: uiText.behaviorDiscipline,
        summary: missionControl.behavioral_insight.coaching.primary_reflection,
        status: behavioralStatusLabel(missionControl?.behavioral_insight?.status),
        tone: missionControl?.behavioral_insight?.status === "attention" ? "attention" : "positive",
      });
    }
    const historyItems = (missionControl?.activity_feed || [])
      .filter((item) => {
        const status = String(item?.status || "").toLowerCase();
        return ![
          "needs_user_confirmation",
          "review_ready",
          "blocked",
          "blocked_by_data",
          "waiting_for_data",
          "pending",
        ].includes(status);
      })
      .filter(Boolean)
      .slice(0, 6);

    return {
      todayItems,
      totalReviewCount,
      reviewItems: reviewItems.slice(0, 6),
      riskItems,
      performanceCards: performanceCards.slice(0, 2),
      historyItems,
    };
  };

  const renderMissionActionRow = (item, section) => {
    const action = missionPrimaryAction(item) || coachingLoopAction(item) || item?.next_best_action || item?.action || null;
    const resolveActions = Array.isArray(item?.resolve_actions) ? item.resolve_actions : [];
    const markDone = resolveActions.find((candidate) => candidate?.resolution === "resolved");
    const snooze = resolveActions.find((candidate) => candidate?.resolution === "snoozed");

    return (
      <div className="mt-3 space-y-2">
        {action && (
          <button
            type="button"
            onClick={() => handleFollowUpAction(action, item)}
            disabled={executingAction}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-3 py-3 text-[11px] font-black text-white shadow-lg shadow-blue-600/15 transition-colors hover:bg-blue-700 disabled:opacity-60"
          >
            {followUpIcon(action.handoff || action.type)}
            <span className="leading-tight">{humanizeActionLabel(action, item)}</span>
          </button>
        )}
        {(section === "today" || section === "reviews") && (markDone || snooze) && (
          <div className="flex flex-wrap gap-2">
            {markDone && (
              <button
                type="button"
                onClick={() => handleMissionPrimaryAction(markDone)}
                disabled={executingAction}
                className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-white px-3 py-1.5 text-[10px] font-black text-emerald-700 transition hover:bg-emerald-50 disabled:opacity-60 dark:border-emerald-900/50 dark:bg-slate-950/40 dark:text-emerald-300"
              >
                <CheckCircle2 size={11} />
                {uiText.markDone}
              </button>
            )}
            {snooze && (
              <button
                type="button"
                onClick={() => handleMissionPrimaryAction(snooze)}
                disabled={executingAction}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-black text-slate-600 transition hover:bg-slate-50 disabled:opacity-60 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-300"
              >
                <Activity size={11} />
                {uiText.reviewLater}
              </button>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderMissionSectionCard = (item, section) => {
    if (!item) return null;
    const tone = section === "today"
      ? "border-blue-100 dark:border-blue-900/50 bg-blue-50/45 dark:bg-blue-950/15"
      : section === "reviews"
        ? "border-violet-100 dark:border-violet-900/50 bg-violet-50/45 dark:bg-violet-950/15"
        : "border-rose-100 dark:border-rose-900/50 bg-rose-50/45 dark:bg-rose-950/15";
    const behavioralBadge = humanizeBehavioralPriorityBadge(item);

    return (
      <div key={missionIdentityKey(item) || item.id || item.title} className={`rounded-xl border px-3 py-3 ${tone}`}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-black leading-snug text-slate-900 dark:text-slate-100">
              {section === "risk" && !isReviewMissionItem(item)
                ? (item.title || humanizePlanHealthTitle(item))
                : humanizeMissionTitle(item)}
            </p>
            <p className="mt-1 text-[10px] font-semibold leading-snug text-slate-600 dark:text-slate-300">
              {section === "risk" && !isReviewMissionItem(item)
                ? (item.reason || humanizePlanHealthReason(item))
                : humanizeMissionReason(item)}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            {humanizeMissionBadge(item, section) && (
              <span className={`text-[8px] font-black uppercase tracking-widest ${
                String(item.priority || item.status).toLowerCase().includes("high") || String(item.status || "").toLowerCase().includes("block")
                  ? "text-rose-600"
                  : String(item.priority || item.status).toLowerCase().includes("medium") || String(item.status || "").toLowerCase().includes("wait")
                    ? "text-amber-600"
                    : "text-emerald-600"
              }`}>
                {humanizeMissionBadge(item, section)}
              </span>
            )}
            {behavioralBadge && (
              <span className={`rounded-full border px-2 py-0.5 text-[7px] font-black uppercase tracking-widest ${behavioralPriorityBadgeTone(item)}`}>
                {behavioralBadge}
              </span>
            )}
          </div>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {item.asset && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/50 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
              {item.asset}
            </span>
          )}
          {item.freshness?.label && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/50 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
              {item.freshness.label}
            </span>
          )}
          {item.review_status && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/50 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
              {item.review_status}
            </span>
          )}
          {typeof item.confidence === "number" && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/50 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
              conf {Math.round(item.confidence * 100)}%
            </span>
          )}
        </div>
        {item.behavioral_priority_reason && (
          <div className="mt-2 rounded-lg border border-white/80 dark:border-slate-900/40 bg-white/70 dark:bg-slate-950/35 px-2.5 py-2">
            <div className="text-[7px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
              {uiText.finnBrakesBecause}
            </div>
            <p className="mt-1 text-[9px] font-semibold leading-snug text-slate-600 dark:text-slate-300">
              {item.behavioral_priority_reason}
            </p>
          </div>
        )}
        {renderMissionActionRow(item, section)}
      </div>
    );
  };

  const renderMissionHistoryEntry = (item) => {
    if (!item) return null;
    return (
      <div key={item.id} className="rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/40 px-3 py-2">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[11px] font-black text-slate-800 dark:text-slate-100 leading-tight">
            {humanizeHistoryTitle(item)}
          </span>
          <span className={`text-[8px] font-black uppercase tracking-widest ${
            item.status === "executed" || item.status === "resolved"
              ? "text-emerald-600"
              : item.status === "failed"
                ? "text-rose-600"
                : "text-slate-400"
          }`}>
            {humanizeHistoryStatus(item)}
          </span>
        </div>
        <p className="mt-1 text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
          {humanizeHistoryReason(item)}
        </p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {item.asset && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/50 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
              {item.asset}
            </span>
          )}
          {item.agent_accountability?.dominant_label && (
            <span className="rounded-full bg-blue-50 dark:bg-blue-950/40 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-blue-600 dark:text-blue-300">
              {item.agent_accountability.dominant_label}
            </span>
          )}
        </div>
      </div>
    );
  };

  const handleMissionPrimaryAction = async (action) => {
    if (!action) return;
    if (action.prompt) {
      await handleFollowUpAction(action);
      return;
    }
    if (action.type) {
      await handleExecuteAction(action);
    }
  };

  const buildPriorityDrillIn = (item) => {
    if (!item) return null;
    const asset = item.asset || null;
    const type = String(item.type || "").toLowerCase();
    const title = String(item.title || "").toLowerCase();
    const action = item.action || null;

    if (action?.handoff === "bot_execution_console" || type.includes("bot") || title.includes("bot")) {
      return {
        label: asset ? uiText.openBotFlowFor.replace("{asset}", asset) : uiText.openBotFlow,
        run: () => openExecutionConsole({ ...action, asset }),
      };
    }
    if (type.includes("setup") || title.includes("setup")) {
      return {
        label: asset ? uiText.openSetupFor.replace("{asset}", asset) : uiText.openSetup,
        run: () => {
          router.push(asset ? `/setup?symbol=${asset}` : "/setup");
          setIsOpen(false);
        },
      };
    }
    if (type.includes("strategy") || title.includes("strategie") || title.includes("strategy") || type.includes("blocked_plan")) {
      return {
        label: asset ? uiText.openStrategyFor.replace("{asset}", asset) : uiText.openStrategy,
        run: () => {
          router.push(asset ? `/setup?symbol=${asset}` : "/setup");
          setIsOpen(false);
        },
      };
    }
    if (type.includes("portfolio") || title.includes("portfolio") || title.includes("risico")) {
      return {
        label: asset ? `Open ${asset} bot desk` : "Open portfolio desk",
        run: () => {
          router.push(asset ? `/bot?symbol=${asset}` : "/bot");
          setIsOpen(false);
        },
      };
    }
    if (action?.prompt) {
      return {
        label: action.label || "Open in chat",
        run: () => handleFollowUpAction(action),
      };
    }
    return null;
  };

  const renderCoachingLoopEntry = (item, tone = "slate") => {
    if (!item) return null;
    const action = coachingLoopAction(item);
    const toneClasses = tone === "rose"
      ? "border-rose-100 dark:border-rose-900/50 bg-rose-50/50 dark:bg-rose-950/20"
      : tone === "amber"
        ? "border-amber-100 dark:border-amber-900/50 bg-amber-50/50 dark:bg-amber-950/20"
        : "border-slate-100 dark:border-slate-800 bg-white/70 dark:bg-slate-950/30";

    return (
      <div key={item.id || item.title} className={`rounded-xl border px-3 py-2 ${toneClasses}`}>
        <div className="flex items-center justify-between gap-3">
          <span className="text-[11px] font-black text-slate-800 dark:text-slate-100 leading-tight">
            {humanizeMissionTitle(item)}
          </span>
          {item.priority && (
            <span className={`text-[8px] font-black uppercase tracking-widest ${
              item.priority === "high" ? "text-rose-600" : item.priority === "medium" ? "text-amber-600" : "text-emerald-600"
            }`}>
              {item.priority}
            </span>
          )}
        </div>
        {item.reason && (
          <p className="mt-1 text-[10px] font-semibold text-slate-500 dark:text-slate-400 leading-snug">
            {humanizeMissionReason(item)}
          </p>
        )}
        {item.why_now && (
          <p className="mt-1 text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
            {item.why_now}
          </p>
        )}
        {Array.isArray(item.supporting_signals) && item.supporting_signals.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {item.supporting_signals.slice(0, 4).map((signal) => (
              <span
                key={`${item.id || item.title}-${signal}`}
                className="rounded-full bg-white/80 dark:bg-slate-950/50 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400"
              >
                {signal}
              </span>
            ))}
          </div>
        )}
        {action && (
          <button
            type="button"
            onClick={() => handleFollowUpAction(action, item)}
            disabled={executingAction}
            className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-blue-100 dark:border-blue-900/40 bg-white/80 dark:bg-slate-950/50 px-3 py-2 text-[10px] font-black uppercase tracking-wider text-blue-700 dark:text-blue-300 shadow-sm transition-all hover:border-blue-300 dark:hover:border-blue-700 hover:bg-blue-50 dark:hover:bg-blue-950/40 active:scale-[0.98] disabled:opacity-60"
          >
            {followUpIcon(action.handoff || action.type)}
            <span className="normal-case tracking-normal text-[11px] leading-tight">{humanizeActionLabel(action, item)}</span>
          </button>
        )}
      </div>
    );
  };

  const renderMissionWorkqueueItem = (item) => {
    const action = missionPrimaryAction(item);
    const resolutionTone = (resolveAction) => {
      const lane = resolveAction?.lane || resolveAction?.resolution;
      if (lane === "done" || lane === "resolved") return "border-emerald-200 dark:border-emerald-900/50 text-emerald-700 dark:text-emerald-300";
      if (lane === "monitor" || lane === "monitor_today") return "border-blue-200 dark:border-blue-900/50 text-blue-700 dark:text-blue-300";
      if (lane === "data" || lane === "waiting_for_data") return "border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-300";
      if (lane === "later" || lane === "snoozed") return "border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300";
      if (lane === "skip" || lane === "skipped") return "border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-300";
      return "border-slate-100 dark:border-slate-800 text-slate-500 dark:text-slate-400";
    };
    return (
      <div key={item.id} className={`rounded-xl border px-3 py-2 ${missionItemTone(item)}`}>
        <div className="flex items-center justify-between gap-3">
          <span className="text-[11px] font-black text-slate-800 dark:text-slate-100 leading-tight">
            {humanizeMissionTitle(item)}
          </span>
          <span className={`text-[8px] font-black uppercase tracking-widest ${
            item.priority === "high" ? "text-rose-600" : item.priority === "medium" ? "text-amber-600" : "text-emerald-600"
          }`}>
            {item.priority}
          </span>
        </div>
        <p className="mt-1 text-[10px] font-semibold text-slate-500 dark:text-slate-400 leading-snug">
          {humanizeMissionReason(item)}
        </p>
        <div className="mt-2 flex flex-wrap gap-1">
          <span className="rounded-full bg-white/80 dark:bg-slate-950/50 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
            {missionResolveLabel(item.resolve_state || item.status)}
          </span>
          {item.resolve_state && item.status && item.resolve_state !== item.status && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/50 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-slate-400">
              {item.status}
            </span>
          )}
          {item.freshness?.status && (
            <span className={`rounded-full bg-white/80 dark:bg-slate-950/50 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest ${
              item.freshness.status === "stale" ? "text-rose-600" : item.freshness.status === "aging" ? "text-amber-600" : "text-slate-500 dark:text-slate-400"
            }`}>
              {item.freshness.label || item.freshness.status}
            </span>
          )}
          {item.asset && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/50 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
              {item.asset}
            </span>
          )}
          {typeof item.health_score === "number" && (
            <span className="rounded-full bg-white/80 dark:bg-slate-950/50 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
              health {item.health_score}
            </span>
          )}
        </div>
        {action && (
          <button
            type="button"
            onClick={() => handleFollowUpAction(action, item)}
            disabled={executingAction}
            className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-blue-100 dark:border-blue-900/40 bg-white/80 dark:bg-slate-950/50 px-3 py-2 text-[10px] font-black uppercase tracking-wider text-blue-700 dark:text-blue-300 shadow-sm transition-all hover:border-blue-300 dark:hover:border-blue-700 hover:bg-blue-50 dark:hover:bg-blue-950/40 active:scale-[0.98] disabled:opacity-60"
          >
            {followUpIcon(action.handoff || action.type)}
            <span className="normal-case tracking-normal text-[11px] leading-tight">{humanizeActionLabel(action, item)}</span>
          </button>
        )}
        {Array.isArray(item.resolve_actions) && item.resolve_actions.length > 0 && (
          <div className="mt-2 space-y-1.5">
            <div className="text-[8px] font-black uppercase tracking-widest text-slate-400">Afhandelen</div>
            <div className="grid grid-cols-2 gap-1.5">
              {item.resolve_actions.slice(0, 4).map((resolveAction) => (
                <button
                  key={resolveAction.id}
                  type="button"
                  onClick={() => handleMissionPrimaryAction(resolveAction)}
                  disabled={executingAction}
                  className={`rounded-lg border bg-white/70 dark:bg-slate-950/40 px-2 py-1.5 text-left transition hover:shadow-sm disabled:opacity-60 ${resolutionTone(resolveAction)}`}
                >
                  <div className="text-[8px] font-black uppercase tracking-wider">
                    {resolveAction.label}
                  </div>
                  {resolveAction.summary && (
                    <div className="mt-0.5 text-[9px] font-semibold normal-case tracking-normal opacity-80 leading-snug">
                      {resolveAction.summary}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

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
      if (metric) {
        setContextMetric({ metric, symbol: symbol || globalSymbol || "BTC", timeframe: timeframe || "1W" });
        setIsOpen(true);
      }
      if (assistantSuppressRestore && assistantFlow) {
        skipNextFinnRestoreRef.current = assistantFlow;
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
    if (isOpen) {
      if (!previewSectionsOnly) {
        loadMissionControl();
      }
      if (isAssetAnalysisPage) {
        loadInsight();
      }
      if (!previewSectionsOnly) {
        loadFinnState();
      }
      if (!previewSectionsOnly && Object.keys(preferences).length === 0) {
        getAssistantPreferences().then(res => setPreferences(res.preferences || {}));
      }
    } else {
      loadedFinnStateRef.current = false;
    }
  }, [isOpen, isAssetAnalysisPage, pathname]);

  useEffect(() => {
    if (!isOpen || !isAssetAnalysisPage) return;
    void loadInsight();
  }, [currentConversationStorageKey, isAssetAnalysisPage, isOpen]);

  useEffect(() => {
    if (!isOpen || previewSectionsOnly) return;
    const generationStatus = String(missionControl?.first_dashboard_context?.generation_status || "").toLowerCase();
    if (!["pending", "generating", "retry_scheduled"].includes(generationStatus)) return;
    const timer = window.setInterval(() => {
      void loadMissionControl();
    }, 4000);
    return () => window.clearInterval(timer);
  }, [isOpen, previewSectionsOnly, missionControl?.first_dashboard_context?.generation_status, currentConversationStorageKey]);

  useEffect(() => {
    if (!isOpen || previewSectionsOnly || sharedSessionRestoreRef.current) return;
    sharedSessionRestoreRef.current = true;

    (async () => {
      try {
        const prefResponse = await getAssistantPreferences();
        const nextPreferences = prefResponse?.preferences || {};
        setPreferences((current) => (Object.keys(current || {}).length ? current : nextPreferences));

        const preferredSessionId = normalizeFinnSessionId(nextPreferences?.[ACTIVE_FINN_SESSION_ID_KEY]);
        const sessions = await getAssistantSessions();
        setAvailableFinnSessions(Array.isArray(sessions) ? sessions : []);
        const latestSessionId = normalizeFinnSessionId(sessions?.[0]?.id);
        const resolvedSessionId = preferredSessionId || latestSessionId;
        if (!resolvedSessionId) return;

        const detail = await getAssistantSessionDetail(resolvedSessionId);
        setActiveFinnSessionId(resolvedSessionId);
        setMessages((current) => (current.length > 0 ? current : mapBackendSessionMessages(detail?.messages)));
      } catch (error) {
        console.warn("Kon gedeelde FINN-sessie niet laden:", error);
      }
    })();
  }, [isOpen, previewSectionsOnly]);

  const persistActiveFinnSessionId = async (sessionId) => {
    const normalized = normalizeFinnSessionId(sessionId);
    if (!normalized) return;
    setActiveFinnSessionId(normalized);
    try {
      await updateAssistantPreferences({
        [ACTIVE_FINN_SESSION_ID_KEY]: normalized,
      });
    } catch (error) {
      console.warn("Kon actieve FINN-sessie niet bewaren:", error);
    }
  };

  const startNewFinnConversation = async () => {
    setActiveFinnSessionId(null);
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
    if (!normalized) return;
    try {
      const detail = await getAssistantSessionDetail(normalized);
      await persistActiveFinnSessionId(normalized);
      setFinnDraft(null);
      setActiveState(null);
      setMessages(mapBackendSessionMessages(detail?.messages));
    } catch (error) {
      console.warn("Kon FINN-sessie niet herstellen:", error);
    }
  };

  async function loadFinnState() {
    if (loadedFinnStateRef.current) return;
    if (finnStateRequestRef.current) return finnStateRequestRef.current;
    if (skipNextFinnRestoreRef.current) {
      loadedFinnStateRef.current = true;
      skipNextFinnRestoreRef.current = null;
      return;
    }
    loadedFinnStateRef.current = true;
    finnStateRequestRef.current = (async () => {
      try {
        const envelope = await fetchFinnState();
        if (!envelope?.has_draft || !envelope.draft) return;
        const indicatorModalRequest = buildIndicatorModalRequest(envelope, context.symbol || globalSymbol || "BTC");

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

        setFinnDraft(indicatorModalRequest ? null : envelope.draft);
        setActiveState(
          indicatorModalRequest
            ? null
            : envelope.state
              ? { ...envelope.state, can_confirm: envelope.can_confirm }
              : null
        );
        setMessages(prev => {
          const alreadyVisible = prev.some((m) =>
            (m.intent === envelope.intent || m.flow === envelope.flow) &&
            (indicatorModalRequest ? m.text === indicatorModalRequest.responseText : m.draft)
          );
          if (alreadyVisible) return prev;
          return [...prev, {
            role: "assistant",
            text: indicatorModalRequest?.responseText || envelope.response,
            intent: envelope.intent,
            flow: envelope.flow,
            draft: indicatorModalRequest ? null : envelope.draft,
            actions: indicatorModalRequest ? [] : (Array.isArray(envelope.actions) ? envelope.actions : []),
            missingFields: indicatorModalRequest ? [] : (envelope.missing_fields || []),
            invalidFields: indicatorModalRequest ? [] : (envelope.invalid_fields || []),
            nextQuestion: indicatorModalRequest ? null : (envelope.next_question || null),
            canConfirm: indicatorModalRequest ? false : envelope.can_confirm,
            suggestedActions: indicatorModalRequest ? [] : (envelope.suggested_actions || []),
            reasoning: envelope.reasoning,
            state: indicatorModalRequest ? null : (envelope.state || null),
            summary: envelope.summary || null,
            riskSummary: envelope.risk_summary || null,
            nextBestAction: envelope.next_best_action || null,
            reviewReason: envelope.review_reason || null,
            restoredFinnDraft: true,
            isComplete: true,
          }];
        });
      } catch (err) {
        console.error("Finn state herstellen mislukt", err);
      } finally {
        finnStateRequestRef.current = null;
      }
    })();
    return finnStateRequestRef.current;
  }

  async function loadInsight() {
    const requestKey = insightCacheKeyRef.current || `finn-insight:${currentConversationStorageKey}`;
    if (insightRequestRef.current && insightRequestKeyRef.current === requestKey) {
      return insightRequestRef.current;
    }
    setInsightLoading(true);
    if (!insight && typeof window !== "undefined" && requestKey) {
      try {
        const cached = window.sessionStorage.getItem(requestKey);
        if (cached) {
          const parsed = JSON.parse(cached);
          if (parsed && typeof parsed === "object") {
            setInsight((current) => current || parsed);
          }
        }
      } catch (err) {
        console.warn("Finn insight cache read failed", err);
      }
    }
    insightRequestKeyRef.current = requestKey;
    insightRequestRef.current = (async () => {
      try {
        const res = await fetchAssistantInsight(context);
        if (requestKey !== insightCacheKeyRef.current) {
          return res;
        }
        setInsight(res);
        setStableBriefingText(buildBriefingText(res));
        setLastUpdated(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
        if (res && typeof window !== "undefined" && requestKey) {
          try {
            window.sessionStorage.setItem(requestKey, JSON.stringify(res));
          } catch (cacheError) {
            console.warn("Finn insight cache write failed", cacheError);
          }
        }
        return res;
      } catch (err) {
        console.error("Failed to fetch AI insight", err);
        return null;
      } finally {
        if (requestKey === insightCacheKeyRef.current) {
          setInsightLoading(false);
        }
        if (insightRequestKeyRef.current === requestKey) {
          insightRequestRef.current = null;
          insightRequestKeyRef.current = "";
        }
      }
    })();
    return insightRequestRef.current;
  }

  async function loadMissionControl() {
    const requestKey =
      missionControlCacheKeyRef.current ||
      `finn-mission-control:${currentConversationStorageKey}:${pathname || "/assistant"}:${String(globalSymbol || context.symbol || "UNKNOWN").toUpperCase()}`;
    if (missionControlRequestRef.current && missionControlRequestKeyRef.current === requestKey) {
      return missionControlRequestRef.current;
    }
    setMissionControlLoading(true);
    if (!missionControl && typeof window !== "undefined" && requestKey) {
      try {
        const cached = window.sessionStorage.getItem(requestKey);
        if (cached) {
          const parsed = JSON.parse(cached);
          if (parsed && typeof parsed === "object") {
            setMissionControl((current) => current || parsed);
          }
        }
      } catch (err) {
        console.warn("Finn Mission Control cache read failed", err);
      }
    }
    missionControlRequestKeyRef.current = requestKey;
    missionControlRequestRef.current = (async () => {
      let lastError = null;
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          const res = await fetchFinnMissionControl();
          const normalized = res
            ? {
                ...res,
                coaching_loop:
                  res.coaching_loop ||
                  res.analysis?.coaching_loop ||
                  res.state?.analysis?.coaching_loop ||
                  null,
                summary:
                  res.summary ||
                  res.analysis?.summary ||
                  res.state?.analysis?.summary ||
                  null,
                behavioral_insight:
                  res.behavioral_insight ||
                  res.analysis?.behavioral_insight ||
                  res.state?.analysis?.behavioral_insight ||
                  null,
                behavioral_profile:
                  res.behavioral_profile ||
                  res.analysis?.behavioral_profile ||
                  res.state?.analysis?.behavioral_profile ||
                  null,
                trend:
                  res.trend ||
                  res.analysis?.trend ||
                  res.state?.analysis?.trend ||
                  null,
                risk_flags:
                  res.risk_flags ||
                  res.analysis?.risk_flags ||
                  res.state?.analysis?.risk_flags ||
                  null,
                habit_cards:
                  res.habit_cards ||
                  res.analysis?.habit_cards ||
                  res.state?.analysis?.habit_cards ||
                  null,
                priority_engine:
                  res.priority_engine ||
                  res.analysis?.priority_engine ||
                  res.state?.analysis?.priority_engine ||
                  null,
                memory_v2:
                  res.memory_v2 ||
                  res.analysis?.memory_v2 ||
                  res.state?.analysis?.memory_v2 ||
                  null,
                portfolio_operating_system:
                  res.portfolio_operating_system ||
                  res.analysis?.portfolio_operating_system ||
                  res.state?.analysis?.portfolio_operating_system ||
                  null,
                governance_events_summary:
                  res.governance_events_summary ||
                  res.analysis?.governance_events_summary ||
                  res.state?.analysis?.governance_events_summary ||
                  null,
              }
            : null;
          if (requestKey !== missionControlCacheKeyRef.current) {
            return normalized;
          }
          setMissionControl(normalized);
          if (normalized && typeof window !== "undefined" && requestKey) {
            try {
              window.sessionStorage.setItem(requestKey, JSON.stringify(normalized));
            } catch (err) {
              console.warn("Finn Mission Control cache write failed", err);
            }
          }
          setMissionControlLoadError(null);
          setMissionControlLoading(false);
          return normalized;
        } catch (err) {
          lastError = err;
          if (err?.status === 401 || err?.status === 403) {
            break;
          }
          if (attempt < 1) {
            await new Promise((resolve) => setTimeout(resolve, 400));
          }
        }
      }
      console.error("Finn overzicht laden mislukt", lastError);
      if (requestKey === missionControlCacheKeyRef.current) {
        setMissionControlLoadError(lastError?.message || uiText.missionControlUnavailable);
        setMissionControlLoading(false);
      }
      return null;
    })();
    try {
      return await missionControlRequestRef.current;
    } finally {
      if (missionControlRequestKeyRef.current === requestKey) {
        missionControlRequestRef.current = null;
        missionControlRequestKeyRef.current = "";
      }
    }
  }

  async function handleActionClick(action) {
    if (!action) return;
    const { type, symbol, params } = action;

    try {
      if (type === "add_to_watchlist") {
        if (symbol && watchlist?.add) {
          await watchlist.add({ symbol });
        }
      } else if (type === "remove_from_watchlist") {
        if (symbol && watchlist?.remove) {
          await watchlist.remove(symbol);
        }
      } else if (type === "open_setup_page") {
        router.push(`/setup${symbol ? `?symbol=${symbol}` : ""}`);
        setIsOpen(false);
      } else if (type === "generate_strategy") {
        router.push(`/setup${symbol ? `?symbol=${symbol}` : ""}`);
        setIsOpen(false);
      } else if (type === "open_bot_draft") {
        // Support prefilled bot parameters via query params
        const qParams = new URLSearchParams();
        if (symbol) qParams.append("symbol", symbol);
        if (params?.mode) qParams.append("mode", params.mode);
        if (params?.risk) qParams.append("risk", params.risk);
        if (params?.budget) qParams.append("budget", params.budget);
        
        router.push(`/bot?action=new_bot&${qParams.toString()}`);
        setIsOpen(false);
      } else if (type === "navigate_to_page") {
        if (params?.path) {
          router.push(params.path);
          setIsOpen(false);
        }
      }
    } catch (err) {
      console.error("Action execution failed", err);
    }
  }

  async function handleChat(directQuery, isSilent = false, overrideContext = null) {
    const nextQuery = directQuery !== undefined ? directQuery : activeQuery;
    if (!nextQuery.trim()) return;
    if (shouldBlockFinnSubmission({ isAuthenticated: Boolean(user?.id), assetStatus })) {
      showSnackbar("FINN wacht nog op je accountcontext. Probeer het zo opnieuw.", "warning");
      return;
    }

    setLoading(true);
    if (!isSilent) updateQuery("");
    
    if (!isSilent) {
      setMessages(prev => [...prev, { role: "user", text: nextQuery }]);
    }

    const streamId = `stream-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    activeStreamIdRef.current = streamId;

    // Append initial empty assistant bubble
    setMessages(prev => [...prev, { 
      role: "assistant", 
      text: "", 
      isComplete: false,
      streamId,
    }]);

    try {
      const cleanHistory = [
        ...messages.map(m => ({ role: m.role, text: m.text })),
        { role: "user", text: nextQuery }
      ];

      const latestAssistantState = overrideContext || activeState || getLatestAssistantState();
      const baseRequestContext = latestAssistantState?.current_flow
        ? { ...context, ...latestAssistantState }
        : context;
      const requestContext = {
        ...baseRequestContext,
        ...(commandRequest?.context || {}),
      };
      const analyticsSessionId = getAssistantSessionId(user?.id || "anonymous");
      const chatSessionId = activeFinnSessionId || "new";

      await assistantChatStream(
        nextQuery,
        requestContext,
        cleanHistory,
        (token) => {
          // onChunk
          if (activeStreamIdRef.current !== streamId) return;
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
          const originalResponse = envelope?.response || "";
          const sanitizedResponse = stripSuggestedActionsSection(originalResponse);
          const indicatorModalRequest = buildIndicatorModalRequest(envelope, requestContext?.symbol || globalSymbol || "BTC");
          const extractedSuggestedActions =
            Array.isArray(envelope?.suggested_actions) && envelope.suggested_actions.length > 0
              ? envelope.suggested_actions
              : parseSuggestedActions(originalResponse);
          setMessages(prev => {
            const copy = [...prev];
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
                reasoning: envelope.reasoning,
                state: indicatorModalRequest ? null : (envelope.state || null),
                summary: envelope.summary || null,
                riskSummary: envelope.risk_summary || null,
                nextBestAction: envelope.next_best_action || null,
                reviewReason: envelope.review_reason || null,
                isComplete: true,
              };
            }
            return copy;
          });
          activeStreamIdRef.current = null;

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
      if (activeStreamIdRef.current === streamId || activeStreamIdRef.current === null) {
        setLoading(false);
      }
    }
  };

  const handleCancelDraft = (index) => {
    setMessages(prev => prev.map((m, idx) => {
      if (idx === index) {
        return { ...m, draftCanceled: true };
      }
      return m;
    }));
    showSnackbar("Concept geannuleerd", "info");
  };

  const handleDraftSuccess = (index) => {
    setMessages(prev => prev.map((m, idx) => {
      if (idx === index) {
        return { ...m, draftExecuted: true };
      }
      return m;
    }));
  };

  const trackFinnConfirmEvent = (eventName, draftType) => {
    trackAssistantEvent({
      event_name: eventName,
      page: pathname || "/assistant",
      surface: "finn_overlay",
      asset: globalSymbol || null,
      flow_type: "confirm",
      action_type: draftType,
    });
  };

  const closeDraftDrawer = () => {
    if (draftFormRef.current?.isSubmitting?.()) return;
    if (draftDrawer?.trackingType) {
      trackFinnConfirmEvent("finn_confirm_canceled", draftDrawer.trackingType);
    }
    setDraftDrawer(null);
  };

  const handleEditDraft = async (draft, onSuccess) => {
    if (draft.type === "setup") {
      try {
        trackFinnConfirmEvent("finn_confirm_opened", "setup_draft");
        setDraftDrawer({
          type: "setup",
          title: at("modals.editSetupTitle"),
          payload: draft.payload,
          onSuccess,
          trackingType: "setup_draft",
        });
      } catch (err) {
        console.error("Failed to load SetupForm", err);
      }
    } else if (draft.type === "strategy") {
      try {
        const setupsList = await fetchSetups();
        trackFinnConfirmEvent("finn_confirm_opened", "strategy_draft");
        setDraftDrawer({
          type: "strategy",
          title: at("modals.editStrategyTitle"),
          payload: draft.payload,
          setups: setupsList,
          onSuccess,
          trackingType: "strategy_draft",
        });
      } catch (err) {
        console.error("Failed to load StrategyForm", err);
      }
    } else if (draft.type === "bot") {
      try {
        const stratList = await fetchStrategies();
        trackFinnConfirmEvent("finn_confirm_opened", "bot_draft");
        setDraftDrawer({
          type: "bot",
          title: at("modals.editBotTitle"),
          payload: draft.payload,
          strategies: stratList,
          onSuccess,
          trackingType: "bot_draft",
        });
      } catch (err) {
        console.error("Failed to load AddBotForm", err);
      }
    }
  };

  const handleExecuteAction = async (action) => {
    if (!action) return;
    setExecutingAction(true);

    try {
      const res = await executeAssistantAction(action);
      if (action.type === "refresh_daily_scores") {
        if (!res?.ok || !res?.verified?.daily_scores) {
          throw new Error("Daily scores zijn nog niet verifieerbaar.");
        }
        setMessages(prev => [...prev, {
          role: "assistant",
          text: res.message || "Daily scores ververst en geverifieerd.",
          intent: "daily_score_refresh_done",
        }]);
        await loadInsight();
        await loadMissionControl();
        emitFinnRefreshSignals();
        return;
      }

      if (action.type === "generate_bot_decision") {
        if (!res?.ok || !res?.verified?.bot_decision) {
          throw new Error("Bot-decision is nog niet verifieerbaar.");
        }
        setMessages(prev => [...prev, {
          role: "assistant",
          text: res.message || "Bot-decision gegenereerd. Review het voorstel voordat je iets uitvoert.",
          intent: "bot_decision_generated",
        }]);
        await loadInsight();
        await loadMissionControl();
        emitFinnRefreshSignals();
        return;
      }

      if (action.type === "skip_bot_decision") {
        if (!res?.ok || !res?.verified?.bot_decision_skipped) {
          throw new Error("Bot-decision skip is nog niet verifieerbaar.");
        }
        setMessages(prev => [...prev, {
          role: "assistant",
          text: res.message || uiText.botDecisionSkippedVerified,
          intent: "bot_decision_skipped",
          operatorResolution: res.operator_resolution,
        }]);
        await loadInsight();
        await loadMissionControl();
        emitFinnRefreshSignals();
        return;
      }

      if (action.type === "paper_execute_bot_decision") {
        if (!res?.ok || !res?.verified?.paper_execution) {
          throw new Error(uiText.paperExecutionPendingVerification);
        }
        setMessages(prev => [...prev, {
          role: "assistant",
          text: res.message || uiText.botDecisionPaperExecuted,
          intent: "bot_decision_executed",
        }]);
        await loadInsight();
        await loadMissionControl();
        emitFinnRefreshSignals();
        return;
      }

      if (action.type === "live_preflight_bot_decision") {
        const executionConsoleAction = buildExecutionConsoleAction(action, res);
        setMessages(prev => [...prev, {
          role: "assistant",
          text: res.message || "Live preflight gecontroleerd.",
          intent: "bot_live_preflight",
          isError: !res?.verified?.live_preflight,
          suggestedActions: executionConsoleAction ? [executionConsoleAction] : [],
        }]);
        await loadInsight();
        await loadMissionControl();
        emitFinnRefreshSignals();
        return;
      }

      if (action.type === "resolve_mission_item" || action.type === "snooze_mission_item") {
        if (!res?.ok || !res?.verified?.mission_item_resolved) {
          throw new Error("Dit overzichtsitem is nog niet verifieerbaar afgehandeld.");
        }
        setMessages(prev => [...prev, {
          role: "assistant",
          text: res.message || "Overzichtsitem bijgewerkt.",
          intent: "mission_item_resolved",
          operatorResolution: res.operator_resolution,
        }]);
        await loadMissionControl();
        emitFinnRefreshSignals();
        return;
      }

      const isBotOnly = res?.draft?.draft_kind === "bot";
      const isStrategyOnly = res?.draft?.draft_kind === "strategy";
      const isIndicatorConfig = res?.draft?.draft_kind === "indicator_config";
      const isIndicatorDelete = isIndicatorConfig && res?.operation === "delete";
      const verifiedOk = isBotOnly
        ? Boolean(res?.verified?.bot)
        : isIndicatorConfig
        ? Boolean(
            res?.verified?.indicator_config &&
            res?.verified?.backend_confirmed !== false &&
            (res.category === "technical"
              ? res?.verified?.technical_node !== false
              : res?.verified?.macro_node !== false)
          )
        : Boolean(res?.verified?.setup && res?.verified?.strategy && (!res.bot_id || res?.verified?.bot));
      if (!res?.ok || !verifiedOk) {
        throw new Error("Read-after-write verificatie faalde.");
      }

      if (isIndicatorConfig) {
        const indicatorName = String(res.indicator || "").toLowerCase();
        const symbol = res.draft?.symbol || context.symbol || "BTC";
        if (isIndicatorDelete) {
          const rows = res.category === "macro"
            ? await fetchMacroData()
            : await technicalDataAll(symbol);
          const stillPresent = res.category === "macro"
            ? rows.some((row) => String(row.name || "").toLowerCase() === indicatorName)
            : rows.some((row) => String(row.indicator || "").toLowerCase() === indicatorName);
          if (stillPresent) {
            throw new Error("Indicator staat nog steeds in de actieve lijst na verwijderen.");
          }
        } else {
          const [config, rows] = await Promise.all([
            getIndicatorConfig(res.category, res.indicator),
            res.category === "macro" ? fetchMacroData() : technicalDataAll(symbol),
          ]);
          const configFound = Boolean(config?.indicator === res.indicator && Array.isArray(config?.rules) && config.rules.length === 5);
          const shouldVerifyNode = Boolean(res.draft?.activate_node || res.draft?.node_already_active);
          const nodeFound = !shouldVerifyNode ? true : res.category === "macro"
            ? rows.some((row) => String(row.name).toLowerCase() === indicatorName)
            : rows.some((row) => String(row.indicator).toLowerCase() === indicatorName);
          if (!configFound || !nodeFound) {
            throw new Error("Indicator-configuratie is nog niet terugleesbaar via de API.");
          }
        }
        setMessages(prev => [...prev, {
          role: "assistant",
          text: isIndicatorDelete
            ? `${res.duplicate ? "Deze actie was al verwerkt. " : ""}${res.message || "Indicator verwijderd"} en geverifieerd: ${res.category}/${res.indicator} is niet langer actief.`
            : `${res.duplicate ? "Deze actie was al verwerkt. " : ""}${res.message || "Indicator-configuratie opgeslagen"} en geverifieerd: ${res.category}/${res.indicator}.`,
          intent: "indicator_configured",
        }]);
        setFinnDraft(null);
        await loadInsight();
        await loadMissionControl();
        emitFinnRefreshSignals();
        return;
      }

      const [setups, strategies, bots] = await Promise.all([
        fetchSetups(),
        fetchStrategies(),
        fetchBotConfigs(),
      ]);
      const setupFound = isBotOnly || setups.some((setup) => Number(setup.id || setup.setup_id) === Number(res.setup_id));
      const strategyFound = isBotOnly || strategies.some((strategy) => Number(strategy.id) === Number(res.strategy_id));
      const botFound = !res.bot_id || bots.some((bot) => Number(bot.id || bot.bot_id) === Number(res.bot_id));
      if (!setupFound || !strategyFound || !botFound) {
        throw new Error("Aangemaakte objecten zijn nog niet terugleesbaar via de API.");
      }

      setMessages(prev => [...prev, {
        role: "assistant",
        text: isBotOnly
          ? `${res.duplicate ? "Deze actie was al verwerkt. " : ""}Bot ${res.operation === "update" ? "bijgewerkt" : "aangemaakt"} en geverifieerd: bot #${res.bot_id} voor strategy #${res.strategy_id}.`
          : isStrategyOnly
          ? `${res.duplicate ? "Deze actie was al verwerkt. " : ""}Strategie ${res.operation === "update" ? "bijgewerkt" : "aangemaakt"} en geverifieerd: strategy #${res.strategy_id} voor setup #${res.setup_id}.`
          : (() => {
              const createdSetup = setups.find((setup) => Number(setup.id || setup.setup_id) === Number(res.setup_id));
              const createdName = createdSetup?.name || action?.payload?.name || "Nieuwe setup";
              const createdTimeframe = createdSetup?.timeframe || action?.payload?.timeframe || null;
              const createdSymbol = createdSetup?.symbol || action?.payload?.symbol || context.symbol || globalSymbol || "BTC";
              const createdType = createdSetup?.setup_type || action?.payload?.setup_type || "setup";
              const timeframeSuffix = createdTimeframe ? ` op ${createdTimeframe}` : "";
              return `${res.duplicate ? "Deze actie was al verwerkt. " : ""}Setup '${createdName}' voor ${createdSymbol}${timeframeSuffix} is aangemaakt en geverifieerd (${createdType}).`;
            })(),
        intent: isBotOnly ? "bot_created" : (isStrategyOnly ? "strategy_created" : "plan_created"),
      }]);
      setFinnDraft(null);
      await loadInsight();
      await loadMissionControl();
      emitFinnRefreshSignals();
    } catch (err) {
      console.error("Finn action failed", err);
      setMessages(prev => [...prev, {
        role: "assistant",
        text: action.type === "refresh_daily_scores"
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

  const renderDraftCard = (message) => {
    const draft = message.draft;
    const isFinnPlan = message.intent === "plan_creation" || message.flow === "plan_creation" || draft?.plan_type;
    const isFinnStrategy = message.intent === "strategy_creation" || message.flow === "strategy_creation" || draft?.draft_kind === "strategy";
    const isFinnBot = message.intent === "bot_creation" || message.flow === "bot_creation" || draft?.draft_kind === "bot";
    const isFinnIndicator = message.intent === "indicator_config" || message.flow === "indicator_config" || draft?.draft_kind === "indicator_config";
    if (isFinnIndicator) return null;
    if (!draft || (!isFinnPlan && !isFinnStrategy && !isFinnBot && !isFinnIndicator)) return null;

    const setup = draft.setup || {};
    const strategy = draft.strategy || {};
    const dca = draft.dca || {};
    const bot = draft.bot || {};
    const draftType = isFinnStrategy || isFinnBot ? draft.setup_type : draft.plan_type;
    const isDca = draftType === "dca";
    const isTrade = draftType === "trade";
    const setupOptions = (message.state?.setup_options || []).filter((option) => option && option.id);
    const strategyOptions = (message.state?.strategy_options || []).filter((option) => option && option.id);
    const indicatorOptions = (message.state?.indicator_options || draft.indicator_options || []).filter(
      (option) => option && option.name
    );
    const changes = draft.changes || message.state?.changes || [];
    const planDeviation = message.state?.plan_deviation || draft.plan_deviation || null;
    const planDeviationRequiresAck = Boolean(planDeviation?.requires_ack && !planDeviation?.acknowledged);
    const visibleMissingFields = (message.missingFields || []).filter((field) => field !== "plan_deviation_ack");
    const visibleNextQuestion = message.nextQuestion === "plan_deviation_ack" ? null : message.nextQuestion;
    const yesLabel = at("draftRows.yes");
    const noLabel = at("draftRows.no");
    const humanizeFieldFallback = (field) => {
      const raw = String(field || "").trim();
      if (!raw) return "";
      const explicit = {
        "dca.frequency": at("fieldLabels.dca.frequency", "DCA frequentie"),
        "dca_frequency": at("fieldLabels.dca.frequency", "DCA frequentie"),
        "dca.day": at("fieldLabels.dca.day", "DCA weekdag"),
        "dca_day": at("fieldLabels.dca.day", "DCA weekdag"),
        "dca.month_day": at("fieldLabels.dca.month_day", "DCA maanddag"),
        "dca_month_day": at("fieldLabels.dca.month_day", "DCA maanddag"),
        "strategy.base_amount_eur": at("fieldLabels.strategy.base_amount_eur", "Basisbedrag"),
        "base_amount": at("fieldLabels.strategy.base_amount_eur", "Basisbedrag"),
        "base_amount_eur": at("fieldLabels.strategy.base_amount_eur", "Basisbedrag"),
        "setup.name": at("fieldLabels.setup.name", "Naam"),
        "name": at("fieldLabels.setup.name", "Naam"),
        "timeframe": at("fieldLabels.setup.timeframe", "Timeframe"),
        "setup_type": at("draftRows.setupType", "Setup type"),
        "symbol": at("fieldLabels.asset", "Asset"),
      };
      if (explicit[raw]) return explicit[raw];
      const parts = raw.split(".");
      const lastPart = parts[parts.length - 1] || raw;
      return lastPart.replace(/_/g, " ");
    };
    const fieldLabel = (field, fallback = null) => at(`fieldLabels.${field}`, fallback || humanizeFieldFallback(field));
    const fieldQuestion = (field, fallback = null) => at(`fieldQuestions.${field}`, fallback || field);
    const valueLabel = (value, fallback = null) => {
      if (value === undefined || value === null || value === "") return null;
      const normalized = String(value).trim();
      if (!normalized) return null;
      const translated = at(`valueLabels.${normalized}`, normalized);
      return translated || fallback || normalized;
    };
    const draftTitle = isFinnIndicator
      ? at("draftTitles.indicator", "Finn indicator draft")
      : isFinnBot
        ? at("draftTitles.bot", "Finn bot draft")
        : isFinnStrategy
          ? at("draftTitles.strategy", "Finn strategy draft")
          : at("draftTitles.plan", "Finn plan draft");
    const draftRowsText = {
      type: at("draftRows.type"),
      action: at("draftRows.action"),
      category: at("draftRows.category"),
      scoreMode: at("draftRows.scoreMode"),
      weight: at("draftRows.weight"),
      buckets: at("draftRows.buckets"),
      nodeActive: at("draftRows.nodeActive"),
      botId: at("draftRows.botId"),
      strategy: at("draftRows.strategy"),
      setup: at("draftRows.setup"),
      setupType: at("draftRows.setupType"),
      bot: at("draftRows.bot"),
      environment: at("draftRows.environment"),
      risk: at("draftRows.risk"),
      cadence: at("draftRows.cadence"),
      name: at("draftRows.name"),
      timeframe: at("draftRows.timeframe"),
      amount: at("draftRows.amount"),
      technical: at("draftRows.technical"),
      market: at("draftRows.market"),
      execution: at("draftRows.execution"),
      marketConfirmation: at("draftRows.marketConfirmation"),
      entry: at("draftRows.entry"),
      stop: at("draftRows.stop"),
      targets: at("draftRows.targets"),
      automation: at("draftRows.automation"),
      create: at("draftRows.create"),
      update: at("draftRows.update"),
      add: at("draftRows.add"),
      reset: at("draftRows.reset"),
    };
    const isCollecting = !message.canConfirm;
    if (isFinnStrategy && isCollecting) return null;
    const defaultPlanName = draft.asset && draft.plan_type
      ? `${draft.asset} ${draft.plan_type === "dca" ? "Smart DCA" : "Trade Plan"}`
      : null;
    const hideDefaultPlanName = isCollecting && setup.name && defaultPlanName && setup.name === defaultPlanName;
    const hideDefaultTimeframe = isCollecting && isDca && setup.timeframe === "1W";
    const hideScoreRanges = isCollecting;
    const hideDefaultAutomation = isCollecting && !isFinnBot && !isFinnIndicator && !bot.automation;
    const hideDefaultBotSummary = isCollecting && !isFinnStrategy && !isFinnBot && !hasMeaningfulValue(bot.create_bot);
    const dcaScheduleParts = [
      valueLabel(dca.frequency),
      dca.month_day ? String(dca.month_day) : (dca.day && (!isCollecting || dca.day !== "monday") ? valueLabel(dca.day) : null),
    ].filter(Boolean);
    const formatRange = (range) => Array.isArray(range) ? range.join(" - ") : null;
    const formatCurrency = (amount) => (amount ? `€${amount}` : null);
    const formatChangeLabel = (field) => fieldLabel(field, field);
    const formatValue = (value) => {
      if (value === undefined || value === null || value === "") return "—";
      if (Array.isArray(value)) return value.join(", ");
      if (typeof value === "boolean") return value ? yesLabel : noLabel;
      if (typeof value === "string") return valueLabel(value, value);
      return String(value);
    };
    const hasMeaningfulValue = (value) => {
      if (value === undefined || value === null || value === "") return false;
      if (Array.isArray(value)) return value.length > 0;
      return true;
    };
    const showMissingFieldBadges = !isCollecting || !visibleNextQuestion;

    const rows = [
      [draftRowsText.type, valueLabel(isFinnIndicator ? "indicator_config" : (isFinnBot ? "bot" : (isFinnStrategy ? "strategy" : draft.plan_type)))],
      isFinnIndicator ? [draftRowsText.action, draft.operation === "reset" ? draftRowsText.reset : (draft.operation === "update" ? draftRowsText.update : draftRowsText.add)] : null,
      isFinnIndicator ? [draftRowsText.category, draft.category] : null,
      isFinnIndicator ? ["Node", draft.indicator ? `${draft.display_name || draft.indicator} (${draft.indicator})` : null] : null,
      isFinnIndicator ? [draftRowsText.scoreMode, draft.score_mode] : null,
      isFinnIndicator ? [draftRowsText.weight, draft.weight] : null,
      isFinnIndicator ? [draftRowsText.buckets, Array.isArray(draft.rules) ? draft.rules.map((rule) => rule.score).join(" / ") : null] : null,
      isFinnIndicator ? [draftRowsText.nodeActive, draft.activate_node ? yesLabel : noLabel] : null,
      isFinnStrategy ? [draftRowsText.action, draft.operation === "update" ? draftRowsText.update : draftRowsText.create] : null,
      isFinnBot ? [draftRowsText.action, draft.operation === "update" ? draftRowsText.update : draftRowsText.create] : null,
      isFinnBot && draft.operation === "update" ? [draftRowsText.botId, draft.bot_id ? `#${draft.bot_id}` : null] : null,
      isFinnBot ? [draftRowsText.strategy, draft.strategy_id ? `#${draft.strategy_id}` : null] : null,
      isFinnStrategy
        ? [
            draftRowsText.setup,
            draft.setup_name && draft.setup_id ? `${draft.setup_name} (#${draft.setup_id})` : (draft.setup_id ? `#${draft.setup_id}` : null),
          ]
        : null,
      isFinnStrategy && draft.operation === "update" ? [draftRowsText.strategy, draft.strategy_id ? `#${draft.strategy_id}` : null] : null,
      isFinnStrategy ? [draftRowsText.setupType, valueLabel(draft.setup_type, draft.setup_type)] : null,
      isFinnBot ? [draftRowsText.bot, bot.name] : null,
      isFinnBot ? [draftRowsText.environment, valueLabel(bot.is_live ? "live" : "paper")] : null,
      isFinnBot ? [uiText.mode, valueLabel(bot.mode, bot.mode)] : null,
      isFinnBot ? [draftRowsText.risk, valueLabel(bot.risk_profile, bot.risk_profile)] : null,
      isFinnBot ? [draftRowsText.cadence, valueLabel(bot.cadence, bot.cadence)] : null,
      !isFinnIndicator ? [uiText.asset, draft.asset] : null,
      !isFinnStrategy && !isFinnBot && !isFinnIndicator && !hideDefaultPlanName ? [draftRowsText.name, setup.name] : null,
      !isFinnIndicator && !hideDefaultTimeframe ? [draftRowsText.timeframe, isFinnStrategy || isFinnBot ? draft.timeframe : setup.timeframe] : null,
      !isFinnIndicator ? [draftRowsText.amount, isFinnBot ? formatCurrency(bot.budget_total_eur) : formatCurrency(strategy.base_amount_eur)] : null,
      !isFinnStrategy && !isFinnBot && !isFinnIndicator && !hideScoreRanges ? [fieldLabel("setup.macro_score_range", "Macro"), formatRange(setup.macro_score_range)] : null,
      !isFinnStrategy && !isFinnBot && !isFinnIndicator && !hideScoreRanges ? [draftRowsText.technical, formatRange(setup.technical_score_range)] : null,
      !isFinnStrategy && !isFinnBot && !isFinnIndicator && !hideScoreRanges ? [draftRowsText.market, formatRange(setup.market_score_range)] : null,
      isDca && !isFinnStrategy && !isFinnBot ? [valueLabel("dca", "DCA"), dcaScheduleParts.join(" · ")] : null,
      isTrade && !isFinnBot ? [draftRowsText.execution, strategy.entry_type || strategy.trade_execution_mode ? valueLabel(strategy.entry_type || strategy.trade_execution_mode) : null] : null,
      isTrade && !isFinnBot && strategy.entry_type === "market" ? [draftRowsText.marketConfirmation, strategy.market_execution_ack ? yesLabel : noLabel] : null,
      isTrade && !isFinnBot ? [draftRowsText.entry, strategy.entry] : null,
      isTrade && !isFinnBot ? [draftRowsText.stop, strategy.stop_loss] : null,
      isTrade && !isFinnBot ? [draftRowsText.targets, Array.isArray(strategy.targets) ? strategy.targets.join(", ") : null] : null,
      !isFinnBot && !isFinnIndicator && !hideDefaultAutomation ? [draftRowsText.automation, valueLabel(isFinnStrategy ? strategy.automation : bot.automation)] : null,
      !isFinnStrategy && !isFinnBot && bot.create_bot && !hideDefaultBotSummary ? [draftRowsText.bot, `${valueLabel(bot.is_live ? "live" : "paper")} · ${valueLabel(bot.mode, bot.mode)}${bot.risk_profile ? ` · ${valueLabel(bot.risk_profile, bot.risk_profile)}` : ""}`] : null,
    ].filter((row) => {
      if (!row) return false;
      const [, value] = row;
      if (!isCollecting) return true;
      return hasMeaningfulValue(value);
    });
    const shouldRenderDraftRows = rows.length > 0 && !(isFinnStrategy && isCollecting);

    return (
      <div className="mt-4 rounded-2xl border border-blue-200 dark:border-blue-900/50 bg-blue-50/70 dark:bg-blue-950/20 p-4 space-y-4">
        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-blue-600 dark:text-blue-300">
          <ListChecks size={13} />
          {draftTitle}
        </div>
        {shouldRenderDraftRows ? (
          <div className="grid grid-cols-1 gap-2">
            {rows.map(([label, value]) => (
              <div key={label} className="flex items-center justify-between gap-4 border-b border-blue-100/70 dark:border-blue-900/30 pb-2 last:border-b-0 last:pb-0">
                <span className="text-[10px] font-black uppercase tracking-widest text-blue-400">{label}</span>
                <span className="text-xs font-bold text-slate-800 dark:text-slate-100 text-right">{value || "—"}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-blue-100 dark:border-blue-900/40 bg-white/70 dark:bg-slate-950/30 px-3 py-2.5 text-xs font-semibold text-slate-700 dark:text-slate-200">
            {at("draftStatus.collectingDetails", "Finn verzamelt eerst de kernkeuzes en laat daarna pas de volledige conceptkaart zien.")}
          </div>
        )}
        {isFinnStrategy && setupOptions.length > 0 && (
          <div className="rounded-xl border border-blue-100 dark:border-blue-900/40 bg-white/70 dark:bg-slate-950/30 p-3 space-y-2">
            <div className="text-[9px] font-black uppercase tracking-widest text-blue-500 dark:text-blue-300">{uiText.chooseSetup}</div>
            <div className="grid grid-cols-1 gap-2">
              {setupOptions.map((option) => (
                <button
                  key={option.id}
                  onClick={() => handleChat(`setup ${option.id}`)}
                  className="text-left rounded-lg border border-blue-100 dark:border-blue-900/40 bg-blue-50/60 dark:bg-blue-950/20 px-3 py-2 hover:border-blue-300 dark:hover:border-blue-700 transition-colors"
                >
                  <div className="text-xs font-black text-slate-800 dark:text-slate-100">{option.name || `Setup #${option.id}`}</div>
                  <div className="mt-0.5 text-[10px] font-bold uppercase tracking-wider text-blue-500 dark:text-blue-300">
                    #{option.id} · {option.symbol} · {valueLabel(option.setup_type, option.setup_type)} · {option.timeframe}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
        {isFinnBot && strategyOptions.length > 0 && (
          <div className="rounded-xl border border-blue-100 dark:border-blue-900/40 bg-white/70 dark:bg-slate-950/30 p-3 space-y-2">
            <div className="text-[9px] font-black uppercase tracking-widest text-blue-500 dark:text-blue-300">{uiText.chooseStrategy}</div>
            <div className="grid grid-cols-1 gap-2">
              {strategyOptions.map((option) => (
                <button
                  key={option.id}
                  onClick={() => handleChat(`strategy ${option.id}`)}
                  className="text-left rounded-lg border border-blue-100 dark:border-blue-900/40 bg-blue-50/60 dark:bg-blue-950/20 px-3 py-2 hover:border-blue-300 dark:hover:border-blue-700 transition-colors"
                >
                  <div className="text-xs font-black text-slate-800 dark:text-slate-100">{option.name || `Strategy #${option.id}`}</div>
                  <div className="mt-0.5 text-[10px] font-bold uppercase tracking-wider text-blue-500 dark:text-blue-300">
                    #{option.id} · {option.symbol} · {valueLabel(option.setup_type, option.setup_type)} · {option.timeframe}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
        {isFinnIndicator && indicatorOptions.length > 0 && (
          <div className="rounded-xl border border-blue-100 dark:border-blue-900/40 bg-white/70 dark:bg-slate-950/30 p-3 space-y-2">
            <div className="text-[9px] font-black uppercase tracking-widest text-blue-500 dark:text-blue-300">{uiText.chooseIndicatorNode}</div>
            <div className="grid grid-cols-1 gap-2">
              {indicatorOptions.map((option) => (
                <button
                  key={option.name}
                  onClick={() => handleChat(`${option.name}`)}
                  className="text-left rounded-lg border border-blue-100 dark:border-blue-900/40 bg-blue-50/60 dark:bg-blue-950/20 px-3 py-2 hover:border-blue-300 dark:hover:border-blue-700 transition-colors"
                >
                  <div className="text-xs font-black text-slate-800 dark:text-slate-100">{option.display_name || option.name}</div>
                  <div className="mt-0.5 text-[10px] font-bold uppercase tracking-wider text-blue-500 dark:text-blue-300">
                    {option.name} · {option.category}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
        {(isFinnStrategy || isFinnBot || isFinnIndicator) && changes.length > 0 && (
          <div className="rounded-xl border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50/70 dark:bg-emerald-950/20 p-3 space-y-2">
            <div className="text-[9px] font-black uppercase tracking-widest text-emerald-700 dark:text-emerald-300">Wijzigingen</div>
            <div className="space-y-1">
              {changes.map((change, index) => (
                <div key={`${change.field}-${index}`} className="flex items-center justify-between gap-3 text-[11px] font-semibold text-slate-700 dark:text-slate-200">
                  <span className="font-black text-emerald-700 dark:text-emerald-300">{formatChangeLabel(change.field)}</span>
                  <span className="text-right">{formatValue(change.from)} → {formatValue(change.to)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {planDeviation && (
          <div className="rounded-xl border border-rose-200 dark:border-rose-900/50 bg-rose-50/90 dark:bg-rose-950/25 p-3 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-rose-700 dark:text-rose-300">
                <Shield size={13} />
                {uiText.planDeviation}
              </div>
              <span className={`shrink-0 rounded-full px-2 py-1 text-[9px] font-black uppercase tracking-widest border ${
                planDeviation.acknowledged
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300"
                  : "border-rose-200 bg-white/80 text-rose-700 dark:border-rose-900/60 dark:bg-slate-950/40 dark:text-rose-300"
              }`}>
                {planDeviation.acknowledged ? uiText.overrideConfirmed : uiText.overrideRequired}
              </span>
            </div>
            <div className="space-y-1">
              <div className="text-sm font-black text-slate-950 dark:text-slate-50">
                {uiText.planDeviationTitle}
              </div>
              <p className="text-xs font-semibold leading-relaxed text-rose-800 dark:text-rose-100">
                {planDeviation.message || "Deze wijziging wijkt af van je huidige setup-context."}
              </p>
            </div>
            {Array.isArray(planDeviation.reasons) && planDeviation.reasons.length > 0 && (
              <div className="space-y-1.5">
                <div className="text-[9px] font-black uppercase tracking-widest text-rose-600 dark:text-rose-300">{uiText.whyFinnBrakes}</div>
                <div className="grid grid-cols-1 gap-1">
                  {planDeviation.reasons.slice(0, 4).map((reason, index) => (
                    <div key={`${reason}-${index}`} className="rounded-lg border border-rose-100 dark:border-rose-900/40 bg-white/75 dark:bg-slate-950/35 px-2.5 py-2 text-[11px] font-bold leading-snug text-slate-800 dark:text-slate-100">
                      {reason}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {planDeviation.safe_alternative && (
              <p className="text-[11px] font-bold leading-snug text-slate-700 dark:text-slate-200">
                {uiText.safeRoute}: {planDeviation.safe_alternative}
              </p>
            )}
            {planDeviationRequiresAck && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                <button
                  onClick={() => handleChat(planDeviation.ack_phrase || "bewuste override")}
                  disabled={loading || executingAction}
                  className="flex items-center justify-center gap-2 rounded-xl bg-rose-600 px-3 py-2.5 text-[10px] font-black uppercase tracking-widest text-white shadow-lg shadow-rose-600/15 transition-colors hover:bg-rose-700 disabled:opacity-60"
                >
                  <Shield size={14} />
                  {at("behavioralMemory.consciousOverride")}
                </button>
                <button
                  onClick={() => handleChat("annuleer")}
                  disabled={loading || executingAction}
                  className="flex items-center justify-center gap-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-950/40 px-3 py-2.5 text-[10px] font-black uppercase tracking-widest text-slate-700 dark:text-slate-200 transition-colors hover:border-slate-300 dark:hover:border-slate-700 disabled:opacity-60"
                >
                  <X size={14} />
                  {at("behavioralMemory.cancel")}
                </button>
              </div>
            )}
          </div>
        )}
        {(visibleMissingFields.length > 0 || message.invalidFields?.length > 0 || visibleNextQuestion) && (
          <div className="rounded-xl border border-amber-200 dark:border-amber-900/50 bg-amber-50/80 dark:bg-amber-950/20 p-3 space-y-2">
            {showMissingFieldBadges && visibleMissingFields.length > 0 && (
              <div>
                <div className="text-[9px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">{uiText.missingStill}</div>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {visibleMissingFields.map((field) => (
                    <span key={field} className="px-2 py-1 rounded-lg bg-white/80 dark:bg-slate-950/50 text-[10px] font-bold text-amber-800 dark:text-amber-200 border border-amber-100 dark:border-amber-900/40">
                      {fieldLabel(field, field)}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {message.invalidFields?.length > 0 && (
              <div>
                <div className="text-[9px] font-black uppercase tracking-widest text-rose-700 dark:text-rose-300">{uiText.invalid}</div>
                <div className="mt-1 space-y-1">
                  {message.invalidFields.map((item, index) => (
                    <div key={`${item.field}-${index}`} className="text-[11px] font-semibold text-rose-700 dark:text-rose-200">
                      {fieldLabel(item.field, item.field)}: {item.reason}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {visibleNextQuestion && (
              <div className="text-xs font-bold text-slate-800 dark:text-slate-100">
                {fieldQuestion(visibleNextQuestion, fieldLabel(visibleNextQuestion, visibleNextQuestion))}
              </div>
            )}
          </div>
        )}
        {message.actions?.map((action, index) => (
          <button
            key={`${action.type}-${index}`}
            onClick={() => handleExecuteAction(action)}
            disabled={executingAction}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-[11px] font-black uppercase tracking-widest transition-all shadow-lg shadow-blue-600/15"
          >
            {executingAction ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
            {action.label || uiText.confirm}
          </button>
        ))}
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
    const actions = Array.isArray(message.actions) ? message.actions : [];
    const actionOnly = actions.filter((action) => (
      action?.requires_confirmation &&
      [
        "refresh_daily_scores",
        "generate_bot_decision",
        "skip_bot_decision",
        "paper_execute_bot_decision",
        "live_preflight_bot_decision",
      ].includes(action.type)
    ));
    if (actionOnly.length === 0 || message.draft) return null;

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
              {context.page_type || "Finn"} · {context.symbol || "BTC"} · {context.timeframe || "1D"}
            </p>
          </div>
          <div className="rounded-xl border border-blue-100 dark:border-blue-900/40 bg-white/80 dark:bg-slate-950/35 px-3 py-2">
            <div className="text-[8px] font-black uppercase tracking-[0.22em] text-blue-500 dark:text-blue-300">{uiText.impact}</div>
            <p className="mt-1 text-[11px] font-semibold text-slate-700 dark:text-slate-200">
              {at("inlineAction.updatesAfterConfirm")}
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
              disabled={executingAction}
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

  const keepDashboardShellPinned = pathname === "/dashboard" && !!missionControl;

  const scrollAssistantViewport = () => {
    if (keepDashboardShellPinned) {
      scrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
      return;
    }
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollAssistantViewport();
  }, [messages, loading, activeState, missionControl, keepDashboardShellPinned]);

  useLayoutEffect(() => {
    if (!isOpen || !keepDashboardShellPinned || !scrollRef.current) return undefined;

    const pinToTop = () => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = 0;
      }
    };

    pinToTop();
    const raf1 = requestAnimationFrame(pinToTop);
    const raf2 = requestAnimationFrame(() => requestAnimationFrame(pinToTop));
    const t1 = window.setTimeout(pinToTop, 0);
    const t2 = window.setTimeout(pinToTop, 150);
    const t3 = window.setTimeout(pinToTop, 600);

    return () => {
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
      window.clearTimeout(t1);
      window.clearTimeout(t2);
      window.clearTimeout(t3);
    };
  }, [isOpen, keepDashboardShellPinned, missionControl, messages.length, loading, activeState?.current_flow]);

  const progress = activeState ? getFlowProgress(activeState) : null;
  const activeStep = progress ? Math.min(progress.filled + 1, progress.total) : 1;
  const workspaceContextLabel = getFinnWorkspaceLabel(pathname, locale) || humanizeFinnContextValue(context.page_type, "Workspace");
  const finnContextLabel = [workspaceContextLabel, context.symbol || "BTC"]
    .filter(Boolean)
    .join(" · ");
  const compactFinnHeader = [
    "FINN",
    workspaceContextLabel,
    String(context.symbol || globalSymbol || "BTC").toUpperCase(),
  ].filter(Boolean);
  const finnModeLabel =
    activeState?.current_flow && activeState.current_flow !== "none"
      ? uiText.conceptMode
      : pathname?.includes("/portfolio")
      ? uiText.paperMode
      : uiText.readOnlyMode;

  const shouldCondenseMissionControl = (previewSectionsOnly || pathname === "/dashboard") && !isOnboarding;
  const showFullMissionControl = !shouldCondenseMissionControl;
  const overlayMissionSections = buildMissionOverlaySections();
  const primaryProfileHabitAlignment = pickPrimaryProfileHabitAlignment(missionControl);
  const primaryBehaviorLabel = primaryProfileHabitAlignment
    ? humanizeBehaviorFlagLabel(primaryProfileHabitAlignment.flag, primaryProfileHabitAlignment.label)
    : "";
  const primaryBehaviorRule = String(primaryProfileHabitAlignment?.recommended_rule || "").trim();
  const primaryBehaviorCost = String(primaryProfileHabitAlignment?.behavioral_cost || "").trim();
  const primaryCoachingItem =
    overlayMissionSections.todayItems?.[0] ||
    missionControl?.coaching_loop?.daily_priority_stack?.[0] ||
    missionControl?.workqueue?.[0] ||
    missionControl?.coaching_loop?.monitor_only?.[0] ||
    missionControl?.coaching_loop?.suppressed_items?.[0] ||
    null;
  const compactMissionActions = normalizeFollowUpActions([
    missionControl?.agent_controller?.primary_action,
    ...(missionControl?.coaching_loop?.operator_handoffs || []),
    ...(missionControl?.open_actions || []),
  ]).slice(0, 2);
  const briefingFollowUpActions = shouldCondenseMissionControl
    ? []
    : getBriefingFollowUpActions();
  const compactMissionReason =
    (primaryCoachingItem ? humanizeMissionReason(primaryCoachingItem) : null) ||
    primaryCoachingItem?.why_now ||
    missionControl?.behavioral_insight?.coaching?.safe_next_step ||
    missionControl?.behavioral_insight?.coaching?.primary_reflection ||
    missionControl?.summary?.headline ||
    null;
  const compactBehavioralReason =
    String(primaryCoachingItem?.behavioral_priority_reason || "").trim() ||
    primaryBehaviorCost ||
    primaryBehaviorRule ||
    "";
  const activeBriefingSymbol = String(context?.symbol || globalSymbol || "BTC").trim().toUpperCase();
  const firstDashboardContext = missionControl?.first_dashboard_context || null;
  const firstDashboardBriefingText = String(firstDashboardContext?.briefing_text || "").trim();
  const stableBriefingMatchesAsset = !isAssetAnalysisPage
    || !stableBriefingText
    || stableBriefingText.toUpperCase().includes(activeBriefingSymbol);
  const resolvedBriefingText = firstDashboardBriefingText
    || (stableBriefingMatchesAsset
      ? stableBriefingText || buildBriefingText(insight) || ""
      : buildBriefingText(insight) || "");
  const workspaceBriefingLines = String(resolvedBriefingText)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const defaultBriefingLine = at("briefing.market.default", "", {
    symbol: String(context?.symbol || globalSymbol || "BTC").trim().toUpperCase(),
  });
  const workspaceIsStillBuilding =
    workspaceBriefingLines.length <= 2 &&
    workspaceBriefingLines[1] === defaultBriefingLine &&
    overlayMissionSections.todayItems.length === 0 &&
    overlayMissionSections.reviewItems.length === 0 &&
    overlayMissionSections.riskItems.length === 0 &&
    overlayMissionSections.performanceCards.length === 0 &&
    overlayMissionSections.historyItems.length === 0 &&
    Number(missionControl?.summary?.open_action_count || 0) === 0 &&
    Number(missionControl?.summary?.blocked_count || 0) === 0;
  const showFirstDashboardGuidance =
    pathname === "/dashboard" &&
    onboardingComplete &&
    !dashboardReady &&
    workspaceIsStillBuilding;
  const workspaceGreeting = workspaceBriefingLines[0] || "";
  const defaultWorkspaceHeadline =
    workspaceBriefingLines[1] ||
    compactMissionReason ||
    missionControl?.summary?.headline ||
    defaultBriefingLine;
  const defaultWorkspaceSupport =
    workspaceBriefingLines[2] ||
    compactMissionReason ||
    primaryBehaviorRule ||
    "";
  const defaultWorkspaceActionHint = workspaceBriefingLines[3] || "";
  const firstDashboardHeadline = firstDashboardContext?.headline
    || at("uiText.workspaceFirstDashboardHeadline", uiText.workspaceFirstDashboardHeadline, {
      symbol: activeBriefingSymbol,
    });
  const firstDashboardSupport = firstDashboardContext?.support
    || at("uiText.workspaceFirstDashboardSupport", uiText.workspaceFirstDashboardSupport, {
      symbol: activeBriefingSymbol,
    });
  const firstDashboardHint = firstDashboardContext?.action_hint
    || at("uiText.workspaceFirstDashboardHint", uiText.workspaceFirstDashboardHint, {
      symbol: activeBriefingSymbol,
    });
  const workspaceHeadline = firstDashboardContext
    ? firstDashboardHeadline
    : workspaceIsStillBuilding
    ? at("uiText.workspaceBuildingHeadline", uiText.workspaceBuildingHeadline, {
        symbol: activeBriefingSymbol,
      })
    : defaultWorkspaceHeadline;
  const workspaceSupport = firstDashboardContext
    ? firstDashboardSupport
    : workspaceIsStillBuilding
    ? at("uiText.workspaceBuildingSupport", uiText.workspaceBuildingSupport, {
        symbol: activeBriefingSymbol,
      })
    : defaultWorkspaceSupport;
  const workspaceActionHint = firstDashboardContext
    ? firstDashboardHint
    : workspaceIsStillBuilding
    ? at("uiText.workspaceBuildingHint", uiText.workspaceBuildingHint, {
        symbol: activeBriefingSymbol,
      })
    : defaultWorkspaceActionHint;
  const missionDetailSections = [
    {
      key: "today",
      label: uiText.workspaceSectionToday,
      count: overlayMissionSections.todayItems.length,
      summary: uiText.workspaceSummaryToday,
    },
    {
      key: "reviews",
      label: uiText.workspaceSectionReviews,
      count: overlayMissionSections.reviewItems.length,
      summary: uiText.workspaceSummaryReviews,
    },
    ...(overlayMissionSections.riskItems.length > 0
      ? [{
          key: "risk",
          label: uiText.workspaceSectionRisks,
          count: overlayMissionSections.riskItems.length,
          summary: uiText.workspaceSummaryRisks,
        }]
      : []),
    ...(overlayMissionSections.performanceCards.length > 0
      ? [{
          key: "performance",
          label: uiText.workspaceSectionPerformance,
          count: overlayMissionSections.performanceCards.length,
          summary: uiText.workspaceSummaryPerformance,
        }]
      : []),
    {
      key: "history",
      label: uiText.workspaceSectionHistory,
      count: overlayMissionSections.historyItems.length,
      summary: uiText.workspaceSummaryHistory,
    },
  ];
  const openSummaryCount = overlayMissionSections.todayItems.length || missionControl?.summary?.open_action_count || 0;
  const workspaceNeedsAttention =
    openSummaryCount > 0 ||
    overlayMissionSections.reviewItems.length > 0 ||
    overlayMissionSections.riskItems.length > 0 ||
    Number(missionControl?.summary?.blocked_count || 0) > 0;
  const marketStatusValue = (() => {
    const summaryPosture = String(missionControl?.summary?.posture || "").toLowerCase();
    const marketPosture = String(insight?.market_insight?.posture || "").toLowerCase();
    const marketCycle = String(
      insight?.market_insight?.structural_cycle ||
      insight?.market_insight?.cycle ||
      ""
    ).toLowerCase();
    return humanizeSurfaceStatus(
      summaryPosture.includes("action_required")
        ? marketPosture || marketCycle || "defensive"
        : summaryPosture || marketPosture || marketCycle || "defensive"
    );
  })();
  const openItemsAreReviews =
    overlayMissionSections.todayItems.length > 0 &&
    overlayMissionSections.todayItems.every((item) => isReviewCandidate(item));
  const compactOpenLabel = firstDashboardContext?.review_label
      ? firstDashboardContext.review_label
      : openItemsAreReviews
      ? (openSummaryCount === 1 ? uiText.openReviewsOne : at("uiText.openReviewsMany", "", { count: openSummaryCount }))
      : (openSummaryCount === 1 ? uiText.openAttentionOne : at("uiText.openAttentionMany", "", { count: openSummaryCount }));
  const previewQueueSections = missionDetailSections.filter((section) =>
    ["today", "reviews", "risk"].includes(section.key) && (section.count > 0 || section.key === "today")
  );
  const previewHasExtraDetail =
    overlayMissionSections.performanceCards.length > 0 || overlayMissionSections.historyItems.length > 0;
  const previewSecondarySectionKey = overlayMissionSections.performanceCards.length > 0 ? "performance" : "history";
  const showMissionSection = (key) => (showFullMissionControl || shouldCondenseMissionControl) && missionDetailSection === key;

  useEffect(() => {
    if (!isOpen || isOnboarding) return;
    const nextBriefing = buildBriefingText(insight);
    if (nextBriefing) {
      setStableBriefingText(nextBriefing);
    }
  }, [
    isOpen,
    isOnboarding,
    insight,
    missionControl,
    preferences?.first_name,
    context.symbol,
    primaryCoachingItem,
  ]);

  useEffect(() => {
    if (!previewSectionsOnly) return;
    const symbol = normalizeScopedAssetSymbol(context?.symbol || globalSymbol) || "UNKNOWN";
    const snapshotScope = String(user?.id || "anonymous");
    setWorkspaceSnapshot(getWorkspaceSnapshot(symbol, snapshotScope));
    return subscribeWorkspaceSnapshot((nextSymbol, snapshot, nextScope) => {
      if (nextSymbol !== symbol || nextScope !== snapshotScope) return;
      setWorkspaceSnapshot(snapshot);
    });
  }, [previewSectionsOnly, context?.symbol, globalSymbol, user?.id]);

  useEffect(() => {
    if (!previewSectionsOnly || !isOpen || isOnboarding) return;
    setStableBriefingText(buildSnapshotBriefingText(workspaceSnapshot));
  }, [previewSectionsOnly, isOpen, isOnboarding, workspaceSnapshot, preferences?.first_name, context.symbol, globalSymbol]);

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

  const showSimpleFinnHistory =
    !isSimpleFinnModal ||
    messages.length > 0 ||
    loading ||
    Boolean(activeState) ||
    recentFinnSessionItems.length > 0;

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
                <p className="mt-0.5 text-[11px] font-bold text-slate-500 dark:text-slate-400 tracking-tight">
                  {compactFinnHeader.slice(1).join(" • ")}
                </p>
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
        {!persistent ? (
          <button
            onClick={() => setIsOpen(false)}
            className="p-2 hover:bg-slate-50 dark:hover:bg-slate-900 rounded-lg transition-colors text-secondary hover:text-slate-900 dark:hover:text-slate-100"
          >
            <X size={18} />
          </button>
        ) : null}
      </div>

      <div className="flex-1 overflow-y-auto no-scrollbar scroll-smooth" ref={scrollRef}>
        {!isSimpleFinnModal && contextMetric && (
          <div className="m-5 p-5 bg-blue-600/5 dark:bg-blue-600/10 border-2 border-blue-600/20 rounded-2xl relative animate-in fade-in slide-in-from-top-4 duration-300">
            <button 
              onClick={() => setContextMetric(null)} 
              className="absolute top-3.5 right-3.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              <X size={16} />
            </button>
            <div className="flex items-center gap-2 mb-2">
              <div className="p-1.5 bg-blue-600 text-white rounded-lg shadow-md shadow-blue-600/20">
                <Target size={14} />
              </div>
              <div>
                <h3 className="text-xs font-black text-slate-900 dark:text-white uppercase tracking-wider">{getMetricTitle(contextMetric.metric)}</h3>
                <span className="text-[10px] font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest">{contextMetric.symbol} · {contextMetric.timeframe}</span>
              </div>
            </div>
            <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 leading-relaxed italic border-l-2 border-blue-500 pl-3 py-0.5 my-2 mb-0">
              "{getMetricAnalysisText(contextMetric.metric, contextMetric.symbol, contextMetric.timeframe)}"
            </p>
          </div>
        )}
        {!isSimpleFinnModal && shouldCondenseMissionControl ? (
          <div className="p-4 border-b border-slate-100 dark:border-slate-800 bg-[linear-gradient(180deg,rgba(248,250,252,0.92)_0%,rgba(255,255,255,1)_100%)] dark:bg-[#0f172a] space-y-3 animate-fade-in">
            {missionControlLoading && !missionControl ? (
              <div className="rounded-[22px] border border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-950/35 px-4 py-4 space-y-3 animate-pulse">
                <div className="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-slate-400">
                  <Sparkles size={11} className="text-blue-500" />
                  {uiText.loadingWorkspace}
                </div>
                <div className="h-4 w-8/12 rounded-full bg-slate-200 dark:bg-slate-800" />
                <div className="h-3 w-5/12 rounded-full bg-slate-200 dark:bg-slate-800" />
                <div className="grid gap-2 md:grid-cols-4">
                  <div className="h-14 rounded-xl bg-slate-100 dark:bg-slate-900" />
                  <div className="h-14 rounded-xl bg-slate-100 dark:bg-slate-900" />
                  <div className="h-14 rounded-xl bg-slate-100 dark:bg-slate-900" />
                  <div className="h-14 rounded-xl bg-slate-100 dark:bg-slate-900" />
                </div>
              </div>
            ) : (
              <>
                <div className="rounded-[22px] border border-slate-200 dark:border-slate-800 bg-white/96 dark:bg-slate-950/30 px-4 py-4 shadow-[0_16px_36px_-34px_rgba(37,99,235,0.35)]">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.24em] text-blue-600 dark:text-blue-300">
                        <Shield size={12} />
                        {uiText.workspaceSummary}
                      </div>
                      {workspaceGreeting ? (
                        <p className="mt-3 text-[13px] font-semibold text-slate-500 dark:text-slate-400">
                          {workspaceGreeting}
                        </p>
                      ) : null}

                      <h3 className="mt-1.5 max-w-4xl text-[22px] font-black leading-[1.18] tracking-tight text-slate-950 dark:text-slate-50 lg:text-[24px]">
                        {workspaceHeadline}
                      </h3>

                      {(workspaceSupport || workspaceActionHint) ? (
                        <p className="mt-2.5 max-w-3xl text-[14px] font-medium leading-6 text-slate-600 dark:text-slate-300">
                          {workspaceSupport || workspaceActionHint}
                        </p>
                      ) : null}

                      <div className="mt-4 flex flex-wrap items-center gap-2">
                        <span className="rounded-full border border-emerald-200/80 bg-emerald-50 px-2.5 py-1 text-[9px] font-black uppercase tracking-[0.16em] text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300">
                          {showFirstDashboardGuidance
                            ? uiText.workspaceFirstDashboardLabel
                            : workspaceIsStillBuilding
                            ? uiText.workspaceBuildingLabel
                            : workspaceNeedsAttention
                            ? uiText.workspaceActionNeeded
                            : uiText.workspaceOnTrack}
                        </span>
                        <div className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.14em] text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
                          <span className="text-slate-400 dark:text-slate-500">{uiText.workspaceStatusMarket}</span>
                          <span className="text-slate-950 dark:text-slate-50">
                            {marketStatusValue}
                          </span>
                        </div>
                        <div className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.14em] text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
                          <span className="text-slate-400 dark:text-slate-500">{uiText.workspaceStatusReviews}</span>
                          <span className="text-slate-950 dark:text-slate-50">{overlayMissionSections.reviewItems.length}</span>
                        </div>
                        <div className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.14em] text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
                          <span className="text-slate-400 dark:text-slate-500">{uiText.workspaceStatusRisks}</span>
                          <span className="text-slate-950 dark:text-slate-50">{overlayMissionSections.riskItems.length}</span>
                        </div>
                      </div>

                      {primaryProfileHabitAlignment && compactBehavioralReason ? (
                        <div className="mt-4 rounded-xl border border-amber-200/80 bg-amber-50/70 px-3 py-2.5 dark:border-amber-900/40 dark:bg-amber-950/20">
                          <div className="text-[8px] font-black uppercase tracking-[0.18em] text-amber-700 dark:text-amber-300">
                            {at("cards.finnSlowsDownOn")} {primaryBehaviorLabel}
                          </div>
                          <p className="mt-1 text-[11px] font-semibold leading-snug text-slate-700 dark:text-slate-200">
                            {compactBehavioralReason}
                          </p>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>

                <div className="rounded-[22px] border border-slate-200 dark:border-slate-800 bg-white/96 dark:bg-slate-950/30 p-3 shadow-[0_14px_32px_-34px_rgba(15,23,42,0.32)]">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.24em] text-blue-600 dark:text-blue-300">
                        <ListChecks size={12} />
                        {uiText.workspaceQueue}
                      </div>
                      <p className="mt-0.5 text-[13px] font-medium text-slate-500 dark:text-slate-400">
                        {uiText.workspaceDetails}
                      </p>
                    </div>
                    <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[9px] font-black uppercase tracking-[0.14em] text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                      {compactOpenLabel}
                    </span>
                  </div>

                  <div className="mt-3 grid gap-2 xl:grid-cols-4">
                    {previewQueueSections.map((section) => (
                      <button
                        key={section.key}
                        type="button"
                        onClick={() => setMissionDetailSection((current) => current === section.key ? "" : section.key)}
                        className={`rounded-[18px] border px-3 py-3 text-left transition-all ${
                          missionDetailSection === section.key
                            ? "border-blue-300 bg-blue-50/70 shadow-[0_16px_40px_-35px_rgba(37,99,235,0.55)] dark:border-blue-900/60 dark:bg-blue-950/20"
                            : "border-slate-200 bg-slate-50/75 hover:border-slate-300 hover:bg-white dark:border-slate-800 dark:bg-slate-900/35 dark:hover:border-slate-700 dark:hover:bg-slate-900/60"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-[9px] font-black uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                            {section.label}
                          </span>
                          <span className="rounded-full bg-white/90 px-2 py-0.5 text-[11px] font-black text-slate-900 shadow-sm dark:bg-slate-950/80 dark:text-slate-100">
                            {section.count}
                          </span>
                        </div>
                        <p className="mt-2 text-[13px] font-semibold leading-5 text-slate-700 dark:text-slate-200">
                          {section.summary}
                        </p>
                      </button>
                    ))}

                    {previewHasExtraDetail ? (
                      <button
                        type="button"
                        onClick={() => setMissionDetailSection((current) => current === previewSecondarySectionKey ? "" : previewSecondarySectionKey)}
                        className={`rounded-[18px] border px-3 py-3 text-left transition-all ${
                          missionDetailSection === previewSecondarySectionKey
                            ? "border-blue-300 bg-blue-50/70 shadow-[0_16px_40px_-35px_rgba(37,99,235,0.55)] dark:border-blue-900/60 dark:bg-blue-950/20"
                            : "border-slate-200 bg-slate-50/75 hover:border-slate-300 hover:bg-white dark:border-slate-800 dark:bg-slate-900/35 dark:hover:border-slate-700 dark:hover:bg-slate-900/60"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-[9px] font-black uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                          {(missionDetailSections.find((section) => section.key === previewSecondarySectionKey)?.label) || uiText.workspaceSectionMore}
                          </span>
                          <span className="rounded-full bg-white/90 px-2 py-0.5 text-[11px] font-black text-slate-900 shadow-sm dark:bg-slate-950/80 dark:text-slate-100">
                            {overlayMissionSections.performanceCards.length + overlayMissionSections.historyItems.length}
                          </span>
                        </div>
                        <p className="mt-2 text-[13px] font-semibold leading-5 text-slate-700 dark:text-slate-200">
                          {(missionDetailSections.find((section) => section.key === previewSecondarySectionKey)?.summary) ||
                            (overlayMissionSections.performanceCards.length > 0
                              ? uiText.workspaceSummaryPerformance
                              : uiText.workspaceSummaryHistory)}
                        </p>
                      </button>
                    ) : null}
                  </div>
                </div>

                {missionDetailSections.map((section) => {
                  if (missionDetailSection !== section.key) return null;

                  if (section.key === "today") {
                    return (
                      <div key={section.key} className="rounded-[24px] border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 p-4 space-y-3">
                        <p className="text-[11px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                          {section.summary}
                        </p>
                        {overlayMissionSections.todayItems.length > 0 ? (
                          overlayMissionSections.todayItems.map((item) => renderMissionSectionCard(item, "today"))
                        ) : (
                          <div className="rounded-xl border border-slate-100 dark:border-slate-800 bg-white/80 dark:bg-slate-950/35 px-3 py-3 text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                            {uiText.noActions}
                          </div>
                        )}
                      </div>
                    );
                  }

                  if (section.key === "reviews") {
                    return (
                      <div key={section.key} className="rounded-[24px] border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 p-4 space-y-3">
                        <p className="text-[11px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                          {section.summary}
                        </p>
                        {overlayMissionSections.reviewItems.length > 0 ? (
                          overlayMissionSections.reviewItems.map((item) => renderMissionSectionCard(item, "reviews"))
                        ) : (
                          <div className="rounded-xl border border-slate-100 dark:border-slate-800 bg-white/80 dark:bg-slate-950/35 px-3 py-3 text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                            {uiText.noReviews}
                          </div>
                        )}
                      </div>
                    );
                  }

                  if (section.key === "risk") {
                    return (
                      <div key={section.key} className="rounded-[24px] border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 p-4 space-y-3">
                        <p className="text-[11px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                          {section.summary}
                        </p>
                        {overlayMissionSections.riskItems.length > 0 ? (
                          overlayMissionSections.riskItems.map((item) => renderMissionSectionCard(item, "risk"))
                        ) : (
                          <div className="rounded-xl border border-slate-100 dark:border-slate-800 bg-white/80 dark:bg-slate-950/35 px-3 py-3 text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                            {at("cards.noExtraBlockers")}
                          </div>
                        )}
                      </div>
                    );
                  }

                  if (section.key === "performance") {
                    return (
                      <div key={section.key} className="rounded-[24px] border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 p-4 space-y-3">
                        <p className="text-[11px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                          {section.summary}
                        </p>
                        {overlayMissionSections.performanceCards.length > 0 ? (
                          <div className="space-y-2">
                            {overlayMissionSections.performanceCards.map((card) => (
                              <div
                                key={card.key}
                                className={`rounded-xl border px-3 py-3 ${
                                  card.tone === "positive"
                                    ? "border-emerald-100 dark:border-emerald-900/40 bg-emerald-50/30 dark:bg-emerald-950/10"
                                    : card.tone === "attention"
                                      ? "border-amber-100 dark:border-amber-900/40 bg-amber-50/45 dark:bg-amber-950/15"
                                      : "border-slate-100 dark:border-slate-800 bg-white/90 dark:bg-slate-950/25"
                                }`}
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <p className="text-[11px] font-black leading-snug text-slate-900 dark:text-slate-100">
                                    {card.title}
                                  </p>
                                  {card.status ? (
                                    <span className="rounded-full bg-slate-100 dark:bg-slate-900 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                                      {card.status}
                                    </span>
                                  ) : null}
                                </div>
                                <p className="mt-1 text-[10px] font-semibold leading-snug text-slate-600 dark:text-slate-300">
                                  {card.summary}
                                </p>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="rounded-xl border border-slate-100 dark:border-slate-800 bg-white/80 dark:bg-slate-950/35 px-3 py-3 text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                            {uiText.noPerformance}
                          </div>
                        )}
                      </div>
                    );
                  }

                  return (
                    <div key={section.key} className="rounded-[24px] border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 p-4 space-y-3">
                      <p className="text-[11px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                        {section.summary}
                      </p>
                      {overlayMissionSections.historyItems.length > 0 ? (
                        overlayMissionSections.historyItems.map(renderMissionHistoryEntry)
                      ) : (
                        <div className="rounded-xl border border-slate-100 dark:border-slate-800 bg-white/80 dark:bg-slate-950/35 px-3 py-3 text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                          {uiText.noHistory}
                        </div>
                      )}
                    </div>
                  );
                })}
              </>
            )}
          </div>
        ) : null}

        {/* SECTION 1 — FINN POSTURE & BRIEFING */}
        {!isSimpleFinnModal && !shouldCondenseMissionControl && (
        <div className="p-5 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/20 space-y-2.5 animate-fade-in">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Shield size={12} className="text-blue-600" />
                <span className="text-[10px] font-black text-slate-900 dark:text-white uppercase tracking-widest">{uiText.activeBriefing}</span>
              </div>
            <span className="text-[9px] font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 px-2 py-0.5 rounded-full border border-emerald-200/50 dark:border-emerald-800/50">{uiText.defensivePosture}</span>
          </div>
          {isOnboarding ? (
            <div className="p-4 bg-blue-600/5 dark:bg-blue-600/10 border-2 border-blue-600/20 rounded-2xl animate-in slide-in-from-right-4 duration-500">
               <div className="flex items-center gap-2.5 mb-3">
                  <div className="p-1.5 bg-blue-600 rounded-lg shadow-lg shadow-blue-600/20">
                    <ListChecks size={14} className="text-white" />
                  </div>
                  <span className="text-[10px] font-black text-blue-600 dark:text-blue-400 tracking-widest uppercase">{uiText.startGuide}</span>
               </div>
               <div className="space-y-3">
                  <p className="text-sm font-bold text-foreground dark:text-slate-100 leading-snug">
                    {/* 🎖️ CELEBRATION MODE */}
                    {stepStatus?.[`has_${pathname.split('/').pop()}`] ? (
                      at("onboarding.done", "", { flow: pathname.split('/').pop() })
                    ) : (
                      pathname.includes("market") ? at("onboarding.market") :
                      pathname.includes("macro") ? at("onboarding.macro") :
                      pathname.includes("technical") ? at("onboarding.technical") :
                      pathname.includes("setup") ? at("onboarding.setup") :
                      pathname.includes("strategy") ? at("onboarding.strategy") :
                      at("onboarding.default")
                    )}
                  </p>
               </div>
            </div>
          ) : (
            <div className="space-y-3">
              {profileSummaryLabel && (
                <div className="rounded-full border border-blue-100 bg-blue-50/60 px-3 py-1 text-[9px] font-black uppercase tracking-widest text-blue-700 dark:border-blue-900/50 dark:bg-blue-950/20 dark:text-blue-300 inline-flex max-w-full">
                  {uiText.alignedTo}: {profileSummaryLabel}
                </div>
              )}
              <div className="min-h-[52px]">
                {resolvedBriefingText ? (
                  <p className="whitespace-pre-line text-xs font-semibold text-slate-800 dark:text-slate-200 leading-relaxed italic border-l-3 border-blue-500 pl-3 py-0.5">
                    {resolvedBriefingText}
                  </p>
                ) : insightLoading && !previewSectionsOnly ? (
                  <div className="border-l-3 border-blue-500 pl-3 py-1 space-y-2 animate-pulse">
                    <div className="h-3 w-11/12 rounded-full bg-slate-200 dark:bg-slate-800" />
                    <div className="h-3 w-8/12 rounded-full bg-slate-200 dark:bg-slate-800" />
                  </div>
                ) : (
                  <p className="whitespace-pre-line text-xs font-semibold text-slate-800 dark:text-slate-200 leading-relaxed italic border-l-3 border-blue-500 pl-3 py-0.5">
                    {buildBriefingText(insight)}
                  </p>
                )}
              </div>
              {briefingFollowUpActions.length > 0 && (
                renderFollowUpButtons(briefingFollowUpActions, true)
              )}
            </div>
          )}
        </div>
        )}

        {/* SECTION 1B — FINN Mission Control */}
        {!isSimpleFinnModal && !shouldCondenseMissionControl && (missionControlLoading || missionControl?.summary || missionControl?.coaching_loop || missionControl?.behavioral_insight) && (
          <div className="p-5 border-b border-slate-100 dark:border-slate-800 bg-white dark:bg-[#0f172a] space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Activity size={12} className="text-blue-600" />
                <span className="text-[10px] font-black text-slate-900 dark:text-white uppercase tracking-widest">{uiText.workspaceOverview}</span>
              </div>
              <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full border ${
                missionControl?.summary?.posture === "stable"
                  ? "bg-emerald-50 text-emerald-600 border-emerald-200/70 dark:bg-emerald-900/20 dark:text-emerald-300 dark:border-emerald-800/50"
                  : "bg-amber-50 text-amber-700 border-amber-200/70 dark:bg-amber-900/20 dark:text-amber-300 dark:border-amber-800/50"
              }`}>
                {compactOpenLabel}
              </span>
            </div>

            {missionControlLoading && !missionControl && (
              <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 px-3 py-3 space-y-2 animate-pulse">
                <div className="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-slate-400">
                  <Sparkles size={11} className="text-blue-500" />
                  {uiText.loadingWorkspace}
                </div>
                <div className="h-3 w-2/3 rounded-full bg-slate-200 dark:bg-slate-800" />
                <div className="h-3 w-1/2 rounded-full bg-slate-200 dark:bg-slate-800" />
              </div>
            )}

            {!showFullMissionControl && (
              <div className="space-y-3">
                <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 px-3 py-3 space-y-3">
                  <div>
                    <div className="text-[8px] font-black uppercase tracking-widest text-slate-400">{uiText.todayFirst}</div>
                    <p className="mt-1 text-[12px] font-black leading-snug text-slate-900 dark:text-slate-100">
                      {primaryCoachingItem ? humanizeMissionTitle(primaryCoachingItem) : (missionControl?.coaching_loop?.headline || "Kies eerst je eerstvolgende veilige stap.")}
                    </p>
                    {compactMissionReason && (
                      <div className="mt-2">
                        <div className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">{uiText.why}</div>
                        <p className="mt-1 text-[10px] font-semibold leading-snug text-slate-600 dark:text-slate-300">
                          {compactMissionReason}
                        </p>
                      </div>
                    )}
                    {primaryProfileHabitAlignment && compactBehavioralReason && (
                      <div className="mt-2 rounded-lg border border-amber-200/80 bg-amber-50/70 px-2.5 py-2 dark:border-amber-900/40 dark:bg-amber-950/20">
                        <div className="text-[7px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">
                          {at("cards.finnSlowsDownOn")} {primaryBehaviorLabel}
                        </div>
                        <p className="mt-1 text-[9px] font-semibold leading-snug text-slate-700 dark:text-slate-200">
                          {compactBehavioralReason}
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 overflow-hidden">
                  {missionDetailSections.map((section, index) => (
                    <button
                      key={section.key}
                      type="button"
                      onClick={() => setMissionDetailSection((current) => current === section.key ? "" : section.key)}
                      className={`w-full flex items-center justify-between gap-3 px-4 py-3 text-left transition-colors ${
                        missionDetailSection === section.key
                          ? "bg-blue-50/70 text-blue-700 dark:bg-blue-950/20 dark:text-blue-300"
                          : "bg-transparent text-slate-900 dark:text-slate-100 hover:bg-slate-100/70 dark:hover:bg-slate-900/40"
                      } ${index !== missionDetailSections.length - 1 ? "border-b border-slate-200 dark:border-slate-800" : ""}`}
                    >
                      <span className="text-[11px] font-black tracking-wide">
                        {section.label} <span className="text-slate-400 dark:text-slate-500">({section.count})</span>
                      </span>
                      <ChevronDown size={16} className={`transition-transform ${missionDetailSection === section.key ? "rotate-180" : ""}`} />
                    </button>
                  ))}
                </div>
              </div>
            )}

            {missionDetailSections.map((section) => {
              if (missionDetailSection !== section.key) return null;

              if (section.key === "today") {
                return (
                  <div key={section.key} className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 p-3 space-y-3">
                    <p className="text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                      {section.summary}
                    </p>
                    {overlayMissionSections.todayItems.length > 0 ? (
                      overlayMissionSections.todayItems.map((item) => renderMissionSectionCard(item, "today"))
                    ) : (
                      <div className="rounded-xl border border-slate-100 dark:border-slate-800 bg-white/80 dark:bg-slate-950/35 px-3 py-3 text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                        {uiText.noActions}
                      </div>
                    )}
                  </div>
                );
              }

              if (section.key === "reviews") {
                return (
                  <div key={section.key} className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 p-3 space-y-3">
                    <p className="text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                      {section.summary}
                    </p>
                    {overlayMissionSections.reviewItems.length > 0 ? (
                      overlayMissionSections.reviewItems.map((item) => renderMissionSectionCard(item, "reviews"))
                    ) : (
                      <div className="rounded-xl border border-slate-100 dark:border-slate-800 bg-white/80 dark:bg-slate-950/35 px-3 py-3 text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                        {uiText.noReviews}
                      </div>
                    )}
                  </div>
                );
              }

              if (section.key === "risk") {
                return (
                  <div key={section.key} className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 p-3 space-y-3">
                    <p className="text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                      {section.summary}
                    </p>
                    {overlayMissionSections.riskItems.length > 0 ? (
                      overlayMissionSections.riskItems.map((item) => renderMissionSectionCard(item, "risk"))
                    ) : (
                      <div className="rounded-xl border border-slate-100 dark:border-slate-800 bg-white/80 dark:bg-slate-950/35 px-3 py-3 text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                        {at("cards.noExtraBlockers")}
                      </div>
                    )}
                  </div>
                );
              }

              if (section.key === "performance") {
                return (
                  <div key={section.key} className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 p-3 space-y-3">
                    <p className="text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                      {section.summary}
                    </p>
                    {overlayMissionSections.performanceCards.length > 0 ? (
                      <div className="space-y-2">
                        {overlayMissionSections.performanceCards.map((card) => (
                          <div
                            key={card.key}
                            className={`rounded-xl border px-3 py-3 ${
                              card.tone === "positive"
                                ? "border-emerald-100 dark:border-emerald-900/40 bg-emerald-50/30 dark:bg-emerald-950/10"
                                : card.tone === "attention"
                                  ? "border-amber-100 dark:border-amber-900/40 bg-amber-50/45 dark:bg-amber-950/15"
                                  : "border-slate-100 dark:border-slate-800 bg-white/90 dark:bg-slate-950/25"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-[11px] font-black leading-snug text-slate-900 dark:text-slate-100">
                                {card.title}
                              </p>
                              {card.status && (
                                <span className="rounded-full bg-slate-100 dark:bg-slate-900 px-2 py-0.5 text-[7px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                                  {card.status}
                                </span>
                              )}
                            </div>
                            <p className="mt-1 text-[10px] font-semibold leading-snug text-slate-600 dark:text-slate-300">
                              {card.summary}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-xl border border-slate-100 dark:border-slate-800 bg-white/80 dark:bg-slate-950/35 px-3 py-3 text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                        {uiText.noPerformance}
                      </div>
                    )}
                  </div>
                );
              }

              return (
                <div key={section.key} className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/50 p-3 space-y-3">
                  <p className="text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                    {section.summary}
                  </p>
                  {overlayMissionSections.historyItems.length > 0 ? (
                    overlayMissionSections.historyItems.map(renderMissionHistoryEntry)
                  ) : (
                    <div className="rounded-xl border border-slate-100 dark:border-slate-800 bg-white/80 dark:bg-slate-950/35 px-3 py-3 text-[10px] font-semibold leading-snug text-slate-500 dark:text-slate-400">
                      {uiText.noHistory}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {!previewSectionsOnly && (
        <>
        {/* MESSAGES AREA */}
        {showSimpleFinnHistory ? (
        <div className={`space-y-4 ${isSimpleFinnModal ? "p-5 pb-8" : "p-6 pb-20"}`}>
          {isSimpleFinnModal && (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <div className="px-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400 dark:text-slate-500">
                  {uiText.backendSessions}
                </div>
                <button
                  type="button"
                  onClick={() => void startNewFinnConversation()}
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
                    onClick={() => void restoreFinnSession(session.id)}
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

          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[90%] rounded-2xl p-4 ${
                m.role === "user" 
                  ? "bg-blue-600 text-white shadow-lg shadow-blue-600/10" 
                  : m.isError 
                    ? "bg-rose-50 dark:bg-rose-900/20 border border-rose-100 dark:border-rose-900 text-rose-700 dark:text-rose-300"
                    : "bg-[var(--color-border-subtle)] dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-foreground dark:text-slate-100"
                }`}>
                <p className="text-sm leading-relaxed">{m.text}</p>
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && renderOperatorReadoutCard(m)}
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && renderAgentController(getMessageAgentController(m))}
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && renderDecisionReviewV3Card(getMessageDecisionReview(m))}
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && renderPlanAdherenceCard(getMessagePlanAdherenceReview(m))}
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && renderOutcomeTrackingCard(getMessageOutcomeTracking(m))}
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && renderPriorityEngineCard(getMessagePriorityEngine(m))}
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && renderMemoryV2Card(getMessageMemoryV2(m))}
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && renderPortfolioOperatingSystemCard(getMessagePortfolioOperatingSystem(m))}
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && renderBehavioralIntelligenceCard(getMessageBehavioralAnalysis(m))}
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && renderPortfolioRisk(getMessagePortfolioRisk(m))}
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && renderExecutionReviewCard(getMessageExecutionReview(m))}
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && renderOperatorResolutionCard(getMessageOperatorResolution(m))}
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && renderAgentVerdicts(getMessageAgentVerdicts(m))}
                {!isSimpleFinnModal && m.role === "assistant" && m.isComplete !== false && (() => {
                  const suggestions = getMessageFollowUpActions(m);
                  if (suggestions.length === 0) return null;
                  return renderFollowUpButtons(suggestions);
                })()}
                {!isSimpleFinnModal && m.reasoning && m.isComplete !== false && (
                  <ReasoningWidget reasoning={m.reasoning} />
                )}
                {/* Universal Action Card Renderer */}
                {m.isComplete !== false && (() => {
                  const card = (m.draft?.type === "action_card" ? m.draft : null) || (m.action?.type === "action_card" ? m.action : null);
                  if (card) {
                    return (
                      <UniversalActionCard
                        card={card}
                        onCancel={() => handleCancelDraft(i)}
                        onSuccess={() => handleDraftSuccess(i)}
                        handleEditDraft={handleEditDraft}
                      />
                    );
                  }
                  return null;
                })()}
                {m.action && m.action.type !== "action_card" && !m.draft?.plan_type && m.isComplete !== false && (
                  <ActionCard action={m.action} onAction={handleActionClick} />
                )}
                {m.draft && m.intent !== "plan_creation" && m.flow !== "plan_creation" && m.intent !== "strategy_creation" && m.flow !== "strategy_creation" && !m.draft?.plan_type && m.draft?.draft_kind !== "strategy" && m.draft?.draft_kind !== "indicator_config" && m.draft.type !== "action_card" && !m.draftCanceled && !m.draftExecuted && m.isComplete !== false && (
                  <DraftCard 
                    draft={m.draft} 
                    onCancel={() => handleCancelDraft(i)} 
                    onSuccess={() => handleDraftSuccess(i)}
                    handleEditDraft={handleEditDraft}
                  />
                )}
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
                {renderBehavioralMemoryAckCard(m)}
                {!isSimpleFinnModal && renderDraftCard(m)}
                {!isSimpleFinnModal && renderInlineActionCard(m)}
                {m.isError && (
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

          {/* LIVE INTERACTIVE CONCEPT CARD */}
          {activeState && activeState.current_flow && activeState.current_flow !== "none" && activeState.current_flow !== "plan_creation" && (() => {
            const flow = activeState.current_flow;
            const slots = flow === "strategy_creation" ? getStrategyFlowSlots(activeState) : (activeState.slots || {});
            const canConfirmActiveFlow = Boolean(activeState.can_confirm);
            let shouldShowCard = false;
            
            if (flow === "setup_creation") {
              const hasCoreChoice = !!slots.setup_type;
              const hasMeaningfulProgress = !!(slots.timeframe && (slots.dca_frequency || slots.entry || slots.stop_loss || slots.base_amount));
              shouldShowCard = canConfirmActiveFlow && hasCoreChoice && hasMeaningfulProgress;
            } else if (flow === "strategy_creation") {
              shouldShowCard = false;
            } else if (flow === "bot_creation") {
              shouldShowCard = canConfirmActiveFlow && !!slots.budget_total_eur;
            } else {
              shouldShowCard = canConfirmActiveFlow;
            }

            if (!shouldShowCard) return null;

            return (
              <div className="flex justify-start animate-in slide-in-from-bottom-3 duration-300">
                <div className="max-w-[90%]">
                  <ConceptCard 
                    state={activeState}
                    onCancel={() => {
                      handleChat("annuleer", false);
                      setActiveState(null);
                    }}
                    onEdit={() => {
                      const mockDraft = {
                        type: activeState.current_flow.split("_")[0],
                        payload: {
                          name: activeState.slots?.name || `${activeState.slots?.symbol || globalSymbol} Concept`,
                          symbol: activeState.slots?.symbol || globalSymbol,
                          setup_type: activeState.slots?.setup_type || "trade",
                          ...activeState.slots
                        }
                      };
                      handleEditDraft(mockDraft, async () => {
                        setActiveState(null);
                        await handleChat("ik heb hem zojuist opgeslagen", true);
                      });
                    }}
                    onFinalize={() => handleChat(flow === "strategy_creation" ? "maak de strategie" : "maak de setup")}
                    onUpdateSlots={(newSlots) => {
                      if (flow === "setup_creation") {
                        if (newSlots.setup_type) handleChat(newSlots.setup_type, true);
                        if (newSlots.dca_frequency) handleChat(newSlots.dca_frequency, true);
                      }
                      if (flow === "bot_creation" && (newSlots.budget_total_eur || newSlots.budget_daily_limit_eur)) {
                        handleChat(String(newSlots.budget_total_eur || newSlots.budget_daily_limit_eur), true);
                      }
                    }}
                  />
                </div>
              </div>
            );
          })()}

          {loading && (
            <ChatSkeleton />
          )}
          <div ref={messagesEndRef} />
        </div>
        ) : null}
        </>
        )}
      </div>

      <Drawer
        isOpen={Boolean(draftDrawer)}
        onClose={closeDraftDrawer}
        isCloseBlocked={() => Boolean(draftFormRef.current?.isSubmitting?.())}
        title={draftDrawer?.title || at("uiText.draftLabel")}
        subtitle={at("uiText.draftLabel")}
        width={draftDrawer?.type === "setup" ? "max-w-3xl" : "max-w-2xl"}
      >
        {draftDrawer?.type === "setup" ? (
          <SetupForm
            ref={draftFormRef}
            mode="new"
            initialData={draftDrawer.payload}
            onSaved={() => {
              trackFinnConfirmEvent("finn_confirm_confirmed", draftDrawer.trackingType);
              showSnackbar(at("modals.setupCreatedSuccess"), "success");
              draftDrawer.onSuccess?.();
              setDraftDrawer(null);
            }}
          />
        ) : null}

        {draftDrawer?.type === "strategy" ? (
          <StrategyForm
            ref={draftFormRef}
            setups={draftDrawer.setups || []}
            isEdit={false}
            strategy={{
              name: draftDrawer.payload?.name,
              symbol: draftDrawer.payload?.symbol,
              setup_type: draftDrawer.payload?.setup_type,
              setup_id: draftDrawer.payload?.setup_id || draftDrawer.setups?.[0]?.id,
              base_amount: draftDrawer.payload?.base_amount,
              entry: draftDrawer.payload?.entry,
              targets: draftDrawer.payload?.targets,
              stop_loss: draftDrawer.payload?.stop_loss,
              execution_mode: draftDrawer.payload?.execution_mode || "fixed",
            }}
            onSubmit={async (payload) => {
              await createStrategy(payload);
              trackFinnConfirmEvent("finn_confirm_confirmed", draftDrawer.trackingType);
              showSnackbar(at("modals.strategyCreatedSuccess"), "success");
              draftDrawer.onSuccess?.();
              setDraftDrawer(null);
            }}
          />
        ) : null}

        {draftDrawer?.type === "bot" ? (
          <AddBotForm
            ref={draftFormRef}
            strategies={draftDrawer.strategies || []}
            initialData={{
              name: draftDrawer.payload?.name,
              strategy_id: draftDrawer.payload?.strategy_id || draftDrawer.strategies?.[0]?.id,
              mode: draftDrawer.payload?.mode || "manual",
              is_live: draftDrawer.payload?.is_live || false,
              risk_profile: draftDrawer.payload?.risk_profile || "balanced",
              base_currency: draftDrawer.payload?.base_currency || "EUR",
              budget_total_eur: draftDrawer.payload?.budget_total_eur || 500.0,
              budget_daily_limit_eur: draftDrawer.payload?.budget_daily_limit_eur || 50.0,
              budget_min_order_eur: draftDrawer.payload?.budget_min_order_eur || 10.0,
              budget_max_order_eur: draftDrawer.payload?.budget_max_order_eur || 100.0,
              max_asset_exposure_pct: draftDrawer.payload?.max_asset_exposure_pct || 100.0,
            }}
            hideActions={false}
            submitLabel={at("modals.saveCreate")}
            submitBusyLabel={at("uiText.loadingShort")}
            cancelLabel={uiText.cancel}
            successMessage=""
            saveFailedMessage={at("universalAction.executionFailed")}
            onCancel={closeDraftDrawer}
            onSubmit={async (payload) => {
              return await createBotConfig({
                ...payload,
                cadence: draftDrawer.payload?.cadence || "daily",
              });
            }}
            onSaved={() => {
              trackFinnConfirmEvent("finn_confirm_confirmed", draftDrawer.trackingType);
              showSnackbar("Bot succesvol aangemaakt!", "success");
              draftDrawer.onSuccess?.();
              setDraftDrawer(null);
            }}
          />
        ) : null}
      </Drawer>

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
          {isSimpleFinnModal ? (
            <FinnCommandCenter
              ref={commandCenterRef}
              isOpen={isOpen}
              query={activeQuery}
              request={commandRequest}
              onQueryChange={updateQuery}
              onAskFinn={() => handleChat()}
              onClose={() => setIsOpen(false)}
              watchlist={watchlist}
            />
          ) : null}
          <div className="relative group">
          {isSimpleFinnModal && showComposerMenu ? (
            <div className="absolute bottom-[calc(100%+10px)] left-0 z-20 w-60 overflow-hidden rounded-2xl border border-slate-200 bg-white p-1.5 shadow-xl shadow-slate-900/10 dark:border-slate-800 dark:bg-slate-950">
              <button
                type="button"
                onClick={() => {
                  setShowComposerMenu(false);
                  updateQuery("");
                  commandCenterRef.current?.openAssetSearch();
                  composerInputRef.current?.focus();
                }}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-semibold text-slate-800 transition hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-900"
              >
                <Search size={17} className="text-slate-500" />
                {composerMenuCopy.asset}
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowComposerMenu(false);
                  updateQuery("");
                  commandCenterRef.current?.openIndicatorSearch();
                  composerInputRef.current?.focus();
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
          <input 
            ref={composerInputRef}
            type="text" 
            value={activeQuery}
            onChange={(e) => {
              setShowComposerMenu(false);
              updateQuery(e.target.value);
            }}
            onKeyDown={(event) => {
              if (isSimpleFinnModal && commandCenterRef.current?.handleKeyDown(event)) return;
              if (event.key === "Enter") handleChat();
            }}
            placeholder={isSimpleFinnModal ? composerMenuCopy.placeholder : uiText.inputPlaceholder}
            className={`w-full pr-14 py-4 bg-[var(--color-border-subtle)] dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-2xl focus:ring-4 focus:ring-blue-600/5 focus:bg-white dark:focus:bg-slate-800 focus:border-blue-600/20 transition-all outline-none text-sm text-foreground dark:text-slate-100 ${isSimpleFinnModal ? "pl-14" : "pl-6"}`}
          />
          <button 
            onClick={() => {
              if (isSimpleFinnModal && commandCenterRef.current?.submitPrimary()) return;
              handleChat();
            }}
            disabled={loading || !activeQuery.trim()}
            className="absolute right-3 top-2.5 p-2 rounded-xl bg-slate-900 dark:bg-blue-600 text-white hover:bg-blue-600 dark:hover:bg-blue-700 disabled:opacity-50 transition-all shadow-lg"
          >
            <Send size={18} />
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

export function FinnPanel(props) {
  return (
    <Suspense fallback={null}>
      <AIAssistantContent
        {...props}
        isOpen={true}
        setIsOpen={() => {}}
        persistent
      />
    </Suspense>
  );
}

function UniversalActionCard({ card, onCancel, onSuccess, handleEditDraft }) {
  const { openConfirm, showSnackbar } = useModal();
  const { t } = useTranslation();
  const [status, setStatus] = useState("pending"); // pending, executing, success, error, canceled
  const [errorMessage, setErrorMessage] = useState("");
  const assistantCopy = t?.assistant || {};
  const at = (path, fallback = "", vars = {}) => interpolateTranslation(getDictionaryValue(assistantCopy, path) ?? fallback, vars);
  const uiText = {
    actionCanceled: at("uiText.actionCanceled"),
    actionSucceeded: at("uiText.actionSucceeded"),
    aiCommandCenter: at("uiText.aiCommandCenter"),
    conceptSuffix: at("uiText.conceptSuffix"),
    draftLabel: at("uiText.draftLabel"),
    actionLabel: at("uiText.actionLabel"),
    asset: at("uiText.asset"),
    setupType: at("uiText.setupType"),
    dcaParameters: at("uiText.dcaParameters"),
    scoreThresholds: at("uiText.scoreThresholds"),
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
    safetyProfile: at("uiText.safetyProfile"),
    budget: at("uiText.budget"),
    environment: at("uiText.environment"),
    mode: at("uiText.mode"),
    liveReal: at("uiText.liveReal"),
    paperSandbox: at("uiText.paperSandbox"),
  };

  const cardType = card.card_type || "";
  const payload = card.payload || {};
  const isDraft = cardType.endsWith("_draft_card");
  const baseType = cardType.replace("_draft_card", "").replace("_card", ""); // setup, strategy, bot, add_to_watchlist, remove_from_watchlist etc.

  const handleApprove = async () => {
    setStatus("executing");
    setErrorMessage("");
    try {
      const res = await executePendingAction(card.action_id);
      if (res && res.error) {
        throw new Error(res.error || at("universalAction.executionFailed"));
      }
      setStatus("success");
      showSnackbar(at("universalAction.executionSucceeded"), "success");
      if (onSuccess) onSuccess();
    } catch (err) {
      console.error("Action execution failed:", err);
      setStatus("error");
      setErrorMessage(err.message || at("universalAction.executionError"));
      showSnackbar(at("universalAction.executionFailed"), "danger");
    }
  };

  const handleCancelClick = () => {
    setStatus("canceled");
    if (onCancel) onCancel();
  };

  const handleEditClick = () => {
    if (!handleEditDraft) return;
    const draftType = cardType.replace("_draft_card", ""); // setup, strategy, bot
    const mockDraft = {
      type: draftType,
      payload: payload
    };
    handleEditDraft(mockDraft, () => {
      setStatus("success");
      if (onSuccess) onSuccess();
    });
  };

  // --- Theme styling ---
  const getAccentGradient = () => {
    if (baseType === "setup") return "from-amber-500 to-yellow-400";
    if (baseType === "strategy") return "from-blue-500 to-indigo-500";
    if (baseType === "bot") return "from-emerald-500 to-teal-500";
    return "from-violet-500 to-fuchsia-500";
  };

  const getRiskBadge = () => {
    if (baseType === "setup") {
      const isDca = payload.setup_type === "dca";
      return isDca 
        ? { text: uiText.riskLow, class: "bg-emerald-500/10 text-emerald-500 dark:text-emerald-400 border-emerald-500/20" }
        : { text: uiText.riskMedium, class: "bg-amber-500/10 text-amber-500 dark:text-amber-400 border-amber-500/20" };
    }
    if (baseType === "strategy") {
      const sl = parseFloat(payload.stop_loss);
      const isHighSl = sl && sl > 12;
      return isHighSl
        ? { text: uiText.riskHigh, class: "bg-rose-500/10 text-rose-500 dark:text-rose-400 border-rose-500/20" }
        : { text: uiText.riskMedium, class: "bg-amber-500/10 text-amber-500 dark:text-amber-400 border-amber-500/20" };
    }
    if (baseType === "bot") {
      const risk = payload.risk_profile || "balanced";
      if (risk === "aggressive") return { text: uiText.riskActive, class: "bg-rose-500/10 text-rose-500 dark:text-rose-400 border-rose-500/20" };
      if (risk === "conservative") return { text: uiText.riskConservative, class: "bg-emerald-500/10 text-emerald-500 dark:text-emerald-400 border-emerald-500/20" };
      return { text: uiText.riskBalanced, class: "bg-blue-500/10 text-blue-500 dark:text-blue-400 border-blue-500/20" };
    }
    return { text: uiText.operational, class: "bg-violet-500/10 text-violet-500 dark:text-violet-400 border-violet-500/20" };
  };

  const riskBadge = getRiskBadge();

  if (status === "canceled") {
    return (
      <div className="mt-4 p-4 bg-slate-100/50 dark:bg-slate-950/20 border border-dashed border-slate-200 dark:border-slate-800/80 rounded-2xl text-center text-[10px] text-slate-400 dark:text-slate-500 font-bold uppercase tracking-wider animate-in fade-in duration-200">
        ✕ {uiText.actionCanceled}
      </div>
    );
  }

  if (status === "success") {
    return (
      <div className="mt-4 p-5 bg-emerald-500/10 dark:bg-emerald-950/20 border border-emerald-500/30 rounded-2xl text-center text-xs text-emerald-600 dark:text-emerald-400 font-black uppercase tracking-widest flex flex-col items-center justify-center gap-2 animate-in fade-in zoom-in-95 duration-300">
        <div className="w-10 h-10 rounded-full bg-emerald-500 text-white flex items-center justify-center text-lg font-black shadow-lg shadow-emerald-500/20 animate-bounce">
          ✓
        </div>
        <span>{uiText.actionSucceeded}</span>
      </div>
    );
  }

  return (
    <div className="mt-4 overflow-hidden rounded-2xl border border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-xl shadow-slate-100/10 dark:shadow-none animate-in fade-in slide-in-from-bottom-4 duration-300">
      {/* CARD ACCENT LINE */}
      <div className={`h-1.5 w-full bg-gradient-to-r ${getAccentGradient()}`} />

      <div className="p-4 space-y-4">
        {/* CARD TITLE & RISK BADGE */}
        <div className="flex items-start justify-between">
          <div className="space-y-0.5">
            <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
              {uiText.aiCommandCenter}
            </span>
            <h4 className="text-xs font-black text-foreground dark:text-slate-200 tracking-tight leading-snug">
              {payload.name || (baseType === "add_to_watchlist" ? at("universalAction.watchlistActivation", "", { symbol: payload.symbol }) : baseType === "remove_from_watchlist" ? at("universalAction.watchlistDeactivation", "", { symbol: payload.symbol }) : `${payload.symbol || uiText.asset} ${uiText.conceptSuffix}`)}
            </h4>
          </div>
          <div className="flex flex-col items-end gap-1.5">
            <span className={`text-[8px] font-black uppercase tracking-wider px-2 py-0.5 rounded-md shadow-sm text-white bg-gradient-to-r ${getAccentGradient()}`}>
              {baseType} {isDraft ? uiText.draftLabel : uiText.actionLabel}
            </span>
            <span className={`text-[8px] font-black uppercase px-1.5 py-0.5 rounded border ${riskBadge.class}`}>
              {riskBadge.text}
            </span>
          </div>
        </div>

        {/* METADATA CONTENT AREA */}
        <div className="rounded-xl bg-slate-50 dark:bg-slate-950 p-3.5 border border-slate-100 dark:border-slate-800/80 space-y-2.5 shadow-inner">
          {baseType === "setup" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col col-span-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.name || "Naam"}</span>
                <span className="text-xs text-foreground dark:text-slate-200">{payload.name || "—"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.asset}</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{payload.symbol || globalSymbol || context.symbol || "—"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.setupType}</span>
                <span className="uppercase text-xs text-foreground dark:text-slate-200">{payload.setup_type || "dca"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.timeframe || "Timeframe"}</span>
                <span className="text-xs text-foreground dark:text-slate-200">{payload.timeframe || "—"}</span>
              </div>
              {(payload.market_condition || payload.min_macro_score !== undefined) && (
                <div className="flex flex-col col-span-2 border-t border-slate-100 dark:border-slate-800 pt-2">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.marketCondition}</span>
                  <span className="text-xs text-foreground dark:text-slate-200">
                    {getSetupMarketConditionLabel(payload.market_condition || inferSetupMarketConditionFromScores(payload), uiText)}
                  </span>
                </div>
              )}
              {payload.setup_type === "dca" && (
                <div className="flex flex-col col-span-2 border-t border-slate-100 dark:border-slate-800 pt-2">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.dcaParameters}</span>
                  <span className="text-xs text-foreground dark:text-slate-200">
                    {[payload.dca_frequency, payload.dca_day ? `op ${payload.dca_day}` : null].filter(Boolean).join(" ") || "—"}
                  </span>
                </div>
              )}
              {!(payload.market_condition || inferSetupMarketConditionFromScores(payload)) && (payload.min_macro_score !== undefined || payload.min_technical_score !== undefined) && (
                <div className="flex flex-col col-span-2 border-t border-slate-100 dark:border-slate-800 pt-2 space-y-1">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">{uiText.scoreThresholds}</span>
                  <div className="grid grid-cols-3 gap-2 mt-1">
                    <div className="bg-white dark:bg-slate-900 rounded-lg p-1.5 text-center border border-slate-100 dark:border-slate-800">
                      <div className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-500">Macro</div>
                      <div className="text-[10px] font-mono font-black text-blue-500">{payload.min_macro_score ?? 30}-{payload.max_macro_score ?? 70}</div>
                    </div>
                    <div className="bg-white dark:bg-slate-900 rounded-lg p-1.5 text-center border border-slate-100 dark:border-slate-800">
                      <div className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-500">Tech</div>
                      <div className="text-[10px] font-mono font-black text-amber-500">{payload.min_technical_score ?? 40}-{payload.max_technical_score ?? 80}</div>
                    </div>
                    <div className="bg-white dark:bg-slate-900 rounded-lg p-1.5 text-center border border-slate-100 dark:border-slate-800">
                      <div className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-500">Market</div>
                      <div className="text-[10px] font-mono font-black text-emerald-500">{payload.min_market_score ?? 20}-{payload.max_market_score ?? 60}</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {baseType === "strategy" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.asset}</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{payload.symbol || globalSymbol || context.symbol || "—"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.baseBudget}</span>
                <span className="text-xs text-foreground dark:text-slate-200">€{payload.base_amount || 100.0}</span>
              </div>
              {payload.setup_type === "trade" ? (
                <>
                  <div className="flex flex-col border-t border-slate-100 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.entryTarget}</span>
                    <span className="text-xs text-foreground dark:text-slate-200">€{payload.entry}</span>
                  </div>
                  <div className="flex flex-col border-t border-slate-100 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.stopLoss}</span>
                    <span className="text-xs text-rose-500">€{payload.stop_loss}</span>
                  </div>
                  <div className="flex flex-col col-span-2 border-t border-slate-100 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.takeProfitTargets}</span>
                    <span className="text-xs text-emerald-500 font-mono">
                      {Array.isArray(payload.targets) ? payload.targets.map(t => `€${t}`).join(" · ") : `€${payload.targets}`}
                    </span>
                  </div>
                </>
              ) : (
                <div className="flex flex-col col-span-2 border-t border-slate-100 dark:border-slate-800 pt-2">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.dcaMultiplierMode}</span>
                  <span className="text-xs text-foreground dark:text-slate-200 uppercase font-mono">{payload.execution_mode || "fixed"}</span>
                </div>
              )}
            </div>
          )}

          {baseType === "bot" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.safetyProfile}</span>
                <span className="text-xs text-foreground dark:text-slate-200 capitalize">{payload.risk_profile || "balanced"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.budget}</span>
                <span className="text-xs text-foreground dark:text-slate-200">€{payload.budget_total_eur || 500.0}</span>
              </div>
              <div className="flex flex-col border-t border-slate-100 dark:border-slate-800 pt-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.environment}</span>
                <span className="text-xs text-foreground dark:text-slate-200">
                  {payload.is_live ? uiText.liveReal : uiText.paperSandbox}
                </span>
              </div>
              <div className="flex flex-col border-t border-slate-100 dark:border-slate-800 pt-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.mode}</span>
                <span className="text-xs text-foreground dark:text-slate-200 capitalize">{payload.mode || "manual"}</span>
              </div>
            </div>
          )}

          {baseType.includes("watchlist") && (
            <div className="text-[11px] font-bold text-slate-600 dark:text-slate-300 flex items-center gap-3">
              <Activity size={18} className="text-violet-500 animate-pulse" />
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.targetAsset}</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{payload.symbol}</span>
              </div>
            </div>
          )}

          {!["setup", "strategy", "bot"].includes(baseType) && !baseType.includes("watchlist") && (
            <div className="text-xs text-slate-500 dark:text-slate-400 font-bold leading-relaxed">
              {payload.description || uiText.noDetailedParameters}
            </div>
          )}
        </div>

        {/* INLINE ERROR DISPLAY */}
        {status === "error" && (
          <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-[10px] text-rose-500 font-black tracking-wide leading-snug animate-in fade-in slide-in-from-top-1 duration-200">
            ⚠ {errorMessage}
          </div>
        )}

        {/* CONTROL BUTTONS WITH OPTIMISTIC LOADING */}
        <div className="grid grid-cols-3 gap-2">
          <button
            onClick={handleApprove}
            disabled={status === "executing"}
            className={`py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider text-white transition-all shadow-md flex items-center justify-center gap-1.5 bg-gradient-to-r ${getAccentGradient()} hover:opacity-90 active:scale-95 disabled:opacity-50`}
          >
            {status === "executing" ? (
              <>
                <Loader2 size={12} className="animate-spin" />
                <span>{uiText.loadingShort}</span>
              </>
            ) : (
              uiText.approve
            )}
          </button>

          {isDraft && handleEditDraft ? (
            <button
              onClick={handleEditClick}
              disabled={status === "executing"}
              className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider border-2 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-950 transition-all hover:bg-slate-50 active:scale-95 disabled:opacity-50 flex items-center justify-center"
            >
              {uiText.edit}
            </button>
          ) : (
            <div className="col-span-1" /> // Placeholder to maintain exact symmetrical grid alignment
          )}

          <button
            onClick={handleCancelClick}
            disabled={status === "executing"}
            className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider border-2 border-slate-200 dark:border-slate-700 hover:border-red-500 hover:text-red-500 dark:hover:border-red-500/30 text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-950 transition-all hover:bg-slate-50 active:scale-95 disabled:opacity-50 flex items-center justify-center"
          >
            {uiText.cancel}
          </button>
        </div>
      </div>
    </div>
  );
}

function ActionCard({ action, onAction }) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const assistantCopy = t?.assistant || {};
  const at = (path, fallback = "", vars = {}) => interpolateTranslation(getDictionaryValue(assistantCopy, path) ?? fallback, vars);
  const uiText = {
    actionCheck: at("uiText.actionCheck"),
    actionCheckBody: at("uiText.actionCheckBody"),
  };
  
  // State for bundle execution
  const [steps, setSteps] = useState([]);
  const [bundleStatus, setBundleStatus] = useState("idle"); // idle, running, success, failed

  useEffect(() => {
    if (action?.type === "bundle" && action?.actions) {
      setSteps(
        action.actions.map((act, index) => ({
          ...act,
          id: index,
          status: "pending", // pending, processing, success, failed
        }))
      );
    }
  }, [action]);

  const handleSingleClick = async () => {
    setLoading(true);
    try {
      await onAction(action);
      setSuccess(true);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleBundleClick = async () => {
    setBundleStatus("running");
    
    let hasError = false;
    const updatedSteps = [...steps];

    for (let i = 0; i < updatedSteps.length; i++) {
      // Update state to processing for the current step
      updatedSteps[i] = { ...updatedSteps[i], status: "processing" };
      setSteps([...updatedSteps]);

      try {
        // Execute the action via the callback
        await onAction(updatedSteps[i]);
        
        // Mark as success
        updatedSteps[i] = { ...updatedSteps[i], status: "success" };
        setSteps([...updatedSteps]);
      } catch (err) {
        console.error(`Step ${i} failed:`, err);
        updatedSteps[i] = { ...updatedSteps[i], status: "failed" };
        setSteps([...updatedSteps]);
        hasError = true;
        break; // Stop sequential execution upon error
      }
      
      // Short delay for visual polish & sequential feel
      await new Promise(resolve => setTimeout(resolve, 600));
    }

    if (hasError) {
      setBundleStatus("failed");
    } else {
      setBundleStatus("success");
    }
  };

  const getActionLabel = (act = action) => {
    switch (act.type) {
      case "add_to_watchlist": return at("actionLabels.add_to_watchlist", "", { symbol: act.symbol || "" });
      case "remove_from_watchlist": return at("actionLabels.remove_from_watchlist", "", { symbol: act.symbol || "" });
      case "open_setup_page": return at("actionLabels.open_setup_page", "", { symbol: act.symbol || "" });
      case "generate_strategy": return at("actionLabels.generate_strategy", "", { symbol: act.symbol || "" });
      case "open_bot_draft": return at("actionLabels.open_bot_draft", "", { symbol: act.symbol || "" });
      case "navigate_to_page": return at("actionLabels.navigate_to_page", "", { label: act.params?.label || at("actionLabels.page") });
      default: return at("actionLabels.default");
    }
  };

  const getActionDescription = (act = action) => {
    switch (act.type) {
      case "add_to_watchlist": return at("actionDescriptions.add_to_watchlist", "", { symbol: act.symbol || "" });
      case "remove_from_watchlist": return at("actionDescriptions.remove_from_watchlist", "", { symbol: act.symbol || "" });
      case "open_setup_page": return at("actionDescriptions.open_setup_page", "", { symbol: act.symbol || "" });
      case "generate_strategy": return at("actionDescriptions.generate_strategy", "", { symbol: act.symbol || "" });
      case "open_bot_draft": return at("actionDescriptions.open_bot_draft");
      case "navigate_to_page": return at("actionDescriptions.navigate_to_page", "", { label: act.params?.label || at("actionLabels.page") });
      default: return "";
    }
  };

  // --- RENDERING MULTI-ACTION BUNDLE ---
  if (action?.type === "bundle") {
    return (
      <div className="mt-3 p-5 bg-gradient-to-br from-blue-600/5 to-indigo-600/5 dark:from-blue-950/10 dark:to-indigo-950/10 border-2 border-blue-200/50 dark:border-blue-900/40 rounded-2xl flex flex-col gap-4 shadow-xl shadow-blue-500/5">
        <div className="flex items-center justify-between border-b border-blue-100/30 dark:border-blue-900/20 pb-2.5">
          <div>
            <h4 className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-600 dark:text-blue-400 flex items-center gap-2">
              <span className="flex h-2 w-2 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
              </span>
              {uiText.actionCheck}
            </h4>
            <p className="text-[11px] text-slate-500 dark:text-slate-400 font-bold mt-1">
              {uiText.actionCheckBody}
            </p>
          </div>
        </div>

        {/* Action Steps List */}
        <div className="space-y-3">
          {steps.map((step, idx) => (
            <div 
              key={step.id} 
              className={`flex items-start gap-3 p-3 rounded-xl border transition-all ${
                step.status === "processing" 
                  ? "bg-blue-50/50 dark:bg-blue-950/30 border-blue-300 dark:border-blue-800 shadow-sm"
                  : step.status === "success"
                    ? "bg-emerald-50/20 dark:bg-emerald-950/10 border-emerald-500/30 dark:border-emerald-500/20"
                    : step.status === "failed"
                      ? "bg-rose-50/20 dark:bg-rose-950/10 border-rose-500/30 dark:border-rose-500/20"
                      : "bg-white/50 dark:bg-slate-900/40 border-slate-100 dark:border-slate-800"
              }`}
            >
              {/* Step Number / Status Indicator */}
              <div className="flex-shrink-0 mt-0.5">
                {step.status === "pending" && (
                  <div className="w-5 h-5 rounded-full border-2 border-slate-200 dark:border-slate-700 flex items-center justify-center text-[9px] font-black text-slate-400 dark:text-slate-500">
                    {idx + 1}
                  </div>
                )}
                {step.status === "processing" && (
                  <div className="w-5 h-5 flex items-center justify-center text-blue-500">
                    <Loader2 size={16} className="animate-spin" />
                  </div>
                )}
                {step.status === "success" && (
                  <div className="w-5 h-5 rounded-full bg-emerald-500 dark:bg-emerald-600 flex items-center justify-center text-white text-[10px] font-black transition-all duration-300 scale-100">
                    ✓
                  </div>
                )}
                {step.status === "failed" && (
                  <div className="w-5 h-5 rounded-full bg-rose-500 dark:bg-rose-600 flex items-center justify-center text-white text-[10px] font-black">
                    !
                  </div>
                )}
              </div>

              {/* Step Info */}
              <div className="flex-1">
                <span className="text-xs font-black text-foreground dark:text-slate-200 block leading-tight">
                  {step.description || getActionLabel(step)}
                </span>
                <span className="text-[10px] text-slate-400 dark:text-slate-500 font-medium block mt-0.5">
                  {getActionDescription(step)}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Execution Trigger */}
        <button 
          onClick={handleBundleClick}
          disabled={bundleStatus === "running" || bundleStatus === "success"}
          className={`w-full py-3 rounded-xl text-[10px] font-black uppercase tracking-widest text-white transition-all shadow-lg active:scale-95 ${
            bundleStatus === "success" 
              ? "bg-emerald-600 shadow-emerald-600/15 cursor-default" 
              : bundleStatus === "failed"
                ? "bg-rose-600 shadow-rose-600/15"
                : "bg-blue-600 hover:bg-blue-700 shadow-blue-600/15"
          }`}
        >
          {bundleStatus === "running" 
            ? "Acties worden verwerkt..." 
            : bundleStatus === "success" 
              ? "✓ Acties opgeslagen" 
              : bundleStatus === "failed"
                ? "Probeer opnieuw"
                : `Bevestig acties (${steps.length})`}
        </button>
      </div>
    );
  }

  // --- RENDERING SINGLE ACTION ---
  return (
    <div className="mt-3 p-4 bg-blue-100/10 dark:bg-blue-950/20 border border-blue-200/50 dark:border-blue-900/40 rounded-2xl flex flex-col gap-3">
      <div>
        <h4 className="text-[10px] font-black uppercase tracking-[0.15em] text-blue-600 dark:text-blue-400">{uiText.proposedAction}</h4>
        <p className="text-[11px] text-slate-500 dark:text-slate-400 font-medium mt-1 leading-snug">{getActionDescription()}</p>
      </div>
      
      <button 
        onClick={handleSingleClick}
        disabled={loading || success}
        className={`w-full py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest text-white transition-all shadow-md active:scale-95 ${
          success 
            ? "bg-emerald-600 shadow-emerald-600/15 cursor-default" 
            : "bg-blue-600 hover:bg-blue-700 shadow-blue-600/15"
        }`}
      >
        {loading ? "Processing..." : success ? "✓ Executed Successfully" : getActionLabel()}
      </button>
    </div>
  );
}

function DraftCard({ draft, onCancel, onSuccess, handleEditDraft }) {
  const { openConfirm, showSnackbar } = useModal();
  const { t } = useTranslation();
  const at = createAssistantTranslator(t);
  const uiText = buildAssistantUiText(at);
  const [approving, setApproving] = useState(false);
  const payload = draft?.payload && typeof draft.payload === "object" ? draft.payload : {};

  const handleApprove = async () => {
    setApproving(true);
    try {
      if (draft.type === "setup") {
        await saveNewSetup(payload);
        showSnackbar(uiText.draftSetupApproved, "success");
        onSuccess();
      } else if (draft.type === "strategy") {
        const setups = await fetchSetups();
        const matching = setups.filter(s => s.symbol?.toUpperCase() === payload.symbol?.toUpperCase());
        if (matching.length === 0) {
          showSnackbar(uiText.missingSetupForStrategy.replace("{symbol}", payload.symbol || ""), "danger");
          setApproving(false);
          return;
        }
        const payload = {
          ...draft.payload,
          setup_id: matching[0].id
        };
        await createStrategy(payload);
        showSnackbar(uiText.draftStrategyApproved, "success");
        onSuccess();
      } else if (draft.type === "bot") {
        const strategies = await fetchStrategies();
        const matching = strategies.filter(s => s.symbol?.toUpperCase() === payload.name?.split(' ')[0]?.toUpperCase() || s.name?.toLowerCase().includes(payload.name?.toLowerCase()));
        let stratId = matching[0]?.id;
        if (!stratId && strategies.length > 0) {
          stratId = strategies[0].id;
        }
        if (!stratId) {
          showSnackbar(uiText.missingStrategyForBot, "danger");
          setApproving(false);
          return;
        }
        const payload = {
          ...draft.payload,
          strategy_id: stratId
        };
        await createBotConfig(payload);
        showSnackbar(uiText.draftBotApproved, "success");
        onSuccess();
      }
    } catch (err) {
      console.error(err);
      showSnackbar(uiText.draftApproveError.replace("{type}", draft.type), "danger");
    } finally {
      setApproving(false);
    }
  };

  const handleEditClick = () => {
    handleEditDraft(draft, onSuccess);
  };

  const getAccentGradient = () => {
    if (draft.type === "setup") return "from-amber-500 to-yellow-400";
    if (draft.type === "strategy") return "from-blue-500 to-indigo-500";
    return "from-emerald-500 to-teal-500";
  };

  return (
    <div className="mt-4 overflow-hidden rounded-2xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/60 shadow-xl shadow-slate-100/10 dark:shadow-none animate-in fade-in duration-300">
      {/* CARD HEADER */}
      <div className={`h-1.5 w-full bg-gradient-to-r ${getAccentGradient()}`} />
      
      <div className="p-4 space-y-4">
        {/* TITLE & BADGE */}
        <div className="flex items-start justify-between">
          <div className="space-y-0.5">
            <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
              {uiText.conceptReview}
            </span>
            <h4 className="text-xs font-black text-foreground dark:text-slate-200 tracking-tight leading-snug">
              {payload.name || uiText.newConcept}
            </h4>
          </div>
          <span className={`text-[8px] font-black uppercase tracking-wider px-2 py-0.5 rounded-md shadow-sm text-white bg-gradient-to-r ${getAccentGradient()}`}>
            {draft.type}
          </span>
        </div>

        {/* METADATA RENDER */}
        <div className="rounded-xl bg-white dark:bg-slate-950 p-3.5 border border-slate-100 dark:border-slate-800/80 space-y-2.5 shadow-sm">
          {draft.type === "setup" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col col-span-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.name || "Naam"}</span>
                <span className="text-xs text-foreground dark:text-slate-200">{payload.name || "—"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.asset}</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{payload.symbol || globalSymbol || context.symbol || "—"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.setupType}</span>
                <span className="uppercase text-xs text-foreground dark:text-slate-200">{payload.setup_type || "dca"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.timeframe || "Timeframe"}</span>
                <span className="text-xs text-foreground dark:text-slate-200">{payload.timeframe || uiText.required}</span>
              </div>
              {(payload.market_condition || payload.min_macro_score !== undefined) && (
                <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800 pt-2">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.marketCondition}</span>
                  <span className="text-xs text-foreground dark:text-slate-200">
                    {getSetupMarketConditionLabel(payload.market_condition || inferSetupMarketConditionFromScores(payload), uiText)}
                  </span>
                </div>
              )}
              {payload.setup_type === "dca" && (
                <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800 pt-2">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.dcaParameters}</span>
                  <span className="text-xs text-foreground dark:text-slate-200">
                    {[payload.dca_frequency, payload.dca_day ? `op ${payload.dca_day}` : null].filter(Boolean).join(" ") || uiText.required}
                  </span>
                </div>
              )}
              {!(payload.market_condition || inferSetupMarketConditionFromScores(payload)) && (
                <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800 pt-2 space-y-1">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">{uiText.scoreThresholds}</span>
                  <div className="grid grid-cols-3 gap-2 mt-1">
                    <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-1.5 text-center">
                      <div className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-500">Macro</div>
                      <div className="text-[10px] font-mono font-black text-blue-500">{payload.min_macro_score ?? 30}-{payload.max_macro_score ?? 70}</div>
                    </div>
                    <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-1.5 text-center">
                      <div className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-500">Tech</div>
                      <div className="text-[10px] font-mono font-black text-amber-500">{payload.min_technical_score ?? 40}-{payload.max_technical_score ?? 80}</div>
                    </div>
                    <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-1.5 text-center">
                      <div className="text-[7px] font-black uppercase text-slate-400 dark:text-slate-500">Market</div>
                      <div className="text-[10px] font-mono font-black text-emerald-500">{payload.min_market_score ?? 20}-{payload.max_market_score ?? 60}</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {draft.type === "strategy" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.asset}</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{payload.symbol || globalSymbol || context.symbol || "—"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.baseBudget}</span>
                <span className="text-xs text-foreground dark:text-slate-200">€{payload.base_amount || 100.0}</span>
              </div>
              {payload.setup_type === "trade" ? (
                <>
                  <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.entryTarget}</span>
                    <span className="text-xs text-foreground dark:text-slate-200">€{payload.entry}</span>
                  </div>
                  <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.stopLoss}</span>
                    <span className="text-xs text-rose-500">€{payload.stop_loss}</span>
                  </div>
                  <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.takeProfitTargets}</span>
                    <span className="text-xs text-emerald-500 font-mono">
                      {Array.isArray(payload.targets) ? payload.targets.map(t => `€${t}`).join(" · ") : `€${payload.targets}`}
                    </span>
                  </div>
                </>
              ) : (
                <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800 pt-2">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.dcaMultiplierMode}</span>
                  <span className="text-xs text-foreground dark:text-slate-200 uppercase font-mono">{payload.execution_mode || "fixed"}</span>
                </div>
              )}
            </div>
          )}

          {draft.type === "bot" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.safetyProfile}</span>
                <span className="text-xs text-foreground dark:text-slate-200 capitalize">{payload.risk_profile || "balanced"}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.budget}</span>
                <span className="text-xs text-foreground dark:text-slate-200">€{payload.budget_total_eur || 500.0}</span>
              </div>
              <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.environment}</span>
                <span className="text-xs text-foreground dark:text-slate-200">
                  {payload.is_live ? uiText.liveReal : uiText.paperSandbox}
                </span>
              </div>
              <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.mode}</span>
                <span className="text-xs text-foreground dark:text-slate-200 capitalize">{payload.mode || "manual"}</span>
              </div>
            </div>
          )}
        </div>

        {/* BUTTON CONTROLS */}
        <div className="grid grid-cols-3 gap-2">
          <button
            onClick={handleApprove}
            disabled={approving}
            className={`py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider text-white transition-all shadow-md flex items-center justify-center gap-1 bg-gradient-to-r ${getAccentGradient()} hover:opacity-90 active:scale-95`}
          >
            {approving ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              uiText.approve
            )}
          </button>
          
          <button
            onClick={handleEditClick}
            disabled={approving}
            className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider border-2 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-950 transition-all hover:bg-slate-50 active:scale-95 flex items-center justify-center"
          >
            {uiText.edit}
          </button>

          <button
            onClick={onCancel}
            disabled={approving}
            className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider border-2 border-slate-200 dark:border-slate-700 hover:border-red-500 hover:text-red-500 dark:hover:border-red-500/30 text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-950 transition-all hover:bg-slate-50 active:scale-95 flex items-center justify-center"
          >
            {uiText.cancel}
          </button>
        </div>
      </div>
    </div>
  );
}

function ConceptCard({ state, onCancel, onEdit, onFinalize, onUpdateSlots }) {
  const { t } = useTranslation();
  const at = createAssistantTranslator(t);
  const uiText = buildAssistantUiText(at);
  const { current_flow, slots } = state;
  const flowType = current_flow?.split("_")?.[0] || "setup"; // setup, strategy, bot

  const getAccentGradient = () => {
    if (flowType === "setup") return "from-amber-500 to-yellow-400";
    if (flowType === "strategy") return "from-blue-500 to-indigo-500";
    return "from-emerald-500 to-teal-500";
  };

  return (
    <div className="mt-4 overflow-hidden rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-800 bg-slate-50/30 dark:bg-slate-900/40 shadow-md animate-in fade-in duration-300">
      <div className="p-4 space-y-4">
        {/* TITLE & BADGE */}
        <div className="flex items-start justify-between">
          <div className="space-y-0.5">
            <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              {uiText.activeConcept}
            </span>
            <h4 className="text-xs font-black text-foreground dark:text-slate-200 tracking-tight leading-snug">
              {flowType === "setup" ? `${slots?.symbol || "..."} ${uiText.setupConceptSuffix}` :
               flowType === "strategy" ? `${slots?.symbol || "..."} ${uiText.strategyConceptSuffix}` :
               `${slots?.name || "..."} ${uiText.botConceptSuffix}`}
            </h4>
          </div>
          <span className={`text-[8px] font-black uppercase tracking-wider px-2 py-0.5 rounded-md shadow-sm text-white bg-gradient-to-r ${getAccentGradient()}`}>
            {flowType} {uiText.conceptSuffix}
          </span>
        </div>

        {/* METADATA RENDER WITH PLACEHOLDERS */}
        <div className="rounded-xl bg-white dark:bg-slate-950 p-3.5 border border-slate-100 dark:border-slate-800/80 space-y-2.5 shadow-sm">
          {flowType === "setup" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-3.5 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col col-span-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.name}</span>
                <span className="text-xs text-foreground dark:text-slate-200">
                  {slots?.name || <span className="text-slate-400 italic font-normal">{uiText.required}</span>}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.asset}</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{slots?.symbol || <span className="text-slate-400 italic font-normal">{uiText.required}</span>}</span>
              </div>
              
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1">{uiText.setupType}</span>
                <div className="flex gap-1.5">
                  {['dca', 'trade'].map((type) => (
                    <button
                      key={type}
                      onClick={() => onUpdateSlots && onUpdateSlots({ setup_type: type })}
                      className={`px-2.5 py-0.5 rounded-lg text-[9px] font-black uppercase tracking-wider transition-all duration-150 active:scale-95 ${
                        slots?.setup_type === type
                          ? 'bg-amber-500 text-white shadow-sm'
                          : 'bg-slate-100 dark:bg-slate-900 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-800'
                      }`}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800/80 pt-2.5">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.timeframe || "Timeframe"}</span>
                <span className="text-xs text-foreground dark:text-slate-200">
                  {slots?.timeframe || <span className="text-slate-400 italic font-normal">{uiText.required}</span>}
                </span>
              </div>

              {slots?.setup_type === "dca" && (
                <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800/80 pt-2.5">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1.5">{uiText.dcaFrequency}</span>
                  <div className="flex gap-1.5">
                    {['daily', 'weekly', 'monthly'].map((freq) => (
                      <button
                        key={freq}
                        onClick={() => onUpdateSlots && onUpdateSlots({ dca_frequency: freq })}
                        className={`px-2.5 py-0.5 rounded-lg text-[9px] font-black uppercase tracking-wider transition-all duration-150 active:scale-95 ${
                          slots?.dca_frequency === freq
                            ? 'bg-amber-500 text-white shadow-sm'
                            : 'bg-slate-100 dark:bg-slate-900 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-800'
                        }`}
                      >
                        {freq === "daily" ? uiText.daily : freq === "weekly" ? uiText.weekly : uiText.monthly}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {(slots?.market_condition || slots?.min_macro_score !== undefined) && (
                <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800/80 pt-2.5">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.marketCondition}</span>
                  <span className="text-xs text-foreground dark:text-slate-200">
                    {getSetupMarketConditionLabel(slots?.market_condition, uiText)}
                  </span>
                </div>
              )}
            </div>
          )}

          {flowType === "strategy" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.asset}</span>
                <span className="font-mono text-xs text-foreground dark:text-slate-200">{slots?.symbol || <span className="text-slate-400 italic font-normal">{uiText.required}</span>}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.baseBudget}</span>
                <span className="text-xs text-foreground dark:text-slate-200">
                  {slots?.base_amount ? `€${slots.base_amount}` : <span className="text-slate-400 italic font-normal">{uiText.chooseAmount}</span>}
                </span>
              </div>
              {slots?.setup_type === "trade" ? (
                <>
                  <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.entryTarget}</span>
                    <span className="text-xs text-foreground dark:text-slate-200">
                      {slots?.entry ? `€${slots.entry}` : <span className="text-slate-400 italic font-normal">{uiText.optional}</span>}
                    </span>
                  </div>
                  <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.stopLoss}</span>
                    <span className="text-xs text-rose-500">
                      {slots?.stop_loss ? `€${slots.stop_loss}` : <span className="text-slate-400 italic font-normal">{uiText.optional}</span>}
                    </span>
                  </div>
                  <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800 pt-2">
                    <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.takeProfitTargets}</span>
                    <span className="text-xs text-emerald-500 font-mono">
                      {slots?.targets ? (Array.isArray(slots.targets) ? slots.targets.map(t => `€${t}`).join(" · ") : `€${slots.targets}`) : <span className="text-slate-400 italic font-normal">{uiText.optional}</span>}
                    </span>
                  </div>
                </>
              ) : (
                <div className="flex flex-col col-span-2 border-t border-slate-50 dark:border-slate-800 pt-2">
                  <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.dcaMultiplierMode}</span>
                    <span className="text-xs text-foreground dark:text-slate-200 uppercase font-mono">{slots?.execution_mode || <span className="text-slate-400 italic font-normal">{uiText.optional}</span>}</span>
                </div>
              )}
            </div>
          )}

          {flowType === "bot" && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] font-bold text-slate-600 dark:text-slate-300">
              <div className="flex flex-col col-span-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.botName}</span>
                <span className="text-xs text-foreground dark:text-slate-200">{slots?.name || uiText.defaultBotName}</span>
              </div>
              <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.safetyProfile}</span>
                <span className="text-xs text-foreground dark:text-slate-200 capitalize">{slots?.risk_profile || <span className="text-slate-400 italic font-normal">{uiText.required}</span>}</span>
              </div>
              <div className="flex flex-col border-t border-slate-50 dark:border-slate-800 pt-2">
                <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-0.5">{uiText.budget}</span>
                <span className="text-xs text-foreground dark:text-slate-200">
                  {slots?.budget_total_eur ? `€${slots.budget_total_eur}` : <span className="text-slate-400 italic font-normal">{uiText.required}</span>}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* CONTROLS */}
        <div className="grid grid-cols-3 gap-2">
          <button
            onClick={onCancel}
            className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider border-2 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-950 transition-all hover:bg-slate-50 active:scale-95 flex items-center justify-center"
          >
            {uiText.cancel}
          </button>
          
          <button
            onClick={onEdit}
            className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider border-2 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-950 transition-all hover:bg-slate-50 active:scale-95 flex items-center justify-center"
          >
            {uiText.edit}
          </button>

          <button
            onClick={onFinalize}
            className="py-2 px-3 rounded-xl text-[10px] font-black uppercase tracking-wider text-white transition-all shadow-md flex items-center justify-center bg-emerald-600 hover:bg-emerald-700 active:scale-95"
          >
            {uiText.approve}
          </button>
        </div>
      </div>
    </div>
  );
}

function ReasoningWidget({ reasoning }) {
  const pathname = usePathname();
  if (!reasoning) return null;

  const isAdminMode = pathname?.includes("/admin");

  if (isAdminMode) {
    return <DebugExplainabilityCard reasoning={reasoning} />;
  }

  // Hide completely for standard users
  return null;
}

function DebugExplainabilityCard({ reasoning }) {
  const { t } = useTranslation();
  const at = createAssistantTranslator(t);
  const uiText = buildAssistantUiText(at);
  const [isOpen, setIsOpen] = useState(false);
  if (!reasoning) return null;

  const { confidence_score, risk_detected, reasons, coaching_level } = reasoning;

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 shadow-sm">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-3 py-2 flex items-center justify-between text-left text-[10px] font-black uppercase tracking-wider text-rose-500 dark:text-rose-400 hover:bg-slate-100 dark:hover:bg-slate-800/60 transition-colors"
      >
        <span className="flex items-center gap-1.5 font-mono">
          <Brain size={12} className="text-rose-500" />
          {uiText.debugReasoning}
        </span>
        <ChevronDown size={12} className={`transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {isOpen && (
        <div className="p-3 border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 space-y-2.5 font-mono text-[10px]">
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-2 text-center border border-slate-100 dark:border-slate-800">
              <span className="text-[7px] font-black uppercase tracking-wider text-slate-400 block">{uiText.confidence}</span>
              <span className="text-[11px] font-black text-blue-500">{confidence_score ? `${confidence_score}%` : uiText.notAvailable}</span>
            </div>
            
            <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-2 text-center border border-slate-100 dark:border-slate-800">
              <span className="text-[7px] font-black uppercase tracking-wider text-slate-400 block">{uiText.risk}</span>
              <span className={`text-[10px] font-black ${risk_detected ? 'text-rose-500 animate-pulse' : 'text-emerald-500'}`}>
                {risk_detected ? uiText.detected : uiText.safe}
              </span>
            </div>
            
            <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-2 text-center border border-slate-100 dark:border-slate-800">
              <span className="text-[7px] font-black uppercase tracking-wider text-slate-400 block">{uiText.coaching}</span>
              <span className="text-[10px] font-black text-amber-500 uppercase">{coaching_level || uiText.general}</span>
            </div>
          </div>

          {reasons && reasons.length > 0 && (
            <div className="space-y-1">
              <span className="text-[8px] font-black uppercase tracking-widest text-slate-400 block">{uiText.reasoningChains}:</span>
              <ul className="space-y-1 pl-2">
                {reasons.map((reason, idx) => (
                  <li key={idx} className="text-[10px] text-slate-600 dark:text-slate-300 flex items-start gap-1.5">
                    <span className="text-blue-500 mt-0.5">•</span>
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
