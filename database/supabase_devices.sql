-- =============================================================================
-- PEMF — Supabase 'devices' tablosu (TEMASSIZ uzaktan erişim için device-registry)
-- =============================================================================
-- Backend (servers/sync_worker._publish_device_registry) bu tabloya cihazın
-- güncel erişim bilgisini (tunnel_url / local_ip / last_seen) device_id ile yazar.
-- Mobil uygulama, aynı WiFi'de cihazı (mDNS) bulamadığında bu tablodan device_id
-- ile güncel tunnel_url'i çekip QR OKUTMADAN uzaktan bağlanır.
--
-- KURULUM: Supabase Dashboard → SQL Editor → bu dosyayı yapıştır → Run.
-- =============================================================================

create table if not exists public.devices (
    device_id  text primary key,          -- get_unique_device_id() (MAC tabanlı, stabil)
    name       text,                       -- "PEMF-Vet" veya PEMF_DEVICE_NAME
    tunnel_url text,                        -- güncel https://...trycloudflare.com (her restart değişir)
    local_ip   text,                       -- LAN IP (aynı WiFi fallback)
    api_port   integer default 8000,
    last_seen  timestamptz default now(),  -- heartbeat (cihaz canlı mı)
    created_at timestamptz default now()
);

-- ── Row Level Security ──────────────────────────────────────────────────────
-- Backend publishable/anon anahtar kullanır. Bağlantı bilgisi düşük-hassasiyetli
-- olduğundan anon upsert + okuma açılır. (Prod'da: backend'e API-key auth + RLS
-- daraltması önerilir.)
alter table public.devices enable row level security;

drop policy if exists devices_anon_select on public.devices;
create policy devices_anon_select on public.devices
    for select using (true);

drop policy if exists devices_anon_insert on public.devices;
create policy devices_anon_insert on public.devices
    for insert with check (true);

drop policy if exists devices_anon_update on public.devices;
create policy devices_anon_update on public.devices
    for update using (true) with check (true);
