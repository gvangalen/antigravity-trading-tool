import { Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../../constants/theme';
import { triggerHaptic } from '../../utils/haptics';

type SuggestedPromptChipsProps = {
  prompts: string[];
  onSelect: (prompt: string) => void;
};

export function SuggestedPromptChips({ prompts, onSelect }: SuggestedPromptChipsProps) {
  return (
    <View style={styles.promptRow}>
      {prompts.map((prompt) => (
        <Pressable
          key={prompt}
          onPress={async () => {
            await triggerHaptic('selection');
            onSelect(prompt);
          }}
          style={({ pressed }) => [styles.prompt, pressed && styles.pressed]}
        >
          <Text style={styles.promptText}>{prompt}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  pressed: {
    opacity: 0.84,
  },
  prompt: {
    backgroundColor: theme.colors.surfaceMuted,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  promptRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  promptText: {
    color: theme.colors.textSoft,
    fontSize: 12,
    fontWeight: '900',
  },
});
