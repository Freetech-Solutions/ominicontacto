function registerContactCenterDashboard() {
    Alpine.data('contactCenterDashboard', () => ({
        // Estado del componente (preselección desde URL supervision/<id_camp>/panel-general/)
        campaignId: (typeof window !== 'undefined' && window.CONTACT_CENTER_INITIAL_CAMPAIGN_ID != null) ? String(window.CONTACT_CENTER_INITIAL_CAMPAIGN_ID) : '',
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
                outbound: {
                    discadas: 0,
                    atendidas: 0,
                    atendidas_human: 0,
                    atendidas_bot: 0,
                    atendidas_mix: 0,
                    positivas: 0,
                    llamadas_discando: 0,
                    contestadores: 0,
                    ocupado: 0,
                    timeout: 0,
                    canceladas: 0,
                    congestion: 0,
                    chanunavail: 0,
                    num_sin_ruta: 0,
                    errores: 0,
                    shortcall: 0,
                },
                inbound: {
                    entrantes: 0,
                    atendidas: 0,
                    positivas: 0,
                    en_cola: 0,
                    abandonadas: 0,
                    timeout: 0,
                    errores: 0,
                },
                call_times: {
                    aht: 0,
                    mas_extensa: 0,
                    gestion_positiva: 0,
                },
                gestiones: {
                    human: 0,
                    bot: 0,
                    mixed: 0,
                },
            },
            estado_discador: {
                pending_initial: 0,
                pending_retries: 0,
                finalized_no_contact: 0,
                contacted_successfully: 0,
                attempted_calls: 0,
                answered_pstn: 0,
                answered_agent: 0,
                status: [],
            },
        },
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
        charts: {
            outbound: null,
            inbound: null,
            gestiones: null,
        },
        chartsInitialized: {
            outbound: false,
            inbound: false,
            gestiones: false,
        },
        pollingId: null,
        pollingIntervalMs: 5000, // 5 segundos
        statsPollingId: null,
        statsIntervalMs: 30000, // stats ATT/llamadas vía REST (no viajan en el stream)
        agentesMap: {}, // id → fila fusionada (estado vivo del stream + stats REST)
        agentesSocket: null,
        streamEnabled: !!(typeof window !== 'undefined' && window.CONTACT_CENTER_AGENTES_STREAM_URL),
        _streamEverConnected: false,
        _streamMessageSeen: 'Stream subscribed!',
        dialerSocket: null,
        dialerWsEnabled: (typeof ReconnectingWebSocket !== 'undefined'),
        _dialerWsConnected: false,
        _dialerWsEverConnected: false,
        _dialerNeedsRestResync: false, // un fetchLlamadas completo tras reconexión WS
        outboundDialerSocket: null,
        outboundDialerWsEnabled: (typeof ReconnectingWebSocket !== 'undefined'),
        _outboundDialerWsConnected: false,
        _outboundDialerWsEverConnected: false,
        _outboundNeedsRestResync: false, // snapshot REST tras reconexión / cambio de campaña
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
                outbound: null,
                inbound: null,
                call_times: null,
                gestiones: null,
            },
            estado_discador: null,
        },

        // Colores para gr?ficos
        colors: {
            success: '#4caf50',
            successLight: '#80e27e',
            warning: '#ff9800',
            danger: '#f44336',
            info: '#2196f3',
            purple: '#9c27b0',
            grey: '#9e9e9e',
            teal: '#009688',
            orange: '#ff5722',
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
                console.warn('[ContactCenter] deepEqual alcanzó el límite de profundidad, usando comparación por referencia');
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
                    console.warn(`[ContactCenter] Reintentando fetch (intento ${attempt + 1}/${maxRetries}):`, url);
                }
            }
            
            // Si llegamos aquí, todos los intentos fallaron
            console.error(`[ContactCenter] Error en fetch después de ${maxRetries + 1} intentos:`, lastError);
            throw lastError;
        },

        /**
         * Inicializaci?n del componente
         */
        init() {
            // Prevenir inicializaciones m?ltiples, salvo si el canvas del gr?fico inbound fue reemplazado (p. ej. Alpine re-render)
            if (this.initialized) {
                const canvasReplaced = this.charts.inbound && this.charts.inbound.canvas && !document.contains(this.charts.inbound.canvas);
                if (!canvasReplaced) {
                    console.warn('[ContactCenter] El componente ya est? inicializado');
                    return;
                }
                // Canvas reemplazado: destruir gr?ficos y permitir re-inicializaci?n
                this.destroyCharts();
                this.initialized = false;
            }

            // Configurar Chart.js para dark mode
            Chart.defaults.color = '#b0b0b0';
            Chart.defaults.font.family = "'Segoe UI', sans-serif";

            // Inicializar gr?ficos
            this.initCharts();

            // Cargar datos iniciales (primera carga completa)
            this.fetchData().then(() => {
                if (this.streamEnabled) {
                    this.connectAgentesStream();
                    this.startStatsPolling();
                }
                if (this.dialerWsEnabled) {
                    this.connectDialerStatsSocket();
                }
                this.syncOutboundDialerSocket();
            });

            // Iniciar polling (llamadas/bots siempre; agentes solo si no hay stream)
            this.startPolling();

            // Limpiar recursos al cerrar la página
            const cleanupHandler = () => {
                this.cleanup();
            };
            window.addEventListener('beforeunload', cleanupHandler);
            
            // Prevenir memory leaks: pausar polling cuando la página está oculta
            const visibilityHandler = () => {
                if (document.hidden) {
                    // Pausar polling cuando la página está oculta
                    this.stopPolling();
                    this.stopStatsPolling();
                    this.disconnectDialerStatsSocket();
                    this.disconnectOutboundDialerSocket();
                } else {
                    // Reanudar polling cuando la página vuelve a ser visible
                    this.startPolling();
                    if (this.streamEnabled) {
                        this.startStatsPolling();
                    }
                    if (this.dialerWsEnabled) {
                        this.connectDialerStatsSocket();
                    }
                    this.syncOutboundDialerSocket();
                }
            };
            document.addEventListener('visibilitychange', visibilityHandler);
            
            // Fallback adicional: limpiar en pagehide (más confiable que beforeunload en algunos navegadores)
            window.addEventListener('pagehide', cleanupHandler);

            // Marcar como inicializado
            this.initialized = true;
        },

        /**
         * Destruir todos los gr?ficos existentes de forma segura
         * Cancela todas las actualizaciones pendientes antes de destruir
         */
        destroyCharts() {
            this.destroyingCharts = true;
            
            // Cancelar todas las actualizaciones pendientes de gráficos
            Object.keys(this._chartUpdating || {}).forEach(key => {
                delete this._chartUpdating[key];
            });
            
            // Destruir todos los gráficos
            Object.keys(this.charts).forEach(key => {
                if (this.charts[key] && typeof this.charts[key].destroy === 'function') {
                    try {
                        this.charts[key].destroy();
                    } catch (e) {
                        console.warn(`[ContactCenter] Error al destruir gr?fico ${key}:`, e);
                    }
                }
                this.charts[key] = null;
                this.chartsInitialized[key] = false;
            });
            
            // Resetear flag inmediatamente después de destruir (sin setTimeout)
            // Esto previene race conditions donde actualizaciones pueden ocurrir durante el timeout
            this.destroyingCharts = false;
        },

        /**
         * Inicializar los 4 gr?ficos Chart.js
         */
        initCharts() {
            // Destruir gr?ficos existentes antes de crear nuevos
            this.destroyCharts();

            // NOTA: El gráfico outbound ahora usa una tabla con barras CSS en lugar de Chart.js
            // Esto es más robusto y siempre muestra los valores correctamente
            this.charts.outbound = null;
            this.chartsInitialized.outbound = true;

            // 2. INBOUND CHART (Dona)
            const ctxIn = document.getElementById('inboundChart');
            if (ctxIn) {
                try {
                    // Guardar referencia a los colores para usar en generateLabels
                    const inboundColors = [
                        this.colors.success,   // Atendidas - verde
                        this.colors.grey,    // Abandonadas - gris
                        this.colors.danger,    // Timeout - rojo
                    ];
                    
                    this.charts.inbound = new Chart(ctxIn.getContext('2d'), {
                        type: 'doughnut',
                        data: {
                            labels: [
                                'Atendidas',
                                'Abandonadas (Cancel)',
                                'Timeout Sistema',
                            ],
                            datasets: [{
                                data: [0, 0, 0],  // Valores iniciales para que Chart.js calcule layout
                                backgroundColor: inboundColors,
                                borderWidth: 2,
                                borderColor: '#16213e'
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            animation: {
                                duration: 0 // Desactivar animaciones desde el inicio
                            },
                            plugins: {
                                legend: { 
                                    position: 'right',
                                    generateLabels: (chart) => {
                                        const data = chart.data;
                                        if (data.labels.length && data.datasets.length) {
                                            const dataset = data.datasets[0];
                                            
                                            return data.labels.map((label, i) => {
                                                const value = dataset.data[i] || 0;
                                                // Formatear el label según el tipo
                                                let displayLabel = label;
                                                if (label === 'Abandonadas') {
                                                    displayLabel = 'Abandonadas';
                                                } else if (label === 'Timeout Sistema') {
                                                    displayLabel = 'Timeout';
                                                }
                                                // Usar el color correcto de la lista definida arriba
                                                const color = inboundColors[i] || dataset.backgroundColor?.[i] || '#9e9e9e';
                                                return {
                                                    text: `${displayLabel}: ${value}`,
                                                    fillStyle: color,
                                                    hidden: false,
                                                    index: i
                                                };
                                            });
                                        }
                                        return [];
                                    }
                                }
                            },
                            cutout: '65%'
                        }
                    });
                    // Marcar como inicializado después de un pequeño delay para permitir que Chart.js configure todos los plugins
                    setTimeout(() => {
                        this.chartsInitialized.inbound = true;
                    }, 50);
                } catch (e) {
                    console.error('[ContactCenter] Error al inicializar gráfico inbound:', e);
                    this.charts.inbound = null;
                }
            }

            // NOTA: El gráfico de gestiones ha sido removido del Panel General
            this.charts.gestiones = null;
            this.chartsInitialized.gestiones = true;

            // NOTA: El gráfico de sentimiento ha sido reemplazado por el widget "Estado Discador"
        },

        /**
         * Obtener datos del endpoint API (carga inicial completa)
         */
        async fetchData() {
            this.loading = true;
            try {
                const url = window.CONTACT_CENTER_DATA_URL || '/supervision/panel-general/data/';
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

                // Actualizar datos
                this.data = {
                    agentes: {
                        ...this.data.agentes,
                        ...(jsonData.agentes || {}),
                        lista_agentes: jsonData.agentes?.lista_agentes || [],
                    },
                    llamadas: jsonData.llamadas || this.data.llamadas,
                    estado_discador: jsonData.estado_discador || this.data.estado_discador,
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
                        outbound: JSON.parse(JSON.stringify(this.data.llamadas?.outbound || {})),
                        inbound: JSON.parse(JSON.stringify(this.data.llamadas?.inbound || {})),
                        call_times: JSON.parse(JSON.stringify(this.data.llamadas?.call_times || {})),
                        gestiones: JSON.parse(JSON.stringify(this.data.llamadas?.gestiones || {})),
                    },
                    estado_discador: JSON.parse(JSON.stringify(this.data.estado_discador || {})),
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
                const url = window.CONTACT_CENTER_AGENTES_URL || '/supervision/panel-general/data/agentes/';
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
                const url = window.CONTACT_CENTER_AGENTES_LISTA_URL || '/supervision/panel-general/data/agentes-lista/';
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
         * Obtener solo m?tricas de llamadas
         */
        async fetchLlamadas() {
            try {
                const url = window.CONTACT_CENTER_LLAMADAS_URL || '/supervision/panel-general/data/llamadas/';
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

                const newLlamadas = {
                    outbound: jsonData.outbound || {},
                    inbound: jsonData.inbound || {},
                    call_times: jsonData.call_times || {},
                    gestiones: jsonData.gestiones || {},
                };
                
                const newEstadoDiscador = jsonData.estado_discador || {
                    pending_initial: 0,
                    pending_retries: 0,
                    finalized_no_contact: 0,
                    contacted_successfully: 0,
                    attempted_calls: 0,
                    answered_pstn: 0,
                    answered_agent: 0,
                    status: [],
                };

                // Con WS discador activo: no pisar estado_discador ni canales activos (salvo resync post-reconnect)
                const protectDialerLive = this.shouldProtectDialerFromRest();
                // Outbound: REST (CALLDATA DB2) es fuente absoluta entre polls; el WS aplica deltas en vivo.
                // No bloquear Outbound desde REST (evita UI congelada si el WS conecta pero no pinta).
                const liveOutbound = this.data.llamadas?.outbound || {};
                if (protectDialerLive) {
                    newLlamadas.outbound = {
                        ...newLlamadas.outbound,
                        llamadas_discando: liveOutbound.llamadas_discando || 0,
                    };
                }

                let hasChanges = false;
                const groupsToCheck = ['outbound', 'inbound', 'call_times', 'gestiones'];
                
                for (const group of groupsToCheck) {
                    if (this.hasChanged(group, newLlamadas[group], this.previousData.llamadas[group])) {
                        hasChanges = true;
                        break;
                    }
                }
                
                // Verificar cambios en estado_discador solo si el REST puede escribirlo
                if (!protectDialerLive && this.hasChanged('estado_discador', newEstadoDiscador, this.previousData.estado_discador)) {
                    hasChanges = true;
                }

                // Solo actualizar si hay cambios
                if (hasChanges) {
                    this.data.llamadas = newLlamadas;
                    if (!protectDialerLive) {
                        this.data.estado_discador = newEstadoDiscador;
                        this.previousData.estado_discador = JSON.parse(JSON.stringify(newEstadoDiscador));
                    }
                    this.previousData.llamadas = {
                        outbound: JSON.parse(JSON.stringify(newLlamadas.outbound)),
                        inbound: JSON.parse(JSON.stringify(newLlamadas.inbound)),
                        call_times: JSON.parse(JSON.stringify(newLlamadas.call_times)),
                        gestiones: JSON.parse(JSON.stringify(newLlamadas.gestiones)),
                    };
                    
                    // Actualizar timestamp
                    if (jsonData.timestamp) {
                        const date = new Date(jsonData.timestamp);
                        this.lastUpdate = date.toLocaleTimeString();
                    }
                    
                    // Actualizar solo los gr?ficos que cambiaron
                    this.updateChartsSelective(newLlamadas);
                }

                if (this._dialerNeedsRestResync) {
                    this._dialerNeedsRestResync = false;
                }
                if (this._outboundNeedsRestResync) {
                    this._outboundNeedsRestResync = false;
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
                const url = window.CONTACT_CENTER_BOTS_CAMPANA_URL || '/supervision/panel-general/data/bots-campana/';
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

        /**
         * Actualizar gr?ficos con los datos actuales (todos)
         */
        updateCharts() {
            const llamadas = this.data.llamadas || {};
            this.updateChartsSelective(llamadas);
        },

        /**
         * Verificar si un gr?fico est? listo para ser actualizado
         */
        isChartReady(chart, chartKey) {
            if (!chart) return false;
            if (this.destroyingCharts) return false;
            if (typeof chart.destroyed !== 'undefined' && chart.destroyed) return false;
            if (typeof chart.update !== 'function') return false;
            if (!chart.data || !chart.data.datasets || !chart.data.datasets[0]) return false;
            // Verificar que el gr?fico tenga la estructura completa de Chart.js
            if (!chart.canvas || !chart.ctx) return false;
            // Verificar que el canvas aún esté en el DOM
            if (!chart.canvas.parentNode) return false;
            // Compatibilidad con Chart.js v3/v4: no asumir estructura interna de config/plugins
            if (chart.canvas && chart.canvas.isConnected === false) return false;
            return true;
        },

        /**
         * Actualizar un gr?fico de forma segura usando requestAnimationFrame
         * Previene actualizaciones concurrentes del mismo gráfico
         */
        safeUpdateChart(chart, data, chartKey) {
            if (!chart || !chartKey) return;
            if (!this.isChartReady(chart, chartKey)) return;
            
            // Prevenir actualizaciones concurrentes del mismo gráfico
            if (this._chartUpdating[chartKey]) {
                return;
            }
            
            // Marcar como actualizando
            this._chartUpdating[chartKey] = true;
            
            try {
                // Verificar que los datos sean un array válido
                if (!Array.isArray(data)) {
                    console.warn('[ContactCenter] Los datos del gráfico deben ser un array');
                    this._chartUpdating[chartKey] = false;
                    return;
                }
                
                // Verificar que el dataset exista
                if (!chart.data || !chart.data.datasets || !chart.data.datasets[0]) {
                    console.warn('[ContactCenter] El gráfico no tiene un dataset válido');
                    this._chartUpdating[chartKey] = false;
                    return;
                }
                
                // Preservar los colores originales si se están perdiendo (especialmente para inbound)
                if (chartKey === 'inbound') {
                    // Definir los colores correctos para inbound - SIEMPRE establecerlos explícitamente
                    const inboundColors = [
                        this.colors.success,   // Atendidas - verde
                        this.colors.grey,    // Abandonadas - gris
                        this.colors.danger,    // Timeout - rojo
                    ];
                    
                    // SIEMPRE establecer los colores correctos para evitar que se pierdan
                    chart.data.datasets[0].backgroundColor = inboundColors;
                }
                
                // Actualizar los datos
                chart.data.datasets[0].data = data;
                
                // Usar requestAnimationFrame para asegurar que la actualizaci?n ocurra en el momento correcto
                requestAnimationFrame(() => {
                    try {
                        // Verificar nuevamente antes de actualizar (puede haber cambiado el estado)
                        if (!this.isChartReady(chart, chartKey)) {
                            this._chartUpdating[chartKey] = false;
                            return;
                        }
                        
                        try {
                            // Para gráficos de tipo doughnut, asegurar que se renderice incluso con datos cero
                            if (chart.config.type === 'doughnut' && chartKey === 'inbound') {
                                // Verificar que el canvas tenga dimensiones válidas
                                if (chart.canvas && chart.canvas.width === 0) {
                                    chart.resize();
                                }
                            }
                            
                            // Usar 'none' solo si el gráfico ya fue inicializado completamente
                            // Esto evita problemas con plugins que intentan acceder a propiedades no inicializadas
                            if (this.chartsInitialized[chartKey]) {
                                chart.update('none');
                            } else {
                                // Si no está inicializado, usar update sin argumentos para permitir la inicialización
                                chart.update();
                                this.chartsInitialized[chartKey] = true;
                            }
                        } catch (e) {
                            // Si 'none' falla, intentar sin argumentos
                            try {
                                chart.update();
                                this.chartsInitialized[chartKey] = true;
                            } catch (e2) {
                                console.warn('[ContactCenter] Error al actualizar gr?fico:', e2);
                                // Si ambos fallan, marcar como no inicializado para reintentar en la próxima actualización
                                this.chartsInitialized[chartKey] = false;
                            }
                        }
                    } finally {
                        // Resetear flag de actualización en finally para asegurar que siempre se resetee
                        this._chartUpdating[chartKey] = false;
                    }
                });
            } catch (e) {
                console.warn('[ContactCenter] Error al preparar actualizaci?n de gr?fico:', e);
                // Resetear flag en caso de error
                this._chartUpdating[chartKey] = false;
            }
        },

        /**
         * Actualizar gr?ficos de forma selectiva basado en los datos proporcionados
         */
        updateChartsSelective(llamadas) {
            if (!llamadas) return;
            if (this.destroyingCharts) return; // No actualizar si se est?n destruyendo gr?ficos

            // NOTA: El gráfico outbound ahora usa Alpine.js directamente en el HTML
            // Los valores se actualizan automáticamente cuando cambia this.data.llamadas.outbound
            // No necesitamos actualizar Chart.js para outbound

            // Actualizar Inbound Chart
            if (this.charts.inbound && llamadas.inbound) {
                const inbound = llamadas.inbound;
                this.safeUpdateChart(this.charts.inbound, [
                    inbound.atendidas || 0,
                    inbound.abandonadas || 0,
                    inbound.timeout || 0,
                ], 'inbound');
            }

            // NOTA: El gráfico de gestiones ha sido removido del Panel General
            // NOTA: El gráfico de sentimiento ha sido reemplazado por el widget "Estado Discador"
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
                    console.warn('[ContactCenter] Polling ya en curso, saltando esta iteración');
                    return;
                }
                
                // Crear nuevo AbortController para este ciclo de polling
                this._pollingAbortController = new AbortController();
                this._isPolling = true;

                // Con stream activo: solo métricas de campaña/bots (agentes vivos van por WS)
                const tasks = this.streamEnabled
                    ? [this.fetchLlamadas(), this.fetchBotsCampana()]
                    : [
                        this.fetchAgentes(),
                        this.fetchAgentesLista(),
                        this.fetchLlamadas(),
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
                    console.warn('[ContactCenter] Error al colgar en cleanup:', e);
                }
            }
            this.stopPolling();
            this.stopStatsPolling();
            this.disconnectAgentesStream();
            this.disconnectDialerStatsSocket();
            this.disconnectOutboundDialerSocket();
            this.destroyCharts();
            this.initialized = false;
        },

        /**
         * Manejar cambio de campa?a
         */
        onCampaignChange() {
            // Con stream: refiltrar inmediatamente desde agentesMap; REST trae baseline/stats
            if (this.streamEnabled) {
                this.updateFilteredAgentes();
            }
            this._outboundNeedsRestResync = true;
            this.syncOutboundDialerSocket();
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
            const baseUrl = window.CONTACT_CENTER_API_ACTION_AGENT;
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
            const url = window.CONTACT_CENTER_API_SPY;
            const supervisorId = window.CONTACT_CENTER_SUPERVISOR_ID;
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
            const url = window.CONTACT_CENTER_API_SPY;
            const supervisorId = window.CONTACT_CENTER_SUPERVISOR_ID;
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
            const url = window.CONTACT_CENTER_API_THREE_WAY;
            const supervisorId = window.CONTACT_CENTER_SUPERVISOR_ID;
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
            const url = window.CONTACT_CENTER_API_SEND_MESSAGE;
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
            const campaignNames = window.CONTACT_CENTER_CAMPAIGN_NAMES || {};
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
                    console.warn('[ContactCenter] Error parseando evento de stream de agentes:', err);
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
            const url = window.CONTACT_CENTER_AGENTES_STREAM_URL;
            if (!url || typeof ReconnectingWebSocket === 'undefined') {
                console.warn('[ContactCenter] Stream de agentes no disponible; usando polling REST');
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
                    console.warn('[ContactCenter] Error procesando mensaje de stream:', err);
                }
            });
            rws.addEventListener('error', () => {
                console.warn('[ContactCenter] Error en websocket de agentes');
            });
            this.agentesSocket = rws;
        },

        disconnectAgentesStream() {
            if (this.agentesSocket) {
                try {
                    this.agentesSocket.close();
                } catch (e) {
                    console.warn('[ContactCenter] Error cerrando stream de agentes:', e);
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

        isSelectedCampaignDialer() {
            if (!this.campaignId) {
                return false;
            }
            const types = window.CONTACT_CENTER_CAMPAIGN_TYPES || {};
            const typeDialer = window.CONTACT_CENTER_TYPE_DIALER != null
                ? Number(window.CONTACT_CENTER_TYPE_DIALER)
                : 2;
            return Number(types[String(this.campaignId)]) === typeDialer;
        },

        syncOutboundDialerSocket() {
            if (this.isSelectedCampaignDialer() && this.outboundDialerWsEnabled) {
                if (!this.outboundDialerSocket) {
                    this.connectOutboundDialerSocket();
                }
            } else {
                this.disconnectOutboundDialerSocket();
            }
        },

        connectOutboundDialerSocket() {
            if (typeof ReconnectingWebSocket === 'undefined') {
                console.warn('[ContactCenter] ReconnectingWebSocket no disponible; Outbound por REST');
                this.outboundDialerWsEnabled = false;
                this._outboundDialerWsConnected = false;
                return;
            }
            this.disconnectOutboundDialerSocket();
            const url = 'wss://' + window.location.host + '/channels/supervision/dialer';
            const rws = new ReconnectingWebSocket(url, [], {
                connectionTimeout: 10000,
                maxReconnectionDelay: 3000,
                minReconnectionDelay: 1000,
            });
            rws.addEventListener('open', () => {
                this._outboundDialerWsConnected = true;
                if (this._outboundDialerWsEverConnected) {
                    this._outboundNeedsRestResync = true;
                    this.fetchLlamadas();
                }
                this._outboundDialerWsEverConnected = true;
            });
            rws.addEventListener('message', (e) => {
                try {
                    const eventData = JSON.parse(e.data);
                    this.applyOutboundDialerEvent(eventData);
                } catch (err) {
                    console.warn('[ContactCenter] Error procesando mensaje supervision/dialer:', err);
                }
            });
            rws.addEventListener('close', () => {
                this._outboundDialerWsConnected = false;
            });
            rws.addEventListener('error', () => {
                console.warn('[ContactCenter] Error en websocket supervision/dialer');
            });
            this.outboundDialerSocket = rws;
        },

        disconnectOutboundDialerSocket() {
            this._outboundDialerWsConnected = false;
            if (this.outboundDialerSocket) {
                try {
                    this.outboundDialerSocket.close();
                } catch (e) {
                    console.warn('[ContactCenter] Error cerrando websocket supervision/dialer:', e);
                }
                this.outboundDialerSocket = null;
            }
        },

        /**
         * Aplica updates del canal /channels/supervision/dialer a Llamadas Outbound.
         */
        applyOutboundDialerEvent(eventData) {
            if (!eventData || !this.campaignId || !this.isSelectedCampaignDialer()) {
                return;
            }
            // initial_data es snapshot grueso de dialers table; Outbound usa REST como baseline absoluto
            if (eventData.initial_data != null) {
                return;
            }
            if (eventData.type !== 'update' || !eventData.args || eventData.args.DIALER == null) {
                return;
            }
            const payload = eventData.args.DIALER;
            const updates = Array.isArray(payload) ? payload : [payload];
            const ATTENDED_FIELDS = ['atendidas_human', 'atendidas_bot', 'atendidas_mix'];
            let changed = false;
            const nextOutbound = { ...(this.data.llamadas.outbound || {}) };

            updates.forEach((data) => {
                if (!data || Number(data.campaign_id) !== Number(this.campaignId)) {
                    return;
                }
                // Prefer outbound_field; fallback mínimo por field grueso (compat payloads viejos)
                let outboundField = data.outbound_field;
                if (!outboundField && data.field) {
                    const fieldFallback = {
                        dialed: 'discadas',
                        amd: 'contestadores',
                        shortcall: 'shortcall',
                    };
                    outboundField = fieldFallback[data.field] || null;
                    if (data.field === 'attended') {
                        // Sin desglose fine: sumar atendidas agregadas
                        const deltaAtt = Number(data.delta != null ? data.delta : 1);
                        nextOutbound.atendidas = Number(nextOutbound.atendidas || 0) + deltaAtt;
                        nextOutbound.positivas = Number(nextOutbound.positivas || 0) + deltaAtt;
                        changed = true;
                    }
                }
                if (!outboundField) {
                    return;
                }
                const delta = Number(data.delta != null ? data.delta : 1);
                nextOutbound[outboundField] = Number(nextOutbound[outboundField] || 0) + delta;
                if (ATTENDED_FIELDS.includes(outboundField)) {
                    nextOutbound.atendidas = Number(nextOutbound.atendidas || 0) + delta;
                    nextOutbound.positivas = Number(nextOutbound.positivas || 0) + delta;
                }
                changed = true;
            });

            if (!changed) {
                return;
            }
            this.data.llamadas = {
                ...this.data.llamadas,
                outbound: nextOutbound,
            };
            if (this.previousData.llamadas) {
                this.previousData.llamadas.outbound = JSON.parse(JSON.stringify(nextOutbound));
            }
            this.lastUpdate = new Date().toLocaleTimeString();
        },

        connectDialerStatsSocket() {
            if (typeof ReconnectingWebSocket === 'undefined') {
                console.warn('[ContactCenter] ReconnectingWebSocket no disponible; Estado Discador por REST');
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
                    console.warn('[ContactCenter] Error suscribiendo dialer_stats:', e);
                }
                this._dialerWsConnected = true;
                if (this._dialerWsEverConnected) {
                    // Reconexión: un snapshot REST completo (discador + gráficos) y luego vuelven los eventos
                    this._dialerNeedsRestResync = true;
                    this.fetchLlamadas();
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
                    console.warn('[ContactCenter] Error procesando mensaje omnidialer:', err);
                }
            });
            rws.addEventListener('close', () => {
                this._dialerWsConnected = false;
            });
            rws.addEventListener('error', () => {
                console.warn('[ContactCenter] Error en websocket omnidialer');
            });
            this.dialerSocket = rws;
        },

        disconnectDialerStatsSocket() {
            this._dialerWsConnected = false;
            if (this.dialerSocket) {
                try {
                    this.dialerSocket.close();
                } catch (e) {
                    console.warn('[ContactCenter] Error cerrando websocket omnidialer:', e);
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
                this.data.llamadas = {
                    ...this.data.llamadas,
                    outbound: {
                        ...(this.data.llamadas.outbound || {}),
                        llamadas_discando: calls,
                    },
                };
                if (this.previousData.llamadas && this.previousData.llamadas.outbound) {
                    this.previousData.llamadas.outbound = {
                        ...this.previousData.llamadas.outbound,
                        llamadas_discando: calls,
                    };
                }
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
            const reserved = {
                type: true, camp_id: true, admin: true,
            };
            Object.keys(mapping).forEach((k) => { reserved[k] = true; });
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
            const statusList = Array.isArray(next.status) ? next.status.slice() : [];
            Object.keys(args).forEach((redisKey) => {
                if (reserved[redisKey]) {
                    return;
                }
                const value = Number(args[redisKey]);
                if (Number.isNaN(value)) {
                    return;
                }
                const idx = statusList.findIndex((s) => s.gbState === redisKey);
                if (idx >= 0) {
                    if (Number(statusList[idx].nCalls) !== value) {
                        statusList[idx] = Object.assign({}, statusList[idx], { nCalls: value });
                        changed = true;
                    }
                } else {
                    statusList.push({
                        gbState: redisKey,
                        gbStateLabel: redisKey,
                        nCalls: value,
                    });
                    changed = true;
                }
            });
            if (changed) {
                next.status = statusList;
            }
            if (!changed) {
                return;
            }
            this.data.estado_discador = next;
            this.previousData.estado_discador = JSON.parse(JSON.stringify(next));
            this.lastUpdate = new Date().toLocaleTimeString();
        },

        agentBelongsToSelectedCampaign(agente) {
            if (!this.campaignId) {
                return false;
            }
            const campaignNames = window.CONTACT_CENTER_CAMPAIGN_NAMES || {};
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
                console.log('[ContactCenter] Componente contactCenterDashboard registrado correctamente');
                return true;
            } catch (error) {
                console.error('[ContactCenter] Error al registrar el componente:', error);
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
            console.error('[ContactCenter] No se pudo registrar el componente despu?s de', maxAttempts, 'intentos');
        }
    }, 100);
})();
