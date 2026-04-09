/**
 * Handle the create launchpad bug aside panel functionality.
 */

/**
 * Set active tab in bug creation aside.
 * @param {HTMLButtonElement} tab // The tab element to set as active.
 * @param {NodeListOf<HTMLButtonElement>} tabs // The tab group containing tab.
 */
function setActiveTab(tab, tabs) {
    tabs.forEach(function(tabElement) {
        var tabContent = document.getElementById(tabElement.getAttribute('aria-controls'));

        if (tabElement === tab) {
            tabElement.setAttribute('aria-selected', true);
            tabElement.setAttribute('tabindex', '0');
            if (tabContent) {
                tabContent.removeAttribute('hidden');
            }
        } else {
            tabElement.setAttribute('aria-selected', false);
            tabElement.setAttribute('tabindex', '-1');
            if (tabContent) {
                tabContent.setAttribute('hidden', true);
            }
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    var aside = document.querySelector('.l-aside');
    var asideOpenBtn = document.querySelector('.js-aside-open');
    var asideCloseBtn = document.querySelector('.js-aside-close');
    var tabs = aside ? aside.querySelectorAll('.p-tabs [role="tab"]') : [];

    if (!aside || !asideOpenBtn || !asideCloseBtn) {
        return;
    }

    // Activate aside tabs based on click or arrow key press.
    tabs.forEach(function(tab, index) {
        tab.addEventListener('click', function() {
            setActiveTab(tab, tabs);
        });

        tab.addEventListener('keydown', function(e) {
            if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) {
                return;
            }

            e.preventDefault();

            var nextIndex = index;
            if (e.key === 'ArrowRight') {
                nextIndex = (index + 1) % tabs.length;
            } else if (e.key === 'ArrowLeft') {
                nextIndex = (index - 1 + tabs.length) % tabs.length;
            }

            var nextTab = tabs[nextIndex];
            setActiveTab(nextTab, tabs);
            nextTab.focus();
        });
    });

    // Open aside panel when Create button clicked.
    asideOpenBtn.addEventListener('click', function(e) {
        aside.classList.remove('is-collapsed');
    });

    // Close the aside panel when clicking outside.
    asideCloseBtn.addEventListener('click', function(e) {
        aside.classList.add('is-collapsed');
        document.activeElement.blur();
    });

    // Go to LP bug creation page on submit.
    var createMergeForm = document.getElementById('create-merge-form');
    if (createMergeForm) {
        createMergeForm.addEventListener('submit', function(e) {
            e.preventDefault();
            var packageInput = document.getElementById('merge-package');
            if (!packageInput || !packageInput.value.trim()) {
                createMergeForm.reportValidity();
                return;
            }

            var packageName = packageInput.value.trim();
            var fileBugPath = '/launchpad/mergebug/' + encodeURIComponent(packageName);
            window.open(fileBugPath, '_blank', 'noopener,noreferrer');
        });
    }

    var createBackportForm = document.getElementById('create-backport-form');
    if (createBackportForm) {
        createBackportForm.addEventListener('submit', function(e) {
            e.preventDefault();
            var packageInput = document.getElementById('backport-package');
            if (!packageInput || !packageInput.value.trim()) {
                createBackportForm.reportValidity();
                return;
            }

            var packageName = packageInput.value.trim();
            var fileBugPath = '/launchpad/backportbug/' + encodeURIComponent(packageName);
            window.open(fileBugPath, '_blank', 'noopener,noreferrer');
        });
    }
});
