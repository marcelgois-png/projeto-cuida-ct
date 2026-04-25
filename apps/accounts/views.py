from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView, CreateView, UpdateView

from .models import User
from .forms import UserForm

class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return bool(self.request.user.is_authenticated and getattr(self.request.user, "is_admin", False))

def user_is_admin(request) -> bool:
    return bool(request.user.is_authenticated and getattr(request.user, "is_admin", False))

class UserListView(AdminRequiredMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    context_object_name = "users"
    ordering = ["nome_completo", "username"]

class UserCreateView(AdminRequiredMixin, CreateView):
    model = User
    form_class = UserForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("user-list")

    def form_valid(self, form):
        messages.success(self.request, "Usuário criado com sucesso.")
        return super().form_valid(form)

class UserUpdateView(AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("user-list")

    def form_valid(self, form):
        messages.success(self.request, "Usuário atualizado com sucesso.")
        return super().form_valid(form)

@login_required
@require_http_methods(["POST"])
def toggle_user_active(request, pk: int) -> HttpResponse:
    if not user_is_admin(request):
        raise Http404
    user = get_object_or_404(User, pk=pk)
    
    # Previne que o administrador se inative
    if user == request.user:
        messages.error(request, "Você não pode inativar a própria conta.")
        return redirect("user-list")
        
    user.is_active = not user.is_active
    user.save()
    status = "ativado" if user.is_active else "inativado"
    messages.success(request, f"Usuário {status} com sucesso.")
    return redirect("user-list")

@login_required
@require_http_methods(["POST"])
def delete_user(request, pk: int) -> HttpResponse:
    if not user_is_admin(request):
        raise Http404
    user = get_object_or_404(User, pk=pk)
    
    if user == request.user:
        messages.error(request, "Você não pode excluir a própria conta.")
        return redirect("user-list")
        
    user.delete()
    messages.success(request, "Usuário excluído com sucesso.")
    return redirect("user-list")
