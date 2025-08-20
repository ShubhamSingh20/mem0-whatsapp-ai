import phonenumbers
from phonenumbers import timezone as pn_tz

def infer_timezone_from_number(e164: str) -> str | None:
    try:
        e164 = e164.replace("whatsapp:", "")
        num = phonenumbers.parse(e164, None)
        tzs = pn_tz.time_zones_for_number(num)  # e.g. ['Asia/Kolkata']
        return tzs[0] if tzs else None
    except Exception:
        return None
