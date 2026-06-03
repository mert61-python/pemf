import { View } from "react-native";
import Svg, { Polyline, Rect } from "react-native-svg";
import { colors } from "@/theme/tokens";

interface SparklineProps {
  values: number[];
  height?: number;
  color?: string;
}

export function Sparkline({ values, height = 120, color = colors.primary }: SparklineProps) {
  const width = 320;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(1, max - min);
  const points = values
    .map((value, index) => {
      const x = (index / Math.max(1, values.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 18) - 9;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <View>
      <Svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`}>
        <Rect x="0" y="0" width={width} height={height} rx="8" fill={colors.bgAlt} />
        <Polyline points={points} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      </Svg>
    </View>
  );
}
