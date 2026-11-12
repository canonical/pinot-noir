import hashlib


def gravatar_url(user) -> str:
    """Return a Gravatar URL from a Django user's email, or an empty string."""
    email = getattr(user, "email", "").strip().lower()
    if not email:
        return ""
    email_hash = hashlib.md5(email.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"https://www.gravatar.com/avatar/{email_hash}"
