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

import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ominicontacto_app.models import AgenteProfile, Campana
from reportes_app.models import InitiationMethod, InteractionsSummary


# Status que usan los reportes y gráficos (contestadas vs no contestadas / abandono / expiradas)
STATUS_CONTESTADA = 'EXIT_ANSWERED'
STATUS_NO_CONTESTADAS = [
    'EXIT_ABANDON',
    'EXIT_TIMEOUT',
    'CANCEL',
    'EXIT_SHORTCALL',
    'EXIT_AMD',
]
INITIATION_METHODS = [InitiationMethod.AGENT, InitiationMethod.DIALER, InitiationMethod.BOT]
DIRECTIONS = ['INBOUND', 'OUTBOUND']

# Pesos para variedad realista (más contestadas y OUTBOUND para que los gráficos tengan volumen)
WEIGHTS_STATUS = [60] + [8] * len(STATUS_NO_CONTESTADAS)  # 60% EXIT_ANSWERED, resto repartido
WEIGHTS_DIRECTION = [70, 30]  # 70% OUTBOUND, 30% INBOUND
WEIGHTS_INITIATION = [50, 40, 10]  # AGENT, DIALER, BOT

BATCH_SIZE = 500
DEFAULT_CAMPAIGN_IDS = [1, 2, 3]
FAKE_PREFIX = 'fake-'


class Command(BaseCommand):
    help = (
        'Genera registros fake en interactions_summary para probar reportes y gráficos '
        'del centro de contacto. Los interaction_id generados empiezan por "fake-".'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'cantidad',
            nargs='?',
            type=int,
            default=200,
            help='Número de registros a generar (default: 200).',
        )
        parser.add_argument(
            '--dias',
            type=int,
            default=30,
            help='Distribuir start_time/end_time en los últimos N días (default: 30).',
        )
        parser.add_argument(
            '--campana-ids',
            type=int,
            nargs='*',
            default=None,
            help='Usar solo estos campaign_id; si no se indica, se usan campañas existentes o IDs por defecto.',
        )
        parser.add_argument(
            '--solo-campanas-existentes',
            action='store_true',
            help='Tomar solo IDs de campañas existentes en Campana (ignorado si se pasa --campana-ids).',
        )
        parser.add_argument(
            '--incluir-agentes',
            action='store_true',
            default=True,
            help='Asignar agent_id desde agentes de las campañas usadas (default: True).',
        )
        parser.add_argument(
            '--no-incluir-agentes',
            action='store_false',
            dest='incluir_agentes',
            help='No asignar agent_id (todos null).',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Antes de generar, borrar registros cuyo interaction_id empiece por "fake-".',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar cuántos se crearían y con qué rango de fechas/campañas, sin escribir.',
        )

    def _get_campaign_ids(self, options):
        cids = options.get('campana_ids')
        if cids is not None and len(cids) > 0:
            return list(cids)
        if options.get('solo_campanas_existentes'):
            ids = list(Campana.objects.values_list('id', flat=True))
            if ids:
                return ids
        return DEFAULT_CAMPAIGN_IDS

    def _get_agent_ids(self, campaign_ids, include_agents):
        if not include_agents:
            return []
        agent_ids = list(
            AgenteProfile.objects.filter(
                campana_member__queue_name__campana_id__in=campaign_ids
            ).values_list('id', flat=True).distinct()
        )
        return agent_ids

    def _random_phone(self):
        return ''.join(str(random.randint(0, 9)) for _ in range(15))

    def _random_dt_in_last_days(self, days):
        now = timezone.now()
        start = now - timedelta(days=days)
        delta_seconds = (now - start).total_seconds()
        r = random.random() * delta_seconds
        return start + timedelta(seconds=r)

    def _build_one_record(self, campaign_ids, agent_ids, end_max):
        status = random.choices(
            [STATUS_CONTESTADA] + STATUS_NO_CONTESTADAS,
            weights=WEIGHTS_STATUS,
            k=1
        )[0]
        direction = random.choices(DIRECTIONS, weights=WEIGHTS_DIRECTION, k=1)[0]
        initiation = random.choices(INITIATION_METHODS, weights=WEIGHTS_INITIATION, k=1)[0]

        start_time = self._random_dt_in_last_days(self.days)
        # end_time entre start_time y como máximo start + duración razonable
        max_duration_sec = 7200 if status == STATUS_CONTESTADA else 300
        duration_sec = random.randint(1, max_duration_sec)
        end_time = min(
            start_time + timedelta(seconds=duration_sec),
            end_max
        )
        if end_time <= start_time:
            end_time = start_time + timedelta(seconds=1)

        total_duration = Decimal(str((end_time - start_time).total_seconds()))
        total_sec = max(1, int(float(total_duration)))
        if status == STATUS_CONTESTADA:
            agent_duration = Decimal(str(random.randint(min(10, total_sec), total_sec)))
            wait_conn_duration = Decimal(str(random.randint(0, 120)))
            bot_duration = Decimal('0') if random.random() > 0.1 else Decimal(str(random.randint(1, min(60, total_sec))))
        else:
            agent_duration = Decimal('0')
            wait_conn_duration = Decimal(str(random.randint(0, 300)))
            bot_duration = Decimal('0')

        campaign_id = random.choice(campaign_ids)
        agent_id = random.choice(agent_ids) if agent_ids else None

        is_sale = status == STATUS_CONTESTADA and random.random() < 0.15
        is_transferred = status == STATUS_CONTESTADA and random.random() < 0.1
        transfer_count = random.randint(0, 2) if is_transferred else 0

        interaction_id = f'{FAKE_PREFIX}{uuid.uuid4().hex}'
        source = self._random_phone()
        dest = self._random_phone()
        if direction == 'INBOUND':
            source_address, destination_address = source, dest
        else:
            source_address, destination_address = dest, source

        return InteractionsSummary(
            interaction_id=interaction_id,
            tenant_id='fake-tenant',
            node_id='node-1',
            campaign_id=campaign_id,
            channel_type='VOICE',
            direction=direction,
            initiation_method=initiation,
            status=status,
            hangup_cause=None,
            source_address=source_address,
            destination_address=destination_address,
            start_time=start_time,
            end_time=end_time,
            total_duration=total_duration,
            bot_duration=bot_duration,
            wait_conn_duration=wait_conn_duration,
            agent_duration=agent_duration,
            agent_id=agent_id,
            qualification_id=None,
            customer_id=None,
            is_sale=is_sale,
            is_transferred=is_transferred,
            transfer_count=transfer_count,
            channel_data={},
            created_at=end_time,
            updated_at=end_time,
        )

    def handle(self, *args, **options):
        cantidad = options['cantidad']
        if cantidad <= 0:
            raise CommandError('cantidad debe ser mayor que 0.')

        self.days = options['dias']
        if self.days <= 0:
            raise CommandError('--dias debe ser mayor que 0.')

        dry_run = options.get('dry_run', False)
        clear = options.get('clear', False)
        include_agents = options.get('incluir_agentes', True)

        campaign_ids = self._get_campaign_ids(options)
        agent_ids = self._get_agent_ids(campaign_ids, include_agents)

        end_max = timezone.now()
        start_range = end_max - timedelta(days=self.days)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[DRY-RUN] Se crearían {cantidad} registros con interaction_id '
                    f'prefijo "{FAKE_PREFIX}".'
                )
            )
            self.stdout.write(
                f'  Rango de fechas: últimos {self.days} días (desde ~{start_range.date()}).'
            )
            self.stdout.write(f'  campaign_id: {campaign_ids}.')
            self.stdout.write(f'  agent_id: {len(agent_ids)} agentes o null.' if agent_ids else '  agent_id: null en todos.')
            return

        if clear:
            deleted, _ = InteractionsSummary.objects.filter(
                interaction_id__startswith=FAKE_PREFIX
            ).delete()
            self.stdout.write(
                self.style.WARNING(f'Eliminados {deleted} registros con interaction_id empezando por "{FAKE_PREFIX}".')
            )

        created = 0
        batch = []
        for i in range(cantidad):
            batch.append(self._build_one_record(campaign_ids, agent_ids, end_max))
            if len(batch) >= BATCH_SIZE:
                InteractionsSummary.objects.bulk_create(batch)
                created += len(batch)
                batch = []
                self.stdout.write(f'  Creados {created}/{cantidad}...')
        if batch:
            InteractionsSummary.objects.bulk_create(batch)
            created += len(batch)

        self.stdout.write(
            self.style.SUCCESS(f'Creados {created} registros fake en interactions_summary.')
        )
