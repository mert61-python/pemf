/* tests/firmware_host/esp8266 — ArduinoJson taklidi (1-G · Y48 komut aparatı). Yalnız 8266 `processControlCommand`'ın
 * kullandığı yüzey: `doc["k"] | "varsayılan"`, `doc.containsKey("k")`, `doc["k"].as<float|long|int>()`,
 * `doc["k"].is<float|int>()`. Belge senaryodan anahtar=değer olarak kurulur (`komut_kosum.cpp`); JSON ayrıştırma YOK. */
#ifndef PEMF_HOST_ARDUINOJSON_H
#define PEMF_HOST_ARDUINOJSON_H

#include <stdlib.h>
#include <string.h>

#include <map>
#include <string>

class JsonDeger {
 public:
  JsonDeger() : _var(false), _sayi(false) {}
  JsonDeger(const std::string &metin, bool sayi) : _var(true), _sayi(sayi), _metin(metin) {}
  const char *operator|(const char *varsayilan) const { return (_var && !_sayi) ? _metin.c_str() : varsayilan; }
  template <typename T> T as() const { return _var ? (T)strtod(_metin.c_str(), nullptr) : (T)0; }
  template <typename T> bool is() const;

 private:
  bool _var, _sayi;
  std::string _metin;
};

template <> inline bool JsonDeger::is<float>() const {
  return _var && _sayi && strpbrk(_metin.c_str(), ".eE") != nullptr;
}
template <> inline bool JsonDeger::is<int>() const {
  return _var && _sayi && strpbrk(_metin.c_str(), ".eE") == nullptr;
}

class JsonDocument {
 public:
  void koy(const std::string &anahtar, const std::string &deger, bool sayi) { _alan[anahtar] = JsonDeger(deger, sayi); }
  bool containsKey(const char *anahtar) const { return _alan.count(anahtar) != 0; }
  /* Başvuru döner: `const char* s = doc["k"] | "";` belgedeki dizeyi göstermeli (gerçek ArduinoJson gibi) — geçici
   * kopyanın `c_str()`'ı ifade sonunda sarkardı. */
  const JsonDeger &operator[](const char *anahtar) const {
    static const JsonDeger bos;
    auto it = _alan.find(anahtar);
    return it == _alan.end() ? bos : it->second;
  }
  void clear() { _alan.clear(); }

 private:
  std::map<std::string, JsonDeger> _alan;
};

template <size_t N> class StaticJsonDocument : public JsonDocument {};

#endif /* PEMF_HOST_ARDUINOJSON_H */
