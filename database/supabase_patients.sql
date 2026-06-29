-- =============================================================================
-- PEMF — Bulut patients + treatment_sessions GÜVENLİ MODEL (P1 audit 2026-06-28)
-- =============================================================================
-- SORUN: patients/treatment_sessions bulut tablolarinda RLS YOKtu → gomulu anon
-- anahtarla TAM SELECT/INSERT (cross-tenant okuma + zehirleme). PII Fernet-sifreli
-- gider ama metadata + yazma yuzeyi aciktiir. Bu dosya supabase_devices.sql ile AYNI
-- modeli (RLS + SECURITY DEFINER RPC, anon'a dogrudan tablo erisimi YOK) uygular.
--
-- KULLANIM: Supabase SQL Editor'de bir kez calistir. Bulut HASTA SYNC'i YALNIZ
-- PEMF_CLOUD_PATIENT_SYNC=1 iken aktiftir (varsayilan 0 = bulut sync KAPALI).
-- NOT: name/owner/vet_contact gibi PII alanlari LOKALDE Fernet ile SIFRELI saklanir
-- ve buluta da SIFRELI (enc) gider; bulut hicbir zaman duz-metin PII gormez.
-- =============================================================================

-- 1) Tablolar (idempotent) — device_id ile cross-tenant ayrim
create table if not exists public.patients (
  id           text primary key,
  device_id    text not null,
  name         text,         -- Fernet-sifreli (enc)
  species      text,
  breed        text,
  age          text,
  weight       text,
  owner        text,         -- Fernet-sifreli (enc)
  vet_contact  text,         -- Fernet-sifreli (enc)
  created_at   text,
  updated_at   text
);
create index if not exists idx_patients_device on public.patients(device_id);

create table if not exists public.treatment_sessions (
  id               text primary key,
  device_id        text not null,
  session_date     text,
  start_time       text,
  end_time         text,
  duration_minutes integer,
  treatment_mode   text,
  target_condition text,
  frequency_hz     double precision,
  intensity_mt     double precision,
  pulse_duration_ms integer,
  operator_name    text,     -- bulutta NULL (PII lokal kalir)
  patient_name     text,     -- bulutta NULL
  patient_notes    text,     -- bulutta NULL
  session_status   text,
  created_at       text
);
create index if not exists idx_sessions_device on public.treatment_sessions(device_id);

-- 2) RLS AC + anon'a DOGRUDAN tablo erisimi VERME (policy yok = erisim yok)
alter table public.patients            enable row level security;
alter table public.treatment_sessions  enable row level security;
revoke all on public.patients           from anon;
revoke all on public.treatment_sessions from anon;

-- 3) SECURITY DEFINER RPC'ler — device_id SUNUCU-TARAFI zorlanir (client zorlamaz)
create or replace function public.upsert_patient(p_device_id text, p_patient jsonb)
returns void language plpgsql security definer set search_path = public as $$
begin
  insert into public.patients (id, device_id, name, species, breed, age, weight, owner, vet_contact, created_at, updated_at)
  values (
    p_patient->>'id', p_device_id, p_patient->>'name', p_patient->>'species', p_patient->>'breed',
    p_patient->>'age', p_patient->>'weight', p_patient->>'owner', p_patient->>'vet_contact',
    p_patient->>'created_at', p_patient->>'updated_at'
  )
  on conflict (id) do update set
    name=excluded.name, species=excluded.species, breed=excluded.breed, age=excluded.age,
    weight=excluded.weight, owner=excluded.owner, vet_contact=excluded.vet_contact, updated_at=excluded.updated_at
  where public.patients.device_id = p_device_id;  -- yalniz KENDI kaydini guncelle (tenant izolasyon)
end; $$;

create or replace function public.upsert_session(p_device_id text, p_session jsonb)
returns void language plpgsql security definer set search_path = public as $$
begin
  insert into public.treatment_sessions (id, device_id, session_date, start_time, end_time, duration_minutes,
    treatment_mode, target_condition, frequency_hz, intensity_mt, pulse_duration_ms,
    operator_name, patient_name, patient_notes, session_status, created_at)
  values (
    p_session->>'id', p_device_id, p_session->>'session_date', p_session->>'start_time', p_session->>'end_time',
    (p_session->>'duration_minutes')::int, p_session->>'treatment_mode', p_session->>'target_condition',
    (p_session->>'frequency_hz')::double precision, (p_session->>'intensity_mt')::double precision,
    (p_session->>'pulse_duration_ms')::int, p_session->>'operator_name', p_session->>'patient_name',
    p_session->>'patient_notes', p_session->>'session_status', p_session->>'created_at'
  )
  on conflict (id) do update set
    end_time=excluded.end_time, duration_minutes=excluded.duration_minutes, session_status=excluded.session_status
  where public.treatment_sessions.device_id = p_device_id;
end; $$;

-- PULL: yalniz BU cihazin kayitlari (anon dogrudan SELECT yapamaz)
create or replace function public.resolve_patients(p_device_id text)
returns setof public.patients language sql security definer set search_path = public as $$
  select * from public.patients where device_id = p_device_id;
$$;

create or replace function public.resolve_sessions(p_device_id text)
returns setof public.treatment_sessions language sql security definer set search_path = public as $$
  select * from public.treatment_sessions where device_id = p_device_id;
$$;

-- 4) RPC'leri anon'a ac (yalniz bu 4 fonksiyon; tablolar kapali)
grant execute on function public.upsert_patient(text, jsonb)   to anon;
grant execute on function public.upsert_session(text, jsonb)   to anon;
grant execute on function public.resolve_patients(text)        to anon;
grant execute on function public.resolve_sessions(text)        to anon;
