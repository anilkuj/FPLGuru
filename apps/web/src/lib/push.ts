import { asJson } from "./api";

export function getVapidKey(base: string) {
  return fetch(`${base}/push/vapid-public-key`, { cache: "no-store" })
    .then(asJson<{ key: string }>)
    .then((r) => r.key);
}

export function urlBase64ToUint8Array(b64: string): Uint8Array<ArrayBuffer> {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

export async function subscribePush(apiBase: string, entryId: number, vapidKey: string) {
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(vapidKey),
  });
  const json = sub.toJSON() as { endpoint?: string; keys?: Record<string, string> };
  await fetch(`${apiBase}/entries/${entryId}/push/subscribe`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
  });
  return sub;
}

export async function unsubscribePush(apiBase: string, entryId: number) {
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (!sub) return;
  await fetch(`${apiBase}/entries/${entryId}/push/subscribe`, {
    method: "DELETE",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ endpoint: sub.endpoint }),
  });
  await sub.unsubscribe();
}
