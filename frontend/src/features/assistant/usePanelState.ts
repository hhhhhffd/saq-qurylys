import { useState } from 'react';

const PANEL_KEY = 'saq_ai_panel';

interface PanelState {
  open: boolean;
  expanded: boolean;
}

function load(): PanelState {
  try {
    const stored = JSON.parse(localStorage.getItem(PANEL_KEY) ?? '{}') as Partial<PanelState>;
    // Under 62em the panel covers the whole page, so it is never reopened by itself there.
    return { open: stored.open === true && window.matchMedia('(min-width: 62em)').matches, expanded: stored.expanded === true };
  } catch {
    return { open: false, expanded: false };
  }
}

/** Open/expanded state of the assistant panel, remembered on this device. */
export function usePanelState() {
  const [state, setState] = useState(load);

  const update = (change: Partial<PanelState>) => {
    const next = { ...state, ...change };
    setState(next);
    try {
      localStorage.setItem(PANEL_KEY, JSON.stringify(next));
    } catch {
      // Persistence is best-effort.
    }
  };

  return {
    ...state,
    setOpen: (open: boolean) => update({ open }),
    toggleExpanded: () => update({ expanded: !state.expanded }),
  };
}
