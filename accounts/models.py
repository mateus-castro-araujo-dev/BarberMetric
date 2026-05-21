import re
import hashlib
import secrets
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify
from django.conf import settings
from cryptography.fernet import Fernet


def _fernet():
    key = settings.FIELD_ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_field(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_field(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except Exception:
        return ''


def validar_cpf(cpf: str) -> bool:
    cpf = re.sub(r'\D', '', cpf)
    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    d1 = 0 if soma % 11 < 2 else 11 - soma % 11
    if int(cpf[9]) != d1:
        return False
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    d2 = 0 if soma % 11 < 2 else 11 - soma % 11
    return int(cpf[10]) == d2


def formatar_cpf(cpf: str) -> str:
    cpf = re.sub(r'\D', '', cpf)
    return f'{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}'


def hash_cpf(cpf: str) -> str:
    cpf = re.sub(r'\D', '', cpf)
    return hashlib.sha256(cpf.encode()).hexdigest()


def normalizar_telefone(tel: str) -> str:
    return re.sub(r'\D', '', tel)


def gerar_slug_unico(nome: str) -> str:
    base = slugify(nome)
    slug = base
    counter = 1
    while Barbearia.objects.filter(slug=slug).exists():
        slug = f'{base}-{counter}'
        counter += 1
    return slug


class Barbearia(models.Model):
    PLANO_TRIAL = 'trial'
    PLANO_PRO = 'pro'
    PLANO_MAX = 'max'
    PLANO_ATIVO = 'ativo'      # legado — equivale a max
    PLANO_SUSPENSO = 'suspenso'
    PLANO_CANCELADO = 'cancelado'

    PLANO_CHOICES = [
        (PLANO_TRIAL, 'Período de Teste'),
        (PLANO_PRO, 'Pro — R$14,90/mês'),
        (PLANO_MAX, 'Max — R$34,90/mês'),
        (PLANO_ATIVO, 'Ativo (legado)'),
        (PLANO_SUSPENSO, 'Aguardando Pagamento'),
        (PLANO_CANCELADO, 'Cancelado'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='barbearia')
    nome = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, max_length=120)
    _cpf_proprietario = models.TextField(db_column='cpf_proprietario')
    cpf_hash = models.CharField(max_length=64, unique=True, db_index=True, null=True, blank=True)
    telefone = models.CharField(max_length=20)
    telefone_normalizado = models.CharField(max_length=20, unique=True, db_index=True, null=True, blank=True)
    cidade = models.CharField(max_length=100)
    estado = models.CharField(max_length=2)
    plano = models.CharField(max_length=20, choices=PLANO_CHOICES, default=PLANO_TRIAL)
    data_cadastro = models.DateTimeField(auto_now_add=True)
    ativo = models.BooleanField(default=True)
    pagamento_solicitado = models.BooleanField(default=False)
    data_pagamento_solicitado = models.DateTimeField(null=True, blank=True)
    # Verificação de email
    email_verificado = models.BooleanField(default=False)
    token_verificacao = models.CharField(max_length=64, null=True, blank=True)
    token_expira = models.DateTimeField(null=True, blank=True)
    # Redefinição de senha
    token_reset_senha = models.CharField(max_length=64, null=True, blank=True)
    token_reset_expira = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Barbearia'
        verbose_name_plural = 'Barbearias'

    def __str__(self):
        return self.nome

    @property
    def cpf_proprietario(self):
        return decrypt_field(self._cpf_proprietario)

    @cpf_proprietario.setter
    def cpf_proprietario(self, value):
        self._cpf_proprietario = encrypt_field(re.sub(r'\D', '', value))

    @property
    def cpf_formatado(self):
        cpf = self.cpf_proprietario
        if len(cpf) == 11:
            return f'{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}'
        return cpf

    @property
    def data_fim_trial(self):
        return self.data_cadastro + timedelta(days=30)

    @property
    def dias_restantes_trial(self):
        if self.plano != self.PLANO_TRIAL:
            return None
        delta = self.data_fim_trial - timezone.now()
        return max(0, delta.days)

    @property
    def trial_expirado(self):
        return self.plano == self.PLANO_TRIAL and self.dias_restantes_trial == 0

    @property
    def acesso_liberado(self):
        if not self.ativo:
            return False
        if self.plano in (self.PLANO_ATIVO, self.PLANO_PRO, self.PLANO_MAX):
            return True
        if self.plano == self.PLANO_TRIAL and not self.trial_expirado:
            return True
        return False

    @property
    def limites(self):
        """Retorna dicionário com os limites do plano atual."""
        if self.plano in (self.PLANO_MAX, self.PLANO_ATIVO):
            return {'clientes_nome': 1000, 'barbeiros': 20, 'servicos': 20, 'produtos': 20}
        if self.plano == self.PLANO_PRO:
            return {'clientes_nome': 100, 'barbeiros': 2, 'servicos': 6, 'produtos': 6}
        # trial
        return {'clientes_nome': 10, 'barbeiros': 1, 'servicos': 4, 'produtos': 4}

    @property
    def nome_plano(self):
        mapa = {
            self.PLANO_TRIAL: 'Trial Gratuito',
            self.PLANO_PRO: 'Pro',
            self.PLANO_MAX: 'Max',
            self.PLANO_ATIVO: 'Max',
            self.PLANO_SUSPENSO: 'Suspenso',
            self.PLANO_CANCELADO: 'Cancelado',
        }
        return mapa.get(self.plano, self.plano)

    def gerar_token_verificacao(self):
        self.token_verificacao = secrets.token_urlsafe(32)
        self.token_expira = timezone.now() + timedelta(hours=48)

    def gerar_token_reset_senha(self):
        self.token_reset_senha = secrets.token_urlsafe(32)
        self.token_reset_expira = timezone.now() + timedelta(hours=2)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = gerar_slug_unico(self.nome)
        super().save(*args, **kwargs)


class PagamentoMP(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CANCELLED = 'cancelled'

    barbearia = models.ForeignKey(Barbearia, on_delete=models.CASCADE, related_name='pagamentos_mp')
    payment_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=50, default=STATUS_PENDING)
    plano_escolhido = models.CharField(max_length=10, default='pro')
    qr_code = models.TextField(blank=True)
    qr_code_base64 = models.TextField(blank=True)
    valor = models.DecimalField(max_digits=8, decimal_places=2, default=14.90)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pagamento Mercado Pago'
        verbose_name_plural = 'Pagamentos Mercado Pago'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.barbearia.nome} — R${self.valor} ({self.status})'


class SolicitacaoPagamento(models.Model):
    barbearia = models.ForeignKey(Barbearia, on_delete=models.CASCADE, related_name='solicitacoes')
    data = models.DateTimeField(auto_now_add=True)
    mensagem = models.TextField(blank=True)
    atendido = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Solicitação de Pagamento'
        verbose_name_plural = 'Solicitações de Pagamento'
        ordering = ['-data']

    def __str__(self):
        return f'{self.barbearia.nome} - {self.data.strftime("%d/%m/%Y")}'
