import { ReactNode } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Activity, BarChart3, Bell, BrainCircuit, Gauge, History, LayoutDashboard, Settings, SlidersHorizontal, Waves, Users, type LucideIcon } from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useResponsive } from "@/hooks/useResponsive";
import { colors, radius, spacing, typography } from "@/theme/tokens";
import { RouteKey } from "@/types/domain";
import { useUserMode } from "@/context/UserModeContext";
import { useLiveData } from "@/context/LiveDataContext";

interface NavItem {
  key: RouteKey;
  label: string;
  icon: LucideIcon;
  expertOnly: boolean;
}

const allNavItems: NavItem[] = [
  { key: "ai", label: "Akıllı Teşhis", icon: BrainCircuit, expertOnly: false },
  { key: "dashboard", label: "Ana Ekran", icon: LayoutDashboard, expertOnly: false },
  { key: "simulator", label: "Simülasyon", icon: Waves, expertOnly: true },
  { key: "control", label: "Kontrol", icon: SlidersHorizontal, expertOnly: true },
  { key: "patients", label: "Hastalar", icon: Users, expertOnly: true },
  { key: "sensors", label: "Sensörler", icon: Activity, expertOnly: true },
  { key: "history", label: "Geçmiş", icon: History, expertOnly: true },
  { key: "kpi", label: "Raporlar", icon: BarChart3, expertOnly: true },
  { key: "settings", label: "Ayarlar", icon: Settings, expertOnly: false }
];

interface AppShellProps {
  activeRoute: RouteKey;
  title: string;
  subtitle: string;
  onRouteChange: (route: RouteKey) => void;
  children: ReactNode;
}

export function AppShell({ activeRoute, title, subtitle, onRouteChange, children }: AppShellProps) {
  const responsive = useResponsive();
  const insets = useSafeAreaInsets();
  const { isExpert } = useUserMode();
  const { unreadCount, wsConnected } = useLiveData();
  const desktop = responsive.isDesktop || responsive.isTablet;

  const navItems = allNavItems.filter(item => !item.expertOnly || isExpert);

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      {desktop ? (
        <View style={styles.sidebar}>
          <View style={styles.brand}>
            <Gauge color={colors.primary} size={24} />
            <View>
              <Text style={styles.brandTitle}>PEMF Vet</Text>
              <Text style={styles.brandSub}>Responsive Console</Text>
            </View>
          </View>
          <View style={styles.navList}>
            {navItems.map((item) => (
              <NavButton
                key={item.key}
                item={item}
                active={activeRoute === item.key}
                compact={false}
                onPress={() => onRouteChange(item.key)}
              />
            ))}
          </View>
        </View>
      ) : null}

      <View style={styles.main}>
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <Text style={styles.title}>{title}</Text>
            <Text style={styles.subtitle}>{subtitle}</Text>
          </View>
          <View style={styles.headerRight}>
            <View style={[styles.wsIndicator, !wsConnected && styles.wsIndicatorOff]} />
            {unreadCount > 0 && (
              <View style={styles.notifBadgeWrap}>
                <Bell size={16} color={colors.textMuted} />
                <View style={styles.notifBadge}>
                  <Text style={styles.notifBadgeText}>{unreadCount > 99 ? "99+" : unreadCount}</Text>
                </View>
              </View>
            )}
          </View>
        </View>

        <ScrollView contentContainerStyle={[styles.content, !desktop && { paddingBottom: 92 + insets.bottom }]}>
          {children}
        </ScrollView>
      </View>

      {!desktop ? (
        <View style={[styles.bottomNav, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
          {navItems.slice(0, 5).map((item) => (
            <NavButton
              key={item.key}
              item={item}
              active={activeRoute === item.key}
              compact
              onPress={() => onRouteChange(item.key)}
            />
          ))}
        </View>
      ) : null}
    </View>
  );
}

function NavButton({ item, active, compact, onPress }: { item: NavItem; active: boolean; compact: boolean; onPress: () => void }) {
  const Icon = item.icon;
  return (
    <Pressable
      accessibilityLabel={item.label}
      accessibilityRole="button"
      onPress={onPress}
      style={[compact ? styles.bottomItem : styles.navItem, active && styles.navItemActive]}
    >
      <Icon size={18} color={active ? colors.text : colors.textMuted} />
      <Text style={[compact ? styles.bottomLabel : styles.navLabel, active && styles.navLabelActive]} numberOfLines={1}>
        {item.label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: {
    backgroundColor: colors.bg,
    flex: 1,
    flexDirection: "row"
  },
  sidebar: {
    backgroundColor: colors.bgAlt,
    borderRightColor: colors.border,
    borderRightWidth: 1,
    gap: spacing.xl,
    padding: spacing.xl,
    width: 248
  },
  brand: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.md
  },
  brandTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "800"
  },
  brandSub: {
    color: colors.textMuted,
    fontSize: typography.small
  },
  navList: {
    gap: spacing.sm
  },
  navItem: {
    alignItems: "center",
    borderRadius: radius.md,
    flexDirection: "row",
    gap: spacing.md,
    minHeight: 44,
    paddingHorizontal: spacing.md
  },
  navItemActive: {
    backgroundColor: colors.primarySoft
  },
  navLabel: {
    color: colors.textMuted,
    fontSize: typography.body,
    fontWeight: "700"
  },
  navLabelActive: {
    color: colors.text
  },
  main: {
    flex: 1
  },
  header: {
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.lg,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  headerLeft: { flex: 1 },
  headerRight: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  wsIndicator: {
    width: 10, height: 10, borderRadius: 5,
    backgroundColor: "#22c55e",
    shadowColor: "#22c55e", shadowOpacity: 0.8, shadowRadius: 4,
  },
  wsIndicatorOff: { backgroundColor: "#f59e0b", shadowColor: "#f59e0b" },
  notifBadgeWrap: { position: "relative", padding: spacing.xs },
  notifBadge: {
    position: "absolute", top: 0, right: 0,
    backgroundColor: "#ef4444",
    borderRadius: 8, minWidth: 16, height: 16,
    alignItems: "center", justifyContent: "center", paddingHorizontal: 3,
  },
  notifBadgeText: { color: "#fff", fontSize: 9, fontWeight: "800" },
  title: {
    color: colors.text,
    fontSize: typography.title,
    fontWeight: "800"
  },
  subtitle: {
    color: colors.textMuted,
    fontSize: typography.body,
    marginTop: spacing.xs
  },
  content: {
    gap: spacing.lg,
    padding: spacing.xl
  },
  bottomNav: {
    backgroundColor: colors.bgAlt,
    borderTopColor: colors.border,
    borderTopWidth: 1,
    bottom: 0,
    flexDirection: "row",
    left: 0,
    paddingHorizontal: spacing.sm,
    paddingTop: spacing.sm,
    position: "absolute",
    right: 0
  },
  bottomItem: {
    alignItems: "center",
    borderRadius: radius.md,
    flex: 1,
    gap: spacing.xs,
    minHeight: 56,
    justifyContent: "center",
    paddingHorizontal: spacing.xs
  },
  bottomLabel: {
    color: colors.textMuted,
    fontSize: 10,
    fontWeight: "700"
  }
});
