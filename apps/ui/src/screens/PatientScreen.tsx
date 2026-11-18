// Author: mertaygn, cglrgrkn
import { useEffect, useState } from "react";
import { StyleSheet, Text, TextInput, View, TouchableOpacity, ActivityIndicator } from "react-native";
import { PlusCircle, Search, User, CheckCircle, Edit, Trash2, Activity, Check } from "lucide-react-native";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { colors, radius, spacing, typography, rs, layoutMax, touch } from "@/theme/tokens";
import { apiGet, apiPost, platformConfirm } from "@/services/apiClient";
import { duzenlemePayloadu } from "@/utils/hastaGuncelleme";
import type { Patient } from "@/types/domain";
import { useToast } from "@/components/ui/ToastProvider";
import { useAppNav } from "@/context/AppNavContext";
import { useUserMode } from "@/context/UserModeContext";
import { useOperatorOptional } from "@/context/OperatorContext";
import { isDesktopHost } from "@/services/desktopSession";
import { useAuth } from "@/context/AuthContext";
import { canAccess } from "@/config/access";
import {
  canChooseScope,
  eklemeKimlikIstemiMetni,
  effectiveScope,
  inScope,
  kimlikIstemiMetni,
  kimlikIstemi,
  silmeKimlikIstemiMetni,
  silinebilir,
  silinmeyecekNotu,
  baskaHekimSilmeMetni,
} from "@/utils/patientScope";
import { aramaEslesir } from "@/utils/aramaNormalize";
import { useCokluSecim } from "@/hooks/useCokluSecim";
import { hastaninSonAnalizi, hastayaGoreSonAnaliz, kapsamda, sonAnalizOzeti, type AnalizKaydi } from "@/utils/sonAnaliz";
import { SecimCubugu } from "@/components/ui/SecimCubugu";
import { TOPLU_SILME_ONAYI } from "@/services/topluSilme";
import { profilSozlugu } from "@/utils/profilSozlugu";
import { useTranslation } from "react-i18next";
import i18n from "i18next";

/** Y108: tekil silmede sunucu 404 (başka cihazda / sekmede zaten silinmiş) → bilgi; liste yenilenir. */
export const zatenSilinmisHasta = (): string => i18n.t("hasta.silme.zatenSilinmis");

export function PatientScreen() {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const { navigateTo, setSelectedPatient } = useAppNav();
  const { userMode, isExpert, isResearcher } = useUserMode();
  // SG.G1 / G2: kapsam düğmelerinin dili profile göre (araştırmada "Tüm Ekip" / "Benim Örneklerim"; veteriner metinleri AYNEN).
  const SK = profilSozlugu({ petOwner: userMode === "pet_owner", researcher: !!isResearcher || userMode === "researcher" });
  const { session } = useAuth();
  // ⚠️ DENETİM 2026-08-09 (Tier 1): kimlik AKTİF OPERATÖRDÜR, giriş e-postası değil.
  // Klinik tek Supabase hesabını paylaşıyor → her hasta aynı hesaba damgalanıyor ve
  // "Benim Hastalarım / Tüm Klinik" ayrımı (çoklu-operatör özelliğinin tüm amacı) anlamsız kalıyordu.
  const op = useOperatorOptional();
  const myEmail = (op ? op.operatorEmail : (session?.email || "")).toLowerCase();
  // Y113: kimlik veritabanı okunamıyorsa kimliksiz istemler arızayı ve çareyi söyler ("operatörünüzü seçin" DEMEZ).
  const kimlikDbOkunamiyor = Boolean(op?.kimlikDbOkunamiyor);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  // Klinik-ici gorunum: "mine" = benim kaydettiklerim (+ sahipsiz eski kayitlar), "all" = tum klinik.
  const [scope, setScope] = useState<"mine" | "all">("mine");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  /** KP-5 · 17: sunucunun 503 gerekçesi (DB'siz kip: erişimsiz Windows hesabı / veritabanı açılamıyor — sunucu istek dilinde yazar).
   *  Boşsa genel "yüklenemedi / bağlantıyı kontrol edin" iletisi (sunucuya ulaşılamadı ya da gerekçesiz hata). */
  const [loadErrorDetail, setLoadErrorDetail] = useState("");
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState({
    id: "", name: "", species: "", breed: "", age: "", weight: "", owner: "", vet_contact: "", owner_email: ""
  });
  // ⚠️ LOST-UPDATE SAVUNMASI (denetim 2026-08-30): düzenlemeye başlarkenki ORİJİNAL değerler.
  // Kaydederken yalnız DEĞİŞEN alanlar gönderilir → backend field-merge dokunulmayan alanı korur.
  // İki cihaz aynı hastayı farklı alanlarda düzenlerse biri diğerini SİLMEZ. Tüm-form göndermek
  // (eski davranış) B'nin bayat değerini A'nın yeni değerinin üstüne yazıyordu.
  const [editBaseline, setEditBaseline] = useState<Record<string, string>>({});

  const loadPatients = async () => {
    setLoading(true);
    setLoadError(false);
    let sunucuGerekcesi = "";
    const res = await apiGet<{ status: string, data: Patient[] }>("/patients", { status: "error", data: [] }, {
      onHttpError: (durum, detay) => { if (durum === 503 && detay) sunucuGerekcesi = detay; },
    });
    // ŞEKİL DOĞRULAMASI: `data` dizi gelmezse aşağıdaki `.filter`/`.map` çöker.
    if (res.status === "success" && Array.isArray(res.data)) {
      setPatients(res.data);
    } else {
      setLoadErrorDetail(sunucuGerekcesi);
      setLoadError(true);
    }
    setLoading(false);
  };

  useEffect(() => {
    loadPatients();
  }, []);

  const handleAddOrEditPatient = async () => {
    if (saving) return; // çift-tık koruması (mükerrer kayıt önleme)
    if (!form.name || !form.species) {
      showToast(t("hasta.form.doldurun"), "error");
      return;
    }

    // Validasyon — TR ondalık virgülünü kabul et (3,5 → 3.5).
    const ageN = Number(String(form.age).replace(",", "."));
    const weightN = Number(String(form.weight).replace(",", "."));
    if (form.age && (isNaN(ageN) || ageN < 0 || ageN > 50)) {
      showToast(t("hasta.form.yasAraligi"), "error");
      return;
    }
    if (form.weight && (isNaN(weightN) || weightN < 0 || weightN > 200)) {
      showToast(t("hasta.form.kiloAraligi"), "error");
      return;
    }
    // E-posta opsiyonel; girildiyse basit format kontrolü (rapor gönderimi için).
    if (form.owner_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.owner_email.trim())) {
      showToast(t("hasta.form.gecersizEposta"), "error");
      return;
    }

    // ⚠️ A-61 (D2.70): hasta eklemek KİMLİK ister. Kayıtlı operatörlü cihazda kimse seçili değilken istek GÖNDERİLMEZ:
    // kimliksiz eklenen hasta sahipsiz yazılır ve kliniğin HER hekiminin "Benim" listesine düşerdi. Operatörsüz tek
    // hekimli klinikte kimlik oturum e-postasıdır (Kural 2 — engel yok).
    if (!editingId && !myEmail) {
      showToast(kimlikIstemi(eklemeKimlikIstemiMetni(), kimlikDbOkunamiyor), "error");
      return;
    }

    // Ondalıkları nokta-normalize ederek gönder (backend/AI parse edebilsin).
    const normalized = { ...form, age: form.age ? String(ageN) : "", weight: form.weight ? String(weightN) : "" };
    // ⚠️ LOST-UPDATE SAVUNMASI: düzenlemede YALNIZ değişen alanları gönder (bkz. editBaseline).
    // Karşılaştırma ham `form` üzerinden (baseline ham yüklendi); gönderim `normalized` (nokta).
    // Boşaltma da bir değişikliktir → boş gönderilir → backend o alanı temizler (kasıtlı silme).
    // Backend field-merge, GÖNDERİLMEYEN alanı korur → iki cihaz çakışmaz.
    const payload: Record<string, string> = editingId
      ? duzenlemePayloadu(form, editBaseline, normalized, editingId)
      // Yeni kayit: operator_email = giris yapan hekim (klinik-ici sahiplik). Duzenlemede DEGISMEZ.
      : { ...normalized, operator_email: myEmail };
    setSaving(true);
    const res = await apiPost<{ status: string }>("/patients", payload, { status: "error" });
    setSaving(false);

    if (res.status === "success") {
      setIsAdding(false);
      setEditingId(null);
      setForm({ id: "", name: "", species: "", breed: "", age: "", weight: "", owner: "", vet_contact: "", owner_email: "" });
      loadPatients();
      showToast(editingId ? t("hasta.form.guncellendi") : t("hasta.form.kaydedildi"), "success");
    } else {
      showToast(t("hasta.form.islemHatasi"), "error");
    }
  };

  const handleEdit = (p: Patient) => {
    const loaded = {
      id: p.id || "",
      name: p.name || "",
      species: p.species || "",
      breed: p.breed || "",
      age: p.age || "",
      weight: p.weight || "",
      owner: p.owner || "",
      vet_contact: p.vet_contact || "",
      owner_email: p.owner_email || ""
    };
    setForm(loaded);
    setEditBaseline(loaded);  // orijinal snapshot → kaydetmede diff için
    setEditingId(p.id ?? null);
    setIsAdding(true);
  };

  const handleDelete = async (id: string) => {
    // ⚠️ D2.72 (B-6.26 · Y92): tekil silme de YALNIZ kendi kaydına (kural `patientScope.silinebilir`, backend aynısını
    // jetondan uygular). Eskiden her görünen kartta "sil" başka hekimin kaydına istek gönderiyordu.
    if (!myEmail) { showToast(kimlikIstemi(silmeKimlikIstemiMetni(), kimlikDbOkunamiyor), "error"); return; }
    const hedef = patients.find((p) => p.id === id);
    if (!hedef || !silinebilir(hedef, silmeBaglami)) { showToast(baskaHekimSilmeMetni(), "error"); return; }
    // platformConfirm = web-güvenli onay. (Alert.alert çoklu-buton WEB'de tetiklenmez → "Sil" onPress
    // hiç çalışmıyor, istek gitmiyordu → "hasta silme çalışmıyor". window.confirm'e düşer.)
    if (!(await platformConfirm(t("hasta.sil.baslik"), t("hasta.sil.govde"), t("ortak.sil")))) return;
    // Sunucu: POST /api/patients/{id}/delete (Expo-uyumlu) veya DELETE /api/patients/{id}.
    // ⚠️ Y108 (S-B.5): olmayan hasta 404 → "zaten silinmiş" (bilgi) + liste yenilenir (seans kartıyla aynı — D2.43); diğer
    // hatalarda sunucunun gerekçesi (428 kimlik, 403 başka hekim, 500 arıza). Kapı: __tests__/hastaTekilSilme.Y108.web.test.tsx
    const hata = { durum: 0, detay: "" };
    const res = await apiPost<{ status: string }>(`/patients/${id}/delete`, {}, { status: "error" },
      { silent: true, onHttpError: (durum, detay) => { hata.durum = durum; hata.detay = detay || ""; } });
    if (res.status === "success" || res.status === undefined) {
      showToast(t("hasta.sil.silindi"), "success");
      loadPatients();
    } else if (hata.durum === 404) {
      showToast(zatenSilinmisHasta(), "info");
      loadPatients();
    } else {
      showToast(hata.detay || t("hasta.sil.silinemedi"), "error");
    }
  };

  const handleDeleteAll = async () => {
    // ⚠️ Y106 (S-B.3): kayıtlı operatörlü klinikte kliniğin TAMAMINI silmek SEÇİLİ operatör ister (backend 428 der; iz onun
    // adına). Kimliksizken (kimse seçili değil / kilit sonrası) istek GÖNDERİLMEZ, onay penceresi bile açılmaz. Operatörsüz
    // klinikte `myEmail` oturum e-postasıdır (Kural 2). Kapı: __tests__/tumunuSil.Y106.web.test.tsx
    if (!myEmail) { showToast(kimlikIstemi(silmeKimlikIstemiMetni(), kimlikDbOkunamiyor), "error"); return; }
    if (!(await platformConfirm(t("hasta.sil.tumuBaslik"), t("hasta.sil.tumuGovde"), t("hasta.sil.hepsiniSil")))) return;
    // Backend (audit B-8.2) kazara toplu-silmeye karşı confirm ister.
    const res = await apiPost<{ status: string; vacuum_ok?: boolean }>(`/patients/delete_all`, { confirm: "DELETE_ALL" }, { status: "error" });
    if (res.status === "success") {
      showToast(t("hasta.sil.tumuSilindi"), "success");
      // ⚠️ D2.57 (B-3.109): silme GERÇEKLEŞTİ ama VACUUM düştüyse (disk dolu / G-Ç) bu AYRICA söylenir — silinen veri dosyanın boş
      // sayfalarında kalabilir. Eskiden backend bu durumda "error" dönüyor, ekran "başarısız" deyip listeyi yenilemiyordu.
      if (res.vacuum_ok === false) {
        showToast(t("hasta.sil.vacuumTamamlanamadi"), "info");
      }
      loadPatients();
    } else {
      showToast(t("hasta.sil.topluBasarisiz"), "error");
    }
  };

  const handleStartSession = (p: Patient) => {
    // Seçili hastayı paylaş + Kontrol ekranına git (orada seans bu hastayla başlar).
    setSelectedPatient({ id: p.id, name: p.name, species: p.species });
    showToast(t("hasta.kontrolePaneli", { name: p.name }), "success");
    navigateTo("control");
  };

  // "Benim Hastalarım" = operator_email eşleşen VEYA sahipsiz (eski/migrasyon) kayıtlar → hiçbir hasta kaybolmaz.
  // "Tüm Klinik" = filtresiz. Oturum yoksa (myEmail boş) filtreleme yapılmaz (hepsi).
  // KVKK: ev sahibi profili "all" kapsamına ASLA çıkamaz (sekme de gizli — bu ikinci kapı,
  // ileride başka bir yerden setScope("all") çağrılırsa diye). Mantık utils/patientScope.ts'te.
  const etkinScope = effectiveScope(scope, { isExpert, isResearcher, operatorKayitli: (op?.operators?.length ?? 0) > 0 });
  const scopedPatients = patients.filter(p => inScope(p, etkinScope, myEmail));
  // D2.72 · Y92: silme yetkisinin bağlamı (tek kaynak `silinebilir`). Kayıtlı operatör yoksa Kural 2.
  const silmeBaglami = {
    myEmail, operatorKayitli: (op?.operators?.length ?? 0) > 0, kapsam: etkinScope, isExpert,
    kayitliOperatorler: (op?.operators ?? []).map((o) => o.email), // Y104: sahipsiz = boş ya da kayıtlı olmayan sahip
  };
  // ⚠️ DENETİM 2026-09-12 (sahip: "klinik ve benim ayrımı düzgün çalışıyor mu incele"):
  // burada `inScope`un KOPYASI vardı. İki kopya sessizce ayrışır — sekmedeki SAYI bir kuralı,
  // LİSTE başka bir kuralı uygularsa operatör "(3)" görüp 5 kayıt bulur (ya da tersi) ve
  // hangisinin doğru olduğunu bilemez. Tek kaynak: utils/patientScope.
  // ⚠️ Oturum yokken 0: sahiplik kıyaslanamıyorken "hepsi benim" demek yanlış olurdu.
  const mineCount = myEmail ? patients.filter((p) => inScope(p, "mine", myEmail)).length : 0;
  // ⚠️ DENETİM 2026-08-17: ham `toLowerCase()` Türkçe'de İ→'i'+U+0307 ürettiği için "İpek" kaydı
  // "ipek" ile ARANDIĞINDA bulunamıyordu (I→i de 'ı' vermiyordu). Tek kaynak: aramaEslesir.
  const matchedPatients = scopedPatients.filter(
    (p) => aramaEslesir(p.name, search) || aramaEslesir(p.owner, search),
  );
  // PERFORMANS: liste sunucudan SAYFALANMADAN tümüyle geliyor ve ScrollView içinde `.map` ile
  // (sanallaştırma olmadan) render ediliyordu → birkaç yüz hastası olan klinikte her arama
  // tuşunda tüm kartlar yeniden render ediliyor, kaydırma takılıyordu. Backend'de sayfalama ucu
  // olmadığından (TreatmentHistory'deki `?limit&cursor` burada YOK) istemci tarafında artımlı
  // gösterim yapılır: kullanıcı "Daha fazla göster" ile açar. Arama kapsamı TÜM listede kalır.
  const PAGE = 60;
  const [visibleCount, setVisibleCount] = useState(PAGE);
  useEffect(() => { setVisibleCount(PAGE); }, [search, scope]);
  const filteredPatients = matchedPatients.slice(0, visibleCount);
  const hiddenCount = matchedPatients.length - filteredPatients.length;

  // ── SON ANALİZ ÖZETİ (sahip isteği 2026-09-12: "pet owner için ne ekleyebiliriz") ──
  // "Mia'ya en son ne zaman baktırdım?" sorusunun tek bakışta cevabı.
  // ⚠️ YENİ BACKEND YOK: `/api/ai/log` zaten hasta adı + tarih + özet döndürüyor.
  // ⚠️ HATA SESSİZ: analiz geçmişi okunamazsa hasta listesi YİNE ÇALIŞIR (özet gizlenir).
  // Yardımcı bir bilgi yüzünden asıl ekranı düşürmek orantısız olurdu.
  const [sonAnalizler, setSonAnalizler] = useState<Map<string, AnalizKaydi>>(new Map());
  useEffect(() => {
    let iptal = false;
    (async () => {
      const y = await apiGet<{ data?: AnalizKaydi[] } | null>("/ai/log?limit=200", null);
      if (iptal || !y || !Array.isArray(y.data)) return;
      // ⚠️ KAPSAM SÜZGECİ ŞART (denetim 2026-09-12, KENDİ EKLEMEMDE bulundu):
      // `/api/ai/log` operatör süzgeci DESTEKLEMİYOR — TÜM kliniğin analizlerini döndürür.
      // Süzmeden kullanınca "Benim Hastalarım"daki bir kartın altında BAŞKA bir hekimin
      // analiz özeti görünüyordu. Bu, sahibin İş 7'de sorduğu "klinik/benim ayrımı düzgün
      // çalışıyor mu?" sorusunun tam konusu ve orada üç kopyayı tek kaynağa aldığım kuralın
      // ta kendisi — yeni kod onu atlamıştı. TEK KAYNAK: patientScope.inScope.
      setSonAnalizler(hastayaGoreSonAnaliz(y.data.filter((k) => kapsamda(k, etkinScope, myEmail))));
    })();
    return () => { iptal = true; };
    // ⚠️ `patients` BAĞIMLILIKTA: yeni bir analiz yapılıp bu ekrana dönüldüğünde liste
    // yeniden yüklenir (`loadPatients`) → özet de tazelenir. Boş bağımlılıkla yazılmış ilk
    // sürüm, analizden sonra ESKİ özeti göstermeye devam ediyordu (sessiz bayatlama).
  }, [patients, etkinScope, myEmail]);

  // ── TOPLU SİLME (sahip bildirimi 2026-09-12: "hasta veri tabanında da toplu sil butonu lazım") ──
  // ⚠️ "Tümünü Sil" İLE AYNI ŞEY DEĞİL: bu, operatörün SEÇTİKLERİNİ siler ve o yüzden
  // veteriner-kısıtına (isExpert) tabi değildir — kendi kayıtlarını seçip silmek olağan iştir.
  // ⚠️ Seçim yalnız EKRANDA GÖRÜNEN kayıtlara kapanır (bkz. useCokluSecim "hayalet seçim"):
  // kapsam/arama değişince operatörün artık göremediği kayıtlar silinmez.
  const secim = useCokluSecim<string>(filteredPatients.map((p) => p.id || p.name || ""));
  const [siliniyor, setSiliniyor] = useState(false);

  const secilenleriSil = async () => {
    const secilenler = secim.seciliKimlikler.filter(Boolean);
    if (secilenler.length === 0 || siliniyor) return;
    // ⚠️ D2.72 (B-6.26 · Y92): istek YALNIZ silinebilen (kendi) kayıtlarla gider; dışarıda kalanların SAYISI onayda
    // söylenir. Eskiden "Tüm Klinik → Tümünü Seç" başka hekimlerin hastalarını isteğe koyuyordu (araştırma profili
    // "Tümünü Sil" kısıtını böyle dolanıyordu). Backend aynı kuralı jetondan uygular (karışık seçim → 403, hiçbiri).
    if (!myEmail) { showToast(kimlikIstemi(silmeKimlikIstemiMetni(), kimlikDbOkunamiyor), "error"); return; }
    const kimlikler = secilenler.filter((k) => {
      const p = patients.find((x) => (x.id || x.name || "") === k);
      return !!p && silinebilir(p, silmeBaglami);
    });
    if (kimlikler.length === 0) { showToast(baskaHekimSilmeMetni(), "error"); return; }
    const ok = await platformConfirm(
      t("hasta.sil.seciliBaslik"),
      t("hasta.sil.topluGovde", { count: kimlikler.length, not: silinmeyecekNotu(secilenler.length - kimlikler.length) }),
      t("ortak.sil"),
    );
    if (!ok) return;
    setSiliniyor(true);
    // TEK İSTEK, TEK TRANSACTION (bkz. servers/patient_router.remove_patients_bulk):
    // N ayrı silme yarı yolda koparsa operatör hangi kayıtların gittiğini bilemezdi.
    const res = await apiPost<{ status: string; silinen?: number }>(
      "/patients/delete_bulk",
      { patient_ids: kimlikler, confirm: TOPLU_SILME_ONAYI },
      { status: "error" },
    );
    setSiliniyor(false);
    if (res.status === "success") {
      const n = res.silinen ?? kimlikler.length;
      showToast(
        n === kimlikler.length ? t("hasta.sil.silindiSayi", { count: n }) : t("hasta.sil.kismenSilindi", { n, toplam: kimlikler.length }),
        "success",
      );
      secim.temizle();
      loadPatients();
    } else {
      showToast(t("hasta.sil.topluBasarisizKisa"), "error");
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>{SK.veritabani}</Text>
        <View style={{flexDirection: 'row', gap: spacing.sm}}>
          {/* Güvenlik/KVKK (inceleme): "Tümünü Sil" paylaşılan hasta-DB'sini yıkar → yalnız VETERİNER (isExpert).
              Araştırma modu (PIN'li de olsa) tüm klinik kayıtlarını silememeli.
              ⚠️ O-B.10 (A-03 · D2.11): arka uç kliniğin tamamını silmeyi YALNIZ cihazın kendisinden kabul eder (telefon, LAN,
              tünel → 403) → düğme de yalnız cihazın kendi ekranında (`isDesktopHost` — loopback) görünür; başka yerde ölü
              eylemdi. Kapı: __tests__/tumunuSilGorunurluk.OB10.{lan,tunel,cihaz}.web.test.tsx */}
          {isExpert && isDesktopHost() && (
            <Button
              label={t("hasta.sil.tumunuSil")}
              icon={<Trash2 color={colors.danger} size={16} />}
              variant="secondary"
              onPress={handleDeleteAll}
            />
          )}
          <Button
            label={secim.secimModu ? t("hasta.liste.secimiKapat") : t("hasta.liste.sec")}
            icon={!secim.secimModu ? <CheckCircle color={colors.primary} size={16} /> : undefined}
            variant="secondary"
            onPress={secim.secimModunuDegistir}
          />
          <Button
            label={isAdding ? t("ayarlar.iptal") : SK.yeniKayit}
            icon={!isAdding ? <PlusCircle color={colors.white} size={16} /> : undefined}
            variant={isAdding ? "secondary" : "primary"}
            onPress={() => {
              if (isAdding) {
                setEditingId(null);
                setForm({ id: "", name: "", species: "", breed: "", age: "", weight: "", owner: "", vet_contact: "", owner_email: "" });
              }
              setIsAdding(!isAdding);
            }}
          />
        </View>
      </View>

      {isAdding && (
        <Card style={styles.formCard}>
          <Text style={styles.formTitle}>{editingId ? t("hasta.form.duzenleBaslik") : t("hasta.form.ekleBaslik")}</Text>
          <ResponsiveGrid minItemWidth={200}>
            <TextInput style={styles.input} accessibilityLabel={t("hasta.form.adEtiketi")} placeholder={t("hasta.form.adYer")} placeholderTextColor={colors.textMuted} value={form.name} onChangeText={t => setForm({...form, name: t})} />
            <TextInput style={styles.input} accessibilityLabel={t("hasta.form.turEtiketi")} placeholder={t("hasta.form.turYer")} placeholderTextColor={colors.textMuted} value={form.species} onChangeText={t => setForm({...form, species: t})} />
            <TextInput style={styles.input} accessibilityLabel={t("hasta.form.irkEtiketi")} placeholder={t("hasta.form.irkYer")} placeholderTextColor={colors.textMuted} value={form.breed} onChangeText={t => setForm({...form, breed: t})} />
            <TextInput style={styles.input} accessibilityLabel={t("hasta.form.yasEtiketi")} placeholder={t("hasta.form.yasYer")} placeholderTextColor={colors.textMuted} value={form.age} onChangeText={t => setForm({...form, age: t})} keyboardType="numeric" />
            <TextInput style={styles.input} accessibilityLabel={t("hasta.form.kiloEtiketi")} placeholder={t("hasta.form.kiloEtiketi")} placeholderTextColor={colors.textMuted} value={form.weight} onChangeText={t => setForm({...form, weight: t})} keyboardType="numeric" />
            <TextInput style={styles.input} accessibilityLabel={t("hasta.form.sahipEtiketi")} placeholder={t("hasta.form.sahipYer")} placeholderTextColor={colors.textMuted} value={form.owner} onChangeText={t => setForm({...form, owner: t})} />
            <TextInput style={styles.input} accessibilityLabel={t("hasta.form.vetTelEtiketi")} placeholder={t("hasta.form.vetTelYer")} placeholderTextColor={colors.textMuted} value={form.vet_contact} onChangeText={t => setForm({...form, vet_contact: t})} keyboardType="phone-pad" />
            <TextInput style={styles.input} accessibilityLabel={t("hasta.form.sahipEpostaEtiketi")} placeholder={t("hasta.form.sahipEpostaYer")} placeholderTextColor={colors.textMuted} value={form.owner_email} onChangeText={t => setForm({...form, owner_email: t})} keyboardType="email-address" autoCapitalize="none" autoCorrect={false} />
          </ResponsiveGrid>
          <View style={styles.saveBtn}>
            <Button label={saving ? t("hesap.operator.kaydediliyor") : editingId ? t("guncelleme.guncelle") : t("ayarlar.kaydet")} icon={<CheckCircle color={colors.white} size={16} />} onPress={handleAddOrEditPatient} disabled={saving} />
          </View>
        </Card>
      )}

      {/* Klinik-içi görünüm: hekim varsayılan kendi hastalarını görür, isterse tüm kliniğe geçer.
          ⚠️ KVKK 2026-08-08: "Tüm Klinik" EV SAHİBİNE KAPALI. Bu ekran pet_owner'a yeni açıldı
          (AI hasta seçimi için); hasta DB'si aynı makinede profiller arasında PAYLAŞILDIĞINDAN
          ev sahibi sekmeye basıp kliniğin tüm hasta listesini (sahip adı/iletişim = kişisel veri)
          görebilirdi. Ev sahibi YALNIZ kendi kayıtlarını görür — `scope` "mine"da kilitli. */}
      {canChooseScope(myEmail, { isExpert, isResearcher }) ? (
        <View style={styles.segment}>
          <TouchableOpacity
            style={[styles.segmentBtn, scope === "mine" && styles.segmentBtnActive]}
            onPress={() => setScope("mine")}
            accessibilityLabel={SK.benimListe.toLocaleLowerCase("tr-TR").replace(/^benim /, "Benim ")}
          >
            <Text style={[styles.segmentText, scope === "mine" && styles.segmentTextActive]} numberOfLines={1}>
              {SK.benimListe}{mineCount ? ` (${mineCount})` : ""}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.segmentBtn, scope === "all" && styles.segmentBtnActive]}
            onPress={() => setScope("all")}
            accessibilityLabel={t("hasta.liste.tumKapsamEtiketi", { tumKapsamKucuk: SK.tumKapsamKucuk, kayitlarAd: SK.kayitlarAd })}
          >
            <Text style={[styles.segmentText, scope === "all" && styles.segmentTextActive]} numberOfLines={1}>
              {SK.tumKapsam} ({patients.length})
            </Text>
          </TouchableOpacity>
        </View>
      ) : null}

      <View style={styles.searchBox}>
        <Search color={colors.textMuted} size={20} />
        <TextInput
          style={styles.searchInput}
          accessibilityLabel={SK.araEtiketi}
          placeholder={SK.araYer}
          placeholderTextColor={colors.textMuted}
          value={search}
          onChangeText={setSearch}
        />
      </View>

      <View style={styles.list}>
  {/* [S4 adım 3] İç dikey ScrollView KALDIRILDI: kabuk (AppShell) zaten tek kaydırıcı ve
  keyboardShouldPersistTaps='handled' taşıyor. İç ScrollView'ın yükseklik sınırı
  olmadığı için kendi kaydırmasını hiç üretmiyordu; ama klavye açıkken dokunuşu
  yutup 'Kaydet/Bağlan' düğmelerini İKİ dokunuş gerektiriyordu. */}
        {loading ? (
          <View style={styles.stateBox}>
            <ActivityIndicator color={colors.primary} />
            <Text style={styles.emptyText}>{t("ayarlar.veriTasima.yukleniyor")}</Text>
          </View>
        ) : loadError ? (
          <View style={styles.stateBox}>
            <Text style={styles.emptyText}>{loadErrorDetail || t("hasta.liste.yuklenemedi")}</Text>
            <Button label={t("ortak.tekrarDene")} variant="secondary" onPress={loadPatients} />
          </View>
        ) : filteredPatients.length === 0 ? (
          <Text style={styles.emptyText}>
            {!myEmail ? kimlikIstemi(kimlikIstemiMetni(), kimlikDbOkunamiyor) : search ? t("hasta.liste.aramaBos") : SK.bosListe}
          </Text>
        ) : (
          <>
          {secim.secimModu ? (
            <SecimCubugu
              seciliSayi={secim.seciliSayi}
              hepsiSecili={secim.hepsiSecili}
              onTumunuSec={secim.tumunuSec}
              onTemizle={secim.temizle}
              onSil={secilenleriSil}
              onVazgec={secim.secimModunuDegistir}
              siliniyor={siliniyor}
              gizliSayi={hiddenCount}
              silEtiketi={t("hasta.sil.seciliBaslik")}
              testID="hasta-secim-cubugu"
            />
          ) : null}
          <ResponsiveGrid minItemWidth={340}>
            {filteredPatients.map((p) => (
              // key olarak p.id (idx değil) — silme/eklemede doğru DOM diff.
              <Card key={p.id || p.name} style={styles.patientCard}>
                <View style={styles.cardHeader}>
                  <View style={styles.headerLeft}>
                    {secim.secimModu ? (
                      <TouchableOpacity
                        style={[styles.onayKutusu, secim.secilimi(p.id || p.name || "") && styles.onayKutusuSecili]}
                        onPress={() => secim.degistir(p.id || p.name || "")}
                        accessibilityRole="checkbox"
                        accessibilityState={{ checked: secim.secilimi(p.id || p.name || "") }}
                        accessibilityLabel={t("hasta.liste.secimEtiketi", { name: p.name })}
                        testID={`hasta-secim-${p.id || p.name}`}
                      >
                        {secim.secilimi(p.id || p.name || "") ? <Check color={colors.white} size={16} /> : null}
                      </TouchableOpacity>
                    ) : (
                      <User color={colors.primary} size={24} />
                    )}
                    <View style={styles.headerText}>
                      <Text style={styles.patientName} numberOfLines={1}>{p.name}</Text>
                      <Text style={styles.patientSub} numberOfLines={1}>{p.species} · {p.breed}</Text>
                    </View>
                  </View>
                  <View style={styles.actions}>
                    {/* Seans Başlat yalnız control erişimi olan profillere (vet) — araştırma modu control'e
                        giremez, buton effectiveRoute kapısında dashboard'a düşen çıkmaz-sokaktı (UX + tutarlılık). */}
                    {/* a11y: ikon-only butonlarda etiket/rol YOKTU → ekran okuyucu yalnız "buton"
                        diyordu; hangi hastaya ait olduğu da belirsizdi. Dokunma hedefi de 44pt'nin
                        altındaydı (actionBtnIcon minWidth/minHeight ile büyütüldü). */}
                    {canAccess(userMode, "control") && (
                      <TouchableOpacity onPress={() => handleStartSession(p)} style={styles.actionBtnIcon}
                        accessibilityRole="button" accessibilityLabel={t("hasta.liste.seansBaslatEtiketi", { name: p.name })}>
                        <Activity color={colors.success} size={20} />
                      </TouchableOpacity>
                    )}
                    <TouchableOpacity onPress={() => handleEdit(p)} style={styles.actionBtnIcon}
                      accessibilityRole="button" accessibilityLabel={t("hasta.liste.duzenleEtiketi", { name: p.name })}>
                      <Edit color={colors.primary} size={20} />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => handleDelete(p.id!)} style={styles.actionBtnIcon}
                      accessibilityRole="button" accessibilityLabel={t("hasta.liste.silEtiketi", { name: p.name })}>
                      <Trash2 color={colors.danger} size={20} />
                    </TouchableOpacity>
                  </View>
                </View>
                <View style={styles.detailsRow}>
                  <Text style={styles.detailText} numberOfLines={1}>{t("hasta.kart.sahip")}<Text style={{fontWeight: "bold"}}>{p.owner || t("hasta.kart.belirtilmemis")}</Text></Text>
                  <Text style={styles.detailText}>{t("hasta.kart.kilo", { kilo: p.weight || "-" })}</Text>
                  <Text style={styles.detailText}>{t("hasta.kart.yas", { yas: p.age || "-" })}</Text>
                  {/* Tüm Klinik görünümünde kaydı hangi hekimin oluşturduğunu göster. */}
                  {etkinScope === "all" && p.operator_email ? (
                    <Text style={styles.detailText} numberOfLines={1}>{t("hasta.kart.kaydeden", { eposta: p.operator_email })}</Text>
                  ) : null}
                  {/* ⚠️ Son analiz özeti — önce hasta KİMLİĞİ, bulunamazsa ADI ile eşlenir
                      (2026-09-12 taşıması). Kimlik aynı adlı iki hayvanı AYIRIR; ad yedeği,
                      taşımanın bilerek kimliksiz bıraktığı ESKİ kayıtlar için gereklidir. */}
                  {sonAnalizOzeti(hastaninSonAnalizi(sonAnalizler, p)) ? (
                    <Text style={styles.sonAnaliz} numberOfLines={2} testID={`hasta-son-analiz-${p.id || p.name}`}>
                      {t("hasta.kart.sonAnaliz", { ozet: sonAnalizOzeti(hastaninSonAnalizi(sonAnalizler, p)) })}
                    </Text>
                  ) : null}
                </View>
              </Card>
            ))}
          </ResponsiveGrid>
          </>
        )}

        {hiddenCount > 0 && (
          <TouchableOpacity
            style={styles.loadMoreBtn}
            onPress={() => setVisibleCount((n) => n + PAGE)}
            accessibilityRole="button"
            accessibilityLabel={t("hasta.liste.dahaFazlaEtiketi", { count: hiddenCount })}
          >
            <Text style={styles.loadMoreText}>{t("hasta.dahaFazla.metin", { count: hiddenCount })}</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  // Seçim onay kutusu — `User` ikonunun YERİNE geçer (satır kaymasın). Dokunma hedefi
  // `touch.min`den küçük olamaz: kaza SEÇİMİ yanlış kaydı silmeye götürür.
  onayKutusu: {
    width: touch.min,
    height: touch.min,
    borderRadius: rs(6),
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  onayKutusuSecili: { backgroundColor: colors.primary, borderColor: colors.primary },
  sonAnaliz: { color: colors.primary, fontSize: typography.small, fontWeight: "600", width: "100%" },
  container: { flex: 1, gap: spacing.lg, width: "100%", maxWidth: layoutMax.icerik, alignSelf: "center" },
  loadMoreBtn: {
    marginTop: spacing.md, paddingVertical: spacing.md, alignItems: "center",
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgAlt,
  },
  loadMoreText: { color: colors.primary, fontWeight: "700", fontSize: typography.small },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: spacing.md },
  title: { color: colors.text, fontSize: typography.title, fontWeight: "800", marginBottom: spacing.xs },
  formCard: { gap: spacing.md, backgroundColor: colors.bgAlt, borderColor: colors.primarySoft, borderWidth: 1 },
  formTitle: { color: colors.primary, fontSize: typography.subtitle, fontWeight: "700" },
  input: { backgroundColor: colors.bg, color: colors.text, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  saveBtn: { marginTop: spacing.sm },
  segment: { flexDirection: "row", backgroundColor: colors.bgAlt, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: rs(4), gap: rs(4) },
  segmentBtn: { flex: 1, paddingVertical: spacing.sm, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  segmentBtnActive: { backgroundColor: colors.primary },
  segmentText: { color: colors.textMuted, fontSize: typography.caption, fontWeight: "700" },
  segmentTextActive: { color: colors.white },
  searchBox: { flexDirection: "row", alignItems: "center", backgroundColor: colors.bgAlt, paddingHorizontal: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, height: rs(48), gap: spacing.sm },
  searchInput: { flex: 1, color: colors.text, fontSize: typography.body },
  // [S4 adım 3] Alt boşluk TEK yerde: AppShell içerik ScrollView'ı rs(160)+güvenli alan (mobil) /
  // rs(84) (masaüstü) veriyor. Ekranın kendi paddingBottom'ı bunun ÜSTÜNE binip sayfa sonunda
  // ~200 px ölü alan bırakıyordu.
  list: { gap: spacing.md },
  patientCard: { gap: spacing.md },
  cardHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md },
  headerLeft: { flex: 1, flexDirection: "row", alignItems: "center", gap: spacing.md },
  headerText: { flex: 1, minWidth: rs(0) },
  patientName: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800" },
  patientSub: { color: colors.textMuted, fontSize: typography.small, marginTop: 2 },
  detailsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.lg, backgroundColor: colors.bgAlt, padding: spacing.sm, borderRadius: radius.sm },
  detailText: { color: colors.textMuted, fontSize: typography.caption },
  emptyText: { color: colors.textMuted, textAlign: "center", marginTop: spacing.xl },
  stateBox: { alignItems: "center", justifyContent: "center", gap: spacing.md, marginTop: spacing.xl },
  actions: { flexDirection: "row", gap: spacing.sm },
  // WCAG 2.5.5 / platform kılavuzu: minimum 44pt dokunma hedefi. `padding: xs` ile ~28px kalıyordu
  // ve üç yıkıcı-yakın buton (sil / düzenle / seans başlat) yan yana duruyordu → yanlış dokunuş.
  actionBtnIcon: { padding: spacing.xs, minWidth: touch.min, minHeight: touch.min, alignItems: "center", justifyContent: "center" }
});
