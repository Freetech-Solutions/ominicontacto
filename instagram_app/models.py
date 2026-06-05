import uuid

from django.db import models
from django.db.models import JSONField
from django.utils import timezone
from django.utils.translation import gettext as _

from ominicontacto_app.models import (
    AgenteProfile, Campana, Contacto, HistoricalCalificacionCliente,
)


def upload_to(instance, filename):
    return "archivos_instagram/{0}-{1}".format(
        str(uuid.uuid4()), filename)[:95]


class PlantillaInstagram(models.Model):
    TIPO_TEXT = 0
    MENSAJE_TIPOS = (
        (TIPO_TEXT, _('Texto')),
    )
    nombre = models.CharField(max_length=100)
    tipo = models.IntegerField(choices=MENSAJE_TIPOS)
    configuracion = JSONField(default=dict)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre


class GrupoPlantillaInstagram(models.Model):
    nombre = models.CharField(max_length=100)
    plantillas = models.ManyToManyField(PlantillaInstagram, related_name="grupos")

    class Meta:
        verbose_name = "Grupo de Plantillas de Instagram"
        verbose_name_plural = "Grupos de Plantillas de Instagram"

    def __str__(self):
        return self.nombre


class CuentaInstagramManager(models.Manager):

    def get_queryset(self):
        return super(CuentaInstagramManager, self).get_queryset().exclude(is_active=False)


class CuentaInstagram(models.Model):
    """Configuración de una cuenta profesional de Instagram para mensajería entrante."""
    objects = CuentaInstagramManager()
    objects_default = models.Manager()

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    access_token = models.CharField(max_length=500)
    verify_token = models.CharField(max_length=255)
    app_id = models.CharField(max_length=255)
    page_id = models.CharField(max_length=255)
    ig_user_id = models.CharField(max_length=255)
    username = models.CharField(max_length=255, blank=True, default="")

    destination = models.ForeignKey(
        'configuracion_telefonia_app.DestinoEntrante', on_delete=models.PROTECT,
        related_name="instagram_accounts", blank=True, null=True)
    horario = models.ForeignKey(
        'configuracion_telefonia_app.GrupoHorario', on_delete=models.PROTECT,
        related_name="instagram_accounts", blank=True, null=True)
    welcome_message = models.ForeignKey(
        PlantillaInstagram, blank=True, null=True,
        on_delete=models.PROTECT, related_name="accounts_welcome_message")
    goodbye_message = models.ForeignKey(
        PlantillaInstagram, blank=True, null=True,
        on_delete=models.PROTECT, related_name="accounts_goodbye_message")
    out_of_hours_message = models.ForeignKey(
        PlantillaInstagram, blank=True, null=True,
        on_delete=models.PROTECT, related_name="accounts_out_of_hours_message")

    validated = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Instagram Account Configuration"
        verbose_name_plural = "Instagram Account Configurations"

    @property
    def get_stream_name(self):
        return 'instagram_webhook_account_{}'.format(self.ig_user_id)

    def __str__(self):
        return f"{self.name} (Instagram: {self.ig_user_id})"


class ConfiguracionInstagramCampana(models.Model):
    """Configuración del canal Instagram asociada a una campaña."""
    campana = models.OneToOneField(
        'ominicontacto_app.Campana', on_delete=models.CASCADE,
        related_name='configuracion_instagram')
    cuenta = models.ForeignKey(
        CuentaInstagram, on_delete=models.PROTECT, related_name='campanas')
    grupo_plantilla_instagram = models.ForeignKey(
        GrupoPlantillaInstagram, related_name="configuracion_instagram",
        blank=True, null=True, on_delete=models.PROTECT)
    grupo_plantilla_facebook = models.ForeignKey(
        'facebook_meta_app.GrupoPlantillaMessenger', related_name="configuracion_instagram",
        blank=True, null=True, on_delete=models.PROTECT)
    nivel_servicio = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Configuración Instagram Campaña"
        verbose_name_plural = "Configuraciones Instagram Campaña"

    def __str__(self):
        return f"Configuración de {self.campana.nombre} - Instagram: {self.cuenta.name}"


class ConversationInstagramApp(models.Model):
    """Conversación entrante entre un usuario de Instagram y OMniLeads."""
    account = models.ForeignKey(CuentaInstagram, on_delete=models.CASCADE,
                                related_name='conversations_instagram')
    campana = models.ForeignKey(Campana, null=True, blank=True, on_delete=models.CASCADE,
                                related_name="instagram_conversaciones")
    client = models.ForeignKey(
        Contacto, null=True, related_name="conversations_instagram", on_delete=models.CASCADE)
    ig_scoped_id = models.CharField(max_length=255, null=True)
    agent = models.ForeignKey(
        AgenteProfile, null=True, related_name="conversations_instagram",
        on_delete=models.CASCADE)
    is_disposition = models.BooleanField(default=False)
    conversation_disposition = models.ForeignKey(
        HistoricalCalificacionCliente, related_name="conversations_instagram",
        null=True, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)
    last_message = models.ForeignKey('MessageInstagramApp', null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)
    expire = models.DateTimeField(null=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    atendida = models.BooleanField(default=False)
    error = models.BooleanField(default=False)
    error_ex = models.JSONField(default=dict)
    date_last_interaction = models.DateTimeField(null=True)
    client_alias = models.CharField(max_length=100, null=True)

    class Meta:
        verbose_name = "Instagram App Conversation"
        verbose_name_plural = "Instagram App Conversations"
        ordering = ['-updated_at']

    def __str__(self):
        return f"Conversation between {self.ig_scoped_id} and Instagram ID: {self.account.ig_user_id}"

    def otorgar_conversacion(self, agent, attended=True):
        try:
            self.agent = agent
            self.atendida = attended
            self.save(update_fields=["agent", "atendida"])
            return True
        except Exception:
            return False


class MessageInstagramAppManager(models.Manager):
    def mensajes_enviados(self):
        return self.filter(origen=models.F("conversation__account__ig_user_id"))

    def mensajes_recibidos(self):
        return self.exclude(origen=models.F("conversation__account__ig_user_id"))


class MessageInstagramApp(models.Model):
    conversation = models.ForeignKey(
        ConversationInstagramApp, on_delete=models.CASCADE, related_name='messages',
        null=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    message_id = models.CharField(max_length=255, unique=True)
    origen = models.CharField(max_length=100)
    sender = JSONField(default=dict)
    content = JSONField(default=dict)
    type = models.CharField(max_length=100)
    file = models.FileField(upload_to=upload_to, max_length=1000, null=True, blank=True)
    status = models.CharField(max_length=100)
    fail_reason = models.CharField(max_length=100, null=True, blank=True)
    objects = MessageInstagramAppManager()

    class Meta:
        verbose_name = "Instagram App Message"
        verbose_name_plural = "Instagram App Messages"
        ordering = ['-timestamp']

    def __str__(self):
        return f"Instagram message {self.message_id}"


class AttachmentInstagramApp(models.Model):
    message = models.ForeignKey(MessageInstagramApp, on_delete=models.CASCADE,
                                related_name='attachments')
    attachment_type = models.CharField(max_length=50)
    url = models.URLField()
    name = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "Instagram App Attachment"
        verbose_name_plural = "Instagram App Attachments"
        ordering = ['-id']

    def __str__(self):
        return f"Attachment ({self.attachment_type}) for Message ID: {self.message.message_id}"


class MenuInteractivoInstagram(models.Model):
    menu_header = models.CharField(max_length=1024)
    texto_opcion_incorrecta = models.CharField(max_length=100, null=True, blank=True)
    texto_derivacion = models.CharField(max_length=100)
    timeout = models.IntegerField(null=True)
    account = models.ForeignKey(
        CuentaInstagram, related_name="menuinteractivo", on_delete=models.CASCADE,
        null=True, blank=True)
    is_main = models.BooleanField(default=False)

    @property
    def nombre(self):
        return self.menu_header


class OpcionMenuInteractivoInstagram(models.Model):
    opcion = models.OneToOneField(
        'configuracion_telefonia_app.OpcionDestino', on_delete=models.CASCADE,
        related_name="opcion_menu_instagram_app")
    descripcion = models.CharField(max_length=72)
