export type ChatRole = 'assistant' | 'user';

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
};

export type AssistantChatRequest = {
  query?: string;
  message: string;
  context?: AssistantRuntimeContext;
  history?: AssistantHistoryMessage[];
};

export type AssistantChatResponse = {
  message: ChatMessage;
};

export type AssistantHistoryMessage = {
  role: ChatRole;
  text: string;
};

export type AssistantRuntimeContext = {
  page_type?: string;
  symbol?: string;
  timeframe?: string;
  setup_name?: string;
};

export type AssistantReasoning = {
  confidence_score: number;
  risk_detected: boolean;
  reasons: string[];
  coaching_level: string;
};

export type AssistantAction =
  | {
      type:
        | 'add_to_watchlist'
        | 'remove_from_watchlist'
        | 'open_setup_page'
        | 'generate_strategy'
        | 'open_bot_draft'
        | 'navigate_to_page';
      symbol?: string;
      params?: Record<string, unknown>;
      description?: string;
    }
  | {
      type: 'bundle';
      actions: AssistantAction[];
      symbol?: string;
      params?: Record<string, unknown>;
    };

export type AssistantDraft = {
  type: 'setup' | 'strategy' | 'bot';
  payload: Record<string, unknown>;
};

export type AssistantConversationState = {
  current_flow: string;
  asset?: string;
  slots: Record<string, unknown>;
  missing_slots?: string[];
  status: 'collecting' | 'complete' | 'none';
};

export type AssistantEnvelope = {
  response: string;
  intent?: string;
  flow?: string;
  action?: AssistantAction | null;
  draft?: AssistantDraft | null;
  state?: AssistantConversationState | null;
  reasoning?: AssistantReasoning | null;
  trace_id?: string | null;
  summary?: string | null;
  risk_summary?: string | null;
  next_best_action?: string | null;
  review_reason?: string | null;
};

export type AssistantFeedItem =
  | {
      id: string;
      type: 'message';
      role: ChatRole;
      text: string;
      summary?: string | null;
      riskSummary?: string | null;
      nextBestAction?: string | null;
      reviewReason?: string | null;
      flow?: string | null;
      intent?: string | null;
    }
  | {
      id: string;
      type: 'action';
      title: string;
      reason: string;
      impact: string;
      primaryAction: string;
    }
  | {
      id: string;
      type: 'draft';
      draft: AssistantDraft;
    }
  | {
      id: string;
      type: 'state';
      state: AssistantConversationState;
    }
  | {
      id: string;
      type: 'reasoning';
      reasoning: AssistantReasoning;
    };
