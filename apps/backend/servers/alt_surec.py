# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GA (istem 53) — ana sunucunun YARDIMCI ALT SÜREÇLERİ (canlı alan hesabı; geliştirici modül sürücüleri): aynı çalıştırılabilirin
`--alt-surec <ad>` alt komutu, konsol penceresi AÇMADAN (`utils.gizli_surec`), DÜŞÜK öncelikle, JSON satırlarıyla (stdin istek → stdout
yanıt; port / ağ YOK).

NEDEN SÜREÇ (iş parçacığı DEĞİL) — ÖLÇÜLDÜ 18-11 (PC, gerçek alan tablosu): alan modeli kurulurken (RL dalga benzetimi, Python döngüsü
GIL'i tutar) `POST /api/hardware/emergency_stop` p50 4,9 → 288 ms; sürekli Gram hesabında bile en kötü 21 → 34 ms. Ayrı süreç GIL'i
paylaşmaz; düşük öncelik (BELOW_NORMAL) ana sunucuya — ACİL DURDUR, sürüş, keep-alive — işlemcide ÖNCELİK bırakır.

Sahada Python YOK (donmuş EXE): alt süreç `PEMF_Backend.exe --alt-surec <ad>` (kurtarma / destek paketi alt komutlarıyla aynı desen,
`backend_service.main`); kaynaktan koşuda `python backend_service.py --alt-surec <ad>`. Ebeveyn ölürse stdin kapanır → alt süreç çıkar.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import threading

logger = logging.getLogger(__name__)

ALT_KOMUT = "--alt-surec"
#: Windows BELOW_NORMAL_PRIORITY_CLASS — alt süreç ana sunucuyla işlemci yarışında GERİDE kalır.
DUSUK_ONCELIK = 0x0000_4000
#: Alt süreçte BLAS / OpenMP tek iş parçacığı (LattePanda 4 çekirdek: sürüş, arayüz, kamera AI ile paylaşılır).
TEK_IS_PARCACIGI = {
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "PYTHONIOENCODING": "utf-8",
}
_BACKEND_DIZINI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND_SERVICE = os.path.join(_BACKEND_DIZINI, "backend_service.py")
#: Kaynak kipi önyükleyicisi: gömülü Python (`._pth` kipi) betik dizinini `sys.path`'e KOYMAZ (ölçüldü: `No module named 'utils'`) →
#: `apps/backend` açıkça eklenir, `backend_service` `__main__` olarak koşar; kalan argv `[-c, --alt-surec, ad, …]`.
_ONYUKLEYICI = (
    "import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); runpy.run_path(sys.argv.pop(1), run_name='__main__')"
)


def komut(ad: str, *arg: str) -> list[str]:
    """Alt süreç komut satırı: donmuş → `[PEMF_Backend.exe, --alt-surec, ad, …]`; kaynak → `[python, -X utf8, -c <önyükleyici>,
    apps/backend, backend_service.py, --alt-surec, ad, …]`."""
    if getattr(sys, "frozen", False):
        return [sys.executable, ALT_KOMUT, ad, *arg]
    return [sys.executable, "-X", "utf8", "-c", _ONYUKLEYICI, _BACKEND_DIZINI, _BACKEND_SERVICE, ALT_KOMUT, ad, *arg]


def calistir(argv: list[str]) -> int:
    """`backend_service.main` → `--alt-surec <ad> …` dağıtıcısı (sunucu / port / donanım / veritabanı AÇILMAZ)."""
    if not argv:
        return 2
    ad, kalan = argv[0], list(argv[1:])
    if ad == "canli-alan":
        from servers.canli_alan_hesapci import main as _main

        return _main(kalan)
    if ad == "modul-surucu":
        from servers.modul_surucu import main as _modul_main

        return _modul_main(kalan)
    return 2


def json_satir_dongusu(isle, girdi=None, cikti=None) -> int:
    """Alt süreç tarafı: her girdi satırı bir JSON istek → `isle(istek)` → bir JSON yanıt satırı. İşleyici istisnası yanıt olarak döner
    (`{"hata": tür}`) — döngü SÜRER. Bozuk satır → `{"hata": "bozukIstek"}`. Girdi kapanınca (ebeveyn öldü / kapattı) 0 döner."""
    girdi = sys.stdin if girdi is None else girdi
    cikti = sys.stdout if cikti is None else cikti
    for satir in girdi:
        satir = satir.strip()
        if not satir:
            continue
        try:
            istek = json.loads(satir)
            if not isinstance(istek, dict):
                raise ValueError("nesne değil")
        except ValueError:
            yanit = {"hata": "bozukIstek"}
        else:
            try:
                yanit = isle(istek)
            except Exception as e:  # işleyici hatası alt süreci düşürmez
                yanit = {"hata": type(e).__name__}
        cikti.write(json.dumps(yanit, ensure_ascii=False) + "\n")
        cikti.flush()
    return 0


class JsonSatirSureci:
    """Ebeveyn tarafı: alt süreci (gerekince) başlatır, istek yazar, yanıtı ZAMAN AŞIMIYLA bekler. Zaman aşımı / ölü süreç → None
    (çağıran fail-safe davranır); takılan süreç öldürülür, sonraki istek yeniden başlatır. Aynı anda TEK istek (kilit)."""

    def __init__(self, komut_satiri: list[str], ad: str = "alt-surec", baslatici=None):
        self._komut = list(komut_satiri)
        self._ad = ad
        self._baslatici = baslatici or self._varsayilan_baslatici
        self._kilit = threading.Lock()
        self._p = None
        self._yanitlar: queue.Queue = queue.Queue()

    @staticmethod
    def _varsayilan_baslatici(komut_satiri: list[str]):
        from utils import gizli_surec

        return gizli_surec.baslat(
            komut_satiri,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={**os.environ, **TEK_IS_PARCACIGI},
            creationflags=gizli_surec.bayraklar() | (DUSUK_ONCELIK if os.name == "nt" else 0),
        )

    def calisiyor(self) -> bool:
        return self._p is not None and self._p.poll() is None

    def _baslat(self) -> None:
        self._yanitlar = queue.Queue()
        self._p = self._baslatici(self._komut)
        threading.Thread(target=self._oku, args=(self._p, self._yanitlar), daemon=True, name=f"{self._ad}-oku").start()

    @staticmethod
    def _oku(p, kuyruk: queue.Queue) -> None:
        try:
            for satir in p.stdout:
                try:
                    kuyruk.put(json.loads(satir.decode("utf-8")))
                except ValueError:
                    kuyruk.put({"hata": "bozukYanit"})
        except (OSError, ValueError):
            pass
        kuyruk.put(None)  # akış bitti: süreç öldü / kapandı

    def istek(self, veri: dict, zaman_asimi: float) -> dict | None:
        with self._kilit:
            try:
                if not self.calisiyor():
                    self._baslat()
                self._p.stdin.write((json.dumps(veri, ensure_ascii=False) + "\n").encode("utf-8"))
                self._p.stdin.flush()
            except (OSError, ValueError):
                logger.warning("%s: istek yazılamadı — süreç yeniden başlatılacak", self._ad)
                self._durdur()
                return None
            try:
                yanit = self._yanitlar.get(timeout=zaman_asimi)
            except queue.Empty:
                logger.warning("%s: %.1f sn içinde yanıt yok — süreç durduruluyor", self._ad, zaman_asimi)
                self._durdur()
                return None
            if yanit is None:
                self._durdur()
            return yanit

    def _durdur(self, bekle_s: float = 2.0) -> None:
        p, self._p = self._p, None
        if p is None:
            return
        try:
            p.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            p.wait(timeout=bekle_s)
        except subprocess.TimeoutExpired:
            p.kill()
            try:
                p.wait(timeout=bekle_s)
            except subprocess.TimeoutExpired:
                logger.warning("%s: alt süreç sonlandırılamadı (pid %s)", self._ad, getattr(p, "pid", "?"))

    def kapat(self) -> None:
        """Alt süreci kapatır (stdin kapanır → döngü çıkar; çıkmazsa öldürülür)."""
        with self._kilit:
            self._durdur()
