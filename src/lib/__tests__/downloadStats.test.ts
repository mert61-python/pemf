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

/* ── SÜRÜMLÜ DOSYA ADLARI (2026-08-10) ────────────────────────────────────────
   Kurulum dosyası artık sürüm taşıyor (`PEMFVetClient-Setup-1.9.18.exe`). Sayaç SABİT ada
   bakıyordu → yeni sürümlerin indirmeleri HİÇ SAYILMIYOR, Windows sayacı sessizce donuyordu.
   Gerçek veriyle ölçüldü: sabit-ad mantığı 46, desen mantığı 51 (5 indirme kayıptı).
   Geçmiş sayı da korunmalı: eski `-Setup.exe` adı hâlâ sayılır.                          */
describe('sürümlü dosya adları', () => {
  it('KRİTİK: sürümlü Windows kurulumu SAYILIR', () => {
    const r = aggregate([rel([['PEMFVetClient-Setup-1.9.18.exe', 7]])])
    expect(r.windows).toBe(7)
  })

  it('KRİTİK: eski sürümsüz ad da SAYILIR (geçmiş kaybolmaz)', () => {
    const r = aggregate([rel([['PEMFVetClient-Setup.exe', 46], ['PEMFVetClient-Setup-1.9.18.exe', 5]])])
    expect(r.windows).toBe(51)
  })

  it('APK sayılır (sürümlü ya da değil)', () => {
    const r = aggregate([rel([['PEMF_Vet_Mobil.apk', 13], ['PEMF_Vet_Mobil-2.3.8.apk', 2]])])
    expect(r.android).toBe(15)
  })

  it('KRİTİK: runtime paketleri HÂLÂ sayılmaz (sayaç şişmesin)', () => {
    const r = aggregate([rel([
      ['base.zip', 999], ['base-app.zip', 999], ['base-deps.zip', 999],
      ['home.zip', 999], ['vet.zip', 999], ['research.zip', 999], ['manifest.json', 999],
      ['PEMFVetClient-Setup-1.9.18.exe', 3],
    ])])
    expect(r.total).toBe(3)
  })

  it('benzer ama YANLIŞ adlar sayılmaz (desen fazla geniş olmasın)', () => {
    const r = aggregate([rel([
      ['PEMFVetClient-Setup-1.9.18.exe.sig', 5],
      ['not-PEMFVetClient-Setup.exe', 5],
      ['PEMFVetClient-Setup-beta.exe', 5],
    ])])
    expect(r.total).toBe(0)
  })
})
