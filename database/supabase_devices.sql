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
    device_id    text primary key,          -- get_unique_device_id() (MAC tabanlı, stabil)
    name         text,                       -- "PEMF-Vet" veya PEMF_DEVICE_NAME
    tunnel_url   text,                        -- güncel https://...trycloudflare.com (her restart değişir)
    local_ip     text,                       -- LAN IP (aynı WiFi fallback)
    api_port     integer default 8000,
    pairing_code text,                        -- kalıcı 6 haneli eşleştirme kodu (get_pairing_code())
    last_seen    timestamptz default now(),  -- heartbeat (cihaz canlı mı)
    created_at   timestamptz default now()
);

-- Mevcut (eski) kurulumlar için: tablo zaten varsa pairing_code sütununu ekle.
-- Bu satır idempotent'tir (tekrar çalıştırılabilir). Backend, bu sütun YOKSA
-- pairing_code'suz upsert'e otomatik düşer; yine de kodu yayınlamak için ekleyin.
alter table public.devices add column if not exists pairing_code text;

-- ── Row Level Security ──────────────────────────────────────────────────────
-- GÜVENLİK MODELİ (sertleştirilmiş):
-- RLS açık kalır. ANON ROLÜ TABLOYU DÖKEMEZ (SELECT politikası kaldırıldı). Cihaz
-- erişim bilgisini (tunnel_url/local_ip) yalnız aşağıdaki resolve_device() RPC'si
-- üzerinden, TAM pairing_code veya TAM device_id ile TEK satır olarak verir.
-- Böylece anon publishable anahtara sahip biri tüm cihazların tünel URL'lerini
-- listeleyip cross-tenant sızdıramaz.
alter table public.devices enable row level security;

-- Cross-tenant SELECT sızıntısını kapatır: anon doğrudan tabloyu okuyamaz.
-- (YENİDEN OLUŞTURULMAZ — okuma yalnız resolve_device() RPC'si ile yapılır.)
drop policy if exists devices_anon_select on public.devices;

-- YAZMA artık DOĞRUDAN tablo policy'si ile DEĞİL, aşağıdaki upsert_device() SECURITY
-- DEFINER RPC'si ile yapılır (RLS'i güvenli aşar). Anon'a doğrudan tablo INSERT/UPDATE
-- VERİLMEZ → tunnel poisoning + sahte-cihaz ekleme yüzeyi kapanır. Anon yalnız iki RPC'yi
-- (resolve_device = okuma, upsert_device = yazma) çalıştırır; tabloya doğrudan erişemez.
-- (NOT: anon-write policy'leri bilinçli olarak OLUŞTURULMUYOR; eski kurulumda varsa kaldırılır.)
drop policy if exists devices_anon_insert on public.devices;
drop policy if exists devices_anon_update on public.devices;

-- ── Güvenli okuma RPC'si (SECURITY DEFINER) ─────────────────────────────────
-- Anon tabloyu döküremediği için cihazı yalnız bu fonksiyonla çözer.
-- Yalnız TAM device_id VEYA TAM 6-haneli pairing_code (büyük/küçük harf duyarsız)
-- ile eşleşen, TAZE (last_seen > now()-5dk) TEK satırı döner. Parça/önek/joker yok.
-- SECURITY DEFINER + sabit search_path: RLS'i baypas eder ama yalnız bu dar sorguyla.
create or replace function public.resolve_device(p_code text default null, p_device_id text default null)
returns table (device_id text, name text, tunnel_url text, local_ip text, last_seen timestamptz)
language sql security definer set search_path = public as $$
    select d.device_id, d.name, d.tunnel_url, d.local_ip, d.last_seen
    from public.devices d
    where d.last_seen > now() - interval '5 minutes'
      and ( (p_device_id is not null and d.device_id = p_device_id)
            or (p_code is not null and length(p_code)=6 and upper(d.pairing_code)=upper(p_code)) )
    order by d.last_seen desc limit 1;
$$;

-- Fonksiyon yürütme yetkisi: önce herkesten al, yalnız anon'a ver (en az ayrıcalık).
revoke all on function public.resolve_device(text,text) from public;
grant execute on function public.resolve_device(text,text) to anon;

-- ── Güvenli YAZMA RPC'si (SECURITY DEFINER) ─────────────────────────────────
-- Backend (publishable/anon anahtar) registry'yi YALNIZ bu fonksiyonla yazar.
-- SECURITY DEFINER → RLS'i sahibi yetkisiyle aşar; anon'a doğrudan tablo INSERT/UPDATE
-- vermeye gerek kalmaz (dump + poisoning yüzeyi kapalı). last_seen heartbeat now() ile.
create or replace function public.upsert_device(
    p_device_id text, p_name text, p_tunnel_url text, p_local_ip text,
    p_api_port integer, p_pairing_code text
) returns void
language sql security definer set search_path = public as $$
    insert into public.devices (device_id, name, tunnel_url, local_ip, api_port, pairing_code, last_seen)
    values (p_device_id, p_name, p_tunnel_url, p_local_ip, coalesce(p_api_port, 8000), p_pairing_code, now())
    on conflict (device_id) do update set
        name        = excluded.name,
        tunnel_url  = excluded.tunnel_url,
        local_ip    = excluded.local_ip,
        api_port    = excluded.api_port,
        pairing_code = excluded.pairing_code,
        last_seen   = now();
$$;

revoke all on function public.upsert_device(text,text,text,text,integer,text) from public;
grant execute on function public.upsert_device(text,text,text,text,integer,text) to anon;
