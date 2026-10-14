# Author: mertaygn, cglrgrkn
"""D1.29 · B-10.215 · B-10.219 · B-10.220 — firmware araç zinciri SAHTE "temiz / uyumlu / tam" demez.

İG-8.28 ve B-8.13 düzeltmelerinden sonra derle → kopyala → yak → kimlik zinciri bu araçlarla yürüyecek (sahaya ELLE
yakılacak firmware dahil). Üç sahte-yeşil:
  (215) `scripts/firmware_derle.py`: `arm-none-eabi-nm` yokken printf-float kapısı koşmadan "SONUC: TEMIZ" → `_printf_float`'
        siz (tüm sensör telemetrisi sessizce ölü) bir ELF yakılabilirdi. Artık ölçülemeyen ürün 1 döner.
  (219) `scripts/stm_firmware_kimligi.py`: karar kendi `kanal >= 7` eşiğindeydi; backend `kanal == paket genişliği` der →
        8 kanallı kartta betik "YENİ FIRMWARE YÜKLÜ", HEAD aynı kartı 409 ile reddeder (plan C1b-89, Y7 sorusu).
  (220) `scripts/stm_workspace_kopyala.py`: protokol işaretleri HAM metinde aranıyordu — `Coil_KipUygula` tanımı ve
        çağrısı silinip yorumu kalan kaynak "tam" sayılıyordu.
Betikler gerçek seri port / derleyici / CubeIDE OLMADAN, mantık işlevleriyle sınanır (`betik_alt_sureci.betik_modulu`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from betik_alt_sureci import betik_modulu

KOK = Path(__file__).resolve().parents[1]
MAIN_C = KOK / "firmware" / "stm32_pemf" / "Core" / "Src" / "main.c"


# ── (215) firmware_derle ────────────────────────────────────────────────────


def _sahte_elf(tmp_path: Path, semboller: str) -> Path:
    """`[nm, elf]` çağrısında nm = python, elf = sembolleri basan küçük betik (gerçek arm aracı gerekmez)."""
    p = tmp_path / "sahte_elf.py"
    p.write_text(f"print({semboller!r})\n", encoding="utf-8")
    return p


def test_KRITIK_215_nm_YOKKEN_printf_float_kapisi_TEMIZ_DEMEZ(tmp_path, capsys):
    fd = betik_modulu("firmware_derle")
    rc = fd.printf_float_kapisi(
        _sahte_elf(tmp_path, "00000000 T _printf_float"), str(tmp_path / "yok" / "arm-none-eabi-nm.exe")
    )
    assert rc == 1, "nm YOKKEN printf-float kapısı 0 döndü — ölçülmemiş ürün 'TEMİZ' sayılıyor"
    assert "KOSULAMADI" in capsys.readouterr().out


def test_KARSIT_215_kapi_sembolu_GORUNCE_0_GORMEYINCE_1(tmp_path):
    fd = betik_modulu("firmware_derle")
    assert fd.printf_float_kapisi(_sahte_elf(tmp_path, "00000000 T _printf_float"), sys.executable) == 0
    assert fd.printf_float_kapisi(_sahte_elf(tmp_path, "00000000 T main"), sys.executable) == 1


def _sahte_derleme(fd, tmp_path: Path, monkeypatch, *, baglama_dosyalari: bool) -> list[list[str]]:
    """`derle_stm` gerçek derleyici OLMADAN: geçici proje (1 kaynak), sahte gcc yolu, `subprocess.run` YALNIZ betik
    modülünde kayıtçı (her çağrı rc 0). Gerçek arm aracı / CubeIDE / dosya sistemi dışına yazım YOK."""
    import types

    proje = tmp_path / "stm32_pemf"
    (proje / "Core" / "Src").mkdir(parents=True)
    (proje / "Core" / "Src" / "x.c").write_text("int x;\n", encoding="utf-8")
    if baglama_dosyalari:
        (proje / "Core" / "Startup").mkdir(parents=True)
        (proje / "Core" / "Startup" / "startup_stm32f429zitx.s").write_text("\n", encoding="utf-8")
        (proje / "STM32F429ZITX_FLASH.ld").write_text("\n", encoding="utf-8")
    cagrilar: list[list[str]] = []

    def run(argv, **_k):
        cagrilar.append([str(a) for a in argv])
        return fd.subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(
        fd, "subprocess", types.SimpleNamespace(run=run, CompletedProcess=fd.subprocess.CompletedProcess)
    )
    monkeypatch.setattr(fd, "STM_PROJE", proje)
    monkeypatch.setattr(fd, "_stm_gcc", lambda: tmp_path / "sahte" / "arm-none-eabi-gcc.exe")
    monkeypatch.setattr(fd, "shutil", types.SimpleNamespace(which=lambda _ad: None))
    return cagrilar


def test_KRITIK_215_baglama_YAPILAMAYINCA_derleme_TEMIZ_DEMEZ(tmp_path, monkeypatch, capsys):
    """Startup/linker betiği yokken eskiden "NOT … bağlama ATLANDI" + rc 0 → `main()` "SONUC: TEMIZ" basıyordu:
    bağlanmamış, printf-float kapısı HİÇ koşmamış bir ürün temiz sayılıyordu (D1.29, plan `:239-241`)."""
    fd = betik_modulu("firmware_derle")
    cagrilar = _sahte_derleme(fd, tmp_path, monkeypatch, baglama_dosyalari=False)
    rc = fd.derle_stm()
    assert len(cagrilar) == 1 and "-c" in cagrilar[0], f"ön koşul: yalnız tek derleme çağrısı: {cagrilar}"
    assert rc == 1, "bağlama YAPILAMADI ama derle_stm 0 döndü → 'SONUC: TEMIZ' (ölçülmemiş ürün)"
    assert "YAPILAMADI" in capsys.readouterr().out


def test_KARSIT_215_baglama_dosyalari_VARKEN_baglanir_ve_nm_yoksa_yine_1(tmp_path, monkeypatch):
    fd = betik_modulu("firmware_derle")
    cagrilar = _sahte_derleme(fd, tmp_path, monkeypatch, baglama_dosyalari=True)
    assert fd.derle_stm() == 1, "nm (sahte gcc yanında) YOK → printf-float kapısı koşamaz → 1"
    assert any("-T" in c for c in cagrilar), f"bağlama çağrısı yapılmadı: {cagrilar}"


# ── (219) stm_firmware_kimligi ──────────────────────────────────────────────


def _banner(kanal: int) -> str:
    # TD1 · Y68: kart paket boyunu BEYAN eder (pkt=); `uni=` basıp pkt= basmayan banner 120 / 121'i ayırt edemez (None).
    return f"-> STM_READY: DDS v2.3 ({kanal}-ch KARMA uni=0x60 + HW_SYNC@PB1) proto=3 pkt={16 * kanal + 9}"


@pytest.mark.parametrize("kanal", [5, 6, 7, 8])
def test_KRITIK_219_betigin_karari_BACKEND_uyum_kapisiyla_AYNI(kanal, monkeypatch, capsys):
    from utils.stm32_kimlik import banner_ayristir, uyum_denetle
    from utils.stm32_transport import STM_PAKET_BOBIN_SAYISI

    beklenen, _ = uyum_denetle(banner_ayristir(_banner(kanal)), STM_PAKET_BOBIN_SAYISI)
    assert beklenen is not None, "ön koşul: banner backend'ce okunmalı"
    sk = betik_modulu("stm_firmware_kimligi")
    monkeypatch.setattr(sk, "_portlari_bul", lambda istenen: ["COM_TEST"])
    monkeypatch.setattr(sk, "_dinle", lambda port, sure: (kanal, [_banner(kanal)]))
    monkeypatch.setattr(sys, "argv", ["stm_firmware_kimligi.py", "--sure", "0"])
    rc = sk.main()
    assert (rc == 0) is beklenen, (
        f"{kanal} kanallı kart: betik rc={rc} ({'uyumlu' if rc == 0 else 'uyumsuz'}) ama backend uyum kapısı "
        f"{'UYUMLU' if beklenen else 'UYUMSUZ (seans 409)'} diyor — operatöre yanlış teşhis"
    )


# ── (220) stm_workspace_kopyala ─────────────────────────────────────────────


def test_KRITIK_220_protokol_isareti_YORUMDAKI_kopyayla_GECMEZ(tmp_path):
    import re

    kaynak = MAIN_C.read_text(encoding="utf-8")
    tanim = re.search(r"static void Coil_KipUygula\(uint8_t istenen\) \{.*?\n\}\n", kaynak, re.S)
    cagri = "        Coil_KipUygula(pkt_local.unipolar_maskesi);\n"
    assert tanim and kaynak.count(cagri) == 1, "aparat: Coil_KipUygula tanımı/çağrısı bulunamadı"
    mutant = kaynak.replace(tanim.group(0), "").replace(cagri, "")
    assert "Coil_KipUygula" in mutant, "senaryo: yalnız yorumdaki kopya kalmalı"
    (tmp_path / "main.c").write_text(mutant, encoding="utf-8")
    kopya = betik_modulu("stm_workspace_kopyala")
    eksik = kopya._protokol_eksikleri(tmp_path / "main.c")
    assert any("kip uygulama" in e for e in eksik), f"kip uygulaması yalnız YORUMDA kalan kaynak 'tam' sayıldı: {eksik}"


def test_KARSIT_220_gercek_main_c_TAM_sayilir():
    kopya = betik_modulu("stm_workspace_kopyala")
    assert kopya._protokol_eksikleri(MAIN_C) == []
    assert kopya._bobin_sayisi(MAIN_C) == 7


# ── 1-B bağımsız inceleme (i3): araç zinciri YOKKEN açıkça istenen hedef TEMİZ sayılmaz ─────────────────


def test_KRITIK_215_stm_ACIKCA_istenip_derleyici_YOKKEN_1_ve_TEMIZ_DEMEZ(monkeypatch, capsys):
    fd = betik_modulu("firmware_derle")
    monkeypatch.setattr(fd, "_stm_gcc", lambda: None)
    monkeypatch.setattr(fd, "_ATLANAN", [])
    monkeypatch.setattr(sys, "argv", ["firmware_derle.py", "--stm"])
    assert fd.main() == 1, "`--stm` istendi, derleyici yok → 0 döndü (stm_yak'a ölçülmemiş ikili gider)"
    cikti = capsys.readouterr().out
    assert "SONUC: TEMIZ" not in cikti.replace("SONUC: TEMIZ DEGIL", ""), cikti[-400:]


def test_KARSIT_215_hepsi_kipinde_atlanan_RC0_ama_SONUC_TEMIZ_DEGIL(monkeypatch, capsys):
    fd = betik_modulu("firmware_derle")
    monkeypatch.setattr(fd, "_stm_gcc", lambda: None)
    monkeypatch.setattr(fd, "_s3_cli", lambda: None)
    monkeypatch.setattr(fd, "_ATLANAN", [])
    monkeypatch.setattr(sys, "argv", ["firmware_derle.py"])
    assert fd.main() == 0
    cikti = capsys.readouterr().out
    assert "SONUC: TEMIZ DEGIL" in cikti and "STM32" in cikti.split("SONUC:")[-1], cikti[-400:]
