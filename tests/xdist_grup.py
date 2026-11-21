# -*- coding: utf-8 -*-
"""Y312 (sahip 20-11: "tam testlerde süreler kısalsın" · "xdist kur") — pytest-xdist `--dist loadgroup` altında İŞARETSİZ testler kendi
DOSYALARININ biriminde (`loadfile` gibi), `xdist_group("seri")` işaretliler farklı dosyalarda olsalar da TEK işçide koşar.

Neden: xdist'in `loadgroup` zamanlayıcısı işaretsiz testi TEK BAŞINA birim yapar (`load` gibi; 3.8 `scheduler/loadgroup._split_scope`)
→ bir dosyanın testleri işçilere bölünür. Süit dosya içi sıraya göre yazılmıştır (modül fikstürleri, iki kollu meta kapılar: 1. kol
kirletir, 2. kol temiz görmeli). İşaretsiz teste `xdist_group` vermek de çözüm DEĞİL: xdist işaretli testin düğüm kimliğine `@grup`
soneki ekler ve düğüm kimliğine bakan kapılar (OA24, C2_3_5) bozulur (PX'te ölçüldü). Bu yüzden düğüm kimliğine DOKUNULMAZ; yalnız
zamanlayıcının birim seçimi değişir: denetleyicide `pytest_xdist_make_scheduler` (tests/conftest.py) bu zamanlayıcıyı döndürür.
Seri koşuda ve başka dağıtım kiplerinde HİÇBİR şey yapmaz (None → xdist varsayılanı). Kapı: tests/test_xdist_dosya_grubu_Y312.py

YGH (istem 59, sahip 20-11 "ağır model testleri tek işçide") AĞIR MODEL GRUBU: gerçek ağırlık yükleyen dosyalar modeli işçi ÖMRÜ boyunca
önbellekte tutar. Dağınıkken her işçi farklı modelleri AYRI yükler → guii Y30 (6 işçi, gerçek ağırlıklar) RAM tepesi %99,0: tepe anında altı
işçinin her biri hafif test koşarken 2–4 GB tutuyordu (YGH keşfi 21-11, işçi başına test-bellek kaydı). `AGIR_MODEL_DOSYALARI` tek birimde
(`AGIR`) → aynı işçide dosya dosya sırayla; diğer işçiler hafif kalır. Silme / atlama / gevşetme YOK; düğüm kimliği DEĞİŞMEZ (işaret değil,
yalnız zamanlama birimi). Liste ölçümden: işçi çalışma kümesinde ≥ 300 MB kalıcı artış ya da ≥ 1 GB geçici tepe yapan gerçek-ağırlık
dosyaları + aynı ağırlıkları yükleyen kardeşleri (başka işçide ilk yükleyici olurlardı). Yeni gerçek-model testi buraya eklenir.
"""

from __future__ import annotations

SERI = "seri"
AGIR = "agir-model"
AGIR_MODEL_DOSYALARI = frozenset(
    {
        "tests/test_KP_ai_router_analiz_uclari.py",
        "tests/test_ODD_B3_oneri_KONUM_ESKI_ile_BULUNAMADI_ayri.py",
        "tests/test_OTB_T123_onay_DOZ_tavani_MODEL_ve_fizik_duzeltmesi.py",
        "tests/test_OYZ4_1_kuyu_araligi_SON5_ORTANCA_Y306.py",
        "tests/test_T3_Y189_KOSULSUZ_kip_ve_kabin_kamerasi_KARE.py",
        "tests/test_ai_golden_values.py",
        "tests/test_ai_hub_fantom_petri_v2v3_YANIT_ve_PARITE_AI2_C3.py",
        "tests/test_ai_pro_arastirma_gercek_pipeline.py",
        "tests/test_ai_pro_canli_alan_ve_denetim.py",
        "tests/test_gradient_xai_ses_termal.py",
        "tests/test_petri_cv_v2_KAHIN_MAKULLIK_ONNX_AI2_C1.py",
        "tests/test_petri_plausibility.py",
        "tests/test_petri_v2_KIRPIK_plaka_PEMF_kapisi_AII_1_1.py",
        "tests/test_renal_xai.py",
        "tests/test_scratch_gercek_model.py",
        "tests/test_xai_faz2_kuyruk.py",
        "tests/test_xai_hucre_SKOR_hedefli_cam_AI1_X5.py",
        "tests/test_xai_ses_BOS_harita_AI1_X7.py",
        "tests/test_xai_termal_HEDEF_tahminle_uyusur_AI1_X1.py",
        "tests/test_xai_termal_hedef_iddiasi_SINIF_DUYARSIZ_yontemde_AII_3_1.py",
        "tests/test_xai_yolo_TESPIT_hedefli_cam_AI1_X2_X3.py",
        "tests/test_xai_yolo_cam_ESIK_canli_tespitle_ayni_AII_3_4.py",
    }
)


def kapsam(nodeid: str) -> str:
    """Zamanlama birimi: `xdist_group` işaretli test → grup adı (xdist'in `@grup` soneki), ağır model dosyası → `AGIR`,
    diğer işaretsiz → dosya yolu."""
    if nodeid.rfind("@") > nodeid.rfind("]"):  # parametre kimliğindeki '@' grup soneki sayılmaz (xdist ile aynı ölçüt)
        return nodeid.split("@")[-1]
    dosya = nodeid.split("::", 1)[0]
    return AGIR if dosya in AGIR_MODEL_DOSYALARI else dosya


def zamanlayici(config, log):
    """`--dist loadgroup` ise dosya birimli grup zamanlayıcısı; değilse None (xdist kendi varsayılanını seçer)."""
    if config.getvalue("dist") != "loadgroup":
        return None
    from xdist.scheduler import LoadGroupScheduling

    class DosyaGrubuZamanlayici(LoadGroupScheduling):
        def _split_scope(self, nodeid: str) -> str:
            return kapsam(nodeid)

    return DosyaGrubuZamanlayici(config, log)
