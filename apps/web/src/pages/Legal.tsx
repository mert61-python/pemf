// Author: mertaygn, cglrgrkn
import { useLocation, Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { COMPANY, LEGAL_DOCS } from '../config'
import type { LegalSlug } from '../config'

/* ============================================================
   PEMF Vet — Yasal belgeler (tek bileşen, route'a göre içerik)
   ŞABLON: Metinler 6502 sy. TKHK, Mesafeli Sözleşmeler Yönetmeliği
   (2015), 6563 sy. E-Ticaret Kanunu ve 6698 sy. KVKK çerçevesinde
   hazırlanmış taslaklardır. Şirket bilgileri config.ts > COMPANY'den
   okunur (placeholder'lar doldurulunca tüm belgeler güncellenir).
   Yayına almadan önce bir hukuk danışmanınca gözden geçirilmelidir.
   ============================================================ */

/* ---- Metin değerleri + zengin metin bileşenleri (I18N: her paragraf TEK anahtar + <Trans>, KURALLAR §4.1b) ---- */
const BILESENLER = { kalin: <strong />, kod: <code /> }
function degerler() {
  return {
    marka: COMPANY.brandName,
    eposta: COMPANY.email,
    kvkkEposta: COMPANY.kvkkEmail,
    gun: COMPANY.withdrawalDays,
    adres: COMPANY.address,
    sehir: COMPANY.city,
    ulke: COMPANY.country,
    unvan: COMPANY.legalName,
    tur: COMPANY.entityType,
    tel: COMPANY.phone,
    daire: COMPANY.taxOffice,
    vergiNo: COMPANY.taxNo,
    mersis: COMPANY.mersis,
    sicil: COMPANY.tradeRegistry,
    telefon: COMPANY.phone ? ` — ${COMPANY.phone}` : '',
  }
}
type YP = { values: ReturnType<typeof degerler>; components: typeof BILESENLER }
const ypKur = (): YP => ({ values: degerler(), components: BILESENLER })

/* ---- Küçük, yeniden kullanılabilir metin bileşenleri ---- */
function H2({ children }: { children: ReactNode }) {
  return <h2 className="mt-8 mb-3 text-xl font-bold text-fg">{children}</h2>
}
function H3({ children }: { children: ReactNode }) {
  return <h3 className="mt-5 mb-2 text-base font-semibold text-fg">{children}</h3>
}
function P({ children }: { children: ReactNode }) {
  return <p className="mb-3 text-sm leading-relaxed text-muted">{children}</p>
}
function UL({ children }: { children: ReactNode }) {
  return (
    <ul className="mb-3 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-muted">{children}</ul>
  )
}

/* Satıcı kimliği — 6563 sy. Kanun m.5 + Yönetmelik zorunlu bilgileri. */
function SellerIdentity({ yp }: { yp: YP }) {
  return (
    <UL>
      <li><Trans i18nKey="yasal.satici.unvan" {...yp} /></li>
      <li><Trans i18nKey="yasal.satici.tur" {...yp} /></li>
      <li><Trans i18nKey="yasal.satici.adres" {...yp} /></li>
      {COMPANY.phone ? <li><Trans i18nKey="yasal.satici.tel" {...yp} /></li> : null}
      <li><Trans i18nKey="yasal.satici.eposta" {...yp} /></li>
      <li><Trans i18nKey="yasal.satici.vergi" {...yp} /></li>
      <li><Trans i18nKey="yasal.satici.mersis" {...yp} /></li>
      <li><Trans i18nKey="yasal.satici.sicil" {...yp} /></li>
    </UL>
  )
}

/* ------------------------------------------------------------------
   BELGE İÇERİKLERİ — her slug için bir taslak.
   ------------------------------------------------------------------ */
const DOCS: Record<LegalSlug, (yp: YP) => ReactNode> = {
  /* =============== 1) MESAFELİ SATIŞ SÖZLEŞMESİ =============== */
  'mesafeli-satis': (yp) => (
    <>
      <P>
        <Trans i18nKey="yasal.mesafeli.01" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.mesafeli.02" {...yp} /></H2>
      <H3><Trans i18nKey="yasal.mesafeli.03" {...yp} /></H3>
      <SellerIdentity yp={yp} />
      <H3><Trans i18nKey="yasal.mesafeli.04" {...yp} /></H3>
      <P>
        <Trans i18nKey="yasal.mesafeli.05" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.mesafeli.06" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.mesafeli.07" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.mesafeli.08" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.mesafeli.09" {...yp} />
      </P>
      <P>
        <Trans i18nKey="yasal.mesafeli.10" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.mesafeli.11" {...yp} /></H2>
      <UL>
        <li>
          <Trans i18nKey="yasal.mesafeli.12" {...yp} />
        </li>
        <li>
          <Trans i18nKey="yasal.mesafeli.13" {...yp} />
        </li>
        <li>
          <Trans i18nKey="yasal.mesafeli.14" {...yp} />
        </li>
        <li>
          <Trans i18nKey="yasal.mesafeli.15" {...yp} />
        </li>
      </UL>

      <H2><Trans i18nKey="yasal.mesafeli.16" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.mesafeli.17" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.mesafeli.18" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.mesafeli.19" {...yp} />
      </P>
      <P>
        <Trans i18nKey="yasal.mesafeli.20" {...yp} />
      </P>
      <P>
        <Trans i18nKey="yasal.mesafeli.21" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.mesafeli.22" {...yp} /></H2>
      <UL>
        <li>
          <Trans i18nKey="yasal.mesafeli.23" {...yp} />
        </li>
        <li>
          <Trans i18nKey="yasal.mesafeli.24" {...yp} />
        </li>
        <li>
          <Trans i18nKey="yasal.mesafeli.25" {...yp} />
        </li>
      </UL>

      <H2><Trans i18nKey="yasal.mesafeli.26" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.mesafeli.27" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.mesafeli.28" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.mesafeli.29" {...yp} />
      </P>
    </>
  ),

  /* =============== 2) ÖN BİLGİLENDİRME FORMU =============== */
  'on-bilgilendirme': (yp) => (
    <>
      <P>
        <Trans i18nKey="yasal.onbilgi.01" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.onbilgi.02" {...yp} /></H2>
      <SellerIdentity yp={yp} />

      <H2><Trans i18nKey="yasal.onbilgi.03" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.onbilgi.04" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.onbilgi.05" {...yp} /></H2>
      <UL>
        <li>
          <Trans i18nKey="yasal.onbilgi.06" {...yp} />
        </li>
        <li><Trans i18nKey="yasal.onbilgi.07" {...yp} /></li>
        <li><Trans i18nKey="yasal.onbilgi.08" {...yp} /></li>
      </UL>

      <H2><Trans i18nKey="yasal.onbilgi.09" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.onbilgi.10" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.onbilgi.11" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.onbilgi.12" {...yp} />
      </P>
      <P>
        <Trans i18nKey="yasal.onbilgi.13" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.onbilgi.14" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.onbilgi.15" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.onbilgi.16" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.onbilgi.17" {...yp} />
      </P>
    </>
  ),

  /* =============== 3) İPTAL, İADE VE CAYMA HAKKI =============== */
  'iptal-iade': (yp) => (
    <>
      <P>
        <Trans i18nKey="yasal.iptal.01" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.iptal.02" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.iptal.03" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.iptal.04" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.iptal.05" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.iptal.06" {...yp} /></H2>
      <UL>
        <li><Trans i18nKey="yasal.iptal.07" {...yp} /></li>
        <li>
          <Trans i18nKey="yasal.iptal.08" {...yp} />
        </li>
        <li><Trans i18nKey="yasal.iptal.09" {...yp} /></li>
      </UL>

      <H2><Trans i18nKey="yasal.iptal.10" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.iptal.11" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.iptal.12" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.iptal.13" {...yp} />
      </P>
    </>
  ),

  /* =============== 4) KVKK AYDINLATMA METNİ =============== */
  kvkk: (yp) => (
    <>
      <P>
        <Trans i18nKey="yasal.kvkk.01" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.kvkk.02" {...yp} /></H2>
      <SellerIdentity yp={yp} />

      <H2><Trans i18nKey="yasal.kvkk.03" {...yp} /></H2>
      <UL>
        <li><Trans i18nKey="yasal.kvkk.04" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.05" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.06" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.07" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.08" {...yp} /></li>
      </UL>
      <P>
        <Trans i18nKey="yasal.kvkk.09" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.kvkk.10" {...yp} /></H2>
      <UL>
        <li><Trans i18nKey="yasal.kvkk.11" {...yp} /></li>
        {/* İndirme artık hesap gerektirdiği için YENİ bir işleme amacı doğdu; yayımlanan metin
            fiili işlemeyi kapsamazsa aydınlatma yükümlülüğü eksik kalır. */}
        <li><Trans i18nKey="yasal.kvkk.12" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.13" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.14" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.15" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.16" {...yp} /></li>
      </UL>

      <H2><Trans i18nKey="yasal.kvkk.17" {...yp} /></H2>
      <UL>
        <li><Trans i18nKey="yasal.kvkk.18" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.19" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.20" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.21" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.22" {...yp} /></li>
      </UL>

      <H2><Trans i18nKey="yasal.kvkk.23" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.kvkk.24" {...yp} />
      </P>

      {/* ⚠️ 2026-08-09 denetimi (Tier 3): metinde YURT DIŞINA AKTARIM başlığı hiç yoktu; oysa
          hesap ve cihaz verileri fiilen yurt dışındaki bir işleyiciye (Supabase) gidiyor ve site
          yurt dışında barındırılıyor (Vercel). Aşağıdaki kalemler koddan ÖLÇÜLEREK yazıldı:
            • Supabase Auth  → e-posta, şifrenin geri döndürülemez özeti, oturum jetonları, kayıt profil alanları
            • devices tablosu (60 sn'de bir heartbeat, servers/sync_worker._publish_device_registry):
              device_id, cihaz adı, tunnel_url, yerel IP, port, eşleştirme kodu, last_seen,
              app_version, launcher_version, base_sha, at_rest_encrypted, (RPC) p_secret cihaz doğrulama anahtarı
              — D2.06: tests/test_kvkk_transfer_claims.py bu kümeyi AST ile koddan çıkarır, eşlemesiz yeni alan KIRMIZI
            • hasta/seans kayıtları → VARSAYILAN OLARAK GİTMEZ (PEMF_CLOUD_PATIENT_SYNC=0);
              yalnız klinik açıkça açarsa ve o hâlde de PII şifreli gönderilir.
          ⚠️ SAHİBİNE: Supabase proje BÖLGESİ (ör. eu-central-1 / us-east-1) panodan okunup
          aşağıdaki cümleye somut olarak yazılmalıdır; ayrıca m.9 kapsamında hangi mekanizmaya
          (taahhütname / standart sözleşme / açık rıza) dayanıldığı hukuk danışmanıyla
          KESİNLEŞTİRİLMELİDİR. Bu metin fiili durumu bildirir, hukuki nitelemeyi yapmaz. */}
      <H2><Trans i18nKey="yasal.kvkk.25" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.kvkk.26" {...yp} />
      </P>
      <UL>
        <li>
          <Trans i18nKey="yasal.kvkk.27" {...yp} />
        </li>
        <li>
          <Trans i18nKey="yasal.kvkk.28" {...yp} />
        </li>
        <li>
          <Trans i18nKey="yasal.kvkk.29" {...yp} />
        </li>
      </UL>
      <P>
        <Trans i18nKey="yasal.kvkk.30" {...yp} />
      </P>
      <P>
        <Trans i18nKey="yasal.kvkk.31" {...yp} />
      </P>
      <P>
        <Trans i18nKey="yasal.kvkk.32" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.kvkk.33" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.kvkk.34" {...yp} />
      </P>
      {/* ⚠️ 2026-08-09 denetimi: metin "öngörülen süreler" diyordu ama YAZILIM somut bir süre
          uyguluyordu (varsayılan 365 gün) ve bunu operatöre hiçbir yerde söylemiyordu. Klinik
          366. günde hasta adı yerine [REDACTED] görüp sebebini bulamıyordu. Uygulanan kuralın
          hukuki metinde de somut olarak yazması gerekir.
          ⚠️ D2.06 (A-38, 2026-10-10): aşağıdaki maddeler yazılımın DEVREDEKİ varsayılanlarından türetilir ve
          tests/test_kvkk_transfer_claims.py `data-saklama` anahtarlarıyla koddaki sayıya kilitler (headless bakımın
          PEMF_RETAIN_* varsayılanları, ayar ucunun maskeleme süresi, günlük bakımın anonimleştirme eşiği). Kodda bir süre
          değişirse metin de değişmeden kapı geçmez. Eski metin maskelemeyi "varsayılan olarak 365 gün sonra" anlatıyordu;
          gerçekte maskeleme klinik onaylamadan HİÇ başlamaz (opt-in). */}
      <P>
        <Trans i18nKey="yasal.kvkk.35" {...yp} />
      </P>
      <UL>
        <li data-saklama="sensor">
          <Trans i18nKey="yasal.kvkk.36" {...yp} />
        </li>
        <li data-saklama="doz">
          <Trans i18nKey="yasal.kvkk.37" {...yp} />
        </li>
        <li data-saklama="olay">
          <Trans i18nKey="yasal.kvkk.38" {...yp} />
        </li>
        <li data-saklama="anonim">
          <Trans i18nKey="yasal.kvkk.39" {...yp} />
        </li>
        <li data-saklama="maskeleme">
          <Trans i18nKey="yasal.kvkk.40" {...yp} />
        </li>
      </UL>
      <P>
        <Trans i18nKey="yasal.kvkk.41" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.kvkk.42" {...yp} /></H2>
      <UL>
        <li><Trans i18nKey="yasal.kvkk.43" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.44" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.45" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.46" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.47" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.48" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.49" {...yp} /></li>
        <li><Trans i18nKey="yasal.kvkk.50" {...yp} /></li>
      </UL>

      <H2><Trans i18nKey="yasal.kvkk.51" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.kvkk.52" {...yp} />
      </P>
    </>
  ),

  /* =============== 5) GİZLİLİK POLİTİKASI =============== */
  gizlilik: (yp) => (
    <>
      <P>
        <Trans i18nKey="yasal.gizlilik.01" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.gizlilik.02" {...yp} /></H2>
      <UL>
        <li><Trans i18nKey="yasal.gizlilik.03" {...yp} /></li>
        <li><Trans i18nKey="yasal.gizlilik.04" {...yp} /></li>
        <li><Trans i18nKey="yasal.gizlilik.05" {...yp} /></li>
        <li><Trans i18nKey="yasal.gizlilik.06" {...yp} /></li>
      </UL>

      <H2><Trans i18nKey="yasal.gizlilik.07" {...yp} /></H2>
      <UL>
        <li><Trans i18nKey="yasal.gizlilik.08" {...yp} /></li>
        {/* Kayıtsız indirme kaldırıldı → indirme amacı burada da açıkça yazılmalı (KVKK metniyle tutarlı). */}
        <li><Trans i18nKey="yasal.gizlilik.09" {...yp} /></li>
        <li><Trans i18nKey="yasal.gizlilik.10" {...yp} /></li>
        <li><Trans i18nKey="yasal.gizlilik.11" {...yp} /></li>
        <li><Trans i18nKey="yasal.gizlilik.12" {...yp} /></li>
      </UL>

      <H2><Trans i18nKey="yasal.gizlilik.13" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.gizlilik.14" {...yp} />
      </P>
      <UL>
        <li>
          <Trans i18nKey="yasal.gizlilik.15" {...yp} />
        </li>
        <li>
          <Trans i18nKey="yasal.gizlilik.16" {...yp} />
        </li>
      </UL>
      <P>
        <Trans i18nKey="yasal.gizlilik.17" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.gizlilik.18" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.gizlilik.19" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.gizlilik.20" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.gizlilik.21" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.gizlilik.22" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.gizlilik.23" {...yp} />
      </P>
    </>
  ),

  /* =============== 6) ÇEREZ POLİTİKASI =============== */
  'cerez-politikasi': (yp) => (
    <>
      <P>
        <Trans i18nKey="yasal.cerez.01" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.cerez.02" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.cerez.03" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.cerez.04" {...yp} /></H2>
      <UL>
        <li>
          <Trans i18nKey="yasal.cerez.05" {...yp} />
        </li>
        <li>
          <Trans i18nKey="yasal.cerez.06" {...yp} />
        </li>
        <li>
          <Trans i18nKey="yasal.cerez.07" {...yp} />
        </li>
      </UL>

      <H2><Trans i18nKey="yasal.cerez.08" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.cerez.09" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.cerez.10" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.cerez.11" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.cerez.12" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.cerez.13" {...yp} />
      </P>
    </>
  ),

  /* =============== 7) KULLANIM ŞARTLARI =============== */
  'kullanim-sartlari': (yp) => (
    <>
      <P>
        <Trans i18nKey="yasal.kullanim.01" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.kullanim.02" {...yp} /></H2>
      <UL>
        <li><Trans i18nKey="yasal.kullanim.03" {...yp} /></li>
        <li><Trans i18nKey="yasal.kullanim.04" {...yp} /></li>
        <li><Trans i18nKey="yasal.kullanim.05" {...yp} /></li>
      </UL>

      <H2><Trans i18nKey="yasal.kullanim.06" {...yp} /></H2>
      <UL>
        <li><Trans i18nKey="yasal.kullanim.07" {...yp} /></li>
        <li><Trans i18nKey="yasal.kullanim.08" {...yp} /></li>
        <li><Trans i18nKey="yasal.kullanim.09" {...yp} /></li>
      </UL>

      <H2><Trans i18nKey="yasal.kullanim.10" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.kullanim.11" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.kullanim.12" {...yp} /></H2>
      <div className="mb-3 rounded-lg border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm leading-relaxed text-amber-200">
        <Trans i18nKey="yasal.kullanim.13" {...yp} />
      </div>
      <P>
        <Trans i18nKey="yasal.kullanim.14" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.kullanim.15" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.kullanim.16" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.kullanim.17" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.kullanim.18" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.kullanim.19" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.kullanim.20" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.kullanim.21" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.kullanim.22" {...yp} />
      </P>

      <H2><Trans i18nKey="yasal.kullanim.23" {...yp} /></H2>
      <P>
        <Trans i18nKey="yasal.kullanim.24" {...yp} />
      </P>
    </>
  ),
}

/* ------------------------------------------------------------------
   Ana bileşen — route'a göre ilgili belgeyi gösterir.
   ------------------------------------------------------------------ */
export function LegalPage() {
  const { t, i18n } = useTranslation()
  const location = useLocation()
  const slug = location.pathname.replace(/^\//, '')
  const doc = LEGAL_DOCS.find((d) => d.slug === slug)

  // Bilinmeyen slug → "belge bulunamadı" + geçerli belgelere bağlantılar.
  if (!doc) {
    return (
      <section className="mx-auto max-w-3xl px-5 py-20 sm:px-6">
        <span className="chip">{t('ortak.altBilgi.yasal')}</span>
        <h1 className="mt-5 text-3xl font-extrabold sm:text-4xl">{t('yasal.kabuk.bulunamadi')}</h1>
        <p className="mt-4 text-muted">{t('yasal.kabuk.bulunamadiAciklama')}</p>
        <ul className="mt-6 space-y-2">
          {LEGAL_DOCS.map((d) => (
            <li key={d.slug}>
              <Link to={`/${d.slug}`} className="text-primary hover:underline">
                {d.title}
              </Link>
            </li>
          ))}
        </ul>
        <Link to="/" className="btn-ghost mt-8">
          {t('ortak.anaSayfayaDon')}
        </Link>
      </section>
    )
  }

  return (
    <article className="mx-auto max-w-3xl px-5 py-14 sm:px-6 sm:py-16">
      <Link to="/" className="text-sm text-muted hover:text-fg">
        {t('yasal.kabuk.anaSayfa')}
      </Link>

      <h1 className="mt-4 text-3xl font-extrabold sm:text-4xl">{doc.title}</h1>

      {/* İÇ NOT KALDIRILDI (metin denetimi, 2026-08-20): burada "bu metin bir şablondur; yayına
          almadan önce hukuk danışmanınca gözden geçirilmelidir" uyarısı MÜŞTERİYE gösteriliyordu.
          Satın alma öncesi sözleşme sayfasında belgeyi taslak ilan etmek güveni doğrudan zedeler;
          hazırlık notu yayına değil, geliştirme akışına aittir. Kilit: src/__tests__/metin-guveni.test.ts */}

      {i18n.language === 'en' && (
        <p className="mt-4 rounded-md border border-border/60 px-3 py-2 text-xs text-muted">{t('yasal.kabuk.baglayici')}</p>
      )}

      <p className="mt-5 text-xs text-muted">{t('yasal.kabuk.sonGuncelleme', { tarih: COMPANY.updated })}</p>

      <div className="mt-6">{DOCS[doc.slug](ypKur())}</div>

      {/* İlgili belgeler */}
      <nav className="mt-12 border-t border-border/60 pt-6">
        <h2 className="mb-3 text-sm font-semibold text-fg">{t('yasal.kabuk.ilgili')}</h2>
        <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted">
          {LEGAL_DOCS.filter((d) => d.slug !== doc.slug).map((d) => (
            <li key={d.slug}>
              <Link to={`/${d.slug}`} className="hover:text-fg">
                {d.title}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </article>
  )
}

export default LegalPage
