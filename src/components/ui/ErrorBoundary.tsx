import React from "react";
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from "react-native";
import { colors, spacing, typography, radius } from "@/theme/tokens";

interface State {
  hasError: boolean;
  error?: Error;
}

/** Uygulama genelinde React hata sınırı — bir ekran çökse bile beyaz-ekran yerine
 *  kurtarılabilir bir hata kartı gösterir (tıbbi cihazda donup kalma önlenir). */
export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("ErrorBoundary yakaladı:", error, info?.componentStack);
  }

  reset = () => this.setState({ hasError: false, error: undefined });

  render() {
    if (this.state.hasError) {
      return (
        <View style={styles.container}>
          <Text style={styles.icon}>⚠️</Text>
          <Text style={styles.title}>Beklenmeyen bir hata oluştu</Text>
          <ScrollView style={styles.msgBox} contentContainerStyle={{ padding: spacing.sm }}>
            <Text style={styles.msg}>{this.state.error?.message || "Bilinmeyen hata."}</Text>
          </ScrollView>
          <TouchableOpacity style={styles.btn} onPress={this.reset} accessibilityRole="button">
            <Text style={styles.btnText}>Tekrar Dene</Text>
          </TouchableOpacity>
        </View>
      );
    }
    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.md },
  icon: { fontSize: 48 },
  title: { color: colors.text, fontSize: typography.title, fontWeight: "800", textAlign: "center" },
  msgBox: { maxHeight: 160, alignSelf: "stretch", backgroundColor: colors.bgAlt, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  msg: { color: colors.textMuted, fontSize: typography.small, fontFamily: "monospace" },
  btn: { backgroundColor: colors.primary, paddingVertical: spacing.md, paddingHorizontal: spacing.xl, borderRadius: radius.md, marginTop: spacing.sm },
  btnText: { color: colors.white, fontSize: typography.body, fontWeight: "700" },
});
