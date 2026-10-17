import { useState } from 'react';

const FONT_KEY = 'saq_font';

function readLargeFont(): boolean {
  try {
    return localStorage.getItem(FONT_KEY) === 'large';
  } catch {
    return false;
  }
}

function applyLargeFont(large: boolean): void {
  if (large) document.documentElement.dataset.font = 'large';
  else delete document.documentElement.dataset.font;
}

/** Applies stored display preferences before the first render, so there is no flash of the default size. */
export function applyStoredPreferences(): void {
  applyLargeFont(readLargeFont());
}

/** Large-font switch (scale in tokens.css). The choice is remembered on this device. */
export function useLargeFont(): [boolean, (large: boolean) => void] {
  const [large, setLarge] = useState(readLargeFont);
  const update = (next: boolean) => {
    setLarge(next);
    applyLargeFont(next);
    try {
      if (next) localStorage.setItem(FONT_KEY, 'large');
      else localStorage.removeItem(FONT_KEY);
    } catch {
      // Persistence is best-effort.
    }
  };
  return [large, update];
}

/** Collapsed <details> would print empty: open them for the print job and restore afterwards. */
export function openDetailsForPrint(): void {
  let closed: HTMLDetailsElement[] = [];
  window.addEventListener('beforeprint', () => {
    closed = Array.from(document.querySelectorAll<HTMLDetailsElement>('details:not([open])'));
    closed.forEach((el) => (el.open = true));
  });
  window.addEventListener('afterprint', () => {
    closed.forEach((el) => (el.open = false));
    closed = [];
  });
}
