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

    // Pre-fill editable text fields from data attributes
    document.getElementById('emailTitle').value   = selected.getAttribute('data-what');
    document.getElementById('emailMessage').value  = selected.getAttribute('data-msg');
    document.getElementById('shortMessage').value  = selected.getAttribute('data-short');

    document.getElementById('loadingOverlay').style.display = 'flex';
    document.getElementById('resultsTable').style.display   = 'none';

    // Show/hide Deviated Courses column based on check_id
    const checkId = selected.value;
    const deviatedCoursesHeader = document.getElementById('deviatedCoursesHeader');
    const showDeviatedCourses = (checkId === '7');
    deviatedCoursesHeader.style.display = showDeviatedCourses ? '' : 'none';

    try {
        const res = await fetch('/api/admin_run_check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ check_id: selected.value })
        });
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
            
            tr.innerHTML = `
                <td style="text-align:center;"><input type="checkbox" name="studentCheck" value="${s.id}" checked></td>
                <td style="font-weight:bold; color:#2980b9;">${s.name}</td>
                <td style="font-size:11px;">${s.program}</td>
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
    const extraMsg = includeInst
        ? "\n\n⚠️ WT IMPACTED - Operations Institute are added to the email"
        : "\n\n✅ Institute Operations not included - no restrictions on WT";

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
                    include_institute: includeInst
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
