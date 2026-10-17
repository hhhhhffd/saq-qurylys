const RELOAD_KEY = 'saq_build_reload_at';
// A second failure this soon after a reload means the server itself is broken: stop reloading, show the message.
const RELOAD_GUARD_MS = 15_000;

/** After a redeploy the chunks of the previous build are gone, so a tab opened before it can no longer load pages. */
export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /dynamically imported module|Importing a module script failed|Unable to preload CSS/i.test(message);
}

/** Reload to get the current build; false when a reload already happened moments ago or cannot be guarded. */
export function reloadForNewBuild(): boolean {
  try {
    const last = Number(sessionStorage.getItem(RELOAD_KEY) ?? 0);
    if (Date.now() - last < RELOAD_GUARD_MS) return false;
    sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
  } catch {
    // Without storage a reload could loop for ever; the message with its button is the safe fallback.
    return false;
  }
  window.location.reload();
  return true;
}
