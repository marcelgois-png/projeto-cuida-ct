from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from io import StringIO
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Prefetch, Q, QuerySet
from django.forms.models import model_to_dict
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView

from .forms import AcompanhamentoRequisicaoFormSet, ImportacaoForm, RequisicaoForm
from .importers import WorkbookImporter
from .domain import clean_display_text, derive_situation, resolve_status_sipac_metadata
from .models import (
    AcompanhamentoRequisicao,
    Empresa,
    EncaminhamentoDiretor,
    GUTParametro,
    ImportacaoArquivo,
    NotaEmpenho,
    Predio,
    RegraPrioridade,
    ReforcoEmpenho,
    Requisicao,
    Requisitante,
    StatusSipacOpcao,
    TaxonomiaServico,
)
from apps.accounts.views import AdminRequiredMixin, user_is_admin
from .services import (
    calculate_execution_days,
    climatization_investment_for_queryset,
    control_panel_analytics,
    control_panel_macrostatus_catalog,
    metrics_for_queryset,
    resolve_control_panel_macrostatus,
    serialize_requisicao,
    service_panel_for_queryset,
    status_sipac_catalog,
    status_sipac_display,
    status_sipac_lookup,
)

TABLE_PAGE_SIZE = 25
PAGINATION_EDGE_PAGES = 2
PAGINATION_WINDOW_PAGES = 2


def user_is_operator(request: HttpRequest) -> bool:
    return bool(request.user.is_authenticated and getattr(request.user, "is_operator", False))


def user_is_admin(request: HttpRequest) -> bool:
    return bool(request.user.is_authenticated and getattr(request.user, "is_admin", False))


def user_is_director(request: HttpRequest) -> bool:
    return bool(request.user.is_authenticated and getattr(request.user, "is_director", False))


class OperatorRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return user_is_operator(self.request)


class DirectorRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return user_is_director(self.request)


class InternalViewerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return user_is_operator(self.request) or user_is_director(self.request)


SORTABLE_COLUMNS = {
    "codigo": ("ano", "numero", "codigo"),
    "assunto": ("assunto", "codigo"),
    "requisitante": ("nome_requisitante_snapshot", "codigo"),
    "prioridade": ("prioridade_final", "codigo"),
    "dias_abertura": ("data_cadastro", "codigo"),
    "status": ("status_fluxo", "situacao_texto", "codigo"),
    "status_sipac": ("status_sipac", "codigo"),
    "situacao": ("situacao_requisicao", "codigo"),
    "link_sipac": ("link_sipac", "codigo"),
    "gravidade": ("gravidade", "codigo"),
    "urgencia": ("urgencia", "codigo"),
    "tendencia": ("tendencia", "codigo"),
    "gut": ("gut_score", "codigo"),
    "empresa": ("empresa", "codigo"),
}

ORCAMENTO_SORTABLE_COLUMNS = {
    "codigo": ("ano", "numero", "codigo"),
    "assunto": ("assunto", "codigo"),
    "orcamento_valor": ("orcamento_valor", "codigo"),
    "tipo_servico": ("tipo_servico", "codigo"),
    "servico": ("servico", "codigo"),
    "empresa": ("empresa", "codigo"),
    "nota_empenho": ("nota_empenho__nota_empenho", "codigo"),
}

CONTROL_PANEL_SERVICE_SORTABLE_COLUMNS = ("tipo_servico", "ativas", "inativas", "total")
CONTROL_PANEL_STATUS_SORTABLE_COLUMNS = ("macrostatus", "status_sipac", "total")
CONTROL_PANEL_ANNUAL_SORTABLE_COLUMNS = ("ano", "quantidade", "orcamento_total", "dias_execucao")
CONTROL_PANEL_OLDEST_ACTIVE_SORTABLE_COLUMNS = ("codigo", "divisao", "predio", "status", "dias", "prioridade", "triagem")

FILTER_OPTION_DEFINITIONS = {
    "divisao": {"lookup": "divisao", "output": "divisoes"},
    "status_sipac": {"lookup": "status_sipac", "output": "statuses", "kind": "status"},
    "situacao_requisicao": {"lookup": "situacao_requisicao", "output": "situacoes"},
    "prioridade_final": {"lookup": "prioridade_final", "output": "prioridades"},
    "sinfra_responsavel": {"lookup": "sinfra_responsavel", "output": "sinfras"},
    "requisitante": {"lookup": "nome_requisitante_snapshot", "output": "requisitantes"},
    "unidade_setor": {"lookup": "unidade_setor_snapshot", "output": "unidades_setor"},
    "tipo_servico": {"lookup": "tipo_servico", "output": "tipos_servico"},
    "servico": {"lookup": "servico", "output": "servicos"},
    "predio": {"lookup": "predio__nome", "output": "predios"},
}


def ordering_for_request(request: HttpRequest) -> list[object]:
    sort = request.GET.get("sort", "codigo").strip()
    direction = request.GET.get("dir", "desc").strip().lower()
    if sort not in SORTABLE_COLUMNS:
        sort = "codigo"
    if direction not in {"asc", "desc"}:
        direction = "desc"
    if sort == "dias_abertura":
        if direction == "asc":
            return [F("data_cadastro").desc(nulls_last=True), "codigo"]
        return [F("data_cadastro").asc(nulls_last=True), "codigo"]
    prefix = "-" if direction == "desc" else ""
    return [f"{prefix}{field}" for field in SORTABLE_COLUMNS[sort]]


def orcamento_ordering_for_request(request: HttpRequest) -> list[object]:
    sort = request.GET.get("sort", "codigo").strip()
    direction = request.GET.get("dir", "desc").strip().lower()
    if sort not in ORCAMENTO_SORTABLE_COLUMNS:
        sort = "codigo"
    if direction not in {"asc", "desc"}:
        direction = "desc"
    if sort in {"orcamento_valor", "nota_empenho"}:
        field = ORCAMENTO_SORTABLE_COLUMNS[sort][0]
        if direction == "asc":
            return [F(field).asc(nulls_last=True), "codigo"]
        return [F(field).desc(nulls_last=True), "codigo"]
    prefix = "-" if direction == "desc" else ""
    return [f"{prefix}{field}" for field in ORCAMENTO_SORTABLE_COLUMNS[sort]]


def orcamento_sort_context(request: HttpRequest) -> dict[str, Any]:
    current_sort = request.GET.get("sort", "codigo").strip()
    current_dir = request.GET.get("dir", "desc").strip().lower()
    if current_sort not in ORCAMENTO_SORTABLE_COLUMNS:
        current_sort = "codigo"
    if current_dir not in {"asc", "desc"}:
        current_dir = "desc"
    params = request.GET.copy()
    sort_links: dict[str, dict[str, str | bool]] = {}
    for key in ORCAMENTO_SORTABLE_COLUMNS:
        sort_params = params.copy()
        next_dir = "asc"
        if current_sort == key and current_dir == "asc":
            next_dir = "desc"
        sort_params["sort"] = key
        sort_params["dir"] = next_dir
        sort_links[key] = {
            "querystring": sort_params.urlencode(),
            "active": current_sort == key,
            "direction": current_dir if current_sort == key else "",
        }
    return {
        "orcamento_sort_links": sort_links,
        "orcamento_querystring": params.urlencode(),
    }


def base_queryset(*, public: bool = False) -> QuerySet[Requisicao]:
    queryset = Requisicao.objects.select_related("predio", "requisitante").all()
    if public:
        queryset = queryset.filter(visivel_publicamente=True)
    return queryset


def acompanhamento_prefetch() -> Prefetch:
    return Prefetch(
        "acompanhamentos",
        queryset=AcompanhamentoRequisicao.objects.select_related("usuario").order_by("data", "criado_em", "pk"),
    )


def save_acompanhamento_formset(
    acompanhamento_formset: AcompanhamentoRequisicaoFormSet,
    *,
    requisicao: Requisicao,
    user,
) -> list[AcompanhamentoRequisicao]:
    created_acompanhamentos: list[AcompanhamentoRequisicao] = []
    for acompanhamento in acompanhamento_formset.save(commit=False):
        is_new = acompanhamento.pk is None
        acompanhamento.requisicao = requisicao
        if is_new and getattr(user, "is_authenticated", False):
            acompanhamento.usuario = user
        acompanhamento.save()
        if is_new:
            created_acompanhamentos.append(acompanhamento)
    return created_acompanhamentos


def _request_params(request_or_params: HttpRequest | Any):
    return request_or_params.GET if hasattr(request_or_params, "GET") else request_or_params


def _apply_request_filters(
    queryset: QuerySet[Requisicao],
    request_or_params,
    *,
    public: bool = False,
    exclude_keys: set[str] | None = None,
) -> QuerySet[Requisicao]:
    params = _request_params(request_or_params)
    exclude_keys = exclude_keys or set()

    query = params.get("q", "").strip()
    if query and "q" not in exclude_keys:
        queryset = queryset.filter(
            Q(codigo__icontains=query)
            | Q(assunto__icontains=query)
            | Q(local_servico__icontains=query)
            | Q(nome_requisitante_snapshot__icontains=query)
        )

    for key, definition in FILTER_OPTION_DEFINITIONS.items():
        if key in exclude_keys:
            continue
        value = params.get(key, "").strip()
        if value:
            queryset = queryset.filter(**{definition["lookup"]: value})

    if not public and "visivel_publicamente" not in exclude_keys and params.get("visivel_publicamente") in {"true", "false"}:
        queryset = queryset.filter(visivel_publicamente=params.get("visivel_publicamente") == "true")

    if "force_active" not in exclude_keys and params.get("force_active") == "true":
        queryset = queryset.filter(situacao_requisicao__iexact="Ativa")

    if "ano" not in exclude_keys:
        selected_year = params.get("ano", "").strip()
        if selected_year.isdigit():
            year = int(selected_year)
            queryset = queryset.filter(Q(ano=year) | Q(ano__isnull=True, data_cadastro__year=year))

    if "macrostatus" not in exclude_keys:
        macrostatus = params.get("macrostatus", "").strip()
        valid_macrostatuses = {item["key"] for item in control_panel_macrostatus_catalog()}
        if macrostatus in valid_macrostatuses:
            matching_ids = [
                pk
                for pk, status_sipac, situacao_requisicao in queryset.values_list("pk", "status_sipac", "situacao_requisicao")
                if resolve_control_panel_macrostatus(status_sipac, situacao_requisicao) == macrostatus
            ]
            queryset = queryset.filter(pk__in=matching_ids)

    dias_min = params.get("dias_min", "").strip()
    dias_max = params.get("dias_max", "").strip()
    if dias_min and dias_min.isdigit() and "dias_min" not in exclude_keys:
        limit_date = date.today() - timedelta(days=int(dias_min))
        queryset = queryset.filter(data_cadastro__lte=limit_date)
    if dias_max and dias_max.isdigit() and "dias_max" not in exclude_keys:
        limit_date = date.today() - timedelta(days=int(dias_max))
        queryset = queryset.filter(data_cadastro__gte=limit_date)

    return queryset


def _distinct_filter_values(queryset: QuerySet[Requisicao], lookup: str) -> list[str]:
    return list(
        queryset.exclude(**{f"{lookup}__isnull": True})
        .exclude(**{lookup: ""})
        .values_list(lookup, flat=True)
        .distinct()
        .order_by(lookup)
    )


def _status_filter_catalog(values: list[str]) -> list[dict[str, Any]]:
    allowed_values = {value.strip() for value in values if isinstance(value, str) and value.strip()}
    if not allowed_values:
        return []
    return [item for item in status_sipac_catalog(values) if item["value"] in allowed_values]


def _macrostatus_filter_catalog(queryset: QuerySet[Requisicao]) -> list[dict[str, str]]:
    catalog = control_panel_macrostatus_catalog()
    available_keys = {item["key"]: False for item in catalog}
    for status_sipac, situacao in queryset.values_list("status_sipac", "situacao_requisicao"):
        available_keys[resolve_control_panel_macrostatus(status_sipac, situacao)] = True
    return [item for item in catalog if available_keys.get(item["key"])]


def _year_filter_values(queryset: QuerySet[Requisicao]) -> list[int]:
    years: set[int] = set()
    for ano, data_cadastro in queryset.values_list("ano", "data_cadastro"):
        if ano is not None:
            years.add(ano)
        elif data_cadastro:
            years.add(data_cadastro.year)
    return sorted(years)


def _basic_filter_options(queryset: QuerySet[Requisicao]) -> dict[str, Any]:
    status_values = _distinct_filter_values(queryset, "status_sipac")
    return {
        "divisoes": _distinct_filter_values(queryset, "divisao"),
        "statuses": _status_filter_catalog(status_values),
        "situacoes": _distinct_filter_values(queryset, "situacao_requisicao"),
        "prioridades": _distinct_filter_values(queryset, "prioridade_final"),
        "sinfras": _distinct_filter_values(queryset, "sinfra_responsavel"),
        "requisitantes": _distinct_filter_values(queryset, "nome_requisitante_snapshot"),
        "unidades_setor": _distinct_filter_values(queryset, "unidade_setor_snapshot"),
        "tipos_servico": _distinct_filter_values(queryset, "tipo_servico"),
        "servicos": _distinct_filter_values(queryset, "servico"),
        "predios": _distinct_filter_values(queryset, "predio__nome"),
        "macrostatuses": _macrostatus_filter_catalog(queryset),
        "anos": _year_filter_values(queryset),
    }


def _smart_filter_options(
    queryset: QuerySet[Requisicao],
    request: HttpRequest,
    *,
    public: bool = False,
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for key, definition in FILTER_OPTION_DEFINITIONS.items():
        option_queryset = _apply_request_filters(queryset, request, public=public, exclude_keys={key})
        values = _distinct_filter_values(option_queryset, definition["lookup"])
        if definition.get("kind") == "status":
            options[definition["output"]] = _status_filter_catalog(values)
        else:
            options[definition["output"]] = values
    macrostatus_queryset = _apply_request_filters(queryset, request, public=public, exclude_keys={"macrostatus"})
    options["macrostatuses"] = _macrostatus_filter_catalog(macrostatus_queryset)
    years_queryset = _apply_request_filters(queryset, request, public=public, exclude_keys={"ano"})
    options["anos"] = _year_filter_values(years_queryset)
    return options


def filtered_queryset(request: HttpRequest, *, public: bool = False) -> QuerySet[Requisicao]:
    queryset = _apply_request_filters(base_queryset(public=public), request, public=public)
    return queryset.order_by(*ordering_for_request(request))


def has_active_filters(request: HttpRequest) -> bool:
    ignored_keys = {"sort", "dir", "page", "force_active"}
    for key, values in request.GET.lists():
        if key in ignored_keys:
            continue
        if any(value.strip() for value in values):
            return True
    return False


def format_table_count_label(filtered_count: int, total_count: int, has_filters: bool) -> str:
    if has_filters:
        return f"{filtered_count} de {total_count}"
    return str(total_count)


def _page_querystring(params, page_number: int) -> str:
    page_params = params.copy()
    page_params["page"] = str(page_number)
    return page_params.urlencode()


def _pagination_pages(page_obj) -> list[dict[str, Any]]:
    current_page = page_obj.number
    total_pages = page_obj.paginator.num_pages
    visible_pages: set[int] = set()
    for page_number in range(1, total_pages + 1):
        near_start = page_number <= PAGINATION_EDGE_PAGES
        near_end = page_number > total_pages - PAGINATION_EDGE_PAGES
        near_current = abs(page_number - current_page) <= PAGINATION_WINDOW_PAGES
        if near_start or near_end or near_current:
            visible_pages.add(page_number)

    pages: list[dict[str, Any]] = []
    previous_page = 0
    for page_number in sorted(visible_pages):
        if previous_page and page_number - previous_page > 1:
            pages.append({"ellipsis": True})
        pages.append(
            {
                "number": page_number,
                "current": page_number == current_page,
                "ellipsis": False,
            }
        )
        previous_page = page_number
    return pages


def table_context(request: HttpRequest, *, public: bool = False) -> dict[str, Any]:
    queryset = filtered_queryset(request, public=public)
    filtered_count = queryset.count()
    total_count = base_queryset(public=public).count()
    filters_active = has_active_filters(request)
    paginator = Paginator(queryset, TABLE_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    page_items = list(page_obj.object_list)
    lookup = status_sipac_lookup([item.status_sipac for item in page_items])
    for item in page_items:
        item.status_sipac_exibicao = status_sipac_display(item.status_sipac, lookup)
    page_obj.object_list = page_items
    current_sort = request.GET.get("sort", "codigo").strip()
    current_dir = request.GET.get("dir", "desc").strip().lower()
    if current_sort not in SORTABLE_COLUMNS:
        current_sort = "codigo"
    if current_dir not in {"asc", "desc"}:
        current_dir = "desc"
    params = request.GET.copy()
    params.pop("page", None)
    pagination_pages = _pagination_pages(page_obj)
    for page in pagination_pages:
        if not page["ellipsis"]:
            page["querystring"] = _page_querystring(params, page["number"])
    sort_links: dict[str, dict[str, str | bool]] = {}
    for key in SORTABLE_COLUMNS:
        sort_params = params.copy()
        next_dir = "asc"
        if current_sort == key and current_dir == "asc":
            next_dir = "desc"
        sort_params["sort"] = key
        sort_params["dir"] = next_dir
        sort_links[key] = {
            "querystring": sort_params.urlencode(),
            "active": current_sort == key,
            "direction": current_dir if current_sort == key else "",
        }
    return {
        "page_obj": page_obj,
        "public_mode": public,
        "querystring": params.urlencode(),
        "sort_links": sort_links,
        "table_target": "#public-results" if public else "#internal-results",
        "table_url": reverse("public-requisicoes-table" if public else "internal-requisicoes-table"),
        "filtered_count": filtered_count,
        "total_count": total_count,
        "has_active_filters": filters_active,
        "table_count_label": format_table_count_label(filtered_count, total_count, filters_active),
        "pagination_pages": pagination_pages,
        "previous_page_querystring": (
            _page_querystring(params, page_obj.previous_page_number())
            if page_obj.has_previous()
            else ""
        ),
        "next_page_querystring": (
            _page_querystring(params, page_obj.next_page_number())
            if page_obj.has_next()
            else ""
        ),
    }


def filter_options(
    public: bool = False,
    *,
    queryset: QuerySet[Requisicao] | None = None,
    request: HttpRequest | None = None,
) -> dict[str, Any]:
    if queryset is None:
        queryset = Requisicao.objects.all()
        if public:
            queryset = queryset.filter(visivel_publicamente=True)
    if request is not None:
        return _smart_filter_options(queryset, request, public=public)
    return _basic_filter_options(queryset)


def _control_panel_base_queryset() -> QuerySet[Requisicao]:
    return base_queryset(public=True)


def _control_panel_has_active_filters(request: HttpRequest) -> bool:
    for key in (
        "q",
        "divisao",
        "tipo_servico",
        "servico",
        "situacao_requisicao",
        "macrostatus",
        "status_sipac",
        "predio",
        "requisitante",
        "unidade_setor",
        "ano",
        "dias_min",
        "dias_max",
    ):
        if request.GET.get(key, "").strip():
            return True
    return False


def _control_panel_service_sort_state(request: HttpRequest) -> tuple[str, str]:
    sort = request.GET.get("service_sort", "total").strip()
    direction = request.GET.get("service_dir", "desc").strip().lower()
    if sort not in CONTROL_PANEL_SERVICE_SORTABLE_COLUMNS:
        sort = "total"
    if direction not in {"asc", "desc"}:
        direction = "desc"
    return sort, direction


def _sort_control_panel_service_groups(
    groups: list[dict[str, Any]],
    *,
    sort: str,
    direction: str,
) -> list[dict[str, Any]]:
    rows = list(groups)
    reverse = direction == "desc"
    if sort == "tipo_servico":
        rows.sort(key=lambda entry: clean_display_text(entry.get("tipo_servico", "")).lower(), reverse=reverse)
        return rows

    metric_key = "quantidade" if sort == "total" else sort
    rows.sort(key=lambda entry: clean_display_text(entry.get("tipo_servico", "")).lower())
    rows.sort(key=lambda entry: int(entry.get(metric_key) or 0), reverse=reverse)
    return rows


def _control_panel_service_sort_links(request: HttpRequest) -> dict[str, dict[str, str | bool]]:
    current_sort, current_dir = _control_panel_service_sort_state(request)
    params = request.GET.copy()
    sort_links: dict[str, dict[str, str | bool]] = {}
    for key in CONTROL_PANEL_SERVICE_SORTABLE_COLUMNS:
        sort_params = params.copy()
        next_dir = "asc"
        if current_sort == key and current_dir == "asc":
            next_dir = "desc"
        sort_params["service_sort"] = key
        sort_params["service_dir"] = next_dir
        sort_links[key] = {
            "querystring": sort_params.urlencode(),
            "active": current_sort == key,
            "direction": current_dir if current_sort == key else "",
        }
    return sort_links


def _control_panel_status_sort_state(request: HttpRequest) -> tuple[str, str]:
    sort = request.GET.get("status_sort", "").strip()
    direction = request.GET.get("status_dir", "asc").strip().lower()
    if sort not in CONTROL_PANEL_STATUS_SORTABLE_COLUMNS:
        sort = ""
    if direction not in {"asc", "desc"}:
        direction = "asc"
    return sort, direction


def _sort_control_panel_raw_status_breakdown(
    rows: list[dict[str, Any]],
    *,
    sort: str,
    direction: str,
) -> list[dict[str, Any]]:
    sorted_rows = list(rows)
    reverse = direction == "desc"
    if sort == "macrostatus":
        sorted_rows.sort(key=lambda entry: clean_display_text(entry.get("macrostatus", "")).lower(), reverse=reverse)
        return sorted_rows
    if sort == "status_sipac":
        sorted_rows.sort(key=lambda entry: clean_display_text(entry.get("label", "")).lower(), reverse=reverse)
        return sorted_rows
    if sort == "total":
        sorted_rows.sort(key=lambda entry: clean_display_text(entry.get("label", "")).lower())
        sorted_rows.sort(key=lambda entry: int(entry.get("total") or 0), reverse=reverse)
        return sorted_rows
    return sorted_rows


def _control_panel_status_sort_links(request: HttpRequest) -> dict[str, dict[str, str | bool]]:
    current_sort, current_dir = _control_panel_status_sort_state(request)
    params = request.GET.copy()
    sort_links: dict[str, dict[str, str | bool]] = {}
    for key in CONTROL_PANEL_STATUS_SORTABLE_COLUMNS:
        sort_params = params.copy()
        next_dir = "asc"
        if current_sort == key and current_dir == "asc":
            next_dir = "desc"
        sort_params["status_sort"] = key
        sort_params["status_dir"] = next_dir
        sort_links[key] = {
            "querystring": sort_params.urlencode(),
            "active": current_sort == key,
            "direction": current_dir if current_sort == key else "",
        }
    return sort_links


def _control_panel_table_sort_state(
    request: HttpRequest,
    *,
    sort_param: str,
    dir_param: str,
    allowed: tuple[str, ...],
    default_sort: str,
    default_dir: str,
) -> tuple[str, str]:
    sort = request.GET.get(sort_param, default_sort).strip()
    direction = request.GET.get(dir_param, default_dir).strip().lower()
    if sort not in allowed:
        sort = default_sort
    if direction not in {"asc", "desc"}:
        direction = default_dir
    return sort, direction


def _control_panel_table_sort_links(
    request: HttpRequest,
    *,
    allowed: tuple[str, ...],
    current_sort: str,
    current_dir: str,
    sort_param: str,
    dir_param: str,
) -> dict[str, dict[str, str | bool]]:
    params = request.GET.copy()
    sort_links: dict[str, dict[str, str | bool]] = {}
    for key in allowed:
        sort_params = params.copy()
        next_dir = "asc"
        if current_sort == key and current_dir == "asc":
            next_dir = "desc"
        sort_params[sort_param] = key
        sort_params[dir_param] = next_dir
        sort_links[key] = {
            "querystring": sort_params.urlencode(),
            "active": current_sort == key,
            "direction": current_dir if current_sort == key else "",
        }
    return sort_links


def _sort_rows_with_nullable_numeric_value(
    rows: list[Any],
    *,
    key_func,
    reverse: bool,
) -> list[Any]:
    non_null_rows = [row for row in rows if key_func(row) is not None]
    null_rows = [row for row in rows if key_func(row) is None]
    non_null_rows.sort(key=key_func, reverse=reverse)
    return non_null_rows + null_rows


def _average_non_null(values: list[Any]) -> int | None:
    numeric_values = [float(value) for value in values if value is not None]
    if not numeric_values:
        return None
    return int(round(sum(numeric_values) / len(numeric_values)))


def _sort_control_panel_annual_summary(
    rows: list[dict[str, Any]],
    *,
    sort: str,
    direction: str,
) -> list[dict[str, Any]]:
    sorted_rows = list(rows)
    reverse = direction == "desc"
    if sort == "ano":
        sorted_rows.sort(key=lambda row: int(row.get("ano") or 0), reverse=reverse)
    elif sort == "quantidade":
        sorted_rows.sort(key=lambda row: int(row.get("quantidade") or 0), reverse=reverse)
    elif sort == "orcamento_total":
        sorted_rows.sort(key=lambda row: row.get("orcamento_total") or 0, reverse=reverse)
    elif sort == "dias_execucao":
        sorted_rows = _sort_rows_with_nullable_numeric_value(
            sorted_rows,
            key_func=lambda row: row.get("dias_execucao"),
            reverse=reverse,
        )
    return sorted_rows


def _sort_control_panel_quantity_matrix(
    matrix: dict[str, Any],
    *,
    sort: str,
    direction: str,
) -> dict[str, Any]:
    years = list(matrix.get("years", []))
    sorted_rows = list(matrix.get("rows", []))
    reverse = direction == "desc"
    if sort == "divisao":
        sorted_rows.sort(key=lambda row: clean_display_text(row.get("divisao", "")).lower(), reverse=reverse)
    elif sort == "total":
        sorted_rows.sort(key=lambda row: clean_display_text(row.get("divisao", "")).lower())
        sorted_rows.sort(key=lambda row: int(row.get("total") or 0), reverse=reverse)
    elif sort.startswith("year_"):
        year_text = sort.removeprefix("year_")
        if year_text.isdigit():
            year = int(year_text)
            if year in years:
                sorted_rows.sort(key=lambda row: clean_display_text(row.get("divisao", "")).lower())
                sorted_rows.sort(
                    key=lambda row: int((row.get("years") or {}).get(year) or 0),
                    reverse=reverse,
                )
    return {
        "years": years,
        "rows": sorted_rows,
        "total_row": matrix.get("total_row", {}),
    }


def _sort_control_panel_wait_matrix(
    matrix: dict[str, Any],
    *,
    sort: str,
    direction: str,
) -> dict[str, Any]:
    years = list(matrix.get("years", []))
    sorted_rows = []
    for row in matrix.get("rows", []):
        years_map = dict(row.get("years", {}))
        row_average = _average_non_null([years_map.get(year) for year in years])
        sorted_rows.append(
            {
                **row,
                "years": years_map,
                "media": row_average,
            }
        )

    total_row_raw = dict(matrix.get("total_row", {}))
    total_years = dict(total_row_raw.get("years", {}))
    total_row = {
        **total_row_raw,
        "years": total_years,
        "media": _average_non_null([total_years.get(year) for year in years]),
    }

    reverse = direction == "desc"
    if sort == "divisao":
        sorted_rows.sort(key=lambda row: clean_display_text(row.get("divisao", "")).lower(), reverse=reverse)
    elif sort == "media":
        sorted_rows.sort(key=lambda row: clean_display_text(row.get("divisao", "")).lower())
        sorted_rows = _sort_rows_with_nullable_numeric_value(
            sorted_rows,
            key_func=lambda row: row.get("media"),
            reverse=reverse,
        )
    elif sort.startswith("year_"):
        year_text = sort.removeprefix("year_")
        if year_text.isdigit():
            year = int(year_text)
            if year in years:
                sorted_rows.sort(key=lambda row: clean_display_text(row.get("divisao", "")).lower())
                sorted_rows = _sort_rows_with_nullable_numeric_value(
                    sorted_rows,
                    key_func=lambda row: (row.get("years") or {}).get(year),
                    reverse=reverse,
                )
    return {
        "years": years,
        "rows": sorted_rows,
        "total_row": total_row,
    }


def _oldest_active_sort_value(item: Any, sort: str) -> Any:
    if sort == "codigo":
        return clean_display_text(getattr(item, "codigo", ""))
    if sort == "divisao":
        return clean_display_text(getattr(item, "divisao", ""))
    if sort == "predio":
        predio = getattr(item, "predio", None)
        if predio:
            return clean_display_text(getattr(predio, "nome", ""))
        return clean_display_text(getattr(item, "local_servico", ""))
    if sort == "status":
        return clean_display_text(getattr(item, "status_sipac_exibicao", "") or getattr(item, "status_sipac", ""))
    if sort == "dias":
        return getattr(item, "control_days", None)
    if sort == "prioridade":
        return clean_display_text(getattr(item, "prioridade_final", ""))
    if sort == "triagem":
        return getattr(item, "pk", None)
    return ""


def _sort_control_panel_oldest_active(
    rows: list[Any],
    *,
    sort: str,
    direction: str,
) -> list[Any]:
    sorted_rows = list(rows)
    reverse = direction == "desc"
    if sort in {"dias", "triagem"}:
        return _sort_rows_with_nullable_numeric_value(
            sorted_rows,
            key_func=lambda item: _oldest_active_sort_value(item, sort),
            reverse=reverse,
        )
    sorted_rows.sort(key=lambda item: clean_display_text(getattr(item, "codigo", "")).lower())
    sorted_rows.sort(
        key=lambda item: str(_oldest_active_sort_value(item, sort)).lower(),
        reverse=reverse,
    )
    return sorted_rows


def _control_panel_filtered_queryset(request: HttpRequest) -> QuerySet[Requisicao]:
    queryset = _control_panel_option_queryset(request)
    return queryset


def _control_panel_years(queryset: QuerySet[Requisicao] | None = None) -> list[int]:
    source_queryset = queryset if queryset is not None else _control_panel_base_queryset()
    years: set[int] = set()
    for ano, data_cadastro in source_queryset.values_list("ano", "data_cadastro"):
        if ano is not None:
            years.add(ano)
        elif data_cadastro:
            years.add(data_cadastro.year)
    return sorted(years)


def _control_panel_option_queryset(
    request: HttpRequest,
    *,
    exclude_keys: set[str] | None = None,
) -> QuerySet[Requisicao]:
    exclude_keys = exclude_keys or set()
    return _apply_request_filters(
        _control_panel_base_queryset(),
        request,
        public=True,
        exclude_keys=exclude_keys,
    )


def _control_panel_macrostatus_options(request: HttpRequest | None = None) -> list[dict[str, str]]:
    catalog = control_panel_macrostatus_catalog()
    if request is None:
        return catalog

    queryset = _control_panel_option_queryset(request, exclude_keys={"macrostatus"})
    available_keys = {
        item["key"]: False
        for item in catalog
    }
    for status_sipac, situacao in queryset.values_list("status_sipac", "situacao_requisicao"):
        available_keys[resolve_control_panel_macrostatus(status_sipac, situacao)] = True
    return [item for item in catalog if available_keys.get(item["key"])]


def _control_panel_filters_context(request: HttpRequest | None = None) -> dict[str, Any]:
    if request is None:
        filters = _basic_filter_options(_control_panel_base_queryset())
        filters["macrostatuses"] = _control_panel_macrostatus_options()
        filters["anos"] = _control_panel_years()
        return filters

    filters: dict[str, Any] = {}
    for key in (
        "divisao",
        "tipo_servico",
        "servico",
        "situacao_requisicao",
        "status_sipac",
        "predio",
        "requisitante",
        "unidade_setor",
    ):
        definition = FILTER_OPTION_DEFINITIONS[key]
        option_queryset = _control_panel_option_queryset(request, exclude_keys={key})
        values = _distinct_filter_values(option_queryset, definition["lookup"])
        if definition.get("kind") == "status":
            filters[definition["output"]] = _status_filter_catalog(values)
        else:
            filters[definition["output"]] = values
    filters["macrostatuses"] = _control_panel_macrostatus_options(request)
    filters["anos"] = _control_panel_years(_control_panel_option_queryset(request, exclude_keys={"ano"}))
    return filters


def _control_panel_content_context(request: HttpRequest) -> dict[str, Any]:
    macrostatus = request.GET.get("macrostatus", "").strip()
    if macrostatus and macrostatus not in {item["key"] for item in control_panel_macrostatus_catalog()}:
        macrostatus = ""
    service_sort, service_dir = _control_panel_service_sort_state(request)
    status_sort, status_dir = _control_panel_status_sort_state(request)
    annual_sort, annual_dir = _control_panel_table_sort_state(
        request,
        sort_param="annual_sort",
        dir_param="annual_dir",
        allowed=CONTROL_PANEL_ANNUAL_SORTABLE_COLUMNS,
        default_sort="ano",
        default_dir="asc",
    )
    oldest_sort, oldest_dir = _control_panel_table_sort_state(
        request,
        sort_param="oldest_sort",
        dir_param="oldest_dir",
        allowed=CONTROL_PANEL_OLDEST_ACTIVE_SORTABLE_COLUMNS,
        default_sort="dias",
        default_dir="desc",
    )

    control_panel_return_url = reverse("public-control-panel")
    current_query = request.GET.urlencode()
    if current_query:
        control_panel_return_url = f"{control_panel_return_url}?{current_query}"

    filtered_queryset = _control_panel_filtered_queryset(request)
    analytics = control_panel_analytics(
        filtered_queryset,
        macrostatus_filter=macrostatus,
        include_internal=user_is_operator(request) or user_is_director(request),
        years=_control_panel_years(filtered_queryset),
    )
    analytics["service_groups"] = _sort_control_panel_service_groups(
        analytics.get("service_groups", []),
        sort=service_sort,
        direction=service_dir,
    )
    analytics["raw_status_breakdown"] = _sort_control_panel_raw_status_breakdown(
        analytics.get("raw_status_breakdown", []),
        sort=status_sort,
        direction=status_dir,
    )
    analytics["annual_summary"] = _sort_control_panel_annual_summary(
        analytics.get("annual_summary", []),
        sort=annual_sort,
        direction=annual_dir,
    )

    quantity_matrix = analytics.get("division_year_quantity_matrix", {})
    quantity_years = list(quantity_matrix.get("years", []))
    quantity_year_sort_keys = {year: f"year_{year}" for year in quantity_years}
    quantity_allowed = ("divisao", *tuple(quantity_year_sort_keys.values()), "total")
    quantity_sort, quantity_dir = _control_panel_table_sort_state(
        request,
        sort_param="qty_matrix_sort",
        dir_param="qty_matrix_dir",
        allowed=quantity_allowed,
        default_sort="total",
        default_dir="desc",
    )
    analytics["division_year_quantity_matrix"] = _sort_control_panel_quantity_matrix(
        quantity_matrix,
        sort=quantity_sort,
        direction=quantity_dir,
    )

    wait_matrix = analytics.get("division_year_wait_matrix", {})
    wait_years = list(wait_matrix.get("years", []))
    wait_year_sort_keys = {year: f"year_{year}" for year in wait_years}
    wait_allowed = ("divisao", *tuple(wait_year_sort_keys.values()), "media")
    wait_sort, wait_dir = _control_panel_table_sort_state(
        request,
        sort_param="wait_matrix_sort",
        dir_param="wait_matrix_dir",
        allowed=wait_allowed,
        default_sort="divisao",
        default_dir="asc",
    )
    analytics["division_year_wait_matrix"] = _sort_control_panel_wait_matrix(
        wait_matrix,
        sort=wait_sort,
        direction=wait_dir,
    )

    internal_triage = analytics.get("internal_triage")
    if isinstance(internal_triage, dict):
        internal_triage["oldest_active"] = _sort_control_panel_oldest_active(
            internal_triage.get("oldest_active", []),
            sort=oldest_sort,
            direction=oldest_dir,
        )
        analytics["internal_triage"] = internal_triage

    annual_sort_links = _control_panel_table_sort_links(
        request,
        allowed=CONTROL_PANEL_ANNUAL_SORTABLE_COLUMNS,
        current_sort=annual_sort,
        current_dir=annual_dir,
        sort_param="annual_sort",
        dir_param="annual_dir",
    )
    quantity_matrix_sort_links = _control_panel_table_sort_links(
        request,
        allowed=quantity_allowed,
        current_sort=quantity_sort,
        current_dir=quantity_dir,
        sort_param="qty_matrix_sort",
        dir_param="qty_matrix_dir",
    )
    wait_matrix_sort_links = _control_panel_table_sort_links(
        request,
        allowed=wait_allowed,
        current_sort=wait_sort,
        current_dir=wait_dir,
        sort_param="wait_matrix_sort",
        dir_param="wait_matrix_dir",
    )
    oldest_active_sort_links = _control_panel_table_sort_links(
        request,
        allowed=CONTROL_PANEL_OLDEST_ACTIVE_SORTABLE_COLUMNS,
        current_sort=oldest_sort,
        current_dir=oldest_dir,
        sort_param="oldest_sort",
        dir_param="oldest_dir",
    )

    analytics.update(
        {
            "is_internal_viewer": user_is_operator(request) or user_is_director(request),
            "has_active_filters": _control_panel_has_active_filters(request),
            "control_panel_return_url": control_panel_return_url,
            "control_panel_content_url": reverse("public-control-panel-content"),
            "service_sort_links": _control_panel_service_sort_links(request),
            "status_sort_links": _control_panel_status_sort_links(request),
            "annual_sort_links": annual_sort_links,
            "quantity_matrix_sort_links": quantity_matrix_sort_links,
            "quantity_matrix_sort_links_by_year": {
                year: quantity_matrix_sort_links.get(key, {})
                for year, key in quantity_year_sort_keys.items()
            },
            "wait_matrix_sort_links": wait_matrix_sort_links,
            "wait_matrix_sort_links_by_year": {
                year: wait_matrix_sort_links.get(key, {})
                for year, key in wait_year_sort_keys.items()
            },
            "oldest_active_sort_links": oldest_active_sort_links,
            "selected_macrostatus_label": next(
                (
                    item["label"]
                    for item in control_panel_macrostatus_catalog()
                    if item["key"] == macrostatus
                ),
                "",
            ),
        }
    )
    return analytics


def _control_panel_shell_context(request: HttpRequest) -> dict[str, Any]:
    return {
        "filters": _control_panel_filters_context(request),
        "control_panel_shell_url": reverse("public-control-panel-shell"),
        **_control_panel_content_context(request),
    }


def _public_dashboard_context(request: HttpRequest) -> dict[str, Any]:
    queryset = filtered_queryset(request, public=True)
    selected_divisao = request.GET.get("divisao", "").strip()
    metrics = metrics_for_queryset(queryset)
    metrics["investimento_requisicoes"] = climatization_investment_for_queryset(queryset)
    return {
        "metrics": metrics,
        "service_panel": service_panel_for_queryset(queryset, selected_divisao=selected_divisao),
        "filters": filter_options(public=True, request=request, queryset=base_queryset(public=True)),
        **table_context(request, public=True),
        "processos_metrics": {
            "enviados": 0,
            "ativos": 0,
            "executados": 0,
            "investimento": 0,
        },
        "modulo_processos_disponivel": False,
        "today": date.today(),
    }


def _internal_lista_context(request: HttpRequest) -> dict[str, Any]:
    return {
        "filters": filter_options(public=False, request=request, queryset=base_queryset(public=False)),
        **table_context(request, public=False),
    }


def _internal_decisoes_context(request: HttpRequest) -> dict[str, Any]:
    queryset = _director_pending_queryset(request)
    decision_query = request.GET.urlencode()
    decisoes_return_url = reverse("internal-decisoes")
    if decision_query:
        decisoes_return_url = f"{decisoes_return_url}?{decision_query}"
    pending_filtered_count = queryset.count()
    pending_total_count = _director_pending_queryset().count()
    filters_active = has_active_filters(request)
    return {
        "filters": filter_options(request=request, queryset=_director_pending_queryset()),
        "pending_requests": queryset,
        "decisoes_return_url": decisoes_return_url,
        "forward_options": _director_forward_options(),
        "total_pending": pending_total_count,
        "pending_filtered_count": pending_filtered_count,
        "pending_has_active_filters": filters_active,
        "pending_count_label": format_table_count_label(
            pending_filtered_count,
            pending_total_count,
            filters_active,
        ),
    }


def _internal_priorizacao_context(request: HttpRequest) -> dict[str, Any]:
    request.GET = request.GET.copy()
    request.GET["force_active"] = "true"
    table_data = table_context(request, public=False)
    total_active = Requisicao.objects.filter(situacao_requisicao__iexact="Ativa").count()
    gut_options = {
        "gravidade": GUTParametro.objects.filter(tipo=GUTParametro.Tipo.GRAVIDADE),
        "urgencia": GUTParametro.objects.filter(tipo=GUTParametro.Tipo.URGENCIA),
        "tendencia": GUTParametro.objects.filter(tipo=GUTParametro.Tipo.TENDENCIA),
    }
    return {
        "filters": filter_options(
            public=False,
            request=request,
            queryset=base_queryset(public=False).filter(situacao_requisicao__iexact="Ativa"),
        ),
        "gut_options": gut_options,
        "empresas_list": Empresa.objects.filter(ativa=True),
        "total_active": total_active,
        "priorizacao_count_label": format_table_count_label(
            table_data["filtered_count"],
            total_active,
            table_data["has_active_filters"],
        ),
        **table_data,
    }


class PublicDashboardView(TemplateView):
    template_name = "tracker/public_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_public_dashboard_context(self.request))
        return context


class PublicRequisicaoDetailView(DetailView):
    model = Requisicao
    template_name = "tracker/public_requisicao_detail.html"

    def get_queryset(self):
        return (
            Requisicao.objects.filter(visivel_publicamente=True)
            .select_related("predio", "requisitante")
            .prefetch_related(acompanhamento_prefetch())
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["today"] = date.today()
        context["status_sipac_exibicao"] = status_sipac_display(self.object.status_sipac)
        context["dias_para_execucao"] = calculate_execution_days(self.object)
        context["acompanhamentos"] = self.object.acompanhamentos.all()
        return context


class InternalRequisicaoDetailView(InternalViewerRequiredMixin, DetailView):
    model = Requisicao
    template_name = "tracker/internal_requisicao_detail.html"

    def get_queryset(self):
        return (
            Requisicao.objects.select_related("predio", "requisitante")
            .prefetch_related(acompanhamento_prefetch())
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["today"] = date.today()
        context["status_sipac_exibicao"] = status_sipac_display(self.object.status_sipac)
        context["dias_para_execucao"] = calculate_execution_days(self.object)
        context["acompanhamentos"] = self.object.acompanhamentos.all()
        context["can_edit_requisicao"] = user_is_operator(self.request)
        context["next_url"] = self.request.GET.get("next") or (
            reverse("internal-decisoes") if user_is_director(self.request) else reverse("internal-lista")
        )
        return context


class PublicControlPanelView(TemplateView):
    template_name = "tracker/public_control_panel.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "today": date.today(),
                **_control_panel_shell_context(self.request),
            }
        )
        return context


@require_http_methods(["GET"])
def public_control_panel_content(request: HttpRequest) -> HttpResponse:
    return render(request, "tracker/_public_control_panel_content.html", _control_panel_content_context(request))


@require_http_methods(["GET"])
def public_control_panel_shell(request: HttpRequest) -> HttpResponse:
    return render(request, "tracker/_public_control_panel_shell.html", _control_panel_shell_context(request))


class InternalCadastroView(OperatorRequiredMixin, TemplateView):
    template_name = "tracker/internal_cadastro.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Metrics without filters for the general dashboard overview
        queryset = base_queryset(public=False)
        context.update(
            {
                "metrics": metrics_for_queryset(queryset),
                "import_form": ImportacaoForm(),
                "last_imports": ImportacaoArquivo.objects.select_related("iniciado_por")[:5],
            }
        )
        return context


class InternalListaView(OperatorRequiredMixin, TemplateView):
    template_name = "tracker/internal_lista.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_internal_lista_context(self.request))
        return context


class InternalDecisoesView(DirectorRequiredMixin, TemplateView):
    template_name = "tracker/internal_decisoes.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.request.GET = self.request.GET.copy()
        context.update(_internal_decisoes_context(self.request))
        return context


class InternalEncaminhamentosView(DirectorRequiredMixin, TemplateView):
    template_name = "tracker/internal_encaminhamentos.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "encaminhamentos": EncaminhamentoDiretor.objects.select_related("diretor").prefetch_related(
                    "requisicoes__predio",
                    "requisicoes__requisitante",
                ),
                "total_encaminhamentos": EncaminhamentoDiretor.objects.count(),
            }
        )
        return context


@login_required
@require_http_methods(["POST"])
def internal_cancel_encaminhamento(request: HttpRequest, pk: int) -> HttpResponse:
    if not user_is_director(request):
        raise Http404

    encaminhamento = get_object_or_404(
        EncaminhamentoDiretor.objects.prefetch_related("requisicoes"),
        pk=pk,
    )
    requisicoes = list(encaminhamento.requisicoes.all())
    quantidade = len(requisicoes)
    numero = encaminhamento.numero

    with transaction.atomic():
        if requisicoes:
            Requisicao.objects.filter(pk__in=[item.pk for item in requisicoes]).update(
                status_processo_diretor=Requisicao.StatusProcessoDiretor.AGUARDANDO_DECISAO,
                observacao_diretor="",
                atualizado_em=timezone.now(),
            )
            for requisicao in requisicoes:
                AcompanhamentoRequisicao.objects.create(
                    requisicao=requisicao,
                    data=date.today(),
                    atualizacao_situacao=(
                        f"Encaminhamento do diretor #{numero} cancelado. "
                        "Requisi\u00e7\u00e3o devolvida para a fila de decis\u00f5es."
                    ),
                    usuario=request.user,
                )
        encaminhamento.delete()

    label = "requisição" if quantidade == 1 else "requisições"
    messages.warning(
        request,
        f"Encaminhamento #{numero} cancelado. {quantidade} {label} para Decis\u00f5es de Processo.",
    )
    return redirect("internal-encaminhamentos")


def _director_pending_queryset(request: HttpRequest | None = None) -> QuerySet[Requisicao]:
    if request is None:
        return base_queryset(public=False).filter(
            status_processo_diretor=Requisicao.StatusProcessoDiretor.AGUARDANDO_DECISAO
        )
    return filtered_queryset(request, public=False).filter(
        status_processo_diretor=Requisicao.StatusProcessoDiretor.AGUARDANDO_DECISAO
    )


def _director_decision_definition(decisao: str) -> dict[str, str] | None:
    mapping = {
        "abrir_processo": {
            "status": Requisicao.StatusProcessoDiretor.AUTORIZADO,
            "tipo": EncaminhamentoDiretor.Tipo.ABRIR_PROCESSO,
            "label": "Abrir processo",
            "badge_class": "badge-success-soft",
            "button_class": "btn-success",
            "button_icon": "bi-check-lg",
            "button_label": "Gerar encaminhamento",
            "title": "Encaminhamento para abertura de processo",
        },
        "encerrar_requisicao": {
            "status": Requisicao.StatusProcessoDiretor.NEGADO,
            "tipo": EncaminhamentoDiretor.Tipo.ENCERRAR_REQUISICAO,
            "label": "Encerrar requisi\u00e7\u00e3o",
            "badge_class": "badge-danger-soft",
            "button_class": "btn-danger",
            "button_icon": "bi-x-lg",
            "button_label": "Gerar encaminhamento",
            "title": "Encaminhamento para encerramento da requisi\u00e7\u00e3o",
        },
        "inspecionar_in_loco": {
            "status": Requisicao.StatusProcessoDiretor.INSPECAO_IN_LOCO,
            "tipo": EncaminhamentoDiretor.Tipo.INSPECIONAR_IN_LOCO,
            "label": "Inspecionar in loco",
            "badge_class": "badge-primary-soft",
            "button_class": "btn-primary",
            "button_icon": "bi-geo-alt",
            "button_label": "Gerar encaminhamento",
            "title": "Encaminhamento para inspeção in loco",
        },
    }
    return mapping.get(decisao)


def _director_forward_options() -> list[dict[str, str]]:
    return [
        {"value": "abrir_processo", "label": "Abrir Processo"},
        {"value": "encerrar_requisicao", "label": "Encerrar"},
        {"value": "inspecionar_in_loco", "label": "Inspecionar in loco"},
    ]


def _render_director_forward_modal(
    request: HttpRequest,
    *,
    requisicoes: list[Requisicao],
    decisao: str,
    orientacoes: str = "",
    form_error: str = "",
    status: int = 200,
) -> HttpResponse:
    decision_definition = _director_decision_definition(decisao)
    if decision_definition is None:
        return HttpResponse("Encaminhamento invalido.", status=400)
    return render(
        request,
        "tracker/_decisoes_encaminhamento_modal.html",
        {
            "selected_requisicoes": requisicoes,
            "decisao": decisao,
            "decision_definition": decision_definition,
            "orientacoes": orientacoes,
            "form_error": form_error,
            "today": date.today(),
        },
        status=status,
    )


@login_required
@require_http_methods(["GET"])
def internal_decisoes_table(request: HttpRequest) -> HttpResponse:
    if not user_is_director(request):
        raise Http404
    request.GET = request.GET.copy()
    return render(request, "tracker/_decisoes_pending_table.html", _internal_decisoes_context(request))


@login_required
@require_http_methods(["GET"])
def internal_decisoes_panel(request: HttpRequest) -> HttpResponse:
    if not user_is_director(request):
        raise Http404
    request.GET = request.GET.copy()
    return render(request, "tracker/_internal_decisoes_panel.html", _internal_decisoes_context(request))


@login_required
@require_http_methods(["POST"])
def internal_decision_forward_preview(request: HttpRequest) -> HttpResponse:
    if not user_is_director(request):
        raise Http404

    ids = request.POST.getlist("requisicao_ids")
    decisao = request.POST.get("decisao", "").strip()
    requisicoes = list(
        _director_pending_queryset().filter(id__in=ids).select_related("predio", "requisitante").order_by("-ano", "-numero")
    )
    if not requisicoes:
        return HttpResponse("Selecione ao menos uma requisi\u00e7\u00e3o para encaminhar.", status=400)
    if _director_decision_definition(decisao) is None:
        return HttpResponse("Selecione um tipo de encaminhamento valido.", status=400)
    return _render_director_forward_modal(request, requisicoes=requisicoes, decisao=decisao)


@login_required
@require_http_methods(["POST"])
def internal_bulk_decide_process(request: HttpRequest) -> HttpResponse:
    if not user_is_director(request):
        raise Http404

    ids = request.POST.getlist("requisicao_ids")
    decisao = request.POST.get("decisao", "").strip()
    orientacoes = request.POST.get("orientacoes", "").strip()
    decision_definition = _director_decision_definition(decisao)
    requisicoes = list(
        _director_pending_queryset().filter(id__in=ids).select_related("predio", "requisitante").order_by("-ano", "-numero")
    )

    if not requisicoes:
        messages.error(request, "Selecione ao menos uma requisi\u00e7\u00e3o para encaminhar.")
        return redirect("internal-decisoes")
    if decision_definition is None:
        return _render_director_forward_modal(
            request,
            requisicoes=requisicoes,
            decisao=decisao,
            orientacoes=orientacoes,
            form_error="Selecione um tipo de encaminhamento valido.",
        )
    if not orientacoes:
        return _render_director_forward_modal(
            request,
            requisicoes=requisicoes,
            decisao=decisao,
            orientacoes=orientacoes,
            form_error="Explique as orientacoes do diretor para o Operador antes de salvar.",
        )

    with transaction.atomic():
        encaminhamento = EncaminhamentoDiretor.objects.create(
            tipo=decision_definition["tipo"],
            orientacoes=orientacoes,
            diretor=request.user,
        )
        encaminhamento.requisicoes.add(*requisicoes)
        Requisicao.objects.filter(pk__in=[item.pk for item in requisicoes]).update(
            status_processo_diretor=decision_definition["status"],
            observacao_diretor=orientacoes,
            atualizado_em=timezone.now(),
        )
        for requisicao in requisicoes:
            AcompanhamentoRequisicao.objects.create(
                requisicao=requisicao,
                data=date.today(),
                atualizacao_situacao=(
                    f"Encaminhamento do diretor #{encaminhamento.numero}: "
                    f"{decision_definition['label']}. {orientacoes}"
                ),
                usuario=request.user,
            )

    quantidade = len(requisicoes)
    label = "requisição" if quantidade == 1 else "requisições"
    messages.success(
        request,
        f"Encaminhamento #{encaminhamento.numero} registrado para {quantidade} {label}.",
    )

    if request.headers.get("HX-Request") == "true":
        response = HttpResponse(status=204)
        response["HX-Refresh"] = "true"
        return response
    return redirect("internal-encaminhamentos")


class InternalPriorizacaoView(OperatorRequiredMixin, TemplateView):
    template_name = "tracker/internal_priorizacao.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_internal_priorizacao_context(self.request))
        return context


class InternalVisitasView(OperatorRequiredMixin, TemplateView):
    template_name = "tracker/internal_visitas.html"


@login_required
@require_http_methods(["GET"])
def internal_priorizacao_table(request: HttpRequest) -> HttpResponse:
    if not user_is_operator(request):
        raise Http404
    return render(request, "tracker/_priorizacao_table.html", _internal_priorizacao_context(request))


@login_required
@require_http_methods(["GET"])
def internal_priorizacao_panel(request: HttpRequest) -> HttpResponse:
    if not user_is_operator(request):
        raise Http404
    return render(request, "tracker/_internal_priorizacao_panel.html", _internal_priorizacao_context(request))


@login_required
@require_http_methods(["POST"])
def priorizacao_bulk_assign_empresa(request):
    if not user_is_operator(request):
        raise Http404
        
    ids = request.POST.getlist("requisicao_ids")
    empresa_nome = request.POST.get("empresa_nome", "").strip()
    
    if ids and empresa_nome:
        if empresa_nome == "none":
            empresa_nome = ""
        Requisicao.objects.filter(id__in=ids).update(empresa=empresa_nome)
        
    response = HttpResponse()
    response["HX-Trigger"] = "refreshTable"
    return response


@login_required
@require_http_methods(["POST"])
def update_requisicao_gut(request, pk):
    if not user_is_operator(request):
        raise Http404
        
    requisicao = get_object_or_404(Requisicao, pk=pk)
    field = request.POST.get("field")
    value = request.POST.get("value")
    
    if field in ["gravidade", "urgencia", "tendencia", "empresa"]:
        setattr(requisicao, field, value)
        
        if field in ["gravidade", "urgencia", "tendencia"]:
            # Calculate new GUT score
            try:
                g_obj = GUTParametro.objects.filter(tipo=GUTParametro.Tipo.GRAVIDADE, descricao=requisicao.gravidade).first()
                u_obj = GUTParametro.objects.filter(tipo=GUTParametro.Tipo.URGENCIA, descricao=requisicao.urgencia).first()
                t_obj = GUTParametro.objects.filter(tipo=GUTParametro.Tipo.TENDENCIA, descricao=requisicao.tendencia).first()
                
                g_val = g_obj.valor if g_obj else 0
                u_val = u_obj.valor if u_obj else 0
                t_val = t_obj.valor if t_obj else 0
                
                requisicao.gut_score = g_val * u_val * t_val
            except Exception:
                pass
            
        requisicao.save()
        
    gut_options = {
        "gravidade": GUTParametro.objects.filter(tipo=GUTParametro.Tipo.GRAVIDADE),
        "urgencia": GUTParametro.objects.filter(tipo=GUTParametro.Tipo.URGENCIA),
        "tendencia": GUTParametro.objects.filter(tipo=GUTParametro.Tipo.TENDENCIA),
    }
    
    return render(request, "tracker/_priorizacao_row.html", {
        "item": requisicao,
        "gut_options": gut_options,
        "empresas_list": Empresa.objects.filter(ativa=True)
    })


class RequisicaoCreateView(OperatorRequiredMixin, CreateView):
    model = Requisicao
    form_class = RequisicaoForm
    template_name = "tracker/requisicao_form.html"
    success_url = reverse_lazy("internal-lista")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def acompanhamento_queryset(self):
        if not getattr(self, "object", None):
            return AcompanhamentoRequisicao.objects.none()
        return AcompanhamentoRequisicao.objects.filter(requisicao=self.object).select_related("usuario")

    def get_acompanhamento_formset(self):
        if self.request.method in {"POST", "PUT"}:
            return AcompanhamentoRequisicaoFormSet(
                self.request.POST,
                instance=self.object,
                queryset=self.acompanhamento_queryset(),
            )
        return AcompanhamentoRequisicaoFormSet(instance=self.object, queryset=self.acompanhamento_queryset())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("acompanhamento_formset", self.get_acompanhamento_formset())
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        acompanhamento_formset = self.get_acompanhamento_formset()
        if form.is_valid() and acompanhamento_formset.is_valid():
            return self.forms_valid(form, acompanhamento_formset)
        return self.forms_invalid(form, acompanhamento_formset)

    def forms_valid(self, form, acompanhamento_formset):
        with transaction.atomic():
            self.object = form.save()
            acompanhamento_formset.instance = self.object
            created_acompanhamentos = save_acompanhamento_formset(
                acompanhamento_formset,
                requisicao=self.object,
                user=self.request.user,
            )
        success_message = "Requisi\u00e7\u00e3o atualizada com sucesso."
        if created_acompanhamentos:
            autor_nome = created_acompanhamentos[-1].usuario_nome or self.request.user.username
            quantidade = len(created_acompanhamentos)
            if quantidade == 1:
                success_message += f" Situa\u00e7\u00e3o cadastrada por {autor_nome}."
            else:
                success_message += f" {quantidade} situa\u00e7\u00f5es cadastradas por {autor_nome}."
        messages.success(self.request, success_message)
        return redirect(self.get_success_url())

    def forms_invalid(self, form, acompanhamento_formset):
        return self.render_to_response(self.get_context_data(form=form, acompanhamento_formset=acompanhamento_formset))

    def form_valid(self, form):
        messages.success(self.request, "Requisi\u00e7\u00e3o criada com sucesso.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs)

    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class RequisicaoUpdateView(OperatorRequiredMixin, UpdateView):
    model = Requisicao
    form_class = RequisicaoForm
    template_name = "tracker/requisicao_form.html"
    success_url = reverse_lazy("internal-lista")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def acompanhamento_queryset(self):
        return AcompanhamentoRequisicao.objects.filter(requisicao=self.object).select_related("usuario")

    def get_acompanhamento_formset(self):
        if self.request.method in {"POST", "PUT"}:
            return AcompanhamentoRequisicaoFormSet(
                self.request.POST,
                instance=self.object,
                queryset=self.acompanhamento_queryset(),
            )
        return AcompanhamentoRequisicaoFormSet(instance=self.object, queryset=self.acompanhamento_queryset())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("acompanhamento_formset", self.get_acompanhamento_formset())
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        acompanhamento_formset = self.get_acompanhamento_formset()
        if form.is_valid() and acompanhamento_formset.is_valid():
            return self.forms_valid(form, acompanhamento_formset)
        return self.forms_invalid(form, acompanhamento_formset)

    def forms_valid(self, form, acompanhamento_formset):
        saving_comment = "save_acompanhamento" in self.request.POST
        with transaction.atomic():
            self.object = form.save()
            acompanhamento_formset.instance = self.object
            created_acompanhamentos = save_acompanhamento_formset(
                acompanhamento_formset,
                requisicao=self.object,
                user=self.request.user,
            )

        if saving_comment:
            if created_acompanhamentos:
                autor_nome = created_acompanhamentos[-1].usuario_nome or self.request.user.username
                success_message = f"Comentário salvo por {autor_nome}."
            else:
                success_message = "Comentário atualizado com sucesso."
            messages.success(self.request, success_message)
            return redirect(f"{reverse('requisicao-update', args=[self.object.pk])}#acompanhamento-section")

        success_message = "Requisição atualizada com sucesso."
        messages.success(self.request, success_message)
        return redirect(self.get_success_url())

    def forms_invalid(self, form, acompanhamento_formset):
        return self.render_to_response(self.get_context_data(form=form, acompanhamento_formset=acompanhamento_formset))

    def form_valid(self, form):
        messages.success(self.request, "Requisição atualizada com sucesso.")
        return super().form_valid(form)


@require_http_methods(["GET"])
def public_requisicoes_table(request: HttpRequest) -> HttpResponse:
    return render(request, "tracker/_requisicoes_table.html", table_context(request, public=True))


@require_http_methods(["GET"])
def public_dashboard_panel(request: HttpRequest) -> HttpResponse:
    return render(request, "tracker/_public_dashboard_panel.html", _public_dashboard_context(request))


@require_http_methods(["GET"])
def home_consulta_req(request: HttpRequest) -> HttpResponse:
    return render(request, "tracker/_public_home_consulta_req.html", _public_dashboard_context(request))


@login_required
@require_http_methods(["GET"])
def internal_requisicoes_table(request: HttpRequest) -> HttpResponse:
    if not user_is_operator(request):
        raise Http404
    return render(request, "tracker/_requisicoes_table.html", table_context(request, public=False))


@login_required
@require_http_methods(["GET"])
def internal_requisicoes_panel(request: HttpRequest) -> HttpResponse:
    if not user_is_operator(request):
        raise Http404
    return render(request, "tracker/_internal_lista_panel.html", _internal_lista_context(request))


@login_required
@require_http_methods(["POST"])
def importacao_upload(request: HttpRequest) -> HttpResponse:
    if not user_is_admin(request):
        raise Http404
    form = ImportacaoForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Envie um arquivo válido para importação.")
        return redirect("internal-cadastro")
    importer = WorkbookImporter(user=request.user)
    importacao = importer.import_file(form.cleaned_data["arquivo"])
    messages.success(
        request,
        f"Importação concluída: {importacao.resumo_json.get('total_processado', 0)} registros processados.",
    )
    return redirect("internal-cadastro")


@login_required
@require_http_methods(["POST"])
def indicar_processo(request: HttpRequest, pk: int) -> HttpResponse:
    if not user_is_operator(request):
        raise Http404
    requisicao = get_object_or_404(Requisicao, pk=pk)
    requisicao.status_processo_diretor = Requisicao.StatusProcessoDiretor.AGUARDANDO_DECISAO
    requisicao.save()
    messages.success(request, "Indicação de abertura de processo enviada ao Diretor de Centro com sucesso.")
    
    response = HttpResponse()
    response["HX-Trigger"] = "refreshTable"
    return response


def _prepare_bulk_decision_requisicoes(
    requisicoes: list[Requisicao],
    *,
    acompanhamento_values: dict[int, str] | None = None,
    missing_ids: set[int] | None = None,
) -> list[Requisicao]:
    acompanhamento_values = acompanhamento_values or {}
    missing_ids = missing_ids or set()

    for requisicao in requisicoes:
        acompanhamentos = list(requisicao.acompanhamentos.all())
        requisicao.bulk_acompanhamento_value = acompanhamento_values.get(requisicao.pk, "")
        requisicao.bulk_missing = requisicao.pk in missing_ids
        requisicao.ultimo_acompanhamento = acompanhamentos[-1] if acompanhamentos else None

    return requisicoes


@login_required
@require_http_methods(["POST"])
def internal_bulk_decisions_preview(request: HttpRequest) -> HttpResponse:
    if not user_is_operator(request):
        raise Http404

    ids = request.POST.getlist("requisicao_ids")
    requisicoes = _prepare_bulk_decision_requisicoes(
        list(
            Requisicao.objects.filter(id__in=ids)
            .select_related("predio", "requisitante")
            .prefetch_related("acompanhamentos")
            .order_by("-ano", "-numero")
        )
    )

    if not requisicoes:
        return HttpResponse("Selecione ao menos uma requisição para encaminhar.", status=400)

    return render(
        request,
        "tracker/_bulk_decisions_preview.html",
        {
            "selected_requisicoes": requisicoes,
            "today": date.today(),
        },
    )


@login_required
@require_http_methods(["POST"])
def internal_bulk_decisions(request: HttpRequest) -> HttpResponse:
    if not user_is_operator(request):
        raise Http404

    ids = request.POST.getlist("requisicao_ids")
    is_htmx_request = request.headers.get("HX-Request") == "true"
    requisicoes = list(
        Requisicao.objects.filter(id__in=ids)
        .select_related("predio", "requisitante")
        .prefetch_related("acompanhamentos")
        .order_by("-ano", "-numero")
    )
    if not requisicoes:
        messages.error(request, "Selecione ao menos uma requisição.")
        return redirect("internal-lista")

    justificativas: dict[int, str] = {}
    faltantes: list[Requisicao] = []
    for requisicao in requisicoes:
        texto = request.POST.get(f"acompanhamento_{requisicao.pk}", "").strip()
        justificativas[requisicao.pk] = texto
        if not texto:
            faltantes.append(requisicao)

    if faltantes:
        requisicoes = _prepare_bulk_decision_requisicoes(
            requisicoes,
            acompanhamento_values=justificativas,
            missing_ids={item.pk for item in faltantes},
        )
        return render(
            request,
            "tracker/_bulk_decisions_preview.html",
            {
                "selected_requisicoes": requisicoes,
                "today": date.today(),
                "form_error": "Explique o motivo do encaminhamento para todas as requisições selecionadas.",
            },
            status=200 if is_htmx_request else 400,
        )

    for requisicao in requisicoes:
        requisicao.status_processo_diretor = Requisicao.StatusProcessoDiretor.AGUARDANDO_DECISAO
        requisicao.save()
        AcompanhamentoRequisicao.objects.create(
            requisicao=requisicao,
            data=date.today(),
            atualizacao_situacao=f"Encaminhada para Direção: {justificativas[requisicao.pk]}",
            usuario=request.user,
        )

    messages.success(request, f"{len(requisicoes)} requisições encaminhadas para análise do diretor.")
    if is_htmx_request:
        response = HttpResponse(status=204)
        response["HX-Refresh"] = "true"
        return response
    return redirect("internal-lista")


def parse_payload(request: HttpRequest) -> dict[str, Any]:
    if request.content_type and "application/json" in request.content_type:
        return json.loads(request.body.decode("utf-8") or "{}")
    return request.POST.dict()


def json_error(message: str, *, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def requisicao_to_form_data(instance: Requisicao) -> dict[str, Any]:
    return model_to_dict(instance, fields=RequisicaoForm.Meta.fields)


@require_http_methods(["GET"])
def api_public_indicadores(request: HttpRequest) -> JsonResponse:
    queryset = filtered_queryset(request, public=True)
    return JsonResponse(metrics_for_queryset(queryset))


@require_http_methods(["GET"])
def api_public_requisicoes(request: HttpRequest) -> JsonResponse:
    context = table_context(request, public=True)
    lookup = status_sipac_lookup([item.status_sipac for item in context["page_obj"].object_list])
    return JsonResponse(
        {
            "count": context["page_obj"].paginator.count,
            "num_pages": context["page_obj"].paginator.num_pages,
            "page": context["page_obj"].number,
            "results": [serialize_requisicao(item, public=True, status_lookup_map=lookup) for item in context["page_obj"].object_list],
        }
    )


@require_http_methods(["GET"])
def api_public_requisicao_detail(request: HttpRequest, pk: int) -> JsonResponse:
    requisicao = get_object_or_404(Requisicao.objects.select_related("predio", "requisitante"), pk=pk, visivel_publicamente=True)
    lookup = status_sipac_lookup([requisicao.status_sipac])
    return JsonResponse(serialize_requisicao(requisicao, public=True, status_lookup_map=lookup))


@login_required
@require_http_methods(["GET", "POST"])
def api_internal_requisicoes(request: HttpRequest) -> JsonResponse | HttpResponse:
    if not user_is_operator(request):
        return json_error("Acesso negado.", status=403)

    if request.method == "GET":
        queryset = filtered_queryset(request, public=False)
        if request.GET.get("format") == "csv":
            return export_internal_csv(queryset)
        context = table_context(request, public=False)
        lookup = status_sipac_lookup([item.status_sipac for item in context["page_obj"].object_list])
        return JsonResponse(
            {
                "count": context["page_obj"].paginator.count,
                "num_pages": context["page_obj"].paginator.num_pages,
                "page": context["page_obj"].number,
                "results": [serialize_requisicao(item, public=False, status_lookup_map=lookup) for item in context["page_obj"].object_list],
            }
        )

    payload = parse_payload(request)
    form = RequisicaoForm(payload, user=request.user)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    requisicao = form.save()
    lookup = status_sipac_lookup([requisicao.status_sipac])
    return JsonResponse(serialize_requisicao(requisicao, public=False, status_lookup_map=lookup), status=201)


@login_required
@require_http_methods(["GET", "PATCH", "PUT"])
def api_internal_requisicao_detail(request: HttpRequest, pk: int) -> JsonResponse:
    if not user_is_operator(request):
        return json_error("Acesso negado.", status=403)

    requisicao = get_object_or_404(Requisicao.objects.select_related("predio", "requisitante"), pk=pk)
    if request.method == "GET":
        lookup = status_sipac_lookup([requisicao.status_sipac])
        payload = serialize_requisicao(requisicao, public=False, status_lookup_map=lookup)
        payload["historico"] = [
            {
                "status_sipac": item.status_sipac,
                "situacao_requisicao": item.situacao_requisicao,
                "observacao": item.observacao,
                "origem": item.origem,
                "criado_em": item.criado_em.isoformat(),
            }
            for item in requisicao.historicos.all()[:20]
        ]
        return JsonResponse(payload)

    payload = requisicao_to_form_data(requisicao)
    payload.update(parse_payload(request))
    form = RequisicaoForm(payload, instance=requisicao, user=request.user)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    requisicao = form.save()
    lookup = status_sipac_lookup([requisicao.status_sipac])
    return JsonResponse(serialize_requisicao(requisicao, public=False, status_lookup_map=lookup))


@login_required
@require_http_methods(["GET", "POST"])
def api_internal_importacoes(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        if not user_is_operator(request):
            return json_error("Acesso negado.", status=403)
        items = ImportacaoArquivo.objects.select_related("iniciado_por")[:20]
        return JsonResponse(
            {
                "results": [
                    {
                        "id": item.id,
                        "nome_arquivo": item.nome_arquivo,
                        "tipo_arquivo": item.tipo_arquivo,
                        "status": item.status,
                        "criado_em": item.criado_em.isoformat(),
                        "processado_em": item.processado_em.isoformat() if item.processado_em else None,
                        "resumo_json": item.resumo_json,
                    }
                    for item in items
                ]
            }
        )

    if not user_is_admin(request):
        return json_error("Apenas administradores podem importar arquivos.", status=403)

    form = ImportacaoForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    importacao = WorkbookImporter(user=request.user).import_file(form.cleaned_data["arquivo"])
    return JsonResponse({"id": importacao.id, "status": importacao.status, "resumo_json": importacao.resumo_json}, status=201)


@login_required
@require_http_methods(["GET"])
def api_internal_regras_prioridade(request: HttpRequest) -> JsonResponse:
    if not user_is_operator(request):
        return json_error("Acesso negado.", status=403)
    rules = RegraPrioridade.objects.filter(ativa=True)
    return JsonResponse(
        {"results": [{"id": rule.id, "chave_normalizada": rule.chave_normalizada, "prioridade": rule.prioridade} for rule in rules]}
    )


@login_required
@require_http_methods(["GET"])
def api_internal_cadastros(request: HttpRequest) -> JsonResponse:
    if not user_is_operator(request):
        return json_error("Acesso negado.", status=403)
    return JsonResponse(
        {
            "predios": [{"id": item.id, "nome": item.nome} for item in Predio.objects.all()[:500]],
            "requisitantes": [{"id": item.id, "nome": item.nome, "unidade_setor": item.unidade_setor} for item in Requisitante.objects.all()[:500]],
            "taxonomias": [
                {"id": item.id, "divisao": item.divisao, "tipo_servico": item.tipo_servico, "servico": item.servico}
                for item in TaxonomiaServico.objects.exclude(servico="")[:500]
            ],
        }
    )


def export_internal_csv(queryset: QuerySet[Requisicao]) -> HttpResponse:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "codigo",
            "assunto",
            "orcamento",
            "data_cadastro",
            "divisao",
            "tipo_servico",
            "servico",
            "predio",
            "local_servico",
            "status_sipac",
            "situacao_requisicao",
            "sinfra_responsavel",
            "prioridade_final",
            "requisitante",
            "contato_direto_url",
            "link_atendimento",
            "link_sipac",
        ]
    )
    for item in queryset:
        writer.writerow(
            [
                item.codigo,
                item.assunto,
                item.orcamento,
                item.data_cadastro.isoformat() if item.data_cadastro else "",
                item.divisao,
                item.tipo_servico,
                item.servico,
                item.predio.nome if item.predio else "",
                item.local_servico,
                item.status_sipac,
                item.situacao_requisicao,
                item.sinfra_responsavel,
                item.prioridade_final,
                item.nome_requisitante_publico,
                item.contato_direto_url,
                item.link_atendimento,
                item.link_sipac,
            ]
        )
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="requisicoes_ct_sinfra.csv"'
    return response


def _annotate_status_list(qs):
    result = []
    for item in qs:
        meta = resolve_status_sipac_metadata(item.descricao)
        item.rotulo_exibicao = meta["rotulo"] or item.descricao
        item.situacao_derivada = derive_situation(item.descricao)
        item.mapeado = bool(meta["numero"])
        result.append(item)
    return result


class InternalGestaoListasView(AdminRequiredMixin, TemplateView):
    template_name = "tracker/internal_gestao_listas.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_list"] = _annotate_status_list(StatusSipacOpcao.objects.all())
        context["taxonomia_list"] = TaxonomiaServico.objects.all()
        context["gut_params"] = GUTParametro.objects.all()
        context["empresas"] = Empresa.objects.all()
        return context


@login_required
def empresa_crud(request, pk=None):
    if not user_is_admin(request):
        raise Http404
    
    instance = get_object_or_404(Empresa, pk=pk) if pk else None
    
    if request.method == "POST":
        nome = request.POST.get("nome", "").strip()
        ativa = request.POST.get("ativa") == "on"
        
        if not nome:
            return HttpResponse("Nome da empresa é obrigatório", status=400)
            
        if instance:
            instance.nome = nome
            instance.ativa = ativa
            instance.save()
        else:
            Empresa.objects.create(nome=nome, ativa=ativa)
            
        return render(request, "tracker/_empresa_list_rows.html", {
            "empresas": Empresa.objects.all()
        })
        
    return render(request, "tracker/_empresa_form.html", {"instance": instance})


@login_required
@require_http_methods(["POST", "DELETE"])
def empresa_delete(request, pk):
    if not user_is_admin(request):
        raise Http404
    instance = get_object_or_404(Empresa, pk=pk)
    instance.delete()
    return render(request, "tracker/_empresa_list_rows.html", {
        "empresas": Empresa.objects.all()
    })



@login_required
def gut_parametro_crud(request, pk=None):
    if not user_is_admin(request):
        raise Http404
    
    instance = get_object_or_404(GUTParametro, pk=pk) if pk else None
    
    if request.method == "POST":
        tipo = request.POST.get("tipo")
        valor = request.POST.get("valor")
        descricao = request.POST.get("descricao", "").strip()
        
        if not tipo or not valor or not descricao:
            return HttpResponse("Todos os campos são obrigatórios", status=400)
            
        if instance:
            instance.tipo = tipo
            instance.valor = valor
            instance.descricao = descricao
            instance.save()
        else:
            GUTParametro.objects.create(tipo=tipo, valor=valor, descricao=descricao)
            
        return render(request, "tracker/_gut_list_rows.html", {
            "gut_params": GUTParametro.objects.all()
        })
        
    return render(request, "tracker/_gut_form.html", {"instance": instance})


@login_required
@require_http_methods(["POST", "DELETE"])
def gut_parametro_delete(request, pk):
    if not user_is_admin(request):
        raise Http404
    instance = get_object_or_404(GUTParametro, pk=pk)
    instance.delete()
    return render(request, "tracker/_gut_list_rows.html", {
        "gut_params": GUTParametro.objects.all()
    })



@login_required
def status_sipac_crud(request, pk=None):
    if not user_is_admin(request):
        raise Http404
    
    instance = get_object_or_404(StatusSipacOpcao, pk=pk) if pk else None
    
    if request.method == "POST":
        descricao = request.POST.get("descricao", "").strip()
        ativa = request.POST.get("ativa") == "on"
        
        if not descricao:
            return HttpResponse("Descrição obrigatória", status=400)
            
        if instance:
            instance.descricao = descricao
            instance.ativa = ativa
            instance.save()
        else:
            StatusSipacOpcao.objects.create(descricao=descricao, ativa=ativa)
            
        return render(request, "tracker/_status_list_rows.html", {
            "status_list": _annotate_status_list(StatusSipacOpcao.objects.all())
        })
        
    return render(request, "tracker/_status_form.html", {"instance": instance})


@login_required
@require_http_methods(["POST", "DELETE"])
def status_sipac_delete(request, pk):
    if not user_is_admin(request):
        raise Http404
    instance = get_object_or_404(StatusSipacOpcao, pk=pk)
    instance.delete()
    return render(request, "tracker/_status_list_rows.html", {
        "status_list": _annotate_status_list(StatusSipacOpcao.objects.all())
    })

@login_required
@require_http_methods(["POST"])
def status_sipac_bulk(request):
    if not user_is_admin(request):
        raise Http404
    
    status_ids = request.POST.getlist("status_ids")
    action = request.POST.get("action")
    
    if status_ids and action in ["ativar", "inativar"]:
        StatusSipacOpcao.objects.filter(pk__in=status_ids).update(
            ativa=(action == "ativar")
        )
        
    return render(request, "tracker/_status_list_rows.html", {
        "status_list": _annotate_status_list(StatusSipacOpcao.objects.all())
    })

@login_required
def taxonomia_crud(request, pk=None):
    if not user_is_admin(request):
        raise Http404
    
    instance = get_object_or_404(TaxonomiaServico, pk=pk) if pk else None
    
    if request.method == "POST":
        divisao = request.POST.get("divisao", "").strip()
        tipo_servico = request.POST.get("tipo_servico", "").strip()
        servico = request.POST.get("servico", "").strip()
        
        if not divisao or not tipo_servico:
            return HttpResponse("Divisão e Tipo de Serviço são obrigatórios", status=400)
            
        if instance:
            instance.divisao = divisao
            instance.tipo_servico = tipo_servico
            instance.servico = servico
            instance.save()
        else:
            TaxonomiaServico.objects.create(
                divisao=divisao,
                tipo_servico=tipo_servico,
                servico=servico
            )
            
        return render(request, "tracker/_taxonomia_list_rows.html", {
            "taxonomia_list": TaxonomiaServico.objects.all()
        })
        
    return render(request, "tracker/_taxonomia_form.html", {"instance": instance})


@login_required
@require_http_methods(["POST", "DELETE"])
def taxonomia_delete(request, pk):
    if not user_is_admin(request):
        raise Http404
    instance = get_object_or_404(TaxonomiaServico, pk=pk)
    instance.delete()
    return render(request, "tracker/_taxonomia_list_rows.html", {
        "taxonomia_list": TaxonomiaServico.objects.all()
    })


# ── ORÇAMENTO ─────────────────────────────────────────────────────────────────

def _requisicoes_finalizadas_orcamento_queryset() -> QuerySet[Requisicao]:
    return Requisicao.objects.filter(
        orcamento_valor__isnull=False,
        orcamento_valor__gt=0,
    ).filter(
        Q(situacao_requisicao__iexact="Inativa") | Q(status_sipac__icontains="FINALIZADA")
    )


def _orcamento_filtered_queryset(request: HttpRequest | None = None) -> QuerySet[Requisicao]:
    queryset = _requisicoes_finalizadas_orcamento_queryset()
    if request is None:
        return queryset

    return _apply_request_filters(queryset, request)


def _orcamento_filter_options(request: HttpRequest | None = None) -> dict[str, Any]:
    return filter_options(queryset=_requisicoes_finalizadas_orcamento_queryset(), request=request)


def _orcamento_redirect_url(return_query: str = "", anchor: str = "") -> str:
    redirect_url = reverse("internal-orcamento")
    if return_query:
        redirect_url = f"{redirect_url}?{return_query}"
    if anchor:
        redirect_url = f"{redirect_url}#{anchor}"
    return redirect_url


def _orcamento_context(request: HttpRequest | None = None):
    notas = list(NotaEmpenho.objects.prefetch_related("reforcos", "requisicoes_empenho").all())
    valor_total = sum(n.valor_total for n in notas)
    saldo_total = sum(n.saldo for n in notas)
    reqs_finalizadas = _orcamento_filtered_queryset(request).select_related("nota_empenho")
    total_reqs_pagas = _requisicoes_finalizadas_orcamento_queryset().count()
    return {
        "notas": notas,
        "empresas_list": Empresa.objects.filter(ativa=True),
        "valor_total": valor_total,
        "saldo_total": saldo_total,
        "reqs_finalizadas": reqs_finalizadas,
        "orcamento_filters": _orcamento_filter_options(request),
        "total_notas": len(notas),
        "total_reqs_pagas": total_reqs_pagas,
    }


def _orcamento_panel_context(request: HttpRequest) -> dict[str, Any]:
    context = _orcamento_context(request)
    context["reqs_finalizadas"] = context["reqs_finalizadas"].order_by(*orcamento_ordering_for_request(request))
    filtered_count = context["reqs_finalizadas"].count()
    total_count = context["total_reqs_pagas"]
    filters_active = has_active_filters(request)
    context.update(orcamento_sort_context(request))
    context.update(
        {
            "orcamento_filtered_count": filtered_count,
            "orcamento_total_count": total_count,
            "orcamento_has_active_filters": filters_active,
            "orcamento_count_label": format_table_count_label(filtered_count, total_count, filters_active),
        }
    )
    return context


class InternalOrcamentoView(OperatorRequiredMixin, TemplateView):
    template_name = "tracker/internal_orcamento.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_orcamento_panel_context(self.request))
        return context


@login_required
@require_http_methods(["GET"])
def internal_orcamento_panel(request: HttpRequest) -> HttpResponse:
    if not user_is_operator(request):
        raise Http404
    return render(request, "tracker/_internal_orcamento_panel.html", _orcamento_panel_context(request))


@login_required
@require_http_methods(["POST"])
def requisicao_orcamento_nota_update(request, pk):
    if not user_is_operator(request):
        raise Http404

    requisicao = get_object_or_404(_requisicoes_finalizadas_orcamento_queryset(), pk=pk)
    nota_id = request.POST.get("nota_empenho_id", "").strip()
    return_query = request.POST.get("return_query", "").strip()

    if nota_id:
        requisicao.nota_empenho = get_object_or_404(NotaEmpenho, pk=nota_id)
        requisicao.save()
        messages.success(
            request,
            f"Nota de empenho {requisicao.nota_empenho.nota_empenho} vinculada à requisição {requisicao.codigo}.",
        )
    else:
        requisicao.nota_empenho = None
        requisicao.save()
        messages.warning(
            request,
            f"A requisição {requisicao.codigo} ficou sem nota de empenho e saiu do cálculo do saldo total.",
        )

    return redirect(_orcamento_redirect_url(return_query))


@login_required
@require_http_methods(["POST"])
def requisicoes_orcamento_nota_bulk_update(request):
    if not user_is_operator(request):
        raise Http404

    requisicao_ids = request.POST.getlist("requisicao_ids")
    bulk_action = request.POST.get("bulk_action", "link").strip() or "link"
    nota_id = request.POST.get("nota_empenho_id", "").strip()
    return_query = request.POST.get("return_query", "").strip()

    if not requisicao_ids:
        messages.error(request, "Selecione ao menos uma requisição finalizada para aplicar a ação em lote.")
        return redirect(_orcamento_redirect_url(return_query))

    requisicoes = list(_requisicoes_finalizadas_orcamento_queryset().filter(pk__in=requisicao_ids).order_by("pk"))
    if not requisicoes:
        messages.error(request, "Nenhuma requisição finalizada válida foi encontrada para a ação em lote.")
        return redirect(_orcamento_redirect_url(return_query))

    quantidade = len(requisicoes)
    label = "requisição" if quantidade == 1 else "requisições"

    if bulk_action == "unlink":
        for requisicao in requisicoes:
            requisicao.nota_empenho = None
            requisicao.save()
        messages.warning(request, f"Nota de empenho desvinculada de {quantidade} {label}.")
        return redirect(_orcamento_redirect_url(return_query))

    if not nota_id:
        messages.error(request, "Selecione uma nota de empenho para vincular em lote.")
        return redirect(_orcamento_redirect_url(return_query))

    nota = get_object_or_404(NotaEmpenho, pk=nota_id)
    for requisicao in requisicoes:
        requisicao.nota_empenho = nota
        requisicao.save()

    messages.success(request, f"Nota de empenho {nota.nota_empenho} vinculada a {quantidade} {label}.")
    return redirect(_orcamento_redirect_url(return_query))


@login_required
def nota_empenho_crud(request, pk=None):
    if not user_is_operator(request):
        raise Http404

    instance = get_object_or_404(NotaEmpenho, pk=pk) if pk else None

    if request.method == "POST":
        from decimal import Decimal, InvalidOperation

        numero = request.POST.get("numero", "").strip()
        valor_str = request.POST.get("valor", "").strip()
        if "," in valor_str:
            valor_str = valor_str.replace(".", "").replace(",", ".")
        valor_str = valor_str.replace("R$", "").replace(" ", "")
        numero_processo = request.POST.get("numero_processo_sipac", "").strip()
        link_processo = request.POST.get("link_processo_sipac", "").strip()
        empresa = request.POST.get("empresa", "").strip()

        if not numero or not valor_str:
            return HttpResponse("Número e Valor são obrigatórios.", status=400)

        try:
            valor = Decimal(valor_str)
        except InvalidOperation:
            return HttpResponse("Valor inválido.", status=400)

        if instance:
            instance.nota_empenho = numero
            instance.valor = valor
            instance.numero_processo_sipac = numero_processo
            instance.link_processo_sipac = link_processo
            instance.empresa = empresa
            instance.save()
        else:
            NotaEmpenho.objects.create(
                nota_empenho=numero,
                valor=valor,
                numero_processo_sipac=numero_processo,
                link_processo_sipac=link_processo,
                empresa=empresa,
            )

        return render(request, "tracker/_nota_empenho_rows.html", _orcamento_context())

    return render(request, "tracker/_nota_empenho_form.html", {
        "instance": instance,
        "empresas_list": Empresa.objects.filter(ativa=True),
    })


@login_required
def nota_empenho_reforco(request, pk, reforco_pk=None):
    if not user_is_operator(request):
        raise Http404

    nota = get_object_or_404(NotaEmpenho, pk=pk)
    reforco = get_object_or_404(ReforcoEmpenho, pk=reforco_pk, empenho=nota) if reforco_pk else None

    if request.method == "GET":
        return render(
            request,
            "tracker/_nota_empenho_reforco_form.html",
            {
                "nota": nota,
                "reforco": reforco,
            },
        )

    from decimal import Decimal, InvalidOperation

    valor_str = request.POST.get("valor_reforco", "").strip()
    if "," in valor_str:
        valor_str = valor_str.replace(".", "").replace(",", ".")
    valor_str = valor_str.replace("R$", "").replace(" ", "")

    if not valor_str:
        return HttpResponse("Informe o valor do reforço.", status=400)

    try:
        adicional = Decimal(valor_str)
        if adicional <= 0:
            return HttpResponse("O valor deve ser positivo.", status=400)
    except InvalidOperation:
        return HttpResponse("Valor inválido.", status=400)

    numero_processo_sipac = request.POST.get("numero_processo_sipac", "").strip()
    descricao = request.POST.get("descricao_reforco", "").strip()
    if reforco:
        reforco.valor = adicional
        reforco.numero_processo_sipac = numero_processo_sipac
        reforco.descricao = descricao
        reforco.save()
    else:
        ReforcoEmpenho.objects.create(
            empenho=nota,
            valor=adicional,
            numero_processo_sipac=numero_processo_sipac,
            descricao=descricao,
        )

    return render(request, "tracker/_nota_empenho_rows.html", _orcamento_context())


@login_required
@require_http_methods(["POST", "DELETE"])
def nota_empenho_reforco_delete(request, pk, reforco_pk):
    if not user_is_operator(request):
        raise Http404

    nota = get_object_or_404(NotaEmpenho, pk=pk)
    reforco = get_object_or_404(ReforcoEmpenho, pk=reforco_pk, empenho=nota)
    reforco.delete()
    return render(request, "tracker/_nota_empenho_rows.html", _orcamento_context())


@login_required
@require_http_methods(["POST", "DELETE"])
def nota_empenho_delete(request, pk):
    if not user_is_operator(request):
        raise Http404

    nota = get_object_or_404(NotaEmpenho, pk=pk)
    nota.delete()
    return render(request, "tracker/_nota_empenho_rows.html", _orcamento_context())


@login_required
@require_http_methods(["POST"])
def requisicao_delete(request, pk):
    if not user_is_operator(request):
        raise Http404

    requisicao = get_object_or_404(Requisicao, pk=pk)
    codigo_confirmado = request.POST.get("codigo_confirmacao", "").strip()

    if codigo_confirmado != requisicao.codigo:
        messages.error(request, "Código de confirmação incorreto. A requisição não foi apagada.")
        return redirect("internal-lista")

    codigo = requisicao.codigo
    with transaction.atomic():
        requisicao.delete()

    messages.warning(request, f"Requisição {codigo} apagada com sucesso.")
    return redirect("internal-lista")
