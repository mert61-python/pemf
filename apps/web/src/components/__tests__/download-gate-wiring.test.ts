// Author: mertaygn, cglrgrkn
/**
 * İndirme kapısı — YÜZEY BAĞLANTISI regresyon kilidi (DENETIM 2026-08-06).
 *
 * NEDEN kaynak metni üzerinden test: `lib/download.ts` testleri kapının KARARINI kilitliyor ama
 * yüzeylerin o karara BAĞLI OLDUĞUNU kilitlemiyordu. Mutasyonla kanıtlandı: Home hero'daki
 * `<button onClick={download(...)}>` geri `<a href={d.url}>` yapıldığında ana indirme düğmesi
 * kapıyı tamamen atlıyor ve 28 testin HEPSİ yeşil kalıyordu — asıl regresyon serbestti.
 *
 * Projede jsdom/@testing-library kurulu değil (vitest node ortamında koşuyor) ve bu denetimde
 * ağdan paket kurulmadı; bu yüzden tıklama zinciri yerine yüzeylerin KAYNAĞI denetleniyor.
 * Dosyalar `?raw` ile okunuyor (node:fs DEĞİL) — tsconfig.app'te node tipleri yok, `?raw`
 * bildirimi ise vite/client ile geliyor, yani `npm run build` içindeki `tsc -b` temiz kalıyor.
 * DOM testleri eklendiğinde bu dosya silinebilir — ama o zamana kadar tek kilit budur.
 */
import { describe, it, expect } from 'vitest'
import downloadButtonsSrc from '../DownloadButtons.tsx?raw'
import downloadPageSrc from '../../pages/Download.tsx?raw'
import downloadGateSrc from '../DownloadGate.tsx?raw'
import { kaynakSoy } from '../../__tests__/_soyucu'

/** İndirme düğmesi barındıran TÜM yüzeyler. Yeni bir yüzey eklenirse buraya da eklenmeli.
 *
 *  ⚠️ YORUMLAR SOYULUR (2026-08-20): kapı ham metinde arıyordu ve bu deseni ANLATAN bir yorum
 *  (`href={...} yasaktır` açıklaması) yanlış-KIRMIZI veriyordu — ölçüldü. Soyucu string
 *  literallerini korur, yani gerçek bir `href="…"` hâlâ görünür; yalnız yorumlar elenir.
 *  Kapının GÜCÜ AZALMAZ: aşağıdaki iddialar soyulmuş kaynakta koşar. */
const YUZEYLER: [string, string][] = [
  ['components/DownloadButtons.tsx', kaynakSoy(downloadButtonsSrc)],
  ['pages/Download.tsx', kaynakSoy(downloadPageSrc)],
]

describe('indirme yüzeyleri kapıya bağlı kalır', () => {
  it('her yüzey kararı useDownloadGate’ten alır (kendi koşulunu yazmaz)', () => {
    for (const [ad, src] of YUZEYLER) {
      expect(src, `${ad} kapı hook'unu kullanmıyor`).toContain('useDownloadGate')
      expect(src, `${ad} indirmeyi kapı üzerinden tetiklemiyor`).toMatch(/onClick=\{\(\)\s*=>\s*download\(/)
    }
  })

  it('hiçbir yüzey release adresine DOĞRUDAN bağlantı vermez (kapıyı atlayan `<a href>` yok)', () => {
    // Asıl arka kapı buydu: `<a href={d.url}>` hem tıklamada hem "Bağlantıyı farklı kaydet"te
    // kapıyı atlıyordu. Adres çözümü YALNIZ lib/download.ts'te kalmalı.
    for (const [ad, src] of YUZEYLER) {
      expect(src, `${ad} içinde dinamik href var → kapı atlanabilir`).not.toMatch(/href=\{/)
      expect(src, `${ad} indirme adresini kendisi okuyor → kapı dışına çıkabilir`).not.toMatch(/\.url\b/)
    }
  })

  it('kapı hook’u oturumu AuthContext’ten okur ve modalı AuthModal’dan ister', () => {
    // Hook'un kendisi boşaltılırsa (ör. requestDownload çağrılmadan doğrudan gezinilse)
    // yukarıdaki iki test yeşil kalırdı.
    expect(downloadGateSrc).toContain('useAuth')
    expect(downloadGateSrc).toContain('useAuthModal')
    expect(downloadGateSrc).toMatch(/requestDownload\(/)
  })
})
