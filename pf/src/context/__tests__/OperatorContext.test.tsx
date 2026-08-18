// Author: mertaygn, cglrgrkn
/**
 * AKTİF OPERATÖR — tek makine, çoklu veteriner (2026-08-08).
 *
 * Kilitlenen davranışlar:
 *   * GERİYE UYUM: operatör kayıtlı değilse `operatorEmail` oturum e-postasına düşer →
 *     tek veterinerli klinikler HİÇBİR ŞEY yapmadan çalışmaya devam eder,
 *   * çoklu-kullanıcı kipinde kimse seçilmemişse e-posta BOŞ döner (yanlış kişiye yazma!),
 *   * 401 (PIN hatalı) ile 423 (kilitli) AYRI mesajlanır,
 *   * ⚠️ HASTA GÜVENLİĞİ: seans sürerken hareketsizlik kilidi ERTELENİR.
 */
import React from "react";
import { Text } from "react-native";
import { act, render, waitFor } from "@testing-library/react-native";

const mockSession: { email: string } | null = { email: "sahip@klinik.com" };
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: mockSession }) }));

const mockGet = jest.fn();
const mockPost = jest.fn();
// ⚠️ 2026-08-09 (Tier 1): PIN doğrulanınca backend kısa ömürlü bir OPERATÖR JETONU verir ve
// yazma yollarında `operator_email` ondan türetilir. Jeton kurulmazsa backend, kayıtlı bir
// hekimin adına yazmayı REDDEDER (kayıt sahipsiz kalır) → bu mock kritik.
const mockSetToken = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockGet(...a),
  apiPost: (...a: unknown[]) => mockPost(...a),
  setOperatorToken: (...a: unknown[]) => mockSetToken(...a),
}));

import { OperatorProvider, useOperator, type EnrollResult } from "../OperatorContext";

function Prob() {
  const o = useOperator();
  return (
    <>
      <Text testID="mail">{o.operatorEmail || "(bos)"}</Text>
      <Text testID="coklu">{o.multiUser ? "coklu" : "tek"}</Text>
      <Text testID="aktif">{o.active?.display_name || "(yok)"}</Text>
    </>
  );
}

let sonBaglam: ReturnType<typeof useOperator> | null = null;
function Yakala() {
  sonBaglam = useOperator();
  return null;
}

const kur = (p: { sessionActive?: boolean; autoLockMs?: number } = {}) =>
  render(
    <OperatorProvider {...p}>
      <Prob />
      <Yakala />
    </OperatorProvider>,
  );

beforeEach(() => {
  jest.useRealTimers();
  sonBaglam = null;
  mockGet.mockReset().mockResolvedValue({ ok: true, data: [] });
  mockPost.mockReset().mockResolvedValue({ ok: true });
  mockSetToken.mockReset();
});

describe("geriye uyum — tek veterinerli klinik", () => {
  it("KRİTİK: operatör kayıtlı değilse oturum e-postası kullanılır", async () => {
    const { getByTestId } = kur();
    await waitFor(() => expect(getByTestId("mail").children.join("")).toBe("sahip@klinik.com"));
    expect(getByTestId("coklu").children.join("")).toBe("tek");
  });
});

describe("çoklu-kullanıcı kipi", () => {
  it("KRİTİK: operatör KAYITLIYSA ve kimse seçilmemişse e-posta BOŞ döner", async () => {
    // Yanlış kişiye kayıt yazmaktansa boş yazmak yeğdir — atıf hatası KVKK sorunudur.
    mockGet.mockResolvedValue({ ok: true, data: [{ email: "a@x.com", display_name: "Dr. A" }] });
    const { getByTestId } = kur();
    await waitFor(() => expect(getByTestId("coklu").children.join("")).toBe("coklu"));
    expect(getByTestId("mail").children.join("")).toBe("(bos)");
  });

  it("doğru PIN ile geçiş aktif operatörü belirler", async () => {
    mockGet.mockResolvedValue({ ok: true, data: [{ email: "a@x.com", display_name: "Dr. A" }] });
    const { getByTestId } = kur();
    await waitFor(() => expect(sonBaglam).not.toBeNull());
    await act(async () => { await sonBaglam!.switchTo("a@x.com", "123456"); });
    await waitFor(() => expect(getByTestId("mail").children.join("")).toBe("a@x.com"));
    expect(getByTestId("aktif").children.join("")).toBe("Dr. A");
  });

  it("KRİTİK: 401 → 'bad_pin', 423 → 'locked' (ayrı mesajlar)", async () => {
    mockGet.mockResolvedValue({ ok: true, data: [{ email: "a@x.com", display_name: "Dr. A" }] });
    kur();
    await waitFor(() => expect(sonBaglam).not.toBeNull());

    mockPost.mockImplementation((_p: string, _b: unknown, fb: unknown, opts: { onHttpError?: (s: number) => void }) => {
      opts?.onHttpError?.(401); return Promise.resolve(fb);
    });
    await act(async () => {
      expect(await sonBaglam!.switchTo("a@x.com", "000000")).toEqual({ ok: false, error: "bad_pin" });
    });

    mockPost.mockImplementation((_p: string, _b: unknown, fb: unknown, opts: { onHttpError?: (s: number) => void }) => {
      opts?.onHttpError?.(423); return Promise.resolve(fb);
    });
    await act(async () => {
      expect(await sonBaglam!.switchTo("a@x.com", "000000")).toEqual({ ok: false, error: "locked" });
    });
  });

  it("başarısız geçiş aktif operatörü DEĞİŞTİRMEZ", async () => {
    mockGet.mockResolvedValue({ ok: true, data: [{ email: "a@x.com", display_name: "Dr. A" }] });
    const { getByTestId } = kur();
    await waitFor(() => expect(sonBaglam).not.toBeNull());
    await act(async () => { await sonBaglam!.switchTo("a@x.com", "123456"); });
    mockPost.mockImplementation((_p: string, _b: unknown, fb: unknown, opts: { onHttpError?: (s: number) => void }) => {
      opts?.onHttpError?.(401); return Promise.resolve(fb);
    });
    await act(async () => { await sonBaglam!.switchTo("a@x.com", "999999"); });
    expect(getByTestId("mail").children.join("")).toBe("a@x.com");
  });

  it("kayıt (enroll) sonrası kişi doğrudan aktif olur — PIN tekrar sorulmaz", async () => {
    const { getByTestId } = kur();
    await waitFor(() => expect(sonBaglam).not.toBeNull());
    mockGet.mockResolvedValue({ ok: true, data: [{ email: "sahip@klinik.com", display_name: "Dr. Sahip" }] });
    await act(async () => { expect((await sonBaglam!.enroll("Dr. Sahip", "123456")).ok).toBe(true); });
    await waitFor(() => expect(getByTestId("aktif").children.join("")).toBe("Dr. Sahip"));
  });
});

/**
 * PIN DEĞİŞTİRME KAPISI (2026-08-09 denetimi).
 * Backend, e-posta zaten kayıtlıysa 401 döner ve MEVCUT PIN ister — yoksa bu ucu çağırabilen
 * herkes başka bir hekimin PIN'ini ezip onun kimliğiyle kayıt yazabilirdi. İstemci bu 401'i
 * "kayıt başarısız" diye yutarsa kullanıcı ne olduğunu ANLAYAMAZ ve PIN'ini asla değiştiremez.
 */
describe("PIN değiştirme — eski PIN kapısı", () => {
  const httpKodla = (kod: number) =>
    mockPost.mockImplementation(async (_yol, _govde, varsayilan, opt) => {
      (opt as { onHttpError?: (s: number) => void })?.onHttpError?.(kod);
      return varsayilan;
    });

  it("eski PIN gönderilir", async () => {
    kur();
    await waitFor(() => expect(sonBaglam).not.toBeNull());
    await act(async () => { await sonBaglam!.enroll("Dr. Sahip", "222222", "111111"); });
    expect(mockPost).toHaveBeenLastCalledWith(
      "/operators/enroll",
      expect.objectContaining({ pin: "222222", eski_pin: "111111" }),
      null, expect.anything());
  });

  it("401 → need_old_pin (kullanıcıya mevcut PIN sorulabilsin)", async () => {
    kur();
    await waitFor(() => expect(sonBaglam).not.toBeNull());
    httpKodla(401);
    let r: EnrollResult;
    await act(async () => { r = await sonBaglam!.enroll("Dr. Sahip", "222222"); });
    expect(r!).toEqual({ ok: false, error: "need_old_pin" });
  });

  it("423 → locked ('PIN hatalı' DEME, kullanıcı boşuna denemesin)", async () => {
    kur();
    await waitFor(() => expect(sonBaglam).not.toBeNull());
    httpKodla(423);
    let r: EnrollResult;
    await act(async () => { r = await sonBaglam!.enroll("Dr. Sahip", "222222", "111111"); });
    expect(r!).toEqual({ ok: false, error: "locked" });
  });

  it("başarısız kayıt aktif operatörü DEĞİŞTİRMEZ", async () => {
    const { getByTestId } = kur();
    await waitFor(() => expect(sonBaglam).not.toBeNull());
    httpKodla(401);
    await act(async () => { await sonBaglam!.enroll("Saldirgan", "999999"); });
    expect(getByTestId("aktif").children.join("")).toBe("(yok)");
  });
});

describe("hareketsizlik kilidi", () => {
  it("süre dolunca aktif operatör düşer", async () => {
    // ⚠️ Sahte zamanlayıcı RENDER'DAN ÖNCE açılmalı: aralık (setInterval) effect içinde kurulur;
    // sonradan geçilirse zaten-kurulmuş aralık sahte saati DİNLEMEZ ve test yanlış yere bakar.
    jest.useFakeTimers();
    mockGet.mockResolvedValue({ ok: true, data: [{ email: "a@x.com", display_name: "Dr. A" }] });
    const { getByTestId } = kur({ autoLockMs: 1 });
    await act(async () => {});                                   // effect + liste yüklemesi
    await act(async () => { await sonBaglam!.switchTo("a@x.com", "123456"); });
    expect(getByTestId("aktif").children.join("")).toBe("Dr. A");

    await act(async () => { jest.advanceTimersByTime(31_000); });
    expect(getByTestId("aktif").children.join("")).toBe("(yok)");
  });

  it("KRİTİK — HASTA GÜVENLİĞİ: SEANS SÜRERKEN kilitlenmez", async () => {
    // Bobinler hastanın üzerinde çalışırken kimlik düşürmek, operatörü kritik anda PIN
    // ekranına sokar ve ACİL DURDUR'a erişimi geciktirir.
    jest.useFakeTimers();
    mockGet.mockResolvedValue({ ok: true, data: [{ email: "a@x.com", display_name: "Dr. A" }] });
    const { getByTestId } = kur({ autoLockMs: 1, sessionActive: true });
    await act(async () => {});
    await act(async () => { await sonBaglam!.switchTo("a@x.com", "123456"); });

    await act(async () => { jest.advanceTimersByTime(120_000); });
    expect(getByTestId("aktif").children.join("")).toBe("Dr. A");
  });

  it("touch() sayacı sıfırlar", async () => {
    jest.useFakeTimers();
    mockGet.mockResolvedValue({ ok: true, data: [{ email: "a@x.com", display_name: "Dr. A" }] });
    const { getByTestId } = kur({ autoLockMs: 60_000 });
    await act(async () => {});
    await act(async () => { await sonBaglam!.switchTo("a@x.com", "123456"); });

    await act(async () => { jest.advanceTimersByTime(45_000); });
    act(() => sonBaglam!.touch());
    await act(async () => { jest.advanceTimersByTime(45_000); });
    expect(getByTestId("aktif").children.join("")).toBe("Dr. A");
  });

  it("elle lock() aktif operatörü düşürür", async () => {
    mockGet.mockResolvedValue({ ok: true, data: [{ email: "a@x.com", display_name: "Dr. A" }] });
    const { getByTestId } = kur();
    await waitFor(() => expect(sonBaglam).not.toBeNull());
    await act(async () => { await sonBaglam!.switchTo("a@x.com", "123456"); });
    act(() => sonBaglam!.lock());
    await waitFor(() => expect(getByTestId("aktif").children.join("")).toBe("(yok)"));
  });
});

/**
 * OPERATÖR JETONU (2026-08-09 denetimi, Tier 1).
 * PIN doğrulaması eskiden hiçbir şeye bağlanmıyordu: `operator_email` her uçta istemci beyanıydı
 * ve cihaza erişen herkes başka bir hekimin adına kayıt yazabiliyordu. Artık doğrulama kısa
 * ömürlü bir jeton üretir; istemci onu KURMAZSA backend kayıtlı hekim adına yazmayı reddeder
 * (kayıt sahipsiz kalır) — yani bu bağlantı kopunca çoklu-operatör atfı SESSİZCE çalışmaz.
 */
describe("operatör jetonu", () => {
  it("KRİTİK: PIN doğrulanınca jeton KURULUR", async () => {
    kur();
    await waitFor(() => expect(sonBaglam).not.toBeNull());
    mockPost.mockResolvedValue({ ok: true, operator_token: "JETON-123" });
    await act(async () => { await sonBaglam!.switchTo("a@x.com", "123456"); });
    expect(mockSetToken).toHaveBeenCalledWith("JETON-123");
  });

  it("KRİTİK: kayıt (enroll) da jeton kurar — ilk operatörün kayıtları sahipsiz kalmasın", async () => {
    kur();
    await waitFor(() => expect(sonBaglam).not.toBeNull());
    mockPost.mockResolvedValue({ ok: true, operator_token: "JETON-KAYIT" });
    await act(async () => { await sonBaglam!.enroll("Dr. Sahip", "123456"); });
    expect(mockSetToken).toHaveBeenCalledWith("JETON-KAYIT");
  });

  it("KRİTİK: kilitlenince jeton DÜŞER (backend o hekim adına yazmaya devam etmesin)", async () => {
    kur();
    await waitFor(() => expect(sonBaglam).not.toBeNull());
    mockPost.mockResolvedValue({ ok: true, operator_token: "T" });
    await act(async () => { await sonBaglam!.switchTo("a@x.com", "123456"); });
    mockSetToken.mockClear();
    await act(async () => { sonBaglam!.lock(); });
    expect(mockSetToken).toHaveBeenCalledWith(null);
  });

  it("başarısız PIN jeton KURMAZ", async () => {
    kur();
    await waitFor(() => expect(sonBaglam).not.toBeNull());
    mockPost.mockImplementation(async (_y, _g, varsayilan, opt) => {
      (opt as { onHttpError?: (s: number) => void })?.onHttpError?.(401);
      return varsayilan;
    });
    await act(async () => { await sonBaglam!.switchTo("a@x.com", "000000"); });
    expect(mockSetToken).not.toHaveBeenCalled();
  });
});
