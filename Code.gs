const SHEET_NAMES = {
  processes: 'Procesos',
  logs: 'Bitacora',
  users: 'Usuarios',
  config: 'Config'
};

const DEFAULT_FIELDS = [
  { name: 'Número de expediente', type: 'text', required: true },
  { name: 'Demandante', type: 'text', required: true },
  { name: 'Demandado', type: 'text', required: true },
  { name: 'Número de registro judicial', type: 'text', required: true },
  { name: 'Identificador de juzgado', type: 'text', required: true },
  { name: 'Abogado/Asociado asignado', type: 'text', required: true },
  { name: 'Estado del proceso', type: 'text', required: true }
];

function doGet() {
  return HtmlService.createTemplateFromFile('index')
    .evaluate()
    .setTitle('Bitácora de Procesos');
}

function include(filename) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}

function ensureSheets_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  Object.values(SHEET_NAMES).forEach((name) => {
    if (!ss.getSheetByName(name)) {
      ss.insertSheet(name);
    }
  });

  const processSheet = ss.getSheetByName(SHEET_NAMES.processes);
  if (processSheet.getLastRow() === 0) {
    processSheet.appendRow(['ID', 'Creado', 'Datos JSON']);
  }

  const logSheet = ss.getSheetByName(SHEET_NAMES.logs);
  if (logSheet.getLastRow() === 0) {
    logSheet.appendRow(['ID', 'Proceso ID', 'Fecha', 'Nota']);
  }

  const userSheet = ss.getSheetByName(SHEET_NAMES.users);
  if (userSheet.getLastRow() === 0) {
    userSheet.appendRow(['Usuario', 'Hash', 'Salt', 'Admin', 'Creado']);
  }

  const configSheet = ss.getSheetByName(SHEET_NAMES.config);
  if (configSheet.getLastRow() === 0) {
    configSheet.appendRow(['Nombre', 'Tipo', 'Requerido']);
  }
}

function getConfig() {
  ensureSheets_();
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAMES.config);
  const rows = sheet.getDataRange().getValues();
  if (rows.length <= 1) {
    saveConfig(DEFAULT_FIELDS);
    return DEFAULT_FIELDS;
  }
  return rows.slice(1).map((row) => ({
    name: row[0],
    type: row[1] || 'text',
    required: String(row[2]).toLowerCase() === 'true'
  }));
}

function saveConfig(fields) {
  ensureSheets_();
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAMES.config);
  sheet.clear();
  sheet.appendRow(['Nombre', 'Tipo', 'Requerido']);
  fields.forEach((field) => {
    sheet.appendRow([field.name, field.type, field.required ? 'true' : 'false']);
  });
  return true;
}

function isSetupNeeded() {
  ensureSheets_();
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAMES.users);
  return sheet.getLastRow() <= 1;
}

function createAdminUser(username, password) {
  ensureSheets_();
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAMES.users);
  if (sheet.getLastRow() > 1) {
    throw new Error('Ya existe un usuario administrador.');
  }
  return createUser_(username, password, true);
}

function createUser_(username, password, isAdmin) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAMES.users);
  const existing = sheet.getRange(2, 1, Math.max(sheet.getLastRow() - 1, 0), 1)
    .getValues()
    .flat()
    .filter(String);
  if (existing.includes(username)) {
    throw new Error('El usuario ya existe.');
  }
  const salt = Utilities.getUuid();
  const hash = hashPassword_(password, salt);
  const created = new Date().toISOString();
  sheet.appendRow([username, hash, salt, isAdmin ? 'true' : 'false', created]);
  return true;
}

function authenticate(username, password) {
  ensureSheets_();
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAMES.users);
  const rows = sheet.getDataRange().getValues();
  const match = rows.slice(1).find((row) => row[0] === username);
  if (!match) {
    return { ok: false, message: 'Usuario o contraseña inválidos.' };
  }
  const hash = hashPassword_(password, match[2]);
  if (hash !== match[1]) {
    return { ok: false, message: 'Usuario o contraseña inválidos.' };
  }
  return {
    ok: true,
    user: {
      username: match[0],
      isAdmin: String(match[3]).toLowerCase() === 'true'
    }
  };
}

function listProcesses() {
  ensureSheets_();
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAMES.processes);
  const rows = sheet.getDataRange().getValues();
  return rows.slice(1).map((row) => ({
    id: row[0],
    createdAt: row[1],
    data: row[2] ? JSON.parse(row[2]) : {}
  }));
}

function createProcess(data) {
  ensureSheets_();
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAMES.processes);
  const id = getNextId_('process');
  const createdAt = new Date().toISOString();
  sheet.appendRow([id, createdAt, JSON.stringify(data)]);
  return { id, createdAt };
}

function addLogEntry(processId, entryDate, note) {
  ensureSheets_();
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAMES.logs);
  const id = getNextId_('log');
  const dateValue = entryDate || new Date().toISOString().slice(0, 10);
  sheet.appendRow([id, processId, dateValue, note]);
  return true;
}

function listLogEntries(processId) {
  ensureSheets_();
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAMES.logs);
  const rows = sheet.getDataRange().getValues();
  return rows.slice(1)
    .filter((row) => String(row[1]) === String(processId))
    .map((row) => ({
      id: row[0],
      processId: row[1],
      date: row[2],
      note: row[3]
    }));
}

function hashPassword_(password, salt) {
  const digest = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    `${salt}${password}`,
    Utilities.Charset.UTF_8
  );
  return digest.map((b) => ('0' + (b & 0xff).toString(16)).slice(-2)).join('');
}

function getNextId_(key) {
  const props = PropertiesService.getScriptProperties();
  const current = Number(props.getProperty(`id_${key}`) || '0');
  const next = current + 1;
  props.setProperty(`id_${key}`, String(next));
  return next;
}
