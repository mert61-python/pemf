/**
 * KP-3 C · utils/aiDetail kenar durumları — her test bir DAVRANIŞ iddiası (AI kayıt ayrıntısı ekranda ASLA "[object Object]" /
 * "function …" / ham blob göstermez):
 *  - fmtVal: işlev / bigint gibi gösterilemeyen değer "—"; skaler dizideki gösterilemeyen öğe de "—".
 *  - cleanDetail: nesne olmayan girdi (null / dizi / dizge) → {}; 600 karakteri aşan dizge alanı SAKLANMAZ.
 *  - detailRows: nesne olmayan girdi → satır yok; 400 karakteri aşan dizge satırı ATLANIR.
 * GERÇEK: modülün kendisi.
 */
import { cleanDetail, detailRows, fmtVal, STRIP_STRING_LEN, DISPLAY_STRING_LEN } from "@/utils/aiDetail";

it("fmtVal: gösterilemeyen değer '—'; skaler dizide gösterilemeyen öğe '—'", () => {
  expect(fmtVal(() => 1)).toBe("—");
  expect(fmtVal(BigInt(5))).toBe("—");
  expect(fmtVal([1, () => 2])).toBe("1, —");
  expect(fmtVal({ a: () => 1 })).not.toContain("function");
});

it("cleanDetail: nesne olmayan girdi → {}; uzun dizge alanı saklanmaz", () => {
  expect(cleanDetail(null)).toEqual({});
  expect(cleanDetail([1, 2])).toEqual({});
  expect(cleanDetail("metin")).toEqual({});
  expect(cleanDetail({ kisa: "a", uzun: "x".repeat(STRIP_STRING_LEN + 1) })).toEqual({ kisa: "a" });
});

it("detailRows: nesne olmayan girdi → satır yok; uzun dizge satırı atlanır", () => {
  expect(detailRows(null)).toEqual([]);
  expect(detailRows("metin")).toEqual([]);
  const r = detailRows({ sayi: 3, uzun: "y".repeat(DISPLAY_STRING_LEN + 1) });
  expect(r).toHaveLength(1);
  expect(r[0].value).toBe("3");
});
