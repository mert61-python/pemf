# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KULLANDIKÇA ÖDE (PAYG) — önden ödeme olmayan üyelik (8. parti, sahip isteği 2026-08-20).

Sahip: "hiç önden satın almadan kullandıkça öde gibi bir üyelik olmalı."

MODEL: aylık ücret YOK, önden jeton alımı YOK. Kart kaydedilir; harcanan jeton biriktirilir ve
DÖNEM SONUNDA (ya da eşik aşılınca) faturalandırılır. Hiç kullanılmazsa ücret ÇIKMAZ.

Bu, ön-ödemeli plandan farklı bir tüketim yolu gerektirir: bakiye 0 olsa bile analiz İZİNLİDİR
ve tüketim `kullandikca_borc` olarak birikir. Sınırsız değildir — `KULLANIM_TAVANI` (birikmiş
borç sınırı) aşılırsa yeni analiz durur (ödeme alınamayan sınırsız kullanım riski).

⚠️ TIBBİ GÜVENLİK: kullandıkça-öde de olsa jeton TİCARİ kapıdır — seans, seans durdurma, ACİL
DURDURMA ve sensör okuma her koşulda serbesttir (borç tavanı aşılmış olsa bile).
"""

from __future__ import annotations

import importlib
import os

import pytest

_ORTAM_ANAHTARLARI = ("PEMF_JETON_ENFORCED", "PEMF_DATA_DIR", "PEMF_JETON_BORC_TAVANI")


@pytest.fixture(autouse=True)
def _ortam_ve_modul_geri_yukle():
    """D5 (ortam sızıntısı envanteri): `_yeni` `os.environ`a DOĞRUDAN yazar ve `servers.jeton`u yeniden yükleyip `JETON_ENFORCED`i elle
    kurar — test bitince bunlar KALIYORDU (`PEMF_JETON_ENFORCED` sonraki dosyalara sızıyordu [ÖLÇTÜM]). Ortam eski hâline döner,
    modül o ortamla yeniden yüklenir. Gözcü: tests/ortam_sizinti_gozcusu.py"""
    once = {k: os.environ.get(k) for k in _ORTAM_ANAHTARLARI}
    yield
    for k, v in once.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import servers.jeton as j

    importlib.reload(j)


def _yeni(tmp_path, **env):
    # ⚠️ ORTAM SIZINTISI: `os.environ` testler arasında KALICIDIR; bir testte kurulan
    # `PEMF_JETON_BORC_TAVANI="0"` sonraki teste sızıp yanlış-KIRMIZI veriyordu (ölçüldü).
    # Her çağrıda VARSAYILANLARI da açıkça yaz → testler birbirinden bağımsız kalsın.
    ortam = {
        "PEMF_JETON_ENFORCED": "1",
        "PEMF_DATA_DIR": str(tmp_path),
        "PEMF_JETON_BORC_TAVANI": "300",
    }
    ortam.update(env)
    for k, v in ortam.items():
        os.environ[k] = v
    import servers.jeton as j

    importlib.reload(j)
    # T3 · Y194: jeton KOD düzeyinde kapalı (`JETON_SAHIP_ACIK = False`, ortam yok sayılır) → ücretlendirme mantığı burada sahip
    # anahtarı açılmış gibi sınanır (satış açılınca geçerli olacak davranış).
    j.JETON_ENFORCED = os.environ.get("PEMF_JETON_ENFORCED") == "1"
    return j


def test_KRITIK_PAYG_bakiye_SIFIRKEN_analiz_calisir_ve_borc_birikir(tmp_path):
    """Önden ödeme yok → bakiye 0'da analiz reddedilemez; tüketim borç olarak yazılır."""
    j = _yeni(tmp_path)
    gonderilen = []
    y = j.JetonYoneticisi(
        bakiye_okuyucu=lambda: 0,
        tuketim_gonderici=lambda **k: (gonderilen.append(k), True)[1],
        odeme_modeli="kullandikca",
    )
    karar = y.izin("goruntu")
    assert karar.izinli, "kullandıkça-öde üyelikte bakiye 0 diye analiz engellendi"
    assert karar.jeton_harcandi == j.MALIYET["goruntu"]
    assert gonderilen and gonderilen[0]["tur"] == "kullandikca", (
        f"tüketim 'kullandikca' türüyle gönderilmedi: {gonderilen}"
    )


def test_KRITIK_PAYG_borc_TAVANI_asilinca_yeni_analiz_durur(tmp_path):
    """Ödeme alınamayan sınırsız kullanım riski: birikmiş borç tavanı."""
    j = _yeni(tmp_path, PEMF_JETON_BORC_TAVANI="3")
    y = j.JetonYoneticisi(
        bakiye_okuyucu=lambda: 0,
        tuketim_gonderici=lambda **k: True,
        odeme_modeli="kullandikca",
        borc_okuyucu=lambda: 3,  # tavana ulaşıldı
    )
    karar = y.izin("goruntu")
    assert not karar.izinli, "borç tavanı aşıldığı hâlde analiz sürdü"
    assert "öde" in karar.mesaj.lower() or "fatura" in karar.mesaj.lower(), (
        f"red mesajı ne yapılacağını söylemiyor: {karar.mesaj!r}"
    )


def test_KRITIK_GUVENLIK_PAYG_borc_tavaninda_bile_tedavi_serbest(tmp_path):
    """⚠️ Pazarlık edilemez: borç tavanı bir TİCARİ sınırdır, tedaviyi durduramaz."""
    j = _yeni(tmp_path, PEMF_JETON_BORC_TAVANI="0")
    y = j.JetonYoneticisi(
        bakiye_okuyucu=lambda: 0,
        tuketim_gonderici=lambda **k: True,
        odeme_modeli="kullandikca",
        borc_okuyucu=lambda: 9999,
    )
    for guvenli in ("seans_baslat", "seans_durdur", "acil_durdur", "sensor_oku", "cihaz_kontrol"):
        assert y.izin(guvenli).izinli, f"borç tavanında GÜVENLİK yolu engellendi: {guvenli}"


def test_KARSIT_KANIT_on_odemeli_planda_bakiye_0_HALA_reddeder(tmp_path):
    """Aşırı-genişleme koruması: PAYG davranışı ön-ödemeli plana sızmamalı."""
    j = _yeni(tmp_path)
    y = j.JetonYoneticisi(
        bakiye_okuyucu=lambda: 0,
        tuketim_gonderici=lambda **k: True,
        odeme_modeli="on_odemeli",
    )
    assert not y.izin("goruntu").izinli, "ön-ödemeli planda bakiye 0 iken analiz izinli çıktı"


def test_KRITIK_PAYG_borc_OKUNAMAZSA_analiz_BASLATILMAZ_S4B5(tmp_path):
    """S-4B.5 (sahip kararı 2026-10-19): borç okunamıyorsa (internet yok) yeni analiz başlatılmaz — eskiden borç 0 sayılıp İZİN
    veriliyordu (fail-open). Ücret çevrimiçi düşülür; tedavi yolu bu kapıya hiç gelmez."""

    def patlayan():
        raise ConnectionError("ağ yok")

    j = _yeni(tmp_path)
    gonderilen: list = []
    y = j.JetonYoneticisi(
        bakiye_okuyucu=lambda: 0,
        tuketim_gonderici=lambda **k: (gonderilen.append(k), True)[1],
        odeme_modeli="kullandikca",
        borc_okuyucu=patlayan,
    )
    karar = y.izin("goruntu")
    assert not karar.izinli and karar.sebep == "cevrimdisi" and "internet gerekir" in karar.mesaj, karar
    assert not gonderilen and y.bekleyen_tuketim_sayisi() == 0


def test_KARSIT_KANIT_PAYG_yolda_kalan_odeme_deftere_ve_BORCA_eklenir(tmp_path):
    """Düşüm o an gönderilemezse (ağ koptu) kayıt defterde bekler ("Bir süre yeniden dene") ve sonraki kararlarda BORCA eklenir —
    tavan, gönderilemeyen kullanım yüzünden aşılamaz."""
    j = _yeni(tmp_path, PEMF_JETON_BORC_TAVANI="3")
    y = j.JetonYoneticisi(
        bakiye_okuyucu=lambda: 0,
        tuketim_gonderici=lambda **k: False,
        odeme_modeli="kullandikca",
        borc_okuyucu=lambda: 1,
        sahip="payg-1",
    )
    assert y.izin("goruntu").izinli  # borç 1 + yolda 0 < 3
    assert y.bekleyen_tuketim_sayisi() == 1, "gönderilemeyen kullanım deftere yazılmadı"
    assert y.izin("goruntu").izinli  # 1 + 1 < 3
    son = y.izin("goruntu")  # 1 + 2 = 3 → tavan
    assert not son.izinli and son.sebep == "borc_tavani", f"yolda kalan kullanım borca eklenmedi: {son}"


def test_KRITIK_PAYG_tavanin_1_altinda_ES_ZAMANLI_analizler_TAVANI_ASAMAZ(tmp_path):
    """Eşzamanlılık açığı (2026-10-19, sahip "bunları yap"): karar analiz başlarken, tüketim teslimde. Tavanın 1 altındaki borçta
    eşzamanlı 4 analiz 4 izin alıyordu — sunucu kullandıkça modelinde borcu SINIRSIZ artırır (tavan yalnız cihazda,
    supabase_jetonlar.sql). Kural AYNI (`borç + ayrılmış < tavan`); teslim edilmeyen analiz ayrımı bırakır; başka hesap etkilenmez."""
    j = _yeni(tmp_path, PEMF_JETON_BORC_TAVANI="3")

    def yonetici(sahip: str):
        return j.JetonYoneticisi(
            bakiye_okuyucu=lambda: 0,
            tuketim_gonderici=lambda **k: True,
            odeme_modeli="kullandikca",
            borc_okuyucu=lambda: 2,
            sahip=sahip,
        )

    kararlar = [yonetici("payg-2").on_izin("goruntu") for _ in range(4)]  # dördü de karar aldı, hiçbiri teslim edilmedi
    assert [k.izinli for k, _ in kararlar] == [True, False, False, False], [k for k, _ in kararlar]
    kararlar[0][1].birak()  # ilk analiz teslim edilmeden düştü (uç istisnası) → ayrım bırakılır
    assert yonetici("payg-2").on_izin("goruntu")[0].izinli, "teslim edilmeyen analizin ayrımı sızdı — tavan kilitlendi"
    assert yonetici("payg-3").on_izin("goruntu")[0].izinli, "bir hesabın ayrımı başka hesabın tavanından düşüldü"


def test_KARSIT_PAYG_tavanin_ALTINDA_agir_analiz_ESKISI_GIBI_izinli(tmp_path):
    """Kural değişmedi: tavanın altındaki borçta analiz izinlidir, maliyeti tavanı aşabilir (borç 2, tavan 3, ağır araştırma 3)."""
    j = _yeni(tmp_path, PEMF_JETON_BORC_TAVANI="3")
    y = j.JetonYoneticisi(
        bakiye_okuyucu=lambda: 0,
        tuketim_gonderici=lambda **k: True,
        odeme_modeli="kullandikca",
        borc_okuyucu=lambda: 2,
        sahip="payg-4",
    )
    assert y.izin("agir_arastirma").izinli, "tavanın altındaki borçta ağır analiz reddedildi (kural sıkılaştı)"


def test_KARSIT_KANIT_web_ile_ayni_PAYG_parametreleri(tmp_path):
    """Site 'jeton başına ₺X' derken cihaz başka bir modelle çalışamaz."""
    import re
    from pathlib import Path

    j = _yeni(tmp_path)
    web = (Path(__file__).resolve().parent.parent / "apps/web" / "src" / "config.ts").read_text(
        encoding="utf-8", errors="replace"
    )
    m = re.search(r"kullandikcaOde:\s*\{([^}]*)\}", web)
    assert m, "web tarafında JETON.kullandikcaOde tanımlı değil"
    alanlar = dict(re.findall(r"(\w+):\s*([\d.]+)", m.group(1)))
    assert "jetonFiyati" in alanlar, "jeton birim fiyatı tanımsız"
    assert float(alanlar["jetonFiyati"]) > 0
    assert "borcTavani" in alanlar, "borç tavanı web tarafında tanımsız"
    assert int(float(alanlar["borcTavani"])) == j.BORC_TAVANI, (
        f"borç tavanı ayrıştı: web={alanlar['borcTavani']} cihaz={j.BORC_TAVANI}"
    )
