# 1. Update client.py
client_py = r'C:\Users\Kentaro\.gemini\antigravity\scratch\kentaro\app\routes\client.py'
with open(client_py, 'r', encoding='utf-8') as f:
    client_code = f.read().replace('\r\n', '\n')

old_prog = """    form_checks = FormCheckSubmission.query.filter_by(client_id=profile.id).order_by(FormCheckSubmission.created_at.desc()).all()
    today_str = dt.date.today().isoformat()

    return render_template(
        'client/progress.html',
        profile=profile,
        weight_logs=weight_logs,
        latest_weight=latest_weight,
        photos=photos,
        form_checks=form_checks,
        today_str=today_str,
    )"""

new_prog = """    form_checks = FormCheckSubmission.query.filter_by(client_id=profile.id).order_by(FormCheckSubmission.created_at.desc()).all()
    today_str = dt.date.today().isoformat()

    chart_labels = [w.date.strftime('%b %d') if hasattr(w.date, 'strftime') else str(w.date) for w in weight_logs]
    chart_data = [float(w.weight) for w in weight_logs]

    return render_template(
        'client/progress.html',
        profile=profile,
        weight_logs=weight_logs,
        latest_weight=latest_weight,
        photos=photos,
        form_checks=form_checks,
        today_str=today_str,
        chart_labels=chart_labels,
        chart_data=chart_data,
    )"""

if old_prog in client_code:
    client_code = client_code.replace(old_prog, new_prog)
    with open(client_py, 'w', encoding='utf-8') as f:
        f.write(client_code)
    print("Updated client.py with chart_labels and chart_data!")
else:
    print("Warning: old_prog not found in client.py")

# 2. Update client/progress.html
prog_html = r'C:\Users\Kentaro\.gemini\antigravity\scratch\kentaro\app\templates\client\progress.html'
with open(prog_html, 'r', encoding='utf-8') as f:
    h_code = f.read().replace('\r\n', '\n')

old_chart_js = """        const chartLabels = {{ chart_labels|tojson|safe }};
        const chartData = {{ chart_data|tojson|safe }};"""

new_chart_js = """        const chartLabels = {{ (chart_labels or [])|tojson|safe }};
        const chartData = {{ (chart_data or [])|tojson|safe }};"""

if old_chart_js in h_code:
    h_code = h_code.replace(old_chart_js, new_chart_js)
    with open(prog_html, 'w', encoding='utf-8') as f:
        f.write(h_code)
    print("Updated client/progress.html with fallback!")
else:
    print("Warning: old_chart_js not found in progress.html")

# 3. Update coach/client_detail.html
coach_detail_html = r'C:\Users\Kentaro\.gemini\antigravity\scratch\kentaro\app\templates\coach\client_detail.html'
with open(coach_detail_html, 'r', encoding='utf-8') as f:
    cd_code = f.read().replace('\r\n', '\n')

if old_chart_js in cd_code:
    cd_code = cd_code.replace(old_chart_js, new_chart_js)
    with open(coach_detail_html, 'w', encoding='utf-8') as f:
        f.write(cd_code)
    print("Updated coach/client_detail.html with fallback!")
