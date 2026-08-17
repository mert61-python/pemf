-- Author: mertaygn, cglrgrkn
-- resolve_device: TAZELİK PENCERESİNİ GENİŞLET — "cihaz kapalı" teşhisi ölü koddu
-- (denetim 2026-08-17). Supabase → SQL Editor → bu dosyayı yapıştır → Run.
--
-- SORUN: fonksiyon `last_seen > now() - interval '5 minutes'` ile SUNUCUDA eliyordu; mobil
-- uygulamanın `deviceRegistry.STALE_MS`i de 5 dakika. İki pencere EŞİT olduğu için bayat satır
-- istemciye HİÇ ulaşmıyordu:
--   · `_cozumle`nin `if (!isFresh(...)) return { durum: "bayat" }` dalı ULAŞILAMAZ,
--   · `agTanisi`nin `bayat → cihaz_kapali` teşhisi hiç çalışmıyor,
--   · kullanıcı `{durum:"yok"}` alıyor ve ekranda "Kodu kontrol edin" yazıyor — oysa kod DOĞRU,
--     cihaz KAPALI. (2026-08-12 saha bildiriminin aynısı: kullanıcı yanlış yöne bakıyor.)
--
-- ÇÖZÜM: pencere 30 güne genişletilir; TAZELİK KARARI İSTEMCİDE kalır.
-- ⚠️ BAĞLANMA KARARI DEĞİŞMEZ: istemci 5 dk'lık `STALE_MS`i sürdürüyor ve `pairing.cihazaBaglan`
-- ile `getRemoteUrlForDevice` YALNIZ `durum === "bulundu"`e bakıyor → bayat/zehirli `tunnel_url`
-- hiçbir zaman kullanılmaz. Genişletme sadece SEBEBİ istemciye taşır.
-- ⚠️ APK/web YAYINI GEREKMEZ: sahadaki uygulamada `bayat` dalı ZATEN yazılı; bu SQL uygulandığı
-- an doğru mesaj görünmeye başlar.
--
-- ⚠️ NEDEN AYRI DOSYA: `database/supabase_devices.sql` baştan-kurulum betiğidir ve v2 kuruluyken
-- TEKRAR ÇALIŞTIRILAMAZ (`database/README.md`: sırsız v1 aşırı-yükleri geri gelir ve anon'a
-- yeniden grant edilir, hiçbir hata görünmeden). Bu dosya YALNIZ `resolve_device`i değiştirir,
-- `upsert_device`e DOKUNMAZ.
-- ⚠️ İmza ve dönüş tablosu BİREBİR aynı olduğu için `create or replace` geçerlidir: drop
-- gerekmez, ikinci bir aşırı-yükleme (PGRST203) oluşmaz, sahiplik/ACL korunur. Backend
-- etkilenmez — o yalnız `upsert_device` çağırıyor.
begin;

create or replace function public.resolve_device(p_code text default null, p_device_id text default null)
returns table (device_id text, name text, tunnel_url text, local_ip text, last_seen timestamptz)
language sql security definer set search_path = public as $$
    select d.device_id, d.name, d.tunnel_url, d.local_ip, d.last_seen
    from public.devices d
    where d.last_seen > now() - interval '30 days'
      and ( (p_device_id is not null and d.device_id = p_device_id)
            or (p_code is not null and length(p_code)=6 and upper(d.pairing_code)=upper(p_code)) )
    order by d.last_seen desc limit 1;
$$;

-- Yetki (idempotent güvence): tablo dökümü kapalı kalır, yalnız anon bu RPC'yi çalıştırır.
revoke all on function public.resolve_device(text,text) from public;
grant execute on function public.resolve_device(text,text) to anon;

commit;
