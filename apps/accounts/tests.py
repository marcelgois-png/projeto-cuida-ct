from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from .models import User
from .forms import UserForm


def make_user(username="joao", role=User.Role.OPERATOR, **kwargs):
    u = User.objects.create_user(
        username=username,
        password="senha123",
        nome_completo=kwargs.pop("nome_completo", "João da Silva"),
        telefone=kwargs.pop("telefone", "83912345678"),
        role=role,
        **kwargs,
    )
    return u


class UserModelTests(TestCase):
    def test_admin_por_role(self):
        u = make_user(role=User.Role.ADMIN)
        self.assertTrue(u.is_admin)
        self.assertTrue(u.is_operator)
        self.assertTrue(u.is_director)

    def test_operator_nao_e_admin_nem_director(self):
        u = make_user(role=User.Role.OPERATOR)
        self.assertFalse(u.is_admin)
        self.assertTrue(u.is_operator)
        self.assertFalse(u.is_director)

    def test_director_nao_e_admin_nem_operator(self):
        u = make_user(role=User.Role.DIRECTOR)
        self.assertFalse(u.is_admin)
        self.assertFalse(u.is_operator)
        self.assertTrue(u.is_director)

    def test_superuser_e_admin(self):
        u = User.objects.create_superuser(username="super", password="s")
        self.assertTrue(u.is_admin)

    def test_admin_role_define_is_staff(self):
        u = make_user(role=User.Role.ADMIN)
        self.assertTrue(u.is_staff)


class UserFormTests(TestCase):
    def _data(self, **kwargs):
        base = {
            "nome_completo": "Maria Souza",
            "username": "maria",
            "email": "maria@ct.ufpb.br",
            "telefone": "83999990000",
            "role": User.Role.OPERATOR,
            "matricula": "",
            "senha": "Senha@2026",
            "senha_confirmacao": "Senha@2026",
        }
        base.update(kwargs)
        return base

    def test_form_valido_cria_usuario(self):
        form = UserForm(data=self._data())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertTrue(user.pk)
        self.assertTrue(user.check_password("Senha@2026"))

    def test_senhas_diferentes_invalida(self):
        form = UserForm(data=self._data(senha_confirmacao="outra"))
        self.assertFalse(form.is_valid())
        self.assertIn("senha_confirmacao", form.errors)

    def test_senha_obrigatoria_em_criacao(self):
        form = UserForm(data=self._data(senha="", senha_confirmacao=""))
        self.assertFalse(form.is_valid())

    def test_senha_opcional_em_edicao(self):
        user = make_user()
        data = self._data(username=user.username, senha="", senha_confirmacao="")
        form = UserForm(data=data, instance=user)
        self.assertTrue(form.is_valid(), form.errors)

    def test_edicao_sem_senha_mantem_senha_original(self):
        user = make_user()
        original_hash = user.password
        data = self._data(username=user.username, senha="", senha_confirmacao="")
        form = UserForm(data=data, instance=user)
        form.save()
        user.refresh_from_db()
        self.assertEqual(user.password, original_hash)


class UserViewsTests(TestCase):
    def setUp(self):
        self.admin = make_user(username="admin_user", role=User.Role.ADMIN)
        self.operator = make_user(username="op_user", role=User.Role.OPERATOR)

    def test_lista_redireciona_anonimo(self):
        r = self.client.get(reverse("user-list"))
        self.assertEqual(r.status_code, 302)

    def test_lista_redireciona_operator(self):
        self.client.force_login(self.operator)
        r = self.client.get(reverse("user-list"))
        self.assertEqual(r.status_code, 403)

    def test_lista_acessivel_para_admin(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("user-list"))
        self.assertEqual(r.status_code, 200)

    def test_toggle_ativo_inativa_usuario(self):
        self.client.force_login(self.admin)
        self.assertTrue(self.operator.is_active)
        self.client.post(reverse("user-toggle-active", args=[self.operator.pk]))
        self.operator.refresh_from_db()
        self.assertFalse(self.operator.is_active)

    def test_toggle_ativo_nao_permite_auto_inativacao(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("user-toggle-active", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_deletar_usuario(self):
        self.client.force_login(self.admin)
        pk = self.operator.pk
        self.client.post(reverse("user-delete", args=[pk]))
        self.assertFalse(User.objects.filter(pk=pk).exists())

    def test_deletar_nao_permite_auto_exclusao(self):
        self.client.force_login(self.admin)
        pk = self.admin.pk
        self.client.post(reverse("user-delete", args=[pk]))
        self.assertTrue(User.objects.filter(pk=pk).exists())

    def test_toggle_bloqueado_para_operator(self):
        self.client.force_login(self.operator)
        r = self.client.post(reverse("user-toggle-active", args=[self.admin.pk]))
        self.assertEqual(r.status_code, 404)
