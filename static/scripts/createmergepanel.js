/**
 * Handle the create merge aside panel open/close functionality.
 */

document.addEventListener('DOMContentLoaded', function() {
    var aside = document.querySelector('.l-aside');
    var asideOpenBtn = document.querySelector('.js-aside-open');
    var asideCloseBtn = document.querySelector('.js-aside-close');

    if (!aside || !asideOpenBtn || !asideCloseBtn) {
        return;
    }

    // Open aside panel when Create Merge button clicked.
    asideOpenBtn.addEventListener('click', function(e) {
        aside.classList.remove('is-collapsed');
    });

    // Close the aside panel when clicking outside.
    asideCloseBtn.addEventListener('click', function(e) {
        aside.classList.add('is-collapsed');
        document.activeElement.blur();
    });

    // Close panel when form is submitted
    var form = document.getElementById('create-merge-form');
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            // TODO: Open lp link with additional pre-defined query options
        });
    }
});
