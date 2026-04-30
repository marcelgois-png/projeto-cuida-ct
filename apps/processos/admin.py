from django.contrib import admin

from .models import OrcamentoEmpenho, Orcamento, Processo


class OrcamentoInline(admin.TabularInline):
    model = Orcamento
    extra = 0
    fields = ('numero_sequencial', 'descricao', 'valor', 'status', 'data_emissao')
    show_change_link = True


@admin.register(Processo)
class ProcessoAdmin(admin.ModelAdmin):
    list_display = (
        'numero_processo', 'assunto', 'status', 'gerencia',
        'predio', 'data_abertura', 'data_conclusao',
    )
    list_filter = ('status', 'gerencia', 'situacao_sipac', 'servico')
    search_fields = ('numero_processo', 'assunto')
    date_hierarchy = 'data_abertura'
    inlines = [OrcamentoInline]
    filter_horizontal = ('solicitantes', 'requisicoes')
    raw_id_fields = ('empresa', 'encaminhamento_diretor')


@admin.register(Orcamento)
class OrcamentoAdmin(admin.ModelAdmin):
    list_display = (
        'processo', 'numero_sequencial', 'valor', 'status', 'data_emissao',
    )
    list_filter = ('status',)
    search_fields = ('processo__numero_processo', 'descricao')


@admin.register(OrcamentoEmpenho)
class OrcamentoEmpenhoAdmin(admin.ModelAdmin):
    list_display = ('orcamento', 'empenho', 'valor_alocado', 'data_vinculacao')
    search_fields = ('orcamento__processo__numero_processo',)
