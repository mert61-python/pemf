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
**Adım A2:** `health` + `favicon` + `discovery` → `servers/system_router.py`. **Önce characterization:** `tests/test_status_shapes.py` (5 uç response anahtar-kümesini dondurur — özellikle `/api/health` `atRestEncrypted`/`status`, kurulum-doğrulaması için kritik).

| Handler | Yol (DEĞİŞMEDİ) | Lazy-import erişimi | Not |
|---|---|---|---|
| `health_check` | `GET /api/health` | `state.core`, `_app_data_dir()` | auth-muaf (path bazlı → korunur); shape testli |
| `favicon` | `GET /favicon.ico` | — (trivial) | auth-muaf |
| `discovery_info` | `GET /api/discovery` | `_APP_VERSION` | auth-muaf; shape testli |

- **api_server.py:** −61 satır daha. `metrics` (`GET /metrics`) BIRAKILDI (ağır coupling: `_session_lock`/`_active_session`/`_ws_lock`/`_ws_clients` → ayrı observability pass).
- **Doğrulama:** compile+import OK · route-contract (67) · **response-shape golden (health/discovery/system_info/gateway/kpi)** · **92 test yeşil**.
**Adım A3:** `kpi/summary` (~100 satır SQL) → `system_router.py`. **Byte-exact** çıkarıldı (script ile; yalnız `@app`→`@router`, lazy-import ekle, `_get_treatment_db()`→`_api._get_treatment_db()` — SQL/mantık birebir). Shape zaten `test_status_shapes.py`'de kilitli. api_server.py **−102 satır**. 92 test yeşil.

- **Kalan system-ish:** yalnız `metrics` (`GET /metrics`; ağır coupling → ayrı observability pass'te).

## Faz B — `session_router` (2026-07-06) — SAFETY-ADJACENT, dikkatli

**Önce characterization:** `tests/test_session_char.py` (2 test) — `session/notes` fallback response shape + `session/active` read-only invariant. (`session/notes` mevcut testlerde KAPSANMIYORDU.)

**Adım B1:** `session/active` + `session/notes` (+ `SessionNotesPayload`) → **`servers/session_router.py`**. Byte-exact (script + **word-boundary** `_api.` prefix — `get_active_session` gibi fonksiyon adlarını mangle etmeden).

| Handler | Yol (DEĞİŞMEDİ) | Lazy-import erişimi |
|---|---|---|
| `get_active_session` | `GET /api/session/active` | `_session_lock`, `_active_session` (**salt-okunur**; global MUTATE yok — watchdog STOP korunur) |
| `save_session_notes` | `POST /api/session/notes` | `_app_data_dir`, `_session_lock`, `_active_session`, `_sensor_sample_buffer(_lock)`, treatment-DB |

- **"Dikkatli" ile YAKALANAN regresyon:** `test_live_state::test_get_active_session_is_readonly_on_expiry`, `api_server.get_active_session`'i **doğrudan** (HTTP değil) çağırıyordu → taşınınca `AttributeError`. Test yeni konuma yönlendirildi (`session_router.get_active_session`; davranış/güvenlik-invariant birebir). `test_session_char` state-bağımsız sağlam invariant'a çevrildi.
- **api_server.py:** −89 satır. **94 test yeşil** (route-contract + shape + session-char + 9 mevcut session testi).
- **⏸️ DEFERRED (human-review batch):** `session/start` (`:1114`, **bobin-sürer**) + `session/stop` (`:1680`) — safety-kritik; PR-boyu diff olarak ayrıca sunulacak (kullanıcı kararı).

> Gelecek cleanup (davranış-koruma DIŞI, ayrı iş): lazy-import edilen paylaşılan durum (`_live_state`, `_build_ws_snapshot`, `state`, `_active_session`, `_session_lock`) → `servers/live_state.py`/`session_state.py`'ye taşınmalı.
