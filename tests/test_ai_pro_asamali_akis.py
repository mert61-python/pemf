# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""AI PRO: KEDI -> ORGAN -> PARAMETRE asamali akisi (saha bildirimi 2026-08-24).

🔴 OLCULEN KILITLENME (mobilde AI Pro HIC baslatilamiyordu):
  · `/api/ai/pro/propose` TAZE lokalizasyon ister (`_ai_organ_cache`, <120 sn, ayni organ);
  · lokalizasyon YALNIZ kare islenince olusur;
  · mobilde kareler `AiProPanel` icinde `if (IS_WEB || !running) return;` ile YALNIZ seans
    BASLADIKTAN sonra akiyordu;
  · seans ise propose'suz baslamiyordu.
Sonuc: dongusel kilit. Kullaniciya "Kamerayi hedefe dogrultup 'Yeniden konumla' ile
lokalizasyonu tamamlayin" deniyordu ama o dugme yalnizca sunucuda bir bayrak set ediyor —
kare akmadigi icin HICBIR SEY olmuyordu. Ekran hatayi tekrar tekrar gosteriyordu.

SAHIP ISTEGI: "once kedi tespiti ardindan organ tespiti calisip kullanicinin sectigi organa gore
faz duty hesaplanmali konum bilgilerine gore."

SOZLESME:
  1. Kare ucu kedi VARLIGINI organ lokalizasyonundan AYRI bildirir → arayuz "kedi yok" ile
     "kedi var, organ aranıyor" durumlarini ayirt edip kullaniciya ne yapacagini soyleyebilir.
  2. Durum ucu ayni bilgiyi tasir (hazirlik ekrani kare yanitini kacirirsa oradan okur).
  3. ⚠️ TIBBI GUVENLIK DEGISMEZ: hazirlik karesi BOBIN SURMEZ — surus yalnizca onaylanmis ve
     sure-watchdog'u olan AKTIF seansta olur (`session_active`). Bu kapi P0'dir, gevsetilemez.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_ROUTER = _KOK / "servers" / "ai_router.py"
_PANEL = _KOK / "pf" / "src" / "components" / "domain" / "AiProPanel.tsx"


@pytest.fixture(scope="module")
def router() -> str:
    return _ROUTER.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def panel() -> str:
    return _PANEL.read_text(encoding="utf-8", errors="replace")


# ── 1) Backend: kedi varligi organdan AYRI bildirilir ────────────────────────────


def test_KRITIK_kedi_varligi_organdan_AYRI_bildirilir(router):
    """Kullanici "kedi yok" ile "kedi var ama organ bulunamadi"yi ayirt edebilmeli.

    Ikisi de bugun tek bir `detected: false` altinda birlesiyordu; kullaniciya ne yapmasi
    gerektigi (kamerayi hayvana dogrultmak mi, aciyi degistirmek mi) soylenemiyordu.
    """
    assert "kedi_var" in router, (
        "cat_organ sonucundan kedi VARLIGI cikarilmiyor — arayuz 'kedi yok' ile "
        "'organ bulunamadi'yi ayirt edemez (sahip istegi: once kedi, sonra organ)"
    )
    m = re.search(r"def _extract_organ_target\(.*?\n\ndef ", router, re.S)
    assert m, "_extract_organ_target bulunamadi"
    assert "organs_by_id" in m.group(0) and "kedi_var" in m.group(0), "kedi varligi organ sozlugunden turetilmiyor"


def test_KRITIK_her_cache_update_kedi_var_PARITE(router):
    """🔴 İKİ TRANSPORT PARİTESİ (denetim 2026-08-24, E3): web (_ai_pro_loop) ve mobil
    (ai_pro_frame) yollari `_ai_organ_cache`i AYNI asama anahtarlariyla guncellemeli.

    Loop `lkedi`yi cozup ATIYORDU — cache'i yalniz frame yolu (kedi_var) guncelliyordu. Sonuc: web/
    sunucu-kamerali seansta ws `catDetected` ve /status + propose-409 ipucu SUREC OMRU boyunca bayat
    kaliyor, hedef kaybolunca yanlis operator yonlendirmesi (kedi kabinden ciktiginda 'aciyi
    degistirin'). Bu deponun 1 NUMARALI hata deseni: ayni kural iki transport, biri uygulamiyor.
    Her cache.update sozlugu kedi_var TASIMALI."""
    bloklar = re.findall(r"_ai_organ_cache\.update\(\s*\{(.*?)\}\s*\)", router, re.S)
    assert len(bloklar) >= 2, (
        f"iki cache.update yolu (loop + frame) beklendi, {len(bloklar)} bulundu — ai_router.py bicimi degismis"
    )
    for i, b in enumerate(bloklar):
        assert '"kedi_var"' in b, (
            f"{i}. cache.update kedi_var YAZMIYOR — o transport'ta (web-loop ya da mobil-frame) asama "
            "bilgisi bayat kalir ve yanlis yonlendirme uretir (E3)"
        )


def test_KRITIK_kare_yaniti_asamayi_TASIR(router):
    """Mobil panel asamayi /frame HTTP yanitindan okur; alan yoksa hazirlik ekrani sessiz kalir.

    ⚠️ GERCEK ai_pro_frame YANITINA capalanir (denetim 2026-08-24, E2): router.find('"detected":
    localized') ILK gecis WS yayinidir (_ai_pro_loop, catDetected orada VAR ama mobil onu /frame'den
    okur, /status'tan degil). Eski test ilk gecisi (WS blogu) olcup /frame yanitini HIC gormeden
    yesil donuyordu; /frame catDetected TASIMIYORDU ve mobil hazirlik ekraninin 'hayvan gorunuyor,
    organ araniyor' asamasi olu kaliyordu (F1 sinifi yanlis-yesil kapi)."""
    fi = router.find("def ai_pro_frame")
    assert fi > 0, "ai_pro_frame ucu bulunamadi — ai_router.py bicimi degismis"
    govde = router[fi:]
    # 3. tur B1: 'detected' değeri artık `bool(localized) and not is_foreign` → JSON-anahtarına
    # pinle (çıplak değer ifadesine değil), yoksa sahiplik-kapısı eklenince çıpa kayar.
    i = govde.find('"detected":')
    assert i > 0, "ai_pro_frame HTTP yanitinda 'detected' bulunamadi"
    blok = govde[i - 200 : i + 600]
    # ⚠️ JSON ANAHTARI desenini ara (`"catDetected":`), cIplak "catDetected" DEGIL: yanit
    # yorumlarinda da "catDetected" kelimesi geciyor ve ciplak arama bir mutasyonu KACIRDI
    # (kod satiri silinse bile yorum kelimesi yesil birakiyordu — deponun 1 numarali hata deseni,
    # bu testin kendisinde). Anahtar-deger sozdizimi yorumda gecmez.
    assert '"catDetected":' in blok, (
        "ai_pro_frame HTTP yaniti kedi varligini (catDetected) TASIMIYOR — mobil panel onu YALNIZ "
        "/frame yanitindan okur (AiProStatus tipi catDetected icermez); hazirlik ekrani 'hayvan "
        "gorunuyor, organ araniyor' asamasini HIC gosteremez, hayvan kadrajdayken bile 'hayvan "
        "araniyor' der (E2)"
    )


def test_KRITIK_durum_ucu_asamayi_TASIR(router):
    i = router.find("def ai_pro_status")
    assert i > 0, "status ucu bulunamadi"
    # JSON anahtari (`"catDetected":`) — ciplak kelime yorumda da gecebilir (mutasyon kacisi).
    assert '"catDetected":' in router[i : i + 900], "durum ucu kedi varligini tasimiyor"


def test_KARSIT_KANIT_hazirlik_karesi_BOBIN_SURMEZ(router):
    """🔴 P0 DEGISMEZ: surus yalnizca onaylanmis + watchdog'lu AKTIF seansta.

    Hazirlik icin kare akitmak bu kapiyi GEVSETMEZ; gevsetilseydi onaysiz ve suresiz bir
    PEMF maruziyeti dogardi.
    """
    # 3. tur B1: kapı `... and not is_foreign:` ile SIKILAŞTIRILDI (yabancı kare de sürmez).
    # `localized and session_active` şartı KORUNUYOR → renksiz koşula (iki-koşul ÖN-EK) pinle;
    # gevşetme (koşulun kaldırılması) yine kırmızı verir, meşru sıkılaştırma yeşil kalır.
    assert "if localized and session_active" in router, (
        "bobin surus kapisi degismis — hazirlik karesi bobin surebilir (P0 ihlali)"
    )
    # Sıkılaştırmanın gevşemeye dönüşmediğini de doğrula: kapı hâlâ `session_active`'i ŞART koşmalı.
    assert "session_active and not is_foreign" in router, (
        "B1 sahiplik kapısı (not is_foreign) düştü — yabancı kare bobin sürebilir"
    )


# ── 2) Mobil: hazirlik asamasinda kare AKAR ─────────────────────────────────────


def test_KRITIK_mobil_kare_BASLAMADAN_ONCE_de_akar(panel):
    """🔴 ASIL KILITLENME: kareler yalniz `running` iken akiyordu.

    `/propose` taze lokalizasyon ister, lokalizasyon kare ister, kare ise seans ister →
    dongusel kilit. Mobilde AI Pro HIC baslatilamiyordu.
    """
    m = re.search(r"if \(IS_WEB \|\| !running\) return;", panel)
    assert not m, (
        "mobil kare akisi hala YALNIZ `running` iken calisiyor — propose taze lokalizasyon "
        "ister, lokalizasyon kare ister, kare seans ister: AI Pro hic baslatilamaz"
    )
    assert "hazirlik" in panel, "hazirlik (lokalizasyon-once) asamasi yok"


def test_KRITIK_yeniden_konumla_GERCEKTEN_calisir(panel):
    """'Yeniden Konumla' yalniz sunucu bayragi set ediyordu; kare akmadan hicbir sey olmuyordu —
    kullaniciya ise tam olarak o dugmeye basmasi soyleniyordu."""
    i = panel.find("const relocalize")
    assert i > 0, "relocalize bulunamadi"
    # ⚠️ Pencere GENIS: gerekce yorumlari uzun (ilk yazimda 700 karakter yetmedi).
    blok = panel[i : i + 1600]
    assert "hazirlik" in blok.lower() or "setHazirlik" in blok, (
        "'Yeniden Konumla' kare akisini BASLATMIYOR — dugme gorsel olarak calisiyor ama "
        "lokalizasyon icin gereken kare hic gonderilmiyor"
    )


def test_KRITIK_lokalizasyon_bitince_oneri_OTOMATIK_istenir(panel):
    """Kullanici hazirligi izleyip ayrica bir dugmeye daha basmak zorunda kalmamali."""
    assert re.search(r"(localized|catDetected)", panel), "panel asama bilgisini okumuyor"
    assert "/ai/pro/propose" in panel, "oneri istegi yok"


def test_KARSIT_KANIT_onay_kapisi_KORUNUR(panel):
    """⚠️ Akisi kolaylastirmak ONAY KAPISINI kaldirmaz: hekim ne uygulanacagini gorup
    onaylamadan tedavi BASLAMAZ (sahip karari 2026-08-06)."""
    assert "/ai/pro/approve" in panel, "onay adimi kaldirilmis"
    # ⚠️ CAGRI yerini ara, ilk gecisi DEGIL: modul basligi da yollari aniyor ve ilk gecis
    # yorumun icinde kaliyor (ilk yazimda bu testi yanlis-KIRMIZI yapti).
    m = re.search(r'apiPost<[^>]*>\(\s*"/ai/pro/start"', panel)
    assert m, "start CAGRISI bulunamadi"
    onceki = panel[max(0, m.start() - 1200) : m.start()]
    assert "proposal" in onceki, "start onaydan bagimsiz cagrilabiliyor"


def test_KRITIK_kamera_HAZIRLIKTA_da_monte_edilir(panel):
    """🔴 KİLİTLENMENİN İKİNCİ HALKASI (ölçülerek bulundu).

    Kare akışını `hazirlik`e açmak TEK BAŞINA yetmiyordu: `CameraView` yalnız `running` iken
    monte ediliyordu, dolayısıyla hazırlıkta `cameraRef.current` null kalıyor ve kare HİÇ
    çekilemiyordu. İki halka birden düzeltilmeden lokalizasyon imkânsızdı.
    """
    assert not re.search(r"\) : running && permission\?\.granted \? \(", panel), (
        "kamera hala YALNIZ `running` iken monte ediliyor — hazirlikta cameraRef null kalir ve "
        "kare cekilemez; lokalizasyon hic olusmaz (kilitlenmenin ikinci halkasi)"
    )
    assert re.search(r"\(running \|\| hazirlik\) && permission\?\.granted", panel), (
        "kamera montaj kosulu hazirligi kapsamiyor"
    )


def test_KRITIK_asama_kullaniciya_GOSTERILIR(panel):
    """Sahip isteği: "önce kedi tespiti ardından organ tespiti" — operatör hangi aşamada
    olduğunu ve ne yapması gerektiğini GÖRMELİ; sessiz bir bekleme kabul edilemez."""
    assert "asamaMetni" in panel, "hazirlik asama metni yok"
    for ipucu in ("Hayvan aranıyor", "aranıyor…", "konumlandı"):
        assert ipucu in panel, f"asama metni eksik: {ipucu}"
    assert "catDetected" in panel, "panel kedi/organ ayrimini okumuyor"


def test_KRITIK_hazirliktan_CIKIS_yolu_var(panel):
    """Kullanıcı hazırlıkta sıkışmamalı: vazgeçebilmeli (eski akışta hatadan çıkış yoktu)."""
    i = panel.find("hazirlikIptal")
    assert i > 0, "hazirliktan cikis (vazgec) yolu yok"
    assert "setHazirlik(false)" in panel, "vazgec hazirligi kapatmiyor"


# ── 3) Hazirlik SAVURGAN ya da GURULTULU olmamali (kendi eklediğim kusurlar) ────


def test_KRITIK_oneri_hatasinda_RETRY_FIRTINASI_olmaz(panel):
    """🔴 KENDI EKLEDIGIM KUSUR: oneri alinamazsa bayrak sifirlaniyordu ve efekt HER KAREYE
    bagli oldugu icin ~400 ms'de bir yeniden deneniyordu. `apiPost` sessiz olmadigi icin her
    denemede kullaniciya "Sunucu Hatasi" bildirimi basardi — yani duzeltilen arizanin daha
    hizli tekrarlayan bir surumu.

    SOZLESME: basarisizlikta (a) bekleme suresi uygulanir, (b) istek SESSIZ olur ve sebep
    hazirlik seridinde gosterilir (kullanici bildirim yagmuruna tutulmaz).
    """
    i = panel.find("oneriIstendiRef.current = true;")
    assert i > 0, "otomatik oneri efekti bulunamadi"
    # ⚠️ Pencere GERIYE de acilir: bekleme kapisi bayrak atamasindan ONCE gelir (erken-donus).
    # Ilk yazimda yalniz ileri bakiyordum ve test DOGRU kodu yanlis-KIRMIZI gosterdi.
    blok = panel[max(0, i - 600) : i + 1800]
    assert "silent: true" in blok, "oneri istegi SESSIZ degil — her basarisiz denemede kullaniciya hata bildirimi basar"
    # ⚠️ Referansin VARLIGI yetmez, KAPI olarak kullanilmasi gerekir: ilk yazimda yalniz
    # "oneriBeklemeRef gecıyor mu" diye bakiyordum ve kapiyi silen mutasyon KACTI (bayrak
    # basarisizlik dalinda hala set ediliyordu). Olcu: erken-donus karsilastirmasi.
    assert re.search(r"if \(Date\.now\(\) < oneriBeklemeRef\.current\)\s*return", blok), (
        "basarisizlikta bekleme KAPISI yok — her karede yeniden denenir (retry firtinasi)"
    )
    assert "oneriBeklemeRef.current = Date.now() +" in blok, "bekleme suresi hic kurulmuyor"


def test_KRITIK_hazirlikta_kare_hizi_DUSUK(panel):
    """Sunucu organ lokalizasyonunu EN FAZLA 10 sn'de bir calistirir (_ORGAN_LOCALIZE_INTERVAL_S).
    Hazirlikta 400 ms'de bir kare yuklemek her ise yarar lokalizasyon basina ~25 bosa yukleme
    demektir: pil, isinma ve mobil veri. Kapali dongu SEANSINDA 400 ms dogrudur; hazirlikta degil.
    """
    m = re.search(r"setInterval\(capture,\s*([A-Za-z0-9_ ?:.]+)\)", panel)
    assert m, "kare yakalama araligi bulunamadi"
    ifade = m.group(1)
    assert "hazirlik" in ifade or "HAZIRLIK" in ifade.upper(), (
        f"hazirlikta kare araligi seans ile AYNI ({ifade!r}) — sunucu 10 sn'de bir lokalize "
        "ederken ~25 kat fazla kare yuklenir"
    )


def test_KARSIT_KANIT_SEANSTA_kare_hizi_DUSMEZ(panel):
    """⚠️ Kapali dongu: hayvan hareket ettikce duty/faz guncellenir. Seans sirasinda kare
    hizini dusurmek tedavinin takibini bozardi — tasarruf YALNIZ hazirlikta."""
    # ⚠️ Once "400" in panel yaziyordu: dosyadaki HERHANGI bir 400 (piksel, timeout, HTTP kodu)
    # bunu yesil yapardi ve seans hizi 1500'e dusurulse bile testin haberi olmazdi. Sabitin
    # KENDISINI ve interval'in DOGRU dali sectigini olc.
    m = re.search(r"const\s+KARE_ARALIK_SEANS_MS\s*=\s*(\d+)", panel)
    assert m, "KARE_ARALIK_SEANS_MS sabiti yok"
    seans = int(m.group(1))
    assert seans == 400, f"seans kare araligi degismis: {seans} ms (takip bozulur)"

    h = re.search(r"const\s+KARE_ARALIK_HAZIRLIK_MS\s*=\s*(\d+)", panel)
    assert h, "KARE_ARALIK_HAZIRLIK_MS sabiti yok"
    hazirlik = int(h.group(1))
    assert hazirlik > seans, f"hazirlik ({hazirlik} ms) seanstan hizli/esit — tasarruf yanlis yerde yapiliyor"

    # ⚠️ Asil kilit: dallar TERS baglanirsa iki sabit de dogru kalir ama seans yavaslar.
    t = re.search(r"setInterval\(\s*\w+\s*,\s*running\s*\?\s*(\w+)\s*:\s*(\w+)\s*\)", panel)
    assert t, "kare interval'i `running` dalina gore secilmiyor"
    assert t.group(1) == "KARE_ARALIK_SEANS_MS" and t.group(2) == "KARE_ARALIK_HAZIRLIK_MS", (
        f"interval dallari TERS: running -> {t.group(1)}, hazirlik -> {t.group(2)}"
    )


# ── 4) Tibbi cihaz sertlestirmeleri (sahip onayi 2026-08-24) ────────────────────


def test_KRITIK_guven_operatore_GOSTERILIR(panel):
    """⚠️ `_MIN_RELIABILITY = 0.3` — yani %30 guvenle "konumlandi" denebiliyor ve tedavi
    parametreleri O OLCUMDEN hesaplaniyor. Operator ekranda bir sayi gormedigi surece sinirda
    gecen bir konumlandirma ile net olani AYIRT EDEMEZ. Esik degistirilmedi (yanlis-negatifleri
    artirirdi); yapilan sey karari BILGILENDIRMEK."""
    # Guven METNE girmeli (sadece hesaplanip kullanilmamasi yetmez).
    assert re.search(r"güven %\$\{guvenYuzde\}", panel), (
        "hazirlik seridinde GUVEN gosterilmiyor — %30 ile %95 ayni gorunur"
    )
    assert "DUSUK_GUVEN" in panel or "dusukGuven" in panel, (
        "dusuk guven ayrica isaretlenmiyor — operator sinirda gecen olcumu fark etmez"
    )


def test_KRITIK_TEK_kare_yargisi_yetmez(panel):
    """Bir SANSLI kare oneriyi tetikliyordu. Tibbi bir konumlandirma adiminda ust uste tutarli
    olcum istemek savunulabilir; maliyeti birkac saniyelik gecikme."""
    m = re.search(r"ARDISIK_ONAY\s*=\s*(\d+)", panel)
    assert m and int(m.group(1)) >= 2, "ardisik onay sayisi 2'den az — tek kare ile ayni sey"
    # ⚠️ Sabitin VARLIGI yetmez, KAPI olarak ZORLANMASI gerekir: ilk yazimda yalniz adin
    # gecmesine bakiyordum ve erken-donusu silen mutasyon KACTI (bu turda ucuncu kez ayni
    # zayiflik: "var mi" ile "uygulaniyor mu" ayni sey degil).
    assert re.search(r"if \(ardisikRef\.current < ARDISIK_ONAY\)\s*return", panel), (
        "ardisik sayac KAPI olarak kullanilmiyor — tek kare yine oneriyi tetikler"
    )
    # Olcum koptugunda sayac SIFIRLANMALI, yoksa "ardisik" degil "TOPLAM" olur (arada kaybolan
    # olcumler sayilmaya devam eder ve tek-kare yargisina geri donulur).
    # ⚠️ SIFIRLAMAYI KOPMA DALINDA ara: `ardisikRef.current = 0` panelde baska yerlerde de
    # geciyor (Vazgec, yeniden baslatma) ve genel arama mutasyonu KACIRDI.
    assert re.search(r"if \(!mobileResult\?\.detected\)\s*\{[^}]*ardisikRef\.current = 0", panel, re.S), (
        "olcum KOPUNCA sayac sifirlanmiyor — 'ardisik' degil 'toplam' sayilir"
    )
    # Efekt bagimliligi NESNE olmali: `.detected` boolean'i true'da sabitlenir, efekt bir daha
    # kosmaz ve sayac 1'de takilirdi (olculdu: oneri HIC istenmiyordu).
    assert re.search(r"\}, \[hazirlik, mobileResult, organId, duration\]\);", panel), (
        "efekt bagimliligi nesne degil — ardisik sayac ilerlemez ve oneri HIC istenmez"
    )


def test_KRITIK_hazirlik_SONSUZA_kadar_surmez(panel):
    """Hayvan hic bulunamazsa hazirlik sonsuza kadar kare yukluyordu: pil, isinma, mobil veri.
    Once SOMUT yonlendirme, sonra otomatik durma."""
    assert "HAZIRLIK_UYARI_MS" in panel, "gecikmede somut yonlendirme yok"
    assert "HAZIRLIK_TAVAN_MS" in panel, "hazirlik icin ust sinir yok (sonsuz kare akisi)"
    # Yonlendirme EYLEM soylemeli ("tekrar deneyin" degil).
    for ipucu in ("ışığı", "mesafe"):
        assert ipucu in panel, f"yonlendirme somut degil: '{ipucu}' gecmiyor"


def test_KARSIT_KANIT_tavan_SEANSI_kesmez(panel):
    """⚠️ Ust sinir YALNIZ hazirliga aittir. Suren bir otonom seansi kare tavaniyla kesmek
    tedaviyi yarida birakirdi — seansin kendi sure-watchdog'u vardir."""
    # ⚠️ KULLANIMI ara, TANIMI degil: `panel.find` ilk gecisi (sabit tanimi) buluyordu ve
    # pencere kullanim blogunu hic gormuyordu (bu turda ucuncu kez ayni tuzak).
    m = re.search(r"if \(gecen >= HAZIRLIK_TAVAN_MS\)\s*\{(.*?)\n      \}", panel, re.S)
    assert m, "tavan KULLANIMI bulunamadi (yalniz sabit tanimli olabilir)"
    blok = m.group(1)
    assert "setHazirlik(false)" in blok, "tavan dolunca hazirlik kapatilmiyor"
    # Tavan YALNIZ hazirliga ait: seansi durduran bir cagri BURADA olmamali.
    assert "/ai/pro/stop" not in blok, (
        "tavan SEANSI da durduruyor — suren otonom tedavi yarida kesilir (onun kendi sure-watchdog'u var)"
    )
    m2 = re.search(r"useEffect\(\(\) => \{\s*if \(!hazirlik\)", panel)
    assert m2, "hazirlik saati `hazirlik` degilken erken donmuyor — seansta da kosardi"


def test_KRITIK_dogrulama_asamasi_KONUMLANDI_IDDIA_ETMEZ(panel):
    """⚠️ Asama seridi hekimin gordugu TEK gostergedir; asamayi yanlis soylemek sertlestirmeyi
    gorunmez kilar.

    Ilk yazdigimda dogrulama dalinin sonunda "· konumlandi" fragmani kalmisti: ekran daha 1/2
    olcumdeyken "konumlandi" diyordu. Operator, iki-olcum kapisinin ise yaradigini goremez ve
    yarim dogrulanmis bir konumu tamamlanmis sanardi. Dort asama BIRBIRINDEN AYIRT EDILEBILIR
    kalmali: hayvan yok / hayvan var-organ yok / gorüldü-dogrulaniyor / konumlandi.
    """
    m = re.search(r"const asamaMetni = (.*?);\n\n", panel, re.S)
    assert m, "asamaMetni bulunamadi"
    blok = m.group(1)

    dallar = re.findall(r"`([^`]*)`", blok)
    assert len(dallar) == 4, f"4 asama metni bekleniyordu, {len(dallar)} bulundu: {dallar}"

    dogrulama = [d for d in dallar if "ARDISIK_ONAY}" in d and "guvenYuzde" not in d]
    assert len(dogrulama) == 1, f"dogrulama dali tekil degil: {dogrulama}"
    metin = dogrulama[0]

    # ⚠️ Asil kilit: dogrulama dali tamamlanmayi IDDIA EDEMEZ (aksansiz yazim dahil).
    for yasak in ("konumlandı", "konumlandi"):
        assert yasak not in metin, (
            f"dogrulama asamasi '{yasak}' diyor — 1/2 olcumdeyken konum tamamlanmis gorunur: {metin!r}"
        )
    # Ve gercekten devam ettigini soylemeli.
    assert "doğrulanıyor" in metin, f"dogrulama asamasi surdugunu soylemiyor: {metin!r}"

    # Karsit taraf: tamamlanma dali konumlandi DEMELI, yoksa iki asama ayirt edilemez.
    tamam = [d for d in dallar if "guvenYuzde" in d]
    assert len(tamam) == 1 and "konumlandı" in tamam[0], f"tamamlanma dali konumu bildirmiyor: {tamam}"
