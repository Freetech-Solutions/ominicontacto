from django.views.generic import TemplateView

from ominicontacto_app.models import Campana


class InstagramAccountConfigurationView(TemplateView):
    """Configuración de cuentas de Instagram."""
    template_name = "instagram_account_configuration.html"


class CampaignReportConversationsListView(TemplateView):
    """Vista de reporte de conversaciones de Instagram para una campaña."""
    template_name = "instagram_campaign_report_conversations.html"

    def get_object(self, queryset=None):
        return Campana.objects.get(pk=self.kwargs['pk_campana'])

    def get_context_data(self, **kwargs):
        context = super(CampaignReportConversationsListView, self).get_context_data(**kwargs)
        context['campaign'] = self.get_object()
        return context


class GeneralReportListView(TemplateView):
    """Vista de reporte general de Instagram para una campaña."""
    template_name = "instagram_report_general.html"

    def get_object(self, queryset=None):
        return Campana.objects.get(pk=self.kwargs['pk_campana'])

    def get_context_data(self, **kwargs):
        context = super(GeneralReportListView, self).get_context_data(**kwargs)
        context['campaign'] = self.get_object()
        return context
