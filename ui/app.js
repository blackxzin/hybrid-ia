'use strict';
const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.hash.slice(1));
const token = params.get('token') || sessionStorage.getItem('hybrid-token') || '';
if (token) sessionStorage.setItem('hybrid-token', token);
history.replaceState(null, '', '/');
let active = null, previewId = null, skills = [];
async function api(path, body) {
  const response = await fetch('/api/' + path, {method: body === undefined ? 'GET' : 'POST', headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)});
  if (!response.ok) {const result = await response.json(); throw new Error(result.error || 'Falha no pedido');}
  return response;
}
function status(text) {$('status').textContent = text;}
function message(role, text) {
  const article = document.createElement('article'); article.className = role;
  const label = document.createElement('strong'); label.textContent = role === 'user' ? 'VOCÊ' : 'ASSISTENTE';
  const content = document.createElement('pre'); content.textContent = text;
  article.append(label, content); $('messages').append(article); article.scrollIntoView({block: 'nearest'}); return content;
}
async function refresh() {
  const data = await (await api('models')).json();
  const current = $('model').value; $('model').replaceChildren(new Option('Configurado no projeto', ''));
  data.models.forEach(item => $('model').add(new Option(item.model + ' · ' + item.provider, item.key)));
  if (current && [...$('model').options].some(item => item.value === current)) $('model').value = current;
  else if (data.models.length) $('model').value = data.models[0].key;
  $('availability').textContent = data.models.length + ' modelos disponíveis.' + (data.errors.length ? ' Indisponível: ' + data.errors.map(item => item.provider).join(', ') : '');
  skills = (await (await api('skills')).json()).skills; renderSkills();
  const sessions = await (await api('sessions')).json(); $('sessions').replaceChildren(...sessions.sessions.map(name => new Option(name, name)));
}
function renderSkills() {
  const current = $('skill').value, query = $('skill-filter').value.toLocaleLowerCase();
  $('skill').replaceChildren(new Option('Auto · conforme o pedido', 'auto'), new Option('Sem skill', 'none'));
  skills.filter(item => (item.name + ' ' + item.description).toLocaleLowerCase().includes(query)).forEach(item => $('skill').add(new Option(item.name + ' · ' + item.description, item.name)));
  if ([...$('skill').options].some(item => item.value === current)) $('skill').value = current;
}
$('skill-filter').oninput = () => {renderSkills(); showSkill().catch(error => status(error.message));};
async function showSkill() {
  const name = $('skill').value;
  $('skill-content').textContent = name === 'auto' ? 'Auto seleciona uma skill por pedido.' : name === 'none' ? 'Nenhuma skill será carregada.' : (await (await api('skill', {name})).json()).content;
}
$('skill').onchange = () => showSkill().catch(error => status(error.message));
function guarded(fn) {return async event => {try {await fn(event);} catch (error) {status(error.message);}};}
$('refresh').onclick = guarded(refresh);
$('load').onclick = guarded(async () => {if (active) return; const data = await (await api('session', {name: $('session').value})).json(); $('messages').replaceChildren(); data.messages.forEach(item => message(item.role, item.content)); status('Sessão carregada');});
$('clear').onclick = () => {if (active) return; $('session').value = ''; $('messages').replaceChildren(); status('Nova conversa sem persistência');};
$('chat').onsubmit = guarded(async event => {
  event.preventDefault(); if (active) return;
  const request = $('prompt').value.trim(); if (!request) return;
  const session = $('session').value.trim(); if (session && !/^[A-Za-z0-9_-]{1,64}$/.test(session)) throw new Error('Sessão: use letras, números, _ ou - (até 64).');
  active = crypto.randomUUID(); $('send').disabled = true; $('cancel').disabled = false;
  message('user', request); const output = message('assistant', ''); status('Gerando…');
  let completed = false;
  try {
    const response = await api('chat', {id: active, request, model: $('model').value, mode: $('mode').value, session, skill: $('skill').value, auto_context: $('context').checked});
    const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '';
    while (true) {
      const {value, done} = await reader.read(); buffer += decoder.decode(value, {stream: !done});
      let newline;
      while ((newline = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1); if (!line) continue;
        const data = JSON.parse(line);
        if (data.type === 'token') output.textContent += data.text;
        if (data.type === 'done') {output.textContent = data.answer; const m = data.metrics; $('metrics').textContent = `${m.effective_mode} · ${m.status}\n${m.total_seconds.toFixed(2)} s\nEntrada local: ${m.local_input_tokens} tokens\nSaída local: ${m.local_output_tokens} tokens\nChamadas externas: ${m.external_attempts}\nRevisão: ${m.review_status}\nSkill: ${m.selected_skill}`; status('Concluído'); completed = true;}
        if (data.type === 'cancelled') {status('Cancelado · resposta parcial'); completed = true;}
        if (data.type === 'error') throw new Error(data.error);
      }
      if (done) break;
    }
    if (!completed) throw new Error('Conexão encerrada antes da conclusão');
  } finally {active = null; $('send').disabled = false; $('cancel').disabled = true;}
});
$('cancel').onclick = guarded(async () => {if (active) {await api('cancel', {id: active}); status('Cancelamento solicitado; aguardando o servidor interromper');}});
$('search').onclick = guarded(async () => {$('search-results').textContent = (await (await api('search', {query: $('query').value})).json()).context || 'Nenhum resultado.';});
$('patch').oninput = () => {previewId = null; $('apply').disabled = true;};
$('preview').onclick = guarded(async () => {const data = await (await api('patch/preview', {patch: $('patch').value})).json(); previewId = data.id; $('patch-preview').textContent = data.diff; $('apply').disabled = false; $('patch-result').textContent = '';});
$('apply').onclick = guarded(async () => {if (!previewId) return; $('apply').disabled = true; const id = previewId; previewId = null; const data = await (await api('patch/apply', {id, confirm: true, allow_exec: $('allow-exec').checked})).json(); $('patch-result').textContent = 'Arquivos alterados:\n' + data.files.join('\n') + '\n\n' + (data.check.ok ? 'Verificação aprovada.' : 'A verificação encontrou problemas.') + (data.check.output ? '\n' + data.check.output : '') + (data.check.errors?.length ? '\n' + data.check.errors.map(error => error.file + ': ' + error.error).join('\n') : ''); status(data.check.ok ? 'Patch aplicado e verificação aprovada' : 'Patch aplicado; verificação encontrou problemas');});
refresh().catch(error => status(error.message));
