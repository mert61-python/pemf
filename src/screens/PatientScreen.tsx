import { useEffect, useState } from "react";
import { StyleSheet, Text, TextInput, View, ScrollView, TouchableOpacity, Alert, ActivityIndicator } from "react-native";
import { PlusCircle, Search, User, CheckCircle, Edit, Trash2, Activity } from "lucide-react-native";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { colors, radius, spacing, typography, rs } from "@/theme/tokens";
import { apiGet, apiPost } from "@/services/apiClient";
import type { Patient } from "@/types/domain";
import { useToast } from "@/components/ui/ToastProvider";
import { useAppNav } from "@/context/AppNavContext";

export function PatientScreen() {
  const { showToast } = useToast();
  const { navigateTo, setSelectedPatient } = useAppNav();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState({
    id: "", name: "", species: "", breed: "", age: "", weight: "", owner: "", vet_contact: "", owner_email: ""
  });

  const loadPatients = async () => {
    setLoading(true);
    setLoadError(false);
    const res = await apiGet<{ status: string, data: Patient[] }>("/patients", { status: "error", data: [] });
    if (res.status === "success") {
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
    const payload = editingId ? { ...normalized, id: editingId } : normalized;
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
    setForm({
      id: p.id || "",
      name: p.name || "",
      species: p.species || "",
      breed: p.breed || "",
      age: p.age || "",
      weight: p.weight || "",
      owner: p.owner || "",
      vet_contact: p.vet_contact || "",
      owner_email: p.owner_email || ""
    });
    setEditingId(p.id ?? null);
    setIsAdding(true);
  };

  const handleDelete = (id: string) => {
    Alert.alert("Hasta Sil", "Bu hastası silmek istediğinizden emin misiniz?", [
      { text: "İptal", style: "cancel" },
      { 
        text: "Sil", 
        style: "destructive", 
        onPress: async () => {
          // Sunucu tarafında DELETE /api/patients/{id} endpoint'i kullanılıyor
          const res = await apiPost<{status: string}>(`/patients/${id}/delete`, {}, { status: "error" });
          if (res.status === "success" || res.status === undefined) {
            showToast("Hasta silindi.", "success");
            loadPatients();
          } else {
            showToast("Hasta silinemedi.", "error");
          }
        } 
      }
    ]);
  };

  const handleDeleteAll = () => {
    Alert.alert("Tüm Hastaları Sil", "Veritabanındaki TÜM HASTALARI silmek istediğinizden emin misiniz? Bu işlem geri alınamaz!", [
      { text: "İptal", style: "cancel" },
      { 
        text: "Hepsini Sil", 
        style: "destructive", 
        onPress: async () => {
          // Backend (audit B-8.2) kazara toplu-silmeye karşı confirm ister.
          const res = await apiPost<{status: string}>(`/patients/delete_all`, { confirm: "DELETE_ALL" }, { status: "error" });
          if (res.status === "success") {
            showToast("Tüm hastalar silindi.", "success");
            loadPatients();
          } else {
            showToast("Toplu silme işlemi başarısız.", "error");
          }
        } 
      }
    ]);
  };

  const handleStartSession = (p: Patient) => {
    // Seçili hastayı paylaş + Kontrol ekranına git (orada seans bu hastayla başlar).
    setSelectedPatient({ id: p.id, name: p.name, species: p.species });
    showToast(`${p.name} için kontrol paneline gidiliyor.`, "success");
    navigateTo("control");
  };

  const filteredPatients = patients.filter(p => (p.name || "").toLowerCase().includes(search.toLowerCase()) || (p.owner || "").toLowerCase().includes(search.toLowerCase()));

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Hasta Veritabanı</Text>
        <View style={{flexDirection: 'row', gap: spacing.sm}}>
          <Button 
            label="Tümünü Sil" 
            icon={<Trash2 color={colors.danger} size={16} />}
            variant="secondary"
            onPress={handleDeleteAll}
          />
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

      <ScrollView contentContainerStyle={styles.list}>
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
                    <TouchableOpacity onPress={() => handleStartSession(p)} style={styles.actionBtnIcon}><Activity color={colors.success} size={20} /></TouchableOpacity>
                    <TouchableOpacity onPress={() => handleEdit(p)} style={styles.actionBtnIcon}><Edit color={colors.primary} size={20} /></TouchableOpacity>
                    <TouchableOpacity onPress={() => handleDelete(p.id!)} style={styles.actionBtnIcon}><Trash2 color={colors.danger} size={20} /></TouchableOpacity>
                  </View>
                </View>
                <View style={styles.detailsRow}>
                  <Text style={styles.detailText} numberOfLines={1}>Sahip: <Text style={{fontWeight: "bold"}}>{p.owner || "Belirtilmemiş"}</Text></Text>
                  <Text style={styles.detailText}>Kilo: {p.weight || "-"} kg</Text>
                  <Text style={styles.detailText}>Yaş: {p.age || "-"}</Text>
                </View>
              </Card>
            ))}
          </ResponsiveGrid>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, gap: spacing.lg, width: "100%", maxWidth: rs(1100), alignSelf: "center" },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: spacing.md },
  title: { color: colors.text, fontSize: typography.title, fontWeight: "800", marginBottom: spacing.xs },
  formCard: { gap: spacing.md, backgroundColor: colors.bgAlt, borderColor: colors.primarySoft, borderWidth: 1 },
  formTitle: { color: colors.primary, fontSize: typography.subtitle, fontWeight: "700" },
  input: { backgroundColor: colors.bg, color: colors.text, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  saveBtn: { marginTop: spacing.sm },
  searchBox: { flexDirection: "row", alignItems: "center", backgroundColor: colors.bgAlt, paddingHorizontal: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, height: rs(48), gap: spacing.sm },
  searchInput: { flex: 1, color: colors.text, fontSize: typography.body },
  list: { gap: spacing.md, paddingBottom: spacing.xl },
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
  actionBtnIcon: { padding: spacing.xs }
});
