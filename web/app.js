/**
 * Israeli Startup Job Scanner — Frontend App
 *
 * Plain vanilla JS — no frameworks, no build step.
 * Loads jobs from ../data/jobs.json, handles filtering, sorting,
 * pagination, read/unread state, saved jobs, followed companies,
 * saved searches, and daily reports — all via localStorage.
 */

const APP_VERSION = '1.0.0';

// ─── State ──────────────────────────────────────────────────────────────────

const state = {
    allJobs: [],
    filteredJobs: [],
    metadata: null,
    readJobs: {},
    savedJobs: {},
    followedCompanies: {},
    savedSearches: [],
    currentPage: 1,
    pageSize: 100,
    sortField: 'updated',
    sortDir: 'desc',
    lastRefresh: null,
    activeTab: 'jobs',
    filters: {
        search: '',
        location: '',
        seniority: '',
        industry: '',
        department: '',
        status: '',
    },
};

// ─── LocalStorage ───────────────────────────────────────────────────────────

const STORAGE_KEYS = {
    read: 'israeliJobScanner_readJobs',
    saved: 'israeliJobScanner_savedJobs',
    followed: 'israeliJobScanner_followedCompanies',
    searches: 'israeliJobScanner_savedSearches',
};

function loadFromStorage(key, fallback) {
    try {
        const stored = localStorage.getItem(key);
        return stored ? JSON.parse(stored) : fallback;
    } catch {
        return fallback;
    }
}

function saveToStorage(key, data) {
    try {
        localStorage.setItem(key, JSON.stringify(data));
    } catch (e) {
        console.warn('Failed to save to localStorage:', e);
    }
}

// Read state
function loadReadState() {
    state.readJobs = loadFromStorage(STORAGE_KEYS.read, {});
}
function saveReadState() { saveToStorage(STORAGE_KEYS.read, state.readJobs); }
function isRead(jobId) { return !!state.readJobs[jobId]; }
function markRead(jobId) { state.readJobs[jobId] = Date.now(); saveReadState(); }
function markUnread(jobId) { delete state.readJobs[jobId]; saveReadState(); }
function toggleRead(jobId) { isRead(jobId) ? markUnread(jobId) : markRead(jobId); }

// Saved jobs
function loadSavedJobs() {
    state.savedJobs = loadFromStorage(STORAGE_KEYS.saved, {});
}
function saveSavedJobs() { saveToStorage(STORAGE_KEYS.saved, state.savedJobs); }
function isSaved(jobId) { return !!state.savedJobs[jobId]; }
function toggleSaveJob(jobId) {
    if (isSaved(jobId)) {
        delete state.savedJobs[jobId];
    } else {
        state.savedJobs[jobId] = Date.now();
    }
    saveSavedJobs();
}

// Followed companies
function loadFollowedCompanies() {
    state.followedCompanies = loadFromStorage(STORAGE_KEYS.followed, {});
}
function saveFollowedCompanies() { saveToStorage(STORAGE_KEYS.followed, state.followedCompanies); }
function isFollowed(company) { return !!state.followedCompanies[company]; }
function toggleFollowCompany(company) {
    if (isFollowed(company)) {
        delete state.followedCompanies[company];
    } else {
        state.followedCompanies[company] = Date.now();
    }
    saveFollowedCompanies();
}

// Saved searches
function loadSavedSearches() {
    state.savedSearches = loadFromStorage(STORAGE_KEYS.searches, []);
}
function saveSavedSearches() { saveToStorage(STORAGE_KEYS.searches, state.savedSearches); }

// ─── Data Loading ───────────────────────────────────────────────────────────

async function loadJobs() {
    try {
        const resp = await fetch('../data/jobs.json?t=' + Date.now());
        if (!resp.ok) throw new Error('Failed to load jobs.json');
        state.allJobs = await resp.json();
        return true;
    } catch (e) {
        console.error('Error loading jobs:', e);
        document.getElementById('jobTableBody').innerHTML =
            '<tr><td colspan="10" style="text-align:center;padding:40px;color:#f87171;">Failed to load jobs. Make sure you\'ve run the fetcher first.<br><code>python3 fetch/fetcher.py</code></td></tr>';
        return false;
    }
}

async function loadMetadata() {
    try {
        const resp = await fetch('../data/metadata.json?t=' + Date.now());
        if (!resp.ok) return;
        state.metadata = await resp.json();
        state.lastRefresh = state.metadata.lastRefresh;
    } catch (e) {
        console.warn('Could not load metadata:', e);
    }
}

// ─── Filtering ──────────────────────────────────────────────────────────────

function applyFilters() {
    const { search, location, seniority, industry, department, status } = state.filters;
    const searchLower = search.toLowerCase();

    state.filteredJobs = state.allJobs.filter(job => {
        // Text search
        if (searchLower) {
            const haystack = (job.title + ' ' + job.company).toLowerCase();
            if (!haystack.includes(searchLower)) return false;
        }

        // Location
        if (location && job.locationEn !== location && job.location !== location) return false;

        // Seniority
        if (seniority && job.seniority !== seniority) return false;

        // Industry
        if (industry && job.industry !== industry) return false;

        // Department
        if (department && job.department !== department) return false;

        // Status filters
        if (status === 'unread' && isRead(job.id)) return false;
        if (status === 'read' && !isRead(job.id)) return false;
        if (status === 'saved' && !isSaved(job.id)) return false;
        if (status === 'followed' && !isFollowed(job.company)) return false;

        return true;
    });

    applySort();
    state.currentPage = 1;
    renderTable();
    renderPagination();
    updateStats();
}

// ─── Sorting ────────────────────────────────────────────────────────────────

function applySort() {
    const { sortField, sortDir } = state;
    const dir = sortDir === 'asc' ? 1 : -1;

    state.filteredJobs.sort((a, b) => {
        let va = a[sortField] || '';
        let vb = b[sortField] || '';

        if (sortField === 'status') {
            va = isRead(a.id) ? 1 : 0;
            vb = isRead(b.id) ? 1 : 0;
            return (va - vb) * dir;
        }

        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();

        if (va < vb) return -1 * dir;
        if (va > vb) return 1 * dir;
        return 0;
    });
}

function setSort(field) {
    if (state.sortField === field) {
        state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        state.sortField = field;
        state.sortDir = field === 'updated' ? 'desc' : 'asc';
    }

    document.querySelectorAll('#jobTable th.sortable').forEach(th => {
        th.classList.remove('active', 'asc', 'desc');
        if (th.dataset.sort === state.sortField) {
            th.classList.add('active', state.sortDir);
        }
    });

    applySort();
    renderTable();
}

// ─── Rendering — Main Table ─────────────────────────────────────────────────

function renderTable() {
    const tbody = document.getElementById('jobTableBody');
    const start = (state.currentPage - 1) * state.pageSize;
    const end = start + state.pageSize;
    const pageJobs = state.filteredJobs.slice(start, end);

    if (pageJobs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:40px;color:var(--text-dim);">No jobs match your filters</td></tr>';
        return;
    }

    const html = pageJobs.map(job => {
        const read = isRead(job.id);
        const rowClass = read ? 'read' : 'unread';
        const dotClass = read ? 'read' : 'unread';
        const saved = isSaved(job.id);
        const followed = isFollowed(job.company);
        const seniorityBadge = getSeniorityBadge(job.seniority);
        const dateDisplay = formatDate(job.updated);

        return `<tr class="job-row ${rowClass}" data-id="${job.id}">
            <td class="col-status" title="Click to toggle read status">
                <span class="status-dot ${dotClass}" data-action="toggle"></span>
            </td>
            <td class="col-save">
                <button class="save-btn ${saved ? 'saved' : ''}" data-action="save" title="${saved ? 'Unsave job' : 'Save job'}">${saved ? '\u2605' : '\u2606'}</button>
            </td>
            <td class="col-title">
                <a href="${escapeHtml(job.url)}" target="_blank" rel="noopener" class="job-title-link" data-action="open">
                    ${escapeHtml(job.title)}
                </a>
            </td>
            <td class="col-company">
                <button class="follow-btn ${followed ? 'followed' : ''}" data-action="follow" data-company="${escapeHtml(job.company)}" title="${followed ? 'Unfollow company' : 'Follow company'}">${followed ? '\u2665' : '\u2661'}</button>
                ${escapeHtml(job.company)}
            </td>
            <td class="col-location">${escapeHtml(job.locationEn || job.location)}</td>
            <td class="col-industry">${escapeHtml(job.industry)}</td>
            <td class="col-seniority">${seniorityBadge}</td>
            <td class="col-department">${escapeHtml(job.department)}</td>
            <td class="col-updated">${dateDisplay}</td>
            <td class="col-source"><span class="source-badge">${escapeHtml(job.source)}</span></td>
        </tr>`;
    }).join('');

    tbody.innerHTML = html;

    document.getElementById('showingCount').textContent =
        `Showing ${start + 1}-${Math.min(end, state.filteredJobs.length)} of ${state.filteredJobs.length} jobs`;
}

function renderPagination() {
    const totalPages = Math.ceil(state.filteredJobs.length / state.pageSize);
    const prevBtn = document.getElementById('prevPage');
    const nextBtn = document.getElementById('nextPage');
    const pageInfo = document.getElementById('pageInfo');

    prevBtn.disabled = state.currentPage <= 1;
    nextBtn.disabled = state.currentPage >= totalPages;
    pageInfo.textContent = `Page ${state.currentPage} of ${totalPages || 1}`;
}

function updateStats() {
    const total = state.allJobs.length;
    const unread = state.allJobs.filter(j => !isRead(j.id)).length;
    const newCount = state.metadata?.newSinceLastRefresh || 0;

    document.getElementById('statTotal').textContent = `${total.toLocaleString()} jobs`;
    document.getElementById('statUnread').textContent = `${unread.toLocaleString()} unread`;
    document.getElementById('statNew').textContent = `${newCount} new`;

    if (state.metadata?.lastRefresh) {
        document.getElementById('statRefresh').textContent =
            `Refreshed ${timeAgo(state.metadata.lastRefresh)}`;
    }

    // Update tab badges
    const savedCount = Object.keys(state.savedJobs).length;
    const followedCount = Object.keys(state.followedCompanies).length;
    const searchesCount = state.savedSearches.length;

    updateTabBadge('savedJobs', savedCount);
    updateTabBadge('followedCompanies', followedCount);
    updateTabBadge('savedSearches', searchesCount);
}

function updateTabBadge(tabName, count) {
    const tab = document.querySelector(`.tab[data-tab="${tabName}"]`);
    if (!tab) return;
    let badge = tab.querySelector('.tab-badge');
    if (count > 0) {
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'tab-badge';
            tab.appendChild(badge);
        }
        badge.textContent = count;
    } else if (badge) {
        badge.remove();
    }
}

function populateFilters() {
    const locations = new Set();
    const seniorities = new Set();
    const industries = new Set();
    const departments = new Set();

    state.allJobs.forEach(job => {
        if (job.locationEn) locations.add(job.locationEn);
        if (job.seniority) seniorities.add(job.seniority);
        if (job.industry) industries.add(job.industry);
        if (job.department) departments.add(job.department);
    });

    populateSelect('locationFilter', [...locations].sort());
    populateSelect('seniorityFilter', [...seniorities].sort());
    populateSelect('industryFilter', [...industries].sort());
    populateSelect('departmentFilter', [...departments].sort());
}

function populateSelect(id, values) {
    const select = document.getElementById(id);
    const currentValue = select.value;
    const firstOption = select.options[0];

    select.innerHTML = '';
    select.appendChild(firstOption);

    values.forEach(val => {
        if (!val) return;
        const option = document.createElement('option');
        option.value = val;
        option.textContent = val;
        select.appendChild(option);
    });

    select.value = currentValue;
}

// ─── Rendering — Saved Jobs Tab ─────────────────────────────────────────────

function renderSavedJobsTab() {
    const tbody = document.getElementById('savedJobsTableBody');
    const savedIds = Object.keys(state.savedJobs);
    const countEl = document.getElementById('savedJobsCount');

    const savedJobsList = state.allJobs
        .filter(j => isSaved(j.id))
        .sort((a, b) => (state.savedJobs[b.id] || 0) - (state.savedJobs[a.id] || 0));

    countEl.textContent = `${savedJobsList.length} saved`;

    if (savedJobsList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No saved jobs yet. Click the star icon on any job to save it.</td></tr>';
        return;
    }

    tbody.innerHTML = savedJobsList.map(job => {
        const seniorityBadge = getSeniorityBadge(job.seniority);
        const dateDisplay = formatDate(job.updated);
        const savedAt = formatDate(new Date(state.savedJobs[job.id]).toISOString());

        return `<tr class="job-row" data-id="${job.id}">
            <td class="col-save">
                <button class="save-btn saved" data-action="unsave" title="Unsave job">\u2605</button>
            </td>
            <td class="col-title">
                <a href="${escapeHtml(job.url)}" target="_blank" rel="noopener" class="job-title-link">${escapeHtml(job.title)}</a>
            </td>
            <td class="col-company">${escapeHtml(job.company)}</td>
            <td class="col-location">${escapeHtml(job.locationEn || job.location)}</td>
            <td class="col-industry">${escapeHtml(job.industry)}</td>
            <td class="col-seniority">${seniorityBadge}</td>
            <td class="col-updated">${dateDisplay}</td>
            <td class="col-saved-at">${savedAt}</td>
        </tr>`;
    }).join('');
}

// ─── Rendering — Followed Companies Tab ─────────────────────────────────────

function renderFollowedCompaniesTab() {
    const container = document.getElementById('followedCompaniesContainer');
    const countEl = document.getElementById('followedCompaniesCount');
    const followedNames = Object.keys(state.followedCompanies);

    countEl.textContent = `${followedNames.length} followed`;

    if (followedNames.length === 0) {
        container.innerHTML = '<div class="empty-state">No followed companies yet. Click the heart icon next to any company name to follow it.</div>';
        return;
    }

    const companiesWithJobs = followedNames
        .sort()
        .map(name => {
            const jobs = state.allJobs
                .filter(j => j.company === name)
                .sort((a, b) => (b.updated || '').localeCompare(a.updated || ''))
                .slice(0, 5);
            return { name, jobs, totalJobs: state.allJobs.filter(j => j.company === name).length };
        });

    container.innerHTML = companiesWithJobs.map(c => `
        <div class="company-card" data-company="${escapeHtml(c.name)}">
            <div class="company-card-header">
                <span class="company-card-name">${escapeHtml(c.name)}</span>
                <div class="company-card-meta">
                    ${c.totalJobs} job${c.totalJobs !== 1 ? 's' : ''}
                    <button class="company-unfollow-btn" data-action="unfollow" data-company="${escapeHtml(c.name)}">Unfollow</button>
                </div>
            </div>
            <ul class="company-card-jobs">
                ${c.jobs.map(j => `
                    <li>
                        <a href="${escapeHtml(j.url)}" target="_blank" rel="noopener">${escapeHtml(j.title)}</a>
                        <span class="job-meta">${escapeHtml(j.locationEn || j.location || '')} ${formatDate(j.updated)}</span>
                    </li>
                `).join('')}
                ${c.totalJobs > 5 ? `<li style="color:var(--text-dim);font-size:0.78rem;">+ ${c.totalJobs - 5} more</li>` : ''}
            </ul>
        </div>
    `).join('');
}

// ─── Rendering — Daily Report Tab ───────────────────────────────────────────

function renderDailyReport() {
    const container = document.getElementById('reportContent');
    const dateInput = document.getElementById('reportDate');
    const selectedDate = dateInput.value || new Date().toISOString().slice(0, 10);

    // Filter jobs for the selected date
    const dayJobs = state.allJobs.filter(job => {
        const jobDate = (job.updated || job.firstSeen || '').slice(0, 10);
        return jobDate === selectedDate;
    });

    if (dayJobs.length === 0) {
        container.innerHTML = `<div class="empty-state">No jobs found for ${selectedDate}. Try selecting a different date.</div>`;
        return;
    }

    // Compute breakdowns
    const byIndustry = countBy(dayJobs, 'industry');
    const bySeniority = countBy(dayJobs, 'seniority');
    const byDepartment = countBy(dayJobs, 'department');

    // Followed company jobs
    const followedNames = Object.keys(state.followedCompanies);
    const followedJobs = dayJobs.filter(j => followedNames.includes(j.company));
    const byFollowedCompany = countBy(followedJobs, 'company');

    const colors = ['fill-accent', 'fill-green', 'fill-yellow', 'fill-orange', 'fill-red', 'fill-purple'];

    let html = '';

    // Summary cards
    html += `<div class="report-summary">
        <div class="report-stat-card">
            <div class="report-stat-number">${dayJobs.length}</div>
            <div class="report-stat-label">Total Jobs</div>
        </div>
        <div class="report-stat-card">
            <div class="report-stat-number">${Object.keys(byIndustry).length}</div>
            <div class="report-stat-label">Industries</div>
        </div>
        <div class="report-stat-card">
            <div class="report-stat-number">${Object.keys(byDepartment).length}</div>
            <div class="report-stat-label">Departments</div>
        </div>
        <div class="report-stat-card">
            <div class="report-stat-number" style="color:var(--red)">${followedJobs.length}</div>
            <div class="report-stat-label">From Followed</div>
        </div>
    </div>`;

    // Industry breakdown
    html += renderBarChart('By Industry', byIndustry, dayJobs.length, colors);

    // Seniority breakdown
    html += renderBarChart('By Seniority', bySeniority, dayJobs.length, colors);

    // Department breakdown
    html += renderBarChart('By Department', byDepartment, dayJobs.length, colors);

    // Followed companies
    if (followedJobs.length > 0) {
        html += `<div class="report-section report-followed-section">
            <h3>From Followed Companies</h3>
            ${renderBarChartInner(byFollowedCompany, followedJobs.length, ['fill-red'])}
        </div>`;
    }

    container.innerHTML = html;
}

function countBy(arr, field) {
    const counts = {};
    arr.forEach(item => {
        const val = item[field] || 'Unknown';
        counts[val] = (counts[val] || 0) + 1;
    });
    return counts;
}

function renderBarChart(title, data, total, colors) {
    return `<div class="report-section">
        <h3>${escapeHtml(title)}</h3>
        ${renderBarChartInner(data, total, colors)}
    </div>`;
}

function renderBarChartInner(data, total, colors) {
    const sorted = Object.entries(data).sort((a, b) => b[1] - a[1]);
    const max = sorted.length > 0 ? sorted[0][1] : 1;

    return `<div class="bar-chart">
        ${sorted.map(([label, count], i) => `
            <div class="bar-row">
                <span class="bar-label">${escapeHtml(label)}</span>
                <div class="bar-track">
                    <div class="bar-fill ${colors[i % colors.length]}" style="width: ${(count / max) * 100}%"></div>
                </div>
                <span class="bar-count">${count}</span>
            </div>
        `).join('')}
    </div>`;
}

// ─── Rendering — Saved Searches Tab ─────────────────────────────────────────

function renderSavedSearchesTab() {
    const container = document.getElementById('savedSearchesContainer');
    const countEl = document.getElementById('savedSearchesCount');

    countEl.textContent = `${state.savedSearches.length} saved`;

    if (state.savedSearches.length === 0) {
        container.innerHTML = '<div class="empty-state">No saved searches yet. Apply filters on the Jobs tab and click "Save Search" to save a filter combination.</div>';
        return;
    }

    container.innerHTML = state.savedSearches.map((search, idx) => {
        const matchCount = countMatchingJobs(search.filters);
        const filterSummary = describeFilters(search.filters);

        return `<div class="saved-search-item" data-idx="${idx}">
            <div style="flex:1">
                <div class="saved-search-name">${escapeHtml(search.name)}</div>
                <div class="saved-search-filters">${filterSummary || 'All jobs (no filters)'}</div>
            </div>
            <span class="saved-search-badge">${matchCount}</span>
            <button class="saved-search-delete" data-action="delete-search" data-idx="${idx}" title="Delete search">&times;</button>
        </div>`;
    }).join('');
}

function countMatchingJobs(filters) {
    return state.allJobs.filter(job => {
        if (filters.search) {
            const haystack = (job.title + ' ' + job.company).toLowerCase();
            if (!haystack.includes(filters.search.toLowerCase())) return false;
        }
        if (filters.location && job.locationEn !== filters.location && job.location !== filters.location) return false;
        if (filters.seniority && job.seniority !== filters.seniority) return false;
        if (filters.industry && job.industry !== filters.industry) return false;
        if (filters.department && job.department !== filters.department) return false;
        if (filters.status === 'unread' && isRead(job.id)) return false;
        if (filters.status === 'read' && !isRead(job.id)) return false;
        if (filters.status === 'saved' && !isSaved(job.id)) return false;
        if (filters.status === 'followed' && !isFollowed(job.company)) return false;
        return true;
    }).length;
}

function describeFilters(filters) {
    const parts = [];
    if (filters.search) parts.push(`"${filters.search}"`);
    if (filters.location) parts.push(filters.location);
    if (filters.seniority) parts.push(filters.seniority);
    if (filters.industry) parts.push(filters.industry);
    if (filters.department) parts.push(filters.department);
    if (filters.status) parts.push(filters.status);
    return parts.join(' / ');
}

// ─── Tab Navigation ─────────────────────────────────────────────────────────

const TAB_MAP = {
    jobs: 'tabJobs',
    savedJobs: 'tabSavedJobs',
    followedCompanies: 'tabFollowedCompanies',
    dailyReport: 'tabDailyReport',
    savedSearches: 'tabSavedSearches',
};

function switchTab(tabName) {
    state.activeTab = tabName;

    // Update tab buttons
    document.querySelectorAll('.tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === tabName);
    });

    // Show/hide sections
    document.querySelectorAll('.tab-content').forEach(s => {
        s.classList.remove('active');
    });
    const sectionId = TAB_MAP[tabName];
    if (sectionId) {
        document.getElementById(sectionId).classList.add('active');
    }

    // Render tab-specific content
    if (tabName === 'savedJobs') renderSavedJobsTab();
    if (tabName === 'followedCompanies') renderFollowedCompaniesTab();
    if (tabName === 'dailyReport') renderDailyReport();
    if (tabName === 'savedSearches') renderSavedSearchesTab();
}

// ─── Save Search Modal ──────────────────────────────────────────────────────

function openSaveSearchModal() {
    const modal = document.getElementById('saveSearchModal');
    const nameInput = document.getElementById('saveSearchName');
    const summary = document.getElementById('modalFilterSummary');

    nameInput.value = '';

    // Show current filters
    const parts = [];
    if (state.filters.search) parts.push(`<span class="filter-tag">Search: "${escapeHtml(state.filters.search)}"</span>`);
    if (state.filters.location) parts.push(`<span class="filter-tag">Location: ${escapeHtml(state.filters.location)}</span>`);
    if (state.filters.seniority) parts.push(`<span class="filter-tag">Seniority: ${escapeHtml(state.filters.seniority)}</span>`);
    if (state.filters.industry) parts.push(`<span class="filter-tag">Industry: ${escapeHtml(state.filters.industry)}</span>`);
    if (state.filters.department) parts.push(`<span class="filter-tag">Department: ${escapeHtml(state.filters.department)}</span>`);
    if (state.filters.status) parts.push(`<span class="filter-tag">Status: ${escapeHtml(state.filters.status)}</span>`);

    summary.innerHTML = parts.length > 0 ? parts.join(' ') : '<span style="color:var(--text-muted)">No filters applied (will match all jobs)</span>';

    modal.classList.remove('hidden');
    setTimeout(() => nameInput.focus(), 50);
}

function closeSaveSearchModal() {
    document.getElementById('saveSearchModal').classList.add('hidden');
}

function confirmSaveSearch() {
    const nameInput = document.getElementById('saveSearchName');
    const name = nameInput.value.trim();
    if (!name) {
        nameInput.style.borderColor = 'var(--red)';
        setTimeout(() => nameInput.style.borderColor = '', 1500);
        return;
    }

    state.savedSearches.push({
        name,
        filters: { ...state.filters },
        createdAt: new Date().toISOString(),
    });
    saveSavedSearches();
    closeSaveSearchModal();
    updateStats();
}

function applySavedSearch(idx) {
    const search = state.savedSearches[idx];
    if (!search) return;

    // Switch to jobs tab
    switchTab('jobs');

    // Apply filters
    state.filters = { ...search.filters };

    // Update UI inputs
    document.getElementById('searchInput').value = state.filters.search || '';
    document.getElementById('locationFilter').value = state.filters.location || '';
    document.getElementById('seniorityFilter').value = state.filters.seniority || '';
    document.getElementById('industryFilter').value = state.filters.industry || '';
    document.getElementById('departmentFilter').value = state.filters.department || '';
    document.getElementById('statusFilter').value = state.filters.status || '';

    applyFilters();
}

function deleteSavedSearch(idx) {
    state.savedSearches.splice(idx, 1);
    saveSavedSearches();
    renderSavedSearchesTab();
    updateStats();
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function getSeniorityBadge(seniority) {
    const classes = {
        'Intern': 'badge-intern',
        'Junior': 'badge-junior',
        'Mid-level': 'badge-mid',
        'Senior': 'badge-senior',
        'Lead': 'badge-lead',
        'Manager': 'badge-manager',
        'Executive': 'badge-executive',
    };
    const cls = classes[seniority] || 'badge-mid';
    return `<span class="badge ${cls}">${escapeHtml(seniority)}</span>`;
}

function formatDate(dateStr) {
    if (!dateStr) return '<span class="date-old">-</span>';

    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    let text, cls;
    if (diffDays === 0) {
        text = 'Today';
        cls = 'date-today';
    } else if (diffDays === 1) {
        text = 'Yesterday';
        cls = 'date-today';
    } else if (diffDays <= 7) {
        text = `${diffDays}d ago`;
        cls = 'date-recent';
    } else if (diffDays <= 30) {
        text = `${Math.floor(diffDays / 7)}w ago`;
        cls = 'date-recent';
    } else {
        text = date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
        cls = 'date-old';
    }

    return `<span class="${cls}" title="${dateStr}">${text}</span>`;
}

function timeAgo(isoStr) {
    const date = new Date(isoStr);
    const now = new Date();
    const diffMs = now - date;
    const mins = Math.floor(diffMs / 60000);
    const hours = Math.floor(mins / 60);

    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
}

// ─── Event Handlers ─────────────────────────────────────────────────────────

function setupEventListeners() {
    // Tab navigation
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // Search input (debounced)
    let searchTimeout;
    document.getElementById('searchInput').addEventListener('input', e => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            state.filters.search = e.target.value;
            applyFilters();
        }, 200);
    });

    // Filter dropdowns
    ['locationFilter', 'seniorityFilter', 'industryFilter', 'departmentFilter', 'statusFilter'].forEach(id => {
        document.getElementById(id).addEventListener('change', e => {
            const filterName = id.replace('Filter', '');
            state.filters[filterName] = e.target.value;
            applyFilters();
        });
    });

    // Sort headers
    document.querySelectorAll('#jobTable th.sortable').forEach(th => {
        th.addEventListener('click', () => setSort(th.dataset.sort));
    });

    // Main table click delegation
    document.getElementById('jobTableBody').addEventListener('click', e => {
        const row = e.target.closest('.job-row');
        if (!row) return;
        const jobId = row.dataset.id;
        const actionEl = e.target.closest('[data-action]');
        const action = actionEl ? actionEl.dataset.action : null;

        // Toggle read/unread on dot click
        if (action === 'toggle') {
            toggleRead(jobId);
            updateRowState(row, jobId);
            updateStats();
            return;
        }

        // Save/unsave job
        if (action === 'save') {
            toggleSaveJob(jobId);
            const saved = isSaved(jobId);
            actionEl.classList.toggle('saved', saved);
            actionEl.textContent = saved ? '\u2605' : '\u2606';
            actionEl.title = saved ? 'Unsave job' : 'Save job';
            updateStats();
            return;
        }

        // Follow/unfollow company
        if (action === 'follow') {
            const company = actionEl.dataset.company;
            toggleFollowCompany(company);
            // Update all follow buttons for this company in current view
            document.querySelectorAll('[data-action="follow"]').forEach(btn => {
                if (btn.dataset.company === company) {
                    const followed = isFollowed(company);
                    btn.classList.toggle('followed', followed);
                    btn.textContent = followed ? '\u2665' : '\u2661';
                    btn.title = followed ? 'Unfollow company' : 'Follow company';
                }
            });
            updateStats();
            return;
        }

        // Open link and mark as read
        if (action === 'open') {
            markRead(jobId);
            updateRowState(row, jobId);
            updateStats();
        }
    });

    // Saved Jobs table click delegation
    document.getElementById('savedJobsTableBody').addEventListener('click', e => {
        const actionEl = e.target.closest('[data-action]');
        if (actionEl && actionEl.dataset.action === 'unsave') {
            const row = actionEl.closest('.job-row');
            if (!row) return;
            toggleSaveJob(row.dataset.id);
            renderSavedJobsTab();
            updateStats();
        }
    });

    // Followed Companies click delegation
    document.getElementById('followedCompaniesContainer').addEventListener('click', e => {
        if (e.target.dataset.action === 'unfollow') {
            const company = e.target.dataset.company;
            toggleFollowCompany(company);
            renderFollowedCompaniesTab();
            updateStats();
        }
    });

    // Saved Searches click delegation
    document.getElementById('savedSearchesContainer').addEventListener('click', e => {
        if (e.target.dataset.action === 'delete-search') {
            e.stopPropagation();
            deleteSavedSearch(parseInt(e.target.dataset.idx, 10));
            return;
        }
        const item = e.target.closest('.saved-search-item');
        if (item) {
            applySavedSearch(parseInt(item.dataset.idx, 10));
        }
    });

    // Save Search button + modal
    document.getElementById('saveSearchBtn').addEventListener('click', openSaveSearchModal);
    document.getElementById('cancelSaveSearch').addEventListener('click', closeSaveSearchModal);
    document.getElementById('confirmSaveSearch').addEventListener('click', confirmSaveSearch);
    document.getElementById('saveSearchName').addEventListener('keydown', e => {
        if (e.key === 'Enter') confirmSaveSearch();
        if (e.key === 'Escape') closeSaveSearchModal();
    });
    document.getElementById('saveSearchModal').addEventListener('click', e => {
        if (e.target === e.currentTarget) closeSaveSearchModal();
    });

    // Daily report date picker
    document.getElementById('reportDate').addEventListener('change', renderDailyReport);

    // Mark all visible as read
    document.getElementById('markAllReadBtn').addEventListener('click', () => {
        const start = (state.currentPage - 1) * state.pageSize;
        const end = start + state.pageSize;
        const pageJobs = state.filteredJobs.slice(start, end);
        pageJobs.forEach(job => markRead(job.id));
        renderTable();
        updateStats();
    });

    // Mark all visible as unread
    document.getElementById('markAllUnreadBtn').addEventListener('click', () => {
        const start = (state.currentPage - 1) * state.pageSize;
        const end = start + state.pageSize;
        const pageJobs = state.filteredJobs.slice(start, end);
        pageJobs.forEach(job => markUnread(job.id));
        renderTable();
        updateStats();
    });

    // Pagination
    document.getElementById('prevPage').addEventListener('click', () => {
        if (state.currentPage > 1) {
            state.currentPage--;
            renderTable();
            renderPagination();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    });

    document.getElementById('nextPage').addEventListener('click', () => {
        const totalPages = Math.ceil(state.filteredJobs.length / state.pageSize);
        if (state.currentPage < totalPages) {
            state.currentPage++;
            renderTable();
            renderPagination();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    });

    document.getElementById('pageSizeSelect').addEventListener('change', e => {
        state.pageSize = parseInt(e.target.value, 10);
        state.currentPage = 1;
        renderTable();
        renderPagination();
    });

    // Refresh link in banner
    document.getElementById('refreshLink').addEventListener('click', e => {
        e.preventDefault();
        init();
    });

    // Refresh button
    document.getElementById('refreshBtn').addEventListener('click', triggerRefresh);

    // Keyboard shortcuts
    document.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            switchTab('jobs');
            document.getElementById('searchInput').focus();
        }
        if (e.key === 'Escape') {
            closeSaveSearchModal();
        }
    });
}

function updateRowState(row, jobId) {
    const read = isRead(jobId);
    row.classList.toggle('read', read);
    row.classList.toggle('unread', !read);

    const dot = row.querySelector('.status-dot');
    if (dot) {
        dot.classList.toggle('read', read);
        dot.classList.toggle('unread', !read);
    }
}

// ─── Manual Refresh ─────────────────────────────────────────────────────────

async function triggerRefresh() {
    const btn = document.getElementById('refreshBtn');
    const progress = document.getElementById('refreshProgress');
    const progressBar = document.getElementById('refreshProgressBar');
    const progressText = document.getElementById('refreshProgressText');
    const originalText = btn.textContent;

    btn.disabled = true;
    btn.classList.add('refreshing');
    btn.textContent = 'Refreshing...';

    // Show indeterminate progress bar
    progress.classList.remove('hidden');
    progressBar.classList.remove('determinate');
    progressText.textContent = 'Fetching new jobs from all sources...';

    // Cycle through progress stages while waiting
    const stages = [
        'Fetching TechMap jobs...',
        'Downloading company data...',
        'Enriching company details...',
        'Fetching Greenhouse jobs...',
        'Fetching Lever jobs...',
        'Deduplicating and processing...',
        'Still working, this can take a few minutes...',
    ];
    let stageIdx = 0;
    const stageInterval = setInterval(() => {
        if (stageIdx < stages.length) {
            progressText.textContent = stages[stageIdx];
            stageIdx++;
        }
    }, 15000);
    // Show first real stage after 3s
    const firstStageTimer = setTimeout(() => {
        progressText.textContent = stages[0];
        stageIdx = 1;
    }, 3000);

    try {
        const resp = await fetch('/api/refresh', { method: 'POST' });
        const data = await resp.json();

        // Clear stage timers
        clearInterval(stageInterval);
        clearTimeout(firstStageTimer);

        if (resp.status === 409) {
            progressText.textContent = 'A refresh is already in progress...';
            btn.textContent = 'Already refreshing...';
            setTimeout(() => {
                btn.textContent = originalText;
                btn.disabled = false;
                btn.classList.remove('refreshing');
                progress.classList.add('hidden');
            }, 3000);
            return;
        }

        if (!resp.ok) throw new Error(data.message || 'Refresh failed');

        // Show completion
        progressBar.classList.add('determinate');
        progressBar.style.setProperty('--progress', '100%');
        progressText.textContent = `Done! Found ${data.newJobs} new job${data.newJobs !== 1 ? 's' : ''} (${data.totalJobs} total)`;

        await init();
        btn.textContent = `Done! ${data.newJobs} new`;
        setTimeout(() => {
            btn.textContent = originalText;
            btn.classList.remove('refreshing');
            progress.classList.add('hidden');
            progressBar.style.removeProperty('--progress');
        }, 3000);
    } catch (e) {
        console.error('Refresh failed:', e);
        clearInterval(stageInterval);
        clearTimeout(firstStageTimer);
        progressText.textContent = 'Data updates automatically every 3 hours.';
        progressText.style.color = 'var(--text-dim)';
        btn.textContent = 'Auto-refresh only';
        setTimeout(() => {
            btn.textContent = originalText;
            btn.classList.remove('refreshing');
            progress.classList.add('hidden');
            progressText.style.color = '';
        }, 4000);
    } finally {
        btn.disabled = false;
    }
}

// ─── Auto-refresh Check ─────────────────────────────────────────────────────

function startAutoRefreshCheck() {
    setInterval(async () => {
        try {
            const resp = await fetch('../data/metadata.json?t=' + Date.now());
            if (!resp.ok) return;
            const meta = await resp.json();

            if (state.lastRefresh && meta.lastRefresh !== state.lastRefresh) {
                document.getElementById('updateBanner').classList.remove('hidden');
            }
        } catch {
            // Ignore
        }
    }, 5 * 60 * 1000);
}

// ─── Init ───────────────────────────────────────────────────────────────────

async function init() {
    loadReadState();
    loadSavedJobs();
    loadFollowedCompanies();
    loadSavedSearches();

    const [jobsOk] = await Promise.all([loadJobs(), loadMetadata()]);
    if (!jobsOk) return;

    document.getElementById('updateBanner').classList.add('hidden');
    document.getElementById('versionBadge').textContent = 'v' + APP_VERSION;

    // Set default date for daily report
    document.getElementById('reportDate').value = new Date().toISOString().slice(0, 10);

    populateFilters();
    applyFilters();
    updateStats();
    startAutoRefreshCheck();
}

// Boot
setupEventListeners();
init();
