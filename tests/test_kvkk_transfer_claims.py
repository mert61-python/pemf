# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KVKK METNİ İLE YAZILIM AYNI ŞEYİ SÖYLÜYOR MU (2026-08-09 denetimi, Tier 3).

ARIZA: KVKK Aydınlatma Metni'nde **yurt dışına aktarım başlığı yoktu**. Oysa hesap verileri
(Supabase Auth) ve cihaz kayıt defteri (60 sn'de bir heartbeat) fiilen yurt dışındaki bir
işleyiciye gidiyor, site de yurt dışında barındırılıyor. Aktarımın varlığını söylemeyen bir
aydınlatma metni, ilgili kişiyi KVKK m.11'de tanınan "aktarıldığı üçüncü kişileri bilme"
hakkından yoksun bırakır.

⚠️ Bu dosya HUKUKİ NİTELEME YAPMAZ. Yaptığı tek şey, metindeki **ölçülebilir** iddiaların
koddaki davranışla uyuşup uyuşmadığını sınamaktır. Hukuki metin ile yazılım ayrışırsa ikisinden
biri yanlıştır — ve hangi yönde ayrıştığı burada görünür.

Kilitlenen iddialar:
  1) "Hasta ve seans kayıtları yurt dışına aktarılmaz … varsayılan olarak kapalı"
     → `PEMF_CLOUD_PATIENT_SYNC` varsayılanı KAPALI olmalı.
  2) Metinde sayılan cihaz-kayıt alanları, gerçekten gönderilen alan kümesiyle örtüşmeli
     (yeni bir alan eklenip metne yazılmazsa, aydınlatma eksik kalır).
"""

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
LEGAL = KOK / "pemf-vet-web" / "src" / "pages" / "Legal.tsx"


@pytest.fixture(scope="module")
def metin():
    if not LEGAL.exists():
        pytest.skip("pemf-vet-web kaynagi yok")
    return LEGAL.read_text(encoding="utf-8")


# ── metin gerçekten aktarımı anlatıyor mu ───────────────────────────────────


def test_KRITIK_yurt_disina_aktarim_basligi_VAR(metin):
    assert "Yurt Dışına Aktarım" in metin, (
        "KVKK metninde yurt disina aktarim basligi YOK — fiili aktarim beyan edilmiyor"
    )


def test_aktarim_ALICILARI_adlandirilir(metin):
    bolum = metin.split("Yurt Dışına Aktarım", 1)[1].split("<H2>6.", 1)[0]
    for alici in ("Supabase", "Vercel", "iyzico"):
        assert alici in bolum, f"aktarim bolumunde alici '{alici}' adlandirilmamis"


def test_m9_dayanagi_ANILIR(metin):
    assert "m.9" in metin.split("Yurt Dışına Aktarım", 1)[1][:2000], "aktarim bolumu KVKK m.9'a atif yapmiyor"


# ── metin ile kod aynı şeyi mi söylüyor ─────────────────────────────────────


def test_KRITIK_hasta_bulut_syncı_GERCEKTEN_kapali():
    """Metin "hasta ve seans kayıtları yurt dışına aktarılmaz … varsayılan kapalı" diyor.
    Varsayılan bir gün açılırsa metin YANLIŞ BEYAN hâline gelir."""
    src = (KOK / "servers" / "sync_worker.py").read_text(encoding="utf-8")
    m = re.search(
        r'patient_sync_enabled\s*=\s*os\.environ\.get\(\s*"PEMF_CLOUD_PATIENT_SYNC"\s*,\s*"([^"]*)"\s*\)\s*==\s*"1"',
        src,
    )
    assert m, "PEMF_CLOUD_PATIENT_SYNC varsayilani okunamadi (kod degismis olabilir)"
    assert m.group(1) != "1", (
        "hasta/seans bulut sync'i VARSAYILAN ACIK olmus — KVKK metni 'aktarilmaz' diyor, "
        "yazilim aktariyor. Ikisinden biri duzeltilmeli."
    )


def test_KRITIK_hasta_syncı_KAPALIYKEN_RPC_YOLUNA_GIRILMEZ(monkeypatch):
    """Davranışsal kanıt (kaynak-metin değil): senkron döngüsünün bir turu koşturulur ve
    hasta/seans gönderme yollarına HİÇ girilmediği doğrulanır. Cihaz kayıt defteri yayını ise
    beklenen davranıştır — metin onu zaten beyan ediyor."""
    monkeypatch.delenv("PEMF_CLOUD_PATIENT_SYNC", raising=False)
    from servers import sync_worker

    w = sync_worker.CloudSyncWorker(supabase_url="", supabase_key="", interval_sec=1)
    assert w.patient_sync_enabled is False, "bayrak varsayilan ACIK"

    girilen = []
    monkeypatch.setattr(w, "_ensure_client", lambda: True)
    monkeypatch.setattr(w, "_publish_device_registry", lambda: (girilen.append("device"), w.stop_event.set(), True)[-1])
    monkeypatch.setattr(w, "_sync_patients", lambda *a: girilen.append("patients"))
    monkeypatch.setattr(w, "_sync_sessions", lambda *a: girilen.append("sessions"))
    # DB açılışları döngünün başında; gerçek dosyaya dokunmasın.
    monkeypatch.setattr(sync_worker, "get_patient_database", lambda *a, **k: object())
    monkeypatch.setattr(sync_worker, "get_treatment_db", lambda *a, **k: object())

    w._sync_loop()
    assert "patients" not in girilen and "sessions" not in girilen, (
        f"hasta/seans yoluna GIRILDI: {girilen} — KVKK metni 'aktarilmaz' diyor"
    )
    assert "device" in girilen, "cihaz kayit defteri yayini da durmus (uzaktan erisim kirilir)"


def test_bayrak_ACILINCA_hasta_yolu_calisir(monkeypatch):
    """Karşı-kanıt: test "hiç çağrılmıyor"u bayrak yüzünden mi yoksa yol ölü olduğu için mi
    görüyor? Bayrağı açınca yola girilmeli — yoksa üstteki test boş güvence olurdu."""
    monkeypatch.setenv("PEMF_CLOUD_PATIENT_SYNC", "1")
    from servers import sync_worker

    w = sync_worker.CloudSyncWorker(supabase_url="", supabase_key="", interval_sec=1)
    girilen = []
    monkeypatch.setattr(w, "_ensure_client", lambda: True)
    monkeypatch.setattr(w, "_publish_device_registry", lambda: True)
    monkeypatch.setattr(w, "_sync_patients", lambda *a: (girilen.append("patients"), w.stop_event.set()))
    monkeypatch.setattr(w, "_sync_sessions", lambda *a: girilen.append("sessions"))
    monkeypatch.setattr(sync_worker, "get_patient_database", lambda *a, **k: object())
    monkeypatch.setattr(sync_worker, "get_treatment_db", lambda *a, **k: object())

    w._sync_loop()
    assert "patients" in girilen, "bayrak acikken bile hasta yoluna girilmedi — test bos guvence"


def test_metindeki_cihaz_alanlari_GERCEKTE_gonderilenlerle_ortusur(metin):
    """Kayıt defterine yeni bir alan eklenip aydınlatma metnine yazılmazsa beyan eksik kalır.
    Alan → metinde geçmesi beklenen Türkçe karşılık."""
    src = (KOK / "servers" / "sync_worker.py").read_text(encoding="utf-8")
    gonderilen = set(re.findall(r'^\s{16}"([a-z_]+)":', src, re.M))
    bolum = metin.split("Yurt Dışına Aktarım", 1)[1].split("<H2>6.", 1)[0]

    karsilik = {
        "device_id": "cihaz kimliği",
        "name": "adı",
        "tunnel_url": "uzaktan erişim adresi",
        "local_ip": "yerel IP",
        "api_port": "port",
        "pairing_code": "eşleştirme kodu",
        "last_seen": "son görülme",
    }
    eksik = [a for a in karsilik if a in gonderilen and karsilik[a].lower() not in bolum.lower()]
    assert not eksik, (
        f"cihaz kayit defterinde gonderilen ama metinde anlatilmayan alan(lar): {eksik} — "
        "aydinlatma metni fiili islemeyi kapsamiyor"
    )
    # Sürüm alanları ayrı bir yardımcıdan gelir (`_surum_alanlari`); metin onları da anmalı.
    assert "sürüm" in bolum.lower(), "metin gonderilen yazilim surumlerinden hic soz etmiyor"


def test_saklama_suresi_metni_KODDAKI_varsayilanla_ayni(metin):
    """Metin "365 gün" diyor; kod başka bir varsayılan uygularsa klinik yanlış bilgilendirilir."""
    if "365" not in metin:
        pytest.skip("metinde somut sure yok")
    src = (KOK / "database" / "treatment_history_db.py").read_text(encoding="utf-8")
    assert "365" in src, "hukuki metin 365 gun diyor ama kodda o varsayilan yok"
