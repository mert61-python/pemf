# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""MASAÜSTÜ ARAYÜZÜ — SADE DİL (kullanıcı-dostuluk denetimi 5. parti, 2026-08-20).

Web sitesinde dört parti boyunca temizlenen jargon, hekimin ASIL kullandığı yüzeyde —
`launcher/app/ui/index.html` — aynen duruyordu:

  · "Hafif client…"                         → ürünün adı ekranda "client"
  · "SHA-256 ile doğrular"                  → kriptografi terimi
  · "indirilen kısım cache'te korundu"      → geliştirici terimi
  · "Client güncelleniyor…"                 → aynı adlandırma karmaşası
  · "Uygulama çekirdeği"                    → iç terim (paket adı)

Site ile aynı sözlük burada da geçerli (bkz. pemf-vet-web/METIN-KILAVUZU.md):
ürün adı **PEMF Vet**, süreci anlatan yerde tek ad **başlatıcı**.

⚠️ Kapı YORUM-SOYULMUŞ metinde çalışır: bu dosyaların yorumları düzeltmenin gerekçesini
(dolayısıyla ESKİ hatalı ifadeyi) anlatır; soyulmazsa kapı kendi açıklamasını görüp
yanlış-KIRMIZI verir — bu deponun beş kez düştüğü tuzak.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
UI = KOK / "launcher" / "app" / "ui" / "index.html"


def _soy(src: str) -> str:
    """HTML/JS yorumlarını söker; string literalleri (ekran metni!) korur."""
    src = re.sub(r"<!--.*?-->", " ", src, flags=re.S)
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    # satır yorumları: string içindeki // (ör. "https://") korunmalı → tırnak-bilinçli tarama
    out, i, n, durum = [], 0, len(src), 0  # 0=kod 1=' 2=" 3=` 4=//
    while i < n:
        c, nx = src[i], src[i + 1] if i + 1 < n else ""
        if durum == 0:
            if c == "/" and nx == "/":
                durum = 4
                i += 2
                out.append("  ")
                continue
            if c == "'":
                durum = 1
            elif c == '"':
                durum = 2
            elif c == "`":
                durum = 3
            out.append(c)
        elif durum in (1, 2, 3):
            if c == "\\":
                out.append(c)
                out.append(nx)
                i += 2
                continue
            kapanis = {1: "'", 2: '"', 3: "`"}[durum]
            if c == kapanis:
                durum = 0
            out.append(c)
        else:
            if c == "\n":
                durum = 0
                out.append("\n")
            else:
                out.append(" ")
        i += 1
    return "".join(out)


def _i18n_tr() -> str:
    """I18N bloğunun TÜRKÇE EKRAN DEĞERLERİ (yorumlar soyulmuş, ANAHTAR ADLARI hariç).

    ⚠️ İlk yazımda blok ham hâliyle taranıyordu ve `cached:` ANAHTARI "cache" yasağına takılıp
    yanlış-KIRMIZI veriyordu (ölçüldü). Anahtar adı kod tanımlayıcısıdır — ekranda görünmez;
    ölçülmesi gereken şey yalnız tırnak içindeki DEĞERLERDİR.
    """
    # ⚠️ Blok sınırlarını burada YENİDEN hesaplamaya gerek yok: `_i18n_tr_ham()` aynı işi
    # yapıyor ve işaretler bulunamazsa zaten patlıyor. (Refaktörden kalan ölü satırlar silindi.)
    return "\n".join(re.findall(r'"([^"]*)"', _i18n_tr_ham()))


def _i18n_tr_ham() -> str:
    """TÜRKÇE bloğun HAM hâli — anahtar adıyla arama yapan testler için (ör. `repair:`)."""
    s = _soy(UI.read_text(encoding="utf-8", errors="replace"))
    i = s.index("const I18N")
    j = s.index("en: {", i)
    return s[i:j]


def test_KRITIK_urun_adi_ekranda_client_DEGIL():
    """Ekran metninde "client" geçmez — site ile aynı karar (ürün adı PEMF Vet)."""
    tr = _i18n_tr()
    for olu in ("Hafif client", "client sürümü", "Client güncelleniyor"):
        assert olu not in tr, f"masaüstü arayüzünde hâlâ 'client' adlandırması var: {olu!r}"


def test_KRITIK_gelistirici_terimleri_YOK():
    """SHA-256 / cache / çekirdek gibi terimler hekime hiçbir şey anlatmıyor."""
    tr = _i18n_tr()
    for olu in ("SHA-256", "cache", "Uygulama çekirdeği"):
        assert olu not in tr, f"masaüstü arayüzünde geliştirici terimi: {olu!r}"


def test_KRITIK_onar_dugmesi_NE_ONARDIGINI_soyler():
    """Tek kelimelik "Onar" neyin onarılacağını söylemiyordu (denetim bulgusu)."""
    m = re.search(r'repair:\s*"([^"]+)"', _i18n_tr_ham())
    assert m, "repair düğmesi bulunamadı"
    assert len(m.group(1)) > 5, f"'Onar' tek başına belirsiz: {m.group(1)!r}"


def test_KARSIT_KANIT_basaltici_adi_TANIMLI_ve_marka_KORUNUR():
    """Aşırı-sadeleştirme koruması: ara katman adı büsbütün silinmemeli (kullanıcı ne indirdiğini
    bilmeli) ve marka/ürün adı ekranda durmalı."""
    tr = _i18n_tr()
    assert "başlatıcı" in tr.lower(), "süreç adı 'başlatıcı' hiç geçmiyor — kullanıcı ne kurduğunu bilemez"
    assert "PEMF Vet" in tr, "ürün adı ekrandan silinmiş"


def test_KARSIT_KANIT_INGILIZCE_bolum_de_guncellenmis():
    """İki dil AYNI şeyi söylemeli — yalnız Türkçesini düzeltmek çeviriyi ayrıştırırdı."""
    s = _soy(UI.read_text(encoding="utf-8", errors="replace"))
    en = s[s.index("en: {") :]
    assert "Lightweight client" not in en, "İngilizce metin eski adlandırmada kalmış"
    assert "SHA-256" not in en, "İngilizce metinde kriptografi terimi kalmış"
