export function inactiveProposalIds(proposalIds, settledResults) {
  return new Set(proposalIds.filter((proposalId, index) =>
    settledResults[index]?.status === "fulfilled"
    && !["draft", "pending_confirmation"].includes(settledResults[index].value?.status)
  ));
}

export function setupDraftFrequencyLabel(supplied, translate) {
  if (supplied?.setup_type !== "dca") return "";
  const label = (value) => {
    if (typeof value !== "string" && typeof value !== "number") return null;
    const normalized = String(value).trim();
    return normalized ? translate(normalized) : null;
  };
  return [label(supplied.dca_frequency), label(supplied.dca_day || supplied.dca_month_day)]
    .filter(Boolean).join(" · ");
}

export function suspendedProposalIds(proposalIds, settledResults, clarificationRequired = false) {
  return new Set(proposalIds.filter((_, index) =>
    settledResults[index]?.status !== "fulfilled"
    || (clarificationRequired
      && ["draft", "pending_confirmation"].includes(settledResults[index].value?.status))
  ));
}

export function isFinnProposalCorrection(message) {
  const text = String(message || "").trim();
  // Only a direct revision command can suspend a confirmable proposal. A
  // question about a possible change is still a read-only coach turn.
  return !text.includes("?") && /^(?:(?:corrigeer|correctie|wijzig|verander|pas\s+(?:het|de|dit|deze|mijn)\b|maak\s+(?:er|het|de)\b|noem\s+(?:de|het)\b|correct|change|update|modify|ändere|korrigiere)\b|(?:de|the)\s+(?:naam|name)\s+(?:is|moet|should)\b)/i.test(text);
}

export function suspendFinnProposalCards(messages, proposalIds) {
  if (!proposalIds.size) return messages;
  return messages.map((message) => {
    const proposalId = (message.actions || []).find((action) => action?.type === "v2_proposal")?.proposal_id;
    return proposalIds.has(proposalId)
      ? { ...message, confirmationSuspended: true }
      : message;
  });
}

export function retireFinnProposalCards(messages, proposalIds) {
  if (!proposalIds.size) return messages;
  return messages.map((message) => {
    const proposalId = (message.actions || []).find((action) => action?.type === "v2_proposal")?.proposal_id;
    if (!proposalIds.has(proposalId)) return message;
    return {
      ...message,
      actions: [],
      canConfirm: false,
      setupDraft: null,
      actionDraft: null,
      state: { ...(message.state || {}), setup_draft: null, action_draft: null },
      proposalRetired: true,
    };
  });
}

// A guided follow-up can return the existing proposal ID again. Keep the
// explanation in chat history, but only the latest turn may offer Confirm.
export function retireEarlierFinnProposalCards(messages, streamId, proposalId) {
  if (!proposalId) return messages;
  return messages.map((message) => message.streamId === streamId
    ? message
    : retireFinnProposalCards([message], new Set([proposalId]))[0]);
}

export function verifiedPaperBotStrategy({ target, draftStrategyId, ownerStrategies }) {
  const proposalId = Number(target?.target_id);
  const draftId = Number(draftStrategyId);
  if (target?.target_type !== "strategy"
      || !Number.isSafeInteger(proposalId) || proposalId <= 0
      || !Number.isSafeInteger(draftId) || draftId !== proposalId) return null;
  return ownerStrategies.find((item) => Number(item.id || item.strategy_id) === proposalId) || null;
}

// Conversation history may restore only the latest owner-scoped, unexpired
// proposal. No confirmation token is stored in the browser; Confirm always
// rereads the proposal and uses the server's publish/confirm/execute path.
export function mapBackendSessionMessages(messages = []) {
  return (Array.isArray(messages) ? messages : [])
    .filter((message) => typeof message?.content === "string" && message.content.trim())
    .map((message) => {
      const base = {
        role: message.role === "user" ? "user" : "assistant",
        text: message.content,
        isComplete: true,
      };
      const pending = message.role === "assistant" ? message.pending_proposal : null;
      const operationId = String(pending?.operation_id || "");
      const draft = pending?.draft;
      if (!pending?.proposal_id || !operationId || !draft
          || draft.operation_id !== operationId || (draft.missing_inputs || []).length) return base;
      const supplied = draft.supplied_inputs || {};
      const isSetup = operationId === "create_setup";
      const isDraftCard = isSetup || ["create_strategy", "create_bot", "watchlist_add", "watchlist_remove",
        "create_indicator_configuration", "update_indicator_configuration", "delete_indicator_configuration"].includes(operationId);
      const confirmationSuspended = operationId === "create_bot" && !supplied.strategy_name;
      return {
        ...base,
        setupDraft: isSetup ? draft : null,
        actionDraft: !isSetup && isDraftCard ? draft : null,
        canConfirm: !confirmationSuspended,
        confirmationSuspended,
        state: {
          run_status: "completed",
          setup_draft: isSetup ? draft : null,
          action_draft: !isSetup && isDraftCard ? draft : null,
        },
        actions: [{
          type: "v2_proposal",
          proposal_id: pending.proposal_id,
          requires_confirmation: true,
          display_context: {
            conversation_id: pending.conversation_id,
            run_id: pending.run_id,
            operation_id: operationId,
            name: supplied.name,
            symbol: supplied.symbol || pending.asset,
            timeframe: supplied.timeframe,
            setup_name: supplied.setup_name,
            strategy_name: supplied.strategy_name,
            supplied_inputs: supplied,
            before_state: pending.before_state || {},
            requested_state: pending.requested_state || {},
            changed_fields: pending.requested_state || {},
            safety_mode: operationId === "create_bot" ? "Paper · niet-live" : null,
          },
        }],
      };
    });
}
