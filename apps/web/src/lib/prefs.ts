export function getPref(key: string, fallback: number): number {
  try {
    const v =
      typeof window !== "undefined"
        ? window.localStorage.getItem(`fplguru.${key}`)
        : null;
    const n = v ? Number(v) : NaN;
    return Number.isFinite(n) ? n : fallback;
  } catch {
    return fallback;
  }
}

export function setPref(key: string, value: number): void {
  try {
    window.localStorage.setItem(`fplguru.${key}`, String(value));
  } catch {
    /* ignore */
  }
}

export function getPrefStr<T extends string>(key: string, fallback: T): T {
  try {
    const v =
      typeof window !== "undefined"
        ? window.localStorage.getItem(`fplguru.${key}`)
        : null;
    return (v as T) ?? fallback;
  } catch {
    return fallback;
  }
}

export function setPrefStr(key: string, value: string): void {
  try {
    window.localStorage.setItem(`fplguru.${key}`, value);
  } catch {
    /* ignore */
  }
}
