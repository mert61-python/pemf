# -*- coding: utf-8 -*-
# Author: mertaygn
"""SEANS DURUMU DIŞA AKTARIMDA TÜRKÇE — sahip bildirimi 2026-09-12.

===============================================================================
NE OLDU
===============================================================================
Sahip: "bu csv de tamamlandı yazmalı ingilizce yazıyor completed onu düzelt."

Ekran durumu çeviriyordu (`STATUS_LABELS_TR`), CSV ham DB değerini yazıyordu. Aynı
kaydın Excel'deki dili ile ekrandaki dili FARKLIYDI.

===============================================================================
BU DOSYA NE ÖLÇER
===============================================================================
· CSV'nin Durum sütunu GERÇEKTEN Türkçe mi (uçtan uca, gerçek endpoint)
· DB'deki HAM değer bozulmadı mı (durum mantığı/sorgular İngilizce sabite bakıyor)
· Python ve TypeScript sözlükleri AYRIŞTI mı (iki dilde iki harita → sessiz sapma)
· ÜRETİMDE YAZILAN her durum çevrilebiliyor mu (EMERGENCY_STOPPED bu yüzden bulundu)
"""

from __future__ import annotations

import csv
import io
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

_TS = KOK / "apps" / "ui" / "src" / "screens" / "TreatmentHistoryScreen.tsx"
#: SON-O.1 (22-SON inceleme): seans detay modalının KENDİ haritası var — bu kapı yalnız geçmiş ekranını taradığı için modal üç üretim
#: durumunu (EMERGENCY_STOPPED / ABORTED_DUE_TO_POWER / HARDWARE_REJECTED) çeviremiyor, ham "Emergency_stopped" gösteriyordu.
_TS_MODAL = KOK / "apps" / "ui" / "src" / "components" / "domain" / "SessionDetailModal.tsx"


@pytest.fixture
def istemci():
    from fastapi.testclient import TestClient
    from servers import api_server

    with TestClient(api_server.app) as c:
        yield c


@pytest.fixture
def dolu_db(tmp_path):
    """İÇİNDE BİLİNEN DURUMLU seanslar olan izole bir geçmiş DB'si.

    ⚠️ `history_router._app_data_dir` modül seviyesinde çözülür (süreç boyunca TEK DB) →
    bağımlılık ezmeden bu kapı, daha önce koşan testlerin satırlarına bağlı olurdu.
    """
    from database.treatment_history_db import TreatmentHistoryDB
    from servers import api_server
    from servers.history_router import get_db

    kok = tmp_path / "durum_gecmisi"
    kok.mkdir(parents=True, exist_ok=True)
    db = TreatmentHistoryDB(kok)
    sid = db.start_session(treatment_mode="Manuel", patient_name="Mia")
    db.end_session(sid, session_status="completed")
    api_server.app.dependency_overrides[get_db] = lambda: db
    yield db, sid
    api_server.app.dependency_overrides.pop(get_db, None)


def _csv_satirlari(govde: bytes) -> list[list[str]]:
    metin = govde.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(metin)))


# ============================================================================
# 1. ⚠️ ASIL KAPI — CSV'DE DURUM TÜRKÇE
# ============================================================================


def test_KRITIK_CSV_durum_sutunu_TURKCE(istemci, dolu_db):
    """MUTASYON: `durum_etiketi(...)` sarmalını kaldır (ham `s.get(...)` bırak) → KIRMIZI.

    Sahadaki etki: sahibin bizzat bildirdiği arıza — Excel'de "completed".
    """
    y = istemci.get("/api/history/export_csv")
    assert y.status_code == 200, y.text
    satirlar = _csv_satirlari(y.content)
    basliklar = satirlar[0]
    i_durum = basliklar.index("Durum")
    degerler = [s[i_durum] for s in satirlar[1:] if s]
    assert degerler, "CSV veri satiri uretmedi -> kapi olcemez"
    assert "Tamamlandı" in degerler, f"Durum sutunu TURKCE degil: {degerler}"
    assert "completed" not in degerler, f"HAM INGILIZCE deger CSVde kaldi: {degerler}"


def test_KRITIK_HAM_deger_API_yanitinda_DEGISMEDI(istemci, dolu_db):
    """⚠️ KARŞIT KANIT: çeviri YALNIZ dışa aktarım sınırında olmalı.

    Durum mantığı (rozet rengi, KPI sorguları, `session_status == 'completed'`) İngilizce
    sabite bakar. Çeviri veri katmanına sızarsa rozet renkleri ve istatistikler SESSİZCE
    bozulurdu — CSV düzelirken ekran bozulurdu.

    MUTASYON: `get_session_history`/list ucunda da çevir → KIRMIZI.
    """
    kayitlar = istemci.get("/api/history/").json()
    assert isinstance(kayitlar, list) and kayitlar, kayitlar
    durumlar = {(k.get("session_status") or "") for k in kayitlar}
    assert "completed" in durumlar, f"HAM deger API yanitinda kaybolmus: {durumlar}"
    assert "Tamamlandı" not in durumlar, "ceviri VERI KATMANINA sizdi -> durum mantigi bozulur"


# ============================================================================
# 2. ⚠️ İKİ DİLDE İKİ HARİTA — SESSİZ SAPMA KAPISI
# ============================================================================


def _ts_haritasi(ts_yolu: Path = _TS) -> dict[str, str]:
    """`STATUS_ANAHTARLARI` gövdesini TS kaynağından ayıklar (yorumlar sökülür). I18N: değerler katalog ANAHTARIDIR → TR değeri katalogdan çözülür
    (ölçüt YER DEĞİŞTİRDİ, gevşemedi: ekrandaki Türkçe etiket ↔ Python `DURUM_ETIKETLERI`); EN değeri de dolu olmalı."""
    import i18n_yardimci as iy
    from c_soyucu import c_soy

    src = c_soy(ts_yolu.read_text(encoding="utf-8"))
    m = re.search(r"STATUS_ANAHTARLARI:\s*Record<string,\s*string>\s*=\s*\{(.*?)\};", src, re.S)
    assert m, "STATUS_ANAHTARLARI govdesi bulunamadi -> capa bayatladi"
    cift = dict(re.findall(r'(\w+)\s*:\s*"([^"]*)"', m.group(1)))
    tr, en = iy.katalog("arayuz", "tr"), iy.katalog("arayuz", "en")
    for k, anahtar in cift.items():
        assert str(en.get(anahtar, "")).strip(), f"{anahtar} EN degeri BOS"
    return {k: tr.get(anahtar, f"<katalogda yok: {anahtar}>") for k, anahtar in cift.items()}


def test_KRITIK_python_ve_TS_sozlukleri_AYNI():
    """⚠️ İki dilde iki harita var ve SESSİZCE ayrışır: biri yeni durumu çevirir, öbürü
    ham İngilizce bırakır. Sahip aynı kaydı ekranda Türkçe, Excel'de İngilizce görür —
    bu şikâyetin TAM KENDİSİ.

    MUTASYON: TS haritasından bir anahtar sil (ya da etiketini değiştir) → KIRMIZI.
    """
    from utils.seans_durum import DURUM_ETIKETLERI

    ts = _ts_haritasi()
    assert ts, "TS haritasi bos ayiklandi -> capa bayatladi"
    assert set(ts) == set(DURUM_ETIKETLERI), (
        f"anahtarlar AYRISTI. yalniz TS: {sorted(set(ts) - set(DURUM_ETIKETLERI))}, "
        f"yalniz PY: {sorted(set(DURUM_ETIKETLERI) - set(ts))}"
    )
    # I18N-P1: sunucu tablosu da katalog ANAHTARI saklar (arayüz `STATUS_ANAHTARLARI` deseni) → ölçüt GEVŞEMEDİ, yer değiştirdi:
    # iki taraftaki ÇÖZÜLEN Türkçe etiket aynı olmalı; İngilizce de iki tarafta dolu ve aynı.
    import i18n_yardimci as iy

    sv_tr, sv_en = iy.katalog("sunucu", "tr"), iy.katalog("sunucu", "en")
    ui_en = iy.katalog("arayuz", "en")
    py_tr = {k: sv_tr.get(DURUM_ETIKETLERI[k], f"<katalogda yok: {DURUM_ETIKETLERI[k]}>") for k in DURUM_ETIKETLERI}
    farkli = {k: (ts[k], py_tr[k]) for k in ts if ts[k] != py_tr[k]}
    assert not farkli, f"ayni durum IKI FARKLI Turkce etikete cevriliyor: {farkli}"
    for k, anahtar in DURUM_ETIKETLERI.items():
        assert str(sv_en.get(anahtar, "")).strip(), f"{anahtar} EN degeri BOS"
        assert sv_en[anahtar] == ui_en.get(f"seans.durum.{k}"), f"{k}: EN sunucu ≠ arayuz"


def test_KRITIK_SEANS_DETAY_MODALI_haritasi_da_python_ile_AYNI_SON_O1():
    """SON-O.1 (22-SON inceleme): seans detay modalının (`SessionDetailModal.tsx`) KENDİ `STATUS_ANAHTARLARI` haritası var; yukarıdaki kapı
    yalnız geçmiş ekranını taradığı için modal EMERGENCY_STOPPED / ABORTED_DUE_TO_POWER / HARDWARE_REJECTED'i çeviremiyor, "Durum" satırında
    ham "Emergency_stopped" gösteriyordu (2026-09-12 hatasının ikizi — iki dilde de).

    MUTASYON: modal haritasından bir anahtar sil → KIRMIZI."""
    from utils.seans_durum import DURUM_ETIKETLERI

    gecmis, modal = _ts_haritasi(_TS), _ts_haritasi(_TS_MODAL)
    assert modal, "modal haritasi bos ayiklandi -> capa bayatladi"
    assert set(modal) == set(DURUM_ETIKETLERI), (
        f"seans detay modali haritasi AYRISTI. yalniz modal: {sorted(set(modal) - set(DURUM_ETIKETLERI))}, "
        f"modalda EKSIK: {sorted(set(DURUM_ETIKETLERI) - set(modal))}"
    )
    assert modal == gecmis, (
        f"modal ile gecmis ekrani ayni durumu FARKLI etikete ceviriyor: {set(modal.items()) ^ set(gecmis.items())}"
    )


def test_KRITIK_URETIMDE_yazilan_her_durum_cevrilebiliyor():
    """⚠️ BU KAPI GERÇEK BİR BOŞLUK BULDU (2026-09-12): `EMERGENCY_STOPPED` ve
    `ABORTED_DUE_TO_POWER` üretimde YAZILIYOR ama iki haritada da YOKTU → acil
    durdurulmuş bir seans ekranda "Emergency_stopped" görünüyordu.

    Çıpa üretim kaynağına pinli: yeni bir durum sabiti eklenip haritalar unutulursa KIRMIZI.
    """
    from utils.seans_durum import DURUM_ETIKETLERI

    # ⚠️ D2.09 (B-10.253, 2026-10-06): bu kapı yalnız `treatment_history_db.py`yi tarıyordu; B4 bölmesinden
    # (2026-09-18) sonra `ABORTED_DUE_TO_POWER` / `active` / `completed` `thdb_*.py`de ve kapı 5 durumdan
    # yalnız 2'sini görüyordu → `thdb_seans.py`deki güç-kesintisi literali haritada OLMAYAN bir değere
    # çevrilince YEŞİL kaldı (ölçüldü). Artık TÜM tedavi DB modülleri taranır; parametre varsayılanı
    # (`session_status: str = "…"`) ve `session_status or '…'` biçimi de okunur.
    db_dizin = KOK / "apps" / "backend" / "database"
    yazilanlar = set()
    for yol in [db_dizin / "treatment_history_db.py", *sorted(db_dizin.glob("thdb_*.py"))]:
        src = yol.read_text(encoding="utf-8")
        # `session_status = 'X'` / `session_status TEXT DEFAULT 'X'` / `session_status: str = "X"` / sabit atamalari.
        yazilanlar |= set(
            re.findall(r"session_status\s*(?::\s*str\s*)?(?:TEXT DEFAULT|=)\s*['\"]([A-Za-z_]+)['\"]", src)
        )
        yazilanlar |= set(re.findall(r"session_status\s+or\s+['\"]([A-Za-z_]+)['\"]", src))
        yazilanlar |= set(re.findall(r'SEANS_DURUMU_[A-Z_]+\s*=\s*"([A-Za-z_]+)"', src))
    yazilanlar -= {""}
    eksik = sorted(d for d in yazilanlar if d.lower() not in DURUM_ETIKETLERI)
    assert not eksik, f"URETIMDE yazilan ama cevrilemeyen durum(lar): {eksik}"
    # Tarayıcının KAPSAMI (Ö.6): bugün üretimde yazıldığı bilinen durumların HEPSİNİ görmeli; görmüyorsa
    # literal başka bir yere taşınmıştır ve kapı sessizce daralmıştır (bölme sonrası tam bu oldu).
    bilinen = {"active", "completed", "ABORTED_DUE_TO_POWER", "EMERGENCY_STOPPED", "HARDWARE_REJECTED"}
    assert bilinen <= yazilanlar, (
        f"uretim durum tarayicisi KOR: gorulmeyen {sorted(bilinen - yazilanlar)} -> literal tasinmis, capa bayatladi"
    )


# ============================================================================
# 3. BİLİNMEYEN DURUM SİLİNMEZ
# ============================================================================


def test_bilinmeyen_durum_SILINMEZ_ham_deger_kalir():
    """Harita bayatlarsa hücre BOŞ kalmamalı: operatör "durum yok" sanardı."""
    from utils.seans_durum import durum_etiketi

    assert durum_etiketi("quantum_flux") == "Quantum_flux"
    assert durum_etiketi(None) == ""
    assert durum_etiketi("") == ""
    assert durum_etiketi("COMPLETED") == "Tamamlandı", "buyuk/kucuk harf duyarli olmamali"
