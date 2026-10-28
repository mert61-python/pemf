# -*- coding: utf-8 -*-
"""I18N-P1 · 11c — launcher çekirdeği (`launcher/core/src/*.rs`): operatöre giden hata / ilerleme iletileri `crate::dil::t / t_ile`
(katalog `launcher/i18n → rust.*`).

⚠️ TR çıktı ESKİ literallerle BAYT BAYT aynı (beklenen metinler taşıma ÖNCESİ kaynaktan sabitlenmiştir — aşağıdaki tablo); EN katalogda Türkçe harf yok,
yer tutucu kümesi TR ile aynı; her anahtar çekirdekte GERÇEKTEN kullanılıyor; arayüzün metne göre dallanmaları (DNS · yanlış parola · çevrimdışı) iki dilde eşleşiyor.
Güvenlik / akış mantığı DEĞİŞMEDİ (Rust çekirdek testleri 338 yeşil): yalnız iletinin üretildiği yer.
MUTASYON: katalog TR değeri değişirse / çekirdekte t()'yi ham metne döndüren çağrı kalırsa / UI eşleşmesi tek dile dönerse → KIRMIZI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
CEKIRDEK = KOK / "launcher" / "core" / "src"
HTML = KOK / "launcher" / "app" / "ui" / "index.html"
TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")

#: ESKİ literaller (yer tutucular `{{ad}}`; biçim dizgisindeki `{e}` / `{}` / `{0}` → adlı yer tutucu).
ESKI_TR = {
    "rust.acma.butce": "açılım boyut bütçesi aşıldı",
    "rust.acma.butceSymlink": "açılım boyut bütçesi aşıldı (symlink)",
    "rust.acma.cokGirdi": "çok fazla girdi: {{adet}}",
    "rust.acma.disinaYazma": "GÜVENLİK: arşiv girdisi kurulum dizininin dışına yazmaya çalıştı: {{yol}}",
    "rust.acma.dizinDisinaCikiyor": "{{ad}} -> {{hedef}} (kurulum dizini disina cikiyor)",
    "rust.acma.dosyaSistemi": "dosya sistemi hatası: {{hata}}",
    "rust.acma.iptal": "açma iptal edildi",
    "rust.acma.kaynakLimiti": "GÜVENLİK: arşiv kaynak-limitini aştı (zip-bomb?): {{ayrinti}}",
    "rust.acma.mutlakHedef": "{{ad}} -> {{hedef}} (mutlak hedef)",
    "rust.acma.profilAltinaYazamaz": "{{ad}} (profil paketi '{{profil}}' altına yazamaz — doğrulanmış runtime/durum dosyası)",
    "rust.acma.symlinkDesteklenmiyor": "{{ad}}: bu platformda sembolik link desteklenmiyor",
    "rust.acma.symlinkDisari": "{{ad}} (hedef dizin symlink/junction üzerinden kurulum kökünün DIŞINA çözümlendi)",
    "rust.acma.zipOkunamadi": "zip okunamadı: {{hata}}",
    "rust.ag.acilamadi": "{{yol}} açılamadı: {{hata}}",
    "rust.ag.agDosyaHatasi": "ağ/dosya hatası: {{hata}}",
    "rust.ag.aktarimBasarisiz": "indirme aktarımı başarısız: {{hata}}",
    "rust.ag.aralikVerilmedi": "sunucu istenen aralığı vermedi (beklenen ofset {{beklenen}}, gelen {{gelen}}) — .part sıfırlandı",
    "rust.ag.beklenenRepo": "github.com{{yol}} — beklenen repo {{repo}}",
    "rust.ag.boyutSiniri": "indirme boyut sınırını aştı ({{done}} > {{tavan}} bayt) — iptal edildi",
    "rust.ag.dns": "ağ adı çözümlenemedi (DNS): {{hata}}",
    "rust.ag.duraklatildi": "indirme duraklatıldı",
    "rust.ag.gorevSonlandi": "{{etiket}}: ağ görevi beklenmedik şekilde sonlandı",
    "rust.ag.hostBeklenmeyen": "Host beklenen release sunucusu değil ({{host}}) — indirilmedi (güvenlik)",
    "rust.ag.iptalEdildi": "indirme iptal edildi",
    "rust.ag.manifestAlinamadi": "manifest alınamadı",
    "rust.ag.olusturulamadi": "{{yol}} oluşturulamadı: {{hata}}",
    "rust.ag.politikaSiniri": "indirme politika sınırı: {{ayrinti}}",
    "rust.ag.sureSiniri": "indirme küresel süre sınırını aştı ({{sn}} sn) — iptal edildi",
    "rust.ag.tasinamadi": "{{yol}} taşınamadı: {{hata}}",
    "rust.ag.urlCozumlenemedi": "URL çözümlenemedi: {{url}}",
    "rust.ag.urlHttpsDegil": "URL HTTPS değil — indirilmedi (güvenlik): {{url}}",
    "rust.ag.yanitYok": "{{etiket}}: {{sn}} sn içinde yanıt gelmedi — çevrimdışı sayıldı",
    "rust.ag.yazilamadi": "diske yazılamadı: {{hata}}",
    "rust.ag.yazilamadiFlush": "diske yazılamadı (flush): {{hata}}",
    "rust.ag.yerelDosya": "yerel dosya hatası: {{hata}}",
    "rust.ag.yolNoktaSegmenti": "github.com{{yol}} — yol nokta-segmenti/kodlanmış ayraç içeriyor (pin atlatma)",
    "rust.backend.baslatilamadi": "backend başlatılamadı: {{hata}}",
    "rust.backend.bulunamadi": "backend çalıştırılabiliri bulunamadı: {{yol}}",
    "rust.backend.gunlukBayat": "⚠️ Aşağıdaki satırlar {{dk}} dk ÖNCESİNE ait — bu çalışmaya ait OLMAYABİLİR (backend              günlüğe hiç yazamadan çökmüş olabilir). Günlük: {{yol}}",
    "rust.backend.gunlukIpucu": "Ayrıntı için backend günlüğü: {{yol}}",
    "rust.backend.hazirOlmadi": "backend {{timeout_s}} sn içinde hazır olmadı (port {{port}}). Son çıktı:\n{{tail}}",
    "rust.backend.oturumDevredilemedi": "backend'e oturum devredilemedi (bağlantı yok)",
    "rust.backend.oturumKabulEdilmedi": "backend oturumu kabul etmedi (HTTP {{s}})",
    "rust.backend.oturumSerilestirilemedi": "oturum serileştirilemedi",
    "rust.backend.oturumYalnizYerel": "Oturum yalnız yerel backend'e (127.0.0.1) devredilebilir",
    "rust.backend.portYok": "boş port bulunamadı ({{start}}..{{end}})",
    "rust.backend.sonlandi": "backend başlarken sonlandı (çıkış kodu {{code}}). Son çıktı:\n{{tail}}",
    "rust.dogrulama.dosyaOkunamadi": "dosya okunamadı: {{hata}}",
    "rust.dogrulama.sha256Uyusmadi": "SHA256 UYUŞMADI — dosya bozuk ya da değiştirilmiş. beklenen={{beklenen}} gerçek={{gercek}}",
    "rust.giris.adresDogrulanamadi": "Giriş sunucusu adresi doğrulanamadı — işlem iptal edildi (güvenlik)",
    "rust.giris.cevrimdisi": "İnternet bağlantısı yok — çevrimdışı devam edebilirsiniz",
    "rust.giris.cokDeneme": "Çok fazla deneme yapıldı — birkaç dakika sonra tekrar deneyin",
    "rust.giris.epostaDogrulanmamis": "E-posta adresiniz doğrulanmamış — gelen kutunuzu kontrol edin",
    "rust.giris.girdiBos": "E-posta ve parola boş bırakılamaz",
    "rust.giris.kimlikHatali": "E-posta veya parola hatalı",
    "rust.giris.oturumGecersiz": "Kayıtlı oturum geçersiz — lütfen tekrar giriş yapın",
    "rust.giris.sunucuHatasi": "Giriş sunucusu hata verdi (HTTP {{kod}})",
    "rust.giris.yanitOkunamadi": "Giriş yanıtı okunamadı",
    "rust.kurulum.appGeriAlinamadi": "app guncellemesi GERI ALINAMADI ({{geri}}) — cihaz DOGRULANMAMIS/yarim app agaciyla kalmis olabilir; 'Onar' calistirin. (geri almayi tetikleyen adim: {{adim}})",
    "rust.kurulum.appYedegiYok": "app yedeği bulunamadı — geri alma YAPILAMADI (cihaz doğrulanmamış sürümde)",
    # D6.67: ekranda süreç adı "başlatıcı" (METIN-KILAVUZU §1)
    "rust.kurulum.baskaPencere": "Başka bir PEMF Vet başlatıcı penceresi kurulum/güncelleme yapıyor. Onun bitmesini bekleyin ya da diğer pencereyi kapatın. ({{hata}})",
    "rust.kurulum.enAzBirProfil": "En az bir profil kurulu kalmalı — önce başka bir profil kurun, sonra bunu kaldırın.",
    "rust.kurulum.eskiAppYedekleniyor": "eski uygulama sürümü yedekleniyor",
    "rust.kurulum.eskiKurulumAlgilandi": "eski kurulum algılandı ({{adet}} profil)",
    "rust.kurulum.eskiPaketlerTemizlendi": "eski paketler temizlendi ({{boyut}})",
    "rust.kurulum.eskiSurumTemizleniyor": "eski sürüm temizleniyor",
    "rust.kurulum.guncellemeGeriAlinamadi": "guncelleme GERI ALINAMADI ({{geri}}) — cihaz DOGRULANMAMIS yeni surumde olabilir; 'Onar' calistirin. (geri almayi tetikleyen adim: {{adim}})",
    "rust.kurulum.kalanOnbellekYok": "Kalan profil '{{profil}}' için önbellekte {{dosya}} yok — ortak dosyalar güvenle hesaplanamaz. 'Kurulumu onar' sonrası tekrar deneyin.",
    "rust.kurulum.katmanEksikDonuldu": "yeni uygulama katmanı eksik — eski sürüme dönüldü",
    "rust.kurulum.katmanEksikGeriAlinamadi": "yeni uygulama katmanı eksik ve GERİ ALINAMADI (yedek yok) — cihaz doğrulanmamış sürümde; 'Onar' ile yeniden kurun",
    "rust.kurulum.kayitOkunamadi": "Kurulu profil kaydı okunamadı ama diskte model verisi VAR — hangi profillerin onarılacağı bilinmiyor. Profilleri yeniden seçip kurun (indirilenler önbellekten gelir, yeniden İNMEZ).",
    "rust.kurulum.onbellekBozuk": "{{profil}} için önbellekteki {{dosya}} bozuk ({{hata}}) — 'Kurulumu onar' sonrası tekrar deneyin",
    "rust.kurulum.onbellekOkunamadi": "{{profil}} için önbellekteki {{dosya}} okunamadı ({{hata}}) — 'Kurulumu onar' sonrası tekrar deneyin",
    "rust.kurulum.onbellekYok": "{{profil}} için önbellekte {{dosya}} yok — 'Kurulumu onar' sonrası tekrar deneyin",
    "rust.kurulum.paketGuvensiz": "{{profil}} paketinde güvensiz girdi ({{sebep}}) — hiçbir dosya silinmedi. Bu profil buradan kaldırılamıyor: paket bozuk görünüyorsa 'Kurulumu onar' deneyin; sorun sürerse uygulamayı kaldırıp yalnız istediğiniz profillerle yeniden kurun.",
    "rust.kurulum.profilKurulDegil": "'{{profil}}' kurulu görünmüyor — profil listesini yenileyip tekrar deneyin.",
    "rust.kurulum.profilManifestteYok": "'{{ad}}' profili manifestte yok — ortak dosyalar hesaplanamaz. Manifesti yenileyip tekrar deneyin.",
    "rust.kurulum.profilSecilmedi": "Kaldırılacak profil seçilmedi.",
    "rust.kurulum.silinemedi": "{{yol}} silinemedi ({{hata}}) — uygulama ya da antivirüs dosyayı kilitlemiş olabilir; açık uygulamaları kapatıp 'Kurulumu onar' ile tekrar deneyin. Profil kaydı değişmedi.",
    "rust.kurulum.silmeKokDisi": "GÜVENLİK: {{yol}} kurulum kökünün dışına çözümlendi — silme durduruldu.",
    "rust.kurulum.yeniKurulumEksik": "yeni kurulum eksik (exe/web bulunamadı) — takas yapılmadı",
    "rust.kurulum.yetersizDisk": "Yetersiz disk alanı: {{gerek}} gerekiyor, bu diskte {{bos}} boş. Yer açıp tekrar deneyin.",
    "rust.kurulum.yolAiModelsDisi": "ai_models/ disinda girdi: {{ad}}",
    "rust.kurulum.yolGuvensizKarakter": "guvensiz yol karakteri: {{ad}}",
    "rust.kurulum.yolMutlak": "mutlak ya da bos parcali yol: {{ad}}",
    "rust.kurulum.yolSonuNokta": "sonu nokta/bosluk ile biten parca: {{ad}}",
    "rust.kurulum.yolUstDizin": "ust dizine kacis: {{ad}}",
    "rust.manifest.alanYok": "manifest'te '{{alan}}' alanı yok",
    "rust.manifest.ayristirilamadi": "manifest JSON olarak ayrıştırılamadı: {{hata}}",
    "rust.manifest.platformPaketiYok": "Bu platform ({{platform}}) için manifest'te paket YOK. Mevcut anahtarlar: [{{available}}]. Yanlış platformun paketi KURULMAZ — yayın sürecinde bu platformun base paketi eksik.",
    "rust.manifest.profilYok": "'{{profile}}' profili manifest'te yok. Mevcut profiller: [{{available}}]",
    "rust.manifest.sha256Gecersiz": "'{{key}}' kaydının sha256 değeri geçersiz (64 hex bekleniyor, gelen: {{got}})",
    "rust.yedek.ayniSurucu": "Yedek hedefi hasta verisiyle AYNI sürücüde. Disk arızasında ikisi de kaybolur — harici bir disk ya da ağ paylaşımı seçin.",
    "rust.yedek.yazilamiyor": "Bu klasöre yazılamıyor. Sürücü takılı ve yazılabilir olmalı.",
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


def _kaynak() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(CEKIRDEK.glob("*.rs")))


@pytest.mark.parametrize("anahtar", sorted(ESKI_TR))
def test_KRITIK_TR_deger_eski_literalle_bayt_bayt_ayni_EN_dolu_Turkce_harfsiz_ayni_yer_tutucular(anahtar):
    tr, en = _tr(), _en()
    assert tr[anahtar] == ESKI_TR[anahtar], f"TR değer eski literalden FARKLI: {anahtar}"
    assert en.get(anahtar), f"EN boş: {anahtar}"
    assert not TR_HARF.search(en[anahtar]), f"EN'de Türkçe harf: {anahtar}: {en[anahtar]!r}"
    yer = lambda s: sorted(re.findall(r"\{\{(\w+)\}\}", s))  # noqa: E731
    assert yer(tr[anahtar]) == yer(en[anahtar]), f"yer tutucu kümesi ayrışmış: {anahtar}"


def test_KRITIK_her_anahtar_cekirdekte_KULLANILIYOR_ve_eski_Turkce_literal_kalmadi():
    kaynak = _kaynak()
    kullanilmayan = [k for k in ESKI_TR if f'"{k}"' not in kaynak]
    assert not kullanilmayan, f"katalogda var ama çekirdekte çağrılmıyor: {kullanilmayan}"
    # yorum SATIRLARI atılır (eski metin yorumda anılabilir; kod ölçülür)
    kod = "\n".join(s for s in kaynak.splitlines() if not s.lstrip().startswith("//"))
    kalan = [(k, m) for k, m in ESKI_TR.items() if "{{" not in m and f'"{m}"' in kod]
    assert not kalan, f"ESKİ Türkçe literal çekirdekte hâlâ duruyor: {kalan}"


def test_thiserror_hata_nesneleri_Display_katalogdan_ve_anahtar_ilk_satirda():
    """`#[error("{}", crate::dil::t_ile("anahtar", …))]` — anahtar çağrının İLK satırında (K-3 statik denetimi bölünmüş çağrıyı dinamik sayar)."""
    kaynak = _kaynak()
    cagrilar = re.findall(r'#\[error\("\{\}", crate::dil::t(?:_ile)?\("(rust\.[\w.]+)"', kaynak)
    assert len(cagrilar) >= 38, f"thiserror iletileri katalogdan değil: {len(cagrilar)}"
    assert set(cagrilar) <= set(ESKI_TR), sorted(set(cagrilar) - set(ESKI_TR))
    # Türkçe harf taşıyan çıplak `#[error("…")]` kalmamalı (dil-bağımsız teknik iletiler — ör. "HTTP {status} — {url}" — muaf)
    assert not re.findall(r'#\[error\("[^"]*[çğıöşüÇĞİÖŞÜ][^"]*"\)\]', kaynak), "çıplak Türkçe #[error(...)] kalmış"


def test_arayuz_metne_gore_dallanmalari_IKI_dilde_eslesir():
    """Rust iletisi dile göre değişir → arayüzün metne göre dallandığı üç yer (DNS · yanlış parola · çevrimdışı) EN iletiyle de eşleşmeli."""
    ham = HTML.read_text(encoding="utf-8")
    m = re.search(r"if \((/[^\n]+/i)\.test\(m\)\) return x\.errDns;", ham)
    assert m, "hataCumlesi DNS koşulu bulunamadı"
    dns = re.compile(m.group(1)[1:-2].replace("\\(", r"\(").replace("\\)", r"\)"), re.I)
    for dil, ileti in (("tr", _tr()["rust.ag.dns"]), ("en", _en()["rust.ag.dns"])):
        assert dns.search(ileti.replace("{{hata}}", "x")), f"{dil}: DNS iletisi arayüz koşuluna uymuyor: {ileti}"
    assert 'm.includes("parola hatalı")' in ham and "incorrect email or password" in ham
    assert (
        "parola hatalı" in _tr()["rust.giris.kimlikHatali"]
        or "parola hatalı" in _tr()["rust.giris.kimlikHatali"].lower()
    )
    assert re.search(r"incorrect email or password", _en()["rust.giris.kimlikHatali"], re.I)
    assert 'm.includes("İnternet bağlantısı yok")' in ham and "no internet connection" in ham
    assert "İnternet bağlantısı yok" in _tr()["rust.giris.cevrimdisi"]
    assert re.search(r"no internet connection", _en()["rust.giris.cevrimdisi"], re.I)
    # diskte yer yok: arayüz `disk` sözcüğüne bakar — iki dilde de var
    assert "disk" in _tr()["rust.kurulum.yetersizDisk"].lower() and "disk" in _en()["rust.kurulum.yetersizDisk"].lower()
