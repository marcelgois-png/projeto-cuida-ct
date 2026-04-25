"""
Data migration: copia o campo orcamento (CharField legado) para orcamento_valor
(DecimalField) nas requisições que ainda não têm orcamento_valor preenchido.

Aceita os formatos mais comuns do campo texto:
  "1500"  /  "1500.00"  /  "1500,00"  /  "1.500,00"  /  "R$ 1.500,00"
"""
import re
from decimal import Decimal, InvalidOperation

from django.db import migrations


def _parse(raw: str) -> Decimal | None:
    if not raw:
        return None
    cleaned = raw.strip()
    # Remove símbolo de moeda e espaços
    cleaned = re.sub(r"[Rr$\s]", "", cleaned)
    # Formato BR: tem vírgula → remove pontos de milhar, troca vírgula por ponto
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        v = Decimal(cleaned).quantize(Decimal("0.01"))
        return v if v > 0 else None
    except InvalidOperation:
        return None


def forwards(apps, schema_editor):
    Requisicao = apps.get_model("tracker", "Requisicao")
    to_update = []
    for req in Requisicao.objects.filter(orcamento_valor__isnull=True).exclude(orcamento=""):
        valor = _parse(req.orcamento)
        if valor is not None:
            req.orcamento_valor = valor
            to_update.append(req)
    if to_update:
        Requisicao.objects.bulk_update(to_update, ["orcamento_valor"])


def backwards(apps, schema_editor):
    pass  # Não reverte — manter os valores é seguro


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0014_orcamento_completo"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
