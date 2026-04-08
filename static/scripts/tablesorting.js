/**
 * Sorts a table by the column specified.
 * @param {HTMLElement} header Sortable header element that was clicked.
 * @param {HTMLTableElement} table Table to sort.
 */
function sortTable(header, table) {
  var SORTABLE_STATES = {
    none: 0,
    ascending: -1,
    descending: 1,
    ORDER: ['none', 'ascending', 'descending'],
  };

  // Get index of column based on position of header cell in <thead>
  var headerCells = [].slice.call(table.tHead.rows[0].cells);
  var col = -1;
  for (var x = 0; x < headerCells.length; x += 1) {
    if (headerCells[x] === header) {
      col = x;
      break;
    }
  }

  if (col === -1) {
    return;
  }

  // Based on the current aria-sort value, get the next state.
  var newOrder = SORTABLE_STATES.ORDER.indexOf(header.getAttribute('aria-sort')) + 1;
  newOrder = newOrder > SORTABLE_STATES.ORDER.length - 1 ? 0 : newOrder;
  newOrder = SORTABLE_STATES.ORDER[newOrder];

  // Reset all header sorts.
  var headerSorts = table.querySelectorAll('[aria-sort]');
  for (var i = 0, ii = headerSorts.length; i < ii; i += 1) {
    headerSorts[i].setAttribute('aria-sort', 'none');
  }

  // Set the new header sort.
  header.setAttribute('aria-sort', newOrder);

  var direction = SORTABLE_STATES[newOrder];
  var body = table.tBodies[0];

  // Separate data rows from state rows
  var dataRows = [];
  var stateRows = [];

  [].slice.call(body.rows).forEach(function(row) {
    if (row.getAttribute('data-index') !== null) {
      dataRows.push(row);
    } else {
      stateRows.push(row);
    }
  });

  // If the direction is 0 ignore sorting for column.
  if (direction === 0) {
    dataRows.sort(function(a, b) {
      return a.getAttribute('data-index') - b.getAttribute('data-index');
    });
  } else {
    // Pre-extract content to avoid live collection problems
    var rowContent = dataRows.map(function(row) {
      var content = row.cells[col] ? row.cells[col].textContent.trim() : '';
      return { row: row, content: content };
    });

    // Sort extracted data
    rowContent.sort(function(a, b) {
      var strA = String(a.content).toLowerCase();
      var strB = String(b.content).toLowerCase();
      var comparison = strA < strB ? -1 : strA > strB ? 1 : 0;
      return direction === -1 ? comparison : -comparison;
    });

    // Update dataRows with sorted rows
    dataRows = rowContent.map(function(item) { return item.row; });
  }

  // Rebuild tbody
  var allRows = dataRows.concat(stateRows);
  while (body.firstChild) {
    body.removeChild(body.firstChild);
  }
  for (i = 0; i < allRows.length; i += 1) {
    body.appendChild(allRows[i]);
  }
}

function setupClickableHeader(table, header) {
  header.addEventListener('click', function() {
    sortTable(header, table);
  });
}

/**
 * Initializes a sortable table by assigning event listeners to sortable column headers.
 * @param {HTMLTableElement} table
 */
function setupSortableTable(table) {
  // Assume only one tbody is in the table.
  var rows = table.tBodies[0].rows;
  // Set an index for the default order.
  for (var row = 0, totalRows = rows.length; row < totalRows; row += 1) {
    rows[row].setAttribute('data-index', row);
  }

  // Select sortable column headers.
  var clickableHeaders = table.querySelectorAll('th[aria-sort]');
  // Attach the click event for each header.
  for (var i = 0, ii = clickableHeaders.length; i < ii; i += 1) {
    setupClickableHeader(table, clickableHeaders[i]);
  }
}

// Initialize when DOM is ready so tables in the body exist.
document.addEventListener('DOMContentLoaded', function () {
  // Make all tables on the page sortable.
  var tables = document.querySelectorAll('table');

  for (var i = 0, ii = tables.length; i < ii; i += 1) {
    setupSortableTable(tables[i]);
  }
});
