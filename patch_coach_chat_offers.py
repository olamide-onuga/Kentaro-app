with open('app/templates/coach/chat.html', 'r', encoding='utf-8') as f:
    coach_chat = f.read()

# Update Support modal to use support.create_ticket
coach_chat = coach_chat.replace(
    'action="{{ url_for(\'coach.start_coach_support_chat\') }}"',
    'action="{{ url_for(\'support.create_ticket\') }}"'
)

# Replace the condition {% if client and is_enrolled %} to {% if client %}
# and upgrade inChatProgramModal to support full custom program offer
old_modal_start = "{% if client and is_enrolled %}\n<!-- In-Chat Program Creation/Assignment Modal -->"
new_modal_start = "{% if client %}\n<!-- In-Chat Program Creation/Assignment Modal -->"
if old_modal_start in coach_chat:
    coach_chat = coach_chat.replace(old_modal_start, new_modal_start)

# Add custom program offer card in message loop
offer_card_coach = """                        {% if msg.message_type == 'offer' or msg.offer_id or (msg.offer) %}
                        <!-- Coach Custom Program Offer Card -->
                        <div class="w-full min-w-[280px] sm:min-w-[340px] max-w-sm py-2 space-y-3 bg-white dark:bg-gray-900 rounded-2xl p-4 border border-emerald-500/40 shadow-md text-gray-900 dark:text-gray-100">
                            <div class="flex items-center justify-between pb-2 border-b border-gray-100 dark:border-gray-800">
                                <div class="flex items-center gap-2">
                                    <span class="text-xl">🎯</span>
                                    <div>
                                        <span class="text-[9px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400">Custom Program Offer</span>
                                        <h4 class="text-sm font-black text-gray-900 dark:text-gray-100 leading-tight">
                                            {{ msg.offer.title if msg.offer else 'Custom Coaching Program' }}
                                        </h4>
                                    </div>
                                </div>
                                <span class="px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider {% if msg.offer and msg.offer.status == 'paid' %}bg-emerald-500/20 text-emerald-700 dark:text-emerald-300{% elif msg.offer and msg.offer.status == 'declined' %}bg-red-500/20 text-red-600{% elif msg.offer and msg.offer.status == 'accepted' %}bg-amber-500/20 text-amber-700{% else %}bg-blue-500/20 text-blue-700 dark:text-blue-300{% endif %}">
                                    {{ msg.offer.status|upper if msg.offer else 'SENT' }}
                                </span>
                            </div>

                            <div class="grid grid-cols-2 gap-2 text-xs py-1">
                                <div class="bg-gray-50 dark:bg-gray-800/80 p-2.5 rounded-xl border border-gray-100 dark:border-gray-800">
                                    <span class="text-[9px] font-bold uppercase text-gray-400">Agreed Price</span>
                                    <p class="font-black text-sm text-gray-900 dark:text-gray-100 mt-0.5">
                                        {{ msg.offer.currency if msg.offer else '$' }} {{ "%.2f"|format(msg.offer.amount) if (msg.offer and msg.offer.amount) else '' }}
                                    </p>
                                </div>
                                <div class="bg-gray-50 dark:bg-gray-800/80 p-2.5 rounded-xl border border-gray-100 dark:border-gray-800">
                                    <span class="text-[9px] font-bold uppercase text-gray-400">Duration &amp; Split</span>
                                    <p class="font-black text-sm text-gray-900 dark:text-gray-100 mt-0.5">
                                        {{ msg.offer.duration_weeks if msg.offer else 4 }} Wks
                                    </p>
                                </div>
                            </div>

                            {% if msg.offer and msg.offer.description %}
                            <p class="text-xs text-gray-600 dark:text-gray-300 line-clamp-2 leading-relaxed">
                                {{ msg.offer.description }}
                            </p>
                            {% endif %}

                            <div class="pt-1 flex items-center justify-between text-[11px] text-gray-400">
                                <span>Status: <strong class="text-gray-700 dark:text-gray-300 capitalize">{{ msg.offer.status if msg.offer else 'Sent' }}</strong></span>
                                <a href="{{ url_for('coach.coach_offers') }}" class="font-bold text-emerald-600 hover:underline">
                                    Manage Offers →
                                </a>
                            </div>
                        </div>
                        {% elif msg.message_type == 'program' or msg.program_id or (msg.message and '🎯' in msg.message and 'Program' in msg.message) %}"""

if '<!-- Coach Custom Program Offer Card -->' not in coach_chat:
    coach_chat = coach_chat.replace(
        "{% if msg.message_type == 'program' or msg.program_id or (msg.message and '🎯' in msg.message and 'Program' in msg.message) %}",
        offer_card_coach
    )

# Add "Create Custom Program" button in the chat header actions
header_btn_old = """                <button onclick="document.getElementById('inChatProgramModal').classList.remove('hidden')" 
                        class="p-2 sm:px-3 sm:py-1.5 rounded-xl bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 font-bold text-xs flex items-center gap-1.5 transition">
                    <span>🎯</span>
                    <span class="hidden sm:inline">Assign Program</span>
                </button>"""

header_btn_new = """                <button onclick="document.getElementById('inChatProgramOfferModal').classList.remove('hidden')" 
                        class="p-2 sm:px-3 sm:py-1.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-100 dark:hover:bg-emerald-900/60 font-bold text-xs flex items-center gap-1.5 transition">
                    <span>🎯</span>
                    <span class="hidden sm:inline">Create Custom Program</span>
                </button>"""

if header_btn_old in coach_chat:
    coach_chat = coach_chat.replace(header_btn_old, header_btn_new)

# Add rich inChatProgramOfferModal to coach_chat
rich_offer_modal = """
<!-- In-Chat Program Offer Modal -->
<div id="inChatProgramOfferModal" class="hidden fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="bg-white dark:bg-neutral-900 border border-gray-200 dark:border-gray-800 rounded-3xl p-6 sm:p-8 max-w-lg w-full shadow-2xl max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between mb-4 pb-2 border-b border-gray-100 dark:border-gray-800">
            <div>
                <span class="text-[9px] font-black uppercase tracking-widest text-emerald-600">Marketplace Proposal</span>
                <h3 class="font-extrabold text-base text-gray-900 dark:text-gray-100">
                    Create Custom Program for {{ client.first_name if client else 'Athlete' }}
                </h3>
            </div>
            <button onclick="document.getElementById('inChatProgramOfferModal').classList.add('hidden')" class="p-1 text-gray-400 hover:text-black dark:hover:text-white font-bold">&times;</button>
        </div>

        <form id="coachCustomProgramOfferForm" class="space-y-3.5 text-xs">
            <input type="hidden" name="client_id" value="{{ client.id if client else '' }}">

            <div>
                <label class="block font-bold text-gray-700 dark:text-gray-300 mb-1">Program Title *</label>
                <input type="text" id="offTitle" name="title" required placeholder="e.g. Personalized Strength &amp; Hypertrophy"
                       class="w-full px-3.5 py-2.5 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-neutral-950 text-gray-900 dark:text-gray-100">
            </div>

            <div class="grid grid-cols-2 gap-3">
                <div>
                    <label class="block font-bold text-gray-700 dark:text-gray-300 mb-1">Duration (Weeks)</label>
                    <input type="number" id="offDuration" name="duration_weeks" value="4" min="1" max="52"
                           class="w-full px-3.5 py-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-neutral-950 text-gray-900 dark:text-gray-100">
                </div>
                <div>
                    <label class="block font-bold text-gray-700 dark:text-gray-300 mb-1">Training Frequency</label>
                    <input type="text" id="offFreq" name="frequency" value="4 days / week" placeholder="e.g. 3 days / week"
                           class="w-full px-3.5 py-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-neutral-950 text-gray-900 dark:text-gray-100">
                </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
                <div>
                    <label class="block font-bold text-gray-700 dark:text-gray-300 mb-1">Program Price *</label>
                    <input type="number" step="0.01" id="offPrice" name="amount" required placeholder="e.g. 150.00"
                           class="w-full px-3.5 py-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-neutral-950 text-gray-900 dark:text-gray-100">
                </div>
                <div>
                    <label class="block font-bold text-gray-700 dark:text-gray-300 mb-1">Currency</label>
                    <select name="currency" id="offCurrency" class="w-full px-3.5 py-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-neutral-950 text-gray-900 dark:text-gray-100">
                        <option value="USD">USD ($)</option>
                        <option value="NGN">NGN (₦)</option>
                        <option value="GBP">GBP (£)</option>
                        <option value="EUR">EUR (€)</option>
                    </select>
                </div>
            </div>

            <div>
                <label class="block font-bold text-gray-700 dark:text-gray-300 mb-1">Target Goals</label>
                <input type="text" id="offGoals" name="goals" placeholder="e.g. Master Muscle-Up, increase pull-ups to 20, improve core"
                       class="w-full px-3.5 py-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-neutral-950 text-gray-900 dark:text-gray-100">
            </div>

            <div>
                <label class="block font-bold text-gray-700 dark:text-gray-300 mb-1">Program Description / Overview</label>
                <textarea id="offDesc" name="description" rows="2" placeholder="Brief outline of workout phases and expectations..."
                          class="w-full px-3.5 py-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-neutral-950 text-gray-900 dark:text-gray-100"></textarea>
            </div>

            <!-- Existing or New workout template selection -->
            {% if coach_programs %}
            <div>
                <label class="block font-bold text-gray-700 dark:text-gray-300 mb-1">Attach Routine Template (optional)</label>
                <select name="program_id" id="offProgSelect" class="w-full px-3.5 py-2 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-neutral-950 text-gray-900 dark:text-gray-100">
                    <option value="">-- Create Fresh Custom Structure --</option>
                    {% for prog in coach_programs %}
                    <option value="{{ prog.id }}">{{ prog.name }}</option>
                    {% endfor %}
                </select>
            </div>
            {% endif %}

            <div id="coachOfferStatusMsg" class="hidden text-xs text-center py-1"></div>

            <div class="pt-2 flex items-center gap-3">
                <button type="button" onclick="document.getElementById('inChatProgramOfferModal').classList.add('hidden')"
                        class="px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-800 text-gray-600 font-bold">
                    Cancel
                </button>
                <button type="button" onclick="submitCoachProgramOffer()"
                        class="flex-1 py-2.5 rounded-xl bg-[#00a884] hover:bg-[#008f6f] text-white font-black shadow-sm transition">
                    Send Custom Program Offer 🚀
                </button>
            </div>
        </form>
    </div>
</div>

<script>
function submitCoachProgramOffer() {
    var title = document.getElementById('offTitle').value.trim();
    var price = parseFloat(document.getElementById('offPrice').value);
    var statusEl = document.getElementById('coachOfferStatusMsg');

    if (!title) {
        statusEl.className = 'text-xs text-center py-1 text-red-500 font-bold';
        statusEl.textContent = 'Please provide a program title.';
        statusEl.classList.remove('hidden');
        return;
    }
    if (isNaN(price) || price <= 0) {
        statusEl.className = 'text-xs text-center py-1 text-red-500 font-bold';
        statusEl.textContent = 'Please specify a valid program price.';
        statusEl.classList.remove('hidden');
        return;
    }

    var formEl = document.getElementById('coachCustomProgramOfferForm');
    var formData = new FormData(formEl);

    statusEl.className = 'text-xs text-center py-1 text-gray-500 font-bold';
    statusEl.textContent = 'Sending custom program proposal...';
    statusEl.classList.remove('hidden');

    fetch('/coach/chat/create-custom-program-offer-ajax', {
        method: 'POST',
        body: formData
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.ok) {
            statusEl.className = 'text-xs text-center py-1 text-emerald-600 font-bold';
            statusEl.textContent = 'Offer sent successfully!';
            setTimeout(function() {
                document.getElementById('inChatProgramOfferModal').classList.add('hidden');
                window.location.reload();
            }, 800);
        } else {
            statusEl.className = 'text-xs text-center py-1 text-red-500 font-bold';
            statusEl.textContent = data.error || 'Failed to send offer.';
        }
    })
    .catch(function(err) {
        statusEl.className = 'text-xs text-center py-1 text-red-500 font-bold';
        statusEl.textContent = 'Network error while sending offer.';
    });
}
</script>
"""

if 'id="inChatProgramOfferModal"' not in coach_chat:
    coach_chat += rich_offer_modal

with open('app/templates/coach/chat.html', 'w', encoding='utf-8') as f:
    f.write(coach_chat)

print("Updated app/templates/coach/chat.html with custom program offer modal and cards")
