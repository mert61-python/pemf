# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D2.79 (D-3.1) + B-3.13'ün ikinci yarısı — `file_acl` mevcut kullanıcıyı ADIYLA değil sürecin SID'iyle verir; açılış kilidi
sürecin hesabını korur.

D-3.1: `getpass.getuser()` LocalSystem serviste `<MAKİNE>$` döndürür; `icacls` bu adı eşleyemez (1332, "hesap adlarıyla güvenlik
kimlikleri arasında eşleme yapılmadı") ve komut HEP-YA-HİÇ olduğu için SYSTEM/Administrators kilidi de UYGULANMAZ — sır dizini,
`_save` sonrası sır dosyası ve `auth_users.db` yerel Users'a açık kalır (sahip ölçtü, 2026-09-24). SYSTEM olarak koşum YASAK: hâl
`getpass.getuser` yamasıyla (`OMEN$`) ve GERÇEK `icacls` ile kurulur; LocalSystem kolu sürecin SID'i `S-1-5-18` verilerek ölçülür.
Sonuç ACL'i SID biçiminde (SDDL, `Get-Acl`) okunur: Türkçe Windows'ta grup ADLARI değişir, SID'ler değişmez.

B-3.13 ikinci yarı: `backend_service._harden_secret_file_acls` sır dosyalarını `keep_current_user=False` ile kilitliyordu →
yükseltilmemiş (launcher) süreç kendi `pemf_secrets.json`unu bir sonraki açılışta okuyamaz. D-3.1 düzelmeden `True` yapmak
LocalSystem'de kilidi tamamen düşürürdü (hep-ya-hiç) — bu yüzden AYNI değişiklikte.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from acl_sddl import sid_metni

pytestmark = pytest.mark.skipif(os.name != "nt", reason="NTFS ACL (icacls) yalnız Windows")


def _sddl(p: Path) -> str:
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", f"(Get-Acl -LiteralPath '{p}').Sddl"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0 and "D:" in r.stdout, f"aparat: SDDL okunamadı: {r.stdout}{r.stderr}"
    return r.stdout.strip()


def _dacl_sidleri(sddl: str) -> set[str]:
    """DACL'deki ERİŞİM VER (A) ACE'lerinin SID'leri; takma adlar (SY, BA, … ve YS1j: yerleşik Administrator `LA`) Windows'un SDDL
    çözücüsüyle açık SID'e çevrilir (`acl_sddl.sid_metni`)."""
    dacl = sddl.split("D:", 1)[1]
    sidler = set()
    for ace in dacl.split("(")[1:]:
        alanlar = ace.rstrip(")").split(";")
        if len(alanlar) >= 6 and alanlar[0] == "A":
            sidler.add(sid_metni(alanlar[5]))
    return sidler


def test_KARSIT_SDDL_takma_adlari_ACIK_SIDe_cozulur_yerlesik_Administrator_LA_YS1j():
    """YS1j: GitHub koşucusu yerleşik Administrator (RID 500) → SDDL sürecin SID'ini `LA` yazar. Beklenen SID bağımsız kaynaktan
    (yerel hesap listesi, SAM) okunur; sabit takma ad sözlüğü `LA`yı çözmüyordu."""
    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-LocalUser | Where-Object { $_.SID.Value -like 'S-1-5-21-*-500' } | ForEach-Object { $_.SID.Value }",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    la = r.stdout.strip()
    assert r.returncode == 0 and la.startswith("S-1-5-21-") and la.endswith("-500"), (
        f"aparat: yerleşik Administrator SID'i: {r}"
    )
    sidler = _dacl_sidleri("O:LAG:SYD:PAI(A;;FA;;;LA)(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x1200a9;;;S-1-5-19)(D;;FA;;;BU)")
    assert sidler == {la, "S-1-5-18", "S-1-5-32-544", "S-1-5-19"}, sidler


def _sifirla(p: Path) -> None:
    subprocess.run(["icacls", str(p), "/reset", "/T", "/C"], capture_output=True, timeout=60)


def _kendi_sid() -> str:
    r = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=30)
    return r.stdout.strip().split(",")[-1].strip().strip('"')


@pytest.fixture()
def localsystem_adi(monkeypatch):
    """LocalSystem hâli: `getpass.getuser()` makine hesabının adını döndürür (`<MAKİNE>$`) — icacls bunu EŞLEYEMEZ (1332)."""
    import getpass

    ad = (os.environ.get("COMPUTERNAME") or "PEMFHOST") + "$"
    monkeypatch.setattr(getpass, "getuser", lambda: ad)
    return ad


def test_KRITIK_dosya_kilidi_getpass_MAKINE_HESABI_iken_UYGULANIR_surec_SIDi_verilir_D279(tmp_path, localsystem_adi):
    """getpass `<MAKİNE>$` (LocalSystem adı) dönerken GERÇEK `lock_down_file(tmp, keep_current_user=True)`: dönüş True; DACL'de
    SYSTEM, Administrators ve sürecin SID'i VAR, Users / Authenticated Users YOK. Bugün icacls 1332 → False (kilit hiç yok)."""
    from utils import file_acl as fa

    f = tmp_path / "pemf_secrets.json"
    f.write_text("{}", encoding="utf-8")
    try:
        assert fa.lock_down_file(f, keep_current_user=True) is True, "kilit UYGULANMADI (icacls ad eşleme hatası 1332?)"
        sidler = _dacl_sidleri(_sddl(f))
        beklenen = {"S-1-5-18", "S-1-5-32-544", _kendi_sid()}
        assert beklenen <= sidler, f"DACL eksik: {sorted(beklenen - sidler)} (var: {sorted(sidler)})"
        assert not ({"S-1-5-32-545", "S-1-5-11"} & sidler), f"Users / Authenticated Users DACL'de: {sorted(sidler)}"
        assert f.read_text(encoding="utf-8") == "{}", "süreç kendi dosyasından dışarı atıldı"
    finally:
        _sifirla(f)


def test_KRITIK_dizin_kilidi_getpass_MAKINE_HESABI_iken_UYGULANIR_surec_SIDi_verilir_D279(tmp_path, localsystem_adi):
    """Aynı iddia sır DİZİNİ için (`lock_down_dir`, kalıtımlı): içinde YENİ doğan dosya Users'a kapalı, sürece açık."""
    from utils import file_acl as fa

    d = tmp_path / "PEMF_GUI"
    d.mkdir()
    try:
        assert fa.lock_down_dir(d, keep_current_user=True) is True, "dizin kilidi UYGULANMADI (icacls 1332?)"
        yeni = d / "pemf_secrets.json.1.tmp"
        yeni.write_text("x", encoding="utf-8")
        sidler = _dacl_sidleri(_sddl(yeni))
        assert {"S-1-5-18", "S-1-5-32-544", _kendi_sid()} <= sidler, f"yeni dosya kalıtımı eksik: {sorted(sidler)}"
        assert not ({"S-1-5-32-545", "S-1-5-11"} & sidler), f"yeni dosya Users'a açık: {sorted(sidler)}"
    finally:
        _sifirla(d)


def test_KRITIK_LocalSystem_surecinde_kilit_SYSTEM_ve_Administrators_ile_UYGULANIR_D279(
    tmp_path, localsystem_adi, monkeypatch
):
    """LocalSystem süreci benzetimi (SYSTEM olarak koşum YASAK): sürecin SID'i S-1-5-18. Kilit UYGULANIR (hep-ya-hiç düşmez) ve
    DACL yalnız SYSTEM + Administrators (Users yok). Test süreci SYSTEM olmadığı için dosyayı artık okuyamaz → `finally` reset."""
    from utils import file_acl as fa

    monkeypatch.setattr(fa, "_surec_sid", lambda: "S-1-5-18", raising=False)
    f = tmp_path / "auth_users.db"
    f.write_bytes(b"SQLite format 3\x00")
    try:
        assert fa.lock_down_file(f, keep_current_user=True) is True, (
            "LocalSystem'de kilit UYGULANMADI (hep-ya-hiç düşüş)"
        )
        sidler = _dacl_sidleri(_sddl(f))
        assert {"S-1-5-18", "S-1-5-32-544"} <= sidler and not ({"S-1-5-32-545", "S-1-5-11"} & sidler), sorted(sidler)
    finally:
        _sifirla(f)
    assert f.read_bytes().startswith(b"SQLite"), "aparat: erişim geri gelmedi"


def test_KRITIK_surec_SIDi_OKUNAMAZSA_kilit_UYGULANMAZ_surec_kendini_disari_ATMAZ_D279(tmp_path, monkeypatch):
    """SID okunamazsa (belirteç hatası) kilit UYGULANMAZ ve False döner: ad tahminiyle (getpass) devam etmek LocalSystem'de
    hep-ya-hiç düşer ya da yanlış hesabı yazar; eksik ACE ile kilitlemek süreci KENDİ dosyasından dışarı atar (P3)."""
    from utils import file_acl as fa

    monkeypatch.setattr(fa, "_surec_sid", lambda: None, raising=False)
    f = tmp_path / "pemf_secrets.json"
    f.write_text("{}", encoding="utf-8")
    once = _sddl(f)
    try:
        assert fa.lock_down_file(f, keep_current_user=True) is False, "SID okunamazken kilit 'uygulandı' dendi"
        assert _sddl(f) == once, "SID okunamazken DACL değiştirildi"
    finally:
        _sifirla(f)


def test_KRITIK_acilis_kilidi_sir_dosyalarinda_SUREC_HESABINI_korur_D279(tmp_path, monkeypatch):
    """B-3.13 ikinci yarı: `backend_service._harden_secret_file_acls` sır dosyalarını (ve `*.plain.bak*`) sürecin hesabını KORUYARAK
    kilitler. Varsayılan (False) yükseltilmemiş backend'i kendi `pemf_secrets.json`undan dışarı atıyordu. GERÇEK fonksiyon, casus
    `lock_down_file` (argümanlar GERÇEK imzaya bağlanır)."""
    import inspect
    import logging

    import backend_service as bs
    import utils.file_acl as fa

    app = tmp_path / "PEMF_GUI"
    app.mkdir()
    for ad in (
        "pemf_secrets.json",
        ".pemf_key_v2",
        "api_token.txt",
        "patients.db.plain.bak",
        "pemf_treatment_history.db.plain.bak.20260101_000000",
    ):
        (app / ad).write_text("x", encoding="utf-8")
    imza = inspect.signature(fa.lock_down_file)
    cagrilar = []

    def _casus(*a, **k):
        b = imza.bind(*a, **k)
        b.apply_defaults()
        cagrilar.append((Path(b.arguments["path"]).name, b.arguments["keep_current_user"]))
        return True

    monkeypatch.setattr(fa, "lock_down_file", _casus)
    bs._harden_secret_file_acls(app, logging.getLogger("d279"))
    adlar = {ad for ad, _ in cagrilar}
    assert {"pemf_secrets.json", "patients.db.plain.bak"} <= adlar, (
        f"açılış kilidi beklenen dosyalara uygulanmadı: {sorted(adlar)}"
    )
    disari = sorted(ad for ad, tut in cagrilar if tut is not True)
    assert not disari, f"açılış kilidi bu dosyalarda sürecin hesabını DIŞARI atıyor (keep_current_user False): {disari}"
