from __future__ import annotations

from django.http import HttpRequest


def sidebar_badges(request: HttpRequest) -> dict:
    """Inject sidebar badge counts for director-only nav items."""
    if not request.user.is_authenticated or not getattr(request.user, "is_director", False):
        return {}

    from apps.tracker.models import EncaminhamentoDiretor, Requisicao  # noqa: PLC0415

    decisoes_count = Requisicao.objects.filter(
        status_processo_diretor=Requisicao.StatusProcessoDiretor.AGUARDANDO_DECISAO
    ).count()

    assessoria_count = EncaminhamentoDiretor.objects.exclude(
        status=EncaminhamentoDiretor.StatusEncaminhamento.CONCLUIDO
    ).count()

    return {
        "sidebar_decisoes_count": decisoes_count,
        "sidebar_assessoria_count": assessoria_count,
    }
