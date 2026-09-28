const money = new Intl.NumberFormat('uk-UA', {maximumFractionDigits: 0});
const number = new Intl.NumberFormat('uk-UA', {maximumFractionDigits: 1});
let materials = [];

function riskClass(level) { return level === 'високий' ? 'risk-high' : level === 'середній' ? 'risk-medium' : 'risk-low'; }
function render(data) {
  const k = data.kpi;
  document.querySelector('#kpis').innerHTML = [
    [money.format(k.revenue) + ' ₴', 'Загальна виручка'], [k.deals, 'Кількість угод'],
    [k.materials, 'Матеріали під контролем'], [k.high_risk, 'Високий ризик дефіциту']
  ].map(x => `<article class="kpi"><strong>${x[0]}</strong><span>${x[1]}</span></article>`).join('');
  const maximum = Math.max(...data.monthly_revenue.map(x => x.revenue));
  document.querySelector('#chart').innerHTML = data.monthly_revenue.map(x => `<div class="bar" style="height:${Math.max(4, x.revenue / maximum * 100)}%" data-label="${x.period}: ${money.format(x.revenue)} ₴"></div>`).join('');
  document.querySelector('#risk-list').innerHTML = data.materials.map(m => `<div class="risk-row"><div><b>${m.name}</b><div class="small">Запас: ${number.format(m.stock)} ${m.unit} · постачання ${m.lead_time_days} дн.</div></div><div class="score ${riskClass(m.risk.level)}">${m.risk.score} · ${m.risk.level}</div></div>`).join('');
  document.querySelector('#manager-list').innerHTML = data.managers.map((m, i) => `<div class="manager-row"><div><b>${i + 1}. ${m.manager}</b><div class="small">${m.deals} угод · середній чек ${money.format(m.average_check)} ₴</div></div><div class="score">${m.score}</div></div>`).join('');
  document.querySelector('#forecast-list').innerHTML = data.materials.map(m => `<tr><td><b>${m.name}</b><div class="small">${m.category}</div></td><td>${number.format(m.stock)} ${m.unit}</td><td class="${riskClass(m.risk.level)}"><b>${m.risk.score}</b> · ${m.risk.level}</td><td><div class="forecast">${m.forecast.map(f => `<b>${f.period}: ${number.format(f.quantity)}</b>`).join('')}</div></td></tr>`).join('');
}
async function load() {
  const [dashboard, materialList] = await Promise.all([fetch('/api/dashboard').then(r => r.json()), fetch('/api/materials').then(r => r.json())]);
  materials = materialList; render(dashboard);
  document.querySelector('#material-select').innerHTML = materials.map(m => `<option value="${m.id}">${m.name} (${m.unit})</option>`).join('');
}
const dialog = document.querySelector('#sale-dialog');
document.querySelector('#open-sale').onclick = () => { document.querySelector('[name=sold_at]').value = new Date().toISOString().slice(0,10); dialog.showModal(); };
document.querySelector('#close-sale').onclick = () => dialog.close();
document.querySelector('#sale-form').onsubmit = async e => {
  e.preventDefault(); const form = new FormData(e.target); const payload = Object.fromEntries(form);
  payload.material_id = Number(payload.material_id); payload.quantity = Number(payload.quantity); payload.unit_price = Number(payload.unit_price);
  const response = await fetch('/api/sales', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  if (!response.ok) { document.querySelector('#form-error').textContent = (await response.json()).error || 'Не вдалося зберегти продаж'; return; }
  dialog.close(); e.target.reset(); await load();
};
load();
