# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.75 (B-11.5) — kurtarma yönergesinin HER kopyası sahada ÇALIŞAN `PEMF_Backend.exe --kurtarma …` biçiminde.

Kusur: `KURTARMA-KODU.txt` (ürün yazar), yedeklerin yanındaki `OKU-KURTARMA.txt` (ürün yazar), aracın kendi uyarıları ve RUNBOOK
`python tools/kurtarma.py …` diyordu. Sahada Python YOK; tek çalıştırılabilir launcher'ın kurduğu `PEMF_Backend.exe`dir ve kurtarma
onun `--kurtarma` alt komutudur → anakartı ölen klinik yönergeyi izleyince "Python bulunamadı" alır, yedeklerin açılamadığını sanırdı
(metin 1.9.50'de de sahada). Düzeltme: komut TEK kaynaktan (`utils.backup_recovery.kurtarma_komutu`).

Kapı: üreticiler GERÇEK çağrılır (kod dosyası metni, makine dışı yedeğin gerçek `_copy_offsite` yazıcısı, aracın `main`i), RUNBOOK
okunur; her komut ayrıştırılır → ilk sözcük `PEMF_Backend.exe`, kalan GERÇEK `backend_service._kurtarma_mi`den geçer. KURTARMA-KODU.txt
komutu ayrıca donmuş EXE benzetiminde (D2.35 aparatı) GERÇEK araçla koşar — yönerge, içe aktarmada ölen bir yola işaret etmesin.
"""

from __future__ import annotations

import re
import shlex
import threading
from pathlib import Path

import pytest
from donmus_kurtarma_aparati import DEPO, donmus_kurtarma_kos

_KOMUT = re.compile(r"PEMF_Backend\.exe\"?\s+--kurtarma|kurtarma\.py")


def _komutlar(metin: str) -> list[str]:
    """Metindeki kurtarma KOMUTLARI: ters tırnaklı parçalar ya da (tırnaksız satırda) satırın kendisi; `&&` öncesi atılır."""
    bulunan = []
    for satir in metin.splitlines():
        parcalar = re.findall(r"`([^`]+)`", satir) if "`" in satir else [satir]
        for p in parcalar:
            if _KOMUT.search(p):
                bulunan.append(p.split("&&")[-1].strip())
    return bulunan


def _sozcukler(komut: str) -> list[str]:
    t = [s.strip('"') for s in shlex.split(komut, posix=False)]
    return t[1:] if t and t[0] == "&" else t  # PowerShell çağrı işleci


def _sahada_calisir(komut: str) -> list[str]:
    from backend_service import _kurtarma_mi

    t = _sozcukler(komut)
    assert t and Path(t[0].replace("\\", "/")).name == "PEMF_Backend.exe", (
        f"kurtarma komutu sahada ÇALIŞMAZ (Python yok; tek çalıştırılabilir PEMF_Backend.exe): {komut}"
    )
    kalan = _kurtarma_mi(t[1:])
    assert kalan is not None, f"`--kurtarma` alt komutu yok: {komut}"
    return kalan


def test_KRITIK_KURTARMA_KODU_txt_komutu_SAHADA_ve_DONMUS_EXEde_calisir_D275(tmp_path):
    from utils import backup_recovery as br

    komutlar = _komutlar(br.kod_dosyasi_metni(br.generate_recovery_code()))
    assert komutlar, "aparat: KURTARMA-KODU.txt metninde kurtarma komutu bulunamadı"
    for komut in komutlar:
        kalan = _sahada_calisir(komut)
        yok = str(tmp_path / "yok")
        argv = [re.sub(r"<[^>]+>", lambda _m: yok, a) for a in kalan]  # yer tutucu → var olmayan yol
        sonuc, cikti = donmus_kurtarma_kos(tmp_path, argv)
        assert "kacan" not in sonuc, f"yönergenin işaret ettiği yol donmuş EXE'de öldü: {sonuc}"
        assert sonuc.get("rc") == 2 and "zarf bulunamadi" in cikti, f"araç komutu tanımadı: {sonuc}\n{cikti[-600:]}"


@pytest.fixture
def yazici(temp_app_data, tmp_path, monkeypatch):
    """Makine dışı yedek yazıcısı (`_copy_offsite`) — GERÇEK; yalnız iş parçacığı / DB kurulmaz (D2.36 deseni)."""
    from services.headless_db_maintenance import HeadlessDBMaintenance

    nas = tmp_path / "NAS"
    monkeypatch.setenv("PEMF_BACKUP_DIR", str(nas))
    w = object.__new__(HeadlessDBMaintenance)
    w.app_data_dir, w.db, w.patient_db = temp_app_data, None, None
    w.backup_interval, w.backup_retention_keep = 24 * 3600, 14
    w._stop, w._thread = threading.Event(), None
    zarf = temp_app_data / "kurtarma-zarfi.enc"
    zarf.write_bytes(b'{"tur": "kurtarma-zarfi", "v": 1, "aparat": "D275"}')
    return w, nas, zarf


def test_KRITIK_OKU_KURTARMA_notu_komutlari_SAHADA_calisir_D275(yazici):
    w, nas, zarf = yazici
    w._copy_offsite([zarf])
    not_ = nas / "OKU-KURTARMA.txt"
    assert not_.is_file(), "aparat: makine dışı kurtarma notu yazılmadı"
    komutlar = _komutlar(not_.read_text(encoding="utf-8"))
    assert len(komutlar) >= 2, f"aparat: notta zarf + hesap komutu bekleniyordu: {komutlar}"
    for komut in komutlar:
        _sahada_calisir(komut)


def test_KRITIK_aracin_KENDI_uyarilari_SAHADA_calisan_komutu_soyler_D275(tmp_path, monkeypatch, capsys):
    """Aracın bastığı yönergeler (DURDURULDU zorlama satırı, hesap yedeğinde "önce anahtarları yerleştirin", başarı sonrası
    hesap adımı) gerçek koşulda üretilir; sır deposu en alt katta (kod `get_secret`) yönlendirilir."""
    from utils import backup_recovery as br
    from utils import secrets_manager as sm

    import tools.kurtarma as k

    kod = br.generate_recovery_code()
    zarf = tmp_path / "kurtarma-zarfi.enc"
    zarf.write_bytes(br.build_envelope(kod, {"sqlcipher_key": "d275-sql"}))
    monkeypatch.setattr(sm, "get_secret", lambda ad, generate=False: "var")  # makinede anahtar VAR → DURDURULDU
    assert k.main(["--zarf", str(zarf), "--kod", kod, "--yaz"]) == 3
    monkeypatch.setattr(sm, "get_secret", lambda ad, generate=False: "")  # anahtar YOK → "önce yerleştirin"
    yedek = tmp_path / "pemf_auth_users_20261009_080000.db"
    yedek.write_bytes(b"\x00" * 64)  # şifreli görünümlü (SQLite başlığı yok)
    assert k.main(["--hesap-yedegi", str(yedek), "--cikti", str(tmp_path / "auth_users.db")]) == 2
    komutlar = _komutlar(capsys.readouterr().out)
    assert len(komutlar) >= 2, f"aparat: aracın yönerge satırları üretilmedi: {komutlar}"
    for komut in komutlar:
        _sahada_calisir(komut)


def test_KRITIK_RUNBOOK_kurtarma_komutlari_SAHADA_calisir_D275():
    komutlar = _komutlar((DEPO / "docs" / "RUNBOOK.md").read_text(encoding="utf-8"))
    assert len(komutlar) >= 3, f"aparat: RUNBOOK'ta kurtarma komutu bulunamadı: {komutlar}"
    for komut in komutlar:
        _sahada_calisir(komut)
