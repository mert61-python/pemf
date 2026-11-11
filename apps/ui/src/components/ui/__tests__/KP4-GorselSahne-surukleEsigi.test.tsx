/**
 * KP-4 B1 · src/components/ui/GorselSahne.tsx — tam ekran görüntüleyicide SÜRÜKLEME eşiği: parmak / fare 2 px'ten AZ oynadıysa hareket
 * sürükleme sayılmaz (dokunuş düğmelere / sayfa çiplerine gider, görüntü titremez); herhangi bir eksende 2 px'i aşınca sürükleme yakalanır.
 * SAHTE (platform): PanResponder hareket durumu — ürünün KENDİ eşik işlevi, yapılandırmasından alınıp çağrılır (KP-3 AppShell deseni).
 */
import React from "react";
import { PanResponder, type PanResponderCallbacks } from "react-native";
import { render } from "@testing-library/react-native";
import { GorselSahne } from "@/components/ui/GorselSahne";

it("KRİTİK: 2 px'e kadar oynama sürükleme DEĞİL; yatayda ya da dikeyde 2 px'i aşan hareket sürüklemedir", () => {
  // ⚠️ spyOn birikir (jest-arayuz-test-tuzaklari) → temizle; bu bileşenin İLK create'i alınır.
  const casus = jest.spyOn(PanResponder, "create");
  casus.mockClear();
  render(<GorselSahne sayfalar={[{ k: "01_input", ad: "Girdi", uri: "file:///foto.jpg" }]} tavanY={400} sifirlaAnahtari="a" />);
  const cfg = casus.mock.calls[0][0] as PanResponderCallbacks;
  const sahiplen = (dx: number, dy: number) => cfg.onMoveShouldSetPanResponder!({} as never, { dx, dy } as never);
  expect(sahiplen(0, 0)).toBe(false);
  expect(sahiplen(2, -2)).toBe(false);
  expect(sahiplen(3, 0)).toBe(true);
  expect(sahiplen(0, -3)).toBe(true);
  expect(sahiplen(-2.5, 1)).toBe(true);
  casus.mockRestore();
});
