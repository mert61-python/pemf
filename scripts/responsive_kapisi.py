# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""RESPONSIVE KAPISI — görünüm-alanı taşması + dokunma hedefi + kritik eleman görünürlüğü (2026-09-04 denetimi)

Ölçülen (Edge/Chrome headless + CDP `Emulation.setDeviceMetricsOverride`; `--window-size`
TEK BAŞINA düzen görünüm alanını DEĞİŞTİRMİYOR — innerWidth 504×473 sabit kalıyor, ölçüldü):
  1. tasma    : document.scrollingElement.scrollWidth <= innerWidth (+1 px tolerans)
  2. dokunma  : etkileşimli elemanların (button, a[href], role=button/link/tab…) kısa kenarı
                dokunmatik görünümde ≥ 44 px, masaüstünde ≥ 24 px (WCAG 2.5.8)
  3. kritik   : ACİL DURDUR / Kur ve Başlat / Giriş yap gibi elemanlar VAR + GÖRÜNÜR +
                kaydırınca görünüm alanına giriyor + üstü örtülmemiş (elementFromPoint)
  4. ust-kesik: (yalnız launcher) main.scrollTop=0 iken ilk içerik header'ın altında mı
                (launcher-1: ortalanmış taşma kaydırmayla ulaşılamıyor)
  5. png      : her hedef×durum×görünüm alanı için ekran görüntüsü (CI artefaktı)

Bağımlılık: YALNIZ stdlib (gömülü python + CI setup-python'da pip yok). WebSocket istemcisi
~60 satır (RFC 6455 metin çerçevesi; CDP başka bir şey kullanmaz).

Kullanım:
    python scripts/responsive_kapisi.py --hedef launcher
    python scripts/responsive_kapisi.py --hedef pf --pf-dist pf/dist
    python scripts/responsive_kapisi.py --hedef site --site-dist pemf-vet-web/dist
    python scripts/responsive_kapisi.py --hedef launcher --mutasyon "#btn-install{display:none}"  # → 1 bekle
Çıkış: 0 temiz (yalnız baseline'daki bilinenler) · 1 YENİ bulgu · 2 kullanım/altyapı hatası
       · 3 ortam yok (tarayıcı ya da derleme çıktısı yok; --zorunlu ile 2'ye döner — CI'da ŞART)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_KOK = Path(
    os.environ.get("PEMF_KOK") or Path(__file__).resolve().parent.parent
)  # PEMF_KOK: test/mutasyon harness'ı için
BASELINE = _KOK / "tests" / "responsive_kapisi_baseline.json"

# ── görünüm alanları (denetim raporu §2 + cihaz sınıfları a-j) ───────────────────────────
#   (w, h, mobil-emülasyon)  — mobil: dokunma olayları + 44 px eşiği
GORUNUMLER = {
    "pf": [
        (320, 568, True),
        (360, 800, True),
        (640, 360, True),
        (700, 540, False),
        (768, 1024, True),
        (911, 512, False),
        (1280, 720, False),
        (1920, 1080, False),
    ],
    # launcher 320-640'ta ÜRETİM DIŞI (ampirik-9) — min pencere 700×540; 911×512 = 1366@%150,
    # 1024×576 = 1280@%125 (launcher-2 DPI sınıfı)
    "launcher": [
        (700, 540, False),
        (880, 600, False),
        (911, 512, False),
        (1024, 576, False),
        (1280, 720, False),
        (1920, 1080, False),
    ],
    "site": [
        (320, 568, True),
        (360, 800, True),
        (390, 844, True),
        (640, 360, True),
        (768, 1024, True),
        (911, 512, False),
        (1280, 720, False),
        (1920, 1080, False),
    ],
}
DOKUNMA_MIN_MOBIL = 44
DOKUNMA_MIN_MASAUSTU = 24


def kova(w: int) -> str:
    """Baseline anahtarı görünüm alanı SINIFI ile kurulur (piksel değil) — 8 görünümde 8 ayrı satır yerine 3."""
    return "dar" if w <= 430 else ("orta" if w <= 1024 else "genis")


# ── hedef tanımları: durumlar + kritik elemanlar ─────────────────────────────────────────
# kritik: {"ad", "css" | "metin"(regex, role=button/a/button içinde)} — hepsi görünür+erişilebilir olmalı
HEDEFLER = {
    "pf": {
        "giris": {
            "hazirla": None,
            "kritik": [
                {"ad": "Giriş Yap (gönder)", "metin": r"^Giriş Yap$", "son": True},
                {"ad": "Kayıt Ol sekmesi", "metin": r"^Kayıt Ol$"},
                {"ad": "Şifremi unuttum", "metin": r"^Şifremi unuttum"},
            ],
        },
        "kayit": {
            "hazirla": "tikla:metin:^Kayıt Ol$",
            "kritik": [{"ad": "Kayıt Ol (gönder)", "metin": r"^(Kayıt Ol|Hesap Oluştur)$", "son": True}],
        },
    },
    "launcher": {
        "login": {
            "kritik": [
                {"ad": "Giriş yap", "css": "#btn-login"},
                {"ad": "Şifremi unuttum", "css": "#btn-forgot"},
                {"ad": "Hesap oluştur", "css": "#btn-signup"},
                {"ad": "Çevrimdışı başlat", "css": "#btn-offline-start"},
            ]
        },
        "select": {
            "kritik": [
                {"ad": "Kur ve Başlat", "css": "#btn-install"},
                {"ad": "Geri dön", "css": "#btn-sel-cancel"},
                {"ad": "ilk profil kartı", "css": "#cards .card"},
            ]
        },
        "install": {"kritik": [{"ad": "Duraklat", "css": "#btn-pause"}, {"ad": "İptal", "css": "#btn-cancel"}]},
        "ready": {
            "kritik": [
                {"ad": "Başlat", "css": "#btn-start"},
                {"ad": "Profilleri değiştir", "css": "#btn-change"},
                {"ad": "Onar", "css": "#btn-repair"},
                {"ad": "Uygulamayı kaldır", "css": "#btn-uninstall"},
                {"ad": "Destek", "css": "#foot-support"},
            ]
        },
        "error": {"kritik": [{"ad": "hata kutusu", "css": "#error"}, {"ad": "Onar", "css": "#btn-repair"}]},
        "gunc": {"kritik": [{"ad": "güncelleme açıklaması", "css": "#gunc-lead"}]},
    },
    # ⚠️ durum adları EĞİK ÇİZGİSİZ: Git-Bash (MSYS) "/"-ile başlayan argümanı Windows yoluna çevirir → "/" durumu sessizce atlanıyordu (ölçüldü)
    "site": {
        "ana": {"yol": "/", "kritik": [{"ad": "üst çubuk: Giriş yap / Menü", "css": "header button"}]},
        "download": {
            "yol": "/download",
            "kritik": [{"ad": "birincil indirme düğmesi", "css": "main button[data-kapi='indir'], main button"}],
        },
        "features": {"yol": "/features", "kritik": []},
        "pricing": {"yol": "/pricing", "kritik": []},
        "support": {"yol": "/support", "kritik": []},
    },
}

# ── launcher durum enjeksiyonu (ampirik ajanın _inject.js'i; index.html'e DOKUNMADAN geçici kopya) ─
LAUNCHER_INJECT = r"""
<script>(function(){
  var v = new URLSearchParams(location.search).get("v") || "detect";
  var $ = function(id){ return document.getElementById(id); };
  ["s-detect","s-login","s-select","s-install","s-guncelleme","s-ready"].forEach(function(id){ $(id).hidden = true; });
  if (v === "gunc") { document.documentElement.classList.add("gunc"); $("s-guncelleme").hidden=false;
    $("gunc-lead").textContent="Yeni sürüm indiriliyor ve kuruluyor. Bu pencere işlem bitince kendiliğinden kapanacak; lütfen bilgisayarı kapatmayın."; return; }
  $("ver").textContent = "v9.9.99";
  if (v === "detect") { $("s-detect").hidden=false; return; }
  $("auth-box").hidden = false; $("auth-email").textContent = "ornek.kullanici@klinik.example";
  if (v === "login") { $("auth-box").hidden = true; $("s-login").hidden=false; $("btn-offline-start").hidden=false;
    var e=$("error"); e.hidden=false; e.textContent="E-posta ve parola gerekli."; return; }
  if (v === "select") { $("s-select").hidden=false;
    var defs=[["Evcil Hayvan Sahibi","Analiz odaklı ev kullanımı — kedi/köpek organ lokalizasyonu ve ses analizi","0,32 GB",true],
              ["Veteriner Hekim","Klinik seans yönetimi, hasta kayıtları, AI Pro teşhis ve raporlama","0,61 GB",true],
              ["Araştırma Modu","Simülasyon, ham sensör verisi ve deneysel protokoller","0,12 GB",false]];
    var box=$("cards"); defs.forEach(function(d){ var c=document.createElement("div"); c.className="card"+(d[3]?" sel":"");
      c.innerHTML='<span class="box"></span><div class="meta"><b>'+d[0]+'</b><span>'+d[1]+'</span></div><span class="size">'+d[2]+'</span>'; box.appendChild(c); });
    var dn=$("dep-notice"); dn.hidden=false; dn.textContent="Not: Veteriner Hekim profilinin AI Pro organ lokalizasyonu, Evcil Hayvan Sahibi paketindeki modelleri kullanır.";
    $("btn-install").disabled=false; $("sel-back-wrap").hidden=false; return; }
  if (v === "install") { $("s-install").hidden=false; $("pct").textContent="%47"; $("bar").querySelector("i").style.width="47%";
    $("dl-bytes").textContent="612,4 / 1.570,2 MB"; $("dl-speed").textContent="12,8 MB/sn"; $("dl-eta").textContent="1 dk 15 sn";
    $("status").textContent="base.zip indiriliyor — runtime katmanı (1/4)"; return; }
  if (v === "ready" || v === "error") { $("s-ready").hidden=false; var ch=$("chips");
    ["Evcil Hayvan Sahibi","Veteriner Hekim","Araştırma Modu"].forEach(function(n){ var s=document.createElement("span"); s.className="chip"; s.textContent=n; ch.appendChild(s); });
    var n=$("notice"); n.hidden=false; n.innerHTML='<b>Arka planda güncelleme indiriliyor</b><div class="bgline"><div class="bgbar"><i style="width:63%"></i></div><span class="bgpct">%63</span></div>';
    if (v === "error") { var e=$("error"); e.hidden=false; e.innerHTML='Kurulum doğrulanamadı: SHA-256 uyuşmazlığı. "Onar" ile yeniden deneyin.<div class="errdetail">deps.zip → sha256 beklenen 3f1c…9a2e, gelen 77b0…10cd</div>'; }
  }
})();</script>
"""

# ── ölçüm JS'i (sayfada koşar; JSON döndürür) ───────────────────────────────────────────
METRIK_JS = r"""
(async (SPEC) => {
  const gorunur = (el) => { const r = el.getBoundingClientRect(); if (!(r.width > 0 && r.height > 0)) return false;
    const cs = getComputedStyle(el); return cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity) > 0.05; };
  const anahtar = (el) => ((el.innerText || el.getAttribute('aria-label') || el.id || el.tagName) + '').trim().replace(/\s+/g, ' ').slice(0, 40);
  const bul = (k) => {
    if (k.css) { const hepsi = [...document.querySelectorAll(k.css)]; return hepsi.find(gorunur) || hepsi[0] || null; }
    const re = new RegExp(k.metin); const adaylar = [...document.querySelectorAll('button,a,[role=button],[role=link]')]
      .filter(e => gorunur(e) && re.test((e.innerText || '').trim()));
    return k.son ? adaylar[adaylar.length - 1] : adaylar[0];
  };
  if (SPEC.hazirla && SPEC.hazirla.startsWith('tikla:metin:')) {
    const el = bul({ metin: SPEC.hazirla.slice(12) }); if (!el) return { hata: 'hazirla: eleman yok ' + SPEC.hazirla };
    el.click(); await new Promise(r => setTimeout(r, 1200));
  }
  document.documentElement.style.scrollBehavior = 'auto'; document.body.style.scrollBehavior = 'auto';
  await (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve());
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const de = document.scrollingElement || document.documentElement, vw = innerWidth, vh = innerHeight;
  const main = document.querySelector('main');
  const out = { vw, vh, sw: de.scrollWidth, sh: de.scrollHeight, bodySW: document.body.scrollWidth,
                mainSW: main ? main.scrollWidth : null, mainCW: main ? main.clientWidth : null, tasan: [], kucuk: [], kritik: [], ustKesik: null };
  // 1) taşan elemanlar (teşhis için ilk 8)
  let n = 0; for (const el of document.querySelectorAll('body *')) { if (n++ > 5000 || out.tasan.length >= 8) break;
    const r = el.getBoundingClientRect(); if (r.width && r.right > vw + 1 && r.left < vw) out.tasan.push({ tag: el.tagName, k: anahtar(el), sag: Math.round(r.right) }); }
  // 2) dokunma hedefleri
  const SEL = 'button,a[href],[role=button],[role=link],[role=tab],[role=switch],[role=checkbox],[role=radio],[role=menuitem],input[type=checkbox],input[type=radio],input[type=submit],summary';
  out.satirIci = []; out.aralikMuaf = [];
  const hedefler = [...document.querySelectorAll(SEL)].filter(e => gorunur(e) && !e.closest('[aria-hidden="true"]'));
  const dikd = hedefler.map(e => e.getBoundingClientRect());
  const komsuVar = (i) => { const r = dikd[i], cx = r.left + r.width / 2, cy = r.top + r.height / 2, yc = SPEC.dokunmaMin / 2;
    return dikd.some((o, j) => j !== i && !(cx + yc <= o.left || cx - yc >= o.right || cy + yc <= o.top || cy - yc >= o.bottom)); };
  for (let i = 0; i < hedefler.length; i++) { const el = hedefler[i];
    const r = dikd[i]; const kisa = Math.min(r.width, r.height); if (kisa >= SPEC.dokunmaMin) continue;
    const kayit = { k: anahtar(el), w: Math.round(r.width), h: Math.round(r.height) };
    // WCAG 2.5.8 aralık muafiyeti: eşik çaplı daire komşu hedefe değmiyorsa yanlış-dokunma riski yok → bilgi
    if (!komsuVar(i)) { if (out.aralikMuaf.length < 30) out.aralikMuaf.push(kayit); continue; }
    // WCAG 2.5.8 muafiyeti: metin akışındaki satır-içi bağlantı (display:inline <a>) → bilgi, kapıyı kırmızı yapmaz
    if (el.tagName === 'A' && getComputedStyle(el).display === 'inline') { if (out.satirIci.length < 30) out.satirIci.push(kayit); continue; }
    out.kucuk.push(kayit); }
  // 3) kritik elemanlar: var + görünür + kaydırınca görünüm alanında + üstü örtülmemiş
  for (const k of SPEC.kritik) { const el = bul(k);
    if (!el) { out.kritik.push({ ad: k.ad, durum: 'YOK' }); continue; }
    if (!gorunur(el)) { out.kritik.push({ ad: k.ad, durum: 'GIZLI' }); continue; }
    el.scrollIntoView({ block: 'center', inline: 'nearest' }); await new Promise(r => requestAnimationFrame(r));
    const r = el.getBoundingClientRect(); const icinde = r.top >= -1 && r.left >= -1 && r.bottom <= vh + 1 && r.right <= vw + 1;
    const cx = Math.max(0, Math.min(vw - 1, r.left + r.width / 2)), cy = Math.max(0, Math.min(vh - 1, r.top + r.height / 2));
    const ust = document.elementFromPoint(cx, cy); const acik = !!ust && (ust === el || el.contains(ust));
    out.kritik.push({ ad: k.ad, durum: !icinde ? 'DISARIDA' : (!acik ? 'ORTULU' : 'OK'), w: Math.round(r.width), h: Math.round(r.height),
                      orten: (!acik && ust) ? anahtar(ust) : undefined }); }
  window.scrollTo(0, 0); if (main) main.scrollTop = 0;
  // 4) launcher: üstten kesik içerik (launcher-1) — main.scrollTop=0 iken ilk görünür bölümün ilk çocuğu header'ın altında mı?
  if (SPEC.ustKesik && main) { const hdr = document.querySelector('header'); const sec = document.querySelector('main section:not([hidden])');
    const ilk = sec && sec.firstElementChild; if (ilk && hdr && gorunur(hdr)) { const t = ilk.getBoundingClientRect().top, hb = hdr.getBoundingClientRect().bottom;
      out.ustKesik = { kesik: t < hb - 1, ilkUst: Math.round(t), headerAlt: Math.round(hb) }; } }
  return out;
})(%SPEC%)
"""


# ── minimal RFC 6455 istemcisi (CDP metin çerçeveleri; bağımlılıksız) ─────────────────────
class CdpWs:
    def __init__(self, url: str, zaman_asimi: float = 60.0):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=zaman_asimi)
        anahtar = base64.b64encode(os.urandom(16)).decode()
        # ⚠️ Origin başlığı GÖNDERİLMEZ — Chrome yabancı origin'i 403 ile reddeder (websocket-client'ta suppress_origin=True)
        istek = (
            f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {anahtar}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(istek.encode())
        ham = b""
        while b"\r\n\r\n" not in ham:
            parca = self.sock.recv(4096)
            if not parca:
                raise RuntimeError("CDP: el sıkışma yarım kaldı")
            ham += parca
        bas, _, self.buf = ham.partition(b"\r\n\r\n")
        if b" 101 " not in bas.split(b"\r\n")[0]:
            raise RuntimeError("CDP: WebSocket yükseltmesi reddedildi: " + bas.decode(errors="replace")[:200])
        self.kimlik = 0

    def _oku(self, n: int) -> bytes:
        while len(self.buf) < n:
            parca = self.sock.recv(max(65536, n - len(self.buf)))
            if not parca:
                raise RuntimeError("CDP: bağlantı kapandı")
            self.buf += parca
        veri, self.buf = self.buf[:n], self.buf[n:]
        return veri

    def gonder(self, metin: str) -> None:
        yuk = metin.encode()
        bas = bytearray([0x81])
        n = len(yuk)
        if n < 126:
            bas.append(0x80 | n)
        elif n < 65536:
            bas.append(0x80 | 126)
            bas += struct.pack(">H", n)
        else:
            bas.append(0x80 | 127)
            bas += struct.pack(">Q", n)
        maske = os.urandom(4)
        self.sock.sendall(bytes(bas) + maske + bytes(b ^ maske[i % 4] for i, b in enumerate(yuk)))

    def al(self) -> str:
        parcalar = []
        while True:
            b0, b1 = self._oku(2)
            op, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._oku(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._oku(8))[0]
            if b1 & 0x80:
                maske = self._oku(4)
                veri = bytes(b ^ maske[i % 4] for i, b in enumerate(self._oku(n)))
            else:
                veri = self._oku(n)
            if op == 0x8:
                raise RuntimeError("CDP: karşı taraf kapattı")
            if op == 0x9:  # ping → pong
                self.sock.sendall(bytes([0x8A, 0x80]) + b"\0\0\0\0")
                continue
            if op in (0x1, 0x0):
                parcalar.append(veri)
                if b0 & 0x80:
                    return b"".join(parcalar).decode()

    def cagir(self, yontem: str, params: dict | None = None) -> dict:
        self.kimlik += 1
        self.gonder(json.dumps({"id": self.kimlik, "method": yontem, "params": params or {}}))
        while True:
            m = json.loads(self.al())
            if m.get("id") == self.kimlik:
                if "error" in m:
                    raise RuntimeError(f"CDP {yontem}: {m['error']}")
                return m.get("result", {})

    def olay_bekle(self, ad: str, sure: float) -> bool:
        son = time.time() + sure
        while time.time() < son:
            try:
                m = json.loads(self.al())
            except socket.timeout:
                return False
            if m.get("method") == ad:
                return True
        return False

    def kapat(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


# ── tarayıcı keşfi (ortam YETENEĞİ: ad değil dosya; `CI` bayrağı KULLANILMAZ) ─────────────
def tarayici_bul(istenen: str | None) -> str | None:
    adaylar = [
        istenen,
        os.environ.get("PEMF_TARAYICI"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/microsoft-edge",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for a in adaylar:
        if a and Path(a).is_file():
            return a
    for ad in ("msedge", "microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        yol = shutil.which(ad)
        if yol:
            return yol
    return None


def bos_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class SpaHandler(SimpleHTTPRequestHandler):
    """Statik dist sunumu + SPA geri dönüşü (/pricing → index.html). Log sessiz."""

    def log_message(self, *a):  # noqa: D401
        pass

    def send_head(self):
        yol = Path(self.translate_path(self.path))
        if not yol.exists() and "." not in Path(urllib.parse.urlparse(self.path).path).name:
            self.path = "/index.html"
        return super().send_head()


class SessizSunucu(ThreadingHTTPServer):
    def handle_error(self, request, client_address):  # Chrome bağlantıyı erken kapatınca WinError 10054 izi basılmasın
        pass


def sunucu_baslat(dizin: Path) -> tuple[ThreadingHTTPServer, int]:
    port = bos_port()
    srv = SessizSunucu(("127.0.0.1", port), partial(SpaHandler, directory=str(dizin)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, port


def tarayici_baslat(exe: str, profil: Path) -> tuple[subprocess.Popen, int]:
    port = bos_port()
    shutil.rmtree(profil, ignore_errors=True)
    proc = subprocess.Popen(
        [
            exe,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            "--lang=tr-TR",
            "--force-device-scale-factor=1",
            "--font-render-hinting=none",
            "--disable-extensions",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profil}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(80):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2).read()
            return proc, port
        except Exception:
            time.sleep(0.25)
    proc.kill()
    raise RuntimeError("tarayıcı 20 sn içinde CDP portunu açmadı")


def sekme_ac(port: int) -> dict:
    return json.loads(
        urllib.request.urlopen(
            urllib.request.Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
        ).read()
    )


def olc(
    port: int, url: str, w: int, h: int, mobil: bool, spec: dict, bekle: float, png: Path | None, mutasyon: str | None
) -> dict:
    sekme = sekme_ac(port)
    ws = CdpWs(sekme["webSocketDebuggerUrl"])
    try:
        ws.cagir(
            "Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": mobil}
        )
        if mobil:
            ws.cagir("Emulation.setTouchEmulationEnabled", {"enabled": True})
        ws.cagir("Page.enable")
        ws.cagir("Page.navigate", {"url": url})
        ws.olay_bekle("Page.loadEventFired", 20)
        time.sleep(bekle)
        if mutasyon:  # mutasyon kanıtı: depoya dokunmadan CSS enjekte et → kapı KIRMIZI olmalı
            ws.cagir(
                "Runtime.evaluate",
                {
                    "expression": f"(()=>{{const s=document.createElement('style');s.textContent={json.dumps(mutasyon)};document.head.appendChild(s);}})()"
                },
            )
            time.sleep(0.3)
        ifade = METRIK_JS.replace("%SPEC%", json.dumps(spec, ensure_ascii=False))
        r = ws.cagir("Runtime.evaluate", {"expression": ifade, "returnByValue": True, "awaitPromise": True})
        met = r.get("result", {}).get("value") or {"hata": str(r)[:300]}
        if png:
            png.parent.mkdir(parents=True, exist_ok=True)
            png.write_bytes(base64.b64decode(ws.cagir("Page.captureScreenshot", {"format": "png"})["data"]))
        return met
    finally:
        ws.kapat()
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{sekme['id']}", timeout=5).read()
        except Exception:
            pass


def bulgular_uret(hedef: str, durum: str, w: int, h: int, mobil: bool, met: dict) -> list[dict]:
    """Ölçümü bulgu satırlarına çevir. anahtar = hedef/durum/kontrol/eleman@kova — baseline bununla eşleşir."""
    b: list[dict] = []
    kv = kova(w)
    if "hata" in met:
        b.append(
            {"anahtar": f"{hedef}/{durum}/olcum-hatasi@{kv}", "siddet": "yuksek", "detay": met["hata"], "g": f"{w}x{h}"}
        )
        return b
    sw = max(met["sw"], met["bodySW"])
    if sw > met["vw"] + 1:
        b.append(
            {
                "anahtar": f"{hedef}/{durum}/tasma@{kv}",
                "siddet": "yuksek",
                "detay": f"scrollWidth {sw} > innerWidth {met['vw']}; taşanlar: {met['tasan'][:4]}",
                "g": f"{w}x{h}",
            }
        )
    if met.get("mainSW") and met.get("mainCW") and met["mainSW"] > met["mainCW"] + 1:
        b.append(
            {
                "anahtar": f"{hedef}/{durum}/tasma-main@{kv}",
                "siddet": "yuksek",
                "detay": f"main.scrollWidth {met['mainSW']} > clientWidth {met['mainCW']}",
                "g": f"{w}x{h}",
            }
        )
    esik = DOKUNMA_MIN_MOBIL if mobil else DOKUNMA_MIN_MASAUSTU
    for k in met["kucuk"]:
        kisa = min(k["w"], k["h"])
        b.append(
            {
                "anahtar": f"{hedef}/{durum}/dokunma/{k['k']}@{kv}",
                "siddet": "yuksek" if kisa < 24 else "orta",
                "detay": f"{k['w']}×{k['h']} px < {esik}",
                "g": f"{w}x{h}",
            }
        )
    for k in met["kritik"]:
        if k["durum"] != "OK":
            b.append(
                {
                    "anahtar": f"{hedef}/{durum}/kritik/{k['ad']}@{kv}",
                    "siddet": "yuksek",
                    "detay": f"{k['durum']}" + (f" (örten: {k.get('orten')})" if k.get("orten") else ""),
                    "g": f"{w}x{h}",
                }
            )
    if met.get("ustKesik") and met["ustKesik"]["kesik"]:
        b.append(
            {
                "anahtar": f"{hedef}/{durum}/ust-kesik@{kv}",
                "siddet": "yuksek",
                "detay": f"ilk içerik üstü {met['ustKesik']['ilkUst']} < header altı {met['ustKesik']['headerAlt']} (kaydırmayla ulaşılamaz)",
                "g": f"{w}x{h}",
            }
        )
    return b


def launcher_varyanti_hazirla(cikti: Path) -> str:
    kaynak = _KOK / "launcher" / "app" / "ui" / "index.html"
    html = kaynak.read_text(encoding="utf-8")
    if "</body>" not in html:
        raise RuntimeError("launcher index.html: </body> yok")
    hedef = cikti / "_launcher" / "index.html"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    # Modül betiği `window.__TAURI__.core` satırında TypeError ile ölür (Tauri yok) → durum enjeksiyonu DOM'u kurar.
    hedef.write_text(html.replace("</body>", LAUNCHER_INJECT + "</body>"), encoding="utf-8")
    return hedef.resolve().as_uri()


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # gömülü python stdout cp1254 tuzağı
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hedef", choices=list(HEDEFLER), required=True)
    ap.add_argument("--pf-dist", default=str(_KOK / "pf" / "dist"))
    ap.add_argument("--site-dist", default=str(_KOK / "pemf-vet-web" / "dist"))
    ap.add_argument("--cikti", default=str(_KOK.parent / "PEMF_BUILD" / "responsive_kapisi"))
    ap.add_argument("--baseline", default=str(BASELINE))
    ap.add_argument("--tarayici", default=None)
    ap.add_argument("--zorunlu", action="store_true", help="tarayıcı/derleme yoksa 3 yerine 2 (CI'da ŞART)")
    ap.add_argument(
        "--bekle", type=float, default=None, help="yükleme sonrası oturma süresi (pf varsayılan 3.5 sn, diğer 1.5)"
    )
    ap.add_argument("--gorunum", default=None, help="yalnız bu görünümler: 320x568,911x512")
    ap.add_argument("--durum", default=None, help="yalnız bu durum(lar): login,select")
    ap.add_argument(
        "--mutasyon", default=None, help="sayfaya enjekte edilecek CSS (kapının KIRMIZI olduğunu kanıtlamak için)"
    )
    ap.add_argument(
        "--bayat-hata", action="store_true", help="baseline'da olup artık görülmeyen kayıt → hata (ratchet)"
    )
    ap.add_argument("--png-yok", action="store_true")
    a = ap.parse_args(argv)

    exe = tarayici_bul(a.tarayici)
    if not exe:
        print(
            "ORTAM: Chromium tabanlı tarayıcı bulunamadı (Edge/Chrome) — kapı ATLANDI"
            + (" → --zorunlu: HATA" if a.zorunlu else "")
        )
        return 2 if a.zorunlu else 3
    cikti = Path(a.cikti).resolve()
    cikti.mkdir(
        parents=True, exist_ok=True
    )  # ⚠️ --user-data-dir MUTLAK olmalı (göreli yol → CDP portu hiç açılmıyor, ölçüldü)
    bekle = a.bekle if a.bekle is not None else (3.5 if a.hedef == "pf" else 1.5)
    secili_g = None
    if a.gorunum:
        secili_g = {tuple(int(x) for x in g.split("x")) for g in a.gorunum.split(",")}
    secili_d = set(a.durum.split(",")) if a.durum else None

    srv = None
    if a.hedef == "launcher":
        taban = launcher_varyanti_hazirla(cikti)
        url_uret = lambda durum: f"{taban}?v={durum}"  # noqa: E731
    else:
        dist = Path(a.pf_dist if a.hedef == "pf" else a.site_dist)
        if not (dist / "index.html").is_file():
            print(f"ORTAM: derleme çıktısı yok: {dist}/index.html (pf: `npm run export:web`, site: `npx vite build`)")
            return 2 if a.zorunlu else 3
        srv, port_http = sunucu_baslat(dist)
        url_uret = lambda durum: f"http://127.0.0.1:{port_http}{HEDEFLER[a.hedef][durum].get('yol', '/')}"  # noqa: E731

    proc, port = tarayici_baslat(exe, cikti / "_profil")
    bulgular: list[dict] = []
    olcumler: list[dict] = []
    try:
        for durum, tanim in HEDEFLER[a.hedef].items():
            if secili_d and durum not in secili_d:
                continue
            for w, h, mobil in GORUNUMLER[a.hedef]:
                if secili_g and (w, h) not in secili_g:
                    continue
                spec = {
                    "kritik": tanim.get("kritik", []),
                    "hazirla": tanim.get("hazirla"),
                    "dokunmaMin": DOKUNMA_MIN_MOBIL if mobil else DOKUNMA_MIN_MASAUSTU,
                    "ustKesik": a.hedef == "launcher",
                }
                ad = durum.strip("/").replace("/", "_") or "ana"
                png = None if a.png_yok else cikti / a.hedef / f"{ad}_{w}x{h}.png"
                met = None
                for deneme in (1, 2):  # tek yeniden deneme: sekme/WS takılması bulgu DEĞİLDİR
                    try:
                        met = olc(port, url_uret(durum), w, h, mobil, spec, bekle, png, a.mutasyon)
                        break
                    except Exception as e:  # noqa: BLE001
                        met = {"hata": f"{type(e).__name__}: {e}"}
                        time.sleep(1.0)
                olcumler.append(
                    {
                        "hedef": a.hedef,
                        "durum": durum,
                        "w": w,
                        "h": h,
                        "mobil": mobil,
                        "png": str(png) if png else None,
                        "m": met,
                    }
                )
                yeni = bulgular_uret(a.hedef, ad, w, h, mobil, met)
                bulgular.extend(yeni)
                print(
                    f"{a.hedef:8} {ad:10} {w:4}x{h:<4} sw={met.get('sw', '?'):>5} kucuk={len(met.get('kucuk', [])):2} "
                    f"kritik={sum(1 for k in met.get('kritik', []) if k['durum'] != 'OK')} bulgu={len(yeni)}",
                    flush=True,
                )
    finally:
        proc.terminate()
        if srv:
            srv.shutdown()

    # ── baseline karşılaştırması ─────────────────────────────────────────────────────────
    taban: dict[str, dict] = {}
    if Path(a.baseline).is_file():
        for kayit in json.loads(Path(a.baseline).read_text(encoding="utf-8")).get("bilinen", []):
            taban[kayit["anahtar"]] = kayit
    gorulen = {b["anahtar"] for b in bulgular}
    yeni = [b for b in bulgular if b["anahtar"] not in taban]
    bilinen = [b for b in bulgular if b["anahtar"] in taban]
    bayat = [k for k in taban if k.startswith(a.hedef + "/") and k not in gorulen]

    rapor = {
        "hedef": a.hedef,
        "tarayici": exe,
        "mutasyon": a.mutasyon,
        "olcumler": olcumler,
        "bulgular": bulgular,
        "yeni": yeni,
        "bilinen_sayisi": len(bilinen),
        "bayat": bayat,
    }
    (cikti / f"rapor_{a.hedef}.json").write_text(json.dumps(rapor, ensure_ascii=False, indent=1), encoding="utf-8")

    # yeni bulguları anahtar bazında tekilleştir (aynı anahtar 3 görünümde çıkabilir)
    tekil: dict[str, dict] = {}
    for b in yeni:
        tekil.setdefault(b["anahtar"], b)
    print(
        f"\n== {a.hedef}: {len(olcumler)} ölçüm · {len(bulgular)} bulgu satırı · bilinen {len(bilinen)} · YENİ {len(tekil)} · bayat {len(bayat)}"
    )
    for k, b in sorted(tekil.items()):
        print(f"  YENİ [{b['siddet']}] {k}  ({b['g']}): {b['detay'][:160]}")
    for k in bayat:
        print(f"  BAYAT (baseline'da var, artık görülmüyor → sil): {k}")
    if a.bayat_hata and bayat:
        return 1
    return 1 if tekil else 0


if __name__ == "__main__":
    sys.exit(main())
