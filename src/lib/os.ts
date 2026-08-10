// Author: mertaygn, cglrgrkn
export type OS = 'windows' | 'macos' | 'linux' | 'other'

/** Tarayıcıdan işletim sistemini sezer (SPA — navigator mevcut). */
export function detectOS(): OS {
  if (typeof navigator === 'undefined') return 'other'
  const s = `${navigator.userAgent} ${navigator.platform}`.toLowerCase()
  if (s.includes('win')) return 'windows'
  if (s.includes('mac') || s.includes('iphone') || s.includes('ipad')) return 'macos'
  if (s.includes('android')) return 'other' // Android UA 'linux' içerir; hedef değil
  if (s.includes('linux') || s.includes('x11')) return 'linux'
  return 'other'
}
