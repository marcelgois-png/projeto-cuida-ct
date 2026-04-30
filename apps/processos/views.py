from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.models import (
    GerenciaSINFRA,
    ServicoProcesso,
    SituacaoSIPAC,
    StatusProcesso,
)

from .forms import OrcamentoForm, ProcessoForm
from .models import Orcamento, Processo


# ── helpers ───────────────────────────────────────────────────────────────────

def _filter_context():
    """Contexto compartilhado para filtros da lista."""
    return {
        "status_list": StatusProcesso.objects.filter(ativo=True).order_by("ordem"),
        "gerencia_list": GerenciaSINFRA.objects.filter(ativa=True).order_by("nome"),
        "situacao_list": SituacaoSIPAC.objects.filter(ativa=True).order_by("nome"),
        "servico_list": ServicoProcesso.objects.filter(ativo=True).order_by("ordem", "nome"),
    }


# ── Lista ─────────────────────────────────────────────────────────────────────

class ProcessosListaView(LoginRequiredMixin, ListView):
    model = Processo
    template_name = "processos/lista.html"
    context_object_name = "processos"
    paginate_by = 50

    def get_queryset(self):
        qs = (
            Processo.objects
            .select_related("status", "gerencia", "situacao_sipac", "servico", "predio")
            .order_by("-data_abertura", "numero_processo")
        )
        q = self.request.GET
        if q.get("busca"):
            termo = q["busca"].strip()
            qs = qs.filter(numero_processo__icontains=termo) | qs.filter(assunto__icontains=termo)
        if q.get("status"):
            qs = qs.filter(status__id=q["status"])
        if q.get("gerencia"):
            qs = qs.filter(gerencia__id=q["gerencia"])
        if q.get("situacao"):
            qs = qs.filter(situacao_sipac__id=q["situacao"])
        if q.get("servico"):
            qs = qs.filter(servico__id=q["servico"])
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(_filter_context())
        ctx["total"] = self.get_queryset().count()
        ctx["filtros"] = self.request.GET
        return ctx


# ── Cadastro ──────────────────────────────────────────────────────────────────

class ProcessoCadastroView(LoginRequiredMixin, CreateView):
    model = Processo
    form_class = ProcessoForm
    template_name = "processos/cadastro.html"
    success_url = reverse_lazy("processos:lista")

    def form_valid(self, form):
        messages.success(self.request, f"Processo {form.instance.numero_processo} cadastrado com sucesso.")
        return super().form_valid(form)

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

    def form_valid(self, form):
        messages.success(self.request, f"Processo {form.instance.numero_processo} atualizado.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Corrija os erros abaixo antes de salvar.")
        return super().form_invalid(form)


# ── Detalhe ───────────────────────────────────────────────────────────────────

class ProcessoDetalheView(LoginRequiredMixin, DetailView):
    model = Processo
    template_name = "processos/detalhe.html"
    context_object_name = "processo"

    def get_queryset(self):
        return (
            Processo.objects
            .select_related("status", "gerencia", "situacao_sipac", "servico", "predio", "empresa")
            .prefetch_related("solicitantes", "orcamentos__orcamento_empenhos__empenho", "requisicoes")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["orcamento_form"] = OrcamentoForm()
        return ctx


# ── Orçamento CRUD (HTMX) ─────────────────────────────────────────────────────

def orcamento_add(request, processo_pk):
    """POST: adiciona orçamento ao processo; retorna redirect para o detalhe."""
    processo = get_object_or_404(Processo, pk=processo_pk)
    if request.method == "POST":
        form = OrcamentoForm(request.POST, request.FILES)
        if form.is_valid():
            orc = form.save(commit=False)
            orc.processo = processo
            # Atribui número sequencial automático
            ultimo = processo.orcamentos.order_by("-numero_sequencial").first()
            orc.numero_sequencial = (ultimo.numero_sequencial + 1) if ultimo else 1
            orc.save()
            messages.success(request, f"Orçamento {orc.numero_sequencial} adicionado.")
        else:
            messages.error(request, "Erro ao salvar orçamento. Verifique os dados.")
    return redirect(reverse("processos:detalhe", kwargs={"pk": processo_pk}))


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
        return (
            Processo.objects
            .filter(status__ativo=True)
            .select_related("status", "gerencia", "predio")
            .order_by("classificacao_az", "-data_abertura")
        )


def priorizacao_az_update(request, pk):
    """HTMX GET → retorna form inline; POST → salva e retorna badge atualizado."""
    processo = get_object_or_404(Processo, pk=pk)

    if request.method == "GET" and request.GET.get("edit"):
        # Retorna mini-formulário inline
        url_post = reverse("processos:priorizacao-az-update", kwargs={"pk": pk})
        html = (
            f'<form hx-post="{url_post}" hx-target="#az-cell-{pk}" hx-swap="innerHTML"'
            f' class="d-flex align-items-center gap-1 justify-content-center">'
            f'<input type="hidden" name="csrfmiddlewaretoken"'
            f' value="{{{{ csrf_token }}}}">'
            f'<input name="classificacao_az" type="text" maxlength="1"'
            f' value="{processo.classificacao_az}"'
            f' style="width:2.2rem;text-align:center;text-transform:uppercase;'
            f'font-size:.9rem;padding:.1rem .2rem;" class="form-control form-control-sm">'
            f'<button type="submit" class="btn btn-xs btn-primary py-0 px-1"'
            f' style="background:#7A2632;border-color:#7A2632;">'
            f'<i class="bi bi-check-lg"></i></button>'
            f'</form>'
        )
        return HttpResponse(html)

    if request.method == "POST":
        from django.middleware.csrf import CsrfViewMiddleware
        val = request.POST.get("classificacao_az", "").upper().strip()
        if val and (len(val) != 1 or not val.isalpha()):
            return HttpResponse('<span class="text-danger small">Letra inválida</span>', status=422)
        processo.classificacao_az = val
        processo.save(update_fields=["classificacao_az", "atualizado_em"])

    badge = (
        f'<span class="az-badge-wrap" hx-get="{reverse("processos:priorizacao-az-update", kwargs={"pk": pk})}?edit=1"'
        f' hx-target="#az-cell-{pk}" hx-swap="innerHTML" style="cursor:pointer;" title="Clique para editar">'
        f'<span class="badge rounded-pill" style="background:#7A2632;min-width:1.8rem;">{processo.classificacao_az}</span>'
        f'</span>'
        if processo.classificacao_az
        else (
            f'<span class="az-badge-wrap" hx-get="{reverse("processos:priorizacao-az-update", kwargs={"pk": pk})}?edit=1"'
            f' hx-target="#az-cell-{pk}" hx-swap="innerHTML" style="cursor:pointer;" title="Clique para editar">'
            f'<span class="text-muted">—</span></span>'
        )
    )
    return HttpResponse(badge)


# ── Painel Público de Processos ───────────────────────────────────────────────

@require_http_methods(["GET"])
def public_consulta_processos(request):
    """HTMX partial: tabela pública de processos (sem autenticação)."""
    qs = (
        Processo.objects
        .select_related("status", "gerencia", "predio")
        .order_by("-data_abertura", "numero_processo")
    )
    busca = request.GET.get("busca", "").strip()
    if busca:
        qs = qs.filter(numero_processo__icontains=busca) | qs.filter(assunto__icontains=busca)
    return render(request, "processos/_public_consulta_processos.html", {
        "processos": qs[:100],
        "busca": busca,
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
            .prefetch_related("orcamentos", "requisicoes")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        processo = self.object

        # Orçamentos visíveis publicamente: apenas APROVADO
        ctx["orcamentos_publicos"] = processo.orcamentos.filter(
            status=Orcamento.Status.APROVADO
        ).order_by("numero_sequencial")

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


# ── Empenhos ──────────────────────────────────────────────────────────────────

class EmpenhoProcessosView(LoginRequiredMixin, ListView):
    model = Processo
    template_name = "processos/empenhos.html"
    context_object_name = "processos"

    def get_queryset(self):
        return (
            Processo.objects
            .prefetch_related("orcamentos__orcamento_empenhos__empenho")
            .filter(orcamentos__isnull=False)
            .distinct()
            .order_by("-data_abertura")
        )
