/*
 * Copyright (C) 2018 Freetech Solutions
 * This file is part of OMniLeads
 * SPDX-License-Identifier: LGPL-3.0
 *
 * Reporte de Performance: mismo date picker que reporte/centro_de_contacto
 * (daterangepicker con presets Hoy, Últimos 7 días, etc.) y llamada a API con date_start y date_end.
 */

(function() {
    'use strict';

    var API_URL = null; // se inyecta desde el template
    var lastReportData = null; // última respuesta de la API
    var agenteGrupoMap = {}; // agent_id (string) -> grupo_id (number), desde #agente-grupo-map
    var AGENTE_REPORTE_GRAFICO_URL_TEMPLATE = null;
    var currentDateStart = null;
    var currentDateEnd = null;
    var currentPage = 1;
    var SUBSCRIBED_MESSAGE = 'Subscribed!';

    (function initAgenteGrupoMap() {
        var el = document.getElementById('agente-grupo-map');
        if (el && el.textContent) {
            try {
                agenteGrupoMap = JSON.parse(el.textContent) || {};
            } catch (e) {}
        }
    })();

    function getApiUrl() {
        if (API_URL) return API_URL;
        var el = document.getElementById('api_reportes_agents_activity_v2_url');
        if (el) {
            API_URL = el.getAttribute('data-url') || el.getAttribute('value') || '';
        } else {
            API_URL = '';
        }
        return API_URL;
    }

    function getAgenteReporteGraficoUrlTemplate() {
        if (AGENTE_REPORTE_GRAFICO_URL_TEMPLATE) return AGENTE_REPORTE_GRAFICO_URL_TEMPLATE;
        var el = document.getElementById('agente_reporte_grafico_url_template');
        if (el) {
            AGENTE_REPORTE_GRAFICO_URL_TEMPLATE = el.getAttribute('data-url-template') || '';
        } else {
            AGENTE_REPORTE_GRAFICO_URL_TEMPLATE = '';
        }
        return AGENTE_REPORTE_GRAFICO_URL_TEMPLATE;
    }

    function getAgenteReporteGraficoUrl(agentId) {
        if (agentId === null || agentId === undefined || agentId === '—') return '';
        var template = getAgenteReporteGraficoUrlTemplate();
        if (!template) return '';
        var url = template.replace('123456789', String(agentId));
        var query = [];
        if (currentDateStart) query.push('date_start=' + encodeURIComponent(currentDateStart));
        if (currentDateEnd) query.push('date_end=' + encodeURIComponent(currentDateEnd));
        if (!query.length) return url;
        return url + (url.indexOf('?') >= 0 ? '&' : '?') + query.join('&');
    }

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

    function setDefaultFechas() {
        var $fecha = $('#id_fecha');
        if (!$fecha.val() || !$fecha.val().trim()) {
            $fecha.val(formatRange(moment(), moment()));
        }
    }

    function getFechasFromUrl() {
        var params = new URLSearchParams(window.location.search);
        var desde = params.get('fecha_desde');
        var hasta = params.get('fecha_hasta');
        return { desde: desde, hasta: hasta };
    }

    function getSelectedAgentIds() {
        var $sel = $('#id_agente');
        if (!$sel.length) return null;
        var allValue = $sel.attr('data-all-agents-value') || '__all_agents__';
        var selected = $sel.val() || [];
        if (selected.length === 0 || selected.indexOf(allValue) !== -1) return null;
        return selected.map(function(id) { return parseInt(id, 10); }).filter(function(id) { return !isNaN(id); });
    }

    function getSelectedGroupIds() {
        var $sel = $('#id_grupo_agente');
        if (!$sel.length) return null;
        var allValue = $sel.attr('data-all-groups-value') || '__all_groups__';
        var selected = $sel.val() || [];
        if (selected.length === 0 || selected.indexOf(allValue) !== -1) return null;
        return selected.map(function(id) { return parseInt(id, 10); }).filter(function(id) { return !isNaN(id); });
    }

    function getPageSize() {
        var el = document.getElementById('reporte-performance-page-size');
        if (!el) return 10;
        var n = parseInt(el.value, 10);
        return (n >= 10 && n <= 50) ? n : 10;
    }

    function getSelectedAgenteGrupoForApi() {
        var agente = ($('#id_agente').val() || []).slice();
        var grupo = ($('#id_grupo_agente').val() || []).slice();
        return { agente: agente, grupo_agente: grupo };
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
            if (selectedValues.indexOf(allAgentsValue) === -1 || selectedValues.length <= 1) return;
            var normalizedValues = selectedValues[selectedValues.length - 1] === allAgentsValue
                ? [allAgentsValue]
                : selectedValues.filter(function(v) { return v !== allAgentsValue; });
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
            currentPage = 1;
            if (currentDateStart && currentDateEnd) fetchReport(currentDateStart, currentDateEnd, 1);
        });
        ensureDefaultAllAgents();
        enforceAllAgentsExclusivity();
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
            if (selectedValues.indexOf(allGroupsValue) === -1 || selectedValues.length <= 1) return;
            var normalizedValues = selectedValues[selectedValues.length - 1] === allGroupsValue
                ? [allGroupsValue]
                : selectedValues.filter(function(v) { return v !== allGroupsValue; });
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
            currentPage = 1;
            if (currentDateStart && currentDateEnd) fetchReport(currentDateStart, currentDateEnd, 1);
        });
        ensureDefaultAllGroups();
        enforceAllGroupsExclusivity();
    }

    function initTabsL1HashState() {
        var $tabs = $('#agentsActivityTabsL1 a.nav-link');
        var $tabsContent = $('#agentsActivityTabsL1Content');
        var defaultHash = '#tab-listado';
        if (!$tabs.length || !$tabsContent.length) return;

        function findTabLink(hash) {
            if (!hash || hash.charAt(0) !== '#') return $();
            return $tabs.filter('[href="' + hash + '"]').first();
        }

        function setHash(hash) {
            if (!hash || hash.charAt(0) !== '#') return;
            if (window.history && typeof window.history.replaceState === 'function') {
                var url = window.location.pathname + window.location.search + hash;
                window.history.replaceState({}, '', url);
            } else {
                window.location.hash = hash;
            }
        }

        function showTab($link) {
            if (!$link.length) return;
            if ($.fn.tab) {
                $link.tab('show');
                return;
            }
            var target = $link.attr('href');
            $tabs.removeClass('active').attr('aria-selected', 'false');
            $link.addClass('active').attr('aria-selected', 'true');
            $tabsContent.find('.tab-pane').removeClass('show active');
            if (target && target.charAt(0) === '#') {
                $(target).addClass('show active');
            }
        }

        var $initial = findTabLink(window.location.hash);
        if (!$initial.length) $initial = findTabLink(defaultHash);
        showTab($initial);
        if ($initial.length) setHash($initial.attr('href'));

        if ($.fn.tab) {
            $tabs.on('shown.bs.tab', function(e) {
                var href = $(e.target).attr('href');
                setHash(href);
            });
        } else {
            $tabs.on('click', function(e) {
                e.preventDefault();
                var $link = $(this);
                showTab($link);
                setHash($link.attr('href'));
            });
        }
    }

    function buildTaskId() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
    }

    function getFechaDesdeHastaForExport() {
        var parsed = parseExistingRange($('#id_fecha').val() || '');
        if (parsed) {
            return {
                desde: parsed.startDate.format('DD/MM/YYYY'),
                hasta: parsed.endDate.format('DD/MM/YYYY')
            };
        }
        var now = moment();
        return { desde: now.format('DD/MM/YYYY'), hasta: now.format('DD/MM/YYYY') };
    }

    function initListadoCSVExport() {
        var $taskIdInput = $('#csv_agents_activity_listado_task_id');
        var $csvDescarga = $('#csvAgentsActivityListadoDescarga');
        var $csvDescargaLink = $('#csvAgentsActivityListadoDescargaLink');
        var $barraCSV = $('#barraProgresoCSVAgentsActivityListado');
        if (!$taskIdInput.length || !$csvDescarga.length) return;

        if (!($taskIdInput.val() || '').trim()) {
            $taskIdInput.val(buildTaskId());
        }

        function generarReporteCSV(taskId, urlExportacion) {
            var fechas = getFechaDesdeHastaForExport();
            var postData = {
                task_id: taskId,
                desde: fechas.desde,
                hasta: fechas.hasta,
                agente: $('#id_agente').val() || [],
                grupo_agente: $('#id_grupo_agente').val() || [],
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
                    console.error('Error export CSV listado agentes:', textStatus, errorThrown);
                }
            });
        }

        $csvDescarga.on('click', function() {
            var taskId = ($taskIdInput.val() || '').trim();
            if (!taskId) {
                taskId = buildTaskId();
                $taskIdInput.val(taskId);
            }

            var urlExportacion = ($('#csv_agents_activity_listado_api_export_url').val() || '').trim();
            var urlPrefix = ($('#csv_agents_activity_listado_download_url_prefix').val() || '').trim();
            if (!urlExportacion || !taskId) {
                console.error('Export CSV listado agentes: configuración inválida.');
                if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'error', title: '', text: typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.' });
                } else {
                    alert(typeof gettext !== 'undefined' ? gettext('No se pudo iniciar la exportación. Recargue la página e intente de nuevo.') : 'No se pudo iniciar la exportación. Recargue la página e intente de nuevo.');
                }
                return;
            }

            $csvDescarga.val(typeof gettext !== 'undefined' ? gettext('Generando...') : 'Generando...');
            $csvDescarga.prop('disabled', true);
            $csvDescargaLink.addClass('hidden');
            $barraCSV.removeClass('hidden').find('.progress-bar').width('0%').text('0%');

            var wsPath = '/consumers/reporte_grafico_campana/agents_activity_listado/cc/' + taskId;
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
                var data = String(e.data);
                if (data === SUBSCRIBED_MESSAGE) {
                    generarReporteCSV(taskId, urlExportacion);
                    return;
                }

                $barraCSV.find('.progress-bar').width(data + '%').text(data + '%');
                if (data === '100') {
                    var downloadUrl = urlPrefix.replace('TASKID', taskId);
                    $csvDescargaLink.attr('href', downloadUrl).removeClass('hidden');
                    $csvDescarga.remove();
                    rws.close();
                }
            });
        });
    }

    function renderRows(data) {
        var tbody = document.getElementById('reporte-performance-tbody');
        var contador = document.getElementById('reporte-performance-contador');
        if (!tbody) return;

        var list = (data && data.data) ? data.data : [];
        var totalCount = (data && typeof data.total_count === 'number') ? data.total_count : list.length;
        var page = (data && typeof data.page === 'number') ? data.page : 1;
        var pageSize = (data && typeof data.page_size === 'number') ? data.page_size : list.length;

        function fmtNum(n) {
            if (n === null || n === undefined) return '—';
            return Number(n);
        }
        function fmtPct(n) {
            if (n === null || n === undefined) return '—';
            return Number(n).toFixed(1) + '%';
        }
        function fmtTransferKpi(n) {
            if (n === null || n === undefined) return '—';
            var num = Number(n);
            if (isNaN(num)) return '—';
            var rounded = Math.round(num * 10) / 10;
            if (Math.abs(rounded - Math.round(rounded)) < 1e-9) {
                return String(Math.round(rounded));
            }
            return rounded.toFixed(1).replace('.', ',');
        }
        function secondsToHHMMSS(sec) {
            if (sec === null || sec === undefined) return '—';
            var n = Number(sec);
            if (isNaN(n) || n < 0) return '—';
            var totalSec = Math.round(n);
            var h = Math.floor(totalSec / 3600);
            var m = Math.floor((totalSec % 3600) / 60);
            var s = totalSec % 60;
            function pad(x) { return (x < 10 ? '0' : '') + x; }
            return pad(h) + ':' + pad(m) + ':' + pad(s);
        }
        var html = '';
        list.forEach(function(row) {
            var agente = row.agent_name || row.agente || '—';
            var id = row.agent_id != null ? row.agent_id : (row.id != null ? row.id : '—');
            var agenteReporteUrl = getAgenteReporteGraficoUrl(id);
            var agenteHtml = agente;
            if (agenteReporteUrl) {
                agenteHtml = '<a href="' + agenteReporteUrl + '" class="text-blue-700 hover:text-blue-900 hover:underline">' + agente + '</a>';
            }
            html += '<tr>';
            html += '<td><div><div class="font-medium text-gray-900">' + agenteHtml + '</div><div class="text-xs text-gray-400">ID: ' + id + '</div></div></td>';
            html += '<td class="text-right f-mono text-gray-600">' + secondsToHHMMSS(row.session_seconds) + '</td>';
            html += '<td class="text-right f-mono"><div class="text-gray-900">' + secondsToHHMMSS(row.ready_seconds) + '</div><div class="text-xs text-green-600">' + fmtPct(row.ready_pct) + '</div></td>';
            html += '<td class="text-right f-mono"><div class="text-gray-900">' + secondsToHHMMSS(row.pause_seconds) + '</div><div class="text-xs text-orange-500">' + fmtPct(row.pause_pct) + '</div></td>';
            html += '<td class="text-right f-mono"><div class="text-gray-900">' + secondsToHHMMSS(row.acw_seconds) + '</div><div class="text-xs text-blue-600 font-bold">' + fmtPct(row.acw_pct) + '</div></td>';
            html += '<td class="text-right font-medium">' + fmtNum(row.total_interactions) + '</td>';
            html += '<td class="text-right f-mono font-medium text-gray-900">' + fmtNum(row.gestiones_count) + '</td>';
            html += '<td class="text-center text-gray-500 text-xs">';
            html += '<span class="bg-gray-100 px-2 py-1 rounded">' + fmtNum(row.inbound_voice_count) + ' <i class="fas fa-arrow-down text-gray-400 ml-1"></i></span> ';
            html += '<span class="bg-gray-100 px-2 py-1 rounded ml-1">' + fmtNum(row.outbound_voice_count) + ' <i class="fas fa-arrow-up text-gray-400 ml-1"></i></span>';
            html += '</td>';
            html += '<td class="text-center text-gray-500 text-xs">';
            html += '<span class="bg-gray-100 px-2 py-1 rounded">' + fmtNum(row.inbound_chat_count) + ' <i class="fas fa-arrow-down text-gray-400 ml-1"></i></span> ';
            html += '<span class="bg-gray-100 px-2 py-1 rounded ml-1">' + fmtNum(row.outbound_chat_count) + ' <i class="fas fa-arrow-up text-gray-400 ml-1"></i></span>';
            html += '</td>';
            html += '<td class="text-right f-mono text-gray-600">' + secondsToHHMMSS(row.conversation_seconds) + '</td>';
            html += '<td class="text-right f-mono font-medium text-gray-900">' + secondsToHHMMSS(row.tmo_avg) + '</td>';
            html += '<td class="text-right f-mono font-medium text-gray-900">' + secondsToHHMMSS(row.act_avg) + '</td>';
            html += '<td class="text-center text-gray-500 text-xs">';
            html += '<span class="bg-gray-100 px-2 py-1 rounded">' + fmtNum(row.transfer_in_count) + ' <i class="fas fa-arrow-down text-gray-400 ml-1"></i></span> ';
            html += '<span class="bg-gray-100 px-2 py-1 rounded ml-1">' + fmtNum(row.transfer_out_count) + ' <i class="fas fa-arrow-up text-gray-400 ml-1"></i></span>';
            html += '</td>';
            html += '<td class="text-right f-mono font-medium text-gray-900">' + fmtNum(row.hold_count) + '</td>';
            html += '</tr>';
        });

        tbody.innerHTML = html || '<tr><td colspan="14" class="py-8 text-center text-gray-500">No hay datos para el rango seleccionado.</td></tr>';
        if (contador) {
            if (totalCount === 0) {
                contador.textContent = 'Mostrando 0 de 0 agentes';
            } else {
                var from = (page - 1) * pageSize + 1;
                var to = Math.min(page * pageSize, totalCount);
                contador.textContent = 'Mostrando ' + from + '–' + to + ' de ' + totalCount + ' agentes';
            }
        }
    }

    function renderPagination(data) {
        var nav = document.getElementById('reporte-performance-pagination');
        if (!nav) return;
        var numPages = (data && typeof data.num_pages === 'number') ? data.num_pages : 0;
        var page = (data && typeof data.page === 'number') ? data.page : 1;
        if (numPages <= 1) {
            nav.innerHTML = '';
            return;
        }
        var transPrincipio = typeof gettext !== 'undefined' ? gettext('Principio') : 'Principio';
        var transAnterior = typeof gettext !== 'undefined' ? gettext('Anterior') : 'Anterior';
        var transSiguiente = typeof gettext !== 'undefined' ? gettext('Siguiente') : 'Siguiente';
        var transFinal = typeof gettext !== 'undefined' ? gettext('Final') : 'Final';
        var rangeSize = 5;
        var pages = [];
        if (numPages <= rangeSize) {
            for (var i = 1; i <= numPages; i++) pages.push(i);
        } else if (page <= (rangeSize + 1) / 2) {
            for (var i = 1; i <= rangeSize; i++) pages.push(i);
        } else if (page > numPages - (rangeSize + 1) / 2) {
            for (var i = numPages - rangeSize + 1; i <= numPages; i++) pages.push(i);
        } else {
            var half = Math.floor((rangeSize - 1) / 2);
            for (var i = page - half; i <= page + half; i++) pages.push(i);
        }
        var html = '<ul class="pagination justify-content-center mb-0">';
        html += '<li class="page-item' + (page <= 1 ? ' disabled' : '') + '">';
        html += '<button type="button" class="page-link" data-page="1">' + transPrincipio + '</button></li>';
        html += '<li class="page-item' + (page <= 1 ? ' disabled' : '') + '">';
        html += '<button type="button" class="page-link" data-page="' + (page > 1 ? page - 1 : 1) + '">' + transAnterior + '</button></li>';
        for (var j = 0; j < pages.length; j++) {
            var p = pages[j];
            html += '<li class="page-item' + (p === page ? ' active' : '') + '">';
            html += '<button type="button" class="page-link" data-page="' + p + '">' + p + '</button></li>';
        }
        html += '<li class="page-item' + (page >= numPages ? ' disabled' : '') + '">';
        html += '<button type="button" class="page-link" data-page="' + (page < numPages ? page + 1 : numPages) + '">' + transSiguiente + '</button></li>';
        html += '<li class="page-item' + (page >= numPages ? ' disabled' : '') + '">';
        html += '<button type="button" class="page-link" data-page="' + numPages + '">' + transFinal + '</button></li>';
        html += '</ul>';
        nav.innerHTML = html;
    }

    function initPaginationNav() {
        $(document).on('click', '#reporte-performance-pagination .page-link', function(e) {
            var btn = e.currentTarget;
            if (btn.disabled || $(btn).closest('.page-item').hasClass('disabled')) return;
            var p = parseInt(btn.getAttribute('data-page'), 10);
            if (isNaN(p) || p < 1) return;
            currentPage = p;
            if (currentDateStart && currentDateEnd) fetchReport(currentDateStart, currentDateEnd, p);
        });
    }

    function initPageSizeSelect() {
        var $sel = $('#reporte-performance-page-size');
        if (!$sel.length) return;
        $sel.on('change', function() {
            currentPage = 1;
            if (currentDateStart && currentDateEnd) fetchReport(currentDateStart, currentDateEnd, 1);
        });
    }

    function updateSubtitulo(desdeStr, hastaStr) {
        var el = document.getElementById('reporte-performance-subtitulo');
        if (el) {
            el.textContent = 'Datos desde ' + (desdeStr || '—') + ' hasta ' + (hastaStr || '—');
        }
    }

    function fetchReport(dateStart, dateEnd, pageOverride) {
        var url = getApiUrl();
        if (!url) {
            lastReportData = { data: [], total_count: 0, page: 1, page_size: getPageSize(), num_pages: 0 };
            renderRows(lastReportData);
            renderPagination(lastReportData);
            return;
        }
        var page = pageOverride != null ? pageOverride : currentPage;
        var pageSize = getPageSize();
        var params = [
            'date_start=' + encodeURIComponent(dateStart),
            'date_end=' + encodeURIComponent(dateEnd),
            'page=' + encodeURIComponent(String(page)),
            'page_size=' + encodeURIComponent(String(pageSize))
        ];
        var filters = getSelectedAgenteGrupoForApi();
        (filters.agente || []).forEach(function(v) {
            params.push('agente=' + encodeURIComponent(String(v)));
        });
        (filters.grupo_agente || []).forEach(function(v) {
            params.push('grupo_agente=' + encodeURIComponent(String(v)));
        });
        var sep = url.indexOf('?') >= 0 ? '&' : '?';
        url = url + sep + params.join('&');

        var xhr = new XMLHttpRequest();
        xhr.open('GET', url, true);
        xhr.setRequestHeader('Accept', 'application/json');
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== 4) return;
            var data = { data: [], total_count: 0, page: 1, page_size: pageSize, num_pages: 0 };
            try {
                if (xhr.status === 200 && xhr.responseText) {
                    data = JSON.parse(xhr.responseText);
                }
            } catch (e) {}
            currentPage = data.page != null ? data.page : page;
            lastReportData = data;
            renderRows(data);
            renderPagination(data);
        };
        xhr.send();
    }

    function runSearch() {
        var rawVal = $('#id_fecha').val();
        var parsed = parseExistingRange(rawVal);
        if (!parsed) {
            currentDateStart = null;
            currentDateEnd = null;
            updateSubtitulo('', '');
            lastReportData = { data: [], total_count: 0, page: 1, page_size: getPageSize(), num_pages: 0 };
            renderRows(lastReportData);
            renderPagination(lastReportData);
            return;
        }
        var dateStart = parsed.startDate.format('YYYY-MM-DD');
        var dateEnd = parsed.endDate.format('YYYY-MM-DD');
        currentDateStart = dateStart;
        currentDateEnd = dateEnd;
        var desdeStr = parsed.startDate.format('DD/MM/YYYY');
        var hastaStr = parsed.endDate.format('DD/MM/YYYY');

        updateSubtitulo(desdeStr, hastaStr);
        currentPage = 1;
        fetchReport(dateStart, dateEnd, 1);

        var url = new URL(window.location.href);
        url.searchParams.set('fecha_desde', desdeStr);
        url.searchParams.set('fecha_hasta', hastaStr);
        window.history.replaceState({}, '', url.toString());
    }

    $(function() {
        var $form = $('#form-filtro-performance');
        if (!$form.length) return;

        var urlFechas = getFechasFromUrl();
        if (urlFechas.desde && urlFechas.hasta) {
            $('#id_fecha').val(urlFechas.desde + ' - ' + urlFechas.hasta);
        }

        initDateRangePicker();
        setDefaultFechas();
        initAgentesSelect();
        initGruposSelect();
        initTabsL1HashState();
        initListadoCSVExport();
        initPageSizeSelect();
        initPaginationNav();

        $form.on('submit', function(e) {
            e.preventDefault();
            runSearch();
        });

        runSearch();
    });
})();
