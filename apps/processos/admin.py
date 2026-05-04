from django.contrib import admin

from .models import InteressadoProcesso, ItemOrcamento, OrcamentoEmpenho, Orcamento, Processo


class ItemOrcamentoInline(admin.TabularInline):
    model = ItemOrcamento
    extra = 0
    fields = ('ordem', 'numero', 'descricao', 'valor')


class OrcamentoInline(admin.TabularInline):
    model = Orcamento
    extra = 0
    fields = ('numero_sequencial', 'descricao', 'valor', 'status', 'data_emissao')
    show_change_link = True


class InteressadoProcessoInline(admin.TabularInline):
    model = InteressadoProcesso
    extra = 0
    fields = ('tipo', 'identificador', 'nome')


@admin.register(Processo)
class ProcessoAdmin(admin.ModelAdmin):
    list_display = (
        'numero_processo', 'assunto', 'status', 'gerencia',
        'predio', 'data_abertura', 'data_conclusao',
    )
    list_filter = ('status', 'gerencia', 'situacao_sipac', 'servico')
    search_fields = ('numero_processo', 'assunto', 'unidade_origem', 'interessados__nome')
    date_hierarchy = 'data_abertura'
    inlines = [InteressadoProcessoInline, OrcamentoInline]
    filter_horizontal = ('solicitantes', 'requisicoes')
    raw_id_fields = ('empresa', 'encaminhamento_diretor')


@admin.register(Orcamento)
class OrcamentoAdmin(admin.ModelAdmin):
    list_display = (
        'processo', 'numero_sequencial', 'valor', 'status', 'data_emissao',
    )
    list_filter = ('status',)
    search_fields = ('processo__numero_processo', 'descricao')
    inlines = [ItemOrcamentoInline]


@admin.register(ItemOrcamento)
class ItemOrcamentoAdmin(admin.ModelAdmin):
    list_display = ('orcamento', 'numero', 'descricao', 'valor', 'ordem')
    search_fields = ('orcamento__processo__numero_processo', 'descricao')
    list_filter = ()


@admin.register(OrcamentoEmpenho)
class OrcamentoEmpenhoAdmin(admin.ModelAdmin):
    list_display = ('orcamento', 'empenho', 'valor_alocado', 'data_vinculacao')
    search_fields = ('orcamento__processo__numero_processo',)


@admin.register(InteressadoProcesso)
class InteressadoProcessoAdmin(admin.ModelAdmin):
    list_display = ('processo', 'tipo', 'identificador', 'nome')
    search_fields = ('processo__numero_processo', 'tipo', 'identificador', 'nome')
    list_filter = ('tipo',)
