# -*- coding: utf-8 -*-
"""FIRMWARE OTOMATİK GÜNCELLEME ORKESTRASYONU — `servers/firmware_manager`.

Sahip kararı 2026-09-22: cihaz firmware'i KENDİ alacak, açılışta, kullanıcı müdahalesi
olmadan. Yani bu modül hasta başındaki bir cihazda **kendiliğinden yakma** tetikleyecek.
Kapı, her dalın ne yaptığını davranışsal ölçer: gerçek ağ yok, gerçek yakma yok —
manifest ve yakma YAMALANIR, ölçülen şey SIRA ve KARAR.

İDDİALAR
  1. Manifest okunamıyorsa (internet yok) → BEKLE, `uygulandi=False`, gerekçe YAZILI
     (fail-quiet ≠ fail-silent)
  2. STM bağlı değilse → yakma DENENMEZ
  3. Uyumluysa → indirme bile yapılmaz (gereksiz yakma RİSKTİR)
  4. SHA256 yoksa/tutmuyorsa → indirme reddedilir, yakma YOK
  5. Plan `client_geri_al` ise → `update_manager.rollback()` çağrılır, firmware YAKILMAZ
  6. Yakma başarısızsa → `uygulandi=False` ve hata KODUYLA yazılır
  7. `durum()` her dalda GÜNCELLENİR — "atlandı" ile "yapıldı" ayırt edilebilir
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from utils import surum_uyumu as su

KURAL = [{"clientMin": "1.9.50", "clientMax": "", "firmwareMin": "2.3", "firmwareMax": ""}]


@pytest.fixture()
def fm(monkeypatch):
    """Taze modül + dış dünya YAMALI (ağ yok, yakma yok, client sürümü sabit)."""
    m = importlib.import_module("servers.firmware_manager")
    importlib.reload(m)  # modül-global durum testler arasında sızmasın
    monkeypatch.setattr(m.um, "get_current_version", lambda: "1.9.51")
    monkeypatch.setattr(m.um, "get_status", lambda: {"previousStable": {"version": "1.9.20"}})
    return m


def _manifest(fw_surum="2.3", url="https://example/fw.bin", sha="ab" * 32, kurallar=None):
    return {
        "firmware": {"stm32": {"version": fw_surum, "url": url, "sha256": sha}},
        "uyumluluk": KURAL if kurallar is None else kurallar,
    }


# ──────────────────────────────────────────────────────────────────────────
# 1) AĞ / DONANIM YOKKEN — sessiz atlama OLMAZ
# ──────────────────────────────────────────────────────────────────────────


def test_KRITIK_manifest_YOKSA_bekler_ve_GEREKCE_yazar(fm, monkeypatch):
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: None)
    d = fm.acilis_denetimi(firmware_surum="2.2", stm_bagli=True)
    assert d["eylem"] == su.BEKLE, f"internet yokken {d['eylem']} — beklemesi gerekirdi"
    assert d["uygulandi"] is False
    assert d["gerekce"], "gerekçe BOŞ — destek mühendisi neden atlandığını okuyamaz"
    assert d["kontrol_edildi"] is True, "kontrol edildiği işaretlenmemiş"


def test_KRITIK_STM_bagli_degilse_YAKMA_DENENMEZ(fm, monkeypatch):
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: _manifest())
    cagrildi = []
    monkeypatch.setattr(fm, "firmware_indir", lambda *a, **k: cagrildi.append(a) or (None, "x"))
    d = fm.acilis_denetimi(firmware_surum="2.2", stm_bagli=False)
    assert d["eylem"] == su.BEKLE, d["gerekce"]
    assert not cagrildi, "STM bağlı değilken indirme/yakma denenmiş"


# ──────────────────────────────────────────────────────────────────────────
# 2) UYUMLUYSA DOKUNMA
# ──────────────────────────────────────────────────────────────────────────


def test_KRITIK_uyumluysa_INDIRME_bile_yapilmaz(fm, monkeypatch):
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: _manifest(fw_surum="2.4"))
    cagrildi = []
    monkeypatch.setattr(fm, "firmware_indir", lambda *a, **k: cagrildi.append(a) or (None, "x"))
    d = fm.acilis_denetimi(firmware_surum="2.3", stm_bagli=True)
    assert d["eylem"] == su.EYLEM_YOK, d["gerekce"]
    assert not cagrildi, "zaten uyumluyken indirme yapılmış — gereksiz yakma RİSKTİR"


# ──────────────────────────────────────────────────────────────────────────
# 3) BÜTÜNLÜK — doğrulanmamış firmware yakılmaz
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url,sha,beklenen_parca",
    [("https://example/fw.bin", "", "SHA256"), ("", "ab" * 32, "url")],
)
def test_KRITIK_eksik_url_ya_da_sha_REDDEDILIR(fm, url, sha, beklenen_parca):
    yol, hata = fm.firmware_indir(url, sha)
    assert yol is None and beklenen_parca.lower() in hata.lower(), hata


def test_KRITIK_indirme_basarisizsa_YAKMA_YOK(fm, monkeypatch):
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: _manifest())
    monkeypatch.setattr(fm, "firmware_indir", lambda *a, **k: (None, "SHA256 tutmadı"))
    yakildi = []
    monkeypatch.setattr(fm, "_firmware_uygula", fm._firmware_uygula)  # gerçek yol
    import utils.stm_yakma as sy

    monkeypatch.setattr(sy, "yakma_akisi", lambda *a, **k: yakildi.append(a))
    d = fm.acilis_denetimi(firmware_surum="2.2", stm_bagli=True)
    assert not yakildi, "indirme başarısızken YAKILMIŞ"
    assert d["uygulandi"] is False and "SHA256" in d["hata"]


# ──────────────────────────────────────────────────────────────────────────
# 4) PLAN UYGULAMA — hangi dal hangi işi çağırıyor
# ──────────────────────────────────────────────────────────────────────────


def test_KRITIK_firmware_guncelle_dali_YAKMA_cagirir(fm, monkeypatch, tmp_path):
    sahte = tmp_path / "fw.bin"
    sahte.write_bytes(b"X")
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: _manifest(fw_surum="2.3"))
    monkeypatch.setattr(fm, "firmware_indir", lambda *a, **k: (sahte, ""))
    import utils.stm_yakma as sy

    cagri = {}

    def _sahte_yak(yol, **k):
        cagri["yol"] = yol
        return sy.Sonuc(sy.TAMAM, "ok", adimlar=["sahte"])

    monkeypatch.setattr(sy, "yakma_akisi", _sahte_yak)
    d = fm.acilis_denetimi(firmware_surum="2.2", stm_bagli=True)
    assert cagri.get("yol") == sahte, "yakma çağrılmadı"
    assert d["uygulandi"] is True and d["firmwareSurum"] == "2.3", d


def test_KRITIK_client_geri_al_dali_FIRMWARE_YAKMAZ(fm, monkeypatch):
    """Plan geri alma diyorsa firmware'e DOKUNULMAZ — yanlış tarafı yakmak felakettir."""
    # client 1.9.51 + fw 2.1; yeni firmware YOK → tek çare client'ı 1.9.20'ye almak
    kurallar = [
        {"clientMin": "1.9.00", "clientMax": "1.9.49", "firmwareMin": "2.0", "firmwareMax": "2.2"},
        {"clientMin": "1.9.50", "clientMax": "", "firmwareMin": "2.3", "firmwareMax": ""},
    ]
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: _manifest(fw_surum="", kurallar=kurallar))
    import utils.stm_yakma as sy

    yakildi = []
    monkeypatch.setattr(sy, "yakma_akisi", lambda *a, **k: yakildi.append(a))
    geri = []
    monkeypatch.setattr(fm.um, "rollback", lambda: geri.append(1) or {"ok": True})

    d = fm.acilis_denetimi(firmware_surum="2.1", stm_bagli=True)
    assert d["eylem"] == su.CLIENT_GERI_AL, d["gerekce"]
    assert geri, "client rollback ÇAĞRILMADI"
    assert not yakildi, "geri alma dalında firmware YAKILMIŞ"


def test_KRITIK_yakma_basarisizsa_KOD_ile_yazilir(fm, monkeypatch, tmp_path):
    sahte = tmp_path / "fw.bin"
    sahte.write_bytes(b"X")
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: _manifest(fw_surum="2.3"))
    monkeypatch.setattr(fm, "firmware_indir", lambda *a, **k: (sahte, ""))
    import utils.stm_yakma as sy

    monkeypatch.setattr(
        sy,
        "yakma_akisi",
        lambda *a, **k: sy.Sonuc(sy.UYUMSUZ_GERI_DONULDU, "kart 5 kanallı", adimlar=[]),
    )
    d = fm.acilis_denetimi(firmware_surum="2.2", stm_bagli=True)
    assert d["uygulandi"] is False
    assert str(sy.UYUMSUZ_GERI_DONULDU) in d["hata"], f"hata kodu yazılmamış: {d['hata']}"


def test_uygula_FALSE_ise_hicbir_yan_etki_YOK(fm, monkeypatch):
    """`uygula=False` ölçüm kipidir: plan hesaplanır, hiçbir şey yapılmaz."""
    monkeypatch.setattr(fm, "manifest_oku", lambda **_k: _manifest())
    cagrildi = []
    monkeypatch.setattr(fm, "firmware_indir", lambda *a, **k: cagrildi.append(a) or (None, ""))
    d = fm.acilis_denetimi(firmware_surum="2.2", stm_bagli=True, uygula=False)
    assert d["eylem"] == su.FIRMWARE_GUNCELLE, "plan yine de hesaplanmalıydı"
    assert not cagrildi and d["uygulandi"] is False


# ──────────────────────────────────────────────────────────────────────────
# 5) TEK KAYNAK + DURDURMA YÜZEYİ YOK
# ──────────────────────────────────────────────────────────────────────────


def test_indirme_zinciri_update_managerDAN(fm):
    """İkinci bir indirici = ikinci bir güvenlik yüzeyi. Host-pin/tavan ORADAN gelmeli."""
    kaynak = __import__("pathlib").Path(fm.__file__).read_text(encoding="utf-8")
    for beklenen in ("_validate_installer_url", "_download_to", "_private_temp_path"):
        assert f"um.{beklenen}" in kaynak, f"{beklenen} yeniden yazılmış olabilir"


def test_ACIL_DURDURMA_yuzeyi_ACILMAMIS(fm):
    """⚠️ Bu modül seansı/E-stop'u engelleyen bir şey dışa açmamalı."""
    disa_acik = {a for a in dir(fm) if not a.startswith("_")}
    yasak = {"estop", "emergency", "seans_engelle", "acil_durdur", "session_block"}
    assert not (disa_acik & yasak), f"durdurma yüzeyi açılmış: {disa_acik & yasak}"


# ──────────────────────────────────────────────────────────────────────────
# 6) AÇILIŞ SIRASI — client kontrolünden SONRA, servis açılmadan ÖNCE
# ──────────────────────────────────────────────────────────────────────────


def test_KRITIK_acilis_SIRASI_client_kontrolunden_SONRA():
    """Sahip: *"ilk açılışta client güncelleme kontrol ediyor zaten, ARDINDAN stm için de
    kontrol etcek… sonra açılacak."*

    ⚠️ SIRA ASIL İDDİADIR, varlık değil: `_donanim_guncellemesi_safe` çağrısının var olması
    hiçbir şey kanıtlamaz — client kontrolünün ÜSTÜNE alınırsa client sürümü henüz
    belirlenmemiş olur ve uyum kararı YANLIŞ girdiyle verilir. Sıra AST'den okunur.
    """
    import ast

    from utils.path_utils import kaynak_kokunu_bul

    kok = kaynak_kokunu_bul(__file__)
    kaynak = (kok / "apps" / "backend" / "backend_service.py").read_text(encoding="utf-8")
    agac = ast.parse(kaynak)
    ana = next(d for d in ast.walk(agac) if isinstance(d, ast.FunctionDef) and d.name == "main")

    def _satirlar(ad: str) -> list[int]:
        return [d.lineno for d in ast.walk(ana) if isinstance(d, ast.Call) and getattr(d.func, "id", "") == ad]

    client = _satirlar("_start_update_checker_safe")
    donanim = _satirlar("_donanim_guncellemesi_safe")
    assert client, "client güncelleme kontrolü çağrısı YOK — çıpa bayat"
    assert donanim, "donanım güncellemesi çağrısı YOK — açılışa bağlanmamış"
    assert min(client) < min(donanim), (
        f"SIRA BOZUK: client kontrolü satır {min(client)}, donanım {min(donanim)}. "
        "Firmware uyumu client sürümüne bağlıdır; o belli olmadan karar verilemez."
    )

    # Servis AÇILMADAN önce olmalı: `server.run()` daha sonra gelmeli.
    kosum = [d.lineno for d in ast.walk(ana) if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "run"]
    assert kosum and min(donanim) < min(kosum), (
        "donanım güncellemesi servis açıldıktan SONRA koşuyor — sahip 'sonra açılacak' dedi"
    )


#: Y1 (sahip, 2026-09-29): oto-firmware VARSAYILAN KAPALI — yalnız AÇIK '1' otomatik uygular; değişken yoksa ya da
#: başka HER değerde yalnız ölçülür (plan hesaplanır, yakılmaz).
_BAYRAK_KOLLARI = [
    (None, False),
    ("0", False),
    ("false", False),
    ("False", False),
    ("", False),
    ("true", False),
    ("yes", False),
    ("2", False),
    ("1", True),
    (" 1 ", True),
]


@pytest.mark.parametrize("deger,uygular", _BAYRAK_KOLLARI)
def test_KRITIK_kill_switch_DEGERI_olculur_Y1_D1107(fm, monkeypatch, deger, uygular):
    """GERÇEK `backend_service._donanim_guncellemesi_safe` → GERÇEK `acilis_denetimi`: ayrıştırılabilir banner, yakmayı
    gerektiren manifest kuralı; `_firmware_uygula` (indir + yak) KAYITÇI — gerçek indirme/yakma YOK. Ölçülen: otomatik
    yakma kararı `PEMF_FW_AUTO_UPDATE`'in DEĞERİNE bağlı (Y1: yalnız açık '1').

    ⚠️ D1.107 (B-10.39): eski kapı (`test_kill_switch_VAR`) yalnız AST'de `os.environ.get("PEMF_FW_AUTO_UPDATE")`
    ÇAĞRISININ VARLIĞINI arıyordu — `uygula=bool(os.environ.get(...))` ('0' → AÇIK) ya da varsayılanın '1' kalması onu
    YEŞİL bırakıyordu. Bu kapı değeri davranışla ölçer.
    """
    import backend_service as bs
    from utils.stm32_kimlik import banner_ayristir
    from utils.surum_uyumu import surum_demeti

    kimlik = banner_ayristir("-> STM_READY: 2.3.0 (7-ch KARMA uni=0x60 + HW_SYNC@PB1) Waiting for commands...")
    assert kimlik is not None and surum_demeti(kimlik.surum) is not None, "aparat: banner ayrıştırılamadı (kapı kör)"
    monkeypatch.setattr(
        fm, "manifest_oku", lambda **_k: _manifest(fw_surum="2.4", kurallar=[{"clientMin": "", "firmwareMin": "2.4"}])
    )
    yakilan = []
    monkeypatch.setattr(fm, "_firmware_uygula", lambda girdi, plan, *a, **k: yakilan.append(plan.hedef_surum) or {})
    if deger is None:
        monkeypatch.delenv("PEMF_FW_AUTO_UPDATE", raising=False)
    else:
        monkeypatch.setenv("PEMF_FW_AUTO_UPDATE", deger)

    class _Gunluk:
        def __getattr__(self, ad):
            return lambda *a, **k: None

    bs._donanim_guncellemesi_safe(SimpleNamespace(stm_kimlik=kimlik, stm_is_connected=True), _Gunluk())
    d = fm.durum()
    assert d["eylem"] == su.FIRMWARE_GUNCELLE, f"aparat: plan yakmayı GEREKTİRMEDİ — kapı kör olurdu: {d}"
    if uygular:
        assert yakilan == ["2.4"], f"PEMF_FW_AUTO_UPDATE={deger!r} (açık '1') iken plan UYGULANMADI: {yakilan}"
    else:
        assert yakilan == [], (
            f"PEMF_FW_AUTO_UPDATE={deger!r} iken otomatik YAKMA uygulandı — Y1: yalnız açık '1' uygular; değişken "
            "yoksa ya da başka bir değerse yalnız ÖLÇÜLÜR"
        )
        assert d["uygulandi"] is False, d
