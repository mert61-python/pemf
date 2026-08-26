# Author: mertaygn, cglrgrkn
"""
JETON (token) TÜKETİM KAPISI — cihaz tarafı (sahip kararı 2026-08-20).

Ücretlendirme "kuyruk/hız" vaadi yerine JETON tüketimine bağlandı: 1 jeton = 1 yapay zekâ
analizi. Sebep: yapay zekâ analizleri klinik bilgisayarında ÇALIŞIYOR; "sunucuda sıra
beklersiniz" vaadinin karşılığı yoktu. Jeton ölçülebilir ve dürüstçe anlatılabilir bir birimdir.

  · Şema/uzlaştırma : database/supabase_jetonlar.sql (atomik `jeton_tuket` RPC + defter)
  · Uç              : pemf-vet-web/api/tokens.ts (bakiye + tüketim, idempotans zorunlu)
  · Kullanıcı metni : pemf-vet-web/src/config.ts::JETON (maliyet tablosu TEK KAYNAK)

╔══════════════════════════════════════════════════════════════════════════════════════════╗
║ ⚠️ TIBBİ CİHAZ GÜVENLİĞİ — PAZARLIK EDİLEMEZ                                             ║
║ Jeton TİCARİ bir kapıdır, güvenlik kontrolü DEĞİLDİR. Süren seansı, seans durdurmayı,    ║
║ ACİL DURDURMAYI, sensör okumayı ve cihaz kontrolünü ASLA engellemez. Yalnız YENİ yapay   ║
║ zekâ ANALİZİ isteğini kapılar. (entitlement.py aynı ilkeyi taşır: "compute-önceliği       ║
║ kapısı, güvenlik kontrolü değil" + her belirsizlikte fail-open.)                          ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

ÇEVRİMDIŞI KLİNİK: internet yokken analiz DURMAZ. Tüketim yerel deftere yazılır ve bağlantı
gelince uzlaşır. Sınırsız değildir (`PEMF_JETON_OFFLINE_TAVAN`) — aksi hâlde ücretlendirme
anlamsızlaşırdı; tavan aşılsa bile TEDAVİ yolu serbest kalır.

ÇİFT DÜŞME YOK: her tüketim `istek_id` taşır; yeniden deneme ve uzlaştırma aynı jetonu iki kez
harcayamaz (sunucuda `token_ledger` UNIQUE, burada yerel defterde anahtar kontrolü).

⚠️ BAYRAKLI: `PEMF_JETON_ENFORCED` KAPALIYKEN her şey no-op — satış açılana kadar canlı
davranış değişmez (entitlement.py deseniyle birebir).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


# ── Yapılandırma ────────────────────────────────────────────────────────────
JETON_ENFORCED: bool = _flag("PEMF_JETON_ENFORCED", False)
OFFLINE_TAVAN: int = max(0, int(os.getenv("PEMF_JETON_OFFLINE_TAVAN", "50") or 50))

# KULLANDIKÇA ÖDE (sahip isteği 2026-08-20): önden ödeme/jeton alımı OLMAYAN üyelik. Aylık ücret
# yok; harcanan jeton birikir ve dönem sonunda (ya da eşik aşılınca) faturalanır. Hiç kullanılmazsa
# ücret çıkmaz. Bakiye 0 olsa bile analiz İZİNLİDİR — kapı, bakiye yerine BİRİKMİŞ BORCA bakar.
#
# ⚠️ Neden tavan var: ödeme alınamayan sınırsız kullanım (kartı düşen/vazgeçen hesap) riski.
# Tavan TİCARİ bir sınırdır — aşılsa bile tedavi yolu serbest kalır (aşağıdaki GUVENLIK_YOLLARI).
BORC_TAVANI: int = max(0, int(os.getenv("PEMF_JETON_BORC_TAVANI", "300") or 300))

# ⚠️ TEK KAYNAK EŞLEŞMESİ: bu tablo `pemf-vet-web/src/config.ts::JETON.maliyet` ile BİREBİR
# aynı olmalıdır — kullanıcı sitede "1 jeton" okuyup cihazda 3 harcarsa güven biter.
# `tests/test_jeton_yoneticisi.py::test_KARSIT_KANIT_maliyet_tablosu_WEB_ile_AYNI` kilitler.
MALIYET: dict[str, int] = {
    "goruntu": 1,
    "ses": 1,
    "sensor": 1,
    "agir_arastirma": 3,
    "ai_pro_seans": 5,
}

# ⚠️ GÜVENLİK YOLLARI: bunlar jetondan BAĞIMSIZDIR ve hiçbir koşulda kapılanmaz.
# Yeni bir tedavi/emniyet yolu eklenirse buraya da eklenmelidir.
GUVENLIK_YOLLARI: frozenset[str] = frozenset(
    {"seans_baslat", "seans_durdur", "acil_durdur", "sensor_oku", "cihaz_kontrol", "durum"}
)

_YETERSIZ_MESAJ = (
    "Jeton hakkınız bitti; yeni yapay zekâ analizi başlatılamadı. "
    "Seans, acil durdurma ve sensör izleme bundan ETKİLENMEZ. "
    "Ek jeton paketiyle hemen devam edebilirsiniz."
)


@dataclass(frozen=True)
class Karar:
    izinli: bool
    jeton_harcandi: int = 0
    mesaj: str = ""
    sebep: str = ""


def _defter_yolu() -> Path:
    kok = os.getenv("PEMF_DATA_DIR") or str(Path.home() / ".pemf")
    p = Path(kok) / "jeton_bekleyen.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class JetonYoneticisi:
    """Analiz isteklerini jeton bakiyesine göre kapılar; çevrimdışı tüketimi biriktirir.

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
    ) -> None:
        """`odeme_modeli`:
        · "on_odemeli"  → plan hakkı/satın alınan jetondan düşer; bakiye biterse analiz durur.
        · "kullandikca" → önden ödeme YOK; tüketim borç olarak birikir, dönem sonunda faturalanır.
        `borc_okuyucu` yalnız kullandıkça-öde modelinde kullanılır (birikmiş, faturalanmamış jeton).
        """
        self._bakiye_oku = bakiye_okuyucu
        self._tuketim_gonder = tuketim_gonderici
        self._defter = defter_yolu or _defter_yolu()
        self._kilit = threading.Lock()
        self._odeme_modeli = odeme_modeli
        self._borc_oku = borc_okuyucu or (lambda: 0)

    # ── Yerel defter (çevrimdışı tüketim) ───────────────────────────────────
    def _defteri_oku(self) -> list[dict]:
        try:
            return json.loads(self._defter.read_text(encoding="utf-8")) or []
        except Exception:
            return []

    def _defteri_yaz(self, kayitlar: list[dict]) -> None:
        try:
            self._defter.write_text(json.dumps(kayitlar, ensure_ascii=False), encoding="utf-8")
        except Exception:
            # Defter yazılamazsa tüketim izi kaybolur ama TEDAVİ ETKİLENMEZ — sessiz düşme
            # yerine uyar (ücretlendirme eksik kalır, klinik çalışmaya devam eder).
            logger.warning("jeton: bekleyen tüketim defteri yazılamadı", exc_info=True)

    def bekleyen_tuketim_sayisi(self) -> int:
        return len(self._defteri_oku())

    def _bekleyene_ekle(self, kayit: dict) -> None:
        with self._kilit:
            kayitlar = self._defteri_oku()
            if any(k.get("istek_id") == kayit["istek_id"] for k in kayitlar):
                return  # idempotans: aynı istek defterde iki kez durmaz
            kayitlar.append(kayit)
            self._defteri_yaz(kayitlar)

    # ── Ana kapı ────────────────────────────────────────────────────────────
    def izin(self, islem: str, istek_id: str | None = None, cihaz_id: str | None = None) -> Karar:
        """Bir işlem için jeton kapısı. GÜVENLİK yolları her koşulda serbesttir."""
        # 1) GÜVENLİK YOLU → hiçbir koşulda kapılanmaz (bayrak, bakiye, ağ durumu fark etmez).
        if islem in GUVENLIK_YOLLARI:
            return Karar(izinli=True, sebep="guvenlik_yolu")

        # 2) Bayrak kapalı → no-op (satış açılana kadar canlı davranış değişmez).
        if not JETON_ENFORCED:
            return Karar(izinli=True, sebep="enforce_kapali")

        maliyet = MALIYET.get(islem, MALIYET["goruntu"])
        iid = istek_id or f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:12]}"

        # 2b) KULLANDIKÇA ÖDE: önden ödeme yok → bakiyeye BAKILMAZ. Kapı, birikmiş (henüz
        # faturalanmamış) borca bakar. Tavan aşılmadıysa analiz serbesttir ve tüketim
        # "kullandikca" türüyle kaydedilir; dönem sonunda faturalanır.
        if self._odeme_modeli == "kullandikca":
            try:
                borc = int(self._borc_oku())
            except Exception:
                borc = 0  # borç okunamıyorsa kullanıcıyı cezalandırma (fail-open)
            if BORC_TAVANI and borc >= BORC_TAVANI:
                return Karar(
                    izinli=False,
                    sebep="borc_tavani",
                    mesaj=(
                        "Kullandıkça öde üyeliğinizde faturalanmamış kullanım sınırına ulaşıldı; "
                        "yeni yapay zekâ analizi başlatılamadı. Ödemeniz alındığında sınır sıfırlanır. "
                        "Seans, acil durdurma ve sensör izleme ETKİLENMEZ."
                    ),
                )
            return self._tuket(maliyet, islem, iid, cihaz_id, tur="kullandikca")

        # 3) Bakiye okunamıyorsa (çevrimdışı klinik) → tavana kadar İZİN + borç kaydı.
        try:
            bakiye = int(self._bakiye_oku())
        except Exception:
            bekleyen = self.bekleyen_tuketim_sayisi()
            if bekleyen >= OFFLINE_TAVAN:
                return Karar(
                    izinli=False,
                    mesaj=(
                        "İnternet bağlantısı olmadan yapılabilecek analiz sınırına ulaşıldı. "
                        "Cihazı internete bağladığınızda kaldığınız yerden devam edersiniz. "
                        "Seans, acil durdurma ve sensör izleme ETKİLENMEZ."
                    ),
                    sebep="offline_tavan",
                )
            self._bekleyene_ekle(
                {"istek_id": iid, "miktar": maliyet, "tur": "analiz", "detay": islem, "cihaz_id": cihaz_id}
            )
            return Karar(izinli=True, jeton_harcandi=maliyet, sebep="cevrimdisi")

        # 4) Bakiye yetersiz → YALNIZ analiz reddedilir (tedavi yolu zaten yukarıda serbest).
        if bakiye < maliyet:
            return Karar(izinli=False, mesaj=_YETERSIZ_MESAJ, sebep="yetersiz")

        # 5) Tüketimi gönder. Gönderim düşerse analiz DURMAZ — kayıt deftere düşer (fail-open).
        return self._tuket(maliyet, islem, iid, cihaz_id, tur="analiz")

    def _tuket(self, maliyet: int, islem: str, iid: str, cihaz_id: str | None, tur: str) -> Karar:
        """Tüketimi gönderir; gönderilemezse yerel deftere yazar (iki ödeme modelinde de ortak)."""
        try:
            gitti = bool(self._tuketim_gonder(miktar=maliyet, tur=tur, detay=islem, istek_id=iid, cihaz_id=cihaz_id))
        except Exception:
            gitti = False
        if not gitti:
            self._bekleyene_ekle({"istek_id": iid, "miktar": maliyet, "tur": tur, "detay": islem, "cihaz_id": cihaz_id})
        return Karar(izinli=True, jeton_harcandi=maliyet, sebep="tuketildi")

    # ── Uzlaştırma ──────────────────────────────────────────────────────────
    def bekleyenleri_uzlastir(self) -> int:
        """Biriken çevrimdışı tüketimi gönderir. Başarılı olanlar defterden düşer.

        ⚠️ Başarısız gönderim kaydı SİLMEZ: silseydik tüketim sessizce kaybolur ve kullanıcı
        bedava analiz yapmış olurdu (ya da tersi: borcu iki kez ödeyebilirdi). `istek_id`
        sayesinde tekrar gönderim güvenlidir — sunucu ikinciyi yok sayar.
        """
        kayitlar = self._defteri_oku()
        if not kayitlar:
            return 0
        kalan: list[dict] = []
        gonderilen = 0
        for k in kayitlar:
            try:
                ok = bool(self._tuketim_gonder(**k))
            except Exception:
                ok = False
            if ok:
                gonderilen += 1
            else:
                kalan.append(k)
        with self._kilit:
            self._defteri_yaz(kalan)
        return gonderilen


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

_SUPABASE_TIMEOUT: float = max(1.0, float(os.getenv("PEMF_JETON_TIMEOUT", "4") or "4"))


def _bearer_token(request: Request) -> str:
    h = request.headers.get("authorization") or ""
    return h[7:].strip() if h.lower().startswith("bearer ") else ""


# ── Uç → işlem eşlemesi ──────────────────────────────────────────────────────────
# TAM YOL pinlenir (bu deponun dersi: parça-eşleme kapıları string hileleriyle deliniyor).
# Kapılanmayan ai_router uçları (analiz DEĞİL):
#   pro/stop            → seans DURDURMA: güvenlik sınıfı, hiçbir koşulda kapılanmaz
#   pro/status          → durum okuma
#   pro/approve|reject  → operatör onay kararı (analiz zaten propose aşamasında yapıldı)
#   pro/frame           → seans İÇİ kare akışı — ücret seans-başına (pro/start = 5) alınır;
#                         kare başına almak 5 jetonluk seansı yüzlerce jetona çevirirdi
#   pro/organ|calibrate → kalibrasyon/kurulum
_SERBEST_AI_UCLARI: frozenset = frozenset(
    {
        "/api/ai/pro/stop",
        "/api/ai/pro/status",
        "/api/ai/pro/approve",
        "/api/ai/pro/reject",
        "/api/ai/pro/frame",
        "/api/ai/pro/organ",
        "/api/ai/pro/calibrate",
    }
)
# Ağır araştırma (belge: patoloji, RNA, tomografi, yara-kapanma = 3 jeton).
# scratch: KARAR 0.6 (2026-08-26, scratch-entegrasyon-plani.md) — 872MB CPN
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


def _tuketim_gonder_canli(token: str, **k) -> bool:
    """rpc/jeton_tuket — atomik düşüm (satır kilidi + istek_id idempotansı RPC içinde)."""
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
        return bool(isinstance(sonuc, dict) and sonuc.get("ok"))
    except Exception:
        return False


# Çevrimdışı defter yazımları per-istek yönetici örneklerinden gelir; dosya yarışını tek
# modül-kilidiyle serileştir (örnek başına kilit dosyayı KORUMAZDI).
_GATE_DEFTER_KILIT = threading.Lock()


def _jeton_kapisi_karari(request: Request) -> None:
    """Senkron karar gövdesi (test yüzeyi). İzin yoksa HTTPException(402) fırlatır."""
    # ⚠️ SIRA: serbest-uç ve bayrak kontrolü HER ŞEYDEN ÖNCE — pro/stop için ağ çağrısı bile
    # yapılmaz (ağ gecikmesi seans durdurmayı geciktiremez; testle kilitli).
    islem = _islem_turu(getattr(getattr(request, "url", None), "path", "") or "")
    if islem is None:
        return
    if not JETON_ENFORCED:
        return  # sahip kararı: satış kapalı — kapı bağlı ama uykuda (bayrak tek anahtar)

    token = _bearer_token(request)
    try:
        satir = _bakiye_satiri_oku(token)
    except Exception:
        satir = None  # çevrimdışı/tokensız → JetonYoneticisi fail-open yolu (yerel defter)

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
    )
    yonetici._kilit = _GATE_DEFTER_KILIT  # defter dosyası paylaşımlı → kilit de paylaşımlı

    karar = yonetici.izin(islem)
    if not karar.izinli:
        # 402: ticari red. Mesaj TEDAVİNİN ETKİLENMEDİĞİNİ açıkça söyler (hasta güvenliği algısı).
        raise HTTPException(status_code=402, detail=karar.mesaj or _YETERSIZ_MESAJ)


async def jeton_gate(request: Request) -> None:
    """Router-seviyesi bağımlılık. Bloklayan Supabase çağrısı threadpool'a atılır (belge 4.1;
    ai_queue_gate ile aynı gerekçe — event loop bloklanmasın)."""
    import asyncio

    await asyncio.to_thread(_jeton_kapisi_karari, request)
