-- =============================================================================
-- PROFİL BULUTA — seans ve hasta / denek kaydının ARAYÜZ PROFİLİ (CH2 · S-SG.8 / sahip kararı Y151, 2026-10-15)
-- =============================================================================
--
-- NEDEN: SG.G1 (2026-10-14) her yeni seansı ve hasta / denek kaydını açıldığı arayüz profiliyle (veterinarian / researcher /
-- pet_owner) YEREL veritabanına yazar; liste / rapor / KPI profile göre süzülür. Bulut kopyasında bu bilgi yoktu → buluttan inen
-- kayıt profilsiz iniyor ve türetme kuralıyla (araştırma AI Pro seansı → araştırma, değilse veteriner) görünüyordu: araştırma
-- profilinde açılmış sıradan bir seans başka cihaza / yeniden kuruluma VETERİNER diye dönebilirdi.
--
-- NE YAPAR (yalnız EKLEMELİ — hiçbir satır / kolon / imza silinmez):
--   1) `treatment_sessions.profil` ve `patients.profil` — `text not null default ''` (var olan satırlar '' alır = "bilinmiyor",
--      okumada türetilir; profil kişisel veri DEĞİLDİR, şifresiz üst veridir).
--   2) `upsert_session` / `upsert_patient` AYNI İMZAYLA yeniden tanımlanır: yükteki (jsonb) `profil` anahtarı isteğe bağlı
--      parametredir — anahtarı göndermeyen eski cihaz değişmeden çalışır, yeni aşırı-yük (PGRST203) YOKTUR. Değer küçük harfe
--      çevrilir; bilinmeyen değer '' olur; buluttan BOŞ gelen profil bulutta DOLU değeri EZMEZ. `_pemf_verify_device` sır doğrulaması
--      ve `where device_id = p_device_id` cross-tenant koruması AYNEN durur.
--   3) Yetkiler rol rol yazılır (`revoke … from public` anon / authenticated yetkisini KALDIRMAZ — 2026-08-21 dersi): yalnız `anon`
--      (cihaz kendi sırrıyla kimliklenir), `public` ve `authenticated` geri alınır. `resolve_sessions` / `resolve_patients`
--      `select *` döndürdüğü için yeni kolonu kendiliğinden taşır — DEĞİŞTİRİLMEZ.
--
-- CİHAZ TARAFI (`apps/backend/servers/sync_worker.py`) bu dosya uygulanmadan da çalışır: eski fonksiyon yükteki `profil`i yok sayar,
-- resolve satırında `profil` anahtarı olmadığından yerel profil ezilmez ve yeniden gönderme yapılmaz. Dosya uygulanınca resolve
-- satırları `profil` taşır; daha önce profilsiz gönderilmiş kayıtlar kayıt başına BİR KEZ yeniden gönderilir (geri doldurma).
-- Kapı: `tests/test_CH2_profil_BULUTA_S_SG8.py`.
--
-- SIRA: `supabase_secure_v2.sql` + `../../../supabase/seans_kimligi_bilesik_anahtar.sql` uygulanmış olmalı (aşağıdaki kapı denetler).
-- UYGULAMA (yayın hazırlığında, SAHİPLE): python scripts/supabase_sql.py --dosya apps/backend/database/supabase_profil.sql --yaz
-- GERİ ALMA (veri silmez, fonksiyonları eski gövdeye döndürür): `supabase_profil_geri_al.sql`.
-- İdempotent: tekrar çalıştırmak aynı sonucu verir. TEK İŞLEM: herhangi bir adım düşerse hiçbiri uygulanmaz.

begin;

-- 0) ÖN KOŞUL KAPISI — v2 (cihaz sırrı) ve seans bileşik anahtarı yoksa HİÇBİR ŞEY yapmadan dur.
do $$
declare
  v_pk text[];
begin
  if to_regprocedure('public._pemf_verify_device(text,text)') is null then
    raise exception 'supabase_profil.sql DURDU: once supabase_secure_v2.sql uygulanmali (public._pemf_verify_device yok)';
  end if;
  select array_agg(a.attname::text order by a.attname::text) into v_pk
    from pg_constraint c
    join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any (c.conkey)
   where c.conrelid = 'public.treatment_sessions'::regclass and c.contype = 'p';
  if v_pk is distinct from array['device_id', 'id'] then
    raise exception 'supabase_profil.sql DURDU: once supabase/seans_kimligi_bilesik_anahtar.sql uygulanmali (treatment_sessions birincil anahtari: %)', v_pk;
  end if;
end $$;

-- 1) EKLEMELİ kolonlar
alter table public.treatment_sessions add column if not exists profil text not null default '';
alter table public.patients add column if not exists profil text not null default '';

-- 2) upsert_session — gövde `supabase/seans_kimligi_bilesik_anahtar.sql` ile AYNI + profil
create or replace function public.upsert_session(p_device_id text, p_session jsonb, p_secret text)
returns void language plpgsql security definer set search_path = public as $$
declare
  v_profil text := lower(btrim(coalesce(p_session->>'profil', '')));
begin
  if not public._pemf_verify_device(p_device_id, p_secret) then
    raise exception 'device secret mismatch';
  end if;
  if v_profil not in ('veterinarian', 'researcher', 'pet_owner') then
    v_profil := '';
  end if;
  insert into public.treatment_sessions (id, device_id, session_date, start_time, end_time, duration_minutes,
    treatment_mode, target_condition, frequency_hz, intensity_mt, pulse_duration_ms,
    operator_name, patient_name, patient_notes, session_status, created_at, profil)
  values (p_session->>'id', p_device_id, p_session->>'session_date', p_session->>'start_time', p_session->>'end_time',
    (p_session->>'duration_minutes')::int, p_session->>'treatment_mode', p_session->>'target_condition',
    (p_session->>'frequency_hz')::double precision, (p_session->>'intensity_mt')::double precision,
    (p_session->>'pulse_duration_ms')::int, p_session->>'operator_name', p_session->>'patient_name',
    p_session->>'patient_notes', p_session->>'session_status', p_session->>'created_at', v_profil)
  on conflict (device_id, id) do update set
    end_time=excluded.end_time, duration_minutes=excluded.duration_minutes, session_status=excluded.session_status,
    profil=case when excluded.profil <> '' then excluded.profil else public.treatment_sessions.profil end
  where public.treatment_sessions.device_id = p_device_id;
end; $$;

-- 3) upsert_patient — gövde `supabase_secure_v2.sql` ile AYNI + profil
create or replace function public.upsert_patient(p_device_id text, p_patient jsonb, p_secret text)
returns void language plpgsql security definer set search_path = public as $$
declare
  v_profil text := lower(btrim(coalesce(p_patient->>'profil', '')));
begin
  if not public._pemf_verify_device(p_device_id, p_secret) then
    raise exception 'device secret mismatch';
  end if;
  if v_profil not in ('veterinarian', 'researcher', 'pet_owner') then
    v_profil := '';
  end if;
  insert into public.patients (id, device_id, name, species, breed, age, weight, owner, vet_contact, created_at, updated_at, profil)
  values (p_patient->>'id', p_device_id, p_patient->>'name', p_patient->>'species', p_patient->>'breed',
          p_patient->>'age', p_patient->>'weight', p_patient->>'owner', p_patient->>'vet_contact',
          p_patient->>'created_at', p_patient->>'updated_at', v_profil)
  on conflict (id) do update set
    name=excluded.name, species=excluded.species, breed=excluded.breed, age=excluded.age,
    weight=excluded.weight, owner=excluded.owner, vet_contact=excluded.vet_contact, updated_at=excluded.updated_at,
    profil=case when excluded.profil <> '' then excluded.profil else public.patients.profil end
  where public.patients.device_id = p_device_id;
end; $$;

-- 4) Yetkiler — ROL ROL (yalnız cihaz = anon)
revoke all on function public.upsert_session(text, jsonb, text) from public, authenticated;
revoke all on function public.upsert_patient(text, jsonb, text) from public, authenticated;
grant execute on function public.upsert_session(text, jsonb, text) to anon;
grant execute on function public.upsert_patient(text, jsonb, text) to anon;

-- 5) PostgREST şema önbelleği (resolve_* yeni kolonu hemen taşısın)
notify pgrst, 'reload schema';

commit;
