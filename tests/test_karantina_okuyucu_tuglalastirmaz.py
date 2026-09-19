# Author: mertaygn, cglrgrkn
"""KARANTINA: KISA ÖMÜRLÜ BİR OKUYUCU CİHAZI TUĞLALAŞTIRMAZ.

NE OLDU (2026-09-19'da ölçüldü). `test_anahtar_uyusmazligi_karantina` tam süitte ARALIKLI
düşüyordu; tek başına ve 44 dosyalık önekte hep geçiyordu. Aralıklı kırmızıyı kovalarken
altından ÜRÜN ARIZASI çıktı.

ÖLÇÜM (deterministik, bu dosyanın kendisi):

    dosyada `open(db, "rb")` AÇIKKEN  →  `karantinaya_al(...)` **None** döner
      → `TreatmentHistoryDB._init_database` / `PatientDatabase._init_database`
        `RuntimeError(... karantinaya ALINAMADI ...)` fırlatır
      → **BACKEND AÇILMAZ.**

SADECE OKUMA tutamacı yetiyor. Üründe tam bunu yapan bir daemon var:
`api_server._daily_maintenance_loop` günlük yedeği `shutil.copy2` ile alıyor — yani
`pemf_treatment_history.db`'yi AÇIYOR. Anahtar uyuşmazlığı (kaldır-yeniden-kur sonrası
yenilenen `pemf_secrets.json`) tam o ana denk gelirse, TUĞLALAŞMAYI ÖNLEMEK için yazılmış
kurtarma zarfı tuğlalaşmaya sebep oluyordu.

⚠️ ESKİ BÜTÇE YETMİYORDU: `_kilit_direncli_tasi` 4 × 0,25 sn = **0,75 sn** bekliyordu.
Docstring'i yalnız BU SÜRECİN kendi yetim SQLCipher tutamacını anlatıyor ve onu
`gc.collect()` çözüyor — ölçüldü: `gc.collect` tamamen devre dışıyken bile karantina
çalışıyor. Yani eski gerekçe doğru ama EKSİK; başka bir okuyucuyu kapsamıyordu.

Bütçe 24 × 0,25 sn = 6 sn'ye çıkarıldı. Açılışta en kötü durumda 6 sn gecikme,
AÇILMAMAKTAN kıyaslanamayacak kadar iyidir. Kalıcı bir okuyucu varsa yine düşer ve hata
mesajı operatöre ne yapacağını söyler — o davranış BİLEREK korunuyor.

⚠️ BU RİSK WINDOWS'A ÖZGÜ (CI'da ölçüldü, 2026-09-19). POSIX'te açık bir tutamaç
`rename`'i ENGELLEMEZ; Linux runner'da kalıcı okuyucuyla bile karantina BAŞARILI oldu ve
bu dosyanın ilk hâli orada kırmızı verdi. Windows'ta ise açık tutamaç `shutil.move`'u
`PermissionError`a düşürür. Saha makinesi Windows olduğu için risk GERÇEK; ama kilit
davranışını ölçen testler artık `win32`e pinli. Bütçeyi KAYNAKTAN ölçen test her
platformda koşar — asıl değişmez odur.

⚠️ BU KAPININ KAPSAMADIĞI ŞEY — `gc.collect()`. Mutasyonla ölçüldü (2026-09-19): o satır
KALDIRILINCA bu dosyanın dördü de YEŞİL kalıyor. Yani buradaki yeşil, `gc.collect()`in
gereksiz olduğu anlamına GELMEZ; o satır 2026-08-14 saha arızası için eklendi (bu süreç
kendi yetim SQLCipher tutamacını tutuyordu) ve bu makinede o koşul yeniden üretilemedi.
**Kapı yeşil diye o satırı silmeyin** — silen kişi bu kapıdan hiçbir uyarı almaz.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import sqlcipher_util as su  # noqa: E402

sqlcipher = su.import_sqlcipher()
pytestmark = pytest.mark.skipif(sqlcipher is None, reason="sqlcipher3 binding yok")

#: Okuyucunun tutamacı bırakması için geçen süre. ESKİ bütçenin (0,75 sn) ÜSTÜNDE, yenisinin
#: (6 sn) ALTINDA seçildi — böylece bu test eski koda karşı KIRMIZI, yeniye karşı YEŞİL.
OKUYUCU_SURESI_S = 1.5


def _sifreli_db_yaz(yol: Path) -> None:
    c = sqlcipher.connect(str(yol))
    c.execute("PRAGMA key='ESKI-ANAHTAR'")
    c.execute("CREATE TABLE t (v TEXT)")
    c.execute("INSERT INTO t VALUES ('eski-seans')")
    c.commit()
    c.close()


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="POSIX'te acik tutamac rename'i engellemez — kilit davranisi YALNIZ Windows'ta olculebilir",
)
def test_KRITIK_kisa_omurlu_OKUYUCU_karantinayi_dusurmez(tmp_path):
    """🔴 ASIL REGRESYON: günlük yedek kopyası karantinayı kilitlerse cihaz AÇILMAZ."""
    db = tmp_path / "pemf_treatment_history.db"
    _sifreli_db_yaz(db)

    biraktim = threading.Event()

    def _okuyucu():
        # `shutil.copy2`nin yaptığının aynısı: dosyayı OKUMAK için aç, bir süre tut, bırak.
        with open(db, "rb") as f:
            f.read(4096)
            time.sleep(OKUYUCU_SURESI_S)
        biraktim.set()

    t = threading.Thread(target=_okuyucu, name="sahte-gunluk-yedek", daemon=True)
    t.start()
    try:
        sonuc = su.karantinaya_al(db, logger=None)
    finally:
        t.join(timeout=OKUYUCU_SURESI_S + 5)

    assert biraktim.is_set(), "okuyucu tutamacı bırakmadı — test kurgusu bozuk"
    assert sonuc is not None, (
        f"{OKUYUCU_SURESI_S} sn tutamaç tutan bir OKUYUCU karantinayı düşürdü. Üründe bu, "
        "`RuntimeError(... karantinaya ALINAMADI ...)` demek → BACKEND AÇILMAZ. Kurtarma "
        "zarfının bütçesi kısa (bkz. `_kilit_direncli_tasi` deneme sayısı)."
    )
    assert Path(sonuc).exists(), "karantina dosyası yazılmamış"
    assert not db.exists(), "eski DB kenara alınmamış"


def test_KARSIT_KANIT_tutamac_YOKKEN_zaten_calisiyor(tmp_path):
    """Temel durum: kilit yoksa karantina anında olur (test boş geçmiyor)."""
    db = tmp_path / "pemf_treatment_history.db"
    _sifreli_db_yaz(db)
    basla = time.monotonic()
    sonuc = su.karantinaya_al(db, logger=None)
    assert sonuc is not None
    assert time.monotonic() - basla < 1.0, "kilit yokken beklememeli"


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="POSIX'te acik tutamac rename'i engellemez — bu sinir YALNIZ Windows'ta var",
)
def test_KARSIT_KANIT_KALICI_okuyucuda_HALA_duser(tmp_path):
    """⚠️ Bütçe DAVRANIŞI DEĞİŞTİRMİYOR: kalıcı kilitte hâlâ `None` döner.

    Bu bilinçli: dosya gerçekten kilitliyse sessizce "başardım" demek, açılamayan DB'nin
    üzerine temiz DB açmaya çalışmak demektir. Operatöre hata göstermek doğrudur. Bu test,
    bütçe büyütmesinin o sınırı GEVŞETMEDİĞİNİ kilitler.
    """
    db = tmp_path / "pemf_treatment_history.db"
    _sifreli_db_yaz(db)
    f = open(db, "rb")  # noqa: SIM115 — bilerek açık tutuluyor
    try:
        sonuc = su.karantinaya_al(db, logger=None)
    finally:
        f.close()
    assert sonuc is None, "kalıcı kilitte karantina BAŞARILI sayılamaz — sessiz veri riski"


def test_KARSIT_KANIT_butce_gercekten_genis(tmp_path):
    """Bütçe kaynakta da ölçülür: kısa bir okuyucuyu bekleyecek kadar deneme olmalı.

    Davranış testi yeterli görünse de, biri `bekleme_s`i düşürüp `deneme`yi artırırsa toplam
    bütçe sabit kalır ve davranış testi yine geçer. Burada TOPLAM süre kilitlenir.
    """
    import inspect

    imza = inspect.signature(su._kilit_direncli_tasi)
    deneme = imza.parameters["deneme"].default
    bekleme = imza.parameters["bekleme_s"].default
    toplam = deneme * bekleme
    assert toplam >= 4.0, (
        f"karantina bütçesi {toplam} sn — kısa bir yedek kopyası bile sığmaz. "
        "Eski değer 4 × 0,25 = 0,75 sn idi ve sahada tuğlalaşma riski taşıyordu."
    )


# ═════════════════════════════════════════════════════════════════════════════════════════
# İKİNCİ BÜTÇE — 2026-09-19'da AYRIŞMIŞ olduğu ÖLÇÜLDÜ
# ═════════════════════════════════════════════════════════════════════════════════════════
#
# Yukarıdaki düzeltme `_kilit_direncli_tasi`yi 0,75 sn → 6 sn yaptı ve 13 ardışık tam süit
# yeşil geçti. 14.'de KIRMIZI geldi — ama başka bir testte:
#
#     test_at_rest_encryption_rollout.py::test_KRITIK_mevcut_duz_metin_klinik_GOCER_ve_veri_KORUNUR
#     AssertionError: goc sirasinda SEANS kayboldu   (assert [] == ['GocenHasta'])
#
# TAM YIĞIN İZİ (kayıt bunu özellikle istiyordu; önceki iki düşüşte `tail` ile kesilmişti):
#     sqlcipher_util.py:618  os.remove(enc_tmp)  → PermissionError [WinError 32]  ← BAŞLATICI
#     sqlcipher_util.py:668  _tasi_yeniden_dene  → "5 denemede basarisiz"
#     → göç İPTAL (düz metin korundu — DOĞRU davranış)
#     → ama çağıran düz-metin DB'yi "yanlış anahtar" sayıp KARANTİNAYA aldı → geçmiş BOŞ göründü
#
# KÖK: aynı kural İKİ yerde, ayrı bütçelerle.
#     `_kilit_direncli_tasi`  24 × 0,25 = 6,0 sn   ← dün genişletildi
#     `_tasi_yeniden_dene`     5 × artan = 2,0 sn   ← DOKUNULMAMIŞTI
#     `os.remove(enc_tmp)`     korumasız            ← zincirin en zayıf halkası
# Bu deponun tekrar eden sınıfı: "aynı kural iki yerde → sessizce ayrışır".


def test_KRITIK_IKI_yardimci_AYNI_butceyi_okur():
    """🔴 ASIL REGRESYON: biri genişletilip diğeri unutulursa göç yolu kırılmaya devam eder."""
    import inspect

    t = inspect.signature(su._kilit_direncli_tasi).parameters
    y = inspect.signature(su._tasi_yeniden_dene).parameters
    tasi = t["deneme"].default * t["bekleme_s"].default
    dene = y["denemeler"].default * y["bekleme"].default

    assert tasi == dene, (
        f"iki taşıma yardımcısının bütçesi AYRIŞTI: _kilit_direncli_tasi={tasi} sn · "
        f"_tasi_yeniden_dene={dene} sn. 2026-09-19'da tam bu ayrışma göç yolunu kırdı."
    )
    assert tasi >= 4.0, f"ortak bütçe {tasi} sn — kısa bir kilit bile sığmaz"
    assert tasi == su._KILIT_BUTCESI_SN, (
        f"bütçe TEK KAYNAKTAN gelmiyor ({tasi} ≠ {su._KILIT_BUTCESI_SN}) — elle yazılmış değer var"
    )

    # ⚠️ DEĞER EŞİTLİĞİ YETMEZ — bir mutasyonla ölçüldü (K2, 2026-09-20): `deneme=8,
    # bekleme_s=0,75` de tam 6,0 eder ve yukarıdaki üç iddianın ÜÇÜ DE geçer. Ama değer
    # artık SABİTTEN gelmiyordur; sabit bir gün değişince sessizce AYRIŞIR — bu arızanın
    # ta kendisi. Bu yüzden varsayılanların SABİTİN ADI olduğu YAPISAL olarak pinlenir.
    for fn in (su._kilit_direncli_tasi, su._tasi_yeniden_dene):
        imza_satiri = inspect.getsource(fn).splitlines()[0]
        for sabit in ("_KILIT_DENEME", "_KILIT_BEKLEME_SN"):
            assert sabit in imza_satiri, (
                f"{fn.__name__} varsayılanı `{sabit}`den TÜRETİLMİYOR — elle yazılmış değer "
                f"bugün doğru olsa bile sabit değişince ayrışır:\n    {imza_satiri.strip()}"
            )


def test_KRITIK_silme_de_KILIT_DIRENCLI(tmp_path, monkeypatch):
    """`os.remove(enc_tmp)` ölçülen BAŞLATICIYDI ve hiç koruması yoktu."""
    import os as _os

    p = tmp_path / "x.enc.tmp"
    p.write_bytes(b"veri")

    cagri = {"n": 0}
    gercek = _os.remove

    def _once_kilitli(yol, *a, **k):
        cagri["n"] += 1
        if cagri["n"] <= 3:  # ilk üç deneme "kilitli"
            raise PermissionError(32, "kilitli")
        return gercek(yol, *a, **k)

    monkeypatch.setattr(su.os, "remove", _once_kilitli)
    assert su._kilit_direncli_sil(p) is True, "geçici kilit aşılamadı — tek deneme yapıyor olabilir"
    assert cagri["n"] == 4, f"beklenen 4 deneme, yapılan {cagri['n']}"
    assert not p.exists(), "dosya silinmedi"


def test_KRITIK_silme_KALICI_kilitte_FIRLATMAZ(tmp_path, monkeypatch):
    """Bütçe dolunca False döner — istisna fırlatıp göçü çökertmez.

    ⚠️ Bu dalın KOŞULDUĞU ölçülür: bu depoda "except dalına hiç uğranmıyor" arızası yaşandı.
    """
    p = tmp_path / "kalici.tmp"
    p.write_bytes(b"veri")

    def _hep_kilitli(yol, *a, **k):
        raise PermissionError(32, "kalici kilit")

    monkeypatch.setattr(su.os, "remove", _hep_kilitli)
    # Bütçeyi kısalt — gerçek 6 sn'yi süitte beklemeyelim; ÖLÇÜLEN şey DAVRANIŞ.
    monkeypatch.setattr(su, "_KILIT_DENEME", 2)
    monkeypatch.setattr(su, "_KILIT_BEKLEME_SN", 0.01)
    assert su._kilit_direncli_sil(p) is False, "kalıcı kilitte True döndü — çağıran yanlış ilerler"
    assert p.exists(), "dosya silinmiş görünüyor ama silinmemeliydi"


def test_KRITIK_goc_ENC_TMPyi_korumali_siliyor():
    """Yardımcı var ama çağrılmıyorsa hiçbir şey değişmemiştir — çağrıyı kaynağa pinle."""
    import inspect

    kaynak = inspect.getsource(su.migrate_to_encrypted_if_needed)
    kod = "\n".join(s.split("#")[0] for s in kaynak.splitlines())
    assert "_kilit_direncli_sil(enc_tmp" in kod, (
        "göç hâlâ çıplak `os.remove(enc_tmp)` kullanıyor — ölçülen başlatıcı açık"
    )
