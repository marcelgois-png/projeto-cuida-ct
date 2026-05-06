from .settings import *  # noqa: F401, F403

# Usa storage simples para não exigir collectstatic durante os testes.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
