-- PEMF Vet — CANLI ŞEMA SERTLEŞTİRME (rol yetkilerini geri alma)
-- =================================================================================
-- BULUNDUĞU AN: 2026-08-21, canlı projeye ilk kez SQL erişimi sağlandığında ölçüldü
-- (`scripts/supabase_sql.py --denetim`).
--
-- NE BULUNDU: `public` şemasındaki DÖRT tablonun tamamında `anon` ve/veya `authenticated`
-- rollerine DOĞRUDAN tablo yetkisi duruyordu — SELECT, INSERT, UPDATE, DELETE, TRUNCATE,
-- REFERENCES, TRIGGER. Bu, Supabase'in YENİ TABLOYA VERDİĞİ VARSAYILAN yetkidir; hiç kimse
-- açıkça `grant` yazmadı. Deponun kendi değişmez testi (`tests/test_supabase_sql_invariants.py`
-- → `test_anon_rollerine_dogrudan_tablo_yetkisi_verilmiyor`) yalnız .sql DOSYALARINA bakıyordu;
-- dosyalarda `grant` olmadığı için test hep yeşildi ve sapma GÖRÜNMEDİ.
--
-- ⚠️ BUGÜN SIZINTI YOK — ve bunu abartmamak önemli: `devices`, `patients`, `treatment_sessions`
-- tablolarında RLS AÇIK ve SIFIR politika var; `subscriptions`ta RLS açık ve yalnız
-- "kendi satırını SELECT" politikası var. RLS, politikası olmayan komutları REDDEDER. Yani
-- yetkiler ATIL durumda: PostgREST üzerinden hiçbiri kullanılamıyor.
--
-- ⚠️ ASIL RİSK GİZLİ MAYIN OLMASI: tek bir izin verici politika eklendiği anda (ör. hata
-- ayıklarken yazılan `for all using (true)`) ya da RLS bir göç sırasında bir an kapatıldığında,
-- mobil uygulamanın İÇİNDE taşınan `anon` anahtarı doğrudan yazma yetkisine kavuşur. Ayrıca
-- TRUNCATE/REFERENCES/TRIGGER yetkileri RLS ile FİLTRELENMEZ (RLS satır düzeyindedir; TRUNCATE
-- tablo düzeyi bir ayrıcalıktır) — bugün PostgREST bunları uçlamıyor, ama yetkinin durması için
-- hiçbir sebep yok.
--
-- NEDEN GÜVENLE GERİ ALINABİLİR (ölçüldü, varsayılmadı):
--   · `devices` / `patients` / `treatment_sessions`: hiçbir istemci bu tablolara DOĞRUDAN
--     gitmiyor — erişim yalnız SECURITY DEFINER RPC'leriyle (resolve_*/upsert_*). Depo geneli
--     `rest/v1/<tablo>` taramasında tek bir kullanım bile çıkmadı.
--   · `subscriptions`: web uçları SERVICE_ROLE ile yazıyor (RLS ve grant'ları baypas eder →
--     etkilenmez). `servers/entitlement.py` ise kullanıcının KENDİ JWT'siyle OKUYOR → bu yüzden
--     `authenticated` rolünde SELECT **bırakılır**.
--   · Zaten RLS tarafından reddedilen bir yetkiyi geri almak davranışı DEĞİŞTİREMEZ.
--
-- GERİ ALMA: bu dosya bir sertleştirmedir; geri almak gerekirse ilgili `grant` verilir. Ancak
-- geri vermeden ÖNCE "hangi istemci hangi tabloya doğrudan gidiyor?" sorusu cevaplanmalıdır.
--
-- Çalıştırma:  python scripts/supabase_sql.py --dosya database/supabase_sertlestirme.sql --yaz
-- Doğrulama :  python scripts/supabase_sql.py --denetim

-- ── 1) YALNIZ RPC ile erişilen tablolar: doğrudan yetki KALMASIN ─────────────────
revoke all on public.devices            from anon, authenticated;
revoke all on public.patients           from anon, authenticated;
revoke all on public.treatment_sessions from anon, authenticated;

-- ── 2) subscriptions ─────────────────────────────────────────────────────────────
-- ⚠️ BU BÖLÜM AYNI GÜN AŞILDI. İlk hâli `authenticated`ta SELECT bırakıyordu, çünkü
-- `servers/entitlement.py` tabloyu doğrudan okuyordu ve RLS politikası tek başına yetmiyordu.
-- Sahip kararı ("okumaları RPC'ye taşı") sonrası okuma `abonelik_getir()` fonksiyonuna taşındı
-- → istisnaya gerek kalmadı. Aşağıdaki satır artık TAM geri alma yapıyor.
-- (Tarihçe bilerek duruyor: "neden bir dönem SELECT vardı?" sorusunun cevabı budur.)
revoke all on public.subscriptions from anon, authenticated;

-- ── 3) FONKSİYON YETKİLERİ: `revoke ... from public` YETMİYOR ───────────────────
-- ⚠️ Aynı kök neden fonksiyonlarda da var ve DAHA TEHLİKELİ. Supabase yeni fonksiyona anon +
-- authenticated + service_role rollerine AYRICA execute verir; deponun her yerinde kullanılan
-- `revoke all on function ... from public` kalıbı bu üçünü KALDIRMAZ (PUBLIC ayrı bir kavramdır).
--
-- `_pemf_verify_device(device_id, secret)` tam bu yüzden anon'a AÇIKTI. İstemcilerin hiçbiri onu
-- çağırmıyor (yalnız diğer RPC'lerin içinden) ama anon'a açık olması bir DOĞRULAMA ORAKÜLÜ
-- demektir: saldırgan cihaz sırrını sınırsız denemeyle arayabilir. SECURITY DEFINER fonksiyonlar
-- birbirini SAHİP yetkisiyle çağırdığı için bu geri alma iç kullanımı bozmaz.
revoke all on function public._pemf_verify_device(text, text) from anon, authenticated;

-- ⚠️ ANON'A AÇIK KALMASI GEREKENLER (tasarım — dokunmayın): resolve_device (eşleştirme),
-- upsert_device / upsert_patient / upsert_session / resolve_patients / resolve_sessions
-- (hepsi `p_secret` ile kendini doğrular), usage_counts (yalnız toplamlar).
-- Kapı: `scripts/supabase_sql.py --denetim` 5. madde bu listeyi kilitler.

-- ── 4) KÖK NEDEN — ✅ ÇÖZÜLDÜ (sahip kararı: "okumaları RPC'ye taşı") ────────────
-- Sapmanın kaynağı, Supabase'in yeni tabloya otomatik anon/authenticated yetkisi vermesidir.
-- Bu dosya yazıldığında varsayılanı kapatamıyorduk: `subscriptions`/`token_balances` okuması
-- "RLS ile kendi satırını oku" desenine dayanıyordu ve o desen tablo SELECT yetkisini ZORUNLU
-- kılıyor (RLS politikası tek başına yetmez). Varsayılanı kapatmak, bir sonraki tabloyu
-- "politikası var ama okunamıyor" durumuna düşürürdü — üstelik hata mesajı bunu söylemeden.
--
-- Sahip kararıyla desen değişti: okumalar SECURITY DEFINER RPC'lere taşındı
-- (`database/supabase_okuma_rpc.sql` → `abonelik_getir` / `jeton_bakiyem` / `jeton_defterim`).
-- Hiçbir tablonun rol yetkisine ihtiyacı kalmadığı için varsayılan da orada kapatıldı:
--
--     alter default privileges in schema public revoke all on tables from anon, authenticated;
--
-- Deneyle doğrulandı: kapatmadan sonra oluşturulan yeni bir tablo HİÇ yetki almıyor.
-- Kapı: `scripts/supabase_sql.py --denetim` (istisna kümesi artık BOŞ) +
-- `tests/test_supabase_okuma_rpc_uzerinden.py` (istemciler tabloya doğrudan gidemez).

-- Not: mevcut RLS politikaları ve SECURITY DEFINER RPC yetkileri DEĞİŞMEZ — bu dosya yalnız
-- doğrudan tablo yetkilerini kaldırır.
