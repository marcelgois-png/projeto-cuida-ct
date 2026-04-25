from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def brl(value):
    """Formata um valor Decimal/float como moeda brasileira. Ex: 1500.50 → '1.500,50'"""
    if value is None or value == "":
        return "-"
    try:
        v = Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return str(value)
    # Formata com separador de milhar (.) e decimal (,)
    formatted = f"{v:,.2f}"          # '1,500.50'  (locale EN)
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")  # '1.500,50'
    return formatted


@register.filter
def intdot(value):
    """Formata inteiro com separador de milhar brasileiro. Ex: 1500 -> '1.500'"""
    if value is None or value == "":
        return "-"
    try:
        v = int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    return f"{v:,}".replace(",", ".")


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return None
    return mapping.get(key)
