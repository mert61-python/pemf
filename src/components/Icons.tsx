/* Inline SVG ikon seti — stroke = currentColor, className ile boyut/renk. */
type P = { className?: string }

const base = (className = '') => ({
  className,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.7,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
})

/** PEMF Vet logosu — hedef/nişangâh + kalp (favicon ile aynı fikir). */
export function Logo({ className }: P) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" opacity="0.5" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path
        d="M12 15.4c-2.4-1.6-3.9-3-3.9-4.7a2.1 2.1 0 0 1 3.9-1.06A2.1 2.1 0 0 1 15.9 10.7c0 1.7-1.5 3.1-3.9 4.7Z"
        fill="currentColor"
      />
    </svg>
  )
}

export const Download = ({ className }: P) => (
  <svg {...base(className)}><path d="M12 3v12m0 0 4-4m-4 4-4-4" /><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></svg>
)
export const ArrowRight = ({ className }: P) => (
  <svg {...base(className)}><path d="M5 12h14m0 0-6-6m6 6-6 6" /></svg>
)
export const Check = ({ className }: P) => (
  <svg {...base(className)}><path d="m5 12 5 5L20 7" /></svg>
)
export const Windows = ({ className }: P) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor"><path d="M3 5.5 10.5 4.4v7.1H3V5.5Zm0 13 7.5 1.1v-7H3v5.9ZM11.5 4.3 21 3v8.5h-9.5V4.3Zm0 8.2H21V21l-9.5-1.3v-7.2Z" /></svg>
)
export const Apple = ({ className }: P) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor"><path d="M16.4 12.7c0-2.2 1.8-3.3 1.9-3.4-1-1.5-2.6-1.7-3.2-1.7-1.4-.1-2.6.8-3.3.8-.7 0-1.7-.8-2.8-.8-1.5 0-2.8.8-3.6 2.1-1.5 2.7-.4 6.6 1.1 8.8.7 1.1 1.6 2.3 2.7 2.2 1.1 0 1.5-.7 2.8-.7 1.3 0 1.6.7 2.8.7 1.2 0 1.9-1.1 2.6-2.1.8-1.2 1.2-2.3 1.2-2.4-.1 0-2.4-.9-2.4-3.6ZM14.3 6.1c.6-.7 1-1.7.9-2.7-.9 0-1.9.6-2.5 1.3-.5.6-1 1.6-.9 2.6 1 .1 2-.5 2.5-1.2Z" /></svg>
)
export const Linux = ({ className }: P) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor"><path d="M12 2c-2 0-3.3 1.5-3.3 3.6 0 .7.1 1.2.1 1.8 0 .8-.9 1.4-1.7 2.8-.9 1.5-1.9 3.6-1.9 5.2 0 2.6 1.6 4.4 3.4 5.2l-.5 1.2c-.2.4.1.9.6.9h6.6c.5 0 .8-.5.6-.9l-.5-1.2c1.8-.8 3.4-2.6 3.4-5.2 0-1.6-1-3.7-1.9-5.2-.8-1.4-1.7-2-1.7-2.8 0-.6.1-1.1.1-1.8C15.3 3.5 14 2 12 2Zm-1.6 3.1c.5 0 .9.5.9 1.1s-.4 1.1-.9 1.1-.9-.5-.9-1.1.4-1.1.9-1.1Zm3.2 0c.5 0 .9.5.9 1.1s-.4 1.1-.9 1.1-.9-.5-.9-1.1.4-1.1.9-1.1Z" /></svg>
)
export const Android = ({ className }: P) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor"><path d="M17.6 9.48l1.84-3.18c.16-.31.04-.69-.26-.85a.637.637 0 0 0-.83.22l-1.88 3.24a11.43 11.43 0 0 0-8.94 0L5.65 5.67a.643.643 0 0 0-.87-.2c-.28.18-.37.54-.22.83L6.4 9.48A10.78 10.78 0 0 0 1 18h22a10.78 10.78 0 0 0-5.4-8.52zM7 15.25a1.25 1.25 0 1 1 0-2.5 1.25 1.25 0 0 1 0 2.5zm10 0a1.25 1.25 0 1 1 0-2.5 1.25 1.25 0 0 1 0 2.5z" /></svg>
)
export const Bluetooth = ({ className }: P) => (
  <svg {...base(className)}><path d="m7 8 10 8-5 4V4l5 4L7 16" /></svg>
)
export const Database = ({ className }: P) => (
  <svg {...base(className)}><ellipse cx="12" cy="5.5" rx="7" ry="3" /><path d="M5 5.5v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6M5 11.5v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" /></svg>
)
export const Refresh = ({ className }: P) => (
  <svg {...base(className)}><path d="M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5" /></svg>
)
export const Brain = ({ className }: P) => (
  <svg {...base(className)}><path d="M9.5 3A2.5 2.5 0 0 0 7 5.5 2.5 2.5 0 0 0 5 8v.5A2.5 2.5 0 0 0 4 13a2.5 2.5 0 0 0 1.5 2.3A2.5 2.5 0 0 0 8 18a2.5 2.5 0 0 0 4 .9V4.5A2.5 2.5 0 0 0 9.5 3Zm5 0A2.5 2.5 0 0 1 17 5.5 2.5 2.5 0 0 1 19 8v.5a2.5 2.5 0 0 1 1 4.5 2.5 2.5 0 0 1-1.5 2.3A2.5 2.5 0 0 1 16 18a2.5 2.5 0 0 1-4 .9" /></svg>
)
export const Shield = ({ className }: P) => (
  <svg {...base(className)}><path d="M12 3 5 6v5c0 4.4 3 8.3 7 9.5 4-1.2 7-5.1 7-9.5V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></svg>
)
export const Monitor = ({ className }: P) => (
  <svg {...base(className)}><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></svg>
)
export const Sparkle = ({ className }: P) => (
  <svg {...base(className)}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.4 2.4M15.3 15.3l2.4 2.4M17.7 6.3l-2.4 2.4M8.7 15.3l-2.4 2.4" /></svg>
)
export const Bolt = ({ className }: P) => (
  <svg {...base(className)}><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" /></svg>
)
export const Menu = ({ className }: P) => (
  <svg {...base(className)}><path d="M4 6h16M4 12h16M4 18h16" /></svg>
)
export const Close = ({ className }: P) => (
  <svg {...base(className)}><path d="M6 6l12 12M18 6 6 18" /></svg>
)

export const ICONS = { bluetooth: Bluetooth, database: Database, refresh: Refresh, brain: Brain, shield: Shield, monitor: Monitor }
export type IconName = keyof typeof ICONS
