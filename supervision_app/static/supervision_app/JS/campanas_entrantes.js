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
var table_entrantes;
var table_data = [];
var rws;
var campanas_supervisor = [];
var campanas_id_supervisor = [];

const MENSAJE_CONEXION_WEBSOCKET = 'Stream subscribed!';


$(function() {
    campaigns = JSON.parse(document.getElementById('campaigns-data').textContent);

    campanas_supervisor = $('input#campanas_list').val().split(',');
    campanas_id_supervisor = $('input#campanas_list_id').val().split(',');
    createDataTable();

    connectToDataChannel();
    connectToSupervisorStream();
});

function connectToDataChannel(){
    const url = `wss://${window.location.host}/channels/supervision/inbound`;
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
    // let no_calls = [];
    for (let camp_id in initial_data){
        let data = initial_data[camp_id];
        let name = campaigns[camp_id].name;
        let camp_stats = new InboundStats(camp_id, name);
        camp_stats.initializeCallStats(data);
        table_data.push(camp_stats);
        // if (camp_stats.hasNoCalls()){
        //     no_calls.push(camp_stats);
        // }
    }
    table_entrantes.clear();
    table_entrantes.rows.add(table_data).draw();

    // // Remove rows with no calls and no agents
    // no_calls.forEach(dataRow => {
    //     let row = ? // Get proper row
    //     console.log(dataRow)
    //     if (dataRow && dataRow.hasNoAgents()){
    //         row.remove();
    //     }
    // });

}

function updateTable(event_data){
    if (event_data.type == 'update' && event_data.args.IN != undefined){
        let camp_id = event_data.args.IN.campaign_id;
        let camp_name = campaigns[camp_id].name;
        let row = table_entrantes.row((idx, data) => data.name === camp_name);
        let row_data=row.data();
        row_data.updateCallMetric(event_data.args.IN);
        row.data(row_data).draw();
    }
}

/** TODO: Dejar de procesar datos de agentes desde el stream. */
function connectToSupervisorStream(){
    const url = `wss://${window.location.host}/consumers/stream/supervisor/${$('input#supervisor_id').val()}/entrantes`;
    const rws = new ReconnectingWebSocket(url, [], {
        connectionTimeout: 10000,
        maxReconnectionDelay: 3000,
        minReconnectionDelay: 1000,
    });
    rws.addEventListener('message', function(e) {
        if (e.data != MENSAJE_CONEXION_WEBSOCKET) {
            try {
                var data = JSON.parse(e.data);
                processData(data);
            } catch (err) {
                console.log(err);
            }
        }
    });

    function processData(data) {
        let haveAgentsData = false;
        let fistCallStats = {};
        data.forEach(info => {
            let row = JSON.parse(info
                .replaceAll('\'', '"')
                .replaceAll('"[', '[')
                .replaceAll(']"', ']'));
            if (row['NAME']) {
                // Agent Stats Data
                agents.updateAgent(row);
                haveAgentsData = true;
            }
        });

        // Update/add rows with received Agents Stats Data 
        if (haveAgentsData) {
            let newAgentStats = agents.calculateStats(campanas_supervisor);
            for (const campaign in newAgentStats) {
                const statsEmpty = emptyStats(newAgentStats[campaign]);
                let row = table_entrantes.row('#' + campaign);
                let dataRow = row.data();
                if (dataRow == null && !statsEmpty) {
                    let campaign_id = campanas_id_supervisor[campanas_supervisor.indexOf(campaign)];
                    let newDataRow = new InboundStats(campaign_id, campaign);
                    newDataRow.updateAgentStats(newAgentStats[campaign]);
                    table_entrantes.row.add(newDataRow);
                } else if (dataRow && dataRow.hasNoCalls() && statsEmpty) {
                    row.remove();
                } else if (dataRow) {
                    dataRow.updateAgentStats(newAgentStats[campaign]);
                    row.data(dataRow);
                }
            }
        }
        table_entrantes.draw();
    }

    function emptyStats(stats) {
        return stats.agentes_online == 0 &&
            stats.agentes_llamada == 0 &&
            stats.agentes_pausa == 0;
    }

}

function createDataTable() {
    table_entrantes = $('#tableEntrantes').DataTable({
        data: table_data,
        rowId: 'name',
        columns: [
            { 'data': 'name' },
            { 'data': 'agentes_online' },
            { 'data': 'agentes_llamada' },
            { 'data': 'agentes_pausa' },
            { 'data': 'agentes_ready' },
            { 'data': 'queue_size' },
            { 'data': 'attended' },
            { 'data': 'abandons' },
            { 'data': 'expired' },
            { 'data': 'abandon_avg'},
            { 'data': 'wait_avg'},
            { 'data': 'abandon_rate' },
            { 'data': 'dispositions' },
            { 'data': 'target' },
        ],
        lengthMenu: [[10, 25, 50, 100, 200, 500, -1], [10, 25, 50, 100, 200, 500 , gettext('Todos')]],
        language: {
            search: gettext('Buscar: '),
            infoFiltered: gettext('(filtrando de un total de _MAX_ contactos)'),
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

class InboundStats {

    constructor(id, name) {
        this.id = id;
        this.name = name;
        this.queue_size = 0;
        this.attended = 0;
        this.abandons = 0;
        this.expired = 0;
        this.total_abandon_time = 0;
        this.abandon_avg = 0;
        this.wait_avg = 0;
        this.dispositions = 0;
        this.agentes_online = 0;
        this.agentes_llamada = 0;
        this.agentes_pausa = 0;
        this.agentes_ready = 0;
        this.abandon_rate = 0;
        this.target = 100;
        this.disposition_target = campaigns[id].target;
    }

    hasNoCalls() {
        if (this.queue_size != 0 ||
            this.attended != 0 ||
            this.abandons != 0 ||
            this.expired != 0 ||
            this.dispositions != 0) return false;
        return true;
    }

    hasNoAgents() {
        return this.agentes_online == 0;
    }

    initializeCallStats(newStats) {
        this.queue_size = newStats['queue_size'];
        this.attended = parseInt(newStats['attended']);
        this.abandons = parseInt(newStats['abandons']);
        this.expired = parseInt(newStats['expired']);
        this.dispositions = newStats['dispositions'];
        this.total_abandon_time = parseFloat(newStats['total_abandon_time']);
        this.total_wait_time = parseFloat(newStats['total_wait_time']);

        this.updateAbandonAvg();
        this.updateAbandonRate();
        this.updateWaitAvg();
        this.updateTarget();
    }

    updateAbandonAvg(){
        let avg = 0;
        if (this.abandons > 0) {
            avg = this.total_abandon_time / this.abandons;
        }
        this.abandon_avg = avg.toFixed(1) + gettext(' segundos');
    }

    updateAbandonRate(){
        let total = this.attended + this.abandons + this.expired;
        this.abandon_rate = 0;
        if (total > 0) {
            this.abandon_rate = (this.abandons / total * 100).toFixed(1);
        }
    }

    updateWaitAvg(){
        let avg = 0;
        if (this.attended > 0) {
            avg = this.total_wait_time / this.attended;
        }
        this.wait_avg = avg.toFixed(1) + gettext(' segundos');
    }

    updateTarget(){
        if (this.disposition_target > 0){
            this.target = (100 * this.dispositions / this.disposition_target).toFixed(1);
        }

    }

    updateAgentStats(agentStats) {
        this.agentes_online = agentStats.agentes_online;
        this.agentes_llamada = agentStats.agentes_llamada;
        this.agentes_pausa = agentStats.agentes_pausa;
        this.agentes_ready = this.agentes_online - this.agentes_llamada - this.agentes_pausa;
    }

    updateCallMetric(event_data) {
        switch (event_data.field) {
        case 'expired':
            this.expired += 1;
            break;
        case 'attended':
            this.attended += 1;
            this.total_wait_time += Number(event_data.wait_time);
            this.updateWaitAvg();
            break;
        case 'abandons':
            this.abandons += 1;
            this.total_abandon_time += Number(event_data.time);
            this.updateAbandonAvg();
            this.updateAbandonRate();
            break;
        case 'dispositions':{
            const delta = event_data.delta || 1;
            this.dispositions = Number(this.dispositions) + delta;
            this.updateTarget();
            break;
        }
        case 'queue_size':
            this.queue_size = Number(event_data.size);
            break;
        default:
            break;
        }
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
                'agentes_online': 0,
                'agentes_llamada': 0,
                'agentes_pausa': 0
            };
            Object.values(this.agentList).forEach(agent => {
                if (agent.campanas.includes(campaign) && agent.status != '') {
                    stats[campaign]['agentes_online']++;
                    if (agent.status.indexOf('PAUSE') == 0) {
                        stats[campaign]['agentes_pausa']++;
                    } else if (agent.status.indexOf('ONCALL') == 0 || agent.status.indexOf('DIALING') == 0) {
                        stats[campaign]['agentes_llamada']++;
                    }
                }
            });
        });
        return stats;
    }

    updateAgent(newAgentData) {
        const agentId = newAgentData.id;
        if (agentId == undefined){
            return;
        }
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

var agents = new Agents();
