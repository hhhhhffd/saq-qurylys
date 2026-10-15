import phonenumbers

DEFAULT_REGION = "KZ"


def normalize_phone(raw: str, region: str = DEFAULT_REGION) -> str | None:
    """Return the number in E.164 format, or None if it is not a valid phone number."""
    try:
        parsed = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
