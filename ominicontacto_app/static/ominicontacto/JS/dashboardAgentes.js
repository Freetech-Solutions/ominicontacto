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

/* global gettext ReconnectingWebSocket Urls */

(function() {
    'use strict';

    var SUBSCRIBE_CONFIRMATION_MESSAGE = 'Subscribed!';
    var TASK_ID = 'dashboard1';

    function formatSecondsToHMS(seconds) {
        if (seconds === undefined || seconds === null || isNaN(seconds)) {
            return '00:00:00';
        }
        var s = Math.max(0, Math.floor(Number(seconds)));
        var h = Math.floor(s / 3600);
        var m = Math.floor((s % 3600) / 60);
        var sec = s % 60;
        return (h < 10 ? '0' : '') + h + ':' +
               (m < 10 ? '0' : '') + m + ':' +
               (sec < 10 ? '0' : '') + sec;
    }

    function parseJsonSafe(value, fallback) {
        if (value === undefined || value === null || value === '') {
            return fallback;
        }
        if (typeof value !== 'string') {
            return value;
        }
        try {
            return JSON.parse(value);
        } catch (e) {
            return fallback;
        }
    }

    var availabilityChart = null;

    function ensureChart() {
        var canvas = document.getElementById('availabilityChart');
        if (!canvas || typeof Chart === 'undefined') {
            return;
        }
        if (availabilityChart) {
            return;
        }
        availabilityChart = new Chart(canvas.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: ['Ready (0%)', 'ACW (0%)', gettext('Pausa') + ' (0%)', gettext('Conversación') + ' (0%)'],
                datasets: [{
                    data: [0, 0, 0, 0],
                    backgroundColor: ['#0f9d58', '#4285f4', '#ff5722', '#aa00ff'],
                    borderWidth: 0,
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '75%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { usePointStyle: true, padding: 20, boxWidth: 8 }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return ' ' + context.label;
                            }
                        }
                    }
                }
            }
        });
    }

    function updateChart(readyPct, acwPct, pausePct, talkPct) {
        if (!availabilityChart) {
            ensureChart();
        }
        if (availabilityChart) {
            availabilityChart.data.labels = [
                'Ready (' + (readyPct || 0) + '%)',
                'ACW (' + (acwPct || 0) + '%)',
                gettext('Pausa') + ' (' + (pausePct || 0) + '%)',
                gettext('Conversación') + ' (' + (talkPct || 0) + '%)'
            ];
            availabilityChart.data.datasets[0].data = [
                readyPct || 0,
                acwPct || 0,
                pausePct || 0,
                talkPct || 0
            ];
            availabilityChart.update();
        }
    }

    function updateUI(data) {
        var sessionDisplay = data.session_display || formatSecondsToHMS(data.session_seconds);
        var conectadas = parseJsonSafe(data.conectadas, { total: 0, entrantes: 0, salientes: 0 });
        var venta = parseJsonSafe(data.venta, { total: 0, observadas: 0 });
        var total = conectadas.total || 0;
        var entrantes = conectadas.entrantes || 0;
        var salientes = conectadas.salientes || 0;
        var gestiones = venta.total || 0;
        var talkSeconds = parseFloat(data.talk_seconds) || 0;
        var avgTalkSeconds = parseFloat(data.avg_talk_seconds) || 0;
        var transferIn = parseInt(data.transfer_in, 10) || 0;
        var transferOut = parseInt(data.transfer_out, 10) || 0;
        var holdSeconds = parseInt(data.hold_seconds, 10) || 0;
        var whatsappTotal = parseInt(data.whatsapp_total, 10) || 0;
        var whatsappEntrantes = parseInt(data.whatsapp_entrantes, 10) || 0;
        var whatsappSalientes = parseInt(data.whatsapp_salientes, 10) || 0;

        var sessionEl = document.getElementById('session-display');
        if (sessionEl) sessionEl.textContent = sessionDisplay;

        var gestionesEl = document.getElementById('gestiones-value');
        if (gestionesEl) gestionesEl.textContent = gestiones;

        var readyEl = document.getElementById('ready-display');
        if (readyEl) readyEl.textContent = formatSecondsToHMS(data.ready_seconds);
        var acwEl = document.getElementById('acw-display');
        if (acwEl) acwEl.textContent = formatSecondsToHMS(data.acw_seconds);
        var pauseEl = document.getElementById('pause-display');
        if (pauseEl) pauseEl.textContent = formatSecondsToHMS(data.pause_seconds);

        var totalInterEl = document.getElementById('total-interacciones');
        if (totalInterEl) totalInterEl.textContent = total;
        var inboundEl = document.getElementById('inbound-count');
        if (inboundEl) inboundEl.textContent = entrantes;
        var outboundEl = document.getElementById('outbound-count');
        if (outboundEl) outboundEl.textContent = salientes;

        var whatsappTotalEl = document.getElementById('whatsapp-total');
        if (whatsappTotalEl) whatsappTotalEl.textContent = whatsappTotal;
        var whatsappInboundEl = document.getElementById('whatsapp-inbound-count');
        if (whatsappInboundEl) whatsappInboundEl.textContent = whatsappEntrantes;
        var whatsappOutboundEl = document.getElementById('whatsapp-outbound-count');
        if (whatsappOutboundEl) whatsappOutboundEl.textContent = whatsappSalientes;

        var talkEl = document.getElementById('talk-time');
        if (talkEl) talkEl.textContent = formatSecondsToHMS(talkSeconds);
        var attEl = document.getElementById('att-value');
        if (attEl) attEl.textContent = formatSecondsToHMS(avgTalkSeconds);

        var transferTotalEl = document.getElementById('transferencias-total');
        if (transferTotalEl) transferTotalEl.textContent = transferIn + transferOut;
        var transferInEl = document.getElementById('transfer-in');
        if (transferInEl) transferInEl.textContent = transferIn;
        var transferOutEl = document.getElementById('transfer-out');
        if (transferOutEl) transferOutEl.textContent = transferOut;

        var holdEl = document.getElementById('hold-time');
        if (holdEl) holdEl.textContent = formatSecondsToHMS(holdSeconds);

        updateChart(
            parseFloat(data.ready_pct) || 0,
            parseFloat(data.acw_pct) || 0,
            parseFloat(data.pause_pct) || 0,
            parseFloat(data.talk_pct) || 0
        );

        updateLogsTable(data.logs);
    }

    function updateLogsTable(logsData) {
        var tbody = document.getElementById('logs-tbody');
        if (!tbody) return;

        var items = [];
        if (logsData) {
            if (typeof logsData === 'string') {
                try {
                    items = JSON.parse(logsData);
                } catch (e) {
                    items = [];
                }
            } else if (Array.isArray(logsData)) {
                items = logsData;
            } else if (logsData && Array.isArray(logsData.values)) {
                items = logsData.values;
            }
        }

        if (items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 2rem;">' +
                gettext('Sin registros por el momento.') + '</td></tr>';
            return;
        }

        var html = '';
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            var channel = (item.channel || 'VOICE').toUpperCase();
            var channelLabel = channel === 'WHATSAPP' ? gettext('WhatsApp') : gettext('Voz');
            var phone = (item.phone || '').toString();
            var dataStr = (item.data || '').toString();
            var engaged = item.engaged;
            var engagedText = engaged ? gettext('Sí') : gettext('No');
            var engagedClass = engaged ? 'yes' : 'no';
            var callDisposition = (item.callDisposition || '').toString();
            var comments = (item.comments || '').toString();
            var audit = (item.audit || '').toString();
            var campanaId = item.campana_id;
            var tipoCampana = item.tipo_campana;
            var contactoId = item.contacto_id;
            var actions = item.actions;

            var phoneCell = '<span>' + escapeHtml(phone) + '</span>';
            if (campanaId !== undefined && tipoCampana !== undefined && contactoId !== undefined && phone) {
                phoneCell = '<button type="button" class="btn btn-sm btn-outline-primary btn-phone" ' +
                    'data-campana-id="' + escapeHtml(String(campanaId)) + '" ' +
                    'data-tipo-campana="' + escapeHtml(String(tipoCampana)) + '" ' +
                    'data-contacto-id="' + escapeHtml(String(contactoId)) + '" ' +
                    'data-phone="' + escapeHtml(phone) + '">' + escapeHtml(phone) + '</button>';
            }

            var actionsHtml = '';
            if (actions && typeof actions === 'object') {
                if (typeof Urls !== 'undefined') {
                    if (actions.campanaId !== undefined && actions.contactoId !== undefined) {
                        var urlCalif = Urls.calificacion_cliente_actualiza_desde_reporte(
                            actions.campanaId, actions.contactoId);
                        actionsHtml += '<a class="logs-action-link" href="' + escapeHtml(urlCalif) + '">' +
                            gettext('Call disposition') + '</a> ';
                    }
                    if (actions.gestionId !== undefined && actions.calificacionId !== undefined) {
                        var urlVenta = Urls.formulario_venta(actions.calificacionId);
                        actionsHtml += '<a class="logs-action-link" href="' + escapeHtml(urlVenta) + '">' +
                            gettext('Engaged') + '</a>';
                    }
                }
            }

            html += '<tr>' +
                '<td>' + escapeHtml(channelLabel) + '</td>' +
                '<td>' + phoneCell + '</td>' +
                '<td>' + escapeHtml(dataStr) + '</td>' +
                '<td><span class="badge-engaged ' + engagedClass + '">' + escapeHtml(engagedText) + '</span></td>' +
                '<td>' + escapeHtml(callDisposition) + '</td>' +
                '<td>' + escapeHtml(comments) + '</td>' +
                '<td>' + escapeHtml(audit) + '</td>' +
                '<td class="actions-links">' + actionsHtml + '</td>' +
                '</tr>';
        }
        tbody.innerHTML = html;

        tbody.querySelectorAll('.btn-phone[data-campana-id]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var campanaId = this.getAttribute('data-campana-id');
                var tipoCampana = this.getAttribute('data-tipo-campana');
                var contactoId = this.getAttribute('data-contacto-id');
                var phone = this.getAttribute('data-phone');
                makeClick2Call(campanaId, tipoCampana, contactoId, phone, 'agendas');
            });
        });
    }

    function escapeHtml(text) {
        if (!text) return '';
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function makeClick2Call(campaignId, campaignType, contactId, phone, callType) {
        var target = (window.parent && window.parent !== window) ? window.parent : window;
        if (target && typeof target.click2call !== 'undefined' && typeof target.click2call.call_contact === 'function') {
            target.click2call.call_contact(campaignId, campaignType, contactId, phone, callType);
        }
    }

    function showDashboard() {
        var waiting = document.getElementById('waiting-card');
        var content = document.getElementById('dashboard-content');
        if (waiting) waiting.style.display = 'none';
        if (content) content.style.display = 'block';
    }

    function init() {
        var agenteIdInput = document.getElementById('agente_id');
        if (!agenteIdInput || !agenteIdInput.value) {
            return;
        }

        var cached = sessionStorage.getItem('dataDashboard');
        if (cached) {
            try {
                var parsed = JSON.parse(cached);
                if (parsed && parsed.core) {
                    showDashboard();
                    updateUI(parsed.core);
                }
            } catch (e) {
                /* ignore */
            }
        }

        var url = 'wss://' + window.location.host +
            '/consumers/reporte_agente/estadisticas_dia_actual/' +
            agenteIdInput.value + '/' + TASK_ID;

        var rws = new ReconnectingWebSocket(url, [], {
            connectionTimeout: 8000,
            maxReconnectionDelay: 3000,
            minReconnectionDelay: 1000,
        });

        rws.addEventListener('message', function(e) {
            if (e.data === SUBSCRIBE_CONFIRMATION_MESSAGE) {
                return;
            }
            var data;
            try {
                data = JSON.parse(e.data);
            } catch (err) {
                return;
            }

            showDashboard();
            updateUI(data);

            sessionStorage.setItem('dataDashboard', JSON.stringify({ core: data }));
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
