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
