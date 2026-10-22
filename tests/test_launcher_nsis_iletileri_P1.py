# -*- coding: utf-8 -*-
"""I18N-P1 · 11d (KRİTİK) — kurulum / kaldırma sihirbazı (`launcher/app/windows/hooks.nsi`): iletiler `launcher/i18n → nsis.*` kataloğundan, `LangString PEMF_<ad>` olarak
ÜRETİLİR (`scripts/i18n/launcher_uret.py`); kodda yalnız `$(PEMF_<ad>)` başvurusu var.

KRİTİK: kaldırma sırasında bobin E-stop teyidi (DOĞRULANDI / DOĞRULANAMADI — bobinleri ELLE kontrol edin) ve hasta kayıtlarının KORUNDUĞU (SİLİNMEDİ) bildirimi.
Bu kapı: TR metin ESKİSİYLE bayt bayt aynı (altın tablo) · EN dolu / Türkçe harfsiz / aynı NSIS değişkenleri ($0 $1 $2 $INSTDIR $\r$\n …) · her anahtar hooks.nsi'de
GERÇEKTEN başvuruluyor · MessageBox yalnız sessiz olmayan + yükseltme olmayan kaldırmada (self-update `/S` kilitlenmesin) · kritik anahtarlar listede.
MUTASYON: katalog TR değeri değişirse / hooks.nsi'den başvuru kalkarsa / EN'de değişken düşerse / MessageBox koruması kalkarsa → KIRMIZI.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
HOOKS = KOK / "launcher" / "app" / "windows" / "hooks.nsi"
TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
KRITIK = (
    "estopGonderiliyor",
    "estopDogrulandi",
    "estopDogrulanamadi",
    "estopDogrulanamadiKutu",
    "portGecersiz",
    "surecDurduruluyor",
    "kayitlarKorundu",
    "kaldirildiKutu",
)

#: Altın TR değerler (taşıma ÖNCESİ / I18N-0 hooks.nsi metinleri; NSIS kaçışları `$\r$\n` değerin İÇİNDE).
GOLDEN_TR = {
    # LN L7 · D2.67 / D2.77 (DALGA-2): konum / iz yolu sabit `%APPDATA%\\PEMF_GUI` (all bağlamında `$APPDATA` → C:\\ProgramData) yerine
    # PREUNINSTALL'da çözülen GERÇEK kök `$PEMF_VeriKoku` (launcher'ın backend'e verdiği kök; yoksa ProgramData / APPDATA)
    "estopDogrulanamadi": "PEMF: bobin E-stop DOĞRULANAMADI (nsExec=$0 $1) — bobinleri ELLE kontrol edin; iz: $PEMF_VeriKoku\\logs\\uninstall_estop.log",
    "estopDogrulanamadiKutu": "PEMF: bobin acil-durdurma DOĞRULANAMADI ($0).$\\r$\\n$\\r$\\nBobinleri ELLE kontrol edin (cihaz üzerindeki göstergeler / fiziksel kapatma).$\\r$\\n$\\r$\\nAyrıntı: $1$\\r$\\nKayıt: $PEMF_VeriKoku\\logs\\uninstall_estop.log",
    "estopDogrulandi": "PEMF: bobin E-stop DOĞRULANDI — $1",
    "estopGonderiliyor": "PEMF: aktif seans güvenliği — bobinlere E-stop gönderiliyor (port $2)…",
    "kaldirildiKutu": "PEMF Vet kaldırıldı.$\\r$\\n$\\r$\\nHASTA KAYITLARI, SEANS GEÇMİŞİ ve AI ANALİZ GEÇMİŞİ SİLİNMEDİ.$\\r$\\nTıbbi kayıt oldukları için kaldırma sırasında korunurlar.$\\r$\\n$\\r$\\nKonum:$\\r$\\n$PEMF_VeriKoku$\\r$\\n$\\r$\\nKalıcı silmek isterseniz bu klasörü elle silin ya da yeniden kurup uygulama içinden silin (Hastalar → 'Tümünü Sil', AI Geçmişi → 'Geçmişi Sil').",
    "kayitlarKorundu": "PEMF: Hasta kayıtları, seans geçmişi ve AI analiz geçmişi KORUNDU (tıbbi kayıt) — $PEMF_VeriKoku",
    # 18K K1 (İG-8.27 NSIS ikizi): port dosyası geçersizken STOP artık ATLANMAZ — varsayılan port denenir; ileti gerçeği söyler.
    "portGecersiz": "PEMF: backend.port geçersiz ('$1') — varsayılan port deneniyor.",
    "portVeriKokunden": "PEMF: backend.port $INSTDIR'de yok — veri kökünden okundu.",
    "surecDurduruluyor": "PEMF: artık backend süreçleri durduruluyor…",
    "temizlikTamam": "PEMF Vet Client temizliği tamamlandı.",
    # Y164 (S-I18N.8, sahip 2026-10-20; YH A3): ileti kutunun KENDİ yazısını aynen anar ("'uygulama verisini sil'" → "'Uygulama verilerini sil'")
    "veriSilIsaretli": "PEMF: 'Uygulama verilerini sil' işaretli — indirilen çalışma-zamanı ve modeller kaldırılıyor…",
    "veriSilIsaretsiz": "PEMF: 'Uygulama verilerini sil' işaretsiz — indirilen profiller/modeller KORUNUYOR (yeniden kurulumda tekrar inmez). Tamamen silmek için kaldırırken kutuyu işaretleyin.",
    "yukseltmeKorunuyor": "PEMF: yükseltme — indirilen modeller ve önbellek korunuyor (tekrar inmez).",
}


def _nsis(dil: str) -> dict:
    return json.loads((KOK / "launcher" / "i18n" / f"{dil}.json").read_text(encoding="utf-8"))["nsis"]


def _kod() -> str:
    """hooks.nsi — üretilmiş LangString bloğu ve yorum satırları HARİÇ (başvurular kodda aranır)."""
    s = HOOKS.read_text(encoding="utf-8")
    bas = s.index("; >>> I18N-DIL")
    son = s.index("; <<< I18N-DIL")
    s = s[:bas] + s[son:]
    return "\n".join(x for x in s.splitlines() if not x.lstrip().startswith(";"))


@pytest.mark.parametrize("anahtar", sorted(GOLDEN_TR))
def test_KRITIK_TR_deger_eskisiyle_bayt_bayt_ayni_EN_dolu_Turkce_harfsiz_ayni_NSIS_degiskenleri(anahtar):
    tr, en = _nsis("tr"), _nsis("en")
    assert tr[anahtar] == GOLDEN_TR[anahtar], f"TR değer eskisinden FARKLI: {anahtar}"
    assert en.get(anahtar), f"EN boş: {anahtar}"
    assert not TR_HARF.search(en[anahtar]), f"EN'de Türkçe harf: {anahtar}: {en[anahtar]!r}"
    degisken = lambda s: sorted(re.findall(r"\$(?:\\r|\\n|\w+)", s))  # noqa: E731
    assert degisken(tr[anahtar]) == degisken(en[anahtar]), f"NSIS değişken kümesi ayrışmış: {anahtar}"


def test_KRITIK_her_anahtar_hooks_nsi_de_BASVURULUYOR_DetailPrint_ya_da_MessageBox():
    kod = _kod()
    eksik = [k for k in GOLDEN_TR if f'"$(PEMF_{k})"' not in kod]
    assert not eksik, f"katalogda var ama hooks.nsi'de başvurulmuyor: {eksik}"
    # düz Türkçe ileti kodda KALMAMIŞ (DetailPrint / MessageBox yalnız $(PEMF_…) alır)
    cikarma = re.findall(r'(?:DetailPrint|MessageBox[^"\n]*)\s+"([^"\n]*)"', kod)
    cikarma = [c for c in cikarma if not c.startswith("$(PEMF_")]
    assert not [c for c in cikarma if TR_HARF.search(c)], f"hooks.nsi'de düz Türkçe ileti: {cikarma}"


def test_KRITIK_MessageBox_yalniz_sessiz_olmayan_ve_yukseltme_olmayan_kaldirmada():
    """Self-update `/S` ile kurar, Tauri yükseltmesi eski kaldırıcıyı `/UPDATE` ile koşturur: orada MessageBox akışı KİLİTLER."""
    kod = _kod().splitlines()
    kutular = [i for i, x in enumerate(kod) if "MessageBox" in x and "$(PEMF_" in x]
    assert len(kutular) == 2, f"beklenen 2 MessageBox, bulunan {len(kutular)}"
    for i in kutular:
        onceki = "\n".join(kod[max(0, i - 4) : i])
        assert "${IfNot} ${Silent}" in onceki and "$UpdateMode <> 1" in onceki, (
            f"MessageBox sessiz / yükseltme korumasız: {kod[i]!r}"
        )


def test_KRITIK_guvenlik_ifadeleri_iki_dilde_korunuyor():
    tr, en = _nsis("tr"), _nsis("en")
    assert "ELLE kontrol" in tr["estopDogrulanamadiKutu"] and "MANUALLY" in en["estopDogrulanamadiKutu"]
    assert "ELLE kontrol" in tr["estopDogrulanamadi"] and "MANUALLY" in en["estopDogrulanamadi"].upper()
    assert "DOĞRULANAMADI" in tr["estopDogrulanamadi"] and "NOT be confirmed" in en["estopDogrulanamadi"]
    assert "DOĞRULANDI" in tr["estopDogrulandi"] and "CONFIRMED" in en["estopDogrulandi"]
    assert "varsayılan port deneniyor" in tr["portGecersiz"] and "trying the default port" in en["portGecersiz"]
    assert "atlandı" not in tr["portGecersiz"] and "skipped" not in en["portGecersiz"]  # 18K K1: STOP atlanmıyor
    assert "SİLİNMEDİ" in tr["kaldirildiKutu"] and "NOT DELETED" in en["kaldirildiKutu"]
    assert "KORUNDU" in tr["kayitlarKorundu"] and "KEPT" in en["kayitlarKorundu"]


#: Tauri NSIS dil dosyalarındaki kaldırma kutusunun yazısı (`LangString deleteAppData`: Turkish.nsh / English.nsh — tauri-bundler; EN derlemede
#: ölçüldü `launcher/target/release/nsis/x64/English.nsh:27`, TR I18N-0'da ölçüldü — S-I18N.8).
KUTU = {"tr": "Uygulama verilerini sil", "en": "Delete the application data"}


@pytest.mark.parametrize("dil", ["tr", "en"])
@pytest.mark.parametrize("anahtar", ["veriSilIsaretli", "veriSilIsaretsiz"])
def test_Y164_kaldirma_iletisi_KUTUNUN_KENDI_YAZISINI_aynen_anar(dil, anahtar):
    """Y164: kullanıcı ilettiği kutuyu ekranda gördüğü yazıyla tanısın — "'uygulama verisini sil'" kutuda yazmıyordu."""
    deger = _nsis(dil)[anahtar]
    assert f"'{KUTU[dil]}'" in deger, (dil, anahtar, deger)


def test_KRITIK_sekiz_kritik_anahtar_kritik_listesinde_launcher_yuzeyinde():
    liste = json.loads((KOK / "i18n" / "kritik-anahtarlar.json").read_text(encoding="utf-8"))
    kayitli = {k["anahtar"] for k in liste["anahtarlar"] if k["yuzey"] == "launcher"}
    assert kayitli >= {f"nsis.{k}" for k in KRITIK}, sorted({f"nsis.{k}" for k in KRITIK} - kayitli)
    tr = _nsis("tr")
    assert all(k in tr for k in KRITIK)
