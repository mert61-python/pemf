// Author: mertaygn, cglrgrkn
import React, { createContext, useContext, useState, ReactNode, useEffect, useRef, useCallback, useMemo } from "react";
import { StyleSheet, Text, View, Animated, AccessibilityInfo } from "react-native";
import { CheckCircle, AlertCircle, Info } from "lucide-react-native";
import { colors, radius, spacing, typography, rs } from "@/theme/tokens";
import { setToastHandler } from "@/services/toastBridge";

type ToastType = "success" | "error" | "info";

interface ToastMessage {
  id: string;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  showToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within ToastProvider");
  return context;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastMessage | null>(null);
  // useRef: Animated.Value'lar her render'da YENİDEN oluşturulmasın (eskiden her render'da
  // new Animated.Value → animasyon stale değerlere bağlanıyor + gereksiz alokasyon).
  const opacity = useRef(new Animated.Value(0)).current;
  const translateY = useRef(new Animated.Value(-20)).current;
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentTypeRef = useRef<ToastType | null>(null);

  // Unmount'ta bekleyen gizleme-zamanlayıcısını temizle (iptal-edilmeyen setTimeout sızıntısı önle).
  useEffect(() => () => { if (hideTimer.current) clearTimeout(hideTimer.current); }, []);

  // YÜKSEK fix: showToast STABİL referans olmalı. Eskiden her render'da yeniden yaratılıyordu → tüm
  // useToast tüketicileri render + [showToast] bağımlılıklı effect'ler yeniden çalışırdı. En tehlikelisi:
  // AiHubScreen otonom AI-Pro tedavi effect'i showToast'ı deps'ten ÇIKARMAK zorunda kalmıştı (yoksa her
  // toast otonom tedaviyi YENİDEN BAŞLATIRDI). useCallback([]) ile artık deps'e güvenle eklenebilir.
  const showToast = useCallback((message: string, type: ToastType = "info") => {
    // DÜŞÜK fix: aktif bir HATA toast'ı görünürken daha düşük öncelikli (info/success) yeni toast onu
    // EZMESİN → kritik medikal uyarı yutulmaz. (Yeni bir HATA her zaman gösterilir + ezer.)
    if (currentTypeRef.current === "error" && type !== "error") return;
    currentTypeRef.current = type;
    const newToast = { id: Math.random().toString(), message, type };
    setToast(newToast);

    // A11y (#66): toast görsel + 3sn'de kaybolur → ekran-okuyucu kullanan operatör HATA/uyarıyı
    // (ör. "durdurulamadı — ACİL DURDUR") kaçırmasın. Hata/uyarıları TalkBack/VoiceOver'a duyur.
    if (type === "error") {
      AccessibilityInfo.announceForAccessibility(message);
    }

    // Önceki gizleme zamanlayıcısını iptal et — art arda toast'larda erken kapanma/yığılma önle.
    if (hideTimer.current) clearTimeout(hideTimer.current);

    opacity.setValue(0);
    translateY.setValue(-20);
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 300, useNativeDriver: true }),
      Animated.spring(translateY, { toValue: 20, useNativeDriver: true })
    ]).start();

    hideTimer.current = setTimeout(() => {
      Animated.parallel([
        Animated.timing(opacity, { toValue: 0, duration: 300, useNativeDriver: true }),
        Animated.timing(translateY, { toValue: -20, duration: 300, useNativeDriver: true })
      // #91: fade-out KESİLİRSE (fade sırasında yeni toast gelip animasyonu keserse) finished=false →
      // yeni toast'ı ANINDA yok etme; yalnız animasyon TAMAMLANDIYSA temizle.
      ]).start(({ finished }) => { if (finished) { setToast(null); currentTypeRef.current = null; } });
    }, 3000);
  }, []); // yalnız stable ref'lere (opacity/translateY/hideTimer) + setToast'a kapanır → bağımlılık yok

  // F-6: service katmanı (apiClient) toast gönderebilsin diye handler'ı kaydet.
  useEffect(() => {
    setToastHandler(showToast);
    return () => setToastHandler(null);
  }, [showToast]);

  const contextValue = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
      {toast && (
        // pointerEvents="box-none": konteyner tam genişlikte ve absolute konumlu; ayarlanmadığında
        // 3+ saniye boyunca altındaki AppShell başlık kontrollerini (profil çipi, bildirimler,
        // yeniden bağlan) dokunulmaz yapıyordu. Artık dokunuşlar konteynerin BOŞ alanından geçer.
        <Animated.View pointerEvents="box-none" style={[styles.toastContainer, { opacity, transform: [{ translateY }] }]}>
          <View
            style={[styles.toast, styles[toast.type]]}
            accessibilityRole="alert"
            accessibilityLiveRegion={toast.type === "error" ? "assertive" : "polite"}
          >
            {toast.type === "success" && <CheckCircle color={colors.white} size={20} />}
            {toast.type === "error" && <AlertCircle color={colors.white} size={20} />}
            {toast.type === "info" && <Info color={colors.white} size={20} />}
            <Text style={styles.message} numberOfLines={4}>{toast.message}</Text>
          </View>
        </Animated.View>
      )}
    </ToastContext.Provider>
  );
}

const styles = StyleSheet.create({
  toastContainer: {
    position: "absolute",
    top: rs(40),
    left: spacing.md,
    right: spacing.md,
    alignItems: "center",
    zIndex: 9999
  },
  toast: {
    flexDirection: "row",
    alignItems: "center",
    maxWidth: rs(480),
    alignSelf: "center",
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    gap: spacing.md,
    shadowColor: "#000",
    shadowOpacity: 0.3,
    shadowRadius: 10,
    shadowOffset: { width: rs(0), height: rs(4) },
    elevation: 5
  },
  success: { backgroundColor: colors.success },
  error: { backgroundColor: colors.danger },
  info: { backgroundColor: colors.primary },
  message: {
    flexShrink: 1,
    color: colors.white,
    fontSize: typography.body,
    fontWeight: "700"
  }
});
