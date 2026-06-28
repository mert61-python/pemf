/**
 * RealtimeChart — Canvas tabanlı yüksek performanslı gerçek zamanlı grafik.
 *
 * Python pyqtgraph'ın çift eksenli (mT + °C) grafik sisteminin React karşılığı.
 * Web'de Canvas 2D API kullanır. Sliding window (2000 veri noktası).
 */
import { useEffect, useRef, useCallback } from "react";
import { View, StyleSheet, Platform, Text } from "react-native";
import Svg, { Line, Polyline, Rect, Text as SvgText, G } from "react-native-svg";
import type { CoilSensorHistory } from "@/types/domain";

// 8 bobin için yüksek kontrastlı, kategorik (birbirinden barizce ayrık) palet.
// Üst üste binen çizgiler ayırt edilebilsin diye kırmızı/mavi/yeşil/turuncu/mor/turkuaz/pembe/sarı.
const COIL_COLORS = [
  "#EF4444", "#3B82F6", "#22C55E", "#F97316",
  "#A855F7", "#06B6D4", "#EC4899", "#EAB308",
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

  // Sürekli 60fps yerine yalnızca veri/ayar/boyut değişince çiz (CPU/batarya tasarrufu).
  useEffect(() => {
    if (Platform.OS !== "web") return;
    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, [draw, width, height]);

  if (Platform.OS !== "web") {
    // React Native (APK/iOS) — react-native-svg ile çapraz-platform grafik (boş View değil).
    return (
      <NativeRealtimeChart
        history={history}
        visibleCoils={visibleCoils}
        showMagnetic={showMagnetic}
        showTemp={showTemp}
        width={width}
        height={height}
      />
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

/** React Native (APK/iOS) için react-native-svg tabanlı grafik — son ~120 nokta downsample. */
function NativeRealtimeChart({
  history, visibleCoils, showMagnetic = true, showTemp = true, width = 800, height = 300,
}: Props) {
  const PAD = { top: 20, right: 60, bottom: 40, left: 60 };
  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;

  const downsample = (pts: any[]) => {
    if (pts.length <= 120) return pts;
    const step = Math.ceil(pts.length / 120);
    const out: any[] = [];
    for (let i = 0; i < pts.length; i += step) out.push(pts[i]);
    return out;
  };

  const series: { id: number; pts: any[] }[] = [];
  let magMin = Infinity, magMax = -Infinity, tempMin = Infinity, tempMax = -Infinity, maxPoints = 0;
  for (const coilId of visibleCoils) {
    const pts = downsample(history[coilId] ?? []);
    series.push({ id: coilId, pts });
    if (pts.length > maxPoints) maxPoints = pts.length;
    for (const p of pts) {
      if (showMagnetic) { if (p.magneticMt < magMin) magMin = p.magneticMt; if (p.magneticMt > magMax) magMax = p.magneticMt; }
      if (showTemp) { if (p.objectTemp < tempMin) tempMin = p.objectTemp; if (p.objectTemp > tempMax) tempMax = p.objectTemp; }
    }
  }

  if (maxPoints < 2) {
    return (
      <View style={[styles.fallback, { width, height }]}>
        <Text style={{ color: "#334155", fontSize: 14 }}>Sensör verisi bekleniyor…</Text>
      </View>
    );
  }

  if (magMin === magMax) { magMin -= 0.1; magMax += 0.1; }
  if (tempMin === tempMax) { tempMin -= 1; tempMax += 1; }
  const magRange = magMax - magMin || 1;
  const tempRange = tempMax - tempMin || 1;

  const xAt = (i: number, n: number) => PAD.left + (n > 1 ? i / (n - 1) : 0) * plotW;
  const yMag = (v: number) => PAD.top + plotH - ((v - magMin) / magRange) * plotH;
  const yTemp = (v: number) => PAD.top + plotH - ((v - tempMin) / tempRange) * plotH;

  return (
    <View style={styles.wrap}>
      <Svg width={width} height={height}>
        <Rect x={0} y={0} width={width} height={height} fill="#0a0f1e" />
        {Array.from({ length: 6 }, (_, i) => {
          const y = PAD.top + (plotH / 5) * i;
          return <Line key={`h${i}`} x1={PAD.left} y1={y} x2={PAD.left + plotW} y2={y} stroke="#1e293b" strokeWidth={1} />;
        })}
        {Array.from({ length: 9 }, (_, i) => {
          const x = PAD.left + (plotW / 8) * i;
          return <Line key={`v${i}`} x1={x} y1={PAD.top} x2={x} y2={PAD.top + plotH} stroke="#1e293b" strokeWidth={1} />;
        })}
        {series.map(({ id, pts }) => {
          if (pts.length < 2) return null;
          const color = COIL_COLORS[(id - 1) % 8];
          const n = pts.length;
          const magStr = pts.map((p, i) => `${xAt(i, n)},${yMag(p.magneticMt)}`).join(" ");
          const tempStr = pts.map((p, i) => `${xAt(i, n)},${yTemp(p.objectTemp)}`).join(" ");
          return (
            <G key={id}>
              {showMagnetic ? <Polyline points={magStr} fill="none" stroke={color} strokeWidth={1.5} /> : null}
              {showTemp ? <Polyline points={tempStr} fill="none" stroke={color} strokeWidth={1} strokeDasharray="4,4" /> : null}
            </G>
          );
        })}
        {Array.from({ length: 5 }, (_, i) => {
          const val = magMin + (magRange / 4) * i;
          const y = PAD.top + plotH - (plotH / 4) * i;
          return <SvgText key={`ml${i}`} x={PAD.left - 6} y={y + 4} fill="#22c55e" fontSize={11} textAnchor="end">{val.toFixed(1)}</SvgText>;
        })}
        {showTemp ? Array.from({ length: 5 }, (_, i) => {
          const val = tempMin + (tempRange / 4) * i;
          const y = PAD.top + plotH - (plotH / 4) * i;
          return <SvgText key={`tl${i}`} x={PAD.left + plotW + 6} y={y + 4} fill="#fb923c" fontSize={11} textAnchor="start">{val.toFixed(1)}</SvgText>;
        }) : null}
        <Rect x={PAD.left} y={PAD.top} width={plotW} height={plotH} fill="none" stroke="#334155" strokeWidth={1} />
      </Svg>
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
