from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


# ── Stubs (Bloco C) — substituídos no Bloco D ─────────────────────────────────

class ProcessosListaView(LoginRequiredMixin, TemplateView):
    template_name = 'processos/lista.html'


class ProcessosCadastroView(LoginRequiredMixin, TemplateView):
    template_name = 'processos/cadastro.html'


class PriorizacaoAZView(LoginRequiredMixin, TemplateView):
    template_name = 'processos/priorizacao_az.html'


class EmpenhoProcessosView(LoginRequiredMixin, TemplateView):
    template_name = 'processos/empenhos.html'
