"""Test settings — use SQLite in-memory so tests run without MySQL."""
from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Silence password hasher for faster user creation
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
