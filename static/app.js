'use strict';
const $ = (id) => document.getElementById(id);
let selectedUid = null;
let hits = [];
let aliasRequest = 0;
const kinds = {exact: 'تطبیق کامل', reordered: 'ترتیب متفاوت کلمات', prefix: 'شروع کلمات', fuzzy: 'شباهت نوشتاری'};

function status(message, error = false) {
  $('status').textContent = message;
  $('status').dataset.error = String(error);
}

async function api(path, options = {}) {
  const key = $('key').value.trim();
  if (!key) throw new Error('کلید API را وارد کن.');
  const response = await fetch(path, {...options, headers: {'X-API-Key': key, 'Content-Type': 'application/json'}});
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) throw new Error('کلید API معتبر نیست.');
    if (response.status === 409) throw new Error(data.detail === 'Alias already exists for this user' ? 'این نام مستعار قبلاً برای همین کاربر ثبت شده است.' : 'همگام‌سازی دیگری در حال اجراست.');
    if (response.status === 502) throw new Error('همگام‌سازی ناموفق بود؛ اتصال LDAP، رمز، TLS و دیتابیس را بررسی کن.');
    if (response.status === 422) throw new Error('ورودی معتبر نیست؛ نام باید شامل حرف یا عدد باشد.');
    throw new Error(typeof data.detail === 'string' ? data.detail : 'درخواست ناموفق بود.');
  }
  return data;
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

function renderResults() {
  $('results').replaceChildren();
  $('count').textContent = `(${hits.length})`;
  if (!hits.length) $('results').append(element('p', 'نتیجه‌ای پیدا نشد. املای دیگر یا حداقل امتیاز کمتر را امتحان کن. برای لقب‌ها باید نام مستعار ثبت شده باشد.', 'muted'));
  for (const hit of hits) {
    const user = hit.user;
    const card = element('article', '', `card${selectedUid === user.uid ? ' active' : ''}`);
    card.append(element('h3', user.display_name || [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username || user.uid));
    card.append(element('p', `${user.username || '—'} · ${user.department || 'واحد نامشخص'} · ${user.enabled ? 'فعال' : 'غیرفعال'}`));
    card.append(element('p', user.email || 'ایمیل ثبت نشده'));
    card.append(element('p', `امتیاز: ${hit.score} از ۱۰۰`, 'score'));
    card.append(element('p', `${kinds[hit.match_type] || hit.match_type}${hit.matched_field === 'alias' ? ' در نام مستعار' : ''}: ${hit.matched_name}`, 'badge'));
    const button = element('button', 'مدیریت نام‌های مستعار', 'secondary');
    button.type = 'button';
    button.addEventListener('click', () => selectUser(user));
    card.append(button);
    $('results').append(card);
  }
}

async function loadAliases(uid) {
  const request = ++aliasRequest;
  const aliases = await api(`/data/users/${uid}/aliases`);
  if (request !== aliasRequest || uid !== selectedUid) return;
  $('aliases').replaceChildren();
  if (!aliases.length) $('aliases').append(element('li', 'نام مستعاری ثبت نشده است.'));
  for (const alias of aliases) {
    const li = element('li', '');
    li.append(element('span', alias.name));
    const button = element('button', 'حذف');
    button.type = 'button';
    button.setAttribute('aria-label', `حذف نام مستعار ${alias.name}`);
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await api(`/data/users/${uid}/aliases/${alias.id}`, {method: 'DELETE'});
        if (selectedUid === uid) await loadAliases(uid);
        status('نام مستعار حذف شد؛ برای به‌روزرسانی نتایج دوباره جست‌وجو کن.');
      } catch (error) { status(error.message, true); }
      finally { button.disabled = false; }
    });
    li.append(button);
    $('aliases').append(li);
  }
}

async function selectUser(user) {
  selectedUid = user.uid;
  $('selected').textContent = `${user.display_name || user.username || user.uid} — ${user.uid}`;
  $('alias-editor').hidden = false;
  $('aliases').replaceChildren(element('li', 'در حال دریافت…'));
  renderResults();
  try { await loadAliases(user.uid); }
  catch (error) { status(error.message, true); }
}

$('search-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('search').disabled = true;
  status('در حال جست‌وجو…');
  try {
    const params = new URLSearchParams({q: $('query').value, limit: $('limit').value, min_score: $('threshold').value, enabled_only: $('enabled').checked});
    hits = await api(`/data/users/search?${params}`);
    selectedUid = null;
    aliasRequest++;
    $('selected').textContent = 'یک کاربر را از نتایج انتخاب کن.';
    $('alias-editor').hidden = true;
    renderResults();
    status(`${hits.length} نتیجه پیدا شد. امتیاز، معیار شباهت است و احتمال صحت نیست.`);
  } catch (error) { status(error.message, true); }
  finally { $('search').disabled = false; }
});

$('alias-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!selectedUid) return;
  const uid = selectedUid;
  $('add-alias').disabled = true;
  try {
    await api(`/data/users/${uid}/aliases`, {method: 'POST', body: JSON.stringify({name: $('alias').value})});
    $('alias').value = '';
    if (selectedUid === uid) await loadAliases(uid);
    status('نام مستعار ثبت شد؛ حالا می‌توانی با همین نام جست‌وجو کنی.');
  } catch (error) { status(error.message, true); }
  finally { $('add-alias').disabled = false; }
});

$('sync').addEventListener('click', async () => {
  $('sync').disabled = true;
  status('در حال دریافت کاربران از LDAP؛ لطفاً صبر کن…');
  try {
    const result = await api('/data/sync', {method: 'POST'});
    status(`${result.synced} کاربر همگام‌سازی شد. اکنون جست‌وجو کن.`);
  } catch (error) { status(error.message, true); }
  finally { $('sync').disabled = false; }
});
