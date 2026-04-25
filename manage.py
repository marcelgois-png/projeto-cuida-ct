#!/usr/bin/env python
import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ct_sinfra.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django não pôde ser importado. Verifique o ambiente virtual."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

