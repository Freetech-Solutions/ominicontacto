from django.views.generic import TemplateView


class InstagramAccountConfigurationView(TemplateView):
    """Configuración de cuentas de Instagram."""
    template_name = "instagram_account_configuration.html"
