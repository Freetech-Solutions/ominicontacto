/* global gettext */
/* global initContactsDBMetadataField */

'use strict';
{
    function addField(fieldsContainerElem, name, is_phone, is_external_id, is_email) {
        fieldsContainerElem.append(`
            <div class="form-row align-items-center" >
                <div class="col-auto">
                    <input type="text" class="form-control" name="name" placeholder="${gettext('Nombre')}" value="${name}">
                </div>
                <div class="col-auto ml-4">
                    <div class="form-check">
                        <label class="form-check-label">
                            <input class="form-check-input" type="checkbox" name="is-phone" ${is_phone ? 'checked' : ''}>
                            ${gettext('Campos de teléfono')}
                        </label>
                    </div>
                </div>
                <div class="col-auto ml-4">
                    <div class="form-check">
                        <label class="form-check-label">
                            <input class="form-check-input" type="radio" name="is-external-id" ${is_external_id ? 'checked' : ''}>
                            ${gettext('Id externo')}
                        </label>
                    </div>
                </div>
                <div class="col-auto ml-4">
                    <div class="form-check">
                        <label class="form-check-label">
                            <input class="form-check-input" type="radio" name="is-email" ${is_email ? 'checked data-checked="true"' : ''}>
                            ${gettext('Email')}
                        </label>
                    </div>
                </div>
                <div class="col-auto">
                    <button class="btn btn-outline-danger" data-remove-field="">
                        ${gettext('Remover')}
                    </button>
                </div>
            </div>
        `);
    }

    window.initContactsDBMetadataField = function(
        formElem,
        formFieldElem,
        fieldsContainerElem,
        addFieldTriggerElem
    ) {
        const {
            col_id_externo,
            col_email,
            cols_telefono,
            nombres_de_columnas,
            ...restProps
        } = JSON.parse(formFieldElem.val());
        
        nombres_de_columnas.forEach(function(nombre, index) {
            addField(
                fieldsContainerElem,
                nombre,
                cols_telefono.includes(index),
                col_id_externo === index,
                col_email === index,
            );
        });

        fieldsContainerElem.on('click', '[data-remove-field]', function(event){
            event.preventDefault();
            $(this).parents('.form-row').remove();
        });

        addFieldTriggerElem.on('click', function(event) {
            event.preventDefault();
            addField(fieldsContainerElem, '', false, false);
        });

        formElem.on('submit', function() {
            const formFieldValue = {
                ...restProps,
                nombres_de_columnas: [],
                col_id_externo: null,
                col_email: null,
                cols_telefono: [],
                cant_col: 0,
            };
            fieldsContainerElem.children().each(function(_, row){
                const name = $(row).find('input[name="name"]').val();
                if (name) {
                    formFieldValue.nombres_de_columnas.push(name);
                    if ($(row).find('input[name="is-phone"]').prop('checked')) {
                        formFieldValue.cols_telefono.push(formFieldValue.cant_col);
                    }
                    if ($(row).find('input[name="is-external-id"]').prop('checked')) {
                        formFieldValue.col_id_externo = formFieldValue.cant_col;
                    }
                    if ($(row).find('input[name="is-email"]').prop('checked')) {
                        formFieldValue.col_email = formFieldValue.cant_col;
                    }
                    formFieldValue.cant_col += 1;
                }
            });
            formFieldElem.val(JSON.stringify(formFieldValue));
        });

        // Check/uncheck radio button using javascript and html
        // https://stackoverflow.com/a/79769030
        // document.querySelectorAll('input[type=\"radio\"]').forEach((radio) => {
        //     radio.addEventListener("click", (event) => {
        //     });
        // });
        $(formElem).on('click', 'input[type="radio"]', function(event) {
            if(event.target.dataset.checked == 'true') {
                event.target.checked = false;
                delete event.target.dataset.checked;
                event.target.dispatchEvent(new Event('change'));
            } else {
                for(const el of document.querySelectorAll(`input[name="${event.target.name}"]`)) {
                    delete el.dataset.checked;
                }
                event.target.dataset.checked = 'true';
            }
        });

        return {
        };
    };
}

$(document).ready(function(){
    initContactsDBMetadataField(
        $('#wizardForm'),
        $('[name="custom-basedatoscontacto-metadata"'),
        $('.custom-basedatoscontacto-metadata-fields'),
        $('.custom-basedatoscontacto-metadata-fields-add'),
    );
});
