# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""LAUNCHER PROFİL HARİTASI ↔ PAKET LİSTESİ SENKRON — denetim 2026-08-28 #06.

ÖLÇÜLEN ARIZA. `launcher/core/src/install.rs::infer_profiles_from_disk`, `ai_models` altındaki
BİRİNCİ seviye dizin adını profil sanıyordu. Gerçek sevk düzeni ise
`ai_models/ai_hub/<modül>/...` (make_model_zip.py her girdiyi `f"ai_models/{rel}"` yazar ve
`rel` daima `ai_hub/` ile başlar; yayındaki `vet.zip` merkezî dizininde doğrulandı).

Sonuç: gerçek bir kurulumda çıkarım `["ai_hub"]` dönüyordu ve `repair()`
`UnknownProfile { profile: "ai_hub" }` ile İNDİRME BAŞLAMADAN düşüyordu. Kullanıcı "Onar"a
basınca "eski kurulum algılandı (1 profil)" ardından *"'ai_hub' profili manifest'te yok"*
görüyordu — bozuk model paketi olan klinik Onar'la kurtarılamıyordu.

⚠️ 2026-08-04 P3 düzeltmesinin kapısı bu hatayı GÖREMİYORDU: fixture'ı `ai_models/home/` diye
ELLE uyduruyordu — üretimde hiç oluşmayan bir düzen. Kapı, arıza canlıyken yeşil kalıyordu.

Bu dosya Rust tarafındaki `PROFIL_MODULLERI` tablosunun `build_tools/make_model_zip.py`'deki
paket listeleriyle senkron kalmasını sağlar: yeni bir AI modülü bir profile eklenip Rust tablosu
güncellenmezse, o modülü içeren kurulumda "Onar" yine eksik profil çıkarır.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_INSTALL_RS = _KOK / "launcher" / "core" / "src" / "install.rs"


def _paket_haritasi() -> dict[str, str]:
    """make_model_zip.py::PROFILLER + PARCALAR → {modül: profil} (TEK KAYNAK)."""
    sys.path.insert(0, str(_KOK / "build_tools"))
    try:
        mmz = __import__("make_model_zip")
    except Exception as e:  # pragma: no cover
        pytest.skip(f"make_model_zip içe aktarılamadı ({e})")

    harita: dict[str, str] = {}
    gruplar = list(getattr(mmz, "PROFILLER", {}).items())
    # `research-2` ayrı bir profil DEĞİL, research'ün parçasıdır.
    gruplar += [(ad.split("-")[0], yollar) for ad, yollar in getattr(mmz, "PARCALAR", {}).items()]
    for profil, yollar in gruplar:
        for yol in yollar:
            parcalar = yol.split("/")
            if len(parcalar) >= 2 and parcalar[0] == "ai_hub":
                harita.setdefault(parcalar[1], profil)
    return harita


def _rust_haritasi() -> dict[str, str]:
    """install.rs::PROFIL_MODULLERI tablosunu oku (Rust derlemeden)."""
    metin = _INSTALL_RS.read_text(encoding="utf-8")
    m = re.search(r"pub const PROFIL_MODULLERI:[^=]*=\s*\[(.*?)\];", metin, re.DOTALL)
    assert m, "install.rs içinde PROFIL_MODULLERI tablosu bulunamadı (çıpa kaymış olabilir)"
    ciftler = re.findall(r'\("([^"]+)",\s*"([^"]+)"\)', m.group(1))
    assert ciftler, "PROFIL_MODULLERI tablosu boş okundu"
    return dict(ciftler)


def test_harita_okunabiliyor():
    """Kapının kendisi çalışıyor mu."""
    assert len(_paket_haritasi()) >= 10
    assert len(_rust_haritasi()) >= 10


def test_KRITIK_rust_tablosu_paket_listesiyle_AYNI():
    """Her AI modülü, paketlendiği profile eşlenmeli — yoksa 'Onar' eksik profil çıkarır."""
    paket = _paket_haritasi()
    rust = _rust_haritasi()

    eksik = {m: p for m, p in paket.items() if m not in rust}
    fazla = {m: p for m, p in rust.items() if m not in paket}
    yanlis = {m: (rust[m], p) for m, p in paket.items() if m in rust and rust[m] != p}

    assert not eksik, (
        f"Bu modüller paketlere giriyor ama launcher tablosunda YOK: {eksik}. "
        f"Kurulumda o modül varsa 'Onar' profili çıkaramaz."
    )
    assert not fazla, f"Launcher tablosunda paketlerde olmayan modüller var: {fazla}"
    assert not yanlis, f"Profil eşlemesi YANLIŞ (rust≠paket): {yanlis}"


def test_KRITIK_rust_tablosu_uzunlugu_bildirimle_TUTARLI():
    """`[(&str, &str); N]` dizi boyutu gerçek girdi sayısıyla uyuşmalı — uyuşmazsa Rust
    derlenmez, ama hatayı build'e bırakmak yerine burada söyleyelim."""
    metin = _INSTALL_RS.read_text(encoding="utf-8")
    m = re.search(r"pub const PROFIL_MODULLERI:\s*\[\(&str,\s*&str\);\s*(\d+)\]", metin)
    assert m, "PROFIL_MODULLERI bildirimi okunamadı"
    assert int(m.group(1)) == len(_rust_haritasi()), (
        f"bildirilen boyut {m.group(1)} ≠ gerçek girdi sayısı {len(_rust_haritasi())}"
    )


def test_KRITIK_profil_adlari_manifest_anahtarlariyla_AYNI():
    """Sağdaki adlar manifest `models` anahtarı olmalı; değilse UnknownProfile geri gelir."""
    import json

    manifest = _KOK / "pemf-app-packages" / "manifest.json"
    if not manifest.is_file():
        pytest.skip("manifest.json yok (paketleme yapılmamış)")
    anahtarlar = set(json.loads(manifest.read_text(encoding="utf-8")).get("models", {}))
    profiller = set(_rust_haritasi().values())
    assert profiller <= anahtarlar, (
        f"Launcher tablosunda manifest'te olmayan profil adı var: {profiller - anahtarlar}. "
        f"repair() bunlarda UnknownProfile ile düşer (bulgunun ta kendisi)."
    )


def test_duz_profil_adlari_da_taniniyor():
    """Geriye uyum: doğrudan `ai_models/<profil>/` düzeni de kabul edilmeli."""
    metin = _INSTALL_RS.read_text(encoding="utf-8")
    m = re.search(r"fn dizin_adini_profile_cevir[^{]*\{(.*?)\n\}", metin, re.DOTALL)
    assert m, "dizin_adini_profile_cevir bulunamadı"
    for profil in ("home", "vet", "research"):
        assert f'"{profil}"' in m.group(1), f"düz profil adı '{profil}' tanınmıyor"


def test_KRITIK_ai_hub_ADI_PROFIL_SAYILMIYOR():
    """Bulgunun özü: 'ai_hub' bir profil DEĞİLDİR, kapsayıcı dizindir."""
    assert "ai_hub" not in _rust_haritasi(), "'ai_hub' profil tablosuna girmiş — repair() yine UnknownProfile ile düşer"
    paket = _paket_haritasi()
    assert "ai_hub" not in paket, "paket listesinden 'ai_hub' modül gibi okunmuş (ayrıştırma hatası)"


def test_ayristirma_gercekten_calisiyor_karsit_kanit():
    """Karşıt-kanıt: kapı boş kümeleri karşılaştırıp sahte yeşil vermiyor."""
    paket = _paket_haritasi()
    assert "em_kedi" in paket and paket["em_kedi"] == "vet", f"beklenen bilinen eşleme yok: {paket.get('em_kedi')}"
    assert "cat_disease" in paket and paket["cat_disease"] == "home"


def test_install_rs_ast_benzeri_cipa_saglam():
    """`PROFIL_MODULLERI` doğrudan `infer_profiles_from_disk` tarafından kullanılmalı;
    tablo var ama kullanılmıyorsa düzeltme etkisizdir (zayıf-çıpa dersi)."""
    metin = _INSTALL_RS.read_text(encoding="utf-8")
    i = metin.find("fn dizin_adini_profile_cevir")
    assert i != -1
    govde = metin[i : i + 800]
    assert "PROFIL_MODULLERI" in govde, "çevirici tabloyu KULLANMIYOR — tablo süs olur"
    j = metin.find("pub fn infer_profiles_from_disk")
    assert j != -1
    assert "dizin_adini_profile_cevir" in metin[j : j + 2000], (
        "infer_profiles_from_disk çeviriciyi çağırmıyor — düzeltme bağlanmamış"
    )
