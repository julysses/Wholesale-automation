"""Conservative short-reply bound, independent of carrier smart encoding."""

# At most three long-code SMS segments: Unicode multipart segments hold 67
# UTF-16 units, or at least 66 when a surrogate pair cannot straddle a boundary.
# GSM extension characters cost at most two septets each, so this bound also
# fits three GSM multipart segments (198 * 2 <= 3 * 153).
MAX_REPLY_UTF16_UNITS = 198


def short_sms_reply(text):
    if not isinstance(text, str) or not text.strip():
        return False
    try:
        return len(text.encode('utf-16-le')) // 2 <= MAX_REPLY_UTF16_UNITS
    except UnicodeEncodeError:
        return False
