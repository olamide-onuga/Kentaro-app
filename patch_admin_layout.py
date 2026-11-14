with open('app/templates/admin/layout.html', 'r', encoding='utf-8') as f:
    code = f.read()

target = """                    <!-- Chat Support -->
                    <a href="{{ url_for('admin.support_chat') }}"
                       class="flex items-center justify-between px-3.5 py-2.5 rounded-2xl text-xs font-semibold transition {% if request.endpoint == 'admin.support_chat' %}bg-red-50 dark:bg-red-950/50 text-red-600 dark:text-red-400 font-bold border border-red-200/60 dark:border-red-900/60{% else %}text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-900{% endif %}">
                        <span class="flex items-center gap-2.5">
                            <span class="text-base">💬</span>
                            <span>Support Chat</span>
                        </span>
                    </a>"""

replacement = """                    <!-- Support Tickets -->
                    <a href="{{ url_for('admin.support_tickets') }}"
                       class="flex items-center justify-between px-3.5 py-2.5 rounded-2xl text-xs font-semibold transition {% if request.endpoint in ['admin.support_tickets', 'admin.ticket_detail'] %}bg-red-50 dark:bg-red-950/50 text-red-600 dark:text-red-400 font-bold border border-red-200/60 dark:border-red-900/60{% else %}text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-900{% endif %}">
                        <span class="flex items-center gap-2.5">
                            <span class="text-base">🎫</span>
                            <span>Support Tickets</span>
                        </span>
                        {% if admin_pending_tickets and admin_pending_tickets > 0 %}
                        <span class="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-amber-500 text-white animate-pulse">
                            {{ admin_pending_tickets }}
                        </span>
                        {% endif %}
                    </a>

                    <!-- Support Reports -->
                    <a href="{{ url_for('admin.support_reports') }}"
                       class="flex items-center justify-between px-3.5 py-2.5 rounded-2xl text-xs font-semibold transition {% if request.endpoint in ['admin.support_reports', 'admin.support_report_detail'] %}bg-red-50 dark:bg-red-950/50 text-red-600 dark:text-red-400 font-bold border border-red-200/60 dark:border-red-900/60{% else %}text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-900{% endif %}">
                        <span class="flex items-center gap-2.5">
                            <span class="text-base">📊</span>
                            <span>Support Reports</span>
                        </span>
                    </a>

                    <!-- Chat Support (Live DM) -->
                    <a href="{{ url_for('admin.support_chat') }}"
                       class="flex items-center justify-between px-3.5 py-2.5 rounded-2xl text-xs font-semibold transition {% if request.endpoint == 'admin.support_chat' %}bg-red-50 dark:bg-red-950/50 text-red-600 dark:text-red-400 font-bold border border-red-200/60 dark:border-red-900/60{% else %}text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-900{% endif %}">
                        <span class="flex items-center gap-2.5">
                            <span class="text-base">💬</span>
                            <span>Support Chat (Live DM)</span>
                        </span>
                    </a>"""

code_norm = code.replace('\r\n', '\n')
target_norm = target.replace('\r\n', '\n')
replacement_norm = replacement.replace('\r\n', '\n')

if target_norm in code_norm:
    code_norm = code_norm.replace(target_norm, replacement_norm)
    with open('app/templates/admin/layout.html', 'w', encoding='utf-8') as f:
        f.write(code_norm)
    print("Updated app/templates/admin/layout.html successfully")
else:
    print("Target not found in layout.html")
