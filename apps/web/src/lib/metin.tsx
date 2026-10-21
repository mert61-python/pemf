// Author: mertaygn, cglrgrkn
import { Fragment, type ReactNode } from 'react'

/** Çeviri şablonundaki `{{ad}}` işaretçilerini verilen düğümlerle (bağlantı, vurgu) değiştirir; kalan metin aynen.
 *  Şablon `t('anahtar', { skipInterpolation: true })` ile ham alınır → İngilizce kelime sırası farklı olsa da bağlantı yerinde kalır. */
export function baglantiliMetin(sablon: string, yerler: Record<string, ReactNode>): ReactNode[] {
  return sablon
    .split(/(\{\{\w+\}\})/)
    .filter((p) => p !== '')
    .map((p, i) => {
      const m = /^\{\{(\w+)\}\}$/.exec(p)
      return m && m[1] in yerler ? <Fragment key={i}>{yerler[m[1]]}</Fragment> : p
    })
}
