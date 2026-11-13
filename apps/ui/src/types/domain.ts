// Author: mertaygn, cglrgrkn
// ─── Route ───────────────────────────────────────────────────────────────────
export type RouteKey =
  | "dashboard"
  | "control"
  | "sensors"
  | "history"
  | "patients"
  | "kpi"
  | "simulator"
  | "ai"
  | "ai_history"
  | "settings";

// ─── Connection ──────────────────────────────────────────────────────────────
/**
 * Bağlantı/alt sistem durumu.
 *
 * ⚠️ `devre_disi` (2026-09-11): alt sistem KURULU DEĞİL — arıza DEĞİLDİR. ESP kartları
 * sistemden söküldüğünde MQTT bu duruma düşer. Eskiden "warning" kalıyordu ve kurulu
 * olmayan bir şey için kalıcı sarı rozet üretiyordu (sahip: "kırmızı dolu bir ekran var").
 * Uyarı körlüğüne karşı: renk YALNIZ gerçekten bozuk olan için ayrılır.
 */
export type ConnectionState = "online" | "warning" | "offline" | "error" | "devre_disi";

// ─── Coil ────────────────────────────────────────────────────────────────────
/** ESP bobininin START komutuna verdiği cihaz-onayı (backend `coil_ack` WS olayı, saha 2026-09-08).
 *  ok=true → PWM gerçekten uygulandı (firmware `isActive()`), false → cihaz REDDETTİ (termal kilit /
 *  doğrulama), null → 2 sn içinde onay GELMEDİ. Broker PUBACK'i DEĞİL, cihazın kendi sözüdür. */
export interface CoilDeviceAck {
  ok: boolean | null;
  reason: "ack" | "nack" | "timeout";
  commandId?: string;
  latencyMs?: number;
  ts: number;
}

export interface CoilStatus {
  id: number;
  connected: boolean;
  running: boolean;
  frequencyHz: number;
  dutyCycle: number;
  magneticMt: number;
  objectTemp: number;
  ambientTemp: number;
  currentA: number;
  stm32Driven?: boolean;
  phase?: number;
  durationMin?: number;
  /** Son START komutunun cihaz onayı (yalnız ESP 6-8; status telemetrisiyle SİLİNMEZ). */
  deviceAck?: CoilDeviceAck;
  /**
   * GERÇEKTEN ölçülmüş alan adları (`"currentA"`, `"objectTemp"`, `"ambientTemp"`,
   * `"magneticMt"`). Backend bunu gelen telemetriden TÜRETİR.
   *
   * ⚠️ NEDEN VAR: `0.0` ile "ölçülmedi" ayırt edilemiyordu. Bobin 1-5'te yalnız ACS712
   * (akım), bobin 6-7'de yalnız MLX (sıcaklık/alan) var; ölçülmeyen alan `_live_state`te
   * `0.0` olarak DURUR (aşağı akış `null` değil `0.0` bekliyor). Arayüz bu listeye bakıp
   * ölçülmeyeni **kısa çizgi (—)** gösterir; `0.00 mT` yazmak ölçüm gibi okunur.
   *
   * Boş/tanımsız → hiçbir alan ölçülmemiş (henüz telemetri gelmedi ya da sensör yok).
   */
  measuredFields?: string[];
  /** TD2: alan sensörünün kazanç ayarı doğrulanamadı — ölçülen mT GÖSTERİLMEZ (backend yazmaz). */
  alanDogrulanamadi?: boolean;
  /** TD5: akım ölçümü güvenilmez (ADC tavanı / aralık dışı) — `currentA` GÖSTERİLMEZ (backend yazmaz). */
  akimGuvenilmez?: boolean;
  /**
   * Kartın ETKİN olarak uyguladığı sürüş kipi (ACK `K=` alanı). `true` = unipolar.
   *
   * ⚠️ `undefined`/`null` = FIRMWARE BİLDİRMEDİ (eski sürüm ya da hiç sürüş olmadı).
   * `false` varsaymak "bipolar doğrulandı" yalanıdır — arayüz bu durumda kısa çizgi
   * gösterir. İSTEK değil ETKİN kiptir: bobin 6-7 sürücüsü tek yönlü olduğundan
   * onlara bipolar istense de `true` döner.
   */
  unipolar?: boolean | null;
  /**
   * T-c (Tezgâh-2 #6): backend'in KAYITLI sürüş kipi isteği (yetenekle OR'lanmış — bir sonraki sürüşte karta GİDEN kip).
   * Sürüş Kipi kutuları bundan başlar; yoksa kartın bildirdiği `unipolar`dan. `null`/yok = bu backend sürecinde istek yapılmadı.
   */
  unipolarIstek?: boolean | null;
  /** Bu bobin bipolar sürülebilir mi (donanım yeteneği). Yoksa düğme KİLİTLİ çizilir. */
  bipolarYetenek?: boolean;
  /**
   * Y69 (sahip, S-G4): kartın GERÇEKTEN uyguladığı duty (%, ACK `E=`). `dutyCycle` İSTENENDİR (ACK `D=`); yüksek
   * frekansta ölü-zaman tavanı ve tick nicelemesi uygulananı düşürür (1 kHz bipolar %50 → %46; 10 kHz %10 → 0).
   *
   * ⚠️ `undefined`/`null` = kart BİLDİRMEDİ (eski firmware / ESP bobini / kopuk) → arayüz kısa çizgi; `0` = SÜRÜLMÜYOR.
   * İkisini 0'a eşitlemek "sürülmüyor" yalanıdır.
   */
  dutyEtkin?: number | null;
}

// ─── Patient ─────────────────────────────────────────────────────────────────
export interface PatientSummary {
  name: string;
  species: string;
  breed: string;
  owner: string;
}

export interface Patient extends PatientSummary {
  id?: string;
  age?: string;
  weight?: string;
  vet_contact?: string;
  owner_email?: string;  // hasta sahibi e-postası (rapor gönderimi) — backend PatientInput ile aynı
  operator_email?: string;  // kaydı oluşturan hekim e-postası (klinik-içi "Benim Hastalarım" filtresi)
}

// ─── Session / Treatment ──────────────────────────────────────────────────────
export interface ActiveTreatment {
  mode: string;
  frequencyHz: number;
  /** REÇETE yoğunluğu: operatörün yazdığı sayı. Cihaza GÖNDERİLMEZ, yalnız kayda girer. */
  intensityMt: number;
  /**
   * ÖLÇÜLEN yoğunluk: STM'e bağlı MLX90393'ün SEANS BOYUNCA gördüğü TEPE |B| (mT).
   *
   * ⚠️ `null`/`undefined` = HİÇ ÖLÇÜM YOK (sensör bağlı değil ya da seans yok) — 0 DEĞİL.
   * Bu ayrım şart: 0 göstermek "ölçtük, alan yok" demektir; ölçüm yokken kart reçete
   * değerine düşer ve ETİKETİ de "(kayıt)" olur ki operatör hangisini gördüğünü bilsin.
   */
  measuredIntensityMt?: number | null;
  /** Ölçümün geldiği bobin (tek manyetik sensör bobin 6'ya eşlenik). */
  measuredIntensityCoil?: number | null;
  /**
   * SEANS BOYU en büyük ölçülen |B| (mT). `measuredIntensityMt` ANLIK (son saniyenin
   * tepesi); bu asla düşmez ve kayda giren sayıdır.
   * ⚠️ null = hiç ölçüm gelmedi (0.0 DEĞİL).
   */
  measuredPeakMt?: number | null;
  /**
   * D1.89 (İNCELEME-2 §10 #5): duty GÜDÜMLÜ seansın (AI Pro) TEMSİL duty'si (%, bobin 1 plan duty'si). mT DEĞİLDİR —
   * eskiden `intensityMt`e yazılıp "37 mT" görünüyordu. null/yok = elle seans (reçete `intensityMt`).
   */
  dutyTemsilYuzde?: number | null;
  remainingMin: number;
  elapsedSec: number;
  durationSec: number;
  isActive: boolean;
}

export interface TreatmentSession {
  id: string;
  date: string;
  patientName: string;
  mode: string;
  target: string;
  durationMin: number;
  status: "completed" | "running" | "stopped";
}

// ─── Notifications ────────────────────────────────────────────────────────────
export type NotificationLevel = "success" | "warning" | "error" | "info";

export interface AppNotification {
  id: number;
  /** Türkçe metin — HER ZAMAN dolu (eski sunucu / günlük / denetim). Arayüz yalnız `mesajlar` yoksa bunu gösterir. */
  message: string;
  /** I18N-P1 · sunucu `_bildir`: iki dilli metin. Arayüz KENDİ dilindekini gösterir; sunucu metnine göre dallanılmaz (KURALLAR §4.9). */
  mesajlar?: { tr?: string; en?: string };
  level: NotificationLevel;
  timestamp: string;
  read?: boolean;
}

// ─── System ──────────────────────────────────────────────────────────────────
export interface SystemInfo {
  softwareVersion: string;
  hardwareVersion: string;
  deviceId: string;
  startTime: string;
  uptime: string;
  totalSessions: number;
}

/** CANLI E-ALANI (2026-08-06) — tedavi sürerken vekil modelin canlı B/duty'den türettiği
 *  elektrik alanı. AI panelindeki E_cancer/E_healthy ile AYNI modelden gelir (tutarlılık).
 *  `null` = analiz bağlamı yok ya da seans pasif → UI bar'ı HİÇ göstermez (uydurma değer yok). */
export interface EFieldLive {
  /** Sağlıklı dokuda öngörülen alan. `null` = HESAPLANMADI (aşağıdaki neden alanları) → UI '—' (Y6). */
  healthy: number | null;
  /** Tümör/hedef dokuda öngörülen alan (`null` → '—') */
  cancer: number | null;
  /** Ortalama (`null` → '—') */
  avg: number | null;
  /** Hesaba giren ÇALIŞAN bobin sayısı (0 → bobinler durdu, değerler sıfır) */
  activeCoils: number;
  /** Modele verilen canlı girdiler — şeffaflık/teşhis için. B yalnız alanı ÖLÇÜLEN bobinlerden; `null` = ölçülmüyor. */
  achievedB_T: number | null;
  dutySum: number;
  /** ODK6: "cst" = ODAK seansında sürülen planın CST E'si (tepe |E|, V/m; hesaplanan, E ölçülmedi); yoksa vekil model ("yaklaşık"). */
  kaynak?: "cst" | "vekil";
  /** ODK10: `kaynak: "cst"` iken E'nin hesaplandığı ortam — "kuyu" = petri kuyusu SIVISI içinde (CST petri benzetimiyle doğrulandı),
   *  "hava" / yok = havada (ortamsız; doku içinde çok daha düşük). */
  ortam?: "kuyu" | "hava" | null;
  /** D1.76 · İG-5.83: E neden hesaplanmadı (yalnız-ek alanlar; eski backend göndermez). */
  egitimAraligiDisi?: boolean;
  bOlculmuyor?: boolean;
  egitimAraligiBilinmiyor?: boolean;
  /**
   * Y51 (sahip): toplam duty vekil modelin eğitim aralığı DIŞINDA — E yine gösterilir, yanında "eğitim aralığı dışı —
   * güvenilmez" etiketi. `dutyEgitimAraligi` = [alt, üst] (modelin referans örnekleminden). Eski backend göndermez.
   */
  dutyEgitimAraligiDisi?: boolean;
  dutyEgitimAraligi?: [number, number];
  /** Hesap zamanı (epoch sn) — tazelik denetimi için */
  ts: number;
}

// ─── Dashboard Snapshot ──────────────────────────────────────────────────────
export interface DashboardSnapshot {
  gateway: ConnectionState;
  mqtt: ConnectionState;
  /** Y230 (BE 3): ESP alt sistemi açık mı (backend `esp_etkin()`); yoksa (eski backend) KAPALI — `espEtkinMi`. */
  espEtkin?: boolean;
  /**
   * İNTERNET — CİHAZ AĞINDAN AYRI. Bu ürün internetsiz ÇALIŞIR; internet yalnız uzaktan
   * erişim içindir. ⚠️ Arayüz bunu NÖTR bilgi olarak gösterir, arıza rengiyle DEĞİL.
   * Eski davranış: internet yokluğu `gateway`i offline yapıp "Bağlantı" rozetini
   * kırmızıya çeviriyordu — hotspot açık ve tüm donanım çalışırken bile.
   */
  internet?: ConnectionState;
  stm: ConnectionState;
  patient: PatientSummary;
  activeTreatment: ActiveTreatment;
  coils: CoilStatus[];
  sessions: TreatmentSession[];
  notifications: AppNotification[];
  system: SystemInfo;
  /** Canlı E-alanı (yoksa null — bkz. EFieldLive) */
  eField?: EFieldLive | null;
  /** D1.81 · Y4: acil durdurma MANDALI (yoksa eski backend → bant çizilmez). */
  estopMandali?: EstopMandali | null;
  /** D1.E04 · İG-6.7: son ACİL DURDUR'un teyit durumu (backend `estop_teyit`). null = bu süreçte E-stop yok. */
  estopTeyit?: EstopTeyit | null;
  /** TD1: kart ↔ uygulama paket uyumu (backend `hardware.stm.uyum` → WS `stm_uyum`). Yoksa eski backend → bant çizilmez. */
  stmUyum?: StmUyum | null;
  /** CH4 · Y154: akım sensörü açık mı (backend `utils/akim_olcumu`, varsayılan KAPALI). Yalnız `true` iken akım çizilir. */
  akimOlcumu?: boolean;
}

/**
 * TD1 (tezgâh 2026-10-14): kartın yazılımı bu uygulama sürümüyle uyumlu mu. ⚠️ "BAĞLI" ile "UYUMLU" AYRI (bağlantı
 * göstergesi 2 durumlu kalır): kart konuşuyor olabilir ama paketi reddeden eski bir yazılım koşuyor olabilir.
 */
export interface StmUyum {
  /** true = uyumlu · false = KESİN uyumsuz (bobinler çalışmaz) · null = doğrulanamadı / henüz bilinmiyor */
  uyumlu: boolean | null;
  /** "FW-PAKET" (uyumsuz) · "FW-KIMLIK" (doğrulanamadı) · null = bant yok */
  kod?: string | null;
  /** Operatör metni (sade Türkçe + tek eylem) — backend `utils/stm32_kimlik.OPERATOR_METNI`. */
  mesaj?: string;
  /** Destek / servis ayrıntısı (teknik) — yalnız "Teknik ayrıntı" açılınca gösterilir. */
  ayrinti?: string;
}

/** D1.E04: "durdu" (`running:false`) ile "teyit edildi" AYRI — teyit yalnız backend'in teyidi ya da kartın tüm-sıfır ACK'i. */
export interface EstopTeyit {
  teyitli: boolean;
  /** "estop" (E-stop yanıtının teyidi) | "stm_ack" (kartın sonradan gelen tüm-sıfır ACK'i). */
  kaynak?: string;
  zaman?: number;
  /** Y227 (BE 2b): durdurma ANINDA bobin / seans var mıydı — false = boştaydı (teyitsiz düğme tutulmaz), null = okunamadı.
   *  Eski backend göndermez → eski davranış (teyitsizken düğme kalır). */
  calisiyordu?: boolean | null;
}

/**
 * ACİL DURDURMA MANDALI (D1.81 · sahip kararı Y4) — backend `utils/estop_mandali.durum()`.
 * `aktif` iken hiçbir START kabul edilmez; yalnız operatörün ayrı "Sıfırla" eylemi kaldırır ve sıfırlama
 * kendi başına BAŞLATMAZ. `neden` acil durdurmanın kaynağıdır ("manual", "stm_disconnected", "esp_alarm_…").
 */
export interface EstopMandali {
  aktif: boolean;
  neden?: string;
  /** Mandalın kurulduğu an (epoch sn). */
  zaman?: number;
  sifirlamaZamani?: number;
  nesil?: number;
  /** Y46: mandal önceki süreçten (diskten) yüklendi — "Sıfırla"ya basılmadan yeniden başlatıldı. */
  oncekiOturum?: boolean;
  /** 13 §2-d: `eylem` metni ZATEN "Sıfırla" adımını söylüyor mu (makine-okur; metin eşleşmesi gerekmesin). Eski sunucu: yok. */
  eylemSifirlaSoyler?: boolean;
  /** TD6 · K12: backend'in nedene özgü EYLEM metni (ör. kart reddinde duty / uyumsuzluk metni); boş → arayüz nedenden türetir. */
  eylem?: string;
  /** I18NI-A1.1: `eylem`in dil karşılıkları {tr, en} (WS yükü dil bilmez). Eski sunucu: yok → `eylem`. */
  eylemler?: Partial<Record<string, string>>;
  /** Y226 (BE 2a): mandalı PC'deki uygulamanın BOŞTAKİ kapanışı kurdu — alarm bandı yerine tek nötr satır. Eski sunucu: yok. */
  bostaKapanis?: boolean;
}

// ─── WebSocket live data ──────────────────────────────────────────────────────
export interface SensorDataPoint {
  magneticMt: number;
  objectTemp: number;
  ambientTemp: number;
  currentA: number;
  timestamp: number;
  /**
   * D1.90 · İG-6.90: noktanın geldiği yayındaki `measuredFields` (o an GERÇEKTEN ölçülen alanlar). Ölçülmeyen alan WS'te
   * 0.0 gelir; grafik onu ölçüm sanıp ekseni 0'a çekiyordu. `undefined` = alanı göndermeyen eski backend (eski davranış).
   */
  olculen?: string[];
}

// Per-coil history: last 2000 samples
export type CoilSensorHistory = Record<number, SensorDataPoint[]>;
