from __future__ import annotations

from functools import wraps

from django.core.cache import cache
from django.http import JsonResponse


def get_client_ip(request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def rate_limit(requests: int = 60, window: int = 60):
    """
    Limita chamadas por IP. Padrão: 60 requisições por minuto.
    Retorna 429 quando o limite é excedido.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            ip = get_client_ip(request)
            key = f"rl:{view_func.__module__}.{view_func.__name__}:{ip}"
            count = cache.get(key, 0)
            if count >= requests:
                return JsonResponse(
                    {"erro": "Limite de requisições excedido. Tente novamente em instantes."},
                    status=429,
                )
            cache.set(key, count + 1, timeout=window)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
