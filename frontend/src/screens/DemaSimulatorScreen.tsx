import React from "react";
import { StyleSheet, View, Platform, Text } from "react-native";
import { WebView } from "react-native-webview";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography } from "@/theme/tokens";
import { serviceConfig } from "@/services/config";

export function DemaSimulatorScreen() {
  // apiBaseUrl http://127.0.0.1:8000/api ise, simulator root path'tedir.
  // /api 'yi kaldırıp /simulator/index.html ekliyoruz.
  const baseUrl = serviceConfig.apiBaseUrl.replace("/api", "");
  const simulatorUrl = `${baseUrl}/simulator/index.html`;

  return (
    <View style={styles.container}>
      <Card style={styles.headerCard}>
        <Text style={styles.title}>DEMA Terapi Simülatörü</Text>
        <Text style={styles.muted}>
          Orijinal simülasyon motoru. Manyetik alan etkileşimlerini canlı olarak izleyebilirsiniz.
        </Text>
      </Card>
      
      <View style={styles.simulatorContainer}>
        {Platform.OS === "web" ? (
          <iframe 
            src={simulatorUrl} 
            style={{ width: "100%", height: "100%", border: "none", borderRadius: 8 }} 
            title="DEMA Simulator"
          />
        ) : (
          <WebView 
            source={{ uri: simulatorUrl }} 
            style={styles.webview} 
            javaScriptEnabled={true}
          />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    gap: spacing.lg,
  },
  headerCard: {
    gap: spacing.xs,
  },
  title: {
    color: colors.text,
    fontSize: typography.title,
    fontWeight: "800",
  },
  muted: {
    color: colors.textMuted,
    fontSize: typography.body,
  },
  simulatorContainer: {
    flex: 1,
    minHeight: 500,
    backgroundColor: colors.bgAlt,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 8,
    overflow: "hidden",
  },
  webview: {
    flex: 1,
    backgroundColor: "transparent",
  }
});
