from .models import Barbeiro


def barbearia_context(request):
    ctx = {}
    if request.user.is_authenticated:
        try:
            barbearia = request.user.barbearia
            ctx['barbearia'] = barbearia
            ctx['dias_trial'] = barbearia.dias_restantes_trial
            ctx['plano'] = barbearia.plano

            barbeiro_id = request.session.get('barbeiro_id')
            barbeiro = None
            modo_todos = barbeiro_id == 'todos'
            if not modo_todos and barbeiro_id:
                try:
                    barbeiro = Barbeiro.objects.get(id=barbeiro_id, barbearia=barbearia, ativo=True)
                except Barbeiro.DoesNotExist:
                    pass
            if not modo_todos and not barbeiro:
                barbeiro = barbearia.barbeiros.filter(ativo=True).first()
                if barbeiro:
                    request.session['barbeiro_id'] = barbeiro.id
            ctx['barbeiro_atual'] = barbeiro
            ctx['modo_todos'] = modo_todos
            ctx['todos_barbeiros'] = barbearia.barbeiros.filter(ativo=True)
        except Exception:
            pass

    # Flag PWA: consumida uma única vez da sessão
    if request.session.pop('pwa_prompt', False):
        ctx['pwa_prompt'] = True

    return ctx
