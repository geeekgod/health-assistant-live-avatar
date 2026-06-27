import re

_INDIAN_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")


def parse_indian_mobile(phone: str | None) -> str | None:
    """Return 10-digit Indian mobile or None. Accepts +91 / 91 prefix or bare 10 digits."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone.strip())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not _INDIAN_MOBILE_RE.match(digits):
        return None
    return digits


def to_e164_india(ten_digits: str) -> str:
    return f"+91{ten_digits}"


def format_indian_phone(phone: str | None) -> str | None:
    ten = parse_indian_mobile(phone)
    return to_e164_india(ten) if ten else None


def phone_lookup_variants(phone: str | None) -> list[str]:
    ten = parse_indian_mobile(phone)
    if not ten:
        return []
    stored = to_e164_india(ten)
    return list({ten, stored})
