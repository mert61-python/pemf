-- =============================================================================
-- GERİ ALMA — `supabase_profil.sql` (CH2 · S-SG.8 / Y151)
-- =============================================================================
--
-- NE YAPAR: `upsert_session` ve `upsert_patient`i `supabase_profil.sql` ÖNCESİ gövdelerine döndürür (bulut artık profil YAZMAZ).
-- Gövdeler birebir: `upsert_session` → `../../../supabase/seans_kimligi_bilesik_anahtar.sql`, `upsert_patient` → `supabase_secure_v2.sql`.
-- Yetkiler rol rol aynen yeniden yazılır (yalnız anon).
--
-- NE YAPMAZ: `profil` kolonlarını SİLMEZ — eklemeli kolon zararsızdır ve bulutta biriken profil bilgisi kaybolmaz. Cihazlar bu dosyadan
-- sonra da çalışır: eski fonksiyon yükteki `profil`i yok sayar; resolve satırları kolonu taşımaya devam ettiğinden yeni profilli kayıtlar
-- bulutta '' kalır, cihaz bunları kayıt başına süreç ömründe en fazla BİR KEZ yeniden gönderir (sel yok), yerel profil ezilmez.
-- Kolonları da kaldırmak gerekirse (bulut profil bilgisi KALICI silinir — önce sahiple konuşun), bu dosyadan SONRA ayrıca:
--     alter table public.treatment_sessions drop column if exists profil;
--     alter table public.patients drop column if exists profil;
--
-- UYGULAMA (sahiple): python scripts/supabase_sql.py --dosya apps/backend/database/supabase_profil_geri_al.sql --yaz
-- İdempotent, TEK İŞLEM.

begin;

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
  on conflict (device_id, id) do update set
    end_time=excluded.end_time, duration_minutes=excluded.duration_minutes, session_status=excluded.session_status
  where public.treatment_sessions.device_id = p_device_id;
end; $$;

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

revoke all on function public.upsert_session(text, jsonb, text) from public, authenticated;
revoke all on function public.upsert_patient(text, jsonb, text) from public, authenticated;
grant execute on function public.upsert_session(text, jsonb, text) to anon;
grant execute on function public.upsert_patient(text, jsonb, text) to anon;

notify pgrst, 'reload schema';

commit;
