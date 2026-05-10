import { AssistantChatRequest, AssistantChatResponse } from '../types/assistant';

const API_BASE_URL = 'http://localhost:8000';

class APIClient {
  async postAssistantChat(request: AssistantChatRequest): Promise<AssistantChatResponse> {
    const response = await fetch(`${API_BASE_URL}/api/assistant/chat`, {
      body: JSON.stringify(request),
      headers: {
        'Content-Type': 'application/json',
      },
      method: 'POST',
    });

    if (!response.ok) {
      throw new Error('Assistant chat request failed');
    }

    return response.json();
  }
}

export const apiClient = new APIClient();
