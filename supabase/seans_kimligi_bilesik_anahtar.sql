-- =================================================================================
-- SEANS KİMLİĞİ ÇAKIŞMASI — ÇOKLU KLİNİKTE SESSİZ VERİ KAYBI
-- Bulundu: 2026-08-30 Supabase denetimi (sahip isteği: "çoklu klinik kullanımını düşün")
-- =================================================================================
--
-- ÖLÇÜLEN DURUM
-- -------------
-- `public.treatment_sessions` birincil anahtarı YALNIZ `id` idi:
--     PRIMARY KEY (id)
-- Ama `id`, kliniğin YEREL SQLite tablosundan gelir ve orada
--     id INTEGER PRIMARY KEY AUTOINCREMENT      (database/treatment_history_db.py:720)
-- yani her klinikte 1, 2, 3, … diye başlar. Canlıdaki tek kaydın id'si düpedüz `2` idi.
--
-- SONUÇ (çoklu klinik):
--     Klinik A → id=1 yazar, GLOBAL anahtarı kaplar
--     Klinik B → id=1 yazmaya çalışır
--                `on conflict (id) do update ... where device_id = p_device_id`
--                → WHERE tutmaz (kayıt A'nın) → UPDATE olmaz
--                → INSERT de olamaz (çakışma) → HATA DA DÖNMEZ
--     Klinik B'nin seansı buluta SESSİZCE yazılmaz.
--
-- ⚠️ Bu bir güvenlik açığı DEĞİL: kimse başkasının verisini okuyamaz ya da ezemez
-- (`_pemf_verify_device` + `where device_id` korumaları sağlam). Bu bir VERİ KAYBI
-- sorunudur ve en kötü yanı SESSİZ olmasıdır — ne istemci ne sunucu bir şey fark eder.
--
-- ⚠️ `public.patients` AYNI DESENDE AMA GÜVENLİ: oradaki `id` UUID
-- (`database/patient_database.py:259` → TEXT PRIMARY KEY; canlıdaki örnek
-- `5819280a-2734-4cfe-a567-12ed23bbec07`). UUID çakışması pratikte imkânsız olduğu için
-- bu göç `patients`e KASITLI olarak DOKUNMAZ — gereksiz şema riski alınmaz.
--
-- ÇÖZÜM
-- -----
-- Anahtarı cihaz-kapsamlı yap: `(device_id, id)`. Böylece her kliniğin id uzayı kendine
-- aittir; A'nın 1'i ile B'nin 1'i farklı satırlardır.
--
-- GERİ ALMA (gerekirse):
--     alter table public.treatment_sessions drop constraint treatment_sessions_pkey;
--     alter table public.treatment_sessions add constraint treatment_sessions_pkey primary key (id);
--     -- ve `upsert_session`ı `on conflict (id)` haline döndür
--   ⚠️ Geri alma, iki klinikte aynı id varsa BAŞARISIZ olur (tekillik bozulur) — o noktadan
--   sonra geri dönüş, çakışan satırların elle ayıklanmasını gerektirir.

begin;

-- 1) Birincil anahtarı cihaz-kapsamlı yap ------------------------------------------
--    NOT: `id` ve `device_id` zaten NOT NULL (ölçüldü) → ek kısıt gerekmez.
alter table public.treatment_sessions drop constraint if exists treatment_sessions_pkey;
alter table public.treatment_sessions add constraint treatment_sessions_pkey primary key (device_id, id);

-- 2) upsert_session: çakışma artık CİHAZ İÇİNDE değerlendirilir --------------------
--    `where ... device_id = p_device_id` KORUNUYOR: bileşik anahtarla teknik olarak
--    gereksiz hale geldi ama savunma katmanı olarak durur (birincil anahtar ileride
--    yeniden değişirse cross-tenant ezme yine engellenmiş olur).
--    ⚠️ ESKİ İMZAYI ÖNCE DÜŞÜR (kapı: test_supabase_sql_invariants). Depoda `upsert_session`
--    2-parametreli bir sürümle de tanımlanmıştı (`database/supabase_patients.sql`). PostgreSQL
--    aynı adı farklı arite ile AŞIRI YÜKLER; ikisi birden dururken PostgREST çağrıyı
--    çözemez ve `PGRST203` döner. Düşürme, yeni imzayı getiren betiğin İÇİNDE olmalı ki bu
--    dosya TEK BAŞINA çalıştırıldığında da güvenli olsun.
--    (Canlıda ölçüldü: şu an yalnız 3-parametreli imza var — bu satır oradaki durumu
--    değiştirmez, dosyanın kendi kendine yeterliliğini sağlar.)
drop function if exists public.upsert_session(text, jsonb);

create or replace function public.upsert_session(p_device_id text, p_session jsonb, p_secret text)
returns void
language plpgsql
security definer
set search_path to 'public'
as $function$
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
end; $function$;

commit;
