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

> Yeni bug bulundukça bu dosyaya eklenecek. Şu an refactor kaynaklı bug yok.
