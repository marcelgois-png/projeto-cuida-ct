from __future__ import annotations

from django import forms
from django.forms import inlineformset_factory

from .domain import (
    clean_display_text,
    coerce_brazilian_phone,
    derive_situation,
    extract_request_parts,
    is_valid_brazilian_phone,
    normalize_key,
)
from .models import AcompanhamentoRequisicao, Predio, Requisicao, Requisitante, TaxonomiaServico
from .services import register_status_history, resolve_priority_label, status_sipac_catalog, status_sipac_display

DATE_INPUT_FORMAT = "%Y-%m-%d"
DATE_INPUT_FORMATS = [DATE_INPUT_FORMAT, "%d/%m/%Y"]


class RequisicaoForm(forms.ModelForm):
    codigo = forms.CharField(label="Nº Requisição")
    assunto = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))
    orcamento_valor = forms.DecimalField(
        required=False,
        label="Orçamento",
        max_digits=12,
        decimal_places=2,
        widget=forms.TextInput(attrs={
            "placeholder": "0,00",
            "inputmode": "decimal",
            "autocomplete": "off",
        }),
    )
    data_cadastro = forms.DateField(
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(format=DATE_INPUT_FORMAT, attrs={"type": "date"}),
    )
    data_execucao = forms.DateField(
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(format=DATE_INPUT_FORMAT, attrs={"type": "date"}),
    )
    local_servico = forms.CharField(required=False)
    nome_requisitante_snapshot = forms.CharField(label="Nome do Requisitante")
    unidade_setor_snapshot = forms.CharField(label="Unidade/Setor")
    contato_direto_url = forms.CharField(
        required=False,
        label="Contato",
        widget=forms.TextInput(attrs={"placeholder": "(83) 99999-9999", "inputmode": "tel"}),
    )
    link_atendimento = forms.URLField(required=False, label="Link do Atendimento")
    link_sipac = forms.URLField(required=False, label="Link SIPAC")
    situacao_requisicao = forms.CharField(
        required=False,
        label="Situação da Requisição",
        widget=forms.TextInput(attrs={"readonly": "readonly"}),
    )

    class Meta:
        model = Requisicao
        fields = [
            "numero",
            "ano",
            "codigo",
            "assunto",
            "orcamento_valor",
            "data_cadastro",
            "data_execucao",
            "tipo_requisicao",
            "divisao",
            "unidade_origem",
            "status_sipac",
            "situacao_requisicao",
            "tipo_servico",
            "servico",
            "predio",
            "local_servico",
            "requisitante",
            "nome_requisitante_snapshot",
            "unidade_setor_snapshot",
            "contato_direto_url",
            "situacao_texto",
            "gravidade",
            "urgencia",
            "tendencia",
            "sinfra_responsavel",
            "link_atendimento",
            "link_sipac",
            "visivel_publicamente",
        ]
        labels = {
            "divisao": "Divisão",
            "status_sipac": "Status SIPAC",
            "tipo_servico": "Tipo de Serviço",
            "servico": "Serviço",
            "predio": "Prédio Envolvido",
            "local_servico": "Local do Serviço",
        }
        help_texts = {
            "situacao_requisicao": "Calculada automaticamente a partir do Status SIPAC.",
        }
        widgets = {
            "numero": forms.HiddenInput(),
            "ano": forms.HiddenInput(),
            "tipo_requisicao": forms.HiddenInput(),
            "unidade_origem": forms.HiddenInput(),
            "requisitante": forms.HiddenInput(),
            "situacao_texto": forms.HiddenInput(),
            "gravidade": forms.HiddenInput(),
            "urgencia": forms.HiddenInput(),
            "tendencia": forms.HiddenInput(),
            "sinfra_responsavel": forms.HiddenInput(),
            "visivel_publicamente": forms.HiddenInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.taxonomy_options = self._load_taxonomy_options()
        self.status_sipac_options = self._load_status_sipac_options()
        self._configure_taxonomy_fields()
        self._configure_status_field()
        self._configure_predio_field()

        for name, field in self.fields.items():
            if isinstance(field.widget, forms.HiddenInput):
                continue
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")

        self.fields["situacao_requisicao"].disabled = True
        self.fields["situacao_requisicao"].required = False

        if self.instance.pk:
            self.fields["data_execucao"].disabled = False
        else:
            self.fields["data_execucao"].disabled = True
            self.fields["data_execucao"].help_text = "Disponível somente após a criação da requisição."
            self.fields["data_execucao"].initial = None

        if not self.is_bound and not self.instance.pk:
            self.fields["visivel_publicamente"].initial = True

        self.fields["situacao_requisicao"].initial = derive_situation(self._status_source())

        # Exibe orcamento_valor com vírgula decimal no formato BR (ex: "1500,00")
        if not self.is_bound and self.instance.pk and self.instance.orcamento_valor is not None:
            self.initial["orcamento_valor"] = str(self.instance.orcamento_valor).replace(".", ",")

    def _load_taxonomy_options(self) -> list[dict[str, str]]:
        rows = TaxonomiaServico.objects.exclude(divisao="").order_by(
            "ordem_divisao",
            "divisao",
            "ordem_tipo",
            "tipo_servico",
            "ordem_servico",
            "servico",
        )
        options: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            item = (
                clean_display_text(row.divisao),
                clean_display_text(row.tipo_servico),
                clean_display_text(row.servico),
            )
            if item in seen:
                continue
            seen.add(item)
            options.append({"divisao": item[0], "tipo_servico": item[1], "servico": item[2]})
        return options

    def _load_status_sipac_options(self) -> list[dict[str, str]]:
        extra_values = list(
            Requisicao.objects.exclude(status_sipac="").values_list("status_sipac", flat=True).distinct().order_by("status_sipac")
        )
        current = self._current_value("status_sipac")
        if current:
            extra_values.append(current)
        return status_sipac_catalog(extra_values)

    def _current_value(self, name: str) -> str:
        if self.is_bound:
            return clean_display_text(self.data.get(self.add_prefix(name), ""))
        initial = self.initial.get(name)
        if initial not in ("", None):
            return clean_display_text(initial)
        return clean_display_text(getattr(self.instance, name, ""))

    def _ordered_values(self, key: str) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        for row in self.taxonomy_options:
            value = row[key]
            if not value or value in seen:
                continue
            seen.add(value)
            values.append(value)
        current_value = self._current_value(key)
        if current_value and current_value not in seen:
            values.append(current_value)
        return values

    def _configure_taxonomy_fields(self) -> None:
        self._replace_choice_field("divisao", self._ordered_values("divisao"), "form-select")
        self._replace_choice_field("tipo_servico", self._ordered_values("tipo_servico"), "form-select")
        self._replace_choice_field("servico", self._ordered_values("servico"), "form-select")

    def _configure_status_field(self) -> None:
        original = self.fields["status_sipac"]
        attrs = dict(original.widget.attrs)
        attrs["class"] = "form-select"
        attrs["data-status-source"] = "status-sipac"
        self.fields["status_sipac"] = forms.ChoiceField(
            choices=[("", "---------")] + [(item["value"], item["label"]) for item in self.status_sipac_options],
            required=original.required,
            label=original.label,
            help_text=original.help_text,
            widget=forms.Select(attrs=attrs),
        )

    def _configure_predio_field(self) -> None:
        self.fields["predio"].queryset = Predio.objects.order_by("nome")
        self.fields["predio"].empty_label = "---------"
        self.fields["predio"].widget.attrs["class"] = "form-select"

    def _replace_choice_field(self, name: str, values: list[str], css_class: str) -> None:
        original = self.fields[name]
        attrs = dict(original.widget.attrs)
        attrs["class"] = css_class
        attrs["data-taxonomy-field"] = name
        self.fields[name] = forms.ChoiceField(
            choices=[("", "---------")] + [(value, value) for value in values],
            required=original.required,
            label=original.label,
            help_text=original.help_text,
            widget=forms.Select(attrs=attrs),
        )

    def _status_source(self) -> str:
        if self.is_bound:
            return self.data.get(self.add_prefix("status_sipac"), "")
        return self.initial.get("status_sipac") or getattr(self.instance, "status_sipac", "")

    def _resolve_taxonomia(self, divisao: str, tipo_servico: str, servico: str) -> TaxonomiaServico | None:
        if not any([divisao, tipo_servico, servico]):
            return None
        return TaxonomiaServico.objects.filter(chave_normalizada=normalize_key(divisao, tipo_servico, servico)).first()

    def clean(self):
        cleaned_data = super().clean()
        divisao = clean_display_text(cleaned_data.get("divisao"))
        tipo_servico = clean_display_text(cleaned_data.get("tipo_servico"))
        servico = clean_display_text(cleaned_data.get("servico"))
        status_sipac = clean_display_text(cleaned_data.get("status_sipac"))
        taxonomia = self._resolve_taxonomia(divisao, tipo_servico, servico)
        if any([divisao, tipo_servico, servico]) and taxonomia is None:
            message = "Selecione uma combinação válida de Divisão, Tipo de Serviço e Serviço."
            self.add_error("divisao", message)
            self.add_error("tipo_servico", message)
            self.add_error("servico", message)
            return cleaned_data
        if taxonomia:
            cleaned_data["divisao"] = taxonomia.divisao
            cleaned_data["tipo_servico"] = taxonomia.tipo_servico
            cleaned_data["servico"] = taxonomia.servico
        cleaned_data["taxonomia"] = taxonomia
        cleaned_data["status_sipac"] = status_sipac
        if status_sipac:
            cleaned_data["status_sipac_exibicao"] = status_sipac_display(status_sipac)
        cleaned_data["situacao_requisicao"] = derive_situation(status_sipac)
        cleaned_data["nome_requisitante_snapshot"] = clean_display_text(cleaned_data.get("nome_requisitante_snapshot"))
        cleaned_data["unidade_setor_snapshot"] = clean_display_text(cleaned_data.get("unidade_setor_snapshot"))
        cleaned_data["local_servico"] = clean_display_text(cleaned_data.get("local_servico"))
        return cleaned_data

    def clean_orcamento_valor(self):
        from decimal import Decimal, InvalidOperation
        raw = self.data.get(self.add_prefix("orcamento_valor"), "").strip()
        if not raw:
            return None
        # Aceita formato BR "1.500,00" ou "1500,00" ou "1500.00"
        if "," in raw:
            raw = raw.replace(".", "").replace(",", ".")
        raw = raw.replace("R$", "").replace(" ", "")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            raise forms.ValidationError("Informe um valor monetário válido. Ex: 1500,00")
        if value < 0:
            raise forms.ValidationError("O valor não pode ser negativo.")
        return value.quantize(Decimal("0.01"))

    def clean_codigo(self):
        numero = self.cleaned_data.get("numero")
        ano = self.cleaned_data.get("ano")
        codigo = clean_display_text(self.cleaned_data.get("codigo"))
        if codigo:
            parsed_numero, parsed_ano = extract_request_parts(codigo)
            if parsed_numero is None or parsed_ano is None:
                raise forms.ValidationError("Informe o Nº Requisição no formato número/ano.")
            self.cleaned_data["numero"] = parsed_numero
            self.cleaned_data["ano"] = parsed_ano
            return codigo
        if numero and ano:
            return f"{numero}/{ano}"
        raise forms.ValidationError("Informe o Nº Requisição no formato número/ano.")

    def clean_contato_direto_url(self):
        value = clean_display_text(self.cleaned_data.get("contato_direto_url"))
        if not value:
            return ""
        if not is_valid_brazilian_phone(value):
            raise forms.ValidationError("Informe um telefone brasileiro válido, com DDD.")
        return coerce_brazilian_phone(value)

    def save(self, commit=True):
        previous_status = self.instance.status_sipac if self.instance.pk else ""
        previous_note = self.instance.situacao_texto if self.instance.pk else ""
        instance = super().save(commit=False)
        instance.numero = self.cleaned_data.get("numero")
        instance.ano = self.cleaned_data.get("ano")
        instance.taxonomia = self.cleaned_data.get("taxonomia")
        instance.situacao_requisicao = derive_situation(instance.status_sipac)
        instance.prioridade_final = resolve_priority_label(instance.prioridade_lookup_key, instance.prioridade_final)

        if not self.instance.pk:
            instance.data_execucao = None

        requisitante_nome = clean_display_text(instance.nome_requisitante_snapshot)
        if requisitante_nome:
            requisitante = Requisitante.objects.filter(
                chave_normalizada=normalize_key(requisitante_nome),
                unidade_setor=instance.unidade_setor_snapshot or "",
            ).first()
            if requisitante is None:
                requisitante = Requisitante.objects.create(
                    nome=requisitante_nome,
                    unidade_setor=instance.unidade_setor_snapshot or "",
                    contato_url=instance.contato_direto_url or "",
                )
            else:
                has_changes = False
                if requisitante.nome != requisitante_nome:
                    requisitante.nome = requisitante_nome
                    has_changes = True
                if requisitante.contato_url != (instance.contato_direto_url or ""):
                    requisitante.contato_url = instance.contato_direto_url or ""
                    has_changes = True
                if has_changes:
                    requisitante.save()
            instance.requisitante = requisitante
        else:
            instance.requisitante = None

        if commit:
            instance.save()
            register_status_history(
                instance,
                previous_status=previous_status,
                previous_note=previous_note,
                note=instance.situacao_texto,
                user=self.user,
            )
        return instance


class ImportacaoForm(forms.Form):
    arquivo = forms.FileField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["arquivo"].widget.attrs.setdefault("class", "form-control")


class AcompanhamentoRequisicaoForm(forms.ModelForm):
    class Meta:
        model = AcompanhamentoRequisicao
        fields = ["data", "atualizacao_situacao"]
        widgets = {
            "data": forms.DateInput(format=DATE_INPUT_FORMAT, attrs={"type": "date"}),
            "atualizacao_situacao": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Descreva a nova situação da requisição",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data"].input_formats = DATE_INPUT_FORMATS
        self.fields["data"].widget.format = DATE_INPUT_FORMAT
        self.fields["data"].widget.attrs.setdefault("class", "form-control")
        self.fields["atualizacao_situacao"].widget.attrs.setdefault("class", "form-control")


class AcompanhamentoComentarioForm(AcompanhamentoRequisicaoForm):
    class Meta(AcompanhamentoRequisicaoForm.Meta):
        labels = {
            "data": "Data da situação",
            "atualizacao_situacao": "Comentário / situação",
        }
        widgets = {
            "data": forms.DateInput(format=DATE_INPUT_FORMAT, attrs={"type": "date"}),
            "atualizacao_situacao": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Descreva a situação ou comentário que ficará visível no histórico.",
                }
            ),
        }


AcompanhamentoRequisicaoFormSet = inlineformset_factory(
    Requisicao,
    AcompanhamentoRequisicao,
    form=AcompanhamentoRequisicaoForm,
    extra=0,
    can_delete=False,
)
