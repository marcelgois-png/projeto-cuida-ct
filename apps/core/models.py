from __future__ import annotations

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


# ── Models movidos do tracker (Bloco B) ───────────────────────────────────────
# Os save() usam lazy import de tracker.domain para evitar dependência circular.
# Bloco E vai mover clean_display_text / normalize_key para core.domain.


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


class Requisitante(TimeStampedModel):
    nome = models.CharField(max_length=255)
    chave_normalizada = models.CharField(max_length=255, editable=False)
    unidade_setor = models.CharField(max_length=255, blank=True)
    contato_url = models.CharField(max_length=30, blank=True)
    visivel_publicamente = models.BooleanField(default=True)

    class Meta:
        ordering = ('nome',)
        db_table = 'core_solicitante'
        constraints = [
            models.UniqueConstraint(
                fields=('chave_normalizada', 'unidade_setor'),
                name='tracker_unique_requisitante',
            )
        ]

    def save(self, *args, **kwargs):
        from apps.tracker.domain import clean_display_text, normalize_key
        self.nome = clean_display_text(self.nome)
        self.unidade_setor = clean_display_text(self.unidade_setor)
        self.contato_url = clean_display_text(self.contato_url)
        self.chave_normalizada = normalize_key(self.nome)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nome


class TaxonomiaServico(TimeStampedModel):
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


class StatusSipacOpcao(TimeStampedModel):
    numero = models.CharField(max_length=2, blank=True)
    rotulo = models.CharField(max_length=255, blank=True)
    descricao = models.CharField(max_length=255, unique=True)
    chave_normalizada = models.CharField(max_length=255, unique=True, editable=False)
    ordem = models.PositiveIntegerField(null=True, blank=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ('ordem', 'numero', 'descricao')
        db_table = 'core_statussipacopcao'

    def save(self, *args, **kwargs):
        from apps.tracker.domain import clean_display_text, normalize_key, resolve_status_sipac_metadata
        metadata = resolve_status_sipac_metadata(self.descricao)
        self.numero = clean_display_text(self.numero) or metadata['numero']
        self.rotulo = clean_display_text(self.rotulo) or metadata['rotulo'] or metadata['descricao']
        self.descricao = clean_display_text(self.descricao)
        self.chave_normalizada = normalize_key(self.descricao)
        if self.ordem is None:
            self.ordem = metadata['ordem']
        super().save(*args, **kwargs)

    @property
    def exibicao(self) -> str:
        from apps.tracker.domain import clean_display_text
        return clean_display_text(self.rotulo) or self.descricao

    def __str__(self) -> str:
        return self.exibicao


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


class NotaEmpenho(TimeStampedModel):
    nota_empenho = models.CharField(max_length=100, verbose_name='Nota de Empenho')
    valor = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Valor (R$)')
    numero_processo_sipac = models.CharField(max_length=100, blank=True, verbose_name='Nº Processo SIPAC')
    link_processo_sipac = models.URLField(max_length=1000, blank=True, verbose_name='Link Processo SIPAC')
    empresa = models.CharField(max_length=255, blank=True, verbose_name='Empresa')

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
        return self.reforcos.aggregate(total=Sum('valor'))['total'] or 0

    @property
    def valor_total(self):
        return self.valor + self.total_reforcos

    @property
    def saldo(self):
        from django.db.models import Sum
        gasto = self.requisicoes_empenho.filter(
            situacao_requisicao='Inativa',
            orcamento_valor__isnull=False,
        ).aggregate(total=Sum('orcamento_valor'))['total'] or 0
        return self.valor_total - gasto


class ReforcoEmpenho(TimeStampedModel):
    empenho = models.ForeignKey(
        NotaEmpenho,
        on_delete=models.CASCADE,
        related_name='reforcos',
        verbose_name='Nota de Empenho',
    )
    valor = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Valor do Reforço (R$)')
    numero_processo_sipac = models.CharField(max_length=100, blank=True, verbose_name='Nº Processo SIPAC')
    descricao = models.TextField(blank=True, verbose_name='Descrição')

    class Meta:
        ordering = ('-criado_em',)
        verbose_name = 'Reforço de Empenho'
        verbose_name_plural = 'Reforços de Empenho'
        db_table = 'core_movimentacaoempenho'

    def __str__(self) -> str:
        return f'Reforço R${self.valor} — {self.empenho.nota_empenho}'
