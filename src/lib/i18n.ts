/* PEMF Vet Client — TR/EN yerelleştirme (hafif; kütüphanesiz). */
import { FREE_MODE } from "../config";

export type Lang = "tr" | "en";

const KEY = "pemf-client-lang";

/** Kayıtlı dil (yoksa tarayıcı/sistem TR'ye varsayılır). */
export function loadLang(): Lang {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "tr" || v === "en") return v;
  } catch {}
  return "tr";
}
export function saveLang(l: Lang) {
  try {
    localStorage.setItem(KEY, l);
  } catch {}
}

type Dict = Record<string, string>;

const TR: Dict = {
  // header
  "hdr.website": "Web Sitesi",
  "hdr.about": "Hakkında",
  // profiles
  "prof.badge": "Kurulum",
  "prof.title": "Kullanım profil(ler)inizi seçin",
  "prof.sub": "Yalnız seçtiğiniz profillerin modelleri iner. Çoklu seçim yapabilirsiniz.",
  "prof.preview": "Uygulama içi görünüm",
  "prof.plan": "profiller aboneliğinize göre açık",
  "prof.logout": "Çıkış",
  "prof.free": "Ücretsiz",
  "prof.included": "Dahil",
  "prof.locked": "Aboneliğinizde yok",
  "prof.perMonth": "/ay",
  "prof.download": "İndirme",
  "prof.extra": "Ek aylık",
  "prof.none": "yok",
  "prof.install": "Kur ve devam et",
  // features
  "feat.ai.t": "Yapay Zekâ Teşhis",
  "feat.ai.d": "Kamera, ses ve görüntüyle akıllı ön-değerlendirme",
  "feat.shield.t": "Güvenli Tedavi",
  "feat.shield.d": "Tek-tuş protokoller + donanım güvenlik sınırları",
  "feat.db.t": "Hasta Yönetimi",
  "feat.db.d": "Şifreli hasta kaydı, seans geçmişi ve KPI",
  "feat.cloud.t": "Uzaktan Erişim",
  "feat.cloud.d": "Mobil uygulamayla klinik dışından izleme",
  // installing
  "inst.starting": "Başlatılıyor…",
  "inst.downloading": "İndiriliyor…",
  "inst.installing": "Kuruluyor…",
  "inst.paused": "Duraklatıldı",
  "inst.st.paused": "Duraklatıldı",
  "inst.st.retry": "Yeniden bağlanılıyor…",
  "inst.st.installing": "Kuruluyor",
  "inst.st.downloading": "İndiriliyor",
  "inst.resume": "Devam et",
  "inst.pause": "Durdur",
  "inst.cancel": "İptal",
  "inst.noteInstalling": "Dosyalar yerlerine kuruluyor (yönetici izni gerekebilir).",
  "inst.noteDownloading": "Bağlantı kesilirse otomatik olarak kaldığı yerden devam eder.",
  "inst.failTitle": "Kurulum başarısız",
  "inst.back": "Geri",
  "inst.retry": "Tekrar dene",
  "inst.eta.min": "dk",
  "inst.eta.sec": "sn",
  // ready
  "ready.title": "Hazır!",
  "ready.sub": "PEMF Vet kuruldu. Uygulamayı başlatın veya profillerinizi güncelleyin.",
  "ready.shortcut": "Masaüstü kısayolları eklendi",
  "ready.launch": "Başlat",
  "ready.launching": "Başlatılıyor…",
  "ready.launchFailed":
    "Arka plan servisi henüz hazır değil. Birkaç saniye sonra tekrar deneyin; sorun sürerse 'Onar'.",
  "ready.change": "Profilleri değiştir",
  "ready.repair": "Onar",
  "ready.uninstall": "Uygulamayı kaldır",
  "ready.uninstalling": "Kaldırılıyor…",
  "ready.repairConfirm":
    "Uygulama açılmıyor/hatalıysa onarın: çekirdek yeniden indirilip temiz kurulur (birkaç dakika, modeller/hasta verisi korunur). Devam edilsin mi?",
  "ready.uninstallConfirm":
    "PEMF Vet uygulamasını (arka plan servisi + AI modelleri) kaldırmak istiyor musunuz? Bu işlem yönetici izni gerektirir.",
  "ready.uninstallFail": "Kaldırma başarısız: ",
  // about
  "about.about":
    "PEMF Vet; kamera destekli yapay zekâ teşhisini güvenli PEMF (pulslu elektromanyetik alan) tedavisiyle birleştiren klinik bir platformdur. Bu launcher, seçtiğiniz profillere göre gerekli yapay zekâ modellerini indirir, arka plan servisini kurar ve uygulamayı başlatır.",
  "about.website": "Web Sitesi",
  "about.downloads": "İndirmeler",
  "about.support": "Destek",
  "about.version": "Sürüm",
  "about.close": "Kapat",
  // how it works
  "how.title": "Nasıl çalışır?",
  "how.s1.t": "Profil seç",
  "how.s1.d": "İhtiyacınıza uygun profil(ler)i işaretleyin.",
  "how.s2.t": "Modeller iner",
  "how.s2.d": "Seçilen yapay zekâ modelleri ve arka plan servisi kurulur.",
  "how.s3.t": "Başlat",
  "how.s3.d": "Uygulama tarayıcıda açılır — kullanıma hazırsınız.",
  // system requirements
  "sys.title": "Sistem gereksinimleri",
  "sys.os": "Windows 10/11 (64-bit)",
  "sys.ram": "8 GB RAM (16 GB önerilir)",
  "sys.disk": "Profillere göre 3–5 GB boş disk",
  "sys.net": "Kurulum için internet + yönetici izni",
  // update
  "upd.available": "Yeni sürüm {v} hazır",
  "upd.desc": "Güncellemede kurulu profilleriniz ve modelleriniz korunur.",
  "upd.update": "Güncelle",
  "upd.later": "Sonra",
  "upd.updating": "Güncelleme indiriliyor…",
  "upd.launching": "Yükleyici başlatılıyor…",
  "upd.restartNote": "Uygulama birazdan kapanıp güncellenmiş haliyle yeniden açılacak. Kurulu profilleriniz korunur.",
  // login
  "login.sub": "Kurulum için hesabınızla giriş yapın. Aboneliğinize göre profiller açılır.",
  "login.email": "E-posta",
  "login.password": "Şifre",
  "login.signingIn": "Giriş yapılıyor…",
  "login.signIn": "Giriş yap",
  "login.badCreds": "E-posta veya şifre hatalı.",
  "login.noAccount": "Hesabınız yok mu?",
  "login.register": "Web sitesinden kayıt olun",
  "login.emailNotConfirmed": "E-posta adresiniz henüz doğrulanmamış.",
  "login.rateLimited": "Çok fazla deneme. Lütfen biraz bekleyip tekrar deneyin.",
  "login.generic": "Giriş yapılamadı. Lütfen tekrar deneyin.",
  "login.netErr": "Bağlantı hatası. İnternetinizi kontrol edip tekrar deneyin.",
  "boot.loading": "Yükleniyor…",
  "upd.skip": "Güncellemeyi atla",
  "common.ok": "Tamam",
  "common.cancel": "Vazgeç",
  "inst.listenErr": "Kurulum başlatılamadı (olay dinleyicisi). Lütfen tekrar deneyin.",
  // mac
  "mac.title": "PEMF'i Mac'te çalıştır",
  "mac.sub": "Mac'te PEMF, Docker ile çalışır. Aşağıdaki iki adımı tamamlayın, sonra başlatın.",
  "mac.checking": "Kontrol ediliyor…",
  "mac.notInstalled": "Kurulu değil — Docker Desktop gerekli.",
  "mac.notRunning": "Kurulu ama çalışmıyor — Docker Desktop'ı açın (balina yeşil olsun).",
  "mac.running": "Çalışıyor.",
  "mac.download": "İndir",
  "mac.open": "Aç",
  "mac.pkg": "PEMF paketi",
  "mac.pkgMissing": "Bulunamadı — paketi indirip Downloads klasörüne PEMF-Mac-Paket olarak çıkarın.",
  "mac.starting": "PEMF başlatılıyor… ilk açılışta imaj yüklemesi + AI ~1-3 dk sürebilir.",
  "mac.runningMsg": "Çalışıyor — tarayıcıda http://localhost:8080 açıldı.",
  "mac.startErr": "Başlatma hatası: ",
  "mac.stopped": "PEMF durduruldu.",
  "mac.stopErr": "Durdurma hatası: ",
  "mac.startBtn": "PEMF'i başlat",
  "mac.startingBtn": "Başlatılıyor…",
  "mac.openBrowser": "Tarayıcıda aç",
  "mac.stop": "Durdur",
  "mac.refresh": "Durumu yenile",
};

const EN: Dict = {
  "hdr.website": "Website",
  "hdr.about": "About",
  "prof.badge": "Setup",
  "prof.title": "Choose your usage profile(s)",
  "prof.sub": "Only the models for the profiles you pick are downloaded. Multiple selection is allowed.",
  "prof.preview": "In-app view",
  "prof.plan": "profiles enabled per your plan",
  "prof.logout": "Sign out",
  "prof.free": "Free",
  "prof.included": "Included",
  "prof.locked": "Not in your plan",
  "prof.perMonth": "/mo",
  "prof.download": "Download",
  "prof.extra": "Extra monthly",
  "prof.none": "none",
  "prof.install": "Install & continue",
  "feat.ai.t": "AI Diagnosis",
  "feat.ai.d": "Smart pre-assessment from camera, sound and images",
  "feat.shield.t": "Safe Treatment",
  "feat.shield.d": "One-tap protocols + hardware safety limits",
  "feat.db.t": "Patient Management",
  "feat.db.d": "Encrypted patient records, session history and KPIs",
  "feat.cloud.t": "Remote Access",
  "feat.cloud.d": "Monitor from outside the clinic via the mobile app",
  "inst.starting": "Starting…",
  "inst.downloading": "Downloading…",
  "inst.installing": "Installing…",
  "inst.paused": "Paused",
  "inst.st.paused": "Paused",
  "inst.st.retry": "Reconnecting…",
  "inst.st.installing": "Installing",
  "inst.st.downloading": "Downloading",
  "inst.resume": "Resume",
  "inst.pause": "Pause",
  "inst.cancel": "Cancel",
  "inst.noteInstalling": "Placing files (administrator permission may be required).",
  "inst.noteDownloading": "If the connection drops it automatically resumes.",
  "inst.failTitle": "Installation failed",
  "inst.back": "Back",
  "inst.retry": "Retry",
  "inst.eta.min": "min",
  "inst.eta.sec": "sec",
  "ready.title": "Ready!",
  "ready.sub": "PEMF Vet is installed. Launch the app or update your profiles.",
  "ready.shortcut": "Desktop shortcuts added",
  "ready.launch": "Launch",
  "ready.launching": "Starting…",
  "ready.launchFailed":
    "The background service isn't ready yet. Try again in a few seconds; if it persists, use 'Repair'.",
  "ready.change": "Change profiles",
  "ready.repair": "Repair",
  "ready.uninstall": "Uninstall",
  "ready.uninstalling": "Uninstalling…",
  "ready.repairConfirm":
    "Repair if the app won't open or is faulty: the core is re-downloaded and cleanly reinstalled (a few minutes; models/patient data are preserved). Continue?",
  "ready.uninstallConfirm":
    "Remove the PEMF Vet app (background service + AI models)? This requires administrator permission.",
  "ready.uninstallFail": "Uninstall failed: ",
  "about.about":
    "PEMF Vet is a clinical platform that combines camera-assisted AI diagnosis with safe PEMF (pulsed electromagnetic field) therapy. This launcher downloads the AI models for the profiles you choose, installs the background service and launches the app.",
  "about.website": "Website",
  "about.downloads": "Downloads",
  "about.support": "Support",
  "about.version": "Version",
  "about.close": "Close",
  "how.title": "How it works",
  "how.s1.t": "Pick a profile",
  "how.s1.d": "Select the profile(s) that fit your needs.",
  "how.s2.t": "Models download",
  "how.s2.d": "The selected AI models and background service are installed.",
  "how.s3.t": "Launch",
  "how.s3.d": "The app opens in your browser — you're ready to go.",
  "sys.title": "System requirements",
  "sys.os": "Windows 10/11 (64-bit)",
  "sys.ram": "8 GB RAM (16 GB recommended)",
  "sys.disk": "3–5 GB free disk depending on profiles",
  "sys.net": "Internet + administrator rights to install",
  "upd.available": "Version {v} is available",
  "upd.desc": "Your installed profiles and models are preserved during the update.",
  "upd.update": "Update",
  "upd.later": "Later",
  "upd.updating": "Downloading update…",
  "upd.launching": "Starting installer…",
  "upd.restartNote": "The app will close shortly and reopen with the update applied. Your installed profiles are preserved.",
  // login
  "login.sub": "Sign in with your account to install. Profiles unlock based on your subscription.",
  "login.email": "Email",
  "login.password": "Password",
  "login.signingIn": "Signing in…",
  "login.signIn": "Sign in",
  "login.badCreds": "Incorrect email or password.",
  "login.noAccount": "No account?",
  "login.register": "Register on the website",
  "login.emailNotConfirmed": "Your email address hasn't been verified yet.",
  "login.rateLimited": "Too many attempts. Please wait a moment and try again.",
  "login.generic": "Sign-in failed. Please try again.",
  "login.netErr": "Connection error. Check your internet and try again.",
  "boot.loading": "Loading…",
  "upd.skip": "Skip update",
  "common.ok": "OK",
  "common.cancel": "Cancel",
  "inst.listenErr": "Couldn't start installation (event listener). Please try again.",
  // mac
  "mac.title": "Run PEMF on Mac",
  "mac.sub": "On Mac, PEMF runs via Docker. Complete the two steps below, then start.",
  "mac.checking": "Checking…",
  "mac.notInstalled": "Not installed — Docker Desktop is required.",
  "mac.notRunning": "Installed but not running — open Docker Desktop (whale should be green).",
  "mac.running": "Running.",
  "mac.download": "Download",
  "mac.open": "Open",
  "mac.pkg": "PEMF package",
  "mac.pkgMissing": "Not found — download the package and extract it to Downloads as PEMF-Mac-Paket.",
  "mac.starting": "Starting PEMF… first launch may take ~1-3 min for image load + AI.",
  "mac.runningMsg": "Running — opened http://localhost:8080 in your browser.",
  "mac.startErr": "Start error: ",
  "mac.stopped": "PEMF stopped.",
  "mac.stopErr": "Stop error: ",
  "mac.startBtn": "Start PEMF",
  "mac.startingBtn": "Starting…",
  "mac.openBrowser": "Open in browser",
  "mac.stop": "Stop",
  "mac.refresh": "Refresh status",
};

const DICTS: Record<Lang, Dict> = { tr: TR, en: EN };

/** Dil için t(key, vars?) üretir. Bilinmeyen anahtar → anahtarın kendisi (görünür hata). */
export function makeT(lang: Lang) {
  const d = DICTS[lang] ?? TR;
  return (key: string, vars?: Record<string, string | number>): string => {
    let s = d[key] ?? TR[key] ?? key;
    if (vars) for (const k in vars) s = s.replace(`{${k}}`, String(vars[k]));
    return s;
  };
}

/** Profil ad/slogan/model çevirisi (config TR; EN + araştırma FREE_MODE ternary burada). */
export const PROFILE_I18N: Record<
  string,
  Record<Lang, { name: string; tagline: string; models: readonly string[] }>
> = {
  home: {
    tr: {
      name: "Ev Sahibi",
      tagline: "Kamera destekli akıllı teşhis + tek-tuş güvenli tedavi.",
      models: ["FGS yüz-ağrısı", "Segmentasyon", "Kedi organ 3B", "Kedi sesi", "Hastalık ön-değerlendirme"],
    },
    en: {
      name: "Pet Owner",
      tagline: "Camera-assisted smart diagnosis + one-tap safe treatment.",
      models: ["FGS facial-pain", "Segmentation", "Cat organ 3D", "Cat sound", "Disease pre-assessment"],
    },
  },
  vet: {
    tr: {
      name: "Veteriner Hekim",
      tagline: "Tam klinik kontrol: manuel frekans, sensör, hasta veritabanı.",
      models: ["Manuel kontrol", "Sensör monitörü", "Hasta DB + KPI", "AI Pro otonom tedavi"],
    },
    en: {
      name: "Veterinarian",
      tagline: "Full clinical control: manual frequency, sensors, patient database.",
      models: ["Manual control", "Sensor monitor", "Patient DB + KPI", "AI Pro autonomous therapy"],
    },
  },
  research: {
    tr: {
      name: "Araştırma Modu",
      tagline: FREE_MODE
        ? "Kanser-araştırma modelleri — test aşamasında ücretsiz."
        : "Kanser-araştırma modelleri — ağır indirme; ücretli eklenti (+₺390/ay).",
      models: ["Fantom tümör", "Petri kuyu", "Böbrek RNA/CT/patoloji", "CKD"],
    },
    en: {
      name: "Research Mode",
      tagline: FREE_MODE
        ? "Cancer-research models — free during the test phase."
        : "Cancer-research models — heavy download; paid add-on (+₺390/mo).",
      models: ["Phantom tumor", "Petri well", "Kidney RNA/CT/pathology", "CKD"],
    },
  },
};
