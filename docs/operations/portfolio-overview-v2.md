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
  gedateerde omrekening blijft de positiewaarde onbekend. De koersbron moet
  bovendien een bronmoment binnen 24 uur hebben.
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
voorlopig niet als eurografiek getoond. Nieuwe snapshots worden niet geschreven
als een aangehouden positie geen controleerbare, recente EUR-koers heeft.

## Vervolg voor complete waardering

Voor een waarde bij USDT/USD-posities is een gedateerde FX-bron, dezelfde
EUR-prijsgrondslag in Paper-orderberekening en portefeuillewaardering, en
versiebeheer op de waardehistorie nodig. Voor een volledig Live-overzicht is
daarnaast brokerreconciliatie nodig die cash en posities precies één keer telt.
Tot die contracten bestaan, toont de productweergave een onbekende waarde in
plaats van een schijnbaar precies eurobedrag.

Bij herkeuring: controleer Paper en Live apart, twintig assets, meerdere bots
per asset, eigenaarsscheiding, botlimieten versus cash, verse en oude koersen,
en dat FINN dezelfde onbekende waarden en bronmomenten uitlegt. Een Portfolio-
knop bespreekt de gegevens in chat en voert zelf geen order uit.
