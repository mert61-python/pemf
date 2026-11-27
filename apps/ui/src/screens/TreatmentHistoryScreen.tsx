// Author: mertaygn, cglrgrkn
import { useEffect, useState } from "react";
import { StyleSheet, Text, View, TouchableOpacity, ActivityIndicator, TextInput, Platform } from "react-native";
import { Edit3, Trash2, Check } from "lucide-react-native";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/StatusPill";
import { colors, spacing, typography, rs, radius, layoutMax, touch } from "@/theme/tokens";
import { serviceConfig } from "@/services/config";
import { apiGet, apiPost, platformConfirm, platformAlert } from "@/services/apiClient";
import { useToast } from "@/components/ui/ToastProvider";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { useAppNav } from "@/context/AppNavContext";
import { useAuth } from "@/context/AuthContext";
import { useOperatorOptional } from "@/context/OperatorContext";
import { SessionDetailModal } from "@/components/domain/SessionDetailModal";
import { aramaEslesir } from "@/utils/aramaNormalize";
import { hedefEtiketi, modEtiketi, nedenliDurum } from "@/utils/seansDegerEtiketi";
import {
  inScope,
  kimlikIstemiMetni,
  kimlikIstemi,
  silmeKimlikIstemiMetni,
  silinebilir,
  silinmeyecekNotu,
  baskaHekimSilmeMetni,
} from "@/utils/patientScope";
import { useUserMode } from "@/context/UserModeContext";
import { profilSozlugu } from "@/utils/profilSozlugu";
import { etkinBicimYereli } from "@/i18n/dil";
import i18n from "i18next";

/** D2.43: tekil silmede seans sunucuda yoksa (başka cihaz/hekim az önce silmiş) gösterilen metin. */
export const zatenSilinmisSeans = (): string => i18n.t("seans.gecmis.zatenSilinmis");
import { downloadFileWithAuth } from "@/services/dosyaIndir";
import { backendBuMakinede } from "@/services/backendKonumu";
import { useCokluSecim } from "@/hooks/useCokluSecim";
import { SecimCubugu } from "@/components/ui/SecimCubugu";
import { TOPLU_SILME_ONAYI } from "@/services/topluSilme";
import { kayitYogunlugu } from "@/utils/yogunlukGosterimi";
import { CSV_MAX, PDF_MAX } from "@/screens/treatmentHistorySinirlari";
import { useTranslation } from "react-i18next";

// Backend ham seans durumlarını (İngilizce) görüntüleme için Türkçeye çevirir.
// NOT: Yalnızca gösterim amaçlıdır; backend ham değerleri (renk/durum mantığı) değiştirilmez.
const STATUS_ANAHTARLARI: Record<string, string> = {
  completed: "seans.durum.completed",
  active: "seans.durum.active",
  running: "seans.durum.running",
  in_progress: "seans.durum.in_progress",
  pending: "seans.durum.pending",
  stopped: "seans.durum.stopped",
  interrupted: "seans.durum.interrupted",
  aborted_recovered: "seans.durum.aborted_recovered",
  cancelled: "seans.durum.cancelled",
  canceled: "seans.durum.canceled",
  error: "seans.durum.error",
  failed: "seans.durum.failed",
  success: "seans.durum.success",
  // ⚠️ ÜRETİMDE KULLANILAN AMA HARİTADA OLMAYAN İKİ DURUM (2026-09-12'de bulundu):
  // backend bunları gerçekten yazıyor (acil durdurma / güç kesintisi mutabakatı) ama
  // harita çeviremediği için ekranda ham "Emergency_stopped" görünüyordu.
  emergency_stopped: "seans.durum.emergency_stopped",
  aborted_due_to_power: "seans.durum.aborted_due_to_power",
  // ⚠️ Donanım komutu reddetti → seans HİÇ başlamadı. "Tamamlandı" yazmak,
  // uygulanmamış bir tedaviyi uygulanmış olarak belgelemek olurdu.
  hardware_rejected: "seans.durum.hardware_rejected",
  // Y207 (S-D5.3): kanıtı 3 açılış boyunca okunamayan seans — süre / doz bilinmiyor (uydurulmadı).
  aborted_duration_unknown: "seans.durum.aborted_duration_unknown"
};

/** ODD K-8 · Y295: kart tarihi etkin dilin biçiminde — `started_epoch` varsa ondan, yoksa `session_date` + `start_time` (yerel saat). */
export function seansTarihi(s: { started_epoch?: number | null; session_date?: string; start_time?: string }): string {
  const ham = `${s.session_date ?? ""} ${s.start_time ?? ""}`.trim();
  const d =
    typeof s.started_epoch === "number" && Number.isFinite(s.started_epoch)
      ? new Date(s.started_epoch * 1000)
      : /^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?$/.test(ham)
        ? new Date(ham.replace(" ", "T"))
        : null;
  if (!d || Number.isNaN(d.getTime())) return ham;
  return d.toLocaleString(etkinBicimYereli(), { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function statusEtiketi(status?: string, neden?: string | null): string {
  if (!status) return i18n.t("ai.deger.unknown");
  const key = status.toLowerCase();
  const anahtar = STATUS_ANAHTARLARI[key];
  // YS2 a (B1): AI Pro durdurma nedeni → "Durduruldu (plaka kaydı)" (PDF / CSV ile aynı kaynak ve etiket).
  if (typeof anahtar === "string") return nedenliDurum(i18n.t, i18n.t(anahtar as never) as string, neden);
  // Bilinmeyen durumu en azından okunaklı göster (ilk harf büyük).
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function TreatmentHistoryScreen() {
  const { t } = useTranslation();
  const { selectedPatient } = useAppNav();
  const { session } = useAuth();
  // ⚠️ DENETİM 2026-08-09 (Tier 1): "Benim Seanslarım" filtresi AKTİF OPERATÖRE göre olmalı.
  // Giriş e-postası kullanılınca paylaşılan hesaplı klinikte filtre ya hiçbir şey ya her şeyi
  // gösteriyordu — hekim kendi seansını bulamıyor, başkasınınkini kendi sanıyordu.
  const op = useOperatorOptional();
  const myEmail = (op ? op.operatorEmail : (session?.email || "")).toLowerCase();
  // Y113: kimlik veritabanı okunamıyorsa kimliksiz istemler arızayı ve çareyi söyler ("operatörünüzü seçin" DEMEZ).
  const kimlikDbOkunamiyor = Boolean(op?.kimlikDbOkunamiyor);
  const { isExpert, isResearcher } = useUserMode();
  // SG.G1: kapsam düğmesinin dili profile göre (araştırmada "Tüm Ekip"; liste zaten profile göre ayrı — `X-PEMF-Profil`).
  const SK = profilSozlugu({ researcher: !!isResearcher });
  // Klinik-içi görünüm: "mine" = benim başlattığım seanslar (+ sahipsiz eski), "all" = tüm klinik.
  const [scope, setScope] = useState<"mine" | "all">("mine");
  // D2.72 · Y92: seans (tıbbi kayıt) silme yetkisinin bağlamı — tek kaynak `silinebilir`; kayıtlı operatör yoksa Kural 2.
  const silmeBaglami = {
    myEmail, operatorKayitli: (op?.operators?.length ?? 0) > 0, kapsam: scope, isExpert,
    kayitliOperatorler: (op?.operators ?? []).map((o) => o.email), // Y104: sahipsiz = boş ya da kayıtlı olmayan sahip
  };
  const silmeEngeli = (kayit: { operator_email?: string | null }): string | null =>
    !myEmail ? kimlikIstemi(silmeKimlikIstemiMetni(), kimlikDbOkunamiyor) : silinebilir(kayit, silmeBaglami) ? null : baskaHekimSilmeMetni();
  const { showToast } = useToast();
  const [sessions, setSessions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  // audit B-8.2: keyset (cursor) pagination — ilk sayfa + "Daha Fazla" ile büyük geçmişe eriş.
  const PAGE_SIZE = 50;
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  // Hastalar tabından "geçmiş"e gelindiyse aramayı o hastayla önceden doldur.
  const [searchQuery, setSearchQuery] = useState(selectedPatient?.name || "");
  // Seans BOBİN-DETAYI modalı için seçili seans (null → kapalı).
  const [selectedSessionId, setSelectedSessionId] = useState<string | number | null>(null);

  // YS2 e (B8, YG2 25-11): profilin TOPLAM seans sayısı (sahip tek tek saymak zorunda kaldı). Liste TAMSA toplam odur; SAYFALIYSA
  // istatistik ucundan (`X-PEMF-Profil` süzgeciyle AYNI küme) — liste isteğinden SONRA, yalnız gerektiğinde; okunamazsa sayı yazılmaz.
  const [toplamSeans, setToplamSeans] = useState<number | null>(null);
  // Y331 (sahip 26-11): seans alan CSV'leri artık bulut eşitlemesi DIŞINDA yerel klasörde (`~/PEMF Vet/Seans CSV`) — klasörü açan
  // eylem (yalnız backend'in kendi bilgisayarında; sunucu da yalnız cihazın kendi ekranından açar, uzak istemciye yalnız yolu söyler).
  const csvKlasorunuAc = async () => {
    const r = await apiPost<{ status: string; yol?: string } | null>("/history/seans_csv_klasoru/ac", {}, null);
    if (r?.status === "success") showToast(t("seans.gecmis.csvKlasoruAcildi", { yol: r.yol ?? "" }), "success");
    else if (r?.status === "uzak") showToast(t("seans.gecmis.csvKlasoruUzak", { yol: r.yol ?? "" }), "info");
    else showToast(t("seans.gecmis.csvKlasoruAcilamadi"), "error");
  };

  const fetchHistory = async () => {
    setLoading(true);
    setLoadError(false);
    const data = await apiGet<any[] | null>(`/history/?limit=${PAGE_SIZE}`, null);
    setToplamSeans(null);
    if (Array.isArray(data) && data.length === PAGE_SIZE) {
      apiGet<{ total_sessions?: number } | null>("/history/statistics", null).then((s) =>
        setToplamSeans(typeof s?.total_sessions === "number" ? s.total_sessions : null),
      );
    }
    // ŞEKİL DOĞRULAMASI: `null` kontrolü tek başına yetmez — backend/proxy dizi OLMAYAN bir 2xx
    // gövdesi (ör. `{detail: ...}`, captive-portal yanıtı) dönerse `sessions.filter` TypeError
    // atıp ekranı beyaza düşürüyordu. Diziden başkasını "veri yok" say.
    if (!Array.isArray(data)) {
      setLoadError(true);
      setSessions([]);
      setHasMore(false);
    } else {
      setSessions(data);
      setHasMore(data.length === PAGE_SIZE);  // tam sayfa → daha fazlası olabilir
    }
    setLoading(false);
  };

  // audit B-8.2: sonraki sayfa — cursor = yüklü SON seansın id'si (keyset). Büyük geçmişte yalnız
  // en yeni sayfayla sınırlı kalmadan tüm kayıtlara sayfalayarak eriş (offset yavaşlığı/kayması yok).
  const loadMore = async () => {
    // `loading` de kapıya dahil: tam yenileme uçarken sayfalama basılırsa, eski listenin son
    // id'siyle istenen sayfa yenileme bittikten SONRA eklenir → kopuk/yinelenen kayıtlar.
    if (loading || loadingMore || !hasMore || sessions.length === 0) return;
    setLoadingMore(true);
    const lastId = sessions[sessions.length - 1]?.id;
    const data = await apiGet<any[] | null>(`/history/?limit=${PAGE_SIZE}&cursor=${lastId}`, null);
    if (Array.isArray(data) && data.length > 0) {
      setSessions((prev) => [...prev, ...data]);
      setHasMore(data.length === PAGE_SIZE);
    } else {
      setHasMore(false);
    }
    setLoadingMore(false);
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const filteredSessions = sessions.filter((s) => {
    // "Benim Seanslarım" = operator_email eşleşen VEYA sahipsiz (eski/migrasyon) kayıtlar → hiçbiri kaybolmaz.
    // ⚠️ D2.70 (B-6.19 · Y103): kural burada KENDİ kopyasıyla yazılıydı (`scope === "mine" && myEmail`) — kimlik düşünce
    // tüm kliniğin seansları "Benim" görünüyordu. TEK KAYNAK `inScope`: kimliksizken kayıt yok (fail-closed).
    if (!inScope(s, scope, myEmail)) return false;
    // ⚠️ DENETİM 2026-08-17: ham `toLowerCase()` Türkçe'de İ→'i'+U+0307 ürettiği için "İpek"
    // kaydı "ipek" ile aranınca bulunamıyordu. BURADAKİ ETKİ EN AĞIRI: süzme yalnız YÜKLENMİŞ
    // sayfalar üzerinde çalışır, dolayısıyla hekim "bu hastanın geçmişi yok" sonucuna varıyor ve
    // PDF/CSV dışa aktarımı `filteredSessions` üzerinden gittiği için BOŞ/EKSİK rapor üretiliyordu.
    return (
      aramaEslesir(s.patient_name, searchQuery) ||
      aramaEslesir(s.patient_notes, searchQuery) ||
      aramaEslesir(s.session_date, searchQuery)
    );
  });

  // "Tümünü PDF İndir" EKRANDA GÖRÜNEN (aktif filtre) kayıtları verir — eskiden filtreyi yok
  // sayıp tüm seansları alıyordu. Ayrıca çok kayıtta uzun URL 414 vermesin diye üst sınır.
  const downloadAllPdf = async () => {
    const list = filteredSessions;
    if (list.length === 0) return;
    // KAPSAM UYARISI: "Tümünü PDF İndir" adına rağmen YALNIZ o an EKRANA YÜKLENMİŞ sayfaları
    // aktarıyor (geçmiş sayfalanarak gelir, ilk sayfa 50 kayıt). Kullanıcı 500 seansı olan bir
    // klinikte "tümü" sanıp 50 kayıtlık rapor alıyor ve bunu fark etmiyordu. Daha yüklenmemiş
    // kayıt varsa AÇIKÇA söyle ve onay iste.
    if (hasMore) {
      const go = await platformConfirm(
        t("seans.gecmis.yalnizYuklenen"),
        t("seans.gecmis.yuklenenOnayRapor", { yuklenen: sessions.length, liste: list.length }),
        t("seans.gecmis.yuklenenleriAktar")
      );
      if (!go) return;
    }
    if (list.length > PDF_MAX) {
      platformAlert(t("seans.gecmis.cokKayit"), t("seans.gecmis.pdfSinir", { adet: list.length, enCok: PDF_MAX }));
    }
    const sessionIds = list.slice(0, PDF_MAX).map(s => s.id).join(",");
    downloadFileWithAuth(`${serviceConfig.apiBaseUrl}/history/export_pdf?session_ids=${sessionIds}`, `PEMF_Rapor_${list.length}_seans.pdf`, showToast);
  };

  // KVKK (#49): CSV artık aktif KAPSAM+ARAMA'yı onurlandırır (eskiden filtreyi yok sayıp TÜM
  // kliniğin PII'sini döküyordu). "Benim Seanslarım" veya arama aktifse yalnız GÖRÜNEN kayıtları
  // gönder; "Tüm Klinik" + aramasız ise operatör bilinçli tam-export istemiştir (parametresiz).
  // CSV_MAX: URL 414 olmasın; aşımda uyar + kırp (PDF deseniyle tutarlı) — sınırlar `treatmentHistorySinirlari` (KP-5 · 8).

  /**
   * ⚠️ DÜĞME ETİKETİ GERÇEĞİ SÖYLEMELİ (denetim 2026-09-12).
   *
   * Sahip "Excel/CSV İndir"in başına "tamamını" eklenmesini istedi. Ama varsayılan kapsam
   * "Benim Seanslarım" olduğu için düğme aslında EKRANDA GÖRÜNEN alt kümeyi indiriyor —
   * sabit "Tümünü" yazısı o hâlde YALAN olurdu. (Aynı yanlış "Tümünü PDF İndir"de zaten
   * vardı: kod yorumu bile "EKRANDA GÖRÜNEN kayıtları verir" diyor.)
   *
   * Operatör 200 seansı olan bir klinikte "Tümünü" yazan düğmeye basıp 12 kayıtlık dosya
   * alıyor ve bunu FARK ETMİYORDU. Etiket artık kapsamı izler; "Tümünü" yalnız gerçekten
   * tümü indirildiğinde yazar.
   *
   * ⚠️ KURAL `downloadCsv` İÇİNDEKİYLE BİREBİR AYNI KAYNAKTAN: ayrışırsa etiket bir şey der,
   * indirme başka şey yapar.
   */
  // ⚠️ B2-3.4 (2-B incelemesi): KİMLİKSİZKEN de daraltılmış (Y103 · D2.70) — kilitten sonra `scope` "all" kalınca id listesiz
  // istek kliniğin TÜM seans geçmişini (hasta adı, not) indiriyordu; liste boşken döküm dolu. Kural 2'de `myEmail` = oturum.
  const kapsamDaraltilmis = !myEmail || scope === "mine" || searchQuery.trim().length > 0;

  const downloadCsv = async () => {
    const filtered = kapsamDaraltilmis;
    let url = `${serviceConfig.apiBaseUrl}/history/export_csv`;
    if (filtered) {
      const list = filteredSessions;
      if (list.length === 0) { showToast(t("seans.gecmis.disaAktarilacakYok"), "error"); return; }
      // Filtreli CSV, id listesiyle gider → yalnız YÜKLENMİŞ kayıtları kapsar (aynı kapsam
      // sorunu PDF'te olduğu gibi). Filtresiz dal sunucu-tarafı tam export yaptığı için etkilenmez.
      if (hasMore) {
        const go = await platformConfirm(
          t("seans.gecmis.yalnizYuklenen"),
          t("seans.gecmis.yuklenenOnayCsv", { adet: list.length }),
          t("seans.gecmis.yuklenenleriAktar")
        );
        if (!go) return;
      }
      if (list.length > CSV_MAX) {
        platformAlert(t("seans.gecmis.cokKayit"), t("seans.gecmis.csvSinir", { adet: list.length, enCok: CSV_MAX }));
      }
      url += `?session_ids=${list.slice(0, CSV_MAX).map(s => s.id).join(",")}`;
    }
    downloadFileWithAuth(url, "PEMF_Gecmis.csv", showToast);
  };



  // ── TOPLU SİLME (sahip bildirimi 2026-09-12) ──────────────────────────────────
  // ⚠️ Seçim YALNIZ EKRANDA GÖRÜNEN kayıtlara kapanır (bkz. useCokluSecim "hayalet seçim"):
  // operatör seçtikten sonra aramayı/kapsamı değiştirirse, artık göremediği kayıtlar silinmez.
  const secim = useCokluSecim<number>(filteredSessions.map((s) => s.id));
  // YS2 e (B8): "20 seans"; süzgeç / arama / yüklenmemiş sayfa varsa "x / y seans gösteriliyor". Kimliksizken (kayıt gösterilmez,
  // Y103) sayı da yazılmaz.
  const toplam = toplamSeans ?? (hasMore ? null : sessions.length);
  const sayacMetni =
    !myEmail || toplam == null
      ? null
      : filteredSessions.length === toplam
        ? t("seans.gecmis.toplamSeans", { count: toplam })
        : t("seans.gecmis.gosterilenSeans", { gosterilen: filteredSessions.length, count: toplam });
  const [siliniyor, setSiliniyor] = useState(false);

  const secilenleriSil = async () => {
    const secilenler = secim.seciliKimlikler;
    if (secilenler.length === 0 || siliniyor) return;
    // ⚠️ D2.72 (B-6.26 · Y92): istek YALNIZ silinebilen (kendi) seanslarla gider; dışarıda kalanların SAYISI onayda
    // söylenir. Eskiden "Tüm Klinik → Tümünü Seç" başka hekimlerin seans kayıtlarını (tıbbi kayıt) isteğe koyuyordu.
    if (!myEmail) { showToast(kimlikIstemi(silmeKimlikIstemiMetni(), kimlikDbOkunamiyor), "error"); return; }
    const kimlikler = secilenler.filter((k) => {
      const kayit = sessions.find((x) => x.id === k);
      return !!kayit && silinebilir(kayit, silmeBaglami);
    });
    if (kimlikler.length === 0) { showToast(baskaHekimSilmeMetni(), "error"); return; }
    const ok = await platformConfirm(
      t("seans.gecmis.topluSilBaslik"),
      t("seans.gecmis.topluSilGovde", { adet: kimlikler.length, not: silinmeyecekNotu(secilenler.length - kimlikler.length) }),
      t("ortak.sil"),
    );
    if (!ok) return;
    setSiliniyor(true);
    // ⚠️ TEK İSTEK: N ayrı silme isteği yarı yolda koparsa operatör hangi kayıtların gittiğini
    // bilemezdi. Sunucu hepsini tek transaction'da siler (bkz. servers/history_router.delete_bulk).
    const res = await apiPost<{ status: string; silinen?: number; istenen?: number }>(
      "/history/delete_bulk",
      { session_ids: kimlikler, confirm: TOPLU_SILME_ONAYI },
      { status: "error" },
    );
    setSiliniyor(false);
    if (res.status === "success") {
      // ⚠️ İSTENEN ile SİLİNEN AYRI raporlanır: başka bir operatör aynı kaydı bu arada silmiş
      // olabilir. "5 silindi" demek yerine sunucunun söylediği gerçeği göster.
      const n = res.silinen ?? kimlikler.length;
      showToast(
        n === kimlikler.length ? t("seans.gecmis.silindi", { count: n }) : t("seans.gecmis.silindiKismi", { n, adet: kimlikler.length }),
        "success",
      );
      secim.temizle();
      fetchHistory();
    } else {
      showToast(t("hasta.sil.topluBasarisizKisa"), "error");
    }
  };


  return (
    <View style={{ width: "100%", maxWidth: layoutMax.icerik, alignSelf: "center" }}>
  {/* [S4 adım 3] İç dikey ScrollView KALDIRILDI: kabuk (AppShell) zaten tek kaydırıcı ve
  keyboardShouldPersistTaps='handled' taşıyor. İç ScrollView'ın yükseklik sınırı
  olmadığı için kendi kaydırmasını hiç üretmiyordu; ama klavye açıkken dokunuşu
  yutup 'Kaydet/Bağlan' düğmelerini İKİ dokunuş gerektiriyordu. */}
      <View style={styles.headerRow}>
        <Text style={styles.intro}>{SK.seansGecmisiGiris}</Text>
        <View style={{flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm}}>
          <TouchableOpacity
            style={[styles.btnOutline, secim.secimModu && styles.btnOutlineAktif]}
            onPress={secim.secimModunuDegistir}
            accessibilityRole="button"
            accessibilityLabel={t("seans.gecmis.secimKipiEtiketi")}
            testID="gecmis-secim-kipi"
          >
            <Text style={styles.btnOutlineText}>{secim.secimModu ? t("hasta.liste.secimiKapat") : t("hasta.liste.sec")}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btnOutline} onPress={downloadCsv}>
            <Text style={styles.btnOutlineText}>{kapsamDaraltilmis ? t("seans.gecmis.csvGorunen") : t("seans.gecmis.csvTumu")}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btnPrimary} onPress={downloadAllPdf}>
            <Text style={styles.btnPrimaryText}>{kapsamDaraltilmis ? t("seans.gecmis.pdfGorunen") : t("seans.gecmis.pdfTumu")}</Text>
          </TouchableOpacity>
          {backendBuMakinede() ? (
            <TouchableOpacity
              style={[styles.btnOutline, { minHeight: touch.min, justifyContent: "center" }]}
              onPress={csvKlasorunuAc}
              accessibilityRole="button"
              accessibilityLabel={t("seans.gecmis.csvKlasoruEtiketi")}
              testID="gecmis-csv-klasoru"
            >
              <Text style={styles.btnOutlineText}>{t("seans.gecmis.csvKlasoru")}</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      </View>

      {myEmail ? (
        <View style={styles.segment}>
          <TouchableOpacity style={[styles.segmentBtn, scope === "mine" && styles.segmentBtnActive]} onPress={() => setScope("mine")} accessibilityLabel={t("seans.gecmis.benimEtiket")}>
            <Text style={[styles.segmentText, scope === "mine" && styles.segmentTextActive]} numberOfLines={1}>{t("seans.gecmis.benim")}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.segmentBtn, scope === "all" && styles.segmentBtnActive]} onPress={() => setScope("all")} accessibilityLabel={t("seans.gecmis.tumKapsamEtiketi", { tumKapsamKucuk: SK.tumKapsamKucuk })}>
            <Text style={[styles.segmentText, scope === "all" && styles.segmentTextActive]} numberOfLines={1}>{SK.tumKapsam}</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      <View style={styles.searchBox}>
        <TextInput
          style={styles.searchInput}
          placeholder={SK.gecmisAraYer}
          placeholderTextColor={colors.textMuted}
          value={searchQuery}
          onChangeText={setSearchQuery}
        />
      </View>

      {!loading && !loadError && sayacMetni ? (
        <Text style={styles.sayac} testID="gecmis-sayac">{sayacMetni}</Text>
      ) : null}

      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : loadError ? (
        <View style={{ alignItems: "center", gap: spacing.md, marginTop: spacing.xl }}>
          <Text style={[styles.intro, { flex: undefined }]}>{t("seans.gecmis.yuklenemedi")}</Text>
          <TouchableOpacity style={styles.btnOutline} onPress={fetchHistory}>
            <Text style={styles.btnOutlineText}>{t("ortak.tekrarDene")}</Text>
          </TouchableOpacity>
        </View>
      ) : filteredSessions.length === 0 ? (
        <Text style={[styles.intro, { marginTop: spacing.md, flex: undefined, textAlign: "center" }]}>
          {!myEmail
            ? kimlikIstemi(kimlikIstemiMetni(), kimlikDbOkunamiyor)
            : searchQuery
            ? (hasMore
                ? t("seans.gecmis.eslesmeYok")
                : t("hasta.liste.aramaBos"))
            : t("seans.gecmis.kayitYok")}
        </Text>
      ) : (
        <>
          {/* ⚠️ `gizliSayi`: geçmiş sayfalanarak gelir; yüklenmemiş kayıt varsa "Tümünü Seç"
              onları KAPSAMAZ. Sunucu toplam sayıyı vermiyor → gerçek sayı bilinmiyor; 1
              vererek "daha var" bilgisini veriyoruz. Uydurma bir sayı yazmak daha kötü olurdu
              (şerit "137 kayıt ekranda değil" der, oysa 3 olabilir). */}
          {secim.secimModu ? (
            <SecimCubugu
              seciliSayi={secim.seciliSayi}
              hepsiSecili={secim.hepsiSecili}
              onTumunuSec={secim.tumunuSec}
              onTemizle={secim.temizle}
              onSil={secilenleriSil}
              onVazgec={secim.secimModunuDegistir}
              siliniyor={siliniyor}
              gizliSayi={hasMore ? 1 : 0}
              testID="gecmis-secim-cubugu"
            />
          ) : null}
          <ResponsiveGrid minItemWidth={360}>
            {filteredSessions.map((session) => (
              <SessionCard
                key={session.id}
                session={session}
                onRefresh={fetchHistory}
                onOpenDetails={() => setSelectedSessionId(session.id)}
                silmeEngeli={silmeEngeli(session)}
                secimModu={secim.secimModu}
                secili={secim.secilimi(session.id)}
                onSecimDegistir={() => secim.degistir(session.id)}
              />
            ))}
          </ResponsiveGrid>
        </>
      )}

      {hasMore && (
        <TouchableOpacity
          style={styles.loadMoreBtn}
          onPress={loadMore}
          disabled={loading || loadingMore}
          accessibilityRole="button"
          accessibilityLabel={t("seans.gecmis.dahaFazlaEtiket")}
        >
          {loadingMore
            ? <ActivityIndicator color={colors.primary} />
            : <Text style={styles.loadMoreText}>{t("seans.gecmis.dahaFazla")}</Text>}
        </TouchableOpacity>
      )}

      <SessionDetailModal
        visible={selectedSessionId !== null}
        sessionId={selectedSessionId}
        onClose={() => setSelectedSessionId(null)}
        adsizAd={SK.sahipsizKayit}
        bildir={showToast}
      />
    </View>
  );
}

function SessionCard({
  session,
  onRefresh,
  onOpenDetails,
  silmeEngeli = null,
  secimModu = false,
  secili = false,
  onSecimDegistir,
}: {
  session: any;
  onRefresh: () => void;
  onOpenDetails: () => void;
  /** D2.72 · Y92: dolu ise bu kayıt bu kimlikle SİLİNEMEZ — tekil silme istek göndermez, metni gösterir. */
  silmeEngeli?: string | null;
  secimModu?: boolean;
  secili?: boolean;
  onSecimDegistir?: () => void;
}) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  // ODD B-4: adı olmayan kayıt araştırmada "Sahipsiz örnek" (petri / fantom seansı "Bilinmeyen Hasta" görünüyordu).
  const { isResearcher: arastirmaci } = useUserMode();
  const adsiz = profilSozlugu({ researcher: !!arastirmaci }).sahipsizKayit;
  const [isEditingNotes, setIsEditingNotes] = useState(false);
  const [notes, setNotes] = useState(session.patient_notes || "");
  // VERİ KAYBI: `notes` yalnız İLK render'da başlatılıyordu. Liste yenilendiğinde (aynı `key`,
  // güncellenmiş `patient_notes`) yerel değer BAYAT kalıyor; kullanıcı kaydettiğinde başka bir
  // operatörün aynı seansa yazdığı notu sessizce EZİYORDU. Sunucu değeri değişince (ve kullanıcı
  // o an düzenlemiyorsa) yerel state'i tazele.
  useEffect(() => {
    if (!isEditingNotes) setNotes(session.patient_notes || "");
    // isEditingNotes BİLEREK hariç: düzenleme sırasında gelen yenileme kullanıcının yazdığını silmesin.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.patient_notes]);
  const s = session.session_status?.toLowerCase();
  let state: "online" | "warning" | "offline" = "offline";
  if (s === "completed") state = "online";
  else if (s === "active" || s === "running") state = "warning";
  else if (s === "interrupted" || s === "error" || s === "aborted_recovered") state = "offline";

  const downloadPdf = () => {
    downloadFileWithAuth(`${serviceConfig.apiBaseUrl}/history/export_pdf?session_ids=${session.id}`, `PEMF_Rapor_${session.patient_name || "hasta"}_${session.id}.pdf`, showToast);
  };

  const handleSaveNotes = async () => {
    const res = await apiPost<{status: string}>("/history/update_notes", { session_id: session.id, notes }, { status: "error" });
    if (res.status === "success") {
      setIsEditingNotes(false);
      showToast(t("seans.gecmis.notlarKaydedildi"), "success");
      onRefresh();
    } else {
      showToast(t("seans.gecmis.notlarKaydedilemedi"), "error");
    }
  };

  const handleDelete = async () => {
    if (silmeEngeli) { showToast(silmeEngeli, "error"); return; }   // D2.72 · Y92 (karar üst bileşende, tek kaynak)
    const ok = await platformConfirm(t("seans.gecmis.kaydiSilBaslik"), t("seans.gecmis.kaydiSilSorusu"), t("ortak.sil"));
    if (!ok) return;
    // ⚠️ D2.43 (B-2.7): olmayan seansın silinmesi artık 404 (eskiden 'success'). "Zaten silinmiş" bir HATA değildir —
    // başka bir cihaz/hekim az önce silmiş olabilir: söylenir ve liste yenilenir. Diğer hatalarda sunucunun gerekçesi.
    const hata = { durum: 0, detay: "" };
    const res = await apiPost<{status: string}>(
      "/history/delete",
      { session_id: session.id },
      { status: "error" },
      { silent: true, onHttpError: (durum, detay) => { hata.durum = durum; hata.detay = detay || ""; } },
    );
    if (res.status === "success") {
      showToast(t("seans.gecmis.seansSilindi"), "success");
      onRefresh();
    } else if (hata.durum === 404) {
      showToast(zatenSilinmisSeans(), "info");
      onRefresh();
    } else {
      showToast(hata.detay || t("seans.gecmis.silmeBasarisiz"), "error");
    }
  };

  return (
    <Card style={styles.card}>
      <View style={styles.row}>
        {/* ⚠️ SEÇİM KİPİNDE KART DOKUNUŞU SEÇER, DETAY AÇMAZ: iki eylemi aynı dokunuşa
            bindirmek, operatörün silmek için seçtiğini sanıp modal açmasına yol açardı. */}
        {secimModu ? (
          <TouchableOpacity
            style={[styles.onayKutusu, secili && styles.onayKutusuSecili]}
            onPress={onSecimDegistir}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: secili }}
            accessibilityLabel={t("seans.gecmis.secimEtiketi", { ad: session.patient_name || t("seans.gecmis.kayit") })}
            testID={`gecmis-secim-${session.id}`}
          >
            {secili ? <Check color={colors.white} size={16} /> : null}
          </TouchableOpacity>
        ) : null}
        <TouchableOpacity
          style={styles.titleArea}
          onPress={secimModu ? onSecimDegistir : onOpenDetails}
          accessibilityLabel={secimModu ? t("seans.gecmis.kaydiSec") : t("seans.gecmis.detayiAc")}
        >
          <Text style={styles.title} numberOfLines={1} ellipsizeMode="tail">{session.patient_name || adsiz}</Text>
          <Text style={styles.muted} numberOfLines={1} ellipsizeMode="tail">{seansTarihi(session)}</Text>
          {secimModu ? null : <Text style={styles.detailsHint} numberOfLines={1}>{t("seans.gecmis.bobinDetayi")}</Text>}
        </TouchableOpacity>
        <View style={{flexShrink: 1, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'flex-end', gap: spacing.sm}}>
          <StatusPill label={statusEtiketi(session.session_status, session.durdurma_nedeni)} state={state} />
          {/* ⚠️ SAHİP BİLDİRİMİ (2026-09-12): "paylaşım seçeneği ve pdf butonu aynı işi
              yapıyor seans başına. birini tutalım birini kaldır."
              ÖLÇÜLDÜ — DOĞRUYDU: `handleShareReport` ile `downloadPdf` AYNI uca, AYNI dosya
              adıyla gidiyordu; tek fark bir "hazırlanıyor" bildirimiydi. Paylaş ikonu,
              yapmadığı bir şeyi (ayrı bir paylaşım akışı) vaat ediyordu.
              ⚠️ MOBİLDE İŞLEV KAYBI YOK: `downloadFileWithAuth` native tarafta zaten
              `Sharing.shareAsync` ile paylaşım sayfasını açar — yani bu TEK düğme
              masaüstünde kaydeder, telefonda paylaşır. */}
          <TouchableOpacity style={styles.btnOutline} onPress={downloadPdf} accessibilityLabel={t("seans.gecmis.pdfEtiketi")}>
            <Text style={styles.btnOutlineText}>PDF</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.iconBtn}
            onPress={handleDelete}
            accessibilityRole="button"
            accessibilityLabel={t("seans.gecmis.kaydiSilEtiketi", { ad: session.patient_name || adsiz })}
          >
            <Trash2 color={colors.danger} size={18} />
          </TouchableOpacity>
        </View>
      </View>
      <View style={styles.detailGrid}>
        <Detail label={t("seans.detay.mod")} value={modEtiketi(t, session.treatment_mode || "") || "-"} />
        <Detail label={t("ai.pro.adim.hedef")} value={hedefEtiketi(t, session.target_condition || "") || "-"} />
        <Detail label={t("kontrol.sinir.sure")} value={t("seans.gecmis.sureDk", { sure: session.duration_minutes || 0 })} />
        <Detail label={t("kontrol.bobin.frekans")} value={`${session.frequency_hz || 0} Hz`} />
        {/* D1.89 · B-6.27: reçete CİHAZA GÖNDERİLMEZ → "(kayıt)"; reçetesiz seans "0 mT" değil "—". */}
        <Detail label={t("kontrol.yogunluk.kayit")} value={kayitYogunlugu(session.intensity_mt)} />
      </View>
      <View style={styles.notesContainer}>
        <View style={styles.notesHeader}>
          <Text style={styles.detailLabel}>{t("seans.gecmis.notlar")}</Text>
          {isEditingNotes ? (
             <View style={{flexDirection: 'row', gap: spacing.sm}}>
                <TouchableOpacity onPress={handleSaveNotes}><Text style={{color: colors.success, fontWeight: "bold"}}>{t("ayarlar.kaydet")}</Text></TouchableOpacity>
                <TouchableOpacity onPress={() => { setIsEditingNotes(false); setNotes(session.patient_notes || ""); }}><Text style={{color: colors.danger, fontWeight: "bold"}}>{t("ayarlar.iptal")}</Text></TouchableOpacity>
             </View>
          ) : (
            <TouchableOpacity onPress={() => setIsEditingNotes(true)}><Edit3 color={colors.textMuted} size={14} /></TouchableOpacity>
          )}
        </View>

        {isEditingNotes ? (
          <TextInput
            style={styles.notesInput}
            value={notes}
            onChangeText={setNotes}
            multiline
            placeholder={t("seans.gecmis.notPlaceholder")}
            placeholderTextColor={colors.textMuted}
          />
        ) : (
          <Text style={[styles.notesText, !session.patient_notes && {color: colors.textSubtle}]}>
            {session.patient_notes || t("seans.gecmis.notYok")}
          </Text>
        )}
      </View>
    </Card>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.detail}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.detailValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  segment: { flexDirection: "row", backgroundColor: colors.bgAlt, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: rs(4), gap: rs(4), marginBottom: spacing.md },
  segmentBtn: { flex: 1, paddingVertical: spacing.sm, borderRadius: rs(6), alignItems: "center", justifyContent: "center" },
  segmentBtnActive: { backgroundColor: colors.primary },
  segmentText: { color: colors.textMuted, fontSize: typography.caption, fontWeight: "700" },
  segmentTextActive: { color: colors.white },
  loadMoreBtn: {
    alignSelf: "center",
    marginTop: spacing.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xl,
    borderRadius: rs(10),
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: touch.min,
    justifyContent: "center",
    alignItems: "center",
  },
  loadMoreText: { color: colors.primary, fontWeight: "700", fontSize: typography.body },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.md,
    flexWrap: 'wrap',
    gap: spacing.sm
  },
  searchBox: {
    marginBottom: spacing.md,
    backgroundColor: colors.bgAlt,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm
  },
  searchInput: {
    color: colors.text,
    fontSize: typography.body,
  },
  sayac: { color: colors.textMuted, fontSize: typography.small, fontWeight: "600" },
  intro: {
    color: colors.textMuted,
    fontSize: typography.body,
    flex: 1,
    minWidth: rs(200)
  },
  card: {
    gap: spacing.md,
    marginBottom: spacing.md
  },
  row: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.md
  },
  titleArea: {
    flex: 1,
    minWidth: rs(0),
    flexShrink: 1
  },
  title: {
    color: colors.text,
    fontSize: typography.subtitle,
    fontWeight: "800"
  },
  detailsHint: {
    color: colors.primary,
    fontSize: typography.small,
    fontWeight: "700",
    marginTop: spacing.xs
  },
  muted: {
    color: colors.textMuted,
    fontSize: typography.caption,
    marginTop: spacing.xs
  },
  detailGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm
  },
  detail: {
    backgroundColor: colors.bgAlt,
    borderRadius: 8,
    minWidth: rs(100),
    flex: 1,
    padding: spacing.md
  },
  detailLabel: {
    color: colors.textMuted,
    fontSize: typography.small,
    fontWeight: "700"
  },
  detailValue: {
    color: colors.text,
    fontSize: typography.body,
    fontWeight: "800",
    marginTop: spacing.xs
  },
  notesContainer: {
    marginTop: spacing.xs,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.border
  },
  notesHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  notesText: {
    color: colors.text,
    fontSize: typography.small,
    marginTop: spacing.xs,
    fontStyle: 'italic'
  },
  notesInput: {
    color: colors.text,
    fontSize: typography.small,
    marginTop: spacing.xs,
    backgroundColor: colors.bg,
    borderRadius: 4,
    padding: spacing.xs,
    minHeight: rs(60),
    textAlignVertical: 'top'
  },
  btnPrimary: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center'
  },
  btnPrimaryText: {
    color: "#fff",
    fontWeight: "bold",
    fontSize: typography.small
  },
  btnOutline: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: colors.primary,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: 8
  },
  btnOutlineText: {
    color: colors.primary,
    fontWeight: "bold",
    fontSize: typography.small
  },
  iconBtn: {
    padding: spacing.xs
  },
  btnOutlineAktif: { backgroundColor: colors.bgAlt },
  // Seçim onay kutusu — dokunma hedefi `touch.min`den küçük OLAMAZ (kaza silmesi değil,
  // kaza SEÇİMİ riski; küçük hedef yanlış kaydı seçtirir).
  onayKutusu: {
    width: touch.min,
    height: touch.min,
    borderRadius: rs(6),
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
    marginRight: spacing.sm
  },
  onayKutusuSecili: { backgroundColor: colors.primary, borderColor: colors.primary }
});
