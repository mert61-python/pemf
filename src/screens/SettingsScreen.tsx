import { useEffect, useState } from "react";
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView, ActivityIndicator, Platform } from "react-native";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography, radius, rf, rs } from "@/theme/tokens";
import { apiGet, apiPost, platformAlert } from "@/services/apiClient";
import { Save, UserCog, Network, ServerCrash, RefreshCcw, Trash2, Wifi, Search, Link2, Copy } from "lucide-react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { updateServiceConfig, loadStoredApiToken, setStoredDeviceId } from "@/services/config";
import { getDeviceByPairingCode, getRemoteUrlForDevice } from "@/services/deviceRegistry";
import { checkHealth, exchangeCodeForToken } from "@/services/discovery";
import { useUserMode } from "@/context/UserModeContext";
import { useToast } from "@/components/ui/ToastProvider";


export function SettingsScreen() {
  const { setUserMode, isExpert } = useUserMode();
  const { showToast } = useToast();
  const [settings, setSettings] = useState({
    clinic_name: "",
    clinic_phone: "",
    ble_gateway_mac: "",
    mqtt_broker: "localhost",
    mqtt_port: "1883",
    server_ip: "127.0.0.1"
  });
  
  const [loading, setLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState("");
  const [searching, setSearching] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<"idle" | "ok" | "fail">("idle");

  // Bu cihazın eşleştirme kimliği (operatör paylaşsın diye) — /api/health'ten gelir.
  const [pairingCode, setPairingCode] = useState("");
  const [deviceId, setDeviceId] = useState("");
  // Uzak cihaza bağlanmak için girilen kod/kimlik.
  const [remoteInput, setRemoteInput] = useState("");
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    let mounted = true;
    const fetchSettings = async () => {
      await loadStoredApiToken();
      const clinicPhone = (await AsyncStorage.getItem("pemf_clinic_phone")) || "";
      setSettings(prev => ({ ...prev, clinic_phone: clinicPhone }));
      try {
        const savedIp = await AsyncStorage.getItem("@pemf_server_address") ||
                        await AsyncStorage.getItem("@pemf_server_ip");
        if (savedIp) {
          setSettings(prev => ({ ...prev, server_ip: savedIp }));
          // WEB: cihazın KENDİ paneli origin'den (localhost) serve edilir. Kayıtlı adrese
          // (ör. ESKİ/ölü tünel URL'si — quick tünel her restart değişir) yönlendirirsek
          // /health + /settings origin yerine ölü adrese gider → pairing kodu YAZILMAZ.
          // Native mobilde gerekir (cihaza bağlanmak için), web'de DEĞİL.
          if (Platform.OS !== "web") updateServiceConfig(savedIp);
        }
      } catch (e) {}

      const data = await apiGet<any>("/settings/", {});
      if (mounted && data) {
        setSettings(prev => ({
          ...prev,
          clinic_name: data.clinic_name || "",
          ble_gateway_mac: data.ble_gateway_mac || "",
          mqtt_broker: data.mqtt_broker || "localhost",
          mqtt_port: data.mqtt_port?.toString() || "1883"
        }));
      }

      // Bağlı cihazın eşleştirme kimliğini al (operatör başka bir cihaza paylaşsın diye).
      const health = await apiGet<any>("/health", {}, { silent: true });
      if (mounted && health) {
        setPairingCode(health.pairingCode || "");
        setDeviceId(health.deviceId || "");
      }
    };
    fetchSettings();
    return () => { mounted = false; };
  }, []);

  /** Girilen adrese bağlanmayı test eder */
  const handleTestConnection = async () => {
    setSearching(true);
    setConnectionStatus("idle");
    try {
      const addr = settings.server_ip;
      const base = addr.startsWith("http") ? addr.replace(/\/$/, "") : `http://${addr}:8000`;
      const controller = new AbortController();
      setTimeout(() => controller.abort(), 5000);
      const res = await fetch(`${base}/api/health`, { signal: controller.signal });
      if (res.ok) {
        updateServiceConfig(addr);
        await AsyncStorage.setItem("@pemf_server_address", addr).catch(() => {});
        setConnectionStatus("ok");
        showToast("✅ Bağlantı başarılı! Adres kaydedildi.", "success");
      } else {
        setConnectionStatus("fail");
        showToast("❌ Sunucuya ulaşılamadı.", "error");
      }
    } catch {
      setConnectionStatus("fail");
      showToast("❌ Bağlantı zaman aşımına uğradi.", "error");
    }
    setSearching(false);
  };

  /** Otomatik ağ tarama */
  const handleAutoSearch = async () => {
    setSearching(true);
    setConnectionStatus("idle");
    showToast("🔍 Ağ taranıyor...", "info");
    try {
      const subnets = ["192.168.1", "192.168.0", "10.0.0", "172.16.0"];
      const candidates = [100, 1, 101, 2, 102, 110, 50, 200];

      for (const subnet of subnets) {
        // Her subnet için paralel tarama
        const results = await Promise.allSettled(
          candidates.map(async (last) => {
            const ip = `${subnet}.${last}`;
            const ctrl = new AbortController();
            const timeout = setTimeout(() => ctrl.abort(), 1500);
            try {
              const res = await fetch(`http://${ip}:8000/api/health`, { signal: ctrl.signal });
              clearTimeout(timeout);
              if (res.ok) {
                const data = await res.json();
                if (data?.service === "PEMF-Vet") return ip;
              }
            } catch { clearTimeout(timeout); }
            throw new Error("not found");
          })
        );

        for (const r of results) {
          if (r.status === "fulfilled" && r.value) {
            const ip = r.value;
            setSettings(prev => ({ ...prev, server_ip: ip }));
            updateServiceConfig(ip);
            await AsyncStorage.setItem("@pemf_server_address", ip).catch(() => {});
            setConnectionStatus("ok");
            showToast(`✅ PEMF sunucusu bulundu: ${ip}`, "success");
            setSearching(false);
            return;
          }
        }
      }
      showToast("⚠️ Ağda PEMF sunucusu bulunamadı. QR kodu tarayın.", "info");
    } catch { }
    setSearching(false);
  };

  /**
   * Uzak cihaza eşleştirme kodu YA DA cihaz kimliği ile bağlan.
   * Girdi <= 8 karakter ise EŞLEŞTİRME KODU, değilse CİHAZ KİMLİĞİ kabul edilir.
   */
  const handleRemoteConnect = async () => {
    const input = remoteInput.trim();
    if (!input) return;
    setConnecting(true);
    try {
      let tunnelUrl: string | null = null;
      let resolvedDeviceId = input;

      if (input.length <= 8) {
        // EŞLEŞTİRME KODU → cihazı bul
        const device = await getDeviceByPairingCode(input);
        if (device && device.tunnel_url) {
          tunnelUrl = device.tunnel_url;
          resolvedDeviceId = device.device_id;
        }
      } else {
        // CİHAZ KİMLİĞİ → güncel tunnel_url'i bul
        tunnelUrl = await getRemoteUrlForDevice(input);
      }

      // 1) Kayıt bulunamadı → kod/kimlik yanlış olabilir (çevrimdışıdan AYIR).
      if (!tunnelUrl) {
        setConnectionStatus("fail");
        showToast("Bu kod/kimlikle eşleşen kayıtlı cihaz bulunamadı. Kodu kontrol edin.", "error");
        return;
      }

      // 2) Kayıt var ama cihaz şu an erişilemez → KAYDETMEDEN ÖNCE health doğrula.
      const alive = await checkHealth(tunnelUrl);
      if (!alive) {
        setConnectionStatus("fail");
        showToast("Cihaz bulundu ama şu an çevrimdışı/erişilemiyor.", "error");
        return;
      }

      // 3) Canlı → kaydet + bağlan.
      updateServiceConfig(tunnelUrl);
      // Kod-yolu (hiç LAN'a girmemiş telefon): 6-haneli kodu cihaz token'ıyla takas et →
      // uzaktan HTTP + WS auth çalışsın. Yoksa "bağlandı ✓" ama tüm veri 401 olurdu (audit P0).
      if (input.length <= 8) { await exchangeCodeForToken(tunnelUrl, input); }
      await setStoredDeviceId(resolvedDeviceId);
      await AsyncStorage.setItem("@pemf_server_address", tunnelUrl).catch(() => {});
      setSettings(prev => ({ ...prev, server_ip: tunnelUrl as string }));
      setConnectionStatus("ok");
      showToast("Cihaz eşleştirildi ve bağlanıldı ✓", "success");
    } catch {
      setConnectionStatus("fail");
      showToast("Eşleştirme sunucusuna ulaşılamadı. İnternet bağlantınızı kontrol edin.", "error");
    } finally {
      setConnecting(false);
    }
  };



  /** Bir değeri panoya kopyala (web) ya da kopyalanabilsin diye göster (native).
   *  RemoteConnectionPanel kalıbı: native'de pano kütüphanesi yok → platformAlert. */
  const copyValue = async (label: string, value: string) => {
    if (!value) return;
    if (Platform.OS === "web" && typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(value);
        showToast(`${label} panoya kopyalandı ✓`, "success");
      } catch {
        platformAlert(label, value);
      }
    } else {
      platformAlert(label, `Bu değeri kopyalayın:\n\n${value}`);
    }
  };

  const handleSave = async () => {
    setLoading(true);
    setSaveStatus("Kaydediliyor...");
    try {
      // Canonical anahtar @pemf_server_address (discovery + ilk-yükleme bunu okur) + geri-uyum için ip.
      await AsyncStorage.setItem("@pemf_server_address", settings.server_ip);
      await AsyncStorage.setItem("@pemf_server_ip", settings.server_ip);
      updateServiceConfig(settings.server_ip);
    } catch(e) {}
    const result = await apiPost<any>("/settings/", settings, { status: "error" });
    setLoading(false);
    if (result.status === "success") {
      setSaveStatus("Ayarlar başarıyla kaydedildi.");
      setTimeout(() => setSaveStatus(""), 3000);
    } else {
      setSaveStatus("Kaydetme hatası.");
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.headerTitle}>Sistem Ayarları</Text>
      <Text style={styles.intro}>Uygulama tercihleri ve cihaz bağlantı ayarları.</Text>

      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <UserCog color={colors.primary} size={20} />
          <Text style={styles.cardTitle}>Profil Ayarları</Text>
        </View>
        <Text style={styles.label}>Şu anki mod: {isExpert ? 'Veteriner Hekim' : 'Evcil Hayvan Sahibi'}</Text>
        <TouchableOpacity style={[styles.btnOutline, { marginTop: spacing.md }]} onPress={() => setUserMode(null)}>
          <Text style={styles.btnOutlineText}>Farklı Bir Profile Geçiş Yap</Text>
        </TouchableOpacity>
      </Card>

      {isExpert && (
        <Card style={styles.card}>
          <View style={styles.cardHeader}>
            <UserCog color={colors.primary} size={20} />
            <Text style={styles.cardTitle}>Klinik Bilgileri</Text>
          </View>
          <Text style={styles.label}>Klinik Adı</Text>
          <TextInput
            style={styles.input}
            accessibilityLabel="Klinik adı"
            value={settings.clinic_name}
            onChangeText={val => setSettings({...settings, clinic_name: val})}
            placeholder="Örn: VetCare Plus"
          />

          <Text style={styles.label}>Klinik Acil Telefon</Text>
          <TextInput
            style={styles.input}
            accessibilityLabel="Klinik acil telefon"
            value={settings.clinic_phone}
            onChangeText={val => { setSettings({...settings, clinic_phone: val}); AsyncStorage.setItem("pemf_clinic_phone", val).catch(() => {}); }}
            placeholder="Örn: +902125550000"
            keyboardType="phone-pad"
          />
        </Card>
      )}

      {isExpert && (
        <>
          <Card style={styles.card}>
            <View style={styles.cardHeader}>
              <Network color={colors.primary} size={20} />
              <Text style={styles.cardTitle}>Uzaktan Erişim Bağlantısı</Text>
            </View>
            <Text style={styles.helperText}>
              Cihaz OTOMATİK bağlanır — IP girmeniz gerekmez.{'\n'}
              📡 Aynı Wi-Fi → mDNS ile anında bulunur.{'\n'}
              🌐 Farklı ağ → bir kez eşleştikten sonra cihazın buluttaki güncel adresinden otomatik bağlanır.{'\n'}
              Aşağısı yalnız otomatik bağlantı olmazsa MANUEL yedektir.
            </Text>

            {/* EŞLEŞTİRME — Bu cihazın kimliği + uzak cihaza kod/kimlik ile bağlan */}
            <View style={styles.pairBox}>
              <View style={styles.pairHeaderRow}>
                <Link2 color={colors.primary} size={16} />
                <Text style={styles.pairTitle}>Cihaz Eşleştirme</Text>
              </View>

              {(pairingCode || deviceId) ? (
                <View style={styles.pairIdentity}>
                  <Text style={styles.helperText}>
                    Bu cihazı uzaktan açmak için aşağıdaki kimliği başka bir cihazla paylaşın.
                  </Text>
                  {pairingCode ? (
                    <TouchableOpacity
                      style={styles.copyRow}
                      onPress={() => copyValue("Eşleştirme kodu", pairingCode)}
                    >
                      <Text selectable style={styles.pairCodeText}>
                        Bu cihazın eşleştirme kodu: <Text style={styles.pairCodeValue}>{pairingCode}</Text>
                      </Text>
                      <Copy color={colors.primary} size={16} />
                    </TouchableOpacity>
                  ) : null}
                  {deviceId ? (
                    <TouchableOpacity
                      style={styles.copyRow}
                      onPress={() => copyValue("Cihaz kimliği", deviceId)}
                    >
                      <Text
                        selectable
                        style={[styles.pairDeviceText, { flex: 1 }]}
                        numberOfLines={1}
                        ellipsizeMode="middle"
                      >
                        Cihaz kimliği: <Text style={styles.pairDeviceValue}>{deviceId}</Text>
                      </Text>
                      <Copy color={colors.primary} size={16} />
                    </TouchableOpacity>
                  ) : null}
                </View>
              ) : (
                <Text style={styles.helperText}>
                  Bu cihazın eşleştirme kimliği yalnızca cihaza bağlıyken görünür.
                </Text>
              )}

              <Text style={[styles.label, { marginTop: spacing.md }]}>Uzak cihaza bağlan (kod ya da kimlik)</Text>
              <TextInput
                style={styles.input}
                accessibilityLabel="Uzak cihaza bağlan: eşleştirme kodu veya cihaz kimliği"
                value={remoteInput}
                onChangeText={(v) => setRemoteInput(v.replace(/\s+/g, "").toUpperCase())}
                placeholder="Eşleştirme kodu (örn: A3F9K2) veya cihaz kimliği"
                autoCapitalize="characters"
                autoCorrect={false}
              />
              <TouchableOpacity
                style={[styles.btnPrimary, { justifyContent: "center" }]}
                onPress={handleRemoteConnect}
                disabled={connecting}
              >
                {connecting
                  ? <ActivityIndicator size="small" color="#fff" />
                  : <Link2 color="#fff" size={16} />}
                <Text style={styles.btnPrimaryText}>{connecting ? "Bağlanıyor..." : "Cihaza Bağlan"}</Text>
              </TouchableOpacity>
            </View>

            {/* Otomatik Bağlantı Butonları */}
            <View style={styles.autoConnectRow}>
              <TouchableOpacity
                style={[styles.autoBtn, { borderColor: colors.primary }]}
                onPress={handleAutoSearch}
                disabled={searching}
              >
                {searching
                  ? <ActivityIndicator size="small" color={colors.primary} />
                  : <Search color={colors.primary} size={16} />}
                <Text style={[styles.autoBtnText, { color: colors.primary }]}>
                  {searching ? "Aranıyor..." : "Ağı Yeniden Tara"}
                </Text>
              </TouchableOpacity>
            </View>

            {/* Bağlantı Durum Göstergesi */}
            {connectionStatus !== "idle" && (
              <View style={[styles.connStatus, { backgroundColor: connectionStatus === "ok" ? "#1a3a1a" : "#3a1a1a" }]}>
                <Text style={{ color: connectionStatus === "ok" ? "#4ade80" : "#f87171", fontWeight: "700" }}>
                  {connectionStatus === "ok" ? "✅ Bağlı" : "❌ Bağlanamadı"}
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: rf(12), marginTop: 2 }}>{settings.server_ip}</Text>
              </View>
            )}

            <Text style={styles.label}>Manuel Sunucu Adresi</Text>
            <TextInput
              style={styles.input}
              accessibilityLabel="Manuel sunucu adresi"
              value={settings.server_ip}
              onChangeText={val => setSettings({...settings, server_ip: val})}
              placeholder="192.168.1.100 veya https://xxxx.trycloudflare.com" 
              autoCapitalize="none"
              keyboardType="default"
            />
            <TouchableOpacity style={styles.testBtn} onPress={handleTestConnection} disabled={searching}>
              <Wifi color={colors.text} size={14} />
              <Text style={styles.testBtnText}>Bağlantıyı Test Et</Text>
            </TouchableOpacity>
            <Text style={styles.helperText}>
              Manuel yedek: aynı Wi-Fi&apos;de IP (192.168.x.x:8000), farklı ağda tünel linki (https://...trycloudflare.com).
            </Text>
          </Card>

          <View style={styles.actions}>
            <TouchableOpacity style={styles.btnPrimary} onPress={handleSave} disabled={loading}>
              <Save color="#fff" size={16} />
              <Text style={styles.btnPrimaryText}>{loading ? "Kaydediliyor..." : "Ayarları Kaydet"}</Text>
            </TouchableOpacity>
            {saveStatus ? <Text style={styles.statusText}>{saveStatus}</Text> : null}
          </View>
        </>
      )}

      {isExpert && (
        <View style={{ marginTop: spacing.xl }}>
          <Card style={[styles.card as any, { borderColor: colors.danger, borderWidth: 1 }]}>
            <View style={styles.cardHeader}>
              <ServerCrash color={colors.danger} size={20} />
              <Text style={[styles.cardTitle, {color: colors.danger}]}>Donanım Bakım ve Servis</Text>
            </View>
            <Text style={styles.helperText}>Sadece acil durumlarda veya sistem kilitlenmelerinde kullanın.</Text>
            
            <View style={{ gap: spacing.md, marginTop: spacing.md }}>
              <TouchableOpacity 
                style={[styles.btnOutline, { borderColor: colors.warning }]} 
                onPress={async () => {
                  const res = await apiPost<any>("/hardware/selftest", {}, {status: "error"});
                  if (res.status === "success") showToast("Self-Test komutu donanıma gönderildi.", "success");
                  else showToast("Self-Test gönderilemedi.", "error");
                }}
              >
                <RefreshCcw color={colors.warning} size={16} style={{marginRight: 8}} />
                <Text style={[styles.btnOutlineText, { color: colors.warning }]}>Donanım Self-Test Başlat</Text>
              </TouchableOpacity>

              <TouchableOpacity 
                style={[styles.btnOutline, { borderColor: colors.danger }]} 
                onPress={async () => {
                  const res = await apiPost<any>("/hardware/reset_pwm", {}, {status: "error"});
                  if (res.status === "success") showToast("Tüm bobin PWM sinyalleri sıfırlandı.", "success");
                  else showToast("PWM sıfırlama başarısız.", "error");
                }}
              >
                <Trash2 color={colors.danger} size={16} style={{marginRight: 8}} />
                <Text style={[styles.btnOutlineText, { color: colors.danger }]}>Tüm PWM Sinyallerini Sıfırla (Reset)</Text>
              </TouchableOpacity>

              <TouchableOpacity 
                style={[styles.btnOutline, { borderColor: colors.textMuted }]} 
                onPress={async () => {
                  const res = await apiPost<any>("/hardware/cleanup_esp", {}, {status: "error"});
                  if (res.status === "success") showToast("Kopmuş cihaz bağlantıları temizlendi.", "info");
                }}
              >
                <Network color={colors.textMuted} size={16} style={{marginRight: 8}} />
                <Text style={[styles.btnOutlineText, { color: colors.textMuted }]}>Kopmuş Cihazları Ağdan Temizle</Text>
              </TouchableOpacity>
            </View>
          </Card>
        </View>
      )}

    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingBottom: spacing.xxl,
    width: "100%",
    maxWidth: rs(900),
    alignSelf: "center"
  },
  headerTitle: {
    fontSize: typography.title,
    fontWeight: "800",
    color: colors.text,
    marginBottom: spacing.xs
  },
  intro: {
    color: colors.textMuted,
    fontSize: typography.body,
    marginBottom: spacing.lg
  },
  card: {
    marginBottom: spacing.md,
    gap: spacing.sm
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.xs
  },
  cardTitle: {
    fontSize: typography.subtitle,
    fontWeight: '700',
    color: colors.text
  },
  label: {
    fontSize: typography.small,
    fontWeight: '600',
    color: colors.textSubtle,
    marginTop: spacing.xs
  },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: typography.body,
    backgroundColor: colors.bgAlt,
    color: colors.text,
    marginBottom: spacing.sm
  },
  helperText: {
    fontSize: typography.caption,
    color: colors.textMuted,
    fontStyle: 'italic'
  },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginTop: spacing.md
  },
  btnPrimary: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderRadius: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm
  },
  btnPrimaryText: {
    color: "#fff",
    fontWeight: "bold",
    fontSize: typography.body
  },
  btnOutline: {
    borderWidth: 1,
    borderColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center'
  },
  btnOutlineText: {
    color: colors.primary,
    fontWeight: "bold"
  },
  statusText: {
    color: colors.primary,
    fontWeight: '600',
    fontSize: typography.small
  },
  autoConnectRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  autoBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    borderWidth: 1.5,
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
    backgroundColor: colors.bgAlt,
  },
  autoBtnText: {
    fontSize: typography.small,
    fontWeight: '700',
  },
  connStatus: {
    borderRadius: radius.sm,
    padding: spacing.sm,
    marginBottom: spacing.sm,
    alignItems: 'center',
  },
  testBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    backgroundColor: colors.bgAlt,
    borderRadius: radius.sm,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    marginBottom: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
  },
  testBtnText: {
    color: colors.text,
    fontSize: typography.small,
    fontWeight: '600',
  },
  pairBox: {
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    backgroundColor: colors.primarySoft,
    gap: spacing.xs,
  },
  pairHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginBottom: spacing.xs,
  },
  pairTitle: {
    fontSize: typography.subtitle,
    fontWeight: '700',
    color: colors.text,
  },
  pairIdentity: {
    gap: spacing.xs,
  },
  copyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  pairCodeText: {
    fontSize: typography.body,
    color: colors.textMuted,
  },
  pairCodeValue: {
    fontSize: typography.subtitle,
    fontWeight: '800',
    color: colors.primary,
    letterSpacing: 2,
  },
  pairDeviceText: {
    fontSize: typography.caption,
    color: colors.textMuted,
  },
  pairDeviceValue: {
    fontWeight: '700',
    color: colors.text,
  },
});
