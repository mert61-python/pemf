# -*- coding: utf-8 -*-
"""I18N-P1 · 11b — launcher Rust uygulaması (`launcher/app/src/main.rs`): operatöre giden `Err(String)` iletileri `pemf_launcher_core::dil::t / t_ile`
(katalog `launcher/i18n → rust.hata.*`).

⚠️ TR çıktı ESKİ literallerle BAYT BAYT aynı (beklenen metinler taşıma ÖNCESİ kaynaktan sabitlenmiştir — aşağıdaki tablo); EN katalogda Türkçe harf yok,
yer tutucu kümesi TR ile aynı (K-1 de denetler); her anahtar GERÇEKTEN main.rs'de kullanılıyor; arayüz metne göre dallanmaları iki dilde eşleşiyor.
MUTASYON: katalog TR değeri değişirse / main.rs'de t()'yi ham metne döndüren çağrı kalırsa / UI "seans" eşleşmesi tek dile dönerse → KIRMIZI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from i18n_yardimci import launcher_ui

KOK = Path(__file__).resolve().parents[1]
MAIN = KOK / "launcher" / "app" / "src" / "main.rs"
HTML = KOK / "launcher" / "app" / "ui" / "index.html"
TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")

#: ESKİ literaller (yer tutucular `{{ad}}`; biçim dizgisindeki `{e}` / `{}` → adlı yer tutucu).
ESKI_TR = {
    "rust.hata.arkaPlanIndirmeCoktu": "arka plan indirme çöktü: {{e}}",
    "rust.hata.ayrintiYok": "ayrıntı yok",
    "rust.hata.backendKurulDegil": "Backend henüz kurulu değil — önce kurulumu tamamlayın.",
    "rust.hata.baslatilamadi": "başlatılamadı ({{yol}}): {{e}} — Defender ASR / AppLocker %TEMP%'teki kopyayı engelliyor olabilir",
    "rust.hata.baslatmaGorevCoktu": "başlatma görevi çöktü: {{e}}",
    "rust.hata.cikisGorevCoktu": "çıkış görevi çöktü: {{e}}",
    "rust.hata.exeYoluOkunamadi": "exe yolu okunamadı: {{e}}",
    "rust.hata.girisGorevCoktu": "giriş görevi çöktü: {{err}}",
    "rust.hata.guncellemeBackendYanitsiz": "Backend yanıt vermiyor, seans sürüyor olabilir — güncelleme ertelendi.",
    "rust.hata.guncellemeDenetimiGorevCoktu": "güncelleme denetimi görevi çöktü: {{e}}",
    "rust.hata.guncellemeDogrulanamadi": "Güncelleme doğrulanamadı: {{e}}",
    "rust.hata.guncellemeGorevCoktu": "güncelleme görevi çöktü: {{e}}",
    "rust.hata.guncellemeSeansSuruyor": "Şu anda bir seans sürüyor — güncelleme seans bittikten sonra yapılacak.",
    "rust.hata.guncellemeSha256Yok": "Güncelleme SHA256 yok — güvenlik gereği atlandı",
    "rust.hata.guncellemeYoluGuvensiz": "Güncelleme yolu güvensiz karakter içeriyor",
    "rust.hata.guvenlikDuvariGorevCoktu": "Güvenlik duvarı görevi çöktü: {{e}}",
    "rust.hata.guvenlikDuvariIzinYok": "Yönetici izni verilmedi — güvenlik duvarı kuralı eklenemedi.",
    "rust.hata.indirmeAdresiGecersizKarakter": "Geçersiz karakter içeren indirme adresi reddedildi",
    "rust.hata.indirmeAdresiIzinsiz": "İzin verilmeyen indirme adresi: {{url}}",
    "rust.hata.kaldiriciYok": "Kaldırıcı (uninstall.exe) bulunamadı. Windows 'Ayarlar → Uygulamalar'dan kaldırabilirsiniz.",
    "rust.hata.kaldiriciYoluGuvensiz": "Kaldırıcı yolu güvensiz karakter içeriyor",
    "rust.hata.kaldiriciYoluUtf8": "kaldırıcı yolu UTF-8 değil",
    "rust.hata.kaldirmaBasarisiz": "Kaldırma başarısız (uygulama çalışıyor olabilir): {{e}}",
    "rust.hata.kaldirmaHazirligiCoktu": "kaldırma hazırlığı çöktü: {{e}}",
    "rust.hata.kaydedilemedi": "Kaydedilemedi: {{e}}",
    "rust.hata.klasorSecici": "Klasör seçici çalışmadı (PowerShell çıkış kodu {{kod}}): {{ayrinti}}. PowerShell bu makinede kısıtlı olabilir (ConstrainedLanguage/WDAC) — bu mesajı BT yöneticinize iletin.",
    "rust.hata.klasorSeciciAcilamadi": "Klasör seçici açılamadı: {{e}}",
    "rust.hata.klasorSeciciGorevCoktu": "Klasör seçici görevi çöktü: {{e}}",
    "rust.hata.kopyalanamadi": "kopyalanamadı ({{yol}}): {{e}}",
    "rust.hata.kurulumBackendYanitsiz": "Backend yanıt vermiyor, seans sürüyor olabilir — kurulum ertelendi.",
    "rust.hata.kurulumGorevCoktu": "kurulum görevi çöktü: {{e}}",
    "rust.hata.launcherYoluUtf8": "launcher yolu UTF-8 değil",
    "rust.hata.manifestGorevCoktu": "manifest görevi çöktü: {{e}}",
    "rust.hata.manifestIndirilemedi": "Manifest indirilemedi: {{e}}",
    "rust.hata.onarimGorevCoktu": "onarım görevi çöktü: {{e}}",
    "rust.hata.onarimSeansSuruyor": "Şu anda bir seans sürüyor — onarım seans bittikten sonra yapılabilir.",
    "rust.hata.otoGuncellemeDesteklenmiyor": "Bu platformda oto-güncelleme desteklenmiyor",
    "rust.hata.oturumOkumaGorevCoktu": "oturum okuma görevi çöktü: {{e}}",
    "rust.hata.oturumYenilemeGorevCoktu": "oturum yenileme görevi çöktü: {{e}}",
    "rust.hata.pencereYoluUtf8": "pencere yolu UTF-8 değil",
    "rust.hata.platformDesteklenmiyor": "Bu platformda desteklenmiyor",
    "rust.hata.profilKaldirmaGorevCoktu": "profil kaldırma görevi çöktü: {{e}}",
    "rust.hata.profilKaldirmaSeansSuruyor": "Şu anda bir seans sürüyor — profil kaldırma seans bittikten sonra yapılabilir.",
    "rust.hata.seansBasladiGuncellemeErtelendi": "Seans başladı — güncelleme kuruldu değil, ertelendi. İndirilen dosya saklandı.",
    "rust.hata.setupYoluUtf8": "setup yolu UTF-8 değil",
    "rust.hata.temizlikGorevCoktu": "temizlik görevi çöktü: {{e}}",
    "rust.hata.yardimciBaslatilamadi": "yardımcı başlatılamadı ({{yol}}): {{e}}",
    "rust.hata.yardimciBatchYoluGuvensiz": "yardımcı batch yolu güvensiz karakter içeriyor",
    "rust.hata.yardimciBatchYoluUtf8": "yardımcı batch yolu UTF-8 değil",
    "rust.hata.yardimciHemenSonlandi": "Yardımcı komut dosyası hemen sonlandı (cmd çıkış kodu {{kod}}) — yol: {{yol}}. Geçici klasör yolunda özel karakter (&, ^) olabilir; %TEMP% değişkenini denetleyin.",
    "rust.hata.yoneticiIzniVerilmedi": "Yönetici izni verilmedi.",
    "rust.hata.yukseltmeBaslatilamadi": "Yükseltme başlatılamadı: {{e}}",
    "rust.pencere.guncelleniyor": "PEMF Vet — güncelleniyor",
}


def _kat(dil: str) -> dict:
    import json

    return json.loads((KOK / "launcher" / "i18n" / f"{dil}.json").read_text(encoding="utf-8"))["rust"]


def _duz(d: dict, onek: str = "") -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_duz(v, onek + k + "."))
        else:
            out[onek + k] = v
    return out


def _tr() -> dict:
    return {"rust." + k: v for k, v in _duz(_kat("tr")).items()}


def _en() -> dict:
    return {"rust." + k: v for k, v in _duz(_kat("en")).items()}


@pytest.mark.parametrize("anahtar", sorted(ESKI_TR))
def test_KRITIK_TR_deger_eski_literalle_bayt_bayt_ayni_EN_dolu_Turkce_harfsiz_ayni_yer_tutucular(anahtar):
    tr, en = _tr(), _en()
    assert tr[anahtar] == ESKI_TR[anahtar], f"TR değer eski literalden FARKLI: {anahtar}"
    assert en.get(anahtar), f"EN boş: {anahtar}"
    assert not TR_HARF.search(en[anahtar]), f"EN'de Türkçe harf: {anahtar}: {en[anahtar]!r}"
    yer = lambda s: sorted(re.findall(r"\{\{(\w+)\}\}", s))  # noqa: E731
    assert yer(tr[anahtar]) == yer(en[anahtar]), f"yer tutucu kümesi ayrışmış: {anahtar}"


def test_KRITIK_her_anahtar_main_rs_de_KULLANILIYOR_ve_eski_Turkce_literal_kalmadi():
    kaynak = MAIN.read_text(encoding="utf-8")
    kullanilmayan = [k for k in ESKI_TR if f'"{k}"' not in kaynak]
    assert not kullanilmayan, f"katalogda var ama main.rs'de çağrılmıyor: {kullanilmayan}"
    kalan = [(k, m) for k, m in ESKI_TR.items() if "{{" not in m and f'"{m}"' in kaynak]
    assert not kalan, f"ESKİ Türkçe literal main.rs'de hâlâ duruyor: {kalan}"


def test_klasor_secici_aciklamasi_katalogdan_ve_tek_tirnak_kacislanir():
    kaynak = MAIN.read_text(encoding="utf-8")
    assert 'dil::t("rust.klasorSecici.aciklama").replace(\'\\\'\', "\'\'")' in kaynak, (
        "PowerShell açıklamasında tek tırnak kaçışı yok"
    )
    assert "Yedeklerin kopyalanacagi harici disk" not in kaynak, "açıklama metni koda geri gömülmüş"
    assert _tr()["rust.klasorSecici.aciklama"] == "Yedeklerin kopyalanacagi harici disk / ag paylasimi"
    assert "'" not in _en()["rust.klasorSecici.aciklama"], "EN açıklamada tek tırnak: PowerShell betiği kırılır"


def test_pencere_basligi_ve_yok_yedekleri_katalogdan():
    assert _tr()["rust.pencere.guncelleniyor"] == "PEMF Vet — güncelleniyor"
    assert _en()["rust.pencere.guncelleniyor"] == "PEMF Vet — updating"
    assert _tr()["rust.hata.yok"] == "yok" and _en()["rust.hata.yok"] == "none"
    kaynak = MAIN.read_text(encoding="utf-8")
    assert 'w.set_title(&pemf_launcher_core::dil::t("rust.pencere.guncelleniyor"))' in kaynak


def test_arayuz_seans_eslesmesi_iki_dilde_ve_guncelleme_etiketi_veri_kimligi_cevrilir():
    """Rust iletisi dile göre değişir → arayüzün metne göre dallanması iki dilde eşleşmeli (`seans` / `session`)."""
    ham = HTML.read_text(encoding="utf-8")
    assert re.search(r"if \(/seans\|session/i\.test\(m\)\) notice\(t\(\)\.rtBusy\); else fail\(e\);", ham)
    for anahtar in (
        "rust.hata.onarimSeansSuruyor",
        "rust.hata.profilKaldirmaSeansSuruyor",
        "rust.hata.guncellemeSeansSuruyor",
    ):
        assert re.search(r"seans|session", _tr()[anahtar], re.I) and re.search(r"seans|session", _en()[anahtar], re.I)
    # Progress.what = "Güncelleme" VERİ kimliği (Rust değişmez) → gösterimde ui.updateWhat
    assert 'what === "Güncelleme" ? t().updateWhat' in ham
    assert launcher_ui("tr")["updateWhat"] == "Güncelleme" and launcher_ui("en")["updateWhat"] == "Update"
