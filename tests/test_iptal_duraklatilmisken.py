# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""[5.6] DURAKLAT → İPTAL ÖLÜYDÜ + [5.10] İPTAL YABANCI .part SİLİYORDU (2. tur, sahip onayı 2026-08-20).

[5.6] Ölçülen kusur: pause'da kurulum komutu {status:"paused"} ile çoktan dönmüş, `CTL_CANCEL`
bayrağını okuyacak görev kalmamıştı; her komut girişi de bayrağı CTL_RUN ile eziyordu → İptal
grileşiyor, ekran süresiz "Duraklatıldı"da kalıyordu. Düzeltme: `iptalTiklandi` duraklatılmışken
temizliği GÖREVSİZ yapar (açılıştaki "yarım kaldı → İptal et" yolundaki `discard_pending` aynısı:
bekleyen kayıt düşer, güncel planın .part'ları korunur) ve ekranı hazır/seçim'e döndürür; koşan
görev varken bayrak yolu (cancel_install) AYNEN.

[5.10] Ölçülen kusur: `install_and_launch` iptal dalı `clear_partials(&root, &[])` çağırıyordu —
"yabancı .part sorunu discard_pending yolundaydı" gerekçesi EŞZAMANLILIKTA yanlış: ön-indirme
kilidi yalnız yoklayıp bırakır ve kilitsiz indirir; kurulumdan önce başlamış arka plan
ön-indirmesinin ≤1,4 GB .part'ı bu iptalle siliniyordu (FILE_SHARE_DELETE silmeyi kabul eder,
sonraki rename düşer — 2026-08-17'de discard_pending'de kapatılan sınıfın aynısı). Düzeltme:
aynı plan-koruması (`plan_part_paths`); çekirdek sözleşme launcher/core/tests/iptal_temizligi.rs.

Node-harness deseni test_devam_et_duraklatilmis_guncelleme.py'den.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"
_MAIN_RS = _KOK / "launcher" / "app" / "src" / "main.rs"
_NODE = shutil.which("node")


# ─────────────────────────── [5.10] yapısal kapı (Rust, yorum-soyulmuş) ───────────────────────────


def _rust_soy(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"//[^\n]*", " ", src)
    return src


def test_KRITIK_5_10_kurulum_iptali_plan_partlarini_KORUR():
    """install_and_launch iptal dalı clear_partials'ı PLAN korumasıyla çağırmalı (`&[]` değil)."""
    soy = _rust_soy(_MAIN_RS.read_text(encoding="utf-8", errors="replace"))
    i = soy.index("async fn install_and_launch")
    j = soy.index("async fn ", i + 10)
    govde = soy[i:j]
    # SON oluşum: ilki spawn_blocking closure'ındaki `return Ok(InstallOutcome::Cancelled)`,
    # temizliği yapan match kolu sonda (ilk koşuda ölçüldü).
    k = govde.rindex("InstallOutcome::Cancelled")
    dal = govde[k : k + 600]
    m = re.search(r"clear_partials\s*\(\s*&root\s*,\s*([^)]*)\)", dal)
    assert m, "iptal dalında clear_partials çağrısı bulunamadı — temizlik kayboldu mu?"
    # 17. parti (adversaryal inceleme): yalnız `plan_part_paths` ALT-DİZİSİ yetmez — boş/bozuk
    # manifest'le (`plan_part_paths("", ...)` → boş liste → TÜM .part'lar silinir) ya da aynı adlı
    # yerel değişkenle kapı yeşil geçerdi. Komutun kendi manifest klonu da pinli.
    # (dış yakalama ilk ')'de kesildiğinden iç desen kapanış parantezi İÇERMEZ — ilk koşuda ölçüldü)
    assert re.search(r"plan_part_paths\s*\(\s*&manifest_raw_iptal\s*,\s*&root", m.group(1)), (
        f"iptal dalı clear_partials'ı KOMUTUN MANİFESTİYLE beslenen plan koruması olmadan çağırıyor "
        f"({m.group(1).strip()!r}) — eşzamanlı arka plan ön-indirmesinin .part'ı silinir (bulgu [5.10])"
    )


def test_KARSIT_5_10_discard_pending_korumasi_AYNEN():
    """discard_pending'in 2026-08-17 koruması değişmemiş olmalı (aynı desen, iki yol)."""
    soy = _rust_soy(_MAIN_RS.read_text(encoding="utf-8", errors="replace"))
    i = soy.index("fn discard_pending")
    govde = soy[i : i + 700]
    assert "plan_part_paths" in govde, "discard_pending'in plan koruması kaybolmuş"


# ─────────────────────────── [5.6] davranışsal (Node-harness) ───────────────────────────

pytestmark_node = pytest.mark.skipif(_NODE is None, reason="node yok")


def _fonksiyon(ham: str, imza: str) -> str:
    i = ham.index(imza)
    kapanis = chr(10) + "      }"
    j = ham.index(kapanis, i) + len(kapanis)
    return ham[i:j]


def _satir(ham: str, parca: str) -> str:
    return next(s for s in ham.splitlines() if parca in s)


def _kos(senaryo: str, tmp_path: Path) -> dict:
    ham = _UI.read_text(encoding="utf-8")

    do_install = _fonksiyon(ham, "async function doInstall(profiles)")
    iptal = _fonksiyon(ham, "function iptalTiklandi()")
    assert "install_and_launch" in do_install, "doInstall cikarimi YARIM"
    assert "discard_pending" in iptal and "cancel_install" in iptal, "iptalTiklandi cikarimi YARIM"

    kod = "\n".join(
        [
            _satir(ham, 'const SCREENS = ["s-detect"'),
            _fonksiyon(ham, "function show(id)"),
            _satir(ham, "function curScreen()"),
            "const KAPI_ZAMAN_ASIMI_MS = 25000; let startKapiTimer = null;",
            _fonksiyon(ham, "function startKapisiKapat()"),
            _fonksiyon(ham, "function startKapisiAc()"),
            _fonksiyon(ham, "function startKapisiKapaliMi()"),
            _fonksiyon(ham, "function startEtiketi(x)"),
            _satir(ham, "let pausedOp = false;"),
            _fonksiyon(ham, "function setInstallControls(mode)"),
            _fonksiyon(ham, "function showPaused()"),
            _fonksiyon(ham, "function iptalTiklandi()"),
            do_install,
        ]
    )

    js = f"""
let busy = false, baseInstalled = true, manifestRaw = "manifest-v1", authed = true;
let resumeOp = null, lastProfiles = null, installed = [];
const cagrilar = [];

const t = () => ({{ pausedTitle: "Duraklatildi", pausedLead: "duraklatildi-alt",
  loginRequired: "giris", start: "Baslat", backToApp: "don", startChecking: "kontrol" }});

const _el = {{}};
function $(id) {{
  if (!_el[id]) _el[id] = {{ textContent: "", hidden: false, disabled: false, dataset: {{}}, onclick: null }};
  return _el[id];
}}
function setTimeout(fn, ms) {{ return 1; }}
function clearTimeout(id) {{}}
function startPolling() {{}}
function stopPolling() {{}}
function resetInstallUI() {{}}
function renderChips() {{}}
function clearErr() {{}}
function clearNotice() {{}}
function notice(m) {{}}
function fail(m) {{ cagrilar.push(["FAIL", String(m)]); }}
async function refreshEnv() {{ return {{}}; }}

let KURULUM_SONUCU = {{ status: "paused" }};
async function invoke(ad, args) {{
  cagrilar.push([ad, args && args.manifestRaw]);
  if (ad === "install_and_launch") return KURULUM_SONUCU;
  return null;
}}

{kod}

const OUT = {{}};
function anlik(ad) {{
  OUT[ad] = {{
    ekran: curScreen(),
    pausedOp,
    resumeVar: !!resumeOp,
    discard: cagrilar.filter((c) => c[0] === "discard_pending").length,
    cancel: cagrilar.filter((c) => c[0] === "cancel_install").length,
    discardManifest: (cagrilar.find((c) => c[0] === "discard_pending") || [])[1] || null,
  }};
}}
(async () => {{
{senaryo}
  console.log(JSON.stringify(OUT));
}})();
"""
    yol = tmp_path / "iptal_duraklatilmisken.mjs"
    yol.write_text(js, encoding="utf-8")
    r = subprocess.run([_NODE, str(yol)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"node hatasi: {r.stderr[-900:]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


_SENARYO = """
  for (const s of SCREENS) $(s).hidden = (s !== "s-ready");
  await doInstall(["home"]);          // komut {status:"paused"} dondu -> showPaused kostu
  busy = false;
  anlik("duraklatildi");
  iptalTiklandi();                    // [5.6] duraklatilmisken IPTAL
  await Promise.resolve(); await Promise.resolve(); // refreshEnv().then zinciri bosalsin
  anlik("iptal_sonrasi");
  setInstallControls("running");      // karsit-kanit: kosarken bayrak yolu AYNEN
  iptalTiklandi();
  anlik("kosarken_iptal");
"""


@pytestmark_node
def test_ON_KOSUL_duraklatilmis_duruma_ulasildi(tmp_path):
    o = _kos(_SENARYO, tmp_path)
    assert o["duraklatildi"]["ekran"] == "s-install", f"duraklatilmis ekrana ulasilamadi: {o['duraklatildi']}"
    assert o["duraklatildi"]["pausedOp"] is True, "showPaused pausedOp bayragini kurmadi"


@pytestmark_node
def test_KRITIK_5_6_duraklatilmisken_IPTAL_calisir(tmp_path):
    """İptal ekranı 'Duraklatıldı'dan çıkarmalı ve temizliği görevsiz yapmalı (cancel_install DEĞİL —
    bayrağı okuyacak görev yok; discard_pending manifestRaw İLE — plan .part'ları korunsun)."""
    o = _kos(_SENARYO, tmp_path)
    s = o["iptal_sonrasi"]
    assert s["ekran"] in ("s-ready", "s-select"), (
        f"Iptal ekrani 'Duraklatildi'da BIRAKTI — tek cikis pencereyi kapatmakti (bulgu [5.6]): {s}"
    )
    assert s["discard"] == 1 and s["cancel"] == 0, f"gorevsiz temizlik yolu kosulmadi: {s}"
    assert s["discardManifest"] == "manifest-v1", (
        "discard_pending manifestRaw'siz — plan .part korumasi devre disi kalir"
    )
    assert s["resumeVar"] is False and s["pausedOp"] is False, "iptal sonrasi durum sifirlanmadi"


@pytestmark_node
def test_KARSIT_5_6_kosan_gorev_varken_bayrak_yolu_AYNEN(tmp_path):
    """Koşan görev varken İptal davranışı DEĞİŞMEZ: cancel_install bayrağı (görev okur)."""
    o = _kos(_SENARYO, tmp_path)
    s = o["kosarken_iptal"]
    assert s["cancel"] == 1, f"kosan-gorev iptali bayrak yoluna gitmedi (asiri-duzeltme): {s}"
    assert s["discard"] == 1, f"kosarken iptal discard_pending'i TEKRAR cagirdi: {s}"
