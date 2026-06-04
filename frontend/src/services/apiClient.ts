import { serviceConfig } from "@/services/config";

export async function apiGet<T>(path: string, fallback: T): Promise<T> {
  try {
    const url = `${serviceConfig.apiBaseUrl}${path}`;
    const response = await fetch(url);
    if (!response.ok) {
      console.error(`API GET Hatası [${response.status}]: ${url}`);
      return fallback;
    }
    return (await response.json()) as T;
  } catch (error) {
    console.error(`API GET İstek Başarısız: ${path}`, error);
    return fallback;
  }
}

export async function apiPost<T>(path: string, body: unknown, fallback: T): Promise<T> {
  try {
    const url = `${serviceConfig.apiBaseUrl}${path}`;
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    });
    if (!response.ok) {
      console.error(`API POST Hatası [${response.status}]: ${url}`);
      return fallback;
    }
    return (await response.json()) as T;
  } catch (error) {
    console.error(`API POST İstek Başarısız: ${path}`, error);
    return fallback;
  }
}
