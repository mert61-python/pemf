// Author: mertaygn, cglrgrkn
/**
 * ScrollableModalCard — kısa ekranda KAYDIRILABİLİR, eylem satırı SABİT modal kartı.
 * [S5, 2026-09-04 responsive denetimi]
 * ====================================================================================
 * ÖLÇÜLEN DURUM: ortalanmış modallar (plan yükseltme, AI seans önerisi onayı, yedek parolası)
 * ScrollView'sız düz View'dı ve yüzde tabanlı `maxHeight` kullanıyordu. Yatay telefonda
 * (360-430 px yükseklik) ve klavye açıkken kartın ALTI (Onayla / Anladım / Kaydet düğmeleri)
 * ekran dışında kalıyor ve KAYDIRILAMIYORDU → hekim onay veremiyordu.
 *
 * TASARIM:
 *  · maxHeight YÜZDE DEĞİL mutlak: pencere − güvenli alanlar − kenar boşluğu (çentikli/yatay
 *    cihazda yüzde hesabı yanıltıyordu).
 *  · Gövde `ScrollView` (flexShrink:1) — Yoga'da çocuklar varsayılan `flexShrink:0` olduğu için
 *    maxHeight aşılınca taşıyorlardı; ekranB-10'un kök nedeni buydu.
 *  · `footer` ScrollView'in DIŞINDA → eylem satırı HER ZAMAN görünür (onay/iptal kaybolmaz).
 *  · iOS'ta KeyboardAvoidingView (Android'de RN Modal kendi penceresini adjustResize ile daraltır).
 *
 * ⚠️ Perde ve kart `Pressable`'dır ama DOKUNMA HEDEFİ DEĞİLDİR (dokunuş yutucu) —
 * dokunma-hedefi kapısı için muaf yorumları aşağıdadır.
 */
import { ReactNode } from "react";
import { KeyboardAvoidingView, Modal, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, radius, rs, spacing } from "@/theme/tokens";
import { KAV_BEHAVIOR_MODAL } from "@/hooks/useKeyboard";
import { useResponsive } from "@/hooks/useResponsive";

export interface ScrollableModalCardProps {
  visible: boolean;
  /** Android geri tuşu / Escape. */
  onRequestClose: () => void;
  /** Perdeye dokununca (verilmezse perde dokunuşu yutulur, kapatmaz). */
  onBackdropPress?: () => void;
  /** Kaydırma alanının ÜSTÜNDE sabit kalan başlık (başlık + kapat düğmesi). */
  header?: ReactNode;
  /** Kaydırma alanının ALTINDA sabit kalan eylem satırı (Onayla / Vazgeç). */
  footer?: ReactNode;
  children: ReactNode;
  maxWidth?: number;
  /** "center" (varsayılan) ya da "bottom" (alt-sayfa). */
  align?: "center" | "bottom";
  cardStyle?: object;
  contentStyle?: object;
  testID?: string;
  accessibilityLabel?: string;
}

export function ScrollableModalCard({
  visible,
  onRequestClose,
  onBackdropPress,
  header,
  footer,
  children,
  maxWidth = rs(520),
  align = "center",
  cardStyle,
  contentStyle,
  testID,
  accessibilityLabel,
}: ScrollableModalCardProps) {
  const insets = useSafeAreaInsets();
  const { height } = useResponsive();

  // Mutlak tavan: pencere − güvenli alanlar − kenar boşluğu. Yüzde hesabı çentikli/yatay
  // cihazlarda kartı ekran dışına taşırıyordu.
  const maxHeight = Math.max(rs(220), height - insets.top - insets.bottom - 2 * spacing.md);

  return (
    <Modal visible={visible} transparent animationType={align === "bottom" ? "slide" : "fade"} onRequestClose={onRequestClose}>
      <KeyboardAvoidingView style={styles.kav} behavior={KAV_BEHAVIOR_MODAL}>
        {/* dokunma-hedefi: muaf (perde — hedef değil, dokunuş yutucu) */}
        <Pressable
          style={[styles.backdrop, align === "bottom" ? styles.backdropBottom : styles.backdropCenter]}
          onPress={onBackdropPress}
        >
          {/* dokunma-hedefi: muaf (kart — hedef değil, perde dokunuşunu yutar) */}
          <Pressable
            onPress={() => {}}
            style={[
              styles.card,
              align === "bottom" ? styles.cardBottom : null,
              { maxWidth, maxHeight, paddingBottom: align === "bottom" ? insets.bottom + spacing.md : spacing.md },
              cardStyle,
            ]}
            testID={testID}
            accessibilityLabel={accessibilityLabel}
          >
            {header ? <View style={styles.header}>{header}</View> : null}
            <ScrollView
              style={styles.body}
              contentContainerStyle={[styles.bodyContent, contentStyle]}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              {children}
            </ScrollView>
            {footer ? <View style={styles.footer}>{footer}</View> : null}
          </Pressable>
        </Pressable>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  kav: { flex: 1 },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", paddingHorizontal: spacing.md },
  backdropCenter: { alignItems: "center", justifyContent: "center" },
  backdropBottom: { justifyContent: "flex-end" },
  card: {
    width: "100%",
    alignSelf: "center",
    backgroundColor: colors.panel,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    overflow: "hidden",
  },
  cardBottom: { borderBottomLeftRadius: 0, borderBottomRightRadius: 0 },
  header: { paddingBottom: spacing.sm },
  // ⚠️ flexShrink:1 ŞART — Yoga'da çocuk varsayılanı 0'dır ve kart maxHeight'ı aşılınca gövde
  //    taşıp eylem satırını ekran dışına itiyordu (ekranB-10).
  body: { flexShrink: 1, flexGrow: 0 },
  bodyContent: { gap: spacing.sm, paddingBottom: spacing.sm },
  footer: { paddingTop: spacing.sm },
});
