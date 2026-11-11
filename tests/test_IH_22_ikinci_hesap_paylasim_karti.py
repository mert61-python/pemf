# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""T2Y #22 (Y275, istem 46) — İKİNCİ WINDOWS HESABINDA Y182 PAYLAŞIM KARTI GÖRÜNÜR KALIR.

ÖLÇÜLEN KUSUR (11 Kasım, ikinci yerel hesap `Şükrü`): hasta veri dizinine erişemeyen hesapta başlatıcı açılışında paylaşım kartı
ÇIKMIYORDU. Kök neden `paylasim_durumu` hatası DEĞİL — çekirdek o hesapta "Gerekli" der (Şükrü kimliğiyle sonda) — kartın ÇİZİLDİĞİ
kutu (`#notice`) açılışın ağ adımında SİLİNİYORDU: `refreshEnv` kartı ateşle-unut çizer, `bootNetwork` manifest gelince
`clearNotice()` (çevrimiçi) ya da `notice(offlineReady)` (çevrimdışı) ile aynı kutuyu temizler / ezer. Ayrıca `paylasim_durumu`
çağrısı hata verirse kart sessizce hiç çizilmiyordu (`catch (_) { return false; }`).

Düzeltme: paylaşım kartı KENDİ kutusunda (`#paylasim`) — bildirim kutusunun temizlenmesi / başka not onu silmez; durum
belirlenemezse kart "paylaşım gerekli olabilir" metniyle ve aynı yönetici düğmesiyle görünür.

Bu dosya GERÇEK arayüz işlevlerini (`launcher/app/ui/index.html`) sahte DOM + sahte Tauri `invoke` ile Node'da koşturur ve DAVRANIŞI
ölçer (kaynak-metin değil); `invoke` yanıtlarının SIRASI senaryoda denetlenir (paylaşım yoklaması önce / manifest önce / çevrimdışı).
"""

import json
import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

_KOK = Path(__file__).resolve().parent.parent
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"
_NODE = shutil.which("node")

pytestmark = pytest.mark.skipif((_NODE is None) and not capraz.ZORUNLU, reason="node yok")


def _ham() -> str:
    return _UI.read_text(encoding="utf-8").replace("\r\n", "\n")


def _fonksiyon(ham: str, imza: str) -> str:
    i = ham.index(imza)
    kapanis = "\n      }"
    j = ham.index(kapanis, i) + len(kapanis)
    return ham[i:j]


def _satir(ham: str, parca: str) -> str:
    return next(s for s in ham.splitlines() if parca in s)


# Çok satırlı gerçek işlevler (gövde 6 boşluklu `}` ile kapanır).
_ISLEVLER = [
    "function notice(msg, onRetry)",
    "async function paylasimKontrol()",
    "async function firewallKontrol(backendCalisti)",
    "async function refreshEnv()",
    "async function bootLocal()",
    "async function bootNetwork(env)",
]
# Düzeltmeyle gelen yardımcılar — ÖNCE-KIRMIZI koşusunda yoktur (yokluk davranış testinde kırmızı olur, çıkarımda değil).
_SECMELI = ["function paylasimKartiCiz(d)", "function paylasimDiliYenile()"]

_SURUCU = r"""
class El {
  constructor(id) { this.id = id; this._t = ""; this.hidden = false; this.disabled = false; this.className = "";
    this.children = []; this.onclick = null; this.style = {}; this.dataset = {}; this.classList = { add() {}, remove() {}, toggle() {} }; }
  get textContent() { return [this._t, ...this.children.map((c) => c.textContent)].filter(Boolean).join(" | "); }
  set textContent(v) { this._t = String(v); this.children = []; }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); }
  querySelector() { return null; } querySelectorAll() { return []; }
}
const _el = {};
function $(id) { return _el[id] || (_el[id] = new El(id)); }
const document = { createElement: () => new El(null) };
const t = () => new Proxy({}, { get: (_, k) => (typeof k === "string" ? k : undefined) });
const tf = (k) => k;
const profName = (k) => k;
let LANG = "tr";
let installed = [], baseInstalled = true, platform = "windows", ver = "", pkgVersion = "", manifestRaw = "", profileKeys = [];
let sizes = {}, baseBytes = 0, busy = false, envCache = null;
let yedekNotuDurum = null, paylasimNotu = false, paylasimDurum = null;
let EKRAN = "s-ready";
function show(id) { EKRAN = id; }
function curScreen() { return EKRAN; }
function stopPrefetchPoll() {} function startKapisiKapat() {} function startKapisiAc() {} function setOffline() {}
function startUpdateWatch() {} function renderCards() {} function renderChips() {} function askConfirm() {} function fail(m) { CAGRI.push("FAIL:" + m); }
async function yedekHedefiKontrol() {}
// Güncelleme onayı: senaryo isterse bildirim kutusuna bir kart çizer (paylaşım kartı onu ezmemeli, o da paylaşım kartını).
let GUNCELLEME_KARTI = false;
async function guncellemeyiDegerlendir() { if (GUNCELLEME_KARTI) notice("GUNCELLEME-KARTI"); return "yok"; }
const CAGRI = [];
// invoke yanıt SIRASI: her komut `GECIKME[ad]` mikro görev sonra yanıtlar (senaryo sırayı böyle kurar).
let GECIKME = { paylasim_durumu: 1, fetch_profiles: 60 };
let PAYLASIM = { gerekli: true, grup_var: false }, PAYLASIM_HATA = false, CEVRIMDISI = false, KUR_HATA = false;
const bekleN = async (n) => { for (let i = 0; i < n; i++) await Promise.resolve(); };
async function invoke(ad, args) {
  CAGRI.push(ad);
  await bekleN(GECIKME[ad] || 0);
  if (ad === "detect_environment") return { installed_profiles: ["vet"], already_installed: true, platform: "windows", launcher_version: "1.9.54" };
  if (ad === "paylasim_durumu") { if (PAYLASIM_HATA) throw new Error("ipc"); return JSON.parse(JSON.stringify(PAYLASIM)); }
  if (ad === "paylasim_kur") { if (KUR_HATA) throw "KUR-HATASI"; return { status: "ok" }; }
  if (ad === "firewall_durumu") return { gereksiz: true };
  if (ad === "fetch_profiles") { if (CEVRIMDISI) throw new Error("offline"); return { raw: "{}", version: "1.9.54", platform_supported: true, profiles: [] }; }
  return null;
}
const bekle = async () => { for (let i = 0; i < 400; i++) await Promise.resolve(); };
// Görünen kutular: gizli olmayan ve metni olan her öğe (kart hangi kutuda çizilirse çizilsin) — başlıktaki sürüm rozeti hariç.
const gorunur = () => Object.values(_el).filter((e) => !e.hidden && e.textContent && e.id !== "ver").map((e) => ({ id: e.id, metin: e.textContent }));
const kartDugmesi = () => { for (const e of Object.values(_el)) { if (e.hidden) continue; for (const c of e.children) if (c.textContent === "paylasimKur") return c; } return null; };
const durum = () => ({ gorunur: gorunur(), cagri: CAGRI.slice(), paylasimNotu, dugme: !!kartDugmesi() });
__KOD__
const OUT = {};
(async () => {
  for (const id of ["notice", "error", "paylasim"]) $(id).hidden = true;  // gerçek HTML'de `hidden` öznitelikli kutular
__SENARYO__
  console.log(JSON.stringify(OUT));
})().catch((e) => { console.log(JSON.stringify({ HATA: String(e && e.stack || e) })); });
"""


def _kos(senaryo: str, tmp_path: Path) -> dict:
    ham = _ham()
    parcalar = [_satir(ham, "function clearNotice()")]
    parcalar += [_fonksiyon(ham, imza) for imza in _ISLEVLER]
    parcalar += [_fonksiyon(ham, imza) for imza in _SECMELI if imza in ham]
    js = _SURUCU.replace("__KOD__", "\n".join(parcalar)).replace("__SENARYO__", senaryo)
    f = tmp_path / "paylasim.mjs"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([_NODE, str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, f"node hatası: {r.stderr[-1500:]}"
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert "HATA" not in out, out["HATA"]
    return out


def _metinler(d: dict) -> str:
    return " || ".join(g["metin"] for g in d["gorunur"])


_ACILIS = "  const env = await bootLocal(); await bootNetwork(env); await bekle();"


def test_KRITIK_paylasim_yoklamasi_ONCE_bitince_manifest_temizligi_KARTI_SILMEZ(tmp_path):
    """Şükrü'deki sıra: yerel sonda (ms) manifestten (ağ) önce biter → kart çizilir → `bootNetwork` bildirim kutusunu temizler.
    MUTASYON: kart yeniden `#notice`'e çizilirse KIRMIZI."""
    d = _kos(_ACILIS + "\n  OUT.a = durum();", tmp_path)["a"]
    m = _metinler(d)
    assert "paylasimGerekli" in m and d["dugme"], f"paylaşım kartı açılışın ağ adımında silindi: {d}"
    assert "paylasimKvkk" in m, m


def test_KRITIK_cevrimdisi_acilis_notu_KARTI_EZMEZ(tmp_path):
    """Çevrimdışı açılış "Hazır (çevrimdışı)" notunu yazar — paylaşım kartı yerinde kalır, ikisi birlikte görünür."""
    d = _kos("  CEVRIMDISI = true;\n" + _ACILIS + "\n  OUT.a = durum();", tmp_path)["a"]
    m = _metinler(d)
    assert "paylasimGerekli" in m and d["dugme"], f"çevrimdışı notu paylaşım kartını ezdi: {d}"
    assert "offlineReady" in m, f"çevrimdışı notu kayboldu: {m}"


def test_KRITIK_manifest_ONCE_gelirse_kart_GUNCELLEME_onayini_EZMEZ(tmp_path):
    """Ters sıra: manifest + güncelleme onay kartı önce, paylaşım yoklaması sonra — ikisi de görünür kalır (Y253 onayı kaybolmaz)."""
    d = _kos(
        "  GECIKME = { paylasim_durumu: 80, fetch_profiles: 1 }; GUNCELLEME_KARTI = true;\n"
        + _ACILIS
        + "\n  OUT.a = durum();",
        tmp_path,
    )["a"]
    m = _metinler(d)
    assert "paylasimGerekli" in m and d["dugme"], f"paylaşım kartı yok: {d}"
    assert "GUNCELLEME-KARTI" in m, f"paylaşım kartı güncelleme onayını ezdi: {m}"


def test_KRITIK_durum_YOKLANAMAZSA_kart_gerekli_olabilir_ve_YONETICI_dugmesiyle_gorunur(tmp_path):
    """`paylasim_durumu` hata verirse (IPC / görev çöktü) kart SUSMAZ: "paylaşım gerekli olabilir" + aynı yönetici düğmesi.
    Çekirdeğin `belirsiz` yanıtı (veri dizininin varlığı / erişimi belirlenemedi) aynı kartı çizer."""
    out = _kos(
        "  PAYLASIM_HATA = true;\n"
        + _ACILIS
        + "\n  OUT.a = durum();\n"
        + "  PAYLASIM_HATA = false; PAYLASIM = { belirsiz: true };\n"
        + "  await refreshEnv(); await bekle(); OUT.b = durum();",
        tmp_path,
    )
    for k in ("a", "b"):
        m = _metinler(out[k])
        assert "paylasimBelirsiz" in m and out[k]["dugme"], f"{k}: durum belirlenemeyince kart yok: {out[k]}"
        assert "paylasimGerekli" not in m, f"{k}: belirsiz durumda kesin 'erişemiyor' metni: {m}"
        assert "paylasimKvkk" in m, f"{k}: düğmenin sonucu (KVKK) söylenmiyor: {m}"


def test_erisen_hesapta_KART_YOK_ve_bildirimler_eskisi_gibi(tmp_path):
    """Tek hesaplı saha (Y275): erişen hesapta kart ÇİZİLMEZ; çevrimdışı notu ve temizlik eskisi gibi."""
    out = _kos(
        "  PAYLASIM = { gerekli: false };\n"
        + _ACILIS
        + "\n  OUT.a = durum();\n"
        + "  CEVRIMDISI = true; await bootNetwork({}); await bekle(); OUT.b = durum();",
        tmp_path,
    )
    assert not out["a"]["dugme"] and "paylasim" not in _metinler(out["a"]), out["a"]
    assert not out["a"]["paylasimNotu"], out["a"]
    assert _metinler(out["b"]) == "offlineReady", out["b"]


def test_KRITIK_kurulduktan_sonra_SONUC_metni_bildirim_temizliginde_KALIR(tmp_path):
    """Düğme → `paylasim_kur` tamam → "kuruldu, oturumu kapatıp açın" metni; sonraki bildirim temizliği onu silmez. Hata → hata metni
    + düğme yeniden basılabilir."""
    out = _kos(
        _ACILIS
        + "\n  const b = kartDugmesi(); await b.onclick(); await bekle(); clearNotice(); OUT.a = durum();\n"
        + "  KUR_HATA = true; await refreshEnv(); await bekle(); const b2 = kartDugmesi(); await b2.onclick(); await bekle();\n"
        + "  OUT.b = durum(); OUT.b.basilabilir = !kartDugmesi().disabled;",
        tmp_path,
    )
    a = _metinler(out["a"])
    assert "paylasimKuruldu" in a and not out["a"]["dugme"], f"kuruldu metni yok ya da düğme kaldı: {out['a']}"
    assert "paylasim_kur" in out["a"]["cagri"]
    assert "KUR-HATASI" in _metinler(out["b"]) and out["b"]["basilabilir"], out["b"]


def test_dil_degisince_kart_YENIDEN_cizilir(tmp_path):
    """Kart ekrandayken dil değişirse aynı durumla yeniden çizilir (EN'de Türkçe kalmaz) — `applyLang` çağırır."""
    out = _kos(
        _ACILIS
        + "\n  $('paylasim').textContent = ''; $('notice').textContent = '';\n"
        + "  if (typeof paylasimDiliYenile === 'function') paylasimDiliYenile(); OUT.a = durum();",
        tmp_path,
    )
    assert "paylasimGerekli" in _metinler(out["a"]) and out["a"]["dugme"], out["a"]
    ham = _ham()
    dil = _fonksiyon(ham, "function applyLang()")
    assert "paylasimDiliYenile()" in dil, "applyLang paylaşım kartını yeniden çizmiyor"
