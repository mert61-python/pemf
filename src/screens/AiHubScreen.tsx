import { useState, useEffect, useRef } from "react";
import { StyleSheet, Text, View, Image, ScrollView, ActivityIndicator, TouchableOpacity, TextInput, Alert, Platform, Linking } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { Camera, Image as ImageIcon, Sparkles, Stethoscope, ScissorsSquare as Scan, Activity, Microscope, CheckCircle2, Video, SwitchCamera } from "lucide-react-native";
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { colors, radius, spacing, typography } from "@/theme/tokens";
import { useToast } from "@/components/ui/ToastProvider";
import { apiPost, platformAlert } from "@/services/apiClient";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { serviceConfig } from "@/services/config";
import { useUserMode } from "@/context/UserModeContext";
import { useLiveData } from "@/context/LiveDataContext";
import { useAppNav } from "@/context/AppNavContext";
import { useResponsive } from "@/hooks/useResponsive";

type AiModule = "disease" | "landmark" | "segmentation" | "thermal" | "reticulocytes";

const SYMPTOMS = [
  "İştah Kaybı", "Kusma", "İshal", "Öksürük", "Solunum Güçlüğü", 
  "Topallık", "Deri Lezyonları", "Burun Akıntısı", "Göz Akıntısı", 
  "Halsizlik / Uyuşukluk", "Kilo Kaybı", "Hapşırma", "Dehidrasyon", "Ateş"
];

/** AI teşhis sonucunu kalıcı audit loguna gönderir (hasta + modül + özet). */
async function logAiResult(patientName: string, module: string, summary: string) {
  try {
    await apiPost("/ai/log", { patient_name: patientName || "", module, summary }, null);
  } catch {
    /* audit başarısız — kullanıcı akışını bozma */
  }
}

function summarizeVision(d: any): string {
  if (d?.fgs_total !== undefined) return `FGS ${d.fgs_total}/10${d?.pain_level ? ` (${d.pain_level})` : ""}`;
  if (d?.cat_count !== undefined) return `${d.cat_count} kedi tespit edildi`;
  if (d?.prediction?.label) return `Termal: ${d.prediction.label}`;
  if (d?.counts) return `Eritrosit ${d.counts["erythrocyte"] ?? "?"} / Retikülosit ${(d.counts["punctate reticulocyte"] ?? 0) + (d.counts["aggregate reticulocyte"] ?? 0)}`;
  return "Analiz tamamlandı";
}

export function AiHubScreen() {
  const { isExpert } = useUserMode();
  const { selectedPatient } = useAppNav();
  const [activeModule, setActiveModule] = useState<AiModule>("landmark");

  if (!isExpert) {
    return <PetOwnerAiScreen />;
  }

  const patientName = selectedPatient?.name || "";

  const MODULES: { id: AiModule; label: string; desc: string; icon: any }[] = [
    { id: "landmark", label: "Yüz Ağrısı (FGS)", desc: "YOLO-pose ile yüz ağrı skoru", icon: Scan },
    { id: "disease", label: "Hastalık", desc: "XGBoost ile hastalık tahmini", icon: Stethoscope },
    { id: "segmentation", label: "Segmentasyon", desc: "Vücut sınırı tespiti", icon: Scan },
    { id: "thermal", label: "Termal", desc: "Termal anormallik analizi", icon: Activity },
    { id: "reticulocytes", label: "Retikülosit", desc: "Mikroskobik hücre sayımı", icon: Microscope },
  ];

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.selectorHeading}>Tanı Modülleri</Text>
        <View style={styles.moduleGrid}>
          {MODULES.map((m) => {
            const Icon = m.icon;
            const active = activeModule === m.id;
            return (
              <TouchableOpacity
                key={m.id}
                style={[styles.moduleCard, active && styles.moduleCardActive]}
                onPress={() => setActiveModule(m.id)}
                activeOpacity={0.85}
              >
                <View style={[styles.moduleIconWrap, active && styles.moduleIconWrapActive]}>
                  <Icon size={22} color={active ? colors.white : colors.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.moduleLabel, active && styles.moduleLabelActive]} numberOfLines={1}>{m.label}</Text>
                  <Text style={styles.moduleDesc} numberOfLines={2}>{m.desc}</Text>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>

        {activeModule === "disease" && <DiseaseModule patientName={patientName} />}
        {/* BUG #4 FIX: key={activeModule} sayesinde tab değişiminde VisionModule sıfırdan mount olur,
            önceki sekmeye ait imageFile/imageUri state'i bir sonraki sekmeye sızmaz. */}
        {activeModule === "landmark" && <VisionModule key="landmark" endpoint="/vision/landmark" title="Yüz Ağrısı Skoru (FGS)" subtitle="YOLO-pose modeli ile yüzdeki kilit noktaları analiz eder." patientName={patientName} />}
        {activeModule === "segmentation" && <VisionModule key="segmentation" endpoint="/vision/segmentation" title="Kedi Segmentasyonu" subtitle="YOLOv8-seg modeli ile kedinin vücut sınırlarını tespit eder." patientName={patientName} />}
        {activeModule === "thermal" && <VisionModule key="thermal" endpoint="/vision/thermal" title="Termal Görüntü Analizi" subtitle="GhostNetV2 ile termal anormallikleri tespit eder." patientName={patientName} />}
        {activeModule === "reticulocytes" && <VisionModule key="reticulocytes" endpoint="/vision/reticulocytes" title="Retikülosit Sayımı" subtitle="Mikroskop görüntüsünden hücreleri otomatik sayar." patientName={patientName} />}
      </ScrollView>
    </View>
  );
}

function PetOwnerAiScreen() {
  const { showToast } = useToast();
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [imageFile, setImageFile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [treatmentStatus, setTreatmentStatus] = useState<string>("");

  const takePhoto = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      (input as any).capture = 'environment';
      input.onchange = (e: any) => {
        const file = e.target.files[0];
        if (file) {
          setImageFile(file);
          setImageUri(URL.createObjectURL(file));
          setResult(null); setTreatmentStatus("");
        }
      };
      input.click();
    } else {
      let res = await ImagePicker.launchCameraAsync({ allowsEditing: true, quality: 0.7, base64: true });
      if (!res.canceled) { 
        setImageUri(res.assets[0].uri); 
        setImageBase64(res.assets[0].base64 || null);
        setImageFile((res.assets[0] as any).file || null);
        setResult(null); setTreatmentStatus(""); 
      }
    }
  };

  const pickImage = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      input.onchange = (e: any) => {
        const file = e.target.files[0];
        if (file) {
          // BUG #3 FIX: Eski objectURL'yi revoke et, memory leak önlenir
          if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri);
          setImageFile(file);
          setImageUri(URL.createObjectURL(file));
          setResult(null); setTreatmentStatus("");
        }
      };
      input.click();
    } else {
      let res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: true, quality: 0.7, base64: true });
      if (!res.canceled) { 
        setImageUri(res.assets[0].uri); 
        setImageBase64(res.assets[0].base64 || null);
        setImageFile((res.assets[0] as any).file || null);
        setResult(null); setTreatmentStatus(""); 
      }
    }
  };

  const analyzeImage = async () => {
    if (!imageUri) return;
    setLoading(true);
    try {
      const formData = new FormData();
      if (Platform.OS === 'web') {
        let blob = imageFile;
        if (!blob && imageBase64) {
          const bstr = atob(imageBase64);
          let n = bstr.length;
          const u8arr = new Uint8Array(n);
          while (n--) {
            u8arr[n] = bstr.charCodeAt(n);
          }
          blob = new Blob([u8arr], { type: 'image/jpeg' });
        } else if (!blob && imageUri && imageUri.startsWith('data:')) {
          const arr = imageUri.split(',');
          const mime = arr[0].match(/:(.*?);/)?.[1] || 'image/jpeg';
          const bstr = atob(arr[1]);
          let n = bstr.length;
          const u8arr = new Uint8Array(n);
          while (n--) {
            u8arr[n] = bstr.charCodeAt(n);
          }
          blob = new Blob([u8arr], { type: mime });
        } else if (!blob) {
          throw new Error("Web ortamında geçerli bir dosya bulunamadı.");
        }
        formData.append("file", blob, "camera_capture.jpg");
      } else {
        if (imageBase64) {
          formData.append("image_base64", imageBase64);
        } else {
          formData.append("file", { uri: imageUri, name: "camera_capture.jpg", type: "image/jpeg" } as any);
        }
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
        showToast(data?.detail || "Teşhis sırasında hata oluştu.", "error");
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
              <View style={{ flex: 1 }}>
                <Button variant="secondary" label="Yeni Fotoğraf" onPress={() => { setImageUri(null); setImageBase64(null); setImageFile(null); }} />
              </View>
              <View style={{ flex: 1 }}>
                <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "Teşhis Et"} onPress={() => analyzeImage()} disabled={loading} icon={loading ? <ActivityIndicator color="#fff" /> : <Sparkles color="#fff" size={16} />} />
              </View>
            </View>
          </View>
        )}

        {result && (() => {
          let recommendation = "";
          let requiresVet = false;
          let showTherapy = false;
          const score = result.fgs_total;
          // GÜVENLİK: tespit yoksa (detected=false / score yok / <0) "ağrı yok" YANLIŞ güvencesi VERME.
          const notDetected = result.detected === false || score == null || score < 0;

          if (notDetected) {
            recommendation = "Kedinin yüzü net tespit edilemedi. Lütfen yüzü net, iyi aydınlatılmış ve tam karşıdan çekilmiş bir fotoğrafla tekrar deneyin.";
          } else if (score === 0) {
            recommendation = "Dostunuzun yüz hatlarında herhangi bir ağrı veya stres belirtisi görülmüyor. Oldukça rahat görünüyor!";
          } else if (score > 0 && score <= 3) {
            recommendation = "Dostunuzda hafif bir rahatsızlık veya yorgunluk belirtisi olabilir. Bu durum geçici olabilir ancak gözlemlemeye devam edin. İsteğe bağlı olarak PEMF terapisi ile onu rahatlatabilirsiniz.";
            showTherapy = true;
          } else if (score > 3 && score <= 5) {
            recommendation = "Orta derecede ağrı veya stres belirtileri tespit edildi! Yüz hatlarında belirgin bir gerginlik var. Otonom PEMF terapisi uygulayarak rahatlamasını sağlayabilirsiniz. Belirtiler 1-2 günden uzun sürerse hekime danışın.";
            showTherapy = true;
          } else {
            recommendation = "ŞİDDETLİ AĞRI BELİRTİSİ! Dostumuz ciddi bir rahatsızlık yaşıyor olabilir. Lütfen vakit kaybetmeden VETERİNER HEKİMİNİZE BAŞVURUN.";
            requiresVet = true;
          }

          return (
            <View style={styles.petOwnerResult}>
              <Text style={styles.petOwnerResultTitle}>Yapay Zeka Analiz Sonucu</Text>
              
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.sm }}>
                <Text style={styles.body}>Ağrı Skoru (FGS):</Text>
                <Text style={[styles.title, { color: notDetected ? colors.textMuted : score > 3 ? colors.danger : colors.success }]}>{notDetected ? "—" : `${score} / 10`}</Text>
              </View>

              <View style={[styles.recommendationBox, requiresVet && { backgroundColor: colors.danger + "22", borderColor: colors.danger }]}>
                <Text style={[styles.recommendationText, requiresVet && { color: colors.danger, fontWeight: 'bold' }]}>
                  {recommendation}
                </Text>
                
                {showTherapy && (
                  <TouchableOpacity style={styles.startTherapyBtn} onPress={startAutoTreatment}>
                    <CheckCircle2 color="#fff" size={20} />
                    <Text style={styles.startTherapyText}>Otonom Rahatlama Terapisini Başlat</Text>
                  </TouchableOpacity>
                )}
                {requiresVet && (
                  <TouchableOpacity
                    style={[styles.startTherapyBtn, { backgroundColor: colors.danger }]}
                    onPress={async () => {
                      const phone = ((await AsyncStorage.getItem("pemf_clinic_phone")) || "").replace(/\s/g, "");
                      if (phone) Linking.openURL(`tel:${phone}`).catch(() => {});
                      else platformAlert("Klinik telefonu ayarlı değil", "Ayarlar ekranından klinik telefon numarasını girin.");
                    }}
                  >
                    <Stethoscope color="#fff" size={20} />
                    <Text style={styles.startTherapyText}>Veteriner Kliniğini Ara</Text>
                  </TouchableOpacity>
                )}
              </View>

              {treatmentStatus ? <Text style={[styles.statusText, { textAlign: 'center', marginTop: spacing.md }]}>{treatmentStatus}</Text> : null}
            </View>
          );
        })()}
      </Card>

      <View style={{ marginTop: spacing.xl }}>
        <DiseaseModule patientName="" />
      </View>
    </ScrollView>
  );
}

/** Medikal sorumluluk reddi — her AI sonucunun altında gösterilir (karar-destek / yasal). */
function MedicalDisclaimer() {
  return (
    <Text style={styles.disclaimer}>
      ⚠️ Bu yapay zeka sonucu yalnızca karar-destek amaçlıdır; veteriner hekim muayenesi ve
      teşhisinin yerine geçmez. Nihai karar hekime aittir.
    </Text>
  );
}

function DiseaseModule({ patientName }: { patientName: string }) {
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
    // Girdi aralık validasyonu (boş alanlar serbest; doluysa makul aralıkta olmalı).
    const ranges: Record<string, [number, number, string]> = {
      age: [0, 40, "Yaş"], weight: [0, 80, "Kilo"], hr: [0, 400, "Nabız"],
      temp: [25, 46, "Ateş"], duration: [0, 3650, "Süre"],
    };
    for (const k of Object.keys(ranges)) {
      const raw = (form as any)[k];
      if (raw !== "" && raw != null) {
        const n = Number(raw);
        const [lo, hi, label] = ranges[k];
        if (isNaN(n) || n < lo || n > hi) {
          showToast(`${label} geçersiz (${lo}–${hi} aralığında olmalı).`, "error");
          return;
        }
      }
    }
    // Kritik vitaller ZORUNLU — backend bunları ister (boş/sıfır → anlamsız tahmin, 422 döner).
    // Boş bırakılırsa kullanıcı "sunucu hatası" görüyordu; net Türkçe uyarı verip erken çıkalım.
    if (!form.weight || !form.hr || !form.temp) {
      showToast("Kilo, nabız ve vücut sıcaklığını girin (tahmin için gerekli).", "error");
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
    if (res.status === "success") {
      setResult(res.results);
      const top = res.results?.[0];
      logAiResult(patientName, "Hastalık Analizi", top ? `${top.disease} (%${(top.probability * 100).toFixed(0)})` : "Belirgin sonuç yok");
    }
    // Hata durumunda apiClient zaten kullanıcıya bildirim gösterir (çift-popup önlendi).
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
      <View style={{ marginTop: spacing.sm }}>
        <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "Teşhisi Başlat"} onPress={analyze} disabled={loading} />
      </View>
      
      {result && (
        <View style={styles.resultBox}>
          <Text style={styles.resultTitle}>Yapay Zeka Olası Hastalık Tahminleri:</Text>
          {result.length === 0 ? (
            <Text style={styles.resultText}>Bu semptomlarla eşleşen belirgin bir hastalık bulunamadı.</Text>
          ) : (
            result.map((r, i) => (
              <View key={i} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: spacing.xs }}>
                <Text style={[styles.resultText, { flex: 1 }]}>{r.disease}</Text>
                <Text style={[styles.resultText, { fontWeight: 'bold', color: r.probability > 0.6 ? colors.danger : colors.warning }]}>
                  %{(r.probability * 100).toFixed(1)}
                </Text>
              </View>
            ))
          )}
          <MedicalDisclaimer />
        </View>
      )}
    </Card>
  );
}

// Tab değişiminde (VisionModule unmount olur) foto/sonuç kaybolmasın diye modül-seviyesi cache.
const visionCache: Record<string, { imageUri: string | null; imageBase64: string | null; result: any }> = {};

function VisionModule({ endpoint, title, subtitle, patientName }: { endpoint: string, title: string, subtitle: string, patientName: string }) {
  const { showToast } = useToast();
  const [imageUri, setImageUri] = useState<string | null>(visionCache[endpoint]?.imageUri ?? null);
  const [imageBase64, setImageBase64] = useState<string | null>(visionCache[endpoint]?.imageBase64 ?? null);
  const [imageFile, setImageFile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(visionCache[endpoint]?.result ?? null);
  
  const [isLive, setIsLive] = useState(false);
  // BUG FIX: Canlı kamera varsayılan olarak ARKA ('back') kamera (kediyi çekmek için);
  // selfie/ön kamera açılmasını engeller. Flip butonu ile ön↔arka geçiş yapılabilir.
  const [facing, setFacing] = useState<"back" | "front">("back");
  const [autoAdjust, setAutoAdjust] = useState(false);
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<any>(null);
  const liveIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // BUG #2 FIX: loading state'ini useRef ile takip et, setInterval closure'u her zaman güncel değeri okur
  const loadingRef = useRef(false);
  const autoAdjustRef = useRef(autoAdjust);
  const { aiVisionData } = useLiveData();
  const { isCompact } = useResponsive();

  useEffect(() => {
    autoAdjustRef.current = autoAdjust;
  }, [autoAdjust]);

  // Foto/sonuç'u cache'e yaz → tab değişip geri dönünce korunur (tekrar yükleme gerekmez).
  useEffect(() => {
    visionCache[endpoint] = { imageUri, imageBase64, result };
  }, [endpoint, imageUri, imageBase64, result]);

  useEffect(() => {
    let active = true;
    if (isLive && autoAdjust) {
      // Otonom (Kapalı Döngü) Modu - Backend'i Başlat
      apiPost<{status: string}>("/ai/pro/start", {}, {status: "error"}).then((res) => {
        if (!active) return;
        if (res?.status === "success") showToast("Otonom Biofeedback başladı", "success");
        else showToast("Otonom Biofeedback başlatılamadı (kamera/model erişilemedi).", "error");
      });
    } else {
      // Backend'i durdur (Kamerayı serbest bırakır)
      apiPost<{status: string}>("/ai/pro/stop", {}, {status: "error"}).catch(() => {});
    }

    return () => {
      active = false;
      apiPost<{status: string}>("/ai/pro/stop", {}, {status: "error"}).catch(() => {});
    };
  }, [isLive, autoAdjust]);

  // Canlı kamera (otonom-OLMAYAN mod): telefon kamerasından periyodik kare yakala → analiz et.
  useEffect(() => {
    if (!isLive || autoAdjust) return;
    const capture = async () => {
      if (loadingRef.current || !cameraRef.current) return;
      loadingRef.current = true;
      try {
        const photo = await cameraRef.current.takePictureAsync({ quality: 0.5, base64: true, skipProcessing: true });
        if (photo?.base64) {
          const fd = new FormData();
          fd.append("image_base64", photo.base64);
          fd.append("auto_adjust", "false");
          const ctrl = new AbortController();
          const t = setTimeout(() => ctrl.abort(), 15000);
          const r = await fetch(serviceConfig.apiBaseUrl + "/ai" + endpoint, {
            method: "POST", body: fd, headers: { Accept: "application/json" }, signal: ctrl.signal,
          });
          clearTimeout(t);
          const data = await r.json();
          if (r.ok && data?.status === "success") setResult(data); // overlay result.image_base64 ile güncellenir
        }
      } catch {
        /* canlı modda kare hatalarını sessiz geç */
      } finally {
        loadingRef.current = false;
      }
    };
    liveIntervalRef.current = setInterval(capture, 2500);
    return () => {
      if (liveIntervalRef.current) {
        clearInterval(liveIntervalRef.current);
        liveIntervalRef.current = null;
      }
    };
  }, [isLive, autoAdjust, endpoint]);

  // "Model hazırlanıyor" ipucu: analiz 8sn'den uzun sürerse (ilk-kullanım model indirme).
  const [longLoading, setLongLoading] = useState(false);
  useEffect(() => {
    if (!loading) {
      setLongLoading(false);
      return;
    }
    const t = setTimeout(() => setLongLoading(true), 8000);
    return () => clearTimeout(t);
  }, [loading]);

  const toggleLive = async () => {
    if (!isLive) {
      // Kamerayı açarken izin yoksa iste.
      if (!permission?.granted) {
        const res = await requestPermission();
        if (!res?.granted) {
          showToast("Kamera için izin gerekli.", "error");
          return;
        }
      }
    }
    const next = !isLive;
    setIsLive(next);
    if (!next) {
      setImageUri(null);
      setImageBase64(null);
      setImageFile(null);
      setResult(null);
    }
  };

  const takePhoto = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      (input as any).capture = 'environment';
      input.onchange = (e: any) => {
        const file = e.target.files[0];
        if (file) {
          // BUG #3 FIX: eski objectURL'yi temizle
          if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri);
          setImageFile(file);
          setImageUri(URL.createObjectURL(file));
          setImageBase64(null);
          setResult(null);
        }
      };
      input.click();
    } else {
      let res = await ImagePicker.launchCameraAsync({ allowsEditing: true, quality: 0.8, base64: true });
      if (!res.canceled) {
        setImageUri(res.assets[0].uri);
        setImageBase64(res.assets[0].base64 || null);
        setImageFile((res.assets[0] as any).file || null);
        setResult(null);
      }
    }
  };

  const pickImage = async () => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      input.onchange = (e: any) => {
        const file = e.target.files[0];
        if (file) {
          // BUG #3 FIX: eski objectURL'yi temizle
          if (imageUri && imageUri.startsWith('blob:')) URL.revokeObjectURL(imageUri);
          setImageFile(file);
          setImageUri(URL.createObjectURL(file));
          setImageBase64(null);
          setResult(null);
        }
      };
      input.click();
    } else {
      let res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: true, quality: 0.8, base64: true });
      if (!res.canceled) {
        setImageUri(res.assets[0].uri);
        setImageBase64(res.assets[0].base64 || null);
        setImageFile((res.assets[0] as any).file || null);
        setResult(null);
      }
    }
  };

  const analyzeImage = async (uriToAnalyze?: string | null) => {
    uriToAnalyze = typeof uriToAnalyze === "string" ? uriToAnalyze : imageUri;
    if (!uriToAnalyze) return;
    // BUG #2 FIX: loadingRef hem state hem de interval closure için güncelleniyor
    setLoading(true);
    loadingRef.current = true;
    try {
      const formData = new FormData();
      if (Platform.OS === 'web') {
        let blob: Blob | null = null;
        if (uriToAnalyze === imageUri && imageFile) {
          blob = imageFile;
        } else if (uriToAnalyze.startsWith('data:')) {
          const arr = uriToAnalyze.split(',');
          const mime = arr[0].match(/:(.*?);/)?.[1] || 'image/jpeg';
          const bstr = atob(arr[1]);
          let n = bstr.length;
          const u8arr = new Uint8Array(n);
          while (n--) {
            u8arr[n] = bstr.charCodeAt(n);
          }
          blob = new Blob([u8arr], { type: mime });
        } else if (uriToAnalyze === imageUri && imageBase64) {
          const bstr = atob(imageBase64);
          let n = bstr.length;
          const u8arr = new Uint8Array(n);
          while (n--) {
            u8arr[n] = bstr.charCodeAt(n);
          }
          blob = new Blob([u8arr], { type: 'image/jpeg' });
        } else {
          const res = await fetch(uriToAnalyze);
          blob = await res.blob();
          if (blob.type && !blob.type.startsWith("image/")) {
            throw new Error("Seçilen dosya görsel olarak okunamadı.");
          }
        }
        if (!blob) {
          throw new Error("Görüntü dosyası hazırlanamadı.");
        }
        formData.append("file", blob, "upload.jpg");
      } else {
        if (uriToAnalyze === imageUri && imageBase64) {
          formData.append("image_base64", imageBase64);
        } else {
          formData.append("file", { uri: uriToAnalyze, name: "upload.jpg", type: "image/jpeg" } as any);
        }
      }
      formData.append("auto_adjust", autoAdjustRef.current ? "true" : "false");
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), 60000); // ilk-kullanım model indirme için geniş timeout
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai" + endpoint, {
        method: "POST",
        body: formData,
        headers: { "Accept": "application/json" },
        signal: ctrl.signal,
      });
      clearTimeout(to);
      const data = await response.json();
      if (response.ok && data.status === "success") {
        setResult(data);
        if (isLive) setImageUri(`data:image/jpeg;base64,${data.image_base64}`); // overlay updated
        else logAiResult(patientName, title, summarizeVision(data)); // sadece manuel analizleri audit'e yaz
      }
      else if (!isLive) showToast(data?.detail || "Analiz sırasında hata oluştu.", "error");
    } catch (error) {
      if (!isLive) showToast("Ağ veya sunucu hatası.", "error");
    } finally {
      setLoading(false);
      loadingRef.current = false;
    }
  };

  return (
    <Card style={styles.card}>
      <View style={{flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start'}}>
        <View style={{flex: 1}}>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.subtitle}>{subtitle}</Text>
        </View>
        {endpoint === "/vision/landmark" && (
          <TouchableOpacity 
            style={[styles.autoAdjustBtn, autoAdjust ? styles.autoAdjustActive : null]} 
            onPress={() => setAutoAdjust(!autoAdjust)}
          >
            <Activity color={autoAdjust ? colors.white : colors.primary} size={16} />
            <Text style={[styles.autoAdjustText, autoAdjust ? {color: colors.white} : null]}>
              Otonom Biofeedback
            </Text>
          </TouchableOpacity>
        )}
      </View>
      
      {!imageUri && !isLive && (
        <View style={styles.photoGuide}>
          {endpoint === "/vision/landmark" ? (
            <>
              <Text style={styles.photoGuideTitle}>📸 Doğru FGS analizi için fotoğraf ipuçları</Text>
              <Text style={styles.photoGuideItem}>• Kedinin yüzünü <Text style={styles.photoGuideBold}>tam karşıdan</Text>, net ve yakın çekin</Text>
              <Text style={styles.photoGuideItem}>• İyi aydınlatma — bulanık veya karanlık olmasın</Text>
              <Text style={styles.photoGuideItem}>• Gözler, kulaklar, burun ve bıyıklar net görünsün</Text>
              <Text style={styles.photoGuideItem}>• Tek kedi, yüz kameraya dönük olsun</Text>
            </>
          ) : (
            <>
              <Text style={styles.photoGuideTitle}>📸 Fotoğraf ipuçları</Text>
              <Text style={styles.photoGuideItem}>• Net, iyi aydınlatılmış, yakın görüntü kullanın (bulanık olmasın)</Text>
            </>
          )}
          <Text style={styles.photoGuideWarn}>⚠️ Yanlış/bulanık fotoğraf hatalı sonuç verir. Yüz net tespit edilemezse uyarı gösterilir.</Text>
        </View>
      )}
      <View style={styles.imagePreviewContainer}>
        {(isLive && autoAdjust && aiVisionData?.imageBase64) ? (
          <View style={styles.cameraContainer}>
            <Image source={{ uri: `data:image/jpeg;base64,${aiVisionData.imageBase64}` }} style={styles.cameraView} resizeMode="contain" />
            <View style={styles.liveIndicator}>
              <View style={styles.liveDot} />
              <Text style={styles.liveText}>OTONOM BİOFEEDBACK AKTİF</Text>
            </View>
          </View>
        ) : isLive ? (
          <View style={styles.cameraContainer}>
            <CameraView ref={cameraRef} style={styles.cameraView} facing={facing} />
            {result?.image_base64 && (
              <Image source={{ uri: `data:image/jpeg;base64,${result.image_base64}` }} style={styles.cameraOverlay} />
            )}
            <TouchableOpacity
              style={styles.flipCameraBtn}
              onPress={() => setFacing((f) => (f === "back" ? "front" : "back"))}
            >
              <SwitchCamera color={colors.white} size={20} />
            </TouchableOpacity>
            <View style={styles.liveIndicator}>
              <View style={styles.liveDot} />
              <Text style={styles.liveText}>KAMERA AKTİF</Text>
            </View>
          </View>
        ) : imageUri ? (
          <Image source={{ uri: result?.image_base64 ? `data:image/jpeg;base64,${result.image_base64}` : imageUri }} style={styles.imagePreview} />
        ) : (
          <View style={styles.placeholderBox}>
            <ImageIcon color={colors.textMuted} size={48} />
            <Text style={styles.placeholderText}>Görüntü seçilmedi</Text>
          </View>
        )}
      </View>

      <View style={[styles.btnRow, isCompact && { flexDirection: "column" }]}>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label="Galeriden Seç" icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} disabled={isLive} />
        </View>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button label="Fotoğraf Çek" icon={<Camera color={colors.white} size={16} />} onPress={takePhoto} disabled={isLive} />
        </View>
        <View style={isCompact ? { width: "100%" } : { flex: 1 }}>
          <Button
            label={isLive ? "Canlıyı Durdur" : "Canlı Kamera"}
            variant={isLive ? "danger" : "secondary"}
            icon={<Video color={isLive ? colors.white : colors.primary} size={16} />}
            onPress={toggleLive}
          />
        </View>
      </View>

      <View style={styles.analyzeBtn}>
        <Button variant="primary" label={loading ? "Analiz Ediliyor..." : "AI Analizini Başlat"} icon={loading ? <ActivityIndicator color={colors.white} /> : <Sparkles color={colors.white} size={16} />} disabled={!imageUri || loading} onPress={() => analyzeImage()} />
      </View>
      {longLoading && <Text style={styles.modelHint}>Model hazırlanıyor (ilk kullanım uzun sürebilir)…</Text>}

      {result && !autoAdjust && (
        <View style={styles.resultBox}>
          <Text style={styles.resultTitle}>Analiz Sonucu:</Text>
          {(result.detected === false || result.fgs_total === null || (typeof result.fgs_total === "number" && result.fgs_total < 0)) && (
            <Text style={[styles.resultText, { color: colors.warning, fontWeight: "600" }]}>⚠️ Kedi yüzü net tespit edilemedi — ağrı skoru hesaplanamadı. Net, iyi aydınlatılmış, tam karşıdan çekilmiş bir fotoğrafla tekrar deneyin.</Text>
          )}
          {result.pain_level && !(result.detected === false || result.fgs_total === null) && (() => {
            // Backend 'Mild'/'Moderate'/'Severe' veya 'Mild Pain' döndürebilir → normalize et + uygun ton.
            const k = String(result.pain_level).replace(/\s*pain\s*/i, "").trim().toLowerCase();
            const labels: Record<string, string> = { no: "Ağrı Yok", none: "Ağrı Yok", mild: "Hafif Ağrı", moderate: "Orta Derece Ağrı", severe: "Şiddetli Ağrı" };
            const tone = (k === "no" || k === "none") ? colors.success : k === "mild" ? colors.warning : colors.danger;
            return <Text style={styles.resultText}>Ağrı Seviyesi: <Text style={{fontWeight:'bold', color: tone}}>{labels[k] || result.pain_level}</Text></Text>;
          })()}
          {result.fgs_total != null && result.fgs_total >= 0 && (
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
             const prob = result.prediction.confidence !== undefined ? (result.prediction.confidence * 100).toFixed(1) : "?";
             return <Text style={styles.resultText}>Termal Tespit: <Text style={{fontWeight:'bold', color: result.prediction.label === "Sick" ? colors.danger : colors.success}}>{lbl}</Text> (Doğruluk: %{prob})</Text>;
          })()}
          {result.counts && (
            <>
              <Text style={styles.resultText}>Eritrosit: {result.counts["erythrocyte"]}</Text>
              <Text style={styles.resultText}>Noktalı Retikülosit: {result.counts["punctate reticulocyte"]}</Text>
              <Text style={styles.resultText}>Agrege Retikülosit: {result.counts["aggregate reticulocyte"]}</Text>
            </>
          )}
          {result.hw_status === "updated" && (
            <View style={{ marginTop: spacing.sm, padding: spacing.sm, backgroundColor: colors.success + "22", borderRadius: radius.sm, borderWidth: 1, borderColor: colors.success }}>
              <Text style={[styles.resultText, {fontWeight: 'bold', color: colors.success}]}>Cihaz Otonom Olarak Güncellendi!</Text>
              <Text style={styles.resultText}>Yeni Frekans: {result.hw_params?.freq?.toFixed(1)} Hz</Text>
              <Text style={styles.resultText}>Yeni Şiddet: {result.hw_params?.duty?.toFixed(1)} %</Text>
            </View>
          )}
          <MedicalDisclaimer />
        </View>
      )}

      {isLive && autoAdjust && aiVisionData && (
        <View style={styles.resultBox}>
          <Text style={styles.resultTitle}>Otonom Canlı Sonuç:</Text>
          <Text style={styles.resultText}>Anlık FGS Skoru: <Text style={{fontWeight:'bold'}}>{aiVisionData.fgs_total} / 10</Text></Text>
          <View style={{ marginTop: spacing.sm, padding: spacing.sm, backgroundColor: colors.success + "22", borderRadius: radius.sm, borderWidth: 1, borderColor: colors.success }}>
             <Text style={[styles.resultText, {fontWeight: 'bold', color: colors.success}]}>Cihaz Otonom Olarak Güncelleniyor (Saniyede 1)</Text>
          </View>
        </View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  selectorHeading: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800", marginTop: spacing.lg, marginBottom: spacing.md },
  moduleGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginBottom: spacing.lg },
  moduleCard: { flexGrow: 1, flexBasis: 220, minWidth: 180, flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.lg, backgroundColor: colors.bgAlt, borderWidth: 1, borderColor: colors.border },
  moduleCardActive: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  moduleIconWrap: { width: 44, height: 44, borderRadius: radius.md, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border },
  moduleIconWrapActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  moduleLabel: { color: colors.text, fontSize: typography.body, fontWeight: "700" },
  moduleLabelActive: { color: colors.primary },
  moduleDesc: { color: colors.textMuted, fontSize: typography.small, marginTop: 2, lineHeight: 15 },
  content: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xl, width: "100%", maxWidth: 980, alignSelf: "center" },
  card: { gap: spacing.lg },
  cardHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm },
  title: { color: colors.text, fontSize: typography.subtitle, fontWeight: "800" },
  subtitle: { color: colors.textMuted, fontSize: typography.body, marginBottom: spacing.sm },
  input: { backgroundColor: colors.bg, color: colors.text, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  symptomsGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  symptomBtn: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.sm, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border },
  symptomBtnActive: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  symptomLabel: { color: colors.textMuted, fontSize: typography.small },
  symptomLabelActive: { color: colors.primary, fontWeight: "bold" },
  imagePreviewContainer: { width: "100%", height: 300, backgroundColor: colors.bg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, overflow: "hidden", justifyContent: "center", alignItems: "center", position: "relative" },
  photoGuide: { backgroundColor: colors.primarySoft, borderRadius: radius.md, padding: spacing.md, gap: 3, borderWidth: 1, borderColor: colors.primarySoft },
  photoGuideTitle: { color: colors.text, fontSize: typography.small, fontWeight: "800", marginBottom: 2 },
  photoGuideItem: { color: colors.textMuted, fontSize: typography.small, lineHeight: 18 },
  photoGuideBold: { color: colors.text, fontWeight: "bold" },
  photoGuideWarn: { color: colors.warning, fontSize: typography.small, fontStyle: "italic", marginTop: spacing.xs },
  imagePreview: { width: "100%", height: "100%", resizeMode: "contain" },
  cameraContainer: { width: "100%", height: "100%", position: "relative" },
  cameraView: { flex: 1 },
  cameraOverlay: { position: "absolute", top: 0, left: 0, width: "100%", height: "100%", resizeMode: "contain", opacity: 0.8 },
  liveIndicator: { position: "absolute", top: 12, right: 12, flexDirection: "row", alignItems: "center", backgroundColor: "rgba(0,0,0,0.6)", paddingHorizontal: 8, paddingVertical: 4, borderRadius: 12, gap: 6 },
  flipCameraBtn: { position: "absolute", bottom: 12, right: 12, width: 44, height: 44, borderRadius: 22, backgroundColor: "rgba(0,0,0,0.6)", alignItems: "center", justifyContent: "center" },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.danger },
  liveText: { color: colors.white, fontSize: 10, fontWeight: "bold" },
  placeholderBox: { alignItems: "center", gap: spacing.md },
  placeholderText: { color: colors.textMuted, fontSize: typography.body },
  btnRow: { flexDirection: "row", gap: spacing.md },
  analyzeBtn: { marginTop: spacing.sm },
  resultBox: { marginTop: spacing.md, padding: spacing.md, backgroundColor: colors.bgAlt, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.primarySoft },
  resultTitle: { color: colors.primary, fontSize: typography.body, fontWeight: "800", marginBottom: spacing.xs },
  resultText: { color: colors.text, fontSize: typography.body, marginTop: spacing.xs },
  actions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg },
  bigActionBtn: { flex: 1, backgroundColor: colors.primary, borderRadius: radius.md, alignItems: 'center', padding: spacing.xl, gap: spacing.sm },
  bigActionText: { color: '#fff', fontSize: typography.subtitle, fontWeight: '800' },
  secondaryActionBtn: { flex: 1, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, alignItems: 'center', padding: spacing.xl, gap: spacing.sm },
  secondaryActionText: { color: colors.primary, fontSize: typography.subtitle, fontWeight: '700' },
  previewImage: { width: '100%', height: 300, borderRadius: radius.md, backgroundColor: colors.bg },
  petOwnerResult: { marginTop: spacing.lg, padding: spacing.md, backgroundColor: colors.bgAlt, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  petOwnerResultTitle: { fontSize: typography.subtitle, color: colors.text, fontWeight: '800', marginBottom: spacing.sm },
  body: { color: colors.text, fontSize: typography.body, marginBottom: 4 },
  recommendationBox: { backgroundColor: colors.warning + "22", padding: spacing.md, borderRadius: radius.md, marginTop: spacing.md, borderWidth: 1, borderColor: colors.warning },
  recommendationText: { color: colors.text, fontSize: typography.small, marginBottom: spacing.md },
  startTherapyBtn: { backgroundColor: colors.success, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: spacing.md, borderRadius: radius.md, gap: spacing.sm },
  startTherapyText: { color: '#fff', fontWeight: '800', fontSize: typography.body },
  statusText: { color: colors.primary, fontWeight: 'bold' },
  autoAdjustBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, borderWidth: 1, borderColor: colors.primary, paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderRadius: radius.sm },
  autoAdjustActive: { backgroundColor: colors.primary },
  autoAdjustText: { color: colors.primary, fontSize: typography.small, fontWeight: 'bold' },
  disclaimer: { color: colors.textMuted, fontSize: typography.small, fontStyle: 'italic', marginTop: spacing.md, lineHeight: 16 },
  modelHint: { color: colors.warning, fontSize: typography.small, textAlign: 'center', marginTop: spacing.sm, fontStyle: 'italic' }
});
