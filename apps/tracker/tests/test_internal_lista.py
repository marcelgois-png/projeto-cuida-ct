from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.tracker.models import AcompanhamentoRequisicao, Requisicao, StatusRequisicao


User = get_user_model()


class InternalListaBulkDecisionTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            username="operador_lista",
            password="segredo",
            role="operator",
        )
        self.client.login(username="operador_lista", password="segredo")

        st_enviada, _ = StatusRequisicao.objects.get_or_create(
            codigo="02 ENVIADA", defaults={"nome": "Enviada", "mapeamento_situacao": "ATIVA", "ordem": 2}
        )
        st_os_emitida, _ = StatusRequisicao.objects.get_or_create(
            codigo="04 OS EMITIDA", defaults={"nome": "OS emitida", "mapeamento_situacao": "ATIVA", "ordem": 4}
        )

        self.requisicao_1 = Requisicao.objects.create(
            codigo="301/2026",
            numero=301,
            ano=2026,
            assunto="Troca de luminária",
            data_cadastro=date(2026, 4, 1),
            status_sipac=st_enviada,
            local_servico="Biblioteca",
            nome_requisitante_snapshot="CARLA TESTE",
        )
        self.requisicao_2 = Requisicao.objects.create(
            codigo="302/2026",
            numero=302,
            ano=2026,
            assunto="Reparo hidráulico",
            data_cadastro=date(2026, 4, 2),
            status_sipac=st_os_emitida,
            local_servico="Laboratório",
            nome_requisitante_snapshot="JOÃO TESTE",
        )

        AcompanhamentoRequisicao.objects.create(
            requisicao=self.requisicao_1,
            data=date(2026, 4, 8),
            atualizacao_situacao="Vistoria inicial concluída.",
        )

    def test_internal_list_page_keeps_only_top_direction_button(self):
        response = self.client.get(reverse("internal-lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enc. para Direção")
        self.assertNotContains(response, "bi-briefcase")

    def test_bulk_decisions_preview_shows_selected_requests_and_follow_up_section(self):
        response = self.client.post(
            reverse("lista-bulk-decisions-preview"),
            {"requisicao_ids": [self.requisicao_1.pk, self.requisicao_2.pk]},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ACOMPANHAMENTO DA REQUISIÇÃO")
        self.assertContains(response, "Registre observações sucessivas sobre a evolução do atendimento.")
        self.assertContains(response, self.requisicao_1.codigo)
        self.assertContains(response, "Vistoria inicial concluída.")
        self.assertContains(response, f'name="acompanhamento_{self.requisicao_1.pk}"', html=False)

    def test_bulk_decisions_submit_updates_status_and_creates_follow_up(self):
        response = self.client.post(
            reverse("lista-bulk-decisions"),
            {
                "requisicao_ids": [self.requisicao_1.pk, self.requisicao_2.pk],
                f"acompanhamento_{self.requisicao_1.pk}": "Necessita validação da Direção por impacto orçamentário.",
                f"acompanhamento_{self.requisicao_2.pk}": "Encaminhada por envolver definição institucional.",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["HX-Refresh"], "true")

        self.requisicao_1.refresh_from_db()
        self.requisicao_2.refresh_from_db()
        self.assertEqual(
            self.requisicao_1.status_processo_diretor,
            Requisicao.StatusProcessoDiretor.AGUARDANDO_DECISAO,
        )
        self.assertEqual(
            self.requisicao_2.status_processo_diretor,
            Requisicao.StatusProcessoDiretor.AGUARDANDO_DECISAO,
        )
        self.assertTrue(
            AcompanhamentoRequisicao.objects.filter(
                requisicao=self.requisicao_1,
                atualizacao_situacao__icontains="impacto orçamentário",
            ).exists()
        )
        self.assertTrue(
            AcompanhamentoRequisicao.objects.filter(
                requisicao=self.requisicao_2,
                atualizacao_situacao__icontains="definição institucional",
            ).exists()
        )

    def test_bulk_decisions_submit_requires_justification_for_each_request(self):
        response = self.client.post(
            reverse("lista-bulk-decisions"),
            {
                "requisicao_ids": [self.requisicao_1.pk, self.requisicao_2.pk],
                f"acompanhamento_{self.requisicao_1.pk}": "",
                f"acompanhamento_{self.requisicao_2.pk}": "Texto preenchido.",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Explique o motivo do encaminhamento para todas as requisições selecionadas.",
        )
        self.assertContains(response, "is-invalid")
        self.requisicao_1.refresh_from_db()
        self.assertEqual(
            self.requisicao_1.status_processo_diretor,
            Requisicao.StatusProcessoDiretor.NAO_INDICADO,
        )
