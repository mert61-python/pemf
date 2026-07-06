# REFACTOR_LOG — ne nereye taşındı (eşleme günlüğü)

Davranış-koruyan refactor. Her adım: kaynak → hedef + doğrulama. **Sıfır davranış değişikliği** ilkesi.

## Faz 0 — Güvenlik ağı (2026-07-06, commit `4cea676`)
- `REFACTOR_PLAN.md` + `tests/test_route_contract.py` (67-route golden-master). **Kod değişmedi** — yalnız test + plan. 87 test yeşil.

## Faz A — `system_router` (2026-07-06)

**Adım A1:** 4 status/sistem ucu `api_server.py` → **`servers/system_router.py`** (yeni `APIRouter`).

| Handler | Yol (DEĞİŞMEDİ) | Paylaşılan-state erişimi (lazy-import `servers.api_server`) |
|---|---|---|
| `system_info` | `GET /api/system/info` | `_APP_VERSION`, `state.core` |
| `gateway_status` | `GET /api/gateway/status` | `_live_state`, `_live_state_lock`, `state.core` |
| `get_dashboard_snapshot` | `GET /api/dashboard-snapshot` | `_build_ws_snapshot()` |
| `clear_notifications` | `POST /api/notifications/clear` | `_live_state`, `_live_state_lock`, `_ws_broadcast_sync()` |

- **Yöntem:** paylaşılan runtime durumu çağrı-zamanı `from servers import api_server as _api` ile okunur (circular import yok; api_server router'ı include eder, router app'i yalnız handler çağrılınca import eder).
- **api_server.py:** −77 satır (2206 → 2129). `include_router(system_router)` eklendi.
- **Doğrulama:** `py_compile` + import OK · **route-contract golden (67 route) birebir** · **87 test yeşil**.
- **Kalan system route'ları** (sonraki adımlar): `health` (`:674`), `discovery` (`:757`) — **auth-muaf + kurulum-doğrulama → dikkatli**; `kpi/summary` — ayrı domain, `_get_treatment_db` bağımlı.

> Gelecek cleanup (davranış-koruma DIŞI, ayrı iş): lazy-import edilen paylaşılan durum (`_live_state`, `_build_ws_snapshot`, `state`) → `servers/live_state.py`'ye taşınmalı.
