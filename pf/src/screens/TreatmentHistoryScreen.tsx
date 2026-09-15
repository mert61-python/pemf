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
import { downloadFileWithAuth } from "@/services/dosyaIndir";
import { useCokluSecim } from "@/hooks/useCokluSecim";
import { SecimCubugu } from "@/components/ui/SecimCubugu";
import { TOPLU_SILME_ONAYI } from "@/services/topluSilme";

// Backend ham seans durumlarını (İngilizce) görüntüleme için Türkçeye çevirir.
// NOT: Yalnızca gösterim amaçlıdır; backend ham değerleri (renk/durum mantığı) değiştirilmez.
const STATUS_LABELS_TR: Record<string, string> = {
  completed: "Tamamlandı",
  active: "Aktif",
  running: "Çalışıyor",
  in_progress: "Devam Ediyor",
  pending: "Bekliyor",
  stopped: "Durduruldu",
  interrupted: "Kesintiye Uğradı",
  aborted_recovered: "Kurtarıldı",
  cancelled: "İptal Edildi",
  canceled: "İptal Edildi",
  error: "Hata",
  failed: "Başarısız",
  success: "Başarılı",
  // ⚠️ ÜRETİMDE KULLANILAN AMA HARİTADA OLMAYAN İKİ DURUM (2026-09-12'de bulundu):
  // backend bunları gerçekten yazıyor (acil durdurma / güç kesintisi mutabakatı) ama
  // harita çeviremediği için ekranda ham "Emergency_stopped" görünüyordu.
  emergency_stopped: "Acil Durduruldu",
  aborted_due_to_power: "Elektrik Kesintisi",
  // ⚠️ Donanım komutu reddetti → seans HİÇ başlamadı. "Tamamlandı" yazmak,
  // uygulanmamış bir tedaviyi uygulanmış olarak belgelemek olurdu.
  hardware_rejected: "Donanım Reddetti"
};

function statusLabelTr(status?: string): string {
  if (!status) return "Bilinmiyor";
  const key = status.toLowerCase();
  if (STATUS_LABELS_TR[key]) return STATUS_LABELS_TR[key];
  // Bilinmeyen durumu en azından okunaklı göster (ilk harf büyük).
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function TreatmentHistoryScreen() {
  const { selectedPatient } = useAppNav();
  const { session } = useAuth();
  // ⚠️ DENETİM 2026-08-09 (Tier 1): "Benim Seanslarım" filtresi AKTİF OPERATÖRE göre olmalı.
  // Giriş e-postası kullanılınca paylaşılan hesaplı klinikte filtre ya hiçbir şey ya her şeyi
  // gösteriyordu — hekim kendi seansını bulamıyor, başkasınınkini kendi sanıyordu.
  const op = useOperatorOptional();
  const myEmail = (op ? op.operatorEmail : (session?.email || "")).toLowerCase();
  // Klinik-içi görünüm: "mine" = benim başlattığım seanslar (+ sahipsiz eski), "all" = tüm klinik.
  const [scope, setScope] = useState<"mine" | "all">("mine");
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

  const fetchHistory = async () => {
    setLoading(true);
    setLoadError(false);
    const data = await apiGet<any[] | null>(`/history/?limit=${PAGE_SIZE}`, null);
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
    if (scope === "mine" && myEmail) {
      const op = (s.operator_email || "").toLowerCase();
      if (op && op !== myEmail) return false;
    }
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
  const PDF_MAX = 200;
  const downloadAllPdf = async () => {
    const list = filteredSessions;
    if (list.length === 0) return;
    // KAPSAM UYARISI: "Tümünü PDF İndir" adına rağmen YALNIZ o an EKRANA YÜKLENMİŞ sayfaları
    // aktarıyor (geçmiş sayfalanarak gelir, ilk sayfa 50 kayıt). Kullanıcı 500 seansı olan bir
    // klinikte "tümü" sanıp 50 kayıtlık rapor alıyor ve bunu fark etmiyordu. Daha yüklenmemiş
    // kayıt varsa AÇIKÇA söyle ve onay iste.
    if (hasMore) {
      const go = await platformConfirm(
        "Yalnızca yüklenen kayıtlar",
        `Şu ana kadar ${sessions.length} seans yüklendi ve daha fazlası var. Rapor YALNIZ yüklenmiş ` +
        `${list.length} kaydı içerecek.\n\nTümünü almak için önce "Daha Fazla Yükle" ile listeyi tamamlayın.`,
        "Yüklenenleri aktar"
      );
      if (!go) return;
    }
    if (list.length > PDF_MAX) {
      platformAlert("Çok fazla kayıt", `${list.length} seans var; ilk ${PDF_MAX} tanesi PDF'e aktarılacak. Aramayı daraltın.`);
    }
    const sessionIds = list.slice(0, PDF_MAX).map(s => s.id).join(",");
    downloadFileWithAuth(`${serviceConfig.apiBaseUrl}/history/export_pdf?session_ids=${sessionIds}`, `PEMF_Rapor_${list.length}_seans.pdf`, showToast);
  };

  // KVKK (#49): CSV artık aktif KAPSAM+ARAMA'yı onurlandırır (eskiden filtreyi yok sayıp TÜM
  // kliniğin PII'sini döküyordu). "Benim Seanslarım" veya arama aktifse yalnız GÖRÜNEN kayıtları
  // gönder; "Tüm Klinik" + aramasız ise operatör bilinçli tam-export istemiştir (parametresiz).
  const CSV_MAX = 1000; // URL 414 olmasın; aşımda uyar + kırp (PDF deseniyle tutarlı).

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
  const kapsamDaraltilmis = scope === "mine" || searchQuery.trim().length > 0;
  const disaAktarimOneki = kapsamDaraltilmis ? "Görünenleri" : "Tümünü";

  const downloadCsv = async () => {
    const filtered = kapsamDaraltilmis;
    let url = `${serviceConfig.apiBaseUrl}/history/export_csv`;
    if (filtered) {
      const list = filteredSessions;
      if (list.length === 0) { showToast("Dışa aktarılacak kayıt yok.", "error"); return; }
      // Filtreli CSV, id listesiyle gider → yalnız YÜKLENMİŞ kayıtları kapsar (aynı kapsam
      // sorunu PDF'te olduğu gibi). Filtresiz dal sunucu-tarafı tam export yaptığı için etkilenmez.
      if (hasMore) {
        const go = await platformConfirm(
          "Yalnızca yüklenen kayıtlar",
          `Filtre aktif olduğu için dışa aktarım YALNIZ yüklenmiş ${list.length} kaydı içerecek; ` +
          `listede daha fazlası var.\n\nTümü için önce "Daha Fazla Yükle" ile listeyi tamamlayın.`,
          "Yüklenenleri aktar"
        );
        if (!go) return;
      }
      if (list.length > CSV_MAX) {
        platformAlert("Çok fazla kayıt", `${list.length} seans var; ilk ${CSV_MAX} tanesi CSV'ye aktarılacak. Aramayı daraltın.`);
      }
      url += `?session_ids=${list.slice(0, CSV_MAX).map(s => s.id).join(",")}`;
    }
    downloadFileWithAuth(url, "PEMF_Gecmis.csv", showToast);
  };



  // ── TOPLU SİLME (sahip bildirimi 2026-09-12) ──────────────────────────────────
  // ⚠️ Seçim YALNIZ EKRANDA GÖRÜNEN kayıtlara kapanır (bkz. useCokluSecim "hayalet seçim"):
  // operatör seçtikten sonra aramayı/kapsamı değiştirirse, artık göremediği kayıtlar silinmez.
  const secim = useCokluSecim<number>(filteredSessions.map((s) => s.id));
  const [siliniyor, setSiliniyor] = useState(false);

  const secilenleriSil = async () => {
    const kimlikler = secim.seciliKimlikler;
    if (kimlikler.length === 0 || siliniyor) return;
    const ok = await platformConfirm(
      "Seçili Kayıtları Sil",
      `${kimlikler.length} seans kaydı KALICI olarak silinecek. Bu işlem geri alınamaz.`,
      "Sil",
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
        n === kimlikler.length ? `${n} seans silindi.` : `${n}/${kimlikler.length} seans silindi.`,
        "success",
      );
      secim.temizle();
      fetchHistory();
    } else {
      showToast("Toplu silme başarısız.", "error");
    }
  };


  return (
    <View style={{ width: "100%", maxWidth: layoutMax.icerik, alignSelf: "center" }}>
  {/* [S4 adım 3] İç dikey ScrollView KALDIRILDI: kabuk (AppShell) zaten tek kaydırıcı ve
  keyboardShouldPersistTaps='handled' taşıyor. İç ScrollView'ın yükseklik sınırı
  olmadığı için kendi kaydırmasını hiç üretmiyordu; ama klavye açıkken dokunuşu
  yutup 'Kaydet/Bağlan' düğmelerini İKİ dokunuş gerektiriyordu. */}
      <View style={styles.headerRow}>
        <Text style={styles.intro}>Hastalarınıza ait geçmiş seans kayıtları ve raporlamalar.</Text>
        <View style={{flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm}}>
          <TouchableOpacity
            style={[styles.btnOutline, secim.secimModu && styles.btnOutlineAktif]}
            onPress={secim.secimModunuDegistir}
            accessibilityRole="button"
            accessibilityLabel="Toplu seçim kipini aç veya kapat"
            testID="gecmis-secim-kipi"
          >
            <Text style={styles.btnOutlineText}>{secim.secimModu ? "Seçimi Kapat" : "Seç"}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btnOutline} onPress={downloadCsv}>
            <Text style={styles.btnOutlineText}>{disaAktarimOneki} Excel/CSV İndir</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.btnPrimary} onPress={downloadAllPdf}>
            <Text style={styles.btnPrimaryText}>{disaAktarimOneki} PDF İndir</Text>
          </TouchableOpacity>
        </View>
      </View>

      {myEmail ? (
        <View style={styles.segment}>
          <TouchableOpacity style={[styles.segmentBtn, scope === "mine" && styles.segmentBtnActive]} onPress={() => setScope("mine")} accessibilityLabel="Benim seanslarım">
            <Text style={[styles.segmentText, scope === "mine" && styles.segmentTextActive]} numberOfLines={1}>Benim Seanslarım</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.segmentBtn, scope === "all" && styles.segmentBtnActive]} onPress={() => setScope("all")} accessibilityLabel="Tüm klinik seansları">
            <Text style={[styles.segmentText, scope === "all" && styles.segmentTextActive]} numberOfLines={1}>Tüm Klinik</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      <View style={styles.searchBox}>
        <TextInput
          style={styles.searchInput}
          placeholder="Hasta, Not veya Tarih ara..."
          placeholderTextColor={colors.textMuted}
          value={searchQuery}
          onChangeText={setSearchQuery}
        />
      </View>

      {loading ? (
        <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.xl }} />
      ) : loadError ? (
        <View style={{ alignItems: "center", gap: spacing.md, marginTop: spacing.xl }}>
          <Text style={[styles.intro, { flex: undefined }]}>Geçmiş yüklenemedi. Bağlantıyı kontrol edin.</Text>
          <TouchableOpacity style={styles.btnOutline} onPress={fetchHistory}>
            <Text style={styles.btnOutlineText}>Tekrar Dene</Text>
          </TouchableOpacity>
        </View>
      ) : filteredSessions.length === 0 ? (
        <Text style={[styles.intro, { marginTop: spacing.md, flex: undefined, textAlign: "center" }]}>
          {searchQuery
            ? (hasMore
                ? "Yüklü sayfalarda eşleşme yok — daha eski kayıtlarda olabilir, aşağıdan “Daha Fazla Yükle”."
                : "Aramayla eşleşen kayıt yok.")
            : "Geçmiş seans kaydı bulunamadı."}
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
          accessibilityLabel="Daha fazla geçmiş yükle"
        >
          {loadingMore
            ? <ActivityIndicator color={colors.primary} />
            : <Text style={styles.loadMoreText}>Daha Fazla Yükle</Text>}
        </TouchableOpacity>
      )}

      <SessionDetailModal
        visible={selectedSessionId !== null}
        sessionId={selectedSessionId}
        onClose={() => setSelectedSessionId(null)}
      />
    </View>
  );
}

function SessionCard({
  session,
  onRefresh,
  onOpenDetails,
  secimModu = false,
  secili = false,
  onSecimDegistir,
}: {
  session: any;
  onRefresh: () => void;
  onOpenDetails: () => void;
  secimModu?: boolean;
  secili?: boolean;
  onSecimDegistir?: () => void;
}) {
  const { showToast } = useToast();
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
      showToast("Notlar kaydedildi.", "success");
      onRefresh();
    } else {
      showToast("Notlar kaydedilemedi.", "error");
    }
  };

  const handleDelete = async () => {
    const ok = await platformConfirm("Kaydı Sil", "Bu seans kaydını silmek istediğinizden emin misiniz?", "Sil");
    if (!ok) return;
    const res = await apiPost<{status: string}>("/history/delete", { session_id: session.id }, { status: "error" });
    if (res.status === "success") {
      showToast("Seans silindi.", "success");
      onRefresh();
    } else {
      showToast("Silme işlemi başarısız.", "error");
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
            accessibilityLabel={`${session.patient_name || "Kayıt"} seçimi`}
            testID={`gecmis-secim-${session.id}`}
          >
            {secili ? <Check color={colors.white} size={16} /> : null}
          </TouchableOpacity>
        ) : null}
        <TouchableOpacity
          style={styles.titleArea}
          onPress={secimModu ? onSecimDegistir : onOpenDetails}
          accessibilityLabel={secimModu ? "Kaydı seç" : "Seans detayını aç"}
        >
          <Text style={styles.title} numberOfLines={1} ellipsizeMode="tail">{session.patient_name || "Bilinmeyen Hasta"}</Text>
          <Text style={styles.muted} numberOfLines={1} ellipsizeMode="tail">{session.session_date} {session.start_time}</Text>
          {secimModu ? null : <Text style={styles.detailsHint} numberOfLines={1}>Bobin detayını gör ›</Text>}
        </TouchableOpacity>
        <View style={{flexShrink: 1, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'flex-end', gap: spacing.sm}}>
          <StatusPill label={statusLabelTr(session.session_status)} state={state} />
          {/* ⚠️ SAHİP BİLDİRİMİ (2026-09-12): "paylaşım seçeneği ve pdf butonu aynı işi
              yapıyor seans başına. birini tutalım birini kaldır."
              ÖLÇÜLDÜ — DOĞRUYDU: `handleShareReport` ile `downloadPdf` AYNI uca, AYNI dosya
              adıyla gidiyordu; tek fark bir "hazırlanıyor" bildirimiydi. Paylaş ikonu,
              yapmadığı bir şeyi (ayrı bir paylaşım akışı) vaat ediyordu.
              ⚠️ MOBİLDE İŞLEV KAYBI YOK: `downloadFileWithAuth` native tarafta zaten
              `Sharing.shareAsync` ile paylaşım sayfasını açar — yani bu TEK düğme
              masaüstünde kaydeder, telefonda paylaşır. */}
          <TouchableOpacity style={styles.btnOutline} onPress={downloadPdf} accessibilityLabel="Seans raporunu PDF olarak al">
            <Text style={styles.btnOutlineText}>PDF</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.iconBtn} onPress={handleDelete}>
            <Trash2 color={colors.danger} size={18} />
          </TouchableOpacity>
        </View>
      </View>
      <View style={styles.detailGrid}>
        <Detail label="Mod" value={session.treatment_mode || "-"} />
        <Detail label="Hedef" value={session.target_condition || "-"} />
        <Detail label="Süre" value={`${session.duration_minutes || 0} dk`} />
        <Detail label="Frekans" value={`${session.frequency_hz || 0} Hz`} />
        <Detail label="Yoğunluk" value={`${session.intensity_mt || 0} mT`} />
      </View>
      <View style={styles.notesContainer}>
        <View style={styles.notesHeader}>
          <Text style={styles.detailLabel}>Notlar:</Text>
          {isEditingNotes ? (
             <View style={{flexDirection: 'row', gap: spacing.sm}}>
                <TouchableOpacity onPress={handleSaveNotes}><Text style={{color: colors.success, fontWeight: "bold"}}>Kaydet</Text></TouchableOpacity>
                <TouchableOpacity onPress={() => { setIsEditingNotes(false); setNotes(session.patient_notes || ""); }}><Text style={{color: colors.danger, fontWeight: "bold"}}>İptal</Text></TouchableOpacity>
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
            placeholder="Seans notu..."
            placeholderTextColor={colors.textMuted}
          />
        ) : (
          <Text style={[styles.notesText, !session.patient_notes && {color: colors.textSubtle}]}>
            {session.patient_notes || "Not eklenmemiş."}
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
