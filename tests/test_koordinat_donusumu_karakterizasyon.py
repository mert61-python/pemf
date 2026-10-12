# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""FANTOM/PETRİ KOORDİNAT DÖNÜŞÜMÜ — yapısal kapılar (2026-09-08; D1.100 ile yenilendi 2026-10-02).

⚠️ D1.100 (B-5.16): bu dosyadaki KARAKTERİZASYON GOLDEN'I (R = I, t = (0, 0, 500) pozunda "bugün ne üretiyor"
tablosu) KALDIRILDI ve bir DOĞRULUK testiyle değiştirildi: `test_koordinat_donusumu_FIZIKSEL_poz_DOGRULUK_ve_RED.py`.
Golden'ın pozu kamerayı marker'ın ARKASINA koyuyordu (fiziksel değil) ve dönüşümün kamera orijinini döndürmeme
hatasını (fiziksel pozda ~1,5 m kayma) gizliyordu. "Sahadaki yatay düzlem (Y = −20 cm) sayısal olarak kötü
koşullanmış; sentetik ışınlarda kesişim 10⁶ mm'ye fırlıyor" ölçüm kaydı da aynı hatanın ürünüydü: düzeltilmiş
dönüşüm aynı düzlemi fiziksel pozda < 5 mm çözüyor (doğruluk testinin "yaml" kolu). Gerçek kabinde kabul (±2 cm,
VERIFICATION §15) ve A-17 yeniden ölçümü TEZGÂHTADIR (Oturum 13) — burada ölçüm uydurulmaz.

Dönüşüm değişince bunun SESSİZ olmaması hâlâ önemli: aynı fonksiyon AI Hub tek-foto analizlerini
(`/api/ai/vision/em_fantom`, `/api/ai/vision/em_petri`) ve Docker `ai_service`i de besler.

Girdiler SENTETİKTİR (ağırlık/fotoğraf gerekmez) → bu kapı CI'da da koşar.
"""

import numpy as np
import pytest
from kabin_fiziksel_poz import fiziksel_poz, genis_aci_ic_parametre, izdusur

_TOL_MM = 1e-6


@pytest.fixture()
def donusum():
    # AI-2 C6: v1 `phantom_cv` emekli → hocanın v3'ü (aynı `cv_ortak` gövdesi, aynı saha kabin çekirdeği).
    from ai_hub.inference_em_fantom.phantom_cv_v3 import coord_transform as ct
    from ai_hub.inference_em_fantom.phantom_cv_v3.cabin_config import load_cabin_config

    cfg = load_cabin_config(None)  # depoya gömülü kabin geometrisi (65x50x50)
    intr = genis_aci_ic_parametre(ct)
    poz, R_kk, C = fiziksel_poz(ct, cfg)
    return ct, cfg, intr, poz, R_kk, C


def test_KRITIK_marker_KABIN_rotasyonu_UYGULANIR(donusum, monkeypatch):
    """Karar #6: marker çerçevesinden kabin çerçevesine İŞARET/PERMUTASYON dönüşümü uygulanır. Marker arka duvarda
    (normal −Z) ve "üst" oku tavana baktığında beklenen matris diag(−1, +1, −1).

    ⚠️ KULLANIMI ölç, varlığı değil: matris doğruysa yetmez — dönüşüm ışına VE kamera orijinine (D1.100) uygulanmalı.
    Birim matrise çevrilince fiziksel pozdaki bilinen nokta artık doğru geri dönmemeli."""
    ct, cfg, intr, poz, R_kk, C = donusum
    from ai_hub.cv_ortak import coord_transform as ortak
    from ai_hub.cv_ortak.coord_transform import _marker_to_cabin_R

    beklenen_R = np.diag([-1.0, 1.0, -1.0])
    assert np.allclose(_marker_to_cabin_R(cfg), beklenen_R, atol=1e-9), (
        f"marker→kabin dönüşümü beklenen diag(-1,1,-1) değil: {_marker_to_cabin_R(cfg).tolist()} "
        "— marker arka duvarda (normal -Z) ve üst oku tavana bakıyor varsayımı bozulduysa "
        "KABIN_KURULUM_KILAVUZU ile birlikte gözden geçirin"
    )
    eksen = cfg.phantom_plate.hedef_duzlem_indeksi
    P = np.zeros(3)
    P[eksen] = cfg.phantom_plate.hedef_duzlem_mm
    px = izdusur(intr.K, R_kk, C, P)
    assert px is not None
    p = ct.pixel_to_cabin_mm(px, poz, intr, cfg)
    assert abs(p[eksen] - cfg.phantom_plate.hedef_duzlem_mm) < _TOL_MM, (
        "kesişim yapılandırılan hedef düzleminde değil — yaml `hedef_duzlem_eksen`/`hedef_duzlem_cm` ile kod ayrışmış olabilir"
    )
    assert np.linalg.norm(p - P) < 5.0

    monkeypatch.setattr(ortak, "_marker_to_cabin_R", lambda c: np.eye(3))
    try:
        bozuk = ct.pixel_to_cabin_mm(px, poz, intr, cfg)
    except ValueError:
        return  # birim matrisle kesişim geçersiz → dönüşüm KULLANILIYOR
    assert np.linalg.norm(bozuk - P) > 50.0, (
        "marker→kabin dönüşümü birim matrise çevrildiği hâlde sonuç aynı — dönüşüm UYGULANMIYOR"
    )


def test_KRITIK_iki_profil_AYNI_uygulamayi_kullanir(donusum):
    """Fantom ve petri AYNI koordinat dönüşümünü kullanmalı — ayrışırlarsa aynı kabinde
    FARKLI 3B koordinat üretirler ve bunu kimse fark etmez.

    ⚠️ ÖLÇÜT DEĞİŞTİ (A2, 2026-09-19). Bu test eskiden iki DOSYAYI `filecmp` ile
    karşılaştırıyordu ve kendi docstring'i *"tek kaynak yapılana kadar"* diyordu. Tek kaynak
    yapıldı: gövde `ai_hub/cv_ortak/coord_transform.py`de, profillerde ince kabuk var.
    Dosya karşılaştırması artık YANLIŞ ÖLÇÜT olurdu — iki kabuk de aynı ama bu, gövdenin
    aynı olduğunu KANITLAMAZ.

    Yeni ölçüt daha güçlü: iki profilin gördüğü fonksiyon NESNESİ aynı mı. Aynı nesne
    ayrışamaz — dosya kopyası ayrışabilirdi.
    """
    from ai_hub.inference_em_fantom.phantom_cv_v3 import coord_transform as f_ct
    from ai_hub.inference_petri_dish.petri_cv_v2 import coord_transform as p_ct

    ortak = [ad for ad in dir(f_ct) if not ad.startswith("_") and callable(getattr(f_ct, ad, None))]
    assert len(ortak) >= 3, f"kabuk çok az sembol sunuyor ({ortak}) — yeniden-dışa-aktarım kırılmış"

    ayrisan = [ad for ad in ortak if getattr(f_ct, ad, None) is not getattr(p_ct, ad, None)]
    assert not ayrisan, (
        f"fantom ve petri AYNI nesneyi görmüyor: {ayrisan} — koordinat dönüşümü yeniden "
        "kopyalanmış olabilir; aynı kabinde farklı 3B koordinat üretirler"
    )


def test_KRITIK_hedef_duzlemi_YAPILANDIRILABILIR(donusum):
    """Karar #6: fantom/petri kabinde YATAY duruyorsa doğru kesişim düzlemi "Y = taban + kalınlık" olmalı; eski kod
    her zaman kabin Z=0 (DİKEY orta düzlem) ile kesişiyordu. Kodun yapılandırılan değeri GERÇEKTEN kullandığı ölçülür
    (fiziksel pozda, o düzlemdeki bilinen nokta). MUTASYON: kesişimi sabit `plate_z`/eksen 2'ye döndürün → KIRMIZI."""
    ct, cfg, intr, poz, R_kk, C = donusum

    cfg.phantom_plate.hedef_duzlem_eksen = "Y"
    cfg.phantom_plate.hedef_duzlem_cm = -24.0
    Py = np.array([0.0, -240.0, 0.0])
    yatay = ct.pixel_to_cabin_mm(izdusur(intr.K, R_kk, C, Py), poz, intr, cfg)
    assert abs(yatay[1] - (-240.0)) < 1e-6 and np.linalg.norm(yatay - Py) < 5.0, (
        f"yatay düzlem yapılandırması uygulanmadı: {np.round(yatay, 1).tolist()} (beklenen {Py.tolist()}) — "
        "yatay yerleşimde hedef kabin ortasındaki dikey perdeye yansıtılır ve konum yanlış çıkar"
    )

    cfg.phantom_plate.hedef_duzlem_eksen = "Z"
    cfg.phantom_plate.hedef_duzlem_cm = 0.0
    Pz = np.array([0.0, 0.0, 0.0])
    dikey = ct.pixel_to_cabin_mm(izdusur(intr.K, R_kk, C, Pz), poz, intr, cfg)
    assert abs(dikey[2] - 0.0) < 1e-6 and np.linalg.norm(dikey - Pz) < 5.0, (
        "eksen 'Z' seçilince dikey orta düzlem kullanılmıyor"
    )
    assert not np.allclose(yatay, dikey), "iki düzlem aynı sonucu veriyor — yapılandırma etkisiz"


def test_KRITIK_yaml_ve_parser_hedef_duzlemini_TASIYOR():
    """Yaml'a alan eklemek yetmez: ayrıştırıcı onu OKUMALI (bilinmeyen anahtar sessizce yok
    sayılır). MUTASYON: parser satırını silin → KIRMIZI.

    ⚠️ ÇIPA TEK KAYNAĞA TAŞINDI (A2, 2026-09-19). Eskiden "İki kopya da taşımalı" diyordu ve
    iki `cabin_config.py`yi ayrı ayrı okuyordu. Ayrıştırıcı artık TEK yerde
    (`ai_hub/cv_ortak/cabin_config.py`); profil dosyaları ince kabuk. YAML'lar ise
    profil-başına AYRI kalmaya devam ediyor, o yüzden onlar hâlâ ayrı ayrı ölçülür.
    """
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]

    cfg_src = (kok / "ai_hub" / "cv_ortak" / "cabin_config.py").read_text(encoding="utf-8")
    assert 'plate_r.get("hedef_duzlem_eksen"' in cfg_src, (
        "ortak ayrıştırıcı yaml'daki hedef düzlemini OKUMUYOR — alan sessizce yok sayılır"
    )
    assert "hedef_duzlem_mm" in cfg_src and "hedef_duzlem_indeksi" in cfg_src, (
        "ortak yapılandırma sınıfı düzlem yardımcılarını sunmuyor"
    )

    for kok_dizin, yaml_adi in (
        ("inference_em_fantom/phantom_cv_v3", "cabin_config_v3.yaml"),
        ("inference_petri_dish/petri_cv_v2", "cabin_config_v2.yaml"),
    ):
        yaml_src = (kok / "ai_hub" / kok_dizin / yaml_adi).read_text(encoding="utf-8")
        assert "hedef_duzlem_eksen" in yaml_src, f"{kok_dizin}: yaml hedef düzlemi taşımıyor"
        # ⚠️ Kabuk gerçekten ORTAK ayrıştırıcıya bağlı mı — yoksa yukarıdaki iddia boşa düşer.
        kabuk = (kok / "ai_hub" / kok_dizin / "cabin_config.py").read_text(encoding="utf-8")
        assert "cv_ortak" in kabuk, f"{kok_dizin}: kabuk ortak ayrıştırıcıya bağlı değil"
