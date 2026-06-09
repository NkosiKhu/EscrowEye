export function readStored<T>(key: string): T | null {
  const stored = localStorage.getItem(key);
  return stored ? (JSON.parse(stored) as T) : null;
}
