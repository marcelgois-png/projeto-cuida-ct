from __future__ import annotations

from datetime import date

from django.db import models


PRIORITY_CHOICES = [
    ('1 - Urgente', '1 - Urgente'),
    ('2 - Alta', '2 - Alta'),
    ('3 - Média', '3 - Média'),
    ('4 - Baixa', '4 - Baixa'),
    ('5 - Analisar', '5 - Analisar'),
    ('6 - Inativa', '6 - Inativa'),
]


class TimeStampedModel(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ── Localização ───────────────────────────────────────────────────────────────

class Predio(TimeStampedModel):
    nome = models.CharField(max_length=255, unique=True)
    chave_normalizada = models.CharField(max_length=255, unique=True, editable=False)
    latitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    visivel_publicamente = models.BooleanField(default=True)

    class Meta:
        ordering = ('nome',)
        db_table = 'core_predio'

    def save(self, *args, **kwargs):
        from apps.tracker.domain import clean_display_text, normalize_key
        self.nome = clean_display_text(self.nome)
        self.chave_normalizada = normalize_key(self.nome)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nome


class Setor(TimeStampedModel):
    nome = models.CharField(max_length=200, unique=True)
    sigla = models.CharField(max_length=20, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ('nome',)
        db_table = 'core_setor'

    def __str__(self) -> str:
        return self.nome


# ── Pessoas ───────────────────────────────────────────────────────────────────

class Solicitante(TimeStampedModel):
    nome = models.CharField(max_length=255)
    chave_normalizada = models.CharField(max_length=255, editable=False)
    identificador = models.CharField(max_length=50, blank=True)
    tipo_identificador = models.CharField(
        max_length=20,
        blank=True,
        choices=[('SIAPE', 'SIAPE'), ('MATRICULA', 'Matrícula'), ('CPF', 'CPF')],
    )
    setor = models.ForeignKey(
        Setor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='solicitantes',
    )
    contato_url = models.CharField(max_length=30, blank=True)
    visivel_publicamente = models.BooleanField(default=True)

    class Meta:
        ordering = ('nome',)
        db_table = 'core_solicitante'

    def save(self, *args, **kwargs):
        from apps.tracker.domain import clean_display_text, normalize_key
        self.nome = clean_display_text(self.nome)
        self.contato_url = clean_display_text(self.contato_url)
        self.chave_normalizada = normalize_key(self.nome)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nome


# Alias para compatibilidade durante a transição (Bloco E remove este alias)
Requisitante = Solicitante


# ── Serviços ──────────────────────────────────────────────────────────────────

class DivisaoSINFRA(TimeStampedModel):
    nome = models.CharField(max_length=200, unique=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ('nome',)
        db_table = 'core_divisaosinfra'
        verbose_name = 'Divisão SINFRA'
        verbose_name_plural = 'Divisões SINFRA'

    def __str__(self) -> str:
        return self.nome


class TipoServico(TimeStampedModel):
    nome = models.CharField(max_length=200)
    divisao = models.ForeignKey(
        DivisaoSINFRA,
        on_delete=models.PROTECT,
        related_name='tipos_servico',
        verbose_name='Divisão',
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ('divisao__nome', 'nome')
        db_table = 'core_tiposervico'
        unique_together = (('divisao', 'nome'),)
        verbose_name = 'Tipo de serviço'
        verbose_name_plural = 'Tipos de serviço'

    def __str__(self) -> str:
        return f'{self.divisao.nome} / {self.nome}'


class Servico(TimeStampedModel):
    nome = models.CharField(max_length=200)
    tipo_servico = models.ForeignKey(
        TipoServico,
        on_delete=models.PROTECT,
        related_name='servicos',
        verbose_name='Tipo de serviço',
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ('tipo_servico__divisao__nome', 'tipo_servico__nome', 'nome')
        db_table = 'core_servico'
        unique_together = (('tipo_servico', 'nome'),)
        verbose_name = 'Serviço'
        verbose_name_plural = 'Serviços'

    def __str__(self) -> str:
        return f'{self.tipo_servico} / {self.nome}'


class TaxonomiaServico(TimeStampedModel):
    """Mantido como tabela de lookup/mapeamento. Bloco E avalia remoção."""
    divisao = models.CharField(max_length=255)
    tipo_servico = models.CharField(max_length=255)
    servico = models.CharField(max_length=255, blank=True)
    chave_normalizada = models.CharField(max_length=255, unique=True, editable=False)
    ordem_divisao = models.PositiveIntegerField(null=True, blank=True)
    ordem_tipo = models.PositiveIntegerField(null=True, blank=True)
    ordem_servico = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ('divisao', 'tipo_servico', 'servico')
        db_table = 'core_taxonomiaservico'

    def save(self, *args, **kwargs):
        from apps.tracker.domain import clean_display_text, normalize_key
        self.divisao = clean_display_text(self.divisao)
        self.tipo_servico = clean_display_text(self.tipo_servico)
        self.servico = clean_display_text(self.servico)
        self.chave_normalizada = normalize_key(self.divisao, self.tipo_servico, self.servico)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return ' / '.join(filter(None, [self.divisao, self.tipo_servico, self.servico]))


# ── Status e priorização ──────────────────────────────────────────────────────

class StatusRequisicao(TimeStampedModel):
    numero = models.CharField(max_length=2, blank=True)
    nome = models.CharField(max_length=255, blank=True)
    codigo = models.CharField(max_length=255, unique=True)
    chave_normalizada = models.CharField(max_length=255, unique=True, editable=False)
    mapeamento_situacao = models.CharField(
        max_length=20,
        blank=True,
        choices=[('ATIVA', 'Ativa'), ('INATIVA', 'Inativa')],
        verbose_name='Mapeamento situação',
    )
    ordem = models.PositiveIntegerField(null=True, blank=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ('ordem', 'numero', 'codigo')
        db_table = 'core_statusrequisicao'
        verbose_name = 'Status de requisição'
        verbose_name_plural = 'Status de requisições'

    def save(self, *args, **kwargs):
        from apps.tracker.domain import clean_display_text, normalize_key, resolve_status_sipac_metadata
        metadata = resolve_status_sipac_metadata(self.codigo)
        self.numero = clean_display_text(self.numero) or metadata['numero']
        self.nome = clean_display_text(self.nome) or metadata['rotulo'] or metadata['descricao']
        self.codigo = clean_display_text(self.codigo)
        self.chave_normalizada = normalize_key(self.codigo)
        if self.ordem is None:
            self.ordem = metadata['ordem']
        super().save(*args, **kwargs)

    @property
    def exibicao(self) -> str:
        from apps.tracker.domain import clean_display_text
        return clean_display_text(self.nome) or self.codigo

    def __str__(self) -> str:
        return self.exibicao


# Alias de compatibilidade (Bloco E remove)
StatusSipacOpcao = StatusRequisicao


class RegraPrioridade(TimeStampedModel):
    chave_normalizada = models.CharField(max_length=255, unique=True)
    prioridade = models.CharField(max_length=30, choices=PRIORITY_CHOICES)
    descricao = models.CharField(max_length=255, blank=True)
    origem = models.CharField(max_length=50, default='planilha')
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ('prioridade', 'chave_normalizada')
        db_table = 'core_regraprioridade'

    def __str__(self) -> str:
        return f'{self.prioridade} - {self.chave_normalizada}'


class GUTParametro(TimeStampedModel):
    class Tipo(models.TextChoices):
        GRAVIDADE = 'GRAVIDADE', 'Gravidade'
        URGENCIA = 'URGENCIA', 'Urgência'
        TENDENCIA = 'TENDENCIA', 'Tendência'

    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    valor = models.PositiveSmallIntegerField()
    descricao = models.CharField(max_length=255)

    class Meta:
        ordering = ('tipo', '-valor')
        verbose_name = 'Parâmetro GUT'
        verbose_name_plural = 'Parâmetros GUT'
        unique_together = (('tipo', 'valor'),)
        db_table = 'core_gutparametro'

    def __str__(self) -> str:
        return f'{self.tipo} {self.valor}: {self.descricao}'


# ── Empresas e empenhos ───────────────────────────────────────────────────────

class Empresa(TimeStampedModel):
    nome = models.CharField(max_length=255, unique=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ('nome',)
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'
        db_table = 'core_empresa'

    def __str__(self) -> str:
        return self.nome


class Empenho(TimeStampedModel):
    nota_empenho = models.CharField(max_length=100, verbose_name='Nota de Empenho')
    numero_processo_sipac = models.CharField(max_length=100, blank=True, verbose_name='Nº Processo SIPAC')
    link_processo_sipac = models.URLField(max_length=1000, blank=True, verbose_name='Link Processo SIPAC')
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='empenhos',
        verbose_name='Empresa',
    )
    modulo_origem = models.CharField(max_length=20, default='REQUISICAO', verbose_name='Módulo de origem')

    class Meta:
        ordering = ('-criado_em',)
        verbose_name = 'Nota de Empenho'
        verbose_name_plural = 'Notas de Empenho'
        db_table = 'core_empenho'

    def __str__(self) -> str:
        return self.nota_empenho

    @property
    def total_reforcos(self):
        from django.db.models import Sum
        return self.reforcos.filter(tipo='REFORCO').aggregate(total=Sum('valor'))['total'] or 0

    @property
    def valor_total(self):
        from django.db.models import Sum
        return self.reforcos.aggregate(total=Sum('valor'))['total'] or 0

    @property
    def saldo(self):
        from django.db.models import Sum
        gasto = self.requisicoes_empenho.filter(
            situacao_requisicao='Inativa',
            orcamento_valor__isnull=False,
        ).aggregate(total=Sum('orcamento_valor'))['total'] or 0
        return self.valor_total - gasto


# Alias de compatibilidade (Bloco E remove)
NotaEmpenho = Empenho


class MovimentacaoEmpenho(TimeStampedModel):
    class Tipo(models.TextChoices):
        VALOR_INICIAL = 'VALOR_INICIAL', 'Valor inicial'
        REFORCO = 'REFORCO', 'Reforço'
        ESTORNO = 'ESTORNO', 'Estorno'
        ANULACAO = 'ANULACAO', 'Anulação'

    empenho = models.ForeignKey(
        Empenho,
        on_delete=models.CASCADE,
        related_name='reforcos',
        verbose_name='Nota de Empenho',
    )
    tipo = models.CharField(
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.REFORCO,
        verbose_name='Tipo',
    )
    valor = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Valor do Reforço (R$)')
    numero_processo_sipac = models.CharField(max_length=100, blank=True, verbose_name='Nº Processo SIPAC')
    descricao = models.TextField(blank=True, verbose_name='Descrição')
    data = models.DateField(null=True, blank=True, verbose_name='Data')
    observacao = models.TextField(blank=True, verbose_name='Observação')

    class Meta:
        ordering = ('-criado_em',)
        verbose_name = 'Movimentação de Empenho'
        verbose_name_plural = 'Movimentações de Empenho'
        db_table = 'core_movimentacaoempenho'

    def __str__(self) -> str:
        return f'{self.get_tipo_display()} R${self.valor} — {self.empenho.nota_empenho}'


# Alias de compatibilidade (Bloco E remove)
ReforcoEmpenho = MovimentacaoEmpenho
