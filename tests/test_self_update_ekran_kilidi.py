# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""🔴 Başarısız client self-update, launcher'ı "Client güncelleniyor…" ekranında HAPSETMEMELİ.

DENETİM BULGUSU (2026-08-17). `trySelfUpdate` ekranı `show("s-install")` ile devralıyor ama
`catch` dalı yalnız `stopPolling(); return false;` yapıyor — **hiçbir `show()` ekranı geri
almıyor** ve `bootNetwork`'ün hiçbir dalında telafi eden bir çağrı yok. Sonuç:

  * Pencere `s-install` ekranında, *"Yeni bir client sürümü bulundu — indirilip kuruluyor.
    Uygulama otomatik yeniden başlayacak."* metniyle kalıyor. **Metin yalan.**
  * Başlat/Onar/Kaldır/Profil değiştir HEPSİ erişilemez (hepsi gizli `s-ready` bölümünün içinde).
  * Başarı ile başarısızlık kullanıcı için **ayırt edilemez** (aynı ekran, aynı metin).
  * Kurulu OLMAYAN cihazda kaçış yolu HİÇ YOK → **yeni kullanıcı hiç kuramaz.**
  * Seans sürerken kapı reddettiğinde veteriner TEDAVİ sırasında "otomatik yeniden başlayacak"
    okuyor — kapının var olma sebebi tam bunun olmamasıdır.

Belirlenimci ret sebepleri (her açılışta tekrarlar): asset 404 (`--clobber` kesme tuzağı),
manifest sha'sı ile yayınlanan exe'nin uyuşmaması, `detect_running_backend` bir süreç görüp
`/api/health`in yanıt vermemesi (`session_active` → `None` → kapı reddeder).

⚠️ KODUN KENDİ NİYETİ BUNU YAZIYOR ve karşılanmıyordu: `trySelfUpdate` başlığı
*"Başarısızsa … normal boot sürer; güncelleme kullanıcıyı ASLA bloklamaz"*, iptal notu
*"`Cancelled` ile döner → catch → normal boot"*, `BUILD.md` *"Yoksa/başarısızsa normal açılış
sürer"*, `main.rs` *"güncelleme kullanıcıyı ASLA bloklamaz"*. Belgelenmiş niyet ile kod ayrışmıştı.

⚠️ `record_selfupdate_attempt` sayacına BİLEREK DOKUNULMADI: o sayaç yalnız indirme+doğrulama
BAŞARILI olduktan sonra çağrılıyor, yani bu hata sınıfını hiç kapsamıyor. Ama geçici ağ kopmalarını
saymaya başlamak, zayıf WiFi'li bir kliniğin client güncellemelerini KALICI olarak susturabilirdi
(1.9.27 girdisi: aynı makinede ~%33 anlık TCP kopması ölçüldü). Ekranın geri alınması "cihaz
açılmıyor" sonucunu tamamen kaldırıyor; kalan şey her açılışta birkaç saniyelik sessiz bir yeniden
deneme — engelleyici değil.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"
_NODE = shutil.which("node")


@pytest.fixture(scope="module")
def ui() -> str:
    return _UI.read_text(encoding="utf-8")


def _fonksiyon(ham: str, imza: str) -> str:
    """`index.html`ten bir fonksiyonu (girintili kapanışına kadar) çıkarır."""
    i = ham.index(imza)
    kapanis = chr(10) + "      }"
    j = ham.index(kapanis, i) + len(kapanis)
    return ham[i:j]


def _senaryo(senaryo: str, tmp_path: Path) -> dict:
    """GERÇEK `trySelfUpdate` + GERÇEK kapı fonksiyonlarını sahte DOM/Tauri ile Node'da koştur.

    ⚠️ Kapı fonksiyonları da DAHİL EDİLİR: `show("s-ready")` yan etki olarak `startKapisiAc()`
    çağırıyor, dolayısıyla "ekranı geri al" düzeltmesi düğmeyi ağ adımı bitmeden AÇABİLİR — tam
    olarak 1.9.30'un önlemek için yazıldığı belirti. Bu yüzden düğmenin son hâli de ölçülür.
    """
    ham = _UI.read_text(encoding="utf-8")
    kod = "\n".join(
        [
            "const KAPI_ZAMAN_ASIMI_MS = 25000; let startKapiTimer = null;",
            _fonksiyon(ham, "function startKapisiKapat()"),
            _fonksiyon(ham, "function startKapisiAc()"),
            _fonksiyon(ham, "async function trySelfUpdate(u)"),
        ]
    )

    surucu = """
        const SCREENS = ["s-select", "s-install", "s-ready"];
        const EKRAN = { "s-select": true, "s-install": true, "s-ready": false }; // baslangic: s-ready
        const NESNE = {};
        global.$ = (id) => (NESNE[id] = NESNE[id] || { textContent: "", hidden: false, disabled: false, dataset: {} });
        global.appRunning = false;
        global.setTimeout = (fn, ms) => 1; global.clearTimeout = () => {};
        // GERÇEK `show`un yan etkisi taklit edilir: "s-ready"ye dönüş kapıyı AÇAR (bilerek).
        global.show = (id) => {
          for (const s of SCREENS) EKRAN[s] = (s !== id);
          if (id === "s-ready" && typeof startKapisiAc === "function") startKapisiAc();
        };
        global.curScreen = () => SCREENS.find((s) => !EKRAN[s]) || null;
        global.resetInstallUI = () => {};
        global.startPolling = () => {};
        global.stopPolling = () => {};
        global.indet = () => {};
        global.notice = (m) => { NOT.push(String(m)); };
        global.clearNotice = () => {};
        global.t = () => ({
          startChecking: "Güncelleme kontrol ediliyor…",
          start: "Başlat",
          backToApp: "Uygulamaya dön",
          updatingTitle: "Client güncelleniyor…",
          updatingLead: "Yeni bir client sürümü bulundu — indirilip kuruluyor.",
          updatingApply: "uygulanıyor",
          selfUpdateFailed: "Client güncellemesi tamamlanamadı — uygulama normal açılıyor.",
        });
        const NOT = [];
        global.invoke = async (ad) => { if (ad === "apply_self_update") throw new Error(RET_SEBEBI); return null; };
        __KOD__
        const durum = () => ({
          ekran: curScreen(),
          notlar: NOT.slice(),
          dugmeKilitli: !!$("btn-start").disabled,
          dugmeKapi: $("btn-start").dataset.kapi || null,
        });
        __SENARYO__
        """.replace("__KOD__", kod).replace("__SENARYO__", senaryo)
    f = tmp_path / "selfupdate.mjs"
    f.write_text(surucu, encoding="utf-8")
    r = subprocess.run([_NODE, str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, f"node hatasi:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


_GUNCELLEME = '{ installer_url: "https://x/setup.exe", sha256: "a".repeat(64), size: 1, version: "9.9.9" }'


@pytest.mark.skipif(_NODE is None, reason="node yok")
def test_KRITIK_KURULU_cihazda_basarisizlikta_ekran_GERI_ALINIR(tmp_path):
    """Kurulu cihaz: self-update patlarsa ekran `s-ready`ye dönmeli (Başlat'a ulaşılabilsin)."""
    s = _senaryo(
        """
        const RET_SEBEBI = "asset 404";
        const out = {};
        out.once = durum();
        out.donus = await trySelfUpdate(GUNCELLEME);
        out.sonra = durum();
        console.log(JSON.stringify(out));
        """.replace("GUNCELLEME", _GUNCELLEME),
        tmp_path,
    )
    assert s["once"]["ekran"] == "s-ready", "on-kosul: kurulu cihaz s-ready'de baslar"
    assert s["donus"] is False, "basarisizlikta false donmeli (normal boot surmeli)"
    assert s["sonra"]["ekran"] == "s-ready", (
        f"ekran '{s['sonra']['ekran']}' ekraninda KALDI. `s-install` gorunurken Baslat/Onar/Kaldir "
        "hepsi gizli `s-ready` icinde → cihaz ACILAMAZ ve ekranda 'indirilip kuruluyor, otomatik "
        "yeniden baslayacak' YAZIYOR (yalan)."
    )


@pytest.mark.skipif(_NODE is None, reason="node yok")
def test_KRITIK_KURULU_OLMAYAN_cihazda_da_ekran_GERI_ALINIR(tmp_path):
    """Taze cihaz: kaçış yolu HİÇ yoktu (`tryRuntimeUpdate` `!baseInstalled` ile hemen dönüyor,
    `pending_profiles` de boş) → yeni kullanıcı hiç kuramıyordu."""
    s = _senaryo(
        """
        const RET_SEBEBI = "sha uyusmadi";
        EKRAN["s-select"] = false; EKRAN["s-ready"] = true;   // taze cihaz: kurulum secimi ekrani
        const out = {};
        out.once = durum();
        out.donus = await trySelfUpdate(GUNCELLEME);
        out.sonra = durum();
        console.log(JSON.stringify(out));
        """.replace("GUNCELLEME", _GUNCELLEME),
        tmp_path,
    )
    assert s["once"]["ekran"] == "s-select", "on-kosul: taze cihaz s-select'te baslar"
    assert s["sonra"]["ekran"] == "s-select", (
        f"taze cihazda ekran '{s['sonra']['ekran']}'da kaldi → YENI KULLANICI HIC KURAMAZ"
    )


@pytest.mark.skipif(_NODE is None, reason="node yok")
def test_KRITIK_basarisizlik_SESSIZ_kalmaz(tmp_path):
    """Başarı ile başarısızlık ayırt edilebilir olmalı — kullanıcı ne olduğunu OKUMALI."""
    s = _senaryo(
        """
        const RET_SEBEBI = "iptal";
        const out = {};
        out.donus = await trySelfUpdate(GUNCELLEME);
        out.sonra = durum();
        console.log(JSON.stringify(out));
        """.replace("GUNCELLEME", _GUNCELLEME),
        tmp_path,
    )
    assert s["sonra"]["notlar"], (
        "basarisizlikta kullaniciya HICBIR SEY soylenmiyor → basari ile basarisizlik ayirt edilemez"
    )


@pytest.mark.skipif(_NODE is None, reason="node yok")
def test_eksik_manifest_alanlari_ekrani_HIC_DEVRALMAZ_karsit_kanit(tmp_path):
    """Karşı-kanıt: `installer_url`/`sha256` yoksa fonksiyon ekrana HİÇ dokunmamalı (eski-tip bildirim)."""
    s = _senaryo(
        """
        const RET_SEBEBI = "kullanilmaz";
        const out = {};
        out.donus = await trySelfUpdate({ version: "9.9.9" });
        out.sonra = durum();
        console.log(JSON.stringify(out));
        """,
        tmp_path,
    )
    assert s["donus"] is False
    assert s["sonra"]["ekran"] == "s-ready", "eksik alanlarda ekran gereksiz yere degistirildi"
    assert not s["sonra"]["notlar"], "eksik alanlarda gereksiz uyari gosterildi"


@pytest.mark.skipif(_NODE is None, reason="node yok")
def test_auto_false_ekrani_HIC_DEVRALMAZ_karsit_kanit(tmp_path):
    """Karşı-kanıt: `--launcher-rollout 0` (auto=false) yolunda da ekran devralınmamalı."""
    s = _senaryo(
        """
        const RET_SEBEBI = "kullanilmaz";
        const out = {};
        out.donus = await trySelfUpdate({ installer_url: "u", sha256: "s", auto: false });
        out.sonra = durum();
        console.log(JSON.stringify(out));
        """,
        tmp_path,
    )
    assert s["donus"] is False
    assert s["sonra"]["ekran"] == "s-ready"


@pytest.mark.skipif(_NODE is None, reason="node yok")
def test_KRITIK_ekran_geri_alinirken_BASLAT_kapisi_ACILMAZ(tmp_path):
    """🔴 Ekranı geri almak, ağ adımı bitmeden düğmeyi AÇMAMALI.

    `show("s-ready")` yan etki olarak `startKapisiAc()` çağırıyor (bilerek: kapıyı tek tek çıkış
    yollarına serpiştirmemek için). Ama `trySelfUpdate` başarısız olduğunda ağ adımı HENÜZ BİTMEZ —
    `tryRuntimeUpdate()` sonra koşar ve ekranı devralabilir. Düğmeyi orada açmak, 1.9.30'un
    ortadan kaldırmak için yazıldığı belirtiyi geri getirirdi: veteriner "Başlat"a basacakken ekran
    güncellemeye geçer ve tıklama boşa gider. Bu kusuru İNCELEMEDE kendi düzeltmemde buldum."""
    s = _senaryo(
        """
        const RET_SEBEBI = "asset 404";
        const out = {};
        startKapisiKapat();              // ag adiminin basi (bootNetwork boyle yapiyor)
        out.oncesi = durum();
        out.donus = await trySelfUpdate(GUNCELLEME);
        out.sonrasi = durum();
        console.log(JSON.stringify(out));
        """.replace("GUNCELLEME", _GUNCELLEME),
        tmp_path,
    )
    assert s["oncesi"]["dugmeKilitli"] is True, "on-kosul: ag adimi basinda kapi kapali olmali"
    assert s["sonrasi"]["ekran"] == "s-ready", "ekran geri alinmadi"
    assert s["sonrasi"]["dugmeKilitli"] is True, (
        "ekran geri alinirken kapi ACILDI → runtime guncelleme kontrolu bitmeden 'Baslat' "
        "tiklanabilir oluyor ve ekran sonra devralinirsa tiklama BOSA GIDER (1.9.30 belirtisi)."
    )


def test_niyet_metni_kaynakta_KORUNUR_capa(ui):
    """Çıpa: "kullanıcıyı ASLA bloklamaz" niyeti kaynakta yazılı kalmalı.

    Bu bulgunun kök nedeni tam olarak "belgelenmiş niyet ile kodun ayrışması"ydı; niyet metni
    silinirse bir sonraki okuyucu ekranı geri almanın neden zorunlu olduğunu bilemez."""
    assert "ASLA bloklamaz" in ui, "self-update'in bloklamama niyeti kaynaktan silinmis"


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
