// =========================================================
// MIAE ACADEMIC PLANNER — planner.js
// =========================================================

// coursesData GLOBAL — populat în DOMContentLoaded, accesibil din showCourseInfo
let coursesData = {};

// Per-term overrides: { zoneId: { cr: N, cnt: N } }
window.termOverrides    = {};
window.activePopoverZone = null;

// CEGEP / equivalent course codes that map to a WT display name
const WT_ALIASES = {
    'CWTE100': 'WT1', 'CWTE101': 'WT1',
    'CWTE200': 'WT2', 'CWTE201': 'WT2',
    'CWTE300': 'WT3', 'CWTE301': 'WT3',
    'WILE600': 'WT1', 'WILE601': 'WT1',
    'WILE700': 'WT2', 'WILE701': 'WT2'
};

// Courses to completely hide/ignore (CWTE placeholders)
const HIDDEN_COURSES = new Set([]);

// =========================================================
// HELPER FUNCTIONS — accesibile din toată pagina
// =========================================================
function getCourseType(dbCourse) {
    if (dbCourse._unknown) return 'OTHER';
    return dbCourse['CORE_TE'] || 'ENG CORE';
}

function getBorderClass(dbCourse) {
    if (dbCourse._unknown) return 'border-other';
    const t = String(dbCourse['CORE_TE'] || '').toUpperCase();
    if (t === 'REP') return 'border-rep';
    return t.includes('ECP') ? 'border-ecp' : t.includes('PRG') ? 'border-prg' : 'border-eng';
}

function getTermsBadges(dbCourse) {
    let badges = '';
    if (String(dbCourse['SUM 1'] || '').toUpperCase() === 'X' || String(dbCourse['SUM 2'] || '').toUpperCase() === 'X')
        badges += '<span class="term-badge badge-sum">SUM</span> ';
    if (String(dbCourse['FALL'] || '').toUpperCase() === 'X')
        badges += '<span class="term-badge badge-fall">FALL</span> ';
    if (String(dbCourse['WIN'] || '').toUpperCase() === 'X')
        badges += '<span class="term-badge badge-win">WIN</span> ';
    return badges || '<span class="term-badge badge-any">ANY</span>';
}

// Extrage coduri de cursuri dintr-un string req
// Suportă: "ENGR 213", "AERO 490A", "ENGR 1234", "MIAE383"
// Normalizează: fără spații, uppercase, fără sufix A/B (consistent cu dataset.courseId)
function parseCourseIds(str) {
    const matches = String(str || '').match(/[A-Z]{2,5}\s*\d{3,4}[A-Z]?/gi) || [];
    return matches.map(m => {
        const n = m.replace(/\s/g, '').toUpperCase();
        // Preserve 490A/490B suffix
        if (/490[AB]$/i.test(n)) return n;
        return n.replace(/[AB]$/, '');
    });
}

// Normalizează cheia din coursesData la același format ca dataset.courseId
function normKey(key) { return key.replace(/[AB]$/, ''); }

// Lookup robust: încearcă cheia exactă, apoi cu sufix A/B (pentru cursuri 490-style)
function lookupCourse(id) {
    return coursesData[id] || coursesData[id + 'A'] || coursesData[id + 'B'] || null;
}

// Normalize a displayed course id (remove spaces, uppercase)
function normDisplayId(id) { return String(id || '').replace(/\s/g, '').toUpperCase(); }

// For equivalence checks (taken courses etc.), keep 490A/490B distinct; otherwise strip trailing A/B.
function normEquivId(id) {
    const n = normDisplayId(id);
    if (/490[AB]$/i.test(n)) return n;
    return n.replace(/[AB]$/i, '');
}

// Extract the display-id from a course box (e.g. AERO490A). Falls back to id suffix.
function getBoxDisplayId(box) {
    if (!box) return '';
    return normDisplayId(box.dataset.displayId || (box.id || '').split('_').pop());
}

// Parse requirement strings into ids preserving suffix (e.g. AERO 490a -> AERO490A)
function parseReqIdsPreserve(str) {
    const matches = String(str || '').match(/[A-Z]{2,5}\s*\d{3,4}[A-Z]?/gi) || [];
    return matches.map(m => normDisplayId(m));
}

// Lanț ÎNAPOI: cursurile de care depinde startId
// Returnează { light: Set (direct co-reqs), dark: Set (direct pre-reqs + tot tranzitiv) }
function getBackwardChain(startId) {
    const entry     = lookupCourse(startId) || {};
    const directPre = new Set(parseCourseIds(entry['PRE-REQUISITE']));
    const directCo  = new Set(parseCourseIds(entry['CO-REQUISITE']));

    // Co-reqs directe (care nu sunt și pre-reqs) → light
    const light = new Set([...directCo].filter(id => !directPre.has(id)));
    const dark  = new Set([...directPre]);

    // BFS din toate direct pre+co; tot ce găsim → dark
    const visited = new Set([startId, ...directPre, ...directCo]);
    const queue   = [...directPre, ...directCo];
    while (queue.length) {
        const cur    = queue.shift();
        const cEntry = lookupCourse(cur);
        if (!cEntry) continue;
        [...parseCourseIds(cEntry['PRE-REQUISITE']), ...parseCourseIds(cEntry['CO-REQUISITE'])].forEach(id => {
            if (!visited.has(id)) { visited.add(id); dark.add(id); queue.push(id); }
        });
    }
    // dark câștigă față de light
    light.forEach(id => { if (dark.has(id)) light.delete(id); });
    return { light, dark };
}

// Lanț ÎNAINTE: cursurile care depind de startId
// Returnează { light: Set (direct co-req-of), dark: Set (direct pre-req-of + tot tranzitiv) }
function getForwardChain(startId) {
    const directPostPre = new Set();
    const directPostCo  = new Set();

    Object.entries(coursesData).forEach(([key, entry]) => {
        const nk    = normKey(key);
        const pNorm = String(entry['PRE-REQUISITE'] || '').replace(/\s/g, '').toUpperCase();
        const cNorm = String(entry['CO-REQUISITE']  || '').replace(/\s/g, '').toUpperCase();
        if (pNorm.includes(startId)) directPostPre.add(nk);
        if (cNorm.includes(startId)) directPostCo.add(nk);
    });

    const light   = new Set([...directPostCo].filter(id => !directPostPre.has(id)));
    const dark    = new Set([...directPostPre]);
    const visited = new Set([startId, ...directPostPre, ...directPostCo]);
    const queue   = [...directPostPre, ...directPostCo];

    while (queue.length) {
        const cur = queue.shift();
        Object.entries(coursesData).forEach(([key, entry]) => {
            const nk = normKey(key);
            if (visited.has(nk)) return;
            const pNorm = String(entry['PRE-REQUISITE'] || '').replace(/\s/g, '').toUpperCase();
            const cNorm = String(entry['CO-REQUISITE']  || '').replace(/\s/g, '').toUpperCase();
            if (pNorm.includes(cur) || cNorm.includes(cur)) {
                visited.add(nk); dark.add(nk); queue.push(nk);
            }
        });
    }
    light.forEach(id => { if (dark.has(id)) light.delete(id); });
    return { light, dark };
}

// Build WT summary by comparing actual WT placement vs original blue W-x terms
function getPlannedWtMap() {
    const out = {};
    (window.APP_CONFIG.coopTerms || []).forEach(ct => {
        const t = String(ct.type || '').toUpperCase().trim(); // W-1 / S-5 etc.
        const m = t.match(/^W-(\d)$/);
        if (!m) return;
        const wtKey = `WT${m[1]}`;
        out[wtKey] = {
            term: `${ct.year} ${ct.season}`,
            type: t
        };
    });
    return out;
}

function getActualWtMap() {
    const out = {};
    document.querySelectorAll('.drop-zone .course-box.wt').forEach(box => {
        const cid = (box.dataset.courseId || '').toUpperCase();
        const did = (box.dataset.displayId || '').toUpperCase();
        const m = cid.match(/WT(\d)/) || did.match(/WT(\d)/);
        if (!m || !box.parentElement) return;

        const wtKey = `WT${m[1]}`;
        const zid = box.parentElement.id;
        if (zid === 'zone_Unallocated') return;

        const season = zid.split('_').pop();
        const yearMatch = zid.match(/zone_(\d{4}-\d{4})/);
        const newTerm = `${yearMatch ? yearMatch[1] : ''} ${season}`.trim();

        out[wtKey] = { term: newTerm };
    });
    return out;
}


function isCurrentSummerZone(zone) {
    return !!zone &&
        zone.dataset.isCurrent === 'true' &&
        zone.dataset.isSummer === 'true';
}

function isAutoPlaceBlocked(zone) {
    // Past terms stay locked. The only exception is the current Summer term:
    // during Summer, students/admins must be able to move the currently loaded
    // Summer courses while still keeping current Fall/Winter locked.
    return !!zone && (
        zone.dataset.isPast === 'true' ||
        (zone.dataset.isCurrent === 'true' && !isCurrentSummerZone(zone))
    );
}

function showSpinner(msg) {
    const el = document.getElementById('loadingOverlay');
    if (!el) return;
    const msgEl = document.getElementById('spinnerMsg');
    if (msgEl) msgEl.textContent = msg || '';
    el.style.display = 'flex';
}
function hideSpinner() {
    const el = document.getElementById('loadingOverlay');
    if (el) el.style.display = 'none';
}

document.addEventListener("DOMContentLoaded", () => {
    const config = window.APP_CONFIG;
    if (!config) return;

    const studentCourses  = config.studentCourses;
    const coopTerms       = config.coopTerms;
    const cgpaHistory     = config.cgpaHistory;
    const coursesDb       = config.coursesDb;
    const ugrdProgs       = config.ugrdProgs;
    const gradProgs       = config.gradProgs;
    const allProgs        = config.allProgs;
    const isGuest         = config.isGuest;
    const isGrad          = config.isGrad;
    const detectedProgram = config.detectedProgram;

    // Global limits (modificate din Control Panel)
    window.globalMaxCourses = 5;
    window.globalMaxCr      = 18;

    // Populăm dicționarul global coursesData
    if (coursesDb) {
        coursesDb.forEach(c => {
            const key = String(c.COURSE).replace(/\s/g, '').toUpperCase();
            coursesData[key] = c;
        });
    }

    // Build reverse lookup maps: for each course, who lists it as a prereq/coreq?
    window._isPreReqFor = {}; // { courseId -> [listOfCoursesItIsPrereqFor] }
    window._isCoReqFor  = {}; // { courseId -> [listOfCoursesItIsCoReqFor] }
    Object.values(coursesData).forEach(entry => {
        const thisCid   = String(entry.COURSE || '').replace(/\s+/g,'').replace(/[AB]$/,'').toUpperCase();
        const prereqStr = String(entry['PRE-REQUISITE'] || '').replace(/\s/g,'').toUpperCase();
        const coreqStr  = String(entry['CO-REQUISITE']  || '').replace(/\s/g,'').toUpperCase();
        Object.keys(coursesData).forEach(cid => {
            if (prereqStr.includes(cid)) {
                (window._isPreReqFor[cid] = window._isPreReqFor[cid] || new Set()).add(thisCid);
            }
            if (coreqStr.includes(cid)) {
                (window._isCoReqFor[cid] = window._isCoReqFor[cid] || new Set()).add(thisCid);
            }
        });
    });
    // Convert Sets to sorted arrays
    Object.keys(window._isPreReqFor).forEach(k => { window._isPreReqFor[k] = [...window._isPreReqFor[k]].sort(); });
    Object.keys(window._isCoReqFor).forEach(k  => { window._isCoReqFor[k]  = [...window._isCoReqFor[k]].sort();  });

    // --- CALCULE TIMP ---
    const now              = new Date();
    const currentMonth     = now.getMonth() + 1;
    const currentYear      = now.getFullYear();

    let currentSeason = 'Winter';
    if (currentMonth >= 5 && currentMonth <= 8)  currentSeason = 'Summer';
    else if (currentMonth >= 9 && currentMonth <= 12) currentSeason = 'Fall';

    const currentAcaYearStart = (currentMonth < 5) ? currentYear - 1 : currentYear;
    const currentAcaYearStr   = `${currentAcaYearStart}-${currentAcaYearStart + 1}`;
    const minAllowedYear      = currentAcaYearStart - 2;

    let detectedStartYear = currentAcaYearStart;
    if (studentCourses && studentCourses.length > 0) {
        let oldestYear = 9999;
        studentCourses.forEach(c => {
            if (c.year && c.year.includes('-')) {
                let yBase = parseInt(c.year.split('-')[0]);
                if (yBase < oldestYear) oldestYear = yBase;
            }
        });
        detectedStartYear = oldestYear; // Use actual oldest year, not clamped
    }

    // =========================================================
    // DRAG & DROP
    // =========================================================
    window.allowDrop = function(ev) {
        ev.preventDefault();
        ev.currentTarget.classList.add('dragover');
    };

    window.drag = function(ev) {
        ev.dataTransfer.setData("text", ev.target.id);
    };

    window.drop = function(ev) {
        ev.preventDefault();
        document.querySelectorAll('.drop-zone').forEach(z => z.classList.remove('dragover'));
        const id = ev.dataTransfer.getData("text");
        const el = document.getElementById(id);
        if (!el) return;
        const dropZone = ev.currentTarget;
        if (dropZone && dropZone.classList.contains('drop-zone')) {
            dropZone.appendChild(el);
            const isGridZone = dropZone.id !== 'zone_Unallocated'; // Y0 also auto-pins
            // Pin when manually dropped on grid; unpin when returned to Unallocated/Y0
            if (isGridZone && !el.classList.contains('course-taken')) {
                el.dataset.pinned = 'true';
                el.classList.add('pinned');
                const cb = el.querySelector('.c-checkbox');
                if (cb && !cb.disabled) cb.checked = true;
            } else {
                delete el.dataset.pinned;
                el.classList.remove('pinned');
                const cb = el.querySelector('.c-checkbox');
                if (cb && !cb.disabled) cb.checked = false;
            }
            // Auto-check CO-OP if a WT course is dragged onto the grid
            if (isGridZone && el.classList.contains('wt')) {
                const coopCb = document.getElementById('coopRegistered');
                if (coopCb && !coopCb.checked) {
                    coopCb.checked = true;
                    window.rebuildGrid();
                    return; // rebuildGrid calls updateCredits
                }
            }
            // If dropped into Unallocated, re-sort the zone
            if (dropZone.id === 'zone_Unallocated') {
                window.sortUnallocated();
            }
            window.updateCredits();
        }
    };

    // Toggle pin state when user manually clicks the checkbox
    window.toggleCoursePin = function(cb) {
        const box = cb.closest('.course-box');
        if (!box) return;
        if (cb.checked) {
            box.dataset.pinned = 'true';
            box.classList.add('pinned');
        } else {
            delete box.dataset.pinned;
            box.classList.remove('pinned');
        }
    };

    // =========================================================
    // GENERARE HTML CURS
    // =========================================================
    function generateCourseHTML(cId, credits, dbCourse, isTaken, grade) {
        let title      = dbCourse.TITLE || '';
        let type       = getCourseType(dbCourse);
        let termBadges = getTermsBadges(dbCourse);

        const prereq = dbCourse['PRE-REQUISITE'] || 'None';
        const coreq  = dbCourse['CO-REQUISITE']  || 'None';
        const baseCid = cId.replace(/[AB]$/, '').replace(/\s/g, '').toUpperCase();
        const isPreFor = (window._isPreReqFor?.[baseCid] || []).join(', ') || 'None';
        const isCoFor  = (window._isCoReqFor?.[baseCid]  || []).join(', ') || 'None';

        let checkbox = isTaken
            ? `<input type="checkbox" class="c-checkbox" checked disabled>`
            : `<input type="checkbox" class="c-checkbox" onclick="window.toggleCoursePin(this)">`;

        // Add grade badge for taken courses (only for power users)
        let gradeBadge = '';
        const isPowerUser = window.APP_CONFIG?.isPowerUser || false;
        if (isTaken && grade && isPowerUser) {
            // Determine grade class based on letter grade
            let gradeClass = 'grade-other';
            const gradeUpper = grade.toUpperCase();
            if (gradeUpper.startsWith('A')) {
                gradeClass = 'grade-a';
            } else if (gradeUpper.startsWith('B')) {
                gradeClass = 'grade-b';
            } else if (gradeUpper.startsWith('C') || gradeUpper.startsWith('D')) {
                gradeClass = 'grade-cd';
            } else if (gradeUpper.startsWith('F') || gradeUpper.startsWith('R')) {
                gradeClass = 'grade-fail';
            } else if (gradeUpper === 'DISC') {
                gradeClass = 'grade-disc';
            }
            gradeBadge = `<span class="grade-badge ${gradeClass}">${grade}</span>`;
        }

        return `
            ${checkbox}
            <div class="c-headline">
                <span class="c-code">${cId} (${credits}cr)</span>
                ${gradeBadge}
                <span class="c-title">${title}</span>
            </div>
            <div class="c-meta">
                <span class="c-type">[${type}]</span>
                <div class="c-badges">${termBadges}</div>
            </div>
            <div class="c-reqs">
                <div><b>PRE-req:</b> ${prereq}&nbsp;&nbsp;||&nbsp;&nbsp;<b>CO-req:</b> ${coreq}</div>
                <div><b>is pre for:</b> ${isPreFor}&nbsp;&nbsp;||&nbsp;&nbsp;<b>is co for:</b> ${isCoFor}</div>
            </div>
        `;
    }

    // =========================================================
    // CONSTRUIRE GRID
    // =========================================================
    window.rebuildGrid = function() {
        const tbody = document.getElementById('tableBody');
        if (!tbody) return;
        tbody.innerHTML = '';
        window.termOverrides = {}; // reset per-term overrides on grid rebuild

        const sYearStr = document.getElementById('startYear').value;
        const baseYear = parseInt(sYearStr.split('-')[0]);
        const isCoop   = document.getElementById('coopRegistered').checked;
        const seasons  = ['Summer', 'Fall', 'Winter'];

        // Rândul Y0
        const trY0 = document.createElement('tr');
        trY0.innerHTML = `
            <td class="year-label"><strong>Y 0</strong><span class="year-subtext">Past / Exempt</span></td>
            <td colspan="3" style="background:#fdfdfd; padding:10px;">
                <div class="drop-zone drop-zone-horizontal" id="zone_Y0"
                     style="min-height:50px; border:2px dashed #bdc3c7;"
                     ondragover="allowDrop(event)" ondrop="drop(event)"></div>
            </td>`;
        tbody.appendChild(trY0);
        
        // Add term name headers between Y0 and Y1
        const headerY0Y1 = document.createElement('tr');
        headerY0Y1.className = 'term-names-row';
        headerY0Y1.innerHTML = `
            <td style="padding:0;height:18px;background:#f8f9fa;"></td>
            <td style="background:#f8f9fa;padding:1px 0;text-align:center;height:18px;">
                <span style="font-size:9px;color:#27ae60;font-weight:bold;font-size:13px">Summer</span>
            </td>
            <td style="background:#f8f9fa;padding:1px 0;text-align:center;height:18px;">
                <span style="font-size:9px;color:#d35400;font-weight:bold;font-size:13px">Fall</span>
            </td>
            <td style="background:#f8f9fa;padding:1px 0;text-align:center;height:18px;">
                <span style="font-size:9px;color:#2980b9;font-weight:bold;font-size:13px">Winter</span>
            </td>`;
        tbody.appendChild(headerY0Y1);

        // helper: term order number for past/future comparison
        const seasonOrd = { Summer: 1, Fall: 2, Winter: 3 };
        const currentTermOrd = parseInt(currentAcaYearStr.split('-')[0]) * 10 + (seasonOrd[currentSeason] || 0);

        for (let y = 1; y <= 7; y++) {
            // Add colored header row before each year (except Y1 since we added it after Y0)
            if (y > 1) {
                const headerTr = document.createElement('tr');
                headerTr.className = 'term-names-row';
                headerTr.innerHTML = `
                    <td style="padding:0;height:18px;background:#f8f9fa;"></td>
                    <td style="background:#f8f9fa;padding:1px 0;text-align:center;height:18px;">
                        <span style="font-size:9px;color:#27ae60;font-weight:bold;font-size:13px;">Summer</span>
                    </td>
                    <td style="background:#f8f9fa;padding:1px 0;text-align:center;height:18px;">
                        <span style="font-size:9px;color:#d35400;font-weight:bold;font-size:13px;">Fall</span>
                    </td>
                    <td style="background:#f8f9fa;padding:1px 0;text-align:center;height:18px;">
                        <span style="font-size:9px;color:#2980b9;font-weight:bold;font-size:13px;">Winter</span>
                    </td>`;
                tbody.appendChild(headerTr);
            }
            
            const tr         = document.createElement('tr');
            const rowAcaYear = `${baseYear + y - 1}-${baseYear + y}`;
            let rowHtml = `<td class="year-label"><strong>Y ${y}</strong><span class="year-subtext">${rowAcaYear}</span></td>`;

            seasons.forEach(season => {
                const zoneId    = `zone_${rowAcaYear}_${season}`;
                const hardMaxCr = season === 'Summer' ? 16 : 18;
                const termOrd   = parseInt(rowAcaYear.split('-')[0]) * 10 + (seasonOrd[season] || 0);
                const isPast    = termOrd < currentTermOrd;
                const isCurrent = termOrd === currentTermOrd;

                let tdClass     = '';
                let headerClass = 'term-header';
                let coopLabel   = '';
                let cgpaHtml    = '';

                if (cgpaHistory) {
                    let found = cgpaHistory.find(h => h.year === rowAcaYear && h.season === season);
                    if (found && found.info) cgpaHtml = `<div class="cgpa-info">${found.info}</div>`;
                }

                if (rowAcaYear === currentAcaYearStr && season === currentSeason) tdClass = 'current-term-bg';

                let isStudyTerm = false;
                if (isCoop && coopTerms) {
                    let ct = coopTerms.find(t => t.year === rowAcaYear && t.season === season);
                    if (ct) {
                        const isWork = ct.type.startsWith('W');
                        headerClass += isWork ? ' coop-work-header' : ' coop-study-header';
                        isStudyTerm  = !isWork;
                        coopLabel    = ` <span style="color:${isWork ? '#e74c3c' : '#2980b9'};font-weight:900;">[${ct.type}]</span>`;
                        
                        // Add Term Details if present (bold dark red)
                        if (ct.details && ct.details.trim()) {
                            coopLabel += `<br><span style="font-size:11px;color:#8B0000;font-weight:bold;">${ct.details}</span>`;
                        }
                        
                        // Add Jobs View/Applied info only if either > 0
                        const jobsView = parseInt(ct.jobs_view) || 0;
                        const jobsApplied = parseInt(ct.jobs_applied) || 0;
                        
                        if (jobsView > 0 || jobsApplied > 0) {
                            const jobParts = [];
                            if (jobsView > 0) {
                                jobParts.push(`view: ${jobsView}`);
                            }
                            if (jobsApplied > 0) {
                                jobParts.push(`app: ${jobsApplied}`);
                            }
                            
                            const jobInfo = jobParts.join(' / ');
                            
                            // Add WS content on separate line if present
                            if (ct.ws && ct.ws.trim()) {
                                coopLabel += `<br><span style="font-size:11px;color:#8B0000;font-weight:bold;">${ct.ws}</span>`;
                                coopLabel += `<br><span style="font-size:11px;color:#8B0000;font-weight:bold;">${jobInfo}</span>`;
                            } else {
                                coopLabel += `<br><span style="font-size:11px;color:#8B0000;font-weight:bold;">${jobInfo}</span>`;
                            }
                        }
                    }
                }

                rowHtml += `
                    <td class="${tdClass.trim()}">
                        <div class="${headerClass}">
                            <span>Cr:<span id="cr_${zoneId}" style="color:${isStudyTerm ? '#2980b9' : '#912338'};">0</span> | <span id="cnt_${zoneId}" style="color:${isStudyTerm ? '#2980b9' : '#912338'};">#0</span>${coopLabel}</span>
                            <span id="limits_${zoneId}" style="cursor:pointer;text-decoration:underline dotted #aaa;" title="Click to override this term's limits" onclick="event.stopPropagation(); window.openTermPopover('${zoneId}', this)">≤<span id="maxCr_${zoneId}">${hardMaxCr}</span>cr | ≤<span id="maxCnt_${zoneId}">-</span>#</span>
                        </div>
                        <div id="restrictions_${zoneId}" class="term-restrictions-container"></div>
                        ${cgpaHtml}
                        <div class="drop-zone" id="${zoneId}"
                             data-is-past="${isPast}"
                             data-is-current="${isCurrent}"
                             data-is-summer="${season === 'Summer'}"
                             data-hard-max-cr="${hardMaxCr}"
                             ondragover="allowDrop(event)" ondrop="drop(event)"></div>
                    </td>`;
            });

            tr.innerHTML = rowHtml;
            tbody.appendChild(tr);
        }

        placeCourses();
        window.updateUnallocated();
        window.updateCredits(); // re-run after unallocated is populated (WT detection needs full DOM)
        if (window.updateSubmitVisibility) window.updateSubmitVisibility();
        const ws = document.getElementById('workspace');
        if (ws) ws.style.visibility = 'visible';
    };

    // =========================================================
    // PLASARE CURSURI DIN TRANSCRIPT ÎN GRID
    // =========================================================
    function placeCourses() {
        document.querySelectorAll('.course-box').forEach(e => e.remove());
        const sYearStr = document.getElementById('startYear').value;
        if (!sYearStr || !studentCourses) return;

        const sYearBase = parseInt(sYearStr.split('-')[0]);
        const isCoop    = document.getElementById('coopRegistered').checked;
        const placedWtAliases = new Set();

        studentCourses.forEach((c, i) => {
            const rawCid = c.id.replace(/\s/g, '').toUpperCase();

            // Skip hidden courses entirely
            if (HIDDEN_COURSES.has(rawCid)) return;

            const isCvteWt = rawCid in WT_ALIASES;
            const displayId = isCvteWt ? WT_ALIASES[rawCid] : c.id;

            // Only place each WT alias (WT1/WT2/WT3) once even if multiple CWTE/WILE codes exist
            if (isCvteWt) {
                if (placedWtAliases.has(displayId)) return;
                placedWtAliases.add(displayId);
            }
            const isWt = c.id.includes('WT') || isCvteWt;

            if (!isCoop && isWt) return;

            let baseCid  = displayId.replace(/[AB]$/, '').replace(/\s/g, '').toUpperCase();
            // For 490 courses, keep the A/B suffix for correct lookup
            if (/490[AB]$/i.test(normDisplayId(displayId))) {
                baseCid = normDisplayId(displayId);
            }
            let dbCourse = lookupCourse(baseCid) || { _unknown: true };

            let borderClass = getBorderClass(dbCourse);

            const div            = document.createElement('div');
            div.id               = `course_student_${i}_${rawCid}`;
            // CVTE/WILE→WT alias: shown green (wt-alias overrides course-taken gray)
            // Actual WT courses from transcript also keep wt class
            const isWtDisplay = c.id.includes('WT') || isCvteWt;
            const isCurrentSummerCourse = (
                currentSeason === 'Summer' &&
                c.year === currentAcaYearStr &&
                c.season === 'Summer'
            );
            const isLockedTaken = !isCurrentSummerCourse;
            div.className        = `course-box ${borderClass} ${isWtDisplay ? 'wt' : ''} ${isCvteWt ? 'wt-alias' : ''} ${isLockedTaken ? 'course-taken' : 'current-summer-course movable-current-term'}`;
            div.dataset.credit   = isWt ? 0 : c.credit;
            div.dataset.courseId = baseCid;
            div.dataset.displayId = normDisplayId(displayId);
            div.dataset.grade    = c.grade || "";
            if (isCurrentSummerCourse) div.dataset.currentSummerMovable = 'true';
            div.draggable      = true;
            div.ondragstart    = window.drag;
            div.innerHTML      = generateCourseHTML(
                isCvteWt ? `${displayId} (${c.id})` : c.id,
                isWt ? 0 : c.credit, dbCourse, isLockedTaken, c.grade);
            if (isCurrentSummerCourse) {
                div.dataset.pinned = 'true';
                div.classList.add('pinned');
                const cb = div.querySelector('.c-checkbox');
                if (cb && !cb.disabled) cb.checked = true;
            }
            div.onclick        = () => window.showCourseInfo(displayId);

            let cYearBase = parseInt(c.year.split('-')[0]);
            if (cYearBase < sYearBase) {
                const z0 = document.getElementById('zone_Y0');
                if (z0) { div.dataset.originalZone = 'zone_Y0'; z0.appendChild(div); }
            } else {
                const zoneId = `zone_${c.year}_${c.season}`;
                const zone = document.getElementById(zoneId);
                if (zone) { div.dataset.originalZone = zoneId; zone.appendChild(div); }
                else {
                    const z0 = document.getElementById('zone_Y0');
                    if (z0) { div.dataset.originalZone = 'zone_Y0'; z0.appendChild(div); }
                }
            }
        });

        window.updateCredits();
    }

    // =========================================================
    // CURSURI NEALOCATE (SIDEBAR)
    // =========================================================
    window.updateUnallocated = function() {
        const unallocZone = document.getElementById('zone_Unallocated');
        if (!unallocZone) return;
        unallocZone.innerHTML = '';

        const progSel = document.getElementById('programSelect');
        if (!progSel || !progSel.value) return;

        const selectedProg = progSel.value;
        const isCoop       = document.getElementById('coopRegistered').checked;
        if (!studentCourses || !coursesDb) return;

        // Taken courses: keep 490A/490B distinct; everything else compares by base (strip A/B)
        // Also mark WT alias targets as taken (e.g. CWTE101 → WT1 means WT1 is taken)
        const takenExact = new Set();
        const takenEquiv = new Set();
        studentCourses.forEach(c => {
            const rawCid = c.id.replace(/\s/g, '').toUpperCase();
            takenExact.add(normDisplayId(c.id));
            takenEquiv.add(normEquivId(c.id));
            const alias = WT_ALIASES[rawCid];
            if (alias) {
                takenExact.add(normDisplayId(alias));
                takenEquiv.add(normEquivId(alias));
            }
        });

        const items = [];

        coursesDb.filter(c => c.PROGRAM === selectedProg).forEach((c, i) => {
            const cId = normDisplayId(c.COURSE);
            const is490Split = /490[AB]$/.test(cId);
            const baseCid = is490Split ? cId : cId.replace(/[AB]$/, '');

            // Skip hidden courses
            if (HIDDEN_COURSES.has(cId)) return;

            if (!isCoop && cId.includes('WT')) return;

            // Skip if taken
            if (takenExact.has(cId)) return;
            if (!is490Split && takenEquiv.has(baseCid)) return;

            let dbCourse    = lookupCourse(baseCid) || c;
            let borderClass = getBorderClass(dbCourse);

            const div            = document.createElement('div');
            div.id               = `course_unalloc_${i}_${cId}`;
            div.className        = `course-box ${borderClass} ${cId.includes('WT') ? 'wt' : ''}`;
            div.dataset.credit   = cId.includes('WT') ? 0 : (c.CREDIT || 0);
            div.dataset.courseId = baseCid;       // base id used for lookup/highlighting
            div.dataset.displayId = cId;          // stable display id (preserves 490A/490B)
            div.draggable      = true;
            div.ondragstart    = window.drag;
            div.innerHTML      = generateCourseHTML(cId, cId.includes('WT') ? 0 : (c.CREDIT || 0), dbCourse, false);
            div.onclick        = () => window.showCourseInfo(cId);

            items.push({ cId, div, isWT: cId.includes('WT') });
        });

        // WT courses at the top, then regular alphabetical
        const alpha = (a, b) => a.cId.localeCompare(b.cId);
        const wt      = items.filter(x =>  x.isWT).sort(alpha);
        const regular = items.filter(x => !x.isWT).sort(alpha);

        [...wt, ...regular].forEach(x => unallocZone.appendChild(x.div));
    };

    // =========================================================
    // UPDATE CREDITE ȘI CURSURI ÎN HEADER TERMEN
    // =========================================================
    window.updateCredits = function() {
        document.querySelectorAll('td').forEach(td => {
            const zone = td.querySelector('.drop-zone');
            if (!zone || zone.id === 'zone_Y0' || zone.id === 'zone_Unallocated') return;

            let total = 0, count = 0;
            Array.from(zone.children).forEach(child => {
                if (child.classList.contains('course-box')) {
                    total += parseFloat(child.dataset.credit || 0);
                    count++;
                }
            });

            const isPast    = zone.dataset.isPast === 'true';
            const isSummer  = zone.dataset.isSummer === 'true';
            const hardMaxCr = parseFloat(zone.dataset.hardMaxCr || (isSummer ? 16 : 18));

            // Limite efective
            let effMaxCr, effMaxCnt;
            if (isPast) {
                effMaxCr  = (total % 1 === 0) ? total : parseFloat(total.toFixed(2));
                effMaxCnt = count;
            } else {
                const ov  = window.termOverrides[zone.id] || {};
                effMaxCr  = ov.cr  !== undefined ? ov.cr  : Math.min(window.globalMaxCr, hardMaxCr);
                effMaxCnt = ov.cnt !== undefined ? ov.cnt : (isSummer ? Math.max(1, window.globalMaxCourses - 1) : window.globalMaxCourses);
            }

            const totalStr = (total % 1 === 0) ? total : total.toFixed(2);
            const over     = !isPast;

            const _isStudyTerm = !!td.querySelector('.coop-study-header');
            const _normalColor = _isStudyTerm ? '#2980b9' : '#912338';

            const crSpan = document.getElementById(`cr_${zone.id}`);
            if (crSpan) { crSpan.innerText = totalStr; crSpan.style.color = (over && total > effMaxCr) ? '#e74c3c' : _normalColor; }

            const cntSpan = document.getElementById(`cnt_${zone.id}`);
            if (cntSpan) { cntSpan.innerText = '#' + count; cntSpan.style.color = (over && count > effMaxCnt) ? '#e74c3c' : _normalColor; }

            const maxCrSpan = document.getElementById(`maxCr_${zone.id}`);
            if (maxCrSpan) maxCrSpan.innerText = effMaxCr;

            const maxCntSpan = document.getElementById(`maxCnt_${zone.id}`);
            if (maxCntSpan) maxCntSpan.innerText = effMaxCnt;

            // Update restrictions display for this term
            if (window.checkRestrictions) {
                const season = zone.id.split('_').pop();
                const yearMatch = zone.id.match(/zone_(\d{4}-\d{4})/);
                const yearStr = yearMatch ? yearMatch[1] : '';
                const restrictions = window.checkRestrictions(zone.id, season, yearStr);
                const restContainer = document.getElementById(`restrictions_${zone.id}`);
                if (restContainer) {
                    restContainer.innerHTML = '';
                    const seen = new Set();
                    restrictions.forEach(r => {
                        if (seen.has(r.text)) return;
                        seen.add(r.text);
                        const div = document.createElement('div');
                        div.className = `term-restriction-warning ${r.isWarning ? 'warning-yes' : 'warning-no'}`;
                        div.style.whiteSpace = 'pre-line';
                        div.textContent = r.text;
                        restContainer.appendChild(div);
                    });
                }
            }
        });

        // Not full-time check: blue (S-x) Fall/Winter terms, plus any Fall/Winter term
        // between the first S-x zone and the last placed WT
        (function() {
            const progNamesDb  = window.APP_CONFIG?.programNamesDb || [];
            const selectedProg = document.getElementById('programSelect')?.value || '';
            const progRow      = progNamesDb.find(r => String(r['Program'] || '').trim() === selectedProg);
            const creditsFT    = progRow ? parseFloat(progRow['Credits_FT']) : NaN;
            const isACSD       = !!document.getElementById('acsdRegistered')?.checked;

            function _sk(zid) {
                const m = zid.match(/zone_(\d{4}-\d{4})_(\w+)/);
                return m ? `${m[1]}-${{ Summer:1, Fall:2, Winter:3 }[m[2]] || 0}` : '';
            }

            // first blue (S-x) zone key
            let firstCoopKey = '';
            document.querySelectorAll('td').forEach(td => {
                if (!td.querySelector('.coop-study-header')) return;
                const z = td.querySelector('.drop-zone');
                if (!z || z.id === 'zone_Y0' || z.id === 'zone_Unallocated') return;
                const k = _sk(z.id);
                if (k && (!firstCoopKey || k < firstCoopKey)) firstCoopKey = k;
            });

            // Find the highest WT number that exists anywhere
            let maxWtNum = 0;
            document.querySelectorAll('.course-box.wt').forEach(b => {
                const did = (b.dataset.displayId || b.dataset.courseId || '').toUpperCase();
                const m = did.match(/WT(\d)/);
                if (m) maxWtNum = Math.max(maxWtNum, parseInt(m[1]));
            });

            // Find the zone of the highest WT (only if placed in grid, not Unallocated)
            let lastWtKey = '';
            if (maxWtNum > 0) {
                document.querySelectorAll('.drop-zone').forEach(zone => {
                    if (zone.id === 'zone_Unallocated' || zone.id === 'zone_Y0') return;
                    const hasMaxWt = Array.from(zone.children).some(c => {
                        if (!c.classList.contains('wt')) return false;
                        const did = (c.dataset.displayId || c.dataset.courseId || '').toUpperCase();
                        const m = did.match(/WT(\d)/);
                        return m && parseInt(m[1]) === maxWtNum;
                    });
                    if (hasMaxWt) {
                        const k = _sk(zone.id);
                        if (k > lastWtKey) lastWtKey = k;
                    }
                });
            }

            document.querySelectorAll('td').forEach(td => {
                const zone = td.querySelector('.drop-zone');
                if (!zone || zone.id === 'zone_Y0' || zone.id === 'zone_Unallocated') return;
                const restContainer = document.getElementById(`restrictions_${zone.id}`);
                if (!restContainer) return;

                // remove previous FT warning
                restContainer.querySelectorAll('.ft-warning').forEach(el => el.remove());

                if (isNaN(creditsFT)) return;
                const season = zone.id.split('_').pop();
                if (season !== 'Fall' && season !== 'Winter') return;

                const isBlue  = !!td.querySelector('.coop-study-header');
                const zKey    = _sk(zone.id);
                
                // NEW LOGIC: If highest WT is placed and this zone is after it, skip validation for blue terms
                if (lastWtKey && zKey > lastWtKey && isBlue) {
                    return; // Skip full-time check for blue terms after highest WT
                }
                
                const inRange = firstCoopKey && lastWtKey && zKey >= firstCoopKey && zKey <= lastWtKey;
                if (!isBlue && !inRange) return; // must be blue or within co-op range

                if (zone.querySelector('.course-box.wt')) return; // WT placed → full time

                const termCr = Array.from(zone.children)
                    .filter(c => c.classList.contains('course-box'))
                    .reduce((s, c) => s + parseFloat(c.dataset.credit || 0), 0);

                if (termCr >= creditsFT) return;

                const yearMatch = zone.id.match(/zone_(\d{4}-\d{4})_/);
                const label = `${yearMatch ? yearMatch[1] : ''} ${season}`.trim();

                const msg = isACSD
                    ? '!! Student is registered with ACSD — enter in justification the credits approved by ACSD.'
                    : `Not full-time: ${label} has ${termCr}cr < FT minimum of ${creditsFT}cr — add justification`;

                const div = document.createElement('div');
                div.className = 'term-restriction-warning warning-yes ft-warning';
                div.textContent = msg;
                restContainer.appendChild(div);
            });
        })();

        // After last placed WT: show FYI note on all subsequent terms
        (function() {
            // helper: zone sort key → "YYYY-YYYY-N" where N: Summer=1, Fall=2, Winter=3
            function zoneSortKey(zid) {
                const ym = zid.match(/zone_(\d{4}-\d{4})_(\w+)/);
                if (!ym) return '';
                const sn = { Summer: 1, Fall: 2, Winter: 3 }[ym[2]] || 0;
                return `${ym[1]}-${sn}`;
            }

            // collect all grid zones in chronological order (exclude Y0 and Unallocated)
            const allGridZones = Array.from(document.querySelectorAll('.drop-zone'))
                .filter(z => z.id !== 'zone_Y0' && z.id !== 'zone_Unallocated' && /zone_\d{4}-\d{4}_/.test(z.id))
                .sort((a, b) => zoneSortKey(a.id).localeCompare(zoneSortKey(b.id)));

            // find the highest WT number that exists anywhere (grid + unallocated)
            let maxWtNum = 0;
            document.querySelectorAll('.course-box.wt').forEach(b => {
                const did = (b.dataset.displayId || b.dataset.courseId || '').toUpperCase();
                const m = did.match(/WT(\d)/);
                if (m) maxWtNum = Math.max(maxWtNum, parseInt(m[1]));
            });

            // find the zone of the highest WT — only counts if placed in grid (not Unallocated)
            let lastWtKey = '';
            if (maxWtNum > 0) {
                allGridZones.forEach(z => {
                    const hasMaxWt = Array.from(z.children).some(c => {
                        if (!c.classList.contains('wt')) return false;
                        const did = (c.dataset.displayId || c.dataset.courseId || '').toUpperCase();
                        const m = did.match(/WT(\d)/);
                        return m && parseInt(m[1]) === maxWtNum;
                    });
                    if (hasMaxWt) {
                        const k = zoneSortKey(z.id);
                        if (k > lastWtKey) lastWtKey = k;
                    }
                });
            }

            const FYI_MSG = 'might not be full time (< 12CR accepted). Note: International students - check with ISO';

            allGridZones.forEach(z => {
                const restContainer = document.getElementById(`restrictions_${z.id}`);
                if (!restContainer) return;

                // remove any previous FYI-post-WT note
                restContainer.querySelectorAll('.post-wt-fyi').forEach(el => el.remove());

                if (!lastWtKey) return; // no WT placed yet
                if (zoneSortKey(z.id) <= lastWtKey) return; // not after last WT

                // skip if an overlapping restriction note is already shown
                const existingTexts = Array.from(restContainer.querySelectorAll('.term-restriction-warning'))
                    .map(el => el.textContent.toLowerCase());
                const hasOverlap = existingTexts.some(t => t.includes('12') || t.includes('full time') || t.includes('off'));
                if (hasOverlap) return;

                const div = document.createElement('div');
                div.className = 'term-restriction-warning warning-no post-wt-fyi';
                div.textContent = FYI_MSG;
                restContainer.appendChild(div);
            });
        })();

        // LOW GPA next-2-terms visual warning (2 terms after current term)
        // UGRAD: GPA past 24.5cr < threshold+0.2 (e.g. < 2.7) OR CGPA < threshold (e.g. < 2.5)
        // GRAD: CGPA < 3.3
        (function() {
            // remove any previous low-gpa-next-term divs
            document.querySelectorAll('.low-gpa-next-term').forEach(el => el.remove());

            const _isGradProg2 = !!window.APP_CONFIG?.isGrad || (document.getElementById('programSelect')?.value || '').toUpperCase().includes('GRAD');
            const progNamesDb  = window.APP_CONFIG?.programNamesDb || [];
            const selectedProg = document.getElementById('programSelect')?.value || '';
            const progRow      = progNamesDb.find(r => String(r['Program'] || '').trim() === selectedProg);
            const threshold    = _isGradProg2 ? 3.3 : (progRow ? parseFloat(progRow['GPA_2_terms']) : NaN);
            const history      = window.APP_CONFIG?.cgpaHistory || [];

            if (isNaN(threshold) || !history.length) return;

            const gpaThreshold = _isGradProg2 ? 3.3 : threshold + 0.2; // GRAD: 3.3, UGRAD: 2.7
            const last      = history[history.length - 1];
            const infoStr   = String(last.info || '');
            // Extract GPA past Xcr value — handles both <b>val</b> and plain text formats
            const recentM   = infoStr.match(/<b>([\d.]+)<\/b>/) || infoStr.match(/GPA past [\d.]+cr:\s*([\d.]+)/);
            const cgpaM     = infoStr.match(/CGPA\s+([\d.]+)/);
            const recentGpa = recentM ? parseFloat(recentM[1]) : null;
            const cgpa      = cgpaM   ? parseFloat(cgpaM[1])   : null;
            const termLabel = `${last.year} ${last.season}`;

            // build a descriptive reason string for any failing metric
            const reasons = [];
            if (recentGpa !== null && recentGpa < gpaThreshold) reasons.push(`GPA past 24.5cr = ${recentGpa} (< ${gpaThreshold})`);
            if (cgpa      !== null && cgpa      < threshold)    reasons.push(`CGPA = ${cgpa} (< ${threshold})`);
            if (!reasons.length) return;

            const reasonStr = reasons.join(' or ') + ` in ${termLabel}`;

            // Use current term as anchor (not the low-GPA term)
            const currentZoneKey = `${currentAcaYearStr}-${{ Summer:1, Fall:2, Winter:3 }[currentSeason] || 0}`;

            // collect all grid zones sorted chronologically
            const allZones = Array.from(document.querySelectorAll('.drop-zone'))
                .filter(z => z.id && z.id !== 'zone_Unallocated' && z.id !== 'zone_Y0')
                .map(z => {
                    const m = z.id.match(/zone_(\d{4}-\d{4})_(\w+)/);
                    return m ? { zone: z, key: `${m[1]}-${{ Summer:1, Fall:2, Winter:3 }[m[2]] || 0}` } : null;
                })
                .filter(Boolean)
                .sort((a, b) => a.key < b.key ? -1 : a.key > b.key ? 1 : 0);

            // find the 2 zones immediately after the current term
            const afterIdx = allZones.findIndex(z => z.key > currentZoneKey);
            if (afterIdx === -1) return;
            const nextTwo = allZones.slice(afterIdx, afterIdx + 2);

            // Show restriction in next 2 terms after current
            nextTwo.forEach(({ zone }) => {
                const restContainer = document.getElementById(`restrictions_${zone.id}`);
                if (!restContainer) return;
                const div = document.createElement('div');
                div.className = 'term-restriction-warning warning-yes low-gpa-next-term';
                div.textContent = `no WT due to low ${reasonStr}`;
                restContainer.appendChild(div);
            });
        })();

        if (window.validateGrid) window.validateGrid();
    };

    // =========================================================
    // INIȚIALIZARE DROPDOWN-URI
    // =========================================================
    function initDropdowns() {
        const progSel  = document.getElementById('programSelect');
        const sYearSel = document.getElementById('startYear');
        const cYearSel = document.getElementById('coopStartYear');
        const coopCb   = document.getElementById('coopRegistered');
        if (!progSel || !sYearSel || !cYearSel) return;

        let progsToLoad = isGuest ? allProgs : (isGrad ? gradProgs : ugrdProgs);
        if (progsToLoad) {
            progsToLoad.forEach(p => progSel.add(new Option(p, p)));
            if (progsToLoad.includes(detectedProgram)) progSel.value = detectedProgram;
        }

        const dropdownStart = Math.min(minAllowedYear, detectedStartYear);
        for (let i = dropdownStart; i <= currentAcaYearStart + 3; i++) {
            let yStr = `${i}-${i + 1}`;
            sYearSel.add(new Option(yStr, yStr));
            cYearSel.add(new Option(yStr, yStr));
        }
        sYearSel.value = `${detectedStartYear}-${detectedStartYear + 1}`;

        let isActiveCoop = false;
        if (coopTerms && coopTerms.length > 0) {
            cYearSel.value = coopTerms[0].year;
            document.getElementById('coopStartTerm').value = coopTerms[0].season;
            coopTerms.forEach(ct => {
                if (parseInt(ct.year.split('-')[0]) >= currentAcaYearStart) isActiveCoop = true;
            });
        }
        if (coopCb) coopCb.checked = isActiveCoop;

        const hasData = (studentCourses && studentCourses.length > 0) || (coopTerms && coopTerms.length > 0);
        if (hasData && !isGuest) {
            sYearSel.disabled = true;
            cYearSel.disabled = true;
            document.getElementById('coopStartTerm').disabled = true;
        }

        showSpinner('Loading student data…');
        window.rebuildGrid();
        setTimeout(() => { window.validateGrid && window.validateGrid(); }, 0);

        // Gray out Load Sequence button if no sequence data
        const btnLoadSeq = document.getElementById('btnLoadSeq');
        if (btnLoadSeq) {
            const hasSeq = window.APP_CONFIG.sequencesDb && window.APP_CONFIG.sequencesDb.length > 0;
            btnLoadSeq.disabled = !hasSeq;
            if (!hasSeq) { btnLoadSeq.style.opacity = '0.45'; btnLoadSeq.style.cursor = 'not-allowed'; }
        }
    }

    initDropdowns();

    // Check if this is a PENDING load (from sessionStorage flag) — gray out submit, show approve
    if (config.isPowerUser && sessionStorage.getItem('_pendingLoad') === '1') {
        // Don't remove _pendingLoad yet — processApproval needs it
        // Force CO-OP checked — only CO-OP students submit for approval
        const coopCbPending = document.getElementById('coopRegistered');
        if (coopCbPending && !coopCbPending.checked) {
            coopCbPending.checked = true;
            window.rebuildGrid();
        }
        setTimeout(() => {
            // Only disable submit button for power users viewing pending plans
            // Regular students should always be able to submit
            const btnSubmit = document.getElementById('btnSubmitApproval');
            if (btnSubmit && config.isPowerUser) {
                btnSubmit.disabled = true;
                btnSubmit.style.opacity = '0.45';
                btnSubmit.style.cursor = 'not-allowed';
            }
            // Approve/rework buttons are now always visible for power users
        }, 500);
    }

    // Sync header program display when programSelect changes
    const headerProg = document.getElementById('headerProgram');
    if (headerProg) {
        const syncProg = () => {
            const progName = document.getElementById('programSelect')?.value || '';
            const discipline = window.APP_CONFIG?.disciplineDescr || '';
            
            // Display: Program name + discipline description (if available)
            if (discipline) {
                headerProg.textContent = `${progName} — ${discipline}`;
            } else {
                headerProg.textContent = progName;
            }
        };
        syncProg();
        document.getElementById('programSelect')?.addEventListener('change', syncProg);
    }

    // Load pending count for power users
    if (window.APP_CONFIG?.isPowerUser && window.refreshPendingCount) {
        window.refreshPendingCount();
    }

    // Load notes + apply initial loaded plan (if any)
    if (window.loadNotes) window.loadNotes();
    if (window.APP_CONFIG && window.APP_CONFIG.initialPlan) {
        try {
            const ip = window.APP_CONFIG.initialPlan;
            const obj = (typeof ip === 'string') ? JSON.parse(ip) : ip;
            window.applyLoadedPlan(obj);
        }
        catch(e) { console.error('Initial plan parse failed', e); }
    }

    // Hide initial spinner after everything is rendered
    setTimeout(() => hideSpinner(), 0);

    // Mandatory reason highlight: red border on reasonBlock if no radio selected
    function updateReasonHighlight() {
        const block = document.getElementById('reasonBlock');
        const badge = document.getElementById('reasonMandatoryBadge');
        if (!block) return;
        const anyChecked = !!document.querySelector('input[name="submissionReason"]:checked');
        block.style.borderColor = anyChecked ? '#e5e5e5' : '#e74c3c';
        block.style.background  = anyChecked ? '#fafafa'  : '#fdf2f2';
        if (badge) badge.style.display = anyChecked ? 'none' : 'inline';
    }
    document.querySelectorAll('input[name="submissionReason"]').forEach(r =>
        r.addEventListener('change', () => {
            updateReasonHighlight();
            if (window.buildStudentMessage) window.buildStudentMessage();
        })
    );
    updateReasonHighlight();

    // Hide Submit button when CO-OP is unchecked (submit only relevant for CO-OP students)
    function updateSubmitVisibility() {
        const coopCb = document.getElementById('coopRegistered');
        const btn    = document.getElementById('btnSubmitApproval');
        const panel  = document.getElementById('submissionPanel');
        if (!btn) return;
        const isCoopOn = coopCb ? coopCb.checked : false;
        btn.style.display    = isCoopOn ? '' : 'none';
        if (panel) panel.style.display = isCoopOn ? '' : 'none';
    }
    window.updateSubmitVisibility = updateSubmitVisibility;
    const coopCbEl = document.getElementById('coopRegistered');
    if (coopCbEl) coopCbEl.addEventListener('change', updateSubmitVisibility);
    updateSubmitVisibility();

    // Track checkbox state changes and auto-add to public notes
    (function() {
        const coopCb = document.getElementById('coopRegistered');
        const acsdCb = document.getElementById('acsdRegistered');
        
        // Store initial states
        let prevCoopState = coopCb ? coopCb.checked : false;
        let prevAcsdState = acsdCb ? acsdCb.checked : false;
        
        async function logCheckboxChange(checkboxName, isChecked) {
            if (!isChecked) return; // Only log when checked (not unchecked)
            
            // For CO-OP: only log if student is withdrawn (NOT IN CO-OP)
            if (checkboxName === 'CO-OP') {
                const isWithdrawn = window.APP_CONFIG?.isWithdrawn || false;
                if (!isWithdrawn) return; // Don't log if student is in CO-OP program
            }
            
            const now = new Date();
            const pad = n => String(n).padStart(2, '0');
            const dt = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
            const studentName = window.APP_CONFIG?.studentName || window.APP_CONFIG?.viewingSid || 'Student';
            const comment = `[${dt}, ${studentName}]: Checked ${checkboxName}`;
            
            // Prepend to public notes textarea
            const publicNotesEl = document.getElementById('publicNotes');
            if (publicNotesEl) {
                const existing = publicNotesEl.value.trim();
                publicNotesEl.value = existing ? `${comment}\n\n${existing}` : comment;
                
                // Trigger auto-resize
                publicNotesEl.dispatchEvent(new Event('input'));
            }
            
            // Save to database via API
            try {
                await apiJson('/api/comments/append', 'POST', { text: comment });
            } catch (e) {
                console.warn('Could not save checkbox change to public notes:', e);
            }
        }
        
        if (coopCb) {
            coopCb.addEventListener('change', function() {
                const newState = this.checked;
                if (!prevCoopState && newState) {
                    // Changed from unchecked to checked
                    logCheckboxChange('CO-OP', true);
                }
                prevCoopState = newState;
            });
        }
        
        if (acsdCb) {
            acsdCb.addEventListener('change', function() {
                const newState = this.checked;
                if (!prevAcsdState && newState) {
                    // Changed from unchecked to checked
                    logCheckboxChange('ACSD', true);
                }
                prevAcsdState = newState;
            });
        }
    })();

    // Auto-check CO-OP if student has co-op terms in transcript (and no plan loaded yet)
    // BUT: if student is withdrawn, force uncheck and disable
    // SKIP if we just loaded a plan (initialPlan exists OR _justLoadedPlan flag is set)
    if (!window.APP_CONFIG?.initialPlan && !window._justLoadedPlan) {
        const hasCoopTerms = Array.isArray(window.APP_CONFIG?.coopTerms) && window.APP_CONFIG.coopTerms.length > 0;
        const isWithdrawn = window.APP_CONFIG?.isWithdrawn || false;
        
        if (isWithdrawn) {
            // Student is withdrawn - force uncheck CO-OP checkbox
            const coopCb = document.getElementById('coopRegistered');
            if (coopCb) {
                coopCb.checked = false;
                // rebuildGrid will be called by the onchange event
            }
        } else if (hasCoopTerms) {
            const coopCb = document.getElementById('coopRegistered');
            if (coopCb && !coopCb.checked) { 
                coopCb.checked = true; 
                // rebuildGrid will be called by the onchange event
            }
        }
    }

    // Close per-term popover when clicking outside
    document.addEventListener('click', () => {
        const p = document.getElementById('termPopover');
        if (p) p.style.display = 'none';
        window.activePopoverZone = null;
    });

    // =========================================================
    // SORT UNALLOCATED ZONE (alphabetical, WT first)
    // =========================================================
    window.sortUnallocated = function() {
        const zone = document.getElementById('zone_Unallocated');
        if (!zone) return;
        const boxes = Array.from(zone.querySelectorAll('.course-box'));
        boxes.sort((a, b) => {
            const aWt = a.classList.contains('wt') ? 0 : 1;
            const bWt = b.classList.contains('wt') ? 0 : 1;
            if (aWt !== bWt) return aWt - bWt;
            const aId = getBoxDisplayId(a);
            const bId = getBoxDisplayId(b);
            return aId.localeCompare(bId);
        });
        boxes.forEach(b => zone.appendChild(b));
    };

    // =========================================================
    // REPEAT COURSE FUNCTIONALITY
    // =========================================================
    window.populateRepeatDropdown = function() {
        const sel = document.getElementById('repeatCourseSelect');
        if (!sel) return;
        sel.innerHTML = '<option value="">— select course —</option>';

        // Get all placed course IDs (from transcript / taken)
        const takenIds = new Set();
        document.querySelectorAll('.course-box.course-taken').forEach(box => {
            const cid = (box.dataset.displayId || box.dataset.courseId || '').toUpperCase();
            if (cid) takenIds.add(cid);
        });

        // Also add courses that already have _REP versions
        const existingReps = new Set();
        document.querySelectorAll('.course-box').forEach(box => {
            const did = getBoxDisplayId(box);
            if (did && did.endsWith('_REP')) existingReps.add(did);
        });

        Array.from(takenIds).sort().forEach(cid => {
            const repId = cid + '_REP';
            if (existingReps.has(repId)) return; // already has a repeat
            const opt = document.createElement('option');
            opt.value = cid;
            opt.textContent = cid;
            sel.appendChild(opt);
        });
    };

    // Call now that the function exists and grid is built
    window.populateRepeatDropdown();

    window.addRepeatCourse = function() {
        const sel = document.getElementById('repeatCourseSelect');
        if (!sel || !sel.value) { alert('Select a course to repeat.'); return; }
        const origCid = sel.value;
        const repCid = origCid + '_REP';
        const baseCid = origCid.replace(/[AB]$/, '');

        // Lookup original course data
        const dbCourse = lookupCourse(baseCid) || {};
        const credit = parseFloat(dbCourse.CREDIT || dbCourse.CREDVAL || 3);

        // Build prereq: the original course itself
        const repDb = Object.assign({}, dbCourse);
        repDb['PRE-REQUISITE'] = origCid;
        // Keep same co-reqs — but NOT as prereqs
        // This repeat is prereq for everything the original was prereq for (only pre-reqs, not co-reqs)

        const unallocZone = document.getElementById('zone_Unallocated');
        if (!unallocZone) return;

        const div = document.createElement('div');
        div.id = `course_rep_${repCid}`;
        div.className = `course-box border-rep`;
        div.dataset.credit = credit;
        div.dataset.courseId = baseCid;
        div.dataset.displayId = repCid;
        div.dataset.isRepeat = 'true';
        div.draggable = true;
        div.ondragstart = window.drag;

        // Generate HTML with REP label
        let title = dbCourse.TITLE || '';
        let termBadges = getTermsBadges(dbCourse);
        const prereq = origCid;
        const coreq = 'None';
        const isPreFor = (window._isPreReqFor?.[baseCid] || []).join(', ') || 'None';
        const isCoFor = 'None';

        div.innerHTML = `
            <input type="checkbox" class="c-checkbox" onclick="window.toggleCoursePin(this)">
            <div class="c-headline">
                <span class="c-code">${repCid} (${credit}cr)</span>
                <span class="rep-label">REP</span>
                <span class="c-title">${title}</span>
            </div>
            <div class="c-meta">
                <span class="c-type">[REP]</span>
                <div class="c-badges">${termBadges}</div>
            </div>
            <div class="c-reqs">
                <div><b>PRE-req:</b> ${prereq}&nbsp;&nbsp;||&nbsp;&nbsp;<b>CO-req:</b> ${coreq}</div>
                <div><b>is pre for:</b> ${isPreFor}&nbsp;&nbsp;||&nbsp;&nbsp;<b>is co for:</b> ${isCoFor}</div>
            </div>
        `;
        div.onclick = () => window.showCourseInfo(baseCid);

        // Register in coursesData for validation
        coursesData[repCid] = Object.assign({}, dbCourse, {
            COURSE: repCid,
            CORE_TE: 'REP',
            'PRE-REQUISITE': origCid,
            'CO-REQUISITE': '',
            '_isRepeat': true
        });

        // Update reverse lookup: _REP is prereq for everything original was
        const origPreForSet = window._isPreReqFor[baseCid] || [];
        window._isPreReqFor[repCid] = [...origPreForSet];
        // Original is prereq of _REP
        (window._isPreReqFor[baseCid] = window._isPreReqFor[baseCid] || []).push(repCid);

        unallocZone.appendChild(div);
        window.sortUnallocated();
        window.populateRepeatDropdown();
        window.updateCredits();
    };

    // =========================================================
    // RESTRICTIONS CHECK (from CORE_TE.xlsx Restrictions sheet)
    // Columns: Date after which takes effect, Program, COOP selected,
    //          Year, Term, Course, Restriction, WARNING
    // All non-empty conditions are ANDed together.
    // =========================================================
    window.restrictionsDb = config.restrictionsDb || [];

    // Determine selected program family for matching
    function getProgFamily(progName) {
        const p = String(progName || '').toUpperCase();
        if (p.includes('INDUSTRIAL') || p.includes('INDU')) return 'INDU';
        if (p.includes('AERO')) return 'AERO';
        if (p.includes('MECH')) return 'MECH';
        return '';
    }

    window.checkRestrictions = function(zoneId, season, yearStr) {
        // Returns array of { text, isWarning (true=red → goes to error list), isFyi (orange → no error list) }
        const results = [];
        if (!window.restrictionsDb || !window.restrictionsDb.length) return results;

        const zone = document.getElementById(zoneId);
        if (!zone) return results;

        const boxes = Array.from(zone.children).filter(c => c.classList.contains('course-box'));
        const wtBoxes = boxes.filter(b => b.classList.contains('wt'));

        let totalCr = 0;
        boxes.forEach(b => { totalCr += parseFloat(b.dataset.credit || 0); });

        // Collect all course IDs in this term (both base and display)
        const courseIdsInTerm = new Set();
        boxes.forEach(b => {
            const cid = (b.dataset.courseId || '').toUpperCase();
            if (cid) courseIdsInTerm.add(cid);
            const did = (b.dataset.displayId || '').toUpperCase();
            if (did) courseIdsInTerm.add(did);
        });

        const today = new Date();
        today.setHours(0,0,0,0);

        const isCoop = !!document.getElementById('coopRegistered')?.checked;
        const selectedProg = document.getElementById('programSelect')?.value || '';
        const progFamily = getProgFamily(selectedProg);

        // Check CO-OP terms data to see if this term is a planned WT (W-1, W-2, W-3)
        const coopTerms = window.APP_CONFIG?.coopTerms || [];
        const isPlannedWT = coopTerms.some(ct =>
            ct.year === yearStr && ct.season === season && String(ct.type || '').toUpperCase().startsWith('W')
        );

        window.restrictionsDb.forEach(r => {
            let match = true;

            // 1) Date filter: if "Date after which takes effect" is set, only apply if today >= that date
            const dateStr = r['Date after which takes effect'];
            if (dateStr && String(dateStr).trim() && String(dateStr).toLowerCase() !== 'nan' && String(dateStr).toLowerCase() !== 'nat') {
                const effDate = new Date(dateStr);
                if (!isNaN(effDate.getTime()) && today < effDate) match = false;
            }

            // 2) Program filter: if Program column is set, must match current program family
            const rProg = String(r['Program'] || '').trim().toUpperCase();
            if (rProg && rProg !== 'NAN') {
                if (progFamily !== rProg) match = false;
            }

            // 3) COOP selected filter
            const rCoop = String(r['COOP selected'] || '').trim().toUpperCase();
            if (rCoop && rCoop !== 'NAN') {
                if (rCoop === 'YES' && !isCoop) match = false;
                if (rCoop === 'NO' && isCoop) match = false;
            }

            // 3b) Level filter: UGRD or GRAD — skip if doesn't match student level
            const rLevel = String(r['Level'] || r['level'] || '').trim().toUpperCase();
            if (rLevel && rLevel !== 'NAN') {
                const studentIsGrad = !!window.APP_CONFIG?.isGrad;
                if (rLevel === 'UGRD' && studentIsGrad) match = false;
                if (rLevel === 'GRAD' && !studentIsGrad) match = false;
            }

            // 4) Year filter: if set, must match this term's academic year
            const rYear = String(r['Year'] || '').trim();
            if (rYear && rYear.toLowerCase() !== 'nan') {
                if (rYear !== yearStr) match = false;
            }

            // 5) Term/Season filter: if set, must match this term's season
            const rTerm = String(r['Term'] || '').trim();
            if (rTerm && rTerm.toLowerCase() !== 'nan') {
                if (rTerm.toUpperCase() !== season.toUpperCase()) match = false;
            }

            // 6) Course filter: if set, check if that course (or type) is in this term
            const rCourse = String(r['Course'] || '').trim();
            if (rCourse && rCourse.toLowerCase() !== 'nan') {
                const courseNorm = rCourse.replace(/\s/g, '').toUpperCase();
                if (courseNorm === 'WT') {
                    // Special: "WT" means this restriction applies to terms containing WT courses
                    // But if this is already a planned CO-OP WT term (W-1/W-2/W-3), skip
                    if (wtBoxes.length === 0) match = false;
                    if (isPlannedWT) match = false; // already planned as WT, no warning needed
                } else {
                    // Regular course restriction
                    // If Term is specified → course must be in THIS specific term
                    // If Term is NOT specified → this is a global "program must include this course" restriction
                    //    → show it in the term where the course IS placed, or skip per-term display
                    //      (the validateGrid global deduplication will handle showing it once in the issues panel)
                    const hasTerm = rTerm && rTerm.toLowerCase() !== 'nan';
                    if (hasTerm) {
                        // Term-specific: course must be in this term
                        if (!courseIdsInTerm.has(courseNorm)) match = false;
                    } else {
                        // Global: show only in the term where the course actually sits
                        if (!courseIdsInTerm.has(courseNorm)) match = false;
                    }
                }
            }

            if (!match) return;

            const warningCol = String(r['WARNING'] || '').trim().toUpperCase();
            // Default: YES (warning). Only NO/FYI explicitly marks as non-warning.
            const isFyi = warningCol === 'NO' || warningCol === 'FYI';
            const isWarning = !isFyi;
            const text = String(r['Restriction'] || 'Restriction applies');

            results.push({ text, isWarning, isFyi });
        });

        return results;
    };

    // Re-run updateCredits if an initial plan was loaded before checkRestrictions was defined
    if (window.APP_CONFIG?.initialPlan) {
        window.updateCredits();
    }

    // =========================================================
    // CREDIT SUMMARY (before submit)
    // =========================================================
    window.updateCreditSummary = function() {
        const panel = document.getElementById('creditSummaryContent');
        if (!panel) return;

        // compute Y-term label from zone id and start year
        const startYearStr = document.getElementById('startYear')?.value || '';
        const startBase = parseInt(startYearStr.split('-')[0]) || 0;
        function termLabel(zid) {
            const m = zid.match(/zone_(\d{4})-\d{4}_(\w+)/);
            if (!m || !startBase) return '';
            const yn = parseInt(m[1]) - startBase + 1;
            const sn = { Summer: 'SUM', Fall: 'FALL', Winter: 'WIN' }[m[2]] || m[2];
            return `Y${yn}_${sn}`;
        }

        const cats = {};       // cat → total credits
        const catCourses = {}; // cat → [{did, cr, label}]
        let total = 0;

        document.querySelectorAll('.drop-zone .course-box').forEach(box => {
            const zid = box.parentElement?.id;
            if (!zid || zid === 'zone_Unallocated') return;
            if (box.classList.contains('wt')) return;

            const cid = (box.dataset.courseId || '').toUpperCase();
            const did = (box.dataset.displayId || cid).toUpperCase();
            const db = lookupCourse(cid) || {};
            const cr = parseFloat(box.dataset.credit || 0);
            let cat = String(db['CORE_TE'] || '').trim().toUpperCase() || 'OTHER';

            if (cat.includes('ECP')) cat = 'ECP';
            else if (cat.includes('TE') && !cat.includes('CORE')) cat = 'TE';

            cats[cat] = (cats[cat] || 0) + cr;
            total += cr;
            if (!catCourses[cat]) catCourses[cat] = [];
            catCourses[cat].push({ did, cr, label: termLabel(zid) });
        });

        const fmt = v => v % 1 === 0 ? v : v.toFixed(1);
        const ecpCr   = cats['ECP']   || 0;
        const otherCr = cats['OTHER'] || 0;
        const repCr   = cats['REP']   || 0;

        // For GRAD programs: include OTHER in main total (no separate CORE/TE breakdown)
        const _isGradCredits = !!window.APP_CONFIG?.isGrad || (document.getElementById('programSelect')?.value || '').toUpperCase().includes('GRAD');
        const mainTotal = _isGradCredits
            ? total - ecpCr - repCr          // GRAD: OTHER counts in main total
            : total - ecpCr - otherCr - repCr; // UGRD: OTHER excluded from main total

        // Get program requirements from Programs sheet
        const selectedProg = document.getElementById('programSelect')?.value || '';
        const programsReqDb = window.APP_CONFIG?.programsRequirementsDb || [];
        const progReqs = {}; // { 'ENG CORE': 27, 'PRG CORE': 87, 'TE': 6 }
        programsReqDb.forEach(row => {
            if (String(row['Program'] || '').trim() === selectedProg && String(row['Level'] || '').trim() === 'UGRD') {
                const type = String(row['Type of credits'] || '').trim();
                const required = parseFloat(row['no of credits'] || 0);
                if (type && required >= 0) {  // Include even if 0
                    progReqs[type] = required;
                }
            }
        });

        // Combine all categories: from cats AND from progReqs
        const allCats = new Set([...Object.keys(cats), ...Object.keys(progReqs)]);
        let mainCats = Array.from(allCats).filter(k => k !== 'ECP' && k !== 'REP').sort();
        // For UGRD: also exclude OTHER from main breakdown; for GRAD: keep OTHER in breakdown
        if (!_isGradCredits) mainCats = mainCats.filter(k => k !== 'OTHER');

        // Summary line: Xcr CAT1 + Xcr CAT2 ... with required credits and red highlighting
        const parts = mainCats.map(k => {
            const current = cats[k] || 0;
            const required = progReqs[k];
            const isLow = required !== undefined && current < required;
            const color = isLow ? '#c0392b' : '#333';
            
            if (required !== undefined) {
                return `<span style="color:${color};"><span style="font-size:15px; font-weight:bold;">${fmt(current)}</span>/${fmt(required)}cr</span> ${k}`;
            } else {
                return `<span style="font-size:15px; font-weight:bold;">${fmt(current)}</span>cr ${k}`;
            }
        }).filter(p => p);  // Remove empty parts

        const addons = [];
        if (repCr)   addons.push(`<span style="font-size:15px; font-weight:bold;">${fmt(repCr)}</span>cr REP`);
        if (ecpCr)   addons.push(`<span style="font-size:15px; font-weight:bold;">${fmt(ecpCr)}</span>cr ECP`);
        if (otherCr && !_isGradCredits) addons.push(`<span style="font-size:15px; font-weight:bold;">${fmt(otherCr)}</span>cr OTHER`);
        const addonNote = addons.length
            ? ` <span style="color:#888">(in addition to ${addons.join(', ')})</span>` : '';

        // For GRAD: show "Total: Xcr OTHER" if all credits are OTHER
        panel.innerHTML = `<b>Total: <span style="font-size:15px;">${fmt(mainTotal)}</span>cr</b>${parts.length ? ' = ' + parts.join(' + ') : ''}${addonNote}`;

        // Breakdown → separate panel, one course per line (all cats including REP/ECP/OTHER)
        const breakdownPanel = document.getElementById('creditBreakdownContent');
        if (!breakdownPanel) return;
        const allBreakdownCats = Object.keys(cats).sort();
        if (!allBreakdownCats.length) { breakdownPanel.innerHTML = '<span style="color:#aaa">—</span>'; return; }

        let html = '';
        allBreakdownCats.forEach(k => {
            if (!catCourses[k]?.length) return;
            const sorted = catCourses[k].slice().sort((a, b) => a.label.localeCompare(b.label) || a.did.localeCompare(b.did));
            const rows = sorted.map(c =>
                `<div class="cs-course-row"><span class="cs-did">${c.did}</span><span class="cs-cr">(${fmt(c.cr)}cr)</span><span class="cs-label">${c.label}</span></div>`
            ).join('');
            html += `<div class="cs-cat-block"><div class="cs-cat-label">${k}</div>${rows}</div>`;
        });
        breakdownPanel.innerHTML = html;
    };

    // =========================================================
    // STUDENT MESSAGE FORMAT (issues + justification)
    // =========================================================
    window.buildStudentMessage = function() {
        const issues = Array.isArray(window.latestIssues) ? window.latestIssues : [];
        const justText = document.getElementById('justificationText');
        if (!justText) return;

        // Get selected reason code
        const reasonCode = getSelectedReasonCode();
        const reasonLabels = {
            0: "I found an internship on my own (I have one in hand)",
            1: "I have not yet started / I was asked by COOP AD but there are no changes",
            2: "I want to reduce summer load",
            3: "I want to reduce overall load",
            4: "Off sequence (e.g., must repeat course)",
            5: "I couldn't find a place in one/several courses I had scheduled",
            6: "I have / will change academic program (e.g., transfer)",
            7: "I was not placed for the coming work term (did not find an internship)",
            8: "My WT is or will be extended",
            9: "LOW GPA - CO-OP AD requested a CoS",
            10: "Other personal reasons: see my comments"
        };

        if (issues.length === 0 && reasonCode === null) {
            if (justText.value.includes('ERRORS & WARNINGS:') || justText.value.includes('ISSUES & JUSTIFICATIONS:') || justText.value.includes('Submission Reason:')) {
                justText.value = '';
            }
            justText.dataset.originalText = '';
            return;
        }

        // Extract existing justification answers keyed by error text
        const currentText = justText.value;
        const answersMap = {};
        const blocks = currentText.split(/(?=\d+\.\s)/);
        blocks.forEach(block => {
            const m = block.match(/^\d+\.\s*([^\n]+)\n(?:Justification|DETAILS|Details \(optional\)):\s*([\s\S]*)/);
            if (m) answersMap[m[1].trim()] = m[2].trim();
        });

        // Build new interleaved text
        let newContent = '';
        let itemNumber = 1;

        // Add reason code as first item if selected
        if (reasonCode !== null && reasonLabels[reasonCode] !== undefined) {
            const reasonText = `Submission Reason: ${reasonCode}) ${reasonLabels[reasonCode]}`;
            const savedAnswer = answersMap[reasonText] || '';
            const labelText = (reasonCode === 4 || reasonCode === 5 || reasonCode === 6 || reasonCode === 10) ? 'DETAILS' : 'DETAILS (optional)';
            newContent += `${itemNumber}. ${reasonText}\n${labelText}: ${savedAnswer}\n\n`;
            itemNumber++;
        }

        // Add validation issues
        issues.forEach((issue) => {
            const prefix = issue.sev === 'error' ? '[ERROR]' : issue.sev === 'warning' ? '[WARNING]' : '[FYI]';
            const isFyi = issue.msg.startsWith('FYI');
            const errText = issue.courseId ? `${issue.courseId}: ${issue.msg}` : issue.msg;
            if (isFyi) {
                newContent += `${itemNumber}. ${prefix} ${errText}\n\n`;
            } else if (issue.sev === 'warning') {
                const savedAnswer = answersMap[errText] || '';
                newContent += `${itemNumber}. ${prefix} ${errText}\nDetails (optional): ${savedAnswer}\n\n`;
            } else {
                const savedAnswer = answersMap[errText] || '';
                newContent += `${itemNumber}. ${prefix} ${errText}\nJustification: ${savedAnswer}\n\n`;
            }
            itemNumber++;
        });

        justText.value = newContent;
        justText.dataset.originalText = newContent;

        // Autosize
        justText.style.height = 'auto';
        justText.style.height = justText.scrollHeight + 'px';
    };

    // =========================================================
    // DOUBLE-CLICK ON NOTES (admin: prepend timestamp)
    // =========================================================
    if (config.isPowerUser) {
        // Use the logged-in admin's email (from session), not the viewed student's
        const adminEmail = "{{ student_email or '' }}"; // Will be set via APP_CONFIG
        ['publicNotes', 'privateNotes'].forEach(noteId => {
            const el = document.getElementById(noteId);
            if (!el) return;
            el.addEventListener('dblclick', () => {
                const now = new Date();
                const pad = n => String(n).padStart(2, '0');
                const dt = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
                // Use admin's own email from session (config.adminEmail or fallback to logged-in user)
                const myEmail = config.adminEmail || config.studentId || '';
                const prefix = `[${dt}, ${myEmail}]: `;
                const existing = el.value;
                el.value = prefix + '\n' + existing;
                el.setSelectionRange(prefix.length, prefix.length);
                el.focus();
                // Trigger auto-save
                el.dispatchEvent(new Event('input'));
            });
        });
    }

    // =========================================================
    // PENDING LOAD → GRAY OUT SUBMIT
    // =========================================================
    window._pendingLoaded = false;
    const origApplyLoadedPlan = window.applyLoadedPlan;
    // We'll override after definition below

    // Autosize: all textarea elements auto-expand with content
    function autosizeTextarea(el) {
        el.style.height = 'auto';
        el.style.height = el.scrollHeight + 'px';
    }
    window._autosizeAll = function() {
        document.querySelectorAll('textarea').forEach(el => autosizeTextarea(el));
    };
    document.querySelectorAll('textarea').forEach(el => {
        el.addEventListener('input', () => autosizeTextarea(el));
        autosizeTextarea(el);
    });
    
    // Auto-load most recent APPROVED sequence on page load
    // Skip if loading from pending or if user manually loaded a sequence
    setTimeout(async () => {
        console.log('[AUTOLOAD] Starting autoload check...');
        
        if (sessionStorage.getItem('_skipAutoLoad') === '1') {
            console.log('[AUTOLOAD] SKIPPED: _skipAutoLoad flag is set');
            sessionStorage.removeItem('_skipAutoLoad');
            return;
        }
        
        // If page already has initialPlan (loaded via ?load_seq_id=), skip
        if (window.APP_CONFIG?.initialPlan) {
            console.log('[AUTOLOAD] SKIPPED: initialPlan already exists');
            return;
        }
        
        console.log('[AUTOLOAD] Fetching sequence list...');
        try {
            const res = await apiJson('/api/sequence/list');
            console.log('[AUTOLOAD] API response:', res);
            
            if (res.ok && res.auto_load_sequence) {
                const seq = res.auto_load_sequence;
                console.log(`[AUTOLOAD] Found ${seq.type} sequence: ${seq.name} (${seq.id})`);
                
                // Show loading spinner
                showSpinner('Loading sequence...');
                
                const item = await apiJson(`/api/sequence/get/${encodeURIComponent(seq.id)}`);
                console.log('[AUTOLOAD] Received plan data:', item.plan ? 'YES' : 'NO', item.plan ? `(${Object.keys(item.plan).length} keys)` : '');
                
                if (item.plan) {
                    item.plan.reason_code = item.reason_code;
                    item.plan.justification = item.justification;
                    window.applyLoadedPlan(item.plan);
                } else {
                    console.log('[AUTOLOAD] ERROR: No plan data in response');
                }
                
                // Hide spinner
                hideSpinner();
                
                // Show success banner
                const banner = document.createElement('div');
                banner.id = 'debugBanner';
                banner.style.cssText = 'position:fixed;top:10px;left:50%;transform:translateX(-50%);background:#2196F3;color:white;padding:12px 24px;border-radius:6px;z-index:10000;font-weight:bold;box-shadow:0 4px 8px rgba(0,0,0,0.2);';
                banner.textContent = `Sequence loaded: ${seq.name} - ${seq.type.toUpperCase()}`;
                document.body.appendChild(banner);
                
                // Remove banner on first click anywhere
                document.addEventListener('click', () => banner.remove(), { once: true });
            } else {
                console.log('[AUTOLOAD] No auto_load_sequence found in response');
            }
        } catch (e) {
            console.error('[AUTOLOAD] Error:', e);
        }
    }, 1000); // Longer delay to ensure page is fully loaded

    // =========================================================
    // SESSION KEEPALIVE — ping server every 5 min if user is active
    // =========================================================
    let _userActive = false;
    ['mousemove', 'click', 'keydown', 'scroll', 'touchstart'].forEach(evt => {
        document.addEventListener(evt, () => { _userActive = true; }, { passive: true });
    });
    setInterval(async () => {
        if (!_userActive) return;
        _userActive = false;
        try {
            await fetch('/api/keepalive', { method: 'POST', credentials: 'same-origin' });
        } catch (_) { /* ignore */ }
    }, 5 * 60 * 1000); // every 5 minutes
});

// =========================================================
// PANOU INFO CURS
// coursesData e global — va fi populat când userul dă click
// =========================================================
window.showCourseInfo = function(cid) {
    // Info is now shown inline on each course card — click only triggers visual highlighting
    const baseCid = cid.replace(/[AB]$/, '').replace(/\s/g, '').toUpperCase();

    const { light: backLight, dark: backDark } = getBackwardChain(baseCid);
    const { light: fwdLight,  dark: fwdDark  } = getForwardChain(baseCid);

    document.querySelectorAll('.course-box').forEach(b => {
        b.style.boxShadow = '0 1px 2px rgba(0,0,0,0.05)';
        b.style.removeProperty('background-color');
        const bid = (b.dataset.courseId || '').toUpperCase();
        if (bid === baseCid) {
            b.style.boxShadow = '0 0 0 3px #e74c3c';
        } else if (backDark.has(bid)) {
            b.style.boxShadow = '0 0 0 2px #d4a017';
            b.style.setProperty('background-color', '#fef3c0', 'important');
        } else if (backLight.has(bid)) {
            b.style.boxShadow = '0 0 0 2px #f0d060';
            b.style.setProperty('background-color', '#fffde7', 'important');
        } else if (fwdDark.has(bid)) {
            b.style.boxShadow = '0 0 0 2px #1976d2';
            b.style.setProperty('background-color', '#bbdefb', 'important');
        } else if (fwdLight.has(bid)) {
            b.style.boxShadow = '0 0 0 2px #90caf9';
            b.style.setProperty('background-color', '#e3f2fd', 'important');
        }
    });
};

// =========================================================
// API — SAVE SEQUENCE / ADMIN NOTES
// =========================================================
window.saveSequence = async function(statusStr) {
    let payload = {
        target_sid:    window.APP_CONFIG.viewingSid || window.APP_CONFIG.student_id,
        program:       document.getElementById('programSelect').value,
        status:        statusStr,
        justification: document.getElementById('justificationText') ? document.getElementById('justificationText').value : "",
        sequence_data: {}
    };
    document.querySelectorAll('.drop-zone').forEach(z => {
        payload.sequence_data[z.id] = Array.from(z.children).map(c => c.id);
    });
    const route = statusStr === 'DRAFT' ? '/api/save_draft' : '/api/submit_sequence';
    try {
        let res = await fetch(route, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (res.ok) alert(`Sequence saved as ${statusStr}`);
    } catch(e) { console.error(e); }
};

// =========================================================
// ADMIN — SWITCH VIEWING STUDENT (Power Users)
// Server-side authorization: app.py checks session student_id starts with '9'
// =========================================================
// =========================================================
// PENDING APPROVALS DROPDOWN (header button for admins)
// =========================================================
window.openPendingMenu = async function() {
    const dropdown = document.getElementById('pendingMenuDropdown');
    if (!dropdown) return;
    if (dropdown.style.display !== 'none') { dropdown.style.display = 'none'; return; }
    dropdown.innerHTML = '<div style="padding:8px;color:#888;font-size:11px;">Loading…</div>';
    dropdown.style.display = 'block';
    try {
        const res = await apiJson('/api/admin/pending', 'GET');
        const pending = res.pending || [];
        if (!pending.length) {
            dropdown.innerHTML = '<div style="padding:8px;color:#888;font-size:11px;">No pending approvals.</div>';
            return;
        }
        dropdown.innerHTML = pending.slice(0, 25).map(p => {
            const dt = String(p.updated_at || '').substring(0, 16);
            return `<div class="pending-menu-item" onclick="window.openPendingItem('${p.id}','${p.student_id}')">`
                + `<b>${p.student_id}</b>${p.student_name ? ' — ' + p.student_name : ''}<br>`
                + `<span style="color:#888;">${p.name || ''} | ${dt}</span></div>`;
        }).join('');
    } catch(e) {
        dropdown.innerHTML = '<div style="padding:8px;color:#e74c3c;font-size:11px;">Error loading.</div>';
    }
};

window.openPendingItem = async function(seqId, studentId) {
    try {
        const dropdown = document.getElementById('pendingMenuDropdown');
        if (dropdown) dropdown.style.display = 'none';
        await apiJson('/api/admin/view_sid', 'POST', { student_id: studentId });
        sessionStorage.setItem('_pendingLoad', '1');
        sessionStorage.setItem('_skipAutoLoad', '1'); // Disable auto-load when loading from pending
        sessionStorage.setItem('_pendingSeqId', seqId);
        window.location.href = `/planner?load_seq_id=${encodeURIComponent(seqId)}`;
    } catch(e) {
        alert('Error: ' + e.message);
    }
};

// =========================================================
// CANNED COMMENTS (Power User)
// =========================================================
window.insertCannedComment = function(type) {
    const publicNotes = document.getElementById('publicNotes');
    if (!publicNotes) return;
    
    let msg = '';
    if (type === 1) {
        msg = "Due to low academic performance, student cannot go on next scheduled WT; must re-sequence. This places the student on Probation (still with CO-OP, but no work terms; this has no impact on MIAE Program and course registration). Student's status in CO-OP Program will be re-evaluated every term upon academic performance.";
    } else if (type === 2) {
        msg = "Due to low academic performance, apply one of the two: if next term WT is already secured, the one after (next next one) cannot be placed in the subsequent 2 terms, and will be approved pending academic performance improvement. If next term WT is not already secured, it must be re-scheduled at earliest 2 terms later and will be approved pending academic performance improvement. In either case, a change of sequence is requested. This places the student on Probation (still with CO-OP, but no work term; this has no impact on MIAE Program and course registration). Student's status in CO-OP Program will be re-evaluated every term upon academic performance.";
    } else if (type === 3) {
        msg = "\nHello,\n\nI understand this is a difficult situation. As a reminder, the minimum CGPA requirements for undergraduate Engineering and Computer Science co-op programs are outlined here: https://www.concordia.ca/academics/co-op/internships.html (select your program).\n\nUnder normal circumstances, students with a CGPA below the minimum threshold would be withdrawn from the co-op program immediately. However, MIAE Department is willing to offer students a second chance to improve their academic standing, with certain restrictions.\n\nWe cannot authorize a work term until the student has demonstrated the minimum required engineering knowledge, which is directly measured by your GPA (at least 0.2 above the withdrawal threshold). Additionally, there is a procedural constraint: final grades are typically posted after the search term begins, and we cannot authorize a search term before student's improved grades are available. The above explains why we had to postpone your internship by 2 terms.\n\nOnce your grades are posted and your CGPA shows significant improvement, we will remove the restriction and you can proceed with your work term.\n\nI am confident this is a temporary setback, and that your performance next term will demonstrate the progress needed to move forward.\n\nBest regards,";
    } else if (type === 4) {
        msg = "Please provide an updated CoS ASAP.\n\nYou must reschedule your sequence or you will be withdrawn from the CO-OP program.\n\nThank you for your quick action.";
    }
    
    // Format: [date time, email]: message\n\nold text
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    const dt = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
    const email = window.APP_CONFIG?.adminEmail || '';
    
    const existing = String(publicNotes.value || '').trim();
    const newComment = `[${dt}, ${email}]: ${msg}${existing ? '\n\n' + existing : ''}`;
    
    publicNotes.value = newComment;
    
    // Trigger auto-resize
    publicNotes.dispatchEvent(new Event('input'));
    
    // Auto-save
    if (window.autoSaveAdminNotes) {
        window.autoSaveAdminNotes(newComment, document.getElementById('privateNotes')?.value || '');
    }
};

// =========================================================
// SEND EMAIL TO STUDENT (Power User)
// =========================================================
window.sendEmailToStudent = function() {
    const studentName = window.APP_CONFIG?.studentName || '';
    const studentId = window.APP_CONFIG?.viewingSid || '';
    const studentEmail = window.APP_CONFIG?.studentEmail || `${studentId}@mail.concordia.ca`;
    const adminEmail = window.APP_CONFIG?.adminEmail || '';
    const publicNotes = document.getElementById('publicNotes')?.value || '';
    const program = document.getElementById('programSelect')?.value || '';
    
    if (!publicNotes.trim()) {
        alert('No message to send. Please add a message in the Public Notes field.');
        return;
    }
    
    // Check if student is GRAD
    const isGrad = program && program.toUpperCase().includes('GRAD');
    
    // Determine coordinator email based on GRAD status
    let ccList;
    if (isGrad) {
        // GRAD students: Nadia + Charlene
        ccList = ['coop_miae@concordia.ca', 'nadia.mazzaferro@concordia.ca', 'charlene.wald@concordia.ca'];
    } else {
        // UGRD students: Sabrina + coordinator (Fred/Nathalie based on INDU and SID)
        let coordEmail = 'frederick.francis@concordia.ca';
        if (program && program.toUpperCase().includes('INDU')) {
            try {
                const lastDigit = parseInt(String(studentId).slice(-1));
                if (lastDigit >= 5 && lastDigit <= 9) {
                    coordEmail = 'nathalie.steverman@concordia.ca';
                }
            } catch (e) {
                console.warn('Could not determine coordinator from student ID');
            }
        }
        ccList = ['coop_miae@concordia.ca', 'sabrina.poirier@concordia.ca', coordEmail];
    }
    
    // Check if Institute Operations should be included
    const includeInst = document.getElementById('includeInstituteOps')?.checked || false;
    const headerMsg = includeInst 
        ? "⚠️ WT IMPACTED - Operations Institute are cc-ed\n\n" 
        : "";
    
    // Add Institute Operations to CC if checkbox is checked
    if (includeInst) {
        ccList.push('instituteoperations@concordia.ca');
    }
    ccList = [...new Set(ccList)]; // Remove duplicates
    
    // Build email content
    const subject = `MIAE CO-OP AD message for ${studentName}, ${studentId}`;
    const body = `${headerMsg}Hello ${studentName},\n\nPlease see the message below:\n\n${publicNotes}\n\nPS: Please use REPLY TO ALL\n\nRegards,\n${adminEmail}`;
    
    // Show custom dialog with email preview
    const confirmed = confirm(`Send email to:\n\nTo: ${studentEmail}\nCC: ${ccList.join(', ')}\n\nSubject: ${subject}\n\nMessage:\n${body}\n\nPress OK to send, or Cancel to abort.`);
    
    if (confirmed) {
        // Send email via backend API
        showSpinner('Sending email...');
        fetch('/api/admin/send_student_email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                student_id: studentId,
                student_name: studentName,
                student_email: studentEmail,
                program: program,
                message: publicNotes,
                include_institute: includeInst,
                cc_list: ccList
            })
        })
        .then(res => res.json())
        .then(data => {
            hideSpinner();
            if (data.ok) {
                alert('✅ Email sent successfully!');
            } else {
                alert(`❌ Failed to send email: ${data.error}`);
            }
        })
        .catch(err => {
            hideSpinner();
            console.error('Email send error:', err);
            alert(`❌ Failed to send email: ${err.message}`);
        });
    }
};

// =========================================================
// APPROVE / REWORK (Power User action)
// =========================================================
window.processApproval = async function(action) {
    if (!window.APP_CONFIG?.isPowerUser) { alert('Unauthorized'); return; }
    if (window._approvalInProgress) return; // prevent double-click
    window._approvalInProgress = true; // lock immediately before any confirm dialogs

    const viewingSid = window.APP_CONFIG.viewingSid;
    const seqId2 = sessionStorage.getItem('_pendingSeqId') || (window.APP_CONFIG.initialPlanId ? String(window.APP_CONFIG.initialPlanId).replace(/"/g,'') : '');
    if (!seqId2) {
        const proceed = confirm('No sequence loaded to approve.\n\nPress OK to proceed anyway, or Cancel to abort.');
        if (!proceed) { window._approvalInProgress = false; return; }
    }

    const conf = confirm(`Are you sure you want to ${action} this sequence for ${viewingSid}?`);
    if (!conf) { window._approvalInProgress = false; return; }

    // Client-side reason_code validation (mandatory for both APPROVED and REWORK)
    const reasonCode = getSelectedReasonCode();
    if (reasonCode === null) {
        window._approvalInProgress = false;
        alert('Submission reason not selected. Please select a reason before proceeding.');
        return;
    }
    showSpinner(`${action === 'APPROVED' ? 'Approving' : 'Sending rework'}…`);
    // Disable buttons to prevent any further clicks
    const btnApprove = document.getElementById('btnApprove');
    const btnRework = document.getElementById('btnRework');
    if (btnApprove) btnApprove.disabled = true;
    if (btnRework) btnRework.disabled = true;

    const termSummary = buildEmailTermSummary();

    // Build WT summary
    const plannedWt = getPlannedWtMap();
    const actualWt  = getActualWtMap();
    const wtSummary = {};

    ['WT1', 'WT2', 'WT3'].forEach(wt => {
        const planned = plannedWt[wt] || null;
        const actual  = actualWt[wt] || null;

        let changeText = '';
        let newTerm = actual ? actual.term : (planned ? planned.term : '');

        if (planned && actual) {
            if (planned.term !== actual.term) {
                changeText = `CHANGED from ${planned.type} (${planned.term}) to ${actual.term}`;
            }
        } else if (planned && !actual) {
            changeText = `MISSING from planner (expected ${planned.type} in ${planned.term})`;
            newTerm = planned.term;
        } else if (!planned && actual) {
            changeText = `ADDED in ${actual.term} (no original W-x match)`;
        }

        if (planned || actual) {
            wtSummary[wt] = {
                old_term: planned ? planned.term : '',
                new_term: newTerm,
                change_text: changeText
            };
        }
    });

    const valErrors = (window.latestIssues || []).filter(i => i.sev === 'error').map(i => `${i.courseId || ''}: ${i.msg}`);

    // ── Build course deviations for DB (only on APPROVED) ──
    let courseDeviations = [];
    if (action === 'APPROVED') {
        const sequencesDb = window.APP_CONFIG?.sequencesDb || [];
        const progSel2 = document.getElementById('programSelect');
        const progKey2 = progSel2 ? getProgramKey(progSel2.value) : null;
        const sYearStr2 = document.getElementById('startYear')?.value || '';
        const baseYear2 = sYearStr2 ? parseInt(sYearStr2.split('-')[0]) : 0;

        // Standard sequence map: courseId → { stdZoneId, stdLabel, stdOrd }
        const stdMap2 = {};
        if (sequencesDb.length && progKey2 && baseYear2) {
            sequencesDb.filter(s => s.PROGRAM_KEY === progKey2).forEach(entry => {
                const cid = String(entry.COURSE).replace(/\s/g, '').toUpperCase();
                const pos = String(entry.POSITION).trim();
                const zid = positionToZoneId(pos, baseYear2);
                if (!zid) return;
                const ord = getTermOrdFromZoneId(zid);
                const parts = zid.replace('zone_', '').split('_');
                stdMap2[cid] = { stdZoneId: zid, stdOrd: ord, stdLabel: parts.join(' ') };
            });
        }

        // Helper: format course number for DB — "AAAA 123" or "AAAA 1234"
        function fmtCourseForDb(rawId) {
            const n = rawId.replace(/\s/g, '').toUpperCase();
            // Match: 2-5 letters + 3-4 digits + optional suffix
            const m = n.match(/^([A-Z]{2,5})(\d{3,4})([A-Z]?)$/);
            if (!m) return null;
            return `${m[1]} ${m[2]}${m[3]}`;
        }

        // Helper: zone id → "YYYY-YYYY Season"
        function zoneToTermLabel(zid) {
            if (!zid) return '';
            const parts = zid.replace('zone_', '').split('_');
            return parts.join(' ');
        }

        // Iterate all future grid zones (after current term)
        document.querySelectorAll('.drop-zone').forEach(zone => {
            if (zone.id === 'zone_Y0' || zone.id === 'zone_Unallocated') return;
            if (isAutoPlaceBlocked(zone)) return;

            const actualOrd = getTermOrdFromZoneId(zone.id);
            const actualLabel = zoneToTermLabel(zone.id);

            Array.from(zone.children).forEach(box => {
                if (!box.classList.contains('course-box')) return;
                if (box.classList.contains('course-taken')) return;

                const cid = (box.dataset.courseId || '').toUpperCase();
                const displayId = (box.dataset.displayId || cid).toUpperCase();

                // WT courses: include WT1, WT2, WT3
                if (box.classList.contains('wt')) {
                    const wtMatch = displayId.match(/^WT(\d)$/);
                    if (wtMatch) {
                        const wtName = `WT${wtMatch[1]}`;
                        const std = stdMap2[wtName];
                        const origLabel = std ? std.stdLabel : '';
                        const origOrd = std ? std.stdOrd : actualOrd;
                        const delta = actualOrd - origOrd;
                        courseDeviations.push({
                            course: wtName,
                            original_term: origLabel,
                            new_term: actualLabel,
                            delta: delta
                        });
                    }
                    return;
                }

                const db = lookupCourse(cid) || {};
                const coreType = String(db['CORE_TE'] || '').toUpperCase();

                // Skip TE (pure electives)
                if (coreType.includes('TE') && !coreType.includes('CORE')) return;

                // Skip ENGR W-courses (work-term related ENGR courses like ENGR391, ENGR392 etc.)
                if (/^ENGR\d/.test(cid) && cid.match(/ENGR[234]\d{2}/)) {
                    // Only skip if it looks like a work-placement course (W-prefix in title or similar)
                    const title = String(db['TITLE'] || '').toUpperCase();
                    if (title.includes('WORK') || title.includes('CO-OP') || title.includes('COOP')) return;
                }

                // 490A → store as "DEPT 490", skip 490B entirely
                let courseForDb;
                if (/490B$/.test(displayId)) return; // skip 490B
                if (/490A$/.test(displayId)) {
                    // Store as "DEPT 490" (without A suffix)
                    const prefix = displayId.replace(/490A$/, '');
                    courseForDb = `${prefix} 490`;
                } else {
                    courseForDb = fmtCourseForDb(displayId);
                }

                if (!courseForDb) return;

                // Look up standard sequence position
                const std = stdMap2[displayId] || stdMap2[cid] || stdMap2[cid.replace(/[AB]$/, '')];
                const origLabel = std ? std.stdLabel : '';
                const origOrd = std ? std.stdOrd : actualOrd;
                const delta = actualOrd - origOrd;

                courseDeviations.push({
                    course: courseForDb,
                    original_term: origLabel,
                    new_term: actualLabel,
                    delta: delta
                });
            });
        });
    }

    try {
        const payload = {
            status: action,
            student_id: viewingSid,
            timestamp: seqId2,
            public_comments: document.getElementById('publicNotes')?.value || '',
            private_comments: document.getElementById('privateNotes')?.value || '',
            student_name: window.APP_CONFIG.studentName || viewingSid,
            program: document.getElementById('programSelect')?.value || '',
            wt_summary: wtSummary,
            term_summary: termSummary,
            justification: document.getElementById('justificationText')?.value || '',
            validation_errors: valErrors,
            course_deviations: courseDeviations,
            reason_code: reasonCode,
            plan: collectPlanSnapshot()  // Include plan data for approve handler
        };
        
        // Auto-prepend approval/rework comment to public notes
        try {
            const now = new Date();
            const pad = n => String(n).padStart(2, '0');
            const dt = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
            const email = window.APP_CONFIG?.adminEmail || window.APP_CONFIG?.studentId || '';
            const actionLabel = action === 'APPROVED' ? 'Sequence APPROVED' : 'Sequence REWORK';
            const existing = String(document.getElementById('publicNotes')?.value || '').trim();
            const newComment = `[${dt}, ${email}]: ${actionLabel}${existing ? '\n\n' + existing : ''}`;
            await apiJson('/api/comments/append', 'POST', { text: newComment });
            const pubEl = document.getElementById('publicNotes');
            if (pubEl) pubEl.value = newComment;
            // Update payload with the new public_comments
            payload.public_comments = newComment;
        } catch (ne) {
            console.warn('Could not append approval comment to public notes:', ne.message);
        }
        
        const res = await apiJson('/api/admin/approve', 'POST', payload);
        if (res.ok) {
            hideSpinner();
            alert(`${action} successfully.`);
            sessionStorage.removeItem('_pendingLoad');
            sessionStorage.removeItem('_pendingSeqId');
            // Reset to admin's own view and reload
            try { await apiJson('/api/admin/reset_view', 'POST'); } catch(_) {}
            window.location.href = '/planner';
        } else {
            hideSpinner();
            alert(`Failed: ${res.error || 'Unknown error'}`);
        }
    } catch (e) {
        hideSpinner();
        console.error(e);
        alert(`Error: ${e.message}`);
    } finally {
        window._approvalInProgress = false;
        const btnApprove = document.getElementById('btnApprove');
        const btnRework = document.getElementById('btnRework');
        if (btnApprove) btnApprove.disabled = false;
        if (btnRework) btnRework.disabled = false;
    }
};

window.refreshPendingCount = async function() {
    try {
        const badge = document.getElementById('pendingBadge');
        const res = await apiJson('/api/admin/pending', 'GET');
        const n = (res.pending || []).length;
        if (badge) badge.textContent = n > 0 ? ` (${n})` : '';
    } catch(e) { /* silent */ }
};

// Close pending dropdown when clicking outside
document.addEventListener('click', (e) => {
    const btn = document.getElementById('btnPendingHeader');
    const dd  = document.getElementById('pendingMenuDropdown');
    if (dd && btn && !btn.contains(e.target)) dd.style.display = 'none';
});

// =========================================================
// ADMIN STUDENT SEARCH AUTOCOMPLETE
// =========================================================
let searchTimeout = null;
let currentSearchResults = [];

window.setupAdminSearchAutocomplete = function() {
    const input = document.getElementById('adminSidInput');
    const dropdown = document.getElementById('adminSearchDropdown');
    
    if (!input || !dropdown) return;
    
    // Enter key triggers Switch button
    input.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            window.adminSwitchStudent();
        }
    });
    
    // Search as user types (with debouncing)
    input.addEventListener('input', function() {
        const query = this.value.trim();
        
        // Clear previous timeout
        if (searchTimeout) clearTimeout(searchTimeout);
        
        // Hide dropdown if less than 4 characters
        if (query.length < 4) {
            dropdown.style.display = 'none';
            currentSearchResults = [];
            return;
        }
        
        // Debounce: wait 300ms after user stops typing
        searchTimeout = setTimeout(async () => {
            try {
                const res = await fetch(`/api/admin/search_students?q=${encodeURIComponent(query)}`);
                const data = await res.json();
                
                if (data.ok && data.results && data.results.length > 0) {
                    currentSearchResults = data.results;
                    renderSearchDropdown(data.results);
                } else {
                    dropdown.style.display = 'none';
                    currentSearchResults = [];
                }
            } catch (e) {
                console.error('Search error:', e);
                dropdown.style.display = 'none';
            }
        }, 300);
    });
    
    // Handle keyboard navigation
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            dropdown.style.display = 'none';
        }
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    });
};

function renderSearchDropdown(results) {
    const dropdown = document.getElementById('adminSearchDropdown');
    if (!dropdown) return;
    
    dropdown.innerHTML = '';
    
    results.forEach(student => {
        const item = document.createElement('div');
        item.style.cssText = 'padding:10px; cursor:pointer; border-bottom:1px solid #e0e0e0; transition:background 0.2s;';
        item.innerHTML = `
            <div style="font-weight:bold; font-size:13px; color:#2c3e50;">${escapeHtml(student.name)}</div>
            <div style="font-size:11px; color:#7f8c8d; margin-top:2px;">ID: ${escapeHtml(student.id)} • ${escapeHtml(student.email)}</div>
        `;
        
        item.addEventListener('mouseenter', function() {
            this.style.background = '#f0f0f0';
        });
        
        item.addEventListener('mouseleave', function() {
            this.style.background = '#fff';
        });
        
        item.addEventListener('click', function() {
            selectStudent(student);
        });
        
        dropdown.appendChild(item);
    });
    
    dropdown.style.display = 'block';
}

function selectStudent(student) {
    const input = document.getElementById('adminSidInput');
    const dropdown = document.getElementById('adminSearchDropdown');
    
    if (input) {
        input.value = student.id;
    }
    
    if (dropdown) {
        dropdown.style.display = 'none';
    }
    
    // Automatically switch to the selected student
    window.adminSwitchStudent();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize autocomplete when page loads
document.addEventListener('DOMContentLoaded', function() {
    if (window.APP_CONFIG && window.APP_CONFIG.isPowerUser) {
        window.setupAdminSearchAutocomplete();
    }
});

window.adminSwitchStudent = async function() {
    try {
        const inp = document.getElementById('adminSidInput');
        const targetSid = (inp ? inp.value : '').trim();
        if (!targetSid) {
            alert('Enter a Student ID.');
            return;
        }

        showSpinner('Loading student…');
        const res = await fetch('/admin_change_sid', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_sid: targetSid })
        });
        if (res.ok) {
            window.location.reload();
        } else {
            hideSpinner();
            const txt = await res.text();
            console.error('admin_change_sid failed:', txt);
            alert('Error switching student ID.');
        }
    } catch (e) {
        console.error(e);
        alert('Connection error.');
    }
};

window.adminResetView = async function() {
    try {
        if (!window.APP_CONFIG || !window.APP_CONFIG.isPowerUser) {
            alert('Unauthorized');
            return;
        }
        const selfSid = String(window.APP_CONFIG.studentId || '').trim();
        if (!selfSid) {
            alert('Missing your own SID in APP_CONFIG.');
            return;
        }
        showSpinner('Resetting view…');
        const res = await fetch('/admin_change_sid', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_sid: selfSid })
        });
        if (res.ok) {
            window.location.reload();
        } else {
            hideSpinner();
            const txt = await res.text();
            console.error('admin_change_sid reset failed:', txt);
            alert('Error resetting view.');
        }
    } catch (e) {
        console.error(e);
        alert('Connection error.');
    }
};

// =========================================================
// CONTROL PANEL — set global limits
// =========================================================
window.setGlobalMaxCourses = function(n) {
    window.globalMaxCourses = n;
    document.querySelectorAll('#cpCoursesBtns button').forEach(b =>
        b.classList.toggle('cp-active', parseInt(b.dataset.val) === n));
    window.updateCredits();
};

window.setGlobalMaxCr = function(n) {
    window.globalMaxCr = n;
    document.querySelectorAll('#cpCreditsBtns button').forEach(b =>
        b.classList.toggle('cp-active', parseInt(b.dataset.val) === n));
    window.updateCredits();
};

// =========================================================
// PER-TERM POPOVER
// =========================================================
window.openTermPopover = function(zoneId, el) {
    const popover = document.getElementById('termPopover');
    if (!popover) return;

    // Toggle: click same zone again to close
    if (window.activePopoverZone === zoneId && popover.style.display !== 'none') {
        popover.style.display = 'none';
        window.activePopoverZone = null;
        return;
    }
    window.activePopoverZone = zoneId;

    const ov = window.termOverrides[zoneId] || {};

    // Title: readable zone name
    const readableId = zoneId.replace('zone_', '').replace(/_/g, ' ');
    document.getElementById('tp_title').innerText = readableId;

    // Build max-credits buttons: fixed range 0,3,6,...,21
    const crBtns = document.getElementById('tp_cr_btns');
    crBtns.innerHTML = '';
    [0, 3, 6, 9, 12, 15, 18, 21].forEach(v => {
        const btn = document.createElement('button');
        btn.innerText   = v;
        btn.dataset.val = v;
        if (ov.cr === v) btn.classList.add('tp-active');
        btn.onclick = (e) => {
            e.stopPropagation();
            window.termOverrides[zoneId] = window.termOverrides[zoneId] || {};
            window.termOverrides[zoneId].cr = v;
            crBtns.querySelectorAll('button').forEach(b =>
                b.classList.toggle('tp-active', parseInt(b.dataset.val) === v));
            window.updateCredits();
        };
        crBtns.appendChild(btn);
    });

    // Build max-courses buttons: fixed range 0-6
    const cntBtns = document.getElementById('tp_cnt_btns');
    cntBtns.innerHTML = '';
    [0, 1, 2, 3, 4, 5, 6].forEach(v => {
        const btn = document.createElement('button');
        btn.innerText   = v;
        btn.dataset.val = v;
        if (ov.cnt === v) btn.classList.add('tp-active');
        btn.onclick = (e) => {
            e.stopPropagation();
            window.termOverrides[zoneId] = window.termOverrides[zoneId] || {};
            window.termOverrides[zoneId].cnt = v;
            cntBtns.querySelectorAll('button').forEach(b =>
                b.classList.toggle('tp-active', parseInt(b.dataset.val) === v));
            window.updateCredits();
        };
        cntBtns.appendChild(btn);
    });

    // Position directly below the clicked element (position:fixed — no scroll offset)
    const rect = el.getBoundingClientRect();
    popover.style.top  = `${rect.bottom + 4}px`;
    popover.style.left = `${Math.max(4, rect.left - 60)}px`;
    popover.style.display = 'block';
};

window.clearTermOverride = function() {
    if (window.activePopoverZone) {
        delete window.termOverrides[window.activePopoverZone];
        window.updateCredits();
        document.getElementById('termPopover').style.display = 'none';
        window.activePopoverZone = null;
    }
};

// =========================================================
// STANDARD SEQUENCE LOADER
// =========================================================
function getProgramKey(progName) {
    const p = String(progName).toUpperCase();
    if (p.includes('INDUSTRIAL')) return 'INDUSTRIAL';
    if (p.includes('MECHANICAL') || p.includes('MECH')) return 'MECHANICAL';
    if (p.includes('AERO')) {
        if (p.includes('AVIONICS') || p.includes(' C:') || p.includes(' C ')) return 'AERO_C';
        if (p.includes('STRUCTURE') || p.includes(' B:') || p.includes(' B ')) return 'AERO_B';
        return 'AERO_A';
    }
    return null;
}

function positionToZoneId(position, baseYear) {
    // position format: Y1_FALL, Y2_SUM, Y3_WIN
    const m = String(position).match(/^Y(\d+)_(FALL|SUM|WIN)$/i);
    if (!m) return null;
    const yNum = parseInt(m[1]);
    const seasonMap = { SUM: 'Summer', FALL: 'Fall', WIN: 'Winter' };
    const season = seasonMap[m[2].toUpperCase()];
    if (!season) return null;
    const acaStart = baseYear + yNum - 1;
    return `zone_${acaStart}-${acaStart + 1}_${season}`;
}

window.loadStandardSequence = function() {
    const sequencesDb = window.APP_CONFIG.sequencesDb;
    if (!sequencesDb || sequencesDb.length === 0) {
        alert('No sequence data available.');
        return;
    }

    const progSel = document.getElementById('programSelect');
    if (!progSel || !progSel.value) {
        alert('Please select a program first.');
        return;
    }

    const progKey = getProgramKey(progSel.value);
    if (!progKey) {
        alert('No standard sequence found for this program.');
        return;
    }

    const sYearStr = document.getElementById('startYear').value;
    const baseYear = parseInt(sYearStr.split('-')[0]);

    const seqEntries = sequencesDb.filter(s => s.PROGRAM_KEY === progKey);

    // Only check if course has been taken (skip taken courses)
    let placed = 0;
    seqEntries.forEach(entry => {
        const courseId = String(entry.COURSE).replace(/\s/g, '').toUpperCase();
        const position = String(entry.POSITION).trim();

        // Look for the course in the Unallocated zone only (meaning not taken and not already placed)
        const baseCid = courseId.replace(/[AB]$/, '');
        const unallocEl =
            document.querySelector(`#zone_Unallocated [data-display-id="${courseId}"]`) ||
            document.querySelector(`#zone_Unallocated [data-course-id="${courseId}"]`) ||
            document.querySelector(`#zone_Unallocated [data-course-id="${baseCid}"]`);
        if (!unallocEl) return;

        const targetZoneId = positionToZoneId(position, baseYear);
        if (!targetZoneId) return;

        const targetZone = document.getElementById(targetZoneId);
        if (!targetZone || isAutoPlaceBlocked(targetZone)) return; // never place in past/current

        targetZone.appendChild(unallocEl);
        placed++;
    });

    window.updateCredits();
    if (placed > 0) alert(`Placed ${placed} courses per standard sequence.`);
    else alert('No unallocated courses to place (all may already be in the grid or target terms are in the past).');
};

// =========================================================
// CLEAR TO UNALLOCATED (move all non-taken non-pinned future courses back)
// =========================================================
window.clearToUnallocated = function() {
    const unallocZone = document.getElementById('zone_Unallocated');
    if (!unallocZone) return;
    document.querySelectorAll('.drop-zone').forEach(zone => {
        if (zone.id === 'zone_Unallocated' || zone.id === 'zone_Y0') return;
        if (isAutoPlaceBlocked(zone)) return;
        Array.from(zone.children).forEach(child => {
            if (child.classList.contains('course-box') &&
                !child.classList.contains('course-taken') &&
                child.dataset.pinned !== 'true') {
                unallocZone.appendChild(child);
            }
        });
    });
    if (window.sortUnallocated) window.sortUnallocated();
    window.updateCredits();
};

// =========================================================
// CEGEP BUTTON — place all ECP unallocated courses into Y0 and pin them
// =========================================================
window.placeCegepInY0 = function() {
    const y0 = document.getElementById('zone_Y0');
    const unalloc = document.getElementById('zone_Unallocated');
    if (!y0 || !unalloc) return;

    let moved = 0;
    Array.from(unalloc.querySelectorAll('.course-box')).forEach(box => {
        const base = (box.dataset.courseId || '').toUpperCase();
        const db = lookupCourse(base) || {};
        const t = String(db['CORE_TE'] || '').toUpperCase();
        if (!t.includes('ECP')) return;
        y0.appendChild(box);
        box.dataset.pinned = 'true';
        box.classList.add('pinned');
        const cb = box.querySelector('.c-checkbox');
        if (cb && !cb.disabled) cb.checked = true;
        moved++;
    });
    window.updateCredits();
    if (moved === 0) alert('No ECP courses found in Unallocated.');
};

// =========================================================
// AUTO PLACE (priority + backtracking search)
// - prioritizes courses with long prerequisite/corequisite chains and high fan-out
// - places courses as early as possible within offered terms & limits
// - backtracks when stuck (trial & error) and returns best partial placement found
// =========================================================
// =========================================================
// AUTO PLACE LEGACY (sequence-based + relocation loop)
// =========================================================
window.autoPlaceLegacy = function() {
    const unallocZone = document.getElementById('zone_Unallocated');
    if (!unallocZone) return;
    showSpinner('Auto-placing courses…');
    setTimeout(() => { window._autoPlaceLegacyImpl(); }, 0);
};
window._autoPlaceLegacyImpl = function() {
    const unallocZone = document.getElementById('zone_Unallocated');
    if (!unallocZone) { hideSpinner(); return; }

    const sequencesDb = window.APP_CONFIG.sequencesDb;
    const progSel     = document.getElementById('programSelect');
    const progKey     = progSel ? getProgramKey(progSel.value) : null;

    // Step 1: clear all non-taken non-pinned from future zones → Unallocated
    document.querySelectorAll('.drop-zone').forEach(zone => {
        if (zone.id === 'zone_Unallocated' || zone.id === 'zone_Y0') return;
        if (isAutoPlaceBlocked(zone)) return;
        Array.from(zone.children).forEach(child => {
            if (child.classList.contains('course-box') &&
                !child.classList.contains('course-taken') &&
                !child.classList.contains('wt') &&
                child.dataset.pinned !== 'true') {
                unallocZone.appendChild(child);
            }
        });
    });

    if (!sequencesDb || !sequencesDb.length || !progKey) {
        window.updateCredits();
        return;
    }

    // Step 2: place in sequence order respecting limits
    const sYearStr   = document.getElementById('startYear').value;
    const baseYear   = parseInt(sYearStr.split('-')[0]);
    const seqEntries = sequencesDb.filter(s => s.PROGRAM_KEY === progKey);

    function getZoneLimits(zone) {
        const isSummer  = zone.dataset.isSummer === 'true';
        const hardMaxCr = parseFloat(zone.dataset.hardMaxCr || (isSummer ? 16 : 18));
        const ov        = window.termOverrides[zone.id] || {};
        return {
            maxCr:  ov.cr  !== undefined ? ov.cr  : Math.min(window.globalMaxCr, hardMaxCr),
            maxCnt: ov.cnt !== undefined ? ov.cnt : (isSummer ? Math.max(1, window.globalMaxCourses - 1) : window.globalMaxCourses)
        };
    }

    function getZoneUsage(zone) {
        let curCnt = 0, curCr = 0;
        Array.from(zone.children).forEach(c => {
            if (c.classList.contains('course-box')) { curCnt++; curCr += parseFloat(c.dataset.credit || 0); }
        });
        return { curCnt, curCr };
    }

    function tryPlace(el, zone) {
        const { maxCr, maxCnt } = getZoneLimits(zone);
        const { curCnt, curCr } = getZoneUsage(zone);
        const thisCr = parseFloat(el.dataset.credit || 0);
        if (curCnt >= maxCnt) return false;
        if (curCr + thisCr > maxCr + 0.01) return false;
        zone.appendChild(el);
        return true;
    }

    let placed = 0;
    seqEntries.forEach(entry => {
        const courseId = String(entry.COURSE).replace(/\s/g, '').toUpperCase();
        const position = String(entry.POSITION).trim();
        const baseCid  = courseId.replace(/[AB]$/, '');
        const unallocEl =
            document.querySelector(`#zone_Unallocated [data-course-id="${courseId}"]`) ||
            document.querySelector(`#zone_Unallocated [data-course-id="${baseCid}"]`);
        if (!unallocEl) return;
        if (unallocEl.classList.contains('wt')) return; // skip WT — must be placed manually
        // Skip OTHER (unknown) and TE
        const _db = lookupCourse(baseCid);
        if (!_db || _db._unknown) return;
        const _t = String(_db['CORE_TE'] || '').toUpperCase();
        if (_t.includes('TE') && !_t.includes('CORE')) return;
        const targetZoneId = positionToZoneId(position, baseYear);
        if (!targetZoneId) return;
        const targetZone = document.getElementById(targetZoneId);
        if (!targetZone || isAutoPlaceBlocked(targetZone)) return;
        if (tryPlace(unallocEl, targetZone)) placed++;
    });

    // Step 3: Smart relocation loop — fix hard errors (offering + pre-req order)
    // Build sorted list of all future non-past zones
    const allFutureZones = [];
    document.querySelectorAll('.drop-zone').forEach(z => {
        if (z.id === 'zone_Unallocated' || z.id === 'zone_Y0') return;
        if (isAutoPlaceBlocked(z)) return;
        allFutureZones.push({ id: z.id, ord: getTermOrdFromZoneId(z.id), el: z });
    });
    allFutureZones.sort((a, b) => a.ord - b.ord);

    for (let iter = 0; iter < 3; iter++) {
        // Build placement snapshot
        const snap = {};
        document.querySelectorAll('.drop-zone .course-box').forEach(box => {
            const cid = (box.dataset.courseId || '').toUpperCase();
            if (!cid || !box.parentElement) return;
            snap[cid] = { zoneId: box.parentElement.id, termOrd: getTermOrdFromZoneId(box.parentElement.id), el: box };
        });

        let moved = 0;
        // For each course in a future zone with a hard error, try to find a better zone
        allFutureZones.forEach(({ el: zoneEl, ord: zOrd }) => {
            const season = zoneEl.id.split('_').pop();
            Array.from(zoneEl.children).forEach(box => {
                if (!box.classList.contains('course-box')) return;
                if (box.classList.contains('course-taken')) return;
                if (box.dataset.pinned === 'true') return;

                const cid = (box.dataset.courseId || '').toUpperCase();
                const db  = lookupCourse(cid) || {};
                let hasHardError = false;

                // Hard error 1: not offered this season
                const hasAnyX = ['SUM 1', 'SUM 2', 'FALL', 'WIN'].some(k => String(db[k] || '').toUpperCase() === 'X');
                if (hasAnyX && !box.classList.contains('wt')) {
                    let offered = false;
                    if (season === 'Summer') offered = ['SUM 1', 'SUM 2'].some(k => String(db[k] || '').toUpperCase() === 'X');
                    if (season === 'Fall')   offered = String(db['FALL'] || '').toUpperCase() === 'X';
                    if (season === 'Winter') offered = String(db['WIN']  || '').toUpperCase() === 'X';
                    if (!offered) hasHardError = true;
                }

                // Hard error 2: pre-req not in earlier term
                if (!hasHardError) {
                    const prereqStr = String(db['PRE-REQUISITE'] || '');
                    prereqStr.split(/[;,]/).forEach(seg => {
                        const opts = parseCourseIds(seg).filter(id => snap[id]);
                        if (!opts.length) return;
                        if (!opts.some(id => snap[id].termOrd < zOrd)) hasHardError = true;
                    });
                }

                if (!hasHardError) return;

                // Calculate min ordinal after which this course can be placed (all pre-reqs placed before)
                let minAfterOrd = 0;
                const prereqStr = String(db['PRE-REQUISITE'] || '');
                prereqStr.split(/[;,]/).forEach(seg => {
                    const opts = parseCourseIds(seg).filter(id => snap[id]);
                    if (!opts.length) return;
                    const bestOrd = Math.min(...opts.map(id => snap[id].termOrd));
                    minAfterOrd = Math.max(minAfterOrd, bestOrd);
                });

                // Try each future zone in order
                for (const { id: tzId, ord: tzOrd, el: tzEl } of allFutureZones) {
                    if (tzOrd <= minAfterOrd) continue; // must be strictly after all pre-reqs
                    if (tzEl === zoneEl) continue;      // don't try same zone
                    const tzSeason = tzId.split('_').pop();

                    // Check offering in target season
                    if (hasAnyX && !box.classList.contains('wt')) {
                        let tzOffered = false;
                        if (tzSeason === 'Summer') tzOffered = ['SUM 1', 'SUM 2'].some(k => String(db[k] || '').toUpperCase() === 'X');
                        if (tzSeason === 'Fall')   tzOffered = String(db['FALL'] || '').toUpperCase() === 'X';
                        if (tzSeason === 'Winter') tzOffered = String(db['WIN']  || '').toUpperCase() === 'X';
                        if (!tzOffered) continue;
                    }

                    if (tryPlace(box, tzEl)) { moved++; break; }
                }
            });
        });

        if (moved === 0) break;
    }

    window.updateCredits(); // also calls validateGrid

    const wtUnplaced = document.querySelectorAll('#zone_Unallocated .course-box.wt').length;
    let msg = placed > 0 ? `Auto-placed ${placed} courses.` : 'No regular courses could be placed — all terms may be full or past.';
    if (wtUnplaced > 0) msg += `\n\n⚠ ${wtUnplaced} Work Term(s) were not auto-placed. Please drag them to your desired term(s) manually.`;
    hideSpinner();
    alert(msg);
};


window.autoPlace = function() {
    const unallocZone = document.getElementById('zone_Unallocated');
    if (!unallocZone) return;
    showSpinner('Auto-placing courses (graph search)…');
    setTimeout(() => { window._autoPlaceImpl(); }, 0);
};
window._autoPlaceImpl = function() {
    const unallocZone = document.getElementById('zone_Unallocated');
    if (!unallocZone) { hideSpinner(); return; }

    // ─── 0) Reset: move all non-taken, non-pinned, non-past courses back to Unallocated ───
    document.querySelectorAll('.drop-zone').forEach(zone => {
        if (zone.id === 'zone_Unallocated' || zone.id === 'zone_Y0') return;
        if (isAutoPlaceBlocked(zone)) return;
        Array.from(zone.children).forEach(child => {
            if (!child.classList.contains('course-box')) return;
            if (child.classList.contains('course-taken')) return;
            if (child.dataset.pinned === 'true') return;
            unallocZone.appendChild(child);
        });
    });

    // ─── 1) Build list of future zones (chronological) ───
    const zones = [];
    document.querySelectorAll('.drop-zone').forEach(z => {
        if (z.id === 'zone_Unallocated' || z.id === 'zone_Y0') return;
        if (isAutoPlaceBlocked(z)) return;
        zones.push({ id: z.id, ord: getTermOrdFromZoneId(z.id), el: z, season: z.id.split('_').pop() });
    });
    zones.sort((a, b) => a.ord - b.ord);

    if (!zones.length) {
        window.updateCredits();
        alert('No future terms available to auto-place into.');
        return;
    }

    // ─── 2) Zone capacity helpers ───
    function getZoneLimits(zoneEl) {
        const isSummer  = zoneEl.dataset.isSummer === 'true';
        const hardMaxCr = parseFloat(zoneEl.dataset.hardMaxCr || (isSummer ? 16 : 18));
        const ov        = window.termOverrides[zoneEl.id] || {};
        return {
            maxCr:  ov.cr  !== undefined ? ov.cr  : Math.min(window.globalMaxCr, hardMaxCr),
            maxCnt: ov.cnt !== undefined ? ov.cnt : (isSummer ? Math.max(1, window.globalMaxCourses - 1) : window.globalMaxCourses)
        };
    }

    // ─── 3) Fixed assignments (taken + pinned + WT already on grid) ───
    const fixedMap = new Map(); // displayId -> { zid, ord }
    document.querySelectorAll('.drop-zone').forEach(zone => {
        if (zone.id === 'zone_Unallocated') return;
        Array.from(zone.children).forEach(box => {
            if (!box.classList.contains('course-box')) return;
            if (box.classList.contains('course-taken') || box.dataset.pinned === 'true' || box.classList.contains('wt')) {
                const did = getBoxDisplayId(box);
                fixedMap.set(did, { zid: zone.id, ord: getTermOrdFromZoneId(zone.id) });
            }
        });
    });

    // ─── 4) Courses to place: CORE/PRG/ECP always, TE up to program limit, exclude OTHER ───
    // Get TE credit limit from program requirements
    const _selectedProgAP = document.getElementById('programSelect')?.value || '';
    const _progReqDbAP = window.APP_CONFIG?.programsRequirementsDb || [];
    let _teMaxCrAP = 0;
    _progReqDbAP.forEach(row => {
        if (String(row['Program'] || '').trim() === _selectedProgAP && String(row['Level'] || '').trim() === 'UGRD') {
            if (String(row['Type of credits'] || '').trim().toUpperCase() === 'TE') {
                _teMaxCrAP = parseFloat(row['no of credits'] || 0);
            }
        }
    });

    // Count TE credits already placed on grid (not in unallocated)
    let _teCrAlreadyPlaced = 0;
    document.querySelectorAll('.drop-zone .course-box').forEach(box => {
        if (box.parentElement && box.parentElement.id === 'zone_Unallocated') return;
        if (box.classList.contains('wt')) return;
        const db = lookupCourse((box.dataset.courseId || '').toUpperCase()) || {};
        const t = String(db['CORE_TE'] || '').toUpperCase();
        if (t === 'TE' || (t.includes('TE') && !t.includes('CORE') && !t.includes('PRG') && !t.includes('ECP'))) {
            _teCrAlreadyPlaced += parseFloat(box.dataset.credit || 0);
        }
    });

    let _teCrBudget = Math.max(0, _teMaxCrAP - _teCrAlreadyPlaced);

    const boxesToPlace = Array.from(unallocZone.querySelectorAll('.course-box'))
        .filter(b => !b.classList.contains('course-taken'))
        .filter(b => !b.classList.contains('wt'))
        .filter(b => b.dataset.pinned !== 'true')
        .filter(b => {
            const cid = (b.dataset.courseId || '').toUpperCase();
            const db = lookupCourse(cid);
            if (!db || db._unknown) return false;
            const t = String(db['CORE_TE'] || '').toUpperCase();
            // Exclude OTHER
            if (t === 'OTHER') return false;
            // CORE, PRG, ECP → always include
            if (t.includes('CORE') || t.includes('PRG') || t.includes('ECP')) return true;
            // TE → include only if within budget
            if (t.includes('TE')) {
                const cr = parseFloat(b.dataset.credit || 0);
                if (_teCrBudget >= cr) {
                    _teCrBudget -= cr;
                    return true;
                }
                return false;
            }
            // Anything else (REP etc.) → include
            return true;
        });

    if (!boxesToPlace.length) {
        window.updateCredits();
        alert('Nothing to auto-place (all courses are already placed or pinned).');
        return;
    }

    const byDisplayId = new Map(boxesToPlace.map(b => [getBoxDisplayId(b), b]));
    const allCourseIds = new Set([...fixedMap.keys(), ...boxesToPlace.map(getBoxDisplayId)]);

    // ─── 5) Build prereq DAG among placeable courses ───
    function getReqSegments(dbField) {
        return String(dbField || '').split(/[;,]/).map(s => s.trim()).filter(Boolean);
    }
    function resolveCandidates(reqId) {
        const r = normDisplayId(reqId);
        const out = [];
        if (allCourseIds.has(r)) out.push(r);
        const base = r.replace(/[AB]$/, '');
        if (out.length === 0) {
            allCourseIds.forEach(id => { if (id.replace(/[AB]$/, '') === base) out.push(id); });
        }
        if (/490$/.test(base)) {
            out.sort((a, b) => {
                const aW = a.endsWith('490A') ? 0 : a.endsWith('490B') ? 1 : 2;
                const bW = b.endsWith('490A') ? 0 : b.endsWith('490B') ? 1 : 2;
                return aW - bW || a.localeCompare(b);
            });
        }
        return [...new Set(out)];
    }

    // Forward edges: prereq → Set(dependent)
    const fwdEdges = new Map();
    // Backward edges: course → Set(its prereqs) — only among placeable courses
    const bwdEdges = new Map();

    boxesToPlace.forEach(b => {
        const did = getBoxDisplayId(b);
        if (!fwdEdges.has(did)) fwdEdges.set(did, new Set());
        if (!bwdEdges.has(did)) bwdEdges.set(did, new Set());
    });

    boxesToPlace.forEach(box => {
        const did = getBoxDisplayId(box);
        const base = (box.dataset.courseId || '').toUpperCase();
        const db = lookupCourse(base) || {};
        getReqSegments(db['PRE-REQUISITE']).forEach(seg => {
            const ids = parseReqIdsPreserve(seg).flatMap(resolveCandidates);
            ids.forEach(pid => {
                if (byDisplayId.has(pid) && pid !== did) {
                    if (!fwdEdges.has(pid)) fwdEdges.set(pid, new Set());
                    fwdEdges.get(pid).add(did);
                    bwdEdges.get(did).add(pid);
                }
            });
        });
    });

    // ─── 6) Compute longest backward chain and forward chain for each course ───
    const backLenMemo = new Map();
    function backLen(id, seen = new Set()) {
        if (backLenMemo.has(id)) return backLenMemo.get(id);
        if (seen.has(id)) return 0;
        seen.add(id);
        let mx = 0;
        (bwdEdges.get(id) || new Set()).forEach(pred => {
            if (byDisplayId.has(pred)) {
                const l = 1 + backLen(pred, new Set(seen));
                if (l > mx) mx = l;
            }
        });
        // Also count prereqs that are already fixed (taken/pinned) — each adds 0 but allows chain to start
        backLenMemo.set(id, mx);
        return mx;
    }

    const fwdLenMemo = new Map();
    function fwdLen(id, seen = new Set()) {
        if (fwdLenMemo.has(id)) return fwdLenMemo.get(id);
        if (seen.has(id)) return 0;
        seen.add(id);
        let mx = 0;
        (fwdEdges.get(id) || new Set()).forEach(succ => {
            if (byDisplayId.has(succ)) {
                const l = 1 + fwdLen(succ, new Set(seen));
                if (l > mx) mx = l;
            }
        });
        fwdLenMemo.set(id, mx);
        return mx;
    }

    // Compute chain lengths
    const chainInfo = new Map();
    boxesToPlace.forEach(b => {
        const id = getBoxDisplayId(b);
        chainInfo.set(id, { back: backLen(id), fwd: fwdLen(id) });
    });

    // ─── 7) Standard sequence lookup (for scoring) ───
    const sequencesDb = window.APP_CONFIG.sequencesDb || [];
    const progSel     = document.getElementById('programSelect');
    const progKey     = progSel ? getProgramKey(progSel.value) : null;
    const sYearStr    = document.getElementById('startYear').value;
    const baseYear    = parseInt(sYearStr.split('-')[0]);

    // Map: courseId -> standard zone ord
    const stdOrdMap = new Map();
    if (sequencesDb.length && progKey) {
        sequencesDb.filter(s => s.PROGRAM_KEY === progKey).forEach(entry => {
            const cid = String(entry.COURSE).replace(/\s/g, '').toUpperCase();
            const pos = String(entry.POSITION).trim();
            const zid = positionToZoneId(pos, baseYear);
            if (zid) stdOrdMap.set(cid, getTermOrdFromZoneId(zid));
        });
    }

    // ─── 8) Offering check ───
    function isOfferedInSeason(db, season) {
        const hasAnyX = ['SUM 1','SUM 2','FALL','WIN'].some(k => String(db[k] || '').toUpperCase() === 'X');
        if (!hasAnyX) return true;
        if (season === 'Summer') return ['SUM 1','SUM 2'].some(k => String(db[k] || '').toUpperCase() === 'X');
        if (season === 'Fall')   return String(db['FALL'] || '').toUpperCase() === 'X';
        if (season === 'Winter') return String(db['WIN']  || '').toUpperCase() === 'X';
        return true;
    }

    // Build candidate zones per course
    function getCandidateZones(id) {
        const box = byDisplayId.get(id);
        if (!box) return [];
        const base = (box.dataset.courseId || '').toUpperCase();
        const db = lookupCourse(base) || {};
        const is490A = /490A$/.test(id);
        const is490B = /490B$/.test(id);
        const list = [];
        zones.forEach(z => {
            if (is490A && z.season !== 'Fall') return;
            if (is490B && z.season !== 'Winter') return;
            if (!isOfferedInSeason(db, z.season)) return;
            list.push({ zid: z.id, ord: z.ord, season: z.season });
        });
        return list;
    }

    // ─── 9) State-based solver with backtracking (operates on pure data, not DOM) ───
    // State: assignment map courseId -> zid, zone usage map

    function buildInitialZoneUsage() {
        const usage = {};
        zones.forEach(z => {
            const lim = getZoneLimits(z.el);
            usage[z.id] = { curCr: 0, curCnt: 0, hasWT: false, wtCnt: 0, regularCnt: 0, lim };
            // Count fixed boxes in this zone
            Array.from(z.el.children).forEach(box => {
                if (!box.classList.contains('course-box')) return;
                const cr = parseFloat(box.dataset.credit || 0);
                usage[z.id].curCr += cr;
                usage[z.id].curCnt += 1;
                if (box.classList.contains('wt')) {
                    usage[z.id].hasWT = true;
                    usage[z.id].wtCnt += 1;
                } else {
                    usage[z.id].regularCnt += 1;
                }
            });
        });
        return usage;
    }

    function cloneUsage(u) {
        const c = {};
        for (const k in u) {
            c[k] = { ...u[k], lim: { ...u[k].lim } };
        }
        return c;
    }

    function canFitState(id, zid, usage) {
        const st = usage[zid];
        if (!st) return false;
        const box = byDisplayId.get(id);
        const cr = parseFloat(box.dataset.credit || 0);
        const courseId = (box.dataset.courseId || '').toUpperCase();
        const is490 = /490[AB]?$/.test(courseId);
        
        // Restriction: 490 courses cannot be in the same term as WT
        if (is490 && st.hasWT) return false;
        
        if (st.hasWT && !box.classList.contains('wt')) {
            if (st.regularCnt >= 1) return false;
        }
        if (st.curCnt + 1 > st.lim.maxCnt) return false;
        if (st.curCr + cr > st.lim.maxCr + 0.01) return false;
        return true;
    }

    function applyState(id, zid, usage) {
        const st = usage[zid];
        const box = byDisplayId.get(id);
        const cr = parseFloat(box.dataset.credit || 0);
        st.curCr += cr;
        st.curCnt += 1;
        if (box.classList.contains('wt')) {
            st.hasWT = true;
            st.wtCnt += 1;
        } else {
            st.regularCnt += 1;
        }
    }

    function prereqsSatisfied(courseId, targetOrd, assignment) {
        const box = byDisplayId.get(courseId);
        if (!box) return false;
        const base = (box.dataset.courseId || '').toUpperCase();
        const db = lookupCourse(base) || {};

        // Check prereqs: each segment needs at least one candidate placed strictly before targetOrd
        const preSegs = getReqSegments(db['PRE-REQUISITE']);
        for (const seg of preSegs) {
            const ids = parseReqIdsPreserve(seg).flatMap(resolveCandidates);
            if (!ids.length) continue;
            const ok = ids.some(pid => {
                // Check fixed
                const f = fixedMap.get(pid);
                if (f && f.ord < targetOrd) return true;
                // Check assignment
                const azid = assignment.get(pid);
                if (azid) {
                    const aord = getTermOrdFromZoneId(azid);
                    return aord < targetOrd;
                }
                return false;
            });
            if (!ok) return false;
        }

        // Check coreqs: same or earlier
        const coSegs = getReqSegments(db['CO-REQUISITE']);
        for (const seg of coSegs) {
            const ids = parseReqIdsPreserve(seg).flatMap(resolveCandidates);
            if (!ids.length) continue;
            const ok = ids.some(cid => {
                const f = fixedMap.get(cid);
                if (f && f.ord <= targetOrd) return true;
                const azid = assignment.get(cid);
                if (azid) return getTermOrdFromZoneId(azid) <= targetOrd;
                // Not yet placed: allow if it has candidate zones <= targetOrd
                const cands = getCandidateZones(cid);
                return cands.some(z => z.ord <= targetOrd);
            });
            if (!ok) return false;
        }

        // 490A/B linkage
        if (/490B$/.test(courseId)) {
            const aId = courseId.replace(/B$/, 'A');
            const aZid = assignment.get(aId) || fixedMap.get(aId)?.zid;
            if (aZid) {
                const aYear = aZid.match(/zone_(\d{4})-/)?.[1];
                if (aYear) {
                    const bZone = zones.find(z => z.ord === targetOrd);
                    const bYear = bZone?.id?.match(/zone_(\d{4})-/)?.[1];
                    const aSeason = aZid.split('_').pop();
                    const bSeason = bZone?.season;
                    if (!(bYear && aYear === bYear && aSeason === 'Fall' && bSeason === 'Winter')) return false;
                }
            }
        }
        return true;
    }

    // ─── 10) Score a configuration ───
    // Pure data score (no DOM needed) — distance + unplaced penalties
    function scoreConfigBase(assignment) {
        let distScore = 0;
        let unplacedCore = 0;
        let unplacedEcp  = 0;

        boxesToPlace.forEach(b => {
            const id = getBoxDisplayId(b);
            const base = (b.dataset.courseId || '').toUpperCase();
            const db = lookupCourse(base) || {};
            const t = String(db['CORE_TE'] || '').toUpperCase();
            const isEcp = t.includes('ECP');

            if (!assignment.has(id)) {
                if (isEcp) unplacedEcp++;
                else unplacedCore++;
                return;
            }

            // Distance from standard sequence (only for non-ECP)
            if (!isEcp && stdOrdMap.has(id)) {
                const placedOrd = getTermOrdFromZoneId(assignment.get(id));
                const stdOrd = stdOrdMap.get(id);
                distScore += Math.abs(placedOrd - stdOrd);
            }
        });

        // Penalty: unplaced courses are very expensive (100 per core, 50 per ECP)
        return distScore + unplacedCore * 100 + unplacedEcp * 50;
    }

    // Set of displayIds placed by the solver (to distinguish from taken/pinned/WT)
    const solverPlacedIds = new Set();

    // Full score: apply assignment to DOM → run validateGrid → count course-level errors
    // on solver-placed boxes only → restore DOM. Returns { score, validationErrors }.
    function scoreConfigWithValidation(assignment) {
        const baseScore = scoreConfigBase(assignment);

        // ── Temporarily apply assignment to DOM ──
        // Remember where each solver-placed box currently is (should be Unallocated)
        const savedParents = new Map();
        solverPlacedIds.clear();

        assignment.forEach((zid, cid) => {
            const box = byDisplayId.get(cid);
            if (!box) return;
            solverPlacedIds.add(cid);
            savedParents.set(cid, box.parentElement);
            const zoneEl = document.getElementById(zid);
            if (zoneEl) zoneEl.appendChild(box);
        });

        // ── Run validateGrid silently ──
        // validateGrid writes error badges onto course-box elements and populates
        // the issues panel. We call it, then inspect the boxes.
        if (window.validateGrid) window.validateGrid();

        // ── Collect errors ONLY on solver-placed boxes ──
        let validationErrorCount = 0;
        const validationErrors = [];

        assignment.forEach((_zid, cid) => {
            const box = byDisplayId.get(cid);
            if (!box) return;
            // Check if validateGrid marked this box with an error
            // validateGrid adds class 'cv-error' for error-severity issues
            // and appends a div.cv-error-line with the message
            if (box.classList.contains('cv-error')) {
                validationErrorCount++;
                const errLine = box.querySelector('.cv-error-line');
                if (errLine) {
                    validationErrors.push(`${cid}: ${errLine.innerText.replace(/^▶\s*/, '')}`);
                }
            }
        });

        // ── Restore DOM: move boxes back to their original parents ──
        savedParents.forEach((parent, cid) => {
            const box = byDisplayId.get(cid);
            if (box && parent) parent.appendChild(box);
        });

        // Clear validation badges that validateGrid added (clean slate for next attempt)
        boxesToPlace.forEach(b => {
            b.classList.remove('cv-warning', 'cv-error');
            const el = b.querySelector('.cv-error-line');
            if (el) el.remove();
        });

        // Each validation error on a solver-placed course adds a heavy penalty (200 per error)
        const totalScore = baseScore + validationErrorCount * 200;
        return { score: totalScore, validationErrors, validationErrorCount };
    }

    // ─── 11) Sort courses: highest backLen first (deepest prereq chain) ───
    const sortedByBack = [...boxesToPlace].map(b => getBoxDisplayId(b))
        .sort((a, b) => {
            const ba = chainInfo.get(a), bb = chainInfo.get(b);
            // Primary: backLen desc
            if (bb.back !== ba.back) return bb.back - ba.back;
            // Secondary: total chain (back + fwd) desc
            return (bb.back + bb.fwd) - (ba.back + ba.fwd);
        });

    // ─── 12) Recursive chain placer with backtracking ───
    // We limit total iterations to avoid hanging on large course sets
    const MAX_ITERATIONS = 50000;
    let iterations = 0;
    let bestAssignment = null;
    let bestScore = Infinity;

    // Get all prereqs of a course that still need placement (not fixed, not yet in assignment)
    function getUnplacedPrereqs(id, assignment) {
        return [...(bwdEdges.get(id) || [])].filter(pid =>
            byDisplayId.has(pid) && !assignment.has(pid) && !fixedMap.has(pid)
        );
    }

    // Get all direct dependents (courses that list id as prereq) still needing placement
    function getUnplacedDependents(id, assignment) {
        return [...(fwdEdges.get(id) || [])].filter(did =>
            byDisplayId.has(did) && !assignment.has(did) && !fixedMap.has(did)
        );
    }

    // Try to place a course and then recursively place its prereq chain backward,
    // then proceed forward to dependents. Returns true if we found a complete placement for the sub-chain.
    function placeChainBackward(id, assignment, usage, maxOrd) {
        if (iterations >= MAX_ITERATIONS) return;
        if (assignment.has(id)) return; // already placed

        // Find candidate zones for this course, filtered by maxOrd
        const cands = getCandidateZones(id).filter(z => z.ord <= maxOrd);

        // Try standard sequence position first if it fits
        const stdOrd = stdOrdMap.get(id);
        if (stdOrd !== undefined) {
            cands.sort((a, b) => {
                const da = Math.abs(a.ord - stdOrd);
                const db2 = Math.abs(b.ord - stdOrd);
                return da - db2;
            });
        }

        for (const cand of cands) {
            iterations++;
            if (iterations >= MAX_ITERATIONS) return;

            if (!canFitState(id, cand.zid, usage)) continue;
            if (!prereqsSatisfied(id, cand.ord, assignment)) {
                // Prereqs not yet placed — try to place them first (backward)
                const unplacedPre = getUnplacedPrereqs(id, assignment);
                if (unplacedPre.length > 0) {
                    const savedAssignment = new Map(assignment);
                    const savedUsage = cloneUsage(usage);
                    let allPreOk = true;

                    for (const pid of unplacedPre) {
                        placeChainBackward(pid, assignment, usage, cand.ord - 1);
                        if (!assignment.has(pid)) { allPreOk = false; break; }
                    }

                    if (allPreOk && prereqsSatisfied(id, cand.ord, assignment)) {
                        // prereqs were placed, now place this course
                        if (canFitState(id, cand.zid, usage)) {
                            assignment.set(id, cand.zid);
                            applyState(id, cand.zid, usage);
                            return; // success
                        }
                    }

                    // Backtrack prereq placements if this path didn't work
                    // Restore state
                    for (const [k, v] of savedAssignment) assignment.set(k, v);
                    for (const k of [...assignment.keys()]) {
                        if (!savedAssignment.has(k)) assignment.delete(k);
                    }
                    Object.assign(usage, cloneUsage(savedUsage));
                    // Try next candidate zone
                    continue;
                }
                continue; // prereqs can't be placed
            }

            // Prereqs satisfied, place this course
            assignment.set(id, cand.zid);
            applyState(id, cand.zid, usage);
            return; // success
        }
    }

    // ─── 13) Main solve: iterate through root courses (sorted by backLen desc) ───
    // Try placing the deepest-chain course first, then its prereqs backward,
    // then move to next unplaced course. Try shifting root if not all placed.

    function solve() {
        const assignment = new Map();
        const usage = buildInitialZoneUsage();
        iterations = 0;

        // Process courses in chain-depth order
        for (const rootId of sortedByBack) {
            if (assignment.has(rootId)) continue;
            if (iterations >= MAX_ITERATIONS) break;

            // Try to place this course (with backward chain resolution)
            const maxOrd = zones[zones.length - 1].ord;
            placeChainBackward(rootId, assignment, usage, maxOrd);
        }

        // Now try to place any remaining courses greedily (forward pass)
        const remaining = sortedByBack.filter(id => !assignment.has(id));
        remaining.sort((a, b) => {
            const ca = chainInfo.get(a), cb = chainInfo.get(b);
            return (cb.back + cb.fwd) - (ca.back + ca.fwd);
        });

        for (const id of remaining) {
            if (assignment.has(id)) continue;
            const cands = getCandidateZones(id);
            for (const cand of cands) {
                if (!canFitState(id, cand.zid, usage)) continue;
                if (!prereqsSatisfied(id, cand.ord, assignment)) continue;
                assignment.set(id, cand.zid);
                applyState(id, cand.zid, usage);
                break;
            }
        }

        return assignment;
    }

    // Run solver multiple times with different root orderings for diversity
    function solveMulti() {
        let bestValErrors = [];
        let bestValCount  = 0;

        function tryAttempt(label) {
            iterations = 0;
            const assignment = solve();
            const result = scoreConfigWithValidation(assignment);
            if (result.score < bestScore) {
                bestScore       = result.score;
                bestAssignment  = new Map(assignment);
                bestValErrors   = result.validationErrors;
                bestValCount    = result.validationErrorCount;
            }
        }

        // Attempt 1: default order (deepest backLen first)
        tryAttempt('backLen-desc');

        // Attempt 2: deepest total chain first (back+fwd)
        sortedByBack.sort((a, b) => {
            const ca = chainInfo.get(a), cb = chainInfo.get(b);
            return (cb.back + cb.fwd) - (ca.back + ca.fwd);
        });
        tryAttempt('totalChain-desc');

        // Attempt 3: deepest fwdLen first
        sortedByBack.sort((a, b) => {
            const ca = chainInfo.get(a), cb = chainInfo.get(b);
            if (cb.fwd !== ca.fwd) return cb.fwd - ca.fwd;
            return cb.back - ca.back;
        });
        tryAttempt('fwdLen-desc');

        // Attempt 4: standard sequence order (courses that appear earliest in std seq first)
        if (stdOrdMap.size > 0) {
            sortedByBack.sort((a, b) => {
                const sa = stdOrdMap.get(a) || 9999;
                const sb = stdOrdMap.get(b) || 9999;
                if (sa !== sb) return sa - sb;
                const ca = chainInfo.get(a), cb = chainInfo.get(b);
                return (cb.back + cb.fwd) - (ca.back + ca.fwd);
            });
            tryAttempt('stdSeq-order');
        }

        // If best still has validation errors, try more aggressive strategies:
        // shift problematic courses to later slots by penalizing their current zones
        if (bestValCount > 0 && bestAssignment) {
            // Attempt 5: remove errored courses from assignment and re-solve remaining
            const cleanAssignment = new Map(bestAssignment);
            bestValErrors.forEach(errStr => {
                const cid = errStr.split(':')[0].trim();
                if (cleanAssignment.has(cid)) cleanAssignment.delete(cid);
            });

            // Try re-placing the removed courses in later positions
            const removedIds = [];
            bestValErrors.forEach(errStr => {
                const cid = errStr.split(':')[0].trim();
                if (byDisplayId.has(cid)) removedIds.push(cid);
            });

            if (removedIds.length > 0) {
                // Rebuild usage from cleanAssignment
                const usage = buildInitialZoneUsage();
                cleanAssignment.forEach((zid, cid) => {
                    applyState(cid, zid, usage);
                });

                // Try placing removed courses in later slots
                removedIds.forEach(cid => {
                    const cands = getCandidateZones(cid);
                    for (const cand of cands) {
                        if (!canFitState(cid, cand.zid, usage)) continue;
                        if (!prereqsSatisfied(cid, cand.ord, cleanAssignment)) continue;
                        cleanAssignment.set(cid, cand.zid);
                        applyState(cid, cand.zid, usage);
                        break;
                    }
                });

                const result = scoreConfigWithValidation(cleanAssignment);
                if (result.score < bestScore) {
                    bestScore      = result.score;
                    bestAssignment = new Map(cleanAssignment);
                    bestValErrors  = result.validationErrors;
                    bestValCount   = result.validationErrorCount;
                }
            }
        }
    }

    solveMulti();

    // ─── 14) Apply best assignment to DOM ───
    const finalAssignment = bestAssignment || new Map();

    finalAssignment.forEach((zid, cid) => {
        const box = byDisplayId.get(cid);
        const zoneEl = document.getElementById(zid);
        if (box && zoneEl) zoneEl.appendChild(box);
    });

    window.updateCredits();

    const placedN     = finalAssignment.size;
    const totalN      = boxesToPlace.length;
    const unplacedN   = totalN - placedN;
    const wtUnplacedN = document.querySelectorAll('#zone_Unallocated .course-box.wt').length;

    let msg = `Auto-place (graph search): placed ${placedN}/${totalN} courses.`;
    if (bestScore < Infinity) msg += `\nScore: ${bestScore} (lower = closer to standard sequence, 0 validation errors = ideal).`;
    if (unplacedN > 0) msg += `\n\n⚠ ${unplacedN} course(s) remain in Unallocated (no valid slot found — terms may be full or prereqs unresolved).`;
    if (wtUnplacedN > 0) msg += `\n\n⚠ ${wtUnplacedN} Work Term(s) not auto-placed — drag them manually.`;
    hideSpinner();
    alert(msg);
};

// =========================================================
// LIVE VALIDATION (runs after every grid change)
// =========================================================
function getTermOrdFromZoneId(zid) {
    if (!zid || zid === 'zone_Y0') return -1;
    const m = zid.match(/zone_(\d{4})-\d{4}_(Summer|Fall|Winter)/);
    if (!m) return -1;
    const year = parseInt(m[1]);
    const season = m[2];
    
    // Proper chronological order within academic year:
    // Summer (1) → Fall (2) → Winter (3)
    // Each academic year gets 3 slots: year*3 + season_offset
    const seasonOrd = { Summer: 1, Fall: 2, Winter: 3 };
    return year * 3 + seasonOrd[season];
}

function addWarningBadge(box, issues) {
    const existing = box.querySelector('.cv-error-line');
    if (existing) existing.remove();
    const hasError = issues.some(i => i.sev === 'error');
    box.classList.toggle('cv-error',   hasError);
    box.classList.toggle('cv-warning', !hasError);
    const line = document.createElement('div');
    line.className = `cv-error-line ${hasError ? 'cv-error-line-err' : 'cv-error-line-warn'}`;
    line.innerHTML = issues.map(i => '▶ ' + i.msg.replace(/</g, '&lt;')).join('<br>');
    box.appendChild(line);
}

window.validateGrid = function() {
    // 1. Clear previous state
    document.querySelectorAll('.course-box').forEach(b => {
        b.classList.remove('cv-warning', 'cv-error');
        const el = b.querySelector('.cv-error-line');
        if (el) el.remove();
        const distEl = b.querySelector('.std-seq-dist');
        if (distEl) distEl.remove();
    });

    // Collect all issues across all boxes; apply badges at end
    const allIssues = []; // { courseId, msg, sev }
    const boxIssues = new Map(); // box element → [{msg, sev}]

    function flagBox(box, issues) {
        if (!issues.length) return;
        const cid = (box.dataset.courseId || '?').toUpperCase();
        issues.forEach(i => allIssues.push({ courseId: cid, msg: i.msg, sev: i.sev }));
        const existing = boxIssues.get(box) || [];
        boxIssues.set(box, [...existing, ...issues]);
    }

    // 2. Build placement snapshot: keyed by both normalized ID and raw ID (preserving A/B suffix)
    const snap = {};
    document.querySelectorAll('.drop-zone .course-box').forEach(box => {
        const cid = (box.dataset.courseId || '').toUpperCase();
        if (!cid || !box.parentElement) return;
        const entry = { zoneId: box.parentElement.id, termOrd: getTermOrdFromZoneId(box.parentElement.id), el: box };
        snap[cid] = entry;
        // Also store under raw ID (with A/B suffix) extracted from element ID
        const rawParts = (box.id || '').toUpperCase().split('_');
        const rawCid   = rawParts[rawParts.length - 1]; // e.g. "ENGR490A"
        if (rawCid && rawCid !== cid) snap[rawCid] = entry;
    });

    // Pre-req/co-req parser that PRESERVES A/B suffix (e.g. ENGR490A stays ENGR490A)
    function parseReqIds(str) {
        const matches = String(str || '').match(/[A-Z]{2,5}\s*\d{3,4}[A-Z]?/gi) || [];
        return matches.map(m => m.replace(/\s/g, '').toUpperCase());
    }
    function lookupSnap(id) {
        return snap[id] || snap[id.replace(/[AB]$/, '')] || null;
    }

    // 3. Check each zone (skip Y0 and Unallocated)
    document.querySelectorAll('.drop-zone').forEach(zone => {
        if (zone.id === 'zone_Y0' || zone.id === 'zone_Unallocated') return;
        const zOrd   = getTermOrdFromZoneId(zone.id);
        const isPast = zone.dataset.isPast === 'true';
        const season = zone.id.split('_').pop(); // Summer | Fall | Winter

        const boxes     = Array.from(zone.children).filter(c => c.classList.contains('course-box'));
        const wtBoxes   = boxes.filter(b => b.classList.contains('wt'));
        const realBoxes = boxes.filter(b => !b.classList.contains('wt') && !b.classList.contains('course-taken'));

        boxes.forEach(box => {
            if (box.classList.contains('course-taken')) {
                const origZone = box.dataset.originalZone;
                if (origZone && origZone !== zone.id) {
                    // Format original zone for display: zone_2025-2026_Winter → "2025-2026 WIN"
                    const parts = origZone.replace('zone_', '').split('_');
                    const origLabel = origZone === 'zone_Y0'
                        ? 'Y0 (Past/Exempt)'
                        : `${parts[0]} ${parts[1] === 'Winter' ? 'WIN' : parts[1] === 'Summer' ? 'SUM' : parts[1]}`;
                    flagBox(box, [{ msg: `Course already taken in ${origLabel} — for repeated courses use the REPEAT A COURSE menu`, sev: 'error' }]);
                }
                return;
            }
            const cid    = (box.dataset.courseId || '').toUpperCase();
            const db     = lookupCourse(cid) || {};
            const issues = [];

            // Check 1: Term offering
            if (!isPast && !box.classList.contains('wt')) {
                const hasAnyX = ['SUM 1', 'SUM 2', 'FALL', 'WIN'].some(k =>
                    String(db[k] || '').toUpperCase() === 'X');
                if (hasAnyX) {
                    let offered = false;
                    if (season === 'Summer') offered = ['SUM 1', 'SUM 2'].some(k => String(db[k] || '').toUpperCase() === 'X');
                    if (season === 'Fall')   offered = String(db['FALL'] || '').toUpperCase() === 'X';
                    if (season === 'Winter') offered = String(db['WIN']  || '').toUpperCase() === 'X';
                    if (!offered) issues.push({ msg: `Not offered in ${season}`, sev: 'error' });
                }
            }

            // Check 2: Pre-reqs must be in an EARLIER term (uses A/B-aware lookup)
            const prereqStr = String(db['PRE-REQUISITE'] || '');
            prereqStr.split(/[;,]/).forEach(seg => {
                const opts = parseReqIds(seg).filter(id => lookupSnap(id));
                if (!opts.length) return;
                const ok = opts.some(id => lookupSnap(id).termOrd < zOrd);
                if (!ok) issues.push({ msg: `Pre-req [${opts.join(' or ')}] not in earlier term`, sev: 'error' });
            });

            // Check 3: Co-reqs must be in same or earlier term (uses A/B-aware lookup)
            const coreqStr = String(db['CO-REQUISITE'] || '');
            coreqStr.split(/[;,]/).forEach(seg => {
                const opts = parseReqIds(seg).filter(id => lookupSnap(id));
                if (!opts.length) return;
                const ok = opts.some(id => lookupSnap(id).termOrd <= zOrd);
                if (!ok) issues.push({ msg: `Co-req [${opts.join(' or ')}] must be in same or earlier term`, sev: 'warning' });
            });

            // Check 4: WT conflict — max 1 real course alongside WT
            if (box.classList.contains('wt') && realBoxes.length > 1) {
                issues.push({ msg: 'Max 1 course alongside a Work Term', sev: 'error' });
            }
            if (!box.classList.contains('wt') && wtBoxes.length > 0 && realBoxes.length > 1) {
                issues.push({ msg: 'Too many courses in a Work Term', sev: 'error' });
            }
            
            // Check 4b: Warning when exactly 1 course is taken during WT
            if (!box.classList.contains('wt') && wtBoxes.length > 0 && realBoxes.length === 1) {
                issues.push({ msg: 'You may take a maximum of one course during your internship term. You must obtain approval of your sequence from your Academic Director and written permission from your employer. The course must not interfere with the internship or conflict with normal business hours. Students are responsible for their coursework; employers are not obligated to adjust work schedules, and professors are not obligated to grant accommodations.', sev: 'warning' });
            }

            // Check 5: Capstone (490) cannot be in a WT term
            if (cid.includes('490') && wtBoxes.length > 0) {
                issues.push({ msg: 'Capstone (490) cannot be in a Work Term', sev: 'error' });
            }

            if (issues.length) flagBox(box, issues);
        });
    });

    // Check 6: 490A and 490B must be consecutive (Fall → Winter of same aca year)
    const cap490 = {};
    document.querySelectorAll('.drop-zone .course-box').forEach(box => {
        if (box.classList.contains('course-taken') || !box.parentElement) return;
        const rawId = box.id || '';
        const zid   = box.parentElement.id;
        const mA    = rawId.match(/_([A-Z]+490)A$/i);
        const mB    = rawId.match(/_([A-Z]+490)B$/i);
        if (mA) cap490[mA[1].toUpperCase() + 'A'] = { box, zid };
        if (mB) cap490[mB[1].toUpperCase() + 'B'] = { box, zid };
    });
    Object.keys(cap490).filter(k => k.endsWith('A')).forEach(keyA => {
        const prefix = keyA.slice(0, -1);
        const aInfo  = cap490[prefix + 'A'];
        const bInfo  = cap490[prefix + 'B'];
        if (!aInfo || !bInfo) return;
        const aYear   = aInfo.zid.match(/zone_(\d{4})-/)?.[1];
        const bYear   = bInfo.zid.match(/zone_(\d{4})-/)?.[1];
        const aSeason = aInfo.zid.split('_').pop();
        const bSeason = bInfo.zid.split('_').pop();
        const ok = (aYear === bYear && aSeason === 'Fall' && bSeason === 'Winter');
        if (!ok) {
            flagBox(aInfo.box, [{ msg: `${prefix}A must be in Fall, ${prefix}B in same year Winter`, sev: 'error' }]);
            flagBox(bInfo.box, [{ msg: `${prefix}B must follow ${prefix}A in Winter of same year`, sev: 'error' }]);
        }
    });

    // Gather all zones sorted for WT checks
    const allZones = [];
    document.querySelectorAll('.drop-zone').forEach(z => {
        if (z.id === 'zone_Y0' || z.id === 'zone_Unallocated') return;
        allZones.push({ id: z.id, ord: getTermOrdFromZoneId(z.id), el: z });
    });
    allZones.sort((a, b) => a.ord - b.ord);

    // Check 7 + 8: WT ordering — WT2 requires WT1 before, WT3 requires WT2 before
    if (document.getElementById('coopRegistered')?.checked) {
        // Collect WT positions: { WT1: { ord, el: box }, WT2: ..., WT3: ... }
        const wtPos = {};
        allZones.forEach(({ ord, el }) => {
            Array.from(el.children).forEach(box => {
                if (!box.classList.contains('wt')) return;
                // Skip taken WT courses for position tracking
                const cid = (box.dataset.courseId || '').toUpperCase();
                const did = (box.dataset.displayId || '').toUpperCase();
                // Determine WT number from displayId, courseId, or alias
                let wtNum = null;
                const mDid = did.match(/WT(\d)/);
                const mCid = cid.match(/WT(\d)/);
                if (mDid) wtNum = mDid[1];
                else if (mCid) wtNum = mCid[1];
                else {
                    // Check aliases: e.g. CWTE101 → WT1
                    const rawCid = (box.id || '').toUpperCase();
                    for (const [alias, wtName] of Object.entries(WT_ALIASES)) {
                        if (rawCid.includes(alias) || did.includes(alias) || cid === alias.replace(/\s/g,'')) {
                            const am = wtName.match(/WT(\d)/);
                            if (am) { wtNum = am[1]; break; }
                        }
                    }
                }
                if (wtNum) {
                    const key = 'WT' + wtNum;
                    if (!wtPos[key] || ord < wtPos[key].ord) wtPos[key] = { ord, el: box };
                }
            });
        });

        // WT1 checks — study terms + credits (skip for GRAD programs)
        const _isGradProg = !!window.APP_CONFIG?.isGrad || (document.getElementById('programSelect')?.value || '').toUpperCase().includes('GRAD');
        if (wtPos.WT1 && !_isGradProg) {
            let studyTermsBefore = 0, coreCrBefore = 0;
            allZones.forEach(({ ord, el }) => {
                if (ord >= wtPos.WT1.ord) return;
                const boxes = Array.from(el.children).filter(c => c.classList.contains('course-box') && !c.classList.contains('wt'));
                if (boxes.length > 0) studyTermsBefore++;
                boxes.forEach(b => {
                    const db = lookupCourse(b.dataset.courseId || '') || {};
                    const t  = String(db['CORE_TE'] || '').toUpperCase();
                    if (t.includes('CORE') || t.includes('TE') || t.includes('PRG'))
                        coreCrBefore += parseFloat(b.dataset.credit || 0);
                });
            });
            if (studyTermsBefore < 2)
                flagBox(wtPos.WT1.el, [{ msg: 'Must have ≥2 study terms before WT1', sev: 'error' }]);
            else if (coreCrBefore < 30)
                flagBox(wtPos.WT1.el, [{ msg: `Only ${coreCrBefore} CORE/TE credits before WT1 (need ≥30)`, sev: 'error' }]);

            // ENCS 282 must be taken before WT1
            let encs282Before = false;
            allZones.forEach(({ ord, el }) => {
                if (ord >= wtPos.WT1.ord) return;
                Array.from(el.children).forEach(b => {
                    const cid = (b.dataset.courseId || '').toUpperCase();
                    if (cid === 'ENCS282') encs282Before = true;
                });
            });
            if (!encs282Before)
                flagBox(wtPos.WT1.el, [{ msg: 'ENCS 282 must be taken before WT1', sev: 'error' }]);
        }

        // Check 8: WT2 must be after WT1
        if (wtPos.WT2) {
            if (!wtPos.WT1)
                flagBox(wtPos.WT2.el, [{ msg: 'WT1 must be placed before WT2', sev: 'error' }]);
            else if (wtPos.WT2.ord <= wtPos.WT1.ord)
                flagBox(wtPos.WT2.el, [{ msg: 'WT2 must be in a later term than WT1', sev: 'error' }]);
        }

        // Check 8b: WT3 must be after WT2
        if (wtPos.WT3) {
            if (!wtPos.WT2)
                flagBox(wtPos.WT3.el, [{ msg: 'WT2 must be placed before WT3', sev: 'error' }]);
            else if (wtPos.WT3.ord <= wtPos.WT2.ord)
                flagBox(wtPos.WT3.el, [{ msg: 'WT3 must be in a later term than WT2', sev: 'error' }]);
        }

        // Check: WT placed in a low-GPA restricted term
        ['WT1','WT2','WT3'].forEach(wtKey => {
            if (!wtPos[wtKey]) return;
            const wtZone = wtPos[wtKey].el.parentElement;
            if (!wtZone) return;
            const restContainer = document.getElementById(`restrictions_${wtZone.id}`);
            if (!restContainer) return;
            const hasLowGpaRestriction = restContainer.querySelector('.low-gpa-next-term');
            if (hasLowGpaRestriction) {
                flagBox(wtPos[wtKey].el, [{ msg: `${wtKey} placed in a restricted term — ${hasLowGpaRestriction.textContent}`, sev: 'error' }]);
            }
        });

        // Check 8c: Term immediately before last WT must be full-time (≥Credits_FT)
        // Find the last (highest) WT
        const lastWt = [wtPos.WT1, wtPos.WT2, wtPos.WT3]
            .filter(w => w)
            .sort((a, b) => b.ord - a.ord)[0];
        
        if (lastWt && lastWt.ord > 0) {
            // Look up Credits_FT from program DB
            const _progNamesDb8c = window.APP_CONFIG?.programNamesDb || [];
            const _selectedProg8c = document.getElementById('programSelect')?.value || '';
            const _progRow8c = _progNamesDb8c.find(r => String(r['Program'] || '').trim() === _selectedProg8c);
            const _creditsFT8c = _progRow8c ? parseFloat(_progRow8c['Credits_FT']) : 12; // fallback 12

            // Find the term immediately before the last WT
            const prevTermOrd = lastWt.ord - 1;
            const prevZone = allZones.find(z => z.ord === prevTermOrd);
            
            if (prevZone) {
                const prevSeason = prevZone.id.split('_').pop();
                const isPrevSummer = prevSeason === 'Summer';
                
                // Check if previous term has a WT
                const prevHasWt = Array.from(prevZone.el.children).some(c => c.classList.contains('wt'));
                
                // Only check if previous term is NOT summer and does NOT have a WT
                if (!isPrevSummer && !prevHasWt) {
                    let prevCr = 0;
                    Array.from(prevZone.el.children).forEach(box => {
                        if (!box.classList.contains('wt')) {
                            prevCr += parseFloat(box.dataset.credit || 0);
                        }
                    });
                    
                    if (prevCr < _creditsFT8c) {
                        const lastWtName = (lastWt.el.dataset.displayId || lastWt.el.dataset.courseId || 'last WT').toUpperCase();
                        const prevLabel = prevZone.id.replace('zone_', '').replace(/_/g, ' ');
                        flagBox(lastWt.el, [{ msg: `Not full-time: ${prevLabel} has ${prevCr}cr < FT minimum of ${_creditsFT8c}cr — the term before ${lastWtName} must be Full-Time`, sev: 'error' }]);
                    }
                }
            }
        }

        // Check 9: After WT3 there must be ≥1 CORE/PRG/ECP course
        if (wtPos.WT3) {
            let coreAfterWT3 = 0;
            const teAfterWT3 = [];
            let totalPlannedCr = 0;

            // Count all placed non-taken courses total credits
            document.querySelectorAll('.drop-zone .course-box').forEach(box => {
                if (box.classList.contains('course-taken')) return;
                if (box.parentElement && box.parentElement.id !== 'zone_Unallocated') {
                    totalPlannedCr += parseFloat(box.dataset.credit || 0);
                }
            });
            // Also count taken courses
            document.querySelectorAll('.drop-zone .course-box.course-taken').forEach(box => {
                totalPlannedCr += parseFloat(box.dataset.credit || 0);
            });

            allZones.forEach(({ ord, el }) => {
                if (ord <= wtPos.WT3.ord) return;
                Array.from(el.children).forEach(box => {
                    if (!box.classList.contains('course-box') || box.classList.contains('wt')) return;
                    const db = lookupCourse(box.dataset.courseId || '') || {};
                    const t  = String(db['CORE_TE'] || '').toUpperCase();
                    const cr = parseFloat(box.dataset.credit || 0);
                    if (t.includes('CORE') || t.includes('PRG') || t.includes('ECP')) {
                        coreAfterWT3++;
                    } else if (t.includes('TE')) {
                        teAfterWT3.push(`${(box.dataset.courseId || '').toUpperCase()} (${cr}cr)`);
                    }
                });
            });

            if (coreAfterWT3 === 0) {
                let msg = 'Must have ≥1 CORE/PRG course after WT3';
                if (teAfterWT3.length > 0) {
                    msg += ` — TE after WT3: ${teAfterWT3.join(', ')} — Total planned: ${totalPlannedCr}cr (TE electives count toward 120cr)`;
                }
                flagBox(wtPos.WT3.el, [{ msg, sev: 'error' }]);
            }
        }

        // Check 10: 3 consecutive WTs validation
        const wtOrds = [];
        if (wtPos.WT1) wtOrds.push({ num: 1, ord: wtPos.WT1.ord, el: wtPos.WT1.el });
        if (wtPos.WT2) wtOrds.push({ num: 2, ord: wtPos.WT2.ord, el: wtPos.WT2.el });
        if (wtPos.WT3) wtOrds.push({ num: 3, ord: wtPos.WT3.ord, el: wtPos.WT3.el });
        wtOrds.sort((a, b) => a.ord - b.ord);

        if (wtOrds.length >= 3) {
            // Check if any 3 WTs are consecutive (ord values differ by 1)
            for (let i = 0; i < wtOrds.length - 2; i++) {
                if (wtOrds[i+1].ord === wtOrds[i].ord + 1 && wtOrds[i+2].ord === wtOrds[i].ord + 2) {
                    // Flag all 3 WTs involved
                    flagBox(wtOrds[i].el, [{ msg: 'Invalid Sequence: You cannot have 3 consecutive Work Terms', sev: 'error' }]);
                    flagBox(wtOrds[i+1].el, [{ msg: 'Invalid Sequence: You cannot have 3 consecutive Work Terms', sev: 'error' }]);
                    flagBox(wtOrds[i+2].el, [{ msg: 'Invalid Sequence: You cannot have 3 consecutive Work Terms', sev: 'error' }]);
                    break;
                }
            }
        }

        // Check 11: 3 summer WTs validation
        let summerWTCount = 0;
        const summerWTs = [];
        if (wtPos.WT1) {
            const zone1 = allZones.find(z => z.ord === wtPos.WT1.ord);
            if (zone1 && zone1.id.includes('Summer')) {
                summerWTCount++;
                summerWTs.push({ num: 1, el: wtPos.WT1.el });
            }
        }
        if (wtPos.WT2) {
            const zone2 = allZones.find(z => z.ord === wtPos.WT2.ord);
            if (zone2 && zone2.id.includes('Summer')) {
                summerWTCount++;
                summerWTs.push({ num: 2, el: wtPos.WT2.el });
            }
        }
        if (wtPos.WT3) {
            const zone3 = allZones.find(z => z.ord === wtPos.WT3.ord);
            if (zone3 && zone3.id.includes('Summer')) {
                summerWTCount++;
                summerWTs.push({ num: 3, el: wtPos.WT3.el });
            }
        }

        if (summerWTCount >= 3) {
            // Flag all 3 summer WTs
            summerWTs.forEach(wt => {
                flagBox(wt.el, [{ msg: 'Invalid Sequence: You cannot have 3 Summer Work Terms', sev: 'error' }]);
            });
        }
    }

    // Check 10: Restrictions from CORE_TE.xlsx
    if (window.checkRestrictions && window.restrictionsDb) {
        const seenRestrictions = new Set(); // deduplicate global restrictions
        
        // 10a: Per-term restrictions (shown in term headers AND in error list if WARNING)
        allZones.forEach(({ id: zid, el: zoneEl }) => {
            const season = zid.split('_').pop();
            const yearMatch = zid.match(/zone_(\d{4}-\d{4})/);
            const yearStr = yearMatch ? yearMatch[1] : '';
            const restrictions = window.checkRestrictions(zid, season, yearStr);
            restrictions.forEach(r => {
                if (r.isWarning && !seenRestrictions.has(r.text)) {
                    seenRestrictions.add(r.text);
                    allIssues.push({ courseId: '', msg: '⚠ ' + r.text, sev: 'warning' });
                }
            });
        });
        
        // 10b: Global course restrictions (no Term/Year) — check if course exists anywhere
        //       These show as warnings if the relevant course is placed anywhere in the grid
        const isCoop = !!document.getElementById('coopRegistered')?.checked;
        const selectedProg = document.getElementById('programSelect')?.value || '';
        const progFam = (function(p) {
            const u = String(p||'').toUpperCase();
            if (u.includes('INDU')) return 'INDU';
            if (u.includes('AERO')) return 'AERO';
            if (u.includes('MECH')) return 'MECH';
            return '';
        })(selectedProg);
        
        window.restrictionsDb.forEach(r => {
            const rCourse = String(r['Course'] || '').trim();
            const rTerm = String(r['Term'] || '').trim();
            const rYear = String(r['Year'] || '').trim();
            if (!rCourse || rCourse.toLowerCase() === 'nan') return;
            // Only handle global restrictions (no specific term/year) here
            if (rTerm && rTerm.toLowerCase() !== 'nan') return;
            if (rYear && rYear.toLowerCase() !== 'nan') return;
            
            // Check program filter
            const rProg = String(r['Program'] || '').trim().toUpperCase();
            if (rProg && rProg !== 'NAN' && progFam !== rProg) return;
            
            // Check COOP filter
            const rCoopSel = String(r['COOP selected'] || '').trim().toUpperCase();
            if (rCoopSel && rCoopSel !== 'NAN') {
                if (rCoopSel === 'YES' && !isCoop) return;
                if (rCoopSel === 'NO' && isCoop) return;
            }
            
            // Check Level filter: UGRD or GRAD
            const rLevel2 = String(r['Level'] || r['level'] || '').trim().toUpperCase();
            if (rLevel2 && rLevel2 !== 'NAN') {
                const studentIsGrad2 = !!window.APP_CONFIG?.isGrad;
                if (rLevel2 === 'UGRD' && studentIsGrad2) return;
                if (rLevel2 === 'GRAD' && !studentIsGrad2) return;
            }
            
            // Check date filter
            const dateStr = r['Date after which takes effect'];
            if (dateStr && String(dateStr).trim() && String(dateStr).toLowerCase() !== 'nan' && String(dateStr).toLowerCase() !== 'nat') {
                const effDate = new Date(dateStr);
                const today = new Date(); today.setHours(0,0,0,0);
                if (!isNaN(effDate.getTime()) && today < effDate) return;
            }
            
            const warningCol = String(r['WARNING'] || '').trim().toUpperCase();
            const isFyi = warningCol === 'NO' || warningCol === 'FYI';
            const isWarning = !isFyi;
            const text = String(r['Restriction'] || 'Restriction applies');
            
            if (isWarning && !seenRestrictions.has(text)) {
                seenRestrictions.add(text);
                allIssues.push({ courseId: '', msg: '⚠ ' + text, sev: 'warning' });
            }
        });
    }

    // Check 11: Required CORE/PRG courses still in Unallocated should be flagged
    const unallocZone = document.getElementById('zone_Unallocated');
    if (unallocZone) {
        Array.from(unallocZone.children).forEach(box => {
            if (!box.classList.contains('course-box') || box.classList.contains('wt')) return;
            const cid = (box.dataset.courseId || '').toUpperCase();
            const db  = lookupCourse(cid) || {};
            const t   = String(db['CORE_TE'] || '').toUpperCase();
            if (t.includes('CORE') || t.includes('PRG') || t.includes('ECP')) {
                flagBox(box, [{ msg: 'Required course not placed in any term', sev: 'error' }]);
            }
        });
    }

    // GPA check against program threshold (DB: Program_names → GPA_2_terms)
    // Also colours every cgpa-info cell: red if below threshold, orange if in low range
    (function() {
        const progNamesDb = window.APP_CONFIG?.programNamesDb || [];
        const selectedProg = document.getElementById('programSelect')?.value || '';

        // DB column is "Program" (capital P)
        const progRow = progNamesDb.find(r => String(r['Program'] || '').trim() === selectedProg);
        const threshold = progRow ? parseFloat(progRow['GPA_2_terms']) : NaN;

        const history = window.APP_CONFIG?.cgpaHistory || [];

        // Colour every past-term cgpa-info div based on its own GPA values
        document.querySelectorAll('.cgpa-info').forEach(div => {
            const info = div.innerHTML || '';
            const recentM = info.match(/<b>([\d.]+)<\/b>/) || info.match(/GPA past [\d.]+cr:\s*([\d.]+)/);
            const cgpaM   = info.match(/CGPA\s+([\d.]+)/);
            const rv = recentM ? parseFloat(recentM[1]) : null;
            const cv = cgpaM   ? parseFloat(cgpaM[1])   : null;
            const minVal = [rv, cv].filter(v => v !== null).reduce((a, b) => Math.min(a, b), Infinity);

            // reset
            div.style.background   = '';
            div.style.borderColor  = '';
            div.style.color        = '';

            if (!isNaN(threshold) && minVal !== Infinity) {
                if (minVal < threshold) {
                    div.style.background  = '#fdf2f2';
                    div.style.borderColor = '#e74c3c';
                    div.style.color       = '#c0392b';
                } else if (minVal < threshold + 0.2) {
                    div.style.background  = '#fef5e7';
                    div.style.borderColor = '#e67e22';
                    div.style.color       = '#e67e22';
                }
            }
        });

        // Add issues to error panel for the LAST (most recent) term only
        if (!history.length || isNaN(threshold)) return;
        const _isGradGpa = !!window.APP_CONFIG?.isGrad || (document.getElementById('programSelect')?.value || '').toUpperCase().includes('GRAD');
        const gpaLimit = _isGradGpa ? 3.3 : threshold + 0.2;
        const cgpaLimit = _isGradGpa ? 3.3 : threshold;

        const last = history[history.length - 1];
        const _infoStr2 = String(last.info || '');
        const recentMatch = _infoStr2.match(/<b>([\d.]+)<\/b>/) || _infoStr2.match(/GPA past [\d.]+cr:\s*([\d.]+)/);
        const cgpaMatch   = _infoStr2.match(/CGPA\s+([\d.]+)/);
        const isNA        = _infoStr2.includes('N/A');
        const recentGpa   = recentMatch ? parseFloat(recentMatch[1]) : null;
        const cgpa        = cgpaMatch   ? parseFloat(cgpaMatch[1])   : null;
        const termLabel   = `${last.year} ${last.season}`;

        [{ val: recentGpa, name: 'GPA past 24.5cr', limit: gpaLimit }, { val: cgpa, name: 'CGPA', limit: cgpaLimit }].forEach(({ val, name, limit }) => {
            if (val === null || isNA) return;
            if (val < limit) {
                allIssues.push({ courseId: '', msg: `LOW ${name} (${val} < ${limit}) in ${termLabel} — cannot schedule a WT in next 2 terms after current term`, sev: 'error' });
            } else if (!_isGradGpa && val < threshold + 0.2) {
                allIssues.push({ courseId: '', msg: `${name} (${val}) in low range — must recover prior to next WT`, sev: 'warning' });
            }
        });
    })();

    // Credits_FT check: co-op study terms (blue) that are Fall/Winter must meet minimum credits
    (function() {
        const progNamesDb  = window.APP_CONFIG?.programNamesDb || [];
        const selectedProg = document.getElementById('programSelect')?.value || '';
        const progRow      = progNamesDb.find(r => String(r['Program'] || '').trim() === selectedProg);
        const creditsFT    = progRow ? parseFloat(progRow['Credits_FT']) : NaN;
        if (isNaN(creditsFT)) return;

        const isACSD = !!document.getElementById('acsdRegistered')?.checked;
        const isCoop = !!document.getElementById('coopRegistered')?.checked;
        if (!isCoop) return;

        // Find last placed WT zone sort key (reuse same logic as post-WT FYI)
        function zoneSortKey(zid) {
            const m = zid.match(/zone_(\d{4}-\d{4})_(\w+)/);
            if (!m) return '';
            return `${m[1]}-${{ Summer:1, Fall:2, Winter:3 }[m[2]] || 0}`;
        }
        let lastWtKey = '';
        document.querySelectorAll('.drop-zone .course-box.wt').forEach(b => {
            const zid = b.parentElement?.id;
            if (!zid || zid === 'zone_Unallocated') return;
            const k = zoneSortKey(zid);
            if (k > lastWtKey) lastWtKey = k;
        });

        // first blue (S-x) zone key
        let firstCoopKey = '';
        document.querySelectorAll('td').forEach(td => {
            if (!td.querySelector('.coop-study-header')) return;
            const z = td.querySelector('.drop-zone');
            if (!z || z.id === 'zone_Y0' || z.id === 'zone_Unallocated') return;
            const k = zoneSortKey(z.id);
            if (k && (!firstCoopKey || k < firstCoopKey)) firstCoopKey = k;
        });

        // Co-op terms: blue study terms + any Fall/Winter term between first S-x and last WT
        const lowTerms = [];
        document.querySelectorAll('.drop-zone').forEach(zone => {
            const zid = zone.id;
            if (!zid || zid === 'zone_Unallocated' || zid === 'zone_Y0') return;
            const season = zid.split('_').pop();
            if (season !== 'Fall' && season !== 'Winter') return;

            const td = zone.closest('td');
            if (!td) return;

            const isBlue  = !!td.querySelector('.coop-study-header');
            const zKey    = zoneSortKey(zid);
            
            // Skip terms AFTER the last WT
            if (lastWtKey && zKey > lastWtKey) return;
            
            const inRange = firstCoopKey && lastWtKey && zKey >= firstCoopKey && zKey <= lastWtKey;
            if (!isBlue && !inRange) return;

            // WT placed in term → full time, skip
            if (zone.querySelector('.course-box.wt')) return;

            const termCr = Array.from(zone.children)
                .filter(c => c.classList.contains('course-box'))
                .reduce((s, c) => s + parseFloat(c.dataset.credit || 0), 0);

            const yearMatch = zid.match(/zone_(\d{4}-\d{4})_/);
            const label = `${yearMatch ? yearMatch[1] : ''} ${season}`.trim();

            if (termCr < creditsFT) {
                lowTerms.push({ label, cr: termCr });
            }
        });

        if (!lowTerms.length) return;

        if (isACSD) {
            allIssues.push({
                courseId: '',
                msg: '!! Student is registered with ACSD — enter in the justification the number of credits approved by ACSD for each affected term.',
                sev: 'warning'
            });
        } else {
            lowTerms.forEach(({ label, cr }) => {
                allIssues.push({
                    courseId: '',
                    msg: `Not full-time: ${label} has ${cr}cr < FT minimum of ${creditsFT}cr — add justification`,
                    sev: 'error'
                });
            });
        }
    })();

    // Check: Credit requirements validation
    (function() {
        const selectedProg = document.getElementById('programSelect')?.value || '';
        const programsReqDb = window.APP_CONFIG?.programsRequirementsDb || [];
        
        // Get program requirements
        const progReqs = {}; // { 'ENG CORE': 27, 'PRG CORE': 87, 'TE': 6 }
        programsReqDb.forEach(row => {
            if (String(row['Program'] || '').trim() === selectedProg && String(row['Level'] || '').trim() === 'UGRD') {
                const type = String(row['Type of credits'] || '').trim();
                const required = parseFloat(row['no of credits'] || 0);
                if (type && required > 0) {  // Only check categories with required > 0
                    progReqs[type] = required;
                }
            }
        });
        
        if (Object.keys(progReqs).length === 0) return;
        
        // Calculate current credits by category
        const cats = {};
        document.querySelectorAll('.drop-zone .course-box').forEach(box => {
            if (box.parentElement?.id === 'zone_Unallocated') return;
            const cid = (box.dataset.courseId || '').toUpperCase();
            const db  = lookupCourse(cid) || {};
            const t   = String(db['CORE_TE'] || '').trim();
            const cr  = parseFloat(box.dataset.credit || 0);
            if (t && cr > 0) {
                cats[t] = (cats[t] || 0) + cr;
            }
        });
        
        // Check each required category
        Object.keys(progReqs).forEach(category => {
            const required = progReqs[category];
            const current = cats[category] || 0;
            
            if (current < required) {
                allIssues.push({
                    courseId: '',
                    msg: `Not enough credits in ${category} category: ${current} listed out of ${required} required`,
                    sev: 'error'
                });
            }
        });
    })();

    // Check: Standard sequence deviation — list courses placed in a different term than std seq
    // Skip for GRAD programs (no standard sequence)
    (function() {
        const _isGradProg2 = !!window.APP_CONFIG?.isGrad || (document.getElementById('programSelect')?.value || '').toUpperCase().includes('GRAD');
        if (_isGradProg2) return;

        const sequencesDb = window.APP_CONFIG?.sequencesDb;
        if (!sequencesDb || !sequencesDb.length) return;

        const progSel = document.getElementById('programSelect');
        if (!progSel || !progSel.value) return;
        const progKey = getProgramKey(progSel.value);
        if (!progKey) return;

        const sYearStr = document.getElementById('startYear')?.value;
        if (!sYearStr) return;
        const baseYear = parseInt(sYearStr.split('-')[0]);

        // Build map: courseId → { stdZoneId, stdOrd, stdLabel }
        const stdMap = {};
        sequencesDb.filter(s => s.PROGRAM_KEY === progKey).forEach(entry => {
            const cid = String(entry.COURSE).replace(/\s/g, '').toUpperCase();
            const pos = String(entry.POSITION).trim();
            const zid = positionToZoneId(pos, baseYear);
            if (!zid) return;
            const ord = getTermOrdFromZoneId(zid);
            const parts = zid.replace('zone_', '').split('_');
            const label = parts.join(' ');
            stdMap[cid] = { stdZoneId: zid, stdOrd: ord, stdLabel: label };
        });

        if (!Object.keys(stdMap).length) return;

        // Helper: zone id → human label
        function zoneLabel(zid) {
            if (!zid || zid === 'zone_Y0') return 'Y0';
            if (zid === 'zone_Unallocated') return 'Unallocated';
            const parts = zid.replace('zone_', '').split('_');
            return parts.join(' ');
        }

        // Scan all placed courses on the grid (including WT and taken courses)
        const deviations = [];
        document.querySelectorAll('.drop-zone').forEach(zone => {
            if (zone.id === 'zone_Y0' || zone.id === 'zone_Unallocated') return;
            const actualOrd = getTermOrdFromZoneId(zone.id);

            Array.from(zone.children).forEach(box => {
                if (!box.classList.contains('course-box')) return;

                const cid = (box.dataset.courseId || '').toUpperCase();
                const displayId = (box.dataset.displayId || cid).toUpperCase();

                // For WT courses: lookup by WT1/WT2/WT3
                let std = null;
                if (box.classList.contains('wt')) {
                    const wtMatch = displayId.match(/^WT(\d)$/);
                    if (wtMatch) std = stdMap['WT' + wtMatch[1]];
                } else {
                    std = stdMap[displayId] || stdMap[cid] || stdMap[cid.replace(/[AB]$/, '')];
                }

                if (!std) return; // no standard sequence entry for this course

                if (zone.id === std.stdZoneId) return; // matches standard — no deviation

                const diff = actualOrd - std.stdOrd;
                const sign = diff > 0 ? `+${diff}` : `${diff}`;
                const actualLabel = zoneLabel(zone.id);

                deviations.push({
                    courseId: displayId,
                    diff: diff,
                    sign: sign,
                    stdLabel: std.stdLabel,
                    actualLabel: actualLabel,
                    absDiff: Math.abs(diff)
                });

                // Write DIST label directly on the course box
                const distDiv = document.createElement('div');
                distDiv.className = 'std-seq-dist';
                const color = diff > 0 ? '#c0392b' : '#2980b9';
                distDiv.style.cssText = `font-size:10px;color:${color};font-weight:700;margin-top:2px;line-height:1.2;`;
                distDiv.textContent = `DIST ${sign} from std.seq. ${std.stdLabel}`;
                box.appendChild(distDiv);
            });
        });

        if (!deviations.length) return;

        // Sort by absolute deviation descending
        deviations.sort((a, b) => b.absDiff - a.absDiff);
    })();

    // Apply all badges
    boxIssues.forEach((issues, box) => addWarningBadge(box, issues));

    // List OTHER (unknown) courses placed on the grid
    (function() {
        const otherCourses = [];
        document.querySelectorAll('.drop-zone .course-box').forEach(box => {
            const zone = box.parentElement;
            if (!zone || zone.id === 'zone_Unallocated') return;
            if (box.classList.contains('wt')) return;
            const cid = (box.dataset.courseId || '').toUpperCase();
            const db = lookupCourse(cid);
            const coreTE = db ? String(db['CORE_TE'] || '').trim().toUpperCase() : '';
            // OTHER = unknown course OR empty CORE_TE OR explicitly 'OTHER'
            if (!db || db._unknown || !coreTE || coreTE === 'OTHER') {
                const displayId = box.dataset.displayId || cid;
                if (displayId && !otherCourses.includes(displayId)) otherCourses.push(displayId);
            }
        });
        if (otherCourses.length) {
            allIssues.push({ courseId: '', msg: `[OTHER] course(s) taken: ${otherCourses.join(', ')}`, sev: 'warning' });
        }
    })();

    // Update error panel
    const epBox   = document.getElementById('errPanel');
    const title   = document.getElementById('errPanelTitle');
    const panel   = document.getElementById('errPanelBody');
    if (epBox && title && panel) {
        panel.innerHTML = '';
        const errCount  = allIssues.filter(i => i.sev === 'error').length;
        const warnCount = allIssues.filter(i => i.sev === 'warning').length;
        const fyi       = allIssues.filter(i => i.sev === 'fyi').length;
        window.latestIssues = allIssues;

        if (allIssues.length === 0) {
            epBox.style.display = 'none';
            panel.classList.remove('ep-open');
        } else {
            epBox.style.display = '';
            panel.classList.add('ep-open');
            const total = allIssues.length;
            const parts = [];
            if (errCount > 0)  parts.push(`<span style="color:#c0392b; font-weight:bold;">${errCount} Error${errCount > 1 ? 's' : ''}</span>`);
            if (warnCount > 0) parts.push(`<span style="color:#2980b9; font-weight:bold;">${warnCount} Warning${warnCount > 1 ? 's' : ''}</span>`);
            if (fyi > 0)       parts.push(`<span style="color:#7f8c8d;">${fyi} FYI</span>`);
            title.innerHTML = `⚠ ${total} (${parts.join(', ')})`;

            // Show ALL issues in the body (expandable)
            allIssues.forEach(({ courseId, msg, sev }) => {
                const item = document.createElement('div');
                item.className = `ep-item ${sev === 'error' ? 'ep-error' : sev === 'fyi' ? 'ep-fyi' : 'ep-warning'}`;
                item.style.whiteSpace = 'pre-line';
                item.innerText = courseId ? `${courseId}: ${msg}` : msg;
                panel.appendChild(item);
            });
        }
    }

    // Update student message format in justification textarea
    if (window.buildStudentMessage) window.buildStudentMessage();

    // Update credit summary
    if (window.updateCreditSummary) window.updateCreditSummary();
};

window.autoSaveAdminNotes = async function(pub, priv) {
    try {
        await fetch('/api/save_admin_notes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_sid: window.APP_CONFIG.viewingSid, Public_comments: pub, PRIVATE_comments: priv })
        });
    } catch(e) { console.error("Autosave failed", e); }
};



// =========================================================
// SAVE / LOAD / SUBMIT + NOTES (Planner)
// =========================================================

function collectPlanSnapshot() {
    const plan = {
        version: 1,
        savedAt: new Date().toISOString(),
        startYear: document.getElementById('startYear')?.value || null,
        coopRegistered: !!document.getElementById('coopRegistered')?.checked,
        acsdRegistered: !!document.getElementById('acsdRegistered')?.checked,
        coopStartYear: document.getElementById('coopStartYear')?.value || null,
        coopStartTerm: document.getElementById('coopStartTerm')?.value || null,
        program: document.getElementById('programSelect')?.value || null,
        globalLimits: { maxCourses: window.globalMaxCourses, maxCredits: window.globalMaxCr },
        termOverrides: window.termOverrides || {},
        placements: []
    };

    // Save all non-taken course placements (including WT), plus pinned state
    document.querySelectorAll('.drop-zone .course-box').forEach(box => {
        if (box.classList.contains('course-taken')) return;
        const did = getBoxDisplayId(box);
        const zid = box.parentElement?.id;
        if (!did || !zid) return;
        plan.placements.push({
            displayId: did,
            zoneId: zid,
            pinned: box.dataset.pinned === 'true'
        });
    });

    // Also save unallocated positions (still useful on load)
    const unalloc = document.getElementById('zone_Unallocated');
    if (unalloc) {
        Array.from(unalloc.children).forEach(box => {
            if (!box.classList.contains('course-box')) return;
            if (box.classList.contains('course-taken')) return;
            const did = getBoxDisplayId(box);
            plan.placements.push({
                displayId: did,
                zoneId: 'zone_Unallocated',
                pinned: box.dataset.pinned === 'true'
            });
        });
    }

    return plan;
}

function getSelectedReasonCode() {
    const el = document.querySelector('input[name="submissionReason"]:checked');
    return el ? parseInt(el.value, 10) : null;
}

function getJustificationText() {
    return String(document.getElementById('justificationText')?.value || '').trim();
}

// Clean justification text before submission.
// Warnings are no longer included in the textarea, so this is a simple passthrough.
function stripWarningsFromJustification(text) {
    return (text || '').trim();
}

function currentIssues() {
    return Array.isArray(window.latestIssues) ? window.latestIssues : [];
}

window.applyLoadedPlan = function(planObj) {
    console.log('[applyLoadedPlan] CALLED with planObj:', planObj ? 'YES' : 'NO', planObj ? `(keys: ${Object.keys(planObj).length})` : '');
    if (!planObj) {
        console.log('[applyLoadedPlan] ABORT: planObj is null/undefined');
        return;
    }

    // =========================================================
    // COMPATIBILITY: detect old format (zone-based dict without 'version')
    // Old format: { "Y0_ANY": ["CHEM205",...], "Y1_FALL": [...], "startYear":"2024", ... }
    // New format: { version: 1, placements: [...], startYear: "2024-2025", ... }
    // =========================================================
    const isOldFormat = !planObj.version && !planObj.placements;
    if (isOldFormat) {
        // Convert old format to new
        const converted = {
            version: 1,
            startYear: planObj.startYear ? (planObj.startYear.includes('-') ? planObj.startYear : `${planObj.startYear}-${parseInt(planObj.startYear)+1}`) : null,
            coopRegistered: planObj.coop === true || planObj.coop === 'true',
            coopStartYear: planObj.coopStartYear ? (planObj.coopStartYear.includes('-') ? planObj.coopStartYear : `${planObj.coopStartYear}-${parseInt(planObj.coopStartYear)+1}`) : null,
            coopStartTerm: planObj.coopStartTerm || planObj.startTerm || null,
            program: planObj.program || null,
            globalLimits: planObj.globalLimits || null,
            termOverrides: planObj.termOverrides || {},
            placements: [],
            reason_code: planObj.reason_code !== undefined && planObj.reason_code !== null ? planObj.reason_code : (planObj.cos_reason !== undefined && planObj.cos_reason !== null ? planObj.cos_reason : 0),
            justification: planObj.justification || planObj.student_comments || ''
        };

        // Parse zone-based entries
        const sYearStr = converted.startYear || document.getElementById('startYear')?.value || '';
        const baseYear = sYearStr ? parseInt(sYearStr.split('-')[0]) : 2024;

        Object.entries(planObj).forEach(([key, val]) => {
            if (!Array.isArray(val)) return;
            // Key patterns from old tool: "Y0_ANY", "Y1_FALL", "Y2_SUM", "Y3_WIN", "UNALLOCATED"
            let zoneId = null;
            if (key === 'UNALLOCATED' || key === 'unallocated') {
                zoneId = 'zone_Unallocated';
            } else {
                const m = key.match(/^Y(\d+)_(ANY|SUM|FALL|WIN|SUMMER|WINTER)$/i);
                if (m) {
                    const yNum = parseInt(m[1]);
                    if (yNum === 0) {
                        zoneId = 'zone_Y0';
                    } else {
                        const seasonMap = { SUM: 'Summer', SUMMER: 'Summer', FALL: 'Fall', WIN: 'Winter', WINTER: 'Winter', ANY: 'Summer' };
                        const season = seasonMap[m[2].toUpperCase()] || 'Fall';
                        const acaStart = baseYear + yNum - 1;
                        zoneId = `zone_${acaStart}-${acaStart + 1}_${season}`;
                    }
                }
                // Also handle new-style zone IDs in old saves: "zone_2024-2025_Fall"
                if (!zoneId && key.startsWith('zone_')) {
                    zoneId = key;
                }
            }
            if (!zoneId) return;

            val.forEach(courseStr => {
                const cid = String(courseStr).replace(/\s/g, '').toUpperCase();
                if (!cid) return;
                // Extract course ID from old format (could be "course_student_0_CHEM205" or just "CHEM205")
                const idMatch = cid.match(/([A-Z]{2,5}\d{3,4}[A-Z]?(?:_REP)?)/);
                if (idMatch) {
                    converted.placements.push({
                        displayId: idMatch[1],
                        zoneId: zoneId,
                        pinned: zoneId !== 'zone_Unallocated'
                    });
                }
            });
        });

        planObj = converted;
    }

    // Restore settings first (without triggering onchange events)
    const startYearEl = document.getElementById('startYear');
    const coopCb = document.getElementById('coopRegistered');
    const coopStartYearEl = document.getElementById('coopStartYear');
    const coopStartTermEl = document.getElementById('coopStartTerm');
    const programEl = document.getElementById('programSelect');
    
    // Store original inline handler code from HTML attributes
    const startYearHandler = startYearEl?.getAttribute('onchange');
    const coopHandler = coopCb?.getAttribute('onchange');
    const coopStartYearHandler = coopStartYearEl?.getAttribute('onchange');
    const coopStartTermHandler = coopStartTermEl?.getAttribute('onchange');
    const programHandler = programEl?.getAttribute('onchange'); // programSelect DOES have inline handler: updateUnallocated()
    
    // Disable inline handlers using removeAttribute
    if (startYearEl) startYearEl.removeAttribute('onchange');
    if (coopCb) coopCb.removeAttribute('onchange');
    if (coopStartYearEl) coopStartYearEl.removeAttribute('onchange');
    if (coopStartTermEl) coopStartTermEl.removeAttribute('onchange');
    if (programEl) programEl.removeAttribute('onchange');
    
    // Now set values without triggering rebuilds
    if (planObj.startYear && startYearEl) {
        // Ensure the option exists in the dropdown before setting it
        const optExists = [...startYearEl.options].some(o => o.value === planObj.startYear);
        if (!optExists) {
            startYearEl.add(new Option(planObj.startYear, planObj.startYear), startYearEl.options[0]);
        }
        startYearEl.value = planObj.startYear;
    }
    if (coopCb) {
        const hasTranscriptCoop = Array.isArray(window.APP_CONFIG?.coopTerms) && window.APP_CONFIG.coopTerms.length > 0;
        const hasSavedWT = Array.isArray(planObj.placements) && planObj.placements.some(p =>
            /^WT\d$/i.test(String(p.displayId || ''))
        );

        coopCb.checked = !!planObj.coopRegistered || hasTranscriptCoop || hasSavedWT;
        const acsdCb = document.getElementById('acsdRegistered');
        if (acsdCb && planObj.acsdRegistered !== undefined) acsdCb.checked = !!planObj.acsdRegistered;

        if (sessionStorage.getItem('_pendingLoad') === '1') {
            coopCb.checked = true;
        }
    }
    if (planObj.coopStartYear && coopStartYearEl) {
        const optExists = [...coopStartYearEl.options].some(o => o.value === planObj.coopStartYear);
        if (!optExists) {
            coopStartYearEl.add(new Option(planObj.coopStartYear, planObj.coopStartYear), coopStartYearEl.options[0]);
        }
        coopStartYearEl.value = planObj.coopStartYear;
    }
    if (planObj.coopStartTerm && coopStartTermEl) coopStartTermEl.value = planObj.coopStartTerm;
    if (planObj.program && programEl) programEl.value = planObj.program;

    // Restore global limits
    if (planObj.globalLimits) {
        if (typeof planObj.globalLimits.maxCourses === 'number') window.setGlobalMaxCourses(planObj.globalLimits.maxCourses);
        if (typeof planObj.globalLimits.maxCredits === 'number') window.setGlobalMaxCr(planObj.globalLimits.maxCredits);
    }

    // Rebuild grid with the new dropdown values (handlers are disabled, so this won't trigger cascading rebuilds)
    window.rebuildGrid();

    // Restore per-term overrides (must be after rebuildGrid)
    window.termOverrides = planObj.termOverrides || {};

    // Map displayId -> box element AFTER rebuildGrid (get fresh elements)
    const boxMap = new Map();
    document.querySelectorAll('.course-box').forEach(box => {
        boxMap.set(getBoxDisplayId(box), box);
    });

    // Recreate REP courses that were saved but don't exist yet
    (planObj.placements || []).forEach(p => {
        const did = normDisplayId(p.displayId);
        if (!did.endsWith('_REP')) return;
        if (boxMap.has(did)) return; // already exists
        const origCid = did.replace(/_REP$/, '');
        const baseCid = origCid.replace(/[AB]$/, '');
        const dbCourse = lookupCourse(baseCid) || {};
        if (!dbCourse || dbCourse._unknown) return;
        const credit = parseFloat(dbCourse.CREDIT || dbCourse.CREDVAL || 3);
        const repDb = Object.assign({}, dbCourse, {
            COURSE: did, CORE_TE: 'REP',
            'PRE-REQUISITE': origCid, 'CO-REQUISITE': '', '_isRepeat': true
        });
        coursesData[did] = repDb;
        const div = document.createElement('div');
        div.id = `course_rep_${did}`;
        div.className = 'course-box border-rep';
        div.dataset.credit = credit;
        div.dataset.courseId = baseCid;
        div.dataset.displayId = did;
        div.dataset.isRepeat = 'true';
        div.draggable = true;
        div.ondragstart = window.drag;
        const title = dbCourse.TITLE || '';
        const termBadges = getTermsBadges(dbCourse);
        const isPreFor = (window._isPreReqFor?.[baseCid] || []).join(', ') || 'None';
        div.innerHTML = `
            <input type="checkbox" class="c-checkbox" onclick="window.toggleCoursePin(this)">
            <div class="c-headline">
                <span class="c-code">${did} (${credit}cr)</span>
                <span class="rep-label">REP</span>
                <span class="c-title">${title}</span>
            </div>
            <div class="c-meta">
                <span class="c-type">[REP]</span>
                <div class="c-badges">${termBadges}</div>
            </div>
            <div class="c-reqs">
                <div><b>PRE-req:</b> ${origCid}&nbsp;&nbsp;||&nbsp;&nbsp;<b>CO-req:</b> None</div>
                <div><b>is pre for:</b> ${isPreFor}&nbsp;&nbsp;||&nbsp;&nbsp;<b>is co for:</b> None</div>
            </div>`;
        div.onclick = () => window.showCourseInfo(baseCid);
        const origPreForSet = window._isPreReqFor[baseCid] || [];
        window._isPreReqFor[did] = [...origPreForSet];
        (window._isPreReqFor[baseCid] = window._isPreReqFor[baseCid] || []).push(did);
        const unalloc = document.getElementById('zone_Unallocated');
        if (unalloc) unalloc.appendChild(div);
        boxMap.set(did, div);
    });

    // Apply placements
    (planObj.placements || []).forEach(p => {
        const box = boxMap.get(normDisplayId(p.displayId));
        const zone = document.getElementById(p.zoneId);
        if (!box || !zone) return;
        // Don't move taken courses
        if (box.classList.contains('course-taken')) return;

        zone.appendChild(box);
        if (p.pinned) {
            box.dataset.pinned = 'true';
            box.classList.add('pinned');
            const cb = box.querySelector('.c-checkbox');
            if (cb && !cb.disabled) cb.checked = true;
        } else {
            delete box.dataset.pinned;
            box.classList.remove('pinned');
            const cb = box.querySelector('.c-checkbox');
            if (cb && !cb.disabled) cb.checked = false;
        }
    });

    // Restore reason + justification if present
    if (planObj.reason_code !== undefined && planObj.reason_code !== null) {
        const r = document.querySelector(`input[name="submissionReason"][value="${planObj.reason_code}"]`);
        if (r) r.checked = true;
    }
    if (planObj.justification && document.getElementById('justificationText')) {
        document.getElementById('justificationText').value = planObj.justification;
    }

    window.updateCredits();
    setTimeout(() => window.validateGrid && window.validateGrid(), 0);

    // Re-enable submit button (in case it was grayed out from a previous PENDING load)
    const btnSubmit = document.getElementById('btnSubmitApproval');
    if (btnSubmit) {
        btnSubmit.disabled = false;
        btnSubmit.style.opacity = '1';
        btnSubmit.style.cursor = 'pointer';
    }
    
    // Set flag to prevent auto-check CO-OP from triggering after load
    window._justLoadedPlan = true;
    setTimeout(() => { delete window._justLoadedPlan; }, 100);

    
    // Restore inline handlers using setAttribute
    if (startYearEl && startYearHandler) startYearEl.setAttribute('onchange', startYearHandler);
    if (coopCb && coopHandler) coopCb.setAttribute('onchange', coopHandler);
    if (coopStartYearEl && coopStartYearHandler) coopStartYearEl.setAttribute('onchange', coopStartYearHandler);
    if (coopStartTermEl && coopStartTermHandler) coopStartTermEl.setAttribute('onchange', coopStartTermHandler);
    if (programEl && programHandler) programEl.setAttribute('onchange', programHandler);
};

async function apiJson(url, method = 'GET', body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const resp = await fetch(url, opts);
    if (!resp.ok) {
        // Any 401 from API = session expired or not logged in → redirect to login
        if (resp.status === 401) {
            alert('Your session has expired. You will be redirected to login.\nYour work has NOT been lost — after logging in, use Load to recover your latest draft.');
            window.location.href = '/login';
            throw new Error('Session expired');
        }
        const t = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${t}`);
    }
    return await resp.json();
}

window.saveDraft = async function() {
    // Generate default name with current date and time
    const now = new Date();
    const defaultName = `Draft ${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
    
    // Prompt user for sequence name
    const sequenceName = prompt('Enter a name for this sequence:', defaultName);
    
    // If user cancels, don't save
    if (sequenceName === null) {
        return;
    }
    
    // Use the entered name or default if empty
    const finalName = sequenceName.trim() || defaultName;
    
    showSpinner('Saving draft…');
    try {
        const plan = collectPlanSnapshot();
        const payload = {
            status: "DRAFT",
            name: finalName,
            plan,
            issues: currentIssues(),
            reason_code: getSelectedReasonCode(),
            justification: getJustificationText(),
            term_summary: buildEmailTermSummary()
        };
        const res = await apiJson('/api/sequence/save', 'POST', payload);
        hideSpinner();
        alert(`Saved draft: "${finalName}"\nID: ${res.sequence_id}`);
    } catch (e) {
        hideSpinner();
        console.error(e);
        alert(`Save failed: ${e.message}`);
    }
};

window.handleLogout = async function(event) {
    event.preventDefault();
    
    const isPowerUser = window.APP_CONFIG?.isPowerUser || false;
    
    // For non-power users, auto-save before logout
    if (!isPowerUser) {
        const confirmLogout = confirm('Save your current work before logging out?');
        
        if (confirmLogout) {
            try {
                // Auto-save with timestamp name
                const now = new Date();
                const autoSaveName = `Auto-save on logout ${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
                
                showSpinner('Saving before logout…');
                
                const plan = collectPlanSnapshot();
                const payload = {
                    status: "DRAFT",
                    name: autoSaveName,
                    plan,
                    issues: currentIssues(),
                    reason_code: getSelectedReasonCode(),
                    justification: getJustificationText(),
                    term_summary: buildEmailTermSummary()
                };
                
                await apiJson('/api/sequence/save', 'POST', payload);
                hideSpinner();
                
                // Redirect to logout after successful save
                window.location.href = '/logout';
            } catch (e) {
                hideSpinner();
                console.error(e);
                const proceedAnyway = confirm(`Save failed: ${e.message}\n\nDo you want to logout anyway?`);
                if (proceedAnyway) {
                    window.location.href = '/logout';
                }
            }
        } else {
            // User chose not to save, logout directly
            window.location.href = '/logout';
        }
    } else {
        // Power users logout directly without auto-save
        window.location.href = '/logout';
    }
};

window.loadPlan = async function() {
    showSpinner('Loading sequences…');
    try {
        const res = await apiJson('/api/sequence/list');
        const seq = res.sequences || [];
        hideSpinner();
        if (!seq.length) { alert('No saved sequences found.'); return; }

        // Numbered list descending by date (server already returns DESC)
        const lines = seq.slice(0, 15).map((s, i) => {
            const dt = String(s.updated_at || '').replace('T', ' ').substring(0, 16);
            const nm = s.name || 'Plan';
            return `${i + 1}. ${nm} — ${s.status} — ${dt}`;
        });
        const chosen = prompt(`Enter number to load:\n\n${lines.join('\n')}\n\n(${seq.length} total, showing latest ${lines.length})`);
        if (!chosen) return;

        // Accept "1" or "1."
        const idx = parseInt(String(chosen).replace(/\.$/, '').trim(), 10) - 1;
        if (isNaN(idx) || idx < 0 || idx >= seq.length) { alert('Invalid selection.'); return; }

        showSpinner('Loading plan…');
        const selected = seq[idx];
        const item = await apiJson(`/api/sequence/get/${encodeURIComponent(selected.id)}`);
        if (!item.plan) { hideSpinner(); alert('Selected sequence has no plan data.'); return; }
        item.plan.reason_code = item.reason_code;
        item.plan.justification = item.justification;
        
        sessionStorage.setItem('_skipAutoLoad', '1');
        window.applyLoadedPlan(item.plan);
        hideSpinner();
    } catch (e) {
        hideSpinner();
        console.error(e);
        alert(`Load failed: ${e.message}`);
    }
};

function buildEmailTermSummary() {
    const termSummary = [];
    const startYear = document.getElementById('startYear')?.value;
    const coopTerms = Array.isArray(window.APP_CONFIG?.coopTerms) ? window.APP_CONFIG.coopTerms : [];

    if (!startYear) return termSummary;

    const baseYear = parseInt(startYear.split('-')[0], 10);

    for (let y = 1; y <= 7; y++) {
        const rowYear = `${baseYear + y - 1}-${baseYear + y}`;
        const rowData = {};

        ['Summer', 'Fall', 'Winter'].forEach(season => {
            const zid = `zone_${rowYear}_${season}`;
            const zone = document.getElementById(zid);
            const tKey = season === 'Summer' ? 'SUM' : season === 'Fall' ? 'FALL' : 'WIN';

            const ct = coopTerms.find(t => t.year === rowYear && t.season === season);
            const coopLabel = ct ? String(ct.type || '') : '';
            const coopKind = coopLabel.startsWith('W') ? 'work' : (coopLabel.startsWith('S') ? 'study' : '');

            if (!zone) {
                rowData[tKey] = { cr: 0, courses: [], coop_label: coopLabel, coop_kind: coopKind };
                return;
            }

            let cr = 0;
            const courses = [];
            Array.from(zone.children).forEach(box => {
                if (!box.classList.contains('course-box')) return;
                const c = parseFloat(box.dataset.credit || 0);
                cr += c;
                const did = box.dataset.displayId || box.dataset.courseId || '';
                const grade = box.dataset.grade || '';
                courses.push({
                    name: did,
                    credit: c,
                    is_wt: box.classList.contains('wt'),
                    grade: grade
                });
            });

            rowData[tKey] = {
                cr: Math.round(cr * 10) / 10,
                courses,
                coop_label: coopLabel,
                coop_kind: coopKind
            };
        });

        const hasAnything = Object.values(rowData).some(d => d.courses.length > 0);
        if (hasAnything) {
            termSummary.push({ year: rowYear, data: rowData });
        }
    }

    return termSummary;
}

window.submitForApproval = async function() {
    if (window._submitInProgress) return; // prevent double-submit
    const reason = getSelectedReasonCode();
    const just = getJustificationText();
    const issues = currentIssues();
    const hasErrors = issues && issues.some(i => i.sev === 'error');

    if (reason === null) {
        alert('Please select a submission reason (0–10).');
        return;
    }
    if ((reason === 9 || hasErrors) && !just) {
        alert('Justification is required (because you selected reason #9 or there are Errors).');
        return;
    }

    if (hasErrors) {
        const origText = String(document.getElementById('justificationText')?.dataset?.originalText || '');
        if (Math.abs(just.length - origText.length) < 4) {
            alert('Please add your justification comments after each issue. Your text must differ from the auto-generated template.');
            return;
        }
    }

    window._submitInProgress = true;
    const btnEl = document.getElementById('btnSubmitApproval');
    if (btnEl) btnEl.disabled = true;

    showSpinner('Submitting for approval…');
    try {
        const plan = collectPlanSnapshot();
        // Strip warning lines from justification (keep student comments if any)
        const cleanedJust = stripWarningsFromJustification(just);
        const payload = {
            status: "PENDING_APPROVAL",
            plan,
            issues,
            reason_code: reason,
            justification: cleanedJust,
            term_summary: buildEmailTermSummary()
        };
        const res = await apiJson('/api/sequence/save', 'POST', payload);

        // restul rămâne la fel

        // Backend now handles adding justification to public notes before sending email
        // Update the UI to show the justification was added
        if (cleanedJust) {
            try {
                const now = new Date();
                const pad = n => String(n).padStart(2, '0');
                const dt = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
                const name = window.APP_CONFIG?.studentName || window.APP_CONFIG?.viewingSid || '';
                
                // Format justification based on reason code
                let formattedJust = cleanedJust;
                if (reason === 4 || reason === 5 || reason === 6 || reason === 10) {
                    formattedJust = `DETAILS:\n${cleanedJust}`;
                } else {
                    formattedJust = `Justification:\n${cleanedJust}`;
                }
                
                const existing = String(document.getElementById('publicNotes')?.value || '').trim();
                const newComment = `[${dt}, ${name}]:\n${formattedJust}${existing ? '\n\n' + existing : ''}`;
                // Update UI only (backend already saved it)
                const pubEl = document.getElementById('publicNotes');
                if (pubEl) pubEl.value = newComment;
            } catch (ne) {
                console.warn('Could not update public notes UI:', ne.message);
            }
        }

        hideSpinner();
        alert(`Submitted for approval. ID: ${res.sequence_id}`);
    } catch (e) {
        hideSpinner();
        console.error(e);
        alert(`Submit failed: ${e.message}`);
    } finally {
        window._submitInProgress = false;
        const btnEl2 = document.getElementById('btnSubmitApproval');
        if (btnEl2) btnEl2.disabled = false;
    }
};

// =========================================================
// NOTES (Public/Private)
// =========================================================
window.showNotesTab = function(which) {
    const pub = document.getElementById('publicNotes');
    const priv = document.getElementById('privateNotes');
    const tPub = document.getElementById('tabPublicNotes');
    const tPriv = document.getElementById('tabPrivateNotes');
    if (!pub || !priv || !tPub || !tPriv) return;

    const isAdmin = !!window.APP_CONFIG?.isPowerUser;

    if (which === 'private' && !isAdmin) {
        // non-admin: stay on public
        which = 'public';
    }

    if (which === 'public') {
        pub.style.display = '';
        priv.style.display = 'none';
        tPub.classList.add('active');
        tPriv.classList.remove('active');
    } else {
        pub.style.display = 'none';
        priv.style.display = '';
        tPub.classList.remove('active');
        tPriv.classList.add('active');
    }
};

let _notesDebounce = null;

window.loadNotes = async function() {
    try {
        const isAdmin = !!window.APP_CONFIG?.isPowerUser;
        const res = await apiJson('/api/comments', 'GET');

        const pub  = document.getElementById('publicNotes');
        const priv = document.getElementById('privateNotes');

        if (pub)  pub.value  = res.public_comment  || '';
        if (priv) priv.value = res.private_comment || '';

        // Students: public notes are read-only
        if (!isAdmin && pub) pub.readOnly = true;

        // Rerun autosize after programmatic value set
        if (window._autosizeAll) window._autosizeAll();

        // Admins: auto-save on change (debounced)
        if (isAdmin) {
            const handler = () => {
                clearTimeout(_notesDebounce);
                _notesDebounce = setTimeout(window.saveNotes, 500);
            };
            if (pub)  pub.addEventListener('input', handler);
            if (priv) priv.addEventListener('input', handler);
        }
    } catch (e) {
        console.error('Load notes failed', e);
    }
};

window.saveNotes = async function() {
    try {
        const isAdmin = !!window.APP_CONFIG?.isPowerUser;
        if (!isAdmin) return;

        const pub = String(document.getElementById('publicNotes')?.value || '');
        const priv = String(document.getElementById('privateNotes')?.value || '');
        await apiJson('/api/comments', 'POST', { public_comment: pub, private_comment: priv });
    } catch (e) {
        console.error('Save notes failed', e);
    }
};

// =========================================================
// ADMIN tools (pending approvals + view SID)
// =========================================================
window.adminViewStudent = async function() {
    const sid = prompt('Enter Student ID to view:');
    if (!sid) return;
    try {
        await apiJson('/api/admin/view_sid', 'POST', { student_id: sid.trim() });
        window.location.href = '/planner';
    } catch (e) {
        console.error(e);
        alert(`Cannot switch view: ${e.message}`);
    }
};

window.openPendingApprovals = async function() {
    try {
        const res = await apiJson('/api/admin/pending', 'GET');
        const pending = res.pending || [];
        if (!pending.length) { alert('No pending approvals.'); return; }

        const lines = pending.slice(0, 20).map((p, i) => {
            const dt = String(p.updated_at || p.id || '').substring(0, 16);
            return `${i + 1}. SID ${p.student_id} — ${p.name || 'Plan'} — ${dt}`;
        });
        const chosen = prompt(`Enter number to open:\n\n${lines.join('\n')}\n\n(${pending.length} total, showing latest ${lines.length})`);
        if (!chosen) return;

        const idx = parseInt(String(chosen).replace(/\.$/, '').trim(), 10) - 1;
        if (isNaN(idx) || idx < 0 || idx >= pending.length) { alert('Invalid selection.'); return; }
        const item = pending[idx];

        // Switch server-side view, then open planner pre-loaded with this submission
        await apiJson('/api/admin/view_sid', 'POST', { student_id: item.student_id });
        window.location.href = `/planner?load_seq_id=${encodeURIComponent(item.id)}`;
    } catch (e) {
        console.error(e);
        alert(`Pending approvals failed: ${e.message}`);
    }
};



// =========================================================
// STUDENT DETAILS POPUP
// =========================================================
window.showStudentDetails = async function() {
    const studentId = window.APP_CONFIG?.viewingSid || window.APP_CONFIG?.studentId;
    if (!studentId) {
        alert('No student selected');
        return;
    }
    
    try {
        const res = await apiJson('/api/admin/student_details');
        if (!res.ok) {
            alert('Failed to load student details: ' + (res.error || 'Unknown error'));
            return;
        }
        
        // Create popup window
        const popup = window.open('', 'StudentDetails', 'width=1200,height=800,scrollbars=yes,resizable=yes');
        if (!popup) {
            alert('Popup blocked. Please allow popups for this site.');
            return;
        }
        
        // Build HTML for the popup
        const html = `
<!DOCTYPE html>
<html>
<head>
    <title>Student Details - ${res.student_id}</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background: #f5f5f5;
        }
        h1 {
            color: #912338;
            border-bottom: 3px solid #912338;
            padding-bottom: 10px;
        }
        h2 {
            color: #333;
            margin-top: 30px;
            background: #912338;
            color: white;
            padding: 10px;
            border-radius: 4px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        th {
            background: #34495e;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: bold;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        td {
            padding: 10px 12px;
            border-bottom: 1px solid #ddd;
        }
        tr:hover {
            background: #f8f9fa;
        }
        .empty {
            text-align: center;
            color: #999;
            font-style: italic;
            padding: 20px;
        }
        .count {
            color: #666;
            font-size: 14px;
            margin-left: 10px;
        }
    </style>
</head>
<body>
    <h1>📊 Student Details: ${res.student_id}</h1>
    
    <h2>CO-OP Data <span class="count">(${res.coop.length} rows)</span></h2>
    ${buildTable(res.coop)}
    
    <h2>Transcripts <span class="count">(${res.transcripts.length} rows)</span></h2>
    ${buildTable(res.transcripts)}
    
    <h2>CGPA Timeline <span class="count">(${res.cgpa_timeline.length} rows)</span></h2>
    ${buildTable(res.cgpa_timeline)}
</body>
</html>
        `;
        
        popup.document.write(html);
        popup.document.close();
        
    } catch (e) {
        console.error('Student details error:', e);
        alert('Error loading student details: ' + e.message);
    }
};

function buildTable(data) {
    if (!data || data.length === 0) {
        return '<div class="empty">No data available</div>';
    }
    
    // Get all unique column names
    const columns = [...new Set(data.flatMap(row => Object.keys(row)))];
    
    let html = '<table><thead><tr>';
    columns.forEach(col => {
        html += `<th>${escapeHtml(col)}</th>`;
    });
    html += '</tr></thead><tbody>';
    
    data.forEach(row => {
        html += '<tr>';
        columns.forEach(col => {
            const val = row[col];
            html += `<td>${val !== null && val !== undefined ? escapeHtml(String(val)) : ''}</td>`;
        });
        html += '</tr>';
    });
    
    html += '</tbody></table>';
    return html;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}


// =========================================================
// STUDENT EMAIL HISTORY POPUP
// =========================================================
window.showStudentEmails = async function() {
    const studentId = window.APP_CONFIG?.viewingSid || window.APP_CONFIG?.studentId;
    if (!studentId) {
        alert('No student selected');
        return;
    }
    
    try {
        const res = await apiJson('/api/admin/student_emails');
        if (!res.ok) {
            alert('Failed to load email history: ' + (res.error || 'Unknown error'));
            return;
        }
        
        // Create popup window
        const popup = window.open('', 'EmailHistory', 'width=1000,height=700,scrollbars=yes,resizable=yes');
        if (!popup) {
            alert('Popup blocked. Please allow popups for this site.');
            return;
        }
        
        // Build HTML for the popup
        const html = `
<!DOCTYPE html>
<html>
<head>
    <title>Email History - ${res.student_id}</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background: #f5f5f5;
        }
        h1 {
            color: #912338;
            border-bottom: 3px solid #912338;
            padding-bottom: 10px;
        }
        .email-list {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .email-item {
            padding: 15px;
            border-bottom: 1px solid #eee;
            cursor: pointer;
            transition: background 0.2s;
        }
        .email-item:hover {
            background: #f8f9fa;
        }
        .email-item:last-child {
            border-bottom: none;
        }
        .email-date {
            color: #666;
            font-size: 12px;
            margin-bottom: 5px;
        }
        .email-subject {
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }
        .email-meta {
            font-size: 12px;
            color: #888;
        }
        .email-detail {
            display: none;
            margin-top: 15px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 4px;
            border-left: 4px solid #912338;
        }
        .email-detail.active {
            display: block;
        }
        .empty {
            text-align: center;
            color: #999;
            font-style: italic;
            padding: 40px;
        }
        .count {
            color: #666;
            font-size: 14px;
            margin-left: 10px;
        }
    </style>
</head>
<body>
    <h1>📧 Email History: ${res.student_id} <span class="count">(${res.emails.length} emails)</span></h1>
    
    <div class="email-list">
        ${buildEmailList(res.emails)}
    </div>
    
    <script>
        function toggleEmail(id) {
            const detail = document.getElementById('detail-' + id);
            if (detail) {
                detail.classList.toggle('active');
            }
        }
    </script>
</body>
</html>
        `;
        
        popup.document.write(html);
        popup.document.close();
        
    } catch (e) {
        console.error('Email history error:', e);
        alert('Error loading email history: ' + e.message);
    }
};

function buildEmailList(emails) {
    if (!emails || emails.length === 0) {
        return '<div class="empty">No emails found for this student</div>';
    }
    
    // Sort by date descending
    emails.sort((a, b) => new Date(b.date) - new Date(a.date));
    
    let html = '';
    emails.forEach((email, index) => {
        const date = new Date(email.date);
        const dateStr = date.toLocaleString();
        const term = getTermFromDate(date);
        
        html += `
            <div class="email-item" onclick="toggleEmail(${index})">
                <div class="email-date">${dateStr} ${term ? `— ${term}` : ''}</div>
                <div class="email-subject">${escapeHtml(email.subject)}</div>
                <div class="email-meta">
                    From: ${escapeHtml(email.from)} → To: ${escapeHtml(email.to.join(', '))}
                </div>
                <div id="detail-${index}" class="email-detail">
                    ${email.content || '<em>No content available</em>'}
                </div>
            </div>
        `;
    });
    
    return html;
}

function getTermFromDate(date) {
    const month = date.getMonth() + 1; // 1-12
    const year = date.getFullYear();
    
    let term = '';
    let acaYear = '';
    
    if (month >= 5 && month <= 8) {
        term = 'Summer';
        acaYear = `${year}-${year + 1}`;
    } else if (month >= 9 && month <= 12) {
        term = 'Fall';
        acaYear = `${year}-${year + 1}`;
    } else { // 1-4
        term = 'Winter';
        acaYear = `${year - 1}-${year}`;
    }
    
    return `${term} ${acaYear}`;
}
