-- =============================================================================
-- PEMF — Supabase GÜVENLİ MODEL v2 (Coverage-Audit 2026-07-27, P1 IDOR + tünel-zehirleme)
-- =============================================================================
-- SORUN (v1'de): devices/patients/sessions RPC'leri YETKİ olarak yalnız `device_id`
-- kullanıyordu. device_id = get_unique_device_id() = MAC-türevli, GİZLİ DEĞİL ve
-- /api/health'ten sızıyordu. Sonuç: gömülü anon-key + bir device_id bilen saldırgan
--   • upsert_device(kurban_id, 'https://saldirgan-tunel', ...) → tünel ZEHİRLEME → cihaz DEVRALMA
--   • resolve_patients(kurban_id) → o kliniğin hasta/seans METADATA'sını (tür/frekans/tarih) döker
--   • upsert_patient(kurban_id, sahte) → sahte kayıt enjekte
-- (PII adı/sahibi Fernet-şifreli gider; ama metadata + yazma/devralma yüzeyi açık.)
--
-- ÇÖZÜM (v2): device_id ARTIK yalnız satır-anahtarı. YETKİ = cihaza-özel CAPABILITY-TOKEN
-- (provisyon-sırrı). Cihaz sırrı üretir (SecretsManager DPAPI), HASH'ini bulutta saklar,
-- HER RPC'de sırrı gönderir; RPC bcrypt ile doğrular. Sırrı bilmeyen (anon-key sahibi dahil)
-- ne devralır ne cross-tenant okur. İlk-kayıt = TOFU (trust-on-first-use): ilk provisyon
-- sırrı mühürler; sonrası eşleşme ister.
--
-- ⚠️ KOORDİNE DEPLOY: Bu SQL YENİ imza (ekstra p_secret) getirir + ESKİ imzaları DÜŞÜRÜR.
--    Backend'i (sync_worker) p_secret gönderecek sürümle AYNI ANDA güncelle (aksi halde
--    device-registry/sync geçici kırılır). Backend değişikliği bu commit'te yapıldı.
--
-- KURULUM: Supabase Dashboard → SQL Editor → bu dosyayı yapıştır → Run (idempotent).
-- =============================================================================

create extension if not exists pgcrypto;   -- crypt() + gen_salt('bf') (bcrypt) için

-- ── devices: capability-token sütunu ────────────────────────────────────────
alter table public.devices add column if not exists secret_hash text;

-- ── Ortak doğrulayıcı: (device_id, secret) → geçerli mi ─────────────────────
-- NOT: search_path'e `extensions` eklendi — Supabase'de pgcrypto (crypt/gen_salt) `extensions`
-- şemasında kuruludur; yalnız `public` ile "function crypt does not exist" hatası alınır.
create or replace function public._pemf_verify_device(p_device_id text, p_secret text)
returns boolean language sql security definer set search_path = public, extensions as $$
  select exists(
    select 1 from public.devices d
    where d.device_id = p_device_id
      and d.secret_hash is not null
      and d.secret_hash = crypt(coalesce(p_secret,''), d.secret_hash)
  );
$$;
revoke all on function public._pemf_verify_device(text,text) from public;  -- yalnız RPC'ler içinden

-- ── upsert_device v2: TOFU + secret doğrulama (tünel-zehirlemeyi kapatır) ────
-- Eski imzayı düşür (p_secret'siz) → cutover.
drop function if exists public.upsert_device(text,text,text,text,integer,text);
create or replace function public.upsert_device(
    p_device_id text, p_name text, p_tunnel_url text, p_local_ip text,
    p_api_port integer, p_pairing_code text, p_secret text
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
    insert into public.devices (device_id, name, tunnel_url, local_ip, api_port, pairing_code, secret_hash, last_seen)
    values (p_device_id, p_name, p_tunnel_url, p_local_ip, coalesce(p_api_port,8000), p_pairing_code,
            crypt(p_secret, gen_salt('bf')), now())
    on conflict (device_id) do nothing;   -- yarış: araya insert girdiyse aşağıda doğrulanır
    -- Eğer conflict yüzünden yazılamadıysa (başka insert kazandı) secret'i doğrulayıp güncelle:
    if not found then
      if not public._pemf_verify_device(p_device_id, p_secret) then
        raise exception 'device secret mismatch';
      end if;
      update public.devices set name=p_name, tunnel_url=p_tunnel_url, local_ip=p_local_ip,
        api_port=coalesce(p_api_port,8000), pairing_code=p_pairing_code, last_seen=now()
      where device_id = p_device_id;
    end if;
  else
    -- Mevcut kayıt: sırrı DOĞRULA → yalnız gerçek cihaz günceller
    if v_hash <> crypt(p_secret, v_hash) then
      raise exception 'device secret mismatch';
    end if;
    update public.devices set name=p_name, tunnel_url=p_tunnel_url, local_ip=p_local_ip,
      api_port=coalesce(p_api_port,8000), pairing_code=p_pairing_code, last_seen=now()
    where device_id = p_device_id;
  end if;
end; $$;
revoke all on function public.upsert_device(text,text,text,text,integer,text,text) from public;
grant execute on function public.upsert_device(text,text,text,text,integer,text,text) to anon;

-- NOT: resolve_device DEĞİŞMEDİ — mobil app cihazı PAIRING-KODU (operatörün paylaştığı sır) ile
-- çözer; cihaz-sırrına ihtiyacı yok. Tünel-URL okuması pairing-kodu-gate'li kalır (v1 doğruydu).
-- (Rate-limit: SQL'de değil; Supabase → Auth/Edge Functions rate-limit veya API-gateway ile; not düşüldü.)

-- ── patients/sessions RPC'leri v2: p_secret doğrulaması ─────────────────────
drop function if exists public.upsert_patient(text,jsonb);
create or replace function public.upsert_patient(p_device_id text, p_patient jsonb, p_secret text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public._pemf_verify_device(p_device_id, p_secret) then
    raise exception 'device secret mismatch';
  end if;
  insert into public.patients (id, device_id, name, species, breed, age, weight, owner, vet_contact, created_at, updated_at)
  values (p_patient->>'id', p_device_id, p_patient->>'name', p_patient->>'species', p_patient->>'breed',
          p_patient->>'age', p_patient->>'weight', p_patient->>'owner', p_patient->>'vet_contact',
          p_patient->>'created_at', p_patient->>'updated_at')
  on conflict (id) do update set
    name=excluded.name, species=excluded.species, breed=excluded.breed, age=excluded.age,
    weight=excluded.weight, owner=excluded.owner, vet_contact=excluded.vet_contact, updated_at=excluded.updated_at
  where public.patients.device_id = p_device_id;
end; $$;
grant execute on function public.upsert_patient(text,jsonb,text) to anon;

drop function if exists public.upsert_session(text,jsonb);
create or replace function public.upsert_session(p_device_id text, p_session jsonb, p_secret text)
returns void language plpgsql security definer set search_path = public as $$
begin
  if not public._pemf_verify_device(p_device_id, p_secret) then
    raise exception 'device secret mismatch';
  end if;
  insert into public.treatment_sessions (id, device_id, session_date, start_time, end_time, duration_minutes,
    treatment_mode, target_condition, frequency_hz, intensity_mt, pulse_duration_ms,
    operator_name, patient_name, patient_notes, session_status, created_at)
  values (p_session->>'id', p_device_id, p_session->>'session_date', p_session->>'start_time', p_session->>'end_time',
    (p_session->>'duration_minutes')::int, p_session->>'treatment_mode', p_session->>'target_condition',
    (p_session->>'frequency_hz')::double precision, (p_session->>'intensity_mt')::double precision,
    (p_session->>'pulse_duration_ms')::int, p_session->>'operator_name', p_session->>'patient_name',
    p_session->>'patient_notes', p_session->>'session_status', p_session->>'created_at')
  -- ⚠️ ÇAKIŞMA CİHAZ-KAPSAMLI (2026-08-30 denetimi, çoklu klinik): `id` kliniğin YEREL
  -- SQLite tablosundan gelir ve orada AUTOINCREMENT'tir → her klinik 1,2,3… kullanır.
  -- `on conflict (id)` iken ikinci kliniğin seansı SESSİZCE yazılmıyordu (ne INSERT, ne
  -- UPDATE, ne hata). Anahtar `(device_id, id)` yapıldı; göç:
  -- `supabase/seans_kimligi_bilesik_anahtar.sql`.
  on conflict (device_id, id) do update set
    end_time=excluded.end_time, duration_minutes=excluded.duration_minutes, session_status=excluded.session_status
  where public.treatment_sessions.device_id = p_device_id;
end; $$;
grant execute on function public.upsert_session(text,jsonb,text) to anon;

drop function if exists public.resolve_patients(text);
create or replace function public.resolve_patients(p_device_id text, p_secret text)
returns setof public.patients language plpgsql security definer set search_path = public as $$
begin
  if not public._pemf_verify_device(p_device_id, p_secret) then
    raise exception 'device secret mismatch';
  end if;
  return query select * from public.patients where device_id = p_device_id;
end; $$;
grant execute on function public.resolve_patients(text,text) to anon;

drop function if exists public.resolve_sessions(text);
create or replace function public.resolve_sessions(p_device_id text, p_secret text)
returns setof public.treatment_sessions language plpgsql security definer set search_path = public as $$
begin
  if not public._pemf_verify_device(p_device_id, p_secret) then
    raise exception 'device secret mismatch';
  end if;
  return query select * from public.treatment_sessions where device_id = p_device_id;
end; $$;
grant execute on function public.resolve_sessions(text,text) to anon;

-- =============================================================================
-- SONUÇ: device_id artık yalnız satır-anahtarı; YETKİ cihaz-sırrına (bcrypt-hash) dayanır.
-- Sırrı bilmeyen anon-key sahibi: cihazı DEVRALAMAZ, hasta/seans OKUYAMAZ/YAZAMAZ.
-- =============================================================================
