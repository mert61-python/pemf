-- FİLO ENVANTERİ — upsert_device'e sürüm alanları (2026-08-09 denetimi, Tier 2)
-- Author: mertaygn, cglrgrkn
--
-- NEDEN: bir bobin-güvenliği hatası bulunduğunda "hangi klinik hangi sürümde?" sorusunun cevabı
-- YOKTU. Cihaz kaydı 60 sn'de bir heartbeat gönderiyor ama içinde sürüm bilgisi hiç yoktu;
-- `rollout: 0` yalnız YENİ kurulumları durdurur, sahadaki cihazlara dokunmaz. Geri çağırma
-- yapılabilmesi için önce ENVANTER gerekir.
--
-- ⚠️ GERİYE UYUM: backend yeni parametreleri gönderir, RPC kabul etmezse ESKİ imzaya düşer
-- (bkz. servers/sync_worker.py). Yani bu SQL dağıtılmadan da sistem çalışır — yalnızca envanter
-- boş kalır. Dağıtıldığı anda alanlar dolmaya başlar; backend değişikliği GEREKMEZ.
--
-- KULLANIM: Supabase → SQL Editor → bu dosyayı çalıştır.

-- 1) Kolonlar (idempotent)
alter table public.devices add column if not exists app_version       text;
alter table public.devices add column if not exists launcher_version  text;
alter table public.devices add column if not exists base_sha          text;
alter table public.devices add column if not exists at_rest_encrypted boolean;

-- 2) RPC — ESKİ imza KORUNUR (yeni parametreler DEFAULT'lu).
--    Böylece güncellenmemiş bir backend de aynı fonksiyonu çağırmaya devam eder.
create or replace function public.upsert_device(
    p_device_id         text,
    p_name              text,
    p_tunnel_url        text,
    p_local_ip          text,
    p_api_port          int,
    p_pairing_code      text,
    p_secret            text,
    p_app_version       text    default null,
    p_launcher_version  text    default null,
    p_base_sha          text    default null,
    p_at_rest_encrypted boolean default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    v_mevcut_sir text;
begin
    -- TOFU mührü: cihaz-id bulutta BAŞKA bir sırla mühürlenmişse yazma (cross-tenant koruma).
    select device_secret into v_mevcut_sir from public.devices where device_id = p_device_id;
    if v_mevcut_sir is not null and v_mevcut_sir <> p_secret then
        raise exception 'device secret mismatch';
    end if;

    insert into public.devices as d (
        device_id, name, tunnel_url, local_ip, api_port, pairing_code, device_secret,
        app_version, launcher_version, base_sha, at_rest_encrypted, last_seen
    ) values (
        p_device_id, p_name, p_tunnel_url, p_local_ip, p_api_port, p_pairing_code, p_secret,
        p_app_version, p_launcher_version, p_base_sha, p_at_rest_encrypted, now()
    )
    on conflict (device_id) do update set
        name             = excluded.name,
        tunnel_url       = excluded.tunnel_url,
        local_ip         = excluded.local_ip,
        api_port         = excluded.api_port,
        pairing_code     = excluded.pairing_code,
        -- ⚠️ Sürüm alanları YALNIZ dolu gelirse güncellenir: eski bir backend (alan göndermeyen)
        -- heartbeat atınca mevcut envanteri SİLMEMELİ, aksi hâlde filo görünürlüğü yanıp söner.
        app_version       = coalesce(excluded.app_version,       d.app_version),
        launcher_version  = coalesce(excluded.launcher_version,  d.launcher_version),
        base_sha          = coalesce(excluded.base_sha,          d.base_sha),
        at_rest_encrypted = coalesce(excluded.at_rest_encrypted, d.at_rest_encrypted),
        last_seen        = now();
end;
$$;

-- 3) Geri çağırma sorgusu — "kim etkileniyor?"
--    Örnek: 1.9.14'ten eski client çalıştıran ve son 7 gün içinde görülen klinikler.
--
--    select device_id, name, app_version, launcher_version, base_sha,
--           at_rest_encrypted, last_seen
--      from public.devices
--     where last_seen > now() - interval '7 days'
--       and (launcher_version is null or launcher_version < '1.9.14')
--     order by last_seen desc;
