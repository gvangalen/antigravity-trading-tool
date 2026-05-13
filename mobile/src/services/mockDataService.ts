import { assistantApi } from './tradamindApi';
import { ChatMessage } from '../types/assistant';
import { TodayScores } from '../types/scores';
import { Strategy } from '../types/strategy';

const now = () => new Date().toISOString();

const wait = async (ms: number) => {
  await new Promise((resolve) => setTimeout(resolve, ms));
};

export async function getInitialChatMessages(): Promise<ChatMessage[]> {
  await wait(250);

  return [
    {
      id: 'assistant-1',
      role: 'assistant',
      content:
        'Goedemorgen. Ik bewaak vandaag macro, marktstructuur, technische setup en je actieve strategie. Stel je vraag voordat je een trade overweegt.',
      createdAt: now(),
    },
    {
      id: 'user-1',
      role: 'user',
      content: 'Wat is het belangrijkste aandachtspunt vandaag?',
      createdAt: now(),
    },
    {
      id: 'assistant-2',
      role: 'assistant',
      content:
        'De markt oogt constructief, maar niet euforisch. Wacht op bevestiging rond je entry zone en forceer geen positie bij dun volume.',
      createdAt: now(),
    },
  ];
}

export async function sendAssistantMessage(content: string): Promise<ChatMessage> {
  try {
    const response = await assistantApi.chat(content, {
      page_type: 'legacy_mobile_mock',
      symbol: 'BTC',
      timeframe: 'Daily',
    });

    return {
      id: response.trace_id || `assistant-${Date.now()}`,
      role: 'assistant',
      content: response.response,
      createdAt: now(),
    };
  } catch {
    await wait(700);

    return {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content:
        'Mock response: ik zie een gemengd maar beheersbaar marktbeeld. Houd de positie klein totdat setup en technical score allebei verbeteren.',
      createdAt: now(),
    };
  }
}

export async function getTodayScores(): Promise<TodayScores> {
  await wait(250);

  return {
    scores: [
      { label: 'Macro', value: 68, status: 'Neutral to supportive' },
      { label: 'Market', value: 74, status: 'Risk appetite improving' },
      { label: 'Technical', value: 71, status: 'Trend intact' },
      { label: 'Setup', value: 63, status: 'Wait for cleaner entry' },
    ],
    aiSummary:
      'Vandaag is het marktbeeld constructief, maar nog niet sterk genoeg om agressief te handelen. De beste aanpak is geduldig blijven en alleen actie nemen bij bevestiging.',
  };
}

export async function getActiveStrategy(): Promise<Strategy> {
  await wait(250);

  return {
    symbol: 'BTC/USDT',
    bias: 'Bullish, selective',
    entryZone: '67,800 - 68,600',
    targets: ['70,200', '72,000', '74,500'],
    stopLoss: '66,900',
    confidenceScore: 72,
    aiExplanation:
      'De trend blijft positief zolang BTC boven de entry zone stabiliseert. Momentum is aanwezig, maar de risk/reward verbetert pas na een gecontroleerde pullback.',
  };
}
