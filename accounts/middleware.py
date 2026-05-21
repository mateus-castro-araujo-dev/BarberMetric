from django.shortcuts import redirect


EXEMPT_PREFIXES = (
    '/login/',
    '/logout/',
    '/cadastro/',
    '/admin/',
    '/pagamento/',
    '/static/',
    '/status/',
    '/api/',
    '/verificar-email/',
    '/reenviar-verificacao/',
    '/dev/',
    '/conta-bloqueada/',
    '/esqueci-senha/',
    '/redefinir-senha/',
)


class TrialMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_staff:
            path = request.path
            if not any(path.startswith(p) for p in EXEMPT_PREFIXES):
                try:
                    barbearia = request.user.barbearia
                    if not barbearia.ativo:
                        return redirect('conta_bloqueada')
                    if not barbearia.email_verificado:
                        return redirect('verificar_email_aviso')
                    if not barbearia.acesso_liberado:
                        return redirect('pagamento')
                except Exception:
                    return redirect('cadastro')
        return self.get_response(request)
