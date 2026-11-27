# -*- coding: utf-8 -*-
"""D4.02 · B-10.6 · B-10.7 — kapsam ölçümünün `source` kümesi ürün kodunun TAMAMINI kapsar.

🔴 ÖLÇÜLEN DURUM (2026-10-10, 4-A): `[tool.coverage.run] source = ["servers", "database", "controllers", "utils"]` idi.
F4 taşımasıyla (2026-09-18) `apps/backend/` altına giren `services/` paketi (Mosquitto / ağ durumu / UDP keşif
süpervizörleri, cihaz kimlik bilgileri, DB bakımı) ve üst düzey `backend_service` (açılış FİRMWARE zinciri, ACİL DURDUR
açılış yolu), `headless_core` (STM telemetri ayrıştırıcı) ve `event_bus` modülleri ÖLÇÜLMÜYORDU: bu yüzeylerde kapsam
düşse de ratchet kıpırdamıyordu. Ayrıca eşik, ölçülen değerin 17–21 puan altındaydı (büyük gerilemeyi sessizce geçirir).

KAPI: `source` = (pyproject `[tool.setuptools.package-dir]`'de `apps/backend/` altına eşlenen ürün paketleri) ∪
(`apps/backend/` altındaki İZLENEN üst düzey `.py` modülleri) — TAM eşitlik: eksik ad = ölçülmeyen ürün kodu; fazla ad =
var olmayan kaynak (coverage yalnız "never imported" UYARISI verir, düşmez). Küme kaynaktan TÜRETİLİR, elle yazılmaz.

⚠️ Kapsam sınırı (4-A inc. S-A2.3): `ai_service/` ayrı süreçtir (bilinçli dışarıda).
S-4B.2 [ÖNERİLEN UYGULANDI] (4-A inc. S-4A.3): depo KÖKÜNDEKİ, backend sürecinde içe aktarılan kod da ürün kodudur. Küme ayrıca
backend başlangıç köklerinden (`check_headless_imports.DEFAULT_ROOTS`) TÜM birinci-taraf import kenarlarıyla (eager / lazy, açık /
korunan) ERİŞİLEN ve `apps/backend` DIŞINDA çözülen modüllerden TÜRETİLİR: kök paketi olduğu gibi girer (bugün `ai`, `pemf_gui`);
iki bilinçli istisna `KOK_PAKET_ISTISNA`'da gerekçesiyle (ai_hub = mevcut ağır/ayrı politikası; tools = geliştirici araç paketi —
içinden ERİŞİLEN modüller TEK TEK girer: bugün `tools.kurtarma` — `PEMF_Backend.exe --kurtarma` — ve
`tools.destek_paketi` — `PEMF_Backend.exe --destek-paketi`, D6.47).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

try:  # tomllib yalnız 3.11+; depo 3.10'a kilitli (bkz. test_paket_sinirlari)
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover
    import tomli as _toml

KOK = Path(__file__).resolve().parents[1]
BACKEND = "apps/backend"
#: Backend'den erişilen ama PAKET düzeyinde kaynağa GİRMEYEN kök paketleri (gerekçe zorunlu).
KOK_PAKET_ISTISNA = {
    "ai_hub": "Y326 (istem 66 CT1 g): ÖLÇÜLÜR (`source`) ama sunucu toplamının DIŞINDA (`report.omit`) — ayrı taban "
    "`tests/kapsam_tabani.json`; import grafiği türetmesine girmez (paket bütün olarak `source`ta)",
    "tools": "geliştirici araç paketi (e2e, sniffer…) — yalnız backend'den ERİŞİLEN modülleri tek tek girer",
}


def _pyproject() -> dict:
    return _toml.loads((KOK / "pyproject.toml").read_text(encoding="utf-8"))


def urun_kumesi(t: dict) -> set[str]:
    """Ürün paketleri (package-dir → apps/backend/…) ∪ apps/backend üst düzey izlenen modüller."""
    paket_dizini = t["tool"]["setuptools"]["package-dir"]
    paketler = {ad for ad, yol in paket_dizini.items() if yol.replace("\\", "/").startswith(BACKEND + "/")}
    ls = subprocess.run(["git", "ls-files", "-z", "--", BACKEND], cwd=KOK, capture_output=True, timeout=120)
    assert ls.returncode == 0, f"git ls-files düştü: {ls.stderr[:200]!r}"
    moduller = set()
    for yol in (x.decode("utf-8") for x in ls.stdout.split(b"\x00") if x):
        parca = yol.split("/")
        if len(parca) == 3 and parca[2].endswith(".py") and parca[2] != "__init__.py":
            moduller.add(parca[2][:-3])
        # 4-A inc. 4A-2.12: `package-dir`'e eklenmeden gelen alt paket de ürün kodudur (çalışma anında apps/backend sys.path'te).
        if len(parca) == 4 and parca[3] == "__init__.py":
            moduller.add(parca[2])
    return paketler | moduller | kok_kumesi()


def _erisilen_kok_modulleri() -> set[str]:
    """Backend başlangıç köklerinden erişilen, `apps/backend` DIŞINDA (depo kökünde) çözülen birinci-taraf modüller."""
    import importlib.util
    from collections import deque

    sp = importlib.util.spec_from_file_location("_chi_d402", KOK / "scripts" / "check_headless_imports.py")
    chi = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(chi)
    backend = (KOK / BACKEND).resolve()
    gorulen, dq, kok = set(chi.DEFAULT_ROOTS), deque(chi.DEFAULT_ROOTS), set()
    while dq:
        mod = dq.popleft()
        yol = chi.module_to_path(mod)
        if yol is None:
            continue
        if backend not in Path(yol).resolve().parents:
            kok.add(mod)
        b = chi.analyze(yol)
        for d in b["fp_eager"] | b["fp_eager_g"] | b["fp_lazy"] | b["fp_lazy_g"]:
            if d not in gorulen:
                gorulen.add(d)
                dq.append(d)
    return kok


def kok_kumesi() -> set[str]:
    """Kök paketi PAKET olarak; `KOK_PAKET_ISTISNA`'daki `tools` yalnız erişilen MODÜLLERİYLE; ai_hub hiç."""
    kume = set()
    for mod in _erisilen_kok_modulleri():
        ust = mod.split(".")[0]
        if ust == "ai_hub":
            continue
        kume.add(mod if ust in KOK_PAKET_ISTISNA else ust)
    return kume


def _urun_dosyalari() -> list[str]:
    ls = subprocess.run(["git", "ls-files", "-z", "--", BACKEND], cwd=KOK, capture_output=True, timeout=120)
    assert ls.returncode == 0, f"git ls-files düştü: {ls.stderr[:200]!r}"
    return [x.decode("utf-8") for x in ls.stdout.split(b"\x00") if x and x.endswith(b".py")]


def test_KRITIK_kapsam_source_URUN_KODUNA_esit():
    t = _pyproject()
    urun = urun_kumesi(t)
    assert len(urun) >= 8, f"VAKUM: ürün kümesi yalnız {sorted(urun)} — türetme bozuk (paket-dir / git ls-files)"
    assert {"services", "backend_service"} <= urun, f"türetme ürün kodunu görmüyor: {sorted(urun)}"
    assert {"ai", "pemf_gui"} <= urun, (
        f"türetme backend'in içe aktardığı KÖK paketlerini görmüyor (S-4A.3): {sorted(urun)}"
    )
    source = set(t["tool"]["coverage"]["run"]["source"])
    # Y326: ai_hub ayrı tabanla ölçülür — source'ta OLMALI, sunucu raporunun (fail_under) DIŞINDA kalmalı
    assert "ai_hub" in source, "Y326: ai_hub ölçümden çıkarılmış"
    assert "*/ai_hub/*" in t["tool"]["coverage"]["report"].get("omit", []), (
        "ai_hub sunucu toplamına karışıyor (fail_under 100)"
    )
    source -= {"ai_hub"}
    eksik, fazla = sorted(urun - source), sorted(source - urun)
    assert not eksik, f"kapsam ÖLÇMÜYOR (ratchet bu kodda kördür): {eksik}"
    assert not fazla, f"kapsam source'unda var olmayan ürün adı (coverage yalnız uyarır): {fazla}"
    # 4-A inc. 4A-2.12: `omit` ürün dosyasını ölçümden çıkarmamalı (coverage göreli deseni cwd'ye göre mutlaklaştırır).
    import fnmatch

    desenler = [
        d if d.startswith("*") or Path(d).is_absolute() else (KOK / d).as_posix()
        for d in t["tool"]["coverage"]["run"].get("omit", [])
    ]
    disarida = sorted(y for y in _urun_dosyalari() if any(fnmatch.fnmatch((KOK / y).as_posix(), d) for d in desenler))
    assert not disarida, f"[tool.coverage.run] omit ürün kodunu ölçümden ÇIKARIYOR: {disarida[:10]}"


def test_KARSIT_KANIT_turetme_paket_disi_ve_test_dizinini_ALMAZ():
    """Türetme `scripts`/`build_tools` (kurulum paketi ama ürün çalışma kodu değil) ve `tests`i ürün saymaz."""
    urun = urun_kumesi(_pyproject())
    assert not {"scripts", "build_tools", "tests", "ai_hub", "__init__"} & urun, sorted(urun)


def test_KARSIT_KANIT_kok_turetme_AI_HUB_ve_TOOLS_paketini_ALMAZ():
    """Kök türetmesi ai_hub'ı hiç, tools'u paket olarak almaz (yalnız erişilen modülü); erişilen kök modülleri boş değil."""
    kok = kok_kumesi()
    assert kok, "VAKUM: backend'den erişilen kök modülü yok — import grafiği bozuk"
    assert not {"ai_hub", "tools"} & kok and not any(k.startswith("ai_hub.") for k in kok), sorted(kok)
