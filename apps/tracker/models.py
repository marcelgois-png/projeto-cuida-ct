from __future__ import annotations

from datetime import date

from django.conf import settings
from django.db import models

from apps.core.models import (
    TimeStampedModel,
    Predio,
    Setor,
    Solicitante,
    DivisaoSINFRA,
    TipoServico,
    Servico,
    TaxonomiaServico,
    StatusRequisicao,
    GUTParametro,
    RegraPrioridade,
    Empresa,
    Empenho,
    MovimentacaoEmpenho,
    # aliases de compatibilidade — removidos no Bloco E
    Requisitante,
    StatusSipacOpcao,
    NotaEmpenho,
    ReforcoEmpenho,
)

from .domain import (
    PRIORITY_CHOICES,
    calculate_gut,
    classify_gut,
    clean_display_text,
    derive_situation,
    normalize_key,
    resolve_status_sipac_metadata,
)


class ImportacaoArquivo(TimeStampedModel):
    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        PROCESSANDO = "processando", "Processando"
        CONCLUIDA = "concluida", "Concluída"
        FALHA = "falha", "Falha"

    nome_arquivo = models.CharField(max_length=255)
    tipo_arquivo = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
    iniciado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="importacoes_realizadas",
    )
    processado_em = models.DateTimeField(null=True, blank=True)
    resumo_json = models.JSONField(default=dict, blank=True)
    mensagem_erro = models.TextField(blank=True)

    class Meta:
        ordering = ("-criado_em",)

    def __str__(self) -> str:
        return f"{self.nome_arquivo} ({self.get_status_display()})"


class Requisicao(TimeStampedModel):
    codigo = models.CharField(max_length=20, unique=True)
    numero = models.PositiveIntegerField(null=True, blank=True)
    ano = models.PositiveIntegerField(null=True, blank=True)
    assunto = models.TextField(blank=True)
    orcamento = models.CharField(max_length=255, blank=True)
    data_cadastro = models.DateField(null=True, blank=True)
    tipo_requisicao = models.CharField(max_length=255, blank=True)
    # divisao/tipo_servico/servico: eram CharFields, agora são FKs (migração C2)
    divisao = models.ForeignKey(
        'core.DivisaoSINFRA',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requisicoes',
        verbose_name='Divisão',
    )
    tipo_servico = models.ForeignKey(
        'core.TipoServico',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requisicoes',
        verbose_name='Tipo de serviço',
    )
    servico = models.ForeignKey(
        'core.Servico',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requisicoes',
        verbose_name='Serviço',
    )
    unidade_origem = models.CharField(max_length=255, blank=True)
    # status_sipac: era CharField, agora é FK (migração C3) — permanece nullable
    status_sipac = models.ForeignKey(
        'core.StatusRequisicao',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requisicoes',
        verbose_name='Status SIPAC',
    )
    situacao_requisicao = models.CharField(max_length=20, blank=True)
    predio = models.ForeignKey(
        'core.Predio',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requisicoes",
    )
    local_servico = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    # requisitante aponta para core.Solicitante (renomeado via C1); campo renomeado no Bloco E
    requisitante = models.ForeignKey(
        'core.Solicitante',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requisicoes",
    )
    nome_requisitante_snapshot = models.CharField(max_length=255, blank=True)
    unidade_setor_snapshot = models.CharField(max_length=255, blank=True)
    contato_direto_url = models.CharField(max_length=30, blank=True)
    situacao_texto = models.TextField(blank=True)
    status_fluxo = models.CharField(max_length=50, blank=True)
    gravidade = models.CharField(max_length=100, blank=True)
    urgencia = models.CharField(max_length=100, blank=True)
    tendencia = models.CharField(max_length=100, blank=True)
    gut_score = models.PositiveIntegerField(default=0)
    gut_nivel = models.CharField(max_length=20, blank=True)
    sinfra_responsavel = models.CharField(max_length=100, blank=True)
    prioridade_final = models.CharField(max_length=30, choices=PRIORITY_CHOICES, blank=True)
    link_atendimento = models.URLField(max_length=1000, blank=True)
    link_sipac = models.URLField(max_length=1000, blank=True)
    data_execucao = models.DateField(null=True, blank=True)
    dias_para_execucao = models.IntegerField(null=True, blank=True)
    visivel_publicamente = models.BooleanField(default=True)
    importacao_origem = models.ForeignKey(
        ImportacaoArquivo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requisicoes",
    )
    empresa = models.CharField(max_length=255, blank=True, verbose_name="Empresa")
    orcamento_valor = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Orçamento (R$)"
    )
    # nota_empenho aponta para core.Empenho (renomeado via C4); campo renomeado no Bloco E
    nota_empenho = models.ForeignKey(
        'core.Empenho',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requisicoes_empenho",
        verbose_name="Nota de Empenho",
    )

    class StatusProcessoDiretor(models.TextChoices):
        NAO_INDICADO = "nao_indicado", "Não Indicado"
        AGUARDANDO_DECISAO = "aguardando_decisao", "Aguardando Decisão"
        AUTORIZADO = "autorizado", "Autorizado"
        NEGADO = "negado", "Negado"
        INSPECAO_IN_LOCO = "inspecao_in_loco", "Inspecionar in loco"

    status_processo_diretor = models.CharField(
        max_length=20,
        choices=StatusProcessoDiretor.choices,
        default=StatusProcessoDiretor.NAO_INDICADO,
    )
    observacao_diretor = models.TextField(blank=True)

    class Meta:
        ordering = ("-ano", "-numero")

    def save(self, *args, **kwargs):
        self.recompute_derived_fields()
        super().save(*args, **kwargs)

    def recompute_derived_fields(self):
        self.codigo = clean_display_text(self.codigo)
        self.assunto = clean_display_text(self.assunto)
        self.orcamento = clean_display_text(self.orcamento)
        self.tipo_requisicao = clean_display_text(self.tipo_requisicao)
        self.unidade_origem = clean_display_text(self.unidade_origem)
        self.local_servico = clean_display_text(self.local_servico)
        self.nome_requisitante_snapshot = clean_display_text(self.nome_requisitante_snapshot)
        self.unidade_setor_snapshot = clean_display_text(self.unidade_setor_snapshot)
        self.contato_direto_url = clean_display_text(self.contato_direto_url)
        self.situacao_texto = clean_display_text(self.situacao_texto)
        self.status_fluxo = clean_display_text(self.status_fluxo)
        self.gravidade = clean_display_text(self.gravidade)
        self.urgencia = clean_display_text(self.urgencia)
        self.tendencia = clean_display_text(self.tendencia)
        self.sinfra_responsavel = clean_display_text(self.sinfra_responsavel)
        self.link_atendimento = clean_display_text(self.link_atendimento)
        self.link_sipac = clean_display_text(self.link_sipac)
        # status_sipac é agora FK — derive situacao a partir do mapeamento
        if self.status_sipac:
            self.situacao_requisicao = (
                'Ativa' if self.status_sipac.mapeamento_situacao == 'ATIVA' else 'Inativa'
            )
        else:
            self.situacao_requisicao = ''
        self.gut_score = calculate_gut(self.gravidade, self.urgencia, self.tendencia)
        self.gut_nivel = classify_gut(self.gut_score)
        if not self.data_cadastro:
            self.dias_para_execucao = None
        elif (
            self.status_sipac
            and self.status_sipac.codigo == "06 FINALIZADA"
        ):
            if self.data_execucao:
                self.dias_para_execucao = max((self.data_execucao - self.data_cadastro).days, 0)
            else:
                self.dias_para_execucao = None
        elif self.situacao_requisicao == "Ativa":
            self.dias_para_execucao = max((date.today() - self.data_cadastro).days, 0)
        else:
            self.dias_para_execucao = None
        if self.predio:
            if self.latitude is None:
                self.latitude = self.predio.latitude
            if self.longitude is None:
                self.longitude = self.predio.longitude

    @property
    def prioridade_lookup_key(self) -> str:
        return normalize_key(
            self.divisao.nome if self.divisao else '',
            self.tipo_servico.nome if self.tipo_servico else '',
            self.servico.nome if self.servico else '',
        )

    @property
    def dias_desde_abertura(self) -> int | None:
        if not self.data_cadastro:
            return None
        return max((date.today() - self.data_cadastro).days, 0)

    @property
    def nome_requisitante_publico(self) -> str:
        return self.nome_requisitante_snapshot or (self.requisitante.nome if self.requisitante else "")

    def __str__(self) -> str:
        return self.codigo


class EncaminhamentoDiretor(TimeStampedModel):
    class Tipo(models.TextChoices):
        ABRIR_PROCESSO = "abrir_processo", "Abrir processo"
        ENCERRAR_REQUISICAO = "encerrar_requisicao", "Encerrar requisição"
        INSPECIONAR_IN_LOCO = "inspecionar_in_loco", "Inspecionar in loco"

    numero = models.PositiveIntegerField(unique=True, editable=False)
    data_encaminhamento = models.DateField(default=date.today)
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    orientacoes = models.TextField(verbose_name="Orientacoes do diretor")
    diretor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="encaminhamentos_diretor",
    )
    requisicoes = models.ManyToManyField(
        Requisicao,
        related_name="encaminhamentos_diretor",
        blank=True,
        verbose_name="Requisições",
    )

    class Meta:
        ordering = ("-numero", "-data_encaminhamento", "-criado_em")
        verbose_name = "Encaminhamento do diretor"
        verbose_name_plural = "Encaminhamentos do diretor"

    def save(self, *args, **kwargs):
        self.orientacoes = clean_display_text(self.orientacoes)
        if not self.numero:
            ultimo_numero = (
                EncaminhamentoDiretor.objects.aggregate(models.Max("numero")).get("numero__max") or 0
            )
            self.numero = ultimo_numero + 1
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Encaminhamento #{self.numero}"


class HistoricoStatus(TimeStampedModel):
    class Origem(models.TextChoices):
        IMPORTACAO = "importacao", "Importação"
        MANUAL = "manual", "Manual"

    requisicao = models.ForeignKey(Requisicao, on_delete=models.CASCADE, related_name="historicos")
    status_sipac = models.CharField(max_length=255)
    situacao_requisicao = models.CharField(max_length=20, blank=True)
    observacao = models.TextField(blank=True)
    origem = models.CharField(max_length=20, choices=Origem.choices, default=Origem.MANUAL)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historicos_registrados",
    )

    class Meta:
        ordering = ("-criado_em",)

    def save(self, *args, **kwargs):
        if not self.situacao_requisicao:
            self.situacao_requisicao = derive_situation(self.status_sipac)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.requisicao.codigo} - {self.status_sipac}"


class AcompanhamentoRequisicao(TimeStampedModel):
    requisicao = models.ForeignKey(Requisicao, on_delete=models.CASCADE, related_name="acompanhamentos")
    data = models.DateField()
    atualizacao_situacao = models.TextField()
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acompanhamentos_registrados",
    )

    class Meta:
        ordering = ("data", "criado_em", "pk")
        verbose_name = "Acompanhamento da requisição"
        verbose_name_plural = "Acompanhamentos da requisição"

    def save(self, *args, **kwargs):
        self.atualizacao_situacao = clean_display_text(self.atualizacao_situacao)
        super().save(*args, **kwargs)

    @property
    def usuario_nome(self) -> str:
        if not self.usuario:
            return ""
        return (
            clean_display_text(getattr(self.usuario, "nome_completo", ""))
            or clean_display_text(self.usuario.get_full_name())
            or self.usuario.username
        )

    def __str__(self) -> str:
        return f"{self.requisicao.codigo} - {self.data:%d/%m/%Y}"
