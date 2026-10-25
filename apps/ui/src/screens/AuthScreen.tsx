// Author: mertaygn, cglrgrkn
/**
 * AuthScreen — operatör giriş/kayıt ekranı (web + mobil, tek kod).
 * Koyu-premium tasarım: aurora-glow arka plan, logo, sekmeli giriş/kayıt, canlı şifre-kural göstergesi.
 * .edu e-postası → sonraki profil-seçimde araştırma modu açılır (bilgilendirme ipucu gösterilir).
 */
import { useRef, useState } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, Image,
  ActivityIndicator, ScrollView, KeyboardAvoidingView, useWindowDimensions,
} from "react-native";
import Svg, { Defs, RadialGradient, Stop, Rect } from "react-native-svg";
import { KAV_BEHAVIOR_PENCERE } from "@/hooks/useKeyboard";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Mail, Lock, Eye, EyeOff, Check, X, ArrowRight, GraduationCap, User, Phone, Building2, MapPin, Home, Stethoscope } from "lucide-react-native";
import type { ComponentType } from "react";
import { colors, spacing, radius, typography, rf, rs, touch } from "@/theme/tokens";
import { passwordChecks, isPasswordValid, isEmailValid, isResearchEmail } from "@/services/authApi";
import { signUpUser, signInUser, sendPasswordReset } from "@/services/supabaseAuth";
import { EstopMandalBandi } from "@/components/ui/EstopMandalBandi";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";
import { DilSecici } from "@/components/domain/DilSecici";
import { useTranslation } from "react-i18next";

const LOGO = require("../../assets/icon.png");

type Mode = "login" | "register" | "reset";

/**
 * CH1 · Y151 (çoklu hesap): `hesapEkleme` → "Hesap ekle" kipi. Etkin hesap bu cihazda AÇIK KALIR (park edildi); giriş yapılan yeni hesap
 * etkin olur, ikisi arasında üst menüdeki "E-posta hesapları"ndan geçilir. `onVazgec` → giriş yapmadan önceki hesaba dön.
 */
export function AuthScreen({ hesapEkleme = false, onVazgec }: { hesapEkleme?: boolean; onVazgec?: () => void } = {}) {
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const { width: winW, height: winH } = useWindowDimensions();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  // Kayıt profili (yalnız Kayıt Ol modunda) — Supabase user_metadata'ya yazılır.
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [title, setTitle] = useState("");         // ünvan (örn. Vet. Hekim)
  const [phone, setPhone] = useState("");         // kişisel cep
  const [clinicName, setClinicName] = useState("");
  const [clinicPhone, setClinicPhone] = useState(""); // klinik acil telefon (AiHub arama)
  const [city, setCity] = useState("");
  const [district, setDistrict] = useState("");
  const [address, setAddress] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  // Klavye "Git/Bitti" tuşu devre-dışı butonu ATLAYIP submit'i çağırabildiği için senkron kilit.
  const submittingRef = useRef(false);
  const [error, setError] = useState("");
  const [suggestRegister, setSuggestRegister] = useState(false); // (Supabase jenerik hata → nadir)
  const [notice, setNotice] = useState("");                      // olumlu mesaj (yeşil)
  const pwRef = useRef<TextInput>(null);       // klavye "İleri" → şifreye odak
  const confirmRef = useRef<TextInput>(null);  // klavye "İleri" → şifre-tekrara odak
  // Kayıt profil alanları klavye "İleri" odak zinciri (ad→soyad→…→e-posta; klinik→şehir→…→gönder).
  const emailRef = useRef<TextInput>(null);
  const lastNameRef = useRef<TextInput>(null);
  const titleRef = useRef<TextInput>(null);
  const phoneRef = useRef<TextInput>(null);
  const clinicNameRef = useRef<TextInput>(null);
  const cityRef = useRef<TextInput>(null);
  const districtRef = useRef<TextInput>(null);
  const addressRef = useRef<TextInput>(null);
  const clinicPhoneRef = useRef<TextInput>(null);

  const isRegister = mode === "register";
  const isReset = mode === "reset";
  const showRules = isRegister;                // yeni-şifre kuralları yalnız KAYIT'ta (reset = e-posta linki)
  const checks = passwordChecks(password);
  const emailOk = isEmailValid(email);
  const pwOk = isPasswordValid(password);
  const confirmOk = !isRegister || (confirm.length > 0 && confirm === password);
  // .edu (araştırma) e-postasında kliniğe gerek yok → klinik alanları opsiyonel; yalnız ad+soyad zorunlu.
  const isResearchReg = isRegister && isResearchEmail(email);
  // Kayıtta zorunlu: ad, soyad (+ klinik değilse klinik adı/şehir/ilçe). (ünvan/telefon/adres opsiyonel)
  const profileOk = !isRegister || !!(
    firstName.trim() && lastName.trim() &&
    (isResearchReg || (clinicName.trim() && city.trim() && district.trim()))
  );
  const canSubmit = emailOk
    && (isReset ? true : isRegister ? pwOk && confirmOk && profileOk : password.length > 0)
    && !loading;

  const switchMode = (m: Mode) => {
    setMode(m);
    setError("");
    setConfirm("");
    setSuggestRegister(false);
    // Mod değişince kayıt profil alanlarını temizle (giriş↔kayıt geçişinde eski değerler kalmasın).
    setFirstName(""); setLastName(""); setTitle(""); setPhone("");
    setClinicName(""); setClinicPhone(""); setCity(""); setDistrict(""); setAddress("");
    if (m !== "login") setNotice(""); // sıfırlama/doğrulama bilgisi login'e taşınır, diğerlerinde temizlenir
  };

  const submit = async () => {
    // YENİDEN-GİRİŞ KİLİDİ: buton `loading` iken devre dışı, AMA klavyedeki "Git/Bitti" tuşu
    // (`onSubmitEditing`) submit'i DOĞRUDAN çağırdığından butonu atlıyordu → arka arkaya iki
    // kayıt/giriş isteği (Supabase rate-limit hatası, çift hesap denemesi). Ref ile kapıla:
    // state güncellemesi asenkron olduğundan `loading` tek başına yeterli değil.
    if (submittingRef.current) return;
    submittingRef.current = true;
    try {
      await doSubmit();
    } finally {
      submittingRef.current = false;
    }
  };

  const doSubmit = async () => {
    setError(""); setNotice("");
    if (!emailOk) { setError(t("giris.hata.gecersizEposta")); return; }
    if (isRegister && !pwOk) { setError(t("giris.hata.sifreKurallari")); return; }
    if (isRegister && !confirmOk) { setError(t("giris.hata.sifrelerEslesmiyor")); return; }
    if (isRegister && !profileOk) {
      setError(isResearchReg ? t("giris.hata.adSoyadEksik") : t("giris.hata.klinikBilgisiEksik"));
      return;
    }
    if (!isReset && !isRegister && password.length === 0) { setError(t("giris.hata.sifreGir")); return; }
    setLoading(true);

    // Şifre sıfırlama — e-postaya bağlantı gider; yeni şifre onay-sayfasında belirlenir (Supabase).
    if (isReset) {
      const r = await sendPasswordReset(email);
      setLoading(false);
      if (r.ok) {
        setMode("login"); setPassword(""); setConfirm("");
        setNotice(t("giris.sifirlama.gonderildi"));
      } else setError(r.error || t("giris.sifirlama.gonderilemedi"));
      return;
    }

    // Kayıt — Supabase autoconfirm AÇIK olduğundan oturum ANINDA kurulur; doğrulama e-postası YOK.
    // (2026-08-06 sahip kararı: doğrulama akışı tümüyle kaldırıldı — bkz. services/supabaseAuth.ts)
    if (isRegister) {
      const r = await signUpUser(email, password, {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        full_name: `${firstName.trim()} ${lastName.trim()}`.trim(),
        title: title.trim(),
        phone: phone.trim(),
        clinic_name: clinicName.trim(),
        clinic_phone: clinicPhone.trim(),
        city: city.trim(),
        district: district.trim(),
        address: address.trim(),
      });
      setLoading(false);
      // Kayıt başarılıysa oturum zaten açıldı → AuthContext.onAuthStateChange uygulamayı
      // OTOMATİK açar. Kullanıcıyı login formuna geri atıp e-posta beklettirmiyoruz.
      if (!r.ok) setError(r.error || t("giris.hata.kayitBasarisiz"));
      return;
    }

    // Giriş — başarıda AuthContext (onAuthStateChange) uygulamayı OTOMATİK açar.
    const r = await signInUser(email, password);
    setLoading(false);
    if (!r.ok) setError(r.error || t("giris.hata.girisBasarisiz"));
  };

  const showResearchHint = isRegister && email.length > 3 && isResearchEmail(email);

  return (
    <View style={styles.root}>
      {/* Aurora arka plan — react-native-svg radyal-gradyanlar: RN'de blur-kütüphanesi olmadığından
          sert-daire yerine GERÇEK gradyan → yumuşak premium glow (web + native uyumlu). */}
      <Svg width={winW} height={winH} style={StyleSheet.absoluteFill} pointerEvents="none">
        <Defs>
          <RadialGradient id="gV" cx="16%" cy="10%" r="62%">
            <Stop offset="0%" stopColor={colors.violet} stopOpacity={0.4} />
            <Stop offset="100%" stopColor={colors.violet} stopOpacity={0} />
          </RadialGradient>
          <RadialGradient id="gB" cx="86%" cy="92%" r="66%">
            <Stop offset="0%" stopColor={colors.primary} stopOpacity={0.34} />
            <Stop offset="100%" stopColor={colors.primary} stopOpacity={0} />
          </RadialGradient>
          <RadialGradient id="gT" cx="97%" cy="15%" r="46%">
            <Stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.16} />
            <Stop offset="100%" stopColor="#0ea5e9" stopOpacity={0} />
          </RadialGradient>
        </Defs>
        <Rect x={0} y={0} width={winW} height={winH} fill="url(#gV)" />
        <Rect x={0} y={0} width={winW} height={winH} fill="url(#gB)" />
        <Rect x={0} y={0} width={winW} height={winH} fill="url(#gT)" />
      </Svg>

      {/* [S4 adım 6] Android 11+ (API 30) edge-to-edge pencerede aktivite klavyeyle DARALMAZ;
          manifest adjustResize tek başına yetmez → orada da 'padding' gerekir. Karar tek
          kaynakta (hooks/useKeyboard.KAV_BEHAVIOR_PENCERE). */}
      <KeyboardAvoidingView behavior={KAV_BEHAVIOR_PENCERE} style={styles.flex}>
        <ScrollView
          contentContainerStyle={[
            styles.scroll,
            {
              paddingTop: insets.top + spacing.xl,
              paddingBottom: insets.bottom + spacing.xxl,
              paddingLeft: Math.max(spacing.xl, insets.left),
              paddingRight: Math.max(spacing.xl, insets.right),
            },
          ]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* D1.81 · Y4 (Y23 ile tutarlı): oturum açılmamışken de mandal durumu ve "Sıfırla" görünür
              (masaüstü yerel istemcidir: sıfırlama ucu oturum istemez). */}
          <EstopMandalBandi />
          {/* Y184: oturum açmadan da dil seçilebilsin (Ayarlar'la AYNI kayıt; bayrak kapalıyken çizilmez). */}
          <View style={styles.dilSatiri}>
            <DilSecici />
          </View>
          {hesapEkleme ? (
            <View style={styles.eklemeBandi} testID="hesap-ekleme-bandi">
              <Text style={styles.eklemeMetni}>
                {t("giris.hesapEkleme.aciklama")}
              </Text>
              {onVazgec ? (
                <TouchableOpacity
                  style={[styles.eklemeVazgec, { minHeight: touch.min }]}
                  onPress={onVazgec}
                  accessibilityRole="button"
                  accessibilityLabel={t("giris.hesapEkleme.vazgecEtiketi")}
                >
                  <Text style={styles.eklemeVazgecMetni}>{t("giris.hesapEkleme.vazgec")}</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          ) : null}
          <View style={styles.card}>
            {/* Logo + marka */}
            <View style={styles.brand}>
              <View style={styles.logoRing}>
                <Image source={LOGO} style={styles.logo} resizeMode="contain" />
              </View>
              <Text style={styles.brandTitle}>PEMF Vet</Text>
              <Text style={styles.brandSub}>{t("giris.marka.altBaslik")}</Text>
            </View>

            {/* Sekmeler (giriş/kayıt) veya sıfırlama başlığı */}
            {isReset ? (
              <View style={styles.resetHead}>
                <Text style={styles.resetTitle}>{t("giris.sifirlama.baslik")}</Text>
                <Text style={styles.resetSub}>{t("giris.sifirlama.aciklama")}</Text>
              </View>
            ) : (
              <View style={styles.tabs}>
                <TouchableOpacity
                  style={[styles.tab, !isRegister && styles.tabActive]}
                  onPress={() => switchMode("login")}
                  accessibilityRole="button"
                >
                  <Text style={[styles.tabText, !isRegister && styles.tabTextActive]}>{t("giris.girisYap")}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.tab, isRegister && styles.tabActive]}
                  onPress={() => switchMode("register")}
                  accessibilityRole="button"
                >
                  <Text style={[styles.tabText, isRegister && styles.tabTextActive]}>{t("giris.kayitOl")}</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* Kişisel bilgiler (yalnız Kayıt) */}
            {isRegister && (
              <>
                <View style={styles.row}>
                  <ProfileField Icon={User} value={firstName} onChange={(t) => { setFirstName(t); setError(""); }} placeholder={t("giris.alan.ad")} flex autoCapitalize="words" onSubmitEditing={() => lastNameRef.current?.focus()} />
                  <ProfileField Icon={User} value={lastName} onChange={(t) => { setLastName(t); setError(""); }} placeholder={t("giris.alan.soyad")} flex autoCapitalize="words" inputRef={lastNameRef} onSubmitEditing={() => titleRef.current?.focus()} />
                </View>
                <ProfileField Icon={Stethoscope} value={title} onChange={setTitle} placeholder={t("giris.alan.unvan")} autoCapitalize="words" inputRef={titleRef} onSubmitEditing={() => phoneRef.current?.focus()} />
                <ProfileField Icon={Phone} value={phone} onChange={setPhone} placeholder={t("giris.alan.cepTelefonu")} keyboardType="phone-pad" inputRef={phoneRef} onSubmitEditing={() => emailRef.current?.focus()} />
              </>
            )}

            {/* E-posta */}
            <View style={styles.field}>
              <Mail size={18} color={colors.textMuted} style={styles.fieldIcon} />
              <TextInput
                ref={emailRef}
                style={styles.input}
                value={email}
                onChangeText={(t) => { setEmail(t); setError(""); setSuggestRegister(false); }}
                placeholder={t("giris.alan.eposta")}
                placeholderTextColor={colors.textMuted}
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
                autoComplete="email"
                textContentType="emailAddress"
                returnKeyType="next"
                blurOnSubmit={false}
                onSubmitEditing={() => pwRef.current?.focus()}
              />
            </View>

            {/* Şifre (giriş + kayıt; sıfırlamada YOK — orada yalnız e-posta) */}
            {!isReset && (
              <View style={styles.field}>
                <Lock size={18} color={colors.textMuted} style={styles.fieldIcon} />
                <TextInput
                  ref={pwRef}
                  style={[styles.input, { paddingRight: rs(40) }]}
                  value={password}
                  // SESSİZ GİRİŞ HATASI: şifre alanı boşluğu kırpmıyordu. Mobil klavye, panodan
                  // yapıştırma ve şifre yöneticileri şifrenin SONUNA sıklıkla boşluk ekler; Supabase
                  // bunu farklı bir şifre sayıp reddeder ve kullanıcı "E-posta veya şifre hatalı"
                  // görür — alanda hiçbir görünür fark olmadığı için sebebi anlaşılamaz.
                  // (Canlı doğrulandı: kırpılmış parola 200, sonunda boşluklu aynısı 400 — D3.16: değer burada YAZILMAZ.)
                  // Baştaki/sondaki boşluğu GİRİŞTE at → kullanıcının GÖRDÜĞÜ ile GÖNDERİLEN aynı olur.
                  // İç boşluklara dokunulmaz (gerçek bir parola karakteri olabilir).
                  onChangeText={(t) => { setPassword(t.replace(/^\s+|\s+$/g, "")); setError(""); }}
                  placeholder={t("giris.alan.sifre")}
                  placeholderTextColor={colors.textMuted}
                  secureTextEntry={!showPw}
                  autoCapitalize="none"
                  autoCorrect={false}
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  textContentType={isRegister ? "newPassword" : "password"}
                  returnKeyType={isRegister ? "next" : "go"}
                  blurOnSubmit={!isRegister}
                  onSubmitEditing={isRegister ? () => confirmRef.current?.focus() : submit}
                />
                <TouchableOpacity style={styles.eyeBtn} onPress={() => setShowPw((v) => !v)} accessibilityLabel={t("giris.alan.sifreGoster")}>
                  {showPw ? <EyeOff size={18} color={colors.textMuted} /> : <Eye size={18} color={colors.textMuted} />}
                </TouchableOpacity>
              </View>
            )}

            {/* Şifremi unuttum (yalnız giriş) */}
            {mode === "login" && (
              <TouchableOpacity onPress={() => switchMode("reset")} style={styles.forgotRow} accessibilityRole="button">
                <Text style={styles.forgotText}>{t("giris.sifremiUnuttum")}</Text>
              </TouchableOpacity>
            )}

            {/* Şifre tekrar (kayıt + sıfırlama) */}
            {showRules && (
              <View style={styles.field}>
                <Lock size={18} color={colors.textMuted} style={styles.fieldIcon} />
                <TextInput
                  ref={confirmRef}
                  style={styles.input}
                  value={confirm}
                  // Şifre alanıyla AYNI kural — yoksa "Şifreler eşleşmiyor" hatası, iki alan
                  // ekranda birebir aynı görünürken ortaya çıkardı.
                  onChangeText={(t) => { setConfirm(t.replace(/^\s+|\s+$/g, "")); setError(""); }}
                  placeholder={isReset ? t("giris.alan.yeniSifreTekrar") : t("giris.alan.sifreTekrar")}
                  placeholderTextColor={colors.textMuted}
                  secureTextEntry={!showPw}
                  autoCapitalize="none"
                  autoCorrect={false}
                  autoComplete="new-password"
                  textContentType="newPassword"
                  returnKeyType="next"
                  blurOnSubmit={false}
                  onSubmitEditing={() => clinicNameRef.current?.focus()}
                />
                {confirm.length > 0 && (
                  <View style={styles.eyeBtn}>
                    {confirmOk ? <Check size={18} color={colors.success} /> : <X size={18} color={colors.danger} />}
                  </View>
                )}
              </View>
            )}

            {/* Şifre kuralları (kayıt + sıfırlama) — canlı gösterge */}
            {showRules && (
              <View style={styles.rules}>
                <Rule ok={checks.length} label={t("giris.kural.enAz8")} />
                <Rule ok={checks.upper} label={t("giris.kural.buyukHarf")} />
                <Rule ok={checks.lower} label={t("giris.kural.kucukHarf")} />
                <Rule ok={checks.digit} label={t("giris.kural.rakam")} />
              </View>
            )}

            {/* Klinik bilgileri (yalnız Kayıt) */}
            {isRegister && (
              <>
                <Text style={styles.sectionLabel}>{isResearchReg ? t("giris.klinik.kurumBaslik") : t("giris.klinik.baslik")}</Text>
                <ProfileField Icon={Building2} value={clinicName} onChange={(t) => { setClinicName(t); setError(""); }} placeholder={isResearchReg ? t("giris.klinik.kurumAdi") : t("giris.klinik.ad")} autoCapitalize="words" inputRef={clinicNameRef} onSubmitEditing={() => cityRef.current?.focus()} />
                <View style={styles.row}>
                  <ProfileField Icon={MapPin} value={city} onChange={(t) => { setCity(t); setError(""); }} placeholder={t("giris.klinik.sehir")} flex autoCapitalize="words" inputRef={cityRef} onSubmitEditing={() => districtRef.current?.focus()} />
                  <ProfileField Icon={MapPin} value={district} onChange={(t) => { setDistrict(t); setError(""); }} placeholder={t("giris.klinik.ilce")} flex autoCapitalize="words" inputRef={districtRef} onSubmitEditing={() => addressRef.current?.focus()} />
                </View>
                <ProfileField Icon={Home} value={address} onChange={setAddress} placeholder={t("giris.klinik.adres")} autoCapitalize="sentences" inputRef={addressRef} onSubmitEditing={() => clinicPhoneRef.current?.focus()} />
                <ProfileField Icon={Phone} value={clinicPhone} onChange={setClinicPhone} placeholder={t("giris.klinik.acilTelefon")} keyboardType="phone-pad" inputRef={clinicPhoneRef} returnKeyType="done" onSubmitEditing={submit} />
              </>
            )}

            {/* .edu ipucu */}
            {showResearchHint && (
              <View style={styles.eduHint}>
                <GraduationCap size={16} color={colors.violet} />
                <Text style={styles.eduHintText}>{t("giris.arastirmaIpucu")}</Text>
              </View>
            )}

            {/* Bilgi (yeşil) + Hata */}
            {notice ? <Text style={styles.notice}>{notice}</Text> : null}
            {error ? <Text style={styles.error}>{error}</Text> : null}

            {/* "Doğrulama e-postasını tekrar gönder" düğmesi KALDIRILDI (2026-08-06):
                Supabase autoconfirm açık → gönderilecek doğrulama e-postası YOK. Düğme
                "gönderildi" deyip hiçbir şey yapmıyor, kullanıcıyı gelmeyen bir e-postayı
                beklemeye itiyordu. Şifre unutulduysa "Şifremi unuttum" akışı zaten var. */}

            {/* Kayıtsız e-posta → tek dokunuşla Kayıt Ol'a geç (e-posta/şifre korunur) */}
            {suggestRegister && !isRegister ? (
              <TouchableOpacity style={styles.suggestBtn} onPress={() => switchMode("register")} accessibilityRole="button">
                <Text style={styles.suggestText}>{t("giris.oneri.buEpostayla")}<Text style={styles.suggestLink}>{t("giris.oneri.hesapOlustur")}</Text></Text>
              </TouchableOpacity>
            ) : null}

            {/* Gönder */}
            <TouchableOpacity
              style={[styles.submit, !canSubmit && styles.submitDisabled]}
              onPress={submit}
              disabled={!canSubmit}
              accessibilityRole="button"
            >
              {loading ? (
                <ActivityIndicator color={colors.white} />
              ) : (
                <>
                  <Text style={styles.submitText} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>{isReset ? t("giris.sifirlama.gonder") : isRegister ? t("giris.hesapOlustur") : t("giris.girisYap")}</Text>
                  <ArrowRight size={18} color={colors.white} />
                </>
              )}
            </TouchableOpacity>

            {/* Alt geçiş */}
            {isReset ? (
              <TouchableOpacity onPress={() => switchMode("login")} style={styles.switchRow}>
                <Text style={styles.switchText}><Text style={styles.switchLink}>{t("giris.giriseDon")}</Text></Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity onPress={() => switchMode(isRegister ? "login" : "register")} style={styles.switchRow}>
                <Text style={styles.switchText}>
                  {isRegister ? t("giris.gecis.hesapVar") : t("giris.gecis.hesapYok")}
                  <Text style={styles.switchLink}>{isRegister ? t("giris.gecis.girisYap") : t("giris.gecis.kayitOl")}</Text>
                </Text>
              </TouchableOpacity>
            )}
          </View>

          <Text style={styles.footer}>{t("giris.altBilgi")}</Text>
        </ScrollView>
      </KeyboardAvoidingView>
      {/* D1.87 · A-58 / Y23 (sahip) + 1-C §9 #1: oturum açılmamışken / internet yokken de çalışan bobin DURDURULABİLİR.
          Eskiden burada yalnız mandal bandı ("Sıfırla") vardı — ekran durduramadan mandalı kaldırabiliyordu. Görünürlük
          kuralı kabukla AYNI (çalışan bobin / seans / STM belirsiz / teyitsiz). */}
      <GlobalEmergencyStop />
    </View>
  );
}

function ProfileField({ Icon, value, onChange, placeholder, keyboardType, autoCapitalize, flex, inputRef, returnKeyType, onSubmitEditing }: {
  Icon: ComponentType<{ size?: number; color?: string; style?: any }>;
  value: string;
  onChange: (t: string) => void;
  placeholder: string;
  keyboardType?: "default" | "phone-pad";
  autoCapitalize?: "none" | "words" | "sentences";
  flex?: boolean;
  inputRef?: React.RefObject<TextInput | null>;
  returnKeyType?: "next" | "done";
  onSubmitEditing?: () => void;
}) {
  return (
    <View style={[styles.field, flex ? { flex: 1, minWidth: rs(150) } : null]}>
      <Icon size={18} color={colors.textMuted} style={styles.fieldIcon} />
      <TextInput
        ref={inputRef}
        style={styles.input}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={colors.textMuted}
        keyboardType={keyboardType ?? "default"}
        autoCapitalize={autoCapitalize ?? "sentences"}
        autoCorrect={false}
        returnKeyType={returnKeyType ?? "next"}
        onSubmitEditing={onSubmitEditing}
        blurOnSubmit={returnKeyType === "done"}
      />
    </View>
  );
}

function Rule({ ok, label }: { ok: boolean; label: string }) {
  return (
    <View style={styles.rule}>
      <View style={[styles.ruleDot, ok ? styles.ruleDotOk : styles.ruleDotOff]}>
        {ok ? <Check size={11} color={colors.white} /> : null}
      </View>
      <Text style={[styles.ruleText, ok && styles.ruleTextOk]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  dilSatiri: { flexDirection: "row", justifyContent: "flex-end", marginBottom: spacing.sm },
  root: { flex: 1, backgroundColor: colors.bg },
  // CH1 · Y151: "Hesap ekle" kipinin bandı (etkin hesap açık kalır + vazgeç).
  eklemeBandi: {
    width: "100%", maxWidth: rs(460), marginBottom: spacing.md, padding: spacing.md, gap: spacing.sm,
    borderRadius: radius.lg, borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.panel,
  },
  eklemeMetni: { color: colors.text, fontSize: rf(13), lineHeight: rf(19) },
  eklemeVazgec: { alignSelf: "flex-start", justifyContent: "center", paddingHorizontal: spacing.md },
  eklemeVazgecMetni: { color: colors.primary, fontSize: rf(13), fontWeight: "700" },
  flex: { flex: 1 },
  // Yatay dolgu inline verilir (çentik güvenli alanı) — bkz. render.
  scroll: { flexGrow: 1, alignItems: "center", justifyContent: "center", paddingVertical: spacing.xxl },

  card: {
    width: "100%", maxWidth: rs(430), alignSelf: "center",
    backgroundColor: "rgba(24,32,51,0.92)",
    borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
    padding: spacing.xl, gap: spacing.md,
    shadowColor: "#000", shadowOpacity: 0.4, shadowRadius: 24, shadowOffset: { width: 0, height: rs(12) }, elevation: 12,
  },

  brand: { alignItems: "center", gap: spacing.xs, marginBottom: spacing.sm },
  logoRing: {
    width: rs(84), height: rs(84), borderRadius: rs(24),
    alignItems: "center", justifyContent: "center",
    backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: colors.primary,
    shadowColor: colors.primary, shadowOpacity: 0.5, shadowRadius: 18, shadowOffset: { width: 0, height: 0 }, elevation: 8,
  },
  logo: { width: rs(60), height: rs(60), borderRadius: rs(14) },
  brandTitle: { color: colors.text, fontSize: rf(26), fontWeight: "900", marginTop: spacing.xs },
  brandSub: { color: colors.textMuted, fontSize: typography.small },

  tabs: {
    flexDirection: "row", backgroundColor: colors.bg, borderRadius: radius.md,
    padding: rs(4), borderWidth: 1, borderColor: colors.border, marginBottom: spacing.xs,
  },
  tab: { flex: 1, paddingVertical: spacing.sm, borderRadius: radius.sm, alignItems: "center" },
  tabActive: { backgroundColor: colors.primary },
  tabText: { color: colors.textMuted, fontWeight: "700", fontSize: typography.body },
  tabTextActive: { color: colors.white },

  resetHead: { alignItems: "center", gap: rs(2), marginBottom: spacing.xs },
  resetTitle: { color: colors.text, fontSize: typography.title, fontWeight: "800" },
  resetSub: { color: colors.textMuted, fontSize: typography.small, textAlign: "center" },
  adminHint: { color: colors.textMuted, fontSize: typography.caption, marginTop: rs(4), marginLeft: rs(2) },
  // [S3 adım 7 / ampirik-4] Metin bağlantısının dokunma alanı metin kutusuyla sınırlıydı (~20 px).
  // Yükseklik tabanı + yatay dolgu ile 44 px; negatif marj görsel ritmi korur.
  forgotRow: {
    alignSelf: "flex-end", minHeight: touch.min, justifyContent: "center",
    paddingHorizontal: spacing.sm, marginTop: rs(-4) - spacing.sm, marginRight: -spacing.sm,
  },
  forgotText: { color: colors.primary, fontSize: touch.linkFont, fontWeight: "700" },

  field: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.bg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md,
  },
  fieldIcon: { marginRight: spacing.sm },
  input: { flex: 1, color: colors.text, fontSize: typography.body, paddingVertical: spacing.md },
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  sectionLabel: { color: colors.textMuted, fontSize: typography.caption, fontWeight: "800", letterSpacing: 0.5, textTransform: "uppercase", marginTop: spacing.xs },
  eyeBtn: { position: "absolute", right: spacing.md, height: "100%", justifyContent: "center", paddingLeft: spacing.sm },

  rules: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: rs(-2) },
  // [S6 adım 7 / ekranA-19] Sabit %48 genişlik, yazı ölçeği 1,3'te kural metnini kırpıyordu.
  // flexBasis + flexGrow: sığdığında 2 sütun, sığmadığında tek sütuna iner.
  rule: { flexDirection: "row", alignItems: "center", gap: rs(6), flexBasis: "48%", flexGrow: 1, minWidth: rs(130) },
  ruleDot: { width: rs(16), height: rs(16), borderRadius: rs(8), alignItems: "center", justifyContent: "center" },
  ruleDotOk: { backgroundColor: colors.success },
  ruleDotOff: { backgroundColor: "transparent", borderWidth: 1.5, borderColor: colors.border },
  ruleText: { color: colors.textMuted, fontSize: typography.caption, flexShrink: 1 },
  ruleTextOk: { color: colors.text },

  eduHint: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: "rgba(139,92,246,0.12)", borderRadius: radius.sm,
    borderWidth: 1, borderColor: "rgba(139,92,246,0.4)", padding: spacing.sm,
  },
  eduHintText: { color: colors.violet, fontSize: typography.caption, flex: 1 },

  error: { color: colors.danger, fontSize: typography.small, textAlign: "center" },
  notice: { color: colors.success, fontSize: typography.small, textAlign: "center" },
  suggestBtn: { alignItems: "center", paddingVertical: spacing.xs },
  suggestText: { color: colors.textMuted, fontSize: typography.small },
  suggestLink: { color: colors.primary, fontWeight: "800" },

  submit: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    backgroundColor: colors.primary, borderRadius: radius.md, minHeight: rs(54),
    paddingVertical: spacing.md, paddingHorizontal: spacing.lg, marginTop: spacing.xs,
    shadowColor: colors.primary, shadowOpacity: 0.4, shadowRadius: 14, shadowOffset: { width: 0, height: rs(4) }, elevation: 6,
  },
  submitDisabled: { backgroundColor: colors.panelSoft, shadowOpacity: 0, elevation: 0 },
  submitText: { color: colors.white, fontSize: rf(18), fontWeight: "800", textAlign: "center", flexShrink: 1 },

  switchRow: { alignItems: "center", justifyContent: "center", minHeight: touch.min, marginTop: 0 },
  switchText: { color: colors.textMuted, fontSize: touch.linkFont },
  switchLink: { color: colors.primary, fontWeight: "800" },

  footer: { color: colors.textMuted, fontSize: typography.caption, textAlign: "center", marginTop: spacing.lg, opacity: 0.7 },
});
