import { useEffect, useState } from "react";
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView, ActivityIndicator, Platform } from "react-native";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography, radius, rf, rs } from "@/theme/tokens";
import { apiGet, apiPost, platformAlert } from "@/services/apiClient";
import { Save, UserCog, Network, ServerCrash, RefreshCcw, Trash2, Wifi, Search, Link2, Copy } from "lucide-react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { updateServiceConfig, loadStoredApiToken, setStoredDeviceId } from "@/services/config";
import { getDeviceByPairingCode, getRemoteUrlForDevice } from "@/services/deviceRegistry";
import { checkHealth, exchangeCodeForToken, discoverBackend } from "@/services/discovery";
import { useUserMode } from "@/context/UserModeContext";
import { useAuth } from "@/context/AuthContext";
import { updateProfile } from "@/services/supabaseAuth";
import { useToast } from "@/components/ui/ToastProvider";
import { useLiveData } from "@/context/LiveDataContext";


export function SettingsScreen() {
  const { setUserMode, isExpert, isResearcher } = useUserMode();
  const { reconnect: liveReconnect } = useLiveData();
  const { session } = useAuth();
  const prof = session?.profile || {};
  const { showToast } = useToast();
  // Klinik/profil bilgisi artık KAYIT (login) formunda toplanır (Supabase user_metadata) → burada salt-okunur gösterilir.
  const [settings, setSettings] = useState({
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

  // Profil düzenleme (Supabase user_metadata → updateProfile). E-posta değiştirilemez.
  const [editP, setEditP] = useState(false);
  const [savingP, setSavingP] = useState(false);
  const [pForm, setPForm] = useState({
    first_name: "", last_name: "", title: "", phone: "",
    clinic_name: "", clinic_phone: "", city: "", district: "", address: ""
  });
  const startEditProfile = () => {
    setPForm({
      first_name: prof.first_name || "", last_name: prof.last_name || "",
      title: prof.title || "", phone: prof.phone || "",
      clinic_name: prof.clinic_name || "", clinic_phone: prof.clinic_phone || "",
      city: prof.city || "", district: prof.district || "", address: prof.address || ""
    });
    setEditP(true);
  };
  const saveProfile = async () => {
    if (!pForm.first_name.trim() || !pForm.last_name.trim()) {
      showToast("Ad ve soyad boş olamaz.", "error");
      return;
    }
    setSavingP(true);
    const meta = {
      ...pForm,
      first_name: pForm.first_name.trim(),
      last_name: pForm.last_name.trim(),
      full_name: `${pForm.first_name.trim()} ${pForm.last_name.trim()}`.trim(),
    };
    const r = await updateProfile(meta);
    setSavingP(false);
    if (r.ok) { showToast("Profil güncellendi.", "success"); setEditP(false); }
    else showToast(r.error || "Profil güncellenemedi.", "error");
  };

  useEffect(() => {
    let mounted = true;
    const fetchSettings = async () => {
      await loadStoredApiToken();
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

  /** Bağlantıyı test eder. Web: app KENDİ origin'ine bağlıdır → onu test et, base'i ASLA repoint etme
   *  (server_ip alanı native içindir; web'de repoint = çalışan bağlantıyı kırar). Native: girilen adresi test+kaydet. */
  const handleTestConnection = async () => {
    setSearching(true);
    setConnectionStatus("idle");
    try {
      if (Platform.OS === "web") {
        const origin = (typeof window !== "undefined" && window.location?.origin) ? window.location.origin : "";
        const controller = new AbortController();
        setTimeout(() => controller.abort(), 5000);
        const res = await fetch(`${origin}/api/health`, { signal: controller.signal });
        setConnectionStatus(res.ok ? "ok" : "fail");
        showToast(res.ok ? "✅ Sunucuya bağlısınız." : "❌ Sunucuya ulaşılamadı.", res.ok ? "success" : "error");
      } else {
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
      }
    } catch {
      setConnectionStatus("fail");
      showToast("❌ Bağlantı zaman aşımına uğradı.", "error");
    }
    setSearching(false);
  };

  /** Otomatik ağ tarama (yalnız NATIVE). Web: tarayıcı LAN cross-origin fetch'i engeller + sunucu
   *  zaten bu sayfanın origin'i → tarama anlamsız/yanlış-negatif. Web'de origin'i doğrula, repoint YOK. */
  const handleAutoSearch = async () => {
    setSearching(true);
    setConnectionStatus("idle");
    if (Platform.OS === "web") {
      try {
        const origin = (typeof window !== "undefined" && window.location?.origin) ? window.location.origin : "";
        const ctrl = new AbortController();
        setTimeout(() => ctrl.abort(), 5000);
        const res = await fetch(`${origin}/api/health`, { signal: ctrl.signal });
        setConnectionStatus(res.ok ? "ok" : "fail");
        showToast(res.ok ? "✅ Sunucuya bağlısınız (bu sayfanın sunucusu)." : "❌ Sunucuya ulaşılamadı.", res.ok ? "success" : "error");
      } catch { setConnectionStatus("fail"); showToast("❌ Sunucuya ulaşılamadı.", "error"); }
      setSearching(false);
      return;
    }
    // NATIVE: app'in GERÇEK keşif merdivenini kullan (discovery.ts: kayıtlı-adres → mDNS → remote →
    // TAM /24 subnet 1-254). Eski sabit-liste [100,1,101,2,102,110,50,200] backend'in DHCP IP'sini
    // (ör. .37) KAÇIRIYORDU → "bağlı olmasına rağmen bulunamadı". discoverBackend zaten config'i uygular +
    // PEMF kimliğini doğrular; bağlıyken kayıtlı adresi ilk sırada onaylar (yanlış-negatif biter).
    showToast("🔍 Ağ taranıyor...", "info");
    try {
      const found = await discoverBackend();
      if (found) {
        const ipOnly = found.address.replace(/^https?:\/\//, "").replace(/:\d+$/, "");
        setSettings(prev => ({ ...prev, server_ip: ipOnly }));
        setConnectionStatus("ok");
        showToast(`✅ PEMF cihazı bulundu: ${ipOnly}`, "success");
        liveReconnect(); // doğrulanmış/yeni adrese WS'i bağla
      } else {
        setConnectionStatus("fail");
        showToast("⚠️ Ağda PEMF cihazı bulunamadı. Cihazla aynı WiFi'de olduğunuzdan emin olun ya da IP'yi elle girin.", "info");
      }
    } catch {
      setConnectionStatus("fail");
      showToast("⚠️ Tarama başarısız. Cihaz IP'sini elle girin.", "info");
    }
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
      // GÜVENLİK: resolvedDeviceId'yi de geç (auto-yolla AYNI): Cloudflare tünel-URL'i başka bir
      // kliniğin cihazına yeniden atanmış / Supabase satırı zehirlenmişse /api/health deviceId
      // uyuşmazlığında BAĞLANMA — yanlış hastaya/cihaza komut gönderme riski.
      const alive = await checkHealth(tunnelUrl, resolvedDeviceId);
      if (!alive) {
        setConnectionStatus("fail");
        showToast("Cihaz bulundu ama şu an çevrimdışı ya da kimlik doğrulanamadı.", "error");
        return;
      }

      // 3) Canlı → kaydet + bağlan.
      if (!updateServiceConfig(tunnelUrl)) {  // #63: geçersiz adres → ayarı bozma
        setConnectionStatus("fail");
        showToast("Geçersiz cihaz adresi biçimi.", "error");
        return;
      }
      // Kod-yolu (hiç LAN'a girmemiş telefon): 6-haneli kodu cihaz token'ıyla takas et →
      // uzaktan HTTP + WS auth çalışsın. Yoksa "bağlandı ✓" ama tüm veri 401 olurdu (audit P0).
      if (input.length <= 8) { await exchangeCodeForToken(tunnelUrl, input); }
      await setStoredDeviceId(resolvedDeviceId);
      await AsyncStorage.setItem("@pemf_server_address", tunnelUrl).catch(() => {});
      setSettings(prev => ({ ...prev, server_ip: tunnelUrl as string }));
      // #87: yeni serviceConfig ile WS'i HEMEN yeniden bağla → önceki cihazın telemetrisi
      // gösterilmeye devam etmesin (yanlış-cihaz görüntüsü). reconnect() connectionEpoch bump eder.
      liveReconnect();
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
      // KRİTİK: web'de app KENDİ origin'ine bağlıdır → base'i repoint ETME. Aksi halde bir sonraki
      // apiPost("/settings/") yanlış/boş adrese gider → "Kaydetme hatası" + tüm bağlantı kopar (yeşil kalır).
      if (Platform.OS !== "web") updateServiceConfig(settings.server_ip);
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
        <Text style={styles.label}>Şu anki mod: {isExpert ? 'Veteriner Hekim' : isResearcher ? 'Araştırma Modu' : 'Evcil Hayvan Sahibi'}</Text>
        <TouchableOpacity style={[styles.btnOutline, { marginTop: spacing.md }]} onPress={() => setUserMode(null)}>
          <Text style={styles.btnOutlineText}>Farklı Bir Profile Geçiş Yap</Text>
        </TouchableOpacity>
      </Card>

      {/* Hesap/Klinik bilgileri — kayıt (login) formunda girildi; buradan düzenlenebilir (Supabase user_metadata). */}
      <Card style={styles.card}>
        <View style={styles.cardHeaderRow}>
          <View style={styles.cardHeader}>
            <UserCog color={colors.primary} size={20} />
            <Text style={styles.cardTitle}>Hesap Bilgileri</Text>
          </View>
          {!editP ? (
            <TouchableOpacity onPress={startEditProfile} accessibilityLabel="Profili düzenle">
              <Text style={styles.editLink}>Düzenle</Text>
            </TouchableOpacity>
          ) : null}
        </View>

        {editP ? (
          <>
            <View style={styles.row2}>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Ad</Text>
                <TextInput style={styles.input} value={pForm.first_name} onChangeText={t => setPForm({ ...pForm, first_name: t })} placeholder="Ad" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Soyad</Text>
                <TextInput style={styles.input} value={pForm.last_name} onChangeText={t => setPForm({ ...pForm, last_name: t })} placeholder="Soyad" />
              </View>
            </View>
            <Text style={styles.label}>Ünvan</Text>
            <TextInput style={styles.input} value={pForm.title} onChangeText={t => setPForm({ ...pForm, title: t })} placeholder="Örn. Vet. Hekim" />
            <Text style={styles.label}>Telefon</Text>
            <TextInput style={styles.input} value={pForm.phone} onChangeText={t => setPForm({ ...pForm, phone: t })} placeholder="Cep telefonu" keyboardType="phone-pad" />
            <Text style={styles.label}>Klinik / Muayenehane</Text>
            <TextInput style={styles.input} value={pForm.clinic_name} onChangeText={t => setPForm({ ...pForm, clinic_name: t })} placeholder="Klinik adı" />
            <View style={styles.row2}>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Şehir (İl)</Text>
                <TextInput style={styles.input} value={pForm.city} onChangeText={t => setPForm({ ...pForm, city: t })} placeholder="Şehir" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>İlçe</Text>
                <TextInput style={styles.input} value={pForm.district} onChangeText={t => setPForm({ ...pForm, district: t })} placeholder="İlçe" />
              </View>
            </View>
            <Text style={styles.label}>Adres</Text>
            <TextInput style={styles.input} value={pForm.address} onChangeText={t => setPForm({ ...pForm, address: t })} placeholder="Açık adres" />
            <Text style={styles.label}>Klinik Acil Telefon</Text>
            <TextInput style={styles.input} value={pForm.clinic_phone} onChangeText={t => setPForm({ ...pForm, clinic_phone: t })} placeholder="Klinik acil telefon" keyboardType="phone-pad" />
            <View style={styles.actions}>
              <TouchableOpacity style={styles.btnPrimary} onPress={saveProfile} disabled={savingP}>
                <Save color="#fff" size={16} />
                <Text style={styles.btnPrimaryText}>{savingP ? "Kaydediliyor..." : "Kaydet"}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.btnOutline, { marginLeft: spacing.md }]} onPress={() => setEditP(false)} disabled={savingP}>
                <Text style={styles.btnOutlineText}>İptal</Text>
              </TouchableOpacity>
            </View>
          </>
        ) : (
          <>
            <Info label="Ad Soyad" value={prof.full_name || [prof.first_name, prof.last_name].filter(Boolean).join(" ")} />
            {prof.title ? <Info label="Ünvan" value={prof.title} /> : null}
            <Info label="E-posta" value={session?.email} />
            {prof.clinic_name ? <Info label="Klinik / Muayenehane" value={prof.clinic_name} /> : null}
            {(prof.city || prof.district) ? <Info label="Şehir / İlçe" value={[prof.city, prof.district].filter(Boolean).join(" / ")} /> : null}
            {prof.address ? <Info label="Adres" value={prof.address} /> : null}
            {prof.phone ? <Info label="Telefon" value={prof.phone} /> : null}
            {prof.clinic_phone ? <Info label="Klinik Acil Telefon" value={prof.clinic_phone} /> : null}
            <Text style={styles.mutedNote}>E-posta hesap kimliğidir, değiştirilemez. Diğer bilgileri "Düzenle" ile güncelleyebilirsin.</Text>
          </>
        )}
      </Card>

      {/* Bağlantı/eşleştirme TÜM profillerde görünür: AI modelleri backend bağlantısı olmadan çalışmaz →
          Evcil Hayvan Sahibi + Araştırma + Veteriner hepsi cihaza bağlanabilmeli (eskiden yalnız vet+araştırma). */}
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

            {/* Manuel IP yedeği YALNIZ Veteriner (uzman) modunda — otomatik+eşleştirme çoğu durumu kapsar;
                normal kullanıcıyı karmaşadan uzak tut, kısıtlı-ağ yedeği uzmanda dursun. */}
            {isExpert && (
              <>
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
              </>
            )}
          </Card>

          <View style={styles.actions}>
            <TouchableOpacity style={styles.btnPrimary} onPress={handleSave} disabled={loading}>
              <Save color="#fff" size={16} />
              <Text style={styles.btnPrimaryText}>{loading ? "Kaydediliyor..." : "Ayarları Kaydet"}</Text>
            </TouchableOpacity>
            {saveStatus ? <Text style={styles.statusText}>{saveStatus}</Text> : null}
          </View>
        </>

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
            </View>
          </Card>
        </View>
      )}

    </ScrollView>
  );
}

/** Salt-okunur profil satırı (etiket + değer). */
function Info({ label, value }: { label: string; value?: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue} selectable numberOfLines={2}>{value || "—"}</Text>
    </View>
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
  cardHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between'
  },
  editLink: {
    color: colors.primary,
    fontWeight: '800',
    fontSize: typography.small
  },
  row2: {
    flexDirection: 'row',
    gap: spacing.md
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border
  },
  infoLabel: {
    fontSize: typography.small,
    fontWeight: '600',
    color: colors.textMuted
  },
  infoValue: {
    flex: 1,
    fontSize: typography.body,
    fontWeight: '700',
    color: colors.text,
    textAlign: 'right'
  },
  mutedNote: {
    fontSize: typography.caption,
    color: colors.textMuted,
    marginTop: spacing.sm
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
