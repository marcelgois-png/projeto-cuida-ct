from __future__ import annotations

from django.test import TestCase, RequestFactory, override_settings
from django.http import JsonResponse

from apps.core.ratelimit import rate_limit
from apps.core.views import health


class HealthViewTests(TestCase):
    def test_retorna_200_com_banco_acessivel(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["db"])

    def test_resposta_e_json(self):
        response = self.client.get("/health/")
        self.assertEqual(response["Content-Type"], "application/json")

    def test_degraded_quando_banco_indisponivel(self):
        from unittest.mock import patch
        with patch("apps.core.views.connection.ensure_connection", side_effect=Exception("falha")):
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data["status"], "degraded")
        self.assertFalse(data["db"])


class RateLimitTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _make_view(self, limit=2):
        @rate_limit(requests=limit, window=60)
        def dummy_view(request):
            return JsonResponse({"ok": True})
        return dummy_view

    def test_permite_requisicoes_dentro_do_limite(self):
        view = self._make_view(limit=3)
        req = self.factory.get("/")
        req.META["REMOTE_ADDR"] = "10.0.0.1"
        for _ in range(3):
            r = view(req)
            self.assertEqual(r.status_code, 200)

    def test_bloqueia_apos_exceder_limite(self):
        import json
        view = self._make_view(limit=2)
        req = self.factory.get("/")
        req.META["REMOTE_ADDR"] = "10.0.0.2"
        view(req)
        view(req)
        r = view(req)
        self.assertEqual(r.status_code, 429)
        self.assertIn("erro", json.loads(r.content))

    def test_ips_diferentes_nao_interferem(self):
        view = self._make_view(limit=1)
        rf = self.factory

        req_a = rf.get("/")
        req_a.META["REMOTE_ADDR"] = "10.0.0.10"

        req_b = rf.get("/")
        req_b.META["REMOTE_ADDR"] = "10.0.0.11"

        self.assertEqual(view(req_a).status_code, 200)
        self.assertEqual(view(req_b).status_code, 200)

    def test_usa_x_forwarded_for_quando_disponivel(self):
        view = self._make_view(limit=1)
        req = self.factory.get("/")
        req.META["REMOTE_ADDR"] = "192.168.1.1"
        req.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.5, 192.168.1.1"
        self.assertEqual(view(req).status_code, 200)
        r2 = view(req)
        self.assertEqual(r2.status_code, 429)
