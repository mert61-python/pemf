# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) A2 — CANLI 3B ALAN (ana sunucu tarafı): abonelik + saniyede bir döngü + iletim. Kontrol sekmesi "Alan haritası" kartı
ve dijital ikiz (`pemf.ikiz.alan`) bu iletiyi (`alan_haritasi`) kullanır.

YALNIZ GÖSTERİM: hiçbir sürüş kararı bu görünümden alınmaz. ACİL DURDUR / sürüş / keep-alive ile ORTAK KİLİT YOK ve hesap ANA SÜREÇTE
YAPILMAZ: bobin durumu `HardwareController.calisan_bobin_durumu()` ANLIK GÖRÜNTÜSÜYLE (kilit µs) okunur, harita AYRI SÜREÇTE
(`servers.canli_alan_hesapci`, `servers.alt_surec` — neden süreç: oradaki ölçüm) hesaplanır. Döngü YALNIZ en az bir istemci abone iken
koşar; son abone gidince döngü biter ve alt süreç kapanır. Çalışan bobin yoksa alt süreç hiç başlamaz (`sifir`).

Durum kodları: `tamam` · `sifir` (çalışan bobin yok) · kalibrasyon kodları · `modelYok` · `modelBozuk` · `hata` (alt süreç yanıt
vermedi / öldü — sonraki turda yeniden başlatılır) — hiçbiri ÇÖKERTMEZ; arayüz eylem söyleyen TR + EN metin gösterir.
"""

from __future__ import annotations

import logging
import math
import threading
import time

from utils.dongu_guvenligi import dongu_hatasini_bildir

logger = logging.getLogger(__name__)

SURUM = 1
ILETI_TURU = "alan_haritasi"
ARALIK_S = 1.0
N_BOBIN = 7
#: İlk istek alt süreç açılışı + birim alan / RL dalgası kurulumunu içerir (LattePanda'da saniyeler) → cömert; sonrakiler ms.
HESAP_ZAMAN_ASIMI_S = 60.0


def _durum(kod: str) -> dict:
    return {"surum": SURUM, "durum": kod, "zaman": time.time(), "modelTahmini": True}


class AltSurecHesap:
    """Varsayılan hesap: `--alt-surec canli-alan` süreci (ilk istekte açılır)."""

    def __init__(self, surec=None):
        if surec is None:
            from servers.alt_surec import JsonSatirSureci, komut

            surec = JsonSatirSureci(komut("canli-alan"), ad="canli-alan")
        self._surec = surec

    def __call__(self, bobinler: list) -> dict | None:
        return self._surec.istek({"bobinler": [list(b) for b in bobinler]}, HESAP_ZAMAN_ASIMI_S)

    def kapat(self) -> None:
        self._surec.kapat()


class CanliAlan:
    """`bobin_durumu()` → {bobin: {"freq", "duty" (oran), "phase" (derece)}} (yalnız ÇALIŞANLAR); `gonder(ileti, alicilar)` → yalnız
    abonelere; `hesap(bobinler)` → harita verisi ya da None (yanıt yok) — varsayılan `AltSurecHesap` (ayrı süreç)."""

    def __init__(self, bobin_durumu, gonder, hesap=None, aralik_s: float = ARALIK_S):
        self._bobin_durumu = bobin_durumu
        self._gonder = gonder
        self._hesap = hesap
        self._aralik = float(aralik_s)
        self._kilit = threading.Lock()
        self._aboneler: list = []
        self._is: threading.Thread | None = None
        self._uyandir = threading.Event()

    # ── abonelik ─────────────────────────────────────────────────────────────────────────────────
    def abone(self, istemci, acik: bool) -> None:
        """İstemci (WebSocket) aboneliği. İlk abone döngüyü başlatır; son abone gidince döngü kendiliğinden biter."""
        with self._kilit:
            var = any(a is istemci for a in self._aboneler)
            if acik and not var:
                self._aboneler.append(istemci)
            elif not acik and var:
                self._aboneler = [a for a in self._aboneler if a is not istemci]
            if self._aboneler and self._is is None:
                self._is = threading.Thread(target=self._dongu, daemon=True, name="canli-alan")
                self._is.start()
        self._uyandir.set()

    def abone_sayisi(self) -> int:
        with self._kilit:
            return len(self._aboneler)

    def _dongu(self) -> None:
        while True:
            with self._kilit:
                alicilar = list(self._aboneler)
                if not alicilar:
                    self._is = None
                    break
            self._uyandir.clear()
            try:
                veri = self.tur()
            except Exception:
                dongu_hatasini_bildir("Canlı alan döngü hatası", logger=logger)
                veri = _durum("hata")
            try:
                self._gonder({"type": ILETI_TURU, "data": veri}, alicilar)
            except Exception:
                dongu_hatasini_bildir("Canlı alan gönderim hatası", logger=logger)
            self._uyandir.wait(self._aralik)
        kapat = getattr(self._hesap, "kapat", None)
        if kapat is not None:
            kapat()

    # ── tur ──────────────────────────────────────────────────────────────────────────────────────
    def _calisanlar(self) -> list[tuple[int, float, float, float]]:
        try:
            durum = self._bobin_durumu() or {}
        except Exception:
            dongu_hatasini_bildir("Canlı alan: bobin durumu okunamadı", logger=logger, seviye=logging.WARNING)
            durum = {}
        out = []
        for i, s in durum.items():
            try:
                b, f, d, p = int(i), float(s["freq"]), float(s["duty"]), float(s["phase"])
            except (KeyError, TypeError, ValueError):
                continue
            if 1 <= b <= N_BOBIN and d > 0 and f > 0 and all(math.isfinite(v) for v in (f, d, p)):
                out.append((b, round(f, 1), round(d, 4), round(p % 360.0, 2)))
        return sorted(out)

    def tur(self) -> dict:
        """Bir güncelleme: bobin durumu → hesap (alt süreç) → ileti verisi. Hata → durum kodu (fırlatmaz)."""
        bobinler = self._calisanlar()
        if not bobinler:
            return _durum("sifir")
        if self._hesap is None:
            self._hesap = AltSurecHesap()
        veri = self._hesap(bobinler)
        if not isinstance(veri, dict) or "durum" not in veri:
            logger.warning(
                "Canlı alan hesabı yanıt vermedi / bozuk: %s",
                (veri or {}).get("hata") if isinstance(veri, dict) else veri,
            )
            return _durum("hata")
        return veri
