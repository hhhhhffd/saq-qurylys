import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';

/** The value, delayed until it has stopped changing for `wait` ms. Returns `[debounced, cancel]`; the first value is immediate. */
export function useDebouncedValue<T>(value: T, wait: number): [T, () => void] {
  const [debounced, setDebounced] = useState(value);
  const timer = useRef<number | undefined>(undefined);
  const mounted = useRef(false);

  const cancel = useCallback(() => {
    window.clearTimeout(timer.current);
    timer.current = undefined;
  }, []);

  useEffect(() => {
    // The initial value is already in state; only later changes are debounced.
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    timer.current = window.setTimeout(() => setDebounced(value), wait);
    return cancel;
  }, [value, wait, cancel]);

  return [debounced, cancel];
}

export type DebouncedCallback<Args extends unknown[]> = ((...args: Args) => void) & {
  /** runs the pending call now */
  flush: () => void;
  /** drops the pending call */
  cancel: () => void;
};

// Plain closures instead of refs: the debouncer is created once per `delay` and fed the latest callback by an effect.
function createDebouncer<Args extends unknown[]>(delay: number) {
  let callback: (...args: Args) => void = () => undefined;
  let timer: number | undefined;
  let pending: Args | null = null;

  const cancel = () => {
    window.clearTimeout(timer);
    timer = undefined;
    pending = null;
  };
  const flush = () => {
    const args = pending;
    if (!args) return;
    cancel();
    callback(...args);
  };
  const call = Object.assign(
    (...args: Args) => {
      window.clearTimeout(timer);
      pending = args;
      timer = window.setTimeout(flush, delay);
    },
    { flush, cancel },
  );
  return {
    call,
    setCallback: (next: (...args: Args) => void) => {
      callback = next;
    },
  };
}

/** `callback` called `delay` ms after the last call, with the last arguments. A pending call is dropped on unmount. */
export function useDebouncedCallback<Args extends unknown[]>(callback: (...args: Args) => void, delay: number): DebouncedCallback<Args> {
  const debouncer = useMemo(() => createDebouncer<Args>(delay), [delay]);
  useEffect(() => {
    debouncer.setCallback(callback);
  });
  useEffect(() => debouncer.call.cancel, [debouncer]);
  return debouncer.call;
}

/** Open/closed state: `const [opened, { open, close, toggle }] = useDisclosure(false)`. */
export function useDisclosure(initialState = false) {
  const [opened, setOpened] = useState(initialState);
  const open = useCallback(() => setOpened(true), []);
  const close = useCallback(() => setOpened(false), []);
  const toggle = useCallback(() => setOpened((current) => !current), []);
  return [opened, { open, close, toggle }] as const;
}

/**
 * Size of an element, kept up to date with a ResizeObserver: `<div ref={ref}>`. It is a callback ref, so an element
 * that mounts later is picked up. Starts at 0×0 until the first measurement.
 */
export function useElementSize<T extends HTMLElement = HTMLDivElement>() {
  const [size, setSize] = useState({ width: 0, height: 0 });
  const observer = useRef<ResizeObserver | null>(null);
  const frame = useRef(0);

  const ref = useCallback((node: T | null) => {
    observer.current?.disconnect();
    observer.current = null;
    cancelAnimationFrame(frame.current);
    if (!node) return;
    observer.current = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(() => {
        const box = entry.borderBoxSize?.[0];
        setSize(box ? { width: box.inlineSize, height: box.blockSize } : { width: entry.contentRect.width, height: entry.contentRect.height });
      });
    });
    observer.current.observe(node);
  }, []);

  return { ref, width: size.width, height: size.height };
}

const reducedMotionQuery = '(prefers-reduced-motion: reduce)';

function subscribeReducedMotion(onChange: () => void) {
  const media = window.matchMedia(reducedMotionQuery);
  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
}

/** `prefers-reduced-motion: reduce`, read synchronously on the first render and live afterwards. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(reducedMotionQuery).matches,
    () => false,
  );
}
