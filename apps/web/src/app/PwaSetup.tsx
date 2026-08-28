"use client";

import { useEffect, useState } from "react";

type BIPEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<unknown> };

export function PwaSetup() {
  const [deferred, setDeferred] = useState<BIPEvent | null>(null);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    }
    const onBip = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BIPEvent);
    };
    window.addEventListener("beforeinstallprompt", onBip);
    return () => window.removeEventListener("beforeinstallprompt", onBip);
  }, []);

  if (!deferred) return null;
  return (
    <button
      className="rounded border px-2 py-1 text-sm"
      onClick={() => {
        deferred.prompt();
        setDeferred(null);
      }}
    >
      Install app
    </button>
  );
}
