function registerContactCenterDashboard() {
    Alpine.data('panelDialerDashboard', () => ({
        // Estado del componente (preselección desde URL supervision/<id_camp>/panel-general/)
        campaignId: (typeof window !== 'undefined' && window.PANEL_DIALER_INITIAL_CAMPAIGN_ID != null) ? String(window.PANEL_DIALER_INITIAL_CAMPAIGN_ID) : '',
        // Panel Dialer: sin gráficos Inbound/Outbound
        data: {
            agentes: {
                logueados: 0,
                ready: 0,
                oncall: 0,
                paused: 0,
                onconfer: 0,
                voicebot: 0,
                lista_agentes: [],
            },
            llamadas: {
                call_times: {
                    aht: 0,
                    mas_extensa: 0,
                    gestion_positiva: 0,
                },
            },
            llamadas_discando: 0,
            estado_discador: {
                pending_initial: 0,
                pending_retries: 0,
                finalized_no_contact: 0,
                contacted_successfully: 0,
                attempted_calls: 0,
                answered_pstn: 0,
                answered_agent: 0,
                conectadas_no_atendidas: 0,
                estimadas: 0,
                contactos_llamados: 0,
                campana_nombre: '',
                campana_estado: '',
                status: [],
            },
            pacing: null,
        },
        show_pacing_section: false,
        loading: false,
        lastUpdate: null,
        initialized: false,
        filteredAgentes: [], // Lista filtrada de agentes (solo estados READY, ONCALL, RINGING, PAUSED)
        listaBots: [],      // Lista de agentes voicebot de la campaña (nombre, llamadas_activas)
        actionLoading: false,
        messageModalOpen: false,
        messageModalRecipientId: '',
        messageModalRecipientType: 'agent',
        messageModalText: '',
        charts: {},
        chartsInitialized: {},
        pollingId: null,
        pollingIntervalMs: 5000, // 5 segundos
        statsPollingId: null,
        statsIntervalMs: 30000, // stats ATT/llamadas vía REST (no viajan en el stream)
        agentesMap: {}, // id → fila fusionada (estado vivo del stream + stats REST)
        agentesSocket: null,
        streamEnabled: !!(typeof window !== 'undefined' && window.PANEL_DIALER_AGENTES_STREAM_URL),
        _streamEverConnected: false,
        _streamMessageSeen: 'Stream subscribed!',
        dialerSocket: null,
        dialerWsEnabled: (typeof ReconnectingWebSocket !== 'undefined'),
        _dialerWsConnected: false,
        _dialerWsEverConnected: false,
        _dialerNeedsRestResync: false, // un fetchEstadoDiscador completo tras reconexión WS
        destroyingCharts: false, // Flag para prevenir actualizaciones durante destrucción
        _isPolling: false, // Flag para prevenir solapamiento de requests de polling
        _pollingAbortController: null, // AbortController para cancelar requests en vuelo
        _chartUpdating: {}, // Flags para prevenir actualizaciones concurrentes de gráficos
        previousData: {
            agentes: {
                logueados: 0,
                ready: 0,
                oncall: 0,
                paused: 0,
                onconfer: 0,
                voicebot: 0,
            },
            lista_agentes: [],
            llamadas: {
                call_times: null,
            },
            llamadas_discando: null,
            estado_discador: null,
            pacing: null,
        },

        emptyEstadoDiscador() {
            return {
                pending_initial: 0,
                pending_retries: 0,
                finalized_no_contact: 0,
                contacted_successfully: 0,
                attempted_calls: 0,
                answered_pstn: 0,
                answered_agent: 0,
                conectadas_no_atendidas: 0,
                estimadas: 0,
                contactos_llamados: 0,
                campana_nombre: '',
                campana_estado: '',
                status: [],
            };
        },

        resetEstadoDiscador() {
            this.data.estado_discador = this.emptyEstadoDiscador();
            this.data.llamadas_discando = 0;
            this.data.pacing = null;
            this.show_pacing_section = false;
            this.previousData.estado_discador = JSON.parse(JSON.stringify(this.data.estado_discador));
            this.previousData.llamadas_discando = 0;
            this.previousData.pacing = null;
        },

        campaignName() {
            const names = window.PANEL_DIALER_CAMPAIGN_NAMES || {};
            return names[String(this.campaignId)] || '';
        },


        /**
         * Comparaci?n profunda de objetos/arrays
         * Optimizada con límite de profundidad para prevenir stack overflow
         */
        deepEqual(obj1, obj2, maxDepth = 10, currentDepth = 0) {
            // Early return: comparación por referencia (más rápida)
            if (obj1 === obj2) return true;
            
            // Early return: null/undefined check
            if (obj1 == null || obj2 == null) return false;
            
            // Early return: tipos primitivos
            if (typeof obj1 !== 'object' || typeof obj2 !== 'object') return false;
            
            // Prevenir stack overflow con límite de profundidad
            if (currentDepth >= maxDepth) {
                console.warn('[PanelDialer] deepEqual alcanzó el límite de profundidad, usando comparación por referencia');
                return obj1 === obj2;
            }
            
            // Optimización: comparar arrays primero (más común y más rápido)
            if (Array.isArray(obj1) && Array.isArray(obj2)) {
                if (obj1.length !== obj2.length) return false;
                // Comparación elemento por elemento
                for (let i = 0; i < obj1.length; i++) {
                    if (!this.deepEqual(obj1[i], obj2[i], maxDepth, currentDepth + 1)) {
                        return false;
                    }
                }
                return true;
            }
            
            // Si uno es array y el otro no, no son iguales
            if (Array.isArray(obj1) || Array.isArray(obj2)) return false;
            
            // Comparación de objetos
            const keys1 = Object.keys(obj1);
            const keys2 = Object.keys(obj2);
            
            // Early return: diferente número de claves
            if (keys1.length !== keys2.length) return false;
            
            // Comparar cada clave
            for (const key of keys1) {
                // Early return: clave no existe en obj2
                if (!keys2.includes(key)) return false;
                
                const val1 = obj1[key];
                const val2 = obj2[key];
                
                // Comparación recursiva con incremento de profundidad
                if (!this.deepEqual(val1, val2, maxDepth, currentDepth + 1)) {
                    return false;
                }
            }
            
            return true;
        },

        /**
         * Verifica si un valor ha cambiado comparando con el valor anterior
         */
        hasChanged(path, newValue, oldValue) {
            if (oldValue === undefined) return true; // Primera vez
            if (newValue === oldValue) return false; // Comparaci?n simple para primitivos
            
            // Para objetos y arrays, usar comparaci?n profunda
            if (typeof newValue === 'object' && newValue !== null) {
                return !this.deepEqual(newValue, oldValue);
            }
            
            return newValue !== oldValue;
        },

        /**
         * Función helper para fetch con timeout, retry y manejo robusto de errores
         * @param {string} url - URL a la que hacer la request
         * @param {Object} options - Opciones de fetch (headers, credentials, etc.)
         * @param {number} timeoutMs - Timeout en milisegundos (default: 10000)
         * @param {number} maxRetries - Número máximo de reintentos (default: 2)
         * @param {AbortSignal} signal - AbortSignal para cancelar la request
         * @returns {Promise<Response>} - Response de la request
         */
        async safeFetch(url, options = {}, timeoutMs = 10000, maxRetries = 2, signal = null) {
            let lastError = null;
            
            for (let attempt = 0; attempt <= maxRetries; attempt++) {
                try {
                    // Crear AbortController para timeout
                    const timeoutController = new AbortController();
                    const timeoutId = setTimeout(() => {
                        timeoutController.abort();
                    }, timeoutMs);
                    
                    // Combinar signals si se proporciona uno externo
                    let combinedSignal = timeoutController.signal;
                    if (signal) {
                        // Si hay un signal externo, crear uno combinado
                        const combinedController = new AbortController();
                        signal.addEventListener('abort', () => combinedController.abort());
                        timeoutController.signal.addEventListener('abort', () => combinedController.abort());
                        combinedSignal = combinedController.signal;
                    }
                    
                    // Realizar fetch con timeout
                    const response = await fetch(url, {
                        ...options,
                        signal: combinedSignal,
                    });
                    
                    clearTimeout(timeoutId);
                    
                    // Si la respuesta no es OK, lanzar error
                    if (!response.ok) {
                        throw new Error(`Error HTTP: ${response.status} ${response.statusText}`);
                    }
                    
                    return response;
                    
                } catch (error) {
                    lastError = error;
                    
                    // Si fue cancelado (AbortError), no reintentar
                    if (error.name === 'AbortError') {
                        throw error;
                    }
                    
                    // Si es el último intento, lanzar el error
                    if (attempt === maxRetries) {
                        break;
                    }
                    
                    // Exponential backoff: esperar antes de reintentar
                    const delay = Math.min(1000 * Math.pow(2, attempt), 5000);
                    await new Promise(resolve => setTimeout(resolve, delay));
                    
                    // Log del reintento
                    console.warn(`[PanelDialer] Reintentando fetch (intento ${attempt + 1}/${maxRetries}):`, url);
                }
            }
            
            // Si llegamos aquí, todos los intentos fallaron
            console.error(`[PanelDialer] Error en fetch después de ${maxRetries + 1} intentos:`, lastError);
            throw lastError;
        },

        /**
         * Inicializaci?n del componente
         */
        init() {
            if (this.initialized) {
                console.warn('[PanelDialer] El componente ya está inicializado');
                return;
            }

            this.fetchData().then(() => {
                if (this.streamEnabled) {
                    this.connectAgentesStream();
                    this.startStatsPolling();
                }
                if (this.dialerWsEnabled) {
                    this.connectDialerStatsSocket();
                }
            });

            this.startPolling();

            const cleanupHandler = () => {
                this.cleanup();
            };
            window.addEventListener('beforeunload', cleanupHandler);
            
            const visibilityHandler = () => {
                if (document.hidden) {
                    this.stopPolling();
                    this.stopStatsPolling();
                    this.disconnectDialerStatsSocket();
                } else {
                    this.startPolling();
                    if (this.streamEnabled) {
                        this.startStatsPolling();
                    }
                    if (this.dialerWsEnabled) {
                        this.connectDialerStatsSocket();
                    }
                }
            };
            document.addEventListener('visibilitychange', visibilityHandler);
            
            window.addEventListener('pagehide', cleanupHandler);

            this.initialized = true;
        },

        /**
         * Destruir todos los gr?ficos existentes de forma segura
         * Cancela todas las actualizaciones pendientes antes de destruir
         */
        destroyCharts() {
            this.destroyingCharts = false;
        },

        /**
         * Panel Dialer: sin gráficos
         */
        initCharts() {
        },

        /**
         * Obtener datos del endpoint API (carga inicial completa)
         */
        async fetchData() {
            this.loading = true;
            try {
                const url = window.PANEL_DIALER_DATA_URL || '/supervision/panel-general/data/';
                const params = new URLSearchParams();
                if (this.campaignId) {
                    params.set('campaign_id', this.campaignId);
                }
                const fullUrl = params.toString() ? `${url}?${params.toString()}` : url;

                const response = await this.safeFetch(fullUrl, {
                    credentials: 'same-origin',
                    headers: {
                        'Accept': 'application/json',
                    }
                }, 10000, 2, this._pollingAbortController?.signal);

                const jsonData = await response.json();

                if (jsonData.error) {
                    throw new Error(jsonData.error);
                }

                // Actualizar datos (Estado Discador va por endpoint dedicado)
                this.data = {
                    agentes: {
                        ...this.data.agentes,
                        ...(jsonData.agentes || {}),
                        lista_agentes: jsonData.agentes?.lista_agentes || [],
                    },
                    llamadas: {
                        call_times: (jsonData.llamadas && jsonData.llamadas.call_times) || this.data.llamadas.call_times,
                    },
                    llamadas_discando: this.data.llamadas_discando || 0,
                    estado_discador: this.data.estado_discador || this.emptyEstadoDiscador(),
                    pacing: this.data.pacing,
                };

                // Sembrar mapa vivo de agentes (estado + stats) desde el baseline REST
                this.seedAgentesMapFromLista(this.data.agentes.lista_agentes || []);
                
                // Actualizar lista filtrada de agentes
                this.updateFilteredAgentes();

                // Guardar como valores anteriores para comparaci?n
                this.previousData = {
                    agentes: {
                        logueados: this.data.agentes.logueados,
                        ready: this.data.agentes.ready,
                        oncall: this.data.agentes.oncall,
                        paused: this.data.agentes.paused,
                        onconfer: this.data.agentes.onconfer,
                        voicebot: this.data.agentes.voicebot,
                    },
                    lista_agentes: JSON.parse(JSON.stringify(this.data.agentes.lista_agentes || [])),
                    llamadas: {
                        call_times: JSON.parse(JSON.stringify(this.data.llamadas?.call_times || {})),
                    },
                    llamadas_discando: this.data.llamadas_discando || 0,
                    estado_discador: JSON.parse(JSON.stringify(this.data.estado_discador || {})),
                    pacing: this.data.pacing ? JSON.parse(JSON.stringify(this.data.pacing)) : null,
                };

                // Actualizar timestamp
                if (jsonData.timestamp) {
                    const date = new Date(jsonData.timestamp);
                    this.lastUpdate = date.toLocaleTimeString();
                } else {
                    this.lastUpdate = new Date().toLocaleTimeString();
                }

                // Actualizar gr?ficos
                this.updateCharts();
                await this.fetchEstadoDiscador();

            } catch (error) {
                console.error('Error obteniendo datos del contact center:', error);
                // Mantener datos anteriores en caso de error
            } finally {
                this.loading = false;
            }
        },

        /**
         * Obtener solo m?tricas agregadas de agentes
         */
        async fetchAgentes() {
            try {
                const url = window.PANEL_DIALER_AGENTES_URL || '/supervision/panel-general/data/agentes/';
                const params = new URLSearchParams();
                if (this.campaignId) {
                    params.set('campaign_id', this.campaignId);
                }
                const fullUrl = params.toString() ? `${url}?${params.toString()}` : url;

                const response = await this.safeFetch(fullUrl, {
                    credentials: 'same-origin',
                    headers: {
                        'Accept': 'application/json',
                    }
                }, 10000, 1, this._pollingAbortController?.signal);

                const jsonData = await response.json();

                if (jsonData.error) {
                    throw new Error(jsonData.error);
                }

                // Comparar con valores anteriores
                const newAgentes = {
                    logueados: jsonData.logueados || 0,
                    ready: jsonData.ready || 0,
                    oncall: jsonData.oncall || 0,
                    paused: jsonData.paused || 0,
                    onconfer: jsonData.onconfer || 0,
                    voicebot: jsonData.voicebot || 0,
                };

                let hasChanges = false;
                for (const key in newAgentes) {
                    if (this.hasChanged(key, newAgentes[key], this.previousData.agentes[key])) {
                        hasChanges = true;
                        break;
                    }
                }

                // Solo actualizar si hay cambios
                if (hasChanges) {
                    this.data.agentes = {
                        ...this.data.agentes,
                        ...newAgentes,
                    };
                    this.previousData.agentes = { ...newAgentes };
                    
                    // Actualizar timestamp
                    if (jsonData.timestamp) {
                        const date = new Date(jsonData.timestamp);
                        this.lastUpdate = date.toLocaleTimeString();
                    }
                }

            } catch (error) {
                console.error('Error obteniendo m?tricas de agentes:', error);
            }
        },

        /**
         * Obtener solo lista detallada de agentes
         */
        async fetchAgentesLista() {
            try {
                const url = window.PANEL_DIALER_AGENTES_LISTA_URL || '/supervision/panel-general/data/agentes-lista/';
                const params = new URLSearchParams();
                if (this.campaignId) {
                    params.set('campaign_id', this.campaignId);
                }
                const fullUrl = params.toString() ? `${url}?${params.toString()}` : url;

                const response = await this.safeFetch(fullUrl, {
                    credentials: 'same-origin',
                    headers: {
                        'Accept': 'application/json',
                    }
                }, 10000, 1, this._pollingAbortController?.signal);

                const jsonData = await response.json();

                if (jsonData.error) {
                    throw new Error(jsonData.error);
                }

                const newLista = jsonData.lista_agentes || [];

                // Comparar con lista anterior
                if (this.hasChanged('lista_agentes', newLista, this.previousData.lista_agentes)) {
                    this.previousData.lista_agentes = JSON.parse(JSON.stringify(newLista));

                    if (this.streamEnabled) {
                        // Solo mergear columnas de stats (ATT / llamadas); no tocar estado vivo
                        this.mergeStatsFromLista(newLista);
                    } else {
                        this.data.agentes.lista_agentes = newLista;
                        this.seedAgentesMapFromLista(newLista);
                    }

                    // Actualizar lista filtrada de agentes
                    this.updateFilteredAgentes();
                    
                    // Actualizar timestamp
                    if (jsonData.timestamp) {
                        const date = new Date(jsonData.timestamp);
                        this.lastUpdate = date.toLocaleTimeString();
                    }
                }

            } catch (error) {
                console.error('Error obteniendo lista de agentes:', error);
            }
        },

        /**
         * Estado Discador completo (paridad modal campana_dialer/list)
         */
        async fetchEstadoDiscador() {
            if (!this.campaignId) {
                this.resetEstadoDiscador();
                return;
            }
            try {
                const url = window.PANEL_DIALER_ESTADO_URL || '/supervision/panel-dialer/data/estado-discador/';
                const params = new URLSearchParams();
                params.set('campaign_id', this.campaignId);
                const fullUrl = `${url}?${params.toString()}`;

                const response = await this.safeFetch(fullUrl, {
                    credentials: 'same-origin',
                    headers: {
                        'Accept': 'application/json',
                    }
                }, 10000, 1, this._pollingAbortController?.signal);

                const jsonData = await response.json();
                if (jsonData.error) {
                    throw new Error(jsonData.error);
                }

                const protectLive = this.shouldProtectDialerFromRest();
                const incoming = {
                    ...this.emptyEstadoDiscador(),
                    ...(jsonData.estado_discador || {}),
                };
                // WS puede tener canales/stats más frescos: no pisar esos keys si el socket vive
                if (protectLive) {
                    const live = this.data.estado_discador || {};
                    [
                        'attempted_calls', 'answered_pstn', 'answered_agent',
                        'pending_initial', 'pending_retries',
                        'finalized_no_contact', 'contacted_successfully',
                    ].forEach((key) => {
                        if (live[key] !== undefined && live[key] !== null) {
                            incoming[key] = live[key];
                        }
                    });
                }

                let newDiscando = Number(jsonData.llamadas_discando || 0);
                if (protectLive) {
                    newDiscando = Number(this.data.llamadas_discando || 0);
                }

                this.data.estado_discador = incoming;
                this.data.llamadas_discando = newDiscando;
                this.data.pacing = jsonData.pacing || null;
                this.show_pacing_section = !!jsonData.show_pacing_section;
                this.previousData.estado_discador = JSON.parse(JSON.stringify(incoming));
                this.previousData.llamadas_discando = newDiscando;
                this.previousData.pacing = this.data.pacing
                    ? JSON.parse(JSON.stringify(this.data.pacing))
                    : null;

                if (jsonData.timestamp) {
                    this.lastUpdate = new Date(jsonData.timestamp).toLocaleTimeString();
                }

                if (this._dialerNeedsRestResync) {
                    this._dialerNeedsRestResync = false;
                }
            } catch (error) {
                const isAbort = error.name === 'AbortError' || (typeof DOMException !== 'undefined' && error instanceof DOMException && error.message && String(error.message).toLowerCase().includes('aborted'));
                if (!isAbort) {
                    console.error('Error obteniendo estado del discador:', error);
                }
            }
        },

        /**
         * Obtener solo métricas de tiempos de llamada (AHT / gestión)
         */
        async fetchLlamadas() {
            try {
                const url = window.PANEL_DIALER_LLAMADAS_URL || '/supervision/panel-general/data/llamadas/';
                const params = new URLSearchParams();
                if (this.campaignId) {
                    params.set('campaign_id', this.campaignId);
                }
                const fullUrl = params.toString() ? `${url}?${params.toString()}` : url;

                const response = await this.safeFetch(fullUrl, {
                    credentials: 'same-origin',
                    headers: {
                        'Accept': 'application/json',
                    }
                }, 10000, 1, this._pollingAbortController?.signal);

                const jsonData = await response.json();

                if (jsonData.error) {
                    throw new Error(jsonData.error);
                }

                const newCallTimes = jsonData.call_times || {};
                if (this.hasChanged('call_times', newCallTimes, this.previousData.llamadas.call_times)) {
                    this.data.llamadas = {
                        call_times: newCallTimes,
                    };
                    this.previousData.llamadas = {
                        call_times: JSON.parse(JSON.stringify(newCallTimes)),
                    };
                    if (jsonData.timestamp) {
                        const date = new Date(jsonData.timestamp);
                        this.lastUpdate = date.toLocaleTimeString();
                    }
                }

            } catch (error) {
                // No loguear como error el abort esperado al desmontar o cerrar (stopPolling -> abort)
                const isAbort = error.name === 'AbortError' || (typeof DOMException !== 'undefined' && error instanceof DOMException && error.message && String(error.message).toLowerCase().includes('aborted'));
                if (!isAbort) {
                    console.error('Error obteniendo m?tricas de llamadas:', error);
                }
            }
        },

        /**
         * Obtener lista de bots (agentes voicebot) de la campaña
         */
        async fetchBotsCampana() {
            if (!this.campaignId) {
                this.listaBots = [];
                return;
            }
            try {
                const url = window.PANEL_DIALER_BOTS_CAMPANA_URL || '/supervision/panel-general/data/bots-campana/';
                const params = new URLSearchParams();
                params.set('campaign_id', this.campaignId);
                const fullUrl = `${url}?${params.toString()}`;

                const response = await this.safeFetch(fullUrl, {
                    credentials: 'same-origin',
                    headers: {
                        'Accept': 'application/json',
                    }
                }, 10000, 1, this._pollingAbortController?.signal);

                const jsonData = await response.json();

                if (jsonData.error) {
                    throw new Error(jsonData.error);
                }

                this.listaBots = jsonData.bots || [];
            } catch (error) {
                const isAbort = error.name === 'AbortError' || (typeof DOMException !== 'undefined' && error instanceof DOMException && error.message && String(error.message).toLowerCase().includes('aborted'));
                if (!isAbort) {
                    console.error('Error obteniendo bots de la campaña:', error);
                }
                this.listaBots = [];
            }
        },

        updateCharts() {
            // Panel Dialer: sin gráficos
        },

        isChartReady() {
            return false;
        },

        safeUpdateChart() {
        },

        updateChartsSelective() {
        },

                /**
         * Iniciar polling para actualizar datos peri?dicamente
         */
        startPolling() {
            // Limpiar polling anterior si existe
            if (this.pollingId) {
                clearInterval(this.pollingId);
                this.pollingId = null;
            }
            
            // Cancelar requests pendientes si existen
            if (this._pollingAbortController) {
                this._pollingAbortController.abort();
            }

            // Iniciar nuevo polling - llamar a las funciones separadas
            this.pollingId = setInterval(() => {
                // Prevenir solapamiento: si ya hay un polling en curso, saltar esta iteración
                if (this._isPolling) {
                    console.warn('[PanelDialer] Polling ya en curso, saltando esta iteración');
                    return;
                }
                
                // Crear nuevo AbortController para este ciclo de polling
                this._pollingAbortController = new AbortController();
                this._isPolling = true;

                // Con stream activo: solo métricas de campaña/bots (agentes vivos van por WS)
                const tasks = this.streamEnabled
                    ? [this.fetchLlamadas(), this.fetchEstadoDiscador(), this.fetchBotsCampana()]
                    : [
                        this.fetchAgentes(),
                        this.fetchAgentesLista(),
                        this.fetchLlamadas(),
                        this.fetchEstadoDiscador(),
                        this.fetchBotsCampana(),
                    ];
                
                // Ejecutar las funciones en paralelo
                Promise.all(tasks).catch(error => {
                    // Solo loguear si no fue cancelado intencionalmente
                    if (error.name !== 'AbortError') {
                        console.error('Error en polling:', error);
                    }
                }).finally(() => {
                    // Resetear flag cuando todas las requests terminen
                    this._isPolling = false;
                });
            }, this.pollingIntervalMs);
        },

        /**
         * Detener polling
         */
        stopPolling() {
            if (this.pollingId) {
                clearInterval(this.pollingId);
                this.pollingId = null;
            }
            
            // Cancelar requests pendientes
            if (this._pollingAbortController) {
                this._pollingAbortController.abort();
                this._pollingAbortController = null;
            }
            
            // Resetear flag de polling
            this._isPolling = false;
        },

        /**
         * Polling lento de stats de agentes (ATT / totales) cuando el stream está activo.
         */
        startStatsPolling() {
            this.stopStatsPolling();
            if (!this.streamEnabled) {
                return;
            }
            this.statsPollingId = setInterval(() => {
                this.fetchAgentesLista();
            }, this.statsIntervalMs);
        },

        stopStatsPolling() {
            if (this.statsPollingId) {
                clearInterval(this.statsPollingId);
                this.statsPollingId = null;
            }
        },

        /**
         * Limpiar recursos al desmontar el componente
         */
        cleanup() {
            if (window.contactCenterPhoneController && typeof window.contactCenterPhoneController.is_on_call === 'function' && window.contactCenterPhoneController.is_on_call()) {
                try {
                    window.contactCenterPhoneController.phone.hangUp();
                } catch (e) {
                    console.warn('[PanelDialer] Error al colgar en cleanup:', e);
                }
            }
            this.stopPolling();
            this.stopStatsPolling();
            this.disconnectAgentesStream();
            this.disconnectDialerStatsSocket();
            this.destroyCharts();
            this.initialized = false;
        },

        /**
         * Manejar cambio de campa?a
         */
        onCampaignChange() {
            if (this.streamEnabled) {
                this.updateFilteredAgentes();
            }
            this.resetEstadoDiscador();
            this.fetchData();
            this.fetchBotsCampana();
        },

        /**
         * Formatear tiempo en segundos a formato MM:SS o MMm SSs
         */
        formatTime(seconds) {
            if (!seconds || seconds === 0) {
                return '0s';
            }
            const totalSeconds = Math.floor(seconds);
            const minutes = Math.floor(totalSeconds / 60);
            const secs = totalSeconds % 60;

            if (minutes > 0) {
                return `${minutes}m ${secs.toString().padStart(2, '0')}s`;
            }
            return `${secs}s`;
        },

        /**
         * Formatear n?mero con separadores de miles
         */
        formatNumber(num) {
            if (num === null || num === undefined) {
                return '0';
            }
            return Number(num).toLocaleString('es-ES');
        },

        formatPacingText(value) {
            if (value === null || value === undefined || value === '') {
                return '—';
            }
            return String(value);
        },

        formatPacingNumber(value) {
            if (value === null || value === undefined || value === '') {
                return '—';
            }
            return this.formatNumber(value);
        },

        formatPacingFloat(value, digits) {
            if (value === null || value === undefined || value === '') {
                return '—';
            }
            const n = Number(value);
            if (Number.isNaN(n)) {
                return '—';
            }
            return n.toFixed(digits || 2);
        },

        formatPacingPercent(value) {
            if (value === null || value === undefined || value === '') {
                return '—';
            }
            const n = Number(value);
            if (Number.isNaN(n)) {
                return '—';
            }
            return `${Math.round(n * 100)}%`;
        },

        formatPacingBool(value) {
            if (value === null || value === undefined || value === '') {
                return '—';
            }
            return Number(value) ? 'sí' : 'no';
        },

        /**
         * Obtener clase CSS para el estado del agente
         */
        getAgentStatusClass(status) {
            if (!status) return 'agent-offline';
            const statusUpper = status.toUpperCase();
            if (statusUpper === 'READY') return 'agent-ready';
            if (statusUpper === 'ONCALL') return 'agent-oncall';
            if (statusUpper.includes('RINGING')) return 'agent-ringing';
            if (statusUpper.includes('CONFER')) return 'agent-onconfer';
            if (statusUpper.startsWith('PAUSE')) return 'agent-pause';
            return 'agent-offline';
        },

        /**
         * Obtener clase CSS para el badge de estado
         */
        getStatusBadgeClass(status) {
            if (!status) return 'badge-offline';
            const statusUpper = status.toUpperCase();
            if (statusUpper === 'READY') return 'badge-ready';
            if (statusUpper === 'ONCALL') return 'badge-oncall';
            if (statusUpper.includes('RINGING')) return 'badge-ringing';
            if (statusUpper.includes('CONFER')) return 'badge-onconfer';
            if (statusUpper.startsWith('PAUSE')) return 'badge-pause';
            return 'badge-offline';
        },

        /**
         * Obtener icono para el estado
         */
        getStatusIcon(status) {
            if (!status) return 'fas fa-circle';
            const statusUpper = status.toUpperCase();
            if (statusUpper === 'READY') return 'fas fa-check-circle';
            if (statusUpper === 'ONCALL') return 'fas fa-phone-volume';
            if (statusUpper.includes('RINGING')) return 'fas fa-bell';
            if (statusUpper.includes('CONFER')) return 'fas fa-users';
            if (statusUpper.startsWith('PAUSE')) return 'fas fa-pause-circle';
            return 'fas fa-circle';
        },

        /**
         * Formatear timestamp
         */
        formatTimestamp(timestamp) {
            if (!timestamp) return '-';
            try {
                // El timestamp puede venir en diferentes formatos
                // Intentar parsearlo como n?mero (Unix timestamp) o como string
                let date;
                if (typeof timestamp === 'number' || /^\d+$/.test(timestamp)) {
                    // Unix timestamp en segundos o milisegundos
                    const ts = parseInt(timestamp);
                    date = ts > 1000000000000 ? new Date(ts) : new Date(ts * 1000);
                } else {
                    date = new Date(timestamp);
                }
                
                if (isNaN(date.getTime())) {
                    return timestamp; // Retornar el valor original si no se puede parsear
                }
                
                const now = new Date();
                const diffMs = now - date;
                const diffSecs = Math.floor(diffMs / 1000);
                const diffMins = Math.floor(diffSecs / 60);
                
                if (diffSecs < 60) {
                    return `Hace ${diffSecs}s`;
                } else if (diffMins < 60) {
                    return `Hace ${diffMins}m`;
                } else {
                    return date.toLocaleTimeString('es-ES', { 
                        hour: '2-digit', 
                        minute: '2-digit' 
                    });
                }
            } catch (e) {
                return timestamp;
            }
        },

        getCsrfToken() {
            const name = 'csrftoken';
            let cookieValue = null;
            if (document.cookie && document.cookie !== '') {
                const cookies = document.cookie.split(';');
                for (let i = 0; i < cookies.length; i++) {
                    const cookie = cookies[i].trim();
                    if (cookie.substring(0, name.length + 1) === (name + '=')) {
                        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                        break;
                    }
                }
            }
            return cookieValue;
        },

        async postJson(url, body) {
            const csrfToken = this.getCsrfToken();
            const headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            };
            if (csrfToken) {
                headers['X-CSRFToken'] = csrfToken;
            }
            const response = await fetch(url, {
                method: 'POST',
                credentials: 'same-origin',
                headers,
                body: JSON.stringify(body),
            });
            if (!response.ok) {
                const errText = await response.text();
                let errMsg = errText;
                try {
                    const errJson = JSON.parse(errText);
                    if (errJson.error) errMsg = errJson.error;
                } catch (_) {}
                throw new Error(errMsg || response.statusText);
            }
            return response;
        },

        async executeSupervisorAction(agentId, action) {
            const baseUrl = window.PANEL_DIALER_API_ACTION_AGENT;
            if (!baseUrl) {
                alert('Configuración de API no disponible.');
                return;
            }
            const url = baseUrl + agentId + '/';
            this.actionLoading = true;
            try {
                await this.postJson(url, { accion: action });
                alert('Acción ejecutada correctamente.');
            } catch (err) {
                alert('Error al ejecutar la acción: ' + (err.message || err));
            } finally {
                this.actionLoading = false;
            }
        },

        async executeSpy(agente) {
            const agentId = agente && (agente.id !== undefined) ? agente.id : agente;
            const agentName = (agente && agente.nombre) ? agente.nombre : ('Agente ' + agentId);
            if (window.contactCenterPhoneController && window.contactCenterPhoneController.is_on_call()) {
                alert('Debe finalizar la acción actual antes de realizar otra.');
                return;
            }
            const url = window.PANEL_DIALER_API_SPY;
            const supervisorId = window.PANEL_DIALER_SUPERVISOR_ID;
            if (!url || !supervisorId) {
                alert('Configuración de supervisor o API no disponible.');
                return;
            }
            window.spied_agent_name = agentName;
            this.actionLoading = true;
            try {
                await this.postJson(url, {
                    supervisor_id: supervisorId,
                    agent_id: String(agentId),
                    whisper: 'none',
                });
                alert('Monitoreo iniciado correctamente.');
            } catch (err) {
                alert('Error al iniciar monitoreo: ' + (err.message || err));
            } finally {
                this.actionLoading = false;
            }
        },

        async executeWhisper(agente) {
            const agentId = agente && (agente.id !== undefined) ? agente.id : agente;
            const agentName = (agente && agente.nombre) ? agente.nombre : ('Agente ' + agentId);
            if (window.contactCenterPhoneController && window.contactCenterPhoneController.is_on_call()) {
                alert('Debe finalizar la acción actual antes de realizar otra.');
                return;
            }
            const url = window.PANEL_DIALER_API_SPY;
            const supervisorId = window.PANEL_DIALER_SUPERVISOR_ID;
            if (!url || !supervisorId) {
                alert('Configuración de supervisor o API no disponible.');
                return;
            }
            window.spied_agent_name = agentName;
            this.actionLoading = true;
            try {
                await this.postJson(url, {
                    supervisor_id: supervisorId,
                    agent_id: String(agentId),
                    whisper: 'both',
                });
                alert('Susurro iniciado correctamente.');
            } catch (err) {
                alert('Error al iniciar susurro: ' + (err.message || err));
            } finally {
                this.actionLoading = false;
            }
        },

        async executeThreeWay(agente) {
            const agentId = agente && (agente.id !== undefined) ? agente.id : agente;
            const agentName = (agente && agente.nombre) ? agente.nombre : ('Agente ' + agentId);
            if (window.contactCenterPhoneController && window.contactCenterPhoneController.is_on_call()) {
                alert('Debe finalizar la acción actual antes de realizar otra.');
                return;
            }
            const url = window.PANEL_DIALER_API_THREE_WAY;
            const supervisorId = window.PANEL_DIALER_SUPERVISOR_ID;
            if (!url || !supervisorId) {
                alert('Configuración de supervisor o API no disponible.');
                return;
            }
            window.spied_agent_name = agentName;
            this.actionLoading = true;
            try {
                await this.postJson(url, {
                    supervisor_id: supervisorId,
                    agent_id: String(agentId),
                });
                alert('Conferencia 3 vías solicitada correctamente.');
            } catch (err) {
                alert('Error al solicitar conferencia: ' + (err.message || err));
            } finally {
                this.actionLoading = false;
            }
        },

        executePause(agente) {
            const status = (agente.STATUS || '').toUpperCase();
            const action = status.indexOf('PAUSE') === 0 ? 'AGENTUNPAUSE' : 'AGENTPAUSE';
            this.executeSupervisorAction(agente.id, action);
        },

        executeLogout(agentId) {
            this.executeSupervisorAction(agentId, 'AGENTLOGOUT');
        },

        openMessageModal(agentId) {
            this.messageModalRecipientId = String(agentId);
            this.messageModalRecipientType = 'agent';
            this.messageModalText = '';
            this.messageModalOpen = true;
        },

        async sendMessage() {
            const url = window.PANEL_DIALER_API_SEND_MESSAGE;
            if (!url) {
                alert('Configuración de API no disponible.');
                return;
            }
            const csrfToken = this.getCsrfToken();
            const params = new URLSearchParams({
                'recipient-id': this.messageModalRecipientId,
                'recipient-type': this.messageModalRecipientType,
                'message-text': this.messageModalText,
            });
            const headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Requested-With': 'XMLHttpRequest',
            };
            if (csrfToken) {
                headers['X-CSRFToken'] = csrfToken;
            }
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers,
                    body: params.toString(),
                });
                if (!response.ok) {
                    const errText = await response.text();
                    let errMsg = errText;
                    try {
                        const errJson = JSON.parse(errText);
                        if (errJson.error) errMsg = errJson.error;
                    } catch (_) {}
                    throw new Error(errMsg || response.statusText);
                }
                this.messageModalOpen = false;
                this.messageModalText = '';
                alert('Mensaje enviado correctamente.');
            } catch (err) {
                alert('Error al enviar mensaje: ' + (err.message || err));
            }
        },

        /**
         * Sembrar agentesMap desde lista REST (baseline o fallback polling).
         */
        seedAgentesMapFromLista(lista) {
            const campaignNames = window.PANEL_DIALER_CAMPAIGN_NAMES || {};
            const selectedName = this.campaignId ? campaignNames[String(this.campaignId)] : null;
            const nextMap = {};
            (lista || []).forEach((agente) => {
                if (agente == null || agente.id == null) {
                    return;
                }
                const id = String(agente.id);
                const prev = this.agentesMap[id] || {};
                let campanas = agente.CAMPANAS || prev.CAMPANAS || [];
                if ((!campanas || (Array.isArray(campanas) && campanas.length === 0)) && selectedName) {
                    // Lista REST filtrada por campaign_id: garantizar pertenencia hasta que llegue el stream
                    campanas = [selectedName];
                }
                nextMap[id] = {
                    ...prev,
                    ...agente,
                    id: agente.id,
                    CAMPANAS: campanas,
                    nombre: agente.nombre || prev.nombre || agente.NAME || (`Agente ${agente.id}`),
                };
            });
            // Si viene del REST filtrado por campaña, conservamos agentes de otras campañas
            // que ya estén en el mapa (estado vivo del stream) y solo actualizamos los recibidos.
            if (this.streamEnabled && Object.keys(this.agentesMap).length > 0) {
                Object.keys(nextMap).forEach((id) => {
                    this.agentesMap[id] = nextMap[id];
                });
            } else {
                this.agentesMap = nextMap;
            }
            // Reasignar para reactividad Alpine
            this.agentesMap = { ...this.agentesMap };
        },

        /**
         * Mergear solo columnas de estadísticas desde REST sin pisar STATUS vivo.
         */
        mergeStatsFromLista(lista) {
            (lista || []).forEach((agente) => {
                if (agente == null || agente.id == null) {
                    return;
                }
                const id = String(agente.id);
                const prev = this.agentesMap[id] || {};
                this.agentesMap[id] = {
                    ...prev,
                    id: agente.id,
                    nombre: agente.nombre || prev.nombre,
                    username: agente.username || prev.username,
                    grupo: agente.grupo || prev.grupo,
                    ANSWERED_TOTAL_CALLS_IN: (agente.ANSWERED_TOTAL_CALLS_IN != null
                        ? agente.ANSWERED_TOTAL_CALLS_IN
                        : (prev.ANSWERED_TOTAL_CALLS_IN != null ? prev.ANSWERED_TOTAL_CALLS_IN : 0)),
                    ANSWERED_TOTAL_CALLS_DIALER: (agente.ANSWERED_TOTAL_CALLS_DIALER != null
                        ? agente.ANSWERED_TOTAL_CALLS_DIALER
                        : (prev.ANSWERED_TOTAL_CALLS_DIALER != null ? prev.ANSWERED_TOTAL_CALLS_DIALER : 0)),
                    ANSWERED_TOTAL_CALLS_MANUAL: (agente.ANSWERED_TOTAL_CALLS_MANUAL != null
                        ? agente.ANSWERED_TOTAL_CALLS_MANUAL
                        : (prev.ANSWERED_TOTAL_CALLS_MANUAL != null ? prev.ANSWERED_TOTAL_CALLS_MANUAL : 0)),
                    ATT: (agente.ATT != null ? agente.ATT : (prev.ATT != null ? prev.ATT : 0)),
                    // Completar campos de presentación si aún no existen
                    CAMPAIGN: prev.CAMPAIGN || agente.CAMPAIGN || '',
                    CONTACT_NUMBER: prev.CONTACT_NUMBER || agente.CONTACT_NUMBER || '',
                    STATUS: prev.STATUS || agente.STATUS || '',
                    TIMESTAMP: prev.TIMESTAMP || agente.TIMESTAMP || '',
                    CAMPANAS: prev.CAMPANAS || agente.CAMPANAS || [],
                    NAME: prev.NAME || agente.NAME || agente.nombre || '',
                    SIP: prev.SIP || agente.SIP || '',
                };
            });
            this.agentesMap = { ...this.agentesMap };
        },

        isVoicebotAgent(agent) {
            const flag = agent && agent.VOICEBOT;
            return flag === '1' || flag === 1 || String(flag).toLowerCase() === 'true';
        },

        parseStreamAgentPayload(element) {
            return JSON.parse(element
                .replaceAll('\'', '"')
                .replaceAll('’', '\'')
                .replaceAll('"[', '[')
                .replaceAll(']"', ']'));
        },

        /**
         * Aplicar batch de eventos del Redis Stream de agentes del supervisor.
         */
        applyStreamAgents(rawData) {
            const data = JSON.parse(rawData);
            const updates = {};
            data.forEach((element) => {
                try {
                    if (typeof element !== 'string') {
                        return;
                    }
                    // Ignorar marcadores de arranque del stream vacío
                    if (element.indexOf('"value": "false"') !== -1 || element.indexOf('\'value\': \'false\'') !== -1) {
                        return;
                    }
                    const agent = this.parseStreamAgentPayload(element);
                    if (this.isVoicebotAgent(agent)) {
                        if (agent.id != null && this.agentesMap[String(agent.id)]) {
                            delete this.agentesMap[String(agent.id)];
                        }
                        return;
                    }
                    const agentId = agent.id;
                    if (agentId == null) {
                        return;
                    }
                    const id = String(agentId);
                    const status = agent.STATUS || '';
                    if (['OFFLINE', ''].includes(String(status).toUpperCase())) {
                        if (this.agentesMap[id]) {
                            delete this.agentesMap[id];
                        }
                        return;
                    }
                    const prev = this.agentesMap[id] || {};
                    const newTs = parseInt(agent.TIMESTAMP, 10) || 0;
                    const prevTs = parseInt(prev.TIMESTAMP, 10) || 0;
                    if (prev.TIMESTAMP && newTs && newTs < prevTs) {
                        return;
                    }
                    updates[id] = {
                        ...prev,
                        id: agentId,
                        STATUS: status,
                        CAMPAIGN: agent.CAMPAIGN || '',
                        CONTACT_NUMBER: agent.CONTACT_NUMBER || '',
                        TIMESTAMP: agent.TIMESTAMP || prev.TIMESTAMP || '',
                        NAME: agent.NAME || prev.NAME || '',
                        nombre: prev.nombre || agent.NAME || (`Agente ${agentId}`),
                        SIP: agent.SIP || prev.SIP || '',
                        PAUSE_ID: agent.PAUSE_ID || prev.PAUSE_ID || '',
                        CAMPANAS: agent.CAMPANAS || prev.CAMPANAS || [],
                        GROUP: agent.GROUP || prev.GROUP || '',
                        grupo: prev.grupo || agent.GROUP || '',
                        VOICEBOT: agent.VOICEBOT,
                        ANSWERED_TOTAL_CALLS_IN: prev.ANSWERED_TOTAL_CALLS_IN || 0,
                        ANSWERED_TOTAL_CALLS_DIALER: prev.ANSWERED_TOTAL_CALLS_DIALER || 0,
                        ANSWERED_TOTAL_CALLS_MANUAL: prev.ANSWERED_TOTAL_CALLS_MANUAL || 0,
                        ATT: prev.ATT || 0,
                    };
                } catch (err) {
                    console.warn('[PanelDialer] Error parseando evento de stream de agentes:', err);
                }
            });
            Object.keys(updates).forEach((id) => {
                this.agentesMap[id] = updates[id];
            });
            this.agentesMap = { ...this.agentesMap };
            this.updateFilteredAgentes();
            this.lastUpdate = new Date().toLocaleTimeString();
        },

        connectAgentesStream() {
            const url = window.PANEL_DIALER_AGENTES_STREAM_URL;
            if (!url || typeof ReconnectingWebSocket === 'undefined') {
                console.warn('[PanelDialer] Stream de agentes no disponible; usando polling REST');
                this.streamEnabled = false;
                this.stopStatsPolling();
                this.startPolling();
                return;
            }
            this.disconnectAgentesStream();
            const rws = new ReconnectingWebSocket(url, [], {
                connectionTimeout: 10000,
                maxReconnectionDelay: 3000,
                minReconnectionDelay: 1000,
            });
            rws.addEventListener('open', () => {
                if (this._streamEverConnected) {
                    // Reconexión: resincronizar baseline REST (stats + estados)
                    this.fetchData();
                }
                this._streamEverConnected = true;
            });
            rws.addEventListener('message', (e) => {
                if (e.data === this._streamMessageSeen || e.data === 'Stream subscribed!') {
                    return;
                }
                try {
                    this.applyStreamAgents(e.data);
                } catch (err) {
                    console.warn('[PanelDialer] Error procesando mensaje de stream:', err);
                }
            });
            rws.addEventListener('error', () => {
                console.warn('[PanelDialer] Error en websocket de agentes');
            });
            this.agentesSocket = rws;
        },

        disconnectAgentesStream() {
            if (this.agentesSocket) {
                try {
                    this.agentesSocket.close();
                } catch (e) {
                    console.warn('[PanelDialer] Error cerrando stream de agentes:', e);
                }
                this.agentesSocket = null;
            }
        },

        /**
         * true cuando el WS discador vive y no hay un resync REST forzado tras reconexión.
         */
        shouldProtectDialerFromRest() {
            return !!(this.dialerWsEnabled && this._dialerWsConnected && !this._dialerNeedsRestResync);
        },

        connectDialerStatsSocket() {
            if (typeof ReconnectingWebSocket === 'undefined') {
                console.warn('[PanelDialer] ReconnectingWebSocket no disponible; Estado Discador por REST');
                this.dialerWsEnabled = false;
                this._dialerWsConnected = false;
                return;
            }
            this.disconnectDialerStatsSocket();
            const url = 'wss://' + window.location.host + '/channels/omnidialer';
            const rws = new ReconnectingWebSocket(url, [], {
                connectionTimeout: 10000,
                maxReconnectionDelay: 3000,
                minReconnectionDelay: 1000,
            });
            rws.addEventListener('open', () => {
                try {
                    rws.send(JSON.stringify({
                        action: 'subscribe',
                        payload: { service: 'dialer_stats' },
                    }));
                } catch (e) {
                    console.warn('[PanelDialer] Error suscribiendo dialer_stats:', e);
                }
                this._dialerWsConnected = true;
                if (this._dialerWsEverConnected) {
                    // Reconexión: un snapshot REST completo del Estado Discador y luego vuelven los eventos
                    this._dialerNeedsRestResync = true;
                    this.fetchEstadoDiscador();
                }
                this._dialerWsEverConnected = true;
            });
            rws.addEventListener('message', (e) => {
                try {
                    const eventData = JSON.parse(e.data);
                    if (eventData.type === 'stats' && eventData.args) {
                        this.applyDialerStatsEvent(eventData.args);
                    }
                } catch (err) {
                    console.warn('[PanelDialer] Error procesando mensaje omnidialer:', err);
                }
            });
            rws.addEventListener('close', () => {
                this._dialerWsConnected = false;
            });
            rws.addEventListener('error', () => {
                console.warn('[PanelDialer] Error en websocket omnidialer');
            });
            this.dialerSocket = rws;
        },

        disconnectDialerStatsSocket() {
            this._dialerWsConnected = false;
            if (this.dialerSocket) {
                try {
                    this.dialerSocket.close();
                } catch (e) {
                    console.warn('[PanelDialer] Error cerrando websocket omnidialer:', e);
                }
                this.dialerSocket = null;
            }
        },

        /**
         * Aplica eventos STATS/CALLS del canal /channels/omnidialer a Estado Discador.
         */
        applyDialerStatsEvent(args) {
            if (!args || !this.campaignId) {
                return;
            }
            if (Number(args.camp_id) !== Number(this.campaignId)) {
                return;
            }

            const eventType = args.type;
            if (eventType === 'CALLS') {
                const calls = Number(args.calls || 0);
                this.data.llamadas_discando = calls;
                this.previousData.llamadas_discando = calls;
                this.lastUpdate = new Date().toLocaleTimeString();
                return;
            }

            if (eventType !== 'STATS') {
                // STATUSCHANGE / EXPIRATION / etc. fuera del widget Estado Discador
                return;
            }

            const mapping = {
                ATTEMPTED_CALLS: 'attempted_calls',
                ANSWERED_PSTN: 'answered_pstn',
                ANSWERED_AGENT: 'answered_agent',
                PENDING_INITIAL_CONTACT_ATTEMPTS: 'pending_initial',
                'NO CONTACTS WITH PENDING ATTEMPTS': 'pending_retries',
                'FINALIZED WITH NO CONTACT': 'finalized_no_contact',
                'CONTACTED SUCCESSFULLY': 'contacted_successfully',
            };
            const next = { ...(this.data.estado_discador || {}) };
            let changed = false;
            Object.keys(mapping).forEach((redisKey) => {
                if (Object.prototype.hasOwnProperty.call(args, redisKey)) {
                    const alpineKey = mapping[redisKey];
                    const value = Number(args[redisKey] || 0);
                    if (next[alpineKey] !== value) {
                        next[alpineKey] = value;
                        changed = true;
                    }
                }
            });
            if (!changed) {
                return;
            }
            // Al actualizar STATS via WS, recalcular restantes estimadas
            if (Object.prototype.hasOwnProperty.call(next, 'pending_initial')
                    || Object.prototype.hasOwnProperty.call(next, 'pending_retries')) {
                next.estimadas = Number(next.pending_initial || 0) + Number(next.pending_retries || 0);
            }
            this.data.estado_discador = next;
            this.previousData.estado_discador = JSON.parse(JSON.stringify(next));
            this.lastUpdate = new Date().toLocaleTimeString();
        },

        agentBelongsToSelectedCampaign(agente) {
            if (!this.campaignId) {
                return false;
            }
            const campaignNames = window.PANEL_DIALER_CAMPAIGN_NAMES || {};
            const selectedName = campaignNames[String(this.campaignId)];
            if (!selectedName) {
                return false;
            }
            const campanas = agente.CAMPANAS;
            if (Array.isArray(campanas)) {
                return campanas.some((c) => String(c) === String(selectedName));
            }
            if (typeof campanas === 'string') {
                // Puede venir serializado como "['A', 'B']" o CSV
                return campanas.indexOf(selectedName) !== -1;
            }
            // Fallback: campaña activa de la llamada actual
            return String(agente.CAMPAIGN || '') === String(selectedName);
        },

        isActiveAgentStatus(status) {
            if (!status) {
                return false;
            }
            const statusUpper = String(status).toUpperCase();
            if (['READY', 'ONCALL', 'RINGING'].includes(statusUpper)) {
                return true;
            }
            if (statusUpper.startsWith('PAUSE')) {
                return true;
            }
            // Estados no visibles en tabla (alineado con supervision.js checkStatus2Show)
            if (['OFFLINE', ''].includes(statusUpper)) {
                return false;
            }
            return false;
        },

        recomputeAgentCounters(agentesDeCampana) {
            const online = agentesDeCampana.filter((agente) => {
                const status = String(agente.STATUS || '').toUpperCase();
                return status && status !== 'OFFLINE';
            });
            const counters = {
                logueados: online.length,
                ready: 0,
                oncall: 0,
                paused: 0,
                onconfer: 0,
                voicebot: this.data.agentes.voicebot || 0,
            };
            online.forEach((agente) => {
                const status = String(agente.STATUS || '').toUpperCase();
                if (status === 'READY') {
                    counters.ready += 1;
                }
                if (status === 'ONCALL') {
                    counters.oncall += 1;
                }
                if (status.startsWith('PAUSE')) {
                    counters.paused += 1;
                }
                if (status.indexOf('CONFER') !== -1) {
                    counters.onconfer += 1;
                }
            });
            this.data.agentes = {
                ...this.data.agentes,
                ...counters,
                lista_agentes: agentesDeCampana,
            };
            this.previousData.agentes = {
                logueados: counters.logueados,
                ready: counters.ready,
                oncall: counters.oncall,
                paused: counters.paused,
                onconfer: counters.onconfer,
                voicebot: counters.voicebot,
            };
        },

        /**
         * Actualizar lista filtrada de agentes (solo estados READY, ONCALL, RINGING, PAUSED)
         * y opcionalmente filtrados por campaña seleccionada cuando hay stream.
         */
        updateFilteredAgentes() {
            const source = Object.values(this.agentesMap || {});
            let agentesDeCampana = source;

            if (this.streamEnabled) {
                if (!this.campaignId) {
                    this.filteredAgentes = [];
                    this.recomputeAgentCounters([]);
                    return;
                }
                agentesDeCampana = source.filter((agente) => this.agentBelongsToSelectedCampaign(agente));
            } else if (!this.data.agentes?.lista_agentes) {
                this.filteredAgentes = [];
                return;
            } else {
                agentesDeCampana = this.data.agentes.lista_agentes;
            }

            if (this.streamEnabled) {
                this.recomputeAgentCounters(agentesDeCampana);
            }

            this.filteredAgentes = agentesDeCampana.filter((agente) => this.isActiveAgentStatus(agente.STATUS));
        },
    }));
}

// Registrar el componente cuando Alpine.js est? listo
// Este script se carga ANTES de Alpine.js, as? que debemos esperar a que Alpine est? disponible
(function() {
    function registerComponent() {
        if (typeof window.Alpine !== 'undefined' && typeof window.Alpine.data === 'function') {
            try {
                registerContactCenterDashboard();
                console.log('[PanelDialer] Componente panelDialerDashboard registrado correctamente');
                return true;
            } catch (error) {
                console.error('[PanelDialer] Error al registrar el componente:', error);
                return false;
            }
        }
        return false;
    }
    
    // El evento alpine:init se dispara en document, no en window
    // Este evento se dispara ANTES de que Alpine inicialice los elementos del DOM
    document.addEventListener('alpine:init', () => {
        registerComponent();
    });
    
    // Tambi?n intentar registrar inmediatamente si Alpine ya est? disponible
    // (por si el script se carga despu?s de Alpine)
    if (registerComponent()) {
        // Ya est? registrado, no hacer nada m?s
        return;
    }
    
    // Fallback: intentar peri?dicamente por si el evento no se dispara
    let attempts = 0;
    const maxAttempts = 50; // 5 segundos m?ximo
    const interval = setInterval(() => {
        attempts++;
        if (registerComponent()) {
            clearInterval(interval);
        } else if (attempts >= maxAttempts) {
            clearInterval(interval);
            console.error('[PanelDialer] No se pudo registrar el componente despu?s de', maxAttempts, 'intentos');
        }
    }, 100);
})();
