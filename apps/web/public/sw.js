const SHELL = "fplguru-shell-v1";
const RUNTIME = "fplguru-runtime-v1";
const SHELL_URLS = ["/", "/squad", "/fdr", "/live", "/alerts"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches
      .open(SHELL)
      .then((c) => c.addAll(SHELL_URLS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== SHELL && k !== RUNTIME).map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const { request } = e;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  // API GETs: network-first, fall back to the last good response
  if (
    url.pathname.startsWith("/entries/") ||
    url.pathname.startsWith("/xp") ||
    url.pathname.startsWith("/fdr") ||
    url.pathname.startsWith("/gameweeks")
  ) {
    e.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(RUNTIME).then((c) => c.put(request, copy));
          return res;
        })
        .catch(() => caches.match(request)),
    );
    return;
  }

  // everything else (shell + static): cache-first, then network
  e.respondWith(
    caches.match(request).then(
      (hit) =>
        hit ||
        fetch(request)
          .then((res) => {
            if (res.ok && url.origin === self.location.origin) {
              const copy = res.clone();
              caches.open(RUNTIME).then((c) => c.put(request, copy));
            }
            return res;
          })
          .catch(() => caches.match("/")),
    ),
  );
});

self.addEventListener("push", (e) => {
  let data = {};
  try {
    data = e.data ? e.data.json() : {};
  } catch {
    data = {};
  }
  const title = data.title || "FPLGuru";
  e.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || "",
      tag: data.tag || "fplguru",
      data: { url: data.url || "/alerts" },
    }),
  );
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const target = (e.notification.data && e.notification.data.url) || "/alerts";
  e.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((cs) => {
      for (const c of cs) if ("focus" in c) return c.navigate(target).then(() => c.focus());
      return self.clients.openWindow(target);
    }),
  );
});
