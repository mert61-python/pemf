import { supabase } from "./supabase";

/* Kullanıcının aboneliğinden hangi profillerin KURULABİLECEĞİNİ belirler (onaylı eşleme):
   home (Ev Sahibi) → herkes (temel/deneme) · vet (Veteriner) → aktif ücretli (Pro/Pro+)
   research (Araştırma) → 'research' eklentisi. Web'de kayıt olan e-posta = tek kaynak. */

export type Tier = "baslangic" | "pro" | "pro_plus";
export type Entitlement = {
  tier: Tier;
  status: string; // trialing | active | past_due | canceled
  addons: string[];
  email: string;
};

export async function fetchEntitlement(): Promise<Entitlement | null> {
  let user;
  try {
    const res = await supabase.auth.getUser();
    user = res.data.user;
  } catch {
    return null; // getUser bazı ağ yollarında REJECT eder (try/catch DIŞINDAYDI) → app'i bloke etme
  }
  if (!user) return null;
  let tier: Tier = "baslangic";
  let status = "trialing";
  let addons: string[] = [];
  try {
    const { data } = await supabase
      .from("subscriptions")
      .select("tier,status,addons")
      .eq("user_id", user.id)
      .maybeSingle();
    if (data) {
      tier = (["baslangic", "pro", "pro_plus"].includes(data.tier) ? data.tier : "baslangic") as Tier;
      status = data.status || "trialing";
      addons = Array.isArray(data.addons) ? data.addons : [];
    }
  } catch {
    /* tablo/ağ yoksa deneme varsayılanı — app'i bloke etme */
  }
  return { tier, status, addons, email: user.email || "" };
}

/** İzinli profil id'leri (home/vet/research). FREE_MODE'da bu çağrılmaz (hepsi açık). */
export function allowedProfileIds(e: Entitlement | null): Set<string> {
  const s = new Set<string>(["home"]); // Ev Sahibi herkese (temel/deneme)
  if (!e) return s;
  const active = e.status === "active" || e.status === "trialing";
  if (active && (e.tier === "pro" || e.tier === "pro_plus")) s.add("vet");
  if (active && e.addons.includes("research")) s.add("research");
  return s;
}
