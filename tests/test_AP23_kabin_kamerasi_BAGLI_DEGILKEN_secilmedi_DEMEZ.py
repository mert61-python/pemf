# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AP-23 (ev denemesi 14 Kasım, kurulu uygulama): seçili kabin kamerası (KD-2 kimlikli) TAKILI DEĞİLKEN hazırlık uyarısı "Kabin kamerası
SEÇİLMEDİ… seçip yeniden deneyin" diyordu; kamera kartı da "şu an kamera 0" gösteriyordu (çelişki — kullanıcı seçili kamerayı yeniden
seçmeye yönelir, asıl eylem kamerayı takmak). Kök: hazırlık iş parçacığı `KameraBulunamadi` metnini doğru üretiyor ama KODU
`kamera_secilmedi` saklıyordu → `/ai/pro/status` metni KODDAN istek dilinde yeniden üretince kimlik kayboluyordu.
SÖZLEŞME: kod `kamera_bulunamadi`; durum metni İSTEK dilinde ve kimliği (ad + VID/PID) söyler; `GET /settings/kabin-kamerasi` `bagli`
(False = aygıt listesi okundu, kimlik yok · None = bilinmiyor) + `guncelIndeks` verir — kamera AÇILMAZ. Seçim hiç yoksa eski metin / kod.
EN ALT sahte: MSMF aygıt listesi (`kamera_kimligi.msmf_kameralar`) ve `cv2.VideoCapture` (açılırsa sayılır)."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

PUSAT = {
    "ad": "FHD Camera",
    "vidpid": "VID_1BCF&PID_28C4",
    "aygit_yolu": r"\\?\usb#vid_1bcf&pid_28c4&mi_00#7&1da11eb4&1&0000#{x}",
}
HP = {
    "ad": "HP True Vision FHD Camera",
    "vidpid": "VID_04F2&PID_B7F3",
    "aygit_yolu": r"\\?\usb#vid_04f2&pid_b7f3&mi_00#7&2d19683b&0&0000#{x}",
}


def _liste(*aygitlar):
    return [dict(a, indeks=i) for i, a in enumerate(aygitlar)]


class _Kapali:
    def isOpened(self):  # noqa: N802 — OpenCV adı
        return False

    def release(self):
        return None


@pytest.fixture()
def ortam(monkeypatch, tmp_path):
    import servers.ai_pro_hedef as hedef
    import servers.ai_router as air
    import servers.api_server as apis
    from utils import kabin_kamerasi as kk
    from utils import kamera_kimligi

    monkeypatch.delenv("PEMF_KABIN_KAMERASI", raising=False)
    kok = tmp_path / "veri"
    kok.mkdir()
    monkeypatch.setattr(kk, "_veri_koku", lambda: kok)
    aygitlar: list = []
    monkeypatch.setattr(kamera_kimligi, "msmf_kameralar", lambda: [dict(a) for a in aygitlar])
    acilan: list = []
    monkeypatch.setattr(air.cv2, "VideoCapture", lambda *a: acilan.append(a) or _Kapali())

    class _Sag:
        ad = "sahte"
        title = "Sahte Model"
        subject_label = "sahte özne"
        achieved_B = 0.001
        duty_sum = 2.0
        join_timeout_s = 11.0
        varsayilan_hedef = 0

        def hedef_idleri(self):
            return frozenset({0, 1})

        def yukle(self):
            return None

        def localize(self, frame_bgr, hedef_id):
            return (False, 0.0, 0.0, 0.0, 0.0, None, False, None)

        def hedef_adi(self, hedef_id):
            return f"Sahte {hedef_id}"

        def ipucu(self, ozne_var, hedef_adi):
            return "sahte ipucu"

    monkeypatch.setitem(hedef.SAGLAYICILAR, "sahte", _Sag())
    onceki = (air._ai_hedef_modeli, air._ai_hazirlik_hata, air._ai_hazirlik_hata_kodu, air._ai_hazirlik_hata_saglayici)
    with apis._session_lock:
        oturum = dict(apis._active_session)
        apis._active_session.clear()
        apis._active_session.update({"is_active": False, "mode": "Sistem Hazır"})
    air._ai_loop_active = False
    air._ai_hazirlik_active = False
    air._ai_hazirlik_hata, air._ai_hazirlik_hata_kodu = "", ""
    monkeypatch.setattr(apis, "_ws_broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(apis, "update_live_session_state", lambda *a, **k: None)
    kk.canli_durdur()
    yield air, kk, aygitlar, acilan, TestClient(apis.app), kok

    air._ai_hazirlik_durdur_ic()
    air._ai_loop_active = False
    air._ai_hedef_modeli, air._ai_hazirlik_hata, air._ai_hazirlik_hata_kodu, air._ai_hazirlik_hata_saglayici = onceki
    with apis._session_lock:
        apis._active_session.clear()
        apis._active_session.update(oturum)
    kk.canli_durdur()


def _bekle(kosul, sn=5.0):
    son = time.time() + sn
    while time.time() < son:
        if kosul():
            return True
        time.sleep(0.03)
    return False


def test_KRITIK_secili_kamera_TAKILI_DEGILKEN_hazirlik_hatasi_KIMLIGI_istek_dilinde_soyler(ortam):
    """MUTASYON: hazırlıkta `KameraBulunamadi` için kodu yine `kamera_secilmedi` yazın ya da `_hazirlik_hata_goster`in yeni kodu
    yeniden üretmesini kaldırın → KIRMIZI."""
    from utils import ceviri

    air, kk, aygitlar, acilan, c, _kok = ortam
    aygitlar[:] = _liste(HP, PUSAT)
    kk.kamera_sec(1)
    aygitlar[:] = _liste(HP)  # kabin kamerası çıkarıldı — dahili kamera indeks 0'da
    assert c.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 0, "model": "sahte"}).status_code == 200
    assert _bekle(lambda: air._ai_hazirlik_active is False and air._ai_hazirlik_hata_kodu != "")
    assert acilan == [], f"seçili kamera yokken BAŞKA kamera açıldı: {acilan}"
    secilmedi = {d: ceviri.t("ai.pro.hazirlik.kameraSecilmedi", dil=d) for d in ("tr", "en")}
    for dil in ("tr", "en"):
        st = c.get("/api/ai/pro/status", headers={"X-PEMF-Dil": dil}).json()
        beklenen = ceviri.t("ayarlar.kabinKamerasi.kimlikBulunamadi", dil=dil, ad=PUSAT["ad"], vidpid=PUSAT["vidpid"])
        assert st["hazirlikHataKodu"] == "kamera_bulunamadi", st["hazirlikHataKodu"]
        assert st["hazirlikHata"] == beklenen and st["hazirlikHata"] != secilmedi[dil], (dil, st["hazirlikHata"])


def test_KARSIT_secim_HIC_YOKKEN_kod_ve_metin_SECILMEDI_kalir(ortam):
    from utils import ceviri

    air, kk, aygitlar, acilan, c, _kok = ortam
    aygitlar[:] = _liste(HP, PUSAT)
    assert kk.secili_kamera() is None
    r = c.post("/api/ai/pro/hazirlik/baslat", json={"organ_id": 0, "model": "sahte"}, headers={"X-PEMF-Dil": "en"})
    assert r.status_code == 409 and r.json()["detail"] == ceviri.t("ai.pro.hazirlik.kameraSecilmedi", dil="en"), r.text
    assert acilan == []


def test_KRITIK_ayar_ucu_secili_kameranin_BUGUN_BAGLI_olup_olmadigini_ve_GUNCEL_indeksi_verir(ortam):
    """Kart "şu an kamera 0" yerine "BAĞLI DEĞİL" diyebilsin; sıra değiştiyse güncel indeks. Kamera AÇILMAZ (yalnız aygıt listesi).
    MUTASYON: `bagli`yı her zaman True / None yapın ya da `guncelIndeks` yerine saklı indeksi verin → KIRMIZI."""
    air, kk, aygitlar, acilan, c, kok = ortam
    aygitlar[:] = _liste(HP, PUSAT)
    kk.kamera_sec(1)
    aygitlar[:] = _liste(HP)
    j = c.get("/api/settings/kabin-kamerasi").json()
    assert j["secili"]["indeks"] == 1 and j["bagli"] is False and j["guncelIndeks"] is None, j
    aygitlar[:] = _liste(PUSAT, HP)  # takıldı, MSMF sırası değişti
    j = c.get("/api/settings/kabin-kamerasi").json()
    assert j["bagli"] is True and j["guncelIndeks"] == 0, j
    aygitlar[:] = []  # liste okunamadı → bilinmiyor (kart eski satırı gösterir)
    j = c.get("/api/settings/kabin-kamerasi").json()
    assert j["bagli"] is None and j["guncelIndeks"] is None, j
    (kok / kk.KAMERA_DOSYASI).write_text(json.dumps({"indeks": 2}), encoding="utf-8")  # KD-2 öncesi kimliksiz seçim
    aygitlar[:] = _liste(HP)
    j = c.get("/api/settings/kabin-kamerasi").json()
    assert j["secili"] == {"indeks": 2, "kaynak": "ayar"} and j["bagli"] is None, j
    assert acilan == [], f"ayar ucu kamera AÇTI: {acilan}"


def test_KRITIK_tarama_ve_secim_yanitlari_da_BAGLANTI_durumunu_tasir(ortam, monkeypatch):
    """Kamera takılıp "Kameraları tara" denince kart "BAĞLI DEĞİL"den çıkabilsin (sayfa yenilemeden); seçim yanıtı da aynı alanları
    taşır. MUTASYON: tarama / seçim yanıtından `secim_baglanti` alanlarını kaldırın → KIRMIZI."""
    air, kk, aygitlar, acilan, c, _kok = ortam
    monkeypatch.setattr(kk, "kameralari_tara", lambda *a, **k: [])  # tarama kamerayı açar — burada açılmasın
    aygitlar[:] = _liste(HP, PUSAT)
    r = c.post("/api/settings/kabin-kamerasi", json={"indeks": 1}).json()
    assert r["secili"]["indeks"] == 1 and r["bagli"] is True and r["guncelIndeks"] == 1, r
    aygitlar[:] = _liste(HP)
    t = c.post("/api/settings/kabin-kamerasi/tara").json()
    assert t["bagli"] is False and t["guncelIndeks"] is None, t
    aygitlar[:] = _liste(PUSAT, HP)  # takıldı, yeniden tarandı
    t = c.post("/api/settings/kabin-kamerasi/tara").json()
    assert t["bagli"] is True and t["guncelIndeks"] == 0, t
    assert acilan == []
