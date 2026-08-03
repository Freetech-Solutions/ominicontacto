# -*- coding: utf-8 -*-

from mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework import status

from facebook_meta_app.api.v1.page_configuration import ViewSet


class PageConfigurationDestroyTests(SimpleTestCase):

    @patch('facebook_meta_app.api.v1.page_configuration.StreamDePaginas')
    @patch('facebook_meta_app.api.v1.page_configuration.PaginaMetaFacebook.objects.get')
    def test_destroy_deactivates_page_before_notifying_stream(
            self, get_page, stream_class):
        page = MagicMock(id=1, is_active=True)
        get_page.return_value = page

        response = ViewSet().destroy(request=None, pk=page.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(page.is_active)
        page.save.assert_called_once_with(update_fields=['is_active'])
        page.delete.assert_not_called()
        stream_class.return_value.notificar_page_eliminada.assert_called_once_with(page)
