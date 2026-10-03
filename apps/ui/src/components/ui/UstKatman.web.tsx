// Author: mertaygn, cglrgrkn
/**
 * ÜST KATMAN (web) — içerik `document.body`'ye PORTAL ile çizilir (D1.E05 · İG-6.6).
 *
 * ÖLÇÜLEN KUSUR (aday doğrulaması İG-6.6, gerçek web paketi + headless Chrome): react-native-web her açık `Modal`'ı
 * `document.body`'ye eklenen `position: fixed; z-index: 9999` tam ekran bir kapsayıcıyla çizer. Kayan ACİL DURDUR ise
 * uygulama kökünün içinde, her RN-web `View`'unun açtığı `z-index: 0` yığın bağlamında kalıyordu → kendi `z-index`'i ne
 * olursa olsun Modal'ın ALTINDA: Seans Detayı açıkken düğmenin merkezindeki eleman Modal'dı, E-stop isteği 0, bobin
 * sürmeye devam etti. Body düzeyindeki portal + `GES_WEB_KATMAN` (bkz. GlobalEmergencyStop) her Modal'ın üstündedir.
 */
import React from "react";
import { createPortal } from "react-dom";

export function UstKatman({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  if (typeof document === "undefined" || !document.body) return <>{children}</>;
  return createPortal(children, document.body);
}
