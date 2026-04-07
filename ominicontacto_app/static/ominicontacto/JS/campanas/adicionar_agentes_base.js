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
/* global AGREGAR_AGENTE REMOVER_CAMPO obtenerAgentesGrupos eliminarPrimeraFilaVacia asociarDatosRow*/

// Función para actualizar el badge de tipo de agente (voicebot/humano)
window.updateAgentTypeBadge = function(selectElement) {
    var $select = $(selectElement);
    var $row = $select.closest('tr');
    var $badge = $row.find('.agent-type-badge');
    
    if (!$badge.length) {
        return; // No hay badge, salir
    }
    
    // Obtener el texto del option seleccionado
    var selectedOption = $select.find('option:selected');
    var selectedText = '';
    var selectedValue = $select.val();
    
    if (selectedOption.length && selectedValue) {
        selectedText = selectedOption.text().trim();
    } else {
        // Si select2 está inicializado, obtener el texto del contenedor
        var $select2Container = $select.next('.select2-container');
        if ($select2Container.length) {
            selectedText = $select2Container.find('.select2-selection__rendered').text().trim();
        }
    }
    
    // Verificar si es voicebot
    if (selectedText && selectedText.indexOf('[Voicebot]') !== -1) {
        $badge.removeClass('text-muted label-default').addClass('label label-info');
        $badge.text('Voicebot');
    } else if (selectedText && selectedText !== '---------') {
        $badge.removeClass('text-muted label-info').addClass('label label-default');
        $badge.text('Humano');
    } else {
        $badge.removeClass('label label-info label-default').addClass('text-muted');
        $badge.text('-');
    }
}

var $adicionarAgente = $('#adicionarAgente');
var wizard = $('#wizard').val();
$('.linkFormset').formset({
    addText: AGREGAR_AGENTE,
    deleteText: REMOVER_CAMPO,
    prefix: wizard,
    addCssClass: 'addFormset btn btn-outline-primary',
    deleteCssClass: 'deleteFormset btn btn-outline-danger',
    addMultRows: {'button': $adicionarAgente,
        'function': obtenerAgentesGrupos,
        'post_function': eliminarPrimeraFilaVacia},
    added: function (row) {asociarDatosRow(row);}
});

// Función auxiliar para inicializar select2 con detección de voicebot
function initializeMemberSelect($select, sorter) {
    if ($select.attr('name') && $select.attr('name').indexOf('member') !== -1) {
        if (!$select.hasClass('select2-hidden-accessible')) {
            $select.select2({
                sorter: sorter,
                language: {
                    noResults: function() {
                        return "No se encontraron resultados";
                    }
                }
            });
        }
        // Actualizar badge inicial
        setTimeout(function() {
            updateAgentTypeBadge($select[0]);
        }, 50);
        // Remover eventos anteriores para evitar duplicados
        $select.off('change.select2-agent-type select2:select.select2-agent-type');
        // Actualizar badge cuando cambia la selección
        $select.on('change.select2-agent-type', function() {
            updateAgentTypeBadge(this);
        });
        $select.on('select2:select.select2-agent-type', function() {
            var $this = $(this);
            setTimeout(function() {
                updateAgentTypeBadge($this[0]);
            }, 10);
        });
    } else {
        if (!$select.hasClass('select2-hidden-accessible')) {
            $select.select2({sorter: sorter});
        }
    }
}

$(document).ready(function(){
    function sorter(data) {
        return data.sort(function (a, b) {
            if (a.text > b.text) {
                return 1;
            }
            if (a.text < b.text) {
                return -1;
            }
            return 0;
        });
    }
    
    // Inicializar select2 y actualizar badges para todos los selects existentes
    $('select.form-control').each(function() {
        initializeMemberSelect($(this), sorter);
    });
    
    // Listener global para cambios en selects de miembros (delegación de eventos)
    $(document).on('change', 'select.form-control[name*="member"]', function() {
        updateAgentTypeBadge(this);
    });
    
    $(document).on('select2:select', 'select.form-control[name*="member"]', function() {
        var $this = $(this);
        setTimeout(function() {
            updateAgentTypeBadge($this[0]);
        }, 10);
    });
    
    // Cuando se agrega una nueva fila
    $('.addFormset').click(function(){
        setTimeout(function() {
            $('select.form-control').each(function() {
                initializeMemberSelect($(this), sorter);
            });
        }, 200);
    });
    
    // Validar antes de enviar el formulario si requiere voicebot
    $('#wizardForm').on('submit', function(e) {
        var requiresVoicebot = $('#requires_voicebot').val() === 'true';
        if (requiresVoicebot) {
            var hasVoicebot = false;
            $('select.form-control[name*="member"]').each(function() {
                var $select = $(this);
                var selectedOption = $select.find('option:selected');
                if (selectedOption.length) {
                    var selectedText = selectedOption.text().trim();
                    if (selectedText && selectedText.indexOf('[Voicebot]') !== -1) {
                        hasVoicebot = true;
                        return false; // Salir del each
                    }
                }
            });
            
            if (!hasVoicebot) {
                e.preventDefault();
                alert('Cuando el destino de llamada Dialer es "Agente Remoto", debe asignarse al menos un agente voicebot a la campaña.');
                return false;
            }
        }
    });
});
