from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.tracker.models import AcompanhamentoRequisicao, EncaminhamentoDiretor, Requisicao


User = get_user_model()


class InternalDecisoesFlowTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_user(
            username="diretor_ct",
            password="segredo",
            role="director",
        )
        self.client.login(username="diretor_ct", password="segredo")

        self.requisicao_1 = Requisicao.objects.create(
            codigo="401/2026",
            numero=401,
            ano=2026,
            assunto="Adequacao eletrica",
            data_cadastro=date(2026, 4, 3),
            status_sipac="02 ENVIADA",
            local_servico="Bloco A",
            nome_requisitante_snapshot="MARIA TESTE",
            status_processo_diretor=Requisicao.StatusProcessoDiretor.AGUARDANDO_DECISAO,
        )
        self.requisicao_2 = Requisicao.objects.create(
            codigo="402/2026",
            numero=402,
            ano=2026,
            assunto="Revisao estrutural",
            data_cadastro=date(2026, 4, 4),
            status_sipac="04 OS EMITIDA",
            local_servico="Bloco B",
            nome_requisitante_snapshot="JOSE TESTE",
            status_processo_diretor=Requisicao.StatusProcessoDiretor.AGUARDANDO_DECISAO,
        )

    def test_preview_modal_shows_selected_requests_and_guidance_field(self):
        response = self.client.post(
            reverse("decisoes-encaminhamento-preview"),
            {
                "requisicao_ids": [self.requisicao_1.pk, self.requisicao_2.pk],
                "decisao": "autorizado",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Orientações ao Operador")
        self.assertContains(response, "Abrir processo")
        self.assertContains(response, self.requisicao_1.codigo)
        self.assertContains(response, self.requisicao_2.codigo)

    def test_submit_creates_encaminhamento_and_updates_requests(self):
        response = self.client.post(
            reverse("decisoes-bulk-decide"),
            {
                "requisicao_ids": [self.requisicao_1.pk, self.requisicao_2.pk],
                "decisao": "autorizado",
                "orientacoes": "Abrir processo administrativo e orientar o operador a reunir a documentacao.",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["HX-Refresh"], "true")

        encaminhamento = EncaminhamentoDiretor.objects.get()
        self.assertEqual(encaminhamento.numero, 1)
        self.assertEqual(encaminhamento.tipo, EncaminhamentoDiretor.Tipo.ABRIR_PROCESSO)
        self.assertEqual(encaminhamento.requisicoes.count(), 2)

        self.requisicao_1.refresh_from_db()
        self.requisicao_2.refresh_from_db()
        self.assertEqual(
            self.requisicao_1.status_processo_diretor,
            Requisicao.StatusProcessoDiretor.AUTORIZADO,
        )
        self.assertEqual(
            self.requisicao_2.status_processo_diretor,
            Requisicao.StatusProcessoDiretor.AUTORIZADO,
        )
        self.assertTrue(
            AcompanhamentoRequisicao.objects.filter(
                requisicao=self.requisicao_1,
                atualizacao_situacao__icontains="Encaminhamento do diretor #1",
            ).exists()
        )

    def test_encaminhamentos_page_lists_saved_blocks(self):
        encaminhamento = EncaminhamentoDiretor.objects.create(
            tipo=EncaminhamentoDiretor.Tipo.ENCERRAR_REQUISICAO,
            orientacoes="Encerrar a requisicao e comunicar o requisitante.",
            diretor=self.director,
        )
        encaminhamento.requisicoes.add(self.requisicao_1)

        response = self.client.get(reverse("internal-encaminhamentos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Encaminhamento #001")
        self.assertContains(response, "Encerrar requisicao")
        self.assertContains(response, self.requisicao_1.codigo)
        self.assertContains(response, "Encerrar a requisicao e comunicar o requisitante.")

    def test_director_can_view_internal_request_without_edit_button(self):
        response = self.client.get(reverse("internal-requisicao-detail", args=[self.requisicao_1.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.requisicao_1.codigo)
        self.assertNotContains(response, ">Editar<", html=False)
        self.assertNotContains(response, "Cadastrar situação")

    def test_cancel_encaminhamento_returns_requests_to_decision_queue(self):
        encaminhamento = EncaminhamentoDiretor.objects.create(
            tipo=EncaminhamentoDiretor.Tipo.ABRIR_PROCESSO,
            orientacoes="Abrir processo com urgencia.",
            diretor=self.director,
        )
        encaminhamento.requisicoes.add(self.requisicao_1, self.requisicao_2)
        Requisicao.objects.filter(pk__in=[self.requisicao_1.pk, self.requisicao_2.pk]).update(
            status_processo_diretor=Requisicao.StatusProcessoDiretor.AUTORIZADO,
            observacao_diretor="Abrir processo com urgencia.",
        )

        response = self.client.post(reverse("internal-cancel-encaminhamento", args=[encaminhamento.pk]))

        self.assertRedirects(response, reverse("internal-encaminhamentos"))
        self.assertFalse(EncaminhamentoDiretor.objects.filter(pk=encaminhamento.pk).exists())
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
        self.assertEqual(self.requisicao_1.observacao_diretor, "")
        self.assertTrue(
            AcompanhamentoRequisicao.objects.filter(
                requisicao=self.requisicao_1,
                atualizacao_situacao__icontains="cancelado",
            ).exists()
        )
