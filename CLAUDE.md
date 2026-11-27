# CLAUDE.md — bu depoda çalışan her oturum ÖNCE bunu okur

## Çok dillilik (TR + EN) — kalıcı kural (sahip / hoca: "bir şey eklerken hep oraya iki dilde ekler")

1. **Kullanıcıya görünen her metin katalogdan gelir** — kodda sabit Türkçe / İngilizce ekran metni YAZILMAZ.
   Arayüz / site `t("adAlani.anahtar")`, sunucu `ceviri.t("…")`, launcher Rust `dil::t("…")`, NSIS `$(PEMF_…)`, DEMA `t("…")`.
2. **Yeni anahtar `tr` + `en` BİRLİKTE** eklenir (tek dilde anahtar K-1 kapısında kırmızı): `scripts/i18n/katalog.py anahtar-ekle`.
3. **Var olan Türkçe metin BAYT BAYT aynı kalır**; TR değeri elle yazılmaz, kaynaktan kopyalanır (`scripts/i18n/uygula.py`).
4. **Terim sözlüğü** `i18n/terimler.json` (Seans → Session, Jeton → Credit, ACİL DURDUR → EMERGENCY STOP …) — K-4.
5. **Güvenlik metinleri** `i18n/kritik-anahtarlar.json`; ACİL DURDUR çeviri sisteminden bağımsız (`apps/ui/src/i18n/kritik.ts`) — K-5.
6. **İngilizce bayrağı kapalı** (`i18n/bayrak.json`); yalnız inceleme oturumu açar (`scripts/i18n/bayrak.py --ac`).
7. **Günlük (log) iletileri Türkçe kalır**; DB değerleri, API alan adları, testID'ler çevrilmez.
8. **Kapılar** `tests/test_i18n_*.py` (K-1 … K-7) + jest `apps/ui/src/i18n/__tests__` + site vitest `apps/web/src/i18n/__tests__`.
   Kaynak metnini tarayan bir testi kırarsan GEVŞETME — `tests/i18n_yardimci.py` / `kaynakMetni.ts` ile çevir (iki mutant).
9. **Göç durumu** `i18n/kapsam.json` (`scripts/i18n/kapsam.py durum`); kapsam defterinde `tamam` dosyada sabit metin bırakma (K-2).

Ayrıntı, örnek dönüşümler ve sık hatalar: **`i18n/KURALLAR.md`**.

## Test kapsamı — kalıcı kural (sahip Y311 / Y325: "yeni kodlar eklenince ya da mevcut kodlar değişince … kalıcı kural olarak koymalıyız")

1. **Fark kapsamı %100:** eklediğin / değiştirdiğin her ölçülen satır ve dal AYNI commit'teki testlerle koşar (Python, `ai_hub`, arayüz,
   site, başlatıcı, kart yazılımı). CI'da `scripts/fark_kapsami.py` dal ↔ `duzeltme/dalga-2` (yoksa `production-hardening`) farkını ölçer.
2. **Yeni dosya baştan %100** — "sonra test yazarız" yok.
3. **İstisna yalnız bilinçli açık kalan türleri:** gerçek sistem kolu (yasak port, gerçek HKCU / kasa / güvenlik duvarı, Win32 hata kolu),
   yalnız yarış / platform kolu, kanıtlanmış ulaşılamaz kol — kodda gerekçeli etiketle (`# pragma: no cover — <neden>`,
   `/* istanbul ignore next — <neden> */`, `// LCOV_EXCL_LINE — <neden>`). "Test yazmak zor" istisna DEĞİL.
4. **Paket toplamı tabanın altına inemez:** taban `tests/kapsam_tabani.json` (insan okur tablo: `DENETIM\KAPSAM-TABANI.md`); CI
   eşikleri oradan okunur (pytest `fail_under` + `scripts/kapsam_tabani_kapisi.py`, jest / vitest yapılandırması, cargo
   `--fail-under-lines`). Taban YALNIZ yukarı gider; düşüş test eklenerek kapatılır, eşik DÜŞÜRÜLMEZ.
5. **Ölçü için test silinmez, etiket yayılmaz;** ölü kod silinirse testleri de temizlenir.
6. **Atlama da sessiz değil:** CI'da atlanan her test `tests/ci_atlanan_defteri.json`'da gerekçeli (yalnız Y = yalnız yayın makinesi
   eseri, P = platform / ortam). Eksik model / test girdisi CI model paketine girer (`scripts/ci_modelleri.py`), deftere GİRMEZ.

Kapılar: `tests/test_CT1f_*.py` · `tests/test_CT1c_ci_atlanan_defteri_KAPI.py`. `ci push`tan önce yerel CI eşi: `DENETIM\araclar\ci-esi\`.
