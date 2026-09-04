# Author: mertaygn, cglrgrkn
"""AI KARE BOYUTU — istemci oran kilidinin KAYNAĞI  [S7 adım 4, 2026-09-04 denetimi].

ÖLÇÜLEN DURUM: AI görüntü yanıtları yalnız `image_base64` taşıyordu. Karenin gerçek boyutu
(`oh, ow`) küçültme için zaten hesaplanıyor ama ATILIYORDU. İstemci kutunun oranını bilemediği
için görüntüyü kırpıyor, üzerine çizilen ORGAN İŞARETLERİ kırpılmamış koordinatlara göre
yerleştiği için canlı görüntüyle KAYIYORDU. Bu bir tıbbi karar ekranı (hekim organ konumuna
bakarak dozu onaylıyor).

SÖZLEŞME: kare döndüren her yanıt kodlanan dizinin GERÇEK boyutunu da verir
(`image_w`/`image_h`; WebSocket'te `imageW`/`imageH`). Alan YALNIZ-EK: eski istemci yok sayar,
yeni istemci alan yoksa cihaz yönü varsayılanına düşer (pf/src/utils/kameraKutusu.ts).

⚠️ Bu dosya model çalıştırmaz; yardımcının doğruluğunu ve yanıt/yayın noktalarının alanı
TAŞIDIĞINI kaynak düzeyinde kilitler (modeller CI'da yüklü değil).
"""

import ast
import pathlib

import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_ROUTER = _KOK / "servers" / "ai_router.py"

pytestmark = pytest.mark.skipif(not _ROUTER.exists(), reason="servers/ai_router.py yok")


def _kaynak() -> str:
    return _ROUTER.read_text(encoding="utf-8")


def test_KRITIK_yardimci_kodlanan_dizinin_boyutunu_verir():
    """`_kare_boyutu` shape'ten (h, w) okur ve int döndürür — yanlış sıra oranı TERS çevirir."""
    kaynak = _kaynak()
    agac = ast.parse(kaynak)
    fn = next(
        (d for d in agac.body if isinstance(d, ast.FunctionDef) and d.name == "_kare_boyutu"),
        None,
    )
    assert fn is not None, "servers/ai_router.py içinde _kare_boyutu yardımcısı yok"

    # Yardımcıyı numpy'siz, sahte bir dizi ile çalıştır (shape yeterli).
    # ⚠️ İmzada `np.ndarray` tip notu var; numpy CI'da yüklü olmayabilir → sahte modülle bağla.
    govde = ast.get_source_segment(kaynak, fn)

    class _SahteNp:
        ndarray = object

    ortam: dict = {"np": _SahteNp}
    exec(compile(ast.parse(govde), "<kare_boyutu>", "exec"), ortam)  # noqa: S102

    class SahteDizi:
        shape = (960, 1280, 3)

    assert ortam["_kare_boyutu"](SahteDizi()) == {"image_w": 1280, "image_h": 960}


def test_KRITIK_kare_donduren_yanitlar_boyutu_tasiyor():
    """Beş HTTP yanıtı (landmark, ai_pro/frame, segmentation, thermal, cat_organ) + retikülosit."""
    kaynak = _kaynak()
    assert kaynak.count("**_kare_boyutu(") >= 6, (
        "Kare döndüren yanıtlardan biri boyut alanını bırakmış; istemci oran kilidi "
        "varsayılana düşer ve organ işaretleri kayabilir."
    )


def test_KRITIK_websocket_yayinlari_boyutu_tasiyor():
    """Hazırlık önizlemesi ve seans yayını `ai_vision` şemasıyla aynı alanları taşır."""
    kaynak = _kaynak()
    assert kaynak.count('"imageW"') == 2 and kaynak.count('"imageH"') == 2, (
        "ai_vision yayınlarından biri imageW/imageH taşımıyor (hazırlık önizlemesi ve seans "
        "yayını AYNI şemayı kullanmak zorunda)."
    )


def test_alan_yalniz_EK_oldugu_icin_geriye_uyumlu():
    """image_base64 alanı kaldırılmamalı: eski istemciler onunla çiziyor."""
    kaynak = _kaynak()
    assert '"image_base64": b64_image' in kaynak
    assert '"imageBase64": b64_image' in kaynak
