// Author: mertaygn, cglrgrkn
/**
 * CoilParameterPanel — Tekil bobin için parametre ayar paneli.
 *
 * Python unified_control_window'daki per-coil kontrol panelinin karşılığı.
 * Frekans, duty, faz, süre girişleri ve start/stop butonu içerir.
 */
import { StyleSheet, Text, View, TextInput, TouchableOpacity } from "react-native";
import { useState, useCallback, useEffect, useRef } from "react";
import { colors, spacing, typography, rf, rs, touch } from "@/theme/tokens";
import { apiPost } from "@/services/apiClient";
import { clampTherapyParams } from "@/services/therapyLimits";
import type { CoilDeviceAck } from "@/types/domain";
import { useTranslation } from "react-i18next";

const COIL_COLORS = [
  "#FF5252", "#FF4081", "#E040FB", "#7C4DFF",
  "#536DFE", "#448AFF", "#40C4FF", "#18FFFF",
];

// Bobin yüzey sıcaklığı UYARI eşiği (°C) — üstünde YALNIZ görsel uyarı.
// ⚠️ SAHİP KARARI A-47 + Y2 (2026-09-29): 48 °C'de otomatik durdurma/engelleme KALDIRILDI; hiçbir
// katmanda (firmware, backend, istemci) termal kesme yok (bobin 1–7; 8266'nın kendi 100 °C kesmesi
// firmware'de kalır, Y40). Eskiden bu eşiğin üstünde panel kendiliğinden STOP gönderiyordu.
// Geri eklenecekse sahip kararıyla ("istersek sonradan ekleriz"). Kapı:
// __tests__/CoilSicaklikUyarisi.A47.test.tsx.
const SICAKLIK_UYARI_ESIGI_C = 48;

interface Props {
  coilId: number;
  connected: boolean;
  running: boolean;
  objectTemp: number;
  /** GERÇEKTEN ölçülmüş alan adları; yoksa ilgili okuma kısa çizgi (—) gösterilir. */
  measuredFields?: string[];
  frequencyHz: number;
  dutyCycle: number;
  /** Y69: kartın UYGULADIĞI duty (%, ACK `E=`); null/undefined = bildirilmedi ("-"), 0 = sürülmüyor. */
  dutyEtkin?: number | null;
  magneticMt: number;
  currentA: number;
  defaultFreq?: number;
  defaultDuty?: number;
  defaultPhase?: number;
  defaultDuration?: number;
  disabled?: boolean;
  stm32Driven?: boolean;    // Bu bobin STM32 üzerinden mi çalışıyor?
  stmConnected?: boolean;   // STM32 USB bağlı mı?
  /** Son START komutunun CİHAZ onayı (ESP `coil_ack`); commandId ile HTTP yanıtındaki command_id eşleşir. */
  deviceAck?: CoilDeviceAck;
  /** CH4 · Y154: akım sensörü açık mı (backend bayrağı, `akimOlcumuAcik(snapshot)`). Kapalıyken "A" okuması ÇİZİLMEZ. */
  akimOlcumu?: boolean;
}

export function CoilParameterPanel({
  coilId,
  connected,
  running,
  objectTemp,
  measuredFields,
  frequencyHz,
  dutyCycle,
  dutyEtkin,
  magneticMt,
  currentA,
  defaultFreq = 50,
  defaultDuty = 25,
  defaultPhase = 0,
  defaultDuration = 0,
  disabled = false,
  stm32Driven = false,
  stmConnected = false,
  deviceAck,
  akimOlcumu = false,
}: Props) {
  const { t } = useTranslation();
  const [freq, setFreq] = useState(String(defaultFreq));
  const [duty, setDuty] = useState(String(defaultDuty));
  const [duration, setDuration] = useState(String(defaultDuration));
  const [phase, setPhase] = useState(String(defaultPhase));

  // ══════════════════════════════════════════════════════════════════════════
  // ⚠️ SAHA ARIZASI 2026-09-11 — "TOPLU UYGULAMA" DEĞERLERİ PANELLERE GEÇMİYORDU
  // ══════════════════════════════════════════════════════════════════════════
  // Sahip: "76 Hz, %50 duty, 30 dk ile başlattım, başlatınca kutu değerleri
  // default'a dönüyor (100 Hz, %25, 20 dk)."
  //
  // KÖK NEDEN: yukarıdaki `useState(String(defaultFreq))` başlangıç değerini YALNIZ
  // İLK MOUNT'ta okur. Operatör "Toplu Uygulama" alanlarını değiştirince prop güncelleniyor
  // ama panel state'i İLK değerde (ekran açıldığındaki 100/25/0/20) donup kalıyordu.
  //
  // ⚠️ BU KOZMETİK DEĞİL, DOZ HATASI: toplu başlatma master değerlerini doğru gönderiyor,
  // ama operatör panelde başka bir sayı GÖRÜYOR ve o panelin kendi "Başlat"ına basarsa
  // bobin GÖRDÜĞÜ değerle değil, donmuş eski değerle sürülür.
  //
  // ÇÖZÜM: master değeri DEĞİŞTİĞİNDE paneli takip ettir. Alan başına "en son görülen
  // master" ref'i tutulur; yalnız o alanın master'ı değiştiğinde üzerine yazılır.
  // Böylece tek bir bobine özel değer girildiğinde (ör. bobin 3 = 200 Hz) master'ın
  // DEĞİŞMEYEN alanları o bobini bozmaz — yalnız gerçekten değişen alan güncellenir.
  const sonMaster = useRef({
    freq: defaultFreq,
    duty: defaultDuty,
    phase: defaultPhase,
    duration: defaultDuration,
  });
  useEffect(() => {
    const s = sonMaster.current;
    if (defaultFreq !== s.freq) { s.freq = defaultFreq; setFreq(String(defaultFreq)); }
    if (defaultDuty !== s.duty) { s.duty = defaultDuty; setDuty(String(defaultDuty)); }
    if (defaultPhase !== s.phase) { s.phase = defaultPhase; setPhase(String(defaultPhase)); }
    if (defaultDuration !== s.duration) { s.duration = defaultDuration; setDuration(String(defaultDuration)); }
  }, [defaultFreq, defaultDuty, defaultPhase, defaultDuration]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Cihaz onayı beklenen START'ın command_id'si (saha 2026-09-08: "butona dokundum, PWM başladı mı?").
  // Saat karşılaştırması DEĞİL, command_id eşleşmesi: tablet/backend saat kayması sonucu etkilemez.
  const [bekleyenKomut, setBekleyenKomut] = useState<string | null>(null);
  // ⚠️ D1.82 · İG-6.8 · Y47: Durdur, kendi START isteği askıdayken de basılabilir. Elle tekil yolda START'ın niyeti ile
  // sürüşü arasında nesil denetimi yok (1-C bilinçli kapsam): istek backend'e STOP'tan SONRA ulaşırsa bobin yeniden
  // başlar → START yanıtından sonra STOP YİNELENİR (idempotent; gönderim yalnız artar, Ö.4-Y8). Ref: aynı render'da da görülsün.
  const startUcustaRef = useRef(false);
  const startSonrasiDurdurRef = useRef(false);

  const color = COIL_COLORS[(coilId - 1) % 8];

  const sendCommand = useCallback(async (start: boolean): Promise<boolean> => {
    if (start) {
      startUcustaRef.current = true;
      startSonrasiDurdurRef.current = false;
    } else if (startUcustaRef.current) {
      startSonrasiDurdurRef.current = true;
    }
    setLoading(true);
    setError(null);
    try {
      // NaN-guard (|| DEĞİL): kullanıcı bilerek 0 yazarsa (bobini parkla) 0 KORUNSUN — eskiden
      // `parseFloat("0") || defaultFreq` 0'ı falsy sayıp default'a döndürüp bobini süründürüyordu.
      // Arka uç 0 Hz BAŞLATMAYI o bobin için DURDURMA olarak işler (A-05, D1.53; yanıtta `sifirHzDurdurma`).
      const pf = parseFloat(freq);   let f = Number.isNaN(pf) ? defaultFreq : pf;
      const pd = parseFloat(duty);   let d = Number.isNaN(pd) ? defaultDuty : pd;
      const pp = parseFloat(phase);  let ph = Number.isNaN(pp) ? defaultPhase : pp;
      // NaN-guard (|| DEĞİL): boş/geçersiz süre `parseInt(NaN)||0 = 0` ile SESSİZCE "süresiz"
      // oluyordu. Geçersizse default'a düş; ayrıca 0/süresiz'e çözülürse AÇIK uyar (aşağıda).
      const pDur = parseInt(duration, 10);
      let durMin = Number.isNaN(pDur) ? defaultDuration : pDur;
      if (start) {
        // Güvenlik: yalnızca BAŞLAT'ta sınır uygula (stop meşru biçimde 0 olabilir).
        const c = clampTherapyParams({ freq: f, duty: d, phase: ph, duration: durMin });
        f = c.values.freq; d = c.values.duty; ph = c.values.phase; durMin = c.values.duration;
        const warns = [...c.warnings];
        // Süre 0/süresiz: operatör süre girmediğini BİLMELİ — sessiz süresiz-seans olmasın.
        // ⚠️ DENETİM 2026-08-17 — ESKİ METİN DAYANAKSIZDI. Burada "donanım watchdog'u DURATION_MAX'a
        // kaplar (kontrolsüz kalmaz)" yazıyordu ve kullanıcıya "bobin donanım üst-sınırına kadar
        // çalışır" deniyordu. İki açıdan yanlıştı: (1) `DURATION_MAX_MINUTES` (9999 dk ≈ 6,9 gün)
        // klinik bir sınır değil, STM32 PROTOKOL sabitidir — gerçek klinik kapak 120 dk;
        // (2) bu panel ESP bobinlerini (6-8) de sürüyor ve o taraftaki "donanım üst-sınırı"
        // iddiasının dayanağı bu depoda YOK (ESP firmware'i burada değil, bkz. firmware/README).
        // Gerçek kapağı SUNUCU uygular: `_esp_duration_seconds` (ESP) + `HardwareController` (STM).
        // Yanlış güvence, korumasızlıktan tehlikelidir → metin artık nereye dayandığını söylüyor.
        // Kilit: `__tests__/CoilDurationHonesty.test.tsx`.
        if (durMin <= 0) warns.push(t("kontrol.panel.sureGirilmedi"));
        if (warns.length) setError(warns.join(" "));
      }
      // YÜKSEK fix: apiPost ağ-hatası/non-2xx'te THROW ETMEZ (fallback=null döner) → dönüşü DOĞRULA.
      // Eskiden yanıt kontrol edilmeden "başarılı" sayılıyordu → STOP sessizce düşse bile kullanıcı
      // bobinin durduğunu sanıyordu (bobin ÇALIŞMAYA DEVAM). null/status:error → açık uyarı ver.
      // ⚠️ D3I çapraz (C2) · Ö.4-Y8: DURDUR düz-HTTP kapısına BAĞLANMAZ (`durdurma: true`, yalnız start:false gövdeyle — AST kapısı
      // `acilDurdur.Y8.duzHttp.D3I.test.tsx`); BAŞLAT kapıda KALIR. Eskiden ikisi tek çağrıydı → genel http'de Durdur HİÇ gitmiyordu.
      const govde = { freq: f, duty: d, phase: ph, duration: durMin * 60 };
      type KomutYaniti = { status?: string; command_id?: string; mesaj?: string } | null;
      const res = start
        ? await apiPost<KomutYaniti>(`/coil/${coilId}/control`, { ...govde, start: true }, null)
        : await apiPost<KomutYaniti>(`/coil/${coilId}/control`, { ...govde, start: false }, null, { durdurma: true });
      if (start) {
        startUcustaRef.current = false;
        if (startSonrasiDurdurRef.current) {
          // D1.82: START uçuştayken operatör DURDUR'a bastı → yanıt ne olursa olsun STOP yinelenir; son söz durdurmanın.
          startSonrasiDurdurRef.current = false;
          const dur = await apiPost<{ status?: string } | null>(`/coil/${coilId}/control`, {
            freq: 0, duty: 0, phase: 0, duration: 0, start: false,
          }, null, { durdurma: true });
          setBekleyenKomut(null);
          if (!dur || dur.status !== "success") {
            setError(t("kontrol.panel.durdurmaOnaylanamadi"));
          }
          return false;
        }
      }
      // Denetim 2. tur [1.1] (2026-08-20): teyit yalnız AÇIK "success". Backend broker'a
      // ulaşamayınca HTTP 200 + {status:"mqtt_unavailable"} döner; eski yüklem (`!== "error"`)
      // onu teyit sayıyordu → durdurma komutu hiç ulaşmamışken "durduruldu" deniyordu (sahte güvence,
      // korumasızlıktan tehlikeli; o zamanki en ağır yüzey A-47 ile kaldırılan 48 °C otomatik
      // durdurmasıydı). Kilit: __tests__/coilDurdurmaOnayi.test.tsx.
      const ok = !!res && res.status === "success";
      // ESP bobini: broker aldı (PUBACK) ≠ cihaz uyguladı. Yanıttaki command_id ile `coil_ack` eşlenir;
      // eski backend command_id vermezse bekleme durumu hiç açılmaz (sessiz geriye-uyum). STM bobinleri
      // ack yayınlamaz → onlarda bekleme YOK.
      setBekleyenKomut(start && ok && !stm32Driven && typeof res?.command_id === "string" ? res.command_id : null);
      if (!ok) {
        // TD6 · K3 (tezgâh Oturum 13): kart duty'yi REDDETTİYSE backend nedeni ve eylemi `mesaj`la verir ("Bobin 1 çift yönlü
        // kipte en fazla %50 çalışabilir; %80 kabul edilmedi. …"); eskiden API "success" dönüyor, bobin sessizce başlamıyordu.
        setError(start
          ? (typeof res?.mesaj === "string" && res.mesaj.trim()
            ? res.mesaj
            : t("kontrol.panel.komutOnaylanamadi"))
          : t("kontrol.panel.durdurmaOnaylanamadi"));
      }
      return ok;
    } catch {
      setError(t("kontrol.panel.komutGonderilemedi"));
      return false;
    } finally {
      if (start) startUcustaRef.current = false;
      setLoading(false);
    }
  }, [coilId, freq, duty, phase, duration, defaultFreq, defaultDuty, defaultPhase, defaultDuration, t]);

  /** Bu alan GERÇEKTEN ölçülüyor mu? (bkz. readings bloğundaki gerekçe) */
  const olcum = useCallback(
    (alan: string) => Array.isArray(measuredFields) && measuredFields.includes(alan),
    [measuredFields]
  );

  // A-47: 48 °C üstü YALNIZ görsel uyarı — istek GÖNDERİLMEZ, seans engellenmez/durdurulmaz.
  // Yalnız GERÇEKTEN ölçülen (taze) sıcaklıkta: susan sensörün donmuş değeri backend'de
  // `measuredFields`ten düşer (D1.67) → ne sayı ne uyarı (Y6: '—').
  const sicaklikUyarisi = olcum("objectTemp") && objectTemp > SICAKLIK_UYARI_ESIGI_C;

  const isDisabled = disabled || !connected || (stm32Driven && !stmConnected);

  // Cihaz onayı metni: YALNIZ bekleyen START'ın command_id'siyle eşleşen ack sayılır (eski/başka
  // komutun onayı sahte güvence olmasın). ok=true → PWM cihazda uygulandı; false → cihaz reddetti
  // (termal kilit / doğrulama); null → 2 sn içinde onay gelmedi.
  const guncelAck = bekleyenKomut && deviceAck && deviceAck.commandId === bekleyenKomut ? deviceAck : null;
  let ackMetni: string | null = null;
  let ackRenk = "#94a3b8";
  if (bekleyenKomut && !guncelAck) {
    ackMetni = t("kontrol.panel.ackBekleniyor");
  } else if (guncelAck?.ok === true) {
    const ms = typeof guncelAck.latencyMs === "number" ? ` (${guncelAck.latencyMs} ms)` : "";
    ackMetni = t("kontrol.panel.ackOk", { ms });
    ackRenk = "#22c55e";
  } else if (guncelAck?.ok === false) {
    ackMetni = t("kontrol.panel.ackRed");
    ackRenk = "#ef4444";
  } else if (guncelAck) {
    ackMetni = t("kontrol.panel.ackGelmedi");
    ackRenk = "#f59e0b";
  }

  return (
    <View style={[styles.card, { borderColor: connected ? color + "44" : "#334155" }]}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={[styles.colorDot, { backgroundColor: connected ? color : "#475569" }]} />
          <Text style={styles.coilTitle}>{t("kontrol.bobin.baslik", { id: coilId })}</Text>
          {stm32Driven ? (
            <View style={styles.sourceBadgeStm}><Text style={styles.sourceBadgeText}>STM32</Text></View>
          ) : (
            <View style={styles.sourceBadgeEsp}><Text style={styles.sourceBadgeText}>WiFi</Text></View>
          )}
        </View>
        <View style={styles.headerRight}>
          {olcum("objectTemp") ? (
            <View style={[styles.tempBadge, objectTemp > 45 && styles.tempWarning]}
              accessibilityLabel={objectTemp > 45 ? t("kontrol.panel.sicaklikYuksekEtiketi", { sicaklik: objectTemp.toFixed(1) }) : t("kontrol.panel.sicaklikEtiketi", { sicaklik: objectTemp.toFixed(1) })}>
              {/* #121: >45°C uyarısı yalnız-RENK değil — ⚠ ikonu + metin (renk-körü operatör görsün). */}
              <Text style={styles.tempText}>{objectTemp > 45 ? "⚠ " : ""}{objectTemp.toFixed(1)}°C</Text>
            </View>
          ) : (
            /* ⚠️ DENETİM 2026-08-09 (Tier 2) — "ÖLÇÜLMÜYOR" İLE "SERİN" AYIRT EDİLEBİLMELİ.
               Eskiden sıcaklık yoksa rozet HİÇ çizilmiyordu; operatör bunu "sorun yok" diye
               okuyabiliyordu. Oysa STM üzerinden sürülen bobiller (`live_state.STM_COIL_IDS`)
               için STM protokolünde SICAKLIK ALANI YOKTUR — o bobinlerden hiçbir zaman ölçüm
               gelmez. (A-47 ile 48 °C otomatik durdurması TÜM bobinlerden kaldırıldı; ölçülen
               bobinde de yalnız görsel uyarı vardır — `SICAKLIK_UYARI_ESIGI_C`.)
               ⚠️ BURAYA SAYI YAZMAYIN. 2026-09-10'a kadar bu yorumda sabit bir bobin sayısı
               duruyordu; bobin 6-7 ESP'den STM'e taşınınca yorum sessizce BAYATLADI. Kapsam tek
               kaynak `live_state.STM_COIL_IDS`'tedir. Kapı: tests/test_sim_GERCEGI_ASMAZ.py Koruma donanım tarafında yapılana kadar bu sınır GÖRÜNÜR olmalı;
               sessiz bir boşluk, operatörün var olmayan bir korumaya güvenmesine yol açar.
               (Gerçek çözüm: 1-5 için sıcaklık sensörü + STM telemetrisi + firmware kesmesi.) */
            /* Sahip isteği 2026-09-10: ölçüm olmayan yerde KISA ÇİZGİ dursun.
               ⚠️ Ekran-okuyucu etiketi AÇIK KALIYOR: görsel çizgi kısa ama "ölçüm yok +
               otomatik termal durdurma uygulanmaz" bilgisi kaybolmamalı (görme engelli
               operatör için tek kaynak). */
            <View style={styles.tempBadge}
              accessibilityLabel={t("kontrol.panel.sicaklikOlcumuYok")}>
              <Text style={[styles.tempText, { color: colors.textMuted }]}>-</Text>
            </View>
          )}
          {/* A11y (#67): durum YALNIZ-RENK değil — nokta + kısa metin (renk-körü operatör AKTİF ile
              HAZIR/durmuş bobini ayırt edebilsin; ekran-okuyucu için accessibilityLabel). */}
          <View style={styles.statusWrap}>
            <View
              style={[styles.statusDot, { backgroundColor: running ? "#22c55e" : connected ? "#f59e0b" : "#ef4444" }]}
              accessibilityElementsHidden
              importantForAccessibility="no"
            />
            <Text
              style={[styles.statusLabel, { color: running ? "#22c55e" : connected ? "#f59e0b" : "#ef4444" }]}
              accessibilityLabel={running ? t("kontrol.panel.durumAktifEtiketi") : connected ? t("kontrol.panel.durumHazirEtiketi") : t("kontrol.panel.durumCevrimdisiEtiketi")}
            >
              {running ? t("ayarlar.sistemDurumu.aktif") : connected ? t("kontrol.bobin.hazir") : t("kontrol.bobin.offline")}
            </Text>
          </View>
        </View>
      </View>

      {/* Live readings
          ⚠️ ÖLÇÜLMEYEN ALAN KISA ÇİZGİ (—), SIFIR DEĞİL. Bobin 1-5'te yalnız ACS712
          (akım) var, bobin 6-7'de yalnız MLX (sıcaklık/alan). `0.00 mT` yazmak
          "ölçtüm, sıfır çıktı" diye okunur ve operatör var olmayan bir sensöre güvenir.
          Kaynak `measuredFields` — backend bunu GELEN telemetriden türetir, bobin
          numarasından TAHMİN ETMEZ (topoloji değişince arayüz kendiliğinden doğru kalır). */}
      <View style={styles.readings}>
        <Reading label="mT" value={olcum("magneticMt") ? magneticMt.toFixed(2) : "-"} active={running} />
        {/* CH4 · Y154: akım sensörü KAPALIYKEN (varsayılan) "A" okuması hiç çizilmez. */}
        {akimOlcumu ? (
          <Reading label="A" value={olcum("currentA") ? currentA.toFixed(3) : "-"} active={running} />
        ) : null}
        <Reading label="Hz" value={frequencyHz > 0 ? String(frequencyHz) : "-"} active={running} />
        <Reading label={t("kontrol.panel.dcYuzde")} value={dutyCycle > 0 ? String(dutyCycle) : "-"} active={running} />
        {/* Y69 (sahip, S-G4): İSTENEN DC%'nin yanında kartın UYGULADIĞI (ACK `E=`; 1 kHz bipolar %50 → 46.0).
            Bildirilmediyse "-"; 0 gerçek değerdir (0 tick'e nicelenmiş bobin SÜRÜLMÜYOR). */}
        <Reading
          label={t("kontrol.panel.uygYuzde")}
          value={typeof dutyEtkin === "number" && Number.isFinite(dutyEtkin) ? dutyEtkin.toFixed(1) : "-"}
          active={running}
        />
      </View>

      {/* Parameter inputs */}
      <View style={styles.paramGrid}>
        <ParamInput
          label={t("kontrol.panel.frekansHz")}
          value={freq}
          onChangeText={setFreq}
          disabled={isDisabled}
          keyboardType="numeric"
        />
        <ParamInput
          label={t("kontrol.panel.dutyYuzde")}
          value={duty}
          onChangeText={setDuty}
          disabled={isDisabled}
          keyboardType="numeric"
        />
        <ParamInput
          label={t("kontrol.panel.fazDerece")}
          value={phase}
          onChangeText={setPhase}
          disabled={isDisabled}
          keyboardType="numeric"
        />
        <ParamInput
          label={t("kontrol.panel.sureDk")}
          value={duration}
          onChangeText={setDuration}
          disabled={isDisabled}
          keyboardType="numeric"
        />
      </View>

      {/* A-47: 48 °C üstü YALNIZ GÖRSEL UYARI. Otomatik durdurma YOK (sahip kararı) — metin bunu
          AÇIKÇA söyler ki operatör var olmayan bir korumaya güvenmesin; durdurma kararı operatörde
          (⏹ Durdur / ACİL DURDUR). A11y (#68): yanık riski ekran-okuyucuya duyurulur. */}
      {sicaklikUyarisi ? (
        <Text
          style={styles.errorText}
          testID="sicaklik-uyarisi"
          accessibilityRole="alert"
          accessibilityLiveRegion="assertive"
        >
          {t("kontrol.panel.sicaklikUyari", { esik: SICAKLIK_UYARI_ESIGI_C, sicaklik: objectTemp.toFixed(1) })}
        </Text>
      ) : null}

      {/* A11y (#68): komut/durdurma-onaylanamadı gibi güvenlik uyarıları ekran-okuyucuya
          DUYURULSUN. accessibilityLiveRegion='assertive' + role='alert'. */}
      {error ? (
        <Text style={styles.errorText} accessibilityRole="alert" accessibilityLiveRegion="assertive">
          {error}
        </Text>
      ) : null}

      {/* CİHAZ ONAYI (saha 2026-09-08): "butona dokundum, PWM başladı mı?" — broker PUBACK'i değil,
          ESP'nin kendi `ack`i (firmware isActive()). Backend `coil_ack` WS olayı ms içinde gelir;
          'Aktif' rozeti 3 sn'lik status telemetrisinden geldiği için tek başına geç kalıyordu. */}
      {ackMetni ? (
        <Text
          style={[styles.ackText, { color: ackRenk }]}
          testID="cihaz-onayi"
          accessibilityRole="text"
          accessibilityLiveRegion="polite"
        >
          {ackMetni}
        </Text>
      ) : null}

      {/* Control buttons */}
      <View style={styles.btnRow}>
        {/* ⚠️ ETİKET DURUMA GÖRE (sahip isteği 2026-09-11: "parametre güncelle butonu lazım").
            Bobin ÇALIŞIRKEN bu düğme zaten bir güncellemedir — firmware çalışan bobinde
            frekans/duty/faz/süreyi kesintisiz değiştirir, yeniden başlatma YOKTUR.
            Ama üzerinde "Başlat" yazdığı için operatör basmaya çekiniyordu ("tedaviyi
            baştan mı alır?"). Etiket artık ne yaptığını söylüyor; DAVRANIŞ AYNI. */}
        <TouchableOpacity
          style={[styles.btnStart, isDisabled && styles.btnDisabled]}
          onPress={() => sendCommand(true)}
          disabled={isDisabled || loading}
          accessibilityRole="button"
          accessibilityLabel={running ? t("kontrol.panel.guncelleEtiketi") : t("kontrol.panel.baslatEtiketi")}
        >
          <Text style={styles.btnStartText}>{running ? t("kontrol.panel.uygula") : t("kontrol.panel.baslat")}</Text>
        </TouchableOpacity>
        {/* DURDURMA ASLA KİLİTLENMEZ: buton `running`'e bağlıydı ve `running` telemetriden gelir.
            STM çevrimdışı raporlandığında LiveDataContext bu bobinleri `running:false`'a
            normalize ettiğinden (bağlantı yokken "çalışıyor" gösterme kuralı), bobin gerçekte
            sürülüyor olsa bile Durdur butonu DEVRE DIŞI kalıyordu — yani telemetri kaybı, durdurma
            yeteneğini de götürüyordu. Durdurma komutu idempotenttir; her zaman gönderilebilmeli. */}
        {/* ⚠️ D1.82 · Y47: `disabled={loading}` KALKTI — kendi START isteği askıdayken (≤ 8 sn) durdurma basılamıyordu
            (ölçüldü: STOP isteği 0, bobin sürmeye devam etti). `loading` yalnız görünüm. */}
        <TouchableOpacity
          style={[styles.btnStop, loading && styles.btnDisabled]}
          onPress={() => sendCommand(false)}
          accessibilityRole="button"
          accessibilityLabel={t("kontrol.panel.durdurEtiketi")}
        >
          <Text style={styles.btnStopText}>{t("kontrol.panel.durdur")}</Text>
        </TouchableOpacity>
      </View>

      {!connected && (
        <View style={styles.offlineBanner}>
          <Text style={styles.offlineText}>{t("kontrol.panel.bobinBagliDegil")}</Text>
        </View>
      )}
    </View>
  );
}

function Reading({ label, value, active }: { label: string; value: string; active: boolean }) {
  return (
    <View style={styles.reading}>
      {/* [S6 adım 4] Canlı okuma (mT / °C / A) tek satır ve sığdırılarak yazılır: sistem yazı
          ölçeği 1,3'te "12.34 mT" iki satıra bölünüp kart yüksekliğini kaydırıyordu. */}
      <Text
        style={[styles.readingValue, !active && { color: "#475569" }]}
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.7}
        maxFontSizeMultiplier={1.1}
      >
        {value}
      </Text>
      <Text style={styles.readingLabel}>{label}</Text>
    </View>
  );
}

function ParamInput({
  label,
  value,
  onChangeText,
  disabled,
  keyboardType,
}: {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
  disabled: boolean;
  keyboardType: "numeric" | "default";
}) {
  return (
    <View style={styles.paramInputWrap}>
      <Text style={styles.paramLabel}>{label}</Text>
      <TextInput
        style={[styles.paramInput, disabled && styles.paramInputDisabled]}
        value={value}
        onChangeText={onChangeText}
        editable={!disabled}
        keyboardType={keyboardType}
        selectTextOnFocus
        accessibilityLabel={label}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#0f172a",
    borderRadius: 14,
    padding: spacing.md,
    borderWidth: 1,
    gap: spacing.sm,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  headerLeft: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  headerRight: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  colorDot: { width: rs(10), height: rs(10), borderRadius: 5 },
  coilTitle: { color: colors.text, fontWeight: "700", fontSize: typography.body },
  statusDot: { width: rs(8), height: rs(8), borderRadius: 4 },
  statusWrap: { flexDirection: "row", alignItems: "center", gap: rs(4) },
  // [S6/S7-10] 320 px'te 9 px'e düşüyordu (okunmuyordu).
  statusLabel: { fontSize: typography.small, fontWeight: "700", letterSpacing: 0.3 },
  tempBadge: {
    backgroundColor: "#1e293b",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
  },
  tempWarning: { backgroundColor: "#7f1d1d" },
  tempText: { color: colors.text, fontSize: rf(11), fontWeight: "700" },

  readings: {
    flexDirection: "row",
    gap: spacing.xs,
    backgroundColor: "#1e293b",
    borderRadius: 8,
    padding: spacing.sm,
  },
  reading: { flex: 1, alignItems: "center" },
  readingValue: { color: colors.primary, fontSize: typography.body, fontWeight: "800", fontVariant: ["tabular-nums"] as any },
  readingLabel: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700" },

  paramGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
  },
  paramInputWrap: { width: "48%", gap: 2 },
  paramLabel: { color: colors.textMuted, fontSize: rf(11), fontWeight: "600" },
  paramInput: {
    backgroundColor: "#1e293b",
    borderRadius: 6,
    padding: spacing.sm,
    color: colors.text,
    fontSize: typography.body,
    fontWeight: "700",
    borderWidth: 1,
    borderColor: "#334155",
  },
  paramInputDisabled: { opacity: 0.4 },

  btnRow: { flexDirection: "row", gap: spacing.xs },
  btnStart: {
    flex: 1,
    backgroundColor: "#16a34a",
    borderRadius: 8,
    padding: spacing.sm,
    alignItems: "center",
    justifyContent: "center",
    // [S3] 320 px'te dolgu ile 32 px kalıyordu; bobin başlat/durdur hedefi 44 px tabanında.
    minHeight: touch.min,
  },
  btnStartText: { color: "#fff", fontWeight: "700", fontSize: typography.small },
  btnStop: {
    flex: 1,
    backgroundColor: "#7f1d1d",
    borderRadius: 8,
    padding: spacing.sm,
    alignItems: "center",
    justifyContent: "center",
    // [S3] 320 px'te dolgu ile 32 px kalıyordu; bobin başlat/durdur hedefi 44 px tabanında.
    minHeight: touch.min,
  },
  btnStopText: { color: "#fff", fontWeight: "700", fontSize: typography.small },
  btnDisabled: { opacity: 0.4 },

  errorText: { color: "#ef4444", fontSize: typography.small },
  ackText: { fontSize: typography.small, fontWeight: "600", marginTop: spacing.xs },
  offlineBanner: {
    backgroundColor: "#1e293b",
    borderRadius: 6,
    padding: spacing.xs,
    alignItems: "center",
  },
  offlineText: { color: "#f59e0b", fontSize: typography.small, fontWeight: "600" },
  sourceBadgeStm: {
    backgroundColor: "#1e3a5f",
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 2,
    borderWidth: 1,
    borderColor: "#3b82f6",
  },
  sourceBadgeEsp: {
    backgroundColor: "#14532d",
    borderRadius: 4,
    paddingHorizontal: 5,
    paddingVertical: 2,
    borderWidth: 1,
    borderColor: "#22c55e",
  },
  sourceBadgeText: { color: "#fff", fontSize: typography.small, fontWeight: "800" },
});
