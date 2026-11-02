# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KP-2 · apps/backend/utils/file_acl.py · sözleşmeler: süreç belirteci açılamaz / bilgi boyutu boş / bilgi okunamaz / SID metne
çevrilemezse SID None — belirteç HER durumda kapatılır, ayrılmamış bellek serbest bırakılmaz · SID yoksa `keep_current_user`
dizin kilidi UYGULANMAZ (False + uyarı, `icacls` hiç çağrılmaz) · SID okunursa dizin kilidi süreç ACE'iyle (`(OI)(CI)F`) tek
`icacls` çağrısı · bilgisayar adı okunamaz / grup SID'i çözülemez / API yüklenemezse "bu makinenin yerel grubu" DEĞİL · Windows
dışında dizin 0o700, dosya 0o600 (chmod hatası → False), SID / yerel grup yok.

Sahte yalnız EN ALT katta: `ctypes.WinDLL` (advapi32 / kernel32 işlevleri), `subprocess.run` (icacls — gerçek ACL DEĞİŞMEZ),
`os.chmod`, `sys.platform`. Belirteç önbelleği (`_surec_sid_oku`) test başında ve sonunda temizlenir.
"""

from __future__ import annotations

import ctypes
import logging
import sys

import pytest
from utils import file_acl as fa


class _Fn:
    def __init__(self, impl):
        self.impl, self.argtypes, self.restype, self.cagri = impl, None, None, []

    def __call__(self, *a):
        self.cagri.append(a)
        return self.impl(*a)


class _Dll:
    def __init__(self, **fn):
        self.__dict__.update({k: _Fn(v) for k, v in fn.items()})


class _Senaryo:
    """Belirteç / yerel grup API'lerinin sahte davranışı. `bozuk` = başarısız olacak adım."""

    BELIRTEC = 4242

    def __init__(self, bozuk=None, sid="S-1-5-21-11-22-33-1001", tur=4, alan="KP2MAKINE", bilgisayar="kp2makine"):
        self.bozuk, self.sid, self.tur, self.alan, self.bilgisayar = bozuk, sid, tur, alan, bilgisayar
        self.kernel32 = _Dll(
            GetCurrentProcess=lambda: -1,
            CloseHandle=lambda h: 1,
            LocalFree=lambda p: None,
            GetComputerNameW=self._bilgisayar_adi,
        )
        self.advapi32 = _Dll(
            OpenProcessToken=self._ac,
            GetTokenInformation=self._bilgi,
            ConvertSidToStringSidW=self._sid_metni,
            ConvertStringSidToSidW=self._sid_coz,
            LookupAccountSidW=self._hesap,
        )
        self.yuklenen = []

    def windll(self, ad, *a, **k):
        self.yuklenen.append(ad)
        if self.bozuk == "yukle":
            raise OSError(126, "Belirtilen modül bulunamadı", ad)
        return {"advapi32": self.advapi32, "kernel32": self.kernel32}[ad]

    def _ac(self, surec, erisim, ref):
        if self.bozuk == "ac":
            return 0
        ref._obj.value = self.BELIRTEC
        return 1

    def _bilgi(self, h, sinif, tampon, boy, ref_boy):
        if tampon is None:
            ref_boy._obj.value = 0 if self.bozuk == "boy" else 44
            return 0
        return 0 if self.bozuk == "bilgi" else 1

    def _sid_metni(self, psid, ref):
        if self.bozuk == "metin":
            return 0
        ref._obj.value = self.sid
        return 1

    def _bilgisayar_adi(self, tampon, ref_boy):
        if self.bozuk == "bilgisayar":
            return 0
        tampon.value = self.bilgisayar
        return 1

    def _sid_coz(self, sid, ref):
        if self.bozuk == "coz":
            return 0
        ref._obj.value = 777
        return 1

    def _hesap(self, sistem, psid, ad, ad_boy, alan, alan_boy, ref_tur):
        alan.value = self.alan
        ref_tur._obj.value = self.tur
        return 1


@pytest.fixture()
def ortam(monkeypatch, tmp_path):
    fa._surec_sid_oku.cache_clear()
    monkeypatch.delenv("PEMF_DATA_GROUP_SID", raising=False)
    calistirilan = []

    def _run(args, **k):
        calistirilan.append((list(args), k))
        return None

    monkeypatch.setattr(fa.subprocess, "run", _run)
    dizin = tmp_path / "sir_dizini"
    dizin.mkdir()
    yield calistirilan, dizin
    fa._surec_sid_oku.cache_clear()


def _kur(monkeypatch, senaryo):
    monkeypatch.setattr(ctypes, "WinDLL", senaryo.windll)
    return senaryo


# ── süreç SID'i (belirteç) ────────────────────────────────────────────────────────────────────────────────────────────


def test_belirtec_ACILAMAZSA_SID_None_dizin_kilidi_UYGULANMAZ_icacls_cagrilmaz(ortam, monkeypatch, caplog):
    calistirilan, dizin = ortam
    s = _kur(monkeypatch, _Senaryo(bozuk="ac"))
    assert fa._surec_sid() is None
    with caplog.at_level(logging.WARNING, logger=fa.__name__):
        assert fa.lock_down_dir(dizin, keep_current_user=True) is False
    assert calistirilan == [], "SID yokken icacls çağrıldı (süreç kendi dizininden dışarı atılırdı)"
    assert any("Dizin ACL kilidi UYGULANMADI" in r.getMessage() for r in caplog.records)
    assert s.kernel32.CloseHandle.cagri == [], "açılmamış belirteç kapatılmaya çalışıldı"


@pytest.mark.parametrize("bozuk", ["boy", "bilgi"])
def test_belirtec_bilgisi_BOS_ya_da_OKUNAMAZSA_SID_None_ve_belirtec_KAPATILIR(ortam, monkeypatch, bozuk):
    s = _kur(monkeypatch, _Senaryo(bozuk=bozuk))
    assert fa._surec_sid() is None
    assert [c[0].value for c in s.kernel32.CloseHandle.cagri] == [_Senaryo.BELIRTEC], "belirteç kapatılmadı"
    assert s.advapi32.ConvertSidToStringSidW.cagri == []
    assert len(s.advapi32.GetTokenInformation.cagri) == (1 if bozuk == "boy" else 2)


def test_SID_metne_CEVRILEMEZSE_None_LocalFree_YOK_belirtec_KAPATILIR(ortam, monkeypatch):
    s = _kur(monkeypatch, _Senaryo(bozuk="metin"))
    assert fa._surec_sid() is None
    assert s.kernel32.LocalFree.cagri == [], "ayrılmamış SID metni serbest bırakıldı"
    assert len(s.kernel32.CloseHandle.cagri) == 1


def test_KARSIT_SID_okunursa_dizin_kilidi_SUREC_ACEsi_ile_TEK_icacls(ortam, monkeypatch):
    calistirilan, dizin = ortam
    s = _kur(monkeypatch, _Senaryo())
    assert fa._surec_sid() == "S-1-5-21-11-22-33-1001"
    assert len(s.kernel32.LocalFree.cagri) == 1 and len(s.kernel32.CloseHandle.cagri) == 1
    assert fa.lock_down_dir(dizin, keep_current_user=True) is True
    assert len(calistirilan) == 1
    args, k = calistirilan[0]
    assert args[:3] == ["icacls", str(dizin), "/inheritance:r"]
    assert args[-2:] == ["/grant:r", "*S-1-5-21-11-22-33-1001:(OI)(CI)F"]
    assert "*S-1-5-32-545" in args and k["check"] is True and k["timeout"] == 10


# ── bu makinenin yerel grubu mu ───────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bozuk", ["bilgisayar", "coz", "yukle"])
def test_bilgisayar_adi_ya_da_SID_cozulemezse_ya_da_API_yuklenemezse_YEREL_GRUP_DEGIL(monkeypatch, bozuk):
    s = _kur(monkeypatch, _Senaryo(bozuk=bozuk))
    assert fa._bu_makinenin_yerel_grubu_mu("S-1-5-21-11-22-33-1005") is False
    if bozuk != "yukle":
        assert s.kernel32.LocalFree.cagri == [], "çözülmemiş SID serbest bırakıldı"
    assert s.advapi32.LookupAccountSidW.cagri == []


def test_KARSIT_cozulen_YEREL_grup_buyuk_kucuk_harf_duyarsiz_KABUL_ve_SID_serbest(monkeypatch):
    s = _kur(monkeypatch, _Senaryo())
    assert fa._bu_makinenin_yerel_grubu_mu("S-1-5-21-11-22-33-1005") is True
    assert [c[0].value for c in s.kernel32.LocalFree.cagri] == [777]
    s2 = _kur(monkeypatch, _Senaryo(tur=2))  # SidTypeGroup (etki alanı grubu)
    assert fa._bu_makinenin_yerel_grubu_mu("S-1-5-21-11-22-33-1005") is False
    assert len(s2.kernel32.LocalFree.cagri) == 1


# ── Windows dışı ──────────────────────────────────────────────────────────────────────────────────────────────────────


def test_windows_DISINDA_dizin_0o700_dosya_0o600_SID_ve_yerel_grup_YOK(ortam, monkeypatch, tmp_path):
    calistirilan, dizin = ortam
    dosya = tmp_path / "pemf_secrets.json"
    dosya.write_text("{}", encoding="utf-8")
    chmod = []
    with monkeypatch.context() as m:
        m.setattr(sys, "platform", "linux")
        m.setattr(fa.os, "chmod", lambda p, mod: chmod.append((p, mod)))
        sonuc = (
            fa.lock_down_dir(dizin),
            fa.lock_down_file(dosya, keep_current_user=True),
            fa._surec_sid(),
            fa._bu_makinenin_yerel_grubu_mu("S-1-5-21-11-22-33-1005"),
        )
    assert sonuc == (True, True, None, False)
    assert chmod == [(str(dizin), 0o700), (str(dosya), 0o600)]
    assert calistirilan == [], "Windows dışında icacls çağrıldı"


def test_windows_DISINDA_chmod_HATASI_False(ortam, monkeypatch, tmp_path):
    _calistirilan, dizin = ortam
    dosya = tmp_path / "anahtar.bin"
    dosya.write_bytes(b"x")

    def _izin_yok(p, mod):
        raise PermissionError(1, "Operation not permitted", p)

    with monkeypatch.context() as m:
        m.setattr(sys, "platform", "linux")
        m.setattr(fa.os, "chmod", _izin_yok)
        sonuc = (fa.lock_down_dir(dizin), fa.lock_down_file(dosya))
    assert sonuc == (False, False)
