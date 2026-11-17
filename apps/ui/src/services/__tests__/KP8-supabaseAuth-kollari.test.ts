/**
 * KP-8 · src/services/supabaseAuth.ts kalan dallar (supabaseAuth.test düzeneği — `@supabase/supabase-js` istemcisi ve depolar sahte):
 *  - E-posta / parola alanı BOŞ (undefined) gelse de istek çökmez: boş dizeyle gider (sunucu reddeder, uygulama değil).
 *  - İstemci ileti taşımayan bir değer FIRLATIRSA (ör. düz metin) sonuç `ok:false` ve hata metni o değerden eşlenir (çökmez) —
 *    kayıt, giriş, parola sıfırlama, profil güncelleme.
 *  - Oturum okuması oturum alanı OLMAYAN yanıt verirse `null` (uydurma oturum yok).
 */
jest.mock("@supabase/supabase-js", () => {
  const auth = {
    signInWithPassword: jest.fn(async () => ({ error: null })),
    signUp: jest.fn(async () => ({ data: { session: null }, error: null })),
    resetPasswordForEmail: jest.fn(async () => ({ error: null })),
    updateUser: jest.fn(async () => ({ error: null })),
    getSession: jest.fn(async () => ({ data: {} })),
    resend: jest.fn(async () => ({ error: null })),
  };
  return { createClient: () => ({ auth }), __auth: auth };
});
jest.mock("@react-native-async-storage/async-storage", () => ({
  getItem: jest.fn(async () => null), setItem: jest.fn(async () => undefined), removeItem: jest.fn(async () => undefined),
}));
jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(async () => null), setItemAsync: jest.fn(async () => undefined), deleteItemAsync: jest.fn(async () => undefined),
}));

import { getCurrentSession, sendPasswordReset, signInUser, signUpUser, updateProfile } from "@/services/supabaseAuth";

const mockAuth = (jest.requireMock("@supabase/supabase-js") as { __auth: Record<string, jest.Mock> }).__auth;

beforeEach(() => jest.clearAllMocks());

it("boş (undefined) e-posta / parola çökmez: boş dizeyle gider", async () => {
  await signInUser(undefined as unknown as string, undefined as unknown as string);
  expect(mockAuth.signInWithPassword).toHaveBeenCalledWith({ email: "", password: "" });
  await signUpUser(undefined as unknown as string, "p");
  expect(mockAuth.signUp.mock.calls[0][0].email).toBe("");
  await sendPasswordReset(undefined as unknown as string);
  expect(mockAuth.resetPasswordForEmail.mock.calls[0][0]).toBe("");
});

it.each([
  ["kayıt", () => signUpUser("a@b.co", "p"), "signUp"],
  ["giriş", () => signInUser("a@b.co", "p"), "signInWithPassword"],
  ["sıfırlama", () => sendPasswordReset("a@b.co"), "resetPasswordForEmail"],
  ["profil", () => updateProfile({ first_name: "A" }), "updateUser"],
] as const)("%s: istemci ILETISIZ değer fırlatırsa ok:false + o değerden eşlenen metin (çökmez)", async (_ad, cagri, yontem) => {
  mockAuth[yontem].mockRejectedValueOnce("KP8 duz metin ag hatasi");
  const r = await cagri();
  expect(r.ok).toBe(false);
  expect(typeof r.error).toBe("string");
  expect((r.error as string).length).toBeGreaterThan(0);
});

it("oturum alanı OLMAYAN yanıt → null", async () => {
  mockAuth.getSession.mockResolvedValueOnce({ data: {} });
  await expect(getCurrentSession()).resolves.toBeNull();
});
