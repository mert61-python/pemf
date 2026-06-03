import { useEffect, useState } from "react";
import { StyleSheet, Text, TextInput, View, ScrollView } from "react-native";
import { PlusCircle, Search, User, CheckCircle } from "lucide-react-native";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { colors, radius, spacing, typography } from "@/theme/tokens";
import { apiGet, apiPost } from "@/services/apiClient";
import { useToast } from "@/components/ui/ToastProvider";

export function PatientScreen() {
  const { showToast } = useToast();
  const [patients, setPatients] = useState<any[]>([]);
  const [isAdding, setIsAdding] = useState(false);
  const [search, setSearch] = useState("");

  const [form, setForm] = useState({
    name: "", species: "", breed: "", age: "", weight: "", owner: "", vet_contact: ""
  });

  const loadPatients = async () => {
    const res = await apiGet<{ status: string, data: any[] }>("/patients", { status: "error", data: [] });
    if (res.status === "success") {
      setPatients(res.data);
    }
  };

  useEffect(() => {
    loadPatients();
  }, []);

  const handleAddPatient = async () => {
    if (!form.name || !form.species) {
      showToast("Lütfen Hasta Adı ve Türü alanlarını doldurun.", "error");
      return;
    }
    const res = await apiPost<{ status: string }>("/patients", form, { status: "error" });
    if (res.status === "success") {
      setIsAdding(false);
      setForm({ name: "", species: "", breed: "", age: "", weight: "", owner: "", vet_contact: "" });
      loadPatients();
      showToast("Hasta başarıyla veritabanına kaydedildi.", "success");
    } else {
      showToast("Kayıt sırasında bir hata oluştu.", "error");
    }
  };

  const filteredPatients = patients.filter(p => p.name.toLowerCase().includes(search.toLowerCase()) || p.owner.toLowerCase().includes(search.toLowerCase()));

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Hasta Veritabanı</Text>
        <Button 
          label={isAdding ? "İptal" : "Yeni Hasta Kayıt"} 
          icon={!isAdding ? <PlusCircle color={colors.white} size={16} /> : undefined}
          variant={isAdding ? "secondary" : "primary"}
          onPress={() => setIsAdding(!isAdding)} 
        />
      </View>

      {isAdding && (
        <Card style={styles.formCard}>
          <Text style={styles.formTitle}>Yeni Hasta Ekle</Text>
          <ResponsiveGrid minItemWidth={200}>
            <TextInput style={styles.input} placeholder="Hasta Adı (örn: Mia)" placeholderTextColor={colors.textMuted} value={form.name} onChangeText={t => setForm({...form, name: t})} />
            <TextInput style={styles.input} placeholder="Türü (örn: Kedi)" placeholderTextColor={colors.textMuted} value={form.species} onChangeText={t => setForm({...form, species: t})} />
            <TextInput style={styles.input} placeholder="Irkı" placeholderTextColor={colors.textMuted} value={form.breed} onChangeText={t => setForm({...form, breed: t})} />
            <TextInput style={styles.input} placeholder="Yaş" placeholderTextColor={colors.textMuted} value={form.age} onChangeText={t => setForm({...form, age: t})} />
            <TextInput style={styles.input} placeholder="Kilo (kg)" placeholderTextColor={colors.textMuted} value={form.weight} onChangeText={t => setForm({...form, weight: t})} />
            <TextInput style={styles.input} placeholder="Sahibi" placeholderTextColor={colors.textMuted} value={form.owner} onChangeText={t => setForm({...form, owner: t})} />
          </ResponsiveGrid>
          <Button label="Kaydet" icon={<CheckCircle color={colors.white} size={16} />} onPress={handleAddPatient} style={styles.saveBtn} />
        </Card>
      )}

      <View style={styles.searchBox}>
        <Search color={colors.textMuted} size={20} />
        <TextInput 
          style={styles.searchInput} 
          placeholder="Hasta veya Sahip Ara..." 
          placeholderTextColor={colors.textMuted}
          value={search}
          onChangeText={setSearch}
        />
      </View>

      <ScrollView contentContainerStyle={styles.list}>
        {filteredPatients.map((p, idx) => (
          <Card key={idx} style={styles.patientCard}>
            <View style={styles.cardHeader}>
              <User color={colors.primary} size={24} />
              <View>
                <Text style={styles.patientName}>{p.name}</Text>
                <Text style={styles.patientSub}>{p.species} · {p.breed}</Text>
              </View>
            </View>
            <View style={styles.detailsRow}>
              <Text style={styles.detailText}>Sahip: <Text style={{fontWeight: "bold"}}>{p.owner}</Text></Text>
              <Text style={styles.detailText}>Kilo: {p.weight} kg</Text>
              <Text style={styles.detailText}>Yaş: {p.age}</Text>
            </View>
          </Card>
        ))}
        {filteredPatients.length === 0 && <Text style={styles.emptyText}>Kayıt bulunamadı.</Text>}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, gap: spacing.lg },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  title: { color: colors.text, fontSize: typography.title, fontWeight: "800" },
  formCard: { gap: spacing.md, backgroundColor: colors.bgAlt, borderColor: colors.primarySoft, borderWidth: 1 },
  formTitle: { color: colors.primary, fontSize: typography.subtitle, fontWeight: "700" },
  input: { backgroundColor: colors.bg, color: colors.text, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  saveBtn: { marginTop: spacing.sm },
  searchBox: { flexDirection: "row", alignItems: "center", backgroundColor: colors.bgAlt, paddingHorizontal: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, height: 48, gap: spacing.sm },
  searchInput: { flex: 1, color: colors.text, fontSize: typography.body },
  list: { gap: spacing.md, paddingBottom: spacing.xl },
  patientCard: { gap: spacing.md },
  cardHeader: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  patientName: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800" },
  patientSub: { color: colors.textMuted, fontSize: typography.small, marginTop: 2 },
  detailsRow: { flexDirection: "row", gap: spacing.lg, backgroundColor: colors.bgAlt, padding: spacing.sm, borderRadius: radius.sm },
  detailText: { color: colors.textMuted, fontSize: typography.caption },
  emptyText: { color: colors.textMuted, textAlign: "center", marginTop: spacing.xl }
});
