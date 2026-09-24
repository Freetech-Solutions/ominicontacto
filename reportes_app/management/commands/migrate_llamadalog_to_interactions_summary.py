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

"""
Migra datos históricos de LlamadaLog + CalificacionCliente (legacy) a InteractionsSummary.

LlamadaLog registra varias filas por llamada (todas comparten callid); InteractionsSummary
exige interaction_id=callid UNIQUE, así que cada callid produce una sola fila. Este comando
solo registra la PRIMERA PARTE de la llamada (desde ENTERQUEUE/DIAL hasta su evento terminal:
no-contactación, no-diálogo, fin de conexión con agente, o fin de conexión por transferencia).
El tramo del agente destino de una transferencia no se registra como interacción separada, e
InteractionTransfers/InteractionJourney quedan fuera de alcance.

Solo se migran callids con MIN(time) < MIN(start_time) de InteractionsSummary (o < now() si esa
tabla está vacía), para no tocar nunca el rango ya cubierto por el sistema que la puebla hacia
adelante. El límite inferior es configurable con --since (default: inicio del año en curso).
"""

from collections import defaultdict

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Min, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from configuracion_telefonia_app.models import RutaEntrante
from ominicontacto_app.models import Campana, HistoricalCalificacionCliente, OpcionCalificacion
from reportes_app.models import InteractionsSummary, LlamadaLog

DEFAULT_CHUNK_SIZE = 500
DEFAULT_SINCE = '2026-01-01T00:00:00'
CHANNEL_TYPE_VOICE = 'VOICE'

# Eventos crudos de Asterisk para "entrante sin diálogo con agente" (no los normalizados
# EXIT_* del modelo, que nunca aparecen en LlamadaLog.event).
EVENTOS_NO_DIALOGO_RAW = ('ABANDON', 'EXITWITHTIMEOUT', 'AMD', 'ABANDONWEL')

# Fin de la primera parte por inicio/completud de una transferencia (incluye intentos
# fallidos y abandonos del cliente durante una consulta).
EVENTOS_TRANSFER_TERMINAL = frozenset(
    LlamadaLog.EVENTOS_FIN_CONEXION_POR_TRANSFER + ['ABANDON-CAMPCT', 'ABANDON-CT']
)

# Conjunto completo de eventos que cierran la "primera parte" de una llamada.
TERMINAL_EVENTS = frozenset(
    LlamadaLog.EVENTOS_NO_CONTACTACION
    + EVENTOS_NO_DIALOGO_RAW
    + tuple(LlamadaLog.EVENTOS_FIN_CONEXION_AGENTE)
) | EVENTOS_TRANSFER_TERMINAL

# Cross-referencia: reportes_app/management/commands/sync_interactions_summary_calldata.py
STATUS_ALIAS = {
    'ABANDON': 'EXIT_ABANDON',
    'ABANDONWEL': 'EXIT_ABANDON',
    'AMD': 'EXIT_AMD',
    'EXITWITHTIMEOUT': 'EXIT_TIMEOUT',
    'EXPIRE': 'EXIT_TIMEOUT',
}

HANGUP_CAUSE_MAP = {
    'COMPLETEAGENT': 'AGENT',
    'COMPLETEOUTNUM': 'EXTERNAL',
    'ABANDON': 'EXTERNAL',
    'ABANDONWEL': 'EXTERNAL',
    'EXITWITHTIMEOUT': 'SYSTEM',
    'EXPIRE': 'SYSTEM',
    'AMD': 'SYSTEM',
}
for _event in LlamadaLog.EVENTOS_NO_CONTACTACION:
    HANGUP_CAUSE_MAP[_event] = 'SYSTEM'

OUTBOUND_TIPOS = (
    LlamadaLog.LLAMADA_MANUAL, LlamadaLog.LLAMADA_DIALER,
    LlamadaLog.LLAMADA_PREVIEW, LlamadaLog.LLAMADA_CLICK2CALL,
)
TRANSFER_TIPOS = (LlamadaLog.LLAMADA_TRANSFER_INTERNA, LlamadaLog.LLAMADA_TRANSFER_EXTERNA)


def _direction_for_tipo(tipo_llamada):
    if tipo_llamada == LlamadaLog.LLAMADA_ENTRANTE:
        return 'INBOUND'
    if tipo_llamada in OUTBOUND_TIPOS:
        return 'OUTBOUND'
    return None


def _initiation_method_for_tipo(tipo_llamada):
    if tipo_llamada in (LlamadaLog.LLAMADA_MANUAL, LlamadaLog.LLAMADA_CLICK2CALL):
        return 'AGENT'
    if tipo_llamada in (LlamadaLog.LLAMADA_DIALER, LlamadaLog.LLAMADA_PREVIEW):
        return 'DIALER'
    return None


class Command(BaseCommand):
    help = (
        'Migra LlamadaLog + CalificacionCliente (legacy) a InteractionsSummary para el rango '
        '[--since, MIN(start_time) de InteractionsSummary). Solo registra la primera parte de '
        'cada llamada (sin seguir transferencias). Nunca toca el rango ya cubierto por el '
        'sistema que puebla InteractionsSummary en producción.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=DEFAULT_CHUNK_SIZE,
            help=f'Cantidad de callids a procesar por iteración (default: {DEFAULT_CHUNK_SIZE}).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='No escribe en InteractionsSummary; solo reporta los conteos que se generarían.',
        )
        parser.add_argument(
            '--since',
            type=str,
            default=DEFAULT_SINCE,
            help=(
                'ISO datetime: límite inferior (inclusive) hasta dónde migrar hacia atrás '
                f'(default: {DEFAULT_SINCE}).'
            ),
        )
        parser.add_argument(
            '--tenant-id',
            type=str,
            default=None,
            help=(
                'tenant_id a usar en las filas migradas (default: settings.ALLOWED_HOSTS[0], '
                'el FQDN del deployment). No es un valor crítico, se puede pisar.'
            ),
        )

    def handle(self, *args, **options):
        chunk_size = options['chunk_size']
        if chunk_size <= 0:
            raise CommandError('--chunk-size debe ser mayor que 0')
        dry_run = options['dry_run']
        since = self._parse_iso_dt(options['since'], '--since')
        tenant_id = options.get('tenant_id') or self._default_tenant_id()

        boundary = InteractionsSummary.objects.aggregate(Min('start_time'))['start_time__min']
        if boundary is None:
            boundary = timezone.now()
            self.stdout.write(self.style.WARNING(
                f'InteractionsSummary está vacía; se usa el momento actual ({boundary}) '
                'como techo de migración.'
            ))

        self.stdout.write(
            f'Rango a migrar: [{since}, {boundary}) (start_time >= since, < boundary). '
            f'tenant_id={tenant_id!r}'
        )

        if since >= boundary:
            self.stdout.write(self.style.WARNING(
                f'No hay nada para migrar: --since ({since}) '
                f'no es anterior al boundary ({boundary}).'
            ))
            return

        skipped_null_callid = LlamadaLog.objects.filter(
            time__gte=since, time__lt=boundary
        ).filter(Q(callid__isnull=True) | Q(callid='')).count()

        outcid_by_campaign = dict(Campana.objects.values_list('id', 'outcid'))
        ruta_entrante_by_campaign = self._preload_ruta_entrante_by_campaign()
        gestion_opcion_ids = set(
            OpcionCalificacion.objects
            .filter(tipo=OpcionCalificacion.GESTION)
            .values_list('id', flat=True)
        )

        counts_by_status = defaultdict(int)
        status_sin_mapeo = defaultdict(int)
        skipped_no_terminal_event = 0
        agent_duration_clamped = 0
        direction_edge_case_count = 0
        is_transferred_count = 0
        qualification_resolved_count = 0
        is_sale_count = 0
        total_callids_scanned = 0
        total_created = 0
        chunk_num = 0

        base_callids_qs = (
            LlamadaLog.objects
            .exclude(Q(callid__isnull=True) | Q(callid=''))
            .filter(time__gte=since, time__lt=boundary)
            .values('callid')
            .annotate(min_time=Min('time'))
        )

        last_min_time = None
        last_callid = None

        while True:
            qs = base_callids_qs
            if last_min_time is not None:
                qs = qs.filter(
                    Q(min_time__lt=last_min_time) |
                    Q(min_time=last_min_time, callid__lt=last_callid)
                )
            page = list(qs.order_by('-min_time', '-callid')[:chunk_size])
            if not page:
                break
            chunk_num += 1

            # Extiende el chunk si corta en medio de un grupo de callids con el mismo
            # min_time exacto, para que MIN(start_time) sea un checkpoint fiable al resumir.
            cutoff_min_time = page[-1]['min_time']
            cutoff_callid = page[-1]['callid']
            while True:
                extra = list(
                    base_callids_qs.filter(min_time=cutoff_min_time, callid__lt=cutoff_callid)
                    .order_by('-callid')
                )
                if not extra:
                    break
                page.extend(extra)
                cutoff_callid = extra[-1]['callid']

            last_min_time, last_callid = page[-1]['min_time'], page[-1]['callid']
            chunk_callids = [row['callid'] for row in page]
            total_callids_scanned += len(chunk_callids)

            groups = defaultdict(list)
            chunk_rows = (
                LlamadaLog.objects
                .filter(callid__in=chunk_callids)
                .order_by('callid', 'time', 'id')
            )
            for row in chunk_rows:
                groups[row.callid].append(row)

            representative_by_callid = {}
            for callid, rows in groups.items():
                terminal_rows = [r for r in rows if r.event in TERMINAL_EVENTS]
                if not terminal_rows:
                    skipped_no_terminal_event += 1
                    continue
                representative_by_callid[callid] = min(terminal_rows, key=lambda r: (r.time, r.id))

            latest_qualification = self._fetch_latest_qualifications(chunk_callids)

            to_create = []
            for callid, representative in representative_by_callid.items():
                rows = groups[callid]
                interaction, flags = self._build_interaction(
                    callid, rows, representative, tenant_id,
                    outcid_by_campaign, ruta_entrante_by_campaign,
                    gestion_opcion_ids, latest_qualification,
                )
                counts_by_status[interaction.status] += 1
                if flags['status_sin_mapeo']:
                    status_sin_mapeo[representative.event] += 1
                if flags['agent_duration_clamped']:
                    agent_duration_clamped += 1
                if flags['direction_edge_case']:
                    direction_edge_case_count += 1
                if interaction.is_transferred:
                    is_transferred_count += 1
                if interaction.qualification_id is not None:
                    qualification_resolved_count += 1
                if interaction.is_sale:
                    is_sale_count += 1
                to_create.append(interaction)

            if to_create and not dry_run:
                with transaction.atomic():
                    InteractionsSummary.objects.bulk_create(to_create)
            total_created += len(to_create)

            self.stdout.write(
                f'Chunk {chunk_num}: callids={len(chunk_callids)} creadas={len(to_create)} '
                f'(acumulado: scanned={total_callids_scanned} created={total_created}) '
                f'last_min_time={last_min_time}'
            )

        self._print_summary(
            dry_run, total_callids_scanned, total_created, counts_by_status,
            skipped_null_callid, skipped_no_terminal_event, status_sin_mapeo,
            agent_duration_clamped, direction_edge_case_count, is_transferred_count,
            qualification_resolved_count, is_sale_count,
        )

    def _build_interaction(
        self, callid, rows, representative, tenant_id,
        outcid_by_campaign, ruta_entrante_by_campaign,
        gestion_opcion_ids, latest_qualification,
    ):
        flags = {
            'status_sin_mapeo': False,
            'agent_duration_clamped': False,
            'direction_edge_case': False,
        }
        event = representative.event
        tipo_llamada = representative.tipo_llamada

        is_transferred = event in EVENTOS_TRANSFER_TERMINAL
        transfer_count = sum(1 for r in rows if r.event in EVENTOS_TRANSFER_TERMINAL)

        if event in LlamadaLog.EVENTOS_FIN_CONEXION_AGENTE:
            status = 'EXIT_ANSWERED'
        else:
            status = STATUS_ALIAS.get(event, event)
            is_aliased = event in STATUS_ALIAS
            is_no_contactacion = event in LlamadaLog.EVENTOS_NO_CONTACTACION
            if not is_aliased and not is_no_contactacion:
                flags['status_sin_mapeo'] = True

        hangup_cause = HANGUP_CAUSE_MAP.get(event)

        direction = _direction_for_tipo(tipo_llamada)
        if direction is None:
            if tipo_llamada in TRANSFER_TIPOS:
                first_row = min(rows, key=lambda r: (r.time, r.id))
                direction = _direction_for_tipo(first_row.tipo_llamada)
            if direction is None:
                direction = 'OUTBOUND'
                flags['direction_edge_case'] = True

        initiation_method = _initiation_method_for_tipo(tipo_llamada)

        if tipo_llamada in OUTBOUND_TIPOS:
            source_address = outcid_by_campaign.get(representative.campana_id)
            destination_address = representative.numero_marcado
        else:
            source_address = representative.numero_marcado
            destination_address = ruta_entrante_by_campaign.get(representative.campana_id)

        start_time = min(r.time for r in rows)
        end_time = representative.time

        # -1 en duracion_llamada es un sentinel legacy de "sin valor disponible" (la llamada
        # no llegó a completarse), nunca una duración real — se descarta, nunca se resta/suma.
        raw_duracion_llamada = representative.duracion_llamada
        if raw_duracion_llamada is not None and raw_duracion_llamada < 0:
            flags['agent_duration_clamped'] = True
        duracion_llamada = max(0, raw_duracion_llamada or 0)
        bridge_wait_time = representative.bridge_wait_time or 0
        total_duration = duracion_llamada + bridge_wait_time
        wait_conn_duration = bridge_wait_time
        agent_duration = duracion_llamada

        # -1 es un sentinel legacy de "sin agente"/"sin contacto" (ej. LlamadaLog.agente_extra_id
        # en cantidad_llamadas_no_atendidas_fecha) — se normaliza a NULL, nunca se persiste -1.
        agent_id = representative.agente_id
        if agent_id == -1:
            agent_id = None
        customer_id = representative.contacto_id
        if customer_id == -1:
            customer_id = None

        qualification_id = None
        is_sale = False
        if agent_id is not None:
            hist = latest_qualification.get((callid, agent_id))
            if hist is not None:
                qualification_id = hist.id
                is_sale = hist.opcion_calificacion_id in gestion_opcion_ids

        interaction = InteractionsSummary(
            interaction_id=callid,
            tenant_id=tenant_id,
            node_id=None,
            campaign_id=representative.campana_id,
            channel_type=CHANNEL_TYPE_VOICE,
            direction=direction,
            initiation_method=initiation_method,
            status=status,
            hangup_cause=hangup_cause,
            source_address=source_address,
            destination_address=destination_address,
            start_time=start_time,
            end_time=end_time,
            total_duration=total_duration,
            bot_duration=0,
            wait_conn_duration=wait_conn_duration,
            agent_duration=agent_duration,
            agent_id=agent_id,
            qualification_id=qualification_id,
            customer_id=customer_id,
            is_sale=is_sale,
            is_transferred=is_transferred,
            transfer_count=transfer_count,
            channel_data={},
            created_at=end_time,
            updated_at=end_time,
        )
        return interaction, flags

    def _fetch_latest_qualifications(self, chunk_callids):
        qualifications_qs = (
            HistoricalCalificacionCliente.objects
            .filter(callid__in=chunk_callids)
            .exclude(history_type='-')
            .order_by('callid', 'agente_id', '-history_date', '-history_id')
        )
        latest_qualification = {}
        for hist_row in qualifications_qs.iterator(chunk_size=2000):
            key = (hist_row.callid, hist_row.agente_id)
            if key not in latest_qualification:
                latest_qualification[key] = hist_row
        return latest_qualification

    def _preload_ruta_entrante_by_campaign(self):
        ct_campana = ContentType.objects.get_for_model(Campana)
        rows = (
            RutaEntrante.objects
            .filter(destino__content_type=ct_campana)
            .order_by('-id')
            .values_list('destino__object_id', 'telefono')
        )
        ruta_entrante_by_campaign = {}
        for campana_id, telefono in rows:
            ruta_entrante_by_campaign[campana_id] = telefono
        return ruta_entrante_by_campaign

    def _default_tenant_id(self):
        hosts = settings.ALLOWED_HOSTS
        if not hosts or hosts[0] == '*':
            raise CommandError(
                'No se pudo determinar tenant_id automáticamente desde settings.ALLOWED_HOSTS; '
                'pase --tenant-id explícitamente.'
            )
        return hosts[0]

    def _print_summary(
        self, dry_run, total_scanned, total_created, counts_by_status,
        skipped_null_callid, skipped_no_terminal_event, status_sin_mapeo,
        agent_duration_clamped, direction_edge_case_count, is_transferred_count,
        qualification_resolved_count, is_sale_count,
    ):
        prefix = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Total callids escaneados: {total_scanned} | creadas: {total_created}'
        ))
        for status, count in sorted(counts_by_status.items()):
            self.stdout.write(f'  status={status}: {count}')
        if skipped_null_callid:
            self.stdout.write(self.style.WARNING(
                f'Omitidas por callid nulo/vacío: {skipped_null_callid}'
            ))
        if skipped_no_terminal_event:
            self.stdout.write(self.style.WARNING(
                f'Omitidas por no tener evento terminal en el grupo: {skipped_no_terminal_event}'
            ))
        if status_sin_mapeo:
            self.stdout.write('Status sin mapeo explícito (evento crudo usado tal cual):')
            for event, count in sorted(status_sin_mapeo.items()):
                self.stdout.write(f'  {event}: {count}')
        self.stdout.write(f'  is_transferred=True: {is_transferred_count}')
        self.stdout.write(f'  agent_duration clampeada a 0: {agent_duration_clamped}')
        self.stdout.write(
            f'  direction: casos borde (tipo_llamada no cubierto): {direction_edge_case_count}'
        )
        self.stdout.write(f'  qualification_id resuelto: {qualification_resolved_count}')
        self.stdout.write(f'  is_sale=True: {is_sale_count}')

    @staticmethod
    def _parse_iso_dt(value, option_name):
        dt = parse_datetime(value)
        if dt is None:
            raise CommandError(f'{option_name} inválido, use un ISO datetime: {value!r}')
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
