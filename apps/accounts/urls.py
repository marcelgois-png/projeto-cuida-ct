from django.urls import path
from . import views

urlpatterns = [
    path("painel/usuarios/", views.UserListView.as_view(), name="user-list"),
    path("painel/usuarios/novo/", views.UserCreateView.as_view(), name="user-create"),
    path("painel/usuarios/<int:pk>/editar/", views.UserUpdateView.as_view(), name="user-update"),
    path("painel/usuarios/<int:pk>/ativar/", views.toggle_user_active, name="user-toggle-active"),
    path("painel/usuarios/<int:pk>/excluir/", views.delete_user, name="user-delete"),
]
