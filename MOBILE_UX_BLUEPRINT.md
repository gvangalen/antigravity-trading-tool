# Tradamind Mobile UX Blueprint

Datum: 2026-05-10  
Basiscontext: `PROJECT_ANALYSIS.md`  
Scope: mobile UX architectuur, app-flow, interaction design en productgedrag voor Tradamind Mobile.

## 0. North Star

Tradamind Mobile is geen mobiele trading terminal. Het is een AI-native trading operating layer die de gebruiker helpt om rustiger, contextvoller en veiliger beslissingen te nemen.

De kernbelofte:

> Open de app, begrijp wat ertoe doet, neem alleen een bewuste actie, en keer terug naar de assistant.

Desktop blijft het volledige command center. Mobile wordt de dagelijkse co-pilot: snel, contextueel, adviserend en actiegericht.

## 1. Mobile Product Filosofie

### Wat De Gebruiker Moet Voelen

De gebruiker moet voelen:

- Rust: de app verlaagt trading stress in plaats van die op te voeren.
- Controle: elke aanbeveling heeft context, risico en reden.
- Focus: er is altijd een duidelijke volgende stap, of juist een duidelijke reden om niets te doen.
- Vertrouwen: AI is transparant genoeg om te begrijpen, maar niet zo verbose dat het besluitvorming vertraagt.
- Continuiteit: mobile voelt verbonden met desktop, bot, strategie, setup en rapportage.
- Bescherming: Tradamind remt impulsieve acties af bij zwakke signalen of onduidelijke risk/reward.

De emotionele baseline is niet "trade nu", maar "beslis beter".

### Verschil Met Traditionele Trading Apps

Traditionele trading apps optimaliseren vaak voor:

- Koersen.
- Grafieken.
- Order buttons.
- FOMO-notificaties.
- Veel assets en veel beweging.
- Snelle executie.

Tradamind Mobile optimaliseert voor:

- Context voor actie.
- Risico voor rendement.
- Persoonlijke strategie boven algemene marktnoise.
- AI-coaching boven ruwe data.
- Guardrails boven impuls.
- Uitleg en reflectie boven dopamine.

Een traditionele trading app vraagt: "Wil je kopen of verkopen?"  
Tradamind Mobile vraagt: "Past deze actie bij je setup, score, strategie en risico?"

### Waarom Assistant-First?

Assistant-first is logisch omdat de backend al een intelligence layer heeft die context kan combineren:

- Daily scores.
- Master score.
- Active setup.
- Active strategy.
- Bot recommendation.
- Market snapshot.
- User preferences.
- Behavioral signals.
- Conversation state.
- Drafts and actions.

Een scherm kan meestal maar een deel van die context tonen. Een assistant kan de juiste context selecteren, samenvatten en in actie omzetten.

Assistant-first betekent niet chat-only. Het betekent dat de assistant de operating layer is:

- De assistant geeft briefing.
- De assistant legt kaarten uit.
- De assistant start flows.
- De assistant maakt drafts.
- De assistant routeert naar workspace-schermen.
- De assistant brengt de gebruiker terug naar de belangrijkste beslissing.

### AI + Dashboard Zonder Chaos

De UX combineert AI en workspace via drie lagen:

- Assistant layer: context, uitleg, coaching, flows, decision framing.
- Card layer: compacte objecten zoals score, strategy, bot action, draft, warning.
- Workspace layer: gefocuste schermen voor inspectie en bevestiging.

Regel:

> AI vertelt wat belangrijk is. Cards tonen bewijs en actie. Workspace geeft controle wanneer detail nodig is.

Dashboardinformatie mag nooit los rondzweven. Elk datapunt moet antwoord geven op een vraag:

- Wat is de toestand?
- Waarom verandert dit mijn beslissing?
- Wat kan ik veilig doen?
- Wanneer moet ik juist wachten?

## 2. Core Mobile Flow

### Ideale Dagelijkse Flow

#### Stap 1: Gebruiker opent app

Startpunt is bij voorkeur `Assistant`, niet een marktdashboard. De eerste viewport toont:

- Korte AI briefing.
- Active asset.
- Current decision state.
- Belangrijkste risico of kans.
- Een primaire quick action, meestal "Bekijk Today" of "Controleer actie".

De gebruiker moet binnen 5 seconden weten of er iets belangrijks speelt.

#### Stap 2: Assistant briefing

De assistant toont geen lange chatgeschiedenis als eerste object. Hij toont een briefing card:

- "Wat speelt er nu?"
- "Wat betekent dit voor jouw strategie?"
- "Wat is de veilige volgende stap?"

Voorbeeldstructuur:

- Status: `Constructive, not aggressive`
- Why: `Market en technical zijn sterk, setup wacht op betere entry`
- Risk: `Entry dicht bij weerstand`
- Next: `Bekijk actieve strategie` of `Wacht op bevestiging`

#### Stap 3: Context bekijken

De gebruiker tapt op Today, een insight card of een assistant suggestion. De app opent een compacte context:

- Master score.
- Macro/market/technical/setup scores.
- Market snapshot.
- What matters now.
- Active recommendation.

Context is scanbaar en niet bedoeld als research-terminal.

#### Stap 4: Strategie/setup bekijken

Wanneer actie relevant is, gaat de gebruiker naar `Action` of `Strategy`.

Hier ziet de gebruiker:

- Actieve setup.
- Strategy confidence.
- Entry zone.
- Targets.
- Stop/invalidation.
- Bot recommendation.
- Waarom deze actie wel/niet past.

Het scherm moet antwoord geven op: "Is mijn plan nog geldig?"

#### Stap 5: Actie nemen of overslaan

Acties zijn altijd framed:

- Confirm draft.
- Skip bot action.
- Mark executed.
- Add to watchlist.
- Ask assistant why.
- Open deeper workspace.

Execution confirmation mag niet voelen als een casino-button. Voor trading/bot acties:

- Toon action summary.
- Toon risico.
- Toon guardrail status.
- Toon consequence.
- Vereis expliciete bevestiging.

#### Stap 6: Terug naar assistant

Na elke actie keert de gebruiker terug naar de assistant met een status update:

- "Ik heb deze botactie overgeslagen. Ik blijf SOL monitoren."
- "Setup draft is opgeslagen. Volgende logische stap: strategie laten genereren."
- "Trade gemarkeerd als uitgevoerd. Ik neem dit mee in je volgende rapport."

De assistant sluit de loop. Dat maakt mobile coherent.

### Core Loop

De dagelijkse mobile loop:

1. Brief.
2. Inspect.
3. Decide.
4. Confirm or skip.
5. Reflect.
6. Return to assistant.

Elke UX-flow moet in deze loop passen.

## 3. Navigation Architectuur

### Primaire Bottom Tabs

Aanbevolen bottom tabs:

1. `Assistant`
2. `Today`
3. `Action`
4. `Workspace`
5. `Profile`

Als de app extreem gefocust moet blijven, kan `Workspace` later verborgen worden achter Assistant/Today. Voor een eerste volwassen mobile product is deze structuur helder genoeg zonder desktop over te nemen.

### Tab 1: Assistant

Rol:

- Operating layer.
- Startpunt.
- Coaching.
- Flow orchestration.
- Drafts/actions.

Bevat:

- Briefing.
- Assistant feed.
- Chat composer.
- Suggested prompts.
- Active flow state.
- Cards in conversation.

### Tab 2: Today

Rol:

- Dagelijkse intelligence summary.
- Scanbare markt- en strategiecontext.

Bevat:

- Master score.
- What matters now.
- Domain score cards.
- Market snapshot.
- Active recommendation.
- Link naar Action.

### Tab 3: Action

Rol:

- Alles wat vandaag besluitbaar is.
- Bot action, active strategy, setup validity, risk confirmation.

Bevat:

- Active setup/strategy block.
- Bot recommendation.
- Risk/execution card.
- Confirm/skip/ask assistant.

### Tab 4: Workspace

Rol:

- Gefocuste inspectie en lichte configuratie.
- Geen volledige desktopkopie.

Bevat:

- Watchlist.
- Compact reports.
- Setup/strategy list summaries.
- Bot list summaries.
- Deep links naar desktop voor zware configuratie.

### Tab 5: Profile

Rol:

- Vertrouwen, personalisatie en account.

Bevat:

- User profile.
- AI preferences.
- Risk profile.
- Experience level.
- Notification settings.
- Backend/session status.
- Support/debug trace area.

### Primaire Schermen

Primair:

- Assistant Home.
- Today Summary.
- Action Center.
- Active Strategy Detail.
- Draft Review.
- Bot Decision Detail.
- Profile Preferences.

Secundair:

- Watchlist management.
- Report summary.
- Setup summary.
- Strategy summary.
- Bot summary.
- Notification settings.
- Backend/system status.

Niet mobiel centraal:

- Full indicator editor.
- Full macro/technical/market tables.
- Admin.
- Backtest studio.
- PDF exports.
- Complex chart configuration.

### Deep Navigation

Deep navigation werkt via objecten, niet via pagina's.

Voorbeelden:

- Push alert over BTC bot decision -> opent `Action > Bot Decision Detail`.
- Assistant action `open_strategy` -> opent `Action > Active Strategy Detail`.
- Draft returned by assistant -> opent `Draft Review Sheet`.
- Score tap in Today -> opent `Score Detail Sheet`, niet een volledige macro/technical pagina.
- Report alert -> opent `Report Summary`, met "Vraag assistant om uitleg".

### Modals en Sheets

Gebruik bottom sheets voor:

- Score detail.
- Risk explanation.
- Draft review.
- Confirm action.
- Edit small parameter.
- Choose active asset.
- Suggested prompt picker.

Gebruik full-screen modal alleen voor:

- Authentication.
- Complex draft edit.
- Onboarding/preferences.
- High-risk execution confirmation.

### Push Deep Links

Pushmeldingen mogen nooit direct naar een koop/verkoopknop leiden. Ze openen context.

Push types:

- `daily_briefing_ready` -> Assistant briefing.
- `bot_action_ready` -> Action bot card.
- `risk_warning` -> Warning card + assistant explanation.
- `strategy_invalidated` -> Strategy detail.
- `report_ready` -> Report summary.
- `draft_needs_review` -> Draft review sheet.

Elke push heeft:

- Menselijke titel.
- Korte reden.
- Deep link naar context.
- Secondary action: "Vraag waarom".

### Assistant-Driven Navigation

Assistant actions sturen navigatie, maar blijven beperkt en voorspelbaar:

- Open Today.
- Open Action.
- Open Strategy detail.
- Open Draft Review.
- Open Watchlist.
- Open Preferences.

De assistant mag niet zomaar diepe desktopachtige routes openen. Hij moet mobiele objecten openen.

## 4. Assistant UX Architectuur

### Assistant Feed

De Assistant tab is een feed met conversationele en card-gebaseerde elementen.

Volgorde:

1. Current context header.
2. Briefing card.
3. Active state card indien flow actief is.
4. Assistant/user messages.
5. Insight/action/draft cards inline.
6. Composer.

De feed is geen eindeloze chatdump. Oude berichten zijn beschikbaar, maar de actuele decision state staat bovenaan.

### Chat Messages vs Insight Cards

Chat messages:

- Kort.
- Conversational.
- Voor uitleg, vragen en begeleiding.
- Niet gebruiken voor complexe data.

Insight cards:

- Gestructureerd.
- Scanbaar.
- Voor market state, score breakdown, risk warning, recommendation.
- Bevatten labels, waarden, status en CTA.

Regel:

> Tekst legt uit. Cards laten beslissen.

### Action Cards

Action cards zijn uitvoerbare assistant-output.

Voorbeelden:

- Add SOL to watchlist.
- Open active strategy.
- Review setup draft.
- Skip bot action.
- Mark executed.

Structuur:

- Title.
- One-line reason.
- Impact/risk hint.
- Primary action.
- Secondary action: ask why / cancel.

### Draft Review Cards

Drafts komen uit de assistant backend voor setup, strategy of bot.

Draft card structuur:

- Type badge: Setup / Strategy / Bot.
- Asset.
- Purpose.
- Key parameters.
- Missing or assumed values.
- Risk note.
- Buttons: `Confirm`, `Edit`, `Cancel`, `Ask why`.

Voor setup draft:

- Symbol.
- Setup type.
- Timeframe/frequency.
- Score thresholds.
- Market condition.

Voor strategy draft:

- Symbol.
- Entry.
- Targets.
- Stop loss.
- Base amount.
- Confidence/risk profile.

Voor bot draft:

- Mode.
- Live/paper status.
- Budget.
- Daily limit.
- Max exposure.
- Cadence.

Geen draft wordt stilletjes uitgevoerd. Mobile is review-first.

### Warning/Risk Cards

Risk cards moeten visueel duidelijk zijn, maar niet paniekerig.

Types:

- Strategy invalidation warning.
- Bot guardrail block.
- Concentration risk.
- Low confidence.
- Data stale warning.
- High volatility.
- Live execution warning.

Structuur:

- Severity: info / caution / high risk.
- What happened.
- Why it matters.
- What not to do.
- Safe next step.

CTA's:

- Ask assistant.
- View detail.
- Skip action.
- Adjust risk profile.

### Strategy Cards

Strategy cards tonen het plan, niet de hele analyse.

Structuur:

- Asset and bias.
- Confidence.
- Entry zone.
- Targets.
- Invalidation/stop.
- Current status: valid / waiting / invalidated.
- AI explanation.
- CTA: View detail / Ask why / Create adjustment draft.

### Bot Action Cards

Bot action cards zijn de hoogste aandacht in mobile.

Structuur:

- Bot name.
- Proposed action: buy / sell / hold / skip.
- Confidence.
- Amount or no amount.
- Guardrail status.
- Top reasons.
- Risk note.
- Buttons: Confirm status, Skip, Mark executed, Ask why.

Voor live trading moet extra friction gelden:

- Confirm sheet.
- Explicit "paper/live" badge.
- Consequence summary.
- No accidental one-tap execution.

### Tone

De assistant tone:

- Rustig.
- Direct.
- Professioneel.
- Menselijk.
- Niet hypey.
- Geen overdreven zekerheid.
- Geen casino-taal.

Voorbeelden:

- Goed: "De setup is nog geldig, maar de entry is niet schoon genoeg."
- Goed: "Mijn advies: wacht op bevestiging of verklein de positie."
- Fout: "Sterk koopsignaal! Pak deze kans."

### Pacing

Mobile assistant responses moeten korter zijn dan desktop:

- Eerste antwoord: 2-4 zinnen.
- Daarna cards voor details.
- "Waarom?" als optionele verdieping.
- Bij risico: eerst waarschuwing, daarna uitleg.

### Hierarchie

Elke assistant output volgt:

1. Conclusie.
2. Reden.
3. Risico.
4. Volgende stap.

Niet:

1. Lange analyse.
2. Veel scores.
3. Daarna pas conclusie.

### Interaction Patterns

Belangrijkste patronen:

- Tap card -> detail sheet.
- Long press card -> copy/debug/share later.
- Swipe down sheet -> dismiss.
- Pull feed -> refresh insight.
- Tap suggestion -> sends prompt.
- Draft confirm -> bottom confirmation.
- Risk card -> ask assistant why.

## 5. Today Experience

### Doel Van Today

Today is de dagelijkse intelligence snapshot. Het is geen dashboardtab met alles. Het is het antwoord op:

> Wat moet ik nu weten voordat ik iets doe?

### Structuur

Aanbevolen volgorde:

1. Header with active asset and last updated.
2. Master decision state.
3. What Matters Now.
4. Active Recommendation.
5. Score stack.
6. Market snapshot.
7. Active setup/strategy preview.
8. Latest report insight.
9. Ask assistant CTA.

### Header

Bevat:

- Active asset selector.
- Timestamp.
- Data freshness indicator.
- Small status chip: live / stale / syncing.

### Master Decision State

Geen abstracte gauge zonder betekenis. Gebruik een status:

- `Risk-on, selective`
- `Neutral, wait for confirmation`
- `Risk-off`
- `Setup valid, entry pending`
- `Strategy invalidated`

Met master score als ondersteuning, niet als enige focus.

### What Matters Now

Een korte lijst van maximaal 3 punten:

- Grootste positieve factor.
- Grootste risico.
- Wat de gebruiker vandaag moet monitoren.

Voorbeeld:

- Market appetite improves.
- Entry zone is close to resistance.
- Wait for technical confirmation before increasing size.

### Score Visualisatie

Gebruik vier compacte domain cards:

- Macro.
- Market.
- Technical.
- Setup.

Elke card toont:

- Score.
- Direction/trend.
- One-line interpretation.
- Tap for detail.

Geen grote complexe charts op de eerste viewport. Scoregeschiedenis kan als mini sparkline of detail sheet.

### Market Snapshot

Toon alleen:

- Price.
- 24h change.
- Volume/volatility indicator indien betrouwbaar.
- Last updated.
- One interpretation.

Market snapshot is bewijs, geen command center.

### AI Samenvatting

AI summary staat na score/context, zodat het niet als losse mening voelt.

Structuur:

- "Mijn lezing"
- "Waarom"
- "Wat ik zou vermijden"

### Active Recommendation

Recommendation card:

- Primary recommendation: wait / monitor / review bot / reduce risk / confirm draft.
- Confidence.
- Reason.
- CTA.

Belangrijk: aanbeveling mag ook "niets doen" zijn. Dat is productwaarde.

## 6. Action/Strategy Experience

### Doel Van Action

Action is het scherm voor beslissingen die mogelijk vandaag relevant zijn.

Het antwoordt op:

- Is mijn setup actief?
- Is mijn strategie geldig?
- Wat adviseert de bot?
- Wat is het risico?
- Moet ik iets doen of overslaan?

### Actieve Setup

Active setup card:

- Setup name.
- Asset.
- Type: DCA / trade.
- Timeframe.
- Active/inactive.
- Match score.
- Condition summary.
- CTA: "Vraag waarom" / "Bekijk regels".

Niet alle thresholds direct tonen. Toon alleen detail op tap.

### Strategy Confidence

Strategy card:

- Confidence score.
- Bias.
- Entry zone.
- Targets.
- Stop/invalidation.
- Current market relation to entry.
- Status: waiting / valid / invalidated / completed.

Confidence moet altijd gepaard gaan met reden en onzekerheid.

### Invalidation

Invalidation verdient een eigen UX-behandeling.

Als strategie invalidated:

- Toon rode/caution status, niet alleen lage score.
- Leg uit welk niveau of signaal brak.
- Toon wat niet te doen.
- Bied acties:
  - Ask assistant.
  - Create adjustment draft.
  - Mark strategy inactive.
  - Open desktop for full review.

### Bot Recommendation

Bot recommendation card:

- Action.
- Confidence.
- Requested amount.
- Final amount after guardrails.
- Guardrail result.
- Reasons.
- Trade plan summary.

Hold/skip is net zo belangrijk als buy/sell. Gebruik niet alleen groene states voor actie; "wait" moet ook professioneel en waardevol voelen.

### Risk Explanation

Risk explanation is een sheet:

- Top risk.
- Why it matters.
- Related score(s).
- Portfolio exposure.
- Strategy invalidation.
- Safe alternative.

De sheet moet snel scanbaar zijn en eindigen met een duidelijke keuze.

### Execution Confirmation UX

Voor bevestiging:

1. User taps action.
2. Confirmation sheet opens.
3. Show summary:
   - What will happen.
   - Paper or live.
   - Amount.
   - Risk.
   - Reversibility.
4. User confirms with explicit button.
5. Haptic feedback.
6. Assistant feed receives completion message.

Voor high-risk/live:

- Extra confirmation copy.
- Geen default-positive styling.
- Button label concreet: `Markeer als uitgevoerd`, `Sla botactie over`, `Maak paper bot`.

## 7. Workspace Filosofie

### Wat In Workspace Hoort

Workspace bevat alles wat de gebruiker af en toe moet inspecteren of licht beheren:

- Watchlist.
- Assets.
- Setup summaries.
- Strategy summaries.
- Bot summaries.
- Report summaries.
- Preferences shortcuts.
- Desktop handoff links.

Workspace is georganiseerd per object, niet per data-domein.

### Wat Niet In Workspace Hoort

Niet in mobile workspace:

- Volledige indicator rule editors.
- Grote historical score tables.
- Complexe chart workbench.
- Backtest studio.
- Admin.
- Multi-panel bot configuration.
- PDF report export.
- Bulk operations.

### Workspace vs Assistant

Assistant:

- Interpreteert.
- Begeleidt.
- Start flows.
- Maakt drafts.
- Sluit loops.

Workspace:

- Toont objecten.
- Laat inspectie toe.
- Laat eenvoudige wijzigingen toe.
- Geeft toegang tot desktop voor complex werk.

Regel:

> Assistant is de laag die begrijpt. Workspace is de laag waar objecten wonen.

### Desktop en Mobile Samen

Desktop:

- Deep analysis.
- Configuration.
- Backtests.
- Full charts.
- Admin.
- Complex strategy/bot setup.

Mobile:

- Daily briefing.
- Assistant.
- Alerts.
- Review.
- Confirm/skip.
- Light edits.

Desktop handoff:

- Mobile toont "Open op desktop voor volledige configuratie".
- Drafts kunnen op mobile worden gestart en later op desktop verdiept.
- Reports kunnen op mobile gelezen worden, desktop exporteert.

## 8. Design System Richting

### Typography

Richting:

- Premium fintech, compact maar ademend.
- Grote display type alleen voor hoofdstatus of tab title.
- Cards gebruiken middelgrote headings.
- Body text 15-16px equivalent.
- Labels klein, uppercase, spaarzaam.
- Geen negatieve letter spacing.

Hierarchie:

- Screen title: 28-34.
- Primary status: 22-28.
- Card title: 16-19.
- Body: 15-16.
- Metadata: 11-13.

### Spacing

Spacing moet rust scheppen:

- Screen horizontal padding: 16-20.
- Card padding: 16-20.
- Card gap: 12-16.
- Section gap: 20-28.
- Bottom safe padding ruim houden boven tab bar.

Geen dichtgetimmerde trading terminal. Compacte informatie, maar met duidelijke ritmes.

### Card Hierarchy

Card levels:

- Level 1: primary decision card, sterkste visuele focus.
- Level 2: supporting insight cards.
- Level 3: detail/metadata cards.
- Inline chips: status, freshness, risk, confidence.

Gebruik kaarten voor beslissingsobjecten, niet voor elke losse metric.

### Animations

Animaties zijn functioneel:

- Streaming text: subtiel.
- Card entrance: korte fade/slide.
- State change: haptic + small transition.
- Pull refresh: native.
- Confirmation success: compact feedback.

Geen speelse of nerveuze motion. Trading UX moet stabiel aanvoelen.

### Transitions

Gebruik:

- Bottom sheet slide.
- Tab transition zonder dramatiek.
- Card expand naar detail sheet.
- Assistant quick prompt insertion.

Vermijd:

- Lange page transitions.
- Overdreven spring motion.
- Constant pulserende visuals.

### Dark Mode Filosofie

Dark mode mag premium en rustig zijn, maar niet zwaar en somber.

Richting:

- Donkere achtergrond.
- Iets lichtere elevated surfaces.
- Hoge leesbaarheid.
- Accentkleur beperkt gebruiken.
- Risk colors duidelijk maar niet schreeuwerig.

Donkerblauw/slate mag niet de hele identiteit domineren. Gebruik neutrale surfaces, rustige accentkleur, subtiele statuskleuren.

### Fintech Uitstraling

Visueel gevoel:

- Institutioneel.
- Precies.
- Veilig.
- Modern.
- Niet flashy.

Trading apps voelen vaak druk. Tradamind moet voelen als een research desk in je hand.

### Rust vs Informatie

Elke viewport heeft maximaal:

- 1 primaire conclusie.
- 1 primaire actie.
- 2-4 ondersteunende datapunten.
- 1 optionele verdieping.

Als er meer nodig is, gebruik detail sheets.

## 9. Native Mobile Gedrag

### Gestures

Gebruik native patronen:

- Pull-to-refresh op Assistant, Today en Action.
- Swipe down to dismiss sheets.
- Horizontal chips voor assets/watchlist.
- Tap card to inspect.
- Long press voor secondary utility later.

Niet gebruiken:

- Swipe actions voor high-risk trading actions.
- Hidden gestures voor belangrijke flows.

### Pull-To-Refresh

Refresh moet contextueel zijn:

- Assistant: refresh insight/briefing.
- Today: refresh scores, market snapshot, recommendation.
- Action: refresh bot decision, strategy validity, setup state.

Toon laatste update en stale state.

### Loading Skeletons

Gebruik skeletons die lijken op echte cards:

- Briefing skeleton.
- Score stack skeleton.
- Bot action skeleton.
- Strategy skeleton.

Geen full-screen spinner behalve bij auth of eerste cold start.

### Haptics

Haptics:

- Light selection bij tab/sheet/action tap.
- Medium bij confirmed action.
- Warning haptic bij high-risk warning.
- Success haptic bij saved draft/marked executed.

Niet bij elke streaming token of kleine UI update.

### Push Interactions

Push tap opent altijd context:

- Alert -> relevant card/detail.
- Daarna assistant prompt klaarzetten: "Leg dit uit".

Push copy moet kalm zijn:

- Goed: "BTC strategy needs review. Entry condition weakened."
- Fout: "BTC moving fast! Act now."

### Keyboard Behavior

Assistant composer:

- Keyboard avoiding behavior correct voor iOS/Android.
- Composer blijft zichtbaar.
- Send button disabled bij lege tekst.
- Suggested prompts verdwijnen of worden compact boven keyboard.
- Multiline input max hoogte.

Na submit:

- Keyboard mag open blijven bij gesprek.
- Bij action/draft cards mag keyboard sluiten om reviewruimte te geven.

### Safe Area Behavior

Respecteer:

- Dynamic Island/notch.
- Bottom home indicator.
- Tab bar safe area.
- Keyboard safe area.

Primary CTA's mogen nooit onder home indicator of tab bar verdwijnen.

### Scroll Gedrag

Assistant:

- Nieuwe message scrollt naar beneden.
- Bij active flow blijft state card bereikbaar bovenaan.
- Als user omhoog scrolt, niet agressief terugduwen.
- Toon "new response" anchor indien nodig.

Today/Action:

- Start altijd bovenaan bij nieuwe app open.
- Pull refresh bovenaan.
- Detail via sheets om scroll stack niet te verliezen.

## 10. UX Anti-Patterns

### Wat Tradamind Mobile Niet Mag Worden

Niet:

- Een verkleinde desktopdashboard.
- Een crypto exchange clone.
- Een chart-first app.
- Een AI-chat zonder actiekaarten.
- Een notificatiegedreven FOMO-machine.
- Een app met tien tabs en tientallen metrics.

### Fouten Van Trading Apps

Vermijden:

- Grote buy/sell knoppen zonder context.
- Felgroene en felrode emotional design.
- Pushmeldingen die urgentie forceren.
- Price movement als hoofdverhaal.
- Elke metric even belangrijk maken.
- User naar trade duwen bij lage confidence.

### Dashboard Overload

Mobile mag niet proberen te tonen:

- Alle scores tegelijk met history, tabellen en charts.
- Macro, market, technical als aparte volledige dashboards.
- Meer dan 3-4 cards boven de fold.
- Een chart als standaard startpunt.

### Tabellen-Chaos

Tabellen zijn desktopmateriaal. Op mobile:

- Transformeer tabellen naar cards.
- Toon top contributors.
- Geef filters via sheets.
- Link naar desktop voor volledige details.

### Teveel Metrics

Metrics zonder besluitcontext zijn ruis.

Elke metric moet een label krijgen:

- Supports action.
- Blocks action.
- Neutral.
- Needs attention.
- Stale.

### Agressieve Trading UX

Verboden productgevoel:

- "Buy now".
- "Opportunity".
- "Don't miss".
- Casino-achtige kleur/motion.
- One-tap live execution.
- AI die certainty claimt.

Tradamind moet professioneel vertragen wanneer risico stijgt.

## 11. Aanbevolen Bouwvolgorde

### Stap 1: UX Foundation

Bouw eerst:

- Navigation shell met tabs: Assistant, Today, Action, Workspace, Profile.
- Shared card system.
- Status chips.
- Bottom sheet component.
- Loading skeletons.
- Error/stale state patterns.
- Active asset context header.

Zonder deze basis wordt elke flow inconsistent.

### Stap 2: Assistant Envelope UX

Fundamenteel:

- Chat message rendering.
- Briefing card.
- Action card.
- Draft review card.
- Warning/risk card.
- State progress card.
- Suggested prompt chips.

Valideer eerst dat backend envelopes goed in mobile UI passen.

### Stap 3: Today MVP

Bouw:

- Master decision state.
- What Matters Now.
- Four domain score cards.
- Market snapshot.
- Active recommendation.
- Ask assistant CTA.

Valideer:

- Begrijpt user binnen 5 seconden de status?
- Is "niets doen" een waardevolle uitkomst?
- Is de assistant de natuurlijke volgende stap?

### Stap 4: Action MVP

Bouw:

- Active setup card.
- Active strategy card.
- Bot decision card.
- Risk explanation sheet.
- Skip/mark executed confirmations.
- Ask why from every action card.

Valideer:

- Begrijpt user waarom actie wel/niet verstandig is?
- Voelt confirmation veilig?
- Keert de flow logisch terug naar assistant?

### Stap 5: Draft Confirmation Flows

Bouw:

- Setup draft review.
- Strategy draft review.
- Bot draft review.
- Confirm/edit/cancel.
- Assistant completion message.

Valideer:

- Kan de user een assistant-created draft vertrouwen?
- Zijn assumed values zichtbaar?
- Is edit licht genoeg voor mobile?

### Stap 6: Push en Deep Links

Bouw:

- Push permission UX.
- Notification categories.
- Deep link routing naar Assistant/Today/Action/detail sheets.
- "Ask why" prompt prefill.

Valideer:

- Push voelt adviserend, niet opdringerig.
- Deep links openen context, geen losse schermen.

### Stap 7: Workspace en Desktop Handoff

Bouw:

- Watchlist workspace.
- Setup/strategy/bot summaries.
- Report summaries.
- Desktop handoff affordances.

Valideer:

- Workspace ondersteunt assistant, maar concurreert er niet mee.
- Complexe flows blijven desktop-first.

## Componenten Die Fundamenteel Zijn

Essentiele componenten:

- `AssistantBriefingCard`
- `AssistantMessage`
- `InsightCard`
- `ActionCard`
- `DraftReviewCard`
- `RiskWarningCard`
- `ScoreDomainCard`
- `MasterDecisionCard`
- `MarketSnapshotCard`
- `StrategyStatusCard`
- `BotDecisionCard`
- `BottomSheet`
- `ConfirmActionSheet`
- `AssetContextHeader`
- `SuggestedPromptChips`
- `DataFreshnessIndicator`
- `LoadingSkeletonCard`

Deze componenten vormen samen de mobile operating system laag.

## UX Succescriteria

Tradamind Mobile werkt als:

- De gebruiker de app opent en binnen 5 seconden weet wat relevant is.
- De assistant vaker startpunt dan bijzaak is.
- Cards actie mogelijk maken zonder analyse-overload.
- De app ook waarde levert wanneer het advies "wachten" is.
- Risk explanations helder genoeg zijn om impuls te remmen.
- Drafts betrouwbaar aanvoelen maar nooit automatisch worden uitgevoerd.
- Desktop en mobile elkaar versterken in plaats van dupliceren.

## Slotprincipe

Tradamind Mobile moet voelen als een kalme AI trading chief of staff:

- Hij leest de markt.
- Hij kent je strategie.
- Hij bewaakt je risico.
- Hij maakt concepten klaar.
- Hij laat jou bewust bevestigen.

De assistant is de operating layer. De schermen zijn werkruimtes. De actie is altijd geïnformeerd.
