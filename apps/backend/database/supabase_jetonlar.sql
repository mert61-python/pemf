-- PEMF Vet — JETON (token) ÜCRETLENDİRME ALTYAPISI
-- =================================================================================
-- Sahip kararı 2026-08-20: ücretlendirme "kuyruk/hız" vaadi yerine JETON tüketimine bağlanır.
-- Neden: yapay zekâ analizleri klinik bilgisayarında ÇALIŞIR; "sunucuda sıra beklersiniz"
-- çerçevesinin karşılığı yoktu.
-- ⚠️ OLGU DÜZELTMESİ (8. parti): "hiç karşılığı yoktu" YANLIŞ bir özetti. Eş-zamanlılık
-- sınırlayıcısı GERÇEKTEN var (servers/entitlement.py::ai_queue_gate → ai_router.py:54) ama
-- PEMF_TIER_ENFORCED KAPALI olduğu için çalışmıyor — ve zaten klinik makinesinde, sunucuda
-- değil. Kapalı bir mekanizma satılamaz; vaadin kaldırılması yerinde. Jeton ise gerçekten
-- ölçülebilen ve dürüstçe anlatılabilen bir birimdir: 1 jeton = 1 yapay zekâ analizi.
--
-- MODEL (iki cepli bakiye):
--   · aylik_hak      → planın her dönem YENİLENEN hakkı (devretmez)
--   · satin_alinan   → ek paketle alınan jetonlar (SÜRESİZ, devreder)
--   Tüketim önce `aylik_hak`ten düşer; bitince `satin_alinan`dan. Böylece kullanıcı satın
--   aldığı jetonu plan hakkı dururken kaybetmez.
--
-- ⚠️ TIBBİ CİHAZ GÜVENLİĞİ — DEĞİŞMEZ: jeton bir TİCARİ kapıdır, güvenlik kontrolü DEĞİLDİR.
--   · Süren bir seansı, acil durdurmayı, sensör okumayı, cihaz kontrolünü ASLA engellemez.
--   · Yalnız YENİ yapay zekâ ANALİZİ isteğini kapılar.
--   · Çevrimdışı klinikte tüketim yerel rezervden düşülür ve bağlantı gelince uzlaştırılır
--     (bkz. servers/jeton.py). İnternet yokluğu kliniği çalışamaz hâle GETİRMEZ.
--
-- Yazma yalnız service_role (ödeme geri-çağrısı + tüketim ucu). Kullanıcı YALNIZ kendi
-- bakiyesini okur — `subscriptions` tablosuyla birebir aynı güvenlik deseni.
-- Supabase SQL editöründe çalıştırın.

-- ── 1) BAKİYE ────────────────────────────────────────────────────────────────────
create table if not exists public.token_balances (
  user_id          uuid primary key references auth.users (id) on delete cascade,
  aylik_hak        integer not null default 0 check (aylik_hak >= 0),
  satin_alinan     integer not null default 0 check (satin_alinan >= 0),
  -- KULLANDIKÇA ÖDE (sahip isteği 2026-08-20): önden ödeme/aylık ücret olmayan üyelik.
  --   'on_odemeli'  → tüketim bakiyeden düşer; bakiye biterse yeni analiz durur.
  --   'kullandikca' → bakiyeye BAKILMAZ; tüketim `kullandikca_borc`ta birikir ve dönem sonunda
  --                   (ya da eşik aşılınca) faturalanır. Hiç kullanılmazsa ücret çıkmaz.
  odeme_modeli     text not null default 'on_odemeli'
    check (odeme_modeli in ('on_odemeli', 'kullandikca')),
  -- Birikmiş, HENÜZ FATURALANMAMIŞ tüketim (yalnız kullandıkça-öde modelinde artar).
  -- ⚠️ Tavan uygulaması cihaz+uç tarafında (BORC_TAVANI): ödeme alınamayan sınırsız kullanımı
  -- engeller. TİCARİ sınırdır — aşılsa bile seans/acil durdurma çalışmaya devam eder.
  kullandikca_borc integer not null default 0 check (kullandikca_borc >= 0),
  -- Çevrimdışı klinikte oluşan ve henüz uzlaştırılmamış tüketim (negatife düşmez; bkz. jeton.py)
  bekleyen_borc    integer not null default 0 check (bekleyen_borc >= 0),
  donem_basi       timestamptz not null default now(),
  donem_sonu       timestamptz not null default (now() + interval '1 month'),
  updated_at       timestamptz not null default now()
);

alter table public.token_balances enable row level security;

-- `subscriptions` ile aynı sertleştirme: varsayılan grant'leri kaldır, yazmayı service_role'de bırak.
-- ⚠️ ÖLÇÜLDÜ (2026-08-21, canlı): bu satırın ilk hâli yalnız insert/update/delete alıyordu; oysa
-- Supabase yeni tabloya SELECT + REFERENCES + TRIGGER + TRUNCATE de veriyor.
-- ⚠️ SONRA SAHİP KARARI GELDİ ("okumaları RPC'ye taşı"): bakiye artık `jeton_bakiyem()` SECURITY
-- DEFINER fonksiyonundan okunuyor (bkz. database/supabase_okuma_rpc.sql), yani `authenticated`
-- rolünün tabloda SELECT yetkisine de İHTİYACI YOK. Hepsi geri alınır.
revoke all on public.token_balances from anon, authenticated;

drop policy if exists "token_balances_own_read" on public.token_balances;
create policy "token_balances_own_read" on public.token_balances
  for select using (auth.uid() = user_id);

-- ── 2) DEFTER (tüketim/yükleme izi) ──────────────────────────────────────────────
-- Neden ayrı defter: "jetonum nereye gitti?" sorusu desteğe en çok gelen sorulardan biri olur;
-- ayrıca çevrimdışı uzlaştırmada AYNI işlemin iki kez düşülmemesi için `istek_id` benzersizliği
-- şart (idempotans). Silme YOK — düzeltme ters kayıtla yapılır.
create table if not exists public.token_ledger (
  id           bigserial primary key,
  user_id      uuid not null references auth.users (id) on delete cascade,
  -- Pozitif = yükleme (plan yenileme / satın alma), negatif = tüketim
  miktar       integer not null,
  -- ⚠️ 'kullandikca' ŞART: cihaz (servers/jeton.py) kullandıkça-öde tüketimini bu türle gönderir;
  -- listede olmazsa RPC check ihlaliyle patlar ve tüketim KAYBOLUR. 'faturalandi' = borç tahsil
  -- edildiğinde yazılan pozitif kapanış kaydı.
  tur          text not null check (tur in ('plan_yenileme', 'satin_alma', 'analiz',
                                            'kullandikca', 'faturalandi', 'duzeltme')),
  -- Hangi analiz (ör. 'goruntu', 'ses', 'agir_arastirma', 'ai_pro_seans') — raporlama için
  detay        text,
  -- ⚠️ İDEMPOTANS ANAHTARI: aynı istek iki kez gelirse (yeniden deneme / çevrimdışı uzlaştırma)
  -- ikinci kayıt UNIQUE ihlaliyle düşer ve bakiye BİR KEZ düşülür.
  istek_id     text not null,
  cihaz_id     text,
  created_at   timestamptz not null default now(),
  unique (user_id, istek_id)
);

alter table public.token_ledger enable row level security;
-- Defter okuması da RPC'de: `jeton_defterim(p_limit)` (bkz. supabase_okuma_rpc.sql).
revoke all on public.token_ledger from anon, authenticated;

drop policy if exists "token_ledger_own_read" on public.token_ledger;
create policy "token_ledger_own_read" on public.token_ledger
  for select using (auth.uid() = user_id);

create index if not exists token_ledger_user_time on public.token_ledger (user_id, created_at desc);

-- ── 3) ATOMİK TÜKETİM ────────────────────────────────────────────────────────────
-- Neden RPC: "oku → hesapla → yaz" üç ayrı isteğe bölünürse iki cihaz aynı anda analiz
-- istediğinde bakiye ÇİFT düşer ya da hiç düşmez. Tek deyimde, satır kilidiyle yapılır.
-- Dönüş: jsonb { ok, kalan, sebep }
create or replace function public.jeton_tuket(
  p_miktar integer,
  p_tur text,
  p_detay text,
  p_istek_id text,
  p_cihaz_id text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user uuid := auth.uid();
  v_bakiye public.token_balances%rowtype;
  v_aylik integer;
  v_satin integer;
  v_kalan integer;
begin
  if v_user is null then
    return jsonb_build_object('ok', false, 'sebep', 'auth');
  end if;
  if p_miktar is null or p_miktar <= 0 then
    return jsonb_build_object('ok', false, 'sebep', 'gecersiz_miktar');
  end if;

  -- İDEMPOTANS: aynı istek daha önce işlendiyse bakiyeyi TEKRAR düşme, mevcut durumu döndür.
  if exists (select 1 from public.token_ledger l where l.user_id = v_user and l.istek_id = p_istek_id) then
    select * into v_bakiye from public.token_balances where user_id = v_user;
    return jsonb_build_object('ok', true, 'kalan', coalesce(v_bakiye.aylik_hak, 0) + coalesce(v_bakiye.satin_alinan, 0), 'tekrar', true);
  end if;

  -- Satır kilidi: eşzamanlı iki analiz aynı jetonu harcayamaz.
  select * into v_bakiye from public.token_balances where user_id = v_user for update;
  if not found then
    return jsonb_build_object('ok', false, 'sebep', 'bakiye_yok');
  end if;

  -- KULLANDIKÇA ÖDE: bakiyeye bakılmaz; tüketim borç olarak birikir (önden ödeme yok).
  -- Borç TAVANI burada uygulanmaz — tavan cihaz/uç tarafının işidir ve TİCARİ bir sınırdır;
  -- veritabanı katmanında reddetmek, çevrimdışı uzlaştırmayı da bloklardı (tüketim ZATEN olmuş).
  if v_bakiye.odeme_modeli = 'kullandikca' then
    update public.token_balances
       set kullandikca_borc = kullandikca_borc + p_miktar,
           updated_at = now()
     where user_id = v_user
     returning kullandikca_borc into v_kalan;

    insert into public.token_ledger (user_id, miktar, tur, detay, istek_id, cihaz_id)
    values (v_user, -p_miktar, 'kullandikca', p_detay, p_istek_id, p_cihaz_id);

    return jsonb_build_object('ok', true, 'kalan', 0, 'borc', v_kalan, 'model', 'kullandikca');
  end if;

  if (v_bakiye.aylik_hak + v_bakiye.satin_alinan) < p_miktar then
    return jsonb_build_object('ok', false, 'sebep', 'yetersiz',
                              'kalan', v_bakiye.aylik_hak + v_bakiye.satin_alinan);
  end if;

  -- ÖNCE aylık hak (devretmez → önce o bitsin), SONRA satın alınan (süresiz).
  v_aylik := least(v_bakiye.aylik_hak, p_miktar);
  v_satin := p_miktar - v_aylik;

  update public.token_balances
     set aylik_hak = aylik_hak - v_aylik,
         satin_alinan = satin_alinan - v_satin,
         updated_at = now()
   where user_id = v_user
   returning (aylik_hak + satin_alinan) into v_kalan;

  insert into public.token_ledger (user_id, miktar, tur, detay, istek_id, cihaz_id)
  values (v_user, -p_miktar, p_tur, p_detay, p_istek_id, p_cihaz_id);

  return jsonb_build_object('ok', true, 'kalan', v_kalan);
end;
$$;

-- ⚠️ `from public` YETMİYOR (2026-08-21 canlıda ölçüldü): Supabase yeni fonksiyona anon,
-- authenticated ve service_role rollerine AYRICA execute verir; PUBLIC'ten geri almak bunları
-- KALDIRMAZ. Roller tek tek yazılmalı.
revoke all on function public.jeton_tuket(integer, text, text, text, text) from public, anon;
grant execute on function public.jeton_tuket(integer, text, text, text, text) to authenticated;

-- ── 4) DÖNEM YENİLEME ────────────────────────────────────────────────────────────
-- Plan hakkı her dönem YENİDEN yazılır (devretmez); satın alınan jetonlara DOKUNULMAZ.
-- service_role tarafından (ödeme yenileme geri-çağrısı ya da zamanlanmış iş) çağrılır.
create or replace function public.jeton_donem_yenile(p_user uuid, p_aylik_hak integer)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.token_balances (user_id, aylik_hak, donem_basi, donem_sonu)
  values (p_user, p_aylik_hak, now(), now() + interval '1 month')
  on conflict (user_id) do update
    set aylik_hak = excluded.aylik_hak,
        donem_basi = now(),
        donem_sonu = now() + interval '1 month',
        updated_at = now();

  insert into public.token_ledger (user_id, miktar, tur, detay, istek_id)
  values (p_user, p_aylik_hak, 'plan_yenileme', 'dönem hakkı', 'yenile_' || p_user::text || '_' || extract(epoch from now())::bigint::text);
end;
$$;

-- ⚠️⚠️ EN KRİTİK SATIR. Bu fonksiyon SECURITY DEFINER'dır ve İSTEDİĞİ kullanıcıya İSTEDİĞİ
-- kadar jeton yazar. `anon` unutulursa, mobil uygulamanın İÇİNDE taşınan anon anahtarıyla
-- herkes kendine sınırsız jeton yazabilir (doğrudan fatura baypası) ve başkasının bakiyesini
-- EZEBİLİR. 2026-08-21'de şema canlıya ilk kurulduğunda tam olarak bu delik açıldı: ilk hâl
-- yalnız `public, authenticated` diyordu, `anon` execute yetkisiyle kaldı (ölçülüp kapatıldı).
revoke all on function public.jeton_donem_yenile(uuid, integer) from public, anon, authenticated;
-- Yalnız service_role çağırır (grant verilmez).

-- Not: satırı olmayan kullanıcı, uygulama tarafında "deneme hakkı" varsayılanı alır
-- (bkz. pemf-vet-web/src/config.ts JETON.planHaklari ve servers/jeton.py).
