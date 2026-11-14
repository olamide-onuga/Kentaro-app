with open('app/templates/base.html', 'r', encoding='utf-8') as f:
    code = f.read()

# Fix the mojibake speech bubble
code = code.replace('ðŸ’¬', '💬')

# Add Support link to Client desktop nav
old_client_nav = '<a href="{{ url_for(\'client.profile\') }}" class="px-3 py-1.5 text-sm font-medium text-kn-muted hover:text-kn-text rounded-md hover:bg-kn-section transition-colors dark:text-kn-muted-dark dark:hover:text-kn-text-dark dark:hover:bg-kn-section-dark">Profile</a>'
new_client_nav = '<a href="{{ url_for(\'client.profile\') }}" class="px-3 py-1.5 text-sm font-medium text-kn-muted hover:text-kn-text rounded-md hover:bg-kn-section transition-colors dark:text-kn-muted-dark dark:hover:text-kn-text-dark dark:hover:bg-kn-section-dark">Profile</a>\n                        <a href="{{ url_for(\'support.history\') }}" class="px-3 py-1.5 text-sm font-medium text-kn-muted hover:text-kn-text rounded-md hover:bg-kn-section transition-colors dark:text-kn-muted-dark dark:hover:text-kn-text-dark dark:hover:bg-kn-section-dark">Support</a>'

if old_client_nav in code and 'url_for(\'support.history\')' not in code:
    code = code.replace(old_client_nav, new_client_nav)

# Add Offers and Support links to Coach desktop nav
old_coach_nav = '<a href="{{ url_for(\'coach.packages\') }}" class="px-3 py-1.5 text-sm font-medium text-kn-muted hover:text-kn-text rounded-md hover:bg-kn-section transition-colors dark:text-kn-muted-dark dark:hover:text-kn-text-dark dark:hover:bg-kn-section-dark">Packages</a>'
new_coach_nav = '<a href="{{ url_for(\'coach.packages\') }}" class="px-3 py-1.5 text-sm font-medium text-kn-muted hover:text-kn-text rounded-md hover:bg-kn-section transition-colors dark:text-kn-muted-dark dark:hover:text-kn-text-dark dark:hover:bg-kn-section-dark">Packages</a>\n                        <a href="{{ url_for(\'coach.coach_offers\') }}" class="px-3 py-1.5 text-sm font-medium text-kn-muted hover:text-kn-text rounded-md hover:bg-kn-section transition-colors dark:text-kn-muted-dark dark:hover:text-kn-text-dark dark:hover:bg-kn-section-dark">Offers</a>\n                        <a href="{{ url_for(\'support.history\') }}" class="px-3 py-1.5 text-sm font-medium text-kn-muted hover:text-kn-text rounded-md hover:bg-kn-section transition-colors dark:text-kn-muted-dark dark:hover:text-kn-text-dark dark:hover:bg-kn-section-dark">Support</a>'

if old_coach_nav in code and 'url_for(\'coach.coach_offers\')' not in code:
    code = code.replace(old_coach_nav, new_coach_nav)

# Add Support Tickets to Admin desktop nav
old_admin_nav = '<a href="{{ url_for(\'admin.support_chat\') }}" class="px-3 py-1.5 text-sm font-medium text-kn-muted hover:text-kn-text rounded-md hover:bg-kn-section transition-colors dark:text-kn-muted-dark dark:hover:text-kn-text-dark dark:hover:bg-kn-section-dark relative inline-flex items-center gap-1.5">Support Chat<span class="global-unread-badge inline-flex items-center justify-center bg-red-500 text-white text-[9px] font-black rounded-full min-w-[16px] h-4 px-1 leading-none" data-count="{{ unread_count|default(0) }}" style="display:{% if unread_count|default(0) > 0 %}inline-flex{% else %}none{% endif %};">{{ unread_count|default(0) }}</span></a>'
new_admin_nav = '<a href="{{ url_for(\'admin.support_tickets\') }}" class="px-3 py-1.5 text-sm font-medium text-kn-muted hover:text-kn-text rounded-md hover:bg-kn-section transition-colors dark:text-kn-muted-dark dark:hover:text-kn-text-dark dark:hover:bg-kn-section-dark">Support Tickets</a>\n                        ' + old_admin_nav

if old_admin_nav in code and 'url_for(\'admin.support_tickets\')' not in code:
    code = code.replace(old_admin_nav, new_admin_nav)

# Mobile Menu Links
code = code.replace(
    '<a href="{{ url_for(\'client.profile\') }}" class="flex items-center gap-3 px-3 py-2.5 text-sm font-semibold text-gray-800 hover:bg-gray-100 rounded-xl dark:text-gray-200 dark:hover:bg-gray-900 transition">Profile</a>',
    '<a href="{{ url_for(\'client.profile\') }}" class="flex items-center gap-3 px-3 py-2.5 text-sm font-semibold text-gray-800 hover:bg-gray-100 rounded-xl dark:text-gray-200 dark:hover:bg-gray-900 transition">Profile</a>\n              <a href="{{ url_for(\'support.history\') }}" class="flex items-center gap-3 px-3 py-2.5 text-sm font-semibold text-gray-800 hover:bg-gray-100 rounded-xl dark:text-gray-200 dark:hover:bg-gray-900 transition">🎫 Support Desk</a>'
)

code = code.replace(
    '<a href="{{ url_for(\'coach.subscription\') }}" class="flex items-center gap-3 px-3 py-2.5 text-sm font-semibold text-gray-800 hover:bg-gray-100 rounded-xl dark:text-gray-200 dark:hover:bg-gray-900 transition">💎 My Plan</a>',
    '<a href="{{ url_for(\'coach.coach_offers\') }}" class="flex items-center gap-3 px-3 py-2.5 text-sm font-semibold text-gray-800 hover:bg-gray-100 rounded-xl dark:text-gray-200 dark:hover:bg-gray-900 transition">🎯 Custom Program Offers</a>\n              <a href="{{ url_for(\'support.history\') }}" class="flex items-center gap-3 px-3 py-2.5 text-sm font-semibold text-gray-800 hover:bg-gray-100 rounded-xl dark:text-gray-200 dark:hover:bg-gray-900 transition">🎫 Support Desk</a>\n              <a href="{{ url_for(\'coach.subscription\') }}" class="flex items-center gap-3 px-3 py-2.5 text-sm font-semibold text-gray-800 hover:bg-gray-100 rounded-xl dark:text-gray-200 dark:hover:bg-gray-900 transition">💎 My Plan</a>'
)

with open('app/templates/base.html', 'w', encoding='utf-8') as f:
    f.write(code)

print("Updated app/templates/base.html with Support Desk and Offers navigation links and fixed speech bubble emoji")
