/**
 * RealtimeChart — Canvas tabanlı yüksek performanslı gerçek zamanlı grafik.
 *
 * Python pyqtgraph'ın çift eksenli (mT + °C) grafik sisteminin React karşılığı.
 * Web'de Canvas 2D API kullanır. Sliding window (2000 veri noktası).
 */
import { useEffect, useRef, useCallback } from "react";
import { View, StyleSheet, Platform } from "react-native";
import type { CoilSensorHistory } from "@/types/domain";

const COIL_COLORS = [
  "#FF5252", "#FF4081", "#E040FB", "#7C4DFF",
  "#536DFE", "#448AFF", "#40C4FF", "#18FFFF",
];

interface Props {
  history: CoilSensorHistory;
  visibleCoils: Set<number>;       // coil IDs to display (1-8)
  showMagnetic?: boolean;
  showTemp?: boolean;
  width?: number;
  height?: number;
}

export function RealtimeChart({
  history,
  visibleCoils,
  showMagnetic = true,
  showTemp = true,
  width = 800,
  height = 300,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    const PAD = { top: 20, right: 60, bottom: 40, left: 60 };
    const plotW = W - PAD.left - PAD.right;
    const plotH = H - PAD.top - PAD.bottom;

    // Background
    ctx.fillStyle = "#0a0f1e";
    ctx.fillRect(0, 0, W, H);

    // Grid
    ctx.strokeStyle = "#1e293b";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
      const y = PAD.top + (plotH / 5) * i;
      ctx.beginPath();
      ctx.moveTo(PAD.left, y);
      ctx.lineTo(PAD.left + plotW, y);
      ctx.stroke();
    }
    for (let i = 0; i <= 8; i++) {
      const x = PAD.left + (plotW / 8) * i;
      ctx.beginPath();
      ctx.moveTo(x, PAD.top);
      ctx.lineTo(x, PAD.top + plotH);
      ctx.stroke();
    }

    // Collect ranges
    let magMin = Infinity, magMax = -Infinity;
    let tempMin = Infinity, tempMax = -Infinity;
    let maxPoints = 0;

    for (const coilId of visibleCoils) {
      const pts = history[coilId] ?? [];
      if (pts.length > maxPoints) maxPoints = pts.length;
      for (const p of pts) {
        if (showMagnetic) {
          if (p.magneticMt < magMin) magMin = p.magneticMt;
          if (p.magneticMt > magMax) magMax = p.magneticMt;
        }
        if (showTemp) {
          if (p.objectTemp < tempMin) tempMin = p.objectTemp;
          if (p.objectTemp > tempMax) tempMax = p.objectTemp;
        }
      }
    }

    if (maxPoints < 2) {
      // No data — draw placeholder
      ctx.fillStyle = "#334155";
      ctx.font = "14px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Sensör verisi bekleniyor…", W / 2, H / 2);
      return;
    }

    // Normalize ranges with padding
    if (magMin === magMax) { magMin -= 0.1; magMax += 0.1; }
    if (tempMin === tempMax) { tempMin -= 1; tempMax += 1; }
    const magRange = magMax - magMin || 1;
    const tempRange = tempMax - tempMin || 1;

    // Draw curves for each visible coil
    for (const coilId of visibleCoils) {
      const pts = history[coilId] ?? [];
      if (pts.length < 2) continue;
      const color = COIL_COLORS[(coilId - 1) % 8];

      // Magnetic field — solid line (left axis), per-coil color
      if (showMagnetic) {
        ctx.strokeStyle = color;  // her bobine özgü renk
        ctx.lineWidth = 1.5;
        ctx.setLineDash([]);
        ctx.beginPath();
        for (let i = 0; i < pts.length; i++) {
          const x = PAD.left + (i / (pts.length - 1)) * plotW;
          const y = PAD.top + plotH - ((pts[i].magneticMt - magMin) / magRange) * plotH;
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      // Temperature — dashed line (right axis)
      if (showTemp) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        for (let i = 0; i < pts.length; i++) {
          const x = PAD.left + (i / (pts.length - 1)) * plotW;
          const y = PAD.top + plotH - ((pts[i].objectTemp - tempMin) / tempRange) * plotH;
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    // Left axis labels (mT)
    ctx.fillStyle = "#22c55e";
    ctx.font = "11px Inter, sans-serif";
    ctx.textAlign = "right";
    for (let i = 0; i <= 4; i++) {
      const val = magMin + (magRange / 4) * i;
      const y = PAD.top + plotH - (plotH / 4) * i;
      ctx.fillText(val.toFixed(1), PAD.left - 6, y + 4);
    }
    ctx.fillText("mT", PAD.left - 6, PAD.top - 4);

    // Right axis labels (°C)
    if (showTemp) {
      ctx.fillStyle = "#fb923c";
      ctx.textAlign = "left";
      for (let i = 0; i <= 4; i++) {
        const val = tempMin + (tempRange / 4) * i;
        const y = PAD.top + plotH - (plotH / 4) * i;
        ctx.fillText(val.toFixed(1), PAD.left + plotW + 6, y + 4);
      }
      ctx.fillText("°C", PAD.left + plotW + 6, PAD.top - 4);
    }

    // Border
    ctx.strokeStyle = "#334155";
    ctx.lineWidth = 1;
    ctx.strokeRect(PAD.left, PAD.top, plotW, plotH);

  }, [history, visibleCoils, showMagnetic, showTemp]);

  useEffect(() => {
    if (Platform.OS !== "web") return;
    const animate = () => {
      draw();
      rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [draw]);

  if (Platform.OS !== "web") {
    // React Native (non-web) fallback — just show a placeholder
    return (
      <View style={[styles.fallback, { width, height }]}>
      </View>
    );
  }

  return (
    <View style={styles.wrap}>
      {/* @ts-ignore — canvas is web-only */}
      <canvas
        ref={canvasRef as any}
        width={width}
        height={height}
        style={{ display: "block", width: "100%", height: "auto", borderRadius: 8 }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { borderRadius: 8, overflow: "hidden" },
  fallback: {
    backgroundColor: "#0a0f1e",
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
  },
});
