const positiveId = (value) => Number.isSafeInteger(value) && value > 0;
const pairName = (value) => /^[A-Z0-9][A-Z0-9._/-]{0,30}$/.test(value || '');

export function journeyNextStepAfterConfirmedWrite(operationId, nextStep, locale = 'nl') {
  if (!['create_setup', 'create_strategy'].includes(operationId) ||
      !positiveId(nextStep?.setup_id) || !pairName(nextStep?.pair)) return null;
  const language = String(locale).split('-')[0];
  const pair = nextStep.pair;
  const setupId = nextStep.setup_id;
  if (nextStep.step === 'strategy') {
    const copy = {
      nl: [`Je setup voor ${pair} is opgeslagen. Wil je nu een strategie aan deze setup koppelen?`, 'Strategie voorbereiden', `Bereid een strategie voor mijn bestaande ${pair}-setup met ID ${setupId} voor. Maak geen nieuwe setup. Vraag naar ontbrekende keuzes en leg de strategie ter bevestiging voor.`],
      en: [`Your ${pair} setup is saved. Would you like to link a strategy now?`, 'Prepare strategy', `Prepare a strategy for my existing ${pair} setup with ID ${setupId}. Do not create another setup. Ask for missing choices and present the strategy for confirmation.`],
      de: [`Dein Setup für ${pair} ist gespeichert. Möchtest du jetzt eine Strategie verknüpfen?`, 'Strategie vorbereiten', `Bereite eine Strategie für mein bestehendes ${pair}-Setup mit ID ${setupId} vor. Erstelle kein weiteres Setup. Frage nach fehlenden Angaben und lege die Strategie zur Bestätigung vor.`],
    }[language] || null;
    if (!copy) return null;
    return { question: copy[0], choices: [{ label: copy[1], reply: copy[2] }] };
  }
  if (nextStep.step === 'paper' && positiveId(nextStep.strategy_id)) {
    const strategyId = nextStep.strategy_id;
    const copy = {
      nl: [`De strategie voor ${pair} is opgeslagen. Wil je nu een Paper-bot voor deze strategie voorbereiden?`, 'Paper-bot voorbereiden', `Bereid een Paper-botvoorstel voor mijn opgeslagen ${pair}-strategie met ID ${strategyId} voor setup ID ${setupId} voor. Vraag naar ontbrekende risico- en budgetkeuzes en leg de bot apart ter bevestiging voor. Activeer niets en plaats geen order.`],
      en: [`The ${pair} strategy is saved. Would you like to prepare a Paper bot for it?`, 'Prepare Paper bot', `Prepare a Paper bot proposal for my saved ${pair} strategy with ID ${strategyId} for setup ID ${setupId}. Ask for missing risk and budget choices and present the bot separately for confirmation. Do not activate or place an order.`],
      de: [`Die Strategie für ${pair} ist gespeichert. Möchtest du einen Paper-Bot dafür vorbereiten?`, 'Paper-Bot vorbereiten', `Bereite einen Paper-Bot-Vorschlag für meine gespeicherte ${pair}-Strategie mit ID ${strategyId} für Setup ID ${setupId} vor. Frage nach fehlenden Risiko- und Budgetangaben und lege den Bot gesondert zur Bestätigung vor. Aktiviere nichts und platziere keine Order.`],
    }[language] || null;
    if (!copy) return null;
    return { question: copy[0], choices: [{ label: copy[1], reply: copy[2] }] };
  }
  return null;
}

export function affirmativeJourneyReply(input, messages) {
  if (!/^(?:ja|ja graag|graag|yes|yes please|sure|ok|okay|ja bitte)$/i.test(String(input || '').trim())) return null;
  const latest = Array.isArray(messages) ? messages.at(-1) : null;
  return latest?.role === 'assistant' && latest?.journeyGuidance
    ? latest.watchlistGuidance?.choices?.[0]?.reply || null : null;
}
