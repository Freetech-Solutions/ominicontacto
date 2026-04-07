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

/* global Urls */
/* global gettext */
var campaigns;
var table_dialers;
var table_data = [];
var rws;

var agentes = {};
//var campanas = {};
var campanas_supervisor = [];
var campanas_id_supervisor = [];
const MENSAJE_CONEXION_WEBSOCKET = 'Stream subscribed!';
var wombat_enabled = false;
let POLL_DELAY = 30 * 1000;

$(function() {
    campaigns = JSON.parse(document.getElementById('campaigns-data').textContent);
    wombat_enabled = JSON.parse(document.getElementById('wombat_enabled').textContent);
 
    campanas_supervisor = $('input#campanas_list').val().split(',');
    if (campanas_supervisor.length == 1 && campanas_supervisor[0] == '') {
        campanas_supervisor = [];
    }
    campanas_id_supervisor = $('input#campanas_list_id').val().split(',');
    createDataTable();
    subcribeFilterChange();
    handle_filter();
    
    connectToDataChannel();
    connectToSupervisorStream();
});

function connectToDataChannel(){
    const url = `wss://${window.location.host}/channels/supervision/dialer`;
    rws = new ReconnectingWebSocket(url, [], {
        connectionTimeout: 10000,
        maxReconnectionDelay: 3000,
        minReconnectionDelay: 1000,
    });
    rws.addEventListener('message', function(e) {
        let data = JSON.parse(e.data);
        processData(data);
    });
}

function processData(data){
    if (data.initial_data != undefined){
        initializeTable(data.initial_data);
    }
    else {
        updateTable(data);
    }
}

function initializeTable(initial_data){
    table_data = [];
    for (let camp_id in initial_data){
        let data = initial_data[camp_id];
        let name = campaigns[camp_id].name;
        let camp_data = new DialerStats(camp_id, name);
        for (let field in data){
            camp_data[field] = data[field];
        }
        updateTarget(camp_id, camp_data);
        table_data.push(camp_data);
    }
    table_dialers.clear();
    table_dialers.rows.add(table_data).draw();
    if (wombat_enabled){
        setTimeout(pollWombatStats, POLL_DELAY);
    }
}

function updateTable(event_data){
    if (event_data.type == 'update' && event_data.args.DIALER != undefined){
        const payload = event_data.args.DIALER;
        const updates = Array.isArray(payload) ? payload : [payload];
        updates.forEach(function(data) {
            let camp_id = data.campaign_id;
            let field = data.field;
            const delta = data.delta || 1;
            let camp_name = campaigns[camp_id].name;
            let row = table_dialers.row((idx, rowData) => rowData.name === camp_name);
            let row_data = row.data();
            if (field == 'channels'){
                row_data[field] = Number(data[field]);
            }
            else if (field == 'pending'){
                updatePending(row_data, data);
            }
            else if (field == 'status') {
                row_data.status = data.value;
            }
            else {
                row_data[field] = Number(row_data[field]) + delta;
                if (field == 'dispositions'){
                    updateTarget(camp_id, row_data);
                }
            }
            if (field == 'dialed' && Number.isFinite(data.channels)){
                row_data.channels = data.channels;
            }
            row.data(row_data);
        });
        table_dialers.draw();
    }
}

function updateTarget(camp_id, camp_data){
    let target = campaigns[camp_id].target;
    if (target == 0){
        camp_data.target = 100;
        return;
    }
    camp_data.target = (100 * camp_data.dispositions / target).toFixed(1);
}

function updatePending(camp_data, data){
    /** Only for OMniDialer */
    if (data.pending_initial !== undefined){
        camp_data.pending_initial = Number(data.pending_initial);
        camp_data.pending = camp_data.pending_initial + camp_data.pending_retries;
    }
    if (data.pending_retries !== undefined){
        camp_data.pending_retries = Number(data.pending_retries);
        camp_data.pending = camp_data.pending_initial + camp_data.pending_retries;
    }
}

function pollWombatStats() {
    let url = Urls.supervision_wombat_dialer_stats();
    $.get(url).success(
        function(data) {
            if (data['status'] == 'OK'){
                // Asumo que vienen los status de todas las campañas
                for (let id in data['statuses']){
                    let camp_name = campaigns[id].name;
                    let row = table_dialers.row((idx, data) => data.name === camp_name);
                    let row_data=row.data();

                    row_data.status = data['statuses'][id];
                    let pending = data['pendings'][id];
                    if (Number.isFinite(pending)){
                        row_data.pending = pending;
                    }
                    let channels = data['channels'][id];
                    if (Number.isFinite(channels)){
                        row_data['channels'] = channels;
                    }
                    row.data(row_data).draw();
                }
            }
        }
    );
    setTimeout(pollWombatStats, POLL_DELAY);
}


/** TODO: Dejar de procesar datos de agentes desde el stream. */
function connectToSupervisorStream(){
    const url = `wss://${window.location.host}/consumers/stream/supervisor/${$('input#supervisor_id').val()}/dialers`;
    const stream_rws = new ReconnectingWebSocket(url, [], {
        connectionTimeout: 10000,
        maxReconnectionDelay: 3000,
        minReconnectionDelay: 1000,
    });

    stream_rws.addEventListener('message', function(e) {
        if (e.data != MENSAJE_CONEXION_WEBSOCKET) {
            try {
                var data = JSON.parse(e.data);
                if (campanas_supervisor.length > 0) {
                    processAgentData(data);
                } else {
                    table_dialers.clear().draw();
                }
            } catch (err) {
                console.log(err);
            }
        }
    });

    function processAgentData(data) {
        let haveAgentsData = false;
        data.forEach(info => {
            try {
                let row = JSON.parse(info
                    .replaceAll('\'', '"')
                    .replaceAll('"[', '[')
                    .replaceAll(']"', ']')
                    .replaceAll('"{', '{')
                    .replaceAll('}"', '}'));
                if (row['NAME']) {
                    agents.updateAgent(row);
                    haveAgentsData = true;
                }
            } catch (err) {
                console.log(err);
            }
        });

        if (haveAgentsData) {
            let newAgentStats = agents.calculateStats(campanas_supervisor);
            for (const campaign in newAgentStats) {
                const nombre_saneado = campaign
                    .replaceAll('(', '')
                    .replaceAll(')', '');
                const statsEmpty = emptyStats(newAgentStats[campaign]);
                let row = table_dialers
                    .row('#' + nombre_saneado);
                let dataRow = row.data();
                if (!dataRow && !statsEmpty) {
                    let newDataRow = new DialerStats(campanas_id_supervisor[campanas_supervisor.indexOf(campaign)], campaign);
                    newDataRow.updateAgentStats(newAgentStats[campaign]);
                    table_dialers.row.add(newDataRow);
                } else if (dataRow && dataRow.isEmpty() && statsEmpty) {
                    row.remove();
                } else if (dataRow) {
                    dataRow.updateAgentStats(newAgentStats[campaign]);
                    row.data(dataRow);
                }
            }
        }
        table_dialers.draw();
    }

    function emptyStats(stats) {
        return stats.agents_online == 0 &&
            stats.agents_oncall == 0 &&
            stats.agents_onpause == 0;
    }
}

function createDataTable() {
    table_dialers = $('#tableDialers').DataTable({
        data: table_data,
        rowId: 'nombre_saneado',
        stateSave: true,
        columns: [
            { 'data': 'name' },
            { 'data': 'agents_online' },
            { 'data': 'agents_oncall' },
            { 'data': 'agents_onpause' },
            { 'data': 'agents_ready' },
            { 'data': 'dialed' },
            { 'data': 'attended' },
            { 'data': 'shortcall' },
            { 'data': 'not_attended' },
            { 'data': 'amd' },
            { 'data': 'channels' },
            { 'data': 'connections_lost' },
            { 'data': 'dispositions' },
            { 'data': 'pending' },
            { 'data': 'target' },
            { 'data': 'status', 'visible': false }, /** TODO ACTIVA(2) O PAUSADA(5) */
        ],
        'searchCols': [
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            { 'search': filter_by_status(), },
        ],
        lengthMenu: [[10, 25, 50, 100, 200, 500, -1], [10, 25, 50, 100, 200, 500 , gettext('Todos')]],
        language: {
            search: gettext('Buscar: '),
            infoFiltered: gettext('(filtrando de un total de _MAX_ campañas)'),
            paginate: {
                first: gettext('Primero '),
                previous: gettext('Anterior '),
                next: gettext(' Siguiente'),
                last: gettext(' Último'),
            },
            lengthMenu: gettext('Mostrar _MENU_ entradas'),
            info: gettext('Mostrando _START_ a _END_ de _TOTAL_ entradas'),
        }
    });
}
class DialerStats {

    constructor(id, name) {
        this.id = id;
        this.name = name;
        this.nombre_saneado = name
            .replaceAll('(', '')
            .replaceAll(')', '');
        this.dialed = 0;
        this.attended = 0;
        this.shortcall = 0;
        this.not_attended = 0;
        this.amd = 0;
        this.connections_lost = 0;
        this.dispositions = 0;
        this.pending = 0;
        this.pending_initial = 0;
        this.pending_retries = 0;
        this.channels = 0;
        this.agents_online = 0;
        this.agents_oncall = 0;
        this.agents_onpause = 0;
        this.agents_ready = 0;
        this.target = 0;
        this.status = 0;
    }

    isEmpty() {
        if (this.efectuadas > 0) return false;
        if (this.atendidas > 0) return false;
        if (this.no_atendidas > 0) return false;
        if (this.contestadores > 0) return false;
        if (this.connections_lost > 0) return false;
        if (this.gestiones > 0) return false;
        if (this.pending > 0) return false;
        if (this.channels > 0) return false;
        if (this.target > 0) return false;
        return true;
    }

    updateAgentStats(agentStats) {
        this.agents_online = agentStats.agents_online;
        this.agents_oncall = agentStats.agents_oncall;
        this.agents_onpause = agentStats.agents_onpause;
        this.agents_ready = this.agents_online - this.agents_oncall - this.agents_onpause;
    }

}

class Agents {
    constructor() {
        this.agentList = {};
    }

    calculateStats(campaignList) {
        let stats = {};
        campaignList.forEach(campaign => {
            stats[campaign] = {
                'agents_online': 0,
                'agents_oncall': 0,
                'agents_onpause': 0
            };
            Object.values(this.agentList).forEach(agent => {
                if (agent.campanas.includes(campaign) && agent.status != '') {
                    stats[campaign]['agents_online']++;
                    if (agent.status.indexOf('PAUSE') == 0) {
                        stats[campaign]['agents_onpause']++;
                    } else if (agent.status.indexOf('ONCALL') == 0) {
                        stats[campaign]['agents_oncall']++;
                    }
                }
            });
        });
        return stats;
    }

    updateAgent(newAgentData) {
        const agentId = newAgentData.id;
        if (!agentId) return;
        this.agentList[agentId] = (this.agentList[agentId]) ? this.agentList[agentId] : {};

        if (this.agentList[agentId]['timestamp'] &&
            this.agentList[agentId]['timestamp'] > newAgentData.TIMESTAMP) {
            return;
        }

        this.agentList[agentId]['campanas'] = newAgentData.CAMPANAS;
        this.agentList[agentId]['timestamp'] = newAgentData.TIMESTAMP;
        this.agentList[agentId]['campaign'] = newAgentData.CAMPAIGN;

        if (newAgentData.STATUS != '' &&
            newAgentData.STATUS != 'OFFLINE' &&
            newAgentData.STATUS != 'UNAVAILABLE') {
            this.agentList[agentId]['status'] = newAgentData.STATUS;

        } else {
            this.agentList[agentId]['status'] = '';
        }
    }
}

function subcribeFilterChange() {
    $('#filter_by_status').change(function() {
        handle_filter();
    });
}

function handle_filter() {
    let selection = $('#filter_by_status').find('option:selected');
    let value = selection.val();
    // Limpiar filtro obsoleto en columna 14 (target) restaurado por stateSave
    table_dialers.columns(14).search('');
    if(value > 0){
        table_dialers.columns(15).search(value).draw();
    } else {
        // Solo mostrar Activas (2) o Pausadas (5)
        table_dialers.columns(15).search('[2|5]', true, false).draw();
    }
}

function filter_by_status() {
    return $('#filter_by_status option:selected').val();
}

var agents = new Agents();
