# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""«PROFİLLERİ DEĞİŞTİR» FARK AKIŞI + yedek notunun dili (denetim 2026-09-06).

Ölçülen kusurlar:
  · Düğme seçili HER profili topluyordu — kurulu olan (yeniden inmeyecek) da "Kur ve Başlat · X GB"
    içine giriyordu. Kullanıcı 0,15 GB inecekken 0,5 GB görüyordu.
  · Seçimi kaldırılan kurulu profil için HİÇBİR şey olmuyordu: ne ekranda işaret, ne backend çağrısı.
  · Yedek hedefi notu koda gömülü Türkçeydi → EN arayüzde Türkçe kalıyordu.

Bu dosya GERÇEK `profilFarki` / `updateInstallBtn` / `renderCards` / `profilleriUygula` /
`profilKaldir` / `doInstall` / `yedekHedefiKontrol` / `applyLang` kodunu sahte DOM + sahte
`invoke` ile Node'da KOŞTURUR (metin aramaz): rozetler, düğme etiketi/durumu, backend çağrı
SIRASI (remove_profiles → install_and_launch) ve dil değişiminde notun yeniden çizimi ölçülür.
Mutasyonlar (kanıtlandı, KIRMIZI): kurulu profil toplama geri eklenince; `kaldir` doluyken
`remove_profiles` atlanınca; not metni yeniden koda gömülünce.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"
_NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(_NODE is None, reason="node yok")

GiB = 1073741824
BASE = 81133442 + 1487710488  # canlı manifest 1.9.42 (app + deps katmanı)
HOME, VET, RESEARCH = 333465719, 152284455, 1613947855 + 1814085825


def _fonksiyon(ham: str, imza: str) -> str:
    i = ham.index(imza)
    kapanis = "\n      }"
    j = ham.index(kapanis, i) + len(kapanis)
    return ham[i:j]


def _satir(ham: str, baslangic: str) -> str:
    m = re.search(r"^[ \t]*" + re.escape(baslangic) + r".*$", ham, re.M)
    assert m, f"satır bulunamadı: {baslangic}"
    return m.group(0)


def _blok(ham: str, baslangic: str, bitis: str) -> str:
    i = ham.index(baslangic)
    j = ham.index(bitis, i) + len(bitis)
    return ham[i:j]


def _gb(n: int) -> str:
    """index.html `gb`: (n/GiB).toFixed(n >= GiB ? 1 : 2) — JS half-up yuvarlama."""
    from decimal import ROUND_HALF_UP, Decimal

    basamak = 1 if n >= GiB else 2
    return str(Decimal(n / GiB).quantize(Decimal(10) ** -basamak, rounding=ROUND_HALF_UP))


def _kos(
    tmp_path: Path,
    *,
    lang="tr",
    kurulu=(),
    secili=(),
    base_installed=True,
    base_bytes=BASE,
    uygula=False,
    kaldirma_hatasi=None,
    authed=True,
    yedek=None,
    dil_degistir=None,
    notu_temizle=False,
) -> dict:
    ham = _UI.read_text(encoding="utf-8")
    parcalar = [
        _blok(ham, "      const I18N = {", "\n      };"),
        _blok(ham, "      const PROFILE_META = {", "\n      };"),
        _satir(ham, "const PROFILE_DEPS"),
        _satir(ham, "const PROFILE_SOFT_DEPS"),
        _satir(ham, "const PROFILE_ORDER"),
        _fonksiyon(ham, "function withDeps(keys)"),
        _satir(ham, "function cumBytes(key)"),
        _satir(ham, "const gb = "),
        _satir(ham, "const profName = "),
        _fonksiyon(ham, "function orderedKeys()"),
        _fonksiyon(ham, "function profilFarki()"),
        _fonksiyon(ham, "function updateInstallBtn()"),
        _fonksiyon(ham, "function cekirdekKarti()"),
        _fonksiyon(ham, "function renderCards()"),
        _fonksiyon(ham, "function hataCumlesi(msg)"),
        _fonksiyon(ham, "function fail(msg)"),
        _satir(ham, "function clearErr()"),
        _fonksiyon(ham, "function notice(msg, onRetry)"),
        _satir(ham, "function clearNotice()"),
        _fonksiyon(ham, "function yedekNotuCiz(d)"),
        _fonksiyon(ham, "function yedekNotuDiliYenile()"),
        _fonksiyon(ham, "async function yedekHedefiKontrol()"),
        _fonksiyon(ham, "function applyLang()"),
        _fonksiyon(ham, "async function doInstall(profiles)"),
        _fonksiyon(ham, "async function profilKaldir(profiller)"),
        _fonksiyon(ham, "async function profilleriUygula()"),
    ]
    kod = "\n".join(parcalar)
    js = f"""
let LANG = {json.dumps(lang)};
const t = () => I18N[LANG];
let busy = false, installed = {json.dumps(list(kurulu))};
let profileKeys = ["home", "vet", "research"];
let sizes = {{ home: {HOME}, vet: {VET}, research: {RESEARCH} }};
let baseBytes = {base_bytes};
let baseInstalled = {json.dumps(base_installed)};
let selected = new Set({json.dumps(list(secili))});
let manifestRaw = "{{}}", authed = {json.dumps(authed)}, lastProfiles = [], resumeOp = null, appRunning = false;
let yedekNotuDurum = null;
const KALDIRMA_HATASI = {json.dumps(kaldirma_hatasi)};
const YEDEK = {json.dumps(yedek)};
// ── sahte DOM: yalnız kodun dokunduğu yüzey. textContent ataması ÇOCUKLARI da siler (gerçek DOM gibi). ──
class El {{
  constructor(tag) {{ this.tagName = tag; this.className = ""; this.type = ""; this.title = ""; this.disabled = false;
    this._t = ""; this.innerHTML = ""; this.hidden = false; this.attrs = {{}}; this.children = []; this.onclick = null;
    this.classList = {{ toggle() {{}}, add() {{}}, remove() {{}} }}; }}
  get textContent() {{ return this._t; }}
  set textContent(v) {{ this._t = String(v); this.children = []; }}
  setAttribute(k, v) {{ this.attrs[k] = String(v); }}
  getAttribute(k) {{ return this.attrs[k]; }}
  append(...cs) {{ for (const c of cs) this.children.push(c); }}
  appendChild(c) {{ this.children.push(c); return c; }}
  querySelector() {{ return new El("i"); }}
}}
const document = {{ createElement: (tag) => new El(tag), documentElement: {{ lang: "" }}, createTextNode: (s) => {{ const e = new El("#text"); e._t = s; return e; }} }};
const _el = {{}};
function $(id) {{ if (!_el[id]) _el[id] = new El("div"); return _el[id]; }}
$("notice").hidden = true; $("error").hidden = true; // gerçek HTML'de ikisi de `hidden` başlar
// ── kaydedici sahteler ──
const calls = [], screens = [];
function show(id) {{ screens.push(id); }}
function depNotice() {{}}
function resetInstallUI() {{ $("inst-title").textContent = t().instDl; }}
function indet() {{}}
function setInstallControls() {{}}
function startPolling() {{}}
function stopPolling() {{}}
function stopPrefetchPoll() {{}}
function renderChips() {{}}
function renderGuide() {{}}
function startEtiketi(x) {{ return x.start; }}
function setRunningUi() {{}}
function applyRememberLabel() {{}}
async function refreshEnv() {{ calls.push(["refreshEnv"]); }}
async function invoke(cmd, args) {{
  calls.push([cmd, args && args.profiles ? args.profiles.slice() : null]);
  if (cmd === "remove_profiles") {{
    if (KALDIRMA_HATASI) throw KALDIRMA_HATASI;
    const kalan = installed.filter((k) => !args.profiles.includes(k));
    return {{ status: "ok", removed: args.profiles.slice(), installed: kalan, freed_bytes: 1, kept_shared: 0 }};
  }}
  if (cmd === "install_and_launch") return {{ status: "ok" }};
  if (cmd === "yedek_hedefi_durumu") return YEDEK;
  return {{}};
}}

{kod}

function kartOzet(c) {{
  const meta = c.children.find((x) => x.className === "meta");
  const b = meta ? meta.children.find((x) => x.tagName === "b") : null;
  const etiket = (cls) => {{ const e = b ? b.children.find((x) => x.className === cls) : null; return e ? e.textContent : null; }};
  const size = c.children.find((x) => x.className === "size");
  return {{ cls: c.className, pressed: c.attrs["aria-pressed"], label: b ? b.textContent : null,
            reqtag: etiket("reqtag"), rmtag: etiket("rmtag"), size: size ? size.textContent : null }};
}}
const cocukMetni = (el, i) => (el.hidden || !el.children[i] ? null : el.children[i].textContent);
const notMetni = () => cocukMetni($("notice"), 0);
const notDugme = () => cocukMetni($("notice"), 1);
(async () => {{
  renderCards();
  const kartlar = $("cards").children.map(kartOzet);
  const btn = $("t-install").textContent, btnDisabled = $("btn-install").disabled;
  const out = {{ kartlar, btn, btnDisabled }};
  if (YEDEK) {{
    await yedekHedefiKontrol();
    out.notOnce = notMetni(); out.notDugmeOnce = notDugme();
    if ({json.dumps(bool(notu_temizle))}) clearNotice();
    if ({json.dumps(dil_degistir)}) {{ LANG = {json.dumps(dil_degistir)}; applyLang(); }}
    out.notSonra = notMetni(); out.notDugmeSonra = notDugme();
    out.yedekSorgusu = calls.filter((c) => c[0] === "yedek_hedefi_durumu").length;
  }}
  if ({json.dumps(bool(uygula))}) {{ await profilleriUygula(); }}
  out.calls = calls; out.screens = screens; out.installedSonra = installed.slice();
  out.hata = $("error").hidden ? null : ($("error").textContent || cocukMetni($("error"), 0));
  out.kartlarSonra = $("cards").children.map(kartOzet);
  console.log(JSON.stringify(out));
}})().catch((e) => {{ console.error(e && e.stack || e); process.exit(2); }});
"""
    dosya = tmp_path / "kapi.js"
    dosya.write_text(js, encoding="utf-8")
    r = subprocess.run([_NODE, str(dosya)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, f"Node hata:\n{r.stderr[-2000:]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def _kart(s: dict, key: str, sonra=False) -> dict:
    idx = ["home", "vet", "research"].index(key) + 1  # 0 = ana uygulama kartı
    return (s["kartlarSonra"] if sonra else s["kartlar"])[idx]


# ─────────────────────────── kart rozetleri + düğme toplamı ───────────────────────────


def test_KRITIK_kurulu_ve_secili_profil_KURULU_der_ve_TOPLAMA_GIRMEZ(tmp_path):
    s = _kos(tmp_path, kurulu=["home"], secili=["home", "vet"])
    assert _kart(s, "home")["size"] == "kurulu", f"kurulu+seçili kart boyut yerine 'kurulu' demeli: {_kart(s, 'home')}"
    assert _kart(s, "home")["rmtag"] is None, "kurulu+seçili kartta 'kaldırılacak' rozeti OLMAMALI"
    assert _kart(s, "vet")["size"] == f"{_gb(VET)} GB", "eklenecek kart kendi boyutunu yazmalı"
    assert s["btn"] == f"Kur ve Başlat · {_gb(VET)} GB", (
        f"düğme yalnız İNECEK olanı (vet) saymalı — kurulu home toplama girmemeli: {s['btn']!r}"
    )
    assert s["btnDisabled"] is False


def test_KRITIK_secimi_kaldirilan_kurulu_profil_KALDIRILACAK_rozeti_ve_acilacak_yer(tmp_path):
    s = _kos(tmp_path, kurulu=["home", "vet"], secili=["home"])
    v = _kart(s, "vet")
    assert v["rmtag"] == "kaldırılacak", f"kurulu+seçimsiz kartta kırmızı 'kaldırılacak' rozeti yok: {v}"
    assert v["pressed"] == "false" and "sel" not in v["cls"].split()
    assert v["size"] == f"{_gb(VET)} GB", f"kaldırılacak kart açılacak yeri (boyutunu) yazmalı: {v['size']}"
    # yalnız kaldırma → "Uygula ve Başlat", BOYUTSUZ (indirme yok)
    assert s["btn"] == "Uygula ve Başlat", (
        f"yalnız kaldırma varken etiket boyutsuz 'Uygula ve Başlat' olmalı: {s['btn']!r}"
    )
    assert s["btnDisabled"] is False


def test_ekle_toplami_ana_uygulama_kurulu_degilse_onu_da_sayar_kurulu_profili_saymaz(tmp_path):
    s = _kos(tmp_path, kurulu=["home"], secili=["home", "vet"], base_installed=False)
    assert s["btn"] == f"Kur ve Başlat · {_gb(VET + BASE)} GB", s["btn"]
    s2 = _kos(tmp_path, kurulu=["home"], secili=["home", "vet"], base_installed=True)
    assert s2["btn"] == f"Kur ve Başlat · {_gb(VET)} GB", s2["btn"]


def test_KRITIK_degisiklik_yoksa_dugme_KAPALI_ve_Degisiklik_yok(tmp_path):
    s = _kos(tmp_path, kurulu=["home", "vet"], secili=["home", "vet"])
    assert s["btnDisabled"] is True, "hiçbir fark yokken düğme açık kalmış (boş kurulum başlatır)"
    assert s["btn"] == "Değişiklik yok", s["btn"]


def test_KRITIK_hepsi_kaldirilirsa_dugme_KAPALI_ve_en_az_bir_profil(tmp_path):
    s = _kos(tmp_path, kurulu=["home", "vet"], secili=[])
    assert s["btnDisabled"] is True, "tüm profiller kaldırılmışken düğme açık — son profil silinirdi"
    assert s["btn"] == "En az bir profil seçili kalmalı", s["btn"]
    assert _kart(s, "home")["rmtag"] == "kaldırılacak" and _kart(s, "vet")["rmtag"] == "kaldırılacak"


def test_ilk_kurulum_davranisi_korunur(tmp_path):
    """Kurulu profil yokken (ilk kurulum) eski etiketler: boş seçim → 'Kur ve Başlat' kapalı."""
    s = _kos(tmp_path, kurulu=[], secili=[], base_installed=False)
    assert s["btnDisabled"] is True and s["btn"] == "Kur ve Başlat", s["btn"]
    s2 = _kos(tmp_path, kurulu=[], secili=["home"], base_installed=False)
    assert s2["btn"] == f"Kur ve Başlat · {_gb(HOME + BASE)} GB" and s2["btnDisabled"] is False


def test_ingilizce_rozetler_ve_etiketler(tmp_path):
    s = _kos(tmp_path, lang="en", kurulu=["home", "vet"], secili=["home", "research"])
    assert _kart(s, "vet")["rmtag"] == "will be removed"
    assert _kart(s, "home")["size"] == "installed"
    assert s["btn"] == f"Install & Start · {_gb(RESEARCH)} GB"
    s2 = _kos(tmp_path, lang="en", kurulu=["home", "vet"], secili=["home"])
    assert s2["btn"] == "Apply & Start"


# ─────────────────────────── tıklama akışı: SIRA ve KOŞUL ───────────────────────────


def _komutlar(s: dict) -> list:
    return [c for c in s["calls"] if c[0] in ("remove_profiles", "install_and_launch")]


def test_KRITIK_ekle_ve_kaldir_birlikte_ONCE_remove_profiles_SONRA_install(tmp_path):
    s = _kos(tmp_path, kurulu=["home", "vet"], secili=["home", "research"], uygula=True)
    k = _komutlar(s)
    assert k == [["remove_profiles", ["vet"]], ["install_and_launch", ["research"]]], (
        f"beklenen sıra: remove_profiles([vet]) → install_and_launch([research]); olan: {k}"
    )
    assert s["installedSonra"] == ["home"] or "research" in s["installedSonra"], (
        f"kaldırma sonucu `installed` tazelenmemiş: {s['installedSonra']}"
    )
    assert s["hata"] is None


def test_KRITIK_yalniz_kaldirma_remove_profiles_cagrilir_install_CAGRILMAZ_hazir_ekrani(tmp_path):
    s = _kos(tmp_path, kurulu=["home", "vet"], secili=["home"], uygula=True)
    k = _komutlar(s)
    assert k == [["remove_profiles", ["vet"]]], f"yalnız kaldırmada tek çağrı remove_profiles([vet]) olmalı: {k}"
    assert s["screens"][-1] == "s-ready", f"kaldırma bitince Hazır! ekranına dönülmeli: {s['screens']}"
    assert s["installedSonra"] == ["home"], s["installedSonra"]
    assert s["hata"] is None


def test_KRITIK_yalniz_ekleme_remove_profiles_CAGRILMAZ_install_yalniz_yeni_profili_tasir(tmp_path):
    s = _kos(tmp_path, kurulu=["home"], secili=["home", "vet"], uygula=True)
    k = _komutlar(s)
    assert k == [["install_and_launch", ["vet"]]], (
        f"yalnız eklemede remove_profiles ÇAĞRILMAMALI ve kurulu home yeniden indirilmemeli: {k}"
    )


def test_degisiklik_yokken_tiklama_hicbir_backend_cagrisi_yapmaz(tmp_path):
    s = _kos(tmp_path, kurulu=["home"], secili=["home"], uygula=True)
    assert _komutlar(s) == [] and s["screens"] == []
    s0 = _kos(tmp_path, kurulu=["home"], secili=[], uygula=True)
    assert _komutlar(s0) == [] and s0["screens"] == [], "son profil kaldırılmaya çalışıldı"


def test_kaldirma_hatasi_install_BASLAMAZ_secim_ekrani_ve_sebep_gosterilir(tmp_path):
    neden = "vet için önbellekte vet.zip yok — 'Kurulumu onar' sonrası tekrar deneyin"
    s = _kos(tmp_path, kurulu=["home", "vet"], secili=["home", "research"], uygula=True, kaldirma_hatasi=neden)
    k = _komutlar(s)
    assert k == [["remove_profiles", ["vet"]]], f"kaldırma başarısızken install_and_launch BAŞLAMAMALI: {k}"
    assert s["screens"][-1] == "s-select", f"hatada seçim ekranına dönülmeli: {s['screens']}"
    assert s["hata"] and neden in s["hata"], f"hata kutusu backend sebebini taşımalı: {s['hata']!r}"
    assert s["installedSonra"] == ["home", "vet"], "hatada `installed` değişmemeli"


def test_ekleme_varken_giris_yoksa_HICBIR_sey_yapilmaz_giris_ekrani(tmp_path):
    """Yarım iş yok: giriş yoksa kaldırma da yapılmaz (kullanıcı giriş sonrası tek seferde uygular)."""
    s = _kos(tmp_path, kurulu=["home", "vet"], secili=["home", "research"], uygula=True, authed=False)
    assert _komutlar(s) == [], "giriş yokken backend çağrısı yapıldı"
    assert s["screens"] == ["s-login"], s["screens"]


def test_yalniz_kaldirma_giris_GEREKTIRMEZ(tmp_path):
    s = _kos(tmp_path, kurulu=["home", "vet"], secili=["home"], uygula=True, authed=False)
    assert _komutlar(s) == [["remove_profiles", ["vet"]]]


# ─────────────────────────── yedek notu: dil değişince yeniden çizim ───────────────────────────


def test_KRITIK_yedek_notu_EN_dile_gecince_INGILIZCE_yeniden_cizilir_backend_e_sorulmaz(tmp_path):
    s = _kos(tmp_path, yedek={"yol": None, "erisilebilir": False}, dil_degistir="en")
    assert s["notOnce"] and "AYNI diskte" in s["notOnce"], f"TR not beklenen metni taşımıyor: {s['notOnce']!r}"
    assert s["notDugmeOnce"] == "Yedek hedefi seç"
    assert s["notSonra"] and "SAME disk" in s["notSonra"], (
        f"EN'e geçince yedek notu Türkçe kaldı / yeniden çizilmedi: {s['notSonra']!r}"
    )
    assert s["notDugmeSonra"] == "Choose backup destination", s["notDugmeSonra"]
    assert s["yedekSorgusu"] == 1, f"dil değişimi backend'e yeniden sormamalı: {s['yedekSorgusu']} sorgu"


def test_yedek_notu_erisilemeyen_hedef_yolu_iki_dilde_tasir(tmp_path):
    s = _kos(tmp_path, yedek={"yol": "E:\\PEMF_Yedek", "erisilebilir": False}, dil_degistir="en")
    assert "E:\\PEMF_Yedek" in s["notOnce"] and "erişilemiyor" in s["notOnce"]
    assert "E:\\PEMF_Yedek" in s["notSonra"] and "unreachable" in s["notSonra"]


def test_yedek_notu_temizlenmisse_dil_degisimi_onu_GERI_GETIRMEZ(tmp_path):
    s = _kos(tmp_path, yedek={"yol": None, "erisilebilir": False}, dil_degistir="en", notu_temizle=True)
    assert s["notOnce"] and s["notSonra"] is None, f"temizlenmiş not dil değişince geri geldi: {s['notSonra']!r}"


def test_yedek_hedefi_saglamsa_not_yok(tmp_path):
    s = _kos(tmp_path, yedek={"yol": "E:\\PEMF_Yedek", "erisilebilir": True}, dil_degistir="en")
    assert s["notOnce"] is None and s["notSonra"] is None


# ─────────────────────────── yapısal kapılar ───────────────────────────


def test_sozluk_iki_dilde_yeni_anahtarlari_tasir():
    ham = _UI.read_text(encoding="utf-8")
    tr = _blok(ham, "        tr: {", "\n        },")
    en = _blok(ham, "        en: {", "\n        },")
    for ad in ("applyStart", "noChange", "keepOne", "willRemove", "removing", "backupSameDisk", "backupChoose"):
        assert re.search(rf"\b{ad}:\s*\"[^\"]+\"", tr), f"tr sözlüğünde {ad} yok/boş"
        assert re.search(rf"\b{ad}:\s*\"[^\"]+\"", en), f"en sözlüğünde {ad} yok/boş"
    for ad in ("removeFailed", "backupUnreachable"):
        assert re.search(rf"\b{ad}:\s*\(\w+\)\s*=>", tr), f"tr sözlüğünde {ad} fonksiyonu yok"
        assert re.search(rf"\b{ad}:\s*\(\w+\)\s*=>", en), f"en sözlüğünde {ad} fonksiyonu yok"


def test_kur_dugmesi_fark_akisina_bagli_ve_yedek_notu_kodda_gomulu_degil():
    ham = _UI.read_text(encoding="utf-8")
    m = re.search(r'\$\("btn-install"\)\.onclick\s*=\s*\(\)\s*=>\s*\{([^}]*)\}', ham)
    assert m and "profilleriUygula()" in m.group(1), "Kur düğmesi profilleriUygula() akışına bağlı değil"
    assert "applyLang()" in ham and "yedekNotuDiliYenile();" in _fonksiyon(ham, "function applyLang()"), (
        "applyLang yedek notunu yeniden çizmiyor"
    )
    govde = _fonksiyon(ham, "async function yedekHedefiKontrol()") + _fonksiyon(ham, "function yedekNotuCiz(d)")
    assert "Yedek hedefi şu an" not in govde and "Yedek hedefi seç" not in govde, (
        "yedek notu metni yeniden koda gömülmüş"
    )


def test_KRITIK_ana_uygulama_YOKKEN_kayitli_profiller_yeniden_kurulur_kilitlenmez(tmp_path):
    """Çalışma-zamanı ağacı silinmiş (yarım kalan güncelleme ağacı siler) ama kayıt dosyası dolu:
    aynı seçim "Değişiklik yok" deyip kullanıcıyı KİLİTLEMEMELİ. Kayıtlı profiller yeniden İNMEZ
    (toplama girmez, kart 'kurulu' der) ama kurulum hepsini yeniden geçer; hiçbiri kaldırılmaz ve
    'kaldırılacak' rozeti çıkmaz (sahip incelemesi 2026-09-06)."""
    s = _kos(tmp_path, kurulu=["home", "vet"], secili=["home", "vet"], base_installed=False, uygula=True)
    assert s["btnDisabled"] is False, "ana uygulama yokken aynı seçim düğmeyi kapatmış — kurtarma yolu kilitli"
    assert s["btn"] == f"Kur ve Başlat · {_gb(BASE)} GB", s["btn"]
    assert _kart(s, "home")["size"] == "kurulu" and _kart(s, "home")["rmtag"] is None, _kart(s, "home")
    k = _komutlar(s)
    assert len(k) == 1 and k[0][0] == "install_and_launch" and sorted(k[0][1]) == ["home", "vet"], (
        f"ana uygulama yokken kurulum SEÇİLEN HER profili geçmeli, kaldırma OLMAMALI: {k}"
    )
    s2 = _kos(tmp_path, kurulu=["home", "vet"], secili=[], base_installed=False)
    assert s2["btn"] == "Kur ve Başlat" and s2["btnDisabled"] is True, "ilk kurulum etiketi korunmalı"
    assert _kart(s2, "vet")["rmtag"] is None, "ana uygulama yokken 'kaldırılacak' rozeti yanıltıcı (silinmez)"
