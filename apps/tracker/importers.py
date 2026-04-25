from __future__ import annotations

import csv
import io
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from .domain import (
    clean_display_text,
    coerce_brazilian_phone,
    coerce_coordinate,
    coerce_date,
    coerce_int,
    extract_request_parts,
    normalize_key,
    normalize_text,
    resolve_status_sipac_metadata,
)
from .models import (
    HistoricoStatus,
    ImportacaoArquivo,
    Predio,
    RegraPrioridade,
    Requisicao,
    Requisitante,
    StatusSipacOpcao,
    TaxonomiaServico,
)
from .services import register_status_history, resolve_priority_label


class ImportErrorPlanilha(Exception):
    pass


class WorkbookImporter:
    def __init__(self, user=None):
        self.user = user

    def import_file(self, uploaded_file) -> ImportacaoArquivo:
        suffix = Path(uploaded_file.name).suffix.lower()
        if suffix not in {".xlsm", ".xlsx", ".csv"}:
            raise ImportErrorPlanilha("Formato inválido. Envie um arquivo XLSM, XLSX ou CSV.")

        importacao = ImportacaoArquivo.objects.create(
            nome_arquivo=uploaded_file.name,
            tipo_arquivo=suffix.lstrip("."),
            status=ImportacaoArquivo.Status.PROCESSANDO,
            iniciado_por=self.user,
        )

        try:
            with transaction.atomic():
                if suffix == ".csv":
                    summary = self._import_csv(uploaded_file, importacao)
                else:
                    summary = self._import_workbook(uploaded_file, importacao, suffix)
            importacao.status = ImportacaoArquivo.Status.CONCLUIDA
            importacao.resumo_json = summary
            importacao.processado_em = timezone.now()
            importacao.save(update_fields=["status", "resumo_json", "processado_em", "atualizado_em"])
        except Exception as exc:
            importacao.status = ImportacaoArquivo.Status.FALHA
            importacao.mensagem_erro = str(exc)
            importacao.processado_em = timezone.now()
            importacao.save(
                update_fields=["status", "mensagem_erro", "processado_em", "atualizado_em"]
            )
            raise

        return importacao

    def _import_workbook(self, uploaded_file, importacao: ImportacaoArquivo, suffix: str) -> dict[str, Any]:
        uploaded_file.seek(0)
        workbook = load_workbook(
            uploaded_file,
            read_only=True,
            data_only=True,
            keep_vba=suffix == ".xlsm",
        )
        requisitantes_lookup = self._load_requisitantes(workbook)
        self._load_predios(workbook)
        self._load_status_sipac_options(workbook)
        self._load_priority_rules(workbook)
        self._load_taxonomy_candidates(workbook)
        references = self._load_reference_priority_maps(workbook)
        base_sheet = self._get_sheet(workbook, "requisicoes - ct")
        rows = self._sheet_to_dicts(base_sheet)
        summary = self._upsert_requests(rows, importacao, requisitantes_lookup, references)
        summary["referencias"] = {
            "prioridades_gme": len(references["gme"]),
            "prioridades_ar": len(references["ar"]),
            "requisitantes": len(requisitantes_lookup),
        }
        return summary

    def _import_csv(self, uploaded_file, importacao: ImportacaoArquivo) -> dict[str, Any]:
        uploaded_file.seek(0)
        text = uploaded_file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows = []
        for row in reader:
            rows.append({self._normalized_header(key): value for key, value in row.items()})
        return self._upsert_requests(rows, importacao, {}, {"gme": {}, "ar": {}})

    def _upsert_requests(
        self,
        rows: list[dict[str, Any]],
        importacao: ImportacaoArquivo,
        requisitantes_lookup: dict[str, dict[str, str]],
        references: dict[str, dict[str, dict[str, str]]],
    ) -> dict[str, Any]:
        created = 0
        updated = 0
        counters = {
            "divisao": Counter(),
            "status_sipac": Counter(),
            "situacao_requisicao": Counter(),
            "sinfra_responsavel": Counter(),
            "prioridade_final": Counter(),
        }

        for row in rows:
            codigo = self._get_value(row, "n requisicao", "no requisicao", "codigo")
            if not codigo:
                continue
            numero, ano = extract_request_parts(str(codigo))
            requisitante_nome = self._get_value(row, "requisitante")
            requisitante_data = requisitantes_lookup.get(normalize_key(requisitante_nome), {})
            unidade_setor = self._get_value(row, "unidade/setor", "unidade setor") or requisitante_data.get("setor", "")
            contato = coerce_brazilian_phone(self._get_value(row, "contato") or requisitante_data.get("contato", ""))

            predio = self._ensure_predio(self._get_value(row, "predio envolvido"))
            taxonomia = self._ensure_taxonomia(
                self._get_value(row, "divisao"),
                self._get_value(row, "tipo de servico"),
                self._get_value(row, "servico"),
            )
            requisitante = self._ensure_requisitante(requisitante_nome, unidade_setor, contato)
            reference = references["gme"].get(str(codigo)) or references["ar"].get(str(codigo)) or {}

            defaults = {
                "numero": numero,
                "ano": ano,
                "assunto": clean_display_text(self._get_value(row, "assunto") or ""),
                "orcamento": self._get_value(row, "orcamento", "orçamento") or "",
                "data_cadastro": coerce_date(self._get_value(row, "data de cadastro")),
                "tipo_requisicao": clean_display_text(self._get_value(row, "tipo de requisicao") or ""),
                "divisao": clean_display_text(self._get_value(row, "divisao") or ""),
                "unidade_origem": clean_display_text(self._get_value(row, "unidade de origem") or ""),
                "status_sipac": clean_display_text(self._get_value(row, "status sipac") or ""),
                "tipo_servico": clean_display_text(self._get_value(row, "tipo de servico") or ""),
                "servico": clean_display_text(self._get_value(row, "servico") or ""),
                "taxonomia": taxonomia,
                "predio": predio,
                "local_servico": clean_display_text(self._get_value(row, "local do servico") or ""),
                "latitude": coerce_coordinate(self._get_value(row, "latitude"), kind="latitude"),
                "longitude": coerce_coordinate(self._get_value(row, "longitude"), kind="longitude"),
                "requisitante": requisitante,
                "nome_requisitante_snapshot": clean_display_text(requisitante_nome or ""),
                "unidade_setor_snapshot": clean_display_text(unidade_setor),
                "contato_direto_url": contato or "",
                "situacao_texto": clean_display_text(self._get_value(row, "situacao") or reference.get("situacao", "") or ""),
                "status_fluxo": clean_display_text(self._get_value(row, "status") or ""),
                "sinfra_responsavel": clean_display_text(self._get_value(row, "sinfra") or reference.get("sinfra", "") or ""),
                "link_atendimento": clean_display_text(self._get_value(row, "link do atendimento") or reference.get("link_atendimento", "") or ""),
                "link_sipac": clean_display_text(self._get_value(row, "link sipac") or reference.get("link_sipac", "") or ""),
                "data_execucao": coerce_date(self._get_value(row, "data execucao")),
                "dias_para_execucao": coerce_int(self._get_value(row, "dias para execucao")),
                "visivel_publicamente": True,
                "importacao_origem": importacao,
            }

            requisicao, was_created = Requisicao.objects.get_or_create(codigo=str(codigo), defaults=defaults)
            previous_status = requisicao.status_sipac if not was_created else ""
            previous_note = requisicao.situacao_texto if not was_created else ""
            if was_created:
                created += 1
            else:
                updated += 1
                for field, value in defaults.items():
                    setattr(requisicao, field, value)

            requisicao.prioridade_final = (
                reference.get("prioridade_final")
                or resolve_priority_label(requisicao.prioridade_lookup_key, requisicao.prioridade_final)
            )
            requisicao.save()
            if was_created:
                HistoricoStatus.objects.create(
                    requisicao=requisicao,
                    status_sipac=requisicao.status_sipac,
                    situacao_requisicao=requisicao.situacao_requisicao,
                    observacao=requisicao.situacao_texto,
                    origem=HistoricoStatus.Origem.IMPORTACAO,
                    usuario=self.user,
                )
            else:
                register_status_history(
                    requisicao,
                    previous_status=previous_status,
                    previous_note=previous_note,
                    note=requisicao.situacao_texto,
                    user=self.user,
                    origin=HistoricoStatus.Origem.IMPORTACAO,
                )

            counters["divisao"][requisicao.divisao] += 1
            counters["status_sipac"][requisicao.status_sipac] += 1
            counters["situacao_requisicao"][requisicao.situacao_requisicao] += 1
            counters["sinfra_responsavel"][requisicao.sinfra_responsavel] += 1
            counters["prioridade_final"][requisicao.prioridade_final] += 1

        return {
            "criados": created,
            "atualizados": updated,
            "total_processado": created + updated,
            "contagens": {key: dict(value) for key, value in counters.items()},
        }

    def _load_requisitantes(self, workbook) -> dict[str, dict[str, str]]:
        sheet = self._get_sheet(workbook, "requisitantes do ct")
        lookup: dict[str, dict[str, str]] = {}
        for index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            if index == 1:
                continue
            nome = normalize_text(row[0] if len(row) > 0 else "")
            if not nome:
                continue
            setor = normalize_text(row[1] if len(row) > 1 else "")
            contato = coerce_brazilian_phone(row[2] if len(row) > 2 else "")
            requisitante, _ = Requisitante.objects.get_or_create(
                chave_normalizada=normalize_key(nome),
                unidade_setor=setor,
                defaults={"nome": nome, "contato_url": contato},
            )
            changed = False
            if not requisitante.nome:
                requisitante.nome = nome
                changed = True
            if contato and requisitante.contato_url != contato:
                requisitante.contato_url = contato
                changed = True
            if changed:
                requisitante.save()
            lookup[normalize_key(nome)] = {"setor": setor, "contato": contato}
        return lookup

    def _load_predios(self, workbook) -> None:
        sheet = self._get_sheet(workbook, "legendas (1)")
        for row in sheet.iter_rows(min_row=2, max_col=16, values_only=True):
            nome = normalize_text(row[13] if len(row) > 13 else "")
            if not nome:
                continue
            latitude = coerce_coordinate(row[14] if len(row) > 14 else None, kind="latitude")
            longitude = coerce_coordinate(row[15] if len(row) > 15 else None, kind="longitude")
            predio, created = Predio.objects.get_or_create(
                chave_normalizada=normalize_key(nome),
                defaults={"nome": nome, "latitude": latitude, "longitude": longitude},
            )
            if not created:
                changed = False
                if not predio.nome:
                    predio.nome = nome
                    changed = True
                if latitude is not None and predio.latitude != latitude:
                    predio.latitude = latitude
                    changed = True
                if longitude is not None and predio.longitude != longitude:
                    predio.longitude = longitude
                    changed = True
                if changed:
                    predio.save()

    def _load_status_sipac_options(self, workbook) -> None:
        sheet = self._get_sheet(workbook, "legendas (1)")
        seen: dict[str, int] = {}
        for row in sheet.iter_rows(min_row=2, min_col=23, max_col=23, values_only=True):
            descricao = clean_display_text(row[0] if row else "")
            if not descricao:
                continue
            metadata = resolve_status_sipac_metadata(descricao)
            ordem = metadata["ordem"] or seen.setdefault(descricao, len(seen) + 1)
            StatusSipacOpcao.objects.update_or_create(
                descricao=metadata["descricao"] or descricao,
                defaults={
                    "numero": metadata["numero"],
                    "rotulo": metadata["rotulo"] or descricao,
                    "descricao": metadata["descricao"] or descricao,
                    "chave_normalizada": normalize_key(metadata["descricao"] or descricao),
                    "ordem": ordem,
                    "ativa": True,
                },
            )

    def _load_priority_rules(self, workbook) -> None:
        sheet = self._get_sheet(workbook, "legendas (1)")
        for row in sheet.iter_rows(min_row=2, min_col=44, max_col=45, values_only=True):
            key = normalize_key(row[0] if len(row) > 0 else "")
            priority = normalize_text(row[1] if len(row) > 1 else "")
            if not key or not priority:
                continue
            RegraPrioridade.objects.update_or_create(
                chave_normalizada=key,
                defaults={"prioridade": priority, "descricao": "Importada da planilha"},
            )

    def _load_taxonomy_candidates(self, workbook) -> None:
        if self._load_taxonomy_candidates_from_legendas_1(workbook):
            return
        self._load_taxonomy_candidates_from_legendas_2(workbook)

    def _load_taxonomy_candidates_from_legendas_1(self, workbook) -> bool:
        sheet = self._get_sheet(workbook, "legendas (1)")
        divisao_orders: dict[str, int] = {}
        tipo_orders: dict[tuple[str, str], int] = {}
        servico_orders: dict[tuple[str, str, str], int] = {}
        found = False

        for row in sheet.iter_rows(min_row=2, min_col=27, max_col=29, values_only=True):
            divisao = self._clean_display_text(row[0] if len(row) > 0 else "")
            tipo = self._clean_display_text(row[1] if len(row) > 1 else "")
            servico = self._clean_display_text(row[2] if len(row) > 2 else "")
            if not divisao and not tipo and not servico:
                continue
            found = True
            ordem_divisao = divisao_orders.setdefault(divisao, len(divisao_orders) + 1) if divisao else None
            ordem_tipo = None
            ordem_servico = None
            if divisao and tipo:
                ordem_tipo = tipo_orders.setdefault((divisao, tipo), len([key for key in tipo_orders if key[0] == divisao]) + 1)
            if divisao and tipo and servico:
                ordem_servico = servico_orders.setdefault(
                    (divisao, tipo, servico),
                    len([key for key in servico_orders if key[0] == divisao and key[1] == tipo]) + 1,
                )
            self._upsert_taxonomia_hierarchy(divisao, tipo, servico, ordem_divisao, ordem_tipo, ordem_servico)

        return found

    def _load_taxonomy_candidates_from_legendas_2(self, workbook) -> None:
        sheet = self._get_sheet(workbook, "legendas (2)")
        division_types: dict[str, list[str]] = defaultdict(list)
        divisao_orders: dict[str, int] = {}
        tipo_orders: dict[tuple[str, str], int] = {}
        servico_orders: dict[tuple[str, str, str], int] = {}

        for row in sheet.iter_rows(min_row=2, min_col=18, max_col=25, values_only=True):
            divisao = self._clean_display_text(row[0] if len(row) > 0 else "")
            if not divisao:
                continue
            ordem_divisao = divisao_orders.setdefault(divisao, len(divisao_orders) + 1)
            self._upsert_taxonomia_hierarchy(divisao, "", "", ordem_divisao, None, None)
            for index, tipo in enumerate(row[1:], start=1):
                tipo_text = self._clean_display_text(tipo)
                if not tipo_text:
                    continue
                division_types[divisao].append(tipo_text)
                tipo_orders.setdefault((divisao, tipo_text), index)
                self._upsert_taxonomia_hierarchy(divisao, tipo_text, "", ordem_divisao, index, None)

        for row in sheet.iter_rows(min_row=2, min_col=27, max_col=37, values_only=True):
            tipo = self._clean_display_text(row[0] if len(row) > 0 else "")
            if not tipo:
                continue
            divisao = next((key for key, values in division_types.items() if tipo in values), "")
            ordem_divisao = divisao_orders.get(divisao)
            ordem_tipo = tipo_orders.get((divisao, tipo))
            for index, servico in enumerate(row[1:], start=1):
                servico_text = self._clean_display_text(servico)
                if not servico_text or not divisao:
                    continue
                servico_orders.setdefault((divisao, tipo, servico_text), index)
                self._upsert_taxonomia_hierarchy(divisao, tipo, servico_text, ordem_divisao, ordem_tipo, index)

    def _upsert_taxonomia_hierarchy(
        self,
        divisao: str,
        tipo_servico: str,
        servico: str,
        ordem_divisao: int | None,
        ordem_tipo: int | None,
        ordem_servico: int | None,
    ) -> None:
        if divisao:
            TaxonomiaServico.objects.update_or_create(
                chave_normalizada=normalize_key(divisao),
                defaults={
                    "divisao": divisao,
                    "tipo_servico": "",
                    "servico": "",
                    "ordem_divisao": ordem_divisao,
                    "ordem_tipo": None,
                    "ordem_servico": None,
                },
            )
        if divisao and tipo_servico:
            TaxonomiaServico.objects.update_or_create(
                chave_normalizada=normalize_key(divisao, tipo_servico),
                defaults={
                    "divisao": divisao,
                    "tipo_servico": tipo_servico,
                    "servico": "",
                    "ordem_divisao": ordem_divisao,
                    "ordem_tipo": ordem_tipo,
                    "ordem_servico": None,
                },
            )
        if divisao and tipo_servico and servico:
            TaxonomiaServico.objects.update_or_create(
                chave_normalizada=normalize_key(divisao, tipo_servico, servico),
                defaults={
                    "divisao": divisao,
                    "tipo_servico": tipo_servico,
                    "servico": servico,
                    "ordem_divisao": ordem_divisao,
                    "ordem_tipo": ordem_tipo,
                    "ordem_servico": ordem_servico,
                },
            )

    def _load_reference_priority_maps(self, workbook) -> dict[str, dict[str, dict[str, str]]]:
        return {
            "gme": self._load_reference_sheet(workbook, "prioridades sinfra - gme"),
            "ar": self._load_reference_sheet(workbook, "prioridades ar-condicionado"),
        }

    def _load_reference_sheet(self, workbook, sheet_name: str) -> dict[str, dict[str, str]]:
        sheet = self._get_sheet(workbook, sheet_name)
        references = {}
        for row in self._sheet_to_dicts(sheet):
            codigo = self._get_value(row, "n requisicao", "no requisicao")
            if not codigo:
                continue
            references[str(codigo)] = {
                "sinfra": clean_display_text(self._get_value(row, "sinfra")),
                "prioridade_final": clean_display_text(self._get_value(row, "prioridade")),
                "link_atendimento": clean_display_text(self._get_value(row, "link do atendimento")),
                "link_sipac": clean_display_text(self._get_value(row, "link sipac")),
                "situacao": clean_display_text(self._get_value(row, "situacao")),
            }
        return references

    def _ensure_predio(self, nome: str | None) -> Predio | None:
        if not nome:
            return None
        normalized = normalize_key(nome)
        predio = Predio.objects.filter(chave_normalizada=normalized).first()
        if predio:
            return predio
        return Predio.objects.create(nome=normalize_text(nome))

    def _ensure_requisitante(self, nome: str | None, setor: str, contato: str) -> Requisitante | None:
        if not nome:
            return None
        normalized = normalize_key(nome)
        normalized_setor = normalize_text(setor)
        requisitante = Requisitante.objects.filter(
            chave_normalizada=normalized,
            unidade_setor=normalized_setor,
        ).first()
        if requisitante:
            changed = False
            if contato and requisitante.contato_url != contato:
                requisitante.contato_url = contato
                changed = True
            if changed:
                requisitante.save()
            return requisitante
        return Requisitante.objects.create(
            nome=normalize_text(nome),
            unidade_setor=normalized_setor,
            contato_url=coerce_brazilian_phone(contato),
        )

    def _ensure_taxonomia(self, divisao: str | None, tipo_servico: str | None, servico: str | None) -> TaxonomiaServico | None:
        if not divisao and not tipo_servico and not servico:
            return None
        divisao = self._clean_display_text(divisao)
        tipo_servico = self._clean_display_text(tipo_servico)
        servico = self._clean_display_text(servico)
        key = normalize_key(divisao, tipo_servico, servico)
        taxonomia = TaxonomiaServico.objects.filter(chave_normalizada=key).first()
        if taxonomia:
            return taxonomia
        return TaxonomiaServico.objects.create(
            divisao=divisao,
            tipo_servico=tipo_servico,
            servico=servico,
        )

    def _get_sheet(self, workbook, normalized_title: str):
        for sheet in workbook.worksheets:
            if self._normalized_header(sheet.title) == self._normalized_header(normalized_title):
                return sheet
        raise ImportErrorPlanilha(f"Aba obrigatória não encontrada: {normalized_title}")

    def _sheet_to_dicts(self, sheet) -> list[dict[str, Any]]:
        iterator = sheet.iter_rows(values_only=True)
        try:
            header = next(iterator)
        except StopIteration as exc:
            raise ImportErrorPlanilha(f"Aba vazia: {sheet.title}") from exc
        header_map = [self._normalized_header(column) for column in header]
        rows = []
        for raw_row in iterator:
            row = {}
            for index, column in enumerate(header_map):
                if not column:
                    continue
                row[column] = raw_row[index] if index < len(raw_row) else None
            rows.append(row)
        return rows

    def _get_value(self, row: dict[str, Any], *aliases: str) -> Any:
        for alias in aliases:
            key = self._normalized_header(alias)
            if key in row:
                return row[key]
        return None

    def _normalized_header(self, value: Any) -> str:
        normalized = normalize_text(value).lower()
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return normalized.strip()

    def _clean_display_text(self, value: Any) -> str:
        return clean_display_text(value)
