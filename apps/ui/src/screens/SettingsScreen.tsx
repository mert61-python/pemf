// Author: mertaygn, cglrgrkn
import { useCallback, useEffect, useRef, useState } from "react";
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ActivityIndicator, Platform } from "react-native";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography, radius, rf, rs, layoutMax, touch } from "@/theme/tokens";
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
import { GenisletilebilirMetin } from "@/components/ui/GenisletilebilirMetin";
import { backendBuMakinede } from "@/services/backendKonumu";
import { DilSecimKarti } from "@/components/domain/DilSecimKarti";
import { dilSecimiGorunur } from "@/i18n";
import {
  disaAktarmaAgHatasiMesaji,
  disaAktarmaZamanAsimiMesaji,
  iceAktarmaAgHatasiMesaji,
  iceAktarmaZamanAsimiMesaji,
  VERI_TASIMA_ZAMAN_ASIMI_MS,
} from "@/services/veriTasima";
import { useTranslation } from "react-i18next";


/** S-F2-1.1: denetim izinin UTC ISO zamanını yerel tarih-saate çevirir; okunamazsa ham metin. */
function sonTurZamani(at: string | null | undefined): string {
  if (!at) return "bilinmiyor";
  const t = new Date(at);
  return Number.isNaN(t.getTime()) ? String(at) : t.toLocaleString("tr-TR");
}

export function SettingsScreen() {
  const { t } = useTranslation();
  const { setUserMode, isExpert, isResearcher } = useUserMode();
  // SG.G3 (sahip, 2026-10-13: "araştırma profilinin ayarlar kısmında bunlar da olmalı … veri saklama süresi veri taşıma donanım
  // bakım"): bakım / taşıma / saklama kartları UZMAN profillerde (veteriner VEYA araştırma); Ev Sahibi'nde GİZLİ kalır (KVKK).
  // Profiller herkese açık (sahip kararı) → gerçek erişim genişlemez; uçlar profil bilmez. Taşıma ve saklama CİHAZ GENELİDİR.
  const uzmanProfil = isExpert || isResearcher;
  const { reconnect: liveReconnect, wsConnected } = useLiveData();
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
    // D2.58 (B-3.90): pending null = sayılamadı (DB hatası) — "0 bekleyen" yalanı yok; ekran söyler, onay düğmesi çıkmaz.
    days: number; configured: boolean; acknowledged: boolean; pending: number | null; default: number;
    // D2.55 · A-09: onay süreye ve maskeleme kapsamına bağlı. Kayıtlı ama geçersiz onay (süre/kapsam değişti) → approvalStale.
    approvedDays?: number | null; approvedCount?: number | null; approvalStale?: boolean;
    // D2.54 · A-06: 5 yıl inaktif hasta anonimleştirmesi — onay yoksa bekleyen sayı (sayılamazsa null) gösterilir, operatör onaylar.
    // S-F2-1.1: lastRun = son anonimleştirme turu (denetim izinden; zaman UTC ISO) — tur yoksa null.
    anonymization?: {
      days: number; acknowledged: boolean; pending: number | null; approvedAt?: string | null;
      lastRun?: { at: string | null; count: number | null } | null;
    };
    // F2-1.2 · A-73: onaylanmamış saat şüphesi (neden metni) — varken maskeleme / anonimleştirme / saklama silmesi KOŞMAZ.
    clockSuspect?: string | null;
  }
  const [retention, setRetention] = useState<RetentionDurum | null>(null);
  const [retMesgul, setRetMesgul] = useState(false);

  const retentionYukle = useCallback(async () => {
    const r = await apiGet<RetentionDurum | null>("/settings/retention", null, { silent: true });
    if (r) setRetention(r);
  }, []);
  useEffect(() => { void retentionYukle(); }, [retentionYukle]);

  const retentionKaydet = useCallback(async (govde: {
    days?: number; acknowledge?: boolean; acknowledge_days?: number; anonymize_acknowledge?: boolean; anonymize_revoke?: boolean;
    clock_confirm?: boolean;
  }) => {
    setRetMesgul(true);
    await apiPost<{ status?: string } | null>("/settings/retention", govde, null);
    setRetMesgul(false);
    // D2.55: başarısızlıkta da yenile — 409 (süre bu ekran açıldıktan sonra değişti) sonrası operatör GÜNCEL süreyi ve
    // etkilenecek kayıt sayısını görmeli; eski ekranda kalıp yeniden onaylamaya çalışmamalı.
    await retentionYukle();
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
    // ⚠️ D2.E01 (İG-6.20): masaüstü uygulamasında (backend BU makinede) dosyayı BACKEND yazar ve doğrular — `<a download>` WebView2'de
    // sessizce ölebiliyor (09-11 saha arızası, `dosyaIndir.ts`) ve eskiden dosya oluşmasa da "Yedek oluşturuldu" deniyordu (ölçüldü).
    // "oluşturuldu" YALNIZ backend yolu ve boyutu bildirince. Tarayıcı (LAN) yolunda dosya istemciye iner: metin "indirme başlatıldı —
    // doğrulayın" der. ⚠️ D2.E03 (Y84): UZUN zaman aşımı, "Tekrar deneyin" yok. Kapı: SettingsVeriTasima.D2E01_E03.web.test.tsx
    const yerel = backendBuMakinede();
    setTasimaMesgul("export");
    const res = await apiPost<{ status?: string; filename?: string; data_b64?: string; yol?: string; ad?: string;
                               bayt?: number; counts?: Record<string, number> } | null>(
      "/data/export", yerel ? { passphrase: parola, kaydet: true } : { passphrase: parola }, null,
      { timeoutMs: VERI_TASIMA_ZAMAN_ASIMI_MS, zamanAsimiMesaji: disaAktarmaZamanAsimiMesaji(),
        agHatasiMesaji: disaAktarmaAgHatasiMesaji() });
    setTasimaMesgul("");
    if (!res) return;                                 // hata mesajını apiPost gösterdi
    const c = res.counts || {};
    const sayim = t("ayarlar.yedek.sayim", { hasta: c.patients ?? 0, seans: c.treatment_sessions ?? 0, analiz: c.ai_analyses ?? 0 });
    if (yerel) {
      if (res.status === "success" && res.yol && (res.bayt ?? 0) > 0) {
        showToast(t("ayarlar.yedek.olusturuldu", { yol: res.yol, sayim }), "success");
      } else {
        showToast(t("ayarlar.yedek.yolYok"), "error");
      }
      return;
    }
    if (!res.data_b64) {
      showToast(t("ayarlar.yedek.icerikYok"), "error");
      return;
    }
    try {
      // base64 → Blob → indir. Dosya diske YALNIZ kullanıcının seçtiği yere gider.
      const ham = atob(res.data_b64);
      const buf = new Uint8Array(ham.length);
      for (let i = 0; i < ham.length; i++) buf[i] = ham.charCodeAt(i);
      const url = URL.createObjectURL(new Blob([buf], { type: "application/octet-stream" }));
      const ad = res.filename || "pemf-vet-yedek.pemfbak";
      const a = document.createElement("a");
      a.href = url; a.download = ad;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      showToast(
        t("ayarlar.yedek.indirmeBasladi", { dosyaAdi: ad, sayim }),
        "info",
      );
    } catch {
      showToast(t("ayarlar.yedek.kaydedilemedi"), "error");
    }
  }, [showToast, parolaSor, t]);

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
        t("ayarlar.yedek.geriYukleBaslik"),
        // ⚠️ Y12: metin GERÇEĞİ söyler — tedavi geçmişinin TAMAMI değişir; hasta kartları SİLİNMEZ (yedekte olmayanların kartı kalır).
        t("ayarlar.yedek.geriYukleOnay"),
        t("ayarlar.yedek.geriYukleDugme")))) return;
      setTasimaMesgul("import");
      // ⚠️ D2-3.5 (2-D incelemesi): dosya okunamazsa (arrayBuffer reddi) kilit açılır ve neden söylenir — eskiden düğmeler KALICI
      // kilitli, "Yükleniyor…" sonsuza dek kalıyordu (işlenmeyen ret). Kapı: screens/__tests__/VeriTasimaAgHatasi.D2_3_5.web.test.tsx
      let s = "";
      try {
        const buf = new Uint8Array(await f.arrayBuffer());
        for (let i = 0; i < buf.length; i++) s += String.fromCharCode(buf[i]);
      } catch {
        setTasimaMesgul("");
        showToast(t("ayarlar.yedek.okunamadi"), "error");
        return;
      }
      // ⚠️ D2.E03 (Y84): UZUN zaman aşımı; zaman aşımında metin "Tekrar deneyin" DEMEZ — geri yükleme cihazda sürüyor olabilir.
      const res = await apiPost<{ status?: string; counts?: Record<string, number>; uyari?: string } | null>(
        "/data/import", { passphrase: parola, blob_b64: btoa(s), confirm: "REPLACE_ALL" }, null,
        { timeoutMs: VERI_TASIMA_ZAMAN_ASIMI_MS, zamanAsimiMesaji: iceAktarmaZamanAsimiMesaji(),
          agHatasiMesaji: iceAktarmaAgHatasiMesaji() });
      setTasimaMesgul("");
      if (!res?.counts) return;
      const c = res.counts;
      // Denetim 2026-08-28 #05: backend "eklendi / zaten vardı / BAŞARISIZ" ayrımını BİLEREK
      // döndürüyor ama ekrana hiç ulaşmıyordu — "0 hasta" tek başına "hepsi zaten vardı" mı
      // yoksa "hepsi başarısız" mı olduğunu söylemez; tıbbi kayıt taşımada bu ayrım kritik.
      const zatenVardi = c.patient_db_zaten_vardi ?? 0;
      const basarisiz = c.patient_db_basarisiz ?? 0;
      const ek = [
        zatenVardi > 0 ? t("ayarlar.yedek.zatenVardi", { count: zatenVardi }) : "",
        basarisiz > 0 ? t("ayarlar.yedek.aktarilamadi", { count: basarisiz }) : "",
      ].filter(Boolean).join(", ");
      showToast(
        t("ayarlar.yedek.geriYuklendi", { hasta: c.patients ?? 0, seans: c.treatment_sessions ?? 0, analiz: c.ai_analyses ?? 0 })
        + (ek ? ` (${ek})` : "")
        // ⚠️ Y12: yedekte olmayan hastaların kartı korundu ama seans geçmişleri silindi — sunucu söyler, ekran GÖSTERİR.
        + (res.uyari ? ` ${res.uyari}` : ""),
        basarisiz > 0 ? "error" : "success",
      );
    };
    inp.click();
  }, [showToast, parolaSor, t]);
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
      showToast(t("ayarlar.hesap.adSoyadBos"), "error");
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
    if (r.ok) { showToast(t("ayarlar.hesap.guncellendi"), "success"); setEditP(false); }
    else showToast(r.error || t("ayarlar.hesap.guncellenemedi"), "error");
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
        showToast(res.ok ? t("ayarlar.baglanti.bagli") : t("ayarlar.baglanti.ulasilamadi"), res.ok ? "success" : "error");
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
            showToast(t("ayarlar.baglanti.gecersizAdres"), "error");
            return;
          }
          await AsyncStorage.setItem("@pemf_server_address", addr).catch(() => {});
          // #5: REST tabanı değişti ama WS eski cihaza bağlı kalıyordu → komutlar YENİ cihaza,
          // telemetri/"CANLI" rozeti ESKİ cihazdan geliyordu (iki cihazlı klinikte yanlış hasta
          // verisi okuma riski). Diğer iki yol (otomatik arama, uzaktan bağlan) zaten reconnect
          // ediyordu; bu yol atlanmıştı.
          liveReconnect();
          setConnectionStatus("ok");
          showToast(t("ayarlar.baglanti.basarili"), "success");
        } else {
          setConnectionStatus("fail");
          showToast(t("ayarlar.baglanti.cihazYok"), "error");
        }
      }
    } catch {
      setConnectionStatus("fail");
      showToast(t("ayarlar.baglanti.zamanAsimi"), "error");
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
        showToast(res.ok ? t("ayarlar.baglanti.bagliBuSayfa") : t("ayarlar.baglanti.ulasilamadi"), res.ok ? "success" : "error");
      } catch { setConnectionStatus("fail"); showToast(t("ayarlar.baglanti.ulasilamadi"), "error"); }
      setSearching(false);
      return;
    }
    // NATIVE: app'in GERÇEK keşif merdivenini kullan (discovery.ts: kayıtlı-adres → mDNS → remote →
    // TAM /24 subnet 1-254). Eski sabit-liste [100,1,101,2,102,110,50,200] backend'in DHCP IP'sini
    // (ör. .37) KAÇIRIYORDU → "bağlı olmasına rağmen bulunamadı". discoverBackend zaten config'i uygular +
    // PEMF kimliğini doğrular; bağlıyken kayıtlı adresi ilk sırada onaylar (yanlış-negatif biter).
    showToast(t("ayarlar.baglanti.taraniyor"), "info");
    try {
      const found = await discoverBackend();
      if (found) {
        const ipOnly = found.address.replace(/^https?:\/\//, "").replace(/:\d+$/, "");
        setSettings(prev => ({ ...prev, server_ip: ipOnly }));
        setConnectionStatus("ok");
        showToast(t("ayarlar.baglanti.bulundu", { adres: ipOnly }), "success");
        liveReconnect(); // doğrulanmış/yeni adrese WS'i bağla
      } else {
        setConnectionStatus("fail");
        showToast(t("ayarlar.baglanti.agdaYok"), "info");
      }
    } catch {
      setConnectionStatus("fail");
      showToast(t("ayarlar.baglanti.taramaBasarisiz"), "info");
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
        // Y42: "bağlantı önceki cihazda kaldı" yalnız uygulama gerçekten bir cihaza bağlıyken
        showToast(eslesmeMesaji(sonuc, { oncekiCihazaBagli: wsConnected }), "error");
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
        showToast(t("ayarlar.kopyala.kopyalandi", { etiket: label }), "success");
      } catch {
        platformAlert(label, value);
      }
    } else {
      platformAlert(label, t("ayarlar.kopyala.elle", { deger: value }));
    }
  };

  const handleSave = async () => {
    setLoading(true);
    setSaveStatus(t("ayarlar.kaydediliyor"));
    try {
      // #72: adres eskiden DOĞRULANMADAN kaydediliyor ve updateServiceConfig'in `false` dönüşü
      // yok sayılıyordu → boş/bozuk bir server_ip kalıcı hâle gelip sonraki açılışta keşfi
      // bozabiliyordu. Yalnız GEÇERLİ bir adres kalıcılaştırılır; geçersizse mevcut ayar korunur.
      const addr = (settings.server_ip || "").trim();
      if (addr && Platform.OS !== "web") {
        // ⚠️ D3.18 (B-6.28): "Test Et" ile AYNI PEMF kimlik kapısı (`service === "PEMF-Vet"` + kimlik). Eskiden Kaydet bunu
        // atlıyordu → doğrulanmamış bir LAN host'u taban + kalıcı adres oluyor, `/settings/` POST'u ve sonraki her istek (cihaz
        // anahtarı, Supabase JWT, operatör jetonu) oraya gidiyordu. Reddedilen adres KAYDEDİLMEZ, ayarlar oraya GÖNDERİLMEZ.
        let dogrulandi = false;
        try {
          dogrulandi = await checkHealth(addr, null);
        } catch {
          dogrulandi = false;
        }
        if (!dogrulandi) {
          setLoading(false);
          setSaveStatus(t("ayarlar.baglanti.cihazYok"));
          return;
        }
      }
      if (addr) {
        // KRİTİK: web'de app KENDİ origin'ine bağlıdır → base'i repoint ETME. Aksi halde bir sonraki
        // apiPost("/settings/") yanlış/boş adrese gider → "Kaydetme hatası" + tüm bağlantı kopar (yeşil kalır).
        const applied = Platform.OS === "web" ? true : updateServiceConfig(addr);
        if (!applied) {
          setLoading(false);
          setSaveStatus(t("ayarlar.baglanti.adresKaydedilmedi"));
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
      setSaveStatus(t("ayarlar.kaydedildi"));
      // #124: bu zamanlayıcı takip edilmiyordu → ekran 3sn dolmadan kapatılırsa unmount sonrası
      // setState (React uyarısı + boşa iş). Ref'te tut, unmount'ta temizle.
      if (saveStatusTimerRef.current) clearTimeout(saveStatusTimerRef.current);
      saveStatusTimerRef.current = setTimeout(() => setSaveStatus(""), 3000);
    } else {
      setSaveStatus(t("ayarlar.kayitHatasi"));
    }
  };

  return (
    <View style={styles.container}>
  {/* [S4 adım 3] İç dikey ScrollView KALDIRILDI: kabuk (AppShell) zaten tek kaydırıcı ve
  keyboardShouldPersistTaps='handled' taşıyor. İç ScrollView'ın yükseklik sınırı
  olmadığı için kendi kaydırmasını hiç üretmiyordu; ama klavye açıkken dokunuşu
  yutup 'Kaydet/Bağlan' düğmelerini İKİ dokunuş gerektiriyordu. */}
      <Text style={styles.headerTitle}>{t("ayarlar.baslik")}</Text>
      <Text style={styles.intro}>{t("ayarlar.altBaslik")}</Text>

      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <UserCog color={colors.primary} size={20} />
          <Text style={styles.cardTitle}>{t("ayarlar.profil.baslik")}</Text>
        </View>
        <Text style={styles.label}>{t("ayarlar.profil.suankiMod", { mod: isExpert ? t("ayarlar.profil.modVeteriner") : isResearcher ? t("ayarlar.profil.modArastirma") : t("ayarlar.profil.modSahip") })}</Text>
        {/* HASTA GÜVENLİĞİ: profil sıfırlama MainRouter'ı söküp WelcomeScreen'e düşürür →
            ACİL DURDUR ve çevrimdışı uyarısı ekrandan kaybolur. Seans sürerken önce durdur. */}
        <TouchableOpacity
          style={[styles.btnOutline, { marginTop: spacing.md }]}
          onPress={async () => { if (await guardTeardown(t("ayarlar.profil.degistirmekEylem"))) setUserMode(null); }}
          accessibilityRole="button"
        >
          <Text style={styles.btnOutlineText}>{t("ayarlar.profil.gecisYap")}</Text>
        </TouchableOpacity>
      </Card>

      {/* I18N (Y161): "Dil / Language" — İngilizce bayrağı kapalıyken HİÇ çizilmez (Türkçe görünüm aynen kalır). */}
      {dilSecimiGorunur() ? <DilSecimKarti /> : null}

      {/* T3 · Y190 (sahip 2026-10-24): "Kabin kamerası" seçimi Ayarlar'dan KALKTI → petri / fantom analiz panelinde ve AI Pro'da. */}

      {/* Hesap/Klinik bilgileri — kayıt (login) formunda girildi; buradan düzenlenebilir (Supabase user_metadata). */}
      <Card style={styles.card}>
        <View style={styles.cardHeaderRow}>
          <View style={styles.cardHeader}>
            <UserCog color={colors.primary} size={20} />
            <Text style={styles.cardTitle}>{t("ayarlar.hesap.baslik")}</Text>
          </View>
          {!editP ? (
            <TouchableOpacity onPress={startEditProfile} accessibilityLabel={t("ayarlar.hesap.duzenleEtiketi")}>
              <Text style={styles.editLink}>{t("ayarlar.hesap.duzenle")}</Text>
            </TouchableOpacity>
          ) : null}
        </View>

        {editP ? (
          <>
            <View style={styles.row2}>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>{t("ayarlar.hesap.ad")}</Text>
                <TextInput style={styles.input} value={pForm.first_name} onChangeText={t => setPForm({ ...pForm, first_name: t })} placeholder={t("ayarlar.hesap.ad")} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>{t("ayarlar.hesap.soyad")}</Text>
                <TextInput style={styles.input} value={pForm.last_name} onChangeText={t => setPForm({ ...pForm, last_name: t })} placeholder={t("ayarlar.hesap.soyad")} />
              </View>
            </View>
            <Text style={styles.label}>{t("ayarlar.hesap.unvan")}</Text>
            <TextInput style={styles.input} value={pForm.title} onChangeText={t => setPForm({ ...pForm, title: t })} placeholder={t("ayarlar.hesap.unvanOrnek")} />
            <Text style={styles.label}>{t("ayarlar.hesap.telefon")}</Text>
            <TextInput style={styles.input} value={pForm.phone} onChangeText={t => setPForm({ ...pForm, phone: t })} placeholder={t("ayarlar.hesap.cepTelefonu")} keyboardType="phone-pad" />
            {/* PROFİLE ÖZEL ALANLAR (2026-08-07): klinik bilgisi yalnız veterinerde, kurum
                bilgisi yalnız araştırmada sorulur. Ev sahibinde ikisi de sorulmaz — evcil
                hayvan sahibinden klinik adı istemek anlamsızdı. */}
            {isExpert && (
              <>
                <Text style={styles.label}>{t("ayarlar.hesap.klinik")}</Text>
                <TextInput style={styles.input} value={pForm.clinic_name} onChangeText={t => setPForm({ ...pForm, clinic_name: t })} placeholder={t("ayarlar.hesap.klinikAdi")} />
              </>
            )}
            {isResearcher && (
              <>
                <Text style={styles.label}>{t("ayarlar.hesap.kurum")}</Text>
                <TextInput style={styles.input} value={pForm.institution} onChangeText={t => setPForm({ ...pForm, institution: t })} placeholder={t("ayarlar.hesap.kurumOrnek")} />
                <Text style={styles.label}>{t("ayarlar.hesap.bolum")}</Text>
                <TextInput style={styles.input} value={pForm.department} onChangeText={t => setPForm({ ...pForm, department: t })} placeholder={t("ayarlar.hesap.bolumOrnek")} />
                <Text style={styles.label}>{t("ayarlar.hesap.akademikUnvan")}</Text>
                <TextInput style={styles.input} value={pForm.academic_title} onChangeText={t => setPForm({ ...pForm, academic_title: t })} placeholder={t("ayarlar.hesap.akademikUnvanOrnek")} />
              </>
            )}
            <View style={styles.row2}>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>{t("ayarlar.hesap.sehirIl")}</Text>
                <TextInput style={styles.input} value={pForm.city} onChangeText={t => setPForm({ ...pForm, city: t })} placeholder={t("ayarlar.hesap.sehir")} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>{t("ayarlar.hesap.ilce")}</Text>
                <TextInput style={styles.input} value={pForm.district} onChangeText={t => setPForm({ ...pForm, district: t })} placeholder={t("ayarlar.hesap.ilce")} />
              </View>
            </View>
            <Text style={styles.label}>{t("ayarlar.hesap.adres")}</Text>
            <TextInput style={styles.input} value={pForm.address} onChangeText={t => setPForm({ ...pForm, address: t })} placeholder={t("ayarlar.hesap.acikAdres")} />
            {isExpert && (
              <>
                <Text style={styles.label}>{t("ayarlar.hesap.klinikAcilTelefon")}</Text>
                <TextInput style={styles.input} value={pForm.clinic_phone} onChangeText={t => setPForm({ ...pForm, clinic_phone: t })} placeholder={t("ayarlar.hesap.klinikAcilTelefonOrnek")} keyboardType="phone-pad" />
              </>
            )}
            <View style={styles.actions}>
              <TouchableOpacity style={styles.btnPrimary} onPress={saveProfile} disabled={savingP}>
                <Save color="#fff" size={16} />
                <Text style={styles.btnPrimaryText}>{savingP ? t("ayarlar.kaydediliyor") : t("ayarlar.kaydet")}</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.btnOutline, { marginLeft: spacing.md }]} onPress={() => setEditP(false)} disabled={savingP}>
                <Text style={styles.btnOutlineText}>{t("ayarlar.iptal")}</Text>
              </TouchableOpacity>
            </View>
          </>
        ) : (
          <>
            <Info label={t("ayarlar.hesap.adSoyad")} value={prof.full_name || [prof.first_name, prof.last_name].filter(Boolean).join(" ")} />
            {prof.title ? <Info label={t("ayarlar.hesap.unvan")} value={prof.title} /> : null}
            <Info label={t("ayarlar.hesap.eposta")} value={session?.email} />
            {/* PROFİLE ÖZEL (2026-08-07): ev sahibine klinik/kurum bilgisi GÖSTERİLMEZ.
                Veri silinmez, yalnız o profille ilgisi olmadığı için gizlenir. */}
            {isExpert && prof.clinic_name ? <Info label={t("ayarlar.hesap.klinik")} value={prof.clinic_name} /> : null}
            {isResearcher && prof.institution ? <Info label={t("ayarlar.hesap.kurum")} value={prof.institution} /> : null}
            {isResearcher && prof.department ? <Info label={t("ayarlar.hesap.bolum")} value={prof.department} /> : null}
            {isResearcher && prof.academic_title ? <Info label={t("ayarlar.hesap.akademikUnvan")} value={prof.academic_title} /> : null}
            {(prof.city || prof.district) ? <Info label={t("ayarlar.hesap.sehirIlce")} value={[prof.city, prof.district].filter(Boolean).join(" / ")} /> : null}
            {prof.address ? <Info label={t("ayarlar.hesap.adres")} value={prof.address} /> : null}
            {prof.phone ? <Info label={t("ayarlar.hesap.telefon")} value={prof.phone} /> : null}
            {isExpert && prof.clinic_phone ? <Info label={t("ayarlar.hesap.klinikAcilTelefon")} value={prof.clinic_phone} /> : null}
            <Text style={styles.mutedNote}>{t("ayarlar.hesap.epostaAciklama")}</Text>
          </>
        )}
      </Card>

      {/* Bağlantı/eşleştirme TÜM profillerde görünür: AI modelleri backend bağlantısı olmadan çalışmaz →
          Evcil Hayvan Sahibi + Araştırma + Veteriner hepsi cihaza bağlanabilmeli (eskiden yalnız vet+araştırma). */}
      <>
          <Card style={styles.card}>
            <View style={styles.cardHeader}>
              <Network color={colors.primary} size={20} />
              <Text style={styles.cardTitle}>{t("ayarlar.uzakErisim.baslik")}</Text>
            </View>
            <Text style={styles.helperText}>
              {t("ayarlar.uzakErisim.aciklama")}
            </Text>

            {/* EŞLEŞTİRME — Bu cihazın kimliği + uzak cihaza kod/kimlik ile bağlan */}
            <View style={styles.pairBox}>
              <View style={styles.pairHeaderRow}>
                <Link2 color={colors.primary} size={16} />
                <Text style={styles.pairTitle}>{t("ayarlar.eslestirme.baslik")}</Text>
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
                    {t("ayarlar.eslestirme.paylasin")}
                  </Text>
                  {pairingCode ? (
                    <TouchableOpacity
                      style={styles.copyRow}
                      onPress={() => copyValue(t("ayarlar.eslestirme.kod"), pairingCode)}
                    >
                      <Text selectable style={styles.pairCodeText}>
                        {t("ayarlar.eslestirme.koduEtiketi")}<Text style={styles.pairCodeValue}>{pairingCode}</Text>
                        {!eslestirmeKoduUzaktanGecerliMi(cloudRegistry) ? (
                          <Text style={styles.bulutKayitHata}>{t("ayarlar.eslestirme.uzaktanGecersiz")}</Text>
                        ) : null}
                      </Text>
                      <Copy color={colors.primary} size={16} />
                    </TouchableOpacity>
                  ) : null}
                  {deviceId ? (
                    <TouchableOpacity
                      style={styles.copyRow}
                      onPress={() => copyValue(t("ayarlar.eslestirme.cihazKimligi"), deviceId)}
                    >
                      <Text
                        selectable
                        style={[styles.pairDeviceText, { flex: 1 }]}
                        numberOfLines={1}
                        ellipsizeMode="middle"
                      >
                        {t("ayarlar.eslestirme.cihazKimligiEtiketi")}<Text style={styles.pairDeviceValue}>{deviceId}</Text>
                      </Text>
                      <Copy color={colors.primary} size={16} />
                    </TouchableOpacity>
                  ) : null}
                </View>
              ) : (
                <Text style={styles.helperText}>
                  {t("ayarlar.eslestirme.kimlikYalnizBagliyken")}
                </Text>
              )}

              <Text style={[styles.label, { marginTop: spacing.md }]}>{t("ayarlar.eslestirme.uzakBaglanBaslik")}</Text>
              <TextInput
                style={styles.input}
                accessibilityLabel={t("ayarlar.eslestirme.uzakBaglanEtiketi")}
                value={remoteInput}
                onChangeText={(v) => setRemoteInput(v.replace(/\s+/g, "").toUpperCase())}
                placeholder={t("ayarlar.eslestirme.uzakBaglanIpucu")}
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
                <Text style={styles.btnPrimaryText}>{connecting ? t("ayarlar.eslestirme.baglaniyor") : t("ayarlar.eslestirme.baglan")}</Text>
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
                  {searching ? t("ayarlar.baglanti.araniyor") : t("ayarlar.baglanti.yenidenTara")}
                </Text>
              </TouchableOpacity>
            </View>

            {/* Bağlantı Durum Göstergesi */}
            {connectionStatus !== "idle" && (
              <View style={[styles.connStatus, { backgroundColor: connectionStatus === "ok" ? "#1a3a1a" : "#3a1a1a" }]}>
                <Text style={{ color: connectionStatus === "ok" ? "#4ade80" : "#f87171", fontWeight: "700" }}>
                  {connectionStatus === "ok" ? t("ayarlar.baglanti.durumBagli") : t("ayarlar.baglanti.durumBaglanamadi")}
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
                <Text style={styles.label}>{t("ayarlar.baglanti.manuelBaslik")}</Text>
                <TextInput
                  style={styles.input}
                  accessibilityLabel={t("ayarlar.baglanti.manuelEtiketi")}
                  value={settings.server_ip}
                  onChangeText={val => setSettings({...settings, server_ip: val})}
                  placeholder={t("ayarlar.baglanti.manuelIpucu")}
                  autoCapitalize="none"
                  keyboardType="default"
                />
                <TouchableOpacity style={styles.testBtn} onPress={handleTestConnection} disabled={searching}>
                  <Wifi color={colors.text} size={14} />
                  <Text style={styles.testBtnText}>{t("ayarlar.baglanti.testEt")}</Text>
                </TouchableOpacity>
                <Text style={styles.helperText}>
                  {t("ayarlar.baglanti.manuelAciklama")}
                </Text>
              </>
            )}
          </Card>

          <View style={styles.actions}>
            <TouchableOpacity style={styles.btnPrimary} onPress={handleSave} disabled={loading}>
              <Save color="#fff" size={16} />
              <Text style={styles.btnPrimaryText}>{loading ? t("ayarlar.kaydediliyor") : t("ayarlar.kaydetDugme")}</Text>
            </TouchableOpacity>
            {saveStatus ? <Text style={styles.statusText}>{saveStatus}</Text> : null}
          </View>
        </>

      {uzmanProfil && (
        <View style={{ marginTop: spacing.xl }}>
          <Card style={[styles.card as any, { borderColor: colors.danger, borderWidth: 1 }]}>
            <View style={styles.cardHeader}>
              <ServerCrash color={colors.danger} size={20} />
              <Text style={[styles.cardTitle, {color: colors.danger}]}>{t("ayarlar.bakim.baslik")}</Text>
            </View>
            <Text style={styles.helperText}>{t("ayarlar.bakim.aciklama")}</Text>

            <View style={{ gap: spacing.md, marginTop: spacing.md }}>
              <TouchableOpacity
                style={[styles.btnOutline, { borderColor: colors.warning }]}
                onPress={async () => {
                  // HASTA GÜVENLİĞİ: self-test bobinleri sürebilir. Tedavi sürerken çalıştırmak
                  // devam eden protokolü bozar → tek dokunuşla değil, onaylı ve seans-kontrollü.
                  if (!(await guardTeardown(t("ayarlar.bakim.selfTestEylem")))) return;
                  if (!(await platformConfirm(
                    t("ayarlar.bakim.selfTestBaslik"),
                    t("ayarlar.bakim.selfTestGovde"),
                    t("ayarlar.bakim.selfTestBaslat")
                  ))) return;
                  const res = await apiPost<any>("/hardware/selftest", {}, {status: "error"});
                  if (res.status === "success") showToast(t("ayarlar.bakim.selfTestGonderildi"), "success");
                  else showToast(t("ayarlar.bakim.selfTestGonderilemedi"), "error");
                }}
              >
                <RefreshCcw color={colors.warning} size={16} style={{marginRight: 8}} />
                <Text style={[styles.btnOutlineText, { color: colors.warning }]}>{t("ayarlar.bakim.selfTestDugme")}</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.btnOutline, { borderColor: colors.danger }]}
                onPress={async () => {
                  // Yön olarak GÜVENLİ (çıkışı sıfırlar) ama süren bir tedaviyi habersiz keser →
                  // onay iste. Not: burada guardTeardown KULLANILMAZ; bu eylemin kendisi durdurmadır.
                  if (!(await platformConfirm(
                    t("ayarlar.bakim.pwmBaslik"),
                    t("ayarlar.bakim.pwmGovde"),
                    t("ayarlar.bakim.pwmSifirla")
                  ))) return;
                  const res = await apiPost<any>("/hardware/reset_pwm", {}, {status: "error"});
                  if (res.status === "success") showToast(t("ayarlar.bakim.pwmSifirlandi"), "success");
                  else showToast(t("ayarlar.bakim.pwmBasarisiz"), "error");
                }}
              >
                <Trash2 color={colors.danger} size={16} style={{marginRight: 8}} />
                <Text style={[styles.btnOutlineText, { color: colors.danger }]}>{t("ayarlar.bakim.pwmDugme")}</Text>
              </TouchableOpacity>
            </View>
          </Card>
        </View>
      )}

      {/* ── CİHAZ TAŞIMA (2026-08-08) ────────────────────────────────────────────────────
          Kayıtlar bilerek MAKİNEDE tutuluyor (bulut senkronu YOK: kişisel veri yurt dışına
          çıkmasın, kayıt kliniğin olsun). Bunun tek gerçek dezavantajı cihaz değişimiydi —
          çözümü bulut değil, kliniğin KENDİ kontrolündeki şifreli dosya.
          Uzman profillerde (veteriner / araştırma — SG.G3): cihazdaki verinin tamamını dışarı çıkarır; Ev Sahibi'nde gizli. */}
      {uzmanProfil && Platform.OS === "web" && (
        <Card style={styles.card}>
          <Text style={styles.cardTitle}>{t("ayarlar.veriTasima.baslik")}</Text>
          <Text style={styles.intro}>
            {isResearcher
              ? t("ayarlar.veriTasima.aciklamaArastirma")
              : t("ayarlar.veriTasima.aciklama")}
            {t("ayarlar.veriTasima.parolaUyarisi")}
          </Text>

          <TouchableOpacity style={styles.btnOutline} disabled={!!tasimaMesgul} onPress={disaAktar}
            accessibilityRole="button"
            accessibilityLabel={isResearcher ? t("ayarlar.veriTasima.disaAktarEtiketiArastirma") : t("ayarlar.veriTasima.disaAktarEtiketi")}>
            <Text style={styles.btnOutlineText}>
              {tasimaMesgul === "export" ? t("ayarlar.veriTasima.hazirlaniyor") : t("ayarlar.veriTasima.yedekOlustur")}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity style={[styles.btnOutline, { borderColor: colors.warning }]}
            disabled={!!tasimaMesgul} onPress={iceAktar}
            accessibilityRole="button" accessibilityLabel={t("ayarlar.veriTasima.geriYukleEtiketi")}>
            <Text style={[styles.btnOutlineText, { color: colors.warning }]}>
              {tasimaMesgul === "import" ? t("ayarlar.veriTasima.yukleniyor") : t("ayarlar.veriTasima.geriYukleDugme")}
            </Text>
          </TouchableOpacity>

          <Text style={[styles.intro, { color: colors.warning }]}>
            {isResearcher
              ? t("ayarlar.veriTasima.geriYukleUyariArastirma")
              : t("ayarlar.veriTasima.geriYukleUyari")}
          </Text>
        </Card>
      )}

      {/* VERİ SAKLAMA — geri dönüşsüz maskeleme operatör kararıdır (2026-08-09 denetimi).
          Tıbbi-hukuki saklama süresi ülkeye/kliniğe göre değişir: KVKK silmeyi ister, açılmış
          bir dava dosyası saklamayı. Yazılım bu kararı sessizce almaz. */}
      {uzmanProfil && retention && (
        <Card style={styles.card}>
          <Text style={styles.cardTitle}>{t("ayarlar.saklama.baslik")}</Text>
          {isResearcher ? (
            <Text style={styles.intro}>{t("ayarlar.saklama.kapsam")}</Text>
          ) : null}
          <Text style={styles.intro}>
            {/* F2-3.5 (A-06 · Legal §6): maskeleme klinik ONAYI olmadan başlamaz — onaysız durumda "maskelenir" diye olmuş gibi anlatılmaz. */}
            {retention.days > 0
              ? retention.acknowledged
                ? t("ayarlar.saklama.maskelenir", { gun: retention.days })
                : t("ayarlar.saklama.onayBekliyor", { gun: retention.days })
              : t("ayarlar.saklama.kapali")}
            {/* D6.08 (B-3.2 · A-06): maskeleme kapalı ≠ "adlar süresiz saklanır" — 5 yıl inaktif hasta anonimleştirmesi (operatör
                onayıyla, eşik backend'in `kvkk_anonimlestirme.ESIK_GUN`'u) maskelemeden AYRI işler; eşik yanıttan söylenir. */}
            {retention.days > 0 || !retention.anonymization
              ? null
              : t("ayarlar.saklama.kapaliAnonim", { gun: retention.anonymization.days })}
          </Text>

          {/* F2-1.2 · A-73: saat ileri sıçradıysa ya da geride kaldıysa geri dönüşsüz adımlar operatör saati onaylayana dek bekler. */}
          {retention.clockSuspect ? (
            <>
              <Text style={[styles.intro, { color: colors.warning }]}>
                {t("ayarlar.saklama.saatSupheli", { saat: retention.clockSuspect })}
              </Text>
              <TouchableOpacity style={[styles.btnOutline, { borderColor: colors.warning, minHeight: touch.min }]}
                disabled={retMesgul} onPress={() => retentionKaydet({ clock_confirm: true })}
                accessibilityRole="button"
                accessibilityLabel={t("ayarlar.saklama.saatOnayEtiketi")}>
                <Text style={[styles.btnOutlineText, { color: colors.warning }]}>
                  {retMesgul ? "…" : t("ayarlar.saklama.saatOnay")}
                </Text>
              </TouchableOpacity>
            </>
          ) : null}

          {retention.pending === null ? (
            <Text style={[styles.intro, { color: colors.warning }]}>
              {t("ayarlar.saklama.bekleyenOkunamadi")}
            </Text>
          ) : retention.pending > 0 ? (
            <>
              {/* D2.55 · A-09: süre ya da maskeleme kapsamı değişince önceki onay geçersiz — neden yeniden sorulduğu söylenir. */}
              {retention.approvalStale ? (
                <Text style={[styles.intro, { color: colors.warning }]}>
                  {retention.approvedDays
                    ? t("ayarlar.saklama.oncekiOnaySure", { gun: retention.approvedDays })
                    : t("ayarlar.saklama.oncekiOnayEski")}
                </Text>
              ) : null}
              <Text style={[styles.intro, { color: colors.warning }]}>
                {t("ayarlar.saklama.maskeBekleyen", { count: retention.pending, gun: retention.days })}
              </Text>
              <TouchableOpacity style={[styles.btnOutline, { borderColor: colors.warning }]}
                disabled={retMesgul} onPress={() => retentionKaydet({ acknowledge: true, acknowledge_days: retention.days })}
                accessibilityRole="button"
                accessibilityLabel={t("ayarlar.saklama.maskeOnayEtiketi")}>
                <Text style={[styles.btnOutlineText, { color: colors.warning }]}>
                  {retMesgul ? "…" : t("ayarlar.saklama.maskeOnay")}
                </Text>
              </TouchableOpacity>
            </>
          ) : null}

          {/* D2.54 · A-06: anonimleştirme operatör ONAYINA bağlı — sessiz ve geri dönüşsüz işlem yok. Bekleyen sayı gösterilir. */}
          {retention.anonymization && !retention.anonymization.acknowledged ? (
            retention.anonymization.pending === null ? (
              <Text style={[styles.intro, { color: colors.warning }]}>
                {t("ayarlar.saklama.anonimOkunamadi")}
              </Text>
            ) : retention.anonymization.pending > 0 ? (
              <>
                <Text style={[styles.intro, { color: colors.warning }]}>
                  {t("ayarlar.saklama.anonimBekleyen", { count: retention.anonymization.pending, gun: retention.anonymization.days })}
                </Text>
                <TouchableOpacity style={[styles.btnOutline, { borderColor: colors.warning, minHeight: touch.min }]}
                  disabled={retMesgul} onPress={() => retentionKaydet({ anonymize_acknowledge: true })}
                  accessibilityRole="button"
                  accessibilityLabel={t("ayarlar.saklama.anonimOnayEtiketi")}>
                  <Text style={[styles.btnOutlineText, { color: colors.warning }]}>
                    {retMesgul ? "…" : t("ayarlar.saklama.anonimOnay")}
                  </Text>
                </TouchableOpacity>
              </>
            ) : null
          ) : retention.anonymization?.acknowledged ? (
            <>
              {/* S-F2-1.1 (2-F incelemesi · Y123 · A-06): onay süresiz değil — operatör son turu görür ve onayı GERİ ALABİLİR. */}
              <Text style={styles.intro}>
                {t("ayarlar.saklama.anonimOnayli", { gun: retention.anonymization.days })}
                {retention.anonymization.lastRun
                  ? t("ayarlar.saklama.sonTur", { zaman: sonTurZamani(retention.anonymization.lastRun.at), sayi: retention.anonymization.lastRun.count ?? 0 })
                  : t("ayarlar.saklama.henuzTurYok")}
              </Text>
              <TouchableOpacity style={[styles.btnOutline, { minHeight: touch.min }]}
                disabled={retMesgul} onPress={() => retentionKaydet({ anonymize_revoke: true })}
                accessibilityRole="button"
                accessibilityLabel={t("ayarlar.saklama.anonimGeriAlEtiketi")}>
                <Text style={styles.btnOutlineText}>
                  {retMesgul ? "…" : t("ayarlar.saklama.anonimDurdur")}
                </Text>
              </TouchableOpacity>
            </>
          ) : null}

          {/* SG.G3: `flex: 0` web'de esas genişliği %0 yapıyordu ("Kapalı" taşıyor, "1 yıl" iki satıra kırılıyordu) ve seçili
              düğmenin kenar / yazı rengi seçilmeyenle AYNIYDI (`btnOutline` zaten primary) → seçili süre ayırt edilmiyordu.
              Artık içerik genişliğinde, dokunma tabanında, seçili DOLGULU ve erişilebilir durumla söylenir. */}
          <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
            {[0, 365, 730, 1825].map((g) => {
              const secili = retention.days === g;
              return (
                <TouchableOpacity key={g} style={[styles.saklamaSecenek, secili && styles.saklamaSecenekSecili]}
                  disabled={retMesgul} onPress={() => retentionKaydet({ days: g })}
                  accessibilityRole="button"
                  accessibilityState={{ selected: secili, disabled: retMesgul }}
                  // RN-web 0.21 `accessibilityState`i DOM'a eşlemez (yalnız aria-*): web'de seçili durum aria-selected ile söylenir.
                  aria-selected={secili}
                  accessibilityLabel={g === 0 ? t("ayarlar.saklama.maskeKapatEtiketi") : t("ayarlar.saklama.sureEtiketi", { gun: g })}>
                  <Text style={[styles.btnOutlineText, secili && styles.saklamaSecenekSeciliMetin]} numberOfLines={1}>
                    {g === 0 ? t("ayarlar.saklama.secenekKapali") : g === 365 ? t("ayarlar.saklama.secenek1Yil") : g === 730 ? t("ayarlar.saklama.secenek2Yil") : t("ayarlar.saklama.secenek5Yil")}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </Card>
      )}

      {/* KÜNYE (2026-08-07): üretici/satıcı kimliği uygulamada da görünür olmalı — tıbbi
          cihaz yazılımında kullanıcı hangi tüzel kişiye ulaşacağını bilmeli (site künyesiyle
          AYNI bilgiler; tek kaynak `FIRMA` sabiti). */}
      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <Building2 color={colors.primary} size={20} />
          <Text style={styles.cardTitle}>{t("ayarlar.hakkinda.baslik")}</Text>
        </View>
        <Text style={styles.label}>{FIRMA.urun}</Text>
        <Text style={styles.kunyeSatir}>{FIRMA.unvan}</Text>
        <Text style={styles.kunyeSatir}>{FIRMA.adres}</Text>
        <Text style={styles.kunyeSatir}>{t("ayarlar.hakkinda.tel")}{FIRMA.tel}  ·  {FIRMA.eposta}</Text>
        <Text style={styles.kunyeSatir}>{t("ayarlar.hakkinda.mersis")}{FIRMA.mersis}{t("ayarlar.hakkinda.vkn")}{FIRMA.vkn}</Text>
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
      {/* ⚠️ Burada DOSYA YOLU, sürüm ve cihaz kimliği gibi UZUN değerler duruyor ve iki
          satırda kesiliyordu — üstelik kesilen kısım (yolun sonu, kimliğin kuyruğu) tam da
          işe yarayan kısım. Dokununca tamamı açılır; `selectable` korunur (kopyalanabilir). */}
      <GenisletilebilirMetin style={styles.infoValue} satir={2} testID="ayar-bilgi-deger">
        {value || "—"}
      </GenisletilebilirMetin>
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
  // SG.G3: saklama süresi seçenekleri — içerik genişliğinde (flex YOK), dokunma tabanı, seçili DOLGULU.
  saklamaSecenek: {
    borderWidth: 1,
    borderColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: touch.min,
    minWidth: touch.min + 24,
  },
  saklamaSecenekSecili: {
    backgroundColor: colors.primary,
  },
  saklamaSecenekSeciliMetin: {
    color: colors.white,
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
