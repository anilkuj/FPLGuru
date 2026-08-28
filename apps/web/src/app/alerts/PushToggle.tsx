"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui";
import { getStoredEntryId } from "@/lib/entry";
import { getVapidKey, subscribePush, unsubscribePush } from "@/lib/push";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function PushToggle() {
  const [state, setState] = useState<"unknown" | "unsupported" | "off" | "on">("unknown");
  const [entryId, setEntryId] = useState<number | null>(null);

  useEffect(() => {
    setEntryId(getStoredEntryId());
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setState("unsupported");
      return;
    }
    navigator.serviceWorker.ready
      .then((reg) => reg.pushManager.getSubscription())
      .then((sub) => setState(sub ? "on" : "off"))
      .catch(() => setState("off"));
  }, []);

  if (state === "unknown" || state === "unsupported" || entryId == null) return null;

  return (
    <Button
      size="sm"
      variant="outline"
      onClick={async () => {
        if (state === "on") {
          await unsubscribePush(API, entryId);
          setState("off");
          return;
        }
        if ((await Notification.requestPermission()) !== "granted") return;
        const key = await getVapidKey(API);
        if (!key) {
          alert("Push is not configured on the server yet.");
          return;
        }
        await subscribePush(API, entryId, key);
        setState("on");
      }}
    >
      {state === "on" ? "Disable notifications" : "Enable notifications"}
    </Button>
  );
}
