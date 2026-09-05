# Author: mertaygn, cglrgrkn
"""SİTE RESPONSIVE CSS SÖZLEŞMESİ  [W, 2026-09-04 denetimi · 2026-09-05 taşındı].

NEDEN BURADA, VITEST'TE DEĞİL: `pemf-vet-web/src/index.css` vitest kurulumunda HİÇBİR sorgu
ekiyle okunamıyor — `?raw`, `?inline` ve `import.meta.glob` üçü de BOŞ dize döndürüyor (Vite'ın
CSS eklentisi araya giriyor; ölçüldü). `node:fs` de kullanılamaz: `tsconfig.app.json`
`types: ["vite/client"]` + `include: ["src"]` ile testleri de tip denetiminden geçiriyor, node
tipleri yok → `npx tsc -b` kırmızı olurdu (ölçüldü; site CI'ının tip adımı bu yüzden kırılmıştı).

⚠️ Gömülü python stdout cp1254 → dosya okumada encoding AÇIKÇA verilir.

ÖLÇÜLEN DURUM (headless Edge + CDP):
  · Altbilgi ve destek sayfasındaki yasal bağlantıların dokunma alanı 120-276 × 20 px'ti
    (erişilebilirlik tabanı 44) — 100 bulgu satırı.
  · iOS Safari 16 px altındaki bir giriş alanına odaklanınca sayfayı YAKINLAŞTIRIP geri
    çıkmıyordu; `.input` punto'su 0,875rem'di.
"""

import pathlib
import re

import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_CSS = _KOK / "pemf-vet-web" / "src" / "index.css"

pytestmark = pytest.mark.skipif(not _CSS.exists(), reason="pemf-vet-web/ yok — kapı atlanır")


def _css() -> str:
    return _CSS.read_text(encoding="utf-8")


def _kod() -> str:
    """CSS yorumlarını soyar.

    ⚠️ Bu depoda DÖRT kapı aynı tuzağa düştü: sözleşmenin KENDİ açıklaması yasakladığı dizeyi
    aynen içeriyor (burada `maximum-scale=1`), ham metinde arayan kapı kendi yorumunu ihlal
    sayıp yanlış-KIRMIZI yanıyor.
    """
    return re.sub(r"/\*.*?\*/", " ", _CSS.read_text(encoding="utf-8"), flags=re.DOTALL)


def test_KRITIK_tap_sinifi_44_px_taban_veriyor():
    """Metin bağlantısının dokunma alanı metin kutusu kadardı (20 px)."""
    kural = re.search(r"\.tap\s*\{[^}]*\}", _css())
    assert kural, ".tap sınıfı yok (altbilgi/destek bağlantıları 44 px tabanını ondan alıyor)"
    assert "min-height: 44px" in kural.group(0), f".tap 44 px taban vermiyor: {kural.group(0)!r}"


def test_KRITIK_dokunmatikte_input_puntosu_16_px():
    """iOS Safari 16 px altına odaklanınca yakınlaştırır ve geri çıkmaz."""
    css = _css()
    assert "pointer: coarse" in css, "dokunmatik punto kuralı yok"
    assert "font-size: max(1rem, 1em)" in css, "16 px taban verilmiyor"
    # ⚠️ Yakınlaştırmayı KAPATMAK erişilebilirliği keser; çözüm punto olmalı.
    assert "maximum-scale=1" not in _kod(), "yakınlaştırma kapatılmış — WCAG 1.4.4 ihlali; çözüm punto tabanıdır"


def test_KRITIK_katmansiz_yazilmis_yoksa_kural_kaybeder():
    """Tailwind v4 katman sırası: theme < base < components < utilities.

    `.input { font-size: .875rem }` components katmanında, `text-sm` utilities katmanında.
    16 px kuralı `@layer base` içine yazılsaydı İKİSİNE DE yenilirdi → kural sessizce ölürdü.
    """
    css = _css()
    i = css.find("pointer: coarse")
    assert i > -1
    # Kuraldan ÖNCEKİ metinde açık kalmış bir `@layer` bloğu olmamalı: kural dosyanın
    # sonunda, tüm @layer bloklarından SONRA ve katmansız durmalı.
    onceki = css[:i]
    assert onceki.count("@layer") > 0, "dosyada hiç @layer yok — yapı değişmiş, kapı güncellenmeli"
    acik = onceki.count("{") - onceki.count("}")
    assert acik == 0, (
        f"`pointer: coarse` kuralı bir @layer bloğunun İÇİNDE ({acik} blok açık): "
        "components/utilities katmanına yenilir ve iOS yakınlaşması geri gelir."
    )


def test_hareket_azalt_tercihi_kaydirma_animasyonunu_kapatir():
    assert "prefers-reduced-motion" in _css(), "smooth scroll vestibüler rahatsızlığı olan kullanıcıda sorun yaratır"


def test_danger_tokeni_tanimli():
    """Tek koyu tema: `dark:` yerine token. Açık-tema kırmızısı koyu zeminde okunmuyordu."""
    assert "--color-danger" in _css(), "danger token yok (text-danger sınıfı üretilmez)"
