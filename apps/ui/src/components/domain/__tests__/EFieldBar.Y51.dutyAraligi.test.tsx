// Author: mertaygn, cglrgrkn
/**
 * Y51 (sahip, D1.61 devamı) — canlı E barı, toplam duty vekil modelin EĞİTİM aralığı dışındayken değeri GÖSTERİR ve yanına
 * "eğitim aralığı dışı — güvenilmez" yazar. B aralığı kuralı (İG-5.83: E '—') ayrı kapıda (`EFieldBar.durust`), aynen.
 * ======================================================================================================================
 * ÖLÇÜLEN KUSUR: tipik seans (5 bobin × %30 = Σduty 1,5) fantom modelinin eğitim aralığının (≈1,94–2,90) dışında; bar bunu
 * söylemeden sayı gösteriyordu. Veri ELLE YAZILMADI: `__fixtures__/efieldDuty.Y51.json` GERÇEK `efield_live.compute` +
 * modelin referans aralığından üretilir (bayatlık kapısı `tests/test_Y51_vekil_duty_EGITIM_ARALIGI_disi_etiketlenir.py`).
 * ⚠️ MUTASYON: etiket kaldırılırsa ya da değer '—'ye çevrilirse KIRMIZI.
 */
let mockSnap: any = {};
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: mockSnap }) }));

import React from "react";
import { render } from "@testing-library/react-native";
import { EFieldBar } from "@/components/domain/EFieldBar";

const F: any = require("./__fixtures__/efieldDuty.Y51.json");
const simdi = () => Date.now() / 1000;

it("KRİTİK: Σduty eğitim aralığı DIŞINDA → E değeri gösterilir VE 'eğitim aralığı dışı — güvenilmez' yazar", () => {
  mockSnap = { eField: { ...F.disarida, ts: simdi() } };
  const u = render(<EFieldBar />);
  expect(u.queryByLabelText("Tümör alan 0.0550")).not.toBeNull(); // değer GİZLENMEDİ
  const uyari = u.getByTestId("efield-duty-araligi-disi");
  const metin = [uyari.props.children].flat().join("");
  expect(metin).toContain("eğitim aralığı dışı — güvenilmez");
  expect(metin).toContain(`${F.disarida.dutyEgitimAraligi[0].toFixed(2)}–${F.disarida.dutyEgitimAraligi[1].toFixed(2)}`);
});

it("KARŞIT: Σduty eğitim aralığında → etiket YOK", () => {
  mockSnap = { eField: { ...F.icerde, ts: simdi() } };
  const u = render(<EFieldBar />);
  expect(u.queryByLabelText("Tümör alan 0.0550")).not.toBeNull();
  expect(u.queryByTestId("efield-duty-araligi-disi")).toBeNull();
});
