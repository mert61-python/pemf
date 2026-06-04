/**
 * NotificationCenter — Python notification_panel.py'nin React karşılığı.
 * WebSocket üzerinden gelen bildirimleri listeler.
 */
import { StyleSheet, Text, View, TouchableOpacity, ScrollView, Animated } from "react-native";
import { useRef, useEffect } from "react";
import { colors, spacing, typography } from "@/theme/tokens";
import { useLiveData } from "@/context/LiveDataContext";
import type { AppNotification, NotificationLevel } from "@/types/domain";

const LEVEL_CONFIG: Record<NotificationLevel, { color: string; bg: string; icon: string }> = {
  success: { color: "#22c55e", bg: "#052e16", icon: "✅" },
  warning: { color: "#f59e0b", bg: "#451a03", icon: "⚠️" },
  error:   { color: "#ef4444", bg: "#450a0a", icon: "❌" },
  info:    { color: "#60a5fa", bg: "#0c1a2e", icon: "ℹ️" },
};

interface Props {
  maxVisible?: number;
  compact?: boolean;
}

export function NotificationCenter({ maxVisible = 20, compact = false }: Props) {
  const { snapshot, unreadCount, markAllRead, clearNotifications } = useLiveData();
  const notifications = (snapshot.notifications ?? []).slice(0, maxVisible);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Text style={styles.title}>🔔 Bildirimler</Text>
          {unreadCount > 0 && (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{unreadCount > 99 ? "99+" : unreadCount}</Text>
            </View>
          )}
        </View>
        <View style={styles.headerActions}>
          {unreadCount > 0 && (
            <TouchableOpacity style={styles.actionBtn} onPress={markAllRead}>
              <Text style={styles.actionBtnText}>Okundu işaretle</Text>
            </TouchableOpacity>
          )}
          {notifications.length > 0 && (
            <TouchableOpacity style={styles.actionBtn} onPress={clearNotifications}>
              <Text style={[styles.actionBtnText, { color: "#ef4444" }]}>Temizle</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>

      {notifications.length === 0 ? (
        <View style={styles.empty}>
          <Text style={styles.emptyIcon}>🔕</Text>
          <Text style={styles.emptyText}>Henüz bildirim yok</Text>
        </View>
      ) : (
        <ScrollView style={compact ? styles.listCompact : styles.list} showsVerticalScrollIndicator={false}>
          {notifications.map((n) => (
            <NotificationItem key={n.id} notification={n} compact={compact} />
          ))}
        </ScrollView>
      )}
    </View>
  );
}

function NotificationItem({ notification: n, compact }: { notification: AppNotification; compact: boolean }) {
  const cfg = LEVEL_CONFIG[n.level] ?? LEVEL_CONFIG.info;
  const fadeAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1,
      duration: 300,
      useNativeDriver: true,
    }).start();
  }, []);

  return (
    <Animated.View style={[styles.item, { backgroundColor: cfg.bg, borderLeftColor: cfg.color, opacity: fadeAnim }]}>
      <Text style={styles.itemIcon}>{cfg.icon}</Text>
      <View style={styles.itemBody}>
        <Text style={[styles.itemMsg, compact && styles.itemMsgCompact]} numberOfLines={compact ? 1 : 3}>
          {n.message}
        </Text>
        {!compact && (
          <Text style={styles.itemTime}>{formatTime(n.timestamp)}</Text>
        )}
      </View>
    </Animated.View>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: "#0a0f1e",
    borderRadius: 14,
    padding: spacing.md,
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: "#1e293b",
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    flexWrap: "wrap",
    gap: spacing.xs,
  },
  headerLeft: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  title: { color: colors.text, fontWeight: "700", fontSize: typography.body },
  badge: {
    backgroundColor: "#ef4444",
    borderRadius: 10,
    minWidth: 20,
    height: 20,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 5,
  },
  badgeText: { color: "#fff", fontSize: 11, fontWeight: "800" },
  headerActions: { flexDirection: "row", gap: spacing.sm },
  actionBtn: { padding: spacing.xs },
  actionBtnText: { color: colors.primary, fontSize: typography.small, fontWeight: "600" },

  list: { maxHeight: 240 },
  listCompact: { maxHeight: 120 },

  item: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    padding: spacing.sm,
    borderRadius: 8,
    borderLeftWidth: 3,
    marginBottom: spacing.xs,
  },
  itemIcon: { fontSize: 14, marginTop: 1 },
  itemBody: { flex: 1, gap: 2 },
  itemMsg: { color: colors.text, fontSize: typography.small, lineHeight: 18 },
  itemMsgCompact: { fontSize: 12 },
  itemTime: { color: colors.textMuted, fontSize: 11 },

  empty: { alignItems: "center", paddingVertical: spacing.xl, gap: spacing.xs },
  emptyIcon: { fontSize: 28 },
  emptyText: { color: colors.textMuted, fontSize: typography.small },
});
