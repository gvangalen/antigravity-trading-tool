# Portfolio-overzicht: geldbetekenis en bewijsgrenzen

De Portfolio-pagina, mobiele Portfolio-weergave en FINN lezen dezelfde
eigenaargebonden projectie via `GET /api/portfolio/summary?environment=paper|live`.
Paper en Live worden afzonderlijk getoond. Een botbudget is een limiet en telt
nooit als cash, belegde waarde of startkapitaal.

## Betekenis van de bedragen

- **Paper-cash** is het werkelijk gefinancierde virtuele saldo in
  `bot_portfolios.cash_eur`. Een nog niet gefinancierde bot heeft een onbekend
  saldo, ook als zijn budgetlimiet is ingesteld.
- **Positiewaarde** is `position_qty × een recente koers in EUR`. De
  `market_data`-prijs staat doorgaans in de quotevaluta van de asset: bij
  BTC/ETH meestal USDT en bij aandelen vaak USD. Zonder controleerbare,
  gedateerde omrekening blijft de positiewaarde onbekend. De prijs- en
  FX-bron moeten elk een eigen bronmoment binnen 24 uur hebben. EUR/USD komt
  van Twelve Data; EUR/USDT van Binance. De opgeslagen factor is EUR per
  quotevaluta en wordt nooit als vaste 1:1-omrekening aangenomen.
- **Bestaande Paper-fills:** oudere Paper-orders hadden niet altijd een
  gecontroleerde EUR-prijs. Bots met zulke transacties worden gemarkeerd als
  `unverified_ledger`; hun cash, resultaat en totaal tellen niet mee als
  geverifieerde portefeuillewaarde totdat de ledger is gereconcilieerd.
  Uitvoeringsregels met `valuation_version=1` blijven ook herkenbaar wanneer
  een oude worker tijdens de uitrol nog een order schrijft. Nieuwe, met een
  gecontroleerde EUR-prijs geboekte Paper-fills krijgen versie 2.
- **Paper-totaal** is de som van bekende virtuele cash en bekende
  positiewaarden. Als een benodigde waarde ontbreekt, is het totaal onbekend;
  bekende cash blijft afzonderlijk zichtbaar.
- **Live** heeft nog geen eigenaargebonden reconciliatie van het gedeelde
  brokerrekeninggeld met de botposities. Het Live-totaal en de beschikbare
  cash blijven daarom onbekend. Een brokerbedrag wordt niet bij elke bot
  opgeteld.
- **Resultaat** is gerealiseerde plus ongerealiseerde ledgerwinst of -verlies.
  Het is geen rendementpercentage. Stortingen en opnames moeten worden
  verwerkt voordat een grafiek als prestatie kan worden uitgelegd.

Historische snapshots zonder vastgelegde valuta- en omrekenprovenance worden
niet als eurografiek getoond. `portfolio_value_snapshots_v2` bevat uitsluitend
volledige Paper-waarderingen met dezelfde EUR-regels als het overzicht. Een
punt wordt niet geschreven als een botledger of benodigde koers/FX-bron
ontbreekt of een oude ledger niet geverifieerd is. Elk nieuw punt bewaart ook
de gebruikte prijsrij, bronmomenten, quotevaluta, FX-factor, virtuele cash per
bot en het update-moment van diens portefeuille voor herleiding.
De grafiek verbindt punten over een ontbrekend uur niet met een
doorlopende lijn. `GET /api/portfolio/value-history` is eigenaargebonden en
geeft voor Live bewust geen punten.

## Vervolg voor complete Live-waardering

Paper-orderpreview, Paper-botsizing en Paper-portefeuillewaardering gebruiken
dezelfde gedateerde EUR-omrekening. Een handmatige Paper-order krijgt pas na
een serverpreview een eigenaar-, bedrag- en orderreferentiegebonden token dat
vijf minuten geldig is. De direct geboekte Paper-prijs komt uit de gedateerde
markt- en FX-bron; een door de client ingevulde prijs of valutamarkering is
geen koersbewijs. Herhaling van dezelfde bevestiging boekt geen tweede order.
Handmatige Live-orders zijn voorlopig niet bevestigbaar. Een verzonden
beurslimietorder kan nog openstaan; zonder bevestigde fills en idempotente
reconciliatie mag de app geen cash of positie in het Live-ledger boeken.
Een Live-overzicht vereist nog
brokerreconciliatie die cash en posities precies één keer aan botten toewijst.
Een Live-bot met een niet-EUR exchange-paar wordt niet met de generieke
Paper-FX-factor uitgevoerd; daarvoor is een exchange-specifiek
afrekenvalutacontract nodig. Tot die contracten bestaan, toont de
productweergave onbekende bedragen in plaats van een schijnbaar precies totaal.

Bij herkeuring: controleer Paper en Live apart, twintig assets, meerdere bots
per asset, eigenaarsscheiding, botlimieten versus cash, verse en oude koersen,
en dat FINN dezelfde onbekende waarden en bronmomenten uitlegt. Een Portfolio-
knop bespreekt de gegevens in chat en voert zelf geen order uit.
