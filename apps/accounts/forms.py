from django import forms
from .models import User

class UserForm(forms.ModelForm):
    senha = forms.CharField(widget=forms.PasswordInput(), required=False, label="Senha")
    senha_confirmacao = forms.CharField(widget=forms.PasswordInput(), required=False, label="Confirmação de Senha")

    class Meta:
        model = User
        fields = ["nome_completo", "matricula", "username", "email", "telefone", "foto", "role"]
        labels = {
            "nome_completo": "Nome Completo",
            "matricula": "Matrícula",
            "username": "Login (Usuário)",
            "email": "E-mail",
            "telefone": "Telefone ou Ramal",
            "foto": "Foto de Perfil",
            "role": "Perfil",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if type(field.widget) in (forms.CheckboxInput, forms.RadioSelect):
                continue
            field.widget.attrs["class"] = "form-control"
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select"

        # Tornar obrigatório o Login, E-mail
        self.fields["username"].required = True
        self.fields["email"].required = True
        self.fields["nome_completo"].required = True
        self.fields["telefone"].required = True

        if not self.instance.pk:
            self.fields["senha"].required = True
            self.fields["senha_confirmacao"].required = True

    def clean(self):
        cleaned_data = super().clean()
        senha = cleaned_data.get("senha")
        senha_confirmacao = cleaned_data.get("senha_confirmacao")

        if senha or senha_confirmacao:
            if senha != senha_confirmacao:
                self.add_error("senha_confirmacao", "As senhas não coincidem.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        senha = self.cleaned_data.get("senha")
        if senha:
            user.set_password(senha)
        if commit:
            user.save()
        return user
