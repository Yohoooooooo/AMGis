document.addEventListener('DOMContentLoaded', function () {
    function addField(buttonClass, inputSelector) {
        const button = document.querySelector(buttonClass);
        if (!button) return;

        button.addEventListener('click', function () {
            const container = this.previousElementSibling.parentElement;
            const template = container.querySelector('.input-group').cloneNode(true);
            const input = template.querySelector('input');

            input.value = '';

            if (!template.querySelector('.remove-field')) {
                const removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.className = 'btn btn-outline-danger remove-field';
                removeBtn.innerHTML = '<i class="bi bi-dash"></i>';
                removeBtn.addEventListener('click', function () {
                    this.closest('.input-group').remove();
                });
                template.appendChild(removeBtn);
            }

            container.insertBefore(template, this);
        });
    }

    function initRemoveButtons() {
        document.querySelectorAll('.remove-field').forEach(button => {
            button.addEventListener('click', function () {
                this.closest('.input-group').remove();
            });
        });
    }

    addField('.add-email-btn');
    addField('.add-phone-btn');
    addField('.add-mobile-btn');
    initRemoveButtons();
});
