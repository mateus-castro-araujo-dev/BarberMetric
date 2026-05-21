from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core import views as core_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('app/', include('core.urls')),
    path('status/<slug:slug>/', core_views.status_publico, name='status_publico'),
    path('api/status/<slug:slug>/', core_views.api_status, name='api_status'),
] + static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0] if settings.DEBUG else settings.STATIC_ROOT)
