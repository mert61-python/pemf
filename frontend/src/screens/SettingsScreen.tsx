import { useEffect, useState } from "react";
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView, Switch } from "react-native";
import { Card } from "@/components/ui/Card";
import { colors, spacing, typography } from "@/theme/tokens";
import { apiGet, apiPost } from "@/services/apiClient";
import { Save, Mail, Radio, UserCog, Network } from "lucide-react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { updateServiceConfig } from "@/services/config";
import { useUserMode } from "@/context/UserModeContext";

export function SettingsScreen() {
  const { userMode, setUserMode, isExpert } = useUserMode();
  const [settings, setSettings] = useState({
    clinic_name: "",
    email_sender: "",
    email_password: "",
    ble_gateway_mac: "",
    mqtt_broker: "localhost",
    mqtt_port: "1883",
    server_ip: "127.0.0.1"
  });
  
  const [loading, setLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState("");

  const [testEmail, setTestEmail] = useState("");
  const [testStatus, setTestStatus] = useState("");

  useEffect(() => {
    let mounted = true;
    const fetchSettings = async () => {
      try {
        const savedIp = await AsyncStorage.getItem("@pemf_server_ip");
        if (savedIp) {
          setSettings(prev => ({ ...prev, server_ip: savedIp }));
          updateServiceConfig(savedIp);
        }
      } catch (e) {}

      const data = await apiGet<any>("/settings/", {});
      if (mounted && data) {
        setSettings(prev => ({
          ...prev,
          clinic_name: data.clinic_name || "",
          email_sender: data.email_sender || "",
          email_password: data.email_password || "",
          ble_gateway_mac: data.ble_gateway_mac || "",
          mqtt_broker: data.mqtt_broker || "localhost",
          mqtt_port: data.mqtt_port?.toString() || "1883"
        }));
      }
    };
    fetchSettings();
    return () => { mounted = false; };
  }, []);

  const handleSave = async () => {
    setLoading(true);
    setSaveStatus("Kaydediliyor...");
    try {
      await AsyncStorage.setItem("@pemf_server_ip", settings.server_ip);
      updateServiceConfig(settings.server_ip);
    } catch(e) {}
    const result = await apiPost<any>("/settings/", settings, { status: "error" });
    setLoading(false);
    if (result.status === "success") {
      setSaveStatus("Ayarlar başarıyla kaydedildi.");
      setTimeout(() => setSaveStatus(""), 3000);
    } else {
      setSaveStatus("Kaydetme hatası.");
    }
  };

  const handleTestEmail = async () => {
    if (!testEmail) return;
    setTestStatus("Gönderiliyor...");
    const payload = {
      recipient_email: testEmail,
      patient_name: "Test Hasta",
      session_ids: "1", // Örnek olarak ID 1
      additional_message: "Bu bir test e-postasıdır."
    };
    const result = await apiPost<any>("/settings/send_email", payload, { status: "error" });
    if (result.status === "success") {
      setTestStatus("E-posta başarıyla gönderildi!");
    } else {
      setTestStatus("Hata: E-posta gönderilemedi.");
    }
    setTimeout(() => setTestStatus(""), 5000);
  };



  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.headerTitle}>Sistem Ayarları</Text>
      <Text style={styles.intro}>Uygulama tercihleri ve cihaz bağlantı ayarları.</Text>

      <Card style={styles.card}>
        <View style={styles.cardHeader}>
          <UserCog color={colors.primary} size={20} />
          <Text style={styles.cardTitle}>Profil Ayarları</Text>
        </View>
        <Text style={styles.label}>Şu anki mod: {isExpert ? 'Veteriner Hekim' : 'Evcil Hayvan Sahibi'}</Text>
        <TouchableOpacity style={[styles.btnOutline, { marginTop: spacing.md }]} onPress={() => setUserMode(null)}>
          <Text style={styles.btnOutlineText}>Farklı Bir Profile Geçiş Yap</Text>
        </TouchableOpacity>
      </Card>

      {isExpert && (
        <Card style={styles.card}>
          <View style={styles.cardHeader}>
            <Mail color={colors.primary} size={20} />
            <Text style={styles.cardTitle}>E-Posta ve Klinik Bilgileri</Text>
          </View>
          <Text style={styles.label}>Klinik Adı</Text>
          <TextInput 
            style={styles.input} 
            value={settings.clinic_name} 
            onChangeText={val => setSettings({...settings, clinic_name: val})} 
            placeholder="Örn: VetCare Plus" 
          />

          <Text style={styles.label}>Gönderici E-Posta (SMTP Gmail)</Text>
          <TextInput 
            style={styles.input} 
            value={settings.email_sender} 
            onChangeText={val => setSettings({...settings, email_sender: val})} 
            placeholder="klinik@gmail.com" 
            autoCapitalize="none"
            keyboardType="email-address"
          />

          <Text style={styles.label}>E-Posta Şifresi (Uygulama Şifresi)</Text>
          <TextInput 
            style={styles.input} 
            value={settings.email_password} 
            onChangeText={val => setSettings({...settings, email_password: val})} 
            placeholder="••••••••" 
            secureTextEntry 
          />
        </Card>
      )}

      {isExpert && (
        <>
          <Card style={styles.card}>
            <View style={styles.cardHeader}>
              <Radio color={colors.primary} size={20} />
              <Text style={styles.cardTitle}>Kablosuz Cihaz Bağlantısı</Text>
            </View>
            <Text style={styles.label}>Cihaz (Gateway) Adresi</Text>
            <TextInput 
              style={styles.input} 
              value={settings.ble_gateway_mac} 
              onChangeText={val => setSettings({...settings, ble_gateway_mac: val})} 
              placeholder="00:1A:7D:DA:71:13" 
              autoCapitalize="characters"
            />
            <Text style={styles.helperText}>Bırakırsanız cihaz otomatik olarak en yakın sisteme bağlanır.</Text>

            <View style={{ marginTop: spacing.md }}>
              <Text style={styles.label}>MQTT Broker Adresi</Text>
              <TextInput 
                style={styles.input} 
                value={settings.mqtt_broker} 
                onChangeText={val => setSettings({...settings, mqtt_broker: val})} 
                placeholder="localhost veya IP" 
                autoCapitalize="none"
              />
              <Text style={styles.label}>MQTT Portu</Text>
              <TextInput 
                style={styles.input} 
                value={settings.mqtt_port} 
                onChangeText={val => setSettings({...settings, mqtt_port: val})} 
                placeholder="1883" 
                keyboardType="numeric"
              />
            </View>
          </Card>

          <Card style={styles.card}>
            <View style={styles.cardHeader}>
              <Network color={colors.primary} size={20} />
              <Text style={styles.cardTitle}>Mobil Ağ Ayarları</Text>
            </View>
            <Text style={styles.label}>Sunucu (Bilgisayar) IP Adresi</Text>
            <TextInput 
              style={styles.input} 
              value={settings.server_ip} 
              onChangeText={val => setSettings({...settings, server_ip: val})} 
              placeholder="Örn: 192.168.1.100" 
              keyboardType="numeric"
            />
            <Text style={styles.helperText}>Mobil uygulamadan masaüstü programına (API) bağlanmak için yerel IP adresini girin.</Text>
          </Card>

          <View style={styles.actions}>
            <TouchableOpacity style={styles.btnPrimary} onPress={handleSave} disabled={loading}>
              <Save color="#fff" size={16} />
              <Text style={styles.btnPrimaryText}>{loading ? "Kaydediliyor..." : "Ayarları Kaydet"}</Text>
            </TouchableOpacity>
            {saveStatus ? <Text style={styles.statusText}>{saveStatus}</Text> : null}
          </View>
        </>
      )}

      {isExpert && (
        <View style={{ marginTop: spacing.xl }}>
          <Card style={styles.card}>
            <View style={styles.cardHeader}>
              <Mail color={colors.primary} size={20} />
              <Text style={styles.cardTitle}>E-Posta Testi</Text>
            </View>
          <Text style={styles.helperText}>
            Yukarıdaki ayarları kaydettikten sonra sistemin e-posta atabildiğini test edin. 
            (Sistemde en az 1 geçmiş seans kaydı olmalıdır).
          </Text>
          <View style={styles.testRow}>
            <TextInput 
              style={[styles.input, { flex: 1, marginBottom: 0 }]} 
              value={testEmail} 
              onChangeText={setTestEmail} 
              placeholder="Alıcı e-posta adresi girin" 
              autoCapitalize="none"
            />
            <TouchableOpacity style={styles.btnOutline} onPress={handleTestEmail}>
              <Text style={styles.btnOutlineText}>Test Gönder</Text>
            </TouchableOpacity>
          </View>
            {testStatus ? <Text style={styles.statusText}>{testStatus}</Text> : null}
          </Card>
        </View>
      )}

    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingBottom: spacing.xxl
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
  statusText: {
    color: colors.primary,
    fontWeight: '600',
    fontSize: typography.small
  },
  testRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginTop: spacing.sm
  }
});
