// Author: mertaygn, cglrgrkn
import { useEffect, useState } from "react";
import { StyleSheet, Text, TextInput, View, TouchableOpacity, ActivityIndicator } from "react-native";
import { PlusCircle, Search, User, CheckCircle, Edit, Trash2, Activity } from "lucide-react-native";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { colors, radius, spacing, typography, rs, layoutMax } from "@/theme/tokens";
import { apiGet, apiPost, platformConfirm } from "@/services/apiClient";
import { duzenlemePayloadu } from "@/utils/hastaGuncelleme";
import type { Patient } from "@/types/domain";
import { useToast } from "@/components/ui/ToastProvider";
import { useAppNav } from "@/context/AppNavContext";
import { useUserMode } from "@/context/UserModeContext";
import { useOperatorOptional } from "@/context/OperatorContext";
import { useAuth } from "@/context/AuthContext";
import { canAccess } from "@/config/access";
import { canChooseScope, effectiveScope, inScope } from "@/utils/patientScope";
import { aramaEslesir } from "@/utils/aramaNormalize";

export function PatientScreen() {
  const { showToast } = useToast();
  const { navigateTo, setSelectedPatient } = useAppNav();
  const { userMode, isExpert, isResearcher } = useUserMode();
  const { session } = useAuth();
  // ⚠️ DENETİM 2026-08-09 (Tier 1): kimlik AKTİF OPERATÖRDÜR, giriş e-postası değil.
  // Klinik tek Supabase hesabını paylaşıyor → her hasta aynı hesaba damgalanıyor ve
  // "Benim Hastalarım / Tüm Klinik" ayrımı (çoklu-operatör özelliğinin tüm amacı) anlamsız kalıyordu.
  const op = useOperatorOptional();
  const myEmail = (op ? op.operatorEmail : (session?.email || "")).toLowerCase();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  // Klinik-ici gorunum: "mine" = benim kaydettiklerim (+ sahipsiz eski kayitlar), "all" = tum klinik.
  const [scope, setScope] = useState<"mine" | "all">("mine");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
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
    const res = await apiGet<{ status: string, data: Patient[] }>("/patients", { status: "error", data: [] });
    // ŞEKİL DOĞRULAMASI: `data` dizi gelmezse aşağıdaki `.filter`/`.map` çöker.
    if (res.status === "success" && Array.isArray(res.data)) {
      setPatients(res.data);
    } else {
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
      showToast("Lütfen Hasta Adı ve Türü alanlarını doldurun.", "error");
      return;
    }

    // Validasyon — TR ondalık virgülünü kabul et (3,5 → 3.5).
    const ageN = Number(String(form.age).replace(",", "."));
    const weightN = Number(String(form.weight).replace(",", "."));
    if (form.age && (isNaN(ageN) || ageN < 0 || ageN > 50)) {
      showToast("Yaş 0–50 aralığında sayısal olmalıdır.", "error");
      return;
    }
    if (form.weight && (isNaN(weightN) || weightN < 0 || weightN > 200)) {
      showToast("Kilo 0–200 kg aralığında sayısal olmalıdır.", "error");
      return;
    }
    // E-posta opsiyonel; girildiyse basit format kontrolü (rapor gönderimi için).
    if (form.owner_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.owner_email.trim())) {
      showToast("Geçerli bir sahip e-posta adresi girin (örn: ad@ornek.com).", "error");
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
      showToast(`Hasta başarıyla ${editingId ? "güncellendi" : "kaydedildi"}.`, "success");
    } else {
      showToast("İşlem sırasında bir hata oluştu.", "error");
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
    // platformConfirm = web-güvenli onay. (Alert.alert çoklu-buton WEB'de tetiklenmez → "Sil" onPress
    // hiç çalışmıyor, istek gitmiyordu → "hasta silme çalışmıyor". window.confirm'e düşer.)
    if (!(await platformConfirm("Hasta Sil", "Bu hastayı silmek istediğinizden emin misiniz?", "Sil"))) return;
    // Sunucu: POST /api/patients/{id}/delete (Expo-uyumlu) veya DELETE /api/patients/{id}.
    const res = await apiPost<{ status: string }>(`/patients/${id}/delete`, {}, { status: "error" });
    if (res.status === "success" || res.status === undefined) {
      showToast("Hasta silindi.", "success");
      loadPatients();
    } else {
      showToast("Hasta silinemedi.", "error");
    }
  };

  const handleDeleteAll = async () => {
    if (!(await platformConfirm("Tüm Hastaları Sil", "Veritabanındaki TÜM HASTALARI silmek istediğinizden emin misiniz? Bu işlem geri alınamaz!", "Hepsini Sil"))) return;
    // Backend (audit B-8.2) kazara toplu-silmeye karşı confirm ister.
    const res = await apiPost<{ status: string }>(`/patients/delete_all`, { confirm: "DELETE_ALL" }, { status: "error" });
    if (res.status === "success") {
      showToast("Tüm hastalar silindi.", "success");
      loadPatients();
    } else {
      showToast("Toplu silme işlemi başarısız.", "error");
    }
  };

  const handleStartSession = (p: Patient) => {
    // Seçili hastayı paylaş + Kontrol ekranına git (orada seans bu hastayla başlar).
    setSelectedPatient({ id: p.id, name: p.name, species: p.species });
    showToast(`${p.name} için kontrol paneline gidiliyor.`, "success");
    navigateTo("control");
  };

  // "Benim Hastalarım" = operator_email eşleşen VEYA sahipsiz (eski/migrasyon) kayıtlar → hiçbir hasta kaybolmaz.
  // "Tüm Klinik" = filtresiz. Oturum yoksa (myEmail boş) filtreleme yapılmaz (hepsi).
  // KVKK: ev sahibi profili "all" kapsamına ASLA çıkamaz (sekme de gizli — bu ikinci kapı,
  // ileride başka bir yerden setScope("all") çağrılırsa diye). Mantık utils/patientScope.ts'te.
  const etkinScope = effectiveScope(scope, { isExpert, isResearcher });
  const scopedPatients = patients.filter(p => inScope(p, etkinScope, myEmail));
  const mineCount = patients.filter(p => {
    if (!myEmail) return false;
    const op = (p.operator_email || "").toLowerCase();
    return !op || op === myEmail;
  }).length;
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

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Hasta Veritabanı</Text>
        <View style={{flexDirection: 'row', gap: spacing.sm}}>
          {/* Güvenlik/KVKK (inceleme): "Tümünü Sil" paylaşılan hasta-DB'sini yıkar → yalnız VETERİNER (isExpert).
              Araştırma modu (PIN'li de olsa) tüm klinik kayıtlarını silememeli. */}
          {isExpert && (
            <Button
              label="Tümünü Sil"
              icon={<Trash2 color={colors.danger} size={16} />}
              variant="secondary"
              onPress={handleDeleteAll}
            />
          )}
          <Button
            label={isAdding ? "İptal" : "Yeni Hasta Kayıt"}
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
          <Text style={styles.formTitle}>{editingId ? "Hasta Bilgilerini Düzenle" : "Yeni Hasta Ekle"}</Text>
          <ResponsiveGrid minItemWidth={200}>
            <TextInput style={styles.input} accessibilityLabel="Hasta adı" placeholder="Hasta Adı (örn: Mia)" placeholderTextColor={colors.textMuted} value={form.name} onChangeText={t => setForm({...form, name: t})} />
            <TextInput style={styles.input} accessibilityLabel="Hayvan türü" placeholder="Türü (örn: Kedi)" placeholderTextColor={colors.textMuted} value={form.species} onChangeText={t => setForm({...form, species: t})} />
            <TextInput style={styles.input} accessibilityLabel="Irk" placeholder="Irkı" placeholderTextColor={colors.textMuted} value={form.breed} onChangeText={t => setForm({...form, breed: t})} />
            <TextInput style={styles.input} accessibilityLabel="Yaş" placeholder="Yaş (Sayı)" placeholderTextColor={colors.textMuted} value={form.age} onChangeText={t => setForm({...form, age: t})} keyboardType="numeric" />
            <TextInput style={styles.input} accessibilityLabel="Kilo (kg)" placeholder="Kilo (kg)" placeholderTextColor={colors.textMuted} value={form.weight} onChangeText={t => setForm({...form, weight: t})} keyboardType="numeric" />
            <TextInput style={styles.input} accessibilityLabel="Sahip adı" placeholder="Sahibi" placeholderTextColor={colors.textMuted} value={form.owner} onChangeText={t => setForm({...form, owner: t})} />
            <TextInput style={styles.input} accessibilityLabel="Veteriner iletişim telefonu" placeholder="Veteriner / İletişim (Tel)" placeholderTextColor={colors.textMuted} value={form.vet_contact} onChangeText={t => setForm({...form, vet_contact: t})} keyboardType="phone-pad" />
            <TextInput style={styles.input} accessibilityLabel="Sahip e-posta" placeholder="Sahip E-Posta (rapor için)" placeholderTextColor={colors.textMuted} value={form.owner_email} onChangeText={t => setForm({...form, owner_email: t})} keyboardType="email-address" autoCapitalize="none" autoCorrect={false} />
          </ResponsiveGrid>
          <View style={styles.saveBtn}>
            <Button label={saving ? "Kaydediliyor…" : editingId ? "Güncelle" : "Kaydet"} icon={<CheckCircle color={colors.white} size={16} />} onPress={handleAddOrEditPatient} disabled={saving} />
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
            accessibilityLabel="Benim hastalarım"
          >
            <Text style={[styles.segmentText, scope === "mine" && styles.segmentTextActive]} numberOfLines={1}>
              Benim Hastalarım{mineCount ? ` (${mineCount})` : ""}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.segmentBtn, scope === "all" && styles.segmentBtnActive]}
            onPress={() => setScope("all")}
            accessibilityLabel="Tüm klinik hastaları"
          >
            <Text style={[styles.segmentText, scope === "all" && styles.segmentTextActive]} numberOfLines={1}>
              Tüm Klinik ({patients.length})
            </Text>
          </TouchableOpacity>
        </View>
      ) : null}

      <View style={styles.searchBox}>
        <Search color={colors.textMuted} size={20} />
        <TextInput
          style={styles.searchInput}
          accessibilityLabel="Hasta veya sahip ara"
          placeholder="Hasta veya Sahip Ara..."
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
            <Text style={styles.emptyText}>Yükleniyor…</Text>
          </View>
        ) : loadError ? (
          <View style={styles.stateBox}>
            <Text style={styles.emptyText}>Hastalar yüklenemedi. Bağlantıyı kontrol edin.</Text>
            <Button label="Tekrar Dene" variant="secondary" onPress={loadPatients} />
          </View>
        ) : filteredPatients.length === 0 ? (
          <Text style={styles.emptyText}>{search ? "Aramayla eşleşen kayıt yok." : "Henüz hasta kaydı yok."}</Text>
        ) : (
          <ResponsiveGrid minItemWidth={340}>
            {filteredPatients.map((p) => (
              // key olarak p.id (idx değil) — silme/eklemede doğru DOM diff.
              <Card key={p.id || p.name} style={styles.patientCard}>
                <View style={styles.cardHeader}>
                  <View style={styles.headerLeft}>
                    <User color={colors.primary} size={24} />
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
                        accessibilityRole="button" accessibilityLabel={`${p.name} için seans başlat`}>
                        <Activity color={colors.success} size={20} />
                      </TouchableOpacity>
                    )}
                    <TouchableOpacity onPress={() => handleEdit(p)} style={styles.actionBtnIcon}
                      accessibilityRole="button" accessibilityLabel={`${p.name} kaydını düzenle`}>
                      <Edit color={colors.primary} size={20} />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => handleDelete(p.id!)} style={styles.actionBtnIcon}
                      accessibilityRole="button" accessibilityLabel={`${p.name} kaydını sil`}>
                      <Trash2 color={colors.danger} size={20} />
                    </TouchableOpacity>
                  </View>
                </View>
                <View style={styles.detailsRow}>
                  <Text style={styles.detailText} numberOfLines={1}>Sahip: <Text style={{fontWeight: "bold"}}>{p.owner || "Belirtilmemiş"}</Text></Text>
                  <Text style={styles.detailText}>Kilo: {p.weight || "-"} kg</Text>
                  <Text style={styles.detailText}>Yaş: {p.age || "-"}</Text>
                  {/* Tüm Klinik görünümünde kaydı hangi hekimin oluşturduğunu göster. */}
                  {etkinScope === "all" && p.operator_email ? (
                    <Text style={styles.detailText} numberOfLines={1}>Kaydeden: {p.operator_email}</Text>
                  ) : null}
                </View>
              </Card>
            ))}
          </ResponsiveGrid>
        )}

        {hiddenCount > 0 && (
          <TouchableOpacity
            style={styles.loadMoreBtn}
            onPress={() => setVisibleCount((n) => n + PAGE)}
            accessibilityRole="button"
            accessibilityLabel={`${hiddenCount} hasta daha göster`}
          >
            <Text style={styles.loadMoreText}>Daha fazla göster ({hiddenCount} kayıt)</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
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
  actionBtnIcon: { padding: spacing.xs, minWidth: rs(44), minHeight: rs(44), alignItems: "center", justifyContent: "center" }
});
