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
var table_outbounds;
var table_data = [];

var rws;

$(function() {
    campaigns = JSON.parse(document.getElementById('campaigns-data').textContent);
    createDataTable();
    connectToDataChannel();
});

function connectToDataChannel(){
    const url = `wss://${window.location.host}/channels/supervision/outbound`;
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
        let camp_data = initial_data[camp_id];
        camp_data.name = campaigns[camp_id].name;
        updateTarget(camp_id, camp_data);
        table_data.push(camp_data);
    }
    table_outbounds.clear();
    table_outbounds.rows.add(table_data).draw();
}

function updateTable(data){
    if (data.type == 'update' && data.args.OUT != undefined){
        let camp_id = data.args.OUT.campaign_id;
        let field = data.args.OUT.field;
        let camp_name = campaigns[camp_id].name;
        let row = table_outbounds.row((idx, data) => data.name === camp_name);
        let row_data=row.data();
        if (field != 'dispositions'){
            row_data[field] = Number(row_data[field]) + 1;
        } else{
            const delta = data.args.OUT.delta || 1;
            row_data[field] = Number(row_data[field]) + delta;
            updateTarget(camp_id, row_data);
        }
        row.data(row_data).draw();
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

function createDataTable() {
    table_outbounds = $('#tableSalientes').DataTable({
        data: table_data,
        columns: [
            { 'data': 'name' },
            { 'data': 'dialed' },
            { 'data': 'attended' },
            { 'data': 'not_attended' },
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
