# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""B4 — `TreatmentHistoryDB` BOLUNMUS KALIR (2026-09-18).

Denetim B4'un GERCEK olcutu satir sayisi DEGILDI. `api_server.py` 5.135 satir ama kodu 3.530;
fark yorumlar ve bu depoda yorumlar OZELLIKTIR (denetim gecmisini tasirlar). Gercek sorun
`TreatmentHistoryDB`nin TEK SINIFTA 93 metot tasimasiydi: seans yasam dongusu + bobin kosusu
+ sensor telemetrisi + AI gecmisi + denetim izi + outbox + sema gocu + PII redaksiyonu.

Bes kume KARISIM (mixin) modullerine ayrildi (93 -> 54 metot, 3530 -> 2446 satir):

    database/thdb_outbox.py       OutboxKarisimi       outbox_messages
    database/thdb_denetim.py      DenetimKarisimi      audit_events
    database/thdb_ai_gecmisi.py   AiGecmisiKarisimi    ai_analyses
    database/thdb_telemetri.py    TelemetriKarisimi    session_coil_runs · sensor_*
    database/thdb_pii.py          PiiKarisimi          PII redaksiyonu / KVKK

⚠️ NEDEN KARISIM, ISBIRLIKCI NESNE DEGIL: `get_treatment_db(...)` urunun her yerinden
aliniyor ve metotlar DOGRUDAN cagriliyor. Isbirlikciye cevirmek (`db.outbox.enqueue(...)`)
tum cagri yerlerini degistirirdi — genis yuzeyli ve davranis-koruyan OLMAYAN bir degisiklik.
Karisim GENEL API'yi BIREBIR korur: ayni nesne, ayni metot adlari, ayni `self`.

BU KAPININ ISI — iki yonlu:
  1. Kumeler GERI TASINMASIN: her karisim modulu var olmali ve sinifin tabanlarinda olmali.
  2. Sinif GERI SISMESIN: yeni is hep "ana sinifa bir metot daha" diye eklenirse bir yil
     sonra yine 93 metot olur. Ust sinir, bugunku sayinin biraz ustunde.

⚠️ KAPI DAVRANIS OLCMEZ. Davranisi TAM SUIT + 48 urun senaryosu olcer; burasi yalnizca
BOLMENIN YERINDE KALDIGINI kilitler.
"""

from __future__ import annotations

import ast
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
ANA = KOK / "database" / "treatment_history_db.py"

#: Ayrilan kumeler — modul dosyasi -> karisim sinifi.
KARISIMLAR = {
    "thdb_outbox.py": "OutboxKarisimi",
    "thdb_denetim.py": "DenetimKarisimi",
    "thdb_ai_gecmisi.py": "AiGecmisiKarisimi",
    "thdb_telemetri.py": "TelemetriKarisimi",
    "thdb_pii.py": "PiiKarisimi",
}

#: Bolme sonrasi ana sinifta 54 metot kaldi. Ust sinir bilincli olarak biraz ustunde:
#: normal bakim nefes alsin ama "her yeni is ana sinifa" egilimi KIRMIZI donsun.
UST_SINIR = 60


def _ana_sinif() -> ast.ClassDef:
    agac = ast.parse(ANA.read_text(encoding="utf-8"))
    c = next(
        (n for n in ast.walk(agac) if isinstance(n, ast.ClassDef) and n.name == "TreatmentHistoryDB"),
        None,
    )
    assert c is not None, "TreatmentHistoryDB sinifi YOK — dosya yapisi degismis, kapi guncellenmeli"
    return c


def test_KRITIK_karisim_modulleri_DURUYOR():
    """Modul dosyasi + icindeki karisim sinifi yerinde mi."""
    eksik = []
    for dosya, sinif in KARISIMLAR.items():
        p = KOK / "database" / dosya
        if not p.is_file():
            eksik.append(f"{dosya} (DOSYA YOK)")
            continue
        agac = ast.parse(p.read_text(encoding="utf-8"))
        if not any(isinstance(n, ast.ClassDef) and n.name == sinif for n in ast.walk(agac)):
            eksik.append(f"{dosya} icinde {sinif} YOK")
    assert not eksik, (
        f"B4 bolmesi GERI ALINMIS: {eksik}. Kumeler ana sinifa geri tasindiysa denetim B4 "
        "yeniden acilir — once bu kapiyi bilincli olarak guncelleyin."
    )


def test_KRITIK_ana_sinif_karisimlari_DEVRALIYOR():
    """⚠️ Modulun var olmasi YETMEZ — sinif onlari TABAN olarak almali.

    Modul dursun ama `class TreatmentHistoryDB:` tabansiz kalsin: o zaman 39 metot URUNDEN
    KAYBOLUR. Capa bu yuzden dosya varligina degil, TABAN LISTESINE pinli.
    """
    c = _ana_sinif()
    tabanlar = {getattr(b, "id", getattr(b, "attr", None)) for b in c.bases}
    eksik = sorted(set(KARISIMLAR.values()) - tabanlar)
    assert not eksik, (
        f"ana sinif su karisimlari DEVRALMIYOR: {eksik} (bugunku tabanlar: {sorted(x for x in tabanlar if x)}). "
        "Modul dursa bile metotlar nesnede OLMAZ."
    )


def test_KRITIK_ana_sinif_GERI_SISMIYOR():
    """Yeni is hep ana sinifa eklenirse bolme bir yil icinde anlamini yitirir."""
    c = _ana_sinif()
    n = sum(1 for x in c.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)))
    assert n <= UST_SINIR, (
        f"TreatmentHistoryDB {n} metoda cikti (ust sinir {UST_SINIR}; B4 bolmesi 93'ten 54'e "
        "indirmisti). Yeni islevi ILGILI KARISIMA ekleyin ya da yeni bir karisim acin; sinirı "
        "yukseltmek son care ve bilincli bir karar olmali."
    )


def test_KARSIT_KANIT_karisimlar_GERCEKTEN_metot_tasiyor():
    """⚠️ Bos karisim sinifi kapiyi yesil birakirdi — icleri dolu mu?

    Bolmenin anlami metotlarin TASINMASIYDI; bos bir `class OutboxKarisimi: pass` da
    yukaridaki iki kapiyi gecerdi.
    """
    bos = []
    for dosya, sinif in KARISIMLAR.items():
        p = KOK / "database" / dosya
        if not p.is_file():
            continue
        agac = ast.parse(p.read_text(encoding="utf-8"))
        c = next((n for n in ast.walk(agac) if isinstance(n, ast.ClassDef) and n.name == sinif), None)
        if c is None:
            continue
        n = sum(1 for x in c.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)))
        if n < 3:
            bos.append(f"{sinif}={n} metot")
    assert not bos, (
        f"karisim(lar) BOSALMIS: {bos}. Metotlar ana sinifa geri tasinmis olabilir — "
        "bolme kagit uzerinde duruyor ama gercekte yok."
    )
