import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { ToastProvider } from "@/components/ui/ToastProvider";
// NOT (P0 audit 2026-06-28): offlineDb.ts kaldirildi — hasta PII'sini DUZ-METIN Supabase
// 'patients' tablosuna (gate/device_id/RLS yok) push/pull eden olu/paralel yoldu (KVKK ihlali).
// Aktif hasta yolu backend /api/patients (yerel SQLCipher). Burada artik bulut-sync YOK.

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <ToastProvider>
        <StatusBar style="light" />
        <Stack screenOptions={{ headerShown: false }} />
      </ToastProvider>
    </SafeAreaProvider>
  );
}
