from django.contrib import admin
from .models import Barbearia, SolicitacaoPagamento


@admin.register(Barbearia)
class BarbeariaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'user', 'plano', 'cidade', 'estado', 'ativo', 'data_cadastro', 'dias_restantes_trial']
    list_filter = ['plano', 'estado', 'ativo']
    search_fields = ['nome', 'user__email', 'cidade']
    readonly_fields = ['data_cadastro', 'slug', 'cpf_formatado']
    list_editable = ['plano', 'ativo']
    actions = ['ativar_assinatura', 'suspender_assinatura']

    def cpf_formatado(self, obj):
        return obj.cpf_formatado
    cpf_formatado.short_description = 'CPF'

    def dias_restantes_trial(self, obj):
        return obj.dias_restantes_trial
    dias_restantes_trial.short_description = 'Dias trial'

    @admin.action(description='Ativar assinatura das selecionadas')
    def ativar_assinatura(self, request, queryset):
        queryset.update(plano='ativo')

    @admin.action(description='Suspender assinatura das selecionadas')
    def suspender_assinatura(self, request, queryset):
        queryset.update(plano='suspenso')


@admin.register(SolicitacaoPagamento)
class SolicitacaoPagamentoAdmin(admin.ModelAdmin):
    list_display = ['barbearia', 'data', 'atendido']
    list_filter = ['atendido']
    list_editable = ['atendido']
