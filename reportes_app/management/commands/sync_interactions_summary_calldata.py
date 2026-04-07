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

from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from ominicontacto_app.models import Campana
from ominicontacto_app.services.redis.connection import create_redis_connection
from reportes_app.models import InteractionsSummary


class Command(BaseCommand):
    help = (
        'Reconstruye OML:CALLDATA:CAMP:{id_camp} en Redis DB2 a partir de '
        'interactions_summary para la campaña indicada.'
    )

    _ANSWERED_STATUSES = {'EXIT_ANSWERED', 'COMPLETEAGENT', 'COMPLETEOUTNUM'}

    _STATUS_ALIAS = {
        'ABANDON': 'EXIT_ABANDON',
        'ABANDONWEL': 'EXIT_ABANDON',
        'AMD': 'EXIT_AMD',
        'EXITWITHTIMEOUT': 'EXIT_TIMEOUT',
        'EXPIRE': 'EXIT_TIMEOUT',
    }

    _VALID_CALL_TYPES = {1, 2, 3, 4, 5}

    def add_arguments(self, parser):
        parser.add_argument(
            'campaign_id',
            type=int,
            help='ID de campaña a sincronizar',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='No escribe en Redis; solo muestra el resumen calculado.',
        )
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=2000,
            help='Tamaño de lote para iterar interactions_summary (default: 2000).',
        )
        parser.add_argument(
            '--use-replica',
            action='store_true',
            help='Lee interactions_summary desde DB replica.',
        )

    def handle(self, *args, **options):
        campaign_id = options['campaign_id']
        dry_run = bool(options.get('dry_run'))
        chunk_size = options.get('chunk_size') or 2000
        db_alias = 'replica' if options.get('use_replica') else 'default'

        if chunk_size <= 0:
            raise CommandError('--chunk-size debe ser mayor que 0')

        campaign_type = self._get_campaign_type(campaign_id)
        if campaign_type is None:
            self.stdout.write(
                self.style.WARNING(
                    f'Campaña {campaign_id} no encontrada en Campana. Se aplicará inferencia por fila.'
                )
            )

        queryset = (
            InteractionsSummary.objects.using(db_alias)
            .filter(campaign_id=campaign_id, channel_type__iexact='VOICE')
            .values(
                'direction',
                'initiation_method',
                'status',
                'total_duration',
                'bot_duration',
                'wait_conn_duration',
                'agent_duration',
                'channel_data',
            )
        )

        total_rows = queryset.count()
        redis_key = f'OML:CALLDATA:CAMP:{campaign_id}'
        stats = defaultdict(lambda: Decimal('0'))
        skipped_rows = 0

        for row in queryset.iterator(chunk_size=chunk_size):
            status = self._normalize_status(row.get('status'))
            if not status:
                skipped_rows += 1
                continue

            direction = self._normalize_text(row.get('direction'))
            call_type = self._resolve_call_type(row, campaign_type)
            if call_type not in self._VALID_CALL_TYPES:
                skipped_rows += 1
                continue

            if direction == 'OUTBOUND':
                self._add(stats, f'CALL_TYPE:{call_type}:DIAL', 1)
                self._add(stats, 'DIAL_OUT', 1)
            elif direction == 'INBOUND':
                self._add(stats, 'DIAL_IN', 1)

            wait_conn_duration = self._to_decimal(row.get('wait_conn_duration'))
            total_duration = self._to_decimal(row.get('total_duration'))
            bot_duration = self._to_decimal(row.get('bot_duration'))
            agent_duration = self._to_decimal(row.get('agent_duration'))

            if status in self._ANSWERED_STATUSES:
                self._add(stats, f'CALL_TYPE:{call_type}:EXIT_ANSWERED', 1)
                self._add(stats, 'EXIT_ANSWERED', 1)

                answered_bucket = self._answered_bucket(
                    bot_duration=bot_duration,
                    agent_duration=agent_duration,
                )
                self._add(stats, f'CALL_TYPE:{call_type}:{answered_bucket}', 1)

                if wait_conn_duration > 0:
                    self._add(
                        stats,
                        f'CALL_TYPE:{call_type}:BRIDGE_WAIT_TOTAL_TIME',
                        wait_conn_duration,
                    )
                if total_duration > 0:
                    self._add(stats, 'TOTAL_CALL_TIME', total_duration)
                    if call_type == Campana.TYPE_ENTRANTE:
                        self._add(
                            stats,
                            f'CALL_TYPE:{Campana.TYPE_ENTRANTE}:ANSWERED_TOTAL_TIME',
                            total_duration,
                        )
                continue

            self._add(stats, f'CALL_TYPE:{call_type}:{status}', 1)

            if status == 'EXIT_ABANDON' and wait_conn_duration > 0:
                self._add(
                    stats,
                    f'CALL_TYPE:{call_type}:ABANDON_WAIT_TOTAL_TIME',
                    wait_conn_duration,
                )

        mapping = self._stats_to_mapping(stats)
        ordered_preview = sorted(mapping.items(), key=lambda item: item[0])

        self.stdout.write(
            f'Campaña={campaign_id} | filas_voz={total_rows} | '
            f'filas_saltadas={skipped_rows} | campos_hash={len(mapping)}'
        )
        for key, value in ordered_preview[:40]:
            self.stdout.write(f'{key}={value}')
        if len(ordered_preview) > 40:
            self.stdout.write(f'... ({len(ordered_preview) - 40} campos adicionales)')

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry-run: no se escribieron cambios en Redis DB2.'))
            return

        redis_connection = create_redis_connection(2)
        redis_connection.delete(redis_key)
        if mapping:
            redis_connection.hset(redis_key, mapping=mapping)

        self.stdout.write(
            self.style.SUCCESS(
                f'Hash sincronizado: {redis_key} ({len(mapping)} campos escritos).'
            )
        )

    def _get_campaign_type(self, campaign_id):
        try:
            return Campana.objects.only('type').get(pk=campaign_id).type
        except Campana.DoesNotExist:
            return None

    def _resolve_call_type(self, row, campaign_type):
        channel_data = row.get('channel_data')
        if isinstance(channel_data, dict):
            for key in ('tipo_llamada', 'call_type', 'id_calltype', 'tipo_campana'):
                parsed = self._to_int(channel_data.get(key))
                if parsed in self._VALID_CALL_TYPES:
                    return parsed

        initiation_method = self._normalize_text(row.get('initiation_method'))
        direction = self._normalize_text(row.get('direction'))

        if initiation_method == 'DIALER':
            return Campana.TYPE_DIALER
        if direction == 'INBOUND' or initiation_method == 'BOT':
            return Campana.TYPE_ENTRANTE
        if initiation_method == 'AGENT':
            if campaign_type in (Campana.TYPE_MANUAL, Campana.TYPE_PREVIEW):
                return campaign_type
            return Campana.TYPE_MANUAL

        if campaign_type in (Campana.TYPE_MANUAL, Campana.TYPE_DIALER, Campana.TYPE_ENTRANTE, Campana.TYPE_PREVIEW):
            return campaign_type
        if direction == 'OUTBOUND':
            return Campana.TYPE_DIALER
        if direction == 'INBOUND':
            return Campana.TYPE_ENTRANTE
        return 0

    def _normalize_status(self, status):
        normalized = self._normalize_text(status)
        if not normalized:
            return ''
        return self._STATUS_ALIAS.get(normalized, normalized)

    @staticmethod
    def _normalize_text(value):
        if value is None:
            return ''
        return str(value).strip().upper()

    @staticmethod
    def _to_int(value):
        if value in (None, '', 'None'):
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_decimal(value):
        if value in (None, '', 'None'):
            return Decimal('0')
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal('0')

    @staticmethod
    def _answered_bucket(bot_duration, agent_duration):
        has_bot = bot_duration > 0
        has_agent = agent_duration > 0
        if has_bot and has_agent:
            return 'EXIT_ANSWERED_MIX'
        if has_bot:
            return 'EXIT_ANSWERED_BOT'
        return 'EXIT_ANSWERED_HUMAN'

    @staticmethod
    def _add(stats, key, value):
        stats[key] += Decimal(str(value))

    @staticmethod
    def _decimal_to_redis_str(value):
        if value == value.to_integral():
            return str(int(value))
        as_text = format(value.normalize(), 'f')
        if '.' in as_text:
            as_text = as_text.rstrip('0').rstrip('.')
        return as_text or '0'

    def _stats_to_mapping(self, stats):
        mapping = {}
        for key, value in stats.items():
            if value == 0:
                continue
            mapping[key] = self._decimal_to_redis_str(value)
        return mapping
