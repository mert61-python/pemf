import { StyleSheet, Text } from "react-native";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography } from "@/theme/tokens";

export function PlaceholderScreen({ title, body }: { title: string; body: string }) {
  return (
    <Card style={styles.card}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.body}>{body}</Text>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.md
  },
  title: {
    color: colors.text,
    fontSize: typography.title,
    fontWeight: "800"
  },
  body: {
    color: colors.textMuted,
    fontSize: typography.body
  }
});
