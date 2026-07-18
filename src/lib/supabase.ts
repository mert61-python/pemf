import { createClient } from "@supabase/supabase-js";

/* Client (launcher) Supabase — web/mobil ile AYNI hesap. Public anahtarlar gömülü (RLS korumalı,
   istemci paketinde zaten açık → güvenli). Oturum Tauri webview localStorage'ında kalıcı. */
const SUPABASE_URL = "https://wmsxonunkphjeregpvuj.supabase.co";
const SUPABASE_ANON = "sb_publishable_D2SaRML_PIhRtr3kqlXxaw_1cS75GKT";

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON, {
  auth: { persistSession: true, autoRefreshToken: true },
});
