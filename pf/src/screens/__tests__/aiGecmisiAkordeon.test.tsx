// Author: mertaygn, cglrgrkn
/**
 * 🔴 SAHA ARIZASI (2026-09-09): AI GEÇMİŞİNDE "DÜZELT" KUTUSUNA YAZILAMIYORDU.
 *
 * ÖLÇÜLEN DAVRANIŞ: kayıt kartı açılıp "Düzelt"e basılınca "Doğru teşhis / düzeltme" kutusu
 * çıkıyor; kullanıcı YAZMAK İÇİN kutuya dokununca **kart kapanıyor** ve yazdığı metin kayboluyordu.
 * Yani hekim bir AI sonucunu düzeltemiyordu — kaydın yanına yazılacak klinik karar hiç girilemiyor.
 *
 * KÖK NEDEN (yapısal): genişletme dokunuşu KARTIN TAMAMINI sarıyordu
 * (`<TouchableOpacity onPress={toggle}>` → `<Card>` → başlık + gövde). `TextInput`e dokunmak
 * web'de bir tıklama olarak YUKARI SIZAR ve üstteki Touchable'ın `onPress`ini tetikler. İç
 * `TouchableOpacity`ler sızmayı durdurur (bu yüzden "Düzelt" düğmesi çalışıyordu), `TextInput`
 * DURDURMAZ — arıza tam bu asimetriden doğuyordu.
 *
 * SÖZLEŞME: genişletme dokunuşu YALNIZ BAŞLIK bölgesinde olur. Gövdedeki hiçbir öğe (metin kutusu,
 * Kaydet/Vazgeç, silme düğmesi) akordeon Touchable'ının İÇİNDE olamaz.
 *
 * ⚠️ Bu kapı DAVRANIŞI değil YAPIYI ölçer ve bu bilinçlidir: jest'in `fireEvent`i tarayıcının
 * tıklama sızmasını taklit etmez, dolayısıyla "kutuya dokun → kapandı mı" testi arıza dururken
 * bile YEŞİL kalırdı (yanlış-yeşil). Arızayı üreten koşul "kutu, toggle'ın alt ağacında" olduğu
 * için ölçülen şey odur.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async () => ({
    status: "success",
    data: [
      {
        id: 7,
        created_at: "2026-09-09T11:53:00",
        mode: "researcher",
        module_id: "cell_scratch",
        module_label: "Yara Kapanma (Scratch)",
        patient_name: "Mia",
        operator_email: "a@x.com",
        input_type: "image",
        result_summary: "Kapanma %29.36 · 2083 hücre",
        result_detail: { cell_count: 2083 },
        confidence: 0.607,
      },
    ],
  })),
  apiPost: jest.fn(async () => ({ status: "success" })),
  platformConfirm: jest.fn(async () => true),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperatorOptional: () => ({ operatorEmail: "a@x.com" }) }));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "researcher", isExpert: true, isResearcher: true }),
}));

import { act, fireEvent, render, within } from "@testing-library/react-native";
import React from "react";

import { AiHistoryScreen } from "@/screens/AiHistoryScreen";

/** Kartı aç ve "Düzelt" kipine geç (kullanıcının gerçek yolu). */
async function duzeltKipi() {
  const u = render(<AiHistoryScreen />);
  await act(async () => {});
  await act(async () => {
    fireEvent.press(u.getByLabelText(/Yara Kapanma \(Scratch\) kaydi/));
  });
  await act(async () => {
    fireEvent.press(u.getByLabelText("AI sonucunu düzelt"));
  });
  return u;
}

it("KRİTİK: düzeltme kutusu akordeon dokunuşunun İÇİNDE DEĞİL (kutuya dokunmak kartı kapatamaz)", async () => {
  const u = await duzeltKipi();

  const kutu = u.getByLabelText("Düzeltme açıklaması");
  expect(kutu).toBeTruthy(); // ara doğrulama: kip gerçekten açıldı (yanlış-yeşil kalkanı)

  // Akordeonu açıp kapatan öğe: başlık Touchable'ı (a11y durumu `expanded` taşır).
  const toggle = u.getByLabelText(/Yara Kapanma \(Scratch\) kaydi, acik/);
  expect(toggle.props.accessibilityState?.expanded).toBe(true);

  // ⚠️ ASIL KİLİT: kutu toggle'ın ALT AĞACINDA OLAMAZ. Olursa web'de tıklama sızar ve kart kapanır.
  expect(within(toggle).queryByLabelText("Düzeltme açıklaması")).toBeNull();
});

it("KRİTİK: gövdedeki DİĞER etkileşimler de toggle'ın dışında (Kaydet/Vazgeç/silme)", async () => {
  const u = await duzeltKipi();
  const toggle = u.getByLabelText(/Yara Kapanma \(Scratch\) kaydi, acik/);

  for (const etiket of ["Düzeltmeyi kaydet", "Yara Kapanma (Scratch) kaydını sil"]) {
    expect(u.getByLabelText(etiket)).toBeTruthy();
    expect(within(toggle).queryByLabelText(etiket)).toBeNull();
  }
});

it("KRİTİK: başlığa dokunmak kartı hâlâ açıp kapatıyor (düzeltme akışı bunu bozmadı)", async () => {
  const u = render(<AiHistoryScreen />);
  await act(async () => {});

  const kapali = u.getByLabelText(/Yara Kapanma \(Scratch\) kaydi/);
  expect(kapali.props.accessibilityState?.expanded).toBe(false);
  expect(u.queryByLabelText("AI sonucunu düzelt")).toBeNull();

  await act(async () => { fireEvent.press(kapali); });
  expect(u.getByLabelText("AI sonucunu düzelt")).toBeTruthy();

  await act(async () => {
    fireEvent.press(u.getByLabelText(/Yara Kapanma \(Scratch\) kaydi, acik/));
  });
  expect(u.queryByLabelText("AI sonucunu düzelt")).toBeNull();
});

it("KRİTİK: yazılan metin kutuda KALIR (arıza metni kaybediyordu)", async () => {
  const u = await duzeltKipi();
  const kutu = u.getByLabelText("Düzeltme açıklaması");

  await act(async () => { fireEvent.changeText(kutu, "gerçek teşhis: idiyopatik sistit"); });

  expect(u.getByLabelText("Düzeltme açıklaması").props.value).toBe("gerçek teşhis: idiyopatik sistit");
  // Kart AÇIK kalmalı: metin girmek akordeonu kapatmaz.
  expect(u.getByLabelText(/Yara Kapanma \(Scratch\) kaydi, acik/)).toBeTruthy();
});
