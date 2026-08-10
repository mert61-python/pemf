// Author: mertaygn, cglrgrkn
import { describe, expect, it } from 'vitest'
import { aggregate } from '../downloadStats'

/* İNDİRME SAYACI (2026-08-06) — toplama mantığı.
   Kritik kural: RUNTIME PAKETLERİ (base.zip, model zip'leri, manifest) SAYILMAZ. Onlar
   client'ın kendi çektiği bileşenlerdir; sayılsalardı sayaç anlamsızca şişerdi. */

const rel = (assets: Array<[string, number]>) => ({
  assets: assets.map(([name, download_count]) => ({ name, download_count })),
})

describe('downloadStats.aggregate', () => {
  it('kurulum dosyalarını platforma göre toplar', () => {
    const v = aggregate([
      rel([['PEMFVetClient-Setup.exe', 4], ['PEMF_Vet_Mobil.apk', 2]]),
      rel([['PEMFVetClient-Setup.exe', 7]]),
    ])
    expect(v.windows).toBe(11)
    expect(v.android).toBe(2)
    expect(v.total).toBe(13)
  })

  it('RUNTIME PAKETLERİNİ saymaz (base.zip / model zip / manifest)', () => {
    const v = aggregate([
      rel([
        ['PEMFVetClient-Setup.exe', 5],
        ['base.zip', 9999],
        ['research.zip', 4321],
        ['manifest.json', 777],
        ['client-latest.json', 12],
      ]),
    ])
    expect(v.windows).toBe(5)
    expect(v.total).toBe(5)
  })

  it('macOS/Linux paketleri ayrı kovada', () => {
    const v = aggregate([
      rel([['PEMFVetClient.dmg', 1], ['PEMFVetClient.deb', 2],
           ['PEMFVetClient.AppImage', 3], ['PEMFVetClient.rpm', 4]]),
    ])
    expect(v.other).toBe(10)
    expect(v.windows).toBe(0)
    expect(v.total).toBe(10)
  })

  it('bozuk/eksik sayıları yok sayar (NaN, negatif, yok)', () => {
    const v = aggregate([
      { assets: [
        { name: 'PEMFVetClient-Setup.exe', download_count: undefined },
        { name: 'PEMFVetClient-Setup.exe', download_count: -5 },
        { name: 'PEMFVetClient-Setup.exe', download_count: 3 },
        { name: undefined, download_count: 100 },
      ] },
    ])
    expect(v.windows).toBe(3)
    expect(v.total).toBe(3)
  })

  it('boş/bozuk yanıtta çökmez', () => {
    expect(aggregate([]).total).toBe(0)
    expect(aggregate([{}]).total).toBe(0)
    expect(aggregate([{ assets: [] }]).total).toBe(0)
  })
})
