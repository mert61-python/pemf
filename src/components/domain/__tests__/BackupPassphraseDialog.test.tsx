// Author: mertaygn, cglrgrkn
/**
 * YEDEK PAROLASI DİYALOĞU (2026-08-09 denetimi, Tier 1).
 *
 * ARIZA: parola `window.prompt` ile TEK KEZ soruluyordu.
 *   • Yazım hatası fark edilmiyordu → dosya KALICI olarak açılamaz hâle geliyor ve bu ancak
 *     yedeğe ihtiyaç duyulan gün (eski makine ölmüş, geri dönüş yok) anlaşılıyordu,
 *   • asgari politika yoktu → tek karakterlik parola kabul ediliyordu,
 *   • `window.prompt` parolayı düz metin gösterir ve native'de hiç çalışmaz.
 */
import { render, fireEvent } from "@testing-library/react-native";
import { BackupPassphraseDialog, MIN_PAROLA } from "@/components/domain/BackupPassphraseDialog";

const GECERLI = "klinik-yedek-2026";

function kur(kip: "olustur" | "gir" = "olustur") {
  const onSubmit = jest.fn();
  const onCancel = jest.fn();
  const u = render(
    <BackupPassphraseDialog visible kip={kip} onSubmit={onSubmit} onCancel={onCancel} />,
  );
  return { ...u, onSubmit, onCancel };
}

const yaz = (u: ReturnType<typeof kur>, etiket: string, deger: string) =>
  fireEvent.changeText(u.getByLabelText(etiket), deger);

it("KRİTİK: parola İKİ KEZ sorulur (yazım hatası yedeği kurtarılamaz kılar)", () => {
  const u = kur("olustur");
  expect(u.getByLabelText("Yedek parolası")).toBeTruthy();
  expect(u.getByLabelText("Yedek parolası tekrar")).toBeTruthy();
});

it("KRİTİK: parolalar UYUŞMUYORSA gönderilemez", () => {
  const u = kur("olustur");
  yaz(u, "Yedek parolası", GECERLI);
  yaz(u, "Yedek parolası tekrar", GECERLI + "x");
  fireEvent.press(u.getByLabelText("Yedeği oluştur"));
  expect(u.onSubmit).not.toHaveBeenCalled();
  expect(u.getByText("Parolalar aynı değil.")).toBeTruthy();
});

it(`KRİTİK: ${MIN_PAROLA} karakterden KISA parola gönderilemez`, () => {
  const u = kur("olustur");
  const kisa = "abcdefg";
  yaz(u, "Yedek parolası", kisa);
  yaz(u, "Yedek parolası tekrar", kisa);
  fireEvent.press(u.getByLabelText("Yedeği oluştur"));
  expect(u.onSubmit).not.toHaveBeenCalled();
  expect(u.getByText(`En az ${MIN_PAROLA} karakter olmalı.`)).toBeTruthy();
});

it("geçerli ve eşleşen parola gönderilir", () => {
  const u = kur("olustur");
  yaz(u, "Yedek parolası", GECERLI);
  yaz(u, "Yedek parolası tekrar", GECERLI);
  fireEvent.press(u.getByLabelText("Yedeği oluştur"));
  expect(u.onSubmit).toHaveBeenCalledWith(GECERLI);
});

it("parola VARSAYILAN olarak gizli, göster/gizle ile açılır", () => {
  const u = kur("olustur");
  expect(u.getByLabelText("Yedek parolası").props.secureTextEntry).toBe(true);
  fireEvent.press(u.getByLabelText("Parolayı göster"));
  expect(u.getByLabelText("Yedek parolası").props.secureTextEntry).toBe(false);
});

it("kayıp riski AÇIKÇA yazılır (parola kaybolursa yedek kurtarılamaz)", () => {
  const u = kur("olustur");
  expect(u.getByText(/AÇILAMAZ ve kurtarılamaz/)).toBeTruthy();
});

it("'gir' kipinde TEK alan olur (mevcut dosyayı açarken tekrar sormak anlamsız)", () => {
  const u = kur("gir");
  expect(u.queryByLabelText("Yedek parolası tekrar")).toBeNull();
  yaz(u, "Yedek parolası", "her-ne-ise");
  fireEvent.press(u.getByLabelText("Devam et"));
  expect(u.onSubmit).toHaveBeenCalledWith("her-ne-ise");
});

it("'gir' kipinde BOŞ parola gönderilemez", () => {
  const u = kur("gir");
  fireEvent.press(u.getByLabelText("Devam et"));
  expect(u.onSubmit).not.toHaveBeenCalled();
});

it("vazgeçilince onSubmit ÇAĞRILMAZ", () => {
  const u = kur("olustur");
  fireEvent.press(u.getByLabelText("Vazgeç"));
  expect(u.onCancel).toHaveBeenCalled();
  expect(u.onSubmit).not.toHaveBeenCalled();
});
