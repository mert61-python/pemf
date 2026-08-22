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


def _yeni(tmp_path, **env):
    # ⚠️ ORTAM SIZINTISI: `os.environ` testler arasında KALICIDIR; bir testte kurulan
    # `PEMF_JETON_BORC_TAVANI="0"` sonraki teste sızıp yanlış-KIRMIZI veriyordu (ölçüldü).
    # Her çağrıda VARSAYILANLARI da açıkça yaz → testler birbirinden bağımsız kalsın.
    ortam = {
        "PEMF_JETON_ENFORCED": "1",
        "PEMF_DATA_DIR": str(tmp_path),
        "PEMF_JETON_BORC_TAVANI": "300",
        "PEMF_JETON_OFFLINE_TAVAN": "50",
    }
    ortam.update(env)
    for k, v in ortam.items():
        os.environ[k] = v
    import servers.jeton as j

    importlib.reload(j)
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


def test_KARSIT_KANIT_PAYG_cevrimdisi_de_calisir(tmp_path):
    """İnternet yokken kullandıkça-öde üyelik de durmaz; tüketim yerel deftere yazılır."""

    def patlayan():
        raise ConnectionError("ağ yok")

    j = _yeni(tmp_path)
    y = j.JetonYoneticisi(
        bakiye_okuyucu=patlayan,
        tuketim_gonderici=lambda **k: False,
        odeme_modeli="kullandikca",
    )
    assert y.izin("goruntu").izinli
    assert y.bekleyen_tuketim_sayisi() == 1


def test_KARSIT_KANIT_web_ile_ayni_PAYG_parametreleri(tmp_path):
    """Site 'jeton başına ₺X' derken cihaz başka bir modelle çalışamaz."""
    import re
    from pathlib import Path

    j = _yeni(tmp_path)
    web = (Path(__file__).resolve().parent.parent / "pemf-vet-web" / "src" / "config.ts").read_text(
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
