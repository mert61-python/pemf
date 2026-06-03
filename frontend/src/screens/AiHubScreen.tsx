import { useState } from "react";
import { StyleSheet, Text, View, Image, ScrollView, ActivityIndicator, TouchableOpacity, TextInput, Alert } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { Camera, Image as ImageIcon, Sparkles, Stethoscope, ScissorsSquare as Scan, Activity, Microscope, CheckCircle2 } from "lucide-react-native";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { colors, radius, spacing, typography } from "@/theme/tokens";
import { useToast } from "@/components/ui/ToastProvider";
import { apiPost } from "@/services/apiClient";
import { serviceConfig } from "@/services/config";
import { Platform } from "react-native";
import { useUserMode } from "@/context/UserModeContext";

type AiModule = "disease" | "landmark" | "segmentation" | "thermal" | "reticulocytes";

const SYMPTOMS = [
  "İştah Kaybı", "Kusma", "İshal", "Öksürük", "Solunum Güçlüğü", 
  "Topallık", "Deri Lezyonları", "Burun Akıntısı", "Göz Akıntısı", 
  "Halsizlik / Uyuşukluk", "Kilo Kaybı", "Hapşırma", "Dehidrasyon", "Ateş"
];

export function AiHubScreen() {
  const { isExpert } = useUserMode();
  const [activeModule, setActiveModule] = useState<AiModule>("landmark");

  if (!isExpert) {
    return <PetOwnerAiScreen />;
  }

  return (
    <View style={styles.container}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabContainer}>
        <TabButton icon={<Scan size={18} color={activeModule === "landmark" ? colors.primary : colors.textMuted}/>} label="Yüz Ağrısı (FGS)" active={activeModule === "landmark"} onPress={() => setActiveModule("landmark")} />
        <TabButton icon={<Stethoscope size={18} color={activeModule === "disease" ? colors.primary : colors.textMuted}/>} label="Hastalık" active={activeModule === "disease"} onPress={() => setActiveModule("disease")} />
        <TabButton icon={<Scan size={18} color={activeModule === "segmentation" ? colors.primary : colors.textMuted}/>} label="Segmentasyon" active={activeModule === "segmentation"} onPress={() => setActiveModule("segmentation")} />
        <TabButton icon={<Activity size={18} color={activeModule === "thermal" ? colors.primary : colors.textMuted}/>} label="Termal" active={activeModule === "thermal"} onPress={() => setActiveModule("thermal")} />
        <TabButton icon={<Microscope size={18} color={activeModule === "reticulocytes" ? colors.primary : colors.textMuted}/>} label="Retikülosit" active={activeModule === "reticulocytes"} onPress={() => setActiveModule("reticulocytes")} />
      </ScrollView>

      <ScrollView contentContainerStyle={styles.content}>
        {activeModule === "disease" && <DiseaseModule />}
        {activeModule === "landmark" && <VisionModule endpoint="/vision/landmark" title="Yüz Ağrısı Skoru (FGS)" subtitle="YOLO-pose modeli ile yüzdeki kilit noktaları analiz eder." />}
        {activeModule === "segmentation" && <VisionModule endpoint="/vision/segmentation" title="Kedi Segmentasyonu" subtitle="YOLOv8-seg modeli ile kedinin vücut sınırlarını tespit eder." />}
        {activeModule === "thermal" && <VisionModule endpoint="/vision/thermal" title="Termal Görüntü Analizi" subtitle="GhostNetV2 ile termal anormallikleri tespit eder." />}
        {activeModule === "reticulocytes" && <VisionModule endpoint="/vision/reticulocytes" title="Retikülosit Sayımı" subtitle="Mikroskop görüntüsünden hücreleri otomatik sayar." />}
      </ScrollView>
    </View>
  );
}

function PetOwnerAiScreen() {
  const { showToast } = useToast();
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [treatmentStatus, setTreatmentStatus] = useState<string>("");

  const takePhoto = async () => {
    let res = await ImagePicker.launchCameraAsync({ allowsEditing: true, quality: 0.7 });
    if (!res.canceled) { setImageUri(res.assets[0].uri); setResult(null); setTreatmentStatus(""); }
  };

  const pickImage = async () => {
    let res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: true, quality: 0.7 });
    if (!res.canceled) { setImageUri(res.assets[0].uri); setResult(null); setTreatmentStatus(""); }
  };

  const analyzeImage = async () => {
    if (!imageUri) return;
    setLoading(true);
    try {
      const formData = new FormData();
      if (Platform.OS === 'web') {
        const res = await fetch(imageUri);
        const blob = await res.blob();
        formData.append("file", blob, "camera_capture.jpg");
      } else {
        formData.append("file", { uri: imageUri, name: "camera_capture.jpg", type: "image/jpeg" } as any);
      }
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai/vision/landmark", {
        method: "POST",
        body: formData,
        headers: { "Accept": "application/json" }
      });
      const data = await response.json();
      if (response.ok && data.status === "success") {
        setResult(data);
      } else {
        showToast("Teşhis sırasında hata oluştu.", "error");
      }
    } catch (error) {
      showToast("Bağlantı hatası.", "error");
    } finally {
      setLoading(false);
    }
  };

  const startAutoTreatment = async () => {
    setTreatmentStatus("Otonom tedavi cihazlara iletiliyor...");
    const res = await apiPost<any>("/hardware/auto_preset", { target_condition: "pain" }, { status: "error" });
    if (res.status === "success") {
      setTreatmentStatus("Tedavi Başladı! Dostunuz güvende.");
    } else {
      setTreatmentStatus("Cihazla iletişim kurulamadı.");
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <Sparkles color={colors.primary} size={28} />
          <Text style={[styles.title, { fontSize: 24 }]}>Akıllı Teşhis Asistanı</Text>
        </View>
        <Text style={styles.subtitle}>Dostunuzun fotoğrafını çekin, yapay zeka anında ağrı ve stres durumunu analiz etsin. Gerekirse tek tuşla otomatik rahatlama terapisini başlatsın.</Text>

        {!imageUri ? (
          <View style={styles.actions}>
            <TouchableOpacity style={styles.bigActionBtn} onPress={takePhoto}>
              <Camera color="#fff" size={32} />
              <Text style={styles.bigActionText}>Kamerayı Aç</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryActionBtn} onPress={pickImage}>
              <ImageIcon color={colors.primary} size={24} />
              <Text style={styles.secondaryActionText}>Galeriden Seç</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={{ gap: spacing.lg, marginTop: spacing.md }}>
            <Image source={{ uri: imageUri }} style={styles.previewImage} resizeMode="contain" />
            <View style={{ flexDirection: 'row', gap: spacing.md }}>
              <Button style={{ flex: 1 }} variant="secondary" label="Yeni Fotoğraf" onPress={() => setImageUri(null)} />
              <Button style={{ flex: 1 }} variant="primary" label={loading ? "Analiz Ediliyor..." : "Teşhis Et"} onPress={analyzeImage} disabled={loading} icon={loading ? <ActivityIndicator color="#fff" /> : <Sparkles color="#fff" size={16} />} />
            </View>
          </View>
        )}

        {result && (
          <View style={styles.petOwnerResult}>
            <Text style={styles.petOwnerResultTitle}>Teşhis Sonucu</Text>
            <Text style={styles.body}>Ağrı Skoru (FGS): <Text style={{ fontWeight: 'bold' }}>{result.fgs_total} / 10</Text></Text>
            <Text style={styles.body}>Durum: <Text style={{ fontWeight: 'bold', color: result.fgs_total > 3 ? colors.danger : colors.success }}>{result.pain_level}</Text></Text>
            {result.fgs_total > 3 && (
              <View style={styles.recommendationBox}>
                <Text style={styles.recommendationText}>Dostumuzun hafif ağrısı var gibi görünüyor. PEMF terapi ile onu rahatlatabiliriz.</Text>
                <TouchableOpacity style={styles.startTherapyBtn} onPress={startAutoTreatment}>
                  <CheckCircle2 color="#fff" size={20} />
                  <Text style={styles.startTherapyText}>Otonom Tedaviyi Başlat</Text>
                </TouchableOpacity>
              </View>
            )}
            {treatmentStatus ? <Text style={[styles.statusText, { textAlign: 'center', marginTop: spacing.md }]}>{treatmentStatus}</Text> : null}
          </View>
        )}
      </Card>

      <View style={{ marginTop: spacing.xl }}>
        <DiseaseModule />
      </View>
    </ScrollView>
  );
}

function TabButton({ label, active, onPress, icon }: any) {
  return (
    <TouchableOpacity style={[styles.tabBtn, active && styles.tabBtnActive]} onPress={onPress}>
      {icon}
      <Text style={[styles.tabLabel, active && styles.tabLabelActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

function DiseaseModule() {
  const { showToast } = useToast();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any[] | null>(null);
  const [form, setForm] = useState({ age: "", weight: "", hr: "", temp: "", duration: "" });
  const [selectedSymptoms, setSelectedSymptoms] = useState<number[]>([]);

  const toggleSymptom = (idx: number) => {
    if (selectedSymptoms.includes(idx)) setSelectedSymptoms(selectedSymptoms.filter(i => i !== idx));
    else setSelectedSymptoms([...selectedSymptoms, idx]);
  };

  const analyze = async () => {
    if (selectedSymptoms.length < 2) {
      showToast("Lütfen en az 2 semptom seçin.", "error");
      return;
    }
    setLoading(true);
    const res = await apiPost<any>("/ai/disease", {
      age: parseFloat(form.age) || 0,
      weight: parseFloat(form.weight) || 0,
      hr: parseFloat(form.hr) || 0,
      temp: parseFloat(form.temp) || 0,
      duration: parseFloat(form.duration) || 0,
      symptom_indices: selectedSymptoms.map(i => i + 1)
    }, { status: "error" });
    setLoading(false);
    if (res.status === "success") setResult(res.results);
    else showToast("Analiz sırasında hata oluştu.", "error");
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>Kedi Hastalık Tahmini (XGBoost)</Text>
      <ResponsiveGrid minItemWidth={150}>
        <TextInput style={styles.input} placeholder="Yaş" keyboardType="numeric" value={form.age} onChangeText={t => setForm({...form, age: t})} />
        <TextInput style={styles.input} placeholder="Kilo" keyboardType="numeric" value={form.weight} onChangeText={t => setForm({...form, weight: t})} />
        <TextInput style={styles.input} placeholder="Nabız" keyboardType="numeric" value={form.hr} onChangeText={t => setForm({...form, hr: t})} />
        <TextInput style={styles.input} placeholder="Ateş" keyboardType="numeric" value={form.temp} onChangeText={t => setForm({...form, temp: t})} />
        <TextInput style={styles.input} placeholder="Süre" keyboardType="numeric" value={form.duration} onChangeText={t => setForm({...form, duration: t})} />
      </ResponsiveGrid>
      <View style={styles.symptomsGrid}>
        {SYMPTOMS.map((s, idx) => (
          <TouchableOpacity key={idx} style={[styles.symptomBtn, selectedSymptoms.includes(idx) && styles.symptomBtnActive]} onPress={() => toggleSymptom(idx)}>
            <Text style={[styles.symptomLabel, selectedSymptoms.includes(idx) && styles.symptomLabelActive]}>{s}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <Button style={styles.analyzeBtn} variant="primary" label={loading ? "Analiz Ediliyor..." : "Teşhisi Başlat"} onPress={analyze} disabled={loading} />
    </Card>
  );
}

function VisionModule({ endpoint, title, subtitle }: { endpoint: string, title: string, subtitle: string }) {
  const { showToast } = useToast();
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const takePhoto = async () => {
    let res = await ImagePicker.launchCameraAsync({ allowsEditing: true, quality: 0.8 });
    if (!res.canceled) setImageUri(res.assets[0].uri);
  };
  const pickImage = async () => {
    let res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: true, quality: 0.8 });
    if (!res.canceled) setImageUri(res.assets[0].uri);
  };

  const analyzeImage = async () => {
    if (!imageUri) return;
    setLoading(true);
    try {
      const formData = new FormData();
      if (Platform.OS === 'web') {
        const res = await fetch(imageUri);
        const blob = await res.blob();
        formData.append("file", blob, "upload.jpg");
      } else {
        formData.append("file", { uri: imageUri, name: "upload.jpg", type: "image/jpeg" } as any);
      }
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai" + endpoint, {
        method: "POST",
        body: formData,
        headers: { "Accept": "application/json" }
      });
      const data = await response.json();
      if (response.ok && data.status === "success") setResult(data);
      else showToast("Analiz sırasında hata oluştu.", "error");
    } catch (error) {
      showToast("Ağ veya sunucu hatası.", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.subtitle}>{subtitle}</Text>
      
      <View style={styles.imagePreviewContainer}>
        {imageUri ? (
          <Image source={{ uri: result?.image_base64 ? `data:image/jpeg;base64,${result.image_base64}` : imageUri }} style={styles.imagePreview} />
        ) : (
          <View style={styles.placeholderBox}>
            <ImageIcon color={colors.textMuted} size={48} />
            <Text style={styles.placeholderText}>Görüntü seçilmedi</Text>
          </View>
        )}
      </View>

      <View style={styles.btnRow}>
        <Button style={{ flex: 1 }} label="Galeriden Seç" icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} />
        <Button style={{ flex: 1 }} label="Fotoğraf Çek" icon={<Camera color={colors.white} size={16} />} onPress={takePhoto} />
      </View>

      <Button style={styles.analyzeBtn} variant="primary" label={loading ? "Analiz Ediliyor..." : "AI Analizini Başlat"} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={analyzeImage} />

      {result && (
        <View style={styles.resultBox}>
          <Text style={styles.resultTitle}>Analiz Sonucu:</Text>
          {result.pain_level && (() => {
            const painLevels: Record<string, string> = { "No Pain": "Ağrı Yok", "Mild Pain": "Hafif Ağrı", "Moderate Pain": "Orta Derece Ağrı", "Severe Pain": "Şiddetli Ağrı" };
            return <Text style={styles.resultText}>Ağrı Seviyesi: <Text style={{fontWeight:'bold', color: result.pain_level === "No Pain" ? colors.success : colors.danger}}>{painLevels[result.pain_level] || result.pain_level}</Text></Text>;
          })()}
          {result.fgs_total !== undefined && (
            <View>
              <Text style={styles.resultText}>FGS Skoru: <Text style={{fontWeight:'bold'}}>{result.fgs_total} / 10</Text></Text>
              {result.raw_fgs?.action_units && (
                <View style={{ marginTop: spacing.sm, paddingLeft: spacing.md, borderLeftWidth: 2, borderLeftColor: colors.primarySoft }}>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>• Kulak Pozisyonu: {result.raw_fgs.action_units["AU1_Ear_Position"]?.score ?? "-"}</Text>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>• Göz Kısma: {result.raw_fgs.action_units["AU2_Orbital_Tightening"]?.score ?? "-"}</Text>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>• Burun Kasılması: {result.raw_fgs.action_units["AU3_Muzzle_Tension"]?.score ?? "-"}</Text>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>• Bıyık Değişimi: {result.raw_fgs.action_units["AU4_Whisker_Position"]?.score ?? "-"}</Text>
                  <Text style={[styles.resultText, {fontSize: typography.small}]}>• Baş Pozisyonu: {result.raw_fgs.action_units["AU5_Head_Position"]?.score ?? "-"}</Text>
                </View>
              )}
            </View>
          )}
          {result.cat_count !== undefined && <Text style={styles.resultText}>Tespit Edilen Kedi: <Text style={{fontWeight:'bold'}}>{result.cat_count}</Text></Text>}
          {result.prediction && (() => {
             const lbl = result.prediction.label === "Sick" ? "Hasta (Riskli)" : "Sağlıklı";
             const prob = result.prediction.probability_sick !== undefined ? (result.prediction.probability_sick * 100).toFixed(1) : "?";
             return <Text style={styles.resultText}>Termal Tespit: <Text style={{fontWeight:'bold', color: result.prediction.label === "Sick" ? colors.danger : colors.success}}>{lbl}</Text> (Olasılık: %{prob})</Text>;
          })()}
          {result.counts && (
            <>
              <Text style={styles.resultText}>Eritrosit: {result.counts["erythrocyte"]}</Text>
              <Text style={styles.resultText}>Noktalı Retikülosit: {result.counts["punctate reticulocyte"]}</Text>
              <Text style={styles.resultText}>Agrege Retikülosit: {result.counts["aggregate reticulocyte"]}</Text>
            </>
          )}
        </View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  tabContainer: { flexDirection: "row", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm },
  tabBtn: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.full, backgroundColor: colors.bgAlt, gap: spacing.sm, borderWidth: 1, borderColor: colors.border },
  tabBtnActive: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  tabLabel: { color: colors.textMuted, fontSize: typography.body, fontWeight: "700" },
  tabLabelActive: { color: colors.primary },
  content: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xl },
  card: { gap: spacing.lg },
  title: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800" },
  subtitle: { color: colors.textMuted, fontSize: typography.body, marginBottom: spacing.sm },
  input: { backgroundColor: colors.bg, color: colors.text, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  symptomsGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  symptomBtn: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.sm, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border },
  symptomBtnActive: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  symptomLabel: { color: colors.textMuted, fontSize: typography.small },
  symptomLabelActive: { color: colors.primary, fontWeight: "bold" },
  imagePreviewContainer: { width: "100%", height: 300, backgroundColor: colors.bg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, overflow: "hidden", justifyContent: "center", alignItems: "center" },
  imagePreview: { width: "100%", height: "100%", resizeMode: "contain" },
  placeholderBox: { alignItems: "center", gap: spacing.md },
  placeholderText: { color: colors.textMuted, fontSize: typography.body },
  btnRow: { flexDirection: "row", gap: spacing.md },
  analyzeBtn: { marginTop: spacing.sm },
  resultBox: { marginTop: spacing.md, padding: spacing.md, backgroundColor: colors.bgAlt, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.primarySoft },
  resultTitle: { color: colors.primary, fontSize: typography.body, fontWeight: "800", marginBottom: spacing.xs },
  resultText: { color: colors.text, fontSize: typography.body, marginTop: spacing.xs }
});
