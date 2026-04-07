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

/* global Alpine Chart ReconnectingWebSocket Urls gettext */

(function() {
    'use strict';

    var STORAGE_KEY = 'dataDashboardAgenteV2';
    var SUBSCRIBE_CONFIRMATION_MESSAGE = 'Subscribed!';
    var TASK_ID = 'dashboard1';

    function translate(text) {
        if (typeof gettext === 'function') {
            return gettext(text);
        }
        return text;
    }

    function parseJsonSafe(value, fallbackValue) {
        if (value === undefined || value === null || value === '') {
            return fallbackValue;
        }
        if (typeof value !== 'string') {
            return value;
        }
        try {
            return JSON.parse(value);
        } catch (error) {
            return fallbackValue;
        }
    }

    function buildPieChartConfig(labels, values, colors) {
        return {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors,
                    borderColor: '#ffffff',
                    borderWidth: 2,
                    hoverOffset: 10,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '55%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            boxWidth: 12,
                            usePointStyle: true,
                            pointStyle: 'circle',
                        },
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.label + ': ' + context.formattedValue;
                            }
                        }
                    }
                },
            },
        };
    }

    function registerAlpineComponent() {
        Alpine.data('agenteDashboard', function() {
            return {
                core: null,
                mensajeEspera: translate('Calculando estadísticas del agente ...'),
                pausasVisible: false,
                lastUpdate: null,
                rws: null,
                charts: {
                    conectadas: null,
                    pausa: null,
                    venta: null,
                },
                pageUnloadHandler: null,
                cleanupDone: false,

                init: function() {
                    this.loadFromSession();

                    this.$nextTick(function() {
                        if (this.core) {
                            this.ensureCharts();
                            this.updateCharts();
                        }
                    }.bind(this));

                    this.connectWebSocket();

                    this.pageUnloadHandler = this.cleanup.bind(this);
                    window.addEventListener('beforeunload', this.pageUnloadHandler);
                    window.addEventListener('pagehide', this.pageUnloadHandler);
                },

                loadFromSession: function() {
                    var cachedData = parseJsonSafe(sessionStorage.getItem(STORAGE_KEY), null);
                    if (!cachedData || !cachedData.core) {
                        return;
                    }

                    this.core = cachedData.core;
                    this.lastUpdate = cachedData.lastUpdate || null;
                    this.pausasVisible = Boolean(cachedData.pausasVisible);
                },

                persistSession: function() {
                    var payload = {
                        core: this.core,
                        lastUpdate: this.lastUpdate,
                        pausasVisible: this.pausasVisible,
                    };
                    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
                },

                connectWebSocket: function() {
                    var agenteIdInput = document.getElementById('agente_id');
                    if (!agenteIdInput || !agenteIdInput.value) {
                        return;
                    }

                    var url = 'wss://' + window.location.host +
                        '/consumers/reporte_agente/estadisticas_dia_actual/' +
                        agenteIdInput.value + '/' + TASK_ID;

                    this.rws = new ReconnectingWebSocket(url, [], {
                        connectionTimeout: 8000,
                        maxReconnectionDelay: 3000,
                        minReconnectionDelay: 1000,
                    });

                    this.rws.addEventListener('message', function(event) {
                        this.handleMessage(event.data);
                    }.bind(this));
                },

                handleMessage: function(rawMessage) {
                    if (rawMessage === SUBSCRIBE_CONFIRMATION_MESSAGE) {
                        return;
                    }

                    var payload = parseJsonSafe(rawMessage, null);
                    if (!payload) {
                        return;
                    }

                    var conectadasData = parseJsonSafe(payload.conectadas, {});
                    var pausaData = parseJsonSafe(payload.tiempos, {});
                    var ventaData = parseJsonSafe(payload.venta, {});
                    var logsData = parseJsonSafe(payload.logs, []);
                    var pausasInfo = parseJsonSafe(payload.pausas, []);

                    if (!Array.isArray(logsData)) {
                        logsData = [];
                    }
                    if (!Array.isArray(pausasInfo)) {
                        pausasInfo = [];
                    }

                    this.core = {
                        conectadas: {
                            statistics: conectadasData.total || 0,
                            title: translate('Llamadas conectadas'),
                            labels: [translate('Salientes'), translate('Entrantes')],
                            values: [conectadasData.salientes || 0, conectadasData.entrantes || 0],
                        },
                        pausa: {
                            statistics: pausaData.tiempo_pausa || 0,
                            title: translate('Tiempos de pausa'),
                            labels: [translate('Productiva'), translate('Recreativa'), translate('Sesión')],
                            values: [
                                pausaData.pausa_productiva || 0,
                                pausaData.pausa_recreativa || 0,
                                pausaData.sesion || 0,
                            ],
                        },
                        venta: {
                            statistics: ventaData.total || 0,
                            title: translate('Ventas'),
                            labels: [translate('Realizadas'), translate('Observadas')],
                            values: [ventaData.total || 0, ventaData.observadas || 0],
                        },
                        logs: {
                            values: logsData,
                        },
                        pausas: {
                            valores_pausas: pausasInfo,
                        },
                    };

                    this.lastUpdate = new Date().toLocaleTimeString();

                    this.$nextTick(function() {
                        this.ensureCharts();
                        this.updateCharts();
                    }.bind(this));

                    this.persistSession();
                },

                ensureCharts: function() {
                    if (!this.core || typeof Chart !== 'function') {
                        return;
                    }

                    if (!this.charts.conectadas) {
                        var conectadasCanvas = document.getElementById('chartConectadas');
                        if (conectadasCanvas) {
                            this.charts.conectadas = new Chart(
                                conectadasCanvas.getContext('2d'),
                                buildPieChartConfig(
                                    this.core.conectadas.labels,
                                    this.core.conectadas.values,
                                    ['#4f46e5', '#22c55e']
                                )
                            );
                        }
                    }

                    if (!this.charts.pausa) {
                        var pausaCanvas = document.getElementById('chartPausa');
                        if (pausaCanvas) {
                            this.charts.pausa = new Chart(
                                pausaCanvas.getContext('2d'),
                                buildPieChartConfig(
                                    this.core.pausa.labels,
                                    this.core.pausa.values,
                                    ['#0ea5e9', '#f59e0b', '#64748b']
                                )
                            );
                        }
                    }

                    if (!this.charts.venta) {
                        var ventaCanvas = document.getElementById('chartVenta');
                        if (ventaCanvas) {
                            this.charts.venta = new Chart(
                                ventaCanvas.getContext('2d'),
                                buildPieChartConfig(
                                    this.core.venta.labels,
                                    this.core.venta.values,
                                    ['#16a34a', '#ef4444']
                                )
                            );
                        }
                    }
                },

                updateChartData: function(chart, labels, values) {
                    if (!chart) {
                        return;
                    }
                    chart.data.labels = labels;
                    chart.data.datasets[0].data = values;
                    chart.update();
                },

                updateCharts: function() {
                    if (!this.core) {
                        return;
                    }

                    this.updateChartData(
                        this.charts.conectadas,
                        this.core.conectadas.labels,
                        this.core.conectadas.values
                    );
                    this.updateChartData(
                        this.charts.pausa,
                        this.core.pausa.labels,
                        this.core.pausa.values
                    );
                    this.updateChartData(
                        this.charts.venta,
                        this.core.venta.labels,
                        this.core.venta.values
                    );
                },

                togglePausas: function() {
                    this.pausasVisible = !this.pausasVisible;
                    this.persistSession();
                },

                metricTitle: function(metricKey) {
                    if (!this.core || !this.core[metricKey]) {
                        return '';
                    }
                    return this.core[metricKey].title || '';
                },

                metricStat: function(metricKey) {
                    if (!this.core || !this.core[metricKey]) {
                        return 0;
                    }
                    return this.core[metricKey].statistics || 0;
                },

                pauseItems: function() {
                    if (!this.core || !this.core.pausas) {
                        return [];
                    }
                    if (!Array.isArray(this.core.pausas.valores_pausas)) {
                        return [];
                    }
                    return this.core.pausas.valores_pausas;
                },

                logItems: function() {
                    if (!this.core || !this.core.logs) {
                        return [];
                    }
                    if (!Array.isArray(this.core.logs.values)) {
                        return [];
                    }
                    return this.core.logs.values;
                },

                makeClick2Call: function(campaignId, campaignType, contactId, phone, callType) {
                    if (window.parent && window.parent.hasOwnProperty('click2call')) {
                        window.parent.click2call.call_contact(
                            campaignId, campaignType, contactId, phone, callType
                        );
                    }
                },

                urlFormularioVenta: function(calificacionId) {
                    if (!calificacionId || typeof Urls === 'undefined') {
                        return '#';
                    }
                    return Urls.formulario_venta(calificacionId);
                },

                urlCalificacion: function(campanaId, contactoId) {
                    if (!campanaId || !contactoId || typeof Urls === 'undefined') {
                        return '#';
                    }
                    return Urls.calificacion_cliente_actualiza_desde_reporte(campanaId, contactoId);
                },

                cleanup: function() {
                    if (this.cleanupDone) {
                        return;
                    }
                    this.cleanupDone = true;

                    if (this.rws) {
                        try {
                            this.rws.close();
                        } catch (error) {
                            // noop
                        }
                        this.rws = null;
                    }

                    if (this.charts.conectadas) {
                        this.charts.conectadas.destroy();
                        this.charts.conectadas = null;
                    }
                    if (this.charts.pausa) {
                        this.charts.pausa.destroy();
                        this.charts.pausa = null;
                    }
                    if (this.charts.venta) {
                        this.charts.venta.destroy();
                        this.charts.venta = null;
                    }

                    if (this.pageUnloadHandler) {
                        window.removeEventListener('beforeunload', this.pageUnloadHandler);
                        window.removeEventListener('pagehide', this.pageUnloadHandler);
                        this.pageUnloadHandler = null;
                    }
                },
            };
        });
    }

    if (window.Alpine) {
        registerAlpineComponent();
    } else {
        document.addEventListener('alpine:init', registerAlpineComponent);
    }
})();
