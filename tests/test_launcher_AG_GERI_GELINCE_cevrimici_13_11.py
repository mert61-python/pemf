# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""CLIENT (launcher) AĞ GERİ GELİNCE ÇEVRİMİÇİNE DÖNER — sahip 13 Kasım 2026: "Client'te internet bağlantısı yokken açıldı, çevrimdışı;
ardından makineyi internete bağlayınca çevrimiçine dönmedi, reconnect algoritması eksik / bozuk".

ÖLÇÜLEN (önce): `bootNetwork` çevrimdışıda `setOffline(true)` + 6 SAATLİK güncelleme turu; tur başarılı olsa da rozeti kapatmıyor, oturumu
tazelemiyordu; `online` olayı dinlenmiyordu → client yeniden açılana dek "Çevrimdışı".
Bu dosya `index.html`in GERÇEK `setOffline` + `agDenemeyiPlanla` + `agiYenidenDene` kodunu sahte DOM / sahte zamanlayıcı / senaryolu `invoke`
ile Node'da KOŞTURUR (metin aramaz)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import capraz
import pytest

_KOK = Path(__file__).resolve().parent.parent
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"
_NODE = shutil.which("node")
_node_gerekir = pytest.mark.skipif((_NODE is None) and not capraz.ZORUNLU, reason="node yok")


def _blok() -> str:
    ham = _UI.read_text(encoding="utf-8")
    bas = ham.index("      function setOffline(on) {")
    son = ham.index('window.addEventListener("online", () => agDenemeyiPlanla(true));', bas)
    return ham[bas:son] + 'window.addEventListener("online", () => agDenemeyiPlanla(true));'


def _kos(tmp_path: Path, senaryo: dict) -> dict:
    js = f"""
const SEN = {json.dumps(senaryo)};
let simdi = 0; const kuyruk = []; let kimlik = 0;
function setTimeout(fn, ms) {{ const id = ++kimlik; kuyruk.push({{ id, t: simdi + ms, fn }}); return id; }}
function clearTimeout(id) {{ const i = kuyruk.findIndex((k) => k.id === id); if (i >= 0) kuyruk.splice(i, 1); }}
async function ilerle(ms) {{
  const hedef = simdi + ms;
  for (;;) {{
    kuyruk.sort((a, b) => a.t - b.t);
    if (!kuyruk.length || kuyruk[0].t > hedef) break;
    const k = kuyruk.shift(); simdi = k.t; k.fn();
    for (let i = 0; i < 20; i++) await Promise.resolve();
  }}
  simdi = hedef;
}}
const olaylar = {{}};
const window = {{ addEventListener: (ad, fn) => {{ olaylar[ad] = fn; }} }};
const _el = {{}};
function $(id) {{ if (!_el[id]) _el[id] = {{ hidden: true }}; return _el[id]; }}
let busy = !!SEN.busy, authed = false, envCache = {{}}, ekran = SEN.ekran || "s-ready", netOffline = false;
const kayit = {{ fetch: [], auth: 0, boot: 0, temizle: 0 }};
let cevrimdisiKalan = SEN.cevrimdisi_deneme;
async function invoke(ad) {{
  if (ad === "fetch_profiles") {{
    kayit.fetch.push(simdi);
    if (cevrimdisiKalan > 0) {{ cevrimdisiKalan--; throw new Error("ag yok"); }}
    return {{ raw: "{{}}" }};
  }}
  throw new Error("beklenmeyen " + ad);
}}
async function refreshAuth() {{ kayit.auth++; authed = !!SEN.oturum_acik; return {{ logged_in: authed, offline: false }}; }}
function curScreen() {{ return ekran; }}
function clearNotice() {{ kayit.temizle++; }}
async function bootNetwork(env) {{ kayit.boot++; }}
{_blok()}
(async () => {{
  setOffline(true);
  $("btn-offline-start").hidden = false;
  if (SEN.online_olayi_ms != null) {{ await ilerle(SEN.online_olayi_ms); olaylar.online(); }}
  if (SEN.busy_bitir_ms != null) {{ await ilerle(SEN.busy_bitir_ms); busy = false; }}
  await ilerle(SEN.sure_ms);
  console.log(JSON.stringify({{ ...kayit, rozet_gizli: $("offline-badge").hidden, offline: netOffline, cevrimdisi_baslat_gizli: $("btn-offline-start").hidden, kuyruk: kuyruk.length }}));
}})();
"""
    f = tmp_path / "k.mjs"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([_NODE, str(f)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


@_node_gerekir
def test_KRITIK_ag_GERI_GELINCE_rozet_KAPANIR_oturum_TAZELENIR_ag_adimi_KOSAR(tmp_path):
    # 2 deneme başarısız (5 sn, +10 sn), 3.'de ulaşılır (+20 sn) → toplam 35 sn
    k = _kos(tmp_path, {"cevrimdisi_deneme": 2, "sure_ms": 40000, "oturum_acik": True})
    assert k["fetch"] == [5000, 15000, 35000], k["fetch"]  # artan aralık: 5 → 10 → 20 sn
    assert k["rozet_gizli"] is True and k["offline"] is False and k["auth"] == 1 and k["boot"] == 1, k
    assert k["cevrimdisi_baslat_gizli"] is True and k["kuyruk"] == 0, "çevrimiçine dönünce deneme zinciri DURMALI"


@_node_gerekir
def test_KRITIK_online_olayi_BEKLEMEDEN_dener(tmp_path):
    k = _kos(tmp_path, {"cevrimdisi_deneme": 0, "online_olayi_ms": 1000, "sure_ms": 0, "oturum_acik": True})
    assert k["fetch"] == [1000] and k["rozet_gizli"] is True and k["boot"] == 1, k


@_node_gerekir
def test_KRITIK_giris_EKRANINDA_uyari_kalkar_ag_adimi_KOSMAZ(tmp_path):
    k = _kos(tmp_path, {"cevrimdisi_deneme": 0, "sure_ms": 6000, "oturum_acik": False, "ekran": "s-login"})
    assert k["rozet_gizli"] is True and k["temizle"] == 1 and k["boot"] == 0 and k["cevrimdisi_baslat_gizli"] is True, k


@_node_gerekir
def test_KARSIT_kurulum_SURERKEN_araya_GIRMEZ_sonra_dener(tmp_path):
    k = _kos(
        tmp_path, {"cevrimdisi_deneme": 0, "busy": True, "busy_bitir_ms": 12000, "sure_ms": 30000, "oturum_acik": True}
    )
    assert all(t >= 12000 for t in k["fetch"]) and k["fetch"], k["fetch"]
    assert k["rozet_gizli"] is True and k["boot"] == 1, k


@_node_gerekir
def test_KARSIT_ag_HIC_gelmezse_deneme_SURER_aralik_60_snde_TAVAN(tmp_path):
    k = _kos(tmp_path, {"cevrimdisi_deneme": 99, "sure_ms": 300000, "oturum_acik": True})
    araliklar = [b - a for a, b in zip([0] + k["fetch"], k["fetch"])]
    assert araliklar[:5] == [5000, 10000, 20000, 30000, 60000] and set(araliklar[5:]) <= {60000}, araliklar
    assert k["rozet_gizli"] is False and k["offline"] is True and k["kuyruk"] == 1


def test_YAPISAL_blok_index_htmlde_ve_setOffline_ZINCIRI_baslatir():
    b = _blok()
    assert re.search(r"function setOffline\(on\) \{[^}]*agDenemeyiPlanla\(false\)", b), (
        "setOffline deneme zincirini başlatmıyor"
    )
