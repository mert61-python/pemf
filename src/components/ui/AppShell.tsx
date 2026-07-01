import { ReactNode, useEffect, useRef, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View, PanResponder } from "react-native";
import { Activity, BarChart3, Bell, BrainCircuit, Gauge, History, LayoutDashboard, MoreHorizontal, Settings, SlidersHorizontal, Waves, Users, type LucideIcon } from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useResponsive } from "@/hooks/useResponsive";
import { colors, radius, spacing, typography } from "@/theme/tokens";
import { RouteKey } from "@/types/domain";
import { useUserMode } from "@/context/UserModeContext";
import { useLiveData } from "@/context/LiveDataContext";
import { NotificationCenter } from "@/components/ui/NotificationCenter";
import { useToast } from "@/components/ui/ToastProvider";
import { UpdateBanner } from "@/components/ui/UpdateBanner";

interface NavItem {
  key: RouteKey;
  label: string;
  icon: LucideIcon;
  expertOnly: boolean;
}

// İlk 4 (uzman) bottom-nav'da; gerisi "Daha Fazla" menüsünde (keşfedilebilirlik fix).
const allNavItems: NavItem[] = [
  { key: "ai", label: "Akıllı Teşhis", icon: BrainCircuit, expertOnly: false },
  { key: "dashboard", label: "Ana Ekran", icon: LayoutDashboard, expertOnly: false },
  { key: "control", label: "Kontrol", icon: SlidersHorizontal, expertOnly: true },
  { key: "patients", label: "Hastalar", icon: Users, expertOnly: true },
  { key: "sensors", label: "Sensörler", icon: Activity, expertOnly: true },
  { key: "history", label: "Geçmiş", icon: History, expertOnly: true },
  { key: "kpi", label: "Raporlar", icon: BarChart3, expertOnly: true },
  { key: "simulator", label: "Simülasyon", icon: Waves, expertOnly: true },
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
  const { unreadCount, connectionQuality, reconnect } = useLiveData();
  const { showToast } = useToast();
  const desktop = responsive.isDesktop || responsive.isTablet;

  // Oto-eşleştirme görünür onayı (#11): config.setStoredDeviceId yeni/değişen cihaz
  // id'sinde "@pemf_just_paired" yazar. Mount'ta okuyup toast göster + bayrağı sil.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const paired = await AsyncStorage.getItem("@pemf_just_paired");
        if (!cancelled && paired) {
          showToast("Cihaz otomatik eşleştirildi ✓", "success");
          await AsyncStorage.removeItem("@pemf_just_paired");
        }
      } catch {
        /* ignore */
      }
    })();
    return () => { cancelled = true; };
  }, [showToast]);

  const navItems = allNavItems.filter(item => !item.expertOnly || isExpert);
  const [showMore, setShowMore] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const showMoreBtn = navItems.length > 5;
  const primaryItems = showMoreBtn ? navItems.slice(0, 4) : navItems;
  const moreItems = showMoreBtn ? navItems.slice(4) : [];
  const moreActive = moreItems.some((i) => i.key === activeRoute);

  // KÖK NEDEN FIX: panResponder useRef ile BİR KEZ oluşur → closure ilk render'ın activeRoute'unu
  // (dashboard) yakalardı (stale) → her swipe dashboard'dan hesaplanıp YANLIŞ taba gidiyordu.
  // Güncel değerleri ref'lerden okuyoruz + tek-swipe-tek-geçiş debounce.
  const desktopRef = useRef(desktop); desktopRef.current = desktop;
  const activeRouteRef = useRef(activeRoute); activeRouteRef.current = activeRoute;
  const navItemsRef = useRef(navItems); navItemsRef.current = navItems;
  const onRouteChangeRef = useRef(onRouteChange); onRouteChangeRef.current = onRouteChange;
  const lastNavRef = useRef(0);

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponder: (_evt, g) => {
        if (desktopRef.current) return false;
        return Math.abs(g.dx) > Math.abs(g.dy) && Math.abs(g.dx) > 24;
      },
      onPanResponderRelease: (_evt, g) => {
        if (desktopRef.current) return;
        if (Math.abs(g.dx) < 60) return;
        const now = Date.now();
        if (now - lastNavRef.current < 600) return; // tek swipe = tek geçiş (çift-atlama önle)
        const items = navItemsRef.current;
        const idx = items.findIndex((i) => i.key === activeRouteRef.current);
        if (idx === -1) return;
        const dir = g.dx < 0 ? 1 : -1; // sola çek → sonraki tab, sağa çek → önceki tab
        const next = idx + dir;
        if (next >= 0 && next < items.length) {
          lastNavRef.current = now;
          onRouteChangeRef.current(items[next].key);
        }
      },
    })
  ).current;

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
          <ScrollView style={styles.navScroll} contentContainerStyle={styles.navList} showsVerticalScrollIndicator={false}>
            {navItems.map((item) => (
              <NavButton
                key={item.key}
                item={item}
                active={activeRoute === item.key}
                compact={false}
                onPress={() => onRouteChange(item.key)}
              />
            ))}
          </ScrollView>
        </View>
      ) : null}

      <View style={styles.main} {...(!desktop ? panResponder.panHandlers : {})}>
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <Text style={styles.title}>{title}</Text>
            <Text style={styles.subtitle}>{subtitle}</Text>
          </View>
          <View style={styles.headerRight}>
            {!desktop && (
              <Pressable onPress={() => onRouteChange("settings")} style={{ padding: spacing.xs }}>
                <Settings size={22} color={colors.textMuted} />
              </Pressable>
            )}
            <Pressable onPress={reconnect} style={styles.wsContainer} accessibilityRole="button" accessibilityLabel="Bağlantıyı yenile">
              {connectionQuality !== "live" && (
                <Text style={[styles.wsTextOff, connectionQuality === "offline" && styles.wsTextOffline]}>
                  {connectionQuality === "stale" ? "Veri gecikmeli" : "Çevrimdışı"}
                </Text>
              )}
              <View style={[
                styles.wsIndicator,
                connectionQuality === "stale" && styles.wsIndicatorStale,
                connectionQuality === "offline" && styles.wsIndicatorOff,
              ]} />
            </Pressable>
            <Pressable
              accessibilityLabel="Bildirimler"
              accessibilityRole="button"
              onPress={() => setShowNotifications(true)}
              style={styles.notifBadgeWrap}
            >
              <Bell size={16} color={colors.textMuted} />
              {unreadCount > 0 && (
                <View style={styles.notifBadge}>
                  <Text style={styles.notifBadgeText}>{unreadCount > 99 ? "99+" : unreadCount}</Text>
                </View>
              )}
            </Pressable>
          </View>
        </View>

        {connectionQuality !== "live" && (
          <Pressable onPress={reconnect} style={[styles.connBanner, connectionQuality === "offline" && styles.connBannerOffline]}>
            <Text style={styles.connBannerText}>
              {connectionQuality === "offline"
                ? "⚠ Cihaza bağlanılamıyor — gösterilen değerler GERÇEK DEĞİL. Dokunup yeniden bağlan."
                : "⚠ Bağlantı gecikmeli — değerler canlı olmayabilir. Dokunup yenile."}
            </Text>
          </Pressable>
        )}

        <UpdateBanner />

        <ScrollView contentContainerStyle={[styles.content, !desktop && { paddingBottom: 92 + insets.bottom }]} keyboardShouldPersistTaps="handled">
          {children}
        </ScrollView>
      </View>

      {!desktop ? (
        <View style={[styles.bottomNav, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
          {primaryItems.map((item) => (
            <NavButton
              key={item.key}
              item={item}
              active={activeRoute === item.key}
              compact
              onPress={() => onRouteChange(item.key)}
            />
          ))}
          {showMoreBtn ? (
            <Pressable
              accessibilityLabel="Daha Fazla"
              accessibilityRole="button"
              onPress={() => setShowMore(true)}
              style={[styles.bottomItem, moreActive && styles.navItemActive]}
            >
              <MoreHorizontal size={18} color={moreActive ? colors.text : colors.textMuted} />
              <Text style={[styles.bottomLabel, moreActive && styles.navLabelActive]} numberOfLines={1}>Daha Fazla</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}

      {!desktop && showMoreBtn ? (
        <Modal visible={showMore} transparent animationType="fade" onRequestClose={() => setShowMore(false)}>
          <Pressable style={styles.moreBackdrop} onPress={() => setShowMore(false)}>
            <View style={[styles.moreSheet, { paddingBottom: insets.bottom + spacing.lg }]}>
              <Text style={styles.moreTitle}>Diğer Ekranlar</Text>
              {moreItems.map((item) => {
                const Icon = item.icon;
                const active = activeRoute === item.key;
                return (
                  <Pressable
                    key={item.key}
                    onPress={() => { onRouteChange(item.key); setShowMore(false); }}
                    style={[styles.moreRow, active && styles.navItemActive]}
                  >
                    <Icon size={20} color={active ? colors.text : colors.textMuted} />
                    <Text style={[styles.moreRowLabel, active && styles.navLabelActive]}>{item.label}</Text>
                  </Pressable>
                );
              })}
            </View>
          </Pressable>
        </Modal>
      ) : null}

      <Modal visible={showNotifications} transparent animationType="fade" onRequestClose={() => setShowNotifications(false)}>
        <Pressable style={styles.notifBackdrop} onPress={() => setShowNotifications(false)}>
          <Pressable style={[styles.notifSheet, { marginTop: insets.top + spacing.xl }]} onPress={() => {}}>
            <NotificationCenter maxVisible={20} />
          </Pressable>
        </Pressable>
      </Modal>
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
  navScroll: { flex: 1 },
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
  wsContainer: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  wsTextOff: { color: "#f59e0b", fontSize: 10, fontWeight: "700" },
  wsIndicator: {
    width: 10, height: 10, borderRadius: 5,
    backgroundColor: "#22c55e",
    shadowColor: "#22c55e", shadowOpacity: 0.8, shadowRadius: 4,
  },
  wsIndicatorOff: { backgroundColor: "#ef4444", shadowColor: "#ef4444" },
  wsIndicatorStale: { backgroundColor: "#f59e0b", shadowColor: "#f59e0b" },
  wsTextOffline: { color: "#ef4444" },
  connBanner: {
    backgroundColor: "#3a2e0a",
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  connBannerOffline: { backgroundColor: "#3a1a1a" },
  connBannerText: { color: "#fcd34d", fontSize: 12, fontWeight: "700", textAlign: "center" },
  notifBadgeWrap: { position: "relative", padding: spacing.xs },
  notifBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", alignItems: "flex-end", paddingHorizontal: spacing.lg },
  notifSheet: { width: "100%", maxWidth: 420 },
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
  },
  moreBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  moreSheet: {
    backgroundColor: colors.bgAlt,
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    padding: spacing.lg,
    gap: spacing.xs,
    borderTopWidth: 1,
    borderColor: colors.border
  },
  moreTitle: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800", marginBottom: spacing.sm },
  moreRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    minHeight: 48
  },
  moreRowLabel: { color: colors.textMuted, fontSize: typography.body, fontWeight: "700" }
});
