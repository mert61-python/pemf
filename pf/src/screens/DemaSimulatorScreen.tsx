// Author: mertaygn, cglrgrkn
import React, { useState } from "react";
import { StyleSheet, View, Platform, Text, TouchableOpacity, useWindowDimensions, ActivityIndicator } from "react-native";
import { WebView } from "react-native-webview";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography, radius, rf, rs } from "@/theme/tokens";
import { serviceConfig } from "@/services/config";
import { RefreshCcw } from "lucide-react-native";
import { EFieldBar } from "@/components/domain/EFieldBar";

export function DemaSimulatorScreen() {
  const [key, setKey] = useState(0); // WebView'ı yeniden yüklemek için
  // İlk açılışta simülatör (ayrı Vite app) yavaş yüklenir → boş kutu yerine "yükleniyor" göster.
  const [loading, setLoading] = useState(true);
  const { height } = useWindowDimensions();
  // Yenile: overlay'i tekrar göster + iframe/WebView'i remount et.
  const reload = () => { setLoading(true); setKey(k => k + 1); };
  // KÖK NEDEN: WebView dikey dokunuş jestlerini yutuyor → ne dış ScrollView ne de simülatör
  // kayıyordu; ayrıca sabit yükseklik simülatör sayfasından kısaydı → alt kontroller kesik.
  // ÇÖZÜM: WebView'i İÇERİĞİNİN TAM yüksekliğine büyüt (postMessage ile ölç) + nestedScrollEnabled
  // → dış AppShell ScrollView'i tüm sayfayı kaydırır, WebView scroll'u kilitlemez. Ölçüm gelene
  // kadar cömert fallback (kesilme yerine fazladan boşluk daha iyi).
  const [webHeight, setWebHeight] = useState(Math.max(640, Math.round(height * 0.78)));

  // apiBaseUrl'den base URL'yi çıkar: http://IP:8000/api → http://IP:8000
  const baseUrl = serviceConfig.apiBaseUrl
    .replace(/\/api\/?$/, "")       // /api sonunu kaldır
    .replace(/\/$/, "");            // trailing slash kaldır
  const simulatorUrl = `${baseUrl}/simulator/index.html`;

  return (
    <View style={styles.container}>
      <Card style={styles.headerCard}>
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.title}>DEMA Terapi Simülatörü</Text>
            <Text style={styles.muted}>
              Manyetik alan etkileşimlerini canlı olarak izleyebilirsiniz.
            </Text>
          </View>
          <TouchableOpacity style={styles.refreshBtn} onPress={reload} accessibilityRole="button" accessibilityLabel="Simülatörü yeniden yükle">
            <RefreshCcw color={colors.textMuted} size={18} />
          </TouchableOpacity>
        </View>
        <Text style={styles.urlText}>{simulatorUrl}</Text>
      </Card>

      {/* CANLI E-ALANI (2026-08-06): simülatörün yanında gerçek cihazın ürettiği alan.
          Analiz bağlamı + aktif seans yoksa kendini render ETMEZ (bkz. EFieldBar). */}
      <EFieldBar />

      <View style={[styles.simulatorContainer, { height: webHeight }]}>
        {Platform.OS === "web" ? (
          <iframe
            key={key}
            src={simulatorUrl}
            style={{ width: "100%", height: "100%", border: "none", borderRadius: 8 }}
            title="DEMA Simulator"
            onLoad={() => setLoading(false)}
          />
        ) : (
          <WebView
            key={key}
            source={{ uri: simulatorUrl }}
            style={styles.webview}
            javaScriptEnabled={true}
            domStorageEnabled={true}
            startInLoadingState={false}
            onLoadStart={() => setLoading(true)}
            onLoadEnd={() => setLoading(false)}
            scalesPageToFit={true}
            nestedScrollEnabled={true}
            onMessage={(e) => {
              const h = parseInt(e.nativeEvent.data, 10);
              if (!isNaN(h) && h > 240 && h < 12000) setWebHeight(h);
            }}
            injectedJavaScriptBeforeContentLoaded={`
              (function(){
                // Simülatör Tailwind-responsive (sm:640/md:768). device-width vererek app KENDİ
                // mobil layout'unu kullanır — width=1024 zorlaması desktop-layout'u küçültüp bozuyordu.
                var m=document.querySelector('meta[name=viewport]');
                if(!m){m=document.createElement('meta');m.name='viewport';(document.head||document.documentElement).appendChild(m);}
                m.setAttribute('content','width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover');
              })(); true;
            `}
            injectedJavaScript={`
              (function(){
                // Yatay taşmayı (iç içe geçen yazı/kaydırma) kesin engelle.
                var s=document.createElement('style');
                s.innerHTML='html,body,#root{overflow-x:hidden!important;max-width:100vw!important}img,canvas,svg{max-width:100%!important;height:auto}';
                (document.head||document.documentElement).appendChild(s);
                // İçeriğin TAM yüksekliğini RN'e bildir → WebView içeriğe göre büyür, dış
                // ScrollView tüm simülatör sayfasını kaydırır (WebView jesti yutup kilitlemez).
                function postH(){
                  try {
                    var h = Math.max(document.body.scrollHeight||0, document.documentElement.scrollHeight||0, document.body.offsetHeight||0);
                    if (h && window.ReactNativeWebView) window.ReactNativeWebView.postMessage(String(h));
                  } catch(e){}
                }
                window.addEventListener('load', postH);
                window.addEventListener('resize', postH);
                [300,800,1500,3000].forEach(function(t){ setTimeout(postH, t); });
                try { new ResizeObserver(postH).observe(document.body); } catch(e){}
              })(); true;
            `}
            onError={() => setLoading(false)}
          />
        )}
        {loading && (
          <View style={styles.loadingOverlay} pointerEvents="none">
            <ActivityIndicator size="large" color={colors.primary} />
            <Text style={styles.loadingText}>Simülatör yükleniyor…</Text>
            <Text style={styles.loadingHint}>İlk açılış birkaç saniye sürebilir</Text>
          </View>
        )}
      </View>
    </View>
  );
}


const styles = StyleSheet.create({
  container: {
    gap: spacing.lg,
    width: "100%",
    maxWidth: rs(1100),
    alignSelf: "center",
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
    backgroundColor: colors.bgAlt,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: 8,
    overflow: "hidden",
  },
  webview: {
    flex: 1,
    backgroundColor: "transparent",
  },
  loadingOverlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.bgAlt,
    gap: spacing.sm,
  },
  loadingText: {
    color: colors.text,
    fontSize: typography.body,
    fontWeight: "700",
    marginTop: spacing.sm,
  },
  loadingHint: {
    color: colors.textMuted,
    fontSize: rf(12),
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.md,
  },
  refreshBtn: {
    padding: spacing.sm,
    backgroundColor: colors.bgAlt,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  urlText: {
    color: colors.textSubtle,
    fontSize: rf(10),
    fontFamily: "monospace",
    marginTop: spacing.xs,
  },
});
