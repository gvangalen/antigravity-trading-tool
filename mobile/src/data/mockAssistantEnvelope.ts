import { AssistantEnvelope } from '../types/assistant';

export const mockAssistantEnvelope: AssistantEnvelope = {
  response:
    'De setup is nog geldig, maar ik zou vandaag niet agressief verhogen. De beste actie is reviewen, wachten op bevestiging, of een kleinere positie plannen.',
  intent: 'decision',
  action: {
    type: 'open_bot_draft',
    symbol: 'BTC',
    description: 'Bot context is ready, but execution remains gated behind review.',
  },
  draft: {
    type: 'strategy',
    payload: {
      name: 'BTC Controlled Pullback Strategy',
      symbol: 'BTC',
      setup_type: 'trade',
      base_amount: 100,
      entry: 68420,
      targets: [70200, 72000],
      stop_loss: 66900,
    },
  },
  state: {
    current_flow: 'strategy_creation',
    asset: 'BTC',
    status: 'collecting',
    slots: {
      symbol: 'BTC',
      setup_type: 'trade',
      base_amount: 100,
    },
    missing_slots: ['entry', 'targets', 'stop_loss'],
  },
  reasoning: {
    confidence_score: 74,
    risk_detected: true,
    reasons: ['Entry is close to resistance', 'Setup confirmation is incomplete'],
    coaching_level: 'intermediate',
  },
  trace_id: 'mock-trdm-envelope-001',
};
