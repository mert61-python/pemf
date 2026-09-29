# -*- coding: utf-8 -*-
"""D0Ö.03 (D-9.3) KAPISI — build AI kapısı ve ürün senaryoları EXE'yi firmware YAKAMAYACAK ortamla başlatır.

ARIZA (DENETIM-09 D-9.3, sahte yakmayla ölçüldü): HEAD'de `PEMF_FW_AUTO_UPDATE` varsayılanı '1'
(`backend_service.py` `_donanim_guncellemesi_safe`). Build AI kapısı (`scripts/build_backend_exe.ps1`)
ve ürün senaryoları (`scripts/urun_senaryolari.py` `kostur`) EXE'yi bu değişkeni ve `PEMF_STM_PORT`'u
VERMEDEN başlatıyordu → build makinesinde gerçek STM (varsayılan COM10) takılıysa, banner ayrıştırıcısı
(B-4.2) düzelip manifeste kural girdiği an kapı firmware YAKMAYA ulaşır; yakma, bobin sürülürken MCU'yu
resetler. `PEMF_SIMULATE` `stm_bagli`yı ETKİLEMİYOR.

KOLLAR:
  (1) Build AI kapısı bloğu (gerçek metni, `Start-Process` gölgelenerek) EXE'ye `PEMF_FW_AUTO_UPDATE='0'`
      ve gerçek olmayan bir `PEMF_STM_PORT` verir.
  (2) `urun_senaryolari.kostur` aynı ikisini verir (Popen sahte — EXE başlatılmaz).
  (3) Davranış: bu ortamlarla GERÇEK `_donanim_guncellemesi_safe` → `acilis_denetimi` zinciri, ayrıştırılabilir
      banner + yakmayı gerektiren sahte manifest kuralıyla çağrılır → yakma (`_firmware_uygula`) ÇAĞRILMAZ.
      Senaryonun yakmaya GERÇEKTEN ulaşabildiği, oto-güncelleme AÇIKÇA etkinken ayrıca doğrulanır.
Dış ortam (koşucu/CI) bu değişkenleri kendi verebilir → iki kol da ÖNCE onları siler (sahte-yeşil olmasın).
MUTASYON: iki betikten birinde `PEMF_FW_AUTO_UPDATE` satırını silmek → KIRMIZI.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from exe_kapisi_surucusu import PWSH, build_makinesi_ortami, kapi_blogunu_kostur, kostur_ortami


def _gercek_com_mu(port: str) -> bool:
    p = (port or "").strip().lower()
    return p == "" or p in ("auto", "otomatik") or re.fullmatch(r"com\d+", p) is not None


@pytest.mark.skipif(PWSH is None, reason="pwsh (PowerShell 7) yok — build betiği pwsh ile koşar")
def test_KRITIK_build_AI_kapisi_EXE_ortami_firmware_YAKAMAZ(tmp_path):
    veri = kapi_blogunu_kostur(tmp_path, build_makinesi_ortami(tmp_path))
    assert veri.get("yakalanan"), f"kapı bloğu EXE'yi başlatmadı (Start-Process çağrılmadı): {veri.get('hata')}"
    env = veri["yakalanan"]["Env"]
    assert env.get("PEMF_FW_AUTO_UPDATE") == "0", (
        f"build AI kapısı EXE'yi PEMF_FW_AUTO_UPDATE={env.get('PEMF_FW_AUTO_UPDATE')!r} ile başlatıyor — "
        "takılı gerçek STM'e firmware yakmaya ulaşabilir (D-9.3)"
    )
    assert not _gercek_com_mu(env.get("PEMF_STM_PORT", "")), (
        f"build AI kapısı gerçek bir STM portuna bağlanabilir: PEMF_STM_PORT={env.get('PEMF_STM_PORT')!r}"
    )


def test_KRITIK_urun_senaryolari_EXE_ortami_firmware_YAKAMAZ(tmp_path, monkeypatch):
    env = kostur_ortami(tmp_path, monkeypatch)
    assert env.get("PEMF_FW_AUTO_UPDATE") == "0", (
        f"urun_senaryolari EXE'yi PEMF_FW_AUTO_UPDATE={env.get('PEMF_FW_AUTO_UPDATE')!r} ile başlatıyor (D-9.3)"
    )
    assert not _gercek_com_mu(env.get("PEMF_STM_PORT", "")), (
        f"urun_senaryolari gerçek bir STM portuna bağlanabilir: PEMF_STM_PORT={env.get('PEMF_STM_PORT')!r}"
    )


def _yakma_zinciri(monkeypatch, fw_otomatik) -> list:
    """GERÇEK `_donanim_guncellemesi_safe` → `acilis_denetimi` zinciri: ayrıştırılabilir banner, yakmayı
    gerektiren sahte manifest. `_firmware_uygula` (indir+yak) KAYDEDİCİYLE değişir — gerçek yakma YOK."""
    import backend_service as bs
    from servers import firmware_manager as fm
    from utils.stm32_kimlik import banner_ayristir
    from utils.surum_uyumu import surum_demeti

    kimlik = banner_ayristir("-> STM_READY: 2.3.0 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) Waiting for commands...")
    assert kimlik is not None and surum_demeti(kimlik.surum) is not None, "banner ayrıştırılamadı (senaryo kör)"
    manifest = {
        "firmware": {"stm32": {"version": "9.9.9", "url": "https://sahte.invalid/fw.bin", "sha256": "0" * 64}},
        "uyumluluk": [{"clientMin": "0.0.0", "firmwareMin": "9.9.9"}],
    }
    yakilan = []
    monkeypatch.setattr(fm, "_durum", dict(fm._durum))  # modül düzeyi durum sonraki testlere SIZMASIN
    monkeypatch.setattr(fm, "manifest_oku", lambda *a, **k: manifest)
    monkeypatch.setattr(fm, "_firmware_uygula", lambda girdi, plan, backend: yakilan.append(plan.hedef_surum) or {})
    if fw_otomatik is None:
        monkeypatch.delenv("PEMF_FW_AUTO_UPDATE", raising=False)
    else:
        monkeypatch.setenv("PEMF_FW_AUTO_UPDATE", fw_otomatik)

    class _Kayit:
        def __getattr__(self, ad):
            return lambda *a, **k: None

    bs._donanim_guncellemesi_safe(SimpleNamespace(stm_kimlik=kimlik, stm_is_connected=True), _Kayit())
    return yakilan


def test_KRITIK_bu_ortamlarla_donanim_guncellemesi_YAKMAZ(tmp_path, monkeypatch):
    # Senaryo gerçekten yakmaya ulaşabiliyor mu (oto-güncelleme AÇIKÇA etkin): ulaşmıyorsa test kör.
    assert _yakma_zinciri(monkeypatch, "1") == ["9.9.9"], "senaryo yakmaya ULAŞMADI — kapı kör olurdu"

    (tmp_path / "u").mkdir()
    ortamlar = [("urun_senaryolari", kostur_ortami(tmp_path / "u", monkeypatch))]
    if PWSH:  # build betiği pwsh ile koşar; yoksa (Linux CI) yalnız ürün senaryoları ortamı sınanır
        (tmp_path / "b").mkdir()
        yakalanan = kapi_blogunu_kostur(tmp_path / "b", build_makinesi_ortami(tmp_path)).get("yakalanan") or {}
        ortamlar.append(("build AI kapısı", yakalanan.get("Env") or {}))
    for ad, env in ortamlar:
        yakilan = _yakma_zinciri(monkeypatch, env.get("PEMF_FW_AUTO_UPDATE"))
        assert yakilan == [], f"{ad} ortamıyla açılış donanım güncellemesi firmware YAKTI: {yakilan} (D-9.3)"
