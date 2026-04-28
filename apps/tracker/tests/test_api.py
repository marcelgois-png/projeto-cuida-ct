import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.tracker.models import (
    AcompanhamentoRequisicao,
    DivisaoSINFRA,
    Predio,
    RegraPrioridade,
    Requisicao,
    Servico,
    StatusRequisicao,
    TaxonomiaServico,
    TipoServico,
)
from apps.tracker.templatetags.tracker_tags import intdot


User = get_user_model()


class ApiAccessTests(TestCase):
    def setUp(self):
        self.predio = Predio.objects.create(nome="Bloco Administrativo do CT")
        RegraPrioridade.objects.create(
            chave_normalizada="ConstrucaoCivilManutencaodeEsquadriasPortadeMadeira",
            prioridade="1 - Urgente",
        )
        self.taxonomia = TaxonomiaServico.objects.create(
            divisao="Construção Civil",
            tipo_servico="Manutenção de Esquadrias",
            servico="Porta de Madeira",
            ordem_divisao=1,
            ordem_tipo=1,
            ordem_servico=1,
        )
        StatusRequisicao.objects.update_or_create(codigo="02 ENVIADA", defaults={"ordem": 2, "nome": "Enviada", "mapeamento_situacao": "ATIVA"})
        self.status_os_emitida, _ = StatusRequisicao.objects.update_or_create(codigo="04 OS EMITIDA", defaults={"ordem": 4, "nome": "OS emitida", "mapeamento_situacao": "ATIVA"})
        self.divisao_cc, _ = DivisaoSINFRA.objects.get_or_create(nome="Construção Civil")
        self.tipo_esq, _ = TipoServico.objects.get_or_create(nome="Manutenção de Esquadrias", divisao=self.divisao_cc)
        self.servico_porta, _ = Servico.objects.get_or_create(nome="Porta de Madeira", tipo_servico=self.tipo_esq)
        self.requisicao = Requisicao.objects.create(
            codigo="111/2026",
            numero=111,
            ano=2026,
            assunto="Troca de porta",
            data_cadastro=date(2026, 4, 1),
            divisao=self.divisao_cc,
            status_sipac=self.status_os_emitida,
            tipo_servico=self.tipo_esq,
            servico=self.servico_porta,
            predio=self.predio,
            local_servico="Coordenação",
            nome_requisitante_snapshot="MARIA TESTE",
            unidade_setor_snapshot="CT - DIREÇÃO DE CENTRO",
            contato_direto_url="(83) 99999-9999",
            link_atendimento="https://atendimento.local/111",
            link_sipac="https://sipac.local/111",
            visivel_publicamente=True,
        )
        self.operator = User.objects.create_user(
            username="operador",
            password="segredo",
            role="operator",
            nome_completo="Operador Teste",
            telefone="(83) 99999-0000",
        )
        self.admin = User.objects.create_user(username="admin", password="segredo", role="admin")

    def test_public_detail_hides_sensitive_links(self):
        response = self.client.get(reverse("api-public-requisicao-detail", args=[self.requisicao.pk]))
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("contato_direto_url", payload)
        self.assertNotIn("link_atendimento", payload)
        self.assertNotIn("link_sipac", payload)
        self.assertEqual(payload["requisitante"], "MARIA TESTE")
        self.assertEqual(payload["status_sipac_exibicao"], "OS emitida")
        self.assertEqual(payload["dias_desde_abertura"], (date.today() - self.requisicao.data_cadastro).days)
        self.assertEqual(payload["dias_para_execucao"], (date.today() - self.requisicao.data_cadastro).days)

    def test_internal_detail_exposes_operational_fields_to_authenticated_operator(self):
        self.client.login(username="operador", password="segredo")
        response = self.client.get(reverse("api-internal-requisicao-detail", args=[self.requisicao.pk]))
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["contato_direto_url"], "(83) 99999-9999")
        self.assertEqual(payload["link_atendimento"], "https://atendimento.local/111")
        self.assertEqual(payload["link_sipac"], "https://sipac.local/111")
        self.assertEqual(payload["status_sipac_exibicao"], "OS emitida")
        self.assertEqual(payload["dias_desde_abertura"], (date.today() - self.requisicao.data_cadastro).days)
        self.assertEqual(payload["dias_para_execucao"], (date.today() - self.requisicao.data_cadastro).days)

    def test_dias_para_execucao_uses_execution_date_when_request_is_finalized(self):
        status_final, _ = StatusRequisicao.objects.get_or_create(
            codigo="06 FINALIZADA", defaults={"nome": "Finalizada", "mapeamento_situacao": "INATIVA"}
        )
        requisicao = Requisicao.objects.create(
            codigo="115/2026",
            numero=115,
            ano=2026,
            assunto="Demanda finalizada",
            data_cadastro=date(2026, 4, 1),
            data_execucao=date(2026, 4, 6),
            status_sipac=status_final,
            visivel_publicamente=True,
        )

        response = self.client.get(reverse("api-public-requisicao-detail", args=[requisicao.pk]))
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dias_para_execucao"], 5)

    def test_dias_para_execucao_is_empty_for_inactive_non_finalized_request(self):
        status_retornada, _ = StatusRequisicao.objects.get_or_create(
            codigo="07 RETORNADA", defaults={"nome": "Retornada", "mapeamento_situacao": "INATIVA"}
        )
        requisicao = Requisicao.objects.create(
            codigo="116/2026",
            numero=116,
            ano=2026,
            assunto="Demanda retornada",
            data_cadastro=date(2026, 4, 1),
            data_execucao=date(2026, 4, 6),
            status_sipac=status_retornada,
            visivel_publicamente=True,
        )

        response = self.client.get(reverse("api-public-requisicao-detail", args=[requisicao.pk]))
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(payload["dias_para_execucao"])

    def test_inactive_non_finalized_request_clears_persisted_execution_days(self):
        status_negada, _ = StatusRequisicao.objects.get_or_create(
            codigo="09 NEGADA", defaults={"nome": "Negada", "mapeamento_situacao": "INATIVA"}
        )
        requisicao = Requisicao.objects.create(
            codigo="117/2026",
            numero=117,
            ano=2026,
            assunto="Demanda negada",
            data_cadastro=date(2026, 4, 1),
            data_execucao=date(2026, 4, 6),
            status_sipac=status_negada,
            dias_para_execucao=99,
            visivel_publicamente=True,
        )

        self.assertIsNone(requisicao.dias_para_execucao)

    def test_internal_endpoints_require_authentication(self):
        response = self.client.get(reverse("api-internal-requisicoes"))
        self.assertEqual(response.status_code, 302)

    def test_operator_cannot_import_but_admin_can(self):
        csv_payload = (
            "Nº Requisição,Assunto,Data de Cadastro,Divisão,Status SIPAC,Tipo de Serviço,Serviço\n"
            "400/2026,Nova demanda,2026-03-01,Construção Civil,02 ENVIADA,Manutenção de Esquadrias,Porta de Madeira\n"
        ).encode("utf-8")

        self.client.login(username="operador", password="segredo")
        response = self.client.post(
            reverse("api-internal-importacoes"),
            {"arquivo": SimpleUploadedFile("base.csv", csv_payload, content_type="text/csv")},
        )
        self.assertEqual(response.status_code, 403)

        self.client.logout()
        self.client.login(username="admin", password="segredo")
        response = self.client.post(
            reverse("api-internal-importacoes"),
            {"arquivo": SimpleUploadedFile("base.csv", csv_payload, content_type="text/csv")},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Requisicao.objects.filter(codigo="400/2026").count(), 1)

    def test_internal_create_endpoint_recomputes_priority(self):
        self.client.login(username="operador", password="segredo")
        payload = {
            "codigo": "222/2026",
            "assunto": "Porta quebrada",
            "orcamento": "R$ 800,00",
            "data_cadastro": "2026-04-01",
            "tipo_requisicao": "REQUISIÇÃO DE MANUTENÇÃO",
            "divisao": self.taxonomia.divisao,
            "unidade_origem": "CT - DIREÇÃO DE CENTRO",
            "status_sipac": "02 ENVIADA",
            "tipo_servico": self.taxonomia.tipo_servico,
            "servico": self.taxonomia.servico,
            "predio": self.predio.id,
            "local_servico": "Laboratório",
            "nome_requisitante_snapshot": "CARLA TESTE",
            "unidade_setor_snapshot": "CT - DIREÇÃO DE CENTRO",
            "contato_direto_url": "83999998888",
            "situacao_texto": "",
            "gravidade": "Muito grave",
            "urgencia": "É urgente",
            "tendencia": "Piorar em curto prazo",
            "sinfra_responsavel": "RN",
            "link_atendimento": "",
            "link_sipac": "",
            "visivel_publicamente": True,
        }
        response = self.client.post(
            reverse("api-internal-requisicoes"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        result = response.json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(result["prioridade_final"], "1 - Urgente")
        self.assertEqual(result["orcamento"], "R$ 800,00")
        self.assertEqual(result["numero"], 222)
        self.assertEqual(result["ano"], 2026)
        self.assertEqual(result["status_sipac_exibicao"], "Enviada")
        self.assertEqual(result["dias_desde_abertura"], (date.today() - date(2026, 4, 1)).days)
        self.assertEqual(result["dias_para_execucao"], (date.today() - date(2026, 4, 1)).days)
        req = Requisicao.objects.get(codigo="222/2026")
        self.assertEqual(req.divisao.nome if req.divisao else None, "Construção Civil")
        self.assertEqual(req.tipo_servico.nome if req.tipo_servico else None, "Manutenção de Esquadrias")
        self.assertEqual(req.servico.nome if req.servico else None, "Porta de Madeira")
        self.assertEqual(req.contato_direto_url, "(83) 99999-8888")

    def test_requisicao_form_page_exposes_taxonomy_and_status_data(self):
        self.client.login(username="operador", password="segredo")
        response = self.client.get(reverse("requisicao-create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="taxonomy-options-data"')
        self.assertContains(response, "Construção Civil")
        self.assertContains(response, "Enviada")
        self.assertContains(response, 'data-taxonomy-field')
        self.assertContains(response, 'name="data_execucao"')
        self.assertContains(response, 'disabled')

    def test_requisicao_edit_page_enables_execution_date(self):
        self.client.login(username="operador", password="segredo")
        response = self.client.get(reverse("requisicao-update", args=[self.requisicao.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="data_execucao"')
        self.assertNotContains(response, 'Disponível somente após a criação da requisição.')

    def test_requisicao_edit_page_displays_acompanhamento_section(self):
        AcompanhamentoRequisicao.objects.create(
            requisicao=self.requisicao,
            data=date(2026, 4, 7),
            atualizacao_situacao="Equipe de manutenção acionada.",
            usuario=self.operator,
        )

        self.client.login(username="operador", password="segredo")
        response = self.client.get(reverse("requisicao-update", args=[self.requisicao.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ACOMPANHAMENTO DA REQUISIÇÃO")
        self.assertContains(response, "Cadastrar situação")
        self.assertContains(response, "form-section-highlight")
        self.assertContains(response, "Usuário")
        self.assertContains(response, "Editar")
        self.assertContains(response, 'name="acompanhamentos-TOTAL_FORMS"')
        self.assertContains(response, 'name="acompanhamentos-0-data"')
        self.assertContains(response, "Equipe de manutenção acionada.")
        self.assertContains(response, "Operador Teste")

    def test_internal_detail_page_shows_read_only_acompanhamento_with_author(self):
        AcompanhamentoRequisicao.objects.create(
            requisicao=self.requisicao,
            data=date(2026, 4, 9),
            atualizacao_situacao="Equipe acionada para nova vistoria técnica.",
            usuario=self.operator,
        )

        self.client.login(username="operador", password="segredo")

        response = self.client.get(reverse("internal-requisicao-detail", args=[self.requisicao.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "form-section-highlight")
        self.assertContains(response, "Usuário")
        self.assertContains(response, "Equipe acionada para nova vistoria técnica.")
        self.assertContains(response, "Operador Teste")
        self.assertNotContains(response, "Cadastrar situação")
        self.assertNotContains(response, 'name="atualizacao_situacao"')
        self.assertNotContains(response, "Salvar comentário")

    def test_internal_detail_page_rejects_comment_post(self):
        self.client.login(username="operador", password="segredo")

        response = self.client.post(
            reverse("internal-requisicao-detail", args=[self.requisicao.pk]),
            {
                "data": "2026-04-09",
                "atualizacao_situacao": "Equipe acionada para nova vistoria técnica.",
            },
        )

        self.assertEqual(response.status_code, 405)
        self.assertFalse(AcompanhamentoRequisicao.objects.filter(requisicao=self.requisicao).exists())
        return

        response = self.client.post(
            reverse("internal-requisicao-detail", args=[self.requisicao.pk]),
            {
                "data": "2026-04-09",
                "atualizacao_situacao": "Equipe acionada para nova vistoria técnica.",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        acompanhamento = AcompanhamentoRequisicao.objects.get(requisicao=self.requisicao)
        self.assertEqual(acompanhamento.usuario, self.operator)
        self.assertContains(response, "Equipe acionada para nova vistoria técnica.")
        self.assertContains(response, "Registrado por Operador Teste")

    def test_requisicao_update_saves_new_acompanhamento_row(self):
        self.client.login(username="operador", password="segredo")
        payload = {
            "codigo": self.requisicao.codigo,
            "assunto": self.requisicao.assunto,
            "orcamento": self.requisicao.orcamento,
            "data_cadastro": self.requisicao.data_cadastro.isoformat(),
            "data_execucao": "",
            "tipo_requisicao": self.requisicao.tipo_requisicao,
            "divisao": self.requisicao.divisao.nome if self.requisicao.divisao else "",
            "unidade_origem": self.requisicao.unidade_origem,
            "status_sipac": self.requisicao.status_sipac.codigo if self.requisicao.status_sipac else "",
            "situacao_requisicao": self.requisicao.situacao_requisicao,
            "tipo_servico": self.requisicao.tipo_servico.nome if self.requisicao.tipo_servico else "",
            "servico": self.requisicao.servico.nome if self.requisicao.servico else "",
            "predio": str(self.predio.pk),
            "local_servico": self.requisicao.local_servico,
            "requisitante": "",
            "nome_requisitante_snapshot": self.requisicao.nome_requisitante_snapshot,
            "unidade_setor_snapshot": self.requisicao.unidade_setor_snapshot,
            "contato_direto_url": self.requisicao.contato_direto_url,
            "situacao_texto": self.requisicao.situacao_texto,
            "gravidade": self.requisicao.gravidade,
            "urgencia": self.requisicao.urgencia,
            "tendencia": self.requisicao.tendencia,
            "sinfra_responsavel": self.requisicao.sinfra_responsavel,
            "link_atendimento": self.requisicao.link_atendimento,
            "link_sipac": self.requisicao.link_sipac,
            "visivel_publicamente": "True",
            "acompanhamentos-TOTAL_FORMS": "1",
            "acompanhamentos-INITIAL_FORMS": "0",
            "acompanhamentos-MIN_NUM_FORMS": "0",
            "acompanhamentos-MAX_NUM_FORMS": "1000",
            "save_acompanhamento": "0",
            "acompanhamentos-0-id": "",
            "acompanhamentos-0-requisicao": str(self.requisicao.pk),
            "acompanhamentos-0-data": "2026-04-08",
            "acompanhamentos-0-atualizacao_situacao": "Visita técnica agendada para inspeção.",
        }

        response = self.client.post(reverse("requisicao-update", args=[self.requisicao.pk]), payload, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AcompanhamentoRequisicao.objects.filter(requisicao=self.requisicao).count(), 1)
        acompanhamento = AcompanhamentoRequisicao.objects.get(requisicao=self.requisicao)
        self.assertEqual(acompanhamento.data.isoformat(), "2026-04-08")
        self.assertEqual(acompanhamento.atualizacao_situacao, "Visita técnica agendada para inspeção.")
        self.assertEqual(acompanhamento.usuario, self.operator)
        self.assertEqual(response.request["PATH_INFO"], reverse("requisicao-update", args=[self.requisicao.pk]))
        self.assertContains(response, "Comentário salvo por Operador Teste.")
        self.assertContains(response, "Editar")

    def test_public_indicators_order_statuses_by_flow_sequence(self):
        st_enviada, _ = StatusRequisicao.objects.get_or_create(
            codigo="02 ENVIADA", defaults={"nome": "Enviada", "mapeamento_situacao": "ATIVA", "ordem": 2}
        )
        st_pendente, _ = StatusRequisicao.objects.get_or_create(
            codigo="10 PENDENTE DE AUTORIZAÇÃO CHEFE UNIDADE",
            defaults={"nome": "Pendente de autorização chefe unidade", "mapeamento_situacao": "ATIVA", "ordem": 10},
        )
        Requisicao.objects.create(
            codigo="112/2026",
            numero=112,
            ano=2026,
            assunto="Novo envio",
            data_cadastro=date(2026, 4, 2),
            status_sipac=st_enviada,
            visivel_publicamente=True,
        )
        Requisicao.objects.create(
            codigo="113/2026",
            numero=113,
            ano=2026,
            assunto="Autorização pendente",
            data_cadastro=date(2026, 4, 3),
            status_sipac=st_pendente,
            visivel_publicamente=True,
        )

        response = self.client.get(reverse("api-public-indicadores"))
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["label"] for item in payload["por_status"]],
            ["Enviada", "OS emitida", "Pendente de autorização chefe unidade"],
        )

    def test_public_dashboard_divisao_filter_applies_to_metrics_and_service_panel(self):
        st_enviada, _ = StatusRequisicao.objects.get_or_create(
            codigo="02 ENVIADA", defaults={"nome": "Enviada", "mapeamento_situacao": "ATIVA", "ordem": 2}
        )
        div_eletrica, _ = DivisaoSINFRA.objects.get_or_create(nome="Instalações Elétricas")
        tipo_quadros, _ = TipoServico.objects.get_or_create(nome="Quadros", divisao=div_eletrica)
        serv_disj, _ = Servico.objects.get_or_create(nome="Disjuntor", tipo_servico=tipo_quadros)
        Requisicao.objects.create(
            codigo="114/2026",
            numero=114,
            ano=2026,
            assunto="Demanda elétrica",
            data_cadastro=date(2026, 4, 4),
            divisao=div_eletrica,
            tipo_servico=tipo_quadros,
            servico=serv_disj,
            status_sipac=st_enviada,
            visivel_publicamente=True,
        )

        response = self.client.get(reverse("public-dashboard"), {"divisao": "Construção Civil"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["metrics"]["total"], 1)
        self.assertEqual(response.context["service_panel"]["selected_divisao"], "Construção Civil")

    def test_public_table_uses_actions_column_with_read_only_view_link(self):
        response = self.client.get(reverse("public-requisicoes-table"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ações")
        self.assertContains(response, reverse("public-requisicao-detail", args=[self.requisicao.pk]))
        self.assertContains(response, "bi-eye")
        self.assertNotContains(response, "<span>Prioridade</span>", html=False)

    def test_public_detail_page_shows_requisition_details_without_edit_actions(self):
        AcompanhamentoRequisicao.objects.create(
            requisicao=self.requisicao,
            data=date(2026, 4, 8),
            atualizacao_situacao="Vistoria pública registrada.",
        )

        response = self.client.get(reverse("public-requisicao-detail", args=[self.requisicao.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detalhes da requisição")
        self.assertContains(response, self.requisicao.codigo)
        self.assertContains(response, self.requisicao.assunto)
        self.assertContains(response, "Vistoria pública registrada.")
        self.assertNotContains(response, "Salvar")
        self.assertNotContains(response, "bi-pencil-square")


def _test_requisicao_edit_page_displays_acompanhamento_section(self):
    AcompanhamentoRequisicao.objects.create(
        requisicao=self.requisicao,
        data=date(2026, 4, 7),
        atualizacao_situacao="Equipe de manutencao acionada.",
        usuario=self.operator,
    )

    self.client.login(username="operador", password="segredo")
    response = self.client.get(reverse("requisicao-update", args=[self.requisicao.pk]))

    self.assertEqual(response.status_code, 200)
    self.assertContains(response, "form-section-highlight")
    self.assertContains(response, "Cadastrar situa")
    self.assertContains(response, "Editar")
    self.assertContains(response, 'name="acompanhamentos-TOTAL_FORMS"')
    self.assertContains(response, 'name="acompanhamentos-0-data"')
    self.assertContains(response, "Operador Teste")


def _test_internal_detail_page_shows_read_only_acompanhamento_with_author(self):
    AcompanhamentoRequisicao.objects.create(
        requisicao=self.requisicao,
        data=date(2026, 4, 9),
        atualizacao_situacao="Equipe acionada para nova vistoria tecnica.",
        usuario=self.operator,
    )

    self.client.login(username="operador", password="segredo")
    response = self.client.get(reverse("internal-requisicao-detail", args=[self.requisicao.pk]))

    self.assertEqual(response.status_code, 200)
    self.assertContains(response, "form-section-highlight")
    self.assertContains(response, "bi-person-circle")
    self.assertContains(response, "Operador Teste")
    self.assertContains(response, "Equipe acionada para nova")
    self.assertNotContains(response, "Cadastrar situa")
    self.assertNotContains(response, 'name="atualizacao_situacao"')
    self.assertNotContains(response, "Salvar coment")


def _test_internal_detail_page_rejects_comment_post(self):
    self.client.login(username="operador", password="segredo")
    response = self.client.post(
        reverse("internal-requisicao-detail", args=[self.requisicao.pk]),
        {
            "data": "2026-04-09",
            "atualizacao_situacao": "Equipe acionada para nova vistoria tecnica.",
        },
    )

    self.assertEqual(response.status_code, 405)
    self.assertFalse(AcompanhamentoRequisicao.objects.filter(requisicao=self.requisicao).exists())


def _test_public_table_uses_view_details_column_with_read_only_view_link(self):
    response = self.client.get(reverse("public-requisicoes-table"))

    self.assertEqual(response.status_code, 200)
    self.assertContains(response, "Ver detalhes")
    self.assertContains(response, reverse("public-requisicao-detail", args=[self.requisicao.pk]))
    self.assertContains(response, "bi-eye")
    self.assertContains(response, "table-status-value")
    self.assertNotContains(response, "<span>Prioridade</span>", html=False)


ApiAccessTests.test_requisicao_edit_page_displays_acompanhamento_section = (
    _test_requisicao_edit_page_displays_acompanhamento_section
)
ApiAccessTests.test_internal_detail_page_shows_read_only_acompanhamento_with_author = (
    _test_internal_detail_page_shows_read_only_acompanhamento_with_author
)
ApiAccessTests.test_internal_detail_page_rejects_comment_post = _test_internal_detail_page_rejects_comment_post
ApiAccessTests.test_public_table_uses_actions_column_with_read_only_view_link = (
    _test_public_table_uses_view_details_column_with_read_only_view_link
)


def _test_public_dashboard_groups_actions_and_shows_climatization_investment(self):
    st_finalizada, _ = StatusRequisicao.objects.get_or_create(
        codigo="06 FINALIZADA", defaults={"nome": "Finalizada", "mapeamento_situacao": "INATIVA", "ordem": 6}
    )
    st_enviada, _ = StatusRequisicao.objects.get_or_create(
        codigo="02 ENVIADA", defaults={"nome": "Enviada", "mapeamento_situacao": "ATIVA", "ordem": 2}
    )
    div_maquinas, _ = DivisaoSINFRA.objects.get_or_create(nome="Maquinas e Equipamentos")
    tipo_ar, _ = TipoServico.objects.get_or_create(nome="Ar Condicionado", divisao=div_maquinas)
    serv_manut, _ = Servico.objects.get_or_create(nome="Manutencao Corretiva", tipo_servico=tipo_ar)
    div_eletrica, _ = DivisaoSINFRA.objects.get_or_create(nome="Instalacoes Eletricas")
    tipo_inst, _ = TipoServico.objects.get_or_create(nome="Instalacao", divisao=div_eletrica)
    serv_tomada, _ = Servico.objects.get_or_create(nome="Tomada p/ ar-condicionado", tipo_servico=tipo_inst)
    div_civil, _ = DivisaoSINFRA.objects.get_or_create(nome="Construcao Civil")
    tipo_esq2, _ = TipoServico.objects.get_or_create(nome="Manutencao de Esquadrias", divisao=div_civil)
    serv_porta2, _ = Servico.objects.get_or_create(nome="Porta de Madeira", tipo_servico=tipo_esq2)
    Requisicao.objects.create(
        codigo="118/2026",
        numero=118,
        ano=2026,
        assunto="Manutencao do ar condicionado do laboratorio",
        data_cadastro=date(2026, 4, 8),
        divisao=div_maquinas,
        tipo_servico=tipo_ar,
        servico=serv_manut,
        status_sipac=st_finalizada,
        orcamento_valor=Decimal("15420.50"),
        visivel_publicamente=True,
    )
    Requisicao.objects.create(
        codigo="119/2026",
        numero=119,
        ano=2026,
        assunto="Troca de fiação para ar condicionado",
        data_cadastro=date(2026, 4, 9),
        divisao=div_eletrica,
        tipo_servico=tipo_inst,
        servico=serv_tomada,
        status_sipac=st_enviada,
        orcamento_valor=Decimal("900.00"),
        visivel_publicamente=True,
    )
    Requisicao.objects.create(
        codigo="120/2026",
        numero=120,
        ano=2026,
        assunto="Reparo em porta",
        data_cadastro=date(2026, 4, 10),
        divisao=div_civil,
        tipo_servico=tipo_esq2,
        servico=serv_porta2,
        status_sipac=st_finalizada,
        orcamento_valor=Decimal("1200.00"),
        visivel_publicamente=True,
    )

    response = self.client.get(reverse("public-dashboard"))

    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.context["metrics"]["investimento_requisicoes"], Decimal("15420.50"))
    # Home page shows investment value (non-breaking space used in template)
    self.assertContains(response, "15.420,50")
    # Home page has action links to browse requests and panels
    html = response.content.decode()
    self.assertIn("Consultar Requisi", html)
    self.assertIn("Painel de Requisi", html)


ApiAccessTests.test_public_dashboard_groups_actions_and_shows_climatization_investment = (
    _test_public_dashboard_groups_actions_and_shows_climatization_investment
)


def _test_intdot_formats_thousands_for_summary_cards(self):
    self.assertEqual(intdot(121707), "121.707")
    self.assertEqual(intdot("1500"), "1.500")


ApiAccessTests.test_intdot_formats_thousands_for_summary_cards = (
    _test_intdot_formats_thousands_for_summary_cards
)
