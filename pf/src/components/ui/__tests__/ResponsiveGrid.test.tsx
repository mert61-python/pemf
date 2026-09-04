// Author: mertaygn, cglrgrkn
/**
 * ResponsiveGrid — sütun sayısı GERÇEK kaptan  [S2 adım 3, 2026-09-04 responsive denetimi]
 * ========================================================================================
 * ÖLÇÜLEN DURUM: sütun sayısı `width / columns < minItemWidth` ile PENCERE genişliğinden
 * hesaplanıyordu. Tablet/masaüstü kabuğunda kenar çubuğu (240 px) + içerik boşluğu (2×24) düşülünce
 * kartlar 768 px'lik pencerede 352 px'lik alana 2 sütun diye yerleşiyor, bobin kartı 182 px'e
 * düşüyordu (ekranB-1). Ölçüm de yoktu: kap daralsa bile ızgara haberdar olmuyordu.
 *
 * YENİ KURAL: sütun = clamp(floor(gridW / (rs(minItemWidth) + 2×sm)), 1, üstSınır)
 *   · gridW: onLayout ÖLÇÜMÜ; ölçüm gelene kadar contentWidth + 2×sm TAHMİNİ (flicker yok).
 *   · üstSınır = max(columns, 2) — plandaki düz `columns` sınırı TELEFONDA REGRESYON yapıyordu:
 *     telefonda columns = 1 olduğu için 8 sensör kartı ve 5 sayısal AI girişi tek sütuna
 *     düşüyordu (bugün ikisi de 2'li). Genişlik hesabı zaten küçük kartlarda devreye girer;
 *     büyük kartlarda (minItemWidth ≥ 260) telefonda hâlâ 1 sütun çıkar. Üst sınır asıl işini
 *     GENİŞ ekranda yapar: 2560 px'te 8 sütuna dağılmayı columns=4'te durdurur.
 *
 * ⚠️ MUTASYON: `width / columns` formülüne dönülürse 1. ve 3. vaka; onLayout kaldırılırsa 4. vaka;
 * üst sınır `columns`a çekilirse 1. vaka KIRILIR.
 */
import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { fireEvent, render } from "@testing-library/react-native";

let mockResponsive: Record<string, unknown> = {};
jest.mock("@/hooks/useResponsive", () => ({ useResponsive: () => mockResponsive }));

import { ResponsiveGrid } from "@/components/ui/ResponsiveGrid";

type Ciz = ReturnType<typeof render>;

function ciz(minItemWidth: number | undefined, cocukSayisi = 6): Ciz {
  const cocuklar = Array.from({ length: cocukSayisi }, (_, i) => <Text key={i}>{`k${i}`}</Text>);
  return render(<ResponsiveGrid minItemWidth={minItemWidth}>{cocuklar}</ResponsiveGrid>);
}

/** Hücre `flexBasis` yüzdesinden sütun sayısını geri hesapla. */
function sutunSayisi(u: Ciz): number {
  const hucreler = u.UNSAFE_getAllByType(View).filter((n) => {
    const s = StyleSheet.flatten(n.props.style) as { flexBasis?: string | number } | undefined;
    return typeof s?.flexBasis === "string";
  });
  if (!hucreler.length) throw new Error("ızgara hücresi bulunamadı");
  const basis = (StyleSheet.flatten(hucreler[0].props.style) as { flexBasis: string }).flexBasis;
  return Math.round(100 / parseFloat(basis));
}

/** Dış ızgara View'ı (flexWrap taşıyan). */
function izgara(u: Ciz) {
  const n = u.UNSAFE_getAllByType(View).find((v) => {
    const s = StyleSheet.flatten(v.props.style) as { flexWrap?: string } | undefined;
    return s?.flexWrap === "wrap";
  });
  if (!n) throw new Error("ızgara kabı bulunamadı");
  return n;
}

const telefon = { width: 390, contentWidth: 390, columns: 1 };
const tabletKabuk = { width: 768, contentWidth: 352, columns: 2 };
const genis = { width: 2560, contentWidth: 2400, columns: 4 };

describe("sütun sayısı gerçek kaptan", () => {
  it("KRİTİK: telefonda küçük kartlar 2 sütun kalır (sensör kartları / sayısal AI girişleri)", () => {
    mockResponsive = telefon;
    expect(sutunSayisi(ciz(160))).toBe(2);
  });

  it("telefonda büyük kartlar tek sütun (Dashboard hero — regresyon yok)", () => {
    mockResponsive = telefon;
    expect(sutunSayisi(ciz(280))).toBe(1);
  });

  it("KRİTİK: kabuklu tablette karar PENCEREDEN değil İÇERİK alanından verilir", () => {
    // 768 px pencere, 352 px içerik. Eski kod: 768/2 = 384 ≥ 260 → 2 sütun (kart 182 px).
    mockResponsive = tabletKabuk;
    expect(sutunSayisi(ciz(260))).toBe(1);
  });

  it("geniş ekranda üst sınır columns'tur (2560 px'te 8 sütuna dağılmaz)", () => {
    mockResponsive = genis;
    expect(sutunSayisi(ciz(160))).toBe(4);
  });
});

describe("onLayout ölçümü", () => {
  it("KRİTİK: ölçüm tahmini EZER (kap daralınca sütun düşer)", () => {
    mockResponsive = genis;
    const u = ciz(160);
    expect(sutunSayisi(u)).toBe(4);
    fireEvent(izgara(u), "layout", { nativeEvent: { layout: { width: 400 } } });
    expect(sutunSayisi(u)).toBe(2);
  });

  it("1 px altı titreşim sütunu değiştirmez", () => {
    mockResponsive = telefon;
    const u = ciz(160);
    fireEvent(izgara(u), "layout", { nativeEvent: { layout: { width: 390 } } });
    const once = sutunSayisi(u);
    fireEvent(izgara(u), "layout", { nativeEvent: { layout: { width: 390.4 } } });
    expect(sutunSayisi(u)).toBe(once);
  });
});

describe("mevcut sözleşme korunur", () => {
  it("falsy çocuklar HAYALET hücre yaratmaz", () => {
    mockResponsive = telefon;
    const u = render(
      <ResponsiveGrid minItemWidth={160}>
        <Text>bir</Text>
        {false}
        {null}
        <Text>iki</Text>
      </ResponsiveGrid>
    );
    const hucreler = u.UNSAFE_getAllByType(View).filter((n) => {
      const s = StyleSheet.flatten(n.props.style) as { flexBasis?: string } | undefined;
      return typeof s?.flexBasis === "string";
    });
    expect(hucreler).toHaveLength(2);
  });

  it("tek çocuk da hücreye sarılır", () => {
    mockResponsive = telefon;
    const u = render(
      <ResponsiveGrid minItemWidth={160}>
        <Text>tek</Text>
      </ResponsiveGrid>
    );
    expect(u.getByText("tek")).toBeTruthy();
    expect(sutunSayisi(u)).toBe(2); // hücre genişliği içeriğe değil ızgaraya bağlı
  });
});
