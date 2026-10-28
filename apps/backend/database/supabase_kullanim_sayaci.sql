-- Author: mertaygn, cglrgrkn
-- ============================================================================
-- KULLANIM SAYACI — sitedeki sayaç "indirme" değil BENZERSİZ KULLANIM göstersin.
--
-- KURULUM: Supabase Dashboard → SQL Editor → bu dosyayı yapıştır → Run. (Idempotent.)
--
-- NEDEN GEREKLİ: site şimdiye kadar GitHub Releases `download_count` gösteriyordu ve bu sayı
-- "kaç kişi" DEĞİL "kaç indirme"dir. İki bilinen şişme kaynağı vardı: (1) client her yeni
-- sürümde kendini güncellerken kurulum dosyasını YENİDEN indirir → kurulu her cihaz, yeni
-- kullanıcı olmadan sayacı artırır; (2) sürüm doğrulaması için yapılan kendi indirmelerimiz.
-- (`lib/downloadStats.ts` bunu zaten belgeliyordu; eksik olan gerçek kaynaktı.)
--
-- GÜVENLİK: bu fonksiyon YALNIZCA SAYI döndürür — satır, kimlik, e-posta, tünel adresi YOK.
-- `devices` tablosunun anon'a SELECT'i bilerek kapalıdır (cross-tenant dump riski; bkz.
-- supabase_devices.sql güvenlik notu). Buradaki SECURITY DEFINER o kapıyı AÇMAZ: geriye
-- yalnız üç tamsayı gider, dolayısıyla dökme yüzeyi oluşmaz.
--
-- ⚠️ auth.users OKUNUR: `security definer` + `set search_path` ile. Yalnız `count(*)` alınır;
-- hiçbir kullanıcı alanı (e-posta vb.) dışarı çıkmaz.
--
-- ⚠️ D6.13 (B-3.60): `-dev` ETİKETLİ SATIRLAR SAYILMAZ. Launcher'sız koşan her backend (geliştirici makinesi, test,
-- Docker, derleme dizini) bulut kaydını `<ad>-dev` adıyla yazar (`servers/sync_worker._cihaz_adi`; sahip kararı 2026-08-30:
-- engelleme değil ETİKETLEME). Süzgeç yokken sitedeki "Aktif cihaz (30 gün)" bunları klinik cihazı sayıyordu. Adı boş
-- (eski istemci) satır gerçek cihaz sayılır (`coalesce`). Kapı: tests/test_kullanim_sayaci_DEV_satirlarini_SAYMAZ_D6_13.py
-- ⚠️ Canlıya bu dosyayı SAHİP uygular (Y172) — depo değişikliği canlıyı kendiliğinden değiştirmez.
-- ============================================================================

create or replace function public.usage_counts()
returns table (
    accounts        bigint,  -- e-postası DOĞRULANMIŞ hesap sayısı = "benzersiz kullanıcı"
    devices_total   bigint,  -- kurulu cihaz (device_id MAC tabanlı birincil anahtar → benzersiz; `-dev` hariç)
    devices_active  bigint   -- son 30 günde heartbeat gönderen cihaz (`-dev` hariç)
)
language sql
security definer
set search_path = public, auth
as $$
    select
        -- ⚠️ YALNIZ DOĞRULANMIŞ hesaplar: doğrulanmamış kayıt "kullanıcı" değildir; e-posta
        -- doğrulaması açık olduğu için (bkz. auth akışı) o satırlar tamamlanmamış denemelerdir.
        (select count(*) from auth.users u where u.email_confirmed_at is not null)::bigint,
        (select count(*) from public.devices d where coalesce(d.name, '') not like '%-dev')::bigint,
        (select count(*) from public.devices d
          where d.last_seen > now() - interval '30 days' and coalesce(d.name, '') not like '%-dev')::bigint;
$$;

-- En az ayrıcalık: önce herkesten al, yalnız anon'a ver (diğer RPC'lerle aynı desen).
revoke all on function public.usage_counts() from public;
grant execute on function public.usage_counts() to anon;

-- Doğrulama (SQL Editor'de çalıştırıp gözle görebilirsiniz):
--     select * from public.usage_counts();
