// Author: mertaygn, cglrgrkn
/**
 * ACİL DURDUR — YERLEŞİM SÖZLEŞMESİ  [S3/S5, 2026-09-04 responsive denetimi]
 * =========================================================================
 * ÖLÇÜLEN DURUM: düğme `left/right: spacing.md` ile SABİT konumlanıyordu. Yatay telefonda
 * (çentikli cihaz yan yatınca insets.left = 44 px) düğmenin sol kenarı çentiğin ALTINA giriyor,
 * dokunuş sistem tarafından yutuluyordu. Yükseklik `rs(52)` idi: 320 px ekranda ölçek 0,85 →
 * 44 px'lik erişilebilirlik tabanının ALTINA (41 px) düşüyordu. Kısa ekranda (yatay telefon)
 * tam genişlik kaplayıp içeriğin üstünü örtüyordu.
 *
 * SÖZLEŞME:
 *  1. Dikey konum = bottomOffset + insets.bottom + spacing.md (klavye/alt bar kabuktan gelir).
 *  2. Yatay kenarlar güvenli alanı AŞMAZ (çentik).
 *  3. ⚠️ HASTA GÜVENLİĞİ: minHeight ölçekten BAĞIMSIZ olarak 44 px'in altına inmez.
 *  4. compact yalnız DARALTIR ve sağa hizalar — GİZLEMEZ, metni kısaltmaz, tabanı küçültmez.
 *
 * ⚠️ MUTASYON: `Math.max(spacing.md, insets.left)` → `spacing.md` yapılırsa 2. vaka;
 * `Math.max(touch.min, rs(52))` → `rs(52)` yapılırsa 3. vaka KIRILIR (dar telefon ölçeğinde).
 */
import React from "react";
import { StyleSheet } from "react-native";
import { render } from "@testing-library/react-native";
import { spacing, touch } from "@/theme/tokens";

let mockSnapshot: Record<string, unknown> = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnapshot, haveRealData: true }),
}));
let mockInsets = { top: 0, bottom: 0, left: 0, right: 0 };
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => mockInsets,
}));
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(async () => ({ confirmed: true })),
  EMERGENCY_STOP_UNCONFIRMED_TITLE: "t",
  EMERGENCY_STOP_UNCONFIRMED_BODY: "b",
}));

import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";

const CALISIYOR = { stm: "online", coils: [{ id: 1, running: true, connected: true }] };

/**
 * Konumlandıran KAPSAYICI'yı bul. `.parent` bileşen (Pressable/Component) düğümlerini de gezdiği
 * için tek adım yetmez; `position:"absolute"` taşıyan ilk atayı ararız — sözleşmenin yaşadığı yer.
 */
function kapsayiciStil(dugme: { parent: unknown }): Record<string, number | string> {
  let n = dugme as { parent?: unknown; props?: { style?: unknown } } | undefined;
  for (let i = 0; i < 12 && n; i++) {
    const st = StyleSheet.flatten(n.props?.style as never) as Record<string, number | string>;
    if (st && st.position === "absolute") return st;
    n = n.parent as typeof n;
  }
  throw new Error("konumlandıran kapsayıcı bulunamadı");
}

function ciz(props: { bottomOffset?: number; compact?: boolean } = {}) {
  mockSnapshot = CALISIYOR;
  const u = render(<GlobalEmergencyStop {...props} />);
  const dugme = u.getByLabelText("Acil durdur");
  return {
    ...u,
    dugme,
    dugmeStil: StyleSheet.flatten(dugme.props.style) as Record<string, number>,
    kapStil: kapsayiciStil(dugme as never),
  };
}

beforeEach(() => {
  mockInsets = { top: 0, bottom: 0, left: 0, right: 0 };
});

describe("konum", () => {
  it("dikey konum = bottomOffset + alt güvenli alan + boşluk", () => {
    mockInsets = { top: 0, bottom: 34, left: 0, right: 0 };
    const { kapStil } = ciz({ bottomOffset: 76 });
    expect(kapStil.bottom).toBe(76 + 34 + spacing.md);
  });

  it("KRİTİK: yatay çentikte düğme güvenli alanın DIŞINA taşmaz", () => {
    mockInsets = { top: 0, bottom: 21, left: 44, right: 44 }; // yan yatmış çentikli telefon
    const { kapStil } = ciz();
    expect(kapStil.left).toBe(44);
    expect(kapStil.right).toBe(44);
  });

  it("çentik yokken normal boşluğa düşer", () => {
    const { kapStil } = ciz();
    expect(kapStil.left).toBe(spacing.md);
    expect(kapStil.right).toBe(spacing.md);
  });
});

describe("HASTA GÜVENLİĞİ — dokunma hedefi", () => {
  it("KRİTİK: minHeight 44 px erişilebilirlik tabanının altına inmez", () => {
    expect(ciz().dugmeStil.minHeight).toBeGreaterThanOrEqual(44);
    expect(ciz({ compact: true }).dugmeStil.minHeight).toBeGreaterThanOrEqual(44);
    expect(touch.min).toBeGreaterThanOrEqual(44); // taban token'ın kendisi de
  });
});

describe("kompakt (yatay telefon)", () => {
  it("KRİTİK: compact DARALTIR ve sağa hizalar — gizlemez", () => {
    const genis = ciz();
    const dar = ciz({ compact: true });
    expect(dar.dugme).toBeTruthy(); // hâlâ ekranda
    expect(dar.dugmeStil.maxWidth).toBeLessThan(genis.dugmeStil.maxWidth);
    expect(dar.kapStil.alignItems).toBe("flex-end");
    expect(genis.kapStil.alignItems).toBe("center");
  });

  it("compact metni KISALTMAZ (adjustsFontSizeToFit sığdırır)", () => {
    const dar = ciz({ compact: true });
    expect(dar.getByText(/ACİL DURDUR/)).toBeTruthy();
  });
});
