export function inactiveProposalIds(proposalIds, settledResults) {
  return new Set(proposalIds.filter((proposalId, index) =>
    settledResults[index]?.status === "fulfilled"
    && !["draft", "pending_confirmation"].includes(settledResults[index].value?.status)
  ));
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
