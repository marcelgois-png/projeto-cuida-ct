from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.tracker.models import Predio, Requisicao


User = get_user_model()


class SmartFiltersTests(TestCase):
    def setUp(self):
        self.predio_a = Predio.objects.create(nome="Bloco A")
        self.predio_b = Predio.objects.create(nome="Bloco B")

        self.operator = User.objects.create_user(
            username="smart_operator",
            password="segredo",
            role="operator",
            nome_completo="Operador Smart",
            telefone="83999990010",
        )
        self.director = User.objects.create_user(
            username="smart_director",
            password="segredo",
            role="director",
            nome_completo="Diretor Smart",
            telefone="83999990011",
        )

        self.civil_active = Requisicao.objects.create(
            codigo="201/2026",
            numero=201,
            ano=2026,
            assunto="Porta danificada",
            data_cadastro=date(2026, 3, 10),
            divisao="Construcao Civil",
            status_sipac="02 ENVIADA",
            tipo_servico="Esquadrias",
            servico="Porta de Madeira",
            predio=self.predio_a,
            nome_requisitante_snapshot="Maria",
            visivel_publicamente=True,
            status_processo_diretor=Requisicao.StatusProcessoDiretor.AGUARDANDO_DECISAO,
        )
        self.eletrica_active = Requisicao.objects.create(
            codigo="202/2026",
            numero=202,
            ano=2026,
            assunto="Disjuntor com defeito",
            data_cadastro=date(2026, 3, 11),
            divisao="Instalacoes Eletricas",
            status_sipac="04 OS EMITIDA",
            tipo_servico="Instalacao Eletrica",
            servico="Disjuntor",
            predio=self.predio_b,
            nome_requisitante_snapshot="Joao",
            visivel_publicamente=True,
            status_processo_diretor=Requisicao.StatusProcessoDiretor.AGUARDANDO_DECISAO,
        )
        self.civil_finalized = Requisicao.objects.create(
            codigo="203/2026",
            numero=203,
            ano=2026,
            assunto="Split instalado",
            data_cadastro=date(2026, 1, 10),
            data_execucao=date(2026, 1, 25),
            divisao="Construcao Civil",
            status_sipac="06 FINALIZADA",
            tipo_servico="Climatizacao",
            servico="Split",
            predio=self.predio_a,
            nome_requisitante_snapshot="Ana",
            orcamento_valor=Decimal("1200.00"),
            visivel_publicamente=True,
        )
        self.eletrica_finalized = Requisicao.objects.create(
            codigo="204/2026",
            numero=204,
            ano=2026,
            assunto="Tomada regularizada",
            data_cadastro=date(2026, 1, 12),
            data_execucao=date(2026, 1, 20),
            divisao="Instalacoes Eletricas",
            status_sipac="06 FINALIZADA",
            tipo_servico="Instalacao Eletrica",
            servico="Tomada",
            predio=self.predio_b,
            nome_requisitante_snapshot="Carlos",
            orcamento_valor=Decimal("300.00"),
            visivel_publicamente=True,
        )
        self.hidden_finalized = Requisicao.objects.create(
            codigo="205/2026",
            numero=205,
            ano=2026,
            assunto="Climatizacao oculta",
            data_cadastro=date(2026, 2, 1),
            data_execucao=date(2026, 2, 8),
            divisao="Maquinas e Equipamentos",
            status_sipac="06 FINALIZADA",
            tipo_servico="Climatizacao",
            servico="Janela",
            predio=self.predio_b,
            orcamento_valor=Decimal("900.00"),
            visivel_publicamente=False,
        )

    def test_priorizacao_panel_limits_tipo_and_servico_from_divisao(self):
        self.client.login(username="smart_operator", password="segredo")

        response = self.client.get(
            reverse("internal-priorizacao-panel"),
            {"divisao": "Construcao Civil"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filters"]["tipos_servico"], ["Esquadrias"])
        self.assertEqual(response.context["filters"]["servicos"], ["Porta de Madeira"])

    def test_priorizacao_panel_limits_divisao_and_servico_from_tipo_servico(self):
        self.client.login(username="smart_operator", password="segredo")

        response = self.client.get(
            reverse("internal-priorizacao-panel"),
            {"tipo_servico": "Instalacao Eletrica"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filters"]["divisoes"], ["Instalacoes Eletricas"])
        self.assertEqual(response.context["filters"]["servicos"], ["Disjuntor"])

    def test_decisoes_panel_uses_same_mutual_filter_logic(self):
        self.client.login(username="smart_director", password="segredo")

        response = self.client.get(
            reverse("internal-decisoes-panel"),
            {"servico": "Porta de Madeira"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filters"]["divisoes"], ["Construcao Civil"])
        self.assertEqual(response.context["filters"]["tipos_servico"], ["Esquadrias"])

    def test_orcamento_panel_limits_options_within_finalized_budget_scope(self):
        self.client.login(username="smart_operator", password="segredo")

        response = self.client.get(
            reverse("internal-orcamento-panel"),
            {"servico": "Split"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["orcamento_filters"]["divisoes"], ["Construcao Civil"])
        self.assertEqual(response.context["orcamento_filters"]["tipos_servico"], ["Climatizacao"])

    def test_public_control_panel_filters_respect_macrostatus_and_public_scope(self):
        response = self.client.get(
            reverse("public-control-panel-shell"),
            {"macrostatus": "finalizada"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filters"]["divisoes"], ["Construcao Civil", "Instalacoes Eletricas"])
        self.assertEqual(response.context["filters"]["tipos_servico"], ["Climatizacao", "Instalacao Eletrica"])
        self.assertEqual(
            [item["value"] for item in response.context["filters"]["statuses"]],
            ["06 FINALIZADA"],
        )
        self.assertNotIn("Maquinas e Equipamentos", response.context["filters"]["divisoes"])

    def test_public_control_panel_supports_extended_filters_and_year(self):
        response = self.client.get(
            reverse("public-control-panel-shell"),
            {
                "tipo_servico": "Esquadrias",
                "servico": "Porta de Madeira",
                "situacao_requisicao": "Ativa",
                "requisitante": "Maria",
                "ano": "2026",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filtered_total"], 1)
        self.assertIn("servicos", response.context["filters"])
        self.assertIn("situacoes", response.context["filters"])
        self.assertIn("requisitantes", response.context["filters"])
        self.assertIn("unidades_setor", response.context["filters"])
        self.assertIn("anos", response.context["filters"])
        self.assertEqual(response.context["filters"]["anos"], [2026])
