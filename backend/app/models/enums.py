from enum import StrEnum


class TerritoryLevel(StrEnum):
    region = "region"
    city = "city"


class Role(StrEnum):
    admin = "admin"
    mio_officer = "mio_officer"
    gask = "gask"
    law_enforcement = "law_enforcement"


class Locale(StrEnum):
    ru = "ru"
    kk = "kk"


class ConstructionStatus(StrEnum):
    not_started = "not_started"
    active = "active"
    stalled = "stalled"
    completed = "completed"


class Zone(StrEnum):
    green = "green"
    yellow = "yellow"
    red = "red"


class KeyStatus(StrEnum):
    no_legal_basis_with_offer = "no_legal_basis_with_offer"
    no_legal_basis = "no_legal_basis"
    money_offer = "money_offer"
    legal_basis_unknown = "legal_basis_unknown"
    stalled = "stalled"
    delayed = "delayed"
    collective_complaint = "collective_complaint"
    readiness_mismatch = "readiness_mismatch"
    active_ads = "active_ads"
    ok = "ok"


class LegalBasisStatus(StrEnum):
    """SPEC 6.0: only `absent_established` counts as a missing legal basis; unknown data is not an absence."""

    confirmed = "confirmed"
    absent_established = "absent_established"
    unknown = "unknown"


class DocType(StrEnum):
    smr_notice = "smr_notice"
    psd = "psd"
    expertise = "expertise"
    dsu_permit = "dsu_permit"
    guarantee = "guarantee"
    ddu_registration = "ddu_registration"
    land_title = "land_title"


class CheckStatus(StrEnum):
    confirmed = "confirmed"
    not_found = "not_found"
    checking = "checking"


class CheckSource(StrEnum):
    housing_portal = "housing_portal"
    kazreestr = "kazreestr"
    mio_registry = "mio_registry"
    cadastre = "cadastre"
    eotinish = "eotinish"
    manual = "manual"
    other = "other"


class ComplaintSource(StrEnum):
    eotinish = "eotinish"
    manual = "manual"
    telegram = "telegram"
    other = "other"


class ComplaintStatus(StrEnum):
    new = "new"
    in_review = "in_review"
    closed = "closed"


class LinkedEntityKind(StrEnum):
    ad_account = "ad_account"
    sales_office = "sales_office"
    phone = "phone"
    website = "website"
    bank_details = "bank_details"


class Platform(StrEnum):
    instagram = "instagram"
    tiktok = "tiktok"
    telegram = "telegram"
    website = "website"
    aggregator = "aggregator"
    outdoor = "outdoor"
    other = "other"


class LinkMethod(StrEnum):
    account = "account"
    phone = "phone"
    name = "name"
    manual = "manual"


class PaymentScheme(StrEnum):
    booking = "booking"
    down_payment = "down_payment"
    deposit = "deposit"
    installment = "installment"
    nonstandard_contract = "nonstandard_contract"


class LlmStatus(StrEnum):
    none = "none"
    pending = "pending"
    done = "done"
    failed = "failed"
    disabled = "disabled"


class AdStatus(StrEnum):
    captured = "captured"
    verification = "verification"
    removed_saved = "removed_saved"


class CaptureStatus(StrEnum):
    pending = "pending"
    done = "done"
    failed = "failed"


class AdOrigin(StrEnum):
    """How a publication entered the system: added by staff (by hand or by URL) or gathered automatically."""

    manual = "manual"
    capture = "capture"
    collector = "collector"
    citizen = "citizen"
    vision = "vision"


class AdVersionSource(StrEnum):
    capture = "capture"
    collector = "collector"
    recheck = "recheck"


class OcrStatus(StrEnum):
    pending = "pending"
    done = "done"
    failed = "failed"


class EvidenceKind(StrEnum):
    screenshot_png = "screenshot_png"
    archive_mhtml = "archive_mhtml"
    photo = "photo"
    document_scan = "document_scan"
    pdf = "pdf"
    registry_response = "registry_response"


class LockMode(StrEnum):
    GOVERNANCE = "GOVERNANCE"
    COMPLIANCE = "COMPLIANCE"


class PhraseCategory(StrEnum):
    booking = "booking"
    down_payment = "down_payment"
    installment = "installment"
    sales_start = "sales_start"
    preliminary_contract = "preliminary_contract"
    deposit = "deposit"
    price_before_completion = "price_before_completion"
    covert_contract = "covert_contract"


class DetectedBy(StrEnum):
    dictionary = "dictionary"
    llm = "llm"


class ScoreTrigger(StrEnum):
    event = "event"
    schedule = "schedule"
    manual = "manual"
    # History reconstructed afterwards from dated facts (SPEC 10.5), not computed at the time.
    replay = "replay"


class SignalStatus(StrEnum):
    requires_confirmation = "requires_confirmation"
    returned = "returned"
    sent = "sent"
    responded = "responded"
    closed = "closed"


class SignalOrigin(StrEnum):
    auto = "auto"
    manual = "manual"


class Recipient(StrEnum):
    mio = "mio"
    gask = "gask"
    law_enforcement = "law_enforcement"


class NotificationKind(StrEnum):
    red_zone = "red_zone"
    signal_returned = "signal_returned"
    signal_sent = "signal_sent"
    signal_due_soon = "signal_due_soon"
    signal_overdue = "signal_overdue"
    signal_responded = "signal_responded"
    capture_failed = "capture_failed"
    citizen_report = "citizen_report"
    collector_failed = "collector_failed"
    assignment_new = "assignment_new"


class HolidayKind(StrEnum):
    holiday = "holiday"
    workday = "workday"


class VisionSource(StrEnum):
    drone = "drone"
    camera = "camera"
    phone = "phone"
    other = "other"


class VisionSessionStatus(StrEnum):
    open = "open"
    reviewed = "reviewed"


class VisionAssetKind(StrEnum):
    photo = "photo"
    video = "video"


class VisionAssetStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class VisionJobKind(StrEnum):
    extract_frames = "extract_frames"
    ocr_region = "ocr_region"


class VisionJobStatus(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class VisionRunStatus(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class VisionCategory(StrEnum):
    outdoor_ad = "outdoor_ad"
    fence = "fence"
    site_gate = "site_gate"
    waste_container = "waste_container"
    wheel_wash = "wheel_wash"
    debris = "debris"
    other = "other"


class VisionFindingStatus(StrEnum):
    """A visual finding is not a violation: the legal conclusion is a separate human check (plan, section 5)."""

    observed = "observed"
    possible_noncompliance = "possible_noncompliance"
    insufficient_evidence = "insufficient_evidence"
    not_applicable = "not_applicable"


class VisionFindingOrigin(StrEnum):
    manual = "manual"
    model = "model"


class VisionReviewState(StrEnum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"
    needs_more_evidence = "needs_more_evidence"


class VisionReviewAction(StrEnum):
    confirm = "confirm"
    reject = "reject"
    needs_more_evidence = "needs_more_evidence"
    not_applicable = "not_applicable"
    comment = "comment"


class AssignmentStatus(StrEnum):
    open = "open"
    done = "done"
    cancelled = "cancelled"
