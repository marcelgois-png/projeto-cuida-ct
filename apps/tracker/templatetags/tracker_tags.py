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
def brl_k(value):
    """Formata valor BRL com abreviação de milhar/milhão para uso em KPIs.
    Ex: 125631.40 → '125,6 mil' | 1234567 → '1,2 mi' | 850 → '850,00'"""
    if value is None or value == "":
        return "-"
    try:
        v = Decimal(str(value))
    except InvalidOperation:
        return str(value)

    abs_v = abs(v)
    sign = "-" if v < 0 else ""

    if abs_v >= Decimal("1000000"):
        abbr = (abs_v / Decimal("1000000")).quantize(Decimal("0.1"))
        formatted = f"{abbr:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{sign}{formatted}mi"
    elif abs_v >= Decimal("1000"):
        abbr = (abs_v / Decimal("1000")).quantize(Decimal("0.1"))
        formatted = f"{abbr:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{sign}{formatted}k"
    else:
        return brl(value)


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return None
    return mapping.get(key)
