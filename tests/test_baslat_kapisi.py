# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Sahip bildirimi 2026-08-16: "Başlat" güncelleme kontrolü bitmeden çıkıyordu.

ARIZA: kurulu cihazda ekran ADIM 1'de (yerel bilgiyle) çiziliyor ve "Başlat" HEMEN
tıklanabilir oluyor. Güncelleme kontrolü ADIM 2'de (ağ) tamamlanıyor. Kullanıcı tam
"Başlat"a basacakken ekran güncellemeye geçiyor — tıklama boşa gidiyor, veteriner ne
olduğunu anlamıyor.

⚠️ ÇÖZÜM EKRANI DONDURMAK DEĞİL. Ekranı ağ adımı bitene kadar bekletmek, 2026-08-06'da
düzeltilen P0'ı geri getirirdi: internetsiz klinikte client "Ortam algılanıyor…" ekranında
SONSUZA KADAR kalıyor ve kurulum ZATEN VARKEN "Başlat"a hiç ulaşılamıyordu. Bu yüzden ekran
anında çizilir; yalnız DÜĞME beklemeye alınır ve sebebi yazılır ("Güncelleme kontrol ediliyor…").

🔴 EN ÖNEMLİ DEĞİŞMEZ: düğme KALICI kilitlenemez. Çevrimdışı, desteklenmeyen platform,
manifest hatası ve ağ adımının asılması dahil HER çıkışta açılır.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"


@pytest.fixture(scope="module")
def ui() -> str:
    return _UI.read_text(encoding="utf-8")


def _bootnetwork(ui: str) -> str:
    m = re.search(r"async function bootNetwork\(env\) \{(.*?)\n      \}", ui, re.S)
    assert m, "bootNetwork bulunamadı"
    return m.group(1)


# ─────────────────────────────────────────────────────────────────────────────
# Kapı var ve doğru anda kapanıyor mu?
# ─────────────────────────────────────────────────────────────────────────────


def test_KRITIK_kapi_ag_adiminin_BASINDA_kapanir(ui):
    """🔴 ASIL ARIZA: kontrol bitmeden düğme tıklanabiliyordu."""
    g = _bootnetwork(ui)
    assert "startKapisiKapat()" in g, "ağ adımı başlarken kapı kapatılmıyor"
    i_kapat = g.index("startKapisiKapat()")
    i_fetch = g.index('invoke("fetch_profiles")')
    assert i_kapat < i_fetch, "kapı manifest çekiminden SONRA kapanıyor → yarış penceresi açık"


def test_KRITIK_ekran_DONDURULMAZ(ui):
    """🔴 2026-08-06 P0'ı geri getirme: ekran ağ adımını BEKLEMEMELİ.

    `bootLocal` hâlâ ekranı anında çizmeli; kapı yalnız DÜĞMEYİ etkiler.
    """
    m = re.search(r"async function bootLocal\(\) \{(.*?)\n      \}", ui, re.S)
    assert m, "bootLocal bulunamadı"
    g = m.group(1)
    assert 'show("s-ready")' in g, "kurulu cihazda ekran anında çizilmiyor → spinner'da donar"
    assert "await invoke(\"fetch_profiles\")" not in g, "yerel adım ağ bekliyor → ekran donar"


def test_kapi_DUGMEYI_kilitler_ve_SEBEBINI_yazar(ui):
    """Sessizce devre dışı bir düğme kullanıcıyı şaşırtır; ne beklediğini söylemeli."""
    m = re.search(r"function startKapisiKapat\(\) \{(.*?)\n      \}", ui, re.S)
    assert m, "startKapisiKapat bulunamadı"
    g = m.group(1)
    assert "disabled = true" in g, "düğme kilitlenmiyor"
    assert "startChecking" in g, "bekleme sebebi yazılmıyor"


# ─────────────────────────────────────────────────────────────────────────────
# 🔴 KALICI KİLİTLENME OLMAMALI — her çıkışta açılır
# ─────────────────────────────────────────────────────────────────────────────


def test_KRITIK_cevrimdisi_cikisinda_kapi_ACILIR(ui):
    """🔴 İnternetsiz klinikte Başlat çalışmalı — backend yereldir, ağ gerekmez."""
    g = _bootnetwork(ui)
    m = re.search(r"catch \(e\) \{(.*?)\n          return;", g, re.S)
    assert m, "çevrimdışı dalı bulunamadı"
    assert "startKapisiAc()" in m.group(1), "çevrimdışıyken kapı AÇILMIYOR → kurulu cihazda Başlat kalıcı kilitli kalır"


def test_KRITIK_desteklenmeyen_platformda_kapi_ACILIR(ui):
    g = _bootnetwork(ui)
    m = re.search(r"if \(!info\.platform_supported\) \{(.*?)\n        \}", g, re.S)
    assert m, "platform dalı bulunamadı"
    assert "startKapisiAc()" in m.group(1), "desteklenmeyen platformda kapı kilitli kalıyor"


def test_KRITIK_guncelleme_karari_sonrasi_kapi_ACILIR(ui):
    """Güncelleme yoksa ya da arka planda iniyorsa Başlat hemen açılmalı."""
    g = _bootnetwork(ui)
    m = re.search(r"if \(await tryRuntimeUpdate\(\)\) return;\n(.*?)\n", g, re.S)
    assert m and "startKapisiAc()" in m.group(1), (
        "güncelleme kararından sonra kapı açılmıyor → güncelleme gerekmese bile Başlat kilitli"
    )


def test_KRITIK_hazir_ekranina_donunce_kapi_ACILIR(ui):
    """Kurulum/onarım/güncelleme bitince `s-ready` gösterilir — kapı orada açılmalı.

    Bu, `show()` içinde TEK YERDE yapılır: açmayı çıkış yollarına serpiştirmek, biri
    unutulduğunda düğmeyi kalıcı kilitlerdi.
    """
    m = re.search(r"function show\(id\) \{(.*?)\n      \}", ui, re.S)
    assert m, "show bulunamadı"
    g = m.group(1)
    assert 's-ready' in g and "startKapisiAc" in g, (
        "`show('s-ready')` kapıyı açmıyor → kurulum bitince Başlat kilitli kalır"
    )


def test_KRITIK_ag_adimi_ASILIRSA_kapi_yine_ACILIR(ui):
    """🔴 Son emniyet: ağ adımı hiç dönmezse düğme sonsuza dek kilitli kalamaz."""
    m = re.search(r"function startKapisiKapat\(\) \{(.*?)\n      \}", ui, re.S)
    assert m and "setTimeout(startKapisiAc" in m.group(1), "zaman aşımı emniyeti yok"
    z = re.search(r"KAPI_ZAMAN_ASIMI_MS\s*=\s*(\d+)", ui)
    assert z, "zaman aşımı sabiti yok"
    ms = int(z.group(1))
    assert 5000 <= ms <= 60000, f"zaman aşımı makul değil: {ms} ms"


def test_kapi_acilinca_dogru_etiket_geri_gelir(ui):
    """Uygulama çalışıyorsa etiket 'Uygulamaya dön' olmalı, 'Başlat' değil."""
    m = re.search(r"function startKapisiAc\(\) \{(.*?)\n      \}", ui, re.S)
    assert m, "startKapisiAc bulunamadı"
    assert "appRunning ?" in m.group(1), (
        "kapı açılırken 'çalışıyor' durumu yok sayılıyor → uygulama açıkken 'Başlat' yazar"
    )


def test_i18n_iki_dilde_TAM(ui):
    assert ui.count("startChecking:") == 2, "`startChecking` iki dilde de tanımlı olmalı"


# ─────────────────────────────────────────────────────────────────────────────
# DAVRANIŞ — fonksiyonları GERÇEKTEN çalıştır (kaynak okumak yetmez)
# ─────────────────────────────────────────────────────────────────────────────

_NODE = shutil.which("node")


def _kapi_senaryosu(senaryo: str, tmp_path: Path) -> dict:
    """Kapı fonksiyonlarını izole edip Node'da koştur."""
    ham = _UI.read_text(encoding="utf-8")
    parcalar = []
    for satir in ham.splitlines():
        if "const KAPI_ZAMAN_ASIMI_MS" in satir or "let startKapiTimer" in satir:
            parcalar.append(satir.strip())
    kapanis = chr(10) + "      }"
    for ad in ("function startKapisiKapat", "function startKapisiAc"):
        i = ham.index(ad)
        j = ham.index(kapanis, i) + len(kapanis)
        parcalar.append(ham[i:j])
    kod = chr(10).join(parcalar)

    surucu = """
        const DUGME = { disabled: false, dataset: {} };
        const ETIKET = { textContent: "Başlat" };
        global.$ = (id) => (id === "btn-start" ? DUGME : ETIKET);
        global.t = () => ({ startChecking: "kontrol", start: "Başlat", backToApp: "Uygulamaya dön" });
        global.appRunning = false;
        let ZAMANLAYICI = null;
        global.setTimeout = (fn, ms) => { ZAMANLAYICI = { fn, ms }; return 1; };
        global.clearTimeout = () => { ZAMANLAYICI = null; };
        __KOD__
        const durum = () => ({ kilitli: DUGME.disabled, etiket: ETIKET.textContent,
                               zamanlayici: ZAMANLAYICI ? ZAMANLAYICI.ms : null });
        __SENARYO__
        """.replace("__KOD__", kod).replace("__SENARYO__", senaryo)
    f = tmp_path / "kapi.mjs"
    f.write_text(surucu, encoding="utf-8")
    r = subprocess.run([_NODE, str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, f"node hatası:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(_NODE is None, reason="node yok")
def test_DAVRANIS_kapat_kilitler_ac_serbest_birakir(tmp_path):
    s = _kapi_senaryosu(
        """
        const out = {};
        out.baslangic = durum();
        startKapisiKapat(); out.kapali = durum();
        startKapisiAc();    out.acik = durum();
        console.log(JSON.stringify(out));
    """,
        tmp_path,
    )
    assert s["baslangic"]["kilitli"] is False
    assert s["kapali"]["kilitli"] is True, "kapat düğmeyi kilitlemiyor"
    assert s["kapali"]["etiket"] == "kontrol", "bekleme sebebi yazılmıyor"
    assert s["acik"]["kilitli"] is False, "aç düğmeyi serbest bırakmıyor"
    assert s["acik"]["etiket"] == "Başlat", "etiket geri gelmiyor"


@pytest.mark.skipif(_NODE is None, reason="node yok")
def test_DAVRANIS_zaman_asimi_kapiyi_ACAR(tmp_path):
    """🔴 Ağ adımı asılırsa düğme sonsuza dek kilitli kalamaz."""
    s = _kapi_senaryosu(
        """
        const out = {};
        startKapisiKapat();
        out.kapali = durum();
        out.zamanlayiciKuruldu = durum().zamanlayici !== null;
        // Ağ adımı hiç dönmedi → zaman aşımı tetiklenir
        (function(){ const z = durum().zamanlayici; })();
        ZAMANLAYICI_TETIKLE();
        out.sonra = durum();
        console.log(JSON.stringify(out));
    """.replace("ZAMANLAYICI_TETIKLE()", "(() => { const f = ZAMANLAYICI.fn; f(); })()"),
        tmp_path,
    )
    assert s["kapali"]["kilitli"] is True
    assert s["zamanlayiciKuruldu"] is True, "zaman aşımı zamanlayıcısı kurulmuyor"
    assert s["sonra"]["kilitli"] is False, "zaman aşımı düğmeyi AÇMIYOR → kalıcı kilit"


@pytest.mark.skipif(_NODE is None, reason="node yok")
def test_DAVRANIS_cift_ac_cagrisi_zararsiz(tmp_path):
    """`show('s-ready')` her çağrıda açmayı dener; kapı kapalı değilken bozmamalı."""
    s = _kapi_senaryosu(
        """
        const out = {};
        startKapisiAc();  out.hicKapanmadan = durum();
        startKapisiKapat(); startKapisiAc(); startKapisiAc();
        out.ciftAc = durum();
        console.log(JSON.stringify(out));
    """,
        tmp_path,
    )
    assert s["hicKapanmadan"]["kilitli"] is False
    assert s["ciftAc"]["kilitli"] is False
