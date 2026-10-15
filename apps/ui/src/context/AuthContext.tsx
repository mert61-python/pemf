// Author: mertaygn, cglrgrkn
/**
 * AuthContext — operatör oturumu (Supabase Auth: e-posta/şifre + doğrulama). Giriş yapılmadan
 * uygulamaya girilemez. Oturum supabase-js ile KALICI (her açılışta tekrar giriş YOK); profil seçimi
 * yine her açılış (bilinçli). `isResearch` = e-posta `.edu` → WelcomeScreen araştırma-modu kartı.
 * Giriş/çıkış/doğrulama-sonrası değişimleri `onAuthStateChange` ile otomatik yansır.
 *
 * 2026-08-06 — MASAÜSTÜ OTURUM DEVRİ: masaüstü client (Tauri) Supabase'e giriş yapıp oturumu
 * backend'e devrettiğinde uygulama açılışta onu devralır ve login ekranını ATLAR (çift giriş yok).
 * Devir yoksa/başarısızsa AKIŞ DEĞİŞMEZ — sessizce normal login gösterilir. Bkz. services/desktopSession.
 */
import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef, ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { AuthSession, isResearchEmail } from "@/services/authApi";
import { supabaseAuth, getCurrentSession, signOutUser } from "@/services/supabaseAuth";
import {
  isDesktopHost,
  hydrateFromDesktopSessionDetayli,
  clearDesktopSession,
  pushDesktopSession,
  type DesktopSession,
} from "@/services/desktopSession";
import { epostaAnahtari, parkEt, parkHesaplari, parktanCikar, type ParkHesap } from "@/services/hesapDeposu";
import {
  etkinOturum,
  hesabaGec as hesabaGecServisi,
  hesapKimliginiDusur,
  parkHesabindanCik,
  tumParkHesaplardanCik,
  type GecisSonucu,
} from "@/services/hesapGecisi";

interface AuthContextValue {
  session: AuthSession | null;
  loading: boolean;       // saklı oturum kontrol edilirken VE masaüstü devri denenirken (ilk açılış)
  isResearch: boolean;    // e-posta .edu → araştırma modu görünür
  /** TÜM hesaplardan çık (mevcut "Çıkış Yap"): etkin + bu cihazda açık tutulan diğer e-posta hesapları. */
  logout: () => Promise<void>;
  /** CH1 · Y151: bu cihazda AÇIK e-posta hesapları (etkin önce). Tek hesaplı kullanımda yalnız etkin hesap. */
  hesaplar?: string[];
  /** CH1: "Hesap ekle" — giriş ekranı açık; etkin hesap park edildi ve vazgeçilirse geri döner. */
  hesapEkleniyor?: boolean;
  hesapEkle?: () => Promise<void>;
  hesapEklemeVazgec?: () => Promise<void>;
  /** CH1: açık başka bir hesaba geç (seans koruması ÇAĞIRANDA — `hesapGecisiEngeli`). */
  hesabaGec?: (eposta: string) => Promise<GecisSonucu>;
  /** CH1: TEK hesaptan çık — etkin değilse yalnız o; etkinse açık başka hesaba geçilir (yoksa tümden çıkış). */
  hesaptanCik?: (eposta: string) => Promise<GecisSonucu>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/**
 * Açılış splash'inin TAVANI (ms) — `hydrating` bu süreden uzun sürerse zorla kapatılır.
 *
 * NEDEN GEREKLİ (denetim 2026-08-06): `hydrating` yalnız aşağıdaki akışın SONUNDA sıfırlanıyordu,
 * o akışın son adımı ise `getCurrentSession()`. supabase-js tüm oturum işlemlerini TEK bir iç
 * kilitle sıraya alır ve devrin `setSession`'ı o kilidi tutarken Supabase'e ağ çağrısı yapar —
 * supabase-js'te bu çağrının ZAMAN AŞIMI YOKTUR. Yarı-açık tünel / captive portal / DNS asılması
 * durumunda `setSession` dakikalarca asılı kalır, `getCurrentSession()` kilidin arkasında bekler
 * ve `hydrating` HİÇ kapanmaz. `DESKTOP_SESSION_BUDGET_MS` yalnız BEKLENEN sonucu sınırlar, arka
 * planda süren çağrıyı değil → tek başına yetmiyordu.
 * Sonuç eskiden: masaüstünde açılış donmuş bir spinner'da kalıyor, operatör uygulamaya —
 * dolayısıyla içindeki ACİL DURDUR'a — hiç giremiyordu. Tavan dolunca splash'ten ÇIKILIR
 * (eski davranış: login ya da saklı oturumla uygulama). Geç gelen devir KAYBOLMAZ: `setSession`
 * tamamlanınca `onAuthStateChange` kullanıcıyı zaten içeri alır.
 *
 * Sabit BİLEREK burada tanımlı (desktopSession'dan import EDİLMEZ): o modül testlerde tümüyle
 * mock'lanıyor, oradan gelen bir süre `undefined` olur ve setTimeout'u sessizce 0 ms'ye düşürürdü.
 */
const HYDRATE_SPLASH_CEILING_MS = 6000;

/** JWT gövdesindeki e-posta (imza DOĞRULANMAZ — yalnız görüntü; jeton launcher'ın doğruladığı devirden gelir). */
function jwtEposta(jeton: string): string {
  try {
    const govde = jeton.split(".")[1] ?? "";
    const b64 = govde.replace(/-/g, "+").replace(/_/g, "/");
    const ham = typeof atob === "function" ? atob(b64) : "";
    const e = (JSON.parse(ham) as { email?: unknown }).email;
    return typeof e === "string" ? e : "";
  } catch {
    return "";
  }
}

/** D1.87 · A-70: Supabase'e ulaşılamadığında launcher devrinden ÇEVRİMDIŞI oturum (yalnız auth; profil/userMode diske yazılmaz). */
function cevrimdisiOturum(d: DesktopSession): AuthSession | null {
  const email = d.email || jwtEposta(d.access_token);
  if (!email) return null;
  return { email, token: d.access_token, profile: undefined, cevrimdisi: true };
}

function toAuthSession(s: Session | null): AuthSession | null {
  if (!s || !s.user?.email) return null;
  // Kayıtta girilen veteriner/klinik profili user_metadata'da → session'a taşı (uygulama her yerden okur).
  const m = (s.user.user_metadata || {}) as Record<string, string>;
  return {
    email: s.user.email,
    token: s.access_token || "",
    profile: {
      first_name: m.first_name || "",
      last_name: m.last_name || "",
      full_name: m.full_name || "",
      title: m.title || "",
      phone: m.phone || "",
      clinic_name: m.clinic_name || "",
      clinic_phone: m.clinic_phone || "",
      city: m.city || "",
      district: m.district || "",
      address: m.address || "",
    },
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(true);
  // MASAÜSTÜ OTURUM DEVRİ (2026-08-06): client Supabase ile giriş yapıp oturumu backend'e devreder;
  // burada devralınır ve login ekranı ATLANIR (çift giriş yok). Devir denenirken AuthGate SPLASH'te
  // kalmalı: `loading` tek başına yetmez, çünkü onAuthStateChange abone olur olmaz INITIAL_SESSION
  // yayınlar → loading false olur ve devir bitmeden AuthScreen bir an "yanıp" çift-giriş hissi verir.
  const [hydrating, setHydrating] = useState(() => isDesktopHost());
  // D1.87 · A-70: Supabase'e ulaşılamadığı için devirden açılan çevrimdışı oturum. Gerçek oturum gelince yerini alır;
  // `INITIAL_SESSION(null)` gibi "oturum yok" olayları onu DÜŞÜRMEZ — yalnız açık çıkış (SIGNED_OUT / logout).
  const cevrimdisiRef = useRef<AuthSession | null>(null);
  // ── CH1 · Y151 ÇOKLU HESAP ─────────────────────────────────────────────────────────────────
  // Park edilmiş (etkin OLMAYAN) hesapların e-postaları; belirteçler `services/hesapDeposu`ta (supabase-js ile AYNI güvenli depo).
  const [parkListesi, setParkListesi] = useState<string[]>([]);
  const [hesapEkleniyor, setHesapEkleniyor] = useState(false);
  const hesapEkleniyorRef = useRef(false);
  // "Hesap ekle" başlarken etkin olan oturum (park edildi): yeni GİRİŞ (farklı belirteç) gelince ekleme biter; vazgeçilirse parktan çıkar.
  const eklemeOncesiRef = useRef<ParkHesap | null>(null);
  // Son görülen etkin e-posta — DEĞİŞİNCE (geçiş / ekleme / çıkış-giriş) kimlik başlıkları HEMEN düşer ve hesap kuşağı artar.
  const sonEpostaRef = useRef<string>("");
  const hesaplariYenile = useCallback(async () => {
    setParkListesi((await parkHesaplari()).map((h) => h.email));
  }, []);

  useEffect(() => {
    void hesaplariYenile();
  }, [hesaplariYenile]);

  useEffect(() => {
    let alive = true;
    // Splash TAVANI — bkz. HYDRATE_SPLASH_CEILING_MS: devir/oturum-okuma asılı kalsa da açılış
    // sonsuza dek spinner'da kilitlenmesin (ACİL DURDUR uygulamanın İÇİNDE yaşıyor).
    // ⚠️ D1.87: tavan MOBİLDE de splash'i bitirir (`loading`). Eskiden yalnız masaüstü `hydrating`ini kapatıyordu; mobilde
    // süresi dolmuş saklı oturumun yenilemesi ağ reddinde asılı kalınca splash ~51 sn sürüyordu (ölçüldü).
    const tavan = setTimeout(() => {
      if (!alive) return;
      setHydrating(false);
      setLoading(false);
    }, HYDRATE_SPLASH_CEILING_MS);
    // ÖNCE abone ol: hidrasyonun tetikleyeceği setSession olayı KAÇMASIN.
    const { data: sub } = supabaseAuth.auth.onAuthStateChange((_event, s) => {
      const yeni = toAuthSession(s);
      if (!yeni && cevrimdisiRef.current && _event !== "SIGNED_OUT") {
        setLoading(false);
        return; // D1.87: çevrimdışı açılış "oturum yok" olayıyla düşmez
      }
      if (yeni || _event === "SIGNED_OUT") cevrimdisiRef.current = null;
      // CH1 · Y151: etkin e-posta DEĞİŞTİ → önceki hesabın Bearer'ı / abonelik başlıkları bu andan sonraki isteklere GİTMEZ ve uçuştaki
      // yanıtları atılır (`apiClient.hesapKusagi`). Uygulama ağacı hesap anahtarıyla yeniden kurulur (`PemfApp.AuthGate`).
      const yeniEposta = epostaAnahtari(yeni?.email);
      if (yeniEposta && sonEpostaRef.current && yeniEposta !== sonEpostaRef.current) hesapKimliginiDusur();
      if (yeniEposta) sonEpostaRef.current = yeniEposta;
      // CH1: "Hesap ekle" kipinde YENİ bir giriş (ekleme öncesinden farklı belirteç) geldi → ekleme biter; giriş yapılan hesap artık
      // etkindir, park listesinde kalmaz (önceki etkin hesap parkta kalır).
      if (hesapEkleniyorRef.current && yeni && s?.access_token && s.access_token !== eklemeOncesiRef.current?.access_token) {
        hesapEkleniyorRef.current = false;
        eklemeOncesiRef.current = null;
        setHesapEkleniyor(false);
        void parktanCikar(yeni.email).then(hesaplariYenile);
      }
      setSession(yeni);
      setLoading(false);
      // 🔴 SAHA ARIZASI (2026-08-24) — "Beni hatırla" bozuluyordu.
      // supabase-js jetonu arka planda yeniler (`autoRefreshToken: true`) ve Supabase yenilemede
      // refresh token'ı DÖNDÜRÜR. Döndürülen jeton YALNIZ tarayıcı deposunda kalıyordu; masaüstü
      // client'ın DPAPI ile diske yazdığı kopya bayatlıyor, bir sonraki açılışta o bayat jetonla
      // yenileme deneniyor, GoTrue açıkça reddediyor ve client kayıtlı oturumu SİLİYORDU →
      // kullanıcıdan yeniden e-posta+parola isteniyordu.
      // Döngüyü burada kapatıyoruz: her döndürmede yeni oturumu client'a geri yaz.
      // ⚠️ Yalnız masaüstünde ve SESSİZ (mobilde `pushDesktopSession` zaten erken döner).
      if (_event === "TOKEN_REFRESHED" && s?.access_token && s?.refresh_token) {
        void pushDesktopSession({
          access_token: s.access_token,
          refresh_token: s.refresh_token,
          email: s.user?.email ?? "",
          expires_at: typeof s.expires_at === "number" ? s.expires_at : 0,
        });
      }
    });
    (async () => {
      // Masaüstü devri (yalnız client'ın açtığı loopback sayfada). Uç yoksa / boş dönerse /
      // hata verirse NORMALDİR → sessizce mevcut login akışına düşülür (kullanıcı hata görmez).
      if (isDesktopHost()) {
        try {
          const devir = await hydrateFromDesktopSessionDetayli();
          if (devir.durum === "cevrimdisi") cevrimdisiRef.current = cevrimdisiOturum(devir.oturum);
        } catch {
          /* sessiz — normal login */
        }
      }
      if (cevrimdisiRef.current && alive) {
        // D1.87 · A-70: ağ yokken `getCurrentSession` de asılabilir — çevrimdışı oturum onu BEKLEMEDEN açılır.
        setSession(cevrimdisiRef.current);
        setLoading(false);
        setHydrating(false);
      }
      // Sonra saklı/devralınmış oturumu oku (ilk açılış).
      const s = await getCurrentSession();
      if (!alive) return;
      const gercek = toAuthSession(s);
      if (gercek) cevrimdisiRef.current = null;
      setSession(gercek ?? cevrimdisiRef.current);
      setLoading(false);
      setHydrating(false);
    })();
    return () => {
      alive = false;
      clearTimeout(tavan);
      sub?.subscription?.unsubscribe();
    };
  }, []);

  const logout = useCallback(async () => {
    cevrimdisiRef.current = null; // D1.87: çevrimdışı açılış da açık çıkışla kapanır
    // CH1 · Y151: "Çıkış Yap" = TÜM hesaplardan çık — bu cihazda açık tutulan diğer hesapların belirteçleri de silinir (sunucuda
    // iptal en-iyi-çaba, beklenmez). Ekleme kipi de kapanır.
    hesapEkleniyorRef.current = false;
    eklemeOncesiRef.current = null;
    setHesapEkleniyor(false);
    await tumParkHesaplardanCik();
    setParkListesi([]);
    // ÖNCE backend'in bellekteki devir oturumunu sil: aksi halde sayfa yenilenince uygulama
    // kendini tekrar hydrate eder ve masaüstünde çıkış İŞLEMEZ. En-iyi-çaba (hata yutulur).
    await clearDesktopSession();
    await signOutUser(); // → onAuthStateChange oturumu null'lar
    setSession(null);
  }, []);

  // ── CH1 · Y151 eylemleri ───────────────────────────────────────────────────────────────────
  const hesapEkle = useCallback(async () => {
    const etkin = await etkinOturum();
    if (etkin) await parkEt(etkin); // giriş ekranında vazgeçilirse ya da başka hesap girilirse bu hesap KAYBOLMAZ
    eklemeOncesiRef.current = etkin;
    hesapEkleniyorRef.current = true;
    setHesapEkleniyor(true);
    await hesaplariYenile();
  }, [hesaplariYenile]);

  const hesapEklemeVazgec = useCallback(async () => {
    const once = eklemeOncesiRef.current;
    hesapEkleniyorRef.current = false;
    eklemeOncesiRef.current = null;
    setHesapEkleniyor(false);
    if (once) await parktanCikar(once.email); // hâlâ etkin — park kopyası kalmasın
    await hesaplariYenile();
  }, [hesaplariYenile]);

  const hesabaGec = useCallback(async (eposta: string): Promise<GecisSonucu> => {
    const r = await hesabaGecServisi(eposta);
    await hesaplariYenile();
    return r;
  }, [hesaplariYenile]);

  const hesaptanCik = useCallback(async (eposta: string): Promise<GecisSonucu> => {
    const etkinEposta = epostaAnahtari((await etkinOturum())?.email ?? session?.email);
    if (epostaAnahtari(eposta) !== etkinEposta) {
      await parkHesabindanCik(eposta);
      await hesaplariYenile();
      return { ok: true };
    }
    const sonraki = (await parkHesaplari()).find((h) => epostaAnahtari(h.email) !== etkinEposta);
    if (!sonraki) {
      await logout(); // açık başka hesap yok → bugünkü çıkış
      return { ok: true };
    }
    const r = await hesabaGecServisi(sonraki.email); // etkin hesap park edilir…
    if (!r.ok) {
      await hesaplariYenile();
      return r;
    }
    await clearDesktopSession(); // masaüstü: çıkılan hesabın devri sayfa yenilemede geri gelmesin
    await parkHesabindanCik(eposta); // …sonra cihazdan silinir (+ sunucuda iptal, en-iyi-çaba)
    await hesaplariYenile();
    return { ok: true };
  }, [session, logout, hesaplariYenile]);

  const isResearch = !!session && isResearchEmail(session.email);

  // Devir sürerken de "yükleniyor" say → AuthGate splash'te kalır, login ekranı yanıp sönmez.
  const busy = loading || hydrating;

  const hesaplar = useMemo(() => {
    const etkin = session?.email ? [session.email] : [];
    return [...etkin, ...parkListesi.filter((e) => epostaAnahtari(e) !== epostaAnahtari(session?.email))];
  }, [session, parkListesi]);

  const value = useMemo(
    () => ({
      session, loading: busy, isResearch, logout,
      hesaplar, hesapEkleniyor, hesapEkle, hesapEklemeVazgec, hesabaGec, hesaptanCik,
    }),
    [session, busy, isResearch, logout, hesaplar, hesapEkleniyor, hesapEkle, hesapEklemeVazgec, hesabaGec, hesaptanCik],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
