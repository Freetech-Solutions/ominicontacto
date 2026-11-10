(function () {
    $(function () {
        var voicebot_checkbox = $('#id_voicebot');
        var voicebot_transport_input = $('#id_voicebot_transport');
        var voicebot_trunk_input = $('#id_voicebot_trunk');
        var voicebot_extension_input = $('#id_voicebot_extension');
        var voicebot_transport_field = voicebot_transport_input.closest('.form-group');
        var voicebot_trunk_field = voicebot_trunk_input.closest('.form-group');
        var voicebot_extension_field = voicebot_extension_input.closest('.form-group');

        if (!voicebot_checkbox.length || !voicebot_trunk_input.length || !voicebot_extension_input.length) {
            return;
        }

        function isAudioSocketTransport() {
            return voicebot_transport_input.length &&
                voicebot_transport_input.val() === 'audiosocket';
        }

        function clearSipVoicebotFields() {
            voicebot_trunk_input.val('');
            voicebot_extension_input.val('');
        }

        function updateVoicebotFieldsVisibility() {
            if (voicebot_checkbox.is(':checked')) {
                if (voicebot_transport_field.length) {
                    voicebot_transport_field.show();
                    voicebot_transport_input.prop('disabled', false);
                }
                if (isAudioSocketTransport()) {
                    clearSipVoicebotFields();
                    voicebot_trunk_field.hide();
                    voicebot_extension_field.hide();
                    voicebot_trunk_input.prop('disabled', true);
                    voicebot_extension_input.prop('disabled', true);
                } else {
                    voicebot_trunk_field.show();
                    voicebot_extension_field.show();
                    voicebot_trunk_input.prop('disabled', false);
                    voicebot_extension_input.prop('disabled', false);
                }
            } else {
                if (voicebot_transport_field.length) {
                    voicebot_transport_field.hide();
                    voicebot_transport_input.prop('disabled', true);
                }
                clearSipVoicebotFields();
                voicebot_trunk_field.hide();
                voicebot_extension_field.hide();
                voicebot_trunk_input.prop('disabled', true);
                voicebot_extension_input.prop('disabled', true);
            }
        }

        updateVoicebotFieldsVisibility();
        voicebot_checkbox.change(updateVoicebotFieldsVisibility);
        if (voicebot_transport_input.length) {
            voicebot_transport_input.change(updateVoicebotFieldsVisibility);
        }
    });
})();
