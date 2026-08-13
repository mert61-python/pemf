// Author: mertaygn, cglrgrkn
import React from "react";
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from "react-native";
import { colors, spacing, typography, radius, rf, rs } from "@/theme/tokens";
import { apiPost } from "@/services/apiClient";

interface State {
  hasError: boolean;
  error?: Error;
}

// YÜKSEK fix — GLOBAL (React-DIŞI) hata ağı: ErrorBoundary yalnız RENDER-fazı hatalarını yakalar.
// Event-handler / setTimeout / promise içindeki uncaught throw sınırı ATLAR → tıbbi cihazda tedavi
// sırasında tüm app çökebilir + /client/error raporu GİTMEZDİ. Aşağıdaki handler bunları da yakalayıp
// aynı sink'e best-effort raporlar. Yalnız BİR KEZ kurulur; native'de mevcut RN handler'ı KORUNUR.
let _globalHandlerInstalled = false;
// #93 (KVKK): hata mesajı/stack'i düz-metin kalıcı /client/error jsonl'ine yazılıyor → hasta PII
// (e-posta/telefon/TC) sızabilir. Rapordan ÖNCE bilinen PII kalıplarını maskele + kırp.
function _redactPII(s: string): string {
  return String(s || "")
    .replace(/[\w.+-]+@[\w.-]+\.\w{2,}/g, "[email]")   // e-posta
    .replace(/\b\d{10,}\b/g, "[num]")                   // TC/telefon/uzun sayı
    .slice(0, 2000);
}
function reportGlobalError(message: string, stack: string) {
  try {
    const route = typeof window !== "undefined" ? (window.location?.hash || window.location?.pathname || "") : "";
    apiPost("/client/error", { message: _redactPII(message), stack: _redactPII(stack), route: `[global] ${route}` }, null, { silent: true }).catch(() => {});
  } catch { /* raporlama best-effort — asla akışı bozma */ }
}
function installGlobalErrorHandler() {
  if (_globalHandlerInstalled) return;
  _globalHandlerInstalled = true;
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    window.addEventListener("error", (e: any) => reportGlobalError(e?.message || "window.onerror", e?.error?.stack || ""));
    window.addEventListener("unhandledrejection", (e: any) => reportGlobalError("unhandledrejection: " + String(e?.reason?.message ?? e?.reason ?? ""), e?.reason?.stack || ""));
  }
  const g: any = typeof global !== "undefined" ? global : undefined;
  if (g?.ErrorUtils?.getGlobalHandler && g?.ErrorUtils?.setGlobalHandler) {
    const prev = g.ErrorUtils.getGlobalHandler();
    g.ErrorUtils.setGlobalHandler((error: any, isFatal?: boolean) => {
      reportGlobalError(`[${isFatal ? "FATAL" : "non-fatal"}] ${String(error?.message ?? error ?? "")}`, String(error?.stack || ""));
      if (typeof prev === "function") prev(error, isFatal); // orijinal RN handler (red-box/crash raporu) korunur
    });
  }
}
installGlobalErrorHandler();

/** Uygulama genelinde React hata sınırı — bir ekran çökse bile beyaz-ekran yerine
 *  kurtarılabilir bir hata kartı gösterir (tıbbi cihazda donup kalma önlenir). */
export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("ErrorBoundary yakaladı:", error, info?.componentStack);
    // F-7: crash'i backend'e fire-and-forget raporla (client_errors.jsonl) — tıbbi cihaz crash
    // görünürlüğü; konsol kapanınca iz kalsın. Raporlama best-effort, ASLA ErrorBoundary'yi bozmaz.
    try {
      const route =
        typeof window !== "undefined" ? window.location?.hash || window.location?.pathname || "" : "";
      apiPost(
        "/client/error",
        {
          message: _redactPII(String(error?.message || error || "")),  // #93: PII maskele
          stack: _redactPII(String(info?.componentStack || error?.stack || "")),
          route,
        },
        null,
        { silent: true },
      ).catch(() => {});
    } catch {
      /* raporlama başarısız olsa da hata kartı gösterilir */
    }
  }

  reset = () => this.setState({ hasError: false, error: undefined });

  render() {
    if (this.state.hasError) {
      return (
        <View style={styles.container}>
          <Text style={styles.icon}>⚠️</Text>
          <Text style={styles.title}>Beklenmeyen bir hata oluştu</Text>
          {/* #93 maskelemesi yalnız BACKEND'e giden kopyaya uygulanıyordu; ekrandaki metin hamdı.
              Hata mesajı hasta adı/e-posta/telefon içerebilir ve bu ekran ekran-görüntüsü alınıp
              destek kanallarına gönderiliyor. Aynı maskeyi görünen metne de uygula. */}
          <ScrollView style={styles.msgBox} contentContainerStyle={{ padding: spacing.sm }}>
            <Text style={styles.msg}>{_redactPII(String(this.state.error?.message || "")) || "Bilinmeyen hata."}</Text>
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
  icon: { fontSize: rf(48) },
  title: { color: colors.text, fontSize: typography.title, fontWeight: "800", textAlign: "center" },
  msgBox: { maxHeight: rs(160), alignSelf: "stretch", backgroundColor: colors.bgAlt, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  msg: { color: colors.textMuted, fontSize: typography.small, fontFamily: "monospace" },
  btn: { backgroundColor: colors.primary, paddingVertical: spacing.md, paddingHorizontal: spacing.xl, borderRadius: radius.md, marginTop: spacing.sm },
  btnText: { color: colors.white, fontSize: typography.body, fontWeight: "700" },
});
