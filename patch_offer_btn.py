# 1. Update coach.py
coach_py = r'C:\Users\Kentaro\.gemini\antigravity\scratch\kentaro\app\routes\coach.py'
with open(coach_py, 'r', encoding='utf-8') as f:
    text = f.read().replace('\r\n', '\n')

old_code = """            if not is_enrolled and not has_other_coach and not has_accepted:
                active_offer = CustomOffer.query.filter_by(
                    coach_id=coach.id,
                    client_id=active_client.id,
                    status='pending'
                ).order_by(CustomOffer.created_at.desc()).first()
                is_marketplace_contact = True
                can_send_offer = True"""

new_code = """            if not has_other_coach:
                active_offer = CustomOffer.query.filter_by(
                    coach_id=coach.id,
                    client_id=active_client.id,
                    status='pending'
                ).order_by(CustomOffer.created_at.desc()).first()
                is_marketplace_contact = True
                can_send_offer = True"""

if old_code in text:
    text = text.replace(old_code, new_code)
    with open(coach_py, 'w', encoding='utf-8') as f:
        f.write(text)
    print("Updated coach.py successfully!")
else:
    print("Warning: old_code not found in coach.py")

# 2. Update coach/chat.html to add quick offer button in message input footer
coach_chat = r'C:\Users\Kentaro\.gemini\antigravity\scratch\kentaro\app\templates\coach\chat.html'
with open(coach_chat, 'r', encoding='utf-8') as f:
    chat_text = f.read().replace('\r\n', '\n')

target_voice_btn = """                    <!-- SVG Voice Recording Button for Coach -->
                    <button type="button" id="recordVoiceBtn" class="p-2.5 rounded-full text-gray-600 hover:text-black dark:text-gray-300 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-neutral-800 transition shrink-0" title="Record voice message" onclick="toggleVoiceRecording()">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"/>
                        </svg>
                    </button>"""

repl_voice_btn = """                    <!-- Create & Send Custom Package Quick Button -->
                    {% if can_send_offer %}
                    <button type="button" onclick="document.getElementById('inChatProgramOfferModal').classList.remove('hidden')" class="p-2.5 rounded-full text-emerald-600 hover:text-emerald-500 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/40 transition shrink-0" title="Create & Send Custom Program Offer">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                    </button>
                    {% endif %}

                    <!-- SVG Voice Recording Button for Coach -->
                    <button type="button" id="recordVoiceBtn" class="p-2.5 rounded-full text-gray-600 hover:text-black dark:text-gray-300 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-neutral-800 transition shrink-0" title="Record voice message" onclick="toggleVoiceRecording()">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"/>
                        </svg>
                    </button>"""

if target_voice_btn in chat_text:
    chat_text = chat_text.replace(target_voice_btn, repl_voice_btn)
    with open(coach_chat, 'w', encoding='utf-8') as f:
        f.write(chat_text)
    print("Updated coach/chat.html successfully!")
else:
    print("Warning: target_voice_btn not found in coach/chat.html")
