const DEFAULT_PRESERVED_KEYS = ["session", "agent_mode", "control"];

export function preserveQueryParams(
  to: string,
  currentSearch: string,
  keys: string[] = DEFAULT_PRESERVED_KEYS,
): string {
  const hashIndex = to.indexOf("#");
  const withoutHash = hashIndex >= 0 ? to.slice(0, hashIndex) : to;
  const hash = hashIndex >= 0 ? to.slice(hashIndex) : "";
  const qIndex = withoutHash.indexOf("?");
  const pathname = qIndex >= 0 ? withoutHash.slice(0, qIndex) : withoutHash;
  const targetParams = new URLSearchParams(qIndex >= 0 ? withoutHash.slice(qIndex + 1) : "");
  const currentParams = new URLSearchParams(currentSearch);

  for (const key of keys) {
    const currentValue = currentParams.get(key);
    if (currentValue !== null && !targetParams.has(key)) {
      targetParams.set(key, currentValue);
    }
  }

  const query = targetParams.toString();
  return `${pathname}${query ? `?${query}` : ""}${hash}`;
}
