# Author: mertaygn, cglrgrkn
"""D1.41 · B-10.243 · B-10.257 — `conftest._seans_ve_watchdog_nobeti`nin denetim işlevi KÖR DEĞİL (Ö.6).

Nöbet teardown'da çalıştığı için kendi kırmızısı bir testin içinden iddia edilemez; bu dosya nöbetin SAF
denetim işlevini (`seans_watchdog_nobet_sorunlari`) sahte bir api nesnesiyle sınar: sızan seans raporlanır
VE kapatılır; arka plan iş parçacıkları başlamışken watchdog yoksa ölüm YALNIZ BİR KEZ raporlanır; canlı
watchdog ve temiz seans yanlış alarm üretmez.
"""

from __future__ import annotations

import threading
import types

import conftest
import pytest
from conftest import seans_watchdog_nobet_sorunlari


@pytest.fixture
def bayrak_sifir():
    eski = conftest._WATCHDOG_OLUMU_BILDIRILDI["evet"]
    conftest._WATCHDOG_OLUMU_BILDIRILDI["evet"] = False
    yield
    conftest._WATCHDOG_OLUMU_BILDIRILDI["evet"] = eski


def _api(aktif: bool, bg: bool):
    return types.SimpleNamespace(
        _session_lock=threading.Lock(),
        _active_session={"is_active": aktif, "session_id": "nobet-testi"} if aktif else {},
        _bg_threads_started=bg,
    )


def test_ARAC_sizan_aktif_seans_RAPORLANIR_ve_KAPATILIR(bayrak_sifir):
    api = _api(aktif=True, bg=False)
    sorun = seans_watchdog_nobet_sorunlari(api, [])
    assert len(sorun) == 1 and "SIZDI" in sorun[0]
    assert api._active_session["is_active"] is False, "nöbet sızıntıyı kapatmadı (sonraki teste taşınır)"


def test_ARAC_olu_watchdog_YALNIZ_BIR_KEZ_raporlanir(bayrak_sifir):
    api = _api(aktif=False, bg=True)
    ilk = seans_watchdog_nobet_sorunlari(api, [])
    ikinci = seans_watchdog_nobet_sorunlari(api, [])
    assert len(ilk) == 1 and "ÖLDÜ" in ilk[0]
    assert ikinci == [], "ölüm her testte yeniden raporlanıyor (zincirleme kırmızı — suçlu test görünmez)"


def test_ARAC_temiz_durum_ve_CANLI_watchdog_alarm_URETMEZ(bayrak_sifir):
    canli = types.SimpleNamespace(name="session-watchdog", is_alive=lambda: True)
    assert seans_watchdog_nobet_sorunlari(_api(aktif=False, bg=True), [canli]) == []
    assert seans_watchdog_nobet_sorunlari(_api(aktif=False, bg=False), []) == []


# ── 1-B bağımsız inceleme (i4): uyku nöbetçisi her zaman çalışır ───────────────────────────────────────


def test_ARAC_uyku_nobetcisi_FIRLATAN_sleep_yamasinda_OLUR():
    class _Dur(Exception):
        pass

    def _firlat(_s):
        raise _Dur()

    t = threading.Thread(target=conftest.uyku_nobetcisi_dongusu, kwargs={"uyku": _firlat}, daemon=True)
    t.start()
    t.join(2)
    assert not t.is_alive(), "fırlatan sleep yaması nöbetçiyi öldürmedi — nöbet bu sınıfı göremez"


def test_ARAC_uyku_nobetcisi_FIRLATMAYAN_sahte_sleepte_YASAR_ve_doner():
    sayac = {"n": 0}

    def _aninda(_s):
        sayac["n"] += 1

    t = threading.Thread(target=conftest.uyku_nobetcisi_dongusu, kwargs={"uyku": _aninda}, daemon=True)
    t.start()
    t.join(0.5)
    assert t.is_alive() and 2 <= sayac["n"] <= 50, f"anında dönen sleep'te nöbetçi döngüsü {sayac['n']} tur (dönme yok)"


def test_KRITIK_suit_nobetcisi_CANLI():
    """Süitin kendi nöbetçisi bu noktaya kadar hiçbir süreç geneli yama tarafından öldürülmedi."""
    assert conftest._UYKU_NOBETCISI.is_alive(), "nobetci-uyku ÖLÜ — önceki bir test süreç geneli sleep yaması yaptı"


def surec_geneli_firlatan_sleep_yamalari(kaynak: str) -> list[str]:
    """`setattr(<…time…>, "sleep", f)` / `<…>.sleep = f` — f FIRLATIYOR (raise ya da `.throw(`) ve iş parçacığı
    denetimi (`current_thread` / `get_ident`) İÇERMİYORSA ihlal. Böyle bir yama yama süresince UYUYAN her iş
    parçacığını (session-watchdog dahil) öldürür (B-10.257). Nöbetçi bunu olasılıksal görür; bu tarama deterministik."""
    import ast

    agac = ast.parse(kaynak)
    fonklar = {n.name: n for n in ast.walk(agac) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def firlatir_ve_yerel_degil(d) -> bool:
        if isinstance(d, ast.Name):
            d = fonklar.get(d.id)
        if d is None:
            return False
        firlat = any(isinstance(n, ast.Raise) for n in ast.walk(d)) or any(
            isinstance(n, ast.Attribute) and n.attr == "throw" for n in ast.walk(d)
        )
        yerel = any(
            (isinstance(n, ast.Attribute) and n.attr in ("current_thread", "get_ident"))
            or (isinstance(n, ast.Name) and n.id in ("current_thread", "get_ident"))
            for n in ast.walk(d)
        )
        return firlat and not yerel

    ihlal = []
    for n in ast.walk(agac):
        if (
            isinstance(n, ast.Call)
            and getattr(n.func, "attr", getattr(n.func, "id", "")) == "setattr"
            and len(n.args) >= 3
            and isinstance(n.args[1], ast.Constant)
            and n.args[1].value == "sleep"
            and firlatir_ve_yerel_degil(n.args[2])
        ):
            ihlal.append(f"{n.lineno}: {ast.unparse(n)[:120]}")
        elif (
            isinstance(n, ast.Assign)
            and any(isinstance(h, ast.Attribute) and h.attr == "sleep" for h in n.targets)
            and firlatir_ve_yerel_degil(n.value)
        ):
            ihlal.append(f"{n.lineno}: {ast.unparse(n)[:120]}")
    return ihlal


def test_KRITIK_testlerde_SUREC_GENELI_firlatan_sleep_yamasi_YOK():
    from pathlib import Path

    testler = Path(__file__).resolve().parent
    bulunan = {
        p.name: ihlal
        for p in sorted(testler.glob("*.py"))
        if (ihlal := surec_geneli_firlatan_sleep_yamalari(p.read_text(encoding="utf-8", errors="replace")))
    }
    assert bulunan == {}, (
        f"süreç geneli FIRLATAN sleep yaması (uyuyan iş parçacıklarını öldürür) — `dongu_tek_tur.bir_tur_kos` kullan: {bulunan}"
    )


def test_ARAC_tarayici_FIRLATAN_yamayi_GORUR_yerel_olani_GECIRIR():
    kotu = 'def t(mp):\n    def _s(x):\n        raise RuntimeError()\n    mp.setattr(api.time, "sleep", _s)\n'
    kotu_lambda = 'def t(mp):\n    mp.setattr(api.time, "sleep", lambda _s: (_ for _ in ()).throw(E()))\n'
    yerel = 'def t(mp):\n    def _s(x):\n        if threading.current_thread() is ana:\n            raise E\n    mp.setattr(time, "sleep", _s)\n'
    sessiz = 'def t(mp):\n    mp.setattr(m.time, "sleep", lambda _s: None)\n'
    assert surec_geneli_firlatan_sleep_yamalari(kotu) and surec_geneli_firlatan_sleep_yamalari(kotu_lambda)
    assert surec_geneli_firlatan_sleep_yamalari(yerel) == [] and surec_geneli_firlatan_sleep_yamalari(sessiz) == []
