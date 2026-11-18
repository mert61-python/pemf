// Author: mertaygn, cglrgrkn
import React, { useEffect, useMemo, useRef, useState } from "react";
import { StyleSheet, View, Platform, Text, TouchableOpacity, useWindowDimensions, ActivityIndicator } from "react-native";
import { WebView } from "react-native-webview";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography, radius, rf, rs, layoutMax } from "@/theme/tokens";
import { serviceConfig } from "@/services/config";
import { dilParametresiEkle } from "@/services/apiClient";
import { RefreshCcw } from "lucide-react-native";
import { useTranslation } from "react-i18next";
import { EFieldBar } from "@/components/domain/EFieldBar";
import { useIkizKoprusu } from "@/hooks/useIkizKoprusu";

export function DemaSimulatorScreen() {
  const { t } = useTranslation();
  const [key, setKey] = useState(0); // WebView'ı yeniden yüklemek için
  // I18N (Y159): simülatör ayrı sayfa — dili başlıkla değil URL'de (`?dil=`) alır; dil değişince çerçeve yeniden yüklenir.
  const { i18n } = useTranslation();
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
  // [S7 adım 11 / ekranB-11] Yükseklik state'e KİLİTLENMİYOR: ilk render'daki pencere
  // yüksekliğine sabitlendiği için PC penceresi küçültülünce/cihaz yan yatınca iframe ekranı
  // aşıyor, alt kontroller kesiliyordu. Ölçüm gelirse (postMessage) o kullanılır, YOKSA pencere
  // yüksekliğinden CANLI türetilir.
  const [olculenH, setOlculenH] = useState<number | null>(null);
  const webHeight = olculenH ?? Math.max(rs(480), Math.round(height * 0.78));
  const setWebHeight = setOlculenH;

  // apiBaseUrl'den base URL'yi çıkar: http://IP:8000/api → http://IP:8000
  const baseUrl = serviceConfig.apiBaseUrl
    .replace(/\/api\/?$/, "")       // /api sonunu kaldır
    .replace(/\/$/, "");            // trailing slash kaldır
  const simulatorUrl = `${baseUrl}/simulator/index.html`;
  // Ekranda yazan adres AYNI kalır (parametresiz); çerçeve dil parametreli adresi yükler.
  const simulatorKaynak = dilParametresiEkle(simulatorUrl);
  const cerceveAnahtari = `${key}:${i18n.language}`;

  // GA (istem 53) A4 — DİJİTAL İKİZ KÖPRÜSÜ (sözleşme v1): yüklenen çerçeveye SALT OKUR `pemf.ikiz.durum` (2 Hz) + ikiz `pemf.ikiz.hazir`
  // deyince `pemf.ikiz.alan`. Çerçeveden YALNIZ `hazir` tanınır — komut yolu YOK. DEMA iletileri yok sayar (hazir demez → alan hesabı başlamaz).
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const webViewRef = useRef<{ postMessage: (m: string) => void } | null>(null);
  const [yuklenen, setYuklenen] = useState<string | null>(null);
  const koken = useMemo(() => {
    try {
      return new URL(simulatorUrl).origin;
    } catch {
      return null;
    }
  }, [simulatorUrl]);
  const gonder = useMemo(() => {
    if (yuklenen !== cerceveAnahtari) return null;
    if (Platform.OS === "web") {
      return (m: string) => {
        const w = iframeRef.current?.contentWindow;
        if (w && koken) w.postMessage(m, koken);
      };
    }
    return (m: string) => webViewRef.current?.postMessage(m);
  }, [yuklenen, cerceveAnahtari, koken]);
  const { gelen } = useIkizKoprusu(gonder);
  useEffect(() => {
    if (Platform.OS !== "web" || typeof window === "undefined" || typeof window.addEventListener !== "function") return undefined;
    const dinle = (e: MessageEvent) => {
      if (!e.source || e.source !== iframeRef.current?.contentWindow || e.origin !== koken) return;
      gelen(e.data);
    };
    window.addEventListener("message", dinle);
    return () => window.removeEventListener("message", dinle);
  }, [gelen, koken]);

  return (
    <View style={styles.container}>
      <Card style={styles.headerCard}>
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.title}>{t("dema.baslik")}</Text>
            {/* D1.91 · A-37 (sahip): simülatör tanıtım/eğitim aracıdır — "canlı izleme" demez. */}
            <Text style={styles.muted}>
              {t("dema.egitimEtiketi")}
            </Text>
          </View>
          <TouchableOpacity style={styles.refreshBtn} onPress={reload} accessibilityRole="button" accessibilityLabel={t("dema.yenidenYukleEtiketi")}>
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
            key={cerceveAnahtari}
            src={simulatorKaynak}
            style={{ width: "100%", height: "100%", border: "none", borderRadius: 8 }}
            title="DEMA Simulator"
            ref={iframeRef}
            onLoad={() => {
              setLoading(false);
              setYuklenen(cerceveAnahtari);
            }}
          />
        ) : (
          <WebView
            key={cerceveAnahtari}
            ref={webViewRef as never}
            source={{ uri: simulatorKaynak }}
            style={styles.webview}
            javaScriptEnabled={true}
            domStorageEnabled={true}
            startInLoadingState={false}
            onLoadStart={() => setLoading(true)}
            onLoadEnd={() => {
              setLoading(false);
              setYuklenen(cerceveAnahtari);
            }}
            scalesPageToFit={true}
            nestedScrollEnabled={true}
            onMessage={(e) => {
              const h = parseInt(e.nativeEvent.data, 10);
              if (!isNaN(h) && h > 240 && h < 12000) setWebHeight(h);
              gelen(e.nativeEvent.data); // GA: yalnız `pemf.ikiz.hazir` tanınır
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
            <Text style={styles.loadingText}>{t("dema.yukleniyor")}</Text>
            <Text style={styles.loadingHint}>{t("dema.ilkAcilis")}</Text>
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
    maxWidth: layoutMax.icerik,
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
