# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
""" "BAŞLAT" KAPISI KAPALIYKEN ETİKET EZİLİYOR → VETERİNER SİLİK "BAŞLAT"A BASIYOR (bulgu 29, cid. 5).

1.9.30 "Başlat" kapısı düğmeyi `disabled` yapıp etiketi *"Güncelleme kontrol ediliyor…"* olarak
yazıyor. Ama `t-start`'ı yazan İKİ başka yol `dataset.kapi`'ye HİÇ bakmıyordu:

    startKapisiKapat()  →  {"disabled": true, "etiket": "Güncelleme kontrol ediliyor…"}
    applyLang()         →  {"disabled": true, "etiket": "Start"}          ← etiket EZİLDİ
    setRunningUi(...)   →  {"disabled": true, "etiket": "Başlat"}         ← yalnız pencere ODAĞIYLA

`applyLang` her TR/EN basışında, `setRunningUi` ise HER pencere odağında (`syncRunningState`)
çalışıyor. `.btn:disabled{opacity:.4}` olduğu için veteriner **silik bir "Başlat"** görüyor ve
beklemenin sebebi ekranın hiçbir yerinde yazmıyor → 1.9.30'un yazılma amacının yarısı geri geliyor.

⚠️ EK BULGU (analiz sırasında ölçüldü, raporda yoktu): `applyLang`in `t-start`'ı ezen satırı, iki
satır yukarıdaki 2026-08-06 düzeltmesini de eziyordu. O düzeltme (*"dil değişiminde 'çalışıyor'
durumu KAYBOLMASIN"*) `t-start` için fiilen ÖLÜYDÜ — yalnız `t-ready-lead`/`t-ready-title` için
çalışıyordu. Bu yama onu da aynı satırda düzeltiyor.

⚠️ KALICI KİLİT YARATILMADI: `disabled` alanına hiç dokunulmuyor; 25 sn'lik `KAPI_ZAMAN_ASIMI_MS`
zaman aşımı ve `show("s-ready")` → `startKapisiAc()` yolları aynen duruyor (6. test kilitliyor).
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

# ⚠️ TR/EN sözlükleri ve dört anahtar BİRBİRİNDEN FARKLI literaller taşımak ZORUNDA: `start` ile
# `startChecking` aynı stringe eşitlenirse assert'ler ayırt etmez ve test sessizce yeşile döner.
_SOZLUK = {
    "tr": {
        "start": "Başlat",
        "startChecking": "Güncelleme kontrol ediliyor…",
        "backToApp": "Uygulamaya dön",
        "repair": "Onar",
    },
    "en": {
        "start": "Start",
        "startChecking": "Checking for updates…",
        "backToApp": "Back to app",
        "repair": "Repair",
    },
}


def _fonksiyon(ham: str, imza: str) -> str:
    i = ham.index(imza)
    kapanis = chr(10) + "      }"
    j = ham.index(kapanis, i) + len(kapanis)
    return ham[i:j]


def _kos(senaryo: str, tmp_path: Path, lang: str = "tr") -> dict:
    """GERÇEK `applyLang` + `setRunningUi` + kapı fonksiyonlarını sahte DOM ile Node'da koştur."""
    ham = _UI.read_text(encoding="utf-8")
    applylang = _fonksiyon(ham, "function applyLang()")
    # ⚠️ ÇIKARIM TAMLIĞI: sentinel yarım keserse testler sessizce anlamsızlaşır.
    assert "renderCards()" in applylang, "applyLang cikarimi YARIM (sentinel kaydi)"

    kod = "\n".join(
        [
            "const KAPI_ZAMAN_ASIMI_MS = 25000; let startKapiTimer = null;",
            _fonksiyon(ham, "function startKapisiKapat()"),
            _fonksiyon(ham, "function startKapisiAc()"),
            _fonksiyon(ham, "function startKapisiKapaliMi()"),
            _fonksiyon(ham, "function startEtiketi(x)"),
            _fonksiyon(ham, "function setRunningUi(on)"),
            applylang,
        ]
    )

    js = f"""
const SOZLUK = {json.dumps(_SOZLUK, ensure_ascii=False)};
let LANG = {json.dumps(lang)};
let appRunning = false;
const t = () => SOZLUK[LANG];

// ⚠️ id BAŞINA AYRI nesne: tek nesne döndürülürse `dataset.kapi` ile `textContent` aynı nesnede
// yaşar, yama yine çalışır ama test gerçeği ÖLÇMEZ.
const _el = {{}};
function $(id) {{
  // ⚠️ Sahte öge GERÇEK DOM'un applyLang tarafından kullanılan yüzeyini taşımalı. `setAttribute`
  // eksikti ve applyLang erişilebilir adları (aria-label) güncellemeye başlayınca beş test birden
  // "el.setAttribute is not a function" ile düştü — davranış değil SAHTE DOM eksikti.
  if (!_el[id]) _el[id] = {{ textContent: "", hidden: false, disabled: false, dataset: {{}},
    type: "password", classList: {{ toggle() {{}} }}, title: "", value: "", focus() {{}},
    attrs: {{}}, setAttribute(k, v) {{ this.attrs[k] = v; }}, getAttribute(k) {{ return this.attrs[k]; }} }};
  return _el[id];
}}
const document = {{ documentElement: {{}} }};
function renderGuide() {{}}
function renderCards() {{}}
function renderChips() {{}}
function applyRememberLabel() {{}}
function setTimeout(fn, ms) {{ return 1; }}
function clearTimeout(id) {{}}

{kod}

const OUT = {{}};
function anlik(ad) {{
  OUT[ad] = {{ etiket: $("t-start").textContent, disabled: $("btn-start").disabled,
               repair: $("t-repair").textContent }};
}}
{senaryo}
console.log(JSON.stringify(OUT));
"""
    yol = tmp_path / "kapi_etiket.mjs"
    yol.write_text(js, encoding="utf-8")
    r = subprocess.run([_NODE, str(yol)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"node hatasi: {r.stderr[-800:]}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_ON_KOSUL_applyLang_GERCEKTEN_KOSTU(tmp_path):
    """Yanlış-yeşil kalkanı: `applyLang` yarıda kalırsa/hiç çağrılmazsa alttaki testler anlamsızdır."""
    o = _kos('startKapisiKapat(); applyLang(); anlik("a");', tmp_path)
    assert o["a"]["repair"] == "Onar", f"applyLang kosmadi: {o}"


def test_KRITIK_DIL_DEGISIMI_kapi_etiketini_EZMEZ(tmp_path):
    """TR/EN'e basmak bekleme sebebini silmemeli."""
    o = _kos('startKapisiKapat(); applyLang(); anlik("a");', tmp_path)
    assert o["a"]["disabled"] is True, "on-kosul: kapi kapali olmali"
    assert o["a"]["etiket"] == "Güncelleme kontrol ediliyor…", (
        f"dil degisimi kapi etiketini EZDI → veteriner SILIK 'Baslat' goruyor: {o['a']}"
    )


def test_KRITIK_PENCERE_ODAGI_kapi_etiketini_EZMEZ(tmp_path):
    """Her pencere odağı `syncRunningState` → `setRunningUi` çağırıyor; etiket korunmalı."""
    o = _kos('startKapisiKapat(); setRunningUi(false); anlik("a");', tmp_path)
    assert o["a"]["disabled"] is True
    assert o["a"]["etiket"] == "Güncelleme kontrol ediliyor…", f"pencere odagi kapi etiketini EZDI: {o['a']}"


def test_KRITIK_uygulama_ACIKKEN_odak_da_EZMEZ(tmp_path):
    """Uygulama çalışıyorken de kapı kapalıysa bekleme sebebi yazmalı."""
    o = _kos('startKapisiKapat(); setRunningUi(true); anlik("a");', tmp_path)
    assert o["a"]["etiket"] == "Güncelleme kontrol ediliyor…", f"'Uygulamaya don' EZDI: {o['a']}"


def test_KAPI_METNI_DILE_CEVRILIR(tmp_path):
    """⚠️ Bu test "etiketi bir değişkende sakla, sonra geri yaz" tipi yamayı REDDEDER.

    Öyle bir yamada metin kapının kapandığı andaki dilde DONAR; dil değişince çevrilmez."""
    o = _kos('startKapisiKapat(); applyLang(); anlik("a");', tmp_path, lang="en")
    assert o["a"]["etiket"] == "Checking for updates…", f"kapi metni EN'e cevrilmedi: {o['a']}"


def test_KARSIT_KANIT_kapi_ACIKKEN_normal_etiket_yazilir(tmp_path):
    """Karşıt-kanıt (REGRESYON BEKÇİSİ, bugün de yeşil): kapı açıkken normal davranış DEĞİŞMEMELİ.

    "Her zaman startChecking yaz" gibi aşırı geniş bir yamayı yakalar."""
    o = _kos('applyLang(); anlik("a"); setRunningUi(true); anlik("b");', tmp_path)
    assert o["a"]["etiket"] == "Başlat", f"kapi acikken etiket bozuldu: {o['a']}"
    assert o["b"]["etiket"] == "Uygulamaya dön", f"'calisiyor' durumu kayboldu: {o['b']}"


def test_KAPI_ACILINCA_etiket_GERI_GELIR(tmp_path):
    """⚠️ KALICI KİLİT YOK: kapı açılınca etiket ve `disabled` normale dönmeli."""
    o = _kos('startKapisiKapat(); applyLang(); startKapisiAc(); anlik("a");', tmp_path)
    assert o["a"]["etiket"] == "Başlat", f"kapi acildi ama etiket takildi: {o['a']}"
    assert o["a"]["disabled"] is False, f"dugme kilitli kaldi: {o['a']}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([str(Path(__file__).resolve()), "-v"]))
