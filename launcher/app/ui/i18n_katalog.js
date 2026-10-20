// ÜRETİLMİŞ DOSYA — ELLE DÜZENLEMEYİN. Kaynak: launcher/i18n/{tr,en}.json → ui.* · Üreteç: scripts/i18n/launcher_uret.py
// (K-6: katalog ile bu dosya ayrışırsa tests/test_i18n_launcher_altyapi.py kırmızı.)
window.PEMF_I18N_KATALOG = {
 "en": {
  "about": "About",
  "aboutBody": "PEMF Vet launcher. It downloads your selected usage profiles, verifies the downloaded files, installs them and opens the app. It connects automatically to the PEMF device on your network.",
  "aboutPlat": "Platform",
  "aboutTitle": "About PEMF Vet",
  "aboutVer": "Version",
  "appCore": "App files",
  "applyStart": "Apply & Start",
  "authSlow": "Slow connection — verifying your session in the background. You can start the app now.",
  "backToApp": "Back to app",
  "backupChoose": "Choose backup destination",
  "backupSameDisk": "Backups are currently on the SAME disk as patient data. A disk failure would lose both; choose an external drive or a network share.",
  "backupUnreachable": "Backup destination is currently unreachable: {{yol}} — plug in the external drive or choose a new destination.",
  "bgCancel": "Cancel",
  "bgCancelConfirm": "Cancel the download?\n\nThe part downloaded so far will be DELETED and the update will start OVER on the next launch.\n\nIf you only want a break, use \"Pause\" — the downloaded part is kept and resumes where it left off.",
  "bgPause": "Pause",
  "bgResume": "Resume",
  "cached": "already downloaded",
  "calc": "calculating",
  "cancel": "Cancel",
  "cancelDl": "Cancel",
  "change": "Change profiles",
  "cont": "Continue",
  "coreDesc": "Interface and shared models — required by every profile",
  "coreInstalled": "installed",
  "coreLocked": "The main application is part of every installation; it cannot be unselected.",
  "coreName": "Main application",
  "coreTag": "required",
  "depAdd": "Add {{profil}}",
  "depNotice": "“{{secili}}” is selected without “{{eksik}}”. They install independently; only AI Pro’s organ localization uses models from the {{eksik}} package — that feature will not work. Everything else works.",
  "detect": "Detecting environment…",
  "dl": "downloading",
  "errDisk": "Not enough disk space. Free up space and try again.",
  "errDns": "Could not reach the internet — the server address could not be resolved. Check your Wi-Fi/network and try again. If you are online, retry in a few minutes.",
  "errSunucu": "The update server is unreachable right now. This is not about your connection; try again shortly.",
  "errTimeout": "The connection timed out. Your network may be slow or briefly interrupted; please try again.",
  "etaLeft": "left",
  "extracting": "installing",
  "footSupport": "Support",
  "footWeb": "Website",
  "fwEngel": "Windows Firewall is BLOCKING incoming connections to this app — the mobile app cannot find the device. Use from the device screen is not affected.",
  "fwIzinVer": "Allow (administrator)",
  "fwKuralYok": "The mobile app may not be able to connect to this device: Windows Firewall has no rule allowing incoming connections. Use from the device screen is not affected.",
  "guide": "Guide",
  "guideClose": "close",
  "guideTitle": "User Guide",
  "guncLead": "Please wait — the new version is being installed. PEMF Vet will reopen by itself; you don't need to close this window or start the app again.",
  "guncSlow": "Taking a bit longer — installation can take 1–2 minutes depending on your computer. If this window doesn't close on its own, open PEMF Vet from the Start menu.",
  "guncTitle": "Updating launcher…",
  "instDl": "Downloading…",
  "instExtract": "Installing…",
  "instStart": "Starting…",
  "instVerify": "Verifying…",
  "install": "Install & Start",
  "keepOne": "Keep at least one profile",
  "kilavuz": {
   "connect": "In veterinary mode the PEMF hardware must be on the SAME Wi-Fi network as your computer. The app finds it automatically; if not, enter the device IP manually in the app's Settings.",
   "connectTitle": "Connecting to the device (Vet)",
   "intro": "PEMF Vet is a platform for AI-assisted diagnosis and PEMF (pulsed magnetic field) sessions in cats. This client downloads, installs and starts the app on your computer. The steps below are written for someone with no prior experience — just follow them in order.",
   "profTitle": "3 Profiles — which one is for you?",
   "profiles": {
    "p01": {
     "does": "Runs AI pre-diagnosis from your cat's camera image: disease, organ, imaging and sound analysis. Does NOT include a device or session.",
     "key": "home",
     "use": {
      "u01": "When the app opens, choose ‘Pet Owner’ and sign in.",
      "u02": "Go to the ‘Smart Diagnosis’ screen.",
      "u03": "Point your camera at the cat or upload a photo/sound file.",
      "u04": "Read the result and suggestions — always consult a veterinarian for a definitive diagnosis."
     },
     "who": "For pet (cat) owners"
    },
    "p02": {
     "does": "Diagnosis + PEMF device sessions + patient records, session history, sensor tracking, KPI panel and simulator. Also includes the Pet Owner diagnostic models (hence the larger size).",
     "key": "vet",
     "use": {
      "u01": "Choose ‘Veterinarian’ and sign in.",
      "u02": "Add a new patient from ‘Patients’.",
      "u03": "Start a session from ‘Control’; adjust coils manually or run autonomously with ‘AI Pro’.",
      "u04": "Track the session via ‘Sensors’ and ‘History’; see clinic stats in ‘KPI’."
     },
     "who": "For veterinarians and clinics"
    },
    "p03": {
     "does": "Petri, histopathology, kidney and phantom AI models; sample/data records and history. Does NOT include a device.",
     "key": "research",
     "use": {
      "u01": "Choose ‘Research Mode’ and sign in.",
      "u02": "Pick the relevant research model from ‘Smart Diagnosis’.",
      "u03": "Upload your image or data file.",
      "u04": "Review the results and save them to ‘History’."
     },
     "who": "For researchers and laboratories"
    }
   },
   "steps": {
    "s01": {
     "b": "The 'Main application' card at the top is part of every installation and cannot be removed (interface and shared models; its size is shown on the right, or 'installed' if already present). Tick at least one of the 3 profiles below it (Pet Owner, Veterinarian, Research). You can pick several; each card shows ONLY its own download size, and the button total counts only what will actually download (the main application if not yet installed + your new picks). In 'Change profiles', an already installed profile says 'installed' and is not counted; unticking an installed profile marks it 'will be removed' and it is deleted from this computer when you press the button.",
     "t": "Choose your profile(s)"
    },
    "s02": {
     "b": "Your selected models download and install. The bar shows percent, speed (MB/s) and time left. You can Pause or Cancel anytime; even if the internet drops or the computer shuts down, you can resume where you left off when you reopen.",
     "t": "Click ‘Install & Start’"
    },
    "s03": {
     "b": "When installation finishes, the app opens in your browser. Next time, use the ‘Start’ button in this window to open it in seconds.",
     "t": "The app opens automatically"
    }
   },
   "stepsTitle": "Installation — 3 steps",
   "trouble": {
    "k01": {
     "b": "Click ‘Repair’ in this window — it re-verifies the packages and fills in what's missing.",
     "t": "The app won't open or a model is missing"
    },
    "k02": {
     "b": "Reopen the app; answer ‘Resume where you left off?’ with ‘Resume’. The downloaded part is kept.",
     "t": "Download interrupted (internet dropped / computer closed)"
    },
    "k03": {
     "b": "Click ‘Uninstall’ (your patient data is KEPT), then install again.",
     "t": "I want to reinstall from scratch"
    },
    "k04": {
     "b": "Use the ‘Website’ link at the top or ‘Support’ at the bottom.",
     "t": "More help"
    }
   },
   "troubleTitle": "Troubleshooting"
  },
  "langLabel": "language",
  "loginBtn": "Sign in",
  "loginEmail": "Email",
  "loginEmpty": "Email and password are required.",
  "loginForgot": "Forgot password",
  "loginLead": "Sign in with your PEMF Vet account — the app won't ask you again.",
  "loginNoPersist": "This platform can't store the session securely — sign-in applies to this launch only.",
  "loginPass": "Password",
  "loginPwInvisible": "The password contains an invisible character (likely from copy-paste). Clear it and type it manually.",
  "loginPwSpace": "Your password starts or ends with a space — usually from pasting. Use “Show” to check.",
  "loginRemember": "Remember me",
  "loginRequired": "Sign in to install or repair.",
  "loginSignup": "Create account",
  "loginTitle": "Sign in",
  "loginWait": "Signing in…",
  "logout": "Sign out",
  "logoutBody": "Your session on this computer will be removed and the app will be signed out. Continue?",
  "logoutTitle": "Sign out",
  "luReady": "PEMF Vet Client {{surum}} is available — it will be installed when you close and reopen the app.",
  "noChange": "No changes",
  "notInstalled": "App is not installed.",
  "notSupported": "The package for this platform ({{platform}}) is not published yet.",
  "offline": "Offline",
  "offlineLogin": "No internet connection — sign-in unavailable. You can start the installed app offline.",
  "offlineReady": "No internet connection — update check and profile list unavailable. You can still start the installed app.",
  "offlineSelect": "No internet connection; installation requires one. Check your connection and try again.",
  "offlineStart": "Start offline",
  "ok": "OK",
  "pause": "Pause",
  "pausedLead": "Download paused — the downloaded part is kept on your computer. You can resume where you left off.",
  "pausedTitle": "Paused",
  "profilMeta": {
   "home": {
    "aciklama": "Feline diagnostic models — disease, organ, imaging, sound",
    "ad": "Pet Owner"
   },
   "research": {
    "aciklama": "Research models — petri, histopathology, kidney, phantom",
    "ad": "Research Mode"
   },
   "vet": {
    "aciklama": "Clinical diagnosis + session (em_kedi, thermal)",
    "ad": "Veterinarian"
   }
  },
  "pwHide": "Hide",
  "pwHideTitle": "Hide password",
  "pwShow": "Show",
  "pwShowTitle": "Show password",
  "ready": "ready — opened in browser",
  "readyLead": "PEMF Vet is installed. Start the app or update your profiles.",
  "readyTitle": "Ready!",
  "reconnTitle": "Reconnecting…",
  "reconnecting": "connection lost, retrying",
  "removeFailed": "Profile could not be removed: {{neden}}",
  "removing": "Removing…",
  "repair": "Repair installation",
  "repairBody": "Installed packages will be re-verified and missing/corrupt files repaired. This may take a few minutes. Continue?",
  "repairTitle": "Repair installation",
  "resume": "Resume",
  "resumeBody": "The previous installation didn't complete (internet may have dropped or the device was closed). The downloaded part is kept — resume where you left off?",
  "resumeNo": "Discard",
  "resumeTitle": "Installation unfinished",
  "resumeYes": "Resume",
  "retry": "Retry",
  "rtBg": "A new version is downloading in the background — you can use the app now; it will be installed on the next launch.",
  "rtBgCancelled": "Update download cancelled — it will be retried on the next launch.",
  "rtBgDone": "New version downloaded — it will be installed on the next launch.",
  "rtBgFail": "Background download did not finish — it will resume on the next launch.",
  "rtBgPaused": "Update download paused — the downloaded part is kept; \"Resume\" continues where it left off.",
  "rtBgPrep": "Preparing…",
  "rtBlocked": "The new version failed to start on this device, so the previous one was restored. Automatic retries are paused — use \"Repair\" to try again, or wait for the next release.",
  "rtBusy": "Updates are not applied during a session — it will update automatically once the session ends.",
  "rtDone": "App updated.",
  "rtLead": "A new app version was found — downloading and installing. You can start it when this finishes.",
  "rtReady": "Update ready — it will be installed when you close and reopen the app.",
  "rtRecall": "⚠️ IMPORTANT SAFETY UPDATE pending. This version is no longer supported; please CLOSE AND REOPEN the app so the update installs. If a session is running, wait for it to finish.",
  "rtRollback": "The new version failed to start; rolled back to the previous working version. The app is usable.",
  "rtRollbackFail": "The new version failed to start and the rollback could not finish. Please use \"Repair\" to reinstall.",
  "rtTitle": "Updating app…",
  "runningLead": "PEMF Vet is running. If you close the app window you can start it again from here.",
  "selCancel": "Back",
  "selLead": "The main application is always installed (cannot be removed). Pick at least one profile — only the ones you pick are downloaded.",
  "selTitle": "Choose your usage profile",
  "selfUpdateFailed": "Launcher update could not be completed — the app is opening normally. It will be retried on the next launch.",
  "start": "Start",
  "startChecking": "Checking for updates…",
  "starting": "starting",
  "tagline": "Veterinary PEMF session + AI diagnostics platform",
  "uninBody": "The downloaded app and AI models will be removed.\n\nDATA THAT IS KEPT (medical records — NOT deleted by uninstall):\n• Patient records\n• Session history\n• AI analysis history\nLocation: %APPDATA%\\PEMF_GUI\n\nIf you also want these deleted, delete them from inside the app BEFORE uninstalling (Patients → \"Delete All\", AI History → \"Delete History\").\n\nContinue?",
  "uninTitle": "Uninstall app",
  "uninstall": "Uninstall",
  "updatingApply": "Applying update, restarting the app…",
  "updatingLead": "A new launcher version was found — downloading and installing. The app will restart automatically.",
  "updatingTitle": "Updating launcher…",
  "verifying": "verifying integrity",
  "web": "Website",
  "willRemove": "will be removed"
 },
 "tr": {
  "about": "Hakkında",
  "aboutBody": "PEMF Vet başlatıcısı. Seçtiğiniz kullanım profillerini indirir, inen dosyaların bütünlüğünü doğrular, kurar ve uygulamayı açar. Aynı ağdaki PEMF cihazınıza otomatik bağlanır.",
  "aboutPlat": "Platform",
  "aboutTitle": "PEMF Vet hakkında",
  "aboutVer": "Sürüm",
  "appCore": "Uygulama dosyaları",
  "applyStart": "Uygula ve Başlat",
  "authSlow": "Bağlantı yavaş — oturum arka planda doğrulanıyor. Uygulamayı şimdi başlatabilirsiniz.",
  "backToApp": "Uygulamaya dön",
  "backupChoose": "Yedek hedefi seç",
  "backupSameDisk": "Yedekler şu anda hasta verisiyle AYNI diskte. Disk arızasında ikisi de kaybolur; harici bir disk ya da ağ paylaşımı seçin.",
  "backupUnreachable": "Yedek hedefi şu an erişilemiyor: {{yol}} — harici diski takın ya da yeni bir hedef seçin.",
  "bgCancel": "İptal",
  "bgCancelConfirm": "İndirmeyi iptal etmek istiyor musunuz?\n\nŞu ana kadar inen kısım SİLİNİR ve güncelleme bir sonraki açılışta BAŞTAN indirilir.\n\nSadece ara vermek istiyorsanız \"Duraklat\" kullanın — inen kısım korunur ve kaldığı yerden devam eder.",
  "bgPause": "Duraklat",
  "bgResume": "Devam et",
  "cached": "zaten indirilmiş",
  "calc": "hesaplanıyor",
  "cancel": "Vazgeç",
  "cancelDl": "İptal",
  "change": "Profilleri değiştir",
  "cont": "Devam",
  "coreDesc": "Arayüz ve ortak modeller — her profil için gerekli",
  "coreInstalled": "kurulu",
  "coreLocked": "Ana uygulama her kurulumda gelir; seçimi kaldırılamaz.",
  "coreName": "Ana uygulama",
  "coreTag": "zorunlu",
  "depAdd": "{{profil}} ekle",
  "depNotice": "“{{secili}}” seçildi ama “{{eksik}}” yok. Bunlar bağımsız kurulur; yalnız AI Pro’nun organ lokalizasyonu {{eksik}} paketindeki modelleri kullanır — o özellik çalışmaz. Diğer her şey çalışır.",
  "detect": "Ortam algılanıyor…",
  "dl": "indiriliyor",
  "errDisk": "Diskte yeterli yer yok. Yer açıp tekrar deneyin.",
  "errDns": "İnternet bağlantısı kurulamadı — sunucu adresi çözümlenemedi. Wi-Fi/ağ bağlantınızı kontrol edip tekrar deneyin. Bağlantı varsa birkaç dakika sonra yeniden deneyin.",
  "errSunucu": "Güncelleme sunucusuna şu an ulaşılamıyor. Bağlantınızla ilgili değil; kısa süre sonra tekrar deneyin.",
  "errTimeout": "Bağlantı zaman aşımına uğradı. Ağınız yavaş ya da geçici olarak kesilmiş olabilir; tekrar deneyin.",
  "etaLeft": "kaldı",
  "extracting": "kuruluyor",
  "footSupport": "Destek",
  "footWeb": "Web Sitesi",
  "fwEngel": "Windows güvenlik duvarı bu uygulamanın ağdan bağlantı almasını ENGELLİYOR — mobil uygulama cihazı bulamaz. Cihaz ekranından kullanım etkilenmez.",
  "fwIzinVer": "İzin ver (yönetici)",
  "fwKuralYok": "Mobil uygulama bu cihaza bağlanamayabilir: Windows güvenlik duvarında gelen bağlantı izni yok. Cihaz ekranından kullanım etkilenmez.",
  "guide": "Kılavuz",
  "guideClose": "kapat",
  "guideTitle": "Kullanım Kılavuzu",
  "guncLead": "Lütfen bekleyin — yeni sürüm kuruluyor. PEMF Vet birazdan kendiliğinden açılacak; bu pencereyi kapatmanız ya da uygulamayı yeniden açmanız gerekmez.",
  "guncSlow": "Biraz uzun sürdü — kurulum bilgisayarın hızına göre 1-2 dakika alabilir. Bu pencere kendiliğinden kapanmazsa PEMF Vet'i Başlat menüsünden açabilirsiniz.",
  "guncTitle": "Başlatıcı güncelleniyor…",
  "instDl": "İndiriliyor…",
  "instExtract": "Kuruluyor…",
  "instStart": "Başlatılıyor…",
  "instVerify": "Doğrulanıyor…",
  "install": "Kur ve Başlat",
  "keepOne": "En az bir profil seçili kalmalı",
  "kilavuz": {
   "connect": "Veteriner modunda PEMF donanımı, bilgisayarınızla AYNI Wi-Fi ağında olmalıdır. Uygulama cihazı otomatik bulur. Bulamazsa uygulama içindeki Ayarlar’dan cihazın IP adresini elle girebilirsiniz.",
   "connectTitle": "Cihaza bağlanma (Veteriner)",
   "intro": "PEMF Vet; kedilerde yapay zekâ ile teşhis ve PEMF (darbeli manyetik alan) ile seans uygulayan bir platformdur. Bu client, uygulamayı bilgisayarınıza indirir, kurar ve başlatır. Aşağıdaki adımlar hiç deneyimi olmayan biri için hazırlanmıştır — sırayla takip etmeniz yeterli.",
   "profTitle": "3 Profil — hangisi sizin için?",
   "profiles": {
    "p01": {
     "does": "Kedinizin kamera görüntüsüyle yapay zekâ ön-teşhisi yapar: hastalık, organ, görüntü ve ses analizi. Cihaz veya seans İÇERMEZ.",
     "key": "home",
     "use": {
      "u01": "Uygulama açılınca ‘Ev Sahibi’ profilini seçip hesabınızla girin.",
      "u02": "‘Akıllı Teşhis’ ekranına gidin.",
      "u03": "Kameranızı kediye doğrultun ya da bir fotoğraf/ses dosyası yükleyin.",
      "u04": "Sonucu ve önerileri okuyun — kesin tanı için mutlaka bir veteriner hekime danışın."
     },
     "who": "Evcil hayvan (kedi) sahipleri için"
    },
    "p02": {
     "does": "Teşhis + PEMF cihazıyla seans uygulama + hasta kaydı, seans geçmişi, sensör takibi, KPI paneli ve simülatör. Ev Sahibi teşhis modellerini de içerir (bu yüzden boyutu daha büyüktür).",
     "key": "vet",
     "use": {
      "u01": "‘Veteriner Hekim’ profilini seçip girin.",
      "u02": "‘Hastalar’ ekranından yeni hasta ekleyin.",
      "u03": "‘Kontrol’ ekranından seansı başlatın; bobinleri elle ayarlayın veya ‘AI Pro’ ile otonom sürün.",
      "u04": "‘Sensörler’ ve ‘Geçmiş’ ile seansı izleyin; ‘KPI’ ile klinik istatistiklerinizi görün."
     },
     "who": "Veteriner hekimler ve klinikler için"
    },
    "p03": {
     "does": "Petri, histopatoloji, böbrek ve fantom yapay zekâ modelleri; örnek/veri kaydı ve geçmiş. Cihaz İÇERMEZ.",
     "key": "research",
     "use": {
      "u01": "‘Araştırma Modu’ profilini seçip girin.",
      "u02": "‘Akıllı Teşhis’ten ilgili araştırma modelini seçin.",
      "u03": "Görüntü veya veri dosyanızı yükleyin.",
      "u04": "Sonuçları inceleyip ‘Geçmiş’e kaydedin."
     },
     "who": "Araştırmacılar ve laboratuvarlar için"
    }
   },
   "steps": {
    "s01": {
     "b": "En üstteki 'Ana uygulama' kartı her kurulumda gelir ve kaldırılamaz (arayüz ve ortak modeller; boyutu sağında yazar, kuruluysa 'kurulu' der). Altındaki 3 profilden en az birini işaretleyin (Ev Sahibi, Veteriner Hekim, Araştırma). Birden fazla seçebilirsiniz; her kartın sağında YALNIZ kendi indirme boyutu yazar, düğmedeki toplam yalnız gerçekten inecekleri sayar (kurulu değilse ana uygulama + yeni seçtikleriniz). 'Profilleri değiştir'de zaten kurulu profil 'kurulu' der ve sayılmaz; işaretini kaldırdığınız kurulu profil 'kaldırılacak' rozeti alır ve düğmeye basınca bu bilgisayardan silinir.",
     "t": "Profil(ler)inizi seçin"
    },
    "s02": {
     "b": "Seçtiğiniz modeller inip kurulur. Çubukta yüzde, hız (MB/s) ve kalan süre görünür. İstediğinizde Duraklat veya İptal edebilir; internet kesilse ya da bilgisayar kapansa bile tekrar açtığınızda kaldığınız yerden devam edebilirsiniz.",
     "t": "‘Kur ve Başlat’a tıklayın"
    },
    "s03": {
     "b": "Kurulum bitince uygulama tarayıcınızda açılır. Sonraki açılışlarda bu penceredeki ‘Başlat’ düğmesiyle saniyeler içinde açarsınız.",
     "t": "Uygulama otomatik açılır"
    }
   },
   "stepsTitle": "Kurulum — 3 adım",
   "trouble": {
    "k01": {
     "b": "Bu penceredeki ‘Onar’a basın — paketleri yeniden doğrular ve eksikleri tamamlar.",
     "t": "Uygulama açılmıyor veya bir model eksik"
    },
    "k02": {
     "b": "Uygulamayı tekrar açın; ‘Kaldığınız yerden devam edilsin mi?’ sorusuna ‘Devam Et’ deyin. İndirilen kısım korunmuştur.",
     "t": "İndirme yarıda kaldı (internet kesildi / bilgisayar kapandı)"
    },
    "k03": {
     "b": "‘Uygulamayı kaldır’a basın (hasta verileriniz KORUNUR), sonra tekrar kurun.",
     "t": "Baştan kurmak istiyorum"
    },
    "k04": {
     "b": "Üstteki ‘Web Sitesi’ veya alttaki ‘Destek’ bağlantısını kullanın.",
     "t": "Daha fazla yardım"
    }
   },
   "troubleTitle": "Sorun giderme"
  },
  "langLabel": "dil",
  "loginBtn": "Giriş yap",
  "loginEmail": "E-posta",
  "loginEmpty": "E-posta ve parola gerekli.",
  "loginForgot": "Şifremi unuttum",
  "loginLead": "PEMF Vet hesabınızla giriş yapın — uygulama sizden bir daha giriş istemeyecek.",
  "loginNoPersist": "Bu platformda oturum güvenli biçimde saklanamıyor — giriş yalnız bu açılış için geçerli.",
  "loginPass": "Parola",
  "loginPwInvisible": "Parolada görünmeyen bir karakter var (kopyala-yapıştırdan gelmiş olabilir). Silip elle yazmayı deneyin.",
  "loginPwSpace": "Parolanızın başında veya sonunda boşluk var — genelde yapıştırmadan gelir. “Göster” ile kontrol edin.",
  "loginRemember": "Beni hatırla",
  "loginRequired": "Kurulum ve onarım için giriş yapmalısınız.",
  "loginSignup": "Hesap oluştur",
  "loginTitle": "Giriş yapın",
  "loginWait": "Giriş yapılıyor…",
  "logout": "Çıkış",
  "logoutBody": "Bu bilgisayardaki oturumunuz silinecek ve uygulamadaki giriş kapatılacak. Devam edilsin mi?",
  "logoutTitle": "Çıkış yap",
  "luReady": "PEMF Vet Client {{surum}} yayınlandı — uygulamayı kapatıp açtığınızda kurulacak.",
  "noChange": "Değişiklik yok",
  "notInstalled": "Uygulama kurulu değil.",
  "notSupported": "Bu platform ({{platform}}) için uygulama paketi henüz yayınlanmadı.",
  "offline": "Çevrimdışı",
  "offlineLogin": "İnternet bağlantısı yok — giriş yapılamıyor. Kurulu uygulamayı çevrimdışı başlatabilirsiniz.",
  "offlineReady": "İnternet bağlantısı yok — güncelleme kontrolü ve profil listesi alınamadı. Kurulu uygulamayı yine de başlatabilirsiniz.",
  "offlineSelect": "İnternet bağlantısı yok; kurulum için bağlantı gerekli. Bağlantıyı kontrol edip tekrar deneyin.",
  "offlineStart": "Çevrimdışı başlat",
  "ok": "Tamam",
  "pause": "Duraklat",
  "pausedLead": "İndirme duraklatıldı — inen kısım bilgisayarınızda korundu. Kaldığınız yerden devam edebilirsiniz.",
  "pausedTitle": "Duraklatıldı",
  "profilMeta": {
   "home": {
    "aciklama": "Kedi teşhis modelleri — hastalık, organ, görüntü, ses",
    "ad": "Ev Sahibi"
   },
   "research": {
    "aciklama": "Araştırma modelleri — petri, histopatoloji, böbrek, fantom",
    "ad": "Araştırma Modu"
   },
   "vet": {
    "aciklama": "Klinik teşhis + seans (em_kedi, termal)",
    "ad": "Veteriner Hekim"
   }
  },
  "pwHide": "Gizle",
  "pwHideTitle": "Parolayı gizle",
  "pwShow": "Göster",
  "pwShowTitle": "Parolayı göster",
  "ready": "hazır — tarayıcıda açıldı",
  "readyLead": "PEMF Vet kuruldu. Uygulamayı başlatın veya profillerinizi güncelleyin.",
  "readyTitle": "Hazır!",
  "reconnTitle": "Yeniden bağlanılıyor…",
  "reconnecting": "bağlantı koptu, yeniden deneniyor",
  "removeFailed": "Profil kaldırılamadı: {{neden}}",
  "removing": "Kaldırılıyor…",
  "repair": "Kurulumu onar",
  "repairBody": "Kurulu paketler yeniden doğrulanıp eksik/bozuk dosyalar onarılacak. Bu birkaç dakika sürebilir. Devam edilsin mi?",
  "repairTitle": "Kurulumu onar",
  "resume": "Devam Et",
  "resumeBody": "Önceki kurulum tamamlanmadı (internet kesilmiş veya kapatılmış olabilir). İndirilen kısım korundu — kaldığınız yerden devam edilsin mi?",
  "resumeNo": "İptal et",
  "resumeTitle": "Kurulum yarım kaldı",
  "resumeYes": "Devam Et",
  "retry": "Tekrar dene",
  "rtBg": "Yeni sürüm arka planda indiriliyor — uygulamayı şimdi kullanabilirsiniz, güncelleme bir sonraki açılışta kurulacak.",
  "rtBgCancelled": "Güncelleme indirmesi iptal edildi — bir sonraki açılışta yeniden denenecek.",
  "rtBgDone": "Yeni sürüm indirildi — güncelleme bir sonraki açılışta kurulacak.",
  "rtBgFail": "Arka plan indirmesi tamamlanamadı — bir sonraki açılışta kaldığı yerden denenecek.",
  "rtBgPaused": "Güncelleme indirmesi duraklatıldı — inen kısım korundu, \"Devam et\" ile kaldığı yerden sürer.",
  "rtBgPrep": "Hazırlanıyor…",
  "rtBlocked": "Yeni sürüm kurulmayı denedi ama cihazda başlayamadı; güvenlik için eski sürüme dönüldü. Otomatik deneme durduruldu — \"Onar\" ile yeniden deneyebilir ya da bir sonraki sürümü bekleyebilirsiniz.",
  "rtBusy": "Seans sürerken güncelleme yapılmaz — seans bitince otomatik güncellenecek.",
  "rtDone": "Uygulama güncellendi.",
  "rtLead": "Yeni bir uygulama sürümü bulundu — indirilip kuruluyor. Bittiğinde başlatabilirsiniz.",
  "rtReady": "Güncelleme hazır — uygulamayı kapatıp açtığınızda kurulacak.",
  "rtRecall": "⚠️ ÖNEMLİ GÜVENLİK GÜNCELLEMESİ bekliyor. Bu sürüm artık desteklenmiyor; uygulamayı KAPATIP AÇIN ki güncelleme kurulsun. Seans sürüyorsa bitmesini bekleyin.",
  "rtRollback": "Yeni sürüm açılamadı; önceki çalışan sürüme geri dönüldü. Uygulama kullanılabilir.",
  "rtRollbackFail": "Yeni sürüm açılamadı ve geri alma tamamlanamadı. Lütfen \"Onar\" ile kurulumu yenileyin.",
  "rtTitle": "Uygulama güncelleniyor…",
  "runningLead": "PEMF Vet çalışıyor. Uygulama penceresini kapatırsanız buradan yeniden başlatabilirsiniz.",
  "selCancel": "Geri dön",
  "selLead": "Ana uygulama her kurulumda gelir (kaldırılamaz). Profillerden en az birini seçin — yalnız seçtikleriniz indirilir.",
  "selTitle": "Kullanım profilinizi seçin",
  "selfUpdateFailed": "Başlatıcı güncellemesi tamamlanamadı — uygulama normal açılıyor. Bir sonraki açılışta yeniden denenecek.",
  "start": "Başlat",
  "startChecking": "Güncelleme kontrol ediliyor…",
  "starting": "başlatılıyor",
  "tagline": "Veteriner PEMF seans + yapay zekâ teşhis platformu",
  "uninBody": "İndirilen uygulama ve AI modelleri silinecek.\n\nKORUNAN VERİLER (tıbbi kayıt — kaldırma ile SİLİNMEZ):\n• Hasta kayıtları\n• Seans geçmişi\n• AI analiz geçmişi\nKonum: %APPDATA%\\PEMF_GUI\n\nBunları da silmek istiyorsanız KALDIRMADAN ÖNCE uygulama içinden silin (Hastalar → \"Tümünü Sil\", AI Geçmişi → \"Geçmişi Sil\").\n\nDevam edilsin mi?",
  "uninTitle": "Uygulamayı kaldır",
  "uninstall": "Uygulamayı kaldır",
  "updatingApply": "Güncelleme uygulanıyor, uygulama yeniden başlatılıyor…",
  "updatingLead": "Yeni bir başlatıcı sürümü bulundu — indirilip kuruluyor. Uygulama kendiliğinden yeniden açılacak.",
  "updatingTitle": "Başlatıcı güncelleniyor…",
  "verifying": "bütünlük doğrulanıyor",
  "web": "Web Sitesi",
  "willRemove": "kaldırılacak"
 }
};
