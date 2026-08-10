// Author: mertaygn, cglrgrkn
//! PEMF Vet Client launcher — çekirdek (UI'dan bağımsız).
//!
//! Sözleşme: `docs/LAUNCHER_SPEC.md`.
//!
//! Akış:
//! ```text
//! manifest indir → platform runtime'ını SEÇ (fallback yok) → base + profil paketini indir
//!   → SHA256 doğrula → zip-slip korumalı aç → backend'i başlat → /api/health bekle → tarayıcı
//! ```
//!
//! Bu crate UI içermez ve ağ katmanından bağımsızdır; böylece indirme/doğrulama/
//! kurulum mantığı headless olarak test edilebilir.

pub mod disk;
pub mod firewall;
pub mod auth;
pub mod backend;
pub mod extract;
pub mod flow;
pub mod install;
pub mod manifest;
pub mod net;
pub mod platform;
pub mod secret_store;
pub mod verify;

pub use manifest::{is_newer, LauncherInfo, Manifest, Package};
