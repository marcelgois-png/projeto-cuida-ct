from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.tracker.models import NotaEmpenho, ReforcoEmpenho, Requisicao


User = get_user_model()


class InternalBudgetPanelTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            username="operador_orcamento",
            password="segredo",
            role="operator",
        )
        self.nota = NotaEmpenho.objects.create(
            nota_empenho="2026NE0001",
            valor=Decimal("1000.00"),
        )

    def test_total_balance_only_subtracts_finalized_request_budgets_linked_to_note(self):
        Requisicao.objects.create(
            codigo="118/2026",
            numero=118,
            ano=2026,
            assunto="Demanda finalizada com custo",
            data_cadastro=date(2026, 4, 5),
            situacao_requisicao="Inativa",
            status_sipac="06 FINALIZADA",
            orcamento_valor=Decimal("250.00"),
            nota_empenho=self.nota,
        )
        Requisicao.objects.create(
            codigo="119/2026",
            numero=119,
            ano=2026,
            assunto="Demanda finalizada sem vínculo",
            data_cadastro=date(2026, 4, 6),
            situacao_requisicao="Inativa",
            status_sipac="06 FINALIZADA",
            orcamento_valor=Decimal("300.00"),
        )

        self.client.login(username="operador_orcamento", password="segredo")
        response = self.client.get(reverse("internal-orcamento"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["valor_total"], Decimal("1000.00"))
        self.assertEqual(response.context["saldo_total"], Decimal("750.00"))
        self.assertEqual(response.context["total_reqs_pagas"], 2)

    def test_budget_page_can_update_note_link_for_finalized_request(self):
        requisicao = Requisicao.objects.create(
            codigo="120/2026",
            numero=120,
            ano=2026,
            assunto="Demanda aguardando vínculo",
            data_cadastro=date(2026, 4, 7),
            situacao_requisicao="Inativa",
            status_sipac="06 FINALIZADA",
            orcamento_valor=Decimal("400.00"),
        )

        self.client.login(username="operador_orcamento", password="segredo")
        response = self.client.post(
            reverse("requisicao-orcamento-nota-update", args=[requisicao.pk]),
            {"nota_empenho_id": str(self.nota.pk)},
        )

        requisicao.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(requisicao.nota_empenho, self.nota)

    def test_budget_page_can_update_note_link_in_bulk_for_selected_requests(self):
        primeira = Requisicao.objects.create(
            codigo="121/2026",
            numero=121,
            ano=2026,
            assunto="Primeira em lote",
            data_cadastro=date(2026, 4, 8),
            situacao_requisicao="Inativa",
            status_sipac="06 FINALIZADA",
            orcamento_valor=Decimal("150.00"),
        )
        segunda = Requisicao.objects.create(
            codigo="122/2026",
            numero=122,
            ano=2026,
            assunto="Segunda em lote",
            data_cadastro=date(2026, 4, 9),
            situacao_requisicao="Inativa",
            status_sipac="06 FINALIZADA",
            orcamento_valor=Decimal("175.00"),
        )

        self.client.login(username="operador_orcamento", password="segredo")
        response = self.client.post(
            reverse("requisicoes-orcamento-nota-bulk-update"),
            {"nota_empenho_id": str(self.nota.pk), "requisicao_ids": [str(primeira.pk), str(segunda.pk)]},
        )

        primeira.refresh_from_db()
        segunda.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(primeira.nota_empenho, self.nota)
        self.assertEqual(segunda.nota_empenho, self.nota)

    def test_budget_page_can_unlink_note_in_bulk_for_selected_requests(self):
        primeira = Requisicao.objects.create(
            codigo="121A/2026",
            numero=221,
            ano=2026,
            assunto="Primeira desvinculação em lote",
            data_cadastro=date(2026, 4, 8),
            situacao_requisicao="Inativa",
            status_sipac="06 FINALIZADA",
            orcamento_valor=Decimal("150.00"),
            nota_empenho=self.nota,
        )
        segunda = Requisicao.objects.create(
            codigo="122A/2026",
            numero=222,
            ano=2026,
            assunto="Segunda desvinculação em lote",
            data_cadastro=date(2026, 4, 9),
            situacao_requisicao="Inativa",
            status_sipac="06 FINALIZADA",
            orcamento_valor=Decimal("175.00"),
            nota_empenho=self.nota,
        )

        self.client.login(username="operador_orcamento", password="segredo")
        response = self.client.post(
            reverse("requisicoes-orcamento-nota-bulk-update"),
            {"bulk_action": "unlink", "requisicao_ids": [str(primeira.pk), str(segunda.pk)]},
        )

        primeira.refresh_from_db()
        segunda.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(primeira.nota_empenho)
        self.assertIsNone(segunda.nota_empenho)

    def test_budget_page_details_base_and_reforco_values_in_note_table(self):
        reforco = ReforcoEmpenho.objects.create(
            empenho=self.nota,
            valor=Decimal("250.00"),
            numero_processo_sipac="23074.012345/2026-10",
            descricao="Complemento para ampliação do escopo",
        )

        self.client.login(username="operador_orcamento", password="segredo")
        response = self.client.get(reverse("internal-orcamento"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Valor Inicial")
        self.assertContains(response, "R$ 1.250,00")
        self.assertContains(response, "R$ 1.000,00")
        self.assertContains(response, "+ Reforço 1")
        self.assertContains(response, "+ R$ 250,00")
        self.assertContains(response, "23074.012345/2026-10")
        self.assertContains(response, "Complemento para ampliação do escopo")
        self.assertContains(response, reverse("nota-empenho-reforco-edit", args=[self.nota.pk, reforco.pk]))
        self.assertContains(response, reverse("nota-empenho-reforco-delete", args=[self.nota.pk, reforco.pk]))

    def test_budget_page_can_create_reforco_with_numero_processo_sipac(self):
        self.client.login(username="operador_orcamento", password="segredo")
        response = self.client.post(
            reverse("nota-empenho-reforco", args=[self.nota.pk]),
            {
                "valor_reforco": "250,00",
                "numero_processo_sipac": "23074.009999/2026-21",
                "descricao_reforco": "Reforço emergencial",
            },
        )

        self.assertEqual(response.status_code, 200)
        reforco = ReforcoEmpenho.objects.get(empenho=self.nota)
        self.assertEqual(reforco.numero_processo_sipac, "23074.009999/2026-21")
        self.assertEqual(reforco.descricao, "Reforço emergencial")

    def test_budget_page_can_edit_existing_reforco(self):
        reforco = ReforcoEmpenho.objects.create(
            empenho=self.nota,
            valor=Decimal("250.00"),
            numero_processo_sipac="23074.000001/2026-01",
            descricao="Texto inicial",
        )

        self.client.login(username="operador_orcamento", password="segredo")
        response = self.client.post(
            reverse("nota-empenho-reforco-edit", args=[self.nota.pk, reforco.pk]),
            {
                "valor_reforco": "300,00",
                "numero_processo_sipac": "23074.000002/2026-02",
                "descricao_reforco": "Texto atualizado",
            },
        )

        self.assertEqual(response.status_code, 200)
        reforco.refresh_from_db()
        self.assertEqual(reforco.valor, Decimal("300.00"))
        self.assertEqual(reforco.numero_processo_sipac, "23074.000002/2026-02")
        self.assertEqual(reforco.descricao, "Texto atualizado")

    def test_budget_page_can_delete_existing_reforco(self):
        reforco = ReforcoEmpenho.objects.create(
            empenho=self.nota,
            valor=Decimal("250.00"),
            numero_processo_sipac="23074.000003/2026-03",
            descricao="Texto para exclusão",
        )

        self.client.login(username="operador_orcamento", password="segredo")
        response = self.client.post(
            reverse("nota-empenho-reforco-delete", args=[self.nota.pk, reforco.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ReforcoEmpenho.objects.filter(pk=reforco.pk).exists())

    def test_budget_page_sorts_finalized_requests_by_budget_value(self):
        menor = Requisicao.objects.create(
            codigo="123/2026",
            numero=123,
            ano=2026,
            assunto="Menor orçamento",
            data_cadastro=date(2026, 4, 10),
            situacao_requisicao="Inativa",
            status_sipac="06 FINALIZADA",
            orcamento_valor=Decimal("100.00"),
        )
        maior = Requisicao.objects.create(
            codigo="124/2026",
            numero=124,
            ano=2026,
            assunto="Maior orçamento",
            data_cadastro=date(2026, 4, 11),
            situacao_requisicao="Inativa",
            status_sipac="06 FINALIZADA",
            orcamento_valor=Decimal("900.00"),
        )

        self.client.login(username="operador_orcamento", password="segredo")
        response = self.client.get(reverse("internal-orcamento"), {"sort": "orcamento_valor", "dir": "asc"})

        resultados = list(response.context["reqs_finalizadas"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(resultados[0].pk, menor.pk)
        self.assertEqual(resultados[-1].pk, maior.pk)
