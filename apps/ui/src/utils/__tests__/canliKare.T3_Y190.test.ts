// Author: mertaygn, cglrgrkn
/**
 * T3 · Y190e — petri / fantom canlı karesinde "tespit yok" (200 + `status: no_detection`) SONUÇSUZ sayılır: durum satırı "tespit
 * yok" der (ret / hata gibi kırmızı değil) ve dakika sayacına girmez — backend `jeton.sonucsuz_mu` kuralının aynası.
 * Ölçülen (3a4c2f5b): `canliKareDurumu` yalnız `status === "success"`ı sonuç sayıyor, `no_detection` → "analiz edilemedi:
 * sunucu yanıtı 200" (yanlış: istek başarılı, yalnız hedef yok).
 */
import { canliKareDurumu, canliOturumBaslat } from "@/utils/canliKare";

it("KRİTİK: petri / fantom 'no_detection' → 'bulunamadi' (tespit yok) ve dakika SAYILMAZ", () => {
  for (const uc of ["/vision/em_petri", "/vision/em_fantom"]) {
    const d = canliKareDurumu(uc, true, 200, { status: "no_detection", success: false, error: "plate_not_found" });
    expect(d.tur).toBe("bulunamadi");
    expect(d.metin).toContain("tespit yok");
    const o = canliOturumBaslat();
    o.kareBildir(d, 0);
    expect(o.jetonSayisi()).toBe(0);
  }
});

it("KARŞIT: başarılı petri / fantom karesi 'sonuc' (dakika sayılır); 422 ret 'red'", () => {
  expect(canliKareDurumu("/vision/em_petri", true, 200, { status: "success", success: true, n_wells: 3 }).tur).toBe("sonuc");
  expect(canliKareDurumu("/vision/em_fantom", false, 422, { detail: "Plaka bulunamadı" }).tur).toBe("red");
});
