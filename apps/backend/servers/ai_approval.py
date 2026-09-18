# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""HEKİM ONAY KAPISI — AI'ın önerdiği tedavi parametreleri onaylanmadan UYGULANMAZ.

SAHİP KARARI (2026-08-06): "sert kapı — onaysız tedavi başlamaz". AI Pro şimdiye kadar
`/api/ai/pro/start` çağrılır çağrılmaz organı lokalize edip em_kedi'nin ürettiği per-coil
duty/phase ile bobinleri SÜRÜYORDU; hekim ne önerildiğini tedavi başladıktan sonra görüyordu.
Artık akış: **öner → hekim görür → onaylar/reddeder → ancak onaydan sonra donanım sürülür.**

TASARIM KARARLARI (hepsi güvenlik gerekçeli):
  * **Tek kullanımlık.** Onay `consume()` ile tüketilir; ikinci kez kullanılamaz. Aksi halde
    bir kez onaylanan parametre günler boyu tekrar tekrar başlatılabilirdi.
  * **Süreli.** Onay `TTL_S` sonra geçersiz. Hasta pozisyonu/durumu değişmiş olabilir; "sabahki
    onay"la akşam tedavi başlatmak klinik olarak savunulamaz.
  * **Parametre mührü.** Onaylanan spekler kaydın İÇİNDE saklanır ve `consume()` onları döner.
    Çağıran, onaylanan değerleri kullanmak ZORUNDA — "onayı al, başka parametreyle sür" mümkün değil.
  * **Reddin gerekçesi tutulur.** Denetim izi için; ayrıca hekim neden reddettiğini yazınca
    model/akış iyileştirmesi için gerçek veri birikir.
  * **Bellekte.** Onay bir OTURUM kararıdır, süreç yeniden başlarsa (EXE güncellemesi, çökme)
    yeniden onay istenmesi DOĞRUDUR — kalıcılaştırmak bayat onayı diriltir. Denetim izi ayrıca
    `session_events`'e yazılır (bkz. ai_router).
"""

from __future__ import annotations

import threading
import time
import uuid

# Onay ömrü. Kısa tutuldu: hekim öneriyi görüp karar verip başlatana kadar dakikalar yeter.
TTL_S = 600.0

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
CONSUMED = "consumed"
EXPIRED = "expired"

_lock = threading.Lock()
_store: dict[str, dict] = {}
# Bellek sızıntısı koruması: hiç kullanılmayan öneriler birikmesin.
_MAX = 50


def _prune_locked(now: float) -> None:
    for k in [k for k, v in _store.items() if now - v["created_at"] > TTL_S * 3]:
        _store.pop(k, None)
    if len(_store) > _MAX:
        for k in sorted(_store, key=lambda k: _store[k]["created_at"])[: len(_store) - _MAX]:
            _store.pop(k, None)


def create(kind: str, specs: dict, meta: dict | None = None) -> dict:
    """Yeni öneri kaydı aç. `specs` = hekime GÖSTERİLEN ve onaylanınca UYGULANACAK parametreler."""
    now = time.time()
    pid = uuid.uuid4().hex
    rec = {
        "id": pid,
        "kind": str(kind),
        "specs": dict(specs or {}),
        "meta": dict(meta or {}),
        "status": PENDING,
        "created_at": now,
        "expires_at": now + TTL_S,
        "decided_at": None,
        "operator": "",
        "reason": "",
    }
    with _lock:
        _store[pid] = rec
        # Budama EKLEDİKTEN SONRA: önce budayıp sonra eklersek sınır her seferinde 1 aşılır.
        _prune_locked(now)
        return dict(rec)


def get(pid: str) -> dict | None:
    with _lock:
        r = _store.get(str(pid or ""))
        return dict(r) if r else None


def _decide(pid: str, status: str, operator: str, reason: str) -> dict:
    now = time.time()
    with _lock:
        r = _store.get(str(pid or ""))
        if not r:
            raise KeyError("Öneri bulunamadı (süresi dolmuş olabilir).")
        if r["status"] != PENDING:
            raise ValueError(f"Bu öneri zaten karara bağlanmış: {r['status']}")
        if now > r["expires_at"]:
            r["status"] = EXPIRED
            raise ValueError("Önerinin süresi doldu; yeniden öneri alın.")
        r["status"] = status
        r["decided_at"] = now
        r["operator"] = str(operator or "")
        r["reason"] = str(reason or "")
        return dict(r)


def approve(pid: str, operator: str = "") -> dict:
    return _decide(pid, APPROVED, operator, "")


def reject(pid: str, operator: str = "", reason: str = "") -> dict:
    return _decide(pid, REJECTED, operator, reason)


def consume(pid: str) -> dict:
    """Onaylı öneriyi TÜKET ve mühürlenen parametreleri dön. Uygun değilse ValueError.

    Donanımı sürecek yol BUNU çağırmak ZORUNDA — böylece 'onaysız sürüş' ve 'onaylanandan
    farklı parametreyle sürüş' ikisi de yapısal olarak imkânsız olur.
    """
    now = time.time()
    with _lock:
        r = _store.get(str(pid or ""))
        if not r:
            raise ValueError("Onay bulunamadı. Önce AI önerisini alıp onaylayın.")
        if r["status"] == CONSUMED:
            raise ValueError("Bu onay zaten kullanıldı. Yeni öneri alın.")
        if r["status"] == REJECTED:
            raise ValueError("Bu öneri REDDEDİLDİ; uygulanamaz.")
        if r["status"] == PENDING:
            raise ValueError("Öneri henüz onaylanmadı.")
        if now > r["expires_at"]:
            r["status"] = EXPIRED
            raise ValueError("Onayın süresi doldu; yeniden öneri alın.")
        r["status"] = CONSUMED
        return dict(r)


def clear() -> None:
    """Yalnız test/temizlik için."""
    with _lock:
        _store.clear()
