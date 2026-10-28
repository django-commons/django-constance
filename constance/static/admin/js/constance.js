(function($) {
    'use strict';

    $(function() {

        $('#content-main').on('click', '.reset-link', function(e) {
            e.preventDefault();

            const rawFieldId = this.dataset.fieldId;
            const fieldEl = document.getElementById(rawFieldId);
            const field = fieldEl ? $(fieldEl) : $('#' + rawFieldId.replace(/ /g, "\\ "));
            const fieldType = this.dataset.fieldType;
            const defaultValue = (this.dataset.default || '').trim();

            if (fieldType === 'checkbox') {
                field.prop('checked', defaultValue === 'true').trigger('change');
            } else if (fieldType === 'multi-select') {
                let defaults = [];
                try {
                    defaults = JSON.parse(defaultValue);
                } catch (err) {
                    defaults = [];
                }
                if (!Array.isArray(defaults)) {
                    defaults = [defaults];
                }
                const stringDefaults = (defaults.flat ? defaults.flat(Infinity) : defaults).map(function(v) {
                    return String(v);
                });

                // CheckboxSelectMultiple: individual checkboxes inside a wrapper
                field.find('input[type="checkbox"]').each(function() {
                    $(this).prop('checked', stringDefaults.indexOf($(this).val()) !== -1).trigger('change');
                });

                // SelectMultiple: <select multiple> element
                field.find('option').each(function() {
                    $(this).prop('selected', stringDefaults.indexOf($(this).val()) !== -1);
                });
                field.trigger('change');
            } else if (fieldType === 'date') {
                const defaultDate = new Date(defaultValue * 1000);
                field.val(defaultDate.strftime(get_format('DATE_INPUT_FORMATS')[0])).trigger('change');
            } else if (fieldType === 'datetime') {
                const defaultDate = new Date(defaultValue * 1000);
                const field0 = document.getElementById(rawFieldId + '_0');
                const field1 = document.getElementById(rawFieldId + '_1');
                (field0 ? $(field0) : $('#' + rawFieldId + '_0')).val(defaultDate.strftime(get_format('DATE_INPUT_FORMATS')[0])).trigger('change');
                (field1 ? $(field1) : $('#' + rawFieldId + '_1')).val(defaultDate.strftime(get_format('TIME_INPUT_FORMATS')[0])).trigger('change');
            } else {
                field.val(defaultValue).trigger('change');
            }
        });
    });
})(django.jQuery);
