with open('app/templates/coach/chat.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add single-tick for unread self messages
old_tick = '''                            {% if is_self and msg.is_read %}
                            <span class="text-[#53bdeb] font-bold">✓✓</span>
                            {% endif %}'''

new_tick = '''                            {% if is_self and msg.is_read %}
                            <span class="text-[#53bdeb] font-bold">✓✓</span>
                            {% elif is_self %}
                            <span class="tick-single text-gray-400">✓</span>
                            {% endif %}'''

if old_tick in content:
    content = content.replace(old_tick, new_tick)
    print("OK: Two-tick in coach/chat.html: Added single tick for unread self messages")
else:
    print("WARNING: old_tick not found in coach/chat.html")

# 2. Update JS appendMessageBubble
old_js_tick = "${isSelf ? '<span class=\"text-[#53bdeb] font-bold\">✓✓</span>' : ''}"
new_js_tick = "${isSelf ? '<span class=\"tick-single text-gray-400\">✓</span>' : ''}"
if old_js_tick in content:
    content = content.replace(old_js_tick, new_js_tick)
    print("OK: Two-tick in coach/chat.html: JS appendMessageBubble now uses single tick for new messages")
else:
    print("WARNING: old_js_tick not found in coach/chat.html")

# 3. Add mark_read emit and messages_read listener
old_status_check = '''    if (partnerId) {
        socket.emit('check_user_status', { target_user_id: partnerId });
    }'''

new_status_check = '''    if (partnerId) {
        socket.emit('check_user_status', { target_user_id: partnerId });
        socket.emit('mark_read', { partner_id: partnerId });
    }

    // Two-tick read receipt: update single ✓ to double ✓✓ when partner reads
    socket.on('messages_read', function(data) {
        if (data && partnerId && parseInt(data.by_user) === partnerId) {
            document.querySelectorAll('.tick-single').forEach(function(el) {
                el.classList.remove('tick-single', 'text-gray-400');
                el.classList.add('tick-double', 'text-[#53bdeb]');
                el.textContent = '\\u2713\\u2713';
            });
        }
    });

    // When incoming message arrives, mark it as read immediately
    socket.on('chat_message', function(data) {
        const fromId = parseInt(data.from || data.sender_id);
        if (partnerId && fromId === partnerId) {
            socket.emit('mark_read', { partner_id: partnerId });
        }
    });'''

if old_status_check in content:
    content = content.replace(old_status_check, new_status_check)
    print("OK: Two-tick in coach/chat.html: Added mark_read emit and messages_read listener")
else:
    print("WARNING: old_status_check not found in coach/chat.html")

# 4. Add support admin button to sidebar if support_admin_id exists
old_conv_list = '''            <!-- Conversations List -->
            <div id="coachListContainer" class="flex-1 overflow-y-auto p-2 space-y-1 chat-scroll">'''

new_conv_list = '''            <!-- Support Contact Button -->
            {% if support_admin_id %}
            <div class="px-3 py-2 bg-[#f0f2f5] dark:bg-[#202c33] border-b border-gray-100 dark:border-gray-800/60">
                <a href="{{ url_for('coach.coach_chat', partner_id=support_admin_id) }}"
                   class="flex items-center gap-2 px-3 py-2 rounded-xl bg-white dark:bg-[#111b21] border border-gray-200 dark:border-gray-700/60 text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-[#2a3942] transition shadow-xs">
                    <span class="text-sm"></span>
                    <span>Contact Kentaro Support</span>
                </a>
            </div>
            {% endif %}

            <!-- Conversations List -->
            <div id="coachListContainer" class="flex-1 overflow-y-auto p-2 space-y-1 chat-scroll">'''

if old_conv_list in content:
    content = content.replace(old_conv_list, new_conv_list)
    print("OK: Support button in coach/chat.html added")
else:
    print("WARNING: old_conv_list not found in coach/chat.html")

with open('app/templates/coach/chat.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("coach/chat.html successfully patched!")
