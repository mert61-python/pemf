# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DURAKLATILMIŞ GÜNCELLEMEDE "DEVAM ET" EKRANI GERİ GETİRMİYOR + HER BASIŞ YENİ İNDİRME (bulgu 31).

`tryRuntimeUpdate` `plan.cached === false` dalında `show()` çağırmadan `false` dönüyordu.
"Devam Et" düğmesi de bu fonksiyona bağlı (`resumeOp = tryRuntimeUpdate`). Ölçülen sonuç:

    ekran: "s-install" / "Duraklatıldı"da KALIYOR      (Başlat/Onar/Kaldır hepsi gizli s-ready'de)
    prefetch_cagrisi: 1 → 2 → 3                        (her basış YENİ ≤1,4 GB indirme)

Başlat/Onar/Kaldır düğmelerinin hepsi gizli `s-ready` ekranının içinde olduğu için cihaz ancak
kapat-aç ile kurtarılıyor. `recheckUpdates`teki `sonBildirim` guard'ı bu dalda YOKTU.

⚠️ ULAŞILABİLİRLİK DAR: `plan.cached` duraklamayı atlatır, dolayısıyla kurulabilen tek gerçek yol
duraklatılmış ekran açıkken **6 saatlik periyodik turun** `manifestRaw`'ı yeni bir sürümle
değiştirmesidir. Aşağıdaki senaryo tam olarak bunu kuruyor.

⚠️ EKRAN GERİ ALMA KOŞULLU (`curScreen() === "s-install"`): koşulsuz `show("s-ready")` çağırmak
`startKapisiAc()` yan etkisiyle "Başlat" kapısını ERKEN açar ve 1.9.30'un düzelttiği belirtiyi geri
getirir — ölçüldü. 4. test bu yönü kilitler.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"
_NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(_NODE is None, reason="node yok")


def _fonksiyon(ham: str, imza: str) -> str:
    i = ham.index(imza)
    kapanis = chr(10) + "      }"
    j = ham.index(kapanis, i) + len(kapanis)
    return ham[i:j]


def _satir(ham: str, parca: str) -> str:
    return next(s for s in ham.splitlines() if parca in s)


def _kos(senaryo: str, tmp_path: Path) -> dict:
    ham = _UI.read_text(encoding="utf-8")

    try_rt = _fonksiyon(ham, "async function tryRuntimeUpdate()")
    recheck = _fonksiyon(ham, "async function recheckUpdates()")
    # ⚠️ ÇIKARIM TAMLIĞI: sentinel yarım keserse testler sessizce anlamsızlaşır.
    assert "apply_runtime_update" in try_rt and "prefetch_runtime_update" in try_rt, "tryRuntimeUpdate cikarimi YARIM"
    assert "sonBildirim" in recheck, "recheckUpdates cikarimi YARIM"

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
            _fonksiyon(ham, "function setInstallControls(mode)"),
            _fonksiyon(ham, "function showPaused()"),
            "let guncellemeTimer = null, sonBildirim = \"\";",
            recheck,
            try_rt,
        ]
    )

    js = f"""
let busy = false, baseInstalled = true, manifestRaw = "manifest-v1", authed = true, appRunning = false;
let resumeOp = null;
let PLAN = {{ needed: true, cached: true }};
let RAW = "manifest-v1";
let prefetch = 0;
let sonCheck = null;
const notlar = [];

const t = () => ({{ rtTitle: "T", rtLead: "L", rtBg: "arka-plan", rtBgDone: "bitti", rtBgFail: "hata",
  rtRecall: "geri-cagirma", rtReady: "hazir", rtDone: "tamam", rtRollback: "geri-alindi",
  rtRollbackFail: "geri-alma-hatasi", pausedTitle: "Duraklatildi", pausedLead: "duraklatildi-alt",
  start: "Baslat", startChecking: "kontrol-ediliyor", backToApp: "Uygulamaya-don", sessionBusy: "seans" }});

const _el = {{}};
function $(id) {{
  if (!_el[id]) _el[id] = {{ textContent: "", hidden: false, disabled: false, dataset: {{}} }};
  return _el[id];
}}
// ⚠️ Zamanlayıcılar taklit: aksi hâlde `startKapisiKapat`ın 25 sn'lik GERÇEK
// `setTimeout(startKapisiAc, KAPI_ZAMAN_ASIMI_MS)` çağrısı Node'u ayakta tutuyor ve tek senaryo
// 25 sn sürüyordu (ölçüldü). Kapının zaman aşımı DAVRANIŞI bu dosyanın konusu değil —
// tests/test_baslat_kapisi.py onu ayrıca kilitliyor.
function setTimeout(fn, ms) {{ return 1; }}
function clearTimeout(id) {{}}
function startPolling() {{}}
function stopPolling() {{}}
function startPrefetchPoll() {{}}
function stopPrefetchPoll() {{}}
function resetInstallUI() {{}}
function renderChips() {{}}
function clearErr() {{}}
function clearNotice() {{}}
function notice(m) {{ notlar.push(String(m)); }}
function fail(m) {{ notlar.push("FAIL:" + String(m)); }}
async function refreshEnv() {{ return {{}}; }}

// ⚠️ `prefetch_runtime_update` ASLA ÇÖZÜLMEYEN bir promise döndürür. Anında çözülen bir mock
// `.then` içindeki `sonBildirim = ""` satırını hemen çalıştırır, guard devre dışı kalır ve YAMALI
// kod bile 2,3,4 ölçer → test YANLIŞ-KIRMIZI olurdu (ölçüldü). Gerçek dünyada ≤1,4 GB indirme
// dakikalar sürer, yani asla-çözülmeyen mock gerçeğe DAHA yakındır.
async function invoke(ad, args) {{
  if (ad === "check_runtime_update") {{ sonCheck = args && args.manifestRaw; return PLAN; }}
  if (ad === "apply_runtime_update") return {{ status: "paused" }};
  if (ad === "fetch_profiles") return {{ raw: RAW }};
  if (ad === "prefetch_runtime_update") {{ prefetch += 1; return new Promise(() => {{}}); }}
  return null;
}}

{kod}

const OUT = {{}};
function anlik(ad, ek) {{
  OUT[ad] = Object.assign({{
    ekran: curScreen(),
    prefetch,
    baslik: $("inst-title").textContent,
    dugmeKilitli: $("btn-start").disabled,
    etiket: $("t-start").textContent,
    sonCheck,
    resumeAdi: resumeOp && resumeOp.name,
  }}, ek || {{}});
}}
(async () => {{
{senaryo}
  console.log(JSON.stringify(OUT));
}})();
"""
    yol = tmp_path / "devam_et.mjs"
    yol.write_text(js, encoding="utf-8")
    r = subprocess.run([_NODE, str(yol)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"node hatasi: {r.stderr[-900:]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


# Duraklatılmış kurulum + periyodik turun manifesti değiştirmesi + üç kez "Devam Et".
_SENARYO_DEVAM = """
  for (const s of SCREENS) $(s).hidden = (s !== "s-ready");
  PLAN = { needed: true, cached: true };
  await tryRuntimeUpdate();            // apply -> paused  => ekran s-install
  busy = false;                        // finally zaten sifirliyor; acik yazildi
  anlik("paused");
  PLAN = { needed: true, cached: false }; RAW = "manifest-v2";
  await recheckUpdates();              // 6 saatlik tur: manifestRaw degisti, arka plan indirme basladi
  anlik("tur");
  await resumeOp(); anlik("devam1");
  await resumeOp(); anlik("devam2");
  await resumeOp(); anlik("devam3");
"""


def test_ON_KOSUL_duraklatilmis_ekran_ve_resumeOp(tmp_path):
    """Yanlış-kırmızı kalkanı: senaryo GERÇEKTEN duraklatılmış duruma ulaşmış olmalı.

    `busy` sızmış olsaydı `tryRuntimeUpdate` ilk satırda `false` döner, ekran s-install'da kalır ve
    2. test yamadan SONRA da kırmızı görünürdü. `sonCheck == "manifest-v2"` fonksiyon gövdesine
    GERÇEKTEN girildiğinin kanıtı."""
    o = _kos(_SENARYO_DEVAM, tmp_path)
    assert o["paused"]["ekran"] == "s-install", f"duraklatilmis ekrana ulasilmadi: {o['paused']}"
    assert o["paused"]["baslik"] == "Duraklatildi"
    assert o["paused"]["resumeAdi"] == "tryRuntimeUpdate", f"resumeOp baglanmadi: {o['paused']}"
    assert o["tur"]["sonCheck"] == "manifest-v2", f"periyodik tur manifesti degistirmedi: {o['tur']}"


def test_KRITIK_DEVAM_ET_ekrani_GERI_GETIRIR(tmp_path):
    """ "Devam Et" ekranı `s-ready`ye döndürmeli; yoksa Başlat/Onar/Kaldır erişilemez kalır."""
    o = _kos(_SENARYO_DEVAM, tmp_path)
    assert o["devam1"]["ekran"] == "s-ready", (
        f"'Devam Et' ekrani 'Duraklatildi'da BIRAKTI → Baslat/Onar/Kaldir erisilemez, cihaz ancak "
        f"kapat-ac ile kurtulur: {o['devam1']}"
    )


def test_KRITIK_her_BASIS_yeni_indirme_baslatmaz(tmp_path):
    """Üç basış TEK indirme başlatmalı (periyodik turun başlattığı indirme).

    Aksi hâlde her basış ≤1,4 GB'lık yeni bir ön-indirme açıyordu (ölçüldü: 1 → 2 → 3 → 4)."""
    o = _kos(_SENARYO_DEVAM, tmp_path)
    assert o["devam3"]["prefetch"] == 1, (
        f"'Devam Et' her basista YENI indirme baslatti (toplam {o['devam3']['prefetch']} cagri)"
    )


def test_KARSIT_KANIT_ACILIS_yolunda_ekran_ELE_GECIRILMEZ_kapi_KAPALI_kalir(tmp_path):
    """⚠️ REGRESYON BEKÇİSİ (bugün de yeşil): açılış yolunda ekran GERİ ALINMAMALI.

    Ekran `s-ready` iken koşulsuz `show("s-ready")` çağırmak `startKapisiAc()` yan etkisiyle
    "Başlat" kapısını erken açar → 1.9.30'un düzelttiği belirti geri gelir (ölçüldü:
    `dugmeKilitli` False). Bu test o aşırı-geniş yamayı reddeder."""
    o = _kos(
        """
  for (const s of SCREENS) $(s).hidden = (s !== "s-ready");
  startKapisiKapat();
  PLAN = { needed: true, cached: false };
  const donus = await tryRuntimeUpdate();
  anlik("acilis", { donus });
""",
        tmp_path,
    )
    a = o["acilis"]
    assert a["donus"] is False, f"acilis yolunda ekran ELE GECIRILDI: {a}"
    assert a["ekran"] == "s-ready"
    assert a["dugmeKilitli"] is True, f"'Baslat' kapisi ERKEN acildi (1.9.30 belirtisi geri geldi): {a}"
    assert a["etiket"] == "kontrol-ediliyor", f"kapi etiketi ezildi: {a}"
    assert a["prefetch"] == 1, f"arka plan indirme baslatilmadi: {a}"


def test_KARSIT_KANIT_paketler_HAZIRSA_devam_normal_calisir(tmp_path):
    """Karşıt-kanıt: paketler cache'deyse "Devam Et" normal kurulum yoluna girmeli.

    "Her durumda s-ready'e kaç" gibi aşırı geniş bir yamayı reddeder."""
    o = _kos(
        """
  for (const s of SCREENS) $(s).hidden = (s !== "s-ready");
  PLAN = { needed: true, cached: true };
  await tryRuntimeUpdate();
  anlik("paused");
  await resumeOp();
  anlik("devam1");
""",
        tmp_path,
    )
    assert o["devam1"]["ekran"] == "s-install", f"hazir paketle kurulum yoluna girilmedi: {o['devam1']}"
    assert o["devam1"]["baslik"] == "Duraklatildi", f"duraklatma akisi bozuldu: {o['devam1']}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([str(Path(__file__).resolve()), "-v"]))
