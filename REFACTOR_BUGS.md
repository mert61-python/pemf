# REFACTOR_BUGS — bulunan-ama-DÜZELTİLMEYEN bug'lar (ayrı iş)

Davranış-koruyan refactor ilkesi: refactor sırasında bir bug bulunursa **düzeltilmez** — buggy
davranış birebir korunur, burada işaretlenir, düzeltmesi AYRI iş olarak ele alınır.

## Faz A — system_router extraction (2026-07-06)
**Bulunan bug: YOK.** Taşınan 8 handler (system/info, gateway/status, dashboard-snapshot,
notifications/clear, health, favicon, discovery, kpi/summary) davranışı birebir korundu;
mantık/SQL hatası görülmedi. (kpi byte-exact taşındı → mantık değişmedi.)

## İlişkili (refactor DIŞI, önceki analizlerde saptanan — bu görevin kapsamı değil)
- `servers/api_server.py` 5× `str(e)` sızıntısı (satır ~977/1022/1876/1905/1924 civarı, extraction'larla kaydı) —
  **davranış-değiştiren güvenlik-fix** olarak AYRI ele alınacak (kullanıcı kararı: "ayrı güvenlik-fix").
  Bu bir refactor bug'ı DEĞİL; bilinçli-ertelenen ayrı iş. Bkz. REFACTOR_PLAN.md B3.

> Yeni bug bulundukça bu dosyaya eklenecek. Şu an refactor kaynaklı bug yok.
