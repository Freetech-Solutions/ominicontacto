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

/* global gettext interpolate Swal */

/**
 * Sincroniza el máximo de agentes concurrentes con el valor del Register Server.
 * Paso 1: el servidor lee el valor sin aplicarlo y devuelve la advertencia de qué límite quedará.
 * Paso 2: solo si el administrador confirma se aplica.
 * El servidor permite una consulta por minuto: mientras tanto el botón queda deshabilitado
 * con una cuenta regresiva (los segundos restantes vienen del servidor, sobreviven al reload).
 */
var $syncButton = $('#syncConcurrency');
var syncUrl = $syncButton.data('url');  // endpoint de enterprise_app
var $syncWait = $('#syncConcurrencyWait');
var countdownTimer = null;

function startCountdown(seconds) {
    clearInterval(countdownTimer);
    var remaining = parseInt(seconds, 10);
    if (!(remaining > 0)) {
        $syncButton.prop('disabled', false);
        $syncWait.text('');
        return;
    }
    $syncButton.prop('disabled', true);
    var render = function() {
        if (remaining <= 0) {
            clearInterval(countdownTimer);
            $syncButton.prop('disabled', false);
            $syncWait.text('');
            return;
        }
        $syncWait.text(interpolate(
            gettext('Puede volver a sincronizar en %s segs'), [remaining]));
        remaining -= 1;
    };
    render();
    countdownTimer = setInterval(render, 1000);
}

startCountdown($syncButton.data('wait'));

var WARNING_ICONS = {
    SYNCED: 'info',
    UNDEFINED: 'info',
};

function applySync() {
    $.post(syncUrl, {action: 'apply'})
        .done(function(data) {
            Swal.fire({
                icon: data.status == 'OK' ? 'success' : 'warning',
                text: data.message,
            }).then(function() {
                location.reload();
            });
        })
        .fail(function(jqXHR) {
            var message = jqXHR.responseJSON ? jqXHR.responseJSON.message :
                gettext('No se pudo conectar al servidor');
            Swal.fire({icon: 'error', text: message});
        });
}

$syncButton.on('click', function(){
    $syncButton.prop('disabled', true);
    $.post(syncUrl, {action: 'preview'})
        .done(function(data) {
            startCountdown(data.retry_after);
            Swal.fire({
                icon: WARNING_ICONS[data.state] || 'warning',
                title: gettext('Atención'),
                html: $('<div>').append($('<p>').text(data.message))
                    .append($('<p>').append($('<b>').text(gettext('¿Desea continuar?')))).html(),
                showCancelButton: true,
                confirmButtonText: gettext('Sí'),
                cancelButtonText: gettext('No'),
                focusCancel: true,
            }).then(function(result) {
                if (result.isConfirmed) {
                    applySync();
                }
            });
        })
        .fail(function(jqXHR) {
            if (jqXHR.status == 429 && jqXHR.responseJSON) {
                startCountdown(jqXHR.responseJSON.retry_after);
                return;
            }
            $syncButton.prop('disabled', false);
            Swal.fire({
                icon: 'error',
                text: gettext('No se pudo conectar al servidor'),
            });
        });
});
