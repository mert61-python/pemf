/**
 * KP-3 C · services/gorselKucult kapsanmayan kolları — her test bir DAVRANIŞ iddiası (gorselKucult.test.ts düzeneğinin aynısı):
 *  - Çözülen görüntü 0 boyutluysa ya da tuval 2B bağlamı verilemiyorsa ORİJİNAL dosya gider (fail-open, analiz yine yapılır).
 *  - `createImageBitmap` YOKSA (eski WebView2) klasik `<img>` yoluyla çözülüp küçültülür; nesne URL'si HER durumda bırakılır.
 *  - `<img>` çözülemezse (onerror) orijinal dosya gider, nesne URL'si yine bırakılır.
 * SAHTE (en alt kat): createImageBitmap / Image / document.createElement('canvas') / URL nesne-URL'leri / File.
 */
import { KUCULTME_ESIGI_BAYT, webIcinKucult } from "@/services/gorselKucult";

const g = globalThis as Record<string, unknown>;

function sahteDosya(ad: string, bayt: number, tur = "image/jpeg"): File {
  return Object.assign({ size: bayt, type: tur } as Blob, { name: ad, lastModified: 0, webkitRelativePath: "" }) as unknown as File;
}

function tuvalKur(opts: { ctxYok?: boolean; ciktiBayt?: number }) {
  g.document = {
    createElement: () => ({
      width: 0,
      height: 0,
      getContext: () => (opts.ctxYok ? null : { drawImage: () => {} }),
      toBlob: (cb: (b: Blob | null) => void) => cb({ size: opts.ciktiBayt ?? 1000, type: "image/jpeg" } as Blob),
    }),
  };
  g.File = class {
    size: number;
    type: string;
    name: string;
    constructor(parts: Blob[], ad: string, o: { type: string }) {
      this.size = parts[0]?.size ?? 0;
      this.type = o.type;
      this.name = ad;
    }
  };
}

const ilkURL = { create: URL.createObjectURL, revoke: URL.revokeObjectURL };
let birakilan: string[];
beforeEach(() => {
  birakilan = [];
  (URL as unknown as Record<string, unknown>).createObjectURL = () => "blob:kp3-1";
  (URL as unknown as Record<string, unknown>).revokeObjectURL = (u: string) => birakilan.push(u);
});
afterEach(() => {
  for (const k of ["createImageBitmap", "document", "Image"]) delete g[k];
  (URL as unknown as Record<string, unknown>).createObjectURL = ilkURL.create;
  (URL as unknown as Record<string, unknown>).revokeObjectURL = ilkURL.revoke;
});

const BUYUK = KUCULTME_ESIGI_BAYT * 4;

it("0 boyutlu görüntü ya da 2B bağlam yok → orijinal dosya", async () => {
  tuvalKur({});
  g.createImageBitmap = async () => ({ width: 0, height: 3000 });
  const f = sahteDosya("kedi.png", BUYUK, "image/png");
  await expect(webIcinKucult(f)).resolves.toBe(f);
  g.createImageBitmap = async () => ({ width: 4000, height: 3000 });
  tuvalKur({ ctxYok: true });
  await expect(webIcinKucult(f)).resolves.toBe(f);
});

it("createImageBitmap yoksa <img> yoluyla küçültülür; nesne URL'si bırakılır", async () => {
  tuvalKur({ ciktiBayt: 2000 });
  g.Image = class {
    width = 4000;
    height = 3000;
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    set src(_u: string) {
      queueMicrotask(() => this.onload?.());
    }
  };
  const sonuc = await webIcinKucult(sahteDosya("kedi.png", BUYUK, "image/png"));
  expect(sonuc.name).toBe("kedi.jpg");
  expect(sonuc.size).toBe(2000);
  expect(birakilan).toEqual(["blob:kp3-1"]);
});

it("<img> çözülemezse orijinal dosya; nesne URL'si yine bırakılır", async () => {
  tuvalKur({});
  g.Image = class {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    set src(_u: string) {
      queueMicrotask(() => this.onerror?.());
    }
  };
  const f = sahteDosya("bozuk.png", BUYUK, "image/png");
  await expect(webIcinKucult(f)).resolves.toBe(f);
  expect(birakilan).toEqual(["blob:kp3-1"]);
});
