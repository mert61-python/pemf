type P = { className?: string }
const s = (className = "") => ({
  className,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
})

export function Logo({ className }: P) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" opacity="0.5" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M12 15.4c-2.4-1.6-3.9-3-3.9-4.7a2.1 2.1 0 0 1 3.9-1.06A2.1 2.1 0 0 1 15.9 10.7c0 1.7-1.5 3.1-3.9 4.7Z" fill="currentColor" />
    </svg>
  )
}

export const Check = ({ className }: P) => (
  <svg {...s(className)}><path d="m5 12 5 5L20 7" /></svg>
)
export const Download = ({ className }: P) => (
  <svg {...s(className)}><path d="M12 3v12m0 0 4-4m-4 4-4-4" /><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></svg>
)
export const ArrowRight = ({ className }: P) => (
  <svg {...s(className)}><path d="M5 12h14m0 0-6-6m6 6-6 6" /></svg>
)
export const Bolt = ({ className }: P) => (
  <svg {...s(className)}><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" /></svg>
)
export const Sparkle = ({ className }: P) => (
  <svg {...s(className)}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.4 2.4M15.3 15.3l2.4 2.4M17.7 6.3l-2.4 2.4M8.7 15.3l-2.4 2.4" /></svg>
)
export const Play = ({ className }: P) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13a1 1 0 0 0 1.5.87l11-6.5a1 1 0 0 0 0-1.74l-11-6.5A1 1 0 0 0 8 5.5Z" /></svg>
)
export const Pause = ({ className }: P) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></svg>
)
export const Close = ({ className }: P) => (
  <svg {...s(className)}><path d="M6 6l12 12M18 6 6 18" /></svg>
)
export const Lock = ({ className }: P) => (
  <svg {...s(className)}><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>
)
export const LogOut = ({ className }: P) => (
  <svg {...s(className)}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="m16 17 5-5-5-5M21 12H9" /></svg>
)
export const Refresh = ({ className }: P) => (
  <svg {...s(className)}><path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5" /></svg>
)
export const Home = ({ className }: P) => (
  <svg {...s(className)}><path d="M3 10.5 12 3l9 7.5M5 9.5V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9.5" /></svg>
)
export const Stethoscope = ({ className }: P) => (
  <svg {...s(className)}><path d="M6 3v5a4 4 0 0 0 8 0V3M4 3h3M13 3h3M10 15a6 6 0 0 0 6 6 4 4 0 0 0 4-4v-2" /><circle cx="20" cy="11" r="2" /></svg>
)
export const Flask = ({ className }: P) => (
  <svg {...s(className)}><path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 18l-5-9V3M7.5 14h9" /></svg>
)

export const Globe = ({ className }: P) => (
  <svg {...s(className)}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.4 3.9 5.6 3.9 9S14.5 18.6 12 21C9.5 18.6 8.1 15.4 8.1 12S9.5 5.4 12 3Z" /></svg>
)
export const Info = ({ className }: P) => (
  <svg {...s(className)}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg>
)
export const ExternalLink = ({ className }: P) => (
  <svg {...s(className)}><path d="M14 4h6v6M20 4l-9 9M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5" /></svg>
)
export const ShieldCheck = ({ className }: P) => (
  <svg {...s(className)}><path d="M12 3 5 6v5c0 4.4 3 8.4 7 9.6 4-1.2 7-5.2 7-9.6V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></svg>
)
export const Cpu = ({ className }: P) => (
  <svg {...s(className)}><rect x="7" y="7" width="10" height="10" rx="2" /><path d="M9.5 3v2M14.5 3v2M9.5 19v2M14.5 19v2M3 9.5h2M3 14.5h2M19 9.5h2M19 14.5h2" /></svg>
)
export const Cloud = ({ className }: P) => (
  <svg {...s(className)}><path d="M7 18a4 4 0 0 1-.5-7.97A5.5 5.5 0 0 1 17 9.5a3.5 3.5 0 0 1 .5 8.5H7Z" /></svg>
)
export const Database = ({ className }: P) => (
  <svg {...s(className)}><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3" /></svg>
)
export const Mail = ({ className }: P) => (
  <svg {...s(className)}><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></svg>
)

export const PROFILE_ICONS = { home: Home, vet: Stethoscope, research: Flask }
export const FEATURE_ICONS = {
  ai: Cpu,
  shield: ShieldCheck,
  db: Database,
  cloud: Cloud,
} as const
