// Author: mertaygn, cglrgrkn
/**
 * `react-dom` için ASGARİ tip bildirimi (D1.E05). Paket kurulu (expo web bağımlılığı) ama `@types/react-dom` yok ve
 * bu ortamda paket İNDİRİLMEZ. Yalnız kullanılan yüzey bildirilir: `UstKatman.web.tsx` (`createPortal`) ve web
 * katman kapısı (`react-dom/client` `createRoot`). `@types/react-dom` eklenirse bu dosya silinir.
 */
declare module "react-dom" {
  import type { ReactNode, ReactPortal } from "react";
  export function createPortal(children: ReactNode, container: Element | DocumentFragment, key?: string | null): ReactPortal;
}

declare module "react-dom/client" {
  import type { ReactNode } from "react";
  export interface Root {
    render(children: ReactNode): void;
    unmount(): void;
  }
  export function createRoot(container: Element | DocumentFragment): Root;
}
