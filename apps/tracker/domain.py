from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
import unicodedata
from datetime import date, datetime
from typing import Any


ACTIVE_STATUS_CODES = {
    "01 CADASTRADA",
    "02 ENVIADA",
    "03 AGUARDANDO OS",
    "04 OS EMITIDA",
    "05 AGUARDANDO AVALIACAO REQUISITANTE",
    "10 PENDENTE DE AUTORIZACAO CHEFE UNIDADE",
}

STATUS_SIPAC_FLOW = (
    ("01", "Cadastrada", "01 CADASTRADA"),
    ("02", "Enviada", "02 ENVIADA"),
    ("03", "Aguardando OS", "03 AGUARDANDO OS"),
    ("04", "OS emitida", "04 OS EMITIDA"),
    ("05", "Aguardando avaliação requisitante", "05 AGUARDANDO AVALIAÇÃO REQUISITANTE"),
    ("06", "Finalizada", "06 FINALIZADA"),
    ("07", "Retornada", "07 RETORNADA"),
    ("08", "Estornada", "08 ESTORNADA"),
    ("09", "Negada", "09 NEGADA"),
    ("10", "Pendente de autorização chefe unidade", "10 PENDENTE DE AUTORIZAÇÃO CHEFE UNIDADE"),
    ("11", "Não executado - motivo diverso", "11 NÃO EXECUTADO - MOTIVO DIVERSO"),
    ("12", "Não executado - abrir processo", "12 NÃO EXECUTADO - ABRIR PROCESSO"),
    ("12", "Não executado - abrir processo (Em análise)", "12 NÃO EXECUTADO - ABRIR PROCESSO (Em análise)"),
    ("13", "Não executado - finalizada pelo tempo SINFRA", "13 NÃO EXECUTADO - FINALIZADA PELO TEMPO SINFRA"),
    ("14", "Não executado - reabrir requisição", "14 NÃO EXECUTADO - REABRIR REQUISIÇÃO"),
    ("15", "Não executado - finalizada falta de resposta", "15 NÃO EXECUTADO - FINALIZADA FALTA DE RESPOSTA"),
    ("16", "Não executado - setor de projetos", "16 NÃO EXECUTADO - SETOR DE PROJETOS"),
)

GRAVIDADE_LEVELS = {
    "Sem gravidade": 1,
    "Pouco grave": 2,
    "Grave": 3,
    "Muito grave": 4,
    "Extremamente grave": 5,
}

URGENCIA_LEVELS = {
    "Pode esperar": 1,
    "Pouco urgente": 2,
    "Mais rápido possível": 3,
    "É urgente": 4,
    "Precisa ser resolvido já": 5,
}

TENDENCIA_LEVELS = {
    "Não mudar nada": 1,
    "Piorar em longo prazo": 2,
    "Piorar em médio prazo": 3,
    "Piorar em curto prazo": 4,
    "Piorar rapidamente": 5,
}

GUT_THRESHOLDS = (
    (125, "CRÍTICO"),
    (75, "MODERADO"),
    (25, "REGULAR"),
)

PRIORITY_CHOICES = (
    ("1 - Urgente", "1 - Urgente"),
    ("2 - Alta", "2 - Alta"),
    ("3 - Média", "3 - Média"),
    ("4 - Baixa", "4 - Baixa"),
    ("5 - Analisar", "5 - Analisar"),
    ("6 - Inativa", "6 - Inativa"),
)


def resolve_status_sipac_metadata(value: Any) -> dict[str, Any]:
    descricao = clean_display_text(value)
    if not descricao:
        return {"numero": "", "rotulo": "", "descricao": "", "ordem": None, "label": ""}

    normalized = normalize_text(descricao).upper()
    for ordem, (numero, rotulo, descricao_oficial) in enumerate(STATUS_SIPAC_FLOW, start=1):
        if normalize_text(descricao_oficial).upper() == normalized:
            return {
                "numero": numero,
                "rotulo": rotulo,
                "descricao": descricao_oficial,
                "ordem": ordem,
                "label": rotulo,
            }

    return {
        "numero": "",
        "rotulo": descricao,
        "descricao": descricao,
        "ordem": None,
        "label": descricao,
    }


def repair_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ").strip()
    if not text or not any(marker in text for marker in ("Ã", "Â", "â", "�")):
        return text
    for encoding in ("latin1", "cp1252"):
        try:
            repaired = text.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if repaired and repaired.count("�") <= text.count("�"):
            return repaired.strip()
    return text


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = repair_text(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_key(*parts: Any) -> str:
    text = "".join(normalize_text(part).replace(" ", "") for part in parts if part)
    return text


def clean_display_text(value: Any) -> str:
    if value in ("", None):
        return ""
    return re.sub(r"\s+", " ", repair_text(value).replace("\xa0", " ")).strip()


def extract_request_parts(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    try:
        raw_number, raw_year = str(value).split("/", 1)
        return int(raw_number), int(raw_year)
    except (ValueError, TypeError):
        return None, None


def derive_situation(status_sipac: str | None) -> str:
    normalized = normalize_text(status_sipac).upper()
    if not normalized:
        return ""
    return "Ativa" if normalized in ACTIVE_STATUS_CODES else "Inativa"


def level_for_choice(value: str | None, mapping: dict[str, int]) -> int:
    normalized = normalize_text(value)
    if not normalized:
        return 0
    # Tenta extrair o número se começar com dígito (ex: "5 - ...")
    match = re.match(r"^(\d)", normalized)
    if match:
        return int(match.group(1))
        
    for choice, score in mapping.items():
        if normalize_text(choice) == normalized:
            return score
    return 0


def calculate_gut(gravidade: str | None, urgencia: str | None, tendencia: str | None) -> int:
    return (
        level_for_choice(gravidade, GRAVIDADE_LEVELS)
        * level_for_choice(urgencia, URGENCIA_LEVELS)
        * level_for_choice(tendencia, TENDENCIA_LEVELS)
    )


def classify_gut(score: int | None) -> str:
    if not score:
        return ""
    if score > GUT_THRESHOLDS[0][0]:
        return GUT_THRESHOLDS[0][1]
    if score > GUT_THRESHOLDS[1][0]:
        return GUT_THRESHOLDS[1][1]
    return GUT_THRESHOLDS[2][1]


def coerce_date(value: Any) -> date | None:
    if value in ("", None):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = normalize_text(value)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def coerce_int(value: Any) -> int | None:
    if value in ("", None):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def coerce_coordinate(value: Any, *, kind: str) -> Decimal | None:
    if value in ("", None):
        return None
    try:
        decimal_value = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, AttributeError):
        return None

    absolute_value = abs(decimal_value)
    limit = Decimal("90") if kind == "latitude" else Decimal("180")

    if absolute_value > limit:
        if absolute_value > Decimal("1000"):
            decimal_value = decimal_value / Decimal("1000000")
        if abs(decimal_value) > limit:
            return None

    return decimal_value.quantize(Decimal("0.000001"))


def coerce_brazilian_phone(value: Any) -> str:
    text = clean_display_text(value)
    if not text:
        return ""
    digits = re.sub(r"\D", "", text)
    if digits.startswith("55") and len(digits) in {12, 13}:
        digits = digits[2:]
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return text


def is_valid_brazilian_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("55") and len(digits) in {12, 13}:
        digits = digits[2:]
    return len(digits) in {10, 11}
