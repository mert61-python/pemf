# Author: mertaygn, cglrgrkn
"""SİYAH KONSOL PENCERESİ REGRESYON KAPISI (backend tarafı).

SAHA ŞİKÂYETİ (2026-08-11): "client güncellemesi için uygulamayı kapatıp geri açtığımda siyah
konsol penceresi çıktı."

Backend, launcher tarafından KONSOLSUZ (`CREATE_NO_WINDOW`) başlatılır. Konsolsuz bir süreçten
konsol-altsistem bir program (powershell, ffmpeg, netsh, taskkill…) çalıştırılınca Windows ona
YENİ BİR KONSOL açar. Tek bir yerde bayrağı unutmak yeterlidir; bu yüzden tek tek düzeltmek
değil, KAYNAK DENETİMİ gerekir.

⚠️ Bu dosya ÇALIŞMA-ZAMANI kodunu denetler. Derleme araçları (`build_tools/`) ve geliştirici
test koşucuları (`tools/e2e_*`) hariçtir: onlar operatörün makinesinde değil, bizim konsolumuzda
çalışır ve pencereleri zaten görünürdür.
"""

import ast
import os
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent

#: Operatörün makinesinde çalışan (yani pencere gösterebilecek) kaynak ağaçları.
CALISMA_ZAMANI = ("servers", "services", "utils", "database", "ai_hub", "hardware")
#: Kök dizindeki tek dosya giriş noktaları.
KOK_DOSYALAR = ("backend_service.py", "headless_core.py")

SPAWN_ADLARI = {"Popen", "run", "call", "check_call", "check_output"}

#: Bayrak vermesi GEREKMEYEN yerler ve sebepleri.
MUAF = {
    # Yardımcının KENDİSİ — bayrağı burada uygular.
    "utils/gizli_surec.py",
    # Yalnız macOS kolunda çalışır (`ioreg`); Windows konsolu açamaz.
    "utils/secrets_manager.py",
}


def _kaynaklar():
    for alt in CALISMA_ZAMANI:
        d = KOK / alt
        if not d.is_dir():
            continue
        for kok, dizinler, adlar in os.walk(d):
            dizinler[:] = [x for x in dizinler if x not in {"__pycache__", "node_modules"}]
            for ad in adlar:
                if ad.endswith(".py"):
                    yield Path(kok) / ad
    for ad in KOK_DOSYALAR:
        p = KOK / ad
        if p.is_file():
            yield p


def _bayraksiz_spawnlar():
    ihlaller = []
    for p in _kaynaklar():
        rel = p.relative_to(KOK).as_posix()
        if rel in MUAF:
            continue
        try:
            agac = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for d in ast.walk(agac):
            if not isinstance(d, ast.Call):
                continue
            f = d.func
            if not (isinstance(f, ast.Attribute) and f.attr in SPAWN_ADLARI):
                continue
            if getattr(f.value, "id", None) != "subprocess":
                continue
            anahtarlar = {k.arg for k in d.keywords}
            # `creationflags=` doğrudan verilmiş VEYA `**kwargs` ile geçiliyor (kwargs sözlüğüne
            # `_windows_creationflags()` konan mevcut desen) → kabul.
            if "creationflags" in anahtarlar or None in anahtarlar:
                continue
            ihlaller.append(f"{rel}:{d.lineno}  subprocess.{f.attr}")
    return ihlaller


def test_KRITIK_calisma_zamaninda_bayraksiz_spawn_YOK():
    """Her `subprocess.*` çağrısı ya `creationflags` vermeli ya `utils.gizli_surec` kullanmalı.

    Kırmızıya dönerse: operatör ekranında siyah konsol penceresi yanıp sönecek."""
    ihlaller = _bayraksiz_spawnlar()
    assert not ihlaller, (
        "Bu spawn'lar operatör ekranında SİYAH KONSOL açar. `utils.gizli_surec.calistir/baslat` "
        "kullanın (ya da creationflags verin):\n  " + "\n  ".join(ihlaller)
    )


def test_KRITIK_yardimci_CREATE_NO_WINDOW_uygular():
    """Bayrak sabiti kaybolursa yardımcı sessizce ETKİSİZ kalır ve yukarıdaki denetim
    "hepsi yardımcıyı kullanıyor" diye YEŞİL yanmaya devam eder — yanlış güvence."""
    from utils.gizli_surec import CREATE_NO_WINDOW, bayraklar

    assert CREATE_NO_WINDOW == 0x0800_0000
    if os.name == "nt":
        assert bayraklar() & CREATE_NO_WINDOW, "bayraklar() CREATE_NO_WINDOW vermiyor"
        assert bayraklar(ayrik=True) & CREATE_NO_WINDOW, "ayrık kolda CREATE_NO_WINDOW düşmüş"
    else:
        assert bayraklar() == 0, "Windows dışında bayrak verilmemeli"


def test_denetim_GERCEKTEN_tarayabiliyor():
    """Karşı-kanıt: tarayıcı hiç dosya bulamıyorsa yukarıdaki test her koşulda yeşil yanar."""
    n = sum(1 for _ in _kaynaklar())
    assert n > 20, f"kaynak taraması çok az dosya buldu ({n}) — denetim gerçeği ölçmüyor olabilir"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
