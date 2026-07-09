# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions

# This file is part of OMniLeads

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#

from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.utils.timezone import now
from django.utils import timezone

from ominicontacto_app.models import Campana
from ominicontacto_app.tests.factories import LlamadaLogFactory as _BaseLlamadaLogFactory
from reportes_app.models import InitiationMethod, InteractionsSummary, LlamadaLog, LlamadaResumen


def interactions_summary_table_exists():
    """Comprueba si la tabla interactions_summary existe en la BD."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'interactions_summary'
            """
        )
        return cursor.fetchone() is not None


def crear_interaction_summary(
    interaction_id,
    campaign_id,
    *,
    direction='OUTBOUND',
    status='EXIT_ANSWERED',
    hangup_cause=None,
    channel_type='VOICE',
    agent_id=None,
    customer_id=None,
    agent_duration=80,
    total_duration=80,
    initiation_method=InitiationMethod.DIALER,
    destination_address='',
    source_address='',
    start_time=None,
    end_time=None,
    using=None,
):
    """
    Crea una fila en InteractionsSummary para tests de reportes/grabaciones (V2).
    """
    start_time = start_time or timezone.now()
    end_time = end_time or (start_time + timedelta(seconds=60))
    manager = InteractionsSummary.objects.using(using) if using else InteractionsSummary.objects
    return manager.create(
        interaction_id=str(interaction_id),
        tenant_id='test-tenant',
        node_id='node-1',
        campaign_id=campaign_id,
        channel_type=channel_type,
        direction=direction,
        initiation_method=initiation_method,
        status=status,
        hangup_cause=hangup_cause,
        source_address=source_address,
        destination_address=destination_address,
        start_time=start_time,
        end_time=end_time,
        total_duration=Decimal(str(total_duration)),
        bot_duration=Decimal('0'),
        wait_conn_duration=Decimal('0'),
        agent_duration=Decimal(str(agent_duration)),
        agent_id=agent_id,
        customer_id=customer_id,
        qualification_id=None,
        is_sale=False,
    )


def crear_interaction_summary_desde_llamada_log(llamada_log, **kwargs):
    """Crea InteractionsSummary alineado con un LlamadaLog de test."""
    defaults = {
        'campaign_id': llamada_log.campana_id,
        'agent_id': llamada_log.agente_id,
        'destination_address': llamada_log.numero_marcado or '',
        'total_duration': llamada_log.duracion_llamada if llamada_log.duracion_llamada > 0 else 60,
        'agent_duration': llamada_log.duracion_llamada if llamada_log.duracion_llamada > 0 else 1,
        'start_time': llamada_log.time,
        'end_time': llamada_log.time,
    }
    contacto_id = llamada_log.contacto_id
    if contacto_id not in (None, -1, '-1'):
        defaults['customer_id'] = contacto_id
    defaults.update(kwargs)
    return crear_interaction_summary(llamada_log.callid, **defaults)


def crear_llamada_resumen_desde_log(llamada_log, **kwargs):
    """Crea LlamadaResumen alineado con un LlamadaLog de test (reporte agente)."""
    duracion = llamada_log.duracion_llamada
    if duracion is None or duracion < 0:
        duracion = 0
    bridge_wait_time = llamada_log.bridge_wait_time
    if bridge_wait_time is None or bridge_wait_time < 0:
        bridge_wait_time = 0
    defaults = {
        'campana_id': llamada_log.campana_id,
        'tipo_campana': llamada_log.tipo_campana,
        'tipo_llamada': llamada_log.tipo_llamada,
        'agente_id': llamada_log.agente_id,
        'contacto_id': llamada_log.contacto_id,
        'numero_marcado': llamada_log.numero_marcado,
        'fecha_inicio': llamada_log.time,
        'fecha_fin': llamada_log.time,
        'duracion_segundos': duracion,
        'bridge_wait_time': bridge_wait_time,
        'event': llamada_log.event,
    }
    defaults.update(kwargs)
    resumen_callid = '{0}:{1}'.format(llamada_log.callid, llamada_log.id)
    resumen, _created = LlamadaResumen.objects.get_or_create(
        callid=resumen_callid,
        defaults=defaults,
    )
    return resumen


class LlamadaLogFactory(_BaseLlamadaLogFactory):
    """LlamadaLogFactory que también crea LlamadaResumen para tests de reportes."""

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        obj = super(LlamadaLogFactory, cls)._create(model_class, *args, **kwargs)
        if obj.event not in LlamadaResumen.EVENTOS_HOLD:
            crear_llamada_resumen_desde_log(obj)
        return obj


def crear_llamada_log_y_resumen(**kwargs):
    """Crea LlamadaLog y su LlamadaResumen asociado (tests de reportes)."""
    return LlamadaLogFactory(**kwargs)


# LlamadaLog.EVENTOS_NO_CONTACTACION
NOCONNECT = ['NOANSWER', 'CANCEL', 'BUSY', 'CHANUNAVAIL', 'FAIL', 'OTHER', 'AMD', 'BLACKLIST',
             'CONGESTION', 'NONDIALPLAN']
CONNECT = ['COMPLETEAGENT', 'COMPLETEOUTNUM']
# LlamadaLog.EVENTOS_NO_DIALOGO
NO_DIALOG = ['EXITWITHTIMEOUT', 'ABANDON']
FINALIZACIONES = NOCONNECT + CONNECT + NO_DIALOG


class GeneradorDeLlamadaLogs():

    def generar_log(self, campana, es_manual, finalizacion, numero_marcado, agente=None,
                    contacto=None, bridge_wait_time=-1, duracion_llamada=-1, archivo_grabacion='',
                    time=None, callid=None):
        if time is None:
            time = now()
        tipo_llamada = Campana.TYPE_MANUAL if es_manual else campana.type
        agente_id = -1 if agente is None else agente.id
        contacto_id = -1 if contacto is None else contacto.id
        self._generar_logs(campana, es_manual, finalizacion, numero_marcado, tipo_llamada,
                           agente_id, contacto_id, bridge_wait_time, duracion_llamada,
                           archivo_grabacion, time, callid, es_transfer=False)

    def _generar_logs(self, campana, es_manual, finalizacion, numero_marcado, tipo_llamada,
                      agente_id, contacto_id, bridge_wait_time, duracion_llamada, archivo_grabacion,
                      time, callid, es_transfer):

        if es_transfer:
            assert finalizacion is None, 'No indicar finalizacion para Transferencias'

        if es_manual or campana.type in [Campana.TYPE_PREVIEW, Campana.TYPE_MANUAL]:
            assert agente_id != -1, 'Una llamada manual debe tener un agente'
            assert finalizacion in NOCONNECT or finalizacion in CONNECT or\
                es_transfer, 'Finalizacion incorrecta: %s' % finalizacion
            self._generar_logs_dial(campana, tipo_llamada, finalizacion, numero_marcado,
                                    agente_id, contacto_id=contacto_id,
                                    bridge_wait_time=bridge_wait_time,
                                    duracion_llamada=duracion_llamada,
                                    archivo_grabacion=archivo_grabacion,
                                    time=time, callid=callid, es_transfer=es_transfer)

        elif campana.type == Campana.TYPE_DIALER:
            assert finalizacion in FINALIZACIONES or (es_transfer and finalizacion is None), \
                'Finalizacion incorrecta: %s' % finalizacion
            self._generar_logs_dial(campana, tipo_llamada, finalizacion, numero_marcado,
                                    agente_id=-1, contacto_id=contacto_id,
                                    bridge_wait_time=bridge_wait_time,
                                    duracion_llamada=duracion_llamada,
                                    archivo_grabacion=archivo_grabacion,
                                    time=time, callid=callid, es_transfer=es_transfer)
            if finalizacion not in NOCONNECT:
                self._generar_logs_queue(campana, tipo_llamada, finalizacion, numero_marcado,
                                         agente_id, contacto_id, bridge_wait_time,
                                         duracion_llamada, archivo_grabacion,
                                         time=time, callid=callid, es_transfer=es_transfer)
        elif campana.type == Campana.TYPE_ENTRANTE:
            assert finalizacion in CONNECT or finalizacion in NO_DIALOG or es_transfer
            self._generar_logs_queue(campana, tipo_llamada, finalizacion, numero_marcado,
                                     agente_id, contacto_id, bridge_wait_time,
                                     duracion_llamada, archivo_grabacion, time=time, callid=callid,
                                     es_transfer=es_transfer)

    def _generar_logs_dial(self, campana, tipo_llamada, finalizacion, numero_marcado, agente_id,
                           contacto_id, bridge_wait_time, duracion_llamada, archivo_grabacion,
                           time, callid=None, es_transfer=False):
        """
        Genera logs para la pata de la conexion desde el DIAL
        """
        LlamadaLogFactory(event='DIAL',
                          campana_id=campana.id,
                          tipo_campana=campana.type,
                          tipo_llamada=tipo_llamada,
                          agente_id=agente_id,
                          numero_marcado=numero_marcado,
                          contacto_id=contacto_id,
                          bridge_wait_time=-1,
                          duracion_llamada=-1,
                          archivo_grabacion='',
                          time=time, callid=callid)

        if finalizacion in NOCONNECT:
            if not es_transfer:
                LlamadaLogFactory(event=finalizacion,
                                  campana_id=campana.id,
                                  tipo_campana=campana.type,
                                  tipo_llamada=tipo_llamada,
                                  agente_id=agente_id,
                                  numero_marcado=numero_marcado,
                                  contacto_id=contacto_id,
                                  bridge_wait_time=bridge_wait_time,
                                  duracion_llamada=-1,
                                  archivo_grabacion='',
                                  time=time, callid=callid)
        else:
            LlamadaLogFactory(event='ANSWER',
                              campana_id=campana.id,
                              tipo_campana=campana.type,
                              tipo_llamada=tipo_llamada,
                              agente_id=agente_id,
                              numero_marcado=numero_marcado,
                              contacto_id=contacto_id,
                              bridge_wait_time=bridge_wait_time,
                              duracion_llamada=-1,
                              archivo_grabacion='',
                              time=time, callid=callid)
            if es_transfer:
                pass  # No hago nada pues la finalizacion se crea segun la transferencia
            elif tipo_llamada in [Campana.TYPE_MANUAL, Campana.TYPE_PREVIEW]:
                assert finalizacion in CONNECT, \
                    'Una llamada Manual con ANSWER debe terminar en COMPLETEAGENT o COMPLETEOUTNUM'
                LlamadaLogFactory(event=finalizacion,
                                  campana_id=campana.id,
                                  tipo_campana=campana.type,
                                  tipo_llamada=tipo_llamada,
                                  agente_id=agente_id,
                                  numero_marcado=numero_marcado,
                                  contacto_id=contacto_id,
                                  bridge_wait_time=bridge_wait_time,
                                  duracion_llamada=duracion_llamada,
                                  archivo_grabacion=archivo_grabacion,
                                  time=time, callid=callid)
            else:
                # Evento extra de Finalizacion para la pata de dial en el caso DIALER
                assert tipo_llamada == Campana.TYPE_DIALER, \
                    'Sólo Dialers no Manuales pueden tener eventos de la pata DIAL de la conexion'
                if es_transfer:
                    pass  # No hago nada pues la finalizacion se crea segun la transferencia
                elif finalizacion in NO_DIALOG:
                    if finalizacion == 'EXITWITHTIMEOUT':
                        finalizacion_pata_dial = 'COMPLETEAGENT'
                    if finalizacion == 'ABANDON':
                        finalizacion_pata_dial = 'COMPLETEOUTNUM'
                    LlamadaLogFactory(event=finalizacion_pata_dial,
                                      campana_id=campana.id,
                                      tipo_campana=campana.type,
                                      tipo_llamada=tipo_llamada,
                                      agente_id=-1,  # 'dialer-dialout'
                                      numero_marcado=numero_marcado,
                                      contacto_id=contacto_id,
                                      bridge_wait_time=bridge_wait_time,
                                      duracion_llamada=duracion_llamada,
                                      archivo_grabacion='',
                                      time=time, callid=callid)
                else:
                    assert finalizacion in CONNECT, \
                        'Finalizacion incorrecta para campaña Dialer:%s' % finalizacion
                    LlamadaLogFactory(event=finalizacion,
                                      campana_id=campana.id,
                                      tipo_campana=campana.type,
                                      tipo_llamada=tipo_llamada,
                                      agente_id=-1,
                                      numero_marcado=numero_marcado,
                                      contacto_id=contacto_id,
                                      bridge_wait_time=bridge_wait_time,
                                      duracion_llamada=duracion_llamada,
                                      archivo_grabacion='',
                                      time=time, callid=callid)

    def _generar_logs_queue(self, campana, tipo_llamada, finalizacion, numero_marcado, agente_id,
                            contacto_id, bridge_wait_time, duracion_llamada, archivo_grabacion,
                            time, callid=None, es_transfer=False):

        """
        Genera logs para la pata de la conexion desde el ENTERQUEUE
        """
        LlamadaLogFactory(event='ENTERQUEUE',
                          campana_id=campana.id,
                          tipo_campana=campana.type,
                          tipo_llamada=tipo_llamada,
                          agente_id=-1,
                          numero_marcado=numero_marcado,
                          contacto_id=contacto_id,
                          bridge_wait_time=-1,
                          duracion_llamada=-1,
                          archivo_grabacion='',
                          time=time, callid=callid)
        if finalizacion in NO_DIALOG:
            # No se establece el Dialogo con el Agente
            LlamadaLogFactory(event=finalizacion,
                              campana_id=campana.id,
                              tipo_campana=campana.type,
                              tipo_llamada=tipo_llamada,
                              agente_id=-1,
                              numero_marcado=numero_marcado,
                              contacto_id=contacto_id,
                              bridge_wait_time=bridge_wait_time,
                              duracion_llamada=-1,
                              archivo_grabacion='',
                              time=time, callid=callid)
        else:
            # Se establece el Dialogo con el Agente
            assert agente_id is not None and agente_id != -1, 'Una llamada conectada debe '
            'tener un agente'
            LlamadaLogFactory(event='CONNECT',
                              campana_id=campana.id,
                              tipo_campana=campana.type,
                              tipo_llamada=tipo_llamada,
                              agente_id=agente_id,
                              numero_marcado=numero_marcado,
                              contacto_id=contacto_id,
                              bridge_wait_time=bridge_wait_time,
                              duracion_llamada=-1,
                              archivo_grabacion='',
                              time=time, callid=callid)
            if es_transfer:
                pass  # No hago nada pues la finalizacion se crea segun la transferencia
            else:
                assert finalizacion in CONNECT, 'Finalizacion incorrecta: %s' % finalizacion
                LlamadaLogFactory(event=finalizacion,
                                  campana_id=campana.id,
                                  tipo_campana=campana.type,
                                  tipo_llamada=tipo_llamada,
                                  agente_id=agente_id,
                                  numero_marcado=numero_marcado,
                                  contacto_id=contacto_id,
                                  bridge_wait_time=bridge_wait_time,
                                  duracion_llamada=duracion_llamada,
                                  archivo_grabacion=archivo_grabacion,
                                  time=time, callid=callid)

    def generar_log_transferencia_campt(self, campana_orig, campana_dest, finalizacion,
                                        numero_marcado, agente_orig, agente_dest, contacto=None,
                                        bridge_wait_time=5, duracion_llamada=5,
                                        archivo_grabacion='', time=None, callid=None):
        """ Genera logs para una llamada transferida a una campaña Entrante """
        es_manual = campana_orig.type == Campana.TYPE_MANUAL
        tipo_llamada = campana_orig.type
        contacto_id = -1 if contacto is None else contacto.id

        assert agente_orig is not None, 'Solo un agente puede transferir'
        assert finalizacion in ['COMPLETE-CAMPT', 'ABANDON', 'EXITWITHTIMEOUT', ]

        # Genero log de llamada hasta CAMPT-TRY
        self._generar_logs(campana=campana_orig, es_manual=es_manual, finalizacion=None,
                           numero_marcado=numero_marcado, tipo_llamada=tipo_llamada,
                           agente_id=agente_orig.id, contacto_id=contacto_id,
                           bridge_wait_time=bridge_wait_time,
                           duracion_llamada=duracion_llamada, archivo_grabacion='',
                           time=time, callid=callid, es_transfer=True)
        LlamadaLogFactory(event='CAMPT-TRY', agente_id=agente_orig.id, campana_id=campana_orig.id,
                          tipo_campana=campana_orig.type, bridge_wait_time=bridge_wait_time,
                          duracion_llamada=duracion_llamada,
                          tipo_llamada=LlamadaLog.LLAMADA_TRANSFER_INTERNA,
                          campana_extra_id=campana_dest.id,
                          numero_marcado=numero_marcado, contacto_id=contacto_id,
                          archivo_grabacion=archivo_grabacion, time=time, callid=callid)
        LlamadaLogFactory(event='ENTERQUEUE-TRANSFER', campana_id=campana_dest.id,
                          agente_id=agente_orig.id,
                          duracion_llamada=0, bridge_wait_time=0,
                          tipo_campana=campana_dest.type,
                          campana_extra_id=campana_orig.id,
                          tipo_llamada=LlamadaLog.LLAMADA_TRANSFER_INTERNA,
                          numero_marcado=numero_marcado, contacto_id=contacto_id,
                          archivo_grabacion=archivo_grabacion, time=time, callid=callid)

        if finalizacion == 'COMPLETE-CAMPT':
            LlamadaLogFactory(event='CAMPT-COMPLETE',
                              campana_id=campana_orig.id,
                              tipo_campana=campana_orig.type,
                              tipo_llamada=LlamadaLog.LLAMADA_TRANSFER_INTERNA,
                              agente_id=agente_orig.id, agente_extra_id=agente_dest.id,
                              bridge_wait_time=bridge_wait_time,
                              duracion_llamada=duracion_llamada,
                              numero_marcado=numero_marcado, contacto_id=contacto_id,
                              archivo_grabacion=archivo_grabacion, time=time, callid=callid)

            LlamadaLogFactory(event='CONNECT', campana_id=campana_dest.id,
                              tipo_campana=campana_dest.type,
                              tipo_llamada=LlamadaLog.LLAMADA_TRANSFER_INTERNA,
                              agente_id=agente_dest.id,
                              bridge_wait_time=bridge_wait_time,
                              duracion_llamada='-1',
                              numero_marcado=numero_marcado, contacto_id=contacto_id,
                              archivo_grabacion=archivo_grabacion, time=time, callid=callid)
            LlamadaLogFactory(event='COMPLETE-CAMPT', campana_id=campana_dest.id,
                              tipo_campana=campana_dest.type,
                              tipo_llamada=LlamadaLog.LLAMADA_TRANSFER_INTERNA,
                              agente_id=agente_dest.id,
                              bridge_wait_time=bridge_wait_time,
                              duracion_llamada=duracion_llamada,
                              numero_marcado=numero_marcado, contacto_id=contacto_id,
                              archivo_grabacion=archivo_grabacion, time=time, callid=callid)

        else:
            assert finalizacion in ['ABANDON', 'EXITWITHTIMEOUT'], 'Finalizacion '
            'incorrecta: %s' % finalizacion
            LlamadaLogFactory(event='CAMPT-FAIL',
                              campana_id=campana_orig.id, tipo_campana=campana_orig.type,
                              tipo_llamada=tipo_llamada,
                              agente_id=agente_orig.id,
                              bridge_wait_time=bridge_wait_time,
                              duracion_llamada=duracion_llamada,
                              numero_marcado=numero_marcado, contacto_id=contacto_id,
                              archivo_grabacion=archivo_grabacion, time=time, callid=callid)
            LlamadaLogFactory(event=finalizacion,
                              campana_id=campana_dest.id, tipo_campana=campana_dest.type,
                              tipo_llamada=LlamadaLog.LLAMADA_TRANSFER_INTERNA,
                              agente_id=-1,
                              bridge_wait_time=bridge_wait_time,
                              duracion_llamada=-1,
                              numero_marcado=numero_marcado, contacto_id=contacto_id,
                              archivo_grabacion=archivo_grabacion, time=time, callid=callid)

    def generar_log_transferencia_bt(self, campana, finalizacion, numero_marcado,
                                     agente_orig, agente_dest, contacto=None,
                                     bridge_wait_time=5, duracion_llamada=5,
                                     archivo_grabacion='', time=None, callid=None):
        """ Genera logs para una llamada con transferencia ciega a Agente """
        es_manual = campana.type == Campana.TYPE_MANUAL
        tipo_llamada = campana.type
        contacto_id = -1 if contacto is None else contacto.id

        assert agente_orig is not None, 'Solo un agente puede transferir'
        assert finalizacion in ['BT-BUSY', 'BT-CANCEL', 'BT-CHANUNAVAIL', 'BT-CONGESTION',
                                'BT-NOANSWER', 'BT-ABANDON', 'COMPLETE-BT', ]
        self._generar_logs(campana=campana, es_manual=es_manual, finalizacion=None,
                           numero_marcado=numero_marcado, tipo_llamada=tipo_llamada,
                           agente_id=agente_orig.id, contacto_id=contacto_id,
                           bridge_wait_time=bridge_wait_time,
                           duracion_llamada=duracion_llamada, archivo_grabacion='',
                           time=time, callid=callid, es_transfer=True)
        LlamadaLogFactory(event='BT-TRY', agente_id=agente_orig.id, campana_id=campana.id,
                          tipo_campana=campana.type, bridge_wait_time=bridge_wait_time,
                          duracion_llamada=duracion_llamada,
                          tipo_llamada=LlamadaLog.LLAMADA_TRANSFER_INTERNA,
                          agente_extra_id=agente_dest.id,
                          numero_marcado=numero_marcado, contacto_id=contacto_id,
                          archivo_grabacion=archivo_grabacion, time=time, callid=callid)
        if finalizacion == 'COMPLETE-BT':
            LlamadaLogFactory(event='BT-ANSWER', agente_id=agente_dest.id,
                              campana_id=campana.id,
                              tipo_campana=campana.type, bridge_wait_time=bridge_wait_time,
                              duracion_llamada=-1,
                              tipo_llamada=LlamadaLog.LLAMADA_TRANSFER_INTERNA,
                              numero_marcado=numero_marcado, contacto_id=contacto_id,
                              archivo_grabacion=-1, time=time, callid=callid)
            LlamadaLogFactory(event='COMPLETE-BT', agente_id=agente_dest.id,
                              campana_id=campana.id,
                              tipo_campana=campana.type, bridge_wait_time=bridge_wait_time,
                              duracion_llamada=duracion_llamada,
                              tipo_llamada=LlamadaLog.LLAMADA_TRANSFER_INTERNA,
                              numero_marcado=numero_marcado, contacto_id=contacto_id,
                              archivo_grabacion=archivo_grabacion, time=time, callid=callid)
            pass
        else:
            LlamadaLogFactory(
                event=finalizacion, agente_id=agente_dest.id,
                campana_id=campana.id,
                tipo_campana=campana.type, bridge_wait_time=bridge_wait_time,
                duracion_llamada=duracion_llamada,
                tipo_llamada=LlamadaLog.LLAMADA_TRANSFER_INTERNA,
                numero_marcado=numero_marcado, contacto_id=contacto_id,
                archivo_grabacion=archivo_grabacion, time=time, callid=callid,
            )

    # def generar_log_transferencia_ct(
        """ Genera logs para una llamada con transferencia consultativa a Agente """
    # def generar_log_transferencia_btout(
        """ Genera logs para una llamada con transferencia ciega a numero externo """
    # def generar_log_transferencia_ctout(
        """ Genera logs para una llamada con transferencia consultativa a numero externo """
