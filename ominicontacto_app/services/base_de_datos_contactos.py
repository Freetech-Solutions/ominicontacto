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
Servicio encargado de validar y crear las bases de datos.
"""

from __future__ import unicode_literals

import csv
import io
import json
import logging
import os
import re

from django.conf import settings
from django.db import connection, transaction
from django.utils.encoding import smart_str
from django.utils.translation import gettext as _

from ominicontacto_app.errors import OmlArchivoImportacionInvalidoError, \
    OmlError, OmlParserMaxRowError, OmlParserCsvImportacionError, OmlParserMinRowError
from ominicontacto_app.models import BaseDatosContacto, \
    MetadataBaseDatosContactoDTO, Contacto
from ominicontacto_app.parser import (
    IteratorCSVBuffer, ParserCsv, validate_telefono, validate_telefono_or_ext,
    validate_fechas, validate_horas)
from ominicontacto_app.utiles import elimina_tildes


logger = logging.getLogger(__name__)


COPY_CONTACTO_SQL = (
    "COPY ominicontacto_app_contacto "
    "(telefono, facebook, ig_scoped_id, email, datos, bd_contacto_id, id_externo, es_originario) "
    "FROM STDIN WITH (FORMAT CSV, NULL '\\N')"
)


def format_contacto_copy_line(telefono, datos, bd_contacto_id, id_externo=None, email=''):
    """Formatea una fila CSV para COPY de ominicontacto_app_contacto."""
    buffer_line = io.StringIO()
    writer = csv.writer(buffer_line, lineterminator='\n')
    id_externo_val = r'\N' if id_externo is None else id_externo
    writer.writerow([
        telefono,
        '',
        '',
        email or '',
        datos,
        bd_contacto_id,
        id_externo_val,
        't',
    ])
    return buffer_line.getvalue()


def importar_contactos_con_copy(row_lines_generator, error_holder=None):
    """
    Ejecuta COPY FROM STDIN en streaming dentro de transaction.atomic().

    Las validaciones del generador no deben lanzar excepciones (psycopg2 las
    envuelve en QueryCanceled): deben setear error_holder['error'] y retornar.
    Si hay error_holder['error'] tras el COPY, se relanza para forzar rollback.
    """
    if error_holder is None:
        error_holder = {}
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.copy_expert(COPY_CONTACTO_SQL, IteratorCSVBuffer(row_lines_generator))
        if error_holder.get('error') is not None:
            raise error_holder['error']


class CreacionBaseDatosService(object):

    # TODO: Antes de crear la base de datos debería validar un poco la estructura
    def genera_base_dato_contacto(self, base_datos_contacto):
        """
        Primer paso de la creación de una BaseDatoContacto.

        Este método se encarga de validar los datos para la creación del
        del objeto y llevar a cabo el guardado del mismo.

        Valida:
            Que el archivo subido para importar la base de datos de contactos
            sea y tenga las características válidas.
            Si el archivo es válido, hace el save del objeto y si no los es
            lanza la excepción correspondiente.
        """
        assert (base_datos_contacto.estado in
                (BaseDatosContacto.ESTADO_EN_DEFINICION,
                 BaseDatosContacto.ESTADO_DEFINIDA_ACTUALIZADA))

        csv_extensions = ['.csv']

        file_invalid_msg = _("El archivo especificado para realizar la importación de contactos "
                             "no es válido.")
        filename = base_datos_contacto.nombre_archivo_importacion
        extension = os.path.splitext(filename)[1].lower()
        if extension not in csv_extensions:
            logger.warn(_("La extension {0} no es CSV. ".format(extension)))
            raise OmlArchivoImportacionInvalidoError(file_invalid_msg)
        base_datos_contacto.save()

    def obtener_telefono_y_datos(self, lista_dato, posicion_primer_telefono,
                                 columna_id_externo):
        id_externo = None
        if len(lista_dato) > 1:
            item = []
            for i, valor in enumerate(lista_dato):
                if i == posicion_primer_telefono:
                    telefono = valor
                elif i == columna_id_externo:
                    id_externo = valor
                else:
                    item.append(valor)
        else:
            telefono = lista_dato[0]
            item = ['']

        datos = json.dumps(item)
        return telefono, datos, id_externo

    def importa_contactos(self, base_datos_contacto, campos_telefonicos, columna_id_externo):
        """
        Tercer paso de la creación de una BaseDatosContacto.
        Inserta contactos via PostgreSQL COPY FROM STDIN en streaming (O(1) RAM).
        """
        assert (base_datos_contacto.estado in
                (BaseDatosContacto.ESTADO_EN_DEFINICION,
                 BaseDatosContacto.ESTADO_DEFINIDA_ACTUALIZADA))

        parser = ParserCsv()

        ids_externos = set(
            base_datos_contacto.contactos.exclude(id_externo__isnull=True)
            .exclude(id_externo='')
            .values_list('id_externo', flat=True)
        )

        filas = parser.iter_estructura_archivo(base_datos_contacto)
        encabezado = next(filas)
        posicion_primer_telefono = encabezado.index(str(campos_telefonicos[0]))
        try:
            primera_fila = next(filas)
        except OmlParserMinRowError:
            raise
        except StopIteration:
            raise OmlParserMinRowError(_("El archivo CSV posee menos de 2 filas"))

        cantidad_previa = base_datos_contacto.cantidad_contactos or 0
        contador = {'cantidad': cantidad_previa}
        error_holder = {}
        max_filas = settings.OL_MAX_CANTIDAD_CONTACTOS

        def _procesar_fila(lista_dato, numero_fila):
            # Limite por cantidad de filas del archivo actual (no del acumulado en BD).
            if numero_fila > max_filas:
                error_holder['error'] = OmlParserMaxRowError(
                    _("El archivo CSV posee mas registros de los permitidos "
                      "({max_filas}).").format(max_filas=max_filas))
                return None
            telefono, datos, id_externo = self.obtener_telefono_y_datos(
                lista_dato, posicion_primer_telefono, columna_id_externo)
            if id_externo is not None and id_externo != '':
                if id_externo in ids_externos:
                    error_holder['error'] = CreacionBaseDatosServiceIdExternoError(
                        numero_fila, columna_id_externo, lista_dato, id_externo)
                    return None
                ids_externos.add(id_externo)
            contador['cantidad'] += 1
            return format_contacto_copy_line(
                telefono, datos, base_datos_contacto.id, id_externo=id_externo)

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
        except OmlParserMaxRowError:
            raise
        except OmlParserCsvImportacionError:
            raise

        base_datos_contacto.cantidad_contactos = contador['cantidad']
        base_datos_contacto.save()

    def define_base_dato_contacto(self, base_datos_contacto):
        """
        Último paso de la creación de una BaseDatosContacto.

        Este método se encarga de marcar como definida y lista para su uso a
        la BaseDatosContacto.
        """
        base_datos_contacto.define()

    # def inferir_metadata(self, base_datos_contacto):
    #     """Devuelve instancia de MetadataBaseDatosContactoDTO que describe
    #     la metadata del archivo desde el cual se creará la BD.
    #
    #     :raises: NoSePuedeInferirMetadataError: si no se pudo inferir. Esto
    #              es algo grave, ya que si se lanza es porque no se encontro
    #              ninguna columan con datos que validen como telefono!
    #     """
    #     lineas = [
    #               ["Nombre", "Contacto", "Email"],
    #               ["juan", "549351444444", "juan@example.com"],
    #               ["juan", "549351444444", "juan@example.com"],
    #               ["juan", "549351444444", "juan@example.com"],
    #               ]
    #     service = PredictorMetadataService()
    #     return service.inferir_metadata_desde_lineas(lineas)

    def valida_contactos(self, base_datos_contacto):
        """
        Validacion para ver si existe en la base de datos el contacto
        """
        assert (base_datos_contacto.estado in
                (BaseDatosContacto.ESTADO_EN_DEFINICION,
                 BaseDatosContacto.ESTADO_DEFINIDA_ACTUALIZADA))

        parser = ParserCsv()

        try:
            estructura_archivo = parser.get_estructura_archivo(
                base_datos_contacto)
            cantidad_contactos = 0
            for lista_dato in estructura_archivo[1:]:
                cantidad_contactos += 1
                contacto = Contacto.objects.filter(
                    # id_cliente=int(lista_dato[1]),
                    bd_contacto=base_datos_contacto
                )
                if len(contacto) > 0:
                    raise (ContactoExistenteError(_("ya existe el contacto con el"
                                                    "  de id de cliente: {0}"
                                                    " la base de datos ".format(
                                                        int(lista_dato[1])))))

        except OmlParserMaxRowError:
            base_datos_contacto.elimina_contactos()
            raise

        except OmlParserCsvImportacionError:
            base_datos_contacto.elimina_contactos()
            raise


class NoSePuedeInferirMetadataError(OmlError):
    """Indica que no se puede inferir los metadatos"""
    pass


class NoSePuedeInferirMetadataErrorEncabezado(OmlError):
    """Indica que no se puede inferir los metadatos"""
    pass


class ContactoExistenteError(OmlError):
    """este contacto con este id de cliente ya existe"""
    pass


class CreacionBaseDatosServiceIdExternoError(OmlParserCsvImportacionError):
    """
    Error en la importación de los contactos del archivo csv. El id externo ya existe.
    """
    pass


DOUBLE_SPACES = re.compile(r' +')


class PredictorMetadataService(object):
    """
    Obtener/Adivinar/Predecir/Inferir cuál es la columna con el teléfono,
    fecha, hora.
    Generar la metadata que representara esto datos de la BDC.
    """

    def _inferir_columnas(self, lineas, func_validadora):
        assert callable(func_validadora)

        matriz = []
        for linea in lineas:
            matriz.append([func_validadora(celda)
                           for celda in linea])

        # https://stackoverflow.com/questions/4937491/\
        #    matrix-transpose-in-python
        matriz_transpuesta = zip(*matriz)
        resultado_validacion_por_columna = [all(lista)
                                            for lista in matriz_transpuesta]

        return [index
                for index, value in enumerate(resultado_validacion_por_columna)
                if value]

    def sanear_nombre_de_columna(self, nombre):
        """Realiza saneamiento básico del nombre de la columna. Con basico
        se refiere a:
        - eliminar trailing spaces
        - pasar a mayusculas
        - reemplazar espacios por '_'
        - eliminar tildes

        Los caracteres invalidos NO son borrados.
        """
        nombre = smart_str(nombre)
        nombre = nombre.strip().upper()
        nombre = DOUBLE_SPACES.sub("_", nombre)
        nombre = elimina_tildes(nombre)
        return nombre

    def inferir_metadata_desde_lineas(self, lineas_unsafe, permitir_ext_pbx=False):
        """Infiere los metadatos desde las lineas pasadas por parametros.

        Devuelve instancias de MetadataBaseDatosContactoDTO.
        """
        assert isinstance(lineas_unsafe, (list, tuple))

        lineas = []
        for linea in lineas_unsafe:
            # FIXME: revisar esto del encoding para py3
            lineas.append(
                [smart_str(col) for col in linea]
            )
        del lineas_unsafe

        logger.debug("inferir_metadata_desde_lineas(): %s", lineas)

        if len(lineas) < 2:
            logger.debug(_("Se deben proveer al menos 2 lineas: {0}".format(lineas)))
            raise NoSePuedeInferirMetadataError(_("Se deben proveer al menos 2 "
                                                  "lineas para poder inferir "
                                                  "los metadatos"))

        # Primero chequeamos q' haya igual cant. de columnas
        set_cant_columnas = set([len(linea) for linea in lineas])
        if len(set_cant_columnas) != 1:
            logger.debug(_("Distintas cantidades "
                           "de columnas: {0}".format(set_cant_columnas)))
            raise NoSePuedeInferirMetadataError(_("Las lineas recibidas "
                                                  "poseen distintas cantidades "
                                                  "de columnas"))

        primer_linea = lineas[0]
        otras_lineas = lineas[1:]
        metadata = MetadataBaseDatosContactoDTO()

        # Ahora chequeamos que haya al menos 1 columna
        if len(primer_linea) == 0:
            logger.debug(_("Las lineas no poseen ninguna "
                           "columna: {0}".format(primer_linea)))
            raise NoSePuedeInferirMetadataError(_("Las lineas no poseen ninguna "
                                                  "columna"))

        metadata.cantidad_de_columnas = len(primer_linea)

        # NO chequeamos que el nombre de la primera columna sea telefono
        # if primer_linea[0] != 'telefono':
        #     raise (NoSePuedeInferirMetadataErrorEncabezado(_("El nombre de la primera "
        #                                                      "columna debe ser telefono")))

        # ======================================================================
        # Primero detectamos columnas de datos
        # ======================================================================

        columnas_con_telefonos = self._inferir_columnas(
            otras_lineas, validate_telefono if not permitir_ext_pbx else validate_telefono_or_ext)

        logger.debug(_("columnas_con_telefonos: {0}".format(columnas_con_telefonos)))

        columnas_con_fechas = self._inferir_columnas(
            otras_lineas, lambda x: validate_fechas([x]))

        logger.debug("columnas_con_fechas: {0}".format(columnas_con_fechas))

        columnas_con_horas = self._inferir_columnas(
            otras_lineas, lambda x: validate_horas([x]))

        logger.debug("columnas_con_horas: {0}".format(columnas_con_horas))

        columna_con_telefono = None
        if len(columnas_con_telefonos) == 0:
            logger.debug(_("No se encontro columna con telefono"))

        else:
            # Se detecto 1 o mas columnas con telefono. Usamos la 1ra.
            logger.debug(_("Se detecto: columnas_con_telefonos: {0}".format(
                columnas_con_telefonos)))

            if columnas_con_telefonos[0] in columnas_con_fechas:
                logger.warn(_("La columna con telefono tambien esta entre "
                              "las columnas detectadas como fecha"))

            elif columnas_con_telefonos[0] in columnas_con_horas:
                logger.warn(_("La columna con telefono tambien esta entre "
                              "las columnas detectadas como hora"))
            else:
                columna_con_telefono = columnas_con_telefonos[0]

        if columna_con_telefono is not None:
            metadata.columna_con_telefono = columna_con_telefono

        metadata.columnas_con_fecha = columnas_con_fechas
        metadata.columnas_con_hora = columnas_con_horas

        # Si no hemos inferido nada, salimos
        if columna_con_telefono is None:
            # En realidad, al menos el numero de columans debio ser
            # inferido. Pero si ni siquiera se detecto numero de
            # telefono, se debe a que (a) hay un bug en esta logica
            # (b) la BD es invalida. Asi que, de cualquire manera,
            # no creo q' valga la pena devolver la instancia de mentadata,
            # me parece mas significativo reportar el hecho de que
            # no se pudo inferir el metadato.
            raise NoSePuedeInferirMetadataError(_("No se pudo inferir ningun "
                                                  "tipo de dato"))

        # ======================================================================
        # Si detectamos telefono, fecha u hora podemos verificar si la
        #  primer linea es encabezado o dato
        # ======================================================================

        validaciones_primer_linea = []

        if columna_con_telefono is not None:
            validaciones_primer_linea.append(
                validate_telefono(primer_linea[columna_con_telefono]))

        for col_fecha in metadata.columnas_con_fecha:
            validaciones_primer_linea.append(
                validate_fechas([primer_linea[col_fecha]]))

        for col_hora in metadata.columnas_con_hora:
            validaciones_primer_linea.append(
                validate_horas([primer_linea[col_hora]]))

        assert validaciones_primer_linea
        logger.debug("validaciones_primer_linea: %s",
                     validaciones_primer_linea)

        primera_fila_es_dato = all(validaciones_primer_linea)
        metadata.primer_fila_es_encabezado = not primera_fila_es_dato

        nombres = []
        if metadata.primer_fila_es_encabezado:
            nombres_orig = [x.strip() for x in primer_linea]
            for num, nombre_columna in enumerate(nombres_orig):
                nombre_columna = self.sanear_nombre_de_columna(nombre_columna)

                # si no hay nombre, le asignamos un nombre generico
                if not nombre_columna:
                    nombre_columna = self.sanear_nombre_de_columna(
                        "COLUMNA_{0}".format(num + 1))

                # revisamos q' no se repita con los preexistentes
                while nombre_columna in nombres:
                    nombre_columna = self.sanear_nombre_de_columna(
                        nombre_columna + "_REPETIDO")

                nombres.append(nombre_columna)

        else:
            nombres = [
                self.sanear_nombre_de_columna("Columna {0}".format(num + 1))
                for num in range(metadata.cantidad_de_columnas)
            ]

        metadata.nombres_de_columnas = nombres

        return metadata

    def inferir_metadata_desde_lineas_base_existente(self, base_datos_contacto,
                                                     lineas_unsafe):
        """Infiere los metadatos desde las lineas pasadas por parametros.
            con base de datos exitente
        Devuelve instancias de MetadataBaseDatosContactoDTO.
        Copiado desde self.inferir_metadata_desde_lineas()
        """
        assert isinstance(lineas_unsafe, (list, tuple))

        lineas = []
        for linea in lineas_unsafe:
            lineas.append(
                [smart_str(col) for col in linea]
            )
        del lineas_unsafe

        logger.debug("inferir_metadata_desde_lineas(): %s", lineas)

        if len(lineas) < 2:
            logger.debug(_("Se deben proveer al menos 2 lineas: {0}".format(lineas)))
            raise NoSePuedeInferirMetadataError(_("Se deben proveer al menos 2 "
                                                  "lineas para poder inferir "
                                                  "los metadatos"))

        # Primero chequeamos q' haya igual cant. de columnas
        set_cant_columnas = set([len(linea) for linea in lineas])
        if len(set_cant_columnas) != 1:
            logger.debug("Distintas cantidades "
                         "de columnas: %s", set_cant_columnas)
            raise NoSePuedeInferirMetadataError(_("Las lineas recibidas "
                                                  "poseen distintas cantidades "
                                                  "de columnas"))

        primer_linea = lineas[0]
        otras_lineas = lineas[1:]
        metadata = base_datos_contacto.get_metadata()

        # Ahora chequeamos que haya al menos 1 columna
        if len(primer_linea) == 0:
            logger.debug("Las lineas no poseen ninguna "
                         "columna: %s", primer_linea)
            raise NoSePuedeInferirMetadataError(_("Las lineas no poseen ninguna "
                                                  "columna"))

        if metadata.cantidad_de_columnas != len(primer_linea):
            logger.debug("Distintas cantidades "
                         "de columnas: %s", set_cant_columnas)
            raise (NoSePuedeInferirMetadataError(_("Las lineas recibidas "
                                                   "poseen distintas cantidades "
                                                   "de columnas")))
        metadata.cantidad_de_columnas = len(primer_linea)

        # chequeamos que el nombre de las columnas sean los mismo cargado previamente
        for columna_base, columna_csv in zip(metadata.nombres_de_columnas, primer_linea):
            if str(columna_base).capitalize() != str(columna_csv).capitalize():
                raise (NoSePuedeInferirMetadataErrorEncabezado(
                    _("El nombre de la  columna {0} no coincide con el "
                      "guardado en la base ".format(columna_base))))

        # ======================================================================
        # Primero detectamos columnas de datos
        # ======================================================================

        columnas_con_telefonos = self._inferir_columnas(
            otras_lineas, validate_telefono)

        logger.debug("columnas_con_telefonos: %s", columnas_con_telefonos)

        columnas_con_fechas = self._inferir_columnas(
            otras_lineas, lambda x: validate_fechas([x]))

        logger.debug("columnas_con_fechas: %s", columnas_con_fechas)

        columnas_con_horas = self._inferir_columnas(
            otras_lineas, lambda x: validate_horas([x]))

        logger.debug("columnas_con_horas: %s", columnas_con_horas)

        columna_con_telefono = None
        if len(columnas_con_telefonos) == 0:
            logger.debug("No se encontro columna con telefono")

        else:
            # Se detecto 1 o mas columnas con telefono. Usamos la 1ra.
            logger.debug("Se detecto: columnas_con_telefonos: %s",
                         columnas_con_telefonos)

            if columnas_con_telefonos[0] in columnas_con_fechas:
                logger.warn(_("La columna con telefono tambien esta entre "
                              "las columnas detectadas como fecha"))

            elif columnas_con_telefonos[0] in columnas_con_horas:
                logger.warn(_("La columna con telefono tambien esta entre "
                              "las columnas detectadas como hora"))
            else:
                columna_con_telefono = columnas_con_telefonos[0]

        if columna_con_telefono is not None:
            metadata.columna_con_telefono = columna_con_telefono

        metadata.columnas_con_fecha = columnas_con_fechas
        metadata.columnas_con_hora = columnas_con_horas

        # Si no hemos inferido nada, salimos
        if columna_con_telefono is None:
            # En realidad, al menos el numero de columans debio ser
            # inferido. Pero si ni siquiera se detecto numero de
            # telefono, se debe a que (a) hay un bug en esta logica
            # (b) la BD es invalida. Asi que, de cualquire manera,
            # no creo q' valga la pena devolver la instancia de mentadata,
            # me parece mas significativo reportar el hecho de que
            # no se pudo inferir el metadato.
            raise NoSePuedeInferirMetadataError(_("No se pudo inferir ningun "
                                                  "tipo de dato"))

        # ======================================================================
        # Si detectamos telefono, fecha u hora podemos verificar si la
        #  primer linea es encabezado o dato
        # ======================================================================

        validaciones_primer_linea = []

        if columna_con_telefono is not None:
            validaciones_primer_linea.append(
                validate_telefono(primer_linea[columna_con_telefono]))

        for col_fecha in metadata.columnas_con_fecha:
            validaciones_primer_linea.append(
                validate_fechas([primer_linea[col_fecha]]))

        for col_hora in metadata.columnas_con_hora:
            validaciones_primer_linea.append(
                validate_horas([primer_linea[col_hora]]))

        assert validaciones_primer_linea
        logger.debug("validaciones_primer_linea: %s",
                     validaciones_primer_linea)

        primera_fila_es_dato = all(validaciones_primer_linea)
        metadata.primer_fila_es_encabezado = not primera_fila_es_dato

        nombres = []
        if metadata.primer_fila_es_encabezado:
            nombres_orig = [x.strip() for x in primer_linea]
            for num, nombre_columna in enumerate(nombres_orig):
                nombre_columna = self.sanear_nombre_de_columna(nombre_columna)

                # si no hay nombre, le asignamos un nombre generico
                if not nombre_columna:
                    nombre_columna = self.sanear_nombre_de_columna(
                        "COLUMNA_{0}".format(num + 1))

                # revisamos q' no se repita con los preexistentes
                while nombre_columna in nombres:
                    nombre_columna = self.sanear_nombre_de_columna(
                        nombre_columna + "_REPETIDO")

                nombres.append(nombre_columna)

        else:
            nombres = [
                self.sanear_nombre_de_columna("Columna {0}".format(num + 1))
                for num in range(metadata.cantidad_de_columnas)
            ]

        metadata.nombres_de_columnas = nombres

        return metadata

    def inferir_columnas_telefono(self, otras_lineas):
        lineas = []
        for linea in otras_lineas:
            lineas.append(
                [smart_str(col) for col in linea]
            )
        columnas_con_telefonos = self._inferir_columnas(
            lineas, validate_telefono)

        logger.debug("columnas_con_telefonos: %s", columnas_con_telefonos)
        return columnas_con_telefonos


class BaseDatosService(object):
    """Servicio de base de datos usado para eliminar contactos duplicados
       se podria eliminar este servicio ya que el filtro se está haciendo por la pk
       jamas habria una pk duplicada
    """

    def eliminar_contactos_duplicados(self, base_datos):

        contactos = Contacto.objects.filter(bd_contacto=base_datos)
        cantidad_contactos = base_datos.cantidad_contactos
        for contacto in contactos:
            if contactos.filter(pk=contacto.pk).count() > 1:
                contacto.delete()
                cantidad_contactos -= 1

        base_datos.cantidad_contactos = cantidad_contactos
        base_datos.save()
