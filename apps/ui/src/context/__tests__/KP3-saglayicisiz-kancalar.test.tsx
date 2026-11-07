/**
 * KP-3 C · bağlam kancaları SAĞLAYICI DIŞINDA kullanılırsa AÇIK hata verir (sessizce `undefined` bağlamla çalışıp "oturum yok" / "operatör
 * yok" gibi YANLIŞ bir duruma düşmez) — useAuth · useEntitlement · useOperator · useUserMode. Her biri kendi iletisiyle.
 * GERÇEK: bağlam modülleri; ağ çağrısı YOK (sağlayıcı hiç çizilmez).
 */
import { renderHook } from "@testing-library/react-native";

import { useAuth } from "@/context/AuthContext";
import { useEntitlement } from "@/context/EntitlementContext";
import { useOperator } from "@/context/OperatorContext";
import { useUserMode } from "@/context/UserModeContext";

beforeEach(() => {
  jest.spyOn(console, "error").mockImplementation(() => undefined); // React'in sınır uyarısı (beklenen hata)
});
afterEach(() => jest.restoreAllMocks());

it.each<[string, () => unknown, string]>([
  ["useAuth", () => useAuth(), "useAuth must be used within AuthProvider"],
  ["useEntitlement", () => useEntitlement(), "useEntitlement must be used within EntitlementProvider"],
  ["useOperator", () => useOperator(), "useOperator, OperatorProvider içinde kullanılmalı"],
  ["useUserMode", () => useUserMode(), "useUserMode must be used within a UserModeProvider"],
])("%s sağlayıcısız → açık hata", (_ad, kanca, ileti) => {
  expect(() => renderHook(kanca)).toThrow(ileti);
});
