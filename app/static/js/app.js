const state = {
  projects: [],
  lookups: {},
  sorts: [{ key: 'date', dir: -1 }],
  editingId: null,
  editingFormulaRow: null,
  materialSort: { key: 'name', dir: 1 },
  editingUserId: null,
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || 'Something went wrong');
  }
  return response.json();
}

function toast(message) {
  const node = $('#toast');
  node.textContent = message;
  node.classList.add('show');
  setTimeout(() => node.classList.remove('show'), 2600);
}

function money(value) {
  return Number(value || 0).toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

function roundUp(value) {
  const num = Number(value || 0);
  return num === 0 ? 0 : Math.ceil(num / 10) * 10;
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function isAdmin() {
  return document.body.dataset.role === 'admin';
}

async function init() {
  bindNavigation();
  bindDashboard();
  bindDialog();
  bindSettings();
  bindShortcuts();
  document.body.classList.toggle('light', localStorage.getItem('theme') === 'light');
  $$('.admin-only').forEach(node => node.classList.toggle('hidden', !isAdmin()));
  await refreshLookups();
  await refreshProjects();
  await refreshStats();
}

function bindNavigation() {
  $$('.nav-btn[data-view]').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.nav-btn').forEach(item => item.classList.remove('active'));
      btn.classList.add('active');
      $$('.view').forEach(view => view.classList.remove('active'));
      $(`#${btn.dataset.view}`).classList.add('active');
      if (btn.dataset.view === 'stats') refreshStats();
    });
  });
  $('#themeToggle').addEventListener('click', () => {
    document.body.classList.toggle('light');
    localStorage.setItem('theme', document.body.classList.contains('light') ? 'light' : 'dark');
  });
  $('#backupBtn').addEventListener('click', async () => {
    const result = await api('/backup', { method: 'POST', body: '{}' });
    toast(`Backup created: ${result.path.split('\\').pop()}`);
  });
  $$('[data-close-dialog]').forEach(button => {
    button.addEventListener('click', () => $(`#${button.dataset.closeDialog}`).close());
  });
}

function bindDashboard() {
  ['searchInput', 'stateFilter', 'contractorFilter', 'fromFilter', 'toFilter'].forEach(id => {
    $(`#${id}`).addEventListener('input', refreshProjects);
  });
  $('#clearFilters').addEventListener('click', () => {
    ['searchInput', 'stateFilter', 'contractorFilter', 'fromFilter', 'toFilter'].forEach(id => $(`#${id}`).value = '');
    refreshProjects();
  });
  $$('th[data-sort]').forEach(th => th.addEventListener('click', () => {
    const key = th.dataset.sort;
    const existing = state.sorts.find(item => item.key === key);
    if (existing) existing.dir *= -1;
    else state.sorts.push({ key, dir: 1 });
    if (state.sorts.length > 3) state.sorts.shift();
    renderProjects();
  }));
  $('#newProjectBtn').addEventListener('click', () => openProjectDialog());
  ['statsFromFilter', 'statsToFilter', 'statsStateFilter'].forEach(id => $(`#${id}`).addEventListener('input', refreshStats));
  $('#clearStatsFilters').addEventListener('click', () => {
    ['statsFromFilter', 'statsToFilter', 'statsStateFilter'].forEach(id => $(`#${id}`).value = '');
    refreshStats();
  });
}

function bindDialog() {
  $('#addMaterialRow').addEventListener('click', () => addMaterialRow());
  $('#saveProjectBtn').addEventListener('click', saveProject);
  $('#cancelProjectBtn').addEventListener('click', () => $('#projectDialog').close());
  $('#topCloseProjectBtn').addEventListener('click', () => $('#projectDialog').close());
  $('#workersToggle').addEventListener('change', event => {
    if (event.target.checked && !findMaterialRow('Working hand')) {
      addMaterialRow({ material_name: 'Working hand', category: 'Labor', unit: 'Other', quantity: 1, unit_price: 0, is_labor: true });
    }
    if (!event.target.checked) {
      const row = findMaterialRow('Working hand');
      if (row) row.remove();
      calculateProject();
    }
  });
  $('#projectImageInput').addEventListener('change', previewImages);
  ['width', 'height', 'final_price', 'project_type', 'work_done'].forEach(name => {
    const node = $(`[name="${name}"]`, $('#projectDialog'));
    const recalculate = debounce(async event => {
      if (name === 'project_type') await loadTemplateMaterials(event.target.value);
      calculateProject();
    }, 180);
    node.addEventListener('input', recalculate);
    node.addEventListener('change', recalculate);
  });
  $('#addPaymentBtn').addEventListener('click', addPayment);
  $('#saveFormulaBtn').addEventListener('click', () => {
    if (state.editingFormulaRow) {
      $('.mat-formula', state.editingFormulaRow).value = $('#formulaInput').value;
      $('.mat-auto', state.editingFormulaRow).checked = Boolean($('#formulaInput').value.trim());
      calculateProject();
    }
    $('#formulaDialog').close();
  });
}

function bindSettings() {
  $('#openMaterialManager').addEventListener('click', () => $('#materialDialog').showModal());
  $('#openUserManager').addEventListener('click', async () => {
    await refreshUsers();
    $('#userDialog').showModal();
  });
  $('#openHelp').addEventListener('click', () => $('#helpDialog').showModal());
  $('#saveMaterialBtn').addEventListener('click', saveMaterial);
  $('#cancelMaterialEdit').addEventListener('click', resetMaterialForm);
  ['materialSearch', 'materialCategoryFilter'].forEach(id => $(`#${id}`).addEventListener('input', renderMaterialSettings));
  $$('th[data-material-sort]').forEach(th => th.addEventListener('click', () => {
    const key = th.dataset.materialSort;
    state.materialSort.dir = state.materialSort.key === key ? state.materialSort.dir * -1 : 1;
    state.materialSort.key = key;
    renderMaterialSettings();
  }));
  $('#saveUserBtn').addEventListener('click', saveUser);
}

function bindShortcuts() {
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'n') {
      event.preventDefault();
      openProjectDialog();
    }
  });
}

async function refreshLookups() {
  state.lookups = await api('/lookups');
  fillDatalist('clientList', state.lookups.clients);
  fillDatalist('shopList', state.lookups.shops);
  fillDatalist('contractorList', state.lookups.contractors);
  fillDatalist('projectTypeList', state.lookups.project_types);
  fillDatalist('categoryList', [...(state.lookups.categories || []), { name: 'Labor' }, { name: 'Other' }]);
  fillDatalist('materialList', state.lookups.materials);
  fillSelect('contractorFilter', state.lookups.contractors, 'All contractors');
  fillSelectByName($('[name="unit"]', $('#materialForm')), state.lookups.units);
  renderMaterialSettings();
}

function fillDatalist(id, rows) {
  $(`#${id}`).innerHTML = (rows || []).map(row => `<option value="${escapeHtml(row.name)}"></option>`).join('');
}

function fillSelect(id, rows, label) {
  const node = $(`#${id}`);
  const selected = node.value;
  node.innerHTML = `<option value="">${label}</option>` + (rows || []).map(row => `<option>${escapeHtml(row.name)}</option>`).join('');
  node.value = selected;
}

function fillSelectByName(node, rows) {
  node.innerHTML = (rows || []).map(row => `<option>${escapeHtml(row.name)}</option>`).join('');
}

async function refreshProjects() {
  const params = new URLSearchParams();
  if ($('#searchInput').value) params.set('search', $('#searchInput').value);
  if ($('#stateFilter').value) params.set('state', $('#stateFilter').value);
  if ($('#contractorFilter').value) params.set('contractor', $('#contractorFilter').value);
  if ($('#fromFilter').value) params.set('from', $('#fromFilter').value);
  if ($('#toFilter').value) params.set('to', $('#toFilter').value);
  state.projects = (await api(`/projects?${params}`)).map(addComputedState);
  renderProjects();
}

function addComputedState(project) {
  const paid = Number(project.remaining_balance || 0) <= 0 && Number(project.final_price || 0) > 0;
  const done = Boolean(project.work_done) || project.status === 'completed' || project.status === 'paid';
  const overdue = !done && project.deadline && project.deadline < today();
  let computed_state = 'work in progress';
  let state_class = overdue ? 'overdue' : 'in-progress';
  if (done && paid) {
    computed_state = 'Completed';
    state_class = 'completed';
  } else if (done && !paid) {
    computed_state = 'Unpaid';
    state_class = 'unpaid';
  }
  return { ...project, paid, done, overdue, computed_state, state_class };
}

function renderProjects() {
  const rows = [...state.projects].sort((a, b) => {
    for (const sort of state.sorts) {
      const av = a[sort.key] ?? '';
      const bv = b[sort.key] ?? '';
      const result = String(av).localeCompare(String(bv), undefined, { numeric: true });
      if (result !== 0) return result * sort.dir;
    }
    return 0;
  });
  $('#projectTable tbody').innerHTML = rows.map(project => `
    <tr data-id="${project.id}">
      <td>${project.date || ''}</td>
      <td>${project.deadline || ''}</td>
      <td>${escapeHtml(project.shop_name || '')}</td>
      <td>${escapeHtml(project.client_name || '')}</td>
      <td>${escapeHtml(project.phone || '')}</td>
      <td>${escapeHtml(project.project_type || '')}</td>
      <td>${escapeHtml(project.contractor || '')}</td>
      <td>${money(project.final_price)}</td>
      <td>${money(project.remaining_balance)}</td>
      <td><span class="status ${project.state_class}">${escapeHtml(project.computed_state)}</span></td>
      <td><label class="check small-check"><input class="dash-work-done" type="checkbox" ${project.done ? 'checked' : ''}> Done</label></td>
      <td><button class="ghost-btn edit-btn" type="button">Edit</button></td>
      <td><button class="ghost-btn delete-btn" type="button">Delete</button></td>
    </tr>`).join('');
  $$('#projectTable tbody tr').forEach(row => {
    row.addEventListener('dblclick', event => {
      if (!event.target.closest('button,input,label')) openProjectDialog(row.dataset.id);
    });
    $('.edit-btn', row).addEventListener('click', () => openProjectDialog(row.dataset.id));
    $('.delete-btn', row).addEventListener('click', () => deleteProject(row.dataset.id));
    $('.dash-work-done', row).addEventListener('change', event => updateWorkDone(row.dataset.id, event.target.checked));
  });
}

async function updateWorkDone(id, workDone) {
  await api(`/projects/${id}/work-done`, { method: 'PATCH', body: JSON.stringify({ work_done: workDone }) });
  await refreshProjects();
  await refreshStats();
  toast('Project state updated');
}

async function openProjectDialog(id = null) {
  state.editingId = id;
  const dialog = $('#projectDialog');
  $('form', dialog).reset();
  $('[name="date"]', dialog).value = today();
  $('#paymentDate').value = today();
  $('#paymentList').innerHTML = '';
  $('#projectThumbs').innerHTML = '';
  $('#remainingBalanceLabel').textContent = 'Remaining: $0.00';
  $('#workersToggle').checked = false;
  $('#dialogTitle').textContent = id ? 'Edit Project' : 'New Project';
  $('#projectMaterials').innerHTML = '';
  if (id) {
    fillProjectForm(await api(`/projects/${id}`));
  } else {
    addMaterialRow();
    calculateProject();
  }
  dialog.showModal();
}

function fillProjectForm(project) {
  const dialog = $('#projectDialog');
  ['project_type', 'date', 'deadline', 'shop_name', 'client_name', 'phone', 'address', 'contractor', 'width', 'height', 'notes', 'final_price'].forEach(name => {
    const node = $(`[name="${name}"]`, dialog);
    if (node) node.value = project[name] ?? '';
  });
  $('[name="work_done"]', dialog).checked = Boolean(project.work_done) || project.status === 'completed' || project.status === 'paid';
  $('#projectMaterials').innerHTML = '';
  (project.materials || []).forEach(material => addMaterialRow(material));
  $('#workersToggle').checked = Boolean((project.materials || []).find(item => item.is_labor));
  renderPayments(project.payments || []);
  setTotals(project.totals || {});
}

async function loadTemplateMaterials(projectType) {
  if (!projectType || state.editingId || $('#projectMaterials').children.length > 1) return;
  const templates = await api(`/templates/${encodeURIComponent(projectType)}`);
  if (!templates.length) return;
  $('#projectMaterials').innerHTML = '';
  templates.forEach(item => addMaterialRow({
    material_id: item.material_id,
    material_name: item.material_name,
    category: item.category,
    unit: item.unit,
    unit_price: item.unit_price,
    formula: item.formula,
    auto_formula: item.auto_formula,
    waste_percent: item.waste_percent,
    quantity: 0,
  }));
  toast('Loaded material template');
}

function addMaterialRow(material = {}) {
  const row = document.createElement('tr');
  row.className = 'material-row';
  row.dataset.isLabor = material.is_labor || material.category === 'Labor' || material.material_name === 'Working hand' ? '1' : '0';
  row.innerHTML = `
    <td><input class="mat-name" list="materialList" value="${escapeHtml(material.material_name || material.name || '')}"></td>
    <td><input class="mat-category" list="categoryList" value="${escapeHtml(material.category || '')}"></td>
    <td><select class="mat-unit">${(state.lookups.units || []).map(unit => `<option ${unit.name === (material.unit || 'Pcs') ? 'selected' : ''}>${escapeHtml(unit.name)}</option>`).join('')}</select></td>
    <td><input class="mat-qty ${material.auto_formula && !material.manual_override ? 'calculated' : ''}" type="number" step="0.0001" value="${material.quantity || ''}"></td>
    <td><input class="mat-price" type="number" step="0.01" value="${material.unit_price || ''}"></td>
    <td><input class="mat-waste" type="number" step="0.1" value="${material.waste_percent || ''}"></td>
    <td><input class="mat-total calculated" readonly value="${material.total_price || ''}"></td>
    <td><input class="mat-auto" type="checkbox" ${material.auto_formula ? 'checked' : ''}></td>
    <td><input class="mat-override" type="checkbox" ${material.manual_override ? 'checked' : ''}></td>
    <td><button class="ghost-btn formula-btn" type="button">Formula</button><input class="mat-formula hidden" value="${escapeHtml(material.formula || '')}"></td>
    <td><button class="icon-btn remove-material" type="button">X</button></td>
  `;
  $('#projectMaterials').appendChild(row);
  $('.remove-material', row).addEventListener('click', () => { row.remove(); calculateProject(); });
  $('.formula-btn', row).addEventListener('click', () => openFormulaDialog(row));
  $$('.mat-name, .mat-category, .mat-unit, .mat-qty, .mat-price, .mat-waste, .mat-auto, .mat-override', row).forEach(input => {
    const updateMaterial = () => {
      hydrateMaterialFromCatalog(row);
      const readOnly = $('.mat-auto', row).checked && !$('.mat-override', row).checked;
      $('.mat-qty', row).readOnly = readOnly;
      $('.mat-total', row).readOnly = !$('.mat-override', row).checked;
      calculateProject();
    };
    input.addEventListener('input', updateMaterial);
    input.addEventListener('change', updateMaterial);
  });
  calculateProject();
}

function findMaterialRow(name) {
  return $$('.material-row').find(row => $('.mat-name', row)?.value === name);
}

function openFormulaDialog(row) {
  state.editingFormulaRow = row;
  $('#formulaInput').value = $('.mat-formula', row).value;
  $('#formulaDialog').showModal();
}

function hydrateMaterialFromCatalog(row) {
  const material_name = $('.mat-name', row).value.trim();
  const material = (state.lookups.materials || []).find(item => item.name === material_name);
  if (!material || row.dataset.hydrated === `${material.id}`) return;
  row.dataset.hydrated = `${material.id}`;
  $('.mat-category', row).value = material.category || '';
  $('.mat-unit', row).value = material.unit || 'Pcs';
  $('.mat-price', row).value = material.unit_price || '';
  $('.mat-formula', row).value = material.formula || '';
  $('.mat-waste', row).value = material.waste_percent || '';
  row.dataset.isLabor = material.category === 'Labor' || material_name === 'Working hand' ? '1' : '0';
  if (material.formula) $('.mat-auto', row).checked = true;
}

function collectMaterials() {
  return $$('.material-row').map(row => {
    const material_name = $('.mat-name', row).value.trim();
    const catalog = (state.lookups.materials || []).find(item => item.name === material_name && item.unit === $('.mat-unit', row).value);
    return {
      material_id: catalog?.id || null,
      material_name: material_name,
      category: $('.mat-category', row).value,
      unit: $('.mat-unit', row).value,
      quantity: Number($('.mat-qty', row).value || 0),
      unit_price: Number($('.mat-price', row).value || 0),
      formula: $('.mat-formula', row).value,
      auto_formula: $('.mat-auto', row).checked,
      manual_override: $('.mat-override', row).checked,
      waste_percent: Number($('.mat-waste', row).value || 0),
      is_labor: row.dataset.isLabor === '1' || $('.mat-category', row).value === 'Labor' || material_name === 'Working hand',
      total_price: Number($('.mat-total', row).value || 0),
    };
  }).filter(item => item.material_name);
}

async function calculateProject() {
  try {
    const dialog = $('#projectDialog');
    const payload = {
      width: Number($('[name="width"]', dialog).value || 0),
      height: Number($('[name="height"]', dialog).value || 0),
      final_price: Number($('[name="final_price"]', dialog).value || 0),
      materials: collectMaterials(),
    };
    const result = await api('/calculate', { method: 'POST', body: JSON.stringify(payload) });
    const rowsWithNames = $$('.material-row').filter(row => $('.mat-name', row).value.trim());
    result.materials.forEach((material, index) => {
      const row = rowsWithNames[index];
      if (!row) return;
      if (!$('.mat-override', row).checked) {
        $('.mat-qty', row).value = material.quantity || '';
        $('.mat-total', row).value = material.total_price ? roundUp(material.total_price) : '';
      }
    });
    setTotals(result.totals);
  } catch (error) {
    toast(error.message);
  }
}

function setTotals(totals) {
  const finalPrice = Number($('[name="final_price"]', $('#projectDialog')).value || totals.final_price || 0);
  const values = {
    materials_total: roundUp(totals.materials_total || 0),
    labor_total: roundUp(totals.labor_total || 0),
    price: roundUp(totals.price || 0),
    profit: roundUp(totals.profit || 0),
    profit_percent: `${totals.profit_percent || 0}%`,
  };
  Object.entries(values).forEach(([name, value]) => {
    const node = $(`[name="${name}"]`, $('#projectDialog'));
    if (node) node.value = value;
  });
  const paid = $$('#paymentList .payment-item').reduce((sum, item) => sum + Number(item.dataset.amount || 0), 0);
  $('#remainingBalanceLabel').textContent = `Remaining: ${money(finalPrice - paid)}`;
}

async function saveProject() {
  const dialog = $('#projectDialog');
  const data = Object.fromEntries(new FormData($('form', dialog)));
  data.work_done = $('[name="work_done"]', dialog).checked;
  data.width = Number(data.width || 0);
  data.height = Number(data.height || 0);
  data.final_price = Number(data.final_price || 0);
  data.materials = collectMaterials();
  if (!data.client_name) data.client_name = 'Walk-in client';
  const method = state.editingId ? 'PUT' : 'POST';
  const path = state.editingId ? `/projects/${state.editingId}` : '/projects';
  await api(path, { method, body: JSON.stringify(data) });
  dialog.close();
  await refreshLookups();
  await refreshProjects();
  await refreshStats();
  toast('Project saved');
}

async function deleteProject(id) {
  if (!confirm('Are you sure you want to delete this project?')) return;
  await api(`/projects/${id}`, { method: 'DELETE' });
  await refreshProjects();
  toast('Project deleted');
}

async function addPayment() {
  if (!state.editingId) {
    toast('Save the project before adding payments');
    return;
  }
  const amount = Number($('#paymentAmount').value || 0);
  if (!amount) return;
  const project = await api('/payments', {
    method: 'POST',
    body: JSON.stringify({
      project_id: state.editingId,
      amount,
      payment_date: $('#paymentDate').value || today(),
      note: $('#paymentNote').value,
    }),
  });
  $('#paymentAmount').value = '';
  $('#paymentNote').value = '';
  renderPayments(project.payments);
  setTotals(project.totals);
  refreshProjects();
}

function renderPayments(payments) {
  $('#paymentList').innerHTML = payments.map(payment => `
    <div class="payment-item" data-amount="${payment.amount}">
      <span>${payment.payment_date} - ${escapeHtml(payment.note || '')}</span>
      <strong>${money(payment.amount)}</strong>
    </div>`).join('');
}

async function refreshStats() {
  const params = new URLSearchParams();
  if ($('#statsFromFilter').value) params.set('from', $('#statsFromFilter').value);
  if ($('#statsToFilter').value) params.set('to', $('#statsToFilter').value);
  if ($('#statsStateFilter').value) params.set('state', $('#statsStateFilter').value);
  const data = await api(`/stats?${params}`);
  $('#statCards').innerHTML = [
    ['Total transactions', data.total_transactions],
    ['Total profit', money(data.total_profit)],
    ['Unpaid amount', money(data.unpaid_amount)],
    ['Avg monthly income', money(data.average_monthly_income)],
    ['Completed jobs', data.completed_jobs],
    ['Pending jobs', data.pending_jobs],
  ].map(([label, value]) => `<div class="panel stat-card"><span>${label}</span><strong>${value}</strong></div>`).join('');
  drawBarChart($('#incomeChart'), data.by_month, '#6ee7f9');
  drawBarChart($('#statusChart'), data.status_mix, '#8bdb81');
}

function drawBarChart(canvas, rows, color) {
  const ctx = canvas.getContext('2d');
  const scale = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * scale;
  canvas.height = rect.height * scale;
  ctx.scale(scale, scale);
  ctx.clearRect(0, 0, rect.width, rect.height);
  const max = Math.max(...rows.map(row => row.value), 1);
  const gap = 14;
  const barWidth = Math.max(24, (rect.width - gap * (rows.length + 1)) / Math.max(rows.length, 1));
  ctx.font = '12px Segoe UI';
  rows.forEach((row, index) => {
    const height = (rect.height - 58) * (row.value / max);
    const x = gap + index * (barWidth + gap);
    const y = rect.height - height - 34;
    ctx.fillStyle = color;
    ctx.fillRect(x, y, barWidth, height);
    ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--muted');
    ctx.fillText(String(row.label).slice(0, 10), x, rect.height - 12);
    ctx.fillText(String(row.value), x, Math.max(12, y - 6));
  });
}

async function saveMaterial() {
  const form = $('#materialForm');
  const payload = Object.fromEntries($$('input, select', form).map(input => [input.name, input.value]));
  if (!payload.name) return toast('Material name is required');
  const materialId = form.dataset.editingId;
  await api(materialId ? `/materials/${materialId}` : '/materials', {
    method: materialId ? 'PUT' : 'POST',
    body: JSON.stringify(payload),
  });
  resetMaterialForm();
  await refreshLookups();
  toast(materialId ? 'Material updated' : 'Material saved');
}

function renderMaterialSettings() {
  const search = ($('#materialSearch')?.value || '').toLowerCase();
  const category = ($('#materialCategoryFilter')?.value || '').toLowerCase();
  const rows = [...(state.lookups.materials || [])]
    .filter(item => !search || [item.name, item.category, item.unit, item.formula].join(' ').toLowerCase().includes(search))
    .filter(item => !category || String(item.category || '').toLowerCase().includes(category))
    .sort((a, b) => String(a[state.materialSort.key] ?? '').localeCompare(String(b[state.materialSort.key] ?? ''), undefined, { numeric: true }) * state.materialSort.dir);
  $('#materialsList').innerHTML = rows.map(material => `
    <tr>
      <td>${escapeHtml(material.name)}</td>
      <td>${escapeHtml(material.category || '')}</td>
      <td>${escapeHtml(material.unit)}</td>
      <td>${money(material.unit_price)}</td>
      <td>${escapeHtml(material.formula || '')}</td>
      <td><button class="ghost-btn edit-material-btn" type="button" data-id="${material.id}">Edit</button></td>
      <td><button class="ghost-btn delete-material-btn" type="button" data-id="${material.id}">Delete</button></td>
    </tr>`).join('');
  $$('.edit-material-btn').forEach(button => button.addEventListener('click', () => startMaterialEdit(Number(button.dataset.id))));
  $$('.delete-material-btn').forEach(button => button.addEventListener('click', () => deleteMaterial(Number(button.dataset.id))));
}

function startMaterialEdit(id) {
  const material = (state.lookups.materials || []).find(item => item.id === id);
  if (!material) return;
  const form = $('#materialForm');
  form.dataset.editingId = material.id;
  form.querySelector('[name="name"]').value = material.name || '';
  form.querySelector('[name="category"]').value = material.category || '';
  form.querySelector('[name="unit"]').value = material.unit || 'Pcs';
  form.querySelector('[name="unit_price"]').value = material.unit_price || '';
  form.querySelector('[name="formula"]').value = material.formula || '';
  form.querySelector('[name="waste_percent"]').value = material.waste_percent || '';
  $('#saveMaterialBtn').textContent = 'Update Material';
  $('#cancelMaterialEdit').classList.remove('hidden');
}

function resetMaterialForm() {
  const form = $('#materialForm');
  $$('input', form).forEach(input => input.value = '');
  delete form.dataset.editingId;
  $('#saveMaterialBtn').textContent = 'Save Material';
  $('#cancelMaterialEdit').classList.add('hidden');
}

async function deleteMaterial(id) {
  if (!confirm('Delete this material?')) return;
  await api(`/materials/${id}`, { method: 'DELETE' });
  await refreshLookups();
  toast('Material deleted');
}

async function refreshUsers() {
  if (!isAdmin()) return;
  const users = await api('/users');
  $('#usersList').innerHTML = users.map(user => `
    <div class="payment-item">
      <span>${escapeHtml(user.username)} - ${escapeHtml(user.role)}</span>
      <button class="ghost-btn edit-user-btn" data-id="${user.id}" type="button">Edit</button>
    </div>`).join('');
  $$('.edit-user-btn').forEach(button => {
    button.addEventListener('click', () => {
      const user = users.find(item => item.id === Number(button.dataset.id));
      state.editingUserId = user.id;
      const form = $('#userForm');
      form.querySelector('[name="username"]').value = user.username;
      form.querySelector('[name="username"]').disabled = true;
      form.querySelector('[name="display_name"]').value = user.display_name || '';
      form.querySelector('[name="role"]').value = user.role;
      form.querySelector('[name="password"]').value = '';
    });
  });
}

async function saveUser() {
  const form = $('#userForm');
  const payload = Object.fromEntries($$('input, select', form).map(input => [input.name, input.value]));
  const path = state.editingUserId ? `/users/${state.editingUserId}` : '/users';
  await api(path, { method: state.editingUserId ? 'PUT' : 'POST', body: JSON.stringify(payload) });
  state.editingUserId = null;
  $$('input', form).forEach(input => { input.value = ''; input.disabled = false; });
  await refreshUsers();
  toast('User saved');
}

function previewImages(event) {
  const files = [...event.target.files].slice(0, 6);
  $('#projectThumbs').innerHTML = files.map(file => `<span><img src="${URL.createObjectURL(file)}" alt="${escapeHtml(file.name)}"></span>`).join('');
}

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  }[char]));
}

init().catch(error => toast(error.message));
