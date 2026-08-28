"use client";

import { useEffect, useState } from "react";

import { getAlerts } from "@/lib/api";
import { getStoredEntryId } from "@/lib/entry";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function NavAlerts() {
  const [unseen, setUnseen] = useState(0);

  useEffect(() => {
    const id = getStoredEntryId();
    if (id == null) return;
    const tick = () =>
      getAlerts(API, id)
        .then((f) => setUnseen(f.unseen))
        .catch(() => undefined);
    tick();
    const t = setInterval(tick, 60000);
    return () => clearInterval(t);
  }, []);

  return (
    <a href="/alerts">
      Alerts
      {unseen > 0 && (
        <span className="ml-1 rounded-full bg-red-500 px-1.5 text-xs text-white">
          {unseen}
        </span>
      )}
    </a>
  );
}
