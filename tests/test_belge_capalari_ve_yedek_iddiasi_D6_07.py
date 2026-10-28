# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.07 (B-4.22 · B-4.23 · B-4.24) — yorum ve README iddiaları KODUN BUGÜNKÜ hâliyle aynı.

ÖLÇÜLEN (HEAD ebf1c3fe, 2026-10-28):
  (a) `servers/auto_discovery.py` kardeş dosyaya iki SATIR çapası veriyordu — `mdns_service.py:219-236` ("ServiceInfo'yu
      SIFIRDAN kuruyor") ve `mdns_service.py:222-223` ("Audit P3: stop() sonrası callback re-publish etmesin"). O satırlarda
      ad-çakışması kodu (`NonUniqueNameException`, `import string`) duruyor; guard `MDNSService._reregister_mqtt`in ilk deyimi.
      Guard'ı "gereksiz" sanıp silen biri kasıtlı kaldırılmış `_pemfvet` servisini DİRİLTİR (B-4.23).
  (b) `services/README.md` "Bu servisler `headless_core.py` tarafından oluşturulur" diyordu; `headless_core` yalnız üç denetleyiciyi
      örnekliyor, `CredentialManager`ı HİÇBİR üretim kodu içe aktarmıyor (elle koşulan CLI) — iki README onu çalışan servis gibi
      anlatıyordu (B-4.24).
  (c) `api_server._daily_maintenance_loop` docstring'i "Gunluk .db yedek … (shutil.copy2)" vaat ediyordu; gövdede yedek çağrısı YOK
      ("3) GUNLUK YEDEK: BURADA YAPILMIYOR"). `sqlcipher_util._kilit_direncli_tasi`in 6 sn bütçe gerekçesi suçluyu bu var olmayan
      kopyalayıcı olarak gösteriyordu (B-4.22).

Kapı yalnız dosya okur ve AST ayrıştırır; ürün kodu İÇE AKTARILMAZ.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
BE = KOK / "apps" / "backend"
MDNS = BE / "services" / "mdns_service.py"
AUTO = BE / "servers" / "auto_discovery.py"
MDNS_TESTI = KOK / "tests" / "test_pemfvet_mdns_yeniden_kayit.py"
SERVIS_README = BE / "services" / "README.md"
CONFIG_README = KOK / "config" / "README.md"

GUARD_GEREKCESI = "Audit P3: stop() sonrası callback re-publish etmesin"


def _oku(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _agac(p: Path) -> ast.Module:
    return ast.parse(_oku(p), filename=str(p))


def _sinif_metodu(agac: ast.Module, sinif: str, metod: str) -> ast.FunctionDef | None:
    for d in agac.body:
        if isinstance(d, ast.ClassDef) and d.name == sinif:
            for m in d.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == metod:
                    return m
    return None


def _modul_islevi(agac: ast.Module, ad: str) -> ast.FunctionDef | None:
    for d in agac.body:
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and d.name == ad:
            return d
    return None


def _cagri_adlari(dugum: ast.AST) -> set[str]:
    adlar: set[str] = set()
    for d in ast.walk(dugum):
        if isinstance(d, ast.Call):
            f = d.func
            if isinstance(f, ast.Name):
                adlar.add(f.id)
            elif isinstance(f, ast.Attribute):
                adlar.add(f.attr)
    return adlar


def _govde_docstringsiz(fn: ast.FunctionDef) -> list[ast.stmt]:
    g = list(fn.body)
    if g and isinstance(g[0], ast.Expr) and isinstance(getattr(g[0], "value", None), ast.Constant):
        g = g[1:]
    return g


# ── (a) mDNS çapaları ────────────────────────────────────────────────────────────────────────────────────────────────


SATIR_CAPASI = re.compile(r"mdns_service\.py:(\d+)(?:-(\d+))?")
ALINTI = re.compile(r'"([^"]{8,})"')


def test_mdns_satir_capalari_GOSTERDIGI_satirda_alintiyi_tasir():
    """`mdns_service.py:N[-M]` biçimli her çapa, aynı satırdaki "alıntı"yı N..M aralığında TAŞIMALI; alıntısız satır çapası
    kayar ve doğrulanamaz → ADla verilmeli (`MDNSService._reregister_mqtt`)."""
    hedef = _oku(MDNS).splitlines()
    bozuk = []
    for kaynak in (AUTO, MDNS_TESTI):
        for no, satir in enumerate(_oku(kaynak).splitlines(), 1):
            for m in SATIR_CAPASI.finditer(satir):
                bas = int(m.group(1))
                son = int(m.group(2) or bas)
                aralik = "\n".join(hedef[bas - 1 : son])
                alintilar = ALINTI.findall(satir[m.end() :])
                if not alintilar:
                    bozuk.append(f"{kaynak.name}:{no} alıntısız satır çapası {m.group(0)} (kayar — ADla verin)")
                elif not any(a in aralik for a in alintilar):
                    bozuk.append(f"{kaynak.name}:{no} {m.group(0)} gösterdiği satırlarda {alintilar[0]!r} YOK")
    assert not bozuk, "mdns_service satır çapası kaymış / doğrulanamıyor:\n" + "\n".join(bozuk)


def test_auto_discovery_ad_capasi_GUARDLI_ve_SIFIRDAN_kuran_metodu_gosterir():
    metin = _oku(AUTO)
    assert "MDNSService._reregister_mqtt" in metin, (
        "auto_discovery gerekçe çapası `MDNSService._reregister_mqtt` adını vermiyor"
    )
    assert GUARD_GEREKCESI in metin, "auto_discovery guard gerekçesini (Audit P3) alıntılamıyor"
    # Ad çapasının her `MDNSService.<ad>` başvurusu gerçekten var olan bir metoda çıkmalı.
    agac = _agac(MDNS)
    for ad in sorted(set(re.findall(r"MDNSService\.(\w+)", metin))):
        assert _sinif_metodu(agac, "MDNSService", ad) is not None, (
            f"auto_discovery `MDNSService.{ad}` diyor; böyle bir metot YOK"
        )

    fn = _sinif_metodu(agac, "MDNSService", "_reregister_mqtt")
    assert fn is not None, "MDNSService._reregister_mqtt YOK — çapa boşa düştü"
    ilk = _govde_docstringsiz(fn)[0]
    guard_mu = (
        isinstance(ilk, ast.If)
        and isinstance(ilk.test, ast.UnaryOp)
        and isinstance(ilk.test.op, ast.Not)
        and isinstance(ilk.test.operand, ast.Attribute)
        and ilk.test.operand.attr == "_running"
        and len(ilk.body) == 1
        and isinstance(ilk.body[0], ast.Return)
    )
    assert guard_mu, (
        "_reregister_mqtt'in ilk deyimi `if not self._running: return` guard'ı DEĞİL (çapanın gerekçesi yok)"
    )
    satir = _oku(MDNS).splitlines()[ilk.body[0].lineno - 1]
    assert GUARD_GEREKCESI in satir, "guard satırı 'Audit P3' gerekçesini taşımıyor"
    cagrilar = _cagri_adlari(fn)
    assert {"_build_service_info", "register_service"} <= cagrilar, (
        "_reregister_mqtt ServiceInfo'yu SIFIRDAN kurmuyor (_build_service_info + register_service yok)"
    )


# ── (b) services/README + config/README ─────────────────────────────────────────────────────────────────────────────

HC_IFADESI = "`headless_core.py` tarafından oluşturulur"


def test_services_readme_headless_core_OLUSTURUR_dedigi_her_sinif_orada_orneklenir():
    metin = _oku(SERVIS_README)
    tablo_siniflari = re.findall(r"\*\*`([A-Z]\w+)`\*\*", metin)
    satirlar = [s for s in metin.splitlines() if HC_IFADESI in s]
    assert satirlar, f"services/README '{HC_IFADESI}' cümlesini kaybetti (kapı boşa düşer)"
    orneklenen = _cagri_adlari(_agac(BE / "headless_core.py"))
    eksik = []
    for s in satirlar:
        once = s.split(HC_IFADESI, 1)[0]
        ozne = re.findall(r"`([A-Z][A-Za-z]+)`", once)
        if not ozne:  # "Bu servisler …" → tablodaki BÜTÜN sınıflar
            ozne = tablo_siniflari
        eksik += [ad for ad in ozne if ad not in orneklenen]
    assert not eksik, (
        f"services/README bu sınıfları `headless_core.py` oluşturur diyor ama orada örneklenmiyor: {eksik}"
    )


def test_services_readme_diger_olusturuculari_dogru_anlatir():
    metin = _oku(SERVIS_README)
    hs = _agac(BE / "services" / "headless_services.py")
    ms = next(d for d in hs.body if isinstance(d, ast.ClassDef) and d.name == "MosquittoSupervisor")
    assert "MDNSService" in _cagri_adlari(ms), (
        "MDNSService'i MosquittoSupervisor örneklemiyor — README cümlesi bayatladı"
    )
    assert "`MDNSService`'i `MosquittoSupervisor` oluşturur" in metin
    hdm = _modul_islevi(_agac(BE / "services" / "headless_db_maintenance.py"), "start_headless_db_maintenance")
    assert hdm is not None and "HeadlessDBMaintenance" in _cagri_adlari(hdm)
    bs = _modul_islevi(_agac(BE / "backend_service.py"), "_start_db_maintenance")
    assert bs is not None and "start_headless_db_maintenance" in _cagri_adlari(bs)
    assert "`start_headless_db_maintenance` ile başlar" in metin


def _credential_manager_ice_aktaranlar() -> list[str]:
    bulunan = []
    for p in sorted(BE.rglob("*.py")):
        if p.name == "credential_manager.py" or "node_modules" in p.parts:
            continue
        try:
            agac = _agac(p)
        except SyntaxError:
            continue
        for d in ast.walk(agac):
            if isinstance(d, ast.ImportFrom):
                adlar = [d.module or ""] + [a.name for a in d.names]
            elif isinstance(d, ast.Import):
                adlar = [a.name for a in d.names]
            else:
                continue
            if any(a.split(".")[-1] == "credential_manager" for a in adlar):
                bulunan.append(str(p.relative_to(KOK)))
    return bulunan


def test_credential_manager_CLI_diye_anlatilir_calisan_servis_diye_DEGIL():
    aktaranlar = _credential_manager_ice_aktaranlar()
    assert not aktaranlar, (
        f"credential_manager artık üretim kodunda içe aktarılıyor ({aktaranlar}) — README'lerdeki 'elle koşulan CLI' "
        "anlatımını yeniden ölçün"
    )
    cm = _agac(BE / "services" / "credential_manager.py")
    assert _modul_islevi(cm, "main") is not None, "credential_manager CLI giriş noktası (main) YOK"
    bozuk = []
    for p in (SERVIS_README, CONFIG_README):
        for no, s in enumerate(_oku(p).splitlines(), 1):
            if "credential_manager" not in s or s.startswith("İlgili:"):
                continue
            if "CLI" not in s:
                bozuk.append(f"{p.relative_to(KOK)}:{no} credential_manager'ı CLI diye anlatmıyor")
            if re.search(r"tarafından (üretilir|tüketilir|oluşturulur)", s):
                bozuk.append(
                    f"{p.relative_to(KOK)}:{no} credential_manager'a çalışma-anı üretici/tüketici rolü veriyor"
                )
    assert not bozuk, "\n".join(bozuk)
    # Yazdığı yer deponun config/credentials'ı değil, veri kökü.
    assert re.search(
        r'CREDENTIALS_DIR = _APP_DATA_DIR / "config" / "credentials"', _oku(BE / "services" / "credential_manager.py")
    )
    assert "`<veri kökü>/config/credentials/`" in _oku(SERVIS_README)
    assert "`<veri kökü>/config/credentials/`" in _oku(CONFIG_README)


# ── (c) günlük döngü yedek iddiası ──────────────────────────────────────────────────────────────────────────────────

YEDEK_CAGRILARI = {"copy2", "copyfile", "copy", "copyfileobj", "create_backup", "backup", "yedek_yaz"}


def _bakim_dongusu() -> ast.FunctionDef:
    fn = _modul_islevi(_agac(BE / "servers" / "api_server.py"), "_daily_maintenance_loop")
    assert fn is not None, "api_server._daily_maintenance_loop YOK — kapıyı yeniden ölçün"
    return fn


def test_gunluk_bakim_docstringi_govdede_OLMAYAN_yedegi_vaat_etmez():
    fn = _bakim_dongusu()
    doc = ast.get_docstring(fn) or ""
    yedek_cagrisi = _cagri_adlari(ast.Module(body=_govde_docstringsiz(fn), type_ignores=[])) & YEDEK_CAGRILARI
    if yedek_cagrisi:  # gövde yeniden yedek alıyorsa bu kol iddiayı denetlemez
        return
    assert "copy2" not in doc, "docstring `copy2` yedeğini anıyor; gövdede yedek çağrısı YOK"
    assert not re.search(r"Gunluk \.db yedek\s*:", doc), "docstring günlük .db yedeğini döngünün işi gibi listeliyor"
    assert "YEDEK ALMAZ" in doc and "headless_db_maintenance" in doc, (
        "docstring yedeğin bu döngüde ALINMADIĞINI ve gerçek yedekleyiciyi (headless_db_maintenance) söylemiyor"
    )


def test_kilit_butcesi_gerekcesi_bakim_dongusunu_KOPYALAYICI_diye_suclamaz():
    fn = _bakim_dongusu()
    if _cagri_adlari(fn) & YEDEK_CAGRILARI:
        return
    tasi = _modul_islevi(_agac(BE / "database" / "sqlcipher_util.py"), "_kilit_direncli_tasi")
    assert tasi is not None
    doc = ast.get_docstring(tasi) or ""
    paragraflar = [p for p in re.split(r"\n\s*\n", doc) if "_daily_maintenance_loop" in p]
    assert paragraflar, (
        "bütçe gerekçesi eski suçluyu (_daily_maintenance_loop) artık hiç anmıyor — kapıyı yeniden ölçün"
    )
    for p in paragraflar:
        assert "copy2" not in p, "bütçe gerekçesi _daily_maintenance_loop'u hâlâ `copy2` kopyalayıcısı diye anlatıyor"
        assert "KALDIRILDI" in p and "headless_db_maintenance" in p, (
            "bütçe gerekçesi kopyalayıcının KALDIRILDIĞINI ve gerçek yedekleyiciyi söylemiyor"
        )
