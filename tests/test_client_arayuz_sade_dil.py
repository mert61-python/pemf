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

Site ile aynı sözlük burada da geçerli (bkz. apps/web/METIN-KILAVUZU.md):
ürün adı **PEMF Vet**, süreci anlatan yerde tek ad **başlatıcı**.

⚠️ Kapı YORUM-SOYULMUŞ metinde çalışır: bu dosyaların yorumları düzeltmenin gerekçesini
(dolayısıyla ESKİ hatalı ifadeyi) anlatır; soyulmazsa kapı kendi açıklamasını görüp
yanlış-KIRMIZI verir — bu deponun beş kez düştüğü tuzak.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from i18n_yardimci import launcher_ui as ui

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
    return "\n".join(_ui_degerleri("tr"))


def _ui_degerleri(dil: str) -> list[str]:
    """I18N-P1 · 11a: arayüz sözlükleri `launcher/i18n/<dil>.json → ui.*` kataloğuna taşındı; ekran DEĞERLERİ (anahtar adı değil) sırayla."""
    out: list[str] = []

    def gez(d):
        for v in d.values():
            if isinstance(v, dict):
                gez(v)
            else:
                out.append(v)

    gez(ui(dil))
    return out


def test_KRITIK_urun_adi_ekranda_client_DEGIL():
    """Ekran metninde "client" geçmez — site ile aynı karar (ürün adı PEMF Vet).

    ⚠️ D5.28 (B-10.228): kapı eskiden yalnız ÜÇ kalıbı arıyordu ("Hafif client" …) — `ui.luReady` "PEMF Vet Client {{surum}} yayınlandı"
    ve `ui.kilavuz.intro` "Bu client, …" ekranda duruyordu ve kapı YEŞİLDİ (önceki sürümde de backtick'li değerler hiç taranmıyordu).
    Kural artık KELİMENİN KENDİSİ: ekrandaki hiçbir TR / EN değerinde "client" yok (süreç adı TR "başlatıcı", EN "launcher"). Windows
    kurulum adı (`PEMF Vet Client` — kaldırma kaydı, klasör, productName) EKRAN metni değildir, değişmez."""
    for dil in ("tr", "en"):
        kotu = [v for v in _ui_degerleri(dil) if re.search(r"(?i)\bclient\b", v)]
        assert not kotu, f"masaüstü arayüzünde ({dil}) hâlâ 'client' adlandırması var: {kotu}"
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
    onar = ui("tr").get("repair")
    assert onar, "repair düğmesi bulunamadı"
    assert len(onar) > 5, f"'Onar' tek başına belirsiz: {onar!r}"


def test_KARSIT_KANIT_basaltici_adi_TANIMLI_ve_marka_KORUNUR():
    """Aşırı-sadeleştirme koruması: ara katman adı büsbütün silinmemeli (kullanıcı ne indirdiğini
    bilmeli) ve marka/ürün adı ekranda durmalı."""
    tr = _i18n_tr()
    assert "başlatıcı" in tr.lower(), "süreç adı 'başlatıcı' hiç geçmiyor — kullanıcı ne kurduğunu bilemez"
    assert "PEMF Vet" in tr, "ürün adı ekrandan silinmiş"


def test_KARSIT_KANIT_INGILIZCE_bolum_de_guncellenmis():
    """İki dil AYNI şeyi söylemeli — yalnız Türkçesini düzeltmek çeviriyi ayrıştırırdı."""
    en = "\n".join(_ui_degerleri("en"))
    assert "Lightweight client" not in en, "İngilizce metin eski adlandırmada kalmış"
    assert "SHA-256" not in en, "İngilizce metinde kriptografi terimi kalmış"


# ─────────────── D6.67 (B-7.22 · B-7.23): METIN-KILAVUZU yasak adları — ekrana giden TÜM kaynaklar ───────────────
# Eski kapı yalnız `ui.*` değerlerinde "client" arıyordu: profil kartı adı (`ui.profilMeta`), kılavuz (`ui.kilavuz`), Rust iletileri
# (`rust.*` — giriş / kurulum hataları ekranda), NSIS kaldırıcı satırları (`nsis.*`) ve index.html'in HTML varsayılan metni (JS
# çalışmadan önce görünen etiket / başlık) yasak adları taşıyordu ve kapı YEŞİLDİ.
_YASAK = {
    "tr": {
        # Tur 2 kolu (D67 çürütme, mutant u1): büyük / küçük harf ve Türkçe İ / ı biçimlerinden bağımsız ("ev sahibi", "EV SAHİBİ").
        "Ev Sahibi": (
            r"(?i)\bev sah[iıİI]b[iıİI]",
            "'Evcil Hayvan Sahibi' (Türkçede 'ev sahibi' = mülk sahibi) — METIN-KILAVUZU §2",
        ),
        "Araştırma Modu": (r"(?i)araştırma modu", "kurulum profili 'Araştırma' (mod ❌) — METIN-KILAVUZU §3"),
        "PEMF Vet Client": (
            r"PEMF Vet Client",
            "ekranda ürün adı 'PEMF Vet', süreç adı 'başlatıcı' — METIN-KILAVUZU §1",
        ),
        "Parola": (r"(?i)\bparola", "giriş bilgisi 'şifre' (parola ❌) — METIN-KILAVUZU §3"),
        "KPI": (r"\bKPI\b", "'klinik istatistikleri' / uygulamadaki menü adı 'Raporlar' — METIN-KILAVUZU §2"),
        "client": (r"(?i)\bclient\b", "süreç adı 'başlatıcı' — METIN-KILAVUZU §1"),
    },
    "en": {
        "Research Mode": (r"(?i)\bresearch mode\b", "install profile 'Research' (TR 'Araştırma Modu' ile eş)"),
        "PEMF Vet Client": (r"PEMF Vet Client", "product name 'PEMF Vet', process name 'launcher'"),
        "KPI": (r"\bKPI\b", "'clinic statistics' / app menu 'Reports'"),
        "client": (r"(?i)\bclient\b", "process name 'launcher'"),
        "Home Owner": (r"(?i)\bhome ?owner", "'Pet Owner'"),
    },
}
# Bilinçli, DAR istisna defteri. Y211 · S-D67.15 (sahip): giriş hatası iletisi artık METİN sözleşmesi DEĞİL — `doLogin` makine-okur koda
# (`AuthError::kod`) bakar → "parola" istisnaları (kimlikHatali / girdiBos / doLogin karşılaştırması) KALDIRILDI, iletiler "şifre" der.
# İstisna BAYATLARSA (ileti düzeltildiyse) aşağıdaki kapı kırmızıdır.
_ISTISNA: dict[tuple[str, str, str], str] = {}


def _duz(d: dict, yol: str = ""):
    for k, v in d.items():
        y = f"{yol}.{k}" if yol else k
        if isinstance(v, dict):
            yield from _duz(v, y)
        elif isinstance(v, str):
            yield y, v


def _katalog_kaynaklari(dil: str) -> list[tuple[str, str]]:
    """`launcher/i18n/<dil>.json` — ui (arayüz), rust (başlatıcı iletileri), nsis (kaldırıcı) — HER değer."""
    veri = json.loads((KOK / "launcher" / "i18n" / f"{dil}.json").read_text(encoding="utf-8"))
    return list(_duz(veri))


def _js_dizgeleri(js: str) -> list[str]:
    """Yorumları soyulmuş betikteki '…', "…" ve `…` dizgelerinin içeriği (ters bölü kaçışı bilinçli)."""
    out, i, n = [], 0, len(js)
    while i < n:
        c = js[i]
        if c in "'\"`":
            j, buf = i + 1, []
            while j < n and js[j] != c:
                if js[j] == "\\" and j + 1 < n:
                    buf.append(js[j : j + 2])
                    j += 2
                    continue
                buf.append(js[j])
                j += 1
            out.append("".join(buf))
            i = j + 1
            continue
        i += 1
    return out


def _html_kaynaklari() -> list[tuple[str, str]]:
    """index.html (yorumlar soyulmuş): HTML metin düğümleri + görünen öznitelikler (JS çalışmadan önceki VARSAYILAN metin) ve betik dizgeleri."""
    src = _soy(UI.read_text(encoding="utf-8"))
    betikler = re.findall(r"<script\b[^>]*>(.*?)</script>", src, flags=re.S | re.I)
    isaret = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", src, flags=re.S | re.I)
    out = [("index.html:html", m.strip()) for m in re.findall(r">([^<>]+)<", isaret) if m.strip()]
    out += [
        ("index.html:html", m)
        for m in re.findall(r'\b(?:title|placeholder|aria-label|alt|content)\s*=\s*"([^"]*)"', isaret, flags=re.I)
    ]
    out += [("index.html:js", s) for b in betikler for s in _js_dizgeleri(b) if s.strip()]
    return out


def _yasak_bulgulari() -> list[str]:
    kotu = []
    for dil in ("tr", "en"):
        kaynaklar = _katalog_kaynaklari(dil) + (_html_kaynaklari() if dil == "tr" else [])
        for yol, metin in kaynaklar:
            for ad, (desen, dogru) in _YASAK[dil].items():
                if re.search(desen, metin) and (dil, yol, ad) not in _ISTISNA:
                    kotu.append(f"[{dil}] {yol}: '{ad}' → {dogru}: {metin[:120]!r}")
    return kotu


def test_KRITIK_METIN_KILAVUZU_yasak_adlari_ekrana_giden_HICBIR_kaynakta_YOK_D6_67():
    kotu = _yasak_bulgulari()
    assert not kotu, f"{len(kotu)} ekran metni METIN-KILAVUZU yasak adını taşıyor:\n" + "\n".join(kotu)


def test_KARSIT_D6_67_istisnalar_BAYAT_degil_ve_dogru_adlar_EKRANDA():
    """İstisna yalnız sözleşmeli iletide durur; ileti düzeltilince istisna da kalkmalı (yoksa kapı ileride kör kalır). Aşırı-temizlik
    koruması: doğru adlar ekranda — kart / kılavuz 'Evcil Hayvan Sahibi', kurulum profili 'Araştırma', giriş etiketi 'Şifre'."""
    tr = dict(_katalog_kaynaklari("tr"))
    js = [s for y, s in _html_kaynaklari() if y == "index.html:js"]
    for dil, yol, ad in _ISTISNA:
        desen = _YASAK[dil][ad][0]
        if yol == "index.html:js":
            assert any(re.search(desen, s) for s in js), (
                f"istisna BAYAT: {yol} artık '{ad}' taşımıyor — _ISTISNA'dan çıkarın"
            )
        else:
            assert yol in tr and re.search(desen, tr[yol]), (
                f"istisna BAYAT: {yol} artık '{ad}' taşımıyor — _ISTISNA'dan çıkarın"
            )
    assert tr["ui.profilMeta.home.ad"] == "Evcil Hayvan Sahibi", tr["ui.profilMeta.home.ad"]
    assert tr["ui.profilMeta.research.ad"] == "Araştırma", tr["ui.profilMeta.research.ad"]
    assert tr["ui.loginPass"] == "Şifre", tr["ui.loginPass"]
    assert "Raporlar" in tr["ui.kilavuz.profiles.p02.use.u04"], tr["ui.kilavuz.profiles.p02.use.u04"]
