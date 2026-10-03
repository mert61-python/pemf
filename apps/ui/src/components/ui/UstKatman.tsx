// Author: mertaygn, cglrgrkn
/**
 * ÜST KATMAN (native) — içerik OLDUĞU YERDE çizilir. Web karşılığı `UstKatman.web.tsx` (D1.E05 · İG-6.6).
 *
 * Native'de RN `Modal` ayrı bir pencere katmanıdır; kayan ACİL DURDUR'un onun üstüne taşınması bu dosyanın işi değildir
 * (native Modal örtüsü ayrıca ölçülmeli — aday raporu: emülatör yok, BİLİNMİYOR).
 */
import React from "react";

export function UstKatman({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return <>{children}</>;
}
