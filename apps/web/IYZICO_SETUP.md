# PEMF Vet — iyzico Abonelik Kurulumu (A1, Türkiye)

**Model:** Abonelik **web'de** satılır (iyzico Subscription). Ödeme sonrası iyzico → `/api/callback`
(+ tekrarlayan ödemelerde `/api/webhook`) Supabase `subscriptions` tablosuna yazar (service_role).
Mobil/masaüstü-client/backend bu tabloyu **yalnız okur** (Apple 3.1.1 uyumlu).

```
Web /pricing → /odeme (fatura bilgisi) → /api/checkout → iyzico ödeme formu (gömülü)
                                              │ ödeme
                    iyzico → /api/callback (retrieve) ──► Supabase subscriptions
                    iyzico → /api/webhook (tekrarlayan) ─► (re-fetch, authoritative)
                                              │
              Mobil / client / backend ← RLS ile kendi satırını okur (spoof-proof)
```

## 1) Supabase
`pf/supabase/subscriptions.sql` çalıştırılmış olmalı (tablo + RLS). Not: `stripe_subscription_id`
sütunu iyzico **subscriptionReferenceCode**'unu, `stripe_customer_id` **customerReferenceCode**'u
tutar (sütun adları eski, işlev iyzico).

## 2) iyzico ürün + ödeme planları
iyzico Panel → **Abonelik → Ürünler** → ürün oluştur → her ürüne **Ödeme Planı** (recurring) ekle.
**8 plan** gerekir (fiyatlar KDV dahil TRY):

| Plan | Aylık | Yıllık |
|------|-------|--------|
| Pro | ₺990 | ₺9.900 |
| Pro+ | ₺1.990 | ₺19.900 |
| Pro **+ Araştırma** | ₺1.380 | ₺13.800 |
| Pro+ **+ Araştırma** | ₺2.380 | ₺23.800 |

Her planın **referans kodunu** (pricingPlanReferenceCode) `.env` / Vercel'e girin (bkz `.env.example`).
*(Araştırma fiyatı = temel + ₺390. iyzico'da abonelik tek-plandır → Araştırma ayrı plan olarak katlanır.)*

## 3) API anahtarları + Vercel env
iyzico → **Ayarlar → API Anahtarları** → `IYZICO_API_KEY` + `IYZICO_SECRET_KEY` + **Üye İşyeri No** →
`IYZICO_MERCHANT_ID`. `IYZICO_URI` = sandbox (`https://sandbox-api.iyzipay.com`) → test; prod
(`https://api.iyzipay.com`) → canlı. Tüm değişkenleri **Vercel → Settings → Environment Variables**'a
girin (`.env.example`'daki gibi; Supabase public değerleri hazır, service_role + iyzico anahtarları GİZLİ).

## 4) Webhook
iyzico Panel → **Ayarlar → Üye İşyeri → Abonelik Bildirimleri** → URL: `https://<site>/api/webhook`.
İmza (`X-IYZ-SIGNATURE-V3`) doğrulanır; **ancak** webhook aboneliği ayrıca iyzico'dan yeniden çeker
(authoritative) → sahte bildirim hak veremez. Sandbox'ta imza doğrulandıktan sonra
`IYZICO_WEBHOOK_STRICT=1` ile sıkılaştırın.

## 5) Test (sandbox)
1. Sandbox anahtarları + planlarla deploy. Pricing → Pro/Pro+ → **/odeme** → giriş + fatura bilgisi →
   "Ödemeye geç" → iyzico formu gömülür.
2. iyzico **test kartı** ile öde (ör. 5528790000000008, son kullanma ileri tarih, CVC 123).
3. `subscriptions`'ta satır oluşmalı (tier + status=active + addons). Mobil/client o hesapla girince görür.

## 6) Enforcement (canlı satış hazır olunca)
- Backend: `PEMF_TIER_ENFORCED=1`. Mobil: `entitlement.ts` → `ENTITLEMENT_ENFORCED=true` + APK rebuild.

## Uçlar
- `POST /api/checkout` — `{ tier, yearly, research, token, customer }` → `{ content }` (gömülü form).
- `GET/POST /api/callback` — ödeme sonrası; retrieve → subscriptions yazar → redirect.
- `POST /api/webhook` — tekrarlayan; imza + authoritative re-fetch → subscriptions günceller.
- `POST /api/cancel` — `{ token }` → aboneliği iptal eder.
