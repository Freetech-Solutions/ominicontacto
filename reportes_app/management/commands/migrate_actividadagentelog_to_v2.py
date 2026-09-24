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
Migra datos históricos de ActividadAgenteLog (legacy) a AgentActivityEventV2.

El mapeo replica reportes_app/agent_activity_dual_write.py (write_agent_activity_event_v2),
la implementación de referencia que ya escribe en producción para estos mismos eventos.

Solo se migran filas con time < MIN(ts) de AgentActivityEventV2 (o time < now() si esa
tabla está vacía), para no tocar nunca el rango ya cubierto por el dual-write. El límite
inferior es configurable con --since (default: inicio del año en curso) para poder migrar
por etapas.
"""

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Min, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ominicontacto_app.models import Pausa
from reportes_app.models import ActividadAgenteLog, AgentActivityEventV2

DEFAULT_CHUNK_SIZE = 2000
DEFAULT_SINCE = '2026-01-01T00:00:00'
# Pseudo-ids de pausa históricos que nunca corresponden a una fila real de Pausa
# (Supervisión / On-Whatsapp); se guardan tal cual en aux_code, sin marcar metadata.
PAUSE_SENTINEL_IDS = ('00', 'OW')


class Command(BaseCommand):
    help = (
        'Migra ActividadAgenteLog (legacy) a AgentActivityEventV2 para el rango '
        '[--since, MIN(ts) de AgentActivityEventV2). Nunca toca el rango ya cubierto '
        'por el dual-write en producción.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=DEFAULT_CHUNK_SIZE,
            help=(
                'Tamaño de lote de lectura/escritura por iteración '
                f'(default: {DEFAULT_CHUNK_SIZE}).'
            ),
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='No escribe en AgentActivityEventV2; solo reporta los conteos que se generarían.',
        )
        parser.add_argument(
            '--since',
            type=str,
            default=DEFAULT_SINCE,
            help=(
                'ISO datetime: límite inferior (inclusive) hasta dónde migrar hacia atrás '
                f'(default: {DEFAULT_SINCE}). Permite migrar por etapas.'
            ),
        )

    def handle(self, *args, **options):
        chunk_size = options['chunk_size']
        if chunk_size <= 0:
            raise CommandError('--chunk-size debe ser mayor que 0')
        dry_run = options['dry_run']
        since = self._parse_iso_dt(options['since'], '--since')

        boundary = AgentActivityEventV2.objects.aggregate(Min('ts'))['ts__min']
        if boundary is None:
            boundary = timezone.now()
            self.stdout.write(self.style.WARNING(
                f'AgentActivityEventV2 está vacía; se usa el momento actual ({boundary}) '
                'como techo de migración.'
            ))

        self.stdout.write(
            f'Rango a migrar: [{since}, {boundary}) (time >= since, time < boundary).'
        )

        if since >= boundary:
            self.stdout.write(self.style.WARNING(
                f'No hay nada para migrar: --since ({since}) '
                f'no es anterior al boundary ({boundary}).'
            ))
            return

        valid_pausa_ids = set(Pausa.objects.values_list('id', flat=True))

        counts_by_event_type = defaultdict(int)
        skipped_unexpected_event = defaultdict(int)
        skipped_null_agente = 0
        invalid_pause_id_count = 0
        total_scanned = 0
        total_migrated = 0
        chunk_num = 0
        last_time = None
        last_id = None

        while True:
            qs = ActividadAgenteLog.objects.filter(time__gte=since, time__lt=boundary)
            if last_time is not None:
                qs = qs.filter(Q(time__lt=last_time) | Q(time=last_time, id__lt=last_id))
            rows = list(qs.order_by('-time', '-id')[:chunk_size])
            if not rows:
                break
            chunk_num += 1

            # Si el chunk corta en medio de un grupo de filas con el mismo `time`
            # exacto, se extiende para incluir el grupo completo: así, al comittear,
            # MIN(ts) siempre significa "todo lo de arriba ya está resuelto" (necesario
            # para que una corrida interrumpida pueda resumirse de forma segura).
            cutoff_time = rows[-1].time
            cutoff_id = rows[-1].id
            while True:
                extra = list(
                    ActividadAgenteLog.objects.filter(
                        time=cutoff_time, id__lt=cutoff_id
                    ).order_by('-id')
                )
                if not extra:
                    break
                rows.extend(extra)
                cutoff_id = extra[-1].id

            total_scanned += len(rows)
            to_create = []
            for row in rows:
                av2 = self._map_row(
                    row, valid_pausa_ids, counts_by_event_type,
                    skipped_unexpected_event,
                )
                if av2 is None:
                    if row.agente_id is None:
                        skipped_null_agente += 1
                    continue
                if av2.metadata.get('invalid_pause_id'):
                    invalid_pause_id_count += 1
                to_create.append(av2)

            if to_create and not dry_run:
                with transaction.atomic():
                    AgentActivityEventV2.objects.bulk_create(to_create)
            total_migrated += len(to_create)

            last_time, last_id = rows[-1].time, rows[-1].id
            self.stdout.write(
                f'Chunk {chunk_num}: leídas={len(rows)} migradas={len(to_create)} '
                f'(acumulado: scanned={total_scanned} '
                f'migrated={total_migrated}) last_time={last_time}'
            )

        self._print_summary(
            dry_run, total_scanned, total_migrated, counts_by_event_type,
            skipped_null_agente, skipped_unexpected_event, invalid_pause_id_count,
        )

    def _map_row(self, row, valid_pausa_ids, counts_by_event_type, skipped_unexpected_event):
        if row.agente_id is None:
            return None

        event = row.event
        pause_id = None
        aux_code = None
        metadata = {}

        if event == ActividadAgenteLog.LOGIN:
            event_type = AgentActivityEventV2.EventType.SESSION_LOGIN
        elif event == ActividadAgenteLog.LOGOUT:
            event_type = AgentActivityEventV2.EventType.SESSION_LOGOUT
        elif event == ActividadAgenteLog.UNPAUSE:
            event_type = AgentActivityEventV2.EventType.STATE_READY
        elif event == ActividadAgenteLog.PAUSE:
            pausa_id = row.pausa_id
            if not pausa_id or pausa_id == '0':
                event_type = AgentActivityEventV2.EventType.STATE_ACW
            else:
                event_type = AgentActivityEventV2.EventType.STATE_PAUSED
                if pausa_id in PAUSE_SENTINEL_IDS:
                    aux_code = pausa_id
                else:
                    try:
                        pid = int(pausa_id)
                    except (TypeError, ValueError):
                        pid = None
                    if pid is not None and pid in valid_pausa_ids:
                        pause_id = pid
                    else:
                        aux_code = pausa_id
                        metadata = {'invalid_pause_id': True}
        else:
            skipped_unexpected_event[event] += 1
            return None

        counts_by_event_type[event_type] += 1
        return AgentActivityEventV2(
            ts=row.time,
            agente_id=row.agente_id,
            event_type=event_type,
            pause_id=pause_id,
            aux_code=aux_code,
            metadata=metadata,
        )

    def _print_summary(
            self, dry_run, total_scanned, total_migrated, counts_by_event_type,
            skipped_null_agente, skipped_unexpected_event,
            invalid_pause_id_count):
        prefix = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Total escaneadas: {total_scanned} | migradas: {total_migrated}'
        ))
        for event_type, count in sorted(counts_by_event_type.items()):
            self.stdout.write(f'  {event_type}: {count}')
        self.stdout.write(f'  con metadata.invalid_pause_id: {invalid_pause_id_count}')
        if skipped_null_agente:
            self.stdout.write(self.style.WARNING(
                f'Omitidas por agente_id nulo: {skipped_null_agente}'
            ))
        for event, count in sorted(skipped_unexpected_event.items()):
            self.stdout.write(self.style.WARNING(
                f'Omitidas por event inesperado {event!r}: {count}'
            ))

    @staticmethod
    def _parse_iso_dt(value, option_name):
        dt = parse_datetime(value)
        if dt is None:
            raise CommandError(f'{option_name} inválido, use un ISO datetime: {value!r}')
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
