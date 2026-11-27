# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""MLX90393 BEKÇİSİ — Y285 (sahip 13 Kasım 2026: "kopsa bile bağlanır; birkaç denemeden sonra bağlanmazsa kullanıcıya uyarı gider: manyetik
alan sensörü düştü — sensörü çıkarıp takın ya da kartın gücünü kesip yeniden bağlayın"). Firmware kısmı: `pemf_sensor.c` (DDS v2.6).

Kayıp sensörü FIRMWARE kendisi yeniden arar (açılışta yoksa 2 sn'de bir yoklama, her 3. denemede I2C hat kurtarması; çalışırken kopan
sensör için 50 ms'de bir denetim okuması, 5 hatada bir hat kurtarması). Bu bekçi, bir bobinde `B=` taşıyan `STM_TELE` satırı `ESIK_S`
boyunca gelmezse (≈ 5 yoklama + en az bir hat kurtarması) o bobini DÜŞTÜ ilan eder — TEK sefer; `B=` yeniden gelince bobin yeniden
izlenir. Kullanıcı uyarısı ("düştü" / "yeniden bağlandı") `api_server` telemetri işleyicisinde (`alan_kayip` olayı, bildirim anahtarları
`bildirim.mlxDustu` / `bildirim.mlxGeriGeldi`).

KAPSAM: yalnız bu backend sürecinde en az bir kez `B=` gelmiş bobin izlenir — sensörü hiç takılmamış hat (bugün I2C1 / bobin 7) uyarı
ÜRETMEZ. STM bağlı değilken süre işlemez; yeniden bağlanınca izlenen bobinlerin süresi BAĞLANTI anından başlar (kart açılışı + ilk pencere
payı) ve önceki "düştü" kararı silinir (sensör hâlâ yoksa olay yeniden üretilir; `api_server` yalnız bayrak GEÇİŞİNDE bildirir).
"""

from __future__ import annotations

import threading
import time

#: Firmware yoklama aralığı 2 sn, hat kurtarması her 3. denemede (6 sn) → 10 sn ≈ 5 deneme + 1 kurtarma. Telemetri penceresi 1 sn.
ESIK_S = 10.0


class MlxBekci:
    """Bobin başına son `B=` anı; `tikla()` yeni düşenleri bir kez döndürür. İş parçacığı güvenli (okuyucu + bağlantı geçişleri)."""

    def __init__(self, saat=time.monotonic, esik_s: float = ESIK_S):
        self._saat = saat
        self._esik = float(esik_s)
        self._kilit = threading.Lock()
        self._son: dict[int, float] = {}
        self._dustu: set[int] = set()
        self._bagli = False
        # YS2 d (B5, YG0 25-11) TANI: uyarı 2 kez kendiliğinden düzeldi, doğrudan COM'da kesinti yok → kart mı sustu, okuyucu mu
        # duraksadı? Son tık anı + bobin başına son `B=`den beri okuyucu döngüsünün EN UZUN tık aralığı (yalnız günlüğe; karar AYNI).
        self._son_tik: float | None = None
        self._en_uzun_ara: dict[int, float] = {}

    def baglandi(self) -> None:
        with self._kilit:
            simdi = self._saat()
            self._bagli = True
            for coil_id in self._son:
                self._son[coil_id] = simdi
            self._dustu.clear()
            self._son_tik = None  # kopukken geçen süre okuyucu duraksaması SAYILMAZ (bağlanınca baştan)
            self._en_uzun_ara.clear()

    def koptu(self) -> None:
        with self._kilit:
            self._bagli = False

    def veri(self, coil_id: int) -> None:
        """Bu bobinden `B=` geldi (doğrulanmamış `B=` de sensörün YAŞADIĞINI gösterir)."""
        with self._kilit:
            c = int(coil_id)
            self._son[c] = self._saat()
            self._dustu.discard(c)
            self._en_uzun_ara[c] = 0.0

    def tikla(self) -> list[int]:
        """Eşiği yeni aşan (henüz bildirilmemiş) bobinler; bağlı değilken boş."""
        with self._kilit:
            if not self._bagli:
                return []
            simdi = self._saat()
            if self._son_tik is not None:
                ara = simdi - self._son_tik
                for c in self._son:
                    self._en_uzun_ara[c] = max(self._en_uzun_ara.get(c, 0.0), ara)
            self._son_tik = simdi
            yeni = sorted(c for c, t in self._son.items() if c not in self._dustu and simdi - t >= self._esik)
            self._dustu.update(yeni)
            return yeni

    def tani(self, coil_id) -> tuple[float, float]:
        """YS2 d (B5) TANI: (son `B=`den beri geçen sn, okuyucu döngüsünün bu sürede EN UZUN tık aralığı sn). İkincisi birincisine
        yakınsa okuyucu DURAKSAMIŞTIR (yanlış uyarı adayı — ağır CV / model yüklemesi); küçükse kart gerçekten `B=` basmamıştır."""
        with self._kilit:
            c = int(coil_id)
            t = self._son.get(c)
            return (0.0 if t is None else self._saat() - t, self._en_uzun_ara.get(c, 0.0))
