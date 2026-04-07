# -*- coding: utf-8 -*-
# Copyright (C) 2018 Freetech Solutions
#
# This file is part of OMniLeads
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version 3, as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#
from django.db import connection
import logging

logger = logging.getLogger(__name__)


class LlamadaResumenService:
    """
    Servicio para actualizar la tabla de resumen de llamadas
    cuando se califica una llamada.
    """
    
    def actualizar_desde_calificacion(self, calificacion):
        """
        Actualiza el registro en reportes_app_llamada_resumen
        con los datos de la calificación.
        
        Args:
            calificacion: Instancia de CalificacionCliente
        """
        if not calificacion:
            logger.warning("Calificacion es None, omitiendo actualización de resumen")
            return False
        
        callid = calificacion.callid
        if not callid:
            logger.warning(f"Calificacion {calificacion.id} no tiene callid, omitiendo actualización")
            return False
        
        try:
            opcion_calificacion = calificacion.opcion_calificacion
            # Determinar si es venta: es_gestion() retorna True cuando tipo == GESTION
            es_venta = opcion_calificacion.es_gestion() if opcion_calificacion else False
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE public.reportes_app_llamada_resumen
                    SET
                        calificacion_id = %s,
                        opcion_calificacion_id = %s,
                        opcion_calificacion_nombre = %s,
                        opcion_calificacion_tipo = %s,
                        subcalificacion = %s,
                        es_venta = %s,
                        updated_at = NOW()
                    WHERE callid = %s
                """, [
                    calificacion.id,
                    opcion_calificacion.id if opcion_calificacion else None,
                    opcion_calificacion.nombre if opcion_calificacion else None,
                    opcion_calificacion.tipo if opcion_calificacion else None,
                    calificacion.subcalificacion or None,
                    es_venta,
                    callid
                ])
                
                rows_updated = cursor.rowcount
                if rows_updated == 0:
                    logger.warning(
                        f"No se encontró registro en resumen para callid={callid}. "
                        "La llamada puede no haber finalizado aún o el registro no existe."
                    )
                    return False
                
                logger.debug(
                    f"Actualizado resumen para callid={callid}, "
                    f"calificacion_id={calificacion.id}, es_venta={es_venta}"
                )
                return True
                
        except Exception as e:
            logger.error(
                f"Error actualizando resumen desde calificación {calificacion.id}: {e}",
                exc_info=True
            )
            return False

