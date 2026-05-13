# Tradamind Project Analysis

Datum analyse: 2026-05-10  
Scope: bestaande backend, Next.js frontend en Expo/React Native mobile prototype.

## Executive Summary

Tradamind is geen simpel trading dashboard. Het project is uitgegroeid tot een AI-first trading intelligence operating system voor crypto-besluitvorming: het combineert marktdata, macrodata, technische indicatoren, persoonlijke setups, strategieen, bot-beslissingen, portfolio-context, rapportages en een conversationele assistant.

De desktop-app is momenteel het complete command center. De mobile app moet daar niet een verkleinde kopie van worden. De sterkste mobiele richting is een assistant-first decision companion: snel openen, vragen stellen, context krijgen, risico begrijpen, een setup/strategie/bot als concept laten voorbereiden en alleen de essentiele acties bevestigen.

De backend bevat al veel van wat hiervoor nodig is: authenticated APIs, score endpoints, agent insights, SSE assistant streaming, conversation state, deterministic slot filling, draft payloads, bot endpoints, watchlist, reports, push subscriptions en een scheduled intelligence pipeline via Celery. De huidige mobile app is echter nog vooral een prototype met mockdata en een onvolledige API-koppeling.

## 1. Backend Architectuur

### Hoofdstructuur

De backend is een FastAPI-app in `backend/trading-tool-backend/backend/main.py`. Routers worden onder `/api` geladen via `safe_include`, met afzonderlijke modules voor auth, onboarding, market, macro, technical, setups, strategy, scores, dashboard, agents, bot, reports, assistant, admin, notifications, exchange en watchlist.

Belangrijke architectuurpatronen:

- API layer: `backend/api/*.py`
- Service layer: `backend/services/*.py`
- Repository layer: `backend/infrastructure/repositories/*.py`
- Database models: `backend/infrastructure/models.py`
- Background jobs: `backend/celery_task/*.py`
- AI agents: `backend/ai_agents/*.py`
- AI core/prompt/context utilities: `backend/ai_core/*.py`
- Trading/bot engines: `backend/engine/*.py`

Dit is al duidelijk opgezet als layered architecture. De codebase is niet alleen CRUD; veel domeinlogica zit in services, engines en scheduled agents.

### Bestaande API-systemen

Belangrijkste API-domeinen:

- Auth: `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout`, `/api/auth/me`
- Dashboard: `/api/dashboard`, `/api/dashboard/health`, `/api/dashboard/trading_advice`, `/api/dashboard/top_setups`, `/api/dashboard/setup_summary`
- Scores: `/api/score/macro`, `/api/score/technical`, `/api/score/market`, `/api/scores/daily`, `/api/scores/history`, `/api/ai/master_score`
- Assistant: `/api/assistant/chat`, `/api/assistant/chat/stream`, `/api/assistant/preferences`, `/api/assistant/insight`
- Agents: `/api/agents/insights/{category}`, `/api/agents/reflections/{category}`, `/api/tasks/{task_id}`
- Market data: live/latest, 7d, forward returns, indicator lists/rules
- Macro data: indicator CRUD, daily/weekly/monthly/quarterly summaries, rules
- Technical data: indicator CRUD, daily/weekly/monthly/quarterly summaries, history/rules
- Setups: CRUD, active, top, daily scores, explanations
- Strategies: CRUD, generate, analyze, active-today, execution curves
- Bots/orders: bot configs, today/history, generate/skip/mark executed, manual order preview/create, portfolios, trades, trade plans, balance history
- Reports: daily/weekly/monthly/quarterly latest/history/generate/export
- Exchange: encrypted keys and balances
- Watchlist: list/add/remove symbols
- Notifications: push subscribe/unsubscribe
- Admin: AI stats, users, logs, log analysis

### AI endpoints en AI-systemen

De belangrijkste assistant endpoints zijn production-relevant:

- `POST /api/assistant/chat`: non-streaming JSON response met `response`, `intent`, `action`, `draft`, `state`, `reasoning`, `trace_id`.
- `POST /api/assistant/chat/stream`: SSE streaming met tekstchunks en finale envelope.
- `GET/PATCH /api/assistant/preferences`: AI-personalisatie zoals tone, detail level, coaching style, experience level en risk profile.
- `POST /api/assistant/insight`: snelle contextuele greeting, bot insight en market insight.

Daarnaast bestaan categorie-agents:

- Macro agent
- Market agent
- Technical agent
- Setup agent
- Strategy agent
- Trading bot agent
- Daily/weekly/monthly/quarterly report agents
- Score/master-score agent

De assistant is geen losse chatbot. `AiAssistantService` bouwt context uit scores, setups, reports, bots, user preferences, market data, strategy data, conversation state en portfolio intelligence. `AiGateway` handelt AI-quota, cache, semantic cache, cost logging en fallback af.

### Score-systemen

Er bestaan meerdere scorelagen:

- Individuele indicator scoring voor macro, market en technical.
- Daily combined scores in `daily_scores`: macro, technical, market, setup per user/symbol.
- Daily setup scores in `daily_setup_scores`.
- AI category insights in `ai_category_insights`: category, score, trend, bias, risk, summary, top signals.
- AI master score via `/api/ai/master_score`.
- Market pressure engine, regime weighting, transition detector en policy/decision engines.
- Bot scores en guardrails in bot decisions/trade plans.

De score-engine is niet alleen een displaylaag. Scores sturen rapporten, assistant-context, botbeslissingen, setup matching en trading advice.

### Dataflows

Hoofdflow:

1. Market/macro/technical data wordt opgehaald via scheduled Celery jobs en runtime fetches.
2. Indicatoren worden gescoord met regels en user-configuraties.
3. `daily_scores` en `ai_category_insights` worden gevuld.
4. Dashboard, reports, assistant en bot engines lezen dezelfde intelligencebronnen.
5. Setups en strategies vertalen scores naar persoonlijke execution logic.
6. Bots gebruiken scores, setup/strategy snapshots, portfolio en guardrails om acties of trade plans te maken.
7. Assistant gebruikt dezelfde context om uitleg, coaching, drafts en navigatie-acties te geven.

Celery beat is volwassen opgezet: market data per 15 minuten, indicator dispatching verspreid over de dag, rule-based scores per 15 minuten, portfolio snapshots, setup agent, trading bot, AI agents, regime memory, strategy snapshot, master score en daily report. De dispatcher staggered jobs per user om pieken te verminderen.

### Production-ready onderdelen

Sterk/production-minded:

- FastAPI router structuur met auth en typed Pydantic schemas.
- Repository/service layering.
- Cookies/refresh auth in web frontend.
- Assistant rate limiting per user en IP.
- Assistant trace IDs, observability velden, usage logs en AI cost tracking.
- Conversation state in database.
- Deterministic slot parsing en draft completion voor assistant workflows.
- AI gateway met quota, exact cache, semantic cache en fallback.
- Celery schedule met rate limiting en staggered dispatch.
- Startup migrations/hotfixes voor live database compatibiliteit.
- Push notification endpoints.
- Exchange key model met encrypted key intent.
- Verification/benchmark scripts voor assistant flows.

Nog niet volledig product-hard:

- Startup migrations in `main.py` zijn pragmatische hotfixes, geen formeel migratiesysteem.
- Sommige frontend API helpers verwijzen naar endpoints die niet lijken te bestaan, zoals `/api/ai/explain_setup`, `/api/ai/strategy` en `/api/ai/score`.
- Mobile API contract klopt nog niet: mobile stuurt `message`, backend verwacht `query`; mobile verwacht `response.message`, backend retourneert `response`.
- Mobile mist auth/cookie/session handling.
- In-memory rate limiting werkt per proces, niet cluster-safe.
- Assistant endpoint whitelist verschilt subtiel tussen non-streaming en streaming schema voor `navigate_to_page`.
- Veel scripts/tests zijn nuttig, maar er lijkt geen uniforme CI/teststrategie.

## 2. Product Analyse

### Wat is Tradamind?

Tradamind is het best te omschrijven als:

> Een AI-first crypto trading intelligence OS dat gebruikers helpt van marktcontext naar persoonlijke setup, strategie, botbeslissing en rapportage te gaan.

Het product bestaat uit meerdere lagen:

- Intelligence layer: macro, market, technical, setup, master score.
- Decision layer: dashboard, trading advice, score history, active setup, strategy.
- Execution layer: bot configs, trade plans, guardrails, manual orders, exchange integration.
- Coaching layer: assistant, reports, AI insights, reflections.
- Personalization layer: onboarding, preferences, risk profile, behavioral signals.

### Is het een dashboard?

Ja, maar dat is slechts de desktop-shell. De dashboardpagina bundelt live market, charting, compact gauges, trading brain, tabs met deep analysis en score history. Desktop is duidelijk bedoeld als cockpit of command center.

### Is het een AI coach?

Ja. De assistant heeft context, geheugen, intent routing, adaptive personalization en flow registry. Hij kan uitleggen, waarschuwen, begeleiden, concepten voorbereiden en suggesties geven. De coachinglaag is een kernonderscheid, niet een bijzaak.

### Is het een operating system?

In producttermen: ja. Tradamind heeft modules die samen een operating loop vormen:

1. Observe market.
2. Interpret scores.
3. Match setup.
4. Generate/refine strategy.
5. Decide bot action.
6. Execute or skip.
7. Reflect/report.
8. Update preferences and behavior.

De desktop UX toont die modules als aparte schermen. Mobile moet die loop juist als gesprek en compacte dagelijkse feed presenteren.

### Belangrijkste onderdelen

De belangrijkste product-assets zijn:

- Assistant + flow registry: dit is de natuurlijke mobiele interface.
- Master score + daily scores: snelle decision state.
- Active strategy/setup: persoonlijke context, belangrijker dan algemene marktdata.
- Bot today/trade plan/guardrails: hoogste actiewaarde.
- Reports/insights: uitleg en reflectie.
- Watchlist/active asset: bepaalt context en personalisatie.

Minder belangrijk voor mobile-first:

- Volledige indicator configuratie.
- Grote tabellen.
- Complexe chart layouts.
- Admin.
- Uitgebreide backtests.
- Bulk CRUD voor setups/strategies.

## 3. UX Analyse

### Desktop-first delen

Desktop-first zijn vooral:

- Dashboard met brede chart + TradingBrain + deep analysis tabs.
- Macro/market/technical schermen met terminal HUDs, tabellen en indicator panels.
- Strategy/setup managers met formulieren en lijsten.
- Bot pagina met portfolio cards, budget forms, guardrails, history tables en order modals.
- Report layout en export/print flows.
- Admin AI/users/logs.

Deze onderdelen vragen schermruimte, vergelijking, tabelscan en multi-panel focus. Ze zijn geschikt voor desktop, matig voor telefoon.

### Mobile-geschikte delen

Goed geschikt voor mobile:

- Assistant chat.
- Today summary met macro/market/technical/setup scores.
- Active strategy card.
- Bot decision of trade plan card.
- Watchlist asset switching.
- Push alerts.
- Quick actions: confirm draft, skip bot, mark executed, add/remove watchlist.
- Compact report summary.
- Preferences/risk profile.

### Assistant-first onderdelen

Deze onderdelen moeten op mobile primair via assistant lopen:

- Setup creation.
- Strategy creation.
- Bot creation.
- Risk check.
- Macro/technical walkthrough.
- Portfolio review.
- Report walkthrough.
- Navigatie tussen decision states.

De flow registry bestaat hier al voor. Mobile moet deze registry niet nabouwen als lange forms, maar de backend state/draft/action envelope gebruiken.

### Te complex voor mobile als centrale ervaring

Niet centraal zetten:

- Indicator rule editing.
- Score weight tuning als primaire flow.
- Full-screen TradingView met veel overlays.
- Backtest configuratie.
- Multi-bot portfolio dashboards.
- Admin logs/stats.
- PDF export.
- Volledige historische tabellen.

Deze kunnen later als advanced sheets of deep links bestaan, maar niet als hoofdproduct.

## 4. Assistant Analyse

### Bestaande assistant-systemen

De assistant heeft al:

- Intent classification.
- Role routing.
- Streaming en non-streaming chat.
- Conversation abort/reset.
- Active asset priority: explicit symbol > page symbol > conversation state > BTC.
- Sequential runtime context loading via `AssistantContextRepository`.
- Live market data injection.
- Historical/analysis context per intent.
- Portfolio intelligence context.
- Behavioral signals.
- Adaptive personalization via user preferences.
- Deterministic slot pre-parsing.
- Persistent conversation state.
- Draft generation voor setup, strategy en bot.
- Action generation voor watchlist, navigation, setup/strategy/bot flows.
- Reasoning envelope met confidence/risk/coaching.
- Usage logging, trace IDs en cache via `AiGateway`.

### Direct bruikbare endpoints voor mobile

Voor mobile MVP:

- `POST /api/assistant/chat/stream` voor echte assistant-first ervaring.
- `POST /api/assistant/chat` als fallback.
- `POST /api/assistant/insight` voor home/assistant greeting en quick context.
- `GET /api/assistant/preferences` en `PATCH /api/assistant/preferences`.
- `GET /api/scores/daily?symbol=...`.
- `GET /api/ai/master_score?symbol=...`.
- `GET /api/strategies/active-today`.
- `GET /api/bot/today?symbol=...`.
- `GET /api/report/daily/latest?symbol=...`.
- `GET/POST/DELETE /api/watchlist`.
- `GET /api/market_data/{symbol}/latest`.
- `POST /api/bot/skip`, `POST /api/bot/mark_executed`.
- `POST /api/setups`, `POST /api/strategies`, `POST /api/bot/configs` voor confirmed drafts.

### Beschikbare assistant-context

De assistant heeft nu context over:

- User preferences en AI profile.
- Active asset/page metadata.
- Live price/change.
- Latest scores and category insights.
- Setups.
- Latest strategy.
- Bot history and behavioral patterns.
- Portfolio intelligence.
- Reports.
- Conversation state/slots.
- Watchlist actions via generated action envelope.

Dit is precies de context die mobile nodig heeft. De ontbrekende schakel is niet intelligentie, maar een mobile API client/state layer die deze contracten netjes verwerkt.

## 5. Mobile Strategie

### Hoe mobile moet verschillen van desktop

Desktop is een cockpit. Mobile moet een pocket co-pilot zijn.

Desktop:

- Volledig overzicht.
- Analyse diepte.
- Tabellen, charts, configuratie.
- Multi-module navigation.
- Strategie/bot beheer.

Mobile:

- "Wat moet ik nu weten?"
- "Kan ik dit doen?"
- "Waarom wel/niet?"
- "Maak een concept voor me."
- "Bevestig/skip/markeer."
- Push-driven re-engagement.
- Assistant als hoofdnavigatie.

Mobile moet minder schermen hebben, maar meer context per interactie.

### Belangrijke mobile flows

Fase-1 flows:

- Login/session.
- Assistant chat met streaming.
- Today screen met master score, domain scores, market snapshot en active recommendation.
- Active Strategy screen met entry, targets, stop loss, confidence en AI explanation.
- Bot Today card met action, confidence, guardrails, amount, reasons, skip/mark executed.
- Assistant draft confirmation voor setup/strategy/bot.
- Watchlist/active asset switching.
- Preferences: risk profile, experience level, tone/detail.

Fase-2 flows:

- Push alert naar assistant context: "Waarom kreeg ik deze alert?"
- Voice input/dictation style assistant.
- Report summary.
- Portfolio/risk review.
- Manual order preview, zeer voorzichtig en bevestigingsgericht.

Fase-3 flows:

- Offline-ish cached last state.
- Advanced charts.
- Multi-bot monitoring.
- Native notifications with deep links.
- Exchange/live execution gating.

### Essentiele schermen

Aanbevolen hoofdstructuur:

- Assistant: primair startscherm.
- Today: compacte daily intelligence feed.
- Action: bot decision/trade plan/active setup.
- Strategy: actieve strategie en relevante levels.
- Profile/Settings: preferences, session, backend status.

Alternatief: bottom tabs beperken tot `Assistant`, `Today`, `Action`, `Profile`. Strategy kan onder Action vallen. Dit past beter bij assistant-first.

### Wat niet centraal moet staan

Niet centraal op mobile:

- Macro, Technical en Market als aparte desktopachtige tabs.
- Setup Manager als formulier-first.
- Strategy Manager als lijst-first.
- Bot Manager als CRUD-first.
- Reports als PDF/read-heavy center.
- Admin.

Deze concepten moeten bestaan als assistant intents en compact cards, niet als desktopkopieen.

## 6. Architectuur Analyse Voor React Native/Expo

### Huidige mobile status

De `mobile/` app is een Expo app met bottom tabs:

- Assistant
- Today
- Strategy
- Settings

Het gebruikt mockdata in `mobile/src/services/mockDataService.ts`. De huidige `apiClient.ts` heeft alleen `postAssistantChat` naar `http://localhost:8000/api/assistant/chat`, zonder auth en met een contract mismatch. `AssistantChatRequest` in backend verwacht `query`; mobile stuurt nu `message`. Backend retourneert `response`; mobile verwacht `response.message`.

Conclusie: mobile is een goede UX-schets, maar nog geen functionele client.

### Beste koppeling met backend

Gebruik dezelfde backend, geen aparte mobile backend in fase 1. Voeg wel een mobile API client layer toe met heldere contracten:

- `authClient`: login, refresh, logout, me.
- `assistantClient`: chat, stream, insight, preferences.
- `scoresClient`: daily, master, history.
- `strategyClient`: active today.
- `botClient`: today, skip, mark executed, configs waar nodig.
- `watchlistClient`: list/add/remove.
- `marketClient`: latest price.

Voor mobile is een BFF later nuttig, maar niet nodig voor de eerste echte versie. Eerst de bestaande APIs benutten.

### Auth/session aanpak

De web app gebruikt cookies met refresh. React Native heeft geen browser-cookie flow zoals web. Mobile heeft daarom een bewuste auth-strategie nodig:

- Optie A: cookie jar met `credentials: include` en platform-support goed testen.
- Optie B: backend uitbreiden met token-based mobile auth.
- Optie C: hybride: login retourneert access token voor mobile, web blijft cookie-based.

Aanbeveling: kies expliciet voor mobile token auth of een bewezen cookie-jar library. Zonder dit blijft alle mobile API integratie fragiel.

### State/data architectuur

Aanbevolen:

- TanStack Query voor server state: scores, assistant insight, bot today, strategy, watchlist.
- Zustand of lightweight context voor UI/app state: active asset, assistant draft envelope, selected tab, local preferences.
- AsyncStorage/SecureStore voor tokens, selected asset en last known assistant/session data.
- SSE support via fetch streaming waar platform mogelijk is; fallback naar non-streaming chat als streaming op device lastig is.

Server state moet dominant blijven. De backend heeft al conversation state; mobile moet die niet dupliceren, alleen renderen.

### Assistant envelope rendering

Mobile moet de assistant response niet als platte tekst behandelen. De backend envelope is productwaarde:

- `response`: chat tekst.
- `intent`: route/coaching context.
- `action`: render als quick action button(s).
- `draft`: render als review card met confirm/edit/cancel.
- `state`: render als progress chip.
- `reasoning`: intern/debug of optioneel "waarom" detail.
- `trace_id`: support/debug.

Dit is de basis voor assistant-first UX.

## 7. Conclusie

### Wat Tradamind nu is

Tradamind is nu een desktop-first AI trading command center met een volwassen backend intelligence layer. Het combineert data ingestion, scoring, AI category agents, assistant workflows, strategy/setup modeling, bot decisioning en reporting.

Het product is rijker dan de UI soms communiceert: de backend is al dicht bij een personal trading intelligence OS.

### Wat Tradamind Mobile moet worden

Tradamind Mobile moet een AI trading co-pilot worden:

- Assistant als primaire interface.
- Today intelligence als snelle status.
- Active action cards voor strategie/bot/risico.
- Draft-confirm flows in plaats van lange formulieren.
- Push-driven en context-aware.
- Rustiger, kleiner en besluitgerichter dan desktop.

Mobile moet gebruikers helpen minder vaak naar complexe dashboards te kijken, niet dezelfde complexiteit in kleiner formaat tonen.

### Grootste kansen

- De assistant backend is al klaar voor mobile-first UX.
- Draft/state/action envelopes kunnen forms vervangen.
- Daily scores en master score zijn perfect voor mobile summaries.
- Bot today/trade plan is een sterke high-frequency mobile use case.
- Push notifications kunnen direct naar assistant explanations leiden.
- Mobile kan Tradamind positioneren als dagelijkse trading coach, niet alleen als analyse-tool.

### Grootste UX-risico's

- Desktop kopieren naar mobile.
- Te veel tabs/modules tonen.
- Assistant alleen als chatbot tonen in plaats van action interface.
- Te veel scoregetallen zonder duidelijke "so what".
- Trading actions te snel of te agressief maken zonder guardrails.
- Complexe setup/strategy/bot creation als forms bouwen terwijl conversation state al bestaat.
- Inconsistentie tussen web assistant actions en mobile assistant actions.

### Grootste technische risico's

- Mobile auth niet goed oplossen.
- Contract drift tussen frontend helpers, backend endpoints en mobile types.
- SSE support op React Native devices onderschatten.
- Geen gedeelde API types/contracts.
- Backend hotfix migrations blijven groeien zonder echte migraties.
- Assistant state/draft confirm flows niet idempotent maken.

## 8. Aanbevolen Roadmap

### Fase 1: Mobile Foundation en echte backend-koppeling

Doel: van mock prototype naar werkende assistant-first client.

- Mobile auth strategy kiezen en implementeren.
- API base URL configureren via environment, niet hardcoded localhost.
- Contract mismatch oplossen: `query` gebruiken en `response/action/draft/state/reasoning` renderen.
- Assistant non-streaming werkend maken; streaming als progressive enhancement.
- Today screen koppelen aan `/api/scores/daily`, `/api/ai/master_score` en latest market data.
- Strategy screen koppelen aan `/api/strategies/active-today`.
- Settings koppelen aan `/api/auth/me`, `/api/assistant/preferences` en `/api/health`.
- Basic error, loading en offline-last-known states.

### Fase 2: Assistant Action UX

Doel: mobile wordt meer dan chat.

- Assistant envelope renderer bouwen.
- Action buttons voor watchlist, navigation, setup/strategy/bot deep links.
- Draft review cards voor setup, strategy en bot.
- Confirm/cancel/edit flows aansluiten op bestaande create endpoints.
- State progress chip renderen voor actieve flows.
- Active asset context consequent meesturen.
- Suggested next actions als tappable prompts tonen.

### Fase 3: Today en Decision Companion

Doel: dagelijks gebruik verhogen.

- Today feed ontwerpen rond "Now / Risk / Action / Why".
- Bot Today card: action, confidence, guardrails, amount, reasons.
- Skip en mark executed flow toevoegen.
- Daily report summary integreren.
- Watchlist + asset switching.
- Portfolio/risk review als assistant quick flow.
- Push notification subscription en deep links naar assistant context.

### Fase 4: Native Quality en Trust Layer

Doel: vertrouwen, veiligheid en premium gevoel.

- Streaming assistant stabiel maken op iOS/Android.
- Secure token storage.
- Trace ID zichtbaar in support/debug.
- Guardrail explanations op alle risky actions.
- Confirmation friction voor live/exchange-gerelateerde acties.
- Observability voor mobile requests en assistant errors.
- App-state refresh, background resume en stale data indicators.

### Fase 5: Advanced Mobile Workflows

Doel: power users bedienen zonder mobile te overladen.

- Compact charts, alleen voor context en bevestiging.
- Report walkthroughs.
- Multi-bot monitoring.
- Manual order preview met strict confirmation.
- Voice input.
- Personalized coaching routines.
- In-app learning prompts op basis van behavioral signals.

## Aanbevolen Productprincipe

De kernregel voor Tradamind Mobile:

> Toon niet alle intelligentie. Toon de volgende beste beslissing, de reden, het risico en de veilige actie.

Desktop blijft het command center. Mobile wordt de coach in je hand.
