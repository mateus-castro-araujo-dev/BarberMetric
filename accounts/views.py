import json
import re
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
ABACATE_API_BASE = 'https://api.abacatepay.com/v1'
ASAAS_API_BASE = 'https://api.asaas.com/v3'
ASAAS_SANDBOX_BASE = 'https://api-sandbox.asaas.com/v3'


def index(request):
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, 'accounts/landing.html')

def landing(request):
    """Landing page sempre visível, mesmo para usuários logados."""
    return render(request, 'accounts/landing.html')


def cadastro(request):
    if request.user.is_authenticated:
        return redirect('home')

    plano_intencao = request.GET.get('plano', '').strip()
    if plano_intencao not in ('pro', 'max'):
        plano_intencao = ''

    if request.method == 'POST':
        form = CadastroForm(request.POST)
        plano_intencao = request.POST.get('plano_intencao', '').strip()
        if plano_intencao not in ('pro', 'max'):
            plano_intencao = ''

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

            nome_proprietario = d['nome_proprietario'].split()[0]
            Barbeiro.objects.create(barbearia=barbearia, nome=nome_proprietario)

            _enviar_email_verificacao(request, barbearia)

            login(request, user)

            if plano_intencao in ('pro', 'max'):
                request.session['plano_intencao'] = plano_intencao

            messages.success(request, 'Bem-vindo! Confirme seu e-mail para ativar sua conta.')
            request.session['pwa_prompt'] = True
            return redirect('verificar_email_aviso')
    else:
        form = CadastroForm()

    return render(request, 'accounts/cadastro.html', {'form': form, 'plano_intencao': plano_intencao})


def _enviar_email_verificacao(request, barbearia):
    token = barbearia.token_verificacao
    link = request.build_absolute_uri(f'/verificar-email/{token}/')
    try:
        send_mail(
            subject='Barber Metric — Confirme seu e-mail',
            message=(
                f'Olá, {barbearia.user.first_name}!\n\n'
                f'Clique no link abaixo para confirmar seu e-mail e ativar sua conta:\n\n'
                f'{link}\n\n'
                f'O link expira em 48 horas.\n\n'
                f'Equipe Barber Metric'
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

    login(request, barbearia.user)
    messages.success(request, 'E-mail verificado! Escolha seu plano para continuar.')
    return redirect('pagamento')


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
            subject='Barber Metric — Redefinição de senha',
            message=(
                f'Olá, {barbearia.user.first_name}!\n\n'
                f'Recebemos uma solicitação para redefinir a senha da sua conta.\n\n'
                f'Clique no link abaixo para criar uma nova senha:\n\n'
                f'{link}\n\n'
                f'Este link expira em 2 horas.\n\n'
                f'Se você não solicitou isso, ignore este e-mail.\n\n'
                f'Equipe Barber Metric'
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

    if request.method == 'POST':
        SolicitacaoPagamento.objects.create(
            barbearia=barbearia,
            mensagem=request.POST.get('mensagem', ''),
        )
        barbearia.pagamento_solicitado = True
        barbearia.data_pagamento_solicitado = timezone.now()
        barbearia.save()
        messages.success(request, 'Solicitação enviada! Entraremos em contato em até 24h.')

    # Prioridade: GET ?plano= > sessão > vazio
    plano_intencao = request.GET.get('plano', '').strip()
    if plano_intencao not in ('pro', 'max'):
        plano_intencao = request.session.pop('plano_intencao', '')
    else:
        request.session.pop('plano_intencao', None)

    pagamento_mp = barbearia.pagamentos_mp.filter(status='pending').first()
    return render(request, 'accounts/pagamento.html', {
        'barbearia': barbearia,
        'pagamento_mp': pagamento_mp,
        'mp_configurado': bool(getattr(django_settings, 'MP_ACCESS_TOKEN', '')),
        'mp_public_key': getattr(django_settings, 'MP_PUBLIC_KEY', ''),
        'valor_pro': getattr(django_settings, 'ASSINATURA_VALOR_PRO', 14.90),
        'valor_max': getattr(django_settings, 'ASSINATURA_VALOR_MAX', 34.90),
        'plano_intencao': plano_intencao,
    })


# ─── Asaas (PIX) ─────────────────────────────────────────────────────────────

def _asaas_headers(api_key):
    return {'access_token': api_key, 'Content-Type': 'application/json'}

def _asaas_base(api_key):
    """Usa produção se a chave contém '_prod_', caso contrário sandbox."""
    if '_prod_' in api_key:
        return ASAAS_API_BASE
    return ASAAS_SANDBOX_BASE

def _asaas_get_or_create_customer(api_key, barbearia):
    """Busca cliente existente pelo CPF ou cria novo."""
    base = _asaas_base(api_key)
    headers = _asaas_headers(api_key)
    try:
        cpf = re.sub(r'\D', '', barbearia.cpf_proprietario or '')
    except Exception:
        cpf = ''

    # Tenta buscar cliente existente pelo CPF
    if cpf:
        try:
            resp = http_requests.get(
                f'{base}/customers',
                params={'cpfCnpj': cpf},
                headers=headers,
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                clientes = data.get('data', [])
                if clientes:
                    return clientes[0]['id'], None
        except Exception:
            pass

    # Cria novo cliente
    nome = f"{barbearia.user.first_name or ''} {barbearia.user.last_name or ''}".strip() or barbearia.nome
    payload = {
        'name': nome,
        'email': barbearia.user.email,
        'cpfCnpj': cpf,
        'externalReference': f'barbearia-{barbearia.pk}',
    }
    telefone = re.sub(r'\D', '', getattr(barbearia, 'telefone', '') or '')
    if telefone:
        payload['mobilePhone'] = telefone

    try:
        resp = http_requests.post(f'{base}/customers', json=payload, headers=headers, timeout=10)
        try:
            data = resp.json()
        except Exception:
            return None, f'Resposta inválida do gateway (HTTP {resp.status_code})'
        if resp.ok:
            return data['id'], None
        return None, data.get('errors', [{'description': str(data)}])[0].get('description', str(data))
    except Exception as e:
        return None, str(e)


@login_required(login_url='/login/')
def gerar_pagamento_pix(request):
    """Cria um pagamento PIX via Asaas e retorna QR code."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Método inválido'}, status=405)

    api_key = getattr(django_settings, 'ASAAS_API_KEY', '')
    if not api_key:
        return JsonResponse({'ok': False, 'erro': 'Gateway de pagamento não configurado.'}, status=503)

    try:
        barbearia = request.user.barbearia
    except Exception:
        return JsonResponse({'ok': False, 'erro': 'Barbearia não encontrada.'}, status=400)

    if barbearia.plano in (Barbearia.PLANO_PRO, Barbearia.PLANO_MAX, Barbearia.PLANO_ATIVO):
        return JsonResponse({'ok': False, 'erro': 'Assinatura já ativa.'})

    # Cancela pagamentos pendentes antigos
    barbearia.pagamentos_mp.filter(status='pending').update(status='cancelled')

    try:
        body = json.loads(request.body or '{}')
    except Exception:
        body = {}
    plano_escolhido = body.get('plano', 'pro')
    if plano_escolhido not in ('pro', 'max'):
        plano_escolhido = 'pro'

    if plano_escolhido == 'max':
        valor = float(getattr(django_settings, 'ASSINATURA_VALOR_MAX', 34.90))
        descricao_plano = 'Max'
    else:
        valor = float(getattr(django_settings, 'ASSINATURA_VALOR_PRO', 14.90))
        descricao_plano = 'Pro'

    base = _asaas_base(api_key)
    headers = _asaas_headers(api_key)

    # 1. Obter ou criar cliente no Asaas
    customer_id, erro_cliente = _asaas_get_or_create_customer(api_key, barbearia)
    if not customer_id:
        return JsonResponse({'ok': False, 'erro': f'Erro ao criar cliente: {erro_cliente}'}, status=502)

    # 2. Criar cobrança PIX
    due_date = (timezone.now() + timezone.timedelta(days=1)).strftime('%Y-%m-%d')
    payload_cobranca = {
        'customer': customer_id,
        'billingType': 'PIX',
        'value': valor,
        'dueDate': due_date,
        'description': f'Barber Metric — Plano {descricao_plano}',
        'externalReference': f'barbearia-{barbearia.pk}-{plano_escolhido}',
    }

    try:
        resp = http_requests.post(f'{base}/payments', json=payload_cobranca, headers=headers, timeout=15)
        try:
            data = resp.json()
        except Exception:
            return JsonResponse({'ok': False, 'erro': f'Resposta inválida do gateway (HTTP {resp.status_code}).'}, status=502)
        if not resp.ok:
            erros = data.get('errors', [])
            detalhe = erros[0].get('description', str(data)) if erros else str(data)
            return JsonResponse({'ok': False, 'erro': f'Erro {resp.status_code}: {detalhe}'}, status=502)
    except http_requests.RequestException as e:
        return JsonResponse({'ok': False, 'erro': f'Erro de conexão: {str(e)}'}, status=502)

    payment_id = str(data.get('id', ''))
    if not payment_id:
        return JsonResponse({'ok': False, 'erro': 'Resposta inválida do gateway.'}, status=502)

    # 3. Obter QR code PIX
    qr_code = ''
    qr_base64 = ''
    try:
        resp_qr = http_requests.get(
            f'{base}/payments/{payment_id}/pixQrCode',
            headers=headers,
            timeout=10,
        )
        if resp_qr.ok:
            qr_data = resp_qr.json()
            qr_code = qr_data.get('payload', '')
            qr_base64 = qr_data.get('encodedImage', '')
    except Exception:
        pass

    PagamentoMP.objects.create(
        barbearia=barbearia,
        payment_id=payment_id,
        status='pending',
        plano_escolhido=plano_escolhido,
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
        'plano': plano_escolhido,
    })


@login_required(login_url='/login/')
def gerar_pagamento_cartao(request):
    """Cria um pagamento com cartão de crédito via Asaas."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'Método inválido'}, status=405)

    api_key = getattr(django_settings, 'ASAAS_API_KEY', '')
    if not api_key:
        return JsonResponse({'ok': False, 'erro': 'Gateway de pagamento não configurado.'}, status=503)

    try:
        barbearia = request.user.barbearia
    except Exception:
        return JsonResponse({'ok': False, 'erro': 'Barbearia não encontrada.'}, status=400)

    if barbearia.plano in (Barbearia.PLANO_PRO, Barbearia.PLANO_MAX, Barbearia.PLANO_ATIVO):
        return JsonResponse({'ok': False, 'erro': 'Assinatura já ativa.'})

    try:
        body = json.loads(request.body or '{}')
    except Exception:
        return JsonResponse({'ok': False, 'erro': 'JSON inválido.'}, status=400)

    plano_escolhido = body.get('plano', 'pro')
    if plano_escolhido not in ('pro', 'max'):
        plano_escolhido = 'pro'

    # Dados do cartão
    holder_name    = body.get('holder_name', '').strip()
    card_number    = re.sub(r'\D', '', body.get('card_number', ''))
    expiry_month   = body.get('expiry_month', '').strip()
    expiry_year    = body.get('expiry_year', '').strip()
    ccv            = body.get('ccv', '').strip()
    cpf_cartao     = re.sub(r'\D', '', body.get('cpf', ''))
    cep            = re.sub(r'\D', '', body.get('cep', ''))
    numero_end     = body.get('numero_endereco', 'S/N').strip()
    recorrente     = bool(body.get('recorrente', False))
    remote_ip      = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '127.0.0.1')).split(',')[0].strip()

    if not all([holder_name, card_number, expiry_month, expiry_year, ccv]):
        return JsonResponse({'ok': False, 'erro': 'Preencha todos os dados do cartão.'}, status=400)

    if plano_escolhido == 'max':
        valor = float(getattr(django_settings, 'ASSINATURA_VALOR_MAX', 34.90))
        descricao_plano = 'Max'
    else:
        valor = float(getattr(django_settings, 'ASSINATURA_VALOR_PRO', 14.90))
        descricao_plano = 'Pro'

    barbearia.pagamentos_mp.filter(status='pending').update(status='cancelled')

    base    = _asaas_base(api_key)
    headers = _asaas_headers(api_key)

    # 1. Obter ou criar cliente
    customer_id, erro_cliente = _asaas_get_or_create_customer(api_key, barbearia)
    if not customer_id:
        return JsonResponse({'ok': False, 'erro': f'Erro ao criar cliente: {erro_cliente}'}, status=502)

    try:
        cpf_barbearia = re.sub(r'\D', '', barbearia.cpf_proprietario or '')
    except Exception:
        cpf_barbearia = ''

    nome_completo = f"{barbearia.user.first_name or ''} {barbearia.user.last_name or ''}".strip() or barbearia.nome
    telefone = re.sub(r'\D', '', getattr(barbearia, 'telefone', '') or '')

    card_data = {
        'holderName': holder_name,
        'number': card_number,
        'expiryMonth': expiry_month,
        'expiryYear': expiry_year,
        'ccv': ccv,
    }
    holder_info = {
        'name': nome_completo,
        'email': barbearia.user.email,
        'cpfCnpj': cpf_cartao or cpf_barbearia,
        'postalCode': cep or '01310100',
        'addressNumber': numero_end,
        'phone': telefone or '11999999999',
    }
    due_date = timezone.now().strftime('%Y-%m-%d')

    payment_id   = ''
    status_asaas = ''
    sub_id       = ''

    if recorrente:
        # 2a. Criar assinatura recorrente mensal
        # Cancela assinatura anterior se existir
        if barbearia.asaas_sub_id:
            try:
                http_requests.delete(
                    f'{base}/subscriptions/{barbearia.asaas_sub_id}',
                    headers=headers, timeout=10,
                )
            except Exception:
                pass

        payload_sub = {
            'customer': customer_id,
            'billingType': 'CREDIT_CARD',
            'value': valor,
            'nextDueDate': due_date,
            'cycle': 'MONTHLY',
            'description': f'Barber Metric — Plano {descricao_plano} (Mensal)',
            'externalReference': f'barbearia-{barbearia.pk}-{plano_escolhido}',
            'creditCard': card_data,
            'creditCardHolderInfo': holder_info,
            'remoteIp': remote_ip,
        }

        try:
            resp = http_requests.post(f'{base}/subscriptions', json=payload_sub, headers=headers, timeout=20)
            try:
                data = resp.json()
            except Exception:
                return JsonResponse({'ok': False, 'erro': f'Resposta inválida do gateway (HTTP {resp.status_code}).'}, status=502)
            if not resp.ok:
                erros = data.get('errors', [])
                detalhe = erros[0].get('description', str(data)) if erros else str(data)
                return JsonResponse({'ok': False, 'erro': detalhe}, status=502)
        except http_requests.RequestException as e:
            return JsonResponse({'ok': False, 'erro': f'Erro de conexão: {str(e)}'}, status=502)

        sub_id     = str(data.get('id', ''))
        status_sub = data.get('status', '')
        payment_id = sub_id  # usa o ID da assinatura como referência

        # Verifica se a primeira cobrança foi realmente aprovada
        aprovado = False
        if sub_id:
            try:
                resp_pag = http_requests.get(
                    f'{base}/subscriptions/{sub_id}/payments',
                    headers=headers,
                    timeout=10,
                )
                if resp_pag.ok:
                    plist = resp_pag.json().get('data', [])
                    if plist:
                        primeiro_status = plist[0].get('status', '')
                        aprovado = primeiro_status in ('RECEIVED', 'CONFIRMED')
                        if not aprovado and primeiro_status in ('PAYMENT_REJECTED', 'DECLINED', 'REFUNDED'):
                            # Cancela assinatura inválida
                            try:
                                http_requests.delete(f'{base}/subscriptions/{sub_id}', headers=headers, timeout=10)
                            except Exception:
                                pass
                            return JsonResponse({'ok': False, 'erro': 'Cartão recusado. Verifique os dados ou tente outro cartão.'}, status=402)
                    else:
                        # Sem pagamentos listados ainda — confia no status da assinatura
                        aprovado = status_sub == 'ACTIVE'
            except Exception:
                # Falha ao buscar pagamentos — usa status da assinatura como fallback
                aprovado = status_sub == 'ACTIVE'

    else:
        # 2b. Cobrança avulsa (sem recorrência)
        payload = {
            'customer': customer_id,
            'billingType': 'CREDIT_CARD',
            'value': valor,
            'dueDate': due_date,
            'description': f'Barber Metric — Plano {descricao_plano}',
            'externalReference': f'barbearia-{barbearia.pk}-{plano_escolhido}',
            'creditCard': card_data,
            'creditCardHolderInfo': holder_info,
            'remoteIp': remote_ip,
        }

        try:
            resp = http_requests.post(f'{base}/payments', json=payload, headers=headers, timeout=20)
            try:
                data = resp.json()
            except Exception:
                return JsonResponse({'ok': False, 'erro': f'Resposta inválida do gateway (HTTP {resp.status_code}).'}, status=502)
            if not resp.ok:
                erros = data.get('errors', [])
                detalhe = erros[0].get('description', str(data)) if erros else str(data)
                return JsonResponse({'ok': False, 'erro': detalhe}, status=502)
        except http_requests.RequestException as e:
            return JsonResponse({'ok': False, 'erro': f'Erro de conexão: {str(e)}'}, status=502)

        payment_id   = str(data.get('id', ''))
        status_asaas = data.get('status', '')
        aprovado     = status_asaas in ('RECEIVED', 'CONFIRMED')

    if not payment_id:
        return JsonResponse({'ok': False, 'erro': 'Resposta inválida do gateway.'}, status=502)

    status_interno = 'approved' if aprovado else 'pending'

    PagamentoMP.objects.create(
        barbearia=barbearia,
        payment_id=payment_id,
        status=status_interno,
        plano_escolhido=plano_escolhido,
        qr_code='',
        qr_code_base64='',
        valor=valor,
    )

    if aprovado:
        novo_plano = Barbearia.PLANO_MAX if plano_escolhido == 'max' else Barbearia.PLANO_PRO
        update_fields = ['plano', 'ativo', 'asaas_customer_id']
        barbearia.plano = novo_plano
        barbearia.ativo = True
        barbearia.asaas_customer_id = customer_id
        if sub_id:
            barbearia.asaas_sub_id = sub_id
            from datetime import date
            from dateutil.relativedelta import relativedelta
            barbearia.proxima_cobranca = date.today() + relativedelta(months=1)
            update_fields += ['asaas_sub_id', 'proxima_cobranca']
        barbearia.save(update_fields=update_fields)

    return JsonResponse({
        'ok': True,
        'payment_id': payment_id,
        'status': status_interno,
        'aprovado': aprovado,
        'recorrente': recorrente,
        'pendente': not aprovado,
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

    api_key = getattr(django_settings, 'ASAAS_API_KEY', '')
    if api_key:
        try:
            base = _asaas_base(api_key)
            resp = http_requests.get(
                f'{base}/payments/{payment_id}',
                headers=_asaas_headers(api_key),
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                status_asaas = data.get('status', '')
                # Mapeia status Asaas → status interno
                if status_asaas in ('RECEIVED', 'CONFIRMED'):
                    novo_status = 'approved'
                elif status_asaas in ('OVERDUE', 'REFUNDED', 'REFUND_REQUESTED', 'CHARGEBACK_REQUESTED', 'CHARGEBACK_DISPUTE', 'DUNNING_REQUESTED', 'DUNNING_RECEIVED'):
                    novo_status = 'cancelled'
                else:
                    novo_status = 'pending'

                pag.status = novo_status
                pag.save(update_fields=['status', 'atualizado_em'])

                if novo_status == 'approved':
                    novo_plano = Barbearia.PLANO_MAX if pag.plano_escolhido == 'max' else Barbearia.PLANO_PRO
                    barbearia.plano = novo_plano
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
def webhook_asaas(request):
    """Webhook do Asaas — processa pagamentos e renovações de assinatura."""
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False}, status=400)

    event = body.get('event', '')
    payment_data = body.get('payment', {})
    subscription_data = body.get('subscription', {})

    # Eventos de pagamento confirmado
    if event in ('PAYMENT_RECEIVED', 'PAYMENT_CONFIRMED'):
        payment_id = payment_data.get('id', '')
        subscription_id = payment_data.get('subscription', '')
        external_ref = payment_data.get('externalReference', '')
        status_asaas = payment_data.get('status', '')

        # Tenta encontrar a barbearia pelo externalReference ou subscription
        barbearia = None
        if external_ref and external_ref.startswith('barbearia-'):
            try:
                pk = int(external_ref.split('-')[1])
                barbearia = Barbearia.objects.get(pk=pk)
            except Exception:
                pass

        if not barbearia and subscription_id:
            try:
                barbearia = Barbearia.objects.get(asaas_sub_id=subscription_id)
            except Exception:
                pass

        if barbearia:
            # Renova acesso
            plano_ref = external_ref.split('-')[-1] if external_ref else 'pro'
            novo_plano = Barbearia.PLANO_MAX if plano_ref == 'max' else Barbearia.PLANO_PRO
            from datetime import date
            from dateutil.relativedelta import relativedelta
            update_fields = ['plano', 'ativo', 'proxima_cobranca']
            barbearia.plano = novo_plano
            barbearia.ativo = True
            barbearia.proxima_cobranca = date.today() + relativedelta(months=1)
            barbearia.save(update_fields=update_fields)

            # Registra pagamento
            if payment_id:
                PagamentoMP.objects.get_or_create(
                    payment_id=payment_id,
                    defaults={
                        'barbearia': barbearia,
                        'status': 'approved',
                        'plano_escolhido': plano_ref if plano_ref in ('pro', 'max') else 'pro',
                        'valor': payment_data.get('value', 0),
                    }
                )

    # Eventos de pagamento em atraso — suspende conta
    elif event in ('PAYMENT_OVERDUE',):
        subscription_id = payment_data.get('subscription', '')
        external_ref = payment_data.get('externalReference', '')

        barbearia = None
        if subscription_id:
            try:
                barbearia = Barbearia.objects.get(asaas_sub_id=subscription_id)
            except Exception:
                pass

        if barbearia:
            barbearia.plano = Barbearia.PLANO_SUSPENSO
            barbearia.save(update_fields=['plano'])

    # Assinatura cancelada
    elif event in ('SUBSCRIPTION_DELETED',):
        sub_id = subscription_data.get('id', '')
        if sub_id:
            try:
                barbearia = Barbearia.objects.get(asaas_sub_id=sub_id)
                barbearia.asaas_sub_id = None
                barbearia.save(update_fields=['asaas_sub_id'])
            except Exception:
                pass

    return JsonResponse({'ok': True})


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
            novo_plano = Barbearia.PLANO_MAX if pag.plano_escolhido == 'max' else Barbearia.PLANO_PRO
            pag.barbearia.plano = novo_plano
            pag.barbearia.ativo = True
            pag.barbearia.save(update_fields=['plano', 'ativo'])
    except PagamentoMP.DoesNotExist:
        if ext_ref and status == 'approved':
            try:
                barbearia = Barbearia.objects.get(pk=ext_ref)
                barbearia.plano = Barbearia.PLANO_PRO
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


def dev_inspecionar(request, barbearia_id):
    """Painel de inspeção detalhada de uma conta."""
    if not _verificar_dev(request):
        return redirect('dev_admin_login')

    from core.models import Barbeiro, Cliente, Servico, Produto, Atendimento, VendaProduto

    b = get_object_or_404(Barbearia, pk=barbearia_id)

    barbeiros      = b.barbeiros.all()
    clientes       = b.clientes.all()
    servicos       = b.servicos.all()
    produtos       = b.produtos.all()
    atendimentos   = b.atendimentos.all()
    vendas         = b.vendas_produto.all()
    pagamentos     = b.pagamentos_mp.all()

    # Faturamento total registrado
    faturamento_total = sum(
        a.valor_total for a in atendimentos if a.valor_total
    )
    faturamento_vendas = sum(
        v.valor_total for v in vendas if v.valor_total
    )

    # Armazenamento estimado (bytes por registro × quantidade)
    # Tamanhos médios por tabela medidos empiricamente no SQLite
    bytes_armazenamento = (
        barbeiros.count()    * 180  +
        clientes.count()     * 320  +
        servicos.count()     * 220  +
        produtos.count()     * 200  +
        atendimentos.count() * 480  +
        vendas.count()       * 300  +
        pagamentos.count()   * 260
    )

    def fmt_bytes(b):
        if b < 1024:
            return f'{b} B'
        elif b < 1024 * 1024:
            return f'{b/1024:.1f} KB'
        else:
            return f'{b/1024/1024:.2f} MB'

    # Último atendimento
    ultimo_atendimento = atendimentos.order_by('-data').first()

    info = {
        'barbeiros_total':    barbeiros.count(),
        'barbeiros_ativos':   barbeiros.filter(ativo=True).count(),
        'clientes_total':     clientes.count(),
        'servicos_total':     servicos.count(),
        'produtos_total':     produtos.count(),
        'atendimentos_total': atendimentos.count(),
        'atendimentos_mes':   atendimentos.filter(
            data__month=timezone.now().month,
            data__year=timezone.now().year,
        ).count(),
        'vendas_total':       vendas.count(),
        'pagamentos_total':   pagamentos.count(),
        'pagamentos_aprovados': pagamentos.filter(status='approved').count(),
        'faturamento_servicos': faturamento_total,
        'faturamento_vendas':   faturamento_vendas,
        'faturamento_geral':    faturamento_total + faturamento_vendas,
        'ultimo_atendimento':   ultimo_atendimento,
        'armazenamento_bytes':  bytes_armazenamento,
        'armazenamento_fmt':    fmt_bytes(bytes_armazenamento),
    }

    # Limites por plano
    limites = {
        'trial':    {'barbeiros': 1,  'clientes': 10,   'servicos': 4,  'produtos': 4},
        'pro':      {'barbeiros': 2,  'clientes': 100,  'servicos': 6,  'produtos': 6},
        'max':      {'barbeiros': 20, 'clientes': 1000, 'servicos': 20, 'produtos': 20},
        'ativo':    {'barbeiros': 20, 'clientes': 1000, 'servicos': 20, 'produtos': 20},
        'suspenso': {'barbeiros': 1,  'clientes': 10,   'servicos': 4,  'produtos': 4},
    }
    lim = limites.get(b.plano, limites['trial'])

    def pct(val, lim):
        return min(100, round(val / lim * 100)) if lim else 0

    barras_plano = [
        {'label': 'Barbeiros', 'valor': info['barbeiros_ativos'], 'limite': lim['barbeiros'], 'pct': pct(info['barbeiros_ativos'], lim['barbeiros']), 'cor': 'linear-gradient(90deg,#6366F1,#8B5CF6)'},
        {'label': 'Clientes',  'valor': info['clientes_total'],   'limite': lim['clientes'],  'pct': pct(info['clientes_total'],   lim['clientes']),  'cor': 'linear-gradient(90deg,#10B981,#34D399)'},
        {'label': 'Servicos',  'valor': info['servicos_total'],   'limite': lim['servicos'],  'pct': pct(info['servicos_total'],   lim['servicos']),  'cor': 'linear-gradient(90deg,#F59E0B,#FCD34D)'},
        {'label': 'Produtos',  'valor': info['produtos_total'],   'limite': lim['produtos'],  'pct': pct(info['produtos_total'],   lim['produtos']),  'cor': 'linear-gradient(90deg,#8B5CF6,#A78BFA)'},
    ]

    return render(request, 'accounts/dev_inspecionar.html', {
        'b':          b,
        'info':       info,
        'barras_plano': barras_plano,
        'barbeiros': barbeiros,
        'servicos':  servicos,
        'produtos':  produtos,
        'pagamentos': pagamentos.order_by('-criado_em')[:10],
    })


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
                elif action == 'set_pro':
                    b.plano = Barbearia.PLANO_PRO
                    b.ativo = True
                    b.save()
                elif action == 'set_max':
                    b.plano = Barbearia.PLANO_MAX
                    b.ativo = True
                    b.save()
                elif action == 'set_ativo':
                    b.plano = Barbearia.PLANO_MAX
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
        'pro': barbearias.filter(plano=Barbearia.PLANO_PRO).count(),
        'max': barbearias.filter(plano__in=[Barbearia.PLANO_MAX, Barbearia.PLANO_ATIVO]).count(),
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

