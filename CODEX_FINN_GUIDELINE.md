# Guidelines for Codex: Mobile Integration of FINN AI Assistant

This document serves as the **official contract, guidelines, and integration checklist** for the Mobile Client (React Native / Expo) to integrate the centralized AI Assistant **"FINN"** without duplicating orchestration or conversation logic.

---

## 1. Architectural Golden Rule

> [!IMPORTANT]
> **Mobile is purely a Rendering & Presentation Layer (View).**
> Do not implement conversation states, intent parsing, flow routing, or draft construction on the mobile side. All intelligence, prompts, state tracking, and drafts are generated and owned by the **FastAPI Backend Core**.

---

## 2. API Contract (The Single Source of Truth)

The mobile client must consume `/api/assistant/chat` (HTTP POST) or `/api/assistant/chat/stream` (SSE Stream). The finalized parsed envelope will always match the following schema:

```typescript
interface AssistantChatResponse {
  response: string;               // Conversational text (Markdown in Dutch)
  intent: string;                 // Classified query intent
  action: {                       // Navigation or side-effects triggers (Nullable)
    type: string;                 // e.g. 'navigate_to_page', 'add_to_watchlist'
    symbol?: string;              // e.g. 'SOL'
    params?: { [key: string]: any } // e.g. { path: '/setup' }
  } | null;
  draft: {                        // Prefilled configurations to confirm (Nullable)
    type: 'setup' | 'strategy' | 'bot';
    payload: any;                 // Complete payload matching setup/strategy schemas
  } | null;
  state: {                        // Current conversational session state (Nullable)
    current_flow: string;         // e.g. 'setup_creation'
    slots: { [key: string]: any }; // Gathered fields so far
    status: 'none' | 'collecting' | 'complete';
  } | null;
  reasoning: {                    // Internal diagnostics
    confidence_score: number;
    risk_detected: boolean;
    coaching_level: 'beginner' | 'advanced';
    reasons: string[];
  } | null;
  suggested_actions: string[] | null; // 2-3 Clickable quick follow-up chips
  trace_id: string;               // Correlation ID
}
```

---

## 3. Implementation Blueprint for Codex

To guarantee that FINN functions identically to the web dashboard, the mobile client should implement the following architectural patterns:

### A. Real-Time Streaming (SSE)
Use an SSE client for React Native (like `react-native-sse` or custom EventSource/fetch hooks) to connect to `/api/assistant/chat/stream`.
*   During streaming, render incoming `text` chunks in real-time in the current bubble.
*   Once the `envelope` event is received, replace or supplement the bubble state with the complete structured payload (extracting `suggested_actions`, `draft`, and `action`).

### B. Suggested Action Chips (`suggested_actions`)
*   When `suggested_actions` is populated (e.g. `["Kies DCA setup", "Kies Trade setup"]`), render them as **horizontal scrolling quick chips** directly under the last chat bubble.
*   Pressing a chip should trigger a standard send request to the backend with that text query, exactly as if the user typed it.

### C. Client-Side Page Navigation Whitelist (`action`)
When `action.type === 'navigate_to_page'`, parse the `action.params.path` and translate the web-whitelist paths to native screen navigations:

| Web Whitelist Path | Mobile Target Screen / Navigation Destination |
| :--- | :--- |
| `/dashboard` | `navigation.navigate('MainTabs', { screen: 'Dashboard' })` |
| `/macro` | `navigation.navigate('MacroScreen')` |
| `/technical` | `navigation.navigate('TechnicalScreen')` |
| `/bot` | `navigation.navigate('BotScreen')` |
| `/strategy` | `navigation.navigate('StrategyScreen')` |
| `/setup` | `navigation.navigate('SetupScreen')` |
| `/report` | `navigation.navigate('ReportScreen')` |
| `/profile` | `navigation.navigate('ProfileScreen')` |

### D. Form Concept Confirmation Sheets (`draft`)
When `draft` is present, render a mobile-optimized premium **Bottom Sheet Drawer** (e.g., using `@gorhom/bottom-sheet` or a native modal drawer):
1.  **Read values from `draft.payload`:** Display prefilled inputs (e.g., Target Asset, Budget, Timeframe, Macro limits) to let the user inspect the draft.
2.  **Confirming:** When the user hits "Confirm/Save", execute the corresponding POST request to the backend setups/strategies endpoints (e.g., `/api/setups/create` or `/api/bots/create`) using the payload.
3.  **Stateless:** The Bottom Sheet is purely a form viewer/editor. It does not contain prompt logic.

---

## 4. Dos and Don'ts for Codex

*   **DON'T** write prompt-based conditional UI. (e.g., *Never do:* `if (response.includes("DCA")) showDcaCard()`). Use the structural `draft` object.
*   **DO** let the backend handle flow cancellations. If the user types "laat maar" or "stop", the backend will clear the Postgres state and return the correct cancellation response and suggested actions. The mobile app just renders whatever the backend tells it.
*   **DO** use haptic feedback (`expo-haptics`) when tapping Suggested Action Chips or confirming a Draft Bottom Sheet to give it a native premium feel.
*   **DO** cache the JWT authentication token securely (`secure-store`) and pass it in the `Authorization: Bearer <token>` header of every chat request so that the backend can resolve the user's Postgres session and active profile.
