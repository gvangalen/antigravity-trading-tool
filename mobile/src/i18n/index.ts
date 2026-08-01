import type { AppLanguage } from '../preferences/AppPreferencesProvider';

type TranslationParams = Record<string, number | string>;
type TranslationValue = string | ((params: TranslationParams) => string);

const enMessages = {
    'common.itemsOpen': ({ count }: TranslationParams) => `${count} items open`,
    'common.confidence': ({ count }: TranslationParams) => `${count}% confidence`,
    'common.sections': ({ count }: TranslationParams) => `${count} sections`,
    'workspace.activeWorkspace': 'Active workspace',
    'workspace.analysis': 'Analysis',
    'workspace.automation': 'Automation',
    'workspace.myPlan': 'My Plan',
    'workspace.portfolio': 'Portfolio',
    'workspace.reflection': 'Reflection',
    'workspace.settings': 'Settings',
    'workspace.analysisDescription': 'Market, macro and technical context',
    'workspace.automationDescription': 'Bots, guardrails and execution review',
    'workspace.myPlanDescription': 'Setups, strategy and decision prep',
    'workspace.portfolioDescription': 'Exposure, balances and system state',
    'workspace.reflectionDescription': 'Reports, review and performance context',
    'workspace.settingsDescription': 'Profile and session controls',
    'login.mobile': 'Tradamind Mobile',
    'login.syncing': 'Syncing',
    'login.apiLive': 'API live',
    'login.apiOffline': 'API offline',
    'login.title': 'Welcome back to FINN.',
    'login.subtitle': 'Log in to load your assistant, watchlist, setups, portfolio and reports with live backend data.',
    'login.email': 'Email',
    'login.password': 'Password',
    'login.passwordPlaceholder': 'Password',
    'login.showPassword': 'Show',
    'login.hidePassword': 'Hide',
    'login.logIn': 'Log in',
    'login.retryLogin': 'Retry login',
    'login.bearerAuth': 'Bearer auth',
    'login.secureTokenStorage': 'Secure token storage',
    'login.autoRefresh': 'Auto refresh',
    'finn.askAboutExposure': 'Ask FINN about exposure',
    'finn.askAboutThisReport': 'Ask FINN about this report',
    'finn.greetingEvening': 'Good evening.',
    'finn.greetingEveningName': ({ name }: TranslationParams) => `Good evening ${name}.`,
    'finn.greetingEveningTrader': 'Good evening trader.',
    'finn.noBriefingReady': 'FINN has no briefing ready yet.',
    'finn.noImmediateItems': 'No immediate items need attention.',
    'finn.openAutomationReview': 'Open automation review',
    'finn.openMyPlan': 'Open My Plan',
    'finn.queueSubtitle': 'What needs your attention now.',
    'finn.queueTitle': 'Work queue',
    'finn.refreshDailyScores': 'Refresh daily scores',
    'finn.reviewNeedsAttention': '1 review needs attention.',
    'finn.reviewsNeedAttention': ({ count }: TranslationParams) => `${count} reviews need attention.`,
    'finn.todayEyebrow': 'Today with FINN',
    'analysis.summaryUnavailable': ({ symbol }: TranslationParams) => `${symbol} is live, but FINN has not returned an analysis briefing yet.`,
    'analysis.evidenceUnavailableHeadline': 'Evidence sections are not available yet.',
    'analysis.evidenceUnavailableBody': 'The backend has not returned market, macro and technical workspace rows yet.',
    'analysis.forwardReturnsUnavailableHeadline': 'Forward returns are not available yet.',
    'analysis.forwardReturnsUnavailableBody': 'The backend has not returned historical forward-return data for this asset yet.',
    'report.unavailableHeadline': 'No report data available yet.',
    'report.unavailableBody': 'The backend has not returned a usable report yet. Refresh later or ask FINN to explain the current workspace context.',
    'report.risksNeedAttention': ({ count }: TranslationParams) => `${count} risk${count === 1 ? '' : 's'} need attention before acting on this reflection.`,
    'report.period.daily': 'Daily report',
    'report.period.weekly': 'Weekly report',
    'report.period.monthly': 'Monthly report',
    'report.period.quarterly': 'Quarterly report',
    'myPlan.workflowEyebrow': 'Plan workspace',
    'myPlan.workflowTitle': 'When do you trade and how?',
    'myPlan.workflowSubtitle': 'Connect market conditions to clear execution rules.',
    'myPlan.workflowStepSetup': 'When am I allowed to trade?',
    'myPlan.workflowStepStrategy': 'How do I execute the trade?',
    'myPlan.workflowStepPlan': 'What is ready for automation?',
    'myPlan.planCheckEyebrow': 'FINN plan check',
    'myPlan.planCheckReady': ({ name }: TranslationParams) => `${name} ready for automation.`,
    'automation.workspaceEyebrow': 'Automation workspace',
    'automation.workspaceTitle': 'Automation',
    'automation.workspaceSubtitle': 'Manage execution and monitor every bot within your risk limits.',
    'automation.stepPlanTitle': 'Plan',
    'automation.stepPlanBody': 'Which rules apply?',
    'automation.stepExecutionTitle': 'Execution',
    'automation.stepExecutionBody': 'What does Automation execute?',
    'automation.stepMonitoringTitle': 'Monitoring',
    'automation.stepMonitoringBody': 'Does everything remain within my risk?',
    'automation.budgetRequired': 'Budget required',
    'automation.directlyVisible': 'Directly visible',
    'automation.lastChecked': 'Last checked',
    'automation.marketAction': 'Market action',
    'automation.nextStepAddBudget': 'Next step: add budget and limits before relying on this bot for execution.',
    'automation.paperTracking': 'Paper tracking',
    'automation.paused': 'Paused',
    'automation.review': 'Review',
    'automation.statusReaction': 'Status reaction',
    'automation.trade': 'Trade',
    'automation.active': 'Active',
    'automation.hold': 'Hold',
    'automation.liveCapital': 'Live capital',
    'automation.viewFullDiagnostics': 'View full diagnostics',
    'automation.waiting': 'Waiting',
    'automation.why': 'Why',
    'automation.noBudgetSupport': 'No budget is set yet, so FINN cannot size or execute trades from this chain.',
    'automation.pausedLiveSupport': ({ pausedCount, liveCount }: TranslationParams) => `${pausedCount} bots are paused. ${liveCount} live bots remain connected for review.`,
    'automation.noBudgetWhy': 'This bot has no budget yet, so FINN cannot size or execute trades from this chain.',
    'portfolio.activeSources': ({ count }: TranslationParams) => `${count} active sources`,
    'portfolio.staleSupport': 'Some portfolio feeds are stale right now. Review capital, balances and bot exposure before acting.',
    'portfolio.metricSupport': ({ metric }: TranslationParams) => `Use this page to verify capital availability, current ${metric} drift and whether live or paper execution still matches desktop.`,
    'queue.body.botsCurrentlyEnabled': 'Bots currently enabled.',
    'queue.body.botsInCurrentPortfolioLens': 'Bots in current portfolio lens.',
    'queue.body.botsPausedOrBlocked': 'Bots still paused or blocked.',
    'queue.body.botsUsingLiveCapital': 'Bots using live capital.',
    'queue.body.botsWaitingReview': 'Bots waiting for review.',
    'queue.body.estimatedTimeToFinish': 'Estimated time to finish the report.',
    'queue.body.executionFlowNeedsReview': 'Execution flow still needs review.',
    'queue.body.fullReportBlocks': 'Full report blocks ready to scan.',
    'queue.body.handleFirst': 'Handle first.',
    'queue.body.howTodayBehaves': 'How today behaves.',
    'queue.body.needDecision': 'Need decision.',
    'queue.body.plansAlreadyReady': 'Plans already ready for execution.',
    'queue.body.plansInCurrentWorkspace': 'Plans in current workspace.',
    'queue.body.plansNeedReview': 'Plans that still need review.',
    'queue.body.slowingYouDown': 'Slowing you down.',
    'queue.body.staleSyncMissingBackendContext': 'Stale sync or missing backend context.',
    'queue.body.topItemsSurfaced': 'Top items FINN surfaced first.',
    'queue.body.visiblePerformanceMatchesMetric': 'Visible performance matches active metric.',
    'queue.body.warningsAndFlags': 'Warnings and caution flags in this report.',
    'queue.body.weakPlansSlowing': 'Weak plans FINN is slowing down.',
    'queue.label.bots': 'Bots',
    'queue.label.highlights': 'Highlights',
    'queue.label.live': 'Live',
    'queue.label.paused': 'Paused',
    'queue.label.performance': 'Performance',
    'queue.label.reading': 'Reading',
    'queue.label.reviews': 'Reviews',
    'queue.label.risks': 'Risks',
    'queue.label.sections': 'Sections',
    'queue.label.tasks': 'Tasks',
    'tag.actionNeeded': 'Action needed',
    'tag.activeBot': 'Active bot',
    'tag.constructive': 'Constructive',
    'tag.defensive': 'Defensive',
    'tag.live': 'Live',
    'tag.liveContext': 'Live context',
    'tag.monitor': 'Monitor',
    'tag.monitoring': 'Monitoring',
    'tag.nearTrigger': 'Near trigger',
    'tag.neutral': 'Neutral',
    'tag.review': 'Review',
    'tag.selective': 'Selective',
    'tag.lowStable': 'Low / stable',
    'tag.paper': 'Paper',
    'tag.pausedBot': 'Paused bot',
    'tag.planReview': 'Plan review',
    'tag.staleSync': 'Stale sync',
    'tag.waitingConfirmation': 'Waiting confirmation',
    'tag.weakStructure': 'Weak structure',
  };

const nlMessages = {
    'common.itemsOpen': ({ count }: TranslationParams) => `${count} open`,
    'common.confidence': ({ count }: TranslationParams) => `${count}% confidence`,
    'common.sections': ({ count }: TranslationParams) => `${count} secties`,
    'workspace.activeWorkspace': 'Actieve workspace',
    'workspace.analysis': 'Analyse',
    'workspace.automation': 'Automatisering',
    'workspace.myPlan': 'Mijn plan',
    'workspace.portfolio': 'Portfolio',
    'workspace.reflection': 'Reflectie',
    'workspace.settings': 'Instellingen',
    'workspace.analysisDescription': 'Markt-, macro- en technische context',
    'workspace.automationDescription': 'Bots, guardrails en uitvoeringsreview',
    'workspace.myPlanDescription': 'Setups, strategie en beslisvoorbereiding',
    'workspace.portfolioDescription': 'Exposure, balansen en systeemstatus',
    'workspace.reflectionDescription': 'Rapporten, review en performancecontext',
    'workspace.settingsDescription': 'Profiel en sessiebeheer',
    'login.mobile': 'Tradamind Mobile',
    'login.syncing': 'Synchroniseren',
    'login.apiLive': 'API live',
    'login.apiOffline': 'API offline',
    'login.title': 'Welkom terug bij FINN.',
    'login.subtitle': 'Log in om je assistant, watchlist, setups, portfolio en rapporten met live backenddata te laden.',
    'login.email': 'E-mail',
    'login.password': 'Wachtwoord',
    'login.passwordPlaceholder': 'Wachtwoord',
    'login.showPassword': 'Toon',
    'login.hidePassword': 'Verberg',
    'login.logIn': 'Log in',
    'login.retryLogin': 'Probeer opnieuw',
    'login.bearerAuth': 'Bearer-auth',
    'login.secureTokenStorage': 'Veilige tokenopslag',
    'login.autoRefresh': 'Auto-refresh',
    'finn.askAboutExposure': 'Vraag FINN naar exposure',
    'finn.askAboutThisReport': 'Vraag FINN naar dit rapport',
    'finn.greetingEvening': 'Goedenavond.',
    'finn.greetingEveningName': ({ name }: TranslationParams) => `Goedenavond ${name}.`,
    'finn.greetingEveningTrader': 'Goedenavond handelaar.',
    'finn.noBriefingReady': 'FINN heeft nog geen briefing klaar.',
    'finn.noImmediateItems': 'Geen directe punten vragen aandacht.',
    'finn.openAutomationReview': 'Open automation review',
    'finn.openMyPlan': 'Open mijn plan',
    'finn.queueSubtitle': 'Wat heeft nu je aandacht nodig?',
    'finn.queueTitle': 'Werklijst',
    'finn.refreshDailyScores': 'Ververs dagelijkse scores',
    'finn.reviewNeedsAttention': '1 review vraagt aandacht.',
    'finn.reviewsNeedAttention': ({ count }: TranslationParams) => `${count} reviews vragen aandacht.`,
    'finn.todayEyebrow': 'Vandaag met FINN',
    'analysis.summaryUnavailable': ({ symbol }: TranslationParams) => `${symbol} is live, maar FINN heeft nog geen analyse-briefing teruggegeven.`,
    'analysis.evidenceUnavailableHeadline': 'Evidence-secties zijn nog niet beschikbaar.',
    'analysis.evidenceUnavailableBody': 'De backend heeft nog geen market-, macro- en technical-workspace-rijen teruggegeven.',
    'analysis.forwardReturnsUnavailableHeadline': 'Forward returns zijn nog niet beschikbaar.',
    'analysis.forwardReturnsUnavailableBody': 'De backend heeft nog geen historische forward-return-data voor deze asset teruggegeven.',
    'report.unavailableHeadline': 'Er is nog geen rapportdata beschikbaar.',
    'report.unavailableBody': 'De backend heeft nog geen bruikbaar rapport teruggegeven. Ververs later opnieuw of vraag FINN om de huidige workspace-context uit te leggen.',
    'report.risksNeedAttention': ({ count }: TranslationParams) => `${count} risico${count === 1 ? '' : "'s"} vragen aandacht voordat je op deze reflectie handelt.`,
    'report.period.daily': 'Dagrapport',
    'report.period.weekly': 'Weekrapport',
    'report.period.monthly': 'Maandrapport',
    'report.period.quarterly': 'Kwartaalrapport',
    'myPlan.workflowEyebrow': 'Plan-workspace',
    'myPlan.workflowTitle': 'Wanneer handel je en hoe?',
    'myPlan.workflowSubtitle': 'Koppel marktomstandigheden aan duidelijke uitvoeringsregels.',
    'myPlan.workflowStepSetup': 'Wanneer mag ik handelen?',
    'myPlan.workflowStepStrategy': 'Hoe voer ik de trade uit?',
    'myPlan.workflowStepPlan': 'Wat is klaar voor automatisering?',
    'myPlan.planCheckEyebrow': 'FINN plan check',
    'myPlan.planCheckReady': ({ name }: TranslationParams) => `${name} is klaar voor automatisering.`,
    'automation.workspaceEyebrow': 'Automation-workspace',
    'automation.workspaceTitle': 'Automatisering',
    'automation.workspaceSubtitle': 'Beheer uitvoering en monitor iedere bot binnen je risicolimieten.',
    'automation.stepPlanTitle': 'Plan',
    'automation.stepPlanBody': 'Welke regels gelden?',
    'automation.stepExecutionTitle': 'Uitvoering',
    'automation.stepExecutionBody': 'Wat voert automatisering uit?',
    'automation.stepMonitoringTitle': 'Monitoring',
    'automation.stepMonitoringBody': 'Blijft alles binnen mijn risico?',
    'automation.budgetRequired': 'Budget vereist',
    'automation.directlyVisible': 'Direct zichtbaar',
    'automation.lastChecked': 'Laatst gecontroleerd',
    'automation.marketAction': 'Marktactie',
    'automation.nextStepAddBudget': 'Volgende stap: voeg budget en limieten toe voordat je op deze bot vertrouwt voor uitvoering.',
    'automation.paperTracking': 'Paper-tracking',
    'automation.paused': 'Gepauzeerd',
    'automation.review': 'Review',
    'automation.statusReaction': 'Statusreactie',
    'automation.trade': 'Handel',
    'automation.active': 'Actief',
    'automation.hold': 'Vasthouden',
    'automation.liveCapital': 'Live kapitaal',
    'automation.viewFullDiagnostics': 'Volledige diagnostiek bekijken',
    'automation.waiting': 'Wachten',
    'automation.why': 'Waarom',
    'automation.noBudgetSupport': 'Er is nog geen budget ingesteld, dus FINN kan vanaf deze chain geen trades sizen of uitvoeren.',
    'automation.pausedLiveSupport': ({ pausedCount, liveCount }: TranslationParams) => `${pausedCount} bots staan gepauzeerd. ${liveCount} live bots blijven verbonden voor review.`,
    'automation.noBudgetWhy': 'Deze bot heeft nog geen budget, dus FINN kan vanaf deze chain geen trades sizen of uitvoeren.',
    'portfolio.activeSources': ({ count }: TranslationParams) => `${count} actieve bronnen`,
    'portfolio.staleSupport': 'Sommige portfoliofeeds zijn nu verouderd. Controleer kapitaal, balansen en bot-exposure voordat je handelt.',
    'portfolio.metricSupport': ({ metric }: TranslationParams) => `Gebruik deze pagina om kapitaalruimte, huidige ${metric}-afwijking en live/paper uitvoering te controleren.`,
    'queue.body.botsCurrentlyEnabled': 'Bots die nu actief zijn.',
    'queue.body.botsInCurrentPortfolioLens': 'Bots in deze portfolio-lens.',
    'queue.body.botsPausedOrBlocked': 'Bots die nog gepauzeerd of geblokkeerd zijn.',
    'queue.body.botsUsingLiveCapital': 'Bots die live kapitaal gebruiken.',
    'queue.body.botsWaitingReview': 'Bots die wachten op review.',
    'queue.body.estimatedTimeToFinish': 'Geschatte leestijd voor dit rapport.',
    'queue.body.executionFlowNeedsReview': 'Executieflow vraagt nog review.',
    'queue.body.fullReportBlocks': 'Volledige rapportblokken staan klaar.',
    'queue.body.handleFirst': 'Pak dit eerst op.',
    'queue.body.howTodayBehaves': 'Hoe vandaag zich gedraagt.',
    'queue.body.needDecision': 'Heeft nog een beslissing nodig.',
    'queue.body.plansAlreadyReady': 'Plannen die al klaar zijn voor uitvoering.',
    'queue.body.plansInCurrentWorkspace': 'Plannen in deze workspace.',
    'queue.body.plansNeedReview': 'Plannen die nog review nodig hebben.',
    'queue.body.slowingYouDown': 'Remt je nu af.',
    'queue.body.staleSyncMissingBackendContext': 'Verouderde sync of ontbrekende backendcontext.',
    'queue.body.topItemsSurfaced': 'Belangrijkste FINN-punten staan vooraan.',
    'queue.body.visiblePerformanceMatchesMetric': 'Zichtbare performance volgt de actieve metric.',
    'queue.body.warningsAndFlags': 'Waarschuwingen en voorzichtigheidsvlaggen in dit rapport.',
    'queue.body.weakPlansSlowing': 'Zwakke plannen die FINN afremt.',
    'queue.label.bots': 'Bots',
    'queue.label.highlights': 'Highlights',
    'queue.label.live': 'Live',
    'queue.label.paused': 'Gepauzeerd',
    'queue.label.performance': 'Prestatie',
    'queue.label.reading': 'Leestijd',
    'queue.label.reviews': 'Reviews',
    'queue.label.risks': "Risico's",
    'queue.label.sections': 'Secties',
    'queue.label.tasks': 'Taken',
    'tag.actionNeeded': 'Actie nodig',
    'tag.activeBot': 'Actieve bot',
    'tag.constructive': 'Constructief',
    'tag.defensive': 'Defensief',
    'tag.live': 'Live',
    'tag.liveContext': 'Live context',
    'tag.monitor': 'Monitor',
    'tag.monitoring': 'Monitoring',
    'tag.nearTrigger': 'Bijna trigger',
    'tag.neutral': 'Neutraal',
    'tag.review': 'Review',
    'tag.selective': 'Selectief',
    'tag.lowStable': 'Laag / stabiel',
    'tag.paper': 'Paper',
    'tag.pausedBot': 'Gepauzeerde bot',
    'tag.planReview': 'Planreview',
    'tag.staleSync': 'Sync verouderd',
    'tag.waitingConfirmation': 'Wacht op bevestiging',
    'tag.weakStructure': 'Zwakke structuur',
  };

const deMessages: Record<keyof typeof enMessages, TranslationValue> = {
  ...enMessages,
  'common.itemsOpen': ({ count }: TranslationParams) => `${count} offen`,
  'common.confidence': ({ count }: TranslationParams) => `${count}% Konfidenz`,
  'common.sections': ({ count }: TranslationParams) => `${count} Abschnitte`,
  'workspace.activeWorkspace': 'Aktiver Workspace',
  'workspace.analysis': 'Analyse',
  'workspace.automation': 'Automation',
  'workspace.myPlan': 'Mein Plan',
  'workspace.portfolio': 'Portfolio',
  'workspace.reflection': 'Reflexion',
  'workspace.settings': 'Einstellungen',
  'workspace.analysisDescription': 'Markt-, Makro- und technischer Kontext',
  'workspace.automationDescription': 'Bots, Leitplanken und Ausführungsprüfung',
  'workspace.myPlanDescription': 'Setups, Strategie und Entscheidungslogik',
  'workspace.portfolioDescription': 'Exposure, Salden und Systemstatus',
  'workspace.reflectionDescription': 'Berichte, Review und Performance-Kontext',
  'workspace.settingsDescription': 'Profil und Sitzungssteuerung',
  'login.mobile': 'Tradamind Mobile',
  'login.syncing': 'Synchronisiert',
  'login.apiLive': 'API live',
  'login.apiOffline': 'API offline',
  'login.title': 'Willkommen zurück bei FINN.',
  'login.subtitle': 'Melde dich an, um Assistant, Watchlist, Setups, Portfolio und Berichte mit Live-Backenddaten zu laden.',
  'login.email': 'E-Mail',
  'login.password': 'Passwort',
  'login.passwordPlaceholder': 'Passwort',
  'login.showPassword': 'Anzeigen',
  'login.hidePassword': 'Verbergen',
  'login.logIn': 'Einloggen',
  'login.retryLogin': 'Erneut versuchen',
  'login.bearerAuth': 'Bearer-Auth',
  'login.secureTokenStorage': 'Sichere Token-Speicherung',
  'login.autoRefresh': 'Auto-Refresh',
  'finn.askAboutExposure': 'Frage FINN nach Exposure',
  'finn.askAboutThisReport': 'Frage FINN nach diesem Bericht',
  'finn.greetingEvening': 'Guten Abend.',
  'finn.greetingEveningName': ({ name }: TranslationParams) => `Guten Abend ${name}.`,
  'finn.greetingEveningTrader': 'Guten Abend Trader.',
  'finn.noBriefingReady': 'FINN hat noch kein Briefing bereit.',
  'finn.noImmediateItems': 'Keine unmittelbaren Punkte brauchen Aufmerksamkeit.',
  'finn.openMyPlan': 'Öffne meinen Plan',
  'finn.queueSubtitle': 'Was braucht jetzt deine Aufmerksamkeit?',
  'finn.queueTitle': 'Arbeitsliste',
  'finn.refreshDailyScores': 'Tageswerte aktualisieren',
  'finn.reviewNeedsAttention': '1 Review braucht Aufmerksamkeit.',
  'finn.reviewsNeedAttention': ({ count }: TranslationParams) => `${count} Reviews brauchen Aufmerksamkeit.`,
  'finn.todayEyebrow': 'Heute mit FINN',
  'analysis.summaryUnavailable': ({ symbol }: TranslationParams) => `${symbol} ist live, aber FINN hat noch kein Analyse-Briefing zurückgegeben.`,
  'analysis.evidenceUnavailableHeadline': 'Evidence-Abschnitte sind noch nicht verfügbar.',
  'analysis.evidenceUnavailableBody': 'Das Backend hat noch keine Workspace-Zeilen für Markt, Makro und Technik zurückgegeben.',
  'analysis.forwardReturnsUnavailableHeadline': 'Forward Returns sind noch nicht verfügbar.',
  'analysis.forwardReturnsUnavailableBody': 'Das Backend hat noch keine historischen Forward-Return-Daten für dieses Asset zurückgegeben.',
  'report.unavailableHeadline': 'Es sind noch keine Berichtsdaten verfügbar.',
  'report.unavailableBody': 'Das Backend hat noch keinen brauchbaren Bericht zurückgegeben. Aktualisiere später erneut oder bitte FINN, den aktuellen Workspace-Kontext zu erklären.',
  'report.risksNeedAttention': ({ count }: TranslationParams) => `${count} Risiko${count === 1 ? '' : 'en'} brauchen Aufmerksamkeit, bevor du auf dieser Reflexion handelst.`,
  'report.period.daily': 'Tagesbericht',
  'report.period.weekly': 'Wochenbericht',
  'report.period.monthly': 'Monatsbericht',
  'report.period.quarterly': 'Quartalsbericht',
  'myPlan.workflowEyebrow': 'Plan-Workspace',
  'myPlan.workflowTitle': 'Wann handelst du und wie?',
  'myPlan.workflowSubtitle': 'Verbinde Marktbedingungen mit klaren Ausführungsregeln.',
  'myPlan.workflowStepSetup': 'Wann darf ich handeln?',
  'myPlan.workflowStepStrategy': 'Wie führe ich den Trade aus?',
  'myPlan.workflowStepPlan': 'Was ist bereit für Automatisierung?',
  'myPlan.planCheckEyebrow': 'FINN Plan-Check',
  'myPlan.planCheckReady': ({ name }: TranslationParams) => `${name} ist bereit für Automatisierung.`,
  'automation.workspaceEyebrow': 'Automation-Workspace',
  'automation.workspaceTitle': 'Automatisierung',
  'automation.workspaceSubtitle': 'Verwalte die Ausführung und überwache jeden Bot innerhalb deiner Risikogrenzen.',
  'automation.stepPlanTitle': 'Plan',
  'automation.stepPlanBody': 'Welche Regeln gelten?',
  'automation.stepExecutionTitle': 'Ausführung',
  'automation.stepExecutionBody': 'Was führt die Automatisierung aus?',
  'automation.stepMonitoringTitle': 'Monitoring',
  'automation.stepMonitoringBody': 'Bleibt alles innerhalb meines Risikos?',
  'automation.budgetRequired': 'Budget erforderlich',
  'automation.directlyVisible': 'Direkt sichtbar',
  'automation.lastChecked': 'Zuletzt geprüft',
  'automation.marketAction': 'Marktaktion',
  'automation.nextStepAddBudget': 'Nächster Schritt: Budget und Limits hinzufügen, bevor du dich bei der Ausführung auf diesen Bot verlässt.',
  'automation.paperTracking': 'Paper-Tracking',
  'automation.paused': 'Pausiert',
  'automation.review': 'Prüfen',
  'automation.statusReaction': 'Statusreaktion',
  'automation.trade': 'Trade',
  'automation.active': 'Aktiv',
  'automation.hold': 'Halten',
  'automation.liveCapital': 'Live-Kapital',
  'automation.viewFullDiagnostics': 'Vollständige Diagnose anzeigen',
  'automation.waiting': 'Warten',
  'automation.why': 'Warum',
  'automation.noBudgetSupport': 'Es ist noch kein Budget gesetzt, daher kann FINN von dieser Chain keine Trades groessen oder ausfuehren.',
  'automation.pausedLiveSupport': ({ pausedCount, liveCount }: TranslationParams) => `${pausedCount} Bots sind pausiert. ${liveCount} Live-Bots bleiben fuer die Pruefung verbunden.`,
  'automation.noBudgetWhy': 'Dieser Bot hat noch kein Budget, daher kann FINN aus dieser Chain keine Trades dimensionieren oder ausfuehren.',
  'portfolio.activeSources': ({ count }: TranslationParams) => `${count} aktive Quellen`,
  'portfolio.staleSupport': 'Einige Portfolio-Feeds sind derzeit veraltet. Pruefe Kapital, Salden und Bot-Exposure, bevor du handelst.',
  'portfolio.metricSupport': ({ metric }: TranslationParams) => `Nutze diese Seite, um Kapitalspielraum, aktuelle ${metric}-Abweichung und Live/Paper-Ausfuehrung zu pruefen.`,
  'tag.actionNeeded': 'Aktion nötig',
  'tag.activeBot': 'Aktiver Bot',
  'tag.constructive': 'Konstruktiv',
  'tag.defensive': 'Defensiv',
  'tag.live': 'Live',
  'tag.liveContext': 'Live-Kontext',
  'tag.monitor': 'Beobachten',
  'tag.monitoring': 'Beobachtung',
  'tag.nearTrigger': 'Nahe Auslöser',
  'tag.neutral': 'Neutral',
  'tag.review': 'Review',
  'tag.selective': 'Selektiv',
  'tag.lowStable': 'Niedrig / stabil',
  'tag.paper': 'Paper',
  'tag.pausedBot': 'Pausierter Bot',
  'tag.planReview': 'Planprüfung',
  'tag.staleSync': 'Veraltete Sync',
  'tag.waitingConfirmation': 'Wartet auf Bestätigung',
  'tag.weakStructure': 'Schwache Struktur',
};

const messages = {
  de: deMessages,
  en: enMessages,
  nl: nlMessages,
} satisfies Record<AppLanguage, Record<string, TranslationValue>>;

export type TranslationKey = keyof typeof messages.en;

export function translate(language: AppLanguage, key: TranslationKey, params: TranslationParams = {}) {
  const value = messages[language][key] ?? messages.en[key];
  return typeof value === 'function' ? value(params) : value;
}

export function translateFinnTag(language: AppLanguage, label: string) {
  const normalized = label.trim().toLowerCase();

  if (['action needed', 'actie nodig', 'aktion nötig'].includes(normalized)) {
    return translate(language, 'tag.actionNeeded');
  }
  if (['active bot', 'actieve bot', 'aktiver bot'].includes(normalized)) {
    return translate(language, 'tag.activeBot');
  }
  if (['constructive', 'constructief', 'konstruktiv'].includes(normalized)) {
    return translate(language, 'tag.constructive');
  }
  if (['defensive', 'defensief', 'defensiv'].includes(normalized)) {
    return translate(language, 'tag.defensive');
  }
  if (['live'].includes(normalized)) {
    return translate(language, 'tag.live');
  }
  if (['live context', 'live context', 'live-kontext'].includes(normalized)) {
    return translate(language, 'tag.liveContext');
  }
  if (['monitor', 'beobachten'].includes(normalized)) {
    return translate(language, 'tag.monitor');
  }
  if (['monitoring', 'beobachtung'].includes(normalized)) {
    return translate(language, 'tag.monitoring');
  }
  if (['near trigger', 'bijna trigger', 'nahe auslöser'].includes(normalized)) {
    return translate(language, 'tag.nearTrigger');
  }
  if (['neutral', 'neutraal'].includes(normalized)) {
    return translate(language, 'tag.neutral');
  }
  if (['review', 'reviewen', 'prüfung'].includes(normalized)) {
    return translate(language, 'tag.review');
  }
  if (['selective', 'selectief', 'selektiv'].includes(normalized)) {
    return translate(language, 'tag.selective');
  }
  if (['low / stable', 'laag / stabiel', 'niedrig / stabil'].includes(normalized)) {
    return translate(language, 'tag.lowStable');
  }
  if (['paper'].includes(normalized)) {
    return translate(language, 'tag.paper');
  }
  if (['paused bot', 'gepauzeerde bot', 'pausierter bot'].includes(normalized)) {
    return translate(language, 'tag.pausedBot');
  }
  if (['plan review', 'planreview', 'planprüfung'].includes(normalized)) {
    return translate(language, 'tag.planReview');
  }
  if (['stale sync', 'sync verouderd', 'veraltete sync'].includes(normalized)) {
    return translate(language, 'tag.staleSync');
  }
  if (['waiting confirmation', 'wacht op bevestiging', 'wartet auf bestätigung'].includes(normalized)) {
    return translate(language, 'tag.waitingConfirmation');
  }
  if (['weak structure', 'zwakke structuur', 'schwache struktur'].includes(normalized)) {
    return translate(language, 'tag.weakStructure');
  }

  return label;
}

const localeSignals: Record<AppLanguage, RegExp[]> = {
  en: [/\bis currently\b/i, /\bfocus on\b/i, /\breviews?\b/i, /\bconfidence\b/i, /\bmonitor\b/i, /\bblocked\b/i, /\bbudget\b/i, /\bgood evening\b/i, /\bdaily scores\b/i, /\brefresh daily scores\b/i, /\bweak structure\b/i, /\bmoving to plan\b/i, /\bwaiting confirmation\b/i],
  nl: [/\bstaat nu\b/i, /\bgoedenavond\b/i, /\brisico'?s?\b/i, /\bvragen aandacht\b/i, /\bververs\b/i, /\bdefensief\b/i, /\bhandelaar\b/i, /\bhallo\b/i, /\bontbreken\b/i, /\bwacht\b/i, /\bsterkere bevestiging\b/i, /\bdagrapport\b/i],
  de: [/\bist derzeit\b/i, /\bguten abend\b/i, /\babschnitte\b/i, /\bkonfidenz\b/i, /\büberwachen\b/i, /\bverteidigen\b/i, /\bberichte?\b/i, /\btageswerte\b/i],
};

export function localizedBackendText(language: AppLanguage, text: string | null | undefined, fallback: string) {
  const value = String(text || '').trim();
  if (!value) return fallback;

  const signals = localeSignals[language];
  const expectedMatchCount = signals.filter((pattern) => pattern.test(value)).length;
  const foreignMatchCount = Object.entries(localeSignals)
    .filter(([locale]) => locale !== language)
    .reduce((count, [, patterns]) => count + patterns.filter((pattern) => pattern.test(value)).length, 0);

  const hasExpectedSignal = expectedMatchCount > 0;
  const hasForeignSignal = foreignMatchCount > 0;

  if (hasForeignSignal && !hasExpectedSignal) {
    return fallback;
  }

  if (hasForeignSignal && foreignMatchCount >= expectedMatchCount) {
    return fallback;
  }

  if (language !== 'en' && !hasExpectedSignal) {
    return fallback;
  }

  const englishSignalCount = localeSignals.en.filter((pattern) => pattern.test(value)).length;
  if (language !== 'en' && englishSignalCount > 0 && expectedMatchCount <= englishSignalCount) {
    return fallback;
  }

  return value;
}
