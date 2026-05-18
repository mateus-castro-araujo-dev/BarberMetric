from django.contrib import admin
from .models import Barbeiro, Cliente, Servico, Atendimento, Produto, VendaProduto, HorarioFuncionamento, StatusFila


@admin.register(Barbeiro)
class BarbeiroAdmin(admin.ModelAdmin):
    list_display = ['nome', 'barbearia', 'ativo']
    list_filter = ['ativo', 'barbearia']


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ['nome', 'telefone', 'barbearia', 'barbeiro']
    list_filter = ['barbearia']
    search_fields = ['nome', 'telefone']


@admin.register(Servico)
class ServicoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'preco', 'barbearia', 'ativo']
    list_filter = ['barbearia', 'ativo']


@admin.register(Atendimento)
class AtendimentoAdmin(admin.ModelAdmin):
    list_display = ['cliente', 'barbeiro', 'barbearia', 'valor_total', 'forma_pagamento', 'data']
    list_filter = ['barbearia', 'forma_pagamento']
    date_hierarchy = 'data'


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'preco', 'barbearia', 'ativo']
    list_filter = ['barbearia', 'ativo']


@admin.register(VendaProduto)
class VendaProdutoAdmin(admin.ModelAdmin):
    list_display = ['produto', 'barbeiro', 'barbearia', 'quantidade', 'valor_total', 'data']
    list_filter = ['barbearia']
    date_hierarchy = 'data'


@admin.register(StatusFila)
class StatusFilaAdmin(admin.ModelAdmin):
    list_display = ['barbearia', 'cortando', 'espera', 'aberto', 'ultima_atualizacao']
