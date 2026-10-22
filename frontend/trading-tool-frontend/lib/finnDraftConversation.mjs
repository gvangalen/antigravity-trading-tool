const COPY = Object.freeze({
  nl: { hint: 'Kies een antwoord of typ je eigen antwoord in de chat.', freeTextHint: 'Typ je antwoord in de chat.', weekly: 'Wekelijks', monthly: 'Maandelijks', fixed: 'Vast bedrag', smart: 'Variabel bedrag op basis van de benchmark', custom: 'Variabel bedrag volgens een curve', dca: 'DCA', trade: 'Trade', cautious: 'Voorzichtig', balanced: 'Gebalanceerd', aggressive: 'Offensief', market: 'Markt', macro: 'Macro', technical: 'Technisch', other: 'Anders · typ in de chat' },
  en: { hint: 'Choose an answer or type your own reply in the chat.', freeTextHint: 'Type your answer in the chat.', weekly: 'Weekly', monthly: 'Monthly', fixed: 'Fixed amount', smart: 'Variable amount based on the benchmark', custom: 'Variable amount using a curve', dca: 'DCA', trade: 'Trade', cautious: 'Cautious', balanced: 'Balanced', aggressive: 'Aggressive', market: 'Market', macro: 'Macro', technical: 'Technical', other: 'Other · type in chat' },
  de: { hint: 'Wähle eine Antwort oder schreibe deine eigene Antwort im Chat.', freeTextHint: 'Schreibe deine Antwort im Chat.', weekly: 'Wöchentlich', monthly: 'Monatlich', fixed: 'Fester Betrag', smart: 'Variabler Betrag nach Benchmark', custom: 'Variabler Betrag nach Kurve', dca: 'DCA', trade: 'Trade', cautious: 'Vorsichtig', balanced: 'Ausgewogen', aggressive: 'Offensiv', market: 'Markt', macro: 'Makro', technical: 'Technisch', other: 'Anders · im Chat schreiben' },
});

export function draftConversationCopy(locale = 'nl') {
  return COPY[String(locale).split('-')[0]] || COPY.nl;
}

export function draftMissingField(message) {
  const draft = message?.setupDraft || message?.actionDraft || message?.state?.setup_draft || message?.state?.action_draft;
  const missing = draft?.missing_inputs || message?.state?.missing_required_inputs || message?.state?.missing_slots || message?.missingFields || [];
  const next = draft?.next_missing_input || message?.state?.next_missing_input || message?.nextQuestion;
  const field = (typeof next === 'string' && /^[a-z][\w.]*$/i.test(next) ? next : null)
    || missing.find((value) => value !== 'plan_deviation_ack');
  return typeof field === 'string' ? field.split('.').at(-1) : null;
}

export function draftQuestionChoices(message, locale = 'nl') {
  const field = draftMissingField(message);
  const copy = draftConversationCopy(locale);
  const optionField = { setup_id: 'setup_options', strategy_id: 'strategy_options', indicator: 'indicator_options' }[field];
  const options = optionField ? message?.state?.[optionField] : null;
  if (Array.isArray(options) && options.length > 0) {
    const kind = field === 'setup_id' ? 'setup' : field === 'strategy_id' ? 'strategy' : null;
    return options.slice(0, 3).map((option) => ({
      label: option.name || option.display_name || String(option.id || ''),
      reply: kind && option.id ? `${kind} ${option.id}` : String(option.name || ''),
    })).filter((option) => option.label && option.reply);
  }
  const choices = {
    dca_frequency: ['weekly', 'monthly'],
    frequency: ['weekly', 'monthly'],
    dca_amount_mode: ['fixed', 'smart'],
    execution_mode: ['fixed', 'custom'],
    setup_type: ['dca', 'trade'],
    risk_profile: ['cautious', 'balanced', 'aggressive'],
    category: ['market', 'macro', 'technical'],
  }[field] || [];
  const reply = { weekly: copy.weekly, monthly: copy.monthly, fixed: copy.fixed, smart: 'Smart DCA', custom: copy.custom, dca: copy.dca, trade: copy.trade, cautious: copy.cautious, balanced: copy.balanced, aggressive: copy.aggressive, market: copy.market, macro: copy.macro, technical: copy.technical };
  return choices.map((choice) => ({ label: copy[choice], reply: reply[choice] }));
}

export function isOpenClarification(message) {
  if (message?.state?.run_status !== 'clarification_required') return false;
  return Boolean(message.state.clarification || !isCollectingDraft(message));
}

export function clarificationQuestionChoices(message) {
  if (!isOpenClarification(message)) return [];
  const clarification = message?.state?.clarification;
  const names = clarification?.choices;
  if (!Array.isArray(names) || names.length < 1 || names.length > 3) return [];
  const choices = names.map((name) => typeof name === 'string' ? name.trim() : '');
  if (choices.some((name) => !name || name.length > 80)) return [];
  if (new Set(choices.map((name) => name.toLocaleLowerCase())).size !== choices.length) return [];
  return choices.map((name) => ({ label: name, reply: name }));
}

export function hasConfirmableDraft(message) {
  const proposal = (message?.actions || []).some((action) => action?.type === 'v2_proposal' && action?.proposal_id);
  const draft = message?.setupDraft || message?.actionDraft || message?.state?.setup_draft || message?.state?.action_draft;
  if (draft) return proposal && !(draft.missing_inputs || []).length && message?.state?.status !== 'collecting' && message?.state?.run_status !== 'clarification_required';
  if (message?.draft) return message.state?.status !== 'collecting' && message.canConfirm !== false;
  return false;
}

export function isCollectingDraft(message) {
  if (hasConfirmableDraft(message)) return false;
  const draft = message?.setupDraft || message?.actionDraft || message?.state?.setup_draft || message?.state?.action_draft;
  if (draft) return Boolean((draft.missing_inputs || []).length || draft.draft_status === 'collecting' || message?.state?.status === 'collecting' || message?.state?.run_status === 'clarification_required');
  return Boolean(
    (message?.draft && (message?.canConfirm === false || message?.state?.status === 'collecting')) ||
    (message?.state?.current_flow && message?.state?.status === 'collecting')
  );
}
