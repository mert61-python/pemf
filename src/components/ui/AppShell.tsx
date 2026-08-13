// Author: mertaygn, cglrgrkn
import { ReactNode, useEffect, useRef, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View, PanResponder } from "react-native";
import { Activity, BarChart3, Bell, BrainCircuit, ClipboardList, History, LayoutDashboard, MoreHorizontal, Settings, SlidersHorizontal, Waves, Users, Heart, Stethoscope, FlaskConical, ChevronDown, LogOut, Check, type LucideIcon } from "lucide-react-native";
import { LinearGradient } from "expo-linear-gradient";
import { BlurView } from "expo-blur";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useResponsive } from "@/hooks/useResponsive";
import { useTeardownGuard } from "@/hooks/useTeardownGuard";
import { installedModes } from "@/services/installedProfiles";
import { getStoredDeviceId } from "@/services/config";
import { DevicePairingGuide } from "@/components/domain/DevicePairingGuide";
import { colors, radius, spacing, typography, rf, rs, gradients, elevation } from "@/theme/tokens";
import { RouteKey } from "@/types/domain";
import { useUserMode } from "@/context/UserModeContext";
import { useAuth } from "@/context/AuthContext";
import { canAccess } from "@/config/access";
import { useLiveData } from "@/context/LiveDataContext";
import { AuroraBackground } from "@/components/ui/AuroraBackground";
import { NotificationCenter } from "@/components/ui/NotificationCenter";
import { useToast } from "@/components/ui/ToastProvider";
import { UpdateBanner } from "@/components/ui/UpdateBanner";
import { MobileUpdateBanner } from "@/components/domain/MobileUpdateBanner";
import { RecoveryCodeBanner } from "@/components/domain/RecoveryCodeBanner";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";
import { OperatorSwitcher } from "@/components/domain/OperatorSwitcher";

/** Uygulama ikonu — AuthScreen ile AYNI kaynak (assets/icon.png) → tek görsel kimlik. */
const APP_ICON = require("../../../assets/icon.png");

interface NavItem {
  key: RouteKey;
  label: string;
  icon: LucideIcon;
}

/** Navigasyon ögesi = ROTA (ekran açar) ‖ AKSİYON (ekran açmaz, iş yapar: çıkış).
 *  NEDEN "logout" bir RouteKey DEĞİL: RouteKey; routeMeta, PemfApp render-switch'i, canAccess ve
 *  swipe-gezinme zincirini besliyor. Çıkışı rota yapmak (a) var olmayan bir ekran için sahte
 *  başlık/render dalı eklemeyi gerektirir, (b) alt barda kaydırarak KAZARA oturum kapatmayı
 *  mümkün kılar. Aksiyon-ögesi ikisini de kapatır (swipe yalnız rota ögelerini gezer). */
type NavEntry = { kind: "route"; item: NavItem } | { kind: "action"; id: "logout"; label: string; icon: LucideIcon };

/** Ayarlar'dan SONRA gelen tek aksiyon ögesi (2026-08-06 sahip isteği: üç profilde de "Çıkış Yap"). */
const LOGOUT_ITEM: Extract<NavEntry, { kind: "action" }> = {
  kind: "action",
  id: "logout",
  label: "Çıkış Yap",
  icon: LogOut,
};

// Görünürlük profile göre config/access (canAccess) ile filtrelenir. İlk 4 erişilebilir öğe
// bottom-nav'da; gerisi "Daha Fazla" menüsünde (keşfedilebilirlik fix).
const allNavItems: NavItem[] = [
  { key: "ai", label: "Akıllı Teşhis", icon: BrainCircuit },
  { key: "dashboard", label: "Ana Ekran", icon: LayoutDashboard },
  { key: "control", label: "Kontrol", icon: SlidersHorizontal },
  { key: "patients", label: "Hastalar", icon: Users },
  { key: "sensors", label: "Sensörler", icon: Activity },
  { key: "history", label: "Seans Geçmişi", icon: History },
  { key: "kpi", label: "Raporlar", icon: BarChart3 },
  { key: "simulator", label: "Simülasyon", icon: Waves },
  { key: "ai_history", label: "AI Geçmişi", icon: ClipboardList },
  { key: "settings", label: "Ayarlar", icon: Settings }
];

// Üst-bar profil-çipi/menüsü için profil meta.
// NOT: buradaki eski `researchOnly` bayrağı ÖLÜ koddu (hiçbir yerde okunmuyordu) ve üstündeki
// yorum ".edu şartı var" derken 30 satır aşağıdaki yorum "3 profil de açık" diyordu — gating'i
// okuyan geliştiriciyi yanıltıyordu. Açık-erişim BİLİNÇLİ sahip kararıdır (ödeme öncesi);
// gerçek kısıt `installedModes()`tir: masaüstü client yalnız KURULU profilleri sunar.
const PROFILE_LIST = [
  { mode: "pet_owner" as const, label: "Evcil Hayvan Sahibi", short: "Evcil", icon: Heart },
  { mode: "veterinarian" as const, label: "Veteriner Hekim", short: "Veteriner", icon: Stethoscope },
  { mode: "researcher" as const, label: "Araştırma Modu", short: "Araştırma", icon: FlaskConical },
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
  const { userMode, setUserMode } = useUserMode();
  const { logout } = useAuth();
  const { unreadCount, connectionQuality, reconnect } = useLiveData();

  // Daha önce eşleşme yapılmış mı? (kayıtlı device_id) — şeridin davranışını belirler.
  // `null` = henüz bilinmiyor; o sırada eski (yeniden dene) davranışı korunur.
  const [eslesmeVar, setEslesmeVar] = useState<boolean | null>(null);
  const [rehberAcik, setRehberAcik] = useState(false);
  useEffect(() => {
    let iptal = false;
    // ⚠️ WEB'DE REHBER YOK: web arayüzünü CİHAZIN KENDİSİ sunar (localhost) ve keşif zaten
    // origin'i kullanır (`discovery`: `Platform.OS === "web"` erken dönüşü). Orada "cihazla
    // eşleş" demek, cihazı KENDİSİYLE eşleştirmeye çağırmak olurdu. Web'de doğru olan eski
    // davranıştır: backend geçici düşmüştür, yeniden denemek anlamlıdır.
    if (Platform.OS === "web") {
      setEslesmeVar(true);
      return () => { iptal = true; };
    }
    getStoredDeviceId()
      .then((id) => { if (!iptal) setEslesmeVar(Boolean(id)); })
      .catch(() => { if (!iptal) setEslesmeVar(null); });
    return () => { iptal = true; };
    // Bağlantı durumu değişince yeniden bak: eşleştikten sonra şerit "yeniden dene"ye dönsün.
  }, [connectionQuality]);
  const { showToast } = useToast();
  const guardTeardown = useTeardownGuard();
  // Masaüstü client'ın kurduğu profiller (WelcomeScreen ile AYNI kaynak). null → kısıt yok (mobil).
  const installed = installedModes();
  const desktop = responsive.isDesktop || responsive.isTablet;
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const profileMeta = PROFILE_LIST.find((p) => p.mode === userMode);
  const ProfileIcon = profileMeta?.icon ?? Heart;

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

  const navItems = allNavItems.filter(item => canAccess(userMode, item.key));
  const [showMore, setShowMore] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  // Alt barda en fazla 4 rota + "Daha Fazla" = 5 slot. "Daha Fazla" artık HER profilde görünür
  // (pet_owner'da yalnız Çıkış için): çıkış aksiyonu orada yaşıyor, aksi halde 4 rotalı profilde
  // nav'dan çıkış yolu kalmazdı.
  const MAX_PRIMARY = 4;
  const primaryItems = navItems.length > MAX_PRIMARY ? navItems.slice(0, MAX_PRIMARY) : navItems;
  const moreRoutes = navItems.slice(primaryItems.length);
  // Sheet içeriği: kalan rotalar + EN SONDA (Ayarlar'dan sonra) Çıkış Yap.
  const moreEntries: NavEntry[] = [
    ...moreRoutes.map((item) => ({ kind: "route" as const, item })),
    LOGOUT_ITEM,
  ];
  // Yanan-sekme yalnız ROTA ögelerine bakar (aksiyonun "aktif" hâli yoktur).
  const moreActive = moreRoutes.some((i) => i.key === activeRoute);

  /**
   * TEK çıkış handler'ı — profil menüsü, kenar çubuğu ve "Daha Fazla" sheet'i AYNI yolu kullanır
   * (davranış sürüklenmesi olmasın).
   *  1) HASTA GÜVENLİĞİ: bobinler çalışıyorsa önce onay + durdurma (useTeardownGuard); durdurma
   *     teyit edilemezse çıkış İPTAL — operatör ACİL DURDUR'un olduğu ekranda kalır.
   *  2) Boştayken de onay: "Çıkış Yap" artık Ayarlar'ın hemen ardında duruyor → yanlış dokunuş
   *     riski var ve kazara çıkış, mobilde e-posta+şifre tekrarı demek.
   * (useCallback ile sarılmadı: memoize edilmiş bir çocuğa geçmiyor ve React-compiler lint'i bu
   *  bileşende mevcut memoizasyonu koruyamadığı için hata veriyordu — sade fonksiyon yeterli.)
   */
  const handleLogout = async () => {
    const ok = await guardTeardown("Çıkış yapmak", {
      confirmWhenIdle: {
        title: "Çıkış Yap",
        body: "Oturum kapatılacak; tekrar girmek için e-posta ve şifre gerekir.",
        confirmLabel: "Çıkış yap",
      },
    });
    if (!ok) return;
    setProfileMenuOpen(false);
    setShowMore(false);
    logout();
  };

  // KÖK NEDEN FIX: panResponder useRef ile BİR KEZ oluşur → closure ilk render'ın activeRoute'unu
  // (dashboard) yakalardı (stale) → her swipe dashboard'dan hesaplanıp YANLIŞ taba gidiyordu.
  // Güncel değerleri ref'lerden okuyoruz + tek-swipe-tek-geçiş debounce.
  const desktopRef = useRef(desktop); desktopRef.current = desktop;
  const activeRouteRef = useRef(activeRoute); activeRouteRef.current = activeRoute;
  // Swipe, ALT BARDAKİ GÖRÜNÜR sekmeleri (primaryItems) gezsin — eskiden tüm navItems'i
  // indeksliyordu, böylece kaydırma alt barda karşılığı olmayan "Daha Fazla" ekranlarına gidip
  // yanan-sekme ile uyumsuz kalıyordu.
  const primaryItemsRef = useRef(primaryItems); primaryItemsRef.current = primaryItems;
  const onRouteChangeRef = useRef(onRouteChange); onRouteChangeRef.current = onRouteChange;
  const lastNavRef = useRef(0);

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      // Yalnız NET yatay hareketi yakala: |dx| baskın (dikeyin ~1.8 katı) + eşik. Diyagonal/dikey
      // kaydırma ve dokunmalar dokunulmadan geçer → dikey scroll ve kart-tıklamaları bloklanmaz.
      onMoveShouldSetPanResponder: (_evt, g) => {
        if (desktopRef.current) return false;
        return Math.abs(g.dx) > 28 && Math.abs(g.dx) > Math.abs(g.dy) * 1.8;
      },
      // Yatay swipe'ı sahiplenince başka bir bileşen (iç ScrollView vb.) ortadan ÇALMASIN.
      onPanResponderTerminationRequest: () => false,
      onPanResponderRelease: (_evt, g) => {
        if (desktopRef.current) return;
        const horizontal = Math.abs(g.dx) > Math.abs(g.dy) * 1.5;
        // Uzun sürükleme (>=64px) VEYA hızlı flick (>=32px + hız) sekme değiştirir; küçük/dikey oynama yok sayılır.
        const strong = Math.abs(g.dx) >= 64 || (Math.abs(g.dx) >= 32 && Math.abs(g.vx) >= 0.35);
        if (!horizontal || !strong) return;
        const now = Date.now();
        if (now - lastNavRef.current < 500) return; // tek swipe = tek geçiş (çift-atlama önle)
        const items = primaryItemsRef.current;
        const idx = items.findIndex((i) => i.key === activeRouteRef.current);
        if (idx === -1) return; // aktif ekran alt barda değil (Daha Fazla içinden) → swipe-gezinme yok
        const dir = g.dx < 0 ? 1 : -1; // sola çek → sonraki tab, sağa çek → önceki tab
        const next = idx + dir;
        if (next >= 0 && next < items.length) {
          lastNavRef.current = now;
          onRouteChangeRef.current(items[next].key);
        }
      },
      onPanResponderTerminate: () => { /* iptal → sessizce bırak (yanlış geçiş yok) */ },
    })
  ).current;

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <AuroraBackground intensity={0.4} />
      {desktop ? (
        <View style={styles.sidebar}>
          <View style={styles.brand}>
            {/* Marka ikonu = UYGULAMA İKONU. Önceden jenerik bir `Gauge` (gösterge) ikonu
                gradyan kutu içinde duruyordu; giriş ekranı, masaüstü kısayolu, APK ve tarayıcı
                sekmesi hep gerçek ikonu gösterirken yalnız burası farklıydı. Tek görsel kimlik. */}
            <Image source={APP_ICON} style={styles.brandLogoImg} resizeMode="contain" />
            <View>
              <Text style={styles.brandTitle}>PEMF Vet</Text>
            </View>
          </View>
          <ScrollView style={styles.navScroll} contentContainerStyle={styles.navList} showsVerticalScrollIndicator={false}>
            {navItems.map((item) => (
              <NavButton
                key={item.key}
                label={item.label}
                icon={item.icon}
                active={activeRoute === item.key}
                compact={false}
                onPress={() => onRouteChange(item.key)}
              />
            ))}
            {/* Ayarlar'dan SONRA: Çıkış Yap. Yıkıcı stille ayrıldı (yanlış tıklama riski). */}
            <NavButton
              label={LOGOUT_ITEM.label}
              icon={LOGOUT_ITEM.icon}
              active={false}
              compact={false}
              danger
              onPress={handleLogout}
            />
          </ScrollView>
        </View>
      ) : null}

      <View style={styles.main} {...(!desktop ? panResponder.panHandlers : {})}>
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <Text style={styles.title} numberOfLines={1}>{title}</Text>
            <Text style={styles.subtitle} numberOfLines={2}>{subtitle}</Text>
          </View>
          <View style={styles.headerRight}>
            {/* AKTİF OPERATÖR (2026-08-08): tek makineyi 3-4 veteriner paylaşıyor. Kayıtlara kimin
                yazıldığı ÜST BARDA sürekli görünür olmalı — yanlış kimlikle çalışmak, kaydı
                yanlış hekime atfeder (KVKK + klinik sorumluluk). Dokununca PIN ile hızlı geçiş. */}
            <OperatorSwitcher />
            {userMode && (
              <Pressable style={styles.profileChip} onPress={() => setProfileMenuOpen(true)} accessibilityRole="button" accessibilityLabel="Profil değiştir">
                <ProfileIcon size={16} color={colors.primary} />
                {desktop && <Text style={styles.profileChipText}>{profileMeta?.short}</Text>}
                <ChevronDown size={14} color={colors.textMuted} />
              </Pressable>
            )}
            {!desktop && (
              // a11y: ikon-only düğmede rol/etiket yoktu ve dokunma hedefi ~30pt idi (min 44pt).
              <Pressable
                onPress={() => onRouteChange("settings")}
                style={styles.iconBtn}
                accessibilityRole="button"
                accessibilityLabel="Ayarlar"
              >
                <Settings size={22} color={colors.textMuted} />
              </Pressable>
            )}
            <Pressable onPress={reconnect} style={styles.wsContainer} accessibilityRole="button" accessibilityLabel="Bağlantıyı yenile">
              {connectionQuality === "offline" && (
                <Text style={[styles.wsTextOff, styles.wsTextOffline]} numberOfLines={1}>
                  Çevrimdışı
                </Text>
              )}
              <View style={[
                styles.wsIndicator,
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

        {/* Profil hızlı-geçiş menüsü — üst-bar çipinden açılır + Çıkış. (Eski "araştırma yalnız
            .edu'da" notu kaldırıldı: .edu gating KAPALI, gerçek kısıt `installedModes()`.) */}
        <Modal visible={profileMenuOpen} transparent animationType="fade" onRequestClose={() => setProfileMenuOpen(false)}>
          <Pressable style={styles.profileMenuBackdrop} onPress={() => setProfileMenuOpen(false)}>
            <BlurView intensity={18} tint="dark" style={StyleSheet.absoluteFill} />
            {/* Kart, backdrop Pressable'ının ÇOCUĞU: düz `View` dokunuşu YUTMADIĞINDAN kart içindeki
                boşluğa (başlık, ayraç, satır aralıkları) dokunmak menüyü kapatıyordu. Bildirim
                sayfasında doğru desen (`onPress={() => {}}` ile Pressable) zaten kullanılıyordu. */}
            <Pressable onPress={() => {}} style={[styles.profileMenuCard, { marginTop: insets.top + rs(52) }]}>
              <Text style={styles.profileMenuTitle}>Profil Değiştir</Text>
              {/* Açık-erişim (bilinçli): entitlement gating kapalı. ANCAK `installedModes()`
                  filtresi WelcomeScreen'de vardı, BURADA YOKTU → yalnız "Ev Sahibi" profili kurulu
                  bir masaüstü client'ta kullanıcı buradan "Veteriner"e geçip manuel bobin kontrolüne
                  ulaşabiliyordu (modelleri/dosyaları kurulu olmayan bir profil). İki yer artık aynı
                  kaynağı kullanır. */}
              {PROFILE_LIST.filter((p) => !installed || installed.has(p.mode)).map((p) => {
                const Icon = p.icon;
                const active = userMode === p.mode;
                return (
                  <Pressable
                    key={p.mode}
                    onPress={() => { setUserMode(p.mode); setProfileMenuOpen(false); }}
                    style={[styles.profileMenuRow, active && styles.profileMenuRowActive]}
                    accessibilityRole="button"
                  >
                    <Icon size={18} color={active ? colors.primary : colors.textMuted} />
                    <Text style={[styles.profileMenuLabel, active && styles.profileMenuLabelActive]}>{p.label}</Text>
                    {active ? <Check size={16} color={colors.primary} /> : null}
                  </Pressable>
                );
              })}
              <View style={styles.profileMenuDivider} />
              {/* HASTA GÜVENLİĞİ: çıkış kabuğu (ve tüm ACİL DURDUR erişimini) söker → seans
                  sürerken önce onay al + bobinleri durdur. Ayrıca satırı profil satırlarından
                  görsel olarak AYIR: eskiden aynı stille dizildiği için yanlış dokunuş çok kolaydı. */}
              <Pressable
                onPress={handleLogout}
                style={[styles.profileMenuRow, styles.profileMenuDanger]}
                accessibilityRole="button"
                accessibilityLabel="Çıkış yap"
              >
                <LogOut size={18} color={colors.danger} />
                <Text style={[styles.profileMenuLabel, { color: colors.danger }]}>Çıkış Yap</Text>
              </Pressable>
            </Pressable>
          </Pressable>
        </Modal>

        {/* ⚠️ ŞERİT İKİ FARKLI DURUMU AYIRIR (2026-08-13, sahip bildirimi).
            Eskiden tek metin vardı ve dokunmak HER ZAMAN `reconnect()` çağırıyordu. Ama telefon
            cihazla farklı ağdayken ve HENÜZ HİÇ EŞLEŞMEMİŞKEN o düğme sonsuza kadar başarısız
            olacak bir işi tekrarlıyordu: keşif merdiveninin uzaktan adımı KAYITLI bir device_id
            ister (discovery adım 3) ve ilk açılışta o kimlik yoktur. Kullanıcı ne olduğunu ve ne
            yapacağını öğrenemiyordu.
              • Hiç eşleşmemiş → REHBER aç (kodu nereden alacağını göster + girdiği yeri ver).
              • Daha önce eşleşmiş → yeniden dene (geçici kopma olabilir; kod istemek gereksiz). */}
        {connectionQuality === "offline" && (
          <Pressable
            onPress={eslesmeVar === false ? () => setRehberAcik(true) : reconnect}
            style={[styles.connBanner, styles.connBannerOffline]}
            testID="conn-banner"
            accessibilityRole="button"
            accessibilityLabel={
              eslesmeVar === false ? "Cihaza bağlanma rehberini aç" : "Bağlantıyı yeniden dene"
            }
          >
            <Text style={styles.connBannerText}>
              {eslesmeVar === false
                ? "⚠ Cihaz bulunamadı — gösterilen değerler GERÇEK DEĞİL. Bağlanmak için DOKUNUN."
                : "⚠ Cihaza bağlanılamıyor — gösterilen değerler GERÇEK DEĞİL. Dokunup yeniden bağlan."}
            </Text>
          </Pressable>
        )}
        <DevicePairingGuide visible={rehberAcik} onClose={() => setRehberAcik(false)} />

        <UpdateBanner />
        {/* Mobil oto-güncelleme (2026-08-08): Android'de yeni APK varsa tek dokunuşla
            indirip kurar — kullanıcı siteden tekrar indirmez. Seans sürerken gizlenir. */}
        <MobileUpdateBanner />
        {/* ⚠️ FELAKET KURTARMA (2026-08-09 denetimi): hasta kayıtları bu makineye bağlı bir
            anahtarla şifreli. Kurtarma kodu makine dışına kopyalanmazsa disk arızasında
            off-site yedekler bile SONSUZA DEK açılamaz. Operatör onaylayana kadar kalıcı. */}
        <RecoveryCodeBanner />

        <ScrollView
          contentContainerStyle={[
            styles.content,
            // Kayan ACİL DURDUR butonu içeriğin son satırını örtmesin.
            !desktop ? { paddingBottom: rs(160) + insets.bottom } : { paddingBottom: rs(84) },
          ]}
          keyboardShouldPersistTaps="handled"
        >
          {children}
        </ScrollView>
      </View>

      {/* HASTA GÜVENLİĞİ: donanım çalışırken HER rotada erişilebilir durdurma. Alt navigasyonun
          üstünde konumlanır (mobil); masaüstünde alt bar yok. */}
      <GlobalEmergencyStop bottomOffset={desktop ? 0 : rs(76)} />

      {!desktop ? (
        <View style={[styles.bottomNav, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
          {primaryItems.map((item) => (
            <NavButton
              key={item.key}
              label={item.label}
              icon={item.icon}
              active={activeRoute === item.key}
              compact
              onPress={() => onRouteChange(item.key)}
            />
          ))}
          <Pressable
            accessibilityLabel="Daha Fazla"
            accessibilityRole="button"
            onPress={() => setShowMore(true)}
            style={[styles.bottomItem, moreActive && styles.navItemActive]}
          >
            <MoreHorizontal size={18} color={moreActive ? colors.primary : colors.textMuted} />
            <Text style={[styles.bottomLabel, moreActive && styles.navLabelActive]} numberOfLines={1}>Daha Fazla</Text>
          </Pressable>
        </View>
      ) : null}

      {!desktop ? (
        <Modal visible={showMore} transparent animationType="fade" onRequestClose={() => setShowMore(false)}>
          <Pressable style={styles.moreBackdrop} onPress={() => setShowMore(false)}>
            <BlurView intensity={24} tint="dark" style={StyleSheet.absoluteFill} />
            {/* Aynı sorun: sheet içi boşluğa dokunmak menüyü kapatıyordu. */}
            <Pressable onPress={() => {}} style={[styles.moreSheet, { paddingBottom: insets.bottom + spacing.lg }]}>
              <Text style={styles.moreTitle}>Diğer Ekranlar</Text>
              {moreEntries.map((entry) => {
                if (entry.kind === "action") {
                  // Çıkış: rota DEĞİL → onRouteChange çağrılmaz, sheet handler içinde kapanır.
                  const Icon = entry.icon;
                  return (
                    <Pressable
                      key={entry.id}
                      onPress={handleLogout}
                      style={[styles.moreRow, styles.profileMenuDanger]}
                      accessibilityRole="button"
                      accessibilityLabel="Çıkış yap"
                    >
                      <Icon size={20} color={colors.danger} />
                      <Text style={[styles.moreRowLabel, { color: colors.danger }]}>{entry.label}</Text>
                    </Pressable>
                  );
                }
                const { item } = entry;
                const Icon = item.icon;
                const active = activeRoute === item.key;
                return (
                  <Pressable
                    key={item.key}
                    onPress={() => { onRouteChange(item.key); setShowMore(false); }}
                    style={[styles.moreRow, active && styles.navItemActive]}
                  >
                    <Icon size={20} color={active ? colors.primary : colors.textMuted} />
                    <Text style={[styles.moreRowLabel, active && styles.navLabelActive]}>{item.label}</Text>
                  </Pressable>
                );
              })}
            </Pressable>
          </Pressable>
        </Modal>
      ) : null}

      <Modal visible={showNotifications} transparent animationType="fade" onRequestClose={() => setShowNotifications(false)}>
        <Pressable style={styles.notifBackdrop} onPress={() => setShowNotifications(false)}>
          <BlurView intensity={24} tint="dark" style={StyleSheet.absoluteFill} />
          <Pressable style={[styles.notifSheet, { marginTop: insets.top + spacing.xl }]} onPress={() => {}}>
            <NotificationCenter maxVisible={20} />
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

// `item` yerine label+icon alır: rota ögeleri kadar AKSİYON ögesi (Çıkış) de aynı düğmeyle
// çizilebilsin — aksiyonun RouteKey'i yoktur. `danger` yıkıcı ögeyi görsel olarak ayırır.
function NavButton({ label, icon: Icon, active, compact, danger, onPress }: {
  label: string; icon: LucideIcon; active: boolean; compact: boolean; danger?: boolean; onPress: () => void;
}) {
  const tint = danger ? colors.danger : active ? colors.primary : colors.textMuted;
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      onPress={onPress}
      style={[compact ? styles.bottomItem : styles.navItem, active && styles.navItemActive, danger && styles.navItemDanger]}
    >
      <Icon size={18} color={tint} />
      <Text
        style={[compact ? styles.bottomLabel : styles.navLabel, active && styles.navLabelActive, danger && { color: colors.danger }]}
        numberOfLines={1}
      >
        {label}
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
    width: rs(248)
  },
  brand: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.md
  },
  brandTitle: {
    color: colors.text,
    fontSize: rf(18),
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
    minHeight: rs(44),
    paddingHorizontal: spacing.md
  },
  navItemActive: {
    backgroundColor: colors.primarySoft
  },
  // Kenar çubuğundaki Çıkış: profil menüsündeki `profileMenuDanger` ile AYNI görsel dil →
  // yıkıcı öge, rota ögelerinden bakışta ayrılır (Ayarlar'ın hemen altında yanlış tıklama riski).
  navItemDanger: {
    backgroundColor: colors.danger + "14",
    borderWidth: 1,
    borderColor: colors.danger + "44",
    marginTop: spacing.sm,
    paddingVertical: spacing.sm,
  },
  // Image (ImageStyle) — brandLogo bir ViewStyle'dir (elevation gölgeleri Image'da geçersiz).
  brandLogoImg: {
    width: rs(40),
    height: rs(40),
    borderRadius: rs(12),
  },
  brandLogo: {
    width: rs(40),
    height: rs(40),
    borderRadius: rs(12),
    alignItems: "center",
    justifyContent: "center",
    ...elevation("glowPrimary"),
  },
  navLabel: {
    color: colors.textMuted,
    fontSize: typography.body,
    fontWeight: "700"
  },
  navLabelActive: {
    color: colors.primary
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
  headerLeft: { flex: 1, minWidth: 0, marginRight: spacing.sm },
  headerRight: { flexShrink: 0, flexDirection: "row", alignItems: "center", gap: spacing.md },
  iconBtn: { minWidth: rs(44), minHeight: rs(44), alignItems: "center", justifyContent: "center" },
  profileChip: {
    flexDirection: "row", alignItems: "center", gap: rs(5),
    paddingVertical: spacing.xs, paddingHorizontal: spacing.sm,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgAlt,
  },
  profileChipText: { color: colors.text, fontSize: typography.small, fontWeight: "700" },
  profileMenuBackdrop: { flex: 1, alignItems: "flex-end", paddingRight: spacing.md },
  profileMenuCard: {
    backgroundColor: colors.bgAlt, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.xs, minWidth: rs(230),
    shadowColor: "#000", shadowOpacity: 0.4, shadowRadius: 16, shadowOffset: { width: 0, height: rs(6) }, elevation: 10,
  },
  profileMenuTitle: {
    color: colors.textMuted, fontSize: typography.caption, fontWeight: "700",
    paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, letterSpacing: 0.5,
  },
  profileMenuRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.md, paddingHorizontal: spacing.sm, borderRadius: radius.sm,
  },
  profileMenuRowActive: { backgroundColor: colors.primarySoft },
  profileMenuLabel: { flex: 1, color: colors.textMuted, fontSize: typography.body, fontWeight: "600" },
  profileMenuLabelActive: { color: colors.text, fontWeight: "800" },
  profileMenuDivider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.xs, marginHorizontal: spacing.sm },
  // Yıkıcı satırı profil satırlarından görsel olarak ayır (yanlış-dokunuş riski).
  profileMenuDanger: { backgroundColor: colors.danger + "14", borderWidth: 1, borderColor: colors.danger + "44", marginTop: spacing.xs },
  wsContainer: { flexShrink: 1, flexDirection: "row", alignItems: "center", gap: spacing.xs },
  wsTextOff: { flexShrink: 1, color: "#f59e0b", fontSize: rf(10), fontWeight: "700" },
  wsIndicator: {
    width: rs(10), height: rs(10), borderRadius: 5,
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
  connBannerText: { color: "#fcd34d", fontSize: rf(12), fontWeight: "700", textAlign: "center" },
  notifBadgeWrap: { position: "relative", padding: spacing.xs },
  notifBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", alignItems: "flex-end", paddingHorizontal: spacing.lg },
  notifSheet: { width: "100%", maxWidth: rs(420) },
  notifBadge: {
    position: "absolute", top: 0, right: 0,
    backgroundColor: "#ef4444",
    borderRadius: 8, minWidth: rs(16), height: rs(16),
    alignItems: "center", justifyContent: "center", paddingHorizontal: 3,
  },
  notifBadgeText: { color: "#fff", fontSize: rf(9), fontWeight: "800" },
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
    minHeight: rs(56),
    justifyContent: "center",
    paddingHorizontal: spacing.xs
  },
  bottomLabel: {
    color: colors.textMuted,
    fontSize: rf(10),
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
    minHeight: rs(48)
  },
  moreRowLabel: { color: colors.textMuted, fontSize: typography.body, fontWeight: "700" }
});
