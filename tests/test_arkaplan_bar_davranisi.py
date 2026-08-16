# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Arka plan indirme barının DAVRANIŞI — yüzde matematiği ve yoklama yaşam döngüsü.

`test_arkaplan_indirme_gostergesi.py` sözleşmeyi (kanal ayrımı, komut kaydı, ekran ele
geçirmeme) kaynak üzerinden kilitler. Ama "yüzde DOĞRU mu hesaplanıyor", "belirsiz bar
gerçekten belirsiz mi", "yoklama sızıyor mu" soruları ancak KODU ÇALIŞTIRARAK yanıtlanır.

Bu dosya `index.html` içindeki script'i çıkarır, minimal bir DOM + sahte `invoke` ile Node'da
koşturur ve fonksiyonları gerçek girdilerle çağırır. (Launcher UI'si Tauri'ye bağlı olduğu
için tam sayfa yüklenemez; yalnız ilgili fonksiyonlar izole edilip çalıştırılır.)
"""

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"
_NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(_NODE is None, reason="node yok — UI davranış testi atlanır")


def _kos(senaryo: str, tmp_path: Path) -> dict:
    """Fonksiyonları izole edip Node'da çalıştır, JSON sonuç döndür."""
    ham = _UI.read_text(encoding="utf-8")
    # Yalnız ihtiyacımız olan parçaları al (tüm script Tauri'ye bağlı, yüklenemez).
    # ⚠️ Fonksiyonlar MODÜL SEVİYESİ duruma kapanır (prefetchTimer/prefetchSeen/prefetchDl);
    # o bildirim satırı alınmazsa `ReferenceError` olur — ilk denemede tam bu oldu.
    durum = next(s for s in ham.splitlines() if "let prefetchTimer" in s)
    parcalar = [durum.strip()]
    for ad in ("function stopPrefetchPoll", "function renderPrefetch", "function startPrefetchPoll"):
        i = ham.index(ad)
        # Fonksiyon sonunu bul: aynı girintideki kapanış süslü parantezi
        j = ham.index("\n      }", i) + len("\n      }")
        parcalar.append(ham[i:j])
    kod = "\n".join(parcalar)

    surucu = (
        textwrap.dedent("""
        // ── minimal DOM ────────────────────────────────────────────────────────────
        class El {
          constructor(tag){ this.tag=tag; this.className=""; this.children=[]; this.style={};
            this._text=""; this.classList={ _s:new Set(),
              add:(c)=>this.classList._s.add(c), remove:(c)=>this.classList._s.delete(c),
              toggle:(c,v)=>{ v?this.classList._s.add(c):this.classList._s.delete(c); },
              contains:(c)=>this.classList._s.has(c) }; }
          set textContent(v){ this._text=v; if(v==="") this.children=[]; }
          get textContent(){ return this._text; }
          appendChild(c){ this.children.push(c); return c; }
          querySelector(sel){
            const ara=(n)=>{ for(const c of n.children){
                if(sel.startsWith(".") && c.className.split(" ").includes(sel.slice(1))) return c;
                if(!sel.startsWith(".") && c.tag===sel) return c;
                const d=ara(c); if(d) return d; } return null; };
            return ara(this); }
        }
        const NOTICE = new El("div");
        global.document = { createElement:(t)=>new El(t) };
        global.$ = (id) => (id === "notice" ? NOTICE : new El("div"));
        global.performance = { now: () => Date.now() };
        global.t = () => ({ verifying:"dogrulaniyor", cached:"onbellekte",
                            reconnecting:"yeniden baglaniyor", rtBgPrep:"Haziralaniyor" });
        global.pkgLabel = (w) => "PKT:" + w;
        global.fmtBytes = (n) => (n/1048576).toFixed(0) + " MB";
        global.fmtSpeed = (b) => (b/1048576).toFixed(1) + " MB/s";
        __KOD__

        function anlik(){
          const bar = NOTICE.querySelector(".bgbar");
          return { pct: NOTICE.querySelector(".bgpct") ? NOTICE.querySelector(".bgpct").textContent : null,
                   genislik: bar ? bar.querySelector("i").style.width : null,
                   belirsiz: bar ? bar.classList.contains("indet") : null,
                   alt: NOTICE.querySelector(".bgsub") ? NOTICE.querySelector(".bgsub").textContent : null };
        }
        __SENARYO__
    """)
        .replace("__KOD__", kod)
        .replace("__SENARYO__", senaryo)
    )

    f = tmp_path / "senaryo.mjs"
    f.write_text(surucu, encoding="utf-8")
    r = subprocess.run([_NODE, str(f)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, f"node hatası:\n{r.stdout}\n{r.stderr}"
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_KRITIK_yuzde_dogru_hesaplanir(tmp_path):
    """Sahip isteğinin özü. 26,6 MB / 71,2 MB ≈ %37."""
    s = _kos(
        """
        renderPrefetch({ step:"downloading", what:"app", done: 26600000, total: 71183520 });
        console.log(JSON.stringify(anlik()));
    """,
        tmp_path,
    )
    assert s["pct"] == "%37", f"yüzde yanlış: {s['pct']}"
    assert s["genislik"].startswith("37."), f"bar genişliği yüzdeyle uyuşmuyor: {s['genislik']}"
    assert s["belirsiz"] is False
    assert "PKT:app" in s["alt"] and "MB" in s["alt"]


def test_yuzde_sinirlar(tmp_path):
    s = _kos(
        """
        const out = [];
        renderPrefetch({ step:"downloading", what:"a", done:0, total:100 }); out.push(anlik().pct);
        renderPrefetch({ step:"downloading", what:"b", done:100, total:100 }); out.push(anlik().pct);
        renderPrefetch({ step:"downloading", what:"c", done:50, total:100 }); out.push(anlik().pct);
        console.log(JSON.stringify({ out }));
    """,
        tmp_path,
    )
    assert s["out"] == ["%0", "%100", "%50"]


def test_KRITIK_content_length_yoksa_SAHTE_yuzde_gosterilmez(tmp_path):
    """`total=0` iken "%0" yazmak kullanıcıya "hiç ilerlemiyor" izlenimi verir — belirsiz bar doğru."""
    s = _kos(
        """
        renderPrefetch({ step:"downloading", what:"deps", done: 5000000, total: 0 });
        console.log(JSON.stringify(anlik()));
    """,
        tmp_path,
    )
    assert s["pct"] == "", f"boyut bilinmezken yüzde yazılmış: {s['pct']}"
    assert s["belirsiz"] is True, "belirsiz bar açılmamış"
    assert "MB" in s["alt"], "en azından inen miktar gösterilmeli"


def test_indirme_disi_fazlar_belirsiz_bar(tmp_path):
    s = _kos(
        """
        const out = {};
        renderPrefetch({ step:"verifying", what:"app" });   out.verify = anlik();
        renderPrefetch({ step:"cached", what:"vet" });      out.cached = anlik();
        renderPrefetch({ step:"manifest_fetched" });        out.manifest = anlik();
        console.log(JSON.stringify(out));
    """,
        tmp_path,
    )
    for faz in ("verify", "cached", "manifest"):
        assert s[faz]["belirsiz"] is True, f"{faz}: belirsiz bar bekleniyordu"
        assert s[faz]["pct"] == "", f"{faz}: anlamsız yüzde gösteriliyor"
    assert "dogrulaniyor" in s["verify"]["alt"]


def test_KRITIK_paket_degisince_hiz_olcumu_SIFIRLANIR(tmp_path):
    """🔴 Yeni pakete geçince önceki paketin bayt sayacı taşınırsa NEGATİF/saçma hız çıkar.

    ⚠️ Bu test önce YÜZDEYİ ölçüyordu ve mutasyon turunda ZAYIF çıktı: yüzde `p.done/p.total`
    ile hesaplanır, `prefetchDl`e HİÇ bağlı değildir → sıfırlamayı kaldırmak yüzdeyi
    değiştirmiyordu. Sıfırlamanın gerçek etkisi HIZ'dadır: app'te 70 MB'a gelmişken deps'in
    1 MB'ıyla devam edilirse fark negatif olur ve alt satırda anlamsız bir hız belirir.
    """
    s = _kos(
        """
        // app: 350 ms'ten uzun iki ölçüm → hız EMA'sı oluşur
        renderPrefetch({ step:"downloading", what:"app", done: 10000000, total: 71183520 });
        const bekle = Date.now() + 400; while (Date.now() < bekle) {}
        renderPrefetch({ step:"downloading", what:"app", done: 70000000, total: 71183520 });
        const alt_app = anlik().alt;
        // deps'e geç: bayt sayacı SIFIRLANMAZSA (1M - 70M) negatif hız üretir
        renderPrefetch({ step:"downloading", what:"deps", done: 1000000, total: 1462119667 });
        const bekle2 = Date.now() + 400; while (Date.now() < bekle2) {}
        renderPrefetch({ step:"downloading", what:"deps", done: 3000000, total: 1462119667 });
        console.log(JSON.stringify({ alt_app, alt_deps: anlik().alt }));
    """,
        tmp_path,
    )
    assert "PKT:deps" in s["alt_deps"]
    # ⚠️ "-" aramak İŞE YARAMAZ: `fmtSpeed` negatifi `Math.max(0, …)` ile kırpar, eksi işareti
    # hiç görünmez (mutasyon turu bunu gösterdi). Sıfırlama yoksa fark (1 MB − 70 MB) negatif
    # olur → hız ya hiç yazılmaz (`speed > 0` tutmaz) ya da "0 KB/s" görünür. Gözlemlenebilir
    # belirti budur; onu doğruluyoruz.
    import re as _re

    m = _re.search(r"([\d.]+)\s*(MB/s|KB/s)", s["alt_deps"])
    assert m, f"yeni pakette HIZ hiç gösterilmiyor — sayaç sıfırlanmadığı için fark negatif: {s['alt_deps']!r}"
    assert float(m.group(1)) > 0, f"hız sıfıra kırpılmış (sayaç eski paketten taşınmış): {s['alt_deps']!r}"


def test_KRITIK_ilk_null_yoklamayi_durdurmaz_ilerleme_sonrasi_null_durdurur(tmp_path):
    """🔴 İlk `null`da durursak bar HİÇ görünmez; ilerleme sonrası `null`da durmazsak sızar."""
    s = _kos(
        """
        let cagri = 0, durdu = false;
        const sira = [null, null, {step:"downloading",what:"app",done:10,total:100}, null];
        global.invoke = async () => sira[Math.min(cagri++, sira.length-1)];
        global.notice = () => {};
        let timer = null;
        global.setInterval = (fn, ms) => { timer = fn; return 1; };
        global.clearInterval = () => { durdu = true; };
        startPrefetchPoll();
        (async () => {
          await timer(); const ilkNullSonrasi = durdu;   // null -> DURMAMALI
          await timer();
          await timer();                                  // ilerleme geldi
          const ilerlemeSonrasi = durdu;
          await timer();                                  // ilerleme sonrasi null -> DURMALI
          console.log(JSON.stringify({ ilkNullSonrasi, ilerlemeSonrasi, sonunda: durdu }));
        })();
    """,
        tmp_path,
    )
    assert s["ilkNullSonrasi"] is False, "ilk null'da durdu → bar hiç görünmez"
    assert s["ilerlemeSonrasi"] is False, "ilerleme akarken durdu"
    assert s["sonunda"] is True, "indirme bitince yoklama DURMADI → zamanlayıcı sızar"
