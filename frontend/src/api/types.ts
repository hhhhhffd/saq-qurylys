/**
 * API types for SAQ QURYLYS (docs/SPEC.md sections 3, 6, 7, 8).
 * This file and `client.ts` are the only places that know the wire format, so
 * they can be aligned with the real OpenAPI schema in one pass.
 * Field names are snake_case exactly as the backend sends them.
 */

// ---------------------------------------------------------------- generic

export interface Paged<T> {
  items: T[];
  total: number;
}

/** Lists that SPEC does not mark as paginated may arrive as a bare array or as `{items}`. */
export type ListResponse<T> = T[] | { items: T[]; total?: number };

export interface ApiErrorBody {
  detail: { code: string; message: string };
}

// ---------------------------------------------------------------- enums (codes)

export type Role = 'admin' | 'mio_officer' | 'gask' | 'law_enforcement';
export type Locale = 'ru' | 'kk';
export type Zone = 'green' | 'yellow' | 'red';

export type ConstructionStatus = 'not_started' | 'active' | 'stalled' | 'completed';
export type DocType =
  | 'smr_notice'
  | 'psd'
  | 'expertise'
  | 'dsu_permit'
  | 'guarantee'
  | 'ddu_registration'
  | 'land_title';
export type CheckStatus = 'confirmed' | 'not_found' | 'checking';
export type CheckSource =
  | 'housing_portal'
  | 'kazreestr'
  | 'mio_registry'
  | 'cadastre'
  | 'eotinish'
  | 'manual'
  | 'other';
export type ComplaintSource = 'eotinish' | 'manual' | 'other';
export type ComplaintStatus = 'new' | 'in_review' | 'closed';
export type LinkedEntityKind = 'ad_account' | 'sales_office' | 'phone' | 'website' | 'bank_details';

export type Platform = 'instagram' | 'tiktok' | 'telegram' | 'website' | 'aggregator' | 'outdoor' | 'other';
export type AdStatus = 'captured' | 'verification' | 'removed_saved';
export type CaptureStatus = 'pending' | 'done' | 'failed';
export type LlmStatus = 'none' | 'pending' | 'done' | 'failed' | 'disabled';
export type LinkMethod = 'account' | 'phone' | 'name' | 'manual';
export type PaymentScheme = 'booking' | 'down_payment' | 'deposit' | 'installment' | 'nonstandard_contract';
export type PhraseCategory =
  | 'booking'
  | 'down_payment'
  | 'installment'
  | 'sales_start'
  | 'preliminary_contract'
  | 'deposit'
  | 'price_before_completion'
  | 'covert_contract';
export type DetectedBy = 'dictionary' | 'llm';
export type EvidenceKind = 'screenshot_png' | 'archive_mhtml' | 'photo' | 'document_scan' | 'pdf';

export type KeyStatus =
  | 'no_permit_with_offer'
  | 'no_permit'
  | 'permit_checking'
  | 'money_offer'
  | 'stalled'
  | 'overdue'
  | 'complaints'
  | 'readiness_overstated'
  | 'ok';

export type SignalStatus = 'requires_confirmation' | 'returned' | 'sent' | 'responded' | 'closed';
export type SignalRecipient = 'mio' | 'gask' | 'law_enforcement';
export type SignalOrigin = 'auto' | 'manual';
export type ProposedMeasure =
  | 'request_documents'
  | 'site_inspection'
  | 'interview_complainants'
  | 'request_payments_info';

export type NotificationKind =
  | 'red_zone'
  | 'signal_returned'
  | 'signal_sent'
  | 'signal_due_soon'
  | 'signal_overdue'
  | 'signal_responded'
  | 'capture_failed';

export type HolidayKind = 'holiday' | 'workday';
export type TerritoryLevel = 'region' | 'city';
export type ScoreTrigger = 'event' | 'schedule' | 'manual';

// ---------------------------------------------------------------- auth / users / territories

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  territory_id: number | null;
  locale: Locale;
}

export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  user: User;
}

export interface AdminUser extends User {
  is_active: boolean;
}

/** `POST /users` takes every field; `PATCH /users/{id}` takes any of them except `username` (immutable). Password: 8..128 chars. */
export interface UserInput {
  /** lowercase: `^[a-z0-9._@-]{3,64}$` */
  username: string;
  full_name: string;
  password?: string;
  role: Role;
  territory_id: number | null;
  is_active: boolean;
  locale: Locale;
}

export interface Territory {
  id: number;
  parent_id: number | null;
  level: TerritoryLevel;
  code: string;
  name: string;
  timezone: string;
  center_lat: number | null;
  center_lon: number | null;
  /** `GET /territories` returns a nested tree; `flattenTerritories` flattens it. */
  children: Territory[];
}

/** `POST /territories`; lat and lon are given together or not at all. */
export interface TerritoryInput {
  parent_id: number | null;
  level: TerritoryLevel;
  /** lowercase latin, digits and dashes: `^[a-z0-9][a-z0-9-]{1,63}$` */
  code: string;
  name: string;
  timezone: string;
  lat?: number | null;
  lon?: number | null;
}

/** `PATCH /territories/{id}`: only these fields can change. */
export type TerritoryUpdate = Partial<Pick<TerritoryInput, 'name' | 'timezone' | 'lat' | 'lon'>>;

export interface DistrictFeature {
  type: 'Feature';
  id?: number | string;
  properties: { id?: number; name: string } & Record<string, unknown>;
  geometry: { type: string; coordinates: unknown } | null;
}

export interface DistrictCollection {
  type: 'FeatureCollection';
  features: DistrictFeature[];
}

export interface Holiday {
  day: string; // YYYY-MM-DD
  kind: HolidayKind;
  name: string;
}

/** `GET /settings` (typed keys with defaults) and `PUT /settings` (partial: send only the keys to change; unknown keys are rejected). */
export interface AppSettings {
  review_days: number;
  ad_window_days: number;
  readiness_gap_pp: number;
  complaints_threshold: number;
  stalled_days: number;
  recheck_after_days: number;
  link_confidence_threshold: number;
  green_interval_days: number;
  yellow_interval_days: number;
  /** e-mail addresses per receiving body */
  recipient_emails: Record<SignalRecipient, string[]>;
}

// ---------------------------------------------------------------- dashboard / objects

export interface ObjectRow {
  id: number;
  code: string;
  name: string;
  developer_name: string | null;
  score: number | null;
  zone: Zone | null;
  key_status: KeyStatus | null;
  /** e.g. `{ stalled_days: 45 }` for key_status `stalled` */
  key_status_detail: Record<string, unknown> | null;
  district_name: string | null;
  lat: number | null;
  lon: number | null;
}

export interface DashboardCounts {
  green: number;
  yellow: number;
  red: number;
  unscored: number;
  total: number;
}

export interface Dashboard {
  counts: DashboardCounts;
  last_updated_at: string | null;
  objects: ObjectRow[];
}

export interface Developer {
  id: number;
  bin: string;
  name: string;
  director: string | null;
  founders: string[];
  authorized_company: string | null;
  phones: string[];
}

export type DeveloperInput = Omit<Developer, 'id'>;

export interface EvidenceMeta {
  id: number;
  kind: EvidenceKind;
  content_type: string;
  sha256: string;
  size_bytes: number;
  captured_at: string;
  source_url: string | null;
  retention_until: string | null;
  lock_mode?: string | null;
}

export interface ObjectDocument {
  id: number;
  object_id: number;
  doc_type: DocType;
  number: string | null;
  issued_at: string | null;
  issuer: string | null;
  check_status: CheckStatus;
  checked_at: string | null;
  checked_by: number | null;
  check_source: CheckSource | null;
  note: string | null;
  evidence: EvidenceMeta[];
}

export interface Inspection {
  id: number;
  object_id: number;
  inspected_at: string;
  readiness_pct: number;
  lat: number | null;
  lon: number | null;
  inspector_id: number | null;
  note: string | null;
  evidence: EvidenceMeta[];
}

export interface Complaint {
  id: number;
  object_id: number;
  received_at: string;
  source: ComplaintSource;
  external_id: string | null;
  is_collective: boolean;
  signatories_count: number;
  summary: string | null;
  status: ComplaintStatus;
  confirmed_payments: boolean;
}

export interface LinkedEntity {
  id: number;
  object_id: number | null;
  developer_id: number | null;
  kind: LinkedEntityKind;
  value: string;
  note: string | null;
}

export interface EvidenceRef {
  type: 'document' | 'ad_post' | 'complaint' | 'inspection' | 'evidence' | string;
  id: number;
}

export interface ScoreFactor {
  code: string;
  weight: number;
  triggered: boolean;
  evidence: EvidenceRef[];
  detail: Record<string, unknown> | null;
}

export interface RiskScore {
  score: number;
  zone: Zone;
  zone_reasons: string[];
  breakdown: ScoreFactor[];
  calculated_at: string;
  trigger?: ScoreTrigger;
}

export interface ObjectDetail {
  id: number;
  code: string;
  territory_id: number;
  district_id: number | null;
  district_name: string | null;
  developer_id: number | null;
  name: string;
  aliases: string[];
  address: string | null;
  cadastral_number: string | null;
  land_purpose: string | null;
  lat: number | null;
  lon: number | null;
  planned_completion: string | null;
  forecast_completion: string | null;
  construction_status: ConstructionStatus;
  stalled_since: string | null;
  readiness_actual_pct: number | null;
  readiness_claimed_pct: number | null;
  prior_violations: string | null;
  score: number | null;
  zone: Zone | null;
  key_status: KeyStatus | null;
  key_status_detail: Record<string, unknown> | null;
  last_scored_at: string | null;
  next_check_at: string | null;
  is_demo: boolean;
  developer: Developer | null;
  documents: ObjectDocument[];
  inspections: Inspection[];
  complaints: Complaint[];
  linked_entities: LinkedEntity[];
  ads_7d_count: number;
  /** claimed minus actual, percentage points; null when either side is unknown */
  readiness_gap_pp: number | null;
  latest_score: RiskScore | null;
}

/** Body for `POST /objects` and `PATCH /objects/{id}`. */
export interface ObjectInput {
  territory_id?: number;
  district_id?: number | null;
  developer_id?: number | null;
  name?: string;
  aliases?: string[];
  address?: string | null;
  cadastral_number?: string | null;
  land_purpose?: string | null;
  lat?: number | null;
  lon?: number | null;
  planned_completion?: string | null;
  forecast_completion?: string | null;
  construction_status?: ConstructionStatus;
  stalled_since?: string | null;
  prior_violations?: string | null;
}

export interface ObjectListParams {
  zone?: Zone;
  district_id?: number;
  q?: string;
  limit?: number;
  offset?: number;
}

export interface ImportResult {
  created: number;
  updated: number;
  errors: { row: number; message: string }[];
}

export interface DocumentInput {
  doc_type: DocType;
  number?: string;
  issued_at?: string;
  issuer?: string;
  /** `checked_at` / `checked_by` are set by the server */
  check_status: CheckStatus;
  check_source?: CheckSource;
  note?: string;
}

export interface InspectionInput {
  inspected_at: string;
  readiness_pct: number;
  lat?: number;
  lon?: number;
  note?: string;
}

export interface ComplaintInput {
  received_at: string;
  source: ComplaintSource;
  external_id?: string;
  is_collective: boolean;
  signatories_count?: number;
  summary?: string;
  status: ComplaintStatus;
  confirmed_payments: boolean;
}

export interface LinkedEntityInput {
  kind: LinkedEntityKind;
  value: string;
  note?: string;
}

export interface ScoreHistoryItem extends RiskScore {
  id: number;
  object_id: number;
  trigger: ScoreTrigger;
}

// ---------------------------------------------------------------- ads

export interface SourceAccount {
  id: number;
  platform: Platform;
  handle: string | null;
  url: string | null;
  object_id: number | null;
  developer_id: number | null;
  territory_id: number | null;
  is_watched: boolean;
  last_collected_at: string | null;
}

export type SourceAccountInput = Partial<Omit<SourceAccount, 'id' | 'last_collected_at'>> & {
  platform: Platform;
};

export interface PhraseHit {
  id: number;
  ad_post_id: number;
  phrase_id: number | null;
  category: PhraseCategory;
  matched_text: string;
  /** character offsets into `AdRow.text` (end exclusive) */
  start: number;
  end: number;
  weight: number;
  detected_by: DetectedBy;
  /** null = not reviewed yet */
  confirmed: boolean | null;
  confirmed_by: number | null;
}

export interface LlmExtraction {
  payment_schemes?: PaymentScheme[];
  claimed_readiness_pct?: number | null;
  price_before_completion?: boolean;
  quotes?: string[];
}

export interface AdRow {
  id: number;
  territory_id: number | null;
  source_account_id: number | null;
  platform: Platform;
  url: string | null;
  author: string | null;
  published_at: string | null;
  captured_at: string | null;
  text: string | null;
  phones: string[];
  links: string[];
  object_id: number | null;
  object_name: string | null;
  link_confidence: number | null;
  link_method: LinkMethod | null;
  payment_schemes: PaymentScheme[];
  claimed_readiness_pct: number | null;
  price_before_completion: boolean;
  llm_status: LlmStatus;
  status: AdStatus;
  max_phrase_weight: number;
  total_phrase_weight: number;
  is_outdoor: boolean;
  lat: number | null;
  lon: number | null;
  last_checked_at: string | null;
  removed_detected_at: string | null;
  capture_status: CaptureStatus;
  capture_error: string | null;
}

export interface AdDetail extends AdRow {
  phrase_hits: PhraseHit[];
  evidence: EvidenceMeta[];
  llm_extraction: LlmExtraction | null;
  linked_object: { id: number; code: string; name: string } | null;
}

export interface AdListParams {
  platform?: Platform;
  object_id?: number;
  status?: AdStatus;
  q?: string;
  limit?: number;
  offset?: number;
}

export interface AdPatch {
  object_id?: number | null;
  status?: AdStatus;
  payment_schemes?: PaymentScheme[];
  claimed_readiness_pct?: number | null;
  price_before_completion?: boolean;
}

export interface CaptureRequest {
  url: string;
  object_id?: number | null;
  platform?: Platform;
}

export interface Phrase {
  id: number;
  text: string;
  variants: string[];
  category: PhraseCategory;
  weight: number;
  is_active: boolean;
}

export type PhraseInput = Omit<Phrase, 'id'>;

// ---------------------------------------------------------------- risk factors

export interface RiskFactor {
  code: string;
  description: string;
  weight: number;
  is_active: boolean;
  sort_order: number;
}

export interface RiskFactorChange {
  id?: number;
  code: string;
  old_weight: number | null;
  new_weight: number | null;
  old_active: boolean | null;
  new_active: boolean | null;
  changed_by: number | null;
  changed_by_name?: string | null;
  changed_at: string;
}

// ---------------------------------------------------------------- signals

export interface SignalRow {
  id: number;
  number: string;
  object_id: number;
  object_name: string;
  zone: Zone | null;
  status: SignalStatus;
  recipient: SignalRecipient | null;
  due_date: string | null;
  is_overdue: boolean;
  created_at: string;
}

export interface SignalSections {
  object_developer: {
    object_code: string;
    object_name: string;
    address: string | null;
    cadastral_number: string | null;
    land_purpose: string | null;
    developer_name: string | null;
    bin: string | null;
    director: string | null;
    founders: string[];
  };
  risk_factors: { code: string; weight: number; detail: Record<string, unknown> | null }[];
  permit_checks: {
    doc_type: DocType;
    source: CheckSource | null;
    check_status: CheckStatus;
    checked_at: string | null;
    number: string | null;
    evidence_ids: number[];
  }[];
  publications: {
    ad_post_id: number;
    platform: Platform;
    url: string | null;
    published_at: string | null;
    captured_at: string | null;
    evidence_ids: number[];
    status: AdStatus;
  }[];
  scheme_payments: {
    payment_schemes: PaymentScheme[];
    contract_types: string[];
    confirmed_payments_note: string;
  };
  proposed_measures: ProposedMeasure[];
  route: { recipient: SignalRecipient | null; review_days: number };
  note: string;
}

export interface AuditEntry {
  id: number;
  user_id: number | null;
  username: string | null;
  at: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip?: string | null;
}

export interface SignalDetail extends SignalRow {
  origin: SignalOrigin;
  sections: SignalSections;
  review_days: number;
  sent_at: string | null;
  sent_by: number | null;
  return_comment: string | null;
  response_text: string | null;
  response_at: string | null;
  responded_by: number | null;
  created_by: number | null;
  audit: AuditEntry[];
}

export interface SignalListParams {
  status?: SignalStatus;
  object_id?: number;
  limit?: number;
  offset?: number;
}

export interface SignalPatch {
  sections?: SignalSections;
  recipient?: SignalRecipient;
  review_days?: number;
}

// ---------------------------------------------------------------- notifications

export interface AppNotification {
  id: number;
  kind: NotificationKind;
  entity_type: string | null;
  entity_id: number | null;
  payload: Record<string, unknown> | null;
  created_at: string;
  read_at: string | null;
}
