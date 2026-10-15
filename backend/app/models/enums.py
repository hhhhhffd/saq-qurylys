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
    no_permit_with_offer = "no_permit_with_offer"
    no_permit = "no_permit"
    permit_checking = "permit_checking"
    money_offer = "money_offer"
    stalled = "stalled"
    overdue = "overdue"
    complaints = "complaints"
    readiness_overstated = "readiness_overstated"
    ok = "ok"


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


class EvidenceKind(StrEnum):
    screenshot_png = "screenshot_png"
    archive_mhtml = "archive_mhtml"
    photo = "photo"
    document_scan = "document_scan"
    pdf = "pdf"


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


class HolidayKind(StrEnum):
    holiday = "holiday"
    workday = "workday"
