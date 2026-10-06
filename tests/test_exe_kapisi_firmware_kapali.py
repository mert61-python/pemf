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

from types import SimpleNamespace

import pytest
from exe_kapisi_surucusu import PWSH, build_makinesi_ortami, kapi_blogunu_kostur, kostur_ortami


def _gercek_com_mu(port: str) -> bool:
    """BEYAZ LİSTE (tur 3 incelemesi): yalnız 'SIM' ya da pyserial URL'leri (socket://, loop://) güvenli.
    `\\\\.\\COM10`, boş, 'auto' ya da başka her değer gerçek karta ulaşabilir sayılır."""
    p = (port or "").strip()
    return not (p.upper() == "SIM" or p.lower().startswith(("socket://", "loop://")))


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


def _yakma_zinciri(monkeypatch, fw_otomatik) -> tuple[list, dict]:
    """GERÇEK `_donanim_guncellemesi_safe` → `acilis_denetimi` zinciri: ayrıştırılabilir banner, yakmayı
    gerektiren sahte manifest. `_firmware_uygula` (indir+yak) KAYDEDİCİYLE değişir — gerçek yakma YOK.
    (yakılanlar, zincir sonundaki `firmware_manager.durum()`) döner: "yakmadı"nın "zincir çöktü" değil
    "plan FIRMWARE_GUNCELLE ama uygulanmadı" olduğu ayırt edilebilsin."""
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
    # Her koşum TEMİZ durumla başlar (önceki koşumun FIRMWARE_GUNCELLE'si "çöktü"yü gizlemesin) ve modül
    # düzeyi durum sonraki testlere SIZMAZ (monkeypatch geri alır).
    monkeypatch.setattr(fm, "_durum", {})
    monkeypatch.setattr(fm, "manifest_oku", lambda *a, **k: manifest)
    monkeypatch.setattr(fm, "_firmware_uygula", lambda girdi, plan, *a, **k: yakilan.append(plan.hedef_surum) or {})
    if fw_otomatik is None:
        monkeypatch.delenv("PEMF_FW_AUTO_UPDATE", raising=False)
    else:
        monkeypatch.setenv("PEMF_FW_AUTO_UPDATE", fw_otomatik)

    class _Kayit:
        def __getattr__(self, ad):
            return lambda *a, **k: None

    bs._donanim_guncellemesi_safe(SimpleNamespace(stm_kimlik=kimlik, stm_is_connected=True), _Kayit())
    return yakilan, fm.durum()


def test_KRITIK_bu_ortamlarla_donanim_guncellemesi_YAKMAZ(tmp_path, monkeypatch):
    from utils import surum_uyumu as su

    # Senaryo gerçekten yakmaya ulaşabiliyor mu (oto-güncelleme AÇIKÇA etkin): ulaşmıyorsa test kör.
    assert _yakma_zinciri(monkeypatch, "1")[0] == ["9.9.9"], "senaryo yakmaya ULAŞMADI — kapı kör olurdu"

    (tmp_path / "u").mkdir()
    ortamlar = [("urun_senaryolari", kostur_ortami(tmp_path / "u", monkeypatch))]
    if PWSH:  # build betiği pwsh ile koşar; yoksa (Linux CI) yalnız ürün senaryoları ortamı sınanır
        (tmp_path / "b").mkdir()
        yakalanan = kapi_blogunu_kostur(tmp_path / "b", build_makinesi_ortami(tmp_path)).get("yakalanan") or {}
        ortamlar.append(("build AI kapısı", yakalanan.get("Env") or {}))
    for ad, env in ortamlar:
        yakilan, durum = _yakma_zinciri(monkeypatch, env.get("PEMF_FW_AUTO_UPDATE"))
        assert yakilan == [], f"{ad} ortamıyla açılış donanım güncellemesi firmware YAKTI: {yakilan} (D-9.3)"
        # "yakmadı" = plan yakmayı GEREKTİRDİ ama oto-güncelleme KAPALI olduğu için uygulanmadı (zincir çökmedi)
        assert durum.get("eylem") == su.FIRMWARE_GUNCELLE and durum.get("uygulandi") is False, (
            f"{ad}: zincir planı FIRMWARE_GUNCELLE'ye ulaşmadı ya da uyguladı — 'yakmadı' başka bir sebepten: {durum}"
        )


def test_KRITIK_urun_senaryolari_ek_sozlugu_FW_ve_STM_PORTU_EZEMEZ(tmp_path, monkeypatch):
    """`kostur(ek=...)` senaryoya özgü değişkenleri verir; güvenlik anahtarlarını SESSİZCE ezmemeli (tur 3)."""
    import exe_kapisi_surucusu as ks

    yakalanan = {}

    class _SahteSurec:
        def __init__(self, argv, env=None, **kw):
            yakalanan["env"] = {k.upper(): v for k, v in (env or {}).items()}

        def poll(self):
            return 0

    for ad in ks.YALITIM_DEGISKENLERI:
        monkeypatch.delenv(ad, raising=False)
    us = ks.urun_senaryolari_modulu()
    monkeypatch.setattr(us, "subprocess", ks.AltSurecVekili(Popen=_SahteSurec))
    (tmp_path / "calisma").mkdir()
    monkeypatch.setattr(us, "CALISMA", tmp_path / "calisma")
    ek = {"PEMF_FW_AUTO_UPDATE": "1", "PEMF_STM_PORT": "COM10"}
    us.kostur(tmp_path / "veri", sifreli=False, ek=ek, sure=1, saglik_bekle=False)
    env = yakalanan["env"]
    assert env.get("PEMF_FW_AUTO_UPDATE") == "0" and not _gercek_com_mu(env.get("PEMF_STM_PORT", "")), (
        f"kostur(ek=...) güvenlik anahtarlarını EZDİ: FW={env.get('PEMF_FW_AUTO_UPDATE')!r} "
        f"STM_PORT={env.get('PEMF_STM_PORT')!r} (D-9.3)"
    )
