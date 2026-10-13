import type { AssistantEnvelope } from '../types/assistant';

export type DraftChoice = { label: string; reply: string };

export function isDraftCorrectionIntent(message: string): boolean {
  const text = String(message || '').trim();
  return !text.includes('?') && /^(?:(?:corrigeer|wijzig|verander|pas\s+(?:het|de|dit|deze|mijn)\b|maak\s+(?:er|het|de)\b|noem\s+(?:de|het)\b|correct|change|update|modify|ändere|korrigiere)\b|(?:de|the)\s+(?:naam|name)\s+(?:is|moet|should)\b)/i.test(text);
}

export function draftOtherLabel(language = 'nl'): string {
  return ({ nl: 'Anders · typ in de chat', en: 'Other · type in chat', de: 'Anders · im Chat schreiben' } as Record<string, string>)[language] || 'Anders · typ in de chat';
}

const COPY = {
  nl: { weekly: 'Wekelijks', monthly: 'Maandelijks', fixed: 'Vast bedrag', smart: 'Variabel bedrag op basis van de benchmark', custom: 'Variabel bedrag volgens een curve', dca: 'DCA', trade: 'Trade', cautious: 'Voorzichtig', balanced: 'Gebalanceerd', aggressive: 'Offensief', market: 'Markt', macro: 'Macro', technical: 'Technisch' },
  en: { weekly: 'Weekly', monthly: 'Monthly', fixed: 'Fixed amount', smart: 'Variable amount based on the benchmark', custom: 'Variable amount using a curve', dca: 'DCA', trade: 'Trade', cautious: 'Cautious', balanced: 'Balanced', aggressive: 'Aggressive', market: 'Market', macro: 'Macro', technical: 'Technical' },
  de: { weekly: 'Wöchentlich', monthly: 'Monatlich', fixed: 'Fester Betrag', smart: 'Variabler Betrag nach Benchmark', custom: 'Variabler Betrag nach Kurve', dca: 'DCA', trade: 'Trade', cautious: 'Vorsichtig', balanced: 'Ausgewogen', aggressive: 'Offensiv', market: 'Markt', macro: 'Makro', technical: 'Technisch' },
} as const;

export function canReviewDraft(envelope: AssistantEnvelope): boolean {
  return Boolean(envelope.draft) && envelope.state?.status !== 'collecting' && !(envelope.state?.missing_slots || []).length && envelope.can_confirm !== false;
}

export function draftChoices(envelope: AssistantEnvelope, language = 'nl'): DraftChoice[] {
  if (envelope.state?.status !== 'collecting') return [];
  const field = String(envelope.state?.next_missing_input || envelope.state?.missing_slots?.[0] || envelope.next_question || '').split('.').pop();
  const optionField = ({ setup_id: 'setup_options', strategy_id: 'strategy_options', indicator: 'indicator_options' } as const)[field as 'setup_id' | 'strategy_id' | 'indicator'];
  const options = optionField ? envelope.state?.[optionField] : null;
  if (Array.isArray(options) && options.length > 0 && options.length <= 3) {
    const kind = field === 'setup_id' ? 'setup' : field === 'strategy_id' ? 'strategy' : null;
    return options.map((option) => ({
      label: option.name || option.display_name || String(option.id),
      reply: kind ? `${kind} ${option.id}` : String(option.name || option.display_name || ''),
    })).filter((choice) => choice.reply);
  }
  const copy = COPY[language as keyof typeof COPY] || COPY.nl;
  const keys = ({
    dca_frequency: ['weekly', 'monthly'],
    frequency: ['weekly', 'monthly'],
    dca_amount_mode: ['fixed', 'smart'],
    execution_mode: ['fixed', 'custom'],
    setup_type: ['dca', 'trade'],
    risk_profile: ['cautious', 'balanced', 'aggressive'],
    category: ['market', 'macro', 'technical'],
  } as Record<string, (keyof typeof COPY.nl)[]>)[field || ''] || [];
  const replies: Record<string, string> = { weekly: copy.weekly, monthly: copy.monthly, fixed: copy.fixed, smart: 'Smart DCA', custom: copy.custom, dca: copy.dca, trade: copy.trade, cautious: copy.cautious, balanced: copy.balanced, aggressive: copy.aggressive, market: copy.market, macro: copy.macro, technical: copy.technical };
  return keys.map((key) => ({ label: copy[key], reply: replies[key] }));
}
