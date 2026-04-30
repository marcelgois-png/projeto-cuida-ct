from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import (
    TimeStampedModel,
    Empenho,
    Empresa,
    GerenciaSINFRA,
    Predio,
    ServicoProcesso,
    SituacaoSIPAC,
    StatusProcesso,
    TipoAmbiente,
)


# ── Processo ──────────────────────────────────────────────────────────────────

class Processo(TimeStampedModel):
    """Processo administrativo de manutenção/obra gerenciado pela SINFRA."""

    numero_processo = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Número do processo',
    )
    data_abertura = models.DateField(
        null=True, blank=True,
        verbose_name='Data de abertura',
    )
    data_os = models.DateField(
        null=True, blank=True,
        verbose_name='Data da OS',
    )
    data_conclusao = models.DateField(
        null=True, blank=True,
        verbose_name='Data de conclusão',
    )
    data_arquivamento = models.DateField(
        null=True, blank=True,
        verbose_name='Data de arquivamento',
    )
    assunto = models.TextField(
        blank=True,
        verbose_name='Assunto',
    )
    servico = models.ForeignKey(
        ServicoProcesso,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='processos',
        verbose_name='Serviço',
    )
    gerencia = models.ForeignKey(
        GerenciaSINFRA,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='processos',
        verbose_name='Gerência SINFRA',
    )
    status = models.ForeignKey(
        StatusProcesso,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='processos',
        verbose_name='Status',
    )
    situacao_sipac = models.ForeignKey(
        SituacaoSIPAC,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='processos',
        verbose_name='Situação SIPAC',
    )
    predio = models.ForeignKey(
        Predio,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='processos',
        verbose_name='Prédio',
    )
    tipo_ambiente = models.ForeignKey(
        TipoAmbiente,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='processos',
        verbose_name='Tipo de ambiente',
    )
    solicitantes = models.ManyToManyField(
        'core.Solicitante',
        blank=True,
        related_name='processos',
        verbose_name='Solicitantes',
    )
    classificacao_az = models.CharField(
        max_length=1,
        blank=True,
        verbose_name='Classificação A-Z',
        help_text='Letra de ordenação para priorização A–Z',
    )
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='processos',
        verbose_name='Empresa',
    )
    link_sipac = models.URLField(
        blank=True,
        verbose_name='Link SIPAC',
    )
    observacao = models.TextField(
        blank=True,
        verbose_name='Observação',
    )
    acompanhamento_ct = models.TextField(
        blank=True,
        verbose_name='Acompanhamento CT',
        help_text='Histórico de acompanhamento interno do CT',
    )
    requisicoes = models.ManyToManyField(
        'tracker.Requisicao',
        blank=True,
        related_name='processos',
        verbose_name='Requisições vinculadas',
    )
    encaminhamento_diretor = models.ForeignKey(
        'tracker.EncaminhamentoDiretor',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='processos',
        verbose_name='Encaminhamento ao diretor',
    )

    class Meta:
        db_table = 'processos_processo'
        ordering = ['-data_abertura', 'numero_processo']
        verbose_name = 'Processo'
        verbose_name_plural = 'Processos'

    def __str__(self) -> str:
        return self.numero_processo

    # ── propriedades calculadas ───────────────────────────────────────────────

    @property
    def tempo_reacao(self) -> int | None:
        """Dias entre abertura e OS (tempo de reação da SINFRA)."""
        if self.data_abertura and self.data_os:
            return (self.data_os - self.data_abertura).days
        return None

    @property
    def tempo_execucao(self) -> int | None:
        """Dias entre OS e conclusão."""
        if self.data_os and self.data_conclusao:
            return (self.data_conclusao - self.data_os).days
        return None

    @property
    def tempo_solucao(self) -> int | None:
        """Dias entre abertura e conclusão (tempo total)."""
        if self.data_abertura and self.data_conclusao:
            return (self.data_conclusao - self.data_abertura).days
        return None

    @property
    def tempo_analise(self) -> int | None:
        """Dias desde a abertura até hoje (processos ainda abertos)."""
        if self.data_abertura and not self.data_conclusao:
            from django.utils import timezone
            return (timezone.localdate() - self.data_abertura).days
        return None

    @property
    def valor_total_orcado(self) -> Decimal:
        """Soma dos valores dos orçamentos aprovados."""
        from django.db.models import Sum
        result = self.orcamentos.aggregate(total=Sum('valor'))['total']
        return result or Decimal('0.00')


# ── Orçamento ─────────────────────────────────────────────────────────────────

class Orcamento(TimeStampedModel):
    """Orçamento associado a um Processo."""

    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', _('Pendente')
        APROVADO = 'APROVADO', _('Aprovado')
        REPROVADO = 'REPROVADO', _('Reprovado')
        CANCELADO = 'CANCELADO', _('Cancelado')

    processo = models.ForeignKey(
        Processo,
        on_delete=models.CASCADE,
        related_name='orcamentos',
        verbose_name='Processo',
    )
    numero_sequencial = models.PositiveSmallIntegerField(
        default=1,
        verbose_name='Número sequencial',
        help_text='1º, 2º, 3º orçamento do processo',
    )
    descricao = models.TextField(
        blank=True,
        verbose_name='Descrição',
    )
    valor = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True, blank=True,
        verbose_name='Valor (R$)',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDENTE,
        verbose_name='Status',
    )
    data_emissao = models.DateField(
        null=True, blank=True,
        verbose_name='Data de emissão',
    )
    data_validade = models.DateField(
        null=True, blank=True,
        verbose_name='Data de validade',
    )
    arquivo_planilha = models.FileField(
        upload_to='processos/orcamentos/',
        blank=True,
        verbose_name='Arquivo/planilha',
    )
    historico_negociacao = models.TextField(
        blank=True,
        verbose_name='Histórico de negociação',
    )
    empenhos = models.ManyToManyField(
        Empenho,
        through='OrcamentoEmpenho',
        blank=True,
        related_name='orcamentos',
        verbose_name='Empenhos',
    )

    class Meta:
        db_table = 'processos_orcamento'
        ordering = ['processo', 'numero_sequencial']
        verbose_name = 'Orçamento'
        verbose_name_plural = 'Orçamentos'

    def __str__(self) -> str:
        return f'{self.processo} — Orçamento {self.numero_sequencial}'


# ── OrcamentoEmpenho ──────────────────────────────────────────────────────────

class OrcamentoEmpenho(TimeStampedModel):
    """Tabela pivot entre Orçamento e Empenho com dados adicionais."""

    orcamento = models.ForeignKey(
        Orcamento,
        on_delete=models.CASCADE,
        related_name='orcamento_empenhos',
        verbose_name='Orçamento',
    )
    empenho = models.ForeignKey(
        Empenho,
        on_delete=models.CASCADE,
        related_name='orcamento_empenhos',
        verbose_name='Empenho',
    )
    valor_alocado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True, blank=True,
        verbose_name='Valor alocado (R$)',
    )
    data_vinculacao = models.DateField(
        null=True, blank=True,
        verbose_name='Data de vinculação',
    )
    observacao = models.TextField(
        blank=True,
        verbose_name='Observação',
    )

    class Meta:
        db_table = 'processos_orcamentoempenho'
        unique_together = [('orcamento', 'empenho')]
        verbose_name = 'Vínculo Orçamento-Empenho'
        verbose_name_plural = 'Vínculos Orçamento-Empenho'

    def __str__(self) -> str:
        return f'{self.orcamento} ↔ {self.empenho}'
