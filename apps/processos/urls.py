from django.urls import path

from . import views

app_name = 'processos'

urlpatterns = [
    path('', views.ProcessosListaView.as_view(), name='lista'),
    path('cadastro/', views.ProcessosCadastroView.as_view(), name='cadastro'),
    path('priorizacao-az/', views.PriorizacaoAZView.as_view(), name='priorizacao-az'),
    path('empenhos/', views.EmpenhoProcessosView.as_view(), name='empenhos'),
]
