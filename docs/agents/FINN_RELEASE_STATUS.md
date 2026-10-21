# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Recente gesloten Paper-trade zonder reviewnummer — herstelkandidaat (21 oktober 2026)

Phase: `DEPLOYED_AWAITING_INDEPENDENT_QA`. De onafhankelijke herkeuring
[39556895361](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39556895361)
op `0e5d797534d36db4dc9e431d6a02eb46d9da59fa` eindigde `NOT_ACCEPTED`.
De eerste gewone FINN-chatbeurt werd voltooid, maar het antwoord bevatte geen
geverifieerd `review_history`-bewijs (`closed_paper_review_chat_evidence_missing`);
de lesvervolgvraag werd niet begonnen. Het gesaniteerde artifact heeft SHA-256
`c8fe44a7e1d9da68b07a5120727b46bbc54859c60fba049a8fda7865b3f7a8c7`.
Het artifact toont geen tool-call-status voor die beurt; of de tool werkelijk
is aangeroepen en wat de exacte prompt was, is daaruit niet vast te stellen.
Twee begonnen Paper-uitvoeringsstappen bewijzen geen afzonderlijke fills;
Live-aanroepen en -activaties waren nul.

De vorige fix verplichtte de dossierlezing bij een expliciet reviewnummer.
Deze kandidaat dekt ook gewone verwijzingen naar een gesloten of laatste
Paper-trade zonder nummer: de bestaande eigenaargebonden recente-dossierlezing
wordt dan vereist. Mutatieverzoeken zijn uitgesloten. Gerichte tests voor
Nederlandse en Engelse formuleringen en de mutatiegrens slagen. De lokale
synthetische echte Luna/Responses-proef leest bij een gewone vraag zonder
nummer de getypeerde review, noemt het bewezen EUR-resultaat en voltooit de
lesvervolgvraag zonder voorstel: vijf eerste beurten en vijf vervolgbeurten
waren voltooid, telkens met dossierlezing. De volledige backend-suite slaagde
met **3645 tests, vier bestaande skips**. Security vond in deze verbrede
read-only route geen eigenaar-, actie- of prompt-injectionblokker; dit is
geen acceptatieclaim. Webbuild, typecheck, i18n-lint, i18n-, command-,
voorstel- en setuptests en `audit:high` slaagden; de audit meldt één
moderate advisory en geen high of critical.
De echte Responses-ontwikkelset slaagde met **20/20** operatie- en
veldmatches en nul provider-, schema-, parse- of validatiefouten (artifact
SHA-256 `04e5b1644a0975207259c7537b7e9a8ef509f7193d3a679d221949f38a047163`).
De geïsoleerde lokale workeractiecontractmatrix sloot **16/16** contracten af,
met nul brokerorders, Live-aanroepen of productieverbindingen; adaptertests
**19/19**. Matrixartifact SHA-256:
`f3c129a2d140f41448d780c21fb4e833c789836cd71b454b96e282e584e0a332`.
De echte Responses-regressie slaagde met **109/109** operatie- en veldmatches
en nul provider-, schema-, parse- of validatiefouten (artifact SHA-256
`9069d86e054232c17db9d91a721e52b80031f6db5108a7c34b0734a8b71290d4`).
De wijziging is via [PR #505](https://github.com/gvangalen/antigravity-trading-tool/pull/505)
gemerged als `47ba1860f19fdde66e476bb5994bdb1d16c98297`. De vijf PR-CI-
en vijf [main-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39559315743)
slaagden. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39559612769)
slaagde. Publieke backend-health en frontend-buildinfo gaven daarna beide
HTTP 200 en exact deze merge-SHA. Onafhankelijke ingelogde live QA staat nog
open; dit is geen acceptatieclaim. Een latere status-only documentcommit kan
de publieke SHA veranderen; QA bindt aan de dan actuele, gelijke backend- en
frontend-SHA.

## Gewone vraag over gesloten Paper-review — herstelkandidaat (21 oktober 2026)

Phase: `DEPLOYED_AWAITING_INDEPENDENT_QA`. De onafhankelijke beschermde herkeuring
[39553606527](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39553606527)
op `c96216cb2977d639e87a9be80c7a0ea074284d34` eindigde `NOT_ACCEPTED`.
De eerste gewone FINN-chatbeurt werd wel voltooid, maar riep de eigenaargebonden
dossierlezing niet aan (`closed_paper_review_chat_evidence_missing`); de
lesvervolgvraag werd niet begonnen. De twee Paper-uitvoeringsstappen in dat
rapport zijn geen bewijs voor gesloten fills. Het gesaniteerde artifact heeft
SHA-256 `d8e3ca0cd67500e15fbd3f2931afffd9cbfe169ab4ab253a8275af52395de2c8`.

De oorzaak is dat een expliciet reviewnummer alleen een verplichte lezing
veroorzaakte wanneer de zin met een leeswerkwoord begon. De herstelkandidaat
herkent ook gewone vragen met dat nummer. Mutatieverzoeken blijven uitgesloten
en de tool leest uitsluitend het dossier van de ingelogde eigenaar. Drie
formuleringsvarianten zijn aan de gerichte regressie toegevoegd. De volledige
backend-suite slaagde lokaal: **3641 tests, vier bestaande skips**. Een echte
Luna/Responses-proef voltooide vijf gewone reviewvragen en vijf lesvervolgvragen;
iedere beurt las hetzelfde synthetische eigenaargebonden dossier en eindigde
zonder voorstel. Security vond geen eigenaar- of actiegrensprobleem. De
geïsoleerde lokale workeractiecontractmatrix sloot **16/16** contracten af,
met nul brokerorders, Live-aanroepen of productieverbindingen; adaptertests
**19/19**. Matrixartifact SHA-256:
`cf4e957667bfd51127db2ece0dfd27f93ab2c6d9e78b4e6bc3735fd0ed668aa9`.
De echte Responses-ontwikkelset slaagde met **20/20** operatie- en
veldmatches, zonder provider-, schema-, parse- of validatiefout (artifact
SHA-256 `1dd67a9229e2177f4f2cbf886328af6f4ee0b20ab1a6081318f18654004786b6`).
De webbuild, typecheck, i18n-lint, i18n-, command-, voorstel- en setuptests
en `audit:high` slaagden; de audit meldt één moderate advisory en geen high
of critical. De echte Responses-regressie slaagde met **109/109** operatie-
en veldmatches en nul provider-, schema-, parse- of validatiefouten
(artifact SHA-256
`ae66364e4f4306139cf7515daf398e37fd9fdfa5b381d9f8ddf8daaa967fd7e0`).
De wijziging is via [PR #503](https://github.com/gvangalen/antigravity-trading-tool/pull/503)
gemerged als `8d9838f4efabcb4257407f1bf36285c9730e4e96`. De vijf PR-CI- en
vijf [main-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39555504784)
slaagden. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39555768540)
slaagde. Publieke backend-health en frontend-buildinfo gaven daarna beide
HTTP 200 en exact deze merge-SHA. Onafhankelijke ingelogde live QA staat nog
open; dit is geen acceptatieclaim. Een latere status-only documentcommit kan
de publieke SHA veranderen; QA bindt aan de dan actuele, gelijke backend- en
frontend-SHA.

## Gesloten Paper-review in gewone FINN-chat — kandidaat (21 oktober 2026)

Phase: `DEPLOYED_AWAITING_INDEPENDENT_QA`. De kandidaat is gemerged via
[PR #501](https://github.com/gvangalen/antigravity-trading-tool/pull/501) als
`cf22e0ca6e08d88d79302221167fb78fc1cd5eb2`. Alle vijf
[PR-CI-jobs](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39551624366)
en vijf [main-CI-jobs](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39551927426)
slaagden. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39552583451)
slaagde. Publieke backend-health en frontend-buildinfo gaven daarna beide
HTTP 200 en exact die merge-SHA. Een latere status-only documentcommit kan
de publieke SHA opnieuw veranderen; onafhankelijke QA bindt aan de dan
actuele, gelijke backend- en frontend-SHA. De voorafgaande onafhankelijke QA-run
[39548142176](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39548142176)
op die SHA eindigde `NOT_ACCEPTED`: de eigenaargebonden `get_closed_trade_review`
was voltooid, maar de eerste gewone FINN-chatbeurt eindigde `unavailable` met
`responses_evidence_not_verified`; de lesvervolgvraag werd niet bereikt. Het
gesaniteerde artifact heeft SHA-256
`51be2951ca5b1fb5241de7e30dc90f6c78ff06d0d2f174124b1b3ced375ccb44`.

Lokaal is de oorzaak gereproduceerd: Luna/Responses las het dossier en gaf
vijfmaal een inhoudelijk eerste antwoord, maar de eigen antwoordcontrole
verwierp het bewezen EUR-resultaat omdat het eigenaargebonden `pnl_eur` als
decimale tekst wordt aangeleverd. Deze kandidaat geeft de bevestigde les
apart en getypeerd door, gemarkeerd als gebruikersreflectie in plaats van
oorspronkelijk plan of bewezen tradefeit. De verifier bindt een genoemd
resultaat aan exact review-ID, EUR-bedrag en teken; een bedrag uit de vraag,
een andere review of valuta kan dat niet vervangen. De definitieve lokale
Luna/Responses-proef voltooide vijf eerste beurten en vijf lesvervolgvragen,
alle met dezelfde eigenaargebonden dossierlezing en zonder voorstel.

Op de definitieve code slaagde de volledige backend-suite: **3639 geslaagd,
vier bestaande skips**. Webbuild, typecheck, i18n-/command-/voorstel-/setuptests,
i18n-lint en `audit:high` slaagden; de audit meldt één moderate advisory,
geen high of critical. De geïsoleerde workeractiecontractmatrix sloot
**16/16** contracten af en de adaptertests **19/19**, met nul brokerorders,
Live-aanroepen en productieverbindingen; artifact SHA-256
`dbec6a48d2d982a7934e7574b8d8a94799dce7009e141d5eedbc0602f5e7c285`.
De echte selector-developmentset slaagde **20/20** (artifact SHA-256
`b2a42f26f6a7d6f5d4cb333fa3f1fac2be2473adebecfb77c279fcec33f3a63f`)
en de regressieset **109/109**, operatienauwkeurigheid 1,0 (artifact SHA-256
`62a9174ee5a168c482a7d0eb668261033357cbc7166a0ccc142b0a90f9636f5d`).
Security en Architecture vonden na onafhankelijke herbeoordeling geen concrete
blocker. Dit is lokale validatie; de beschermde QA-fixture en onafhankelijke
live acceptatie blijven bij de bestaande QA-agent.

## Gesloten Paper-trade → FINN-chat (21 oktober 2026)

De diagnose-only [PR #498](https://github.com/gvangalen/antigravity-trading-tool/pull/498)
is inmiddels gemerged en gedeployed als `2c2aca3c39a9555a0c6c1d2806e789194a706e3f`.
PR-/main-CI en Auto Deploy slaagden; publieke backend en frontend gaven HTTP
200 en deze SHA. De bestaande onafhankelijke QA-agent herhaalde het beschermde
profiel in [run 39544803635](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39544803635).
Uitkomst: `NOT_ACCEPTED`. Het profiel stopte met de gesaniteerde categorie
`closed_paper_review_chat_runtime_error` vóór een terminale chatdiagnose;
de foutfase en de eerste chatbeurt zijn dus niet vastgesteld. Het rapport
meldt twee beoogde Paper-executies, maar die telling wordt vóór de fixture
gezet en bewijst op zichzelf niet dat beide fills plaatsvonden. Er zijn nul
Live-aanroepen geregistreerd. Artifact SHA-256
`f9ed9a7df978f69870d119cd177c97a1f0916619caefcfff9e485f467ac6aeb5`.
De [PR #499](https://github.com/gvangalen/antigravity-trading-tool/pull/499)
is gemerged als `e1fb54e64cbe8b6694888fe6f705fe7f361f9f35` en voegt een vaste,
gesaniteerde fasecode aan dit beschermde foutpad toe, zodat de volgende
onafhankelijke run de breuk kan lokaliseren. Hij verandert geen productantwoord,
actiecontract, Paper-uitvoering of gebruikersgegevens. De chat-QA-uitkomst
telt voortaan alleen daadwerkelijk begonnen Paper-uitvoeringsstappen; een
vroege fixturefout mag niet langer als twee calls worden gelezen. De 93 gerichte
QA-runnertests en de volledige backend-suite (**3613 geslaagd, vier bestaande
skips**) slaagden op de definitieve code. De frontendbuild, typecheck,
i18n-/command-/voorsteltests en `audit:high` slaagden; de audit meldt één
moderate advisory, geen high of critical. De echte Luna/Responses-selectorproeven
slaagden: development **20/20** (artifact SHA-256
`e7f37752090cf132a10744b6a4f897d73e298d3ede1d9c9b7b426bef9def2d59`)
en regression **109/109** (SHA-256
`130a13e936dbc564a4b4aeac4c5aee0533dce92f66bc01de0aa3992948f21263`).
De geïsoleerde lokale workeractiecontractmatrix sloot **16/16** contracten af,
met nul brokerorders, Live-aanroepen of productieverbindingen; adaptertests
**19/19**. Matrixartifact SHA-256
`eed859453f3b623f6216be53362dea75fe8958e5890290454cc012f643604663`.
Security en Architecture vonden na herstel van de cleanup-fout en de
uitvoeringsteller geen resterende blocker. Alle vijf
[PR-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39546716179)
en vijf [main-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39546943352)
slaagden. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39547151751)
slaagde; publieke backend-health en frontend-buildinfo gaven beide HTTP 200
en exact `e1fb54e64cbe8b6694888fe6f705fe7f361f9f35`. Onafhankelijke live
QA op deze kandidaat staat nog open; lokale en publieke controles zijn geen
vervanging daarvoor. Een status-only documentcommit kan de publieke SHA
veranderen; QA bindt aan de dan actuele, gelijke backend- en frontend-SHA.

De daaropvolgende [PR #497](https://github.com/gvangalen/antigravity-trading-tool/pull/497)
is gemerged als `6237191d5c9c8400fcec7d9ed7110c1450ec8582`.
Alle vijf PR- en [main-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39542618819)
en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39542822078)
slaagden. Publieke backend-health en frontend-buildinfo gaven ieder HTTP 200
en exact die SHA. De onafhankelijke QA-agent deed één beschermde
[herproef](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39543046850):
`NOT_ACCEPTED`. De eerste chatbeurt eindigde `unavailable`, met aanwezige
response en veilige foutcategorie `other`; de reviewlezing en tweede beurt
zijn daardoor niet bewezen. Er waren twee gecontroleerde Paper-executies en
nul Live-aanroepen. Gesaniteerd artifact SHA-256
`865b0abeb645db3f09f8cb13fe9105b0eae9e63e659f232c120a7b0f6013cc58`.
De lokale diagnosekandidaat `codex/finn-review-chat-terminal-diagnostics`
voegt uitsluitend begrensde terminal- en read-toolstatussen toe aan het
beschermde QA-artifact. Zij leest de private Responses-checkpoint voor exact
de eigenaar, conversatie en run, maar exporteert geen dossierinhoud, ID of
modeltekst. De gerichte runnertests slagen **91/91** en de volledige
backend-suite **3611 geslaagd, vier bestaande skips**. Dit is nog geen
inhoudelijke reparatie of nieuw live verdict.

Laatste onafhankelijke QA op live `c4ba576a1eb42d240dad6525391bcd0ff1cb4567`:
[run 39540408664](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39540408664)
eindigde `NOT_ACCEPTED`. De eerste gewone FINN-chatbeurt werd nu voltooid,
maar gebruikte geen `review_history`-bewijs bij een expliciet genoemd
trade-reviewnummer. De tweede beurt werd niet uitgevoerd. Twee Paper-executies,
nul Live-aanroepen. Gesaniteerd artifact SHA-256
`b888036b82bd7795431c3e7a867bb6a1054fd801da426974b8bd751af8384349`.
De huidige lokale kandidaat `codex/finn-review-read-routing` maakt bij een
expliciete alleen-lezen vraag naar review `#N` de bestaande eigenaargebonden
dossierlezing verplicht voordat FINN antwoordt. Een bevestigde les blijft
gebruikerscontext, geen bevestigingsopdracht. De vervolgbeurt herleest precies
dat ene dossier op basis van een eerder voltooid, eigenaar- en gesprekgebonden
antwoord. Security en Architecture vonden geen blocker. De volledige
backend-suite slaagde **3610 tests, vier bestaande skips**; webbuild,
typecheck, i18n- en command-/voorsteltests slaagden. De echte
Luna/Responses-developmentset slaagde **20/20** (artifact SHA-256
`48e907f63d29893e6880d60216e5786dc2afe1e4b830f508e55714e0fcb9b66c`),
de echte regressieset **109/109** (SHA-256
`d28c2132990477ea6b143c2981d89dd027b87eedb1e3b907991f7764e9656d7e`),
beide met operatienauwkeurigheid 1,0. De geïsoleerde workeractiecontractmatrix
slaagde op de definitieve code **16/16**, met **19/19** adaptertests; artifact
SHA-256 `a11b08d5b211b6205bc5cb3bc44ef95dc9daf1924f56eece96258668ced0f0be`.
Een afzonderlijke echte Luna/Responses-proef met de
exacte eerste reviewvraag leverde één voltooide `get_closed_trade_review`-lezing,
een inhoudelijk antwoord en nul voorstellen op (synthetisch lokaal dossier,
geen claim over de productie-eigenaar). Onafhankelijke live QA volgt pas na
deployment.

Phase: `QA_NOT_ACCEPTED` voor de chatuitbreiding; laatste geteste productie-SHA
`6237191d5c9c8400fcec7d9ed7110c1450ec8582`. De eerste kandidaat was
`495873bec102f0368cddd69c1d286d339fe81530`. [PR #494](https://github.com/gvangalen/antigravity-trading-tool/pull/494)
is gemerged; alle vijf PR- en main-CI-controles en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39537460230)
slaagden. Backend-health en frontend-buildinfo gaven HTTP 200 en dezelfde SHA.
De bestaande QA-agent startte één beschermde [proef](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39537761284).
Die bereikte de eerste gewone FINN V2-chatbeurt na twee gecontroleerde
Paper-executies en het dossier, maar er kwam geen voltooide chatresponse.
Veilige foutcode: `closed_paper_review_chat_first_turn_failed`; de tweede beurt
werd niet uitgevoerd. Nul Live-aanroepen of Live-botactivaties. Het gesaniteerde
artifact heeft SHA-256
`00cf608302f42c09ce3f14f983e5b9062394efdb2916b2388fdb7a79da59a6e4`.
De terminale status en typed backendfout ontbreken in die versie van het
artifact; de precieze oorzaak is dus nog niet vastgesteld.

Een nieuwe lokale diagnosekandidaat op `codex/finn-paper-review-chat-diagnostics`
voegt uitsluitend een gesaniteerde terminalcategorie, toegestane foutcode en
`response_present` toe bij een mislukte beurt. De 90 gerichte runnertests
en de volledige backend-suite (3605 geslaagd, vier bestaande skips) slagen.
Security vond geen blootstelling van fixture- of providerdata. Deze kandidaat
is via [PR #495](https://github.com/gvangalen/antigravity-trading-tool/pull/495)
gemerged en gedeployed op `627025d79ef65be0120fff8ed4133b95ed5951bc`.
Backend en frontend gaven HTTP 200 en die SHA; alle PR- en main-CI-controles
en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39538972113)
slaagden. Dezelfde onafhankelijke QA-agent deed één beschermde
[herproef](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39539181259):
`NOT_ACCEPTED`; eerste FINN-beurt `unavailable`, `response_present=true`,
maar `typed_error_code=other`. De tweede beurt bleef ongetest. Het artifact
heeft SHA-256
`02d0414e7bc3b49ed404140e59d67d4ebd03ef3a67d343aa7ec45f803652a7c4`.
De beschikbare QA-workflowlogs geven geen nauwkeuriger veilige foutcode.
De volgende lokale kandidaat verbreedt uitsluitend de expliciete lijst van
statische Responses-foutcodes voor dit gesaniteerde diagnoseveld; de fout is
nog niet inhoudelijk gerepareerd. Gerichte runnertests **90/90**, volledige
backend-suite **3605 geslaagd, vier bestaande skips**. Security vond geen
privétekst-lek of wijziging van een actiegrens.

De onafhankelijke QA-agent bevestigde de voorafgaande gesloten Paper-tradereview op
`fd9642afac6eb128eba7818a2f42af111030bb8d` via de beschermde
[QA-run](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39522742378):
twee Paper-fills werden precies één eigenaargebonden gesloten dossier, met
opgeslagen FINN-analyse en een later teruggelezen bevestigde les. Er waren
nul Live-aanroepen. Het gesaniteerde artifact had SHA-256
`94964ed2439b073cb5dc3cb7591fc1091af45804599e24977c99440a673029c5`.
Dat verdict bewees nog geen gewone FINN-chat over dezelfde les. Een latere
read-only browserpoging kon die stap niet doen: het browseraccount had geen
gesloten trade en was terecht gescheiden van de beschermde fixture-eigenaar.

De gedeployde wijziging voegt daarom een afzonderlijk beschermd QA-profiel
`closed_paper_trade_review_chat` toe. Dit hergebruikt de bestaande Paper- en
reviewfixture, voert daarna twee FINN V2-chatbeurten op dezelfde eigenaar en
hetzelfde gesprek uit, en vereist reviewbewijs, de bevestigde les en geen
actievoorstel. Het profiel controleert bovendien dat de tweede beurt een
eigenaar- en gesprekgebonden Responses-resultaat heeft opgeslagen en dat de
twee oorspronkelijke Paper-orders na het gesprek ongewijzigd zijn. De
FINN-taakcode draait binnen het geïsoleerde QA-proces zodat
de tijdelijke review-allowlist uitsluitend voor de inactieve fixture-eigenaar
geldt; een geslaagde proef zou de productlevenscyclus toetsen, maar niet de
Celery-brokerhandoff.
Het QA-rapport bevat alleen vaste statussen en tellingen. Build heeft de
beschermde QA-run niet uitgevoerd. Gerichte runnertests: **89/89**; de volledige
backend-suite: **3599 geslaagd, vier bestaande skips**. De geïsoleerde lokale workeractiecontractmatrix
slaagde inmiddels **16/16**, met **19/19** adaptertests; artifact SHA-256
`a7470c2d59efa85ab6836dd24ae662644b7229b4c6a497c7d082594e4f2df655`.
De echte `gpt-6-luna`/Responses-developmentproef slaagde **20/20** met
operatienauwkeurigheid 1,0 en nul provider-, schema-, parse-, validatie- of
timeoutfouten; artifact SHA-256
`3a86168dc3bce3208a6c59990325d46d075a76ab15ebdeb6b29c5d370b1f9138`.
De afzonderlijke echte Luna/Responses-regressieset slaagde **109/109**, met
operatienauwkeurigheid 1,0 en nul provider-, schema-, parse-, validatie- of
timeoutfouten; artifact SHA-256
`d2151b2dc6c04e43da212ea95802b25eedfaf31b8b9d76c3ece17324f9de7bd3`.
Security en Architecture vonden geen blocker in deze lokale delta. Het
beschermde profiel controleert de actuele Responses-route,
maar attesteert de provider-modelidentiteit niet afzonderlijk. Ook draait de
FINN-taakcode in dit profiel direct en wordt niet via de Celery-broker afgeleverd.

## Rapport- en benchmarkuitleg na Score 2.0-cutover (21 oktober 2026)

Phase: `QA_ACCEPTED_SCOPED` voor de rapport-/benchmarkpresentatie en de
vooruitblik; geen verdict voor de volledige gebruikersreis.
[PR #489](https://github.com/gvangalen/antigravity-trading-tool/pull/489)
is gemerged op `1dc808a784724b1e2951504572824fa2072f5ec0`. Alle vijf
[PR-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39530925876)
en vijf [main-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39531251388)
zijn geslaagd; [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39531543033)
is geslaagd. Publieke backend-health en frontend-buildinfo gaven beide HTTP
200 en exact die SHA. De bestaande onafhankelijke QA-agent accepteerde de
gerichte NL-herkeuring: geen verzonnen botbeslissing, gepauzeerde Paper-bot
en onbekend kassaldo correct onderscheiden; Analyse, Mijn Plan, rapport en
FINN toonden voor BTC dezelfde componenten `40/40/40` en benchmark `40`.
Er was geen Live-order of botactivatie. EN/DE en bredere onboarding- en
multi-planflows zijn hiermee niet afgetekend. QA vond nog een P2:
de modelvooruitblik zei "zonder RSI- en DXY-waarden" terwijl Analyse die
metingen liet zien. De lokale vervolgcorrectie wijst zulke afwezigheidsclaims
bij complete actuele Score 2.0-componenten af. Gerichte rapporttests **16/16**
en root backend **3593 geslaagd, 4 skips** na deze correctie.
[PR #490](https://github.com/gvangalen/antigravity-trading-tool/pull/490)
is gemerged op `c40bf3a264fe96ca907ed69ecfbbad82394cbc38`.
Vijf [PR-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39532169322),
vijf [main-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39532395224)
en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39532644787)
slaagden; publieke backend en frontend gaven HTTP 200 en exact die SHA.
Dezelfde onafhankelijke QA-agent accepteerde de gerichte vervolgtest:
Analyse toonde DXY `101,73` en RSI `40,8`; een nieuw dagrapport nam Markt
`40`, Macro `40` en Technisch `50` mee zonder de onjuiste afwezigheidsclaim.
Er waren geen nieuwe browserconsolefouten, botacties of Live-orders. De
vooruitblik is nog algemeen geformuleerd; dat is een niet-blokkerend
begrijpelijkheidspunt.

Deze batch corrigeert twee bevindingen uit de
onafhankelijke Score 2.0/Paper-herkeuring. Een dagrapport zonder opgeslagen
botbeslissing toont geen verzonnen `Houd vast` of reden "criteria niet bereikt"
meer; het rapport maakt ook duidelijk dat een botbudget geen vastgesteld
kassaldo is. Analyse en Mijn Plan tonen de opgeslagen benchmarkscore met
maximaal één decimaal, zodat `33,3` niet als `33` wordt gepresenteerd.

Gemeten lokale controles: root backend **3593 geslaagd, 4 skips**;
gerichte rapporttests **16 geslaagd**; frontend build, typecheck, i18n-lint,
i18n-tests (**23**), command-tests (**27**), proposal-tests (**8**),
setup-tests (**9**) en high-audit zijn geslaagd. Eén echte
`gpt-6-luna`/Responses-rapportproef met synthetische eigenaargebonden feiten
gaf met draaiende lokale database HTTP 200 en alle acht secties. Het rapport
behield de benchmark `33,3`, noemde de Paper-bot gepauzeerd en behandelde
onbekend kassaldo als onbekend. De eerdere drie Paper/Score 2.0-QA-runs blijven het bewijs
voor de onderliggende botcutover, niet voor deze nieuwe presentatiecorrectie.

## Score 2.0-bot en oude marktagenten (21 oktober 2026)

Phase: `QA_ACCEPTED_SCOPED`. [PR #485](https://github.com/gvangalen/antigravity-trading-tool/pull/485)
is gemerged op `ba3734def342d622b47aa705a234418fc439d524`. Alle vijf
[main-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39527204955)
zijn geslaagd; [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39527489475)
is geslaagd. Publieke backend-health en frontend-buildinfo gaven HTTP 200
en beide exact die SHA. [Status-PR #486](https://github.com/gvangalen/antigravity-trading-tool/pull/486)
is daarna als documentatie-only SHA `8c1925d21f828edd3a9eb07b00060e122ea30d14`
met groene CI en Auto Deploy live gegaan; publieke backend en frontend gaven
beide HTTP 200 en die SHA. De bestaande FINN 2.0-chat, coachfeed en gedeelde
rapportcontext blijven de actieve coachroutes. De bot gebruikt nu alleen
de eigenaar- en assetgebonden Score 2.0-componenten en opgeslagen
setupvoorwaarden voor scorebeslissingen; oude gebruikersbrede
regime-/marktintelligentie kan koopgeschiktheid of bedrag niet wijzigen.
De ongebruikte marktintelligentie-API, kaarten, hook en modules zijn
verwijderd. Een no-op Celery-taak erkent uitsluitend nog al gepubliceerde
regimeberichten tijdens de overgang; Beat plant die taak niet meer.

Gemeten lokale poorten: root backend **3593 geslaagd, 3 bestaande skips**
na rebase op `4eb233599`;
frontend build, typecheck, i18n/command/proposal-tests en high-audit
geslaagd; worker-gedreven actiematrix **16/16**, artifact SHA-256
`375d472273a7ea5456eda2635d6c3a6a423dcbf1f5b458b20de1d58a88d0044f`;
actieadapters **19/19**. Onafhankelijke Security- en Architecture-review
vonden geen open blokker in de huidige lokale delta. De echte
`gpt-6-luna`/Responses-ontwikkelset slaagde **20/20**, zonder provider-,
schema-, parse-, validatie- of timeoutfout; artifact SHA-256
`e740746428a69f39f0c8d69a37bb9233ca0b994d677650dc2f5fc78aab02c6c8`.
Een afzonderlijke echte `gpt-6-luna`/Responses-aanroep voor het gedeelde
dagrapport gaf HTTP 200 en alle acht vereiste secties voor drie synthetische,
eigenaargebonden assetcontexten. De echte Responses-regressieset slaagde
**109/109** met nauwkeurigheid 1,0 voor
operatie, entiteit, asset, polariteit, gespreksverwijzing, verduidelijking,
ontbrekende invoer, off-topic en niet-ondersteunde operaties. Provider-,
schema-, timeout-, parse- en validatiefoutpercentages waren 0; artifact
SHA-256 `00a1723fe2391f76016053f3c95457adf7c56229f9a1892e0fa75a318a2daa9a`.
De bestaande onafhankelijke QA-agent gaf voor de gerichte Score 2.0-botcutover
formeel `ACCEPTED` op `8c1925d21f828edd3a9eb07b00060e122ea30d14`:
[geldige match met één gevulde Paper-order en ledger-entry](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39528548243)
(gesaniteerd artifact SHA-256 `c97ec7868d1a2c86859d12c29c67bdcd323b4d024c80bf2e827d1b7c3a2178a8`),
[verouderde bron zonder koop](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39528571726)
(`d177797efeaf180ca650ad058b7d68a3e7b79c6c6c07888334e54b5536d8e05f`)
en [buiten setupgrenzen zonder koop](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39528773401)
(`57cd04a7f07d4caa7a7022ad023e37ec3a098b0f7087bdedd507b1328707f56e`).
De eerste buiten-grenzenpoging raakte door een exclusieve fixture-lock geen
productpad; de toegestane infrastructuurretry slaagde. Alle drie geslaagde
runs hadden nul Live-trading-calls en nul Live-botactivaties. Analyse, Mijn Plan,
het rapport en FINN waren voor het geteste BTC-plan scoreconsistent en hielden
botbudget gescheiden van kassaldo. Dit verdict dekt niet de volledige
onboarding, mobiel, meerdere plannen per asset, EN/DE of dubbele bevestiging.
Kleine open uitlegpunten: het rapport onderscheidt scorematch, gepauzeerde
botstatus en onbekend Paper-kassaldo nog niet scherp genoeg; totaalscore
`33` versus `33,3` vraagt consequente afronding.

## Gesloten Paper-reflectie: alleen bewijsselectie (21 oktober 2026)

Phase: `LOCAL_FIX_CANDIDATE`. [PR #481](https://github.com/gvangalen/antigravity-trading-tool/pull/481)
is gemerged en gedeployed op `40890e253152ef3d77ef1489aec7e7433c8c4407`;
backend-health en frontend-buildinfo gaven HTTP 200 en dezelfde SHA.
De bestaande onafhankelijke QA-agent draaide één beschermde
[herkeuring 39521537823](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39521537823).
Het gesaniteerde artifact (SHA-256
`429f7e19baa17b1698a8d4891d430d0e9377454c85483b58b8995e85cd760ecd`)
bevestigt één gesloten Paper-dossier met twee fills, maar de analyse werd
`failed` zonder `analysis_json` en de les is niet bewezen. QA-status
`INCOMPLETE`, verdict `NOT_ACCEPTED`, veilige code
`closed_paper_review_dossier_incomplete:analysis_status_failed,analysis_json`.
Er waren twee Paper-uitvoeringsaanroepen en geen Live-trading-calls of
live-botactivaties. Het artifact bewijst geen specifieke model- of
validatiefout.

De productcode vroeg tot nu toe om modelproza (`summary`, `uncertainty`,
`question`, observatietekst) en keurde dat af op vorm of woordkeus, hoewel
het nooit zichtbaar of opgeslagen wordt. De lokale kandidaat vraagt en
valideert alleen thema's en exacte eigenaargebonden bewijs-ID's; de zichtbare
retrospectieve tekst blijft volledig door servertemplates gemaakt. Onjuiste
bewijs-ID's blijven ongeldig. De 61 gerichte reflectietests slagen. Eén
synthetische echte Luna/Responses-proef gaf HTTP 200 en een geldige
bewijsselectie op de eerste poging; dit is geen vervanging voor live QA.
De root backend-suite telt **3580 geslaagd, 3 bestaande skips**.

## Gesloten Paper-tradereview: tweede modelpoging (21 oktober 2026)

Phase: `LOCAL_FIX_CANDIDATE`. Na [PR #480](https://github.com/gvangalen/antigravity-trading-tool/pull/480)
zijn backend-health en frontend-buildinfo HTTP 200 op SHA
`629a4ea2f166c87e9b1aa7047fd8177bda532686`. De gecombineerde
main-CI en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39520108028)
slaagden. De bestaande onafhankelijke QA-agent draaide één beschermde
[herkeuring 39520295886](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39520295886).
De projectie bereikte één gesloten Paper-dossier, maar de analyse stopte op
`closed_paper_review_ai_unavailable:rate_limit`; QA-status `INCOMPLETE`,
verdict `NOT_ACCEPTED`. Gesaniteerd artifact SHA-256
`3aea232b8dc01cfbd276f05905e848facce1f5ced7c20f6e56041c43220f2102`.
Twee Paper-uitvoeringsaanroepen, nul Live-trading-calls en nul live-botactivaties.
Fills in het dossier, analyse en een leesbare les zijn daarmee nog niet bewezen.

De analysemethode staat maximaal twee modelpogingen voor dezelfde afgesloten
trade toe, maar de generieke limiet voor geplande taken staat op één aanroep
per review per uur. De lokale kandidaat geeft uitsluitend
`finn_trade_review` twee eigenaar- en reviewgebonden slots; rapporten en de
FINN-chat behouden hun bestaande limieten. De beschermde QA-diagnose maakt
een lokale slotafwijzing voortaan apart herkenbaar van een provider-429.
De vorige veilige categorie `rate_limit` alleen bewijst nog niet welke van
die twee grenzen werd geraakt.
Gerichte limiet- en diagnosecontrole **2/2** en root backend **3579 geslaagd,
3 bestaande skips**.

## Gesloten Paper-tradereview: AI-beschikbaarheid (21 oktober 2026)

Phase: `LOCAL_DIAGNOSTIC_CANDIDATE`, nog niet gedeployed. De gecontroleerde
fixtureprijs uit [PR #478](https://github.com/gvangalen/antigravity-trading-tool/pull/478)
is live op `879b66e4a9bb38be992a8a615e593f766c1bf5f3`. Alle vijf PR- en
main-CI-controles en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39518640581)
slaagden; publieke backend-health en frontend-buildinfo gaven HTTP 200 en
dezelfde SHA. Onafhankelijke [QA-run 39518870435](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39518870435)
bereikte Paper-uitvoering en één gesloten dossier, maar de analyse bleef
`unavailable` zonder opgeslagen analyse. De veilige foutcode was
`closed_paper_review_dossier_incomplete:analysis_status_unavailable,analysis_json`.
QA-status `INCOMPLETE`, verdict `NOT_ACCEPTED`, gesaniteerd artifact SHA-256
`a902f894a5ceda0e6426012a967309daaad51cc3d2c0799e7b416e46011d3dd7`.
Twee Paper-fixture-uitvoeringen, nul Live-trading-calls en nul
live-botactivaties zijn gemeten.

De lokale diagnosekandidaat laat de beschermde proef bij een OpenAI-fout
uitsluitend een vaste categorie melden (configuratie, limiet, quota,
authenticatie, model, timeout, verbinding of provider). De oorspronkelijke
providerfout, prompt en modelantwoord worden niet in het QA-rapport gezet.
De productanalyse en de normale modelaanroep blijven ongewijzigd.
Gerichte regressie **7/7** en root backend **3576 geslaagd,
3 bestaande skips**. De productroutes voor chat, score, acties en rapporten
zijn ongewijzigd ten opzichte van de vorige live SHA.

## Gesloten Paper-tradereview: gecontroleerde fixtureprijs (21 oktober 2026)

Phase: `LIVE_QA_NOT_ACCEPTED`. Kandidaatbranch
`codex/closed-paper-review-controlled-quote`, codecommit `59bbdc76e` en
[PR #478](https://github.com/gvangalen/antigravity-trading-tool/pull/478).
De diagnoseversie
uit [PR #477](https://github.com/gvangalen/antigravity-trading-tool/pull/477)
is live op `3933ee87a2d68dde02aebbac88bd6a7a94720bb2`; vijf PR- en
main-CI-controles en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39517296357)
slaagden. Publieke backend-health en frontend-buildinfo gaven HTTP 200 en die
SHA. Onafhankelijke [QA-run 39517479852](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39517479852)
kwam niet aan de dossiercontrole toe: de beschermde Paper-uitvoering stopte
veilig omdat een actuele, gecontroleerde EUR-prijs ontbrak. QA-status
`INCOMPLETE`, verdict `NOT_ACCEPTED`, gesaniteerd artifact SHA-256
`3bf33fb12528c85ff223be1c4aef45076eeceb346c8022af144820fca0e5537f`.
Twee fixture-execution-calls, nul Live-trading-calls en nul live-botactivaties
zijn gemeten.

De gesloten-review-fixture test de Paper-ledger-naar-dossierketen, niet de
live koersaanvoer. De lokale kandidaat geeft alleen tijdens de twee
uitvoeringen voor het inactieve, sleutelvrije QA-kindaccount een gecontroleerde
EUR-testkoers aan de bestaande Paper-uitvoeringsfunctie. De processcope wordt
direct daarna hersteld; markttabellen, applicatieworkers en productprijsregels
blijven ongewijzigd. Dit bewijst bij slagen geen automatische Paper-aankoop op
een echte actuele koers. De afwijzing bij ontbrekende EUR-prijs blijft apart
veiligheidbewijs.

Gerichte fixture-regressie **6/6** en root backend **3575 geslaagd,
3 bestaande skips**. Selector-, actie-, frontend- en mobiele productcode zijn
ongewijzigd ten opzichte van de voorafgaande live kandidaat; de daar gemeten
16/16 actiecontracten, 19/19 adapters en echte Responses 20/20 + 109/109
blijven de betreffende releasepoorten.

## Gesloten Paper-tradereview: veldspecifieke diagnose (21 oktober 2026)

Phase: `LIVE_QA_NOT_ACCEPTED`. Diagnosebranch
`codex/closed-paper-review-diagnostics`, codecommit `095e3dec2` en
[PR #477](https://github.com/gvangalen/antigravity-trading-tool/pull/477).
[PR #475](https://github.com/gvangalen/antigravity-trading-tool/pull/475)
is op product-SHA `a7445f2344426424fc758bf5ea58b7a6d4ec92cb` live gezet.
Alle vijf PR- en main-CI-controles en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39515842618)
slaagden; publieke backend-health en frontend-buildinfo gaven beide HTTP 200
en exact die SHA. De bestaande onafhankelijke QA-agent herhaalde het beschermde
profiel in [run 39516106734](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39516106734).
Er werd nu exact één eigenaargebonden gesloten Paper-dossier gevonden, maar
de gecombineerde dossiercontrole gaf `closed_paper_review_dossier_incomplete`.
QA-status `INCOMPLETE`, verdict `NOT_ACCEPTED`; het gesaniteerde rapport heeft
SHA-256 `dde6afd6abb449d0badcf0d5699712140a12e98c2fe052c9ed81d7c822ac2c1b`.
Twee fixture-uitvoeringen, nul Live-trading-calls en nul live-botactivaties
zijn gemeten. Welke dossiercontrole faalde is uit dit artifact niet vast te
stellen. De lokale diagnosekandidaat meldt daarom alleen de namen van de
falende velden en de beperkte analysestatus; geen tradebedragen of inhoud.
Gerichte diagnose-regressie **5/5** en root backend **3570 geslaagd,
3 bestaande skips**. De productselector, uitvoeringsroute en providerclient
zijn ongewijzigd ten opzichte van `a7445f2`; de daar gemeten 16/16
actiematrix, 19/19 adapters en echte Responses 20/20 + 109/109 blijven het
bewijs voor die routes. Nieuwe onafhankelijke QA moet het specifieke
ontbrekende dossieronderdeel nog vaststellen.

## Gesloten Paper-tradereview: beschermde projectie (21 oktober 2026)

Phase: `LIVE_QA_NOT_ACCEPTED`. Kandidaatbranch
`codex/closed-paper-review-projection`, codecommit `fabcbf10d` en
[PR #475](https://github.com/gvangalen/antigravity-trading-tool/pull/475).
Onafhankelijke QA op
de stabiele product-SHA `00d94aa5042027dafa56183df16998bbe34f364a`
bereikte twee Paper-uitvoeringsaanroepen in
[run 39511158472](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39511158472),
maar de reviewlijst bevatte daarna niet exact één dossier. QA gaf
`NOT_ACCEPTED`; een FINN-analyse en reflectie waren niet bewezen. Het
gesaniteerde QA-artifact heeft SHA-256
`a331bcc55b3910ec98f845efd410c87fc8f0623c82b28494f8eaf1fe3588cde2`.
Native mobiel bleef ongetest door de vergrendelde Mac.

De oorzaak in de beschermde proef: de productieprojectieworker verwerkt
alleen allowlisted gebruikers, terwijl de proef een nieuwe inactieve
fixturegebruiker aanmaakt en onmiddellijk de reviewlijst leest. De kandidaat
roept voor uitsluitend die fixture de bestaande productieprojectie- en
Luna-analysetaken aan onder een proceslokale, tijdelijke allowlist en leest
daarna het dossier terug. De normale rollout en periodieke worker blijven
ongewijzigd. De proef onderscheidt voortaan een ontbrekend van een dubbel
dossier en markeert een begonnen fixturetest niet meer als `NOT_STARTED`.

Lokale metingen: root backend **3566 geslaagd, 3 bestaande skips**;
gerichte reviewregressie **4/4**. De eerste actiematrix toonde daarnaast
een wisselende modelkeuze bij de expliciete opdracht om een opgeslagen
RSI-indicatorconfiguratie te verwijderen. Een gerichte registry-route voor die
ondubbelzinnige configuratieterm voorkomt selectie van `delete_setup`; de
bijbehorende regressietest slaagt. De volledige matrix op deze kandidaat
slaagde **16/16**, plus **19/19** adaptertests (artifact SHA-256
`4b38d7a5cc51d4ccb20c53ff7774c25dc3cfe2f580bd9edb8d1cbd2638955fc6`).
De echte Luna/Responses-developmentproef slaagde **20/20**, zonder provider-,
schema-, parse-, validatie- of timeoutfout (artifact SHA-256
`22259230d67f9f4c9ae5a420fa418a6281beedad6dbeffecb9bbc04210f3fe78`).
De echte Luna/Responses-regressie slaagde **109/109** zonder provider-,
schema-, parse-, validatie- of timeoutfout (artifact SHA-256
`857f78ecc286679b1465049098c2c91badc4172639b54764f13562775e82d859`).
Webbuild, typecheck, i18n-lint/tests, commands,
proposals en high-severity audit slaagden; mobiele typecheck, 16 chatproeven
en lint zonder errors slaagden. Een eerste geïsoleerde actiematrix gaf
**15/16** doordat een synthetische verwijdervraag voor een RSI-configuratie
veilig maar verkeerd als setupverwijdering werd geclassificeerd (artifact
SHA-256 `147cd04db38f5dd8f0218c83059f98ecf27f26fa80c2752328f8d3880e27f1f6`).
De herhaling vóór die extra classifierfix gaf **16/16** en **19/19** adaptertests (artifact
SHA-256 `91c99acda0cdc46648647019de8f6daa594ee7b0703d3bef12dc967521e20654`).
De voorafgaande live kandidaat mat echte Responses-development **20/20** en
regression **109/109** zonder provider- of validatiefouten. De 15/16-run
blijft als rood bewijs bewaard en wordt niet als groen geteld.


## Mobiele FINN-feed en gesloten Paper-reflectie (21 oktober 2026)

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. [PR #471](https://github.com/gvangalen/antigravity-trading-tool/pull/471)
is gemerged als productcommit `dda19dce00d6a42b53fac580e39273df4232aa78`
vanaf kandidaat `8b97a103ca6c2562b4366e602428e37a40b50dbc`.

De mobiele werkruimtes tonen dezelfde eigenaargebonden coachfeed in plaats van
een pagina-afhankelijke Today-briefing. Het oude lege briefingcontract is uit
de mobiele overview-API verwijderd. Een niet gebruikte mobiele FINN-screen
met lokaal verzonnen antwoorden en zijn ongebruikte chatkaarten zijn verwijderd.
Score-uitleg gaat via een echte vraag aan FINN 2.0. Reflectie haalt geen apart
mobiel overview meer op alleen voor de oude briefing. De onderliggende
score-, strategie-, bot- en rapportservices blijven bestaan als feitenbronnen.

Lokale metingen: root backend `pytest -q` **3559 geslaagd, 3 bestaande skips**;
41 gerichte dashboard- en tradereviewtests geslaagd. Mobiele typecheck,
chatcontracttests **16/16**, lint zonder errors (90 waarschuwingen) en Expo
web-, iOS- en Android-bundels geslaagd. Webbuild, typecheck, i18n-lint/tests,
command- en voorsteltests en `audit:high` geslaagd; audit meldde één moderate
Next.js-advisory en geen high of critical. De geïsoleerde lokale
FastAPI/Celery/PostgreSQL/Redis/Responses-actiematrix sloot **16/16**
contracten en **19/19** adaptertests af zonder brokerorder of Live-activatie;
artifact SHA-256 `245f752b6d7e6bef996792ad58e0e5900baecc876c1da414ebfc3e779751b4af`.
Echte `gpt-6-luna`/Responses-selectie: development **20/20** (SHA-256
`03fde7b1a70f7898e8075df400450d84a5c122f8fd24c34ce7feb4eba95fd909`)
en regression **109/109** (SHA-256
`75407be96f65207d8d34b3fdb2ea3a4a08a6aedb8174ea61a82ea32075660b29`),
beide zonder provider-, schema-, parse-, validatie- of timeoutfalen.

Alle vijf [PR-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39508735324)
en vijf [main-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39509082075)
slaagden. De eerste overlappende
[Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39509289816)
faalde op een SHA-mismatch met de voorgaande release. De opvolgende
[Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39509360845)
slaagde. Publieke backend-health en frontend-buildinfo gaven daarna beide
HTTP 200 en exact `dda19dce00d6a42b53fac580e39273df4232aa78`.
Een latere status-only commit kan de publieke SHA veranderen; QA bindt aan
de dan actuele gelijke backend/frontend-SHA.

Onafhankelijke native mobiele acceptatie ontbreekt nog. De bestaande QA-agent moet daarnaast via de
beschermde fixture één gecontroleerde Paper-aankoop en volledige verkoop tot
het blijvende tradereviewdossier en FINN-reflectie volgen. Build heeft die
fixture niet aangeroepen. Exchange-import en Live-orders vallen buiten deze
acceptatie.

## Actuele uitkomst agentuitfasering en begeleide Analyse (20 oktober 2026)

Phase: `DESKTOP_SCOPED_QA_ACCEPTED`, volledige productacceptatie blijft open.
De FINN 2.0-chat is de enige actieve webcoach; de oude onboarding-agentketen
en de onbereikbare Mission Control/Today-presentatie zijn uit de actieve
webroute verwijderd. Scoreberekening, dataverzameling, rapportage,
botuitvoering en trade-review blijven gespecialiseerde ondersteunende
services, geen zelfstandige gesprekscoaches. De mobiele legacy-briefingvorm
is in PR #471 verwijderd; native mobiele acceptatie is nog niet afgerond.

Na [PR #466](https://github.com/gvangalen/antigravity-trading-tool/pull/466)
is de taalwisselreparatie gemerged als `19ddf25faf4b71d40c7f0855f1b586f669e82ba7`.
Alle vijf PR- en main-CI-controles en Auto Deploy slaagden. Backend en frontend
gaven daarop HTTP 200 en dezelfde SHA. Een parallelle capaciteitsrelease
wijzigde productie tijdens de eerste onafhankelijke QA-run naar
`116f19e0aff8389b8c836546c8fc82774d451ec4`; een eenmalige chat-502
viel samen met die wissel en werkte na handmatige retry. De oorzaak is niet
bewezen. De bestaande QA-agent herhaalde daarna de gerichte desktoproute met
een nieuw account op de stabiele `116f19e0` (backend/frontend vóór en na gelijk)
en gaf `ACCEPTED` voor die scope: Prijs/DXY/RSI en de vervolgknop bleven na
NL → EN → DE → NL, navigatie en refresh zichtbaar; vrijdag-DCA, een
€80-strategie en een gepauzeerde Paper-bot werden correct gekoppeld. FINN
las de opgeslagen setup-toelichting zonder 502 terug. Geen Live-order.

Resterend: native mobiel was door een vergrendelde Mac niet testbaar; een
positieve scoregestuurde Paper-beslissing, een gesloten tradereview,
exchange-import en databasebrede duplicaatcontrole zijn niet door deze
gerichte QA bewezen. Kleine zichtbare copyrest: de Nederlandse assetkaart
toont na herladen “BTC · BTC · Market”; de plancontrole toont nog de
technische range “Onder druk (26–45)”. Een Paper-bot zonder kassaldo heet
in de lijst “Bot actief”, hoewel de details de beperking uitleggen.

## Begeleide Analyse: taalwissel verliest opgeslagen indicatoren

Phase: `LOCAL_REPAIR_IN_VALIDATION`, nog niet gedeployed. Onafhankelijke
ingelogde QA op product-SHA `0755a9c402565a9c8641ea8d43d34aae036d007b`
gaf `NOT_ACCEPTED` voor de gerichte webscope. Twee nieuwe accounts sloegen
hun profiel bij de eerste poging op; de vorige incidentele HTTP 500 trad in
deze twee pogingen niet op. De Nederlandse indicatornamen, de opgeslagen
“Bedrag per uitvoering: €80”-kaart, FINN-chat en coachfeed bleven goed na
navigatie, refresh en herlogin. De oude Today/Mission Control-weergave kwam
niet terug. Bij NL → EN/DE verdwenen echter Prijs, DXY en RSI uit de
begeleide Analyse-stap terwijl de voortgang 2/4 bleef; refresh herstelde de
gekozen indicatoren en de knop naar Mijn Plan niet. QA moest ze opnieuw
aanklikken. Er is geen Live-order uitgevoerd; mobiel, positieve Paper-uitvoering
en gesloten tradereview zijn niet getest.

De lokale reparatie laat een taalwissel de assetgebonden formulierstatus niet
meer resetten en leest na een echte heropening alleen eigenaargebonden,
opgeslagen indicatorvoorkeuren terug voor reeds voltooide onboardingstappen.
Een lege of standaardvoorkeur voltooit geen stap. De gerichte hersteltests
slagen **2/2** en de volledige i18n-suite **17/17**; webbuild, typecheck,
i18n-lint, 27 commandtests, 8 voorsteltests, 9 setuptests en `audit:high`
zijn groen; de audit meldt alleen de bestaande moderate Next.js-advisory.
De volledige backend-suite slaagde **3555 tests, 3 bestaande skips**. Deze
batch verandert geen FINN-actieregister, providerselectie, backendservice of
worker; de gemeten 16/16-actiematrix en 109/109 echte Responses-regressie
van de huidige live productrelease blijven het relevante contractbewijs.
Een nieuwe onafhankelijke live
taalwissel-/refreshproef is vereist vóór acceptatie.

## Agentuitfasering: laatste webopruiming en nieuwe-gebruiker QA

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. [PR #464](https://github.com/gvangalen/antigravity-trading-tool/pull/464)
is gemerged als product-SHA `0b3458bfd187509a2227077d439904fb3cdf6ce5`.
Alle vijf [PR-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39498460315)
en vijf [main-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39498894735)
slaagden. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39499249351)
slaagde; daarna gaven backend-health en frontend-buildinfo op 20 oktober 2026
ieder HTTP 200 en exact die SHA. Een eerdere overlappende deployrun voor de
voorafgaande capaciteitcommit faalde terecht op een SHA-mismatch en is door
de succesvolle run hierboven opgevolgd. De bestaande onafhankelijke
QA-agent testte de eerdere release `b248f0dd2bc12db73d2bd46cbabaa55a1463d1d1`:
de vijf gerichte FINN/Paper/onboarding-paden werkten, maar een eerste
profielopslag voor een nieuw account kreeg eenmalig HTTP 500. Een herhaling
slaagde. De opgeslagen Mijn Plan-kaart noemde het strategiebedrag zonder
valuta of uitvoeringsbetekenis; de Nederlandse onboarding-samenvatting toonde
Engelse indicatornamen. De nieuwe-gebruikerroute is daarom niet geaccepteerd.

De live kandidaat verwijdert dode Mission Control/Today-presentatie
en zijn oude briefingcache uit de webchat. De actieve FINN 2.0-chat,
voorstelkaarten, coachfeed en gesprekstoestand blijven bestaan. Mijn Plan
labelt een strategiebedrag als bedrag per uitvoering met euroteken; de
onboarding-samenvatting gebruikt de gekozen taal. Bij profielopslag wordt
uitsluitend een aantoonbaar tijdelijke SQLAlchemy-verbindings- of
transactiefout éénmaal veilig herhaald. De oorzaak van de productie-HTTP 500
is zonder servertrace niet bewezen; deze wijziging mag pas na onafhankelijke
nieuwe-gebruiker QA als herstel worden beschouwd. De backend-suite telt
**3551 geslaagd, 3 bestaande skips**; webbuild, typecheck, i18n-lint,
i18n-/setup-/command-/voorsteltests en `audit:high` slaagden. De lokale
FINN-actiematrix slaagde met **16/16 contracten en 19/19 adaptertests**
(artifact SHA-256
`608ec7ab91ee5201dc20903a8f3063da27da38f90c978c628144592c1e631ad0`).
De echte `gpt-6-luna`/Responses-ontwikkelset slaagde **20/20** (artifact
SHA-256 `6fa24409032f7f0a44d1ddb9672a3fce5daba19654d7f17dfe307edb0813e810`);
de echte Responses-regressie slaagde **109/109** operatie- en veldmatches,
zonder provider-, schema-, parse- of validatiefout (artifact SHA-256
`a13a1a3f913e5bf19fad23588f662fde7dedb799b402a2162ef7011941f65048`).
Er was geen productieverbinding, Live-order of
Live-botactivatie in de lokale actiematrix.

Na samenvoeging met `origin/main` op
`52ef2159338ba360932ebe7fcd2d578657a9adab` slaagde de volledige
backend-suite opnieuw met **3552 geslaagd, 3 bestaande skips**. De webbuild,
typecheck, i18n-lint, 15 i18n-tests, 27 commandtests, 8 voorsteltests,
9 setuptests en `audit:high` slaagden opnieuw; de audit noemt één bestaande
moderate Next.js-advisory. De nieuwe main-commit verandert de gedeelde
werkruimtegegevensroute, maar geen FINN-providerselectiecode. De gecombineerde
actiematrix slaagde **16/16 contracten en 19/19 adaptertests** (artifact
SHA-256 `4746e7b508d9462115a6101cf857406c571b455e723d2134ddbf23e140e667e0`).
De ingelogde nieuwe-gebruikerhertest is nog niet onafhankelijk afgerond.
Een statusdocumentatiecommit verandert opnieuw de deploy-SHA; verifieer
vóór QA beide publieke identiteiten en gebruik uitsluitend die SHA voor de
ingelogde hertest.

## Nieuwe-gebruiker QA-herstel na agentuitfasering

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. De publieke backend en frontend gaven op
20 oktober 2026 na de FINN-reparatie beide HTTP 200 en product-SHA
`daaa81002f6ec8aa5b978d17eaa97eb740756682`. Onafhankelijke QA heeft op
de eerdere SHA `1f7077ea179bbf1ef0887be4605d731df73af880`
de feedvolgorde na refresh bevestigd, maar de bredere nieuwe-gebruiker-
route nog niet geaccepteerd. De concrete bevindingen waren een niet-duurzame
`not_due`-uitleg na een Paper-beoordeling, een onterecht ontbrekende exchange
in Paper-onboarding, een irrelevante historie-eis bij RSI en een slecht
leesbaar bedragveld. Een contextmelding verwees bij een DCA-plan bovendien
naar een aparte instapregel.

De [Auto Deploy-run voor `749391240`](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39487592096)
eindigde als failure ondanks de publiek zichtbare SHA. De log toont dat de
productie-deep-healthcheck naar `staging-*`-queues keek. De daaropvolgende
`main`-commit `2159c045c5cf071131078c2871502203dadaa5e7` herstelt de
deploydoel-, topologie- en capaciteitswaarden ná het inlezen van de
langlevende serverinstellingen. [Auto Deploy op die correctie](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39489597019)
slaagde en beide publieke oppervlakken meldden toen die SHA.

De gemergede [PR #459](https://github.com/gvangalen/antigravity-trading-tool/pull/459)
projecteert alleen voor
bevestigde DCA-bedragregels de opgeslagen planning naast de botstatus. Dit
gebruikt dezelfde `dca_due_on_date`-regel als de Paper-engine en maakt na
refresh zichtbaar dat een aankoop op de huidige datum niet gepland is; het
maakt geen botbeslissing of order. Paper-onboarding vereist geen exchange meer,
de RSI-verdieping toont de brondagenrij alleen waar die geschiedenisregel
werkelijk geldt, en het strategiebedrag heeft een leesbaar euro-label. De
feedtekst veronderstelt geen afzonderlijke instapregel meer. Twee niet
aangeroepen oude UI-wrappers zijn verwijderd; de actieve FINN-chat blijft.

Gemeten lokale controles na samenvoeging met de capaciteitsrelease:
root backend-suite **3545 geslaagd, 3 bestaande skips**; gerichte bot- en
onboardingtests **98/98**; feed- en
financiële-tooltests **29/29**. Webbuild, typecheck, i18n-lint, 15 i18n-tests,
27 commandtests, 8 voorsteltests, 9 setuptests en `audit:high` slaagden; de audit meldt
alleen een bestaande moderate Next.js-advisory. Mobiele typecheck, 16
chattests en web-, iOS- en Android-Expo-bundels slaagden; lint had nul errors
en 110 bestaande waarschuwingen. De geïsoleerde lokale API/Celery-matrix vóór
de samenvoeging slaagde **16/16**, zonder productieverbindingen,
brokerorders, live bots of live trading calls; artifact SHA-256
`b9627fe435f55da47e7e064d14a85039b5808e87c8c32f97b7a135d13910a19b`.
De echte Luna/Responses-ontwikkelset op de gecombineerde code slaagde
**20/20**, zonder fout; artifact SHA-256
`40c4cecf2b77fd17132b1040466997f9a3069cbcbea76bc347a7abd51f280a14`.
De gecombineerde workeractieproef slaagde opnieuw **16/16** (artifact SHA-256
`6ffbd3d9ff09c0f3ead13cba6835fa15c40c8c45467096820a5cb1ad19aa432f`),
ook zonder productieverbindingen, brokerorders, live bots of live trading
calls. De echte `gpt-6-luna` Responses-regressie op de gecombineerde code
slaagde **109/109**, zonder provider-, schema-, parse- of validatiefout;
artifact SHA-256
`232dec4a021c2ad843bd1389c354ce94785dff5eec5ccd1604a0777f74cca5a0`.
Alle vijf [merge-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39490602689)
en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39490980493)
slaagden. Backend-health en frontend-buildinfo gaven ieder HTTP 200 en exact
de product-SHA hierboven. De ingelogde functionele acceptatie is nog niet
onafhankelijk afgerond; Build heeft na deployment alleen identiteit en
beschikbaarheid gecontroleerd.
Een documentatie-only statuscommit verandert de deploy-SHA; controleer vóór
QA daarom opnieuw beide publieke identiteiten en gebruik die SHA voor de
ingelogde hertest.

## Multi-user capacity hardening candidate

Phase: `LOCAL_GATES_PASSED_AWAITING_REVIEW`. Draft [PR #453](https://github.com/gvangalen/antigravity-trading-tool/pull/453)
contains account-scoped workspace caching, shared Redis limits, bounded and
durable dispatch waves, read-only trade-review listing, cluster metrics, pool
limits, reduced polling, and an opt-in scaled worker profile. The tracked
profile remains `compact`; no capacity claim or deployment is recorded here.
The latest Build repair excludes synthetic fixture accounts from scheduled
jobs, holds dispatcher reservations through retries, adds stale-reservation
monitoring and fenced single-host recovery, requires queue consumers during
deployment, and verifies each load token's account identity. The current
combined backend suite passed **3543 tests, 3 skips**; Redis admission and
retry/terminal release passed against local Redis. Independent QA, Security,
and Architecture re-reviews found no remaining P1 code blocker in the scoped
candidate. This repair has not yet completed CI, Auto Deploy, or independent
authenticated live QA. Alert-channel routing and the 1000-user live capacity
run remain pending.
The pre-merge implementation and plan baseline is
`b2ccc7c5f48cddf72098bc10145fadcdb3f85783`.

Build evidence on 2026-10-20: root backend suite **3529 passed, 3 skipped**;
frontend typecheck, focused tests and production build passed. All five
[candidate CI jobs](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39476821430)
passed. The isolated local worker-driven FINN matrix passed **16/16** action
contracts and **19/19** adapter tests; its artifact SHA-256 is
`a97eb8b4f5fab376fc44f3b088371ee4975f15e705f133c6e305eb6179495446`.
The real-provider development selector passed **20/20** cases (SHA-256
`3d2a333f5b37fdf9ce7bf2d22ecbcdac962a2ed76e889c392ddd2031c03458ab`),
and the real-provider regression selector passed **109/109** cases (SHA-256
`3b3236d12132911caffa8fb3d43298c1643954b33e6d968bb9ebee5502b5b3cf`).
Both selector runs had zero provider, schema, timeout, parse and validation
failure rates. No broker orders, live trading calls or production connections
were made by the local matrix.

After merging production `main` at `2664fe1fb675f226e0dd4e627d3c8995f132a87b`,
the backend suite passed **3530 tests, 3 skips**. The frontend production build,
typecheck, i18n lint and tests, 27 command tests, 8 proposal tests, and
`audit:high` passed. The isolated worker-driven action matrix was repeated
against the combined source: **16/16** contracts and **19/19** adapter tests,
artifact SHA-256
`d4f2cebd6e61e46558667d47bb84e01dcc3daec2e6f625516907829882a8a297`.
The merged main changes did not touch the selector boundary or registry used
by the real-provider development and regression artifacts above. CI on the
first merge commit passed all five jobs. A later main revision
`1f7077ea179bbf1ef0887be4605d731df73af880` changed FINN feed presentation
and mobile feed code; it has also been merged. The frontend export was rebuilt
from that combined source. The provisioner candidate
`c216d99aa5b38cd520b7876eab56a3b0df1cd3ef` then passed all five
[CI checks](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39482730857).

Production reported `1f7077ea179bbf1ef0887be4605d731df73af880`
from both public surfaces at the last check. That `main` revision is merged
into the local candidate. A read-only host check found 4
vCPU, 7.75 GiB RAM and PostgreSQL `max_connections=100`; the historical 1 GB
host note does not describe the current machine. Independent QA, Security and
Architecture reviews, deployment identity checks, and an authenticated
1000-distinct-account sustained load test are still outstanding. No file with
1000 test accounts exists on this workspace. A controlled production-account
provisioner has now been prepared, but has not run on production. Its
20-minute default tokens allow only the three read routes in the load harness;
the nonexistent FINN state route in the initial harness was replaced with the
existing FINN conversation listing. A local PostgreSQL cycle created three
marked accounts, issued three distinct 0600-file tokens, then deactivated
all three; the private token file was removed. The backend suite on this
candidate passed **3534 tests, 3 skips** after these additions. These checks
are Build evidence, not independent live acceptance.

## FINN 2.0 agentuitfasering

Phase: `LIVE_FEED_REPAIR_AWAITING_INDEPENDENT_QA`. [PR #451](https://github.com/gvangalen/antigravity-trading-tool/pull/451)
is gemerged als product-SHA `191c1199b6129c8feb305657e7d3483d8eef4048`.
Alle vijf PR- en [main-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39470300165)
slaagden. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39470689636)
slaagde; daarna gaven backend-health en frontend-buildinfo ieder HTTP 200
en exact die SHA. De latere onafhankelijke ingelogde herkeuring staat hieronder.
De aparte cutover-checkout verplaatst
de deterministische botuitvoering uit `ai_agents`, laat web en mobiel
V2-voorstellen via dezelfde eigenaargebonden lees-, publicatie-, bevestigings-
en uitvoeringsroute afhandelen, en verwijdert de oude assistent-actie-, status-
en chatsessie-endpoints. De oude `FinnPlanService` en zijn ongebruikte
response-traceservice zijn verwijderd. De niet meer aangeroepen eerste-dashboardbriefingtaken zijn
uit de onboarding-worker en queue-registratie gehaald; workerobservatie volgt
nu de coachfeed- en rapportgeneratie. De gesprek-, score-, feed- en
rapportbronnen blijven bestaan. Mission Control-UI-code heeft geen actieve
productie-aanroepers meer, maar staat nog in de repository. Web- en
mobiele dashboardprojecties lezen de actuele `reported_scores` nu rechtstreeks
uit dezelfde Score 2.0-beoordeling als Analyse en FINN; de oude parallelle
`get_scores_for_symbol`-uitlezing en ongebruikte `market_data/interpreted`-route
met een fictieve scorefallback zijn verwijderd.

Build-bewijs voor deze lokale stand: backend **3522 geslaagd, 3 bestaande
skips**; webbuild, typecheck, i18n-lint, i18n-tests, 27 commandchecks,
8 voorsteltests en `audit:high` geslaagd. Mobiele typecheck, 16 chattests,
web-, iOS- en Android-bundels, en lint met 0 errors geslaagd; de 110
lintwaarschuwingen zijn bestaand. De lokale workeractiecontractmatrix
slaagde met **16/16 contracten en 19/19 adaptertests**; de echte
Responses-ontwikkelproef slaagde met **20/20** operatie- en veldmatches.
Een eerste regressierun vond één direct-order-fout; na reparatie slaagde de
echte `gpt-6-luna` Responses-regressie met **109/109** operatie- en
veldmatches, zonder provider-, schema-, parse- of validatiefout. Een aparte
review vond dat mobiele destructieve voorstellen alleen een object-ID en
handmatige orders alleen het asset konden tonen. Het volledige orderveld staat
nu in de reviewprojectie; een eigenaargeverifieerde doelnaam komt uit de
opgeslagen setup, strategie of bot, en de mobiele kaart noemt het gevolg van
verwijderen of (de)activeren. Herbalanceren blijft uitgeschakeld omdat die
uitvoering ook server-side in shadow mode staat. De gerichte mobiele
reviewtests (16/16), backendprojectietests (9/9) en de volledige backend-suite
na legacyverwijdering slagen. Bij verwijderen en bot-(de)activatie vergelijkt
de uitvoeringsroute de door de gebruiker bekeken eigenaargebonden naam nogmaals
onder een database-rijvergrendeling; web en mobiel tonen en verzenden diezelfde
naam. De gerichte postcondition- en eigenaarstests slagen (27/27). De actieve
gedeelde OpenAI-client gebruikt nu ook standaard Luna/Responses; de oude
Chat Completions-stream en de ongebruikte eerste-briefingvertaler zijn weg.
De na deze aanpassingen herhaalde lokale actiematrix slaagde met **16/16
contracten en 19/19 adaptertests** (artifact SHA-256
`6c4a1b35bb5083101d9e1160b02f4af5fdab07eab2921fcee570727b0e943154`).
Een echte lokale runtimeprobe op de ontwikkelsleutel kreeg HTTP 200 van
Responses en rapporteerde `gpt-6-luna`; de volledige backendherhaling na de
laatste legacyverwijdering telt **3522 geslaagd, 3 bestaande skips**.
De herhaalde echte `gpt-6-luna` Responses-regressie slaagde met **109/109**
operatie- en veldmatches en nul provider-, schema-, timeout-, parse- of
validatiefouten (artifact SHA-256
`4371c6bb6a57151b6d3dd540c75e168a4e1cd1491971e6492b98f36de3d3be3f`).
Nog open: dode Mission Control-UI-code verwijderen en volledige onafhankelijke
ingelogde web- en mobiele acceptatie. De lokale en CI-bewijzen hierboven zijn geen
live-productacceptatie.

De uiteindelijke document-SHA `e26a1b4d049a1aa57bd19f96503e2b79155fbe99`
doorliep alle vijf main-CI-jobs en Auto Deploy; backend-health en frontend-
buildinfo gaven beide HTTP 200 en exact die SHA. Onafhankelijke ingelogde
desktop-QA op die SHA gaf een gedeeltelijk geslaagd oordeel: Score 2.0,
ETH-plan, strategie, Paper-bot, pauze na refresh en FINN-teruglezing werkten.
QA vond drie herstelpunten: afronden van een ETH-onboarding opende BTC, een
overgeslagen Paper-beoordeling gaf geen specifieke datumreden, en de feed
sorteerde oude prioriteitsmeldingen tussen nieuwe gebeurtenissen. De rauwe
`/onboarding/plan.txt`-route trad alleen in een oude tab tijdens een
deploywissel op; dezelfde overgang werkte na een verse paginalading. QA
heeft registratie vanaf nul, een positieve Paper-beslissing en ingelogd
mobiel niet afgetekend; de simulator meldde `API OFFLINE`.

De vervolgkandidaat op `codex/finn-cutover-qa-fixes` draagt de gekozen asset
door naar het dashboard, geeft de getypeerde engine-redenen `not_due` en
`already_executed` door aan de Paper-UI, en sorteert de feed op gebeurtenistijd.
De actieve feed voegt dezelfde gebeurtenissleutel al samen; historie blijft
leesbaar. Lokale validatie van deze batch: backend **3523 geslaagd, 3 bestaande
skips**; webbuild, typecheck, i18n-lint, 15 i18n-tests, 27 commandchecks,
8 voorsteltests en `audit:high` geslaagd (één bestaande moderate Next.js-
advisory). De lokale workeractiecontractmatrix slaagde **16/16** en de
adaptertests **19/19** (artifact SHA-256
`55db4acb33e4aa70b49f23b88aaed4a3cfbecb77c32b9abc748e421cbdaaa2ad`).
De echte Luna/Responses-regressie slaagde **109/109** op operatie en velden,
met nul provider-, schema-, timeout-, parse- of validatiefouten (artifact
SHA-256 `188a109b55f1033314276c5785615d9a8e8b6c0d81686749b94104a523511877`).
[PR #454](https://github.com/gvangalen/antigravity-trading-tool/pull/454)
is gemerged als `971ebc5b1dd4452ee44ee57c56f5443c9f854de4`.
Alle vijf PR- en [main-CI-jobs](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39476383389)
slaagden. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39476766922)
slaagde; daarna gaven publieke backend-health en frontend-buildinfo ieder
HTTP 200 en exact die SHA. Deze statuswijziging krijgt zelf een nieuwe SHA;
de uiteindelijke runtime-identiteit moest opnieuw worden geverifieerd voor
de gerichte live herkeuring. Het resultaat staat hieronder.

De bestaande QA Agent herkeurde de definitieve document-SHA
`2664fe1fb675f226e0dd4e627d3c8995f132a87b` ingelogd op productie.
Backend en frontend toonden beide die SHA. De normale ETH-onboarding ging nu door
naar `/dashboard?symbol=ETH`; een BTC-Paper-DCA buiten de vrijdagplanning gaf
een specifieke `niet aan de beurt`-uitleg zonder nieuwe beslissing of order.
FINN las de BTC-scores 40/20/40, benchmark 33, vrijdagcadans, €75 per uitvoering
en €300 botlimiet correct terug. De feed bleef gedeeltelijk fout: de lijst
staat op `created_at`, maar web en mobiel toonden `updated_at`; dat moment
verandert bij lezen en bij het schrijven van de AI-tekst. Daardoor lijken de
zichtbare datums niet aflopend. De afzonderlijke `already_executed`-tak, een
positieve Paper-beslissing, nieuwe registratie en ingelogd mobiel zijn in die
run niet afgetekend. Een contextloos geopende afrondpagina viel nog op de
bestaande actieve asset terug; de normale ETH-overgang werkte.

Vervolgkandidaat `codex/finn-agent-cutover-final`: de web- en mobiele feed
tonen nu het `created_at`-moment dat de API ook voor de volgorde gebruikt.
Webbuild, webtypecheck, 27 commandtests, 15 i18n-tests, 8 voorsteltests,
i18n-lint en `audit:high` slaagden; de audit meldt één moderate Next.js-
advisory. Mobiele typecheck, 16 chattests, web-, iOS- en Android-bundels en
lint met nul errors (110 bestaande waarschuwingen) slaagden na `npm ci` in de
geïsoleerde checkout. Dit is lokale validatie, geen nieuwe live-acceptatie.
Backendactiecontracten, score- en uitvoeringscode en Responses-adapter zijn
ongewijzigd sinds de hierboven gemeten 3523 backendtests, 16/16 workeracties,
19/19 adaptertests en 109/109 echte-providerregressie. Deze kandidaat wijzigt
uitsluitend welk bestaand API-tijdveld web en mobiel tonen.
[PR #456](https://github.com/gvangalen/antigravity-trading-tool/pull/456)
is gemerged als `1cf720404d79c7f31220b6a58ecffe4b2b29c8e3`.
Alle vijf PR-CI-jobs en alle vijf [main-CI-jobs](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39479585377)
slaagden. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39479993288)
slaagde; daarna gaven publieke backend-health en frontend-buildinfo ieder
HTTP 200 en exact die SHA. Deze statuscommit krijgt zelf een nieuwe SHA;
Build moet daarvan opnieuw de CI-, deployment- en publieke identiteit
controleren voordat de bestaande QA Agent een gericht feedverdict geeft.

## Weekreflectie voor alle gebruikers

Phase: `LIVE_AWAITING_TRADE_FIXTURE_QA`. [PR #442](https://github.com/gvangalen/antigravity-trading-tool/pull/442) vervangt het rollende
zevendaagse trade-overzicht door een per gebruiker opgeslagen reflectie voor
een afgeronde kalenderweek (maandag tot en met zondag, Europe/Amsterdam). De
weekselector toont de samenvatting van die week; individuele afgesloten trades
blijven direct beschikbaar in de volledige dossierlijst. Een maandagtaak legt de
voorgaande week vast en een eigenaargebonden leesactie kan gemiste of oude
weken alsnog materialiseren. Later toegevoegd bewijs werkt dezelfde opgeslagen
week bij. De productieconfiguratie schakelt Trade Reviews voor alle accounts
in, ook als een oude beschermde allowlist of PM2-omgeving is achtergebleven.
De individuele trade-analyse en het Marktrapport behouden hun eigen functie.

Build-bewijs vóór kandidaat: **3937 backendtests geslaagd, 3 bestaande skips**;
na de laatste dossierlijstcorrectie slaagden 30 gerichte tests voor trade-review
en deployobservatie. De vijf [PR-CI-jobs](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39308251149)
en vijf [main-CI-jobs](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39308720335) slaagden.
Frontend productiebuild, typecheck, i18n-lint, 15 i18n-tests en 26
commandchecks geslaagd. `audit:high` slaagde met alleen een bestaande moderate
Next.js-advisory. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39309089818)
slaagde. Daarna gaven backend-health en frontend-buildinfo HTTP 200 met
dezelfde product-SHA `f11ffdfd4823ff32c4e7e50daac92673c058aaf3`.

Onafhankelijke gerichte browser-QA op SHA `10030d64c05d5fc58def21e5a9d52643b42a4de8`
bevestigde dat het ingelogde Test QA Agent-account `/report` zonder allowlistmelding
opent. De afgeronde week van 12 oktober en het opgeslagen lege weekoverzicht
bleven na refresh en in een nieuwe tab zichtbaar. Dit account had nul afgesloten
trades en geen gekoppelde exchange; een gevuld weekoverzicht, direct beschikbaar
dossier in de lopende week, een nieuwe login en eigenaarsscheiding tussen twee
accounts zijn daardoor niet live bewezen. Dezelfde QA vond op 390 px horizontale
overflow. [PR #447](https://github.com/gvangalen/antigravity-trading-tool/pull/447)
en [PR #449](https://github.com/gvangalen/antigravity-trading-tool/pull/449)
herstelden de periodeknoppen, rapportacties en verificatievoet. Op live product-SHA
`9dca28f9287a0b59cf266bd7ce44845f229d9ba8` mat onafhankelijke QA na
expliciete reload `scrollWidth=390` en `clientWidth=390`; alle vier
periodeknoppen waren bedienbaar en de mobiele overflowfix kreeg een gericht
`ACCEPTED`. [Main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39315079232)
en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39315366826)
slaagden; backend en frontend gaven HTTP 200 met diezelfde SHA. De positieve
tradeflow vereist nog onafhankelijke QA met veilig afgesloten testtrades.

## Reflectie-indeling: afgesloten trades en Marktrapport

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. [PR #440](https://github.com/gvangalen/antigravity-trading-tool/pull/440)
is gemerged als product-SHA `be031a73572bc3b6c2a1119630ab3fe6a29778b2`.
De Reflectiepagina toont bovenaan één FINN-reflectie met een rollend overzicht
van afgesloten trades uit de afgelopen zeven dagen en toegang tot de
trade-dossiers. Het bestaande marktgerichte rapport staat daaronder als
Marktrapport. Dit is nog geen vast opgeslagen wekelijks reflectierapport.

Build-bewijs: **3935 backendtests geslaagd, 3 bestaande skips**; de gerichte
trade-reviewtest **18/18**; frontend productiebuild, typecheck, i18n-lint en
15 i18n-tests geslaagd. Alle vijf [PR-CI-jobs](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39301553867)
en [main-CI-jobs](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39302204450)
slaagden. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39302438495)
slaagde; daarna gaven backend-health en frontend-buildinfo ieder HTTP 200 met
exact die product-SHA. Deze documentcorrectie krijgt zelf een nieuwe SHA;
controleer de uiteindelijke runtime-identiteit opnieuw. Onafhankelijke
ingelogde browser-QA van de nieuwe pagina ontbreekt nog; de eerdere
Trade Reviews-verdicts gelden niet automatisch voor deze indeling.

## Hervatte onboarding: opgeslagen setup en watchlist

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. Onafhankelijke browser-QA op productie-SHA
`7a63c824fd321023effc12b0b7756ee1b3b37ed4` vond dat de hervatte
onboarding maandag en geen scorevoorwaarde toonde, terwijl dezelfde opgeslagen
setup in Mijn Plan vrijdag en de band Onder druk had. De onboarding gebruikte
de actieve setupmatch als formulierbron; die projectie bevat geen DCA-weekdag
of scoregrenzen. De lokale reparatie leest volledige eigenaargebonden
setuprecords en toont het opgeslagen ritme en de scorevoorwaarde in de
controlekaart. Watchlist-verwijdering wacht op een geslaagde serveractie en
ververst de gedeelde cache; de Nederlandse bevestiging heeft nu Annuleren.
Asset toevoegen opent meteen de assetkeuze. Onboarding-copy onderscheidt een
opgeslagen plan of bot van een uitgevoerde Paper-beslissing.

Build-bewijs: 16 gerichte onboarding-handofftests, 9 setupchecks, 15
i18n-tests en 26 commandchecks geslaagd; webbuild, typecheck en i18n-lint
geslaagd. `audit:high` slaagde met alleen een bestaande moderate
Next.js-advisory. Er zijn geen backend-, actiecontract- of modelpaden gewijzigd.
[PR #435](https://github.com/gvangalen/antigravity-trading-tool/pull/435)
is gemerged als `0ea6ffd1c9f0cc5f9f0f91d51b85cf6ba197c2d8`. Alle vijf
PR- en [main-CI-controles](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39291827965)
slaagden. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39292092235)
slaagde; daarna gaven `https://tradamind.com/api/health` en
`https://tradamind.com/build-info.json` ieder HTTP 200 en exact die SHA.
Deze documentcorrectie krijgt zelf een nieuwe SHA; QA controleert de
uiteindelijke runtime-identiteit opnieuw. De ingelogde vrijdag-plus-Onder-druk-
herkeuring, verse registratie, tweede eigenaar en mobiele runtime zijn nog
niet afgetekend.

## Coachvervolg: gekozen setup bij scorevergelijking

Phase: `LOCAL_READY_FOR_CANDIDATE`. Onafhankelijke ingelogde browser-QA op
productie-SHA `1485061c7afdc7da5005090a6d1dd5a462a65274` vond de eerdere
generieke FOMO-terugval niet terug: planvraag, bezwaar, dag en Paper-bot kregen
inhoudelijke antwoorden zonder order. De scorevraag over **deze** vrijdagse
BTC-setup koppelde Markt 40, Macro 65 en Technisch 40 echter eerst aan een
andere BTC-setup met band 34–55. De bedoelde setup heeft band 26–45 en werd
pas na expliciete hernoeming goed gelezen. Dit was een bestaand QA-account,
geen nieuwe-gebruikerproef. QA noemt de flow gedeeltelijk geslaagd.

De lokale reparatie draagt de laatst eigenaargebonden bewezen setup door
tussenliggende read-only coachbeurten, ook wanneer zo'n beurt alleen naar de
bot verwijst. Een enkelvoudige score- of inventarisvraag bindt aan de
expliciet genoemde eigenaargebonden setup of aan die bewezen gespreksreferentie;
een scoretool geeft dan slechts de match van dat setup-ID terug. Meervoudige
collectievragen blijven volledige collecties. De strategieweergave vermeldt
nu het eurobedrag **per uitvoering** in NL, EN en DE.

Build-bewijs vóór kandidaat: **3934 backendtests geslaagd, 3 bestaande skips**;
lokale worker-gedreven actiecontractmatrix **16/16** (artifact SHA-256
`1edca8896b4ee43c519d3fc1f126c5bab2222fd4facd000f91f38b8474c0886b`);
een echte Luna/Responses-proef met twee opgeslagen BTC-DCA's en zes
opeenvolgende beurten eindigde **6/6 completed** met de gekozen setup als enige
scorematch in de laatste beurt. Deze proef gebruikte dezelfde lichte
read-only antwoordgrens als productie; een eerdere lokale run zonder die
instelling liet zien dat de oude zware verifier een inhoudelijk modelantwoord
kon vervangen. Webbuild, typecheck, i18n-, command-, proposalchecks en de
high-severity auditpoort slaagden; audit meldde alleen de bestaande moderate
Next.js-advisory. Er is nog geen nieuwe deployment of onafhankelijke QA van
deze reparatie geclaimd.

## Nieuwe gebruiker: doorlopende DCA-coaching en onboarding

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. De reparatie is gemerged via
[PR #430](https://github.com/gvangalen/antigravity-trading-tool/pull/430)
als product-SHA `f4757a3b021c614b3f9405fb7b7196b351737395`.
Alle vijf PR-checks, [main-CI run 39223651879](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39223651879)
en [Auto Deploy run 39223891517](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39223891517)
slaagden. Daarna gaven backend-health en frontend-buildinfo ieder HTTP 200
en exact die SHA. Deze statuswijziging krijgt zelf een nieuwe SHA; QA controleert
de uiteindelijke live-identiteit opnieuw. Onafhankelijke browser-QA op
productie-SHA `735c0f1fbb36100b66c900b5d2089e3ee11aac67` gaf
`NOT_ACCEPTED`: drie read-only vervolgvragen vielen terug op een generieke fout.
Dezelfde proef vond onduidelijkheid over het DCA-bedrag per uitvoering,
technische indicatorcodes in de keuzelijst en een onvoldoende uitgelegde
DCA-scorevoorwaarde. Native mobiel, gesloten-tradereview, tweede eigenaar en
herlogin vielen buiten die proef.

De begrensde productie-runcontractdiagnose [run 39221548253](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39221548253)
vond voor de drie terminale beurten `no_evidence_available` zonder toolaanroep.
De opgeslagen antwoordvorm was driemaal dezelfde vaste weigering voor een
koopuitvoering; de huidige request-preprocessor classificeerde die volledige
vragen als `execute`, hoewel de eerste vraagzin telkens read-only was. De
backend en interactieve FINN-worker meldden de lichte leesgrens als ingeschakeld.
Dit is de aangetoonde routefout, niet een providerstoring of een ontbrekende
Score 2.0-bron. De reparatie onderscheidt bespreking van kopen van een aan
FINN gerichte order en behandelt een echte niet-ondersteunde order als een
afgeronde veilige weigering zonder bewijsverifier.

Lokaal: **3929 backendtests geslaagd, 3 bestaande skips**; gerichte
verzoekclassificatie **356/356**; de worker-gedreven actiecontractmatrix
**16/16** (artifact SHA-256
`aaf5925b2824a6e4acd985287380e19b76292c4019b789ae401ac43d4eca97af`);
een echte Luna/Responses-proef met een opgeslagen vrijdag-DCA-plan en vijf
opeenvolgende vragen eindigde vijfmaal `completed`, zonder voorstel of order.
Frontendbuild, typecheck, i18n-, command- en proposalchecks zijn geslaagd;
`audit:high` gaf alleen een bestaande moderate Next.js-melding. Dit is
Build-bewijs; een nieuwe ingelogde productieherkeuring en onafhankelijk
QA-verdict ontbreken nog.

## Gesloten Paper-trade: Reflectie en FINN-vervolgvragen

Phase: `INDEPENDENT_DESKTOP_QA_ACCEPTED` voor de gerichte Paper-reflectie- en
coachflow. De drie reparaties zijn gemerged via [PR #422](https://github.com/gvangalen/antigravity-trading-tool/pull/422),
[PR #423](https://github.com/gvangalen/antigravity-trading-tool/pull/423) en
[PR #424](https://github.com/gvangalen/antigravity-trading-tool/pull/424).
Op product-SHA `8dea1147cf6112355bf599e9b7d8b7d6979b3f8b` slaagden alle
vijf PR-controles, [main-CI run 39164257770](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39164257770)
en [Auto Deploy run 39164419460](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39164419460).
Backend-health en frontend-buildinfo gaven voor en na onafhankelijke QA beide
HTTP 200 met dezelfde SHA.

De eerste live herkeuring bevestigde twee blijvende gesloten BTC-Paper-dossiers,
het zevendaagse overzicht, een werkende en na refresh bewaarde dossiervraag,
en een Paper-resultaatlabel voor virtuele kasstromen. De tweede reparatie maakte
ook de oude opgeslagen analysetekst en het label “Jouw vraag” correct. De
hoofdchat kon de reviews toen nog niet lezen. De oorzaak in code was een
`max(...)` van een botbeslissing zonder tijdzone en een gesloten trade met
tijdzone. De derde reparatie normaliseert die tijdstippen naar UTC en heeft een
regressietest met beide soorten records. De exacte productie-exceptie is zonder
runtrace niet onafhankelijk vastgelegd.

De laatste onafhankelijke ingelogde browserproef op dezelfde product-SHA
beantwoordde de exacte vraag naar de laatst gesloten BTC-Papertrade met bot
“QA Paper Full Close 1810”, sluitdatum 18 oktober en opgeslagen resultaat
`−€0,25` uit virtuele kasstromen. De veilige leervraag gebruikte het
vastgelegde instap- en uitstapmoment en maakte geen plantrouw of motivatie op.
Er verscheen geen voorstel of order, geen HTTP- of consolefout. FINN noemde het
reviewnummer niet zelf; de bot en het resultaat kwamen overeen met dossier #4.
De QA-allowlisttoegang voor dit browseraccount is na afloop weer verwijderd via
[run 39164622128](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39164622128).

Lokale validatie: **3925 backendtests geslaagd, 3 bestaande skips**; webbuild,
typecheck, i18n-, command- en proposalchecks geslaagd; actiecontractmatrix
**16/16** zonder Live-order. Echte Luna/Responses-proeven voor twee
dossiervragen en de selectorevaluaties **20/20** en **109/109** slaagden.
Het afzonderlijke dagelijkse rapport is niet de plek voor per-tradereflectie.
Algemene Trade Review-uitrol, gekoppelde exchange-import en de mobiele flow
blijven buiten deze geaccepteerde desktop-Paper-scope.

## Desktopbrowser: 100% Paper-sluiting en Trade Review-toegang

Phase: `INDEPENDENT_DESKTOP_QA_ACCEPTED` voor de gerichte Paper-sluitingsflow. De samenhangende
desktopreparatie is gemerged via [PR #419](https://github.com/gvangalen/antigravity-trading-tool/pull/419)
als `f226d5574102c8aa64440416d3b010233d44f82a`. Alle vijf PR-controles,
[main-CI run 39155573979](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39155573979)
en [Auto Deploy run 39155727175](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39155727175)
slaagden. Backend-health en frontend-buildinfo gaven daarna ieder HTTP 200
en exact die SHA. De statuscommit krijgt een nieuwe SHA; QA controleert de
uiteindelijke publieke identiteit opnieuw.

De vorige onafhankelijke browsertest op `7bf7b748d34db2f8de6f1c91cb2a0f4f63f33de0`
sloot wel een volledige virtuele BTC-positie en bevestigde na refresh
`0 BTC`, Paper-cash `€999,62` en resultaat `−€0,38`. De 100%-knop vulde echter
`0,00138 BTC` in plaats van de volledige `0,00138012 BTC`; het resultaatbadge
toonde ten onrechte `−100,00%`; en Reflectie was voor het gebruikte nieuwe
browser-QA-account uitgeschakeld. Die desktopflow kreeg `NOT_ACCEPTED`.

De nieuwe code bewaart bij 100% Paper-verkoop de exacte opgeslagen hoeveelheid.
De botkaart berekent het euroresultaat uit positie plus netto uitvoeringskasstroom
en gebruikt bruto uitgevoerde aankopen als noemer voor het resultaatpercentage;
bij ontbrekende bewijsvelden toont zij geen verzonnen percentage. Lokale
gerichte regressies, **3917 backendtests** met 3 bestaande skips, webbuild,
typecheck, i18n-, command- en proposalchecks slaagden. `audit:high` slaagde
met één moderate Next.js-advisory. De FINN-chat-, actiecontract- en
Responses-selectorroutes zijn in deze batch niet gewijzigd; er is geen nieuwe
echte-providerproef of geïsoleerde actiecontractmatrix voor deze batch
geclaimd.

De handmatige [QA-toegangsrun 39155820001](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39155820001)
slaagde: uitsluitend het gebruikte browser-QA-account is aan de bestaande
Trade Review-allowlist toegevoegd. De algemene rollout blijft uit. Na de
PM2-herstart meldden backend en frontend nog steeds HTTP 200 en dezelfde
product-SHA. Onafhankelijke QA controleerde backend en frontend op
`593fb7e92f54e837a1c179f82ae015980d143ae4`. Na refresh toonde de
botkaart voor een gesloten virtuele positie `−€0,38 (−0,38%)` op €100
uitgevoerde aankopen. Reflectie toonde één gesloten, eigenaargebonden
Paper-dossier met koop, verkoop en FINN-analyse; het dossier bleef na een
harde refresh bestaan. Er waren geen browser-errors of warnings.

Een aparte Paper-testbot kocht virtueel `0,00138088 BTC`. De knop **100%
verkopen** selecteerde precies die opgeslagen hoeveelheid; de bevestigde
verkoop bracht de positie op `0 BTC`. Na refresh waren beide uitgevoerde
trades aanwezig en bleef de bot gepauzeerd. De test gebruikte geen exchange
en deed geen Live-order. De oorspronkelijke botlimieten werden niet verruimd.
Dit accepteert de gerichte desktop-Paper-sluiting en Trade Review-weergave;
het bewijst geen plantrouw wanneer bij de trade geen oorspronkelijk plan is
vastgelegd. Mobiele simulator en gekoppelde exchange-import blijven
uitgesteld volgens de huidige desktopprioriteit.

## Desktopbrowser: volledige virtuele Paper-positie sluiten

Phase: `INDEPENDENT_BROWSER_QA_NOT_ACCEPTED`. De sluitingsfix is gemerged via
[PR #417](https://github.com/gvangalen/antigravity-trading-tool/pull/417)
als `7cf786ef611e78483e99e873d3cf28eb679bb318`. Alle vijf PR-controles,
[main-CI run 39153467115](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39153467115)
en [Auto Deploy run 39153614555](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39153614555)
slaagden. Daarna gaven de publieke backend-health en frontend-buildinfo
ieder HTTP 200 en exact die SHA. Deze statuscommit verandert zelf de SHA;
QA bindt de herkeuring aan de uiteindelijke publieke identiteit.
Onafhankelijke QA op eerdere live SHA
`dddbe4a88ce1f8a0312822291a1c936e16c55d65` bevestigde nu dat de
minimumorder **€100** was, een €50-preview terecht werd geweigerd en een
€100-Paper-koop na expliciete bevestiging slaagde. De virtuele positie bleef
zichtbaar. De volledige verkoop kreeg wel een toegestane preview van circa
€99,74, maar de bevestiging gaf HTTP 400 omdat de minimumorder opnieuw op de
verkoop werd toegepast. De aankoopkosten maken de volledige positie net
kleiner dan €100. De positie bleef open; er is geen Live-order. De gesloten
Trade Review is daarom nog niet afgetekend.

De lokale kandidaat behandelt een volledige sluiting van een bestaande
virtuele Paper-positie als uitzondering op de minimumorder. Een gedeeltelijke
Paper-verkoop onder het minimum wordt al in de preview geweigerd. Voor Live
blijft de bestaande minimumcontrole gelden. Preview en bevestiging gebruiken
dezelfde eigenaargebonden positiehoeveelheid; de gerichte regressie voor
Paper-volledige sluiting, Paper-gedeeltelijke verkoop en Live-grens slaagt.
De volledige backend-suite slaagt met **3916 passed, 3 bestaande skips**.
Frontend, FINN-action contracts en Luna/Responses zijn niet gewijzigd; hun
laatste gemeten lokale checks blijven voor die paden van toepassing. CI,
deployment en onafhankelijke browserherkeuring volgen.

## Desktopbrowser: zichtbare Paper-ordergrens

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. De grensuitleg is gemerged via
[PR #415](https://github.com/gvangalen/antigravity-trading-tool/pull/415)
als `3c231aa4e3e2559cae64fc3f24b7fe30febdeae6`. Alle vijf PR-controles,
[main-CI run 39152228707](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39152228707)
en [Auto Deploy run 39152381530](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39152381530)
slaagden. De publieke backend-health en frontend-buildinfo gaven daarna
ieder HTTP 200 en exact die SHA. Deze statuscommit krijgt opnieuw een SHA;
QA controleert de uiteindelijke live-identiteit rechtstreeks. Onafhankelijke
QA gaf op eerdere live SHA
`204b76afe3b1d8aca8b323acabec328dabd8f67f` `NOT_ACCEPTED` voor de
volledige desktop-scope. De ontbrekende orderreferentie-400 is opgelost; de
handmatige Paper-preview blokkeerde €10 en €50 met de brede melding dat cash
of een botlimiet tekortschiet. De UI toonde €1.000 virtueel kassaldo, €100
daglimiet en €100 maximum per order, maar geen minimumorder. De automatische
botbeslissing gaf apart `Geen voorstel`/€0 toegestane order bij confidence 0;
QA voerde daarom geen €100-preview of order uit. Geen gesloten positie of
Trade Review kon in deze account worden bevestigd. De lege feed, navigatie en
gesprekbehoud slaagden; een werkelijk verlopen feeditem was in die run niet
beschikbaar. De bot bleef Paper en is door QA gepauzeerd achtergelaten.

Build heeft de Paper-voorvertoning lokaal aangepast om de specifieke
guardrailreden te bewaren, inclusief het opgeslagen minimumorderbedrag als
dat de blokkade veroorzaakt. De botdetails tonen nu de minimumorder naast
de overige limieten in NL/EN/DE. Veiligheidsgrenzen en orderuitvoering worden
niet versoepeld. Een gerichte serviceproef voor het specifieke minimum en een
voor het lege kassaldo slagen. De volledige backend-suite slaagt met
**3915 passed, 3 bestaande skips**. Frontend build, typecheck, i18n-lint en
-tests, command-, voorstel- en setuptests slagen; de high-severity audit slaagt
met één bestaande moderate Next.js-melding. Luna/Responses, FINN-operaties
en de automatische botbeslissing zijn niet gewijzigd. Na deployment moet
onafhankelijke QA de zichtbare minimumorder en precieze previewreden toetsen;
een Paper-open/-close en Trade Review vereisen daarnaast een geldig
eigenaargebonden Paper-scenario met passende voorwaarden.

## Desktopbrowser: Paper-voorvertoning en verlopen feeditem

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. De reparatie is gemerged via
[PR #413](https://github.com/gvangalen/antigravity-trading-tool/pull/413)
als `04cf7142a9a0b7a810091ff2683611ec898a457c`. Alle vijf PR-controles,
[main-CI run 39150489286](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39150489286)
en [Auto Deploy run 39150638924](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39150638924)
slaagden. Daarna gaven `https://tradamind.com/api/health` en
`https://tradamind.com/build-info.json` ieder HTTP 200 en exact die SHA.
Deze statuscommit maakt weer een nieuwe SHA; QA bindt haar test aan de
uiteindelijke publieke backend- en frontendidentiteit. Op eerdere live SHA
`19c6fdf7e4c0ca86f8cda0c760eba0f36e7230fe` vond onafhankelijke QA in
een nieuw, via de browser geregistreerd account twee blokkades. De handmatige
Paper-ordervoorvertoning gaf HTTP 400 (`Een unieke orderreferentie is vereist
voor Paper`), waardoor geen order of Trade Review kon worden gemaakt. Een
zichtbare feedmelding die door gewijzigde scoretoestand niet langer actief
was, gaf bij `Afhandelen` HTTP 404 en bleef als verouderde actie staan. Een
andere actuele melding kon wel worden afgehandeld; de lege feed bleef na
refresh leeg. De bot had afzonderlijk virtueel Paper-startkapitaal en een
budgetlimiet; er was geen Live-order.

Build traceerde de Paper-fout tot de frontend-API-adapter: het orderpaneel
maakte een unieke `idempotency_key`, maar `previewManualOrder` liet die weg uit
de POST-body. De adapter stuurt hem nu mee. Bij een feedstatus-404 haalt de
webfeed opnieuw de actieve eigenaargebonden lijst op, zodat het verlopen item
verdwijnt. De gerichte regressies voor de orderreferentie en 404-herstel
slagen; frontend build, typecheck, i18n-, command-, voorstel- en setuptests
slagen. De volledige backend-suite is **3914 passed, 3 bestaande skips**.
De high-severity audit slaagt met één bestaande moderate Next.js-melding.
Backendactiecontracten, Score 2.0, botuitvoering en Luna/Responses zijn in
deze kandidaat niet gewijzigd; eerdere lokale worker- en providerbewijzen
blijven voor die paden van toepassing. De browser-QA voor een daadwerkelijke
Paper-voorvertoning, bevestigde virtuele fill en Trade Review moet op de
nieuwe live SHA opnieuw worden uitgevoerd. De mobiele eindacceptatie en een
geautoriseerde linked-exchange-import blijven buiten deze desktopronde open.

## Desktopbrowser-herkeuring en gemengde frontendbundle

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. De herstelkandidaat is via
[PR #411](https://github.com/gvangalen/antigravity-trading-tool/pull/411)
gemerged als `43933d77f208d73608a633833e9be2951a2a2df1`. Alle vijf
PR-controles, [main-CI run 39148728004](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39148728004)
en [Auto Deploy run 39148892306](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39148892306)
slaagden. Backend-health en frontend-buildinfo gaven daarna ieder HTTP 200
met exact die SHA. Deze statuscommit creëert opnieuw een SHA; QA verifieert
de uiteindelijke live-identiteit via haar preflight.

Onafhankelijke ingelogde browser-QA op eerdere live SHA
`85ed755aa13c4b18c6571949328adc40373e32b3` zag een gevulde FINN-feed
die bij paginawissel en refresh gelijk bleef, twee onderscheiden BTC-plannen,
een contextvaste read-only chat en een Paper-bot met €1.000 budgetlimiet maar
zonder ingesteld virtueel kassaldo. Analyse en Mijn Plan toonden daarna
dezelfde gecombineerde benchmarkscore 30. De eerste navigatie van Mijn Plan
naar Analyse crashte echter met `TypeError: (0 , tz.bF) is not a function` in
een Next.js-chunk; een volledige refresh herstelde Analyse. Het betrokken
productiechunk roept `bF` aan en de huidige gekoppelde chunk exporteert die
functie. Dit past bij een tab met een gemengde oude en nieuwe chunkgraph, maar
de oorspronkelijke clientbundle van de QA-tab is niet vastgelegd.

De kandidaat `codex/web-stale-chunk-recovery` laat een browser-tab zijn
oorspronkelijke deploy-SHA onthouden. Alleen bij dit specifieke type
webpack-exportfout in een Next.js-chunk vergelijkt hij die met de huidige
frontend-buildinfo; bij een daadwerkelijke deploywissel herlaadt hij eenmaal
met cacheverversing. Een identieke SHA of een gewone React-fout wordt niet
automatisch herladen. De gerichte regressieproef slaagde 3/3; webbuild,
typecheck, i18n-, chat-, voorstel- en setupcontroles en de volledige
backend-suite (3914 passed, 3 bestaande skips) slaagden. De bestaande losse
`release-hardening.test.mjs` heeft drie oudere bot-assertions die niet in de
canonieke webgate zitten; de drie hersteltests in dat bestand zijn groen.
Dit is lokale Build-evidence, geen live herkeuring van de nieuwe kandidaat.
Het QA-account had geen gesloten Paper-trade, dus de Trade Review-browserkaart
is nog niet afgetekend. De eerdere beschermde Paper-/dossierproeven blijven
afzonderlijk bewijs voor de backendketen.

## Volledige Score 2.0-Paper- en Trade Review-acceptatie

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. De mobiele opmaakreparatie is via
[PR #409](https://github.com/gvangalen/antigravity-trading-tool/pull/409)
gemerged als `87321aa4962b600fe7d1cf92cf87d4a5016f58a6`.
Alle vijf PR-controles, [main-CI run 39144967224](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39144967224)
en [Auto Deploy run 39145119006](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39145119006)
slaagden. Backend-health en frontend-buildinfo gaven daarna beide HTTP 200
met exact die SHA. Deze statuswijziging krijgt zelf een nieuwe commit-SHA;
QA controleert de uiteindelijke productie-SHA rechtstreeks via haar preflight.

De onafhankelijke QA op eerdere productie-SHA
`38f5829f70975c6027aeb97b02af72044e8d1ac2` heeft de positieve
setupmatch met een gevulde Paper-order, buiten-grenzen-Hold zonder order,
stale-source-Hold zonder order en de gesloten Paper-roundtrip met dossier en
les bevestigd. Het verdict voor de volledige opdracht bleef `NOT_ACCEPTED`:
de native iPhone-flow was niet onafhankelijk herkeurd en een geautoriseerde,
begrensde linked-exchange-koppeling ontbreekt. Er is geen Live-order uitgevoerd.

Build vond bij een diagnose op de iPhone-simulator dat FINN-chat letterlijke
`**` rond nadruk toonde. De mobiele antwoordweergave rendert die nadruk nu
als vetgedrukte tekst. Op de lokale simulator met de productie-API bleven
chat, sluiten/heropenen en navigeren naar Mijn Plan werken; de statusbalk werd
niet meer door de chatkop overlapt. De volledige backend-suite slaagde lokaal
met 3914 tests en 3 bestaande skips; mobiele typecheck, lint zonder errors,
chat-tests en iOS/Android Expo-bundels slaagden. Dit is Build-diagnose en
geen onafhankelijke mobiele QA. De bestaande QA-agent wordt na deployment
opnieuw voor dezelfde native scope gevraagd; de linked-exchange-import blijft
zonder geautoriseerde QA-koppeling onbewezen.

Op eerdere live SHA
`25281a6e31accd14c4076f1ecbe38b78b4f714f5` slaagden de drie bestaande
beschermde QA-profielen: verouderde score gaf Paper Hold zonder order of
cashwijziging ([run 39138883127](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39138883127));
automatische Paper-uitvoering gaf een gevulde order en tradehistorie zonder
Live-call ([run 39139096449](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39139096449));
Trade Review-lijst en bronroutes gaven een geldig schema
([run 39139188234](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39139188234)).
Onafhankelijke QA gaf voor de volledige opdracht toch `NOT_ACCEPTED`, omdat
deze profielen geen positieve of buiten-grenzen setupmatch en geen gesloten
Paper-dossier met les bewezen. Native iPhone-navigatie was op dat moment niet
bedienbaar; een aanvullende mobiele herkeuring is aangevraagd bij dezelfde
QA-agent. Linked-exchange-import blijft afhankelijk van een geautoriseerde
QA-koppeling en er is geen Live-order uitgevoerd.

De volgende kandidaat voegt drie afzonderlijk beveiligde QA-profielen toe:
Score 2.0 binnen grenzen met Paper-fill, buiten grenzen met Hold op een nog
actieve automatische Paper-bot en een
gesloten Paper-roundtrip met dossier en bevestigde les. Bij een lokale
gesloten-trade-proef bleek bovendien een echte projectiefout: het
planbronmoment had een tijdzone en het ledgerbronmoment niet. De vergelijking
is nu naar UTC genormaliseerd met een regressietest. Op een aparte lokale
PostgreSQL/Redis-stack slaagden de positieve, buiten-grenzen en
gesloten-Paper-proeven. De closed-review-proef controleert twee werkelijke
virtuele fills, projectie, dossierlezing en een bevestigde les via de service;
zij bewijst nog geen volledige mobiele UI. Onafhankelijke mobiele QA kon
inmiddels wel navigeren tussen vijf tabs, maar zag een chatkop tegen de
iOS-statusbalk en had geen gevulde feed of opgeslagen plan in dat QA-account.
De chatmodal heeft daarom nu een eigen SafeAreaProvider; die presentatie moet
nog native worden herkeurd. De volledige backend-suite is lokaal groen met
**3914 passed, 3 skipped** (log-SHA-256
`351e7f8a057c5c4380cb3e20e3a7fddfc8e179ee1593d2f99e694e999fb08bba`).
Frontend- en mobiele build/typecheck/lint- en bundelcontroles slaagden. De
lokale API/Celery/Responses-actiecontractmatrix slaagde **16/16** (artifact
SHA-256 `f683b47698c4d9f4ec08e3a1960b856375620c1700752fb98af69ec15c89948c`)
en echte-providerselectie slaagde **20/20** in development (log-SHA-256
`fa3740a8164194c78921d89bd501c899bf2dbb7f83427a9937036b61258090d3`)
en **109/109** in regression (log-SHA-256
`8ad44e568a23c196fcbe22a140e247676e74a6265b36560e385d726c4543096f`).
Kandidaat [PR #407](https://github.com/gvangalen/antigravity-trading-tool/pull/407)
is gemerged als `920ca6d1f58d2aa4988d4ac8e02ea320fc4fee24`. Alle vijf
PR-controles, [main-CI run 39141819315](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39141819315)
en [Auto Deploy run 39141946235](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39141946235)
slaagden. Backend-health en frontend-buildinfo gaven daarna ieder HTTP 200
en exact de merge-SHA. Een wijziging van dit statusdocument krijgt zelf een
nieuwe SHA; onafhankelijke QA verifieert daarom de uiteindelijke productie-SHA
via haar preflight. De beschermde positieve/buiten-grenzen/gesloten-Paper-
profielen en de native iPhone-correctie zijn nog niet onafhankelijk live
geaccepteerd. Linked-exchange-import blijft zonder geautoriseerde begrensde
koppeling onbewezen; geen Live-order is uitgevoerd.

## Score 2.0 Paper- en Trade Review-QA-herstel

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. De beschermde onafhankelijke QA op
productie-SHA `5ff556adbb8236dc3b627e76a96bc3cbc320bf9b` gaf
`NOT_ACCEPTED`: de stale-score-Paper-proef en de automatische Paper-historieproef
faalden op samengestelde verificatiecodes, de Trade Review-preflight kreeg
geen toegang tot de beschermde QA-eigenaar en de native iPhone-proef bleef
achter een iOS-wachtwoorddialoog. Productie-health en frontend-buildinfo gaven
op 2026-10-18 opnieuw HTTP 200 met exact die SHA. Dit is geen bewijs dat de
nieuwe reparatie live staat of door QA is geaccepteerd.

De nieuwe kandidaat `codex/paper-qa-diagnostics` maakt de Paper-invarianten
afzonderlijk herkenbaar zonder fixturewaarden of eigenaar-ID's te exporteren.
De stale-scorefixture gebruikt de huidige opgeslagen gecombineerde
benchmarkgrenzen; de oude losse categoriegrenzen werden door Score 2.0 terecht
als ongeconfigureerd behandeld. De automatische Paper-proef vergelijkt de
daadwerkelijke gevalideerde EUR-fill, het maximaal goedgekeurde bedrag,
portfolio, grootboek en tradehistorie; zij verwacht niet langer dat de
planningprijs bij uitvoering onveranderd is. De productie-PM2-config voegt
alleen in een expliciete `allowlist`-rollout de bestaande beschermde QA-binding
toe aan de backend- en worker-allowlist, nooit aan de frontend of staging.
Een ongeldig bindingnummer of ongeldige bestaande allowlist blijft gesloten.

Op een aparte wegwerp-PostgreSQL/Redis-stack zijn de actuele Score 2.0-paden
doorlopen: een verouderde bron gaf `insufficient_data` en Paper `hold` zonder
order; een volledige score binnen de setupgrenzen gaf één Paper-buy, een
gevulde order en bijpassende ledger/portfolio; een score buiten de grenzen gaf
`outside_conditions`, Paper `hold`, geen order en ongewijzigd virtueel cash.
De beschermde automatische Paper-proef slaagde lokaal ook bij een EUR-fillprijs
van €60.000 in plaats van de €50.000-planningprijs. Dit is lokale Build-evidence,
geen beschermde productie-QA.

De volledige backend-suite slaagde met **3910 passed, 3 skipped**; log-SHA-256
`c6add19bcf85b304afb00816a06120c7687442789f0e3907c79357a4032dac32`.
De lokale
API/Celery/Responses-actiecontractmatrix slaagde **16/16**, zonder Live- of
brokerorder; artifact SHA-256
`7acea9b3a744e82a94a30c21ad3ac79b7bba94a67938988ecbd3625a51c5d71f`.
Echte-providerselectie slaagde **20/20** in development (SHA-256
`d9e4f3fdcdc505a418b8b34623c05a23286e5cffae81e2ff65fceab29ab96a49`)
en **109/109** in regression (SHA-256
`fe3e992d30d15f89889535cf9d30529fed79a731755c75faa2338286c047b316`).
Frontend productiebuild, typecheck, i18n, command/proposal-tests en audit op
high/critical slaagden; de audit meldt één moderate Next.js-advisory. Mobiele
typecheck, lint zonder errors en iOS/Android Expo-bundels slaagden. Native
iPhone-bediening en de volledige gesloten-trade/linked-exchange-acceptatie
blijven voor onafhankelijke QA; er is geen Live-order uitgevoerd.

Kandidaat [PR #405](https://github.com/gvangalen/antigravity-trading-tool/pull/405)
is gemerged als `44455447be3d814896b50efd518157595a112267`. Alle vijf PR- en
main-CI-checks slaagden; [main-CI run 39138094482](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39138094482)
en [Auto Deploy run 39138235896](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39138235896)
zijn geslaagd. Daarna gaven `https://tradamind.com/api/health` en
`https://tradamind.com/build-info.json` ieder HTTP 200 en exact de merge-SHA.
Deze statuswijziging krijgt zelf een nieuwe SHA; QA controleert de feitelijk
gedeployde SHA in haar eigen preflight. De nieuwe onafhankelijke QA-uitkomst
ontbreekt nog. Build start de beschermde QA-workflow niet zelf en vraagt de
bestaande QA-agent dezelfde drie sporen opnieuw te testen.

## S&P 500 Macro-score en bronactualiteit

Phase: `LIVE_TARGETED_QA_ACCEPTED`. De live browser-QA zag op 2026-10-18
een actuele S&P 500-bronmeting met 63 gedateerde dagen (minimum 5), maar geen
indicatorscore. In code is S&P 500 wel selecteerbaar en heeft het een
90-daagse normalisatie; de automatische Score 2.0-template-installatie bevatte
echter geen expliciete S&P 500-scoreregel. De engine laat bij een ontbrekende
regel bewust de score en daardoor Macro en de gecombineerde benchmark leeg.
De exacte regelstatus in de productie-DB is nog niet rechtstreeks vastgesteld.

Kandidaat [PR #402](https://github.com/gvangalen/antigravity-trading-tool/pull/402)
voegt vijf expliciete scorebanden voor de positie van S&P 500 in het eigen
90-daagse bereik toe: 0–20→20, 20–40→35, 40–60→50, 60–80→65 en
80–100→80. Dit volgt het bestaande principe dat hogere S&P 500-positie een
sterker algemeen risicoklimaat betekent; het is geen zelfstandig koopsignaal.
Gebruikersregels blijven intact. De indicator wordt niet geforceerd bij
ontbrekende, te oude of onvoldoende gedateerde brondata. De UI maakt nu
onderscheid tussen bronactualiteit en scorebeschikbaarheid en kan een
ontbrekende regel apart toelichten. De bestaande periodieke refresh scoort een
ongewijzigde bronmeting opnieuw nadat de regel beschikbaar is.

Lokaal gemeten op de bijgewerkte PR-commit: volledige backend-suite 3907 geslaagd,
3 bestaande skips; frontend productiebuild, typecheck, i18n-lint en gerichte
presentatietests geslaagd. Een aanvullende regressie met 63 gedateerde
S&P 500-brondagen bewees eerst `missing_rule` en daarna een geverifieerde
Macro-score via de nieuwe template; 26 gerichte tests geslaagd. De vijf
eerste PR-CI-jobs en de vijf finale PR-CI-jobs in
[run 39116996590](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39116996590)
slaagden. [Main-CI run 39117146178](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39117146178)
en [Auto Deploy run 39117269095](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39117269095)
slaagden op merge-SHA `2b5def026fb310af0660ed7d7ab21deb46ed8976`.
Daarna gaven `https://tradamind.com/api/health` en
`https://tradamind.com/build-info.json` ieder HTTP 200 en exact die SHA.
De status-only merge hieronder creëert zelf een nieuwe SHA; QA verifieert
de actuele publieke SHA in haar eigen preflight. De status-only merge
[PR #403](https://github.com/gvangalen/antigravity-trading-tool/pull/403)
werd gedeployed als `237b39676ea35522faf8f8b0410e709cf2a3ac04`.
[Main-CI run 39117523123](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39117523123)
en [Auto Deploy run 39117662448](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39117662448)
slaagden; publieke backend-health en frontend-buildinfo gaven beide HTTP 200
met exact die SHA.

Onafhankelijke QA gaf `ACCEPTED` voor de **gerichte ingelogde browserproef**
op die SHA. De [beschermde preflight run 39118221051](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39118221051)
bevestigde checkout, release marker, beide publieke SHA's en QA-authenticatie
(HTTP 200); rapporthash
`4409d4635e2778fac53806ecf740e7296a431b45e6e4457961066184555ba2e4`.
In de browser gaf S&P 500 63/5 gedateerde brondagen, genormaliseerde positie
68/100 en score 65 via de systeemregel. Markt 30, Macro 65 en Technisch 40
leverden benchmark 45. De opgeslagen vrijdag-setup “Onder druk” (26–45)
toonde “Voorwaarden passen”; FINN bevestigde de bovengrensmatch en beloofde
geen aankoop. Verversen, nieuwe tab en leesbaarheid op 390 px slaagden; er
waren geen orders of botacties. Een nieuwe login en een live overgang naar
ontbrekende of te oude bron werden niet getest. Een oudere feedkaart met
ontbrekende-scoretekst was historisch en is niet als actueel defect vastgesteld.
Deze QA-vastlegging is alleen documentatie en krijgt zelf weer een andere
deployment-SHA; het QA-verdict blijft gekoppeld aan de expliciet geteste SHA.

## Eén benchmarkscore en een afzonderlijke setupstatus

Phase: `LIVE_AWAITING_INDEPENDENT_AUTHENTICATED_QA`. De kandidaat
`codex/benchmark-setup-match` is via
[PR #399](https://github.com/gvangalen/antigravity-trading-tool/pull/399)
samengevoegd als `f3bec5c2984e08dbe0e92822f379fd70c39d30ed`.
De gewogen, geverifieerde Markt-, Macro- en Technisch-scores vormen één
benchmarkscore per asset. De vijf leesbare marktsituaties en de opgeslagen
setupvoorwaarden gebruiken dezelfde afgeronde hele score, ook op de vier
decimale grensovergangen. De setupstatus bepaalt of voorwaarden passen;
de nabijheidsscore is alleen weergave en nooit een uitvoeringsvoorwaarde.
Een passende setup garandeert geen aankoop: strategie en veiligheidslimieten
beslissen afzonderlijk. Web, onboarding, Mijn Plan en mobiel leggen dit
met dezelfde begrippen uit. Mobiel leest de owner-scoped marktvergelijking
en noemt een opgeslagen plan zonder actuele match geen concept meer. FINN
meldt bij uitvoering geen planafwijking louter omdat een geldige setup op
de grens een nabijheid van 60/100 heeft.

Lokaal gemeten: volledige backend-suite 3904 geslaagd, 3 bestaande skips;
frontend productiebuild, typecheck, i18n- en gerichte setup/onboarding/FINN-
tests geslaagd; mobiele typecheck, lint met 0 fouten, 13 tests en web-, iOS-
en Android Expo-export geslaagd. Onafhankelijke lokale code-QA vond twee
grens- en statuslabelproblemen. Beide zijn gerepareerd en herkeurd zonder
nieuwe lokale blokkade. Dit is geen ingelogde live QA-acceptatie.

Alle vijf jobs van [PR-CI run 39108878510](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39108878510)
en [Main-CI run 39109046064](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39109046064)
slaagden. [Auto Deploy run 39109163097](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39109163097)
slaagde. Op 2026-10-18 gaven `https://tradamind.com/api/health` en
`https://tradamind.com/build-info.json` ieder HTTP 200 met exact deze SHA.
Deze statusupdate creëert zelf een nieuwe commit en kan opnieuw deployen;
de onafhankelijke QA moet daarom in haar preflight de actuele publieke SHA
vaststellen. De ingelogde browserflow en live setupvergelijking zijn nog
niet onafhankelijk geaccepteerd.

## Opgeslagen marktkeuze blijft een FINN-voorwaarde

Phase: `LIVE_CANDIDATE_AWAITING_INDEPENDENT_QA`. Onafhankelijke live QA op
`69ecb55f6f4237ec6a314d0016dd68da43118bd9` vond een inhoudelijke
tegenstrijdigheid: de nieuwe BTC-vrijdag-DCA had de preset “Onder druk” en
marktgrenzen 26–45 opgeslagen, maar FINN noemde die keuze later slechts
beschrijving en geen vastgelegde voorwaarde. De ruwe grenzen waren wel in de
setup en owner-scoped read aanwezig; de presetbetekenis werd alleen in de
frontend afgeleid, terwijl het afzonderlijke reasoning-contextpad de grenzen
en toelichting uit de feitenprojectie wegliet.

De kandidaat `codex/finn-saved-setup-semantics` leidt de vijf presetnamen
uitsluitend uit exacte opgeslagen grenzen af en levert die samen met de
grenzen aan de getypeerde FINN-leestools, inventaris en reasoning-context.
De modelgrens benoemt apart: setupgeschiktheid, vrije gebruikerstoelichting,
DCA-weekdag en uitvoeringsregels uit de gekoppelde strategie. Er wordt geen
actuele score of aankoop afgeleid. Scorematcher, opgeslagen payload en bot-
uitvoering zijn niet gewijzigd. De vrije setup-toelichting blijft bewust in
de editor en FINN-context: de bestaande producttekst noemt haar achtergrond
voor FINN en schrijft geen weergave op de compacte Mijn Plan-kaart voor.

Lokaal gemeten: 742 gerichte backendtests geslaagd; de volledige backend-suite
3897 geslaagd, 3 bestaande skips. Een geïsoleerde lokale publieke API-route
met synthetische ingelogde gebruiker, echte provider, persistente worker,
polling/SSE en drie beurten slaagde. FINN las vrijdag, preset 26–45, vrije
toelichting en €100 terug, noemde de preset een opgeslagen scorevoorwaarde en
weigerde een gegarandeerde aankoop zonder actuele geverifieerde score te
claimen. De nieuwe test met een tweede repositorysessie controleert ook
owner-scoped teruglezing en scheiding van setup en strategie. Dit is Build-
evidence, geen onafhankelijke live QA-acceptatie. Er is geen action contract
of provideradapter gewijzigd; de volledige action-matrix is daarom voor deze
read-only kandidaat niet van toepassing.

[PR #397](https://github.com/gvangalen/antigravity-trading-tool/pull/397)
werd gemerged als `ce10c07a2e50ea80c3bd6935979646f300d9f722`. Alle vijf
PR-CI-jobs slaagden in
[run 39055755644](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39055755644).
[Main-CI run 39055918490](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39055918490)
en [Auto Deploy run 39056066241](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39056066241)
slaagden op dezelfde SHA. Publieke backend-health en frontend-buildinfo gaven
beide HTTP 200 en `ce10c07a2e50ea80c3bd6935979646f300d9f722` op
2026-10-17. Deze documentatie-update creëert zelf een nieuw commit en kan
een nieuwe deployment-SHA opleveren; QA verifieert daarom de actuele publieke
SHA in haar eigen preflight. De inhoudelijke Build-kandidaat is live, maar
onafhankelijke live QA voor de opgeslagen presetbetekenis is nog niet gedaan.

## Mijn Plan toont alleen werkelijk opgeslagen scoregrenzen

Phase: `LIVE_TARGETED_QA_ACCEPTED_FULL_SCOPE_OPEN`. In de onafhankelijke ingelogde
browserherkeuring van `f1fb815ca115edd3853d57cf795c6d3590f213eb`
bleken de vijf keuzes, Custom, opslag en teruglezing na refresh, de
assetgebonden Plan-status, het terugvinden van een oudere BTC-setup, de
strategiepagina, een conflicterende Automation-link, de volledige
Automation-pagina en een 400px-onboardingweergave functioneel. QA gaf toch
`NOT_ACCEPTED` voor volledige acceptatie: Mijn Plan toonde bij een preset met
ontbrekende macro- en technische scoregrenzen ten onrechte `0–100` voor beide
velden. Een nieuwe Paper-botactie, hostcheckout/release-marker en de editor
zelf op 400px zijn in die run niet bewezen; er waren geen echte orders.

Reparatiebranch `codex/setup-score-summary`, implementatie-SHA
`7faabbd5d2a033c7857289b9c53d17650c3766c2`. Mijn Plan toont nu bij
null-grenzen expliciet `geen grens` en onderscheidt ook eenzijdige grenzen en
een geheel ongefilterde setup. De opgeslagen scorevoorwaarden veranderen
niet. Lokaal gemeten: 24 gerichte setup-, onboarding- en regressietests,
frontendtypecheck, i18n-lint en productiebuild met bijgewerkte `out/`-export
geslaagd. Onafhankelijke read-only code-QA op deze implementatie-SHA vond
geen bevindingen en draaide 28 gerichte tests met 28 geslaagd.

[PR #393](https://github.com/gvangalen/antigravity-trading-tool/pull/393)
werd gemerged als `e7f3ce6d6cf98f19a5851e5bccc7fb4d0c0efc36`. Alle vijf
PR-CI-jobs slaagden in
[run 39042845249](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39042845249).
[Main-CI run 39043025464](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39043025464)
en [Auto Deploy run 39043160991](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39043160991)
slaagden op deze SHA. Backend-health en frontend-buildinfo gaven daarna
beide HTTP 200 en deze SHA. Deze status-only handoff krijgt een nieuwe
deployment-SHA; QA verifieert de werkelijk publieke SHA opnieuw. De
onafhankelijke ingelogde browserherkeuring van deze reparatie is uitgevoerd.
De status-only handoff [PR #394](https://github.com/gvangalen/antigravity-trading-tool/pull/394)
werd gemerged als `596e79b813d97b6b921334cbec0636a8733c2ad1`.
[Main-CI run 39043473355](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39043473355)
en [Auto Deploy run 39043618100](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39043618100)
slaagden; backend-health en frontend-buildinfo gaven HTTP 200 en deze SHA.

Onafhankelijke ingelogde QA gaf `ACCEPTED` voor de **gerichte scoreweergave-
reparatie** op deze live SHA: na het opslaan van markt 26–45 toonde Mijn Plan
ook na een harde refresh `markt 26–45 · macro geen grens · technisch geen grens`.
De vijf keuzes en Custom bleven in de editor zichtbaar. QA herstelde de
oorspronkelijke BTC Custom-grenzen 20–60 / 30–70 / 40–80 en bevestigde die na
refresh. Er was geen bot- of orderactie. De editor op 400px kon in deze laatste
run wegens een vergrendelde Mac niet opnieuw worden bediend. Eenzijdige en
volledig afwezige grenzen zijn in code getest maar niet live als opgeslagen
plan. Dit gerichte verdict is geen volledige acceptatie van alle eerdere
FINN-releaseonderdelen. Deze vastlegging is alleen documentatie en krijgt
zelf een nieuwe SHA; het QA-verdict hierboven blijft gekoppeld aan de
expliciet geteste `596e79b813d97b6b921334cbec0636a8733c2ad1`.

## Marktconditie-ontwerp en onboarding-herstel

Phase: `LIVE_NOT_ACCEPTED_DISPLAY_GAP`. De onafhankelijke live browser-QA
van de vorige kandidaat gaf `NOT_ACCEPTED` op productie-SHA
`b3699c0c06af1e91182e878d306d388aa3479900`: Plan toonde een niet-bestaand
ETH-plan als opgeslagen door accountbrede statusvlaggen, en `/strategy` crashte
met `ReferenceError: activeMarketIndicatorNames is not defined`. Een oude
Automation-link kon bovendien ETH in de URL tonen bij een BTC-strategie. De
volledige Automation-pagina, Paper-botopslag en leesbaarheid van de eerdere
marktkaarten op desktop en 400 px zijn wel live vastgesteld. Opslag van een
nieuwe marktkeuze, meerdere strategieën en de uitgestelde Live-botroute zijn
in die browserproef niet afgetekend.

Reparatiebranch: `codex/market-condition-design`, actuele implementatie-SHA
`d7ddf49801c5ca0937350031fc10d96dabf87a87`. De gedeelde marktkeuze in
onboarding en de ingelogde editor gebruikt vijf compacte regels, een
samenvatting naast de keuze en Custom onder Geavanceerd. De vijf bestaande
scorebereiken en opslagpayload blijven gelijk. Plan toont alleen een
opgeslagen setup en strategie die aantoonbaar bij het gekozen asset en elkaar
horen. Plan vindt ook oudere opgeslagen setups die niet actief of laatst
opgeslagen zijn. Automation ontgrendelt alleen strategieën met een setup voor
het gekozen asset. De marktdata-hook levert weer de gebruikte actieve
indicatornamen; Automation corrigeert een conflicterende assetparameter op
basis van de gekozen strategie.

Lokaal gemeten: frontendtypecheck, i18n-lint, productiebuild met bijgewerkte
`out/`-export, 10 setup-scoretests, 15 i18n-tests en 19 gerichte onboarding-
en strategietests geslaagd. De eerste onafhankelijke code-QA vond twee
randgevallen in de assetkoppeling; na reparatie vond de gerichte read-only
hercontrole op `d7ddf49801c5ca0937350031fc10d96dabf87a87` geen nieuwe
P1/P2 en slaagden 25 gerichte tests. Deze batch wijzigt geen FINN-
actiecontract, workerpad of modelprovider.

[PR #391](https://github.com/gvangalen/antigravity-trading-tool/pull/391)
werd gemerged als `fdaea112002c071ee17d5cc64389063a03c75c0b`. Alle vijf
PR-CI-jobs op de laatste PR-SHA slaagden in
[run 39041274684](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39041274684).
[Main-CI run 39041439938](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39041439938)
en [Auto Deploy run 39041581382](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39041581382)
slaagden op exact de merge-SHA. Daarna gaven
`https://tradamind.com/api/health` en
`https://tradamind.com/build-info.json` beide HTTP 200 en exact deze SHA.
De status-only [PR #392](https://github.com/gvangalen/antigravity-trading-tool/pull/392)
werd daarna gemerged als `f1fb815ca115edd3853d57cf795c6d3590f213eb`.
[Main-CI run 39041922478](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39041922478)
en [Auto Deploy run 39042058195](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39042058195)
slaagden; backend-health en frontend-buildinfo gaven daarna beide HTTP 200
en deze SHA. De onafhankelijke browseruitkomst en de resterende weergavefout
staan bovenaan.

## Leesbare setupcondities en volledige Automation-onboarding

Phase: `DEPLOYED_PENDING_INDEPENDENT_BROWSER_QA`. De gebruiker vroeg op 2026-10-17
om de wijzigingen live te zetten voor browserproeven. Kandidaat:
[PR #389](https://github.com/gvangalen/antigravity-trading-tool/pull/389),
branch `codex/market-condition-cards`, implementatie-SHA
`9bf09be3c3d9cf6f1d0f57e32b746cdb2e66dd96`. De onboarding en de
ingelogde setup-editor tonen vijf leesbare marktsituaties, een zesde Custom-
keuze voor exacte scoregrenzen en een aparte ongefilterde DCA-keuze. De
laatste onboardingstap gebruikt nu `/onboarding/automation` met het
bestaande botformulier in de volledige onboardingomgeving. Een ontbrekende
strategie-ID bij meerdere strategieën leidt tot expliciete selectie;
oude onboardinglinks behouden naam, modus, risicoprofiel en budget.

Gemeten vóór deployment: lokale frontendproductiebuild en typecheck,
i18n-lint en -tests, setup-scoretests en 13 gerichte onboarding-handofftests
geslaagd. De onafhankelijke code-QA vond op de laatste implementatie-SHA
geen codebevindingen en draaide 16 gerichte tests opnieuw met 16 geslaagd.
Alle vijf PR-CI-jobs op die SHA zijn geslaagd: workflow-validation,
backend-tests, frontend-quality, mobile-quality en security-baseline. Deze
batch wijzigt geen FINN-actiecontract, workerpad of modelprovider; de
worker-driven action matrix en real-provider regressie hebben daarom geen
gewijzigd contract om lokaal opnieuw te bewijzen. Dit is geen claim over
live botuitvoering of een onafhankelijke browseracceptatie.

De productmerge is `9d72a1efe3d072ad1dfbbe9f4e964f476a2db4c3`.
[Main-CI run 39038311202](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39038311202)
en [Auto Deploy run 39038447994](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39038447994)
slaagden. Direct daarna gaven `https://tradamind.com/api/health` en
`https://tradamind.com/build-info.json` beide HTTP 200 en exact deze SHA.
Deze status-only handoff krijgt zelf een nieuwe deployment-SHA; QA moet de
werkelijk publieke SHA opnieuw vaststellen. De ingelogde browserproef is nog
niet uitgevoerd. De oudere Trade Reviews-QA-uitkomst `NOT_ACCEPTED` en de
native mobiele bewijsleemte blijven afzonderlijk open.

## Browser-QA reparatie: hervatfout en exchange-autofill

Phase: `LIVE_BROWSER_QA_PASSED_WITH_EVIDENCE_GAPS`. In de onafhankelijke
browserproef op `e0eecd7fec16b50cb1deca5e064da8a6bd58d05f` werkte de
uitgestelde Live-botroute: zonder exchange werd een nieuwe bot gepauzeerd
opgeslagen, bleef hij gepauzeerd na refresh en verscheen de FINN-herinnering.
De bestaande Paper-bot bleef intact; er waren geen orders. **Nu koppelen**
toonde Bitvavo en Bybit met hun sleutelvelden. QA vond nog twee reparaties:
de browser vulde opgeslagen accountgegevens automatisch in Bybit-velden, en
een terecht met HTTP 400 geweigerde Hervatten-actie toonde alleen
`API request failed`. De eerste-bot-onboarding is op dat QA-account niet
bewezen omdat daar al een Paper-bot bestond. Afwijzing specifiek wegens
ontbrekende exchange-sleutels is niet afzonderlijk live getest; ontbrekende
budgetlimieten werden eerst geweigerd.

Op `codex/deferred-exchange-qa-fixes` zijn de exchange-sleutelvelden als
nieuwe wachtwoordvelden gemarkeerd, worden waarden bij wisselen van exchange
gewist en staat browserautofill op het omringende formulier uit. De
botinterface leest voor Hervatten de bruikbare `detail` uit de serverrespons
en gebruikt bij onverwachte responses een lokale fallback. Twee gerichte
frontendregressietests voor API-foutmeldingen en de i18n-/command-/
proposalchecks, frontendtypecheck, productiebuild met bijgewerkte tracked
`out/`-export en audit:high slaagden.
[PR #383](https://github.com/gvangalen/antigravity-trading-tool/pull/383) werd
als `a41992a52e94ad1463f749b87c65bff801f0ba07` gemerged na vijf groene
PR-checks. [Main-CI run 39023454645](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39023454645)
en [Auto Deploy run 39023593524](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39023593524)
slaagden. Publieke backend-health en frontend-buildinfo gaven daarna beide
HTTP 200 en exact deze SHA. Deze status-only handoff krijgt zelf een nieuwe
deployment-SHA; QA verifieert de werkelijk publieke SHA opnieuw. Onafhankelijke
browserherkeuring vond plaats op de daaropvolgende status-only release
`5d4cbe8d3d2c8bc960a3f6c9f569ccec2375d6e7` na geslaagde
[main-CI run 39023809514](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39023809514)
en [Auto Deploy run 39023928275](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39023928275).
QA bevestigde zelfstandig dat productiecheckout, release-marker, publieke
backend-health en frontend-buildinfo exact deze SHA tonen. In de ingelogde
browser bleven de Bitvavo- en Bybit-sleutelvelden leeg ondanks browserautofill;
een providerwissel wiste alleen ingevoerde dummywaarden en Enter/Annuleren
verstuurden het botformulier niet. Hervatten zonder limieten werd geweigerd,
de bot bleef gepauzeerd en de UI toonde de concrete serverreden. Na refresh
bleven de gepauzeerde bot, ontbrekende exchange, nul trades en de FINN-
herinnering met juiste detail-link zichtbaar. Er zijn geen echte sleutels,
exchangeverbinding, brokerorder of live activatie gebruikt. De allereerste
bot-onboarding op een leeg account en de afwijzing uitsluitend wegens
ontbrekende sleutels zijn niet live bewezen; de QA-bot had al een Paper-bot
en ontbrekende budgetlimieten blokkeerden de hervatpoging eerst. De
serverreden bevat nog technische veldnamen. De aparte Trade Reviews- en
native mobiele acceptatie blijven open.

## Exchange optioneel tijdens eerste live-bot-onboarding

Phase: `LIVE_BROWSER_QA_PARTIAL_EVIDENCE_GAPS`. Na de eerste UI-reparatie verduidelijkte
de gebruiker het gewenste contract: exchange-koppeling in onboarding moet
optioneel zijn. Op `codex/deferred-exchange-onboarding` krijgt een nieuwe live
bot de keuze **Later koppelen** (standaard) of **Nu koppelen**. Later slaat de
bot gepauzeerd op; zonder koppeling mag onboarding doorgaan. FINN publiceert
dan een eigenaargebonden feedherinnering. De detailweergave en de
onboarding-afronding tonen expliciet dat er geen orders plaatsvinden. Bij
activatie eist de backend nog steeds actieve exchange-keys en geldige
budgetlimieten. Een live bot met de keuze Nu koppelen wordt pas actief
opgeslagen wanneer de koppelstatus bevestigd is; zonder succesvolle koppeling
wordt hij veilig gepauzeerd opgeslagen.

De gerichte bot- en coachfeedtests slaagden **104/104**. De volledige
backend-suite vóór de laatste extra coachfeed-regressietest slaagde met
**3894 passed, 3 skipped**; de extra test slaagde in de gerichte set.
Frontend typecheck, productiebuild/export, i18n-lint, i18n-/command-/
proposaltests en high-severity audit slaagden; de laatste waarschuwingstekst
is opgenomen in de herbouwde export en de laatste i18n-checks.
[PR #381](https://github.com/gvangalen/antigravity-trading-tool/pull/381) werd
als `0200b80774d7a74428aad5a642fc4ef4cda5ecbb` gemerged na vijf groene
PR-checks. [Main-CI run 39022272014](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39022272014)
en [Auto Deploy run 39022404099](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39022404099)
slaagden. Publieke backend-health en frontend-buildinfo gaven allebei HTTP 200
en exact deze SHA. Een status-only handoff krijgt een eigen deployment-SHA;
QA verifieert de werkelijk publieke SHA opnieuw. De onafhankelijke browser-QA
is uitgevoerd zoals hierboven beschreven. Een eerste QA-preflight keek naar
`143.47.186.148`, de oude rollbackhost, en stopte terecht bij een SHA-mismatch.
De actuele productiehost `134.98.150.125` had daarna zowel in checkout als
`LAST_GOOD_COMMIT` dezelfde SHA als publieke backend en frontend; QA
verifieerde dit zelfstandig vóór de browserproef. De verouderde hostverwijzing
in `deploy_live.sh` en mogelijke QA-configuratie blijft een operationele
follow-up. Er zijn geen echte sleutels of orders voor deze Build-validatie
gebruikt.

## Eerste live bot: exchange-koppeling in aanmaakscherm

Phase: `DEPLOYED_INTERIM_SUPERSEDED_BY_USER_CORRECTION`. De browsermelding van de
gebruiker is gereproduceerd in de code: de backend eist actieve exchange-keys
voor het opslaan van een live bot, terwijl de bestaande koppel-UI pas in de
detailweergave van een reeds opgeslagen bot bereikbaar was. De kandidaat op
`codex/bot-onboarding-exchange-connection` toont de bestaande Bitvavo/Bybit-
koppelstap direct binnen het aanmaakformulier wanneer Live exchange is gekozen.
De knoppen in die stap kunnen het omringende botformulier niet indienen; na
succes ververst de verbindingsstatus en verdwijnt een oude foutmelding. Paper
trading blijft zonder exchange mogelijk. Er is geen backend-, actiecontract-,
provider- of sleutelopslagcontract gewijzigd.

[PR #380](https://github.com/gvangalen/antigravity-trading-tool/pull/380) werd
als `23229cc80e6b740fdffcb8b032922f93689513de` gemerged. Vijf PR-checks,
[main-CI run 39021664788](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39021664788)
en [Auto Deploy run 39021809858](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39021809858)
slaagden. Daarna retourneerden publieke backend-health en frontend-buildinfo
allebei HTTP 200 en exact deze SHA. Deze tussenversie wordt door de
gebruikerscorrectie hierboven opgevolgd.

Lokaal geslaagd: frontend typecheck, productiebuild met bijgewerkte tracked
`out/`-export, i18n-lint, i18n-/command-/proposaltests en high-severity
dependency-audit. De audit meldde één *moderate* Next.js-advisory en nul
high/critical meldingen. De echte sleutelverificatie en de eerste live-bot-
browserflow zijn nog niet getest; er zijn geen API-sleutels of live orders
gebruikt. De aparte Trade Reviews-acceptatie hieronder blijft
`NOT_ACCEPTED` totdat onafhankelijke QA de ontbrekende paden bewijst.

## FINN trade-review live browser candidate

Phase: `INDEPENDENT_BROWSER_QA_NOT_ACCEPTED_EVIDENCE_GAPS`. De gebruiker heeft
expliciet gevraagd om de complete huidige reflectiekandidaat te deployen voor
een onafhankelijke live browserproef. Dit vervangt de voorgaande kandidaat als
actieve FINN-release; de native mobiele `NOT_ACCEPTED`-bewijsleemte hieronder
blijft bestaan en wordt hiermee niet tot een acceptatie verklaard.

Kandidaat: [PR #374](https://github.com/gvangalen/antigravity-trading-tool/pull/374),
productmerge `f0c1a31265b4e7205d7ae89c96b6b89fd13be1ca`. Vijf PR-checks
en [main-CI run 39019374684](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39019374684)
slaagden. [Auto Deploy run 39019503840](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39019503840)
slaagde. Direct daarna retourneerden backend-health en frontend-buildinfo
allebei HTTP 200 en exact deze productmerge-SHA. Een status-only handoff krijgt
een eigen deployment-SHA; QA verifieert altijd de dan werkelijk publieke SHA.
De reflectie-API en workers staan
standaard uit en worden in productie uitsluitend voor het aparte QA-account
met `FINN_TRADE_REVIEW_ROLLOUT=allowlist` en
`FINN_TRADE_REVIEW_USER_IDS=93` geactiveerd. De PM2-config geeft deze twee
instellingen door aan API en alle workers; de gerichte runtimeconfiguratietest
verifieerde ook de gesloten standaard. De volledige backend-suite op deze
batch slaagde met **3892 passed, 3 skipped**. De frontendbuild, typecheck,
i18n-, command- en proposalchecks en high-severity audit gate slaagden op
dezelfde productcode vóór deze uitsluitend operationele PM2-wijziging. De
gecombineerde lokale worker/actiecontractmatrix slaagde **16/16**, zonder
brokerorders of productieverbindingen; artifact SHA-256
`b523645c0c21801f8f640fb32da7a115d77ca65f0ea9f94f6ae10fbc19f68b11`.
De echte provider-developmentset slaagde **20/20**; artifact SHA-256
`e8aa59ce19eea3ac3b6f64f33ee1bca19a6e63509f4d9303267f8591ef205b95`.
De echte providerregressie slaagde **109/109** zonder provider-, schema-,
timeout-, parse- of validatiefouten; artifact SHA-256
`c215fafba537515f0e5bacd13015f735944b7e6a0d329b12ce79540c8fbeda34`.

Het aparte Tradamind-QA-account bestaat, maar heeft geen gekoppelde exchange.
De getoonde nieuwe Bitvavo-sleutel heeft alleen leesrechten, terwijl
gedetailleerde order- en tradehistorie ook handelsrecht vereist. Er is geen
API-secret in deze taak gebruikt. Daarom is live Bitvavo-import nog
**onbeproefd**; geen exchange-acceptatie mag uit de browserproef worden
afgeleid. Ook automatische providerbewezen afsluiting van alle exchange-
posities is geen huidige productclaim: de kandidaat gebruikt expliciete
gebruikersbevestiging bij exchange-episodes.

[Statushandoff PR #378](https://github.com/gvangalen/antigravity-trading-tool/pull/378)
werd als `2bed0ecb7d48115323d5fdab8e20b28a10309b22` gedeployed na
[main-CI run 39019771493](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39019771493)
en [Auto Deploy run 39019900983](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39019900983),
beide geslaagd. Publieke backend-health en frontend-buildinfo gaven HTTP 200
en exact die SHA. Onafhankelijke QA verifieerde dezelfde identiteit opnieuw.
Op het aparte QA-account was de onboarding eerst onvolledig; QA voltooide die
via de zichtbare browser-UI met een synthetisch BTC-plan en een handmatige
Paper-bot zonder startsaldo, order of live activatie. Daarna slaagden toegang
tot `/report`, de lege Trade Reviews-staat met nul gesloten posities en geen
exchange, behoud na refresh en een FINN-antwoord dat botbeslissingen niet als
tradeafsluiting claimt. De Trade Reviews-kaart bleef op 390 px leesbaar.

QA gaf **NOT_ACCEPTED voor de volledige Trade Reviews-acceptatie** wegens
ontbrekend bewijs: er was geen veilig volledig afgesloten Paper-tradefixture,
zodat gedeeltelijke/volledige sluiting, dossier, screenshot, les en
leshergebruik niet end-to-end zijn beproefd. Bitvavo/Bybit-import,
eigenaarisolatie met een tweede reviewfixture en geforceerde foutpaden bleven
eveneens onbeproefd. QA meldde een P2: de aangrenzende bestaande
Tradingrapport-sectie wordt op 390 px horizontaal afgeknipt; de nieuwe lege
Trade Reviews-kaart zelf niet. Dit is een browser-scopeverdict en heft de
aparte native iPhone-bewijsleemte niet op. Er zijn geen productcode of
releaseinstellingen aangepast tijdens QA.

## Mobiele FINN-herkeuring: wijzigingsverzoek zonder opgeslagen setup

Phase: `INDEPENDENT_QA_NOT_ACCEPTED_NATIVE_EVIDENCE_GAP`. Onafhankelijke
Expo-web-QA op vorige live SHA
`2dde82f498ed4dd1fe6c654391722bd6762feeda` gaf `NOT_ACCEPTED`:
met nul opgeslagen BTC-setups vroeg FINN bij “Wijzig mijn bestaande BTC setup
naar timeframe 4H” toch welke setup bedoeld werd. Een vervolgbeurt gaf eerst
een generieke afrondfout. De lege planstaat, gedeelde feed, chatopslag en
Reflectie-antwoord waren in die run wel correct. Native iPhone-QA was door
simulatorbediening niet volledig afgerond; Expo Web is daarvoor geen vervanging.

De lokale reparatie op `codex/finn-mobile-empty-setup` leest vóór het
wijzigingsvoorstel de eigenaargebonden verzameling van opgeslagen setups voor
de genoemde asset. Bij nul resultaten antwoordt FINN dat er niets te wijzigen
is, zonder voorstel, bevestiging of actie; bij één of meerdere setups blijft
de bestaande voorstel- en doelkeuzeroute intact. Een gerichte regressie dekt
de exacte QA-zin en de gevallen met één en twee setups. De volledige
backend-suite slaagde met **3743 passed, 3 skipped**. Een synthetische lokale
FastAPI/Celery/PostgreSQL/Redis-proef op de exacte zin eindigde met HTTP 200,
`completed`, antwoord “Je hebt geen opgeslagen BTC-setup om te wijzigen. Je
kunt eerst een nieuwe maken.” en `proposal_id: null`. De volledige lokale
actiecontractmatrix slaagde **16/16**, inclusief polling/SSE-pariteit,
bevestiging, idempotentie en eigenaarisolatie; er waren nul brokerorders,
live bots, live trading calls en productieverbindingen. Matrixartifact:
`c02a2c112c448a64087a268eed446eaf04bba54c6ca33a2c30c53464d760f0e7`.
De echte `gpt-6-luna`-developmentset slaagde **20/20** zonder provider-,
schema-, timeout-, parse- of validatiefout; artifact SHA-256
`f319a611d28960944aac3212f8e0c0bfeb70307c3aefd201116ffd9f714ae860`.
De volledige echte providerregressie slaagde **109/109** zonder dezelfde
foutcategorieën; artifact SHA-256
`b8b5921d2e39db930438fcec68e5d72204205e01e0b8e746f7a92a16306abce2`.
Mobiele typecheck, chatregressies en lint met nul errors slaagden;
Expo-web-, iOS- en Android-bundels zijn gebouwd. Lint meldde 110 bestaande
waarschuwingen. Deze exports bewijzen geen native simulatoracceptatie.
PR #375 is als product-SHA `f2657a389f84eca5100df237264c6840c7ac53e0`
gemerged na vijf groene PR-checks. [Main-CI run 39015860698](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39015860698)
en [Auto Deploy run 39015980824](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/39015980824)
slaagden. Backend-health en frontend-buildinfo retourneerden beide HTTP 200
en exact die product-SHA. Onafhankelijke ingelogde live herkeuring van de
lege-setuproute en de mobiele flow staat nog open; Build claimt geen
QA-acceptatie. Een status-only handoff kan een latere deployment-SHA krijgen;
QA gebruikt de werkelijk gepubliceerde backend- en frontendidentiteit.
De reflectie-PR #374 blijft een aparte draft.

Onafhankelijke QA op de werkelijk live status-handoff-SHA
`04bc95a135bfacd5ff66ea709e9f9a88130481fa` gaf voor de **volledige
mobiele productie-QA `NOT_ACCEPTED`**. De gerichte live Expo-webproef met nul
opgeslagen setups slaagde: de exacte wijzigingsvraag kreeg direct het antwoord
dat er geen BTC-setup is, zonder conceptkaart of bevestiging; na een harde
refresh bleven sessie, lege planstaat en gesprek bestaan. De lege FINN-feed
was zichtbaar op vijf tabs. Een productiegericht gebundelde iPhone-simulator
logde wel in en toonde Analyse, maar iOS-wachtwoorddialoog en daarna falende
simulatoraanrakingen verhinderden de native vervolgproef. De gerichte native
herkeuring bleef daarom eveneens `NOT_ACCEPTED` wegens ontbrekend bewijs,
zonder aangetoonde productfout. Geen handelsactie of productmutatie is getest.
De native verificatie blijft open; Expo Web is geen vervanging daarvoor.

## Mobiele herkeuring: lege setup en verlopen sessie

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. Kandidaatbranch:
`codex/finn-mobile-qa-followup`; productmerge
`84f35cda05404f757a0ae676aebf59ef72b628bc`. Onafhankelijke mobiele QA op vorige live SHA
`54fd212cdd6ef2c092cd71c83120ee67046b6c70` gaf `NOT_ACCEPTED`.
De eerder hangende read-only vraag op Reflectie kreeg na verse login binnen
ongeveer 15 seconden een antwoord, bleef na Expo-reload behouden en deelde
dezelfde lege feed op Analyse, Mijn Plan, Portfolio en Automatisering. QA zag
echter een kort zichtbaar ingelogde UI na een verlopen token. Ook toonde Mijn
Plan een zogenaamd bestaand `BTC setup`; FINN kon dat niet vinden voor een
wijzigingsvoorstel.

Een eigenaargebonden read-only API-controle van hetzelfde aparte QA-account
gaf `/setups` als lege lijst, `/setups/top` als lege lijst en
`/setups/active?symbol=BTC` als `{active: null, source_status:
"missing_scores"}`. De mobiele mapper interpreteerde deze status-wrapper
ten onrechte als setup en gaf hem de gegenereerde naam `BTC setup`. De
reparatiekandidaat toont een lege planstaat zonder bevestigbaar nepplan.
Daarnaast meldt de centrale mobiele API-client een ontbrekende of vervallen
authsessie direct aan de authlaag, die de ingelogde UI sluit; op voorgrond
wordt de sessie opnieuw gecontroleerd. De standaard dev-autologin met vaste
voorbeeldgegevens is verwijderd. De lokale gates zijn groen. PR #372,
main-CI `38854326790` en Auto Deploy `38854485264` slaagden.
Backend-health en frontend-buildinfo gaven daarna beide HTTP 200 en exact
product-SHA `84f35cda05404f757a0ae676aebf59ef72b628bc`. Een nieuwe
onafhankelijke ingelogde mobiele QA-run staat nog open. Een
documentatiehandoff kan een latere, inhoudelijk identieke deployment-SHA
krijgen; QA gebruikt de daadwerkelijk gepubliceerde backend- en
frontendidentiteit.

Lokale validatie op deze kandidaat: 11 gerichte mobiele tests, mobiele
typecheck/lint zonder errors en web/iOS/Android Expo-bundels groen; backend
**3740 passed, 3 skipped**; webbuild, typecheck, i18n-, command-, proposal-
en auditpoort groen. De volledige worker-gedreven API/Celery/Responses-matrix
slaagde **37/37** met **16/16** actiecontracten, **9/9** relaties, p95
**6,87 s** en maximaal **11,03 s**; nul Live-bots en ongeoorloofde executies.
Artifact SHA-256:
`7f497151d6a6dbac152a7bbab06f1a9e2e8b83e83c90612687ab4fde924ff76c`.
De echte `gpt-6-luna`/Responses-developmentset slaagde **20/20**, zonder
providerfout (artifact SHA-256
`eb7371cc5b5b59c3d3e33fca915e7ca59dd845784e178ce65c46c568045b9381`).
De volledige selectorregressie slaagde **109/109**, zonder provider-, schema-,
timeout-, parse- of validatiefout (artifact SHA-256
`3ff9f1bb26f989135263642bba308740b7162a0f17c50c78e24e50d603f5630b`).

## Mobiele feed en chat na onafhankelijke herkeuring

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. Kandidaatbranch:
`codex/finn-mobile-feed-qa-repair`; productmerge
`70ce313b6f85362d83d1c9b72017ab70cfd14203`. Onafhankelijke mobiele QA op vorige live SHA
`cf1c8678d755f5712d9d7a65fba9c40480a40278` gaf `NOT_ACCEPTED`:
een read-only chatvraag bleef op “Even controleren…”, de chat hield op
Reflectie en Automatisering het Analyse-label vast, en de feed was op
Automatisering zonder bot onzichtbaar. Een directe, eigenaargebonden API-proef
met een apart QA-account toonde de oorzaak van de vastloper: `/assistant/chat`
leverde een `finn_v2_visible_pending`-contract met run-ID. De mobiele client
behandelde die tekst als eindantwoord en haalde de terminale run nooit op.
De read-only run-GET voor hetzelfde account bereikte `completed` met inhoud.

De huidige reparatiekandidaat laat mobiel het eigenaargebonden run-ID begrensd
ophalen, bewaakt een niet reagerende native read met een zichtbare timeout,
herstelt een afgeronde V2-conversatie na herladen, koppelt de chatcontext aan
de actieve tab, en toont de gedeelde feed ook op Automatisering zonder bot en
Portfolio. De lokale iPhone-simulator op de live API gaf voor de exacte
QA-vraag een terminal coachantwoord; de lege feed en juiste
Automatisering-context waren zichtbaar. Dit is Build-diagnostiek, geen
onafhankelijke productieacceptatie.

De backend-suite slaagde met **3740 tests, 3 bestaande skips**. De webbuild,
typecheck, i18n-, command- en auditpoort slaagden; de audit meldt één
moderate Next.js-bevinding. Mobiele typecheck, lint zonder errors, zeven
gerichte chat-/pollingregressies en web/iOS/Android Expo-bundels slaagden.
De eerste lokale API/Celery/Responses-matrix voltooide **37/37** cases,
**16/16** acties en **9/9** relaties, maar miste de p95-grens met
**10,08 s** (artifact SHA-256
`e59538ba524026d62b9a752e98bb214a4e6cfdb643d8dc189bab99419e07b949`).
Een herhaling zonder gelijktijdige mobiele bundelbouw slaagde **37/37**,
**16/16** acties en **9/9** relaties met p95 **7,43 s**, maximale beurtduur
**12,27 s**, nul Live-bots en nul niet-toegestane executies (artifact SHA-256
`de470a619ddf643aac0333c14932c78b32b539f6e55306d12abf1869fe831c61`).
De eerste rode latency blijft zichtbaar in deze overdracht.
De echte Responses-selectorproef op `gpt-6-luna` slaagde op de
developmentset **20/20** (artifact SHA-256
`d6b4e46746bd88f0f46429a3816aef30910b9e5a2cf8f64220e12f3e582a83c5`)
en de volledige regressieset **109/109** (artifact SHA-256
`76e6e6066b0191c33ee805abaa0e8d31fef7526a0d64f3f2bf974470a36f7be9`).
Beide hadden nul provider-, schema-, timeout-, parse- of validatiefouten.
PR #370 is gemerged na vijf groene controles. Main-CI
`38799413895` en Auto Deploy `38799875093` slaagden. Daarna gaven backend
health en frontend build-info beide HTTP 200 en exact product-SHA
`70ce313b6f85362d83d1c9b72017ab70cfd14203`. Onafhankelijke ingelogde
mobiele QA op deze reparatie moet nog volgen. De documentatiehandoff kan een
latere, inhoudelijk identieke deployment-SHA krijgen; QA gebruikt altijd de
daadwerkelijk gepubliceerde backend- en frontendidentiteit.
De laatste mobiele controle na alle bronwijzigingen slaagde: zeven gerichte
tests, typecheck, lint met nul errors, en Expo web-, iOS- en Android-bundels.

## Oude FINN-meldingen opruimen

Phase: `LIVE_AWAITING_INDEPENDENT_QA`. Op branch
`codex/retire-legacy-finn-events` verwijdert commit `9c82b0ac0` de ongebruikte
legacy `/assistant/events`-API en -service, de parallelle webpoll in het
chatpaneel, de oude dashboardfeed en een ongebruikte mobiele Mission
Control/Today-adapter. De nieuwe eigenaargebonden FINN-coachfeed blijft de
zichtbare meldingsbron. De oude `finn_plan_created`-eventwrite is verwijderd;
governance-events blijven actief. Vervolgcommit `2f68f219b` verwijdert ook de
niet-aangeroepen publieke Mission Control-route, de dode webclientloader en
verouderde route- en UI-tests. De interne Mission Control-berekening blijft
staan omdat een andere interne coachafnemer die nog gebruikt. Een bevestigde
strategie en een gekoppelde strategie na een botactie blijven nu als
eigenaargebonden doel beschikbaar voor een afzonderlijk bevestigbaar voorstel.
Ook een gekoppelde setup na een bevestigde strategieactie wordt via het
direct voorafgaande actieresultaat aangewezen, nooit via een ouder algemeen
gespreksresultaat.
Een nadere runtimeproef vond bovendien een tijdelijke provider-HTTP 520 in
de antwoordronde na een nog niet opgeslagen verduidelijking. De kandidaat
herhaalt zo'n veilige antwoordronde nu eenmaal zonder de actietool opnieuw
uit te voeren; voorstellen met een opgeslagen `proposal_id` vallen niet onder
die retry.
De geïntegreerde kandidaat weigert bovendien expliciete uitvoeringsverzoeken
zonder ondersteund actiecontract; zo wordt een aankoopverzoek niet omgezet in
een ongerelateerd asset- of watchlistvoorstel.

Op de met actuele `main` geïntegreerde code: `pytest -q` **3740 passed, 3 skipped**; webbuild,
typecheck, command-, proposal- en i18n-tests/lint, mobiele typecheck,
lint zonder errors en web/iOS/Android Expo-bundles slaagden. De echte
`gpt-6-luna`/Responses-selectorproeven slaagden **20/20** development en
**109/109** regressie, zonder provider-, schema- of validatiefout. De
selectorcode en het operatiecontractregister zijn sinds die proeven niet
gewijzigd. De uiteindelijke op deze `main` gebaseerde
API/Celery/Responses-paritymatrix slaagde **37/37**,
inclusief **16/16** actiecontracten, **9/9** lineagecontroles, HTTP 200,
polling/SSE-pariteit en nul Live-bots of niet-toegestane executies. De
terminale p95 was **8,29 s** bij een grens van **10 s**;
maximale beurtduur **11,40 s** bij een grens van **15 s**. Artifact SHA-256:
`bffbdbed64cc5d6c7c2d9ea7393337b59b2a0c1a19a699decde4687bf54a5336`.
Twee eerdere metingen op dezelfde code waren rood: eenmaal selecteerde de
provider `delete_indicator_configuration` niet (15/16 acties, p95 11,42 s),
eenmaal slaagden de acties maar niet de latencygrens (16/16, p95 11,36 s).
De laatste volledige meting behaalde alle verplichte acceptatievelden zonder
verlaging van grenswaarden of verwijdering van cases. Deze wisselvalligheid
blijft een QA-aandachtspunt. [PR #366](https://github.com/gvangalen/antigravity-trading-tool/pull/366)
is als product-SHA `3c7262ba9ab8532d96b8cb84b8b9dc819d69f45a` gemerged.
[PR-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38779320145)
en [main-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38779675028)
slaagden met alle vijf jobs; [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38779956941)
slaagde. Backend-health en frontend-buildinfo gaven daarna beide HTTP 200
met exact die product-SHA. Onafhankelijke ingelogde QA moet nog volgen.

## Botflow: begrijpelijke guardrails en Paper-orderhistorie

Phase: `REPAIR_INDEPENDENT_QA_ACCEPTED_LIMITED`. De botflow is via
[PR #358](https://github.com/gvangalen/antigravity-trading-tool/pull/358)
van branch `codex/bot-end-to-end-paper` in `main` gemerged als product-SHA
`23f06c38de3f097cb4a4c3858a669c538987f2f4` op 2026-10-15. Deze botflow toont de
gebruiker waarom een order wordt tegengehouden of een bedrag wordt verlaagd,
en koppelt Paper-uitvoering aan order- en transactiehistorie. Een gebruiker
kan zijn eigen botinstellingen aanpassen; de server bewaakt de effectieve
limieten bij de daadwerkelijke uitvoering. Deze statusupdate wijzigt zelf
opnieuw de deployment-SHA; de botproductcode blijft gelijk.

Op de geïntegreerde kandidaat slaagden **3738 backendtests, 3 bestaande
skips**, frontendbuild, typecheck, i18n-, command-, proposal- en setuptests,
en de high-severity audit (één moderate Next.js-melding). Mobiele typecheck,
lint zonder errors en web/iOS/Android Expo-bundles slaagden. Een lokale
Score2→Celery→Paper-proef maakte precies één kooporder en twee ledgerregels,
met €50 resterende cash en HTTP 200 voor Today, historie en trades; een
stale-signaalproef hield de bot op Hold zonder order of ledgerregel. De
volledige lokale worker-actiecontractmatrix slaagde **16/16**, de adapters
**19/19**; matrixartifact SHA-256
`3cb88585ec9c4fbf2e397ef2553f4ac545929d8f4477caf3a7b6b12908ae8ce9`.
De echte `gpt-6-luna`/Responses-selectorproeven slaagden **20/20** development
(SHA-256 `0c658111fa9051613079729b830d0d87414f3ca1c560bebc3c7fe03cd617c21a`)
en **109/109** regressie (SHA-256
`3fd5bf91093a93ff61cd638977e72a46eddabd75c77ba9ed538d4b6d7407acae`),
zonder provider-, schema- of validatiefouten. De onafhankelijke QA-, Security- en
Architecture-hercontroles van de geïntegreerde kandidaat gaven alle drie
**GO**, zonder blokkerende bevinding. De
[PR-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38771245261)
en [main-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38771592305)
slaagden met alle vijf jobs. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38771842361)
slaagde. Beide publieke endpoints, `https://tradamind.com/api/health` en
`https://tradamind.com/build-info.json`, gaven daarna HTTP 200 met exact
`23f06c38de3f097cb4a4c3858a669c538987f2f4`. De statusdeploy op
`d1feaf0db685a62699d025429384d0b29ce48703` had groene
[main-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38772479431)
en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38772761894);
beide publieke endpoints gaven opnieuw HTTP 200 met die SHA.

Onafhankelijke ingelogde read-only QA op die status-SHA gaf **NOT_ACCEPTED**
voor de volledige botflowhistorie en uitleg. De officiële
[auth-preflight](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38772995547)
slaagde; artifact SHA-256
`0d37679d2870f50f808f8bf05f5c84078256730f867e732f87f9774aa29abf99`.
Een bestaande Paper-bot toonde een echte blokkade met reden en €2,50→€0,00;
een andere toonde een uitgevoerde Paper-koop van €1,25. Paper- en Live-
portfolioweergaven bleven gescheiden. De 13 zichtbare oudere uitgevoerde
trades hadden echter geen vastgelegde `execution_environment`; hun omgeving
is niet achteraf bewijsbaar uit de huidige botconfig. Een gerichte read-only
hercontrole toonde dat de nieuwste van die 13 trades
op 2026-10-15 om 00:04:09 UTC is uitgevoerd, ruim vóór de
`execution_environment`-writer die op 2026-10-15 om 06:39 UTC live ging.
Deze dataset toont daarmee geen actuele writerfout. Oudere botbeslissingen
toonden letterlijk `{}` als reden en één DCA-redenzin stond ongezien in het
Engels. De herstelkandidaat op branch `codex/bot-history-explanations`
vervangt die twee onbegrijpelijke redenen en legt bij oude orders expliciet
uit waarom de omgeving onbekend blijft, zonder Paper of Live te verzinnen.
Een nieuwe automatische fill en een bestaand verlaagd bedrag konden binnen
de read-only QA-scope niet onafhankelijk worden opgewekt. Na deze reparatie
is opnieuw een exacte live SHA en onafhankelijk QA-verdict nodig.

Op de herstelkandidaat slaagden **3739 backendtests, 3 bestaande skips**,
frontendbuild, typecheck, i18n-, command-, proposal- en setuptests, en de
high-severity audit met één moderate Next.js-melding. De lokale
worker-actiecontractmatrix slaagde **16/16** en de adapters **19/19**,
zonder brokerorders, Live-aanroepen of productieverbindingen; artifact
SHA-256 `df68b054058aa48687a1a22d1596dad4a93301e238d79cc2cc10d798d82d8bd0`.
De echte `gpt-6-luna`/Responses-developmentset slaagde **20/20**, zonder
providerfouten; SHA-256
`8dcfe5c738ac4d539940837535df432969270c7eabdaa4197ae39760d9763a0d`.
De echte regressieset slaagde **109/109**, zonder provider-, schema- of
validatiefouten; SHA-256
`f5babab019d756d0743389886cfc1c6b030dcb77b14557eb752be8f88e536070`.
Onafhankelijke QA- en Security-codehercontroles van de laatste herstelcommit
gaven beide **GO**. Zij bevestigen dat een ontbrekende historische
`execution_environment` onbekend blijft en dat een betekenisvolle
objectreden niet wegvalt. Dit is geen nieuw productie-QA-verdict.

De herstelcode is via [PR #365](https://github.com/gvangalen/antigravity-trading-tool/pull/365)
gemerged als product-SHA `13e6e37e37ff16c80644c6f501710bb514486b3c`.
De [PR-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38775975490),
[main-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38776381141)
en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38776699062)
slaagden. Beide publieke build-endpoints gaven HTTP 200 met exact die SHA.
Deze statusupdate maakt opnieuw een deployment-SHA zonder productcodewijziging;
onafhankelijke ingelogde QA gebruikt de dan actuele publieke SHA.

De statusdeploy op `a20417bf244da6e7978a8a0761a1b977fbfe89cf` had
groene [main-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38777271192)
en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38777502272).
Beide publieke endpoints gaven HTTP 200 met exact die SHA. Onafhankelijke
ingelogde read-only QA op deze SHA gaf **ACCEPTED voor de beperkte historie-
en tekst-reparatie**. De officiële
[auth-preflight](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38777736108)
slaagde; artifact SHA-256
`11f67f7e27b13b761db79db32e376ba8047a73d558beedae8d92d7c72c658da2`.
In de browser toonden alle 13 historische trades `Niet vastgelegd` met een
uitleg over ontbrekend Paper/Live-bewijs. Bot 82 toonde een vertaalde
DCA-redenzin; in de uitgebreide geschiedenis van bots 82 en 77 kwam geen
letterlijke `{}` meer voor. De bestaande Paper-blokkade met €2,50→€0,00
en de gescheiden Paper-/Live-portfolioweergaven bleven intact. QA deed geen
order of write. De werkelijke Paper/Live-herkomst van oude orders, een
nieuw verlaagd bedrag en een nieuwe Paper-fill bleven buiten dit beperkte
acceptatiebewijs. Deze verdictdocumentatie creëert opnieuw een latere
deployment-SHA zonder productcodewijziging.

## Live-brokercash per bot toewijzen

Phase: `INDEPENDENT_QA_PARTIAL_EVIDENCE_GAP` — [PR #361](https://github.com/gvangalen/antigravity-trading-tool/pull/361)
is gemerged en productcommit `e53d76900c14c7dfc0835ddf698283987bcc90b3`
is gedeployed. De wijziging telt één eigenaargebonden brokerrekening één keer
in het Live-totaal, laat vrije EUR-cash expliciet aan eigen Live-bots toewijzen
voor de weergave en toont de rest als niet-toegewezen cash. Een toewijzing
reserveert geen exchange-geld en verandert geen orders of botlimieten.
Onvolledige brokerbedragen en ontbrekende of oude EUR-koersen blijven onbekend.
Web, mobiel en FINN lezen dezelfde projectie; de directe Responses-tool kan
`environment=live|paper` doorgeven.

Op de definitieve lokale code slaagden **3724 backendtests, 3 bestaande skips**,
webbuild, typecheck, i18n-, command-, proposal- en setuptests, mobiele
typecheck, lint zonder errors en web/iOS/Android Expo-bundles. De
high-severity audit slaagde met één bestaande moderate Next.js-melding.
Onafhankelijke Security- en Architecture-codehercontroles vonden geen concrete
blokkade. Een gerichte echte Luna/Responses-run op een synthetische lokale
eigenaar voltooide zonder voorstel en koos `get_portfolio_and_exposure` met
`environment=live`.

De lokale API/Celery-paritymatrix slaagde **37/37**, inclusief **16/16**
actiecontracten, **9/9** lineagecontroles, polling/SSE-pariteit en de
veiligheidscontroles. Voor modelgeleide leesvragen toetst deze poort nu de
daadwerkelijk gebruikte eigenaargebonden Responses-tool, het voltooide
antwoord en afwezigheid van een schrijfvoorstel; zij vereist daarvoor geen
oude `operation_id` meer. Artifact SHA-256:
`8716b5320afa2cdafc167d07153c399521f5821c68fa078936827018ddf22975`.
De echte `gpt-6-luna`/Responses-selectorproeven slaagden **20/20** development
(SHA-256 `761eb193b77d76c2581b8742830803fb33666436c7b895e02d10b004afd80e23`)
en **109/109** regressie (SHA-256
`0c1f5a3a63b20e2c55a22051ae2c5e14fd4dda96113f199be1cda542c5d31357`),
zonder provider-, schema- of validatiefouten. De
[PR-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38724276652),
[main-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38724554980)
en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38724796225)
slaagden. Op 2026-10-15 gaven `https://tradamind.com/api/health` en
`https://tradamind.com/build-info.json` beide HTTP 200 met exact
`e53d76900c14c7dfc0835ddf698283987bcc90b3`. De daaropvolgende
statusdeploy draaide op `3c52b7cd3399dc312c4640c91a9ff90880ead27a`:
[main-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38725237096)
en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38725476295)
slaagden en beide publieke build-endpoints gaven HTTP 200 met die SHA.

Onafhankelijke ingelogde browser-QA op `3c52b7cd3399dc312c4640c91a9ff90880ead27a`
bevestigde scheiding tussen Live en Paper, blijvende Paper-bedragen na refresh,
onbekende waarderingen waar bewijs ontbreekt, en een read-only FINN-antwoord
dat Live niet als nul, Paper-cash of botbudget voorstelde. Er waren geen
consolefouten, gegevenswijzigingen of orders. **De Live-toewijzing is niet
afgetekend:** dit QA-account heeft geen veilige verbonden Live-broker met
twee bots. Eenmalig tellen van broker-cash, twee toewijzingen, restcash,
overallocatie, eigenaarsscheiding en persistentie zijn daardoor niet live
bewezen. Native mobiel en een geforceerde requestfout waren in deze QA-run
niet bereikbaar. De bestaande beschermde portefeuillefixture dekt Paper/FX,
niet deze Live-toewijzing. Een volgende positieve acceptatieproef vereist een
veilig verbonden Live-testbroker zonder orderuitvoering. Deze documentupdate
wijzigt opnieuw de deployment-SHA; de productcode blijft gelijk.

## Portfolio 2.0: verifieerbare waardering per bot

Phase: `INDEPENDENT_QA_NOT_ACCEPTED_EVIDENCE_GAPS`. [PR #354](https://github.com/gvangalen/antigravity-trading-tool/pull/354)
is gemerged als product-SHA `971c3ca398ccda7810b77d1502e626bc8b4c905a`.
De huidige Build-kandidaat voegt uitsluitend een apart beschermd QA-profiel
`portfolio_paper_fx` toe voor de nog onbewezen niet-EUR waardering, server-
Paper-fill en replay. Het profiel leest vóór enige fixture-write bestaande
gedateerde BTC-prijs- en FX-bronnen, maakt alleen een inactieve synthetische
owner en heeft twee expliciete uitvoeringsflags nodig. Het is **lokaal
voorbereid, niet op productie uitgevoerd of door QA geaccepteerd**. De
volledige lokale backend suite gaf **3699 passed, 3 skipped**; `actionlint`
op de beschermde workflow en `git diff --check` slaagden. Security vond geen
concrete blocker; Architecture wees op bron- en bewijsgrenzen, waarna de
prijsverificatie en doorgifte van de autorisatieflag zijn aangescherpt. Het
profiel bewijst de gedeelde adapterprojectie, niet zelfstandig de ingelogde
web-, FINN-chat- of native mobiele runtime.
Een gerichte mobiele foutstatefix volgde via
[PR #357](https://github.com/gvangalen/antigravity-trading-tool/pull/357) als
product-SHA `33ee99b714ac45635edd777dbda89f300383d3df`: bij een mislukte
Portfolio- of historieaanvraag verdwijnen oude bedragen en grafiekpunten,
en NL/EN/DE tonen een concrete fout. Mobiele typecheck, lint en iOS/Android-
bundles, [PR-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38702199695),
[main-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38702480677)
en [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38702701841)
slaagden. Beide publieke build-endpoints gaven daarna HTTP 200 met exact die
SHA. Dit is een nieuwe, nog niet onafhankelijk geaccepteerde build; het
onderstaande QA-verdict hoort bij de eerdere status-SHA.
De [PR-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38698223064)
en [main-CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38698745232)
zijn groen. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38698966645)
slaagde. Op 2026-10-15 gaven `https://tradamind.com/api/health` en
`https://tradamind.com/build-info.json` beide HTTP 200 met exact die
product-SHA. Deze statusupdate creëert na merge opnieuw een latere SHA;
QA bindt uitsluitend aan de dan actuele, identieke publieke SHA.
De nieuwe portfoliolezing scheidt Live en
Paper, toont botbudgetten afzonderlijk van geld, en telt een bot alleen in
waarde, cash en resultaat mee wanneer de onderliggende posities en valuta
verifieerbaar zijn. Oudere Paper-ledgers zonder controleerbare kostprijs
worden niet als actuele waarde voorgesteld. Een gedateerde EUR-valutakoers
is vereist voor niet-EUR posities. De gedeelde projectie wordt door de
webpagina, mobiel en FINN gelezen; paginaweergave veroorzaakt geen order.

De Build-branch is op de actuele bot-release gebaseerd. Lokaal slaagden
**3698 backendtests, 3 skipped** en frontendbuild, typecheck, i18n-,
command- en proposaltests en de high-severity audit. Mobiele typecheck,
lint en web-, iOS- en Android-bundles slaagden. In een lokale Paper-API-proef
werd een door de client aangeleverde prijs van €1 genegeerd: de server
gebruikte €100, boekte één EUR-ledgerfill, en herkende een herhaalde
bevestiging als duplicaat. Een oude Live-botbeslissingsroute die een
exchange-order zonder bewezen afwikkeling als fill kon boeken is nu
fail-closed; de bestaande nieuwe Live-reconciliatie blijft intact.

De volledige lokale worker-actiecontractmatrix gaf **16/16** en de
adaptertests **19/19**. De echte Luna/Responses-selectorproef gaf **20/20**
ontwikkelcases en **109/109** regressiecases met nul providerfouten. Een
aparte tweebeurtige lokale FINN-runtimeproef rond botbudget versus cash
slaagde. Gesanitiseerde lokale artifacts: actiecontractmatrix SHA-256
`ee1ad4c53d42192ae2f106a147da19933d34339979c56e6aa540c772d724d359`,
Luna-regressie SHA-256
`06148f1e697debee582aaac3e5b92f6c26c0911156b1365d441c97e21dc7ef9f`,
FINN-portfolioproef SHA-256
`6fe509fc9207d9758ec6c0150dfa93ab2de87c1ebb9805d9fc76ad945abd9f03`.

Onafhankelijke ingelogde QA op status-SHA
`0778a8d4ca9cc931b9a338edf05f7b665a420420` gaf **NOT ACCEPTED voor de
volledige matrix wegens bewijsgrenzen, zonder aangetoonde nieuwe
productregressie**. Paper en Live bleven bij zes snelle wissels gescheiden.
Een nieuwe gerichte read-only webherkeuring op SHA
`b63586ec305e45bc337e0c9bf0144bca96670e30` slaagde voor de beschikbare
accountdata: Paper/Live-scheiding, onbekende historische ETH-waardering,
twee virtuele cashrijen van €20, FINN-pariteit voor budget versus saldo,
NL/EN/DE en 390 px tabelbereik zonder consolefout. QA kon daarmee geen
actuele niet-EUR FX-positie, een echte API-fout of Paper-replay bewijzen;
native mobiel bleef door een vergrendelde Mac onbeproefd. Dit verandert het
volledige verdict nog niet.
Drie historische ETH-bots kregen geen onbewezen waardering; twee cash-only
bots toonden ieder €20; een ongefinancierde bot toonde zijn €20 limiet niet
als saldo. FINN hield dezelfde read-only geldbetekenis aan. NL/EN/DE en een
op 390 px horizontaal bedienbare botlijst werkten zonder consolefouten.
QA's Paper- en Live-screenshots hebben respectievelijk SHA-256
`bc2f3a2725018c3521f0f19f98b4a383b04233de7ee6679176e095706e8e042d`
en `0a00607ccdc6394847485c75e2a5cdd787f28aa97e29998aeaba9daca8a6bc08`.

De browserfixture bood geen geverifieerde niet-EUR positie met verse koers
en FX, geen geforceerde API-fout en geen geautoriseerde Paper-herhaalproef.
Native mobiel was niet bereikbaar in deze run. QA kon productiecheckout en
release-marker niet zelf rechtstreeks lezen; het geslaagde
[Auto Deploy-log](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38699662596)
registreert wel de uitgecheckte SHA, de productierelease-marker en
`LAST_GOOD_COMMIT` alle drie als
`0778a8d4ca9cc931b9a338edf05f7b665a420420`. Dat log is
Build/Operations-bewijs, geen vervanging van een onafhankelijke QA-preflight.
Een nieuwe beschermde Paper-fixture en herkeuring zijn nog niet uitgevoerd.

## Botflow: automatische Paper-order en geschiedenis

Phase: `AUTO_PAPER_HISTORY_ACCEPTED_BY_INDEPENDENT_QA`. De complete botflow is via
[PR #345](https://github.com/gvangalen/antigravity-trading-tool/pull/345)
overgezet naar de actuele `main` en gemerged als product-SHA
`62dc964b47b63b7ba2058571404303ff472f122c`. De afzonderlijke beschermde
Paper-orderproef is via
[PR #351](https://github.com/gvangalen/antigravity-trading-tool/pull/351)
gemerged als QA-runner-SHA `77b5e84bee05e26ad67ef8ff483c1979d3cbac4e`.
Deze documentatie-update verandert alleen de release-aantekening en creëert
een latere SHA. QA bindt haar officiële run uitsluitend aan de dan actuele,
identieke SHA van backend-health, frontend-buildinfo, productiecheckout en
release-marker.

Build-evidence voor de botflow: volledige backend lokaal **3672 passed,
3 skipped**; frontend productiebuild, typecheck, i18n- en commandtests
geslaagd. De geïsoleerde lokale PostgreSQL-proef vulde één automatische
Paper-order van €50, bracht virtuele kas van €100 naar €50 en gaf in de
accountgeschiedenis `paper / auto / filled / €50` terug. De proef gebruikte
een voorbereide beslissing en stubde alleen de planrevisiecontrole; hij
bewijst daardoor niet de volledige automatische beoordeling. Onafhankelijke
Build-branch QA, Security en Architecture accepteerden de wijziging.
[Main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38693391119)
was groen; [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38693605207)
slaagde op product-SHA `62dc964b47b63b7ba2058571404303ff472f122c`.

Build-evidence voor de beschermde QA-proef: volledige backend lokaal
**3673 passed, 3 skipped**, runner-tests **66 passed**, shellsyntax en
diffcontrole geslaagd. Een geïsoleerde lokale PostgreSQL-uitvoering van de
nieuwe probe gaf `paper / auto / filled / €50`, €50 resterend virtueel saldo,
één execute-ledgerboeking en nul exchange keys. Onafhankelijke Security en
Architecture accepteerden commit `4b03308bd9c7735ae5cfd865d30bd2e4f1750de2`
voor de expliciete executor→ledger→accountgeschiedenis-scope.
[PR #351 CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38694851079)
en [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38695117190)
waren groen. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38695291018)
slaagde; op 2026-10-15 gaven `/api/health` en `/build-info.json` ieder
HTTP 200 met exact `77b5e84bee05e26ad67ef8ff483c1979d3cbac4e`.

Onafhankelijke QA had als actieve scope: één officiële beschermde
`auto_paper_trade_history` run op de actuele live SHA, met
`allow_fixture_actions=true` en `allow_safe_fixture_execution=true`. Alleen
een inactieve synthetische eigenaar zonder exchange keys mag één virtuele
Paper-koop van €50 doen. Acceptatie vereist `paper / auto / filled / €50` in
de accountgeschiedenis, één uitvoeringsboeking, virtuele kas €100→€50,
geen Live-uitvoering en geslaagde cleanup of veilige quarantaine. De probe
seedt de beslissing en order; scheduling, marktbeoordeling, planvorming en
browserweergave blijven buiten dit specifieke productie-QA-verdict.

Onafhankelijke QA voerde precies één beschermde
[productierun 38696292790](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38696292790)
uit op de toen live SHA `25c53897bbef52f584719224785ab2f06f76c70a`
en gaf **ACCEPTED voor deze afgebakende scope**. Het gesanitiseerde rapport
`finn-production-qa-38696292790-1.json` heeft SHA-256
`d8cab5206646d08576546885c9c1a15ff6ec1c457bc536f25f09937235abfb6e`;
QA verifieerde de bijbehorende sidecar. Releasecheckout, release-marker,
publieke backend-health en frontend-buildinfo matchten de exacte SHA;
fixture-authenticatie gaf HTTP 200. De probe rapporteerde `paper / auto /
filled / €50`, virtuele kas €50 na €100 startkapitaal, één
uitvoeringsboeking, nul exchange keys, nul Live-trading- of
Live-bot-activatiecalls en geen runnerfouten. De geslaagde protected run
impliceert dat de verplichte cleanup terugkeerde; het rapport heeft geen
afzonderlijk cleanup-statusveld. Dit is geen bewijs voor planning, scheduler,
marktbeoordeling of de zichtbare browserweergave van `/bot > Alle trades`.
Deze statusupdate wijzigt geen runtimecode en creëert opnieuw een latere SHA.

## Portfolio-overzicht met gedeelde geldbetekenis

Phase: `PORTFOLIO_ENVIRONMENT_TRANSITION_ACCEPTED_BY_INDEPENDENT_QA`.
[PR #347](https://github.com/gvangalen/antigravity-trading-tool/pull/347)
leverde product-SHA `dcb6b80ba2607df3fc2c78dcb845574fb45891df`.
Onafhankelijke ingelogde QA op de documentatie-SHA
`a3fd4cac24eeed1678f13b1c8b6a69b1fdc46cc9` gaf **NOT ACCEPTED**:
bij Paper → Live bleven de Paper-botrijen kort zichtbaar met het label Live,
inclusief Paper-cash, totdat de lege Live-state laadde. Daarnaast faalde een
vóór de deploy geopende tab bij de eerste navigatie met een webpack-
`undefined.call`-fout; een harde refresh herstelde hem. De definitieve
Paper-/Live-gegevens, botbudgetgrens, FINN-pariteit voor bekende en onbekende
Paper-cash en NL/EN/DE-teksten slaagden in deze fixture. Native mobiel,
niet-EUR posities, API-foutstatus en volledig gefinancierde totalen bleven
onbewezen.

De gerichte herstelkandidaat bindt geladen overzichtsgegevens aan hun
Paper-/Live-omgeving en negeert verouderde responses na een wissel. De
oude-tabherstelfunctie herkent nu ook precies de webpack-`undefined.call`-
fout, zonder gewone React-fouten te herladen. Lokaal slaagden frontend
productiebuild, typecheck, i18n-lint en -tests, command- en proposaltests,
de 14 release-hardening-tests en high-severity audit. Onafhankelijke live
herkeuring van deze kandidaat volgde op de live product-SHA.
[PR #349](https://github.com/gvangalen/antigravity-trading-tool/pull/349)
leverde product-SHA `72978701a0d61fd5dfe4e472e2d6f15042879e5c`.
Candidate [CI run 38688451136](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38688451136)
en main [CI run 38688645648](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38688645648)
slaagden. [Auto Deploy run 38688821014](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38688821014)
slaagde; publieke backend-health en frontend-buildinfo gaven ieder HTTP 200
met die product-SHA. Onafhankelijke ingelogde QA gaf **PASS voor de gerichte
Paper/Live-reparatie**: bij vier snelle wissels verscheen geen Paper-bot onder
een Live-label; de zes Paper-bots en FINN bleven bij dezelfde bedragen en
ontbrekende totale waardering; Live bleef leeg. De console bleef schoon.
Kunstmatig trage requests en herstel van een tab met een vóór-de-fix geladen
bundle zijn nog niet live bewezen. Dit is geen acceptatie van een volledig
gewaardeerd Live-portfolio of historische EUR-grafiek.

De nieuwe eigenaargebonden projectie scheidt Paper en Live en geeft web,
mobiel en FINN dezelfde botrijen. Botbudget blijft een limiet en wordt niet
als cash of portefeuillewaarde getoond. Paper-cash komt alleen uit een
gefinancierd virtueel ledger. Posities krijgen alleen een EUR-waarde met een
controleerbare, recente EUR-koers. Een gedeeld Live-brokersaldo wordt niet
per bot opgeteld; Live-totaal en beschikbare cash blijven onbekend zolang
brokerreconciliatie ontbreekt. Historische grafieken met onbekende
koersvaluta worden niet als euroverloop gepresenteerd. Zie
`docs/operations/portfolio-overview-v2.md` voor de veldbetekenis.

Lokale Build-validatie: backend **3615 passed, 3 bestaande skips**;
frontend productiebuild, typecheck, i18n-lint en -tests, command- en
proposaltests en high-severity audit geslaagd. Mobile typecheck, lint en
web/iOS/Android-bundels geslaagd; bestaande lintwaarschuwingen blokkeren niet.
Een lokale eigenaarsscope-API-proef bevestigde dat een bot van een andere
gebruiker niet in het Paper-overzicht verschijnt en dat een USDT-gequote
positie geen EUR-totaal krijgt. De echte Luna/Responses-selectorproeven
haalden **20/20 development** (SHA-256
`a49f2b21c95d25b689b96232d401f7d8019ab9129a3439f47c4e5650ee74a511`)
en **109/109 regression** (SHA-256
`1ba7805fcd88d35bb4ffe06c0fcc1f7954392dc82007c0abc36deae1260bff56`).
De finale lokale worker-actiecontractmatrix slaagde **16/16**, adaptertests
**19/19**, zonder brokerorders, Live-bots, Live-trading calls of
productieverbindingen (SHA-256
`18a728b5d37e8ac3082e2e09111c9a87221e8737a2a309cd64b1b71e5dd763f8`).
Een volledige lokale FastAPI/Celery/PostgreSQL/Responses-gespreksproef
bevestigde dat FINN het botbudget niet als beschikbaar saldo uitlegt,
geen marktprijs of actie verzint en het ophaalmoment onderscheidt van
een koersbronmoment (SHA-256
`3492471dce3822a0bd50188beae2d9c9dfbbebd89d493f9c7faecfd3cc2e5299`).
Candidate [CI run 38686576938](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38686576938)
en main [CI run 38686804786](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38686804786)
slaagden; de eerste poging zonder bijgewerkte statische export faalde
terecht bij de exportinvoercontrole en is vervangen door de geslaagde
candidate. [Auto Deploy run 38686981931](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38686981931)
slaagde. Op 2026-10-15 gaven de publieke backend-health en frontend-buildinfo
ieder HTTP 200 met exact de product-SHA. Deze documentatie-update verandert
alleen de release-aantekening; de live identiteit wordt na die update opnieuw
via de publieke oppervlakken gecontroleerd.

## FINN Guided Name Prompt Intent

Phase: `GUIDED_NAME_PROMPT_ACCEPTED_BY_INDEPENDENT_QA`.
Independent authenticated browser QA on SHA
`78163f86188b6fde7472ded37cbfd407192f17d1` confirmed the exact
“wat stel je voor” flow, acceptance after refresh, a different user-chosen
name, and an explicitly quoted literal name. QA returned **NOT ACCEPTED** for
the wider name flow: “Maak een ETH trade-setup op 4H. Vraag mij om de naam en
sla niets op.” produced a confirmable draft named `en` rather than asking for
the name. No proposal was confirmed; the plan count remained unchanged.

[PR #343](https://github.com/gvangalen/antigravity-trading-tool/pull/343)
recognizes the instruction to ask for a name and prevents a model-proposed
name from overriding it. The exact local FastAPI/Celery/PostgreSQL/Responses
prompt now asks for the name with no proposal; only the user's next name
creates a draft. Product SHA:
`6eb5cc182a7e227f80d1990dd607ff635e5ec267`.

Build evidence on 2026-10-14: backend **3607 passed, 3 existing skips**;
frontend production build, typecheck, i18n lint/tests, command and proposal
tests, and high-severity audit passed. Mobile typecheck, lint, and web/iOS/Android
bundle smokes passed; existing lint warnings are non-blocking. The final
local worker action matrix passed **16/16** and adapters **19/19**, with zero
broker orders, live bots, live-trading calls, or production connections
(SHA-256 `ff2b3521f642b157447be305944b5187dbbb0c8bc2b620f4d0f1fb29098e9340`).
Real Luna/Responses selector development passed **20/20** (SHA-256
`5f76a949a42ae327633a6cb09d3c17997b3c3518deca48997024a57ecb0f6130`)
and regression **109/109** (SHA-256
`bef2cf0b00660c89e2521954a08a2c8f01c9327c8855fd51b47d2a426ed1b83e`).
The combined five-turn local guided-name regression passed (SHA-256
`cf0af878d5f91536c0027e3f2e3446c3f76f89f2c85b5946f81e6157ebeb18e9`).
Candidate [CI run 38624403495](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38624403495)
and main [CI run 38626307261](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38626307261)
passed all five jobs. [Auto Deploy run 38626579154](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38626579154)
succeeded. Public backend health and frontend build-info both returned HTTP
200 and the exact product SHA on 2026-10-14. A later documentation-only SHA
`f4dfaa93cb73675e38beee2682f3381e8e1e44ea` passed main CI and Auto
Deploy and showed that same SHA on both public build surfaces. Independent
authenticated QA returned **PASS** for the targeted guided-name flow on that
SHA at mobile browser width 390×844. The previously failing request to ask
for a name produced a name question without a card; entering `ETH Rustig 4H`
then produced the correct unsaved card. “wat stel je voor” gave only a name
suggestion, and acceptance after refresh produced the correctly named draft.
QA cancelled both drafts without confirmation; the plan count stayed eight,
and the browser console had no errors or warnings. Native mobile runtime was
not available, so this verdict covers the mobile browser, not the native app.

## FINN Guided Name Suggestion

Phase: `GUIDED_NAME_SUGGESTION_READY_FOR_INDEPENDENT_QA`.
The mobile-reported name step treated the user's question “wat stel je voor”
as a literal setup name. The pending-name slot accepted short text without a
question mark, and an answer-only name suggestion discarded the collecting
draft before the user's next choice. [PR #341](https://github.com/gvangalen/antigravity-trading-tool/pull/341)
keeps name questions out of the name field, proposes a descriptive name from
the typed draft without saving it, and keeps that same draft available until
the user accepts the suggestion or types a different name. Product SHA:
`563e10612da400442d46d40a91cd28e21ea91a48`.

Build evidence on 2026-10-14: backend **3606 passed, 3 existing skips**;
frontend production build, typecheck, i18n lint/tests, command and proposal
tests, and high-severity audit passed. Mobile typecheck, lint, and web/iOS/Android
bundle smokes passed; existing lint warnings are non-blocking. The complete
local worker action matrix passed **16/16** and adapters **19/19**, with zero
broker orders, live bots, live-trading calls, or production connections
(SHA-256 `3f6162b82ae7a95b1ffa8e42ef259ed655ca73099cf0548eb2e750c9dc5b606c`).
Real Luna/Responses selector development passed **20/20** (SHA-256
`52641f98b825e9486ef35681467fa03b84c5f54c6c01ff582726f7284a2e4183`)
and regression **109/109** (SHA-256
`21782fb3567a064c5e8ec4fcc9f102c39ce731789ba911edf7fe13bb430745d8`).
The local FastAPI/Celery/PostgreSQL/Responses ETH conversation passed all
three turns: missing name, suggested name without a proposal, and a confirmable
draft only after “ja, gebruik die naam” (SHA-256
`5e37e8175a4ef16b637ca3f27406e8bed21b7f69d736a24d9391f0f880d8d6f5`).
Candidate [CI run 38621135698](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38621135698)
and main [CI run 38621801922](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38621801922)
passed all five jobs. [Auto Deploy run 38622046078](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38622046078)
succeeded. Public backend health and frontend build-info both returned HTTP
200 and the exact product SHA on 2026-10-14. Independent authenticated QA
for the guided mobile/web name step remains pending.

## FINN Chat Side Panel

Phase: `CHAT_SIDE_PANEL_EXPLICIT_DRAFT_ACCEPTED_BY_INDEPENDENT_QA`.
Independent authenticated browser QA returned **NOT ACCEPTED** on the
preceding live SHA `cd640c00c17bab0851d72d5c4dd577c24bf0d5ac`. The
seven-setup score count and German follow-up passed, as did Paper-bot totals,
DCA cadence, proposal restoration, navigation, Stop, mobile display, and the
feed handoff. Two direct requests to show an ETH trade-setup concept without
saving returned a tool-relevance error instead of a proposal card. The guided
creation route did produce the card. No proposal was confirmed or executed.

[PR #338](https://github.com/gvangalen/antigravity-trading-tool/pull/338)
removes the redundant second model relevance veto when the user's explicit
create imperative and the model-selected proposal operation match. It keeps
the typed owner-scoped proposal contract and separate confirmation. An
explicitly excluded proposal or hypothetical exercise cannot create a
confirmable card. Product SHA:
`903bdb5661ded3a0edef387f256bb9e2ddc6d8a8`.

Build evidence on 2026-10-14: backend **3605 passed, 3 existing skips**;
frontend production build, typecheck, i18n lint/tests, command, proposal and
setup tests, and high-severity audit passed. The final local worker action
matrix passed **16/16** and adapters **19/19** with zero broker orders, live
bots, live-trading calls or production connections (artifact SHA-256
`b7eba1604edb529980de5b1eb844e667d26fa06c468e2cb0786f8168f0e36077`).
Real Luna/Responses selector development passed **20/20** (SHA-256
`e9b3514caf14e4302ee9dc0cfad50de869490a783e8b77729eec2e18276252c3`)
and regression **109/109** (SHA-256
`32223a1046496a55122ceaae15b8d19887ee5b60337555fc8f4801e125fd0326`).
The exact two failed free-draft prompts through local
FastAPI/Celery/PostgreSQL/Responses both yielded a proposal card; read-only
and hypothetical controls yielded none (**4/4**). No protected QA material or
production account was used. Candidate CI and main
[CI run 38586237904](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38586237904)
passed all five jobs. [Auto Deploy run 38586570138](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38586570138)
succeeded. Public backend health and frontend build-info both returned HTTP
200 and the exact product SHA. The independent authenticated browser QA bound
its test to backend and frontend SHA
`43d3f4f7e37084b2a547441d132e30e0d18dd6ce` and returned **ACCEPTED**
for the targeted FINN Chat Side Panel flow. Both exact free ETH concept
requests produced the correct unsaved ETH/4H/Trade card. Navigation and
refresh preserved it; cancellation disabled confirmation and cleared the
pending feed update. Guided creation, read-only and hypothetical no-card
controls, German follow-up, Stop, mobile viewport, and browser console checks
passed. QA did not confirm or save a proposal, start a bot, or place an order;
this verdict does not cover complete CRUD or trading execution. The proposal
wording remains somewhat procedural. A later documentation-only SHA does not
change the tested product code.

Prior phase: `CHAT_SIDE_PANEL_SCORE_COUNT_AND_LOCALE_READY_FOR_INDEPENDENT_QA`.
Independent authenticated browser QA returned **NOT ACCEPTED** on the
preceding live SHA `2a1d4fe50970f7c06e1b5381d6535434af2d92f5`:
the proposal card now survived navigation and refresh, cancellation removed
its confirmation action, and the Paper-bot total was consistent at five with
two setups without bots. The seven-ETH-setup explanation nevertheless counted
four macro minimums of zero even though the saved records had three zero,
three 30, and one unbounded setup. A follow-up after switching the UI to
German kept the correct setup context but replied in Dutch. This was an
independent browser retest, not a protected official runner matrix; its
fixture had one strategy per setup.

[PR #336](https://github.com/gvangalen/antigravity-trading-tool/pull/336)
supplies typed, owner-scoped score-condition groups and explicit asset scope
for collection reads, distinguishing an absent bound from literal zero. FINN
still composes the answer; the existing bounded language-only repair now
detects a short German/Dutch mixed sentence, and the web composer submits the
language displayed at send time. Product SHA:
`917c7fa43fdccd4dc9a44ab9c5c51405dcaaae78`.

Build evidence on 2026-10-14: backend **3597 passed, 3 existing skips**;
frontend production build, typecheck, i18n lint/tests, command, proposal and
setup tests, and high-severity audit passed. The local worker action matrix
passed **16/16** and adapters **19/19** with zero broker orders, live bots,
live-trading calls or production connections (artifact SHA-256
`cb8b734faf1c08dbbf19950d3cfc8f52809f549743c8efba7b4ba31476d2f51b`).
Real Luna/Responses selector development passed **20/20** (SHA-256
`081c8d404204bc5e993396e2fd8bbed1ca694aa0d9fd0e72d8972c643f709ef0`)
and regression **109/109** (SHA-256
`e8767cabaaf5d8c60b534ad8e7ac0d6f5a0d029fde06725280aa1c21217bb86d`).
The local FastAPI/Celery/PostgreSQL/Responses seven-setup comparison and
German follow-up passed **2/2** (SHA-256
`6043410d4c7679223deb7bb2693f17511c5fe550cfa0586cda6a31005d026c11`);
the alternate asset-scoped wording passed **1/1** (SHA-256
`ab7589fde2817df58725529eba76a096059902423160227bad6489b9af139d10`).
No protected QA material or production account was used. Candidate
[CI run 38580468313](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38580468313)
and main [CI run 38581372766](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38581372766)
each passed all five jobs. [Auto Deploy run 38581681364](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38581681364)
succeeded. Public backend health and frontend build-info both returned HTTP
200 and the exact product SHA. This status-only commit will have a later SHA;
independent QA must bind its authenticated browser run to both public
surfaces. Independent QA later returned **NOT ACCEPTED** on the status-only
SHA `cd640c00c17bab0851d72d5c4dd577c24bf0d5ac` for the direct-draft
failure recorded in the current phase.

Prior phase: `CHAT_SIDE_PANEL_PROPOSAL_RESUME_AND_COUNT_READY_FOR_INDEPENDENT_QA`.
Independent authenticated browser QA returned **NOT ACCEPTED** on the
preceding live SHA `14052b67a49f584eca677e55deab7b4fed345533`:
the seven-setup comparison now kept bot links, strategy links, DCA rhythm,
and score context aligned, but a still-active proposal card vanished after
hard refresh while its feed item remained pending; a second answer listed
five Paper bots and then summarized them as four. Stop, free and guided
drafts, cancellation, navigation without refresh, draft-text persistence,
DE-to-NL context, feed-to-chat handoff, and mobile NL/EN display passed.
This was an independent browser retest, not a protected official runner
matrix; the QA fixture showed one strategy per setup.
[PR #334](https://github.com/gvangalen/antigravity-trading-tool/pull/334)
restores only the latest owner-scoped, unexpired proposal card from the
persisted run contract and gives Luna exact collection bot totals. The
confirmation token is never returned by conversation history; a click
rereads the proposal and uses the existing server confirmation boundary.
Product SHA: `a34f5166fb102b33e8bfa1cf3d938f41cc47e216`.

Build evidence on 2026-10-14: backend **3595 passed, 3 existing skips**;
frontend production build, typecheck, i18n lint/tests, command, proposal and
setup tests, and high-severity audit passed. The local worker action matrix
passed **16/16** and adapters **19/19** with zero broker orders, live bots,
live-trading calls or production connections (artifact SHA-256
`d645e43b7f5538e1e66e5e521a2d08f9f2660e914a084cd5a175f9f38d6145fb`).
Real Luna/Responses selector development passed **20/20** (SHA-256
`e1f418f96b4500b8b542a01251f170d6b522ca908fb487b1e0deef824c7c1917`)
and regression **109/109** (SHA-256
`a7e2964cb4bd3fefef631337e0eb9198c1244059d69200a71fda98986fa386c4`),
with zero provider, schema, timeout, parse or validation failures. A local
FastAPI/Celery/PostgreSQL/Responses seven-setup comparison with five
separately linked Paper bots passed three times; the final artifact SHA-256
is `ee383e0702f955afa4009daba43983bc2cb51c19970f88a4f281ef982b404a46`.
An authenticated synthetic local API run restored one active SOL proposal
after a conversation GET without exposing a confirmation token; after
cancellation, the same history returned no active proposal card. No
production account or protected QA fixture was used.
Candidate [CI run 38571556115](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38571556115)
and main [CI run 38572580266](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38572580266)
each passed all five jobs. [Auto Deploy run 38572862655](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38572862655)
succeeded. Public backend health and frontend build-info both returned HTTP
200 and the exact product SHA. This status-only commit will have a later SHA;
independent QA must bind its authenticated browser run to both public
surfaces. Independent QA later returned **NOT ACCEPTED** on the status-only
SHA `2a1d4fe50970f7c06e1b5381d6535434af2d92f5` for the score-count and
German follow-up issues recorded in the current phase.

Prior phase: `CHAT_SIDE_PANEL_RELATIONSHIP_COMPARISON_READY_FOR_INDEPENDENT_QA`.
Independent authenticated browser QA returned **NOT ACCEPTED** on the later
status-only live SHA `14052b67a49f584eca677e55deab7b4fed345533` for the
proposal-resume and count issues described above.
Independent authenticated browser QA returned **NOT ACCEPTED** on the
preceding live SHA `264b3cb1416db8332016aefe26937afd212ab9ab`: FINN
completed the seven-setup comparison but assigned Paper-bot links to the
wrong ETH setups, exposed `as_of`, and confused a DCA purchase rhythm with
an analysis timeframe. The two-setup comparison, Stop, guided proposal,
locale, mobile panel, navigation, and feed handoff paths passed in that run.
[PR #332](https://github.com/gvangalen/antigravity-trading-tool/pull/332)
groups each owner-scoped setup with its complete strategy collection, linked
bots, score conditions, and DCA purchase schedule before the model answers;
raw typed tool evidence remains in the trace. Product SHA:
`71665854afbb6fa88f11eff262ab9cd737a3c0e1`.

Build evidence on 2026-10-14: backend **3594 passed, 3 existing skips**;
frontend production build, typecheck, i18n lint/tests, command, proposal and
setup tests, and high-severity audit passed. The local worker action matrix
passed **16/16** and adapters **19/19**, with zero broker orders, live bots,
live-trading calls or production connections (artifact SHA-256
`a173f00b9aa39f0789039aa7c20440e8d9b818f1f13b130386d650dbfa73f208`).
Real Luna/Responses selector development passed **20/20** (SHA-256
`f2787fd08bf8e0990958b9288e7eed30b04e2488c6e8bb4b365cace384249883`)
and regression **109/109** (SHA-256
`d8d97db747b8a424bc6d4343d6b7d07bd63ec1b03c1c63fd2c1cff6032e3dd48`),
with zero provider, schema, timeout, parse or validation failures. Real local
FastAPI/Celery/PostgreSQL/Responses tests of the mixed seven-setup comparison
passed, including one setup with two strategy variants and two separately
linked Paper bots; the exact prior long question passed (artifact SHA-256
`418156f928bb74cfa9984a28bbeb134a8109cf1e83eb6111d9a4e1b760b2fec8`).
Candidate [CI run 38567330102](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38567330102)
and main [CI run 38567622986](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38567622986)
each passed all five jobs. [Auto Deploy run 38567898347](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38567898347)
succeeded. Public backend health and frontend build-info both returned HTTP
200 and the exact product SHA. This status-only commit will have a later SHA;
independent QA must bind its authenticated browser run to both public
surfaces. Independent QA bound to the later status-only SHA and returned the
verdict recorded above.

Prior phase: `CHAT_SIDE_PANEL_MULTI_SETUP_COMPARISON_READY_FOR_INDEPENDENT_QA`.
Independent authenticated browser QA returned **NOT ACCEPTED** on the later
status-only live SHA `264b3cb1416db8332016aefe26937afd212ab9ab` for the
bot-link, DCA-cadence, and raw-field issues described above.

Independent authenticated browser QA returned **NOT ACCEPTED** on the
preceding live SHA `cec58a52a3b86560e1426637f00195a93d296163`: the exact
read-only question about differences among the account's seven ETH setups
ended in a generic terminal error. Stop, draft, locale, navigation and mobile
panel regressions passed in that QA run. [PR #330](https://github.com/gvangalen/antigravity-trading-tool/pull/330)
repairs comparison recognition for “hoe ... verschillen”, reads every
owner-scoped setup and its complete strategy collection in one tool turn,
includes requested current scores, and evaluates the language of a long
coach answer as a whole. Product SHA:
`e206bc94f6873bafc3229bb2058a9c06ad1eac8f`.

Build evidence on 2026-10-14: backend **3594 passed, 3 existing skips**;
frontend production build, typecheck, i18n lint/tests, command, proposal and
setup tests, and high-severity audit passed. The local worker action matrix
passed **16/16** and adapters **19/19**, with zero broker orders, live bots,
live-trading calls or production connections (artifact SHA-256
`8b7ec38d5a335c9cf638c16c628ca573235bbb54ab2c70d46749ef78c5dd7012`).
Real Luna/Responses selector development passed **20/20** (SHA-256
`2fc7cfcfc9d6ab371c1a22a4636b768aba215295c32fa1f295a03d3f9ed8e71e`)
and regression **109/109** (SHA-256
`66d22ae902321d1bbf9c7bb4bf2f78793850cbf3abe69ef2eefe07399d33df69`),
with zero provider, schema, timeout, parse or validation failures. The exact
two- and seven-setup comparison each passed the local FastAPI/Celery/PostgreSQL
and real Responses path as one read-only dispatch; final artifact SHA-256 are
`0929e6735700a707c56150be3d044246f71771ade72671bf3d22eb2d98405bf2`
and `f9eefe93a7991a111552fb4827e86ea180b565e2a729ccb5be00ba93040787b2`.
Candidate [CI run 38562549523](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38562549523)
and main [CI run 38562912547](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38562912547)
each passed all five jobs. [Auto Deploy run 38563175062](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38563175062)
succeeded. Public backend health and frontend build-info both returned HTTP
200 and the exact product SHA. This status-only commit will have a later SHA;
independent QA bound to the later status-only SHA and returned the verdict
recorded above.

Prior phase: `CHAT_SIDE_PANEL_READ_AND_STOP_REPAIR_READY_FOR_INDEPENDENT_QA`.
Independent browser QA returned **NOT ACCEPTED** on the preceding deployed
status SHA `b255b3376d1db61a7289cf2913503d530cadb1bc`: the exact
read-only ETH setup comparison ended in a generic error, and Stop near
completion produced a 409 console error. [PR #328](https://github.com/gvangalen/antigravity-trading-tool/pull/328)
repairs the read-only intent, owner-scoped collection evidence, comparison
answer boundary, and completed-run Stop race. Product SHA:
`5cb0d9ec55bcaf2201cc3009170b2f0153662f8b`.

Build evidence on 2026-10-14: backend **3591 passed, 3 existing skips**;
frontend production build, typecheck, i18n lint/tests, command, proposal
and setup tests, and high-severity audit passed. The local worker action
matrix passed **16/16** and adapters **19/19**, with zero broker orders,
live bots, live-trading calls or production connections (artifact SHA-256
`827d6e808368c1aa14e3c2cc9681cfc20d7cf9eaaa95ce3696f526ad4bfd544a`).
Real Luna/Responses selector development passed **20/20** (SHA-256
`f247cbbef621c4eef088b6777aa9a1cbd77666244fda275acbff708c3c1ff4ad`)
and regression **109/109** (SHA-256
`fd04f46621c51258e9e98d136b96a42af3e01efff211553527cfac6a8f7aa685`),
with zero provider, schema, timeout, parse or validation failures. The exact
ETH comparison passed five consecutive local FastAPI/Celery/PostgreSQL and
real Responses replays; the final replay artifact SHA-256 is
`8daaed00c3e4a4fe42c4854a5af9c5818d40f15eb1cc958148c724524cccd421`.
Candidate [CI run 38557902117](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38557902117)
and main [CI run 38558218407](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38558218407)
each passed all five jobs. [Auto Deploy run 38558454656](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38558454656)
succeeded. Public backend health and frontend build-info both returned HTTP
200 and the exact product SHA. This status-only commit will have a later SHA;
independent QA must bind its authenticated browser run to both public
surfaces. The subsequent independent QA verdict was **NOT ACCEPTED** for the
seven-setup comparison; see the current phase above.

Prior phase: `CHAT_SIDE_PANEL_FINAL_FLOW_READY_FOR_INDEPENDENT_QA`.
The scoped browser QA accepted the core right-panel flow on
`4203b5fa598d29f5790ba5f5165112cc3435c164`. [PR #326](https://github.com/gvangalen/antigravity-trading-tool/pull/326)
addressed the observed 390 px composer and Stop timing gaps. Product SHA:
`be3fd2025a615be3e70162302229c48ac05e68f7`. Backend **3577 passed,
3 existing skips**; local worker action matrix **16/16**, adapters **19/19**;
real Luna/Responses selector development **20/20**, regression **109/109**.
Candidate [CI run 38543425648](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38543425648),
main [CI run 38543690770](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38543690770),
and [Auto Deploy run 38543954147](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38543954147)
succeeded. The later status-only SHA was `b255b3376d1db61a7289cf2913503d530cadb1bc`.

Prior phase: `CHAT_SIDE_PANEL_FIFTH_REPAIR_ACCEPTED_FOR_SCOPED_BROWSER_QA`.
Independent authenticated browser QA returned **NOT ACCEPTED** on the
previous live SHA `8e4f5e5a6c67247aa2987a79e21e0b22f7d37607`: the
three-turn ETH proposal, locale and draft persistence, panel, history and
mobile browser checks passed, but Stop displayed “Antwoord gestopt.”
immediately while the stored conversation showed the generic unavailable
sentence after refresh. [PR #323](https://github.com/gvangalen/antigravity-trading-tool/pull/323)
persists localized Stop text in the terminal run contract and reads the
server's terminal result back into the stopped chat bubble, including when
the worker completed before cancellation. Product SHA:
`4ac4081e412dc2b9161b7254cdeff30cff50aa74`.

Build evidence on 2026-10-14: backend **3574 passed, 3 existing skips**;
frontend production build, typecheck, i18n lint/tests, command, proposal
and setup tests, and high-severity audit passed. The local worker matrix
passed **16/16** and adapters **19/19**, with zero broker orders, live bots,
live-trading calls or production connections (artifact SHA-256
`ebc13ec3579b29030fbf1cea60f624847a41a4fed21fec53fc9ff6204306ee20`).
Local HTTP cancellation and conversation-history readback both returned
“Antwoord gestopt.” Real Luna/Responses selector development passed
**20/20** (SHA-256
`1d92e3343f2cbe7e339df2608de3e88a241ff7d8090fa63e9f48b1c7776306c8`)
and regression **109/109** (SHA-256
`77b1e34b422ce3ea04d1594f4b3e2a260133f8c6cb6065bfbfa1c7713b41516c`),
with zero provider, schema, parse, validation or timeout failures.
Candidate [CI run 38535552019](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38535552019)
and main [CI run 38535847666](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38535847666)
each passed all five jobs. [Auto Deploy run 38536073816](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38536073816)
succeeded. Public backend health and frontend build-info both returned HTTP
200 and the exact product SHA. This status-only update will receive a later
SHA; QA bound its test to both public surfaces. Independent authenticated
browser QA returned **ACCEPTED for the scoped paneel regression** on final
live SHA `4203b5fa598d29f5790ba5f5165112cc3435c164`. The Stop text
“Antwoord gestopt.” persisted exactly after hard refresh; a later read-only
answer did not overwrite it. The three-turn ETH flow left one active
proposal card without confirmation. DE→NL setup reference, unsent composer
draft, Enter, conversation history, feed handoff, add menu, side panel and
console checks passed. A 390 px composer placeholder was partly clipped
while input remained usable (P3). The worker-completed-before-Stop race,
cross-user draft isolation and the full protected-runner matrix were not
separately observed, so this is not broader FINN acceptance. The QA-verdict
documentation commit will receive a later SHA; it does not change product
code.

Prior phase: `CHAT_SIDE_PANEL_FOURTH_REPAIR_READY_FOR_INDEPENDENT_QA`.
Independent authenticated browser QA returned **NOT ACCEPTED** on the
previous live SHA `eecfbdd761355bbe25712f6c49d5b4ff7821071d`: the
language switch, unsent composer refresh, Stop, history, mobile browser
layout and console checks passed, but the guided ETH setup flow displayed
two simultaneously confirmable cards. Local public-route replay proved
that both turns referenced the same backend proposal ID, so the server did
not create two proposals. [PR #321](https://github.com/gvangalen/antigravity-trading-tool/pull/321)
retains the earlier explanation but retires its card when the same proposal
appears in a later turn. It also clarifies the model's tool-selection
instruction for a selected feed update about the whole plan versus setup
fields. Product SHA: `d8ed3e6ef9fb86e35782aeb1a5a5b23085ba10b2`.

Build evidence on 2026-10-14: backend **3571 passed, 3 existing skips**;
frontend production build, typecheck, i18n lint/tests, command, proposal
and setup tests, and high-severity audit passed. The local worker matrix
passed **16/16**, adapters **19/19**, with zero broker orders, live bots,
live-trading calls or production connections (artifact SHA-256
`b0c895ab0161eff02d8dc3bb69e456d1beba2f006513ea3829aa0a117556b626`).
The real local guided ETH replay returned one proposal ID in turns 2 and 3;
none was confirmed (SHA-256
`bfd3640b16f31868e3c2c367f38b8b1024541be4b8f3919f7cd478de902957d4`).
Real Luna/Responses selector development passed **20/20** (SHA-256
`5bed1e8a9d12bbec23c6369ab004dfc151869f9fb86df8011a2904112944f8bb`)
and regression **109/109** (SHA-256
`20c8f565a904eb3ba7e665986c26ff644ec4194a272979d4a1585f06cae8aaba`),
with zero provider, schema, parse, validation or timeout failures. An
earlier development run before the selector clarification scored 19/20
because a feed question received a setup read instead of a full plan read;
the same case passed in the complete final runs. Candidate
[CI run 38531236972](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38531236972)
and main [CI run 38531554568](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38531554568)
each passed all five jobs. [Auto Deploy run 38531792185](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38531792185)
succeeded. Public backend health and frontend build-info both returned HTTP
200 and the exact product SHA. This status-only update will receive a later
SHA; QA must bind to both public surfaces. The new live QA verdict is pending.

Prior phase: `CHAT_SIDE_PANEL_THIRD_REPAIR_READY_FOR_INDEPENDENT_QA`.
The independent authenticated browser QA returned **NOT ACCEPTED** on the
previous live SHA `9ae9ecacf175787184def2d086fc709eacf3b2c5`: the setup,
Stop, panel, history, feed handoff and mobile browser paths passed, but a
German-to-Dutch follow-up lost the named setup, an unsent ordinary composer
draft disappeared after a hard refresh, and the locale-switch toast stayed
in German. [PR #319](https://github.com/gvangalen/antigravity-trading-tool/pull/319)
repairs those three findings and merged as product SHA
`de8ac113447371d20755a763ee5db8b7c05a6d80`. The prior owner-scoped
answer and verified setup remain available after a language switch while
the old Responses provider continuation is reset. The unsent composer draft
is stored per signed-in user for the browser session and cleared on logout;
the language toast uses the destination locale.

Build evidence on 2026-10-14: backend **3571 passed, 3 existing skips**;
frontend production build, typecheck, i18n lint/tests, command, proposal and
setup tests, and high-severity audit passed. The local worker action matrix
passed **16/16**, adapters **19/19**, with zero broker orders, live bots,
live-trading calls or production connections (artifact SHA-256
`a61d77b56180c30ae77c952b189c291f2e45ba1861bfb39b37794a3d1023c4bd`).
The real local six-turn locale replay passed **6/6**, including the German
1D setup reference followed by Dutch “welke setup bedoelde je zojuist?”
(SHA-256 `ba733ad79fb0547c8f0a4ea721b5727e01ecdfb923a1ed7eaaa5e4b397e560a3`).
Real Luna/Responses selector development passed **20/20** (SHA-256
`8f878f0aa3d052953932e07c0a40929234b363825835a6c7b1825f9a99da26b5`)
and full regression **109/109** (SHA-256
`9f7e5737a02d7a5aa444a76c67fc93063b3a3ed73e00d72f6c944ae72d1637e5`),
with zero provider, schema, parse, validation or timeout failures.
Candidate [CI run 38526764853](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38526764853)
and main [CI run 38527017752](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38527017752)
each passed all five jobs. [Auto Deploy run 38527240781](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38527240781)
succeeded. Public backend health and frontend build-info both returned HTTP
200 and the exact product SHA above. This status-only update will receive a
later SHA; independent QA must bind to the SHA reported by both public
surfaces. The new authenticated live QA verdict is pending.

Prior phase: `CHAT_SIDE_PANEL_SECOND_REPAIR_READY_FOR_INDEPENDENT_QA`.
[PR #317](https://github.com/gvangalen/antigravity-trading-tool/pull/317)
merged as product SHA `4d2e43ee34b483c35b32196bfca79e18cd5b7a3c`.
Candidate [CI run 38523392138](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38523392138)
and main [CI run 38523621843](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38523621843)
each passed all five jobs. [Auto Deploy run 38523809897](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38523809897)
succeeded. On 2026-10-14, public backend health and frontend build-info each
returned HTTP 200 and exactly that product SHA. This status-only update will
receive a later SHA; QA must bind to the SHA reported by both public surfaces.
Independent QA
returned **NOT ACCEPTED** on the prior repair release SHA
`58f0ffc46f0867e6f8a76e3f08ad2f2dab10797a`: the owner-scoped setup and
conversation history worked, but a trade setup follow-up lost an already
complete proposal, its card displayed `[object Object]` as a frequency, and
Stop followed by a new question could leave the chat loading. An existing
German conversation also kept German after the UI switched to Dutch. No
proposal was confirmed and no order was executed. The current repair keeps
an open proposal across follow-ups unless the user explicitly asks for a
separate object, omits DCA frequency from trade cards, cancels a stopped V2
run and ignores its late terminal answer, and resets the model continuation
when the request locale changes. The exact three-turn ETH flow with a
different highlighted ETH setup now ends in the same unconfirmed proposal
locally. Backend **3571 passed, 3 existing skips**; web build, typecheck,
i18n, commands, proposals, setups, and high-severity audit passed. The local
worker action matrix passed **16/16**, adapters **19/19**, and recorded zero
broker orders, live bots, live-trading calls, or production connections
(artifact SHA-256 `c14cc328ffb557d96f58c97c248859672fc4d3dd9a7a48f089278c9711f22bc1`).
Real Luna/Responses selector development passed **20/20** (SHA-256
`b3d4b73da7bebb778b817c6e951a8dd51dcde2890a0643ee3452caccfbb57cee`)
and full regression **109/109** (SHA-256
`2c0cba687b707fa01fa38e57f1b516506d81ec83ff0a9e315966b184cbd5bf61`),
with zero provider, schema, parse, validation, or timeout failures. These are
Build results. Independent authenticated live QA remains pending.

Prior phase: `CHAT_SIDE_PANEL_REPAIR_READY_FOR_INDEPENDENT_QA`. [PR #315](https://github.com/gvangalen/antigravity-trading-tool/pull/315)
merged the repair as product SHA `cb3fa9d3e88b87c677564623582578aa8ed298f8`.
Candidate [CI run 38519837753](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38519837753)
and main [CI run 38520063513](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38520063513)
each passed all five jobs. [Auto Deploy run 38520226235](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38520226235)
succeeded. Public `https://tradamind.com/api/health` and
`https://tradamind.com/build-info.json` both returned HTTP 200 and exactly
that product SHA on 2026-10-14. This status-only update will have a later
deployed SHA; QA must bind to the SHA reported by both public surfaces.
The prior independent authenticated browser QA returned **NOT ACCEPTED** on backend/frontend SHA
`26f151bcfa7e86bcfc7fe9bf5541b7730ec71314`: the visible featured ETH plan
and FINN's named setup differed; a completed trade-setup conversation with
optional score boundaries omitted produced no proposal card; FINN 2.0
history was empty and did not restore the conversation after refresh.
The panel layout, direct Enter submission, open/close and navigation draft
retention, plus menu, feed handoff, NL/EN/DE and narrow browser layout passed
that QA scope. No proposal was confirmed or order executed. The repair
aligns the featured plan's workspace setup reference, exposes
owner-scoped FINN 2.0 conversation history, and clarifies the trade-setup
proposal contract. Backend **3570 passed, 3 existing skips** and web build,
typecheck, i18n, commands, proposals, setups, and the high-severity audit
passed locally. The isolated FastAPI/Celery action matrix passed **16/16**
and adapters **19/19**, with zero broker orders, live bots, live-trading calls,
or production connections (artifact SHA-256
`c549856c0522464ba1229ef5904c6d2b117413f4e7ba93665afc92e545fd3736`).
The exact rejected three-turn ETH trade-setup chat produced an unconfirmed
proposal and restored all three user turns through the FINN 2.0 history API
on a second local replay; a separate two-setup ETH fixture read the featured
setup and timeframe correctly. Real Luna/Responses selector development passed
**20/20** with zero provider failures (artifact SHA-256
`9bbf28e269ab7a460d6439f01c3c80e49b8bbda967f62ec835fe6bc196296f31`).
The full real-provider regression passed **109/109**, with zero provider,
schema, parse, validation or timeout failures (artifact SHA-256
`6a56596314001e321ad6dfd7b2a86b7a30e06388dacc8569c428423bb8329bf4`).
These were local Build results for that prior release; its independent
authenticated browser verdict is recorded above.

The prior clarification candidate was
accepted by independent QA. [PR #313](https://github.com/gvangalen/antigravity-trading-tool/pull/313)
contains the persistent web right panel, direct ordinary chat submission,
single visible composer, conversation/draft persistence, header history and
context controls, and responsive mobile chat layout. Source and the tracked
web export were built together on candidate source commit
`75a28ed2b33e108c58ea9dc2cf9e0554eb73807c`. Candidate CI run
`38516086986` and main CI run `38516310695` each passed all five jobs.
The PR merged as product SHA `906462e2f1dc2fd00bba260e9a00b563d71601b1`.
Auto Deploy run `38516477656` succeeded. On 2026-10-14, public backend
health and frontend build-info each returned HTTP 200 with exactly that
product SHA. This was deployment identity, not authenticated chat acceptance;
the subsequent independent QA verdict is recorded above. The mobile source passed Expo bundle exports,
but this repository has no configured mobile OTA/store release path.

Measured local gates on this source: backend `pytest -q` **3569 passed, 3
existing skips**. Web production build, typecheck, i18n lint and tests,
command, proposal and setup tests passed. The production dependency audit
passed its high-severity gate with one moderate Next.js advisory. Mobile
typecheck, lint (warnings only), and Expo web/iOS/Android bundle exports
passed; these exports are not native store builds or a mobile deployment.
The isolated local FastAPI/Celery/PostgreSQL/Redis/Responses safe-action matrix
passed **16/16**, and action adapters passed **19/19**, with zero broker
orders, live bots, live-trading calls or production connections. Its artifact
`.local-finn-parity-artifacts/full-action-matrix.json` has SHA-256
`3dff99f2633578d98659fbf9fb5932d16c070a98a021a9987459990b7587adda`.
Real `gpt-6-luna`/Responses selector development passed **20/20** (artifact
SHA-256 `c4e8fc9c6ae2ab797bc48365a11ff70e5e3a8723324539db4594f29916fa10e4`)
and the full regression passed **109/109** (artifact SHA-256
`c41c45c1e5bf7df660b6a4532c47940954a425234fadfd88e81764cc600bab36`),
with zero provider, schema, parse, validation or timeout failures. These are
local Build facts, not an authenticated live browser verdict.

## General FINN Clarification Choices

Phase: `OPEN_CARD_TARGET_CORRECTION_QA_ACCEPTED`. The prior live
candidate was rejected by independent QA. The repair branch
`codex/finn-guided-asset-and-locale` merged through
[PR #306](https://github.com/gvangalen/antigravity-trading-tool/pull/306)
as product SHA `703c845c4e9b313a5b37d2cafaa66fe71a866ab4`.
Candidate CI run `38458370144` and main CI run `38458644705` each passed
all five jobs. Auto Deploy run `38458901575` succeeded. On 2026-10-13,
public backend health and frontend build-info each returned HTTP 200 and
the exact product SHA. Its status-only
[PR #307](https://github.com/gvangalen/antigravity-trading-tool/pull/307)
passed candidate and main CI, Auto Deploy, and public backend/frontend identity
checks on SHA `2e61ab3e595c30ddcb7aa3f9f4a38052cd212308`. Independent QA
returned **NOT ACCEPTED** on that exact SHA: after an ETH update question,
typing an exact AAPL setup name correctly produced no AAPL proposal and
repeated three ETH choices, but clicking an ETH choice then lost the original
4H update and answered about a bot. The ordinary ETH choice, proposal
correction, and NL/EN/DE choice rendering passed. No proposal was confirmed
or order placed. The repair branch
`codex/finn-cross-asset-choice-continuation` merged through
[PR #308](https://github.com/gvangalen/antigravity-trading-tool/pull/308)
as product SHA `c87be7db44470f19bd19054443e1b84a8863baa1`.
Candidate CI run `38462991392` and main CI run `38463292648` each passed
all five jobs. Auto Deploy run `38463539289` succeeded. On 2026-10-13,
public backend health and frontend build-info each returned HTTP 200 and
the exact product SHA. Its status-only
[PR #309](https://github.com/gvangalen/antigravity-trading-tool/pull/309)
passed candidate and main CI, Auto Deploy, and public identity checks on
SHA `1673e817a40724c74e4c8daf827fd8163acba891`. Independent QA returned
**NOT ACCEPTED** on that exact SHA. The prior ETH → wrong AAPL name → ETH
choice now produced the right unconfirmed 4H card; however, correcting that
open card to another exact saved ETH name while explicitly negating the old
name cancelled the old card but failed to create the new one. NL/EN/DE
clarification and card rendering passed. No proposal was confirmed or order
placed. The repair branch `codex/finn-open-card-target-correction` merged
through [PR #310](https://github.com/gvangalen/antigravity-trading-tool/pull/310)
as product SHA `c7438eb2a021c886c1b4df5772d2b820f05b0510`.
Candidate CI run `38466790681` and main CI run `38467078660` each passed
all five jobs. Auto Deploy run `38467350122` succeeded. On 2026-10-13,
public backend health and frontend build-info each returned HTTP 200 and
the exact product SHA. The status-only
[PR #311](https://github.com/gvangalen/antigravity-trading-tool/pull/311)
passed candidate and main CI, Auto Deploy, and public backend/frontend
identity checks on SHA `eb2d92a565f859c63841fc36cd26bccb2b9f9507`.
The existing independent QA Agent returned **ACCEPTED** for the agreed
authenticated browser scope on that exact SHA. The ETH update showed three
clickable ETH names; an exact AAPL name did not create an AAPL proposal; a
clicked ETH setup produced an unconfirmed 1D → 4H card. The exact correction
to the other saved Friday ETH setup visibly retired the old card and produced
an unconfirmed 1W → 4H card without another target question. Short NL/EN/DE
checks showed translated questions and ETH-only choices. QA confirmed no
proposal or order, unchanged saved timeframes after refresh, and no browser
console errors or warnings. Server-side rejection of an old confirmation
token was not separately exercised in this read-only browser scope.

The local API/Celery regression now covers the exact Dutch correction shape,
including the positive saved name, negated old name, and 4H field. It failed
before repair because one owner-scoped resolver selected the positive name
while a second reference resolver treated both names as equal targets. Both
now read the positive correction clause; the three-turn follow-up and old
card cancellation passed locally. Complete release gates remain pending.
The final backend suite passed **3569**, with **3 existing skips**. Frontend
build, typecheck, proposal tests, i18n lint/tests, command tests and the
high-severity audit passed (one moderate Next.js advisory). The final
API/Celery action matrix passed **16/16**, adapters **19/19**, with zero
broker orders, live-trading calls or production connections (artifact SHA-256
`9fb56aca6a973a2ed3495beb75a3649e8cacacb057eaf2f49efd9f4e56226450`).
Real Luna/Responses selector development passed **20/20** (artifact SHA-256
`cbcd51ea607eaefab518d3858a5d98db5a61ef5d903cd1fee82d281fe7bd9ee5`)
and regression **109/109** (artifact SHA-256
`b0bbf2d9806a353f3e221ef03eb20b91ce363584fca53d5d93d432d39dbe6495`),
with zero provider, schema, parse, validation or timeout failures. These
local results are not a live QA verdict.

The local reproduction added the previously missing third turn to the
seven-candidate API/Celery regression. It first failed with a READ answer or
another target question, then passed when the unresolved target ID remained
missing in the guided contract and the canonical clarification retained the
original ETH update request across the wrong-asset reply. The exact ETH
choice now produces an unconfirmed owner-scoped 4H update proposal. Complete
backend tests passed **3568**, with **3 existing skips**. Frontend build,
typecheck, proposal tests, i18n lint/tests, command tests, and the high
severity dependency gate passed (one moderate Next.js advisory). The final
API/Celery action matrix passed **16/16**, adapters **19/19**, with zero
broker orders, live-trading calls or production connections (artifact SHA-256
`5e7d87b7ae133272001b53fb96fee400e17512a9dbc282f31245e1edd5c7992e`).
Real Luna/Responses selector development passed **20/20** (artifact SHA-256
`cf4abd9b9caa5e7e757ded85afe1668c744a7036e23b844fc4dcb84ae6be8229`)
and regression **109/109** (artifact SHA-256
`74e8d5e6ca18d83e228351ccdf1fbf3b7bf5dc4113fd728553234b75f1c4c84c`),
with zero provider, schema, parse, validation or timeout failures. This is
not an independent live QA verdict.
This repair keeps a pending target choice inside the original owner-scoped
asset, supplies up to three clickable names even on the fast clarification
path, and derives visible clarification language from the request locale.
The seven-candidate local API/Celery regression passed, including a free
cross-asset name and preserved 4H correction, with no confirmation. The final
backend suite passed **3568**, with **3 existing skips**; frontend build,
typecheck, proposal tests, i18n lint/tests, command tests, and the high
severity dependency gate passed. The final-code worker action matrix passed
**16/16**, adapters **19/19**, with zero broker orders, live-trading calls or
production connections (artifact SHA-256
`6660f5111c7ad18f3a2940f0420d759683cf69117bd3730ab4956e7b1f3c115a`).
Real Luna/Responses selector development
passed **20/20** (artifact SHA-256 `fbc97bb23ac2a8534e53c359f5d01e1c71ed659907655bec193d1d6de6ff833c`)
and regression **109/109** (artifact SHA-256 `4ad06f851a059f2ceab5b5fb4fd9c9a633cd1e14cc9fe5f84f79a04b9703c861`),
with zero provider, schema, parse, validation or timeout failures. These local
results do not constitute a deployed or independent QA verdict.

The first implementation merged through
[PR #298](https://github.com/gvangalen/antigravity-trading-tool/pull/298),
passed candidate and main CI, and deployed successfully. Its status-only
follow-up [PR #299](https://github.com/gvangalen/antigravity-trading-tool/pull/299)
also passed CI and deployed. Public backend and frontend each returned HTTP
200 with SHA `a6e0f265af4905fcf519be5be4e8b8ab0afa7c8a` on 2026-10-13.
The existing independent QA Agent tested that exact SHA and returned
**NOT ACCEPTED**: seven ETH setups produced no clickable choices, a typed
setup name once failed terminally, an explicit target correction left two
cards confirmable, and EN/DE variants did not consistently show options.
No proposal was confirmed or order placed. The active repair branch is
`codex/finn-clarification-live-repair`. The repair candidate
`515212bbb` merged through
[PR #300](https://github.com/gvangalen/antigravity-trading-tool/pull/300)
as product SHA `93391cdfe4bfd1e3c888401ee93b4f3fd1a0c1d3`.
Candidate CI run `38440237282` and main CI run `38440549107` each passed
all five jobs. Auto Deploy run `38440801348` succeeded. Public backend health
and frontend build-info each returned HTTP 200 and that exact SHA on
2026-10-13. The existing independent QA Agent returned **NOT ACCEPTED** on
that exact SHA: an AAPL name appeared among ETH clarification choices in
NL/EN/DE; a free exact fourth ETH name failed terminally in NL and DE; and
a correction to a nonexistent ETH setup cancelled the old card but made a
new confirmable card for the old setup. A selected ETH chip and a valid
target correction did work, with no proposal confirmed or order placed.
The active follow-up branch is `codex/finn-clarification-target-resolution`;
its repair is deployed but not yet QA-accepted.

The follow-up gives the asset named in the current turn priority during
owner-scoped target resolution and requires a visibly named replacement
target after an explicit target correction. An exact typed name is resolved
locally against that owner's records even if the persisted choice list is
missing; an unknown name cannot reuse the old proposal's ID. Local API/worker
probes with mixed AAPL/ETH records showed only ETH choices in NL and DE,
resolved the exact fourth name to the correct ETH setup, and cancelled an old
proposal without creating a new one for an unknown replacement. The full
backend suite passed **3566 tests, 3 existing skips**. Frontend typecheck and
proposal-card tests passed; no frontend source changed in this follow-up.
The real Luna/Responses selector development set passed **20/20** (artifact
SHA-256 `3968ef671f367148c07bf2b0c9ef89f90b93177821e3dc2b00f40f1061d1ca92`)
and regression passed **109/109** (artifact SHA-256
`8992ab1310b5f75ae841d50290dd04ee30e0928e7e9320ed8a675c88d0dbe3ae`),
with zero provider, schema, timeout or validation failures. The final
same-code API/Celery action matrix passed **16/16**, adapters **19/19**,
with zero broker orders, live-trading calls or production connections
(artifact SHA-256
`4bfeccc356c8d593bf22b3565c8ff77ccce2b2bace9601cb4a9ddfa519686f56`).
These local results are not an independent live QA verdict.
The repair candidate `c345739f1` merged through
[PR #302](https://github.com/gvangalen/antigravity-trading-tool/pull/302)
as product SHA `56a1d8a2f30edbbced4822b0e64333304d90f398`.
Candidate CI run `38446296810` and main CI run `38446636643` each passed all
five jobs. Auto Deploy run `38446944945` succeeded. Public backend health
and frontend build-info each returned HTTP 200 and that exact SHA on
2026-10-13. The existing independent QA Agent returned **NOT ACCEPTED** on
that exact SHA. The original wrong-asset choices and exact free-name terminal
failure were fixed in NL/EN/DE, and a nonexistent correction cancelled the
old card. The remaining failure was a three-turn continuation: after a
nonexistent replacement name, selecting another ETH setup lost the already
stated 4H change, then asked for the setup again and even showed AAPL. No
proposal was confirmed or order placed. The active repair branch is
`codex/finn-correction-guided-state`; its predecessor was not QA-accepted.

This repair preserves explicitly stated non-target changes while FINN asks
which saved object the user means. A local API/Celery reproduction of the
previously failed three-turn conversation now cancels the old Friday proposal,
offers only owner-scoped ETH setups, and turns the exact Monday choice into a
new unconfirmed proposal with the original 4H change. The checked-in
mixed-asset, seven-candidate regression also passed. The full backend suite
passed **3567 tests, 3 existing skips**; frontend typecheck and proposal tests
passed. The real Luna/Responses selector development set passed **20/20**
(artifact SHA-256 `6cbb58002e504c14c657ff106cef3891d2cfb5ecf1c65c6b320baf0bc3d0fc9e`)
and regression **109/109** (artifact SHA-256
`8cc5e899cf291c7a3be5c2960350123ea8b104d64921f4071e362393ee7d9849`),
with zero provider, schema, timeout, or validation failures. The final
same-code API/Celery action matrix passed **16/16**, adapters **19/19**,
with zero broker orders, live-trading calls, or production connections
(artifact SHA-256
`2cdf6cdaced785236637f5b26c93bb5eddb21182cb2c26e8600f4464189c10ec`).
Candidate `439b45963` merged through
[PR #304](https://github.com/gvangalen/antigravity-trading-tool/pull/304)
as product SHA `d7ddf6ef229088672835f865fbac40c2a7ebe12d`.
Candidate CI run `38451653806` and main CI run `38452051183` each passed all
five jobs. Auto Deploy run `38452309564` succeeded. Public backend health and
frontend build-info each returned HTTP 200 and that exact product SHA on
2026-10-13. The status-only [PR #305](https://github.com/gvangalen/antigravity-trading-tool/pull/305)
passed candidate and main CI, Auto Deploy, and public identity checks on
`7f0aa7828e85e1065407ed9ee8f868da94750114`. Independent QA returned
**NOT ACCEPTED** on that exact SHA: a free AAPL setup name could create an
AAPL proposal while answering an ETH target question; clickable choices were
absent in the tested NL/EN/DE clarifications; EN/DE clarification and card
copy appeared in Dutch. The previous proposal was safely cancelled, and a
free exact ETH name preserved the 4H change. No proposal was confirmed or
order placed. The active repair branch is
`codex/finn-guided-asset-and-locale`; it is not live or QA-accepted.

The repair presents up to three owner-scoped names when more than three
records match, while exact free text can still identify another record.
An imperative change followed by a request to clarify the target remains
an action proposal contract in NL, EN and DE. A target correction cancels
the previous proposal server-side before the replacement runs. Model field
aliases are filtered against the domain allowlist, with explicitly stated
canonical changes taking priority. Local real-provider probes produced the
chosen owner-scoped proposal in NL/EN/DE, including a typed fourth name among
seven; a separate correction probe found the old proposal `cancelled` and the
new one `draft`. A same-code API probe with seven candidates exposed three
clickable names, accepted a typed fourth exact name, and created only a draft
proposal for that owner-scoped target. The final full backend run passed
**3564 tests, 3 existing skips**; frontend typecheck, i18n,
command/proposal tests, build and
high-severity audit passed. One earlier action matrix run was **15/16** due
to an invalid model field alias; after the contract-boundary fix, the complete
matrix passed **16/16** and adapter tests **19/19**, with no broker order,
live-trading call or production connection (artifact SHA-256
`4cf1dddeed55d1ee5bc17b157b0773874ed980134485ba362e8d91e49af15e7d`).
The final real Luna/Responses selector development set passed **20/20**
(artifact SHA-256 `68c1967cd811dcbbe9b3a1b3639f0b5985f1704b07cd1f21ad3e0e4b746b1ff8`)
and full regression passed **109/109** (artifact SHA-256
`cafea4ee804c0f2a8e4e8291a7bad40c9e1b69558dc264faf58caa2e289f163c`),
with zero provider, schema, timeout, parse or validation failures. The
same-code API/Celery action matrix rerun passed **16/16**, adapter tests
**19/19**, and produced no broker order, live-trading call or production
connection (artifact SHA-256
`99734e0f5e0cd804929f011bb8892bb85423f486072e90b43e2e02306d7f5589`).
These local results do not replace a new independent live verdict.

## FINN Draft Card Localization

Phase: `DRAFT_LOCALE_ACCEPTED`. Build candidate
`c07970b5e5f91af60800ec9c1425a14e3acfd565` merged through
[PR #295](https://github.com/gvangalen/antigravity-trading-tool/pull/295)
as product SHA `6db6216cef9db117c543310d7806e49c90e97b6f`.
The five candidate and five main CI jobs passed. Auto Deploy completed
successfully for the product SHA. Public backend health and frontend
build-info both returned HTTP 200 and that exact SHA on 2026-10-13.
The preceding status-only SHA `a9060ee97ba184ade56db7b3637bde433be8e975`
passed all five main CI jobs and Auto Deploy; public backend health and
frontend build-info each returned HTTP 200 with that SHA. Independent
authenticated browser QA returned `ACCEPTED` for the targeted draft
localization repair on that exact live SHA. The German ADX create request
showed a confirmable German indicator card; a fully specified German BTC
DCA request showed the stated name, 1D, Friday and EUR 10 immediately;
an incomplete version asked only for the weekday and completed correctly
after `Freitag.`. EN/DE/NL draft and cancellation copy used the selected
language; cancelled cards no longer had active confirmation buttons. No
proposal was saved or confirmed and no bot or order was executed. The
browser console had no errors or warnings. QA observed two minor limits:
`Woechentlich` is displayed without an umlaut, and the UI opens an empty
chat pane on language switch, so the same visible conversation across that
switch was not proven. No run ID was visible and native mobile was not
tested. This verdict-only documentation commit requires its own public SHA
check; it does not change product code. The preceding browser QA had
returned `NOT_ACCEPTED` on live SHA
`6d2cfd878652f881eda87ec2a7dbc923ea760f62`. German ADX creation
returned a read answer without a proposal; a German weekly DCA request
reasked Friday and its reply failed; deterministic proposal text and web
cancel copy remained Dutch in EN/DE. No proposal was confirmed or executed.
The repair branch was `codex/finn-draft-i18n-qa-repair`. The local
Responses-backed web facade reproduced and passed German indicator creation,
the complete German DCA request, and a two-turn German Friday clarification;
none was confirmed. The full backend suite passed **3560** tests with **3
existing skips**. Frontend typecheck, i18n lint/tests, command/proposal/setup
tests, production build and high-severity audit passed; mobile typecheck,
lint without errors, and web/iOS/Android Expo exports passed. The final
API/Celery action matrix passed **16/16** with **19/19** adapters and zero
broker orders, live-trading calls or production connections (matrix SHA-256
`38119d773cf83f9f89a29e8b30a144b18cec03f21e8cb1cebda8a21f2ae30e05`).
The real Luna/Responses development set passed **20/20** (SHA-256
`43570aa8e976a1ca293262822ac702dace0b99f14336bee2fcadb09c28797ddd`)
and the full regression passed **109/109** (SHA-256
`adf742dee1beed33d33938100ffb7cc99cd9cfcaa460ab3940c2dd7c060cf0a7`),
both with zero provider, schema, timeout, parse or validation failures.
The local evidence above was Build validation; the independent targeted
live verdict is recorded above.

The preceding Build candidate
`cf293330cf1a8ed49f9932d74834046bcd4c0e5a` merged through
[PR #293](https://github.com/gvangalen/antigravity-trading-tool/pull/293)
as product SHA `34e1819901a90756ad589420043d26edbfe758b1`. The active
follow-up addresses Dutch text that independent QA found in German FINN
draft cards and the pending response after the accepted guided-draft repair.
The web draft cards now read button labels, statuses, detail rows, missing
fields and action summaries from NL/EN/DE dictionaries. The current locale
overrides stale conversation context on each chat request. The pending
backend envelope also uses that locale; changing language does not change
the selected proposal or confirmation boundary.

Measured local evidence: root backend suite **3552 passed, 3 existing
skips**; focused visible-delivery suite **6 passed**; frontend typecheck,
i18n lint/tests, command/proposal/setup tests, production build and
high-severity audit passed; mobile typecheck, lint without errors, and
web/iOS/Android Expo exports passed. The local API/Celery action matrix
passed **16/16**, adapters **19/19**, with zero broker orders, live-trading
calls or production connections (matrix SHA-256
`33fdfd127bc8a1101fccacc4ef98a26f8bb6cceab4fbd717372bb6534b757277`).
The real Luna/Responses development dataset passed **20/20** (artifact
SHA-256 `8eea5a0b04669996185fd0dd935e2f6b0571237f94a8c24d719b30a542ef3ae0`).
The full real-provider regression passed **109/109** with zero provider,
schema, timeout, parse or validation failures (artifact SHA-256
`9bd753313786b2c458d3a8a8f819763d899c50a4530c88ac9fa58e9e62e68f40`).
Candidate and main CI each passed all five jobs. Auto Deploy succeeded for
the product SHA. Public backend health and frontend build-info both returned
HTTP 200 and the same product SHA on 2026-10-13. The status-only commit
was deployed and checked before the independent localization run above.

## FINN Guided Draft Revision And Conversation Isolation

Phase: `GUIDED_FOLLOWUP_ACCEPTED`. Build candidate
`26f68f90bf54774c67a3ad2b8863cb2bec57a98b` merged through
[PR #290](https://github.com/gvangalen/antigravity-trading-tool/pull/290)
as product SHA `05ab912c05e47a019dfe11cf37240bb6e11b736d`. Candidate and main
CI each passed all five jobs. Auto Deploy succeeded for that product SHA.
Public backend health and frontend build-info each returned HTTP 200 and
the same SHA on 2026-10-13. This status-only commit needs its own public
SHA check before independent QA starts. Independent authenticated browser
QA returned `NOT_ACCEPTED` on the preceding live SHA
`9a7d8751edfad6743677b5d48fefacd5f7cfc045`.
The intended BTC-setup to ETH-strategy contract switch passed. QA then found
two remaining draft faults: an explicit correction of the open ETH DCA
strategy card from EUR 50 to EUR 75 cancelled the old card but failed to
produce a replacement; and after switching the same conversation from
English to German, a fresh BTC DCA request followed by “Freitag” produced
a confirmable card with the earlier English name and an unsupplied EUR 1
amount. The latter was within one conversation after a language switch,
not a verified leak between separate conversation IDs. QA cancelled the
incorrect card and confirmed no proposal or order. Ordinary strategy,
Paper-bot correction, indicator, read-only coach, and English choice checks
passed; native mobile remained unproven.

The local repair treats an explicit request for a new draft as a fresh
operation even when the pending draft uses the same contract. This prevents
the old amount slot from treating `1D` as EUR 1. For an owner-scoped open DCA
strategy card, a correction with exactly one euro amount now replaces its
base amount; trade strategies with several price fields still require a
named field. The authenticated local web-facade regression passed ten
checks, including both formerly failing conversations and cancelled old
cards, without confirmation or execution. The focused backend suite passed
**768** tests and the root backend suite passed **3551** with **3 existing
skips**. Frontend typecheck, i18n lint/tests, command/proposal/setup tests,
build and high-severity audit passed. Mobile typecheck, lint without errors,
and Expo web/iOS/Android exports passed. The local API/Celery/Responses
action matrix passed **16/16** and adapters **19/19** without broker orders,
live bots, live-trading calls or production connections (matrix SHA-256
`86dc81099a2279c8ad5b4442c1da12811682f90be0fd9146f8115982293b16b9`).
Real Luna/Responses development passed **20/20** with no provider or schema
failures (artifact SHA-256
`78e782011202d8d70dbed929e6dbdf45ef4b5eac6aa906d344b89051fe1a005a`).
The full real-provider regression passed **109/109**, with zero provider,
schema, timeout, parse or validation failures (artifact SHA-256
`154ed1c61f7325e2791d7cf0246080ee4e56c37dd863744456a67819ef579c4d`).
The product candidate is deployed. Independent authenticated browser QA
returned `ACCEPTED` for the targeted draft-flow repair on status-only live
SHA `9df6e5240c44b89e4e8bbdb85599de282bc97441`; backend and frontend
matched that SHA. QA verified the open EUR 50 ETH DCA strategy card was
cancelled and replaced by a distinct EUR 75 card for the same setup. The
English-to-German same-conversation request no longer inherited the old
English name or invented EUR 1. A genuinely new German conversation used
only its stated name, EUR 10 and Friday. Normal strategy, Paper-bot revision
and read-only coaching checks also passed; no proposal was confirmed or
executed and the browser console was clean. Native mobile remained
unproven. German draft cards and loading copy still show some Dutch text;
this is a localization follow-up outside the accepted behavioral repair.

## FINN Guided Draft Operation Switch

Phase: `GUIDED_OPERATION_SWITCH_NOT_ACCEPTED`. Build candidate
`58356dbc372f394355b43bde639aa37d537b03fd` merged through
[PR #288](https://github.com/gvangalen/antigravity-trading-tool/pull/288)
as product SHA `aa75e2e543cbd14ac05f1bdb965d34f723bc0e07`. Candidate and
main CI each passed all five jobs. Auto Deploy succeeded for that product
SHA. Public backend health and frontend build-info each returned HTTP 200
and the same SHA on 2026-10-13. This status-only commit needs its own public
SHA check before independent QA starts. Independent authenticated browser QA
returned `NOT_ACCEPTED` on the preceding live SHA
`d329b5c86f44328b141ae885cc29594a11e091d8`.
When a BTC DCA setup was awaiting an answer, an explicit request to create a
strategy for a saved ETH setup was consumed as the missing BTC setup field.
The next amount and name reply then produced a confirmable BTC setup card.
QA cancelled that card; no plan or bot was confirmed or executed. The
Paper-bot correction, ordinary strategy request, coaching, indicator, and
language checks passed in that run. Native mobile remained unproven.

The deployed repair recognizes an explicit new create operation across
setup, strategy, and bot contracts. When its operation differs from the
pending guided draft, the unanswered slot and its associated conversation
state are cleared before selecting the new contract. A local authenticated
web-facade regression reproduced the pending BTC setup and then reached the
correct owner-bound ETH strategy proposal in the same conversation. It also
verified that a corrected Paper-bot proposal cancels the old card without
confirming either. The root backend suite passed **3549** tests with **3
existing skips**; frontend and mobile gates passed. The local API/Celery/
Responses action matrix passed **16/16** and adapters **19/19**; it made no
broker orders, live bots, live-trading calls or production connections
(matrix SHA-256
`03e8b7c7fa482cb1de13dbf3989a4e1e151a1d24b21d9b165dd3f5b5133d856d`).
Real Luna/Responses development passed **20/20** with no provider, schema,
timeout, parse or validation failures (artifact SHA-256
`23d47cb44e685931f413b88cb4384ac364fbf8f5fc2df08970d77a936687ece1`).
The full real-provider regression passed **109/109**, with zero provider,
schema, timeout, parse or validation failures (artifact SHA-256
`91b5273b1c54f264826c8d7deab90488f3172c40e82acd279fe58e5f532cd9f9`).
The product candidate was deployed, but independent authenticated live QA
returned `NOT_ACCEPTED` on the later status-only SHA
`9a7d8751edfad6743677b5d48fefacd5f7cfc045`. The two follow-up faults
and their accepted repair are recorded above.

## FINN Draft Target Correction Candidate

Phase: `DRAFT_TARGET_CORRECTION_LIVE_PENDING_QA`. Build candidate
`82168d4afa91b571a610309f21410b3e2f1cf387` merged through
[PR #286](https://github.com/gvangalen/antigravity-trading-tool/pull/286)
as product SHA `adfba2ec111cd097c2f4588800e4cca77fa8d1cd`.
Candidate and main CI each passed all five jobs. Auto Deploy succeeded for
that product SHA. Public backend health and frontend build-info each returned
HTTP 200 and that same SHA on 2026-10-13. The status-only commit containing
this record requires its own public SHA check before independent QA starts.
Independent authenticated browser QA returned `NOT_ACCEPTED` on live SHA
`5d058701b9d31705d3217ebf1b9b5ce7c58d9a66`. The exact BTC DCA
three-turn flow and its review card passed. Two further flows failed: “Maak
een DCA-strategie” for an existing setup produced no proposal, while a
similarly worded “Maak een strategie” worked; and changing an open Paper-bot
card from EUR 500 to a EUR 750 botbudgetlimiet withdrew the old card but did
not create a replacement for the same strategy. QA did not confirm a proposal
or execute a bot. Native mobile remained unproven on QA's locked host.

The current repair routes an explicit imperative strategy creation request
through the existing owner-scoped strategy proposal contract; questions and
hypotheticals remain coach turns. The typed Paper-bot input parser recognizes
botbudgetlimiet, and a same-target field correction may reuse only the
owner-scoped prior card's name and strategy after that card is cancelled.
Rejected immediate-plan references still cannot inherit an older target. An
authenticated local web-facade regression created an unconfirmed DCA strategy
proposal, cancelled the EUR 500 Paper-bot card, and created a new EUR 750 card
for the same strategy. The local root backend suite passed **3544**, with
**3 existing skips**. The API/Celery/Responses action matrix passed **16/16**
and adapters **19/19**, with no broker orders, live bots, live-trading calls
or production connections (matrix SHA-256
`8e2d3eea6641059736c8ac8df7d00819146aefdd33cebb4a5c1f00d1c8abe67f`).
Frontend typecheck, i18n lint/tests, command/proposal/setup tests, build and
high-severity audit passed. Mobile typecheck, lint without errors, and Expo
web/iOS/Android exports passed. Real Luna/Responses development first passed
19/20 due to the previously observed selected-feed-plan classification
variance (artifact SHA-256
`b4df8fcd255db28a728352954eeba7e9df2268e500f14ae2b5297ee06ad96bba`);
the unchanged rerun passed **20/20** with zero provider/schema/timeout/parse/
validation failures (artifact SHA-256
`d95ca20ec35800895d789c81a6591f5b05ea743a92860bbc52e12f8f789bb992`).
The complete real-provider regression passed **109/109**, with zero
provider/schema/timeout/parse/validation failures (artifact SHA-256
`daf27f352ab3b532ec5df5262ee173b51d13904bae66f672f4fbce46546d4d0c`).
Independent authenticated QA returned `NOT_ACCEPTED` on the later
status-only SHA `d329b5c86f44328b141ae885cc29594a11e091d8`, as recorded
above.

## FINN Draft Conversation Browser Runtime Candidate

Phase: `DRAFT_CONVERSATION_BROWSER_RUNTIME_LIVE_PENDING_QA`. Build candidate
`84d1f28bb0ae570a2365670ba19276b7f697212f` merged through
[PR #284](https://github.com/gvangalen/antigravity-trading-tool/pull/284)
as product SHA `cb97746106d634e918f5fbb24983e09c6e4c1435`.
Candidate and main CI each passed all five jobs. Auto Deploy succeeded. Public
backend health and frontend build-info returned HTTP 200 and that exact SHA
on 2026-10-13. The independent browser verdict on the preceding live SHA
`e2efec85c05bdea77c6d2343c849397378dd424a` was `NOT_ACCEPTED`:
the BTC DCA dialogue reasked an answered amount mode and Friday, then failed
without a review card. The preceding strategy, Paper-bot, indicator, coach,
and EN/DE targeted checks improved or passed; native mobile could not be
proven on QA's locked host. No proposal was confirmed or executed.

The current repair binds a compound reply to the outstanding typed draft
question when that field is explicitly supplied, retains the other supplied
fields, keeps a following weekday out of the setup name, and distinguishes
DCA amount calculation from bot operation on the review card. A new local
regression follows the same authenticated `/api/assistant/chat/stream` facade
used by web, with browser page, locale, symbol, and timeframe context. It
reached an unconfirmed EUR 50 Friday DCA proposal in three turns. The final
root backend run passed **3534**, with **3 existing skips**. The final local
API/Celery/Responses action matrix passed **16/16** and adapters **19/19**;
no broker orders, live bots, live-trading calls, or production connections
were used (matrix SHA-256
`a00bbadf3960677d3131aa2d07f5f45fe7da3d47c519a2e5ceb039422e5852a2`).
Frontend typecheck, i18n lint/tests, command/proposal/setup tests, build,
and high-severity audit passed. Mobile typecheck, lint without errors, and
Expo web/iOS/Android exports passed. The first real Luna/Responses development
measurement classified one feed plan read as a setup read (19/20); the full
unchanged rerun passed **20/20**, with zero provider/schema/timeout/parse/
validation failures (artifact SHA-256
`da695daef860887c92c799fc5bd4fc4fad0ef368e619eeaf186fe16638dd19e2`).
The complete real-provider regression passed **109/109** with zero such
failures (artifact SHA-256
`7d1fd9d41e7ef2917d2e7a4b93a93d043e39648232752f8bc127c001eb546ac6`).
Build's local and deployment identity gates are complete; independent
authenticated QA owns the acceptance verdict.

## FINN Draft Conversation Design Candidate

Phase: `DRAFT_CONVERSATION_FOLLOWUP_NOT_ACCEPTED`. The follow-up code/export
candidate `76e21ac472d90bb6c645ac36232ddddc56b50e94` on branch
`codex/finn-draft-qa-followup` merged via
[PR #282](https://github.com/gvangalen/antigravity-trading-tool/pull/282).
Candidate CI and main CI each passed all five jobs. Auto Deploy succeeded for
main SHA `6086ecec34b96b2be8c6ddd26df89cb2f9859ac1`; public backend health
and frontend build-info each returned HTTP 200 with that exact SHA on
2026-10-13. Independent live QA did not accept this follow-up; the failure
and subsequent repair are recorded above.

Independent authenticated
browser QA rejected the live draft flow on product SHA
`861b046a967fb1f7571976dec02cd7c8f1c8d141`: the BTC DCA conversation
reasked supplied amount mode and weekday, then failed after the short Friday
answer; DCA strategy review omitted execution and the inapplicable risk style;
Paper-bot review omitted the supplied EUR 500 budget. The web indicator,
read-only coach, amount correction, and EN/DE question-chip checks passed.
No proposal was confirmed or executed. Native mobile was unavailable on QA's
locked host. The current local follow-up keeps explicit optional fields in a
compound clarification, aligns every guided question with its persisted slot,
separates a setup name from a following cadence instruction, and displays the
DCA strategy's execution and risk applicability. Root backend validation passed **3530** tests with **3
existing skips**. The isolated local API/Celery/Responses action matrix passed
**16/16** and action adapters **19/19**, with no broker orders, live bots,
live-trading calls or production connections (matrix SHA-256
`94d2a2dd74d84d9ea36d6817ec1289afd8a2348189d79b544da434ff4c2f8128`).
A synthetic owner-scoped API/Celery probe followed the exact compound BTC DCA
reply through to a complete but unconfirmed EUR 50 proposal; separate DCA
strategy and Paper-bot probes retained their optional amount and EUR 500
budget. Frontend typecheck, i18n lint/tests, command/proposal tests, build and
high-severity audit passed; mobile typecheck, lint without errors and Expo
web/iOS/Android exports passed. Real `gpt-6-luna`/Responses development
passed **20/20**, with no provider/schema/timeout/parse/validation failures
(artifact SHA-256
`17363f6e6a2233e7141b324ca6fa5240489441cb642d209f430b871c22cf1ab5`).
The complete real-provider regression passed **109/109**, with zero
provider/schema/timeout/parse/validation failures (artifact SHA-256
`a29741b32d24bcc6afe25d7c0825d52abeae7587a5f5d1e23a04ee04a0b69f73`).
The code candidate's local, CI, and deployment identity gates are complete;
authenticated QA owns the acceptance verdict.

The deployed design
candidate code/export SHA:
`073f69decad27f6e48771138a1a0c9b770da239c` on branch
`codex/finn-draft-conversation-design` ([PR #278](https://github.com/gvangalen/antigravity-trading-tool/pull/278)).
The complete local repair is code/export SHA
`bbccdbbc49f279d3cdc04a3b227595df72b791f6` on branch
`codex/finn-draft-conversation-repair` ([PR #280](https://github.com/gvangalen/antigravity-trading-tool/pull/280));
candidate and main CI passed all five jobs. Auto Deploy succeeded for merged
main SHA `0b579c1e632c8b773d5f8bce08ec45508f0417d2`. Public backend
health and frontend build-info both returned HTTP 200 and that SHA at
2026-10-13 06:30 UTC. This release-status-only update does not change product
code; its own eventual deployment SHA must be checked again before QA.
Candidate and main CI passed all five jobs. Auto Deploy succeeded and public
backend health and frontend build-info both returned HTTP 200 with deployed
main SHA `5c4e0b32f3b293da01d7a1f9226dcbd12f3a61e7`. A later
status-only commit does not change the product code; public health and build
info remain the runtime identity authority.
The current candidate changes every collecting
draft flow into a question in the FINN conversation. Where a small set of
choices is meaningful, web and mobile show tappable answers; choosing one
sends it as a normal user turn. Free text remains available. A review card
appears only for a complete proposal, and the existing explicit confirmation
still governs writes. Backend clarification prompts now name the missing
field rather than asking a generic question. Independent authenticated live
QA has not accepted this draft conversation design. In the authenticated live
flow, a DCA follow-up repeated a supplied weekly cadence, the clickable
"Vast bedrag" answer ended in a terminal failure and lost draft context,
and a strategy amount correction left the old EUR 50 card confirmable while
the conversation denied an open proposal. An EN/DE run also received a Dutch
missing-field question. No card was confirmed and no data was changed.
The local repair parses conditional DCA fields across turns, binds short mode
answers to the pending slot, preserves compound strategy answers, cancels
superseded proposals before provider work, suspends their web and mobile
confirmation controls immediately, and uses the requested locale for
missing-field prompts. A local API/Celery/Responses continuation created a
complete EUR 75 replacement strategy and verified that its earlier EUR 50
proposal was cancelled (probe artifact SHA-256
`266aea79274624f37b89011b2f6b8357a6c13a15f6648bb23f5dd7496166f9b4`).
The first local matrix found that the answer verifier misclassified saved
entry/stop/target prices written with a euro sign as unsupported budget
amounts. The repair checks these prices against the linked strategy while
still rejecting invented prices, cash, and budgets. Its full rerun passed.
The repair is deployed. Independent authenticated QA has not yet accepted it.

On the final local repair, root backend tests passed **3526**, with **3
skipped**. The isolated local API/Celery/Responses action matrix passed
**16/16** and adapter tests **19/19**, with zero broker orders, live bots,
live trading calls or production connections (artifact SHA-256
`efc6e74aaf0d27a76f01a4dbd747daad5de8adab69852e62573896c66cd7e56d`).
Real `gpt-6-luna`/Responses development passed **20/20**, with zero provider,
schema, timeout, parse or validation failures (artifact SHA-256
`88c3b85126c71083c9e054f011776e15761c48fc308a040d6c84cad4866203bb`).
Frontend typecheck, i18n lint, i18n, command and proposal tests, and
production build passed. Mobile typecheck, lint with no errors, and Expo
web/iOS/Android exports passed. A local EN/DE worker probe returned the
requested language for missing-field questions. The full real-provider
regression passed **109/109**, with zero provider, schema, timeout, parse or
validation failures (artifact SHA-256
`4f58bf2194d72992a74b91ef6c39d7d26fdf5d31ac32c3176f93c7f824176da1`).

## FINN 2.0 Coach Feed Candidate

Phase: `FEED_CONVERSATION_CONTINUITY_CANDIDATE`. The edited-handoff
candidate merged as product SHA `6a31d1c67f069da2149dd6bb0a8d459a1e7d0bab`.
Candidate and main CI passed all five jobs; Auto Deploy succeeded and public
backend and frontend both returned HTTP 200 with that SHA. Independent browser
QA accepted the A→X→B handoff and the direct rewritten first B-question:
FINN named B and distinguished saved 1D from pending 4H. The full conversation
was **not accepted**: after FINN answered the prefilled B-question, the next
turn denied evidence of that still-visible pending 4H proposal. No proposal
was confirmed or order executed. Native mobile remained unavailable on the
locked QA host (report SHA-256
`162151b2451b838fa392c49978a08801c3cff93d0c8ffc430ad682654551ed79`).
The direct read-only Responses completion path advances the answer cursor but
did not persist the selected feed item in the conversation. The current local
candidate stores that owner-scoped selection atomically for the current run,
preserves the composer session, and discards older plan lineage. The next
turn rereads the proposal through its owner-scoped ID. Focused regressions
for the direct completion and continuation repository passed **3/3**. Root
backend tests passed **3499**, with **3 skipped**. The isolated
API/Celery/Responses action matrix passed **16/16** and adapter tests
**19/19**, with no broker orders, live bots, live-trading calls or production
connections (artifact SHA-256
`c147999be0d25812bf9ae582ea2b76a7641773ca032b9afdff21a12e4c65e0d4`).
Real `gpt-6-luna`/Responses development passed **20/20** (artifact SHA-256
`3a1c0ee904a402cfe13f6ee78f423b4a3adde4b3f62dad050040e6f8b7d80938`)
and regression passed **109/109** (artifact SHA-256
`c541ed91293c5b5d6e68fc8ca0181ac1d327271a06b054dbf7ea1c4b4c034af4`),
with zero provider, schema, timeout, parse or validation failures. Candidate
CI passed all five jobs on code SHA
`f23ca4b80a9af303791efd6ef34b0c8a197e5ed8`. The status update,
deployment and independent QA are pending.

The previous proposal-follow-up
candidate merged as product SHA `834437f16c805f29811aa4470e106dd20a17536d`.
Candidate and main CI passed all five jobs, Auto Deploy succeeded, and public
backend health and frontend build-info both returned HTTP 200 with that SHA.
Independent authenticated browser QA did **not** accept the 1D/4H follow-up:
A→visible X→B and navigation stability passed, but editing B's prefilled chat
question removed the selected feed ID from the request. FINN therefore denied
the visible pending 4H proposal, including in a later same-conversation turn.
No proposal was confirmed or order executed. Native mobile could not be
tested on the locked QA host (report SHA-256
`db26e151f73d0ed5c54fe41ab8c1e543a6a4a64e62a9ed35fab4b0b0bbf0d42e`).
The current local candidate attaches the owner-scoped feed ID to the first
nonempty question after explicit selection even when the trader rewrites the
suggested wording. It remains read-only; the server checks item ownership and
separate confirmation. Frontend command tests passed **15/15**, i18n tests
**14/14**, i18n lint, typecheck and production build passed; targeted backend
feed tests passed **23/23**. Root backend tests passed **3497**, with **3
skipped**. The isolated API/Celery/Responses action matrix passed **16/16**
and adapter tests **19/19**, with no broker orders, live bots, live-trading
calls or production connections (artifact SHA-256
`c6426afabe278f7aa524789c0e01b7730f6431a0b4f50591893d1cf70609f488`).
Real `gpt-6-luna`/Responses development passed **20/20** (artifact SHA-256
`670428b667405fa32d538c571d8e1fa719064ec75e54a9ad9c285c798d0a2a9d`)
and regression passed **109/109** (artifact SHA-256
`7169a7c290324c63c3423d3a93c2811105a6c85d7c3ddd0a10fddfdecb467bdd`),
with zero provider, schema, timeout, parse or validation failures. Candidate
CI passed all five jobs on code/export SHA
`8f044c40335ea3230817504586754203ddcaadf3`; its status update, main CI
and Auto Deploy also passed. The independent QA finding is recorded above.

Independent live QA on product SHA
`0979563fd12fa4da3609481103313411e4902738` accepted the targeted web
answer and A→B handoff: one coherent AAPL answer without raw citation markup
or internal planning, different A/B feed IDs and correct B setup lineage after
the visible X, without refresh. It did not establish full product or native
mobile acceptance. QA found one remaining feed-context gap: a follow-up about
an open 4H proposal identified the right B setup and its saved 1D timeframe,
but could not verify that 4H was still an unconfirmed proposal (report SHA-256
`de513fa3c6397bc3571eec1c820bf5659258bbd416ab2f995539a86025e467b0`).
That released candidate carries only whitelisted, owner-scoped pending proposal
fields into FINN's read-only context and rereads the selected feed item from
the saved conversation on follow-up. Those facts reach the actual model-led
Responses prompt; a direct request-level regression proves the pending 4H
change is included. It never treats a proposal as saved or authorizes
confirmation. Root backend tests passed **3497**, with **3 skipped**. The
isolated API/Celery/Responses action matrix passed **16/16** and adapter tests
**19/19**, with no broker orders, live bots, live-trading calls or production
connections (artifact SHA-256
`fd3083d9068472ecc6d84102e8773fdd1859e97d43f68492f156073047c3bbe9`).
Real Luna/Responses development passed **20/20** (artifact SHA-256
`73186dcd81f1452f83f1628b0a5d33175fc62fa7adf2155479e4ee5a23c8b16a`)
and regression passed **109/109** (artifact SHA-256
`ff0ccdefdf93255dd4e36d8f4104ca528a02e2b61cf9da3a4cbd087bcae18fd2`),
with zero provider, schema, timeout, parse or validation failures. Candidate
CI passed all five jobs on code SHA `bd781b73829e1d0a8c76b733c885b6db55f19221`;
its status update, main CI and Auto Deploy also passed. The independent QA
finding on its deployed SHA is recorded above.

Earlier, the feed close and internal
preamble repair in [PR #273](https://github.com/gvangalen/antigravity-trading-tool/pull/273)
merged as product SHA `a494ee2117187359cbf85a78c3e59d3ea1968f31`.
Candidate and main CI passed all five jobs; Auto Deploy succeeded; public
backend and frontend returned HTTP 200 with that SHA. Independent live QA did
not accept the answer boundary: one AAPL feed discussion displayed two
concatenated answer versions and raw `citeturn0` markup in one bubble.
It saw no internal English planning in that turn, verified that the visible X
removes the modal and handoff ID, and saw translated historical feed text in
EN and DE. The exact A→B sequence could not be replayed because its two
existing ETH proposal items had expired into history; native mobile live QA
was unavailable in that session (report SHA-256
`8c6bd648609034a88d76181c3d50e0ec3cc93e8ac8dc13289eb22a6a41c0c2b7`).
The current candidate extracts the final Responses message text instead of
the Python SDK's delimiter-free `output_text` concatenation, and removes only
unrenderable citation tokens. That extraction repair has not yet been
released or independently retested. Its local validation passed: root backend
**3495 passed, 3 skipped**; isolated API/Celery/Responses action matrix
**16/16**, adapter tests **19/19**, with zero broker orders, live bots,
live-trading calls or production connections (artifact SHA-256
`cb0ab76cd62f9212e6562a8f6a8e622ca3457a9ba685bd1113a2a9d5aca4b983`).
Real Luna/Responses development passed **20/20** (SHA-256
`a51851379fed8ba88311e4c67ad809e3096ba24dd9f549dc886eb4af54dcf08f`),
and regression passed **109/109** (SHA-256
`70b9989ca4cb21cb3162ada2fb8dc945d8f5229f68f5968f17cf2bc000992b6c`),
with no provider, schema, timeout, parse or validation failures. Candidate CI
passed all five jobs on the product commit; final documentation CI, Auto
Deploy and independent authenticated QA remain pending.

The feed-modal isolation in
[PR #272](https://github.com/gvangalen/antigravity-trading-tool/pull/272)
merged as product SHA `6d370c318dc659538c6b9f3cbdc24032ac9113c1`.
Candidate CI, main CI and Auto Deploy passed; public backend and frontend
both returned HTTP 200 with exactly that SHA on 12 October 2026.
The independent browser report initially marked the A→B handoff red (report
SHA-256 `920cb66169b341a84b1b1688ede719a8f1d92e35a6dc14501b2608d536e48c88`).
A focused QA diagnosis then found its “FINN-chat sluiten” locator clicked
the background layer, leaving A's modal open. Clicking the visible X really
removed it. The A→B failure is therefore unproven; QA corrected that verdict
(diagnosis SHA-256 `c5b015fc35c065d0c4a31a9aed69ea95913bd745e114e9bccdf0c209b7206e5`).
The same QA run separately observed internal English model-planning text in
a completed user-facing answer. The current repair gives the visible X the
accessible localized close label, removes the backdrop from button selection,
instructs Luna to output only public answer text, and discards only a clearly
separated internal preamble before delivery. It preserves normal coaching
content and the existing action boundaries. Root backend tests passed **3494**
with **3 skipped**; web build, typecheck, i18n lint/tests, command tests and
the high-severity audit passed (one moderate Next.js advisory). Mobile
typecheck, lint (warnings only), and web/iOS/Android bundle smokes passed.
The first local API/Celery/Responses action matrix selected a setup deletion
for an explicit indicator deletion and finished **15/16**; the complete rerun
passed **16/16** with adapters **19/19**, no broker orders, live bots,
live-trading calls or production connections (artifact SHA-256
`e0a0a92d4ec173d7ed7e49ce52f79a3c9d125b44c176063a2f640e15747dfd54`).
The real Luna/Responses development lane passed **20/20** with no provider or
schema failures (SHA-256
`1a31daa4abf73adad937e5f40e410ba791e911f174550944dc6e0cdf36f04ce8`).
The feed-target eval expectation now leaves owner-resolved target identity to
the feed context instead of expecting the selector to echo an internal plan ID.
The complete real Luna/Responses regression passed **109/109** with zero
provider, schema, timeout, parse or validation failures (artifact SHA-256
`f663f0296c3a0d076f222c811a9bcb637fc1c411c0cb3f091f4171730cb81f25`).
Candidate CI and the real provider regressions for PR #273 passed before the
live answer-corruption finding above.

The prior sequential handoff repair merged in
[PR #270](https://github.com/gvangalen/antigravity-trading-tool/pull/270)
as product SHA `e771ab03668fa54940cf227f84b2861e257d0852`.
[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38305679512),
[main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38305868314),
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38306069920)
all succeeded. On 12 October 2026 public backend health and frontend
build-info both returned HTTP 200 and exactly that SHA. Only the web handoff,
command tests, and tracked web bundle changed; backend and provider source
remained the same as the prior green local action and Responses evidence.
The next independent QA run must repeat the A→B click without a refresh and
confirm the second visible draft, exact owner-scoped plan answer, and natural
follow-up. This status-only commit may change the public SHA without changing
product code; public health and build-info remain the runtime identity authority.

Previous independent authenticated
browser QA on public SHA `ed0a8d1dd6c7c74cf699e59fa5fc740b18759056`
returned **NOT_ACCEPTED** (sanitized report SHA-256
`c10687ab200c1c2f0aa07b490baf0e0ee2e47f2c7a8bbd66d801f784682b6717`).
Two simultaneous ETH proposals now showed their exact setup names, but after
discussing plan A, opening plan B in the same page session showed the A answer
and an empty composer. A hard refresh made B work. The next repair isolates a
selected feed handoff from the general command request and gives each
selection a fresh chat component identity. The new web command suite passed
**15/15** including priority over a later generic command request; web build,
typecheck, i18n, proposal tests and high-severity audit passed. Independent
browser validation of this repair remains pending.
The second handoff repair merged in
[PR #268](https://github.com/gvangalen/antigravity-trading-tool/pull/268)
as product SHA `22aaaceb0c39df810cc7b8a8a284072f93103084`.
[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38303518922),
[main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38303742012),
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38303969388)
all succeeded. On 12 October 2026 public backend health and frontend build-info
each returned HTTP 200 and exactly that SHA. This status-only commit may later change the
deployment SHA without changing product code; the public endpoints remain the
runtime identity authority.

The earlier repair merged in
[PR #266](https://github.com/gvangalen/antigravity-trading-tool/pull/266)
as `66c9fd3c4ce3dde8dae1537ff288f9cba8409c77`. Candidate
[CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38299438438),
[main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38299686087)
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38299892242)
all succeeded. On 12 October 2026 the public backend health and frontend
build-info both returned HTTP 200 and exactly that merge SHA. This status-only
documentation commit may produce a later deployment SHA without changing the
product code; public health and build-info remain the live identity authority.
The first release
merged in [PR #264](https://github.com/gvangalen/antigravity-trading-tool/pull/264)
as `f039774b464cabb4375d679b9dd1cf9edfb6a22d`; backend and frontend
reported that SHA with HTTP 200. Independent live QA confirmed the feed,
history, language switching, handled status and read-only chat opening, but
found three gaps: setup detail links lacked an exact setup ID, positive matches
could hide a data blocker from the top three, and draft proposals were not
visible before confirmation. [PR #265](https://github.com/gvangalen/antigravity-trading-tool/pull/265)
merged as `2857415a5a4cdaeba2c08014575ebc9c2d8be684`; public backend and
frontend reported that SHA with HTTP 200. The same independent QA Agent
confirmed specific setup links, a pending proposal before confirmation,
cancelled proposal history, historical AAPL discussion, and NL/EN/DE copy.
The verdict remained partial because a second ETH-plan feed click sometimes
left the chat query empty and a later generic question used the first plan's
context. The current repair routes feed selections directly to an explicit
chat draft and tells the selector that the selected owner-scoped feed subject
supersedes older plan references. Independent live QA on the later
documentation-only SHA `5fe0a31c24b9f963f1394cc042ea5690fb8dded9`
returned **NOT_ACCEPTED** (sanitized report SHA-256
`eede710d9859e80eca97e87a25afaa79cf44d4ac9edf42e6a91e21a3817e36d0`).
The second feed click could leave the composer empty and reuse a previous ETH
plan; simultaneous update proposals showed only the shared asset. A follow-up
batch now binds a feed selection directly to a visible new-chat draft and
resolves proposal target names through the owner-scoped database.
This second repair also starts a separate conversation when a feed item is
selected, keeps its question visible until the user sends or edits it, and
binds an explicit reread of a proposal to the proposal's owner-scoped target
instead of the proposal ID or a prior chat plan. The full backend suite passed
**3493** with **3 skips**. The real Luna/Responses development lane passed
**20/20** (SHA-256
`c0f73898fd7f5b268c9d4e715a866a12f2b99c14484a7fee20511fd51e9ea9d5`),
with zero provider, schema, timeout or validation failures. The isolated
API/Celery/Responses action matrix passed **16/16** with adapter registry
**19/19**; artifact SHA-256
`f653d438f2a647d360855c72f412660397ebc2cc01d13e002be2246643da19a9`.
Web build, typecheck, i18n, command/proposal tests and high-severity audit
passed; mobile typecheck, lint (warnings only) and web/iOS/Android bundle
smokes passed. The real Luna/Responses regression passed **109/109** (SHA-256
`dbd0ec2b42d7c959cd35a0af756dd59099d884f68be725ff3a172968924b0a4a`),
with zero provider, schema, timeout or validation failures. Candidate CI,
main CI, Auto Deploy and the public identity check passed on the SHA above;
independent authenticated QA remains pending.
The repair's full backend suite passed **3489** with **3 skips**. Web build,
typecheck, i18n, command/proposal tests and high-severity audit passed; mobile
typecheck, lint (warnings only) and web/iOS/Android bundle smokes passed. A
new real Luna/Responses development case with prior plan A and selected feed
plan B passed with the B identity and read-only plan contract; the full
development lane passed **19/19**. Selector regression passed **109/109**.
The first isolated action-matrix rerun passed **15/16**: the confirmed strategy
follow-up read the correct owner-scoped strategy but the verifier rejected the
old and new euro amounts because the typed read lacked the currency and the
confirmed prior amount. The current repair supplies EUR on a saved strategy
amount and bounds the previous amount to the same confirmed strategy ID.
Its targeted regression passes. The restarted isolated API/Celery/Responses
matrix passed **16/16** with adapter registry **19/19**; artifact SHA-256
`357ce3a4f6f856141a19aa830b78b18dbf77c98db531b2912a5db38026b59758`.
The final real Luna/Responses selector recheck passed development **19/19**
(SHA-256 `70f34ceaaf7be4b31b124011c52e16fbdcef85bdbf2533d036d03546d059fd37`)
and regression **109/109**
(SHA-256 `ed4e2e7e5e0015e016e0f7c0e93cab974b1c44bab51e685fe60d8abbca41d539`),
with zero provider, schema, timeout or validation failures. The product code
was deployed, but the independent live verdict above rejected the complete
feed-to-chat flow.
Independent Architecture and Security code reviews found no blocker after
both client and persisted prior-plan context were removed at the owner-scoped
feed handoff. The local command test confirms that only an unchanged first
feed question carries its event ID; code inspection confirms that starting a
new chat consumes that ID and closing the modal clears the draft.
Feed discussions now carry a transient owner-scoped event hint to the selector
and re-read facts for the reasoning step. Recorded event facts retain their
historical source time and are separated from a fresh Score 2.0 reread. The
additional feed discussion evidence is not yet part of the persisted V2 tool
artifact hash; replay/audit parity for that sidecar remains follow-up work.

Follow-up local gates: backend **3486 passed, 3 skipped**; frontend build,
typecheck, i18n/command/proposal checks and high-severity audit passed (one
moderate Next.js advisory); mobile typecheck, lint (warnings only) and
web/iOS/Android bundle smokes passed. The isolated API/Celery/Responses action
matrix passed **16/16**, artifact SHA-256
`ad9e7c88f647b8f345792f8bb8ef15a76e391c4f88f8382625a9804a21db98d1`.
Real Luna/Responses selector development passed **18/18**, artifact SHA-256
`c0fda9d44f7048326e103494f1f9757f897d9b312a7d07968946d94987f17eed`;
regression passed **109/109**, artifact SHA-256
`c6732ef783441742dc6b83005267f519325191cb0f9d267630104e5d3037a483`.
Independent Security and Architecture review found no follow-up release blocker.

The candidate replaces the page-triggered FINN Today block and mobile
workspace cards with one owner-scoped event feed. Completed Score 2.0 runs,
saved plan changes, pending FINN proposals and persisted Paper decisions can
publish deduplicated items. The API reads stored NL/EN/DE copy without a
provider call; a separate Luna/Responses worker writes a short neutral lead
in NL/EN/DE and chooses the emphasis once from typed evidence. Only two
subject-bound, neutral lead forms per language pass validation; the server
renders exact verified facts and action boundaries, with factual fallback.
Expired conditions and
proposals leave the active list. Discussing an item re-reads its owner-scoped
current facts and never authorizes a plan mutation or order. Onboarding no
longer starts the automatic first-dashboard briefing.

The final full backend suite passed **3483** with **3 skips**. Focused feed,
confirmation, onboarding, Score 2.0/Paper and setup tests passed. Frontend
build, typecheck, i18n lint/tests, command/proposal tests and high-severity
audit passed; the audit still reports one existing moderate Next.js advisory.
Mobile typecheck, lint (warnings only) and web/iOS/Android Expo bundle smokes
passed. Local PostgreSQL accepted the new feed migration, including durable
occurrence history. A local recurrence probe kept a handled item and opened a
separate unread item for a changed revision. An authenticated
local API probe confirmed owner isolation, deduplication, status/history,
expiry, NL/DE projection and zero provider calls on GET. A real development
Luna/Responses call via `/v1/responses` generated and passed bounded lead
validation in all three languages; rendered copy preserves the exact saved
subject and action boundary.
Real-provider selector development passed
**18/18**, and the full regression passed **109/109**, both with zero provider,
schema or timeout errors. The final isolated local API/Celery action matrix
passed **16/16**, adapter registry **19/19**, with no live trading calls,
broker orders or production connections. Its artifact SHA-256 is
`708a47e1f48c88b3c009b5f5fb34c84225ca7eff065fd0b0b1b93cd90602be18`.
One earlier matrix run had **15/16** because a saved-strategy follow-up was
reported `unavailable`; a full rerun passed. Independent QA must still cover
that continuation in the live flow. Independent Architecture and Security
rechecks found no remaining blocker after lifecycle, copy and account-scope
repairs.

Independent QA scope after deployment: same live SHA on web and mobile;
duplicate score refresh, 20 assets and multiple plans per asset, current and
stale data, pending and expired proposals, Paper decisions, owner isolation,
NL/EN/DE switching, and navigation without feed mutation or OpenAI requests.
No feed action may execute or suggest a live order. A historical item must
not present an old score as a current entry signal. Mobile native installation
is separate from the Expo bundle smoke and needs independent runtime evidence.

## Saved Report Object Names Release

Phase: `ACCEPTED_IN_LIVE_QA`. [PR #261](https://github.com/gvangalen/antigravity-trading-tool/pull/261)
merged as product SHA `b3e7776df98c0960de70e30419fda0759cb36aa2`.
[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38256060004),
[main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38256273006),
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38256511219)
passed. Public backend health and frontend build-info each returned HTTP 200
and exactly the product SHA on 2026-10-12. Independent QA on prior public SHA
`370defe7edeb132b8a298f653848652becb33c4a` returned `NOT_ACCEPTED` for
the targeted language scope. The historical report's headings and narrative
now follow NL → DE → EN → NL after reload, and FINN Today follows the active
language. The remaining defect is identity drift: the translation changed
saved setup and strategy names inside narrative prose while the typed lists
kept the exact stored names. For example a setup containing the Dutch word
`Geen` was rendered with its English equivalent in the introduction. The
saved ETH 50/20/40, setupmatch 74 and 07:20 UTC Price source moment stayed
unchanged. Analyse now showed a genuinely different current Market score 40
from a newer 12:40 source moment; the report correctly kept historical 50.
FINN Today kept the non-live bot status. QA saw no console errors and made no
new report or trading action.

This repair masks owner-scoped setup, strategy and bot names taken from the
typed saved report objects before translating narrative text. It validates
that every name token survives translation and restores the exact stored
spelling afterward. The same rule protects saved names in a localized FINN
Today briefing. Typed lists, score snapshots and persistence are unchanged.
The full backend suite passed **3468** with **3 skips**. A real Luna/Responses
probe translated English and German narrative around two saved names while
preserving both names exactly and leaving the typed score snapshot unchanged.
The final isolated API/Celery safe action matrix passed **16/16** with zero
broker orders, live calls or production connections; artifact SHA-256
`40f965de11563d629769c6f4970592676e6d3c475d856f575436f8e06072efa7`.
Real-provider selector development passed **18/18** with zero provider, schema,
timeout, parse or validation failures; artifact SHA-256
`0eac61d5a26ac0b9f5ffc8e031b9d0126cb736db3b0eccac94712885f0506a7e`.
The complete real-provider regression passed **109/109** with zero provider,
schema, timeout, parse or validation failures; artifact SHA-256
`2883df45ec9f7704e133cbb9f038643969ca93e7a54ed625d675d75716c54fb2`.
The status-only [PR #262](https://github.com/gvangalen/antigravity-trading-tool/pull/262)
merged as public SHA `554bf3b4d3516e2873d711365442785d481ee35a`.
Its [candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38256672367),
[main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38256955952)
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38257189455)
passed; public backend and frontend each returned HTTP 200 and that exact SHA.
Independent authenticated QA accepted the targeted historical-report and FINN
Today language scope on that SHA. The saved report passed NL → DE → EN → NL
with hard refresh: headings and prose followed the active language, while
saved setup names stayed byte-for-byte identical in prose and typed lists.
The saved ETH 50/20/40, setupmatch 74 and Price 07:20 UTC stayed fixed;
current Analyse separately showed Market 40 from 12:40 UTC and setupscore 81.
FINN Today used the current 81, kept the bot non-live and gave no buy advice.
The browser console had no errors or warnings and QA made no writes. A brief
flash of the previous briefing language just after switching locale remains
a minor UI polish item.

## Historical Report Section Repair and FINN Today Language Candidate

Phase: `NOT_ACCEPTED_IN_LIVE_QA`. [PR #259](https://github.com/gvangalen/antigravity-trading-tool/pull/259)
merged as product SHA `090fd29e8a99c4545df2b9cccaa5dd9cef3cea28`.
[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38252359202),
[main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38252586479),
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38252830819)
passed. Public backend health and frontend build-info returned HTTP 200 and
exactly that SHA on 2026-10-12. Independent QA on previous public SHA
`146fd87e63ca8bb0a62e2b9da4fd7a094ee4662f` returned `NOT_ACCEPTED` for
report language. NL → DE → EN → NL showed translated German headings but Dutch
report paragraphs even after reload; English narrative did translate. The
stored ETH 50/20/40 scores, setupmatch 74 and 07:20 UTC Price source moment
remained intact. Analyse had a newer 10:55 UTC Price source moment but the same
Market score 50, so a live score-value change remains unproven. QA also saw a
stored German FINN Today briefing in the Dutch and English interface. The
browser console had no errors or warnings and QA made no report, plan, bot or
trade change.

The report read path could discard an entire translated report when one
paragraph failed its language or number check. This batch retries only the
invalid paragraphs, preserves numeric facts, and checks older report text even
if its saved `content_locale` claims the target language. FINN Today now
projects its stored briefing in the active request language without changing
the stored briefing; the frontend cache and refresh follow the active locale.
Focused backend tests passed **29/29** and the final full backend suite passed
**3465** with **3 skips**. Frontend build, typecheck, i18n lint/tests,
command/proposal/setup tests and high-severity audit passed; the audit still
reports one existing moderate Next.js advisory. A real Luna/Responses local
probe translated **8/8** German report sections and preserved the typed score
snapshot. Another real-provider probe translated a stored German FINN Today
briefing to Dutch and English without changing its market score. Independent
QA later rejected translated saved object names, as recorded above. The final
isolated local API/Celery action matrix
passed **16/16** with zero broker orders, live calls or production connections;
artifact SHA-256 `401dce81eb4aed2aa921459762fb391d669f98b2b2f8ecf571355d71d856ff1e`.
The real-provider selector development set passed **18/18** with zero provider,
schema, timeout, parse or validation failures; artifact SHA-256
`52fc93b6812f06a96ea52d490afae8cc930eee5beeb53f3ebf0624d223a6e7f5`.
The complete real-provider regression passed **109/109** with zero provider,
schema, timeout, parse or validation failures; artifact SHA-256
`e725c24ad960756c4fb8176a9dee8d42681151e229b5f8f0750d33af47f3beaf`.
The existing QA task repeated the historical saved-report NL → DE → EN → NL
browser sequence and FINN Today language switches on the status SHA. Language
and typed score facts passed; translated saved object names failed.

## Report Language Request Parity Repair Candidate

Phase: `NOT_ACCEPTED_IN_LIVE_QA`. [PR #257](https://github.com/gvangalen/antigravity-trading-tool/pull/257)
merged as product SHA `ab491c895c10ae0e6c16b588a03fb6a6e913e1b9`.
[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38246760188),
[main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38246979604),
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38247161073)
passed. Public backend health and frontend build-info returned HTTP 200 and
exactly that SHA on 2026-10-12. Independent QA on previous public backend/frontend SHA
`fac5a6d7207205ed78a2f4991598c3ef62746bf4` returned `NOT_ACCEPTED` for
the preceding report-language candidate. The NL → DE → EN → NL browser sequence
left English headings and Dutch report prose visible in DE and EN, even after
waiting and reloading. Saved ETH 50/20/40, setupmatch 74, plan names, and the
07:20 UTC saved Price source moment stayed intact. Analyse later had a 10:55
UTC Price source moment but the same Market score 50; FINN correctly separated
the newer measurement from the saved report. A later different score value
therefore remains unproven. QA saw no console errors and made no report, plan,
bot, or trade change.

The root cause is now visible in the request path: the web client sends the
active `X-Locale`, but the report API ignored it and used only the stored
account locale; the report page did not refetch content when locale changed.
The German report and report-page dictionaries also contained many literal
English values. This repair makes the API use the request locale, reloads the
selected report on a language switch without allowing an older response to
overwrite a newer one, and localizes those German report strings. The saved
report, Score 2.0 facts, and bot execution are unchanged. A local request-
versus-account-locale regression, including the actual HTTP header, and a real
Luna/Responses multi-section report probe passed; the latter translated all
eight prose sections and kept the typed snapshot unchanged. Local backend
tests passed **3460** with **3 skips**. The frontend build, typecheck, i18n
lint/tests, command/proposal/setup tests, and high-severity audit passed; the
audit still reports one existing moderate Next.js advisory. The final local
worker-driven safe action matrix passed **16/16**, artifact SHA-256
`f4415ab247006be8e3e3648364bce4c4220202909d823d2aad7f0b80447f996b`.
Real Luna/Responses development passed **18/18**, artifact SHA-256
`68686aa4ef3875f24819e680001dd40d463215be55257152e002b3980972df2c`.
The complete regression passed **109/109** with zero selector failures,
artifact SHA-256
`9aa6422e9ad5a62a3e3d41fa60cca65af49e85759ff263f99749f8ce8fda81c3`.
Independent QA repeated the historical saved-report browser sequence on
status SHA `146fd87e63ca8bb0a62e2b9da4fd7a094ee4662f` and rejected the
German narrative as described above. A live score value change remains
unproven until one actually occurs. Build did not change production reports,
scores, plans, bots, or trades.

## Saved Report Language and Later Score Change Candidate

Phase: `NOT_ACCEPTED_IN_LIVE_QA`. [PR #255](https://github.com/gvangalen/antigravity-trading-tool/pull/255)
merged as product SHA `dcfb6cabe910580c0cd7034b81fc72d2ee247593`.
[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38242758865),
[main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38242990761),
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38243188124)
passed. Public backend health and frontend build-info returned HTTP 200 and
exactly that product SHA on 2026-10-12. This candidate addresses two limits from the
independent report readback QA: older report prose remains partly Dutch or
English after a switch to German, and a later change in the live Score 2.0
reading had not occurred during the authenticated browser test. Report prose
now uses a single Luna/Responses translation of only the saved narrative
fields when the requested NL, EN, or DE language differs from the report's
saved content language. New daily reports record that language in their
score-source snapshot. Older reports without a recorded language are
translated on demand. The saved score numbers, source moments, plan identities,
and other typed facts are never passed through the translation result. A
malformed, partially Dutch German, or numerically changed translation is
discarded without changing the saved report. A real development-provider
probe returned idiomatic German while preserving the score snapshot; a first,
weaker prompt had demonstrably left Dutch prose untranslated and was rejected
before this candidate.

The bounded local follow-up changes a current ETH Market score from 50 to 80
after a report snapshot at 08:15 UTC and verifies that FINN's report read tool
still returns the saved 50 while the current score tool returns 80. This is a
deterministic local regression, not evidence that production scores changed
during live QA. The full backend suite passed **3458** tests with **3 skips**;
the frontend build, typecheck, i18n lint/tests, command/proposal/setup tests,
and high-severity audit passed. The audit reports one existing moderate Next.js
advisory. The final worker-driven local safe action matrix passed **16/16**,
artifact SHA-256
`06448b6eaa5beb657951810c802fe0ba8925e96aa5c90cc5f9d0320d1d66a6b8`.
Real Luna/Responses development passed **18/18**, artifact SHA-256
`5db6526cc1ed49563928aeea2dec5f1a46ab394b7710a61ba7c6e86d257d8c7a`.
The unchanged full provider regression passed **109/109** with zero selector
failures, artifact SHA-256
`6f4d323c19ecd84e6f0b0cf127ed34ae3c3f016bc2de7716b171f6f19c1312cd`.
Build has made no
production report, score, plan, bot, or trade change.

Independent QA scope after deployment: reuse the existing QA Agent task. On
the exact public backend/frontend SHA, inspect an existing historical report
after switching NL/EN/DE and verify the narrative language, unchanged score
values and source times, and no browser errors. Compare a saved report score
with a newer live Score 2.0 value if one is available; if the live score has
not changed, record that limit rather than claiming the dynamic case passed.
Only use a protected synthetic fixture update if the active QA goal explicitly
permits it. No live order or bot activation.

## FINN Report Readback Follow-Up Candidate

Phase: `TARGETED_QA_ACCEPTED_WITH_FRESHNESS_LIMIT`. Independent QA retested
the exact saved-report comparison question on public backend/frontend SHA
`6ae71af76b8165363781b87cc2e47eb937fa4ee6` and accepted both P2 fixes.
FINN read the saved ETH 50/20/40 scores, Price/DXY/RSI source moments and
three setup matches at 74, identified report generation at 08:16:04 UTC,
and distinguished the current Score 2.0 reading. The report header showed
AAPL's missing scores separately from ETH's 50/20/40 after refresh; no
misleading global score tiles remained. The browser console had no errors or
warnings, and QA created no second report or plan/bot/trade action. During
this run the underlying scores did not change, so a later live score change
versus the saved snapshot remains unproven. FINN did not separately state the
08:15 UTC snapshot capture time in that answer. Older mixed-language German
report prose remains a separate localization issue; this targeted verdict
does not accept that prose. [PR #252](https://github.com/gvangalen/antigravity-trading-tool/pull/252)
merged as product SHA `c9335e071312367b3cf96bb9dedf678038af5659`.
[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38225207688),
[main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38225422029),
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38225600912)
passed. Public backend health and frontend build-info returned HTTP 200 with
exactly that SHA on 2026-10-12. The prior independent QA accepted the
daily-report source parity scope on live SHA
`072756dab3010e7b405f4644ca6d4312669477cc`: a newly generated ETH
report kept its 08:15 UTC snapshot after reload, and Analyse, report, and
FINN showed Market 50, Macro 20, Technical 40, and three setup matches at 74.
The report stored distinct Price, DXY, and RSI source moments; AAPL's missing
scores stayed unknown, and an older report disclosed its absent source
moments. NL/EN/DE source labels worked. QA found two follow-ups: FINN's
`read_latest_report` tool returned only metadata, so it could not itself
compare the saved report with current scores, and the global score tiles were
ambiguous for a multi-asset report. German historical report prose also
contains older mixed-language text. QA made one report, no plan/bot/trade
change, and saw no browser console errors.

This follow-up candidate passes the saved report's bounded owner-scoped score
snapshot, source times, top setups, and generation time through the existing
FINN read tool. It presents score tiles per asset when a report covers more
than one asset. It does not change the score calculation, report storage, or
bot execution. Local backend tests
passed **3452** with **3 skips**. The frontend
build, typecheck, i18n lint/tests, command/proposal/setup tests, and
high-severity audit passed; the audit still reports one moderate Next.js
advisory. The rebuilt local safe action matrix passed **16/16**, artifact
SHA-256 `fba5279e1d5e3f9b5a9d81ca8fde593cd42ebd096e8c457d1d58bae63bbec0ec`.
Real Luna/Responses development passed **18/18**, artifact SHA-256
`abf5ae89995a6494f76fab00728576988c7e3a994ec2c9599dd40d71a434a9a5`.
The first full regression was **108/109** solely because the provider rejected
an innocuous active-asset question with HTTP 400 `invalid_prompt`; artifact
SHA-256 `58c180bccd401e15d0dfa2486d3abe70b2acb84ef5f06d40330e48df6dde942a`.
The unchanged complete rerun passed **109/109** with zero provider, schema,
timeout, parse, or validation failures; artifact SHA-256
`5660221ac0dba724082100ad14f31a1f980181951e01e438d169a0a40eb89ef8`.
The isolated provider rejection remains an operational risk; the red run is
not counted as a passed gate. No production report or trade was created by
Build for this follow-up.
Build verified only the deployment identity and availability. Independent QA
should reuse the existing QA Agent task and the already saved report: repeat
the exact report-versus-current-score question, confirm FINN now names the
stored ETH score snapshot and source moments separately from newer live data,
and inspect the multi-asset report header for ETH and AAPL. Check no bot or
trade action and record the exact public QA SHA. No new report is required
for this readback-only follow-up.

## Daily Report Source Parity Candidate

Phase: `READY_FOR_INDEPENDENT_QA`. [PR #250](https://github.com/gvangalen/antigravity-trading-tool/pull/250)
merged as product SHA `abd3f8532b354981c31703ad5b4312ba130c7ca2`.
[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38221104622),
[main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38221283995),
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38221470864)
passed. Public backend health and frontend build-info returned HTTP 200 and
exactly that SHA on 2026-10-12. The candidate stores the
same owner-scoped Score 2.0 component status and indicator source moments used
by Analyse and FINN alongside each newly generated daily report. The report
page labels those scores as a saved snapshot, distinguishes their source and
report creation times, and explains that later live scores can differ. Older
reports explicitly say their separate source moments were not stored. The
affected report labels and source details use the NL, EN, and DE dictionaries.
The report still uses Luna/Responses to write coaching prose; verified scores
and setup facts come from the shared context, not the generated prose.

Measured local gates: backend **3451 passed, 3 skipped**; frontend build,
typecheck, i18n lint/tests, command/proposal/setup tests, and high-severity
audit passed (one moderate Next.js advisory). The local worker-driven safe
action matrix passed **16/16**, artifact SHA-256
`2a052f2a1c3a68b58025b32cb57f4a6d8b03ed70cabf3da741ba0ffb0263192f`.
A real Luna/Responses daily-report probe returned HTTP 200 and preserved the
typed source snapshot, artifact SHA-256
`2125747c96eccaa34e9c2c72fc7cdc1c53795a051d528dfd64ef2d38e1ddde66`.
Real-provider selector development passed **18/18** and regression **109/109**
with zero provider, schema, timeout, parse, or validation failures; artifact
SHA-256 values are
`96908d262a4d11e283ff9435269193c8ef73623cd1411159a54c5782a7c35da2`
and `fc3c993888c91eb3643c3ea2797e1ef8500cdcb8fa39d367a91eec1a6ac58d7c`.
The local parity database intentionally has only a minimal `daily_reports`
table; repository JSONB round-trip was therefore checked in an isolated full
temporary table, and production schema/application remain to be verified by
independent QA. Build verified only deployment identity and availability; no
production report or trade was created by Build. Independent QA should create
one new daily report in the existing QA account, compare its saved score facts
and source moments with Analyse and FINN at the same observation time, verify
that later changes are presented as newer rather than contradicting the saved
report, and check NL/EN/DE report labels. It should inspect an older report's
historical-source notice and avoid bot or live-trading actions.

## FINN Coach Consolidation Candidate

Phase: `TARGETED_QA_ACCEPTED_WITH_REPORT_LIMITS`. Independent QA tested
public backend and frontend SHA `b17f41d9268bb43d6c00a951e993e96e7cb2a6ed`
in the existing QA Agent task and accepted the limited retirement scope.
Authenticated FINN chat, FINN Today, Mission Control, and the existing report
remained usable; no agent-controller or agent-verdict cards and no browser
console errors or warnings were seen. FINN kept score and plan facts in a
read-only conversation, and a watchlist request remained an unconfirmed
proposal. QA did not confirm writes, create a report, or establish that all
historical backend paths are absent. QA separately found that an existing
report showed an earlier ETH setup match and price score than the later live
chat without a clear source-time distinction, and that some Dutch report
labels remain in English. Those report presentation issues remain open; this
verdict is not full FINN acceptance.

[PR #247](https://github.com/gvangalen/antigravity-trading-tool/pull/247)
merged as product SHA `2905cea6391d6ca86b58227bcfff5994ebc44ef8`.
[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38210021290),
[main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38210182356),
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38210326802)
passed. Public backend health and frontend build-info returned HTTP 200 with
exactly that SHA on 2026-10-12. The Build candidate removes the
legacy agent-controller and agent-verdict layer from plan status, daily and
portfolio coaching, Mission Control, reflection reports, and the web UI. FINN
retains its existing read tools, score and risk facts, mission workqueue, and
explicit confirmation boundary. Newly issued `agent_controller_handoff`
actions are rejected; historical audit events remain readable. This change
does not replace Score 2.0 calculations, bot execution, or reports.

The backend suite passed 3450 tests with 3 skips. The frontend build,
typecheck, i18n lint/tests, command/proposal tests, and high-severity audit
passed; the audit reported one moderate Next.js advisory. The final rebuilt
local runtime action matrix passed 16/16 with zero production connections or
live orders,
artifact SHA-256
`0af65d74f554af5edcbd9dd83a5f44551681b22b687aec8aefee4eb08b6dc69e`.
The real-provider Luna/Responses selector development set passed 18/18,
artifact SHA-256
`18c5851a93399894f88990f8fec55a9b8ee52dc3cc546535efff7d4ee2c34d3a`.
The real-provider regression set passed 109/109 with zero provider, schema,
timeout, parse, or validation failures, artifact SHA-256
`b5ce71bc3e358a5bd7167c8de911738a7e30da90a3ecfd6757729cf370f90fde`.
The status-only [PR #248](https://github.com/gvangalen/antigravity-trading-tool/pull/248)
deployed as SHA `b17f41d9268bb43d6c00a951e993e96e7cb2a6ed` after passing
[main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38210651149)
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38210807675).
Public backend health and frontend build-info both returned HTTP 200 with
that SHA. The independent QA result above applies to that exact live SHA.

## Five-Flow Current Assessment

Phase: `TARGETED_FIVE_FLOW_QA_ACCEPTED_WITH_RUNTIME_LIMITS`. Independent QA
ran the protected `score2_stale_paper` profile once against public backend and
frontend SHA `0d12d668b36caa296a376820c8c88d427e5ec7c0` in
[workflow 38205075307](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38205075307).
The protected release identity and fixture authentication passed. The
sanitized QA artifact reported `PASS`: an initially scoreable market reading
was aged 30 days in an isolated, inactive synthetic owner; Macro and Technical
remained scoreable while Market and the setup match became insufficient data.
The persisted manual Paper decision was Hold at EUR 0, with no order or ledger
entry, unchanged virtual cash, and no live bot. QA accepted this bounded
stale-source case. Artifact SHA-256:
`4bfd1ac14f5b60c9678747bc9ed1c4f79b56639dc2e7cc2ebc973caa70f5e6de`.
This proves the deployed production code path with a protected synthetic
fixture. It does not prove natural provider staleness or production Celery
dispatch. The earlier five-flow matrix and setup-origin rerun remain the
separate evidence for report, setup limits, budget, bot parity, and cadence.

The protected `score2_stale_paper` QA profile for the remaining live synthetic
stale-source case was merged in [PR #244](https://github.com/gvangalen/antigravity-trading-tool/pull/244) as product SHA `323075858973be4df8371102c31ad4cc691859b0`.
[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38204217135),
[main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38204367254),
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38204483842)
passed. Public backend health and frontend build-info both returned HTTP 200
with exactly that SHA on 2026-10-12. The profile requires explicit per-run
fixture and execution authorization, verifies the bound QA marker, creates an
inactive isolated synthetic owner, proves `change_24h` scores while fresh,
ages only that owner-scoped reading, and checks the saved Score 2.0 and Paper
Hold result. Local PostgreSQL runs passed both the successful case and a
forced validation failure that quarantined the bot while preserving evidence.
The root backend suite passed 3452 tests with 3 skips. Security and
Architecture found no remaining concrete blocker after the isolation and
failure-evidence repairs. The independent protected run and its bounded
acceptance are recorded above.

Phase: `TARGETED_QA_PASSED_FULL_STALE_EVIDENCE_OPEN`. [PR #239](https://github.com/gvangalen/antigravity-trading-tool/pull/239) merged the scoped setup-origin explanation and tracked export as product SHA `bf54e502932aa673813c29f835ada1f927b6c6c7`. [Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38189787773), [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38189942343), and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38190057057) passed. Public backend health and frontend build-info returned HTTP 200 and exactly that SHA on 2026-10-12. Status-only [PR #240](https://github.com/gvangalen/antigravity-trading-tool/pull/240) produced public QA SHA `7ad82f456d6a39c9992be71ee8a9e4a16b1862a8`; [candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38190151758), [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38190327383), and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38190441815) passed, and both public identity endpoints returned HTTP 200 with that SHA. Independent read-only QA on the exact public SHA passed the former failing case: after hard refresh the duplicated setup showed saved Macro 0–70 and explained that the values may have been carried over, with no asserted original provenance. A new unsaved setup still identified its defaults as product suggestions. QA also checked EN and DE and restored NL. No setup, bot, or order was changed during this rerun. The previous full matrix's report and Paper outcomes were not rerun on this UI-only release. The stale-but-present source remains unproven in live QA.

A repeatable local-only stale-source probe now seeds real dated PostgreSQL readings, runs the unmocked Score 2.0 builder, sends the actual Paper task through an isolated Redis/Celery queue, and checks the saved decision, order and ledger tables plus both portfolio snapshot buckets. The measured run on 2026-10-12 returned Macro 20, Market 30, Technical NULL for an RSI reading 30 days old; the canonical Smart-DCA Paper bot stayed active and not-live with Hold, EUR 0, zero orders, zero ledger entries and unchanged EUR 100 virtual cash. The local artifact `.local-finn-parity-artifacts/score2-stale-paper-run.log` has SHA-256 `5a5c1bfb00183487e6a8be4e44dab2fac8a984963b8c25ae56c72c7fd8a4b1a8`; the local score/Paper suite passed 32/32. Independent QA read the saved local score and Paper outcome and confirmed this narrower result. This uses synthetic local indicator history and a local worker; it does not prove a stale production provider source or the production queue. The production stale-source case remains open.

The repeatable local probe and snapshot bootstrap were merged in [PR #242](https://github.com/gvangalen/antigravity-trading-tool/pull/242) as SHA `3df1f9f466f6beff212e71cbd7eb5c48f96833fc`. [Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38191835722), [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38191974736), and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38192083204) passed. Public backend health and frontend build-info both returned HTTP 200 and exactly that SHA. Independent read-only QA on the same SHA found no naturally testable stale-but-present score source: the linked ETH Paper plans had current Market (12 October 00:10 UTC), Macro (11 October 23:59 UTC), and Technical (11 October 23:55 UTC) source moments; AAPL showed a stale price display but no configured score indicators or component scores. QA did not change data or start a Paper assessment. The local PASS must not be read as a live stale-source acceptance. This status-only update will have a later deployment SHA without product-code changes.

Independent authenticated QA ran the complete five-flow matrix on previous public backend/frontend SHA `fd3aa55b515e7d74e11069e92cb4b2638053e8ac` and returned `NOT_ACCEPTED`. A new report rendered without 502 and matched Analyse for ETH Market 40, Macro 20 and Technical 40 while distinguishing missing AAPL scores. Budget versus Paper cash, linked strategy and mode, and DCA cadence versus 1D chart timeframe passed. A new positive ETH match bought EUR 3.25 virtually once (0.001277 ETH); reassessment caused no second purchase. ETH Macro 20 below its saved minimum 30 and an AAPL bot with missing scores both held without purchase. No live bot or broker order was used. One of the five points was only partial: a duplicated setup carrying a saved, customized Macro minimum of 0 showed an editor sentence calling those limits general product suggestions. The repair distinguishes default suggestions on a new setup from saved, edited, and partially empty limits on existing setups, in NL/EN/DE. It also initializes edit sliders from the saved limits on first render. Frontend build, typecheck, i18n lint/tests, command/proposal/setup tests, and high-severity audit passed (one moderate Next.js advisory). The local score-to-worker Paper-chain suite passed 32/32, including a dated but stale source that yields Hold, zero amount, and no order. A stale-but-present score source could not be exercised in live QA without artificially changing the protected fixture and remains a live evidence gap rather than a passing production case.

## Paper Hold Amount Presentation

Phase: `TARGETED_QA_PASSED`. [PR #236](https://github.com/gvangalen/antigravity-trading-tool/pull/236) merged the scoped Hold amount presentation repair and tracked export as product SHA `3d6c6f22a12cb12593a853edafc7799218e9a0a1`. [Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38188002655), [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38188142640), and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38188279299) passed. Public backend health and frontend build-info returned HTTP 200 and exactly that SHA on 2026-10-12. The status-only [PR #237](https://github.com/gvangalen/antigravity-trading-tool/pull/237) then produced public QA SHA `fd79f416040d7774e2c5fd0e43ffba06db64effd`; its [candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38188397252), [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38188510807), and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38188637725) passed, and both public identity endpoints returned HTTP 200 and that SHA. Independent read-only QA on that exact SHA passed: after hard refresh the AAPL Paper bot stayed `HOUD VAST` for incomplete benchmark data without `OPTIMALE GROOTTE` or a proposed amount; virtual cash remained EUR 20, position zero, and day spend zero. An existing ETH `KOOP` decision still displayed its adjusted EUR 2 amount. QA did not start a new assessment or order and did not recheck the ledger in this presentation rerun. This final documentation update has a later SHA but no product code change.

Independent QA on previous public backend/frontend SHA `01fb393bc5723b3f750fc83a236b823dafc53edf` passed the risk-limit wording check: the AAPL Paper bot remained `HOUD VAST` for incomplete benchmark data with EUR 20 virtual cash, zero position and zero day spend; the diagnostic said `Risicolimieten / RISICOLIMIETEN IN ORDE`. QA also found that the same Hold detail still showed `OPTIMALE GROOTTE €3`, although no order was proposed or executed. The scoped frontend repair shows the adjusted-size card only when the persisted decision action is `buy`; it does not change guardrail, Score 2.0, or execution logic. Frontend build, typecheck, i18n lint/tests, command/proposal/setup tests, and high-severity audit passed (one moderate Next.js advisory), and the tracked export was regenerated. Backend action contracts, model/provider selection, score logic, and execution are unchanged from the preceding release.

## Paper Risk Label Scope

Phase: `TARGETED_QA_PASSED`. [PR #234](https://github.com/gvangalen/antigravity-trading-tool/pull/234) merged the scoped Paper risk-limit copy and tracked export as product SHA `ac8a1a71aeae157d389dadc55362accb5b1b3c4a`. [Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38187142427), [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38187309121), and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38187439500) passed. Public backend health and frontend build-info returned HTTP 200 and exactly that SHA on 2026-10-12. Independent QA subsequently verified the risk-limit wording on final public SHA `01fb393bc5723b3f750fc83a236b823dafc53edf`; its residual Hold-size presentation finding is addressed in the current scope above.

Independent QA on previous public backend/frontend SHA `403ee93aeb36509b5132e6bfd29f83409dde0616` passed the strategy-edit UI correction: the linked setup is visibly fixed, and renaming the strategy preserved both the setup and Paper-bot link after hard refresh. QA then used the normal FINN UI to add AAPL without configured indicators. Analyse showed no Market, Macro, Technical, or combined Score 2.0 result. One due, Paper-only assessment saved `HOUD VAST` with reason that current benchmark data was incomplete, one EUR 0 hold log, EUR 20 cash, zero AAPL, and zero day spend after refresh. The previously missing-score no-buy case is therefore independently proven. An intentionally stale-but-present score was not separately exercised.

The same QA run found a presentation mismatch: its detailed guardrail pane labeled the risk-limit subcheck `GROEN / VRIJ` while the overall bot decision correctly held for incomplete benchmark data. This candidate scopes that label, heading, and explanatory copy to risk limits in NL/EN/DE, so a passed risk limit no longer sounds like permission to buy. Decision logic, score calculation, and Paper/Live execution are unchanged. Frontend build, typecheck, i18n lint/tests, command/proposal/setup tests, and high-severity audit passed (one moderate Next.js advisory); the tracked frontend export is updated. Backend action contracts, model/provider selection, score logic, and execution are unchanged from the preceding release, so its measured backend tests, API/Celery action matrix **16/16**, adapters **19/19**, and real Luna/Responses development **18/18** plus regression **109/109** remain applicable. Independent live wording QA is pending.

## Strategy Setup Link Clarity

Phase: `READY_FOR_INDEPENDENT_QA`. [PR #232](https://github.com/gvangalen/antigravity-trading-tool/pull/232) merged the strategy setup-link UI clarification and tracked frontend export as product SHA `1104bac584ff5300a4a7101da9d8dbaffb37e590`. Its first candidate CI failed because the tracked frontend export was omitted; the corrected [candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38185854978), [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38185981459), and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38186095884) all passed. Public backend health and frontend build-info returned HTTP 200 and exactly that product SHA on 2026-10-12. This status-only update will have a later SHA; QA must bind to both public surfaces. Independent QA of the edit-form clarification and the missing/stale-score production case is pending.

Independent QA on previous final public SHA `573eee1a42b690dfe3a16da1fb3a00813c3435d6` proved the previously failing positive Score 2.0 → Paper path: a new daily ETH bot with setup match 81% bought EUR 3.25 virtually once, moved Paper cash from EUR 20 to EUR 16.75, persisted 0.001281 ETH, and a replay added no second order. A separate due bot with Macro 20 below its setup minimum 30 saved a new `HOUD VAST`, with EUR 20 cash, zero day spend and zero ETH. Report/Analyse score parity, visible setup boundaries, botbudget versus Paper cash and daily cadence were observed. QA returned `NOT_ACCEPTED` for the complete five-flow matrix because its fixture had no safely testable missing or stale score source on this SHA. No live order or broker call occurred.

QA also found that the strategy edit form offered a new setup choice, showed a successful save, then reopened with the original setup. Build traced this to the intentional immutable setup relationship in `updateStrategy`: the API client omits `setup_id` from updates. The local UI repair disables the setup selector while editing and explains in NL/EN/DE that a new strategy is needed for a different setup. It does not change the persisted relationship or bot execution. Root backend tests passed **3451** with **3 skipped**; frontend build, typecheck, i18n lint/tests, command/proposal tests and high-severity audit passed (one moderate Next.js advisory). Backend action contracts, provider selection and execution code are unchanged from the immediately preceding release; its measured local API/Celery action matrix **16/16**, adapters **19/19**, and real Luna/Responses development **18/18** plus regression **109/109** remain applicable evidence for those unchanged paths. The UI clarification is deployed; independent authenticated edit-form QA is pending. The missing/stale-score production case remains an independent QA evidence gap.

## Paper Decision Status Contract Repair

Phase: `READY_FOR_INDEPENDENT_QA`. [PR #230](https://github.com/gvangalen/antigravity-trading-tool/pull/230) merged the Paper decision status migration as product SHA `a4fa00d8000ac2681ad1948d52387749711927e0`. [Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38184419396), [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38184578990), and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38184698519) passed. Public backend health and frontend build-info returned HTTP 200 and exactly that SHA on 2026-10-12. This status-only update will have a later SHA; independent QA must bind to the SHA returned by both public surfaces. The positive Score 2.0 match → new Paper decision → virtual execution, plus outside-boundary and missing/stale-score no-buy outcomes, remain pending independent live acceptance.

Independent authenticated QA on previous public backend/frontend SHA `a33100d341269e2a242b7bee0b8d1ffcc034dd8a` returned `NOT_ACCEPTED` for the complete five-flow release. Report/Score 2.0 parity, visible setup boundaries, Paper budget terminology and displayed DCA cadence passed. The controlled positive match reached the new Paper reassessment route, but its single confirmed attempt returned HTTP 502 without a new decision or virtual order; EUR 20 Paper cash and zero ETH remained. The outside-boundary weekly bot was not due that day, so it did not prove a new Hold. Missing/stale-score behavior also remains unproven in that independent run.

Build traced the 502 in scoped production error logs to PostgreSQL `bot_decisions_status_check`: the positive decision computed setup match 81 and proposed EUR 6.50, then the claim of status `executing` failed because the live check allowed only `planned`, `ready`, `approved`, `executed`, `skipped`, and `failed`. The transaction then aborted and the route returned 502. The local repair migrates the check to also allow `executing` and `failed_execution`, registers that migration before application startup, and keeps the disposable baseline consistent. A local PostgreSQL probe reproduced the old schema shape, applied the migration, passed `planned → executing → failed_execution → executed`, and rejected an invalid status. Targeted tests passed 39/39; root backend tests passed 3451 with 3 skipped; frontend build, typecheck, i18n lint/tests, command/proposal tests, and high-severity audit passed (one moderate Next.js advisory). The isolated local API/Celery/Responses action matrix passed **16/16** with adapters **19/19**, zero broker orders, live bots, live-trading calls or production connections (artifact SHA-256 `187b42358c8a4c6426d63f8e6565bee5449b779fe70c62c4585408593ab890c0`). Real Luna/Responses development passed **18/18** (SHA-256 `012de78b4bc4feb2c63c5dfb0f687ebb66a991bbdb645fc282908822a7aabfc2`) and regression **109/109** (SHA-256 `ab96d391612211049afb0a68df8d6c010cd5a974646a38cd2135c763d5d29e08`), with zero provider, schema, timeout, parse or validation failures. Security and Architecture read-only reviews found no concrete blocker; both noted the transactional DDL may need a short table lock. Independent retest is still pending at this phase. Build has not accessed the protected QA fixture or executed a production bot order.

## Active Five-Flow Release

Phase: `READY_FOR_INDEPENDENT_QA`. [PR #228](https://github.com/gvangalen/antigravity-trading-tool/pull/228) merged the explicit Paper reassessment repair into `main` as product SHA `5356d125c57bafa6706f1340c31fe41e62c02298`. [Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38182423351), [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38182539890), and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38182662718) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` each returned HTTP 200 and exactly that SHA on 2026-10-12. This status-only update will have a later SHA; independent QA must bind to the SHA reported by both public surfaces. The five targeted product repairs are live, but the complete release remains **not accepted** until independent authenticated QA proves a positive Score 2.0 setupmatch, a new Paper decision, and a controlled virtual Paper execution, plus outside-boundary and missing/stale-score no-buy behavior. Build performed no authenticated production bot assessment or order.

Phase: `PAPER_REASSESSMENT_CANDIDATE_LOCAL_VALIDATION`. Independent QA on public SHA `d8881cb7bd56b3b029b7552ff33373a7513cb67c` did not accept the complete five-flow release: it verified a positive ETH Score 2.0 match and a persisted EUR 20 virtual Paper balance after explicit funding, but the bot still displayed an older insufficient-funds Hold and the UI offered no explicit way to request a new score-driven Paper assessment. No Paper execution was proved. The current local candidate adds an explicitly confirmed Paper-only assessment action, marks pre-funding Holds as superseded, guards against reopening an executed same-day decision, and reports saved-decision versus virtual execution outcomes separately. A dedicated server route rejects a bot that is Live or inactive and forces the server's current date; the worker checks Paper mode again and the auto executor retains its owner-scoped locked mode check. Implicit reassessments after budget edits and manual trades were removed. A real-provider regression exposed one existing confusion between reformulating and explaining a previous verified answer; the typed reformulation constraint now applies to verified and released answer lineage. The candidate has not yet been deployed or independently re-tested; do not treat the five flows as accepted.

Measured local release gates for this candidate: root backend tests **3450 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command/proposal tests and high-severity audit passed (one moderate Next.js advisory). A first action-matrix run concurrent with selector evaluation was **15/16** because the create-strategy guided follow-up was not selected; the isolated full rerun passed **16/16**, with adapter tests **19/19**, zero broker orders, live-trading calls or production connections (artifact SHA-256 `e58f7e4d90dea71a5deac44a476d32869d0d78dd0eafd4c1b14b04fa36975b09`). The first real Luna/Responses regression was **108/109** due confusion between explanation and reformulation of verified lineage; after the typed-lineage repair, final development passed **18/18** (artifact SHA-256 `2f66a274de1953191d910bcac4088422200933a726d6dacc34f9dd2a5da15024`) and full regression **109/109** (artifact SHA-256 `52ca8fca2b88d3b7357671f24c2ee06b28b5484a2bded515c3584ec33b018854`), with zero provider, schema, parse, validation or timeout failures. Security and Architecture independently rechecked the final Paper-only route and found no remaining concrete code blocker. These local gates do not prove a production Paper execution.

Phase: `READY_FOR_INDEPENDENT_QA`. [PR #226](https://github.com/gvangalen/antigravity-trading-tool/pull/226) merged the Paper-funding repair into `main` as product SHA `766eb734de5145bdc6ba735304e855209ee7235a`. [Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38178931795), [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38179080340), and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38179209577) all completed successfully. Public backend health and frontend build-info each returned HTTP 200 and exactly that SHA on 2026-10-12. This status-only update will have its own later SHA; QA must bind to the SHA shown by both public surfaces. Independent authenticated positive Score 2.0 match → Paper decision → controlled Paper execution, as well as outside-boundary and missing/stale-score outcomes, remain pending. Build has not accessed the protected QA fixture or performed a production bot funding or order.

Build evidence for this phase: Independent QA verified the five targeted product repairs on earlier live SHA `077ab0bdd969c463be1691f6e0ce671b99c7b2e4`, but the positive Score 2.0 setupmatch did not yield a proved Paper execution. Build traced this to the distinction between a bot spending limit and actual virtual Paper cash: an unfunded bot has no spendable portfolio balance. The repair introduces one explicit, idempotent Paper starting credit, exposes it separately from the bot budget, allows an activity-free existing Paper bot to receive its first credit, makes manual preview/preflight/create and automatic/manual decision execution recheck actual cash under a shared bot and portfolio lock, and keeps FINN from combining Paper and Live cash. A local PostgreSQL two-transaction probe proved a second Paper debit waited for the first and read the updated EUR 20 balance; a duplicate initial credit did not book again. A follow-up review found and Build repaired a manual-order budget race by re-reading the bot after its lock, rejects fractional-cent funding, separates Paper and Live portfolio history when both are shown, and calls the remaining budget a limit in the API and mobile mapping. Root backend tests passed **3442**, skipped **3**; frontend build, typecheck, i18n lint/tests, command/proposal tests, and high-severity audit passed (one moderate Next.js advisory). Mobile typecheck, lint (zero errors, existing warnings), and web/iOS/Android bundle smoke passed. The first local real API/Celery/Responses action matrix was **15/16** due a strategy guided-follow-up selection failure; final-code full run passed **16/16**, with adapter tests **19/19**, zero production connections, broker orders, live bots, or live trading calls (artifact SHA-256 `7fd0762505bd52ac88cef8093dc4153d4fbf57c98fd7108b437cfbb7b255987d`). Real-provider selector development passed **18/18** (SHA-256 `7b30fb3347dc220d9d5f1d020614cfe25631488a79eaeddb2e527c5e102b6049`) and regression **109/109** (SHA-256 `bdd961ee086bb87536f859e36231c99623b6b63be735f6b612a0c8995c6d52f8`), using `gpt-6-luna` over Responses with zero provider, schema, parse, validation, or timeout failures. Local evidence does not prove the production Paper execution.

Phase: `FIVE_FLOW_LIVE_QA_PARTIAL_PAPER_PROOF_PENDING`. On 2026-10-11, independent QA confirmed backend and frontend HTTP 200 on exact SHA `077ab0bdd969c463be1691f6e0ce671b99c7b2e4`. A fresh BTC daily report persisted the current price and named strategy; an ETH report did not contradict its complete 40/20/40 scores; a newly loaded tab showed all three strategy/setup pairs. The initial blank card in an old tab did not reproduce after a fresh load; its precise cache cause remains unknown. QA also verified that a first `Nieuw` click generated an ETH report at 20:59 and a second click within 60 seconds retained that timestamp with the translated recent-report reuse notice. Score-boundary visibility, botbudget as a limit, Paper mode, and fixed Friday DCA cadence passed on the preceding same-feature SHA. PR #225, main CI, and Auto Deploy passed; public SHA checks passed. The five requested product repairs are live and the targeted report hertest passed. A positive scorematch-to-controlled-Paper decision and Paper execution remain unproven because the available bot had trading off; no live order is authorized.

Phase: `DAILY_REPORT_REFRESH_AND_FACT_PARITY_LIVE_QA_PENDING`. Independent live QA on public SHA `3c55b48d93eb60b47c3411769972b87bb1762473` returned **NOT_ACCEPTED** for the complete five-flow scope: an explicit `Nieuw` request reused a same-day BTC report while the UI said it was ready; the ETH report showed current 40/20/40 scores but later claimed DXY/RSI values were missing; a multiple-strategy report card showed no named strategy; and a positive 81/100 setupmatch had no proved Paper execution. Score-boundary visibility, score-free fixed Friday DCA, botbudget as a limit, Paper mode, missing-score hold, and the existing bot cadence passed. The repair gives explicit manual report requests a 60-second repeat guard independent of the scheduled 30-minute cooldown, makes UI copy truthful when a recent report is reused, rejects an unsupported missing-data outlook against complete Score 2.0 components, and lists multiple owner-scoped strategy/setup pairs instead of selecting one silently. Targeted report/runtime tests passed **22/22** and the full root suite passed **3428**, skipped **3**. Frontend build, typecheck, i18n lint/tests, command/proposal/setup tests, and `audit:high` passed (one moderate Next.js advisory). Final local API/Celery action matrix passed **16/16** and adapters **19/19** (artifact SHA-256 `72ec91092b33e7247672f39ad37115d8a53ef6890426d3676375773fa421acba`). Real Luna/Responses development passed **18/18** (SHA-256 `11469583651ff1e6c1f4f5120b83e72f0606d1860f6714485fc7e1f0344c391f`) and regression **109/109** (SHA-256 `471e20a99f505c7db746ab253aefeda67294bcc26061d6373abdb563c9bd1b00`), with zero provider, schema, timeout, parse or validation failures. [Main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38173503152) and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38173619433) passed. Public backend health and frontend build-info each returned HTTP 200 and exact SHA `66f2492a52f30f51f98e5ce0a4aee8bb7a288ed5`. Independent QA of this candidate and positive Paper execution remain pending.

Phase: `FIVE_FLOW_REPORT_BOT_PARITY_LOCAL_CANDIDATE`. Independent live QA on public SHA `74c1837c9903f0652607967838304d9fe042ea98` found that the first new-user flow persisted onboarding, setup, strategy, Paper bot, and personal FINN Today briefing; the daily report agreed with incomplete Score 2.0 data; fixed DCA correctly had no score bounds; and the exact three repaired owner-scoped chat reads passed. Remaining related presentation defects were a strategy report card showing the setup name and no available fresh price, and My Plan calling an active manual Paper bot simply “Bot actief”. This candidate projects a dated fresh market snapshot into the shared report facts, keeps strategy and setup names distinct, and labels Paper and live bot modes separately in plan and strategy cards. Targeted shared-context tests passed **12/12**; the full root backend suite exited 0; frontend build, typecheck, i18n lint/tests, command/proposal/setup tests, and `audit:high` passed (one moderate Next.js advisory). The local real API/Celery action matrix passed **16/16** and adapters **19/19** with artifact SHA-256 `1993f8d9aba8a5ff7ee65df318b3f952f6bc813b160fcb576b0a1e14b84b7f5f`. Real Luna/Responses development passed **18/18** (SHA-256 `60f91a2098d9a6f51991b18a27740853fccff55f21f90ca3a92726cfe736eddd`) and regression **109/109** (SHA-256 `acd917c12f4ad5a744426dc8f824ee9691c87e2672e610c85138821bf183ca8f`), with zero provider, schema, timeout, parse or validation failures. CI, deployment identity, independent live QA of this candidate, and a positive score-driven Paper execution are still pending.

Phase: `SLASH_ASSET_PAIR_COLLISION_CANDIDATE`. Independent authenticated QA on public SHA `d65e5f479488db02d3e9cfb34e8d5c1fc5dd7fbb` returned **NOT_ACCEPTED**: the exact three-setup inventory question passed, but a broad comparison and named relationship read both ended with a terminal failure. A local real API/Celery/Responses reproduction with three owner-scoped ETH setups reproduced both failures as `responses_provider_error` within 0.5 seconds; the provider returned HTTP 400 because `Paper/live-status` was misclassified as an unsupported trading pair. That removed all tools while the turn also forced `get_saved_setup_inventory`. The candidate recognizes a slash pair only with a known trading quote or uppercase ticker-like symbols, and never forces a tool absent from the submitted tool definitions. The same three exact turns completed read-only in the local real-provider reproduction after the repair. Root backend tests passed **3424** with 3 skipped; the final API/Celery action matrix passed **16/16** and adapters **19/19**, with zero broker orders, live bots, live-trading calls or production connections (artifact SHA-256 `0805df0efad19295b51e6f2b666a0d0db438360925500db316aa4c6124a05b0e`). Canonical frontend gates passed. Real Luna/Responses selector development passed **18/18** (artifact SHA-256 `41c05a3393dcb41ce070e1255fc519c3f430e54a89fbf7364505befa08a457e0`) and regression **109/109** (artifact SHA-256 `2c50a38c4782b9d5fac8063b9227414e36997770728ce1dc466f1e26b8f2e30a`), with zero provider, schema, timeout, parse or validation failures. Independent live QA remains pending. The new day report, score boundaries, bot budget semantics, Paper modes and cadence passed QA; positive score-driven Paper execution and the missing-score case remain unproven.

Phase: `NEGATED_READ_AND_LINKED_RELATION_REPAIR_CANDIDATE`. Independent authenticated QA on public SHA `1d80f66e927890cb555f789c8784482fbbc57131` returned **NOT_ACCEPTED**. A broad nameless ETH inventory read found three setups, but the exact question ending in “Wijzig niets” found only one, and a broad comparison plus named relationship follow-up said the saved relations were unavailable. The newly generated Dutch day report passed, with Prijs/DXY/RSI, three setups and Score 2.0 values. Score boundaries, bot budget semantics, Paper mode and cadence passed. A fresh positive automatic Paper decision and the missing-score case remained unproven. Root cause reproduced locally: the no-change clause was classified as `update`, and model-led relational reads could answer without first reading the owner-scoped setup graph. The candidate classifies the standalone no-change clause as a read constraint, requires the owner-scoped inventory tool for complete collection and setup-relationship questions, then lets Luna write the answer. Targeted regressions cover the exact wording, broad comparison and named detail while retaining a real preceding mutation. Security and Architecture found no remaining concrete blocker after the read-only mutation rejection and strategy-field scope repairs. Root backend: **3423 passed, 3 skipped**. The final isolated API/Celery matrix passed **16/16** and adapters **19/19**, with zero broker orders, live bots, live-trading calls or production connections (artifact SHA-256 `e6a9069a095e4f12d2d6cd07cd4a8e6df1e10326d27f4887ffdb4cb36ab393e8`). Canonical frontend build, typecheck, i18n lint/tests, command/proposal/setup tests and high-severity audit passed (one existing moderate Next.js advisory). Real Luna/Responses development passed **18/18** (artifact SHA-256 `1a642dcb06431c09fd1f91bbc6d60deda2c15b4567d06b68ec7ae9b21294569c`), and regression passed **109/109** (artifact SHA-256 `76a6590d91c32f71a83d530c9f5130e2e9090a20cf23602cb1798863a38c2c2e`), with zero provider, schema, timeout, parse or validation failures. A new independent live verdict remains pending.

Phase: `FULL_COLLECTION_READ_REPAIR_CANDIDATE`. Independent authenticated QA on public SHA `5ecc4216bfb1909efd1b6e1066ec44f3369e9fb8` returned **NOT_ACCEPTED**: two broad ETH-setup questions correctly included all three owner setups, but “Ik heb drie ETH-setups, waaronder [de one without strategy]; noem ze alle drie” narrowed to that named setup and denied the other two. Score boundaries, budget terminology, Paper modes and cadence passed. A newly generated report matched the three setups and Score 2.0 values, but its closing prose still said `Price` in Dutch. A positive automatic Paper decision remained unproven; the matching bot's last assessment preceded that release. The candidate treats a request for the whole collection as a complete owner-scoped inventory read even without a comparison verb, while singular entry/detail follow-ups retain their setup-plus-strategy read. It passes localized indicator display names to the Luna report writer. Root backend suite: **3408 passed, 3 skipped**. Real Luna/Responses development passed **18/18** (artifact SHA-256 `6345800ec6a4c4b9b6808976c6b36b1295562e35d8f7e790cd7d91f6f1dddc02`) and regression **109/109** (artifact SHA-256 `f78df12c019f93a1cf404d58f697679c024d2eb1828944fc45cea1bb9bafdb63`), with zero provider, schema, timeout, parse or validation failures. Named-pair and single-setup detail reads remain scoped when a count merely supplies context. The isolated API/Celery action matrix passed **16/16** and adapters **19/19**, with zero broker orders, live bots, live trading calls or production connections (artifact SHA-256 `c91bf8e6d17ee12bb9be3d27d9cabc0883db2d9b58feebd58d3af4d9910da398`). Frontend build, typecheck, i18n lint/tests, command/proposal/setup tests and high-severity audit passed (one moderate Next.js advisory). Independent QA must test the next deployed SHA before the five-flow release can be accepted.

Phase: `BROAD_SETUP_INVENTORY_REPAIR_CANDIDATE`. Independent authenticated QA on deployed SHA `29eb5632d8034f0896c7b5b0d664fed5ee96c3a9` returned **NOT_ACCEPTED**: a broad comparison of three ETH setups listed only the two with linked strategies and bots, although a direct read of the third setup and the day report both found it. The candidate normalizes such read-only all-setup comparisons to the complete owner-scoped inventory before narrower tool selection, retains unlinked rows and lets FINN compose the answer. It also localizes indicator names in new report prose. Root backend suite: **3399 passed, 3 skipped**; targeted broad-inventory cases cover a narrower bot tool, a timeframe filter, a named emphasis, all-assets wording and counted collections such as “mijn drie ETH-setups”. Real Luna/Responses development passed **18/18** (artifact SHA-256 `d21a1f7d1877167928e28ec020b9df55f2b7e061e06e439a5d6e50241d8b2527`) and regression **109/109** (artifact SHA-256 `d64e2d09ac172b501978ac3a79b766f85fcb8dbc761a0b9f53e80b76c55233a4`), with zero provider, schema, timeout, parse or validation failures. The isolated API/Celery action matrix passed **16/16** and adapter registry **19/19**, with zero broker orders, live bots, live trading calls or production connections (artifact SHA-256 `1f2c961a2b8b0591c62d0803d9b471cffe5ad933b2972fdf832be9e6232b5fab`). Independent QA must retest this candidate on one deployed SHA. A new same-day report and positive automatic Paper decision remain unaccepted; Paper outside saved bounds waits without an order, while missing score data leaves the bot active without a score-dependent purchase.

Phase: `COMPOSITE_RELATIONSHIP_REPORT_PARITY_DEPLOYED_INDEPENDENT_QA_PENDING`. Product [PR #217](https://github.com/gvangalen/antigravity-trading-tool/pull/217) is deployed as public SHA `ffc7b59583e6f99ec537a5e7eae6a43314aa35b0`; candidate CI `38158808646`, main CI `38158953004` and Auto Deploy `38159100196` passed. Backend health and frontend build-info returned HTTP 200 and this same SHA. FINN now receives owner-scoped strategy and Paper-bot relationships with a setup inventory read, while historical day-report setup-match claims are suppressed across report, mobile and cached preview unless Score 2.0 provenance is present. Report labels are asset-neutral and indicator names localized. Root backend tests passed 3393 with 3 skipped; frontend build, typecheck, i18n lint/tests, command/proposal tests and high-severity audit passed (one moderate Next.js advisory). The isolated API/Celery matrix passed 16/16 and adapters 19/19, with zero broker orders, live bots, live calls or production connections (artifact SHA-256 `13c9f5bdc1a08c1db837976ad3f2c466c9f3ae42b75d14459a96fd6497e40dc7`). Real Luna/Responses development passed 18/18 (artifact SHA-256 `9d3e9b4a17d1038ad577726171c283cc4167ca21e3ca451ed806b69186d447cb`) and regression 109/109 (artifact SHA-256 `506d604460a771d88a4a23c603f529affae0d8e68c88217c6f3467dd723aa69b`), both without provider, schema, timeout, parse or validation failures. Security found no concrete owner-scope or execution blocker; Architecture found and Build closed the report-preview metadata bypass with a full-preview regression test. Independent authenticated live QA, a new same-day report and a positive automatic Paper decision remain open. For Paper, a measured score outside saved setup bounds must wait without an order; missing score data keeps the bot active without a score-dependent buy.

Independent QA on public SHA `4ef34f5e1f4312e0ddc6cd3a823211e500b18498` completed a protected auth preflight (run `38156325635`, sanitized artifact SHA-256 `b6abc4cf255d459fdd303bc3ff0d6d0f58cf30afac57df408703d5678d46023a`) and a read-only browser check with an existing ETH test account. The exact named AAPL bot and fresh onboarding were unavailable in that browser session. A targeted ETH bot question returned the saved strategy, setup, manual mode and Paper status correctly; the follow-up explained why Macro 20 was below that bot setup's minimum 30 despite benchmark 33.3. A broader comparison of both ETH setups omitted a visible strategy/bot relationship until the user narrowed the question. The visible older day report also called a setup match active in prose while its side card said no proven match. This is **partial evidence, not full five-flow acceptance**. The next candidate gives the owner-scoped setup inventory its linked strategy and bot names and modes, so a broad comparison has the relationships in the first typed read; the report reader now replaces unverified legacy setup-match prose whenever it suppresses the corresponding old score/card. Report labels and compact score-card wrapping are also corrected. A new report generated by the current release and an automatic positive Paper decision still require independent live evidence.

Phase: `BOT_RELATIONSHIP_READBACK_DEPLOYED_INDEPENDENT_QA_PENDING_FULL_ACCEPTANCE_OPEN`. The independent browser retest on public SHA `72801083bd242d302996d1f6e5dcd96ed8d2d695` returned **NOT_ACCEPTED**. Report unknown-score copy, score parity, visible setup bounds, the post-confirmation strategy reference, Paper safety, DCA cadence and portfolio budget semantics passed the targeted checks. FINN could still not name the linked strategy, setup or manual mode of the named AAPL Paper bot: the model used the owner-scoped saved-bots/portfolio read path, whose rows exposed Paper and budget but omitted those relationship fields. The repair extends that same typed read path with owner-scoped relationship names and mode, keeps at least 20 saved bots in reasoning context, and preserves the bot's stored asset when no strategy is linked. Local backend validation passed **3391**, skipped **3**; frontend build, typecheck, i18n lint/tests, command/proposal tests and high-severity audit passed (one moderate Next.js advisory). The isolated worker-driven action matrix passed **16/16** and adapters **19/19**, with zero broker orders, live bots, live calls or production connections; artifact SHA-256 `4ea13ce85486d6fcc54a8b04b9a016df074f03edc27441785529c0b2d6c84e1c`. Real-provider Luna/Responses selector development passed **18/18**, artifact SHA-256 `3754260e3036833cf9dcf1b592a3927578407c90a71bc7d3a4b1248658774235`; regression passed **109/109**, artifact SHA-256 `4957336be5b32e087555469544204610e742ef5b765f64b0a7371aa9f772956b`, both with zero provider, schema, timeout, parse or validation failures. [PR #215](https://github.com/gvangalen/antigravity-trading-tool/pull/215) candidate CI `38155246134`, main CI `38155409789` and Auto Deploy `38155544569` passed; it merged as `87595d03550a88da4e35b02233a44e192a8fb40a`. Public backend health and frontend build-info both returned HTTP 200 and that SHA. Independent QA is pending. Positive automatic Paper execution, a natural score refresh, Today regeneration and fresh-user onboarding also remain unproven by the prior retest.

Phase: `BOT_REPORT_PARITY_DEPLOYED_INDEPENDENT_QA_PENDING_FULL_ACCEPTANCE_OPEN` for the optional setup score conditions and bot budget acknowledgement. The previous targeted candidate is not full acceptance. Independent QA on public SHA `bed752a854dcf0da869b9710c939930e11bf9dfa` proved one controlled €10 manual Paper buy at a positive match: the Paper position and €10 spend persisted after refresh, while the live portfolio stayed empty and the separate automatic bot decision remained `HOUD VAST`. A subsequent natural missing-score AAPL test found all three benchmark components unknown and no fabricated zero. It could not test score-free fixed DCA because the manual setup editor always proposed and saved six score bounds. Its score-dependent AAPL Paper test stopped at a bot-budget 409 `BOT_RISK_ACK_REQUIRED`, even after the visible risk confirmation, so the missing-score buy guard was not isolated. The budget dialog also exposed the internal acknowledgement field name. The QA verdict remains **NOT_ACCEPTED** for full DCA/Smart-DCA/Paper acceptance. This build batch makes score limits an explicit opt-in in the setup editor, preserves partially configured existing bounds on unrelated edits, passes the confirmed acknowledgement from the budget drawer to the API, and removes the internal field name from the server message. Local root tests passed **3381**, skipped **3**; focused bot and Paper tests passed **68**; frontend build, typecheck, i18n lint/tests, command/proposal/setup tests, and high-severity audit passed (one moderate Next.js advisory). The isolated worker-driven action matrix passed **16/16** and adapters **19/19** with no broker orders, live calls, live bots, or production connections; matrix artifact SHA-256 `e62e1f58aa79331c15cfc4bbe516e524eb77ff24b20068f774f3cc6aff5457cf`. Real-provider Luna/Responses selector development passed **18/18**, artifact SHA-256 `c94dd88baba3fea4ae2b50fd518de3c9731c3678abbc9b92d679d2472145d0f2`; regression passed **109/109** with zero provider, schema, timeout, parse or validation failures, artifact SHA-256 `0e23acdd977525b5c686784df38da5224600375badb81023e0bc73402fa82cac`. [PR #205](https://github.com/gvangalen/antigravity-trading-tool/pull/205) merged as `f6abe16991ca26cf456221cf37039290dbb1c4fb`. Its initial [CI run 38143017124](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38143017124) failed the required tracked frontend export check; the export was regenerated and committed. The final [candidate CI run 38143208556](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38143208556), [main CI run 38143354102](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38143354102) and [Auto Deploy run 38143504984](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38143504984) passed. Public backend health and frontend build-info both returned HTTP 200 and the exact merged SHA on 2026-10-11. Independent authenticated QA of this SHA is summarized below.

Independent authenticated browser QA on the public status SHA `e75396bee6494d8b2762445f16c29de351bf12a6` confirmed that an AAPL fixed DCA can now be saved with score conditions off and remains “Geen scorevoorwaarden” after refresh; its linked bot stayed active in Paper with the Monday cadence despite naturally missing scores, and a €10 manual Paper preview was allowed but not executed. An explicitly bounded AAPL Paper plan accepted a small bot budget after the visible risk confirmation; its €10 buy preview was blocked specifically for incomplete current Market/Macro/Technical scores, with confirmation disabled. No order or live activation occurred. QA found two remaining P2 UI defects: the expected first budget request produced a 409 and console errors before confirmation, and after refresh the expanded bot detail repeatedly stayed on the fixed DCA bot while QA selected the bounded bot. The bounded bot budget was therefore not independently reread in that detail view after refresh. Automatic Monday execution, database-level proof of six null score fields, and automatic positive-match Paper execution remain unproven. [PR #207](https://github.com/gvangalen/antigravity-trading-tool/pull/207) deployed as `89bf15fd1beaefcaf44cd9252dbdd8b29d4c1ed5` after candidate CI 38144582845, main CI 38144719258 and Auto Deploy 38144825925 passed. Backend health and frontend build-info returned HTTP 200 with that SHA. Independent QA verified a budget increase from €100 to €110 on the bounded AAPL Paper bot: the risk prompt appeared before submission, the console showed no 409, and €0/€110 persisted after refresh. The fixed score-free AAPL Paper bot stayed active and allowed a €10 manual preview with missing scores; the bounded bot stayed active but blocked its €10 preview for missing verified scores. QA found that refreshing the bounded bot deep link selected a BTC bot and rewrote the URL. [PR #208](https://github.com/gvangalen/antigravity-trading-tool/pull/208) repaired initial selection; candidate CI 38145146609, main CI 38145247785 and Auto Deploy 38145364484 passed. Public backend and frontend returned HTTP 200 and SHA `08869cd6c24bc642e2a81b0623faaf03c5e0a210`. The same independent QA agent then confirmed bot 75 remained selected through hard refresh with its strategy and €0/€110 budget, and bot 76 remained selected through hard refresh with its score-free Monday strategy and €0/€100 budget; no BTC substitution recurred. One transient cluster of 401 Token refresh failed console messages occurred during a switch, without a repeated error after refresh; its cause is not established. No order or live activation occurred in either run. Automatic calendar execution, automatic positive-match Paper execution, and the measured-outside-bounds path remain unproven in production; the full five-flow verdict stays **NOT_ACCEPTED**.


Independent QA on public SHA `2d6678da5f7089501e67be972efb0491f37f0f3e` completed a broader existing-account browser matrix. A new daily report rendered without 502; Analyse, My Plan, FINN and the report agreed that AAPL scores are missing, not zero. Stored setup limits were visible and a temporary edit persisted; the linked Paper bot marked its old decision stale. With measured BTC Market 20 and a temporary minimum of 21, a €10 Paper preview was blocked with confirmation disabled; QA restored the minimum of 20 afterward. An AAPL bot with incomplete scores also blocked a buy preview, while a score-free fixed DCA retained its Monday cadence after changing the chart timeframe to 4H and allowed a manual Paper preview. Portfolio and FINN kept bot limits distinct from cash. QA did not place an order. The automatic calendar execution, positive complete-score automatic Paper execution, FINN Today regeneration after an edit, and a fresh registration/onboarding/relogin journey remain unproven. QA also found that the report said one confirmed match in its prose while its setup card said no matching setups, and a saved BTC FINN Today briefing appeared on an AAPL workspace without a clear asset label. The current local repair preserves Score 2.0 semantics on report match rows, scopes the prose count to all followed assets, and labels the Today card with its briefing asset. Focused backend tests passed 36/36; root backend tests passed 3382 with 3 skipped. Frontend build, typecheck, i18n lint/tests, command/proposal/setup tests, and high-severity audit passed (one moderate Next.js advisory). The isolated FastAPI/Celery/PostgreSQL/Redis/Responses action matrix passed 16/16 and adapters 19/19 with zero broker orders, live bots, live calls or production connections; artifact SHA-256 `c2eb35ebea2e435486aca91f249dfc5071c27f8e0e0536dcbaa3a2d5f3b782af`. Real-provider Luna/Responses selector development passed 18/18, artifact SHA-256 `b24623cb3103e36a3bf9174693651b7f0610436c631e5bc85bd6eaddbc46e0a7`; regression passed 109/109, artifact SHA-256 `3b476dc7caaa6cfe6aebf74ab777f82cf927bca577ecc78b3d130d81bc63cc34`, with zero provider, schema, timeout, parse or validation failures. [PR #210](https://github.com/gvangalen/antigravity-trading-tool/pull/210) merged as `012940d2a87952248f0a9ede4c0f348dcc5c5681`; candidate CI 38147688897, main CI 38147836003 and Auto Deploy 38147966531 passed. Backend health and frontend build-info returned HTTP 200 with the same SHA. Independent QA made a new report without 502; with BTC Market score temporarily unavailable, both prose and card showed no confirmed current setupmatch. The positive-match report card path was not observable. On the AAPL workspace, the stored briefing now showed “Vandaag met Finn · BTC”; NL/EN/DE UI labels switched, although the persisted briefing body stayed in its original Dutch. Full five-flow acceptance remains open.


The current local score-refresh repair addresses a measured scheduling gap: configured source measurements refresh every five minutes, while the independent score rebuild normally runs every fifteen minutes. A newly observed source moment makes the previous score temporarily unverified until rebuild. After the committed indicator refresh, the market task now enqueues one owner-scoped Score 2.0 rebuild per successfully rehydrated user on the existing scoring route; all rebuild paths share a per-owner transaction lock so an older calculation cannot overwrite newer source evidence. The periodic rebuild remains the fallback if queueing fails. A forced-overlap regression and a local PostgreSQL transaction-lock contention check passed; root backend tests passed 3385 with 3 skipped. The isolated local worker-driven action matrix passed 16/16, adapters 19/19, with zero broker orders, live bots, live trading calls or production connections; artifact SHA-256 `90ed6075409a9dbc81a8fd044c9918f1f2460ba64295081e6f1d9d9834fd84c9`. The real-provider Luna/Responses selector development set passed 18/18 with zero provider, schema, timeout, parse or validation failures; artifact SHA-256 `19ff547bb1554929f0bbe9f906ec8d9ba85663a349d23f65c20eceb2492bc212`. Real-provider regression passed 109/109 with the same zero failure categories; artifact SHA-256 `ea252554c38fbdd8c6197ab3864bd1b1b6e3aa711a4128a95ec4369503817118`. [PR #211](https://github.com/gvangalen/antigravity-trading-tool/pull/211) merged as `79fb191a02d46cc67412a4343b4873d00f782766`. Candidate CI 38149543754, main CI 38149699185 and Auto Deploy 38149831610 passed. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` returned HTTP 200 and the same SHA. The status-only release marker that contains this evidence must pass its own CI and Auto Deploy before independent QA uses the final public SHA. Independent live retesting is pending; this repair does not itself prove a positive automatic Paper execution or eliminate genuine missing provider data.

Independent QA on final public SHA `257fe08fd08341f1d49f17c06bccb6ae7c1c9b7b` (status [PR #212](https://github.com/gvangalen/antigravity-trading-tool/pull/212); candidate CI 38149920039, main CI 38150040100 and Auto Deploy 38150160256 passed) returned partial, not full acceptance. Analyse, My Plan, FINN and a new daily report agreed on BTC Market 30, Macro 20, Technical 50, benchmark 33.3 and a 73% match for BTC 4H Swing QA; AAPL remained unknown. The stored score limits and DCA Monday cadence survived edits and refresh, and Portfolio/FINN separated €1,210 of bot limits from verified cash. Missing AAPL scores left its Paper bot active but blocked a €10 buy preview; a measured BTC Market 30 below a temporary setup minimum 31 likewise blocked confirmation. QA restored both temporary setup changes and placed no order. QA found two P2 defects: AAPL rows with unknown match scores rendered a bare percent sign in the report comparison, and FINN could not confirm the named AAPL bot's linked strategy and manual mode although the UI showed them. The deployed repair renders unknown comparison scores explicitly and passes the owner-scoped bot's joined strategy/setup names and mode through the typed read evidence. Natural source-refresh-to-score timing, automatic positive Paper execution, fresh onboarding/relogin and causal FINN Today regeneration after an edit remain unproven.

Local validation for the report/bot-evidence repair: root backend **3389 passed, 3 skipped**; the owner-scoped bot join, no-score report and bounded verifier-retry cases passed. Frontend build, typecheck, i18n lint/tests, command/proposal tests and high-severity audit passed (one moderate Next.js advisory). The final restarted isolated FastAPI/Celery action matrix passed **16/16** and adapters **19/19**, with zero broker orders, live bots, live trading calls or production connections; SHA-256 `a36c4faf7fc34d9297d8681d675b8a82b79fe2ed406fd374a5b3a2d57f16d132`. The real-provider Luna/Responses development set passed **18/18** with zero provider, schema, timeout, parse or validation failures; SHA-256 `1544f9a720ae1a224002cdf782c530d158c939b5b3a1c9ef498f94a1edbf54e9`. Regression passed **109/109** with the same zero failure categories; SHA-256 `2841b79cb7f7a79bf65f28453002678f9f69207a7810aae7344540355e95ddfa`. [PR #213](https://github.com/gvangalen/antigravity-trading-tool/pull/213) merged as `9eeba4d3776fe55146b102edf624f900aaaaf760`; candidate CI 38152882196, main CI 38153030705 and Auto Deploy 38153164791 passed. Public backend health and frontend build-info both returned HTTP 200 and that exact SHA on 2026-10-11. Independent authenticated QA remains pending. A null score now has no green best-match claim; the named bot relationship is resolved through the owner-scoped repository read and typed tool result. These local checks do not prove the live conversation or automatic Paper execution.

The first matrix rerun after extending owner predicates to all bot/portfolio joins yielded **15/16**: the `update_strategy` confirmation and saved-record read succeeded, but the follow-up answer was marked unavailable after the semantic verifier received `incomplete_structured_response`. The draft correctly described the saved €120 and unchanged BTC/4H/entry/stop/target values; the provider failure, not a failed update, caused the red gate. A bounded single retry for that verifier error was implemented without weakening a negative safety verdict. The final action matrix passed **16/16** on this change; the earlier 15/16 run remains recorded as a failed intermediate gate.

Historical phase: `TARGETED_QA_PASSED_FULL_ACCEPTANCE_OPEN` for the manual Paper distinction copy. Independent QA returned `NOT_ACCEPTED` for the preceding manual Paper match candidate `a990498bb75aa8db40d0473ad3b628ebed841b2d`. The earlier five-flow candidate also returned `NOT_ACCEPTED` on `522556d7d33aad6f4e383a0633ce7dba6462aa81`. Product repair [PR #196](https://github.com/gvangalen/antigravity-trading-tool/pull/196) was merged as `5ad1566dab333b245681e7c7729a3fedfdfdc1d1`; status-only [PR #197](https://github.com/gvangalen/antigravity-trading-tool/pull/197) deployed as the QA SHA. Candidate [CI run 38133437274](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38133437274), main [CI run 38133985302](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38133985302), status [CI run 38134324405](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38134324405), and [Auto Deploy runs 38134094606](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38134094606) and [38134435821](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38134435821) passed. Public backend health and frontend build-info each returned HTTP 200 and the exact QA SHA on 2026-10-11.

Scope: regenerate an already stored FINN Today briefing after a plan edit; mark a bot's previous decision stale when its owner-scoped setup revision or linked strategy changes; suppress that decision's old action and guardrail display until reevaluation; and reject execution of an old or revisionless buy decision on the server, including Paper and live paths. Keep exits available. Present zero optional order limits as unlimited, distinguish a bot decision hold from a manual Paper order check, and label the report's empty summary as an absent **active** setup match. The user's Paper rule remains: measured scores outside saved setup bounds wait without a buy; missing score data keeps the bot active without a score-dependent buy, while a score-free fixed calendar DCA can follow its schedule.

Measured local evidence on the final product source: root `pytest -q --disable-warnings` **3374 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command tests, and high-severity dependency audit passed (one moderate Next.js advisory). After restarting the local FastAPI/Celery/PostgreSQL/Redis runtime on the final source, the worker-driven Responses action matrix passed **16/16** and adapter tests **19/19**, with zero broker orders, live bots, live-trading calls, or production connections; matrix artifact SHA-256 `888eab12d4bd70664a1e5ffcea069899203eed5b1622aaf6f943c17127971da1`. Real-provider Luna/Responses selector development passed **18/18** and regression **109/109**, with zero provider, schema, timeout, parse, or validation failures; regression artifact SHA-256 `3cdd319e1135b8b743325d4d550686ddf6ba5dca76f97087b9be695bd0706b79`. A local PostgreSQL transaction confirmed that a matching saved setup revision permits the buy check and a revised setup rejects it; the transaction rolled back and made no order. Security independently reviewed the server gate. These are Build and CI results, not a production Paper execution or independent QA verdict.

Independent QA must replay the complete five-flow scope on one explicit public SHA. In particular, edit saved score limits after a negative Paper decision and verify the old decision is no longer current, FINN Today regenerates, and a fresh Paper decision uses the new limits; verify measured outside-bound, missing/stale-score, and positive-match behavior; compare Analyse, Mijn Plan, FINN, Today, report, and bot facts; and check the bot budget and manual Paper wording. No live order is authorized.

QA on `522556d7d33aad6f4e383a0633ce7dba6462aa81` observed that the stale bot decision, unlimited zero-valued optional limits, report active-match summary, FINN score/source explanation, setup versus strategy timeframe, and botbudget versus cash are corrected. FINN Today showed a stored personal briefing after refresh, but the browser did not expose its generation revision. The blocking defect is the manual Paper order path: with an absent Market score and a stale bot decision, the form said an order was ready for checking and its preview offered confirmation without showing the missing setup-match evidence. QA cancelled the preview; no order was placed. A positive fully scored match and controlled Paper execution were not testable with that account's current data. The new repair branch `codex/finn-paper-manual-match-gate` makes the manual Paper preview and server write use the owner-scoped Score 2.0 setup match, with no score requirement for an unbounded fixed DCA. [PR #198](https://github.com/gvangalen/antigravity-trading-tool/pull/198) deployed the repair as `db406da093aa33f680e848f00a0c4c957cac0553`. Candidate [CI run 38136655984](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38136655984), main [CI run 38136790399](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38136790399), and [Auto Deploy run 38136889557](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38136889557) passed. Public backend health and frontend build-info returned the exact product SHA on 2026-10-11. Independent authenticated QA of this SHA is still pending.

Measured Build evidence for that branch: root `pytest -q --disable-warnings` **3379 passed, 3 skipped**; frontend typecheck, i18n lint/tests, command tests, build and high-severity dependency audit passed (one moderate Next.js advisory). Focused Paper preview/create/preflight tests cover missing scores, measured non-match, positive match, unbounded DCA, sell and missing owner-scoped setup. Security's read-only review found no concrete bypass; it identified a Paper-only concurrent-edit window between match read and order insert, without evidence of a practical unauthorized bypass. The first local action matrix was **15/16** because Luna unexpectedly completed all fields on an intentionally incomplete strategy request; its artifact SHA-256 is `6073c2cb0954695867d7b2897c4eb39f21bd94a7f5e73d4516d79a757290a11f`. The full rerun passed **16/16** plus **19/19** adapter tests, with zero broker orders, live bots, live-trading calls or production connections; artifact SHA-256 `a5792961aafb4193d19ccac468cc0ced8817004851c05c4fa70f56e32dae7dea`. Real-provider Luna/Responses selector development passed **18/18**, SHA-256 `d93b90fbd64c9f1ef09e496510e53ddbb02c4633fd858e28bde9e7f849fda92b`. The first selector regression was **108/109** due a provider error on an unrelated Dogecoin watchlist case, SHA-256 `f88ad7244ea0d54607bb78ab63295064536938154d5a2adb3bbb7a3b25a945ba`; the full rerun passed **109/109** with zero provider, schema, timeout, parse and validation failures, SHA-256 `cbc0a6df706aaedf460de0e75f963bc9219c31b7154c90b6a3fde8fdb20f1c0c`. The first red runs remain red evidence rather than being erased by the reruns. These local results do not establish live QA acceptance or positive Paper execution.

Independent authenticated browser QA on `a990498bb75aa8db40d0473ad3b628ebed841b2d` returned **NOT_ACCEPTED**. The server blocked the measured outside-bound Paper buy, but the frontend treated its structured HTTP-200 refusal (`ok: false`, `PAPER_SETUP_MATCH_REQUIRED`) as a generic API error. The modal lost the requested asset and buy direction and showed “Verkoop”. A freshly generated report showed verified Market/Macro/Technical scores 30/20/50 and a complete benchmark, but its setup text falsely said the benchmark was incomplete; Mijn Plan correctly showed a 67% non-match because Macro 20 was below minimum 30. Positive-match preview and FINN/Today facts were otherwise coherent. Missing-score behavior, a new persisted bot decision, score-free DCA and controlled Paper execution were not proven in that browser run; no order was confirmed.

Current product repair [PR #200](https://github.com/gvangalen/antigravity-trading-tool/pull/200), merged as `25b1d90af89f4b0544017fea2b182273f2b7c697`, preserves the typed Paper refusal in the frontend, retaining its reason, asset and direction. The server message now uses the canonical match components to explain the verified boundary. The report renders its setup-match sentence from the same canonical match status: incomplete benchmark and measured non-match are different outcomes. Focused tests cover the 30/20/50 outside-bound report and the Paper-preview boundary. Root backend tests passed **3381**, skipped **3**. Frontend typecheck, i18n lint/tests, command/proposal/setup tests, build and high-severity audit passed (one moderate Next.js advisory). The isolated worker-driven action matrix passed **16/16** with zero broker orders, live bots, live-trading calls or production connections; artifact SHA-256 `06097d818111c40f7239c4c0a677687c07d44e41b0d84df7cc268f67545327ae`. Adapter tests passed **19/19**. Real-provider Luna/Responses selector development passed **18/18**, artifact SHA-256 `1646d54d35f5385da42ebae927b77254dde8b8acb4f93d33aafd9bd40fd9fec9`; regression passed **109/109**, artifact SHA-256 `c02df499b18018a0e3b57be85f6bd99fdac3c7a1a9d31c1a2e274f96881d7d1e`. Both had zero provider, schema, timeout, parse or validation failures. Candidate [CI run 38138884770](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38138884770), main [CI run 38139028020](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38139028020), and [Auto Deploy run 38139157653](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38139157653) passed. Public backend health returned HTTP 200 and frontend build-info was reachable; both reported `25b1d90af89f4b0544017fea2b182273f2b7c697` on 2026-10-11. These are Build and deployment results, not a new live QA verdict or a Paper execution.

Independent authenticated browser QA on `ebda462cd7cf47e0ef4ccec36a05d18b8bf12079` returned **NOT_ACCEPTED** for the full five-flow matrix but confirmed both targeted P1 fixes after a fresh frontend load: with Market/Macro/Technical 30/20/50 and Macro minimum 30, Mijn Plan showed a negative match, the Paper-buy preview retained BTC/Koop/€100 and explained “Macro 20 ligt onder minimum 30” with confirmation disabled, and a newly generated report no longer called the benchmark incomplete. After restoring Macro minimum 20, Mijn Plan showed a 73% positive match and a separate handmatige Paper-buy preview was available; QA did not confirm it. FINN Today, FINN chat, bot budget terminology and stale automatic-decision marking were coherent. The first pre-reload preview used an old browser bundle; the fresh release did not reproduce its API error. Score-free DCA, missing/stale score, a new persisted bot decision and controlled Paper execution remain unproven in that production fixture. QA identified a P2 clarity issue: the bot card says the automatic decision needs a new evaluation while offering a manual Trade action, without immediately explaining that manual Paper preview and confirmation independently recheck current setup conditions. The NL/EN/DE explanatory-copy follow-up was merged in [PR #202](https://github.com/gvangalen/antigravity-trading-tool/pull/202) as `80489b340b8dee99797cdda44221da0f3916971d`; server gates and provider code are unchanged. Frontend typecheck, i18n lint/tests, command tests, build and high-severity audit passed (one moderate Next.js advisory). Candidate [CI run 38140078957](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38140078957), main [CI run 38140224197](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38140224197), and [Auto Deploy run 38140362248](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38140362248) passed. Public backend health and frontend build-info both returned HTTP 200 with `80489b340b8dee99797cdda44221da0f3916971d` on 2026-10-11. Targeted independent QA of this copy is pending; the broader five-flow matrix remains not accepted until the missing/stale, score-free DCA and Paper-execution evidence is available.

Independent targeted browser QA on `0a561e8503a3e2ca8a8897084f5a6daa17d258c7` **passed** the new bot copy. After a fresh page load, “Nieuwe beoordeling nodig” explicitly marked the old automatic decision unusable and explained the separate manual Paper setup check and confirmation. With verified Macro 20 below minimum 30, the €100 buy preview showed the boundary and disabled confirmation; after restoring the QA minimum to 20, only a separate confirmable Paper/manual preview appeared. QA cancelled it. No Paper order or live trade was executed. The prior full five-flow **NOT_ACCEPTED** verdict remains: score-free DCA, missing/stale scores and a persisted Paper execution are not proven by this fixture.

## Previous Five-Flow Release

Phase: `NOT_ACCEPTED` for the full five-flow and Paper objective after independent authenticated browser QA on `50a4d31f4daeb14decc28e42d7b8cf7ff1b70072`. [PR #193](https://github.com/gvangalen/antigravity-trading-tool/pull/193) was merged as product SHA `223c733881ac0548ec75333fed6caf2f27e22fd2`; status-only [PR #194](https://github.com/gvangalen/antigravity-trading-tool/pull/194) deployed as `50a4d31f4daeb14decc28e42d7b8cf7ff1b70072`. Candidate [CI run 38130492050](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38130492050), main [CI run 38130624753](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38130624753), and [Auto Deploy run 38130740778](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38130740778) passed. Status [CI run 38130944071](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38130944071) and [Auto Deploy run 38131060765](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38131060765) passed. Public backend health and frontend build-info both returned HTTP 200 and the QA SHA on 2026-10-11. A later status-only commit changes public SHA without changing product code; QA evidence remains bound to its tested SHA.

Scope: preserve shared verified report facts; reuse a recent daily report without waiting for a new signature; stop silently inserting setup score limits; show and confirm suggested limits in onboarding and display the actual limits or their absence on FINN proposal cards; clarify bot budgets as limits; return separate setup and strategy timeframes plus the saved DCA purchase schedule; and hold buys when measured Score 2.0 components fall outside an owner's saved setup limits. Missing scores leave a score-free fixed calendar DCA active; a DCA with saved score limits holds until those limits can be measured. Sell/exit decisions remain available. This implements the user's 2026-10-11 clarification for the Paper acceptance matrix.

Measured local evidence: backend `pytest -q` **3363 passed, 3 skipped** on commit `bffa12d1a`; frontend build, typecheck, i18n lint/tests, command tests and high-severity audit passed before the final backend-only gate correction (one moderate Next.js advisory). The isolated local FastAPI/Celery/PostgreSQL/Redis/Responses action matrix was rerun after the correction and passed **16/16**, with no live bot, broker order or production connection (artifact SHA-256 `df076bd9309a258572f3b4f489fec9f1db5fecd87b27641e64d63ed95230e388`); action-adapter tests passed **19/19**. Real-provider Luna/Responses selector development was rerun and passed **18/18**, artifact SHA-256 `459ddcabf57c7478efe9a578eabb005a8edaacbaf15ce8323a4c5b10fa8a9876`; regression passed **109/109**, artifact SHA-256 `624e76421c91f5c6426b3cc0d2ef59b9fe8678cc2dc797e1ceecae8c3ed791ac`. Both runs reported zero provider, schema, timeout, parse and validation failures. After Security found a fixed-DCA buy-gate reversal, the final code was corrected and its real match outcomes and order check passed 32 focused tests. Security independently rechecked score-free fixed DCA, bounded fixed DCA with missing data, outside-condition holds and unaffected sell decisions, with no remaining concrete blocker. A local Score 2.0 chain test covers positive match, measured non-match, missing and stale source data through the Paper worker; it does not prove a production Paper execution.

Independent QA used a newly registered account via the visible UI. Profile, BTC indicator setup, saved setup and strategy, and Paper bot persisted across refresh and relogin. Analyse and FINN agreed on Market 30, Macro 20, Technical 50 and benchmark 33.3. Setup bounds were visible before save. A new daily report rendered without a visible 502 and used the same three component scores. Bot budget remained a limit rather than cash. The measured Macro 20 below a saved minimum of 30 led to `HOUD VAST` in bot detail, with no order placed. These paths passed only for the observed state.

The full objective remains open: after changing the Macro minimum to 20, Mijn Plan showed a positive match but the bot continued to display the earlier negative decision after refresh, without a stale-decision marker or proven reevaluation. FINN Today generated a personal first briefing but after that plan edit settled on "personal briefing unavailable" even after relogin. Bot diagnostics displayed a blocked system and zero day/order limits while the manual Paper form called a €100 draft "ready to place"; QA did not submit it, so server acceptance is unknown. The report summary showed no setup value while its detail contained a match score, and Reflectie still exposed English text and raw indicator codes. One FINN bot question missed current scores available to a direct follow-up. A complete positive Paper decision and execution, missing/stale-score cases, and manual-order server enforcement remain unproved. No live bot or broker order was used. A new repair candidate must resolve the three high-priority state contradictions and repeat the full live matrix.

## Previous Release (DCA to Paper follow-up)

| Field | Value |
| --- | --- |
| Phase | `ACCEPTED` for the targeted, unchanged 12-case DCA→Paper regression matrix on live SHA `0066066d5417bff6c0c49bd42ed5ee21b7ba9d5e`. This is not broader Score 2.0 or coach acceptance. |
| Goal | Make a directly requested, same-conversation Paper-bot proposal after confirmed DCA setup/linked strategy when the server has independently verified the exact owner-scoped parent pair. Keep clarification for unsupported or conflicting language and confirmation for all writes. Broader Score 2.0 → setup match → Paper and chat/Today/report parity remain open. |
| Candidate | [PR #190](https://github.com/gvangalen/antigravity-trading-tool/pull/190), implementation commit `0e17d2f19`, frontend export commit `2a475cdd7`, merged as `5adcae1e681d7d1513fbac03ffedf19b69578913`. Status-only [PR #191](https://github.com/gvangalen/antigravity-trading-tool/pull/191) deployed as `0066066d5417bff6c0c49bd42ed5ee21b7ba9d5e`. QA tested this latter live SHA. A later status-only update can change the public SHA without changing product code. |
| Production identity | On 2026-10-11, [candidate CI run 38126357730](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38126357730), [main CI run 38126487262](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38126487262), [status CI run 38126813372](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38126813372), [Auto Deploy run 38126587415](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38126587415), and [status Auto Deploy run 38126922011](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38126922011) passed. Before QA, public backend health and frontend build-info both returned HTTP 200 and SHA `0066066d5417bff6c0c49bd42ed5ee21b7ba9d5e`. |
| Last updated | 2026-10-11. |

Independent protected [QA run 38127031974](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38127031974) returned **ACCEPTED** for its targeted 12-case DCA→Paper matrix: 12/12 executed and passed, all release/auth preflight identities matched, and polling/SSE matched in all 12 cases. A direct Paper-bot proposal used the verified preceding strategy context. No bot existed before confirmation; after safe execution exactly one owner-scoped, non-live Paper-bot existed. All three writes required confirmation, and replay returned `already_executed` without duplicate database effects. No broker order, live-trading call, or live-bot activation occurred. Artifact `finn-production-qa-38127031974-1.json` SHA-256 `4d95d966fb645f15bb2ab6873ab366d4406eac6b9f3fc5322b4dcc26c40c9396`. The sanitized projection does not expose the parent and child strategy IDs side by side, so exact ID equality cannot be independently recomputed from it. The matrix has no separate ambiguous, hypothetical or third-target case, and it does not establish chat/Today/report parity, a positive Score 2.0 setup match, or a score-driven Paper decision. QA also noted runner-observability defects: the trace retains `unsupported_utterance` after later semantic admission, and its summary says `product_calls_executed=0` despite executed cases. These are follow-up diagnostics, not evidence of a failed product case in this matrix.

Independent protected [QA run 38120983081](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38120983081) on `2065668a572d48b8d7c404f8ff440fb16c0ea5ea` returned **NOT_ACCEPTED**: 12 planned, 8 executed, 7 passed, 1 product failure, 4 safely skipped. A confirmed owner-scoped DCA setup and linked strategy were saved, but the immediate bot follow-up selected `READ` with no operation or proposal. The published trace did not include the immediate-bot guard reason, so `accepted` versus `unsupported_utterance` is unknown. Zero broker orders, live calls or live activations; polling/SSE matched. Artifact SHA-256 `4f6aadab10f65b3cff1875966fa963caf1b38c0332c721e8402ee35c196ff37e`. The QA fixture and prompt remain QA-owned.

Independent protected [QA run 38124599126](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38124599126) on `b57d5fd368863b78bb266aed54819e7cd16684dc` returned **NOT_ACCEPTED**: 12 planned, 8 executed, 7 passed, 1 product failure, 4 dependency skips. The confirmed DCA setup and linked strategy were saved. FINN chose `create_bot` for `confirmed_previous_plan`, but the server's phrase-level guard returned `unsupported_utterance`, leaving `strategy_id` unbound and no Paper proposal. The sanitized artifact SHA-256 is `cdf14a20f5183ad706a56c0097b3ea175db1fdd449ec6278da3c9a033c56cd7b`. The protected prompt and fixture remain QA-owned.

The local repair for this failure replaces the phrase-level block on an otherwise verified immediate bot follow-up with two typed Luna/Responses checks: the first requires a clear Paper-bot proposal for the just-confirmed plan; the second requires the requested object domain to be `bot`. The server still verifies the immediate action, owner, setup/strategy IDs, asset, competing targets, and unsupported trading pairs. A missing or unclear check never binds the strategy automatically. The frontend enables confirmation only after the owner-scoped proposal target ID agrees with the draft ID and resolves to a named owner strategy. A separate confirmation remains required for any write. Local backend tests passed **3348**, skipped **3** (log SHA-256 `520d6c6b3ed07c14a89ecac88dd94deecd4296c44bb82692feba709508147e14`). The isolated worker-driven action matrix passed **16/16** with no live bot, broker order, live-trading call, or production connection (artifact SHA-256 `8036999c707f9d9092bb33d6329656734ee3380120ebb04a5bb05d95fd431619`). A synthetic same-conversation DCA confirmation followed by a naturally worded Paper-bot request produced a proposal for exactly the confirmed strategy and no bot before confirmation (artifact SHA-256 `436d3d5b4eb245e19c9dc2d797c810e32f0a7e58c331a7c1d0c76355903f5a7a`). Real Luna selector development and regression passed **18/18** and **109/109**, with no provider or validation failures (artifact SHA-256 `80abdb5ab3b1867779be5679bdd25229a661cf4ccf81e8fe631b441758e46999` and `b6040217eeb120c6b922efc414658a331d62ae5feb1a3d3c0bf4ff36136fafe1`). Frontend build, typecheck, i18n, command, proposal-card tests and high-severity audit passed; the audit reported a moderate Next.js advisory. Read-only Security and Architecture reviews found no unauthorized write or cross-owner binding and no remaining concrete architecture blocker. Their remaining risk is an incorrect confirmable Paper proposal if both semantic checks misread a read-only request; it cannot save without a separate user confirmation. The repair is deployed and accepted for the targeted 12-case matrix described above.

The new local candidate dispatches a registry `create_bot` proposal directly only when the server has already accepted the bounded current-turn request and verified the immediately preceding owner-scoped setup/strategy action. It extracts explicitly supplied bot name and budget, leaves missing fields for guided clarification, and retains confirmation before any write. The request grammar accepts harmless word-order and politeness variants while rejecting unrecognized residue. A proposed semantic model-only fallback was removed after Security reproduced confirmable cards for a third-party portfolio and an illustration request. The terminal trace now exposes only a clamped guard-reason enum, including on READ outcomes, so QA can locate the next failure layer without seeing private text.

Final local backend `pytest -q`: **3340 passed, 3 skipped** (log SHA-256 `534de38400bd15e4acb61068050ba64c9b92333b8acc6e9042f91f9e6ad7fa99`). The isolated prefork FastAPI/Celery/Responses action matrix was rerun after the final guard change and passed **16/16**, with zero broker orders, live bots, trading calls or production connections (artifact SHA-256 `be8689d50bab664cac3f46e9ac4cbb97d626f526cda9d0badc349b0a3941e990`). Seven public same-conversation bot follow-ups after successful local DCA confirmations each produced a proposal for the confirmed strategy without creating a bot; one additional case stopped at DCA creation and cannot count as a follow-up pass (artifact SHA-256 `0e84b8b39ba0e7ba31fa4d39456522e1259420b14f6a24f2aa9fbe4ef5c38327`). Real Luna/Responses selector development and regression passed **18/18** and **109/109** after the final guard change, with zero provider, schema, parse, validation or timeout failures (artifact SHA-256 `bd205b6ce4d05c97bb29f1f359537ab86a664c27f0536fa9de26615538d18c9b` and `1ba042921e9a65d52829e267f3409ca0d0ff2eab51b3ac56b17a08cb6afd7ee5`). Frontend typecheck, build, i18n lint/tests, command/proposal tests and `audit:high` passed; the audit reported only a moderate Next.js advisory. Security's final read-only review found no concrete P1 bypass after a declarative bot example was blocked. A broader nonsealed sequential-action diagnostic remained red at **7/10**: strategy-update selection and strategy/setup deletion failed; create/update Paper-bot passed. This is not counted as a green gate or as evidence for the protected direct-DCA follow-up (artifact SHA-256 `3f4f84c05e40110a2ffcf5a99f9d44185f7d968c75bfdf7fd13d44d791b5c871`). Independent QA is still required, and the current production release remains `NOT_ACCEPTED`.

Independent protected [QA run 38118793637](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38118793637) on `f86523d6d120eced8a7711c7166b17984828d983` returned **NOT_ACCEPTED**: 8 of 12 cases executed, 7 passed, 1 product failure, and 4 safely skipped. The model selected `create_bot` with `confirmed_previous_plan` after a confirmed owner-scoped DCA setup and strategy, but the server guard returned `unsupported_utterance`; no `strategy_id` or bot proposal resulted. The direct action was safe and idempotent, six read cases and polling/SSE parity passed, and there were zero broker orders or live activations. The QA prompt and protected fixture remain QA-owned.

The new candidate retains the verified immediate action, owner, setup, strategy, asset, competing-name and confirmation checks. It recognizes reordered natural bot requests only when every remaining word is accounted for by bounded request grammar; unknown owner, target or read-only clauses require clarification. Flexible requests with a bot name require quotes, and the older bounded route accepts at most two title-cased unquoted name words. Security's final read-only review found no concrete P1 bypass after adversarial account and read-only cases were added. Root backend tests passed **3333**, skipped **3** (log SHA-256 `125cb787258e99211a0d084cbeccead4b3fe7df94485acce7cfa52507d7859cb`); focused bot-reference tests passed **98/98** and adapter registry **19/19**. The isolated prefork FastAPI/Celery/Responses action matrix passed **16/16**, with zero broker orders, live bots, trading calls or production connections (artifact SHA-256 `11f7fced0b5fe050d12cab1532a9bd2bd999e5a113fdb71a8b6862b38502e17d`). A separate synthetic real-provider DCA confirmation → same-conversation Paper proposal bound exactly the confirmed strategy, with zero bots before bot confirmation (artifact SHA-256 `1f2c179bd211eb2aa3cb3b83b05ab309546efe7f199f37c6c76ce320258b091c`). Luna/Responses selector development passed **18/18** and regression **109/109**, with zero provider, schema, parse, validation or timeout failures (artifact SHA-256 `75bba9029d5fbfdd4811809c97af9c3b5e5f2274d5ae000ffb5839340ba6be54` and `37c4782cdea0ca97441ebffadce5dad31b424d65ed6d008a43e1a88b48fc4e50`). Frontend build, typecheck, i18n lint/tests, command, proposal and setup tests and `audit:high` passed; audit reported one moderate Next.js advisory. An additional broad nonsealed parity diagnostic remained red at 14/16 actions and 8/9 lineage, with unrelated read-route selection misses; it is not counted as a green release gate and remains open separately (artifact SHA-256 `9feb4b9bfec5fede6ab23d771d0f90ec85947cc09ec45aee34296ee9eb67b4dd`). These local checks do not replace authenticated live QA.

The candidate repairs the direct Paper-bot continuation after a confirmed DCA setup and strategy. Eight public, synthetic same-conversation wordings passed through local FastAPI, Celery and real Luna/Responses: **8/8** yielded a proposal bound to the just-confirmed strategy and **0** created a bot before confirmation (artifact SHA-256 `1a20d083c75b892bb48602761175cd2da8aa43306db91f3c045f57e0ab3e44ac`). The bounded server reference guard still rejects negated requests, requests for another person's plan and competing targets; rejection clears stale strategy context. Security's independent code review found no concrete new bypass, while noting this is not live evidence. Root backend tests passed **3319**, skipped **3** (log SHA-256 `578904de5c9618a531c2069faf8534ae9d287b85ccd27aa1258f848264f3e20c`). The worker-driven action matrix passed **16/16** (artifact SHA-256 `52b72bd838b16e094990a7f2c049b90588ec7aade00fdfd89e9c89194c1ea848`) and adapter registry **19/19**. Real-provider Luna/Responses selector development passed **18/18** (artifact SHA-256 `e1e30e1da36c867a86e10c6b88402456cb92340a1b6b937d42c9ad1c3093e968`) and regression **109/109** (artifact SHA-256 `2559e40d3dde5b0cdba7a09e8d220784f2059ba44ba4d1cce890221da0ea4d18`), with zero provider, schema, parse, validation or timeout failures. Frontend build, typecheck, i18n lint/tests, command/proposal tests and `audit:high` passed; the audit reported one moderate Next.js advisory. Build did not access the protected QA fixture or sealed holdout. The earlier `fixture_binding_invalid` was resolved by Operations and later protected preflights passed; the latest independent product matrix remains `NOT_ACCEPTED` for the Paper-bot continuation. Full positive Score 2.0 → setupmatch → Paper and chat/Today/report parity still require independent live QA.

The new candidate keeps the immediate confirmed setup/strategy pair unresolved when the entire bot follow-up cannot be established by the server guard. A separate Luna/Responses semantic verdict may distinguish a read-only or different-target request, but it cannot authorize a binding or supply an ID. FINN asks for the exact stored strategy name, resolves that name again within the owner account, and only then offers a confirmable Paper-bot proposal. A local two-turn API/Celery/real-provider probe passed: first turn requested the choice without a proposal; second turn used the exact strategy and returned the correct proposal, with no bot or execution before confirmation and polling/SSE parity (artifact SHA-256 `bbd9a5121e7d822c451c07bfc64842d7c98dd94a76f0e272fe34c5e1009b6a91`). The full backend suite passed **3302**, skipped **3** (log SHA-256 `c6f528bdecbf71c88a8b1bd0b6d168afbd7d0794625718e0c7ab2163af2a60f7`). The worker-driven action matrix passed **16/16** and adapter registry **19/19**, with zero broker orders, live trading calls, live bots or production connections (matrix SHA-256 `b70816f02fb38e80d51ef4cc60f94851e0776af41144af80c55830c37449193c`). Real-provider Luna/Responses development passed **18/18** and regression **109/109**, with zero provider, schema, parse, validation or timeout failures (artifact SHA-256 `9683bbc2068d0b0de7d057b969e0d1390b2101faf574fce3518fd5bfa0a9162e` and `6ec38a37a07a329c6d19282b00a25e0ef4fe35d982a3f503054b76f222e783df`). Frontend build, typecheck, i18n lint/tests, command tests and high-severity audit passed on this backend-only batch; the audit reports one moderate Next.js advisory. Security found no concrete wrong-target or confirmation bypass in this two-turn path, and rejected automatic one-turn binding on a model verdict alone. The existing QA matrix expects a direct one-turn bot proposal, so this candidate must not be represented as accepted for that requirement. Full Score 2.0 → setupmatch → Paper and chat/Today/report parity remain independently unproved.

Independent protected [preflight 38106828989](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38106828989) on `82e85d87d8b3cdbef8d18eb4492178d944453825` passed exact checkout, release marker, backend/frontend identity and fixture authentication (artifact SHA-256 `08c58ee7b518305807ee17ac29d229ef2ccdb23bc742bff302687ed88d56949e`). The [12-case matrix 38106882118](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38106882118) returned **NOT_ACCEPTED** (artifact SHA-256 `e3a88cf85cf2c770f3476c79ddabdfcb4719a287f57cb11c00070b20b8681b1f`): 8 cases executed, 1 product failure, 4 safely not run. The immediate same-conversation `create_bot` ended `clarification_required`, missing `strategy_id`, with no proposal or bot. Sanitized diagnostic recorded `child_target_reference=confirmed_previous_plan`, `child_bound_immediate_pair=false`, and a successful direct owner-scoped parent containing setup and strategy. Thus the model's typed target was correct while the server did not bind the pair. The DCA guard confirmed exactly one setup only after execution, replay made no duplicate, all six reads completed, and polling/SSE parity held for all eight executed cases. No live order or live-bot activation occurred. Positive Score 2.0 → setupmatch → Paper, Smart-DCA amounts and chat/Today/report parity remain unaccepted.

Independent protected [preflight 38108645735](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38108645735) on current live `eb6dad15bc9a69b70c337ad5c3078d44e6cf7d5a` passed exact checkout, release marker, public SHA identity and QA fixture authentication (artifact SHA-256 `1b6adba3d84194786a1b77b6c018a5db4120025e3c4f6bd7adf9a086b93d6993`). The [12-case matrix 38108688334](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38108688334) returned **NOT_ACCEPTED** (artifact SHA-256 `b6057ce9afe4bc114cd6bc97a5ae1734c56987fb28251a831e8bed32b89ddbf8`): 8 executed, 1 product failure, 4 safely not run. The immediate Paper-bot child again selected `confirmed_previous_plan` but did not bind the owner-scoped setup/strategy pair; `strategy_id` was missing, with no proposal or bot. Six READ cases and polling/SSE parity passed; DCA persisted only after confirmation and replay did not duplicate it. No live order or live-bot activation occurred. The previous `fixture_binding_invalid` blocker is resolved; the current blocker is the bot continuation guard. The diagnostic candidate records only a fixed guard-reason enum for that path to distinguish its rejection branch without exposing QA prompts or fixture identities.

The diagnostic candidate changes observability only; it does not relax the bot-binding predicate. Focused bot/runner/continuation tests passed **187/187**, and the full backend suite passed **3294**, skipped **3** (log SHA-256 `b92af19664a53fa8cfa56f812b807268472375aaee7828ec8a058dc8e68ac7b3`). The isolated API/Celery/Responses action matrix passed **16/16** and the adapter registry **19/19** (matrix SHA-256 `f231ceed65d652b62000b033f7f0c0aef2514780b81e724d5df92c2c4bd2f280`). Real-provider Luna/Responses development passed **18/18** (SHA-256 `f1fbdb47312b49923121c79add325be2c6289065b2a533886304ae702c629c63`) and regression **109/109** (SHA-256 `add5df8a0fe37b278b63f9bfc40a226385a64d1355688b89aff1e301bcb1dc68`), with zero provider, schema, timeout, parse or validation failures. This local evidence does not change the live `NOT_ACCEPTED` verdict.

Independent protected [preflight 38110171200](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38110171200) on live `7e0e1a3afcd550a119b2c25e7e1b9ebb64ba499b` passed exact checkout, release marker, backend/frontend identity and fixture authentication (artifact SHA-256 `6debebed5a70fd648a71758e43ce3465eb3371aa8804a6503c4dfefba0f881d8`). The [12-case matrix 38110224505](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38110224505) returned **NOT_ACCEPTED** (artifact SHA-256 `044424ef5a74a23fc7a0ba348b9f220ab83f7a205aeb471f5906650aa8ec3c1a`): 8 executed, 1 product failure, 4 safely not run. The direct `create_bot` follow-up again lacked `strategy_id` and no proposal was made. The model selected `confirmed_previous_plan` and the direct parent contained the correct owner-scoped setup and strategy, but the server reported `child_binding_guard_reason=unsupported_utterance`. Six READ cases and polling/SSE parity passed; DCA persisted only after confirmation, without duplicate on replay; zero live trading calls or activations. The defect is the full-utterance target grammar, not the fixture binding. An experimental removal of that grammar was rejected before commit or deployment after independent Security demonstrated wrong-account and read-only proposals. A future repair must resolve target and action intent as typed evidence and retain explicit confirmation and owner/strategy checks.

The deployed candidate keeps the complete-utterance confirmation boundary and adds bounded natural variants for the just-confirmed setup/strategy. A typed `confirmed_previous_plan` value alone is never enough to bind the pair. A freer candidate route passed a local DCA → Paper probe, but independent Security reproduced wrong-account and negated-bot proposals in it; Build removed that route before release. The revised bounded route passed 64 focused tests, including those counterexamples. A local API/Celery/Responses run on the revised source created a proposal for the exact confirmed strategy without a bot or execution before confirmation (artifact SHA-256 `a8aa63c8bae1e41cb7659679a6ce63d7a3b3aad5d70637e8411cfa56025b39b6`). Security found no remaining concrete bypass in that bounded diff. Final local backend tests passed **3289**, skipped **3** (log SHA-256 `598e688e69c85bb5e6304bf103204be0059011c7d1264a7cd6afa2f4cd1fdba6`). The worker-driven action matrix passed **16/16** and adapter registry **19/19** (artifact SHA-256 `1e9d2efc9a947b10db65f5fd0399c0ee4db02b9798bc13d30b10f1da85e0bf9c`). Real-provider Luna/Responses development passed **18/18** (artifact SHA-256 `ace5b6b049b46c008b49ff4402653e9603f4c95bcdb21b48167e7e024f5e6cb5`) and regression passed **109/109** (artifact SHA-256 `d023ef2f9f0375963fb40a1f618a4dc9383b02ca9f6e069488f618f2b19b56ad`) with zero provider, schema, parse, validation or timeout failures. Independent live QA is pending; these local results do not override the previous live verdict.

Independent protected [preflight 38104171767](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38104171767) on `f33583467b10769186d23bf75b3b1d0491d94c45` passed exact checkout, release marker, backend/frontend identity and fixture authentication (artifact SHA-256 `683d60418b1812f73d0a4bfbbf5cf0a3a0e59081ae666afbd437bd00b350a403`). The [12-case matrix 38104225924](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38104225924) returned **NOT_ACCEPTED** (artifact SHA-256 `cd0c4c905fd74ecfe02e15ea8ead34f0d675e853c52427fb5725f8990c993347`): 8 cases executed, 1 product failure, 4 safely not run. All six read cases, including the stale-source probe, completed with polling/SSE parity. A guarded DCA confirmation created exactly one owner-scoped setup after execution and none before. The immediate same-conversation `create_bot` again ended `clarification_required`, missing `strategy_id`; no proposal, bot, live order or live activation occurred. The sanitized artifact confirms a successful direct parent with setup and strategy but does not expose the model `target_reference` or the immediate-target verification flag. The precise production selector branch remains unproven. Positive Score 2.0 → setupmatch → Paper, fixed/Smart DCA amounts and chat/Today/report parity therefore remain unaccepted.

The deployed candidate keeps the owner/action/run scope and confirmation boundary, but broadens the *bounded* direct-plan reference grammar so ordinary follow-up wording can select the exact confirmed strategy. It still rejects extra target clauses, third-party plans, different assets, older plans and competing owner-scoped names. Security's read-only adversarial review found no remaining concrete wrong-target or cross-owner bypass after rejecting an earlier model-only candidate. Two local API/Celery/Responses DCA → Paper runs passed with the exact confirmed strategy and no bot or execution before confirmation (artifact SHA-256 `110a50c8139aa721ed69496bd36d1315f4c2ec310192514b8dc29e1163cc1840` and `3cd0b4baef84d75e9e3244803276dec0f2eccf100d40b29a02bbf62cc665b62d`). The candidate also records only the validated target-reference enum and whether the pair was truly bound in the sanitized QA diagnostic; it does not store prompt text or identifiers in those fields. These are local checks, not a new live QA verdict.

On the final local source, root backend tests passed **3279**, skipped **3** (log SHA-256 `d7d134cc26e913cd8f76928ca1d319b915313ea5536d68ceaeb1e0de53deca3b`). The worker-driven action matrix passed **16/16** and the adapter registry **19/19** (matrix artifact SHA-256 `1a3937ea8a86c741ec3fe90074362a995b3db87c8d34ac14661634ab105f9c39`). A final natural-wording DCA → Paper run passed without confirmation or bot execution (artifact SHA-256 `f115a1650d6c443bf291ebeaaeffe0b4640dd0a6f73727c2e9a5ab9283ed0901`). Frontend build, typecheck, i18n lint/tests, command tests and high-severity audit passed; the audit reported one moderate finding. Real-provider Luna/Responses development passed **18/18** (artifact SHA-256 `ab15b6b0cecc81a569379c593b19dc9dc3f20ad6e0d9a576bb8daa0f4fad29b5`) and regression **109/109** (artifact SHA-256 `f29d79845f23b8fb5056e23c1e6976bf41793732a52a3f20ee59bc91bb3b436f`), with zero provider, schema, parse, validation or timeout failures. These local gates do not replace independent authenticated live QA.

Independent protected [QA run 38101953609](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38101953609) on live `1e5e5521bfbd7226784b27e4e0c0086f95b53588` returned **NOT_ACCEPTED** (sanitized artifact SHA-256 `e4f05a7b5f1b495ebeb5e2c8389be5bd3962d67c9370efd5aa6dc0a7e573f90f`). Eight of twelve cases ran, with polling/SSE parity for all eight. DCA creation had no pre-execution write, persisted exactly one owner-scoped setup after execution, and idempotent replay made no duplicate. The next same-conversation `create_bot` run ended `clarification_required` with `strategy_id` missing, no proposal and no bot. A stale-source read probe ended `UNAVAILABLE/responses_tool_round_limit`; later cases were safely not run. The artifact proves neither the exact model toolargument nor the precise selector branch, so Build does not claim either as a production root cause. No live trading or live-bot activation occurred.

The local public API/Celery/Responses reproduction found the concrete continuation defect: `prepare_responses_turn` loaded context without the current user message, so its verified immediate-plan target flag was absent before the model's bot proposal was selected. The later orchestrator did receive the message, after the selected bot draft had already lost `strategy_id`. The repair passes that message into the same owner-scoped continuation loader, accepts a bounded inverse strategy relation, and preserves the full-message wrong-target boundary. It also gives a read-only tool sequence one final answer-only provider round after the fifth read, regardless of front-door coaching classification, and stops bot-name extraction before a budget clause. The isolated DCA confirmation → same-conversation Paper proposal now passes with the exact confirmed strategy, no bot confirmation, and no bot or execution created by the child turn (artifact SHA-256 `dc4ee055f40882517e5372a488af5ae03060cab49fab972a2faa5d11bff33435`). Root backend tests passed **3273**, skipped **3** (log SHA-256 `010c28ffca9483cffce7ad2802154a58342ee17333072e84942e5151a9c59063`). The restarted local worker-driven action matrix passed **16/16**, adapter registry **19/19**, with zero broker orders, live bots, live trading calls or production connections (artifact SHA-256 `bb553fe14fcec84506c0c4598ef819cc65657dbbb677d841de1296f2ca394387`). Real-provider Luna/Responses development selector passed **18/18** (artifact SHA-256 `e5da02af8dd623be48b6886dfd316a409a27d0ee9d3d6bfc07b4538464201e77`) and regression **109/109** (artifact SHA-256 `22e6a33c445833bd08ba73cfdc382440ed1387a9884d95ca0f1dc0b06681fc8a`), with zero provider, schema, parse, validation or timeout failures. Frontend build, typecheck, i18n lint/tests, command/proposal/setup tests and high-severity audit passed; audit reported one moderate finding. Security read-only review found no concrete owner-scope or wrong-target bypass after adversarial revisions. These local results do not change the live `NOT_ACCEPTED` verdict until a new candidate is deployed and independently retested.

Protected [QA run 38099522827](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38099522827) on the prior live release `f2c5075fb632df0ceb1529678c0ab2667af53811` returned **NOT_ACCEPTED**: the confirmed DCA action had an owner-scoped setup/strategy pair, but the immediately following Paper-bot guided state lacked `strategy_id`. Eight of twelve cases executed; later cases were not run. The repaired local selector now binds the exact confirmed pair only after owner, action, asset and target-reference checks, and removes stale strategy context when the current target is unverified. Security read-only review found no remaining concrete wrong-target bypass. Local backend tests passed **3263**, skipped **3** (log SHA-256 `bb2d5738d8454511b5dfce4c2af9ace65b2f92793a996cad7ea3834a33b229bc`); the isolated API/Celery/Responses action matrix passed **16/16**, adapter registry **19/19**, with zero live bots, broker orders, live trading calls or production connections (artifact SHA-256 `935a86442128dc984e1bc3dcfe299f9ffef30392ea251ad6e9cd67cf004bf463`). Real-provider Luna/Responses development passed **18/18** and regression **109/109**, with zero provider, schema, parse, validation or timeout failures (artifact SHA-256 `792e73d89d0457b4b0cce75b9b89608c2aa53bb0af5e6d47ddf1d60ad00fb296` and `7de91c36125a4774495cfbb51a2c426bd57484c7dde3de220457f0183eea4f23`). Frontend build, typecheck, i18n, command/proposal/setup tests and high-severity audit passed; the audit reported one moderate finding. Candidate/main CI and Auto Deploy passed; authenticated live product QA is still pending. Separately, Operations' protected fixture provision workflow [38099991606](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38099991606) completed and [preflight 38100022654](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38100022654) confirmed fixture authentication. No fixture ID or token was exported.

Independent protected [QA run 38096057452](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38096057452) on `3d2ab4c526828c3c0f89859bec95e320120b409b` passed SHA and fixture-auth preflight, then confirmed guarded DCA creation without a pre-confirmation write. The next Paper-bot request in the same conversation again ended `clarification_required` with `strategy_id` missing, no proposal and no bot. **8/12 cases executed; verdict `NOT_ACCEPTED`** (sanitized artifact SHA-256 `96316fda1b04e8c33907369836dc669df3077f126ad57034d5750d86be8c8299`). The artifact does not expose the source of the missing ID or the Responses tool trace, so the exact production cause is not claimed. A separate stale-source probe ended `UNAVAILABLE/responses_tool_round_limit`; positive Score 2.0 → setupmatch → Paper and cross-surface parity remain unproven.

The replacement local repair retrieves the confirmed action only when its run ID exactly matches the immediate parent, then allows a narrow, owner-scoped direct follow-up to use that setup/strategy pair. It drops the transient pair flag before future turns and persistence. Read-only Security review found no remaining concrete wrong-target or stale-lineage bypass after adversarial revisions. On the final code, root backend tests passed **3243**, skipped **3** (log SHA-256 `6b695796a6aa3879384d629bf4f941199f8d0c76e1438a3875852aaa941c4df1`). The restarted local PostgreSQL/Redis/API/Celery/Responses matrix passed **16/16**, adapter registry **19/19**, with zero broker orders, live bots, live calls or production connections (artifact SHA-256 `90d8d3f81b006d582bc2e33933943299a694f4a80ef1ab16b27e0d666a6296eb`). A separate local two-turn DCA confirmation → Paper proposal used the same conversation and exactly the confirmed strategy, without confirming the bot (artifact SHA-256 `09ef6f51298e3fc5fba6c3c8764464f231dadd0a919988b5ff3fec2c01768a52`). Real-provider Luna/Responses selector development passed **18/18**, regression **109/109**, with zero provider, schema, parse, validation or timeout failures (artifact SHA-256 `03d1e8b0d313bcbd36777dc760c9d1bcd06ca90839b00c373b47823ea90a98e5` and `3bfab6b3b9d06f6166f32e12c0fd0e53d82e13525fe924a79c6b708932163c9b`). Frontend build, typecheck, i18n lint/tests, command tests and high-severity audit passed; the audit reported one moderate finding. These local gates do not replace independent authenticated live QA.

Independent protected [QA run 38092980933](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38092980933) on `ff58c83677b1595c44c3172100369fb5ff516ab6` passed SHA and fixture-auth preflight, then completed six read-only cases with polling/SSE parity and a guarded DCA setup creation. It saw no pre-confirmation write and exactly one setup after execution. In the same conversation, the Paper-bot request referring to the just-created plan ended `clarification_required`: no linked `strategy_id`, no proposal and no bot. The runner safely stopped later writes; **8/12 cases executed, verdict `NOT_ACCEPTED`** (sanitized artifact SHA-256 `37f7d9771cae8531ae0422454b09628db66d99f60f39b24afb8f59d94b5e6731`). The repair carries the confirmed setup/strategy pair only for an unambiguous temporal follow-up, lets it override stale selector/context IDs, and refuses old lineage after a failed immediate action, explicit asset mismatch or competing plan name. A local two-turn DCA → Paper run through API, Celery and Responses linked the bot to the confirmed strategy and kept it Paper. Backend tests passed **3218**, skipped **3**. The restarted local API/Celery/Responses action matrix passed **16/16** and adapter tests **19/19**, with zero broker orders, live bots, live trading calls or production connections (artifact SHA-256 `9be89fbda1005aaba9774a21606002eaa043877ccc3a88d255ae82dc5411a261`). Real-provider Luna/Responses selector development passed **18/18** and regression **109/109**, with zero provider, schema, parse, validation or timeout failures (artifact SHA-256 `d092a49348d03d20c978c3df8203f0f804a683f3f2044a7fc7b63fc8ede4f84f` and `0089b301465e350c14b422f14a742b628e386e898bc490c3309d2f6a7ffc0ef9`). Security re-review of the name boundary found no remaining incorrect strategy selection. Candidate/main CI and Auto Deploy passed; independent authenticated live QA is pending. Positive Score 2.0 → setupmatch → Paper and chat/Today/report/budget parity remain unproven.

On `d0da84b2`, independent protected [preflight](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38089070435) passed exact release identity and fixture authentication. A guarded [seven-case phase](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38089240621) passed six reads and a DCA create: the owner-scoped setup count remained zero through proposal, publish and confirmation and became one only after execution; replay did not duplicate it (artifact SHA-256 `02854c144166c2e76ee44d1a8c18471188e9c32282cc41b3e4bbb63adf23dff1`). A separately run [Paper-bot case](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38089399463) ended as `READ` with no operation ID or proposal (artifact SHA-256 `54f7c1c503c5f18ccafaf266616cb8d4f0b0cbbe6daf8b7456863e3cc59b2428`). The separate workflow generated a new fixture namespace and conversation; its artifact omits request text and context, so it cannot establish why classification diverged or prove a same-lineage bot creation. QA returned **NOT_ACCEPTED** for the full Score 2.0 → setupmatch → Paper/parity objective. No live order or activation occurred.

On deployed `580009479965b869fb25b197272de4afcce45a99`, independent [single-namespace QA run 38090221129](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38090221129) again passed guarded DCA creation with no pre-confirmation write. Its subsequent Paper-bot creation ended `UNAVAILABLE` with `orchestrator_failed`, no initial or final operation ID and no bot row; the runner safely marked later writes not run. Two read probes ended `responses_tool_round_limit` and `UNAVAILABLE`. QA returned **NOT_ACCEPTED** for the full chain. The local repair resolves a bot strategy through the explicitly named owner setup and returns typed clarification for ambiguous or absent links. The production exception behind `orchestrator_failed` remains unproven without a server trace; the read-probe round-limit cases remain open.

For the linked-strategy repair, **80 focused entity/orchestrator tests** and the root backend suite (**3193 passed, 3 skipped**) passed on the final source. The restarted local API/Celery/Responses action matrix passed **16/16** and its adapter tests **19/19**, with zero broker orders, live bots, live-trading calls or production connections (artifact SHA-256 `090ef6d2354335cbe6a9453ead3acae72a18d40f473b7d824370f0a85bd3c14b`). The real-provider Luna/Responses selector development and regression probes passed **18/18** and **109/109** respectively, with zero provider, schema, parse, validation or timeout failures (artifact SHA-256 `a981bef231aaeae5da557fed05f83e2059d9ffabe1bd2202539a00918e622d75` and `40e9043aa6530f36e7b14e12ec5efe1c9be2da0845e378c1a313ee61e6cf96a9`). Security read-only re-review found no remaining owner-scope or unintended strategy-selection blocker after tests for overlapping names, foreign linked strategies and stale strategy IDs. [Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38092264894) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38092386542) passed all five jobs. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38092507603) succeeded; public backend and frontend identity each returned HTTP 200 and the same SHA. These Build checks do not replace independent authenticated live QA.

The next runner repair makes protected write cases fail closed for all later cases, including resume, and binds the unique name of a newly requested bot without rewriting the referenced setup name. This allows one sequential namespace to test the complete action lineage safely. Local runner tests passed **62/62** and root backend tests **3185 passed, 3 skipped**. Product action contracts and provider selection were not changed; the prior 16/16 real Responses/Celery action matrix and 18/18 plus 109/109 real-provider selector results remain the evidence for those unchanged paths. Independent QA must rerun on the deployed SHA; positive fresh-score matching, Paper decisions and cross-surface fact parity remain unproven.

Independent protected QA on `d4007e4d` passed fixture authentication and eight read-only run/poll/SSE cases. The first typed create-setup write case on [run 38082907524](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38082907524) showed one owner-scoped setup row before confirmation; execution then returned a duplicate-name 409. The old runner had no database baseline before its initial `/runs` call, so this evidence cannot distinguish a premature product write from a row left by a resumed attempt. QA stopped fixture writes and returned **NOT_ACCEPTED**. Build reproduced the local product route without a pre-confirmation write and found a runner resume window that could repeat an uncheckpointed case. The current repair adds a pre-run owner-scoped baseline, stops before confirmation on any proposal-stage write or unavailable evidence, and checkpoints each attempted case before its first product request so interruption cannot silently replay it. This is a runner safety and observability repair; the production cause of the historical row remains unproven.

The repaired runner fingerprints all owner-scoped setup, strategy, bot, watchlist, indicator-configuration and preference state, plus broker-order and live-bot counts. It checks after a failed initial run, after a proposal and after publish, including missing-proposal and expired-case paths. Interrupted cases remain incomplete and are not replayed. Local validation on this branch: backend **3177 passed, 3 skipped**; runner-specific **59 passed**; local owner-scoped PostgreSQL fingerprint query succeeded. The isolated worker/API/Responses action matrix passed **16/16** with zero broker orders, live bots, live trading calls or production connections (SHA-256 `5e2e4f5138521c0a8777264583faf473a2cf193156abd89d26d47e53273672aa`). Real-provider Luna/Responses selector development passed **18/18** and regression **109/109**, each with zero provider, schema, timeout, parse or validation failures. These local checks do not replace independent authenticated live QA.

On `202ca439`, independent QA's isolated create-setup run [38085447943](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38085447943) kept the owner-scoped setup baseline unchanged through the terminal proposal and publish, then created exactly one row on confirmed execution. The broader protected matrix [38085539264](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38085539264) instead observed one namespaced setup row after the terminal proposal and before publish, confirmation or execution. Its 12 product traces each show one attempt and one dispatch; the artifact has no runner-process or reconnect history. QA stopped before confirmation and returned **NOT_ACCEPTED**. Security review found that a detached QA runner could be restarted while its Python child still worked, allowing overlapping fixture actions on one namespace. The current repair serializes Python runners across protected workflows, tracks the Python child through SSH reconnects, uses attempt-specific state, and fails without automatic restart on lock contention. This is a credible runner race, not proven attribution of the observed row. A fresh independent matrix is required; no positive Score 2.0 → Paper or full chat/Today/report parity is accepted yet.

Before the selector correction below, local validation after the runner repair showed backend **3178 passed, 3 skipped**; runner-specific **60 passed**. The real local API/Celery/Responses action matrix passed **16/16** with adapter tests **19/19**; matrix artifact SHA-256 `a2b10edbd73488b7c41236d1ef5145b08b0bb19934f97da2439d753cdbb2afe0`. The Luna/Responses selector development set passed **18/18**, zero provider/schema/timeout/parse/validation failures; artifact SHA-256 `df71fb37283ea52ebc21a5ff19616ae3497c9f37c6e8adfffa2bf93a180b6f73`. The complete regression then failed **108/109**: an evidence-source follow-up was selected as a request to rephrase the previous answer (artifact SHA-256 `04fe80c369d8468c44ec65a80477668414d3133364bbc25b83545019775dcb66`). This is a real red release gate. The repair recognizes evidence questions about a prior assessment as a typed discourse act and keeps that act from becoming a mere restatement when previous-response lineage exists. New local and real-provider validation is required before candidacy. A Linux process probe showed the inherited file lock remains held after its Bash wrapper is killed and releases after its child exits. Security's read-only review found no remaining concrete duplicate-write or fixture-exposure blocker in the revised workflow; this does not establish the historical row's cause or a live product verdict.

After the selector correction, the backend suite passed **3183**, skipped **3**. The restarted local API/Celery/Responses action matrix passed **16/16**, complete, with zero broker orders, live bots, live-trading calls, or production connections; artifact SHA-256 `b24b9d658300c4bc946a686c3e267446748654a4bca2cd63a19e66dc694dc268`. The final real-provider Luna/Responses development set passed **18/18**, with zero provider, schema, timeout, parse or validation failures; artifact SHA-256 `a34f2f4dd3ff999da7877895f880d031f786d98b3da4b8bd1af33d0ea53494c4`. The complete regression rerun passed **109/109** with the same zero failure categories; artifact SHA-256 `d0a47d42357aaea4f135d236aadfe1d396a30a732e8eff3bce37debabd3961ab`.

### Protected QA and fixture recovery

Independent browser QA on `6b81d9e` observed ETH Market 40, Macro 20,
Technical 40 and benchmark 33.3 in Analyse. A new daily setup with boundaries
20–60/0–70/40–80 appeared in Mijn Plan as a positive match at 81%. Its
semi-automatic Paper-bot creation failed with `POST /api/bot/configs` HTTP 500;
after refresh the new bot was absent and no decision or order was made. The
server trace shows a PostgreSQL `bot_configs_mode_check` violation: the API
accepts and writes `semi-auto`, while the deployed constraint allowed only
`semi`. The repair migrates existing `semi` rows to `semi-auto`, updates the
constraint, and makes the pre-start schema gate reject the old constraint.
The report viewed during QA was a 03:36 historical snapshot, so it is not
evidence for parity with the newly created 81% setup. QA verdict: **NOT_ACCEPTED**
for the complete positive Score 2.0 → Paper chain.

Security review of the failed bot-creation path found a related worker defect:
the worker previously auto-executed every proposed order without checking the
bot's `mode`. A newly creatable `semi-auto` live bot could therefore have sent
an order to an exchange without per-order confirmation. The repair leaves
`manual` and `semi-auto` orders pending for the explicit execution route and
permits automatic execution only for `auto`. The executor also locks and
rechecks the current owner-scoped bot mode, active state and Paper/Live setting
before any exchange call. No exchange order was placed
in local validation.

Local repair validation so far: the migration was applied twice in disposable
PostgreSQL 16, converted an existing `semi` row, accepted a new `semi-auto`
row, rejected a new `semi` row, and rolled back successfully.
The real-provider Luna/Responses selector development set passed **18/18**
and regression passed **109/109** with zero provider, schema, timeout, parse or
validation failures. After the mode-safety repair, the backend suite passed
**3170**, skipped **3**; the focused mode test passed **18**. The refreshed
worker-driven action matrix passed **16/16** with zero failed contracts, broker
orders, live bots, live-trading calls or production connections
(SHA-256 `f3afb08fbdd9cd6934e007cc2e1faeed8a2997e0ff7f9056cd51bbb9fdf33f6d`);
adapter tests passed **19**. Frontend production build, typecheck, i18n lint
and tests, command, proposal and setup tests passed. `audit:high` exited 0
with one moderate Next.js advisory and no high vulnerability. [Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38081674469)
and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38081801647) passed all five jobs; [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38081918936)
passed. Backend health and frontend build-info returned HTTP 200 on the merged
code SHA. A local bootstrap mismatch
(`daily_scores.indicator_evidence` as JSON instead of production JSONB) was
also corrected; a reset local database passed all migrations and the pre-start
schema health gate.

The earlier protected preflight failed with `fixture_binding_invalid` before product testing. A protected, sanitized diagnosis found no valid Build or QA binding. [PRs #148–#150](https://github.com/gvangalen/antigravity-trading-tool/pull/150) added the Operations-only diagnosis/provisioning path and created separate nonadmin Build and QA fixtures with server-only bindings. [Preflight run 38077460653](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38077460653) then authenticated the QA fixture successfully (`/api/auth/me` HTTP 200). No fixture ID or credential was exposed in the handoff.

The first encrypted read-only QA manifest stopped before case execution because its storage root was not writable. [PRs #151–#152](https://github.com/gvangalen/antigravity-trading-tool/pull/152) moved it under the protected secrets directory. [QA run 38078492411](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38078492411) then completed six HTTP-200 runs with polling/SSE parity and no confirmation, execution, or live-trading calls. The six failed manifest assertions required legacy operation IDs, but the Responses read-only path intentionally publishes an answer without one; those failures do not establish six failed coach answers. The runner redacts answer content, so that artifact also does not prove factual correctness.

Independent browser QA on the same prior release SHA `3b77ab6a4cbaa3a71db192ca280a2be8f78aa965`, using a separate authenticated ETH account, found Analyse and FINN consistent for the missing-Market path: Macro 20, Technical 40, combined unknown, setup boundaries 20–60 / 30–70 / 40–80, and no current setup match. The bot remained Paper / Hold; its €20 amount was described as a budget limit, not cash. Today's report contained an older 40/20/40 snapshot; it is historical relative to the later Analyse read. A one-time client-side `/report` loading error cleared on reload and did not recur in one fresh navigation, so its cause is unresolved. Neither this browser run nor the protected manifest proves a positive fresh match or a scored Paper decision.

[PR #153](https://github.com/gvangalen/antigravity-trading-tool/pull/153) prevents Automation from ranking bots by historical decision scores and labels a verified saved setup score with the decision timestamp. It changes presentation only; score calculation and bot execution are unchanged. Frontend build, typecheck, i18n checks and relevant tests passed locally; candidate and main CI passed. Independent live QA has not yet reviewed this new presentation SHA.

## Previous Score 2.0 Repair

Independent browser QA of the preceding release observed a fresh BTC benchmark and a persistent Paper bot, but did **not** accept the full chain: report retrieval returned a 502 during the run, onboarding silently saved score boundaries that the user had never seen, the trade panel described a bot budget limit as available balance, and FINN did not reliably confirm the saved bot's Paper state. The observed Macro score was below the hidden setup minimum, so no positive setup match or completed Paper decision was demonstrated. The exact cause of the live 502 is not established from browser evidence; its timing overlapped deployment activity.

This repair gives report generation a short-lived database connection instead of disposing the shared API engine, projects verified category scores into a single-asset report, starts first-report generation when the API returns its pending placeholder, shows and saves the setup score ranges during onboarding, labels bot spending limits accurately, and exposes a direct owner-scoped saved-bot read through the existing portfolio adapter. A new independent QA run must still prove the positive and missing/stale Paper paths on one identified live SHA.

## Previous Score 2.0 Candidate

[PR #146](https://github.com/gvangalen/antigravity-trading-tool/pull/146), with implementation commit `407b90b35f2b2ba746c1d14d1b5113f2a5fe82e2`, repairs the clean-local-database Score 2.0 upsert key and prevents a second macro-score multiplier from altering a confirmed fixed or Smart DCA amount. Cash, budget, exposure and kill-switch limits remain in the Paper path; the macro multiplier remains for non-DCA trades. This release is deployed but has not passed independent authenticated live QA.

Independent Security review found that a general strategy write could persist the `planned_exact` marker without validating the amount rule. The candidate now validates the canonical fixed/Smart DCA amount rule on create and update, rechecks saved strategy data before the Paper worker emits the marker, and makes malformed historical marked plans hold instead of treating them as ordinary DCA. A dedicated persisted-row regression proves the hold and retained macro guardrail. Security re-review found no remaining independent safety-cap bypass in this path; valid owner-authored direct API plans are still accepted as plans. This is a local code finding, not authenticated production execution evidence.

Final local gates after this change: backend **3152 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command tests and `audit:high` passed (one moderate Next.js advisory, no high vulnerabilities); mobile typecheck, lint with warnings but no errors, and web/iOS/Android bundle smokes passed. The final isolated worker-driven action matrix passed **16/16** with zero prohibited executions, SHA-256 `83dce72f1c08bdecb676bc465afd77003828f25c9378eb060e85548c61e33f62`. Real-provider Luna/Responses selector development passed **18/18**, SHA-256 `ef8add0e9954ecb1a8ec72abd9230e734fb04b91c4047b693fa9b1583b978b77`; regression passed **109/109**, SHA-256 `bcb638ef60cb03227c024ddcef317d8a40dba67d3d5fdde598869aa52f7f083b`, with zero provider, schema, parse, validation or timeout failures. [Candidate CI run 38075199262](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38075199262) and [main CI run 38075318015](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38075318015) each passed all five jobs. [Auto Deploy run 38075445628](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38075445628) succeeded; both public SHA endpoints matched `3eb0785881ebf7010d13ede47482b76425633694`. Independent authenticated live QA remains blocked by the fixture binding and has not tested this SHA.

Local evidence: a dated ADA/DXY/RSI data chain produced Market 60, Macro 20, Technical 50, benchmark 43.3, setup `matches` and a persisted €100 Paper decision following the confirmed curve. Missing RSI and stale DXY each yielded `insufficient_data`, Paper hold and €0. The probe artifact SHA-256 is `a1cedc78d7b1156b8f40221b48e8addd1020ec20d2e85315ec11cac8f939084d`. Backend: 3149 passed, 3 skipped. Worker-driven action matrix: 16/16 (SHA-256 `02936f1a3098d4bb5d7833521581def15a55e9cbb0d4c1775b2208a596200503`). Real-provider Luna selector development: 18/18; regression: 109/109 with zero provider/schema/timeout/parse/validation failures. [PR CI run 38072355003](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38072355003) passed all five jobs. These are local and CI facts, not authenticated live QA.

The user authorized a new independent QA assignment for production SHA `c8c76d02f5003975f81f7d4ac429b925eba8d84a`. The first protected [`auth_preflight` run 38072892512](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38072892512) failed SSH host verification before fixture authentication. Operations pinned `QA_SSH_HOST` to the production IP serving the same SHA over verified TLS and updated `QA_SSH_KNOWN_HOSTS` from an existing trusted local ED25519 pin that matched the current server key; `StrictHostKeyChecking=yes` remained enabled. A second protected [`auth_preflight` run 38073237922](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38073237922) reached the host and verified checkout, release marker, backend and frontend on the exact target SHA. Its sanitized report ended before `/api/auth/me` with `fixture_binding_invalid`, `qa_status: NOT_STARTED`, zero cases and zero confirmation, execution, live-trading or live-bot-activation calls. QA's `NOT_ACCEPTED` verdict means the product chain remains unassessed, not that a product case failed. The protected `FINN_QA_USER_ID` binding must be restored by QA/Operations; Build must not substitute a normal account or access the fixture.

Local Build evidence for this repair: root pytest **3146 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command and proposal tests, first-report pending-state test and `audit:high` passed (only a moderate advisory remains); mobile typecheck, lint and web/iOS/Android bundle smokes passed, with lint warnings but no errors. The isolated local FastAPI/Celery/PostgreSQL/Redis/Responses action matrix passed **16/16**, zero failed contracts, broker orders, live bots, live-trading calls or production connections; `.local-finn-parity-artifacts/full-action-matrix.json` SHA-256 `802f39a60cd47e0cd563d1e526c7f968470c42eca3fa29da912037f07a847b14`. Real-provider Luna selector development passed **18/18**, SHA-256 `55459f079868b36de8fa6240214e1fb8e1772ac8c3e0263030f487e80f78b0a2`, and regression passed **109/109**, SHA-256 `38f05e4c0986c6251bb719c05d58461367119a30fdd72833cc6858e9fe6b4bb4`; both had zero provider, schema, parse, validation or timeout failures. A report read from the synthetic local database loaded the owner context through the scoped connection, and a real `/v1/responses` call returned all required daily sections. These are local Build facts, not authenticated live QA or a proven cause of the earlier 502.

[Candidate CI run 38068345710](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38068345710) and [main CI run 38068492168](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38068492168) each passed all five jobs. [Auto Deploy run 38068598183](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38068598183) succeeded. Build verified the two public SHA surfaces and did not perform authenticated production QA. A first candidate CI run was red only because the repository's tracked frontend export was omitted; the export was added before the successful candidate and main gates.

## Previous Release (shared Score 2.0 chain)

| Field | Value |
| --- | --- |
| Phase | `NOT_ACCEPTED` after independent authenticated browser QA; release deployment gates passed, but product parity and the positive Paper path remain open. |
| Goal | Prove the shared Score 2.0 → setup match → Paper path for fresh, missing and stale inputs; align FINN chat, Today and report evidence; move admin-log AI to explicit Luna/Responses; retire unused public legacy routes and labels. |
| Candidate branch | `codex/finn-score-chain-convergence`; [PR #142](https://github.com/gvangalen/antigravity-trading-tool/pull/142). |
| Implementation commits | `bf1fb40856aad9b6e1502d35f21a4d171be3b491` and `5ca2d9150c6ab247ab9eba0104f7938438c6ad0b`. |
| Verified deployed SHA | `bec8e1b73b1a73169d24686f77dc4a3e20dbaf65`; backend health and frontend build info each returned HTTP 200 and this exact SHA. This status-only update may create a later public SHA. |
| Last updated | 2026-10-10. |

This batch uses the shared verified benchmark for FINN Today and report context. A local database fixture produced Market 80, Macro 70, Technical 60, benchmark 70, a matching setup, and one Paper bot without an order; the same benchmark appeared in chat, Today and report context. Missing RSI evidence and a stale RSI source each produced an unknown benchmark and an insufficient setup match, rather than a zero score. The deterministic bot path was exercised locally for a fresh matched score and for missing/stale sources. This is synthetic local evidence, not a live positive Paper decision.

The old onboarding agent bootstrap route and task were removed after its callers moved to the indicator-history → score → Today/report sequence. The public `/ai/master_score` route and web/mobile callers moved to `/scores/benchmark`; internal `master_score` schema fields and methods still have active callers and remain until a typed contract migration. Admin-log analysis now explicitly selects `gpt-6-luna` with reasoning `none` through Responses. Its real-provider synthetic-log probe returned HTTP 200 from `/v1/responses` and a structured response.

Local validation: backend **3144 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command/proposal tests and `audit:high` passed; mobile typecheck, lint and web/iOS/Android bundle smokes passed. The isolated worker-driven action matrix passed **16/16** with zero broker orders, live bots, live-trading calls and production connections; artifact `.local-finn-parity-artifacts/full-action-matrix.json` SHA-256 `d9ddcf64ce104b38e159d0a177731c0733decc203ae5b227855b35a429da10ae`. Real-provider Luna selector development passed **18/18**, SHA-256 `e83813d3574659b685fdeab18ed70d60b7034ca0612a73b1750977d4edd08462`; regression passed **109/109**, SHA-256 `606223db4f365220c09c7f3e391c135f6f9c3bb775e31c5ccaaba1516c759bde`, both with zero provider failures. Local database parity artifact SHA-256 `ecb36a86fc3767595dbbdbb1fe540dd333d1e76dd4634ae53836aa2536d20189`; missing/stale source artifact SHA-256 `c45af2589e21541bc78358e954151c8f3f96be3ce31faafb6380adb84af18479`.

[Candidate CI run 38065766320](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38065766320) and [main CI run 38065893062](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38065893062) each passed all five jobs. [Auto Deploy run 38066012202](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38066012202) succeeded. Build verified public backend/frontend identity and performed no authenticated production QA.

Independent browser QA confirmed a fresh BTC benchmark and a persistent Paper bot but found the report, onboarding-boundary, budget-label and Paper-read issues summarized in the active repair above. It did not demonstrate a positive matched Paper decision. A later repair must be deployed and independently retested before this chain can be accepted.

## Previous Release (React recovery and source moments)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, Auto Deploy and public deployment identity passed. Authenticated live acceptance remains pending. |
| Goal | Stop the Analyse page's React-runtime reload loop and give FINN readable source moments for its first price/score response without changing Score 2.0 freshness decisions. |
| Candidate branch | `codex/finn-chat-react-render`. |
| Implementation merge | [PR #140](https://github.com/gvangalen/antigravity-trading-tool/pull/140) merged as `69d903577bff6a8a93c16cdb03f42b469faefb68`. |
| Verified deployed SHA | `69d903577bff6a8a93c16cdb03f42b469faefb68`; backend health and frontend build info each returned HTTP 200 and this exact SHA. A later status-only deployment can change the public SHA without changing the implementation. |
| Previous live SHA | `feb0b1ebe03c1c0acaee520a5004ffb0ef8dc49f`. Independent QA replayed the exact FOMO question once: FINN answered without a proposal or action. The browser also reloaded automatically and logged React error #185; the first price/score answer still showed milliseconds. |
| Last updated | 2026-10-10. |

React error #185 denotes excessive state updates. The frontend recovery script certainly treated every minified React error as a stale-cache event and reloaded the page. The Analyse workspace also supplied newly allocated empty watchlist and score-weight objects during incomplete responses; those render dependencies have been stabilized and weight state writes now stop when values have not changed. Without the original browser component stack, the exact state loop cannot be attributed to one component from this evidence alone. Runtime errors will now remain visible instead of triggering a cache purge and reload; chunk-loading failures still use cache recovery.

The FINN score adapter now displays component source moments to whole seconds, and the Responses read boundary does the same for the market snapshot. Tool freshness is still calculated from the unrounded provider moment. Stored measurements, scores and bot decisions are unchanged. Focused tests cover both model-facing timestamps and the unchanged market-source freshness input.

Local validation: backend **3133 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command/proposal tests, release-hardening tests and `audit:high` passed. The isolated worker-driven action matrix passed **16/16**, with zero broker orders, live-trading calls or production connections; artifact `.local-finn-parity-artifacts/react-score-display-action-final.json` SHA-256 `e6b6c0924eacc00bd6b4bb774e3bbfd1538b09bc65c3752257f2dbb1b84ed705`. Real-provider Luna selector development passed **18/18**; artifact `.local-finn-parity-artifacts/react-score-display-selector-development.json` SHA-256 `db47325f2e6dceced92d2dc4d26b35de5f13cd3b85466ae3c1bdcf5b52e32aaa`. The first full regression was **108/109** because `reg-ambiguous-improvement-variant` chose `evaluate_plan` instead of `clarify_request`; that red artifact remains recorded. Three immediate isolated replays of that case chose `clarify_request` (**3/3**). The complete rerun passed **109/109** with zero provider, schema, parse or timeout failures; artifact `.local-finn-parity-artifacts/react-score-display-selector-regression-rerun.json` SHA-256 `d5c1264a2e08d2fc109ce4d7ee6f4a25ec68a32bb9fc4adc5826ad78c8cf643c`. Candidate [CI runs 38050844986](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38050844986) and [38051454632](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38051454632), plus [main CI run 38051574431](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38051574431), each passed all five jobs. [Auto Deploy run 38051669790](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38051669790) succeeded. Build verified backend health and frontend build info returned HTTP 200 with the same deployed SHA; Build performed no authenticated production QA.

Independent QA should replay the price/score → FOMO conversation once and monitor for a reload or React error, including a partial Analyse response. It should check that the first price/score answer and the DXY answer show readable source moments. The fresh-price/missing-score transient state remains opportunistic; no score or trade should be manufactured to trigger it.

## Previous Release (FOMO turn and source display)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate and main CI, Auto Deploy, and public deployment identity passed. Authenticated live acceptance remains pending. |
| Goal | Diagnose the intermittent first-turn FOMO failure, verify the fresh-quote/missing-score boundary, and present DXY with the same two-decimal precision and readable source time as Analyse. |
| Candidate branch | `codex/finn-fomo-turn-and-display`. |
| Candidate implementation SHA | `2d6ae86725a76a68babd9313318afab3287d9c49`; [PR #138](https://github.com/gvangalen/antigravity-trading-tool/pull/138) merged as `03e0c97589de6ec9eae84a492437138ffea391e7`. |
| Verified deployed SHA | `03e0c97589de6ec9eae84a492437138ffea391e7`; backend health and frontend build info each returned HTTP 200 and this exact SHA. A later status-only deployment can change the public SHA without changing the implementation. |
| Previous live SHA | `3ae758d3a4fc1a1f7559764f49ea38437c6382c0`, independently tested: price and valid Market score were distinguished, but the first FOMO turn failed once; a repeat succeeded. The missing-score state was not present in that live run. |
| Last updated | 2026-10-10. |

The original production FOMO run was located through a read-only, metadata-only runtime-store query using the exact user-supplied prompt and UTC window. It terminalized `unavailable` with `responses_tool_round_limit` after **five completed read tools** in about 12 seconds. The immediate retry completed after four read tools. This was neither browser polling exhaustion nor the 40-second lifecycle deadline. The request preprocessor also classified the explicit “geen voorstel” coach question as `create` because it mentioned both “voorstel” and “setup”; that disabled the read-only continuation boundary. The repair treats a declined proposal as read-only unless an affirmative earlier mutation exists, and permits one answer-only Responses round after five successful read calls on a read-only coach turn. No further tools or actions are allowed in that final round. The model still owns the answer, and action requests retain the original round limit. The frontend now writes only run-ID, terminal status and error code to the console for failed/unavailable runs, and a distinct diagnostic for polling exhaustion. These diagnostics are not added to FINN's chat answer.

The model-facing DXY snapshot now shows two decimal places and source timestamps to whole seconds. Stored readings, Score 2.0 calculations and bot decisions are unchanged. A deterministic local test covers a four-minute-old Price observation with a saved Market score that still refers to older evidence: the price source is fresh, the Market score remains unavailable pending rebuild, and no benchmark is fabricated. This is **local proof**, not an authenticated production observation of that transient state.

Local validation on the final repair: backend **3131 passed, 3 skipped**. Targeted regressions verify that the exact FOMO request is read-only, that an explicit mutation remains a mutation, and that Luna can answer after five completed reads without a sixth tool. The rebuilt isolated worker-driven safe-action matrix passed **16/16**, with zero broker orders and live-trading calls; artifact `.local-finn-parity-artifacts/fomo-round-final-safe-action-16.json` SHA-256 `a352833ff82a8106a1e5f6b15833b8749647a66d1f5a8690bce9de7357369be5`. A local synthetic real-provider replay of the exact FOMO wording selected **five read tools and then one tool-free answer round**, completing without a proposal in 12.1 seconds; artifact `.local-finn-parity-artifacts/market-score-fomo-exact-probe.json` SHA-256 `42334071ffe16769b220c38f391485c1bf02200609badc4c618d4739003f2fcc`. Real-provider selector development passed **18/18**, SHA-256 `bfffeb5e5606939ffb07cdffb89b787b9f6d7d3f18fecc8945eef0367f9259e8`, and regression passed **109/109**, SHA-256 `d810f4398bfc29406308057888fd17dedb7520c3a570a2e7c6f580547063c0bd`, with zero provider, schema or timeout failures. Earlier candidate regression runs with one elliptical-reformulation mismatch (**108/109**) remain recorded as red diagnostics. A broader 37-case legacy parity harness was also red: it expects selector `operation_id` metadata on model-led read turns and reported a separate delete-operation mismatch. That harness is not the safe-action matrix and needs separate contract maintenance. Frontend build, typecheck, i18n lint/tests, command/proposal tests and `audit:high` passed before the backend-only repair. Candidate CI run [38037988431](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38037988431) and main CI run [38038141442](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38038141442) each passed all five jobs. [Auto Deploy run 38038244700](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/38038244700) succeeded. Build verified backend health and frontend build info returned HTTP 200 with the same deployed SHA; Build performed no authenticated production QA.

Independent QA should replay the exact score → FOMO conversation and inspect the new failure diagnostic if it recurs. QA should also verify DXY presentation and opportunistically check a live fresh-price/missing-score state without manufacturing scores or trading.

## Previous Release (market score evidence parity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, Auto Deploy and public SHA checks passed. Authenticated live QA remains pending. |
| Goal | Keep a fresh Price measurement distinct from a verified Score 2.0 Market score, and avoid exposing raw status codes or binary-float artifacts in FINN's explanation. |
| Candidate branch | `codex/finn-market-score-evidence-parity`. |
| Candidate implementation SHA | `8d1422075732a4fe1869acc41b20d3489f290eec`; release evidence commit follows. |
| Candidate merge SHA | `caac418eb9541c6e9107511ef123dbbaad4cc602` ([PR #136](https://github.com/gvangalen/antigravity-trading-tool/pull/136)). |
| Production SHA | `caac418eb9541c6e9107511ef123dbbaad4cc602`, observed on both public surfaces. This status-only update creates a later SHA; verify current identity before authenticated QA. |
| Previous live SHA | `d3b8c038a69730f9cc3f05206235e612051e74e5`, independently tested: the DXY freshness fix passed; Price quote freshness and Market score eligibility contradicted each other. |
| Last updated | 2026-10-09. |

The code-level cause is that `get_market_snapshot` used the database receipt time as the quote's `as_of`, while Score 2.0 verifies a saved daily score against the configured per-owner indicator measurements and evidence. A failed score verification was always called `stale_source`, even when the measurement itself was fresh and only the score rebuild or evidence match was pending. Without the cited live run trace, the exact failed predicate on that turn is not proven. The repair uses the quote's provider observation time, gives score verification and per-indicator source freshness separate statuses and plain explanations, and makes both read tools available to the model when a question compares them. The macro tool rounds the model-facing DXY value to six significant digits; storage and scoring keep their original precision. The strict Score 2.0 bot gate, score formula, trading permissions and model answer ownership are unchanged.

Measured local evidence: backend **3123 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command/proposal tests passed; `audit:high` exited successfully with one moderate Next.js advisory. The isolated PostgreSQL/Redis/API/Celery action matrix passed **16/16** on the final code, artifact `.local-finn-parity-artifacts/finn-market-score-evidence-release-rerun.json` SHA-256 `644fb527d22196b39140b968ebca8cb1882060879b5214f54e0d89993b47ea6b`. An earlier local matrix had one strategy-clarification miss (15/16); that diagnostic is retained and is not represented as green. A synthetic local two-turn real-provider probe on a fresh quote with an unverified Market score selected both read tools, described the quote as fresh and the score as pending verification, and emitted neither a raw status code nor a made-up score; artifact `.local-finn-parity-artifacts/market-score-two-turn-final.json` SHA-256 `018e6698d7132aeca38a43d429876117081bb70477432d01965dd9299f4b3ec1`. Real-provider Luna selector development selected the expected operation **18/18**; regression selected it **109/109** with zero provider, schema, timeout, parse or validation failures. Artifacts SHA-256 `668be1f5b4f1b73b29958e87f9d2aca18f32e66aaa98bc453180f94bb46b3848` and `fdd2a000884cf893205fd3a54c712fbfe5371968b98453ac3f1c4eda1671ff27`. The regression has one additional conversation-reference/missing-input mismatch on a live-bot-activation case (**108/109** on those two metrics); the same case and result occur in the previous deployed release's regression artifact. That high-risk action path is outside this score-read repair and remains policy-denied. Build performed no authenticated production QA.

After deployment, independent QA should ask FINN to compare the Price measurement's source time with the current Market score in Analyse, then ask a FOMO follow-up. A recent quote and unavailable score must be explained separately, with no raw `stale_source` label, full binary-float DXY value, invented combined score, proposal or order. Check the actual stored score and quote source moments; a truly old measurement should be called old, and a later valid rebuild should allow the score. This candidate does not by itself prove which score verification predicate failed in the original live run.

[Candidate CI run 37983016232](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37983016232) and [main CI run 37983274619](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37983274619) passed all five jobs. [Auto Deploy run 37983491784](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37983491784) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` each returned HTTP 200 and SHA `caac418eb9541c6e9107511ef123dbbaad4cc602`. Build performed no authenticated production QA.

## Previous Release (macro freshness parity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, Auto Deploy and public SHA checks passed. Authenticated live QA remains pending. |
| Goal | Align the separate FINN macro snapshot's source freshness with Score 2.0 so the same DXY observation cannot be fresh in Analyse and stale in a follow-up tool result. |
| Candidate branch | `codex/finn-macro-freshness-parity`. |
| Candidate implementation SHA | `158783fdb9840a75fe46112cd11e54d5ab3332da`; status evidence commit follows. |
| Candidate merge SHA | `88b3c4e54f67920a04f3a62e90407cd1bf56c9ea` ([PR #134](https://github.com/gvangalen/antigravity-trading-tool/pull/134)). |
| Production SHA | `88b3c4e54f67920a04f3a62e90407cd1bf56c9ea`, observed on both public surfaces. This status-only update creates a later SHA; verify current identity before authenticated QA. |
| Previous live SHA | `7d81881d7c5f131016ab8f66ead3d76d0ab8c956`, independently tested: score/FOMO continuity passed; separate macro snapshot freshness contradicted the Score 2.0 DXY source moment. |
| Last updated | 2026-10-09. |

Root cause in code: `read_macro_snapshot` fell through to a generic six-hour tool TTL, while Score 2.0 checks each macro observation using its own release window (four days for DXY, 75 days for monthly inflation/rates). The macro adapter now reports each indicator's `source_status` using the Score 2.0 source rule and supplies a snapshot status only when all measured indicators agree. A mixed snapshot is `unknown` at bundle level; each source retains its own status. No response copy, model override, score calculation, bot rule or action contract changed. Without the specific live run trace, this explains the deterministic mismatch in the deployed code but does not prove that the cited run used that exact tool call.

Measured local evidence: backend **3120 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command/proposal tests passed; `audit:high` exited successfully with one moderate Next.js advisory. Isolated PostgreSQL/Redis/API/Celery action matrix passed **16/16** with zero production connections, broker orders, or live trading calls; artifact `.local-finn-parity-artifacts/finn-macro-freshness-action-matrix.json` SHA-256 `555bfcf0a4f9d1424426d5a3146f4b0c0eda9b43a330904ed729c03ec6fa4dde`. Real-provider Luna selector development passed **18/18** and regression **109/109** operation matches, with zero provider, parse, schema, timeout or validation failures; artifacts SHA-256 `7788cce8f4a23013f60da0e7ff0ff43f07acaba50e15b37542a6d69306325a23` and `ba57e927e75b303591b69387eef682af90dc5ba30f2551a67c3c6d77f52a046a`. A separate synthetic local two-turn real-provider probe read current ETH scores, then the separate DXY macro snapshot; Luna called `get_current_asset_scores` followed by `get_market_snapshot` and identified the same 12-hour-old DXY measurement as fresh in both answers. Artifact `.local-finn-parity-artifacts/macro-freshness-two-turn-probe.json` SHA-256 `ba65b151a6fdb4115bfde24ac6c4f2f078dab15f9233e75ef331244d11932409`. Build performed no authenticated production QA.

After deployment, independent QA should repeat the same score-read → separate macro-snapshot question on the deployed SHA. Compare the DXY source moment and status with Analyse, including an actually stale or missing macro source if available, and verify that no trade or bot action is proposed.

[Candidate CI run 37977348735](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37977348735) and [main CI run 37977569308](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37977569308) passed all five jobs. [Auto Deploy run 37977796710](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37977796710) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` each returned HTTP 200 and SHA `88b3c4e54f67920a04f3a62e90407cd1bf56c9ea`. Build performed no authenticated production QA.

## Previous Release (score freshness continuity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, Auto Deploy and public SHA checks passed. Authenticated live QA remains pending. |
| Goal | Keep Score 2.0 source freshness consistent between a score answer and an immediate FOMO follow-up, and prevent incomplete selector JSON from ending an otherwise valid turn, without replacing the model's coaching answer. |
| Candidate branch | `codex/finn-score-freshness-continuity`. |
| Candidate implementation SHA | `f8dd00a5e00e97299d432073cd12191be1faeedd` (score continuity `2cf327c6a39b04189ae85a8dd07149ecb6245e67`); status-only commit will have a later SHA. |
| Candidate merge SHA | `aa03bdd5399b916bdc8a47dd7d06b6a743464708` ([PR #132](https://github.com/gvangalen/antigravity-trading-tool/pull/132)). |
| Production SHA | `aa03bdd5399b916bdc8a47dd7d06b6a743464708`, observed on both public surfaces. This status-only update creates a later SHA; verify current identity before authenticated QA. |
| Previous live SHA | `9d5fd3e16e8f3166e54cfd5cebcf161075d05e2d`, independently tested with a contradictory same-day freshness explanation; confirmed strategy-rename continuation passed. |
| Last updated | 2026-10-09. |

The score read now distinguishes its daily report date from the UTC moment when FINN checked component-source freshness. That check moment is preserved with the verified evidence for the next turn. The model-led coach is told to re-read the score tool before making a new current-score claim; it may answer general FOMO coaching without a freshness claim. The selector's strict JSON budget was raised after two full regression runs each found an incomplete response on the same short MACD question. A single retry is allowed only for `incomplete_structured_response` without a provider refusal; the original schema and registry validation still apply. No fixed answer copy, action contract, scoring formula, bot execution, or trading permission changed.

[Candidate CI run 37973332390](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37973332390) and [main CI run 37973567473](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37973567473) passed all five jobs. [Auto Deploy run 37973734565](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37973734565) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` each returned HTTP 200 and SHA `aa03bdd5399b916bdc8a47dd7d06b6a743464708`. Build did not perform authenticated production QA. Independent QA should replay the score-read → FOMO follow-up on the deployed SHA, compare FINN's source moments with Analyse, and verify that an unavailable score still remains unknown rather than becoming stale or zero.

Measured local evidence so far: backend **3116 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command and proposal tests passed. `audit:high` exited successfully with one moderate Next.js advisory. The final worker-driven action matrix on the rebuilt API/Celery stack passed **16/16**, artifact `.local-finn-parity-artifacts/freshness-action-matrix-release.json` SHA-256 `e86b5b9c24be2f3a42b4caff7735f0456f2dec81d47cb18595465b011ca9ce9c`. A synthetic local real-provider Luna Responses probe read scores in the first turn and re-read them for **2/2** differently worded FOMO follow-ups; neither answer called the freshly checked scores stale or turned scores into a buy instruction. Artifact `.local-finn-parity-artifacts/freshness-followup-final.json` SHA-256 `245e8250331241fd658e475f4b695d08f17d32d885ae03b618ee3fe1279d2380`. The isolated API/Celery historical-score check passed **2/2 turns** against Score 2.0's current-only contract: a two-day-old stored row did not populate current scores or produce an entry signal. Artifact `.local-finn-parity-artifacts/freshness-date-runtime-final.json` SHA-256 `4b83268307edeebd41dcbe17765d84858ac59e5bb00d2f320d4d982eb52b3db9`. Two 109-case selector runs each had **108/109 operation matches** because `s609-02` returned incomplete structured output. A direct trace captured `response_status=incomplete`, `incomplete_reason=max_output_tokens`; another showed `response_status=completed` with invalid JSON. With the new bounded selector transport, that case passed **12/12** direct real-provider attempts. The final real-provider selector development passed **18/18**, artifact SHA-256 `b3eea83df15d0284fc3223614be30a1d28d86bbb8b06de979f33c7bf98d1578a`; regression passed **109/109** operation matches with zero provider, parse, schema, timeout or validation failures, artifact SHA-256 `1aac376abd93a4accbe4b22956842b5d013f5472fba8b0b28cae6a275e69018c`. The published `s609-16` still has no verified bot identity, so its separate conversation-reference and missing-input metrics are 108/109; no live-bot activation is inferred. A third diagnostic regression was blocked by the local per-case limiter after repeated targeted calls; the eval runner now isolates the limiter per run without changing production limits. The red diagnostic runs are retained, not counted as passes. There is no authenticated production QA claim for this candidate.

## Previous Release (confirmed strategy continuity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, Auto Deploy and public SHA checks passed. Independent authenticated live QA remains pending. |
| Goal | Preserve the confirmed strategy identity and verified rename across FINN follow-up turns; align daily score freshness with Score 2.0 and expose per-indicator source moments. |
| Candidate branch | `codex/finn-confirmed-action-continuity` ([PR #130](https://github.com/gvangalen/antigravity-trading-tool/pull/130), merged). |
| Candidate implementation SHA | `4fcafaa612ed438b6790e90b3d84c3467faf61a7`; candidate head also includes this status update. |
| Previous live SHA | `859b0e6feb129cfc38900324ba5225c10ba59e0c`, independently tested with a broken post-confirmation strategy reference and inconsistent freshness explanation. |
| Candidate merge SHA | `b0854580701e02a0bead70c33fa12f508fa51312`. |
| Production SHA | `b0854580701e02a0bead70c33fa12f508fa51312`, observed on both public surfaces. This status-only update creates a later SHA; check current public identity before live QA. |
| Last updated | 2026-10-09. |

The confirmed strategy postcondition now supplies the owner-scoped strategy and parent setup to the next read. A confirmed rename preserves the verified old and new names; fields still require a fresh saved-object read. The daily score tools compare a report **date** with the current UTC report date while Score 2.0 independently verifies each indicator source. Their typed result now carries the configured indicators' source moments. The model is asked to translate `fixed` to a user-facing fixed amount. This batch does not change bot execution or trading permissions.

Measured local evidence: backend **3111 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command and proposal tests passed. `audit:high` exited successfully with one moderate Next.js advisory. The isolated PostgreSQL/Redis/API/prefork-Celery action matrix passed **16/16**, including a new same-conversation read after a confirmed strategy update; zero production connections, broker orders, live trading calls and live bots. Artifact `.local-finn-parity-artifacts/finn-action-continuity-final.json`, SHA-256 `b65cfa70f39be8e2dc1af3478af641d0828e346d1d5446297aa53a617537bd34`. A separate local real-provider rename → confirmation → follow-up probe completed, read the owner-scoped strategy, and named both old and new strategy names; this is not production QA.

Real-provider Luna selector development passed **18/18**, artifact SHA-256 `381b11ccf2448b346c945ebab068098a474d7b88bce6741ec0cadcbf38aa12fc`. Regression passed **109/109**, artifact SHA-256 `bb89abc3cb8fc982834e93cf1502b0f9c81d8949378699f6ac003671affb6c92`. Both runs had zero provider, schema, parse, validation and timeout failures. The exact reason for the old live freshness contradiction cannot be proven without that run's trace; the new source moments and date semantics make the distinction testable in the next independent live run.

[Candidate CI run 37965385737](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37965385737) and [main CI run 37965609420](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37965609420) passed all five jobs. [Auto Deploy run 37965849977](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37965849977) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` each returned HTTP 200 and SHA `b0854580701e02a0bead70c33fa12f508fa51312`. Build performed no authenticated live QA.

## Previous Release (Luna internal-model unification)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, Auto Deploy and public SHA checks passed. Authenticated live acceptance remains pending. |
| Goal | Use Luna with reasoning `none` for FINN V2's remaining internal Responses calls, and remove redundant proposal and answer overrides that block valid coaching and drafts. |
| Candidate branch | `codex/finn-internal-model-unification` ([PR #128](https://github.com/gvangalen/antigravity-trading-tool/pull/128), merged). |
| Candidate implementation SHA | `bad6705616c61dd3c35ac906a0fc81c2762f95d9`; this status update will have a later SHA. |
| Candidate merge SHA | `18099031e4abee69535c309032a40f1e22fba4a8`. |
| Production SHA | `18099031e4abee69535c309032a40f1e22fba4a8`, observed on both public surfaces after successful Auto Deploy. This status-only update creates a later SHA; public identity must be checked again after its deployment. |
| Last updated | 2026-10-09. |

The FINN V2 auxiliary Responses classifiers, semantic verifier, hard-claim boundary, repair path and structured operation selector now use the configured Luna model and reasoning `none`. Proposal relevance checks only whether the user requested a persistent change; owner-scoped target resolution, contract validation and explicit confirmation remain the write boundary. An inconclusive auxiliary relevance call cannot veto a confirmation-gated draft. The answer boundary no longer treats a coach's question about which risk a rule should address as a promised trading outcome.

Measured local evidence on the isolated PostgreSQL/Redis/API/prefork-Celery stack: backend **3105 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command and proposal tests, and high-severity audit passed. The final worker-driven action matrix passed **16/16** with zero production connections, broker orders, live trading calls or live bots; artifact `.local-finn-parity-artifacts/full-action-matrix-final-verified.json`, SHA-256 `f68e7d6b2e7460d79ede50aa8e70c6b60a0383daa0a1713c1b108a141875a777`. Real-provider model-led coach gates passed **12/12 turns and 3/3 action lifecycles** on both baseline and alternate NL/EN/DE conversations; artifacts `.local-finn-parity-artifacts/model-led-coach-baseline-final.json` SHA-256 `d2181e71a5c3c79cd774d0da4163905c44a4833894df5578e0aed049b3caf423` and `.local-finn-parity-artifacts/model-led-coach-alternate-final.json` SHA-256 `60afb0b462e6dbe8213ec34458bae4992ed4cc99246246f836504576015e7be5`.

Real-provider selector development reached **18/18 operation matches** with zero provider, schema, parse, validation or timeout failures; artifact `.local-finn-parity-artifacts/selector-development-final.json`, SHA-256 `1bb1689d2286d5e994f27a1a377f513f4d6bf4d86d077e35ab59a1d90c2e5fc6`. Regression reached **109/109 operation matches**, with the same zero failure rates; artifact `.local-finn-parity-artifacts/selector-regression-rerun.json`, SHA-256 `6ee88d435d5bd6a071a1567f052cf34186f3b6f573f60f9447ee5b5dab9952d5`. Its conversation-reference and missing-input submetrics are **108/109**: published case `s609-16` asks to activate the “discussed bot” without a verified bot in the case context. The selector keeps `bot_id` missing instead of projecting an unverified target. This mismatch is recorded, not counted as a safe live-bot activation or a fully matching selector case.

Build has not performed authenticated production QA. After deployment, independent QA should verify the explicit saved-object mutation and multi-turn coach paths, effective model provenance where observable, and normal confirmation and Paper boundaries on the deployed SHA.

[Candidate CI run 37944002055](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37944002055) and [main CI run 37944248647](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37944248647) passed all five jobs. [Auto Deploy run 37944423808](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37944423808) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` each returned HTTP 200 and SHA `18099031e4abee69535c309032a40f1e22fba4a8`. Build performed no authenticated live QA.

## Previous Release (unified FINN batch)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; the unified FINN batch and its production migration repair passed candidate/main CI, Auto Deploy, and public backend/frontend SHA checks. Authenticated live acceptance remains pending. |
| Goal | Make FINN the only user-facing trading coach: retire unused legacy assistant, insight, reflection, and flow-registry paths; give chat, Today, reports, web, and mobile the shared FINN context; preserve Score 2.0 semantics and Paper-bot execution boundaries. |
| Candidate branch | `codex/finn-unify-deploy-migration` (repair on top of merged PR #125). |
| Candidate implementation SHA | Original batch `8a5f4d34e460cff80ca50d780013109112b09a36`; repair `5c7065be3e5e20e8aca64054c9d1f434a7e377c0`. |
| Candidate merge SHA | Final repair merge `22dcd339d034541686ff73f65687192cf4894f75`. |
| Production SHA | `22dcd339d034541686ff73f65687192cf4894f75`, observed on both public surfaces after the successful Auto Deploy. This status-only update creates a later SHA; public identity must be checked again after its deployment. The previous score-freshness candidate was superseded without a recorded authenticated QA verdict. |
| Last updated | 2026-10-09. |

Build removed the obsolete assistant service, gateway, insight endpoint and UI requests, unused flow registry, old reflection and insight tables, and stale assistant-only scripts. The active chat and action routes use FINN V2 visible delivery. Web and mobile read the FINN mission-control briefing rather than a separate insight generator. The existing deterministic bot worker and ScoreToolAdapter remain because they execute Paper decisions and read verified Score 2.0 evidence; they are not separate conversational agents. FINN Today and unified reports use Luna through Responses with reasoning `none`. Auxiliary operation selection and answer-boundary helpers still have separate model calls and are not represented here as a single Luna call.

Measured local evidence: root backend suite **3102 passed, 3 skipped** after the completed removal batch; frontend production build, typecheck, i18n lint/tests, command and proposal tests, and high-severity audit passed; mobile typecheck, lint, web/iOS/Android bundle smokes passed (lint emitted existing warnings). A fresh isolated PostgreSQL/Redis/API/prefork-Celery stack migrated without the retired tables. The worker-driven safe-action matrix passed **16/16** with zero broker orders, live trading calls, live bots, or production connections; artifact SHA-256 `51175b894912abd11f00db573c1299a77ab50e4119396f303dc8069ddd64921b`. Real-provider selector development passed **18/18**, artifact SHA-256 `413719de087d1f620b71cb892c4f721bbf947d637ec7173a70057b41bb23109a`; regression passed **109/109**, artifact SHA-256 `2bd8170692b257e46f29bf2d117ac81b9b7ec3af247088ce24e91edef708f095`. Both provider runs had zero provider, schema, parse, validation, or timeout failures. These measurements do not establish authenticated production behavior or an actual score-driven Paper decision.

[PR #125](https://github.com/gvangalen/antigravity-trading-tool/pull/125) merged after all five candidate CI jobs passed; [main CI run 37923006761](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37923006761) also passed all five jobs. [Auto Deploy run 37923169943](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37923169943) failed twice while dropping `ai_category_insights`: the old production view `ai_master_score_view` depends on that table. The deploy script attempted rollback; its output also reported `pm2: command not found` during rollback. Public backend health and frontend build-info afterward both returned HTTP 200 and the previous SHA `b758871848c71f3fbcbb8b21bd1298796e4f771e`. The repair explicitly drops the unused view before the table. A disposable PostgreSQL instance with the same table/view dependency completed that migration, removed both objects, and passed a second idempotent run. The root backend suite passed again (**3102 passed, 3 skipped**), and the canonical migration plan validator passed.

The repair passed all five jobs in [candidate CI run 37923588806](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37923588806). [PR #126](https://github.com/gvangalen/antigravity-trading-tool/pull/126) merged it; [main CI run 37923841838](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37923841838) passed all five jobs. [Auto Deploy run 37924024458](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37924024458) succeeded. Public backend health and frontend build-info each returned HTTP 200 and SHA `22dcd339d034541686ff73f65687192cf4894f75`. Build performed no authenticated production QA.

Independent QA, after deployment and user initiation, should test a new-owner onboarding path through FINN Today, chat, saved plans, dated Score 2.0 evidence and daily/period reports; verify no old insight card appears in web or mobile. Check incomplete and complete benchmark cases, one controlled Paper decision, and that actions still require confirmation. No live order. Build did not access the protected QA fixture or sealed holdout.

## Previous Release (score freshness parity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate and main CI passed, Auto Deploy succeeded, and backend/frontend public endpoints reported the merge SHA. Authenticated live acceptance remains pending. |
| Goal | Align per-indicator source freshness in Analyse and FINN, show verified score contributions consistently, localize RSI explanation, and distinguish no bot evaluation from data refresh. |
| Candidate branch | `codex/score-freshness-parity`. |
| Candidate implementation SHA | `45b990afb2aca26698ca4be49593fa1870f3367a`. |
| Candidate merge SHA | `36066457fcd9ace139d174425dc6f4c4fa314425`. |
| Production SHA | `36066457fcd9ace139d174425dc6f4c4fa314425`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; public identity must be checked again after its deployment. |
| Production SHA before this candidate | `7268ebe8403e70713f88f300ea221ee0c761a1d9`, as reported by independent authenticated QA. |
| Last updated | 2026-10-08. |

Independent QA on the previous SHA confirmed that a new ETH owner receives measured Price, DXY and RSI scores (Market 30, Macro 20, Technical 40, combined 30). The setup correctly did not match because Macro 20 was below its saved floor of 30. QA also found that Analyse called the RSI source current while FINN called the same observation stale; the DXY and RSI detail cards showed no score contribution beside visible category scores; the RSI detail was English in Dutch UI. The new manual Paper bot had no completed decision, so a positive score-driven Paper decision remains unproved.

Code inspection found a six-hour FINN technical-tool TTL against Score 2.0's 36-hour closed-crypto-candle window, string-only timestamp matching for workspace evidence, a frontend contribution read from a different field than its displayed score, hardcoded English RSI explanation, and a bot-card fallback that said data was updating before any decision ran. The candidate uses the shared source-age policy, normalizes UTC evidence moments, derives the visible contribution from verified daily evidence, localizes RSI in all supported languages and labels the no-decision state accurately. It does not change order or bot execution logic.

Measured local evidence on the candidate: root backend suite **3217 passed, 3 skipped**; frontend production build, typecheck, i18n lint/tests, command and proposal tests, and high-severity dependency audit passed. The isolated PostgreSQL/Redis/API/prefork-Celery safe-action matrix passed **16/16**, with zero broker orders, live trading calls, live bots or production connections; artifact SHA-256 `b9f6f34ae4d26544b242ef91cada5ed99d558df2fb03e6bd011023ad73b98426`. Real-provider selector development passed **18/18**, SHA-256 `819fad5b2146f6cd25b20a3596ed1ac1378042e57cb797bb6707b7821f99441c`; regression passed **109/109**, SHA-256 `0cd8ad80b6843603feaede35492177ddad266dd0e68dc65d8d6c362658c75b9c`, both with zero provider, schema, parse, validation or timeout failures. The action matrix completed before the final workspace-only freshness alignment; focused and full backend tests passed afterward. These measurements do not establish production UI parity or an actual Paper decision.

[Candidate CI run 37839499742](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37839499742) and [main CI run 37839789148](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37839789148) each passed all five jobs. [Auto Deploy run 37840033781](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37840033781) succeeded. Public backend health and frontend build-info both returned HTTP 200 and SHA `36066457fcd9ace139d174425dc6f4c4fa314425`. Build performed no authenticated production QA.

Independent QA should repeat the new-owner ETH Price/DXY/RSI flow and compare the *same source observation* in Analyse and FINN. Check each indicator's contribution and NL/EN/DE explanation, plus the bot's initial no-decision label. A positive score-driven Paper decision remains a separate controlled test requiring a matching setup and an actual evaluation run; never infer it from a newly created manual bot.

## Previous Release (indicator history recovery)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; [PR #121](https://github.com/gvangalen/antigravity-trading-tool/pull/121) merged, candidate and main CI passed, Auto Deploy succeeded, and both public surfaces reported the deployed SHA. Authenticated live acceptance remains pending. |
| Goal | Start owner-scoped DXY and RSI history recovery when a preference is saved; fetch enough closed ETH candles for RSI and materialize the indicator before rebuilding scores. |
| Candidate branch | `codex/indicator-history-new-owner`. |
| Candidate implementation SHA | `90b3a426` (includes the direct RSI-add route and crypto-only candle recovery; release evidence commit follows). |
| Candidate merge SHA | `501d1f784f6ae9e9b4dddfbddc822f5a1815f225`. |
| Production SHA | `501d1f784f6ae9e9b4dddfbddc822f5a1815f225`, observed on backend and frontend after Auto Deploy. This status-only update creates a later SHA; public identity must be checked again after its deployment. |
| Production SHA before this candidate | `7df6cd6def5638b8af06f40b1dc7572a669adbdd`, confirmed by the user-provided authenticated browser QA. |
| Last updated | 2026-10-08. |

The authenticated new-owner QA on `7df6cd6` found ETH Price 5/5 and Market 30, but DXY 1/5 and RSI without a measurement; the combined benchmark and setup match remained unknown and the Paper bot made no decision. Read-only production worker logs showed that the hourly history job ran, but no targeted history job was queued by the `PUT /macro/preferences` or `PUT /technical/preferences` routes used by onboarding. The hourly sweep is limited to four scopes. Code inspection found that market history stopped at five closed source days even when crypto RSI required 15. This release repairs the configuration-to-worker handoff and makes RSI request 15 closed days. A source or materialization failure leaves a missing score unknown and records a safe reason for retry.

Local evidence: root backend suite **3214 passed, 3 skipped**, log SHA-256 `2719cd9b569c56a61b7b0457f676e750e5543fa7826dc3344c9a9b39135c937c`; frontend build, typecheck, i18n lint/tests, command/proposal tests and high-severity audit passed; mobile typecheck passed. The isolated PostgreSQL/Redis/API/Celery action matrix passed **16/16** with no broker order or live trading call, artifact SHA-256 `15941e21048c937d79c19ad2590e41eb2d0bf8876c6c7817a4855c06a770fcb4`. This matrix preceded the final direct-POST dispatch and crypto-only scoping additions; their targeted API regressions and the full backend suite passed afterward. A synthetic new-owner run using real dated ETH and direct DXY source routes yielded 63 DXY source days, a measured RSI with no pending owner, and after a normal Price refresh verified Market 30, Macro 20 and Technical 40. Real-provider selector development passed **18/18**, artifact SHA-256 `9d3b3c9b2f9eb67e83dacdc7216f3250db8295f701d870e9763bba035e4324ae`; full regression passed **109/109** with zero provider, schema, parse, validation or timeout failures, artifact SHA-256 `a830af17b9ae7e138399a324c9c32519fdbdf4b1249d9c74753f022327c68439`. [Candidate CI run 37832858087](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37832858087) and [main CI run 37833181571](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37833181571) passed all five jobs. [Auto Deploy run 37833369907](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37833369907) succeeded. Backend health and frontend build-info both returned HTTP 200 and SHA `501d1f784f6ae9e9b4dddfbddc822f5a1815f225`. Build performed no authenticated live acceptance. These local measurements do not prove a live positive setup match or Paper decision.

Independent QA should create a new owner, select ETH Price/DXY/RSI, and observe the targeted recovery after preference save. Compare dated source evidence and scores in Analyse and FINN; the three components should either agree or show a specific unavailable state. Only if all sources are fresh should QA examine a positive setup match and a controlled Paper decision; no live order. Build does not use the protected QA fixture.

## Previous Release (score source adapters)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; [PR #119](https://github.com/gvangalen/antigravity-trading-tool/pull/119) merged, candidate and main CI passed, Auto Deploy succeeded, and both public surfaces reported the deployed SHA. Authenticated live acceptance is pending. |
| Goal | Supply real dated DXY index history and crypto RSI from shared completed market candles, preserve source provenance, and expose pending-source failure reasons so fresh owners can obtain complete Score 2.0 components. |
| Candidate branch | `codex/score-source-diagnostics`. |
| Candidate implementation SHA | `7d543f75` (includes source changes, rollback separation and the aligned isolated action fixture); release evidence commit `5d2c4358`. |
| Candidate merge SHA | `74a8c724ecf39125115aea4712a0810784acc188`. |
| Production SHA | `74a8c724ecf39125115aea4712a0810784acc188`, observed on backend and frontend after Auto Deploy. This status-only update creates a later SHA; public identity must be checked again after its deployment. |
| Production SHA before this candidate | Public backend health and frontend build-info both reported `ec63e300efa85d633b8b643fd190114b9079417b` with HTTP 200 during this Build turn. |
| Last updated | 2026-10-08. |

The preceding authenticated QA run on `2d1b5950` confirmed a new ETH owner could save a profile and select Price, DXY and RSI. Market scored 30 on 5/5 genuine source days, while DXY had 0/5 and RSI no measurement, leaving Macro, Technical and the combined benchmark unknown. This candidate addresses those missing source paths without manufacturing scores. DXY now uses one direct index time series for both current and historical readings; old derived-basket rows remain separately archived. Crypto RSI first uses completed dated market candles already shared by Score 2.0. Source failures retain a safe category/code in worker diagnostics. A production-positive score, setup match or Paper decision has not yet been observed for this candidate.

Measured local evidence: root backend suite **3208 passed, 3 skipped**; frontend build, typecheck, i18n lint/tests, command/proposal/setup tests and high-severity audit passed; mobile typecheck and migration-plan validation passed. The isolated PostgreSQL/Redis/API/Celery action chain passed **16/16**, with zero live bots or non-allowlisted executions after the chain; artifact SHA-256 `1bc8890ee641e3158184075fe5ddef37aff442a9cd0c0e9f151b371e6208e8b1`. Direct DXY history was reachable from the isolated worker and returned 63 genuinely dated closes, last on 2026-10-07. Real-provider selector development passed **18/18**, artifact SHA-256 `aa36d9da2aa088904b2262d01a8dc78b46a42bbe8e4d901f583d87395e7526a4`. A first full regression scored **107/109**, including one provider failure; the sequential complete rerun passed **109/109** with zero provider, schema, timeout, parse or validation failures, artifact SHA-256 `f4af93ef3908a52ca7b48bf53c9477f2c8cee2dc60ec0caf6de385ddcc98bfb8`. The separate 37-case nonsealed diagnostic matrix failed because its original DCA action fixture omitted the now-required amount and its read probes expect legacy operation IDs for freeform answers; this diagnostic is not claimed green. [Candidate CI run 37817577570](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37817577570) and [main CI run 37817832298](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37817832298) each passed all five jobs. [Auto Deploy run 37818042898](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37818042898) succeeded. Backend health and frontend build-info both returned HTTP 200 and SHA `74a8c724ecf39125115aea4712a0810784acc188`. Build performed no authenticated live acceptance.

Independent QA should create a fresh owner, configure ETH Price/DXY/RSI, wait for genuine dated history and an actual rebuild, and compare each indicator's source day, rule and score across Analyse, FINN and the daily report. Confirm that Market, Macro, Technical and the weighted benchmark are either all correctly evidenced or explicitly unavailable, never zero by default. Only with complete fresh data, test one positive setup match and one controlled Paper decision; no live order. Verify old derived DXY measurements do not enter the new direct-index normalization and that a failed source remains pending without a fictitious score.

## Previous Release (current-score parity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; [PR #118](https://github.com/gvangalen/antigravity-trading-tool/pull/118) merged, all CI jobs and Auto Deploy passed, and both public surfaces reported the deployed SHA. Authenticated live acceptance is pending. |
| Goal | Repair the new-account profile loading race and make FINN and Analyse use the same verified current Score 2.0 components and indicator evidence. |
| Candidate branch | `codex/score-qa-followup`. |
| Candidate implementation SHA | `104e8a73` (the release-status commit follows this implementation commit). |
| Candidate merge SHA | `ec63e300efa85d633b8b643fd190114b9079417b`. |
| Production SHA | `899b4fbb093e7cfaf627fdaa556e51ea6d55bec4`, observed on backend and frontend after deployment. This status-only update creates a later SHA; public identity must be checked again after its deployment. |
| Production SHA before this candidate | `db89ca94e45459ad11ec92a1a5df73092918d954`, measured as HTTP 200 on both public surfaces on 2026-10-08. |
| Last updated | 2026-10-08. |

The user-provided authenticated browser check on `db89ca94` found that a new account could not pass profile onboarding because choices appeared unresponsive and Save stayed disabled. Build inspected the already open tab without submitting or saving, clicked all six required choices and observed Save become enabled with no browser errors, then reset the choices; that exact click failure did not reproduce. The code did reveal two ways a slow preferences request could strand the form: a late response overwrote choices made in the meantime, and the request's loading flag disabled Save even after all required choices were set. Both paths are repaired, and selected buttons expose `aria-pressed`.

[Candidate CI run 37797515860](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37797515860) and [main CI run 37798271113](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37798271113) each passed all five jobs. The API merge and a status push did not start the normal main-CI event, so `workflow_dispatch` was added to the existing CI workflow, validated with actionlint, and used to run main CI on `899b4fbb`. [Auto Deploy run 37798507546](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37798507546) completed success. Public backend health and frontend build-info both returned HTTP 200 and SHA `899b4fbb093e7cfaf627fdaa556e51ea6d55bec4`. Build performed no authenticated live acceptance.

The same browser report showed Analyse withholding an unverified ETH Market score while FINN still mentioned a dated stored “Market 30.” The current-score tool now uses the owner-scoped source verification behind Analyse; stale components return null with a reason. A separate saved-score tool preserves explicit historical report reads. Market-price snapshots no longer carry a saved score. Analyse's daily indicator rows now project the verified weighted indicator evidence saved by Score 2.0, rather than older row score fields. Other display periods retain measurements but show no unverified legacy score. Five dated Price days alone still do not prove a score if another configured source or the rule-based rebuild is incomplete.

Measured local Build evidence at `104e8a73`: root pytest **3202 passed, 3 skipped**, log SHA-256 `0587ad0b9295508ea7b8908402276a3c0e184c0cdefe7912693f380d7b410a48`; frontend build, typecheck, i18n lint/tests, command/proposal/setup tests and high-severity dependency audit passed (one moderate Next.js advisory remains). Mobile typecheck passed. The isolated PostgreSQL/Redis/API/Celery action matrix passed **16/16**, with zero broker orders, live trading calls or production connections, artifact SHA-256 `ff388192373baf9a2f0f3dcd54b4f7832c5f3985f7e90b0d5f30285eaedf6bc1`. Real Responses selector development passed **18/18**, artifact SHA-256 `2a77425f88b9950232958670c1d6e75cde4b08cb91489203accf0dc9fdfbcfb2`; regression passed **109/109**, artifact SHA-256 `a9412b9f248b2662d823eee7bf0e92eea0c53e2a1eebd9d5e443d85e7213d64b`, with zero provider, schema, parse, validation or timeout failures. The selector implementation did not change after those provider runs. The isolated stack was stopped after validation.

Independent QA must retest a genuinely new account, including a slow preferences response and successful profile save; compare current ETH scores and individual indicator detail in Analyse with FINN without historical-score leakage; and separately ask for a dated historical report. Record why Price with 5/5 source days is still unscored if the rebuild remains incomplete. A positive benchmark/setup match and controlled Paper decision remain unproven until all configured sources are genuinely complete and fresh. Build has not accessed the protected QA fixture or sealed holdout and has not run authenticated live acceptance.

## Previous Release (Score 2.0 source history bootstrap)

| Field | Value |
| --- | --- |
| Phase | `NOT_ACCEPTED` in the user-provided browser run on `db89ca94`: profile onboarding was blocked and FINN mentioned a stale stored score that Analyse withheld. |
| Goal | Complete Score 2.0 indicator history bootstrap and explicit score rules so a new owner can use genuine existing source days without waiting five days after registration. |
| Candidate branch | `codex/score-history-bootstrap`. |
| Candidate implementation SHA | `c26c676cb54f5b3d1577f40e632d12d0996a70e6` plus release-status commit `d4fc5cc9`; merged as `ac5b70d307c7aa4f0b9682ad5394487139a2f561`. A later status-only commit will create a new SHA without changing score behavior. |
| Production SHA | `ac5b70d307c7aa4f0b9682ad5394487139a2f561`, observed on both public health/build-info surfaces after Auto Deploy. |
| Previous live SHA | `45775a219aba597f74de26c6f92c0c0ebfb5864c`, independently tested before this release. |
| Last updated | 2026-10-08. |

The candidate backfills only genuinely dated, completed Price/Volume and absolute macro observations, rejects generated bucket fallbacks as scores, installs explicit system templates where missing, explains insufficient history in Analyse, and queues an owner score rebuild after history becomes sufficient. A newly configured owner also gets a rebuild when that asset's shared market history was already complete. The prior report fact-parity release remains awaiting its own authenticated QA; this Score 2.0 goal does not count as report acceptance.

Measured local evidence at implementation SHA `c26c676c`: root pytest **3197 passed, 3 skipped**. Frontend production build, typecheck, i18n lint/tests, command and proposal tests, and `audit:high` passed; mobile typecheck passed. The isolated PostgreSQL/Redis/API/Celery action matrix passed **16/16**, with zero production connections or broker orders, artifact SHA-256 `dd3d064a555c9ffe5a485efe4beb50b5fc29bbb643d88b0e1a159aae6c4f5514`. Real Responses selector development passed **18/18**, artifact SHA-256 `1970ccb1be76c4f22e59274ab43beff2cbaffd1723b634cb59a178342a21bf95`; regression passed **109/109**, artifact SHA-256 `a36c8566ad310c9d69a39fbfe808939b9eac9fad17d55472caa2f2030ed1f312`. Both reported zero provider, schema, parse and validation failures. The isolated migration plan validator passed. [Candidate CI run 37781959643](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37781959643) and [main CI run 37782332086](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37782332086) passed all five jobs. [Auto Deploy run 37782581346](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37782581346) succeeded. Public backend health and frontend build-info both returned HTTP 200 and SHA `ac5b70d307c7aa4f0b9682ad5394487139a2f561`. The later `db89ca94` browser run is summarized in the active repair release above.

A direct local DXY history fetch returned Twelve Data HTTP 429 because its daily API-credit limit was exhausted. The branch retains an unavailable Macro score and retries later; it does not prove that five DXY days or a positive benchmark will be available to a new production account today. Independent QA must test a fresh account after deployment, record each indicator's dated-day count and rule origin, compare Analyse/FINN/benchmark, and separately verify any positive setup match and controlled Paper decision only when all sources are genuinely fresh. No live order is part of this release.

## Previous Release (report fact parity)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, Auto Deploy and public SHA checks passed. Authenticated report fact-parity QA remains open. |
| Goal | Make daily report score and saved-plan facts agree with Analyse, FINN chat and the owner-scoped shared context. |
| Candidate branch | `codex/finn-report-facts-parity`. |
| Candidate implementation SHA | `45fc260fbb545ef1cf381294f0eb6634c795c203` in [PR #114](https://github.com/gvangalen/antigravity-trading-tool/pull/114), merged. |
| Production SHA | `b89e69262c2b9b12f3af2ae9a55cf67c2418dc83`, observed on both public surfaces after Auto Deploy. A status-only commit will create a later SHA; QA must bind to the current backend/frontend SHA. |
| Previous live SHA | `6d6913ec6236e7695c362d606d65011e3bd02b08`, independently tested and not accepted for report fact parity. |
| Last updated | 2026-10-08. |

Independent browser QA completed new-account onboarding with ETH monthly DCA, a linked €120 strategy and a Paper bot. FINN Today transitioned from a temporary summary to a stored personal briefing that persisted after refresh and genuine relogin. Analyse and FINN chat correctly showed insufficient market, macro and technical scores. The daily report contradicted them by calling market 10/100 and technical 50/100 current and denying a saved strategy and indicator configuration. The positive fresh-score and Paper execution paths remain unproven. This is a `NOT_ACCEPTED` fact-parity result for that release, not a provider identity trace.

Build traced the discrepancy to three report-path faults. The writer passed raw `reported_scores` into Luna even when source status rejected those values. It always stored `active_strategy=None` and empty indicator highlights. The shared context also called Pydantic-v2-only `model_dump()` on the deployed v1 indicator schema, caught the resulting exception and silently labelled a successful configuration lookup unknown. The repair projects only fresh component scores into report input and output, serializes the real indicator schema through FastAPI's version-compatible encoder, writes owner-scoped strategy and indicator facts, and uses typed report sections for score/configuration claims. FINN chat answer control is unchanged.

Measured local evidence: root pytest **3184 passed, 3 skipped**, log SHA-256 `1224074359f9f195c6aee503d826cc7ab16751eaeb148cb779ef09d20c043264`. Frontend production build, typecheck, i18n lint/tests, command/proposal tests and `audit:high` passed. The isolated PostgreSQL/Redis/API/Celery action matrix passed **16/16**, no broker orders, live calls, live bots or production connections; artifact SHA-256 `957b47baab5b40921f44f1b5e7fa13242c6613f88a6546480ddaa0c30a9a4502`. Real-provider selector development passed **18/18**, artifact SHA-256 `af6a66304fd5af49c1a863fcfa167388203d5983b499be1ddcec184f3bece7e0`; regression passed **109/109**, artifact SHA-256 `4f2f1fdfd2543c939159ce82ccd6159b6d3fe091fd8249b7d5a3644db830fc84`, with zero provider/schema/parse/validation failures. A direct local Luna Responses report over a synthetic database user produced eight nonempty sections, retained configured indicators and saved strategy facts, and kept unverified scalar scores null. The local bootstrap `daily_reports` table lacks historical production report columns, so a direct SQL persistence probe failed with `UndefinedColumn`; the task-to-repository mapping is covered by the focused regression, but the local SQL persistence path is not claimed green. [Candidate CI run 37729841454](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37729841454) and [main CI run 37730025495](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37730025495) passed all five jobs. [Auto Deploy run 37730172154](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37730172154) succeeded. Public backend health and frontend build-info both returned HTTP 200 and SHA `b89e69262c2b9b12f3af2ae9a55cf67c2418dc83`. Independent authenticated QA remains pending.

Independent QA should generate a **new** report after deployment (an older persisted report is not silently rewritten), then compare the same account's Price/DXY/RSI configuration, linked strategy and per-component score freshness in Analyse, FINN chat and the report. With incomplete scores the report must not call raw 10/50 values current or deny configured indicators and saved strategies. The saved report card should distinguish a stored strategy from a current entry signal. Positive fresh-score and Paper decision paths remain separate, unproven acceptance checks. Build did not access the protected QA fixture or sealed holdout.

## Previous Release (unified FINN onboarding and reports)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; candidate/main CI, merge, Auto Deploy and public SHA checks passed. Authenticated QA remains open. |
| Goal | Replace the separate onboarding/report AI-agent chain with one owner-scoped FINN context, retain measured scoring and Paper execution, and use Luna Responses for FINN Today and reports. |
| Candidate branch | `codex/finn-unified-onboarding`. |
| Candidate implementation SHA | `c94eabf5` plus tracked frontend export commit `cb97ab6c` in [PR #112](https://github.com/gvangalen/antigravity-trading-tool/pull/112), merged. |
| Production SHA | `4d6f4e720a61a4f08989844b3cc238e8a58931ef`, observed on both public surfaces after Auto Deploy. This status-only update will create a later SHA; QA must bind to the current backend/frontend SHA. |
| Last updated | 2026-10-07. |

Build replaced the old onboarding sequence of specialist AI interpretations with measured score tasks, a shared owner-scoped context and one FINN briefing. FINN chat, Today and daily/period reports now use that context or its benchmark service. Daily and period report prose uses `gpt-6-luna` with reasoning `none` via Responses. Saved strategy fields, rather than a separate generated daily strategy snapshot, feed current Paper decisions. The former macro, market, technical, score, strategy and report AI-agent modules and their unused schedules were removed. The older standalone strategy-analysis endpoint and button were removed; strategy cards retain FINN review. Deterministic source collection, score calculation, setup match, report storage and bot safety controls remain. Historical backtesting still reads historical strategy snapshots; this release does not claim point-in-time backtest migration.

Measured local evidence on isolated PostgreSQL/Redis/API/Celery: root pytest **3181 passed, 3 skipped**, log SHA-256 `764c8c3514234fa28aa8bbea3f8ee5ae81a6e440e30efb65a4244ed2cde92813`. Frontend build, typecheck, i18n lint/tests, command/proposal tests and `audit:high` passed, log SHA-256 `ca9a799af236c02b0b7eb36aa77b1becf64feb067fe3d83c83ad8844308f5942`. The complete local worker-driven FINN action-contract matrix passed **16/16**, with zero broker orders, live trading calls, live bots or production connections; artifact SHA-256 `b26b69d31ee20fc36fa043c68bfd0e143d713ee469d429f99f0d3e9e3dfd7b2b`. Real-provider selector development passed **18/18**, artifact SHA-256 `0be2547579d19f6a5468b04171b6569919586670df7b376580224bb09e152b9e`; full regression passed **109/109**, artifact SHA-256 `069f9fc50e2ec1d904a4af4ac2b5ffaf9d6d0c0ab74a081a5146a9e84d07b670`. A synthetic completed-onboarding account generated and persisted a first Today briefing with `response_source=ai_generated` and Luna usage recorded; synthetic daily and weekly reports produced eight nonempty sections each using Luna. A local Paper-bot decision completed safely on `hold` with no order. These local probes do not establish the cause of earlier production fallbacks or constitute independent live acceptance.

Independent QA should create a new account, complete onboarding and inspect the first briefing's visible `response_source`, `generation_status` and stable saved text after refresh/relogin. Compare the same owner profile, plans and current score status in FINN chat, Today and daily/weekly reports. Test missing and fresh source evidence separately, then one controlled Paper decision; do not place a live order. Verify Dutch, English and German onboarding text and that strategy cards open FINN review without the retired endpoint. Build did not access the protected QA fixture or sealed holdout.

Candidate [CI run 37686545359](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37686545359) and [main CI run 37686811742](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37686811742) passed all five jobs. [Auto Deploy run 37687051695](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37687051695) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` both returned HTTP 200 and SHA `4d6f4e720a61a4f08989844b3cc238e8a58931ef`. The first candidate CI run failed only the tracked frontend export check; the export was committed and the subsequent candidate run was fully green.

## Previous Release (logout and onboarding locale)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; local gates, candidate/main CI, Auto Deploy and public SHA checks passed. Authenticated browser QA is pending. |
| Goal | Finish the new-user onboarding handoff by making logout a verified server operation and completing locale-specific onboarding copy in Dutch, English, and German. |
| Candidate branch | `codex/onboarding-logout-i18n`. |
| Candidate implementation SHA | `be610f60` in [PR #110](https://github.com/gvangalen/antigravity-trading-tool/pull/110), merged. |
| Production SHA | `9195019257d5a57270944611bc0d8d86df3e1e87`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current backend/frontend SHA. |
| Previous live SHA | `db60d6ea2996a6a835d01eb3dfe92df63163e5e3`, independently tested with a new account. |
| Last updated | 2026-10-07 |

Independent QA on the previous live SHA confirmed a temporary-to-saved FINN Today briefing transition in about 15 seconds, a factually personal stored briefing, and identical final text after a hard refresh. The QA account's ETH monthly day-5 DCA setup, €120 strategy and Paper bot persisted, and onboarding reached 4/4. Logout did not hold in the browser: the same account returned after refresh without a new password, so the saved briefing was not checked after a genuine relogin. Dutch onboarding still displayed “Launch protocol”, “Profile”, “analysis-basis” and “Create bot”. The QA observation does not reveal the logout HTTP status or cookie trace.

Code inspection found that both logout buttons always displayed success and navigated to login, even if the logout request failed. The AuthProvider also erased local state before checking the server response. A surviving HttpOnly auth cookie could therefore restore the same account on refresh. This batch sends logout before clearing local state, bootstraps the existing CSRF cookie when needed, and checks that a fresh `/auth/me` request returns 401 before claiming browser logout. A failed request or surviving cookie leaves the visible session in place with localized failure feedback. The provider also aborts and versions in-flight session checks so an earlier response cannot rehydrate the user after verified logout. Native logout passes its refresh token for revocation. No backend cookie contract was changed, and the exact production failure cause remains unproven without its HTTP trace.

The Dutch onboarding dictionary now covers the reported English labels and related profile, analysis, plan and bot copy. Previously missing bot-step and banner keys were added for all three supported locales, so the screens do not need their English fallback strings for those labels. Locale switching still uses the existing immediate `setLocale`/dictionary path.

Measured local evidence: root pytest **3173 passed, 3 skipped**, final log SHA-256 `a4cf77c0edd6eb8ff0e8258e5ff4b0bab9e9182189ceb985e747d811bd948524`; final frontend build, typecheck, i18n lint/tests, command/proposal tests, focused logout/locale tests, and canonical `audit:high` passed, final build log SHA-256 `6f5ae978c73139bd15f2b8331b20ac6b1f54129d88f863f98c74e96b0a6f98ab`. Isolated PostgreSQL/Redis/API/Celery action-contract matrix passed **16/16**, zero broker orders, live calls or production connections; artifact SHA-256 `2efdeb55c17de20ad8e0db1891c404a56e850c2968a8b8dfb4e995165f8eeda1`. With two separate synthetic accounts on that local API, login and `/me` returned 200, a valid-CSRF logout changed `/me` to 401, and a missing-CSRF logout returned 403 while `/me` stayed 200; a later valid logout cleared that session. Real-provider selector development passed **18/18**, zero provider/schema/parse/validation failures, artifact SHA-256 `7acb05e944824fb83e15e428aef08ebfc71fb4a3f583e77ce57bc20c7da59cdf`. Full regression passed **109/109** with zero provider/schema/parse/validation failures, artifact SHA-256 `78d7db0dfb1d174455b4a2acf1d123ed953d15ec9483af675dc142256265c982`. Build did not access the protected QA fixture or sealed holdout.

Independent QA should sign out from both the avatar menu and profile on a new account, confirm the login page remains logged out after hard refresh and protected navigation, then genuinely log back in and compare the saved FINN Today text. In Dutch, inspect the onboarding shell, analysis, plan, bot and completion screens for untranslated copy; switch to English and German and verify the same labels update immediately. A deliberately failed logout must show an error without falsely reporting success. No live trade is part of this handoff.

Candidate [CI run 37675373786](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37675373786) passed all five checks. Main [CI run 37675671071](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37675671071) passed, and [Auto Deploy run 37675927007](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37675927007) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` both returned HTTP 200 and SHA `9195019257d5a57270944611bc0d8d86df3e1e87`. Build performed no authenticated production QA or production write.

## Previous Release (first FINN Today briefing stability)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ACCEPTED`; independent new-account QA confirmed the temporary-to-saved briefing transition and hard-refresh stability, but could not finish a genuine relogin because logout did not hold. Onboarding copy also remained partly English. |
| Goal | Make the first FINN Today briefing source and generation phase visible on compact and full cards, prevent a stale browser copy from appearing on refresh, and finish the reported Dutch onboarding labels. |
| Candidate branch | `codex/first-briefing-stability`. |
| Candidate implementation SHA | `a531bb98` in [PR #108](https://github.com/gvangalen/antigravity-trading-tool/pull/108), merged. |
| Production SHA | `c27e7c67d4dd191df8e780e9a3fba2a987b1cfc1`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current backend/frontend SHA. |
| Previous live SHA | `626744a8fce6b591375874b08e6c2e9d12f71ccf`, independently tested with a new account. |
| Last updated | 2026-10-07 |

Independent live QA on the previous SHA found that the saved DXY/RSI status, monthly day-5 DCA cadence, Paper bot, refresh/relogin persistence, onboarding completion, and Automation route worked. The first FINN Today text was personal and factually consistent, but after refresh the visible card changed from a plan summary to differently worded personal copy. QA could not observe `response_source` or `generation_status` from the UI, so it did not establish whether the latter text was a stored AI briefing or why the transition occurred. Dutch onboarding still showed “Automation” and “Guided onboarding”.

Code inspection shows that the backend intentionally presents deterministic plan copy during `pending`, `queued`, `generating`, and retry states, then the stored AI result at `ready`; it reuses a ready result when its context version matches. The compact FINN Today card did not label these phases. The browser session cache also stored interim and ready first-dashboard responses, which could reappear before the server's current response on refresh. A separate cached insight could briefly fill the compact card before Mission Control loaded. This batch makes the source phase visible in both card views, treats the server's owner-scoped record as the only cache for the first dashboard briefing, and shows a loading state rather than an unrelated insight while the completed account awaits Mission Control. It also supplies the missing Dutch onboarding shell translation and translates the reported navigation and step labels. It does not change the coach's generated answer or claim a specific provider/queue error in the live QA run.

Measured local evidence: root pytest **3173 passed, 3 skipped**, log SHA-256 `5b395ce166d59a3938a9fb5b7ae0685e2373257372aaa0e4b6e29abf8c26cf8f`; frontend build, typecheck, i18n lint/tests, command/proposal tests, focused source-phase/cache/translation tests, and canonical `audit:high` passed, final build log SHA-256 `3664d822a9b5fe2b4a80b2ff0884b81a13d1fa9e2cef6206b444710a793faba3`. Isolated PostgreSQL/Redis/API/Celery action-contract matrix passed **16/16**, with zero broker orders or live calls, artifact SHA-256 `6cf51eba176431b8636d64d71a4491762f0240537a833c0d03f57de7c57f1153`. Real-provider selector development passed **18/18**, SHA-256 `adabcabdbedc147bb9d08ee5fa64956249b8db54c0d1362dbb2e5b5e1d5e9e8a`. The first regression run, concurrent with the action matrix, scored **108/109**: the general plan-audit case `reg-qa-plan-audit-variant` was selected as `evaluate_setup` instead of `evaluate_plan`; provider, schema, parse, and validation failure rates were zero. This red run remains recorded, artifact SHA-256 `d3d83586840aff7a11f9793274accb33f62ee0c0ca9dd378add2bf7061e4dd9c`. The clean sequential full regression passed **109/109**, with zero provider, schema, parse, or validation failures; artifact SHA-256 `3ab86fbd1d16fcb77e77ced045110e08d5dfcb35576c7d098eac1b347826ebd8`. Build has not accessed the QA fixture or sealed holdout.

Independent QA should check the initial temporary label, the transition to the saved-personal-briefing label, and identical saved text on refresh/relogin while the owner plan and evidence remain unchanged. If the saved text changes, capture the displayed phase before and after; a changed context can legitimately require regeneration, while a changed ready result for the same context is a defect. Verify Dutch onboarding shell, navigation and step labels. Build does not access the authenticated QA fixture.

Candidate [CI run 37669378288](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37669378288) passed all five checks. Main [CI run 37669644264](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37669644264) passed, and [Auto Deploy run 37669868130](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37669868130) succeeded. Public `https://tradamind.com/api/health` and `https://tradamind.com/build-info.json` both returned HTTP 200 and SHA `c27e7c67d4dd191df8e780e9a3fba2a987b1cfc1`. No authenticated Build QA or production write was performed.

## Previous Release (indicator configuration and DCA cadence)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ACCEPTED`; fresh-account browser QA on `626744a8fce6b591375874b08e6c2e9d12f71ccf` passed the indicator, DCA cadence, Paper bot, persistence and Automation route checks, but could not verify the first briefing's source/stability and found Dutch copy remnants. |
| Goal | Distinguish saved indicator configuration from unavailable scores in FINN Today; show the saved DCA purchase schedule separately from a chart timeframe in Automation; finish the Dutch onboarding copy. |
| Candidate branch | `codex/onboarding-briefing-dca-cadence`. |
| Candidate implementation SHA | `814b5ed0` (with candidate status correction in `eb591df9`). |
| PR | [#106](https://github.com/gvangalen/antigravity-trading-tool/pull/106), merged. |
| Production SHA | `31bb3e07877ca573f88d579fbf47fa2ba618ca16`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current backend/frontend SHA. |
| Previous live SHA | `7eafc957254228f0ebd33580dc5179ec258cc489`, independently tested on a fresh account. |
| Last updated | 2026-10-07 |

Independent QA found that the previous FINN Today card said macro and technical layers were not configured despite saved DXY and RSI configurations without usable scores. The Automation bot dialog used a 1D chart timeframe as purchase wording for a monthly day-5 DCA plan. The bot list repeated the timeframe without the plan cadence. Dutch onboarding still showed English state labels. The first card's live `response_source`, `generation_status`, and `trace.last_error_code` were not captured; this release does not claim to identify a provider or queue fault. No execution-cadence or live purchase outcome was established by that browser test.

The briefing input now carries a separate owner-scoped indicator-configuration status, configured names, and complete-current-benchmark boolean. A lookup failure stays unknown; it cannot be read as an empty configuration. The provider prompt explicitly distinguishes a saved indicator from a usable current score and does not let a historical analysis summary override the current configuration. The briefing contract version changes so older ready text is regenerated. Automation resolves the saved setup for its strategy, presents the DCA frequency and weekday/month day, labels 1D as a chart timeframe, and uses a daily bot spending cap rather than a per-1D purchase amount. Guided bot creation sends the saved DCA cadence and makes its default daily and per-order caps at least the strategy base amount. Dutch onboarding labels are translated. A saved setup is still a plan; this work does not assert that a bot is active or that a purchase is due.

Measured local evidence: root pytest **3173 passed, 3 skipped**, log SHA-256 `d55c947270f1a43856a09a7aeed2ec6cf59028702ea85aff19a8499bc6fd24fc`. Frontend build, typecheck, i18n lint/tests, command/proposal tests, focused onboarding and DCA cadence tests, and the canonical production-dependency `audit:high` script passed. Isolated PostgreSQL/Redis/FastAPI/Celery action-contract matrix **16/16**, zero broker orders or live calls, artifact SHA-256 `62c6046fb4e1683791b7201914f069baeffa520510f782f983946e4c7f82f53b`. Real-provider selector development **18/18** (SHA-256 `212be4fd111708028666ec74605dd2c18c5631c15cde62878fbd28c78a84d151`) and regression **109/109** (SHA-256 `b667490a967f87b01a107ebb8befe42ab569cd876be27b316317440ef45c2f6a`) had no provider, schema, parse, validation or timeout failure. A separate three-response real Luna/none briefing probe with saved DXY/RSI and absent scores did not call them unconfigured (SHA-256 `15a688828eb04b3e81ab30587b072df44c81182fa961b61fc7fdcbab679fd98f`); it is supporting evidence, not a production proof. Build has not accessed the QA fixture or sealed holdout.

Independent QA should check a new account's saved DXY/RSI without scores against the FINN Today text and, if observable, capture `response_source` and generation status. For a monthly DCA setup on day 5 with a 1D chart timeframe, compare the saved setup, Automation form, bot cadence, and bot list after refresh. Confirm the daily cap accommodates the saved amount without implying daily purchases, and inspect the Dutch onboarding labels. Actual bot execution remains outside the read-only onboarding result.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37663553111) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37663790208) passed all five jobs. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37664042646) succeeded for `31bb3e07877ca573f88d579fbf47fa2ba618ca16`. Public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-07. Build did not access the authenticated QA fixture.

## Previous Release (first briefing onboarding follow-up)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and deployment identity passed; independent authenticated QA is pending. |
| Goal | Keep Automation visible after a saved strategy during onboarding, schedule first FINN Today retries without a browser read, and identify temporary plan copy as temporary. |
| Candidate branch | `codex/first-briefing-onboarding-followup`. |
| Candidate implementation SHA | `c01fcce911aabe21a45cf8d7bc09f2959974c74f` (with the evidence correction in `0ef9b6162a5baf5b02cfd007241876581ebb53a4`). |
| PR | [#104](https://github.com/gvangalen/antigravity-trading-tool/pull/104), merged. |
| Production SHA | `ba247bb2dfdf26b808a98e71b4800fadfa6f83ff`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current backend/frontend SHA. |
| Previous live SHA | `e9c0db94671faf513f63ed21ce1783995741339a`, independently tested on a fresh account and not accepted for Automation or first AI briefing. |
| Last updated | 2026-10-07 |

The independent browser test observed Automation briefly before a 37-second dark loading state; refresh recovered it. FINN Today showed text that exactly matches the deterministic DCA template after approximately six seconds and did not visibly change during 45 seconds, refresh or relogin. The response source itself was not observed. The live `response_source`, `generation_status` and `trace.last_error_code` were not captured, so the production provider or queue failure cannot be named. The first retry window in this code is 60 seconds; the 45-second observation alone cannot verify that retry.

`AuthGuard` previously redirected `/bot` while onboarding was incomplete even after a strategy had unlocked Automation. It now permits the saved-strategy Automation route through the authoritative status check and its short-lived user-scoped cache. The first-dashboard worker now schedules a delayed retry through the existing enqueue path after a retryable fallback; a dashboard read is no longer required to initiate that retry. An unparseable provider JSON response is classified as retryable. FINN Today labels deterministic plan copy as temporary while generation/retry is active and identifies terminal fallback as a plan summary. The fallback remains safe and does not imply an AI-generated briefing.

Measured local evidence: root pytest **3171 passed, 3 skipped**; `.local-finn-parity-artifacts/first-briefing-followup-pytest-final.log` SHA-256 `06b55e849f32c45669e0d8c7f65244f5e68c0c26910e50f4870fae15b18bd9ce`. Frontend build, typecheck, i18n lint/tests, command/proposal/onboarding tests and high-severity dependency audit passed; frontend build log SHA-256 `65db30c5a2ca3ea5449644c57e3526f17135b42b34198a75183895f4b7578aaa`. The isolated local API/Celery/Responses safe-action matrix passed **16/16**, with zero broker orders or live trading calls; `.local-finn-parity-artifacts/first-briefing-followup-action-matrix-full.json` SHA-256 `e5457c201b88f6fe47450da44a02d5c3b0a70a9650c739abf3a0b757ca7c473f`. Real-provider selector development passed **18/18** (SHA-256 `ef502054623da8c9004a4c1120a0d7260da4dbfc39f3ef7d781cad46de7b89cd`) and regression **109/109** (SHA-256 `1cd512d0c0f585ced39f7e86ea29a9a290f567c666cc4dcded54230c52ce315f`), with zero provider, schema, parse, validation or timeout failures. The older `finn-local.sh matrix` runner was also attempted but failed because its legacy orchestrator snapshot join found no row on the current `visible_runtime` path; this run is recorded as a runner mismatch, not counted green. The current full action-contract runner is the 16/16 evidence above. The scheduled-retry behavior is covered by a targeted Celery task test; a real production retry on the QA account remains unverified.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37648424412) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37648696393) passed all five jobs. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37648918825) succeeded for `ba247bb2dfdf26b808a98e71b4800fadfa6f83ff`. Public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-07. Build did not access the authenticated QA fixture. Independent QA must test a new account's first Automation transition and FINN Today card, including the displayed source/status label and the delayed retry after its due time; matching text alone is not proof of a provider or queue failure.

## Previous Release (first briefing retry)

| Field | Value |
| --- | --- |
| Phase | `QA_NOT_ACCEPTED`. Build gates and deployment identity passed; fresh-account QA on production SHA `e9c0db94671faf513f63ed21ce1783995741339a` reproduced the Automation loading state and a FINN Today card matching the deterministic DCA template; the response source was not observed. |
| Goal | Recover a first FINN Today AI briefing after a transient worker/provider failure, and prevent a slow onboarding-status refresh from blanking Automation on route transitions. |
| Candidate branch | `codex/first-briefing-automation-fix`, merged to `main` in `ced224a3c5f04d07345c1e27125eff2019f0ad3b`. |
| Candidate implementation SHA | `2a565e8a2f8a7da53ed70b7848e9d92fe7b45b16`. |
| PR | [#102](https://github.com/gvangalen/antigravity-trading-tool/pull/102), merged. |
| Production SHA | `ced224a3c5f04d07345c1e27125eff2019f0ad3b`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current backend/frontend SHA. |
| Previous live SHA | `8e150bdfa63202244d8702688dfa32715be3cae7`, independently tested on a fresh QA account. |
| Last updated | 2026-10-07 |

Independent QA confirmed that the DCA onboarding data, Paper bot and 4/4 completion persisted on the previous live SHA. The first FINN Today card stayed on deterministic fallback copy after refresh and relogin; the exact live `response_source` and `last_error_code` were not captured. Automation also showed a dark spinner for more than 20 seconds on first transition. These are QA observations, not a proven production worker trace.

Code investigation found three concrete retry defects: the separate retry scheduler could mark a job `retry_scheduled` before its enqueue task skipped it as already in flight; the dashboard stopped polling while fallback waited for a retry; and the shared OpenAI client allowed only one scheduled call per hour, independently of the briefing service's former second limiter. The repair uses one version-scoped client limiter with three bounded attempts and one queue path for due retries. In an isolated local PostgreSQL/Redis/FastAPI/Celery runtime, a previously stuck `retry_scheduled` record with `ai_rate_limited` advanced to `queued` and then `ready` with `response_source=ai_generated` on worker attempt two. A second controlled worker probe pre-consumed a call slot in the same hour and still reached `ready` on attempt two. Mission Control read it back as `cached_ai`. A direct synthetic Saturday-DCA prompt to `gpt-6-luna` with reasoning `none` returned a valid Dutch briefing. The exact cause of the QA account's production fallback remains unproven without its trace.

The Automation spinner is rendered by `AuthGuard` while it awaits `/api/onboarding/status` at each protected route transition. A recent user-scoped status or a verified completed account now permits the current page to render while the authoritative server check continues; stale in-flight checks cannot redirect a later navigation. Independent browser QA must verify the effect on the first Automation transition.

Local backend tests: **3169 passed, 3 skipped**; `.local-finn-parity-artifacts/first-briefing-retry-pytest-final.log` SHA-256 `8f4f54d48258f96ff086d192ba61e0b983b8c4f9758683057ec079fca565deb0`. Focused first-dashboard and call-capacity tests passed. Frontend build, typecheck, i18n lint/tests, command/proposal/setup tests, onboarding handoff tests and high-severity dependency audit passed. The final isolated prefork Celery/Responses action matrix passed **16/16**, zero broker orders and live-trading calls; `.local-finn-parity-artifacts/first-briefing-retry-action-matrix-final.json` SHA-256 `2cf58c1ea347f0f7ace67c1123a43d44990c3eb9b137d21e820de7c3d1cd9735`. Real-provider selector development passed **18/18** with no provider/schema/parse/validation/timeout failures; SHA-256 `f649fcad794a5a44a47705f9d5d090adcda807739bb45df87771291b18db11f5`. The initial concurrent action matrix was **15/16** and two host-based selector regression runs ended **108/109** and **107/109** because of provider timeouts; they are recorded as red. The final 109-case Linux-runtime regression passed **109/109**, with zero provider, schema, parse, validation or timeout failures; `.local-finn-parity-artifacts/first-briefing-retry-selector-regression-linux.json` SHA-256 `b14291ce526efbf2ca2154db7983401e55c8d9b385585d4f69edbc75c336fccb`. The host-only timeout runs remain recorded as red diagnostics; the local parity-runtime release gate is green. Candidate [CI run 37630660797](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37630660797) passed all five checks, main [CI run 37631011253](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37631011253) passed, and [Auto Deploy run 37631280500](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37631280500) succeeded. Public backend health and frontend build-info both returned HTTP 200 and SHA `ced224a3c5f04d07345c1e27125eff2019f0ad3b`. The subsequent independent authenticated QA did not observe an AI-generated transition and saw the Automation page disappear behind a long loading state.

## Previous Release (fresh onboarding DCA)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and deployment identity checks passed; independent authenticated browser QA has not run. |
| Goal | Repair fresh-user DCA onboarding and the first FINN Today briefing: save the schedule, read the saved plan and trader context, finish the background briefing, and keep optional source failures from aborting Mission Control. |
| Candidate branch | `codex/onboarding-dca-today-context`, merged to `main` in `9e34dbda017c0c7313135c47ba3f4b651a584881`. |
| Candidate implementation SHA | `78cad90c891065bb33d71dad796a1717ebd0dc54` (together with preceding branch commit `ff79f435d67cfb1dab785e6082468d70fc24c112`). |
| PR | [#100](https://github.com/gvangalen/antigravity-trading-tool/pull/100), merged. |
| Production SHA | `9e34dbda017c0c7313135c47ba3f4b651a584881`, observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current backend/frontend SHA. |
| Last updated | 2026-10-07 |

The guided onboarding form now captures a daily, weekly, or monthly DCA
schedule and persists it with the setup; the fixed amount remains in the
linked strategy. The first FINN Today briefing is dispatched independently of
the older score/report chain. Its queued worker can claim its own task, while
Mission Control queues missing briefings without a blocking provider call.
Owner-scoped setup details, strategy amount, profile context, and optional
market context reach the briefing. Fixed DCA is described as a saved schedule,
not a discretionary entry or evidence of an executed purchase. Optional
strategy, bot, indicator, and portfolio reads use database savepoints so an
unavailable source does not invalidate the rest of the request.

Measured local evidence: root pytest **3165 passed, 3 skipped**; log SHA-256
`c14913b4fbc0ab07d5472c98f3206c676ebe254ae6a7ed32b0d5f1bb43d28793`.
Frontend build, typecheck, i18n lint/tests, command/proposal tests, and
high-severity dependency audit passed. The isolated PostgreSQL/Redis/FastAPI
and prefork Celery action matrix passed **16/16**, with zero broker orders and
zero live-trading calls; artifact SHA-256
`b6ec82c85312eb368a031df78b2e11d57287e3c6a17a55ab5f0b2136664e5d21`.
Real-provider selector development passed **18/18** (SHA-256
`85c8f15afb2b76515881bd72e358a71fb423d24402cf4176d2d2fbe9237a0869`)
and regression **109/109** (SHA-256
`a62c02d8c38bce1b89dfe39a82bdf02dda5d6cf0f1f6fd773755dbad6827b8d9`),
with zero provider, schema, parse, validation, or timeout failures. A local
fresh-account API path persisted a Friday DCA setup as weekday code `5` and a
fixed strategy. A local completed-account worker produced `ready` using
`gpt-6-luna`/`none`, with the saved DCA amount and FOMO profile preference;
Mission Control returned successfully for both tested local accounts. This is
Build evidence, not independent production QA. A one-off Automation loading
delay from the earlier browser report was not reproduced here.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37614979009)
and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37615249622)
completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37615474398)
completed success for `9e34dbda017c0c7313135c47ba3f4b651a584881`.
Public backend health and frontend build-info both returned HTTP 200 and that
SHA on 2026-10-07. Build did not access the authenticated QA fixture. QA should
complete a new-account browser path with a fixed DCA schedule, strategy and
Paper bot, then verify the first FINN Today card is personal and remains
consistent after a refresh. A repeated initial Automation loading delay, if
observed, needs a run trace; it was not reproduced in local validation.

## Previous Release (indicator source evidence)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and deployment identity checks passed; authenticated runtime QA is pending. |
| Goal | Expose each indicator's real source observation moment and the distinct dated source days required by absolute-value score normalizers, without changing score or execution decisions. |
| Candidate branch | `codex/score-source-evidence`, merged to `main` in `bf453f9d44777f4099e436d29a49d06d46c15243`. |
| Candidate implementation SHA | `bce8949f94a2c476d14f1c010f498d7a4cfb8d37` |
| PR | [#98](https://github.com/gvangalen/antigravity-trading-tool/pull/98), merged. |
| Previous live SHA | `bbccff3675160a6b1414d200aff1e19fc53b6da5`, reported by the user from authenticated QA. |
| Production SHA | `bf453f9d44777f4099e436d29a49d06d46c15243`, observed on both public surfaces after Auto Deploy. This status-only update will create a later SHA; QA must bind to the current backend/frontend SHA. |
| Last updated | 2026-10-07 |

The workspace projection now carries `source_observed_at` from each measured
indicator and derives freshness from that source moment, never from the receipt
timestamp. Analyse labels `sample_size` as readings in the selected period and
shows a separate count of distinct source days for Price and Volume in the
last 30 days, and DXY, S&P 500, Gold and Oil in the last 90 days. The existing
normalizers require five such days. A missing source moment appears as not
recorded. This is read-only evidence; it does not backfill market or macro
data, invent scores, change setup matches, or trigger bot decisions.

Measured local evidence: root pytest **3160 passed, 3 skipped**; frontend build,
typecheck, i18n lint/tests, command/proposal tests and high-severity dependency
audit passed. The isolated local PostgreSQL/Redis/FastAPI/prefork Celery stack
passed the safe-action matrix **16/16**, with zero prohibited executions,
`.local-finn-parity-artifacts/score-source-evidence-action-matrix.json` SHA-256
`370c6c58b1462d0ec2302dbeb836f830ed1605e6e9ceb9a61aec0e362e4c73e7`.
The real-provider selector development run passed **18/18**, SHA-256
`23e98c9ee8c30437d5d7502caa6b8e6bdec34c1cf44d395133db1d116cdaa569`;
regression passed **109/109**, SHA-256
`6f63a8a7dffe6e21b27ae57524aeef4dcebcc121608e6969ed98b3240643fd43`,
with zero provider, schema, parse, validation or timeout failures. The new
history query also executed against isolated PostgreSQL, and a local workspace
read completed. PR #98's workflow-validation, backend-tests, security-baseline,
mobile-quality and frontend-quality checks all completed success for the
implementation SHA. [Main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37599829650)
and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37600049169)
completed success for merge SHA `bf453f9d44777f4099e436d29a49d06d46c15243`.
Public backend health and frontend build-info both returned HTTP 200 and that
SHA on 2026-10-07. Build did not access the authenticated QA fixture.

The next independent QA pass should record the actual source moment and
historical-day count for the five BTC indicators reported on 2026-10-07. One
reading in the Day view alone does not establish whether scoring has the five
distinct historical source days it needs. A positive setup match and a
score-driven Paper decision remain unproved until complete fresh sources exist.

## Previous Release (pending-source explanation)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ASSESSED`. Targeted authenticated browser QA passed the pending-source explanation on the deployed SHA; broader scoreflow and read-parity acceptance remain open. |
| Goal | Preserve the pending-source status of a configured but unmeasured indicator through the complete asset workspace projection. |
| Candidate branch | `codex/preserve-pending-indicator-status`, merged to `main` in `9474f30a6023871c8895784853d4d9c11d513eaf`. |
| Candidate implementation SHA | `71e4946cdf60049158ca7065a63892e611b11b15` |
| PR | [#95](https://github.com/gvangalen/antigravity-trading-tool/pull/95), merged. |
| Previous live SHA | `b514fdb10356e3632129b12626e1c1898560aa80`; authenticated QA added BTC ADX and confirmed persistence, zero measurements, null value and score, but the expanded detail still said only “Onvoldoende data”. No real provider 429 occurred. |
| Production SHA | `9b47c454c971f6c589ad3ab33d790cfe593772d1` observed on both public surfaces after the status-only Auto Deploy. Any later status update creates a new SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-07 |

The root cause was in `WorkspaceDataService._enrich_indicator_rows`: `_include_configured_rows` marked an unmeasured configured indicator `pending_refresh`, but enrichment unconditionally replaced every null-value row status with `insufficient_data`. The frontend's pending explanation therefore never received its required status. The fix preserves `pending_refresh` for those rows while keeping the value, score and category score absent. A regression test covers the final technical category payload for configured ADX with no observation. This does not claim a real production 429 or a positive setupmatch or score-driven Paper decision.

Targeted authenticated QA on `9b47c454c971f6c589ad3ab33d790cfe593772d1` configured ADX for AAPL, hard-refreshed, and observed the indicator retained with zero measurements, no value and no score. Both the row and expanded detail explained that the source would be retried on the next data refresh and that there was no score yet; no browser errors occurred. This passes the specific pending-source presentation goal. No real provider 429 occurred; a positive setupmatch and score-driven Paper decision remain untested. The separate 20 read-only parity failures below remain open. This report was supplied by the user as QA evidence; no independent artifact hash was provided for this run.

Measured local evidence: root pytest **3156 passed, 3 skipped**, `.local-finn-parity-artifacts/preserve-pending-status-pytest-final.log` SHA-256 `a5bbdfe9a26803cd90f5adb56d938f5156edc955abdcbb35f283bf321fb0bbef`; frontend build, typecheck, i18n lint/tests, command/proposal tests, pending-evidence tests and high-severity dependency audit passed, build log SHA-256 `4898f64db7993188ed0110131f904fa0fd36141aaf1847c90294e76820135abf`. Isolated prefork Celery/Responses safe-action matrix passed **16/16**, with zero prohibited executions, `.local-finn-parity-artifacts/preserve-pending-status-safe-action-matrix.json` SHA-256 `ec1113e6394dccc9523fcba9b79c53c7169adfc33f271de8f20eac92b1940ead`. Real-provider selector development passed **18/18**, SHA-256 `84197429a1e60d8bb6057d222a16af922bfd2a833cb53ce0242eb07571c5edd1`; regression passed **109/109**, SHA-256 `817f5ca216ff22d1523a085a11227624e880029f9fe7f6012c79b6abbb863e61`, with zero provider, schema, parse, validation or timeout failures. An additional nonsealed parity diagnostic was **not green**: the action chain reached 16/16, but 20 read-only cases did not select the expected operation. Its final artifact is `.local-finn-parity-artifacts/preserve-pending-status-full-action-matrix-final2.json` SHA-256 `2402f95e31ed8462c4798ab8eec15cb25f3bc61699f8a02ad39a7c2c94add020`. This diagnostic remains a separate FINN read-route issue and is not counted as passing. The candidate changes no read selector or operation contract.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37574093759) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37574310111) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37574455371) completed success for `9474f30a6023871c8895784853d4d9c11d513eaf`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-07. The [status-only PR #96](https://github.com/gvangalen/antigravity-trading-tool/pull/96) also passed [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37574830533) and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37574979809); both public surfaces returned HTTP 200 and `9b47c454c971f6c589ad3ab33d790cfe593772d1`. Build did not access the authenticated QA fixture. A real 429, a positive setupmatch and a score-driven Paper decision remain unproved.

## Previous Release (pending explanation)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and production identity checks passed; independent authenticated QA is pending. |
| Goal | Show the persisted pending-source explanation for an indicator with no reading after a hard refresh in Analyse. |
| Candidate branch | `codex/technical-pending-evidence`, merged to `main` in `24f7959d8d5925b6d69d452881aec963cfbda642`. |
| Candidate implementation SHA | `7a63c85771fb50d35c48290eea648768513b258e` |
| PR | [#93](https://github.com/gvangalen/antigravity-trading-tool/pull/93), merged. |
| Previous live SHA | `8a8a061e8c7285322f66dbe54d28bfe9392b2b46`; targeted live QA confirmed MA 200 remains configured with zero readings and no score after refresh, but saw only generic insufficient-data text. No real provider 429 occurred in that run. |
| Production SHA | `24f7959d8d5925b6d69d452881aec963cfbda642` observed on public backend and frontend after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

The Analyse workspace already receives `data_status: pending_refresh` for configured indicators without a reading. The row renderer previously collapsed that status to a generic insufficient-data detail. This change keeps score and value absent while explaining that the source will be read again on a later data refresh. It does not claim that an observed 429 caused every pending row. The scheduled configured-source sync remains responsible for retrying the read; a browser refresh alone does not create a measurement.

Measured local evidence: root pytest **3155 passed, 3 skipped**, `.local-finn-parity-artifacts/technical-pending-copy-pytest.log` SHA-256 `70256762dc7a18ef88ba6c4ac4c3851c2103aa92aad5de4e185078557408728b`; frontend build, typecheck, i18n lint/tests, command/proposal tests, pending-evidence tests and high-severity dependency audit passed, `.local-finn-parity-artifacts/technical-pending-copy-frontend-build.log` SHA-256 `b16d04531c984824cfffee9ee28091d96cb18eef3b8b9937b51ab2040b94697f`. Isolated prefork Celery/Responses safe-action matrix passed **16/16**, with zero prohibited executions, `.local-finn-parity-artifacts/technical-pending-copy-full-action-matrix.json` SHA-256 `d1c9507e33b4999815bfb557b96bb7e2cf81950797bebe2f3bc4424e9a1b00f7`. Real-provider selector development passed **18/18**, `.local-finn-parity-artifacts/technical-pending-copy-selector-development.json` SHA-256 `4b068867a37c49496b7c7a398da919fb5fbde854112f4f5458d91240350856f3`; regression passed **109/109**, `.local-finn-parity-artifacts/technical-pending-copy-selector-regression.json` SHA-256 `00f4779b93ef947510a8f54ae88f70f8afe0f8469089339c7bbf3a475e3e6a90`. Both had zero provider, schema, parse, validation or timeout failures. This does not prove an actual production 429, a positive setupmatch with complete fresh sources, or a score-driven Paper decision.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37522979863) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37523303510) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37523609123) completed success for `24f7959d8d5925b6d69d452881aec963cfbda642`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06. Build has not run authenticated live QA. QA should check that an unmeasured configured indicator shows the pending-source explanation after refresh and, if a genuine provider 429 occurs, that the pending route remains usable. A positive setupmatch and score-driven Paper decision still require complete fresh sources.

## Previous Release (technical source limit)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ASSESSED`. Targeted authenticated QA confirmed MA 200 configuration persistence and honest null score on `8a8a061e8c7285322f66dbe54d28bfe9392b2b46`, but did not encounter a real 429; the persisted pending explanation was missing. Positive-match and Paper-decision acceptance remain open. |
| Goal | Keep owner-scoped MA 200 configuration pending without a fabricated reading when its technical source rate-limits; replace the 429→500 generic failure with an explicit pending-source response and UI message. |
| Candidate branch | Merged to `main` in `ff038fbed0987bb69acb97e456352589b8a47a89`. |
| Candidate implementation SHA | `487eba47c0e7462fb1f94b6aa110e547e2bb790d` |
| PR | [#91](https://github.com/gvangalen/antigravity-trading-tool/pull/91), merged. |
| Previous live SHA | `78d3d873fae8328b29ae6c10c267e85e33a64edc`, targeted live QA passed curve/weight persistence, duplicate Price validation and FINN emphasis, but MA 200 hit provider HTTP 429 and the app returned HTTP 500. |
| Production SHA | `ff038fbed0987bb69acb97e456352589b8a47a89` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

This batch classifies Twelve Data and Binance technical HTTP 429 responses as temporary source limits. A user-triggered indicator addition persists its owner-scoped configuration with `value: null` and `score: null`; Analyse already projects configured technical indicators without readings as pending rows. A scheduled refresh still counts a rate-limited read as failed. The API commits the pending configuration and the frontend states that no score exists yet. It neither retries a rate-limited provider immediately nor invents a reading.

Measured local evidence: root pytest **3155 passed, 3 skipped**, `.local-finn-parity-artifacts/technical-rate-limit-pytest.log` SHA-256 `81b9bc1aaf4a0b203f47618eef05f0f8bbef51a00376f1293627cdbe5e8268ca`; frontend build, typecheck, i18n, commands, proposals and production high-severity audit passed, `.local-finn-parity-artifacts/technical-rate-limit-frontend-build.log` SHA-256 `26fc0866f3ef5a45fea1925ba26ade9030a08acda251cbc2cd6c9d7169416a2a`. Isolated prefork Celery/Responses safe-action matrix passed **16/16**, zero prohibited executions, `.local-finn-parity-artifacts/technical-rate-limit-full-action-matrix.json` SHA-256 `236889f1337cb0eebeaf673a918ae71781b32b61e81a6ebb40c080354b6ace4f`. Real-provider selector development passed **18/18**, `.local-finn-parity-artifacts/technical-rate-limit-selector-development.json` SHA-256 `5a8110a9a78922ad7a917cc2d85e6ba5a89cc22ec08257b748de61ca2295fd45`; regression passed **109/109**, `.local-finn-parity-artifacts/technical-rate-limit-selector-regression.json` SHA-256 `940defc1bf82fa8367dc95ad590f036108513ef7fcb97eee0efb72c02969fb9e`. Both runs had zero provider, schema, parse, validation or timeout failures. The 429 branches were injected in local backend tests; this is not an authenticated live test of an actual rate-limited provider. Complete fresh-source positive setupmatch and score-driven Paper execution remain unproved.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37518522551) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37518779838) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37519034762) completed success for `ff038fbed0987bb69acb97e456352589b8a47a89`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06. Build has not run authenticated live QA. Independent QA should verify the real provider-limit case, the persisted pending technical row after refresh, the absence of a false score/setupmatch, and the later transition to a dated value when the source recovers. The positive match and paper-bot decision need complete fresh sources.

## Previous Release (indicator score curve persistence)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ASSESSED`. Targeted authenticated QA passed curve/weight persistence, duplicate Price validation, and FINN emphasis on `78d3d873fae8328b29ae6c10c267e85e33a64edc`; MA 200 exposed a provider 429→API 500 failure. Positive-match and Paper execution acceptance remain open. |
| Goal | Preserve custom indicator curves and weights across configuration writes, show actionable validation errors, prevent duplicate-selection side effects, and render FINN's single-star setup emphasis. |
| Candidate branch | Merged to `main` in `1e35609aacb1274f16e4eb7eb84de810356299b8`. |
| Candidate implementation SHA | `07da8518928ddcf33d3125d942267fe010aa0af6` |
| PR | [#89](https://github.com/gvangalen/antigravity-trading-tool/pull/89), merged. |
| Previous live SHA | `ee1e49ad8fc0c20d3dab685a73937fd718803140`, independently checked for the missing-data and duplicate-indicator paths. |
| Production SHA | `1e35609aacb1274f16e4eb7eb84de810356299b8` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

The independent live check of the previous release found that Analyse and FINN correctly keep incomplete BTC scores and setup matches unavailable, an unscored Volume indicator persists, and a duplicate Price indicator receives a clear error. It did not inspect the raw `null` payload, retest the separate insufficient-history validation error, or prove a positive match with complete fresh sources. These remain evidence limits, not green release claims.

This batch fixes a further configuration defect found during follow-up: saving custom five-band rules and then saving settings could overwrite the rules. The frontend now submits the custom curve and weight together, and the backend preserves existing custom rules on settings updates. Adding a duplicate indicator now fails before configuration writes. The dialog surfaces 400/422 validation details and accurately reports partial creation when a later settings write fails. FINN's text renderer handles single-star emphasis around setup names.

Measured local evidence: root pytest **3149 passed, 3 skipped**, `.local-finn-parity-artifacts/indicator-score-followup-pytest.log` SHA-256 `84b5994f29c635ba83cfef6fe18dafa54aa3253776cf0af257dd3d5d9476be37`; frontend production build and typecheck passed, `.local-finn-parity-artifacts/indicator-score-followup-frontend-build.log` SHA-256 `fe6def5111edb7ed220fb20089ed08c18a44d6680ccc4a9f0cc19e55a4f3e68a`; frontend i18n, commands, proposals, focused config/chat tests and high-severity dependency audit passed, with zero reported vulnerabilities. Isolated prefork Celery/Responses safe-action matrix passed **16/16**, with zero prohibited executions, `.local-finn-parity-artifacts/indicator-score-followup-full-action-matrix.json` SHA-256 `6a5c1366911bb7e5424cc6fcd90d92fabf50ffb1ae0fe4f4e137382882431e83`. Real-provider selector development passed **18/18**, `.local-finn-parity-artifacts/indicator-score-followup-selector-development.json` SHA-256 `41c2e28197c422c945c6ab7036a33e84bc2cd861c4e45ee20b2780a02e74b9c3`; regression passed **109/109**, `.local-finn-parity-artifacts/indicator-score-followup-selector-regression.json` SHA-256 `671b4c8e648f12f75a5a91ff0f09012913cd5b7151612ad25aeb04085d398da4`. Both runs had zero provider, schema, parse, validation or timeout failures. A synthetic, owner-scoped positive setup-match test covers fresh and stale source evidence locally; it does not establish a live positive match or paper-bot decision with five genuinely dated observations.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37513073466) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37513368649) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37513638120) completed success for `1e35609aacb1274f16e4eb7eb84de810356299b8`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06. Build has not run authenticated live QA. Independent QA should verify the raw missing-score payload, custom five-band rule/weight persistence, a visible insufficient-history error, FINN setup-name formatting, and a positive match/paper decision only with complete genuinely dated fresh sources.

## Previous Release (indicator score presentation)

| Field | Value |
| --- | --- |
| Phase | `PARTIALLY_ASSESSED`. Independent live QA passed the targeted missing-data and duplicate-indicator checks on `ee1e49ad8fc0c20d3dab685a73937fd718803140`; positive-match and separate validation-error acceptance remain open. |
| Goal | Repair stale and incomplete indicator-score presentation, preserve missing values in FINN evidence, and allow unscored market indicator configuration while history accumulates. |
| Candidate branch | Merged to `main` in `e7addf5459b08d39509726e21e6334624ddcefb8`. |
| Candidate implementation SHA | `d3c764cdcfa9bc2d804e5b0967c2398b13df714e` |
| PR | [#87](https://github.com/gvangalen/antigravity-trading-tool/pull/87), merged. |
| Previous live SHA | `3b2664f89b37b13fdde8d127bf1350a2c070138b`, independently tested and not accepted. |
| Production SHA | `e7addf5459b08d39509726e21e6334624ddcefb8` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

The new Build batch keeps a raw indicator reading separate from a validated score. Analyse day cards and row explanations use the canonical daily score and its indicator evidence. FINN preserves missing macro and technical scores as `null` and exposes the original source timestamp. A market indicator with too little dated history can be configured but remains unscored. The config dialog now explains duplicate-indicator failures inline. These fixes do not create the missing five-observation production fixture or prove a positive match or paper execution.

Measured local evidence: root pytest **3145 passed, 3 skipped**, `.local-finn-parity-artifacts/indicator-score-v2-qa-fix-pytest.log` SHA-256 `ecd9df3e79c791764637f1be6f32a7c677204840503a751006cb51ce56f88a03`; frontend production build and typecheck passed, `.local-finn-parity-artifacts/indicator-score-v2-qa-fix-frontend-build.log` SHA-256 `0853c8d97c722f652189763c03c7c6fdade2bca2d238f1b53c06cdd7904799d3`; frontend i18n, commands, proposals and high-severity production audit passed with zero vulnerabilities. The new canonical-score presentation tests passed **2/2**. Isolated prefork Celery/Responses safe-action matrix passed **16/16**, zero prohibited executions, `.local-finn-parity-artifacts/indicator-score-v2-qa-fix-full-action-matrix.json` SHA-256 `a8168eb0a1a93d52f1cb7e5a457a22e544d3d40358f8e93cdcd073d222aff19d`. Real-provider selector development passed **18/18**, SHA-256 `c61e11db46079b72471e615c4bac81dbcaac36bc4bcd4ec1d81873c8c003f747`; regression passed **109/109**, SHA-256 `bf414d7cdc37fceb4be4870abdbe09495221dc8fc5ae9337a7475d2d5783393a`, with zero provider, schema, parse, validation or timeout failures. Their artifacts share the `indicator-score-v2-qa-fix-selector-` prefix in `.local-finn-parity-artifacts/`.

[Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37506880820) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37507227211) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37507564081) completed success for `e7addf5459b08d39509726e21e6334624ddcefb8`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06. Build has not run authenticated live QA. The next QA pass must check AAPL stale DXY and one-observation Price presentation, FINN's S&P 500 missing-score semantics, duplicate and insufficient-history indicator configuration, and a controlled positive setupmatch/paper decision only when five genuinely dated measurements per required source are available.

## Previous Release (indicator score flow v2)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and production identity checks passed; this candidate is not independently accepted. |
| Goal | Unify indicator scoring and dated benchmark evidence across FINN, Analyse, Mijn Plan, reports, mobile and bot score input. |
| Candidate branch | Merged to `main` in `56e8a255ad34b74391ec0ae28724e4eb55ddaf95`. |
| Candidate implementation SHA | `a492d7e1f660dcdf60437fe7a7756bb836757722` |
| PR | [#85](https://github.com/gvangalen/antigravity-trading-tool/pull/85), merged. |
| Previous live SHA | `cb0c24827a853c616e0145d652f5353f2e9f8d24`. |
| Production SHA | `56e8a255ad34b74391ec0ae28724e4eb55ddaf95` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Last updated | 2026-10-06 |

The score-flow code passed local root pytest (3142 passed, 3 skipped), frontend build, mobile typecheck/lint/web smoke and migration plan validation. The frontend export was rebuilt, and the production dependency audit passed with zero vulnerabilities after updating the `sharp` override. [Candidate CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37498674203) and [main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37499125577) completed success. [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37499391196) completed success for `56e8a255ad34b74391ec0ae28724e4eb55ddaf95`; public backend health and frontend build-info both returned HTTP 200 and that SHA on 2026-10-06.

The isolated local PostgreSQL/Redis/FastAPI/prefork Celery stack used the real Responses provider and synthetic fixture users. The worker-driven safe-action matrix passed **16/16** with zero prohibited executions: `.local-finn-parity-artifacts/indicator-score-flow-v2-full-action-matrix.json`, SHA-256 `10c048fd645a6ac49ed701f6c88b8c0a950a87bad1e0d604e3e6d0de15071d96`. Real-provider selector development passed **18/18**: `.local-finn-parity-artifacts/indicator-score-flow-v2-selector-development.json`, SHA-256 `eb416a8e6a45cb67854e4c7a425cdc497376162c65d91ac48179f2edb4ddc170`. Real-provider selector regression passed **109/109**: `.local-finn-parity-artifacts/indicator-score-flow-v2-selector-regression.json`, SHA-256 `63f984a2a1c9e045db9fa59da9cde06018ca85f4c9f476500a98ac44dc939728`. Both selector runs had zero provider, schema, parse, validation and timeout failures. The isolated migration completed successfully. Independent authenticated live QA later tested production SHA `3b2664f89b37b13fdde8d127bf1350a2c070138b` and did not accept the score flow because of stale partial scores, missing-to-zero FINN evidence and configuration errors.

## Previous Release (setup-score repair)

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`. Build gates and production identity checks passed; this candidate is not independently accepted. |
| Goal | Repair Analyse ↔ FINN score evidence, setup-boundary reads with multiple strategies, exact Smart-DCA threshold readback, and the paper-bot `NaN` display. |
| Candidate branch | Merged to `main` in `1f50e2f3adc682de0bf2f468be7aaddbc89e4561`. |
| Candidate implementation SHA | `cece6f8ce964a3df7c29c1992ee85cf23af7b1c9` |
| PR | [#83](https://github.com/gvangalen/antigravity-trading-tool/pull/83), merged. |
| Previous live SHA | `82f8b6bec76b80234e4a8b1222aa96fb9cd5cc3b`, reported by independent live QA as not accepted. |
| Production SHA | `1f50e2f3adc682de0bf2f468be7aaddbc89e4561` observed on both public surfaces after Auto Deploy. This status-only update creates a later SHA; QA must bind to the current public backend/frontend SHA. |
| Release owner | Build |
| Last updated | 2026-10-06 |

## Change And Limits

- FINN reads the same owner-scoped saved daily market score as Analyse. It receives source status separately and does not treat a reported score as a verified complete benchmark.
- Saved setup score boundaries remain readable without choosing among linked strategies. The setup-match tool carries those conditions even when current scores are incomplete.
- Smart-DCA score bands and hypothetical amounts are derived from the execution curve engine. Exact score 70 selects the high band in a 40/70 step curve.
- The paper-bot card displays a missing stop-loss instead of `€ NaN`.
- A dated score report can be read even when it precedes today; its report date does not establish current source freshness.
- The [live test plan](../operations/setup-market-match-live-test-plan.md) includes the QA regressions. The one generic failure turn has no runtrace, so its exact cause is not established. A positive match, paper-bot decision with fresh sources, and authenticated cross-surface behavior remain for independent QA.

## Measured Local Build Evidence

All runtime artifacts below used an isolated local PostgreSQL, Redis, FastAPI and prefork Celery stack with the real Responses provider. The chat model was `gpt-6-luna` with reasoning `none`. The selector used its separately configured provider model. The local matrix made no broker orders, live bot activations, live trading calls or production connections.

| Gate | Result | Evidence |
| --- | --- | --- |
| Worker-driven safe action contracts | `16/16`; zero prohibited executions. | `.local-finn-parity-artifacts/setup-match-qa-fix-full-action-matrix.json`, SHA-256 `5fc3d48fba1815bf4e88cdb461bae9144820a7c7ae6e42673c952d6e8cdc92fd`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/setup-match-qa-fix-selector-development.json`, SHA-256 `af7d0cf41d9597ad74ef946145575274392c2a741ac269c03537010e5db7c886`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. Selector implementation was unchanged after this run. | `.local-finn-parity-artifacts/setup-match-qa-fix-selector-regression.json`, SHA-256 `ae6dcfa79f07048bc30182d0430f829c00bf9a8aadbf71794b0fce83ac2a726d`. |
| Local Responses/API/Celery conversation | Named BTC setup bounds with two strategies, follow-up against incomplete scores, saved market score 100 with stale source, and exact Smart-DCA score 70 → €90 all completed read-only. | `.local-finn-parity-artifacts/setup-match-qa-fix-live-probe.json`, SHA-256 `cb5173f4961678f75fa8fb21d1f471d28009aa8c1d5db9bd14c4f8942099ed88`. |
| Dated saved-score conversation | Both turns completed read-only; prior score report date and three values read, no current trade signal inferred. | `.local-finn-parity-artifacts/setup-match-qa-fix-score-date.json`, SHA-256 `d3512dfd695c40765cc328f55c561019fe61ffb5f5346fcdb87dbea678a44ab7`. |
| Backend | `3133 passed, 3 skipped`; includes typed tool, source-status, setup-boundary, Smart-DCA threshold and conversation regressions. | `pytest -q --disable-warnings`; `.local-finn-parity-artifacts/setup-match-qa-fix-pytest.log`, SHA-256 `3aa5133d49c48836ff3ade3da2bae0cf49717aeed19f61f92b66929df5873bc1`. |
| Frontend | Build, typecheck, i18n lint/tests, commands, proposals, setup tests and high-severity production dependency audit passed; zero vulnerabilities. | `.local-finn-parity-artifacts/setup-match-qa-fix-frontend-build.log`, SHA-256 `7adc82013f7addf1e524a5f4cba3ae91b7da2aa70c0a0ca4bf72a4e062744d6f`. |

An additional 37-case public parity runner was tried and did not pass. Its old DCA setup prompt lacks the now-required amount, so clarification is correct, while its read probes require legacy operation IDs absent from the current model-led chat route. This runner is not the required 16-action contract gate; its mismatch is recorded rather than counted as green.

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | [PR #83 CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37420681594) completed success. |
| Main CI and Auto Deploy | [Main CI](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37420888542) and [Auto Deploy](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37421015126) completed success for `1f50e2f3adc682de0bf2f468be7aaddbc89e4561`. |
| Public backend health and frontend build-info | On 2026-10-06 both returned HTTP 200 and SHA `1f50e2f3adc682de0bf2f468be7aaddbc89e4561`. |
| Independent authenticated live QA | Pending for this candidate; only QA owns the fixture and verdict. |
