# -*- coding: utf-8 -*-
"""KP-1 · apps/backend/database/sqlcipher_util.py · sözleşmeler: binding seçimi (sqlcipher3 yoksa pysqlcipher3) · anahtar yolu
fail-closed (tekrar-kısıtlı yardımcı yoksa da ileti + RuntimeError) · `open_encrypted_conn` (row_factory uygulanır; yanlış anahtarda
kapatma hatası özgün hatayı GİZLEMEZ) · kilit dirençli silme / taşıma (bütçe biter → False + uyarı; yetim tutamak gc ile bırakılınca
2. denemede taşınır) · düz-metin tespiti (okunamayan dosya / kapatma hatası) · ACL gevşetme (icacls) · kalan düz kopyaların korunması
· göç sonrası yedek politikası (ACL modülü yoksa güvenli-sil; silinemezse KRİTİK ve False) · yedeği kenara alma (aynı saniyede sıra
eki; taşınamazsa SİLMEZ ve yükseltir) · yarım göç toparlama (ACL gevşetilince geri konur / gevşetilemezse ya da yine düşerse veri
`.plain.bak`'ta kalır) · göç (bağlantı kapatma hatası göçü bozmaz; kilitli `.enc.tmp` → ERTELENİR; boş şema → iptal; artık -wal/-shm
temizlenir / temizlenemezse uyarı; `.enc.tmp → db` düşerse düz-metin geri konur, geri koyma da düşerse veri `.plain.bak`'ta kalır ve
SONRAKİ açılış toparlayıp göçü tamamlar) · Y95 güvenli silme / yarım işlem toparlama · düz yedek şifreleme (dizin / kök hata kolları).

Sahte EN ALT katta: `utils.secrets_manager.get_secret` (kasa YOK; anahtar sabit), icacls = `subprocess.run` (süreç YOK), dosya
kilidi = GERÇEK Windows tutamağı (Python `open` → silme/yeniden adlandırma WinError 32; `CreateFileW` paylaşımsız → okuma da düşer),
modülün `time` / `gc` adları (gerçek bekleme YOK — 24 × 0,25 sn bütçe sayılır), binding (`sqlcipher3.dbapi2.connect` sarmalayıcısı /
parametre olarak verilen binding), modülün `os` / `open` adları yalnız tek işlevde (replace / link / remove / open) GERÇEK arıza
biçimiyle. Şifreli DB'ler yalnız tmp_path'te, gerçek sqlcipher3 ile.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import types

import pytest
from database import sqlcipher_util as su

sc = pytest.importorskip("sqlcipher3.dbapi2", reason="sqlcipher3 binding yok")

WIN = sys.platform == "win32"
yalniz_windows = pytest.mark.skipif(not WIN, reason="Windows dosya kilidi semantiği (paylaşım ihlali) gerekir")

ANAHTAR = "kp-test-anahtari"
_GERCEK_MOVE = shutil.move
KEYQ = "'" + ANAHTAR + "'"


# ── Yardımcılar ──────────────────────────────────────────────────────────────


class _Gunluk:
    """Ürünün `logger` parametresine verilen kaydedici."""

    def __init__(self):
        self.kayit: list = []

    def _k(self, seviye, msg, *a, **k):
        self.kayit.append((seviye, (msg % a) if a else msg, k.get("exc_info")))

    def debug(self, m, *a, **k):
        self._k("debug", m, *a, **k)

    def info(self, m, *a, **k):
        self._k("info", m, *a, **k)

    def warning(self, m, *a, **k):
        self._k("warning", m, *a, **k)

    def error(self, m, *a, **k):
        self._k("error", m, *a, **k)

    def exception(self, m, *a, **k):
        self._k("exception", m, *a, **k)

    def metin(self, seviye=None):
        return [m for s, m, _ in self.kayit if seviye is None or s == seviye]

    def var_mi(self, seviye, parca):
        return any(parca in m for m in self.metin(seviye))


def _duz_db(yol, satirlar=("Karabas", "Pamuk"), tablo=True):
    c = sqlite3.connect(str(yol))
    try:
        if tablo:
            c.execute("CREATE TABLE hasta(ad TEXT)")
            c.executemany("INSERT INTO hasta VALUES (?)", [(s,) for s in satirlar])
        else:
            c.execute("PRAGMA user_version=7")  # başlık yazılır, şema BOŞ
        c.commit()
    finally:
        c.close()


def _sifreli_db(yol, satirlar=("Pamuk",), keyq=KEYQ):
    c = sc.connect(str(yol))
    try:
        c.execute(f"PRAGMA key={keyq}")
        c.execute("CREATE TABLE hasta(ad TEXT)")
        c.executemany("INSERT INTO hasta VALUES (?)", [(s,) for s in satirlar])
        c.commit()
    finally:
        c.close()


def _sifreli_oku(yol, keyq=KEYQ):
    c = sc.connect(str(yol))
    try:
        c.execute(f"PRAGMA key={keyq}")
        return [r[0] for r in c.execute("SELECT ad FROM hasta ORDER BY ad")]
    finally:
        c.close()


def _duz_oku(yol):
    c = sqlite3.connect(str(yol))
    try:
        return [r[0] for r in c.execute("SELECT ad FROM hasta ORDER BY ad")]
    finally:
        c.close()


if WIN:
    import ctypes
    from ctypes import wintypes

    _K32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _K32.CreateFileW.restype = wintypes.HANDLE
    _K32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _K32.CloseHandle.argtypes = [wintypes.HANDLE]
    _GECERSIZ = ctypes.c_void_p(-1).value


class _Kilitler:
    """Başka bir sürecin (antivirüs / yedekleyici) dosyayı PAYLAŞIMSIZ açması: CreateFileW(share=0) → yeniden adlandırma, kopya için
    okuma ve silme GERÇEK paylaşım ihlaliyle düşer. `ac` kilidi kaldırır."""

    def __init__(self):
        self._h: dict = {}

    @staticmethod
    def _k(yol):
        return os.path.normcase(os.path.abspath(str(yol)))

    def kilitle(self, yol):
        k = self._k(yol)
        if k in self._h:
            return
        h = _K32.CreateFileW(str(yol), 0x80000000, 0, None, 3, 0x80, None)
        if h in (None, _GECERSIZ):
            raise OSError(ctypes.get_last_error(), "test kilidi açılamadı", str(yol))
        self._h[k] = h

    def ac(self, yol):
        h = self._h.pop(self._k(yol), None)
        if h is not None:
            _K32.CloseHandle(h)

    def hepsini_ac(self):
        for k in list(self._h):
            _K32.CloseHandle(self._h.pop(k))


@pytest.fixture(autouse=True)
def _arka_plan_isleri(monkeypatch):
    """Y93 arka plan yedek şifreleme işleri bu dosyada AYRI sözlükte; test sonunda beklenir ve sözlük geri konur."""
    monkeypatch.setattr(su, "_yedek_isleri", {})
    monkeypatch.delenv("PEMF_KEEP_PLAIN_BACKUP", raising=False)
    monkeypatch.delenv("PEMF_KEEP_PLAIN_BAK", raising=False)
    yield
    assert su.yedek_sifrelemesini_bekle(20), "arka plan yedek şifrelemesi bitmedi"


@pytest.fixture
def kilit():
    k = _Kilitler()
    yield k
    k.hepsini_ac()


@pytest.fixture
def hizli(monkeypatch):
    """Modülün `time` / `gc` adları: bekleme sayılır (gerçek uyku YOK), gc sayılır."""
    uykular: list = []
    gcler: list = []
    zaman = types.SimpleNamespace(sleep=uykular.append, strftime=time.strftime, time=time.time)
    monkeypatch.setattr(su, "time", zaman)
    monkeypatch.setattr(su, "gc", types.SimpleNamespace(collect=lambda: gcler.append(1) or 0))
    return types.SimpleNamespace(uykular=uykular, gcler=gcler, zaman=zaman)


@pytest.fixture
def kasa(monkeypatch):
    import utils.secrets_manager as sm

    monkeypatch.setattr(sm, "get_secret", lambda ad, *a, **k: ANAHTAR if ad == "sqlcipher_key" else "")
    return sm


class _Icacls:
    """subprocess.run sahtesi (icacls): argümanları kaydeder; `kilit_acar` ise hedef yolun test kilidini kaldırır (ACL gevşedi)."""

    def __init__(self, kilitler=None, basarisiz=False, kilit_acar=True):
        self.cagrilar: list = []
        self.kilitler = kilitler
        self.basarisiz = basarisiz
        self.kilit_acar = kilit_acar

    def __call__(self, args, *a, **k):
        self.cagrilar.append(list(args))
        if self.basarisiz:
            raise subprocess.CalledProcessError(5, args, b"", "Erişim engellendi.".encode("utf-8"))
        if self.kilitler is not None and self.kilit_acar:
            self.kilitler.ac(args[1])
        return subprocess.CompletedProcess(args, 0, b"", b"")


# ── import_sqlcipher / get_sqlcipher_key / open_encrypted_conn ───────────────


def test_import_sqlcipher_YOKSA_pysqlcipher3_dbapi2_doner(monkeypatch):
    """sqlcipher3 içe aktarılamıyor, pysqlcipher3 var → `pysqlcipher3.dbapi2` döner; ikisi de yoksa None."""
    paket = types.ModuleType("pysqlcipher3")
    paket.dbapi2 = types.ModuleType("pysqlcipher3.dbapi2")
    monkeypatch.setitem(sys.modules, "sqlcipher3", None)
    monkeypatch.setitem(sys.modules, "pysqlcipher3", paket)
    assert su.import_sqlcipher() is paket.dbapi2
    monkeypatch.setitem(sys.modules, "pysqlcipher3", None)
    assert su.import_sqlcipher() is None


def test_anahtar_okunamazsa_tekrar_kisitli_yardimci_YOKKEN_de_ileti_ve_RuntimeError(kasa, monkeypatch):
    """get_secret OSError + `tekrar_kisitli_hata` içe aktarılamıyor → logger.error ileti (hata türüyle) ve RuntimeError (from OSError);
    yeni anahtar üretilmez."""
    cagrilar: list = []

    def _kasa(ad, *a, **k):
        cagrilar.append((ad, k.get("generate")))
        raise OSError(5, "G/Ç hatası", "pemf_secrets.json")

    monkeypatch.setattr(kasa, "get_secret", _kasa)
    monkeypatch.delattr(kasa, "tekrar_kisitli_hata")
    monkeypatch.setenv("PEMF_ENCRYPT_AT_REST", "1")
    g = _Gunluk()
    with pytest.raises(RuntimeError, match="yeni anahtar URETILMEDI") as ei:
        su.get_sqlcipher_key("C:/yok", g)
    assert isinstance(ei.value.__cause__, OSError)
    assert cagrilar == [("sqlcipher_key", True)]
    hatalar = g.metin("error")
    assert len(hatalar) == 1 and "OSError" in hatalar[0] and "YENI ANAHTAR URETILMEDI" in hatalar[0]


def test_open_encrypted_conn_row_factory_UYGULANIR_tirnakli_anahtar(tmp_path):
    """Tırnak içeren anahtar kaçışlanır; verilen row_factory bağlantıya konur (satır sütun adıyla okunur)."""
    yol = tmp_path / "s.db"
    kq = "'" + "an''ahtar" + "'"
    _sifreli_db(yol, ("Boncuk",), keyq=kq)
    c = su.open_encrypted_conn(yol, "an'ahtar", sc, row_factory=sc.Row)
    try:
        assert c.row_factory is sc.Row
        satir = c.execute("SELECT ad FROM hasta").fetchone()
        assert satir["ad"] == "Boncuk"
    finally:
        c.close()


class _KapanisiBozuk:
    def __init__(self, gercek):
        self._g = gercek
        self.kapandi = False

    def __getattr__(self, ad):
        return getattr(self._g, ad)

    def close(self):
        self._g.close()
        self.kapandi = True
        raise sc.ProgrammingError("kapatma hatası (taklit)")


def test_open_encrypted_conn_yanlis_anahtarda_KAPATMA_hatasi_ozgun_hatayi_GIZLEMEZ(tmp_path):
    """Yanlış anahtar → 'file is not a database' DatabaseError yükselir (kapatmanın ProgrammingError'ı değil); bağlantı gerçekten
    kapanır (dosya yeniden adlandırılabilir)."""
    yol = tmp_path / "s.db"
    _sifreli_db(yol)
    acilan: list = []

    def _connect(*a, **k):
        acilan.append(_KapanisiBozuk(sc.connect(*a, **k)))
        return acilan[-1]

    binding = types.SimpleNamespace(connect=_connect)
    with pytest.raises(sc.DatabaseError, match="file is not a database"):
        su.open_encrypted_conn(yol, "YANLIS-anahtar", binding)
    assert acilan and acilan[0].kapandi is True
    os.replace(yol, tmp_path / "tasindi.db")  # tutamak sızsaydı Windows'ta WinError 32


# ── _kilit_direncli_sil / _kilit_direncli_tasi ───────────────────────────────


@yalniz_windows
def test_kilit_direncli_sil_BUTCE_bitince_False_ve_UYARI_dosya_yerinde(tmp_path, hizli, monkeypatch):
    """Dosya açık tutamakla kilitli → her deneme WinError 32; bütçe (3) bitince False, uyarı yolu adıyla yazılır, dosya yerinde."""
    monkeypatch.setattr(su, "_KILIT_DENEME", 3)
    yol = tmp_path / "x.enc.tmp"
    yol.write_bytes(b"artik")
    g = _Gunluk()
    with open(yol, "rb"):
        assert su._kilit_direncli_sil(yol, g) is False
    assert yol.exists()
    assert hizli.uykular == [su._KILIT_BEKLEME_SN] * 2 and len(hizli.gcler) == 2
    assert g.var_mi("warning", str(yol)) and g.var_mi("warning", "Dosya silinemedi")


def test_kilit_direncli_sil_deneme_butcesi_SIFIRSA_dokunmadan_False(tmp_path, monkeypatch):
    """_KILIT_DENEME = 0 → hiç denenmez: False döner, dosya yerinde."""
    monkeypatch.setattr(su, "_KILIT_DENEME", 0)
    yol = tmp_path / "x.enc.tmp"
    yol.write_bytes(b"artik")
    assert su._kilit_direncli_sil(yol) is False
    assert yol.exists()


@yalniz_windows
def test_kilit_direncli_tasi_YETIM_tutamak_gc_ile_birakilinca_2_denemede_tasir(tmp_path):
    """Kaynak yalnız bir başvuru döngüsündeki (yetim) dosya nesnesince açık → 1. deneme düşer, gc.collect tutamağı kapatır, 2. deneme
    taşır; True + 'ancak 2. denemede' uyarısı."""
    import gc

    src = tmp_path / "patients.db"
    dst = tmp_path / "patients.db.acilamadi-1"
    src.write_bytes(b"VERI")
    g = _Gunluk()
    gc.disable()
    try:

        class _Yetim:
            pass

        y = _Yetim()
        y.dongu = y
        y.fh = open(src, "rb")
        del y
        assert su._kilit_direncli_tasi(str(src), str(dst), g, deneme=3, bekleme_s=0.01) is True
    finally:
        gc.enable()
        gc.collect()
    assert dst.read_bytes() == b"VERI" and not src.exists()
    assert g.var_mi("warning", "ancak 2. denemede")


# ── duz_metin_sqlite_mi ──────────────────────────────────────────────────────


def test_duz_metin_sqlite_mi_OKUNAMAYAN_dosya_False(tmp_path):
    """Dosya yok / dizin → False (OSError yutulur)."""
    assert su.duz_metin_sqlite_mi(tmp_path / "yok.db") is False
    assert su.duz_metin_sqlite_mi(tmp_path) is False


def test_duz_metin_sqlite_mi_KAPATMA_hatasi_sonucu_degistirmez(tmp_path, monkeypatch):
    """Düz SQLite dosyası; bağlantının close()'u hata verir → yine True (tutamak kapanmış, hata yutulur)."""
    yol = tmp_path / "d.db"
    _duz_db(yol)
    gercek = sqlite3.connect
    acilan: list = []

    class _Bag:
        def __init__(self, c):
            self._c = c

        def execute(self, *a):
            return self._c.execute(*a)

        def close(self):
            self._c.close()
            acilan.append(True)
            raise sqlite3.ProgrammingError("kapatma hatası (taklit)")

    monkeypatch.setattr(su.sqlite3, "connect", lambda *a, **k: _Bag(gercek(*a, **k)))
    assert su.duz_metin_sqlite_mi(yol) is True
    assert acilan == [True]


# ── _kilidi_gevset / _yarim_goc_toparla ──────────────────────────────────────


def test_kilidi_gevset_ACL_modulu_YOKSA_False_ve_debug(tmp_path, monkeypatch):
    """`utils.file_acl.lock_down_file` içe aktarılamıyor → False, debug kaydı (yığın izli)."""
    import utils.file_acl as fa

    monkeypatch.delattr(fa, "lock_down_file")
    g = _Gunluk()
    assert su._kilidi_gevset(str(tmp_path / "x.plain.bak"), g) is False
    assert g.kayit and g.kayit[0][0] == "debug" and "ACL gevsetme denenemedi" in g.kayit[0][1] and g.kayit[0][2] is True


@yalniz_windows
def test_yarim_goc_ACL_gevsetilince_TOPARLANIR(tmp_path, hizli, kilit, monkeypatch):
    """db YOK + `.plain.bak` kilitli → 24 deneme düşer; icacls (süreç hesabıyla /grant:r) kilidi kaldırır → geri konur: True, db düz
    veriyle yerinde, yedek yok, 'ACL kilidi gevsetildikten sonra' uyarısı. icacls argümanlarında SYSTEM + Administrators'a EK OLARAK
    SÜRECİN HESABINA `/grant:r *S-…:F` verilir (gevşetmenin amacı bu — yalnız SYSTEM/Admins kilidi yükseltilmemiş süreci dışarıda tutar)."""
    from utils import file_acl

    db = tmp_path / "patients.db"
    yedek = tmp_path / "patients.db.plain.bak"
    _duz_db(yedek)
    kilit.kilitle(yedek)
    ic = _Icacls(kilit)
    monkeypatch.setattr(subprocess, "run", ic)
    g = _Gunluk()
    assert su._yarim_goc_toparla(str(db), g) is True
    assert _duz_oku(db) == ["Karabas", "Pamuk"] and not yedek.exists()
    assert len(ic.cagrilar) == 1 and ic.cagrilar[0][:2] == ["icacls", str(yedek)] and "/grant:r" in ic.cagrilar[0]
    argumanlar = ic.cagrilar[0]
    verilenler = [argumanlar[i + 1] for i, a in enumerate(argumanlar[:-1]) if a == "/grant:r"]
    surec_ace = file_acl._surec_ace("")
    assert surec_ace is not None and surec_ace.startswith("*S-1-") and surec_ace.endswith(":F")
    assert surec_ace in verilenler, verilenler
    assert len(hizli.uykular) == su._KILIT_DENEME - 1
    assert g.var_mi("warning", "ACL kilidi gevsetildikten sonra")


@yalniz_windows
def test_yarim_goc_ACL_GEVSETILEMEZSE_veri_yedekte_kalir(tmp_path, hizli, kilit, monkeypatch):
    """icacls başarısız → False; db YOK, `.plain.bak` yerinde ve aynen; 'TOPARLANAMADI — veri … dosyasinda duruyor' hatası."""
    db = tmp_path / "patients.db"
    yedek = tmp_path / "patients.db.plain.bak"
    _duz_db(yedek)
    kilit.kilitle(yedek)
    monkeypatch.setattr(subprocess, "run", _Icacls(kilit, basarisiz=True))
    g = _Gunluk()
    assert su._yarim_goc_toparla(str(db), g) is False
    kilit.ac(yedek)
    assert not db.exists() and _duz_oku(yedek) == ["Karabas", "Pamuk"]
    assert g.var_mi("error", "TOPARLANAMADI") and g.var_mi("error", str(yedek))
    assert not g.var_mi("error", "ACL gevsetildi ama")


@yalniz_windows
def test_yarim_goc_ACL_gevsetildi_ama_tasima_YINE_duserse_False(tmp_path, hizli, kilit, monkeypatch):
    """icacls başarılı ama dosya hâlâ kilitli → ikinci taşıma da düşer: False, 'ACL gevsetildi ama tasima yine dustu', veri yedekte."""
    db = tmp_path / "patients.db"
    yedek = tmp_path / "patients.db.plain.bak"
    _duz_db(yedek)
    kilit.kilitle(yedek)
    monkeypatch.setattr(subprocess, "run", _Icacls(kilit, kilit_acar=False))
    g = _Gunluk()
    assert su._yarim_goc_toparla(str(db), g) is False
    kilit.ac(yedek)
    assert not db.exists() and _duz_oku(yedek) == ["Karabas", "Pamuk"]
    assert g.var_mi("error", "ACL gevsetildi ama tasima yine dustu")
    assert len(hizli.uykular) == 2 * (su._KILIT_DENEME - 1)


# ── _kalan_duz_metin_kopyalari_koru / goc_sonrasi_yedek_politikasi ───────────


def test_kalan_duz_kopyalar_ACL_modulu_YOKSA_korunamadi_der_ama_SILMEZ(tmp_path, monkeypatch):
    """Düz-metin kardeş kopya + `lock_down_file` içe aktarılamıyor → kopya listede döner, silinmez, ileti 'ACL korumasi UYGULANAMADI';
    açılırken ValueError veren kardeş atlanır."""
    import utils.file_acl as fa

    yedek = tmp_path / "patients.db.plain.bak"
    kardes = tmp_path / "patients.db.plain.bak.20260101_000000"
    bozuk = tmp_path / "patients.db.plain.bak.20260102_000000"
    sifreli = tmp_path / "patients.db.plain.bak.20260103_000000"
    _duz_db(kardes)
    _duz_db(bozuk)
    _sifreli_db(sifreli)  # düz-metin SQLite değil → listelenmez
    gercek_open = open

    def _open(yol, *a, **k):
        if os.path.normcase(str(yol)) == os.path.normcase(str(bozuk)):
            raise ValueError("embedded null character in path")
        return gercek_open(yol, *a, **k)

    monkeypatch.setattr(su, "open", _open, raising=False)
    monkeypatch.delattr(fa, "lock_down_file")
    g = _Gunluk()
    assert su._kalan_duz_metin_kopyalari_koru(str(yedek), g) == [str(kardes)]
    assert kardes.exists() and bozuk.exists() and _sifreli_oku(sifreli) == ["Pamuk"]
    assert g.var_mi("error", "ACL korumasi UYGULANAMADI") and g.var_mi("error", str(kardes))
    assert len(g.metin("error")) == 1


def test_yedek_politikasi_emanet_isteniyor_ACL_modulu_YOKSA_guvenli_siler(tmp_path, monkeypatch):
    """PEMF_KEEP_PLAIN_BACKUP=1 ama ACL modülü yok → uyarı + 'escrow'dan VAZGEÇİLDİ', `.plain.bak` güvenli-silinir, False."""
    import utils.file_acl as fa

    yedek = tmp_path / "patients.db.plain.bak"
    _duz_db(yedek)
    monkeypatch.setenv("PEMF_KEEP_PLAIN_BACKUP", "1")
    monkeypatch.delattr(fa, "lock_down_file")
    g = _Gunluk()
    assert su.goc_sonrasi_yedek_politikasi(str(yedek), g, etiket="Hasta DB") is False
    assert not yedek.exists()
    assert g.var_mi("warning", ".plain.bak ACL kilidi hata verdi")
    assert g.var_mi("warning", "escrow'dan VAZGEÇİLDİ") and g.var_mi("warning", "GÜVENLİ-SİLİNDİ")


def test_yedek_politikasi_SILINEMEZSE_KRITIK_ve_False(tmp_path):
    """`.plain.bak` salt-okunur (üzerine yazılamaz) → 'KRİTİK … ELLE SİLİN' hatası (yığın izli), False; dosya yerinde ve içerik aynı."""
    yedek = tmp_path / "patients.db.plain.bak"
    _duz_db(yedek)
    once = yedek.read_bytes()
    os.chmod(yedek, stat.S_IREAD)
    g = _Gunluk()
    try:
        assert su.goc_sonrasi_yedek_politikasi(str(yedek), g) is False
        assert yedek.read_bytes() == once
    finally:
        os.chmod(yedek, stat.S_IREAD | stat.S_IWRITE)
    hata = [k for k in g.kayit if k[0] == "error" and "ELLE SİLİN" in k[1]]
    assert hata and hata[0][2] is True and str(yedek) in hata[0][1]


# ── _yedegi_kenara_al ────────────────────────────────────────────────────────


def test_yedegi_kenara_al_AYNI_saniyede_sira_eki_alir(tmp_path, hizli):
    """`.plain.bak.<damga>` ve `.<damga>.1` doluyken → `.<damga>.2`'ye taşınır; hiçbir kopya silinmez; uyarı yeni adı söyler."""
    hizli.zaman.strftime = lambda bicim, *a: "20261101_120000"
    yedek = tmp_path / "patients.db.plain.bak"
    yedek.write_bytes(b"YENI")
    (tmp_path / "patients.db.plain.bak.20261101_120000").write_bytes(b"ESKI0")
    (tmp_path / "patients.db.plain.bak.20261101_120000.1").write_bytes(b"ESKI1")
    g = _Gunluk()
    su._yedegi_kenara_al(str(yedek), g)
    assert not yedek.exists()
    assert (tmp_path / "patients.db.plain.bak.20261101_120000.2").read_bytes() == b"YENI"
    assert (tmp_path / "patients.db.plain.bak.20261101_120000").read_bytes() == b"ESKI0"
    assert (tmp_path / "patients.db.plain.bak.20261101_120000.1").read_bytes() == b"ESKI1"
    assert g.var_mi("warning", "patients.db.plain.bak.20261101_120000.2")


@yalniz_windows
def test_yedegi_kenara_al_TASINAMAZSA_SILMEZ_ve_YUKSELTIR(tmp_path, hizli, kilit):
    """Eski `.plain.bak` paylaşımsız kilitli → 24 deneme düşer: istisna yükselir, 'goc IPTAL, veri yerinde BIRAKILDI', dosya yerinde."""
    yedek = tmp_path / "patients.db.plain.bak"
    yedek.write_bytes(b"TEK KOPYA")
    kilit.kilitle(yedek)
    g = _Gunluk()
    with pytest.raises(OSError):
        su._yedegi_kenara_al(str(yedek), g)
    kilit.ac(yedek)
    assert yedek.read_bytes() == b"TEK KOPYA"
    assert g.var_mi("error", "goc IPTAL, veri yerinde BIRAKILDI")
    assert g.var_mi("warning", "Dosya tasima 24 denemede basarisiz")


# ── migrate_to_encrypted_if_needed ───────────────────────────────────────────


class _BaglayiciSarmal:
    """sqlcipher3.dbapi2.connect sarmalayıcısı (binding katmanı): ilk `kac` close() çağrısı gerçek kapatmadan SONRA hata verir."""

    def __init__(self, kac=1):
        self.kalan = kac
        self.gercek = sc.connect

    def __call__(self, *a, **k):
        dis = self

        class _B:
            def __init__(self, c):
                self._c = c

            def __getattr__(self, ad):
                return getattr(self._c, ad)

            def close(self):
                self._c.close()
                if dis.kalan > 0:
                    dis.kalan -= 1
                    raise sc.OperationalError("kapatma hatası (taklit)")

        return _B(self.gercek(*a, **k))


def test_goc_KAPATMA_hatasi_gocu_BOZMAZ_tamamlanir(tmp_path, kasa, monkeypatch):
    """Düz DB; 'zaten şifreli mi' sınamasındaki bağlantının close()'u hata verir → yutulur, göç tamamlanır: db anahtarla şifreli ve
    veri aynı, `.plain.bak` güvenli-silinmiş."""
    db = tmp_path / "patients.db"
    _duz_db(db)
    sarmal = _BaglayiciSarmal(kac=1)
    monkeypatch.setattr(sc, "connect", sarmal)
    g = _Gunluk()
    su.migrate_to_encrypted_if_needed(db, tmp_path, g)
    assert sarmal.kalan == 0
    assert su.duz_metin_sqlite_mi(db) is False and _sifreli_oku(db) == ["Karabas", "Pamuk"]
    assert not (tmp_path / "patients.db.plain.bak").exists()
    assert not g.metin("exception")


@yalniz_windows
def test_goc_kilitli_ENC_TMP_silinemezse_ERTELENIR_db_duz_kalir(tmp_path, kasa, hizli, kilit):
    """Önceki `.enc.tmp` artığı kilitli → silinemez: 'goc ERTELENDI' uyarısı, db DÜZ ve aynen, `.plain.bak` yok. Göç ORADA DURUR:
    ERTELENDI son kayıttır; dışa aktarma (ATTACH / export) DENENMEZ → 'SQLCipher migrate hatasi' istisna kaydı ya da hata kaydı YOK."""
    db = tmp_path / "patients.db"
    _duz_db(db)
    artik = tmp_path / "patients.db.enc.tmp"
    artik.write_bytes(b"onceki yarim export")
    kilit.kilitle(artik)
    g = _Gunluk()
    su.migrate_to_encrypted_if_needed(db, tmp_path, g)
    assert g.var_mi("warning", "goc ERTELENDI")
    assert g.kayit[-1][0] == "warning" and "goc ERTELENDI" in g.kayit[-1][1], g.kayit[-1]
    assert g.metin("exception") == [] and g.metin("error") == [], g.kayit
    assert _duz_oku(db) == ["Karabas", "Pamuk"] and not (tmp_path / "patients.db.plain.bak").exists()


def test_goc_SEMASI_bos_duz_DB_de_iptal_duz_korunur(tmp_path, kasa, hizli, monkeypatch):
    """Başlıklı ama tablosuz düz DB → şifreli kopya boş (0 şema) → iptal: 'sifreli kopya bos' hatası, `.enc.tmp` silinmiş, db düz.
    İptal yer-değiştirme penceresine GİRMEDEN olur: `shutil.move` HİÇ çağrılmaz (db bir an bile yerinden kalkmaz), bekleme yok,
    uyarı yok; tek kayıt 'sifreli kopya bos' hatasıdır."""
    db = tmp_path / "patients.db"
    _duz_db(db, tablo=False)
    tasimalar: list = []

    def _move(kaynak, hedef, *a, **k):
        tasimalar.append((os.path.basename(str(kaynak)), os.path.basename(str(hedef))))
        return _GERCEK_MOVE(kaynak, hedef, *a, **k)

    monkeypatch.setattr(shutil, "move", _move)
    g = _Gunluk()
    su.migrate_to_encrypted_if_needed(db, tmp_path, g)
    assert g.var_mi("error", "sifreli kopya bos")
    assert g.metin("error") == ["SQLCipher migrate: sifreli kopya bos -> iptal (duz-metin korunur)."]
    assert tasimalar == [] and hizli.uykular == []
    assert g.metin("warning") == [] and g.metin("exception") == [], g.kayit
    assert su.duz_metin_sqlite_mi(db) is True
    assert not (tmp_path / "patients.db.enc.tmp").exists() and not (tmp_path / "patients.db.plain.bak").exists()


def test_goc_ARTIK_shm_TEMIZLENIR(tmp_path, kasa):
    """Geri-alma günlüklü düz DB'nin yanında artık `-shm` (SQLite geri-alma kipinde ona dokunmaz) → göç öncesi silinir; göç
    tamamlanır, uyarı yok."""
    db = tmp_path / "patients.db"
    _duz_db(db)
    (tmp_path / "patients.db-shm").write_bytes(b"\0" * 32)
    g = _Gunluk()
    su.migrate_to_encrypted_if_needed(db, tmp_path, g)
    assert _sifreli_oku(db) == ["Karabas", "Pamuk"]
    assert not (tmp_path / "patients.db-shm").exists()
    assert not g.var_mi("warning", "temizlenemedi")


@yalniz_windows
def test_goc_ARTIK_shm_silinemezse_UYARI_ve_goc_surer(tmp_path, kasa):
    """Artık `-shm` açık tutamakla kilitli → 'temizlenemedi … bozulma riski' uyarısı (yığın izli, yol adıyla); göç yine tamamlanır."""
    db = tmp_path / "patients.db"
    _duz_db(db)
    shm = tmp_path / "patients.db-shm"
    shm.write_bytes(b"\0" * 32)
    g = _Gunluk()
    with open(shm, "rb"):
        su.migrate_to_encrypted_if_needed(db, tmp_path, g)
    uyari = [k for k in g.kayit if k[0] == "warning" and "temizlenemedi" in k[1]]
    assert uyari and str(shm) in uyari[0][1] and uyari[0][2] is True
    assert _sifreli_oku(db) == ["Karabas", "Pamuk"]


class _TasimaKancasi:
    """shutil.move'un önü: adı `kilitlenecek`te olan KAYNAĞA ilk dokunuşta paylaşımsız kilit açılır (AV dosyayı o an açtı), sonra
    GERÇEK shutil.move koşar (gerçek WinError 32)."""

    def __init__(self, kilitler, adlar):
        self.kilitler = kilitler
        self.adlar = set(adlar)
        self.gercek = _GERCEK_MOVE

    def __call__(self, src, dst, *a, **k):
        if os.path.basename(str(src)) in self.adlar:
            self.kilitler.kilitle(src)
        return self.gercek(src, dst, *a, **k)


@yalniz_windows
def test_goc_ENC_TMP_yerine_KONAMAZSA_duz_geri_konur_IPTAL_uyarisi(tmp_path, kasa, hizli, kilit, monkeypatch):
    """`.enc.tmp → db` taşıması kilitte düşer → düz-metin `.plain.bak` db'ye GERİ konur; kilitli `.enc.tmp` silinemese de iptal
    uyarısı yazılır: db düz ve veri aynı, `.plain.bak` yok."""
    db = tmp_path / "patients.db"
    _duz_db(db)
    monkeypatch.setattr(shutil, "move", _TasimaKancasi(kilit, {"patients.db.enc.tmp"}))
    g = _Gunluk()
    su.migrate_to_encrypted_if_needed(db, tmp_path, g)
    assert g.var_mi("warning", "SQLCipher goc IPTAL (dosya kilidi)")
    assert _duz_oku(db) == ["Karabas", "Pamuk"]
    assert not (tmp_path / "patients.db.plain.bak").exists()
    assert (tmp_path / "patients.db.enc.tmp").exists()  # kilitli artık — sonraki açılışta silinir


@yalniz_windows
def test_goc_GERI_ALMA_da_duserse_veri_PLAIN_BAKta_kalir_sonraki_acilis_TAMAMLAR(
    tmp_path, kasa, hizli, kilit, monkeypatch
):
    """`.enc.tmp → db` VE `.plain.bak → db` kilitte düşer → 'GOC GERI ALINAMADI … ELLE geri koyun', db YOK, veri `.plain.bak`'ta.
    Bu hata SON kayıttır: ardından 'duz-metin veri yerinde KORUNDU' (goc IPTAL) uyarısı YAZILMAZ (db yokken yalan olurdu).
    Kilit kalkınca sonraki çağrı yarım göçü toparlar ve göçü tamamlar: db şifreli, veri aynı."""
    db = tmp_path / "patients.db"
    _duz_db(db)
    monkeypatch.setattr(shutil, "move", _TasimaKancasi(kilit, {"patients.db.enc.tmp", "patients.db.plain.bak"}))
    g = _Gunluk()
    su.migrate_to_encrypted_if_needed(db, tmp_path, g)
    assert g.var_mi("error", "GOC GERI ALINAMADI")
    assert g.kayit[-1][0] == "error" and "GOC GERI ALINAMADI" in g.kayit[-1][1], g.kayit[-1]
    assert not g.var_mi("warning", "goc IPTAL") and not g.var_mi("warning", "KORUNDU"), g.metin("warning")
    assert not db.exists()
    kilit.hepsini_ac()
    assert _duz_oku(tmp_path / "patients.db.plain.bak") == ["Karabas", "Pamuk"]
    monkeypatch.setattr(shutil, "move", _TasimaKancasi(kilit, set()))
    g2 = _Gunluk()
    su.migrate_to_encrypted_if_needed(db, tmp_path, g2)
    assert g2.var_mi("warning", "Yarim kalmis goc toparlandi")
    assert _sifreli_oku(db) == ["Karabas", "Pamuk"]
    assert not (tmp_path / "patients.db.plain.bak").exists() and not (tmp_path / "patients.db.enc.tmp").exists()


# ── Y95: _duz_icerigi_sifirla_ve_sil / _anahtarla_dogrulama_hatasi / _yarim_kalan_duz_icerigi_toparla ─


def test_duz_icerik_SALT_OKUNURSA_sifirlanamaz_silinemez_False(tmp_path):
    """Salt-okunur `.duz.sil` → üzerine yazılamaz (uyarı) ve silinemez (hata, 'icerik DUZ-METIN'); False, içerik aynen."""
    yol = tmp_path / "y.db.duz.sil"
    yol.write_bytes(b"HASTA ADLARI")
    os.chmod(yol, stat.S_IREAD)
    g = _Gunluk()
    try:
        assert su._duz_icerigi_sifirla_ve_sil(str(yol), g) is False
        assert yol.read_bytes() == b"HASTA ADLARI"
    finally:
        os.chmod(yol, stat.S_IREAD | stat.S_IWRITE)
    assert g.var_mi("warning", "UZERINE YAZILAMADI") and g.var_mi("error", "icerik DUZ-METIN")


def test_anahtarla_dogrulama_ACILAMAZ_ve_SEMA_BOS_nedenleri(tmp_path):
    """Var olmayan dizindeki yol → 'acilamadi (…)'; anahtarla açılan ama tablosuz şifreli DB → 'sema bos'; dolu → None."""
    neden = su._anahtarla_dogrulama_hatasi(str(tmp_path / "yok_dizin" / "x.db"), KEYQ, sc)
    assert neden is not None and neden.startswith("acilamadi (")
    bos = tmp_path / "bos.db"
    c = sc.connect(str(bos))
    c.execute(f"PRAGMA key={KEYQ}")
    c.execute("CREATE TABLE t(x)")
    c.execute("DROP TABLE t")
    c.commit()
    c.close()
    assert su._anahtarla_dogrulama_hatasi(str(bos), KEYQ, sc) == "sema bos"
    dolu = tmp_path / "dolu.db"
    _sifreli_db(dolu)
    assert su._anahtarla_dogrulama_hatasi(str(dolu), KEYQ, sc) is None


def test_yarim_kalan_AYNI_dosyaya_bag_ise_yalniz_ikinci_ad_kalkar(tmp_path):
    """`.duz.sil` özgün adla AYNI dosya (sabit bağ; değiştirme yapılmadan kesildi) → yalnız ikinci ad silinir, içerik özgün adda aynen."""
    asil = tmp_path / "gunluk.db"
    _duz_db(asil)
    sil = tmp_path / "gunluk.db.duz.sil"
    os.link(asil, sil)
    g = _Gunluk()
    su._yarim_kalan_duz_icerigi_toparla(str(sil), KEYQ, sc, g)
    assert not sil.exists() and _duz_oku(asil) == ["Karabas", "Pamuk"]
    assert g.kayit == []


@yalniz_windows
def test_yarim_kalan_ikinci_ad_SILINEMEZSE_hata_loglanir(tmp_path):
    """Sabit bağ `.duz.sil` açık tutamakla kilitli → silinemez: 'Y95 yarim islem toparlanamadi' hatası, iki ad da yerinde."""
    asil = tmp_path / "gunluk.db"
    _duz_db(asil)
    sil = tmp_path / "gunluk.db.duz.sil"
    os.link(asil, sil)
    g = _Gunluk()
    with open(sil, "rb"):
        su._yarim_kalan_duz_icerigi_toparla(str(sil), KEYQ, sc, g)
    assert sil.exists() and asil.exists()
    assert g.var_mi("error", "Y95 yarim islem toparlanamadi")


# ── _duz_kopyayi_sifrele ─────────────────────────────────────────────────────


def test_duz_kopya_ESKI_enc_tmp_ve_AYNI_dosya_ikinci_ad_varken_sifreler(tmp_path):
    """Önceki `.enc.tmp` artığı ve özgün adla AYNI dosya olan `.duz.sil` varken → artık silinir, bağ yeniden kurulur; şifreli kopya
    yerinde, mtime korunur, eski düz içerik sıfırlanıp silinir (True)."""
    yol = tmp_path / "y.db"
    _duz_db(yol)
    os.utime(yol, (1_700_000_000, 1_700_000_000))
    (tmp_path / "y.db.enc.tmp").write_bytes(b"onceki artik")
    os.link(yol, tmp_path / "y.db.duz.sil")
    assert su._duz_kopyayi_sifrele(str(yol), KEYQ, sc) is True
    assert _sifreli_oku(yol) == ["Karabas", "Pamuk"]
    assert int(os.stat(yol).st_mtime) == 1_700_000_000
    assert not (tmp_path / "y.db.enc.tmp").exists() and not (tmp_path / "y.db.duz.sil").exists()


class _OsVekili:
    """sqlcipher_util'in `os` adı: verilen işlevler dışında GERÇEK os."""

    def __init__(self, **degisen):
        self.__dict__.update(degisen)

    def __getattr__(self, ad):
        return getattr(os, ad)


@yalniz_windows
def test_duz_kopya_DEGISTIRME_dusunce_duz_dosya_AYNEN_kalir(tmp_path):
    """Özgün ad açık tutamakla kilitli → `os.replace` düşer, istisna yükselir; özgün düz dosya aynen okunur, `.enc.tmp` temizlenir."""
    yol = tmp_path / "y.db"
    _duz_db(yol)
    with open(yol, "rb"):
        with pytest.raises(OSError):
            su._duz_kopyayi_sifrele(str(yol), KEYQ, sc)
    assert _duz_oku(yol) == ["Karabas", "Pamuk"]
    assert not (tmp_path / "y.db.enc.tmp").exists()


def test_duz_kopya_DEGISTIRME_ve_ikinci_ad_silme_dusunce_yukseltir(tmp_path, monkeypatch):
    """`os.replace` erişim reddi + ikinci adın silinmesi de düşer → özgün istisna yükselir; düz dosya özgün adda aynen."""
    yol = tmp_path / "y.db"
    _duz_db(yol)
    eski = str(yol) + su._DUZ_SIL_EK

    def _replace(a, b):
        raise PermissionError(13, "Erişim engellendi", str(b))

    def _remove(p):
        if os.path.normcase(str(p)) == os.path.normcase(eski):
            raise PermissionError(32, "Dosya başka bir işlem tarafından kullanılıyor", str(p))
        return os.remove(p)

    monkeypatch.setattr(su, "os", _OsVekili(replace=_replace, remove=_remove))
    with pytest.raises(PermissionError, match="Erişim engellendi"):
        su._duz_kopyayi_sifrele(str(yol), KEYQ, sc)
    assert _duz_oku(yol) == ["Karabas", "Pamuk"]
    assert not (tmp_path / "y.db.enc.tmp").exists()


def test_duz_kopya_DEGISTIRME_sessizce_olmadiysa_DUZ_icerik_SIFIRLANMAZ(tmp_path, monkeypatch):
    """`os.replace` hata vermeden etkisiz kalır (ikinci ad hâlâ özgün dosya) → RuntimeError ('ikinci ad sifreli kopyayi
    gosteriyor'); düz içerik SIFIRLANMAZ; geçici dosyanın silinmesi de düşse yükselen hata aynı."""
    yol = tmp_path / "y.db"
    _duz_db(yol)
    gecici = str(yol) + ".enc.tmp"

    def _remove(p):
        if os.path.normcase(str(p)) == os.path.normcase(gecici):
            raise PermissionError(32, "Dosya başka bir işlem tarafından kullanılıyor", str(p))
        return os.remove(p)

    monkeypatch.setattr(su, "os", _OsVekili(replace=lambda a, b: None, remove=_remove))
    with pytest.raises(RuntimeError, match="ikinci ad sifreli kopyayi gosteriyor"):
        su._duz_kopyayi_sifrele(str(yol), KEYQ, sc)
    assert _duz_oku(yol) == ["Karabas", "Pamuk"]
    assert _duz_oku(str(yol) + su._DUZ_SIL_EK) == ["Karabas", "Pamuk"]


# ── duz_metin_yedekleri_sifrele: dizin / kök kolları ─────────────────────────


def test_yedek_tarama_ACILAMAYAN_kopya_atlanir_digeri_sifrelenir(tmp_path, monkeypatch):
    """`backups/` içinde iki düz .db; biri açılırken ValueError → atlanır (dokunulmaz), öbürü şifrelenir."""
    kok = tmp_path / "kok"
    (kok / "backups").mkdir(parents=True)
    a = kok / "backups" / "a.db"
    b = kok / "backups" / "b.db"
    _duz_db(a)
    _duz_db(b)
    gercek_open = open

    def _open(yol, *x, **k):
        if os.path.normcase(str(yol)) == os.path.normcase(str(a)):
            raise ValueError("embedded null character in path")
        return gercek_open(yol, *x, **k)

    monkeypatch.setattr(su, "open", _open, raising=False)
    sonuc = su.duz_metin_yedekleri_sifrele(str(kok), KEYQ, sc)
    assert sonuc["sifrelendi"] == [str(b)] and sonuc["sifrelenemedi"] == []
    assert _duz_oku(a) == ["Karabas", "Pamuk"] and _sifreli_oku(b) == ["Karabas", "Pamuk"]


def test_yedek_tarama_VERI_KOKU_okunamazsa_sifrelenemedi_ve_hata(tmp_path):
    """Veri kökü yok → kök 'sifrelenemedi'de, 'VERI KOKU OKUNAMADI' hatası; başka iş yok."""
    kok = tmp_path / "yok_kok"
    g = _Gunluk()
    sonuc = su.duz_metin_yedekleri_sifrele(str(kok), KEYQ, sc, g)
    assert sonuc == {"sifrelendi": [], "sifrelenemedi": [str(kok)]}
    assert g.var_mi("error", "VERI KOKU OKUNAMADI")


def test_kok_plain_bak_CANLI_dogrulamasi_istisnayla_duserse_DOKUNULMAZ(tmp_path):
    """Kökte düz `.plain.bak` + şifreli canlı db; binding'in close()'u doğrulamada hata verir → `.plain.bak` atlanır (düz, aynen)."""
    kok = tmp_path / "kok"
    kok.mkdir()
    _sifreli_db(kok / "patients.db")
    _duz_db(kok / "patients.db.plain.bak")

    def _connect(*a, **k):
        return _KapanisiBozuk(sc.connect(*a, **k))

    sonuc = su.duz_metin_yedekleri_sifrele(str(kok), KEYQ, types.SimpleNamespace(connect=_connect))
    assert sonuc == {"sifrelendi": [], "sifrelenemedi": []}
    assert _duz_oku(kok / "patients.db.plain.bak") == ["Karabas", "Pamuk"]


def test_kok_plain_bak_BAG_kurulamazsa_sifrelenir_ama_SIFIRLANAMADI_listelenir(tmp_path, monkeypatch):
    """Dosya sistemi sabit bağ desteklemiyor (os.link → OSError 'Geçersiz işlev') → `.plain.bak` yine şifrelenir; sonuçta
    'duz_icerik_sifirlanamadi' altında listelenir; uyarı 'sabit bag kurulamadi'."""
    kok = tmp_path / "kok"
    kok.mkdir()
    _sifreli_db(kok / "patients.db")
    pb = kok / "patients.db.plain.bak"
    _duz_db(pb)

    def _link(a, b):
        raise OSError(22, "Geçersiz işlev")

    monkeypatch.setattr(su, "os", _OsVekili(link=_link))
    g = _Gunluk()
    sonuc = su.duz_metin_yedekleri_sifrele(str(kok), KEYQ, sc, g, etiket="Hasta DB")
    assert sonuc["sifrelendi"] == [str(pb)] and sonuc["duz_icerik_sifirlanamadi"] == [str(pb)]
    assert _sifreli_oku(pb) == ["Karabas", "Pamuk"]
    assert g.var_mi("warning", "sabit bag kurulamadi") and g.var_mi("warning", "Hasta DB goc sonrasi")


def test_kok_plain_bak_FARKLI_ikinci_ad_varsa_SIFRELENEMEZ_ve_dokunulmaz(tmp_path):
    """Kökte `.plain.bak` + onunla AYNI OLMAYAN `.plain.bak.duz.sil` → şifreleme RuntimeError: 'sifrelenemedi', '.plain.bak
    SIFRELENEMEDI' hatası; Y95 toparlaması özgün ad düz olduğundan ikinci ada DOKUNMAZ; iki dosya da aynen."""
    kok = tmp_path / "kok"
    kok.mkdir()
    _sifreli_db(kok / "patients.db")
    pb = kok / "patients.db.plain.bak"
    _duz_db(pb)
    yabanci = kok / "patients.db.plain.bak.duz.sil"
    yabanci.write_bytes(b"baska dosya")
    g = _Gunluk()
    sonuc = su.duz_metin_yedekleri_sifrele(str(kok), KEYQ, sc, g)
    assert sonuc["sifrelendi"] == [] and sonuc["sifrelenemedi"] == [str(pb)]
    assert _duz_oku(pb) == ["Karabas", "Pamuk"] and yabanci.read_bytes() == b"baska dosya"
    assert g.var_mi("error", "(.plain.bak) SIFRELENEMEDI") and g.var_mi("error", "ozgun ad DUZ-METIN")
