import type { MobileCoachFeedItem } from './tradamindApi';

export function coachFeedDiscussionPrompt(item: MobileCoachFeedItem, language: string): string {
  const symbol = String(item.symbol || '').trim().toUpperCase();
  const pair = String(item.evidence?.trading_pair || '').trim().toUpperCase();
  const asset = pair.startsWith(`${symbol}/`) ? pair : symbol;
  const setup = String(item.evidence?.setup_name || '').trim() || asset;
  const copy = {
    nl: {
      watchlist_added: `Controleer de huidige indicatoren en benchmark voor ${asset} en adviseer een volgende analysestap. Wijzig niets.`,
      analysis_ready: `Controleer de actuele benchmark en bronmomenten voor ${asset}. Adviseer of een setup past en welke keuze je van mij nodig hebt. Maak niets aan.`,
      strategy_next_step: `Controleer of setup '${setup}' voor ${asset} nog bestaat en nu een strategie heeft. Zo niet, adviseer de volgende stap. Maak niets aan.`,
      paper_next_step: `Controleer de opgeslagen strategie voor setup '${setup}' (${asset}), of er een bot bestaat en of de strategie uitvoerbaar is. Adviseer alleen over een Paper-proef en risico-instellingen. Activeer of verhandel niets.`,
      bot_decision: `Controleer het opgeslagen Paper-botbesluit voor ${asset}, de regels en eventuele uitvoering in de botgeschiedenis. Leg uit waarom de bot wel of niet handelde en adviseer één concrete vervolgstap. Gebruik geen actuele koers als bewijs voor historische uitvoering; wijzig niets.`,
    },
    en: {
      watchlist_added: `Check the current indicators and benchmark for ${asset} and suggest a next analysis step. Change nothing.`,
      analysis_ready: `Check the current benchmark and source times for ${asset}. Advise whether a setup fits and what decision you need from me. Create nothing.`,
      strategy_next_step: `Check whether setup '${setup}' for ${asset} still exists and has a linked strategy now. If not, advise the next step. Create nothing.`,
      paper_next_step: `Check the saved strategy for setup '${setup}' (${asset}), whether a bot exists and whether the strategy is execution ready. Only advise on a Paper trial and risk settings. Activate or trade nothing.`,
      bot_decision: `Check the saved Paper bot decision for ${asset}, its rules and any execution in bot history. Explain why the bot did or did not act and suggest one concrete next step. Do not use a current quote as evidence for historical execution; change nothing.`,
    },
    de: {
      watchlist_added: `Prüfe die aktuellen Indikatoren und den Benchmark für ${asset} und empfehle den nächsten Analyseschritt. Ändere nichts.`,
      analysis_ready: `Prüfe den aktuellen Benchmark und die Quellenzeitpunkte für ${asset}. Empfiehl, ob ein Setup passt und welche Entscheidung du von mir brauchst. Erstelle nichts.`,
      strategy_next_step: `Prüfe, ob Setup '${setup}' für ${asset} noch besteht und jetzt eine Strategie hat. Falls nicht, empfehle den nächsten Schritt. Erstelle nichts.`,
      paper_next_step: `Prüfe die gespeicherte Strategie für Setup '${setup}' (${asset}), ob ein Bot existiert und ob die Strategie ausführbar ist. Berate nur über einen Paper-Test und Risikoeinstellungen. Aktiviere oder handle nichts.`,
      bot_decision: `Prüfe die gespeicherte Paper-Botentscheidung für ${asset}, die Regeln und ihre Ausführung in der Bot-Historie. Erkläre, warum der Bot handelte oder nicht, und empfehle einen konkreten nächsten Schritt. Verwende keinen aktuellen Kurs als Beleg für eine frühere Ausführung; ändere nichts.`,
    },
  };
  const locale = language === 'en' || language === 'de' ? language : 'nl';
  const kind = item.event_type as keyof typeof copy.nl;
  return copy[locale][kind] || `${item.title}. ${item.description}`;
}

export function coachFeedQuoteCurrency(item: MobileCoachFeedItem): string | undefined {
  const symbol = String(item.symbol || '').trim().toUpperCase();
  const pair = String(item.evidence?.trading_pair || '').trim().toUpperCase();
  const [base, quote, extra] = pair.split('/');
  return base === symbol && !extra && /^[A-Z]{3,5}$/.test(quote || '') ? quote : undefined;
}
