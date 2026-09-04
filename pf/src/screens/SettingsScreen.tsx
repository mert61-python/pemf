// Author: mertaygn, cglrgrkn
import { useCallback, useEffect, useRef, useState } from "react";
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ActivityIndicator, Platform } from "react-native";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography, radius, rf, rs, layoutMax } from "@/theme/tokens";
import { apiGet, apiPost, platformAlert, platformConfirm } from "@/services/apiClient";
import { Save, UserCog, Network, ServerCrash, RefreshCcw, Trash2, Wifi, Search, Link2, Copy, Building2 } from "lucide-react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { updateServiceConfig, loadStoredApiToken, setStoredDeviceId } from "@/services/config";
import { checkHealth, discoverBackend } from "@/services/discovery";
import { cihazaBaglan, eslesmeMesaji } from "@/services/pairing";
import { useUserMode } from "@/context/UserModeContext";
import { useAuth } from "@/context/AuthContext";
import { updateProfile } from "@/services/supabaseAuth";
import { useToast } from "@/components/ui/ToastProvider";
import { BackupPassphraseDialog, type ParolaKipi } from "@/components/domain/BackupPassphraseDialog";
import { useLiveData } from "@/context/LiveDataContext";
import { useTeardownGuard } from "@/hooks/useTeardownGuard";
import { FIRMA } from "@/config/firma";
// Denetim 2026-08-28 #02: bulut kayit durumunun operatore gorunen karsiligi.
// Saf fonksiyonlar AYRI modulde: testleri tum ekran bagimlilik grafigini yuklemeden kosar.
import { bulutKayitRozeti, eslestirmeKoduUzaktanGecerliMi } from "@/services/bulutKayit";


export function SettingsScreen() {
  const { setUserMode, isExpert, isResearcher } = useUserMode();
  const { reconnect: liveReconnect } = useLiveData();
  const guardTeardown = useTeardownGuard();
  // "Ayarlar kaydedildi" mesajını 3sn sonra silen zamanlayıcı — unmount'ta temizlenmesi için ref'te.
  const saveStatusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (saveStatusTimerRef.current) clearTimeout(saveStatusTimerRef.current); }, []);
  const { session } = useAuth();
  const prof = session?.profile || {};
  const { showToast } = useToast();

  // ── CİHAZ TAŞIMA (2026-08-08) — şifreli dışa/içe aktarma ────────────────────────────────
  // Yalnız web (masaüstü client) yolu: veritabanı O makinede durur, taşıma orada yapılır.
  // Mobilde bölüm hiç gösterilmez → yeni bir yerel-dosya bağımlılığı (picker/fs) EKLENMEZ.
  const [tasimaMesgul, setTasimaMesgul] = useState<"" | "export" | "import">("");

  // ── VERİ SAKLAMA / PII MASKELEME (2026-08-09 denetimi, Tier 1) ────────────────────────
  // Seans kayıtlarındaki hasta/operatör adı ve notlar, süre dolunca `[REDACTED]` ile GERİ
  // DÖNÜŞSÜZ maskeleniyordu ve bu tamamen SESSİZ oluyordu. Süre yalnız `PEMF_RETAIN_PII_DAYS`
  // ortam değişkeniyle ayarlanabiliyordu — hiçbir veteriner bunu bilmez. Klinik 366. günde
  // hasta adı yerine `[REDACTED]` görüyor ve sebebini hiçbir yerde bulamıyordu.
  interface RetentionDurum {
    days: number; configured: boolean; acknowledged: boolean; pending: number; default: number;
  }
  const [retention, setRetention] = useState<RetentionDurum | null>(null);
  const [retMesgul, setRetMesgul] = useState(false);

  const retentionYukle = useCallback(async () => {
    const r = await apiGet<RetentionDurum | null>("/settings/retention", null, { silent: true });
    if (r) setRetention(r);
  }, []);
  useEffect(() => { void retentionYukle(); }, [retentionYukle]);

  const retentionKaydet = useCallback(async (govde: { days?: number; acknowledge?: boolean }) => {
    setRetMesgul(true);
    const r = await apiPost<{ status?: string } | null>("/settings/retention", govde, null);
    setRetMesgul(false);
    if (r?.status === "success") await retentionYukle();
  }, [retentionYukle]);

  // ⚠️ DENETİM 2026-08-09 (Tier 1): `window.prompt` KALDIRILDI. Parolayı düz metin gösteriyor,
  // TEK KEZ soruyor (yazım hatası yedeği kalıcı olarak açılamaz kılar — ve bu ancak yedeğe
  // ihtiyaç duyulan gün anlaşılır) ve native'de hiç çalışmıyordu. Yerine iki-kez-soran,
  // asgari uzunluğu gösteren bir diyalog: `BackupPassphraseDialog`.
  const [parolaKipi, setParolaKipi] = useState<ParolaKipi | null>(null);
  const parolaCozucu = useRef<((p: string | null) => void) | null>(null);

  /** Diyaloğu aç ve parolayı bekle. Vazgeçilirse null. */
  const parolaSor = useCallback((kip: ParolaKipi): Promise<string | null> => {
    setParolaKipi(kip);
    return new Promise<string | null>((resolve) => { parolaCozucu.current = resolve; });
  }, []);

  const parolaKapat = useCallback((deger: string | null) => {
    setParolaKipi(null);
    const c = parolaCozucu.current;
    parolaCozucu.current = null;
    c?.(deger);
  }, []);

  const disaAktar = useCallback(async () => {
    const parola = await parolaSor("olustur");
    if (!parola) return;
    setTasimaMesgul("export");
    const res = await apiPost<{ status?: string; filename?: string; data_b64?: string;
                               counts?: Record<string, number> } | null>(
      "/data/export", { passphrase: parola }, null);
    setTasimaMesgul("");
    if (!res?.data_b64) return;                       // hata mesajını apiPost gösterdi
    try {
      // base64 → Blob → indir. Dosya diske YALNIZ kullanıcının seçtiği yere gider.
      const ham = atob(res.data_b64);
      const buf = new Uint8Array(ham.length);
      for (let i = 0; i < ham.length; i++) buf[i] = ham.charCodeAt(i);
      const url = URL.createObjectURL(new Blob([buf], { type: "application/octet-stream" }));
      const a = document.createElement("a");
      a.href = url; a.download = res.filename || "pemf-vet-yedek.pemfbak";
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      const c = res.counts || {};
      showToast(`Yedek oluşturuldu: ${c.patients ?? 0} hasta, ${c.treatment_sessions ?? 0} seans, ${c.ai_analyses ?? 0} analiz.`, "success");
    } catch {
      showToast("Yedek dosyası kaydedilemedi.", "error");
    }
  }, [showToast, parolaSor]);

  const iceAktar = useCallback(async () => {
    const inp = document.createElement("input");
    inp.type = "file";
    inp.accept = ".pemfbak,application/octet-stream";
    inp.onchange = async () => {
      const f = inp.files?.[0];
      if (!f) return;
      const parola = await parolaSor("gir");
      if (!parola) return;
      if (!(await platformConfirm(
        "Yedekten geri yükle",
        "Bu cihazda kayıt varsa mevcut SEANS ve AI ANALİZ geçmişi SİLİNİP yedektekiyle değiştirilecek.\n\nDevam edilsin mi?",
        "Geri yükle"))) return;
      setTasimaMesgul("import");
      const buf = new Uint8Array(await f.arrayBuffer());
      let s = "";
      for (let i = 0; i < buf.length; i++) s += String.fromCharCode(buf[i]);
      const res = await apiPost<{ status?: string; counts?: Record<string, number> } | null>(
        "/data/import", { passphrase: parola, blob_b64: btoa(s), confirm: "REPLACE_ALL" }, null);
      setTasimaMesgul("");
      if (!res?.counts) return;
      const c = res.counts;
      // Denetim 2026-08-28 #05: backend "eklendi / zaten vardı / BAŞARISIZ" ayrımını BİLEREK
      // döndürüyor ama ekrana hiç ulaşmıyordu — "0 hasta" tek başına "hepsi zaten vardı" mı
      // yoksa "hepsi başarısız" mı olduğunu söylemez; tıbbi kayıt taşımada bu ayrım kritik.
      const zatenVardi = c.patient_db_zaten_vardi ?? 0;
      const basarisiz = c.patient_db_basarisiz ?? 0;
      const ek = [
        zatenVardi > 0 ? `${zatenVardi} hasta zaten vardı` : "",
        basarisiz > 0 ? `${basarisiz} hasta AKTARILAMADI` : "",
      ].filter(Boolean).join(", ");
      showToast(
        `Geri yüklendi: ${c.patients ?? 0} hasta, ${c.treatment_sessions ?? 0} seans, ${c.ai_analyses ?? 0} analiz.`
        + (ek ? ` (${ek})` : ""),
        basarisiz > 0 ? "error" : "success",
      );
    };
    inp.click();
  }, [showToast, parolaSor]);
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
  // Bulut cihaz-kaydının son yayınlanan durumu (/api/health → cloudRegistry).
  // Denetim 2026-08-28 #02: backend bu alanı tam da arızayı göstermek için yayınlıyordu,
  // ama onu çizen hiçbir ekran yoktu → cihaz 13 gündür buluta yazamazken ekran susuyordu.
  // ⚠️ Bu bir ANLIK GÖRÜNTÜDÜR: aşağıdaki health çağrısı useEffect(..., []) içinde tek kez
  // koşar (polling yok), yani ekranın açıldığı andaki durumu gösterir.
  const [cloudRegistry, setCloudRegistry] = useState<string>("unknown");
  // Uzak cihaza bağlanmak için girilen kod/kimlik.
  const [remoteInput, setRemoteInput] = useState("");
  const [connecting, setConnecting] = useState(false);

  // Profil düzenleme (Supabase user_metadata → updateProfile). E-posta değiştirilemez.
  const [editP, setEditP] = useState(false);
  const [savingP, setSavingP] = useState(false);
  const [pForm, setPForm] = useState({
    first_name: "", last_name: "", title: "", phone: "",
    clinic_name: "", clinic_phone: "", city: "", district: "", address: "",
    institution: "", department: "", academic_title: ""
  });
  const startEditProfile = () => {
    // ⚠️ TÜM alanlar yüklenir (yalnız aktif profile ait olanlar GÖSTERİLİR). Yüklenmezse
    // kaydederken diğer profilin bilgileri BOŞ gider ve silinir — profil her açılışta
    // değiştiği için bu, veteriner bilgisini araştırma modunda kaydedince kaybettirirdi.
    setPForm({
      first_name: prof.first_name || "", last_name: prof.last_name || "",
      title: prof.title || "", phone: prof.phone || "",
      clinic_name: prof.clinic_name || "", clinic_phone: prof.clinic_phone || "",
      city: prof.city || "", district: prof.district || "", address: prof.address || "",
      institution: prof.institution || "", department: prof.department || "",
      academic_title: prof.academic_title || ""
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
        setCloudRegistry(String(health.cloudRegistry ?? "unknown"));
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
        // GÜVENLİK (#24): eskiden yalnız `res.ok` kontrol ediliyordu → /api/health'e 200 dönen
        // HERHANGİ bir host (router paneli, NAS, saldırganın sunucusu) kabul ediliyor, ardından
        // updateServiceConfig ile taban oraya çevriliyordu; sonraki her istek cihaz X-API-Key'ini
        // (https ise Supabase JWT'sini de) o host'a yolluyordu. discovery.checkHealth zaten
        // `service === "PEMF-Vet"` + device_id kontrolü yapıyor — aynı kapıyı burada da kullan.
        const ok = await checkHealth(addr, null);
        if (ok) {
          if (!updateServiceConfig(addr)) {   // #63 doğrulaması: geçersiz biçimde ayarı BOZMA
            setConnectionStatus("fail");
            showToast("❌ Geçersiz adres biçimi.", "error");
            return;
          }
          await AsyncStorage.setItem("@pemf_server_address", addr).catch(() => {});
          // #5: REST tabanı değişti ama WS eski cihaza bağlı kalıyordu → komutlar YENİ cihaza,
          // telemetri/"CANLI" rozeti ESKİ cihazdan geliyordu (iki cihazlı klinikte yanlış hasta
          // verisi okuma riski). Diğer iki yol (otomatik arama, uzaktan bağlan) zaten reconnect
          // ediyordu; bu yol atlanmıştı.
          liveReconnect();
          setConnectionStatus("ok");
          showToast("✅ Bağlantı başarılı! Adres kaydedildi.", "success");
        } else {
          setConnectionStatus("fail");
          showToast("❌ Bu adreste bir PEMF cihazı bulunamadı.", "error");
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
      // ⚠️ Bağlantı kararı `services/pairing` içinde, TEK YERDE verilir (çözümleme sebebi →
      // health + kimlik doğrulama → token takası → kalıcı yazma). Buradaki iş yalnız arayüz.
      // Karşılama akışı (`DevicePairingGuide`) da AYNI servisi çağırır; iki kopya tutulsaydı
      // güvenlik değişmezlerinden biri sessizce eskiyebilirdi.
      const sonuc = await cihazaBaglan(input);
      if (sonuc.durum === "ok") {
        setSettings(prev => ({ ...prev, server_ip: sonuc.url }));
        // Yeni serviceConfig ile WS'i HEMEN yeniden bağla → önceki cihazın telemetrisi
        // gösterilmeye devam etmesin (yanlış-cihaz görüntüsü).
        liveReconnect();
        setConnectionStatus("ok");
        showToast(eslesmeMesaji(sonuc), "success");
      } else {
        setConnectionStatus("fail");
        showToast(eslesmeMesaji(sonuc), "error");
      }
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
      // #72: adres eskiden DOĞRULANMADAN kaydediliyor ve updateServiceConfig'in `false` dönüşü
      // yok sayılıyordu → boş/bozuk bir server_ip kalıcı hâle gelip sonraki açılışta keşfi
      // bozabiliyordu. Yalnız GEÇERLİ bir adres kalıcılaştırılır; geçersizse mevcut ayar korunur.
      const addr = (settings.server_ip || "").trim();
      if (addr) {
        // KRİTİK: web'de app KENDİ origin'ine bağlıdır → base'i repoint ETME. Aksi halde bir sonraki
        // apiPost("/settings/") yanlış/boş adrese gider → "Kaydetme hatası" + tüm bağlantı kopar (yeşil kalır).
        const applied = Platform.OS === "web" ? true : updateServiceConfig(addr);
        if (!applied) {
          setLoading(false);
          setSaveStatus("Geçersiz sunucu adresi — kaydedilmedi.");
          return;
        }
        // Canonical anahtar @pemf_server_address (discovery + ilk-yükleme bunu okur) + geri-uyum için ip.
        await AsyncStorage.setItem("@pemf_server_address", addr);
        await AsyncStorage.setItem("@pemf_server_ip", addr);
        if (Platform.OS !== "web") liveReconnect(); // #5 ile aynı sebep: WS de yeni adrese geçsin
      }
    } catch(e) {}
    const result = await apiPost<any>("/settings/", settings, { status: "error" });
    setLoading(false);
    if (result.status === "success") {
      setSaveStatus("Ayarlar başarıyla kaydedildi.");
      // #124: bu zamanlayıcı takip edilmiyordu → ekran 3sn dolmadan kapatılırsa unmount sonrası
      // setState (React uyarısı + boşa iş). Ref'te tut, unmount'ta temizle.
      if (saveStatusTimerRef.current) clearTimeout(saveStatusTimerRef.current);
      saveStatusTimerRef.current = setTimeout(() => setSaveStatus(""), 3000);
    } else {
      setSaveStatus("Kaydetme hatası.");
    }
  };

  return (
    <View style={styles.container}>
  {/* [S4 adım 3] İç dikey ScrollView KALDIRILDI: kabuk (AppShell) zaten tek kaydırıcı ve
  keyboardShouldPersistTaps='handled' taşıyor. İç ScrollView'ın yükseklik sınırı
  olmadığı için kendi kaydırmasını hiç üretmiyordu; ama klavye açıkken dokunuşu
  yutup 'Kaydet/Bağlan' düğmelerini İKİ dokunuş gerektiriyordu. */}
      <Text style={styles.headerTitle}>Sistem Ayarları</Text>
      <Text style={styles.intro}>Uygulama tercihleri ve cihaz bağlantı ayarları.</Text>

      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <UserCog color={colors.primary} size={20} />
          <Text style={styles.cardTitle}>Profil Ayarları</Text>
        </View>
        <Text style={styles.label}>Şu anki mod: {isExpert ? 'Veteriner Hekim' : isResearcher ? 'Araştırma Modu' : 'Evcil Hayvan Sahibi'}</Text>
        {/* HASTA GÜVENLİĞİ: profil sıfırlama MainRouter'ı söküp WelcomeScreen'e düşürür →
            ACİL DURDUR ve çevrimdışı uyarısı ekrandan kaybolur. Seans sürerken önce durdur. */}
        <TouchableOpacity
          style={[styles.btnOutline, { marginTop: spacing.md }]}
          onPress={async () => { if (await guardTeardown("Profil değiştirmek")) setUserMode(null); }}
          accessibilityRole="button"
        >
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
            {/* PROFİLE ÖZEL ALANLAR (2026-08-07): klinik bilgisi yalnız veterinerde, kurum
                bilgisi yalnız araştırmada sorulur. Ev sahibinde ikisi de sorulmaz — evcil
                hayvan sahibinden klinik adı istemek anlamsızdı. */}
            {isExpert && (
              <>
                <Text style={styles.label}>Klinik / Muayenehane</Text>
                <TextInput style={styles.input} value={pForm.clinic_name} onChangeText={t => setPForm({ ...pForm, clinic_name: t })} placeholder="Klinik adı" />
              </>
            )}
            {isResearcher && (
              <>
                <Text style={styles.label}>Üniversite / Kurum</Text>
                <TextInput style={styles.input} value={pForm.institution} onChangeText={t => setPForm({ ...pForm, institution: t })} placeholder="Üniversite / enstitü / kurum" />
                <Text style={styles.label}>Bölüm / Anabilim Dalı</Text>
                <TextInput style={styles.input} value={pForm.department} onChangeText={t => setPForm({ ...pForm, department: t })} placeholder="Bölüm" />
                <Text style={styles.label}>Akademik Ünvan</Text>
                <TextInput style={styles.input} value={pForm.academic_title} onChangeText={t => setPForm({ ...pForm, academic_title: t })} placeholder="Örn. Dr. Öğr. Üyesi (opsiyonel)" />
              </>
            )}
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
            {isExpert && (
              <>
                <Text style={styles.label}>Klinik Acil Telefon</Text>
                <TextInput style={styles.input} value={pForm.clinic_phone} onChangeText={t => setPForm({ ...pForm, clinic_phone: t })} placeholder="Klinik acil telefon" keyboardType="phone-pad" />
              </>
            )}
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
            {/* PROFİLE ÖZEL (2026-08-07): ev sahibine klinik/kurum bilgisi GÖSTERİLMEZ.
                Veri silinmez, yalnız o profille ilgisi olmadığı için gizlenir. */}
            {isExpert && prof.clinic_name ? <Info label="Klinik / Muayenehane" value={prof.clinic_name} /> : null}
            {isResearcher && prof.institution ? <Info label="Üniversite / Kurum" value={prof.institution} /> : null}
            {isResearcher && prof.department ? <Info label="Bölüm / Anabilim Dalı" value={prof.department} /> : null}
            {isResearcher && prof.academic_title ? <Info label="Akademik Ünvan" value={prof.academic_title} /> : null}
            {(prof.city || prof.district) ? <Info label="Şehir / İlçe" value={[prof.city, prof.district].filter(Boolean).join(" / ")} /> : null}
            {prof.address ? <Info label="Adres" value={prof.address} /> : null}
            {prof.phone ? <Info label="Telefon" value={prof.phone} /> : null}
            {isExpert && prof.clinic_phone ? <Info label="Klinik Acil Telefon" value={prof.clinic_phone} /> : null}
            <Text style={styles.mutedNote}>{'E-posta hesap kimliğidir, değiştirilemez. Diğer bilgileri "Düzenle" ile güncelleyebilirsin.'}</Text>
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

              {/* Denetim #02: bulut kaydı bozuksa KODDAN ÖNCE söyle. Eskiden kod koşulsuz
                  "bu cihazın kodu" diye sunuluyordu; oysa buluta gitmediği için uzaktan
                  bağlanmakta işe yaramıyordu ve hiçbir ekran bunu söylemiyordu. */}
              {bulutKayitRozeti(cloudRegistry) ? (
                <Text
                  style={
                    bulutKayitRozeti(cloudRegistry)!.seviye === "hata"
                      ? styles.bulutKayitHata
                      : styles.bulutKayitUyari
                  }
                >
                  {bulutKayitRozeti(cloudRegistry)!.seviye === "hata" ? "⛔ " : "⚠️ "}
                  {bulutKayitRozeti(cloudRegistry)!.metin}
                </Text>
              ) : null}

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
                        {!eslestirmeKoduUzaktanGecerliMi(cloudRegistry) ? (
                          <Text style={styles.bulutKayitHata}> (uzaktan geçersiz)</Text>
                        ) : null}
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
                normal kullanıcıyı karmaşadan uzak tut, kısıtlı-ağ yedeği uzmanda dursun.
                NOT (2026-08-06): sahip kararıyla araştırma profiline cihaz ROTALARI açıldı
                (config/access.ts) ama SERVİS araçları bilinçli olarak veterinerde bırakıldı —
                bunlar bağlantıyı/donanımı bozabilecek bakım işlemleri, araştırma iş akışının parçası değil. */}
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
                  // HASTA GÜVENLİĞİ: self-test bobinleri sürebilir. Tedavi sürerken çalıştırmak
                  // devam eden protokolü bozar → tek dokunuşla değil, onaylı ve seans-kontrollü.
                  if (!(await guardTeardown("Donanım self-test çalıştırmak"))) return;
                  if (!(await platformConfirm(
                    "Donanım Self-Test",
                    "Cihaz kendi kendini test edecek; bu sırada bobinler kısa süre enerjilenebilir. Hayvanın kabinde OLMADIĞINDAN emin olun.",
                    "Testi başlat"
                  ))) return;
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
                  // Yön olarak GÜVENLİ (çıkışı sıfırlar) ama süren bir tedaviyi habersiz keser →
                  // onay iste. Not: burada guardTeardown KULLANILMAZ; bu eylemin kendisi durdurmadır.
                  if (!(await platformConfirm(
                    "Tüm PWM sinyallerini sıfırla",
                    "Tüm bobinlerin çıkışı sıfırlanacak. Devam eden bir seans varsa KESİLİR.",
                    "Sıfırla"
                  ))) return;
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

      {/* ── CİHAZ TAŞIMA (2026-08-08) ────────────────────────────────────────────────────
          Kayıtlar bilerek MAKİNEDE tutuluyor (bulut senkronu YOK: kişisel veri yurt dışına
          çıkmasın, kayıt kliniğin olsun). Bunun tek gerçek dezavantajı cihaz değişimiydi —
          çözümü bulut değil, kliniğin KENDİ kontrolündeki şifreli dosya.
          Yalnız VETERİNER: klinik verisinin tamamını dışarı çıkarır. */}
      {isExpert && Platform.OS === "web" && (
        <Card style={styles.card}>
          <Text style={styles.cardTitle}>Veri Taşıma (Cihaz Değişimi)</Text>
          <Text style={styles.intro}>
            Hasta kayıtları, seans geçmişi ve AI analiz geçmişi tek bir ŞİFRELİ dosyaya aktarılır.
            Yeni bilgisayara aynı parolayla geri yüklenir. Dosya parolasız açılamaz —
            parolayı kaybederseniz yedek kurtarılamaz.
          </Text>

          <TouchableOpacity style={styles.btnOutline} disabled={!!tasimaMesgul} onPress={disaAktar}
            accessibilityRole="button" accessibilityLabel="Klinik verilerini şifreli dosyaya aktar">
            <Text style={styles.btnOutlineText}>
              {tasimaMesgul === "export" ? "Hazırlanıyor…" : "Şifreli Yedek Oluştur"}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity style={[styles.btnOutline, { borderColor: colors.warning }]}
            disabled={!!tasimaMesgul} onPress={iceAktar}
            accessibilityRole="button" accessibilityLabel="Şifreli yedekten geri yükle">
            <Text style={[styles.btnOutlineText, { color: colors.warning }]}>
              {tasimaMesgul === "import" ? "Yükleniyor…" : "Yedekten Geri Yükle"}
            </Text>
          </TouchableOpacity>

          <Text style={[styles.intro, { color: colors.warning }]}>
            Geri yükleme, bu cihazda kayıt varsa mevcut seans ve analiz geçmişini SİLER.
          </Text>
        </Card>
      )}

      {/* VERİ SAKLAMA — geri dönüşsüz maskeleme operatör kararıdır (2026-08-09 denetimi).
          Tıbbi-hukuki saklama süresi ülkeye/kliniğe göre değişir: KVKK silmeyi ister, açılmış
          bir dava dosyası saklamayı. Yazılım bu kararı sessizce almaz. */}
      {isExpert && retention && (
        <Card style={styles.card}>
          <Text style={styles.cardTitle}>Veri Saklama Süresi</Text>
          <Text style={styles.intro}>
            {retention.days > 0
              ? `Seans kayıtlarındaki hasta ve operatör adları ${retention.days} gün sonra kalıcı olarak maskelenir ([REDACTED]). Tedavi verileri (doz, süre, sensör) KALIR.`
              : "Maskeleme KAPALI — hasta ve operatör adları süresiz saklanır."}
          </Text>

          {retention.pending > 0 ? (
            <>
              <Text style={[styles.intro, { color: colors.warning }]}>
                {retention.pending} seans kaydı maskelenmeyi bekliyor. Bu işlem GERİ ALINAMAZ:
                hasta adları kalıcı olarak silinir. Onaylayana kadar hiçbir kayda dokunulmaz.
              </Text>
              <TouchableOpacity style={[styles.btnOutline, { borderColor: colors.warning }]}
                disabled={retMesgul} onPress={() => retentionKaydet({ acknowledge: true })}
                accessibilityRole="button"
                accessibilityLabel="Geri dönüşsüz maskelemeyi onayla ve başlat">
                <Text style={[styles.btnOutlineText, { color: colors.warning }]}>
                  {retMesgul ? "…" : "Anladım, maskelemeyi başlat"}
                </Text>
              </TouchableOpacity>
            </>
          ) : null}

          <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
            {[0, 365, 730, 1825].map((g) => (
              <TouchableOpacity key={g} style={[styles.btnOutline, { flex: 0, paddingHorizontal: spacing.md },
                                                retention.days === g && { borderColor: colors.primary }]}
                disabled={retMesgul} onPress={() => retentionKaydet({ days: g })}
                accessibilityRole="button"
                accessibilityLabel={g === 0 ? "Maskelemeyi kapat" : `Saklama süresi ${g} gün`}>
                <Text style={[styles.btnOutlineText, retention.days === g && { color: colors.primary }]}>
                  {g === 0 ? "Kapalı" : g === 365 ? "1 yıl" : g === 730 ? "2 yıl" : "5 yıl"}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </Card>
      )}

      {/* KÜNYE (2026-08-07): üretici/satıcı kimliği uygulamada da görünür olmalı — tıbbi
          cihaz yazılımında kullanıcı hangi tüzel kişiye ulaşacağını bilmeli (site künyesiyle
          AYNI bilgiler; tek kaynak `FIRMA` sabiti). */}
      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <Building2 color={colors.primary} size={20} />
          <Text style={styles.cardTitle}>Hakkında</Text>
        </View>
        <Text style={styles.label}>{FIRMA.urun}</Text>
        <Text style={styles.kunyeSatir}>{FIRMA.unvan}</Text>
        <Text style={styles.kunyeSatir}>{FIRMA.adres}</Text>
        <Text style={styles.kunyeSatir}>Tel: {FIRMA.tel}  ·  {FIRMA.eposta}</Text>
        <Text style={styles.kunyeSatir}>MERSİS: {FIRMA.mersis}  ·  VKN: {FIRMA.vkn}</Text>
        <Text style={styles.kunyeSatir}>© {FIRMA.yil} {FIRMA.kisaUnvan}</Text>
      </Card>

      {/* Yedek parolası — `window.prompt` yerine (2026-08-09 denetimi): iki kez sorar, asgari
          uzunluğu gösterir, parolayı düz metin sızdırmaz ve native'de de çalışır. */}
      <BackupPassphraseDialog
        visible={parolaKipi !== null}
        kip={parolaKipi ?? "gir"}
        onCancel={() => parolaKapat(null)}
        onSubmit={(p) => parolaKapat(p)}
      />
    </View>
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
    // [S4 adım 3] Alt boşluk TEK yerde: AppShell içerik ScrollView'ı veriyor (mobil rs(160)+güvenli
    // alan / masaüstü rs(84)); ekranın kendi dolgusu üstüne binip ~200 px ölü alan bırakıyordu.
    width: "100%",
    maxWidth: layoutMax.ayar,
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
  // Künye satırları (2026-08-07): küçük, sönük, okunur.
  kunyeSatir: { color: colors.textMuted, fontSize: rf(11), lineHeight: rf(17) },
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
  // Bulut kayit rozeti (denetim #02) — sessiz arizayi gorunur kilar.
  bulutKayitHata: {
    fontSize: typography.caption,
    color: colors.danger,
    marginBottom: spacing.sm,
  },
  bulutKayitUyari: {
    fontSize: typography.caption,
    color: colors.warning,
    marginBottom: spacing.sm,
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
