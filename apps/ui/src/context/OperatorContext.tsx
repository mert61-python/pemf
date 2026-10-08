// Author: mertaygn, cglrgrkn
/**
 * AKTİF OPERATÖR — tek makine, çoklu veteriner (2026-08-08 sahip isteği).
 *
 * SORUN: bir kliniği 3-4 veteriner paylaşıyor ama uygulamaya TEK e-postayla giriliyordu →
 * her kayda AYNI `operator_email` yazılıyordu ve "Benim Hastalarım / Tüm Klinik" ayrımı
 * ANLAMSIZ kalıyordu. Veri modeli çoklu operatörü zaten destekliyordu (patients,
 * treatment_sessions, ai_analyses hepsinde `operator_email` var); eksik olan kimlik katmanıydı.
 *
 * TASARIM: kimlik bir kez Supabase ile doğrulanır (client girişi), her veteriner cihaza 6 haneli
 * bir PIN ile kaydolur; sonraki geçişler PIN ile ve ÇEVRİMDIŞI yapılır. Supabase girişi internet
 * ister — internetsiz klinikte operatör değiştirilemezdi.
 *
 * ⚠️ GERİYE UYUM: hiç operatör kayıtlı değilse `operatorEmail` oturum e-postasına düşer.
 * Tek veterinerli klinikler HİÇBİR ŞEY yapmadan bugünkü gibi çalışmaya devam eder.
 *
 * ⚠️ HASTA GÜVENLİĞİ: hareketsizlik kilidi SEANS SÜRERKEN ERTELENİR. Hastanın üzerinde
 * bobinler çalışırken ekranı kilitlemek, operatörün ACİL DURDUR'a ulaşmasını geciktirir —
 * güncelleme akışındaki "seans sürerken dokunma" ilkesinin aynısı.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { StyleSheet, View } from "react-native";

import { apiGet, apiPost, setOperatorToken } from "@/services/apiClient";
import { useAuth } from "@/context/AuthContext";

export interface Operator {
  email: string;
  display_name: string;
  locked?: boolean;
  last_active?: string;
}

export interface SwitchResult {
  ok: boolean;
  /** "bad_pin" | "locked" | "net" — UI mesajını buna göre seçer. */
  error?: "bad_pin" | "locked" | "net";
}

/** Kayıt sonucu. `need_old_pin` → e-posta zaten kayıtlı, PIN değişimi için mevcut PIN şart. */
export interface EnrollResult {
  ok: boolean;
  error?: "need_old_pin" | "locked" | "invalid" | "net";
}

interface OperatorContextValue {
  /** Cihazda kayıtlı operatörler (hızlı geçiş listesi). */
  operators: Operator[];
  /** Aktif operatör; null → kimse seçilmemiş (oturum e-postasına düşülür). */
  active: Operator | null;
  /** ⭐ TEK KAYNAK — kayıtlara yazılacak e-posta. Her yerde BU kullanılmalı. */
  operatorEmail: string;
  /** Cihazda en az bir operatör kayıtlı mı (çoklu-kullanıcı kipi açık mı). */
  multiUser: boolean;
  refresh: () => Promise<void>;
  /**
   * Bu cihaza kaydol / PIN değiştir. E-posta ZATEN kayıtlıysa backend `eskiPin` ister
   * (2026-08-09): aksi hâlde bu ucu çağırabilen herkes başka bir hekimin PIN'ini ezip
   * onun kimliğiyle kayıt yazabilirdi.
   */
  enroll: (displayName: string, pin: string, eskiPin?: string) => Promise<EnrollResult>;
  switchTo: (email: string, pin: string) => Promise<SwitchResult>;
  /** Aktif operatörü düşür (elle "kilitle" ya da hareketsizlik). */
  lock: () => void;
  /** Kullanıcı etkileşimi bildir — hareketsizlik sayacını sıfırlar. */
  touch: () => void;
}

const Ctx = createContext<OperatorContextValue | null>(null);

/** Hareketsizlik eşiği. Klinik akışında hasta arası boşluklar uzun olabilir → 10 dk. */
export const AUTO_LOCK_MS = 10 * 60 * 1000;

export function OperatorProvider({
  children,
  sessionActive = false,
  autoLockMs = AUTO_LOCK_MS,
}: {
  children: ReactNode;
  /** Cihazda seans sürüyor mu — SÜRERKEN KİLİTLENMEZ (hasta güvenliği). */
  sessionActive?: boolean;
  autoLockMs?: number;
}) {
  const { session } = useAuth();
  const [operators, setOperators] = useState<Operator[]>([]);
  const [active, setActive] = useState<Operator | null>(null);
  const sonEtkilesim = useRef<number>(Date.now());

  const refresh = useCallback(async () => {
    const r = await apiGet<{ ok?: boolean; data?: Operator[] } | null>("/operators", null, { silent: true });
    setOperators(Array.isArray(r?.data) ? r!.data! : []);
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  // ⚠️ B2-4.1 (2-B bağımsız incelemesi): sağlayıcı SÖKÜLÜNCE (çıkış ya da Supabase oturumu düşünce `PemfApp.AuthGate`
  // uygulama ağacını söker) modül düzeyi operatör jetonu da DÜŞER. Eskiden yalnız `lock()` siliyordu: yeniden girişte yeni
  // sağlayıcı "aktif operatör yok" ile başlarken istekler önceki hekimin jetonunu taşıyor, kimliksiz ekranda başlatılan
  // seans / AI kaydı ona atfediliyordu (D2.32'nin çıkış yolu ikizi — ölçüldü). Kapı: __tests__/OperatorContext.B241.cikisJeton.web.test.tsx.
  useEffect(() => () => { setOperatorToken(null); }, []);

  const enroll = useCallback(async (displayName: string, pin: string,
                                    eskiPin = ""): Promise<EnrollResult> => {
    const eposta = (session?.email || "").toLowerCase();
    if (!eposta) return { ok: false, error: "invalid" };
    // ⚠️ `silent`: "bu e-posta zaten kayıtlı, mevcut PIN'i girin" NORMAL bir akıştır (kullanıcı
    // PIN'ini değiştiriyor) — global hata balonu çıkarmaz, mesajı kayıt ekranı kendi gösterir.
    let durum = 0;
    const r = await apiPost<{ ok?: boolean; operator_token?: string } | null>(
      "/operators/enroll", { email: eposta, display_name: displayName, pin, eski_pin: eskiPin },
      null, { silent: true, onHttpError: (s) => { durum = s; } });
    if (!r?.ok) {
      if (durum === 401) return { ok: false, error: "need_old_pin" };
      if (durum === 423) return { ok: false, error: "locked" };
      if (durum === 400) return { ok: false, error: "invalid" };
      return { ok: false, error: "net" };
    }
    // ⚠️ Kaydolan kişi ANINDA aktif olur → jetonu da burada kurulmalı. Aksi hâlde artık
    // "kayıtlı operatör" olduğu için jetonsuz yazmaları backend'de reddedilir ve İLK
    // operatörün tüm kayıtları sessizce SAHİPSİZ yazılırdı.
    setOperatorToken(r.operator_token || null);
    await refresh();
    // Kaydolan kişi zaten giriş yapmış kişidir → doğrudan aktif olur (PIN sormaya gerek yok).
    setActive({ email: eposta, display_name: displayName });
    sonEtkilesim.current = Date.now();
    return { ok: true };
  }, [session, refresh]);

  const switchTo = useCallback(async (email: string, pin: string): Promise<SwitchResult> => {
    // ⚠️ `silent: true`: hatalı PIN NORMAL bir kullanıcı durumudur, global hata balonu ÇIKARMAZ —
    // mesajı PIN ekranı kendi içinde gösterir. Durum kodu `onHttpError` ile alınır: 423 (kilitli)
    // ile 401 (PIN hatalı) bambaşka mesajlardır — kilitliyken "PIN hatalı" demek kullanıcıyı
    // boşuna denemeye devam ettirir.
    let durum = 0;
    const r = await apiPost<{ ok?: boolean; operator_token?: string } | null>(
      "/operators/verify", { email, pin }, null,
      { silent: true, onHttpError: (s) => { durum = s; } });
    if (durum === 423) return { ok: false, error: "locked" };
    if (durum === 401) return { ok: false, error: "bad_pin" };
    if (!r || r.ok !== true) return { ok: false, error: "net" };
    // ⚠️ 2026-08-09 (Tier 1): jetonu KUR. Backend yazma yollarında `operator_email`i bundan
    // türetir; jeton gönderilmezse kayıtlı bir hekimin adına yazma REDDEDİLİR (kayıt sahipsiz
    // kalır). Yani bu satır olmadan çoklu-operatör atfı sessizce çalışmaz.
    setOperatorToken(r.operator_token || null);
    const kayit = operators.find((o) => o.email === email);
    setActive({ email, display_name: kayit?.display_name || email });
    sonEtkilesim.current = Date.now();
    void refresh();
    return { ok: true };
  }, [operators, refresh]);

  // Kilitlemede jeton da DÜŞER: aksi hâlde kimlik ekranda düşmüş görünürken backend hâlâ o
  // hekimin adına kayıt yazmaya devam ederdi.
  // ⚠️ D2.E14 (İG-6.63): jeton SUNUCUDA da iptal edilir — aynı jetonu tutan diğer kopyalar (ikinci sekme, eski mobil)
  // kilitlenen hekim adına yazmayı sürdürüyordu. İstek jeton düşürülmeden ÖNCE kurulur (`apiPost` başlığı eşzamanlı
  // okur); sonucu BEKLENMEZ — sunucu hatası kilidi ENGELLEMEZ. Kapı: __tests__/OperatorContext.E14.sunucuKilit.web.test.tsx.
  const lock = useCallback(() => {
    void apiPost("/operators/lock", {}, null, { silent: true });
    setOperatorToken(null);
    setActive(null);
  }, []);
  const touch = useCallback(() => { sonEtkilesim.current = Date.now(); }, []);

  // ── ETKİLEŞİM → SAYAÇ (D2.E13 · İG-6.18) ─────────────────────────────────────────────────
  // `touch()` üründe HİÇ çağrılmıyordu → kimlik PIN'den tam 10 dk sonra, çalışan hekimde bile düşüyordu (ölçüldü: gerçek
  // tarayıcıda 46 tıklama/tuşa rağmen 600. sn). Web/masaüstü: pencerenin YAKALAMA evresinde gerçek kullanıcı etkileşimi
  // (dokunma/tıklama, tuş, tekerlek). Yerel: kök görünümün yanıtlayıcı YAKALAMA sorgusu — `false` döner, dokunuşu ÇALMAZ.
  // ⚠️ `mousemove` SAYILMAZ: masada kayan fare kimliği sonsuza dek açık tutardı. 10 dk eşiği ve "seans sürerken
  // kilitlenmez" DEĞİŞMEZ. Kapı: __tests__/OperatorContext.E13.etkilesim.web.test.tsx + OperatorContext.test.tsx (yerel).
  useEffect(() => {
    const w = typeof window !== "undefined" ? window : undefined;
    if (!w || typeof w.addEventListener !== "function") return;
    const olaylar = ["pointerdown", "keydown", "wheel", "touchstart"];
    for (const o of olaylar) w.addEventListener(o, touch, { capture: true, passive: true });
    return () => { for (const o of olaylar) w.removeEventListener(o, touch, { capture: true }); };
  }, [touch]);
  const dokunusYakala = useCallback(() => { touch(); return false; }, [touch]);

  // ── HAREKETSİZLİK KİLİDİ ────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!active) return;                       // kilitlenecek bir kimlik yok
    const t = setInterval(() => {
      // ⚠️ SEANS SÜRERKEN KİLİTLEME: bobinler hastanın üzerinde çalışırken kimlik düşürmek,
      // operatörü kritik bir anda PIN ekranına sokar. Seans bitince sayaç yeniden işler.
      if (sessionActive) { sonEtkilesim.current = Date.now(); return; }
      // ⚠️ D2.32 (B-6.8): hareketsizlik kilidi elle "Kilitle" İLE AYNI yoldan — jeton da DÜŞER. Eskiden yalnız
      // `setActive(null)` vardı: ekranda "Operatör seçin" yazarken istekler önceki hekimin jetonunu taşıyor, seans/AI
      // kaydı ve silmeler ona atfediliyordu (ölçüldü). Kapı: __tests__/OperatorContext.D232.kilitJeton.web.test.tsx.
      if (Date.now() - sonEtkilesim.current >= autoLockMs) lock();
    }, 30_000);
    return () => clearInterval(t);
  }, [active, sessionActive, autoLockMs, lock]);

  const value = useMemo<OperatorContextValue>(() => ({
    operators,
    active,
    // GERİYE UYUM: operatör kayıtlı değilse oturum e-postası (tek veterinerli klinik).
    operatorEmail: active?.email || (operators.length === 0 ? (session?.email || "") : ""),
    multiUser: operators.length > 0,
    refresh, enroll, switchTo, lock, touch,
  }), [operators, active, session, refresh, enroll, switchTo, lock, touch]);

  return (
    <Ctx.Provider value={value}>
      <View style={styles.kok} testID="operator-etkilesim-koku" onStartShouldSetResponderCapture={dokunusYakala}>
        {children}
      </View>
    </Ctx.Provider>
  );
}

const styles = StyleSheet.create({ kok: { flex: 1 } });

export function useOperator(): OperatorContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useOperator, OperatorProvider içinde kullanılmalı");
  return v;
}

/**
 * Sağlayıcı YOKSA `null` döner — fırlatmaz.
 *
 * NEDEN AYRI: kayıt YAZAN tüketiciler (ControlScreen, AiHub, AiPro) sağlayıcının içinde OLMAK
 * ZORUNDA; orada sessizce `null`'a düşmek, kaydın yanlış kimlikle yazılması demek olurdu — bu
 * yüzden `useOperator` bilerek FIRLATIR. Buna karşılık üst bardaki çip yalnız bir gösterge:
 * sağlayıcısız bir bağlamda (ör. AppShell'i tek başına render eden testler) uygulamayı
 * çökertmemeli, sadece görünmemeli.
 */
export function useOperatorOptional(): OperatorContextValue | null {
  return useContext(Ctx);
}
