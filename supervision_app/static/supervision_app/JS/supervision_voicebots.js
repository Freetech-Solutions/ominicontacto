/* Copyright (C) 2018 Freetech Solutions

 This file is part of OMniLeads

 This program is free software: you can redistribute it and/or modify
 it under the terms of the GNU Lesser General Public License version 3, as published by
 the Free Software Foundation.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Lesser General Public License for more details.

 You should have received a copy of the GNU Lesser General Public License
 along with this program.  If not, see http://www.gnu.org/licenses/.

*/
/* global create_node */
/* global gettext */
/* global moment */
/* global phone_controller */

var table_voicebots;
var voicebot_rows_cache = {};
const MENSAJE_CONEXION_WEBSOCKET_VOICEBOTS = 'Stream subscribed!';

$(function() {
    if ($('#tableVoicebots').length === 0) {
        return;
    }
    createVoicebotDataTable();
    fetchVoicebotLlamadas();

    const supervisorId = $('input#supervisor_id').val();
    const url = `wss://${window.location.host}/consumers/stream/supervisor/${supervisorId}/voicebots`;
    const rws = new ReconnectingWebSocket(url, [], {
        connectionTimeout: 10000,
        maxReconnectionDelay: 3000,
        minReconnectionDelay: 1000,
    });
    rws.addEventListener('message', function(e) {
        if (e.data !== MENSAJE_CONEXION_WEBSOCKET_VOICEBOTS) {
            try {
                processVoicebotStreamData(e.data);
            } catch (err) {
                console.log(err);
            }
        }
    });

    $('#filter_campana').on('change.voicebots', function() {
        applyVoicebotCampaignFilter();
    });
});

function getSelectedCampaignId() {
    const selection = $('#filter_campana').find('option:selected');
    const campaignId = selection.data('campaign-id');
    if (campaignId) {
        return String(campaignId);
    }
    const val = selection.val();
    return val && /^\d+$/.test(String(val)) ? val : '';
}

function fetchVoicebotLlamadas() {
    const baseUrl = window.SUPERVISION_VOICEBOT_LLAMADAS_URL;
    if (!baseUrl) {
        return;
    }
    const params = new URLSearchParams();
    const campaignId = getSelectedCampaignId();
    if (campaignId) {
        params.set('campaign_id', campaignId);
    }
    const url = params.toString() ? `${baseUrl}?${params.toString()}` : baseUrl;

    $.ajax({
        url: url,
        method: 'GET',
        dataType: 'json',
        success: function(jsonData) {
            voicebot_rows_cache = {};
            (jsonData.llamadas || []).forEach(function(llamada) {
                const row = normalizeVoicebotRow(llamada);
                if (row.row_id) {
                    voicebot_rows_cache[row.row_id] = row;
                }
            });
            renderVoicebotTableFromCache();
        },
        error: function() {
            voicebot_rows_cache = {};
            renderVoicebotTableFromCache();
        },
    });
}

function parseVoicebotStreamElement(element) {
    return JSON.parse(element
        .replaceAll('\'', '"')
        .replaceAll('’', '\'')
        .replaceAll('"[', '[')
        .replaceAll(']"', ']'));
}

function processVoicebotStreamData(rawData) {
    const data = JSON.parse(rawData);
    data.forEach(function(element) {
        try {
            const event = parseVoicebotStreamElement(element);
            if (event.action === 'delete' && event.row_id) {
                delete voicebot_rows_cache[event.row_id];
            } else if (event.action === 'upsert' && event.row_id) {
                const existing = voicebot_rows_cache[event.row_id] || {};
                const merged = normalizeVoicebotRow(Object.assign({}, event, {
                    nombre: existing.nombre || event.nombre,
                }));
                if (!matchesVoicebotCampaignFilter(merged)) {
                    delete voicebot_rows_cache[event.row_id];
                } else {
                    voicebot_rows_cache[event.row_id] = merged;
                }
            }
        } catch (err) {
            console.log('Error parsing voicebot stream data');
            console.log(err);
        }
    });
    renderVoicebotTableFromCache();
}

function matchesVoicebotCampaignFilter(row) {
    const campaignId = getSelectedCampaignId();
    if (!campaignId) {
        return true;
    }
    return String(row.campana_llamada) === String(campaignId);
}

function applyVoicebotCampaignFilter() {
    fetchVoicebotLlamadas();
}

function normalizeVoicebotRow(llamada) {
    return {
        row_id: llamada.row_id,
        id: llamada.agent_id || llamada.id,
        call_id: llamada.call_id || '',
        nombre: llamada.nombre || ('Bot ' + (llamada.agent_id || llamada.id)),
        campana_llamada: llamada.CAMPAIGN || llamada.campana_llamada || '',
        contacto: llamada.CONTACT_NUMBER || llamada.contacto || '',
        status: llamada.STATUS || llamada.status || 'ONCALL',
        tiempo: parseInt(llamada.TIMESTAMP || llamada.tiempo, 10) || 0,
    };
}

function renderVoicebotTableFromCache() {
    if (!table_voicebots) {
        return;
    }

    const newRows = voicebot_rows_cache;

    table_voicebots.rows().every(function() {
        const data = this.data();
        if (data && data.row_id && !newRows[data.row_id]) {
            this.remove(false);
        }
    });

    Object.keys(newRows).forEach(function(rowId) {
        const data = newRows[rowId];
        const existing = table_voicebots.row('#' + rowId);
        if (existing.length && existing.data()) {
            existing.data(data);
        } else {
            table_voicebots.row.add(data);
        }
    });

    table_voicebots.draw(false);
}

function getVoicebotSpyUrl() {
    if (window.SUPERVISION_API_CALL_SPY) {
        return window.SUPERVISION_API_CALL_SPY;
    }
    if (typeof Urls !== 'undefined' && typeof Urls.api_call_spy === 'function') {
        return Urls.api_call_spy();
    }
    return '/api/v1/call/spy/';
}

function getVoicebotHangupUrl() {
    if (window.SUPERVISION_API_CALL_VOICEBOT_HANGUP) {
        return window.SUPERVISION_API_CALL_VOICEBOT_HANGUP;
    }
    if (typeof Urls !== 'undefined' && typeof Urls.api_call_voicebot_hangup === 'function') {
        return Urls.api_call_voicebot_hangup();
    }
    return '/api/v1/call/voicebot-hangup/';
}

function voicebotActionBlocked() {
    if (typeof phone_controller !== 'undefined' && phone_controller.is_on_call()) {
        $.growl.warning({
            title: gettext('Atención!'),
            message: gettext('Debe finalizar la acción actual antes de realizar otra.')
        });
        return true;
    }
    return false;
}

function executeSpyVoicebotCall(agentId, callId) {
    if (voicebotActionBlocked()) {
        return;
    }
    const supervisorId = $('#supervisor_id').val();
    $.ajax({
        url: getVoicebotSpyUrl(),
        type: 'POST',
        dataType: 'json',
        data: {
            supervisor_id: supervisorId,
            agent_id: agentId,
            call_id: callId,
            whisper: 'none',
        },
        success: function() {
            $.growl.success({
                title: gettext('Éxito!'),
                message: gettext('Monitoreo iniciado correctamente.')
            });
        },
        error: function(jqXHR) {
            var errorMessage = gettext('Error al iniciar el monitoreo.');
            if (jqXHR.responseJSON && jqXHR.responseJSON.error) {
                errorMessage = jqXHR.responseJSON.error;
            }
            $.growl.error({ title: gettext('Error!'), message: errorMessage });
        },
    });
}

function executeWhisperVoicebotCall(agentId, callId) {
    if (voicebotActionBlocked()) {
        return;
    }
    const supervisorId = $('#supervisor_id').val();
    $.ajax({
        url: getVoicebotSpyUrl(),
        type: 'POST',
        dataType: 'json',
        data: {
            supervisor_id: supervisorId,
            agent_id: agentId,
            call_id: callId,
            whisper: 'both',
        },
        success: function() {
            $.growl.success({
                title: gettext('Éxito!'),
                message: gettext('Susurro iniciado correctamente.')
            });
        },
        error: function(jqXHR) {
            var errorMessage = gettext('Error al iniciar el susurro.');
            if (jqXHR.responseJSON && jqXHR.responseJSON.error) {
                errorMessage = jqXHR.responseJSON.error;
            }
            $.growl.error({ title: gettext('Error!'), message: errorMessage });
        },
    });
}

function executeHangupVoicebotCall(agentId, callId) {
    $.ajax({
        url: getVoicebotHangupUrl(),
        type: 'POST',
        dataType: 'json',
        data: {
            agent_id: agentId,
            call_id: callId,
        },
        success: function() {
            $.growl.success({
                title: gettext('Éxito!'),
                message: gettext('Llamada finalizada correctamente.')
            });
        },
        error: function(jqXHR) {
            var errorMessage = gettext('Error al finalizar la llamada.');
            if (jqXHR.responseJSON && jqXHR.responseJSON.error) {
                errorMessage = jqXHR.responseJSON.error;
            }
            $.growl.error({ title: gettext('Error!'), message: errorMessage });
        },
    });
}

function obtenerNodosAccionesVoicebot(pk_agent, call_id, status) {
    var $div = create_node('div');

    if (status && status.search('ONCALL') !== -1) {
        var $spy = create_node('a', {
            'class': 'btn btn-light btn-sm',
            'role': 'button',
            'href': '#',
            'onclick': 'executeSpyVoicebotCall(\'' + pk_agent + '\', \'' + call_id + '\'); return false;',
        });
        $spy.append(create_node('span', {
            'class': 'fas fa-volume-up',
            'aria-hidden': 'true',
            'title': gettext('Monitoreo'),
        }));

        var $whisper = create_node('a', {
            'class': 'btn btn-light btn-sm',
            'role': 'button',
            'href': '#',
            'onclick': 'executeWhisperVoicebotCall(\'' + pk_agent + '\', \'' + call_id + '\'); return false;',
        });
        $whisper.append(create_node('span', {
            'class': 'fas fa-comment',
            'aria-hidden': 'true',
            'title': gettext('Susurro'),
        }));

        var $hangup = create_node('a', {
            'class': 'btn btn-light btn-sm',
            'role': 'button',
            'href': '#',
            'onclick': 'executeHangupVoicebotCall(\'' + pk_agent + '\', \'' + call_id + '\'); return false;',
        });
        $hangup.append(create_node('span', {
            'class': 'fas fa-phone-slash',
            'aria-hidden': 'true',
            'title': gettext('Finalizar llamada'),
        }));

        $div.append($spy, $whisper, $hangup);
    }

    return $div.prop('outerHTML');
}

function createVoicebotDataTable() {
    table_voicebots = $('#tableVoicebots').DataTable({
        initComplete: function() {
            const TIME_COL_NUMBER = 4;
            setInterval(function() {
                if (!table_voicebots) {
                    return;
                }
                table_voicebots.rows({ page: 'current', search: 'applied' }).every(function(index) {
                    var cell = this.cell(index, TIME_COL_NUMBER);
                    cell.data(cell.data());
                });
            }, 2000);
        },
        data: [],
        stateSave: true,
        rowId: 'row_id',
        columns: [
            { data: 'nombre' },
            { data: 'campana_llamada' },
            { data: 'contacto' },
            {
                data: 'status',
                render: function(data) {
                    var $status = create_node('p');
                    $status.text(data);
                    if (data.search('ONCALL') !== -1) {
                        $status.attr('class', 'oncall');
                    }
                    return $status.prop('outerHTML');
                },
            },
            {
                data: 'tiempo',
                render: function(data) {
                    if (!data) {
                        return '-';
                    }
                    var duration = moment.duration(Math.round((Date.now() / 1000) - data), 'seconds');
                    return moment.utc(duration.as('milliseconds')).format('HH:mm:ss');
                },
            },
            {
                data: null,
                render: function(data, type, row) {
                    return obtenerNodosAccionesVoicebot(row.id, row.call_id, row.status);
                },
            },
        ],
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, gettext('Todos')]],
        language: {
            search: gettext('Buscar: '),
            paginate: {
                first: gettext('Primero '),
                previous: gettext('Anterior '),
                next: gettext(' Siguiente'),
                last: gettext(' Último'),
            },
            lengthMenu: gettext('Mostrar _MENU_ entradas'),
            info: gettext('Mostrando _START_ a _END_ de _TOTAL_ entradas'),
        },
        orderMulti: true,
    });
}
