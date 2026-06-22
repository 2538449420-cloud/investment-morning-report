const views = [...document.querySelectorAll('.view')];
const navButtons = [...document.querySelectorAll('[data-view-target]')];
const viewLinks = [...document.querySelectorAll('[data-view-link]')];
const reportContent = document.getElementById('report-content');

function escapeHtml(value = '') {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function sourceLink(sourceIds, sourceMap, label = '查看来源') {
  const source = (sourceIds || []).map((id) => sourceMap.get(id)).find(Boolean);
  if (!source?.url) return '';
  return `<a class="source-link" href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(label)} · ${escapeHtml(source.publisher)}</a>`;
}

function formatChineseDate(dateString) {
  const date = new Date(`${dateString}T00:00:00+08:00`);
  const weekday = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'][date.getDay()];
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 · ${weekday}`;
}

function renderReportData(data) {
  const sourceMap = new Map((data.sources || []).map((source) => [source.id, source]));
  const macro = (data.macro || []).map((item) => `
    <article><span>${escapeHtml(item.region)}</span><div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary)} ${escapeHtml(item.why_it_matters)}</p>${sourceLink(item.source_ids, sourceMap)}</div></article>
  `).join('');
  const flashes = (data.market_flashes || []).map((item, index) => `
    <div class="event-card flash-card">
      <span class="event-index">${index + 1}</span>
      <div>
        <div class="flash-title"><h3>${escapeHtml(item.title)}</h3><time>${escapeHtml(item.time_bjt)}</time></div>
        <p>${escapeHtml(item.summary)}</p>
        <div class="impact-row"><span class="positive">可能受益</span><b>${escapeHtml((item.beneficiaries || []).join(' · ') || '需结合具体公司判断')}</b></div>
        <div class="impact-row"><span class="negative">可能承压</span><b>${escapeHtml((item.pressured || []).join(' · ') || '需结合具体公司判断')}</b></div>
        <p class="watch-point"><strong>观察点：</strong>${escapeHtml(item.watch_point)}</p>
        ${sourceLink(item.source_ids, sourceMap, '查看报道')}
      </div>
    </div>
  `).join('');
  const terms = (data.terms || []).map((item, index) => `
    <article><span>${String(index + 1).padStart(2, '0')}</span><h3>${escapeHtml(item.name)}</h3><p>${escapeHtml(item.definition)} ${escapeHtml(item.connection)}</p></article>
  `).join('');
  const conceptParagraphs = (data.concept?.explanation || []).map((text) => `<p>${escapeHtml(text)}</p>`).join('');
  const company = data.company_case || {};
  const metrics = (company.metrics || []).map((metric) => `
    <div><small>${escapeHtml(metric.label)}</small><strong>${escapeHtml(metric.value)}</strong><em>${escapeHtml(metric.date)}</em></div>
  `).join('');
  const advantages = (company.advantages || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  const weaknesses = (company.weaknesses || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  const failureConditions = (company.failure_conditions || []).join('；');
  const options = (data.question?.options || []).map((option) => `
    <button type="button" data-answer="${escapeHtml(option.id === data.question.answer ? 'correct' : 'wrong')}"><b>${escapeHtml(option.id)}</b>${escapeHtml(option.text)}</button>
  `).join('');
  const path = data.knowledge_path || {};
  const nodes = (path.nodes || []).map((node, index, all) => {
    const isToday = node === path.today;
    const branch = index === all.length - 1 ? '└──' : '├──';
    return `<div class="branch-level child${isToday ? ' today-node' : ''}"><span>${branch}</span>${escapeHtml(node)}${isToday ? '<b>← 今日</b>' : ''}</div>`;
  }).join('');

  reportContent.innerHTML = `
    <header class="report-hero">
      <div class="report-meta"><span class="verified-badge">✓ 已完成来源核验</span><time datetime="${escapeHtml(data.report_date)}">${escapeHtml(formatChineseDate(data.report_date))}</time></div>
      <h1>${escapeHtml(data.theme)}</h1><p class="lead">${escapeHtml(data.summary)}</p>
      <div class="hero-footer"><span>预计阅读 12 分钟</span><span>3条宏观 · ${(data.market_flashes || []).length}条快讯</span><span>${(data.sources || []).length} 个可靠来源</span></div>
    </header>
    <section id="market" class="report-section"><div class="section-heading"><span>01</span><h2>全球宏观</h2></div><p class="section-intro">先用3条信息确认大环境。</p><div class="macro-list">${macro}</div></section>
    <section id="events" class="report-section"><div class="section-heading"><span>02</span><h2>今日市场快讯</h2></div><div class="flash-window"><span class="status-dot"></span>统计窗口：昨日08:00—今日08:00（北京时间）</div>${flashes}</section>
    <section id="terms" class="report-section"><div class="section-heading"><span>03</span><h2>今日5个投资名词</h2></div><div class="term-grid">${terms}</div></section>
    <section id="concept" class="report-section"><div class="section-heading"><span>04</span><h2>重点概念</h2></div><h3 class="big-question">${escapeHtml(data.concept?.title)}</h3><p>${escapeHtml(data.concept?.question)}</p>${conceptParagraphs}<div class="concept-formula"><small>${escapeHtml(data.concept?.formula?.name)}</small><strong>${escapeHtml(data.concept?.formula?.expression)}</strong><p>${escapeHtml(data.concept?.formula?.example)} ${escapeHtml(data.concept?.formula?.limitation)}</p></div><div class="embedded-counterexample"><small>概念反例</small><p>${escapeHtml(data.concept?.counterexample)}</p></div></section>
    <section id="company" class="report-section"><div class="section-heading"><span>05</span><h2>真实公司案例</h2></div><div class="company-title"><div class="company-logo">案例</div><div><h3>${escapeHtml(company.company)}</h3><p>${escapeHtml(company.topic)}</p></div></div><h3>它怎么赚钱？</h3><p>${escapeHtml(company.business_model)}</p><p>${escapeHtml(company.customers_pay_because)}</p><p>${escapeHtml(company.revenue_profit_cash)}</p><div class="metric-grid">${metrics}</div><h3>商业模式的优势</h3><ul class="clean-list">${advantages}</ul><h3>风险在哪里？</h3><ul class="clean-list danger">${weaknesses}</ul><div class="embedded-counterexample"><small>逻辑失效条件</small><p>${escapeHtml(failureConditions)}</p><p>${escapeHtml(company.valuation_boundary)}</p></div></section>
    <section id="question" class="report-section question-section"><div class="section-heading"><span>06</span><h2>今日思考题</h2></div><p class="question">${escapeHtml(data.question?.prompt)}</p><div class="quiz" id="quiz">${options}</div><div class="answer" id="answer" data-explanation="${escapeHtml(data.question?.explanation)}" hidden></div></section>
    <section id="tree" class="report-section"><div class="section-heading"><span>07</span><h2>知识树：今日位置</h2></div><div class="tree-branch"><strong>${escapeHtml(path.module)}</strong><div class="branch-level"><span>└──</span><strong>${escapeHtml(path.parent)}</strong></div>${nodes}</div><p>完整知识地图会在“知识树”页面按模块保存，这里只展示今天所在的位置。</p></section>
    <footer class="disclaimer"><strong>风险提示</strong><p>${escapeHtml(data.disclaimer)}</p><p class="generated-at">发布于 ${escapeHtml(data.published_at || data.generated_at || '')}（北京时间）</p></footer>
  `;
  bindQuiz();
  updateReadingState();
}

async function loadLatestReport() {
  if (window.location.protocol === 'file:') return;
  const cacheBuster = new Date().toISOString().slice(0, 13);
  const endpoints = [
    `https://raw.githubusercontent.com/2538449420-cloud/investment-morning-report/main/data/today.json?v=${cacheBuster}`,
    '/api/reports/latest',
    './data/latest.json'
  ];
  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint, { cache: 'no-store' });
      if (!response.ok) continue;
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) continue;
      renderReportData(await response.json());
      return;
    } catch (error) {
      // 继续尝试下一个来源；都不可用时保留内置样稿。
    }
  }
  console.info('使用内置样稿，后台晨报尚未就绪。');
}

function rawGitHubUrl(path) {
  if (!/^data\/[a-zA-Z0-9_./-]+\.json$/.test(path)) return null;
  const cacheBuster = new Date().toISOString().slice(0, 13);
  return `https://raw.githubusercontent.com/2538449420-cloud/investment-morning-report/main/${path}?v=${cacheBuster}`;
}

async function openArchivedReport(path) {
  const url = rawGitHubUrl(path);
  if (!url) return;
  try {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderReportData(await response.json());
    setView('today');
  } catch (error) {
    console.warn('历史晨报暂时无法读取。', error);
  }
}

async function loadHistoryArchive() {
  const list = document.getElementById('history-list');
  const indexUrl = rawGitHubUrl('data/history.json');
  if (!list || !indexUrl) return;
  try {
    const response = await fetch(indexUrl, { cache: 'no-store' });
    if (!response.ok) return;
    const archive = await response.json();
    if (!Array.isArray(archive.reports) || !archive.reports.length) return;
    list.innerHTML = archive.reports.map((item, index) => `
      <button class="history-card${index === 0 ? ' featured' : ''}" type="button" data-history-path="${escapeHtml(item.path)}">
        <time>${escapeHtml(formatChineseDate(item.report_date))}</time>
        <h2>${escapeHtml(item.theme)}</h2>
        <p>${escapeHtml(item.company || item.summary)}</p>
        <span>阅读晨报 →</span>
      </button>
    `).join('');
    list.querySelectorAll('[data-history-path]').forEach((button) => {
      button.addEventListener('click', () => openArchivedReport(button.dataset.historyPath));
    });
  } catch (error) {
    console.info('使用内置历史样稿。');
  }
}

function setView(name) {
  views.forEach((view) => view.classList.toggle('active', view.dataset.view === name));
  navButtons.forEach((button) => button.classList.toggle('active', button.dataset.viewTarget === name));
  window.scrollTo({ top: 0, behavior: 'smooth' });
  document.title = name === 'today' ? '投资晨报' : name === 'history' ? '往期晨报｜投资晨报' : '知识树｜投资晨报';
}

navButtons.forEach((button) => button.addEventListener('click', () => setView(button.dataset.viewTarget)));
viewLinks.forEach((link) => link.addEventListener('click', (event) => {
  event.preventDefault();
  setView(link.dataset.viewLink);
}));
document.querySelector('[data-open-today]').addEventListener('click', () => setView('today'));

const fontButton = document.getElementById('font-button');
const fontMenu = document.getElementById('font-menu');
const moreButton = document.getElementById('more-button');
const moreMenu = document.getElementById('more-menu');

function toggleMenu(button, menu) {
  const willOpen = menu.hidden;
  [fontMenu, moreMenu].forEach((item) => { item.hidden = true; });
  [fontButton, moreButton].forEach((item) => item.setAttribute('aria-expanded', 'false'));
  menu.hidden = !willOpen;
  button.setAttribute('aria-expanded', String(willOpen));
}

fontButton.addEventListener('click', () => toggleMenu(fontButton, fontMenu));
moreButton.addEventListener('click', () => toggleMenu(moreButton, moreMenu));
document.addEventListener('click', (event) => {
  if (!event.target.closest('.topbar-actions')) {
    fontMenu.hidden = true;
    moreMenu.hidden = true;
    fontButton.setAttribute('aria-expanded', 'false');
    moreButton.setAttribute('aria-expanded', 'false');
  }
});

document.querySelectorAll('[data-font-size]').forEach((button) => {
  button.addEventListener('click', () => {
    document.body.classList.remove('font-small', 'font-large');
    if (button.dataset.fontSize === 'small') document.body.classList.add('font-small');
    if (button.dataset.fontSize === 'large') document.body.classList.add('font-large');
    document.querySelectorAll('[data-font-size]').forEach((item) => item.classList.toggle('active', item === button));
    localStorage.setItem('morning-report-font-size', button.dataset.fontSize);
  });
});

const savedFontSize = localStorage.getItem('morning-report-font-size');
if (savedFontSize) document.querySelector(`[data-font-size="${savedFontSize}"]`)?.click();

document.getElementById('print-button').addEventListener('click', () => {
  moreMenu.hidden = true;
  window.print();
});

document.getElementById('word-button').addEventListener('click', () => {
  const wordStyles = '<style>body{font-family:Microsoft YaHei,Arial;line-height:1.8;color:#1d2923}h1,h2,h3{color:#1e6148}blockquote{padding:12px;background:#e2eee7}</style>';
  const html = `<!doctype html><html><head><meta charset="utf-8">${wordStyles}</head><body>${reportContent.innerHTML}</body></html>`;
  const blob = new Blob(['\ufeff', html], { type: 'application/msword' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  const reportDate = reportContent.querySelector('time[datetime]')?.getAttribute('datetime') || '今日';
  link.download = `投资晨报-${reportDate}.doc`;
  link.click();
  URL.revokeObjectURL(link.href);
  moreMenu.hidden = true;
});

function bindQuiz() {
  document.querySelectorAll('#quiz button').forEach((button) => {
    button.addEventListener('click', () => {
    document.querySelectorAll('#quiz button').forEach((item) => item.classList.remove('selected-correct', 'selected-wrong'));
    const correct = button.dataset.answer === 'correct';
    button.classList.add(correct ? 'selected-correct' : 'selected-wrong');
    const answer = document.getElementById('answer');
    answer.hidden = false;
    const explanation = answer.dataset.explanation || '20%的增长本身不能完成判断，还要比较市场原先期待多少、增长来自哪里，以及未来指引有没有变化。';
    answer.innerHTML = correct ? `<strong>回答正确。</strong> ${explanation}` : '<strong>再想一步。</strong> 价格通常还包含了市场此前的预期。';
    });
  });
}
bindQuiz();

const progressBar = document.getElementById('reading-progress-bar');
function updateReadingState() {
  const todayActive = document.getElementById('view-today').classList.contains('active');
  if (!todayActive) {
    progressBar.style.width = '0';
    return;
  }
  const scrollable = document.documentElement.scrollHeight - window.innerHeight;
  const progress = scrollable > 0 ? Math.min(100, Math.max(0, window.scrollY / scrollable * 100)) : 0;
  progressBar.style.width = `${progress}%`;

  const currentSections = [...document.querySelectorAll('.report-section[id]')];
  const currentTocLinks = [...document.querySelectorAll('#toc a')];
  let current = currentSections[0]?.id;
  currentSections.forEach((section) => {
    if (section.getBoundingClientRect().top <= 150) current = section.id;
  });
  currentTocLinks.forEach((link) => link.classList.toggle('active', link.getAttribute('href') === `#${current}`));
}

window.addEventListener('scroll', updateReadingState, { passive: true });
window.addEventListener('resize', updateReadingState);
updateReadingState();
loadLatestReport();
loadHistoryArchive();
