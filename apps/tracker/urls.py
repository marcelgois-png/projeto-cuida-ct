from django.urls import path

from . import views


urlpatterns = [
    path("hub/", views.HubModuloView.as_view(), name="hub-modulo"),
    path("", views.PublicDashboardView.as_view(), name="public-dashboard"),
    path("requisicoes/<int:pk>/", views.PublicRequisicaoDetailView.as_view(), name="public-requisicao-detail"),
    path("public/painel/", views.public_dashboard_panel, name="public-dashboard-panel"),
    path("public/consulta-req/", views.home_consulta_req, name="home-consulta-req"),
    path("painel-controle/", views.PublicControlPanelView.as_view(), name="public-control-panel"),
    path("painel-controle/conteudo/", views.public_control_panel_content, name="public-control-panel-content"),
    path("painel-controle/shell/", views.public_control_panel_shell, name="public-control-panel-shell"),
    path("public/requisicoes/tabela/", views.public_requisicoes_table, name="public-requisicoes-table"),
    path("painel/", views.InternalCadastroView.as_view(), name="internal-cadastro"),
    path("painel/lista/", views.InternalListaView.as_view(), name="internal-lista"),
    path("painel/lista/painel/", views.internal_requisicoes_panel, name="internal-requisicoes-panel"),
    path("painel/orcamento/", views.InternalOrcamentoView.as_view(), name="internal-orcamento"),
    path("painel/orcamento/painel/", views.internal_orcamento_panel, name="internal-orcamento-panel"),
    path("painel/orcamento/nota/add/", views.nota_empenho_crud, name="nota-empenho-add"),
    path("painel/orcamento/nota/<int:pk>/edit/", views.nota_empenho_crud, name="nota-empenho-edit"),
    path("painel/orcamento/nota/<int:pk>/delete/", views.nota_empenho_delete, name="nota-empenho-delete"),
    path("painel/orcamento/nota/<int:pk>/reforco/", views.nota_empenho_reforco, name="nota-empenho-reforco"),
    path(
        "painel/orcamento/nota/<int:pk>/reforco/<int:reforco_pk>/edit/",
        views.nota_empenho_reforco,
        name="nota-empenho-reforco-edit",
    ),
    path(
        "painel/orcamento/nota/<int:pk>/reforco/<int:reforco_pk>/delete/",
        views.nota_empenho_reforco_delete,
        name="nota-empenho-reforco-delete",
    ),
    path(
        "painel/orcamento/requisicao/<int:pk>/nota/",
        views.requisicao_orcamento_nota_update,
        name="requisicao-orcamento-nota-update",
    ),
    path(
        "painel/orcamento/requisicoes/nota/",
        views.requisicoes_orcamento_nota_bulk_update,
        name="requisicoes-orcamento-nota-bulk-update",
    ),
    path("painel/priorizacao/", views.InternalPriorizacaoView.as_view(), name="internal-priorizacao"),
    path("painel/visitas/", views.InternalVisitasView.as_view(), name="internal-visitas"),
    path("painel/priorizacao/tabela/", views.internal_priorizacao_table, name="internal-priorizacao-table"),
    path("painel/priorizacao/painel/", views.internal_priorizacao_panel, name="internal-priorizacao-panel"),
    path("painel/decisoes/", views.InternalDecisoesView.as_view(), name="internal-decisoes"),
    path("painel/decisoes/painel/", views.internal_decisoes_panel, name="internal-decisoes-panel"),
    path("painel/encaminhamentos/", views.InternalEncaminhamentosView.as_view(), name="internal-encaminhamentos"),
    path("painel/encaminhamentos/<int:pk>/cancelar/", views.internal_cancel_encaminhamento, name="internal-cancel-encaminhamento"),
    path("painel/decisoes/tabela/", views.internal_decisoes_table, name="internal-decisoes-table"),
    path("painel/requisicoes/<int:pk>/indicar-processo/", views.indicar_processo, name="indicar-processo"),
    path("painel/requisicoes/<int:pk>/", views.InternalRequisicaoDetailView.as_view(), name="internal-requisicao-detail"),
    path("painel/requisicoes/tabela/", views.internal_requisicoes_table, name="internal-requisicoes-table"),
    path("painel/requisicoes/nova/", views.RequisicaoCreateView.as_view(), name="requisicao-create"),
    path("painel/requisicoes/<int:pk>/editar/", views.RequisicaoUpdateView.as_view(), name="requisicao-update"),
    path("painel/requisicoes/<int:pk>/apagar/", views.requisicao_delete, name="requisicao-delete"),
    path("painel/cadastro-lote/modelo.xlsx", views.modelo_cadastro_lote, name="modelo-cadastro-lote"),
    path("painel/cadastro-lote/", views.cadastro_lote_upload, name="cadastro-lote-upload"),
    path("api/public/indicadores/", views.api_public_indicadores, name="api-public-indicadores"),
    path("api/public/requisicoes/", views.api_public_requisicoes, name="api-public-requisicoes"),
    path("api/public/requisicoes/<int:pk>/", views.api_public_requisicao_detail, name="api-public-requisicao-detail"),
    path("api/internal/requisicoes/", views.api_internal_requisicoes, name="api-internal-requisicoes"),
    path("api/internal/requisicoes/<int:pk>/", views.api_internal_requisicao_detail, name="api-internal-requisicao-detail"),
    path("api/internal/importacoes/", views.api_internal_importacoes, name="api-internal-importacoes"),
    path("api/internal/regras-prioridade/", views.api_internal_regras_prioridade, name="api-internal-regras-prioridade"),
    path("api/internal/cadastros/", views.api_internal_cadastros, name="api-internal-cadastros"),
    
    # Gestão de Listas (Admin)
    path("painel/listas/", views.InternalGestaoListasView.as_view(), name="internal-gestao-listas"),
    path("painel/listas/status/add/", views.status_sipac_crud, name="status-sipac-add"),
    path("painel/listas/status/bulk/", views.status_sipac_bulk, name="status-sipac-bulk"),
    path("painel/listas/status/<int:pk>/edit/", views.status_sipac_crud, name="status-sipac-edit"),
    path("painel/listas/status/<int:pk>/delete/", views.status_sipac_delete, name="status-sipac-delete"),
    path("painel/listas/taxonomia/add/", views.taxonomia_crud, name="taxonomia-add"),
    path("painel/listas/taxonomia/<int:pk>/edit/", views.taxonomia_crud, name="taxonomia-edit"),
    path("painel/listas/taxonomia/<int:pk>/delete/", views.taxonomia_delete, name="taxonomia-delete"),
    path("painel/listas/gut/add/", views.gut_parametro_crud, name="gut-parametro-add"),
    path("painel/listas/gut/<int:pk>/edit/", views.gut_parametro_crud, name="gut-parametro-edit"),
    path("painel/listas/gut/<int:pk>/delete/", views.gut_parametro_delete, name="gut-parametro-delete"),
    path("painel/listas/empresa/add/", views.empresa_crud, name="empresa-add"),
    path("painel/listas/empresa/<int:pk>/edit/", views.empresa_crud, name="empresa-edit"),
    path("painel/listas/empresa/<int:pk>/delete/", views.empresa_delete, name="empresa-delete"),

    # Autocomplete
    path("api/autocomplete/solicitantes/", views.api_autocomplete_solicitantes, name="api-autocomplete-solicitantes"),

    # Gestão de Listas — Prédios
    path("painel/listas/predios/add/", views.predio_crud, name="predio-add"),
    path("painel/listas/predios/<int:pk>/edit/", views.predio_crud, name="predio-edit"),
    path("painel/listas/predios/<int:pk>/delete/", views.predio_delete, name="predio-delete"),

    # Gestão de Listas — Setores
    path("painel/listas/setores/add/", views.setor_crud, name="setor-add"),
    path("painel/listas/setores/<int:pk>/edit/", views.setor_crud, name="setor-edit"),
    path("painel/listas/setores/<int:pk>/delete/", views.setor_delete, name="setor-delete"),

    # Gestão de Listas — Tipos de Ambiente
    path("painel/listas/tipo-ambiente/add/", views.tipo_ambiente_crud, name="tipo-ambiente-add"),
    path("painel/listas/tipo-ambiente/<int:pk>/edit/", views.tipo_ambiente_crud, name="tipo-ambiente-edit"),
    path("painel/listas/tipo-ambiente/<int:pk>/delete/", views.tipo_ambiente_delete, name="tipo-ambiente-delete"),
    path("painel/listas/tipo-ambiente/<int:pk>/toggle/", views.tipo_ambiente_toggle, name="tipo-ambiente-toggle"),

    # Gestão de Listas — Solicitantes
    path("painel/listas/solicitantes/add/", views.solicitante_crud, name="solicitante-add"),
    path("painel/listas/solicitantes/<int:pk>/edit/", views.solicitante_crud, name="solicitante-edit"),
    path("painel/listas/solicitantes/<int:pk>/delete/", views.solicitante_delete, name="solicitante-delete"),

    # Edição Dinâmica e Ações em Lote
    path("painel/priorizacao/bulk-assign/", views.priorizacao_bulk_assign_empresa, name="priorizacao-bulk-assign"),
    path("painel/decisoes/encaminhamento/preview/", views.internal_decision_forward_preview, name="decisoes-encaminhamento-preview"),
    path("painel/decisoes/bulk-decide/", views.internal_bulk_decide_process, name="decisoes-bulk-decide"),
    path("painel/lista/bulk-decisions/preview/", views.internal_bulk_decisions_preview, name="lista-bulk-decisions-preview"),
    path("painel/lista/bulk-decisions/", views.internal_bulk_decisions, name="lista-bulk-decisions"),
    path("painel/requisicoes/<int:pk>/update-gut/", views.update_requisicao_gut, name="update-requisicao-gut"),
]
