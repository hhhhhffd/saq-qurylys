import type { PaymentScheme, ProposedMeasure, SignalRecipient, SignalStatus } from '@/api/types';

export const PAGE_SIZE = 25;

export const SIGNAL_STATUSES: readonly SignalStatus[] = [
  'requires_confirmation',
  'returned',
  'sent',
  'responded',
  'closed',
];
export const RECIPIENTS: readonly SignalRecipient[] = ['mio', 'gask', 'law_enforcement'];
export const PAYMENT_SCHEMES: readonly PaymentScheme[] = [
  'booking',
  'down_payment',
  'deposit',
  'installment',
  'nonstandard_contract',
];
export const MEASURES: readonly ProposedMeasure[] = [
  'request_documents',
  'site_inspection',
  'interview_complainants',
  'request_payments_info',
];

export const MIN_RETURN_COMMENT = 10;
export const MIN_RESPONSE_TEXT = 5;
export const MAX_REVIEW_DAYS = 60;
