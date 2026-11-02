# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/servers/update_manager.py · sözleşmeler: URL çözümlenemezse (kaynak / yönlendirme) reddedilir · izin verilen
yönlendirme izlenir · geçici dizin silinemezse istisna sızmaz · eski `pemf_upd_*` süpürmesi (erişilemeyen dizin atlanır, genç dizine
dokunulmaz; geçici kök yoksa 0) · donmuş derlemede sürüm yolu sırası (_MEIPASS → EXE → EXE/_internal) ve okunamayan sürüm dosyasının
atlanması · ayrıştırılamayan sürüm → güncelleme ÖNERİLMEZ · yakma penceresi okunamazsa güncelleme bayrağına göre karar · aktif
tedavi denetimi FAIL-CLOSED (snapshot yok / istisna → aktif; aktif seans → aktif) · Authenticode (Valid / HashMismatch→tampered /
imzasız / boş / zaman aşımı → unknown; Windows dışı → unknown; yol tırnağı kaçışlı) · apply / rollback: SHA yok / SHA uyuşmaz / imza
kurcalanmış / indirme sırasında tedavi başladı → installer BAŞLATILMAZ, guard serbest; indirilen dosya AV tarafından tutulup
silinemese de akış aynı · rollback: geçersiz URL / guard zaten açık · denetleyici: canlıyken ikinci kez başlamaz; süpürme hatası
döngüyü öldürmez, yeni sürüm günlüğe yazılır.

Sahte EN ALT katta: ağ = `urllib.request.OpenerDirector.open` (urlopen VE pinli açıcı buradan geçer; GERÇEK ağ YOK), süreç =
`subprocess.run` (PowerShell imza denetimi) ve update_manager'ın `subprocess.Popen` adı (installer ASLA çalışmaz — kayıtçı), geçici
kök = `tempfile.tempdir` (tmp) / `tempfile.gettempdir` (kullanılabilir geçici dizin yok), dosya sistemi (`Path.stat` yalnız tek dizin
için EACCES; indirilen dosyaya açık okuma tutamağı = AV tarayıcısı → silme WinError 32), `sys.frozen/_MEIPASS/executable`, `os.name`,
içe aktarma engeli (`utils.firmware_yakma_penceresi`: sys.modules None + paket özniteliği; monkeypatch geri koyar). Aktif-tedavi için
GERÇEK `_build_ws_snapshot` çıktısı (yalnız `activeTreatment.isActive` çevrilir). Döngü olayı (`_stop`) sahte olay: gerçek bekleme YOK.
Tek istisna (üst kat): denetleyici döngüsünün süpürme-hatası kolu için `sweep_stale_update_temp` istisna atar (ürün işlevi istisna
yutar; kol yalnız savunma).
"""

from __future__ import annotations

import errno
import glob
import hashlib
import importlib
import io
import json
import logging
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import types
import urllib.error
import urllib.request

import pytest
from servers import update_manager as um
from utils import ceviri

URL = "https://github.com/mert61-python/pemf-update/releases/download/exe-v999.0.0/PEMF_Setup.exe"
ONCEKI_URL = "https://github.com/mert61-python/pemf-update/releases/download/exe-v1.0.0/PEMF_Setup.exe"
GOVDE = b"MZ-KP-sahte-installer"
SHA = hashlib.sha256(GOVDE).hexdigest()
LOG = "servers.update_manager"


# ── Aparat ───────────────────────────────────────────────────────────────────


class _Yanit(io.BytesIO):
    def __init__(self, veri, kanca=None):
        super().__init__(veri)
        self._kanca = kanca

    def read(self, *a):
        if self._kanca is not None:
            k, self._kanca = self._kanca, None
            k()
        return super().read(*a)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class _Ota:
    """Ağ / süreç / geçici kök aparatı. `manifest` ve `govdeler` testte ayarlanır; `av_kilidi` True → indirilen installer okunurken
    üzerine açık bir okuma tutamağı alınır (AV tarayıcısı) — ürün dosyayı SİLEMEZ."""

    def __init__(self, temp):
        self.temp = temp
        self.manifest: dict = {}
        self.govdeler: dict = {}
        self.ag: list = []
        self.pinli: list = []
        self.ps: list = []
        self.ps_kw: list = []  # EN ALT kat (subprocess.run) çağrı anahtar argümanları: creationflags / timeout / text …
        self.ps_cikti = "NotSigned"
        self.popen: list = []
        self.av_kilidi = False
        self.tutamaklar: list = []

    def _av(self):
        for p in glob.glob(str(self.temp / "pemf_upd_*" / "*.exe")):
            self.tutamaklar.append(open(p, "rb"))

    def ac(self, opener, fullurl, data=None, timeout=None):
        url = fullurl if isinstance(fullurl, str) else fullurl.full_url
        self.ag.append(url)
        self.pinli.append(any(isinstance(h, um._PinliYonlendirme) for h in opener.handlers))
        if url.startswith(um._MANIFEST_URL):
            return _Yanit(json.dumps(self.manifest).encode("utf-8"))
        if url in self.govdeler:
            return _Yanit(self.govdeler[url], self._av if self.av_kilidi else None)
        raise urllib.error.URLError("aparat: bilinmeyen URL")

    def run(self, args, **k):
        self.ps.append(list(args))
        self.ps_kw.append(dict(k))
        if isinstance(self.ps_cikti, BaseException):
            raise self.ps_cikti
        return subprocess.CompletedProcess(args, 0, stdout=self.ps_cikti, stderr="")

    def kapat(self):
        for t in self.tutamaklar:
            t.close()
        self.tutamaklar.clear()

    def dizinler(self):
        return sorted(p.name for p in self.temp.glob("pemf_upd_*"))


@pytest.fixture
def ota(monkeypatch, tmp_path):
    temp = tmp_path / "temp"
    temp.mkdir()
    o = _Ota(temp)
    monkeypatch.setenv("PEMF_LEGACY_EXE_UPDATE", "1")
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    monkeypatch.setattr(um, "_status", dict(um._status))
    monkeypatch.setattr(um, "_applying", False)
    monkeypatch.setattr(um, "_applying_since", None)
    monkeypatch.setattr(
        urllib.request.OpenerDirector, "open", lambda self, u, data=None, timeout=None: o.ac(self, u, data, timeout)
    )
    monkeypatch.setattr(subprocess, "run", o.run)
    monkeypatch.setattr(um, "subprocess", types.SimpleNamespace(Popen=lambda argv, **k: o.popen.append(list(argv))))
    try:
        yield o
    finally:
        o.kapat()


def _yayinla(ota, sha=SHA, onceki=None):
    """Manifest'i GERÇEK `check_for_update` ile önbelleğe al (sürüm 999.0.0 > kurulu)."""
    ota.manifest = {"version": "999.0.0", "installerUrl": URL, "sha256": sha, "notes": "kp"}
    if onceki is not None:
        ota.manifest["previousStable"] = onceki
    ota.govdeler = {URL: GOVDE, ONCEKI_URL: GOVDE}
    st = um.check_for_update(timeout=1)
    assert st["available"] is True and st["error"] == "", st


def _modul_yok(monkeypatch, ad):
    paket_adi, _, alt = ad.rpartition(".")
    paket = importlib.import_module(paket_adi)
    monkeypatch.delattr(paket, alt, raising=False)
    monkeypatch.setitem(sys.modules, ad, None)


def _kayitlar(caplog, parca, seviye=None):
    return [r for r in caplog.records if parca in r.getMessage() and (seviye is None or r.levelno == seviye)]


@pytest.fixture
def snapshot_sayaci(monkeypatch):
    """GERÇEK `_build_ws_snapshot`; `aktif_sonra` çağrı sayısından SONRA `activeTreatment.isActive` True döner."""
    from servers import api_server as api

    gercek = api._build_ws_snapshot
    durum = {"n": 0, "aktif_sonra": None}

    def _snap():
        durum["n"] += 1
        s = gercek()
        if durum["aktif_sonra"] is not None and durum["n"] > durum["aktif_sonra"]:
            s = dict(s)
            s["activeTreatment"] = {**(s.get("activeTreatment") or {}), "isActive": True}
        return s

    monkeypatch.setattr(api, "_build_ws_snapshot", _snap)
    return durum


# ── URL doğrulama / yönlendirme ──────────────────────────────────────────────


def test_kaynak_URL_COZUMLENEMEZSE_reddedilir():
    """`https://[::1` (kapanmamış IPv6) → (False, 'guncelleme.url.cozumlenemedi')."""
    assert um._validate_installer_url("https://[::1") == (False, ceviri.t("guncelleme.url.cozumlenemedi"))


def test_yonlendirme_hedefi_COZUMLENEMEZSE_reddedilir():
    """yönlendirme hedefi `https://[::1` → (False, 'yönlendirme hedefi çözümlenemedi')."""
    assert um._yonlendirme_hedefi_dogrula("https://[::1") == (False, "yönlendirme hedefi çözümlenemedi")


def test_IZINLI_yonlendirme_hedefi_IZLENIR_yeni_istek_hedefe():
    """302 → objects.githubusercontent.com → yeni istek o adrese kurulur (yönlendirme izlenir)."""
    h = um._PinliYonlendirme()
    eski = urllib.request.Request(URL, headers={"User-Agent": "pemf-updater"})
    hedef = "https://objects.githubusercontent.com/github-production-release-asset/abc?sig=1"
    yeni = h.redirect_request(eski, io.BytesIO(b""), 302, "Found", {}, hedef)
    assert isinstance(yeni, urllib.request.Request)
    assert yeni.full_url == hedef


# ── Geçici dizinler ──────────────────────────────────────────────────────────


def test_gecici_dizin_SILINEMEZSE_istisna_sizmaz_debug(caplog):
    """yol olarak kullanılamayan değer (Path TypeError) → `_discard_temp_dir` istisna atmaz; 'gecici guncelleme dizini silinemedi' debug."""
    with caplog.at_level(logging.DEBUG, logger=LOG):
        assert um._discard_temp_dir(12345) is None
    k = _kayitlar(caplog, "gecici guncelleme dizini silinemedi", logging.DEBUG)
    assert k and k[0].exc_info is not None


def test_supurme_ERISILEMEYEN_dizini_atlar_ESKIYI_siler_GENCE_dokunmaz(tmp_path, monkeypatch, caplog):
    """3 dizin: eski (7 sa), genç (şimdi), varlık denetimi EACCES olan → yalnız eski silinir, sayı 1, info kaydı; diğer ikisi yerinde."""
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    eski, genc, kilit = temp / "pemf_upd_eski", temp / "pemf_upd_genc", temp / "pemf_upd_kilit"
    for d in (eski, genc, kilit):
        d.mkdir()
        (d / "x.exe").write_bytes(b"x")
    yedi_saat_once = time.time() - 7 * 3600
    os.utime(eski, (yedi_saat_once, yedi_saat_once))
    os.utime(kilit, (yedi_saat_once, yedi_saat_once))
    orj = pathlib.Path.stat

    def _stat(self, *a, **k):
        if self.name == "pemf_upd_kilit":
            raise PermissionError(errno.EACCES, "Erisim engellendi", str(self))
        return orj(self, *a, **k)

    with monkeypatch.context() as m, caplog.at_level(logging.INFO, logger=LOG):
        m.setattr(pathlib.Path, "stat", _stat)
        assert um.sweep_stale_update_temp() == 1
    assert not eski.exists()
    assert genc.is_dir() and kilit.is_dir()
    assert _kayitlar(caplog, "Eski guncelleme gecici dizini temizlendi: 1")


def test_supurme_GECICI_KOK_YOKSA_0_ve_debug(monkeypatch, caplog):
    """`tempfile.gettempdir` kullanılabilir dizin bulamaz (FileNotFoundError) → 0, istisna sızmaz, debug kaydı."""

    def _yok():
        raise FileNotFoundError(errno.ENOENT, "No usable temporary directory found")

    monkeypatch.setattr(tempfile, "gettempdir", _yok)
    with caplog.at_level(logging.DEBUG, logger=LOG):
        assert um.sweep_stale_update_temp() == 0
    assert _kayitlar(caplog, "gecici dizin suepuermesi basarisiz", logging.DEBUG)


# ── Kurulu sürüm (donmuş derleme) ────────────────────────────────────────────


def _donmus(monkeypatch, mei, exe, meipass=True):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    if meipass:
        monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    else:
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "executable", str(exe / "PEMF_Backend.exe"))


def test_surum_yollari_DONMUS_sira_MEIPASS_EXE_INTERNAL(tmp_path, monkeypatch):
    """donmuş + _MEIPASS → VERSION adayları sırası: MEI, EXE, EXE/_internal, (kaynak kökü = MEI); sonra frontend_version.json aynı sırada."""
    mei, exe = tmp_path / "mei", tmp_path / "exe"
    mei.mkdir()
    exe.mkdir()
    _donmus(monkeypatch, mei, exe)
    exe_r = exe.resolve()
    beklenen = []
    for ad in ("VERSION", "frontend_version.json"):
        beklenen += [mei / ad, exe_r / ad, exe_r / "_internal" / ad, mei / ad]
    assert um._version_paths() == beklenen


def test_surum_DONMUS_meipass_YOKSA_EXE_internal_okunur(tmp_path, monkeypatch):
    """donmuş, _MEIPASS tanımsız → aday listesinde _MEIPASS yok; EXE/_internal/VERSION '3.4.5' okunur."""
    mei, exe = tmp_path / "mei", tmp_path / "exe"
    (exe / "_internal").mkdir(parents=True)
    (exe / "_internal" / "VERSION").write_text("3.4.5\n", encoding="utf-8")
    _donmus(monkeypatch, mei, exe, meipass=False)
    exe_r = exe.resolve()
    assert um._version_paths()[:2] == [exe_r / "VERSION", exe_r / "_internal" / "VERSION"]
    assert um.get_current_version() == "3.4.5"


def test_surum_OKUNAMAYAN_dosya_ATLANIR_siradaki_okunur(tmp_path, monkeypatch):
    """_MEIPASS/VERSION geçersiz UTF-8 → atlanır; EXE/VERSION '2.0.7' döner (ilk okunabilen)."""
    mei, exe = tmp_path / "mei", tmp_path / "exe"
    mei.mkdir()
    exe.mkdir()
    (mei / "VERSION").write_bytes(b"\xff\xfe\xff")
    (exe / "VERSION").write_text("2.0.7\n", encoding="utf-8")
    _donmus(monkeypatch, mei, exe)
    assert um.get_current_version() == "2.0.7"


def test_surum_HICBIR_aday_okunamazsa_0_0_0(tmp_path, monkeypatch):
    """donmuş; _MEIPASS'ta yalnız bozuk frontend_version.json, EXE dizini boş → '0.0.0' (bilinmeyen sürüm; uydurma yok)."""
    mei, exe = tmp_path / "mei", tmp_path / "exe"
    mei.mkdir()
    exe.mkdir()
    (mei / "frontend_version.json").write_text("{bozuk json", encoding="utf-8")
    _donmus(monkeypatch, mei, exe)
    assert um.get_current_version() == "0.0.0"


def test_AYRISTIRILAMAYAN_surum_guncelleme_ONERMEZ_ve_uyari(caplog):
    """'beta' / '1.0.0' → False (sonsuz yeniden kurulum yok) + 'Surum ayristirilamadi' uyarısı."""
    with caplog.at_level(logging.WARNING, logger=LOG):
        assert um._is_newer("beta", "1.0.0") is False
    assert _kayitlar(caplog, "Surum ayristirilamadi", logging.WARNING)


# ── Güncelleme bayrağı / aktif tedavi ────────────────────────────────────────


def test_yakma_penceresi_OKUNAMAZSA_guncelleme_bayragina_gore(monkeypatch, caplog):
    """yakma penceresi modülü yok → debug kaydı; bayrak kapalı → False, bayrak açık ve taze → True."""
    _modul_yok(monkeypatch, "utils.firmware_yakma_penceresi")
    monkeypatch.setattr(um, "_applying", False)
    monkeypatch.setattr(um, "_applying_since", None)
    with caplog.at_level(logging.DEBUG, logger=LOG):
        assert um.is_update_in_progress() is False
    assert _kayitlar(caplog, "firmware yakma penceresi okunamadi", logging.DEBUG)
    monkeypatch.setattr(um, "_applying", True)
    monkeypatch.setattr(um, "_applying_since", time.monotonic())
    assert um.is_update_in_progress() is True


def test_aktif_tedavi_SNAPSHOT_YOKSA_fail_closed(monkeypatch, caplog):
    """api_server'da `_build_ws_snapshot` yok → True (güncelleme reddedilir) + uyarı."""
    from servers import api_server as api

    monkeypatch.delattr(api, "_build_ws_snapshot")
    with caplog.at_level(logging.WARNING, logger=LOG):
        assert um._has_active_treatment() is True
    assert _kayitlar(caplog, "_build_ws_snapshot yok", logging.WARNING)


def test_aktif_tedavi_SEANS_AKTIFSE_True_degilse_False(snapshot_sayaci):
    """gerçek snapshot (seans yok) → False; aynı snapshot `activeTreatment.isActive` True → True."""
    assert um._has_active_treatment() is False
    snapshot_sayaci["aktif_sonra"] = 0
    assert um._has_active_treatment() is True


def test_aktif_tedavi_SNAPSHOT_ISTISNASI_fail_closed(monkeypatch, caplog):
    """snapshot RuntimeError → True + 'fail-closed' istisna kaydı."""
    from servers import api_server as api

    def _patla():
        raise RuntimeError("snapshot coktu")

    monkeypatch.setattr(api, "_build_ws_snapshot", _patla)
    with caplog.at_level(logging.ERROR, logger=LOG):
        assert um._has_active_treatment() is True
    k = _kayitlar(caplog, "Aktif-tedavi kontrolü başarısız", logging.ERROR)
    assert k and k[0].exc_info is not None


# ── Authenticode ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cikti,beklenen",
    [
        ("Valid\r\n", "valid"),
        ("HashMismatch\r\n", "tampered"),
        ("NotTrusted", "tampered"),
        ("NotSigned\r\n", "unsigned"),
        ("", "unsigned"),
    ],
)
def test_authenticode_DURUM_eslemesi_ve_YOL_tirnagi_kacisli(ota, tmp_path, cikti, beklenen):
    """PowerShell çıktısı → durum; komut `-LiteralPath '…it''s….exe'` (tek tırnak ikilenir), pencere açmayan bayrakla: EN ALT
    kattaki `subprocess.run` çağrısı `creationflags` = Windows CREATE_NO_WINDOW (0x08000000; güncelleme sırasında siyah konsol
    penceresi açılmaz), `timeout` = 20 sn, metin çıktısı yakalanır."""
    p = tmp_path / "it's.exe"
    p.write_bytes(b"x")
    ota.ps_cikti = cikti
    assert um._verify_authenticode(p) == beklenen
    assert len(ota.ps) == 1
    args = ota.ps[0]
    assert args[:4] == ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    assert "-LiteralPath '" + str(p).replace("'", "''") + "'" in args[4]
    kw = ota.ps_kw[0]
    assert kw.get("creationflags") == getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000), kw
    assert kw.get("timeout") == 20 and kw.get("text") is True and kw.get("capture_output") is True, kw


def test_authenticode_ZAMAN_ASIMI_unknown_ve_istisna_kaydi(ota, tmp_path, caplog):
    """PowerShell zaman aşımı (TimeoutExpired) → 'unknown' (SHA birincil kapı) + istisna kaydı."""
    ota.ps_cikti = subprocess.TimeoutExpired(["powershell"], 20)
    with caplog.at_level(logging.ERROR, logger=LOG):
        assert um._verify_authenticode(tmp_path / "a.exe") == "unknown"
    k = _kayitlar(caplog, "Authenticode doğrulama başarısız", logging.ERROR)
    assert k and k[0].exc_info is not None


def test_authenticode_WINDOWS_DISI_unknown_surec_YOK(ota, tmp_path, monkeypatch):
    """os.name != 'nt' → 'unknown', PowerShell ÇAĞRILMAZ."""
    with monkeypatch.context() as m:
        m.setattr(os, "name", "posix")
        sonuc = um._verify_authenticode(tmp_path / "a.exe")
    assert sonuc == "unknown"
    assert ota.ps == []


# ── apply_update hata kolları ────────────────────────────────────────────────


def _apply_ortak_sonra(ota):
    assert ota.popen == [], f"installer BAŞLATILDI: {ota.popen}"
    assert um._applying is False and um._applying_since is None
    assert URL in ota.ag and all(ota.pinli[i] for i, u in enumerate(ota.ag) if u == URL), (
        "indirme pinli açıcıdan geçmedi"
    )


def test_apply_SHA_YOKSA_installer_BASLATILMAZ_AV_tutsa_da(ota):
    """manifest sha256 boş + indirilen dosya AV'de tutulu (silinemez) → sha256Yok iletisi; installer yok, guard serbest."""
    _yayinla(ota, sha="")
    ota.av_kilidi = True
    sonuc = um.apply_update()
    assert sonuc == {"ok": False, "error": ceviri.t("guncelleme.apply.sha256Yok")}
    _apply_ortak_sonra(ota)
    assert ota.tutamaklar, "aparat: AV tutamağı alınmadı"


def test_apply_SHA_UYUSMAZSA_installer_BASLATILMAZ_AV_tutsa_da(ota):
    """manifest sha256 başka → sha256Uyusmadi(beklenen[:12], gelen[:12]); installer yok, guard serbest."""
    yanlis = "ab" * 32
    _yayinla(ota, sha=yanlis)
    ota.av_kilidi = True
    sonuc = um.apply_update()
    assert sonuc == {
        "ok": False,
        "error": ceviri.t("guncelleme.apply.sha256Uyusmadi", beklenen=yanlis[:12], gelen=SHA[:12]),
    }
    _apply_ortak_sonra(ota)


@pytest.mark.parametrize("av", [False, True])
def test_apply_IMZA_KURCALANMISSA_installer_BASLATILMAZ_dosya_SILINIR(ota, av):
    """SHA doğru ama Authenticode HashMismatch → imzaGecersiz; installer yok; AV tutmuyorsa özel geçici dizin de silinir."""
    _yayinla(ota)
    ota.ps_cikti = "HashMismatch"
    ota.av_kilidi = av
    sonuc = um.apply_update()
    assert sonuc == {"ok": False, "error": ceviri.t("guncelleme.apply.imzaGecersiz")}
    _apply_ortak_sonra(ota)
    assert len(ota.ps) == 1
    if not av:
        assert ota.dizinler() == [], "kurcalanmış installer diskte KALDI"


def test_apply_INDIRME_SIRASINDA_tedavi_baslarsa_installer_BASLATILMAZ(ota, snapshot_sayaci):
    """ilk denetimde tedavi yok, indirme+imza sonrası ikinci denetimde aktif → indirmedeTedavi; installer yok, guard serbest."""
    _yayinla(ota)
    snapshot_sayaci["aktif_sonra"] = 1
    ota.av_kilidi = True
    sonuc = um.apply_update()
    assert sonuc == {"ok": False, "error": ceviri.t("guncelleme.apply.indirmedeTedavi")}
    _apply_ortak_sonra(ota)
    assert snapshot_sayaci["n"] == 2


# ── rollback hata kolları ────────────────────────────────────────────────────


def _onceki(url=ONCEKI_URL, sha=SHA):
    return {"version": "1.0.0", "installerUrl": url, "sha256": sha}


def test_rollback_GECERSIZ_URL_aga_CIKMADAN_reddedilir(ota):
    """previousStable installerUrl `http://…` → URL hatası (HTTPS değil); ağa installer isteği GİTMEZ; guard dokunulmaz."""
    _yayinla(ota, onceki=_onceki(url="http://github.com/mert61-python/pemf-update/x.exe"))
    sonuc = um.rollback()
    assert sonuc == {"ok": False, "error": ceviri.t("guncelleme.url.httpsDegil")}
    assert [u for u in ota.ag if not u.startswith(um._MANIFEST_URL)] == []
    assert um._applying is False


def test_rollback_GUARD_ZATEN_ACIKSA_reddedilir_guard_KORUNUR(ota, monkeypatch):
    """başka bir uygulama sürerken (bayrak açık) → zatenSuruyor; bayrak ve damgası DEĞİŞMEZ; indirme yok."""
    _yayinla(ota, onceki=_onceki())
    damga = time.monotonic()
    monkeypatch.setattr(um, "_applying", True)
    monkeypatch.setattr(um, "_applying_since", damga)
    sonuc = um.rollback()
    assert sonuc == {"ok": False, "error": ceviri.t("guncelleme.rollback.zatenSuruyor")}
    assert um._applying is True and um._applying_since == damga
    assert ONCEKI_URL not in ota.ag


def _rollback_ortak_sonra(ota):
    assert ota.popen == [], f"rollback installer'ı BAŞLATILDI: {ota.popen}"
    assert um._applying is False and um._applying_since is None
    assert ONCEKI_URL in ota.ag


def test_rollback_SHA_UYUSMAZSA_installer_BASLATILMAZ(ota):
    """previousStable sha256 başka → rollback.sha256Uyusmadi(beklenen[:12]); installer yok (AV tutsa da)."""
    yanlis = "cd" * 32
    _yayinla(ota, onceki=_onceki(sha=yanlis))
    ota.av_kilidi = True
    sonuc = um.rollback()
    assert sonuc == {"ok": False, "error": ceviri.t("guncelleme.rollback.sha256Uyusmadi", beklenen=yanlis[:12])}
    _rollback_ortak_sonra(ota)


def test_rollback_IMZA_KURCALANMISSA_installer_BASLATILMAZ(ota):
    """SHA doğru, Authenticode NotTrusted → rollback.imzaGecersiz; installer yok (AV tutsa da)."""
    _yayinla(ota, onceki=_onceki())
    ota.ps_cikti = "NotTrusted"
    ota.av_kilidi = True
    sonuc = um.rollback()
    assert sonuc == {"ok": False, "error": ceviri.t("guncelleme.rollback.imzaGecersiz")}
    _rollback_ortak_sonra(ota)


def test_rollback_INDIRME_SIRASINDA_tedavi_baslarsa_installer_BASLATILMAZ(ota, snapshot_sayaci):
    """ilk denetim tedavi yok, Popen öncesi ikinci denetim aktif → rollback.indirmedeTedavi; installer yok."""
    _yayinla(ota, onceki=_onceki())
    snapshot_sayaci["aktif_sonra"] = 1
    ota.av_kilidi = True
    sonuc = um.rollback()
    assert sonuc == {"ok": False, "error": ceviri.t("guncelleme.rollback.indirmedeTedavi")}
    _rollback_ortak_sonra(ota)
    assert snapshot_sayaci["n"] == 2


# ── Denetleyici döngüsü ──────────────────────────────────────────────────────


def test_denetleyici_CANLIYKEN_ikinci_kez_BASLAMAZ(monkeypatch):
    """kanal açık + denetleyici iş parçacığı canlı → start_update_checker yeni iş parçacığı KURMAZ (aynı nesne kalır)."""
    monkeypatch.setenv("PEMF_LEGACY_EXE_UPDATE", "1")
    dur = threading.Event()
    canli = threading.Thread(target=dur.wait, daemon=True, name="kp-sahte-denetleyici")
    canli.start()
    try:
        monkeypatch.setattr(um, "_check_thread", canli)
        sayi = threading.active_count()
        um.start_update_checker(interval_sec=5)
        assert um._check_thread is canli
        assert threading.active_count() == sayi
    finally:
        dur.set()
        canli.join(5)


class _SahteOlay:
    """`_stop` yerine: bekleme süresini kaydeder, BEKLEMEZ; ikinci `is_set` True (tek tur)."""

    def __init__(self):
        self.bekleme: list = []
        self._n = 0

    def clear(self):
        pass

    def set(self):
        self._n = 99

    def wait(self, t=None):
        self.bekleme.append(t)
        return False

    def is_set(self):
        self._n += 1
        return self._n > 1


def test_denetleyici_SUPURME_HATASI_donguyu_OLDURMEZ_yeni_surum_GUNLUGE(ota, monkeypatch, caplog):
    """açılış süpürmesi OSError → debug kaydı, döngü sürer: manifest okunur, 'Yeni backend sürümü mevcut: 999.0.0' info; bekleme 20 sn + aralık."""
    ota.manifest = {"version": "999.0.0", "installerUrl": URL, "sha256": SHA}
    olay = _SahteOlay()
    monkeypatch.setattr(um, "_stop", olay)
    monkeypatch.setattr(um, "_check_thread", None)

    def _supurme():
        raise OSError("gecici kok okunamadi")

    monkeypatch.setattr(um, "sweep_stale_update_temp", _supurme)
    with caplog.at_level(logging.DEBUG, logger=LOG):
        um.start_update_checker(interval_sec=7)
        t = um._check_thread
        assert t is not None
        t.join(10)
        assert not t.is_alive()
    assert olay.bekleme == [20, 7]
    assert [u for u in ota.ag if u.startswith(um._MANIFEST_URL)], "döngü manifest okumadı"
    assert _kayitlar(caplog, "acilis gecici-dizin suepuermesi hatasi", logging.DEBUG)
    assert _kayitlar(caplog, "Yeni backend sürümü mevcut: 999.0.0", logging.INFO)
