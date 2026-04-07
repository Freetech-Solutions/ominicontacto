(function () {
    var AGENTE_ROL_ID = document.currentScript.dataset.agenteRolId;
    $(function () {
        var email_field = $('#id_0-email');
        var email_label = email_field.prev('label');
        email_label.html(email_label.text().replace('*', '').trim() + '<b class="hidden" style="color:red"> *</b>');
        var rol_select = $('#id_0-rol');
        var grupo_field = $('#id_0-grupo').closest('.form-group');
        var sip_remote_field = $('#id_0-sip_remote').closest('.form-group');
        var sip_remote_checkbox = $('#id_0-sip_remote');
        var voicebot_field = $('#id_0-voicebot').closest('.form-group');
        var voicebot_checkbox = $('#id_0-voicebot');
        var voicebot_trunk_field = $('#id_0-voicebot_trunk').closest('.form-group');
        var voicebot_extension_field = $('#id_0-voicebot_extension').closest('.form-group');
        var voicebot_trunk_input = $('#id_0-voicebot_trunk');
        var voicebot_extension_input = $('#id_0-voicebot_extension');

        voicebot_trunk_field.hide();
        voicebot_extension_field.hide();
        voicebot_trunk_input.prop('disabled', true);
        voicebot_extension_input.prop('disabled', true);

        rol_select.change(on_rol_select_change);

        // Hacer que sip_remote y voicebot sean mutuamente excluyentes
        sip_remote_checkbox.change(function() {
            if ($(this).is(':checked')) {
                voicebot_checkbox.prop('checked', false);
                update_voicebot_extra_visibility();
            }
        });

        voicebot_checkbox.change(function() {
            if ($(this).is(':checked')) {
                sip_remote_checkbox.prop('checked', false);
            }
            update_voicebot_extra_visibility();
        });

        function update_voicebot_extra_visibility() {
            if (rol_select.val() == AGENTE_ROL_ID && voicebot_checkbox.is(':checked')) {
                voicebot_trunk_field.show();
                voicebot_extension_field.show();
                voicebot_trunk_input.prop('disabled', false);
                voicebot_extension_input.prop('disabled', false);
            } else {
                voicebot_trunk_field.hide();
                voicebot_extension_field.hide();
                voicebot_trunk_input.prop('disabled', true);
                voicebot_extension_input.prop('disabled', true);
            }
        }

        function on_rol_select_change() {
            if (rol_select.val() == AGENTE_ROL_ID) {
                email_field.prop('required', true);
                email_label.children('b').removeClass('hidden');
                grupo_field.show();
                sip_remote_field.show();
                voicebot_field.show();
                update_voicebot_extra_visibility();
            } else {
                email_field.prop('required', false);
                email_label.children('b').addClass('hidden');
                grupo_field.hide();
                sip_remote_field.hide();
                voicebot_field.hide();
                voicebot_trunk_field.hide();
                voicebot_extension_field.hide();
                voicebot_trunk_input.prop('disabled', true);
                voicebot_extension_input.prop('disabled', true);
            }
        }
        on_rol_select_change();
    });
})();
