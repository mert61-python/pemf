# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""PROFİL SEÇİMİNDE "UYGULAMA ÇEKİRDEĞİ" KARTI — önceden seçili, KALDIRILAMAZ, boyutu doğru (2026-09-06).

Sahip isteği: `base` (ana uygulama + ortak modeller) her kurulumda kuruluyor ama ekranda
görünmüyordu; yalnız düğme toplamına sessizce ekleniyordu. Kullanıcı 0,3 GB'lık kartı seçip
1,8 GB indiğini görünce şaşırıyordu. Artık en üstte, seçili ve kilitli bir kart var.

Bu dosya GERÇEK `renderCards` / `cekirdekKarti` / `updateInstallBtn` kodunu sahte bir DOM ile
Node'da KOŞTURUR (metin aramaz): kartın ilk sırada olduğu, tıklamanın hiçbir şeyi
değiştirmediği, `selected`e girmediği, boyutun katmanlardan geldiği ve "kurulu" durumu ölçülür.
Mutasyon: `box.appendChild(cekirdekKarti())` satırı silinince ve tıklama seçimi değiştirince
KIRMIZI (kanıtlandı).
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
BASE_APP, BASE_DEPS = 81133442, 1487710488  # canlı manifest 1.9.42 (app + deps katmanı)
HOME, VET, RESEARCH, RESEARCH2 = 333465719, 152284455, 1613947855, 1814085825

# Sözlük SENTINEL: gerçek metin değil, kablolama ölçülür (kart t().coreName'i mi kullanıyor?).
_SOZLUK = {
    "tr": {
        "coreName": "CORE_TR",
        "coreDesc": "DESC_TR",
        "coreTag": "TAG_TR",
        "coreInstalled": "KURULU_TR",
        "coreLocked": "LOCK_TR",
        "install": "KUR_TR",
        # fark akışı anahtarları (2026-09-06) — bu dosyada kurulu profil yok, yalnız kablolama için.
        "applyStart": "UYGULA_TR",
        "noChange": "FARKYOK_TR",
        "keepOne": "BIRKALSIN_TR",
        "willRemove": "KALDIR_TR",
    },
    "en": {
        "coreName": "CORE_EN",
        "coreDesc": "DESC_EN",
        "coreTag": "TAG_EN",
        "coreInstalled": "KURULU_EN",
        "coreLocked": "LOCK_EN",
        "install": "KUR_EN",
        "applyStart": "UYGULA_EN",
        "noChange": "FARKYOK_EN",
        "keepOne": "BIRKALSIN_EN",
        "willRemove": "KALDIR_EN",
    },
}


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
    """index.html `gb`: (n/GiB).toFixed(n >= GiB ? 1 : 2) — JS toFixed yuvarlaması (half-up)."""
    from decimal import ROUND_HALF_UP, Decimal

    basamak = 1 if n >= GiB else 2
    return str(Decimal(n / GiB).quantize(Decimal(10) ** -basamak, rounding=ROUND_HALF_UP))


def _kos(
    tmp_path: Path,
    *,
    lang="tr",
    base_installed=False,
    base_bytes=BASE_APP + BASE_DEPS,
    secili=(),
    tikla=None,
    kurulu=(),
) -> dict:
    ham = _UI.read_text(encoding="utf-8")
    render = _fonksiyon(ham, "function renderCards()")
    assert "cekirdekKarti()" in render or True  # varlık kapısı aşağıda ayrı ölçülür
    kod = "\n".join(
        [
            _blok(ham, "      const PROFILE_META = {", "\n      };"),
            _satir(ham, "const PROFILE_DEPS"),
            _satir(ham, "const PROFILE_SOFT_DEPS"),
            _satir(ham, "const PROFILE_ORDER"),
            _fonksiyon(ham, "function withDeps(keys)"),
            _satir(ham, "function cumBytes(key)"),
            _satir(ham, "const gb = "),
            _fonksiyon(ham, "function orderedKeys()"),
            # 2026-09-06: düğme toplamı artık `profilFarki()`ten gelir (kurulu profil sayılmaz).
            _fonksiyon(ham, "function profilFarki()"),
            _fonksiyon(ham, "function updateInstallBtn()"),
            _fonksiyon(ham, "function cekirdekKarti()") if "function cekirdekKarti()" in ham else "",
            render,
        ]
    )
    js = f"""
const SOZLUK = {json.dumps(_SOZLUK, ensure_ascii=False)};
let LANG = {json.dumps(lang)};
const t = () => SOZLUK[LANG];
let busy = false, installed = {json.dumps(list(kurulu))};
let profileKeys = ["home", "vet", "research"];
let sizes = {{ home: {HOME}, vet: {VET}, research: {RESEARCH + RESEARCH2} }};
let baseBytes = {base_bytes};
let baseInstalled = {json.dumps(base_installed)};
let selected = new Set({json.dumps(list(secili))});
function depNotice() {{}}
// ── sahte DOM: yalnızca renderCards'ın dokunduğu yüzey ──
class El {{
  constructor(tag) {{ this.tagName = tag; this.className = ""; this.type = ""; this.title = ""; this.disabled = false;
    this.textContent = ""; this.innerHTML = ""; this.hidden = false; this.attrs = {{}}; this.children = []; this.onclick = null; }}
  setAttribute(k, v) {{ this.attrs[k] = String(v); }}
  getAttribute(k) {{ return this.attrs[k]; }}
  append(...cs) {{ for (const c of cs) this.children.push(c); }}
  appendChild(c) {{ this.children.push(c); return c; }}
}}
const document = {{ createElement: (tag) => new El(tag) }};
const _el = {{}};
function $(id) {{ if (!_el[id]) _el[id] = new El("div"); return _el[id]; }}

{kod}

function kartOzet(c) {{
  const meta = c.children.find((x) => x.className === "meta");
  const b = meta ? meta.children.find((x) => x.tagName === "b") : null;
  const tag = b ? b.children.find((x) => x.className === "reqtag") : null;
  const size = c.children.find((x) => x.className === "size");
  return {{ cls: c.className, pressed: c.attrs["aria-pressed"], ariaDisabled: c.attrs["aria-disabled"] || null,
            label: b ? b.textContent : null, tag: tag ? tag.textContent : null, size: size ? size.textContent : null,
            title: c.title, disabled: c.disabled }};
}}
renderCards();
const once = $("cards").children.map(kartOzet);
const tikla = {json.dumps(tikla)};
if (tikla !== null) {{
  const idx = tikla === "core" ? 0 : ["home", "vet", "research"].indexOf(tikla) + 1;
  $("cards").children[idx].onclick();
}}
const sonra = $("cards").children.map(kartOzet);
console.log(JSON.stringify({{ once, sonra, selected: [...selected], btn: $("t-install").textContent, btnDisabled: $("btn-install").disabled }}));
"""
    dosya = tmp_path / "kapi.js"
    dosya.write_text(js, encoding="utf-8")
    r = subprocess.run([_NODE, str(dosya)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, f"Node hata:\n{r.stderr[-1500:]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


# ─────────────────────────── davranışsal kapılar ───────────────────────────


def test_KRITIK_cekirdek_karti_ILK_sirada_secili_ve_kilitli(tmp_path):
    s = _kos(tmp_path)
    kartlar = s["once"]
    assert len(kartlar) == 4, f"4 kart beklenir (çekirdek + 3 profil), {len(kartlar)} çizildi: {kartlar}"
    c = kartlar[0]
    assert "core" in c["cls"].split() and "sel" in c["cls"].split(), f"ilk kart çekirdek+seçili değil: {c}"
    assert c["pressed"] == "true", "çekirdek aria-pressed=true olmalı (seçili)"
    assert c["ariaDisabled"] == "true", "çekirdek aria-disabled=true olmalı (ekran okuyucu 'değiştirilemez' desin)"
    assert c["disabled"] is False, "çekirdek `disabled` OLMAMALI — odaklanabilir kalmalı (Tab ile ulaşılır)"
    assert c["label"] == "CORE_TR" and c["tag"] == "TAG_TR", f"çekirdek etiketi t().coreName/coreTag'den gelmiyor: {c}"
    assert c["title"] == "LOCK_TR", "çekirdek ipucu (title) kilit açıklamasını taşımalı"
    # profiller sırayla ve çekirdekten SONRA
    assert [k["label"] for k in kartlar[1:]] == ["Ev Sahibi", "Veteriner Hekim", "Araştırma Modu"]


def test_KRITIK_cekirdek_tiklanamaz_secimi_degistirmez_selected_a_girmez(tmp_path):
    s = _kos(tmp_path, secili=["vet"], tikla="core")
    assert s["sonra"][0]["cls"] == s["once"][0]["cls"] and s["sonra"][0]["pressed"] == "true", (
        "çekirdek tıklanınca seçim durumu DEĞİŞTİ — kaldırılamaz olmalı"
    )
    assert s["selected"] == ["vet"], (
        f"çekirdek tıklaması `selected`i değiştirdi: {s['selected']} (kurulum çağrısı bozulur)"
    )
    # kontrol: gerçek profil tıklaması hâlâ çalışıyor (kapı yanlış-yeşil değil)
    s2 = _kos(tmp_path, secili=["vet"], tikla="home")
    assert sorted(s2["selected"]) == ["home", "vet"], "profil kartı tıklaması artık çalışmıyor"


def test_KRITIK_boyutlar_cekirdek_katmanlardan_profiller_YALNIZ_kendi(tmp_path):
    s = _kos(tmp_path)
    k = s["once"]
    assert k[0]["size"] == f"{_gb(BASE_APP + BASE_DEPS)} GB", f"çekirdek boyutu app+deps olmalı: {k[0]['size']}"
    assert k[1]["size"] == f"{_gb(HOME)} GB", f"home kartı kendi boyutunu yazmalı: {k[1]['size']}"
    assert k[2]["size"] == f"{_gb(VET)} GB", f"vet kartı kendi boyutunu yazmalı: {k[2]['size']}"
    assert k[3]["size"] == f"{_gb(RESEARCH + RESEARCH2)} GB", "research kartı ana+parça toplamını yazmalı"


def test_KRITIK_dugme_toplami_cekirdek_arti_secilenler(tmp_path):
    s = _kos(tmp_path, secili=["home"])
    assert s["btn"] == f"KUR_TR · {_gb(BASE_APP + BASE_DEPS + HOME)} GB", f"toplam çekirdek+home olmalı: {s['btn']}"
    assert s["btnDisabled"] is False
    # hiç profil yoksa: çekirdek tek başına kurulmaz, düğme kapalı (profil zorunlu)
    s0 = _kos(tmp_path)
    assert s0["btnDisabled"] is True and s0["btn"] == "KUR_TR", "profil seçilmeden düğme açılmamalı"


def test_cekirdek_KURULUYSA_boyut_yerine_kurulu_der_ve_toplama_girmez(tmp_path):
    s = _kos(tmp_path, base_installed=True, secili=["vet"])
    assert s["once"][0]["size"] == "KURULU_TR", f"kuruluyken 'kurulu' yazmalı: {s['once'][0]['size']}"
    assert s["btn"] == f"KUR_TR · {_gb(VET)} GB", f"kuruluyken toplama çekirdek eklenmemeli: {s['btn']}"


def test_KRITIK_kurulu_profil_kurulu_der_ve_toplama_GIRMEZ(tmp_path):
    """ "Profilleri değiştir" (2026-09-06): kurulu+seçili profil yeniden inmez → kartta 'kurulu',
    düğme toplamı yalnız YENİ seçileni sayar (ayrıntılı akış: test_launcher_profil_degistir)."""
    s = _kos(tmp_path, base_installed=True, kurulu=["home"], secili=["home", "vet"])
    assert s["once"][1]["size"] == "KURULU_TR", f"kurulu home kartı 'kurulu' demeli: {s['once'][1]['size']}"
    assert s["btn"] == f"KUR_TR · {_gb(VET)} GB", f"kurulu home toplama girmemeli, yalnız vet: {s['btn']}"


def test_dil_degisince_cekirdek_karti_yeniden_etiketlenir(tmp_path):
    s = _kos(tmp_path, lang="en")
    c = s["once"][0]
    assert c["label"] == "CORE_EN" and c["tag"] == "TAG_EN" and c["title"] == "LOCK_EN"


def test_manifest_boyutsuz_gelmeden_cekirdek_boyutu_bos(tmp_path):
    """Manifest gelmeden çizim: boyut '' (profillerle aynı davranış), kart yine seçili+kilitli."""
    s = _kos(tmp_path, base_bytes=0)
    assert s["once"][0]["size"] == "" and "core" in s["once"][0]["cls"]


# ─────────────────────────── yapısal kapılar ───────────────────────────


def test_sozluk_iki_dilde_cekirdek_anahtarlarini_tasir_ve_aciklama_cekirdegi_soyler():
    ham = _UI.read_text(encoding="utf-8")
    tr = _blok(ham, "        tr: {", "\n        },")
    en = _blok(ham, "        en: {", "\n        },")
    for ad in ("coreName", "coreDesc", "coreTag", "coreInstalled", "coreLocked"):
        assert re.search(rf"\b{ad}:\s*\"[^\"]+\"", tr), f"tr sözlüğünde {ad} yok/boş"
        assert re.search(rf"\b{ad}:\s*\"[^\"]+\"", en), f"en sözlüğünde {ad} yok/boş"
    assert "ana uygulama" in re.search(r'selLead:\s*"([^"]+)"', tr).group(1).lower(), (
        "tr selLead ana uygulamayı anlatmıyor"
    )
    assert "main application" in re.search(r'selLead:\s*"([^"]+)"', en).group(1).lower(), (
        "en selLead main application'ı anlatmıyor"
    )
    # statik HTML varsayılanı tr selLead ile AYNI (JS çalışmadan da doğru metin görünsün)
    statik = re.search(r'id="t-sel-lead">([^<]+)<', ham).group(1)
    assert statik == re.search(r'selLead:\s*"([^"]+)"', tr).group(1), "statik #t-sel-lead tr selLead ile ayrıştı"


def test_cekirdek_boyutu_katmanlardan_hesaplanir():
    """≥1.9.13 istemci katman indirir; boyut `layers[platform].app+deps` olmalı, monolit yedek."""
    ham = _UI.read_text(encoding="utf-8")
    i = ham.index("baseBytes = katToplam")
    blok = ham[i - 400 : i + 120]
    assert "m.layers?.[info.platform]" in blok and "deps?.size" in blok and "app?.size" in blok
    assert "m.runtimes?.[info.platform]?.size ?? m.base?.size" in blok, "katman yoksa monolit yedeği kalkmış"


def test_kilavuz_iki_dilde_cekirdek_kartini_anlatir():
    ham = _UI.read_text(encoding="utf-8")
    assert "Ana uygulama" in _blok(ham, "Profil(ler)inizi seçin", "\"],"), (
        "TR kılavuz 1. adım çekirdek kartını anlatmıyor"
    )
    assert "Main application" in _blok(ham, "Choose your profile(s)", "\"],"), (
        "EN kılavuz 1. adım çekirdek kartını anlatmıyor"
    )
