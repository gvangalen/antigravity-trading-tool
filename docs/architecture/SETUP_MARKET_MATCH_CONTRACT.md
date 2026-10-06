# Setupmatch en benchmark

Status: canonical

## Eén betekenis

De totale benchmark gebruikt de actuele markt-, macro- en technische scores met de huidige Analyse-weging van de gebruiker. De setupmatch vergelijkt de drie componenten met de opgeslagen minimum- en maximumvoorwaarden van één owner-scoped setup. De setupmatch is een beoordeling van planfit, geen instapsignaal of ordertoestemming.

Een setup zonder scorevoorwaarden krijgt `unconfigured` en geen numerieke match. Ontbrekende of verouderde componenten krijgen `insufficient_data` en geen numerieke match. Een geldige score buiten een harde voorwaarde krijgt `outside_conditions`; alleen een match binnen alle opgeslagen voorwaarden krijgt `matches`. Van de passende setups wordt de hoogste als `is_best` aangeduid. De lijst blijft volledig zichtbaar en toont de beste bovenaan.

## Bronnen en afnemers

- `domain/setup_market_match.py` bevat de score- en statusregels.
- `SetupMarketMatchService` leest owner-scoped setups, huidige Analyse-weging, dagscore en de bronmomenten voor FINN, My Plan, dashboard en Analyse.
- `setup_market_match_sync.py` biedt dezelfde regels en broncontrole aan Celery voor rapporten en botbeslissingen.
- Dagrapporten met deze betekenis markeren hun setups als `benchmark_setup_match_v1`. Oude AI-setupcijfers worden niet als actuele match teruggegeven. De oude Setup AI Agent is uitgefaseerd; een Celery-tombstone vangt al gequeue'de taken op zonder te schrijven.
- Web en mobile tonen ontbrekende benchmarks en matches als ontbrekend, niet als nul. Scorehistorie van vóór deze migratie wordt niet stilzwijgend als setupmatch gelabeld.

## Botuitvoering

Een bewezen match kan de bestaande score-invoer voor bedrag en risico beïnvloeden. Bij ontbrekende match gebruikt de engine intern een neutrale invoer voor die berekening; de zichtbare en opgeslagen matchscore blijft leeg. Het ontbreken van een match blokkeert een bestaande bot niet. Smart DCA behoudt zijn afzonderlijke eis van een complete, verse benchmark voor een scoregestuurd bedrag.

## Acceptatiegrens

Lokale tests controleren de gedeelde rekenregels, bronversheid, owner-scope, twintig assets en de nul/ontbrekend-grens. Voor productieacceptatie zijn nog onafhankelijke QA van echte bronmomenten, FINN-antwoord, My Plan, rapport en een gecontroleerde botbeslissing op dezelfde gebruiker en asset nodig. Een lokale groene suite is geen bewijs van live pariteit.
