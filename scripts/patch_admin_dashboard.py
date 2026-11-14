import re

with open('app/templates/admin/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the logout anchor and insert before it
logout_anchor = 'url_for(\'auth.logout\')'
idx = content.find(logout_anchor)
if idx == -1:
    print("ERROR: logout anchor not found")
else:
    # Find the start of that <a> tag
    a_start = content.rfind('<a ', 0, idx)
    insert_text = '''            <a href="{{ url_for('admin.send_anonymous_dm') }}" class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-2xl bg-black dark:bg-white text-white dark:text-black font-bold text-xs hover:opacity-80 transition shadow-sm">
                <span></span> Support DM
            </a>
            <a href="{{ url_for('admin.compose_email') }}" class="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-2xl bg-black dark:bg-white text-white dark:text-black font-bold text-xs hover:opacity-80 transition shadow-sm">
                <span>✉️</span> Send Email
            </a>
            '''
    content = content[:a_start] + insert_text + content[a_start:]
    with open('app/templates/admin/dashboard.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Admin dashboard patched — DM and Email links added.")
