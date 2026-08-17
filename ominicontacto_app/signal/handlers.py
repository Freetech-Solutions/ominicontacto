from datetime import date

from django.db.models.signals import pre_save
from django.dispatch import receiver

from ominicontacto_app.models import CalificacionCliente
from ominicontacto_app.services.dialer.omnidialer import record_bot_disposition_counter
from reportes_app.services.redis.disposition_cache import \
    CampaignDispositionsCache

disposition_cache = CampaignDispositionsCache()


@receiver(pre_save, sender=CalificacionCliente, weak=False, dispatch_uid="redis:disposition-cache")
def update_disposition_cache(sender, instance, raw, using, update_fields, **kwargs):
    if raw:
        return
    previous_nombre = None
    previous_tipo = None
    has_previous_tipo_different = None
    if instance.pk:
        previous = sender.objects.values_list(
            "opcion_calificacion__tipo",
            "opcion_calificacion__nombre",
        ).get(pk=instance.pk)
        previous_nombre = previous[1]
        if instance.modified.date() == date.today():
            previous_tipo = previous[0]
            has_previous_tipo_different = (
                previous_tipo != instance.opcion_calificacion.tipo
            )

    # solo se notifica cuando no hay una calificación previa o cuando cambia
    # el tipo
    if previous_tipo is None or has_previous_tipo_different:
        disposition_cache.record_disposition(
            instance.opcion_calificacion.campana_id,
            instance.opcion_calificacion.es_gestion(),
            has_previous_different=has_previous_tipo_different,
        )

    new_nombre = instance.opcion_calificacion.nombre
    if previous_nombre != new_nombre:
        record_bot_disposition_counter(
            instance.opcion_calificacion.campana_id,
            new_nombre,
            previous_nombre,
        )
