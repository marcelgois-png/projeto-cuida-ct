from __future__ import annotations

from collections import OrderedDict, defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Count, Q, QuerySet, Sum

from .domain import clean_display_text, derive_situation, normalize_text, resolve_status_sipac_metadata
from .models import HistoricoStatus, RegraPrioridade, Requisicao, StatusRequisicao


def status_sipac_catalog(extra_values: list[str] | tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in StatusRequisicao.objects.filter(ativa=True).order_by("ordem", "numero", "codigo"):
        value = clean_display_text(item.codigo)
        if not value or value in seen:
            continue
        rows.append(
            {
                "value": value,
                "numero": clean_display_text(item.numero),
                "rotulo": clean_display_text(item.nome) or value,
                "descricao": value,
                "ordem": item.ordem,
                "label": item.exibicao,
            }
        )
        seen.add(value)

    for value in extra_values or ():
        cleaned = clean_display_text(value)
        if not cleaned or cleaned in seen:
            continue
        metadata = resolve_status_sipac_metadata(cleaned)
        rows.append(
            {
                "value": metadata["descricao"] or cleaned,
                "numero": metadata["numero"],
                "rotulo": metadata["rotulo"] or cleaned,
                "descricao": metadata["descricao"] or cleaned,
                "ordem": metadata["ordem"],
                "label": metadata["label"] or cleaned,
            }
        )
        seen.add(cleaned)

    rows.sort(key=lambda item: (item["ordem"] is None, item["ordem"] or 9999, item["descricao"]))
    return rows


def status_sipac_lookup(extra_values: list[str] | tuple[str, ...] | None = None) -> dict[str, dict[str, Any]]:
    return {item["value"]: item for item in status_sipac_catalog(extra_values)}


def status_sipac_display(value: str | None, lookup: dict[str, dict[str, Any]] | None = None) -> str:
    cleaned = clean_display_text(value)
    if not cleaned:
        return ""
    if lookup and cleaned in lookup:
        return lookup[cleaned]["label"]
    return resolve_status_sipac_metadata(cleaned)["label"] or cleaned


def calculate_execution_days(requisicao: Requisicao) -> int | None:
    if not requisicao.data_cadastro:
        return None

    status_codigo = requisicao.status_sipac.codigo if requisicao.status_sipac else ""
    situacao = clean_display_text(requisicao.situacao_requisicao) or derive_situation(status_codigo)

    if status_codigo == "06 FINALIZADA":
        if not requisicao.data_execucao:
            return None
        return max((requisicao.data_execucao - requisicao.data_cadastro).days, 0)

    if situacao == "Ativa":
        return max((date.today() - requisicao.data_cadastro).days, 0)

    return None


def resolve_priority_label(priority_key: str, fallback: str = "") -> str:
    if not priority_key:
        return fallback
    rule = RegraPrioridade.objects.filter(chave_normalizada=priority_key, ativa=True).first()
    if rule:
        return rule.prioridade
    return fallback


def register_status_history(
    requisicao: Requisicao,
    *,
    previous_status: str = "",
    previous_note: str = "",
    user=None,
    origin: str = HistoricoStatus.Origem.MANUAL,
    note: str = "",
) -> None:
    status_atual = requisicao.status_sipac.codigo if requisicao.status_sipac else ""
    status_changed = (previous_status or "") != status_atual
    note_changed = bool(note) and note != (previous_note or "")
    if not requisicao.pk or not (status_changed or note_changed):
        return
    HistoricoStatus.objects.create(
        requisicao=requisicao,
        status_sipac=status_atual,
        situacao_requisicao=requisicao.situacao_requisicao,
        observacao=note,
        origem=origin,
        usuario=user,
    )


def metrics_for_queryset(queryset: QuerySet[Requisicao]) -> dict[str, Any]:
    total = queryset.count()
    abertas = queryset.filter(situacao_requisicao="Ativa").count()
    inativas = queryset.filter(situacao_requisicao="Inativa").count()
    concluidas = queryset.filter(status_sipac__codigo="06 FINALIZADA").count()
    executadas = queryset.filter(Q(data_execucao__isnull=False) | Q(status_sipac__codigo="06 FINALIZADA")).count()
    publicas = queryset.filter(visivel_publicamente=True).count()
    por_divisao = list(
        queryset.values("divisao__nome")
        .annotate(total=Count("id"))
        .order_by("-total", "divisao__nome")[:8]
    )
    status_rows = list(
        queryset.filter(status_sipac__isnull=False)
        .values("status_sipac__codigo")
        .annotate(total=Count("id"))
    )
    lookup = status_sipac_lookup([row["status_sipac__codigo"] for row in status_rows])
    por_status = []
    for row in status_rows:
        raw_status = clean_display_text(row["status_sipac__codigo"])
        metadata = lookup.get(raw_status, {})
        por_status.append(
            {
                "status_sipac": raw_status,
                "numero": metadata.get("numero", ""),
                "status": metadata.get("rotulo", raw_status),
                "label": metadata.get("label", raw_status),
                "ordem": metadata.get("ordem"),
                "total": row["total"],
            }
        )
    por_status.sort(key=lambda item: (item["ordem"] is None, item["ordem"] or 9999, item["status_sipac"]))
    por_prioridade = list(
        queryset.values("prioridade_final")
        .annotate(total=Count("id"))
        .order_by("prioridade_final")
    )
    return {
        "total": total,
        "abertas": abertas,
        "inativas": inativas,
        "concluidas": concluidas,
        "executadas": executadas,
        "publicas": publicas,
        "por_divisao": por_divisao,
        "por_status": por_status,
        "por_prioridade": por_prioridade,
    }


def climatization_investment_for_queryset(queryset: QuerySet[Requisicao]) -> Decimal:
    total = queryset.filter(
        Q(status_sipac__codigo__icontains="FINALIZADA")
    ).filter(
        Q(tipo_servico__nome__icontains="Ar Condicionado")
        | Q(servico__nome__icontains="Ar Condicionado")
        | Q(servico__nome__icontains="ar-condicionado")
        | Q(tipo_servico__nome__icontains="Climatiza")
        | Q(servico__nome__icontains="Climatiza")
        | Q(assunto__icontains="ar condicionado")
        | Q(assunto__icontains="ar-condicionado")
        | Q(assunto__icontains="climatiza")
    ).aggregate(total=Sum("orcamento_valor"))["total"]
    return total or Decimal("0.00")


CONTROL_PANEL_MACROSTATUS = (
    {"key": "em_andamento", "label": "Em andamento", "color": "#cf5757"},
    {"key": "finalizada", "label": "Finalizada", "color": "#2f855a"},
    {"key": "nao_executada", "label": "N\u00e3o executada", "color": "#98a1ac"},
    {"key": "retornada_estornada", "label": "Retornada/estornada", "color": "#b7791f"},
    {"key": "outros", "label": "Outros", "color": "#64748b"},
)

CONTROL_PANEL_PRIORITY_ORDER = (
    "",
    "1 - Urgente",
    "2 - Alta",
    "3 - Media",
    "3 - M\u00e9dia",
    "4 - Baixa",
    "5 - Analisar",
    "6 - Inativa",
)


def control_panel_macrostatus_catalog() -> list[dict[str, str]]:
    return [dict(item) for item in CONTROL_PANEL_MACROSTATUS]


def resolve_control_panel_macrostatus(status_sipac: str | None, situacao_requisicao: str | None = "") -> str:
    normalized_status = normalize_text(status_sipac).upper()
    normalized_situation = normalize_text(situacao_requisicao).upper() or normalize_text(derive_situation(status_sipac)).upper()

    if not normalized_status:
        return "outros"
    if "NAO EXECUTADO" in normalized_status or "NEGADA" in normalized_status or "CANCELADA" in normalized_status:
        return "nao_executada"
    if "RETORNADA" in normalized_status or "ESTORNADA" in normalized_status:
        return "retornada_estornada"
    if normalized_status.startswith("06 FINALIZADA"):
        return "finalizada"
    if normalized_situation == "ATIVA":
        return "em_andamento"
    return "outros"


def _rounded_average(values: list[int]) -> int | None:
    if not values:
        return None
    return round(sum(values) / len(values))


def _priority_order_key(value: str) -> tuple[int, str]:
    if value in CONTROL_PANEL_PRIORITY_ORDER:
        return (CONTROL_PANEL_PRIORITY_ORDER.index(value), value)
    return (len(CONTROL_PANEL_PRIORITY_ORDER), value)


def control_panel_analytics(
    queryset: QuerySet[Requisicao],
    *,
    macrostatus_filter: str = "",
    include_internal: bool = False,
    years: list[int] | None = None,
) -> dict[str, Any]:
    macro_lookup = {item["key"]: item for item in CONTROL_PANEL_MACROSTATUS}
    items = list(queryset.order_by("ano", "numero", "codigo"))
    status_lookup = status_sipac_lookup([item.status_sipac.codigo if item.status_sipac else "" for item in items])

    if years is None:
        years = sorted(
            {
                item.ano or (item.data_cadastro.year if item.data_cadastro else None)
                for item in items
                if item.ano or item.data_cadastro
            }
        )
        years = [year for year in years if year is not None]

    filtered_items: list[Requisicao] = []
    for item in items:
        item._status_codigo = item.status_sipac.codigo if item.status_sipac else ""
        item.status_sipac_exibicao = status_sipac_display(item._status_codigo, status_lookup)
        item.control_macrostatus_key = resolve_control_panel_macrostatus(item._status_codigo, item.situacao_requisicao)
        item.control_macrostatus_label = macro_lookup[item.control_macrostatus_key]["label"]
        item.control_days = calculate_execution_days(item)
        item.control_year = item.ano or (item.data_cadastro.year if item.data_cadastro else None)
        if macrostatus_filter and item.control_macrostatus_key != macrostatus_filter:
            continue
        filtered_items.append(item)

    macro_rows: dict[str, dict[str, Any]] = {
        item["key"]: {"key": item["key"], "label": item["label"], "color": item["color"], "total": 0, "days": []}
        for item in CONTROL_PANEL_MACROSTATUS
    }
    raw_status_rows: dict[str, dict[str, Any]] = {}
    division_rows: dict[str, dict[str, Any]] = {}
    building_rows: dict[str, dict[str, Any]] = {}
    annual_rows = {
        year: {"ano": year, "quantidade": 0, "orcamento_total": Decimal("0.00"), "dias": []}
        for year in years
    }
    quantity_matrix: dict[str, dict[int, int]] = defaultdict(lambda: {year: 0 for year in years})
    wait_matrix: dict[str, dict[int, list[int]]] = defaultdict(lambda: {year: [] for year in years})
    service_groups: OrderedDict[str, dict[str, Any]] = OrderedDict()

    total_finalizado_orcamento = Decimal("0.00")
    finalized_days: list[int] = []
    oldest_active: list[Requisicao] = []
    active_wait_buckets = [
        {"label": "0\u201330", "min": 0, "max": 30, "count": 0},
        {"label": "31\u201360", "min": 31, "max": 60, "count": 0},
        {"label": "61\u201390", "min": 61, "max": 90, "count": 0},
        {"label": "91\u2013180", "min": 91, "max": 180, "count": 0},
        {"label": "181+", "min": 181, "max": None, "count": 0},
    ]
    active_priority_counts: dict[str, int] = defaultdict(int)
    active_without_priority = 0
    finalized_without_budget = 0
    without_sinfra = 0

    for item in filtered_items:
        macro_entry = macro_rows[item.control_macrostatus_key]
        macro_entry["total"] += 1
        if item.control_days is not None:
            macro_entry["days"].append(item.control_days)

        raw_status = clean_display_text(item._status_codigo) or "(Em branco)"
        status_entry = raw_status_rows.setdefault(
            raw_status,
            {
                "status_sipac": raw_status,
                "label": item.status_sipac_exibicao or raw_status,
                "macrostatus": item.control_macrostatus_label,
                "ordem": resolve_status_sipac_metadata(raw_status).get("ordem"),
                "total": 0,
            },
        )
        status_entry["total"] += 1

        division = clean_display_text(item.divisao.nome if item.divisao else "") or "(Em branco)"
        division_entry = division_rows.setdefault(division, {"divisao": division, "ativas": 0, "inativas": 0, "total": 0})
        division_entry["total"] += 1
        if item.situacao_requisicao == "Ativa":
            division_entry["ativas"] += 1
        else:
            division_entry["inativas"] += 1

        building = clean_display_text(item.predio.nome if item.predio else "") or "(Em branco)"
        building_entry = building_rows.setdefault(building, {"predio": building, "ativas": 0, "inativas": 0, "total": 0})
        building_entry["total"] += 1
        if item.situacao_requisicao == "Ativa":
            building_entry["ativas"] += 1
        else:
            building_entry["inativas"] += 1

        tipo_servico = clean_display_text(item.tipo_servico.nome if item.tipo_servico else "") or "(Em branco)"
        servico = clean_display_text(item.servico.nome if item.servico else "") or "(Em branco)"
        service_group = service_groups.setdefault(
            tipo_servico,
            {
                "tipo_servico": tipo_servico,
                "quantidade": 0,
                "ativas": 0,
                "inativas": 0,
                "dias_execucao_items": [],
                "servicos": OrderedDict(),
            },
        )
        service_group["quantidade"] += 1
        if item.situacao_requisicao == "Ativa":
            service_group["ativas"] += 1
        else:
            service_group["inativas"] += 1
        if item.control_days is not None:
            service_group["dias_execucao_items"].append(item.control_days)
        service_entry = service_group["servicos"].setdefault(
            servico,
            {"servico": servico, "quantidade": 0, "ativas": 0, "inativas": 0, "dias_execucao_items": []},
        )
        service_entry["quantidade"] += 1
        if item.situacao_requisicao == "Ativa":
            service_entry["ativas"] += 1
        else:
            service_entry["inativas"] += 1
        if item.control_days is not None:
            service_entry["dias_execucao_items"].append(item.control_days)

        if item.control_macrostatus_key == "finalizada":
            if item.control_days is not None:
                finalized_days.append(item.control_days)
            if item.orcamento_valor is not None:
                total_finalizado_orcamento += item.orcamento_valor
            else:
                finalized_without_budget += 1
            if item.control_year in annual_rows:
                annual_rows[item.control_year]["quantidade"] += 1
                if item.orcamento_valor is not None:
                    annual_rows[item.control_year]["orcamento_total"] += item.orcamento_valor
                if item.control_days is not None:
                    annual_rows[item.control_year]["dias"].append(item.control_days)
                qty_div = clean_display_text(item.divisao.nome if item.divisao else "") or "(Em branco)"
                quantity_matrix[qty_div][item.control_year] += 1
                if item.control_days is not None:
                    wait_matrix[qty_div][item.control_year].append(item.control_days)

        if item.situacao_requisicao == "Ativa":
            oldest_active.append(item)
            if not clean_display_text(item.sinfra_responsavel):
                without_sinfra += 1
            priority_key = clean_display_text(item.prioridade_final)
            if not priority_key:
                active_without_priority += 1
                priority_key = "(Sem prioridade)"
            active_priority_counts[priority_key] += 1
            if item.control_days is not None:
                for bucket in active_wait_buckets:
                    max_value = bucket["max"]
                    if item.control_days >= bucket["min"] and (max_value is None or item.control_days <= max_value):
                        bucket["count"] += 1
                        break

    macrostatus_breakdown = []
    for item in CONTROL_PANEL_MACROSTATUS:
        row = macro_rows[item["key"]]
        macrostatus_breakdown.append(
            {
                "key": row["key"],
                "label": row["label"],
                "color": row["color"],
                "total": row["total"],
                "dias_execucao": _rounded_average(row["days"]),
            }
        )

    raw_status_breakdown = sorted(
        raw_status_rows.values(),
        key=lambda entry: (entry["ordem"] is None, entry["ordem"] or 9999, -entry["total"], entry["label"]),
    )
    division_status = sorted(division_rows.values(), key=lambda entry: (-entry["total"], entry["divisao"]))
    building_breakdown = sorted(building_rows.values(), key=lambda entry: (-entry["total"], entry["predio"]))[:10]

    normalized_service_groups = []
    for group in service_groups.values():
        services = []
        for entry in group["servicos"].values():
            services.append(
                {
                    "servico": entry["servico"],
                    "ativas": entry["ativas"],
                    "inativas": entry["inativas"],
                    "quantidade": entry["quantidade"],
                    "dias_execucao": _rounded_average(entry["dias_execucao_items"]),
                }
            )
        services.sort(key=lambda entry: (-entry["quantidade"], entry["servico"]))
        normalized_service_groups.append(
            {
                "tipo_servico": group["tipo_servico"],
                "ativas": group["ativas"],
                "inativas": group["inativas"],
                "quantidade": group["quantidade"],
                "dias_execucao": _rounded_average(group["dias_execucao_items"]),
                "total_servicos": len(services),
                "servicos": services,
            }
        )
    normalized_service_groups.sort(key=lambda entry: (-entry["quantidade"], entry["tipo_servico"]))

    annual_summary = []
    annual_quantity_total = 0
    annual_budget_total = Decimal("0.00")
    annual_days_total: list[int] = []
    for year in years:
        row = annual_rows.get(year, {"ano": year, "quantidade": 0, "orcamento_total": Decimal("0.00"), "dias": []})
        annual_summary.append(
            {
                "ano": year,
                "quantidade": row["quantidade"],
                "orcamento_total": row["orcamento_total"],
                "dias_execucao": _rounded_average(row["dias"]),
            }
        )
        annual_quantity_total += row["quantidade"]
        annual_budget_total += row["orcamento_total"]
        annual_days_total.extend(row["dias"])

    quantity_rows = []
    wait_rows = []
    all_divisions = sorted(set(quantity_matrix.keys()) | set(wait_matrix.keys()))
    quantity_totals_by_year = {year: 0 for year in years}
    wait_totals_by_year: dict[int, list[int]] = {year: [] for year in years}

    for division in all_divisions:
        qty_years = quantity_matrix[division]
        wait_years = wait_matrix[division]
        row_total = sum(qty_years.values())
        quantity_rows.append({"divisao": division, "years": qty_years, "total": row_total})
        wait_row_years = {year: _rounded_average(wait_years[year]) for year in years}
        wait_rows.append({"divisao": division, "years": wait_row_years})
        for year in years:
            quantity_totals_by_year[year] += qty_years[year]
            wait_totals_by_year[year].extend(wait_years[year])

    quantity_rows.sort(key=lambda row: (-row["total"], row["divisao"]))
    wait_rows.sort(key=lambda row: row["divisao"])
    quantity_total_row = {
        "divisao": "Total CT",
        "years": quantity_totals_by_year,
        "total": sum(quantity_totals_by_year.values()),
    }
    wait_total_row = {
        "divisao": "M\u00e9dia CT",
        "years": {year: _rounded_average(wait_totals_by_year[year]) for year in years},
    }

    oldest_active.sort(
        key=lambda item: (item.control_days is None, -(item.control_days or 0), item.codigo),
    )
    oldest_active = oldest_active[:8]

    priority_rows = []
    for key, total in active_priority_counts.items():
        priority_rows.append({"label": key, "total": total})
    priority_rows.sort(key=lambda row: _priority_order_key(row["label"]))

    summary_cards = [
        {"label": "Total de requisi\u00e7\u00f5es", "value": len(filtered_items), "format": "int", "tone": "metric-primary"},
        {
            "label": "Requisi\u00e7\u00f5es ativas",
            "value": sum(1 for item in filtered_items if item.situacao_requisicao == "Ativa"),
            "format": "int",
            "tone": "metric-active",
        },
        {
            "label": "Requisi\u00e7\u00f5es finalizadas",
            "value": sum(1 for item in filtered_items if item.control_macrostatus_key == "finalizada"),
            "format": "int",
            "tone": "metric-executed",
        },
        {
            "label": "Requisi\u00e7\u00f5es n\u00e3o executadas",
            "value": sum(1 for item in filtered_items if item.control_macrostatus_key == "nao_executada"),
            "format": "int",
            "tone": "metric-inactive",
        },
        {
            "label": "Tempo m\u00e9dio at\u00e9 execu\u00e7\u00e3o",
            "value": _rounded_average(finalized_days),
            "format": "days",
            "tone": "metric-secondary",
        },
        {
            "label": "Or\u00e7amento finalizado",
            "value": total_finalizado_orcamento,
            "format": "currency",
            "tone": "metric-info",
        },
    ]

    chart_data = {
        "division_status": {
            "labels": [row["divisao"] for row in division_status],
            "ativas": [row["ativas"] for row in division_status],
            "inativas": [row["inativas"] for row in division_status],
        },
        "macrostatus": {
            "labels": [row["label"] for row in macrostatus_breakdown],
            "totals": [row["total"] for row in macrostatus_breakdown],
            "colors": [row["color"] for row in macrostatus_breakdown],
        },
        "macrostatus_wait": {
            "labels": [row["label"] for row in macrostatus_breakdown if row["dias_execucao"] is not None],
            "values": [row["dias_execucao"] for row in macrostatus_breakdown if row["dias_execucao"] is not None],
            "colors": [row["color"] for row in macrostatus_breakdown if row["dias_execucao"] is not None],
        },
        "building_breakdown": {
            "labels": [row["predio"] for row in building_breakdown],
            "ativas": [row["ativas"] for row in building_breakdown],
            "inativas": [row["inativas"] for row in building_breakdown],
        },
        "internal_wait_buckets": {
            "labels": [row["label"] for row in active_wait_buckets],
            "values": [row["count"] for row in active_wait_buckets],
        },
        "internal_priority_breakdown": {
            "labels": [row["label"] for row in priority_rows],
            "values": [row["total"] for row in priority_rows],
        },
    }

    context: dict[str, Any] = {
        "summary_cards": summary_cards,
        "macrostatus_breakdown": macrostatus_breakdown,
        "raw_status_breakdown": raw_status_breakdown,
        "division_status": division_status,
        "service_groups": normalized_service_groups,
        "building_breakdown": building_breakdown,
        "annual_summary": annual_summary,
        "annual_summary_total": {
            "quantidade": annual_quantity_total,
            "orcamento_total": annual_budget_total,
            "dias_execucao": _rounded_average(annual_days_total),
        },
        "division_year_quantity_matrix": {"years": years, "rows": quantity_rows, "total_row": quantity_total_row},
        "division_year_wait_matrix": {"years": years, "rows": wait_rows, "total_row": wait_total_row},
        "chart_data": chart_data,
        "filtered_total": len(filtered_items),
    }

    if include_internal:
        context["internal_triage"] = {
            "wait_buckets": active_wait_buckets,
            "priority_breakdown": priority_rows,
            "pending_operational": {
                "ativas_sem_prioridade": active_without_priority,
                "finalizadas_sem_orcamento": finalized_without_budget,
                "sem_responsavel_sinfra": without_sinfra,
            },
            "oldest_active": oldest_active,
        }

    return context


def service_panel_for_queryset(queryset: QuerySet[Requisicao], *, selected_divisao: str = "") -> dict[str, Any]:
    base_queryset = queryset
    if selected_divisao:
        queryset = queryset.filter(divisao__nome=selected_divisao)

    divisao_status = list(
        base_queryset.values("divisao__nome")
        .annotate(
            ativas=Count("id", filter=Q(situacao_requisicao="Ativa")),
            inativas=Count("id", filter=Q(situacao_requisicao="Inativa")),
            total=Count("id"),
        )
        .order_by("-total", "divisao__nome")[:10]
    )

    grouped_services: OrderedDict[str, dict[str, Any]] = OrderedDict()
    ordered_items = queryset.order_by("tipo_servico__nome", "servico__nome", "codigo")
    for item in ordered_items:
        tipo_servico = clean_display_text(item.tipo_servico.nome if item.tipo_servico else "") or "(Em branco)"
        servico = clean_display_text(item.servico.nome if item.servico else "") or "(Em branco)"
        dias_execucao = calculate_execution_days(item)

        group = grouped_services.setdefault(
            tipo_servico,
            {
                "tipo_servico": tipo_servico,
                "servicos": OrderedDict(),
                "dias_execucao_items": [],
                "quantidade": 0,
            },
        )
        group["quantidade"] += 1
        if dias_execucao is not None:
            group["dias_execucao_items"].append(dias_execucao)

        service_entry = group["servicos"].setdefault(
            servico,
            {
                "servico": servico,
                "dias_execucao_items": [],
                "quantidade": 0,
            },
        )
        service_entry["quantidade"] += 1
        if dias_execucao is not None:
            service_entry["dias_execucao_items"].append(dias_execucao)

    service_groups = []
    for group in grouped_services.values():
        services = []
        for service_entry in group["servicos"].values():
            items = service_entry["dias_execucao_items"]
            services.append(
                {
                    "servico": service_entry["servico"],
                    "dias_execucao": round(sum(items) / len(items)) if items else None,
                    "quantidade": service_entry["quantidade"],
                }
            )
        services.sort(key=lambda entry: (-entry["quantidade"], entry["servico"]))

        group_days = group["dias_execucao_items"]
        service_groups.append(
            {
                "tipo_servico": group["tipo_servico"],
                "dias_execucao": round(sum(group_days) / len(group_days)) if group_days else None,
                "quantidade": group["quantidade"],
                "total_servicos": len(services),
                "servicos": services,
            }
        )

    service_groups.sort(key=lambda entry: (-entry["quantidade"], entry["tipo_servico"]))

    normalized_divisoes = []
    for row in divisao_status:
        normalized_divisoes.append(
            {
                "divisao": row["divisao__nome"] or "(Em branco)",
                "ativas": row["ativas"],
                "inativas": row["inativas"],
                "total": row["total"],
            }
        )

    return {
        "selected_divisao": selected_divisao,
        "divisao_status": normalized_divisoes,
        "service_groups": service_groups,
    }


def serialize_requisicao(
    requisicao: Requisicao,
    *,
    public: bool = False,
    status_lookup_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    status_codigo = requisicao.status_sipac.codigo if requisicao.status_sipac else ""
    status_display = status_sipac_display(status_codigo, status_lookup_map)
    payload = OrderedDict(
        [
            ("id", requisicao.id),
            ("codigo", requisicao.codigo),
            ("numero", requisicao.numero),
            ("ano", requisicao.ano),
            ("assunto", requisicao.assunto),
            ("orcamento", requisicao.orcamento),
            ("data_cadastro", requisicao.data_cadastro.isoformat() if requisicao.data_cadastro else None),
            ("divisao", requisicao.divisao.nome if requisicao.divisao else ""),
            ("tipo_servico", requisicao.tipo_servico.nome if requisicao.tipo_servico else ""),
            ("servico", requisicao.servico.nome if requisicao.servico else ""),
            ("predio", requisicao.predio.nome if requisicao.predio else ""),
            ("local_servico", requisicao.local_servico),
            ("status_sipac", status_codigo),
            ("status_sipac_exibicao", status_display),
            ("situacao_requisicao", requisicao.situacao_requisicao),
            ("sinfra_responsavel", requisicao.sinfra_responsavel),
            ("prioridade_final", requisicao.prioridade_final),
            ("gut_score", requisicao.gut_score),
            ("gut_nivel", requisicao.gut_nivel),
            ("dias_desde_abertura", requisicao.dias_desde_abertura),
            ("dias_para_execucao", calculate_execution_days(requisicao)),
            ("data_execucao", requisicao.data_execucao.isoformat() if requisicao.data_execucao else None),
            ("requisitante", requisicao.nome_requisitante_publico),
            ("unidade_setor", requisicao.unidade_setor_snapshot),
            ("situacao_texto", requisicao.situacao_texto),
        ]
    )
    if not public:
        payload["contato_direto_url"] = requisicao.contato_direto_url
        payload["link_atendimento"] = requisicao.link_atendimento
        payload["link_sipac"] = requisicao.link_sipac
        payload["visivel_publicamente"] = requisicao.visivel_publicamente
    return payload
