# -*- coding: utf-8 -*-
"""D2.28 (B-3.68) — seçili-seans PDF'i `session_ids`'i SQL'e geçirir; en yeni N dışında kalan açıkça istenen seans rapordan DÜŞMEZ.

ÖLÇÜLEN KUSUR (DENETIM-03 B-3.68): `PDFReportGenerator._fetch_sessions` istenen kimlikleri SQL'e geçirmeden geçmişin en yeni
`_HISTORY_FETCH_LIMIT` (50.000) seansını çekip Python'da eşliyordu: daha eski bir seans seçilince rapora GİRMİYOR, "Toplam Seans: N" ile
istatistik sayısı çelişiyor, uç 200 dönüyordu (tıbbi rapor bütünlüğü). Yan fayda: her raporda tüm geçmiş belleğe çekilmez.
APARAT: gerçek `TreatmentHistoryDB` (5 seans), gerçek `PDFReportGenerator`; sınır sabiti 3'e yamalı (ölçek küçültme) → en eski seans
"en yeni N"in DIŞINDA. PDF metni PyMuPDF ile okunur.
"""

from __future__ import annotations

from pathlib import Path

import capraz
import pytest

fitz = capraz.paket_yoksa_atla("fitz", sebep="PyMuPDF yok -> PDF metni cikarilamaz")


@pytest.fixture
def o(tmp_path, monkeypatch):
    from database import sqlcipher_util as su
    from utils import pdf_report_generator as prg

    # ⚠️ Fabrika ve sınıf ÜRETİCİNİN gördüğü modülden alınır. Kümede `database.treatment_history_db`'yi `sys.modules`'tan silen bir
    # test (test_anahtar_uyusmazligi_karantina) önce koşarsa burada yeniden içe aktarılan ad YENİ modülün tekilini, üretici ESKİ
    # modülünkini görür → iki ayrı DB örneği (2-D birikimli kümede ölçüldü: 3 ERROR, aşağıdaki aparat iddiası yakaladı).
    get_treatment_db = prg.get_treatment_db
    TreatmentHistoryDB = get_treatment_db.__globals__["TreatmentHistoryDB"]

    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    monkeypatch.setattr(su, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.setattr(TreatmentHistoryDB, "_get_sqlcipher_key_legacy", lambda self: "")
    kok = tmp_path / "pdf"
    tdb = get_treatment_db(kok)
    ids = []
    for ad in ("EnEskiBoncuk", "Pamuk", "Tarcin", "Zeytin", "EnYeniMia"):
        sid = tdb.start_session(treatment_mode="Manuel", patient_name=ad)
        tdb.end_session(sid, duration_minutes=5)
        ids.append(sid)
    monkeypatch.setattr(prg, "_HISTORY_FETCH_LIMIT", 3)
    uretici = prg.PDFReportGenerator(kok)
    assert uretici.db is tdb, "aparat: üretici başka DB örneğine bakıyor"
    try:
        yield type("O", (), {"tdb": tdb, "ids": ids, "uretici": uretici, "kok": tmp_path})
    finally:
        tdb.close()


def _metin(yol) -> str:
    with fitz.open(str(yol)) as d:
        return "\n".join(s.get_text() for s in d)


def test_KRITIK_D228_EN_YENI_N_disindaki_secili_seans_PDFte_BULUNUR(o):
    cikti = o.uretici.generate_session_report(session_ids=[o.ids[0]], output_path=str(o.kok / "eski.pdf"))
    metin = _metin(cikti)
    assert "EnEskiBoncuk" in metin, (
        "açıkça seçilen (en yeni N dışındaki) seans PDF raporuna GİRMEDİ — istenen tıbbi kayıt rapordan sessizce düştü"
    )


def test_KRITIK_D228_secili_seans_kimlikleri_SQL_sorgusuna_GECER(o, monkeypatch):
    cagrilar = []
    gercek = o.tdb.get_session_history

    def _kaydet(*a, **k):
        cagrilar.append(k)
        return gercek(*a, **k)

    monkeypatch.setattr(o.tdb, "get_session_history", _kaydet)
    o.uretici.generate_session_report(session_ids=[o.ids[1], o.ids[3]], output_path=str(o.kok / "iki.pdf"))
    assert cagrilar, "aparat: geçmiş sorgusu hiç çağrılmadı"
    assert all(sorted(k.get("session_ids") or []) == sorted([o.ids[1], o.ids[3]]) for k in cagrilar), (
        f"seçili kimlikler SQL'e geçmiyor (tüm geçmiş çekilip Python'da eşleniyor): {cagrilar}"
    )


def test_KARSIT_D228_rapor_YALNIZ_secilen_seanslari_icerir_sira_korunur(o):
    cikti = o.uretici.generate_session_report(session_ids=[o.ids[4], o.ids[2]], output_path=str(o.kok / "secili.pdf"))
    metin = _metin(Path(cikti))
    assert "EnYeniMia" in metin and "Tarcin" in metin
    assert "Pamuk" not in metin and "EnEskiBoncuk" not in metin
