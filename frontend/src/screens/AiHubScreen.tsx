import { useState, useEffect, useRef } from "react";
import { StyleSheet, Text, View, Image, ScrollView, ActivityIndicator, TouchableOpacity, TextInput, Alert, Platform } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { Camera, Image as ImageIcon, Sparkles, Stethoscope, ScissorsSquare as Scan, Activity, Microscope, CheckCircle2, Video } from "lucide-react-native";
import { CameraView, useCameraPermissions } from 'expo-camera';
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { colors, radius, spacing, typography } from "@/theme/tokens";
import { useToast } from "@/components/ui/ToastProvider";
import { apiPost } from "@/services/apiClient";
import { serviceConfig } from "@/services/config";
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
          
          if (score === 0) {
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
                <Text style={[styles.title, { color: score > 3 ? colors.danger : colors.success }]}>{score} / 10</Text>
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
                  <View style={[styles.startTherapyBtn, { backgroundColor: colors.danger }]}>
                    <Stethoscope color="#fff" size={20} />
                    <Text style={styles.startTherapyText}>Veteriner Kliniğini Ara</Text>
                  </View>
                )}
              </View>

              {treatmentStatus ? <Text style={[styles.statusText, { textAlign: 'center', marginTop: spacing.md }]}>{treatmentStatus}</Text> : null}
            </View>
          );
        })()}
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
        </View>
      )}
    </Card>
  );
}

function VisionModule({ endpoint, title, subtitle }: { endpoint: string, title: string, subtitle: string }) {
  const { showToast } = useToast();
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [imageFile, setImageFile] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  
  const [isLive, setIsLive] = useState(false);
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<any>(null);
  const liveIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (isLive) {
      if (!permission?.granted) requestPermission();
      // Canlı yayın döngüsü (2 saniyede bir frame alır)
      liveIntervalRef.current = setInterval(async () => {
        if (cameraRef.current && !loading) {
          try {
            const photo = await cameraRef.current.takePictureAsync({ quality: 0.3, base64: true });
            if (photo) {
              setImageUri(photo.uri);
              analyzeImage(photo.uri);
            }
          } catch (e) {
            console.log("Kamera okuma hatası", e);
          }
        }
      }, 2000);
    } else {
      if (liveIntervalRef.current) clearInterval(liveIntervalRef.current);
    }
    return () => {
      if (liveIntervalRef.current) clearInterval(liveIntervalRef.current);
    };
  }, [isLive, permission, loading]);

  const toggleLive = () => {
    setIsLive(!isLive);
    setImageUri(null);
    setImageBase64(null);
    setImageFile(null);
    setResult(null);
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
    setLoading(true);
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
        formData.append("file", { uri: uriToAnalyze, name: "upload.jpg", type: "image/jpeg" } as any);
      }
      const response = await fetch(serviceConfig.apiBaseUrl + "/ai" + endpoint, {
        method: "POST",
        body: formData,
        headers: { "Accept": "application/json" }
      });
      const data = await response.json();
      if (response.ok && data.status === "success") {
        setResult(data);
        if (isLive) setImageUri(`data:image/jpeg;base64,${data.image_base64}`); // overlay updated
      }
      else if (!isLive) showToast(data?.detail || "Analiz sırasında hata oluştu.", "error");
    } catch (error) {
      if (!isLive) showToast("Ağ veya sunucu hatası.", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card style={styles.card}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.subtitle}>{subtitle}</Text>
      
      <View style={styles.imagePreviewContainer}>
        {isLive ? (
          <View style={styles.cameraContainer}>
            <CameraView ref={cameraRef} style={styles.cameraView} facing="back" />
            {result?.image_base64 && (
              <Image source={{ uri: `data:image/jpeg;base64,${result.image_base64}` }} style={styles.cameraOverlay} />
            )}
            <View style={styles.liveIndicator}>
              <View style={styles.liveDot} />
              <Text style={styles.liveText}>CANLI ANALİZ</Text>
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

      <View style={styles.btnRow}>
        <View style={{ flex: 1 }}>
          <Button label="Galeriden Seç" icon={<ImageIcon color={colors.white} size={16} />} onPress={pickImage} disabled={isLive} />
        </View>
        <View style={{ flex: 1 }}>
          <Button label="Fotoğraf Çek" icon={<Camera color={colors.white} size={16} />} onPress={takePhoto} disabled={isLive} />
        </View>
        <View style={{ flex: 1 }}>
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
        </View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  tabContainer: { flexDirection: "row", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm },
  tabBtn: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: 9999, backgroundColor: colors.bgAlt, gap: spacing.sm, borderWidth: 1, borderColor: colors.border },
  tabBtnActive: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  tabLabel: { color: colors.textMuted, fontSize: typography.body, fontWeight: "700" },
  tabLabelActive: { color: colors.primary },
  content: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xl },
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
  imagePreview: { width: "100%", height: "100%", resizeMode: "contain" },
  cameraContainer: { width: "100%", height: "100%", position: "relative" },
  cameraView: { flex: 1 },
  cameraOverlay: { position: "absolute", top: 0, left: 0, width: "100%", height: "100%", resizeMode: "contain", opacity: 0.8 },
  liveIndicator: { position: "absolute", top: 12, right: 12, flexDirection: "row", alignItems: "center", backgroundColor: "rgba(0,0,0,0.6)", paddingHorizontal: 8, paddingVertical: 4, borderRadius: 12, gap: 6 },
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
  statusText: { color: colors.primary, fontWeight: 'bold' }
});
