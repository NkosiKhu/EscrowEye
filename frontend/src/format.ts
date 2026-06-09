export function asArray<T>(value: unknown, key: string): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object" && key in value) {
    const nested = (value as Record<string, unknown>)[key];
    return Array.isArray(nested) ? (nested as T[]) : [];
  }
  return [];
}

export function tinybarToHbar(tinybar?: number | null) {
  if (!tinybar) return "0";
  return (tinybar / 100_000_000).toLocaleString(undefined, {
    maximumFractionDigits: 4,
  });
}

export function hbarToTinybar(hbar: string) {
  const value = Number.parseFloat(hbar || "0");
  return Math.round((Number.isFinite(value) ? value : 0) * 100_000_000);
}

export function formatDate(value?: string) {
  if (!value) return "No timestamp";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function statusLabel(status?: string) {
  return (status ?? "unknown").replace(/_/g, " ");
}

export function truncateMiddle(value?: string | null, keep = 10) {
  if (!value) return "Pending";
  if (value.length <= keep * 2 + 3) return value;
  return `${value.slice(0, keep)}...${value.slice(-keep)}`;
}
