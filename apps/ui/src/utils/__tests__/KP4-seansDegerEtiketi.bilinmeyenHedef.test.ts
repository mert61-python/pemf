/**
 * KP-4 B1 · src/utils/seansDegerEtiketi.ts — AI Pro seans modunda TANINMAYAN hedef parçası (organ adı değil, "(otomatik)" değil, "Ad N"
 * değil — ör. yeni bir backend hedef adı) gösterimde HAM kalır: çeviri uydurulmaz, parça düşmez; model parçası yine çevrilir.
 */
import type { TFunction } from "i18next";
import i18n from "i18next";
import { modEtiketi } from "@/utils/seansDegerEtiketi";

const t = ((k: string, o?: object) => i18n.t(k, o as never)) as unknown as TFunction;

it("KRİTİK: tanınmayan hedef parçası HAM kalır (düşmez, uydurulmaz)", () => {
  expect(modEtiketi(t, "AI Pro · Fantom Tümör · Odak-B")).toBe("AI Pro · Fantom Tümör · Odak-B");
  expect(modEtiketi(t, "AI Pro · Kedi Organ · Böbrek · Sağ lob")).toBe("AI Pro · Kedi Organ · Böbrek · Sağ lob");
});
