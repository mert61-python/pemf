import React from "react";
import { StyleSheet, Text, View, TouchableOpacity } from "react-native";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography } from "@/theme/tokens";
import { useUserMode } from "@/context/UserModeContext";
import { Heart, Stethoscope } from "lucide-react-native";

export function WelcomeScreen() {
  const { setUserMode } = useUserMode();

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>PEMF Sistemine Hoş Geldiniz</Text>
        <Text style={styles.subtitle}>Lütfen kullanım profilinizi seçin</Text>
      </View>

      <View style={styles.cardsContainer}>
        <TouchableOpacity style={styles.cardWrapper} onPress={() => setUserMode('pet_owner')}>
          <View style={[styles.cardContainer, styles.ownerCard]}>
            <Card style={styles.card}>
              <Heart size={48} color={colors.primary} />
              <Text style={styles.cardTitle}>Evcil Hayvan Sahibi</Text>
              <Text style={styles.cardDesc}>
                Kamerayı kullanarak akıllı teşhis yapın ve tek tuşla güvenli tedavi başlatın. Karmaşık ayarlarla uğraşmayın.
              </Text>
            </Card>
          </View>
        </TouchableOpacity>

        <TouchableOpacity style={styles.cardWrapper} onPress={() => setUserMode('veterinarian')}>
          <View style={[styles.cardContainer, styles.vetCard]}>
            <Card style={styles.card}>
              <Stethoscope size={48} color={colors.warning} />
              <Text style={styles.cardTitle}>Veteriner Hekim</Text>
              <Text style={styles.cardDesc}>
                Manuel frekans kontrolü, sensör takibi, geçmiş tedavi analizleri ve klinik ayarlarına tam erişim sağlayın.
              </Text>
            </Card>
          </View>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  header: {
    alignItems: 'center',
    marginBottom: spacing.xxl,
  },
  title: {
    fontSize: 32,
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
  cardsContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xl,
    justifyContent: 'center',
    maxWidth: 900,
  },
  cardWrapper: {
    flex: 1,
    minWidth: 300,
  },
  cardContainer: {
    flex: 1,
  },
  card: {
    alignItems: 'center',
    padding: spacing.xxl,
    gap: spacing.lg,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  ownerCard: {
    backgroundColor: colors.bgAlt,
  },
  vetCard: {
    backgroundColor: colors.bgAlt,
  },
  cardTitle: {
    fontSize: typography.title,
    fontWeight: '800',
    color: colors.text,
  },
  cardDesc: {
    fontSize: typography.body,
    color: colors.textMuted,
    textAlign: 'center',
    lineHeight: 24,
  }
});
