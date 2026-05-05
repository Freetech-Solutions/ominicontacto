/* global Urls */
/* global get_ranges */
/* global gettext */
var analysis_stats = {};
const MENSAJE_CONEXION_WEBSOCKET = 'Subscribed!';

/**
 * Modal de transferencias (misma API y UI que reporte centro de contacto).
 */
function initTransferenciasModalBusquedaGrabacion() {
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

    $(document).on('click', '.reporte-cc-transferencias-trigger', function (e) {
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
            .then(function (response) {
                return response.text().then(function (text) {
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
            .then(function (data) {
                var transfers = data.transfers || [];
                $loading.addClass('d-none');
                if (!transfers.length) {
                    $vacio.removeClass('d-none');
                    return;
                }
                transfers.forEach(function (t) {
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
                        t.destination_target,
                        t.destination_type,
                        t.transfer_type,
                        t.status,
                        cellLabel('source_agent_label', 'source_agent_id'),
                        cellLabel('destination_agent_label', 'destination_agent_id'),
                        cellLabel('destination_campaign_label', 'destination_campaign_id'),
                        dur,
                    ];
                    cells.forEach(function (val) {
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
            .catch(function (err) {
                showError(err.message || gettextMsg('Error al cargar transferencias.', 'Error al cargar transferencias.'));
            });
    });

    $modal.on('hidden.bs.modal', function () {
        resetModalBody();
    });
}

$(document).ready(function () {

    const $fecha = $('#id_fecha');
    $fecha.on('apply.daterangepicker', function (ev, picker) {
        $(this).val(picker.startDate.format('DD/MM/YYYY') + ' - ' + picker.endDate.format('DD/MM/YYYY'));
    });
    $fecha.on('cancel.daterangepicker', function (ev, picker) {
        $(this).val('');
    });
    $fecha.daterangepicker(
        {
            locale: { format: 'DD/MM/YYYY' },
            ranges: get_ranges(),
        },
        function (start, end, label) {
            $(this).html(start.format('MMMM D, YYYY') + ' - ' + end.format('MMMM D, YYYY'));
        }
    );

    $('select.form-control').each(function () {
        $(this).select2();
    });

    const reconnectGracePeriodMs = 15000;
    let elapsedIntervalId = null;
    let reconnectTimeoutId = null;
    let loadingStartTime = null;
    let currentTaskId = null;
    let requestInFlight = false;
    let requestResolved = false;
    let resultFetchInProgress = false;

    function getLoadingElements() {
        return {
            $button: $('#id_buscar_btn'),
            $status: $('#recordings_search_loading_status'),
            $spinner: $('#recordings_search_loading_spinner'),
            $message: $('#recordings_search_loading_message'),
            $elapsed: $('#recordings_search_loading_elapsed'),
        };
    }

    function formatElapsed(milliseconds) {
        const totalSeconds = Math.floor(milliseconds / 1000);
        const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
        const seconds = String(totalSeconds % 60).padStart(2, '0');
        return `${minutes}:${seconds}`;
    }

    function generateTaskId() {
        if (window.crypto && typeof window.crypto.randomUUID === 'function') {
            return window.crypto.randomUUID();
        }
        return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }

    function stopElapsedCounter() {
        if (elapsedIntervalId !== null) {
            window.clearInterval(elapsedIntervalId);
            elapsedIntervalId = null;
        }
        loadingStartTime = null;
    }

    function clearReconnectTimeout() {
        if (reconnectTimeoutId !== null) {
            window.clearTimeout(reconnectTimeoutId);
            reconnectTimeoutId = null;
        }
    }

    function startElapsedCounter() {
        const { $elapsed } = getLoadingElements();
        stopElapsedCounter();
        loadingStartTime = Date.now();
        $elapsed.text('00:00');
        elapsedIntervalId = window.setInterval(function () {
            $elapsed.text(formatElapsed(Date.now() - loadingStartTime));
        }, 1000);
    }

    function updateStatus(customMessage, isError) {
        const { $status, $spinner, $message } = getLoadingElements();
        if (!$status.length) {
            return;
        }

        $status.removeClass('hidden');
        $message.text(customMessage);
        if (isError) {
            $status.addClass('recordings-search-loading-status--error');
            $spinner.addClass('hidden');
            return;
        }

        $status.removeClass('recordings-search-loading-status--error');
        $spinner.removeClass('hidden');
    }

    function sendResumeRequest() {
        if (!requestInFlight || requestResolved || !currentTaskId) {
            return;
        }
        try {
            rws.send(JSON.stringify({
                'type': 'search_recordings.resume',
                'task_id': currentTaskId,
            }));
        } catch (error) {
            startReconnectTimeout();
        }
    }

    async function fetchTaskResult() {
        const { $status } = getLoadingElements();
        if (!currentTaskId || !$status.length || resultFetchInProgress) {
            return;
        }

        resultFetchInProgress = true;
        updateStatus($status.data('fetching-result-text'), false);

        try {
            const response = await fetch(
                `${$status.data('result-url')}?task_id=${encodeURIComponent(currentTaskId)}`,
                {
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    credentials: 'same-origin',
                }
            );

            if (response.status === 202) {
                window.setTimeout(fetchTaskResult, 1000);
                return;
            }

            if (!response.ok) {
                const errorPayload = await response.json();
                throw new Error(errorPayload.error_message || $status.data('connection-error-text'));
            }

            const result = await response.json();
            requestResolved = true;
            setLoading(false);
            applyFragments(result.fragments);
        } catch (error) {
            setLoading(false, error.message || $status.data('connection-error-text'));
        } finally {
            // eslint-disable-next-line require-atomic-updates
            resultFetchInProgress = false;
        }
    }

    function updateStatusFromServer(status, errorMessage) {
        const { $status } = getLoadingElements();
        if (!$status.length) {
            return;
        }
        if (status === 'queued') {
            updateStatus($status.data('queued-text'), false);
            return;
        }
        if (status === 'running') {
            updateStatus($status.data('running-text'), false);
            return;
        }
        if (status === 'done') {
            fetchTaskResult();
            return;
        }
        if (status === 'failed') {
            setLoading(false, errorMessage || $status.data('connection-error-text'));
        }
    }

    function setLoading(value, customMessage) {
        const { $button, $status } = getLoadingElements();
        if (!$button.length || !$status.length) {
            clearReconnectTimeout();
            stopElapsedCounter();
            return;
        }
        if (value) {
            clearReconnectTimeout();
            requestInFlight = true;
            requestResolved = false;
            resultFetchInProgress = false;
            $button.prop('disabled', true);
            updateStatus(customMessage || $status.data('loading-text'), false);
            startElapsedCounter();
            return;
        }

        clearReconnectTimeout();
        $button.prop('disabled', false);
        stopElapsedCounter();
        requestInFlight = false;
        resultFetchInProgress = false;
        if (!customMessage) {
            requestResolved = true;
            currentTaskId = null;
        }

        if (customMessage) {
            currentTaskId = null;
            updateStatus(customMessage, true);
            return;
        }
        $status.addClass('hidden');
    }

    function startReconnectTimeout() {
        const { $status } = getLoadingElements();
        clearReconnectTimeout();
        reconnectTimeoutId = window.setTimeout(function () {
            if (requestInFlight && !requestResolved) {
                currentTaskId = null;
                setLoading(false, $status.data('connection-error-text'));
            }
        }, reconnectGracePeriodMs);
    }

    const $barraProgresoZip = $('#barraProgresoZip');
    const $checkGeneral = $('#check-general');
    const $check_mostrar_datos_contacto = $('#check-mostrar-datos-contacto');
    const $zipDescargaLink = $('#zipDescargaLink');
    const $zipGrabaciones = $('#zipGrabaciones');

    const $form = $('#form-buscar-grabacion');
    const websocketProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const rws = new ReconnectingWebSocket(
        `${websocketProtocol}://${window.location.host}/channels/background-tasks`,
        [],
        {
            connectionTimeout: 8000,
            maxReconnectionDelay: 3000,
            minReconnectionDelay: 1000,
            // debug: true,
        }
    );

    function applyFragments(fragments) {
        if (!fragments) {
            return;
        }
        $barraProgresoZip.hide();
        $zipDescargaLink.hide();
        $zipGrabaciones.show();
        $checkGeneral.prop('checked', false);
        Object.entries(fragments).forEach(([fragment, content]) => {
            $(fragment).html(content);
        });
    }

    function sendSearchRequest() {
        currentTaskId = generateTaskId();
        setLoading(true);
        try {
            rws.send(JSON.stringify({
                'type': 'search_recordings.request',
                'task_id': currentTaskId,
                'data': $form.serialize(),
            }));
        } catch (error) {
            currentTaskId = null;
            setLoading(false, getLoadingElements().$status.data('connection-error-text'));
        }
    }

    $form.submit(function (event) {
        event.preventDefault();
        sendSearchRequest();
    });

    rws.addEventListener('message', function (event) {
        const message = JSON.parse(event.data);
        if (
            message.task_id
            && currentTaskId
            && message.task_id !== currentTaskId
        ) {
            return;
        }
        if (message.type === 'search_recordings.status') {
            if (!requestInFlight) {
                return;
            }
            updateStatusFromServer(message.status, message.error_message);
            return;
        }
        if (message.type === 'search_recordings.respond') {
            if (!requestInFlight) {
                return;
            }
            setLoading(false);
            applyFragments(message.result.fragments);
            // console.log(JSON.stringify(message, null, 2))
        }
    });

    rws.addEventListener('open', function () {
        if (requestInFlight && !requestResolved) {
            clearReconnectTimeout();
            updateStatus(getLoadingElements().$status.data('loading-text'), false);
            sendResumeRequest();
        }
    });

    rws.addEventListener('close', function () {
        const { $button, $status } = getLoadingElements();
        if (requestInFlight && !requestResolved && $button.prop('disabled') && $status.length) {
            updateStatus($status.data('reconnecting-text'), false);
            startReconnectTimeout();
        }
    });

    rws.addEventListener('error', function () {
        const { $button, $status } = getLoadingElements();
        if (requestInFlight && !requestResolved && $button.prop('disabled') && $status.length) {
            updateStatus($status.data('reconnecting-text'), false);
            startReconnectTimeout();
        }
    });



    $('#pagination').on('click', '.page-link', function () {
        $('#id_pagina').val(this.dataset.page);
        sendSearchRequest();
    });

    $('#descripcionModal').on('show.bs.modal', function (event) {
        var button = $(event.relatedTarget);
        var uid_val = button.data('uid');
        var modal = $(this);
        var URL = Urls.grabacion_descripcion(uid_val);
        $.get(
            URL,
            function (data) {
                $('#descripcionModalLabel').text(data.result);
                $('#descripcion-text').text(data.descripcion);
            }
        ).fail(function (data) {
            $('#descripcionModalLabel').text(gettext('Error'));
            $('#descripcion-text').text(gettext('Ha ocurrido un error al intentar conectarse'));
        });
    });

    $checkGeneral.on('click', function () {
        $('.check-grabacion').prop('checked', $checkGeneral.prop('checked'));
    });

    $('#table-body').on('click', '.check-grabacion', function () {
        if (!$('#check-grabacion').prop('checked')) {
            $checkGeneral.prop('checked', false);
        }
    });

    $zipGrabaciones.on('click', function () {
        if ($('.check-grabacion:checked').length === 0) {
            return;
        }
        let final = false;
        // establece conexion a websocket para obtener los status
        // y enviarlos a la barra de progreso
        const rws_tmp = new ReconnectingWebSocket(
            `${websocketProtocol}://${window.location.host}/consumers/genera_zip_grabaciones/grabaciones/${$('#user_id').val()}/zip`,
            [],
            {
                connectionTimeout: 8000,
                maxReconnectionDelay: 3000,
                minReconnectionDelay: 1000,
                // debug: true,
            }
        );
        rws_tmp.addEventListener('message', function (e) {
            const data = e.data;
            if (data == 'Subscribed!') {
                generarZip();
            } else if (!final) {
                $barraProgresoZip.find('.progress-bar').width(data + '%').text(data + '%');
                if (data == '100') {
                    final = true;
                }
            } else {
                $zipGrabaciones.hide();
                $zipDescargaLink.attr('href', Urls.api_grabacion_archivo() + '?filename=/zip/' + data);
                $zipDescargaLink.show();
                rws_tmp.close();
            }
        });
    });

    function generarZip() {
        $.ajax({
            type: 'POST',
            url: Urls.api_grabacion_descarga_masiva(),
            dataType: 'json',
            data: {
                files: JSON.stringify(prepareData()),
                mostrar_datos_contacto: $check_mostrar_datos_contacto.is(':checked')
            },
            success: function (msg) {
                console.log(msg);
            },
            error: function (jqXHR, textStatus, errorThrown) {
                console.log(gettext('Error al ejecutar => ') + textStatus + ' - ' + errorThrown);
            }
        });
        $barraProgresoZip.show();
    }

    function prepareData() {
        return $('.check-grabacion:checked').map(function () {
            const row = $('#tr-' + $(this).val());
            return {
                fecha: row.find('td').eq(2).text(),
                tipo_llamada: row.find('td').eq(3).text(),
                telefono_cliente: row.find('td').eq(4).text(),
                agente: row.find('td').eq(5).text(),
                campana: row.find('td').eq(6).text(),
                archivo: row.find('audio > source').attr('src').split('filename=/')[1],
                calificacion: row.find('td').eq(8).find('a').map(function (_, e) { return e.innerText.trim(); }).toArray().join(', '),
                agente_username: row.find('td').eq(11).text(),
                contacto_id: row.find('td').eq(12).text(),
            };
        }).get();
    }

    /** Sentiment Analysis */
    function updateSentimentAnalysisButtons() {
        $('[data-callid]').each(function (i, button){
            $(button).click(function () {
                executeButtonAction($(this).data('callid'), $(this).data('task'));
            });
            updateSentimentAnalysisButton(button);
        });

    }

    function updateSentimentAnalysisButton(button){
        // Appears instantly on hover
        $(button).tooltip({show: { effect: 'none', delay: 0 }});
        let data = $(button).data();
        // Segun el estado mostrar color distinto
        $(button).removeClass('btn-info btn-warning btn-success btn-danger');
        let status = 0;
        if (data.callid in analysis_stats) {
            status = analysis_stats[data.callid][data.task];
        }
        switch (status) {
        case 0:  // EMPTY
            $(button).addClass('btn-info');  // Celeste
            $(button).attr('title', (gettext('Generar')));
            break;
        case 1:  // PROCESSING
            $(button).addClass('btn-warning');  // Naranja
            $(button).attr('title', (gettext('Generando')));
            break;
        case 2:  // COMPLETED
            $(button).addClass('btn-success');  // Verde
            $(button).attr('title', (gettext('Descargar')));
            break;
        case 3:  // ERROR
            $(button).addClass('btn-danger');  // Rojo
            $(button).attr('title', (gettext('ERROR')));
            break;
        default:
            break;
        }
    }

    function executeButtonAction(callid, task){
        var status = 0;
        if (callid in analysis_stats) {
            status = analysis_stats[callid][task];
        }
        // TODO: Validate task
        switch (status) {
        case 0:
            startProcessing(callid, task);
            break;
        case 1:
            $.growl.warning({
                'title': gettext('Aviso'),
                'message': gettext('Procesamiento en curso.'),
                'duration': 5000});
            break;
        case 2:
            if (task === 'transcription') {
                openTranscripcionModal(callid);
            } else {
                downloadFile(callid, task);
            }
            break;
        case 3:
            // Se produjo un error al procesar
            if (confirm(gettext('Error de procesamiento. ¿DeseaReintentar?'))){
                startProcessing(callid, task);
            }
            break;
        default:
            $.growl.error({
                'title': gettext('Error'),
                'message': gettext('Análisis no disponible.'),
                'duration': 5000});
            break;
        }
    }

    function startProcessing(callid, task) {
        var URL = Urls.api_call_record_analysis(task, callid);
        $.ajax({
            url: URL,
            type: 'POST',
            dataType: 'json',
            success: function(data){
                if (data['status'] == 'ERROR') {
                    setErrorInTask(callid, task);
                    $.growl.error({
                        'title': gettext('Error'),
                        'message': gettext('Error al intentar ejecutar la tarea.'),
                        'duration': 5000});
                }
                else {
                    setProcessingTask(callid, task);
                    if (task === 'transcription') {
                        $.growl.notice({
                            'title': gettext('Proceso iniciado'),
                            'message': gettext('Transcripción y resumen en proceso, puede tomar un tiempo. Aguarde por favor.'),
                            'duration': 5000
                        });
                    }
                }
            },
            error: function(jqXHR, textStatus, errorThrown) {
                $.growl.error({
                    'title': gettext('Error'),
                    'message': gettext('Error al intentar ejecutar la tarea.'),
                    'duration': 5000});
                console.log(gettext('Error al ejecutar => ') + textStatus + ' - ' + errorThrown);
            }
        });
    }

    function setProcessingTask(callid, task){
        if (!(callid in analysis_stats)) {
            analysis_stats[callid] = {};
        }
        analysis_stats[callid][task] = 1;
        let button = $(`[data-callid="${callid}"][data-task="${task}"]`);
        updateSentimentAnalysisButton(button);
    }

    function setErrorInTask(callid, task){
        if (!(callid in analysis_stats)) {
            analysis_stats[callid] = {};
        }
        analysis_stats[callid][task] = 3;
        let button = $(`[data-callid="${callid}"][data-task="${task}"]`);
        updateSentimentAnalysisButton(button);
    }

    // Normaliza callid del WS (ej. "2026-03-05/1772740687.1.mp3") al formato de la tabla (ej. "1772740687.1")
    function normalizedTableCallid(wsCallid) {
        if (!wsCallid || typeof wsCallid !== 'string') return wsCallid;
        const withDatePath = /^\d{4}-\d{2}-\d{2}\//;
        if (withDatePath.test(wsCallid)) {
            return wsCallid.replace(withDatePath, '').replace(/\.mp3$/i, '');
        }
        return wsCallid;
    }

    function updateSentimentAnalysis(data) {
        let task = data.task;
        let callid = data.callid;
        let status = data[`${task}_status`];
        let file = data[`${task}_file`];
        if (!(callid in analysis_stats)) {
            analysis_stats[callid] = {};
        }
        analysis_stats[callid][task] = status;
        analysis_stats[callid][`${task}_file`] = file;
        const tableCallid = normalizedTableCallid(callid);
        if (tableCallid !== callid && !(tableCallid in analysis_stats)) {
            analysis_stats[tableCallid] = {};
        }
        if (tableCallid !== callid) {
            analysis_stats[tableCallid][task] = status;
            analysis_stats[tableCallid][`${task}_file`] = file;
        }
        let button = $(`[data-callid="${callid}"][data-task="${task}"]`);
        if (button.length === 0 && tableCallid !== callid) {
            button = $(`[data-callid="${tableCallid}"][data-task="${task}"]`);
        }
        if (button.length > 0) {
            updateSentimentAnalysisButton(button);
        }
        if (status == '3'){
            let msg = gettext('Análisis no disponible.');
            if ('msg' in data){
                msg = data['msg'];
            }
            $.growl.error({
                'title': gettext('Error de procesamiento'),
                'message': msg,
                'duration': 5000});
        }
        if (task === 'transcription' && (status == 2 || status == '2')) {
            $.growl.notice({
                'title': gettext('Proceso finalizado'),
                'message': gettext('La transcripción y el resumen de la grabación han finalizado.'),
                'duration': 5000
            });
        }
    }

    function downloadFile(callid, task) {
        let filename = analysis_stats[callid][`${task}_file`];
        let url = Urls.api_grabacion_archivo() + '?filename=' + filename;
        console.log(url);
        window.open(url, '_blank');

        // API o link directo?
    }

    function downloadTextAsFile(text, filename) {
        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function openTranscripcionModal(callid) {
        let filename = (callid in analysis_stats && analysis_stats[callid].transcription_file)
            ? analysis_stats[callid].transcription_file
            : (function () {
                const tableCallid = normalizedTableCallid(callid);
                return (tableCallid in analysis_stats && analysis_stats[tableCallid].transcription_file)
                    ? analysis_stats[tableCallid].transcription_file
                    : null;
            })();
        if (!filename) {
            $.growl.error({
                'title': gettext('Error'),
                'message': gettext('No hay archivo de transcripción disponible.'),
                'duration': 5000
            });
            return;
        }
        const url = Urls.api_grabacion_archivo() + '?filename=' + encodeURIComponent(filename);
        const downloadFilename = filename.split('/').pop() || 'transcripcion.json';
        const downloadBase = downloadFilename.replace(/\.json$/i, '');

        $('#transcripcion-modal-loading').show();
        $('#transcripcion-modal-content').hide();
        $('#transcripcion-modal-error').hide().empty();
        $('#transcripcion-modal-json-collapse').collapse('hide');
        $('#transcripcion-download-transcription').hide();
        $('#transcripcion-download-summary').hide();
        $('#transcripcionModal').data('download-base', downloadBase).modal('show');

        $('#transcripcion-download-link').attr('href', url).attr('download', downloadFilename);

        fetch(url, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) throw new Error(gettext('Error al cargar el archivo.'));
                return response.text();
            })
            .then(function (text) {
                let data;
                try {
                    data = JSON.parse(text);
                } catch (e) {
                    throw new Error(gettext('El contenido no es un JSON válido.'));
                }
                $('#transcripcion-modal-loading').hide();
                $('#transcripcion-modal-content').show();
                $('#transcripcion-modal-text').text(data.text || '');
                if (data.summary) {
                    $('#transcripcion-modal-summary-wrap').show();
                    $('#transcripcion-modal-summary').text(data.summary);
                    $('#transcripcion-download-summary').show();
                } else {
                    $('#transcripcion-modal-summary-wrap').hide();
                    $('#transcripcion-download-summary').hide();
                }
                $('#transcripcion-modal-json').text(JSON.stringify(data, null, 2));
                $('#transcripcion-download-transcription').show();
            })
            .catch(function (err) {
                $('#transcripcion-modal-loading').hide();
                $('#transcripcion-modal-content').hide();
                $('#transcripcion-modal-error').show().text(err.message || gettext('Error al cargar la transcripción.'));
                $('#transcripcion-download-transcription').hide();
                $('#transcripcion-download-summary').hide();
                $.growl.error({
                    'title': gettext('Error'),
                    'message': err.message || gettext('Error al cargar la transcripción.'),
                    'duration': 5000
                });
            });
    }

    $('#transcripcion-download-transcription').on('click', function () {
        const base = $('#transcripcionModal').data('download-base') || 'transcripcion';
        const text = $('#transcripcion-modal-text').text();
        downloadTextAsFile(text, base + '_transcripcion.txt');
    });
    $('#transcripcion-download-summary').on('click', function () {
        const base = $('#transcripcionModal').data('download-base') || 'resumen';
        const text = $('#transcripcion-modal-summary').text();
        downloadTextAsFile(text, base + '_resumen.txt');
    });

    initTransferenciasModalBusquedaGrabacion();
});
