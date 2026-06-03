import { StyleSheet, Text, View, TouchableOpacity } from "react-native";
import { PauseCircle, PlayCircle, SlidersHorizontal, BrainCircuit } from "lucide-react-native";
import { CoilControlCard } from "@/components/domain/CoilControlCard";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";
import { colors, spacing, typography } from "@/theme/tokens";
import { DashboardSnapshot } from "@/types/domain";
import { apiPost } from "@/services/apiClient";
import { useState } from "react";

interface ControlScreenProps {
  commandStatus: string;
  onHardwareCommand: (command: string, params: any, msg: string) => void;
  snapshot: DashboardSnapshot;
}

export function ControlScreen({ commandStatus: initialStatus, onHardwareCommand, snapshot }: ControlScreenProps) {
  const [localStatus, setLocalStatus] = useState(initialStatus);
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);

  const presets = [
    { id: "wound_healing", label: "Yara İyileşmesi (Hafif)" },
    { id: "acute_pain", label: "Akut Ağrı (Orta)" },
    { id: "chronic_joint", label: "Kronik Eklem / Osteoartrit" },
    { id: "post_op", label: "Post-operatif İyileşme" }
  ];

  const applyAutoPreset = async () => {
    if (!selectedPreset) return;
    setLocalStatus("AI Reçetesi uygulanıyor...");
    const result = await apiPost<{status: string, parameters?: any}>("/hardware/auto_preset", { target_condition: selectedPreset }, {status: "error"});
    if (result.status === "success") {
      setLocalStatus(`AI Başarılı: ${result.parameters?.freq}Hz, ${result.parameters?.duty}% Duty, ${result.parameters?.duration}Dk uygulandı.`);
    } else {
      setLocalStatus("AI Reçetesi uygulanamadı veya bulunamadı.");
    }
  };
  return (
    <>
      <Card style={styles.panel}>
        <View style={styles.header}>
          <SlidersHorizontal color={colors.primary} size={22} />
          <View>
            <Text style={styles.title}>Manuel Kontrol</Text>
            <Text style={styles.muted}>Tüm bobinleri aynı anda yönet veya teker teker ayarla.</Text>
          </View>
        </View>
        <Text style={styles.commandStatus}>{localStatus}</Text>
        <View style={styles.actions}>
          <Button label="Tüm Bobinleri Başlat" icon={<PlayCircle color={colors.white} size={17} />} onPress={() => onHardwareCommand("start_all_coils", {}, "Tüm bobinleri başlatma komutu gönderildi")} />
          <Button label="Tümünü Durdur" variant="danger" icon={<PauseCircle color={colors.white} size={17} />} onPress={() => onHardwareCommand("stop_all_coils", {}, "Tüm bobinleri durdurma komutu gönderildi")} />
        </View>
      </Card>

      <Card style={styles.panel}>
        <View style={styles.header}>
          <BrainCircuit color={colors.primary} size={22} />
          <View>
            <Text style={styles.title}>AI (Otomatik) Mod</Text>
            <Text style={styles.muted}>Yapay zeka asistanı, seçtiğiniz hedefe uygun literatür destekli frekans ve parametreleri uygular.</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.sm }}>
          {presets.map(p => (
            <TouchableOpacity 
              key={p.id} 
              style={[styles.presetBtn, selectedPreset === p.id && styles.presetBtnActive]}
              onPress={() => setSelectedPreset(p.id)}
            >
              <Text style={[styles.presetText, selectedPreset === p.id && styles.presetTextActive]}>{p.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <View style={{ marginTop: spacing.md, alignSelf: 'flex-start' }}>
          <Button 
            label="Yapay Zeka Reçetesini Başlat" 
            icon={<PlayCircle color={colors.white} size={17} />} 
            onPress={applyAutoPreset} 
            disabled={!selectedPreset}
          />
        </View>
      </Card>

      <ResponsiveGrid minItemWidth={300}>
        {snapshot.coils.map((coil) => (
          <CoilControlCard 
            key={coil.id} 
            coil={coil} 
            onCommand={(cmd, params) => onHardwareCommand(cmd, params, `Bobin ${coil.id} komutu gönderildi`)} 
          />
        ))}
      </ResponsiveGrid>
    </>
  );
}

const styles = StyleSheet.create({
  panel: {
    gap: spacing.lg
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    gap: spacing.md
  },
  title: {
    color: colors.text,
    fontSize: typography.subtitle,
    fontWeight: "800"
  },
  muted: {
    color: colors.textMuted,
    fontSize: typography.body,
    marginTop: spacing.xs
  },
  commandStatus: {
    color: colors.textSubtle,
    fontSize: typography.caption,
    fontWeight: "700"
  },
  actions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md
  },
  presetBtn: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 20,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.bgAlt
  },
  presetBtnActive: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primary
  },
  presetText: {
    color: colors.textMuted,
    fontSize: typography.small,
    fontWeight: "600"
  },
  presetTextActive: {
    color: colors.primary,
    fontWeight: "800"
  }
});
