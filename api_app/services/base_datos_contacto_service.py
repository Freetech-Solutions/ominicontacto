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
from __future__ import unicode_literals

import json

from django.conf import settings
from django.utils.translation import gettext as _

from ominicontacto_app.services.base_de_datos_contactos import (
    CreacionBaseDatosServiceIdExternoError, PredictorMetadataService,
    format_contacto_copy_line, importar_contactos_con_copy)
from ominicontacto_app.parser import ParserCsv
from ominicontacto_app.errors import OmlArchivoImportacionInvalidoError, \
    OmlError, OmlParserCsvImportacionError, OmlParserMaxRowError, \
    OmlParserMinRowError, OmlParserRepeatedColumnsError
from ominicontacto_app.models import BaseDatosContacto

from api_app.utils.contactos.base_datos_contacto_archivo_parser \
    import BaseDatosContactoArchivoCSVParser


class BaseDatosContactoService(object):

    def __init__(self) -> None:
        self.parser = None
        self.legacy_parser = ParserCsv()

    def crear_bd_contactos(self, archivo, nombre_archivo, nombre_bd) -> int:
        model_base_contactos = BaseDatosContacto()
        if self._existe_bd_contactos(nombre_bd):
            raise OmlError(_("Ya existe una base de datos de contactos con ese nombre"))
        self.parser = BaseDatosContactoArchivoCSVParser(nombre_archivo, archivo)

        if not self.parser.es_valida_extension() or not self.parser.es_valido_archivo():
            file_invalid_msg = _("El archivo especificado para realizar la importación de "
                                 "contactos no es válido.")
            raise OmlArchivoImportacionInvalidoError(file_invalid_msg)

        if not self.parser.headers_no_repetidos():
            raise OmlParserRepeatedColumnsError(_("El archivo a procesar tiene nombres de columnas "
                                                  "repetidos."))

        if hasattr(archivo, 'seek'):
            archivo.seek(0)

        model_base_contactos.archivo_importacion = archivo
        model_base_contactos.nombre_archivo_importacion = nombre_archivo
        model_base_contactos.nombre = nombre_bd
        model_base_contactos.save()

        return model_base_contactos.id

    def define_base_datos_contactos(self, base_datos_contacto) -> None:
        base_datos_contacto.define()

    def obtiene_subconjunto_filas_archivo(self, base_datos_contacto) -> dict:
        return self.legacy_parser.previsualiza_archivo(base_datos_contacto)

    def inferir_metadata(self, estructura_archivo):
        predictor_metadata = PredictorMetadataService()
        return predictor_metadata.inferir_metadata_desde_lineas(
            estructura_archivo)

    def importa_contactos_desde_api(self, id, campos_telefonicos, columna_id_externo,
                                    columna_email):
        bd_contactos = BaseDatosContacto.objects.obtener_en_actualizada_para_editar(id)
        self.importa_contactos(bd_contactos, campos_telefonicos, columna_id_externo, columna_email)

    def importa_contactos(self, base_datos_contacto, campos_telefonicos, columna_id_externo,
                          columna_email):
        """
        Tercer paso de la creación de una BaseDatosContacto.
        Inserta contactos via PostgreSQL COPY FROM STDIN en streaming (O(1) RAM).
        """
        assert (base_datos_contacto.estado in
                (BaseDatosContacto.ESTADO_EN_DEFINICION,
                 BaseDatosContacto.ESTADO_DEFINIDA_ACTUALIZADA))

        ids_externos = set(
            base_datos_contacto.contactos.exclude(id_externo__isnull=True)
            .exclude(id_externo='')
            .values_list('id_externo', flat=True)
        )

        filas = self.legacy_parser.iter_estructura_archivo(base_datos_contacto)
        encabezado = next(filas)
        posicion_primer_telefono = encabezado.index(campos_telefonicos[0])
        try:
            primera_fila = next(filas)
        except OmlParserMinRowError:
            raise
        except StopIteration:
            raise OmlParserMinRowError(_("El archivo CSV posee menos de 2 filas"))

        cantidad_previa = base_datos_contacto.cantidad_contactos or 0
        contador = {'cantidad': cantidad_previa, 'filas_archivo': 0}
        error_holder = {}
        max_filas = settings.OL_MAX_CANTIDAD_CONTACTOS

        def _procesar_fila(lista_dato, numero_fila):
            # Limite por cantidad de filas del archivo actual (no del acumulado en BD).
            if numero_fila > max_filas:
                error_holder['error'] = OmlParserMaxRowError(
                    _("El archivo CSV posee mas registros de los permitidos "
                      "({max_filas}).").format(max_filas=max_filas))
                return None
            telefono, datos, id_externo, email = self._obtener_telefono_y_datos(
                lista_dato, posicion_primer_telefono, columna_id_externo, columna_email)
            if id_externo is not None and id_externo != '':
                if id_externo in ids_externos:
                    error_holder['error'] = CreacionBaseDatosServiceIdExternoError(
                        numero_fila, columna_id_externo, lista_dato, id_externo)
                    return None
                ids_externos.add(id_externo)
            contador['cantidad'] += 1
            contador['filas_archivo'] += 1
            return format_contacto_copy_line(
                telefono, datos, base_datos_contacto.id,
                id_externo=id_externo, email=email)

        def row_lines():
            numero_fila = 1
            linea = _procesar_fila(primera_fila, numero_fila)
            if linea is None:
                return
            yield linea
            for lista_dato in filas:
                numero_fila += 1
                linea = _procesar_fila(lista_dato, numero_fila)
                if linea is None:
                    return
                yield linea

        try:
            importar_contactos_con_copy(row_lines(), error_holder)
        except CreacionBaseDatosServiceIdExternoError:
            raise
        except OmlParserMaxRowError as e:
            raise OmlError(
                _("Archivo excede máximo de filas permitidas ({max_filas}). {detalle}").format(
                    max_filas=max_filas, detalle=e))
        except OmlParserCsvImportacionError:
            raise OmlError(_("Error al parsear el archivo csv"))

        base_datos_contacto.cantidad_contactos = contador['cantidad']
        base_datos_contacto.save()
        self.define_base_datos_contactos(base_datos_contacto)

    def _existe_bd_contactos(self, nombre) -> bool:
        return BaseDatosContacto.objects.filter(nombre=nombre).exists()

    def _obtener_telefono_y_datos(self, lista_dato, posicion_primer_telefono,
                                  columna_id_externo, columna_email) -> any:
        id_externo = None
        email = ""
        if len(lista_dato) > 1:
            item = []
            for i, valor in enumerate(lista_dato):
                if i == posicion_primer_telefono:
                    telefono = valor
                elif i == columna_id_externo:
                    id_externo = valor
                elif i == columna_email:
                    email = valor
                else:
                    item.append(valor)
        else:
            telefono = lista_dato[0]
            item = ['']

        datos = json.dumps(item)
        return telefono, datos, id_externo, email

    def remove_db(self, id):
        BaseDatosContacto.objects.filter(id=id).delete()
