// Author: mertaygn, cglrgrkn
import { StyleSheet, Text, TextInput } from "react-native";
import { MAX_FONT_SCALE } from "@/theme/tokens";
import {
  useFonts,
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
  Inter_800ExtraBold,
  Inter_900Black,
} from "@expo-google-fonts/inter";

/** useFonts'a verilecek Inter kesimleri (premium, profesyonel — sistem/telefon fontundan bağımsız). */
export const INTER_FONTS = {
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
  Inter_800ExtraBold,
  Inter_900Black,
};

export { useFonts };

// RN'de ağırlık font DOSYASIYLA gelir (tek aile + fontWeight yetmez) → fontWeight'i doğru Inter kesimine eşle.
const FAMILY_BY_WEIGHT: Record<string, string> = {
  "100": "Inter_400Regular",
  "200": "Inter_400Regular",
  "300": "Inter_400Regular",
  "400": "Inter_400Regular",
  normal: "Inter_400Regular",
  "500": "Inter_500Medium",
  "600": "Inter_600SemiBold",
  "700": "Inter_700Bold",
  bold: "Inter_700Bold",
  "800": "Inter_800ExtraBold",
  "900": "Inter_900Black",
};

/**
 * Text/TextInput elemanına ağırlık-duyarlı Inter fontFamily'sini enjekte eder (zaten font varsa dokunmaz).
 * KRİTİK: ağırlık font DOSYASIYLA geldiğinden fontWeight'i SİLERİZ — aksi halde Android'de
 * "Inter_800ExtraBold" + fontWeight:800 çakışıp sistem fontuna DÜŞER (yalnız 400/varsayılan çalışırdı).
 */
export function injectFont(type: any, props: any): any {
  if (!props) return props;
  // TextInput'u referansla VE 'placeholder' prop'uyla yakala (sarmalanmış olsa bile).
  const isInput = type === TextInput || "placeholder" in props;
  if (type !== Text && !isInput) return props;

  // ── SİSTEM YAZI ÖLÇEĞİ TAVANI  [S6, 2026-09-04 · sahip kararı: 1,2] ──────────────────────
  // ÖLÇÜLEN DURUM: uygulamada hiçbir Text/TextInput'ta maxFontSizeMultiplier YOKTU (grep 0).
  // Android "Yazı boyutu" 1,3'te alt bar etiketleri, seans süresi ve tablo hücreleri taşıyordu.
  // ⚠️ `allowFontScaling={false}` KULLANILMAZ: görme zorluğu olan operatörün tercihi tamamen
  // kapatılmaz, yalnız TAVANLANIR. Yerel bir tavan verilmişse ona dokunulmaz (?? semantiği).
  // ⚠️ Bu blok `flat.fontFamily` erken-dönüşünden ÖNCE olmalı — ikon fontlu Text'ler de kapsansın.
  let out: any = props;
  if (props.allowFontScaling !== false && props.maxFontSizeMultiplier == null) {
    out = { ...props, maxFontSizeMultiplier: MAX_FONT_SCALE };
  }

  const flat: any = { ...(StyleSheet.flatten(out.style) || {}) };
  if (flat.fontFamily) return out; // zaten özel font (ör. ikon) — yalnız tavan uygulandı
  const w = String(flat.fontWeight ?? "400");
  flat.fontFamily = FAMILY_BY_WEIGHT[w] || FAMILY_BY_WEIGHT["400"];
  delete flat.fontWeight; // ağırlık artık aile dosyasında
  if (flat.fontStyle === "italic") delete flat.fontStyle; // italik Inter yüklü değil → el-yazısı fallback'i önle
  return { ...out, style: flat };
}

let _applied = false;

/**
 * Tüm Text/TextInput'a global Inter uygular. RN 0.85'te Text bir FUNCTION component (forwardRef `.render` yok),
 * bu yüzden otomatik JSX runtime'ı (`react/jsx-runtime` jsx/jsxs) sararız — her JSX çağrısını yakalar.
 * Ayrıca forwardRef bileşenleri için `.render` patch'i de dener (varsa). DEFANSİF: hata → sistem fontuna düşer.
 */
export function applyGlobalInter(): void {
  if (_applied) return;
  _applied = true;

  // 1) Asıl mekanizma: otomatik JSX runtime'ı sar (function-component Text için).
  const wrap = (mod: any) => {
    if (!mod || mod.__interPatched) return;
    try {
      const oj = mod.jsx;
      const ojs = mod.jsxs;
      if (typeof oj === "function") mod.jsx = (t: any, p: any, k?: any) => oj(t, injectFont(t, p), k);
      if (typeof ojs === "function") mod.jsxs = (t: any, p: any, k?: any) => ojs(t, injectFont(t, p), k);
      mod.__interPatched = true;
    } catch {
      /* yok say */
    }
  };
  try { wrap(require("react/jsx-runtime")); } catch { /* yok */ }
  try { wrap(require("react/jsx-dev-runtime")); } catch { /* yok */ }

  // 2) Yedek: forwardRef bileşenleri için render-patch (bu RN'de Text function olabilir → guard atlar).
  const patchRender = (Comp: any) => {
    const old = Comp && Comp.render;
    if (typeof old !== "function") return;
    Comp.render = function (...args: any[]) {
      const el = old.apply(this, args);
      if (!el || !el.props) return el;
      try {
        return { ...el, props: injectFont(el.type, el.props) };
      } catch {
        return el;
      }
    };
  };
  patchRender(Text);
  patchRender(TextInput);
}
