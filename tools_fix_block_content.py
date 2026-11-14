import os

# 1. Fix coach/chat.html
chat_path = r"C:\Users\Kentaro\.gemini\antigravity\scratch\kentaro\app\templates\coach\chat.html"
with open(chat_path, "r", encoding="utf-8") as f:
    chat_content = f.read().replace("\r\n", "\n")

# In coach/chat.html, find {% endblock %} around line 1478
# It's right after <!-- Copy Toast --> div
old_toast_block = """<!-- Copy Toast -->
<div id="copyToast" class="hidden fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 text-xs font-bold rounded-2xl shadow-xl">
    Copied to clipboard!
</div>

{% endblock %}"""

new_toast_block = """<!-- Copy Toast -->
<div id="copyToast" class="hidden fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 text-xs font-bold rounded-2xl shadow-xl">
    Copied to clipboard!
</div>"""

if old_toast_block in chat_content:
    chat_content = chat_content.replace(old_toast_block, new_toast_block)
    # Ensure {% endblock %} is at the very end
    if not chat_content.strip().endswith("{% endblock %}"):
        chat_content = chat_content.rstrip() + "\n{% endblock %}\n"
    with open(chat_path, "w", encoding="utf-8") as f:
        f.write(chat_content)
    print("Fixed coach/chat.html - moved {% endblock %} to end of file")
else:
    print("Could not find old_toast_block in coach/chat.html")

# 2. Fix coach/scout_chat.html
scout_path = r"C:\Users\Kentaro\.gemini\antigravity\scratch\kentaro\app\templates\coach\scout_chat.html"
with open(scout_path, "r", encoding="utf-8") as f:
    scout_content = f.read().replace("\r\n", "\n")

old_scout_toast = """<div id="copyToast" class="hidden fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 text-xs font-bold rounded-2xl shadow-xl">
    Copied to clipboard!
</div>

{% endblock %}"""

new_scout_toast = """<div id="copyToast" class="hidden fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 text-xs font-bold rounded-2xl shadow-xl">
    Copied to clipboard!
</div>"""

if old_scout_toast in scout_content:
    scout_content = scout_content.replace(old_scout_toast, new_scout_toast)
    if not scout_content.strip().endswith("{% endblock %}"):
        scout_content = scout_content.rstrip() + "\n{% endblock %}\n"
    with open(scout_path, "w", encoding="utf-8") as f:
        f.write(scout_content)
    print("Fixed coach/scout_chat.html - moved {% endblock %} to end of file")
else:
    print("Could not find old_scout_toast in coach/scout_chat.html")
