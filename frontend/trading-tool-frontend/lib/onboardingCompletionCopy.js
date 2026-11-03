export function onboardingCompletionDescription(copy, status) {
  if (status?.has_strategy && status?.has_bot) return copy?.completeDescriptionWithStrategyAndBot || copy?.completeDescription;
  if (status?.has_strategy) return copy?.completeDescriptionWithStrategy || copy?.completeDescription;
  if (status?.has_bot) return copy?.completeDescriptionWithBot || copy?.completeDescription;
  return copy?.completeDescription;
}
