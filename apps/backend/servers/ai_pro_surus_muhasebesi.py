# Author: mertaygn, cglrgrkn
"""AI Pro seansının GERÇEK sürüş muhasebesi — seans KAYDININ doğruluğu (YS2 a · B1, YG0 tezgâhı 25-11).

ÖLÇÜLEN KUSUR: plaka doğrulanamadığı / plaka kaydığı / hedef kaybolduğu için bobinleri durdurulan (ya da HİÇ sürülmeyen) AI Pro
seansı, süre dolunca "Tamamlandı · tam süre · hedef doz" diye kapanıyordu (12:56 seansı hiç sürülmedi; 13:06 seansı 13:08'de durdu,
sürüş yeniden başlamadı). Geçmiş, PDF ve CSV verilmemiş dozu verilmiş gösteriyordu.

Döngü (`ai_router._ai_pro_loop`) seans başında `basla`, telde KABUL edilen her sürüşte `surdu`, her tolerans / hedef-kaybı STOP'unda
`durdu` çağırır. Seansın TEK kapanış yolu (`api_server._finalize_session_db` ve `/session/stop`) `kapanis_duzeltmesi` ile durumu,
süreyi ve dozu GERÇEĞE çeker; neden `session_parameters.durdurma_nedeni`ye yazılır (geçmiş / detay / PDF / CSV / telefon aynı
satırdan okur). Yalnız YENİ seanslar (eski kayıt değişmez). Bobinlere DOKUNMAZ: yalnız sayar — STOP yolu, mandal ve nesil kapıları
aynen (Ö.4-Y8).

Kural: hiç durdurma olmayan ve sürülmüş seans AYNEN kalır (duvar saati süresi, "Tamamlandı"). Durdurma olduysa süre = gerçek sürüş
(tam dakika; mevcut kayıt kuralı gibi aşağı yuvarlanır). Süre dolduğunda bobinler durdurmayla DURUYORDUYSA ya da hiç sürülmediyse
"Tamamlandı" → "Durduruldu" (+ son neden). Hiç sürülmediyse doz 0. Acil durdurma, iptal ve donanım reddi durumları DEĞİŞMEZ.
"""

from __future__ import annotations

import threading
import time

#: `session_parameters.durdurma_nedeni` kodları (gösterim: `seans.durdurmaNedeni.<kod>` — arayüz ve backend katalogları).
NEDEN_PLAKA_KAYDI = "plaka_kaydi"
NEDEN_PLAKA_DOGRULANAMADI = "plaka_dogrulanamadi"
NEDEN_HEDEF_KAYBI = "hedef_kaybi"
NEDENLER = (NEDEN_PLAKA_KAYDI, NEDEN_PLAKA_DOGRULANAMADI, NEDEN_HEDEF_KAYBI)

#: Kayda yazılan parametre adı.
PARAMETRE = "durdurma_nedeni"

#: Düzeltilen kapanış durumları; geri kalanı (acil durdurma, iptal, donanım reddi …) olduğu gibi yazılır.
_DUZELTILEN_DURUMLAR = frozenset({"completed", "stopped", "interrupted"})

#: Aynı anda tek AI Pro seansı olur; kapanmadan kalan (çökmüş) kayıtlar sınırsız birikmesin.
_EN_COK_KAYIT = 8

_kilit = threading.Lock()
_kayitlar: dict = {}


def _anahtar(db_sid):
    try:
        return int(db_sid)
    except (TypeError, ValueError):
        return None


def _kayit(anahtar: int) -> dict:
    k = _kayitlar.get(anahtar)
    if k is None:
        while len(_kayitlar) >= _EN_COK_KAYIT:
            _kayitlar.pop(next(iter(_kayitlar)))
        k = {"toplam_s": 0.0, "enerji_basi": None, "surudu": False, "durdurma": 0, "neden": None}
        _kayitlar[anahtar] = k
    return k


def basla(db_sid) -> None:
    """Seans başı: bu satırın muhasebesini SIFIRDAN aç (aynı kimlikli eski kayıt kalmaz)."""
    a = _anahtar(db_sid)
    if a is None:
        return
    with _kilit:
        _kayitlar.pop(a, None)
        _kayit(a)


def surdu(db_sid, an: float | None = None) -> None:
    """Telde KABUL edilen sürüş: bobinler bu andan (zaten enerjili değilse) enerjili sayılır."""
    a = _anahtar(db_sid)
    if a is None:
        return
    an = time.monotonic() if an is None else an
    with _kilit:
        k = _kayit(a)
        k["surudu"] = True
        if k["enerji_basi"] is None:
            k["enerji_basi"] = an


def durdu(db_sid, neden: str, an: float | None = None) -> None:
    """Tolerans / hedef-kaybı STOP'u: enerjili süre toplama eklenir, son neden saklanır (yinelenen STOP'ta süre ikinci kez sayılmaz)."""
    a = _anahtar(db_sid)
    if a is None:
        return
    an = time.monotonic() if an is None else an
    with _kilit:
        k = _kayit(a)
        if k["enerji_basi"] is not None:
            k["toplam_s"] += max(0.0, an - k["enerji_basi"])
            k["enerji_basi"] = None
        k["durdurma"] += 1
        k["neden"] = neden if neden in NEDENLER else NEDEN_HEDEF_KAYBI


def kapanis_duzeltmesi(db_sid, durum: str, an: float | None = None) -> dict | None:
    """Kapanışta: muhasebeyi KAPAT (kayıt silinir) ve gerekiyorsa düzeltmeyi döndür.

    @return None = satır olduğu gibi yazılır (muhasebe yok / kesintisiz sürülmüş / düzeltilmeyen durum). Aksi hâlde
            `{"durum", "sure_dk", "doz_sifir", "neden"}` — `neden` None ise parametre YAZILMAZ."""
    a = _anahtar(db_sid)
    if a is None:
        return None
    an = time.monotonic() if an is None else an
    with _kilit:
        k = _kayitlar.pop(a, None)
    if k is None or str(durum or "").lower() not in _DUZELTILEN_DURUMLAR:
        return None
    if not k["durdurma"] and k["surudu"]:
        return None
    enerjili = k["enerji_basi"] is not None
    surus_s = k["toplam_s"] + (max(0.0, an - k["enerji_basi"]) if enerjili else 0.0)
    durmus = not enerjili  # kapanış anında bobinler durdurmayla duruyordu (ya da hiç sürülmedi)
    yeni = "stopped" if durum == "completed" and durmus else durum
    return {
        "durum": yeni,
        "sure_dk": int(surus_s // 60),
        "doz_sifir": not k["surudu"],
        "neden": k["neden"] if durmus and yeni == "stopped" else None,
    }
