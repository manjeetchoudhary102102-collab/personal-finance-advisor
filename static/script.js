(() => {
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  let chart;
  let currentSection = 'dashboard';

  const currency = (value) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(Number(value || 0));
  const selectedMonth = () => $('#monthInput').value;
  const today = new Date().toISOString().slice(0, 10);

  function showToast(message, error = false) {
    const el = $('#toast');
    el.textContent = message;
    el.style.background = error ? '#b33131' : '#172033';
    el.classList.add('show');
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => el.classList.remove('show'), 2600);
  }

  async function api(url, options = {}) {
    const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options });
    const data = await response.json().catch(() => ({ ok: false, error: 'Unexpected server response.' }));
    if (!response.ok || data.ok === false) throw new Error(data.error || 'Request failed.');
    return data;
  }

  function moneyOrDash(value) { return currency(value); }

  function setSection(section) {
    currentSection = section;
    $$('.nav-item').forEach(btn => btn.classList.toggle('active', btn.dataset.section === section));
    $$('.content-section').forEach(el => el.classList.toggle('active', el.id === `${section}-section`));
    const titles = { dashboard: 'Dashboard', expenses: 'Expenses', budget: 'Budget Advisor', 'ai-advisor': 'AI Financial Advisor', summary: 'Monthly Summary' };
    $('#pageTitle').textContent = titles[section] || 'Dashboard';
    $('#sidebar').classList.remove('open');
    if (section === 'expenses') loadExpenses();
    if (section === 'budget') loadBudget();
    if (section === 'ai-advisor') loadAdvice(false);
    if (section === 'summary') loadSummary();
  }

  function renderRecent(items) {
    const body = $('#recentExpenses');
    const empty = $('#recentEmpty');
    body.innerHTML = items.map(e => `<tr><td>${e.date}</td><td>${escapeHtml(e.description)}</td><td><span class="category-pill">${escapeHtml(e.category)}</span></td><td class="amount">${currency(e.amount)}</td></tr>`).join('');
    empty.style.display = items.length ? 'none' : 'block';
  }

  function renderChart(categoryTotals) {
    const labels = Object.entries(categoryTotals).filter(([, value]) => Number(value) > 0).map(([key]) => key);
    const values = labels.map(label => categoryTotals[label]);
    $('#chartEmpty').style.display = labels.length ? 'none' : 'grid';
    if (chart) chart.destroy();
    chart = new Chart($('#expenseChart'), {
      type: 'doughnut',
      data: { labels, datasets: [{ data: values, borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '68%', plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } }, tooltip: { callbacks: { label: ctx => ` ${currency(ctx.raw)}` } } } }
    });
  }

  async function loadDashboard() {
    try {
      const data = await api(`/api/dashboard?month=${encodeURIComponent(selectedMonth())}`);
      $('#incomeValue').textContent = moneyOrDash(data.income);
      $('#expenseValue').textContent = moneyOrDash(data.total_expenses);
      $('#savingsValue').textContent = moneyOrDash(data.savings);
      $('#savingsRate').textContent = `${data.savings_percentage}%`;
      $('#balanceValue').textContent = moneyOrDash(data.remaining_balance);
      $('#transactionCount').textContent = data.transaction_count;
      $('#highestCategory').textContent = data.highest_category || '—';
      $('#expenseMiniTotal').textContent = moneyOrDash(data.total_expenses);
      $('#incomeAmount').value = data.income || '';
      renderRecent(data.recent_expenses);
      renderChart(data.category_totals);
    } catch (error) { showToast(error.message, true); }
  }

  async function loadExpenses() {
    try {
      const params = new URLSearchParams({ month: selectedMonth() });
      const category = $('#categoryFilter').value;
      const start = $('#startFilter').value;
      const end = $('#endFilter').value;
      if (category) params.set('category', category);
      if (start) params.set('start', start);
      if (end) params.set('end', end);
      const data = await api(`/api/expenses?${params}`);
      const body = $('#expensesTable');
      $('#expensesEmpty').style.display = data.expenses.length ? 'none' : 'block';
      body.innerHTML = data.expenses.map(e => `<tr><td>${e.date}</td><td>${escapeHtml(e.description)}</td><td><span class="category-pill">${escapeHtml(e.category)}</span></td><td class="amount">${currency(e.amount)}</td><td><button class="text-btn delete-expense" data-id="${e.id}">Delete</button></td></tr>`).join('');
    } catch (error) { showToast(error.message, true); }
  }

  async function loadBudget() {
    try {
      const data = await api(`/api/budget?month=${encodeURIComponent(selectedMonth())}`);
      $('#budgetTable').innerHTML = data.rows.map(r => `<tr><td><strong>${escapeHtml(r.category)}</strong></td><td>${r.percentage}%</td><td>${currency(r.recommended)}</td><td>${currency(r.spent)}</td><td class="${r.difference >= 0 ? 'positive' : 'negative'}">${r.difference >= 0 ? '+' : ''}${currency(r.difference)}</td><td><span class="status-pill ${r.overspending ? 'status-warn' : 'status-good'}">${r.overspending ? 'Overspending' : 'Within limit'}</span></td></tr>`).join('');
    } catch (error) { showToast(error.message, true); }
  }

  async function loadAdvice(generate = false) {
    if (!generate) return;
    $('#adviceList').innerHTML = '<div class="loading-state">Analyzing your monthly spending…</div>';
    try {
      const data = await api(`/api/advice?month=${encodeURIComponent(selectedMonth())}`);
      $('#advisorMode').textContent = data.mode === 'api' ? 'AI provider response' : 'Rule-based advisor';
      $('#adviceList').innerHTML = data.advice.map((item, index) => `<div class="advice-item"><div class="advice-number">${index + 1}</div><p>${escapeHtml(item)}</p></div>`).join('');
    } catch (error) { $('#adviceList').innerHTML = `<div class="loading-state">${escapeHtml(error.message)}</div>`; }
  }

  async function loadSummary() {
    try {
      const data = await api(`/api/summary?month=${encodeURIComponent(selectedMonth())}`);
      $('#summarySavings').textContent = currency(data.savings);
      $('#summaryRate').textContent = `${data.savings_percentage}% of income`;
      $('#summaryIncome').textContent = currency(data.income);
      $('#summaryExpenses').textContent = currency(data.total_expenses);
      $('#summaryHighest').textContent = data.highest_category || '—';
      const clamped = Math.max(0, Math.min(100, Number(data.savings_percentage || 0)));
      $('#summaryRing').style.background = `conic-gradient(var(--primary) ${clamped * 3.6}deg, #e9edf5 0deg)`;
      $('#summaryRingText').textContent = `${data.savings_percentage}%`;
      $('#overspendingList').innerHTML = data.overspending.length ? data.overspending.map(r => `<div class="warn"><strong>${escapeHtml(r.category)}</strong> is ${currency(r.spent - r.recommended)} above the suggested limit.</div>`).join('') : '<div class="ok">No category is above the simple suggested limit this month.</div>';
      $('#recommendationsList').innerHTML = data.recommendations.map(item => `<div>${escapeHtml(item)}</div>`).join('');
    } catch (error) { showToast(error.message, true); }
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
  }

  $$('.nav-item').forEach(btn => btn.addEventListener('click', () => setSection(btn.dataset.section)));
  $$('[data-section-link]').forEach(btn => btn.addEventListener('click', () => setSection(btn.dataset.sectionLink)));
  $('#mobileMenu').addEventListener('click', () => $('#sidebar').classList.toggle('open'));
  $('#refreshBtn').addEventListener('click', refreshAll);
  $('#monthInput').addEventListener('change', refreshAll);

  $('#incomeForm').addEventListener('submit', async event => {
    event.preventDefault();
    const amount = $('#incomeAmount').value;
    try {
      await api('/api/income', { method: 'POST', body: JSON.stringify({ amount, month: selectedMonth() }) });
      showToast('Monthly income saved.');
      await refreshAll();
    } catch (error) { showToast(error.message, true); }
  });

  $('#expenseDate').value = today;
  $('#expenseDate').value = today;
  $('#expenseForm').addEventListener('submit', async event => {
    event.preventDefault();

    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form).entries());

    try {
      await api('/api/expenses', {
        method: 'POST',
        body: JSON.stringify(payload)
      });

      form.reset();
      $('#expenseDate').value = today;

      showToast('Expense added.');
      await refreshAll();
      setSection('expenses');
    } catch (error) {
      showToast(error.message, true);
    }
  });

  $('#expensesTable').addEventListener('click', async event => {
    const button = event.target.closest('.delete-expense');
    if (!button) return;
    if (!window.confirm('Delete this expense?')) return;
    try {
      await api(`/api/expenses/${button.dataset.id}`, { method: 'DELETE' });
      showToast('Expense deleted.');
      await refreshAll();
      setSection('expenses');
    } catch (error) { showToast(error.message, true); }
  });

  ['categoryFilter', 'startFilter', 'endFilter'].forEach(id => $(('#' + id)).addEventListener('change', loadExpenses));
  $('#clearFilters').addEventListener('click', () => { $('#categoryFilter').value = ''; $('#startFilter').value = ''; $('#endFilter').value = ''; loadExpenses(); });
  $('#generateAdvice').addEventListener('click', () => loadAdvice(true));

  async function refreshAll() {
    await loadDashboard();
    if (currentSection === 'expenses') await loadExpenses();
    if (currentSection === 'budget') await loadBudget();
    if (currentSection === 'summary') await loadSummary();
  }

  refreshAll();
})();
