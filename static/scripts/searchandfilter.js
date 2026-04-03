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

        // Prepare dynamic chip filters.
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
        });

        panel.addEventListener('focusin', function() {
            togglePanel(container, panel, false);
        });

        panel.addEventListener('focusout', function() {
            schedulePanelCloseCheck();
        });
    });
});
