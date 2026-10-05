# Live testplan: benchmark en setupmatch

Status: kandidaat voor onafhankelijke QA; geen live acceptatiebewijs.

Gebruik een ingelogde QA-gebruiker met ten minste twee assets en meerdere setups per asset. Vergelijk steeds dezelfde gebruiker, asset, datum en Analyse-weging. Leg de gedeployde backend- en frontend-SHA vast voordat de test begint. Voer alleen gecontroleerde paper-acties uit; een live order is niet nodig om de score-invoer te beoordelen.

| Controle | Verwachte uitkomst |
| --- | --- |
| Analyse: markt, macro, technisch en totaal | De totaalscore gebruikt de actuele Analyse-weging. FINN noemt dezelfde drie bronwaarden en totaalscore, met bronmoment en ontbrekende gegevens herkenbaar. |
| Mijn Plan: meerdere setups voor één asset | Alle setups blijven zichtbaar. Een setup binnen alle opgeslagen scoregrenzen krijgt `matches`; de best passende staat bovenaan. Een setup buiten een grens krijgt `outside_conditions` met die grens als uitleg. |
| Twintig assets | Een vraag of overzicht voor meerdere assets verwisselt geen setup tussen assets en toont geen setup van een andere gebruiker. |
| Ontbrekende of oude bron | Benchmark en setupmatch ontbreken zichtbaar; FINN en het rapport presenteren geen nul of oude AI-score als actuele match. Na verse volledige bronnen verschijnt de berekening weer. |
| FINN-vervolgvraag | Na een lijst kan FINN de best scorende setup aanwijzen, de drie componenten en opgeslagen grenzen noemen en uitleggen waarom de match wel of niet geldt. Hij verwart de match niet met een bewezen entrytrigger. |
| Dagrapport en mobiel | Dezelfde asset en datum tonen dezelfde betekenis en score als FINN en Mijn Plan. Historische rapporten zonder `benchmark_setup_match_v1` worden niet omgelabeld. |
| Paper-botbeslissing met match | Het besluit gebruikt de nieuwe match als score-invoer voor bestaande bedrag- en risicologica. De zichtbare match en bronstatus komen overeen met FINN en Mijn Plan. Geen botstart of order door een read-only vraag. |
| Paper-botbeslissing zonder match | Er verschijnt geen fictieve zichtbare matchscore. De ontbrekende match blokkeert de bestaande bot niet; overige uitvoerings- en veiligheidsregels blijven gelden. |
| Smart DCA | Bij complete, verse markt-, macro- en technische bronnen volgt het bedrag de opgeslagen curve en actuele Analyse-weging. Bij ontbrekende of oude bronnen ontstaat geen scoregestuurd bedrag. |

Noteer per beurt de run-ID en per botbeslissing de decision-ID, bronmomenten, scorevelden en reden voor een ontbrekende score. Controleer bij een verschil eerst het gedeployde SHA en daarna de eigenaar, asset, weging en bronversheid.
