from asgiref.sync import async_to_sync

from django.core.paginator import Paginator, EmptyPage, Page
from django.db import models
from django.http import QueryDict
from django.template.loader import render_to_string
from django.utils import translation
from ominicontacto_app.forms.base import GrabacionBusquedaFormEx
from ominicontacto_app.models import AgenteProfile
from ominicontacto_app.models import Campana
from ominicontacto_app.models import OpcionCalificacion
from ominicontacto_app.models import CalificacionCliente
from reportes_app.models import InteractionsSummary, SpeechAnalysis
from ominicontacto_app.utiles import convert_fecha_datetime
from channels.db import database_sync_to_async


@database_sync_to_async
def _search_recordings_request(message, user):
    if user.get_is_agente():
        agente = user.get_agente_profile()
        campanas = Campana.objects.filter(
            pk__in=agente.queue_set.values_list("campana_id", flat=True),
        ).exclude(
            estado=Campana.ESTADO_BORRADA,
        )
        data = QueryDict(message["data"]).copy()
        data["agente"] = agente
        form = GrabacionBusquedaFormEx(
            campana_choices=[(c.id, c.nombre) for c in campanas],
            data=data,
        )
        role = "agente"
    elif user.get_es_administrador_o_supervisor_normal():
        supervisor = user.get_supervisor_profile()
        if user.get_is_administrador():
            campanas = Campana.objects.all()
        else:
            campanas = supervisor.campanas_asignadas()
        data = QueryDict(message["data"])
        form = GrabacionBusquedaFormEx(
            campana_choices=[(c.id, c.nombre) for c in campanas],
            data=data,
        )
        role = "supervisor"
    return (
        campanas,
        data,
        form.is_valid(),
        form.cleaned_data,
        form.errors,
        role
    )


class SearchRecordingsMixin(object):
    """
    client-brow -> client-cons (search_recordings.request)
    client-cons -> worker-cons (search_recordings.enqueue)
    worker-cons -> client-cons (search_recordings.dequeue)
    client-cons -> client-brow (search_recordings.respond)
    """

    async def search_recordings_request(self, message):
        with translation.override(self.current_language):
            (
                campanas,
                data,
                form_is_valid,
                form_cleaned_data,
                form_errors,
                role
            ) = await _search_recordings_request(
                message,
                self.scope["user"]
            )
            if form_is_valid:
                await self.channel_layer.send(
                    "background-tasks",
                    {
                        "type": "search_recordings.enqueue",
                        "addressee": {
                            "group": self.groups[1],
                            "channel_name": self.channel_name,
                            "role": role,
                        },
                        "query": form_cleaned_data,
                        "campana_choice": [campana.id for campana in campanas],
                        "current_language": self.current_language,
                        "context": {
                            "BASE_URL": data["BASE_URL"],
                        },
                    },
                )
            else:
                await self.send_json({
                    "type": "search_recordings.respond",
                    "result": {
                        "errors": form_errors
                    },
                })

    def search_recordings_enqueue(self, message):
        with translation.override(message['current_language']):
            # Manejar el caso donde agente puede ser None, 'None' (string), o un ID válido
            agente_id = message["query"].get("agente")
            if agente_id and agente_id != 'None' and str(agente_id).strip():
                try:
                    agente = AgenteProfile.objects.get(pk=int(agente_id))
                except (ValueError, TypeError, AgenteProfile.DoesNotExist):
                    agente = None
            else:
                agente = None
            
            queryset = InteractionsSummary.objects.obtener_grabaciones_by_filtro(
                convert_fecha_datetime(message["query"]["fecha_desde"]),
                convert_fecha_datetime(message["query"]["fecha_hasta"]),
                message["query"]["tipo_llamada"],
                message["query"]["tel_cliente"],
                message["query"]["callid"],
                message["query"]["id_contacto_externo"],
                agente,
                message["query"]["campana"],
                Campana.objects.filter(pk__in=message["campana_choice"]),
                message["query"]["marcadas"],
                message["query"]["duracion"],
                message["query"]["gestion"],
                OpcionCalificacion.objects.filter(
                    nombre=message["query"]["calificacion"],
                ).values_list("id", flat=True),
            )
            paginator = Paginator(queryset, message["query"]["grabaciones_x_pagina"])
            try:
                page = paginator.page(message["query"]["pagina"])
            except EmptyPage:
                page = Page([], message["query"]["pagina"], paginator)

            analysis = {}
            if message["addressee"]["role"] == "agente":
                fragments = {
                    "#table-body": render_to_string(
                        "agente/frame/busqueda_grabacion_ex/_table-body.html",
                        {
                            **message["context"],
                            "page": page,
                        },
                    ),
                    "#pagination": render_to_string(
                        "_pagination.html",
                        {
                            "page": page,
                        },
                    ),
                }
            elif message["addressee"]["role"] == "supervisor":
                # Procesar transferencias - compatible con ambos modelos
                _page_object_dict = {}
                for grabacion in page.object_list:
                    # Usar 'time' (propiedad de compatibilidad) que funciona para ambos modelos
                    grabacion_time = grabacion.time if hasattr(grabacion, 'time') else grabacion.fecha_fin
                    
                    if grabacion.callid not in _page_object_dict:
                        _page_object_dict[grabacion.callid] = {}
                        _page_object_dict[grabacion.callid]['origen'] = grabacion
                        _page_object_dict[grabacion.callid]['contacto_id'] = grabacion.contacto_id
                        _page_object_dict[grabacion.callid]['campana_id'] = grabacion.campana_id
                        _page_object_dict[grabacion.callid]['callid'] = grabacion.callid
                    elif _page_object_dict[grabacion.callid]['origen'].time > grabacion_time:
                        if 'transfer' not in _page_object_dict[grabacion.callid]:
                            _page_object_dict[grabacion.callid]['transfer'] = []
                        aux = _page_object_dict[grabacion.callid]['origen']
                        _page_object_dict[grabacion.callid]['origen'] = grabacion
                        _page_object_dict[grabacion.callid]['contacto_id'] = grabacion.contacto_id
                        _page_object_dict[grabacion.callid]['transfer'].append(aux)
                        _page_object_dict[grabacion.callid]['campana_id'] = grabacion.campana_id
                    else:
                        if 'transfer' not in _page_object_dict[grabacion.callid]:
                            _page_object_dict[grabacion.callid]['transfer'] = []
                        _page_object_dict[grabacion.callid]['transfer'].append(grabacion)
                
                page_object_list = list(_page_object_dict.values())
                # - port of BusquedaGrabacionFormView._get_calificaciones
                identificadores = [
                    (
                        a['contacto_id'] if a.get('contacto_id') is not None else None,
                        a['campana_id'] if a.get('campana_id') is not None else None,
                        a['callid'],
                    )
                    for a in page_object_list
                ]
                _filtro = models.Q()
                _callids = []
                for contacto_id, campana_id, callid in identificadores:
                    # Validar que ambos IDs sean válidos y no sean None ni el string 'None'
                    contacto_valido = (
                        contacto_id is not None and 
                        contacto_id != 'None' and 
                        str(contacto_id).strip() != '' and
                        str(contacto_id) != '-1'
                    )
                    campana_valida = (
                        campana_id is not None and 
                        campana_id != 'None' and 
                        str(campana_id).strip() != ''
                    )
                    
                    if contacto_valido and campana_valida:
                        try:
                            contacto_id_int = int(contacto_id)
                            campana_id_int = int(campana_id)
                            _filtro = _filtro | models.Q(
                                contacto_id=contacto_id_int, 
                                opcion_calificacion__campana_id=campana_id_int
                            )
                        except (ValueError, TypeError):
                            # Si no se puede convertir a int, usar callid en su lugar
                            _callids.append(callid)
                    else:
                        _callids.append(callid)
                calificaciones = CalificacionCliente.history.filter(
                    _filtro | models.Q(callid__in=_callids)
                )
                analysis = self.get_speech_analytics_status(_callids)
                fragments = {
                    "#table-body": render_to_string(
                        "busqueda_grabacion_ex/_table-body.html",
                        {
                            **message["context"],
                            "calificaciones": calificaciones,
                            "page_object_list": page_object_list,
                        },
                    ),
                    "#pagination": render_to_string(
                        "_pagination.html",
                        {
                            "page": page,
                        },
                    ),
                    "#calificaciones": render_to_string(
                        "busqueda_grabacion_ex/_calificaciones.html",
                        {
                            "calificaciones": calificaciones,
                        },
                    ),
                }
            assert fragments
            async_to_sync(self.channel_layer.group_send)(
                message["addressee"]["group"], {
                    "type": "search_recordings.dequeue",
                    "addressee": {
                        "channel_name": message["addressee"]["channel_name"]
                    },
                    "result": {
                        "fragments": fragments,
                        "analysis": analysis,
                    },
                }
            )

    async def search_recordings_dequeue(self, message):
        if message["addressee"]["channel_name"] == self.channel_name:
            await self.send_json({
                "type": "search_recordings.respond",
                "result": message["result"],
            })

    def get_speech_analytics_status(self, _callids):
        qs = SpeechAnalysis.objects.filter(callid__in=_callids).values(
            "callid",
            "transcription_status", "transcription_file",
            "sentiment_status", "sentiment_file",
            "qa_status", "qa_file",
        )
        return {
            row["callid"]: {
                "transcription": row["transcription_status"],
                "transcription_file": row["transcription_file"],
                "sentiment": row["sentiment_status"],
                "sentiment_file": row["sentiment_file"],
                "qa": row["qa_status"],
                "qa_file": row["qa_file"],
            }
            for row in qs
        }
