# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.16 (B-10.211) KAPISI — `stm_workspace_kopyala` aynı gün yeniden koşunca hedefteki workspace'i SİLMEZ.

ARIZA (DENETIM-10 B-10.211): hedef tarihli klasör varsa `shutil.rmtree(hedef)` onaysız ve yedeksiz
siliyordu → sahibin o gün CubeIDE'de yaptığı `main.c` düzenlemesi ve `.metadata` GERİ DÖNÜŞSÜZ gider.

KAPI: tmp hedef kökünde bugünkü tarihli klasöre betiğin ÜRETMEDİĞİ `sahip_notu.txt` ve elle
düzenlenmiş bir `main.c` konur; betiğin GERÇEK `main()`i aynı `--hedef` ile çağrılır (depodaki
`firmware/stm32_pemf` tmp'ye kopyalanır — gerçek hedef/masaüstü KULLANILMAZ). İddia: iki dosya da
SİLİNMEMİŞ — yerinde (betik durdu, ≠0) ya da bir yedek klasörde. Seçilen tasarım (yedeğe taşı, taze
kopya üret) ve taşıma başarısız olursa silmeye DÜŞMEME ayrıca pinlenir. Karşıt-kanıt: temiz kökte
betik kopyayı gerçekten üretir (kapı betiği işlemez hâle getirerek yeşil olamaz).
D0Ö.16 ek (bağımsız inceleme tur 4): HER testte `rmtree` casusu; sabit saatle iki ardışık koşum +
önceden var olan yedek + sahibin `.metadata`sı bayt bayt korunur (sabit ad + eskiyi silme
"rotasyonu" KIRMIZI); kaynak proje yoksa hedefe DOKUNULMAZ; yedeğin flaşlanmaması uyarısı ve
başarısız taşımada "HICBIR SEY SILINMEDI" iletisi; izli proje yoksa kapı ATLAMAZ, KIRMIZI olur.
MUTASYON: koruma dalını kaldırıp koşulsuz `shutil.rmtree(hedef)`e dönmek → KIRMIZI.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

KOK = Path(__file__).resolve().parents[1]
NOT_METNI = "sahibin elle yazdigi not"
DUZENLEME = "/* sahibin CubeIDE duzenlemesi */"


def _betik():
    spec = importlib.util.spec_from_file_location(
        "stm_workspace_kopyala_kapi", KOK / "scripts" / "stm_workspace_kopyala.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def betik():
    m = _betik()
    # ⚠️ ATLAMA DEĞİL (Ö.7): proje dizinleri betiğin KENDİ listesinden; izli dizin yoksa bu bir
    # ad değişikliği/taşıma regresyonudur — kapı sessizce "s" olmamalı.
    eksik = [p for p in m.PROJELER if not (KOK / "firmware" / p).is_dir()]
    if eksik:
        pytest.fail(f"betiğin kopyalayacağı proje depoda yok: {eksik}")
    return m


@pytest.fixture()
def silinenler(monkeypatch, tmp_path) -> list[str]:
    """HER testte SİLME casusu: betik hiçbir yolda silmemeli (gerçek çağrı yine koşar).

    D0Ö.16 ek-2 (tur 5): yalnız `shutil.rmtree` izleniyordu — bayat `.elf`i `os.remove`/`Path.unlink` ile
    silen bir "budama" kapıdan kaçardı. Artık rmtree + os.remove/unlink/rmdir + Path.unlink/rmdir izlenir.
    Kayıt yalnız `tmp_path` altını tutar (başka thread'lerin geçici dosya temizliği sahte KIRMIZI üretmesin).
    """
    kayit: list[str] = []
    kok = str(tmp_path)

    def _casus(gercek):
        def _kaydet(yol, *a, **k):
            if str(yol).startswith(kok):
                kayit.append(str(yol))
            return gercek(yol, *a, **k)

        return _kaydet

    monkeypatch.setattr(shutil, "rmtree", _casus(shutil.rmtree))
    for ad in ("remove", "unlink", "rmdir"):
        monkeypatch.setattr(os, ad, _casus(getattr(os, ad)))
    for ad in ("unlink", "rmdir"):
        monkeypatch.setattr(Path, ad, _casus(getattr(Path, ad)))
    return kayit


def _sabit_saat(betik, monkeypatch, saat: tuple[int, int, int] = (12, 0, 0)) -> str:
    """Yedek adındaki `HHMMSS` damgasını sabitle → aynı saniyede çakışma ve `_2`, `_3` yolu sınanır."""
    gercek = _dt.datetime(2026, 9, 30, *saat)
    monkeypatch.setattr(betik, "_dt", SimpleNamespace(date=_dt.date, datetime=SimpleNamespace(now=lambda: gercek)))
    return gercek.strftime("%H%M%S")


def _hedef(kok: Path) -> Path:
    return kok / f"PEMF_STM32_workspace_{_dt.date.today().isoformat()}"


def _sahip_calismasi(kok: Path) -> Path:
    """Bugünkü hedefte betiğin ÜRETMEDİĞİ iki dosya: bir not ve CubeIDE'de düzenlenmiş main.c."""
    hedef = _hedef(kok)
    (hedef / "stm32_pemf" / "Core" / "Src").mkdir(parents=True)
    (hedef / "sahip_notu.txt").write_text(NOT_METNI, encoding="utf-8")
    (hedef / "stm32_pemf" / "Core" / "Src" / "main.c").write_text(DUZENLEME, encoding="utf-8")
    return hedef


def _kos(betik, kok: Path, monkeypatch) -> int:
    monkeypatch.setattr(sys, "argv", ["stm_workspace_kopyala.py", "--hedef", str(kok)])
    return betik.main()


def _notlar(kok: Path) -> list[Path]:
    return [p for p in kok.rglob("sahip_notu.txt") if p.read_text(encoding="utf-8") == NOT_METNI]


def _duzenlemeler(kok: Path) -> list[Path]:
    return [p for p in kok.rglob("main.c") if p.read_text(encoding="utf-8", errors="replace") == DUZENLEME]


def test_KRITIK_ayni_gun_yeniden_kosum_SAHIBIN_dosyalarini_SILMEZ(betik, tmp_path, monkeypatch, silinenler):
    _sahip_calismasi(tmp_path)
    rc = _kos(betik, tmp_path, monkeypatch)
    assert _notlar(tmp_path), f"betik hedefteki SAHİBİN dosyasını SİLDİ (rc={rc}) — onaysız ve yedeksiz (B-10.211)"
    assert _duzenlemeler(tmp_path), f"sahibin main.c düzenlemesi KAYBOLDU (rc={rc}) (B-10.211)"
    assert not silinenler, f"betik SİLME çağırdı: {silinenler}"


def test_onceki_kopya_YEDEGE_tasinir_ve_TAZE_kopya_uretilir(betik, tmp_path, monkeypatch, capsys, silinenler):
    hedef = _sahip_calismasi(tmp_path)
    assert _kos(betik, tmp_path, monkeypatch) == 0
    yedekler = sorted(p for p in tmp_path.iterdir() if p.name.startswith(f"{hedef.name}_yedek_"))
    assert len(yedekler) == 1, f"önceki kopya tek bir yedek klasöre taşınmadı: {[p.name for p in tmp_path.iterdir()]}"
    assert (yedekler[0] / "sahip_notu.txt").read_text(encoding="utf-8") == NOT_METNI
    assert (yedekler[0] / "stm32_pemf" / "Core" / "Src" / "main.c").read_text(encoding="utf-8") == DUZENLEME
    taze = (hedef / "stm32_pemf" / "Core" / "Src" / "main.c").read_text(encoding="utf-8", errors="replace")
    assert "NUM_COILS" in taze and taze != DUZENLEME, "taze kopya depo kaynağından üretilmedi"
    assert not (hedef / "sahip_notu.txt").exists(), "taze kopyaya betiğin üretmediği dosya karıştı"
    cikti = capsys.readouterr().out
    assert str(yedekler[0]) in cikti, "yedeğin yeri kullanıcıya söylenmedi"
    assert "FLASHLAMAYIN" in cikti, "yedeğin (bayat .elf taşıyabilir) flaşlanmaması uyarısı basılmadı"
    assert not silinenler, f"betik SİLME çağırdı: {silinenler}"


def test_KRITIK_ikinci_ve_ucuncu_kosum_ONCEKI_yedekleri_bayt_bayt_KORUR(betik, tmp_path, monkeypatch, silinenler):
    """Aynı saniyede çakışan yedek adı + önceden var olan yedek + sahibin `.metadata`sı: hiçbiri
    silinmez/budanmaz, yeni yedekler `_2`, `_3` alır (sabit ad + eskiyi silme 'rotasyonu' YASAK).

    D0Ö.16 ek-2 (tur 5): en fazla 3 yedek kuruluyordu — "son N yedeği tut" (N≥3) rotasyonu ve yedekteki
    bayat `Debug/*.elf`i budayan bir değişiklik YEŞİL kalırdı. Artık 20 eski yedek + sahibin `Debug/PEMF.elf`i.
    """
    hedef = _sahip_calismasi(tmp_path)
    (hedef / ".metadata").mkdir()
    (hedef / ".metadata" / "ayar.prefs").write_text("sahip-ayari", encoding="utf-8")
    (hedef / "stm32_pemf" / "Debug").mkdir()
    (hedef / "stm32_pemf" / "Debug" / "PEMF.elf").write_bytes(b"\x7fELF-sahip-derlemesi")
    eskiler = {}
    for i in range(1, 21):
        eski = tmp_path / f"{hedef.name}_yedek_0000{i:02d}"
        (eski / "stm32_pemf" / "Debug").mkdir(parents=True)
        (eski / "stm32_pemf" / "Debug" / "PEMF.elf").write_bytes(f"eski-{i}".encode())
        eskiler[eski] = f"eski-{i}".encode()
    damga = _sabit_saat(betik, monkeypatch)
    dunku = tmp_path / f"{hedef.name}_yedek_{damga}"
    (dunku / ".metadata").mkdir(parents=True)
    (dunku / ".metadata" / "ayar.prefs").write_text("onceki-yedek", encoding="utf-8")

    assert _kos(betik, tmp_path, monkeypatch) == 0
    assert _kos(betik, tmp_path, monkeypatch) == 0
    yedekler = sorted(p.name for p in tmp_path.iterdir() if p.name.startswith(f"{hedef.name}_yedek_{damga}"))
    assert yedekler == [dunku.name, f"{dunku.name}_2", f"{dunku.name}_3"], f"yedek zinciri beklenmedik: {yedekler}"
    assert (dunku / ".metadata" / "ayar.prefs").read_text(encoding="utf-8") == "onceki-yedek"
    ikinci = tmp_path / f"{dunku.name}_2"
    assert (ikinci / ".metadata" / "ayar.prefs").read_text(encoding="utf-8") == "sahip-ayari", "sahibin .metadata'sı"
    assert (ikinci / "sahip_notu.txt").read_text(encoding="utf-8") == NOT_METNI
    assert (ikinci / "stm32_pemf" / "Debug" / "PEMF.elf").read_bytes() == b"\x7fELF-sahip-derlemesi", "yedekte .elf"
    kayip = [
        e.name for e, icerik in eskiler.items() if (e / "stm32_pemf" / "Debug" / "PEMF.elf").read_bytes() != icerik
    ]
    assert not kayip, f"ESKİ yedekler budandı/değişti (rotasyon YASAK): {kayip}"
    assert not silinenler, f"betik SİLME çağırdı: {silinenler}"


def test_KRITIK_kaynak_proje_YOKSA_hedefe_DOKUNULMAZ(betik, tmp_path, monkeypatch, capsys, silinenler):
    """Betik depo dışına kopyalanıp koşulursa: sahibin workspace'i yedeğe TAŞINMAMALI (boş hedef kalmaz)."""
    hedef = _sahip_calismasi(tmp_path)
    monkeypatch.setattr(betik, "PROJELER", ["d0o16_olmayan_proje"])
    rc = _kos(betik, tmp_path, monkeypatch)
    assert rc != 0
    assert (hedef / "sahip_notu.txt").read_text(encoding="utf-8") == NOT_METNI, "sahibin klasörü yerinden oynatıldı"
    assert not [p for p in tmp_path.iterdir() if "_yedek_" in p.name], "kaynak yokken hedef yedeğe taşındı"
    assert "DOKUNULMADI" in capsys.readouterr().err
    assert not silinenler, f"betik SİLME çağırdı: {silinenler}"


def test_KRITIK_tasima_basarisizsa_HICBIR_SEY_SILINMEZ_ve_durur(betik, tmp_path, monkeypatch, capsys, silinenler):
    """CubeIDE klasörü açık tutarken (Windows `PermissionError`) betik silmeye DÜŞMEMELİ."""
    hedef = _sahip_calismasi(tmp_path)

    def _tasinamaz(gercek):
        def _yama(self, *a, **k):
            if Path(self) != hedef:  # yalnız HEDEFİN taşınması başarısız (başka çağrılar GERÇEK işlevine gider)
                return gercek(self, *a, **k)
            raise PermissionError(13, "d0o16: klasor baska bir surecte acik", str(self))

        return _yama

    # D0Ö.16 ek-2 (tur 5): `replace` yaması hedef dışındaki çağrıları `rename`e yönlendiriyordu (anlam farkı).
    monkeypatch.setattr(Path, "rename", _tasinamaz(Path.rename))
    monkeypatch.setattr(Path, "replace", _tasinamaz(Path.replace))
    rc = _kos(betik, tmp_path, monkeypatch)
    assert rc != 0, "hedef yedeğe taşınamadığı hâlde betik devam etti (0 döndü)"
    assert not silinenler, f"betik SİLMEYE düştü: {silinenler}"
    assert (hedef / "sahip_notu.txt").read_text(encoding="utf-8") == NOT_METNI
    assert (hedef / "stm32_pemf" / "Core" / "Src" / "main.c").read_text(encoding="utf-8") == DUZENLEME
    err = capsys.readouterr().err
    assert "HICBIR SEY SILINMEDI" in err, "kullanıcıya 'hiçbir şey silinmedi' denmedi"
    assert "--hedef" in err, "başka bir kök (--hedef) önerisi söylenmedi"


def test_KRITIK_BAYAT_kaynakta_hedefe_DOKUNULMAZ(betik, tmp_path, monkeypatch, capsys, silinenler):
    """D0Ö.16 ek-2 (tur 5): kaynak VAR ama BAYAT (ör. eski dal: NUM_COILS 5) — içerik doğrulaması eskiden
    taşımadan SONRAYDI: sahibin workspace'i yedeğe taşınır, CubeIDE'nin açtığı yolda bayat kopya kalırdı
    (rc 1). Artık kaynak içeriği hedefe DOKUNMADAN denetlenir."""
    hedef = _sahip_calismasi(tmp_path)
    monkeypatch.setattr(betik, "_bobin_sayisi", lambda main_c: 5)
    rc = _kos(betik, tmp_path, monkeypatch)
    assert rc != 0
    assert (hedef / "sahip_notu.txt").read_text(encoding="utf-8") == NOT_METNI, "sahibin klasörü yerinden oynatıldı"
    assert (hedef / "stm32_pemf" / "Core" / "Src" / "main.c").read_text(encoding="utf-8") == DUZENLEME
    assert not [p for p in tmp_path.iterdir() if "_yedek_" in p.name], "bayat kaynakta hedef yedeğe TAŞINDI"
    assert "DOKUNULMADI" in capsys.readouterr().err
    assert not silinenler, f"betik SİLME çağırdı: {silinenler}"


def test_KARSIT_KANIT_temiz_kokte_kopya_URETILIR(betik, tmp_path, monkeypatch, silinenler):
    assert _kos(betik, tmp_path, monkeypatch) == 0
    main_c = _hedef(tmp_path) / "stm32_pemf" / "Core" / "Src" / "main.c"
    assert main_c.is_file() and "NUM_COILS" in main_c.read_text(encoding="utf-8", errors="replace")
    assert not [p for p in tmp_path.iterdir() if "_yedek_" in p.name], "temiz kökte yedek klasörü açılmamalı"
    assert not silinenler, f"betik SİLME çağırdı: {silinenler}"
