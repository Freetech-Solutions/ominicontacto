(function () {
    $(function () {
        var voicebot_checkbox = $('#id_voicebot');
        var voicebot_trunk_input = $('#id_voicebot_trunk');
        var voicebot_extension_input = $('#id_voicebot_extension');
        var voicebot_trunk_field = voicebot_trunk_input.closest('.form-group');
        var voicebot_extension_field = voicebot_extension_input.closest('.form-group');

        if (!voicebot_checkbox.length || !voicebot_trunk_input.length || !voicebot_extension_input.length) {
            return;
        }

        function updateVoicebotFieldsVisibility() {
            if (voicebot_checkbox.is(':checked')) {
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

        updateVoicebotFieldsVisibility();
        voicebot_checkbox.change(updateVoicebotFieldsVisibility);
    });
})();
