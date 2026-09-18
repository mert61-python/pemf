-- PEMF Vet — Abonelik / Entitlement tablosu (A1 modeli)
-- Abonelik WEB'de satılır (Stripe); web/masaüstü-client/mobil YALNIZ okur.
-- Yazma yalnız service_role (Stripe webhook → backend). Client asla yazmaz.
-- Supabase SQL editöründe çalıştırın.

create table if not exists public.subscriptions (
  user_id uuid primary key references auth.users (id) on delete cascade,
  tier text not null default 'baslangic'
    check (tier in ('baslangic', 'pro', 'pro_plus')),
  status text not null default 'trialing'
    check (status in ('trialing', 'active', 'past_due', 'canceled')),
  addons jsonb not null default '[]'::jsonb,           -- örn ["research"]
  trial_ends_at timestamptz,
  current_period_end timestamptz,
  stripe_customer_id text,
  stripe_subscription_id text,
  updated_at timestamptz not null default now()
);

alter table public.subscriptions enable row level security;

-- #107 (savunma-derinliği, patients/sessions deseniyle tutarlılık): Supabase-varsayılan anon/
-- authenticated tablo-grant'lerini KALDIR → yazma yalnız service_role'de kalsın (RLS'in tek-katman
-- olmasına güvenme). SELECT'i RLS + minimum grant ile bırak.
revoke insert, update, delete on public.subscriptions from anon, authenticated;

-- Kullanıcı YALNIZ kendi hakkını okur (mobil/web/client bunu okur).
drop policy if exists "subscriptions_own_read" on public.subscriptions;
create policy "subscriptions_own_read" on public.subscriptions
  for select using (auth.uid() = user_id);

-- Yazma politikası YOK → sadece service_role (Stripe webhook) yazabilir (RLS bypass).
-- Böylece kullanıcı kendi tier'ını değiştiremez.

-- Not: satırı olmayan kullanıcı mobilde "14 gün deneme" varsayılanı alır
-- (defaultEntitlement, hesap oluşturma anından). İsteğe bağlı: kayıt trigger'ı ile
-- otomatik trial satırı da eklenebilir (şart değil — mobil zaten graceful default veriyor).
