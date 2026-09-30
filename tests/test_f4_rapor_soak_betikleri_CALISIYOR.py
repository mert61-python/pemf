# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D0Ö.21 (B-9.27) — XAI toplu rapor ve soak betikleri GERÇEKTEN çalışıyor ve hataları YUTMUYOR.

Ortak import-çözüm kapısı: `test_betikler_ACILIYOR::test_KRITIK_fonksiyon_ici_ilk_taraf_importlari_COZULUYOR`.
Bu dosya DAVRANIŞI ölçer:

  · `xai_batch_rapor.py --modul ses` ALT SÜREÇTE sentetik SESSİZ 1 sn WAV ile: sonuç satırı sessizlik
    kapısından gelir (import hatasından DEĞİL) ve tüm kayıtlar HATA → rc≠0. F4'ten beri ses kolu her
    kayıtta `ModuleNotFoundError` verdi, kayıt kayıt yutuldu ve araç exit 0 ile bitti.
  · Kısmi hata 0 kalır (zarif düşüş); import hatası kayıt kayıt yutulmaz, akışı ≠0 ile durdurur.
  · `--pdf` gerçek veri köküne DOKUNMADAN reddedilir (İG-9.50): import onarılınca PDF üreteci açılışta
    veri kökünde tedavi DB'sini açar (göç + yedek); sır yöneticisi anahtarı gerçek kökten/keyring'den
    okur — geçici `app_data_dir` bunu YALITMAZ.
  · `soak_http_ws._veri_koku()` ALT SÜREÇTE ürünün kullanıcı kökündeki (Windows `%APPDATA%\\PEMF_GUI`,
    Linux `~/.local/share/PEMF_GUI`) sahte .db ile o kökü seçer; iki kökte de .db varken makine kökü
    kazanır (eskiden `utils.path_utils` sessizce düşüyor, soak yanlış kökün DB büyümesini ölçüyordu).

⚠️ Sessiz WAV sessizlik kapısında durur → model YÜKLENMEZ, ağ gerekmez (bkz. betik_alt_sureci).
"""

from __future__ import annotations

import base64
import csv
import sys
import wave
from pathlib import Path

import pytest
from betik_alt_sureci import BETIKLER, betik_modulu, kostur, yalitik_ortam


def _sessiz_wav(yol: Path, sn: float = 1.0, sr: int = 22050) -> Path:
    yol.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(yol), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * int(sr * sn))
    return yol


def test_KRITIK_xai_ses_kolu_ALT_SURECTE_calisir_ve_tum_HATA_cikis_SIFIR_DEGIL(tmp_path):
    env = yalitik_ortam(tmp_path / "ortam")
    wav = _sessiz_wav(tmp_path / "girdi" / "sessiz.wav")
    cikti = tmp_path / "cikti"
    r = kostur(
        [str(BETIKLER / "xai_batch_rapor.py"), "--modul", "ses", "--girdi", str(wav), "--cikti", str(cikti)],
        tmp_path,
        env,
    )
    ozet_yolu = cikti / "summary.csv"
    assert ozet_yolu.is_file(), f"sonuç satırı YOK (rc={r.returncode}):\n{(r.stdout + r.stderr)[-900:]}"
    with open(ozet_yolu, encoding="utf-8-sig") as f:
        ozet = list(csv.DictReader(f))
    assert len(ozet) == 1, ozet
    hata = ozet[0].get("hata", "")
    assert "No module named" not in hata, f"ses kolu import'ta ÖLÜ (B-9.27): {hata}"
    assert "sessizlik" in hata, f"sessiz kayıt sessizlik kapısında durmalıydı: {hata!r}"
    # ⚠️ D0Ö.21 ek (tur 4): yalnız "≠0" pinlemek yetmez — summary'den SONRAKİ herhangi bir çökme de 1
    # verir; o varken tüm-HATA kuralı silinse kapı yeşil kalırdı. Kuralın KENDİSİ ve tam koşu pinlenir.
    assert r.returncode == 1, f"tüm kayıtlar HATA iken çıkış 1 değil (rc={r.returncode}):\n{r.stderr[-600:]}"
    assert "TUM kayitlar hatali" in r.stderr, f"çıkış kodu tüm-HATA kuralından gelmiyor:\n{r.stderr[-600:]}"
    assert (cikti / "index.html").is_file(), "koşu summary'den sonra düştü (index.html yok)"


_KUCUK_JPG = base64.b64encode(b"\xff\xd8\xff\xd9").decode("ascii")


def _xai_main(m, monkeypatch, tmp_path, fn, n_dosya: int = 1, *ek) -> int:
    for i in range(n_dosya):
        _sessiz_wav(tmp_path / "girdi" / f"k{i}.wav", sn=0.1)
    monkeypatch.setattr(m, "_gorsel_explain_fn", lambda modul, yontem: fn)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "xai_batch_rapor.py",
            "--modul",
            "ses",
            "--girdi",
            str(tmp_path / "girdi"),
            "--cikti",
            str(tmp_path / "c"),
            *ek,
        ],
    )
    sonuc = m.main()
    return 0 if sonuc is None else int(sonuc)  # `sys.exit(None)` gibi: None → çıkış 0


def test_KARSIT_KANIT_xai_basarili_kayit_cikis_SIFIR(tmp_path, monkeypatch):
    m = betik_modulu("xai_batch_rapor")
    assert _xai_main(m, monkeypatch, tmp_path, lambda p: {"xai_image_base64": _KUCUK_JPG, "method": "kapi"}) == 0


def test_xai_KISMI_hata_zarif_dusus_cikis_SIFIR(tmp_path, monkeypatch):
    m = betik_modulu("xai_batch_rapor")
    sayac = {"n": 0}

    def fn(p):
        sayac["n"] += 1
        if sayac["n"] == 1:
            raise RuntimeError("tek dosya bozuk")
        return {"xai_image_base64": _KUCUK_JPG, "method": "kapi"}

    assert _xai_main(m, monkeypatch, tmp_path, fn, 2) == 0


def test_KRITIK_xai_IMPORT_hatasi_kayit_kayit_YUTULMAZ(tmp_path, monkeypatch):
    m = betik_modulu("xai_batch_rapor")
    cagri = {"n": 0}

    def fn(p):
        cagri["n"] += 1
        raise ModuleNotFoundError("No module named 'utils'")

    with pytest.raises(SystemExit) as e:
        _xai_main(m, monkeypatch, tmp_path, fn, 3)
    assert e.value.code not in (0, None), "import hatası akışı durdurmadı"
    assert cagri["n"] == 1, f"import hatasından sonra {cagri['n'] - 1} kayıt daha denendi (her biri aynı hatayı verir)"


def test_KRITIK_xai_pdf_VERI_KOKUNE_dokunmadan_REDDEDILIR(tmp_path, monkeypatch):
    m = betik_modulu("xai_batch_rapor")
    import utils.pdf_report_generator as pdfmod

    def _yasak(*a, **k):
        raise AssertionError("get_pdf_generator ÇAĞRILDI — veri kökünde tedavi DB'si açılır (İG-9.50)")

    monkeypatch.setattr(pdfmod, "get_pdf_generator", _yasak)
    with pytest.raises(SystemExit) as e:
        _xai_main(m, monkeypatch, tmp_path, lambda p: {"xai_image_base64": _KUCUK_JPG, "method": "kapi"}, 1, "--pdf")
    assert "IG-9.50" in str(e.value.code) or "İG-9.50" in str(e.value.code), e.value.code
    assert not (tmp_path / "c" / "summary.csv").exists(), "reddedilen koşu yine de işledi"


def test_KRITIK_soak_veri_koku_path_utils_YUKLENEMEZSE_SESSIZ_devam_etmez(monkeypatch):
    m = betik_modulu("soak_http_ws")
    monkeypatch.setitem(sys.modules, "utils.path_utils", None)  # import → ImportError
    with pytest.raises(SystemExit) as e:
        m._veri_koku()
    assert "path_utils" in str(e.value.code), f"hata iletisi ne olduğunu söylemiyor: {e.value.code!r}"


#: Alt süreç: betiği yükler, ÜRÜNÜN kullanıcı kökünü (`get_app_data_directory()`, PEMF_DATA_DIR yok)
#: SORAR, oraya sahte .db koyar, sonra `_veri_koku()`nu basar.
#: ⚠️ D0Ö.21 ek (tur 4, ORTA): beklenen kök eskiden `APPDATA/PEMF_GUI` diye SABİTTİ — Linux'ta ürün
#: `~/.local/share` (macOS `~/Library/Application Support`) kullanır; kapı ubuntu CI'da her koşuda
#: kırmızı olurdu. Kök artık ürünün kendisinden alınır → platformdan bağımsız.
_SOAK_KOK_KODU = (
    "import importlib.util, sys\n"
    "from pathlib import Path\n"
    "s = importlib.util.spec_from_file_location('soak_kapi', sys.argv[1])\n"
    "m = importlib.util.module_from_spec(s)\n"
    "s.loader.exec_module(m)\n"
    "from utils.path_utils import get_app_data_directory\n"
    "k = get_app_data_directory()\n"
    # D0Ö.21 ek-2 (tur 5): sahte kök denetimi YAZIMDAN ÖNCE — ürün yol çözümü ortamı okumayan bir yönteme
    # geçerse sahte .db GERÇEK kullanıcı kökünde yazılıp ancak sonra kırmızıya düşülürdü.
    "if not k.resolve().is_relative_to(Path(sys.argv[2]).resolve()):\n"
    "    raise SystemExit('GERCEK KOK: ' + str(k))\n"
    "(k / 'sahte.db').write_bytes(b'sahte')\n"
    "print('KULLANICI=' + str(k))\n"
    "print('VERI_KOKU=' + str(m._veri_koku()))\n"
)


def _soak_veri_koku_alt_surecte(
    tmp_path: Path, programdata_db: bool, makine_klasoru: bool = False
) -> tuple[Path, Path, Path]:
    """(kullanıcı kökü, makine kökü, seçilen kök) — hepsi sahte ortam altında. `makine_klasoru`: makine kökü
    VAR ama içinde .db YOK."""
    env = yalitik_ortam(tmp_path / "ortam")
    makine = Path(env["PROGRAMDATA"]) / "PEMF_System" / "PEMF_GUI"
    if programdata_db or makine_klasoru:
        makine.mkdir(parents=True)
    if programdata_db:
        (makine / "sahte.db").write_bytes(b"sahte")
    r = kostur(["-c", _SOAK_KOK_KODU, str(BETIKLER / "soak_http_ws.py"), str(tmp_path / "ortam")], tmp_path, env, 120)
    degerler = dict(s.split("=", 1) for s in r.stdout.splitlines() if s.startswith(("KULLANICI=", "VERI_KOKU=")))
    assert set(degerler) == {"KULLANICI", "VERI_KOKU"}, f"alt süreç düştü (rc={r.returncode}):\n{r.stderr[-900:]}"
    kullanici = Path(degerler["KULLANICI"])
    assert kullanici.resolve().is_relative_to((tmp_path / "ortam").resolve()), f"GERÇEK kullanıcı kökü: {kullanici}"
    return kullanici, makine, Path(degerler["VERI_KOKU"])


def test_KRITIK_soak_veri_koku_ALT_SURECTE_APPDATA_kokunu_secer(tmp_path):
    """Yalnız kullanıcı kökünde .db varken onu seçer (eskiden path_utils sessizce düşüyordu, B-9.27)."""
    kullanici, _makine, secilen = _soak_veri_koku_alt_surecte(tmp_path, programdata_db=False)
    assert secilen == kullanici, f"soak veri kökü kullanıcı kökünü seçmedi: {secilen} != {kullanici}"


def test_KRITIK_soak_veri_koku_DBsiz_makine_kokunu_ATLAR(tmp_path):
    """D0Ö.21 ek-2 (tur 5): ölçüt '.db VAR mı', 'klasör var mı' değil — makine kökü VAR ama boşken (ör.
    launcher'sız dev makinesi) kullanıcı kökü seçilmeli. '.db' koşulunu düşüren mutant iki kolda da yeşildi."""
    kullanici, makine, secilen = _soak_veri_koku_alt_surecte(tmp_path, programdata_db=False, makine_klasoru=True)
    assert makine.is_dir() and not any(makine.glob("*.db")), "kurulum: makine kökü var ve boş olmalı"
    assert secilen == kullanici, f"DB'siz makine kökü seçildi (soak boş kökün büyümesini ölçer): {secilen}"


def test_KARSIT_KANIT_soak_veri_koku_MAKINE_kokunu_ONCE_secer(tmp_path):
    """İki kökte de .db varken launcher'ın makine kökü (`PEMF_DATA_DIR=%PROGRAMDATA%\\PEMF_System`) kazanır."""
    _kullanici, makine, secilen = _soak_veri_koku_alt_surecte(tmp_path, programdata_db=True)
    assert secilen == makine, f"makine kökü öncelikli değil: {secilen} != {makine}"
