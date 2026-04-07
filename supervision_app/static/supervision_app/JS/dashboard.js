# -*- coding: utf-8 -*-
document.addEventListener('alpine:init', () => {
    Alpine.data('dashboardCamp', () => ({
        filters: {
            estado: '',
            tipo: '',
            fecha_desde: '',
            fecha_hasta: '',
        },
        metrics: {
            total: 0,
            por_estado: [],
            por_tipo: [],
        },
        list: {
            total: 0,
            items: [],
        },
        loading: false,
        error: null,
        lastUpdated: null,
        pollingId: null,
        pollingIntervalMs: 30000,

        init() {
            const initialMetrics = window.DASHBOARD_CAMP_INITIAL_METRICS;
            if (initialMetrics) {
                this.metrics = initialMetrics;
            }
            this.fetchAll();
            this.startPolling();
        },

        buildQuery() {
            const params = new URLSearchParams();
            Object.keys(this.filters).forEach((key) => {
                const value = this.filters[key];
                if (value) {
                    params.set(key, value);
                }
            });
            return params.toString();
        },

        async fetchMetrics() {
            const query = this.buildQuery();
            const url = query ? `${window.DASHBOARD_CAMP_METRICS_URL}?${query}` : window.DASHBOARD_CAMP_METRICS_URL;
            const response = await fetch(url, { credentials: 'same-origin' });
            if (!response.ok) {
                throw new Error('Error al cargar métricas');
            }
            return response.json();
        },

        async fetchList() {
            const query = this.buildQuery();
            const url = query ? `${window.DASHBOARD_CAMP_LIST_URL}?${query}` : window.DASHBOARD_CAMP_LIST_URL;
            const response = await fetch(url, { credentials: 'same-origin' });
            if (!response.ok) {
                throw new Error('Error al cargar listado');
            }
            return response.json();
        },

        async fetchAll() {
            this.loading = true;
            this.error = null;
            try {
                const [metrics, list] = await Promise.all([
                    this.fetchMetrics(),
                    this.fetchList(),
                ]);
                this.metrics = metrics;
                this.list = list;
                this.lastUpdated = new Date().toLocaleString();
            } catch (error) {
                this.error = error.message || 'Error inesperado';
            } finally {
                this.loading = false;
            }
        },

        applyFilters() {
            this.fetchAll();
        },

        clearFilters() {
            this.filters = {
                estado: '',
                tipo: '',
                fecha_desde: '',
                fecha_hasta: '',
            };
            this.fetchAll();
        },

        startPolling() {
            if (this.pollingId) {
                clearInterval(this.pollingId);
            }
            this.pollingId = setInterval(() => {
                this.fetchAll();
            }, this.pollingIntervalMs);
        },
    }));
});
