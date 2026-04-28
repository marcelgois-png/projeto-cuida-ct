from .settings import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Skip migrations so Django creates tables directly from models,
# avoiding MySQL-specific SQL (RENAME TABLE) in historical migrations.
MIGRATION_MODULES = {
    "accounts": None,
    "core": None,
    "tracker": None,
}

# Use simple static files storage — no manifest required in tests.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
