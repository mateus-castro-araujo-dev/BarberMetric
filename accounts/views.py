import json
import hashlib
import hmac
import requests as http_requests

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings as django_settings
from django.http import JsonResponse
from .forms import CadastroForm
from .models import Barbearia, SolicitacaoPagamento, PagamentoMP, hash_cpf, normalizar_telefone
from core.models import Barbeiro

MP_API_BASE = 'https://api.mercadopago.com'


def index(request):
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, 'accounts/landing.html')


def cadastro(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = CadastroForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            nome_usuario = d['email'].split('@')[0].lower().replace('.', '_')
            base = nome_usuario
            counter = 1
            while User.objects.filter(username=nome_usuario).exists():
                nome_usuario = f'{base}{counter}'
                counter += 1

            user = User.objects.create_user(
                username=nome_usuario,
                email=d['email'],
                password=d['senha'],
                first_name=d['nome_proprietario'].split()[0],
                last_name=' '.join(d['nome_proprietario'].split()[1:]),
            )

            barbearia = Barbearia(
                user=user,
                nome=d['nome_barbearia'],
                telefone=d['telefone'],
                telefone_normalizado=normalizar_telefone(d['telefone']),
                cidade=d['cidade'],
                estado=d['estado'],
            )
            barbearia.cpf_proprietario = d['cpf']
            barbearia.cpf_hash = hash_cpf(d['cpf'])
            barbearia.gerar_token_verificacao()
            barbearia.save()

            # Cria barbeiro padrão com o nome do proprietário
            nome_proprietario = d['nome_proprietario'].split()[0]
            Barbeiro.objects.create(barbearia=barbearia, nome=nome_proprietario)

            _enviar_email_verificacao(request, barbearia)

            login(request, user)
            messages.success(request, f'Bem-vindo! Confirme seu e-mail para ativar a conta. Seu trial de 30 dias começou!')
            return redirect('verificar_email_aviso')
    else:
        form = CadastroForm()

    return render(request, 'accounts/cadastro.html', {'form': form})


def _enviar_email_verificacao(request, barbearia):
    token = barbearia.token_verificacao
    link = request.build_absolute_uri(f'/verificar-email/{token}/')
    try:
        send_mail(
            subject='BarberCloud — Confirme seu e-mail',
            message=(
                f'Olá, {barbearia.user.first_name}!\n\n'
                f'Clique no link abaixo para confirmar seu e-mail e ativar sua conta:\n\n'
                f'{link}\n\n'
                f'O link expira em 48 horas.\n\n'
                f'Equipe BarberCloud'
            ),
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[barbearia.user.email],
            fail_silently=True,
        )
    except Exception:
        pass


def verificar_email_aviso(request):
    return render(request, 'accounts/verificar_email_aviso.html')


def verificar_email(request, token):
    try:
        barbearia = Barbearia.objects.get(token_verificacao=token)
    except Barbearia.DoesNotExist:
        messages.error(request, 'Link de verificação inválido.')
        return redirect('login')

    if barbearia.token_expira and timezone.now() > barbearia.token_expira:
        messages.error(request, 'Link de verificação expirado. Solicite um novo.')
        return redirect('reenviar_verificacao')

    barbearia.email_verificado = True
    barbearia.token_verificacao = None
    barbearia.token_expira = None
    barbearia.save()

    messages.success(request, 'E-mail verificado com sucesso! Bem-vindo ao BarberCloud.')
    return redirect('home')


@login_required(login_url='/login/')
def reenviar_verificacao(request):
    try:
        barbearia = request.user.barbearia
    except Exception:
        return redirect('cadastro')

    if barbearia.email_verificado:
        return redirect('home')

    if request.method == 'POST':
        barbearia.gerar_token_verificacao()
        barbearia.save()
        _enviar_email_verificacao(request, barbearia)
        messages.success(request, 'Novo e-mail de verificação enviado!')
        return redirect('verificar_email_aviso')

    return render(request, 'accounts/reenviar_verificacao.html', {'barbearia': barbearia})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    erro = None
    if request.method == 'POST':
        email = request.POST.get('email', '').lower()
        senha = request.POST.get('senha', '')
        try:
            user_obj = User.objects.get(email=email)
            user = authenticate(request, username=user_obj.username, password=senha)
            if user:
                login(request, user)
                return redirect(request.GET.get('next', 'home'))
            else:
                erro = 'Senha incorreta.'
        except User.DoesNotExist:
            erro = 'E-mail não encontrado.'

    return render(request, 'accounts/login.html', {'erro': erro})


def conta_bloqueada(request):
    return render(request, 'accounts/conta_bloqueada.html')


def esqueci_senha(request):
    if request.user.is_authenticated:
        return redirect('home')

    enviado = False
    erro = None

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        try:
            user_obj = User.objects.get(email=email)
            barbearia = user_obj.barbearia
            barbearia.gerar_token_reset_senha()
            barbearia.save()
            _enviar_email_reset_senha(request, barbearia)
            enviado = True
        except (User.DoesNotExist, Exception):
            # Não revelamos se o e-mail existe ou não
            enviado = True

    return render(request, 'accounts/esqueci_senha.html', {'enviado': enviado, 'erro': erro})


def _enviar_email_reset_senha(request, barbearia):
    token = barbearia.token_reset_senha
    link = request.build_absolute_uri(f'/redefinir-senha/{token}/')
    try:
        send_mail(
            subject='BarberCloud — Redefinição de senha',
            message=(
                f'Olá, {barbearia.user.first_name}!\n\n'
                f'Recebemos uma solicitação para redefinir a senha da sua conta.\n\n'
                f'Clique no link abaixo para criar uma nova senha:\n\n'
                f'{link}\n\n'
                f'Este link expira em 2 horas.\n\n'
                f'Se você não solicitou isso, ignore este e-mail.\n\n'
                f'Equipe BarberCloud'
            ),
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[barbearia.user.email],
            fail_silently=True,
        )
    except Exception:
        pass


def redefinir_senha(request, token):
    if request.user.is_authenticated:
        return redirect('home')

    try:
        barbearia = Barbearia.objects.get(token_reset_senha=token)
    except Barbearia.DoesNotExist:
        return render(request, 'accounts/redefinir_senha.html', {'token_invalido': True})

    if barbearia.token_reset_expira and timezone.now() > barbearia.token_reset_expira:
        return render(request, 'accounts/redefinir_senha.html', {'token_expirado': True})

    erro = None
    if request.method == 'POST':
        senha = request.POST.get('senha', '')
        confirma = request.POST.get('confirma', '')
        if len(senha) < 8:
            erro = 'A senha deve ter pelo menos 8 caracteres.'
        elif senha != confirma:
            erro = 'As senhas não coincidem.'
        else:
            barbearia.user.set_password(senha)
            barbearia.user.save()
            barbearia.token_reset_senha = None
            barbearia.token_reset_expira = None
            barbearia.save()
            messages.success(request, 'Senha redefinida com sucesso! Faça login.')
            return redirect('login')

    return render(request, 'accounts/redefinir_senha.html', {'token': token, 'erro': erro})


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required(login_url='/login/')
def pagamento(request):
    try:
        barbearia = request.user.barbearia
    except Exception:
        return redirect('cadastro')

    if barbearia.acesso_liberado:
        return redirect('home')

    if request.method == 'POST':
        SolicitacaoPagamento.objects.create(
            barbearia=barbearia,
            mensagem=request.POST.get('mensagem', ''),
        )
        barbearia.pagamento_solicitado = True
        barbearia.data_pagamento_solicitado = timezone.now()
        barbearia.save()
        messages.success(request, 'Solicitação enviada! Entraremos em contato em até 24h.')

    pagamento_mp = barbearia.pagamentos_mp.filter(status='pending').first()
    return render(request, 'accounts/pagamento.html', {
        'barbearia': barbearia,
        'pagamento_mp': pagamento_mp,
        'mp_configurado': bool(getattr(django_settings, 'MP_ACCESS_TOKEN', '')),
    })


# ─── Mercado Pago ────────────────────────────────────────────────────────────

@login_required(login_url='/login/')
def gerar_pagamento_pix(request):
    """Cria um pagamento PIX no Mercado Pago e retorna QR code."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Método inválido'}, status=405)

    token = getattr(django_settings, 'MP_ACCESS_TOKEN', '')
    if not token:
        return JsonResponse({'ok': False, 'erro': 'Mercado Pago não configurado.'}, status=503)

    try:
        barbearia = request.user.barbearia
    except Exception:
        return JsonResponse({'ok': False, 'erro': 'Barbearia não encontrada.'}, status=400)

    if barbearia.acesso_liberado:
        return JsonResponse({'ok': False, 'erro': 'Assinatura já ativa.'})

    # Cancela pagamentos pendentes antigos
    barbearia.pagamentos_mp.filter(status='pending').update(status='cancelled')

    valor = float(getattr(django_settings, 'ASSINATURA_VALOR', 20.00))

    payload = {
        'transaction_amount': valor,
        'description': f'BarberCloud — Assinatura Mensal — {barbearia.nome}',
        'payment_method_id': 'pix',
        'payer': {
            'email': barbearia.user.email,
            'first_name': barbearia.user.first_name or 'Cliente',
            'last_name': barbearia.user.last_name or 'BarberCloud',
        },
        'notification_url': request.build_absolute_uri('/pagamento/webhook-mp/'),
        'external_reference': str(barbearia.pk),
        'metadata': {'barbearia_id': barbearia.pk, 'barbearia_nome': barbearia.nome},
    }

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'X-Idempotency-Key': f'barbercloud-{barbearia.pk}-{int(timezone.now().timestamp())}',
    }

    try:
        resp = http_requests.post(
            f'{MP_API_BASE}/v1/payments',
            json=payload,
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except http_requests.RequestException as e:
        return JsonResponse({'ok': False, 'erro': f'Erro ao criar pagamento: {str(e)}'}, status=502)

    poi = data.get('point_of_interaction', {}).get('transaction_data', {})
    qr_code = poi.get('qr_code', '')
    qr_base64 = poi.get('qr_code_base64', '')
    payment_id = str(data.get('id', ''))

    if not payment_id:
        return JsonResponse({'ok': False, 'erro': 'Resposta inválida do Mercado Pago.'}, status=502)

    PagamentoMP.objects.create(
        barbearia=barbearia,
        payment_id=payment_id,
        status=data.get('status', 'pending'),
        qr_code=qr_code,
        qr_code_base64=qr_base64,
        valor=valor,
    )

    return JsonResponse({
        'ok': True,
        'payment_id': payment_id,
        'qr_code': qr_code,
        'qr_code_base64': qr_base64,
        'valor': valor,
    })


@login_required(login_url='/login/')
def verificar_status_mp(request, payment_id):
    """Verifica o status de um pagamento MP."""
    try:
        barbearia = request.user.barbearia
    except Exception:
        return JsonResponse({'ok': False}, status=400)

    try:
        pag = PagamentoMP.objects.get(payment_id=payment_id, barbearia=barbearia)
    except PagamentoMP.DoesNotExist:
        return JsonResponse({'ok': False, 'erro': 'Pagamento não encontrado.'}, status=404)

    token = getattr(django_settings, 'MP_ACCESS_TOKEN', '')
    if token:
        try:
            resp = http_requests.get(
                f'{MP_API_BASE}/v1/payments/{payment_id}',
                headers={'Authorization': f'Bearer {token}'},
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                novo_status = data.get('status', pag.status)
                pag.status = novo_status
                pag.save(update_fields=['status', 'atualizado_em'])

                if novo_status == 'approved':
                    barbearia.plano = Barbearia.PLANO_ATIVO
                    barbearia.ativo = True
                    barbearia.save(update_fields=['plano', 'ativo'])
        except Exception:
            pass

    return JsonResponse({
        'ok': True,
        'status': pag.status,
        'aprovado': pag.status == 'approved',
    })


@csrf_exempt
def webhook_mp(request):
    """Webhook do Mercado Pago para confirmar pagamentos."""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    secret = getattr(django_settings, 'MP_WEBHOOK_SECRET', '')
    if secret:
        sig_header = request.headers.get('X-Signature', '')
        ts = ''
        v1 = ''
        for part in sig_header.split(','):
            part = part.strip()
            if part.startswith('ts='):
                ts = part[3:]
            elif part.startswith('v1='):
                v1 = part[3:]
        manifest = f'id:{request.GET.get("data.id", "")};request-id:{request.headers.get("X-Request-Id", "")};ts:{ts};'
        expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, v1):
            return JsonResponse({'ok': False}, status=403)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False}, status=400)

    topic = body.get('type') or request.GET.get('topic')
    payment_id = None
    if topic == 'payment':
        payment_id = str(body.get('data', {}).get('id') or request.GET.get('id'))

    if not payment_id:
        return JsonResponse({'ok': True})

    token = getattr(django_settings, 'MP_ACCESS_TOKEN', '')
    if not token:
        return JsonResponse({'ok': False}, status=503)

    try:
        resp = http_requests.get(
            f'{MP_API_BASE}/v1/payments/{payment_id}',
            headers={'Authorization': f'Bearer {token}'},
            timeout=10,
        )
        if not resp.ok:
            return JsonResponse({'ok': False}, status=502)
        data = resp.json()
    except Exception:
        return JsonResponse({'ok': False}, status=502)

    status = data.get('status')
    ext_ref = data.get('external_reference')

    try:
        pag = PagamentoMP.objects.get(payment_id=payment_id)
        pag.status = status
        pag.save(update_fields=['status', 'atualizado_em'])

        if status == 'approved':
            pag.barbearia.plano = Barbearia.PLANO_ATIVO
            pag.barbearia.ativo = True
            pag.barbearia.save(update_fields=['plano', 'ativo'])
    except PagamentoMP.DoesNotExist:
        if ext_ref and status == 'approved':
            try:
                barbearia = Barbearia.objects.get(pk=ext_ref)
                barbearia.plano = Barbearia.PLANO_ATIVO
                barbearia.ativo = True
                barbearia.save(update_fields=['plano', 'ativo'])
            except Barbearia.DoesNotExist:
                pass

    return JsonResponse({'ok': True})


# ─── Painel do Desenvolvedor ────────────────────────────────────────────────

def _verificar_dev(request):
    """Retorna True se o request tem acesso de desenvolvedor."""
    secret = getattr(django_settings, 'DEV_ADMIN_SECRET', '')
    # via sessão autenticada
    if request.session.get('dev_admin_auth'):
        return True
    # via query param (login)
    if secret and request.GET.get('secret') == secret:
        request.session['dev_admin_auth'] = True
        return True
    return False


def dev_admin_login(request):
    erro = None
    if request.method == 'POST':
        secret = getattr(django_settings, 'DEV_ADMIN_SECRET', '')
        if request.POST.get('secret') == secret:
            request.session['dev_admin_auth'] = True
            return redirect('dev_admin')
        erro = 'Senha incorreta.'
    return render(request, 'accounts/dev_admin_login.html', {'erro': erro})


def dev_admin_logout(request):
    request.session.pop('dev_admin_auth', None)
    return redirect('dev_admin_login')


def dev_admin(request):
    if not _verificar_dev(request):
        return redirect('dev_admin_login')

    barbearias = Barbearia.objects.select_related('user').order_by('-data_cadastro')
    solicitacoes_pendentes = SolicitacaoPagamento.objects.filter(atendido=False).count()

    # Ações POST
    if request.method == 'POST':
        action = request.POST.get('action')
        bid = request.POST.get('barbearia_id')
        if bid:
            try:
                b = Barbearia.objects.get(pk=bid)
                if action == 'toggle_ativo':
                    b.ativo = not b.ativo
                    b.save()
                elif action == 'set_ativo':
                    b.plano = Barbearia.PLANO_ATIVO
                    b.ativo = True
                    b.save()
                elif action == 'set_trial':
                    b.plano = Barbearia.PLANO_TRIAL
                    b.ativo = True
                    b.save()
                elif action == 'set_suspenso':
                    b.plano = Barbearia.PLANO_SUSPENSO
                    b.ativo = True
                    b.save()
                elif action == 'set_cancelado':
                    b.plano = Barbearia.PLANO_CANCELADO
                    b.ativo = False
                    b.save()
                elif action == 'verificar_email':
                    b.email_verificado = True
                    b.token_verificacao = None
                    b.save()
                elif action == 'toggle_email_verificado':
                    b.email_verificado = not b.email_verificado
                    b.save()
                elif action == 'atender_pagamento':
                    SolicitacaoPagamento.objects.filter(barbearia=b, atendido=False).update(atendido=True)
                    b.plano = Barbearia.PLANO_ATIVO
                    b.ativo = True
                    b.save()
                elif action == 'apagar_conta':
                    b.user.delete()
            except Barbearia.DoesNotExist:
                pass
        anchor = f'#{bid}' if bid else ''
        return redirect(f'/dev/{anchor}')

    stats = {
        'total': barbearias.count(),
        'ativos': barbearias.filter(plano=Barbearia.PLANO_ATIVO).count(),
        'trial': barbearias.filter(plano=Barbearia.PLANO_TRIAL).count(),
        'suspensos': barbearias.filter(plano=Barbearia.PLANO_SUSPENSO).count(),
        'cancelados': barbearias.filter(plano=Barbearia.PLANO_CANCELADO).count(),
        'inativos': barbearias.filter(ativo=False).count(),
        'email_nao_verificado': barbearias.filter(email_verificado=False).count(),
        'solicitacoes_pendentes': solicitacoes_pendentes,
    }

    return render(request, 'accounts/dev_admin.html', {
        'barbearias': barbearias,
        'stats': stats,
    })
