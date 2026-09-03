# GOAL — FINN Release afronden
## Doel
Valideer kandidaat `337e936a` volledig en breng FINN alleen bij volledig groene gates naar onafhankelijke productie-QA.
## Huidige status
- Branch: `codex/finn-selector-state-evaluate-repair`
- Kandidaat: `337e936a`
- Lokale rootsuite: `1610 passed, 3 skipped`
- Echte-provider-validatie loopt of moet worden afgerond
- Productiemodel blijft `gpt-4o-mini`
- Geen datasets of thresholds wijzigen
## Nog verplicht
1. development en regression;
2. sealed holdout;
3. guided `create_setup`;
4. assetprecedence/canonicalisatie;
5. compound `EVALUATE`;
6. authenticated runtime- en active-planparity;
7. confirmation, execution en idempotency;
8. lifecycle, polling/SSE, workers, retries en queueleaks;
9. safety en latency;
10. volledige CI.
## Releasegates
- operationaccuracy >= 95%
- selectoraccuracy >= 98%
- targetassetaccuracy = 100%
- geen blocking state-, runtime- of safetyfouten
- geen uitvoering zonder bevestiging
- geen ongeautoriseerde writes
- geen impliciete live bot
## Beslissing
### Gate rood
- niet deployen;
- geen QA starten;
- rapporteer `NOT READY FOR QA`;
- stop.
### Alle gates groen
- push en release volgens `AGENTS.md`;
- verifieer de productie-SHA en health;
- start zelfstandig exact één onafhankelijke QA-agent;
- geef QA de productie-SHA, artifacts en ongewijzigde gates;
- QA is read-only en mag niets repareren;
- wacht op `ACCEPTED` of `NOT ACCEPTED`;
- rapporteer het verdict aan de gebruiker;
- voer na QA geen automatische repair-loop uit.
## Eindrapport
Vermeld alleen:
- verdict;
- definitieve SHA;
- exacte testmetrics;
- CI/deploymentruns;
- productiehealth;
- QA-run en verdict;
- eventuele blocker.
## Buiten scope
- nieuw model;
- nieuwe functies;
- designwerk;
- dataset- of thresholdwijzigingen;
- case-specifieke patches;
- ongevraagde refactors.
