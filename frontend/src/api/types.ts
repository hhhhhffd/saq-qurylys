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
  'smr_notice' | 'psd' | 'expertise' | 'dsu_permit' | 'guarantee' | 'ddu_registration' | 'land_title';
export type CheckStatus = 'confirmed' | 'not_found' | 'checking';
export type CheckSource =
  'housing_portal' | 'kazreestr' | 'mio_registry' | 'cadastre' | 'eotinish' | 'manual' | 'other';
export type ComplaintSource = 'eotinish' | 'manual' | 'telegram' | 'other';
export type ComplaintStatus = 'new' | 'in_review' | 'closed';
export type LinkedEntityKind = 'ad_account' | 'sales_office' | 'phone' | 'website' | 'bank_details';

export type Platform = 'instagram' | 'tiktok' | 'telegram' | 'website' | 'aggregator' | 'outdoor' | 'other';
export type AdStatus = 'captured' | 'verification' | 'removed_saved';
export type CaptureStatus = 'pending' | 'done' | 'failed';
export type AdOrigin = 'manual' | 'capture' | 'collector' | 'citizen';
export type OcrStatus = 'pending' | 'done' | 'failed';
export type AdVersionSource = 'capture' | 'collector' | 'recheck';
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
export type EvidenceKind = 'screenshot_png' | 'archive_mhtml' | 'photo' | 'document_scan' | 'pdf' | 'registry_response';

export type KeyStatus =
  | 'no_legal_basis_with_offer'
  | 'no_legal_basis'
  | 'money_offer'
  | 'legal_basis_unknown'
  | 'stalled'
  | 'delayed'
  | 'collective_complaint'
  | 'readiness_mismatch'
  | 'active_ads'
  | 'ok';

/** SPEC 6.0: only `absent_established` gives R1; `unknown` is a "needs check" flag, not a finding. */
export type LegalBasisStatus = 'confirmed' | 'absent_established' | 'unknown';
/** Result of the check of one legal-basis document type; `none` = no record of a check. */
export type LegalCheck = CheckStatus | 'none';

export type SignalStatus = 'requires_confirmation' | 'returned' | 'sent' | 'responded' | 'closed';
export type SignalRecipient = 'mio' | 'gask' | 'law_enforcement';
export type SignalOrigin = 'auto' | 'manual';
export type ProposedMeasure =
  'request_documents' | 'site_inspection' | 'interview_complainants' | 'request_payments_info';

export type NotificationKind =
  | 'red_zone'
  | 'signal_returned'
  | 'signal_sent'
  | 'signal_due_soon'
  | 'signal_overdue'
  | 'signal_responded'
  | 'capture_failed'
  | 'citizen_report'
  | 'collector_failed';

export type HolidayKind = 'holiday' | 'workday';
export type TerritoryLevel = 'region' | 'city';
export type ScoreTrigger = 'event' | 'schedule' | 'manual' | 'replay';

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
  significant_delay_days: number;
  /** score from which an object is yellow (below it: green) */
  zone_yellow_min: number;
  /** score from which an object with both R1 and R2 is red */
  zone_red_min: number;
  /** no longer used by the risk model (R4 needs a verified collective complaint); never shown */
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
  /** fictional demo object (D18) */
  is_demo: boolean;
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
  /** checked by an analyst; R4 counts only verified collective complaints */
  is_verified: boolean;
  verified_by: number | null;
  verified_at: string | null;
}

export interface LinkedEntity {
  id: number;
  object_id: number | null;
  developer_id: number | null;
  kind: LinkedEntityKind;
  value: string;
  note: string | null;
}

/** A record a risk factor is based on. R2 evidence also carries the hit and the quoted phrase. */
export interface EvidenceRef {
  /** `ad_post`, `document`, `complaint`, `inspection` */
  type: string;
  id: number;
  phrase_hit_id?: number;
  fragment?: string;
}

export interface R1Detail {
  legal_basis_status: LegalBasisStatus;
  checks: { guarantee: LegalCheck; dsu_permit: LegalCheck };
}

export interface R2Detail {
  window_days: number;
  count: number;
  categories: PhraseCategory[];
  payment_schemes: PaymentScheme[];
}

export interface R3Detail {
  window_days: number;
  count: number;
  construction_status: ConstructionStatus;
}

export interface R4Detail {
  count: number;
  collective_count: number;
  verified_count: number;
  unverified_count: number;
}

export interface R5Detail {
  claimed_pct: number | null;
  actual_pct: number | null;
  gap_pp: number | null;
  threshold: number;
  /** both values come from a dated source: a confirmed publication and a photo inspection */
  sourced: boolean;
  inspected_at: string | null;
}

export interface R6Detail {
  construction_status: ConstructionStatus;
  stalled: boolean;
  stalled_days: number | null;
  stalled_threshold: number;
  delayed: boolean;
  forecast_delay_days: number | null;
  planned_overdue_days: number | null;
  significant_delay_days: number;
}

interface FactorBase<Code extends string, Detail> {
  code: Code;
  /** `R1`..`R6` */
  label: string;
  weight: number;
  triggered: boolean;
  evidence: EvidenceRef[];
  detail: Detail;
}

export type ScoreFactor =
  | FactorBase<'r1_no_legal_basis', R1Detail>
  | FactorBase<'r2_money_offer', R2Detail>
  | FactorBase<'r3_active_ads', R3Detail>
  | FactorBase<'r4_collective_complaint', R4Detail>
  | FactorBase<'r5_readiness_mismatch', R5Detail>
  | FactorBase<'r6_stalled_or_delayed', R6Detail>;

export type RiskFactorCode = ScoreFactor['code'];

/** "Needs check" flags: unknown or unconfirmed facts. They never add points. */
export type NeedsCheck =
  | { code: 'legal_basis_unknown'; detail: { checks: R1Detail['checks'] } }
  | { code: 'complaint_unverified'; detail: { count: number; complaint_ids: number[] } }
  | { code: 'readiness_unverified'; detail: { claimed_pct: number } }
  | { code: 'ai_hypotheses_pending'; detail: { count: number; ad_post_ids: number[] } }
  | { code: 'link_unverified'; detail: { count: number; ad_post_ids: number[] } };

export type NeedsCheckCode = NeedsCheck['code'];

export interface RiskBreakdown {
  /** every active factor, the ones that did not fire included */
  factors: ScoreFactor[];
  needs_check: NeedsCheck[];
  legal_basis_status: LegalBasisStatus;
}

export function findFactor<Code extends RiskFactorCode>(
  breakdown: RiskBreakdown | null,
  code: Code,
): Extract<ScoreFactor, { code: Code }> | undefined {
  return breakdown?.factors.find((factor): factor is Extract<ScoreFactor, { code: Code }> => factor.code === code);
}

export function readBreakdown(
  score: { breakdown: RiskBreakdown | unknown[] } | null | undefined,
): RiskBreakdown | null {
  return score && !Array.isArray(score.breakdown) ? score.breakdown : null;
}

export interface RiskScore {
  score: number;
  zone: Zone;
  /** `score_0_24`, `score_25_59`, `score_60_without_r1_r2` or `r1_and_r2` (the numbers follow the zone settings) */
  zone_reasons: string[];
  /** a score calculated before the case model holds a plain list and carries no factors (see `readBreakdown`) */
  breakdown: RiskBreakdown | unknown[];
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
  is_verified?: boolean;
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
  handle: string;
  url: string | null;
  object_id: number | null;
  developer_id: number | null;
  territory_id: number | null;
  is_watched: boolean;
  last_collected_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
}

export type SourceAccountInput = Partial<
  Omit<SourceAccount, 'id' | 'last_collected_at' | 'last_error' | 'last_error_at'>
> & {
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
  /** null = not reviewed yet: a dictionary match is a rule-based fact, an LLM match is a hypothesis */
  confirmed: boolean | null;
  confirmed_by: number | null;
  /** 0..1, only for LLM hits */
  confidence?: number | null;
  /** LLM was unsure (confidence below 0.5) */
  uncertain?: boolean;
}

export interface LlmFinding {
  category: PhraseCategory;
  quote: string;
  confidence: number;
  uncertain: boolean;
}

/** What the LLM extracted from the text: a hypothesis until an analyst accepts it. */
export interface LlmExtraction {
  findings?: LlmFinding[];
  payment_schemes?: PaymentScheme[];
  claimed_readiness_pct?: number | null;
  price_before_completion?: boolean;
  confidence?: number;
  uncertain: boolean;
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
  is_demo: boolean;
  lat: number | null;
  lon: number | null;
  last_checked_at: string | null;
  removed_detected_at: string | null;
  /** null for a publication entered by hand */
  capture_status: CaptureStatus | null;
  capture_error: string | null;
  origin: AdOrigin;
  /** null when the publication has no photos to read */
  ocr_status: OcrStatus | null;
}

export interface AdDetail extends AdRow {
  /** later texts that differ from the saved original, oldest first (SPEC 10.6) */
  versions: AdVersion[];
  /** when the original was saved: the capture time, else the time the publication was entered */
  original_captured_at: string;
  /** the first screenshot of the publication */
  original_evidence: AdEvidence | null;
  phrase_hits: PhraseHit[];
  evidence: EvidenceMeta[];
  llm_extraction: LlmExtraction | null;
  linked_object: { id: number; code: string; name: string } | null;
}

export interface AdListParams {
  platform?: Platform;
  object_id?: number;
  status?: AdStatus;
  is_demo?: boolean;
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
  /** the object of the card is a fictional demo object (D18) */
  is_demo: boolean;
  zone: Zone | null;
  status: SignalStatus;
  recipient: SignalRecipient | null;
  due_date: string | null;
  is_overdue: boolean;
  created_at: string;
}

/** A phrase hit of a publication on the card: a fact (dictionary or analyst-confirmed) or an AI hypothesis. */
export interface PublicationHit {
  id: number;
  category: PhraseCategory;
  fragment: string;
  detected_by: DetectedBy;
  confirmed: boolean | null;
  kind: 'fact' | 'ai_hypothesis';
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
  /** the factors that fired when the card was formed */
  risk_factors: Pick<ScoreFactor, 'code' | 'label' | 'weight' | 'detail' | 'evidence'>[];
  legal_basis_status: LegalBasisStatus | null;
  needs_check: NeedsCheck[];
  is_demo: boolean;
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
    is_demo: boolean;
    hits: PublicationHit[];
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
  /** immutable copy of the PDF that was sent (evidence kind `pdf`) */
  sent_pdf_evidence_id: number | null;
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
  /** only the parts an officer may edit; the rest of the sections is a snapshot and is ignored by the backend */
  sections?: Partial<Pick<SignalSections, 'scheme_payments' | 'proposed_measures' | 'note'>>;
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

// ---------------------------------------------------------------- admin jobs

/** `POST /phrases/reanalyze` (202) */
export interface ReanalysisQueued {
  queued: boolean;
}

export interface RegistrySyncResult {
  ok: boolean;
  region_id: number;
  started_at: string;
  finished_at: string;
  fetched: number;
  objects_created: number;
  documents_created: number;
  documents_updated: number;
  /** confirmed by the registry before, absent now: set back to `checking` for a manual check */
  documents_unconfirmed: number;
  skipped: number;
  errors: string[];
}

/** `POST /registry-sync/homeportal` (202) */
export interface SyncStarted {
  task_id: string;
}

/** `GET /registry-sync/status` */
export interface RegistrySyncStatus {
  /** the scheduled daily run is on (`HOMEPORTAL_SYNC_ENABLED`); a run can always be started by hand */
  scheduled_enabled: boolean;
  last_sync: RegistrySyncResult | null;
}

// ---------------------------------------------------------------- activity feed (SPEC 10.7)

export type ActivityKind = 'ad_received' | 'score_changed' | 'signal_created' | 'signal_sent';

/** Only the fields of the event's `kind` are filled, the rest are null. */
export interface ActivityEvent {
  /** `<kind>:<row id>` */
  id: string;
  kind: ActivityKind;
  at: string;
  object_id: number | null;
  object_name: string | null;
  ad_id: number | null;
  signal_id: number | null;
  /** publication origin for `ad_received`, card origin (`auto`/`manual`) for the signal kinds */
  origin: AdOrigin | SignalOrigin | null;
  platform: Platform | null;
  score_before: number | null;
  score_after: number | null;
  zone_before: Zone | null;
  zone_after: Zone | null;
  number: string | null;
  is_demo: boolean | null;
}

/** `GET /activity?after=<cursor>&limit=`: `items` are newest first, `cursor` is passed back as `after`. */
export interface ActivityFeed {
  items: ActivityEvent[];
  cursor: string;
}

// ---------------------------------------------------------------- ad versions (SPEC 10.6)

/** A later text of a publication that differs from the saved original (`AdRow.text`). */
export interface AdVersion {
  id: number;
  text: string;
  text_sha256: string;
  observed_at: string;
  source: AdVersionSource;
  /** the capture of the page that showed this text; null when none was taken */
  evidence_id: number | null;
}

/** Evidence as `GET /ads/{id}` sends it: with the flag of an RFC 3161 time stamp. */
export interface AdEvidence extends EvidenceMeta {
  has_tsa_token: boolean;
}
