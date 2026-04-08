/**
 * Client-side search and filter for the merges table.
 * Filters by package text, milestone, status, and assignee.
 */

/**
  Toggles visibility of filter panel.
  @param {HTMLElement} panel Filter panel to show or hide.
*/
function togglePanel(container, panel, collapse) {
  if (typeof collapse === 'undefined') {
    collapse = panel.getAttribute('aria-hidden') !== 'false';
  }
  if (panel && container) {
    if (collapse) {
      panel.setAttribute('aria-hidden', 'true');
      container.setAttribute('aria-expanded', 'false');
    } else {
      panel.setAttribute('aria-hidden', 'false');
      container.setAttribute('aria-expanded', 'true');
    }
  }
}

/**
 * Converts chip text to expected table value for comparison.
 * @param {string} value The chip text value.
 * @returns {string} The expected table value.
 */
function getStandardEntryFromChipText(value) {
    if (value == "UNASSIGNED") {
        return '—';
    }

    return String(value || '').trim().toLowerCase();
}

/**
 * Gets the value of a search and filter chip for a given filter type.
 * @param {HTMLTableRowElement} row The table row element.
 * @param {number} columnIndex The index of the filtered data in the table.
 * @returns {string} The expected table value of the found chip.
 */
function getRowFilterValue(row, columnIndex) {
    let cells = row.querySelectorAll('th, td');

    if (columnIndex < 0 || columnIndex >= cells.length) {
        return '';
    }

    return getStandardEntryFromChipText(cells[columnIndex].textContent);
}

document.addEventListener('DOMContentLoaded', function () {
    // Add click handler for clicks on elements with aria-controls
    [].slice.call(document.querySelectorAll('.p-search-and-filter')).forEach(function(pattern) {
        var input = pattern.querySelector('.p-search-and-filter__input');
        var container = pattern.querySelector('.p-search-and-filter__search-container');
        var panel = pattern.querySelector('.p-search-and-filter__panel');
        var chips = [].slice.call(pattern.querySelectorAll('.p-chip[data-filter-type]'));
        var tableBody = document.querySelector('.p-panel__content tbody');
        var tableHead = document.querySelector('.p-panel__content thead');

        if (!input || !container || !panel || !tableBody || !tableHead) {
            return;
        }

        var columnIndexMap = {};
        [].slice.call(tableHead.querySelectorAll('th')).forEach(function(th, i) {
            columnIndexMap[th.textContent.trim().toLowerCase()] = i;
        });

        var mergeRows = [].slice.call(tableBody.querySelectorAll('tr')).filter(function(row) {
            return row.children.length === 5;
        });

        var activeFilters = {
            milestone: new Set(),
            status: new Set(),
            assignee: new Set()
        };

        var selectedChipsContainer = pattern.querySelector('.p-search-and-filter__selected-chips');
        var noResultsRow = tableBody.querySelector('.js-no-filter-results');

        // Show or hide table rows based on selected chips in search and filter panel.
        function applyChipFilters() {
            var visibleCount = 0;

            mergeRows.forEach(function(row) {
                let isVisible = true;

                Object.keys(activeFilters).forEach(function(filterType) {
                    let selectedValues = activeFilters[filterType];

                    if (selectedValues.size > 0) {
                        let rowValue = getRowFilterValue(row, columnIndexMap[filterType]);

                        if (!selectedValues.has(rowValue)) {
                            isVisible = false;
                        }
                    }
                });

                row.hidden = !isVisible;

                if (isVisible) {
                    visibleCount += 1;
                }
            });

            noResultsRow.hidden = visibleCount > 0;
        }

        var selectedChipsContainer = pattern.querySelector('.p-search-and-filter__selected-chips');

        // Update the display of selected chips in the search bar.
        function updateSelectedChipsDisplay() {
            selectedChipsContainer.innerHTML = '';

            var hasSelected = false;

            Object.keys(activeFilters).forEach(function(filterType) {
                activeFilters[filterType].forEach(function(filterValue) {
                    hasSelected = true;

                    var label = filterType.charAt(0).toUpperCase() + filterType.slice(1);
                    var chipEl = document.createElement('span');
                    chipEl.className = 'p-chip';

                    var leadEl = document.createElement('span');
                    leadEl.className = 'p-chip__lead';
                    leadEl.textContent = label.toUpperCase();

                    var valueEl = document.createElement('span');
                    valueEl.className = 'p-chip__value';
                    valueEl.textContent = filterValue;

                    var dismissBtn = document.createElement('button');
                    dismissBtn.className = 'p-chip__dismiss';
                    dismissBtn.setAttribute('aria-label', 'Dismiss ' + label + ' filter');
                    dismissBtn.type = 'button';
                    dismissBtn.textContent = 'Dismiss';

                    dismissBtn.addEventListener('click', function(e) {
                        e.preventDefault();
                        e.stopPropagation();

                        activeFilters[filterType].delete(filterValue);

                        var filterChip = [].slice.call(chips).find(function(c) {
                            return c.getAttribute('data-filter-type') === filterType &&
                                   getStandardEntryFromChipText(c.getAttribute('data-filter-value')) === filterValue;
                        });

                        if (filterChip) {
                            filterChip.classList.remove('is-active');
                            filterChip.setAttribute('aria-pressed', 'false');
                        }

                        updateSelectedChipsDisplay();
                        applyChipFilters();
                    });

                    chipEl.appendChild(leadEl);
                    chipEl.appendChild(valueEl);
                    chipEl.appendChild(dismissBtn);
                    selectedChipsContainer.appendChild(chipEl);
                });
            });

            container.setAttribute('data-active', hasSelected ? 'true' : 'false');
            container.setAttribute('data-empty', hasSelected ? 'false' : 'true');
        }

        // Prepare chip filtering while typing in the search bar.
        // Remove chips that do not match search text, and hide empty sections as needed.
        var filterSections = [].slice.call(panel.querySelectorAll('.p-filter-panel-section'));

        function applyChipSearchFilter(searchText) {
            var normalizedSearchText = String(searchText || '').trim().toLowerCase();
            var visibleChipCount = 0;
            var visibleSectionCount = 0;

            chips.forEach(function(chip) {
                var chipValue = String(chip.getAttribute('data-filter-value') || '').trim().toLowerCase();
                var shouldShow = !normalizedSearchText || chipValue.indexOf(normalizedSearchText) !== -1;
                chip.hidden = !shouldShow;
                chip.style.display = shouldShow ? '' : 'none';

                if (shouldShow) {
                    visibleChipCount += 1;
                }
            });

            filterSections.forEach(function(section) {
                var sectionVisibleChipCount = section.querySelectorAll('.p-chip[data-filter-type]:not([hidden])').length;
                var showSection = sectionVisibleChipCount > 0;

                section.hidden = !showSection;
                section.style.display = showSection ? '' : 'none';

                if (showSection) {
                    visibleSectionCount += 1;
                }
            });

            if (normalizedSearchText && visibleChipCount === 0 && visibleSectionCount === 0) {
                panel.style.display = 'none';
                panel.hidden = true;
                togglePanel(container, panel, true);
            } else {
                panel.style.display = '';
                panel.hidden = false;

                if (document.activeElement === input || panel.contains(document.activeElement)) {
                    togglePanel(container, panel, false);
                }
            }
        }

        // 100ms search debounce for chip filtering.
        var chipSearchDebounceTimer;
        function scheduleChipSearchFilterUpdate() {
            window.clearTimeout(chipSearchDebounceTimer);

            chipSearchDebounceTimer = window.setTimeout(function() {
                applyChipSearchFilter(input.value);
            }, 100);
        }

        input.addEventListener('input', scheduleChipSearchFilterUpdate);
        input.addEventListener('keyup', scheduleChipSearchFilterUpdate);
        input.addEventListener('search', scheduleChipSearchFilterUpdate);

        // Prepare filtering when chip selected.
        chips.forEach(function(chip) {
            let filterType = chip.getAttribute('data-filter-type');
            let filterValue = getStandardEntryFromChipText(chip.getAttribute('data-filter-value'));

            chip.setAttribute('aria-pressed', 'false');

            chip.addEventListener('click', function() {
                let selectedValues = activeFilters[filterType];

                if (!selectedValues) {
                    return;
                }

                if (selectedValues.has(filterValue)) {
                    selectedValues.delete(filterValue);
                    chip.classList.remove('is-active');
                    chip.setAttribute('aria-pressed', 'false');
                } else {
                    selectedValues.add(filterValue);
                    chip.classList.add('is-active');
                    chip.setAttribute('aria-pressed', 'true');
                }

                input.value = '';
                applyChipSearchFilter('');

                updateSelectedChipsDisplay();
                applyChipFilters();
            });
        });

        function schedulePanelCloseCheck() {
            window.setTimeout(function() {
                // Keep the panel open while focus remains within this widget (e.g. chip clicks).
                if (!pattern.contains(document.activeElement)) {
                    togglePanel(container, panel, true);
                }
            }, 0);
        }

        input.addEventListener('blur', function() {
            schedulePanelCloseCheck();
        });

        input.addEventListener('focus', function() {
            togglePanel(container, panel, false);
            applyChipSearchFilter(input.value);
        });

        panel.addEventListener('focusin', function() {
            togglePanel(container, panel, false);
        });

        panel.addEventListener('focusout', function() {
            schedulePanelCloseCheck();
        });
    });
});
