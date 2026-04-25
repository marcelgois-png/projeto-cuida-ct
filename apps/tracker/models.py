from __future__ import annotations

from datetime import date

from django.conf import settings
from django.db import models

from .domain import (
    PRIORITY_CHOICES,
    calculate_gut,
    classify_gut,
    clean_display_text,
    derive_situation,
    normalize_key,
    resolve_status_sipac_metadata,
)


class TimeStampedModel(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Predio(TimeStampedModel):
    nome = models.CharField(max_length=255, unique=True)
    chave_normalizada = models.CharField(max_length=255, unique=True, editable=False)
    latitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    visivel_publicamente = models.BooleanField(default=True)

    class Meta:
        ordering = ("nome",)

    def save(self, *args, **kwargs):
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
        ordering = ("nome",)
        constraints = [
            models.UniqueConstraint(
                fields=("chave_normalizada", "unidade_setor"),
                name="tracker_unique_requisitante",
            )
        ]

    def save(self, *args, **kwargs):
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
        ordering = ("divisao", "tipo_servico", "servico")

    def save(self, *args, **kwargs):
        self.divisao = clean_display_text(self.divisao)
        self.tipo_servico = clean_display_text(self.tipo_servico)
        self.servico = clean_display_text(self.servico)
        self.chave_normalizada = normalize_key(self.divisao, self.tipo_servico, self.servico)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return " / ".join(filter(None, [self.divisao, self.tipo_servico, self.servico]))


class StatusSipacOpcao(TimeStampedModel):
    numero = models.CharField(max_length=2, blank=True)
    rotulo = models.CharField(max_length=255, blank=True)
    descricao = models.CharField(max_length=255, unique=True)
    chave_normalizada = models.CharField(max_length=255, unique=True, editable=False)
    ordem = models.PositiveIntegerField(null=True, blank=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ("ordem", "numero", "descricao")

    def save(self, *args, **kwargs):
        metadata = resolve_status_sipac_metadata(self.descricao)
        self.numero = clean_display_text(self.numero) or metadata["numero"]
        self.rotulo = clean_display_text(self.rotulo) or metadata["rotulo"] or metadata["descricao"]
        self.descricao = clean_display_text(self.descricao)
        self.chave_normalizada = normalize_key(self.descricao)
        if self.ordem is None:
            self.ordem = metadata["ordem"]
        super().save(*args, **kwargs)

    @property
    def exibicao(self) -> str:
        return clean_display_text(self.rotulo) or self.descricao

    def __str__(self) -> str:
        return self.exibicao


class RegraPrioridade(TimeStampedModel):
    chave_normalizada = models.CharField(max_length=255, unique=True)
    prioridade = models.CharField(max_length=30, choices=PRIORITY_CHOICES)
    descricao = models.CharField(max_length=255, blank=True)
    origem = models.CharField(max_length=50, default="planilha")
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ("prioridade", "chave_normalizada")

    def __str__(self) -> str:
        return f"{self.prioridade} - {self.chave_normalizada}"


class GUTParametro(TimeStampedModel):
    class Tipo(models.TextChoices):
        GRAVIDADE = "GRAVIDADE", "Gravidade"
        URGENCIA = "URGENCIA", "Urgência"
        TENDENCIA = "TENDENCIA", "Tendência"

    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    valor = models.PositiveSmallIntegerField()
    descricao = models.CharField(max_length=255)

    class Meta:
        ordering = ("tipo", "-valor")
        verbose_name = "Parâmetro GUT"
        verbose_name_plural = "Parâmetros GUT"
        unique_together = ("tipo", "valor")

    def __str__(self) -> str:
        return f"{self.tipo} {self.valor}: {self.descricao}"


class Empresa(TimeStampedModel):
    nome = models.CharField(max_length=255, unique=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ("nome",)
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"

    def __str__(self) -> str:
        return self.nome


class NotaEmpenho(TimeStampedModel):
    nota_empenho = models.CharField(max_length=100, verbose_name="Nota de Empenho")
    valor = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Valor (R$)")
    numero_processo_sipac = models.CharField(max_length=100, blank=True, verbose_name="Nº Processo SIPAC")
    link_processo_sipac = models.URLField(max_length=1000, blank=True, verbose_name="Link Processo SIPAC")
    empresa = models.CharField(max_length=255, blank=True, verbose_name="Empresa")

    class Meta:
        ordering = ("-criado_em",)
        verbose_name = "Nota de Empenho"
        verbose_name_plural = "Notas de Empenho"

    def __str__(self) -> str:
        return self.nota_empenho

    @property
    def total_reforcos(self):
        from django.db.models import Sum
        return self.reforcos.aggregate(total=Sum("valor"))["total"] or 0

    @property
    def valor_total(self):
        return self.valor + self.total_reforcos

    @property
    def saldo(self):
        from django.db.models import Sum
        gasto = self.requisicoes_empenho.filter(
            situacao_requisicao="Inativa",
            orcamento_valor__isnull=False,
        ).aggregate(total=Sum("orcamento_valor"))["total"] or 0
        return self.valor_total - gasto


class ReforcoEmpenho(TimeStampedModel):
    empenho = models.ForeignKey(
        NotaEmpenho,
        on_delete=models.CASCADE,
        related_name="reforcos",
        verbose_name="Nota de Empenho",
    )
    valor = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Valor do Reforço (R$)")
    numero_processo_sipac = models.CharField(max_length=100, blank=True, verbose_name="Nº Processo SIPAC")
    descricao = models.TextField(blank=True, verbose_name="Descrição")

    class Meta:
        ordering = ("-criado_em",)
        verbose_name = "Reforço de Empenho"
        verbose_name_plural = "Reforços de Empenho"

    def __str__(self) -> str:
        return f"Reforço R${self.valor} — {self.empenho.nota_empenho}"


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
    divisao = models.CharField(max_length=255, blank=True)
    unidade_origem = models.CharField(max_length=255, blank=True)
    status_sipac = models.CharField(max_length=255, blank=True)
    situacao_requisicao = models.CharField(max_length=20, blank=True)
    tipo_servico = models.CharField(max_length=255, blank=True)
    servico = models.CharField(max_length=255, blank=True)
    taxonomia = models.ForeignKey(
        TaxonomiaServico,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requisicoes",
    )
    predio = models.ForeignKey(
        Predio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requisicoes",
    )
    local_servico = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    requisitante = models.ForeignKey(
        Requisitante,
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
    nota_empenho = models.ForeignKey(
        "NotaEmpenho",
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
        self.divisao = clean_display_text(self.divisao)
        self.unidade_origem = clean_display_text(self.unidade_origem)
        self.status_sipac = clean_display_text(self.status_sipac)
        self.tipo_servico = clean_display_text(self.tipo_servico)
        self.servico = clean_display_text(self.servico)
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
        self.situacao_requisicao = derive_situation(self.status_sipac)
        self.gut_score = calculate_gut(self.gravidade, self.urgencia, self.tendencia)
        self.gut_nivel = classify_gut(self.gut_score)
        if not self.data_cadastro:
            self.dias_para_execucao = None
        elif self.status_sipac == "06 FINALIZADA":
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
        return normalize_key(self.divisao, self.tipo_servico, self.servico)

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
        ENCERRAR_REQUISICAO = "encerrar_requisicao", "Encerrar requisi\u00e7\u00e3o"
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
        verbose_name="Requisi\u00e7\u00f5es",
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
