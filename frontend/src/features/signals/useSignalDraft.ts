import { useEffect, useState } from 'react';
import type { ProposedMeasure, SignalDetail, SignalPatch, SignalRecipient, SignalSections } from '@/api/types';

/** The parts of a card the officer can edit; everything else in `sections` is a snapshot and stays as is. */
export interface SignalDraft {
  scheme_payments: SignalSections['scheme_payments'];
  proposed_measures: ProposedMeasure[];
  note: string;
  recipient: SignalRecipient | null;
  /** empty while the officer is retyping the number */
  review_days: number | '';
}

function fromDetail(detail: SignalDetail): SignalDraft {
  const { sections } = detail;
  return {
    scheme_payments: sections.scheme_payments,
    proposed_measures: sections.proposed_measures,
    note: sections.note,
    recipient: detail.recipient ?? sections.route.recipient,
    review_days: detail.review_days,
  };
}

/** Local edits over the server copy of the card. `value` is the draft when there is one, the server data otherwise. */
export function useSignalDraft(detail: SignalDetail) {
  const [changes, setChanges] = useState<SignalDraft | null>(null);
  const base = fromDetail(detail);
  const value = changes ?? base;
  const dirty = changes !== null && JSON.stringify(changes) !== JSON.stringify(base);
  const valid = value.review_days !== '' && value.review_days >= 1;

  // In-app navigation cannot be intercepted (the app uses BrowserRouter, not a data router),
  // so the browser's own prompt covers reload and tab close.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const update = (patch: Partial<SignalDraft>) => setChanges((current) => ({ ...(current ?? base), ...patch }));
  const reset = () => setChanges(null);

  const toPatch = (): SignalPatch => {
    const reviewDays = value.review_days === '' ? detail.review_days : value.review_days;
    // Only the editable parts go to the backend; the route is saved through `recipient` and `review_days`.
    return {
      sections: {
        scheme_payments: value.scheme_payments,
        proposed_measures: value.proposed_measures,
        note: value.note,
      },
      recipient: value.recipient ?? undefined,
      review_days: reviewDays,
    };
  };

  return { value, dirty, valid, update, reset, toPatch };
}
