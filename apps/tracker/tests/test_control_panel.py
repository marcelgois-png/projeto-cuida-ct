from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.tracker.models import Predio, Requisicao
from apps.tracker.services import control_panel_analytics, resolve_control_panel_macrostatus


User = get_user_model()


class ControlPanelServiceTests(TestCase):
    def test_resolve_control_panel_macrostatus_groups_expected_statuses(self):
        self.assertEqual(resolve_control_panel_macrostatus("02 ENVIADA"), "em_andamento")
        self.assertEqual(resolve_control_panel_macrostatus("06 FINALIZADA"), "finalizada")
        self.assertEqual(resolve_control_panel_macrostatus("09 NEGADA"), "nao_executada")
        self.assertEqual(
            resolve_control_panel_macrostatus("13 NAO EXECUTADO - FINALIZADA PELO TEMPO SINFRA"),
            "nao_executada",
        )
        self.assertEqual(resolve_control_panel_macrostatus("07 RETORNADA"), "retornada_estornada")
        self.assertEqual(resolve_control_panel_macrostatus("08 ESTORNADA"), "retornada_estornada")
        self.assertEqual(resolve_control_panel_macrostatus(""), "outros")


class ControlPanelViewTests(TestCase):
    def setUp(self):
        self.predio_a = Predio.objects.create(nome="Bloco A")
        self.predio_b = Predio.objects.create(nome="Bloco B")

        self.operator = User.objects.create_user(
            username="operador_dashboard",
            password="segredo",
            role="operator",
            nome_completo="Operador Dashboard",
            telefone="83999990000",
        )
        self.director = User.objects.create_user(
            username="diretor_dashboard",
            password="segredo",
            role="director",
            nome_completo="Diretor Dashboard",
            telefone="83999990001",
        )
        self.admin = User.objects.create_user(
            username="admin_dashboard",
            password="segredo",
            role="admin",
            nome_completo="Admin Dashboard",
            telefone="83999990002",
        )

        self.public_active = Requisicao.objects.create(
            codigo="101/2026",
            numero=101,
            ano=2026,
            assunto="Climatizacao do laboratorio",
            data_cadastro=date(2026, 3, 1),
            divisao="Construcao Civil",
            status_sipac="02 ENVIADA",
            tipo_servico="Ar Condicionado",
            servico="Split",
            predio=self.predio_a,
            prioridade_final="",
            visivel_publicamente=True,
        )
        self.public_finalized_budget = Requisicao.objects.create(
            codigo="102/2025",
            numero=102,
            ano=2025,
            assunto="Troca de equipamento",
            data_cadastro=date(2025, 2, 1),
            data_execucao=date(2025, 2, 11),
            divisao="Construcao Civil",
            status_sipac="06 FINALIZADA",
            tipo_servico="Ar Condicionado",
            servico="Split",
            predio=self.predio_a,
            orcamento_valor=Decimal("1000.00"),
            sinfra_responsavel="Equipe 1",
            visivel_publicamente=True,
        )
        self.public_finalized_without_budget = Requisicao.objects.create(
            codigo="103/2026",
            numero=103,
            ano=2026,
            assunto="Reparo eletrico",
            data_cadastro=date(2026, 1, 1),
            data_execucao=date(2026, 1, 21),
            divisao="Instalacoes Eletricas",
            status_sipac="06 FINALIZADA",
            tipo_servico="Eletrica",
            servico="Tomada",
            predio=self.predio_b,
            visivel_publicamente=True,
        )
        self.public_negada = Requisicao.objects.create(
            codigo="104/2026",
            numero=104,
            ano=2026,
            assunto="Servico negado",
            data_cadastro=date(2026, 2, 2),
            divisao="Instalacoes Hidraulicas",
            status_sipac="09 NEGADA",
            tipo_servico="Hidraulica",
            servico="Vazamento",
            predio=self.predio_b,
            visivel_publicamente=True,
        )
        self.public_estornada = Requisicao.objects.create(
            codigo="105/2026",
            numero=105,
            ano=2026,
            assunto="Servico estornado",
            data_cadastro=date(2026, 2, 10),
            divisao="Marcenaria",
            status_sipac="08 ESTORNADA",
            tipo_servico="Marcenaria",
            servico="Porta",
            predio=self.predio_b,
            visivel_publicamente=True,
        )
        self.hidden_finalized = Requisicao.objects.create(
            codigo="106/2026",
            numero=106,
            ano=2026,
            assunto="Oculta do publico",
            data_cadastro=date(2026, 2, 1),
            data_execucao=date(2026, 2, 6),
            divisao="Construcao Civil",
            status_sipac="06 FINALIZADA",
            tipo_servico="Ar Condicionado",
            servico="Split",
            predio=self.predio_a,
            orcamento_valor=Decimal("5000.00"),
            visivel_publicamente=False,
        )

    def test_control_panel_analytics_aggregates_public_metrics_and_internal_triage(self):
        analytics = control_panel_analytics(
            Requisicao.objects.filter(visivel_publicamente=True).select_related("predio"),
            include_internal=True,
            years=[2025, 2026],
        )

        summary = {item["label"]: item["value"] for item in analytics["summary_cards"]}
        self.assertEqual(summary["Total de requisições"], 5)
        self.assertEqual(summary["Requisições ativas"], 1)
        self.assertEqual(summary["Requisições finalizadas"], 2)
        self.assertEqual(summary["Requisições não executadas"], 1)
        self.assertEqual(summary["Tempo médio até execução"], 15)
        self.assertEqual(summary["Orçamento finalizado"], Decimal("1000.00"))

        annual = {item["ano"]: item for item in analytics["annual_summary"]}
        self.assertEqual(annual[2025]["quantidade"], 1)
        self.assertEqual(annual[2025]["orcamento_total"], Decimal("1000.00"))
        self.assertEqual(annual[2025]["dias_execucao"], 10)
        self.assertEqual(annual[2026]["quantidade"], 1)
        self.assertEqual(annual[2026]["orcamento_total"], Decimal("0.00"))
        self.assertEqual(annual[2026]["dias_execucao"], 20)

        matrix_rows = {row["divisao"]: row for row in analytics["division_year_quantity_matrix"]["rows"]}
        self.assertEqual(matrix_rows["Construcao Civil"]["years"][2025], 1)
        self.assertEqual(matrix_rows["Instalacoes Eletricas"]["years"][2026], 1)

        pending = analytics["internal_triage"]["pending_operational"]
        self.assertEqual(pending["ativas_sem_prioridade"], 1)
        self.assertEqual(pending["finalizadas_sem_orcamento"], 1)
        self.assertEqual(pending["sem_responsavel_sinfra"], 1)
        self.assertEqual(len(analytics["internal_triage"]["oldest_active"]), 1)
        self.assertEqual(analytics["internal_triage"]["oldest_active"][0].codigo, self.public_active.codigo)

    def test_public_control_panel_page_is_public_and_hides_internal_section(self):
        response = self.client.get(reverse("public-control-panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vis&atilde;o executiva p&uacute;blica")
        self.assertNotContains(response, "Gest&atilde;o interna")
        self.assertEqual(response.context["filtered_total"], 5)
        summary = {item["label"]: item["value"] for item in response.context["summary_cards"]}
        self.assertEqual(summary["Orçamento finalizado"], Decimal("1000.00"))

    def test_operator_sees_internal_management_block(self):
        self.client.login(username="operador_dashboard", password="segredo")
        response = self.client.get(reverse("public-control-panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gest&atilde;o interna")
        self.assertIn("internal_triage", response.context)

    def test_director_sees_internal_management_block(self):
        self.client.login(username="diretor_dashboard", password="segredo")
        response = self.client.get(reverse("public-control-panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gest&atilde;o interna")
        self.assertIn("internal_triage", response.context)

    def test_admin_sees_internal_management_block(self):
        self.client.login(username="admin_dashboard", password="segredo")
        response = self.client.get(reverse("public-control-panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gest&atilde;o interna")
        self.assertIn("internal_triage", response.context)

    def test_control_panel_partial_applies_combined_filters_and_preserves_public_scope(self):
        response = self.client.get(
            reverse("public-control-panel-content"),
            {"macrostatus": "finalizada", "divisao": "Construcao Civil"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filtered_total"], 1)
        self.assertNotContains(response, "Gest&atilde;o interna")
        summary = {item["label"]: item["value"] for item in response.context["summary_cards"]}
        self.assertEqual(summary["Total de requisições"], 1)
        self.assertEqual(summary["Requisições finalizadas"], 1)
        self.assertEqual(summary["Orçamento finalizado"], Decimal("1000.00"))
