import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Activity, 
  Zap, 
  Clock, 
  Waves, 
  Info, 
  ShieldCheck,
  ChevronRight,
  Settings2,
  Radio,
  Moon,
  HeartPulse,
  BatteryCharging,
  Layers,
  Stethoscope
} from 'lucide-react';

// Types
type Waveform = 'Sinüs' | 'Kare' | 'Testere dişi';

interface SimulationParams {
  frequency: number;
  intensity: number;
  waveform: Waveform;
  duration: number;
}

export default function App() {
  const [params, setParams] = useState<SimulationParams>({
    frequency: 50,
    intensity: 2,
    waveform: 'Kare',
    duration: 20,
  });
  const [isAnimating, setIsAnimating] = useState(true);

  const biologicalEffects = useMemo(() => {
    let effects = [];
    
    // Frequency logic
    if (params.frequency >= 1 && params.frequency <= 10) {
      effects.push({
        title: "Gevşeme",
        description: "Uyku Düzeni, Stres Azaltma",
        icon: <Moon className="w-8 h-8 text-indigo-500" />,
        color: "bg-indigo-50",
        textColor: "text-indigo-700",
        borderColor: "border-indigo-100"
      });
    } else if (params.frequency > 10 && params.frequency <= 50) {
      effects.push({
        title: "Dolaşım",
        description: "Kan Akışı, Doku İyileşmesi",
        icon: <HeartPulse className="w-8 h-8 text-red-500" />,
        color: "bg-red-50",
        textColor: "text-red-700",
        borderColor: "border-red-100"
      });
    } else if (params.frequency > 50 && params.frequency <= 100) {
      effects.push({
        title: "Enerji",
        description: "Metabolizma, Hücre Aktivasyonu",
        icon: <BatteryCharging className="w-8 h-8 text-emerald-500" />,
        color: "bg-emerald-50",
        textColor: "text-emerald-700",
        borderColor: "border-emerald-100"
      });
    } else if (params.frequency > 100 && params.frequency <= 150) {
      effects.push({
        title: "Ağrı Yönetimi",
        description: "Akut Ağrı, Sinir Modülasyonu",
        icon: <Zap className="w-8 h-8 text-orange-500" />,
        color: "bg-orange-50",
        textColor: "text-orange-700",
        borderColor: "border-orange-100"
      });
    }

    // Intensity logic
    if (params.intensity >= 1 && params.intensity <= 2) {
      effects.push({
        title: "Yüzeysel",
        description: "Deri ve Yüzey Dokular",
        icon: <Layers className="w-8 h-8 text-blue-500" />,
        color: "bg-blue-50",
        textColor: "text-blue-700",
        borderColor: "border-blue-100"
      });
    } else if (params.intensity > 2 && params.intensity <= 5) {
      effects.push({
        title: "Derin Etki",
        description: "Kemik, Eklem ve Derin Kas",
        icon: <Stethoscope className="w-8 h-8 text-purple-500" />,
        color: "bg-purple-50",
        textColor: "text-purple-700",
        borderColor: "border-purple-100"
      });
    }

    return effects;
  }, [params.frequency, params.intensity]);

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center p-4 md:p-8 font-sans">
      <div className="w-full max-w-2xl bg-white rounded-3xl shadow-xl shadow-slate-200/50 overflow-hidden border border-slate-100">
        {/* Header */}
        <header className="bg-blue-50 p-6 text-slate-800 border-b border-blue-100 text-center">
          <h1 className="text-lg md:text-xl font-bold leading-tight">
            EU ISO 13485 Tıbbi Cihazlar yönetmeliğine uyumlu tek DEMA terapi cihazıdır.
          </h1>
        </header>

        {/* Visualization Section - Diagram Style */}
        <div className="relative h-[400px] w-full bg-white overflow-hidden flex items-center justify-center border-b border-slate-100">
          <DiagramVisualization params={params} isAnimating={isAnimating} />
        </div>

        {/* Controls Section */}
        <div className="p-6 space-y-8 bg-white">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2 text-slate-400">
              <Settings2 className="w-4 h-4" />
              <h2 className="text-sm font-bold uppercase tracking-wider">Terapi Parametreleri</h2>
            </div>
            
            {/* Animation Toggle */}
            <div className="flex items-center gap-3">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Animasyon</span>
              <button 
                onClick={() => setIsAnimating(!isAnimating)}
                className={`relative w-10 h-5 rounded-full transition-colors duration-200 focus:outline-none ${isAnimating ? 'bg-blue-600' : 'bg-slate-200'}`}
              >
                <motion.div 
                  animate={{ x: isAnimating ? 20 : 2 }}
                  className="absolute top-1 left-0 w-3 h-3 bg-white rounded-full shadow-sm"
                  transition={{ type: "spring", stiffness: 500, damping: 30 }}
                />
              </button>
            </div>
          </div>

          <div className="grid gap-8">
            {/* Frequency */}
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                  <Activity className="w-4 h-4 text-blue-500" />
                  Frekans
                </label>
                <span className="font-mono text-lg font-bold text-blue-600 bg-blue-50 px-3 py-1 rounded-lg">
                  {params.frequency} <span className="text-xs font-normal text-blue-400">Hz</span>
                </span>
              </div>
              <input
                type="range"
                min="1"
                max="150"
                value={params.frequency}
                onChange={(e) => setParams({ ...params, frequency: parseInt(e.target.value) })}
                className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-blue-600"
              />
              <div className="flex justify-between text-[10px] text-slate-400 font-bold uppercase tracking-tighter">
                <span>1 Hz</span>
                <span>75 Hz</span>
                <span>150 Hz</span>
              </div>
            </div>

            {/* Intensity */}
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                  <Zap className="w-4 h-4 text-amber-500" />
                  Yoğunluk (mT)
                </label>
                <span className="font-mono text-lg font-bold text-amber-600 bg-amber-50 px-3 py-1 rounded-lg">
                  {params.intensity} <span className="text-xs font-normal text-amber-400">mT</span>
                </span>
              </div>
              <input
                type="range"
                min="1"
                max="5"
                step="0.1"
                value={params.intensity}
                onChange={(e) => setParams({ ...params, intensity: parseFloat(e.target.value) })}
                className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-amber-500"
              />
              <div className="flex justify-between text-[10px] text-slate-400 font-bold uppercase tracking-tighter">
                <span>1 mT</span>
                <span>3 mT</span>
                <span>5 mT</span>
              </div>
            </div>

            {/* Waveform & Duration Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                    <Waves className="w-4 h-4 text-indigo-500" />
                    Dalga Formu
                  </label>
                  <WaveformPreview type={params.waveform} />
                </div>
                <div className="space-y-1.5">
                  <select
                    value={params.waveform}
                    onChange={(e) => setParams({ ...params, waveform: e.target.value as Waveform })}
                    className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-sm font-medium focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                  >
                    <option value="Sinüs">Sinüs</option>
                    <option value="Kare">Kare</option>
                    <option value="Testere dişi">Testere dişi</option>
                  </select>
                  <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider ml-1">
                    Seçili Mod: <span className="text-indigo-600">{params.waveform}</span>
                  </p>
                </div>
              </div>

              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                    <Clock className="w-4 h-4 text-emerald-500" />
                    Süre
                  </label>
                  <span className="font-mono text-sm font-bold text-emerald-600 bg-emerald-50 px-2 py-1 rounded-lg">
                    {params.duration} dk
                  </span>
                </div>
                <input
                  type="range"
                  min="10"
                  max="30"
                  value={params.duration}
                  onChange={(e) => setParams({ ...params, duration: parseInt(e.target.value) })}
                  className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Biological Effects Section */}
        <div className="p-6 bg-slate-50 space-y-4">
          <div className="flex items-center gap-2 text-blue-600">
            <Info className="w-4 h-4" />
            <h4 className="text-xs font-bold uppercase tracking-wider">Potansiyel Biyolojik Etkiler</h4>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 min-h-[160px]">
            <AnimatePresence mode="popLayout">
              {biologicalEffects.map((effect, idx) => (
                <motion.div
                  key={effect.title}
                  initial={{ opacity: 0, scale: 0.9, y: 20 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.9, y: -20 }}
                  transition={{ 
                    type: "spring",
                    stiffness: 260,
                    damping: 20,
                    delay: idx * 0.05 
                  }}
                  className={`relative overflow-hidden flex flex-col items-center text-center p-5 rounded-3xl border-2 ${effect.borderColor} ${effect.color} shadow-sm hover:shadow-md transition-all group`}
                >
                  <div className="mb-3 p-4 bg-white rounded-2xl shadow-sm group-hover:scale-110 transition-transform duration-300">
                    {effect.icon}
                  </div>
                  <div className="space-y-1">
                    <h5 className={`text-sm font-black uppercase tracking-tight ${effect.textColor}`}>
                      {effect.title}
                    </h5>
                    <p className="text-[10px] text-slate-500 font-bold leading-tight opacity-80 uppercase tracking-tighter">
                      {effect.description}
                    </p>
                  </div>
                  
                  {/* Decorative background element */}
                  <div className={`absolute -right-4 -bottom-4 w-16 h-16 opacity-10 ${effect.textColor}`}>
                    {effect.icon}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>

        {/* Footer Info */}
        <footer className="p-4 bg-white border-t border-slate-100">
          <p className="text-[10px] text-slate-400 text-center leading-relaxed">
            Bu simülatör eğitim amaçlıdır. DEMA terapisi uygulamadan önce mutlaka bir sağlık profesyoneline danışın. 
            ISO 13485 standartları cihaz üretim kalitesini temsil eder.
          </p>
        </footer>
      </div>
    </div>
  );
}

function DiagramVisualization({ params, isAnimating }: { params: SimulationParams, isAnimating: boolean }) {
  const { frequency, intensity, waveform } = params;
  
  // Center point
  const cx = 300;
  const cy = 180;
  
  // Generate field lines
  const lines = useMemo(() => {
    const lineCount = 12;
    const result = [];
    for (let i = 0; i < lineCount; i++) {
      const angle = (i / lineCount) * Math.PI * 2;
      const length = 250;
      const endX = cx + Math.cos(angle) * length;
      const endY = cy + Math.sin(angle) * length;
      
      // Control points for curved lines
      const cp1x = cx + Math.cos(angle - 0.2) * (length * 0.5);
      const cp1y = cy + Math.sin(angle - 0.2) * (length * 0.5);
      
      result.push({
        id: i,
        path: `M ${cx} ${cy} Q ${cp1x} ${cp1y} ${endX} ${endY}`,
        angle
      });
    }
    return result;
  }, []);

  // Depth calculation based on intensity (Scale 1-5 mT to 1-100 for visualization)
  const scaledIntensity = intensity * 20;
  const depthPercentage = scaledIntensity; // 1-100
  const tissueTop = 240;
  const tissueHeight = 120;
  const currentDepth = (depthPercentage / 100) * tissueHeight;

  // Dynamic values for visualization
  const lineStrokeWidth = 0.5 + (scaledIntensity / 50);
  const particleRadius = 2 + (scaledIntensity / 40);
  const particleDuration = Math.max(0.2, 4 / (frequency / 5 + 1));
  const glowOpacity = scaledIntensity / 150;
  const pulseDuration = Math.max(0.5, 3 / (frequency / 10 + 1));

  // Biological effect triggers
  const isHealingActive = frequency >= 10 && frequency <= 50;
  const bloodFlowSpeed = isHealingActive ? (frequency / 10) : 0;

  return (
    <div className="relative w-full h-full flex items-center justify-center">
      <svg viewBox="0 0 600 400" className="w-full h-full">
        {/* Tissue Section (Doku Kesiti) - Multi-layered Realistic Representation */}
        <defs>
          <linearGradient id="skinGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#f9d5b0" stopOpacity="0.9" />
            <stop offset="50%" stopColor="#e0ac69" stopOpacity="0.7" />
            <stop offset="100%" stopColor="#8d5524" stopOpacity="0.9" />
          </linearGradient>
          <linearGradient id="fatGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#fffde7" stopOpacity="0.8" />
            <stop offset="50%" stopColor="#fbc02d" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#f9a825" stopOpacity="0.8" />
          </linearGradient>
          <linearGradient id="muscleGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#ef5350" stopOpacity="0.8" />
            <stop offset="50%" stopColor="#b71c1c" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#7f0000" stopOpacity="0.8" />
          </linearGradient>

          {/* Heatmap Gradient */}
          <radialGradient id="heatmapGradient">
            <stop offset="0%" stopColor="#ff0000" stopOpacity="0.8" />
            <stop offset="40%" stopColor="#ffab00" stopOpacity="0.6" />
            <stop offset="70%" stopColor="#00b0ff" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#00b0ff" stopOpacity="0" />
          </radialGradient>

          {/* Realistic Textures */}
          <pattern id="skinTexture" x="0" y="0" width="4" height="4" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.5" fill="#8d5524" fillOpacity="0.1" />
          </pattern>
          
          <pattern id="fatTexture" x="0" y="0" width="12" height="12" patternUnits="userSpaceOnUse">
            <circle cx="6" cy="6" r="4" fill="#fdd835" fillOpacity="0.2" />
            <circle cx="2" cy="2" r="2" fill="#fff176" fillOpacity="0.1" />
          </pattern>

          <pattern id="muscleTexture" x="0" y="0" width="30" height="6" patternUnits="userSpaceOnUse">
            <line x1="0" y1="3" x2="30" y2="3" stroke="#d32f2f" strokeWidth="0.5" strokeOpacity="0.2" />
          </pattern>

          <pattern id="cellPattern" x="0" y="0" width="20" height="20" patternUnits="userSpaceOnUse">
            <circle cx="10" cy="10" r="2" fill="#ef5350" fillOpacity="0.1" />
          </pattern>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2.5" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
          <filter id="eFieldGlow">
            <feGaussianBlur stdDeviation="1.5" result="blur"/>
            <feComposite in="SourceGraphic" in2="blur" operator="over"/>
          </filter>
          <filter id="vortexGlow">
            <feGaussianBlur stdDeviation="3" result="blur"/>
            <feColorMatrix type="matrix" values="0 0 0 0 0.98  0 0 0 0 0.75  0 0 0 0 0.14  0 0 0 1 0" />
            <feMerge>
              <feMergeNode in="blur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
          <filter id="concentrationFilter">
            <feGaussianBlur stdDeviation={1.5 + intensity} result="blur"/>
            <feMerge>
              <feMergeNode in="blur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>

        {/* Vector Flow Lines (Focusing into tissue) */}
        {isAnimating && (
          <g>
            {[...Array(8)].map((_, i) => {
              const startX = 150 + i * 40;
              const startY = 100;
              const targetX = 300;
              const targetY = tissueTop + currentDepth;
              return (
                <motion.path
                  key={`flow-line-${i}`}
                  d={`M ${startX} ${startY} Q ${startX} ${tissueTop - 50}, ${targetX} ${targetY}`}
                  fill="none"
                  stroke="#3b82f6"
                  strokeWidth="0.5"
                  strokeOpacity="0.3"
                  strokeDasharray="4 4"
                  animate={{ strokeDashoffset: [20, 0] }}
                  transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                />
              );
            })}
          </g>
        )}

        {/* Tissue Layers */}
        <g>
          {/* Muscle Layer (Deepest) */}
          <rect 
            x="130" y={tissueTop + 40} width="340" height={tissueHeight - 40} 
            fill="url(#muscleGradient)" stroke="#8e0000" strokeWidth="0.5" 
            rx="4"
          />
          <rect 
            x="130" y={tissueTop + 40} width="340" height={tissueHeight - 40} 
            fill="url(#muscleTexture)" className="opacity-40"
            rx="4"
          />
          
          {/* Fat Layer (Middle) */}
          <rect 
            x="130" y={tissueTop + 15} width="340" height="25" 
            fill="url(#fatGradient)" stroke="#f9a825" strokeWidth="0.5" 
            rx="2"
          />
          <rect 
            x="130" y={tissueTop + 15} width="340" height="25" 
            fill="url(#fatTexture)" className="opacity-50"
            rx="2"
          />
          
          {/* Skin Layer (Top) */}
          <rect 
            x="130" y={tissueTop} width="340" height="15" 
            fill="url(#skinGradient)" stroke="#8d5524" strokeWidth="0.5" 
            rx="2"
          />
          <rect 
            x="130" y={tissueTop} width="340" height="15" 
            fill="url(#skinTexture)" className="opacity-30"
            rx="2"
          />
        </g>

        {/* Heatmap Focal Point (Dynamic Pulsing) */}
        {isAnimating && (
          <motion.circle
            cx="300"
            cy={tissueTop + currentDepth}
            r={20 + intensity * 10}
            fill="url(#heatmapGradient)"
            animate={{ 
              scale: [1, 1.2, 1],
              opacity: [0.4, 0.8, 0.4]
            }}
            transition={{ 
              duration: 1 / (frequency / 20 + 0.1), 
              repeat: Infinity, 
              ease: "easeInOut" 
            }}
            className="pointer-events-none"
          />
        )}

        {/* Induced E-Fields (Enhanced Multi-layered Vortexes) */}
        {isAnimating && (
          <g>
            {[...Array(6)].map((_, i) => {
              const vx = 180 + i * 50;
              const vy = tissueTop + 60;
              const baseRadius = 12 + (intensity * 2.5);
              const rotationDuration = Math.max(0.2, 3 / (frequency / 10 + 1));
              
              return (
                <g key={`efield-vortex-${i}`} className="pointer-events-none">
                  {/* Core Pulsating Glow */}
                  <motion.circle
                    cx={vx}
                    cy={vy}
                    r={baseRadius * 0.8}
                    fill="url(#vortexRadial)"
                    animate={{ 
                      opacity: [0.1, 0.3, 0.1],
                      scale: [0.8, 1.2, 0.8]
                    }}
                    transition={{ 
                      duration: rotationDuration * 2, 
                      repeat: Infinity, 
                      ease: "easeInOut" 
                    }}
                  />
                  
                  {/* Outer Vortex Ring (Fast) */}
                  <motion.circle
                    cx={vx}
                    cy={vy}
                    r={baseRadius}
                    fill="none"
                    stroke="#fbbf24"
                    strokeWidth="1.2"
                    strokeDasharray="4 8"
                    animate={{ rotate: 360 }}
                    transition={{ 
                      duration: rotationDuration, 
                      repeat: Infinity, 
                      ease: "linear" 
                    }}
                  />
                  
                  {/* Inner Vortex Ring (Counter-rotating, Slower) */}
                  <motion.circle
                    cx={vx}
                    cy={vy}
                    r={baseRadius * 0.6}
                    fill="none"
                    stroke="#f59e0b"
                    strokeWidth="0.8"
                    strokeDasharray="2 6"
                    animate={{ rotate: -360 }}
                    transition={{ 
                      duration: rotationDuration * 1.5, 
                      repeat: Infinity, 
                      ease: "linear" 
                    }}
                  />

                  {/* Field Vector Indicators (Tiny dots orbiting) */}
                  {[...Array(4)].map((_, dotIdx) => (
                    <motion.circle
                      key={`dot-${dotIdx}`}
                      r="1"
                      fill="#fbbf24"
                      animate={{
                        cx: [
                          vx + Math.cos(dotIdx * Math.PI/2) * baseRadius,
                          vx + Math.cos(dotIdx * Math.PI/2 + Math.PI/2) * baseRadius,
                          vx + Math.cos(dotIdx * Math.PI/2 + Math.PI) * baseRadius,
                          vx + Math.cos(dotIdx * Math.PI/2 + 3*Math.PI/2) * baseRadius,
                          vx + Math.cos(dotIdx * Math.PI/2 + 2*Math.PI) * baseRadius,
                        ],
                        cy: [
                          vy + Math.sin(dotIdx * Math.PI/2) * baseRadius,
                          vy + Math.sin(dotIdx * Math.PI/2 + Math.PI/2) * baseRadius,
                          vy + Math.sin(dotIdx * Math.PI/2 + Math.PI) * baseRadius,
                          vy + Math.sin(dotIdx * Math.PI/2 + 3*Math.PI/2) * baseRadius,
                          vy + Math.sin(dotIdx * Math.PI/2 + 2*Math.PI) * baseRadius,
                        ],
                        opacity: [0, 0.8, 0]
                      }}
                      transition={{
                        duration: rotationDuration,
                        repeat: Infinity,
                        ease: "linear",
                        delay: dotIdx * (rotationDuration / 4)
                      }}
                    />
                  ))}
                </g>
              );
            })}
            
            <defs>
              <radialGradient id="vortexRadial">
                <stop offset="0%" stopColor="#fbbf24" stopOpacity="0.6" />
                <stop offset="100%" stopColor="#fbbf24" stopOpacity="0" />
              </radialGradient>
            </defs>
          </g>
        )}

        {/* Blood Flow Visualization (Interactive) */}
        {isAnimating && isHealingActive && (
          <g>
            {[...Array(15)].map((_, i) => (
              <motion.circle
                key={`blood-${i}`}
                r="1.5"
                fill="#ef4444"
                initial={{ 
                  x: 130 + Math.random() * 340, 
                  y: tissueTop + Math.random() * tissueHeight,
                  opacity: 0 
                }}
                animate={{ 
                  x: [null, 130 + Math.random() * 340],
                  opacity: [0, 0.6, 0]
                }}
                transition={{ 
                  duration: 2 / (bloodFlowSpeed || 1), 
                  repeat: Infinity, 
                  delay: i * 0.2,
                  ease: "linear"
                }}
              />
            ))}
          </g>
        )}

        {/* Healing Pulses (Refined: Expanding from center) */}
        {isAnimating && isHealingActive && (
          <g filter="url(#glow)">
            {[...Array(3)].map((_, i) => (
              <motion.rect
                key={`healing-pulse-${i}`}
                x="130"
                y={tissueTop}
                width="340"
                height={tissueHeight}
                fill="none"
                stroke="#4ade80"
                strokeWidth="2"
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ 
                  scale: [0.8, 1.2],
                  opacity: [0, 0.4, 0],
                  strokeWidth: [4, 1]
                }}
                transition={{ 
                  duration: Math.max(0.5, 2 / (frequency / 20)), 
                  repeat: Infinity, 
                  delay: i * (1 / (frequency / 20 + 0.5)),
                  ease: "easeOut"
                }}
                style={{ originX: "300px", originY: `${tissueTop + tissueHeight / 2}px` }}
              />
            ))}
          </g>
        )}

        {/* Dense Field Lines inside Dielectric Medium */}
        {lines.filter(l => l.angle > Math.PI * 0.2 && l.angle < Math.PI * 0.8).map((line, idx) => (
          <g key={`dielectric-group-${idx}`}>
            <motion.path
              d={line.path}
              fill="none"
              stroke="#3b82f6"
              strokeWidth={lineStrokeWidth * 2}
              strokeDasharray="2 4"
              animate={isAnimating ? {
                strokeDashoffset: [0, -20],
                opacity: [0.2, 0.5, 0.2]
              } : { opacity: 0.3 }}
              transition={{
                duration: 1,
                repeat: Infinity,
                ease: "linear"
              }}
              clipPath={`inset(${tissueTop}px 0 0 0)`}
              className="pointer-events-none"
            />
            {/* Interference Pattern Line (Subtle) */}
            <motion.path
              d={line.path}
              fill="none"
              stroke="#60a5fa"
              strokeWidth={lineStrokeWidth}
              strokeDasharray="1 5"
              animate={isAnimating ? {
                strokeDashoffset: [0, 20],
                opacity: [0.1, 0.3, 0.1]
              } : { opacity: 0.1 }}
              transition={{
                duration: 1.5,
                repeat: Infinity,
                ease: "linear"
              }}
              clipPath={`inset(${tissueTop}px 0 0 0)`}
              className="pointer-events-none"
            />
          </g>
        ))}
        
        {/* Dielectric Field Concentration (Below Tissue) */}
        <g filter="url(#concentrationFilter)">
          <defs>
            <linearGradient id="concentrationGlow" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.2 + intensity / 10} />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
            </linearGradient>
          </defs>
          <motion.rect
            x="130"
            y={tissueTop + tissueHeight}
            width="340"
            height={40 + intensity * 4}
            fill="url(#concentrationGlow)"
            animate={isAnimating ? {
              opacity: [0.3, 0.7, 0.3],
              height: [40 + intensity * 3, 40 + intensity * 5, 40 + intensity * 3]
            } : { opacity: 0.4, height: 40 + intensity * 4 }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            className="pointer-events-none"
          />
          {/* Dense Exit Lines */}
          {lines.filter(l => l.angle > Math.PI * 0.4 && l.angle < Math.PI * 0.6).map((line, idx) => (
            <motion.path
              key={`exit-${idx}`}
              d={line.path}
              fill="none"
              stroke="#2563eb"
              strokeWidth={lineStrokeWidth * 1.5}
              strokeDasharray="1 3"
              animate={isAnimating ? {
                strokeDashoffset: [0, -10],
                opacity: [0.4, 0.8, 0.4]
              } : { opacity: 0.5 }}
              transition={{ duration: 0.5, repeat: Infinity, ease: "linear" }}
              clipPath={`inset(${tissueTop + tissueHeight}px 0 0 0)`}
              className="pointer-events-none"
            />
          ))}
        </g>

        {/* Waveform Oscilloscope (Subtle Center Visualization) */}
        <g transform={`translate(${cx - 50}, ${cy - 20})`}>
          <rect width="100" height="40" rx="8" fill="#f8fafc" fillOpacity="0.4" stroke="#e2e8f0" strokeWidth="1" />
          <mask id="waveformMask">
            <rect width="100" height="40" rx="8" fill="white" />
          </mask>
          <g mask="url(#waveformMask)">
            <motion.path
              d={useMemo(() => {
                const points = 50;
                const w = 100;
                const h = 40;
                let path = `M 0 ${h/2}`;
                for (let i = 0; i <= points; i++) {
                  const x = (i / points) * w;
                  let y = h/2;
                  const phase = (i / points) * Math.PI * 4;
                  
                  if (waveform === 'Sinüs') {
                    y = h/2 + Math.sin(phase) * 12;
                  } else if (waveform === 'Kare') {
                    y = h/2 + (Math.sin(phase) >= 0 ? -12 : 12);
                  } else { // Testere dişi
                    y = h/2 + (((i / points) * 4) % 2 - 1) * 12;
                  }
                  path += ` L ${x} ${y}`;
                }
                return path;
              }, [waveform])}
              fill="none"
              stroke="#3b82f6"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              animate={isAnimating ? {
                x: [0, -25],
              } : { x: 0 }}
              transition={{
                duration: Math.max(0.2, 2 / (frequency / 10 + 1)),
                repeat: Infinity,
                ease: "linear"
              }}
              className="opacity-80"
            />
          </g>
          <text x="50" y="35" textAnchor="middle" className="text-[6px] font-bold fill-slate-400 uppercase tracking-tighter">
            {waveform} Sinyali
          </text>
        </g>

        {/* Field Lines */}
        {lines.map((line) => (
          <g key={line.id}>
            {/* Glow Path (Pulsing Shimmer) */}
            <motion.path
              d={line.path}
              fill="none"
              stroke="#93c5fd"
              strokeWidth={lineStrokeWidth * 4}
              animate={isAnimating ? { 
                opacity: [glowOpacity * 0.3, glowOpacity, glowOpacity * 0.3],
                strokeWidth: [lineStrokeWidth * 3, lineStrokeWidth * 6, lineStrokeWidth * 3]
              } : { 
                opacity: glowOpacity * 0.5,
                strokeWidth: lineStrokeWidth * 4
              }}
              transition={{
                duration: pulseDuration,
                repeat: Infinity,
                ease: "easeInOut",
                delay: line.id * 0.1
              }}
              className="pointer-events-none"
            />
            {/* Main Path */}
            <motion.path
              d={line.path}
              fill="none"
              stroke="#60a5fa"
              strokeWidth={lineStrokeWidth}
              animate={isAnimating ? { 
                strokeWidth: lineStrokeWidth,
                opacity: [0.4, 0.7, 0.4]
              } : { 
                strokeWidth: lineStrokeWidth,
                opacity: 0.5
              }}
              transition={{
                duration: pulseDuration * 1.5,
                repeat: Infinity,
                ease: "easeInOut",
                delay: line.id * 0.15
              }}
              className="opacity-60"
            />
            {/* Moving Particles */}
            {isAnimating && (
              <motion.circle
                r={particleRadius}
                fill="#2563eb"
                animate={{
                  offsetDistance: ["0%", "100%"],
                  r: particleRadius
                }}
                transition={{
                  duration: particleDuration,
                  repeat: Infinity,
                  ease: "linear",
                  delay: line.id * (particleDuration / 12)
                }}
                style={{
                  offsetPath: `path("${line.path}")`
                }}
              />
            )}
          </g>
        ))}

        {/* Depth Indicator (Etki Derinliği) */}
        <g>
          {/* Vertical Green Line */}
          <motion.line
            x1="480"
            y1={tissueTop}
            x2="480"
            y2={tissueTop + currentDepth}
            stroke="#16a34a"
            strokeWidth="3"
            animate={{ y2: tissueTop + currentDepth }}
          />
          {/* Horizontal indicator at the end */}
          <motion.line
            x1="475"
            y1={tissueTop + currentDepth}
            x2="485"
            y2={tissueTop + currentDepth}
            stroke="#16a34a"
            strokeWidth="3"
            animate={{ y1: tissueTop + currentDepth, y2: tissueTop + currentDepth }}
          />
        </g>
      </svg>

      {/* Dose-Meter (Tahmini İndüklenen Elektrik Alan - V/m) */}
      <div className="absolute right-4 top-4 bottom-4 w-20 bg-slate-900/95 backdrop-blur-md border border-slate-700 rounded-2xl p-3 flex flex-col items-center shadow-2xl overflow-hidden">
        <div className="flex flex-col items-center gap-1.5 mb-4">
          <div className="p-1.5 bg-amber-500/10 rounded-lg">
            <Zap className="w-4 h-4 text-amber-400 animate-pulse" />
          </div>
          <div className="flex flex-col items-center">
            <span className="text-[8px] font-black text-slate-400 uppercase tracking-[0.15em] text-center leading-tight">İndüklenen</span>
            <span className="text-[8px] font-black text-slate-400 uppercase tracking-[0.15em] text-center leading-tight">E-Alan</span>
          </div>
        </div>
        
        <div className="flex-1 w-full flex gap-1">
          {/* Gauge Ticks */}
          <div className="flex flex-col justify-between h-full py-1">
            {[...Array(11)].map((_, i) => (
              <div key={i} className="flex items-center gap-1">
                <div className={`h-[1px] ${i % 5 === 0 ? 'w-2 bg-slate-500' : 'w-1 bg-slate-700'}`} />
                {i % 5 === 0 && (
                  <span className="text-[6px] font-mono text-slate-500">{(10 - i) * 10}</span>
                )}
              </div>
            ))}
          </div>

          <div className="flex-1 h-full bg-slate-800/50 rounded-lg relative overflow-hidden border border-slate-700/50">
            {/* Active Bar with Segmented Look */}
            <motion.div 
              className="absolute bottom-0 w-full bg-gradient-to-t from-blue-500 via-emerald-500 via-amber-500 to-red-500"
              initial={{ height: 0 }}
              animate={{ 
                height: `${Math.min(100, (frequency * intensity) / 5)}%`,
              }}
              transition={{ type: "spring", stiffness: 80, damping: 15 }}
            >
              {/* Scanline Effect */}
              <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.1)_1px,transparent_1px)] bg-[size:100%_4px]" />
              
              {/* Top Glow */}
              <div className="absolute top-0 left-0 right-0 h-4 bg-white/20 blur-sm" />
            </motion.div>

            {/* Glass Overlay */}
            <div className="absolute inset-0 bg-gradient-to-r from-white/5 to-transparent pointer-events-none" />
          </div>
        </div>

        <div className="mt-4 w-full bg-slate-800 rounded-lg p-2 border border-slate-700 flex flex-col items-center">
          <span className="font-mono text-xs font-bold text-emerald-400 tracking-tighter">
            {((frequency * intensity) / 100).toFixed(2)}
          </span>
          <span className="text-[7px] font-black text-slate-500 uppercase tracking-widest">V/m</span>
        </div>
        
        {/* Status Indicator */}
        <div className="mt-2 flex items-center gap-1">
          <div className={`w-1 h-1 rounded-full ${isAnimating ? 'bg-emerald-500 shadow-[0_0_5px_rgba(16,185,129,0.5)]' : 'bg-slate-600'}`} />
          <span className="text-[6px] font-bold text-slate-500 uppercase">Canlı</span>
        </div>
      </div>

      {/* Signal Monitor Overlay */}
      <div className="absolute top-4 left-4 bg-white/80 backdrop-blur-sm border border-slate-200 rounded-xl p-3 shadow-sm w-32">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[8px] font-bold text-slate-400 uppercase tracking-widest">Sinyal İzleme</span>
          <div className={`w-1.5 h-1.5 rounded-full ${isAnimating ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'}`} />
        </div>
        <div className="h-10 w-full bg-slate-50 rounded-lg border border-slate-100 overflow-hidden flex items-center justify-center">
          <AnimatedSignal waveform={waveform} frequency={frequency} isAnimating={isAnimating} />
        </div>
        <div className="mt-1 text-[7px] font-mono text-slate-400 text-center uppercase">
          {waveform} Modu
        </div>
      </div>

      {/* Labels - Absolute Positioned HTML for better styling */}
      
      {/* Central Node */}
      <motion.div 
        className="absolute bg-blue-600 rounded-full p-4 shadow-lg shadow-blue-200 z-10"
        style={{ left: `${cx}px`, top: `${cy}px`, transform: 'translate(-50%, -50%)' }}
        animate={isAnimating ? { 
          scale: [1, 1 + (frequency / 400), 1],
          boxShadow: [
            "0 10px 15px -3px rgba(59, 130, 246, 0.3)",
            `0 20px 25px -5px rgba(59, 130, 246, ${0.3 + intensity / 200})`,
            "0 10px 15px -3px rgba(59, 130, 246, 0.3)"
          ]
        } : {
          scale: 1,
          boxShadow: "0 10px 15px -3px rgba(59, 130, 246, 0.3)"
        }}
        transition={{ 
          duration: Math.max(0.1, 1 / (frequency / 10 + 1)), 
          repeat: Infinity,
          ease: "easeInOut"
        }}
      >
        <Radio className="w-8 h-8 text-white" />
      </motion.div>

      {/* Doku Kesiti Label */}
      <div 
        className="absolute left-[130px] top-[240px] -translate-y-1/2 -translate-x-4 bg-white border-2 border-red-500 text-red-600 text-[10px] font-bold px-3 py-1 rounded-full shadow-sm"
      >
        DOKU KESİTİ
      </div>

      {/* Tissue Layer Labels */}
      <div className="absolute top-[242px] left-[135px] flex flex-col gap-[18px]">
        <span className="text-[5px] font-bold text-orange-800/60 uppercase tracking-tighter">Deri</span>
        <span className="text-[5px] font-bold text-yellow-800/60 uppercase tracking-tighter">Yağ</span>
        <span className="text-[5px] font-bold text-red-800/60 uppercase tracking-tighter">Kas/Doku</span>
      </div>

      {/* Induced E-Field Legend */}
      <div className="absolute top-[330px] left-[150px] flex items-center gap-1.5 bg-amber-50/80 backdrop-blur-sm px-2 py-1 rounded border border-amber-100">
        <div className="w-1.5 h-1.5 bg-amber-400 rounded-full animate-spin" style={{ animationDuration: `${Math.max(0.5, 3 / (frequency / 10 + 1))}s` }} />
        <span className="text-[7px] font-bold text-amber-600 uppercase tracking-tighter">İndüklenen E-Alan (Girdap Akımları)</span>
      </div>

      {/* Dielectric Info Badge */}
      <div className="absolute top-[255px] left-[150px] flex items-center gap-1.5 bg-red-50/80 backdrop-blur-sm px-2 py-1 rounded border border-red-100">
        <div className="w-1.5 h-1.5 bg-red-400 rounded-full animate-pulse" />
        <span className="text-[7px] font-bold text-red-500 uppercase tracking-tighter">Yoğun Alan Dağılımı</span>
      </div>

      {/* Field Concentration Zone Label */}
      <div className="absolute top-[370px] left-[300px] -translate-x-1/2 flex items-center gap-1.5 bg-blue-50/60 backdrop-blur-sm px-2 py-0.5 rounded border border-blue-100">
        <div className="w-1 h-1 bg-blue-400 rounded-full animate-ping" />
        <span className="text-[6px] font-bold text-blue-500 uppercase tracking-widest">Yoğun Alan Bölgesi (Dielektrik Çıkış)</span>
      </div>

      {/* Etki Derinliği Label */}
      <div 
        className="absolute left-[480px] top-[360px] -translate-x-1/2 bg-white border-2 border-green-600 text-green-700 text-[10px] font-bold px-3 py-1 rounded-full shadow-sm whitespace-nowrap"
      >
        ETKİ DERİNLİĞİ: {intensity} mT
      </div>

      {/* Effect Type Indicator (Yüzeysel vs Derin) */}
      <div className="absolute left-[480px] top-[395px] -translate-x-1/2 flex flex-col items-center gap-1">
        <motion.div 
          animate={{ 
            backgroundColor: intensity <= 2 ? '#3b82f6' : '#1d4ed8',
            scale: intensity <= 2 ? 1 : 1.05,
            boxShadow: intensity <= 2 
              ? "0 4px 6px -1px rgba(59, 130, 246, 0.2)" 
              : "0 10px 15px -3px rgba(29, 78, 216, 0.3)"
          }}
          className="px-4 py-1.5 rounded-xl border border-white/20 backdrop-blur-md flex items-center gap-2 transition-colors"
        >
          {intensity <= 2 ? (
            <Layers className="w-3 h-3 text-white" />
          ) : (
            <Stethoscope className="w-3 h-3 text-white" />
          )}
          <span className="text-[9px] font-black text-white uppercase tracking-widest">
            {intensity <= 2 ? 'Yüzeysel Etki' : 'Derin Etki'}
          </span>
        </motion.div>
        
        {/* Progress-style indicator */}
        <div className="flex gap-1">
          <motion.div 
            animate={{ opacity: intensity <= 2 ? 1 : 0.3 }}
            className="h-1 w-8 rounded-full bg-blue-400" 
          />
          <motion.div 
            animate={{ opacity: intensity > 2 ? 1 : 0.3 }}
            className="h-1 w-8 rounded-full bg-blue-700" 
          />
        </div>
      </div>

      {/* Legend (Etki Derinliği Bilgisi) */}
      <div className="absolute bottom-12 left-[130px] flex gap-4 bg-white/50 backdrop-blur-sm p-2 rounded-lg border border-slate-100">
        <div className="flex items-center gap-1.5">
          <div className={`w-2 h-2 rounded-full transition-colors ${intensity <= 2 ? 'bg-blue-500 ring-2 ring-blue-200' : 'bg-slate-300'}`} />
          <span className={`text-[8px] font-bold uppercase tracking-wider ${intensity <= 2 ? 'text-blue-600' : 'text-slate-400'}`}>1-2 mT: Yüzeysel</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className={`w-2 h-2 rounded-full transition-colors ${intensity > 2 ? 'bg-blue-600 ring-2 ring-blue-200' : 'bg-slate-300'}`} />
          <span className={`text-[8px] font-bold uppercase tracking-wider ${intensity > 2 ? 'text-blue-700' : 'text-slate-400'}`}>3-5 mT: Derin</span>
        </div>
      </div>

      {/* Disclaimer */}
      <div className="absolute bottom-4 right-4 text-[9px] text-slate-400 italic">
        * Görselleştirme ve etkiler eğitim amaçlıdır.
      </div>
    </div>
  );
}

function WaveformPreview({ type }: { type: Waveform }) {
  const width = 40;
  const height = 20;
  
  const d = useMemo(() => {
    if (type === 'Sinüs') {
      return `M 2 ${height/2} Q ${width/4} 2, ${width/2} ${height/2} T ${width-2} ${height/2}`;
    } else if (type === 'Kare') {
      return `M 2 ${height-4} L 2 4 L ${width/2} 4 L ${width/2} ${height-4} L ${width-2} ${height-4}`;
    } else { // Testere dişi
      return `M 2 ${height-4} L ${width/2} 4 L ${width/2} ${height-4} L ${width-2} 4`;
    }
  }, [type]);

  return (
    <div className="bg-indigo-50 p-1.5 rounded-lg border border-indigo-100/50">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="text-indigo-500">
        <path d={d} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

function AnimatedSignal({ waveform, frequency, isAnimating }: { waveform: Waveform, frequency: number, isAnimating: boolean }) {
  const width = 120;
  const height = 40;
  const points = 50;
  
  const pathData = useMemo(() => {
    let d = `M 0 ${height / 2}`;
    const step = width / points;
    const freqFactor = frequency / 10;
    
    for (let i = 0; i <= points; i++) {
      const x = i * step;
      const t = (i / points) * freqFactor * Math.PI * 2;
      let y = height / 2;
      const amp = height / 3;

      if (waveform === 'Sinüs') {
        y = height / 2 + Math.sin(t) * amp;
      } else if (waveform === 'Kare') {
        y = height / 2 + (Math.sin(t) >= 0 ? 1 : -1) * amp;
      } else if (waveform === 'Testere dişi') {
        const phase = (t % (Math.PI * 2)) / (Math.PI * 2);
        y = height / 2 + (phase * 2 - 1) * amp;
      }
      d += ` L ${x} ${y}`;
    }
    return d;
  }, [waveform, frequency]);

  return (
    <svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <motion.path
        d={pathData}
        fill="none"
        stroke="#3b82f6"
        strokeWidth="2"
        animate={isAnimating ? {
          x: [0, -width / (frequency / 10)],
        } : { x: 0 }}
        transition={{
          duration: 1 / (frequency / 20 + 0.1),
          repeat: Infinity,
          ease: "linear"
        }}
      />
      {/* Duplicate for seamless loop */}
      <motion.path
        d={pathData}
        fill="none"
        stroke="#3b82f6"
        strokeWidth="2"
        animate={isAnimating ? {
          x: [width / (frequency / 10), 0],
        } : { x: width / (frequency / 10) }}
        transition={{
          duration: 1 / (frequency / 20 + 0.1),
          repeat: Infinity,
          ease: "linear"
        }}
      />
    </svg>
  );
}
