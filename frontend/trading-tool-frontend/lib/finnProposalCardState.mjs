export function inactiveProposalIds(proposalIds, settledResults) {
  return new Set(proposalIds.filter((proposalId, index) =>
    settledResults[index]?.status === "fulfilled"
    && !["draft", "pending_confirmation"].includes(settledResults[index].value?.status)
  ));
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

export function verifiedPaperBotStrategy({ target, draftStrategyId, ownerStrategies }) {
  const proposalId = Number(target?.target_id);
  const draftId = Number(draftStrategyId);
  if (target?.target_type !== "strategy"
      || !Number.isSafeInteger(proposalId) || proposalId <= 0
      || !Number.isSafeInteger(draftId) || draftId !== proposalId) return null;
  return ownerStrategies.find((item) => Number(item.id || item.strategy_id) === proposalId) || null;
}
