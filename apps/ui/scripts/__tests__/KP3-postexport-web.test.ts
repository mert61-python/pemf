/**
 * KP-3 C · scripts/postexport-web.js — `expo export` sonrası dist/index.html düzeltmesi (her test bir DAVRANIŞ iddiası):
 *  - dist/index.html yoksa açık hata + çıkış 1 (sessizce "başarılı" geçmez).
 *  - Expo'nun lang="en" (çift ya da TEK tırnak, bölge ekli) değeri lang="tr" olur; lang hiç yoksa eklenir.
 *  - description ve favicon yoksa </head>'den hemen önce eklenir; varsa İKİNCİ kez eklenmez.
 *  - Zaten düzeltilmiş dosya YENİDEN YAZILMAZ (değişiklik gerekmedi iletisi).
 * GERÇEK: betiğin kendisi + dosya sistemi (her test kendi geçici dizininde; depo / dist'e dokunulmaz). SAHTE: process.exit.
 */
import fs from "fs";
import os from "os";
import path from "path";

let dizin: string;
let ilkCwd: string;
let cikis: jest.SpyInstance;
let gunluk: jest.SpyInstance;
let hata: jest.SpyInstance;

beforeEach(() => {
  ilkCwd = process.cwd();
  dizin = fs.mkdtempSync(path.join(os.tmpdir(), "kp3-postexport-"));
  process.chdir(dizin);
  cikis = jest.spyOn(process, "exit").mockImplementation(((k?: number) => { throw new Error(`exit:${k}`); }) as never);
  gunluk = jest.spyOn(console, "log").mockImplementation(() => undefined);
  hata = jest.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  process.chdir(ilkCwd);
  fs.rmSync(dizin, { recursive: true, force: true });
  jest.restoreAllMocks();
});

const kos = () => jest.isolateModules(() => { require("../postexport-web.js"); });
const yaz = (html: string) => {
  fs.mkdirSync("dist", { recursive: true });
  fs.writeFileSync(path.join("dist", "index.html"), html);
};
const oku = () => fs.readFileSync(path.join("dist", "index.html"), "utf8");

it("dist/index.html yoksa açık hata + çıkış 1", () => {
  expect(kos).toThrow("exit:1");
  expect(cikis).toHaveBeenCalledWith(1);
  expect(String(hata.mock.calls[0][0])).toContain("dist/index.html YOK");
});

it.each([
  ['<html lang="en"><head><title>x</title></head><body></body></html>'],
  ["<html lang='en-US'><head><title>x</title></head><body></body></html>"],
  ["<html><head><title>x</title></head><body></body></html>"],
])("lang tr olur, description + favicon </head>'den önce eklenir: %s", (html) => {
  yaz(html);
  kos();
  const h = oku();
  expect(h.startsWith('<html lang="tr">')).toBe(true);
  expect(h).toMatch(/<meta name="description" content="[^"]+">\s*\n\s*<link rel="icon" href="\/favicon.ico">\n<\/head>/);
  expect(String(gunluk.mock.calls[0][0])).toContain("uygulandı");
});

it("description / favicon varsa ikinci kez eklenmez; tamamen düzeltilmiş dosya yeniden YAZILMAZ", () => {
  const hazir = '<html lang="tr"><head><meta name="description" content="d"><link rel="icon" href="/favicon.ico"></head></html>';
  yaz(hazir);
  const once = fs.statSync(path.join("dist", "index.html")).mtimeMs;
  const yazim = jest.spyOn(fs, "writeFileSync");
  kos();
  expect(yazim).not.toHaveBeenCalled();
  expect(oku()).toBe(hazir);
  expect(fs.statSync(path.join("dist", "index.html")).mtimeMs).toBe(once);
  expect(String(gunluk.mock.calls[0][0])).toContain("değişiklik gerekmedi");
});
