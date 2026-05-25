(function () {
    var navigation = document.querySelector('.l-navigation');
    var menuToggle = document.querySelector('.js-menu-toggle');
    var menuClose = document.querySelector('.js-menu-close');
    var menuPin = document.querySelector('.js-menu-pin');

    if (menuToggle) {
        menuToggle.addEventListener('click', function () {
            navigation.classList.toggle('is-collapsed');
        });
    }

    if (menuClose) {
        menuClose.addEventListener('click', function () {
            navigation.classList.add('is-collapsed');
            document.activeElement.blur();
        });
    }

    if (menuPin) {
        menuPin.addEventListener('click', function () {
            navigation.classList.toggle('is-pinned');
            var icon = menuPin.querySelector('i');
            if (navigation.classList.contains('is-pinned')) {
                icon.classList.add('p-icon--close');
                icon.classList.remove('p-icon--pin');
            } else {
                icon.classList.add('p-icon--pin');
                icon.classList.remove('p-icon--close');
            }
            document.activeElement.blur();
        });
    }
})();
