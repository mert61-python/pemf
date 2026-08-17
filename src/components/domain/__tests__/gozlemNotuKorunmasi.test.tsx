// Author: mertaygn, cglrgrkn
/**
 * YAZILMIŞ GÖZLEM NOTU, BOBİN `running` RAPORLAYINCA UYARISIZ SİLİNİYORDU (bulgu 20, cid. 5).
 *
 * `ObservationNotesModal`ın sıfırlama effect'i KOŞULSUZ ve `visible`'ın HER İKİ yönündeki değişimde
 * ateşliyordu. Modal ise ACİL DURDUR'un üstünü kapatmasın diye herhangi bir bobin `running`
 * raporladığında GİZLENİYOR (`ControlScreen` bileşeni koşulsuz render ediyor → `visible:false`'da
 * unmount OLMUYOR). Sonuç: seans bitti, hekim gözlem notu yazıyor, DIŞSAL bir kaynak bir bobini
 * `running` raporluyor (STOP'u kaçırmış bir ESP bobini yeniden bağlanınca `status: running`
 * yayınlıyor; ya da masaüstü istemcisi / ikinci hekim seans başlatıyor) → modal gizlenir, yazılmış
 * not + seçili tepki chip'leri UYARISIZ silinir, hiçbir yere kaydedilmez. Donanım durunca modal
 * doğru hasta adıyla ama BOŞ açılır → hekim silindiğini fark etmeyebilir.
 *
 * ⚠️ Modal'ı GİZLEMEK kasıtlı ve doğru — bu test onu değiştirmiyor. Kusur, gizlenmede de
 * SIFIRLAMA yapılmasıydı.
 * ⚠️ #48 KORUMASI KORUNUYOR (T3): A hastasının notu B'ye bulaşmamalı.
 *
 * ⚠️ TESTLER TAMAMEN DAVRANIŞSAL — kaynakta desen ARAMIYOR. Yorum satırına "visible dep değil"
 * yazan bir mutasyon bu testlerden GEÇEMEZ.
 * ⚠️ GİZLİYKEN assert YAPILMIYOR: jest'te `Modal._shouldShowModal` bir kez gösterildikten sonra
 * `isRendered` ile TRUE kalır (`modalDismissed` native olayı hiç gelmez) → gizlenmiş modalın
 * çocukları ağaçta durur. Değer, YENİDEN GÖSTERİLDİKTEN sonra okunuyor.
 */
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/services/apiClient", () => ({
  apiPost: jest.fn(async () => ({ status: "success" })),
  platformAlert: jest.fn(),
}));

import { fireEvent, render, waitFor } from "@testing-library/react-native";
import React from "react";

import { apiPost } from "@/services/apiClient";

import { ObservationNotesModal } from "../ObservationNotesModal";

const NOT = "sağ arka bacakta hafif titreme";
// ⚠️ TEK nesne, rerender'lar arası AYNI: `ControlScreen`deki `obsSession` state'inin davranışı bu.
const REX = { patientName: "Rex", mode: "Manuel" } as never;

const notAlani = (u: ReturnType<typeof render>) => u.getByLabelText("Gözlem notları");

beforeEach(() => {
  (apiPost as jest.Mock).mockClear();
});

it("KRİTİK: modal GİZLENİP tekrar gösterilince yazılmış not KORUNUR", () => {
  const u = render(<ObservationNotesModal visible session={REX} onClose={() => {}} />);

  fireEvent.press(u.getByText("Uyudu"));
  fireEvent.changeText(notAlani(u), NOT);
  // ÖN-ASSERT: yazma gerçekten oldu (aksi hâlde son assert anlamsız yeşile dönebilirdi).
  expect(notAlani(u).props.value).toBe(NOT);

  // Dışsal bir bobin `running` raporladı → modal gizlendi.
  u.rerender(<ObservationNotesModal visible={false} session={REX} onClose={() => {}} />);
  // Donanım durdu → modal geri gösterildi.
  u.rerender(<ObservationNotesModal visible session={REX} onClose={() => {}} />);

  expect(notAlani(u).props.value).toBe(NOT);
});

it("KRİTİK: gizlenme sonrası KAYDET, notu ve tepkiyi TAM gönderir", async () => {
  const u = render(<ObservationNotesModal visible session={REX} onClose={() => {}} />);
  fireEvent.press(u.getByText("Uyudu"));
  fireEvent.changeText(notAlani(u), NOT);
  u.rerender(<ObservationNotesModal visible={false} session={REX} onClose={() => {}} />);
  u.rerender(<ObservationNotesModal visible session={REX} onClose={() => {}} />);

  fireEvent.press(u.getByText("💾 Kaydet"));

  await waitFor(() =>
    expect(apiPost).toHaveBeenCalledWith(
      "/session/notes",
      expect.objectContaining({ notes: `Uyudu — ${NOT}`, patient_name: "Rex" }),
      null,
    ),
  );
});

it("#48 KORUMASI: HASTA DEĞİŞİMİNDE not SİLİNİR (yamadan önce de yeşil — kasıtlı bekçi)", () => {
  // Effect'i tamamen silen ya da dep'i `[]` yapan "aşırı düzeltme" bu testi KIRAR.
  const u = render(<ObservationNotesModal visible session={REX} onClose={() => {}} />);
  fireEvent.changeText(notAlani(u), NOT);
  expect(notAlani(u).props.value).toBe(NOT);

  u.rerender(
    <ObservationNotesModal visible session={{ patientName: "Bella" } as never} onClose={() => {}} />,
  );

  expect(notAlani(u).props.value).toBe("");
});

it("AÇILIŞTA sıfırlama korunuyor (session null → yeni hasta)", () => {
  const u = render(<ObservationNotesModal visible session={REX} onClose={() => {}} />);
  fireEvent.changeText(notAlani(u), NOT);

  // `onClose` → ControlScreen `setObsSession(null)`; sonra yeni seans bitince yeniden atanır.
  u.rerender(<ObservationNotesModal visible={false} session={null} onClose={() => {}} />);
  u.rerender(
    <ObservationNotesModal visible session={{ patientName: "Rex" } as never} onClose={() => {}} />,
  );

  expect(notAlani(u).props.value).toBe("");
});
