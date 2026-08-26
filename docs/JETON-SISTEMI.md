# Jeton (Token) Ücretlendirme Sistemi

**Sahip kararı 2026-08-20.** Planlar önce "işlem önceliği / kuyruk / gerçek zamanlı" ile
ayrılıyordu; yapay zekâ analizleri **klinik bilgisayarında** çalıştığı için "sunucuda sıra beklersiniz" çerçevesi ölçülebilir değildi. ⚠️ OLGU DÜZELTMESİ
(8. parti): "karşılığı hiç yoktu" demiştim — ölçünce YANLIŞ çıktı. Karşılığı VAR:
`servers/entitlement.py::ai_queue_gate` + `_ai_semaphore` gerçek bir eş-zamanlılık
sınırlayıcısıdır ve `ai_router`a bağlıdır. Ama (a) `PEMF_TIER_ENFORCED` varsayılan KAPALI
olduğu için bugün hiç çalışmıyor, (b) kliniğin KENDİ makinesindeki bir sınır — "sunucuda sıra"
değil. Yani vaat bugün doğru DEĞİL ve o çerçeveyle hiç doğru olmadı; kaldırılması yerinde.

Ücretlendirme artık ölçülebilir ve dürüstçe anlatılabilir bir birime bağlı:
**1 jeton = 1 yapay zekâ analizi**. Kuyruk mekanizması silinmedi — kapalı duruyor; yeniden
açılacaksa **önce açıkça anlatılmalı** (açıklanmamış bir yavaşlatma, kaldırılan vaatten kötüdür).
Kilit: `tests/test_tier_kullandikca_tanimi.py`.

## 1. Model

| | |
|---|---|
| **Aylık plan hakkı** | Her dönem yenilenir, **devretmez** (Başlangıç 50 · Pro 500 · Pro+ 2.000) |
| **Satın alınan jeton** | Ek paketle alınır, **süresi dolmaz** |
| **Tüketim sırası** | Önce aylık hak, sonra satın alınan → kullanıcı parasıyla aldığını kaybetmez |
| **Maliyetler** | görüntü/ses/sensör 1 · ağır araştırma (patoloji, RNA, tomografi, yara-kapanma/scratch) 3 · AI Pro otomatik seans 5 |
| **Ek paketler** | 100 → ₺249 · 500 → ₺990 · 2.000 → ₺3.490 (birim fiyat adet arttıkça düşer) |

Tek kaynak: `pemf-vet-web/src/config.ts::JETON` (web) ↔ `servers/jeton.py::MALIYET` (cihaz).
İkisinin **ayrışması test edilir** — kullanıcı sitede "1 jeton" okuyup cihazda 3 harcayamaz.

### 1.1 Kullandıkça Öde (ön ödemesiz üyelik)

Sahip isteği (2026-08-20): *"hiç önden satın almadan kullandıkça öde gibi bir üyelik olmalı."*

| | |
|---|---|
| **Aylık ücret** | Yok |
| **Önden jeton alımı** | Yok — kart tanımlanır, bakiye yüklenmez |
| **Ücret** | Jeton başına **₺2,90** (paketli/planlı jetondan pahalı — taahhütsüzlüğün karşılığı) |
| **Faturalama** | Harcanan jeton `kullandikca_borc` alanında birikir, **ay sonunda** toplu faturalanır |
| **Hiç kullanılmazsa** | Ücret **çıkmaz** |
| **Sürpriz fatura kapısı** | Faturalanmamış kullanım **300 jetona** ulaşınca yeni analiz durur (`BORC_TAVANI`) |
| **Başabaş** | Ayda ~340 analizden sonra Pro (₺990 / 500 jeton) daha ucuz — SSS'deki eşik **hesaplanarak** test edilir |

Akış farkı, iki yerde birden uygulanır ve **ikisi de mutasyonla doğrulandı**:

* **Cihaz** — `servers/jeton.py`: `odeme_modeli="kullandikca"` ise bakiye kapısı atlanır; önce
  `BORC_TAVANI` bakılır, sonra tüketim `tur="kullandikca"` ile gönderilir (M13/M14).
* **Veritabanı** — `jeton_tuket` RPC: `odeme_modeli='kullandikca'` dalı **yetersiz-bakiye
  kapısından ÖNCE** gelir; borcu artırır ve deftere yazar. Dalın silinmesi ya da sıraya
  kayması artık testle yakalanıyor (M17 ilk turda kaçtı, kapı sonradan eklendi).

⚠️ **Borç tavanı ticari bir sınırdır.** Aşılsa bile seans başlatma/durdurma, **acil durdurma**,
sensör okuma ve cihaz kontrolü serbesttir (M15 ile kanıtlandı). Tavan yalnız yeni **yapay zekâ
analizini** durdurur.

⚠️ **Defter `tur` sözlüğü iki yerdedir.** `token_ledger.tur` CHECK kısıtı, `servers/jeton.py`'ın
gönderebileceği **her** türü kapsamalıdır; kapsamazsa RPC check-ihlaliyle patlar ve tüketim
kaybolur. `tests/test_supabase_sql_invariants.py` bunu kaynaktan okuyup karşılaştırır.

## 2. ⚠️ Tıbbi güvenlik değişmezi (pazarlık edilemez)

Jeton **ticari** bir kapıdır, güvenlik kontrolü **değildir**:

- Süren seansı, seans durdurmayı, **acil durdurmayı**, sensör okumayı ve cihaz kontrolünü
  **asla** engellemez — bunlar `GUVENLIK_YOLLARI` kümesinde ve kapının **en başında** serbest
  bırakılır (bayrak/bakiye/ağ durumu fark etmeksizin).
- Yalnız **yeni yapay zekâ analizi** isteğini kapılar.
- Yetersiz bakiye mesajı, tedavinin etkilenmediğini **açıkça söyler**.

Bu üç davranış `tests/test_jeton_yoneticisi.py` içinde kilitli ve mutasyonla doğrulanmıştır
(acil durdurmayı kapıya sokan mutasyon kırmızı yanar).

## 3. Çevrimdışı klinik

İnternet yokken analiz **durmaz**: tüketim `PEMF_DATA_DIR/jeton_bekleyen.json` defterine yazılır,
bağlantı gelince `bekleyenleri_uzlastir()` ile gönderilir. Sınır: `PEMF_JETON_OFFLINE_TAVAN`
(varsayılan 50) — sınırsız olsaydı ücretlendirme anlamsızlaşırdı. Tavan aşılsa bile **tedavi yolu
serbest** kalır.

**Başarısız gönderim kaydı silmez** — silseydi tüketim sessizce kaybolurdu. `istek_id` sayesinde
tekrar gönderim güvenlidir (sunucu ikinciyi yok sayar).

## 4. Parçalar

| Katman | Dosya | İş |
|---|---|---|
| Şema | `database/supabase_jetonlar.sql` | `token_balances` + `token_ledger`, RLS, atomik `jeton_tuket` RPC, `jeton_donem_yenile` |
| Uç | `pemf-vet-web/api/tokens.ts` | GET bakiye · POST tüketim (idempotans zorunlu) |
| Cihaz | `servers/jeton.py` | Kapı + çevrimdışı defter + uzlaştırma; bayraklı, fail-open |
| Web modeli | `pemf-vet-web/src/config.ts::JETON` | Plan hakları, maliyetler, paketler (kullanıcı metninin kaynağı) |
| Arayüz | `src/components/AccountButton.tsx`, `src/lib/jeton.ts` | Hesap menüsünde kalan jeton |
| Fiyat metni | `pemf-vet-web/src/lib/planFiyat.ts` | Plan fiyat gösterimi — **tek kaynak**; aylık ücreti olmayan planı "₺0/ay" diye basmayı önler |
| Canlı DB | `scripts/supabase_sql.py` | SQL uygulama + çalışan sorgu/kilit izleme + `--denetim` (canlı güvenlik değişmezleri). Yazma `--yaz` kapısının arkasında |
| Sertleştirme | `database/supabase_sertlestirme.sql` | Canlıda bulunan rol-yetkisi sapmalarının geri alınması (2026-08-21) |
| Okuma RPC | `database/supabase_okuma_rpc.sql` | `abonelik_getir` · `jeton_bakiyem` · `jeton_defterim` — kullanıcı okumaları RPC'de; tablolarda **hiç** rol yetkisi yok |

## 5. Devreye alma — adım adım

**Bugünkü durum (2026-08-20):** şema, uç, cihaz modülü ve arayüz HAZIR ve testli; ama sistem
**hiçbir yerde devrede değil** — ve sahip kararıyla (2026-08-20) **şimdilik öyle kalacak**:
"ücretsiz sistem şu an aktifte devam etmeli, henüz aktif etme; jeton kalsın, altyapı hazır
şekilde." `FREE_MODE=true` ve `PEMF_JETON_ENFORCED` kapalı; ikisi de **testle kilitli**
(`kullandikca-ode.test.ts` §6). Devreye alınacağı gün eksik olanlar (2026-08-22 güncellemesi): ~~(a) SQL Supabase'de
çalıştırılmadı~~ ✅ Adım 1 yapıldı (2026-08-21); ~~(b) ödeme geri-çağrısı jeton yüklemiyor~~ ✅ Adım 3 yapıldı (2026-08-22); ~~(c) `servers/jeton.py`'yi çağıran kimse yok~~ ✅ Adım 4 yapıldı
(2026-08-22, `jeton_gate` → `ai_router`).

> Sıra önemlidir: her adım kendinden öncekine dayanır ve her adımın sonunda **doğrulama** vardır.
> Adım 1 ve 5 dışındakiler kod işidir; kod yazılırken deponun kuralı geçerli: **kırmızı-önce test →
> düzeltme → mutasyon → tam süit**.

---

### Adım 1 — Şemayı Supabase'e kur — ✅ **YAPILDI (2026-08-21)**

Canlı projede (`wmsxonunkphjeregpvuj`) `token_balances` + `token_ledger` + `jeton_tuket` +
`jeton_donem_yenile` kuruldu ve doğrulandı. Panele yapıştırmak yerine artık araç kullanılıyor:

```
python scripts/supabase_sql.py --dosya database/supabase_jetonlar.sql --yaz
python scripts/supabase_sql.py --denetim        # canlı güvenlik değişmezleri
```

> ⚠️ **KURULUM SIRASINDA CANLI BİR AÇIK OLUŞTU VE KAPATILDI — tekrarlanmasın.**
> `jeton_donem_yenile(uuid, integer)` SECURITY DEFINER'dır ve **istediği kullanıcıya istediği
> kadar jeton yazar**. Dosyadaki `revoke all ... from public, authenticated` satırı yetmedi:
> Supabase yeni fonksiyona `anon` rolüne **ayrıca** execute verir ve PUBLIC'ten geri almak bunu
> kaldırmaz. Sonuç: şema kurulduğu anda, mobil uygulamanın içinde taşınan **anon anahtarıyla
> herkes kendine sınırsız jeton yazabilir** durumdaydı (doğrudan fatura baypası + başkasının
> bakiyesini ezme). Ölçüldü, kapatıldı, `--denetim` 5. maddesiyle kilitlendi.
> **Kural: `from public` YETMEZ — rolleri tek tek yaz (`from public, anon, authenticated`).**

Eski yol (panele yapıştırma) hâlâ geçerlidir; o durumda **kurulumdan sonra mutlaka**
`--denetim` çalıştırın.

**Doğrulama** (aynı editörde çalıştır):
```sql
select table_name from information_schema.tables
 where table_schema='public' and table_name in ('token_balances','token_ledger');
-- 2 satır dönmeli

select routine_name from information_schema.routines
 where routine_schema='public' and routine_name in ('jeton_tuket','jeton_donem_yenile');
-- 2 satır dönmeli
```

**Kendi hesabına deneme jetonu yükle** (test için; `<UID>` = Supabase → Authentication → Users):
```sql
select public.jeton_donem_yenile('<UID>'::uuid, 500);
select * from public.token_balances where user_id='<UID>';   -- aylik_hak = 500
```

**Geri alma:** `drop function if exists public.jeton_tuket(integer,text,text,text,text);`
`drop function if exists public.jeton_donem_yenile(uuid,integer);`
`drop table if exists public.token_ledger; drop table if exists public.token_balances;`

---

### Adım 2 — Bakiye ucunu doğrula *(çalıştırma işi, ~5 dk — şema HAZIR)*

`api/tokens.ts` zaten yayında (Vercel her `api/*.ts` dosyasını uç olarak yayınlar) ve mevcut
ortam değişkenlerini kullanır: `SUPABASE_URL`, `SUPABASE_ANON_KEY` — **yeni env gerekmez**
(service_role yalnız Adım 3'te lazım olacak ve o da zaten tanımlı).

1. Siteye giriş yap → tarayıcı konsolunda oturum jetonunu al:
   ```js
   (await window.supabase?.auth.getSession())?.data?.session?.access_token
   ```
   *(veya hesap menüsünü açıp Ağ sekmesinde `/api/tokens` isteğine bak)*
2. Uç yanıtı:
   ```bash
   curl -H "Authorization: Bearer <JWT>" https://<site>/api/tokens
   # {"kalan":500,"aylik_hak":500,"satin_alinan":0,...}
   ```
3. **Arayüz doğrulaması:** sitede **Hesabım** menüsünü aç → "Kalan jeton 500" görünmeli.
   Görünmüyorsa uç 200 dönmemiştir (menü, yanlış sayı göstermektense hiç göstermez).

---

### Adım 3 — Ödeme yenilemesini jetona bağla — ✅ **YAPILDI (2026-08-22)**

`api/_lib/util.ts::jetonDonemYenile` (service_role RPC) eklendi; `callback.ts` başarı dalı ve
`webhook.ts` yenileme olayı çağırıyor. ⚠️ Webhook yalnız CANLI durumlarda (active/trialing)
yükler — iptal olayına hak yazmak ödenmemiş hak dağıtmaktır. Yükleme patlarsa abonelik yazımı
GERİ ALINMAZ (kullanıcı parasını ödedi; loglanır, destek elle yükler). Tier→hak eşlemesi
`JETON_HAKLARI` sabitinde ve `src/config.ts::JETON.planHaklari` ile paritesi testle kilitli.
Kilit: `api/_lib/__tests__/jeton-yenileme.test.ts` (7 test, 5 mutasyon).
İyzico SANDBOX uçtan-uca doğrulaması hâlâ sahibindir (satış açılmadan önce bir kez).

Orijinal talimat (tarihçe):

Bugün `api/callback.ts` yalnız `upsertSubscription(...)` çağırıyor; jeton yüklenmiyor. Yani
ödeme alınsa bile kullanıcının bakiyesi 0 kalır.

**3.1** `api/_lib/util.ts` içine service-role yardımcı ekle (`upsertSubscription`'ın hemen altına,
aynı deseni izleyerek):

```ts
/** Plan dönemi yenilendiğinde jeton hakkını yazar (service_role — RPC'yi kullanıcı çağıramaz). */
export async function jetonDonemYenile(userId: string, aylikHak: number): Promise<void> {
  const r = await fetch(`${SB_URL()}/rest/v1/rpc/jeton_donem_yenile`, {
    method: 'POST',
    headers: {
      apikey: SB_SERVICE(),
      Authorization: `Bearer ${SB_SERVICE()}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ p_user: userId, p_aylik_hak: aylikHak }),
  })
  if (!r.ok) throw new Error(`jeton_donem_yenile ${r.status}: ${await r.text()}`)
}
```

**3.2** `api/callback.ts` — `upsertSubscription({...})` çağrısının **hemen ardına** ekle:

```ts
// Jeton hakkı plandan gelir (tek kaynak: src/config.ts::JETON.planHaklari).
// ⚠️ Jeton yüklenemezse ABONELİK YAZIMINI GERİ ALMA: kullanıcı parasını ödemiştir; hakkı
// olmadan bırakmak yerine hatayı logla, destek elle yükleyebilsin.
try {
  await jetonDonemYenile(userId, JETON_HAKLARI[meta.tier])
} catch (e) {
  console.error('callback: jeton yüklenemedi (abonelik YAZILDI, elle yükleme gerekir)', { userId, tier: meta.tier, e })
}
```

**3.3** Aynı çağrıyı `api/webhook.ts` içindeki **yenileme** olayına da ekle — aksi hâlde ilk ay
jeton gelir, ikinci ay gelmez.

**3.4** ⚠️ Bu adım para yolunu değiştirir: `pemf-vet-web/api/_lib/__tests__/` altına kırmızı-önce
test yaz (yenileme çağrısı yapılıyor mu, hata yutuluyor mu, tier→hak eşlemesi doğru mu).

**Doğrulama:** iyzico **sandbox**'ta bir abonelik başlat → callback dönüşünde
`select * from token_balances where user_id='<UID>'` → `aylik_hak` planın hakkı kadar olmalı;
`token_ledger`'da `tur='plan_yenileme'` satırı görünmeli.

---

### Adım 4 — Jeton kapısını AI uçlarına bağla — ✅ **YAPILDI (2026-08-22, 18. parti)**

`jeton_gate` yazıldı ve `ai_router`a bağlandı; mobil 402'yi ayrı ele alıyor (`apiClient.ts`).
Taşıma katmanı belgedekinden bilinçli saptı: site ucu yerine **Supabase RPC**
(`jeton_bakiyem`/`jeton_tuket`, entitlement deseni — gerekçe `servers/jeton.py` kapı bloğu
yorumunda: cihaz Supabase'le zaten konuşuyor, siteye sıçrama tek yeni arıza noktası eklerdi;
kimlik `auth.uid()`ten, idempotans RPC içinde). Uç eşlemesi: `pro/stop|status|approve|reject|
frame|organ|calibrate` KAPILANMAZ (stop güvenlik sınıfı; frame seans-içi akış — ücret
seans-başına `pro/start`=5); `pro/propose`=sensor(1); rna/kidney_ct/histopath=3; sound=1;
kalan görüntü uçları=1. **Bayrak HÂLÂ KAPALI** — kapı bağlı ama uykuda; satış açılmadı.
Kilit: `tests/test_jeton_gate.py` (9 test, 7 mutasyon — "pro/stop kapılanır" ve "tedavi ucu
kapılanır" mutasyonları dâhil) + `apiClient.jeton402.test.ts`.

Orijinal talimat (tarihçe):

`servers/jeton.py` yazıldı ve 10 testle kilitli, **ama hiçbir yerden çağrılmıyor**
(`grep -rn "JetonYoneticisi" --include=*.py` yalnız modülün kendisini ve testlerini buluyor).
Bağlantı, `entitlement.py`'nin deseniyle birebir aynı olmalı: **router-seviyesi FastAPI
bağımlılığı**.

**4.1** `servers/jeton.py` içine bir `jeton_gate` bağımlılığı ekle:

- İstek yolundan işlem türünü çıkar (`/ai/goruntu…` → `goruntu`, ağır araştırma uçları →
  `agir_arastirma`, AI Pro seans başlatma → `ai_pro_seans`).
- Çağıranın Supabase JWT'sini **istekten** al (`Authorization` başlığı) — `entitlement.py`
  `resolve_entitlement` içinde bunu zaten yapıyor, aynı yardımcıyı kullan.
- `JetonYoneticisi.izin(...)` çağır; `izinli=False` ise `HTTPException(402, karar.mesaj)` fırlat.
- Bakiye okuma/tüketim gönderme fonksiyonlarını `/api/tokens` ucuna bağla (site adresi env'den).
- **Bloklayan ağ çağrısını `asyncio.to_thread` ile threadpool'a at** — `ai_queue_gate` bunu
  yapıyor; yapmazsan event loop bloklanır.

**4.2** `servers/ai_router.py:54` satırına ekle:

```python
ai_router = APIRouter(dependencies=[Depends(_allow_large_upload), Depends(ai_queue_gate), Depends(jeton_gate)])
```

**4.3** ⚠️ **TIBBİ GÜVENLİK — bu adımın en önemli kısmı.** `ai_router` yalnız analiz uçlarını
taşıyor; ama emin ol:
- Tedavi/kontrol uçları (`/api/session/*`, `/api/coil/*`, acil durdurma) bu router'da **değil**;
- `entitlement.py`'deki `_QUEUE_BYPASS_FRAGMENTS` listesinin karşılığı jeton tarafında
  `GUVENLIK_YOLLARI`dır — yeni bir tedavi ucu eklenirse **oraya da eklenmelidir**;
- Kırmızı-önce test: "jeton 0 iken `/api/session/stop` ve acil durdurma **200 döner**".

**4.4** Mobil/masaüstü arayüzünde 402 yanıtını yakala ve kullanıcıya jeton mesajını göster
(`pf/src/services/apiClient.ts` — 402'yi ayrı ele al, genel hataya karıştırma).

**Doğrulama:** `PEMF_JETON_ENFORCED=1` + bakiyeyi 0'a çek (`update token_balances set aylik_hak=0,
satin_alinan=0 where user_id='<UID>'`) → bir AI analizi iste: **402 + Türkçe mesaj**. Aynı anda
seans başlat/durdur ve acil durdur: **hepsi çalışmalı**.

---

### Adım 5 — Ek jeton paketi satışı *(KOD YAZILACAK, ~2 saat — isteğe bağlı, sonraya bırakılabilir)*

Jeton bitince kullanıcı ek paket alabilmeli (`JETON.paketler`). iyzico tarafında bu bir **abonelik
değil tek seferlik ödemedir**; `IYZICO_SETUP.md`'deki ürün/plan deseninin tek-çekim karşılığı
kurulur, `api/checkout.ts`e `tur: 'jeton_paketi'` dalı eklenir ve başarı geri-çağrısında
`satin_alinan` artırılır (yeni bir `jeton_paket_yukle` RPC'si; `jeton_donem_yenile`
**kullanılmaz** — o aylık hakkı EZER).

Bu adım tamamlanana kadar jetonu biten kullanıcı **plan yükseltmesiyle** devam eder; SSS metni
ek paketten söz ettiği için ya adım tamamlanmalı ya da o cümle geçici olarak yumuşatılmalıdır.

---

### Adım 5b — Kullandıkça-öde tahsilatı *(KOD YAZILACAK, ~3 saat — PAYG satılacaksa ZORUNLU)*

Kullandıkça-öde üyelik **kartı önceden saklamayı** gerektirir: ay sonunda tahsil edilecek tutar
o an belli değildir. iyzico'da bu, abonelik değil **saklı kart + sonradan çekim** desenidir.

**5b.1** Üyelik açılışında ₺0 tutarlı bir kart doğrulama/kaydetme işlemi yapılır; dönen
`cardUserKey` + `cardToken` **Supabase'de service_role ile** saklanır (asla istemciye dönmez).

**5b.2** Ay sonunda çalışan bir iş (Vercel Cron ya da Supabase scheduled function):

```
kullandikca_borc > 0 olan her kullanıcı için:
  tutar = kullandikca_borc × JETON.kullandikcaOde.jetonFiyati
  iyzico saklı kartla çek
  başarılıysa: kullandikca_borc = 0  +  token_ledger'a ('faturalandi', +miktar) kaydı
  başarısızsa: borç DURUR, kullanıcıya e-posta, yeni analiz borç tavanında zaten duracak
```

**5b.3** `JETON.kullandikcaOde.faturaEsigiTL` (₺500) ara-tahsilat eşiğidir: borç bu tutarı aşarsa
ay sonu beklenmeden çekilir. Amaç, tek seferde büyük ve tahsil edilemeyen fatura oluşmaması.

⚠️ **Borç sıfırlaması ile defter kaydı aynı işlemde olmalı.** Ayrı yapılırsa çekim başarılı olup
borç sıfırlanmaz (kullanıcı iki kez ödenir) ya da tersi (hiç tahsil edilmez).

⚠️ **Tahsilat başarısızlığı tedaviyi durdurmaz.** Yalnız yeni analiz durur — ve bu, borç tavanı
kapısının zaten yaptığı şeydir; ayrı bir "hesabı dondur" yolu **eklenmemelidir**.

Bu adım bitene kadar kullandıkça-öde planı sitede görünür ama **satılmamalıdır** (bugün
`FREE_MODE=true` olduğu için zaten hiçbir plan satılmıyor — kapı kapalı).

---

### Adım 6 — Bayrağı aç *(çalıştırma işi, ~1 dk + izleme)*

`PEMF_JETON_ENFORCED=1` (klinik cihazının servis ortamında). İsteğe bağlı:
`PEMF_JETON_OFFLINE_TAVAN=50`.

**Kademeli açmayı öner:** önce tek bir test kliniğinde aç, bir hafta izle (`token_ledger`'da
tüketim akıyor mu, `jeton_bekleyen.json` şişiyor mu), sonra yaygınlaştır.

**Anında geri alma:** `PEMF_JETON_ENFORCED=0` → sistem tamamen no-op olur, hiçbir analiz
engellenmez. Şema ve defter yerinde kalır (veri kaybı yok).

---

### Sırayı bozmayın — neden

| Adım atlanırsa | Ne olur |
|---|---|
| 1 atlanır | Uç 500/boş döner, arayüz bakiyeyi hiç göstermez |
| 3 atlanır | Ödeme alınır ama bakiye 0 kalır → **ödeyen kullanıcı analiz yapamaz** |
| 4 atlanır | Jeton hiç tüketilmez; sistem yalnız "vitrin" olur (bugünkü durum) |
| 5 atlanır | Jetonu biten kullanıcının tek çıkışı plan yükseltmek olur |
| **5b atlanır** | **Kullandıkça-öde üyeler analiz yapar ama HİÇ tahsil edilmez** (kart saklanmadan ay sonu çekimi imkânsız) |
| 6 önce açılır | Kapı bağlı değilse zaten no-op; ama 3 bitmeden açılırsa ödeyen kullanıcı bloklanır |

## 6. Atomiklik ve çift düşme

- Düşme işlemi tek deyimde, **satır kilidiyle** (`for update`) yapılır → iki cihaz aynı anda
  analiz isterse bakiye çift düşmez.
- `token_ledger (user_id, istek_id)` **UNIQUE** → yeniden deneme aynı jetonu iki kez harcamaz;
  RPC ikinci çağrıda mevcut bakiyeyi döndürür (`tekrar: true`).
