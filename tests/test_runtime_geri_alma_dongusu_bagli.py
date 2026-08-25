# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""GERI ALMA DONGUSU KIRICI URETIM KODUNA BAGLI (denetim 2026-08-23, bulgu C2).

⚠️ NEDEN AYRI BIR KAPI: mekanizmanin KENDISI `launcher/core/tests/runtime_geri_alma_dongusu.rs`
ile kilitli — ama yazilip BAGLANMAMIS bir mekanizma sessiz no-op'tur. Bu depoda tam olarak o
yasandi (jeton sistemi 16 testle kilitliydi ve hicbir uretim kodundan cagrilmiyordu; bayrak
acilsa bile davranis DEGISMEYECEKTI). Bu dosya UC baglanti noktasini olcer:

  1. GERI ALMADA sayac artar        → yoksa dongu hic sayilmaz, koruma olu dogar.
  2. BASARIDA sayac temizlenir      → yoksa eski basarisizliklarin kalintisi GERCEK bir
                                       guncellemeyi kalici bloklar (korumadan beter).
  3. KARARDA sayac okunur + UI dali → yoksa sayac yalniz dosyaya yazilan bir sayidir.

SOZLESME: sinir dolunca YALNIZ otomatik kurulum durur. Bildirim ve elle "Onar" ETKILENMEZ;
`needed()` degismez (arizayi gorunmez kilmak, arizadan beterdir).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_MAIN = _KOK / "launcher" / "app" / "src" / "main.rs"
_FLOW = _KOK / "launcher" / "core" / "src" / "flow.rs"
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"


@pytest.fixture(scope="module")
def main_rs() -> str:
    return _MAIN.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def flow_rs() -> str:
    return _FLOW.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def ui() -> str:
    return _UI.read_text(encoding="utf-8", errors="replace")


def test_KRITIK_1_geri_almada_sayac_ARTAR(main_rs):
    """Saglik kapisi dusup geri alinirken deneme kaydedilmezse dongu hic sayilmaz."""
    # Geri alma dalini bul: `guncellemeyi_geri_al` cagrisinin bulundugu blok.
    i = main_rs.find("flow::guncellemeyi_geri_al(&root2, &geri)")
    assert i > 0, "geri alma dali bulunamadi — main.rs bicimi degismis olabilir"
    blok = main_rs[max(0, i - 900) : i]
    assert "geri_almayi_kaydet" in blok, (
        "geri alma aninda deneme sayaci ARTIRILMIYOR — bozuk bir yayin her acilista backend'i "
        "oldurup ~1,19 GB acip 180 sn bekletip geri alir; tek cikis yolu yayincinin rollout:0 "
        "yazmasidir (bulgu C2)"
    )


def test_KRITIK_1b_IC_YOL_deterministik_hata_SAYILIR(main_rs, flow_rs):
    """🔴 C2 İÇ-YOL (denetim 2026-08-24): sağlık-kapısı geri alması (backend açıldı ama sağlıksız)
    sayacı artırıyordu ama `update_installed` İÇİNDEKİ DETERMİNİSTİK hatalar (kilitli model / AV
    karantinası / eksik-exe / bozuk manifest) sayılmıyordu → o hata sınıfı döngü kırıcısına
    (C2/`otomatik_durduruldu`) HİÇ takılmadan her açılışta backend'i öldürüp ~1,19 GB açıp geri
    alıyordu. `apply_runtime_update`'in `update_installed` Err dalı, hata deterministikse (Cancel/
    Pause/geçici-ağ DEĞİL) deneme sayacını yazmalı; sınıflandırma `flow::hata_deterministik_mi`de."""
    assert "flow::update_installed(" in main_rs, "apply_runtime_update update_installed çağrısı yok — main.rs değişmiş"
    # ⚠️ YALNIZ update_installed'in Err(e) DALINA çıpalan (sağlık-kapısı geri almaları da
    # geri_almayi_kaydet çağırır; genış pencere onları kapsayıp mutasyonu KAÇIRIRDI). Err(e) dalı
    # match'in son kolu; ondan match kapanışına (`};`) kadar olan gövde ölçülür.
    j = main_rs.find("Err(e) => {")
    assert j > 0, "update_installed Err(e) dalı bulunamadı — main.rs biçimi değişmiş"
    blok = main_rs[j : main_rs.find("};", j)]
    assert "hata_deterministik_mi" in blok and "geri_almayi_kaydet" in blok, (
        "update_installed'ın Err dalı deterministik hataları SAYMIYOR — kilitli-model/AV/eksik-exe "
        "sınıfı döngü kırıcısına takılmaz, her açılışta backend öldürülüp deps açılır (C2 iç-yol)"
    )
    # Sınıflandırıcı Cancel/Pause'u ve GEÇİCİ ağ hatalarını DIŞLAMALI (kör sayım kullanıcı iptalini
    # döngü-kırıcıya saydırır / geçici ağ hatası güncellemeyi kalıcı bloklardı).
    m = re.search(r"pub fn hata_deterministik_mi\(.*?\n\}", flow_rs, re.S)
    assert m, "hata_deterministik_mi sınıflandırıcısı yok"
    assert "is_retriable" in m.group(0), "geçici ağ hataları (is_retriable) DIŞLANMIYOR — deneme yanlış sayılır"
    assert "Cancelled" in m.group(0) and "Paused" in m.group(0), "kullanıcı iptali/duraklatması DIŞLANMIYOR"


def test_KRITIK_2_basarida_sayac_TEMIZLENIR(main_rs):
    """Temizlenmezse eski basarisizliklarin kalintisi GERCEK bir guncellemeyi bloklar."""
    i = main_rs.find("flow::guncellemeyi_onayla(&root2, &geri)")
    assert i > 0, "onaylama dali bulunamadi"
    blok = main_rs[i : i + 500]
    assert "clear_runtime_attempt" in blok, (
        "basarili guncellemeden sonra sayac SIFIRLANMIYOR — birikmis denemeler bir sonraki "
        "gercek guncellemeyi kalici olarak engelleyebilir"
    )


def test_KRITIK_3_kararda_sayac_OKUNUR(flow_rs):
    """`pending_updates` sayaci okumazsa yazilan sayinin hicbir etkisi olmaz."""
    assert "runtime_otomatik_izinli" in flow_rs, (
        "guncelleme karari deneme sayacini HIC okumuyor — sayac yalniz diske yazilan olu bir sayi"
    )
    assert "otomatik_durduruldu" in flow_rs, "karar sonucu plana tasinmiyor"


def test_KRITIK_3b_KOMUT_bayragi_UIya_TASIR(main_rs):
    """⚠️ EKSİK KÖPRÜ (denetim 2026-08-24, C2 düzeltmesinin KENDİSİNDE bulundu):

    `test_KRITIK_3` flow'un bayrağı HESAPLADIĞINI, `test_KRITIK_4` UI'nın OKUDUĞUNU ölçer — ama
    ikisinin arasındaki `check_runtime_update` komutu bayrağı serileştirmezse zincir sessizce
    kopar. Üretimde tam bu oldu: alan `flow.rs`'te hesaplanıp UI'ya HİÇ taşınmadı → döngü kırıcı
    ölüydü, bozuk yayın her açılışta yeniden kurulup geri alındı; iki uçtaki test yine yeşildi.

    Davranışsal kilit `app/src/main.rs` birim testinde (`plan_to_json_otomatik_durduruldu_tasir`,
    üretilen JSON değeri ölçülür); bu kapı da metin düzeyinde köprünün var olduğunu garanti eder.
    """
    i = main_rs.find("fn plan_to_json")
    assert i > 0, "plan_to_json köprü fonksiyonu bulunamadi — main.rs check_runtime_update bicimi degismis"
    # UI'ya giden JSON'u kuran gövde bayragi TASIMALI (flow -> KOMUT -> UI zincirinin orta halkasi).
    govde = main_rs[i : i + 1400]
    assert '"otomatik_durduruldu": plan.otomatik_durduruldu' in govde, (
        "check_runtime_update komut ciktisi otomatik_durduruldu bayragini UI'ya TASIMIYOR — flow "
        "hesaplasa ve UI okusa bile zincir ortada kopuk, geri-alma dongu kirici olu (bulgu C2)"
    )


def test_KRITIK_4_UI_otomatik_kurulumu_DURDURUR(ui):
    """Bayrak plana konsa da UI okumazsa kurulum yine tekrarlanir."""
    assert "plan.otomatik_durduruldu" in ui, (
        "UI `otomatik_durduruldu` bayragini OKUMUYOR — kurulum yine her acilista tekrarlanir"
    )
    i = ui.find("plan.otomatik_durduruldu")
    blok = ui[i : i + 260]
    assert "return false" in blok, "bayrak okunuyor ama otomatik kurulum durdurulmuyor"


def test_KRITIK_5_kullaniciya_SEBEP_soylenir(ui):
    """⚠️ Sessizce durmak kabul edilemez: kullanici cihazinin eski surumde TAKILI kaldigini
    bilmeli ve elle zorlayabilmeli (self-update'teki ayni sozlesme)."""
    i = ui.find("plan.otomatik_durduruldu")
    blok = ui[i : i + 260]
    assert "notice(" in blok, "otomatik kurulum SESSIZCE durduruldu — kullanici sebebini gormez"
    assert ui.count("rtBlocked:") == 2, "bildirim metni iki dilde tanimli degil"
    # Metin ne YAPILACAGINI soylemeli (yalniz "hata oldu" demek akisi cikmaza sokar).
    # ⚠️ Desen KACISLI TIRNAGI da yutmali: metnin kendisi `\"Onar\"` iciyor ve naif `[^"]+`
    # dizeyi tam orada kesiyor (ilk yazimda yanlis-KIRMIZI verdi).
    tr = re.search(r'rtBlocked:\s*"((?:[^"\\]|\\.)*)"', ui)
    assert tr and "Onar" in tr.group(1), f"metin cikis yolunu ('Onar') soylemiyor: {tr and tr.group(1)!r}"


def test_KARSIT_KANIT_needed_bayraktan_ETKILENMEZ(flow_rs):
    """Bayragi `needed()`e baglamak arizayi GORUNMEZ kilardi: guncelleme hala gereklidir,
    yalniz otomatik kurulumu durur. `needed()` yalnizca katman/profil bayatligina bakmali."""
    m = re.search(r"pub fn needed\(&self\) -> bool \{(.*?)\}", flow_rs, re.S)
    assert m, "needed() bulunamadi"
    assert "otomatik_durduruldu" not in m.group(1), (
        "needed() bayraga baglanmis — guncelleme 'gerekli degil' gorunur, bildirim ve geri cagirma uyarisi da kaybolur"
    )


def test_KARSIT_KANIT_elle_ONAR_yolu_kapanmaz(main_rs):
    """Sinir yalniz OTOMATIK yolu keser; kullanicinin 'Onar'i kapilanmaz."""
    i = main_rs.find("async fn repair")
    assert i > 0, "repair komutu bulunamadi"
    blok = main_rs[i : i + 2500]
    assert "runtime_otomatik_izinli" not in blok, (
        "elle 'Onar' deneme sayacina takiliyor — kullanicinin son cikis yolu kapanmis"
    )
