from __future__ import annotations

from django import forms

from apps.core.models import (
    GerenciaSINFRA,
    Predio,
    ServicoProcesso,
    SituacaoSIPAC,
    StatusProcesso,
    TipoAmbiente,
    Solicitante,
    Empresa,
)

from .models import Processo

DATE_INPUT_FORMAT = "%Y-%m-%d"
DATE_INPUT_FORMATS = [DATE_INPUT_FORMAT, "%d/%m/%Y"]


class ProcessoForm(forms.ModelForm):
    """Formulário de cadastro/edição de Processo."""

    data_abertura = forms.DateField(
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(format=DATE_INPUT_FORMAT, attrs={"type": "date"}),
        label="Data de abertura",
    )
    data_os = forms.DateField(
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(format=DATE_INPUT_FORMAT, attrs={"type": "date"}),
        label="Data da OS",
    )
    data_conclusao = forms.DateField(
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(format=DATE_INPUT_FORMAT, attrs={"type": "date"}),
        label="Data de conclusão",
    )
    data_arquivamento = forms.DateField(
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(format=DATE_INPUT_FORMAT, attrs={"type": "date"}),
        label="Data de arquivamento",
    )

    class Meta:
        model = Processo
        fields = [
            "numero_processo",
            "data_abertura",
            "data_os",
            "data_conclusao",
            "data_arquivamento",
            "assunto",
            "servico",
            "gerencia",
            "status",
            "situacao_sipac",
            "predio",
            "tipo_ambiente",
            "solicitantes",
            "empresa",
            "classificacao_az",
            "link_sipac",
            "observacao",
            "acompanhamento_ct",
        ]
        widgets = {
            "assunto": forms.Textarea(attrs={"rows": 3}),
            "observacao": forms.Textarea(attrs={"rows": 3}),
            "acompanhamento_ct": forms.Textarea(attrs={"rows": 4}),
            "solicitantes": forms.SelectMultiple(attrs={"size": 5}),
            "classificacao_az": forms.TextInput(attrs={"maxlength": 1, "style": "width:4rem;text-transform:uppercase"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ordenação dos querysets
        self.fields["status"].queryset = StatusProcesso.objects.filter(ativo=True).order_by("ordem")
        self.fields["gerencia"].queryset = GerenciaSINFRA.objects.filter(ativa=True).order_by("nome")
        self.fields["situacao_sipac"].queryset = SituacaoSIPAC.objects.filter(ativa=True).order_by("nome")
        self.fields["servico"].queryset = ServicoProcesso.objects.filter(ativo=True).order_by("ordem", "nome")
        self.fields["predio"].queryset = Predio.objects.order_by("nome")
        self.fields["tipo_ambiente"].queryset = TipoAmbiente.objects.order_by("nome")
        self.fields["solicitantes"].queryset = Solicitante.objects.order_by("nome")
        self.fields["empresa"].queryset = Empresa.objects.filter(ativa=True).order_by("nome")
        # Todos os campos FK/M2M são opcionais
        for name, field in self.fields.items():
            if hasattr(field, "queryset") and name != "numero_processo":
                field.required = False

    def clean_classificacao_az(self):
        val = self.cleaned_data.get("classificacao_az", "")
        if val:
            val = val.upper().strip()
            if len(val) > 1 or not val.isalpha():
                raise forms.ValidationError("Informe uma única letra (A–Z).")
        return val
