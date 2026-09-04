// Author: mertaygn, cglrgrkn
/**
 * SİSTEM YAZI ÖLÇEĞİ TAVANI — injectFont sözleşmesi
 * [S6, 2026-09-04 responsive denetimi · sahip kararı: 1,2]
 * ========================================================
 * ÖLÇÜLEN DURUM: `grep allowFontScaling|maxFontSizeMultiplier pf/src` = 0. RN varsayılanı sistem
 * ölçeğini SINIRSIZ uygular; Android "Yazı boyutu" 1,3'te alt bar etiketleri ('Akıllı Teşhis'),
 * seans süresi (1:05:30), bildirim rozeti ve seans detay tablosu taşıyordu.
 *
 * SÖZLEŞME:
 *  1. Her Text/TextInput varsayılan olarak `maxFontSizeMultiplier = MAX_FONT_SCALE` alır.
 *  2. Yerel bir tavan verilmişse DOKUNULMAZ (bileşen kendi sıkı tavanını koyabilir).
 *  3. `allowFontScaling={false}` verilmişse dokunulmaz — ama uygulamada KULLANILMAZ (erişilebilirlik).
 *  4. Tavan, `fontFamily` erken-dönüşünden ÖNCE uygulanır → ikon fontlu Text'ler de kapsanır.
 *
 * ⚠️ MUTASYON: tavan bloğu `if (flat.fontFamily) return out;` satırının ALTINA taşınırsa 4. vaka KIRILIR.
 */
import { Text, TextInput } from "react-native";
import { injectFont } from "@/theme/fonts";
import { MAX_FONT_SCALE } from "@/theme/tokens";

describe("injectFont — yazı ölçeği tavanı", () => {
  it("KRİTİK: sade Text varsayılan tavanı alır", () => {
    const out = injectFont(Text, { children: "x" });
    expect(out.maxFontSizeMultiplier).toBe(MAX_FONT_SCALE);
  });

  it("TextInput da kapsanır (placeholder ile yakalananlar dahil)", () => {
    expect(injectFont(TextInput, { value: "" }).maxFontSizeMultiplier).toBe(MAX_FONT_SCALE);
    expect(injectFont({}, { placeholder: "ör." }).maxFontSizeMultiplier).toBe(MAX_FONT_SCALE);
  });

  it("yerel tavan EZİLMEZ (bileşen daha sıkı tavan koyabilir)", () => {
    const out = injectFont(Text, { children: "x", maxFontSizeMultiplier: 1 });
    expect(out.maxFontSizeMultiplier).toBe(1);
  });

  it("allowFontScaling={false} verilmişse dokunulmaz", () => {
    const out = injectFont(Text, { children: "x", allowFontScaling: false });
    expect(out.maxFontSizeMultiplier).toBeUndefined();
  });

  it("KRİTİK: ikon fontlu Text de tavanlanır (fontFamily erken-dönüşü tavanı atlamamalı)", () => {
    const out = injectFont(Text, { children: "", style: { fontFamily: "Ionicons" } });
    expect(out.maxFontSizeMultiplier).toBe(MAX_FONT_SCALE);
    expect(out.style.fontFamily).toBe("Ionicons"); // özel fonta dokunulmadı
  });

  it("Text/TextInput olmayan bileşene dokunulmaz", () => {
    const props = { children: "x" };
    expect(injectFont({}, props)).toBe(props);
  });

  it("ağırlık→Inter eşlemesi korunur (mevcut sözleşme bozulmadı)", () => {
    const out = injectFont(Text, { children: "x", style: { fontWeight: "800" } });
    expect(out.style.fontFamily).toBe("Inter_800ExtraBold");
    expect(out.style.fontWeight).toBeUndefined();
    expect(out.maxFontSizeMultiplier).toBe(MAX_FONT_SCALE);
  });
});
