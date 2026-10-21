# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""I18N-P1 (S-I18N-P1.1) · SUNUCU İLETİSİNİ ÖN EK / PARÇA İLE TANIYAN İKİ ARAYÜZ YERİ iki dilde çalışır.

Sunucu 503 / 428 / 422 gövdesi İSTEK DİLİNDE gelir (`X-PEMF-Dil`). Arayüz iki iletiyi METNİNE bakarak sınıflar:
  * `KIMLIK_DB_ARIZA_ONEKI` (+ `_EN`) — "Cihazın kimlik veritabanı okunamıyor" (OperatorContext 503 · ObservationNotesModal istemi): tanınmazsa arıza
    "operatörünüzü seçin" diye yanlış sınıflanır (kapı kararı sunucuda, FAIL-CLOSED — değişmez);
  * `TERMAL_UYUMSUZ_IZI` (+ `_EN`) — "termal kamera görüntüsüne benzemiyor" (canlı kare 422): tanınmazsa "termal kamerayı seçin" ipucu düşer.
Bu kapı, arayüzün iki dildeki işaretçilerinin sunucu ve arayüz kataloglarının İKİ DİLDEKİ değerleriyle HÂLÂ eşleştiğini kilitler: bir katalog
metni (ya da işaretçi) değişirse kırmızı olur. ⚠️ Beklenen dizgiler BURADA sabittir (üründen okunmaz).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

TR_ONEK = "Cihazın kimlik veritabanı okunamıyor"
EN_ONEK = "The device's identity database cannot be read"
TR_IZ = "termal kamera görüntüsüne benzemiyor"
EN_IZ = "does not look like a thermal camera image"


def _ts(rel: str) -> str:
    return (KOK / rel).read_text(encoding="utf-8")


def _sabit(kaynak: str, ad: str) -> str:
    m = re.search(rf'(?:export )?const {ad} = "(.+?)";', kaynak)
    assert m, f"{ad} sabiti bulunamadı"
    return m.group(1)


def _yaprak(katalog: dict, anahtar: str):
    for parca in anahtar.split("."):
        katalog = katalog[parca]
    return katalog


def _json(rel: str) -> dict:
    return json.loads((KOK / rel).read_text(encoding="utf-8"))


def test_arayuz_isaretcileri_iki_dilde_beklenen_dizgiyle_AYNI():
    ps = _ts("apps/ui/src/utils/patientScope.ts")
    assert _sabit(ps, "KIMLIK_DB_ARIZA_ONEKI") == TR_ONEK
    assert _sabit(ps, "KIMLIK_DB_ARIZA_ONEKI_EN") == EN_ONEK
    ck = _ts("apps/ui/src/utils/canliKare.ts")
    assert _sabit(ck, "TERMAL_UYUMSUZ_IZI") == TR_IZ
    assert _sabit(ck, "TERMAL_UYUMSUZ_IZI_EN") == EN_IZ


@pytest.mark.parametrize("dil,onek", [("tr", TR_ONEK), ("en", EN_ONEK)])
def test_kimlik_DB_arizasi_iletisi_sunucuda_ve_arayuzde_ON_EKLE_baslar(dil, onek):
    sunucu = _json(f"apps/backend/i18n/{dil}.json")
    assert _yaprak(sunucu, "kimlik.dbOkunamiyor").startswith(onek), (
        f"sunucu {dil}: 503 / 428 iletisi ön ekle başlamıyor"
    )
    arayuz = _json(f"apps/ui/src/i18n/{dil}/hasta.json")
    assert _yaprak(arayuz, "kimlik.dbOkunamiyor").startswith(onek), f"arayüz {dil}: istem metni ön ekle başlamıyor"


@pytest.mark.parametrize("dil,iz", [("tr", TR_IZ), ("en", EN_IZ)])
def test_termal_uyumsuz_iletisi_iki_dilde_iz_parcasini_ICERIR(dil, iz):
    sunucu = _json(f"apps/backend/i18n/{dil}.json")
    assert iz in _yaprak(sunucu, "ai.termal.uyumsuz"), f"sunucu {dil}: termal uyumsuz iletisi iz parçasını içermiyor"


@pytest.mark.parametrize("dil,onek", [("tr", TR_ONEK), ("en", EN_ONEK)])
def test_GERCEK_sunucu_islevleri_istek_dilinde_ON_EKLE_baslar_ve_iz_parcasini_icerir(dil, onek):
    from servers.auth import kimlik_db_okunamiyor_metni
    from utils import ceviri

    assert kimlik_db_okunamiyor_metni(dil).startswith(onek)
    iz = TR_IZ if dil == "tr" else EN_IZ
    assert iz in ceviri.t("ai.termal.uyumsuz", dil=dil)


def test_arayuz_tanima_islevleri_iki_dilde_kullanilir_ham_TR_on_ek_karsilastirmasi_KALMADI():
    oc = _ts("apps/ui/src/context/OperatorContext.tsx")
    assert "kimlikDbArizaMi(detay)" in oc and "detay.startsWith(KIMLIK_DB_ARIZA_ONEKI)" not in oc
    om = _ts("apps/ui/src/components/domain/ObservationNotesModal.tsx")
    assert "kimlikDbArizaMi(kimlikIstemi)" in om and "kimlikIstemi.startsWith(KIMLIK_DB_ARIZA_ONEKI)" not in om
    ck = _ts("apps/ui/src/utils/canliKare.ts")
    assert "detay.includes(TERMAL_UYUMSUZ_IZI) || detay.includes(TERMAL_UYUMSUZ_IZI_EN)" in ck
