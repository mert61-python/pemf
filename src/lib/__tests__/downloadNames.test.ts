// Author: mertaygn, cglrgrkn
/**
 * İNDİRME DOSYA ADLARI — sürüm adın İÇİNDE, etiketle ASLA ayrışmaz (2026-08-10, sahip isteği).
 *
 * İSTEK: indirilen Windows kurulumunun adında sürüm görünsün. Eskiden dosya
 * `PEMFVetClient-Setup.exe` diye kaydediliyordu; İndirilenler klasöründe üç sürüm yan yana
 * durunca hangisinin hangisi olduğu anlaşılmıyordu ve destek çağrısında "hangi setup'ı
 * kurdunuz?" sorusu cevapsız kalıyordu.
 *
 * ASIL RİSK BURADA: adı elle yazmak. Etiket yükseltilip ad güncellenmeyi unutulursa indirme
 * URL'i var olmayan bir dosyayı gösterir → buton **sessizce 404** verir; hata yalnız gerçek bir
 * kullanıcı indirmeyi denediğinde ortaya çıkar. Bu yüzden ad `windowsTag`ten TÜRETİLİR ve bu
 * test iki alanın tutarlılığını kilitler.
 */
import { describe, it, expect } from 'vitest'
import { CLIENT, DOWNLOAD_HOST } from '../../config'

const surum = () => DOWNLOAD_HOST.windowsTag.replace(/^launcher-v/, '')

describe('Windows kurulum dosya adı', () => {
  it('KRİTİK: ad sürümü TAŞIR', () => {
    expect(DOWNLOAD_HOST.windowsAsset).toBe(`PEMFVetClient-Setup-${surum()}.exe`)
    expect(DOWNLOAD_HOST.windowsAsset).toMatch(/PEMFVetClient-Setup-\d+\.\d+\.\d+\.exe$/)
  })

  it('KRİTİK: ad ile etiket AYRIŞAMAZ (elle yazılmış sabit değil)', () => {
    // Etiketi değiştirip adın onunla birlikte değiştiğini gör: sabit bir dize olsaydı bu
    // beklenti tutmaz ve kapı ısırırdı.
    const sahte = { ...DOWNLOAD_HOST, windowsTag: 'launcher-v9.9.9' }
    const turetilen = Object.getOwnPropertyDescriptor(DOWNLOAD_HOST, 'windowsAsset')?.get
    expect(turetilen, 'windowsAsset bir GETTER olmali (turetilmis) — sabit dize DEGIL').toBeTypeOf(
      'function',
    )
    expect(turetilen!.call(sahte)).toBe('PEMFVetClient-Setup-9.9.9.exe')
  })

  it('indirme URL’i etiketle AYNI sürümü gösterir', () => {
    const url = CLIENT.downloads.windows.url
    expect(url).toContain(`/releases/download/${DOWNLOAD_HOST.windowsTag}/`)
    expect(url.endsWith(DOWNLOAD_HOST.windowsAsset)).toBe(true)
    // Etiketteki sürüm ile dosya adındaki sürüm aynı olmalı — 404'ün klasik sebebi bu ayrışma.
    const etiketSurum = surum()
    const adSurum = url.match(/PEMFVetClient-Setup-([\d.]+)\.exe$/)?.[1]
    expect(adSurum).toBe(etiketSurum)
  })

  it('site sürümü (CLIENT.version) ile indirilen dosya AYNI sürüm', () => {
    // Kullanıcı sayfada "1.9.16" okuyup adında başka bir sürüm yazan dosya indirmemeli.
    expect(CLIENT.version).toBe(surum())
  })

  it('APK adı sürüm taşımaz — bu BİLİNÇLİ', () => {
    // Android tarafında dosya adı sürüm taşımaz: APK doğrudan kurulur, İndirilenler'de
    // biriktirilip karşılaştırılmaz ve `versionCode` zaten sistem tarafından gösterilir.
    expect(DOWNLOAD_HOST.androidAsset).toBe('PEMF_Vet_Mobil.apk')
  })
})
