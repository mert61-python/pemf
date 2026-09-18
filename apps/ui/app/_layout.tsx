import { useEffect, useState } from "react";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { Platform, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { ToastProvider } from "@/components/ui/ToastProvider";
import { MobileUpdateGate } from "@/components/domain/MobileUpdateGate";
import { colors } from "@/theme/tokens";
import { useFonts, INTER_FONTS, applyGlobalInter } from "@/theme/fonts";
// NOT (P0 audit 2026-06-28): offlineDb.ts kaldirildi — hasta PII'sini DUZ-METIN Supabase
// 'patients' tablosuna (gate/device_id/RLS yok) push/pull eden olu/paralel yoldu (KVKK ihlali).
// Aktif hasta yolu backend /api/patients (yerel SQLCipher). Burada artik bulut-sync YOK.

// PREMIUM: tüm Text/TextInput'a global Inter (telefonun sistem fontundan bağımsız profesyonel tipografi).
applyGlobalInter();

// NATIVE: Inter, android/app/src/main/assets/fonts'a GÖMÜLÜ → Text asset'ten çözer (runtime useFonts'a
// gerek yok, yükleme-yarışı yok). NOT: RN 0.85 Fabric TextInput native input fontFamily'yi uygulamıyor →
// input alanları sistem fontunda kalır (küçük sınır). WEB: gerçek dosya yok → useFonts @font-face ile yükler.
const isWeb = Platform.OS === "web";

export default function RootLayout() {
  const [fontsLoaded] = useFonts(isWeb ? INTER_FONTS : ({} as any));
  const [fallback, setFallback] = useState(false);
  useEffect(() => {
    if (!isWeb) return;
    const t = setTimeout(() => setFallback(true), 4000);
    return () => clearTimeout(t);
  }, []);
  const ready = !isWeb || fontsLoaded || fallback;
  return (
    <SafeAreaProvider>
      <ToastProvider>
        <StatusBar style="light" />
        {ready ? (
          // AÇILIŞ KAPISI (2026-08-16 sahip isteği): Android'de önce güncelleme kontrolü, SONRA
          // açılış ve kullanım. Kapı `<Stack/>`in ÜSTÜNDE durur → hiçbir rota (login dahil)
          // kontrol bitmeden çizilmez. Web/iOS'ta hiç kapanmaz. Ayrıntı + güvenlik sınırları:
          // MobileUpdateGate başlığı.
          <MobileUpdateGate>
            <Stack screenOptions={{ headerShown: false }} />
          </MobileUpdateGate>
        ) : (
          <View style={{ flex: 1, backgroundColor: colors.bg }} />
        )}
      </ToastProvider>
    </SafeAreaProvider>
  );
}
