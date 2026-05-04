from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Max, Min, Q, Sum, Value, When
from django.db.models.functions import Upper, Trim
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.core.models import (
    Empenho,
    Empresa,
    GerenciaSINFRA,
    MovimentacaoEmpenho,
    Predio,
    ServicoProcesso,
    SituacaoSIPAC,
    StatusRequisicao,
    StatusProcesso,
    TipoAmbiente,
)

from .forms import (
    AcompanhamentoProcessoFormSet,
    InteressadoProcessoFormSet,
    OrcamentoForm,
    ProcessoForm,
)
from .models import AcompanhamentoProcesso, AjusteOrcamento, ItemOrcamento, Orcamento, OrcamentoEmpenho, Processo
from apps.tracker.models import AcompanhamentoRequisicao, EncaminhamentoDiretor

PROCESSOS_HOME_PAGE_SIZE = 100
PROCESSOS_PAGINATION_EDGE_PAGES = 2
PROCESSOS_PAGINATION_WINDOW_PAGES = 2
REQUISICAO_CONVERTIDA_PROCESSO_STATUS = "Requisição Convertida em Processo"
REQUISICAO_CONVERTIDA_PROCESSO_MENSAGEM = (
    "Requisição convertida em processo devido à complexidade dos serviços. "
    "Para acompanhar a continuidade do atendimento, consulte o processo {numero_processo}."
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _filter_context():
    """Contexto compartilhado para filtros da lista."""
    return {
        "status_list":       StatusProcesso.objects.filter(ativo=True).order_by("ordem"),
        "predio_list":       Predio.objects.order_by("nome"),
        "tipo_ambiente_list": TipoAmbiente.objects.filter(ativo=True).order_by("nome"),
    }


def _status_requisicao_convertida_em_processo():
    status, _ = StatusRequisicao.objects.get_or_create(
        codigo=REQUISICAO_CONVERTIDA_PROCESSO_STATUS,
        defaults={
            "nome": REQUISICAO_CONVERTIDA_PROCESSO_STATUS,
            "mapeamento_situacao": "INATIVA",
            "ordem": 99,
            "ativa": True,
        },
    )
    needs_update = False
    if status.nome != REQUISICAO_CONVERTIDA_PROCESSO_STATUS:
        status.nome = REQUISICAO_CONVERTIDA_PROCESSO_STATUS
        needs_update = True
    if status.mapeamento_situacao != "INATIVA":
        status.mapeamento_situacao = "INATIVA"
        needs_update = True
    if not status.ativa:
        status.ativa = True
        needs_update = True
    if needs_update:
        status.save()
    return status


def _mensagem_requisicao_convertida_em_processo(processo):
    return REQUISICAO_CONVERTIDA_PROCESSO_MENSAGEM.format(
        numero_processo=processo.numero_processo or "cadastrado"
    )


def _marcar_requisicoes_convertidas_em_processo(requisicoes, processo, user):
    status_convertida = _status_requisicao_convertida_em_processo()
    mensagem = _mensagem_requisicao_convertida_em_processo(processo)
    hoje = timezone.localdate()
    for requisicao in requisicoes:
        requisicao.status_sipac = status_convertida
        requisicao.status_fluxo = REQUISICAO_CONVERTIDA_PROCESSO_STATUS
        requisicao.save(update_fields=[
            "status_sipac",
            "status_fluxo",
            "situacao_requisicao",
            "dias_para_execucao",
            "atualizado_em",
        ])
        if not AcompanhamentoRequisicao.objects.filter(
            requisicao=requisicao,
            atualizacao_situacao=mensagem,
        ).exists():
            AcompanhamentoRequisicao.objects.create(
                requisicao=requisicao,
                data=hoje,
                atualizacao_situacao=mensagem,
                usuario=user if user.is_authenticated else None,
            )


def _apply_filters(qs, q):
    """Aplica os parâmetros GET como filtros ao queryset de Processo."""
    if q.get("busca"):
        termo = q["busca"].strip()
        qs = qs.filter(numero_processo__icontains=termo) | qs.filter(assunto__icontains=termo)
    if q.get("status"):
        qs = qs.filter(status__id=q["status"])
    if q.get("predio"):
        qs = qs.filter(predio__id=q["predio"])
    if q.get("tipo_ambiente"):
        qs = qs.filter(tipo_ambiente__id=q["tipo_ambiente"])
    if q.get("unidade_origem"):
        qs = qs.filter(unidade_origem__icontains=q["unidade_origem"].strip())
    if q.get("interessado"):
        qs = qs.filter(interessados__nome__icontains=q["interessado"].strip())
    if q.get("az"):
        if q["az"] == "_vazio":
            qs = qs.filter(classificacao_az="")
        else:
            qs = qs.filter(classificacao_az__iexact=q["az"])
    return qs.distinct()


def _az_rank_expression():
    return Case(
        When(classificacao_az__iexact="A", then=Value(1)),
        When(classificacao_az__iexact="B", then=Value(2)),
        When(classificacao_az__iexact="C", then=Value(3)),
        When(classificacao_az__iexact="D", then=Value(4)),
        When(classificacao_az__iexact="E", then=Value(5)),
        default=Value(99),
        output_field=IntegerField(),
    )


def _page_querystring(params, page_number):
    page_params = params.copy()
    page_params["page"] = str(page_number)
    return page_params.urlencode()


def _pagination_pages(page_obj):
    current_page = page_obj.number
    total_pages = page_obj.paginator.num_pages
    visible_pages = set()
    for page_number in range(1, total_pages + 1):
        near_start = page_number <= PROCESSOS_PAGINATION_EDGE_PAGES
        near_end = page_number > total_pages - PROCESSOS_PAGINATION_EDGE_PAGES
        near_current = abs(page_number - current_page) <= PROCESSOS_PAGINATION_WINDOW_PAGES
        if near_start or near_end or near_current:
            visible_pages.add(page_number)

    pages = []
    previous_page = 0
    for page_number in sorted(visible_pages):
        if previous_page and page_number - previous_page > 1:
            pages.append({"ellipsis": True})
        pages.append(
            {
                "number": page_number,
                "current": page_number == current_page,
                "ellipsis": False,
            }
        )
        previous_page = page_number
    return pages


# ── Lista ─────────────────────────────────────────────────────────────────────

class ProcessosListaView(LoginRequiredMixin, ListView):
    model = Processo
    template_name = "processos/lista.html"
    context_object_name = "processos"
    paginate_by = None

    def get_queryset(self):
        qs = (
            Processo.objects
            .select_related("status", "predio", "tipo_ambiente")
            .order_by("-data_abertura", "numero_processo")
        )
        return _apply_filters(qs, self.request.GET)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_filter_context())
        ctx["total"] = self.get_queryset().count()
        ctx["filtros"] = self.request.GET
        return ctx


# ── Cadastro ──────────────────────────────────────────────────────────────────

class ProcessosCadastroPainelView(LoginRequiredMixin, TemplateView):
    template_name = "processos/cadastro_painel.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["metrics"] = {
            "total": Processo.objects.count(),
            "ativos": Processo.objects.filter(data_conclusao__isnull=True, data_arquivamento__isnull=True).count(),
            "executados": Processo.objects.filter(data_conclusao__isnull=False).count(),
            "arquivados": Processo.objects.filter(data_arquivamento__isnull=False).count(),
        }
        ctx["ultimos_processos"] = (
            Processo.objects
            .select_related("status", "predio")
            .order_by("-criado_em", "-data_abertura", "numero_processo")[:5]
        )
        return ctx


class ProcessoCadastroView(LoginRequiredMixin, CreateView):
    model = Processo
    form_class = ProcessoForm
    template_name = "processos/cadastro.html"
    success_url = reverse_lazy("processos:lista")

    def _get_encaminhamento_origem(self):
        encaminhamento_id = (
            self.request.POST.get("encaminhamento_diretor")
            or self.request.GET.get("encaminhamento")
            or ""
        )
        if not str(encaminhamento_id).isdigit():
            return None
        return get_object_or_404(
            EncaminhamentoDiretor.objects.prefetch_related("requisicoes"),
            pk=encaminhamento_id,
            tipo=EncaminhamentoDiretor.Tipo.ABRIR_PROCESSO,
        )

    def _get_interessado_formset(self):
        kwargs = {"instance": getattr(self, "object", None)}
        if self.request.method in {"POST", "PUT"}:
            kwargs["data"] = self.request.POST
        return InteressadoProcessoFormSet(**kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("interessado_formset", self._get_interessado_formset())
        ctx["encaminhamento_origem"] = self._get_encaminhamento_origem()
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        interessado_formset = self._get_interessado_formset()
        if form.is_valid() and interessado_formset.is_valid():
            return self._forms_valid(form, interessado_formset)
        messages.error(self.request, "Corrija os erros abaixo antes de salvar.")
        return self.render_to_response(
            self.get_context_data(form=form, interessado_formset=interessado_formset)
        )

    def _forms_valid(self, form, interessado_formset):
        encaminhamento_origem = self._get_encaminhamento_origem()
        with transaction.atomic():
            self.object = form.save(commit=False)
            if encaminhamento_origem:
                self.object.encaminhamento_diretor = encaminhamento_origem
            self.object.save()
            form.save_m2m()
            if encaminhamento_origem:
                requisicoes_convertidas = list(encaminhamento_origem.requisicoes.all())
                self.object.requisicoes.add(*requisicoes_convertidas)
                _marcar_requisicoes_convertidas_em_processo(
                    requisicoes_convertidas,
                    self.object,
                    self.request.user,
                )
            interessado_formset.instance = self.object
            interessado_formset.save()
        messages.success(self.request, f"Processo {self.object.numero_processo} cadastrado com sucesso.")
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        messages.error(self.request, "Corrija os erros abaixo antes de salvar.")
        return super().form_invalid(form)


# ── Edição ────────────────────────────────────────────────────────────────────

class ProcessoEdicaoView(LoginRequiredMixin, UpdateView):
    model = Processo
    form_class = ProcessoForm
    template_name = "processos/cadastro.html"

    def get_success_url(self):
        return reverse_lazy("processos:detalhe", kwargs={"pk": self.object.pk})

    def _get_interessado_formset(self):
        kwargs = {"instance": self.object}
        if self.request.method in {"POST", "PUT"}:
            kwargs["data"] = self.request.POST
        return InteressadoProcessoFormSet(**kwargs)

    def _acompanhamento_qs(self):
        return AcompanhamentoProcesso.objects.filter(
            processo=self.object
        ).select_related("usuario").order_by("data", "criado_em", "pk")

    def _get_acompanhamento_formset(self):
        kwargs = {"instance": self.object, "queryset": self._acompanhamento_qs()}
        if self.request.method in {"POST", "PUT"}:
            kwargs["data"] = self.request.POST
        return AcompanhamentoProcessoFormSet(**kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("interessado_formset", self._get_interessado_formset())
        ctx.setdefault("acompanhamento_formset", self._get_acompanhamento_formset())
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        interessado_formset = self._get_interessado_formset()
        acompanhamento_formset = self._get_acompanhamento_formset()
        if form.is_valid() and interessado_formset.is_valid() and acompanhamento_formset.is_valid():
            return self._forms_valid(form, interessado_formset, acompanhamento_formset)
        return self.render_to_response(
            self.get_context_data(
                form=form,
                interessado_formset=interessado_formset,
                acompanhamento_formset=acompanhamento_formset,
            )
        )

    def _forms_valid(self, form, interessado_formset, acompanhamento_formset):
        saving_comment = "save_acompanhamento" in self.request.POST
        with transaction.atomic():
            self.object = form.save()
            interessado_formset.instance = self.object
            interessado_formset.save()
            acompanhamento_formset.instance = self.object
            for acomp in acompanhamento_formset.save(commit=False):
                is_new = acomp.pk is None
                acomp.processo = self.object
                if is_new and self.request.user.is_authenticated:
                    acomp.usuario = self.request.user
                acomp.save()
        if saving_comment:
            url = reverse("processos:edicao", kwargs={"pk": self.object.pk})
            return redirect(f"{url}#acompanhamento-section")
        messages.success(self.request, f"Processo {self.object.numero_processo} atualizado.")
        return redirect(self.get_success_url())


# ── Detalhe ───────────────────────────────────────────────────────────────────

class ProcessoDetalheView(LoginRequiredMixin, DetailView):
    model = Processo
    template_name = "processos/detalhe.html"
    context_object_name = "processo"

    def get_queryset(self):
        return (
            Processo.objects
            .select_related("status", "gerencia", "situacao_sipac", "servico", "predio", "empresa")
            .prefetch_related("solicitantes", "interessados", "orcamentos__orcamento_empenhos__empenho", "orcamentos__itens", "orcamentos__ajustes", "requisicoes")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        return ctx


# ── Orçamento CRUD (HTMX) ─────────────────────────────────────────────────────

def _orcamento_full_modal_ctx(processo, orc):
    """Monta o contexto completo para o modal de orçamento (metadados + itens)."""
    return {
        "processo": processo,
        "orcamento": orc,
        "status_choices": Orcamento.Status.choices,
        **orc.get_itens_com_ajustes(),
    }


@login_required
@require_http_methods(["GET", "POST"])
def orcamento_edit(request, processo_pk, orcamento_pk):
    """GET: abre modal completo de edição; POST: salva metadados e retorna modal atualizado."""
    from decimal import Decimal, InvalidOperation
    from datetime import date as date_type
    processo = get_object_or_404(Processo, pk=processo_pk)
    orc = get_object_or_404(Orcamento, pk=orcamento_pk, processo=processo)

    if request.method == "GET":
        return render(request, "processos/_orcamento_full_modal.html",
                      _orcamento_full_modal_ctx(processo, orc))

    descricao = request.POST.get("descricao", "").strip()
    valor_raw = request.POST.get("valor", "").replace(".", "").replace(",", ".").strip()
    status    = request.POST.get("status", Orcamento.Status.PENDENTE)
    data_str  = request.POST.get("data_emissao", "").strip()

    try:
        valor = Decimal(valor_raw) if valor_raw else None
    except InvalidOperation:
        valor = None
    try:
        data_emissao = date_type.fromisoformat(data_str) if data_str else None
    except ValueError:
        data_emissao = None

    orc.descricao    = descricao
    orc.status       = status
    orc.data_emissao = data_emissao
    if valor is not None:
        orc.valor = valor
    orc.save()
    orc.refresh_from_db()
    return render(request, "processos/_orcamento_full_modal.html",
                  _orcamento_full_modal_ctx(processo, orc))


@login_required
@require_http_methods(["GET", "POST"])
def orcamento_add(request, processo_pk):
    """GET: modal de criação; POST: cria orçamento e abre modal completo com itens."""
    from decimal import Decimal, InvalidOperation
    from datetime import date as date_type
    processo = get_object_or_404(Processo, pk=processo_pk)

    if request.method == "GET":
        return render(request, "processos/_orcamento_new_modal.html", {
            "processo": processo,
            "status_choices": Orcamento.Status.choices,
        })

    descricao = request.POST.get("descricao", "").strip()
    valor_raw = request.POST.get("valor", "").replace(".", "").replace(",", ".").strip()
    status    = request.POST.get("status", Orcamento.Status.PENDENTE)
    data_str  = request.POST.get("data_emissao", "").strip()

    try:
        valor = Decimal(valor_raw) if valor_raw else None
    except InvalidOperation:
        valor = None
    try:
        data_emissao = date_type.fromisoformat(data_str) if data_str else None
    except ValueError:
        data_emissao = None

    ultimo = processo.orcamentos.order_by("-numero_sequencial").first()
    orc = Orcamento.objects.create(
        processo=processo,
        descricao=descricao,
        valor=valor,
        status=status,
        data_emissao=data_emissao,
        numero_sequencial=(ultimo.numero_sequencial + 1) if ultimo else 1,
    )
    return render(request, "processos/_orcamento_full_modal.html",
                  _orcamento_full_modal_ctx(processo, orc))


def orcamento_delete(request, processo_pk, orcamento_pk):
    """POST: remove orçamento do processo."""
    orc = get_object_or_404(Orcamento, pk=orcamento_pk, processo_id=processo_pk)
    if request.method == "POST":
        orc.delete()
        messages.success(request, "Orçamento removido.")
    return redirect(reverse("processos:detalhe", kwargs={"pk": processo_pk}))


# ── Priorização A-Z ───────────────────────────────────────────────────────────

class PriorizacaoAZView(LoginRequiredMixin, ListView):
    model = Processo
    template_name = "processos/priorizacao_az.html"
    context_object_name = "processos"

    def get_queryset(self):
        qs = (
            Processo.objects
            .filter(status__ativo=True)
            .exclude(situacao_sipac__nome__iexact="ARQUIVADO")
            .select_related("status", "situacao_sipac", "predio", "tipo_ambiente")
            .annotate(_az_rank=_az_rank_expression())
            .order_by("_az_rank", "-data_abertura")
        )
        return _apply_filters(qs, self.request.GET)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_filter_context())
        ctx["filtros"] = self.request.GET
        return ctx


def priorizacao_az_update(request, pk):
    """HTMX: salva a classificacao A-Z e retorna a celula atualizada."""
    processo = get_object_or_404(Processo, pk=pk)

    if request.method == "POST":
        val = request.POST.get("classificacao_az", "").upper().strip()
        if val not in {"", "A", "B", "C", "D", "E"}:
            return HttpResponse('<span class="text-danger small">Valor invalido</span>', status=422)
        processo.classificacao_az = val
        processo.save(update_fields=["classificacao_az", "atualizado_em"])

    return render(request, "processos/_priorizacao_az_cell.html", {"proc": processo})


# ── Painel de Processos ───────────────────────────────────────────────────────

def _processos_panel_base_queryset():
    return (
        Processo.objects
        .select_related("status", "situacao_sipac", "predio", "tipo_ambiente", "empresa")
        .annotate(_az_rank=_az_rank_expression())
    )


def _processos_panel_filtered_queryset(request):
    qs = _apply_filters(_processos_panel_base_queryset(), request.GET)
    if request.GET.get("situacao"):
        qs = qs.filter(situacao_sipac_id=request.GET["situacao"])
    if request.GET.get("empenho"):
        qs = qs.filter(orcamentos__orcamento_empenhos__empenho_id=request.GET["empenho"])
    return qs.distinct()


def _processos_panel_options():
    return {
        "status_list": StatusProcesso.objects.filter(ativo=True).order_by("ordem", "nome"),
        "situacao_list": SituacaoSIPAC.objects.filter(ativa=True).order_by("nome"),
        "predio_list": Predio.objects.filter(processos__isnull=False).distinct().order_by("nome"),
        "empenho_list": (
            Empenho.objects
            .filter(orcamento_empenhos__orcamento__processo__isnull=False)
            .distinct()
            .order_by("nota_empenho")
        ),
    }


def _processos_panel_empenho_rows(process_ids):
    from decimal import Decimal

    if not process_ids:
        return []
    vinculos = OrcamentoEmpenho.objects.filter(orcamento__processo_id__in=process_ids)
    empenho_ids = list(vinculos.values_list("empenho_id", flat=True).distinct())
    if not empenho_ids:
        return []

    valores_nota = dict(
        MovimentacaoEmpenho.objects
        .filter(empenho_id__in=empenho_ids)
        .values("empenho_id")
        .annotate(total=Sum("valor"))
        .values_list("empenho_id", "total")
    )
    valores_alocados = dict(
        vinculos
        .values("empenho_id")
        .annotate(total=Sum("valor_alocado"))
        .values_list("empenho_id", "total")
    )

    rows = []
    for empenho in Empenho.objects.filter(pk__in=empenho_ids).select_related("empresa").order_by("nota_empenho"):
        valor_nota = valores_nota.get(empenho.pk) or Decimal("0")
        valor_orcado = valores_alocados.get(empenho.pk) or Decimal("0")
        rows.append({
            "nota": empenho.nota_empenho,
            "empresa": empenho.empresa.nome if empenho.empresa else "",
            "valor_nota": valor_nota,
            "orcamentos": valor_orcado,
            "saldo": valor_nota - valor_orcado,
        })
    return rows


def _processos_panel_context(request):
    from decimal import Decimal

    today = timezone.localdate()
    qs = _processos_panel_filtered_queryset(request)
    process_ids = list(qs.values_list("pk", flat=True))
    total_processos = len(process_ids)

    orcamentos = Orcamento.objects.filter(processo_id__in=process_ids)
    total_orcado = orcamentos.aggregate(total=Sum("valor"))["total"] or Decimal("0")
    total_orcado_aprovado = (
        orcamentos
        .filter(status=Orcamento.Status.APROVADO)
        .aggregate(total=Sum("valor"))["total"]
        or Decimal("0")
    )
    total_empenhado = (
        OrcamentoEmpenho.objects
        .filter(orcamento__processo_id__in=process_ids)
        .aggregate(total=Sum("valor_alocado"))["total"]
        or Decimal("0")
    )
    orcamentados = orcamentos.values("processo_id").distinct().count()
    sem_orcamento = max(total_processos - orcamentados, 0)

    executados_filter = (
        Q(data_conclusao__isnull=False)
        | Q(status__nome__icontains="Serviço Realizado")
        | Q(status__nome__icontains="Servico Realizado")
    )
    executados = qs.filter(executados_filter).count()
    arquivados = qs.filter(situacao_sipac__nome__iexact="ARQUIVADO").count()
    ativos = max(total_processos - arquivados, 0)
    ultima_atualizacao = qs.aggregate(data=Max("atualizado_em"))["data"]

    status_rows = list(
        qs.values("status__codigo", "status__nome", "status__ordem")
        .annotate(total=Count("pk", distinct=True), orcamento=Sum("orcamentos__valor"))
        .order_by("status__ordem", "status__nome")
    )
    max_status_total = max([row["total"] for row in status_rows] or [0])
    for row in status_rows:
        row["label"] = row["status__nome"] or "Sem status"
        row["orcamento"] = row["orcamento"] or Decimal("0")
        row["percent"] = int((row["total"] / max_status_total) * 100) if max_status_total else 0

    predio_rows = list(
        qs.values("predio__nome")
        .annotate(total=Count("pk", distinct=True))
        .order_by("-total", "predio__nome")[:12]
    )
    max_predio_total = max([row["total"] for row in predio_rows] or [0])
    for row in predio_rows:
        row["label"] = row["predio__nome"] or "Sem prédio"
        row["percent"] = int((row["total"] / max_predio_total) * 100) if max_predio_total else 0

    map_rows = []
    for row in (
        qs.exclude(predio__latitude__isnull=True)
        .exclude(predio__longitude__isnull=True)
        .values("predio__nome", "predio__latitude", "predio__longitude")
        .annotate(total=Count("pk", distinct=True))
        .order_by("-total", "predio__nome")
    ):
        map_rows.append({
            "label": row["predio__nome"] or "Sem predio",
            "latitude": float(row["predio__latitude"]),
            "longitude": float(row["predio__longitude"]),
            "total": row["total"],
        })

    active_qs = qs.exclude(situacao_sipac__nome__iexact="ARQUIVADO")
    az_rows = []
    for letter in ["A", "B", "C", "D", "E"]:
        az_rows.append({"label": letter, "total": active_qs.filter(classificacao_az__iexact=letter).count()})
    az_rows.append({"label": "Sem A-Z", "total": active_qs.filter(classificacao_az="").count()})
    az_active_total = active_qs.count()

    annual_flow_map = {}
    for item in qs.values("data_abertura", "data_os", "data_conclusao"):
        opened = item["data_abertura"]
        if opened:
            bucket = annual_flow_map.setdefault(opened.year, {"aberturas": 0, "os": 0, "conclusoes": 0})
            bucket["aberturas"] += 1
        os_date = item["data_os"]
        if os_date:
            bucket = annual_flow_map.setdefault(os_date.year, {"aberturas": 0, "os": 0, "conclusoes": 0})
            bucket["os"] += 1
        concluded = item["data_conclusao"]
        if concluded:
            bucket = annual_flow_map.setdefault(concluded.year, {"aberturas": 0, "os": 0, "conclusoes": 0})
            bucket["conclusoes"] += 1
    annual_flow_years = sorted(annual_flow_map)
    annual_flow = {
        "labels": [str(year) for year in annual_flow_years],
        "aberturas": [annual_flow_map[year]["aberturas"] for year in annual_flow_years],
        "os": [annual_flow_map[year]["os"] for year in annual_flow_years],
        "conclusoes": [annual_flow_map[year]["conclusoes"] for year in annual_flow_years],
    }

    oldest_active = []
    for proc in (
        qs.exclude(situacao_sipac__nome__iexact="ARQUIVADO")
        .filter(data_conclusao__isnull=True, data_abertura__isnull=False)
        .order_by("data_abertura", "numero_processo")[:10]
    ):
        oldest_active.append({
            "processo": proc,
            "dias": max((today - proc.data_abertura).days, 0),
        })

    # ── Itens de orçamento: montante por tipo de serviço ──────────────────────
    servico_rows = list(
        ItemOrcamento.objects
        .filter(orcamento__processo_id__in=process_ids, valor__isnull=False)
        .annotate(tipo=Upper(Trim("descricao")))
        .values("tipo")
        .annotate(total_valor=Sum("valor"), qtde=Count("pk"))
        .order_by("-total_valor")[:20]
    )
    for row in servico_rows:
        # Converte para Title Case para exibição legível
        row["label"] = row["tipo"].title() if row["tipo"] else "Sem descrição"

    chart_data = {
        "status": {
            "labels": [row["label"] for row in status_rows],
            "processos": [row["total"] for row in status_rows],
        },
        "predios": {
            "labels": [row["label"] for row in predio_rows],
            "quantidades": [row["total"] for row in predio_rows],
        },
        "az": {
            "labels": [row["label"] for row in az_rows] + ["Total"],
            "quantidades": [row["total"] for row in az_rows] + [az_active_total],
            "total": az_active_total,
        },
        "map": {
            "points": map_rows,
        },
        "servicos": {
            "labels": [row["label"] for row in servico_rows],
            "valores": [float(row["total_valor"]) for row in servico_rows],
            "qtdes": [row["qtde"] for row in servico_rows],
        },
        "annual_flow": annual_flow,
    }

    return {
        "today": today,
        "filtros": request.GET,
        "total_processos": total_processos,
        "ativos": ativos,
        "arquivados": arquivados,
        "sem_orcamento": sem_orcamento,
        "orcamentados": orcamentados,
        "executados": executados,
        "total_orcado": total_orcado,
        "total_orcado_aprovado": total_orcado_aprovado,
        "total_empenhado": total_empenhado,
        "ultima_atualizacao": ultima_atualizacao,
        "status_rows": status_rows,
        "predio_rows": predio_rows,
        "map_rows": map_rows,
        "az_rows": az_rows,
        "az_active_total": az_active_total,
        "empenho_rows": _processos_panel_empenho_rows(process_ids),
        "oldest_active": oldest_active,
        "chart_data": chart_data,
        **_processos_panel_options(),
    }


class PainelProcessosView(TemplateView):
    template_name = "processos/painel_controle.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_processos_panel_context(self.request))
        return ctx


# ── Painel Público de Processos ───────────────────────────────────────────────

@require_http_methods(["GET"])
def public_consulta_processos(request):
    """HTMX partial: tabela pública de processos (sem autenticação)."""
    qs = (
        Processo.objects
        .select_related("status", "predio")
        .prefetch_related("interessados")
        .annotate(primeiro_interessado=Min("interessados__nome"))
    )
    busca = request.GET.get("busca", "").strip()
    if busca:
        qs = qs.filter(Q(numero_processo__icontains=busca) | Q(assunto__icontains=busca))

    interessado = request.GET.get("interessado", "").strip()
    if interessado:
        qs = qs.filter(interessados__nome__icontains=interessado)

    status = request.GET.get("status", "").strip()
    if status.isdigit():
        qs = qs.filter(status_id=status)

    predio = request.GET.get("predio", "").strip()
    if predio.isdigit():
        qs = qs.filter(predio_id=predio)

    unidade_origem = request.GET.get("unidade_origem", "").strip()
    if unidade_origem:
        qs = qs.filter(unidade_origem__icontains=unidade_origem)

    az = request.GET.get("az", "").strip()
    if az:
        if az == "_vazio":
            qs = qs.filter(classificacao_az="")
        else:
            qs = qs.filter(classificacao_az__iexact=az)

    sort_fields = {
        "processo": ("numero_processo", "-data_abertura"),
        "assunto": ("assunto", "predio__nome"),
        "interessados": ("primeiro_interessado", "numero_processo"),
        "status": ("status__nome", "numero_processo"),
        "unidade": ("unidade_origem", "numero_processo"),
    }
    current_sort = request.GET.get("sort", "processo")
    current_dir = request.GET.get("dir", "asc")
    if current_sort not in sort_fields:
        current_sort = "processo"
    if current_dir not in {"asc", "desc"}:
        current_dir = "asc"

    order_fields = sort_fields[current_sort]
    if current_dir == "desc":
        order_fields = tuple("-" + field.lstrip("-") if not field.startswith("-") else field[1:] for field in order_fields)
    qs = qs.order_by(*order_fields).distinct()
    total_processos = qs.count()
    paginator = Paginator(qs, PROCESSOS_HOME_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    pagination_params = request.GET.copy()
    pagination_params.pop("page", None)
    pagination_pages = _pagination_pages(page_obj)
    for page in pagination_pages:
        if not page["ellipsis"]:
            page["querystring"] = _page_querystring(pagination_params, page["number"])

    sort_links = {}
    for key in sort_fields:
        next_dir = "desc" if key == current_sort and current_dir == "asc" else "asc"
        params = pagination_params.copy()
        params["sort"] = key
        params["dir"] = next_dir
        sort_links[key] = {
            "active": key == current_sort,
            "direction": current_dir if key == current_sort else "",
            "querystring": params.urlencode(),
        }

    return render(request, "processos/_public_consulta_processos.html", {
        "page_obj": page_obj,
        "processos": page_obj.object_list,
        "busca": busca,
        "sort_links": sort_links,
        "total_processos": total_processos,
        "pagination_pages": pagination_pages,
        "previous_page_querystring": (
            _page_querystring(pagination_params, page_obj.previous_page_number())
            if page_obj.has_previous()
            else ""
        ),
        "next_page_querystring": (
            _page_querystring(pagination_params, page_obj.next_page_number())
            if page_obj.has_next()
            else ""
        ),
        "status_list": StatusProcesso.objects.filter(processos__isnull=False).distinct().order_by("ordem", "nome"),
        "predio_list": Predio.objects.filter(processos__isnull=False).distinct().order_by("nome"),
        "unidade_list": (
            Processo.objects
            .exclude(unidade_origem="")
            .values_list("unidade_origem", flat=True)
            .distinct()
            .order_by("unidade_origem")[:80]
        ),
        "az_options": ["A", "B", "C", "D", "E"],
    })


@require_http_methods(["GET"])
def public_lista_processos(request):
    """Consulta pública de processos com filtros básicos."""
    qs = (
        Processo.objects
        .select_related("status", "predio")
        .order_by("-data_abertura", "numero_processo")
    )
    qs = _apply_filters(qs, request.GET)
    filtros = {
        "busca":   request.GET.get("busca", ""),
        "status":  request.GET.get("status", ""),
        "predio":  request.GET.get("predio", ""),
        "az":      request.GET.get("az", ""),
    }
    return render(request, "processos/public_lista.html", {
        "processos":   qs[:300],
        "filtros":     filtros,
        "status_list": StatusProcesso.objects.filter(ativo=True).order_by("ordem", "nome"),
        "predio_list": Predio.objects.filter(processos__isnull=False).distinct().order_by("nome"),
        "tem_filtro":  any(filtros.values()),
    })


def public_processos_metrics():
    """Retorna dict de métricas de processos para o painel público."""
    from django.db.models import Sum
    total = Processo.objects.count()
    ativos = Processo.objects.filter(data_conclusao__isnull=True, data_arquivamento__isnull=True).count()
    executados = Processo.objects.filter(data_conclusao__isnull=False).count()
    from .models import Orcamento
    investimento = (
        Orcamento.objects
        .filter(status=Orcamento.Status.APROVADO, valor__isnull=False)
        .aggregate(total=Sum("valor"))["total"] or 0
    )
    return {
        "enviados": total,
        "ativos": ativos,
        "executados": executados,
        "investimento": investimento,
    }


# ── Página pública de Processo ────────────────────────────────────────────────

def montar_timeline(processo):
    """Monta lista cronológica de eventos a partir das datas do processo."""
    eventos = []
    if processo.data_abertura:
        eventos.append({"data": processo.data_abertura, "texto": "Processo aberto", "atual": False})
    if processo.data_os:
        eventos.append({"data": processo.data_os, "texto": "Ordem de serviço emitida", "atual": False})
    if processo.data_conclusao:
        eventos.append({"data": processo.data_conclusao, "texto": "Serviço concluído", "atual": False})
    if processo.data_arquivamento:
        eventos.append({"data": processo.data_arquivamento, "texto": "Processo arquivado", "atual": False})
    eventos = sorted(eventos, key=lambda e: e["data"])
    # Marca o último evento como atual
    if eventos:
        eventos[-1]["atual"] = True
    return eventos


class ProcessoPublicoDetalheView(DetailView):
    """Página pública (sem login) de detalhes de um Processo."""
    model = Processo
    template_name = "processos/detalhe_publico.html"
    context_object_name = "processo"

    def get_queryset(self):
        # Processos APENSADOS não são exibidos publicamente
        return (
            Processo.objects
            .exclude(situacao_sipac__nome="APENSADO")
            .select_related(
                "status", "situacao_sipac", "predio", "tipo_ambiente",
                "empresa", "gerencia", "servico",
            )
            .prefetch_related("orcamentos", "requisicoes", "interessados")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        processo = self.object

        ctx["orcamentos_publicos"] = processo.orcamentos.all().order_by("numero_sequencial")

        # Total orçado público
        from decimal import Decimal
        ctx["total_orcado"] = sum(
            (o.valor for o in ctx["orcamentos_publicos"] if o.valor),
            Decimal("0.00"),
        )

        # Requisições de origem (dados mínimos para o público)
        ctx["requisicoes_origem"] = processo.requisicoes.values(
            "id", "codigo", "assunto"
        )

        # Timeline derivada das datas
        ctx["timeline"] = montar_timeline(processo)

        return ctx


# ── Exclusão individual e em lote ────────────────────────────────────────────

@require_http_methods(["POST"])
def processo_delete(request, pk):
    """POST: exclui um processo."""
    processo = get_object_or_404(Processo, pk=pk)
    numero = processo.numero_processo
    processo.delete()
    messages.success(request, f"Processo {numero} excluído.")
    return redirect(reverse("processos:lista"))


@require_http_methods(["POST"])
def processos_bulk_delete(request):
    """POST: exclui múltiplos processos selecionados."""
    ids = request.POST.getlist("processo_ids")
    if not ids:
        messages.warning(request, "Nenhum processo selecionado.")
        return redirect(reverse("processos:lista"))
    qs = Processo.objects.filter(pk__in=ids)
    count = qs.count()
    qs.delete()
    messages.success(request, f"{count} processo(s) excluído(s).")
    return redirect(reverse("processos:lista"))


# ── Importação em lote ───────────────────────────────────────────────────────

@require_http_methods(["GET"])
def modelo_planilha_processos(request):
    """GET: gera e retorna o modelo XLSX para preenchimento e importação."""
    from .importers import gerar_modelo_xlsx
    content = gerar_modelo_xlsx()
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="modelo_processos.xlsx"'
    return response


@require_http_methods(["POST"])
def importar_processos(request):
    """POST: recebe arquivo XLSX e importa processos em lote."""
    from .importers import ProcessoImporter
    arquivo = request.FILES.get("arquivo")
    if not arquivo:
        messages.error(request, "Nenhum arquivo enviado.")
        return redirect(reverse("processos:lista"))
    try:
        importer = ProcessoImporter()
        resultado = importer.import_file(arquivo)
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"Erro ao processar o arquivo: {exc}")
        return redirect(reverse("processos:lista"))

    criados    = resultado.get("criados", 0)
    atualizados = resultado.get("atualizados", 0)
    interessados_importados = resultado.get("interessados_importados", 0)
    interessados_ignorados = resultado.get("interessados_ignorados", 0)
    erros      = resultado.get("erros", [])
    erros.extend(resultado.get("interessados_erros", []))
    col_info   = resultado.get("colunas", [])

    # Colunas não mapeadas (aviso único)
    nao_mapeadas = [c["original"] for c in col_info if not c["mapeado"] and c["original"]]
    if nao_mapeadas:
        messages.warning(request, "Colunas não reconhecidas (ignoradas): " + ", ".join(nao_mapeadas))

    if erros:
        for erro in erros[:10]:
            messages.warning(request, erro)
        if len(erros) > 10:
            messages.warning(request, f"… e mais {len(erros) - 10} aviso(s) omitido(s).")

    if criados or atualizados or interessados_importados:
        partes = []
        if criados:
            partes.append(f"{criados} processo(s) criado(s)")
        if atualizados:
            partes.append(f"{atualizados} processo(s) atualizado(s)")
        if interessados_importados:
            partes.append(f"{interessados_importados} interessado(s) importado(s)")
        if interessados_ignorados:
            partes.append(f"{interessados_ignorados} interessado(s) ignorado(s)")
        messages.success(request, "Importação concluída: " + " e ".join(partes) + ".")
    elif not erros:
        messages.info(request, "Nenhum processo foi importado (planilha vazia ou sem dados novos).")

    return redirect(reverse("processos:lista"))


@require_http_methods(["POST"])
def diagnosticar_planilha(request):
    """POST: analisa planilha sem importar — retorna mapeamento de colunas."""
    from .importers import ProcessoImporter, HEADER_NAMES
    arquivo = request.FILES.get("arquivo")
    if not arquivo:
        return render(request, "processos/_diagnostico.html", {"erro": "Nenhum arquivo enviado."})
    try:
        importer = ProcessoImporter()
        wb = __import__("openpyxl").load_workbook(arquivo, read_only=True, data_only=True)
        sheet = next(
            (wb[name] for name in wb.sheetnames if name.strip().upper() == "PROCESSOS"),
            wb.active,
        )
        _, col_info = importer._sheet_to_dicts(sheet)
    except Exception as exc:
        return render(request, "processos/_diagnostico.html", {"erro": str(exc)})

    return render(request, "processos/_diagnostico.html", {
        "col_info": col_info,
        "campos_esperados": HEADER_NAMES,
        "mapeadas":    [c for c in col_info if c["mapeado"] and not c.get("ignorado") and c["original"]],
        "ignoradas":   [c for c in col_info if c.get("ignorado") and c["original"]],
        "nao_mapeadas":[c for c in col_info if not c["mapeado"] and c["original"]],
    })


# ── Empenhos ──────────────────────────────────────────────────────────────────

def _processo_empenho_context():
    from decimal import Decimal
    notas = (
        Empenho.objects
        .filter(modulo_origem='PROCESSO')
        .prefetch_related('reforcos', 'orcamento_empenhos__orcamento__processo')
        .order_by('-criado_em')
    )
    valor_total = sum((n.valor_total for n in notas), Decimal('0'))
    saldo_total = sum((n.saldo_processo for n in notas), Decimal('0'))
    total_pagos = (
        Processo.objects
        .filter(data_conclusao__isnull=False, orcamentos__orcamento_empenhos__isnull=False)
        .distinct()
        .count()
    )
    return {
        'notas': notas,
        'total_notas': notas.count(),
        'valor_total': valor_total,
        'saldo_total': saldo_total,
        'total_processos_pagos': total_pagos,
    }


class EmpenhoProcessosView(LoginRequiredMixin, ListView):
    model = Processo
    template_name = "processos/empenhos.html"
    context_object_name = "processos"

    def get_queryset(self):
        return Processo.objects.none()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_processo_empenho_context())
        return ctx


@login_required
def processo_nota_empenho_crud(request, pk=None):
    instance = get_object_or_404(Empenho, pk=pk, modulo_origem='PROCESSO') if pk else None

    if request.method == "POST":
        from decimal import Decimal, InvalidOperation
        numero    = request.POST.get("numero", "").strip()
        valor_str = request.POST.get("valor", "").strip()
        if "," in valor_str:
            valor_str = valor_str.replace(".", "").replace(",", ".")
        valor_str = valor_str.replace("R$", "").replace(" ", "")
        numero_processo = request.POST.get("numero_processo_sipac", "").strip()
        link_processo   = request.POST.get("link_processo_sipac", "").strip()
        empresa_pk      = request.POST.get("empresa", "").strip()
        empresa_obj     = Empresa.objects.filter(pk=empresa_pk).first() if empresa_pk else None

        if not numero or not valor_str:
            return HttpResponse("Número e Valor são obrigatórios.", status=400)
        try:
            valor = Decimal(valor_str)
        except InvalidOperation:
            return HttpResponse("Valor inválido.", status=400)

        if instance:
            instance.nota_empenho       = numero
            instance.numero_processo_sipac = numero_processo
            instance.link_processo_sipac   = link_processo
            instance.empresa               = empresa_obj
            instance.save()
            MovimentacaoEmpenho.objects.update_or_create(
                empenho=instance,
                tipo=MovimentacaoEmpenho.Tipo.VALOR_INICIAL,
                defaults={"valor": valor},
            )
        else:
            empenho = Empenho.objects.create(
                nota_empenho=numero,
                numero_processo_sipac=numero_processo,
                link_processo_sipac=link_processo,
                empresa=empresa_obj,
                modulo_origem='PROCESSO',
            )
            MovimentacaoEmpenho.objects.create(
                empenho=empenho,
                tipo=MovimentacaoEmpenho.Tipo.VALOR_INICIAL,
                valor=valor,
            )
        return render(request, "processos/_nota_empenho_rows.html", _processo_empenho_context())

    return render(request, "processos/_nota_empenho_form.html", {
        "instance": instance,
        "empresas_list": Empresa.objects.filter(ativa=True),
    })


@login_required
@require_http_methods(["POST", "DELETE"])
def processo_nota_empenho_delete(request, pk):
    nota = get_object_or_404(Empenho, pk=pk, modulo_origem='PROCESSO')
    nota.delete()
    return render(request, "processos/_nota_empenho_rows.html", _processo_empenho_context())


@login_required
def processo_nota_empenho_reforco(request, pk, reforco_pk=None):
    nota    = get_object_or_404(Empenho, pk=pk, modulo_origem='PROCESSO')
    reforco = get_object_or_404(MovimentacaoEmpenho, pk=reforco_pk, empenho=nota) if reforco_pk else None

    if request.method == "GET":
        return render(request, "processos/_nota_empenho_reforco_form.html", {
            "nota": nota, "reforco": reforco,
        })

    from decimal import Decimal, InvalidOperation
    valor_str = request.POST.get("valor_reforco", "").strip()
    if "," in valor_str:
        valor_str = valor_str.replace(".", "").replace(",", ".")
    valor_str = valor_str.replace("R$", "").replace(" ", "")
    if not valor_str:
        return HttpResponse("Informe o valor do reforço.", status=400)
    try:
        adicional = Decimal(valor_str)
        if adicional <= 0:
            return HttpResponse("O valor deve ser positivo.", status=400)
    except InvalidOperation:
        return HttpResponse("Valor inválido.", status=400)

    numero_sipac = request.POST.get("numero_processo_sipac", "").strip()
    descricao    = request.POST.get("descricao_reforco", "").strip()
    if reforco:
        reforco.valor                = adicional
        reforco.numero_processo_sipac = numero_sipac
        reforco.descricao            = descricao
        reforco.save()
    else:
        MovimentacaoEmpenho.objects.create(
            empenho=nota,
            tipo=MovimentacaoEmpenho.Tipo.REFORCO,
            valor=adicional,
            numero_processo_sipac=numero_sipac,
            descricao=descricao,
        )
    return render(request, "processos/_nota_empenho_rows.html", _processo_empenho_context())


@login_required
@require_http_methods(["POST", "DELETE"])
def processo_nota_empenho_reforco_delete(request, pk, reforco_pk):
    nota    = get_object_or_404(Empenho, pk=pk, modulo_origem='PROCESSO')
    reforco = get_object_or_404(MovimentacaoEmpenho, pk=reforco_pk, empenho=nota)
    reforco.delete()
    return render(request, "processos/_nota_empenho_rows.html", _processo_empenho_context())


# ── IA: extração de Orçamento via PDF ────────────────────────────────────────

@login_required
@require_http_methods(["GET", "POST"])
def orcamento_ia_extrair(request, processo_pk):
    """
    GET  → exibe modal de upload de PDF.
    POST step=upload → extrai texto do PDF, chama Claude, devolve formulário de confirmação.
    POST step=confirmar → salva o Orçamento e retorna script de reload.
    """
    import io
    import json
    from decimal import Decimal, InvalidOperation

    processo = get_object_or_404(Processo, pk=processo_pk)

    # ── GET: modal de upload ──────────────────────────────────────────────────
    if request.method == "GET":
        return render(request, "processos/_orcamento_ia_upload.html", {
            "processo": processo,
        })

    step = request.POST.get("step", "upload")

    # ── POST step=upload: lê PDF → IA → confirmação ───────────────────────────
    if step == "upload":
        import PyPDF2
        from groq import Groq
        from django.conf import settings

        pdf_file = request.FILES.get("pdf_file")
        if not pdf_file:
            return render(request, "processos/_orcamento_ia_upload.html", {
                "processo": processo,
                "erro": "Nenhum arquivo PDF foi enviado.",
            })

        # Extrai texto do PDF
        try:
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_file.read()))
            texto = "\n".join(
                (page.extract_text() or "") for page in reader.pages
            ).strip()
        except Exception as exc:
            return render(request, "processos/_orcamento_ia_upload.html", {
                "processo": processo,
                "erro": f"Não foi possível ler o PDF: {exc}",
            })

        if not texto:
            return render(request, "processos/_orcamento_ia_upload.html", {
                "processo": processo,
                "erro": "O PDF não contém texto extraível (pode ser uma imagem escaneada).",
            })

        api_key = getattr(settings, "GROQ_API_KEY", "")
        if not api_key:
            return render(request, "processos/_orcamento_ia_upload.html", {
                "processo": processo,
                "erro": "Chave de API da IA não configurada. Defina GROQ_API_KEY no arquivo .env.",
            })

        # Envia o texto (até 14000 chars ≈ 3500 tokens, seguro dentro do limite de 6000 TPM do Groq)
        trecho = texto[:14000]

        prompt = (
            "Você é um extrator de dados de planilhas orçamentárias de construção/manutenção civil.\n"
            "Analise o texto abaixo e extraia TODAS as informações solicitadas com precisão.\n\n"
            f"TEXTO DO PDF:\n{trecho}\n\n"
            "Retorne APENAS um objeto JSON válido (sem markdown, sem blocos ```, sem explicações) "
            "com exatamente estes campos:\n"
            '{\n'
            '  "descricao": "descrição do serviço — combine OBJETO e SERVIÇO separados por \\" - \\" se ambos existirem",\n'
            '  "valor": 12345.67,\n'
            '  "data_emissao": "YYYY-MM-DD ou null",\n'
            '  "numero_processo": "número SIPAC ex: 23074.061438/2020-41 ou null",\n'
            '  "nota_empenho": "código do empenho ex: 2021NE000248 ou null",\n'
            '  "itens": [\n'
            '    {"numero": "1.0", "descricao": "SERVIÇOS PRELIMINARES", "valor": 5609.93},\n'
            '    {"numero": "2.0", "descricao": "IMPERMEABILIZAÇÃO", "valor": 7839.62}\n'
            '  ],\n'
            '  "ajustes": [\n'
            '    {"rotulo": "Desconto", "percentual": -18.5},\n'
            '    {"rotulo": "BDI", "percentual": 25.0}\n'
            '  ]\n'
            '}\n\n'
            'REGRAS OBRIGATÓRIAS:\n'
            '1. "itens": extraia TODOS os grupos/itens numerados (1.0, 2.0, 3.0...) da planilha — '
            'não omita nenhum. Use apenas os valores BASE (coluna "Valor" antes de descontos/BDI). '
            'Ignore subitens (1.1, 1.2...). Se não encontrar itens numerados, use [].\n'
            '2. "valor": valor FINAL da planilha após todos os descontos e acréscimos. '
            'Se não encontrado, some os itens e aplique os ajustes.\n'
            '3. "ajustes": liste TODOS os percentuais de desconto (negativos) e acréscimo (positivos) '
            'na ordem em que são aplicados. Ex: BDI de 25% = 25.0. Se não houver, use [].\n'
            '4. "data_emissao": data de início ou emissão no formato YYYY-MM-DD. Null se não encontrada.\n'
            '5. Campos não encontrados: use null.\n'
            '6. Valores numéricos: use ponto como separador decimal (ex: 5609.93, não "5.609,93").'
        )

        try:
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                temperature=0.1,
            )
            content = response.choices[0].message.content.strip()
            # Remove markdown code fences se presentes
            if "```" in content:
                for part in content.split("```"):
                    stripped = part.lstrip("json").strip()
                    if stripped.startswith("{"):
                        content = stripped
                        break
            dados = json.loads(content)
        except json.JSONDecodeError:
            dados = {}
        except Exception as exc:
            return render(request, "processos/_orcamento_ia_upload.html", {
                "processo": processo,
                "erro": f"Erro ao processar com IA: {exc}",
            })

        empenhos = Empenho.objects.filter(modulo_origem="PROCESSO").order_by("nota_empenho")
        return render(request, "processos/_orcamento_ia_confirmacao.html", {
            "processo": processo,
            "dados": dados,
            "empenhos": empenhos,
        })

    # ── POST step=confirmar: salva o Orçamento ────────────────────────────────
    if step == "confirmar":
        from datetime import date as date_type

        descricao     = request.POST.get("descricao", "").strip()
        valor_raw     = request.POST.get("valor", "").replace(".", "").replace(",", ".").strip()
        data_str      = request.POST.get("data_emissao", "").strip()
        status        = request.POST.get("status", Orcamento.Status.PENDENTE)
        empenho_pk    = request.POST.get("empenho_pk", "").strip()

        try:
            valor = Decimal(valor_raw) if valor_raw else None
        except InvalidOperation:
            valor = None

        try:
            data_emissao = date_type.fromisoformat(data_str) if data_str else None
        except ValueError:
            data_emissao = None

        ultimo = processo.orcamentos.order_by("-numero_sequencial").first()
        numero_seq = (ultimo.numero_sequencial + 1) if ultimo else 1

        orc = Orcamento.objects.create(
            processo=processo,
            numero_sequencial=numero_seq,
            descricao=descricao,
            valor=valor,
            data_emissao=data_emissao,
            status=status,
        )

        if empenho_pk:
            empenho_obj = Empenho.objects.filter(
                pk=empenho_pk, modulo_origem="PROCESSO"
            ).first()
            if empenho_obj:
                OrcamentoEmpenho.objects.create(
                    orcamento=orc,
                    empenho=empenho_obj,
                    valor_alocado=valor,
                )

        # Salva ajustes extraídos pela IA (enviados como JSON)
        ajustes_json = request.POST.get("ajustes_json", "[]")
        try:
            ajustes_lista = json.loads(ajustes_json)
            for ordem, aj in enumerate(ajustes_lista, start=1):
                rotulo = str(aj.get("rotulo") or "").strip()
                perc   = aj.get("percentual")
                if perc is None:
                    continue
                try:
                    from decimal import Decimal as _D
                    AjusteOrcamento.objects.create(
                        orcamento=orc,
                        rotulo=rotulo,
                        percentual=_D(str(perc)),
                        ordem=ordem,
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # Salva itens extraídos pela IA (enviados como JSON)
        itens_json = request.POST.get("itens_json", "[]")
        try:
            itens_lista = json.loads(itens_json)
            for ordem, item in enumerate(itens_lista, start=1):
                desc = str(item.get("descricao") or "").strip()
                if not desc:
                    continue
                val_raw = item.get("valor")
                try:
                    val = Decimal(str(val_raw)) if val_raw is not None else None
                except Exception:
                    val = None
                ItemOrcamento.objects.create(
                    orcamento=orc,
                    numero=str(item.get("numero") or "").strip(),
                    descricao=desc,
                    valor=val,
                    ordem=ordem,
                )
        except Exception:
            pass  # itens são opcionais

        # Retorna script que fecha o modal e recarrega a página
        return HttpResponse(
            '<script>fecharOrcamentoIA(); window.location.reload();</script>'
        )

    return HttpResponse(status=400)


# ── Item / Ajuste de Orçamento CRUD (HTMX) ────────────────────────────────────

def _render_itens_partial(request, orc):
    """Renderiza o partial de itens com dados calculados (itens + ajustes encadeados).
    Auto-sincroniza orc.valor com o total final calculado sempre que há itens."""
    dados = orc.get_itens_com_ajustes()
    if dados['linhas'] and dados['valor_final']:
        Orcamento.objects.filter(pk=orc.pk).update(valor=dados['valor_final'])
        orc.valor = dados['valor_final']
    return render(request, "processos/_orcamento_itens.html", {"orcamento": orc, **dados})


@login_required
def orcamento_itens(request, orcamento_pk):
    """GET: partial com a lista de itens e ajustes de um orçamento."""
    orc = get_object_or_404(Orcamento, pk=orcamento_pk)
    return _render_itens_partial(request, orc)


@login_required
@require_http_methods(["GET", "POST"])
def orcamento_item_add(request, orcamento_pk):
    """GET: formulário inline; POST: cria item e retorna partial atualizado."""
    from decimal import Decimal, InvalidOperation
    from django.db.models import Max
    orc = get_object_or_404(Orcamento, pk=orcamento_pk)

    if request.method == "GET":
        return render(request, "processos/_orcamento_item_form.html", {
            "orcamento": orc, "item": None,
        })

    numero    = request.POST.get("numero", "").strip()
    descricao = request.POST.get("descricao", "").strip()
    valor_raw = request.POST.get("valor", "").replace(".", "").replace(",", ".").strip()
    if not descricao:
        return HttpResponse("Descrição é obrigatória.", status=400)
    try:
        val = Decimal(valor_raw) if valor_raw else None
    except InvalidOperation:
        val = None
    max_ordem = orc.itens.aggregate(m=Max("ordem"))["m"] or 0
    ItemOrcamento.objects.create(
        orcamento=orc, numero=numero, descricao=descricao, valor=val, ordem=max_ordem + 1
    )
    return _render_itens_partial(request, orc)


@login_required
@require_http_methods(["GET", "POST"])
def orcamento_item_edit(request, orcamento_pk, item_pk):
    """GET: formulário de edição; POST: salva e retorna partial atualizado."""
    from decimal import Decimal, InvalidOperation
    orc  = get_object_or_404(Orcamento, pk=orcamento_pk)
    item = get_object_or_404(ItemOrcamento, pk=item_pk, orcamento=orc)

    if request.method == "GET":
        return render(request, "processos/_orcamento_item_form.html", {
            "orcamento": orc, "item": item,
        })

    numero    = request.POST.get("numero", "").strip()
    descricao = request.POST.get("descricao", "").strip()
    valor_raw = request.POST.get("valor", "").replace(".", "").replace(",", ".").strip()
    if not descricao:
        return HttpResponse("Descrição é obrigatória.", status=400)
    try:
        val = Decimal(valor_raw) if valor_raw else None
    except InvalidOperation:
        val = None
    item.numero    = numero
    item.descricao = descricao
    item.valor     = val
    item.save()
    return _render_itens_partial(request, orc)


@login_required
@require_http_methods(["POST"])
def orcamento_item_delete(request, orcamento_pk, item_pk):
    """POST: exclui item e retorna partial atualizado."""
    orc  = get_object_or_404(Orcamento, pk=orcamento_pk)
    item = get_object_or_404(ItemOrcamento, pk=item_pk, orcamento=orc)
    item.delete()
    return _render_itens_partial(request, orc)


@login_required
@require_http_methods(["POST"])
def orcamento_ajuste_add(request, orcamento_pk):
    """POST: cria coluna de ajuste (desconto/acréscimo) e retorna partial atualizado."""
    from decimal import Decimal, InvalidOperation
    from django.db.models import Max
    orc = get_object_or_404(Orcamento, pk=orcamento_pk)
    rotulo      = request.POST.get("rotulo", "").strip()
    perc_raw    = request.POST.get("percentual", "").replace(",", ".").strip()
    if not perc_raw:
        return HttpResponse("Percentual é obrigatório.", status=400)
    try:
        perc = Decimal(perc_raw)
    except InvalidOperation:
        return HttpResponse("Percentual inválido.", status=400)
    max_ordem = orc.ajustes.aggregate(m=Max("ordem"))["m"] or 0
    AjusteOrcamento.objects.create(
        orcamento=orc, rotulo=rotulo, percentual=perc, ordem=max_ordem + 1
    )
    return _render_itens_partial(request, orc)


@login_required
@require_http_methods(["POST"])
def orcamento_ajuste_delete(request, orcamento_pk, ajuste_pk):
    """POST: remove coluna de ajuste e retorna partial atualizado."""
    orc    = get_object_or_404(Orcamento, pk=orcamento_pk)
    ajuste = get_object_or_404(AjusteOrcamento, pk=ajuste_pk, orcamento=orc)
    ajuste.delete()
    return _render_itens_partial(request, orc)
