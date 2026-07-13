export type OS = 'windows' | 'macos' | 'other'

/** Tarayıcıdan işletim sistemini sezer (SPA — navigator mevcut). */
export function detectOS(): OS {
  if (typeof navigator === 'undefined') return 'other'
  const s = `${navigator.userAgent} ${navigator.platform}`.toLowerCase()
  if (s.includes('win')) return 'windows'
  if (s.includes('mac') || s.includes('iphone') || s.includes('ipad')) return 'macos'
  return 'other'
}
