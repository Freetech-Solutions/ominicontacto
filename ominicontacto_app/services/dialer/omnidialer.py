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
import requests
from urllib.parse import urljoin
import logging
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from ominicontacto_app.errors import OmlError
from ominicontacto_app.services.dialer.phone_dialer import AbstractPhoneDialerService
from ominicontacto_app.services.redis.connection import create_redis_connection


logger = logging.getLogger(__name__)
CREATE_URL = 'create-campaign/{0}'
DELETE_URL = 'delete-campaign/{0}'
EDIT_URL = 'edit-campaign/{0}'
START_URL = 'start-campaign/{0}'
PAUSE_URL = 'pause-campaign/{0}'
RESUME_URL = 'resume-campaign/{0}'
STOP_URL = 'stop-campaign/{0}'
CHANGE_DATABASE_URL = 'change-database/{0}'
NOTIFY_DISPOSITION_URL = 'add-incidence-rule-disposition/{0}'
CREATE_INCIDENCE_RULE_URL = '/create-incidence-rule/{0}'
DELETE_INCIDENCE_RULE_URL = '/delete-incidence-rule/{0}'
ADD_AGENDA_URL = '/add-agenda/{0}'

PHONE_INCIDENCE_RULE = 1
DISPOSITION_INCIDENCE_RULE = 2

CAMP_STATS_KEY = 'CAMP:{0}:COUNTER'
CAMP_CHANNELS_KEY = 'OML:CALLS:{0}:DIALER'
CAMP_CALLDATA_KEY = 'OML:CALLDATA:CAMP:{0}'
CAMP_PACING_KEY = 'CAMP:{0}:PACING'
FINALIZED_NOCONTACT = "FINALIZED WITH NO CONTACT"
PENDING_ATTEMPTS = "NO CONTACTS WITH PENDING ATTEMPTS"
FINALIZED_SUCCESS = "CONTACTED SUCCESSFULLY"

# Campos CALLDATA (Redis DB2) que suman el KPI «Conectadas no atendidas» (dialer = CALL_TYPE:2)
CONECTADAS_NO_ATENDIDAS_FIELDS = (
    'CALL_TYPE:2:EXIT_ABANDON',
    'CALL_TYPE:2:EXIT_TIMEOUT',
    'CALL_TYPE:2:EXIT_HANDOFF_ABANDON',
    'CALL_TYPE:2:EXIT_HANDOFF_TIMEOUT',
)
HIDDEN_DIALER_STATUS_KEYS = frozenset({'ANSWERED_AGENT'})

# Etiquetas legibles para el desglose del modal de campaña dialer
DIALER_STATUS_LABELS = {
    '404_NOT_FOUND': _('Teléfono no existe'),
    '480_TEMPORARILY_UNAVAILABLE': _('Temporalmente no disponible'),
    'NOANSWER': _('No atiende'),
    'CHANUNAVAIL': _('Error de canal'),
    'BUSY': _('Teléfono ocupado'),
    'ANSWERED_PSTN': _('Llamadas conectadas'),
    'INVALID_NUMBER': _('Error de ruta'),
    'CANCEL': _('Cancelaciones'),
    'EXIT_SHORTCALL': _('shortcall'),
    'EXIT_ABANDON': _('Abandonadas'),
    'EXIT_TIMEOUT': _('Timeout de cola'),
    'CONECTADAS_NO_ATENDIDAS': _('Conectadas no atendidas'),
}


class OmnidialerServiceError(OmlError):
    pass


class OmnidialerService(AbstractPhoneDialerService):

    def _request(self, url, data=None):
        full_url = urljoin(f'http://{settings.DIALER_HOSTNAME}', url)
        try:
            # We disable SSL verification because dialer host is ours and in
            # the same network, so it is not a security concern.
            result = requests.post(full_url, json=data, verify=False)  # NOSONAR
            if result.status_code == 200:
                return result.json()
            else:
                msg = 'OMniDialer Request Error to: {0} status_code: {1}'.format(
                    full_url, result.status_code)
                logger.error(msg)
                raise OmnidialerServiceError('Error executing request')
        except requests.exceptions.RequestException as e:
            msg = 'OMniDialer Request Error to: {0} for {1}'.format(full_url, e)
            logger.error(msg)
            raise

    def crear_campana(self, campana, evitar_duplicados, evitar_sin_telefono, prefijo_discador):
        data = {'contact-strategy': [1, 3, 4], 'prefix': prefijo_discador}
        return self._request(CREATE_URL.format(campana.id), data)

    def eliminar_campana(self, campana) -> bool:
        try:
            self._request(DELETE_URL.format(campana.id))
        except (OmnidialerServiceError, requests.exceptions.RequestException):
            return False
        return True

    def editar_campana(self, campana):
        data = {"contact-strategy": [1, 3, 4]}
        return self._request(EDIT_URL.format(campana.id), data)

    def iniciar_campana(self, campana):
        return self._request(START_URL.format(campana.id))

    def pausar_campana(self, campana):
        return self._request(PAUSE_URL.format(campana.id))

    def reanudar_campana(self, campana):
        return self._request(RESUME_URL.format(campana.id))

    def terminar_campana(self, campana):
        return self._request(STOP_URL.format(campana.id))

    def agendar_llamada(self, campana, agenda):
        datetime = "27/11/24 15:42:00"
        fecha = agenda.fecha.strftime('%d/%m/%y')
        datetime = f'{fecha} {agenda.hora}'
        data = {
            'campaign_name': campana.nombre,
            'phone_number': agenda.contacto.telefono,
            'id_contact': agenda.contacto.id,
            'datetime': datetime,
        }
        return self._request(ADD_AGENDA_URL.format(campana.id), data)

    def notificar_incidencia_por_calificacion(self, regla, dialer_call_id=None, contact_id=None):
        data = {'id_contact': contact_id,
                'disposition_option': regla.opcion_calificacion.id}
        return self._request(NOTIFY_DISPOSITION_URL.format(regla.opcion_calificacion.campana_id),
                             data)

    def crear_regla_de_incidencia(self, regla, es_de_calificacion=False):
        data = {
            'id': regla.id,
            'max_attempt': regla.intento_max,
            'retry_later': regla.reintentar_tarde,
            'in_mode': regla.en_modo,
        }
        if es_de_calificacion:
            data['type'] = DISPOSITION_INCIDENCE_RULE
            data['disposition_option_id'] = regla.opcion_calificacion.id
            campana_id = regla.opcion_calificacion.campana_id
        else:
            data['type'] = PHONE_INCIDENCE_RULE
            data['status'] = regla.estado
            data['status_custom'] = regla.estado_personalizado
            campana_id = regla.campana_id

        data['campaign_id'] = campana_id
        return self._request(CREATE_INCIDENCE_RULE_URL.format(campana_id), data)

    def eliminar_regla_de_incidencia(self, regla, es_de_calificacion=False) -> bool:
        if es_de_calificacion:
            campana_id = regla.opcion_calificacion.campana_id
            type = DISPOSITION_INCIDENCE_RULE
        else:
            type = PHONE_INCIDENCE_RULE
            campana_id = regla.campana_id

        data = {
            'id': regla.id,
            'type': type,
        }
        return self._request(DELETE_INCIDENCE_RULE_URL.format(campana_id), data)

    def editar_regla_de_incidencia(self, regla, campana, id_anterior, estado_anterior=None,
                                   es_de_calificacion=False) -> bool:
        try:
            self.eliminar_regla_de_incidencia(regla, es_de_calificacion)
            self.crear_regla_de_incidencia(regla, es_de_calificacion)
            return True
        except Exception:
            return False

    def cambiar_bd_contactos(self, campana, params=None):
        return self._request(CHANGE_DATABASE_URL.format(campana.id))

    def obtener_estado_campana(self, campana):
        redis_connection = create_redis_connection(db=3)
        stats = redis_connection.hgetall(CAMP_STATS_KEY.format(campana.id))
        canales_val = redis_connection.get(CAMP_CHANNELS_KEY.format(campana.id))
        try:
            canales_abiertos_pstn = int(canales_val or 0)
        except (TypeError, ValueError):
            canales_abiertos_pstn = 0

        redis_calldata = create_redis_connection(db=2)
        calldata_vals = redis_calldata.hmget(
            CAMP_CALLDATA_KEY.format(campana.id),
            *CONECTADAS_NO_ATENDIDAS_FIELDS,
        ) or ()
        conectadas_no_atendidas = 0
        for val in calldata_vals:
            try:
                conectadas_no_atendidas += int(val or 0)
            except (TypeError, ValueError):
                pass

        efectuadas = int(stats.pop('ATTEMPTED_CALLS', 0))
        terminadas_ok = int(stats.pop(FINALIZED_SUCCESS, 0))
        terminadas_no = int(stats.pop(FINALIZED_NOCONTACT, 0))
        estimadas_iniciales = int(stats.pop('PENDING_INITIAL_CONTACT_ATTEMPTS', 0))
        pending_attempts = int(stats.pop(PENDING_ATTEMPTS, 0))
        llamadas_conectadas = int(stats.pop('ANSWERED_PSTN', 0))
        estimadas = estimadas_iniciales + pending_attempts
        data = {
            'error_consulta': False,
            'canales_abiertos_pstn': canales_abiertos_pstn,
            'efectuadas': efectuadas,
            'terminadas': terminadas_ok + terminadas_no,
            'terminadas_ok': terminadas_ok,
            'terminadas_no': terminadas_no,
            'estimadas': estimadas,
            'estimadas_iniciales': estimadas_iniciales,
            'reintentos_abiertos': pending_attempts,
            # Contactos con al menos un ciclo de resultado (final_status <> INITIAL)
            'contactos_llamados': terminadas_ok + terminadas_no + pending_attempts,
            'llamadas_conectadas': llamadas_conectadas,
            'conectadas_no_atendidas': conectadas_no_atendidas,
        }
        status = []
        # El resto de los valores va a status (sin ANSWERED_AGENT ni KPIs fijos)
        for key, val in stats.items():
            if key in HIDDEN_DIALER_STATUS_KEYS:
                continue
            status.append({
                'gbState': key,
                'gbStateLabel': DIALER_STATUS_LABELS.get(key, key),
                'nCalls': int(val),
            })
        data['status'] = status
        return data

    def obtener_pacing_campana(self, campana):
        """
        Lee el snapshot de pacing predictivo CAMP:{id}:PACING (Redis DB3).

        Escrito por el worker en cada tick de `_allowed_parallel_predictive`.
        Retorna None si el hash está vacío o expiró (TTL corto).
        """
        redis_connection = create_redis_connection(db=3)
        raw = redis_connection.hgetall(CAMP_PACING_KEY.format(campana.id))
        if not raw:
            return None

        def _float(name):
            val = raw.get(name, '')
            if val is None or val == '':
                return None
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        def _int(name):
            val = raw.get(name, '')
            if val is None or val == '':
                return None
            try:
                return int(float(val))
            except (TypeError, ValueError):
                return None

        return {
            'MODE': str(raw.get('MODE') or ''),
            'REASON': str(raw.get('REASON') or ''),
            'GAMMA': _float('GAMMA'),
            'C_DIAL': _int('C_DIAL'),
            'P_HIT': _float('P_HIT'),
            'DROP_RATE': _float('DROP_RATE'),
            'A_FREE': _float('A_FREE'),
            'A_EXPECTED': _float('A_EXPECTED'),
            'C_RINGING': _int('C_RINGING'),
            'TS': _int('TS'),
        }

    def obtener_llamadas_pendientes(self, campana) -> int:
        redis_connection = create_redis_connection(db=3)
        initial, retries = redis_connection.hmget(CAMP_STATS_KEY.format(campana.id),
                                                  'PENDING_INITIAL_CONTACT_ATTEMPTS',
                                                  PENDING_ATTEMPTS)
        if initial is None:
            initial = 0
        if retries is None:
            retries = 0
        return int(initial) + int(retries)

    def obtener_llamadas_pendientes_por_id(self, campanas_por_id) -> int:
        pendientes_por_id = {}
        for campana_id, campana in campanas_por_id.items():
            pendientes_por_id[campana_id] = self.obtener_llamadas_pendientes(campana)
        return pendientes_por_id

    def finalizar_campanas_sin_llamadas_pendientes(self, campanas):
        for campana in campanas:
            if self.obtener_llamadas_pendientes(campana) == 0:
                self.terminar_campana(campana)
