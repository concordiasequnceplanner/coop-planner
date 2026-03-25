// =========================================================
// MIAE ACADEMIC PLANNER — admin_checks.js
// =========================================================

function toggleAll(source) {
    const checkboxes = document.getElementsByName('studentCheck');
    for (let i = 0; i < checkboxes.length; i++) {
        checkboxes[i].checked = source.checked;
    }
}

async function loadCheckData() {
    const selected = document.querySelector('input[name="checkOption"]:checked');
    if (!selected) return;

    const checkId = selected.value;

    // Check 7 and 8 are special — show their panels, hide normal table
    const check7Panel = document.getElementById('check7Panel');
    const check8Panel = document.getElementById('check8Panel');
    check7Panel.style.display = 'none';
    check8Panel.style.display = 'none';

    if (checkId === '7') {
        check7Panel.style.display = 'block';
        document.getElementById('resultsTable').style.display = 'none';
        document.getElementById('studentCountDisplay').style.display = 'none';
        document.querySelector('.admin-email-panel').style.display = '';
        document.getElementById('loadingOverlay').style.display = 'none';
        // Pre-fill email fields from data attributes
        document.getElementById('emailTitle').value   = selected.getAttribute('data-what') || '';
        document.getElementById('emailMessage').value  = selected.getAttribute('data-msg') || '';
        document.getElementById('shortMessage').value  = selected.getAttribute('data-short') || '';
        return;
    }
    if (checkId === '8') {
        check8Panel.style.display = 'block';
        document.getElementById('resultsTable').style.display = 'none';
        document.getElementById('studentCountDisplay').style.display = 'none';
        document.querySelector('.admin-email-panel').style.display = 'none';
        document.getElementById('loadingOverlay').style.display = 'none';
        return;
    }
    document.querySelector('.admin-email-panel').style.display = '';

    // Pre-fill editable text fields from data attributes
    document.getElementById('emailTitle').value   = selected.getAttribute('data-what');
    document.getElementById('emailMessage').value  = selected.getAttribute('data-msg');
    document.getElementById('shortMessage').value  = selected.getAttribute('data-short');

    document.getElementById('loadingOverlay').style.display = 'flex';
    document.getElementById('resultsTable').style.display   = 'none';

    // Show/hide Deviated Courses column based on check_id
    const deviatedCoursesHeader = document.getElementById('deviatedCoursesHeader');
    const coopProgramHeader = document.getElementById('coopProgramHeader');
    const currentCoursesHeader = document.getElementById('currentCoursesHeader');
    const showDeviatedCourses = (checkId === '7');
    const showCoopProgram = (checkId === '6');
    const showCurrentCourses = (checkId === '6');
    deviatedCoursesHeader.style.display = showDeviatedCourses ? '' : 'none';
    coopProgramHeader.style.display = showCoopProgram ? '' : 'none';
    currentCoursesHeader.style.display = showCurrentCourses ? '' : 'none';

    try {
        const res = await fetch('/api/admin_run_check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ check_id: selected.value })
        });
        
        if (!res.ok) {
            const errorData = await res.json().catch(() => ({}));
            if (errorData.error_type === 'disk_space') {
                alert('⚠️ DATABASE SERVER DISK FULL\n\n' + errorData.error + '\n\nPlease try again later or contact support.');
            } else {
                alert('Error loading data: ' + (errorData.error || 'Server error'));
            }
            document.getElementById('loadingOverlay').style.display = 'none';
            return;
        }
        
        const currentStudents = await res.json();

        // Update count display
        const countDisplay = document.getElementById('studentCountDisplay');
        countDisplay.innerText = `🔍 Found ${currentStudents.length} students for this filter.`;
        countDisplay.style.display = 'block';

        // Render table rows
        const tbody = document.getElementById('studentsTableBody');
        tbody.innerHTML = '';
        currentStudents.forEach(s => {
            const tr = document.createElement('tr');
            
            // Build deviated courses cell if applicable
            let deviatedCoursesCell = '';
            if (showDeviatedCourses && s.deviated_courses) {
                deviatedCoursesCell = `<td style="font-size:11px; text-align:left; background:#fff8e1; padding:8px; white-space:pre-wrap; word-wrap:break-word; max-width:400px; overflow-y:auto; max-height:200px; font-family:monospace;">${s.deviated_courses}</td>`;
            } else if (showDeviatedCourses) {
                deviatedCoursesCell = '<td></td>';
            }
            
            // Build coop program cell if applicable (for Check 6)
            let coopProgramCell = '';
            if (showCoopProgram && s.coop_program) {
                coopProgramCell = `<td style="font-size:12px; font-weight:bold; color:#16a085; text-align:center;">${s.coop_program}</td>`;
            } else if (showCoopProgram) {
                coopProgramCell = '<td></td>';
            }
            
            // Build current courses cell if applicable (for Check 6)
            let currentCoursesCell = '';
            if (showCurrentCourses && s.current_courses) {
                // Process courses to highlight CWTE and WILE with blue background
                const courses = s.current_courses.split('<br>');
                const processedCourses = courses.map(course => {
                    const trimmedCourse = course.trim();
                    if (trimmedCourse.startsWith('CWTE') || trimmedCourse.startsWith('WILE')) {
                        return `<span style="background:#5dade2; color:white; padding:2px 6px; border-radius:3px; display:inline-block; margin:2px 0;">${trimmedCourse}</span>`;
                    }
                    return `<span style="display:inline-block; margin:2px 0;">${trimmedCourse}</span>`;
                }).join('<br>');
                
                currentCoursesCell = `<td style="font-size:11px; text-align:left; background:#e8f8f5; padding:8px; max-width:200px; vertical-align:top;">${processedCourses}</td>`;
            } else if (showCurrentCourses) {
                currentCoursesCell = '<td></td>';
            }
            
            tr.innerHTML = `
                <td style="text-align:center;"><input type="checkbox" name="studentCheck" value="${s.id}" checked></td>
                <td style="font-weight:bold; color:#2980b9;">${s.name}</td>
                <td style="font-size:11px;">${s.program}</td>
                ${coopProgramCell}
                ${currentCoursesCell}
                <td style="font-size:12px;">${s.email}</td>
                <td>${s.id}</td>
                <td style="font-weight:bold; color:#c0392b;">${s.cgpa}</td>
                <td>${s.cgpa_cr}</td>
                <td style="font-weight:bold; color:#e67e22;">${s.gpa24}</td>
                <td>${s.gpa24_cr}</td>
                <td style="font-size:11px; white-space:nowrap; text-align:left;">${s.wts}</td>
                ${deviatedCoursesCell}
                <td style="font-size:11px; text-align:left; background:#f9fff9; padding:8px; white-space:pre-wrap; word-wrap:break-word; max-width:300px; overflow-y:auto; max-height:150px;">${s.notes_vis}</td>
                <td style="font-size:11px; text-align:left; background:#fdf2f2; padding:8px; white-space:pre-wrap; word-wrap:break-word; max-width:300px; overflow-y:auto; max-height:150px;">${s.notes_invis}</td>`;
            tbody.appendChild(tr);
        });

        document.getElementById('resultsTable').style.display = 'table';
    } catch (e) {
        alert("Error loading data: " + e);
    } finally {
        document.getElementById('loadingOverlay').style.display = 'none';
    }
}

async function sendBulkEmails() {
    const selected = document.querySelector('input[name="checkOption"]:checked');
    if (!selected) return alert("Select a check first!");

    const sids = Array.from(document.querySelectorAll('input[name="studentCheck"]:checked')).map(cb => cb.value);
    if (sids.length === 0) return alert("No students selected!");

    const body    = document.getElementById('emailMessage').value;
    const short   = document.getElementById('shortMessage').value;
    const subject = document.getElementById('emailTitle').value;

    const includeInst = document.getElementById('chkInstAdmin').checked;
    const includeCoopReseq = document.getElementById('chkCoopReseq').checked;
    
    let extraMsg = "";
    if (includeInst && includeCoopReseq) {
        extraMsg = "\n\n⚠️ WT IMPACTED - Operations Institute AND Coop Resequence are added to the email";
    } else if (includeInst) {
        extraMsg = "\n\n⚠️ WT IMPACTED - Operations Institute are added to the email";
    } else if (includeCoopReseq) {
        extraMsg = "\n\n⚠️ WT IMPACTED - Coop Resequence are added to the email";
    } else {
        extraMsg = "\n\n✅ No WT restrictions - standard email";
    }

    if (!confirm(`Are you sure you want to send emails to ${sids.length} students? This may take a few minutes.` + extraMsg)) return;

    const loadingText = document.getElementById('loadingText');
    document.getElementById('loadingOverlay').style.display = 'flex';

    const batchSize = 15;
    let successCount = 0;
    let errorCount   = 0;

    try {
        for (let i = 0; i < sids.length; i += batchSize) {
            const batchSids = sids.slice(i, i + batchSize);

            loadingText.innerText = `⏳ Sending emails... (${Math.min(i + batchSize, sids.length)} of ${sids.length})`;

            const res = await fetch('/api/admin_bulk_email', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    student_ids: batchSids,
                    message: body,
                    short_msg: short,
                    subject: subject,
                    include_institute: includeInst,
                    include_coop_reseq: includeCoopReseq
                })
            });

            if (res.ok) {
                successCount += batchSids.length;
            } else {
                errorCount += batchSids.length;
                console.error("Error in batch: ", batchSids);
            }
        }

        alert(`✅ Process complete! Sent successfully: ${successCount}. Errors: ${errorCount}.`);
    } catch (e) {
        alert("❌ Connection interrupted or server error.");
    } finally {
        loadingText.innerText = "⏳ Running query across database... Please wait.";
        document.getElementById('loadingOverlay').style.display = 'none';
        loadCheckData(); // Refresh table
    }
}


// =========================================================
// CHECK 7: Students Needing WT Attention
// =========================================================
async function runCheck7() {
    document.getElementById('loadingOverlay').style.display = 'flex';
    document.getElementById('check7Results').style.display = 'none';

    try {
        const res = await fetch('/api/admin_check_wt_attention', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();
        if (!data.ok) {
            alert('Error: ' + (data.error || 'Unknown error'));
            return;
        }

        const resultsEl = document.getElementById('check7Results');
        resultsEl.innerHTML = '';

        const students = data.students || [];
        const summary = document.createElement('div');
        summary.style.cssText = 'font-weight:bold; color:#2c3e50; margin-bottom:10px;';
        summary.innerHTML = `🔍 Found <span style="color:#912338;">${students.length}</span> student${students.length !== 1 ? 's' : ''} with 2 or 3 WTs in the future, no approved sequence`;
        resultsEl.appendChild(summary);

        if (students.length === 0) {
            resultsEl.innerHTML += '<p style="color:#888; font-style:italic;">All students with future WTs have an approved sequence.</p>';
        } else {
            const thStyle = 'padding:6px 10px;text-align:left;border-bottom:2px solid #bdc3c7;font-size:12px;';
            let html = `<table class="wt-movement-table" style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr style="background:#ecf0f1;">
                <th style="${thStyle}width:30px;"><input type="checkbox" checked onclick="document.querySelectorAll('#check7Results input[name=studentCheck]').forEach(c=>c.checked=this.checked)"></th>
                <th style="${thStyle}width:100px;">Student ID</th>
                <th style="${thStyle}">Name</th>
                <th style="${thStyle}">Email</th>
                <th style="${thStyle}width:70px;">GPA24</th>
                <th style="${thStyle}width:70px;">CGPA</th>
                <th style="${thStyle}width:70px;">Credits</th>
                <th style="${thStyle}">WT1</th>
                <th style="${thStyle}">WT2</th>
                <th style="${thStyle}">WT3</th>
                <th style="${thStyle}width:80px;">Seq Status</th>
            </tr></thead><tbody>`;
            students.forEach((s, i) => {
                const bg = i % 2 === 0 ? '#fff' : '#f9f9f9';
                const wt1 = s.wts.WT1 ? s.wts.WT1.term : '-';
                const wt2 = s.wts.WT2 ? s.wts.WT2.term : '-';
                const wt3 = s.wts.WT3 ? s.wts.WT3.term : '-';
                const wt1Future = s.wts.WT1 ? s.wts.WT1.future : false;
                const wt2Future = s.wts.WT2 ? s.wts.WT2.future : false;
                const wt3Future = s.wts.WT3 ? s.wts.WT3.future : false;
                const pastStyle = 'color:#bbb;';
                const futureStyle = 'color:#2980b9;font-weight:bold;';
                const seqStatus = s.seq_status || 'NONE';
                const seqColor = seqStatus === 'NONE' ? '#e74c3c' : seqStatus === 'DRAFT' ? '#e67e22' : seqStatus === 'PENDING' ? '#2980b9' : seqStatus === 'REWORK' ? '#8e44ad' : '#888';
                const tdS = 'padding:4px 10px;border-bottom:1px solid #eee;';
                html += `<tr style="background:${bg};">
                    <td style="${tdS}"><input type="checkbox" name="studentCheck" value="${s.sid}" checked></td>
                    <td style="${tdS}color:#2980b9;font-weight:bold;cursor:pointer;" onclick="window.open('/planner?switch_to=${s.sid}','_blank')">${s.sid}</td>
                    <td style="${tdS}">${s.name}</td>
                    <td style="${tdS}font-size:11px;">${s.email || ''}</td>
                    <td style="${tdS}">${s.gpa24 || '-'}</td>
                    <td style="${tdS}">${s.cgpa || '-'}</td>
                    <td style="${tdS}">${s.credits || '-'}</td>
                    <td style="${tdS}${wt1Future ? futureStyle : pastStyle}">${wt1}</td>
                    <td style="${tdS}${wt2Future ? futureStyle : pastStyle}">${wt2}</td>
                    <td style="${tdS}${wt3Future ? futureStyle : pastStyle}">${wt3}</td>
                    <td style="${tdS}color:${seqColor};font-weight:bold;font-size:11px;">${seqStatus}</td>
                </tr>`;
            });
            html += '</tbody></table>';
            resultsEl.innerHTML += html;
        }

        resultsEl.style.display = 'block';

    } catch (e) {
        alert('Error: ' + e.message);
    } finally {
        document.getElementById('loadingOverlay').style.display = 'none';
    }
}

// =========================================================
// CHECK 8: WT Movement Analysis
// =========================================================
async function runCheck8() {
    const dateFrom = document.getElementById('check8DateFrom').value || null;
    const dateTo = document.getElementById('check8DateTo').value || null;

    document.getElementById('loadingOverlay').style.display = 'flex';
    document.getElementById('check8Results').style.display = 'none';
    document.getElementById('check8Summary').style.display = 'none';

    try {
        const res = await fetch('/api/admin_check_wt_movements', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date_from: dateFrom, date_to: dateTo })
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            alert('Error: ' + (err.error || 'Server error'));
            return;
        }

        const data = await res.json();
        if (!data.ok) {
            alert('Error: ' + (data.error || 'Unknown error'));
            return;
        }

        // Build date range label
        let rangeLabel = '';
        if (dateFrom && dateTo) rangeLabel = `from ${dateFrom} to ${dateTo}`;
        else if (dateFrom) rangeLabel = `from ${dateFrom} to today`;
        else if (dateTo) rangeLabel = `up to ${dateTo}`;
        else rangeLabel = 'all time';

        const summaryEl = document.getElementById('check8Summary');
        summaryEl.innerHTML = `🔍 Found <span style="color:#912338;">${data.total_approved}</span> approved sequences (${rangeLabel})`;
        summaryEl.style.display = 'block';

        const resultsEl = document.getElementById('check8Results');
        resultsEl.innerHTML = '';

        if (data.total_approved === 0) {
            resultsEl.innerHTML = '<p style="color:#888; font-style:italic;">No approved sequences found in this date range.</p>';
            resultsEl.style.display = 'block';
            return;
        }

        // Build panels for WT1, WT2, WT3
        ['WT1', 'WT2', 'WT3'].forEach(wtKey => {
            const entries = data.wt_movements[wtKey] || [];
            const panel = document.createElement('div');
            panel.style.cssText = 'margin-bottom:20px; border:1px solid #ddd; border-radius:8px; overflow:hidden;';

            // Header (clickable to expand/collapse)
            const totalMoved = entries.reduce((s, e) => s + e.count, 0);
            const header = document.createElement('div');
            header.style.cssText = 'background:#34495e; color:#fff; padding:10px 15px; font-weight:bold; font-size:15px; cursor:pointer; display:flex; justify-content:space-between; align-items:center; gap:10px;';
            const sidsBtnId = `sidsToggle_${wtKey}`;
            header.innerHTML = `<span>▼ ${wtKey}</span><span style="display:flex;align-items:center;gap:8px;"><span id="${sidsBtnId}" style="font-size:11px; background:rgba(255,255,255,0.15); padding:3px 10px; border-radius:12px; cursor:pointer;" onclick="event.stopPropagation(); var els=document.querySelectorAll('.sid-list-${wtKey}'); var show=els[0]&&els[0].style.display==='none'; els.forEach(function(e){e.style.display=show?'block':'none';}); this.textContent=show?'Hide IDs':'Show IDs';">Show IDs</span><span style="font-size:13px; background:rgba(255,255,255,0.2); padding:3px 10px; border-radius:12px;">${totalMoved} movement${totalMoved !== 1 ? 's' : ''}</span></span>`;

            const body = document.createElement('div');
            body.style.cssText = 'padding:0; overflow:hidden;';

            header.onclick = (e) => {
                if (e.target.id === sidsBtnId) return;
                const isHidden = body.style.display === 'none';
                body.style.display = isHidden ? '' : 'none';
                header.querySelector('span').textContent = (isHidden ? '▼ ' : '▶ ') + wtKey;
            };

            if (entries.length === 0) {
                body.innerHTML = '<p style="padding:10px 15px; color:#888; font-style:italic; margin:0;">No movements recorded.</p>';
            } else {
                // Group by from_term
                const grouped = {};
                entries.forEach(e => {
                    if (!grouped[e.from_term]) grouped[e.from_term] = [];
                    grouped[e.from_term].push(e);
                });

                const table = document.createElement('table');
                table.className = 'wt-movement-table';
                table.style.cssText = 'width:100%; border-collapse:collapse; font-size:13px; table-layout:fixed;';
                table.innerHTML = `<thead><tr style="background:#ecf0f1;">
                    <th style="padding:4px 10px; text-align:left; border-bottom:2px solid #bdc3c7; width:250px;">Original Term</th>
                    <th style="padding:4px 10px; text-align:center; border-bottom:2px solid #bdc3c7; width:160px; white-space:nowrap;">Total</th>
                    <th style="padding:4px 10px; text-align:left; border-bottom:2px solid #bdc3c7;">Moved To → Count</th>
                </tr></thead>`;

                const tbody = document.createElement('tbody');
                const fromTerms = Object.keys(grouped).sort((a, b) => {
                    // Sort by year then Summer→Fall→Winter
                    const seasonOrd = { Summer: 1, Fall: 2, Winter: 3 };
                    const [yA, sA] = a.split(' ');
                    const [yB, sB] = b.split(' ');
                    if (yA !== yB) return yA.localeCompare(yB);
                    return (seasonOrd[sA] || 0) - (seasonOrd[sB] || 0);
                });

                fromTerms.forEach((fromTerm, idx) => {
                    const destinations = grouped[fromTerm];
                    const fromTotal = destinations.reduce((s, d) => s + d.count, 0);
                    const bgColor = idx % 2 === 0 ? '#fff' : '#f9f9f9';

                    // Sort destinations by year then Summer→Fall→Winter
                    const seasonOrd2 = { Summer: 1, Fall: 2, Winter: 3 };
                    const sortDest = arr => arr.sort((a, b) => {
                        const [yA, sA] = a.to_term.split(' ');
                        const [yB, sB] = b.to_term.split(' ');
                        if (yA !== yB) return yA.localeCompare(yB);
                        return (seasonOrd2[sA] || 0) - (seasonOrd2[sB] || 0);
                    });
                    sortDest(destinations);

                    // Calculate changed vs no-change (all programs)
                    let noChangeCount = 0;
                    let changedCount = 0;
                    destinations.forEach(d => {
                        if (d.from_term === d.to_term) noChangeCount += d.count;
                        else changedCount += d.count;
                    });
                    const totalHtml = `<span style="font-size:14px; font-weight:bold;"><span style="color:#e67e22;">↗${changedCount}</span> + <span style="color:#27ae60;">✓${noChangeCount}</span> = <span style="color:#912338;">${fromTotal}</span></span>`;

                    // Merge destinations by to_term (sum across programs) for main row
                    const mergedDest = {};
                    destinations.forEach(d => {
                        if (!mergedDest[d.to_term]) mergedDest[d.to_term] = 0;
                        mergedDest[d.to_term] += d.count;
                    });
                    const mergedKeys = Object.keys(mergedDest).sort((a, b) => {
                        const [yA, sA] = a.split(' ');
                        const [yB, sB] = b.split(' ');
                        if (yA !== yB) return yA.localeCompare(yB);
                        return (seasonOrd2[sA] || 0) - (seasonOrd2[sB] || 0);
                    });
                    const destHtml = mergedKeys.map(toTerm => {
                        const isSame = fromTerm === toTerm;
                        const cnt = mergedDest[toTerm];
                        if (isSame) return `<span style="color:#27ae60;">${toTerm} (no change): <b>${cnt}</b></span>`;
                        return `<span style="color:#e67e22; font-weight:bold;">${toTerm}: <b>${cnt}</b></span>`;
                    }).join('&nbsp;&nbsp;│&nbsp;&nbsp;');

                    // Main row
                    const tr = document.createElement('tr');
                    tr.style.cssText = `background:${bgColor}; height:auto;`;
                    tr.innerHTML = `
                        <td style="padding:3px 10px; border-bottom:1px solid #eee; font-weight:bold; color:#2980b9; white-space:nowrap; line-height:1.2;">${fromTerm}</td>
                        <td style="padding:3px 10px; border-bottom:1px solid #eee; text-align:center; font-weight:bold; line-height:1.2; white-space:nowrap;">${totalHtml}</td>
                        <td style="padding:3px 10px; border-bottom:1px solid #eee; line-height:1.2;">${destHtml}</td>`;
                    tbody.appendChild(tr);

                    // Sub-rows per program
                    const byProg = {};
                    destinations.forEach(d => {
                        const p = d.prog || 'UGRD';
                        if (!byProg[p]) byProg[p] = [];
                        byProg[p].push(d);
                    });
                    // Sort: ugrd programs first, then grad
                    const progKeys = Object.keys(byProg).sort((a, b) => {
                        const aGrad = a.toLowerCase().includes('grad');
                        const bGrad = b.toLowerCase().includes('grad');
                        if (aGrad !== bGrad) return aGrad ? 1 : -1;
                        return a.localeCompare(b);
                    });
                    progKeys.forEach(prog => {
                        const pDest = byProg[prog];
                        if (!pDest || pDest.length === 0) return;
                        const pTotal = pDest.reduce((s, d) => s + d.count, 0);
                        let pNoChange = 0, pChanged = 0;
                        pDest.forEach(d => {
                            if (d.from_term === d.to_term) pNoChange += d.count;
                            else pChanged += d.count;
                        });
                        // Merge by to_term for this program, collect sids
                        const pMerged = {};
                        const pSids = {};
                        pDest.forEach(d => {
                            if (!pMerged[d.to_term]) { pMerged[d.to_term] = 0; pSids[d.to_term] = []; }
                            pMerged[d.to_term] += d.count;
                            if (d.sids) d.sids.forEach(s => { if (!pSids[d.to_term].includes(s)) pSids[d.to_term].push(s); });
                        });
                        const pKeys = Object.keys(pMerged).sort((a, b) => {
                            const [yA, sA] = a.split(' ');
                            const [yB, sB] = b.split(' ');
                            if (yA !== yB) return yA.localeCompare(yB);
                            return (seasonOrd2[sA] || 0) - (seasonOrd2[sB] || 0);
                        });
                        const pDestHtml = pKeys.map((toTerm, ti) => {
                            const isSame = fromTerm === toTerm;
                            const cnt = pMerged[toTerm];
                            const sidList = (pSids[toTerm] || []).join(' - ');
                            const togId = `sids_${wtKey}_${idx}_${prog.replace(/\s/g,'')}_${ti}`;
                            const sidToggle = sidList ? `<span style="cursor:pointer;font-size:10px;color:#aaa;margin-left:3px;" onclick="event.stopPropagation();var el=document.getElementById('${togId}');el.style.display=el.style.display==='none'?'block':'none';">▶</span><div id="${togId}" class="sid-list-${wtKey}" style="display:none;font-size:10px;color:#888;margin-top:1px;">${sidList}</div>` : '';
                            if (isSame) return `<span style="color:#27ae60;">${toTerm}: ${cnt}</span>${sidToggle}`;
                            return `<span style="color:#e67e22;">${toTerm}: ${cnt}</span>${sidToggle}`;
                        }).join('&nbsp;&nbsp;│&nbsp;&nbsp;');

                        const isGrad = prog.toLowerCase().includes('grad');
                        const progColor = isGrad ? '#8e44ad' : '#2c3e50';
                        const subTr = document.createElement('tr');
                        subTr.style.cssText = `background:${bgColor}; height:auto;`;
                        subTr.innerHTML = `
                            <td style="padding:2px 10px 2px 25px; border-bottom:1px solid #eee; font-size:12px; color:${progColor}; font-weight:600; line-height:1.3; text-align:right;">${prog}</td>
                            <td style="padding:2px 10px; border-bottom:1px solid #eee; text-align:right; font-size:12px; line-height:1.3; white-space:nowrap;"><span style="color:#e67e22;">↗${pChanged}</span> + <span style="color:#27ae60;">✓${pNoChange}</span> = ${pTotal}</td>
                            <td style="padding:2px 10px; border-bottom:1px solid #eee; font-size:12px; line-height:1.3;">${pDestHtml}</td>`;
                        tbody.appendChild(subTr);
                    });
                });

                table.appendChild(tbody);
                body.appendChild(table);
            }

            panel.appendChild(header);
            panel.appendChild(body);
            resultsEl.appendChild(panel);
        });

        resultsEl.style.display = 'block';

    } catch (e) {
        alert('Error: ' + e.message);
    } finally {
        document.getElementById('loadingOverlay').style.display = 'none';
    }
}

async function backfillOriginalWT() {
    if (!confirm('This will populate Original_WT_JSON for all existing APPROVED sequences. Continue?')) return;
    try {
        document.getElementById('loadingOverlay').style.display = 'flex';
        const res = await fetch('/api/admin_backfill_original_wt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();
        if (data.ok) {
            alert(`Backfill complete: ${data.updated} of ${data.total} sequences updated.`);
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        alert('Error: ' + e.message);
    } finally {
        document.getElementById('loadingOverlay').style.display = 'none';
    }
}
