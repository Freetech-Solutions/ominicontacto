export default {
    outboundRoutes: [],
    outboundRoute: {
        id: null,
        nombre: '',
        ring_time: 25,
        dial_options: 'Tt',
        troncales: [],
        patrones_de_discado: []
    },
    dialPattern: {
        id: null,
        prepend: null,
        prefix: null,
        match_pattern: null,
        caller_id: null
    },
    trunk: {
        id: null,
        troncal: null
    },
    sipTrunks: [],
    orphanTrunks: []
};
