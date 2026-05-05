from __future__ import annotations

from pathlib import Path

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
from .models import (
    AcompanhamentoRequisicao,
    DivisaoSINFRA,
    Predio,
    Requisicao,
    Servico,
    Solicitante,
    StatusRequisicao,
    TaxonomiaServico,
    TipoServico,
)
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
    nome_requisitante_snapshot = forms.CharField(label="Nome do Solicitante")
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
            "orcamento",
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
            "solicitante",
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
            "orcamento": forms.HiddenInput(),
            "tipo_requisicao": forms.HiddenInput(),
            "unidade_origem": forms.HiddenInput(),
            "solicitante": forms.HiddenInput(),
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
            Requisicao.objects.filter(status_sipac__isnull=False)
            .values_list("status_sipac__codigo", flat=True)
            .distinct()
            .order_by("status_sipac__codigo")
        )
        if self.is_bound:
            current = clean_display_text(self.data.get(self.add_prefix("status_sipac"), ""))
        else:
            status_obj = getattr(self.instance, "status_sipac", None)
            current = status_obj.codigo if status_obj else ""
        if current and current not in extra_values:
            extra_values.append(current)
        return status_sipac_catalog(extra_values)

    def _current_value(self, name: str) -> str:
        if self.is_bound:
            return clean_display_text(self.data.get(self.add_prefix(name), ""))
        initial = self.initial.get(name)
        if initial not in ("", None):
            return clean_display_text(str(initial))
        val = getattr(self.instance, name, None) or ""
        if hasattr(val, "nome"):
            return clean_display_text(val.nome)
        return clean_display_text(val)

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
        status_obj = getattr(self.instance, "status_sipac", None)
        return status_obj.codigo if status_obj else ""

    def _resolve_taxonomia(self, divisao: str, tipo_servico: str, servico: str) -> TaxonomiaServico | None:
        if not any([divisao, tipo_servico, servico]):
            return None
        return TaxonomiaServico.objects.filter(chave_normalizada=normalize_key(divisao, tipo_servico, servico)).first()

    def _post_clean(self):
        # Temporarily stash the FK-related fields so construct_instance() won't
        # try to assign strings to FK model attributes. The custom save() resolves
        # these to real FK objects after validation.
        _fk_keys = ("divisao", "tipo_servico", "servico", "status_sipac")
        _stash = {k: self.cleaned_data.pop(k, None) for k in _fk_keys if k in getattr(self, "cleaned_data", {})}
        try:
            super()._post_clean()
        finally:
            if _stash:
                self.cleaned_data.update(_stash)

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
        previous_status = (
            self.instance.status_sipac.codigo
            if (self.instance.pk and self.instance.status_sipac)
            else ""
        )
        previous_note = self.instance.situacao_texto if self.instance.pk else ""
        instance = super().save(commit=False)
        instance.numero = self.cleaned_data.get("numero")
        instance.ano = self.cleaned_data.get("ano")

        # Resolve status_sipac from string code → FK
        status_codigo = clean_display_text(self.cleaned_data.get("status_sipac", ""))
        instance.status_sipac = (
            StatusRequisicao.objects.filter(codigo=status_codigo).first()
            if status_codigo else None
        )

        # Resolve divisao/tipo_servico/servico from string names → FKs
        divisao_nome = clean_display_text(self.cleaned_data.get("divisao", ""))
        tipo_nome = clean_display_text(self.cleaned_data.get("tipo_servico", ""))
        servico_nome = clean_display_text(self.cleaned_data.get("servico", ""))
        instance.divisao = DivisaoSINFRA.objects.filter(nome=divisao_nome).first() if divisao_nome else None
        instance.tipo_servico = (
            TipoServico.objects.filter(nome=tipo_nome, divisao=instance.divisao).first()
            if (tipo_nome and instance.divisao) else None
        )
        instance.servico = (
            Servico.objects.filter(nome=servico_nome, tipo_servico=instance.tipo_servico).first()
            if (servico_nome and instance.tipo_servico) else None
        )

        instance.situacao_requisicao = derive_situation(status_codigo)
        instance.prioridade_final = resolve_priority_label(instance.prioridade_lookup_key, instance.prioridade_final)

        if not self.instance.pk:
            instance.data_execucao = None

        solicitante_nome = clean_display_text(instance.nome_requisitante_snapshot)
        if solicitante_nome:
            solicitante = Solicitante.objects.filter(
                chave_normalizada=normalize_key(solicitante_nome),
            ).first()
            if solicitante is None:
                solicitante = Solicitante.objects.create(
                    nome=solicitante_nome,
                    contato_url=instance.contato_direto_url or "",
                )
            else:
                has_changes = False
                if solicitante.nome != solicitante_nome:
                    solicitante.nome = solicitante_nome
                    has_changes = True
                if solicitante.contato_url != (instance.contato_direto_url or ""):
                    solicitante.contato_url = instance.contato_direto_url or ""
                    has_changes = True
                if has_changes:
                    solicitante.save()
            instance.solicitante = solicitante
        else:
            instance.solicitante = None

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


_EXTENSOES_PERMITIDAS = {".xlsx", ".xlsm", ".csv"}
_TAMANHO_MAXIMO_BYTES = 20 * 1024 * 1024  # 20 MB
_MAGIC_ZIP = b"PK\x03\x04"  # assinatura de XLSX/XLSM (formato ZIP interno)


class ImportacaoForm(forms.Form):
    arquivo = forms.FileField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["arquivo"].widget.attrs.setdefault("class", "form-control")

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]

        extensao = Path(arquivo.name).suffix.lower()
        if extensao not in _EXTENSOES_PERMITIDAS:
            raise forms.ValidationError(
                f"Formato inválido. Envie um arquivo XLSX, XLSM ou CSV. "
                f"Recebido: '{extensao or 'sem extensão'}'"
            )

        if arquivo.size > _TAMANHO_MAXIMO_BYTES:
            limite_mb = _TAMANHO_MAXIMO_BYTES // (1024 * 1024)
            raise forms.ValidationError(
                f"Arquivo muito grande. Limite: {limite_mb} MB. "
                f"Recebido: {arquivo.size // (1024 * 1024)} MB."
            )

        if extensao in {".xlsx", ".xlsm"}:
            header = arquivo.read(4)
            arquivo.seek(0)
            if header != _MAGIC_ZIP:
                raise forms.ValidationError(
                    "O arquivo não é um XLSX/XLSM válido. "
                    "Verifique se o arquivo não está corrompido."
                )

        return arquivo


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
