from django.core.exceptions import ValidationError
from mock import Mock

from configuracion_telefonia_app.models import MusicaDeEspera
from configuracion_telefonia_app.tests.factories import PlaylistFactory
from ominicontacto_app.forms.base import CampanaManualForm, CampanaPreviewForm
from ominicontacto_app.models import Campana
from ominicontacto_app.services.asterisk.redis_database import CampanaFamily
from ominicontacto_app.tests.factories import CampanaFactory, QueueFactory
from ominicontacto_app.tests.utiles import OMLBaseTest
from ominicontacto_app.views_campana_manual_creacion import (
    CampanaManualTemplateCreateCampanaView, CampanaManualUpdateView,
)
from ominicontacto_app.views_campana_preview import (
    CampanaPreviewTemplateCreateCampanaView, CampanaPreviewUpdateView,
)


class MusicaEsperaCampanasTests(OMLBaseTest):
    def setUp(self):
        super().setUp()
        self.playlist = PlaylistFactory()
        self.playlist_vacia = PlaylistFactory()
        MusicaDeEspera.objects.create(nombre='MusicaPrueba', playlist=self.playlist)

    def test_formularios_solo_permiten_playlists_con_musica(self):
        for form_class in (CampanaManualForm, CampanaPreviewForm):
            with self.subTest(form=form_class.__name__):
                field = form_class().fields['musiconhold']
                self.assertEqual(field.clean(self.playlist.pk), self.playlist)
                self.assertIsNone(field.clean(''))
                with self.assertRaises(ValidationError):
                    field.clean(self.playlist_vacia.pk)
                with self.assertRaises(ValidationError):
                    field.clean(-1)

    def test_formularios_recuperan_musica_al_editar(self):
        for form_class, tipo in ((CampanaManualForm, Campana.TYPE_MANUAL),
                                 (CampanaPreviewForm, Campana.TYPE_PREVIEW)):
            with self.subTest(tipo=tipo):
                campana = CampanaFactory(type=tipo)
                QueueFactory(campana=campana, musiconhold=self.playlist)
                form = form_class(instance=campana)
                self.assertEqual(form['musiconhold'].value(), self.playlist.pk)

    def test_creacion_desde_template_recupera_musica(self):
        for view_class, tipo in (
                (CampanaManualTemplateCreateCampanaView, Campana.TYPE_MANUAL),
                (CampanaPreviewTemplateCreateCampanaView, Campana.TYPE_PREVIEW)):
            with self.subTest(tipo=tipo):
                campana = CampanaFactory(type=tipo, estado=Campana.ESTADO_TEMPLATE_ACTIVO)
                QueueFactory(campana=campana, musiconhold=self.playlist)
                view = view_class()
                view.kwargs = {'pk_campana_template': campana.pk}
                initial = view.get_form_initial(view.INICIAL)
                self.assertEqual(initial['musiconhold'], self.playlist.pk)

    def test_edicion_permite_cambiar_y_quitar_musica(self):
        for view_class, tipo in ((CampanaManualUpdateView, Campana.TYPE_MANUAL),
                                 (CampanaPreviewUpdateView, Campana.TYPE_PREVIEW)):
            with self.subTest(tipo=tipo):
                campana = CampanaFactory(type=tipo)
                queue = QueueFactory(campana=campana)
                view = view_class()
                form = Mock(instance=campana, cleaned_data={
                    'auto_grabacion': queue.auto_grabacion,
                    'summarize_percentage': queue.summarize_percentage,
                    'transcription_percentage': queue.transcription_percentage,
                })
                for playlist in (self.playlist, None):
                    form.cleaned_data['musiconhold'] = playlist
                    view._save_forms({view.INICIAL: form, view.OPCIONES_CALIFICACION: Mock()})
                    queue.refresh_from_db()
                    self.assertEqual(queue.musiconhold, playlist)

    def test_redis_publica_y_elimina_moh_en_todos_los_tipos_de_campana(self):
        for tipo in (Campana.TYPE_MANUAL, Campana.TYPE_PREVIEW,
                     Campana.TYPE_ENTRANTE, Campana.TYPE_DIALER):
            with self.subTest(tipo=tipo):
                campana = CampanaFactory(type=tipo)
                queue = QueueFactory(campana=campana, musiconhold=self.playlist)
                redis = Mock()
                family = CampanaFamily(redis_connection=redis)
                family.regenerar_family(campana)
                self.assertEqual(redis.hset.call_args.kwargs['mapping']['MOH'],
                                 self.playlist.nombre)
                queue.musiconhold = None
                queue.save()
                family.regenerar_family(campana)
                self.assertNotIn('MOH', redis.hset.call_args.kwargs['mapping'])
                self.assertEqual(redis.delete.call_count, 2)
