from django.urls import path

from . import views

app_name = 'processos'

urlpatterns = [
    path('', views.ProcessosListaView.as_view(), name='lista'),
    path('cadastro/', views.ProcessoCadastroView.as_view(), name='cadastro'),
    path('<int:pk>/', views.ProcessoDetalheView.as_view(), name='detalhe'),
    path('<int:pk>/editar/', views.ProcessoEdicaoView.as_view(), name='edicao'),
    path('priorizacao-az/', views.PriorizacaoAZView.as_view(), name='priorizacao-az'),
    path('empenhos/', views.EmpenhoProcessosView.as_view(), name='empenhos'),
    path('<int:processo_pk>/orcamento/add/', views.orcamento_add, name='orcamento-add'),
    path('<int:processo_pk>/orcamento/<int:orcamento_pk>/delete/', views.orcamento_delete, name='orcamento-delete'),
    path('<int:pk>/az/', views.priorizacao_az_update, name='priorizacao-az-update'),
    path('modelo/', views.modelo_planilha_processos, name='modelo-planilha'),
    path('importar/', views.importar_processos, name='importar'),
    path('public/consulta/', views.public_consulta_processos, name='public-consulta'),
    path('publico/<int:pk>/', views.ProcessoPublicoDetalheView.as_view(), name='detalhe-publico'),
]
