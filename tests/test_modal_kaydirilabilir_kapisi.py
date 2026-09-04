# Author: mertaygn, cglrgrkn
"""MODAL KAYDIRILABİLİRLİK KAPISI  [S5 adım 12, 2026-09-04 responsive denetimi].

ÖLÇÜLEN DURUM: ortalanmış modallar yüzde tabanlı `maxHeight` ile kuruluydu ve gövdeleri düz
`View`'dı. Yoga'da çocukların varsayılan `flexShrink` değeri 0 olduğu için içerik tavanı aşınca
KIRPILIYOR, kaydırma da olmadığı için kartın ALTINDAKİ eylem satırına (Onayla ve Başlat / Anladım /
Kaydet) hiçbir şekilde ulaşılamıyordu. 8 bobinli AI önerisinde ve yatay telefonda (yükseklik
360-430) hekim onayı fiilen imkânsızdı (ekranB-10, kapsam-4, kabuk-4).

SÖZLEŞME: `<Modal` çizen her kaynak dosya ya
  (a) `ScrollableModalCard` kullanır (ortak ilkel: mutlak maxHeight + gövde ScrollView + SABİT
      eylem satırı + iOS klavye kaçınması), ya da
  (b) kendi içinde HEM `<ScrollView` HEM bir yükseklik tavanı (`maxHeight`) taşır.

⚠️ Bu bir YAPISAL kapıdır: davranışı jest testleri ölçer
   (AiSpecApprovalModal.test.tsx, gozlemNotuKorunmasi.test.tsx, BackupPassphraseDialog.test.tsx).
"""

import pathlib
import re

import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_PF = _KOK / "pf" / "src"

# Ortak ilkelin KENDİSİ: sözleşmeyi o tanımlar, kendi kendini doğrulamaz.
_ILKEL = "components/ui/ScrollableModalCard.tsx"

# Kabuk (AppShell) modalları: "Daha Fazla" alt sayfası ve bildirim paneli. Kendi maxHeight'leri
# pencere yüksekliğinden hesaplanır ve içlerinde ScrollView vardır → (b) dalından geçerler.

pytestmark = pytest.mark.skipif(
    not (_PF / "components" / "ui" / "ScrollableModalCard.tsx").exists(),
    reason="pf/ kaynak ağacı yok (yalnız backend paketi) — kapı atlanır",
)


def _modal_dosyalari():
    for p in sorted(_PF.rglob("*.tsx")):
        if "__tests__" in p.parts:
            continue
        bagil = p.relative_to(_PF).as_posix()
        if bagil == _ILKEL:
            continue
        src = p.read_text(encoding="utf-8")
        if "<Modal" in src:
            yield bagil, src


def test_KRITIK_her_modal_kisa_ekranda_kaydirilabilir():
    """Kaydırılamayan modalın eylem satırına yatay telefonda ULAŞILAMAZ."""
    ihlal = []
    for bagil, src in _modal_dosyalari():
        ortak = "ScrollableModalCard" in src
        kendi = "<ScrollView" in src and "maxHeight" in src
        if not (ortak or kendi):
            ihlal.append(bagil)
    assert not ihlal, (
        "Modal ne ScrollableModalCard kullanıyor ne de kendi ScrollView+maxHeight'ini taşıyor; "
        "kısa ekranda eylem satırına ulaşılamaz:\n" + "\n".join(ihlal)
    )


def test_ortak_ilkel_govdeyi_daraltilabilir_tutar():
    """`flexShrink: 1` olmadan ScrollView maxHeight'i AŞAR — ekranB-10'un kök nedeni buydu."""
    src = (_PF / "components" / "ui" / "ScrollableModalCard.tsx").read_text(encoding="utf-8")
    govde = re.search(r"body:\s*\{[^}]*\}", src)
    assert govde, "ScrollableModalCard'da `body` stili bulunamadı (yeniden adlandırıldıysa kapı güncellenmeli)"
    assert "flexShrink: 1" in govde.group(0), (
        "Gövde ScrollView'ı flexShrink:1 taşımıyor: Yoga varsayılanı 0 olduğundan içerik "
        "maxHeight'i aşıp kırpılır ve eylem satırı ekran dışında kalır."
    )


def test_ortak_ilkel_tavani_MUTLAK_hesaplar():
    """Yüzde tavan çentikli/yatay cihazda kartı ekran dışına taşırıyordu."""
    src = (_PF / "components" / "ui" / "ScrollableModalCard.tsx").read_text(encoding="utf-8")
    assert "insets.top" in src and "insets.bottom" in src, (
        "Kart tavanı güvenli alanları düşmüyor — yüzde hesabına dönülmüş olabilir."
    )
    assert 'maxHeight: "88%"' not in src and "maxHeight: '88%'" not in src


def test_onay_ve_yukseltme_modallari_ortak_ilkeli_kullanir():
    """Bu iki modal S5'te ortak ilkele taşındı; geri alınırsa kapı uyarır."""
    for bagil in ("components/domain/AiSpecApprovalModal.tsx", "components/UpgradeModal.tsx"):
        src = (_PF / bagil).read_text(encoding="utf-8")
        assert "ScrollableModalCard" in src, f"{bagil} ortak modal ilkelini bırakmış"
