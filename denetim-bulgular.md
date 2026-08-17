# PEMF Vet — Hata Denetimi (2026-08-17)

Kapsam: yalnızca **kırık davranış**. Refactor/stil/mimari/kütüphane önerisi yok.
Yöntem: tek başına oryantasyon (`BUILD.md`, `README.md`, `CHANGELOG.md`, alt-README'ler) →
beş katman ajanı (şüpheli listesi) → her şüpheli için ayrı **çürütme** ajanı →
katman-aşan zincirler elle kovalandı.

Ciddiyet ölçeği: **1** hasta güvenliği · **2** veri kaybı/bozulması · **3** cihazın
açılamaz/kullanılamaz hâle gelmesi · **4** yanlış klinik çıktı · **5** diğer işlevsel.

## DÜZELTME KAYDI (2026-08-17)

Ciddiyet sırasıyla başlandı. **Her düzeltme için ayrı bir test yazıldı, düzeltmeden ÖNCE kırmızı
olduğu görüldü, sonra yeşile alındı.** Kırmızı-önce kanıtı mutasyon kanıtının en güçlü hâlidir:
test, kusurun GERÇEK hâline karşı ölçülmüştür.

| # | Bulgu | Dosya(lar) | Test | Önce → Sonra |
|---|---|---|---|---|
| 1 | ESP `duration=0` kapağı yok (cid. 1) | `servers/api_server.py` (`_esp_duration_seconds` + 2 çağrı yeri) · `pf/.../CoilParameterPanel.tsx` (dayanaksız güvence metni) | `tests/test_esp_gozetimsiz_sure_kapagi.py` (6) · `pf/.../CoilDurationHonesty.test.tsx` (5) | `assert 0 == 7200` → 11/11 ✓ |
| 2 | Inno installer bobinleri güvene almadan kill ediyor (cid. 1) | `build_tools/PEMF_Backend_Setup.iss` | `tests/test_inno_kurulum_bobin_guvenligi.py` (4) · `tests/test_inno_kod_derlenir.py` (1, gerçek ISCC) | 2 kırmızı → 5/5 ✓ |
| 3 | Seans sürerken uçuştaki APK kurulumu iptal edilmiyor (cid. 1) | `pf/src/hooks/useApkGuncelleme.ts` | `pf/.../useApkGuncelleme.seansKapisi.test.ts` (7) | 3 kırmızı → 7/7 ✓ |
| 6 | `denetim_oku` havuz `row_factory`'sini kalıcı bozuyor (cid. 2) | `database/sqlcipher_util.py` (`dict_satir_fabrikasi`) · `database/treatment_history_db.py` · `servers/sync_worker.py` (2 yer) | `tests/test_row_factory_havuz_kirlenmesi.py` (5) | KVKK sayımı `1 → 0`, bütünlük `ok:False` → 5/5 ✓ |

| 9 | Launcher STM portunu `auto` geçirmiyor (cid. 3) | `launcher/core/src/install.rs` (`ENV_STM_PORT` + `backend_env_with`) | 3 yeni Rust testi (`device_env_anahtarlari_launcherda_KARSILIGINI_BULUR` + 2 davranışsal) | `["PEMF_STM_PORT"]` eksik → 203/203 ✓ |
| 14 | Inno build'i varsayılan yolda çöküyor (cid. 3) | `build_tools/build_installer.ps1` (aynalama "kaynak == hedef" ise atlanır) | `tests/test_installer_frontend_aynalama.py` (2, **bloğu gerçekten koşturur**) | `Cannot find path '…\pf\dist'` → 2/2 ✓ |
| 16 | Migration rollback'inde `Path + str` ölü kod (cid. 3) | `database/treatment_history_db.py` | `tests/test_rollback_wal_temizligi.py` (2) | bayat `-wal` diskte KALDI → 2/2 ✓ |

| 4 | Elle bozulmuş `pemf_secrets.json` → YENİ SQLCipher anahtarı (cid. 2) | `utils/secrets_manager.py` (karantina-kanıtı kapısı) | `tests/test_bozuk_sir_dosyasi_kalici_fail_closed.py` (7) | 4 kırmızı → 7/7 ✓ |
| 11 | Hasta UUID zinciri HER içe aktarımda kopuyor (cid. 3) | `database/patient_database.py` (`add_patient(..., patient_id=)`) · `servers/api_server.py` (import döngüsü) | `tests/test_ice_aktarma_hasta_uuid_zinciri.py` (5, biri UÇTAN UCA) | 4 kırmızı → 5/5 ✓ |
| 5 | Kurtarma zarfı sağlamlığı yalnız `.exists()` (cid. 2) | `utils/backup_recovery.py` (deneme-açma + atomik yazım) | `tests/test_kurtarma_zarfi_saglamlik.py` (4) | 2 kırmızı → 4/4 ✓ |
| 7 | Frekans artışında bayat duty (cid. 2) | `firmware/main.c` (`[FIX-1c]`) | `tests/test_firmware_frekans_artisi_duty.py` (8: ISR modeli + çıpalar + yapısal kapı) | 3 kırmızı → 8/8 ✓ ⚠️ **TEZGÂHTA DOĞRULANMADI** |

| 10 | Başarısız self-update ekranı kilitliyor (cid. 3) | `launcher/app/ui/index.html` (`oncekiEkran` geri alma + iki dilde metin) | `tests/test_self_update_ekran_kilidi.py` (6, gerçek JS Node'da koşar) | 3 kırmızı → 6/6 ✓ |
| 13 | `home.zip` URL'si boş etikete taşınıyor (cid. 3) | `scripts/make_manifest.py` (sha aynıysa URL korunur + bildirim) | `tests/test_manifest_degismeyen_paket_url.py` (5) | 2 kırmızı → 5/5 ✓ |
| 17 | "Ort. Sıcaklık" ölçüm yapmayan bobinlerle seyreltiliyor (cid. 4) | `pf/src/screens/KpiDashboardScreen.tsx` (`hesaplaOrtSicaklik`) | `pf/.../kpiSicaklikDurustlugu.test.tsx` (7) | 7 kırmızı → 7/7 ✓ |
| 12 | AI mikroserviste modalite kapısı atlanıyor (cid. 3) | `servers/ai_router.py` (`_kapili_devret` + 8 uç) | `tests/test_ai_mikroservis_modalite_kapisi.py` (5) | mikroserviste `HTTP 200 "Grade 4 %100"` → 5/5 ✓ |
| 18 | Türkçe `İ`/`I` aramada kayıt bulunamıyor (cid. 4) | `pf/src/utils/aramaNormalize.ts` (yeni, TEK KAYNAK) + 3 arama yüzeyi | `pf/.../aramaNormalize.test.ts` (13) | süit yüklenemedi → 13/13 ✓ |

**Ek doğrulama (bulgu 13) — GERÇEK VERİ ÜZERİNDE SALT-OKUMA KURU KOŞU:** `--out` ile geçici bir
dosyaya üretildi, gerçek `pemf-app-packages/manifest.json`'a **dokunulmadı** (`git status` temiz):
```
~ URL KORUNDU: home.zip (sha ayni, etiket: client-app-v1.9.11)
models.home  : .../client-app-v1.9.11/home.zip     <- asset'in GERÇEKTEN bulunduğu etiket
layers app   : .../client-app-v1.9.16/base-app.zip <- her yayında değişir, yeni etikete gider
runtimes base: .../client-app-v1.9.16/base.zip
```

**⚠️ Kendi düzeltmemde ikincil bir hata yakalandı (bulgu 13):** eklediğim bildirim satırı `→`
karakteri içeriyordu ve betiğin cp1254 konsoluna yazılırken `UnicodeEncodeError` ile **süreci
çökertti** (`exit=1`, manifest yazıldıktan SONRA). Testler bunu anında gösterdi; metin ASCII'ye
çevrildi. Bu deponun bilinen kodlama tuzağının aynısı.

**⚠️ Bulgu 18'de testimin bir boşluğu vardı:** yapısal çıpa yalnız "dosyada `aramaEslesir` geçiyor
mu" diye bakıyordu; çağrı varken **import eksik** olabiliyordu (ilk denememde tam bu oldu ve yalnız
`tsc` yakaladı). Çıpa artık `import ... from "@/utils/aramaNormalize"` desenini de denetliyor.

**⚠️ BULGU 7 İÇİN AÇIK KAYIT:** denetim ortamında donanım yok. Koşan şey C kodu değil ISR'ın Python
modelidir (deponun kendi `test_firmware_stop_latency.py` yaklaşımıyla aynı sınır). C kaynağındaki
düzeltmenin varlığını ayrı bir **yapısal kapı** denetliyor ve mutasyonla doğrulandı, ama
**hiçbiri tezgâh doğrulaması değildir** — gerçek donanımda ölçülmeden yayınlanmasını önermiyorum.

**Model beni iki kez düzeltti (kayda geçiyor):** (a) `ref_ms` hizalaması tick'i sıfıra çekmiyor;
ilk modelim tick=0 varsayıp `period_reset`in klempi hemen uygulamasına yol açtığı için kusuru
GÖRMÜYORDU (yanlış-yeşil). (b) "İlk 500 ms'de dozun 4,78×'i" ölçümü **yanlış değişmezdi**:
aşağı-slew KASITLI (inrush/EMI) ve %50→%5 geçişi enerjiyi azaltır. Doğru değişmez: *geçiş, duty
oranını iki uç noktanın (eski oran, yeni hedef) hiçbirinin üstüne çıkarmamalı* — klemp %99,8 yapıp
ikisini de aşıyordu.

**Ek mutasyon doğrulaması (bulgu 7):** C düzeltmesi kaynaktan çıkarıldı → yapısal kapı kırmızıya
döndü. Kapı **yorumları temizledikten SONRA** sınır arıyor; ilk yazımda açıklama yorumumdaki
`if (period_reset)` metni bitiş çıpası sanılıp blok yarıda kesilmişti.

**Ek mutasyon doğrulaması (bulgu 9):** `device.env`'e uydurma bir `PEMF_YENI_DAVRANIS_AYARI=1`
eklendi ve eksiklik kapısı onu **yakaladı** → kapı bu hata sınıfının **dördüncü** örneğini de
engelliyor. (Sınıfın önceki üçü: `ENV_ENCRYPT_AT_REST` 2026-08-08, `ENV_ENABLE_TUNNEL` 2026-08-12,
`ENV_STM_PORT` 2026-08-17.)

**Ek mutasyon doğrulaması (bulgu 14):** "kaynak == hedef" koruması devre dışı bırakıldı →
davranışsal test kırmızıya döndü (üretim hatası birebir yeniden üretildi).

**Ek mutasyon doğrulaması (bulgu 16):** `str(self.db_path)` → `self.db_path` geri alındı → **iki
kapı da** kırmızıya döndü. Ayrıca yapısal çıpa **yorum satırlarını atıyor** (aksi hâlde hatayı
açıklayan yorumu kusur sanır ya da doğru deseni anlatan bir yorumla geçilebilirdi).

**Ek mutasyon doğrulaması (bulgu 2):** `.iss` üzerinde iki mutasyon uygulandı ve **ikisi de
yakalandı** — (a) `Break;` → `Break` (sözdizimi) derleme kapısını kırdı, (b) `taskkill`'i graceful'ün
önüne taşımak sıra kapısını kırdı. Ayrıca sıra kapısı **yorum satırlarını atıyor**, yani "doğru
sırayı anlatan bir yorum yazmakla" geçilemez.

**Regresyon durumu (son ölçüm):** backend `1140 passed, 1 failed` · launcher `cargo test` **0 hata** (9 ikili) ·
`pf` `463 passed`, `tsc` temiz.
Tek düşen test (`test_KRITIK_site_APK_surumu_versions_json_ile_AYNI`) **benim değişikliklerimle
ilgisiz** — `git stash` ile doğrulandı: `api_server.py` geri alınmış hâlde de düşüyor. Sebebi süren
2.3.17 yayını (`pemf-vet-web/src/config.ts` `androidVersion: '2.3.16'` ↔ `versions.json` `2.3.17`);
disiplin testi işini yapıyor.

### Düzeltmelerde verilen bilinçli kararlar

- **Bulgu 1:** kapak sabiti YENİDEN TANIMLANMADI — `controllers.hardware_controller.
  GOZETIMSIZ_VARSAYILAN_DAKIKA`'dan okunuyor ve yapısal bir test bunu kilitliyor. İki transport bir
  gün ayrışamasın; bu bulgunun kök nedeni tam olarak o ayrışmaydı. `duration=0` **reddedilmedi**
  (Kontrol Paneli'ni bozardı) ve açıkça verilen süreye dokunulmadı — karşı-kanıt testleri var.
  freq/duty/48°C sınırlarına DOKUNULMADI (sahip kararı).
- **Bulgu 2:** force-kill **kaldırılmadı**, graceful'ün arkasına alındı (`AppExit Default Restart`
  + dosya kilitleri yüzünden fallback şart). Servis yoksa (`sc query` → 1060) bekleme hiç yapılmıyor
  → taze kurulum yavaşlamıyor. Bekleme ÜST SINIRLI (~17 sn = 15 sn console-stop + 1,5 sn flush) →
  asılı bir servis kurulumu sonsuz bekletmiyor.
- **Bulgu 3:** kapı KANCADA (`useApkGuncelleme`), bileşende değil — `MobileUpdateGate` provider'ların
  ÜSTÜNDE durduğu için context'e erişemiyor; cihazın kendisine (`/session/active`) sorulunca AÇILIŞ
  KAPISI ve BANT aynı korumayı paylaşıyor. Bandın görünürlük kapısı KALDIRILMADI (ikinci katman).
  **Bilinçli FAIL-OPEN:** seans durumu öğrenilemezse kurulum engellenmiyor — fail-closed olsaydı
  farklı ağdaki telefon bir daha ASLA güncellenemezdi (sahibin yasakladığı kalıcı kilit). Yalnız
  POZİTİF kanıt (`is_active === true`) erteliyor. Sorgu kurulumdan HEMEN ÖNCE yapılıyor (indirme
  dakikalar sürer; başlangıçtaki duruma güvenmek bulgunun kendisiydi) ve `timeoutMs: 2500` ile
  en kötü ~5,4 sn bekletiyor.
- **Bulgu 9:** değer `auto`, ama **ortamda tanımlıysa DOKUNULMUYOR** → sahada portu sabitlemek
  (`PEMF_STM_PORT=COM7`) ya da STM simülatörü (`socket://…`) kullanmak hâlâ mümkün. `auto`
  bulamazsa eski davranışa (`COM10`) düşüyor → COM10'un doğru olduğu makinelerde davranış
  DEĞİŞMİYOR. Asıl kalıcı değer, tek satırlık env düzeltmesi değil **eksiklik kapısı**: artık
  `device.env`'e eklenen her yeni anahtar ya geçirilmek ya da gerekçesiyle muaf tutulmak zorunda.
- **Bulgu 14:** kopyalama **kaldırılmadı**, yalnız "kaynak == hedef" durumunda atlanıyor →
  `$FrontendDir` bir gün yeniden ayrı bir dizine dönerse yol çalışmaya devam eder (karşı-kanıt
  testi bunu kilitliyor). Test bloğu **metin olarak denetlemiyor, gerçekten koşturuyor**.
- **Bulgu 16:** düzeltme tek satır, ama testi **davranışsal** yaptım: eski "koruma" bir kaynak-metin
  grep'iydi (`tests/test_treatment_persistence.py:339`) ve `TypeError`'lı kodu geçiriyordu. Yeni test
  bileşik arızayı (kapanış-checkpoint'i de düştü) modelliyor — ölçtüm ki gerçek
  `close_connections()` yan-dosyaları zaten siliyor, dolayısıyla daha erken yazmak **yanlış-yeşil**
  veriyordu. Yapısal çıpa yanında **duruyor** (başka bir yan-dosya için desen tekrarlanırsa görünür).
- **Bulgu 6:** restore değeri SABİTLENMEDİ — önceki fabrika saklanıp aynen geri konuyor. Havuz
  bağlantıyı düz SQLite'ta `sqlite3.Row`, şifreli kurulumda `sqlcipher.Row` ile kurar; `None`a
  sıfırlamak şifreli kurulumda `row["kolon"]` erişimlerini kırardı. `sync_worker`'daki iki kardeş
  yer de kapatıldı (kısmi düzeltme bırakılmadı); PUSH döngüsünde fabrika ağ RPC'leri boyunca
  TUTULMUYOR, yalnız okuma sarılıyor.

### Düzeltme 8-11'de verilen bilinçli kararlar

- **Bulgu 4 (sır dosyası):** koruma **diskteki kanıta** (`*.corrupt.*`) bakıyor, belleğe DEĞİL —
  backend sık yeniden başlar ve süreç-ömürlü bir kilit bir sonraki açılışta yine yeni anahtar
  üretilmesini engellemezdi. **Taze kurulum bozulmuyor** (dosya yok + kanıt yok → eskisi gibi boş
  doküman) ve **operatörün çıkış yolu açık**: karantina dosyalarını kaldırmak makineyi normal
  çalışmaya döndürür — aksi hâlde cihazı KALICI açılamaz yapardık, yani düzeltmeye çalıştığımız
  şeyden kötüsünü üretirdik. Hata mesajı iki yolu da açıkça yazıyor.
  **Hâlihazırda etkilenmiş makineler YENİDEN tuğlalaşmıyor:** onlarda `pemf_secrets.json` zaten
  yeniden üretilmiş olduğu için dosya VAR → kapı hiç ateşlemiyor.
- **Bulgu 11 (UUID zinciri):** yalnız `id` KORUNUYOR; hasta satırlarını **güncelleme (upsert)
  getirilmedi** — paketten gelen bir değerin yerel olarak düzeltilmiş kaydı ezmesi ayrı bir sahip
  kararıdır. Aynı paket iki kez alınırsa satır ATLANIR ve **sayılıp loglanır** (yoksa geri yükleme
  "hiç hasta gelmedi" gibi görünürdü). Geçersiz/bozuk `id` içe aktarmayı DÜŞÜRMÜYOR: yeni id
  üretilip satır yine yazılıyor — tek bozuk satırın tüm klinik geçmişinin taşınmasını engellemesi
  daha kötü olurdu.
  ⚠️ Testin uçtan uca kısmı **API üzerinden** doğruluyor, modül singleton'ı üzerinden değil: tam
  süit koşusunda `get_patient_database()`'in testte ve uç noktada aynı örneği döndürmediği ölçüldü
  (singleton temizlendi ama içe aktarma `UNIQUE constraint failed: patients.id` ile düştü). İlk
  yazımda test izole geçip tam süitte düşüyordu; sebebi bu.
- **Bulgu 5 (kurtarma zarfı):** "değişmediyse yeniden yazma" davranışı **KASITLI ve testle kilitli**
  (*"operatörün doğruladığı zarf her gün değişip şüphe uyandırmasın"*) → korundu. Değişen tek şey:
  "var mı?" yerine **"gerçekten açılıyor mu?"** sorulması. Yazım ayrıca atomikleştirildi
  (pid'li tmp + fsync + `os.replace`) — aynı depoda `secrets_manager._save` bu deseni kullanıp
  yorumunda NTFS yarım-dosya tehlikesini açıkça anlatıyor; felaket kurtarmanın tek dayanağı olan
  dosya o korumadan yoksundu.
- **Bulgu 7 (firmware):** enerjiyi ARTIRAN yönün slew ile sınırlanması (inrush/EMI) **değişmedi**;
  yalnız mevcut duty ORANI yeni periyoda ölçekleniyor ve güvenlik klempi `period_reset`'i
  BEKLEMEDEN uygulanıyor. Düzeltme, dosyanın kendi `[FIX-1b]` ilkesiyle aynı: tpp, duty-tick,
  faz-tick ve dds-tick'in hepsi tek kritik bölgede aynı parametre setinden türetilir —
  `g_duty_ticks` o ailenin yeniden ölçeklenmeyen tek üyesiydi.

---

### Düzeltme 12-15'te verilen bilinçli kararlar

- **Bulgu 10 (self-update kilidi):** ekran, devralmadan ÖNCEKİ hâline geri alınıyor — dosyanın kendi
  `curScreen()` yardımcısıyla ("arka plandaki manifest işi kullanıcının ekranını ÇALMASIN diye")
  aynı ilke. Başarısızlıkta **nötr bilgi notu** gösteriliyor (kırmızı `fail` DEĞİL): uygulama normal
  açılıyor, kullanıcının yapacağı bir şey yok ve kırmızı hata gereksiz telaş yaratırdı.
  ⚠️ `record_selfupdate_attempt` sayacına **bilerek dokunulmadı**: geçici ağ kopmalarını saymaya
  başlamak, zayıf WiFi'li bir kliniğin client güncellemelerini KALICI susturabilirdi (1.9.27
  girdisi: aynı makinede ~%33 anlık TCP kopması ölçüldü). Ekranın geri alınması "cihaz açılmıyor"
  sonucunu tamamen kaldırıyor; kalan şey her açılışta birkaç saniyelik sessiz yeniden deneme.
- **Bulgu 13 (manifest URL):** URL **dondurulmuyor** — yalnız sha AYNIYSA korunuyor. sha değişirse
  yeni etikete taşınıyor (karşıt-kanıt testi kilitliyor), yani yeni içerik her zaman yayınlanabilir.
  Korunan her URL ekranda **bildiriliyor**; yayıncı diff'te "neden bu URL değişmedi?" sorusunu
  cevapsız bırakmasın.
- **Bulgu 17 (KPI sıcaklık):** hesap test edilebilir bir yardımcıya (`hesaplaOrtSicaklik`) çıkarıldı
  ve ölçüm yokken **sayı yerine "ölçüm yok"** yazılıyor; ölçüm varsa kaç bobinin ölçüldüğü etikete
  ekleniyor. `0` nöbetçisi korunuyor (ölçümsüz bobin `0` gönderir); negatif değer sensör arızasıdır
  ve ölçüm sayılmıyor. Gerçek termal interlock bu ekrandan bağımsız — düzeltilen şey GÖSTERİM.
- **Bulgu 18 (Türkçe arama):** kural **tek kaynağa** (`aramaNormalize.ts`) alındı; bulgunun kök
  nedeni aynı kuralın üç yerde kopyalanmasıydı. **Aksan DÜZLEŞTİRİLMİYOR** — "Şirin" ile "Sirin"i
  birleştirmek bir hasta-kimliği ekranında yanlış kayda bakmak demektir; kapsam yalnız İ/I kuralı
  ve karşıt-kanıt testleri ş/ç/ğ/ü/ö ayrımını kilitliyor. Boş sorgu davranışı (süzme yok) korundu.

---

### Düzeltme 16 (bulgu 12) — kapsam kararı ve KALAN İŞ

Kapı artık devretmeden ÖNCE çalışıyor: girdi **tek kez** okunuyor (`UploadFile.read()` ikinci
çağrıda boş döner), kapıdan geçiriliyor ve GPU servisine **aynı baytlar** `image_base64` olarak
gidiyor. 8 uç: landmark · segmentation · thermal · reticulocytes · em_fantom · kidney_ct ·
histopath · cat_organ.

Deneysel kanıt (gerçek CT fixture'ı → Böbrek Patoloji ucu, `delegate_infer` casuslanmış):
mikroservis modunda ÖNCE `HTTP 200 {"top_1_class":"Grade 4","top_1_prob":1.0}`, SONRA **HTTP 422**
ve GPU servisine hiç devredilmiyor. Karşıt-kanıtlar: doğru modalite (patoloji preparatı) hâlâ
devrediliyor; **aynı CT görüntüsü doğru ucunda (`kidney_ct`) devrediliyor** — yani düzeltme
"her şeyi reddet"e dönüşmedi; gömülü mod hiç etkilenmedi.

**⚠️ BİLEREK KAPSAM DIŞI BIRAKILAN İKİ ŞEY (açık kayıt):**
1. **Ses ucundaki sessizlik kapısı** hâlâ devretmenin arkasında. Kapı ffmpeg transcode + RMS
   ölçümüne bağlı; devretmenin önüne almak ses hattını yeniden kurgulamak demek ve bu ortamda
   ffmpeg davranışını doğrulayamadım. Mikroservis profilinde sessiz kayıt hâlâ kendinden emin bir
   duygu etiketi alabilir ve yanıtta `guvenilir`/`belirsizlik`/`rms_dbfs` alanları gelmez.
2. **`:8100`e doğrudan yapılan çağrılar** (backend'i atlayan bir istemci) hâlâ kapısız. Deponun
   kendi kuralı (`ai_hub/inference_petri_dish/plausibility.py`) kalıcı çözümü yazıyor: kapıları
   `ai_hub/`e taşımak. Bu, AI hattında kendi turunu hak eden daha geniş bir iş.

**⚠️ Testimde iki hata yaptım, ikisi de kayda geçiyor:** (a) `image_base64` bir **Form** alanı,
JSON gövdesi değil — `json=` gönderip 500 alınca kapının atlandığını sandım; multipart'a çevirdim
(mevcut `test_image_domain_guard.py` de öyle yapıyor). (b) Yapısal kapının yorum filtresi yalnız
`#` satırlarını atıyordu ve **kendi docstring'imdeki** örneği kusur sandı; filtre artık
docstring'leri de atıyor — aynı dersin üçüncü tekrarı.

---

## Özet tablo

| # | Bulgu | Cid. | Durum |
|---|---|---|---|
| 1 | ESP bobinlerinde (6-8) `duration=0` gözetimsiz-sürüş kapağı YOK | 1 | ESP firmware'i depoda yok → tek açık nokta |
| 2 | Inno installer bobinleri güvene almadan force-kill ediyor | 1 | elle offline kanal; 6-8 kalan seans süresi enerjili |
| 3 | Seans başlayınca uçuştaki APK kurulumu iptal edilmiyor | 1 | telefon kumandası ~1-2 dk kayboluyor |
| 4 | Elle bozulmuş `pemf_secrets.json` → YENİ SQLCipher anahtarı | 2 | tıbbi kayıt kalıcı okunamaz hâle gelebilir |
| 5 | Kurtarma zarfı sağlamlığı yalnız `.exists()` + yanlış güvence logu | 2 | düşük olasılık, sessiz |
| 6 | `denetim_oku` havuz `row_factory`'sini kalıcı bozuyor | 2 | KVKK onayı görünmez + export/import 500 |
| 7 | Frekans ARTIŞINDA bayat duty → ~1 s tek-polarite + 4,78× on-time | 2 | firmware; parametre-sadakati |
| 8 | `_pemfvet` mDNS kaydı bir daha yapılmıyor | 2 | 4 yedek keşif kanalı var |
| 9 | Launcher STM portunu `auto` geçirmiyor → bobin 1-5 ölü | 3 | ana dağıtım kanalı |
| 10 | Başarısız self-update launcher'ı kilitliyor (taze cihazda kaçış YOK) | 3 | latent; bir yayın hatasıyla tetiklenir |
| 11 | Hasta UUID zinciri HER içe aktarımda kopuyor | 3 | sessiz KVKK anonimleştirme boşluğu |
| 12 | AI mikroserviste modalite + sessizlik kapıları atlanıyor | 3 | yalnız opsiyonel Docker profili |
| 13 | `home.zip` URL'si boş etikete taşınıyor | 3 | latent; yeni kurulum + "Onar" 404 |
| 14 | Inno installer build'i varsayılan yolda çöküyor | 3 | betik kendi kaynağını siliyor |
| 15 | `make_manifest.py` bozuk zip'in sha'sını mühürleyip 0 dönüyor | 3 | yalnız sert-kill sonrası |
| 16 | Migration rollback'inde WAL temizliği ölü kod (`Path + str`) | 3 | bileşik arıza; veri kurtarılabilir |
| 17 | "Ort. Sıcaklık" KPI'ı ölçüm yapmayan 5 bobinle seyreltiliyor | 4 | kilitli dürüstlük değişmezinin ihlali |
| 18 | Türkçe `İ`/`I` aramada geçmiş boş + boş PDF/CSV | 4 | 3 ekran |
| 19-31 | 13 adet ciddiyet-5 bulgu | 5 | aşağıda |

**13 şüpheli çürütüldü** (ayrı başlıkta), **5 kapsam dışı**, **5 doğrulanamadı**, **6 kasıtlı-teyit-ister**.

---

## KESİN BULGULAR

### [1] `duration=0` gözetimsiz-sürüş kapağı ESP bobinlerine (6-8) HİÇ uygulanmıyor — kısmi düzeltme

**Yer:**
- `servers/api_server.py:1417` (`/api/coil/{id}/control`, ESP dalı) ve
  `servers/api_server.py:1487` (`/api/coil/batch`, ESP dalı) → `"duration": payload.duration` HAM geçer
- Kıyas STM dalı: `servers/api_server.py:1395` → `controllers/hardware_controller.py:186`
  (`_dl_min = dur_min if dur_min > 0 else GOZETIMSIZ_VARSAYILAN_DAKIKA`, satır 32'de **120 dk**)
- `servers/api_server.py:989` → `CoilControlPayload.duration: int = Field(default=0, ge=0)` (0 GEÇERLİ)
- Arayüz tarafı: `pf/src/components/domain/CoilParameterPanel.tsx:86,96` ·
  `pf/src/services/therapyLimits.ts:17` (`duration: { min: 0, max: 120 } // 0 = süresiz`)
- Kapsam boşluğu: `tests/test_gozetimsiz_enerjilendirme.py` yalnız **bobin 1** (STM) üzerinden yazılmış

**Tetikleyici:** Kontrol Paneli → *WiFi ESP Bobinler (6–8)* bölümünde bir bobinin süre kutusuna
`0` yazıp **Başlat**. (Ya da doğrudan `POST /api/coil/6/control {"start":true,"freq":50,"duty":25,"duration":0}`
— 422 dönmez, `test_sifir_sure_hala_KABUL_edilir_karsit_kanit` bunu bilerek kilitler.)

**Sonuç:** ESP bobinine `{"command":"start", ..., "duration":0}` yayınlanır ve **sunucu tarafında
hiçbir son-tarih/watchdog kurulmaz.** STM'de aynı girdi 120 dk'da kesilir (yazılım deadline +
firmware timer). Seans açılmadığı için `_session_duration_watchdog` de kapsam dışıdır;
`_esp_telemetry_watchdog` (`api_server.py:481`) yalnız **telemetri susarsa** devreye girer —
sağlıklı yayın yapan bir ESP bobini kapaksız kalır.

**Nasıl doğruladım:** Kod okundu (yukarıdaki satırlar); `GOZETIMSIZ_VARSAYILAN_DAKIKA`
kullanım yerlerinin **tamamı** tarandı → yalnız `controllers/hardware_controller.py` (bobin 1-5).
`pf` tarafında çağrı zinciri `CoilParameterPanel.sendCommand` → `duration: durMin*60` olarak
izlendi; `clampTherapyParams` alt sınırı 0'dır ve `0 = süresiz` diye belgelenmiştir.

**Neden bu bir bug (yorum-iddiası deseni):** `CoilParameterPanel.tsx:84-86` operatöre
*"Süre girilmedi — bobin **donanım üst-sınırına** kadar çalışır"* diyor; kod yorumu da
*"donanım watchdog'u DURATION_MAX'a kaplar (kontrolsüz kalmaz)"* iddia ediyor. `DURATION_MAX_MINUTES`
(9999 dk ≈ 6,9 gün) **STM32 protokol sabitidir** (`utils/stm32_protocol_limits.py`, firmware
paritesiyle kilitli) — ESP ile ilgisi yoktur. Yani operatöre verilen güvence, ESP yolunda
dayanağı bu depoda **olmayan** bir iddiadır (`firmware/README.md:13`: *"ESP firmware'i
(`CoilController.cpp`) bu repoda değil"*).

**`0 = süresiz` bu projenin KENDİ protokol sözleşmesidir — tahmin değil:**
- `firmware/main.c:195` → `uint32_t dur_min; /**< Süre (dakika): 0 = süresiz */`
- `controllers/hardware_controller.py:62` → `# duration=0 → sinirsiz (degismedi)`

Yani `{"duration": 0}` yayınlamak, sistemin kendi sözleşmesinde **"sınırsız çalış"** demektir. STM
yolu bu nöbetçiyi bilinçli olarak 120 dakikaya çeviriyor; ESP yolu onu **olduğu gibi** iletiyor.

**Sınırım (dürüstçe):** ESP firmware'i (`CoilController.cpp`) bu depoda **yok**
(`firmware/README.md:13`), dolayısıyla o tarafta ikinci bir kapak olup olmadığını kodla
doğrulayamadım. Kanıtladığım şey: (a) 1.9.14'te **bilinçli olarak eklenen klinik kapak 8 bobinin
5'ini kapsıyor**, (b) sistemin kendi sözleşmesine göre iletilen değer "sınırsız" demek,
(c) operatöre gösterilen güvence metni ESP için dayanaksız, (d) hiçbir test 6-8'e uğramıyor.
CHANGELOG'un kendi kaydettiği desen: *"Kısmi düzeltme, düzeltilmemiş demektir."*

**Ağırlaştırıcı (ayrı bir bulgu DEĞİL, bilinen/belgeli):** `firmware/README.md:124` bobin 6-8
için termal kesmenin *"yalnız arayüz eşiği"* olduğunu yazıyor. Aşırı-ısınma interlock'u
`CoilParameterPanel.tsx:118-129`'da, yani **ekran açık kaldığı sürece** vardır. Operatör
sekmeyi/uygulamayı kapatırsa süresiz çalışan bir ESP bobininin ne süre ne termal kapağı kalır.

**Karşı-argüman:** ESP firmware'i kendi içinde bir üst sınır taşıyor olabilir; o zaman etki
"kapak yanlış yerde" düzeyine iner. Buna karşı: aynı gerekçe STM için de geçerliydi
(firmware timer'ı vardı) ve yine de yazılım kapağı **bilinçli** eklendi — çünkü 9999 dk'lık
protokol tavanı klinik bir sınır değildi.

---

### [3] Launcher ile kurulan kliniklerde STM portu oto-algılaması KAPALI kalıyor (bobin 1-5 sessizce ölü)

**Yer:**
- `launcher/core/src/install.rs:486-540` (`backend_env_with`) → geçirilen değişken kümesinde
  `PEMF_STM_PORT` **YOK**
- `utils/stm32_transport.py:156-180` → değişken boşsa `configured = FIXED_STM32_PORT`
  (`utils/stm32_transport.py:25` → **`COM10`**); oto-algılama **yalnız** `PEMF_STM_PORT=auto` ile açılır
- Kıyas servis yolu: `deploy/device.env:16` → `PEMF_STM_PORT=auto` (üstündeki satır 13-15 uyarısıyla:
  *"boş bırakılırsa kod oto-algılama YAPMAZ → sabit COM10'a düşer (yanlış port riski)"*)
- `headless_core.py:273` → `Stm32SerialTransport(self.logger)`; `settings` parametresi hiç geçilmiyor
  ve `utils/stm32_transport.py:92`'de saklanıp **hiç okunmuyor** → port için tek kaynak env değişkeni

**Tetikleyici:** Kullanıcı siteden **PEMF Vet Client**'ı indirip kurar (BUILD.md §3: *"ANA dağıtım"*).
Klinik PC'sinde ST-Link VCP, Windows'un USB numaralandırmasına göre COM10 dışında bir numara alır
(COM3/COM4/COM5… — hangi sürücünün önce kurulduğuna ve başka ne takılı olduğuna bağlı).

**Sonuç:** Backend COM10'u açmaya çalışır, açamaz → `_mark_bad` + 3 sn cooldown → sonsuza dek
COM10'u dener. **STM bobinleri 1-5 hiç bağlanmaz.** ESP bobinleri 6-8 MQTT'den çalışmaya devam
eder → cihaz *"çalışıyor gibi görünür"*, arayüz STM'yi `Bekleniyor ⏳` gösterir ve 1-5 panelleri
devre dışı kalır (`pf/src/components/domain/CoilParameterPanel.tsx:138`). Operatörün
yapabileceği bir şey yoktur: bu ayar ne arayüzde ne launcher'da açığa çıkarılmıştır
(`servers/settings_router.py` yalnız MQTT alanlarını yönetir).

**Nasıl doğruladım:**
- `backend_env_with` gövdesi satır satır okundu; küme: `MODELS_DIR, API_PORT, REQUIRE_AUTH,
  ENCRYPT_AT_REST, ENABLE_TUNNEL, DATA_DIR?, BACKUP_DIR?, LAUNCHER_VERSION, BASE_SHA?, HEALTH_NONCE`.
- `servers/api_server.py:137-139` bu boşluğun **bilinen** olduğunu doğruluyor: *"backend .env
  dosyalarini OTOMATIK YUKLEMEZ (load_dotenv yok) → env yalniz NSSM servis kaydinda uygulanir.
  Tauri launcher … exe'yi DOGRUDAN spawn edip yalniz 2 env verdiginden…"* Yani `device.env` launcher
  yolunda **hiç okunmaz**; CORS için çözüm backend varsayılanını değiştirmek olmuştu, STM portu için
  böyle bir düzeltme yapılmadı.
- `grep -rn "PEMF_STM_PORT"` tüm depo: yalnız `.env.example`, `deploy/device.env`,
  `deploy/README.md`, `docs/RUNBOOK.md`, `utils/*`, `tools/*` — **launcher kaynağında hiç geçmiyor.**
- COM10'u sabitleyen bir kurulum adımı yok: `lattekurulum/` ve `scripts/` içinde COM ataması arandı,
  bulunamadı.

**Neden mevcut kapı bunu yakalamıyor:** `launcher/core/src/install.rs:1237`
(`backend_env_kumesi_bilincli_kalir`) kümeyi kilitler ama **değişiklik-tespiti** yapar, eksiklik
tespiti yapmaz — bir değişken *eklenirse* kırılır, *eksikse* sessiz kalır. Testin kendi yorumları
bu sınıfın iki kez yaşandığını yazıyor (`ENV_ENCRYPT_AT_REST` 2026-08-08, `ENV_ENABLE_TUNNEL`
2026-08-12). Bu **üçüncüsü**.

**Karşı-argüman:** Geliştirme/tezgâh makinesinde ST-Link gerçekten COM10 olabilir (sabitin
kaynağı da bu) — o zaman sahibin makinesinde çalışır ve arıza yalnız *başka* makinelerde çıkar.
CHANGELOG'a göre henüz saha kurulumu yok (*"Sahada henüz kurulum olmadığı için…"*), yani bu
arızanın bugüne dek fark edilmemiş olması tutarlıdır. Ayrıca arayüz STM'nin bağlı olmadığını
dürüstçe gösteriyor → veri/doz yanlışlığı DEĞİL, kullanılamazlık.

---
### [1] Seans sürerken indirilen APK'nın kurulumu iptal edilmiyor → seansın ortasında telefon kumandası kayboluyor

**Yer:** `pf/src/hooks/useApkGuncelleme.ts:35-74` (`guncelle` düz async closure; iptal yok) ·
`pf/src/components/domain/MobileUpdateBanner.tsx:43` (`seansAktif` → `return null`) ·
`pf/src/components/domain/MobileUpdateGate.tsx:116-124` (kapı `durum==="acik"` iken de **mount kalır**)

**Tetikleyici:** Android, ön planda. Operatör bantta (ya da açılış kapısında) "Güncelle"ye basar →
128 MB dakikalarca iner → bu sırada seans başlar (telefondan ya da klinik PC'sinden; bant
`snapshot`tan okuduğu için ikisi de sayar) → bant `return null` eder. İndirme bitince
`kurulumuBaslat` çalışır ve Android paket yükleyicisi **seans izleme ekranının üstüne** tam ekran açılır.

**Sonuç:** Operatör onaylarsa uygulama öldürülür ve yeniden kurulur; bobinler **durmaz** (backend'de
istemci-canlılığı tabanlı durdurma yok — `servers/api_server.py:894-901` WS kopmasını yalnız yayın
listesinden siler; `HWKeepAlive` sürer). Telefon kumandası ~1-2 dk (kurulum + açılış + her açılışta
sorulan profil seçimi) kaybolur.

**Nasıl doğruladım:** Düşen test yazıldı ve gerçekten düştü (`kurulumuBaslat` beklenen 0, gerçek 1;
`apkIndir` GERÇEK koştu). Ayrıca: uygulama **tek rotalı** (`pf/app/` içinde yalnız `index.tsx` +
`_layout.tsx`), rota değişimi `PemfApp.tsx:59` state'i → bant hiç unmount olmuyor; olsa bile
closure iptal edilmiyor. `oran !== null` iken bandın X (kapat) düğmesi de kaldırılıyor
(`MobileUpdateBanner.tsx:59-72`) → "Güncelle"ye bir kez basıldıktan sonra kurulum niyetinin
açılması **kaçınılmaz**. Mevcut süit 71/71 geçiyor, yani bu davranış hiçbir testle kilitli değil.

**Neden bu bir bug (niyet kanıtı):** `MobileUpdateBanner.tsx:9-10` korumanın gerekçesini bizzat
yazıyor: *"kurulum uygulamayı yeniden başlatır ve bobinler hastanın üzerindeyken operatörün
ekranını elinden almak kabul edilemez."* Yani değişmez **teklifi gizlemek değil, kurulumun ekranı
almasını engellemek**. Aynı ilke başka yerde doğru uygulanmış: `PemfApp.tsx:101-103` (seans sürerken
hareketsizlik kilidi ERTELENİR). `git log -S"seansAktif"` → bilinçli bir "kurulum devam etsin"
kararı yok.

**Çürütme sonucu:** ÇÜRÜTÜLEMEDİ, ama abartı düzeltildi — **bobinler kontrolsüz kalmıyor**: klinik
PC'sinin yerel arayüzü ACİL DURDUR'u taşımaya devam eder (`api_server.py:3122-3131`, loopback'te
auth-muaf), süre-watchdog ve STM/ESP arıza-tetikli E-stop'lar çalışır. Kaybolan, **yedekli
kontrollerden biri**. Açılış kapısı yolu (`MobileUpdateGate`) aynı kök nedenin ikinci yüzeyi —
tek bulgu sayıldı; doğru düzeltme yeri `useApkGuncelleme` (kurulumdan önce "kurmak güvenli mi"
kapısı + iptal).

---

### [3→4] "Ort. Sıcaklık" KPI'ı, sıcaklık ölçmeyen 5 bobinle seyreltiliyor — kilitli "dürüstlük" değişmezinin ihlali

**Yer:** `pf/src/screens/KpiDashboardScreen.tsx:85-87` (bölen `connectedCoils.length`, `objectTemp>0`
süzgeci YOK), gösterim `:226`; aynı ekranın bobin tablosu `:258` de STM için `0.0` basıyor

**Tetikleyici:** STM çevrimiçi (bobin 1-5 `connected:true`, `objectTemp:0`) + en az bir ESP bobini
gerçek sıcaklık yayınlıyor. Raporlar ekranı açılır.

**Sonuç (ölçüldü):** 5 STM + 3 ESP@50 °C → **18,8 °C**. Üç bobin yanık eşiğine (48 °C) dayanmışken
kart "18,8 °C" diyor. Yalnız-STM kabinde → **0,0 °C**, yani hiç ölçüm yokken "serin" okunan bir sayı.

**Nasıl doğruladım:** Kod satır satır okundu, filtre yok. Premis iki uçtan doğrulandı:
`servers/live_state.py:171-182` bobin 1-5 için `connected=stm_online` yapar, `objectTemp`'e
dokunmaz (varsayılan `0.0`); backend yorumu *"STM bobinlerinde (1-5) sicaklik telemetrisi YOKTUR…
0.0-yerine-NULL yolu BILEREK secilmedi"* diyor. `avgTemp` deponun tamamında yalnız bu ekranda
geçiyor, hiçbir test kilitlemiyor. `git log -S"avgTemp"` → tek commit (ilk içe alma);
dürüstlük kararı SONRA geldi ve bu ekrana taşınmadı.

**Neden kasıtlı DEĞİL:** 2026-08-09 Tier-2 sahip kararı tersini emrediyor ve testle kilitli —
`pf/src/components/domain/CoilParameterPanel.tsx:154-168` + `CoilThermalHonesty.test.tsx` test #3:
*"ölçüm yokken SAHTE bir sıcaklık değeri gösterilmez — 0 °C 'serin' diye okunur."* KPI kartı tam
olarak yasaklanan şeyi yapıyor.

**Çürütme sonucu:** ÇÜRÜTÜLEMEDİ. Abartı düzeltildi: **gerçek termal koruma etkilenmiyor** —
interlock bobin BAŞINA çalışır (`CoilParameterPanel.tsx:119`), 50 °C'lik ESP bobini `>48` eşiğini
geçer ve durdurma komutu gider. Yani hasta güvenliği (1) değil, **yanıltıcı klinik gösterim**.
Aynı seyreltme `avgMag` ve `instantPowerW`'de de var; güvenlikle ilgili olan sıcaklıktır.

---

### [4] Türkçe `İ`/`I` ile arama kaydı bulamıyor → tedavi geçmişi "boş" görünüyor ve boş PDF/CSV üretiyor

**Yer:** `pf/src/screens/TreatmentHistoryScreen.tsx:153-157` (en ağır etki) ·
`pf/src/screens/PatientScreen.tsx:165` · `pf/src/components/domain/PatientGate.tsx:81` —
üçü de `toLowerCase()`; depoda `toLocaleLowerCase` hiç yok

**Tetikleyici:** Adı `İ` içeren (İpek, İnci) ya da büyük `I` içeren (Işık, Ilgaz) bir kayıt; hekim
doğal biçimde küçük harfle "ipek" ya da doğru Türkçe küçük harfle "ışık" yazıyor.

**Sonuç:** `TreatmentHistoryScreen` yüklü sayfaları boş gösterir → aramaya güvenen hekim
"bu hastanın geçmişi yok" sonucuna varır; PDF/CSV dışa aktarımı `filteredSessions` üzerinden
gittiği için (`:164`, `:194`) **boş/eksik rapor üretir**. `PatientScreen` "Aramayla eşleşen kayıt yok."

**Nasıl doğruladım:** `node -e` ile ölçüldü:
`"İpek".toLowerCase()` → `"i̇pek"` (5 kod noktası, `i` + U+0307) → `.includes("ipek")` **false**;
`'IŞIK'.toLowerCase()`=`"işik"` ≠ `'Işık'.toLowerCase()`=`"işık"` → false. Backend'de telafi YOK:
`servers/patient_router.py`'de arama ucu yok, istemci `/patients`'ın tamamını çekip yerelde süzüyor.
5 geçici testle davranış doğrulandı (büyük `İ` ile yazılınca EŞLEŞİYOR — iki taraf aynı bozulmayı
yaşıyor).

**Çürütme sonucu:** KISMEN ÇÜRÜTÜLDÜ. "Hasta ulaşılamaz" **yanlış**: `PatientGate` arama boşken tam
listeyi gösterip seçtiriyor (`PatientGate.test.tsx` bunu zaten kilitliyor), `PatientScreen` listesi
kaydırılabilir ve `owner` alanıyla da aranabilir. Ayakta kalan: **kırık arama kısayolu + eksik
rapor**. `localeCompare(...,"tr")` yalnız `AiHistoryScreen.tsx:223`'te sıralamada doğru
kullanılmış → ekip locale'i biliyor, aramaya taşımamış; bilinçli bir bırakma değil.

---

### [5] AI Hub'ın "Otonom Biofeedback"i onay kapısından beri YAPISAL olarak hiç çalışmıyor — toggle açık kalıyor, hata mesajı yanlış sebebi söylüyor

**Yer:** `pf/src/screens/AiHubScreen.tsx:1060` (gövdeyi **`{}`** ile gönderiyor) ↔
`servers/ai_router.py:1116-1136` (`/api/ai/pro/start` → `ai_approval.consume(payload.proposal_id)`);
`AiHubScreen.tsx:1344` (`autoAdjust` 428'den sonra sıfırlanmıyor) ve `:1085-1097` (watchdog poll'ü
`startedByUsRef` yalnız `.then()` içinde atandığı için **hiç kurulmuyor** — ölü koruma)

**Tetikleyici:** AI Hub → canlı kamera → "Otonom Biofeedback" düğmesi.

**Sonuç:** İstek **her zaman 428** döner (2026-08-06 sert onay kapısı `proposal_id` istiyor, ekran
göndermiyor) → otonom seans hiç başlamaz. Ekrandaki toggle **açık kalır** ve ekranın kendi toast'ı
yanlış sebebi söyler ("kamera/model erişilemedi" ← gerçek sebep: onay yok). Ayrıca aynı bloktaki
watchdog `setInterval` hiçbir zaman kurulmuyor (ref ataması re-render tetiklemez, dep dizisi
`[isLive, autoAdjust]` değişmez) → özellik bir gün çalışırsa koruma yine yok.

**Nasıl doğruladım:** `..\python.exe -m pytest -q tests/test_ai_pro_approval_gate.py` → **12 passed**
(`test_proposal_id_YOKKEN_start_428_doner` dahil). React hook desenini birebir taklit eden geçici
test: start başarılı olsa bile `pollSayaci` beklenen `>0`, gerçek **0**. `apiBaseUrl` zaten `…/api`
ile bitiyor (`config.ts:50`) → yol hatası değil.

**Çürütme sonucu:** Bu, çürütme turunun **orijinal şüpheliyi çürütürken bulduğu** kusur. Orijinal
iddia ("AI Hub'da otonom açılır, sekme değişimi onu durdurur") geçersizdi çünkü AI Hub otonom modu
hiç başlatamıyor. Ayakta kalan gerçek kusur: **ölü bir özellik + açık kalan toggle + yanlış hata
metni**. Sürüm kayması riski: onay kapısından ÖNCEKİ bir backend EXE'sine bağlanan yeni mobil
sürümde start başarılı olur ve kurulmayan watchdog gerçekten önemli hâle gelir.

---

### [5] Yazılmış gözlem notu, herhangi bir bobin `running` raporlayınca uyarısız siliniyor

**Yer:** `pf/src/components/domain/ObservationNotesModal.tsx:52-55` (reset effect'i **koşulsuz** ve
`visible`'ın **her iki** yönündeki değişimde ateşliyor) · `pf/src/screens/ControlScreen.tsx:669-673`
(bileşen koşulsuz render → `visible:false`'da unmount olmuyor) · `:391-393`
(`hardwareRunningOutOfSession = runningCount > 0`, seans state'inden **bağımsız**)

**Tetikleyici:** Seans bitti, modal açık, hekim gözlem notu yazıyor. **Dışsal** bir kaynak bir bobini
`running:true` raporluyor: (a) STOP'u kaçırmış bir ESP bobini kendi `duration`'ıyla sürüp yeniden
bağlanınca `status: running` yayınlıyor (`api_server.py:~495-520` bu senaryoyu birebir yazıyor),
(b) masaüstü istemci / ikinci hekim / uzaktan seans başlatıyor.

**Sonuç:** Modal gizlenir, yazılmış not + seçili tepki chip'leri **uyarısız silinir**, hiçbir yere
kaydedilmez. Donanım durunca modal doğru hasta adıyla ama **boş** açılır — hekim silindiğini fark
etmeyebilir.

**Nasıl doğruladım:** Gerçek bileşenle düşen test: not yazıldı → `visible:false` → `visible:true` →
`value` beklenen not, gerçek `""`; `apiPost` **hiç çağrılmamış** (taslak/AsyncStorage yolu yok).

**Çürütme sonucu:** ÇÜRÜTÜLEMEDİ, daraltıldı. Aynı cihazdan seans başlatmak mümkün değil (Modal
dokunuşları yakalıyor) → tetikleyici mutlaka dışsal, yani günlük akışta seyrek. Kayıp yalnız klinik
gözlem metni (yeniden yazılabilir), hasta güvenliği etkilenmiyor. Modal'ı gizlemek (ACİL DURDUR'un
üstünü kapatmamak) **kasıtlı ve doğru**; kusur, gizlenmede de sıfırlama yapılması — `#48` yorumunun
amacı (A hastasının notu B'ye bulaşmasın) yalnız açılış/hasta-değişimi geçişinde sıfırlamayı gerektirir.

---

### [5] AI Pro panelini yalnızca GÖRÜNTÜLEYEN ikinci istemci, sekmeden çıkınca süren otonom seansı durduruyor

**Yer:** `pf/src/components/domain/AiProPanel.tsx:99` (`setRunning(Boolean(st.active))` — sahiplik
sormuyor) · `:250-255` (unmount cleanup `runningRef.current` ile `/ai/pro/stop`) ·
`pf/src/screens/ControlScreen.tsx:650-655` (koşullu render → gerçek unmount)

**Tetikleyici:** İki istemci (klinik PC'sindeki web arayüzü + telefon, ya da iki veteriner). Biri
otonom seansı başlatmış. İkinci istemci Kontrol → "AI Pro" sekmesini **yalnızca açıp** sonra
"Manuel"e dokunuyor.

**Sonuç:** İkinci istemcinin paneli backend'in `active:true`'sunu benimsiyor ve unmount'ta
`POST /ai/pro/stop` gönderiyor → `servers/ai_router.py:1197-1225` koşulsuz
`_stop_session_coils(range(1,9))` → **7 bobin ve seans iptal edilir** (`start_ai_pro` bobin 1-7
sürüyor, 8 kapalı). Her iki operatöre de gerekçe gösterilmiyor.

**Nasıl doğruladım:** Gerçek bileşenle düşen test: backend `active:true` derken mount→unmount'ta
tam **1** adet `/ai/pro/stop` gitti (beklenen 0).

**Çürütme sonucu:** KISMEN ÇÜRÜTÜLDÜ. Aynı cihazda sekme değişiminde durdurmak **KASITLI**
(`AiProPanel.tsx:246-249`: "panel kapanınca backend bobinleri BAŞSIZ sürmeye devam ediyordu"). Bobin
sayısı 8 değil 7. "Operatöre hiçbir şey gitmez" abartı: başlatan istemcinin paneli 3 sn'lik poll'le
"AI Pro durdu." yazıyor. Bobinler enerjisiz kalıyor = **güvenli yön**. Ayakta kalan: çok-istemcili
klinikte tedavinin sebebi söylenmeden kesilmesi.

---

### [5] Supabase oturumu parçalı yazımı yıkıcı sırayla yapılıyor → veteriner tekrar giriş yapmak zorunda kalıyor (yalnız Android/iOS)

**Yer:** `pf/src/services/supabaseAuth.ts:55-64` (`_secSet`: `_secClearChunks` **önce siler**, parçalar
yazılır, meta **EN SON** güncellenir, `try/catch` YOK — kardeş `_secGet`/`_secRemove`'da var) + `:82-86`

**Tetikleyici:** Token tazelemesi (~saatlik) sırasında bir `SecureStore.setItemAsync` hatası (Keystore)
**veya** birkaç ms'lik pencerede OS'un süreci öldürmesi.

**Sonuç:** Meta artık var olmayan parçalara işaret eder → `_secGet` kalıcı olarak `null` döner →
veteriner **bir sonraki uygulama açılışında e-posta+şifre ile tekrar giriş yapmak zorunda**.

**Nasıl doğruladım:** Parçalı yolun **normal yol** olduğunu ÖLÇTÜM — uygulamanın tam 10
`user_metadata` alanıyla (`AuthScreen.tsx:128-139`) gerçekçi bir GoTrue oturumu kurup saydım:
`access_token` 1283 char + `user` JSON 1330 char → **tam oturum 2735 char → 2 parça**; profilsiz
oturum bile 2074 char → yine 2 parça. Yani 1800 sınırının altına **hiçbir durumda** inmiyor.
Geçici test (silindi) mekanizmayı kanıtladı: `key.1` yazımı patlatılınca meta `__chunks__:2`'de
kalıyor, `key.1` yok, `getItem` → `null`. `@supabase/auth-js` telafi etmiyor: `_saveSession`
(`GoTrueClient.js:4145-4180`) `setItemAsync` etrafında try/catch içermiyor ve alternatif token
kaynağı yok. `_secSet`/`_secGet` **hiç test edilmemiş**; `git log` → tek squash commit, tasarım notu yok.

**Çürütme sonucu:** ÇÜRÜTÜLEMEDİ ama ciddiyet **5'e** indirildi ve platform daraltıldı:
**yalnız native** (klinik makinesinin arayüzü web bundle'dır ve orada parçalama yok → tedaviyi yapan
operatörün konsolu etkilenmiyor). Tedavi ortasında kilitlenme YOK (bellekteki oturum temizlenmiyor,
`GlobalEmergencyStop` dahil çalışmaya devam ediyor). Cihaz eşleştirme token'ı **ayrı** anahtarda
(`pemf_api_token`) → yeniden giriş sonrası telefon tekrar eşleştirmeye gerek kalmadan bağlanır.
Sonuç = **bir yeniden giriş**, veri kaybı değil.

---

### [5] ACİL DURDUR'da gövde okuması zaman aşımının dışında (yalnız web)

**Yer:** `pf/src/services/emergencyStop.ts:56-60` — `clearTimeout` iç `finally`'de, `await
response.json()` (`:60`) artık `AbortController`'a bağlı değil. Doğru desen: `apiClient.ts:227-229`.

**Nasıl doğruladım:** Geçici test — `fetch` 200 başlık döndürüp `json()`'ı asılı bırakınca
`performEmergencyStop` **1500 ms içinde dönmedi** (1501 ms ölçüldü).

**Çürütme sonucu:** KISMEN ÇÜRÜTÜLDÜ — **hasta güvenliği DEĞİL.** (a) Tetikleyici pratikte
ulaşılamaz: `servers/api_server.py:3103-3110` ucu `await asyncio.to_thread(_emergency_stop_all,…)`
yapıp **sonra** dönüyor; ASGI'de başlıkların istemciye ulaşması `_emergency_stop_all`'ın çoktan
bittiğinin **kanıtıdır**. Gövde ~300 bayt, `Content-Length`'li, GZip middleware yok. Bağlantı
RST/FIN ile kırılsa `json()` **reject eder** → `catch` yedek yolları çalıştırır; süresiz askı için
sessiz blackhole gerekir. (b) Geri bildirim kaybolmuyor: `_emergency_stop_all` HTTP yanıtından ÖNCE
WS yayını yapıyor (`api_server.py:3050-3055`) ve istemci onu `LiveDataContext.tsx:349`'da işliyor.
(c) "Buton donar" **yanlış** — hiçbir acil-durdur butonu `stopping` ile devre dışı bırakılmıyor
(bilinçli: `GlobalEmergencyStop.tsx:40` "Çift-tık koruması YOK"). Ayakta kalan: **sağlamlık kusuru**,
2 satırlık düzeltme.

---

### [5] Manuel "⏹ Durdur" ağ kopukken ~40 sn sürüyor ve paralel tur yığılmasına izin veriyor

**Yer:** `pf/src/screens/ControlScreen.tsx:268-299` — 1+1+N ardışık, 8 sn zaman aşımlı POST
(ESP döngüsü `:287-292` **seri** `await`, `Promise.all` yok); buton `disabled={loading}` ve `loading`
yalnız `stopSession` süresince true (`useSessionControl.ts:237`/`259`)

**Çürütme sonucu:** KISMEN ÇÜRÜTÜLDÜ — en ağır iddia ("hiç geri bildirim yok") **olgusal olarak
yanlış**: `stopSession` t≈8 sn'de tam doğru talimatı içeren modal çıkarıyor
(*"Sunucuya ulaşılamadı — donanım HÂLÂ ÇALIŞIYOR olabilir. ACİL DURDUR'a basın ya da fiziksel güç
düğmesini kullanın."*) ve web'de `window.alert` JS thread'ini **bloklar**; ayrıca her 8 sn'lik zaman
aşımında toast, sonda ikinci bir uyarı, başlıkta sürekli "Çevrimdışı". Butonun erken açılması bir
durdurma kontrolü için **istenen yön** (sahip kararı: `GlobalEmergencyStop.tsx:40`,
`SessionProgressCard.tsx:139`). Ayakta kalan: **gecikme + gereksiz paralel tur** (her tur 5 zaman
aşımı daha). Bu bir acil yol değil — her zaman görünür, hiç devre dışı olmayan ACİL DURDUR var.
Ek düzeltme: aktif seans YOKSA `stopSession` hiç çağrılmaz (`:269`) → buton ~32 sn boyunca **hiç**
kilitlenmez.

---

### [5] `start_all_coils`'e "önce hesapla, sonra yaz" koruması taşınmamış → bobin 1 yarım güncellenip takılı gösterge bırakıyor

**Yer:** `controllers/hardware_controller.py:210-229` (`duty_percent_to_ratio(duty)` satır 222,
`is_running=True`+`freq` satır 220-221'den SONRA) ↔ kardeş `update_coil`'in P2 fix'i aynı dosyada
`144-169`. Uç: `servers/api_server.py:1276-1282` (`params: dict`, doğrulama yok)

**Tetikleyici:** Doğrudan `POST /api/hardware/command {"command":"start_all_coils","params":{"duty":<sayısal-olmayan>}}`.
`duty` tek skaler ve 5 bobinde paylaşıldığı için istisna **HER ZAMAN i=1'de** olur → bobin 2-5 her
zaman tamamen dokunulmamış kalır. (`utils/stm32_protocol_limits.py:45` — `float(percent)`
`clamp_float`'un `try`'ının DIŞINDA.)

**Sonuç:** Yalnız bobin 1'in `freq` alanı yazılır. Bobin 1 BOŞTA ise ek olarak `is_running=True` +
`duty=0.0` (manyetik olarak ölü) + `_coil_deadline=None` → **süresiz "çalışıyor" göstergesi** ve
2 Hz seri trafik. HTTP 500 döner.

**Nasıl doğruladım:** Ölçüldü — `update_coil(1, 90, "", ...)` → `False`, durum ve deadline
DEĞİŞMEDİ; `start_all_coils(freq=90, duty="")` → `ValueError` sızdı ve bobin 1 mutasyona uğradı.
`tests/test_hardware_controller_safety.py:153` `update_coil` dalını kilitliyor,
`start_all_coils` için eşdeğer test **YOK**.

**Çürütme sonucu:** KISMEN ÇÜRÜTÜLDÜ, ciddiyet **belirgin şekilde indirildi**:
- **"Sessizce" YANLIŞ** — karma durum canlı ekranda GÖRÜNÜR: STM32 sürdüğü parametreleri `STM_OK:`
  ile geri yayıyor (`headless_core.py:185-215` → `live_state.py:241-264` → WS `stm_coil_update`) ve
  arayüz bobin-başı Hz'i gösteriyor. Üstüne HTTP 500 açık hata.
- **"Kapaksız kalır" YANLIŞ** — `_coil_deadline` ataması satır **225**, patlayan satır **222**'den
  SONRA → eski deadline olduğu gibi kalır. Ölçüldü: kalan süre öncesi/sonrası **1800,0 s** (aynı).
  **Enerjilenme süresinde 0 ek dakika.**
- **UI'dan erişilemez:** tüm `.ts/.tsx/.rs/.kt` üzerinde `start_all_coils` → **0 eşleşme**.
- Frekansın Python tarafında clamp'lenmemesi sahip kararı; *başarılı* bir çağrı 5 bobini de 90 Hz'e
  alır ve tasarım gereği doğrudur.
Ayakta kalan: **durum-tutarlılığı kusuru + boşta bobin için takılı gösterge.**

---

### [5] Kod takası düşerken tünel adresi yine kalıcı yazılıyor (iki cihazlı klinikte)

**Yer:** `pf/src/services/pairing.ts:86-99` — `tokenOk=false` olsa da satır 92-96
`setStoredDeviceId` + `@pemf_server_address` yazımını yapıyor, fonksiyon `kod_reddedildi` dönüyor

**Tetikleyici:** İKİ cihazlı klinik. Telefon A cihazıyla LAN'da çalışıyor; kullanıcı B cihazının
kodunu giriyor; health + device_id geçiyor ama `exchangeCodeForToken` 429/404 ile düşüyor.

**Sonuç:** Adres B-tüneline yazılır. `preferLanIfReachable` B'nin `localIp`'sine ulaşamaz (başka LAN)
→ tünelde kalır, token yok → REST 401 / WS 1008. A cihazının LAN adresi diskten silinmiştir.
Kullanıcı Ayarlar'dan kodu tekrar girmeden düzelmez.

**Çürütme sonucu:** KISMEN ÇÜRÜTÜLDÜ, ciddiyet **5'e indirildi**. Tek cihazlı normal klinikte
**kendini onarıyor**: `pf/src/services/discovery.ts:278-301` `preferLanIfReachable` tam bu senaryo
için yazılmış ve `discoverBackend()`'in her turunda çalışıyor (açılış, ön-plana gelme, WS 1008).
Ölçüldü: diskte tünel adresi varken `discoverBackend()` → adres LAN'a döndü (**disk ezildi**) ve
`provisionToken` ile **token tazelendi**. "Çalışan LAN bağlantısı yok ediliyor" ve "401 fırtınası"
iddiaları çürütüldü — LAN WebSocket'i hiç yıkılmıyor.


---

### [1] Inno offline installer, bobinleri güvene almadan backend'i force-kill ediyor → ESP bobinleri 6-8 hastanın üzerinde enerjili kalıyor

**Yer:** `build_tools/PEMF_Backend_Setup.iss:215` (`taskkill /F /IM PEMF_Backend.exe`) **önce**,
`:216` (`sc.exe stop PemfBackend`) sonra. Doğru desen aynı depoda var:
`launcher/app/windows/hooks.nsi:68-76` (E-stop POST + ~1,8 sn bekleme, `taskkill`'den ÖNCE).

**Tetikleyici:** Kurulu bir `device`-modu cihazda **offline Inno installer elle yeniden çalıştırılır**
(belgelenmiş USB yükseltme yolu — `offline dağıtım/OKU-README.md:62-63`), o an bobin 6/7/8'de aktif
seans varken. Kullanıcı "Kur"a bastığı an `CurStepChanged(ssInstall)` tetiklenir.

**Sonuç:** `TerminateProcess` sinyalsizdir → `backend_service.py:710-723` sinyal işleyicisi koşmaz →
`_safe_stop_outputs` (`:162-222`) çalışmaz → ESP'lere MQTT STOP **hiç** yayınlanmaz. Bobin 1-5
firmware ölü-adam devresiyle ≤1500 ms'de düşer; **6-7-8 kalan seans süresince hastanın üzerinde
enerjili kalır** — varsayılan 20 dk, AI Pro yolunda üst sınır 120 dk (`servers/ai_router.py:465`).
ESP'de link-watchdog **yoktur** (`scripts/pemf_teardown.ps1:71-73`).

**Nasıl doğruladım:** `.iss` `[Code]` bloğunun tamamı (`:138-260`) okundu — `PrepareToInstall` yok,
`CloseApplications` direktifi tanımlı değil, kurulum yolunda hiçbir yerde E-stop yok. Yardımcıya
delege de etmiyor: `setup_services.ps1`'in kurulum dalı (`:273-277`) sırayı doğru kuruyor ama
`[Run]`'dan çağrıldığı için `.iss`'in taskkill'inden **dakikalar sonra** koşuyor → işlevsiz.
Kaldırma yolu doğru (`.iss:240-258` → `setup_services.ps1:94-110` graceful-önce), yani **asimetri
kasıtsız.**

**Neden mevcut kapı yakalamıyor:** Değişmezi kilitleyen test var ama **yalnız NSIS için**:
`tests/test_kaldirma_yetim_surec_temizligi.py:268-282` (`test_estop_taskkillden_once_gonderilir`)
sadece `hooks.nsi`'nin `NSIS_HOOK_PREUNINSTALL` gövdesini ayrıştırıyor. `.iss` hiçbir testte
davranışsal olarak denetlenmiyor.

**Çürütme sonucu:** ÇÜRÜTÜLEMEDİ, daraltıldı. (a) Otomatik/OTA varyant **zaten kapalı**
(`CHANGELOG.md:29`, `update_manager.py:67`, `tests/test_single_update_channel.py` kilitliyor) → "sessiz
OTA seans sırasında installer koşturur" senaryosu ölü; iddia **elle offline kuruluma** daralıyor.
Ama o kanal canlı: `offline dağıtım/` içinde gerçek derlenmiş artefaktlar var,
`build_installer.ps1:49` sürümü otomatik senkronluyor (bakımda) ve `.iss:214` yorumunun kendisi
kill'i *"(re-install)"* için gerekçelendiriyor. (b) Maruziyet **süresiz değil**, kalan seans süresi
kadar (`duration_minutes: Field(default=20, ge=1)`). (c) İkincil `AppExit Default Restart` iddiası
**çürütüldü**: `.iss:216`'daki `sc stop` 5 sn'lik bekleyen yeniden-başlatmayı iptal eder.
**Simetrik düzeltme:** `hooks.nsi:68-76`'daki üç satırın aynısı `.iss:215`'ten önce.

---

### [3] Başarısız client self-update, launcher'ı "Client güncelleniyor…" ekranında hapsediyor — kurulu OLMAYAN cihazda hiç kaçış yolu yok

**Yer:** `launcher/app/ui/index.html:1713-1732` (`trySelfUpdate` catch dalı yalnız
`stopPolling(); return false;` — **hiçbir `show()` yok**) · `:1875-1948` (`bootNetwork`'ün hiçbir
dalında telafi eden `show()` yok) · `launcher/app/src/main.rs:1304`
(`record_selfupdate_attempt` — sayaç)

**Tetikleyici (Windows):** manifest `launcher.version` > çalışan sürüm **ve** `installer_url`+`sha256`
dolu **ve** cihaz `launcher.rollout` diliminde (alan yoksa **varsayılan 100** — `manifest.rs:78`,
testle kilitli) **ve** `apply_self_update` reddediyor. Belirlenimci ret sebepleri:
(a) asset 404 — BUILD.md:349'daki *"`--clobber` kesme tuzağı"*nın tam karşılığı;
(b) manifest sha'sı yayınlanan exe ile uyuşmuyor;
(c) `detect_running_backend` bir süreç görüyor ama `/api/health` yanıt vermiyor → `session_active`
→ `None` → kapı **her açılışta** reddediyor (`main.rs:1221`, `backend.rs:178-208`).
**Ve** aynı turda yarım kurulum YOK + önbellekte hazır runtime güncellemesi YOK (= normal kararlı durum).

**Sonuç:** Pencere `s-install` ekranında, *"Yeni bir client sürümü bulundu — indirilip kuruluyor.
Uygulama otomatik yeniden başlayacak."* metniyle kalıyor. Başlat/Onar/Kaldır/Profil değiştir
**hepsi** erişilemez (hepsi gizli `s-ready` bölümünün içinde, `index.html:524-551`); header'da yalnız
dil/Web/Kılavuz/Hakkında/Çıkış var. Hiçbir hata/not gösterilmiyor.

**Nasıl doğruladım:** Gerçek `index.html` script'i sahte DOM + sahte Tauri ile Node'da 9 senaryoda
koşturuldu:
```
gorunen_ekran: ["s-install"]     inst_title: "Client güncelleniyor…"
btn_start_disabled: false, btn_start_kapi: null   <- kapı AÇIK ama düğme gizli bölümde
notice_gizli: true, error_gizli: true             <- hiçbir açıklama YOK
show_cagrilari: ["s-ready","s-install"]           <- geri dönüş YOK
```
Kontrol koşumu (`apply_self_update` **başarılı**) **aynı ekranı** verdi → başarı ve başarısızlık
kullanıcı için **ayırt edilemez**; ekrandaki "kuruluyor / yeniden başlayacak" yalan.
"İptal kaçış yolu" da çürük: `btn-cancel` handler'ı (`:1623`) yalnız `invoke("cancel_install")` yapıp
kendini disable ediyor — iptalden sonra ekran yine `s-install`.

**Neden "bilinçli karar" savunması geçmiyor:** `index.html:1717-1723` yorumu *"→ catch → normal boot"*
diyor, BUILD.md:230 *"Yoksa/başarısızsa normal açılış sürer"*, `main.rs:1189` *"güncelleme kullanıcıyı
ASLA bloklamaz"*. **Belgelenmiş niyet kodda karşılanmıyor.** Ayrıca 2026-08-04 denetiminin
(`install.rs:827`: *"UI o ekranda Duraklat/İptal'i GİZLEDİĞİ için kullanıcı döngüyü kıramıyordu"*)
eklediği kaçış yolu yarım kalmış: iptal `await`i kırıyor, ekranı geri getirmiyor.

**Sayaç bu hata sınıfını hiç kapsamıyor:** `record_selfupdate_attempt` yalnız
indirme+doğrulama+seans-kapısı geçtikten SONRA çağrılıyor (`main.rs:1304`, tek çağrı yeri) →
indirme/sha/seans hataları `selfupdate_auto_allowed`'ı hiç etkilemiyor (`install.rs:859-864`). Yani
BUILD.md:170'in *"korumalar: deneme sayacı + rollout"* ifadesindeki **sayaç boşta**; kalan tek fren
`--launcher-rollout 0`.

**İki DAHA KÖTÜ alt durum (çürütme turunun ayrıca bulduğu, ölçülmüş):**
- **Kurulu OLMAYAN cihazda kaçış yolu HİÇ YOK.** `already_installed:false` koşumu:
  `show_cagrilari: ["s-select","s-install"]`, ekran `s-install`'da kalıyor. `tryRuntimeUpdate`
  `!baseInstalled` ile hemen dönüyor, `pending_profiles` da boş → **yeni kullanıcı hiç kuramaz.**
  Tetikleyicisi belgeli: BUILD.md:257'deki `windowsTag` senkron uyarısı (site 1.9.29 verirken
  manifest 1.9.31 derse **her taze kurulum** self-update dener).
- **Süren seansta ekran YALAN söylüyor.** Seans aktifse kapı `Some(true)` ile reddeder
  (`main.rs:1221`) → veteriner **tedavi sırasında** *"Client güncelleniyor… Uygulama otomatik
  yeniden başlayacak"* okur. Kapının var olma sebebi tam bunun olmamasıdır.

**Çürütme sonucu:** ÇÜRÜTÜLEMEDİ, daraltıldı. Kaçış yolları tek tek test edildi: yarım kurulum var
→ kurtarıyor ✔; runtime güncellemesi **önbellekte** → kurtarıyor ✔; `--launcher-rollout 0` →
kilit hiç oluşmuyor ✔; çıkış/yeniden giriş → **kurtarmıyor** ✘ (`bootNetwork` aynı microtask'ta
kapıyı kapatıyor). "Kapatıp açmak kurtarmıyor" yalnız **belirlenimci** hata için doğru: geçici TCP
kopmasında `.part` korunuyor (`net.rs:331`) → sonraki açılış Range ile devam eder → o hâlde
ciddiyet 5. **Şu an sahada aktif değil** (canlı manifest 1.9.30, `installer_url` HTTP 200 ve
`Content-Length 2961856` = manifest `size`) → **latent**; bir yayın hatasıyla tetiklenir.

---

### [5] Takastan SONRA iptal/hata `guncellemeyi_geri_al` çağırmıyor → doğrulanmamış sürüm sağlık kapısı ATLANARAK canlıda kalıyor

**Yer:** `launcher/app/src/main.rs:805-810` (`Ok(Iptal)`/`Err` dalları `geri`yi **düşürüyor** — ne
`guncellemeyi_onayla` ne `guncellemeyi_geri_al`) ↔ ihlal edilen sözleşme
`launcher/core/src/flow.rs:538-539`: *"çağıran sağlık kapısından sonra ya `guncellemeyi_onayla` ya
`guncellemeyi_geri_al` çağırmak ZORUNDADIR"*. Sıralama: `atomik_takas` profil döngüsünden **ÖNCE**
(`flow.rs:989` katmanlı / `:1028` tek-parça), profil döngüsü `:1036-1046`.

**Tetikleyici:** Kurulu cihaz + `plan.cached=true` + planda **hem** katman **hem** en az bir profil
var + profil adımında iptal/duraklatma ya da IO hatası (kilitli model dosyası, AV karantinası).

**Sonuç (Rust tatbikatıyla ölçüldü):**
```
[SONUC] Err("açma iptal edildi")
[DISK]  runtime/VERSION = v2       <- CANLI ağaç YENİ sürüm
[DISK]  runtime.old var mi = true  <- ~1,5 GB diskte
[KAYIT] deps/app sha'ları BAYAT (v1)
[2. TUR PLAN] deps=true app=true profiles=["vet"] cached=true   <- TÜM İŞ TEKRAR
[3. TUR PLAN] needed=false ; runtime.old var mi = false          <- YAKINSIYOR
```
Ana hâl: her açılışta katman açımı + takas tekrarlanır (deps turunda ~10 dk, app turunda saniyeler),
**bir tur tamamlanana kadar**. İki daha ağır sonuç:
1. **Doğrulanmamış sürüm sağlık kapısı ATLANARAK canlıya alınıyor** — `runtime/` = v2 ama
   `start_backend` hiç koşmadı; UI `s-ready` diyor ve kullanıcı "Başlat"a basıyor.
2. **Geri dönüş hedefi TÜKETİLİYOR** — 2. turda `atomik_takas` önce `runtime.old`'u siler:
   `[1. tur sonrası] canli=v2 runtime.old=v1` → `[2. tur sonrası] canli=v2 runtime.old=v2`. Yani
   son-bilinen-çalışan v1 yok oluyor; `upgrade_drill.rs`'in *"v1 BİREBİR döner"* güvencesi bu
   senaryoda geçerli değil.

**Çürütme sonucu:** ÇÜRÜTÜLEMEDİ ama **teşhis yeniden çerçevelendi**: "kayıt yazılmıyor" bir hata
değil, **kasıtlı fail-safe** (BUILD.md:332-333, `flow.rs:643-646`;
`upgrade_drill.rs:279 geri_alinan_guncelleme_KAYIT_birakmaz` kilitliyor). Eksik olan **kayıt yazımı
değil, `guncellemeyi_geri_al` çağrısı**. Tasarımın varsayımı belli: katmanlı yolda indirmeler
takastan önce biter, yani Pause/Cancel normalde takas öncesi gelir — kimse aynı turda **profil
paketi** olabileceğini hesaplamamış; `upgrade_drill.rs:167` manifesti `"models": {}` kullandığı için
**bu dal hiçbir testte koşmuyor**. Abartılar düzeltildi: "her açılışta 1,4 GB" yalnız **deps
değiştiğinde**; "disk dolu" tetikleyicisi çürük (`disk_kapisi` takastan ÖNCE koşuyor, `flow.rs:948`);
belirlenimci sonsuz tekrar dar (önbellekte boyutu-doğru-içeriği-bozuk paket gerekiyor —
`paket_onbellekte_hazir` yalnız BOYUTA bakıyor, `flow.rs:113-116`). **Tuğlalaşma DEĞİL** (3. turda
yakınsıyor); koşullu 3 yalnızca yayın gerçekten bozuksa.

---

### [2] Enerjili bir bobinin frekansı ARTIRILDIĞINDA duty bayat kalıyor → ~1 s tek-polarite + istenen dozun 4,78×'ine kadar on-time

**Yer:** `firmware/main.c:1019-1022` (`tpp-1` klempi **yalnız** `if (period_reset)` kapsamında —
blok `:986`'da açılıp `:1023`'te kapanıyor) ↔ `main.c:870` (`g_tpp[i]` **anında** güncelleniyor,
`period_reset` beklemiyor) ↔ `main.c:1012-1013` (aşağı yön de slew'e tabi) + `:1005`
(`target<=0` bypass'ı hedef >0 olduğu için devreye girmiyor)

**Tetikleyici:** Enerjili bir STM bobinine (1-5) `f1 > f0` olan yeni bir parametre seti gönderilmesi.
Sevk edilen arayüzden **iki yol**: (1) `pf/src/components/domain/CoilParameterPanel.tsx:138` —
`isDisabled` koşulunda **`running` YOK**, yani çalışan bobinde Başlat butonu aktif; (2)
`servers/api_server.py:1767-1769` — `/api/session/start` çalışan bobinler için **hiçbir interlock
uygulamıyor**. 1 Hz'de çalışan bobinler (AI Pro sabit 1 Hz) + Manuel seans `masterFreq` varsayılan 100.

**Sonuç (iki ayrı etki, ikisi de ölçüldü):**
- **(a)** Bayat `g_duty_ticks >= yeni tpp` olduğu için `state = (adj < duty)` her tick'te 1 → IN_A
  sürekli HIGH: **≤1000 ms kesintisiz tek-polarite** (sevk edilen yolda `ref_ms` her pakette
  gönderildiği için worst-case 1 Hz→2 Hz'de tam 1000 ms; meşru 1 Hz %50 = 500 ms → **2×**).
- **(b)** İlk `period_reset`'te klemp duty'yi `tpp-1` (=**%99,8**) yapıyor, sonra aşağı-slew ile
  15-19 periyotta iniyor:
  ```
  1Hz%50 -> 100Hz%25 : duty izi 499,474,449,424...  oturma 150 ms
                       ilk 500 ms'de A-ON 184,7 ms (amaçlanan 125,0) = 1,48x
  1Hz%50 -> 100Hz%5  : oturma 190 ms
                       ilk 500 ms'de A-ON 119,6 ms (amaçlanan  25,0) = 4,78x
  karşılaştırma, TEMİZ başlangıç 100Hz%5: A-ON 24,5 ms, oturma 10 ms = doğru
  ```

**Nasıl doğruladım:** ISR sıfırdan iki kez bağımsız modellendi (pending-apply + tick/period_reset +
slew + max_d + faz + bipolar çıkış + `ref_ms` hizalama) ve sayılar yukarıda. Girinti/kapsam teyitli.
Yorumlarda bu duruma dair **hiçbir ⚠️ notu yok** — 2026-08-04 denetimi `g_tpp`/tick ayrışmasını
(`main.c:897-906`) düzeltirken `g_duty_ticks`'i gözden kaçırmış.
`tests/test_firmware_stop_latency.py` modeli `max_d` klempini **ve frekans değişimini** hiç
modellemiyor → dal sınanmamış.

**Çürütme sonucu:** ÇÜRÜTÜLEMEDİ ve **ilk bulanın iddiasından daha geniş** çıktı (etki (b) tamamen
kaçırılmıştı; (a)'nın süresi de 750 ms değil 1000 ms). Ciddiyet dürüstçe **2**: akım seviyesi
makinenin normal zarfını aşmıyor (tepe akım her hâlde V/R; 1 Hz %50'de bobin zaten saniyede 500 ms
tek yönde sürülüyor), shoot-through riski **yok** (sıkışma penceresinde A/B geçişi olmadığı için
dead-time konu dışı), tek atışlık ve kendini onarıyor. Ayakta kalan gerçek kusur: **hekimin girdiği
duty ~0,2 s boyunca sessizce ~4,8× aşılıyor** — klinik cihazda parametre-sadakati kusuru.
Tek satırlık düzeltme: klempi/yeniden-ölçeklemeyi `pending` bloğuna da koymak (`main.c:878` civarı).

---

### [3] AI mikroservis modunda modalite denetimi ve sessizlik kapısı TAMAMEN atlanıyor (opsiyonel Docker profili)

**Yer:** `servers/ai_router.py` — `delegate_infer` **kapıdan önce** dönüyor, ~8 uçta:
landmark `274/275`, segmentation `1394/1395`, thermal `1447/1448`, reticulocytes `1486/1487`,
sound `1935` vs sessizlik kapısı `2016`, kidney_ct `2070/2071`, histopath `2123/2124`,
cat_organ `2174/2175`. Kapılar: `ai_router.py:180-193` (`_decode_image` → `utils/image_domain.check`)
ve `:2011-2027` (`ses_sessiz_mi`). Mikroservis tarafı `ai_service/app.py` (730 satır) bunların
**hiçbirini** içermiyor; `docker/Dockerfile.ai` imaja yalnız `ai_hub/` + `ai_service/` kopyalıyor →
`utils/` imajda **hiç yok**.

**Tetikleyici:** `PEMF_AI_SERVICE_URL` tanımlı bir dağıtım (bugün **yalnız**
`docker/docker-compose.micro.yml:52`).

**Sonuç (deneysel — gerçek CT fixture'ı ile ölçüldü):**
```
[1) GÖMÜLÜ mod (PEMF_AI_SERVICE_URL YOK)]  ai_service_enabled=False
   HTTP 422 → "Bu modül boyalı patoloji preparatı (H&E) bekliyor..."   → KAPI ÇALIŞTI
[2) MİKROSERVİS mod]                        ai_service_enabled=True
   HTTP 200 {"top_1_class":"Grade 4","top_1_prob":1.0}                → KAPI ATLANDI
```
Kapının var olma sebebi olan saha vakası (`tests/test_image_domain_guard.py` başlığı: *"CT kesiti →
Grade 4 · güven %100"*) **birebir geri geldi**. Ses ucunda ayrıca `guvenilir`/`belirsizlik`/`rms_dbfs`
alanları hiç dönmüyor (yalnız `ai_router.py:2044-2046` üretiyor) → istemci "emin değil" bilgisini alamaz.

**Neden bu kural biliniyor:** `ai_hub/inference_petri_dish/plausibility.py:17-21` bizzat yazıyor:
*"denetim ROUTER'da DEĞİL burada durmalı, çünkü `PEMF_AI_SERVICE_URL` tanımlıyken
`servers/ai_router.py` HİÇ çalışmaz."* Petri kapısı bu kurala uyuyor; diğer iki kapı `utils/`te kaldı.
`grep -rln "ai_service_enabled|delegate_infer" tests/` → **0 dosya**.

**Çürütme sonucu:** ÇÜRÜTÜLEMEDİ, ciddiyet **3'e indirildi**: `PEMF_AI_SERVICE_URL` tüm depoda yalnız
`docker-compose.micro.yml`'de set ediliyor; `deploy/*.env`'de yok, `launcher/core/src/install.rs`
geçirmiyor, `ai_service/README.md` servisi *"opsiyoneldir"* diye tanımlıyor. **Sevk edilen
launcher-kurulumlu klinikte ETKİN DEĞİL** (gömülü mod — deneyle kanıtlandı). Kapsam ise ilk bulanın
söylediğinden **geniş**: 3 değil ~8 uç. Doğru düzeltme deponun kendi kuralı: kapıyı `ai_hub/`e taşı.

---

### [3] Yarım kalmış paketlemeden sonra `make_manifest.py` açılamayan arşivin sha'sını mühürleyip 0 ile çıkıyor

**Yer:** `scripts/make_manifest.py:396-421` (geniş `except Exception` → yalnız `[UYARI]`, `return 0`)
+ `build_tools/make_base_zip.py:196-217` (çıktı dosyasına doğrudan yazıyor; temp+rename yok)

**Tetikleyici:** `make_base_zip.py` **sert şekilde** öldürülür (elektrik/BSOD/kill — Ctrl-C DEĞİL),
sonra paketleyici tekrar koşturulmadan `make_manifest.py` + `gh release upload` yapılır.

**Sonuç:** Manifest, açılamayan bir arşivin sha256/size'ını mühürler ve EXIT=0 verir. Taze kurulum
açma aşamasında **açık hatayla** düşer, cihaz açılmaz (paket önbellekte olduğu için sha uyuşur →
yeniden indirme telafi etmez). **İlk bulanın adlandırmadığı daha ağır varyant:** kırpılan dosya
`base-app.zip` olursa (`make_base_zip.py:222`'de **ilk** yazılan dosya) zarar ölü `base` kanalında
değil **canlı `layers` kanalındadır**.

**Nasıl doğruladım:** İzole kopyada yeniden üretildi:
`[UYARI] paket icerik saglamasi yapilamadi: File is not a zip file` + `Yazıldı: manifest.json` +
`EXIT=0`.

**Çürütme sonucu:** KISMEN ÇÜRÜTÜLDÜ, ciddiyet **1'den 3'e** indi:
- **Gerçekçi kesinti bozuk zip BIRAKMIYOR.** `zipfile.ZipFile(out,"w")` context manager'ı `__exit__`'te
  merkezi dizini **yazar** → Ctrl-C/G-Ç hatası/disk dolması = **geçerli ama eksik** zip. Ölçüm: 6
  girdinin 4'ünde Ctrl-C → `testzip()` → `None` (zip geçerli) ve CRC kapısı **açıkça ve sayılarla**
  patladı: *"base.zip ile base-app+base-deps AYNI DEGIL: … 2 dosya yalniz katmanlarda"*. Genel yutma
  dalına yalnız sert-kill ile ulaşılıyor — o durumda operatör paketlemenin öldüğünü zaten bilir.
- **"Taze Windows kurulumları bozuk" YANLIŞ:** `base.zip`i yalnız ≤1.9.12 client'lar okur; taze
  kurulum güncel setup'ı indirip `layers` okur, eski client ise **önce kendini** günceller.
- **Mevcut cihazlar korunuyor:** bozuk arşivde monolith yolunda `flow.rs:412-425` `runtime/`i siler
  (kurulum ekranı + açık hata), katman yolunda `flow.rs:527-534` eski app katmanını `_app_yedek`ten
  **anında geri koyar**.
- Geniş `except` **kasıtlı ve taşıyıcı**: `tests/test_make_manifest.py` paketleri zip-olmayan bayt
  olarak yazıyor → dalı sert hataya çevirmek mevcut süiti kırar. `BUILD.md:351` yayıncıya zaten
  `gh release view --json assets` ile varlık+boyut doğrulamasını şart koşuyor.
- **Yan bulgu (hafif):** `make_base_zip.py:196-217` doğrudan çıktıya yazıyor → tek satırlık
  `tmp + os.replace` bu sınıfı tamamen kapatır.

---

### [3] `home.zip` paket klasöründe durduğu için bir sonraki manifest üretimi URL'sini boş etikete taşıyor (sessiz 404)

**Yer:** `scripts/make_manifest.py:139` + `:166-183` (ASSETS tablosu `:30-37`); disk durumu
`pemf-app-packages/home.zip` (318 390 934 B)

**Tetikleyici:** Bir sonraki app yayınında BUILD.md'yi harfiyen uygulayıp
`python scripts/make_manifest.py --dir pemf-app-packages --tag client-app-v1.9.16 …` koşmak.

**Sonuç:** `models.home` ve `profiles.home` URL'si `client-app-v1.9.11/home.zip` →
`client-app-v1.9.16/home.zip` olarak yeniden yazılır; o etikete `home.zip` yüklenmez → **404**.
**Ev Sahibi profilini seçen her YENİ kurulum ve her "Onar" hata ile düşer.** `vet.zip`/`research.zip`
yerelde olmadığı için taşınır (URL'leri korunur) → üç profilden **tam olarak biri** kırılır.
`net.rs:547,623` 404'ü deterministik sayıp tekrar denemez.

**Nasıl doğruladım:** İzole kopyada gerçek `manifest.json` + gerçek `home.zip` hardlink'i ile koşum:
```
+ home.zip -> models.home        <- normal başarı satırı, uyarı YOK      EXIT=0
diff: models.home.url ve profiles.home.url  v1.9.11 -> v1.9.16 ; sha256 DEĞİŞMEDİ (1e528202…)
```
Canlı yayın (salt HEAD): `client-app-v1.9.11/home.zip` → **200** (318 390 934 B, diskteki dosyayla
birebir); `client-app-v1.9.15/home.zip` → **404**; `client-app-v1.9.15/base-app.zip` → **200**
⇒ paket URL'leri her yayında gerçekten yeni etikete taşınıyor, sabit olan yalnız **manifest'in kendi
adresi** (`client-app-v1.8.0`).

**Neden hiçbir kapı görmüyor:** `sha256` **değişmediği** için `tests/test_manifest_consistency.py`,
`manifest.rs::depodaki_gercek_manifest_ayristirilir` ve URL-pin kontrolü hepsi yeşil kalır.
`--drop-missing` de işe yaramaz — dosya *var*.

**Çürütme sonucu:** ÇÜRÜTÜLEMEDİ, ama **latent** olarak işaretlendi: `git log -p
pemf-app-packages/manifest.json` → home URL'si **hiçbir commit'te değişmemiş**; v1.9.11→v1.9.15
etiket bumplarının hepsi `home.zip` diskte dururken yapıldı, yani **son 4 yayında betik bu klasöre
karşı hiç koşmadı** (manifest fiilen elle düzenleniyor — `tests/test_manifest_consistency.py:8-13`
bu pratiği kayda geçiriyor, oysa `BUILD.md:141` "elle düzenlemeyin" diyor). Kaza olmamasının sebebi
bir koruma değil, betiğin o klasöre yönlendirilmemiş olması. Mevcut kurulumlar etkilenmez
(`flow.rs::pending_updates` profil güncellemesini **sha** ile kararlaştırır, URL değişimi indirme
tetiklemez).

---

### [3] Inno installer build'i şu an varsayılan yolda ÇÖKÜYOR — betik kendi kaynağını siliyor

**Yer:** `build_tools/build_installer.ps1:251` (`$FrontendDir = Join-Path $ProjectRoot "pf"`) +
`:286-290` (`Remove-Item $FrontendDir\dist -Recurse -Force` → ardından `Copy-Item pf\dist → pf\dist`)

**Tetikleyici:** `.\build_tools\build_installer.ps1` (BUILD.md 3b, varsayılan mod).

**Sonuç:** `$FrontendDir` = `pf` olduğu için betik `pf\dist`'i **siliyor**, sonra aynı yoldan
kopyalamaya çalışıyor:
```
THROW: ItemNotFoundException :: Cannot find path '...\pf\dist'
ve pf\dist SİLİNMİŞ kaldı
```
`$ErrorActionPreference="Stop"` (`:12`) olduğu için **offline Inno installer varsayılan yolda hiç
derlenemiyor** (2026-08-15 tek-kaynak değişikliğinden beri); yalnız `PEMF_SKIP_FRONTEND=1` ile
derleniyor. Ayrıca `pf\dist` silindiği için sonraki backend build'i de etkilenir.

**Nasıl doğruladım:** İzole kopyada birebir yeniden üretildi (yukarıdaki çıktı).

**Çürütme sonucu:** Bu, "spec `pf\dist` okuyor, betikler `frontend\dist` doğruluyor" şüphelisini
çürütürken **çıkan** kusur. Orijinal şüpheli KISMEN ÇÜRÜTÜLDÜ: `build_installer.ps1:294-306`
gerçekten `pf\dist`'i doğruluyor (mesaj metni "frontend\dist" yazdığı için yanıltıcı ama yol doğru)
ve ana kanal **iki kapıyla** korunuyor (`make_base_zip.py:327-329` + `:351` → `sys.exit(1)`; sahada
`flow.rs:580 agac_yapisal_gecerli_mi` web'i olmayan ağacı reddedip eski sürüme dönüyor) → arayüzsüz
paket ne yayına çıkabilir ne kurulabilir. Bu yeni bulgu **gürültülü** (sessiz değil) ve yalnız build
zamanı, ama o kanal şu an kırık.

**Aynı turun iki hafif yan notu:** `scripts/build_backend_exe.ps1:74-76` yorumu ve `BUILD.md:75`
bayat ("Spec `frontend\dist`'i bundle'lar" — spec `:163` `pf/dist` okuyor); `build_mac.sh:136`
yanlış dizini doğruluyor ve mac tarafında web kapısı yok, ama `mac-arm64` sahip kararıyla manifest'ten
çıkarılmış → ölü kanal.

---

### [2] Açılışta LAN IP yoksa `_pemfvet` mDNS kaydı o süreç boyunca bir daha YAPILMIYOR

**Yer:** `servers/auto_discovery.py:98-105` (loopback ise `_mdns_service_info` **None kalıyor**, log
*"arayüz gelince kaydolacak"* diyor) · `:49-50` (`_reregister`: `if _mdns_service_info is None: return`)
· `:71-78` (`_get_local_ip` route-lookup başarısızsa `127.0.0.1`). Kardeşi doğru yapıyor:
`services/mdns_service.py:219-236` (`_reregister_mqtt` ServiceInfo'yu **sıfırdan** kuruyor,
None-guard'ı yok) → `_mqtt` toparlanıyor, `_pemfvet` toparlanmıyor.

**Tetikleyici:** Backend NSSM servisi olarak Windows açılışında, default route oluşmadan başlar.

**Sonuç:** `_pemfvet._tcp` o süreç ömrü boyunca **hiç** yayınlanmaz. Deneyle:
`_mdns_service_info=None` iken `_reregister()` → `get_shared_zeroconf` **hiç çağrılmadı**
("erken döndü, hiç denemedi"). Periyodik yeniden-deneme yok (`start_mdns` yalnız açılışta).
`tests/` altında `_pemfvet` yeniden-kayıt testi **yok**.

**Çürütme sonucu:** KISMEN ÇÜRÜTÜLDÜ, ciddiyet **4'ten 2'ye** indi. mDNS telefonun TEK yolu
**değil**: `pf/src/services/discovery.ts:315-358` **5 basamaklı** merdiven —
`1) mevcut origin · 2) kayıtlı adres · 3) mDNS · 4) Supabase remote · 5) SUBNET TARAMA`; dosyanın
kendi başlığı *"mDNS yoksa fallback"* diyor. Yani "telefon cihazı bulamaz, tek çare backend'i
yeniden başlatmak" **yanlış** — ilk bağlanma ~4 sn'den ~70 sn'ye çıkıyor. (`/api/discovery` beşinci
bir kanal değil: ona ulaşmak zaten adresi bilmeyi gerektiriyor.) Düzeltme tek satır: None-guard'ı
kaldırıp ServiceInfo'yu `_reregister_mqtt` gibi sıfırdan kurmak.

---

### [3] Migration rollback'inde WAL temizliği ölü kod (`Path + str` → TypeError)

**Yer:** `database/treatment_history_db.py:1284` (`_side = self.db_path + _sfx`; `self.db_path` bir
`Path` — satır 86, tek atama). Doğru kardeş desen: `database/auth_db.py:53`
(`Path(str(self.db_path) + _sfx)`).

**Tetikleyici (bileşik):** `current_version < TARGET_SCHEMA_VERSION` **VE** ön-yedek geçerli
oluşturuldu **VE** `_ensure_schema_version()` patladı **VE** aynı arıza kapanış-checkpoint'ini de
düşürüp `-wal`i geride bıraktı **VE** at-rest şifreleme açık (`deploy/device.env:48` → varsayılan).

**Sonuç:** Satır 1284 TypeError'a düşer, `try/except` yalnız uyarı basar, `-wal` silinmez → geri
yüklenen yedek + bayat WAL → sonraki açılışta `file is not a database` → karantina → cihaz **BOŞ
tedavi geçmişiyle** açılır.

**Nasıl doğruladım:** `Path + str` → `TypeError unsupported operand type(s) for +: 'WindowsPath' and
'str'` (ölçüldü). SQLCipher'da sonuç doğrulandı: `hmac check failed for pgno=1` →
`DatabaseError file is not a database` (sebep: geri yüklenen yedeğin page-1 salt'ı, WAL
çerçevelerinin şifrelendiği salt'tan farklı).
**Test kapsamı kâğıttan kaplan:** tek "koruma" `tests/test_treatment_persistence.py:339` →
`assert '"-wal"' in src and '"-shm"' in src` — bir **kaynak-metin grep'i**; TypeError'lı kod bunu
sorunsuz geçiyor. Davranışsal test (`tests/test_kalan_davranissal.py:173-228`) satır 1272'de `raise`
ile erken çıkıyor → 1284'e hiç varılmıyor.

**Çürütme sonucu:** KISMEN ÇÜRÜTÜLDÜ, ciddiyet **2 değil 3** ve olasılık **çok düşük**:
- Normal yolda bayat `-wal` **oluşmuyor** (ölçüldü: temiz kapanışta SQLite yan dosyaları kendisi
  siliyor) → bileşik arıza şart. Sahibin kendi yorumu (`:1277-1281`) bunu zaten söylüyor.
- Düz-metin profilde sonuç bozulma bile değil, **sessiz no-op** (WAL replay edilir, `integrity_check`
  "ok" der, yarım-migration hâli geri gelir).
- **Veri kurtarılabilir:** `shutil.copy2(backup_path, self.db_path)` yedeği **kopyalıyor**, taşımıyor →
  `migration_backups\pre_migration_v*.db` diskte kalıyor (son 5 tutuluyor); karantina dosyaları da
  silinmiyor ve `-wal/-shm` kaldırılınca dosya aynı anahtarla okunabildi (ölçüldü: `t sayi: (500,)`).
- Düzeltme tek satır; asıl kalıcı değer kaynak-grep testini satır 1284'ü gerçekten çalıştıran
  davranışsal bir testle değiştirmek.

---

### [5] Inno installer korumasız `ai_hub` sevk ediyor (aynı sürüm numarası, iki farklı yazılım)

**Yer:** `build_tools/build_installer.ps1:229-368` — `guii\dist`i temizleyip kendi PyInstaller'ını
koşuyor, `build_backend_exe.ps1:193-216`'daki kod-koruma adımını **hiç çalıştırmıyor**
(`grep compile_pyd|encrypt_sources|KORUMA` → 0 eşleşme) ve ISCC'yi `/DBuildOutput` vermeden
çağırdığı için `.iss:26` varsayılanı (`..\dist\PEMF_Backend`) düz kaynağı installer'a koyuyor.

**Diskte ölçüldü — ikisi de `VERSION=1.9.15`:**
```
dist/PEMF_Backend/_internal/ai_hub        -> 62 .py / 0 .pyd   (22:05)   <- Inno paketler
PEMF_BUILD/dist/PEMF_Backend/.../ai_hub   -> 49 .pyd / 13 .py  (22:24)   <- base.zip kaynağı
```

**Çürütme sonucu:** GERÇEK BUG — sahip kararı **değil**, tam olarak kapının engellemek için yazıldığı
regresyon: `make_base_zip.py:339-344` + `build_backend_exe.ps1:186-189` ilkeyi *"onefile da olsa
onedir de olsa **client de olsa** pyd olmalı… koruma prosedürel değil YAPISAL olur"* diye yazıyor ve
`.iss:9-12` kaynağın `PEMF_BUILD\dist` olması gerektiğini söylüyor. Ciddiyet 5 (BUILD.md §7 kaynak
korumasının tersine mühendisliği engellemediğini zaten açıkça yazıyor).

---

### [5] 1.9.30'un "Başlat" kapısı: etiket eziliyor, veteriner silik "Başlat"a basıyor

**Yer:** `launcher/app/ui/index.html:1271` (`applyLang`) ve `:1250` (`setRunningUi`, her `focus`ta
`syncRunningState` üzerinden) `t-start`'ı `dataset.kapi`'ye bakmadan eziyor.

**Ölçüldü:** `{"kapi_kapali":{"disabled":true,"etiket":"Güncelleme kontrol ediliyor…"}}` →
TR/EN'e basınca `{"disabled":true,"etiket":"Start"}`; **yalnız pencere odağıyla** da
`{"disabled":true,"etiket":"Başlat"}`. `.btn:disabled{opacity:.4}` → veteriner **silik "Başlat"**
görüyor ve sebebi ekranda hiçbir yerde yok — 1.9.30'un yazılma amacının yarısı geri geliyor.
`tests/test_baslat_kapisi.py` 13 test yeşil ama bu yolu hiç tutmuyor. Kalıcı kilit YOK (≤25 sn).

---

### [5] Duraklatılmış güncellemede "Devam Et" ekranı geri getirmiyor + her basış yeni indirme başlatıyor

**Yer:** `launcher/app/ui/index.html:1587` (`tryRuntimeUpdate` `plan.cached===false` dalında `show()`
çağırmadan `false` dönüyor) · `:1590` (`resumeOp = tryRuntimeUpdate`) · `recheckUpdates`'teki
`sonBildirim` guard'ı burada **yok**

**Ölçüldü:** ekran `s-install`/"Duraklatıldı"da kalıyor, `prefetch_cagrisi: 1 → 2 → 3`.
**Ulaşılabilirlik ilk bulanın dediğinden de dar:** `plan.cached` duraklamayı atlatır (`net.rs:502`
`.part`→`dest` takasını yalnız tamamlanınca yapar; bozuk `dest`i silen tek yol `flow.rs:174-177`
`is_retriable=false` ile HATA olarak çıkar). Kurulabilen tek gerçek yol: duraklatılmış ekran açıkken
**6 saatlik periyodik turun** `manifestRaw`'ı yeni bir sürümle değiştirmesi. Client kapat-aç kurtarır.

---

### [5] Kurulum iptali, o an inen arka plan güncellemesinin `.part`'ını siliyor

**Yer:** `launcher/core/src/install.rs:967` (`clear_partials` — cache'teki **TÜM** `*.part`) ·
`launcher/app/src/main.rs:1178-1184` · `index.html:1937`

**Sıra ölçüldü:** `app_window_open → … → check_runtime_update → prefetch_runtime_update →
discard_pending` — yani ön-indirme başladıktan **hemen sonra** "Kurulum yarım kaldı" sorusu çıkıyor;
"İptal et" tüm `.part`'ları siliyor. (Rust std Windows'ta `FILE_SHARE_DELETE` ile açtığı için silme
başarılı olur, sonraki `rename` düşer.) İnen ≤1,4 GB çöpe gider, sonraki turda sıfırdan iner.
Kendini onarır, veri bozulmaz. `main.rs:724-726` yalnız "aynı `.part`a iki yazıcı" riskini bilinçli
kabul ediyor; **yabancı `.part`ın silinmesi belgelenmiş değil.**

---

### GÖZDEN GEÇİRME TURU — kendi düzeltmelerimde bulduğum 6 kusur

Commit'ten önce 16 düzeltmenin tamamı tek tek yeniden okundu. **Altı kusur bulundu, altısı da
düzeltildi.** Hepsi benim eklediğim koddaydı; hiçbiri denetimin özgün bulgularından değil.

| # | Kusur | Neden ciddi | Düzeltme |
|---|---|---|---|
| A | İçe aktarma döngüsünde `_zaten_var` sayacı "zaten vardı" ile "GERÇEKTEN başarısız"ı **aynı kovaya** koyuyordu | Operatör "0 hasta [+50 zaten vardı]" görüp "sorun yok" diye okur; oysa 50 tıbbi kaydın hepsi kaybolmuş olabilir | Üç sayaç ayrıldı; ayrım hata METNİNDEN değil ÖNCE varlık sorgusundan türetiliyor; üç sonuç **API yanıtında** raporlanıyor (`patient_db`, `..._zaten_vardi`, `..._basarisiz`) |
| B | `make_manifest.py` içinde `rsplit("/", 2)[-2]` bozuk bir URL'de `IndexError` atardı | Yalnız bir günlük etiketi için manifest üretimini çökertir (yayın hattı durur) | `len(_parca) >= 2` koruması, aksi hâlde `"?"` |
| C | `_kapili_devret(name, label)` çağrılarında aynı dize **8 yerde iki kez** yazılıyordu | Bir harf yanlış yazılırsa uç YANLIŞ modalite kapısıyla gate'lenir — sessizce | `label` artık `name`'e düşüyor; çağrı yerleri tek argümanlı |
| D | `em_petri` ucu düzeltmeden SONRA da kapısız kalmıştı; yapısal testimin **8 satırlık sabit penceresi** onu kaçırdı | Yanlış-yeşil kapı, kapı olmamasından kötüdür (düzeltildi sanılır) | Uç dönüştürüldü; kapı artık devretme satırından **fonksiyon sonuna kadar** tarıyor |
| E | Başarısız self-update'te ekranı geri getirmek için `show("s-ready")` çağırmak **"Başlat" kapısını erken açıyordu** | 1.9.30'un düzeltilen semptomunu birebir geri getirir: veteriner ağ adımı bitmeden içeri girer | `startKapisiKapat()` ile yeniden kapatılıyor (idempotent olduğu doğrulandı; 25 sn zaman aşımı kalıcı kilidi engelliyor) + yeni mutasyon-doğrulamalı test |
| F | Yeni testin `PatientDatabase` **sınıf** yaması tam süitte hiç uygulanmıyordu (izole yeşil, süitte kırmızı) | Sessiz yanlış-yeşil: kusur geri gelse test yakalamazdı | Yama hedefi uç noktanın gerçekten okuduğu sembol: `api_server.get_patient_database`. Ölçülen sebep, modülün süit içinde iki ayrı isimle yüklenip **iki ayrı sınıf nesnesi** doğurması |

**⚠️ Yapısal kapılar beni ÜÇ KEZ kendi yorumlarımla kandırdı** (`.iss` sıra kapısı, WAL kapısı, AI
kapısı): kusuru açıklayan yorum/docstring düzeltme sanıldı. Her seferinde filtre sertleştirildi —
kapılar artık yalnız GERÇEKTEN YÜRÜTÜLEN satırlara bakıyor. Bu, "doğru deseni anlatan bir yorum
yazarak" kapı geçmeyi de imkânsız kılıyor.

**Gözden geçirmede bilerek DEĞİŞTİRİLMEYEN bir şey:** KPI'daki `avgMag` (ortalama manyetik alan)
hâlâ ölçüm yapmayan bobinlerle seyreltiliyor. Sıcaklıkta `objectTemp == 0` "sensör okumadı" demek,
ama `magneticMt == 0` **meşru biçimde "bobin kapalı"** olabilir; hangisinin kastedildiği koddan
türetilemedi. Sıcaklık düzeltmesini bu belirsizliğe genişletmek, doğrulanmamış bir varsayımı klinik
göstergeye yazmak olurdu.

**Satır sonları:** dokunduğum 5 dosyada (`\*.iss`, `build_installer.ps1`, `index.html`,
`make_manifest.py`, `sync_worker.py`) çalışma kopyası LF olmuştu; CRLF'e normalize edildi ve
`git diff --stat` birebir aynı kaldı (depo `core.autocrlf=true` ile zaten LF saklıyor, yani commit
içeriği iki hâlde de aynıydı). İlgili 6 test yeniden koşuldu: 24/24 ✓.

---

## İKİNCİ TUR — KALAN 17 KALEM KAPATILDI (2026-08-17)

İlk turda 16 bulgu düzeltilmişti; kalan **15 bulgu + fix-12'den sarkan 2 kalem** bu turda kapandı.
Yöntem aynı: her düzeltme için ayrı test, düzeltmeden ÖNCE kırmızı, sonra yeşil, ardından
**mutasyonla** doğrulama. Kalemler kapatılmadan önce HEPSİ `b86cb11`'in şu anki hâline karşı
YENİDEN DOĞRULANDI (9 salt-okunur analiz ajanı) — ilk turun 16 düzeltmesi bazı çapaları kaydırmış
olabilirdi ve gerçekten iki çapa kaymıştı.

| # | Kalem | Cid. | Dosya(lar) | Test | Mutasyon |
|---|---|---|---|---|---|
| 19 | `start_all_coils` atomik yazım yok | 5 | `controllers/hardware_controller.py` | `test_hardware_controller_safety.py` (+3) | 2/2 ✓ (ham kusur + "istisnayı yut" yalancı düzeltmesi) |
| C1 | Ses ucunda sessizlik kapısı devretmenin ARKASINDA | 3 | `servers/ai_router.py` | `test_ai_mikroservis_modalite_kapisi.py` (+4) | 1/1 ✓ |
| C2 | `:8100`e doğrudan çağrılar KAPISIZ | 3 | `ai_service/app.py`, `docker/Dockerfile.ai` | `test_ai_servis_8100_kapisi.py` (9, yeni) | 4/4 ✓ (COPY silme · kapı silme · **kapı KOPYALAMA** · sessizlik) |
| 8 | `_pemfvet` mDNS bir daha kaydolmuyor | 2 | `servers/auto_discovery.py` | `test_pemfvet_mdns_yeniden_kayit.py` (4, yeni) | 3/3 ✓ — üç yön AYRI testlerle |
| 15y | `make_base_zip` çıktıya doğrudan yazıyor | 3 | `build_tools/make_base_zip.py` | `test_make_base_zip_single_truth.py` (+2) | 3/3 ✓ |
| 29 | "Başlat" kapısı kapalıyken etiket eziliyor | 5 | `launcher/app/ui/index.html` | `test_baslat_kapisi_etiket.py` (7, yeni) | 4/4 ✓ |
| 31 | "Devam Et" ekranı geri getirmiyor + her basış yeni indirme | 5 | `launcher/app/ui/index.html` | `test_devam_et_duraklatilmis_guncelleme.py` (5, yeni) | 3/3 ✓ |
| 30 | Inno installer KORUMASIZ `ai_hub` sevk ediyor | 5 | `build_installer.ps1`, `PEMF_Backend_Setup.iss` | `test_installer_korumali_ai_hub_sevk_eder.py` (9, yeni) | 7/7 ✓ |
| G1 | Takas sonrası iptalde `guncellemeyi_geri_al` çağrılmıyor | 5 | `launcher/core/src/flow.rs` | `upgrade_drill.rs` (+1) | 2/2 ✓ |
| G2 | Kurulum iptali YABANCI `.part` siliyor | 5 | `install.rs`, `flow.rs`, `main.rs`, `index.html` | `iptal_temizligi.rs` (3, yeni) | 2/2 ✓ |
| F1 | Supabase parçalı yazımı geçici hatada oturumu kaybettiriyor | 5 | `pf/src/services/supabaseAuth.ts` | `supabaseAuthStorage.test.ts` (5, yeni) | 2/2 ✓ (**reddedilen sıra-değiştirme çözümü de yakalanıyor**) |
| F2 | ACİL DURDUR'da gövde okuması zaman aşımının DIŞINDA | 5 | `pf/src/services/emergencyStop.ts` | `emergencyStop.test.ts` (+3) | 1/1 ✓ |
| F3 | Takas düşerken tünel adresi kalıcı yazılıyor | 5 | `pf/src/services/pairing.ts` | `pairing.test.ts` (+3) | 2/2 ✓ |
| 20 | Gözlem notu bobin `running` deyince siliniyor | 5 | `pf/.../ObservationNotesModal.tsx` | `gozlemNotuKorunmasi.test.tsx` (4, yeni) | 3/3 ✓ (**yorum-kandırması vektörü dahil**) |
| 25 | Manuel "Durdur" SERİ (~40 sn) + paralel tur yığılması | 5 | `pf/src/screens/ControlScreen.tsx` | `durdurmaTuruParalel.test.tsx` (5, yeni) | 5/5 ✓ |
| 21a | AI Hub otonom modu YAPISAL olarak hiç çalışmıyor | 5 | `pf/src/screens/AiHubScreen.tsx` | `aiHubOtonomOnayKapisi.test.tsx` (3, yeni) | 3/3 ✓ |
| 21b | AI Pro panelini GÖRÜNTÜLEYEN istemci başkasının seansını durduruyor | 5 | `servers/ai_router.py`, `pf/.../AiProPanel.tsx`, `pf/src/services/config.ts` | `AiProPanelSahiplik.test.tsx` (5, yeni) + `test_ai_pro_approval_gate.py` (+4) | 6/6 ✓ |

**Regresyon (son ölçüm):** backend `1187 passed, 1 failed` · `cargo test` **246 passed, 0 hata** ·
`pf` **491 passed** (49 süit), `tsc --noEmit` temiz. Düşen tek test hâlâ süren 2.3.17 yayınının
disiplin testi (`test_KRITIK_site_APK_surumu_versions_json_ile_AYNI`) — bu değişikliklerle ilgisiz.

### Analizin RAPORU DÜZELTTİĞİ yerler (dürüstlük kaydı)

1. **Bulgu 8 için önerdiğim tek-satırlık düzeltme YETERSİZDİ.** İki senaryo var: (S1) açılışta hiç
   adres yok → arayüz gelince `ensure_interfaces_current` callback'i çağırır, guard düzeltilince
   toparlanır; (S2) adres VAR ama default route YOK (offline klinik / hotspot-only) → `_get_local_ip`
   UDP `connect`'e dayandığı için kalıcı `127.0.0.1` döner ve arayüz KÜMESİ değişmediği için callback
   HİÇ çağrılmaz. Guard'ı düzeltmek S2'de hiçbir şeyi düzeltmezdi. Ayrıca guard'ı **tamamen silmek**
   bir REGRESYON olurdu: `stop_mdns` callback'i listeden silmiyor, yani kasıtlı olarak kaldırılmış
   servis diriltilirdi. Düzeltme iki parçalı oldu ve süit iki hatalı yönü **birbirinden ayırt ediyor**.
2. **Bulgu 19'da raporum bir çağrı yerini atlamış.** "UI'dan erişilemez, 0 eşleşme" ifadesi
   `.ts/.tsx/.rs/.kt` için doğru ama `servers/ai_router.py:450` UI'dan (`auto_adjust` form alanı)
   erişilebilen bir Python çağrı yeri. Bug'lı dal oradan tetiklenemiyor (duty her zaman float) →
   ciddiyet 5 duruyor; düzeltmenin uç yerine KONTROLCÜ seviyesinde olmasının bağımsız gerekçesi bu.
3. **Bulgu 19'un "kapaksız kalır YANLIŞ" çürütmem yarım doğruydu.** ÇALIŞAN bobin için doğru
   (deadline değişmiyor), ama BOŞTA bobin için yanlış: `_coil_deadline[1] is None` + `is_running=True`
   ölçüldü ve `_tick`'in `is not None` koşulu yüzünden o bobin ASLA süre-aşımına düşmüyor.
4. **C1 için yazdığım gerekçe YANLIŞTI.** "Ses hattını yeniden kurgulamak gerekiyor ve bu ortamda
   ffmpeg davranışı doğrulanamıyor" demiştim; ikisi de yanlış çıktı. Blok zaten doğru sıradaydı
   (oku → ffmpeg → RMS), tek yapılacak devretme satırını kapının ALTINA indirmekti; ffmpeg de
   `imageio_ffmpeg` üzerinden bu makinede VAR (PATH'te değil). Ölçüldü: ffmpeg 27-31 ms, RMS 2-9 ms.
5. **C2'de kapıları `ai_hub/`e TAŞIMA önerim reddedildi** — `pyproject.toml` coverage
   `omit */ai_hub/*` + mypy `exclude` yüzünden iki güvenlik kapısı KALICI KÖR NOKTAYA girerdi
   (2026-08-09 ratchet kararının tersi). Yerine `utils/` imaja alındı ve kapı **nesne kimliği**
   testiyle kopyalanamaz hâle getirildi.
6. **İki çapa bayatlamıştı** (ilk turun commit'i yüzünden): `clear_partials` `install.rs:967` →
   `1006`; `discard_pending` çağrısı `index.html:1937` → `1975`. Bulguları geçersiz kılmıyor.

### Bu turda KENDİ düzeltmelerimde/testlerimde bulduğum 6 kusur

| Kusur | Nasıl yakalandı | Düzeltme |
|---|---|---|
| Yapısal AI kapımda **iç içe `def`** fonksiyon sonu sanılıyordu → pencere erken kapanıyor, mutasyon SESSİZCE geçiyordu | Bağımsız karşıt-kanıt testi | Sınır artık MODÜL DÜZEYİNDE aranıyor (`lstrip` yok) |
| `:8100` sessizlik reddinde RMS `-inf` **JSON'a yazılamıyor** → 422 yerine jenerik 500, kullanıcı sebebi göremiyor | Yeni testim ilk koşuda | `math.isfinite` koruması İKİ transporta da |
| `make_base_zip` testimdeki "geçici dosya tarayıcıya görünmez" kilidi **BOŞTU** (`finally` dosyayı her hâlde siliyor) | Mutasyon geçti | AST ile adlandırma ifadesi bulunup GERÇEKTEN değerlendiriliyor |
| İlk `start_all_coils` mutasyonum **etkisizdi** (ön-hesaplama bloğu istisnayı zaten yakalıyordu) | Mutasyon kırmızıya dönmedi | Mutasyon `git show HEAD:` ile özgün fonksiyondan alındı |
| E2 paralellik mutasyonum **yanlış şeyi** değiştiriyordu (düzeltme promise'leri istekli oluşturuyor) | Mutasyon geçti | Gerçek kusur biçimi (istek döngü İÇİNDE oluşturulup beklenir) uygulandı → 3 test kırmızı |
| E2'de guard'ın **ref mi state mi** olduğunu test ayırt edemiyordu | `ref → state` mutasyonu geçti | İki basışı TEK `act` içine alan yeni test eklendi |

Ayrıca bir **kaçış dizisi taşıma hatası** yaşandı: `build_installer.ps1`e yazdığım
`"scripts\build_backend_exe.ps1"` yolundaki `\b` **backspace karakterine** dönüştü (aynı şekilde
`_internal\ai_hub`'daki `\a` → BEL). Testler anında yakaladı; açık bayt değerleriyle onarıldı.

### KAPSAM DIŞI bırakılanlar (bilerek, gerekçeli)

- `scripts/make_manifest.py`'deki geniş `except` **DOKUNULMADI**: kasıtlı ve taşıyıcı
  (`test_make_manifest.py` paketleri zip-olmayan bayt olarak yazıyor) + betiğin kendi yorumu
  "acil çıkış paketlerin yeniden üretilmesini bekleyemez" diyor. Kapanan şey YAN bulguydu (atomiklik).
- `services/mdns_service.py`'deki `_mqtt` yayıncısının AYNI kör noktası: offline klinikte `_pemfvet`
  toparlanır, `pemf-gateway.local` HÂLÂ yayınlanmaz. İkinci dosya = daha büyük yama → **ayrı kalem**.
- `build_tools/make_model_zip.py` aynı atomiklik kusurunu taşıyor ve `PEMF_PKG_OUT` yönlendirmesi
  YOK (gerçek `pemf-app-packages/home.zip` üzerine yazar) → test etmesi riskli, **ayrı kalem**.
- `:8100`deki `disease`/`kidney_disease` uçlarının ASGARİ GİRDİ kapısı yok (router'da var) →
  **ayrı kalem**; bu turun konusu modalite/sessizlik kapılarıydı.
- Üretilmiş installer `.exe`'yi açıp içindeki `ai_hub`'ı doğrulayan uçtan-uca test YOK (3,7 GB +
  DiskSpanning). Kapı, ISCC'ye VERİLEN dizini ve o dizinin korumalılığını ölçüyor.
- `tests/test_kalan_regression_gaps.py`'deki iki kapı `inspect.getsource` + metin araması yapıyor →
  yorum içindeki bir örnek desenle yanlış-yeşil olabilirler. **Ayrı test-kalitesi bulgusu.**
- `AiHubScreen`'deki otonom akış ÇALIŞTIRILMADI, KALDIRILDI. Analiz daha derin bir kilit buldu:
  `propose` de TAVUK-YUMURTA kilidinde (öneri üretmek için taze lokalizasyon şart, cache'i yazan
  yol ise ancak `/start` başarılı olunca çalışıyor). Otonom AI Pro'nun AI Hub'dan başlatılabilir
  hâle getirilmesi bir ÜRÜN kararıdır, bug düzeltmesi değil.

---

## KAPSAM DIŞI — bulgu saymadım (triyajın elediği)

Bunlar gerçek gözlemler ama **kırık davranış değil**; tamlık için buradalar.

- **`launcher/app/ui/index.html:988`** — kurulum/onarım başlatmak arka plan indirmesinin yüzde
  göstergesini o oturumda öldürüyor (`clearNotice` → `stopPrefetchPoll`, geri başlatan yol yok).
  İndirme kesilmiyor ve bitişte kullanıcı yine bilgilendiriliyor (*"Yeni sürüm indirildi — güncelleme
  bir sonraki açılışta kurulacak."*) → yalnız gösterge kaybı.
- **manifest `mobile` bloğu vs `versions.json`** (23 ↔ 24) — arıza değil, **süren 2.3.17 yayınının
  yarısı**: `CHANGELOG.md`/`versions.json` commit'siz, CHANGELOG'da sha `SHA_BURAYA`, HEAD hâlâ
  "surum: mobil 2.3.16 yayini". Manifest yayınlanmış 2.3.16'yı doğru gösteriyor ve
  `make_manifest.py:53-57` `mobile`ı bilinçli `CARRY_ONLY` ilan ediyor. Site kapısı zaten kırmızı
  (`test_version_visibility.py::test_KRITIK_site_APK_surumu_versions_json_ile_AYNI` FAILED =
  disiplin testi işini yapıyor).
- **`BUILD.md:223/241/292/309`** — sürümsüz `PEMFVetClient-Setup.exe` / `PEMF_Vet_Mobil.apk`
  yükleme komutları. Olgular doğrulandı (`guii\PEMFVetClient-Setup.exe` 2026-08-08 / 2 926 195 B
  bayat; gerçek 1.9.30 setup'ı `build_tools\Output\...-1.9.30.exe` = 2 961 856 B = manifest
  `launcher.size`; `config.ts:87,112` adları sürümden türetiyor ve `downloadNames.test.ts` kilitliyor)
  → takip edilirse site butonu + self-update 404 olur. Kırık olan **doküman**, çalışan bir kod yolu değil.
- **`.github/workflows/linux-backend.yml:51`** ham `npx expo export` → `postexport-web.js` yamacı
  atlanıyor. Yamanın TAMAMI kozmetik (`lang="tr"`, `description` meta, `<link rel="icon">`) ve
  `manifest.json`'da yalnız `win-x64` var → linux çıktısı hiçbir kullanıcıya gitmiyor.
- **`build_tools/build_installer.ps1:543`** bayat installer adını rapor ediyor (ölçüldü:
  `PEMFBackendSetup_device_v1.9.14.exe`). `$SetupExe` başka hiçbir yerde kullanılmıyor, 15 satır
  sonra doğru ad basılıyor → tek yanıltıcı log satırı.

---

## ÇÜRÜTÜLDÜ — rapor edilmiyor (çürütme turunun elediği şüpheliler)

Bunlar makul görünen ama **ölçümle yanlış çıkan** iddialardı. Bu bölüm, ikinci turun ne iş yaptığını
göstermek için duruyor.

**Açık süre verildiğinde kapak "protokol tavanına" (6,94 gün) düşüyor** —
`controllers/hardware_controller.py:193-197`. İddia: düzeltme yalnız `else` dalına uygulanmış,
`duration_seconds>0` dalı aynı kusuru taşıyor. **Ölçüm iki dalın BİREBİR AYNI sayıyı ürettiğini
gösterdi** (`duration=1e9` → her iki dal 599 940 s), çünkü `normalize_duration_minutes`
(`utils/stm32_protocol_limits.py:73`) `dur_min`'i zaten 9999'a clamp'liyor. Dal asimetrisi yok;
`git show 51e7257` düzeltmenin bilinçli olarak yalnız "süre VERİLMEDEN" durumunu kapsadığını yazıyor.
Ayrıca sevk edilen arayüz süreyi 0-120 dk'ya clamp'liyor (`pf/src/services/therapyLimits.ts:17`).

**AI Pro her karede `_coil_deadline`'ı ileri kaydırıp "tek gerçek süre sınırını" etkisiz kılıyor** —
`servers/ai_router.py:692-699`. İleri kayma gerçek (kare-1 `t0+7200,000`, kare-2 `t0+7200,062`) **ama
üstündeki iki kapak da ateşliyor — ölçüldü**: (1) kare-içi kapak `ai_router.py:1327` → 120 dk'da
`session_active=False`, bobin **hiç sürülmüyor**; (2) `_session_duration_watchdog` → gerçek STOP
(`_stop_session_coils` çağrıldı, bobin 1-7, tepki 0,00 s); (3) `start_mono` kare akışıyla
tazelenemiyor (`cont=True` dalı onu KORUYOR — 50 ms arayla iki çağrıda fark 0,0000). Watchdog her
zaman `_coil_deadline`'dan **daha erken** ateşler. Kalan iş yalnız **bayat yorum**:
`controllers/hardware_controller.py:58-62` `/api/ai/ai_pro/frame`'i "seans-DIŞI" sayıyor, oysa
`ai_router.py:1176-1181` AI Pro seansını tam da watchdog kapsasın diye `_active_session`'a yazıyor.

**Mobil güncellemede kurulum niyetinin iki kez açılması** — `pf/src/services/mobileUpdate.ts:210-242`.
JS'te tekilleştirme gerçekten yok (`kurulumuBaslat` 2 kez çağrılıyor, düşen testle kanıtlandı), ama
iki niyet **birebir aynı** ve `FLAG_ACTIVITY_MULTIPLE_TASK` **verilmiyor**
(`pf/modules/apk-installer/.../ApkInstallerModule.kt:83-87`) → `FLAG_ACTIVITY_NEW_TASK` görev
yeniden kullanır, sahada en olası sonuç **tek yükleyici ekranı**. En kötü hâlde aynı APK için ikinci
bir onay penceresi; kurulum idempotent, hasta güvenliği boyutu yok.

**Tam inmiş paketin "Şimdilik devam et" ile erişilemez olması** — `MobileUpdateGate.tsx:120`
(`oran === null` yanlış yordam; doğrusu `kurulumAcildi`). Niyet/kod uyuşmazlığı gerçek ama zarar
önemsiz: kullanıcı ertelemeyi kendi istedi, aynı ekranda **"Kurulumu tekrar aç"** düğmesi duruyor
(`:180`), erteleme yalnız bellekte (`mobileUpdate.test.ts:424` bunu kilitliyor) ve hazır-dosya hızlı
yolu (`mobileUpdate.ts:280-284`, iki testle kilitli) **tek bayt bile yeniden indirmiyor**.
Toparlanma = bir yeniden açılış + tek dokunuş.

**Tünel watchdog'u 4xx/5xx'te yanlış "ölü" diyor** — `servers/tunnel_manager.py:361-374`. Ölü kod
gerçek (yerel `http.server` ile ölçüldü: 400/403/404/500/502/530 hepsi `HTTPError` → `except` →
`False`; `200 <= code < 500` dalı 4xx için erişilemez). **Ama tetikleyici hiçbir yerde yok:**
`PEMF_ALLOWED_HOSTS` varsayılanı `"*"` ve `if _allowed_hosts != ["*"]` olduğu için
TrustedHostMiddleware **hiç eklenmiyor**; `grep` `.env`/`.rs`/`.yml`/`.ps1`/`.md` → **0 isabet**.
Diğer 4xx kaynakları da kapalı: `/api/health` auth-muaf (`servers/auth.py:33`) ve rate-limit'ten
açıkça muaf (`api_server.py:371`). Kalan tek gerçekçi durum Cloudflare 5xx ve orada `return False`
**zaten istenen davranış**. Zarar iddiası da fazla: yeni URL alınınca `_url_callbacks`
(`tunnel_manager.py:199-200`) Supabase'e anında yeniden yayınlıyor. → **kozmetik ölü kod**, bug değil.

**`rollback()` `_applying_since`'i set etmiyor → kalıcı "güncelleme sürüyor" kilidi** —
`servers/update_manager.py:648-650`. Kod asimetrisi gerçek (ölçüldü: `_applying_since=None` iken
+30000 sn sonra bile `is_update_in_progress()` `True`). **Ama dört ayrı gerekçeyle bugün ölü kod:**
(1) eski kanal varsayılan KAPALI ve `rollback()` bayrağa dokunmadan `:625-626`'da dönüyor —
`PEMF_LEGACY_EXE_UPDATE` hiçbir `.env`/launcher profilinde yok; (2) kanal elle açılsa bile
`previousStable` hiç dolmuyor (`docs/RUNBOOK.md:74-75`, `tests/test_runbook_accuracy.py` kilitliyor)
→ dala ulaşılamıyor; (3) `_applying_since is None` → `True` kalması **KASITLI ve testle kilitli**
(`tests/test_update_rollback.py:259-265` "damgasız bayrak sessizce temizlenmemeli — geriye uyum";
37 test geçti); (4) bayrak yalnız BELLEKTE, süreç yeniden başlarsa kalkıyor. Ciddiyet 1/5.

**Master sync darbesi 10 kHz üstünde kalıcı HIGH** — `firmware/main.c:993-996`. Aritmetik doğru
(eşik tam `tpp = DDS_SYNC_PULSE_TICKS = 5` ⟺ `f > 10 000 Hz`; 200 000 tick modelinde f=10001 →
PB1 HIGH 199 997 / LOW 3). **Ama:** sevk edilen hiçbir yol >100 Hz üretemiyor
(`pf/src/services/therapyLimits.ts:13` clamp; `ai_router.py:467` sabit 1,0 Hz; backend'deki **her**
sayısal freq literali tarandı → 100 Hz üstü tek değer yok). İstek kendi içinde çelişkili:
`DDS_SYNC_PULSE_TICKS 5` = 100 µs, f>10 kHz'de periyot ≤100 µs → "her periyotta 100 µs darbe"
aritmetik olarak imkânsız. Klinik payda da yok: `tpp ≤ 4` → duty çözünürlüğü %25, tedavi dalga formu
sync darbesi konu olmadan **önce** anlamsız. `FREQ_MAX` kodun kendi ifadesiyle "Teknik DDS
maksimumu". → sertleştirme notu (payload'da freq üst sınırı), bug değil.

**Duty slew (inrush) sınırlayıcısı düşük frekansta etkisiz** — `firmware/main.c:882-886`. Aritmetik
doğru ve hatta daha geniş (sevk edilen %50 duty tavanında etkisiz bölge 5 Hz değil **10 Hz**; %25'te
20 Hz). **Ama kusur değil:** formül hedefine göre kusursuz (`tpp/slew = 0,2·f` periyot × `1/f` = tam
0,2 s, frekanstan bağımsız); dejenerasyon saf **kuantizasyon** — duty bir darbe genişliğidir ve
periyotta bir kez değişebilir, dolayısıyla bir periyottan kısa rampa zorunlu olarak tek adıma çöker.
Fizik daha güçlü çürütüyor: inrush *turn-on başına* bir olaydır; 1 Hz'de bobin **saniyede bir kez**
tam %0→%50 sert turn-on yapıyor (20 dk'lık AI Pro seansında ~1200 özdeş olay) — yalnız birincisini
yumuşatmak koruma sağlamaz. `firmware/README.md:18` da atfedilen iddiayı **yapmıyor** (yalnız
"duty slew-rate sınırlayıcı + `tpp-1` clamp" diyor). Fazla iddia yalnız kod yorumlarında
(`main.c:155-159`, `:1003`) → **yorum düzeltmesi**, davranış kusuru yok.

**`--no-monolith` base.zip'i silince acil geri çekme imkânsız hale geliyor** —
`build_tools/make_base_zip.py:232-236` + `scripts/make_manifest.py:366-385`. Mekanik doğrulandı
(izole kopyada `--launcher-rollout 0` → EXIT=1; `--drop-missing` → EXIT=1). **Ama sonuç yanlış:**
(1) betikle zaten yapılabiliyor — `--dir`'i yalnız `manifest.json` içeren bir klasöre çevirmek yeter,
koşum EXIT=0 verdi ve `"rollout": 0` yazılıp diğer bloklar bayt-bayt taşındı; (2) manifest pratikte
**elle** düzenleniyor ve tam bu bloklar — son üç yayın commit'i (`70eaefe`, `1e7f4ba`, `77dd85d`)
4-6 satırlık cerrahi elle düzenlemeler, `make_manifest.py` o yayınlarda hiç koşmamış ve
`BUILD.md:242-252` launcher bloğunu elle düzenlemeyi **yönerge olarak** veriyor; (3) tetikleyici hiç
var olmamış (`git log -S"no-monolith"` → yalnız bayrağı ekleyen commit); (4) `base.zip` şu an diskte
var (1 533 303 145 bayt); (5) `--rollout 0` tek yol değil — `--min-supported-version` sahadaki
kurulumları dilime bakmaksızın güncellemeye zorlar.

**`build_backend_exe.ps1` sürüm senkronunu hiç çağırmıyor → bayat `_internal/VERSION` yayınlanabilir** —
Boşluk **gerçek** ve doğrulandı: `sync_versions` yalnız `build_apk.ps1:33` ve `build_installer.ps1:104`'te;
7 workflow'da `sync_versions.ps1 -Check` koşmuyor; `tests/test_version_visibility.py`'de
`VERSION == versions.json.backend` assert'i **YOK** (`:48-53` depodaki `VERSION`'ı referans alıyor,
bayatlığı göremez) → **kapı yok**. **Ama üç gerekçeyle rapor edilmiyor:** (1) sonuç yönü
**FAIL-SAFE** — `flow.rs:795-799` `zorunlu = is_newer(min_supported_version, kurulu_surum())`; bayat
`VERSION` daha KÜÇÜK okunur → cihaz geri çağırmayı **fazladan** alır, asla atlamaz. "Cihaz güncelleme
almaz" senaryosu `VERSION`'ın **yukarı** bayatlamasını gerektirir, o da `versions.json`'u geri
düşürmeyi gerektirir. (2) Pratikte hiç ayrışmamış: `git log -- VERSION` → her backend bumpında
`VERSION` ve `versions.json` **AYNI commit'te** (`d884b93`, `21b03ec`, `e1efd8e`…). (3) Otorite dosya
kapsamını doğru yazıyor (`versions.json._comment` iki betiği isimle sayıyor); gevşek olan yalnız
`BUILD.md:11` ve `README.md:55` → **iki satırlık doküman imprecision**, kod-doküman çelişkisi değil.
Kapatmak isterseniz tek iş: `sync_versions.ps1 -Check`'i CI'a ya da betiğin başına koymak.

**GERİ ÇAĞIRMA uyarısı açılış yolunda gösterilmiyor** — `launcher/app/ui/index.html:1574` vs `:1075`.
Mekanizma doğrulandı (açılış yolu `rtBg`, periyodik tur `rtRecall` — Node koşumuyla ölçüldü). **Ama
sonuç çürük: geri çağırma açılış yolunda ZORLA UYGULANIYOR** — koşum `B_recall_cached`:
`show_cagrilari: [s-ready, s-install, s-ready]`, sonuç *"Uygulama güncellendi."*; `pending_updates`
(`flow.rs:795-801`) `zorunlu` iken rollout kapısını atlıyor. Yani günlük kapatıp açan makine geri
çağırmayı **alır**. Dahası `rtRecall` metni o dalda **YANLIŞ olurdu**: metin *"uygulamayı KAPATIP
AÇIN ki güncelleme kurulsun"* diyor, ama `cached=false` iken kapatıp açmak hiçbir şey kurmaz —
gösterilen `rtBg` (*"bir sonraki açılışta kurulacak"*) teknik olarak **doğru** metindir. Ayakta kalan
tek şey: indirme sürerken (1,19 GB, uzun) kullanıcı bunun bir **güvenlik** güncellemesi olduğunu
bilmiyor → yalnız aciliyet etiketi eksik. Ciddiyet 5 (bilgilendirme).

**Bulut PULL tamamlanmış seansı bayat "active" ile eziyor** — `servers/sync_worker.py:374-406`.
Mekanizma **doğrulandı** (sahte Supabase istemcisiyle: tur-2'de `('active', None, None, 1)` — PULL
tamamlanmış kaydı ezdi, kalıcı). **Ama sahada ulaşılamaz:** `PEMF_CLOUD_PATIENT_SYNC` dört bağımsız
yerde kapalı (kod varsayılanı `"0"`, `deploy/device.env`+`server.env`+`staging.env` hepsi `=0`,
`docker/Dockerfile.backend:49` `=0`) ve launcher hiç geçirmiyor;
`tests/test_kvkk_transfer_claims.py:65-68` varsayılanı kaynak düzeyinde **kilitliyor**. → **latent
mayın**: bayrağı açan biri tamamlanmış tedavi kayıtlarının bitiş/süre/durumunu kaybeder (o hâlde 4/5).
Hastalarda "düzeltilen ad geri döner" kısmı ayrıca çürük — `test_prod_readiness_fixes.py::
test_d1_cloud_pull_preserves_local_columns_and_search_index` yerel kolonları kilitliyor.

**Periyodik tur manifest'te GEÇERLİ model paketlerini önbellekten siliyor** —
`launcher/core/src/flow.rs:243-257` + `disk.rs:110-118`. Silme kümesinin "ölü paket" değil "bu
operasyonun ihtiyacı olmayan önbellek zip'i" olduğu doğru, **ama zararsız:** plandaki paketler
`korunacak` ile, `.part`'lar `disk.rs:128-131` ile korunuyor; kurulu bir paketin cache kopyası zaten
ölü ağırlık ve 1.9.29 CHANGELOG #3 bunu **özellik** olarak duyuruyor (gerçek eMMC disk-dolma
arızasını çözüyor). Prefetch→sonraki-açılış kurulumu aynı planı kullandığı için "yakında gerekecek
paket" hiç silinmiyor (`pending_updates` KURULU sha'ya bakar, önbelleğe değil). Kalan tek yanlışlık
`disk.rs:111` docstring'i → yorum.

**Kilit meşgulken atlanan ön-indirme "hata" olarak yazılıyor** — `index.html:1584/1081`. Sözleşme
bozulmuyor: sonuç `fail()` ile DEĞİL `notice()` ile gösteriliyor ve `#notice` CSS'i açıkça nötr
("Çevrimdışı bilgi kutusu — hata DEĞİL", `index.html:222-227`); kırmızı `#error` ayrı kutu.
`tests/test_guncelleme_kurulum_kilidi.py:78`'in kilitlediği şey "komut `Err` dönmesin ki UI KIRMIZI
HATA göstermesin" ve o yerinde. Metin de yanlış değil: *"tamamlanamadı — bir sonraki açılışta kaldığı
yerden denenecek"* atlanan turun gerçek sonucudur.

---

## ŞÜPHELİ — DOĞRULANAMADI

- **ESP firmware'inin `duration: 0` davranışı.** Bulgu [1]'in tek açık noktası. `CoilController.cpp`
  bu depoda yok (`firmware/README.md:13`). Kanıtladığım: sözleşme `0 = süresiz`
  (`firmware/main.c:195`, `controllers/hardware_controller.py:62`), STM yolu bunu 120 dk'ya çeviriyor,
  ESP yolu ham iletiyor, hiçbir test 6-8'e uğramıyor. **Eksik:** ESP tarafında ikinci bir kapak olup
  olmadığı. Cevabı yalnız ESP deposu ya da tezgâh ölçümü verir.
- **`apkKur`'un arka planda sessizce başarısız olması.** `ApkInstallerModule.kt:96-103`
  `startActivity` çağırıyor; Android 10+ arka plan aktivite başlatmayı **sessizce** engeller (istisna
  atmaz) → `kurulumuBaslat` "açıldı" der, hiçbir şey açılmaz. "İndirme ekran kilitliyken tamamlanır"
  tasarımı tam bu duruma denk geliyor. Kurtarma var ("Kurulumu tekrar aç"). **Cihazda ölçülmedi**,
  yalnız koddan ve Android davranışından çıkarım.
- **`paket_onbellekte_hazir` yalnız BOYUTA bakıyor** (`launcher/core/src/flow.rs:113-116`). İki
  sürümün bayt-bayt aynı boyutta olması hâlinde `plan.cached` yanlış `true` olur ve açılışta bloklayan
  yola girilir. Bulgu [5]'in (takas-sonrası iptal) belirlenimci tekrarı da tam buna bağlı.
  **Ölçülemedi** — böyle bir çakışma üretilemedi.
- **`servers/settings_router.py:27-32,52-62`** — `SettingsModel` tüm alanlara varsayılan verdiği ve
  `payload.dict()` daima 4 anahtar taşıdığı için yalnız `clinic_name` gönderen bir istemci MQTT broker
  ayarını sessizce `localhost:1883`'e döndürür. **Frontend'de bu POST'un çağrıldığı yer bulunamadı**
  → tetiklenebilirliği doğrulanmadı.
- **Keşif kanalları portu `8000` sabit yayınlıyor** (`sync_worker.py:449`, `api_server.py:818`,
  `system_router.py:321`) ama gerçek port dinamik (`launcher/core/src/flow.rs` `find_free_port`,
  `deploy/staging.env:22` = 8010). 8000 meşgulken telefon yanlış porta bağlanır. Supabase RPC'sinin
  `coalesce(p_api_port,8000)` sözleşmesi "8000 varsayılan" niyetini gösteriyor → **kasıtlı mı, boşluk
  mu ayırt edilemedi.**

---

## KASITLI GÖRÜNÜYOR — TEYİT İSTER

- **`session_coil_runs` (uygulanan DOZ kaydı) sensör saklama süresiyle siliniyor** —
  `database/treatment_history_db.py:1796-1798` `purge_old_coil_runs(sensor_retain_days)`;
  `services/headless_db_maintenance.py:160` varsayılan **90 gün**. Yorum `# P2 audit 2026-06-28` ile
  bağlamayı bilinçli eklemiş. Rahatsız edici yan: geri dönüşsüz PII maskeleme için operatör ONAYI
  zorunlu (`:1817-1826`) ama doz kaydı silmede ne onay ne `denetim_yaz` izi var, ayrı bir ayarı da yok.
- **Destek paketi yasak-ad listesi TAM AD eşliyor** — `utils/support_bundle.py:126-127`.
  `pemf_secrets.json` engelli ama `...json.<pid>.tmp` / `...json.corrupt.<zaman>` (secrets_manager'ın
  ürettiği **gerçek** adlar) değil; maske kalıpları `sqlcipher_key`/`patient_fernet_key`'i içermiyor.
  Bugünkü `PEMF_LOG_DIR` yapılandırmasında sır dosyası taranan dizinde olmadığı için doğrudan sızıntı
  değil — ama bulgu [2]'nin `.corrupt` dosyası tam bu adı taşıyor.
- **Yarım katman seti sessizce yazılıyor** — `scripts/make_manifest.py:225-241` yalnız `app` yerelde
  varken `deps`'i taşımıyor ve sonuç `layers.win-x64 = {app, rollout}` (deps YOK) oluyor; sessiz-kayıp
  kapısı (`:339-358`) platform anahtarı var olduğu için bunu görmüyor ve **hiçbir uyarı basılmıyor**.
  `tests/test_make_manifest.py:129-138` bu davranışı bilerek kilitliyor ("karışık set üretilmesin"),
  yani karar kasıtlı — ama sonucun "eksik katman seti" olduğu hiçbir yerde uyarılmıyor.
- **`CHANGELOG.md:18`** kapının `tests/test_changelog_gate.py` olduğunu söylüyor; o dosya **yok**,
  kapı fiilen `tests/test_version_visibility.py:143-200`'de yaşıyor ve çalışıyor. İşlevsel sorun
  değil, bayat referans.
- **20 baytlık paket sapması:** diskteki `base-deps.zip` (1 462 119 647) ve `base.zip`
  (1 533 303 145), yayınlanan 1.9.15 manifestinden (…667 / …165) 20 bayt küçük; `base-app.zip` ise
  sha'sına kadar birebir aynı. Sebebi commit `3b8ed1c` (paket belirlenimciliği) 1.9.15'ten SONRA
  girmiş olması — beklenen, tek seferlik. Bug değil, ama bir sonraki yayında deps sha'sı bir kez daha
  değişecek (1,4 GB'lık tek seferlik indirme).
- **`deviceRegistry.ts:110` `bayat` dalı ölü kod + yanlış yönlendiren mesaj.**
  `database/supabase_devices.sql:93`'teki RPC `last_seen > now() - interval '5 minutes'` ile
  **sunucuda** filtreliyor → bayat satır istemciye hiç gelmez. Cihaz 5 dk'dan uzun kapalıysa doğru kod
  `{durum:"yok"}` → `pairing.ts:61` *"…bulunamadı. **Kodu kontrol edin.**"* der; `agTanisi.ts:107-108`
  da `bilinmiyor` → rehber hiçbir teşhis göstermez. Mevcut test (`agTanisi.test.ts:81`) bu davranışı
  **kilitliyor**, yani bilinçli olabilir; doğru düzeltme yeri istemci değil SQL.

---

## HİÇ BAKILAMAYAN / TEMİZ ÇIKAN ALANLAR

**Aranıp bulunamayan (temiz görünen):** acil durdurma zincirinin çekirdeği (`_emergency_stop_all`
kapsamı — 2026-08-09'da düzeltilmiş ve kilitli, `stop_all_coils`'in fail-closed dönüşü,
`_force_send_left` STOP telafisi), seans süre-watchdog'unun monotonic saat kullanımı,
`_handle_stm_line`'ın firmware dizeleriyle eşleşmesi (`STM_ERR: Watchdog Timeout` doğru dala düşüyor),
`auth_middleware`'in `/api/v1` yeniden-yazım sırası, `_mqtt_publish` PUBACK doğrulaması, WS
geri-basınç ve ölü-soket temizliği, launcher'da E-stop→kill sırası, `backend.port`'un E-stop adresi
olarak korunması, kurulum kilidi, `runtime.new`/`runtime.old` yarım-takas kurtarması,
`.part`/Range/`Content-Range` doğrulaması, host-pin, disk kapısı, hasta verisinin kaldırmada
korunması, e-posta normalizasyonunda İ/ı katman uyuşmazlığı (yok).

**Hiç bakılamayan alanlar (dürüst kapsam beyanı):**
- **ESP32 firmware** (`CoilController.cpp`) — depoda yok. Bulgu [1]'in kapanmasını engelleyen tek şey.
- **iOS yolu** — EAS bulut build; bu makinede doğrulanamaz.
- **Supabase SQL/RLS politikaları** — `supabase/*.sql` yalnızca dosya olarak okundu; canlı projede
  RLS'in gerçekten uygulandığı doğrulanmadı.
- **`pemf-vet-web`** (pazarlama sitesi + iyzico ödeme) — beş katman ajanından hiçbiri ona atanmadı;
  yalnız `config.ts` sürüm/etiket alanları çapraz kontrol edildi.
- **`ai_hub` model doğruluğu** — altın-değer testleri var ama modellerin klinik geçerliliği bu
  denetimin konusu değil.
- **Gerçek donanım** — hiçbir bulgu tezgâhta ölçülmedi; firmware bulguları ISR modellemesi + aritmetik.
- **Docker/GPU profili** — yalnız bulgu [3] (AI kapıları) bağlamında incelendi.
