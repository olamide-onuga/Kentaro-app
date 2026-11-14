with open('app/templates/admin/settings.html', 'r', encoding='utf-8') as f:
    code = f.read()

# Add tab button
tab_btn = """        <button type="button" onclick="switchSettingsTab('admin_profile')" id="tab-btn-admin_profile"
                class="settings-tab-btn px-4 py-2.5 rounded-2xl text-xs font-bold transition flex items-center gap-2 text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-900">
            <span>👤</span>
            <span>Support Display Name</span>
        </button>
    </div>"""

if 'switchSettingsTab(\'admin_profile\')' not in code:
    code = code.replace(
        "    </div>\n\n    <!-- TAB 1: Announcement Banner -->",
        tab_btn + "\n\n    <!-- TAB 1: Announcement Banner -->"
    )

# Add tab content pane
pane_code = """    <!-- TAB 4: Admin Profile & Display Name -->
    <div id="tab-content-admin_profile" class="settings-tab-pane space-y-6 hidden">
        <div class="bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-3xl p-6 sm:p-8 shadow-sm space-y-6">
            <div class="flex items-center gap-3">
                <span class="text-2xl">👤</span>
                <div>
                    <h2 class="text-lg font-bold text-gray-900 dark:text-gray-100">Professional Admin Display Name</h2>
                    <p class="text-xs text-gray-500 dark:text-gray-400">Set your official administrator display name used in all client and coach support ticket interactions.</p>
                </div>
            </div>

            <form method="POST" action="{{ url_for('admin.update_admin_display_name') }}" class="space-y-6 pt-4 border-t border-gray-100 dark:border-gray-900 max-w-lg">
                <div>
                    <label class="block text-xs font-bold text-gray-900 dark:text-gray-100 mb-2">Display Name</label>
                    <input type="text" name="display_name" value="{{ current_user.display_name or '' }}" required placeholder="e.g. John Davis"
                           class="w-full px-4 py-3 rounded-2xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 text-xs text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-red-500">
                    <p class="text-[11px] text-gray-400 mt-1.5">
                        This name will dynamically appear to clients and coaches when you accept their tickets (e.g. <em>"Your ticket has been accepted by {{ current_user.admin_display_name }}."</em>).
                    </p>
                </div>

                <div class="p-4 rounded-2xl bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-xs text-gray-500">
                    <p>Current active display name: <strong class="text-black dark:text-white">{{ current_user.admin_display_name }}</strong></p>
                    <p class="text-[11px] mt-0.5">Account email: {{ current_user.email }}</p>
                </div>

                <button type="submit" class="px-6 py-3 rounded-2xl bg-black dark:bg-white text-white dark:text-black font-black text-xs hover:opacity-90 transition">
                    Save Display Name
                </button>
            </form>
        </div>
    </div>
"""

if 'id="tab-content-admin_profile"' not in code:
    code = code.replace(
        "    <!-- TAB 1: Announcement Banner -->",
        pane_code + "\n    <!-- TAB 1: Announcement Banner -->"
    )

with open('app/templates/admin/settings.html', 'w', encoding='utf-8') as f:
    f.write(code)

print("Updated app/templates/admin/settings.html with Admin Display Name tab")
