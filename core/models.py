from django.db import models
from accounts.models import Barbearia


class Barbeiro(models.Model):
    barbearia = models.ForeignKey(Barbearia, on_delete=models.CASCADE, related_name='barbeiros')
    nome = models.CharField(max_length=100)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Barbeiro'
        verbose_name_plural = 'Barbeiros'
        ordering = ['nome']
        unique_together = ['barbearia', 'nome']

    def __str__(self):
        return self.nome


class Cliente(models.Model):
    barbearia = models.ForeignKey(Barbearia, on_delete=models.CASCADE, related_name='clientes')
    barbeiro = models.ForeignKey(Barbeiro, on_delete=models.SET_NULL, null=True, blank=True, related_name='clientes')
    nome = models.CharField(max_length=100)
    telefone = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['nome']
        unique_together = ['barbearia', 'barbeiro', 'nome']

    def __str__(self):
        return self.nome


class Servico(models.Model):
    barbearia = models.ForeignKey(Barbearia, on_delete=models.CASCADE, related_name='servicos')
    nome = models.CharField(max_length=100)
    preco = models.DecimalField(max_digits=8, decimal_places=2)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Serviço'
        verbose_name_plural = 'Serviços'
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} - R$ {self.preco}'


class Atendimento(models.Model):
    PAGAMENTO_CHOICES = [
        ('PIX', 'PIX'),
        ('DINHEIRO', 'Dinheiro'),
        ('CREDITO', 'Cartão de Crédito'),
        ('DEBITO', 'Cartão de Débito'),
        ('PLANO', 'Plano Mensal'),
    ]

    barbearia = models.ForeignKey(Barbearia, on_delete=models.CASCADE, related_name='atendimentos')
    barbeiro = models.ForeignKey(Barbeiro, on_delete=models.SET_NULL, null=True, blank=True, related_name='atendimentos')
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='atendimentos')
    servicos_prestados = models.TextField()
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    forma_pagamento = models.CharField(max_length=20, choices=PAGAMENTO_CHOICES)
    data = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Atendimento'
        verbose_name_plural = 'Atendimentos'
        ordering = ['-data']

    def __str__(self):
        return f'{self.barbeiro} → {self.cliente} ({self.data.strftime("%d/%m/%Y")})'


class Produto(models.Model):
    barbearia = models.ForeignKey(Barbearia, on_delete=models.CASCADE, related_name='produtos')
    nome = models.CharField(max_length=100)
    preco = models.DecimalField(max_digits=8, decimal_places=2)
    descricao = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Produto'
        verbose_name_plural = 'Produtos'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class VendaProduto(models.Model):
    PAGAMENTO_CHOICES = [
        ('PIX', 'PIX'),
        ('DINHEIRO', 'Dinheiro'),
        ('CREDITO', 'Cartão de Crédito'),
        ('DEBITO', 'Cartão de Débito'),
    ]

    barbearia = models.ForeignKey(Barbearia, on_delete=models.CASCADE, related_name='vendas_produto')
    barbeiro = models.ForeignKey(Barbeiro, on_delete=models.SET_NULL, null=True, blank=True, related_name='vendas_produto')
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True, related_name='vendas_produto')
    produto = models.ForeignKey(Produto, on_delete=models.SET_NULL, null=True, related_name='vendas')
    quantidade = models.PositiveIntegerField(default=1)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    forma_pagamento = models.CharField(max_length=20, choices=PAGAMENTO_CHOICES)
    data = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Venda de Produto'
        verbose_name_plural = 'Vendas de Produtos'
        ordering = ['-data']


class HorarioFuncionamento(models.Model):
    DIAS = [
        (0, 'Segunda-feira'), (1, 'Terça-feira'), (2, 'Quarta-feira'),
        (3, 'Quinta-feira'), (4, 'Sexta-feira'), (5, 'Sábado'), (6, 'Domingo'),
    ]

    barbearia = models.ForeignKey(Barbearia, on_delete=models.CASCADE, related_name='horarios')
    barbeiro = models.ForeignKey(Barbeiro, on_delete=models.CASCADE, null=True, blank=True, related_name='horarios')
    dia = models.IntegerField(choices=DIAS)
    aberto = models.BooleanField(default=True)
    inicio_manha = models.TimeField(null=True, blank=True)
    fim_manha = models.TimeField(null=True, blank=True)
    inicio_tarde = models.TimeField(null=True, blank=True)
    fim_tarde = models.TimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Horário de Funcionamento'
        verbose_name_plural = 'Horários de Funcionamento'
        ordering = ['dia']
        unique_together = ['barbearia', 'barbeiro', 'dia']

    def __str__(self):
        return f'{self.get_dia_display()} - {self.barbearia.nome}'


class StatusFila(models.Model):
    barbearia = models.OneToOneField(Barbearia, on_delete=models.CASCADE, related_name='status_fila')
    cortando = models.IntegerField(default=0)
    espera = models.IntegerField(default=0)
    aberto = models.BooleanField(default=False)
    mostrar_horarios = models.BooleanField(default=True)
    ultima_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Status da Fila'
        verbose_name_plural = 'Status das Filas'

    def __str__(self):
        return f'Fila - {self.barbearia.nome}'
