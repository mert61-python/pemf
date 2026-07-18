/* PEMF Vet Client (launcher) — yapılandırma */

export const BRAND = {
  name: "PEMF Vet",
  clientName: "PEMF Vet Client",
  version: "1.3.6",
  company: "V-PEMF Technologies",
  tagline: "Veteriner PEMF tedavi + yapay zekâ teşhis platformu",
  about:
    "PEMF Vet; kamera destekli yapay zekâ teşhisini güvenli PEMF (pulslu elektromanyetik alan) tedavisiyle birleştiren klinik bir platformdur. Bu launcher, seçtiğiniz profillere göre gerekli yapay zekâ modellerini indirir, arka plan servisini kurar ve uygulamayı başlatır.",
} as const

/** Harici bağlantılar (varsayılan tarayıcıda açılır — tauri opener). */
export const LINKS = {
  website: "https://pemf-vet-web.vercel.app",
  download: "https://pemf-vet-web.vercel.app/download",
  support: "https://pemf-vet-web.vercel.app/#iletisim",
} as const

/** Client SELF-UPDATE: açılışta bu JSON'a bakar { version, notes, url }. version > mevcutsa güncelle.
 *  Stabil kanal = launcher-v1.8.0 (asset'leri her sürümde --clobber ile yenilenir). */
export const CLIENT_UPDATE_URL =
  "https://github.com/mert61-python/pemf-update/releases/download/launcher-v1.8.0/client-latest.json"

/** Tanıtım özellikleri (hero şeridi + Hakkında). icon = Icons.tsx anahtarı. */
export const FEATURES = [
  { icon: "ai", title: "Yapay Zekâ Teşhis", desc: "Kamera, ses ve görüntüyle akıllı ön-değerlendirme" },
  { icon: "shield", title: "Güvenli Tedavi", desc: "Tek-tuş protokoller + donanım güvenlik sınırları" },
  { icon: "db", title: "Hasta Yönetimi", desc: "Şifreli hasta kaydı, seans geçmişi ve KPI" },
  { icon: "cloud", title: "Uzaktan Erişim", desc: "Mobil uygulamayla klinik dışından izleme" },
] as const

/** TEST AŞAMASI: true → TÜM profiller (Araştırma dahil) ücretsiz indirilebilir; ücret etiketi gizli.
 *  Abonelik canlıya geçince false yapın. */
export const FREE_MODE = true

/** Uygulama (asıl büyük app) — "Başlat" ve app kısayolu bunu açar (mevcut React web). */
// 127.0.0.1 (localhost DEĞİL): native WebView2 penceresi 'localhost'u IPv6 ::1'e çözüp reddedilir
// (backend 0.0.0.0/IPv4 dinler). 127.0.0.1 IPv4'e zorlar → bağlantı çalışır.
export const APP_URL = "http://127.0.0.1:8000"

/** Sürüm manifesti (base app + profil paketleri: url/sha256/size/kind).
 *  GitHub Releases (mert61-python/pemf-update). Test için PEMF_MANIFEST_URL env'i override eder. */
export const MANIFEST_URL =
  "https://github.com/mert61-python/pemf-update/releases/download/client-app-v1.8.0/manifest.json"

export type Profile = {
  id: "home" | "vet" | "research"
  name: string
  tagline: string
  sizeGB: number
  included: boolean
  addonMonthly: number
  models: readonly string[]
}

export const PROFILES: Profile[] = [
  {
    id: "home",
    name: "Ev Sahibi",
    tagline: "Kamera destekli akıllı teşhis + tek-tuş güvenli tedavi.",
    sizeGB: 0.6,
    included: true,
    addonMonthly: 0,
    models: ["FGS yüz-ağrısı", "Segmentasyon", "Kedi organ 3B", "Kedi sesi", "Hastalık ön-değerlendirme"],
  },
  {
    id: "vet",
    name: "Veteriner Hekim",
    tagline: "Tam klinik kontrol: manuel frekans, sensör, hasta veritabanı.",
    sizeGB: 0.9,
    included: true,
    addonMonthly: 0,
    models: ["Manuel kontrol", "Sensör monitörü", "Hasta DB + KPI", "AI Pro otonom tedavi"],
  },
  {
    id: "research",
    name: "Araştırma Modu",
    tagline: FREE_MODE
      ? "Kanser-araştırma modelleri — test aşamasında ücretsiz."
      : "Kanser-araştırma modelleri — ağır indirme; ücretli eklenti.",
    sizeGB: 1.9,
    included: FREE_MODE,
    addonMonthly: FREE_MODE ? 0 : 390,
    models: ["Fantom tümör", "Petri kuyu", "Böbrek RNA/CT/patoloji", "CKD"],
  },
]

export const CLIENT_BASE_MB = 8

/** macOS: PEMF, Windows kurulumu yerine DOCKER ile çalışır. Client Mac'te Docker'ı yönetir.
 *  `packageUrl` = PEMF-Mac-Paket (Docker offline paketi: imajlar + modeller + compose) indirme linki.
 *  PLACEHOLDER → paketi bir yere (Google Drive / GitHub Release) yükleyip gerçek linki buraya yazın. */
export const MAC = {
  packageUrl: "https://ORNEK-PAKET-LINKI/PEMF-Mac-Paket.zip",
  dockerUrl: "https://www.docker.com/products/docker-desktop/",
} as const
