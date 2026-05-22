import csv
import json
from datetime import date, timedelta
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .models import Barbeiro, Cliente, Servico, Atendimento, Produto, VendaProduto, HorarioFuncionamento, StatusFila
from accounts.models import Barbearia

LOGIN_URL = '/login/'

TAXA_CREDITO = Decimal('0.0449')
TAXA_DEBITO = Decimal('0.0269')


def _get_barbearia(request):
    return request.user.barbearia


def _get_barbeiro(request, barbearia):
    barbeiro_id = request.session.get('barbeiro_id')
    if barbeiro_id == 'todos':
        return None
    if barbeiro_id:
        try:
            return Barbeiro.objects.get(id=barbeiro_id, barbearia=barbearia, ativo=True)
        except Barbeiro.DoesNotExist:
            pass
    return barbearia.barbeiros.filter(ativo=True).first()


def _filtrar_barbeiro(qs, barbeiro):
    """Filtra queryset por barbeiro; se None (Todos) não filtra."""
    if barbeiro is not None:
        return qs.filter(barbeiro=barbeiro)
    return qs


def _get_or_create_status(barbearia):
    status, _ = StatusFila.objects.get_or_create(barbearia=barbearia)
    return status


@login_required(login_url=LOGIN_URL)
def home(request):
    barbearia = _get_barbearia(request)
    barbeiro = _get_barbeiro(request, barbearia)
    servicos = Servico.objects.filter(barbearia=barbearia, ativo=True)
    produtos = Produto.objects.filter(barbearia=barbearia, ativo=True)
    clientes = _filtrar_barbeiro(Cliente.objects.filter(barbearia=barbearia), barbeiro).order_by('nome')

    ultimos = _filtrar_barbeiro(Atendimento.objects.filter(barbearia=barbearia), barbeiro).order_by('-data')[:5]
    hints = {}
    for a in ultimos:
        if a.cliente and a.cliente.nome not in hints:
            hints[a.cliente.nome] = a.servicos_prestados

    return render(request, 'core/home.html', {
        'servicos': servicos,
        'produtos': produtos,
        'clientes': clientes,
        'hints': json.dumps(hints),
    })


@login_required(login_url=LOGIN_URL)
@require_POST
def registrar_venda(request):
    barbearia = _get_barbearia(request)
    barbeiro = _get_barbeiro(request, barbearia)

    nome_cliente = request.POST.get('cliente_nome', '').strip() or 'Avulso'
    is_novo = request.POST.get('is_novo') == '1'
    servicos_ids = request.POST.getlist('servicos')
    pagamento = request.POST.get('pagamento', 'PIX')
    telefone = request.POST.get('telefone', '').strip()

    if not servicos_ids:
        return redirect('home')

    servicos = Servico.objects.filter(id__in=servicos_ids, barbearia=barbearia)
    valor = sum(s.preco for s in servicos)



    if is_novo:
        eh_avulso = (nome_cliente == 'Avulso')
        if not eh_avulso:
            limite_clientes = barbearia.limites['clientes_nome']
            total_clientes_nome = Cliente.objects.filter(
                barbearia=barbearia
            ).exclude(nome='Avulso').count()
            if total_clientes_nome >= limite_clientes:
                messages.error(request, 'clientes', extra_tags='upgrade')
                return redirect('home')
        cliente, _ = Cliente.objects.get_or_create(
            barbearia=barbearia, barbeiro=barbeiro, nome=nome_cliente,
            defaults={'telefone': telefone}
        )
    else:
        try:
            cliente = Cliente.objects.get(barbearia=barbearia, barbeiro=barbeiro, nome=nome_cliente)
        except Cliente.DoesNotExist:
            cliente, _ = Cliente.objects.get_or_create(
                barbearia=barbearia, barbeiro=barbeiro, nome=nome_cliente
            )

    nomes_servicos = ', '.join(s.nome for s in servicos)
    Atendimento.objects.create(
        barbearia=barbearia,
        barbeiro=barbeiro,
        cliente=cliente,
        servicos_prestados=nomes_servicos,
        valor_total=round(valor, 2),
        forma_pagamento=pagamento,
    )
    return redirect('home')


@login_required(login_url=LOGIN_URL)
@require_POST
def registrar_produto(request):
    barbearia = _get_barbearia(request)
    barbeiro = _get_barbeiro(request, barbearia)

    nome_cliente = request.POST.get('cliente_nome', '').strip() or 'Avulso'
    pagamento = request.POST.get('pagamento_produto', 'PIX')
    produto_ids = request.POST.getlist('produto_id')
    quantidades = request.POST.getlist('produto_qtd')

    cliente, _ = Cliente.objects.get_or_create(
        barbearia=barbearia,
        barbeiro=_get_barbeiro(request, barbearia),
        nome=nome_cliente,
    )

    salvos = 0
    for pid, qtd_str in zip(produto_ids, quantidades):
        try:
            qtd = int(qtd_str)
        except (ValueError, TypeError):
            continue
        if qtd <= 0:
            continue
        try:
            produto = Produto.objects.get(id=pid, barbearia=barbearia, ativo=True)
            VendaProduto.objects.create(
                barbearia=barbearia,
                barbeiro=barbeiro,
                cliente=cliente,
                produto=produto,
                quantidade=qtd,
                valor_total=produto.preco * qtd,
                forma_pagamento=pagamento,
            )
            salvos += 1
        except Exception:
            continue

    return redirect('home')


@login_required(login_url=LOGIN_URL)
def relatorios(request):
    barbearia = _get_barbearia(request)

    barbeiro = _get_barbeiro(request, barbearia)

    data_str = request.GET.get('data', '')
    try:
        data_sel = date.fromisoformat(data_str)
    except ValueError:
        data_sel = timezone.localdate()

    atendimentos = _filtrar_barbeiro(
        Atendimento.objects.filter(barbearia=barbearia, data__date=data_sel), barbeiro
    )
    vendas_prod = _filtrar_barbeiro(
        VendaProduto.objects.filter(barbearia=barbearia, data__date=data_sel), barbeiro
    )

    total_dia = atendimentos.aggregate(t=Sum('valor_total'))['t'] or 0
    total_prod = vendas_prod.aggregate(t=Sum('valor_total'))['t'] or 0
    total_geral = total_dia + total_prod

    hoje = timezone.localdate()
    semana = hoje - timedelta(days=7)
    mes = hoje.replace(day=1)

    clientes_hoje = atendimentos.values('cliente').distinct().count()
    clientes_semana = _filtrar_barbeiro(
        Atendimento.objects.filter(barbearia=barbearia, data__date__gte=semana), barbeiro
    ).values('cliente').distinct().count()
    clientes_mes = _filtrar_barbeiro(
        Atendimento.objects.filter(barbearia=barbearia, data__date__gte=mes), barbeiro
    ).values('cliente').distinct().count()

    def _soma(qs, **filtros):
        return qs.filter(**filtros).aggregate(t=Sum('valor_total'))['t'] or 0

    pix = (_soma(atendimentos, forma_pagamento='PIX')
           + _soma(vendas_prod, forma_pagamento='PIX'))
    dinheiro = (_soma(atendimentos, forma_pagamento='DINHEIRO')
                + _soma(vendas_prod, forma_pagamento='DINHEIRO'))
    cartao = (_soma(atendimentos, forma_pagamento__in=['CREDITO', 'DEBITO'])
              + _soma(vendas_prod, forma_pagamento__in=['CREDITO', 'DEBITO']))
    plano = _soma(atendimentos, forma_pagamento='PLANO')

    semana_labels = []
    semana_valores = []
    for i in range(6, -1, -1):
        d = hoje - timedelta(days=i)
        dias_pt = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
        semana_labels.append(f"{dias_pt[d.weekday()]} {d.strftime('%d/%m')}")
        v = _filtrar_barbeiro(
            Atendimento.objects.filter(barbearia=barbearia, data__date=d), barbeiro
        ).aggregate(t=Sum('valor_total'))['t'] or 0
        semana_valores.append(float(v))

    return render(request, 'core/relatorios.html', {
        'data_sel': data_sel,
        'atendimentos': atendimentos,
        'vendas_prod': vendas_prod,
        'total_geral': total_geral,
        'clientes_hoje': clientes_hoje,
        'clientes_semana': clientes_semana,
        'clientes_mes': clientes_mes,
        'pix': pix,
        'dinheiro': dinheiro,
        'cartao': cartao,
        'plano': plano,
        'semana_labels': json.dumps(semana_labels),
        'semana_valores': json.dumps(semana_valores),
    })


@login_required(login_url=LOGIN_URL)
def graficos(request):
    barbearia = _get_barbearia(request)
    barbeiro = _get_barbeiro(request, barbearia)

    hoje = timezone.localdate()
    ano = int(request.GET.get('ano', hoje.year))
    mes = int(request.GET.get('mes', hoje.month))

    import calendar
    _, dias_no_mes = calendar.monthrange(ano, mes)
    labels = []
    valores = []
    cortes = []

    for d in range(1, dias_no_mes + 1):
        dia = date(ano, mes, d)
        labels.append(str(d))
        v_at = _filtrar_barbeiro(
            Atendimento.objects.filter(barbearia=barbearia, data__date=dia), barbeiro
        ).aggregate(t=Sum('valor_total'))['t'] or 0
        v_prod = _filtrar_barbeiro(
            VendaProduto.objects.filter(barbearia=barbearia, data__date=dia), barbeiro
        ).aggregate(t=Sum('valor_total'))['t'] or 0
        c = _filtrar_barbeiro(
            Atendimento.objects.filter(barbearia=barbearia, data__date=dia), barbeiro
        ).count()
        valores.append(float(v_at) + float(v_prod))
        cortes.append(c)

    total_mes = sum(valores)
    melhor_dia = labels[valores.index(max(valores))] if any(v > 0 for v in valores) else '-'

    return render(request, 'core/graficos.html', {
        'labels': json.dumps(labels),
        'valores': json.dumps(valores),
        'cortes': json.dumps(cortes),
        'total_mes': total_mes,
        'melhor_dia': melhor_dia,
        'mes_atual': mes,
        'ano_atual': ano,
    })


@login_required(login_url=LOGIN_URL)
def excluir_atendimento(request, pk):
    barbearia = _get_barbearia(request)
    a = get_object_or_404(Atendimento, pk=pk, barbearia=barbearia)
    a.delete()
    return redirect(request.META.get('HTTP_REFERER', 'relatorios'))


@login_required(login_url=LOGIN_URL)
def excluir_venda_produto(request, pk):
    barbearia = _get_barbearia(request)
    v = get_object_or_404(VendaProduto, pk=pk, barbearia=barbearia)
    v.delete()
    return redirect(request.META.get('HTTP_REFERER', 'relatorios'))


@login_required(login_url=LOGIN_URL)
def lista_clientes(request):
    barbearia = _get_barbearia(request)
    barbeiro = _get_barbeiro(request, barbearia)
    hoje = timezone.localdate()
    inativos_limite = hoje - timedelta(days=30)
    semana_inicio = hoje - timedelta(days=7)

    clientes = _filtrar_barbeiro(Cliente.objects.filter(barbearia=barbearia), barbeiro).annotate(
        total_visitas=Count('atendimentos'),
    ).order_by('nome')

    for c in clientes:
        ultimo = c.atendimentos.order_by('-data').first()
        c.ultima_visita = ultimo.data.date() if ultimo else None
        c.dias_sem_visita = (hoje - c.ultima_visita).days if c.ultima_visita else None
        c.inativo = c.ultima_visita and c.ultima_visita < inativos_limite
        total_s = c.atendimentos.aggregate(t=Sum('valor_total'))['t'] or 0
        total_p = c.vendas_produto.aggregate(t=Sum('valor_total'))['t'] or 0
        c.total_gasto = total_s + total_p

    inativos_count = sum(1 for c in clientes if c.inativo)
    ativos_semana = sum(1 for c in clientes if c.ultima_visita and c.ultima_visita >= semana_inicio)

    return render(request, 'core/clientes.html', {
        'clientes': clientes,
        'inativos_count': inativos_count,
        'ativos_semana': ativos_semana,
    })


@login_required(login_url=LOGIN_URL)
def perfil_cliente(request, pk):
    barbearia = _get_barbearia(request)
    cliente = get_object_or_404(Cliente, pk=pk, barbearia=barbearia)

    atendimentos = cliente.atendimentos.all().order_by('-data')
    vendas = cliente.vendas_produto.all().order_by('-data')

    total_s = atendimentos.aggregate(t=Sum('valor_total'))['t'] or 0
    total_p = vendas.aggregate(t=Sum('valor_total'))['t'] or 0
    total_gasto = total_s + total_p
    total_visitas = atendimentos.count()
    ticket_medio = total_gasto / total_visitas if total_visitas else 0

    servico_favorito = None
    if atendimentos:
        from collections import Counter
        todos = []
        for a in atendimentos:
            todos.extend([s.strip() for s in a.servicos_prestados.split(',')])
        if todos:
            servico_favorito = Counter(todos).most_common(1)[0][0]

    ultimo = atendimentos.first()
    dias_sem_visita = None
    if ultimo:
        dias_sem_visita = (timezone.localdate() - ultimo.data.date()).days

    return render(request, 'core/perfil_cliente.html', {
        'cliente': cliente,
        'atendimentos': atendimentos,
        'vendas': vendas,
        'total_gasto': total_gasto,
        'total_visitas': total_visitas,
        'ticket_medio': ticket_medio,
        'servico_favorito': servico_favorito,
        'dias_sem_visita': dias_sem_visita,
    })


@login_required(login_url=LOGIN_URL)
def editar_cliente(request, pk):
    barbearia = _get_barbearia(request)
    cliente = get_object_or_404(Cliente, pk=pk, barbearia=barbearia)

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        telefone = request.POST.get('telefone', '').strip()
        if nome:
            cliente.nome = nome
            cliente.telefone = telefone
            cliente.save()
        return redirect('lista_clientes')

    return render(request, 'core/editar_cliente.html', {'cliente': cliente})


@login_required(login_url=LOGIN_URL)
def excluir_cliente(request, pk):
    barbearia = _get_barbearia(request)
    cliente = get_object_or_404(Cliente, pk=pk, barbearia=barbearia)

    if request.method == 'POST':
        cliente.delete()
        return redirect('lista_clientes')

    return render(request, 'core/confirmar_exclusao_cliente.html', {'cliente': cliente})


@login_required(login_url=LOGIN_URL)
def exportar_csv(request):
    barbearia = _get_barbearia(request)
    barbeiro = _get_barbeiro(request, barbearia)
    clientes = _filtrar_barbeiro(Cliente.objects.filter(barbearia=barbearia), barbeiro)

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="clientes.csv"'
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Nome', 'Telefone', 'Visitas', 'Total Gasto'])
    for c in clientes:
        visitas = c.atendimentos.count()
        gasto_s = c.atendimentos.aggregate(t=Sum('valor_total'))['t'] or 0
        gasto_p = c.vendas_produto.aggregate(t=Sum('valor_total'))['t'] or 0
        gasto = gasto_s + gasto_p
        writer.writerow([c.nome, c.telefone, visitas, f'R$ {gasto:.2f}'])
    return response


@login_required(login_url=LOGIN_URL)
def barbeiros(request):
    barbearia = _get_barbearia(request)
    lista = barbearia.barbeiros.all()
    limite_barbeiros = barbearia.limites['barbeiros']
    return render(request, 'core/barbeiros.html', {
        'lista_barbeiros': lista,
        'limite_barbeiros': limite_barbeiros,
        'nome_plano': barbearia.nome_plano,
    })


@login_required(login_url=LOGIN_URL)
@require_POST
def adicionar_barbeiro(request):
    barbearia = _get_barbearia(request)
    nome = request.POST.get('nome', '').strip()
    if nome:
        limite = barbearia.limites['barbeiros']
        total_atual = barbearia.barbeiros.count()
        if total_atual >= limite:
            messages.error(request, 'barbeiros', extra_tags='upgrade')
            return redirect('barbeiros')
        era_primeiro = not barbearia.barbeiros.exists()
        barbeiro, criado = Barbeiro.objects.get_or_create(barbearia=barbearia, nome=nome)
        if criado and era_primeiro:
            Cliente.objects.filter(barbearia=barbearia, barbeiro=None).update(barbeiro=barbeiro)
            Atendimento.objects.filter(barbearia=barbearia, barbeiro=None).update(barbeiro=barbeiro)
            VendaProduto.objects.filter(barbearia=barbearia, barbeiro=None).update(barbeiro=barbeiro)
    return redirect('barbeiros')


@login_required(login_url=LOGIN_URL)
@require_POST
def excluir_barbeiro(request, pk):
    barbearia = _get_barbearia(request)
    b = get_object_or_404(Barbeiro, pk=pk, barbearia=barbearia)
    b.delete()
    return redirect('barbeiros')


@login_required(login_url=LOGIN_URL)
def trocar_barbeiro(request, pk):
    barbearia = _get_barbearia(request)
    b = get_object_or_404(Barbeiro, pk=pk, barbearia=barbearia, ativo=True)
    request.session['barbeiro_id'] = b.id
    return redirect(request.META.get('HTTP_REFERER', 'home'))


@login_required(login_url=LOGIN_URL)
def trocar_para_todos(request):
    request.session['barbeiro_id'] = 'todos'
    return redirect(request.META.get('HTTP_REFERER', 'home'))


@login_required(login_url=LOGIN_URL)
def servicos(request):
    barbearia = _get_barbearia(request)
    lista = Servico.objects.filter(barbearia=barbearia)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            nome = request.POST.get('nome', '').strip()
            preco = request.POST.get('preco', '0').replace(',', '.')
            if nome:
                limite = barbearia.limites['servicos']
                if lista.count() >= limite:
                    messages.error(request, 'servicos', extra_tags='upgrade')
                else:
                    try:
                        Servico.objects.create(barbearia=barbearia, nome=nome, preco=Decimal(preco))
                    except Exception:
                        pass
        elif action == 'delete':
            sid = request.POST.get('id')
            Servico.objects.filter(id=sid, barbearia=barbearia).delete()
        return redirect('servicos')

    limite_servicos = barbearia.limites['servicos']
    return render(request, 'core/servicos.html', {
        'lista_servicos': lista,
        'limite_servicos': limite_servicos,
        'nome_plano': barbearia.nome_plano,
    })


@login_required(login_url=LOGIN_URL)
def produtos_view(request):
    barbearia = _get_barbearia(request)
    lista = Produto.objects.filter(barbearia=barbearia)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            nome = request.POST.get('nome', '').strip()
            preco = request.POST.get('preco', '0').replace(',', '.')
            descricao = request.POST.get('descricao', '').strip()
            if nome:
                limite = barbearia.limites['produtos']
                if lista.count() >= limite:
                    messages.error(request, 'produtos', extra_tags='upgrade')
                else:
                    try:
                        Produto.objects.create(barbearia=barbearia, nome=nome, preco=Decimal(preco), descricao=descricao)
                    except Exception:
                        pass
        elif action == 'delete':
            pid = request.POST.get('id')
            Produto.objects.filter(id=pid, barbearia=barbearia).delete()
        elif action == 'toggle':
            pid = request.POST.get('id')
            p = Produto.objects.filter(id=pid, barbearia=barbearia).first()
            if p:
                p.ativo = not p.ativo
                p.save()
        return redirect('produtos')

    limite_produtos = barbearia.limites['produtos']
    return render(request, 'core/produtos.html', {
        'lista_produtos': lista,
        'limite_produtos': limite_produtos,
        'nome_plano': barbearia.nome_plano,
    })


@login_required(login_url=LOGIN_URL)
def fila(request):
    barbearia = _get_barbearia(request)
    status = _get_or_create_status(barbearia)
    horarios = HorarioFuncionamento.objects.filter(barbearia=barbearia, barbeiro=None).order_by('dia')

    horarios_dict = {h.dia: h for h in horarios}
    semana = []
    for i in range(7):
        dia_nome = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'][i]
        semana.append({'dia': i, 'nome': dia_nome, 'horario': horarios_dict.get(i)})

    return render(request, 'core/fila.html', {'status': status, 'semana': semana})


@login_required(login_url=LOGIN_URL)
def salvar_fila_ajax(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False})
    barbearia = _get_barbearia(request)
    status = _get_or_create_status(barbearia)
    try:
        data = json.loads(request.body)
        status.cortando = max(0, int(data.get('cortando', status.cortando)))
        status.espera = max(0, int(data.get('espera', status.espera)))
        status.save()
        return JsonResponse({'ok': True, 'cortando': status.cortando, 'espera': status.espera})
    except Exception:
        return JsonResponse({'ok': False})


@login_required(login_url=LOGIN_URL)
def toggle_aberto(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False})
    barbearia = _get_barbearia(request)
    status = _get_or_create_status(barbearia)
    status.aberto = not status.aberto
    status.save()
    return JsonResponse({'ok': True, 'aberto': status.aberto})


@login_required(login_url=LOGIN_URL)
def salvar_horarios(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False})
    barbearia = _get_barbearia(request)
    try:
        data = json.loads(request.body)
        for item in data:
            dia = int(item['dia'])
            h, _ = HorarioFuncionamento.objects.get_or_create(
                barbearia=barbearia, barbeiro=None, dia=dia
            )
            h.aberto = item.get('aberto', False)
            h.inicio_manha = item.get('inicio_manha') or None
            h.fim_manha = item.get('fim_manha') or None
            h.inicio_tarde = item.get('inicio_tarde') or None
            h.fim_tarde = item.get('fim_tarde') or None
            h.save()
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'erro': str(e)})


def status_publico(request, slug):
    barbearia = get_object_or_404(Barbearia, slug=slug, ativo=True)
    status = _get_or_create_status(barbearia)
    horarios = None
    if status.mostrar_horarios:
        horarios = HorarioFuncionamento.objects.filter(barbearia=barbearia, barbeiro=None).order_by('dia')
    return render(request, 'core/status_publico.html', {
        'barbearia': barbearia,
        'status': status,
        'horarios': horarios,
    })


@login_required(login_url=LOGIN_URL)
@require_POST
def toggle_mostrar_horarios(request):
    barbearia = _get_barbearia(request)
    status = _get_or_create_status(barbearia)
    status.mostrar_horarios = not status.mostrar_horarios
    status.save()
    return JsonResponse({'mostrar_horarios': status.mostrar_horarios})


def api_status(request, slug):
    barbearia = get_object_or_404(Barbearia, slug=slug, ativo=True)
    status = _get_or_create_status(barbearia)
    estado = 'Aberta' if status.aberto else 'Fechada'
    msg = (
        f'🏪 *{barbearia.nome}* — {estado}\n'
        f'✂️ Cortando agora: {status.cortando}\n'
        f'⏳ Na espera: {status.espera}'
    )
    return JsonResponse({
        'aberto': status.aberto,
        'cortando': status.cortando,
        'espera': status.espera,
        'mensagem': msg,
    })


@login_required(login_url=LOGIN_URL)
def suporte(request):
    return render(request, 'core/suporte.html')


@login_required(login_url=LOGIN_URL)
@require_POST
def suporte_enviar(request):
    nome = request.POST.get('nome', '').strip()
    sugestao = request.POST.get('sugestao', '').strip()
    if nome and sugestao:
        import logging
        logger = logging.getLogger(__name__)
        logger.info('Sugestão de %s (%s): %s', nome, request.user.email, sugestao)
    return JsonResponse({'ok': True})
