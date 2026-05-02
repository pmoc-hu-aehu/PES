// ============================================================
// SICOR — Bot RPA | Google Apps Script Backend
// Execute setupPlanilha() uma vez após criar a planilha.
// ============================================================

const SHEET_CODIGOS    = 'Codigos';
const SHEET_RESULTADOS = 'Resultados';


// ── Roteador GET ─────────────────────────────────────────────

function doGet(e) {
  const action = e.parameter.action;
  if (action === 'getPending')       return _getPendingJson();
  if (action === 'diagnostico')      return _diagnosticoJson();
  if (action === 'listarCodigos')    return _json(listarCodigos());
  if (action === 'listarResultados') return _json(listarResultados());
  if (action === 'getBotState')      return _json(getBotState());
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('SICOR — Bot RPA')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function _diagnosticoJson() {
  const info = { ok: false, ss: null, sheets: [], error: null };
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    if (!ss) throw new Error('getActiveSpreadsheet() retornou null — script não está vinculado à planilha.');
    info.ss = ss.getName();
    info.sheets = ss.getSheets().map(s => s.getName());
    const cod = ss.getSheetByName(SHEET_CODIGOS);
    const res = ss.getSheetByName(SHEET_RESULTADOS);
    info.codigos_rows    = cod ? cod.getLastRow() : 'aba não existe';
    info.resultados_rows = res ? res.getLastRow() : 'aba não existe';
    info.ok = true;
  } catch(err) {
    info.error = err.message;
  }
  return _json(info);
}

// ── Roteador POST ────────────────────────────────────────────

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    switch (data.action) {
      case 'saveResults':  return _saveResultsHandler(data);
      case 'updateStatus': return _updateStatusHandler(data);
      case 'heartbeat':    return _heartbeatHandler(data);
    }
    return _json({ success: false, error: 'Ação desconhecida' });
  } catch (err) {
    return _json({ success: false, error: err.message });
  }
}

// ── Chamadas pelo painel HTML (google.script.run) ─────────────

function adicionarCodigos(codigosStr) {
  const sheet = _sheet(SHEET_CODIGOS);
  if (!sheet) throw new Error('Aba "Codigos" não encontrada. Execute setupPlanilha() no editor GAS primeiro.');
  const codigos = codigosStr.split('\n').map(c => c.trim()).filter(c => c.length > 0);
  if (!codigos.length) return { success: false, added: 0 };
  const now  = new Date().toLocaleString('pt-BR');
  const rows = codigos.map(c => [c, 'Pendente', now, '']);
  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, 4).setValues(rows);
  return { success: true, added: rows.length };
}

function startBot(codigosStr) {
  const result = codigosStr ? adicionarCodigos(codigosStr) : { added: 0 };
  PropertiesService.getScriptProperties().setProperty('BOT_COMMAND', 'RUN');
  return { success: true, added: result.added };
}

function stopBot() {
  PropertiesService.getScriptProperties().setProperty('BOT_COMMAND', 'STOP');
  return { success: true };
}

function pauseBot() {
  PropertiesService.getScriptProperties().setProperty('BOT_COMMAND', 'PAUSE');
  return { success: true };
}

function resumeBot() {
  PropertiesService.getScriptProperties().setProperty('BOT_COMMAND', 'RUN');
  return { success: true };
}

function getBotState() {
  const p = PropertiesService.getScriptProperties();
  return {
    command:  p.getProperty('BOT_COMMAND')   || 'IDLE',
    hostname: p.getProperty('BOT_HOSTNAME')  || '',
    lastSeen: p.getProperty('BOT_LAST_SEEN') || '',
  };
}

function listarCodigos() {
  const sheet = _sheet(SHEET_CODIGOS);
  if (!sheet) { Logger.log('listarCodigos: aba não encontrada'); return []; }
  const data = sheet.getDataRange().getValues();
  Logger.log('listarCodigos: ' + data.length + ' linha(s) na aba');
  if (data.length < 2) return [];
  return data.slice(1).map(r => ({
    codigo: r[0], status: r[1], adicionado: r[2], processado: r[3]
  }));
}

function listarResultados() {
  const sheet = _sheet(SHEET_RESULTADOS);
  if (!sheet) return [];
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  const numCols  = Math.min(sheet.getLastColumn(), 13);
  const startRow = Math.max(2, lastRow - 299);
  const numRows  = lastRow - startRow + 1;
  const data = sheet.getRange(startRow, 1, numRows, numCols).getValues();
  return data.map(r => ({
    codigo:       _cell(r[0]),  material:     _cell(r[1]),
    req:          _cell(r[2]),  data_req:     _cell(r[3]),
    situacao:     _cell(r[4]),  qtde:         _cell(r[5]),
    vlr_req:      _cell(r[6]),  vlr_emp:      _cell(r[7]),
    documento:    _cell(r[8]),  oc:           _cell(r[9]),
    data_emissao: _cell(r[10]), c_custo:      _cell(r[11])
  }));
}

function buscarResultadosFiltrados(f) {
  const sheet = _sheet(SHEET_RESULTADOS);
  if (!sheet) return { rows: [], total: 0 };
  const data = sheet.getDataRange().getValues();
  if (data.length < 2) return { rows: [], total: 0 };

  const total = data.length - 1;

  const rows = data.slice(1).filter(r => {
    const ocVal = String(r[9] || '').trim();
    if (f.ocTipo === 'tem' && !ocVal)  return false;
    if (f.ocTipo === 'sem' &&  ocVal)  return false;
    if (f.oc       && !ocVal.toLowerCase().includes(f.oc))                    return false;
    if (f.req      && !String(r[2] ||'').toLowerCase().includes(f.req))      return false;
    if (f.material && !String(r[1] ||'').toLowerCase().includes(f.material)
                   && !String(r[0] ||'').toLowerCase().includes(f.material)) return false;
    if (f.situacao && !String(r[4] ||'').toLowerCase().includes(f.situacao)) return false;
    if (f.dataDe || f.dataAte) {
      const raw = String(r[3]||'');
      const p   = raw.split('/');
      if (p.length === 3) {
        const d = new Date(+p[2], +p[1]-1, +p[0]);
        if (f.dataDe) {
          const pd = f.dataDe.split('/');
          if (pd.length===3 && d < new Date(+pd[2],+pd[1]-1,+pd[0])) return false;
        }
        if (f.dataAte) {
          const pa = f.dataAte.split('/');
          if (pa.length===3 && d > new Date(+pa[2],+pa[1]-1,+pa[0])) return false;
        }
      }
    }
    return true;
  }).map(r => ({
    codigo:       _cell(r[0]),  material:     _cell(r[1]),
    req:          _cell(r[2]),  data_req:     _cell(r[3]),
    situacao:     _cell(r[4]),  qtde:         _cell(r[5]),
    vlr_req:      _cell(r[6]),  vlr_emp:      _cell(r[7]),
    documento:    _cell(r[8]),  oc:           _cell(r[9]),
    data_emissao: _cell(r[10]), c_custo:      _cell(r[11])
  }));

  return { rows, total };
}

function contarResultados() {
  const sheet = _sheet(SHEET_RESULTADOS);
  if (!sheet) return { total:0, comOC:0, semOC:0, semDados:0 };
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { total:0, comOC:0, semOC:0, semDados:0 };
  const total = lastRow - 1;
  // Lê só as 2 colunas necessárias: J=OC (col 10), E=Situação (col 5)
  const colOC  = sheet.getRange(2, 10, total, 1).getValues();
  const colSit = sheet.getRange(2,  5, total, 1).getValues();
  const comOC   = colOC.filter(r  => r[0] && String(r[0]).trim()).length;
  const semDados = colSit.filter(r => !r[0] || !String(r[0]).trim()).length;
  return { total, comOC, semOC: total - comOC, semDados };
}

function reprocessarCodigos(codigosStr) {
  const codigos = codigosStr.split('\n').map(c => c.trim()).filter(c => c.length > 0);
  if (!codigos.length) return { success: false, error: 'Nenhum código' };

  const codSheet = _sheet(SHEET_CODIGOS);
  const resSheet = _sheet(SHEET_RESULTADOS);

  // Apaga resultados existentes para esses códigos (de baixo para cima)
  const resData = resSheet.getDataRange().getValues();
  let delRes = 0;
  for (let i = resData.length - 1; i >= 1; i--) {
    if (codigos.includes(String(resData[i][0]).trim())) {
      resSheet.deleteRow(i + 1);
      delRes++;
    }
  }

  // Redefine status para Pendente na aba Codigos
  const codData = codSheet.getDataRange().getValues();
  const found = new Set();
  for (let i = 1; i < codData.length; i++) {
    if (codigos.includes(String(codData[i][0]).trim())) {
      codSheet.getRange(i + 1, 2).setValue('Pendente');
      codSheet.getRange(i + 1, 4).setValue('');
      found.add(String(codData[i][0]).trim());
    }
  }

  // Adiciona códigos que não existiam na fila
  const now = new Date().toLocaleString('pt-BR');
  const novos = codigos.filter(c => !found.has(c));
  if (novos.length) {
    const rows = novos.map(c => [c, 'Pendente', now, '']);
    codSheet.getRange(codSheet.getLastRow() + 1, 1, rows.length, 4).setValues(rows);
  }

  PropertiesService.getScriptProperties().setProperty('BOT_COMMAND', 'RUN');
  return { success: true, reprocessed: codigos.length, resultadosApagados: delRes };
}

function limparConcluidos() {
  const sheet = _sheet(SHEET_CODIGOS);
  const data  = sheet.getDataRange().getValues();
  for (let i = data.length - 1; i >= 1; i--) {
    if (data[i][1] === 'Concluído') sheet.deleteRow(i + 1);
  }
  return { success: true };
}

function limparResultados() {
  const sheet = _sheet(SHEET_RESULTADOS);
  const last  = sheet.getLastRow();
  if (last > 1) sheet.deleteRows(2, last - 1);
  return { success: true };
}

function deletarResultadosSelecionados(indices) {
  const sheet = _sheet(SHEET_RESULTADOS);
  // indices são 0-based a partir dos dados (sem header); apaga de baixo para cima
  const sorted = [...indices].sort((a, b) => b - a);
  for (const i of sorted) {
    sheet.deleteRow(i + 2); // +1 header +1 base-1
  }
  return { success: true };
}

// ── Chamadas pelo Python via HTTP ─────────────────────────────

function _getPendingJson() {
  const p       = PropertiesService.getScriptProperties();
  const command = p.getProperty('BOT_COMMAND') || 'IDLE';

  if (command !== 'RUN') {
    return _json({ success: true, pending: [], command });
  }

  const sheet   = _sheet(SHEET_CODIGOS);
  const data    = sheet.getDataRange().getValues();
  const pending = [];

  for (let i = 1; i < data.length; i++) {
    if (data[i][1] === 'Pendente') {
      pending.push({ row: i + 1, codigo: String(data[i][0]) });
      sheet.getRange(i + 1, 2).setValue('Processando');
    }
  }

  if (!pending.length) {
    p.setProperty('BOT_COMMAND', 'IDLE');
  }

  return _json({ success: true, pending, command });
}

function _heartbeatHandler(data) {
  const p   = PropertiesService.getScriptProperties();
  const now = new Date().toISOString();
  p.setProperty('BOT_HOSTNAME',  data.hostname || '');
  p.setProperty('BOT_LAST_SEEN', now);
  const command = p.getProperty('BOT_COMMAND') || 'IDLE';
  return _json({ success: true, command });
}

function _saveResultsHandler(data) {
  const resSheet = _sheet(SHEET_RESULTADOS);
  const codSheet = _sheet(SHEET_CODIGOS);
  const now      = new Date().toLocaleString('pt-BR');

  for (const r of data.results) {
    resSheet.appendRow([
      r.codigo, r.material, r.req, r.data_req, r.situacao,
      r.qtde, r.vlr_req, r.vlr_emp, r.documento,
      r.oc, r.data_emissao, r.c_custo, now
    ]);
    _markStatus(codSheet, r.codigo, 'Concluído');
  }
  return _json({ success: true });
}

function _updateStatusHandler(data) {
  _markStatus(_sheet(SHEET_CODIGOS), data.codigo, data.status);
  return _json({ success: true });
}

function _markStatus(sheet, codigo, status) {
  const data = sheet.getDataRange().getValues();
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][0]) === String(codigo)) {
      sheet.getRange(i + 1, 2).setValue(status);
      if (status !== 'Pendente') {
        sheet.getRange(i + 1, 4).setValue(new Date().toLocaleString('pt-BR'));
      }
      return;
    }
  }
}

// ── Helpers ──────────────────────────────────────────────────

function _cell(v) {
  if (v instanceof Date) return Utilities.formatDate(v, Session.getScriptTimeZone(), 'dd/MM/yyyy');
  return v == null ? '' : String(v);
}

function _sheet(name) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) throw new Error('Planilha não encontrada. Abra o script dentro da planilha (Extensões → Apps Script).');
  return ss.getSheetByName(name);
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ── Setup inicial (execute uma vez) ──────────────────────────

function setupPlanilha() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  let cod = ss.getSheetByName(SHEET_CODIGOS);
  if (!cod) cod = ss.insertSheet(SHEET_CODIGOS);
  cod.clearContents();
  const hCod = cod.getRange(1, 1, 1, 4);
  hCod.setValues([['Codigo', 'Status', 'Adicionado_em', 'Processado_em']]);
  hCod.setFontWeight('bold').setBackground('#0F172A').setFontColor('white');
  cod.setColumnWidths(1, 4, 160);

  let res = ss.getSheetByName(SHEET_RESULTADOS);
  if (!res) res = ss.insertSheet(SHEET_RESULTADOS);
  res.clearContents();
  const hRes = res.getRange(1, 1, 1, 13);
  hRes.setValues([[
    'Codigo','Material','Req','Data_Req','Situacao',
    'Qtde','Vlr_Req','Vlr_Emp','Documento','O.C.','Data_Emissao','C.Custo','Extraido_em'
  ]]);
  hRes.setFontWeight('bold').setBackground('#0F172A').setFontColor('white');
  res.setColumnWidth(2, 300);
  res.setColumnWidth(9, 280);

  SpreadsheetApp.getUi().alert('Planilha configurada com sucesso!');
}
