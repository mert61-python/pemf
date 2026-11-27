# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y96 (sahip kararı 2026-10-07 · B-3.51 / A-2A.1) — `file_acl` yarısı: çok hesaplı kurulumda kilitler, uygulamayı kullanan hesapların
üye olduğu PAYLAŞILAN yerel grubu (`PEMF_DATA_GROUP_SID`) da korur; yerel Users yine dışarıda. (Launcher yarısı — grubu kurmak ve SID'i
backend'e vermek — Rust oturumunda.)

Kusur: `lock_down_dir` / `lock_down_file` `/inheritance:r` ile veri kökünün kalıtımını KALDIRIP yalnız SYSTEM + Administrators + süreç
hesabını bırakıyordu → launcher veri kökünü paylaşılan grupla kursa bile ilk hesabın açılışı sır dizinini, sır dosyalarını ve
`auth_users.db`yi öbür hesaplara KAPATIYORDU (B-3.51: ikinci hesap "sır okunamadı" ile DB'siz kipte kalır).

Benzetim (yasak: ikinci Windows hesabı / yeni yerel grup OLUŞTURULMAZ): "ilk hesap" = başka bir hesabın SID'i (S-1-5-19, LOCAL SERVICE;
`_surec_sid` yaması); "ikinci hesap" = bu test süreci; "paylaşılan grup" = bu makinede VAR OLAN ve bu sürecin belirtecinde bulunan
oluşturulmuş bir yerel grup (ör. docker-users). Erişim GERÇEK okuma/yazma ile ölçülür: yükseltilmemiş belirteçte Administrators
yalnız-red olduğundan kilitten sonra bu süreç dosyaya YALNIZ grup ACE'iyle ulaşabilir. `finally`: `icacls /reset` ve erişimin geri
geldiği ölçülür. Geniş grup SID'leri (Users / Authenticated Users / Everyone / Interactive / None) ve bir KULLANICI SID'i bu sürecin
belirtecinde de bulunduğundan, yanlışlıkla verilseler okuma BAŞARILI olurdu → ret de gerçek erişimle ölçülür.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="NTFS ACL (icacls) yalnız Windows")

_ORTAM = "PEMF_DATA_GROUP_SID"  # sözleşme adı — launcher bu adla verir (mutasyon hedefinden OKUNMAZ)
_ILK_HESAP = "S-1-5-19"  # LOCAL SERVICE: bu makinede çözülen, bu sürecin OLMADIĞI bir hesap


def _ps(komut: str) -> str:
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", komut],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, f"aparat: powershell düştü: {r.stderr}"
    return r.stdout.strip()


def _sddl(p: Path) -> str:
    s = _ps(f"(Get-Acl -LiteralPath '{p}').Sddl")
    assert "D:" in s, f"aparat: SDDL okunamadı: {s}"
    return s


def _dacl_sidleri(sddl: str) -> set[str]:
    """DACL'deki ERİŞİM VER (A) ACE'lerinin hesapları (SDDL kısaltması ya da SID)."""
    dacl = sddl.split("D:", 1)[1].split("S:", 1)[0]
    return {m.group(2) for m in re.finditer(r"\((A);[^;()]*;[^;()]*;[^;()]*;[^;()]*;([^;()]+)\)", dacl)}


def _sifirla(p: Path) -> None:
    subprocess.run(["icacls", str(p), "/reset", "/T", "/C"], capture_output=True, timeout=60)


def _okunur_mu(p: Path) -> bool:
    try:
        p.read_bytes()
        return True
    except PermissionError:
        return False


@pytest.fixture(scope="module")
def kendi_sid() -> str:
    sid = _ps("[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value")
    assert re.fullmatch(r"S-1-5-21-\d+-\d+-\d+-\d+", sid), f"aparat: sürecin SID'i beklenen biçimde değil: {sid}"
    return sid


@pytest.fixture(scope="module")
def paylasilan_grup() -> str:
    """Bu sürecin belirtecinde bulunan, bu makinede OLUŞTURULMUŞ bir yerel grup (S-1-5-21-…). Yoksa kol ölçülemez → atla."""
    cikti = _ps(
        "$g = [System.Security.Principal.WindowsIdentity]::GetCurrent().Groups | ForEach-Object { $_.Value }; "
        "Get-LocalGroup | Where-Object { $g -contains $_.SID.Value -and $_.SID.Value -like 'S-1-5-21-*' } | "
        "ForEach-Object { $_.SID.Value }"
    )
    sidler = [s.strip() for s in cikti.splitlines() if s.strip()]
    if not sidler:
        pytest.skip("bu makinede sürecin üye olduğu oluşturulmuş yerel grup yok — paylaşılan grup kolu ölçülemez")
    return sidler[0]


@pytest.fixture()
def ilk_hesap(monkeypatch):
    """Kilidi "ilk hesap" (başka bir hesap) uygular; ret günlüğünün "bir kez" kümesi her testte boş."""
    import utils.file_acl as fa

    monkeypatch.setattr(fa, "_surec_sid", lambda: _ILK_HESAP)
    monkeypatch.setattr(fa, "_grup_uyarisi_verilen", set(), raising=False)
    return fa


def test_KRITIK_dosya_kilidi_PAYLASILAN_GRUBA_erisim_verir_ikinci_hesap_OKUR_Y96(
    tmp_path, monkeypatch, ilk_hesap, paylasilan_grup
):
    monkeypatch.setenv(_ORTAM, paylasilan_grup)
    f = tmp_path / "pemf_secrets.json"
    f.write_text("{}", encoding="utf-8")
    try:
        assert ilk_hesap.lock_down_file(f, keep_current_user=True) is True, "kilit uygulanmadı"
        assert _okunur_mu(f), (
            "ikinci hesap (paylaşılan grubun üyesi) ilk hesabın kilidinden sonra sır dosyasını OKUYAMIYOR — grup ACE'i yok"
        )
        sidler = _dacl_sidleri(_sddl(f))
        assert paylasilan_grup in sidler, f"paylaşılan grup DACL'de yok: {sidler}"
        assert not ({"BU", "AU", "S-1-5-32-545", "S-1-5-11"} & sidler), (
            f"Users / Authenticated Users açık kaldı: {sidler}"
        )
    finally:
        _sifirla(f)
    assert _okunur_mu(f), "aparat: /reset sonrası erişim geri gelmedi"


def test_KRITIK_dizin_kilidi_PAYLASILAN_GRUBA_kalitimla_erisim_verir_ikinci_hesap_YAZAR_OKUR_Y96(
    tmp_path, monkeypatch, ilk_hesap, paylasilan_grup
):
    monkeypatch.setenv(_ORTAM, paylasilan_grup)
    d = tmp_path / "PEMF_GUI"
    d.mkdir()
    try:
        assert ilk_hesap.lock_down_dir(d, keep_current_user=True) is True, "dizin kilidi uygulanmadı"
        try:
            (d / "auth_users.db").write_bytes(b"x")
            eristi = (d / "auth_users.db").read_bytes() == b"x" and "auth_users.db" in os.listdir(d)
        except PermissionError:
            eristi = False
        assert eristi, (
            "ikinci hesap ilk hesabın kilitlediği veri dizininde dosya OLUŞTURAMIYOR/OKUYAMIYOR — kalıtımlı grup ACE'i yok"
        )
        assert not ({"BU", "AU", "S-1-5-32-545", "S-1-5-11"} & _dacl_sidleri(_sddl(d))), (
            "Users / Authenticated Users açık kaldı"
        )
    finally:
        _sifirla(d)
    assert "auth_users.db" in os.listdir(d), "aparat: /reset sonrası dizine erişim geri gelmedi"


@pytest.fixture(scope="module")
def olusturulmus_grup() -> str:
    """Bu makinede OLUŞTURULMUŞ herhangi bir yerel grup (S-1-5-21-…) — süreç ÜYE OLMASA da. YS1m: GitHub koşucusunda hiç yoktu (Y96
    grup kolu kapsam dışı: `file_acl` 2 satır, %99,99 < 100); `tests.yml` üyeliksiz `pemf-ci-paylasim` kurar. CI'da yoksa KIRMIZI
    (kurulum adımı sessizce kaybolmasın); yerelde yoksa atla."""
    return _olusturulmus_grup_sec(
        _ps("Get-LocalGroup | Where-Object { $_.SID.Value -like 'S-1-5-21-*' } | ForEach-Object { $_.SID.Value }"),
        os.environ.get("GITHUB_ACTIONS") == "true",
    )


def _olusturulmus_grup_sec(cikti: str, ci: bool) -> str:
    sidler = [s.strip() for s in cikti.splitlines() if s.strip()]
    if not sidler:
        if ci:
            pytest.fail(
                "CI: oluşturulmuş yerel grup YOK — tests.yml 'Paylaşılan yerel grup (Y96, üyeliksiz)' adımı koşmadı"
            )
        pytest.skip("bu makinede oluşturulmuş yerel grup yok — grup ACE'i kolu ölçülemez")
    return sidler[0]


def test_olusturulmus_grup_secimi_CIde_grup_YOKSA_KIRMIZI_yerelde_atlar_YS1m():
    cikti = "\r\nS-1-5-21-1-2-3-1001\r\nS-1-5-21-1-2-3-1002\r\n"
    assert _olusturulmus_grup_sec(cikti, ci=True) == "S-1-5-21-1-2-3-1001"
    with pytest.raises(BaseException) as hata:  # skip de BaseException: CI'da ATLAMA da yakalanıp REDDEDİLSİN
        _olusturulmus_grup_sec(" \r\n", ci=True)
    assert hata.type is pytest.fail.Exception and "adımı koşmadı" in str(hata.value), hata.type
    with pytest.raises(pytest.skip.Exception):
        _olusturulmus_grup_sec("", ci=False)


def test_KRITIK_OLUSTURULMUS_yerel_grup_uye_olunmasa_da_dosya_ve_dizin_kilidinde_ACIKCA_VERILIR_Y96(
    tmp_path, monkeypatch, ilk_hesap, olusturulmus_grup
):
    """Launcher'ın kurduğu grubun üyesi ilk hesaptır; kilidi uygulayan süreç üye olmak ZORUNDA değil. Grup ACE'i DACL'de AÇIKÇA:
    dosyada `FA`, dizinde kalıtımlı `OICI FA` (ikinci hesap dizinde doğan dosyaya da ulaşsın)."""
    monkeypatch.setenv(_ORTAM, olusturulmus_grup)
    f = tmp_path / "pemf_secrets.json"
    f.write_text("{}", encoding="utf-8")
    d = tmp_path / "PEMF_GUI"
    d.mkdir()
    try:
        assert ilk_hesap.lock_down_file(f, keep_current_user=True) is True
        assert f"(A;;FA;;;{olusturulmus_grup})" in _sddl(f), f"dosya kilidinde grup ACE'i yok: {_sddl(f)}"
        assert ilk_hesap.lock_down_dir(d, keep_current_user=True) is True
        assert f"(A;OICI;FA;;;{olusturulmus_grup})" in _sddl(d), f"dizin kilidinde kalıtımlı grup ACE'i yok: {_sddl(d)}"
    finally:
        _sifirla(f)
        _sifirla(d)


_GENIS = {
    "Users": "S-1-5-32-545",
    "AuthenticatedUsers": "S-1-5-11",
    "Everyone": "S-1-1-0",
    "Interactive": "S-1-5-4",
}


@pytest.mark.parametrize("tur", [*_GENIS, "None_513", "kullanici_hesabi"])
def test_KARSIT_genis_grup_ya_da_KULLANICI_SIDi_VERILMEZ_kilit_yine_UYGULANIR_Y96(
    tur, tmp_path, monkeypatch, ilk_hesap, kendi_sid
):
    """Bu SID'lerin HEPSİ bu sürecin belirtecinde var: yanlışlıkla verilseler okuma BAŞARILI olurdu (makinedeki herkes / bir kişi)."""
    sid = _GENIS.get(tur) or {"None_513": kendi_sid.rsplit("-", 1)[0] + "-513", "kullanici_hesabi": kendi_sid}[tur]
    monkeypatch.setenv(_ORTAM, sid)
    f = tmp_path / "pemf_secrets.json"
    f.write_text("{}", encoding="utf-8")
    try:
        assert ilk_hesap.lock_down_file(f, keep_current_user=True) is True, f"{tur} ({sid}) kilidi DÜŞÜRDÜ"
        assert not _okunur_mu(f), f"{tur} ({sid}) gruba VERİLDİ — sır dosyası bu hesaba açıldı"
    finally:
        _sifirla(f)


def test_KARSIT_COZULEMEYEN_grup_SIDi_kilidi_DUSURMEZ_Y96(tmp_path, monkeypatch, ilk_hesap):
    """icacls hep-ya-hiç: çözülemeyen tek SID (silinmiş grup) bütün kilidi düşürür (1332) — grup verilmez, kilit yine uygulanır."""
    monkeypatch.setenv(_ORTAM, "S-1-5-21-1-2-3-4242")
    f = tmp_path / "pemf_secrets.json"
    f.write_text("{}", encoding="utf-8")
    try:
        assert ilk_hesap.lock_down_file(f, keep_current_user=True) is True, (
            "çözülemeyen grup SID'i icacls'i düşürdü (1332, hep-ya-hiç) — kilit HİÇ uygulanmadı, Users açık kaldı"
        )
        sidler = _dacl_sidleri(_sddl(f))
        assert not ({"BU", "AU", "S-1-5-32-545", "S-1-5-11"} & sidler), (
            f"Users / Authenticated Users açık kaldı: {sidler}"
        )
    finally:
        _sifirla(f)


def test_KARSIT_keep_current_user_FALSE_kilidinde_grup_VERILMEZ_Y96(tmp_path, monkeypatch, ilk_hesap, paylasilan_grup):
    """Yalnız SYSTEM + Administrators kipi (`keep_current_user=False`) paylaşılan gruba da AÇILMAZ."""
    monkeypatch.setenv(_ORTAM, paylasilan_grup)
    f = tmp_path / "pemf_mqtt_credentials.json"
    f.write_text("{}", encoding="utf-8")
    try:
        assert ilk_hesap.lock_down_file(f) is True
        assert not _okunur_mu(f), "yalnız SYSTEM + Administrators kilidi paylaşılan gruba da açıldı"
    finally:
        _sifirla(f)


@pytest.mark.parametrize(
    ("sid", "seviye", "ifade"),
    [("S-1-1-0", logging.ERROR, "REDDEDILDI"), ("S-1-5-21-1-2-3-4242", logging.WARNING, "bulunamadi")],
    ids=["genis_Everyone", "cozulemeyen"],
)
def test_ret_nedeni_BIR_KEZ_gunluge_yazilir_Y96(sid, seviye, ifade, tmp_path, monkeypatch, caplog, ilk_hesap):
    """Grup verilmediğinde operatör NEDENİNİ öğrenir (geniş grup = ERROR, bulunamayan = WARNING); her kilitte tekrarlanmaz."""
    monkeypatch.setenv(_ORTAM, sid)
    caplog.set_level(logging.WARNING, logger="utils.file_acl")
    f = tmp_path / "pemf_secrets.json"
    f.write_text("{}", encoding="utf-8")
    try:
        ilk_hesap.lock_down_file(f, keep_current_user=True)
        ilk_hesap.lock_down_file(f, keep_current_user=True)
    finally:
        _sifirla(f)
    kayit = [r for r in caplog.records if _ORTAM in r.getMessage()]
    assert len(kayit) == 1, f"ret nedeni BİR KEZ günlüğe yazılmalı: {[r.getMessage() for r in kayit]}"
    assert kayit[0].levelno == seviye and ifade in kayit[0].getMessage(), kayit[0].getMessage()
