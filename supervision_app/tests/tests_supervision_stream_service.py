# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from supervision_app.services.supervision_stream_service import SupervisionStreamService


class SupervisionStreamServiceTest(SimpleTestCase):

    def test_prepara_agentes_adds_stream_and_skips_voicebot(self):
        conn = MagicMock()
        stream = 'supervisor_5_agentes'
        agent_hashes = {
            'OML:AGENT:10': {
                'STATUS': 'READY',
                'NAME': 'Human',
                'STREAMS': stream,
                'VOICEBOT': None,
            },
            'OML:AGENT:11': {
                'STATUS': 'ONCALL',
                'VOICEBOT': '1',
                'STREAMS': '',
            },
        }
        # Stream ya existía: reset con XTRIM (no DELETE).
        stream_exists = {stream: True}

        def exists(key):
            if key in ('OML:SUPERVISOR:5', 'OML:AGENT:10', 'OML:AGENT:11'):
                return True
            if key == stream:
                return stream_exists.get(stream, False)
            return False

        def hgetall(key):
            if key == 'OML:SUPERVISOR:5':
                return {
                    '10': json.dumps({'grupo': 'G1', 'campana': ['Camp A']}),
                    '11': json.dumps({'grupo': 'G2', 'campana': ['Camp B']}),
                }
            return dict(agent_hashes.get(key, {}))

        def hget(key, field):
            return agent_hashes.get(key, {}).get(field)

        def hset(key, *args, **kwargs):
            mapping = kwargs.get('mapping')
            if mapping is None and len(args) >= 2:
                agent_hashes.setdefault(key, {})[args[0]] = args[1]
                return
            if mapping:
                agent_hashes.setdefault(key, {}).update(mapping)

        def xadd(stream_name, fields, **kwargs):
            if stream_name == stream:
                stream_exists[stream] = True
            return '1-0'

        conn.exists.side_effect = exists
        conn.hgetall.side_effect = hgetall
        conn.hget.side_effect = hget
        conn.hset.side_effect = hset
        conn.xadd.side_effect = xadd
        conn.scan_iter.return_value = []

        service = SupervisionStreamService(conn=conn)
        service.prepara_agentes_para_stream(5, 'agentes')

        conn.xtrim.assert_called_once_with(stream, maxlen=0, approximate=False)
        conn.delete.assert_not_called()
        self.assertIn(stream, agent_hashes['OML:AGENT:10']['STREAMS'])
        # Seed: publish del agente humano (no voicebot); sin start porque ya existía
        xadd_streams = [c[0][0] for c in conn.xadd.call_args_list]
        self.assertEqual(xadd_streams.count(stream), 1)
        payloads = [c[0][1].get('value', '') for c in conn.xadd.call_args_list]
        self.assertTrue(any('READY' in str(p) for p in payloads))
        self.assertFalse(any('VOICEBOT' in str(p) and "'1'" in str(p) for p in payloads))

    def test_prepara_agentes_seeds_stream_after_prepare(self):
        """Sin Gears, el prepare debe XADD el hash de cada agente humano."""
        conn = MagicMock()
        stream = 'supervisor_1_agentes'
        agent_hash = {
            'STATUS': 'ONCALL',
            'NAME': 'Agent One',
            'STREAMS': stream,
            'CAMPANAS': "['Camp A']",
            'GROUP': 'G1',
        }
        state = {'stream_ready': False}

        def exists(key):
            if key in ('OML:SUPERVISOR:1', 'OML:AGENT:2'):
                return True
            if key == stream:
                return state['stream_ready']
            return False

        def hgetall(key):
            if key.startswith('OML:SUPERVISOR'):
                return {'2': json.dumps({'grupo': 'G1', 'campana': ['Camp A']})}
            return dict(agent_hash)

        def hget(key, field):
            return agent_hash.get(field)

        def hset(key, *args, **kwargs):
            mapping = kwargs.get('mapping')
            if mapping is None and len(args) >= 2:
                agent_hash[args[0]] = args[1]
                return
            if mapping:
                agent_hash.update(mapping)

        def xadd(stream_name, fields, **kwargs):
            state['stream_ready'] = True
            return '1-0'

        conn.exists.side_effect = exists
        conn.hgetall.side_effect = hgetall
        conn.hget.side_effect = hget
        conn.hset.side_effect = hset
        conn.xadd.side_effect = xadd
        conn.scan_iter.return_value = []

        service = SupervisionStreamService(conn=conn)
        service.prepara_agentes_para_stream(1, 'agentes')

        # Stream no existía → start marker + seed del agente
        self.assertGreaterEqual(conn.xadd.call_count, 2)
        conn.xtrim.assert_not_called()
        seed_payloads = [
            c[0][1]['value']
            for c in conn.xadd.call_args_list
            if 'value' in c[0][1]
        ]
        self.assertTrue(any('ONCALL' in p and 'Agent One' in p for p in seed_payloads))

    def test_reset_stream_keeps_key_so_concurrent_publish_works(self):
        """H1: durante prepare el stream no desaparece; ACD puede XADD."""
        conn = MagicMock()
        stream = 'supervisor_9_agentes'
        agent_hash = {
            'STATUS': 'READY',
            'NAME': 'Agent',
            'STREAMS': stream,
        }
        state = {'stream_ready': True, 'events': []}

        def exists(key):
            if key in ('OML:SUPERVISOR:9', 'OML:AGENT:1'):
                return True
            if key == stream:
                return state['stream_ready']
            return False

        def hgetall(key):
            if key.startswith('OML:SUPERVISOR'):
                return {'1': json.dumps({'grupo': 'G', 'campana': []})}
            return dict(agent_hash)

        def hget(key, field):
            return agent_hash.get(field)

        def hset(key, *args, **kwargs):
            mapping = kwargs.get('mapping')
            if mapping is None and len(args) >= 2:
                agent_hash[args[0]] = args[1]
                return
            if mapping:
                agent_hash.update(mapping)

        def xtrim(name, maxlen=0, approximate=False):
            # XTRIM vacía entries pero la key sigue existiendo.
            state['stream_ready'] = True

        def xadd(stream_name, fields, **kwargs):
            state['events'].append(fields)
            state['stream_ready'] = True
            return '1-0'

        def delete(key):
            if key == stream:
                state['stream_ready'] = False

        conn.exists.side_effect = exists
        conn.hgetall.side_effect = hgetall
        conn.hget.side_effect = hget
        conn.hset.side_effect = hset
        conn.xtrim.side_effect = xtrim
        conn.xadd.side_effect = xadd
        conn.delete.side_effect = delete
        conn.scan_iter.return_value = []

        service = SupervisionStreamService(conn=conn)

        # Simula publish concurrente de ACD a mitad del prepare (tras reset).
        original_hgetall = conn.hgetall.side_effect

        def hgetall_with_concurrent_publish(key):
            result = original_hgetall(key)
            if key.startswith('OML:SUPERVISOR') and state['stream_ready']:
                agent_hash['STATUS'] = 'ONCALL'
                service.publish_agent_to_streams(1, agent_hash=dict(agent_hash))
            return result

        conn.hgetall.side_effect = hgetall_with_concurrent_publish
        service.prepara_agentes_para_stream(9, 'agentes')

        conn.delete.assert_not_called()
        conn.xtrim.assert_called_once_with(stream, maxlen=0, approximate=False)
        oncall_events = [
            e for e in state['events']
            if 'value' in e and 'ONCALL' in str(e['value'])
        ]
        self.assertTrue(oncall_events)

    def test_sincroniza_campanas_actualiza_lista_stale_y_publica(self):
        conn = MagicMock()
        conn.scan_iter.return_value = ['OML:SUPERVISOR:1']
        conn.exists.return_value = True
        hashes = {
            'OML:SUPERVISOR:1': {
                '2': json.dumps({
                    'grupo': 'G1',
                    'campana': ['DIALER_TEMPLATE_12', 'DIALER_TEMPLATE_13'],
                }),
            },
            'OML:AGENT:2': {
                'STATUS': 'ONCALL',
                'NAME': 'Allen Martin',
                'CAMPANAS': "['DIALER_TEMPLATE_12']",
                'STREAMS': 'supervisor_1_agentes',
                'GROUP': 'G1',
            },
        }
        conn.hgetall.side_effect = lambda key: dict(hashes.get(key, {}))

        def hget(key, field):
            return hashes.get(key, {}).get(field)

        conn.hget.side_effect = hget

        def hset(key, mapping=None, **kwargs):
            if mapping:
                hashes.setdefault(key, {}).update(mapping)

        conn.hset.side_effect = hset
        service = SupervisionStreamService(conn=conn)
        service.sincroniza_campanas_agentes_todos_supervisores()

        self.assertIn('DIALER_TEMPLATE_13', hashes['OML:AGENT:2']['CAMPANAS'])
        conn.xadd.assert_called()
        payload = conn.xadd.call_args[0][1]['value']
        self.assertIn('DIALER_TEMPLATE_13', payload)

    def test_sincroniza_campanas_no_republica_si_ya_coincide(self):
        conn = MagicMock()
        conn.scan_iter.return_value = ['OML:SUPERVISOR:1']
        conn.exists.return_value = True
        campanas = "['DIALER_TEMPLATE_12', 'DIALER_TEMPLATE_13']"
        conn.hgetall.return_value = {
            '2': json.dumps({'grupo': 'G1', 'campana': [
                'DIALER_TEMPLATE_12', 'DIALER_TEMPLATE_13',
            ]}),
        }
        conn.hget.side_effect = lambda key, field: {
            'CAMPANAS': campanas,
            'GROUP': 'G1',
        }.get(field)
        service = SupervisionStreamService(conn=conn)
        service.sincroniza_campanas_agentes_todos_supervisores()
        conn.hset.assert_not_called()
        conn.xadd.assert_not_called()

    def test_publish_agent_to_streams(self):
        conn = MagicMock()
        conn.scan_iter.return_value = ['OML:AGENT:%s' % i for i in range(25)]
        agent_hash = {
            'STATUS': 'READY',
            'STREAMS': 'supervisor_1_agentes',
            'NAME': 'Test',
        }
        conn.hgetall.return_value = agent_hash
        conn.exists.return_value = True
        service = SupervisionStreamService(conn=conn)
        service.publish_agent_to_streams(9, agent_hash=agent_hash)
        conn.xadd.assert_called_once()
        args, kwargs = conn.xadd.call_args
        self.assertEqual(args[0], 'supervisor_1_agentes')
        self.assertIn('READY', args[1]['value'])
        # H4: 25 agentes → maxlen 125
        self.assertEqual(kwargs.get('maxlen'), 125)

    def test_stream_buffer_for_agents_scales_and_caches(self):
        conn = MagicMock()
        conn.scan_iter.return_value = ['OML:AGENT:%s' % i for i in range(40)]
        service = SupervisionStreamService(conn=conn)
        self.assertEqual(service.stream_buffer_for_agents(), 200)
        conn.scan_iter.return_value = []
        self.assertEqual(service.stream_buffer_for_agents(), 200)

    def test_publish_agent_skips_voicebot(self):
        conn = MagicMock()
        conn.scan_iter.return_value = []
        agent_hash = {
            'STATUS': 'ONCALL',
            'VOICEBOT': '1',
            'STREAMS': 'supervisor_1_agentes',
        }
        service = SupervisionStreamService(conn=conn)
        service.publish_agent_to_streams(9, agent_hash=agent_hash)
        conn.xadd.assert_not_called()

    def test_publish_voicebot_active_calls_change(self):
        conn = MagicMock()
        conn.set.return_value = True
        pipe = MagicMock()
        conn.pipeline.return_value = pipe
        conn.hget.return_value = 'supervisor_3_voicebots'
        conn.hgetall.side_effect = [
            {},
            {
                'call-1': json.dumps({
                    'call_id': 'call-1',
                    'campaign_id': '20',
                    'status': 'ONCALL',
                    'timestamp': 1000,
                }),
            },
        ]
        service = SupervisionStreamService(conn=conn)
        service.publish_voicebot_active_calls_change(11)
        self.assertTrue(conn.xadd.called)
        payload = conn.xadd.call_args[0][1]['value']
        self.assertIn("'action': 'upsert'", payload)
        self.assertIn('11__call-1', payload)
        pipe.delete.assert_called()
        pipe.hset.assert_called()
        pipe.execute.assert_called()

    def test_publish_voicebot_skips_when_lock_busy(self):
        conn = MagicMock()
        conn.set.return_value = False
        conn.hget.return_value = 'supervisor_3_voicebots'
        service = SupervisionStreamService(conn=conn)
        with patch(
            'supervision_app.services.supervision_stream_service.time.sleep'
        ):
            with patch(
                'supervision_app.services.supervision_stream_service.'
                'VOICEBOT_FANOUT_LOCK_RETRIES',
                2,
            ):
                service.publish_voicebot_active_calls_change(11)
        conn.xadd.assert_not_called()

    def test_publicar_voicebots_usa_diff_con_lock(self):
        """Scheduler no hace upsert ciego: delega al path con snapshot (H2)."""
        conn = MagicMock()
        conn.scan_iter.return_value = ['OML:VOICEBOT-ACTIVE-CALLS:11']
        service = SupervisionStreamService(conn=conn)
        with patch.object(
            service, 'stream_buffer_for_agents', return_value=100
        ):
            with patch.object(
                service, 'publish_voicebot_active_calls_change'
            ) as publish_mock:
                service.publicar_voicebots_activos_en_streams()
        publish_mock.assert_called_once_with('11', stream_buffer=100)

    def test_refrescar_asignaciones_regenera_y_sincroniza(self):
        """H3: refresh desde DB regenera SUPERVISOR y propaga CAMPANAS/VB streams."""
        conn = MagicMock()
        service = SupervisionStreamService(conn=conn)
        with patch(
            'reportes_app.reportes.reporte_supervisores.ReporteSupervisoresFamily'
        ) as FamilyCls:
            with patch.object(
                service, 'sincroniza_campanas_agentes_todos_supervisores'
            ) as sync_camp:
                with patch.object(
                    service, 'sincroniza_voicebot_streams_todos_supervisores'
                ) as sync_vb:
                    with patch.object(
                        service, 'reconciliar_streams_membership'
                    ) as reconcile:
                        service.refrescar_asignaciones_desde_db()
        FamilyCls.return_value.regenerar_families.assert_called_once()
        sync_camp.assert_called_once()
        sync_vb.assert_called_once()
        reconcile.assert_called_once()

    def test_prepara_agentes_poda_stream_de_agente_que_salio(self):
        """M1: agente fuera del supervisor pierde el stream en STREAMS."""
        conn = MagicMock()
        stream = 'supervisor_1_agentes'
        agent_hashes = {
            'OML:AGENT:2': {
                'STATUS': 'READY',
                'STREAMS': stream,
                'VOICEBOT': None,
            },
            'OML:AGENT:99': {
                'STATUS': 'READY',
                'STREAMS': '{0},supervisor_2_agentes'.format(stream),
                'VOICEBOT': None,
            },
        }

        def exists(key):
            return key in (
                'OML:SUPERVISOR:1', 'OML:AGENT:2', 'OML:AGENT:99', stream)

        def hgetall(key):
            if key == 'OML:SUPERVISOR:1':
                return {'2': json.dumps({'grupo': 'G', 'campana': []})}
            return dict(agent_hashes.get(key, {}))

        def hget(key, field):
            return agent_hashes.get(key, {}).get(field)

        def hset(key, *args, **kwargs):
            mapping = kwargs.get('mapping')
            if mapping is None and len(args) >= 2:
                agent_hashes.setdefault(key, {})[args[0]] = args[1]
                return
            if mapping:
                agent_hashes.setdefault(key, {}).update(mapping)

        conn.exists.side_effect = exists
        conn.hgetall.side_effect = hgetall
        conn.hget.side_effect = hget
        conn.hset.side_effect = hset
        conn.scan_iter.return_value = ['OML:AGENT:2', 'OML:AGENT:99']

        service = SupervisionStreamService(conn=conn)
        with patch.object(service, 'stream_buffer_for_agents', return_value=100):
            service.prepara_agentes_para_stream(1, 'agentes')

        self.assertEqual(agent_hashes['OML:AGENT:99']['STREAMS'], 'supervisor_2_agentes')
        self.assertIn(stream, agent_hashes['OML:AGENT:2']['STREAMS'])

    def test_reconciliar_streams_membership_poda_huerfanos(self):
        """M1: reconciliar quita streams de supervisores inexistentes."""
        conn = MagicMock()
        agent_hashes = {
            'OML:AGENT:5': {
                'STREAMS': 'supervisor_1_agentes,supervisor_9_agentes',
                'VOICEBOT_STREAMS': 'supervisor_9_voicebots',
                'VOICEBOT': None,
            },
        }

        def exists(key):
            return key in ('OML:SUPERVISOR:1', 'OML:AGENT:5')

        def hgetall(key):
            if key == 'OML:SUPERVISOR:1':
                return {'5': json.dumps({'grupo': 'G', 'campana': []})}
            return {}

        def hget(key, field):
            return agent_hashes.get(key, {}).get(field)

        def hset(key, *args, **kwargs):
            if len(args) >= 2:
                agent_hashes.setdefault(key, {})[args[0]] = args[1]

        def scan_iter(match='*'):
            if match.startswith('OML:SUPERVISOR'):
                return ['OML:SUPERVISOR:1']
            return ['OML:AGENT:5']

        conn.exists.side_effect = exists
        conn.hgetall.side_effect = hgetall
        conn.hget.side_effect = hget
        conn.hset.side_effect = hset
        conn.scan_iter.side_effect = scan_iter

        service = SupervisionStreamService(conn=conn)
        service.reconciliar_streams_membership()

        self.assertEqual(
            agent_hashes['OML:AGENT:5']['STREAMS'], 'supervisor_1_agentes')
        self.assertEqual(agent_hashes['OML:AGENT:5']['VOICEBOT_STREAMS'], '')
