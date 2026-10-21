// Author: mertaygn, cglrgrkn
/**
 * I18NI-A2.8 — AI Pro hedef adayının `label` alanı VERİDİR (onay mührü etiketi; Türkçe ön ekli "Tümör T1" / "Kuyu B3"). Sunucu gösterim
 * hâlini ayrı `etiketGosterim` alanında istek / cihaz dilinde kurar (yalnız-ek). Halka erişilebilirlik etiketi ve yedek liste satırı
 * GÖSTERİMİ basmalı; alanı vermeyen ESKİ sunucuda `label`'a düşmeli (TR görünüm göç öncesiyle aynı).
 */
import React from "react";
import { act, render } from "@testing-library/react-native";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";
import { HedefHalkalari, HedefListesi } from "../aipro/HedefSecici";

const depo = { setItem: async () => undefined };
const YENI = [{ id: 1, label: "Tümör T1", etiketGosterim: "Tumour T1", pxn: [0.3, 0.4], reliability: 0.8 }];
const ESKI = [{ id: 1, label: "Tümör T1", pxn: [0.3, 0.4], reliability: 0.8 }];

function metin(u: ReturnType<typeof render>): string {
  const topla = (n: any): string => {
    if (n == null) return "";
    if (typeof n === "string") return n;
    if (Array.isArray(n)) return n.map(topla).join("");
    return topla(n.children);
  };
  return topla(u.toJSON());
}

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

it("EN: halka etiketi ve liste satırı GÖSTERİM alanını basar (VERİ etiketi Türkçe kalsa da)", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  const h = render(<HedefHalkalari hedefler={YENI} seciliId={1} onSec={jest.fn()} kutu={{ width: 100, height: 100 }} />);
  expect(h.getByLabelText("Target 1 / 1: Tumour T1, confidence 80 percent, selected")).toBeTruthy();
  const l = render(<HedefListesi hedefler={YENI} seciliId={0} onSec={jest.fn()} />);
  expect(metin(l)).toContain("Tumour T1");
  expect(metin(l)).not.toContain("Tümör");
  expect(l.getByLabelText("Target 1 / 1: Tumour T1, confidence 80 percent")).toBeTruthy();
});

it("TR + eski sunucu (alan yok): `label` aynen basılır — göç öncesiyle aynı", () => {
  const h = render(<HedefHalkalari hedefler={ESKI} seciliId={1} onSec={jest.fn()} kutu={{ width: 100, height: 100 }} />);
  expect(h.getByLabelText("Hedef 1 / 1: Tümör T1, güven yüzde 80, seçili")).toBeTruthy();
  expect(metin(render(<HedefListesi hedefler={ESKI} seciliId={0} onSec={jest.fn()} />))).toContain("○ Tümör T1");
});
