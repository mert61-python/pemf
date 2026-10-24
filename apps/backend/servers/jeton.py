# Author: mertaygn, cglrgrkn
"""
JETON (token) TÜKETİM KAPISI — cihaz tarafı (sahip kararı 2026-08-20).

Ücretlendirme "kuyruk/hız" vaadi yerine JETON tüketimine bağlandı: 1 jeton = 1 yapay zekâ
analizi. Sebep: yapay zekâ analizleri klinik bilgisayarında ÇALIŞIYOR; "sunucuda sıra
beklersiniz" vaadinin karşılığı yoktu. Jeton ölçülebilir ve dürüstçe anlatılabilir bir birimdir.

  · Şema/uzlaştırma : database/supabase_jetonlar.sql (atomik `jeton_tuket` RPC + defter)
  · Uç              : apps/web/api/tokens.ts (bakiye + tüketim, idempotans zorunlu)
  · Kullanıcı metni : apps/web/src/config.ts::JETON (maliyet tablosu TEK KAYNAK)

╔══════════════════════════════════════════════════════════════════════════════════════════╗
║ ⚠️ TIBBİ CİHAZ GÜVENLİĞİ — PAZARLIK EDİLEMEZ                                             ║
║ Jeton TİCARİ bir kapıdır, güvenlik kontrolü DEĞİLDİR. Süren seansı, seans durdurmayı,    ║
║ ACİL DURDURMAYI, sensör okumayı ve cihaz kontrolünü ASLA engellemez. Yalnız YENİ yapay   ║
║ zekâ ANALİZİ isteğini kapılar. (entitlement.py aynı ilkeyi taşır: "compute-önceliği       ║
║ kapısı, güvenlik kontrolü değil" + her belirsizlikte fail-open.)                          ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

İNTERNET ŞARTI (sahip kararı 2026-10-19 · S-4B.5 + S-4BI.8; YALNIZ ücretlendirme AÇIKKEN): bakiye / borç okunamıyorsa
(internet yok) yeni yapay zekâ analizi BAŞLATILMAZ — 402, sebep `cevrimdisi`. Çevrimdışı analiz, çevrimdışı tavan
(`PEMF_JETON_OFFLINE_TAVAN`) ve "eksi bakiye" (sunucunun reddettiği tüketimin defterde borç olarak beklemesi) KALDIRILDI.
Seans, acil durdurma ve sensör izleme internetsiz de çalışır (bu kapıya hiç gelmez — `_islem_turu`).
YOLDA KALAN ÖDEME ("Bir süre yeniden dene"): analiz çevrimiçi karar alıp teslim edildi ama düşüm tam o an gönderilemediyse kayıt
defterde bekler ve sahibinin bir sonraki çevrimiçi isteğinde gönderilir; o zamana dek sahibin sonraki kararlarında bakiyeden düşülmüş
(kullandıkça öde: borca eklenmiş) sayılır → bakiye eksiye düşmez. Sunucu kaydı KESİN reddederse (`yetersiz`) kayıt düşer, borç tutulmaz.

ÇİFT DÜŞME YOK: her tüketim `istek_id` taşır; yeniden deneme ve uzlaştırma aynı jetonu iki kez
harcayamaz (sunucuda `token_ledger` UNIQUE, burada yerel defterde anahtar kontrolü).

⚠️ BAYRAKLI: `PEMF_JETON_ENFORCED` KAPALIYKEN her şey no-op — satış açılana kadar canlı
davranış değişmez (entitlement.py deseniyle birebir).
⚠️ T3 · Y194 (sahip 2026-10-24): jeton KOD DÜZEYİNDE kapalı (`JETON_SAHIP_ACIK = False`) — ortamdaki `PEMF_JETON_ENFORCED=1` bu sürümde
YOK SAYILIR; her hesapta AI sınırsız. Ücretlendirme mantığı SİLİNMEDİ: satış açılınca sabit `True` yapılıp derlenir, ortam yine gerekir.
"""

from __future__ import annotations

import base64
import contextvars
import functools
import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from utils import ceviri

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


def _sayi(name: str, default, tip=int):
    """Sayısal bayrak; BOZUK değer (ör. 'elli', '4,5') VARSAYILANA düşer ve uyarı yazılır.

    ⚠️ D1.14 (B-2.17): eskiden modül düzeyinde `int(os.getenv(...))` ValueError atıyordu →
    `ai_router` → `api_server` içe aktarımı ölüyor, backend (dolayısıyla ACİL DURDUR ucu) HİÇ
    açılmıyordu. Ticari bir ayarın yazım hatası E-stop'un VAR OLMASINI belirleyemez (Ö.4-Y8 ruhu)."""
    ham = (os.getenv(name) or "").strip()
    if not ham:
        return default
    try:
        return tip(ham)
    except ValueError:
        logger.warning("Gecersiz %s=%r -> varsayilan %r kullaniliyor", name, ham, default)
        return default


# ── Yapılandırma ────────────────────────────────────────────────────────────
#: T3 · Y194 (sahip 2026-10-24: "jetonu kapatalım şimdilik, hangi maille girilirse girilsin ai sınırsız çalışabilsin … genel kodda
#: kapat"): SAHİP ANAHTARI. False iken ortam (`PEMF_JETON_ENFORCED`, launcher geçirir) jetonu AÇAMAZ — ölçüldü: bir makinede kullanıcı
#: ortamındaki `1` her AI analizini bakiyeden düşürüyordu. Satış açılınca True yapılır (ortam yine gerekir).
JETON_SAHIP_ACIK: bool = False
JETON_ENFORCED: bool = JETON_SAHIP_ACIK and _flag("PEMF_JETON_ENFORCED", False)

# KULLANDIKÇA ÖDE (sahip isteği 2026-08-20): önden ödeme/jeton alımı OLMAYAN üyelik. Aylık ücret
# yok; harcanan jeton birikir ve dönem sonunda (ya da eşik aşılınca) faturalanır. Hiç kullanılmazsa
# ücret çıkmaz. Bakiye 0 olsa bile analiz İZİNLİDİR — kapı, bakiye yerine BİRİKMİŞ BORCA bakar.
#
# ⚠️ Neden tavan var: ödeme alınamayan sınırsız kullanım (kartı düşen/vazgeçen hesap) riski.
# Tavan TİCARİ bir sınırdır — aşılsa bile tedavi yolu serbest kalır (tedavi/E-stop uçları kapıya hiç gelmez: `_islem_turu`).
# Tavanı YALNIZ cihaz uygular (sunucu `jeton_tuket` kullandıkça modelinde borcu sınırsız artırır — supabase_jetonlar.sql) →
# eşzamanlı analizler tavanı ayrımla (S-SGI.3 deseni, anahtar `borc:<sahip>`) paylaşır: kural "borç + ayrılmış < tavan".
BORC_TAVANI: int = max(0, _sayi("PEMF_JETON_BORC_TAVANI", 300))

# ⚠️ TEK KAYNAK EŞLEŞMESİ: bu tablo `apps/web/src/config.ts::JETON.maliyet` ile BİREBİR
# aynı olmalıdır — kullanıcı sitede "1 jeton" okuyup cihazda 3 harcarsa güven biter.
# `tests/test_jeton_yoneticisi.py::test_KARSIT_KANIT_maliyet_tablosu_WEB_ile_AYNI` kilitler.
MALIYET: dict[str, int] = {
    "goruntu": 1,
    "ses": 1,
    "sensor": 1,
    "agir_arastirma": 3,
    "ai_pro_seans": 5,
    # TD9 (Y148, sahip 2026-10-14): CANLI kamera kipi (AI Hub görüntü modülleri, kedi organ) DAKİKA BAŞINA — kareler ücretsiz.
    "canli_dakika": 1,
}

# ── CANLI KİP (TD9 · Y148) ──────────────────────────────────────────────────────────────────────────────────────────────
# Eskiden canlı kipte her BAŞARILI kare 1 jeton ("goruntu"); uyarlamalı döngüyle dakikada ~60'a kadar (SG ölçtü). Sahip kararı:
# canlı oturumun her DAKİKASI 1 jeton, yalnız en az bir SONUÇ teslim edilen dakika ("bulunamadı" / ret / hata dakikası 0).
# Kimlik: istemci canlı oturum başına rastgele bir kimlik gönderir (`CANLI_OTURUM_BASLIGI`). Dakika = oturumun bu süreçte
# görülen İLK karesinden itibaren 60 sn'lik kova → 10 dk canlı kullanım ≤ 10 jeton. İdempotans: `istek_id` =
# `canli-<oturum>-<nesil>-<dakika>` (sunucu RPC'si UNIQUE + çevrimdışı defter aynı kimliği iki kez tutmaz; nesil = bu süreçteki
# izleme kaydının kimliği — SGI-2.2) ve aynı süreçte bir kova için TEK tüketim çağrısı. `token_ledger.tur` CHECK listesine YENİ tür
# EKLENMEZ (Supabase şeması canlı): tür mevcut ("analiz" / "kullandikca"), ayırt edici `detay` = "canli_dakika". Çevrimdışı rezerv / borç tavanı / elle analiz / AI Pro
# kare muafiyeti DEĞİŞMEZ.
CANLI_OTURUM_BASLIGI = "x-pemf-canli-oturum"
_CANLI_KIMLIK = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_CANLI_KOVA_SN = 60.0
_CANLI_UNUTMA_SN = 4 * 3600.0
#: SGI-2.1: dakika başı ücret YALNIZ arayüzün canlı kamera kipi olan uçlarda (AI Hub VisionModule canlı: FGS / segmentasyon /
#: termal — retikülosit `galleryOnly` — ve Kedi Organ; T3 · Y190e sahip 2026-10-24: petri / fantom canlı kamerası da "dakika başı
#: 1 jeton", Y148 ile aynı kural). Başka bir "goruntu" ucuna (retikülosit, hastalık) başlık eklemek elle analizin kare başı
#: ücretini dakika başına ÇEVİRMEZ (Y148: elle analiz maliyeti DEĞİŞMEZ — petri / fantomda da başlıksız elle analiz kare başı).
_CANLI_UCLAR: frozenset = frozenset(
    {
        "/api/ai/vision/landmark",
        "/api/ai/vision/segmentation",
        "/api/ai/vision/thermal",
        "/api/ai/vision/cat_organ",
        "/api/ai/vision/em_petri",
        "/api/ai/vision/em_fantom",
    }
)
#: S-SGI.2 (sahip kararı 2026-10-18 "Kare tavanını şimdi ekle"): canlı dakika kovası başına kare TAVANI. Ölçüldü (SGI-2.1): canlı
#: başlığını ekleyen DEĞİŞTİRİLMİŞ istemci dakikada sınırsız elle analizi 1 jetona yaptırabiliyordu. Arayüzün canlı döngüsü kare
#: başlangıçları arasında en az 1 sn bekler (`utils/canliKare.CANLI_ASGARI_ARALIK_MS`) → meşru canlı kip 60 sn'lik kovada ≤ 60 kare.
#: Tavanı AŞAN kare canlı dakika fiyatından ÇIKAR, elle analiz gibi kare başı ("goruntu") ücretlenir (402 değil — analiz sürer).
#: Ticari ayar: `PEMF_JETON_CANLI_KARE_TAVANI` (bozuk değer → varsayılan; 1'in altı 1).
CANLI_KARE_TAVANI: int = max(1, _sayi("PEMF_JETON_CANLI_KARE_TAVANI", 60))


def _istek_yolu(request) -> str:
    return (getattr(getattr(request, "url", None), "path", "") or "").rstrip("/")


_canli_kilit = threading.Lock()
#: (sahip, oturum) → {"t0": ilk karenin monotonic anı, "son": son karenin anı, "nesil": izleme kaydının kimliği,
#: "kovalar": tüketimi başlatılmış dakika kovaları}
_canli_oturumlar: dict = {}
#: TD9: uç bu isteğin sonucunu SONUÇSUZ işaretledi ("bulunamadı") → canlı dakika bu kareyle ücretlenmez (`sonuc_izle`).
_SONUC_YOK: contextvars.ContextVar = contextvars.ContextVar("jeton_sonuc_yok", default=False)


def _yeni_canli_kaydi(t: float) -> dict:
    return {"t0": t, "son": t, "nesil": uuid.uuid4().hex[:8], "kovalar": set()}


def _canli_kova(sahip: str, oturum: str, simdi: float | None = None) -> int:
    """(sahip, oturum) için şimdiki dakika kovası; oturum ilk kez görülüyorsa başlangıç şimdi. Eski oturumlar unutulur.

    ⚠️ SGI-2.2: unutma SON kareden ölçülür (kesintisiz oturum 4 sa'te sıfırlanmaz) ve her yeni izleme kaydı YENİ bir nesil alır —
    sunucu RPC'si `istek_id`de idempotent olduğu için yeniden başlayan süreç / unutulan oturum eski kova kimliklerini YENİDEN
    kullanırsa o dakikalar ücretsiz geçiyordu (30 dk canlı + yeniden başlatma → sonraki 30 dk 0 jeton; 4 sa'ten sonraki her dakika
    ücretsiz — ölçüldü). Bedel: yeniden başlatmada en çok bir dakika iki kez ücretlenir."""
    t = time.monotonic() if simdi is None else simdi
    with _canli_kilit:
        for k in [k for k, v in _canli_oturumlar.items() if t - v.get("son", v["t0"]) > _CANLI_UNUTMA_SN]:
            _canli_oturumlar.pop(k, None)
        d = _canli_oturumlar.setdefault((sahip, oturum), _yeni_canli_kaydi(t))
        d["son"] = t
        return int((t - d["t0"]) // _CANLI_KOVA_SN)


def _canli_istek_id(sahip: str, oturum: str, kova: int) -> str:
    """SGI-2.2: kova tüketiminin idempotans anahtarı — `canli-<oturum>-<nesil>-<kova>`."""
    with _canli_kilit:
        d = _canli_oturumlar.get((sahip, oturum)) or {}
        return f"canli-{oturum}-{d.get('nesil', '0')}-{kova}"


def _canli_kare_say(sahip: str, oturum: str, kova: int) -> int:
    """S-SGI.2: (sahip, oturum)'un bu dakika kovasında KARAR'a gelen kaçıncı kare (1'den başlar). Yalnız güncel kova tutulur."""
    with _canli_kilit:
        d = _canli_oturumlar.setdefault((sahip, oturum), _yeni_canli_kaydi(time.monotonic()))
        if d.get("kare_kova") != kova:
            d["kare_kova"], d["kare_sayi"] = kova, 0
        d["kare_sayi"] += 1
        return d["kare_sayi"]


def _canli_kova_ucretli_mi(sahip: str, oturum: str, kova: int) -> bool:
    with _canli_kilit:
        d = _canli_oturumlar.get((sahip, oturum))
        return bool(d and kova in d["kovalar"])


def _canli_kovayi_al(sahip: str, oturum: str, kova: int) -> bool:
    """Kovanın tüketimini BU çağrı mı yapacak? (aynı süreçte kova başına tek tüketim — eşzamanlı iki kare iki kez düşmez)"""
    with _canli_kilit:
        d = _canli_oturumlar.setdefault((sahip, oturum), _yeni_canli_kaydi(time.monotonic()))
        if kova in d["kovalar"]:
            return False
        d["kovalar"].add(kova)
        return True


def sonucsuz_mu(veri) -> bool:
    """TD9: canlı kare sonucu SONUÇSUZ mu (kedi / yüz / organ bulunamadı; T3 · Y190e: petri / fantom `no_detection` — plaka / kuyucuk
    / tümör yok)? Arayüzün `canliKareDurumu` "bulunamadi" kuralıyla AYNI."""
    if isinstance(veri, dict) and veri.get("status") == "no_detection":
        return True
    if not isinstance(veri, dict) or veri.get("status") != "success":
        return False
    if veri.get("detected") is False or veri.get("bulunamadi_mesaji"):
        return True
    try:
        return "cat_count" in veri and int(veri.get("cat_count")) == 0
    except (TypeError, ValueError):
        return False


def sonuc_izle(fn):
    """TD9: canlı kipte kullanılan async AI uçlarının sarmalayıcısı — dönen sonuç SONUÇSUZSA (`sonucsuz_mu`) isteğin bağlamına
    işaret koyar; `jeton_tuketimi` canlı dakikayı bu kareyle ÜCRETLENDİRMEZ. Uç imzası korunur (`functools.wraps`)."""

    @functools.wraps(fn)
    async def _sar(*a, **k):
        sonuc = await fn(*a, **k)
        try:
            govde = sonuc if isinstance(sonuc, dict) else None
            if govde is None and getattr(sonuc, "body", None):
                govde = json.loads(bytes(sonuc.body).decode("utf-8"))
            if sonucsuz_mu(govde):
                _SONUC_YOK.set(True)
        except Exception:
            logger.debug("jeton: canlı kare sonucu incelenemedi (ücret kuralı değişmedi)", exc_info=True)
        return sonuc

    return _sar


# ⚠️ GÜVENLİK YOLLARI (D4.11 · B-2.14, 2026-10-10): seans, acil durdurma, sensör ve cihaz kontrolü jetondan BAĞIMSIZDIR.
# Bunu taşıyan `_islem_turu`dur (aşağıda): ai_router DIŞINDAKİ her yol ve `_SERBEST_AI_UCLARI` → None → kapı karar vermeden
# döner, `izin()`e HİÇ gelmez. Eskiden burada `GUVENLIK_YOLLARI` ({"seans_baslat", "acil_durdur", …}) kümesi vardı ve
# `izin()`in başında kontrol ediliyordu; ama `izin()`e yalnız MALIYET anahtarları geldiği için üretimde HİÇ eşleşmiyordu
# (96 rotada kesişim ∅) — testler ölü değeri koruyordu. Küme kaldırıldı; kapı
# `tests/test_jeton_kapisi_TUM_ROTALARDA_guvenlik_uclari_SERBEST_D411.py` (gerçek karar, uygulamanın TÜM rotaları).


def _yetersiz_mesaj() -> str:
    return ceviri.t("jeton.mesaj.yetersiz")


def _kimlik_gerekli_mesaj() -> str:
    return ceviri.t("jeton.mesaj.kimlikGerekli")


#: S-4B.5 + S-4BI.8 (sahip kararı 2026-10-19): ücretlendirme açıkken internetsiz analiz YOK.
def _cevrimdisi_mesaj() -> str:
    return ceviri.t("jeton.mesaj.cevrimdisi")


#: 402 yanıtında ret SEBEBİ (`Karar.sebep`: yetersiz / borc_tavani / cevrimdisi / kimlik_yok) — arayüz pencere başlığını buna göre
#: seçer (`apiClient`: "cevrimdisi" → "İnternet bağlantısı gerekli"). Tarayıcı okuyabilsin diye CORS `expose_headers`'ta (api_server).
JETON_SEBEP_BASLIGI = "X-PEMF-Jeton-Sebep"


@dataclass(frozen=True)
class Karar:
    izinli: bool
    jeton_harcandi: int = 0
    mesaj: str = ""
    sebep: str = ""


# ── EŞZAMANLI ANALİZ REZERVASYONU (S-SGI.3 · sahip kararı 2026-10-18 "Rezervasyon ekle") ─────────────────────────────────────
# Ölçülen boşluk (SGI-2.5): KARAR analiz başlarken, TÜKETİM analiz teslim edilince — aradaki pencere analiz süresi kadar. Bakiye 1
# iken eşzamanlı 4 analiz 4 teslim aldı (1 düşüldü, 3 deftere "borç"); çevrimdışı tavan 50 (49 dolu) iken eşzamanlı 4 analiz →
# defter 53. KURAL: karar anında `kalan − ayrılmış ≥ maliyet`; izinli analiz maliyetini AYIRIR; teslimde "tüketildi" işaretlenir,
# teslim edilmezse (uç istisnası, sonuçsuz canlı kare, kopan istemci) BIRAKILIR. Anahtar: ön ödemede SAHİP (`sahip:<özet>`, hesap
# bakiyesi); kullandıkça ödede de SAHİP (`borc:<özet>`, borç tavanı; 2026-10-19 — eşzamanlı analizler tavanı AŞAMAZ). Çevrimdışı
# analiz 2026-10-19'dan beri YOK (S-4B.5) → cihaz geneli çevrimdışı ayrımı kaldırıldı.
# ⚠️ Tüketilmiş ayrım, tüketimden ÖNCE başlamış bakiye okumalarına `_TUKETILMIS_IZ_SN` boyunca görünür kalır: okuma eski bakiyeyi
# getirip karar tüketimden SONRA verilirse tüketim iki kez yok sayılmasın. Süreç içidir (aynı hesabın iki cihazı arasındaki yarışı
# sunucunun satır kilidi çözer; o yarışın `yetersiz` cevabı deftere borç YAZILMAZ — `_tuket`).
_REZERV_KILIT = threading.Lock()
#: anahtar → {istek_id: [miktar, ayrılma anı, tüketim anı | None]}
_rezervler: dict = {}
#: Açık bırakma kaçarsa (karar ile tüketim bağımlılığı arasında kesilen istek) ayrımın sızıntı tavanı.
_REZERV_OMRU_SN = 300.0
#: Tüketilmiş ayrımın eski okumalara görünür kaldığı süre (bakiye okuması `_SUPABASE_TIMEOUT` ile sınırlı).
_TUKETILMIS_IZ_SN = 30.0


def _rezerve_et(
    anahtar: str, rid: str, miktar: int, kalan: int, okuma_ani: float, gereken: "int | None" = None
) -> bool:
    """`kalan` (okuma_ani'nda başlamış okumanın gördüğü) − ayrılmış ≥ `gereken` (verilmezse `miktar`) ise `miktar` kadar ayır ve
    True. Aynı `rid` (canlı dakika kovası: sunucuda idempotent) ikinci kez sayılmaz. `gereken` kullandıkça öde içindir: tavanın
    ALTINDAKİ borçta analiz izinlidir (maliyeti tavanı aşabilir — eski kural `borç < tavan` AYNEN) → `gereken=1`."""
    simdi = time.monotonic()
    with _REZERV_KILIT:
        d = _rezervler.setdefault(anahtar, {})
        for k in [
            k
            for k, (_m, t, tc) in d.items()
            if (tc is None and simdi - t > _REZERV_OMRU_SN) or (tc is not None and simdi - tc > _TUKETILMIS_IZ_SN)
        ]:
            d.pop(k, None)
        if rid in d:
            return True
        ayrilan = sum(m for (m, _t, tc) in d.values() if tc is None or tc > okuma_ani)
        if kalan - ayrilan < (miktar if gereken is None else gereken):
            return False
        d[rid] = [miktar, simdi, None]
        return True


def _rezervi_kapat(anahtar: str, rid: str, tuketildi: bool) -> None:
    with _REZERV_KILIT:
        d = _rezervler.get(anahtar) or {}
        r = d.get(rid)
        if r is None or r[2] is not None:
            return
        if tuketildi:
            r[2] = time.monotonic()
        else:
            d.pop(rid, None)


class _RezervliTuketici:
    """S-SGI.3: tüketici + ayrım. Çağrı tüketir ve ayrımı kapatır (jeton düştüyse "tüketildi", düşmediyse bırakılır); `birak()`
    tüketmeden bırakır. İkisi de yalnız bir kez etkilidir."""

    def __init__(self, fn: "Callable[[], Karar]", anahtar: str, rid: str) -> None:
        self._fn, self._anahtar, self._rid = fn, anahtar, rid

    def __call__(self) -> Karar:
        try:
            k = self._fn()
        except BaseException:
            self.birak()
            raise
        self._kapat(bool(getattr(k, "jeton_harcandi", 0)))
        return k

    def birak(self) -> None:
        self._kapat(False)

    def _kapat(self, tuketildi: bool) -> None:
        if self._rid is not None:
            _rezervi_kapat(self._anahtar, self._rid, tuketildi)
            self._rid = None


class _KesinRed:
    """Sunucu tüketimi KESİN reddetti (`jeton_tuket` → `yetersiz`). Yanlış değerlidir (eski `bool(...)` çağıranlar için "gitmedi")."""

    __slots__ = ()

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "TUKETIM_REDDEDILDI"


TUKETIM_REDDEDILDI = _KesinRed()


#: 4B-1.4: atomik yazımın geçici dosyası ve bozuk defterin karantina dosyası (`<defter>` + ek). SABİT adlar: KVKK tam temizliği
#: (`scripts/pemf_footprint.ps1`) defterle BİRLİKTE bunları da siler — ek değişirse orası da güncellenmeli.
DEFTER_GECICI_EKI = ".tmp"
DEFTER_KARANTINA_EKI = ".bozuk"


def _defter_yolu() -> Path:
    kok = os.getenv("PEMF_DATA_DIR") or str(Path.home() / ".pemf")
    p = Path(kok) / "jeton_bekleyen.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _jwt_sahip(token: str) -> str | None:
    """Jetonu kullananın kimlik ÖZETİ (JWT gövdesindeki `sub` alanının sha256 özeti; imza burada DOĞRULANMAZ — yalnız defter kaydını
    sahibine bağlamak için; sahte jetonla yapılan uzlaştırmayı sunucu RPC'si zaten reddeder). Çözülemezse None.

    ⚠️ D4.23 eki: çevrimdışı defter CİHAZ-GENELİ ve uzlaştırma "bağlantı döndü" anındaki isteğin jetonuyla (`auth.uid()`)
    gönderiyordu → aynı cihazda iki hesap varsa A'nın çevrimdışı analizleri B'nin bakiyesinden düşerdi. Kayıt artık tüketenin
    özetini taşır; uzlaştırma ve `bekleyen` sayımı yalnız o kullanıcının kayıtlarına bakar.
    Kapı: tests/test_jeton_uzlastirma_YALNIZ_TUKETEN_kullaniciya_D423b.py"""
    try:
        govde = (token or "").split(".")[1]
        sub = str(json.loads(base64.urlsafe_b64decode(govde + "=" * (-len(govde) % 4))).get("sub") or "")
    except Exception:
        return None
    return hashlib.sha256(sub.encode("utf-8")).hexdigest()[:16] if sub else None


def _kayit_miktari(k: dict) -> int:
    """Defter kaydının jeton miktarı; bozuk alan 0 (yolda kalan toplamı kararı çökertmez)."""
    try:
        return max(0, int(k.get("miktar") or 0))
    except (TypeError, ValueError):
        return 0


class JetonYoneticisi:
    """Analiz isteklerini jeton bakiyesine göre kapılar; gönderilemeyen (yolda kalan) ödemeyi defterde biriktirir.

    `bakiye_okuyucu` / `tuketim_gonderici` DIŞARIDAN verilir (test edilebilirlik + backend'in
    hangi taşıma katmanını kullandığından bağımsızlık). Gerçek bağlantı `api/tokens.ts` uçlarıdır.
    """

    def __init__(
        self,
        bakiye_okuyucu: Callable[[], int],
        tuketim_gonderici: Callable[..., bool],
        defter_yolu: Path | None = None,
        odeme_modeli: str = "on_odemeli",
        borc_okuyucu: Callable[[], int] | None = None,
        sahip: str | None = None,
        okuma_ani: float | None = None,
        yolda_kalan: int | None = None,
    ) -> None:
        """`odeme_modeli`:
        · "on_odemeli"  → plan hakkı/satın alınan jetondan düşer; bakiye biterse analiz durur.
        · "kullandikca" → önden ödeme YOK; tüketim borç olarak birikir, dönem sonunda faturalanır.
        `borc_okuyucu` yalnız kullandıkça-öde modelinde kullanılır (birikmiş, faturalanmamış jeton).
        `sahip`: jetonu kullananın kimlik özeti (`_jwt_sahip`) — yolda kalan ödeme kaydına yazılır; uzlaştırma yalnız bu sahibin
        kayıtlarını gönderir.
        `okuma_ani`: S-SGI.3 — bakiye okumasının BAŞLADIĞI an (`time.monotonic`), okuyucu önceden okunmuş değeri döndürüyorsa (kapı);
        verilmezse `on_izin` okumadan hemen önceki anı kullanır.
        `yolda_kalan`: sahibin defterde bekleyen ödemelerinin toplamı, bakiye okumasından ÖNCE ölçülmüş (kapı); verilmezse `on_izin`
        okumadan önce defterden ölçer. Önce ölçülür: okuma ile ölçüm arasında biten uzlaştırma kaydı hiçbir yerde saymasın diye.
        """
        self._bakiye_oku = bakiye_okuyucu
        self._tuketim_gonder = tuketim_gonderici
        self._defter = defter_yolu or _defter_yolu()
        self._kilit = threading.Lock()
        self._odeme_modeli = odeme_modeli
        self._borc_oku = borc_okuyucu or (lambda: 0)
        self._sahip = sahip
        self._okuma_ani = okuma_ani
        self._yolda_kalan = yolda_kalan

    # ── Yerel defter (çevrimdışı tüketim) ───────────────────────────────────
    def _defteri_oku(self) -> list[dict]:
        try:
            ham = self._defter.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except Exception:
            logger.warning("jeton: bekleyen tüketim defteri okunamadı", exc_info=True)
            return []
        try:
            return (json.loads(ham) or []) if ham.strip() else []
        except ValueError:
            # ⚠️ 4B-1.4: yarım/bozuk defter eskiden SESSİZCE boş sayılıyor, bir sonraki yazım onu EZİYORDU (uzlaşmamış tüketim
            # kalıcı kayıp). Okunan içerik AYNEN karantina dosyasına eklenir (JSON satırı; aynı içerik bir kez — elle uzlaştırma
            # için; yeniden adlandırma DEĞİL: eşzamanlı yeni yazımı karantinaya almasın) ve olay HATA olarak günlüklenir.
            kopya = self._defter.with_name(self._defter.name + DEFTER_KARANTINA_EKI)
            ozet = hashlib.sha256(ham.encode("utf-8")).hexdigest()[:16]
            try:
                onceki = kopya.read_text(encoding="utf-8") if kopya.exists() else ""
                if f'"ozet": "{ozet}"' not in onceki:
                    with open(kopya, "a", encoding="utf-8") as f:
                        f.write(
                            json.dumps({"ozet": ozet, "zaman": time.time(), "icerik": ham}, ensure_ascii=False) + "\n"
                        )
            except OSError:
                pass
            logger.error("jeton: bekleyen tüketim defteri BOZUK — içerik %s dosyasında saklandı", kopya.name)
            return []

    def _defteri_yaz(self, kayitlar: list[dict]) -> None:
        # ⚠️ 4B-1.4: ATOMİK — geçici dosya + os.replace. Yerinde yazım (önce boşalt, sonra yaz) arka plan uzlaştırma ipliği
        # (daemon) ya da süreç yazım ortasında ölürse defteri boş/yarım bırakıyordu → tüm bekleyen tüketim kayboluyordu.
        # Geçici ad SABİT (KVKK tam temizliği onu da siler); yazımlar defter kilidiyle sıralıdır (`_GATE_DEFTER_KILIT`).
        gecici = self._defter.with_name(self._defter.name + DEFTER_GECICI_EKI)
        try:
            with open(gecici, "w", encoding="utf-8") as f:
                f.write(json.dumps(kayitlar, ensure_ascii=False))
                f.flush()
                os.fsync(f.fileno())
            os.replace(gecici, self._defter)
        except Exception:
            # Defter yazılamazsa tüketim izi kaybolur ama TEDAVİ ETKİLENMEZ — sessiz düşme
            # yerine uyar (ücretlendirme eksik kalır, klinik çalışmaya devam eder). Eski defter BOZULMADAN kalır.
            logger.warning("jeton: bekleyen tüketim defteri yazılamadı", exc_info=True)
            try:
                gecici.unlink(missing_ok=True)
            except OSError:
                pass

    def bekleyen_tuketim_sayisi(self) -> int:
        return len(self._defteri_oku())

    def sahibin_bekleyen_sayisi(self) -> int:
        """Bu yöneticinin sahibine ait (uzlaşmamış) yolda kalan ödeme kaydı sayısı — `bakiye_ozeti`nin `bekleyen` alanı."""
        return sum(1 for k in self._defteri_oku() if k.get("sahip") == self._sahip)

    def sahibin_yolda_kalani(self) -> int:
        """Bu sahibin defterde bekleyen (henüz düşülmemiş) ödemelerinin jeton TOPLAMI — kararda bakiyeden düşülür / borca eklenir.

        ⚠️ Olmasaydı (ölçüldü 2026-10-19): bakiye 1, analiz teslim edildi ama düşüm gönderilemedi → sunucu hâlâ 1 der, sonraki analiz
        de izin alır; yolda kalan ödeme uzlaştırmada `yetersiz` alıp düşer → bir analiz BEDAVA."""
        return sum(_kayit_miktari(k) for k in self._defteri_oku() if k.get("sahip") == self._sahip)

    def _bekleyene_ekle(self, kayit: dict) -> None:
        with self._kilit:
            kayitlar = self._defteri_oku()
            if any(k.get("istek_id") == kayit["istek_id"] for k in kayitlar):
                return  # idempotans: aynı istek defterde iki kez durmaz
            kayitlar.append(kayit)
            self._defteri_yaz(kayitlar)

    # ── Ana kapı ────────────────────────────────────────────────────────────
    def izin(self, islem: str, istek_id: str | None = None, cihaz_id: str | None = None) -> Karar:
        """ÜCRETLİ bir işlem (MALIYET anahtarı) için jeton kapısı: karar + tüketim BİRLİKTE (`on_izin` + tüketici). Tedavi / acil
        durdurma buraya GELMEZ — onları `_islem_turu` None'a eşler ve kapı karar vermeden döner (D4.11)."""
        karar, tuketici = self.on_izin(islem, istek_id, cihaz_id)
        return tuketici() if tuketici is not None else karar

    def on_izin(
        self, islem: str, istek_id: str | None = None, cihaz_id: str | None = None
    ) -> "tuple[Karar, Callable[[], Karar] | None]":
        """İKİ AŞAMALI kapı (SG.G4-5 / G5-4, 2026-10-14): KARAR şimdi, TÜKETİM yalnız analiz BAŞARIYLA bitince.

        Eskiden `izin` kararla birlikte jetonu da düşürüyordu ve router kapısı ucun ÖNÜNDE koşuyordu → modalite / makullik kapısının
        422'si, model hatasının 500'ü, istemcinin iptal ettiği canlı kare de 1 jeton yakıyordu (ölçüldü 2026-10-13: segmentasyon
        canlı kipinde 63 kare 422 aldı, hepsi ücretlendi). Dönüş: (karar, tüketici) — izinsizse tüketici None; izinliyse
        tüketici() tüketimi YAPAR ve son kararı döndürür (fiyat, idempotans, yolda kalan ödeme defteri AYNEN). Kural (1 analiz =
        maliyet tablosu) DEĞİŞMEDİ; değişen yalnız sıra: ücret, sonucu teslim edilen analize."""
        # 2) Bayrak kapalı → no-op (satış açılana kadar canlı davranış değişmez; internet şartı da YOK — S-4B.5 kapsamı).
        if not JETON_ENFORCED:
            return Karar(izinli=True, sebep="enforce_kapali"), None

        maliyet = MALIYET.get(islem, MALIYET["goruntu"])
        iid = istek_id or f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:12]}"
        # Yolda kalan ödeme bakiye okumasından ÖNCE ölçülür (`__init__` notu); kapı okumadan önce ölçüp verir.
        yolda = self._yolda_kalan if self._yolda_kalan is not None else self.sahibin_yolda_kalani()
        okuma_ani = self._okuma_ani if self._okuma_ani is not None else time.monotonic()

        # 2b) KULLANDIKÇA ÖDE: önden ödeme yok → bakiyeye BAKILMAZ. Kapı, birikmiş (henüz
        # faturalanmamış) borca bakar. Tavan aşılmadıysa analiz serbesttir ve tüketim
        # "kullandikca" türüyle kaydedilir; dönem sonunda faturalanır.
        if self._odeme_modeli == "kullandikca":
            try:
                borc = int(self._borc_oku())
            except Exception:
                # S-4B.5 (2026-10-19): eskiden borç 0 sayılıyordu (fail-open). Ücret çevrimiçi düşüldüğü için borç okunamıyorsa
                # yeni analiz başlatılmaz; tedavi yolu bu kapıya hiç gelmez.
                return Karar(izinli=False, mesaj=_cevrimdisi_mesaj(), sebep="cevrimdisi"), None
            borc += yolda

            def tuket() -> Karar:
                return self._tuket(maliyet, islem, iid, cihaz_id, tur="kullandikca")

            if not BORC_TAVANI:
                return Karar(izinli=True, jeton_harcandi=maliyet, sebep="tuketilecek"), tuket
            # 2026-10-19 (eşzamanlılık açığı): eskiden yalnız `borç < tavan` bakılıyordu — tavanın 1 altındaki borçta eşzamanlı N
            # analiz N izin alıyordu (tavan cihaz tarafının işi; sunucu borcu sınırsız artırır). Kural AYNEN, ayrımla.
            anahtar = f"borc:{self._sahip or ''}"
            if borc >= BORC_TAVANI or not _rezerve_et(anahtar, iid, maliyet, BORC_TAVANI - borc, okuma_ani, gereken=1):
                return Karar(
                    izinli=False,
                    sebep="borc_tavani",
                    mesaj=(ceviri.t("jeton.mesaj.borcTavani")),
                ), None
            return Karar(izinli=True, jeton_harcandi=maliyet, sebep="tuketilecek"), _RezervliTuketici(
                tuket, anahtar, iid
            )

        # 3) Bakiye okunamıyorsa (internet yok) → analiz BAŞLATILMAZ (S-4B.5 + S-4BI.8, sahip kararı 2026-10-19). Eskiden
        # çevrimdışı tavana (50) kadar izin + deftere borç yazılıyordu; sunucunun reddettiği borç defterde "eksi bakiye" olarak
        # bekliyordu. Seans / acil durdurma / sensör bu kapıya hiç gelmez (`_islem_turu`).
        try:
            bakiye = int(self._bakiye_oku())
        except Exception:
            return Karar(izinli=False, mesaj=_cevrimdisi_mesaj(), sebep="cevrimdisi"), None

        # 4) Bakiye yetersiz → YALNIZ analiz reddedilir (tedavi yolu buraya hiç gelmez — `_islem_turu`).
        # S-SGI.3: aynı hesabın bu süreçte SÜREN analizlerinin ayırdığı jeton da düşülür (eşzamanlı N analiz bakiyeyi aşamaz).
        # 2026-10-19: yolda kalan ödeme de düşülür (sunucu henüz görmedi; düşülmezse aynı jeton ikinci analize verilirdi).
        bakiye -= yolda
        anahtar = f"sahip:{self._sahip or ''}"
        if bakiye < maliyet or not _rezerve_et(anahtar, iid, maliyet, bakiye, okuma_ani):
            return Karar(izinli=False, mesaj=_yetersiz_mesaj(), sebep="yetersiz"), None

        # 5) Tüketimi gönder. Gönderim düşerse analiz DURMAZ — kayıt deftere düşer (yolda kalan ödeme; sonra yeniden denenir).
        return Karar(izinli=True, jeton_harcandi=maliyet, sebep="tuketilecek"), _RezervliTuketici(
            lambda: self._tuket(maliyet, islem, iid, cihaz_id, tur="analiz"), anahtar, iid
        )

    def _tuket(self, maliyet: int, islem: str, iid: str, cihaz_id: str | None, tur: str) -> Karar:
        """Tüketimi gönderir; gönderilemezse (ağ koptu) YOLDA KALAN ÖDEME olarak deftere yazar — sahibin sonraki çevrimiçi isteğinde
        yeniden gönderilir, o zamana dek kararlarda bakiyeden düşülür (iki ödeme modelinde de ortak; sahip: "Bir süre yeniden dene")."""
        try:
            sonuc = self._tuketim_gonder(miktar=maliyet, tur=tur, detay=islem, istek_id=iid, cihaz_id=cihaz_id)
        except Exception:
            sonuc = False
        if sonuc is TUKETIM_REDDEDILDI:
            # S-SGI.3: sunucu KESİN reddetti (bakiye başka cihazda / süreçte bitti) — deftere "borç" YAZILMAZ: kayıt bakiye
            # yüklenene dek her uzlaştırmada yeniden reddedilirdi. Analiz teslim edildi; bu tek analiz ücretsiz kalır (sahip kararı).
            logger.warning("jeton: sunucu tüketimi reddetti (yetersiz) — analiz teslim edildi, deftere borç yazılmadı")
            return Karar(izinli=True, jeton_harcandi=0, sebep="sunucu_yetersiz")
        gitti = bool(sonuc)
        if not gitti:
            self._bekleyene_ekle(
                {
                    "istek_id": iid,
                    "miktar": maliyet,
                    "tur": tur,
                    "detay": islem,
                    "cihaz_id": cihaz_id,
                    "sahip": self._sahip,
                }
            )
        return Karar(izinli=True, jeton_harcandi=maliyet, sebep="tuketildi")

    # ── Uzlaştırma ──────────────────────────────────────────────────────────
    def bekleyenleri_uzlastir(self) -> int:
        """Yolda kalan ödemeleri gönderir. Başarılı olanlar defterden düşer; dönüş gönderilen sayısı.

        ⚠️ GEÇİCİ hata (ağ, 5xx, bilinmeyen red) kaydı SİLMEZ: silseydik tüketim sessizce kaybolur ve kullanıcı bedava analiz yapmış
        olurdu. `istek_id` sayesinde tekrar gönderim güvenlidir — sunucu ikinciyi yok sayar.
        ⚠️ KESİN red (`TUKETIM_REDDEDILDI` = sunucu `yetersiz`) kaydı DÜŞÜRÜR (S-4BI.8, sahip kararı 2026-10-19 "eksi bakiyeyi
        temizleyelim"): eskiden (Y24) kayıt bakiye yüklenene dek defterde "eksi bakiye" olarak bekliyor, her uzlaştırmada yeniden
        reddediliyordu. Yolda kalan ödeme kararda bakiyeden düşüldüğü için red yalnız başka cihazın aynı hesabı harcadığı yarışta
        olur — teslimdeki kesin redle (`_tuket`) aynı sonuç: o analiz ücretsiz kalır, günlüğe yazılır.
        """
        # D4.23 eki: YALNIZ bu yöneticinin sahibine ait kayıtlar (başka kullanıcının tüketimi bu jetonla gönderilmez).
        kayitlar = [k for k in self._defteri_oku() if k.get("sahip") == self._sahip]
        if not kayitlar:
            return 0
        gonderilen_idler: set = set()
        reddedilen_idler: set = set()
        for k in kayitlar:
            try:
                sonuc = self._tuketim_gonder(**{a: d for a, d in k.items() if a != "sahip"})
            except Exception:
                sonuc = False
            if sonuc is TUKETIM_REDDEDILDI:
                reddedilen_idler.add(k.get("istek_id"))
            elif sonuc:
                gonderilen_idler.add(k.get("istek_id"))
        if reddedilen_idler:
            logger.warning(
                "jeton: %d yolda kalan ödeme sunucuda KESİN reddedildi (yetersiz) — defterden düşüldü, borç tutulmaz",
                len(reddedilen_idler),
            )
        dusulecek = gonderilen_idler | reddedilen_idler
        with self._kilit:
            # ⚠️ D4.23: defter kilit altında YENİDEN okunur ve yalnız gönderilenler düşülür. Eskiden gönderim öncesi okunan
            # liste (`kalan`) defterin ÜZERİNE yazılıyordu → gönderim sürerken eşzamanlı bir analizin deftere düşen
            # tüketimi SİLİNİYORDU (bedava analiz). Uzlaştırma artık arka planda koştuğu için bu yarış gerçek.
            guncel = self._defteri_oku()
            self._defteri_yaz([k for k in guncel if k.get("istek_id") not in dusulecek])
        return len(gonderilen_idler)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# FastAPI KAPISI — JETON-SISTEMI Adım 4 (2026-08-22)
#
# Bu bölüm yazılana kadar modül HİÇBİR üretim kodundan çağrılmıyordu: `PEMF_JETON_ENFORCED`
# açılsa bile davranış değişmezdi (sessiz no-op tuzağı — eksik-taramasının P1 bulgusu).
# Bağlantı entitlement.py deseniyle aynı: router-seviyesi bağımlılık (`ai_router`).
#
# ⚠️ TAŞIMA KATMANI KARARI: belge "tüketimi /api/tokens ucuna bağla" diyordu; Supabase RPC'ye
# DOĞRUDAN bağlandı (`rpc/jeton_bakiyem` + `rpc/jeton_tuket`, kullanıcının kendi JWT'siyle).
# Neden: (a) entitlement.py abonelik için AYNI deseni kullanıyor — cihaz Supabase'le zaten
# konuşuyor, siteye fazladan bir sıçrama tek yeni arıza noktası eklerdi; (b) canlı şema
# sertleştirmesinden (2026-08-21) beri bu RPC'ler tam bu amaç için var: kimlik PARAMETREDEN
# değil auth.uid()'ten gelir (spoof edilemez), idempotans `istek_id` UNIQUE'iyle RPC içinde.
# `api/tokens.ts` sitenin (Hesabım) yüzeyi olarak kalır.
# ═════════════════════════════════════════════════════════════════════════════════════════════

from fastapi import HTTPException, Request  # noqa: E402  (bölüm-yerel import, üst blok dokunulmadı)

_SUPABASE_TIMEOUT: float = max(1.0, _sayi("PEMF_JETON_TIMEOUT", 4.0, float))


def _bearer_token(request: Request) -> str:
    h = request.headers.get("authorization") or ""
    return h[7:].strip() if h.lower().startswith("bearer ") else ""


# ── Uç → işlem eşlemesi ──────────────────────────────────────────────────────────
# TAM YOL pinlenir (bu deponun dersi: parça-eşleme kapıları string hileleriyle deliniyor).
# Kapılanmayan ai_router uçları (analiz DEĞİL):
#   pro/stop            → seans DURDURMA: güvenlik sınıfı, hiçbir koşulda kapılanmaz
#   pro/status          → durum okuma
#   pro/approve|reject  → operatör onay kararı (analiz zaten propose aşamasında yapıldı)
#   ai_pro/frame        → seans İÇİ kare akışı — ücret seans-başına (pro/start = 5) alınır;
#                         kare başına almak 5 jetonluk seansı yüzlerce jetona çevirirdi
#   pro/organ|calibrate → kalibrasyon/kurulum
#   pro/hazirlik/*      → önizleme başlat/durdur: BOBİN SÜRMEZ, SEANS BAŞLATMAZ (2026-08-25 web
#                         kapalı-döngü düzeltmesi) — analiz değil kurulum adımı
#   hazirlik (GET)      → self-test/envanter okuma; `_islem_turu` HTTP metodunu görmediği için
#                         listeye alınmazsa "goruntu" (1 jeton) sınıfına düşerdi
# ⚠️ 2026-09-08: bu listede `/api/ai/pro/frame` yazıyordu — BÖYLE BİR ROTA HİÇ OLMADI. Gerçek uç
# `/api/ai/ai_pro/frame` (ai_router.py'deki `@ai_router.post` rotası, tests/test_route_contract.py) → eşleşme tutmuyor,
# her kare "goruntu" sınıfına düşüyordu. FREE_MODE=true bunu gizliyordu; ücretlendirme açılsaydı
# 5 jetonluk seans kare başına ücretlenirdi. Ölü girdi düzeltildi (test de gerçek yola pinlendi).
_SERBEST_AI_UCLARI: frozenset = frozenset(
    {
        "/api/ai/pro/stop",
        "/api/ai/pro/status",
        "/api/ai/pro/approve",
        "/api/ai/pro/reject",
        "/api/ai/ai_pro/frame",
        "/api/ai/pro/organ",
        "/api/ai/pro/calibrate",
        "/api/ai/pro/hazirlik/baslat",
        "/api/ai/pro/hazirlik/durdur",
        "/api/ai/hazirlik",
    }
)
# Ağır araştırma (belge: patoloji, RNA, tomografi, yara-kapanma = 3 jeton).
# scratch: KARAR 0.6 (2026-08-26, docs/scratch-entegrasyon-plani.md) — 872MB CPN
# araştırma analizi histopath sınıfıdır; explain (XAI) EK jeton DEĞİL (karar 0.5:
# jetonlama uç-çağrısı başınadır, explain parametresi ayrıca sayılmaz).
_AGIR_UCLAR: frozenset = frozenset(
    {
        "/api/ai/vision/kidney_ct",
        "/api/ai/vision/histopath",
        "/api/ai/vision/scratch",
    }
)


def _islem_turu(path: str) -> "str | None":
    """Uçtan MALIYET anahtarına eşleme; None = bu kapının işi değil (serbest)."""
    p = (path or "").rstrip("/")
    if not p.startswith("/api/ai/"):
        return None  # tedavi/kontrol uçları başka router'larda — jeton onların işine karışmaz
    if p in _SERBEST_AI_UCLARI:
        return None
    if p == "/api/ai/pro/start":
        return "ai_pro_seans"
    if p == "/api/ai/pro/propose":
        # Öneri, sensör verisi üzerinde gerçek bir analizdir (seans HENÜZ başlamadı) → sensor=1.
        return "sensor"
    if p.startswith("/api/ai/rna/") or p in _AGIR_UCLAR:
        return "agir_arastirma"
    if p.startswith("/api/ai/sound/"):
        return "ses"
    return "goruntu"


# ── Supabase taşıma katmanı (entitlement deseni; testler bu iki fonksiyonu yamalar) ──
def _bakiye_satiri_oku(token: str) -> dict:
    """rpc/jeton_bakiyem — kullanıcının kendi satırı (auth.uid()). Hata → raise (çevrimdışı yolu)."""
    from utils.secrets_manager import get_secret

    base = (get_secret("supabase_url", default="", generate=False) or "").rstrip("/")
    anon = (get_secret("supabase_anon_key", default="", generate=False) or "").strip()
    if not base or not anon or not token:
        raise ConnectionError("jeton: supabase yapilandirmasi/token yok")
    import requests

    r = requests.post(
        base + "/rest/v1/rpc/jeton_bakiyem",
        json={},
        headers={"apikey": anon, "Authorization": "Bearer " + token, "Content-Type": "application/json"},
        timeout=_SUPABASE_TIMEOUT,
    )
    r.raise_for_status()
    rows = r.json() if r.content else []
    if not isinstance(rows, list) or not rows:
        # Satırı olmayan kullanıcı = henüz jeton yüklenmemiş → sıfır bakiye (kapı için doğru okuma).
        return {"aylik_hak": 0, "satin_alinan": 0, "odeme_modeli": "on_odemeli", "kullandikca_borc": 0}
    return rows[0]


def _tuketim_gonder_canli(token: str, **k) -> "bool | _KesinRed":
    """rpc/jeton_tuket — atomik düşüm (satır kilidi + istek_id idempotansı RPC içinde). Kesin `yetersiz` → `TUKETIM_REDDEDILDI`."""
    from utils.secrets_manager import get_secret

    base = (get_secret("supabase_url", default="", generate=False) or "").rstrip("/")
    anon = (get_secret("supabase_anon_key", default="", generate=False) or "").strip()
    if not base or not anon or not token:
        return False
    import requests

    try:
        r = requests.post(
            base + "/rest/v1/rpc/jeton_tuket",
            json={
                "p_miktar": int(k.get("miktar") or 0),
                "p_tur": str(k.get("tur") or "analiz"),
                "p_detay": k.get("detay"),
                "p_istek_id": str(k.get("istek_id") or ""),
                "p_cihaz_id": k.get("cihaz_id"),
            },
            headers={"apikey": anon, "Authorization": "Bearer " + token, "Content-Type": "application/json"},
            timeout=_SUPABASE_TIMEOUT,
        )
        if not r.ok:
            return False
        sonuc = r.json() if r.content else {}
        if isinstance(sonuc, dict) and sonuc.get("ok") is False and sonuc.get("sebep") == "yetersiz":
            return TUKETIM_REDDEDILDI  # S-SGI.3: kesin red (yanlış değerli; uzlaştırmada kayıt DÜŞER — S-4BI.8, 2026-10-19)
        return bool(isinstance(sonuc, dict) and sonuc.get("ok"))
    except Exception:
        return False


# Çevrimdışı defter yazımları per-istek yönetici örneklerinden gelir; dosya yarışını tek
# modül-kilidiyle serileştir (örnek başına kilit dosyayı KORUMAZDI).
_GATE_DEFTER_KILIT = threading.Lock()


def _defter_yoneticisi(
    tuketim_gonderici: Callable[..., bool] | None = None, sahip: str | None = None
) -> JetonYoneticisi:
    """Yalnız DEFTER işlemleri (bekleyen sayımı / uzlaştırma) için yönetici — bakiye okunmaz; kilit kapının defter kilidiyle ORTAK.

    ⚠️ D4.23 (B-2.15): `bakiye_ozeti` eskiden `JetonYoneticisi()` ARGÜMANSIZ kuruyordu → kurucu iki zorunlu argüman ister,
    `TypeError` yutuluyor ve uç defterde kayıt varken HER ZAMAN `bekleyen: 0` diyordu."""
    y = JetonYoneticisi(
        bakiye_okuyucu=lambda: 0, tuketim_gonderici=tuketim_gonderici or (lambda **k: False), sahip=sahip
    )
    y._kilit = _GATE_DEFTER_KILIT
    return y


# ── BAĞLANTI DÖNÜNCE UZLAŞTIRMA — D4.23 (B-2.16, Y24) ─────────────────────────────────────────────────────────────
# `bekleyenleri_uzlastir` tanımlıydı ama HİÇBİR üretim yolu çağırmıyordu → zorlama açılınca defter hiç uzlaşmaz, tavana
# (o zamanki `PEMF_JETON_OFFLINE_TAVAN`) takılan klinik analiz yapamaz, tüketim faturalanmazdı. Y24 (sahip, önerilen): defterdeki
# tüketim bağlantı dönünce GERİYE DÖNÜK düşülür. 2026-10-19'dan beri (S-4B.5) defterde yalnız YOLDA KALAN ÖDEME olur (çevrimdışı
# analiz yok); uzlaştırma onu "bir süre yeniden dener" (sahip kararı). RPC kullanıcının KENDİ JWT'siyle çağrıldığı için
# (auth.uid()) cihazın elinde arka planda kullanabileceği bir kimlik yok → tetik "bağlantı döndü" anıdır: bir bakiye okuması
# ya da analiz isteği Supabase'e ULAŞTIĞINDA, o isteğin jetonuyla. Arka planda ve TEK UÇUŞLA koşar (isteği bekletmez,
# aynı kaydı iki iplik göndermez); hata kaydı SİLMEZ (defterde kalır, sonraki bağlantıda yeniden denenir).
_UZLASTIRMA_TEK_UCUS = threading.Lock()
_son_uzlastirma: "threading.Thread | None" = None


def _uzlastirmayi_tetikle(token: str) -> bool:
    """Defterde bekleyen varsa uzlaştırmayı arka planda başlatır; başlattıysa True. Asla fırlatmaz (ticari kapı analizi bozmaz)."""
    global _son_uzlastirma
    sahip = _jwt_sahip(token)
    try:
        # Kimliği çözülemeyen jetonla UZLAŞTIRILMAZ: kayıt kime aitse onun bakiyesinden düşmeli (D4.23 eki).
        if not sahip or _defter_yoneticisi(sahip=sahip).sahibin_bekleyen_sayisi() == 0:
            return False
        if not _UZLASTIRMA_TEK_UCUS.acquire(blocking=False):
            return False  # süren uzlaştırma var
    except Exception:
        return False

    def _calis() -> None:
        try:
            n = _defter_yoneticisi(lambda **k: _tuketim_gonder_canli(token, **k), sahip=sahip).bekleyenleri_uzlastir()
            if n:
                logger.info("jeton: %d yolda kalan ödeme uzlaştırıldı (bağlantı döndü)", n)
        except Exception:
            logger.warning("jeton: yolda kalan ödeme uzlaştırması düştü — kayıtlar defterde KALIR", exc_info=True)
        finally:
            _UZLASTIRMA_TEK_UCUS.release()

    try:
        t = threading.Thread(target=_calis, name="jeton-uzlastirma", daemon=True)
        _son_uzlastirma = t
        t.start()
    except Exception:
        _UZLASTIRMA_TEK_UCUS.release()
        logger.warning("jeton: uzlaştırma ipliği başlatılamadı", exc_info=True)
        return False
    return True


def _jeton_kapisi_karari(request: Request) -> None:
    """Senkron karar + tüketim (test yüzeyi; üretim `jeton_gate` + `jeton_tuketimi` AYNI iki parçayı ayrı anlarda çağırır).
    İzin yoksa HTTPException(402) fırlatır."""
    tuketici = _jeton_on_karari(request)
    if tuketici is not None:
        tuketici()


def _red(karar: Karar) -> HTTPException:
    """402: ticari red. Mesaj TEDAVİNİN ETKİLENMEDİĞİNİ açıkça söyler (hasta güvenliği algısı); sebep `JETON_SEBEP_BASLIGI`nda."""
    return HTTPException(
        status_code=402,
        detail=karar.mesaj or _yetersiz_mesaj(),
        headers={JETON_SEBEP_BASLIGI: karar.sebep or "yetersiz"},
    )


def _jeton_on_karari(request: Request) -> "Callable[[], Karar] | None":
    """Senkron KARAR gövdesi: izin yoksa HTTPException(402); izinliyse tüketiciyi (ya da serbest uçta None) döndürür — jeton
    BURADA DÜŞMEZ (SG.G4-5 / G5-4: tüketim yalnız analiz başarıyla bitince, `jeton_tuketimi`)."""
    # ⚠️ SIRA: serbest-uç ve bayrak kontrolü HER ŞEYDEN ÖNCE — pro/stop için ağ çağrısı bile
    # yapılmaz (ağ gecikmesi seans durdurmayı geciktiremez; testle kilitli).
    islem = _islem_turu(getattr(getattr(request, "url", None), "path", "") or "")
    if islem is None:
        return None
    if not JETON_ENFORCED:
        return None  # sahip kararı: satış kapalı — kapı bağlı ama uykuda (bayrak tek anahtar)

    token = _bearer_token(request)
    if not _jwt_sahip(token):
        # ⚠️ 4B-1.5 (Y24): kimliği çözülemeyen (jetonsuz / `sub`'sız) istek eskiden bağlantı VARKEN bile "çevrimdışı" yoluna düşüp
        # İZİN alıyor, deftere SAHİPSİZ kayıt yazıyordu: hiçbir hesaptan düşülmez (bedava analiz; eki uzlaştırmayı sahibe bağladı) ama
        # cihaz-geneli çevrimdışı tavanı doldururdu (tavan 2026-10-19'da kaldırıldı). Ücretlendirme açıkken yeni AI analizi hesap
        # ister; tedavi / E-stop / seans bu kapıya HİÇ gelmez (`_islem_turu` → None, Ö.4-Y8).
        raise _red(Karar(izinli=False, mesaj=_kimlik_gerekli_mesaj(), sebep="kimlik_yok"))

    # ── TD9 (Y148): canlı kip — dakika başına (SGI-2.1: yalnız canlı kipli uçlar) ─────────────────────────────────────────
    oturum = (request.headers.get(CANLI_OTURUM_BASLIGI) or "").strip() if hasattr(request, "headers") else ""
    canli = islem == "goruntu" and _istek_yolu(request) in _CANLI_UCLAR and bool(_CANLI_KIMLIK.match(oturum))
    if canli:
        sahip = _jwt_sahip(token) or ""
        kova = _canli_kova(sahip, oturum)
        if _canli_kare_say(sahip, oturum, kova) > CANLI_KARE_TAVANI:
            # S-SGI.2: meşru canlı döngünün (≥ 1 sn) bir dakikada ulaşamayacağı kare → canlı dakika fiyatından çıkar, kare başı
            # ("goruntu") ücretlenir — ödenmiş dakikanın "kareler ücretsiz" kısa devresi de UYGULANMAZ.
            canli = False
        elif _canli_kova_ucretli_mi(sahip, oturum, kova):
            # SGI-2.3 (Y148 "kareler ücretsiz"): bu canlı dakika ZATEN ödendi → kare ağa çıkmadan serbest; bakiye okunmaz, 402
            # verilmez (eskiden son jetonla ödenen dakikanın sonraki kareleri bakiye 0 görüp 402 alıyordu — ölçüldü).
            return None
    try:
        # 2026-10-19: sahibin yolda kalan ödemesi okumadan ÖNCE (JetonYoneticisi `yolda_kalan` notu). Ölçülemezse 0 (yardımcı hesap).
        yolda = _defter_yoneticisi(sahip=_jwt_sahip(token)).sahibin_yolda_kalani()
    except Exception:
        yolda = 0
    okuma_ani = time.monotonic()  # S-SGI.3: okumanın başladığı an — okuma sürerken tamamlanan tüketim yok sayılmasın
    try:
        satir = _bakiye_satiri_oku(token)
    except Exception:
        satir = None  # internet yok → JetonYoneticisi analizi BAŞLATMAZ (S-4B.5: 402 `cevrimdisi`)
    if satir is not None:
        _uzlastirmayi_tetikle(token)  # D4.23 (Y24): bağlantı DÖNDÜ → yolda kalan ödeme arka planda uzlaşır

    if satir is None:

        def _okuyucu() -> int:
            raise ConnectionError("jeton: bakiye okunamadi (cevrimdisi)")

        model, borc = "on_odemeli", 0
    else:
        _kalan = int(satir.get("aylik_hak") or 0) + int(satir.get("satin_alinan") or 0)

        def _okuyucu(_kalan=_kalan) -> int:
            return _kalan

        model = str(satir.get("odeme_modeli") or "on_odemeli")
        borc = int(satir.get("kullandikca_borc") or 0)

    yonetici = JetonYoneticisi(
        bakiye_okuyucu=_okuyucu,
        tuketim_gonderici=lambda **k: _tuketim_gonder_canli(token, **k),
        odeme_modeli=model,
        borc_okuyucu=lambda borc=borc: borc,
        sahip=_jwt_sahip(token),  # D4.23 eki: yolda kalan ödeme kaydı tüketene bağlanır
        okuma_ani=okuma_ani,
        yolda_kalan=yolda,
    )
    yonetici._kilit = _GATE_DEFTER_KILIT  # defter dosyası paylaşımlı → kilit de paylaşımlı

    if canli:
        karar, tuketici = yonetici.on_izin("canli_dakika", istek_id=_canli_istek_id(sahip, oturum, kova))
        if karar.izinli and tuketici is not None:
            asil = tuketici

            def _canli_tuketici(asil=asil, sahip=sahip, oturum=oturum, kova=kova) -> Karar:
                if not _canli_kovayi_al(sahip, oturum, kova):
                    _tuketmeden_birak(asil)  # S-SGI.3: kova başka karede ödendi — bu karenin ayrımı bırakılır
                    return Karar(izinli=True, sebep="canli_dakika_odendi")
                return asil()

            _canli_tuketici.canli = True  # type: ignore[attr-defined]
            _canli_tuketici.birak = lambda asil=asil: _tuketmeden_birak(asil)  # type: ignore[attr-defined]
            tuketici = _canli_tuketici
        if not karar.izinli:
            raise _red(karar)
        return tuketici

    karar, tuketici = yonetici.on_izin(islem)
    if not karar.izinli:
        raise _red(karar)
    return tuketici


#: `jeton_gate`in izinli analize bıraktığı tüketicinin istek kapsamındaki adı (`request.state`; `jeton_tuketimi` okur).
_BEKLEYEN_TUKETIM = "jeton_bekleyen_tuketim"


def _tuketmeden_birak(tuketici) -> None:
    """S-SGI.3: analiz teslim edilmedi → tüketicinin ayırdığı jeton / defter yeri bırakılır (ayrımsız tüketicide no-op)."""
    birak = getattr(tuketici, "birak", None)
    if callable(birak):
        try:
            birak()
        except Exception:
            logger.debug("jeton: ayrım bırakılamadı (ömür dolunca düşer)", exc_info=True)


async def jeton_gate(request: Request) -> None:
    """Router-seviyesi bağımlılık — KARAR (402 ya da izin). Bloklayan Supabase çağrısı threadpool'a atılır (belge 4.1;
    ai_queue_gate ile aynı gerekçe — event loop bloklanmasın). İzinli analizin tüketicisi `request.state`e bırakılır; jetonu
    `jeton_tuketimi` (aynı router, `scope="function"`) yalnız uç İSTİSNASIZ dönünce düşürür (SG.G4-5 / G5-4).

    ⚠️ O-1.1 (Ö.4-Y8): serbest uç (AI Pro durdurma `/api/ai/pro/stop` …) ve KAPALI bayrak kararı OLAY DÖNGÜSÜNDE verilir —
    ortak iş parçacığı havuzuna HİÇ girmez. Eskiden bu ucuz karar da `to_thread`'deydi: havuz asılı G/Ç ile doluyken AI Pro
    durdurması bu bağımlılıkta bekliyor, STOP porta gitmiyordu (ölçüldü, 1-G önce-kırmızı 30/30). Ağ gereken yol havuzda."""
    import asyncio

    if _islem_turu(getattr(getattr(request, "url", None), "path", "") or "") is None or not JETON_ENFORCED:
        return
    tuketici = await asyncio.to_thread(_jeton_on_karari, request)
    if tuketici is not None:
        setattr(request.state, _BEKLEYEN_TUKETIM, tuketici)


#: SGI-2.4: kopma yoklamasının üst sınırı (sn). Bağlı istemcide başarılı analiz yanıtı en çok bu kadar gecikir (yalnız tüketici varken).
_KOPMA_YOKLAMA_SN = 0.02


async def _istemci_koptu_mu(request: Request) -> bool:
    """İstemci yanıtı beklemeden koptu mu? ⚠️ SGI-2.4: `Request.is_disconnected()` iptal edilmiş kapsamda TEK yoklama yapar;
    `@app.middleware("http")` (BaseHTTPMiddleware — api_server'da üç tane) iç uygulamaya verdiği `receive`'i görev grubuyla
    sardığı için o yoklama her zaman boş döner → kopan istemci de jeton ödüyordu (ASGI katında ölçüldü). Kısa ve SINIRLI bir
    gerçek bekleme ara katmanlardan geçer: uvicorn kopmuş bağlantıda `http.disconnect`ı beklemeden verir.
    Kapı: tests/test_jeton_KOPAN_istemci_ARA_KATMAN_arkasinda_DUSMEZ_SGI_2_4.py"""
    if await request.is_disconnected():
        return True
    import anyio

    mesaj: dict = {}
    with anyio.move_on_after(_KOPMA_YOKLAMA_SN):
        mesaj = await request.receive()
    return mesaj.get("type") == "http.disconnect"


async def jeton_tuketimi(request: Request):
    """Router-seviyesi `yield` bağımlılığı — TÜKETİM (SG.G4-5 / G5-4, 2026-10-14). `Depends(jeton_tuketimi, scope="function")`:
    çıkış kodu uç DÖNDÜKTEN SONRA, yanıt gönderilmeden ÖNCE koşar; uç istisnayla biterse (modalite / makullik 422, model 500,
    GPU servisi hatası, kimlik / onay 4xx) FastAPI istisnayı `yield` noktasına fırlatır ve aşağısı HİÇ koşmaz → jeton DÜŞMEZ.
    İstemci yanıtı beklemeden koptuysa (canlı karenin iptali, sökülen ekran) sonuç teslim edilemez → jeton DÜŞMEZ.

    ⚠️ Serbest uç / kapalı bayrak: `jeton_gate` tüketici bırakmaz → burada havuza da ağa da girilmez (O-1.1, Ö.4-Y8).
    ⚠️ Tüketim hiçbir koşulda başarılı yanıtı bozmaz: gönderim düşerse kayıt yerel deftere yazılır (`_tuket`), beklenmeyen hata
    yalnız günlüğe gider.
    ⚠️ S-SGI.3: teslim edilmeyen her yolda (istisna, sonuçsuz canlı kare, kopan istemci) kararın AYIRDIĞI jeton bırakılır."""
    try:
        yield
    except BaseException:
        _tuketmeden_birak(getattr(request.state, _BEKLEYEN_TUKETIM, None))
        setattr(request.state, _BEKLEYEN_TUKETIM, None)
        raise
    tuketici = getattr(request.state, _BEKLEYEN_TUKETIM, None)
    if tuketici is None:
        return
    setattr(request.state, _BEKLEYEN_TUKETIM, None)
    if getattr(tuketici, "canli", False) and _SONUC_YOK.get():
        # TD9: canlı karede kedi / yüz / organ BULUNAMADI → bu kare dakikayı ücretlendirmez (kedisiz dakika 0 jeton).
        _tuketmeden_birak(tuketici)
        return
    try:
        if await _istemci_koptu_mu(request):
            logger.info(
                "jeton: istemci yanıtı beklemeden koptu — sonuç teslim edilemedi, jeton DÜŞÜLMEDİ (%s)",
                request.url.path,
            )
            _tuketmeden_birak(tuketici)
            return
    except Exception:
        pass  # kopma sorusu yanıtlanamazsa analiz teslim edilecek sayılır (bugünkü davranış)
    import asyncio

    try:
        await asyncio.to_thread(tuketici)
    except Exception:
        logger.warning("jeton: tüketim kaydedilemedi (analiz yanıtı etkilenmedi)", exc_info=True)


# ══════════════════════════════════════════════════════════════════════════════════
# KULLANICIYA GÖRÜNÜR BAKİYE (sahip isteği 2026-09-13: "kullanıcı da kalan hakkını görmeli")
# ══════════════════════════════════════════════════════════════════════════════════
#
# ⚠️ TASARIM KARARI — BAYRAK KAPALIYKEN HİÇBİR ŞEY GÖSTERİLMEZ.
# Bugün canlıda `PEMF_JETON_ENFORCED=0` (satış açılmadı) ve hiçbir kullanıcının bakiye satırı
# yok. O durumda "0 jeton" yazmak DÜPEDÜZ YANLIŞ olurdu: kullanıcı analiz hakkının bittiğini
# sanır, oysa sınırsız. Bu yüzden uç `etkin: false` döner ve arayüz rozeti HİÇ ÇİZMEZ.
#
# ⚠️ ÇEVRİMDIŞI "0" GÖSTERMEK DE YASAK. Bakiye Supabase'den okunur; klinik internetsizken
# okuma başarısız olur. O an "0" yazmak, çalışan bir sistemi bitmiş gibi gösterir
# (bu depoda "sahte değer göster" sınıfının tekrarı). Okuma başarısızsa `bilinmiyor: true`
# döner ve arayüz "—" gösterir.
def bakiye_ozeti(request) -> dict:
    """Kullanıcının kalan jeton hakkı — arayüzde göstermek için.

    Dönüş sözleşmesi:
      · `{"etkin": False}`                      → ücretlendirme KAPALI, rozet çizilmez
      · `{"etkin": True, "bilinmiyor": True}`   → okunamadı (çevrimdışı) → "—"
      · `{"etkin": True, "kalan": N, ...}`      → gerçek bakiye
    Etkinken `bekleyen` = defterde henüz gönderilemeyen (yolda kalan) ödeme sayısı (D4.23; çevrimiçiyken uzlaştırma tetiklenir).
    """
    if not JETON_ENFORCED:
        return {"etkin": False}

    token = _bearer_token(request)
    if not token:
        # Kimliksiz istek: bakiye KİŞİYE özeldir, tahmin üretme.
        return {"etkin": True, "bilinmiyor": True, "sebep": "kimlik_yok"}

    try:
        bekleyen = _defter_yoneticisi(sahip=_jwt_sahip(token)).sahibin_bekleyen_sayisi()  # bu kullanıcının (D4.23 eki)
    except Exception:
        bekleyen = 0
    try:
        satir = _bakiye_satiri_oku(token)
    except Exception:
        # ⚠️ Sıfıra DÜŞME (yukarıdaki nota bakın). Bekleyen çevrimdışı tüketim varsa onu söyle.
        return {"etkin": True, "bilinmiyor": True, "sebep": "cevrimdisi", "bekleyen": bekleyen}
    # D4.23 (Y24): bağlantı DÖNDÜ → biriken çevrimdışı tüketim arka planda geriye dönük düşülür; rozet sunucu bakiyesini
    # gösterir, `bekleyen` henüz uzlaşmamış kayıt sayısını söyler (uzlaşınca 0'a iner).
    _uzlastirmayi_tetikle(token)

    aylik = int(satir.get("aylik_hak") or 0)
    satin = int(satir.get("satin_alinan") or 0)
    model = str(satir.get("odeme_modeli") or "on_odemeli")

    ozet = {
        "etkin": True,
        "bilinmiyor": False,
        "odemeModeli": model,
        "maliyet": dict(MALIYET),
        "bekleyen": bekleyen,
    }
    if model == "kullandikca":
        # Kullandıkça ödemede bakiye kavramı YOK — faturalanmamış borç gösterilir.
        borc = int(satir.get("kullandikca_borc") or 0)
        ozet.update({"borc": borc, "borcTavani": BORC_TAVANI})
    else:
        ozet.update({"kalan": aylik + satin, "aylikHak": aylik, "satinAlinan": satin})
    return ozet
