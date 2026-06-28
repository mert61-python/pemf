import { useState } from "react";
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { Activity, Clock, PlayCircle, Square, Zap, Minus, Plus } from "lucide-react-native";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { colors, radius, spacing, typography } from "@/theme/tokens";
import { CoilStatus } from "@/types/domain";

interface CoilControlCardProps {
  coil: CoilStatus;
  onCommand: (command: string, params: any) => void;
}

export function CoilControlCard({ coil, onCommand }: CoilControlCardProps) {
  const [freq, setFreq] = useState("100.0");
  const [duty, setDuty] = useState("25.0");
  const [phase, setPhase] = useState("0.0");
  const [duration, setDuration] = useState("30");

  const handleStart = () => {
    onCommand("start_coil", {
      coil_id: coil.id,
      freq: parseFloat(freq) || 100,
      duty: parseFloat(duty) || 25,
      phase: parseFloat(phase) || 0,
      duration: parseInt(duration) || 30
    });
  };

  const handleStop = () => {
    onCommand("stop_coil", { coil_id: coil.id });
  };

  return (
    <Card style={styles.card}>
      <View style={styles.header}>
        <View style={styles.titleContainer}>
          <Text style={styles.title}>Bobin {coil.id}</Text>
          <View style={[styles.statusDot, { backgroundColor: coil.running ? colors.success : colors.textMuted }]} />
        </View>
        <Text style={styles.sub}>{coil.running ? "Çalışıyor" : "Beklemede"}</Text>
      </View>

      <View style={styles.controls}>
        <Stepper icon={<Activity color={colors.primary} size={16} />} label="Frekans (Hz)" value={freq} onChange={setFreq} step={1} />
        <Stepper icon={<Zap color={colors.warning} size={16} />} label="Duty (%)" value={duty} onChange={setDuty} step={1} />
        <Stepper icon={<Activity color={colors.cyan} size={16} />} label="Faz (°)" value={phase} onChange={setPhase} step={10} />
        <Stepper icon={<Clock color={colors.violet} size={16} />} label="Süre (Dk)" value={duration} onChange={setDuration} step={1} />
      </View>

      <View style={styles.actions}>
        <View style={{ flex: 1 }}>
          <Button label={coil.running ? "Güncelle" : "Başlat"} icon={<PlayCircle color={colors.white} size={18} />} onPress={handleStart} />
        </View>
        <View style={{ flex: 1 }}>
          <Button label="Durdur" variant="danger" icon={<Square color={colors.white} size={16} fill={colors.white} />} onPress={handleStop} disabled={!coil.running} />
        </View>
      </View>
    </Card>
  );
}

function Stepper({ icon, label, value, onChange, step }: { icon: React.ReactNode, label: string, value: string, onChange: (v: string) => void, step: number }) {
  const handleDec = () => {
    const num = parseFloat(value) || 0;
    onChange(Math.max(0, num - step).toString());
  };
  const handleInc = () => {
    const num = parseFloat(value) || 0;
    onChange((num + step).toString());
  };

  return (
    <View style={styles.stepperContainer}>
      <View style={styles.stepperHeader}>
        {icon}
        <Text style={styles.stepperLabel}>{label}</Text>
      </View>
      <View style={styles.stepperControl}>
        <TouchableOpacity style={styles.stepBtn} onPress={handleDec}>
          <Minus color={colors.textMuted} size={16} />
        </TouchableOpacity>
        <TextInput 
          style={styles.stepperInput} 
          value={value} 
          onChangeText={onChange} 
          keyboardType="numeric" 
          selectTextOnFocus
        />
        <TouchableOpacity style={styles.stepBtn} onPress={handleInc}>
          <Plus color={colors.textMuted} size={16} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: spacing.lg,
    flexBasis: "48%", // Grid layout için
    minWidth: 320,
    borderColor: colors.border,
    borderWidth: 1,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center"
  },
  titleContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm
  },
  title: {
    color: colors.text,
    fontSize: typography.subtitle,
    fontWeight: "800"
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4
  },
  sub: {
    color: colors.textMuted,
    fontSize: typography.small,
    fontWeight: "600",
    textTransform: "uppercase"
  },
  controls: {
    gap: spacing.md
  },
  stepperContainer: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: colors.bgAlt,
    padding: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border
  },
  stepperHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm
  },
  stepperLabel: {
    color: colors.textMuted,
    fontSize: typography.body,
    fontWeight: "600"
  },
  stepperControl: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.bg,
    borderRadius: radius.sm,
    overflow: "hidden"
  },
  stepBtn: {
    padding: spacing.sm,
    backgroundColor: colors.panelSoft
  },
  stepperInput: {
    color: colors.text,
    fontSize: typography.body,
    fontWeight: "700",
    textAlign: "center",
    minWidth: 50,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs
  },
  actions: {
    flexDirection: "row",
    gap: spacing.md
  },
  actionBtn: {
    flex: 1
  }
});
