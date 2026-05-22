import re
from django import forms
from django.contrib.auth.models import User
from .models import validar_cpf, hash_cpf, normalizar_telefone, Barbearia

ESTADOS_BR = [
    ('', 'Estado'),
    ('AC','Acre'),('AL','Alagoas'),('AP','Amapá'),('AM','Amazonas'),
    ('BA','Bahia'),('CE','Ceará'),('DF','Distrito Federal'),('ES','Espírito Santo'),
    ('GO','Goiás'),('MA','Maranhão'),('MT','Mato Grosso'),('MS','Mato Grosso do Sul'),
    ('MG','Minas Gerais'),('PA','Pará'),('PB','Paraíba'),('PR','Paraná'),
    ('PE','Pernambuco'),('PI','Piauí'),('RJ','Rio de Janeiro'),('RN','Rio Grande do Norte'),
    ('RS','Rio Grande do Sul'),('RO','Rondônia'),('RR','Roraima'),('SC','Santa Catarina'),
    ('SP','São Paulo'),('SE','Sergipe'),('TO','Tocantins'),
]


class CadastroForm(forms.Form):
    nome_barbearia = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'BarberMetric', 'class': 'form-control'}),
        label='Nome da Barbearia',
    )
    nome_proprietario = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Seu nome completo', 'class': 'form-control'}),
        label='Nome do Proprietário',
    )
    cpf = forms.CharField(
        max_length=14,
        widget=forms.TextInput(attrs={'placeholder': '000.000.000-00', 'class': 'form-control', 'id': 'id_cpf'}),
        label='CPF do Proprietário',
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'seu@email.com', 'class': 'form-control'}),
    )
    telefone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={'placeholder': '(11) 99999-9999', 'class': 'form-control', 'id': 'id_telefone'}),
    )
    cidade = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'placeholder': 'Sua cidade', 'class': 'form-control'}),
    )
    estado = forms.ChoiceField(
        choices=ESTADOS_BR,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    senha = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={'placeholder': 'Mínimo 8 caracteres', 'class': 'form-control'}),
        label='Senha',
    )
    senha_confirmacao = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Repita a senha', 'class': 'form-control'}),
        label='Confirmar Senha',
    )

    def clean_cpf(self):
        cpf = re.sub(r'\D', '', self.cleaned_data['cpf'])
        if not validar_cpf(cpf):
            raise forms.ValidationError('CPF inválido. Verifique os dados informados.')
        if Barbearia.objects.filter(cpf_hash=hash_cpf(cpf)).exists():
            raise forms.ValidationError('Já existe uma conta cadastrada com este CPF.')
        return cpf

    def clean_telefone(self):
        tel = normalizar_telefone(self.cleaned_data['telefone'])
        if len(tel) < 10:
            raise forms.ValidationError('Telefone inválido.')
        if Barbearia.objects.filter(telefone_normalizado=tel).exists():
            raise forms.ValidationError('Já existe uma conta cadastrada com este telefone.')
        return self.cleaned_data['telefone']

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Já existe uma conta com este e-mail.')
        return email

    def clean_estado(self):
        estado = self.cleaned_data['estado']
        if not estado:
            raise forms.ValidationError('Selecione o estado.')
        return estado

    def clean(self):
        cleaned = super().clean()
        senha = cleaned.get('senha')
        confirmacao = cleaned.get('senha_confirmacao')
        if senha and confirmacao and senha != confirmacao:
            self.add_error('senha_confirmacao', 'As senhas não coincidem.')
        return cleaned
