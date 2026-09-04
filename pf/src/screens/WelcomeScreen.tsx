// Author: mertaygn, cglrgrkn
import React from "react";
import { StyleSheet, Text, View, TouchableOpacity, ScrollView, useWindowDimensions } from "react-native";
import { Card } from "@/components/ui/Card";
import { AuroraBackground } from "@/components/ui/AuroraBackground";
import { FadeInView } from "@/components/ui/FadeInView";
import { colors, spacing, typography, rf, rs, layoutMax } from "@/theme/tokens";
import { useUserMode } from "@/context/UserModeContext";
import { useAuth } from "@/context/AuthContext";
import { Heart, Stethoscope, FlaskConical, LogOut, Sparkles, Zap } from "lucide-react-native";
import { useEntitlement } from "@/context/EntitlementContext";
import { TIER_LABEL } from "@/config/entitlement";
import { installedModes } from "@/services/installedProfiles";
import { useTeardownGuard } from "@/hooks/useTeardownGuard";

export function WelcomeScreen() {
  const { setUserMode } = useUserMode();
  // `.edu` gate KALDIRILDI — araştırma modu tüm hesaplarda görünür. (Erişim, client-kurulumu +
  // aboneliğe göre belirlenecek; app tarafında e-posta şartı yok.)
  const { session, logout } = useAuth();
  const { tier, trialing, trialDaysLeft, realtime, research } = useEntitlement();
  const { width } = useWindowDimensions();
  const guardTeardown = useTeardownGuard();
  const isMobile = width < 768;
  // Masaüstü client'ın kurduğu profiller (?profiles). null → tüm modlar (mobil / bilgi yok).
  const installed = installedModes();
  const showMode = (m: "pet_owner" | "veterinarian" | "researcher") => !installed || installed.has(m);

  return (
    <View style={styles.root}>
      <AuroraBackground intensity={0.75} />
      <ScrollView contentContainerStyle={styles.container} bounces={false}>
        <View style={styles.topBar}>
          <Text style={styles.topEmail} numberOfLines={1}>{session?.email ?? ""}</Text>
          {/* HASTA GÜVENLİĞİ: bu ekrana seans sürerken de gelinebilir (Ayarlar → "Farklı Bir
              Profile Geçiş Yap"). Çıkış, geriye kalan tek yolu (yeniden profil seçip Kontrol'e
              dönmek) da kapatır → önce onay + durdurma. */}
          <TouchableOpacity
            style={styles.logoutBtn}
            onPress={async () => { if (await guardTeardown("Çıkış yapmak")) logout(); }}
            accessibilityRole="button"
            accessibilityLabel="Çıkış yap"
          >
            <LogOut size={16} color={colors.textMuted} />
            <Text style={styles.logoutText}>Çıkış</Text>
          </TouchableOpacity>
        </View>
        <FadeInView style={styles.header}>
          <Text style={styles.title}>PEMF Sistemine Hoş Geldiniz</Text>
          <Text style={styles.subtitle}>Lütfen kullanım profilinizi seçin</Text>
          <View style={styles.planRow}>
            <View style={styles.planPill}>
              <Sparkles size={13} color={colors.primary} />
              <Text style={styles.planPillText}>
                {trialing ? `Deneme · ${trialDaysLeft} gün kaldı` : TIER_LABEL[tier]}
              </Text>
            </View>
            {realtime && (
              <View style={styles.rtPill}>
                <Zap size={12} color={colors.primary} />
                <Text style={styles.rtPillText}>Gerçek-zamanlı</Text>
              </View>
            )}
          </View>
        </FadeInView>

        <View style={[styles.cardsContainer, { flexDirection: isMobile ? 'column' : 'row' }]}>
          {showMode("pet_owner") && (
          <FadeInView delay={90} style={styles.cardWrapper}>
            <TouchableOpacity
              onPress={() => setUserMode('pet_owner')}
              accessibilityRole="button"
              accessibilityLabel="Evcil Hayvan Sahibi profili"
              accessibilityHint="Kamerayla akıllı teşhis ve tek-tuş güvenli seans modu"
            >
              <Card variant="glass" style={styles.card}>
                <View style={[styles.iconRing, styles.ownerRing]}><Heart size={40} color={colors.primary} /></View>
                <Text style={styles.cardTitle}>Evcil Hayvan Sahibi</Text>
                <Text style={styles.cardDesc}>
                  Kamerayı kullanarak akıllı teşhis yapın ve tek tuşla güvenli seans başlatın. Karmaşık ayarlarla uğraşmayın.
                </Text>
              </Card>
            </TouchableOpacity>
          </FadeInView>
          )}

          {showMode("veterinarian") && (
          <FadeInView delay={170} style={styles.cardWrapper}>
            <TouchableOpacity
              onPress={() => setUserMode('veterinarian')}
              accessibilityRole="button"
              accessibilityLabel="Veteriner Hekim profili"
              accessibilityHint="Manuel frekans kontrolü, sensör takibi ve klinik ayarlarına tam erişim"
            >
              <Card variant="glass" style={styles.card}>
                <View style={[styles.iconRing, styles.vetRing]}><Stethoscope size={40} color={colors.warning} /></View>
                <Text style={styles.cardTitle}>Veteriner Hekim</Text>
                <Text style={styles.cardDesc}>
                  Manuel frekans kontrolü, sensör takibi, geçmiş seans analizleri ve klinik ayarlarına tam erişim sağlayın.
                </Text>
              </Card>
            </TouchableOpacity>
          </FadeInView>
          )}

          {showMode("researcher") && (
            <FadeInView delay={250} style={styles.cardWrapper}>
              <TouchableOpacity
                onPress={() => setUserMode('researcher')}
                accessibilityRole="button"
                accessibilityLabel="Araştırma Modu profili"
                accessibilityHint="Kamera destekli klinik kanser araştırma analizleri: fantom tümör, petri kuyu ve böbrek modelleri"
              >
                <Card variant="glass" style={styles.card}>
                  <View style={[styles.iconRing, styles.researchRing]}><FlaskConical size={40} color={colors.violet} /></View>
                  <Text style={styles.cardTitle}>Araştırma Modu</Text>
                  <Text style={styles.cardDesc}>
                    Kamera destekli klinik kanser araştırma analizleri: fantom tümör, petri kuyu ve böbrek (RNA · CT · patoloji · hastalık) modelleriyle detaylı sonuç kaydı.
                  </Text>
                  {!research && (
                    <View style={styles.addonNote}>
                      <Text style={styles.addonNoteText}>Araştırma eklentisi gerektirir</Text>
                    </View>
                  )}
                </Card>
              </TouchableOpacity>
            </FadeInView>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  container: {
    flexGrow: 1,
    backgroundColor: 'transparent',
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    paddingVertical: spacing.xxl,
  },
  header: {
    alignItems: 'center',
    marginBottom: spacing.xxl,
  },
  title: {
    fontSize: rf(32),
    color: colors.text,
    fontWeight: '900',
    textAlign: 'center',
    marginBottom: spacing.sm,
  },
  subtitle: {
    fontSize: typography.title,
    color: colors.textMuted,
    textAlign: 'center',
  },
  planRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.md,
    alignItems: 'center',
    flexWrap: 'wrap',
    justifyContent: 'center',
  },
  planPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: rs(6),
    paddingVertical: rs(5),
    paddingHorizontal: spacing.md,
    borderRadius: 999,
    backgroundColor: 'rgba(79,140,255,0.12)',
    borderWidth: 1,
    borderColor: 'rgba(79,140,255,0.35)',
  },
  planPillText: { color: colors.primary, fontWeight: '700', fontSize: typography.small },
  rtPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: rs(5),
    paddingVertical: rs(5),
    paddingHorizontal: spacing.sm,
    borderRadius: 999,
    backgroundColor: 'rgba(79,140,255,0.10)',
    borderWidth: 1,
    borderColor: 'rgba(79,140,255,0.30)',
  },
  rtPillText: { color: colors.primary, fontWeight: '700', fontSize: typography.small },
  addonNote: {
    paddingVertical: rs(4),
    paddingHorizontal: spacing.sm,
    borderRadius: 8,
    backgroundColor: 'rgba(139,92,246,0.12)',
    borderWidth: 1,
    borderColor: 'rgba(139,92,246,0.35)',
  },
  addonNoteText: { color: colors.violet, fontWeight: '700', fontSize: typography.small },
  cardsContainer: {
    gap: spacing.xl,
    justifyContent: 'center',
    flexWrap: 'wrap',
    maxWidth: layoutMax.genis,
    width: '100%',
  },
  cardWrapper: {
    flex: 1,
    minWidth: rs(280),
  },
  card: {
    alignItems: 'center',
    padding: spacing.xxl,
    gap: spacing.lg,
  },
  iconRing: {
    width: rs(84),
    height: rs(84),
    borderRadius: rs(24),
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
  },
  ownerRing: { backgroundColor: 'rgba(79,140,255,0.12)', borderColor: 'rgba(79,140,255,0.40)' },
  vetRing: { backgroundColor: 'rgba(245,158,11,0.12)', borderColor: 'rgba(245,158,11,0.40)' },
  researchRing: { backgroundColor: 'rgba(139,92,246,0.12)', borderColor: 'rgba(139,92,246,0.40)' },
  cardTitle: {
    fontSize: typography.title,
    fontWeight: '800',
    color: colors.text,
    textAlign: 'center',
  },
  cardDesc: {
    fontSize: typography.body,
    color: colors.textMuted,
    textAlign: 'center',
    lineHeight: rf(24),
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    alignSelf: 'stretch',
    maxWidth: layoutMax.genis,
    width: '100%',
    marginBottom: spacing.lg,
    gap: spacing.md,
  },
  topEmail: { color: colors.textMuted, fontSize: typography.small, flex: 1 },
  logoutBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: rs(6),
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.bgAlt,
  },
  logoutText: { color: colors.textMuted, fontWeight: '700', fontSize: typography.small },
});
