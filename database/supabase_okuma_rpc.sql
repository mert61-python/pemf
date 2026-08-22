-- PEMF Vet — KULLANICI OKUMALARI: RPC'ye taşıma (sahip kararı 2026-08-21)
-- =================================================================================
-- NEDEN. Canlıya ilk SQL erişimi açıldığında ölçüldü: `public` şemasındaki tabloların tamamında
-- `anon`/`authenticated` rollerine DOĞRUDAN tablo yetkisi duruyordu — kimse `grant` yazmadı,
-- Supabase yeni tabloya bunu VARSAYILAN olarak veriyor. Hepsi geri alındı; ama üç tabloda
-- (`subscriptions`, `token_balances`, `token_ledger`) `authenticated SELECT` kalmak ZORUNDAYDI:
-- okuma yolu "RLS ile kendi satırını oku" desenine dayanıyordu ve Postgres'te RLS politikası
-- TEK BAŞINA yetmez — rolün ayrıca tablo SELECT yetkisi de gerekir.
--
-- Bu, kök nedeni kapatmayı da engelliyordu: `alter default privileges ... revoke` yazılsaydı bir
-- sonraki tablo "politikası var ama okunamıyor" durumuna düşerdi ve hata mesajı bunu söylemezdi.
--
-- SAHİP KARARI: **okumaları RPC'ye taşı.** Kullanıcı anahtarıyla yapılan okumalar artık SECURITY
-- DEFINER fonksiyonlardan geçer; tablolarda HİÇBİR role yetki kalmaz. Kazanç:
--   1. Varsayılan yetkiler kaynağında kapatılabilir → yeni tabloda soru hiç doğmaz.
--   2. Dönen ALAN KÜMESİ imzada SABİTLENİR — istemci `select=*` ile fazladan sütun çekemez
--      (bugün `subscriptions` içinde `stripe_customer_id`/`stripe_subscription_id` de var).
--   3. Tek okuma noktası → ileride denetim/limit eklemek için tek yer.
--
-- ⚠️ HER FONKSİYON `auth.uid()` KULLANIR. Parametre olarak kullanıcı kimliği ALMAZLAR — alsalardı
-- çağıran başkasının satırını isteyebilirdi. Kimlik JWT'den gelir, PostgREST'in doğruladığı
-- yerden; sahte kimlik mümkün değildir.
--
-- ⚠️ `anon`A GRANT VERİLMEZ. Bu fonksiyonlar `auth.uid()` ile çalışır; anon'da uid yoktur, yani
-- açmanın hiçbir faydası yok, yalnız saldırı yüzeyi eklerdi.
-- ⚠️ `revoke ... from public` YETMEZ: Supabase yeni fonksiyona anon/authenticated/service_role
-- rollerine AYRICA execute verir. Roller tek tek yazılır (2026-08-21'de `jeton_donem_yenile`
-- tam bu yüzden anon'a açık kalmıştı — sınırsız jeton yazma deliği).
--
-- Çalıştırma:  python scripts/supabase_sql.py --dosya database/supabase_okuma_rpc.sql --yaz
-- Doğrulama :  python scripts/supabase_sql.py --denetim

-- ── 1) ABONELİK — servers/entitlement.py okur ────────────────────────────────────
-- Eskiden: GET /rest/v1/subscriptions?select=tier,addons,status,trial_ends_at,current_period_end
-- Aynı alan kümesi; `stripe_*` sütunları BİLEREK dışarıda (istemcinin işi değil).
create or replace function public.abonelik_getir()
returns table (
  tier               text,
  addons             jsonb,
  status             text,
  trial_ends_at      timestamptz,
  current_period_end timestamptz
)
language sql
security definer
set search_path = public
as $$
  select s.tier, s.addons, s.status, s.trial_ends_at, s.current_period_end
    from public.subscriptions s
   where s.user_id = auth.uid();
$$;

revoke all on function public.abonelik_getir() from public, anon;
grant execute on function public.abonelik_getir() to authenticated;

-- ── 2) JETON BAKİYESİ — pemf-vet-web/api/tokens.ts okur ──────────────────────────
-- Eskiden: GET /rest/v1/token_balances?select=aylik_hak,satin_alinan,bekleyen_borc,
--                                             odeme_modeli,kullandikca_borc,donem_sonu
create or replace function public.jeton_bakiyem()
returns table (
  aylik_hak        integer,
  satin_alinan     integer,
  bekleyen_borc    integer,
  odeme_modeli     text,
  kullandikca_borc integer,
  donem_sonu       timestamptz
)
language sql
security definer
set search_path = public
as $$
  select b.aylik_hak, b.satin_alinan, b.bekleyen_borc,
         b.odeme_modeli, b.kullandikca_borc, b.donem_sonu
    from public.token_balances b
   where b.user_id = auth.uid();
$$;

revoke all on function public.jeton_bakiyem() from public, anon;
grant execute on function public.jeton_bakiyem() to authenticated;

-- ── 3) JETON DEFTERİ — "jetonum nereye gitti?" ───────────────────────────────────
-- Defter tablosu bu soruyu cevaplamak için var (bkz. supabase_jetonlar.sql §2). Tablo yetkisi
-- kaldırıldığı için okuma yolu OLMADAN kalırdı; bu RPC o yolu sağlar.
-- ⚠️ `p_limit` SINIRLANIR: istemcinin verdiği sayı olduğu gibi kullanılsaydı tek istekle tüm
-- defter çekilebilirdi (hem yük hem gereksiz veri). En fazla 200, en az 1.
create or replace function public.jeton_defterim(p_limit integer default 50)
returns table (
  miktar     integer,
  tur        text,
  detay      text,
  cihaz_id   text,
  created_at timestamptz
)
language sql
security definer
set search_path = public
as $$
  select l.miktar, l.tur, l.detay, l.cihaz_id, l.created_at
    from public.token_ledger l
   where l.user_id = auth.uid()
   order by l.created_at desc
   limit least(greatest(coalesce(p_limit, 50), 1), 200);
$$;

revoke all on function public.jeton_defterim(integer) from public, anon;
grant execute on function public.jeton_defterim(integer) to authenticated;

-- ── 4) ARTIK GEREKSİZ TABLO YETKİLERİ ────────────────────────────────────────────
-- Okuma RPC'ye taşındığına göre `authenticated SELECT` istisnası da kalkar.
revoke all on public.subscriptions  from anon, authenticated;
revoke all on public.token_balances from anon, authenticated;
revoke all on public.token_ledger   from anon, authenticated;

-- RLS politikaları BİLEREK BIRAKILIYOR (silinmiyor): SECURITY DEFINER fonksiyonlar RLS'i zaten
-- baypas eder, yani politikalar bugün işlevsizdir. Ama biri ileride yanlışlıkla tabloya SELECT
-- verirse, politikanın orada durması "yalnız kendi satırını görür" güvenlik ağını korur.
-- Politikayı silmek, o hatayı TAM ERİŞİME çevirirdi.

-- ── 5) KÖK NEDEN: varsayılan yetkileri kapat ─────────────────────────────────────
-- ⚠️ SAPMANIN KAYNAĞI BURASI. Supabase, `public` şemasında oluşturulan her yeni tabloya
-- anon+authenticated yetkisi verir. Okumalar RPC'ye taşındığı için artık hiçbir tablonun rol
-- yetkisine ihtiyacı yok → varsayılanı kapatmak güvenlidir ve bir sonraki tabloda aynı deliğin
-- açılmasını önler.
-- ⚠️ BUNDAN SONRA: bir tabloya doğrudan erişim GEREKİRSE açıkça `grant` yazılmalıdır — ve o an
-- `tests/test_supabase_sql_invariants.py` kırmızı yanar. Bu KASITLIDIR: doğrudan tablo erişimi
-- artık sessizce değil, bilinçli bir kararla eklenebilir.
alter default privileges in schema public revoke all on tables from anon, authenticated;
