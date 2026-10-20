# -*- coding: utf-8 -*-
"""I18N-0 · ARAÇ KAPISI — `scripts/i18n/cikar.py` (+ `cikar_ts.cjs`) kullanıcıya görünen metni YAKALIYOR, kodu / günlüğü DIŞLIYOR mu?

Neden kapı: göç partileri (13-I18N-PARTI) ve K-2 (sabit metin yasağı) bu araca dayanır. Araç bir sınıfı sessizce kaçırırsa (ör. JSX metni,
şablon içi parça, Rust #[error]) o sınıf kataloğa hiç taşınmaz ve K-2 "temiz" der — kör kapı. Her bölüm hem POZİTİF (görünen metin aday)
hem KARŞIT (kod / günlük aday DEĞİL) iddia taşır; mutantlar DUZELTME-I18N.md §A7'de.

TS tarafı node + TypeScript derleyicisi ister (`apps/ui|apps/web/node_modules/typescript`); yoksa o testler AÇIK gerekçeyle atlanır — aynı
çıkarıcıyı jest tarafı (`apps/ui/src/i18n/__tests__/cikarim.test.ts`) her koşuda sınar.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from scripts.i18n import cikar, ortak  # noqa: E402

_NODE = shutil.which("node")
_TS_VAR = any((KOK / a / "node_modules" / "typescript" / "package.json").is_file() for a in ("apps/ui", "apps/web"))
ts_gerekli = pytest.mark.skipif(
    not (_NODE and _TS_VAR), reason="node ya da apps/ui|apps/web node_modules/typescript yok (npm ci)"
)


def _metinler(adaylar):
    return {a["metin"] for a in adaylar}


# ── Python ───────────────────────────────────────────────────────────────────────────────────────────────────

_PY = '''
"""Modül belgesi — Türkçe ama docstring, aday DEĞİL."""
import logging
from fastapi import HTTPException
logger = logging.getLogger(__name__)
SABIT_ILETI = "Jeton hakkınız bitti; yeni analiz başlatılamadı."

def uc(x, ad):
    """İşlev belgesi."""
    logger.warning("Günlük iletisi Türkçe kalır %s", x)
    self_log = None
    if x == "Tamamlandı":
        pass
    if "seçin" in ad:
        pass
    d = {"durum": "bekliyor", "mesaj": "Kayıt silindi."}
    _push_notification(f"Bobin {ad} durduruldu", "warning")
    raise HTTPException(status_code=409, detail=f"Seans BAŞLATILMADI — {ad} bağlı değil.")

def _log_info(m):
    pass

def iki():
    _log_info("[STM32] Port seçimi yapıldı")
    return {"detail": "Geçersiz istek verisi."}
'''


def test_python_gorunen_metin_aday_kod_ve_gunluk_degil():
    adaylar, hatalar = cikar.py_adaylari("apps/backend/servers/ornek.py", _PY)
    assert not hatalar
    m = _metinler(adaylar)
    # POZİTİF
    assert "Seans BAŞLATILMADI — {{ad}} bağlı değil." in m
    assert "Bobin {{ad}} durduruldu" in m
    assert "Kayıt silindi." in m
    assert "Jeton hakkınız bitti; yeni analiz başlatılamadı." in m
    assert "Geçersiz istek verisi." in m
    turler = {a["metin"]: a["tur"] for a in adaylar}
    assert turler["Seans BAŞLATILMADI — {{ad}} bağlı değil."] == "detail"
    assert turler["Bobin {{ad}} durduruldu"] == "bildirim"
    yt = {a["metin"]: a["yertutucular"] for a in adaylar}
    assert yt["Seans BAŞLATILMADI — {{ad}} bağlı değil."] == ["ad"]
    # KARŞIT
    assert not any("Günlük iletisi" in x for x in m), "logger iletisi aday olmamalı"
    assert not any("Port seçimi" in x for x in m), "_log_info yardımcı günlüğü aday olmamalı"
    assert "Modül belgesi — Türkçe ama docstring, aday DEĞİL." not in m
    assert "İşlev belgesi." not in m
    assert "Tamamlandı" not in m, "karşılaştırma değeri aday olmamalı"
    assert "bekliyor" not in m


# ── Rust ─────────────────────────────────────────────────────────────────────────────────────────────────────

_RS = r'''
// Yorum: "Türkçe yorum dizgisi aday DEĞİL"
#[derive(Debug, thiserror::Error)]
pub enum Hata {
    #[error("dosya sistemi hatası: {0}")]
    Io(#[from] std::io::Error),
}
pub fn f(port: u16) -> Result<(), String> {
    eprintln!("günlük: port {port} açılamadı");
    log_line(&format!("ilerleme günlüğü {}", port));
    let m = format!("Uygulama {port} portunda başlatılamadı. Onar'ı deneyin.");
    Err("İnternet bağlantısı yok — kurulum indirilemedi.".into())
}
#[cfg(test)]
mod tests {
    #[test]
    fn t() { assert_eq!(super::g(), "Test dizgisi aday DEĞİL"); }
}
'''


def test_rust_gorunen_metin_aday_yorum_gunluk_test_degil():
    adaylar = cikar.rust_adaylari("launcher/core/src/ornek.rs", _RS)
    m = _metinler(adaylar)
    assert "dosya sistemi hatası: {{deger1}}" in m
    assert "Uygulama {{port}} portunda başlatılamadı. Onar'ı deneyin." in m
    assert "İnternet bağlantısı yok — kurulum indirilemedi." in m
    tur = {a["metin"]: a["tur"] for a in adaylar}
    assert tur["dosya sistemi hatası: {{deger1}}"] == "hata"
    assert not any("yorum dizgisi" in x for x in m)
    assert not any("günlük" in x for x in m), "eprintln!/log_line günlükleri aday olmamalı"
    assert not any("Test dizgisi" in x for x in m), "#[cfg(test)] modülü taranmamalı"


# ── NSIS ─────────────────────────────────────────────────────────────────────────────────────────────────────

_NSI = r'''
; Yorum: DetailPrint "yorumdaki ileti aday DEĞİL"
!macro NSIS_HOOK_PREUNINSTALL
  DetailPrint "PEMF: aktif seans güvenliği — bobinlere E-stop gönderiliyor (port $2)…"
  MessageBox MB_OK|MB_ICONEXCLAMATION "PEMF: bobin acil-durdurma DOĞRULANAMADI ($0).$\r$\n$\r$\nBobinleri ELLE kontrol edin."
!macroend
'''


def test_nsis_iletileri_aday_yorum_degil():
    adaylar = cikar.nsis_adaylari("launcher/app/windows/hooks.nsi", _NSI)
    m = _metinler(adaylar)
    assert any(x.startswith("PEMF: aktif seans güvenliği") for x in m)
    assert any("DOĞRULANAMADI" in x and "ELLE kontrol" in x for x in m)
    assert not any("yorumdaki" in x for x in m)


# ── HTML (metin düğümü + öznitelik; <script> içeriği TS çıkarıcısına) ────────────────────────────────────────

_HTML = """<!doctype html><html lang="tr"><head><title>PEMF Vet Client</title><style>.a{content:"Stil metni"}</style></head>
<body><h1>Kurulum hazırlanıyor</h1><button title="Uygulamayı onar">Onar</button><input placeholder="E-posta adresiniz">
<script>
const I18N = { tr: { ready: "Hazır — uygulama açılıyor" } };
console.log("konsol günlüğü aday değil");
</script></body></html>"""


def test_html_metin_ve_oznitelik_aday():
    adaylar, betikler = cikar.html_adaylari("launcher/app/ui/index.html", _HTML)
    m = _metinler(adaylar)
    assert "Kurulum hazırlanıyor" in m
    assert "Uygulamayı onar" in m
    assert "Onar" in m
    assert "E-posta adresiniz" in m
    assert not any("Stil metni" in x for x in m)
    assert betikler and "Hazır — uygulama açılıyor" in betikler[0]["metin"]
    assert betikler[0]["satirOtele"] >= 2, "betik satır ötelemesi HTML'deki gerçek satırı göstermeli"


@ts_gerekli
def test_html_betik_icerigi_ts_cikariciya_gider_ve_satir_dogru():
    dosya = "launcher/app/ui/index.html"
    adaylar, betikler = cikar.html_adaylari(dosya, _HTML)
    r = cikar.ts_adaylari(betikler, KOK)
    hazir = [a for a in r["adaylar"] if a["metin"] == "Hazır — uygulama açılıyor"]
    assert hazir, r
    satir = next(i for i, s in enumerate(_HTML.splitlines(), 1) if "Hazır — uygulama" in s)
    assert hazir[0]["satir"] == satir
    assert hazir[0]["dosya"] == dosya
    assert not any("konsol günlüğü" in a["metin"] for a in r["adaylar"])


# ── TS / TSX ─────────────────────────────────────────────────────────────────────────────────────────────────

_TSX = """
import { Alert, Text, View } from "react-native";
import type { Mod } from "./tur";
export const BASLIK = "⚠️ ACİL DURDURMA DOĞRULANAMADI";
type Kip = "otomatik" | "Elle seçim yapılır";
export function Ekran({ n, ad }: { n: number; ad: string }) {
  console.warn("Konsol günlüğü Türkçe kalır");
  if (ad === "Tamamlandı") return null;
  const yazi = `Hasta başarıyla ${ad ? "güncellendi" : "kaydedildi"}.`;
  Alert.alert("Kayıt silinsin mi?", "Bu işlem geri alınamaz.");
  return (
    <View testID="ekran-kok" accessibilityLabel="Ana ekran">
      <Text>
        Seans
        geçmişi
      </Text>
      <Text>Toplam: {n}</Text>
      <Text>{`🚨 ACİL DURDUR${n > 0 ? ` (${n} bobin)` : ""}`}</Text>
      <Text>{n > 1 ? "Hastalar" : "Hasta"}</Text>
    </View>
  );
}
"""


def _ts(kaynak: str, ad: str = "apps/ui/src/screens/OrnekScreen.tsx"):
    r = cikar.ts_adaylari([{"ad": ad, "metin": kaynak}], KOK, olcum=True)
    assert not r["hatalar"], r["hatalar"]
    return r


@ts_gerekli
def test_ts_jsx_oznitelik_ileti_sablon_aday():
    r = _ts(_TSX)
    a = r["adaylar"]
    m = _metinler(a)
    # POZİTİF
    assert "Seans geçmişi" in m, "çok satırlı JSX metni"
    ham = {x["metin"]: x["ham"] for x in a}
    assert ham["Seans geçmişi"] == "Seans geçmişi", "React JSX boşluk kuralı: satır sonları tek boşluk"
    assert "Toplam:" in m and ham["Toplam:"] == "Toplam: ", "tek satırdaki son boşluk ham değerde KORUNUR"
    assert "Ana ekran" in m
    assert "Kayıt silinsin mi?" in m and "Bu işlem geri alınamaz." in m
    assert "🚨 ACİL DURDUR{{deger1}}" in m, "dış şablon yer tutuculu"
    assert "({{n}} bobin)" in m, "iç içe şablon parçası ayrıca aday"
    assert "Hastalar" in m and "Hasta" in m, "koşullu JSX ifadesi dalları"
    assert "Hasta başarıyla {{deger1}}." in m
    assert "güncellendi" in m and "kaydedildi" in m, "şablon içi koşullu Türkçe parça"
    tur = {x["metin"]: x for x in a}
    assert tur["⚠️ ACİL DURDURMA DOĞRULANAMADI"]["modulDuzeyi"] is True
    assert tur["Ana ekran"]["tur"] == "oznitelik"
    assert tur["Kayıt silinsin mi?"]["tur"] == "ileti"
    assert tur["Toplam:"]["birlesik"] is True, "ifadeyle karışık JSX metni birleşik işaretlenir"
    assert tur["Seans geçmişi"]["bilesen"] == "Ekran"
    # KARŞIT
    assert "ekran-kok" not in m, "testID aday değil"
    assert "Tamamlandı" not in m, "karşılaştırma değeri aday değil"
    assert not any("Konsol günlüğü" in x for x in m)
    assert "react-native" not in m and "./tur" not in m
    assert "Elle seçim yapılır" not in m, "tür birleşimindeki dizgi aday değil"


@ts_gerekli
def test_ts_jsx_ifadesindeki_tek_sozcuk_buyuk_harf_aday_ama_sabit_ve_karsilastirma_degil():
    # P1 ekran taraması: `{bagli ? "CANLI" : "OFFLINE"}` ekrana yazılır; eski sezgi tek sözcüklü büyük harfi SABIT_ADI sanıp atlıyordu
    kaynak = """
import { Text } from "react-native";
const MOD_AD = "ILERI";
export function Rozet({ bagli, mod }: { bagli: boolean; mod: string }) {
  const kip = mod === "HIZLI" ? 1 : 2;
  return (
    <Text>
      {bagli ? "CANLI" : "OFFLINE"}
      {kip}
    </Text>
  );
}
"""
    m = _metinler(_ts(kaynak)["adaylar"])
    assert "CANLI" in m and "OFFLINE" in m, "JSX alt ifadesindeki tek sözcük aday"
    assert "HIZLI" not in m, "karşılaştırma değeri aday değil"
    assert "ILERI" not in m, "JSX dışı sabit tanımlayıcı aday değil"


@ts_gerekli
def test_ts_olcum_karsilastirma_ve_sayi_ayristirma():
    kaynak = """
    export function f(eylem: string, s: string) {
      const a = /Sıfırla/.test(eylem);
      const b = s.includes("parola hatalı");
      const n = parseFloat(s.replace(",", "."));
      return new Date().toLocaleDateString("tr-TR") + String(a && b && n);
    }
    """
    o = _ts(kaynak, "apps/ui/src/utils/ornek.ts")["olcum"]
    ifadeler = " ".join(x["ifade"] for x in o["karsilastirma"])
    assert "/Sıfırla/.test(eylem)" in ifadeler
    assert 's.includes("parola hatalı")' in ifadeler
    assert o["sayiAyristirma"] and o["yerelAyar"]


# ── iki dogal_mi uygulaması AYNI karar verir (sürüklenme kapısı) ─────────────────────────────────────────────

_ORNEKLER = [
    "Kaydet",
    "kaydet",
    "Hastalar",
    "ACİL DURDUR",
    "🚨 DURDURULUYOR…",
    "UYARI:",
    "OK",
    "API",
    "veterinarian",
    "fgs_total",
    "Content-Type",
    "application/json",
    "/api/health",
    "https://pemf.example/x",
    "#ff0000",
    "12 mT",
    "%",
    "Hz",
    "Tüm bobinler durduruldu ✓",
    "No data",
    "x",
    "Bağlı değil",
    "pemf.dil",
    "a.b.c",
    "rgba(0,0,0,0.5)",
    "Seans geçmişi",
    "PEMF Vet",
    "AI Pro",
    "1.9.51",
    "ölçüm",
    "Görüntü",
    "kayit.json",
    "Durdur!",
]


@ts_gerekli
def test_dogal_mi_python_ve_js_ayni():
    js = "const c=require(process.argv[1]);process.stdout.write(JSON.stringify(JSON.parse(process.argv[2]).map(c.dogalMi)))"
    r = subprocess.run(
        [_NODE, "-e", js, str(KOK / "scripts" / "i18n" / "cikar_ts.cjs"), json.dumps(_ORNEKLER)],
        capture_output=True,
        check=True,
    )
    js_sonuc = json.loads(r.stdout.decode("utf-8"))
    py_sonuc = [ortak.dogal_mi(s) for s in _ORNEKLER]
    farklar = [(s, p, j) for s, p, j in zip(_ORNEKLER, py_sonuc, js_sonuc) if p != j]
    assert not farklar, f"dogal_mi (Python) ≠ dogalMi (JS): {farklar}"
    beklenen_dogal = {
        "Kaydet",
        "Hastalar",
        "ACİL DURDUR",
        "🚨 DURDURULUYOR…",
        "UYARI:",
        "Tüm bobinler durduruldu ✓",
        "No data",
        "Bağlı değil",
        "Seans geçmişi",
        "PEMF Vet",
        "AI Pro",
        "ölçüm",
        "Görüntü",
        "Durdur!",
    }
    assert {s for s, p in zip(_ORNEKLER, py_sonuc) if p} == beklenen_dogal


# ── Yüzey dosyaları + CLI ────────────────────────────────────────────────────────────────────────────────────


def test_yuzey_dosyalari_testleri_dislar_ve_bilinen_dosyalari_kapsar():
    arayuz = ortak.yuzey_dosyalari("arayuz")
    assert "apps/ui/src/components/ui/GlobalEmergencyStop.tsx" in arayuz
    assert "apps/ui/src/screens/AuthScreen.tsx" in arayuz
    assert not any("__tests__" in d or d.endswith(".d.ts") for d in arayuz)
    sunucu = ortak.yuzey_dosyalari("sunucu")
    assert "apps/backend/servers/api_server.py" in sunucu
    launcher = ortak.yuzey_dosyalari("launcher")
    assert {"launcher/app/ui/index.html", "launcher/app/windows/hooks.nsi", "launcher/app/src/main.rs"} <= set(launcher)
    assert ortak.dosyanin_yuzeyi("apps/web/src/pages/Home.tsx") == "site"
    assert ortak.dosyanin_yuzeyi("dema-terapi-simülatörü/src/App.tsx") == "dema"


def test_cli_taban_bicimi(tmp_path):
    cikti = tmp_path / "taban.json"
    # Örnek dosya: `klinik_asgari.py` (AI mikroservisiyle ORTAK yaprak modül → Türkçe sabitleri kaynakta KALIR; `seans_durum.py` P1-10e'de katalog anahtarına taşındı).
    rc = cikar.main(["--dosya", "apps/backend/utils/klinik_asgari.py", "--taban", "--cikti", str(cikti)])
    assert rc == 0
    veri = json.loads(cikti.read_text(encoding="utf-8"))
    assert veri["dosyalar"] == ["apps/backend/utils/klinik_asgari.py"]
    assert veri["metinler"], "klinik_asgari.py Türkçe iletiler taşır"
    assert set(veri["metinler"][0]) == {"yuzey", "dosya", "satir", "metin", "ham", "tur", "baglam", "birlesik"}
    assert any(x["metin"] == "yaş negatif olamaz" for x in veri["metinler"])


@ts_gerekli
def test_ts_jsx_html_varliklari_react_gibi_COZULUR():
    """`&quot;` / `&apos;` / `&gt;` JSX metninde ve öznitelikte React tarafından çözülür; ham değer (= katalog TR) da çözülmüş olmalı —
    yoksa t() düz dizgi döndüğü için ekranda `&quot;` görünürdü. JS dizgisindeki `&amp;` ise çözülmez (React onu olduğu gibi basar)."""
    kaynak = (
        "export function A() {\n"
        '  const x = "Ham &amp; kalır";\n'
        '  return <Text title="Kedi &amp; köpek">Üst menüdeki &quot;E-posta hesapları&quot;ndan &gt; geçin</Text>;\n'
        "}\n"
    )
    a = {x["metin"]: x for x in _ts(kaynak)["adaylar"]}
    assert a['Üst menüdeki "E-posta hesapları"ndan > geçin']["ham"] == 'Üst menüdeki "E-posta hesapları"ndan > geçin'
    assert a["Kedi & köpek"]["ham"] == "Kedi & köpek"
    assert a["Ham &amp; kalır"]["ham"] == "Ham &amp; kalır"
