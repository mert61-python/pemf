import type { MutableRefObject } from "react";
import type { KontrolHafizasi } from "@/context/AppNavContext";

/**
 * YS1d (Y320 4 · frontend-ci ESLint): AP-B1 Kontrol belleğine YAZIM. Bellek `AppNavProvider`ın `useRef`'idir (değişebilir) ama bileşene
 * bağlamdan (kanca) geldiği için React derleyicisi (`react-hooks/immutability`, HATA düzeyi) bileşen içindeki `bellek.current.x = …`
 * yazımını "kancadan dönen değer değiştirilemez" diye reddediyordu (AiProPanel, ControlScreen). Yazım bileşen DIŞINDA bu işlevde —
 * davranış AYNI: bellek yoksa (sağlayıcısız çizim / test) yazılmaz. Ayrı modül: `@/context/AppNavContext`i taklit eden testlerde de
 * gerçek kalsın.
 */
export function kontrolHafizasinaYaz<K extends keyof KontrolHafizasi>(
  bellek: MutableRefObject<KontrolHafizasi> | undefined,
  alan: K,
  deger: KontrolHafizasi[K],
): void {
  if (bellek) bellek.current[alan] = deger;
}
