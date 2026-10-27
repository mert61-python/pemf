# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SÜRÜM GÖRÜNÜRLÜĞÜ — "hangi sürüm koşuyor?" doğru cevaplanmalı (2026-08-09 denetimi, Tier 3).

ARIZA: `X-API-Version`, FastAPI `/docs` ve keşif yanıtları sahaya **1.4.1** diyordu. O sayı
`frontendOta` kanalının sürümüdür (`frontend_version.json`); backend'in sürümü `VERSION` =
**1.9.5**. `utils.path_utils.get_app_version()` yanlış kanalı ÖNCE okuyordu — oysa
`update_manager._version_paths()` doğrusunu yapıyordu; iki yer ayrışmıştı.

Neden önemli: sürüm sessiz-otomatik güncellenen bir tıbbi cihazda olay teşhisinin ilk verisidir.
Yanlışsa destek altı sürüm geriye bakar, düzeltilmiş bir hatayı yeniden arar.

Ayrıca `buildId`: aynı sürüm numarası farklı paket içeriği çalıştırabilir (yeniden yayın, yarım
güncelleme, elle kopyalanan dosya). Launcher kurduğu paketin sha'sını `PEMF_BASE_SHA` ile
geçirir; kısaltılmışı "hangi ikili" sorusunu tek başına cevaplar.
"""

import json
import re
from pathlib import Path

import capraz
import pytest
from fastapi.testclient import TestClient

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 51234))


def _temiz_surum():
    """Cache'lenmiş sürümü sıfırla — sıra testleri gerçek okumayı görmeli."""
    from utils import path_utils

    path_utils._APP_VERSION = None


# ── doğru kanal ─────────────────────────────────────────────────────────────


def test_KRITIK_surum_BACKEND_kanalindan_okunur():
    _temiz_surum()
    from utils.path_utils import get_app_version

    beklenen = (KOK / "VERSION").read_text(encoding="utf-8").strip()
    assert get_app_version() == beklenen, "app surumu VERSION (backend kanali) yerine baska kanaldan okunuyor"


def test_KRITIK_frontendOta_surumu_app_surumu_SANILMAZ():
    _temiz_surum()
    from utils.path_utils import get_app_version

    fo = str(json.loads((KOK / "frontend_version.json").read_text(encoding="utf-8"))["version"])
    v = get_app_version()
    if fo != (KOK / "VERSION").read_text(encoding="utf-8").strip():
        assert v != fo, f"app surumu frontendOta kanalindan ({fo}) okunuyor"


def test_iki_surum_kaynagi_AYRISMAZ():
    """`path_utils` ile `update_manager` aynı cevabı vermeli — ayrışma bu arızanın kökeniydi."""
    _temiz_surum()
    from servers.update_manager import get_current_version
    from utils.path_utils import get_app_version

    assert get_app_version() == get_current_version(), "path_utils ve update_manager farkli surum raporluyor"


def test_VERSION_dosyasi_yoksa_frontend_version_a_DUSER(tmp_path, monkeypatch):
    """Geriye uyum: eski paketlerde `VERSION` bundle'lanmamış olabilir."""
    from utils import path_utils

    _temiz_surum()
    monkeypatch.setattr(path_utils, "packaged_resource_path", lambda *p: tmp_path / "yok")
    monkeypatch.setattr(Path, "read_text", Path.read_text)  # gerçek okuma korunur
    # gerçek depo kökündeki VERSION'ı gizle
    gercek = Path.exists

    def sahte_exists(self):
        return False if self.name == "VERSION" else gercek(self)

    monkeypatch.setattr(Path, "exists", sahte_exists)
    v = path_utils.get_app_version()
    _temiz_surum()
    assert v, "VERSION yokken hicbir surum uretilmedi"


# ── HTTP yüzeyi ─────────────────────────────────────────────────────────────


def test_X_API_Version_headeri_DOGRU(client):
    r = client.get("/api/health")
    beklenen = (KOK / "VERSION").read_text(encoding="utf-8").strip()
    assert r.headers.get("X-API-Version") == beklenen, (
        f"X-API-Version yanlis: {r.headers.get('X-API-Version')} != {beklenen}"
    )


def test_health_SURUMU_bildirir(client):
    g = client.get("/api/health").json()
    assert g.get("version"), "health surumu hic bildirmiyor — teshisin ilk verisi eksik"
    assert g["version"] == (KOK / "VERSION").read_text(encoding="utf-8").strip()


# ── buildId ─────────────────────────────────────────────────────────────────


def test_buildId_launcher_sha_sindan_TURER(monkeypatch):
    from utils import path_utils

    monkeypatch.setenv("PEMF_BASE_SHA", "ABCDEF0123456789" + "0" * 48)
    assert path_utils.get_build_id() == "abcdef012345"


def test_KRITIK_buildId_UYDURULMAZ(monkeypatch):
    """Launcher'sız çalıştırmada sahte bir kimlik üretmek, olay kaydını yanlış yönlendirir."""
    from utils import path_utils

    monkeypatch.delenv("PEMF_BASE_SHA", raising=False)
    assert path_utils.get_build_id() == ""
    monkeypatch.setenv("PEMF_BASE_SHA", "kisa")
    assert path_utils.get_build_id() == "", "gecersiz sha'dan kimlik uretildi"


def test_buildId_yokken_header_EKLENMEZ(client):
    """Boş bir `X-Build-Id` "kimlik yok" değil "kimlik boş" diye okunur."""
    from servers import api_server

    if api_server._BUILD_ID:
        pytest.skip("bu ortamda PEMF_BASE_SHA tanimli")
    assert "X-Build-Id" not in client.get("/api/health").headers


# ── CHANGELOG kapısı ────────────────────────────────────────────────────────


def test_KRITIK_CHANGELOG_guncel_surumleri_ICERIR():
    """Sessiz otomatik güncellenen bir cihazda "ne değişti" cevapsız kalmamalı: sürüm
    yükseltmek CHANGELOG'a dokunmayı ZORUNLU kılar.

    ⚠️ SAĞLAMLAŞTIRILDI (2026-08-23): kapı eskiden ham `s not in metin` yapıyordu, yani sürüm
    dizesinin dosyanın HERHANGİ bir yerinde geçmesi yeterliydi. Bu YANLIŞ-YEŞİL üretiyor ve
    ölçülerek yakalandı: backend 1.9.20'ye çıkarıldığında kapı GEÇTİ — çünkü "1.9.20" CHANGELOG'da
    2026-08-11 tarihli bir **launcher** sürümü olarak zaten geçiyordu. Yani app 1.9.20'nin kaydı
    hiç yazılmasa da kapı yeşil kalırdı; koruma tam da korumayı bıraktığı anda görünmez oluyordu.
    Sürüm numaraları kanallar arasında tekrar ettiği için (app 1.9.x ve launcher 1.9.x aynı
    aralıkta) bu kaçınılmazdı.

    Doğru ölçü: sürüm KENDİ KANALININ başlığında geçmeli — `## app 1.9.20 — …`,
    `## launcher 1.9.35 — …`, `## mobile 2.3.22 — …`. Birleşik başlıklar da geçerlidir
    (`## app 1.9.9 · launcher 1.9.20 — …`).
    """
    ch = KOK / "CHANGELOG.md"
    assert ch.exists(), "CHANGELOG.md yok"
    metin = ch.read_text(encoding="utf-8")
    v = json.loads((KOK / "versions.json").read_text(encoding="utf-8"))
    # versions.json anahtarı → CHANGELOG başlığındaki kanal adı.
    kanallar = (
        ("launcher", "launcher", v["launcher"]),
        ("mobile", "mobile", v["mobile"]["name"]),
        ("backend", "app", v["backend"]),
    )
    eksik = [
        f"{ad}={surum} (aranan: '## … {kanal} {surum}')"
        for ad, kanal, surum in kanallar
        if not re.search(rf"^##[^\n]*\b{kanal}\s+{re.escape(surum)}\b", metin, re.M)
    ]
    assert not eksik, (
        f"versions.json'daki surum(ler) CHANGELOG'da KENDI KANALININ basligiyla gecmiyor: {eksik}. "
        "Surum yukseltildiyse degisiklik kaydi da yazilmali. (Dosyanin baska bir yerinde ayni "
        "sayinin gecmesi YETMEZ — surum numaralari kanallar arasinda tekrar ediyor.)"
    )


def test_KRITIK_F7_pre_commit_kancasi_CI_ile_BIREBIR_kanal_basligi():
    """🔴 F7/BLD-3 (denetim 2026-08-24): pre-commit `scripts/check_changelog_surum.py` ham
    `s not in metin` (substring) yapıyordu; CI (yukarıdaki `test_KRITIK_CHANGELOG_guncel_surumleri`)
    2026-08-23'te kanal-başlıklı regex'e sertleştirildi. Betiğin KENDİ docstring'i 'mantık test ile
    BİREBİR aynı tutulur' der — ama ayrışmıştı. Sonuç: cross-kanal bir sürüm (ör. backend, mevcut
    launcher sürümüyle AYNI numaraya çekilince) pre-commit YANLIŞ-YEŞİL verir, eksik CHANGELOG
    push'tan SONRA CI'da kırmızı döner ('Run failed e-postasından önce yakala' — kancanın var oluş
    sebebi — kaybolur). Betik, CI ile AYNI kanal-başlıklı kontrolü yapmalı."""
    import sys as _sys

    _sys.path.insert(0, str(KOK / "scripts"))
    import importlib

    mod = importlib.import_module("check_changelog_surum")
    assert hasattr(mod, "_eksik_kanallar"), (
        "check_changelog_surum saf `_eksik_kanallar` (kanal-başlıklı regex) fonksiyonu SUNMUYOR — "
        "hâlâ ham substring; CI ile ayrışık (F7)"
    )
    # Cross-kanal senaryo: backend sürümü CHANGELOG'da SADECE bir 'launcher' başlığında geçiyor.
    changelog = "## launcher 1.9.37 — 2026-08-24\ndegisiklik\n\n## mobile 2.3.23 — 2026-08-24\ndegisiklik\n"
    v = {"launcher": "1.9.37", "mobile": {"name": "2.3.23"}, "backend": "1.9.37"}  # backend = launcher numarası
    eksik = mod._eksik_kanallar(changelog, v)
    assert "backend=1.9.37" in eksik, (
        "pre-commit backend 1.9.37'yi (yalnız launcher başlığında geçen numara) 'var' saydı — ham "
        "substring; CI kanal-başlıklı regex ('## app 1.9.37') ile ayrışık (F7 yanlış-yeşil)"
    )
    # Karşıt-kanıt: KENDİ kanal (app) başlığında geçen backend sürümü EKSİK sayılmamalı.
    changelog2 = changelog + "## app 1.9.37 — 2026-08-24 backend kaydi\n"
    assert "backend=1.9.37" not in mod._eksik_kanallar(changelog2, v), (
        "app başlığındaki backend sürümü yanlışlıkla eksik sayıldı (kapı fazla katı)"
    )


def test_KRITIK_site_APK_surumu_versions_json_ile_AYNI():
    """Sitedeki APK indirme adı (`PEMF_Vet_Mobil-<sürüm>.apk`) gerçek mobil sürümle eşleşmeli.

    ⚠️ ANDROID'DE ÇIPA YOK. Windows kurulum dosyasının adı `windowsTag`ten TÜRETİLİR, yani
    etiket yükselince ad kendiliğinden doğrudur. Android'in yayın etiketi `launcher-v*` olduğu
    için mobil sürüm site yapılandırmasında AYRICA tutulur — ve elle tutulan her değer ayrışır:
    APK yükseltilip `androidVersion` unutulursa site var olmayan bir dosyaya link verir ve
    indirme butonu **sessizce 404** olur.

    (Bu boşluk mutasyon testiyle bulundu: `androidVersion`ı uydurma bir sürüme çevirmek site
    testlerinin HİÇBİRİNİ kırmıyordu.)"""
    cfg = KOK / "apps/web" / "src" / "config.ts"
    capraz.atla_yoksa("apps/web/src/config.ts", izlenen=True)  # D5-F: eski düz pytest.skip — ZORUNLU kipte DÜŞER
    beklenen = json.loads((KOK / "versions.json").read_text(encoding="utf-8"))["mobile"]["name"]
    m = re.search(r"androidVersion:\s*'([^']+)'", cfg.read_text(encoding="utf-8"))
    assert m, "site config'inde androidVersion bulunamadı"
    assert m.group(1) == beklenen, (
        f"site APK sürümü ({m.group(1)}) versions.json ile ayrışmış ({beklenen}) → "
        f"indirme bağlantısı var olmayan PEMF_Vet_Mobil-{m.group(1)}.apk dosyasına gider (404)"
    )


def _yayin_kimlikleri(m: dict) -> list[tuple[str, str]]:
    """Sahadaki `buildId`nin kaynağı (platform, sha256) — launcher `install.rs` `PEMF_BASE_SHA`: katmanlı kurulumda `app` katmanının
    sha'sı (`record_layer_sha("app", …)`), katmansızda tek parça paketin (`runtimes[platform]` / `base`) sha'sı. client ≥1.9.13 `layers`ı
    okur, `runtimes` / `base`ı YOK SAYAR (manifest `_layers_note`) → `layers` varsa kimlik YALNIZ oradan (`deps` kimlik DEĞİL)."""
    katman = m.get("layers") or {}
    if katman:
        return [(p, ((k or {}).get("app") or {}).get("sha256", "")) for p, k in sorted(katman.items())]
    tek = m.get("runtimes") or {}
    if tek:
        return [(p, (r or {}).get("sha256", "")) for p, r in sorted(tek.items())]
    base = m.get("base")
    return [("base", (base or {}).get("sha256", ""))] if base else []


def _buildid_bulgulari(m: dict, changelog: str) -> list[str]:
    """Yayındaki paketin kimliği CHANGELOG'da YAYINDAKİ sürümün bölümünde (`## app <manifest.version> — …`; kanal başlığı ` — `dan
    önce) geçmeli. Boş liste = temiz. Dosyanın başka bir yerinde (başka sürümün bölümünde) geçmesi YETMEZ."""
    kimlikler = _yayin_kimlikleri(m)
    if not kimlikler:
        return [
            "manifestte yayın kimliği YOK (layers / runtimes / base) — sahadan gelen buildId hiçbir kayıtla eşleştirilemez"
        ]
    surum = str(m.get("version") or "")
    bolum = (
        re.search(rf"^##[^\n—]*\bapp\s+{re.escape(surum)}\b[^\n]*\n(.*?)(?=^## |\Z)", changelog, re.M | re.S)
        if surum
        else None
    )
    if bolum is None:
        return [f"CHANGELOG'da yayındaki sürümün bölümü yok (aranan: '## app {surum} — …')"]
    bulgu = []
    for platform, sha in kimlikler:
        if not re.fullmatch(r"[0-9a-f]{64}", sha or ""):
            bulgu.append(f"{platform}: geçersiz / boş sha256 {sha!r}")
        elif sha[:12] not in bolum.group(1):
            bulgu.append(f"{platform}: {sha[:12]} 'app {surum}' bölümünde yok")
    return bulgu


def test_CHANGELOG_yayindaki_paket_shasini_ICERIR():
    """`buildId` sahadan (ör. `cb33f48382a2`) gelince karşılığı YAYINDAKİ sürümün CHANGELOG bölümünde bulunabilmeli.

    D5-L (L-3.3): kapı eskiden manifestin `base.sha256`ını arıyordu — katmanlı şemada (`layers`) `base` YOK → HER ortamda, ZORUNLU
    kipte de ATLIYORDU (ölü kapı; CHANGELOG'dan kimlik silinince de "skipped" — mutantla ölçüldü). Kimlik artık launcher'ın geçirdiği
    sha'dan (`_yayin_kimlikleri`) ve yalnız o sürümün bölümünde aranır."""
    capraz.atla_yoksa("pemf-app-packages/manifest.json", izlenen=True)  # D5-F: İZLENEN dosya — ZORUNLU kipte DÜŞER
    m = json.loads((KOK / "pemf-app-packages" / "manifest.json").read_text(encoding="utf-8"))
    bulgu = _buildid_bulgulari(m, (KOK / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert not bulgu, (
        "yayindaki paketin kimligi CHANGELOG'da yayindaki surumun bolumunde yok — sahadan gelen buildId hicbir kayitla "
        f"eslesmez: {bulgu}"
    )


def test_KARSIT_buildId_kapisi_KATMAN_kimligini_ve_SURUM_bolumunu_ayirt_eder():
    """Kapının aracı kör değil: sentetik manifest + CHANGELOG ile her kol hem temiz hem kirli girdide ölçülür."""
    app, dep, eski = "a1" * 32, "b2" * 32, "c3" * 32
    ch = (
        "# Değişiklikler\n\n"
        "## launcher 1.9.52 — YAYIN ADAYI (YAYINLANMADI; app 1.9.51 ile birlikte)\n\nkimlik yok\n\n"
        "## app 1.9.51 — YAYINLANMADI\n\nkimlik yok\n\n"
        f"## app 1.9.50 — 2026-09-11\n\nPaket kimliği (`buildId`): `{app[:12]}`. Bağımlılık katmanı `{dep[:12]}`.\n\n"
        f"## app 1.9.49 — 2026-09-10\n\nPaket kimliği (`buildId`): `{eski[:12]}`.\n"
    )
    katmanli = {
        "version": "1.9.50",
        "layers": {"win-x64": {"app": {"sha256": app}, "deps": {"sha256": dep}}},
        "runtimes": {},
    }
    assert _buildid_bulgulari(katmanli, ch) == [], "temiz katmanlı girdi kirli sayıldı"
    # deps katmanının sha'sı kimlik DEĞİL: app kimliği bölümden düşünce (yalnız deps kaldı) kapı DÜŞER
    assert _buildid_bulgulari(katmanli, ch.replace(f"`{app[:12]}`", "`-`")), "app kimliği yokken deps sha'sıyla GEÇTİ"
    # kimlik yalnız BAŞKA sürümün bölümünde (eski ham `in metin` bunu GEÇİRİRDİ)
    baska = {"version": "1.9.50", "layers": {"win-x64": {"app": {"sha256": eski}}}}
    assert _buildid_bulgulari(baska, ch), "kimlik yalnız 1.9.49 bölümündeyken 1.9.50 için GEÇTİ"
    # yayınlanmamış sürüm (başlık açıklamasındaki 'app 1.9.51' bölüm sayılmaz; kendi bölümünde kimlik yok)
    assert _buildid_bulgulari(dict(katmanli, version="1.9.51"), ch), "kimliksiz 1.9.51 bölümü GEÇTİ"
    assert _buildid_bulgulari(dict(katmanli, version="1.9.99"), ch), "bölümü olmayan sürüm GEÇTİ"
    # layers varken base / runtimes YOK SAYILIR (client ≥1.9.13)
    assert _buildid_bulgulari(
        {"version": "1.9.50", "layers": {"win-x64": {"app": {"sha256": eski}}}, "base": {"sha256": app}}, ch
    )
    # tek parça şema (eski launcher) — base / runtimes kimliği
    assert _buildid_bulgulari({"version": "1.9.50", "base": {"sha256": app}}, ch) == []
    assert _buildid_bulgulari({"version": "1.9.50", "runtimes": {"win-x64": {"sha256": app}}}, ch) == []
    # kimliksiz / bozuk manifest → bulgu (ATLAMA DEĞİL)
    assert _buildid_bulgulari({"version": "1.9.50"}, ch), "kimliksiz manifest GEÇTİ"
    assert _buildid_bulgulari({"version": "1.9.50", "layers": {"win-x64": {"deps": {"sha256": dep}}}}, ch), (
        "app'siz katman GEÇTİ"
    )
    assert _buildid_bulgulari({"version": "1.9.50", "layers": {"win-x64": {"app": {"sha256": app[:12]}}}}, ch), (
        "kısa sha GEÇTİ"
    )
