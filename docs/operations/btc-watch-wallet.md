# Alleen-lezen BTC-wallet in Portfolio

Een gebruiker kan één of meer BTC-accounts uit Ledger Wallet koppelen met een
account-xpub (BIP32-diepte 3). De xpub is privacygevoelig: de gekoppelde
blockchainprovider kan alle afgeleide adressen en transacties volgen. De UI
vereist daarom een afzonderlijke expliciete bevestiging. De gebruiker voert
nooit een herstelzin of privésleutel in.

Koppelen heeft twee stappen. Na expliciete provider-toestemming leest de
preview één saldo zonder het account op te slaan. De gebruiker vergelijkt het
bevestigde BTC-saldo en accounttype met Ledger Wallet. Alleen een tweede,
eigenaargebonden bevestiging met een maximaal tien minuten geldig ondertekend
previewbewijs slaat de versleutelde xpub en de previewmeting op. Bij wijziging
van xpub of accounttype is opnieuw een preview nodig. Een verkeerde keuze van
het adrestype kan een nul- of onjuist saldo opleveren.

## Provider

De backend gebruikt de vaste Alchemy Bitcoin UTXO/Blockbook xpub-endpoint.
Configureer `ALCHEMY_BITCOIN_API_KEY` uitsluitend in de beschermde backend- en
workeromgeving; de waarde wordt niet naar de browser gestuurd. De Bitcoin
UTXO-functie moet voor de Alchemy-app ingeschakeld zijn; een bestaande Alchemy-
app met die functie volstaat, een nieuwe app is niet verplicht. Zonder geldige sleutel
blijven koppelen en vernieuwen uitgeschakeld. Controleer vóór vrijgave met een
synthetische publieke account-xpub dat de provider een `balance` in satoshi's
teruggeeft; een sleutel alleen bewijst geen endpointtoegang.

## Gefaseerde vrijgave

De functie staat standaard uit. Zet voor een beperkte pilot alleen
`BTC_WATCH_PILOT_USER_IDS` op een kommagescheiden lijst van bestaande
gebruikers-ID's. Pas na geslaagde onafhankelijke QA kan
`BTC_WATCH_WALLET_ENABLED=true` de functie voor alle accounts openen.
Backend, worker en publieke providerstatus lezen dezelfde flags. Een
uitgeschakelde account kan bestaande koppelingen nog zien en verwijderen,
maar niet toevoegen of verversen; de worker ververst uitsluitend toegelaten
accounts. Test de exacte productie-SHA met een publieke test-xpub en controleer
ook verlopen saldi, eigenaarsisolatie, FINN-bronvermelding en het uitblijven
van een order- of ondertekenpad. Bewaar geen echte gebruiker-xpub in tests of
release-artifacts.

De backend bouwt zelf een output descriptor voor het door de gebruiker gekozen
accounttype. De provider ontdekt ontvang- en wisselgeldadressen. De app bewaart
de xpub versleuteld met `ENCRYPTION_KEY`, geeft hem nooit terug in een API- of
FINN-antwoord en verwijdert hem met de walletkoppeling. HTTP-clientlogs op
INFO zijn voor deze connector uitgeschakeld omdat de provider de sleutel en
descriptor in het URL-pad verwacht.

## Saldocontract

Alleen bevestigde satoshi's vormen de getoonde BTC-hoeveelheid; onbevestigde
satoshi's blijven apart. `fetched_at` is het tijdstip waarop de API-uitlezing
werd ontvangen en is **geen blocktijd**. Een meting ouder dan 24 uur blijft zichtbaar
met een verouderingsstatus, maar krijgt geen actuele EUR-waardering. Een EUR-
waarde vereist tevens een gedateerde BTC-koers en, indien nodig, een geldige
EUR-wisselkoers. Walletsaldo en waardering staan buiten Paper-kas,
botbudgetten, Paper-posities en brokervermogen. FINN mag deze bronnen alleen
afzonderlijk benoemen; er is nog geen geverifieerd totaal van alle echte en
virtuele vermogensbronnen.

Een worker controleert maximaal 10 verschuldigde wallets per 5 minuten, in
hoogstens drie gelijktijdige provideropvragen met zes seconden timeout. Het
taakresultaat meldt `refreshed`, `failed` en `backlog`. Een handmatige refresh
is eigenaargebonden en begrensd. De API heeft geen teken-, PSBT-, overdrachts-
of orderfunctie.
