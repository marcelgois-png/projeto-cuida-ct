from django.contrib import admin

from apps.core.models import (
    Predio,
    RegraPrioridade,
    TaxonomiaServico,
    StatusRequisicao,
    Solicitante,
)

from .models import (
    HistoricoStatus,
    ImportacaoArquivo,
    Requisicao,
)


@admin.register(Predio)
class PredioAdmin(admin.ModelAdmin):
    list_display = ("nome", "latitude", "longitude", "visivel_publicamente")
    search_fields = ("nome",)


@admin.register(Solicitante)
class SolicitanteAdmin(admin.ModelAdmin):
    list_display = ("nome", "setor", "contato_url", "visivel_publicamente")
    search_fields = ("nome",)
    list_filter = ("setor",)


@admin.register(TaxonomiaServico)
class TaxonomiaServicoAdmin(admin.ModelAdmin):
    list_display = ("divisao", "tipo_servico", "servico")
    list_filter = ("divisao", "tipo_servico")
    search_fields = ("divisao", "tipo_servico", "servico")


@admin.register(StatusRequisicao)
class StatusRequisicaoAdmin(admin.ModelAdmin):
    list_display = ("numero", "nome", "codigo", "mapeamento_situacao", "ordem", "ativa")
    list_filter = ("ativa", "mapeamento_situacao")
    search_fields = ("numero", "nome", "codigo")
    ordering = ("ordem", "numero", "codigo")


@admin.register(RegraPrioridade)
class RegraPrioridadeAdmin(admin.ModelAdmin):
    list_display = ("chave_normalizada", "prioridade", "origem", "ativa")
    list_filter = ("prioridade", "origem", "ativa")
    search_fields = ("chave_normalizada", "descricao")


class HistoricoStatusInline(admin.TabularInline):
    model = HistoricoStatus
    extra = 0
    readonly_fields = ("status_sipac", "situacao_requisicao", "origem", "usuario", "criado_em")


@admin.register(Requisicao)
class RequisicaoAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "divisao",
        "tipo_servico",
        "servico",
        "status_sipac",
        "situacao_requisicao",
        "prioridade_final",
        "sinfra_responsavel",
        "visivel_publicamente",
    )
    list_filter = ("situacao_requisicao", "status_sipac", "prioridade_final", "sinfra_responsavel")
    search_fields = ("codigo", "assunto", "local_servico", "nome_requisitante_snapshot")
    inlines = [HistoricoStatusInline]


@admin.register(ImportacaoArquivo)
class ImportacaoArquivoAdmin(admin.ModelAdmin):
    list_display = ("nome_arquivo", "tipo_arquivo", "status", "iniciado_por", "criado_em", "processado_em")
    readonly_fields = ("resumo_json", "mensagem_erro")
