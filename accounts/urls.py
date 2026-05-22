from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('landing/', views.landing, name='landing'),
    path('cadastro/', views.cadastro, name='cadastro'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('pagamento/', views.pagamento, name='pagamento'),
    path('verificar-email/aviso/', views.verificar_email_aviso, name='verificar_email_aviso'),
    path('verificar-email/<str:token>/', views.verificar_email, name='verificar_email'),
    path('reenviar-verificacao/', views.reenviar_verificacao, name='reenviar_verificacao'),
    path('conta-bloqueada/', views.conta_bloqueada, name='conta_bloqueada'),
    path('esqueci-senha/', views.esqueci_senha, name='esqueci_senha'),
    path('redefinir-senha/<str:token>/', views.redefinir_senha, name='redefinir_senha'),
    path('dev/', views.dev_admin, name='dev_admin'),
    path('dev/inspecionar/<int:barbearia_id>/', views.dev_inspecionar, name='dev_inspecionar'),
    path('dev/login/', views.dev_admin_login, name='dev_admin_login'),
    path('dev/logout/', views.dev_admin_logout, name='dev_admin_logout'),
    path('pagamento/gerar-pix/', views.gerar_pagamento_pix, name='gerar_pagamento_pix'),
    path('pagamento/gerar-cartao/', views.gerar_pagamento_cartao, name='gerar_pagamento_cartao'),
    path('pagamento/status-mp/<str:payment_id>/', views.verificar_status_mp, name='verificar_status_mp'),
    path('pagamento/webhook-mp/', views.webhook_mp, name='webhook_mp'),
    path('pagamento/webhook-asaas/', views.webhook_asaas, name='webhook_asaas'),
]
