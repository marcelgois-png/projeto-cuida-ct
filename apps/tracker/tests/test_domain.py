from django.test import TestCase

from apps.tracker.domain import calculate_gut, classify_gut, coerce_brazilian_phone, derive_situation


class DomainRulesTests(TestCase):
    def test_derive_situation_uses_sipac_status(self):
        self.assertEqual(derive_situation("04 OS EMITIDA"), "Ativa")
        self.assertEqual(derive_situation("05 AGUARDANDO AVALIAÇÃO REQUISITANTE"), "Ativa")
        self.assertEqual(derive_situation("06 FINALIZADA"), "Inativa")

    def test_calculate_gut_matches_spreadsheet_levels(self):
        self.assertEqual(calculate_gut("Sem gravidade", "Pode esperar", "Não mudar nada"), 1)
        self.assertEqual(calculate_gut("Muito grave", "É urgente", "Piorar em curto prazo"), 64)

    def test_classify_gut_uses_current_thresholds(self):
        self.assertEqual(classify_gut(10), "REGULAR")
        self.assertEqual(classify_gut(60), "REGULAR")
        self.assertEqual(classify_gut(100), "MODERADO")
        self.assertEqual(classify_gut(130), "CRÍTICO")

    def test_phone_coercion_formats_whatsapp_urls_as_brazilian_phone(self):
        self.assertEqual(coerce_brazilian_phone("https://wa.me/5583999999999"), "(83) 99999-9999")
