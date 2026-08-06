/* Copyright (C) 2018 Freetech Solutions

 This file is part of OMniLeads

 This program is free software: you can redistribute it and/or modify
 it under the terms of the GNU Lesser General Public License version 3, as published by
 the Free Software Foundation.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Lesser General Public License for more details.

 You should have received a copy of the GNU Lesser General License
 along with this program.  If not, see http://www.gnu.org/licenses/.

 Mismo date picker que Reportes/Agentes: un campo con daterangepicker y presets.
*/

(function() {
    'use strict';

    function formatRange(startDate, endDate) {
        return startDate.format('DD/MM/YYYY') + ' - ' + endDate.format('DD/MM/YYYY');
    }

    function parseExistingRange(rawValue) {
        var value = (rawValue || '').trim();
        if (!value) return null;

        var parts = value.split(/\s*-\s*/);
        if (parts.length < 2) return null;

        var startDate = moment(parts[0], 'DD/MM/YYYY', true);
        var endDate = moment(parts[1], 'DD/MM/YYYY', true);
        if (!startDate.isValid() || !endDate.isValid()) return null;

        return { startDate: startDate, endDate: endDate };
    }

    function initDateRangePicker() {
        var $fecha = $('#id_fecha');
        if (!$fecha.length || !$.fn.daterangepicker || typeof get_ranges !== 'function') return;

        var parsedRange = parseExistingRange($fecha.val());
        var startDate = parsedRange ? parsedRange.startDate : moment();
        var endDate = parsedRange ? parsedRange.endDate : moment();

        $fecha.daterangepicker({
            locale: {
                format: 'DD/MM/YYYY'
            },
            startDate: startDate,
            endDate: endDate,
            ranges: get_ranges(),
        });

        $fecha.val(formatRange(startDate, endDate));

        $fecha.on('apply.daterangepicker', function(ev, picker) {
            $(this).val(formatRange(picker.startDate, picker.endDate));
        });

        $fecha.on('cancel.daterangepicker', function() {
            $(this).val('');
        });
    }

    function initCampanasSelect() {
        var $campanaSelect = $('#id_campana');
        var $incluirFinalizadas = $('#id_incluir_finalizadas');
        if (!$campanaSelect.length) return;

        var allCampaignsValue = $campanaSelect.attr('data-all-campaign-value') || '__all__';
        var finalizedIds = (($campanaSelect.attr('data-finalized-ids') || '').split(','))
            .map(function(id) { return id.trim(); })
            .filter(function(id) { return id.length > 0; });
        var isAdjustingSelection = false;

        if ($.fn.select2) {
            $campanaSelect.select2({
                width: '100%',
                closeOnSelect: false,
                placeholder: $campanaSelect.attr('data-placeholder') || ''
            });
        }

        function toggleFinalizedOptions() {
            var includeFinalized = $incluirFinalizadas.is(':checked');
            var selectedValues = $campanaSelect.val() || [];
            var updatedValues = selectedValues.slice();

            $campanaSelect.find('option').each(function() {
                var optionValue = $(this).val();
                if (finalizedIds.indexOf(optionValue) !== -1) {
                    this.disabled = !includeFinalized;
                }
            });

            if (!includeFinalized) {
                updatedValues = updatedValues.filter(function(value) {
                    return finalizedIds.indexOf(value) === -1;
                });
            }

            if (updatedValues.length !== selectedValues.length) {
                isAdjustingSelection = true;
                $campanaSelect.val(updatedValues).trigger('change.select2');
                isAdjustingSelection = false;
            } else {
                $campanaSelect.trigger('change.select2');
            }
        }

        function enforceAllCampaignsExclusivity() {
            if (isAdjustingSelection) return;
            var selectedValues = $campanaSelect.val() || [];
            if (selectedValues.indexOf(allCampaignsValue) === -1 || selectedValues.length <= 1) {
                return;
            }

            var normalizedValues = selectedValues;
            if (selectedValues[selectedValues.length - 1] === allCampaignsValue) {
                normalizedValues = [allCampaignsValue];
            } else {
                normalizedValues = selectedValues.filter(function(value) {
                    return value !== allCampaignsValue;
                });
            }

            isAdjustingSelection = true;
            $campanaSelect.val(normalizedValues).trigger('change.select2');
            isAdjustingSelection = false;
        }

        $campanaSelect.on('change', function() {
            enforceAllCampaignsExclusivity();
        });

        $incluirFinalizadas.on('change', function() {
            toggleFinalizedOptions();
        });

        toggleFinalizedOptions();
        enforceAllCampaignsExclusivity();
    }

    function initGruposSelect() {
        var $groupSelect = $('#id_grupo_agente');
        if (!$groupSelect.length) return;

        var allGroupsValue = $groupSelect.attr('data-all-groups-value') || '__all_groups__';
        var isAdjustingSelection = false;

        if ($.fn.select2) {
            $groupSelect.select2({
                width: '100%',
                closeOnSelect: false,
                placeholder: $groupSelect.attr('data-placeholder') || ''
            });
        }

        function enforceAllGroupsExclusivity() {
            if (isAdjustingSelection) return;
            var selectedValues = $groupSelect.val() || [];
            if (selectedValues.indexOf(allGroupsValue) === -1 || selectedValues.length <= 1) {
                return;
            }

            var normalizedValues = selectedValues;
            if (selectedValues[selectedValues.length - 1] === allGroupsValue) {
                normalizedValues = [allGroupsValue];
            } else {
                normalizedValues = selectedValues.filter(function(value) {
                    return value !== allGroupsValue;
                });
            }

            isAdjustingSelection = true;
            $groupSelect.val(normalizedValues).trigger('change.select2');
            isAdjustingSelection = false;
        }

        function ensureDefaultAllGroups() {
            var selectedValues = $groupSelect.val() || [];
            if (selectedValues.length) return;

            isAdjustingSelection = true;
            $groupSelect.val([allGroupsValue]).trigger('change.select2');
            isAdjustingSelection = false;
        }

        $groupSelect.on('change', function() {
            enforceAllGroupsExclusivity();
        });

        ensureDefaultAllGroups();
        enforceAllGroupsExclusivity();
    }

    function initAgentesSelect() {
        var $agentSelect = $('#id_agente');
        if (!$agentSelect.length) return;

        var allAgentsValue = $agentSelect.attr('data-all-agents-value') || '__all_agents__';
        var isAdjustingSelection = false;

        if ($.fn.select2) {
            $agentSelect.select2({
                width: '100%',
                closeOnSelect: false,
                placeholder: $agentSelect.attr('data-placeholder') || ''
            });
        }

        function enforceAllAgentsExclusivity() {
            if (isAdjustingSelection) return;
            var selectedValues = $agentSelect.val() || [];
            if (selectedValues.indexOf(allAgentsValue) === -1 || selectedValues.length <= 1) {
                return;
            }

            var normalizedValues = selectedValues;
            if (selectedValues[selectedValues.length - 1] === allAgentsValue) {
                normalizedValues = [allAgentsValue];
            } else {
                normalizedValues = selectedValues.filter(function(value) {
                    return value !== allAgentsValue;
                });
            }

            isAdjustingSelection = true;
            $agentSelect.val(normalizedValues).trigger('change.select2');
            isAdjustingSelection = false;
        }

        function ensureDefaultAllAgents() {
            var selectedValues = $agentSelect.val() || [];
            if (selectedValues.length) return;

            isAdjustingSelection = true;
            $agentSelect.val([allAgentsValue]).trigger('change.select2');
            isAdjustingSelection = false;
        }

        $agentSelect.on('change', function() {
            enforceAllAgentsExclusivity();
        });

        ensureDefaultAllAgents();
        enforceAllAgentsExclusivity();
    }

    function initTransferenciasModal() {
        var $modal = $('#modalTransferenciasLlamada');
        var $apiInput = $('#interaction_transfers_api_url');
        if (!$modal.length || !$apiInput.length) {
            return;
        }
        var apiUrlTemplate = ($apiInput.val() || '').trim();
        if (!apiUrlTemplate) {
            return;
        }

        var $tbody = $('#transferencias-llamada-tbody');
        var $loading = $('#transferencias-llamada-loading');
        var $tableWrap = $('#transferencias-llamada-table-wrap');
        var $vacio = $('#transferencias-llamada-vacio');
        var $alert = $('#transferencias-llamada-alert');
        var metaEl = document.getElementById('transferencias-llamada-meta');

        function gettextMsg(key, fallback) {
            return (typeof gettext !== 'undefined' ? gettext(key) : fallback);
        }

        function resetModalBody() {
            $tbody.empty();
            $loading.removeClass('d-none');
            $tableWrap.addClass('d-none');
            $vacio.addClass('d-none');
            $alert.addClass('d-none').text('');
            if (metaEl) {
                metaEl.textContent = '';
            }
        }

        function showError(msg) {
            $loading.addClass('d-none');
            $tableWrap.addClass('d-none');
            $vacio.addClass('d-none');
            $alert.text(msg).removeClass('d-none');
        }

        $(document).on('click', '.reporte-cc-transferencias-trigger', function(e) {
            e.preventDefault();
            var callId = ($(this).attr('data-call-id') || '').trim();
            var recUrl = ($(this).attr('data-recording-url') || '').trim();
            if (!callId) {
                return;
            }

            resetModalBody();

            if (metaEl) {
                metaEl.textContent = '';
                var strong = document.createElement('strong');
                strong.textContent = gettextMsg('ID llamada', 'ID llamada') + ': ';
                metaEl.appendChild(strong);
                metaEl.appendChild(document.createTextNode(callId));
                if (recUrl) {
                    metaEl.appendChild(document.createTextNode(' · '));
                    var a = document.createElement('a');
                    a.href = recUrl;
                    a.target = '_blank';
                    a.rel = 'noopener noreferrer';
                    a.textContent = gettextMsg('Grabación', 'Grabación');
                    metaEl.appendChild(a);
                }
            }

            var sep = apiUrlTemplate.indexOf('?') >= 0 ? '&' : '?';
            var url = apiUrlTemplate + sep + 'interaction_id=' + encodeURIComponent(callId);

            $modal.modal('show');

            fetch(url, {
                credentials: 'same-origin',
                headers: { Accept: 'application/json' },
            })
                .then(function(response) {
                    return response.text().then(function(text) {
                        var data = null;
                        if (text) {
                            try {
                                data = JSON.parse(text);
                            } catch (ignore) {
                                data = null;
                            }
                        }
                        if (!response.ok) {
                            var errText = (data && data.error) ? data.error : response.statusText;
                            throw new Error(errText || gettextMsg('Error al cargar transferencias.', 'Error al cargar transferencias.'));
                        }
                        return data || {};
                    });
                })
                .then(function(data) {
                    var transfers = data.transfers || [];
                    $loading.addClass('d-none');
                    if (!transfers.length) {
                        $vacio.removeClass('d-none');
                        return;
                    }
                    transfers.forEach(function(t) {
                        var tr = document.createElement('tr');
                        function cellLabel(labelKey, idKey) {
                            var v = t[labelKey];
                            if (v !== null && v !== undefined && v !== '') {
                                return v;
                            }
                            var idv = t[idKey];
                            if (idv !== null && idv !== undefined && idv !== '') {
                                return String(idv);
                            }
                            return '—';
                        }
                        var dur = t.segment_duration;
                        if (dur === null || dur === undefined || dur === '') {
                            dur = '—';
                        }
                        var cells = [
                            t.destination_type,
                            t.transfer_type,
                            t.status,
                            cellLabel('source_agent_label', 'source_agent_id'),
                            cellLabel('destination_agent_label', 'destination_agent_id'),
                            cellLabel('destination_campaign_label', 'destination_campaign_id'),
                            dur,
                        ];
                        cells.forEach(function(val) {
                            var td = document.createElement('td');
                            if (val !== null && val !== undefined && val !== '') {
                                td.textContent = String(val);
                            } else {
                                td.textContent = '—';
                            }
                            tr.appendChild(td);
                        });
                        $tbody[0].appendChild(tr);
                    });
                    $tableWrap.removeClass('d-none');
                })
                .catch(function(err) {
                    showError(err.message || gettextMsg('Error al cargar transferencias.', 'Error al cargar transferencias.'));
                });
        });

        $modal.on('hidden.bs.modal', function() {
            resetModalBody();
        });
    }

    $(function() {
        var $form = $('form[method="post"]');
        if ($form.length) {
            initCampanasSelect();
            initAgentesSelect();
            initGruposSelect();
            initDateRangePicker();
        }
        initTransferenciasModal();

        // Export CSV Canalidades por campaña (WebSocket + API, mismo patrón que reporte_grafico contactados)
        var $taskIdInput = $('#csv_canalidades_task_id');
        if ($taskIdInput.length) {
            $taskIdInput.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $taskIdInputEgresos = $('#csv_canalidades_egresos_task_id');
        if ($taskIdInputEgresos.length) {
            $taskIdInputEgresos.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $taskIdCanalidadesPorHora = $('#csv_canalidades_por_hora_task_id');
        if ($taskIdCanalidadesPorHora.length) {
            $taskIdCanalidadesPorHora.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $taskIdCanalidadesPorHoraEgresos = $('#csv_canalidades_por_hora_egresos_task_id');
        if ($taskIdCanalidadesPorHoraEgresos.length) {
            $taskIdCanalidadesPorHoraEgresos.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $taskIdCanalidadesPorDia = $('#csv_canalidades_por_dia_task_id');
        if ($taskIdCanalidadesPorDia.length) {
            $taskIdCanalidadesPorDia.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $taskIdCanalidadesPorMes = $('#csv_canalidades_por_mes_task_id');
        if ($taskIdCanalidadesPorMes.length) {
            $taskIdCanalidadesPorMes.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $taskIdCanalidadesPorMesEgresos = $('#csv_canalidades_por_mes_egresos_task_id');
        if ($taskIdCanalidadesPorMesEgresos.length) {
            $taskIdCanalidadesPorMesEgresos.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $taskIdWaCampanaEgresos = $('#csv_whatsapp_mensajes_por_campana_egresos_task_id');
        if ($taskIdWaCampanaEgresos.length) {
            $taskIdWaCampanaEgresos.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $taskIdWaDiaEgresos = $('#csv_whatsapp_mensajes_por_dia_egresos_task_id');
        if ($taskIdWaDiaEgresos.length) {
            $taskIdWaDiaEgresos.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }

        var subscribeConfirmationMessage = 'Subscribed!';
        var $csvCanalidadesDescarga = $('#csvCanalidadesDescarga');
        var $csvCanalidadesDescargaLink = $('#csvCanalidadesDescargaLink');
        var $barraCSVCanalidades = $('#barraProgresoCSVCanalidades');

        function getFechaDesdeHasta() {
            var val = $('#id_fecha').val() || '';
            var parts = val.split(/\s*-\s*/);
            if (parts.length >= 2) {
                var start = moment(parts[0].trim(), 'DD/MM/YYYY', true);
                var end = moment(parts[1].trim(), 'DD/MM/YYYY', true);
                if (start.isValid() && end.isValid()) {
                    return { desde: start.format('DD/MM/YYYY'), hasta: end.format('DD/MM/YYYY') };
                }
            }
            var now = moment();
            return { desde: now.format('DD/MM/YYYY'), hasta: now.format('DD/MM/YYYY') };
        }

        function generarReporteCSV(taskId, urlExportacion) {
            var fechas = getFechaDesdeHasta();
            var postData = {
                task_id: taskId,
                desde: fechas.desde,
                hasta: fechas.hasta,
                campana: $('#id_campana').val() || [],
                grupo_agente: $('#id_grupo_agente').val() || [],
                agente: $('#id_agente').val() || [],
                campana_id: ($('#id_campana_id').val() || '').trim(),
                contacto_id: ($('#id_contacto_id').val() || '').trim(),
                address: ($('#id_address').val() || '').trim(),
                callid: ($('#id_callid').val() || '').trim(),
                incluir_finalizadas: $('#id_incluir_finalizadas').is(':checked'),
                hora_desde: ($('#id_hora_desde').val() || '').trim(),
                hora_hasta: ($('#id_hora_hasta').val() || '').trim(),
                duracion_agente_min: ($('#id_duracion_agente_min').val() || '').trim(),
                duracion_bot_min: ($('#id_duracion_bot_min').val() || '').trim(),
            };
            var csrfToken = typeof getCookie !== 'undefined' ? getCookie('csrftoken') : '';
            $.ajax({
                type: 'POST',
                url: urlExportacion,
                dataType: 'json',
                contentType: 'application/json',
                data: JSON.stringify(postData),
                headers: { 'X-CSRFToken': csrfToken },
                success: function() {},
                error: function(jqXHR, textStatus, errorThrown) {
                    console.error('Error export CSV canalidades:', textStatus, errorThrown);
                }
            });
        }

        $csvCanalidadesDescarga.on('click', function() {
            var $taskIdEl = $('#csv_canalidades_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_canalidades_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_canalidades_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV canalidades: URL de exportación no configurada (csv_canalidades_api_export_url vacío).');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV canalidades: no se pudo generar task_id (elemento csv_canalidades_task_id no encontrado).');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvCanalidadesDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvCanalidadesDescarga.prop('disabled', true);
            $barraCSVCanalidades.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/consumers/reporte_grafico_campana/canalidades_cc/cc/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVCanalidades.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvCanalidadesDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvCanalidadesDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Canalidades por campaña (Egresos)
        var $csvCanalidadesEgresosDescarga = $('#csvCanalidadesEgresosDescarga');
        var $csvCanalidadesEgresosDescargaLink = $('#csvCanalidadesEgresosDescargaLink');
        var $barraCSVCanalidadesEgresos = $('#barraProgresoCSVCanalidadesEgresos');
        $csvCanalidadesEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_canalidades_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_canalidades_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_canalidades_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV canalidades egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV canalidades egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvCanalidadesEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvCanalidadesEgresosDescarga.prop('disabled', true);
            $barraCSVCanalidadesEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_canalidades_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVCanalidadesEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvCanalidadesEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvCanalidadesEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Canalidades por hora (Ingresos)
        var $csvCanalidadesPorHoraDescarga = $('#csvCanalidadesPorHoraDescarga');
        var $csvCanalidadesPorHoraDescargaLink = $('#csvCanalidadesPorHoraDescargaLink');
        var $barraCSVCanalidadesPorHora = $('#barraProgresoCSVCanalidadesPorHora');
        $csvCanalidadesPorHoraDescarga.on('click', function() {
            var $taskIdEl = $('#csv_canalidades_por_hora_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_canalidades_por_hora_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_canalidades_por_hora_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV canalidades por hora: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV canalidades por hora: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvCanalidadesPorHoraDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvCanalidadesPorHoraDescarga.prop('disabled', true);
            $barraCSVCanalidadesPorHora.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_canalidades_por_hora/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVCanalidadesPorHora.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvCanalidadesPorHoraDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvCanalidadesPorHoraDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Canalidades por día (Ingresos)
        var $csvCanalidadesPorDiaDescarga = $('#csvCanalidadesPorDiaDescarga');
        var $csvCanalidadesPorDiaDescargaLink = $('#csvCanalidadesPorDiaDescargaLink');
        var $barraCSVCanalidadesPorDia = $('#barraProgresoCSVCanalidadesPorDia');
        $csvCanalidadesPorDiaDescarga.on('click', function() {
            var $taskIdEl = $('#csv_canalidades_por_dia_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_canalidades_por_dia_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_canalidades_por_dia_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV canalidades por día: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV canalidades por día: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvCanalidadesPorDiaDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvCanalidadesPorDiaDescarga.prop('disabled', true);
            $barraCSVCanalidadesPorDia.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_canalidades_por_dia/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVCanalidadesPorDia.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvCanalidadesPorDiaDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvCanalidadesPorDiaDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Canalidades por día (Egresos)
        var $csvCanalidadesPorDiaEgresosDescarga = $('#csvCanalidadesPorDiaEgresosDescarga');
        var $csvCanalidadesPorDiaEgresosDescargaLink = $('#csvCanalidadesPorDiaEgresosDescargaLink');
        var $barraCSVCanalidadesPorDiaEgresos = $('#barraProgresoCSVCanalidadesPorDiaEgresos');
        $csvCanalidadesPorDiaEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_canalidades_por_dia_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_canalidades_por_dia_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_canalidades_por_dia_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV canalidades por día egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV canalidades por día egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvCanalidadesPorDiaEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvCanalidadesPorDiaEgresosDescarga.prop('disabled', true);
            $barraCSVCanalidadesPorDiaEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_canalidades_por_dia_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVCanalidadesPorDiaEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvCanalidadesPorDiaEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvCanalidadesPorDiaEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Canalidades por mes (Ingresos)
        var $csvCanalidadesPorMesDescarga = $('#csvCanalidadesPorMesDescarga');
        var $csvCanalidadesPorMesDescargaLink = $('#csvCanalidadesPorMesDescargaLink');
        var $barraCSVCanalidadesPorMes = $('#barraProgresoCSVCanalidadesPorMes');
        $csvCanalidadesPorMesDescarga.on('click', function() {
            var $taskIdEl = $('#csv_canalidades_por_mes_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_canalidades_por_mes_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_canalidades_por_mes_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV canalidades por mes: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV canalidades por mes: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvCanalidadesPorMesDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvCanalidadesPorMesDescarga.prop('disabled', true);
            $barraCSVCanalidadesPorMes.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_canalidades_por_mes/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVCanalidadesPorMes.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvCanalidadesPorMesDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvCanalidadesPorMesDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Canalidades por hora (Egresos)
        var $csvCanalidadesPorHoraEgresosDescarga = $('#csvCanalidadesPorHoraEgresosDescarga');
        var $csvCanalidadesPorHoraEgresosDescargaLink = $('#csvCanalidadesPorHoraEgresosDescargaLink');
        var $barraCSVCanalidadesPorHoraEgresos = $('#barraProgresoCSVCanalidadesPorHoraEgresos');
        $csvCanalidadesPorHoraEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_canalidades_por_hora_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_canalidades_por_hora_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_canalidades_por_hora_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV canalidades por hora egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV canalidades por hora egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvCanalidadesPorHoraEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvCanalidadesPorHoraEgresosDescarga.prop('disabled', true);
            $barraCSVCanalidadesPorHoraEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_canalidades_por_hora_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVCanalidadesPorHoraEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvCanalidadesPorHoraEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvCanalidadesPorHoraEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Canalidades por mes (Egresos)
        var $csvCanalidadesPorMesEgresosDescarga = $('#csvCanalidadesPorMesEgresosDescarga');
        var $csvCanalidadesPorMesEgresosDescargaLink = $('#csvCanalidadesPorMesEgresosDescargaLink');
        var $barraCSVCanalidadesPorMesEgresos = $('#barraProgresoCSVCanalidadesPorMesEgresos');
        $csvCanalidadesPorMesEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_canalidades_por_mes_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_canalidades_por_mes_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_canalidades_por_mes_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV canalidades por mes egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV canalidades por mes egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvCanalidadesPorMesEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvCanalidadesPorMesEgresosDescarga.prop('disabled', true);
            $barraCSVCanalidadesPorMesEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_canalidades_por_mes_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVCanalidadesPorMesEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvCanalidadesPorMesEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvCanalidadesPorMesEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Resumen Operativo > Canalidades: Market Share Omnicanal (Donut)
        var omnichannelShareChartInstance = null;
        var omnichannelSharePendingData = null;
        function loadOmnichannelShare() {
            if (typeof console !== 'undefined' && console.log) {
                console.log('[OmnichannelShare] loadOmnichannelShare() ejecutado');
            }
            var $apiUrlEl = $('#api_omnichannel_share_url');
            var apiUrl = $apiUrlEl.length ? ($apiUrlEl.val() || '').trim() : '';
            if (!apiUrl) {
                $('#omnichannelShareLoading').text(typeof gettext !== 'undefined' ? gettext('URL del informe no configurada. Recargue la página.') : 'URL del informe no configurada. Recargue la página.');
                return;
            }

            var fechas = getFechaDesdeHasta();
            var startM = moment(fechas.desde, 'DD/MM/YYYY', true);
            var endM = moment(fechas.hasta, 'DD/MM/YYYY', true);
            if (!startM.isValid()) { startM = moment(); }
            if (!endM.isValid()) { endM = moment(); }

            var params = 'start_date=' + encodeURIComponent(startM.format('YYYY-MM-DD')) + '&end_date=' + encodeURIComponent(endM.format('YYYY-MM-DD'));
            var urlWithParams = apiUrl + (apiUrl.indexOf('?') !== -1 ? '&' : '?') + params;

            $('#omnichannelShareLoading').text(typeof gettext !== 'undefined' ? gettext('Cargando...') : 'Cargando...');

            $.ajax({
                url: urlWithParams,
                type: 'GET',
                dataType: 'json',
                success: function(data) {
                    $('#omnichannelShareTotalVolume').text(data.total_volume != null ? data.total_volume : '0');
                    if (data.shares) {
                        $('#share-voz').text(data.shares.voz || '0.0%');
                        $('#share-whatsapp').text(data.shares.whatsapp || '0.0%');
                        $('#share-facebook').text(data.shares.facebook || '0.0%');
                        $('#share-email').text(data.shares.email || '0.0%');
                    }
                    $('#omnichannelShareLoading').text('');

                    omnichannelSharePendingData = data;
                    // Dibujar cuando el panel sea visible (pestaña Canalidades activa)
                    if ($('#tab-resumen-canalidades').hasClass('show') && $('#tab-resumen-canalidades').hasClass('active')) {
                        drawOmnichannelShareChart();
                    }
                },
                error: function(xhr) {
                    var msg = typeof gettext !== 'undefined' ? gettext('Error al cargar datos. Compruebe el rango de fechas.') : 'Error al cargar datos. Compruebe el rango de fechas.';
                    if (xhr && xhr.status === 403) {
                        msg = typeof gettext !== 'undefined' ? gettext('Sin permiso para cargar este informe.') : 'Sin permiso para cargar este informe.';
                    } else if (xhr && xhr.status === 404) {
                        msg = typeof gettext !== 'undefined' ? gettext('Recurso no encontrado. Recargue la página.') : 'Recurso no encontrado. Recargue la página.';
                    }
                    $('#omnichannelShareLoading').text(msg);
                    $('#omnichannelShareTotalVolume').text('—');
                    $('#share-voz, #share-whatsapp, #share-facebook, #share-email').text('—');
                    omnichannelSharePendingData = null;
                }
            });
        }
        function drawOmnichannelShareChart() {
            var data = omnichannelSharePendingData;
            if (!data || !data.chart_data || !data.chart_data.datasets || !data.chart_data.datasets.length) return;
            var canvas = document.getElementById('chartOmnichannelShare');
            if (!canvas || typeof Chart === 'undefined') return;
            if (omnichannelShareChartInstance) {
                omnichannelShareChartInstance.destroy();
                omnichannelShareChartInstance = null;
            }
            omnichannelShareChartInstance = new Chart(canvas.getContext('2d'), {
                type: 'doughnut',
                data: data.chart_data,
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: { position: 'bottom' }
                    },
                    cutout: '55%'
                }
            });
        }
        // Disparar carga cuando la pestaña Canalidades se muestra (Bootstrap)
        $(document).on('shown.bs.tab', 'a[href="#tab-resumen-canalidades"]', function() {
            loadOmnichannelShare();
            if (omnichannelSharePendingData) {
                drawOmnichannelShareChart();
                if (omnichannelShareChartInstance && typeof omnichannelShareChartInstance.resize === 'function') {
                    omnichannelShareChartInstance.resize();
                }
            }
        });
        // Fallback: si shown.bs.tab no se dispara, cargar al hacer clic en el enlace (tras mostrar la pestaña)
        $(document).on('click', 'a[href="#tab-resumen-canalidades"]', function() {
            setTimeout(function() { loadOmnichannelShare(); }, 300);
        });
        // Al cargar la página: si Canalidades ya está visible (p. ej. recarga con esa pestaña), cargar datos
        if ($('#tab-resumen-canalidades').hasClass('show') && $('#tab-resumen-canalidades').hasClass('active')) {
            loadOmnichannelShare();
        } else {
            // Por si Bootstrap activa la pestaña tras el ready (p. ej. por hash), intentar carga un poco después
            setTimeout(function() {
                if ($('#tab-resumen-canalidades').hasClass('show') && $('#tab-resumen-canalidades').hasClass('active')) {
                    loadOmnichannelShare();
                }
            }, 400);
        }

        // Export CSV Mensajes por campaña (WhatsApp Egresos)
        var $csvWaCampanaEgresosDescarga = $('#csvWhatsappMensajesPorCampanaEgresosDescarga');
        var $csvWaCampanaEgresosDescargaLink = $('#csvWhatsappMensajesPorCampanaEgresosDescargaLink');
        var $barraCSVWaCampanaEgresos = $('#barraProgresoCSVWhatsappMensajesPorCampanaEgresos');
        $csvWaCampanaEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_whatsapp_mensajes_por_campana_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_whatsapp_mensajes_por_campana_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_whatsapp_mensajes_por_campana_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV whatsapp mensajes por campaña egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV whatsapp mensajes por campaña egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvWaCampanaEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvWaCampanaEgresosDescarga.prop('disabled', true);
            $barraCSVWaCampanaEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_whatsapp_mensajes_por_campana_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVWaCampanaEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvWaCampanaEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvWaCampanaEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Mensajes por mes (WhatsApp Egresos)
        var $csvWaMesEgresosDescarga = $('#csvWhatsappMensajesPorMesEgresosDescarga');
        var $csvWaMesEgresosDescargaLink = $('#csvWhatsappMensajesPorMesEgresosDescargaLink');
        var $barraCSVWaMesEgresos = $('#barraProgresoCSVWhatsappMensajesPorMesEgresos');
        $csvWaMesEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_whatsapp_mensajes_por_mes_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_whatsapp_mensajes_por_mes_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_whatsapp_mensajes_por_mes_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV whatsapp mensajes por mes egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV whatsapp mensajes por mes egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvWaMesEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvWaMesEgresosDescarga.prop('disabled', true);
            $barraCSVWaMesEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_whatsapp_mensajes_por_mes_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVWaMesEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvWaMesEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvWaMesEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Llamadas de voz por campaña (Ingresos/Voz/Campañas)
        var $taskIdLlamadasVoz = $('#csv_llamadas_voz_task_id');
        if ($taskIdLlamadasVoz.length) {
            $taskIdLlamadasVoz.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $taskIdLlamadasVozEgresos = $('#csv_llamadas_voz_egresos_task_id');
        if ($taskIdLlamadasVozEgresos.length) {
            $taskIdLlamadasVozEgresos.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvLlamadasVozDescarga = $('#csvLlamadasVozDescarga');
        var $csvLlamadasVozDescargaLink = $('#csvLlamadasVozDescargaLink');
        var $barraCSVLlamadasVoz = $('#barraProgresoCSVLlamadasVoz');
        $csvLlamadasVozDescarga.on('click', function() {
            var $taskIdEl = $('#csv_llamadas_voz_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_llamadas_voz_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_llamadas_voz_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV llamadas voz: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV llamadas voz: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvLlamadasVozDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvLlamadasVozDescarga.prop('disabled', true);
            $barraCSVLlamadasVoz.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_llamadas_voz/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVLlamadasVoz.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvLlamadasVozDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvLlamadasVozDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Llamadas de voz por campaña (Egresos/Voz/Campañas)
        var $csvLlamadasVozEgresosDescarga = $('#csvLlamadasVozEgresosDescarga');
        var $csvLlamadasVozEgresosDescargaLink = $('#csvLlamadasVozEgresosDescargaLink');
        var $barraCSVLlamadasVozEgresos = $('#barraProgresoCSVLlamadasVozEgresos');
        $csvLlamadasVozEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_llamadas_voz_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_llamadas_voz_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_llamadas_voz_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV llamadas voz egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV llamadas voz egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvLlamadasVozEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvLlamadasVozEgresosDescarga.prop('disabled', true);
            $barraCSVLlamadasVozEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_llamadas_voz_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVLlamadasVozEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvLlamadasVozEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvLlamadasVozEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Listado de llamadas atendidas (Ingresos/Voz)
        var $taskIdLlamadasAtendidas = $('#csv_llamadas_atendidas_task_id');
        if ($taskIdLlamadasAtendidas.length) {
            $taskIdLlamadasAtendidas.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvLlamadasAtendidasDescarga = $('#csvLlamadasAtendidasDescarga');
        var $csvLlamadasAtendidasDescargaLink = $('#csvLlamadasAtendidasDescargaLink');
        var $barraCSVLlamadasAtendidas = $('#barraProgresoCSVLlamadasAtendidas');
        $csvLlamadasAtendidasDescarga.on('click', function() {
            var $taskIdEl = $('#csv_llamadas_atendidas_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_llamadas_atendidas_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_llamadas_atendidas_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV llamadas atendidas: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV llamadas atendidas: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvLlamadasAtendidasDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvLlamadasAtendidasDescarga.prop('disabled', true);
            $barraCSVLlamadasAtendidas.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_llamadas_atendidas_csv/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVLlamadasAtendidas.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvLlamadasAtendidasDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvLlamadasAtendidasDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Listado de llamadas atendidas (Egresos/Voz)
        var $taskIdLlamadasAtendidasEgresos = $('#csv_llamadas_atendidas_egresos_task_id');
        if ($taskIdLlamadasAtendidasEgresos.length) {
            $taskIdLlamadasAtendidasEgresos.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvLlamadasAtendidasEgresosDescarga = $('#csvLlamadasAtendidasEgresosDescarga');
        var $csvLlamadasAtendidasEgresosDescargaLink = $('#csvLlamadasAtendidasEgresosDescargaLink');
        var $barraCSVLlamadasAtendidasEgresos = $('#barraProgresoCSVLlamadasAtendidasEgresos');
        $csvLlamadasAtendidasEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_llamadas_atendidas_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_llamadas_atendidas_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_llamadas_atendidas_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV llamadas atendidas egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV llamadas atendidas egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvLlamadasAtendidasEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvLlamadasAtendidasEgresosDescarga.prop('disabled', true);
            $barraCSVLlamadasAtendidasEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_llamadas_atendidas_egresos_csv/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVLlamadasAtendidasEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvLlamadasAtendidasEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvLlamadasAtendidasEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Listado de llamadas no atendidas (Ingresos/Voz)
        var $taskIdLlamadasNoAtendidas = $('#csv_llamadas_no_atendidas_task_id');
        if ($taskIdLlamadasNoAtendidas.length) {
            $taskIdLlamadasNoAtendidas.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvLlamadasNoAtendidasDescarga = $('#csvLlamadasNoAtendidasDescarga');
        var $csvLlamadasNoAtendidasDescargaLink = $('#csvLlamadasNoAtendidasDescargaLink');
        var $barraCSVLlamadasNoAtendidas = $('#barraProgresoCSVLlamadasNoAtendidas');
        $csvLlamadasNoAtendidasDescarga.on('click', function() {
            var $taskIdEl = $('#csv_llamadas_no_atendidas_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_llamadas_no_atendidas_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_llamadas_no_atendidas_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV llamadas no atendidas: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV llamadas no atendidas: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvLlamadasNoAtendidasDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvLlamadasNoAtendidasDescarga.prop('disabled', true);
            $barraCSVLlamadasNoAtendidas.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_llamadas_no_atendidas_csv/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVLlamadasNoAtendidas.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvLlamadasNoAtendidasDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvLlamadasNoAtendidasDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Listado de llamadas no atendidas (Egresos/Voz)
        var $taskIdLlamadasNoAtendidasEgresos = $('#csv_llamadas_no_atendidas_egresos_task_id');
        if ($taskIdLlamadasNoAtendidasEgresos.length) {
            $taskIdLlamadasNoAtendidasEgresos.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvLlamadasNoAtendidasEgresosDescarga = $('#csvLlamadasNoAtendidasEgresosDescarga');
        var $csvLlamadasNoAtendidasEgresosDescargaLink = $('#csvLlamadasNoAtendidasEgresosDescargaLink');
        var $barraCSVLlamadasNoAtendidasEgresos = $('#barraProgresoCSVLlamadasNoAtendidasEgresos');
        $csvLlamadasNoAtendidasEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_llamadas_no_atendidas_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_llamadas_no_atendidas_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_llamadas_no_atendidas_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV llamadas no atendidas egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV llamadas no atendidas egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvLlamadasNoAtendidasEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvLlamadasNoAtendidasEgresosDescarga.prop('disabled', true);
            $barraCSVLlamadasNoAtendidasEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_llamadas_no_atendidas_egresos_csv/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVLlamadasNoAtendidasEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvLlamadasNoAtendidasEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvLlamadasNoAtendidasEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Llamadas por hora de día (Ingresos/Voz/Horas)
        var $taskIdLlamadasPorHora = $('#csv_llamadas_por_hora_task_id');
        if ($taskIdLlamadasPorHora.length) {
            $taskIdLlamadasPorHora.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvLlamadasPorHoraDescarga = $('#csvLlamadasPorHoraDescarga');
        var $csvLlamadasPorHoraDescargaLink = $('#csvLlamadasPorHoraDescargaLink');
        var $barraCSVLlamadasPorHora = $('#barraProgresoCSVLlamadasPorHora');
        $csvLlamadasPorHoraDescarga.on('click', function() {
            var $taskIdEl = $('#csv_llamadas_por_hora_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_llamadas_por_hora_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_llamadas_por_hora_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV llamadas por hora: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV llamadas por hora: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvLlamadasPorHoraDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvLlamadasPorHoraDescarga.prop('disabled', true);
            $barraCSVLlamadasPorHora.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_llamadas_por_hora/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVLlamadasPorHora.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvLlamadasPorHoraDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvLlamadasPorHoraDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Llamadas por hora de día (Egresos/Voz/Horas)
        var $taskIdLlamadasPorHoraEgresos = $('#csv_llamadas_por_hora_egresos_task_id');
        if ($taskIdLlamadasPorHoraEgresos.length) {
            $taskIdLlamadasPorHoraEgresos.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvLlamadasPorHoraEgresosDescarga = $('#csvLlamadasPorHoraEgresosDescarga');
        var $csvLlamadasPorHoraEgresosDescargaLink = $('#csvLlamadasPorHoraEgresosDescargaLink');
        var $barraCSVLlamadasPorHoraEgresos = $('#barraProgresoCSVLlamadasPorHoraEgresos');
        $csvLlamadasPorHoraEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_llamadas_por_hora_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_llamadas_por_hora_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_llamadas_por_hora_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV llamadas por hora egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV llamadas por hora egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvLlamadasPorHoraEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvLlamadasPorHoraEgresosDescarga.prop('disabled', true);
            $barraCSVLlamadasPorHoraEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_llamadas_por_hora_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVLlamadasPorHoraEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvLlamadasPorHoraEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvLlamadasPorHoraEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Llamadas por día (Ingresos/Voz/Días)
        var $taskIdLlamadasPorDia = $('#csv_llamadas_por_dia_task_id');
        if ($taskIdLlamadasPorDia.length) {
            $taskIdLlamadasPorDia.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvLlamadasPorDiaDescarga = $('#csvLlamadasPorDiaDescarga');
        var $csvLlamadasPorDiaDescargaLink = $('#csvLlamadasPorDiaDescargaLink');
        var $barraCSVLlamadasPorDia = $('#barraProgresoCSVLlamadasPorDia');
        $csvLlamadasPorDiaDescarga.on('click', function() {
            var $taskIdEl = $('#csv_llamadas_por_dia_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_llamadas_por_dia_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_llamadas_por_dia_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV llamadas por día: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV llamadas por día: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvLlamadasPorDiaDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvLlamadasPorDiaDescarga.prop('disabled', true);
            $barraCSVLlamadasPorDia.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_llamadas_por_dia/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVLlamadasPorDia.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvLlamadasPorDiaDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvLlamadasPorDiaDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Llamadas por día (Egresos/Voz/Días)
        var $taskIdLlamadasPorDiaEgresos = $('#csv_llamadas_por_dia_egresos_task_id');
        if ($taskIdLlamadasPorDiaEgresos.length) {
            $taskIdLlamadasPorDiaEgresos.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvLlamadasPorDiaEgresosDescarga = $('#csvLlamadasPorDiaEgresosDescarga');
        var $csvLlamadasPorDiaEgresosDescargaLink = $('#csvLlamadasPorDiaEgresosDescargaLink');
        var $barraCSVLlamadasPorDiaEgresos = $('#barraProgresoCSVLlamadasPorDiaEgresos');
        $csvLlamadasPorDiaEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_llamadas_por_dia_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_llamadas_por_dia_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_llamadas_por_dia_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV llamadas por día egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV llamadas por día egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvLlamadasPorDiaEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvLlamadasPorDiaEgresosDescarga.prop('disabled', true);
            $barraCSVLlamadasPorDiaEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_llamadas_por_dia_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVLlamadasPorDiaEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvLlamadasPorDiaEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvLlamadasPorDiaEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Llamadas por mes (Ingresos/Voz/Mes)
        var $taskIdLlamadasPorMes = $('#csv_llamadas_por_mes_task_id');
        if ($taskIdLlamadasPorMes.length) {
            $taskIdLlamadasPorMes.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvLlamadasPorMesDescarga = $('#csvLlamadasPorMesDescarga');
        var $csvLlamadasPorMesDescargaLink = $('#csvLlamadasPorMesDescargaLink');
        var $barraCSVLlamadasPorMes = $('#barraProgresoCSVLlamadasPorMes');
        $csvLlamadasPorMesDescarga.on('click', function() {
            var $taskIdEl = $('#csv_llamadas_por_mes_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_llamadas_por_mes_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_llamadas_por_mes_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV llamadas por mes: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV llamadas por mes: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvLlamadasPorMesDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvLlamadasPorMesDescarga.prop('disabled', true);
            $barraCSVLlamadasPorMes.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_llamadas_por_mes/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVLlamadasPorMes.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvLlamadasPorMesDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvLlamadasPorMesDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Llamadas por mes (Egresos/Voz/Mes)
        var $taskIdLlamadasPorMesEgresos = $('#csv_llamadas_por_mes_egresos_task_id');
        if ($taskIdLlamadasPorMesEgresos.length) {
            $taskIdLlamadasPorMesEgresos.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvLlamadasPorMesEgresosDescarga = $('#csvLlamadasPorMesEgresosDescarga');
        var $csvLlamadasPorMesEgresosDescargaLink = $('#csvLlamadasPorMesEgresosDescargaLink');
        var $barraCSVLlamadasPorMesEgresos = $('#barraProgresoCSVLlamadasPorMesEgresos');
        $csvLlamadasPorMesEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_llamadas_por_mes_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_llamadas_por_mes_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_llamadas_por_mes_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV llamadas por mes egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV llamadas por mes egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvLlamadasPorMesEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvLlamadasPorMesEgresosDescarga.prop('disabled', true);
            $barraCSVLlamadasPorMesEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_llamadas_por_mes_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVLlamadasPorMesEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvLlamadasPorMesEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvLlamadasPorMesEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Conversaciones Respondidas (Ingresos WhatsApp)
        var $taskIdConvResp = $('#csv_conversaciones_respondidas_task_id');
        if ($taskIdConvResp.length) {
            $taskIdConvResp.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $taskIdConvRespEgresos = $('#csv_conversaciones_respondidas_egresos_task_id');
        if ($taskIdConvRespEgresos.length) {
            $taskIdConvRespEgresos.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvConvRespDescarga = $('#csvConversacionesRespondidasDescarga');
        var $csvConvRespDescargaLink = $('#csvConversacionesRespondidasDescargaLink');
        var $barraCSVConvResp = $('#barraProgresoCSVConversacionesRespondidas');
        $csvConvRespDescarga.on('click', function() {
            var $taskIdEl = $('#csv_conversaciones_respondidas_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_conversaciones_respondidas_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_conversaciones_respondidas_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV conversaciones respondidas: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV conversaciones respondidas: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvConvRespDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvConvRespDescarga.prop('disabled', true);
            $barraCSVConvResp.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_conversaciones_respondidas/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVConvResp.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvConvRespDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvConvRespDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Conversaciones Respondidas (Egresos WhatsApp)
        var $csvConvRespEgresosDescarga = $('#csvConversacionesRespondidasEgresosDescarga');
        var $csvConvRespEgresosDescargaLink = $('#csvConversacionesRespondidasEgresosDescargaLink');
        var $barraCSVConvRespEgresos = $('#barraProgresoCSVConversacionesRespondidasEgresos');
        $csvConvRespEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_conversaciones_respondidas_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_conversaciones_respondidas_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_conversaciones_respondidas_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV conversaciones respondidas egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV conversaciones respondidas egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvConvRespEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvConvRespEgresosDescarga.prop('disabled', true);
            $barraCSVConvRespEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_conversaciones_respondidas_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVConvRespEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvConvRespEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvConvRespEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Conversaciones no respondidas (Ingresos WhatsApp)
        var $taskIdConvNoResp = $('#csv_conversaciones_no_respondidas_task_id');
        if ($taskIdConvNoResp.length) {
            $taskIdConvNoResp.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvConvNoRespDescarga = $('#csvConversacionesNoRespondidasDescarga');
        var $csvConvNoRespDescargaLink = $('#csvConversacionesNoRespondidasDescargaLink');
        var $barraCSVConvNoResp = $('#barraProgresoCSVConversacionesNoRespondidas');
        $csvConvNoRespDescarga.on('click', function() {
            var $taskIdEl = $('#csv_conversaciones_no_respondidas_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_conversaciones_no_respondidas_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_conversaciones_no_respondidas_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV conversaciones no respondidas: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV conversaciones no respondidas: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvConvNoRespDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvConvNoRespDescarga.prop('disabled', true);
            $barraCSVConvNoResp.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_conversaciones_no_respondidas/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVConvNoResp.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvConvNoRespDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvConvNoRespDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Conversaciones no respondidas (Egresos WhatsApp)
        var $csvConvNoRespEgresosDescarga = $('#csvConversacionesNoRespondidasEgresosDescarga');
        var $csvConvNoRespEgresosDescargaLink = $('#csvConversacionesNoRespondidasEgresosDescargaLink');
        var $barraCSVConvNoRespEgresos = $('#barraProgresoCSVConversacionesNoRespondidasEgresos');
        $csvConvNoRespEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_conversaciones_no_respondidas_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_conversaciones_no_respondidas_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_conversaciones_no_respondidas_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV conversaciones no respondidas egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV conversaciones no respondidas egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvConvNoRespEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvConvNoRespEgresosDescarga.prop('disabled', true);
            $barraCSVConvNoRespEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_conversaciones_no_respondidas_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVConvNoRespEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvConvNoRespEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvConvNoRespEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Mensajes por hora de día (WhatsApp Ingresos)
        var $taskIdWaMsg = $('#csv_whatsapp_mensajes_por_hora_task_id');
        if ($taskIdWaMsg.length) {
            $taskIdWaMsg.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvWaMsgDescarga = $('#csvWhatsappMensajesPorHoraDescarga');
        var $csvWaMsgDescargaLink = $('#csvWhatsappMensajesPorHoraDescargaLink');
        var $barraCSVWaMsg = $('#barraProgresoCSVWhatsappMensajesPorHora');

        function generarReporteCSVWhatsappMensajesPorHora(taskId, urlExportacion) {
            var fechas = getFechaDesdeHasta();
            var postData = {
                task_id: taskId,
                desde: fechas.desde,
                hasta: fechas.hasta,
                campana: $('#id_campana').val() || [],
                grupo_agente: $('#id_grupo_agente').val() || [],
                agente: $('#id_agente').val() || [],
                campana_id: ($('#id_campana_id').val() || '').trim(),
                contacto_id: ($('#id_contacto_id').val() || '').trim(),
                address: ($('#id_address').val() || '').trim(),
                callid: ($('#id_callid').val() || '').trim(),
                incluir_finalizadas: $('#id_incluir_finalizadas').is(':checked'),
                hora_desde: ($('#id_hora_desde').val() || '').trim(),
                hora_hasta: ($('#id_hora_hasta').val() || '').trim(),
                duracion_agente_min: ($('#id_duracion_agente_min').val() || '').trim(),
                duracion_bot_min: ($('#id_duracion_bot_min').val() || '').trim(),
            };
            var csrfToken = typeof getCookie !== 'undefined' ? getCookie('csrftoken') : '';
            $.ajax({
                type: 'POST',
                url: urlExportacion,
                dataType: 'json',
                contentType: 'application/json',
                data: JSON.stringify(postData),
                headers: { 'X-CSRFToken': csrfToken },
                success: function() {},
                error: function(jqXHR, textStatus, errorThrown) {
                    console.error('Error export CSV whatsapp mensajes por hora:', textStatus, errorThrown);
                }
            });
        }

        $csvWaMsgDescarga.on('click', function() {
            var $taskIdEl = $('#csv_whatsapp_mensajes_por_hora_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_whatsapp_mensajes_por_hora_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_whatsapp_mensajes_por_hora_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV whatsapp mensajes por hora: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV whatsapp mensajes por hora: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvWaMsgDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvWaMsgDescarga.prop('disabled', true);
            $barraCSVWaMsg.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/consumers/reporte_grafico_campana/wa_mensajes_por_hora/cc/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSVWhatsappMensajesPorHora(taskId, urlExportacion);
                } else {
                    $barraCSVWaMsg.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvWaMsgDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvWaMsgDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Mensajes por hora (WhatsApp Egresos)
        var $taskIdWaMsgEgresos = $('#csv_whatsapp_mensajes_por_hora_egresos_task_id');
        if ($taskIdWaMsgEgresos.length) {
            $taskIdWaMsgEgresos.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvWaMsgEgresosDescarga = $('#csvWhatsappMensajesPorHoraEgresosDescarga');
        var $csvWaMsgEgresosDescargaLink = $('#csvWhatsappMensajesPorHoraEgresosDescargaLink');
        var $barraCSVWaMsgEgresos = $('#barraProgresoCSVWhatsappMensajesPorHoraEgresos');

        function generarReporteCSVWhatsappMensajesPorHoraEgresos(taskId, urlExportacion) {
            var fechas = getFechaDesdeHasta();
            var postData = {
                task_id: taskId,
                desde: fechas.desde,
                hasta: fechas.hasta,
                campana: $('#id_campana').val() || [],
                grupo_agente: $('#id_grupo_agente').val() || [],
                agente: $('#id_agente').val() || [],
                campana_id: ($('#id_campana_id').val() || '').trim(),
                contacto_id: ($('#id_contacto_id').val() || '').trim(),
                address: ($('#id_address').val() || '').trim(),
                callid: ($('#id_callid').val() || '').trim(),
                incluir_finalizadas: $('#id_incluir_finalizadas').is(':checked'),
                hora_desde: ($('#id_hora_desde').val() || '').trim(),
                hora_hasta: ($('#id_hora_hasta').val() || '').trim(),
                duracion_agente_min: ($('#id_duracion_agente_min').val() || '').trim(),
                duracion_bot_min: ($('#id_duracion_bot_min').val() || '').trim(),
            };
            var csrfToken = typeof getCookie !== 'undefined' ? getCookie('csrftoken') : '';
            $.ajax({
                type: 'POST',
                url: urlExportacion,
                dataType: 'json',
                contentType: 'application/json',
                data: JSON.stringify(postData),
                headers: { 'X-CSRFToken': csrfToken },
                success: function() {},
                error: function(jqXHR, textStatus, errorThrown) {
                    console.error('Error export CSV whatsapp mensajes por hora egresos:', textStatus, errorThrown);
                }
            });
        }

        $csvWaMsgEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_whatsapp_mensajes_por_hora_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_whatsapp_mensajes_por_hora_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_whatsapp_mensajes_por_hora_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV whatsapp mensajes por hora egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV whatsapp mensajes por hora egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvWaMsgEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvWaMsgEgresosDescarga.prop('disabled', true);
            $barraCSVWaMsgEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_whatsapp_mensajes_por_hora_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSVWhatsappMensajesPorHoraEgresos(taskId, urlExportacion);
                } else {
                    $barraCSVWaMsgEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvWaMsgEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvWaMsgEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Mensajes por campaña (WhatsApp Ingresos)
        var $taskIdWaCampana = $('#csv_whatsapp_mensajes_por_campana_task_id');
        if ($taskIdWaCampana.length) {
            $taskIdWaCampana.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvWaCampanaDescarga = $('#csvWhatsappMensajesPorCampanaDescarga');
        var $csvWaCampanaDescargaLink = $('#csvWhatsappMensajesPorCampanaDescargaLink');
        var $barraCSVWaCampana = $('#barraProgresoCSVWhatsappMensajesPorCampana');

        $csvWaCampanaDescarga.on('click', function() {
            var $taskIdEl = $('#csv_whatsapp_mensajes_por_campana_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_whatsapp_mensajes_por_campana_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_whatsapp_mensajes_por_campana_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV whatsapp mensajes por campaña: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV whatsapp mensajes por campaña: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvWaCampanaDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvWaCampanaDescarga.prop('disabled', true);
            $barraCSVWaCampana.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/consumers/reporte_grafico_campana/wa_mensajes_por_campana/cc/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSV(taskId, urlExportacion);
                } else {
                    $barraCSVWaCampana.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvWaCampanaDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvWaCampanaDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Mensajes por dia (WhatsApp Ingresos)
        var $taskIdWaDia = $('#csv_whatsapp_mensajes_por_dia_task_id');
        if ($taskIdWaDia.length) {
            $taskIdWaDia.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvWaDiaDescarga = $('#csvWhatsappMensajesPorDiaDescarga');
        var $csvWaDiaDescargaLink = $('#csvWhatsappMensajesPorDiaDescargaLink');
        var $barraCSVWaDia = $('#barraProgresoCSVWhatsappMensajesPorDia');

        function generarReporteCSVWhatsappMensajesPorDia(taskId, urlExportacion) {
            var fechas = getFechaDesdeHasta();
            var postData = {
                task_id: taskId,
                desde: fechas.desde,
                hasta: fechas.hasta,
                campana: $('#id_campana').val() || [],
                grupo_agente: $('#id_grupo_agente').val() || [],
                agente: $('#id_agente').val() || [],
                campana_id: ($('#id_campana_id').val() || '').trim(),
                contacto_id: ($('#id_contacto_id').val() || '').trim(),
                address: ($('#id_address').val() || '').trim(),
                callid: ($('#id_callid').val() || '').trim(),
                incluir_finalizadas: $('#id_incluir_finalizadas').is(':checked'),
                hora_desde: ($('#id_hora_desde').val() || '').trim(),
                hora_hasta: ($('#id_hora_hasta').val() || '').trim(),
                duracion_agente_min: ($('#id_duracion_agente_min').val() || '').trim(),
                duracion_bot_min: ($('#id_duracion_bot_min').val() || '').trim(),
            };
            var csrfToken = typeof getCookie !== 'undefined' ? getCookie('csrftoken') : '';
            $.ajax({
                type: 'POST',
                url: urlExportacion,
                dataType: 'json',
                contentType: 'application/json',
                data: JSON.stringify(postData),
                headers: { 'X-CSRFToken': csrfToken },
                success: function() {},
                error: function(jqXHR, textStatus, errorThrown) {
                    console.error('Error export CSV whatsapp mensajes por dia:', textStatus, errorThrown);
                }
            });
        }

        $csvWaDiaDescarga.on('click', function() {
            var $taskIdEl = $('#csv_whatsapp_mensajes_por_dia_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_whatsapp_mensajes_por_dia_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_whatsapp_mensajes_por_dia_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV whatsapp mensajes por dia: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV whatsapp mensajes por dia: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvWaDiaDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvWaDiaDescarga.prop('disabled', true);
            $barraCSVWaDia.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_whatsapp_mensajes_por_dia/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSVWhatsappMensajesPorDia(taskId, urlExportacion);
                } else {
                    $barraCSVWaDia.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvWaDiaDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvWaDiaDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Mensajes por dia (WhatsApp Egresos)
        var $csvWaDiaEgresosDescarga = $('#csvWhatsappMensajesPorDiaEgresosDescarga');
        var $csvWaDiaEgresosDescargaLink = $('#csvWhatsappMensajesPorDiaEgresosDescargaLink');
        var $barraCSVWaDiaEgresos = $('#barraProgresoCSVWhatsappMensajesPorDiaEgresos');
        $csvWaDiaEgresosDescarga.on('click', function() {
            var $taskIdEl = $('#csv_whatsapp_mensajes_por_dia_egresos_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_whatsapp_mensajes_por_dia_egresos_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_whatsapp_mensajes_por_dia_egresos_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV whatsapp mensajes por dia egresos: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV whatsapp mensajes por dia egresos: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvWaDiaEgresosDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvWaDiaEgresosDescarga.prop('disabled', true);
            $barraCSVWaDiaEgresos.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_whatsapp_mensajes_por_dia_egresos/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSVWhatsappMensajesPorDia(taskId, urlExportacion);
                } else {
                    $barraCSVWaDiaEgresos.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvWaDiaEgresosDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvWaDiaEgresosDescarga.remove();
                        rws.close();
                    }
                }
            });
        });

        // Export CSV Mensajes por mes (WhatsApp Ingresos)
        var $taskIdWaMes = $('#csv_whatsapp_mensajes_por_mes_task_id');
        if ($taskIdWaMes.length) {
            $taskIdWaMes.val(Date.now().toString(36) + Math.random().toString(36).substr(2, 9));
        }
        var $csvWaMesDescarga = $('#csvWhatsappMensajesPorMesDescarga');
        var $csvWaMesDescargaLink = $('#csvWhatsappMensajesPorMesDescargaLink');
        var $barraCSVWaMes = $('#barraProgresoCSVWhatsappMensajesPorMes');

        function generarReporteCSVWhatsappMensajesPorMes(taskId, urlExportacion) {
            var fechas = getFechaDesdeHasta();
            var postData = {
                task_id: taskId,
                desde: fechas.desde,
                hasta: fechas.hasta,
                campana: $('#id_campana').val() || [],
                grupo_agente: $('#id_grupo_agente').val() || [],
                agente: $('#id_agente').val() || [],
                campana_id: ($('#id_campana_id').val() || '').trim(),
                contacto_id: ($('#id_contacto_id').val() || '').trim(),
                address: ($('#id_address').val() || '').trim(),
                callid: ($('#id_callid').val() || '').trim(),
                incluir_finalizadas: $('#id_incluir_finalizadas').is(':checked'),
                hora_desde: ($('#id_hora_desde').val() || '').trim(),
                hora_hasta: ($('#id_hora_hasta').val() || '').trim(),
                duracion_agente_min: ($('#id_duracion_agente_min').val() || '').trim(),
                duracion_bot_min: ($('#id_duracion_bot_min').val() || '').trim(),
            };
            var csrfToken = typeof getCookie !== 'undefined' ? getCookie('csrftoken') : '';
            $.ajax({
                type: 'POST',
                url: urlExportacion,
                dataType: 'json',
                contentType: 'application/json',
                data: JSON.stringify(postData),
                headers: { 'X-CSRFToken': csrfToken },
                success: function() {},
                error: function(jqXHR, textStatus, errorThrown) {
                    console.error('Error export CSV whatsapp mensajes por mes:', textStatus, errorThrown);
                }
            });
        }

        $csvWaMesDescarga.on('click', function() {
            var $taskIdEl = $('#csv_whatsapp_mensajes_por_mes_task_id');
            var taskId = ($taskIdEl.val() || '').trim();
            if (!taskId && $taskIdEl.length) {
                taskId = Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
                $taskIdEl.val(taskId);
            }
            var urlExportacion = ($('#csv_whatsapp_mensajes_por_mes_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_whatsapp_mensajes_por_mes_download_url_prefix').val() || '').trim();
            if (!urlExportacion) {
                console.error('Export CSV whatsapp mensajes por mes: URL de exportación no configurada.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }
            if (!taskId) {
                console.error('Export CSV whatsapp mensajes por mes: no se pudo generar task_id.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvWaMesDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvWaMesDescarga.prop('disabled', true);
            $barraCSVWaMes.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/channels/reporte_centro_contacto_whatsapp_mensajes_por_mes/' + taskId;
            if (window.location.protocol === 'https:') {
                wsPath = 'wss://' + window.location.host + wsPath;
            } else {
                wsPath = 'ws://' + window.location.host + wsPath;
            }

            var rws = typeof ReconnectingWebSocket !== 'undefined'
                ? new ReconnectingWebSocket(wsPath, [], {
                    connectionTimeout: 8000,
                    maxReconnectionDelay: 3000,
                    minReconnectionDelay: 1000,
                })
                : new WebSocket(wsPath);

            rws.addEventListener('message', function(e) {
                var data = e.data;
                if (data === subscribeConfirmationMessage) {
                    generarReporteCSVWhatsappMensajesPorMes(taskId, urlExportacion);
                } else {
                    $barraCSVWaMes.find('.progress-bar').width(data + '%').text(data + '%');
                    if (data === '100') {
                        var downloadUrl = urlPrefix.replace('TASKID', taskId);
                        $csvWaMesDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                        $csvWaMesDescarga.remove();
                        rws.close();
                    }
                }
            });
        });
    });
})();
