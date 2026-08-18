// Author: mertaygn, cglrgrkn
/**
 * MOBİL "ÇIKIŞ" TÜM CİHAZLARI DÜŞÜRÜYORDU (denetim 2026-08-18).
 *
 * `supabaseAuth.auth.signOut()` supabase-js v2'de VARSAYILAN olarak `scope: 'global'` çalışır
 * (`POST /auth/v1/logout?scope=global`) ve kullanıcının TÜM refresh token'larını sunucuda iptal
 * eder. Üç istemci de AYNI Supabase projesini kullanıyor (web `pemf-vet-web/src/lib/supabase.ts`,
 * mobil buradaki `supabaseAuth.ts`, masaüstü `launcher/core/src/auth.rs` — hepsi
 * `wmsxonunkphjeregpvuj`). Sonuç: telefondan çıkış yapmak KLİNİKTEKİ launcher'ın oturumunu da
 * iptal ediyor; launcher bir sonraki jeton tazelemesinde `invalid_grant` alıp açılış kapısında
 * e-posta+parola istiyor. Ters yön de geçerli: launcher'dan çıkınca telefon düşüyor.
 *
 * ⚠️ Bu, `AuthContext`in kendi denetim notunun TERSİ yönde ısırıyor: orada "B kullanıcısı A'nın
 * hakkıyla istek atmasın" diye nesil sayacı var; burada A'nın KENDİ başka cihazı gereksiz yere
 * atılıyor. Çıkış YEREL olmalı — jeton zaten bu cihazın güvenli deposundan siliniyor.
 */
const mockSignOut = jest.fn(async () => ({ error: null }));

jest.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      signOut: (...a: unknown[]) => mockSignOut(...(a as [])),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
      getSession: async () => ({ data: { session: null }, error: null }),
    },
  }),
}));

import { signOutUser } from "@/services/supabaseAuth";

describe("mobil çıkış kapsamı", () => {
  beforeEach(() => mockSignOut.mockClear());

  it("KRİTİK: signOut 'local' kapsamıyla çağrılır (launcher oturumu düşmesin)", async () => {
    await signOutUser();
    expect(mockSignOut).toHaveBeenCalledWith({ scope: "local" });
  });

  it("KARŞIT-KANIT: çağrı hâlâ YAPILIYOR (kapsamı daraltmak çıkışı kaldırmak değildir)", async () => {
    await signOutUser();
    expect(mockSignOut).toHaveBeenCalledTimes(1);
  });
});
