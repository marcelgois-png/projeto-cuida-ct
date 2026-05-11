from __future__ import annotations

from decimal import Decimal

from django.conf import settings
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
    unidade_origem = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Unidade de origem',
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

    # ── propriedades calculadas ──────────────────────────────────────────────

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


# ── InteressadoProcesso ───────────────────────────────────────────────────────

class InteressadoProcesso(TimeStampedModel):
    """Interessado vinculado ao processo conforme dados públicos do SIPAC."""

    processo = models.ForeignKey(
        Processo,
        on_delete=models.CASCADE,
        related_name='interessados',
        verbose_name='Processo',
    )
    tipo = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Tipo',
    )
    identificador = models.CharField(
        max_length=80,
        blank=True,
        verbose_name='Identificador',
    )
    nome = models.CharField(
        max_length=255,
        verbose_name='Nome',
    )

    class Meta:
        db_table = 'processos_interessadoprocesso'
        ordering = ['processo', 'tipo', 'nome']
        unique_together = [('processo', 'tipo', 'identificador', 'nome')]
        verbose_name = 'Interessado do processo'
        verbose_name_plural = 'Interessados do processo'

    def __str__(self) -> str:
        return f'{self.nome} ({self.processo.numero_processo})'


# ── AcompanhamentoProcesso ────────────────────────────────────────────────────

class AcompanhamentoProcesso(TimeStampedModel):
    """Entrada de acompanhamento/histórico de um Processo."""

    processo = models.ForeignKey(
        Processo,
        on_delete=models.CASCADE,
        related_name='acompanhamentos',
        verbose_name='Processo',
    )
    data = models.DateField(verbose_name='Data')
    atualizacao = models.TextField(verbose_name='Atualização da situação')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='acompanhamentos_processo',
        verbose_name='Usuário',
    )

    class Meta:
        db_table = 'processos_acompanhamentoprocesso'
        ordering = ('data', 'criado_em', 'pk')
        verbose_name = 'Acompanhamento do processo'
        verbose_name_plural = 'Acompanhamentos do processo'

    @property
    def usuario_nome(self) -> str:
        if not self.usuario:
            return ''
        nome = getattr(self.usuario, 'nome_completo', None)
        if nome:
            return nome
        full = self.usuario.get_full_name()
        return full or self.usuario.username

    def __str__(self) -> str:
        return f'{self.processo.numero_processo} – {self.data:%d/%m/%Y}'


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

    @property
    def valor_final_calculado(self):
        """Valor final com ajustes encadeados. Se não há itens, retorna self.valor."""
        from decimal import Decimal, ROUND_HALF_UP
        _2 = Decimal('0.01')
        itens = list(self.itens.all())
        if not itens:
            return self.valor
        ajustes = list(self.ajustes.order_by('ordem'))
        total = Decimal('0')
        for item in itens:
            v = item.valor or Decimal('0')
            for aj in ajustes:
                v = (v * (1 + aj.percentual / 100)).quantize(_2, ROUND_HALF_UP)
            total += v
        return total.quantize(_2, ROUND_HALF_UP)

    @property
    def valor_itens(self):
        """Soma dos valores base dos itens (sem ajustes)."""
        from decimal import Decimal
        from django.db.models import Sum
        total = self.itens.aggregate(s=Sum('valor'))['s']
        return total if total is not None else Decimal('0')

    def get_itens_com_ajustes(self):
        """Retorna itens com colunas calculadas por ajuste encadeado."""
        from decimal import Decimal, ROUND_HALF_UP
        _2 = Decimal('0.01')
        ajustes = list(self.ajustes.order_by('ordem'))
        itens   = list(self.itens.order_by('ordem', 'numero'))
        num_cols = len(ajustes) + 1
        totais   = [Decimal('0')] * num_cols

        linhas = []
        for item in itens:
            base = (item.valor or Decimal('0'))
            valores = [base]
            for aj in ajustes:
                prev = valores[-1]
                valores.append(
                    (prev * (1 + aj.percentual / 100)).quantize(_2, ROUND_HALF_UP)
                )
            linhas.append({'item': item, 'valores': valores})
            for i, v in enumerate(valores):
                totais[i] += v

        totais = [t.quantize(_2, ROUND_HALF_UP) for t in totais]
        return {
            'linhas': linhas,
            'ajustes': ajustes,
            'totais': totais,
            'valor_final': totais[-1] if totais else Decimal('0'),
        }

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


# ── AjusteOrcamento ──────────────────────────────────────────────────────────

class AjusteOrcamento(TimeStampedModel):
    """Coluna de desconto ou acréscimo aplicada em cadeia sobre os itens do orçamento."""

    orcamento = models.ForeignKey(
        Orcamento,
        on_delete=models.CASCADE,
        related_name='ajustes',
        verbose_name='Orçamento',
    )
    rotulo = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Rótulo',
        help_text='Ex: Desconto, BDI, ISS',
    )
    percentual = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        verbose_name='Percentual (%)',
        help_text='Negativo para desconto (ex: -18.5), positivo para acréscimo (ex: 25.0)',
    )
    ordem = models.PositiveSmallIntegerField(default=0, verbose_name='Ordem')

    class Meta:
        db_table = 'processos_ajuste_orcamento'
        ordering = ['ordem']
        verbose_name = 'Ajuste de Orçamento'
        verbose_name_plural = 'Ajustes de Orçamento'

    def __str__(self) -> str:
        sinal = '+' if self.percentual >= 0 else ''
        return f'{self.rotulo or "Ajuste"} ({sinal}{self.percentual}%)'


# ── ItemOrcamento ─────────────────────────────────────────────────────────────

class ItemOrcamento(TimeStampedModel):
    """Item/grupo de serviço de um Orçamento (ex: 1.0 Serviços preliminares)."""

    orcamento = models.ForeignKey(
        Orcamento,
        on_delete=models.CASCADE,
        related_name='itens',
        verbose_name='Orçamento',
    )
    numero = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Número',
        help_text='Ex: 1.0, 2.0',
    )
    descricao = models.CharField(max_length=500, verbose_name='Descrição')
    valor = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True, blank=True,
        verbose_name='Valor (R$)',
    )
    ordem = models.PositiveSmallIntegerField(default=0, verbose_name='Ordem')

    class Meta:
        db_table = 'processos_item_orcamento'
        ordering = ['ordem', 'numero']
        verbose_name = 'Item de Orçamento'
        verbose_name_plural = 'Itens de Orçamento'

    def __str__(self) -> str:
        return f'{self.numero} {self.descricao}'.strip()
