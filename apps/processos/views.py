from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.models import (
    GerenciaSINFRA,
    ServicoProcesso,
    SituacaoSIPAC,
    StatusProcesso,
)

from .forms import ProcessoForm
from .models import Processo


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
            .prefetch_related("solicitantes", "orcamentos", "requisicoes")
        )


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
