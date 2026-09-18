// Author: mertaygn, cglrgrkn
/**
 * supabaseAuth — kimlik doğrulama sözleşmesi.
 *
 * GERÇEK VAKA (2026-08-05): Operatör doğru şifreyle giremedi; canlı Supabase'e doğrudan
 * sorulduğunda `Mert…` → HTTP 200, `Mert… ` (sonda boşluk) → HTTP 400 çıktı. E-posta trim
 * ediliyordu ama ŞİFRE edilmiyordu. Mobil klavye / pano / şifre yöneticisi şifrenin sonuna
 * sıklıkla boşluk ekler; alanda görünür fark olmadığı için kullanıcı "E-posta veya şifre hatalı"
 * mesajını çözemiyor. Kayıt ve giriş AYNI kuralı uygulamak ZORUNDA — aksi halde boşlukla
 * kaydolan hesap boşluksuz giremez (kalıcı kilitlenme).
 */
// NOT: jest.mock fabrikaları import'ların ÜSTÜNE hoist edilir → fabrika, dışarıdaki bir `const`
// henüz BAŞLATILMADAN çalışır ve mock `undefined` olur (çağrı sayısı 0 görünür). Bu yüzden sahte
// nesne fabrikanın İÇİNDE kurulur; referansı test içinde modülden alırız.
jest.mock("@supabase/supabase-js", () => {
  const auth = {
    signInWithPassword: jest.fn(async () => ({ error: null })),
    signUp: jest.fn(async () => ({ data: { session: null }, error: null })),
    resetPasswordForEmail: jest.fn(async () => ({ error: null })),
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

import { signInUser, signUpUser } from "@/services/supabaseAuth";

const mockAuth = (jest.requireMock("@supabase/supabase-js") as { __auth: {
  signInWithPassword: jest.Mock; signUp: jest.Mock;
  resetPasswordForEmail: jest.Mock; resend: jest.Mock;
} }).__auth;

beforeEach(() => {
  jest.clearAllMocks();
  mockAuth.signInWithPassword.mockResolvedValue({ error: null });
  mockAuth.signUp.mockResolvedValue({ data: { session: null }, error: null });
});

describe("şifre boşluk kırpma (sessiz giriş hatası)", () => {
  it("KRİTİK: sondaki boşluk giriş öncesi ATILIR", async () => {
    await signInUser("op@klinik.com", "Sifre1234 ");
    expect(mockAuth.signInWithPassword).toHaveBeenCalledWith({
      email: "op@klinik.com",
      password: "Sifre1234",
    });
  });

  it("baştaki boşluk da atılır", async () => {
    await signInUser("op@klinik.com", "  Sifre1234");
    expect(mockAuth.signInWithPassword.mock.calls[0][0].password).toBe("Sifre1234");
  });

  it("İÇ boşluğa DOKUNULMAZ (gerçek parola karakteri olabilir)", async () => {
    await signInUser("op@klinik.com", " iki kelime ");
    expect(mockAuth.signInWithPassword.mock.calls[0][0].password).toBe("iki kelime");
  });

  it("KRİTİK: kayıt ve giriş AYNI kuralı uygular (kilitlenme olmasın)", async () => {
    await signUpUser("yeni@klinik.com", "Sifre1234 \n");
    await signInUser("yeni@klinik.com", " Sifre1234");
    expect(mockAuth.signUp.mock.calls[0][0].password).toBe("Sifre1234");
    expect(mockAuth.signInWithPassword.mock.calls[0][0].password).toBe("Sifre1234");
  });

  it("e-posta da trim edilir (mevcut davranış korunuyor)", async () => {
    await signInUser("  op@klinik.com  ", "Sifre1234");
    expect(mockAuth.signInWithPassword.mock.calls[0][0].email).toBe("op@klinik.com");
  });
});

describe("hata mesajları", () => {
  it("hesap-varlığı SIZDIRILMAZ (e-posta enumerasyonu)", async () => {
    mockAuth.signUp.mockResolvedValueOnce({ data: { session: null }, error: { message: "User already registered" } } as never);
    const r = await signUpUser("var@klinik.com", "Sifre1234");
    expect(r.ok).toBe(false);
    expect(r.error).not.toMatch(/zaten bir hesap var/i);   // eski sızdıran metin
    expect(r.error).toMatch(/giriş yapmayı|şifrenizi sıfırla/i);
  });

  it("giriş hatası artık DOĞRULAMA'ya yönlendirmez, boşluk/harf ipucu verir", async () => {
    // 2026-08-06: e-posta doğrulama akışı kaldırıldı (Supabase autoconfirm açık). Eski mesaj
    // kullanıcıyı ASLA gelmeyecek bir doğrulama e-postasını beklemeye itiyordu.
    mockAuth.signInWithPassword.mockResolvedValueOnce({ error: { message: "Invalid login credentials" } } as never);
    const r = await signInUser("x@y.com", "Sifre1234");
    expect(r.ok).toBe(false);
    expect(r.error).not.toMatch(/doğrula|gelen kutu|yeniden gönder/i);
    expect(r.error).toMatch(/boşluk/i);
  });
});

describe("e-posta doğrulama akışı KALDIRILDI (2026-08-06 sahip kararı)", () => {
  it("kayıt isteğinde emailRedirectTo GÖNDERİLMEZ (gönderilecek e-posta yok)", async () => {
    mockAuth.signUp.mockResolvedValueOnce({ data: { session: { access_token: "t" } }, error: null } as never);
    await signUpUser("yeni@klinik.com", "Sifre1234", { first_name: "A" });
    const opts = mockAuth.signUp.mock.calls[0][0].options;
    expect(opts.emailRedirectTo).toBeUndefined();
    expect(opts.data).toEqual({ first_name: "A" });
  });

  it("kayıt başarılıysa ok:true — kullanıcı e-posta beklemeye YÖNLENDİRİLMEZ", async () => {
    mockAuth.signUp.mockResolvedValueOnce({ data: { session: { access_token: "t" } }, error: null } as never);
    const r = await signUpUser("yeni@klinik.com", "Sifre1234");
    expect(r).toEqual({ ok: true });
  });

  it("KRİTİK: oturum GELMEZSE (panoda Confirm-email tekrar açılmış) sessiz kalmaz, açıkça söyler", async () => {
    mockAuth.signUp.mockResolvedValueOnce({ data: { session: null }, error: null } as never);
    const r = await signUpUser("yeni@klinik.com", "Sifre1234");
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/e-posta onayı açık/i);
  });

  it("resendVerification ve AUTH_VERIFY_URL artık DIŞA AKTARILMIYOR", () => {
    // (dinamik import jest'in CJS ortamında desteklenmiyor → require ile aynı kontrol)
    const mod = jest.requireActual("@/services/supabaseAuth") as Record<string, unknown>;
    expect(mod.resendVerification).toBeUndefined();
    expect(mod.AUTH_VERIFY_URL).toBeUndefined();
    expect(typeof mod.signInUser).toBe("function");   // modül gerçekten yüklendi (yanlış-pozitif değil)
  });
});
