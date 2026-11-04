import re


def to_e164(raw):
    """Turn a Zimbabwean mobile number into +263... form, or return None."""
    cleaned = re.sub(r'[^\d+]', '', raw or '')
    if re.fullmatch(r'\+263(7[1378])\d{7}', cleaned):
        return cleaned
    if re.fullmatch(r'263(7[1378])\d{7}', cleaned):
        return '+' + cleaned
    if re.fullmatch(r'07[1378]\d{7}', cleaned):
        return '+263' + cleaned[1:]
    return None