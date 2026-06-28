import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { ToastProvider } from "@/components/ui/ToastProvider";
import { useEffect } from "react";
import { initOfflineDb, syncWithCloud } from "@/database/offlineDb";

export default function RootLayout() {
  useEffect(() => {
    // 1. Initialize local SQLite
    initOfflineDb();
    
    // 2. Start Cloud Sync if connected
    syncWithCloud();
    
    // 3. Optional: setup a background interval
    const interval = setInterval(() => {
      syncWithCloud();
    }, 60000); // every minute
    
    return () => clearInterval(interval);
  }, []);

  return (
    <SafeAreaProvider>
      <ToastProvider>
        <StatusBar style="light" />
        <Stack screenOptions={{ headerShown: false }} />
      </ToastProvider>
    </SafeAreaProvider>
  );
}
