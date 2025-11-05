// Google Apps Script Web App for Suggestions CRUD (Sheet-backed)
// Usage: Bind this script to your Google Sheet (Extensions → Apps Script),
// then Deploy as Web App (execute as: Me, access: Anyone). Copy the URL.

const SHEET_NAME = '';
const HEADERS = ['Title', 'Description', 'Likes'];
const START_ROW = 2; // row 1 = headers
const COL = { TITLE: 1, DESCRIPTION: 2, LIKES: 3 };

function getSpreadsheet_() {
  // If script is bound to a Sheet, this returns the active file;
  // otherwise you can open by ID: SpreadsheetApp.openById('YOUR_SHEET_ID')
  return SpreadsheetApp.getActive();
}

function getSheet_() {
  const ss = getSpreadsheet_();
  let sh = SHEET_NAME ? ss.getSheetByName(SHEET_NAME) : ss.getSheets()[0];
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME || 'Suggerimenti');
  }
  // Ensure headers
  const headerRange = sh.getRange(1, 1, 1, HEADERS.length);
  const existing = headerRange.getValues()[0];
  let mismatch = false;
  for (let i = 0; i < HEADERS.length; i++) {
    if (String(existing[i] || '') !== HEADERS[i]) { mismatch = true; break; }
  }
  if (mismatch) headerRange.setValues([HEADERS]);
  return sh;
}

function list_() {
  const sh = getSheet_();
  const lastRow = sh.getLastRow();
  if (lastRow < START_ROW) return [];
  const values = sh.getRange(START_ROW, 1, lastRow - START_ROW + 1, HEADERS.length).getValues();
  const items = [];
  for (let i = 0; i < values.length; i++) {
    const row = START_ROW + i;
    const [title, description, likes] = values[i];
    if (!title && !description) continue;
    items.push({
      row: row,
      title: String(title || ''),
      description: String(description || ''),
      likes: Number(likes || 0)
    });
  }
  return items;
}

function create_(title, description) {
  const sh = getSheet_();
  title = String(title || '').trim();
  if (!title) throw new Error("'title' is required");
  sh.appendRow([title, String(description || ''), 0]);
  const row = sh.getLastRow();
  return { status: 'ok', row: row };
}

function like_(row) {
  const sh = getSheet_();
  row = Number(row);
  if (!row || row < START_ROW) throw new Error('invalid row');
  const current = Number(sh.getRange(row, COL.LIKES).getValue() || 0);
  const next = current + 1;
  sh.getRange(row, COL.LIKES).setValue(next);
  return { row: row, likes: next };
}

function parseBody_(e) {
  // Merge JSON body, URL-encoded params and query params
  let payload = {};
  try {
    if (e && e.postData && e.postData.contents) {
      if (e.postData.type === 'application/json') {
        payload = JSON.parse(e.postData.contents);
      } else if (e.postData.type === 'text/plain') {
        try { payload = JSON.parse(e.postData.contents); } catch (_) { payload = {}; }
      } else {
        // application/x-www-form-urlencoded or others: use e.parameter
        payload = Object.assign({}, e.parameter || {});
      }
    }
  } catch (_) {}
  payload = Object.assign({}, e && e.parameter ? e.parameter : {}, payload);
  return payload;
}

function doGet(e) {
  const action = ((e && e.parameter && e.parameter.action) || 'list').toLowerCase();
  try {
    if (action === 'list') {
      return jsonOrJsonp_(e, list_());
    } else if (action === 'health') {
      return jsonOrJsonp_(e, { ok: true });
    }
    throw new Error('unknown action');
  } catch (err) {
    return jsonOrJsonp_(e, { error: String(err && err.message || err) });
  }
}

function doPost(e) {
  const body = parseBody_(e);
  const action = String(body.action || (e && e.parameter && e.parameter.action) || '').toLowerCase();
  try {
    if (action === 'create') {
      const title = body.title;
      const description = body.description;
      return json_(create_(title, description));
    } else if (action === 'like') {
      const row = body.row || body.id;
      return json_(like_(row));
    } else if (action === 'health') {
      return json_({ ok: true });
    }
    throw new Error('unknown action');
  } catch (err) {
    return json_({ error: String(err && err.message || err) });
  }
}

function json_(obj) {
  // Web Apps in Apps Script always return 200; we embed the status in the body if needed.
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function jsonOrJsonp_(e, obj) {
  const cb = e && e.parameter ? e.parameter.callback : null;
  if (cb) {
    // JSONP response for cross-origin GET without CORS
    const body = `${cb}(${JSON.stringify(obj)})`;
    return ContentService
      .createTextOutput(body)
      .setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return json_(obj);
}

function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('Suggestions API')
    .addItem('Init headers', 'getSheet_')
    .addItem('List preview', 'menuPreview_')
    .addToUi();
}

function menuPreview_() {
  const items = list_();
  SpreadsheetApp.getUi().alert('Items: ' + items.length);
}
