from django.urls import path

from . import views

app_name = 'processos'

urlpatterns = [
    path('', views.ProcessosListaView.as_view(), name='lista'),
    path('painel-controle/', views.PainelProcessosView.as_view(), name='painel-controle'),
    path('cadastro/', views.ProcessosCadastroPainelView.as_view(), name='cadastro'),
    path('cadastro/novo/', views.ProcessoCadastroView.as_view(), name='cadastro-novo'),
    path('<int:pk>/', views.ProcessoDetalheView.as_view(), name='detalhe'),
    path('<int:pk>/editar/', views.ProcessoEdicaoView.as_view(), name='edicao'),
    path('priorizacao-az/', views.PriorizacaoAZView.as_view(), name='priorizacao-az'),
    path('empenhos/', views.EmpenhoProcessosView.as_view(), name='empenhos'),
    path('empenhos/nota/add/', views.processo_nota_empenho_crud, name='empenho-nota-add'),
    path('empenhos/nota/<int:pk>/edit/', views.processo_nota_empenho_crud, name='empenho-nota-edit'),
    path('empenhos/nota/<int:pk>/delete/', views.processo_nota_empenho_delete, name='empenho-nota-delete'),
    path('empenhos/nota/<int:pk>/reforco/', views.processo_nota_empenho_reforco, name='empenho-nota-reforco'),
    path('empenhos/nota/<int:pk>/reforco/<int:reforco_pk>/edit/', views.processo_nota_empenho_reforco, name='empenho-nota-reforco-edit'),
    path('empenhos/nota/<int:pk>/reforco/<int:reforco_pk>/delete/', views.processo_nota_empenho_reforco_delete, name='empenho-nota-reforco-delete'),
    path('<int:processo_pk>/orcamento/<int:orcamento_pk>/edit/', views.orcamento_edit, name='orcamento-edit'),
    path('<int:processo_pk>/orcamento/add/', views.orcamento_add, name='orcamento-add'),
    path('<int:processo_pk>/orcamento/<int:orcamento_pk>/delete/', views.orcamento_delete, name='orcamento-delete'),
    path('<int:processo_pk>/orcamento/ia-extrair/', views.orcamento_ia_extrair, name='orcamento-ia-extrair'),
    path('orcamento/<int:orcamento_pk>/itens/', views.orcamento_itens, name='orcamento-itens'),
    path('orcamento/<int:orcamento_pk>/item/add/', views.orcamento_item_add, name='orcamento-item-add'),
    path('orcamento/<int:orcamento_pk>/item/<int:item_pk>/edit/', views.orcamento_item_edit, name='orcamento-item-edit'),
    path('orcamento/<int:orcamento_pk>/item/<int:item_pk>/delete/', views.orcamento_item_delete, name='orcamento-item-delete'),
    path('orcamento/<int:orcamento_pk>/ajuste/add/', views.orcamento_ajuste_add, name='orcamento-ajuste-add'),
    path('orcamento/<int:orcamento_pk>/ajuste/<int:ajuste_pk>/delete/', views.orcamento_ajuste_delete, name='orcamento-ajuste-delete'),
    path('<int:pk>/az/', views.priorizacao_az_update, name='priorizacao-az-update'),
    path('<int:pk>/apagar/', views.processo_delete, name='apagar'),
    path('apagar-lote/', views.processos_bulk_delete, name='apagar-lote'),
    path('diagnosticar/', views.diagnosticar_planilha, name='diagnosticar'),
    path('modelo/', views.modelo_planilha_processos, name='modelo-planilha'),
    path('importar/', views.importar_processos, name='importar'),
    path('public/consulta/', views.public_consulta_processos, name='public-consulta'),
    path('public/lista/', views.public_lista_processos, name='public-lista'),
    path('publico/<int:pk>/', views.ProcessoPublicoDetalheView.as_view(), name='detalhe-publico'),
]
