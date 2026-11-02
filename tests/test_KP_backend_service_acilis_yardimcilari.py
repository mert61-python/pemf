# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/backend_service.py · sözleşmeler: modül başı kapıları (depo kökü, şifreli yükleyici, pip / dış ağ
kapısı yedeği), günlük biçimleyici + `_configure_logging` (JSON / konsol / yedek dizin), çökme kancası, ortam portu, sır
dosyası ACL kilidi, ağ paylaşımı uyarısı, eşleştirme kodu maskesi, DB hazırlığı, API bağlantısı (mandal diskten), Supabase
kimliği, bulut eşitleme / DB bakımı / tünel / güncelleme denetleyicisi başlatıcıları, oturum yoklaması, hotspot betiği ve
başlatıcısı, AI ısıtma, donanım güncellemesi kararı.

Sahteler EN ALT katta: süreç (`subprocess.run`, `file_acl.subprocess`), platform (`ctypes.windll`, modülün `os` adı), kasa
(`secrets_manager.get_secret` / `secrets_path`), saat yok; ağ / iş parçacığı başlatan alt sistem girişleri (bulut eşitleme,
tünel bekçisi, güncelleme denetleyicisi, DB bakımı, firmware manifest denetimi, ağır AI içe aktarımı) gerçek imzalarına uyan
kaydedicilerle değiştirilir — gerçekleri ağa / donanıma çıkar.
"""

from __future__ import annotations

import importlib.util
import io
import json
import logging
import os
import pathlib
import subprocess
import sys
import threading
import types
import wave
from collections import Counter
from pathlib import Path

import backend_service as bs
import pytest

# ── ortak aparat ──────────────────────────────────────────────────────────────────────────────────────────────────────


class _Toplayici(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.kayitlar: list[logging.LogRecord] = []

    def emit(self, record):
        self.kayitlar.append(record)

    def metinler(self, duzey: int | None = None) -> list[str]:
        out = []
        for r in self.kayitlar:
            if duzey is not None and r.levelno != duzey:
                continue
            try:
                out.append(r.getMessage())
            except Exception:
                out.append(str(r.msg))
        return out


_SAYAC = {"n": 0}


def _gunlukcu(ad: str):
    _SAYAC["n"] += 1
    lg = logging.getLogger(f"kp_bs_acilis.{ad}.{_SAYAC['n']}")
    lg.handlers[:] = []
    h = _Toplayici()
    lg.addHandler(h)
    lg.setLevel(logging.DEBUG)
    lg.propagate = False
    return lg, h


class _SatirIciThread(threading.Thread):
    """Gerçek Thread kurucusu (imza doğrulaması korunur); `start` işi SATIR İÇİ koşar → test bitince canlı iş parçacığı yok."""

    def start(self):
        self.run()


def _env_gecici(monkeypatch, ad: str) -> None:
    """Değişken yoksa da çıkışta YOK hâline dönsün (önce setenv, sonra delenv — conftest PEMF_ sızıntı kapısı)."""
    monkeypatch.setenv(ad, "kp-gecici")
    monkeypatch.delenv(ad)


def _taze_yukle(ad: str):
    """backend_service kaynağını sys.modules'e KOYMADAN yeni bir modül nesnesinde yürütür (modül başı satırları için)."""
    spec = importlib.util.spec_from_file_location(ad, bs.__file__)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _SahteKernel32:
    def __init__(self, oturum: int = 1, sonuc: int = 1, patla: bool = False):
        self.oturum, self.sonuc, self.patla = oturum, sonuc, patla
        self.cagri: list = []

    def GetCurrentProcessId(self):
        if self.patla:
            raise OSError("kernel32 yok")
        self.cagri.append("pid")
        return 4242

    def ProcessIdToSessionId(self, pid, ref):
        self.cagri.append(("oturum", pid))
        ref._obj.value = self.oturum
        return self.sonuc


def _windll_sahte(monkeypatch, k32: _SahteKernel32) -> None:
    import ctypes

    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(kernel32=k32), raising=False)


class _OsVekili(types.ModuleType):
    """backend_service'in KENDİ `os` adı için vekil: yalnız verilen öznitelikler ezilir, gerisi gerçek `os`."""

    def __init__(self, **ezilen):
        super().__init__("os")
        self.__dict__.update(ezilen)

    def __getattr__(self, ad):
        return getattr(os, ad)


# ── modül başı ────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_depo_koku_sys_path_te_YOKSA_basa_eklenir(monkeypatch):
    """Depo kökü sys.path'te yokken modül yüklenir → kök sys.path'in BAŞINA eklenir (pemf_gui / ai_hub içe aktarılabilir)."""
    kok = bs._DEPO_KOKU
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != kok])
    assert kok not in sys.path
    mod = _taze_yukle("kp_bs_taze_yol")
    assert sys.path[0] == kok
    assert mod._DEPO_KOKU == kok


def test_kapilar_PATLARSA_modul_yine_yuklenir_dis_ag_degerleri_DOGRUDAN_yazilir(monkeypatch):
    """Şifreli yükleyici, pip yasağı ve dış-ağ kapısı istisna atarsa → modül yine yüklenir (main çağrılabilir) ve
    YOLO_OFFLINE=true + NO_ALBUMENTATIONS_UPDATE=1 doğrudan yazılır (gizlilik kilidi sessizce düşmez)."""
    import utils.encrypted_import as ei
    import utils.runtime_guards as rg

    cagri: list[str] = []

    def _patlayan(ad):
        def _f(*a, **k):
            cagri.append(ad)
            raise RuntimeError(f"kp: {ad} kurulamadı")

        return _f

    monkeypatch.setattr(ei, "install", _patlayan("yukleyici"))
    monkeypatch.setattr(rg, "pip_kurulumunu_yasakla", _patlayan("pip"))
    monkeypatch.setattr(rg, "dis_ag_cagrilarini_kapat", _patlayan("dis_ag"))
    monkeypatch.setenv("YOLO_OFFLINE", "false")
    monkeypatch.setenv("NO_ALBUMENTATIONS_UPDATE", "0")
    mod = _taze_yukle("kp_bs_taze_kapi")
    assert cagri == ["yukleyici", "pip", "dis_ag"]
    assert os.environ["YOLO_OFFLINE"] == "true"
    assert os.environ["NO_ALBUMENTATIONS_UPDATE"] == "1"
    assert callable(mod.main) and mod._VARSAYILAN_PORT == 8000


# ── günlük ────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_duz_bicimleyici_istek_kimligi_OKUNAMAZSA_tire_yazar(monkeypatch):
    """`get_request_id` istisna atarsa → satırdaki [rid] alanı '-' olur (günlük satırı düşmez)."""
    import utils.request_context as rc

    def _patla():
        raise LookupError("bağlam yok")

    monkeypatch.setattr(rc, "get_request_id", _patla)
    f = bs._PlainLogFormatter("%(rid)s|%(levelname)s|%(message)s")
    r = logging.LogRecord("kp", logging.WARNING, __file__, 1, "olay %s", ("x",), None)
    assert f.format(r) == "-|WARNING|olay x"


@pytest.fixture
def gunluk_ortami(monkeypatch, tmp_path):
    """`logging.basicConfig` kaydedilir (kök günlükçü değişmez); konsol akışları sahte; günlük dizini tmp."""
    yakalanan: dict = {}
    monkeypatch.setattr(logging, "basicConfig", lambda **k: yakalanan.update(k))
    monkeypatch.setenv("PEMF_LOG_DIR", str(tmp_path / "gunluk"))
    monkeypatch.delenv("PEMF_LOG_JSON", raising=False)
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    yield yakalanan
    for h in yakalanan.get("handlers") or []:
        h.close()


def test_PEMF_LOG_JSON_1_dosyaya_JSON_satir_yazar(gunluk_ortami, monkeypatch, tmp_path):
    """PEMF_LOG_JSON=1 → dosya işleyicisi JSON biçimleyici taşır; yazılan satır `msg`/`level`/`logger` alanlı JSON'dur."""
    monkeypatch.setenv("PEMF_LOG_JSON", "1")
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    bs._configure_logging(tmp_path, "warning")
    hs = gunluk_ortami["handlers"]
    assert gunluk_ortami["level"] == logging.WARNING and gunluk_ortami["force"] is True
    assert len(hs) == 1 and isinstance(hs[0].formatter, bs._JsonLogFormatter)
    hs[0].handle(logging.LogRecord("kp.json", logging.ERROR, __file__, 1, "olay %s", ("x",), None))
    hs[0].flush()
    satir = (tmp_path / "gunluk" / "backend_service.log").read_text(encoding="utf-8").strip().splitlines()[-1]
    d = json.loads(satir)
    assert (d["msg"], d["level"], d["logger"]) == ("olay x", "ERROR", "kp.json")


def test_konsol_isatty_PATLARSA_yalniz_dosya_isleyicisi(gunluk_ortami, monkeypatch, tmp_path):
    """`sys.stdout.isatty()` istisna atarsa → etkileşimsiz sayılır: kök günlükçüye YALNIZ dönen dosya işleyicisi verilir."""

    class _BozukKonsol(io.StringIO):
        def isatty(self):
            raise ValueError("I/O operation on closed file")

    monkeypatch.setattr(sys, "stdout", _BozukKonsol())
    bs._configure_logging(tmp_path, "INFO")
    hs = gunluk_ortami["handlers"]
    assert [type(h).__name__ for h in hs] == ["RotatingFileHandler"]


def test_GERCEK_konsolda_ikinci_isleyici_KONSOLA_duz_metin_yazar(gunluk_ortami, monkeypatch, tmp_path):
    """Etkileşimli konsol + donmuş değil → ikinci işleyici konsola düz biçimde (`[rid]` alanlı) yazar."""

    class _Konsol(io.StringIO):
        def isatty(self):
            return True

    konsol = _Konsol()
    monkeypatch.setattr(sys, "stdout", konsol)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    bs._configure_logging(tmp_path, "DEBUG")
    hs = gunluk_ortami["handlers"]
    assert len(hs) == 2 and hs[1].stream is konsol
    assert isinstance(hs[1].formatter, bs._PlainLogFormatter)
    hs[1].handle(logging.LogRecord("kp.konsol", logging.INFO, __file__, 1, "merhaba konsol", None, None))
    assert "INFO [kp.konsol] [-] merhaba konsol" in konsol.getvalue()


def test_DONMUS_surecte_konsol_isleyicisi_EKLENMEZ(gunluk_ortami, monkeypatch, tmp_path):
    """Etkileşimli görünse de donmuş (frozen) süreç → konsol işleyicisi eklenmez (drenajsız boru kilitlenmesi)."""

    class _Konsol(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdout", _Konsol())
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    bs._configure_logging(tmp_path, "INFO")
    assert [type(h).__name__ for h in gunluk_ortami["handlers"]] == ["RotatingFileHandler"]


def test_gunluk_ve_YEDEK_dizin_acilamazsa_OZGUN_hata_yukselir(monkeypatch, tmp_path):
    """Günlük dizini de geçici yedek dizin de oluşturulamazsa → ÖZGÜN (asıl dizinin) OSError yükselir, yedeğinki değil."""
    import tempfile

    engel = tmp_path / "asil_dosya"
    engel.write_text("dizin yerine dosya", encoding="utf-8")
    yedek_engel = tmp_path / "gecici_dosya"
    yedek_engel.write_text("dizin yerine dosya", encoding="utf-8")
    monkeypatch.setenv("PEMF_LOG_DIR", str(engel / "logs"))
    monkeypatch.delenv("PEMF_LOG_JSON", raising=False)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(yedek_engel))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(logging, "basicConfig", lambda **k: pytest.fail("işleyici kurulmamalıydı"))
    with pytest.raises(OSError) as hata:
        bs._configure_logging(tmp_path, "INFO")
    assert Path(hata.value.filename) == engel
    assert hata.value.__cause__ is None and hata.value.__suppress_context__ is True


# ── çökme kancası ─────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def kancalar(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    ozgun: list = []
    monkeypatch.setattr(sys, "__excepthook__", lambda t, v, tb: ozgun.append(t))
    monkeypatch.setenv("PEMF_LOG_DIR", str(tmp_path / "lg"))
    return ozgun


def _istisna(tur, metin):
    try:
        raise tur(metin)
    except tur:
        return sys.exc_info()


def test_cokme_kancasi_ANA_istisnayi_crash_loga_ve_CRITICAL_e_yazar(kancalar, tmp_path, caplog):
    """Ana iş parçacığında yakalanmamış istisna → crash.log'a `===== CRASH [main]` + iz, günlüğe CRITICAL; özgün kanca da çağrılır."""
    bs._install_crash_handler(tmp_path)
    et, ev, tb = _istisna(ValueError, "kp-cokme-1")
    with caplog.at_level(logging.CRITICAL, logger="backend_service"):
        sys.excepthook(et, ev, tb)
    metin = (tmp_path / "lg" / "crash.log").read_text(encoding="utf-8")
    assert "===== CRASH [main]" in metin and "ValueError: kp-cokme-1" in metin
    assert kancalar == [ValueError]
    assert any(
        r.levelno == logging.CRITICAL and "YAKALANMAMIS ISTISNA (main)" in r.getMessage() for r in caplog.records
    )


def test_cokme_kancasi_KeyboardInterrupt_KAYDETMEZ_ozgune_iletir(kancalar, tmp_path):
    """KeyboardInterrupt → crash.log YAZILMAZ (operatör Ctrl+C'si çökme değil), yalnız özgün kanca çağrılır."""
    bs._install_crash_handler(tmp_path)
    sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    assert not (tmp_path / "lg" / "crash.log").exists()
    assert kancalar == [KeyboardInterrupt]


def test_cokme_kancasi_IS_PARCACIGI_istisnasini_adiyla_yazar(kancalar, tmp_path):
    """İş parçacığında yakalanmamış istisna → crash.log'a `CRASH [thread:<ad>]` + istisna metni."""
    bs._install_crash_handler(tmp_path)
    threading.excepthook(
        types.SimpleNamespace(
            exc_type=RuntimeError,
            exc_value=RuntimeError("kp-isci-patladi"),
            exc_traceback=None,
            thread=types.SimpleNamespace(name="isci-7"),
        )
    )
    metin = (tmp_path / "lg" / "crash.log").read_text(encoding="utf-8")
    assert "===== CRASH [thread:isci-7]" in metin and "RuntimeError: kp-isci-patladi" in metin


def test_cokme_kancasi_crash_log_YAZILAMAZSA_yine_CRITICAL(kancalar, monkeypatch, tmp_path, caplog):
    """crash.log dizini oluşturulamazsa → kanca düşmez, CRITICAL günlük kaydı yine yazılır."""
    engel = tmp_path / "engel"
    engel.write_text("dosya", encoding="utf-8")
    monkeypatch.setenv("PEMF_LOG_DIR", str(engel / "lg"))
    bs._install_crash_handler(tmp_path)
    et, ev, tb = _istisna(KeyError, "kp-anahtar")
    with caplog.at_level(logging.CRITICAL, logger="backend_service"):
        sys.excepthook(et, ev, tb)
    assert any("YAKALANMAMIS ISTISNA (main)" in r.getMessage() for r in caplog.records)
    assert kancalar == [KeyError]


def test_cokme_kancasi_threading_kancasi_ATANAMAZSA_ana_kanca_yine_kurulur(kancalar, monkeypatch, tmp_path):
    """`threading.excepthook` ataması düşerse → kurulum istisna atmaz ve ana (sys) kanca yine kurulur."""
    once = sys.excepthook

    class _SaltOkuThreading(types.ModuleType):
        def __getattr__(self, ad):
            return getattr(threading, ad)

        def __setattr__(self, ad, deger):
            if ad == "excepthook":
                raise AttributeError("salt okunur")
            super().__setattr__(ad, deger)

    monkeypatch.setitem(sys.modules, "threading", _SaltOkuThreading("threading"))
    bs._install_crash_handler(tmp_path)
    assert sys.modules["threading"] is not threading
    monkeypatch.setitem(sys.modules, "threading", threading)
    assert sys.excepthook is not once and sys.excepthook.__name__ == "_sys_hook"


# ── port ──────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_ortam_portu_DEGISKEN_YOKSA_8000_uyarisiz(monkeypatch):
    """PEMF_API_PORT tanımsız → (8000, None)."""
    monkeypatch.delenv("PEMF_API_PORT", raising=False)
    assert bs.ortam_portu() == (8000, None)


# ── sır dosyası ACL kilidi ────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def icacls(monkeypatch):
    """`file_acl`'ın KENDİ subprocess adı: icacls çağrıları kaydedilir (gerçek ACL değişmez)."""
    import utils.file_acl as fa

    kayit = {"cagri": [], "patla": False}

    def _run(args, **k):
        kayit["cagri"].append(list(args))
        if kayit["patla"]:
            raise subprocess.CalledProcessError(5, args, b"", b"Access is denied.")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(
        fa,
        "subprocess",
        types.SimpleNamespace(run=_run, CREATE_NO_WINDOW=0x08000000, CalledProcessError=subprocess.CalledProcessError),
    )
    return kayit


def test_ACL_her_sir_dosyasi_BIR_kez_surec_hesabi_KORUNARAK_kilitlenir(icacls, monkeypatch, tmp_path):
    """Sır yolları + sabit adlar + `*.plain.bak*` → var olan her dosya için icacls TAM BİR kez (aynı yol iki kaynaktan
    gelse de) ve süreç hesabına ek ACE ile (keep_current_user); özet INFO dosya sayısını söyler."""
    import servers.auth as auth
    import utils.secrets_manager as sm

    app = tmp_path / "veri"
    app.mkdir()
    for ad in (".sqlcipher_key", "pemf_secrets.json", "api_token.txt", "patients.db.plain.bak", "x.db.plain.bak.2026"):
        (app / ad).write_text("gizli", encoding="utf-8")
    monkeypatch.setattr(sm, "secrets_path", lambda: app / "pemf_secrets.json")
    monkeypatch.setattr(auth, "_token_file", lambda: app / "API_TOKEN.TXT")
    lg, h = _gunlukcu("acl_tam")
    bs._harden_secret_file_acls(app, lg)
    sayim = Counter(c[1].lower() for c in icacls["cagri"])
    beklenen = {
        str(app / a).lower()
        for a in (
            ".sqlcipher_key",
            "pemf_secrets.json",
            "api_token.txt",
            "patients.db.plain.bak",
            "x.db.plain.bak.2026",
        )
    }
    assert set(sayim) == beklenen and set(sayim.values()) == {1}
    for c in icacls["cagri"]:
        assert c.count("/grant:r") >= 3, f"süreç hesabı ACE'i yok (keep_current_user düştü): {c}"
    assert any("5 dosya" in m for m in h.metinler(logging.INFO))
    assert not h.metinler(logging.ERROR)


def test_ACL_yol_kaynaklari_PATLARSA_sabit_adaylar_yine_kilitlenir(icacls, monkeypatch, tmp_path):
    """`secrets_path`, `_token_file` ve `*.plain.bak*` taraması istisna atarsa → sabit adlı var olan dosyalar yine kilitlenir."""
    import servers.auth as auth
    import utils.secrets_manager as sm

    def _patla(*a, **k):
        raise PermissionError(13, "erişim yok")

    class _TaramasizYol(type(Path())):
        def glob(self, desen):
            raise OSError("dizin okunamadı")

    app = _TaramasizYol(tmp_path / "veri2")
    app.mkdir()
    (app / ".pemf_key_v2").write_text("k", encoding="utf-8")
    (app / "patients.db.plain.bak").write_text("pii", encoding="utf-8")
    monkeypatch.setattr(sm, "secrets_path", _patla)
    monkeypatch.setattr(auth, "_token_file", _patla)
    lg, h = _gunlukcu("acl_kaynak")
    bs._harden_secret_file_acls(app, lg)
    kilitlenen = [Path(c[1]).name for c in icacls["cagri"]]
    assert kilitlenen == [".pemf_key_v2"]
    assert any("1 dosya" in m for m in h.metinler(logging.INFO))


def test_ACL_icacls_DUSERSE_var_olan_dosya_BASARISIZ_islenemeyen_aday_UYARI(icacls, monkeypatch, tmp_path):
    """icacls hata verirse VAR olan dosya başarısız sayılır (yok olan sayılmaz); işlenemeyen aday WARNING ile başarısız
    sayılır → ERROR özet doğru sayıyı (2) ve YAPILACAK'ı söyler; hiçbir dosya 'kilitlendi' sayılmaz."""
    import servers.auth as auth
    import utils.secrets_manager as sm

    class _BozukYol:
        def __str__(self):
            raise UnicodeEncodeError("utf-8", "x", 0, 1, "kodlanamadı")

    app = tmp_path / "veri3"
    app.mkdir()
    (app / ".sqlcipher_key").write_text("k", encoding="utf-8")
    monkeypatch.setattr(sm, "secrets_path", lambda: _BozukYol())
    monkeypatch.setattr(auth, "_token_file", lambda: app / "yok_token.txt")
    icacls["patla"] = True
    lg, h = _gunlukcu("acl_dusus")
    bs._harden_secret_file_acls(app, lg)
    uyarilar = [r for r in h.kayitlar if r.levelno == logging.WARNING]
    assert any("Sir dosyasi ACL kilidi uygulanamadi" in str(r.msg) for r in uyarilar)
    hatalar = h.metinler(logging.ERROR)
    assert len(hatalar) == 1 and hatalar[0].startswith("2 sir dosyasinin ACL kilidi UYGULANAMADI")
    assert "YAPILACAK" in hatalar[0]
    assert not h.metinler(logging.INFO)


def test_ACL_kilit_yardimcisi_YOKSA_hicbir_sey_denenmez(icacls, monkeypatch, tmp_path):
    """`utils.file_acl.lock_down_file` içe aktarılamazsa → sessizce döner: icacls çağrısı ve günlük kaydı YOK."""
    import utils.file_acl as fa

    monkeypatch.delattr(fa, "lock_down_file")
    app = tmp_path / "veri4"
    app.mkdir()
    (app / ".sqlcipher_key").write_text("k", encoding="utf-8")
    lg, h = _gunlukcu("acl_yok")
    bs._harden_secret_file_acls(app, lg)
    assert icacls["cagri"] == [] and h.kayitlar == []


# ── ağ paylaşımı · eşleştirme · DB · API bağlantısı ───────────────────────────────────────────────────────────────────


def test_veri_koku_UNC_ise_UYARIR_True(tmp_path):
    """Veri kökü UNC (\\\\sunucu\\pay) → True ve 'ağ paylaşımında' WARNING (yol günlükte)."""
    lg, h = _gunlukcu("unc")
    yol = Path(r"\\kp-sunucu\pay\PEMF_GUI")
    assert bs._veri_koku_ag_uyarisi(yol, lg) is True
    uyari = h.metinler(logging.WARNING)
    assert len(uyari) == 1 and "ağ paylaşımında" in uyari[0] and "kp-sunucu" in uyari[0]


def test_veri_koku_YEREL_ise_uyarmaz_False(tmp_path):
    """Yerel sabit diskteki veri kökü → False, uyarı yok."""
    lg, h = _gunlukcu("yerel")
    assert bs._veri_koku_ag_uyarisi(tmp_path, lg) is False
    assert not h.metinler(logging.WARNING)


def test_veri_koku_denetimi_PATLARSA_False_ve_DEBUG(tmp_path):
    """Yol metne çevrilemezse (denetim istisnası) → False, yalnız DEBUG kaydı (açılış durmaz)."""

    class _Bozuk:
        def __str__(self):
            raise ValueError("yol bozuk")

    lg, h = _gunlukcu("bozuk_kok")
    assert bs._veri_koku_ag_uyarisi(_Bozuk(), lg) is False
    assert [r.levelno for r in h.kayitlar] == [logging.DEBUG]
    assert "veri koku konum denetimi yapilamadi" in h.kayitlar[0].getMessage()


def test_eslestirme_kodu_MASKELI_cihaz_kimligi_ACIK_loglanir():
    """Kayıtlı eşleştirme kodu K7M2PQ → günlükte yalnız 'K*****' (tam kod hiçbir satırda yok), cihaz kimliği açık yazılır."""
    from utils.path_utils import get_app_data_directory

    d = get_app_data_directory()
    (d / "pairing_code.txt").write_text("K7M2PQ", encoding="utf-8")
    (d / "device_id.txt").write_text("kp-cihaz-77", encoding="utf-8")
    lg, h = _gunlukcu("eslestirme")
    bs._log_pairing_info(lg)
    metin = "\n".join(h.metinler())
    assert "EŞLEŞTİRME KODU: K***** " in metin and "Cihaz Kimliği: kp-cihaz-77" in metin
    assert "K7M2PQ" not in metin


def test_eslestirme_kodu_OKUNAMAZSA_hata_loglanir_istisna_kacmaz(monkeypatch, tmp_path):
    """Veri kökü açılamazsa (PEMF_DATA_DIR bir dosya) → 'Eşleştirme kodu loglanamadı' ERROR + iz; istisna kaçmaz."""
    engel = tmp_path / "kok_dosya"
    engel.write_text("x", encoding="utf-8")
    monkeypatch.setenv("PEMF_DATA_DIR", str(engel))
    lg, h = _gunlukcu("eslestirme_hata")
    bs._log_pairing_info(lg)
    hatalar = [r for r in h.kayitlar if r.levelno == logging.ERROR]
    assert len(hatalar) == 1 and "Eşleştirme kodu loglanamadı" in hatalar[0].getMessage() and hatalar[0].exc_info


def test_db_hazirligi_PATLARSA_loglanir_acilis_surer(monkeypatch, tmp_path):
    """`initialize_database` istisna atarsa → 'Database initialization failed' ERROR + iz; istisna kaçmaz."""
    engel = tmp_path / "kok_dosya2"
    engel.write_text("x", encoding="utf-8")
    monkeypatch.setenv("PEMF_DATA_DIR", str(engel))
    lg, h = _gunlukcu("db_hata")
    bs._initialize_database_safe(lg)
    hatalar = [r for r in h.kayitlar if r.levelno == logging.ERROR]
    assert len(hatalar) == 1 and "Database initialization failed" in hatalar[0].getMessage() and hatalar[0].exc_info


def test_db_hazirligi_SAGLAMSA_kayit_yok(monkeypatch, tmp_path):
    """Sağlam (izole) veri kökünde yarım göç artığı (`patients.db` YOK + `patients.db.plain.bak` VAR) → DB hazırlığı GERÇEKTEN
    koşar: artık geri konur (`patients.db` aynı içerikle döner, `.plain.bak` kalmaz); istisna kaçmaz, ERROR kaydı yok.
    (KP1-IC.6: eskiden yalnız "ERROR yok" ölçülüyordu — `initialize_database()` hiç çağrılmasa da yeşildi.)"""
    from utils import path_utils

    (tmp_path / "saglam_kok").mkdir()
    monkeypatch.setenv("PEMF_DATA_DIR", str(tmp_path / "saglam_kok"))
    monkeypatch.setattr(path_utils, "_GOC_YAPILDI", set(path_utils._GOC_YAPILDI))
    kok = path_utils.get_app_data_directory()  # ürünün çözdüğü veri dizini (PEMF_DATA_DIR altında)
    assert tmp_path in kok.parents or kok == tmp_path / "saglam_kok", f"aparat: veri dizini tmp dışında {kok}"
    assert not (kok / "patients.db").exists()
    artik = kok / "patients.db.plain.bak"
    artik.write_bytes(b"kp-hasta-verisi-yarim-goc")
    lg, h = _gunlukcu("db_saglam")
    bs._initialize_database_safe(lg)
    assert not [r for r in h.kayitlar if r.levelno >= logging.ERROR]
    assert (kok / "patients.db").is_file(), "DB hazırlığı yarım göç toparlamasını çağırmadı (patients.db geri konmadı)"
    assert (kok / "patients.db").read_bytes() == b"kp-hasta-verisi-yarim-goc"
    assert not artik.exists()


@pytest.fixture
def api_durum(monkeypatch):
    from servers import api_server as api

    monkeypatch.setattr(api.state, "core", api.state.core)
    monkeypatch.setattr(api.state, "hardware", api.state.hardware)
    monkeypatch.setattr(api, "_event_bus_registered", True)
    yield api
    hw = api.state.hardware
    if hw is not None and getattr(hw, "_keep_alive_thread", None) is not None:
        hw.stop()
        hw._keep_alive_thread.join(timeout=3)


def test_API_baglantisi_cekirdek_HC_ve_DISKTEKI_mandali_kurar(api_durum, tmp_path):
    """Çekirdek bağlanınca → api.state.core = çekirdek, api.state.hardware = o çekirdeği saran HardwareController ve
    veri kökündeki KURULU ACİL DURDUR mandalı START kabulünden önce yüklenir (mandallı)."""
    from controllers.hardware_controller import HardwareController
    from utils import estop_mandali

    (tmp_path / "estop_mandali.json").write_text(json.dumps({"aktif": True, "neden": "kp_onceki"}), encoding="utf-8")
    cekirdek = types.SimpleNamespace(app_data_dir=str(tmp_path))
    donen = bs._wire_api_server(cekirdek)
    api = api_durum
    assert donen is api and api.state.core is cekirdek
    assert isinstance(api.state.hardware, HardwareController) and api.state.hardware.core is cekirdek
    assert estop_mandali.mandalli_mi() is True
    assert estop_mandali.durum()["neden"].endswith("kp_onceki")


def test_API_baglantisi_mandal_kaliciligi_KURULAMAZSA_baglanti_surer(api_durum, caplog):
    """Mandal dosya yolu kurulamazsa (app_data_dir yok) → ERROR + iz, bağlantı yine tamamlanır (HC kurulur)."""
    from controllers.hardware_controller import HardwareController

    cekirdek = types.SimpleNamespace(app_data_dir=None)
    with caplog.at_level(logging.ERROR, logger="backend_service"):
        donen = bs._wire_api_server(cekirdek)
    assert donen is api_durum and isinstance(api_durum.state.hardware, HardwareController)
    assert any("ACIL DURDUR mandal kaliciligi kurulamadi" in r.getMessage() and r.exc_info for r in caplog.records)


# ── Supabase · bulut · bakım · tünel · güncelleme ─────────────────────────────────────────────────────────────────────


def test_supabase_kimligi_SIRDAN_okunursa_yapilandirmaya_BAKILMAZ(monkeypatch):
    """Kasa URL + anahtar verirse → aynen döner; pemf_gui.config hiç okunmaz."""
    import utils.secrets_manager as sm

    import pemf_gui.config as pc

    deger = {"supabase_url": "https://kp.ornek", "supabase_anon_key": "sb_publishable_kp"}
    monkeypatch.setattr(sm, "get_secret", lambda ad, *a, **k: deger.get(ad, ""))
    monkeypatch.setattr(pc, "get_config", lambda *a, **k: pytest.fail("yapılandırma okunmamalıydı"))
    assert bs._resolve_supabase_credentials() == ("https://kp.ornek", "sb_publishable_kp")


def test_supabase_kimligi_kasa_BOS_yapilandirma_PATLARSA_gomulu_varsayilan(monkeypatch):
    """Kasa boş + pemf_gui.config istisna → gömülü varsayılan URL ve anon anahtar."""
    import utils.secrets_manager as sm

    import pemf_gui.config as pc

    def _patla(*a, **k):
        raise OSError("config okunamadı")

    monkeypatch.setattr(sm, "get_secret", lambda ad, *a, **k: "")
    monkeypatch.setattr(pc, "get_config", _patla)
    assert bs._resolve_supabase_credentials() == (bs._DEFAULT_SUPABASE_URL, bs._DEFAULT_SUPABASE_ANON_KEY)


def test_bulut_esitleme_COZULEN_kimlikle_baslar_hata_DUSURMEZ(monkeypatch):
    """Bulut eşitleme → `init_cloud_sync(supabase_url, supabase_key)` çözülen kimlikle çağrılır + INFO; başlatıcı istisna
    atarsa ERROR + iz, istisna kaçmaz."""
    import servers.sync_worker as sw
    import utils.secrets_manager as sm

    deger = {"supabase_url": "https://kp.bulut", "supabase_anon_key": "sb_publishable_b"}
    monkeypatch.setattr(sm, "get_secret", lambda ad, *a, **k: deger.get(ad, ""))
    cagri: list = []
    monkeypatch.setattr(
        sw, "init_cloud_sync", lambda supabase_url, supabase_key: cagri.append((supabase_url, supabase_key))
    )
    lg, h = _gunlukcu("bulut")
    bs._start_cloud_sync(lg)
    assert cagri == [("https://kp.bulut", "sb_publishable_b")]
    assert h.metinler(logging.INFO) == ["Cloud sync + device registry started."]

    def _patla(supabase_url, supabase_key):
        raise ConnectionError("ağ yok")

    monkeypatch.setattr(sw, "init_cloud_sync", _patla)
    lg2, h2 = _gunlukcu("bulut_hata")
    bs._start_cloud_sync(lg2)
    assert [r.getMessage() for r in h2.kayitlar if r.levelno == logging.ERROR] == [
        "Cloud sync init failed (non-fatal)."
    ]
    assert not h2.metinler(logging.INFO)


def test_db_bakimi_CEKIRDEGIN_veri_koku_ile_baslar_hata_DUSURMEZ(monkeypatch, tmp_path):
    """DB bakımı → `start_headless_db_maintenance(core.app_data_dir)` + INFO; başlatıcı istisna → ERROR, istisna kaçmaz."""
    import services.headless_db_maintenance as hm

    cagri: list = []
    monkeypatch.setattr(hm, "start_headless_db_maintenance", lambda app_data_dir=None: cagri.append(app_data_dir))
    lg, h = _gunlukcu("bakim")
    bs._start_db_maintenance(types.SimpleNamespace(app_data_dir=tmp_path), lg)
    assert cagri == [tmp_path] and h.metinler(logging.INFO) == ["Headless DB maintenance started."]

    def _patla(app_data_dir=None):
        raise RuntimeError("bakım kurulamadı")

    monkeypatch.setattr(hm, "start_headless_db_maintenance", _patla)
    lg2, h2 = _gunlukcu("bakim_hata")
    bs._start_db_maintenance(types.SimpleNamespace(app_data_dir=tmp_path), lg2)
    assert [r.getMessage() for r in h2.kayitlar if r.levelno == logging.ERROR] == [
        "DB maintenance init failed (non-fatal)."
    ]


@pytest.fixture
def tunel(monkeypatch):
    import servers.auth as auth
    import servers.tunnel_manager as tm

    _env_gecici(monkeypatch, "PEMF_REQUIRE_AUTH")
    _env_gecici(monkeypatch, "PEMF_ENABLE_TUNNEL")
    monkeypatch.setattr(auth, "_require", auth._require)
    cagri: list = []
    monkeypatch.setattr(tm, "start_tunnel_watchdog", lambda port=8000, check_interval=20: cagri.append(port))
    return types.SimpleNamespace(auth=auth, tm=tm, cagri=cagri)


def test_tunel_KAPALIYKEN_hicbir_sey_yapilmaz(tunel):
    """PEMF_ENABLE_TUNNEL yok → bekçi başlamaz, PEMF_REQUIRE_AUTH değişmez."""
    lg, h = _gunlukcu("tunel_kapali")
    bs._maybe_start_tunnel(8123, lg)
    assert tunel.cagri == [] and "PEMF_REQUIRE_AUTH" not in os.environ and h.kayitlar == []


def test_tunel_ACIKKEN_kimlik_ZORLA_acilir_bekci_PORTLA_baslar(tunel, monkeypatch):
    """PEMF_ENABLE_TUNNEL=1, kimlik zorunluluğu kapalı → PEMF_REQUIRE_AUTH=1, auth önbelleği True, GÜVENLİK uyarısı ve
    tünel bekçisi gerçek portla başlar."""
    monkeypatch.setenv("PEMF_ENABLE_TUNNEL", "1")
    lg, h = _gunlukcu("tunel_acik")
    bs._maybe_start_tunnel(8123, lg)
    assert os.environ["PEMF_REQUIRE_AUTH"] == "1" and tunel.auth._require is True
    assert tunel.cagri == [8123]
    assert any("PEMF_REQUIRE_AUTH=1 ZORLA" in m for m in h.metinler(logging.WARNING))
    assert any("tunnel watchdog aktif" in m for m in h.metinler(logging.INFO))


def test_tunel_kimlik_ZATEN_aciksa_uyari_yok(tunel, monkeypatch):
    """PEMF_REQUIRE_AUTH=1 zaten → zorlama uyarısı YOK, auth önbelleğine dokunulmaz, bekçi başlar."""
    monkeypatch.setenv("PEMF_ENABLE_TUNNEL", "1")
    monkeypatch.setenv("PEMF_REQUIRE_AUTH", "1")
    monkeypatch.setattr(tunel.auth, "_require", None)
    lg, h = _gunlukcu("tunel_zaten")
    bs._maybe_start_tunnel(9001, lg)
    assert tunel.auth._require is None and tunel.cagri == [9001]
    assert not h.metinler(logging.WARNING)


def test_tunel_auth_modulu_YOKSA_ortam_yine_ZORLANIR(tunel, monkeypatch):
    """servers.auth içe aktarılamazsa → PEMF_REQUIRE_AUTH=1 yine yazılır ve GÜVENLİK uyarısı basılır."""
    import servers as servers_paketi

    monkeypatch.delattr(servers_paketi, "auth")
    monkeypatch.setitem(sys.modules, "servers.auth", None)
    lg, h = _gunlukcu("tunel_authsuz")
    bs._force_auth_for_tunnel(lg)
    assert os.environ["PEMF_REQUIRE_AUTH"] == "1"
    assert any("ZORLA" in m for m in h.metinler(logging.WARNING))


def test_tunel_bekcisi_PATLARSA_ERROR_istisna_kacmaz(tunel, monkeypatch):
    """Tünel bekçisi başlatılamazsa → 'Tunnel watchdog init failed' ERROR + iz; istisna kaçmaz."""
    monkeypatch.setenv("PEMF_ENABLE_TUNNEL", "1")

    def _patla(port=8000, check_interval=20):
        raise FileNotFoundError("cloudflared yok")

    monkeypatch.setattr(tunel.tm, "start_tunnel_watchdog", _patla)
    lg, h = _gunlukcu("tunel_hata")
    bs._maybe_start_tunnel(8123, lg)
    assert [r.getMessage() for r in h.kayitlar if r.levelno == logging.ERROR] == [
        "Tunnel watchdog init failed (non-fatal)."
    ]


def test_guncelleme_denetleyicisi_BASLAR_hata_DUSURMEZ(monkeypatch):
    """Güncelleme denetleyicisi bir kez başlatılır; başlatıcı istisna atarsa ERROR + iz, istisna kaçmaz."""
    import servers.update_manager as um

    cagri: list = []
    monkeypatch.setattr(um, "start_update_checker", lambda interval_sec=6 * 3600: cagri.append(interval_sec))
    lg, h = _gunlukcu("guncelleme")
    bs._start_update_checker_safe(lg)
    assert cagri == [6 * 3600] and h.kayitlar == []

    def _patla(interval_sec=0):
        raise RuntimeError("iş parçacığı açılamadı")

    monkeypatch.setattr(um, "start_update_checker", _patla)
    lg2, h2 = _gunlukcu("guncelleme_hata")
    bs._start_update_checker_safe(lg2)
    assert [r.getMessage() for r in h2.kayitlar if r.levelno == logging.ERROR] == [
        "Update checker init failed (non-fatal)."
    ]


# ── oturum · hotspot betiği · hotspot ─────────────────────────────────────────────────────────────────────────────────


def test_oturum_KULLANICI_oturumunda_True_SERVIS_oturumunda_False(monkeypatch):
    """Windows'ta ProcessIdToSessionId oturum 1 → True; oturum 0 (servis) → False; çağrı başarısız (0) → False;
    kernel32 istisna → False."""
    k = _SahteKernel32(oturum=1)
    _windll_sahte(monkeypatch, k)
    assert bs._oturum_var_mi() is True and k.cagri == ["pid", ("oturum", 4242)]
    _windll_sahte(monkeypatch, _SahteKernel32(oturum=0))
    assert bs._oturum_var_mi() is False
    _windll_sahte(monkeypatch, _SahteKernel32(oturum=3, sonuc=0))
    assert bs._oturum_var_mi() is False
    _windll_sahte(monkeypatch, _SahteKernel32(patla=True))
    assert bs._oturum_var_mi() is False


def test_oturum_WINDOWS_DISINDA_False(monkeypatch):
    """os.name 'posix' → False (kernel32'ye hiç dokunulmaz)."""
    k = _SahteKernel32(oturum=1)
    _windll_sahte(monkeypatch, k)
    monkeypatch.setattr(bs, "os", _OsVekili(name="posix"))
    assert bs._oturum_var_mi() is False and k.cagri == []


def test_hotspot_betigi_PAKETTEKI_varsa_o_doner(monkeypatch, tmp_path):
    """Paket kaynak yolundaki start_hotspot.ps1 varsa → o yol döner."""
    import utils.path_utils as pu

    betik = tmp_path / "paket" / "start_hotspot.ps1"
    betik.parent.mkdir()
    betik.write_text("# kp", encoding="utf-8")
    monkeypatch.setattr(pu, "packaged_resource_path", lambda *p: betik)
    assert bs._hotspot_betigi() == betik


def test_hotspot_betigi_paket_PATLARSA_EXE_yanindaki_doner(monkeypatch, tmp_path):
    """Paket yolu istisna atarsa → çalıştırılabilirin yanındaki start_hotspot.ps1 döner."""
    import utils.path_utils as pu

    def _patla(*p):
        raise RuntimeError("_MEIPASS yok")

    exe_dizin = tmp_path / "exe"
    exe_dizin.mkdir()
    (exe_dizin / "start_hotspot.ps1").write_text("# kp", encoding="utf-8")
    monkeypatch.setattr(pu, "packaged_resource_path", _patla)
    monkeypatch.setattr(sys, "executable", str(exe_dizin / "PEMF_Backend.exe"))
    assert bs._hotspot_betigi() == (exe_dizin / "start_hotspot.ps1").resolve()


def test_hotspot_betigi_HICBIRI_yoksa_ya_da_okunamazsa_None(monkeypatch, tmp_path):
    """Paket yolu okunamaz (erişim hatası), exe yolu çözülemez, kaynak yolu yok → None."""
    import utils.path_utils as pu

    paket = tmp_path / "erisilemez" / "start_hotspot.ps1"
    monkeypatch.setattr(pu, "packaged_resource_path", lambda *p: paket)
    monkeypatch.setattr(sys, "executable", None)
    gercek_is_file = pathlib.Path.is_file
    sorulan: list = []

    def _is_file(self):
        sorulan.append(self.name)
        if self == paket:
            raise PermissionError(13, "Erişim engellendi", str(self))
        return gercek_is_file(self)

    monkeypatch.setattr(pathlib.Path, "is_file", _is_file)
    assert bs._hotspot_betigi() is None
    assert sorulan == ["start_hotspot.ps1", "start_hotspot.ps1"]


@pytest.fixture
def hotspot(monkeypatch, tmp_path):
    """Kullanıcı oturumu (kernel32 sahte), paket betiği tmp'de, PowerShell çağrısı kaydedilir, iş parçacığı satır içi."""
    import utils.path_utils as pu

    monkeypatch.delenv("PEMF_HOTSPOT", raising=False)
    k = _SahteKernel32(oturum=1)
    _windll_sahte(monkeypatch, k)
    betik = tmp_path / "start_hotspot.ps1"
    betik.write_text("# kp", encoding="utf-8")
    paket_cagri: list = []
    monkeypatch.setattr(pu, "packaged_resource_path", lambda *p: paket_cagri.append(p) or betik)
    kayit = {"cagri": [], "sonuc": subprocess.CompletedProcess([], 0, "", ""), "patla": None}

    def _run(args, **kw):
        kayit["cagri"].append((list(args), kw))
        if kayit["patla"] is not None:
            raise kayit["patla"]
        return kayit["sonuc"]

    monkeypatch.setattr(subprocess, "run", _run)
    monkeypatch.setattr(threading, "Thread", _SatirIciThread)
    return types.SimpleNamespace(k32=k, betik=betik, kayit=kayit, paket_cagri=paket_cagri)


def test_hotspot_BASARILI_betik_GIZLI_PowerShell_ile_SSIDsiz_calisir(hotspot):
    """Kullanıcı oturumu + betik var → powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden
    -File <betik> (SSID / parola YOK), 120 sn zaman aşımı, pencere yok; rc=0 → 'PEMF-Gateway hazır' INFO."""
    lg, h = _gunlukcu("hotspot_ok")
    bs._start_hotspot_safe(lg)
    assert len(hotspot.kayit["cagri"]) == 1
    args, kw = hotspot.kayit["cagri"][0]
    assert args == [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(hotspot.betik),
    ]
    assert kw["timeout"] == 120 and kw["capture_output"] is True and kw["text"] is True
    assert kw["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert h.metinler(logging.INFO) == ["Hotspot: PEMF-Gateway hazır (ESP bobinleri bağlanabilir)."]


def test_hotspot_rc_SIFIR_DEGILSE_cikti_KUYRUGU_ile_uyari(hotspot):
    """Betik rc=1 + stderr → 'Hotspot başlatılamadı (rc=1): <stderr son 300 kr, kırpılmış>' WARNING; INFO yok."""
    hotspot.kayit["sonuc"] = subprocess.CompletedProcess([], 1, "", "  Hata: kablosuz bağdaştırıcı yok\n")
    lg, h = _gunlukcu("hotspot_rc")
    bs._start_hotspot_safe(lg)
    assert h.metinler(logging.WARNING) == ["Hotspot başlatılamadı (rc=1): Hata: kablosuz bağdaştırıcı yok"]
    assert not h.metinler(logging.INFO)


def test_hotspot_PowerShell_YOKSA_hata_loglanir_dusmez(hotspot):
    """powershell.exe başlatılamazsa (FileNotFoundError) → 'Hotspot başlatma hatası' ERROR + iz, istisna kaçmaz."""
    hotspot.kayit["patla"] = FileNotFoundError(2, "powershell.exe bulunamadı")
    lg, h = _gunlukcu("hotspot_yok")
    bs._start_hotspot_safe(lg)
    hatalar = [r for r in h.kayitlar if r.levelno == logging.ERROR]
    assert len(hatalar) == 1 and "Hotspot başlatma hatası" in hatalar[0].getMessage() and hatalar[0].exc_info


def test_hotspot_WINDOWS_DISINDA_hicbir_sey_denenmez(hotspot, monkeypatch):
    """os.name 'posix' → oturum yoklanmaz, betik aranmaz, PowerShell çağrılmaz, günlük yok."""
    monkeypatch.setattr(bs, "os", _OsVekili(name="posix"))
    lg, h = _gunlukcu("hotspot_posix")
    bs._start_hotspot_safe(lg)
    assert hotspot.k32.cagri == [] and hotspot.paket_cagri == [] and hotspot.kayit["cagri"] == [] and h.kayitlar == []


def test_hotspot_SERVIS_oturumunda_ATLANIR_betik_aranmaz(hotspot, monkeypatch):
    """Oturum 0 (servis) → 'başlatma ATLANDI' INFO; betik aranmaz, PowerShell çağrılmaz."""
    _windll_sahte(monkeypatch, _SahteKernel32(oturum=0))
    lg, h = _gunlukcu("hotspot_servis")
    bs._start_hotspot_safe(lg)
    assert hotspot.paket_cagri == [] and hotspot.kayit["cagri"] == []
    assert any("başlatma ATLANDI" in m for m in h.metinler(logging.INFO))


def test_hotspot_betik_YOKSA_uyari_PowerShell_cagrilmaz(hotspot, monkeypatch, tmp_path):
    """Betik hiçbir adayda yok → 'start_hotspot.ps1 bulunamadı' WARNING, PowerShell çağrılmaz."""
    import utils.path_utils as pu

    monkeypatch.setattr(pu, "packaged_resource_path", lambda *p: tmp_path / "yok" / "start_hotspot.ps1")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "yok2" / "python.exe"))
    lg, h = _gunlukcu("hotspot_betiksiz")
    bs._start_hotspot_safe(lg)
    assert hotspot.kayit["cagri"] == []
    assert any("start_hotspot.ps1 bulunamadı" in m for m in h.metinler(logging.WARNING))


# ── AI ısıtma ─────────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def isitma(monkeypatch):
    import utils.agir_import as ai

    monkeypatch.delenv("PEMF_AI_WARMUP", raising=False)
    monkeypatch.setattr(threading, "Thread", _SatirIciThread)
    kayit = {"ad": [], "wav": []}

    def _mel(yol):
        with wave.open(yol, "rb") as w:
            kayit["wav"].append((yol, w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()))
        return "mel"

    def _agir_import(ad):
        kayit["ad"].append(ad)
        return types.SimpleNamespace(audio_to_mel_image=_mel)

    monkeypatch.setattr(ai, "agir_import", _agir_import)
    return kayit


def test_isitma_MODELIN_on_islemesine_0_5_sn_22050_Hz_mono_WAV_verir_sonra_SILER(isitma):
    """Isıtma → ses modülü ağır içe aktarma kapısından alınır, `audio_to_mel_image` 0,5 sn / 22050 Hz / mono / 16-bit
    WAV ile çağrılır, 'AI ısıtma tamam' INFO yazılır ve geçici WAV silinir."""
    lg, h = _gunlukcu("isitma_ok")
    bs._start_ai_warmup_safe(lg)
    assert isitma["ad"] == ["ai_hub.inference_cat_sound.inference_cat_sound"]
    assert len(isitma["wav"]) == 1
    yol, kanal, genislik, hiz, kare = isitma["wav"][0]
    assert (kanal, genislik, hiz, kare) == (1, 2, 22050, 11025)
    assert not os.path.exists(yol), "geçici WAV silinmedi"
    assert any(m.startswith("AI ısıtma tamam (ses ön-işleme):") for m in h.metinler(logging.INFO))


def test_isitma_gecici_WAV_SILINEMEZSE_isitma_yine_TAMAM(isitma, monkeypatch):
    """Geçici WAV silinemezse (OSError) → istisna kaçmaz, 'AI ısıtma tamam' yine yazılır."""
    silinen: list = []

    def _silinemez(yol):
        silinen.append(yol)
        raise PermissionError(32, "dosya kullanımda")

    monkeypatch.setattr(bs, "os", _OsVekili(remove=_silinemez))
    lg, h = _gunlukcu("isitma_silinemez")
    try:
        bs._start_ai_warmup_safe(lg)
        assert len(silinen) == 1 and silinen[0] == isitma["wav"][0][0]
        assert any(m.startswith("AI ısıtma tamam") for m in h.metinler(logging.INFO))
    finally:
        for yol in silinen:
            if os.path.exists(yol):
                os.remove(yol)


# ── donanım güncellemesi kararı ───────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def firmware(monkeypatch):
    import servers.firmware_manager as fm

    monkeypatch.delenv("PEMF_FW_AUTO_UPDATE", raising=False)
    kayit: list = []

    def _acilis_denetimi(firmware_surum="", stm_bagli=False, uygula=False, banner_kaynagi=None, **k):
        kayit.append({"surum": firmware_surum, "stm_bagli": stm_bagli, "uygula": uygula})
        return {"eylem": "BEKLE", "gerekce": "kp"}

    monkeypatch.setattr(fm, "acilis_denetimi", _acilis_denetimi)
    return types.SimpleNamespace(fm=fm, kayit=kayit)


class _Veriyolu:
    def __init__(self, patla: bool = False):
        self.patla = patla
        self.abone: dict = {}

    def subscribe(self, olay, cb, kimlik):
        if self.patla:
            raise RuntimeError("veriyolu kapalı")
        self.abone[olay] = cb
        return True


def test_donanim_abonelik_PATLARSA_uyari_ve_YEDEK_olcum_yine_kurulur(firmware, monkeypatch):
    """Olay veriyolu aboneliği istisna atarsa → 'abone olunamadı' WARNING ve yedek ölçüm iş parçacığı yine kurulur."""
    kurulan: list = []

    class _KayitThread:
        def __init__(self, target=None, name=None, daemon=None, **kw):
            kurulan.append((name, daemon))

        def start(self):
            pass

    monkeypatch.setattr(
        bs, "threading", types.SimpleNamespace(Thread=_KayitThread, Event=threading.Event, Lock=threading.Lock)
    )
    lg, h = _gunlukcu("donanim_abone")
    bs._donanim_guncellemesi_kur(types.SimpleNamespace(stm_is_connected=False), lg, _Veriyolu(patla=True))
    assert any("abone olunamadı" in m for m in h.metinler(logging.WARNING))
    assert kurulan == [("donanim-guncellemesi-yedek", True)]
    assert firmware.kayit == []


def test_donanim_yedek_beklemesi_BITERKEN_el_sikisma_gelirse_TEK_karar_verilir(firmware, monkeypatch):
    """Yedek bekleme süresi dolduğu AN el sıkışma gelirse → gerçek karar (stm_bagli=True) BİR kez verilir; yedek
    'yalnız ölçüm' koşusu YAPILMAZ."""
    cekirdek = types.SimpleNamespace(stm_is_connected=False, stm_kimlik=None)
    yol = _Veriyolu()

    class _YarisOlayi(threading.Event):
        def wait(self, timeout=None):
            cekirdek.stm_is_connected = True
            yol.abone["hardware.stm.connected"]({"kp": 1})  # bekleme dolarken el sıkışma
            return False

    monkeypatch.setattr(
        bs, "threading", types.SimpleNamespace(Thread=_SatirIciThread, Event=_YarisOlayi, Lock=threading.Lock)
    )
    lg, h = _gunlukcu("donanim_yaris")
    bs._donanim_guncellemesi_kur(cekirdek, lg, yol)
    assert firmware.kayit == [{"surum": "", "stm_bagli": True, "uygula": False}]
    assert not any("YALNIZ ÖLÇÜM" in m for m in h.metinler())


def test_donanim_denetimi_PATLARSA_BASARISIZ_uyarisi_servis_dusmez(firmware, monkeypatch):
    """Firmware açılış denetimi istisna atarsa → 'Donanım güncellemesi kontrolü BAŞARISIZ (<tür>)' WARNING + iz."""

    def _patla(**k):
        raise TimeoutError("manifest alınamadı")

    monkeypatch.setattr(firmware.fm, "acilis_denetimi", _patla)
    lg, h = _gunlukcu("donanim_hata")
    bs._donanim_guncellemesi_safe(types.SimpleNamespace(stm_is_connected=True, stm_kimlik=None), lg)
    uyarilar = [r for r in h.kayitlar if r.levelno == logging.WARNING]
    assert len(uyarilar) == 1 and "BAŞARISIZ (TimeoutError)" in uyarilar[0].getMessage() and uyarilar[0].exc_info
