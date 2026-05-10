export type ChatRole = 'assistant' | 'user';

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
};

export type AssistantChatRequest = {
  message: string;
};

export type AssistantChatResponse = {
  message: ChatMessage;
};
