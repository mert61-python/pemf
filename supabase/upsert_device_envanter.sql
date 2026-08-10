-- FİLO ENVANTERİ — upsert_device'e sürüm alanları (2026-08-09 denetimi, Tier 2)
-- Author: mertaygn, cglrgrkn
--
-- NEDEN: bir bobin-güvenliği hatası bulunduğunda "hangi klinik hangi sürümde?" sorusunun cevabı
-- YOKTU. Cihaz kaydı 60 sn'de bir heartbeat gönderiyor ama içinde sürüm bilgisi hiç yoktu;
-- `rollout: 0` yalnız YENİ kurulumları durdurur, sahadaki cihazlara dokunmaz. Geri çağırma
-- yapılabilmesi için önce ENVANTER gerekir.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- ⚠️ BU DOSYANIN İLK HÂLİ ÜRETİMİ KIRARDI (2026-08-10'da dağıtımdan ÖNCE yakalandı). Üç kusur:
--
--   1) İMZA ÇAKIŞMASI. PostgreSQL fonksiyonları (ad + argüman tipleri) ile anahtarlanır;
--      `create or replace` 11 parametreyle çağrılınca mevcut 7-parametreli fonksiyonu
--      DEĞİŞTİRMEZ, YANINA İKİNCİSİNİ EKLER. Bundan sonra 7 argümanlı her çağrı (geriye-uyum
--      yolu ve güncellenmemiş her backend) İKİ adaya birden uyar → PostgREST PGRST203
--      ("could not choose the best candidate") → heartbeat TAMAMEN kırılır, uzaktan erişim ölür.
--      Yani dosya, tam da önlemeyi iddia ettiği şeyi yapardı.
--
--   2) GÜVENLİK GERİLEMESİ. İlk hâl sırrı `device_secret` sütununda DÜZ METİN karşılaştırıyordu.
--      Yayındaki v2 (`database/supabase_secure_v2.sql`) ise bcrypt kullanır: `secret_hash` +
--      `crypt()`, TOFU mührü ve yarış (race) dalı. Dosya çalışsaydı capability-token modeli
--      hash'liden düz-metne düşerdi.
--
--   3) YETKİ KAYBI. Yeni imza için `grant execute ... to anon` yoktu → anon (cihaz) yeni
--      fonksiyonu zaten çağıramazdı.
--
-- Bu sürüm, YAYINDAKİ v2 gövdesini BİREBİR korur ve yalnız dört sürüm sütununu ekler.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- ⚠️ GERİYE UYUM: backend yeni parametreleri gönderir, RPC kabul etmezse ESKİ imzaya düşer
-- (bkz. servers/sync_worker.py). Yani bu SQL dağıtılmadan da sistem çalışır — yalnızca envanter
-- boş kalır. Dağıtıldığı anda alanlar dolmaya başlar; backend değişikliği GEREKMEZ.
--
-- ⚠️ KISA KESİNTİ: eski fonksiyon düşürülüp yenisi yaratılana kadar (milisaniyeler) araya denk
-- gelen bir heartbeat başarısız olur. Backend 60 sn sonra yeniden dener — kalıcı etki yoktur.
--
-- KULLANIM: Supabase → SQL Editor → bu dosyanın TAMAMINI yapıştır → Run. İdempotenttir.

begin;

-- ── 1) Kolonlar (idempotent) ────────────────────────────────────────────────────────────────
alter table public.devices add column if not exists app_version       text;
alter table public.devices add column if not exists launcher_version  text;
alter table public.devices add column if not exists base_sha          text;
alter table public.devices add column if not exists at_rest_encrypted boolean;

-- ── 2) upsert_device'in TÜM eski aşırı-yüklemelerini düşür ──────────────────────────────────
-- Sabit bir imza yazmak yerine kataloğu geziyoruz: geçmişte 6 ve 7 parametreli sürümler
-- yayınlandı (bkz. supabase_devices.sql v1 → supabase_secure_v2.sql v2). Elle yazılan tek bir
-- `drop ... (text,...)` satırı, bilinmeyen bir imzayı diskte bırakır ve çakışma sürer.
do $$
declare r record;
begin
  for r in
    select p.oid::regprocedure as imza
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname = 'upsert_device'
  loop
    execute format('drop function %s', r.imza);
    raise notice 'dusuruldu: %', r.imza;
  end loop;
end $$;

-- ── 3) TEK fonksiyon: v2 gövdesi + sürüm alanları ───────────────────────────────────────────
-- ⚠️ `search_path = public, extensions`: Supabase'de pgcrypto (`crypt`/`gen_salt`) `extensions`
-- şemasındadır; yalnız `public` ile "function crypt does not exist" alınır (v2'de öğrenildi).
create function public.upsert_device(
    p_device_id         text,
    p_name              text,
    p_tunnel_url        text,
    p_local_ip          text,
    p_api_port          integer,
    p_pairing_code      text,
    p_secret            text,
    p_app_version       text    default null,
    p_launcher_version  text    default null,
    p_base_sha          text    default null,
    p_at_rest_encrypted boolean default null
) returns void
language plpgsql security definer set search_path = public, extensions as $$
declare v_hash text;
begin
  if p_secret is null or length(p_secret) < 16 then
    raise exception 'device secret required (>=16)';
  end if;
  select secret_hash into v_hash from public.devices where device_id = p_device_id;
  if v_hash is null then
    -- TOFU: bu device_id'yi İLK provisyonlayan sahiplenir → sırrı mühürle
    insert into public.devices (device_id, name, tunnel_url, local_ip, api_port, pairing_code,
                                secret_hash, app_version, launcher_version, base_sha,
                                at_rest_encrypted, last_seen)
    values (p_device_id, p_name, p_tunnel_url, p_local_ip, coalesce(p_api_port,8000), p_pairing_code,
            crypt(p_secret, gen_salt('bf')), p_app_version, p_launcher_version, p_base_sha,
            p_at_rest_encrypted, now())
    on conflict (device_id) do nothing;   -- yarış: araya insert girdiyse aşağıda doğrulanır
    -- Eğer conflict yüzünden yazılamadıysa (başka insert kazandı) secret'i doğrulayıp güncelle:
    if not found then
      if not public._pemf_verify_device(p_device_id, p_secret) then
        raise exception 'device secret mismatch';
      end if;
      update public.devices set name=p_name, tunnel_url=p_tunnel_url, local_ip=p_local_ip,
        api_port=coalesce(p_api_port,8000), pairing_code=p_pairing_code,
        -- ⚠️ Sürüm alanları YALNIZ dolu gelirse yazılır: sürüm göndermeyen eski bir backend'in
        -- heartbeat'i mevcut envanteri SİLMEMELİ, aksi hâlde filo görünürlüğü yanıp söner.
        app_version       = coalesce(p_app_version,       devices.app_version),
        launcher_version  = coalesce(p_launcher_version,  devices.launcher_version),
        base_sha          = coalesce(p_base_sha,          devices.base_sha),
        at_rest_encrypted = coalesce(p_at_rest_encrypted, devices.at_rest_encrypted),
        last_seen=now()
      where device_id = p_device_id;
    end if;
  else
    -- Mevcut kayıt: sırrı DOĞRULA → yalnız gerçek cihaz günceller
    if v_hash <> crypt(p_secret, v_hash) then
      raise exception 'device secret mismatch';
    end if;
    update public.devices set name=p_name, tunnel_url=p_tunnel_url, local_ip=p_local_ip,
      api_port=coalesce(p_api_port,8000), pairing_code=p_pairing_code,
      app_version       = coalesce(p_app_version,       devices.app_version),
      launcher_version  = coalesce(p_launcher_version,  devices.launcher_version),
      base_sha          = coalesce(p_base_sha,          devices.base_sha),
      at_rest_encrypted = coalesce(p_at_rest_encrypted, devices.at_rest_encrypted),
      last_seen=now()
    where device_id = p_device_id;
  end if;
end; $$;

-- ── 4) Yetki (v2 ile AYNI): public'ten al, yalnız anon'a ver ────────────────────────────────
revoke all on function public.upsert_device(text,text,text,text,integer,text,text,text,text,text,boolean) from public;
grant execute on function public.upsert_device(text,text,text,text,integer,text,text,text,text,text,boolean) to anon;

-- ── 5) KAPI: tek bir aşırı-yükleme kaldı mı? ────────────────────────────────────────────────
-- Bu kontrol olmadan, düşürülemeyen bir imza sessizce kalır ve 7 argümanlı çağrılar
-- PGRST203 ile ölürdü — üstelik hata SAHADA, heartbeat sustuğunda görünürdü.
do $$
declare n int;
begin
  select count(*) into n
    from pg_proc p join pg_namespace ns on ns.oid = p.pronamespace
   where ns.nspname = 'public' and p.proname = 'upsert_device';
  if n <> 1 then
    raise exception 'upsert_device % adet asiri-yukleme birakti — 7 argumanli cagrilar BELIRSIZ kalir (PGRST203)', n;
  end if;
  raise notice 'OK: upsert_device tek imza';
end $$;

commit;

-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- DOĞRULAMA (ayrıca çalıştırın)
--
-- a) İmza gerçekten tek ve 11 parametreli mi:
--    select p.oid::regprocedure from pg_proc p join pg_namespace n on n.oid=p.pronamespace
--     where n.nspname='public' and p.proname='upsert_device';
--
-- b) Envanter dolmaya başladı mı (bir cihaz heartbeat attıktan ~60 sn sonra):
--    select device_id, name, app_version, launcher_version, base_sha,
--           at_rest_encrypted, last_seen
--      from public.devices order by last_seen desc limit 20;
--
-- c) GERİ ÇAĞIRMA sorgusu — "kim etkileniyor?" (örn. 1.9.16'dan eski client, son 7 gün):
--    select device_id, name, app_version, launcher_version, last_seen
--      from public.devices
--     where last_seen > now() - interval '7 days'
--       and (launcher_version is null or launcher_version < '1.9.16')
--     order by last_seen desc;
--
-- d) At-rest şifrelemesi KAPALI çalışan klinik var mı (KVKK/veri riski):
--    select device_id, name, at_rest_encrypted, last_seen
--      from public.devices where at_rest_encrypted is not true order by last_seen desc;
-- ═════════════════════════════════════════════════════════════════════════════════════════════
