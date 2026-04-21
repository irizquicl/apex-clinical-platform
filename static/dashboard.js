const TOKEN_KEY = 'apex_token';
const USER_KEY = 'apex_user';

// Setup nav
document.querySelectorAll('[data-view]').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.view').forEach(v => v.style.display = 'none');
        document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
        document.getElementById('view-' + btn.dataset.view).style.display = 'block';
        btn.classList.add('active');
    });
});

async function api(path, method='GET', body=null) {
    const opts = { method, headers: { 'Authorization': 'Bearer ' + localStorage.getItem(TOKEN_KEY) } };
    if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    const r = await fetch(path, opts);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
}

// Minimal mock functions for UI logic to prevent errors
function renderUser() { }
async function loadFacilities() { }
async function refresh() { }
function closePatient() { }

// Add this Care Plan Intelligence functionality
let currentCpFindings = null;
let currentCarePlanId = null;
let currentPatientId = null;

document.getElementById('btnLoadPccPlans')?.addEventListener('click', async () => {
    const patId = document.getElementById('pccPatientSelect').value;
    if (!patId) return alert('Select patient first');
    currentPatientId = patId;
    
    document.getElementById('pccPlansList').innerHTML = '<p>Loading...</p>';
    try {
        const res = await api(`/api/care-plans/patient/${patId}`);
        const plans = res.care_plans || [];
        if (!plans.length) {
            document.getElementById('pccPlansList').innerHTML = '<p>No active care plans.</p>';
            return;
        }
        let html = '';
        plans.forEach(p => {
            html += `<div style="border:1px solid #ccc; padding: 10px; margin-bottom: 10px; cursor:pointer;" onclick="selectCarePlan(${patId}, ${p.care_plan_id})">
                <strong>${p.problem}</strong><br/>
                <small>Status: ${p.status}</small>
            </div>`;
        });
        document.getElementById('pccPlansList').innerHTML = html;
    } catch (e) {
        document.getElementById('pccPlansList').innerHTML = `<p style="color:red">Error: ${e.message}</p>`;
    }
});

window.selectCarePlan = async function(patId, cpId) {
    currentCarePlanId = cpId;
    try {
        const cp = await api(`/api/care-plans/patient/${patId}/${cpId}`);
        const text = `Problem: ${cp.problem}\nGoals: ${cp.goals}\nInterventions: ${cp.interventions}\nDiscipline: ${cp.responsible_discipline}`;
        document.getElementById('careplanInput').value = text;
        currentCpFindings = null;
        document.getElementById('cpReviewContent').innerHTML = '<p class="text-muted">Awaiting review...</p>';
        document.getElementById('cpRewriteContent').innerHTML = '<p class="text-muted">Awaiting rewrite...</p>';
        document.getElementById('cpScoreBadge').textContent = 'Score: —';
        document.getElementById('cpScoreBadge').style.backgroundColor = '#E2E8F0';
    } catch (e) {
        alert(e.message);
    }
};

document.getElementById('btnReviewCarePlan')?.addEventListener('click', async () => {
    const text = document.getElementById('careplanInput').value.trim();
    if (!text) return alert('Please paste a care plan first.');
    
    document.getElementById('btnReviewCarePlan').textContent = 'Reviewing...';
    document.getElementById('cpReviewContent').innerHTML = '<p class="text-muted">Analyzing against F-tags and clinical standards...</p>';
    
    try {
        let res;
        if (currentCarePlanId && currentPatientId) {
            const wrapper = await api(`/api/care-plans/patient/${currentPatientId}/${currentCarePlanId}/auto-review`, 'POST');
            res = wrapper.review;
        } else {
            res = await api('/api/care-plans/review', 'POST', { care_plan_text: text });
        }
        currentCpFindings = res;
        
        // Update badge
        const badge = document.getElementById('cpScoreBadge');
        const score = res.compliance_score || 0;
        badge.textContent = `Score: ${score}`;
        badge.style.color = '#fff';
        if (score < 60) badge.style.backgroundColor = 'var(--red)';
        else if (score < 80) badge.style.backgroundColor = 'var(--amber)';
        else badge.style.backgroundColor = 'var(--green)';
        
        // Update content
        let html = '';
        if (res.deficiencies && res.deficiencies.length > 0) {
            html += '<div style="margin-bottom: 15px;"><strong style="color: var(--red);">Deficiencies Found:</strong><ul style="margin-top:5px; padding-left: 20px;">' + res.deficiencies.map(d => `<li style="margin-bottom:3px;">${d}</li>`).join('') + '</ul></div>';
        } else {
            html += '<div style="margin-bottom: 15px;"><strong style="color: var(--green);">No Deficiencies Found</strong></div>';
        }
        
        if (res.missing_elements && res.missing_elements.length > 0) {
            html += '<div><strong style="color: var(--amber);">Missing Elements:</strong><ul style="margin-top:5px; padding-left: 20px;">' + res.missing_elements.map(e => `<li style="margin-bottom:3px;">${e}</li>`).join('') + '</ul></div>';
        }
        
        document.getElementById('cpReviewContent').innerHTML = html;
        
    } catch (err) {
        document.getElementById('cpReviewContent').innerHTML = `<p style="color:var(--red)">Error: ${err.message}</p>`;
    } finally {
        document.getElementById('btnReviewCarePlan').textContent = 'Review & Score';
    }
});

document.getElementById('btnRewriteCarePlan')?.addEventListener('click', async () => {
    const text = document.getElementById('careplanInput').value.trim();
    if (!text) return alert('Please paste a care plan first.');
    
    document.getElementById('btnRewriteCarePlan').textContent = 'Rewriting...';
    document.getElementById('cpRewriteContent').innerHTML = '<p class="text-muted">Rewriting to Master Clinical standard...</p>';
    
    try {
        const payload = { care_plan_text: text };
        if (currentCpFindings) {
            payload.findings = currentCpFindings;
        }
        const res = await api('/api/care-plans/rewrite', 'POST', payload);
        document.getElementById('cpRewriteContent').textContent = res.rewritten_care_plan || 'Error parsing rewrite.';
    } catch (err) {
        document.getElementById('cpRewriteContent').innerHTML = `<p style="color:var(--red)">Error: ${err.message}</p>`;
    } finally {
        document.getElementById('btnRewriteCarePlan').textContent = 'Rewrite to Standard';
    }
});

document.getElementById('btnPushPcc')?.addEventListener('click', async () => {
    if (!currentCarePlanId || !currentPatientId) return alert('No PCC care plan selected.');
    const text = document.getElementById('cpRewriteContent').textContent;
    if (!text || text.includes('Awaiting rewrite')) return alert('Rewrite the care plan first.');
    
    try {
        const res = await api(`/api/care-plans/patient/${currentPatientId}/${currentCarePlanId}/push-rewrite`, 'PUT', { rewritten_text: text });
        alert(res.message || 'Pushed successfully');
    } catch (e) {
        alert(e.message);
    }
});
