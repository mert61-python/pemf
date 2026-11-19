-- Author: mertaygn, cglrgrkn
-- TA T5 · ÇOKLU KLİNİK P2 (`resolve_device` kod kaba kuvveti) — seçenek (a): CİHAZ EŞLEŞTİRME KODU 6 → 8 KARAKTER (DoS-nötr).
-- ⚠️ CANLIYA AÇILIŞ GÜNÜ UYGULANIR (sahip "aç" kararıyla, koordinatör — Y172). Supabase → SQL Editor → bu dosyayı yapıştır → Run.
--
-- SORUN (ölçüldü 2026-08-30, hafıza "çoklu klinik güvenlik borçları" P2): `resolve_device(p_code)` sır ALMAZ ve `tunnel_url` +
-- `local_ip` + `name` döndürür; `/api/auth/exchange` tünelden erişilir + auth-muaf (kod = kimlik) → geçerli kod bulunursa exchange
-- TEK denemede api_token verir. Supabase bu RPC'de hız sınırı uygulamıyor (429 yok). Kod uzayı 31⁶ ≈ 887 milyon.
-- ÇÖZÜM (a): yeni kodlar 8 karakter (31⁸ ≈ 852 milyar, ~961 kat) — sunucuda deneme sayacı / kilit YOK → meşru kullanıcıyı
-- kilitleyen DoS yüzeyi oluşmaz. Kod üretimi: `apps/backend/utils/path_utils.get_pairing_code` + `utils/secrets_manager._gen_pairing`.
-- GEÇİŞ: mevcut 6 karakterli kodlar ÇALIŞMAYA DEVAM EDER (cihazın `pairing_code.txt`'si korunur) → RPC 6 VE 8 uzunluğu kabul eder.
-- (Eski kodu 8'e çevirmek isteyen klinik: PEMF_RESET_PAIRING_CODE=1 ile bir açılış — telefonlar yeniden eşleşir.)
--
-- ⚠️ YALNIZ `resolve_device`i değiştirir (`upsert_device`e DOKUNMAZ). İmza ve dönüş tablosu `resolve_device_bayat_gorunur.sql` ile
-- BİREBİR aynı → `create or replace` geçerli: drop gerekmez, ikinci aşırı-yükleme (PGRST203) oluşmaz, sahiplik / ACL korunur.
-- Gövde `resolve_device_bayat_gorunur.sql`in AYNISI (30 gün tazelik penceresi, istemci kararı) — tek fark `length(p_code)` koşulu.
-- UYGULAMADAN ÖNCE: canlı tanımı `select pg_get_functiondef('public.resolve_device(text,text)'::regprocedure);` ile oku; bu dosyanın
-- taban hâlinden (bayat_gorunur.sql) farklıysa DUR ve farkı birleştir.
begin;

create or replace function public.resolve_device(p_code text default null, p_device_id text default null)
returns table (device_id text, name text, tunnel_url text, local_ip text, last_seen timestamptz)
language sql security definer set search_path = public as $$
    select d.device_id, d.name, d.tunnel_url, d.local_ip, d.last_seen
    from public.devices d
    where d.last_seen > now() - interval '30 days'
      and ( (p_device_id is not null and d.device_id = p_device_id)
            or (p_code is not null and length(p_code) in (6, 8) and upper(d.pairing_code)=upper(p_code)) )
    order by d.last_seen desc limit 1;
$$;

-- Yetki (idempotent güvence): tablo dökümü kapalı kalır, yalnız anon bu RPC'yi çalıştırır.
revoke all on function public.resolve_device(text,text) from public;
grant execute on function public.resolve_device(text,text) to anon;

commit;
