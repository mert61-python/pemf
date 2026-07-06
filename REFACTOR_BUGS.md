# REFACTOR_BUGS — bulunan-ama-DÜZELTİLMEYEN bug'lar (ayrı iş)

Davranış-koruyan refactor ilkesi: refactor sırasında bir bug bulunursa **düzeltilmez** — buggy
davranış birebir korunur, burada işaretlenir, düzeltmesi AYRI iş olarak ele alınır.

## Faz A — system_router extraction (2026-07-06)
**Bulunan bug: YOK.** Taşınan 8 handler (system/info, gateway/status, dashboard-snapshot,
notifications/clear, health, favicon, discovery, kpi/summary) davranışı birebir korundu;
mantık/SQL hatası görülmedi. (kpi byte-exact taşındı → mantık değişmedi.)

## İlişkili (refactor DIŞI güvenlik-fix — ✅ DÜZELTİLDİ)
- **B3 `str(e)` istemci sızıntısı — ✅ DÜZELTİLDİ** (ayrı güvenlik-fix commit'i, kullanıcı kararı).
  5 nokta: api_server (AI-öneri, hardware/command, ai/log POST+GET) + session_router (notes).
  İstemciye giden `detail=str(e)` → generic mesaj; loglama eksikse `logging.exception` eklendi
  (sunucu-tarafı tam traceback). **DAVRANIŞ DEĞİŞİKLİĞİ:** response `detail` DEĞERİ değişti
  (ham exception → generic); HTTP status + response SHAPE (status/detail anahtarları) KORUNDU.
  Refactor DEĞİL (davranış-koruma dışı, bilinçli). 94 test yeşil.

## Faz F — Frontend F3 typing sırasında keşfedilen (refactor-ÖNCESİ) → ✅ DÜZELTİLDİ (kullanıcı talebi, commit `pf@cf43816`)

- **`SystemInfoPanel` — "Çalışma Süresi" kalıcı `00:00:00` (latent UI bug).**
  Panel `apiGet("/system/info").uptime` okuyordu (`if (d?.uptime) setUptime(d.uptime)`),
  fakat backend `/api/system/info` **`uptime` döndürmüyor** (dönen 7 anahtar: softwareVersion,
  hardwareVersion, deviceId, pairingCode, tunnelUrl, stmConnected, timestamp — `test_status_shapes.py`
  golden-shape ile kilitli). → `d?.uptime` daima `undefined` → `uptime` state hiç güncellenmez →
  panelde "Çalışma Süresi" hep `00:00:00`. **Refactor-öncesi mevcut** (system_router extraction
  byte-exact idi, bug'ı üretmedi).
  - **Düzeltme araştırması (önemli düzeltme):** ilk önerilen "panel `snapshot.system.uptime` kullansın"
    da YANLIŞTI — WS snapshot'ın `system` dict'i de `uptime` içermiyor; onun yerine **`startTime`**
    (process başlangıç ISO'su, `live_state.py:99`) var. Tek uptime-verisi `startTime`.
  - **UYGULANAN FIX (davranış-değiştiren, bilinçli):** uptime artık WS snapshot'taki `system.startTime`'dan
    istemci tarafında hesaplanır — saf `formatUptime()` util (`src/utils/uptime.ts`, 6 jest testi,
    TZ-bağımsız) + 1sn ticker. **Backend/EXE sözleşmesi değişmedi, rebuild gerekmedi.** `stmConnected`
    mount'ta bir kez okunur (mevcut görünür davranış korundu); ölü 10sn `/system/info` poll kaldırıldı
    (yalnızca ölü `d.uptime`'a hizmet ediyordu). tsc temiz, 36 jest yeşil.
  - **Not:** bu bir REFACTOR değil — bilinçli **davranış değişikliği** (kullanıcı "uptime bug'ı" düzelt dedi).
    Uptime artık gerçek elapsed gösterir (önce hep 00:00:00 idi).

> Yeni bug bulundukça bu dosyaya eklenecek. **Refactor KAYNAKLI bug yok** (yukarıdaki F3 bulgusu refactor-öncesi/frontend, tip-inceleme sırasında görüldü; kullanıcı talebiyle ayrı bug-fix olarak düzeltildi).
