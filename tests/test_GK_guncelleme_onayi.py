# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GÜNCELLEME ONAYI — sahip Y253 / Y254 (2026-11-06; istem 41 A). SAHİP KARARI 2026-08-08'i ("arka planda indir, sonra kur") DEĞİŞTİRİR.

Sahip (Y253): "yeni sürüm kontrolünden sonra yeni güncelleme varsa yapılsın indirilsin mi diye kullanıcı onayı sorulmalı … otomatik
yapmamalı kullanıcı onaylarsa süreç otomatik devam etmeli … bir sonraki açılışta kurulcak süreci yerine oto yeniden başlasın uygulama".
Y254: (a) tek pencere · (b) "Şimdi değil" → sonraki açılışta yeniden sorar, açıkken en çok GÜNDE BİR · (c) zorunlu (`min_supported_version`)
ONAYSIZ iner + ekranda bildirilir + etkin seans bitince yeniden başlatır.

Bu dosya GERÇEK arayüz işlevlerini (`launcher/app/ui/index.html`) sahte DOM + sahte Tauri `invoke` ile Node'da koşturur ve DAVRANIŞI
ölçer (kaynak-metin değil): onaysız indirme YOK · zorunlu onaysız iner + bildirim · onay → indir → kur → yeniden başlat · etkin seansta
kurulum / yeniden başlatma YOK · "Şimdi değil" → indirme yok, sonraki açılışta sorulur, açıkken günde ≤ 1 · soru açılışı BLOKLAMAZ ·
başlatıcı + katman birlikte → TEK akış (önce katman indirilir, onay kaydı, başlatıcı kurulur; yeni başlatıcı sormadan kurar).
Karar tablosu ve pencere içeriği çekirdekte (`launcher/core/src/guncelleme_onayi.rs`, cargo testleri).
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

_KOK = Path(__file__).resolve().parent.parent
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"
_MAIN_RS = _KOK / "launcher" / "app" / "src" / "main.rs"
_NODE = shutil.which("node")

_node_gerek = pytest.mark.skipif((_NODE is None) and not capraz.ZORUNLU, reason="node yok")


def _ham() -> str:
    return _UI.read_text(encoding="utf-8").replace("\r\n", "\n")


def _fonksiyon(ham: str, imza: str) -> str:
    i = ham.index(imza)
    kapanis = "\n      }"
    j = ham.index(kapanis, i) + len(kapanis)
    return ham[i:j]


def _satir(ham: str, parca: str) -> str:
    return next(s for s in ham.splitlines() if parca in s)


_ISLEVLER = [
    "function show(id)",
    "function startKapisiKapat()",
    "function startKapisiAc()",
    "function startKapisiKapaliMi()",
    "function startEtiketi(x)",
    "function setInstallControls(mode)",
    "function showPaused()",
    "function prefetchSonucIsle(r)",
    "async function recheckUpdates()",
    "function onaySorulmali(son, simdi)",
    "async function guncellemeyiDegerlendir(info)",
    "function onaySatirlari(oz)",
    "function onayNotu(oz)",
    "function onayKartiGoster(oz)",
    "async function katmanlariIndir()",
    "async function seansBitenekadarBekle()",
    "async function baslaticiyiGuncelle(b)",
    "async function guncellemeyiUygula(oz, kip)",
    "async function tryRuntimeUpdate()",
    "async function trySelfUpdate(u)",
]

_SURUCU = r"""
class El {
  constructor(id) { this.id = id; this._t = ""; this.hidden = false; this.disabled = false; this.dataset = {}; this.className = "";
    this.children = []; this.onclick = null; this.style = {}; this.classList = { add() {}, remove() {}, toggle() {} }; }
  get textContent() { return [this._t, ...this.children.map((c) => c.textContent)].filter(Boolean).join(" | "); }
  set textContent(v) { this._t = String(v); this.children = []; }
  appendChild(c) { this.children.push(c); return c; }
  querySelector() { return null; } querySelectorAll() { return []; } remove() {}
}
const _el = {};
function $(id) { return _el[id] || (_el[id] = new El(id)); }
const document = { createElement: () => new El(null) };
function bul(id, kok) { for (const c of (kok || $("notice")).children) { if (c.id === id) return c; const x = bul(id, c); if (x) return x; } return null; }
const t = () => new Proxy({}, { get: (_, k) => (typeof k === "string" ? k : undefined) });
let LANG = "tr";
let busy = false, baseInstalled = true, manifestRaw = "m1", sonBildirim = "", guncellemeTimer = null;
let prefetchDuraklatildi = false, prefetchIptalEdildi = false, yedekNotuDurum = null, paylasimNotu = false;
let resumeOp = null, pausedOp = false, appRunning = false;
let sonOnaySorusu = 0, onayAkisiSuruyor = false, onayDevam = null;
const NOT = [];
function notice(m) { NOT.push(String(m)); const b = $("notice"); b.textContent = String(m); b.hidden = false; }
function clearNotice() { const b = $("notice"); b.textContent = ""; b.hidden = true; }
function fail(m) { NOT.push("FAIL:" + String(m)); }
function clearErr() {} function startPrefetchPoll() {} function stopPrefetchPoll() {} function bgTemizle() {} function bgButonlariYaz() {}
function startPolling() {} function stopPolling() {} function resetInstallUI() {} function indet() {} function renderChips() {}
async function refreshEnv() { return {}; }
// Zamanlayıcı: bekleme ANINDA (mikro görevde) biter — sonsuz döngü ENGEL listesi tükenince kendiliğinden kırılır.
globalThis.setTimeout = (fn) => { Promise.resolve().then(fn); return 1; };
globalThis.clearTimeout = () => {};
const CAGRI = [];
let OZ = null, ENGEL = [], PLAN = { needed: true, cached: true }, PREFETCH = "prefetched", SELF = "hata";
async function invoke(ad, args) {
  CAGRI.push(ad);
  if (ad === "fetch_profiles") return { raw: "m1" };
  if (ad === "guncelleme_ozeti") return JSON.parse(JSON.stringify(OZ));
  if (ad === "guncelleme_engeli") { const e = ENGEL.length ? ENGEL.shift() : false; return e ? { engel: true, mesaj: "SEANS-SURUYOR" } : { engel: false }; }
  if (ad === "prefetch_runtime_update") return { status: PREFETCH };
  if (ad === "check_runtime_update") return PLAN;
  if (ad === "apply_runtime_update") return { status: "ready" };
  if (ad === "apply_self_update") { if (SELF === "tamam") return null; throw new Error("ret"); }
  return null;
}
const bekle = async () => { for (let i = 0; i < 200; i++) await Promise.resolve(); };
const kart = () => !!bul("onay-evet");
const durum = () => ({ cagri: CAGRI.slice(), notlar: NOT.slice(), kart: kart(), kartMetni: $("notice").textContent,
  ekran: curScreen(), dugmeKilitli: !!$("btn-start").disabled });
__KOD__
const OUT = {};
(async () => {
  for (const s of SCREENS) $(s).hidden = (s !== "s-ready");
__SENARYO__
  console.log(JSON.stringify(OUT));
})();
"""


def _kos(senaryo: str, tmp_path: Path) -> dict:
    ham = _ham()
    parcalar = [
        _satir(ham, 'const SCREENS = ["s-detect"'),
        _satir(ham, "function curScreen()"),
        _satir(ham, "const tf = (k, p) =>"),
        _satir(ham, "const fmtBytes = (n) =>"),
        _satir(ham, "const profName = (k) =>"),
        _satir(ham, "const HATIRLATMA_MS ="),
        _satir(ham, "const ENGEL_YOKLAMA_MS ="),
        "const KAPI_ZAMAN_ASIMI_MS = 25000; let startKapiTimer = null;",
    ] + [_fonksiyon(ham, imza) for imza in _ISLEVLER]
    kod = "\n".join(parcalar)
    for imza in (
        "guncelleme_ozeti",
        "guncelleme_engeli",
        "prefetch_runtime_update",
        "apply_self_update",
        "apply_runtime_update",
    ):
        assert imza in kod, f"çıkarım YARIM: {imza} yok"
    js = _SURUCU.replace("__KOD__", kod).replace("__SENARYO__", senaryo)
    f = tmp_path / "onay.mjs"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([_NODE, str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, f"node hatası: {r.stderr[-1500:]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


# Pencere içerikleri (çekirdeğin `guncelleme_onayi::ozet` JSON'u ile aynı biçim).
_BASLATICI = {
    "suanki": "1.9.54",
    "yeni": "1.9.55",
    "boyut": 220_000_000,
    "installerUrl": "https://github.com/a/s.exe",
    "sha256": "c" * 64,
    "notTr": "TR-NOTU",
    "notEn": "EN-NOTE",
}
_UYGULAMA = {"suanki": "1.9.52", "yeni": "1.9.53", "notTr": "UYG-TR", "notEn": "APP-EN"}


def _oz(karar: str, baslatici: bool, katman: bool, **ek) -> str:
    oz = {
        "karar": karar,
        "baslatici": _BASLATICI if baslatici else None,
        "uygulama": _UYGULAMA if katman else None,
        "bagimliliklar": False,
        "profiller": ["vet"] if katman else [],
        "toplamBayt": 300_000_000,
        "katmanGerekli": katman,
        "katmanOnbellekte": False,
        "katmanDurduruldu": False,
        "zorunlu": karar == "zorunlu",
        "tasinan": False,
    }
    oz.update(ek)
    return json.dumps(oz)


_INDIR_KUR = {"prefetch_runtime_update", "apply_runtime_update", "apply_self_update"}


@_node_gerek
def test_KRITIK_normal_guncelleme_ONAYSIZ_INMEZ_kart_gosterilir(tmp_path):
    out = _kos(
        f"""
  OZ = {_oz("sor", True, True)};
  await guncellemeyiDegerlendir({{}}); await bekle(); OUT.a = durum();
""",
        tmp_path,
    )["a"]
    assert out["kart"], f"onay kartı gösterilmedi: {out}"
    assert not (_INDIR_KUR & set(out["cagri"])), f"ONAYSIZ indirme / kurulum: {out['cagri']}"
    m = out["kartMetni"]
    for parca in (
        "onayBaslik",
        "onayBaslatici",
        "onayUygulama",
        "onayProfiller",
        "onayBoyut",
        "TR-NOTU",
        "UYG-TR",
        "onayGuncelle",
        "onaySimdiDegil",
    ):
        assert parca in m, f"kartta {parca} yok: {m}"
    assert "EN-NOTE" not in m and "APP-EN" not in m, f"TR ekranda İngilizce not (karışık dil): {m}"


@_node_gerek
def test_kart_notu_SECILI_dilde(tmp_path):
    out = _kos(
        f"""
  LANG = "en"; OZ = {_oz("sor", True, True)};
  await guncellemeyiDegerlendir({{}}); await bekle(); OUT.a = durum();
""",
        tmp_path,
    )["a"]
    assert "EN-NOTE" in out["kartMetni"] and "APP-EN" in out["kartMetni"], out["kartMetni"]
    assert "TR-NOTU" not in out["kartMetni"], out["kartMetni"]


@_node_gerek
def test_KRITIK_zorunlu_ONAYSIZ_iner_bildirilir_seans_bitince_kurar(tmp_path):
    out = _kos(
        f"""
  OZ = {_oz("zorunlu", False, True)}; ENGEL = [true, true];
  await guncellemeyiDegerlendir({{}}); await bekle(); OUT.a = durum();
""",
        tmp_path,
    )["a"]
    assert not out["kart"], "zorunlu güncelleme onaya bağlandı"
    assert out["notlar"] and out["notlar"][0] == "rtRecall", f"zorunlu güncelleme ekranda bildirilmedi: {out['notlar']}"
    c = out["cagri"]
    assert "prefetch_runtime_update" in c and "apply_runtime_update" in c, f"zorunlu güncelleme inmedi / kurulmadı: {c}"
    son_engel = max(i for i, a in enumerate(c) if a == "guncelleme_engeli")
    assert c.index("apply_runtime_update") > son_engel, f"seans bitmeden kuruldu: {c}"
    assert out["notlar"].count("SEANS-SURUYOR") == 2, f"bekleme ekranda söylenmedi: {out['notlar']}"


@_node_gerek
def test_KRITIK_onay_INDIR_KUR_yeniden_baslat_kendiliginden(tmp_path):
    out = _kos(
        f"""
  OZ = {_oz("sor", False, True)};
  await guncellemeyiDegerlendir({{}}); await bekle();
  bul("onay-evet").onclick(); await bekle(); OUT.a = durum();
""",
        tmp_path,
    )["a"]
    c = out["cagri"]
    assert c.index("prefetch_runtime_update") < c.index("guncelleme_engeli") < c.index("apply_runtime_update"), (
        f"onay → indir → (seans kapısı) → kur sırası yok: {c}"
    )
    assert out["ekran"] == "s-ready" and not out["kart"], out


@_node_gerek
def test_KRITIK_etkin_seansta_KURULUM_ve_yeniden_baslatma_YOK(tmp_path):
    out = _kos(
        f"""
  OZ = {_oz("sor", True, False)}; ENGEL = [true, true, true];
  await guncellemeyiDegerlendir({{}}); await bekle();
  const evet = bul("onay-evet");
  ENGEL = Array(5000).fill(true);  // seans hiç bitmiyor
  evet.onclick(); await bekle(); OUT.a = durum();
""",
        tmp_path,
    )["a"]
    assert "apply_self_update" not in out["cagri"] and "apply_runtime_update" not in out["cagri"], (
        f"etkin seansta kurulum / yeniden başlatma: {out['cagri']}"
    )
    assert "SEANS-SURUYOR" in out["notlar"], f"bekleme ekranda söylenmedi: {out['notlar']}"


@_node_gerek
def test_KRITIK_engel_yoklamasi_hata_verirse_ENGEL_VAR_sayilir(tmp_path):
    out = _kos(
        f"""
  OZ = {_oz("sor", False, True, katmanOnbellekte=True)};
  let n = 0; const asil = invoke;
  invoke = async (ad, a) => {{ if (ad === "guncelleme_engeli" && n++ < 3) {{ CAGRI.push(ad); throw new Error("x"); }} return asil(ad, a); }};
  await guncellemeyiDegerlendir({{}}); await bekle();
  bul("onay-evet").onclick(); await bekle(); OUT.a = durum();
""",
        tmp_path,
    )["a"]
    c = out["cagri"]
    assert c.count("guncelleme_engeli") >= 4 and c.index("apply_runtime_update") > 3, (
        f"yoklama hatası 'engel yok' sayıldı: {c}"
    )


@_node_gerek
def test_KRITIK_simdi_degil_INDIRMEZ_acikken_gunde_bir_sonraki_acilista_yeniden(tmp_path):
    out = _kos(
        f"""
  OZ = {_oz("sor", True, True)};
  const gercek = Date.now; let simdi = 1_000_000_000_000; Date.now = () => simdi;
  await guncellemeyiDegerlendir({{}}); await bekle();
  bul("onay-hayir").onclick(); await bekle(); OUT.hayir = durum();
  simdi += 6 * 3600 * 1000; await recheckUpdates(); await bekle(); OUT.alti = durum();
  simdi += 12 * 3600 * 1000; await recheckUpdates(); await bekle(); OUT.onsekiz = durum();
  simdi += 6 * 3600 * 1000 + 1; await recheckUpdates(); await bekle(); OUT.yirmidort = durum();
  // sonraki açılış = yeni oturum (bellek sıfır)
  sonOnaySorusu = 0; clearNotice(); await guncellemeyiDegerlendir({{}}); await bekle(); OUT.acilis = durum();
  Date.now = gercek;
""",
        tmp_path,
    )
    assert not out["hayir"]["kart"] and not (_INDIR_KUR & set(out["hayir"]["cagri"])), (
        f"'Şimdi değil' sonrası indirme: {out['hayir']}"
    )
    assert not out["alti"]["kart"] and not out["onsekiz"]["kart"], "açıkken bir günden SIK soruldu"
    assert not (_INDIR_KUR & set(out["onsekiz"]["cagri"])), f"periyodik tur onaysız indirdi: {out['onsekiz']['cagri']}"
    assert out["yirmidort"]["kart"], "bir gün sonra yeniden sorulmadı"
    assert out["acilis"]["kart"], "sonraki açılışta yeniden sorulmadı"


@_node_gerek
def test_KRITIK_soru_acilisi_BLOKLAMAZ(tmp_path):
    out = _kos(
        f"""
  OZ = {_oz("sor", True, True)};
  startKapisiKapat();
  const zamanAsimi = (async () => {{ for (let i = 0; i < 500; i++) await Promise.resolve(); return "ASILI"; }})();
  const sonuc = await Promise.race([guncellemeyiDegerlendir({{}}).then(() => "dondu"), zamanAsimi]);
  startKapisiAc();
  OUT.a = Object.assign(durum(), {{ sonuc }});
""",
        tmp_path,
    )["a"]
    assert out["sonuc"] == "dondu", "karar işlevi kullanıcının cevabını BEKLİYOR (açılış bloklanır)"
    assert out["kart"] and out["ekran"] == "s-ready" and not out["dugmeKilitli"], (
        f"kart açıkken Başlat kilitli / ekran gitti: {out}"
    )
    ham = _ham()
    boot = _fonksiyon(ham, "async function bootNetwork(env)")
    i = boot.index("await guncellemeyiDegerlendir(info)")
    assert "startKapisiAc();" in boot[i : i + 200], "karar sonrası Başlat kapısı açılmıyor"


@_node_gerek
def test_KRITIK_baslatici_ve_katman_birlikte_TEK_akis(tmp_path):
    out = _kos(
        f"""
  OZ = {_oz("sor", True, True)}; SELF = "tamam";
  await guncellemeyiDegerlendir({{}}); await bekle();
  bul("onay-evet").onclick(); await bekle(); OUT.eski = durum();
  // yeni başlatıcı: çekirdek taşınan onayı görür → "onayli" (katman önbellekte)
  CAGRI.length = 0; clearNotice(); sonOnaySorusu = 0; onayAkisiSuruyor = false;
  OZ = {_oz("onayli", False, True, katmanOnbellekte=True, tasinan=True)};
  await guncellemeyiDegerlendir({{}}); await bekle(); OUT.yeni = durum();
""",
        tmp_path,
    )
    c = out["eski"]["cagri"]
    assert c.index("prefetch_runtime_update") < c.index("guncelleme_onayini_kaydet") < c.index("apply_self_update"), (
        f"tek akış sırası (katman indir → onay kaydı → başlatıcı kur) yok: {c}"
    )
    assert "apply_runtime_update" not in c, f"eski başlatıcı katmanı da kurdu (iki yeniden başlatma): {c}"
    y = out["yeni"]
    assert not y["kart"], "yeni başlatıcı onaylanmış güncellemeyi YENİDEN sordu"
    assert "apply_runtime_update" in y["cagri"] and "prefetch_runtime_update" not in y["cagri"], y["cagri"]
    assert y["cagri"].index("apply_runtime_update") < y["cagri"].index("guncelleme_onayini_temizle"), y["cagri"]


@_node_gerek
def test_tasinan_onay_bitti_ise_uygulama_OTOMATIK_acilir(tmp_path):
    out = _kos(
        f"""
  OZ = {_oz("yok", False, False, tasinan=True)};
  const sonuc = await guncellemeyiDegerlendir({{}}); await bekle();
  OUT.a = Object.assign(durum(), {{ sonuc }});
""",
        tmp_path,
    )["a"]
    assert out["sonuc"] == "ac" and "guncelleme_onayini_temizle" in out["cagri"], out
    boot = _fonksiyon(_ham(), "async function bootNetwork(env)")
    assert re.search(r'guncellemeKarari === "ac"[^\n]*\$\("btn-start"\)\.onclick\(\)', boot), (
        "taşınan onay sonrası uygulama açılmıyor"
    )


@_node_gerek
def test_duraklatilan_onayli_indirme_DEVAM_ile_kaldigi_yerden_kurulur(tmp_path):
    out = _kos(
        f"""
  OZ = {_oz("sor", False, True)}; PREFETCH = "paused";
  await guncellemeyiDegerlendir({{}}); await bekle();
  bul("onay-evet").onclick(); await bekle(); OUT.dur = durum();
  PREFETCH = "prefetched"; prefetchSonucIsle({{ status: "prefetched" }}); await bekle(); OUT.devam = durum();
""",
        tmp_path,
    )
    assert "apply_runtime_update" not in out["dur"]["cagri"], "duraklatılmışken kuruldu"
    assert "apply_runtime_update" in out["devam"]["cagri"], f"'Devam et' sonrası akış sürmedi: {out['devam']['cagri']}"


def test_KRITIK_acilis_ve_periyodik_tur_ONAYSIZ_indirme_kurma_cagirmaz():
    """Kaynak sözleşmesi (davranış testlerinin tamamlayıcısı): açılış ağ adımı ve periyodik tur indirme / kurma komutunu DOĞRUDAN
    çağırmaz — tek giriş `guncellemeyiDegerlendir`."""
    ham = _ham()
    for imza in (
        "async function bootNetwork(env)",
        "async function recheckUpdates()",
        "async function guncellemeyiDegerlendir(info)",
    ):
        g = _fonksiyon(ham, imza)
        for yasak in (
            "prefetch_runtime_update",
            "apply_runtime_update",
            "apply_self_update",
            "trySelfUpdate(",
            "tryRuntimeUpdate(",
        ):
            assert yasak not in g, f"{imza} → {yasak} (onaysız indirme / kurma yolu)"
    assert "await guncellemeyiDegerlendir(info)" in _fonksiyon(ham, "async function bootNetwork(env)")
    assert "await guncellemeyiDegerlendir(info)" in _fonksiyon(ham, "async function recheckUpdates()")


def test_KRITIK_rust_komutlari_kayitli_async_ve_kapi_TEK_yerde():
    rs = _MAIN_RS.read_text(encoding="utf-8").replace("\r\n", "\n")
    blok = re.search(r"generate_handler!\[(.*?)\]", rs, re.S).group(1)
    for ad in ("guncelleme_ozeti", "guncelleme_onayini_kaydet", "guncelleme_onayini_temizle", "guncelleme_engeli"):
        assert re.search(rf"\b{ad}\b", blok), f"{ad} kayıtlı değil"
        assert re.search(rf"async fn {ad}\(", rs), f"{ad} async değil (pencere iş parçacığında koşar)"
    g = rs[rs.index("async fn guncelleme_engeli(") :]
    g = g[: g.index("\n}\n")]
    assert "aktif_seans_kapisi(" in g, "seans engeli TEK kapıyı (aktif_seans_kapisi) kullanmıyor"


def test_baslatici_notu_manifeste_KENDI_surumuyle_iki_dilde_yazilir(tmp_path):
    """Y254 a: onay penceresinin kısa notu manifest `launcher.notes` / `notes_en`'den gelir; kaynak `docs/surum_notlari.json`."""
    import sys

    sys.path.insert(0, str(_KOK / "scripts"))
    import surum_notlari as sn

    notlar = tmp_path / "notlar.json"
    notlar.write_text(json.dumps({"launcher": {"1.9.54": {"notes": "TR", "notes_en": "EN"}}}), encoding="utf-8")
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps({"version": "1.9.52", "launcher": {"version": "1.9.54", "rollout": 100}}), encoding="utf-8")
    assert sn.baslatici_notlarini_yaz(m, notlar) == "1.9.54"
    blok = json.loads(m.read_text(encoding="utf-8"))["launcher"]
    assert (blok["notes"], blok["notes_en"], blok["rollout"]) == ("TR", "EN", 100), blok
    m.write_text(json.dumps({"version": "1.9.52", "launcher": {"version": "1.9.55"}}), encoding="utf-8")
    with pytest.raises(sn.NotYok):
        sn.baslatici_notlarini_yaz(m, notlar)
    assert "notes" not in json.loads(m.read_text(encoding="utf-8"))["launcher"], "notu olmayan sürüme eski not yazıldı"


@_node_gerek
def test_zorunlu_akis_kullanicinin_DURAKLAT_kararini_ezmez(tmp_path):
    """Saha bildirimi 2026-08-28 ilkesi: kullanıcı bu oturumda indirmeyi duraklattıysa periyodik tur (zorunlu bile olsa) onu
    kendiliğinden yeniden başlatmaz; karar oturumluktur."""
    out = _kos(
        f"""
  OZ = {_oz("zorunlu", False, True)}; prefetchDuraklatildi = true;
  await guncellemeyiDegerlendir({{}}); await bekle(); OUT.a = durum();
""",
        tmp_path,
    )["a"]
    assert not (_INDIR_KUR & set(out["cagri"])), f"duraklatılmış indirme kendiliğinden yeniden başladı: {out['cagri']}"
