// Author: mertaygn, cglrgrkn
/* istanbul ignore file -- PLATFORM: `import()` jest'te KOŞMAZ (dinamik içe aktarma dönüştürücüsü yok; yeni bağımlılık YOK — `tembelEkranlar.ts` ile aynı gerekçe); `kayit.ts` testleri yükleyiciyi sahteler */
/**
 * GA (istem 53) B3 — modül paneli YÜKLEYİCİLERİ: kimlik → dinamik içe aktarma (panel yalnız modül SEÇİLİNCE indirilir / yüklenir).
 * Yeni modül birleştirilirken buraya tek satır eklenir; kimlik sunucudaki `moduller/<kimlik>/modul.json` ile AYNI.
 */
export const PANEL_YUKLEYICILERI = {
  ornek: () => import("./ornek/Panel"),
};
