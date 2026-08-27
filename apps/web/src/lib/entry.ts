const KEY = "fplguru.entryId";

export function getStoredEntryId(): number | null {
  try {
    const v =
      typeof window !== "undefined" ? window.localStorage.getItem(KEY) : null;
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}

export function setStoredEntryId(id: number): void {
  try {
    window.localStorage.setItem(KEY, String(id));
  } catch {
    /* private mode / storage disabled — ignore */
  }
}
