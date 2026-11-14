import re

# ─────────────────────────────────────────────────────────────────────────────
# 1. PATCH CLIENT CHAT: OFFER CARD, PROGRAM PREVIEW MODAL, SUPPORT MODAL
# ─────────────────────────────────────────────────────────────────────────────
with open('app/templates/client/chat.html', 'r', encoding='utf-8') as f:
    client_chat = f.read()

# Replace support modal button to link/open support ticket modal
client_chat = client_chat.replace(
    'action="{{ url_for(\'client.start_support_chat\') }}"',
    'action="{{ url_for(\'support.create_ticket\') }}"'
)

# Support History link in support modal or header
if 'url_for(\'support.history\')' not in client_chat:
    client_chat = client_chat.replace(
        '<span class="text-xs text-gray-500 dark:text-gray-400">Direct platform assistance from Kentaro staff</span>',
        '<span class="text-xs text-gray-500 dark:text-gray-400">Direct platform assistance from Kentaro staff</span> · <a href="/support/history" class="text-xs font-bold text-blue-500 underline">View Support History</a>'
    )

# Add custom offer card in message loop
offer_card_template = """                        {% if msg.message_type == 'offer' or msg.offer_id or (msg.offer) %}
                        <!-- Structured Custom Program Offer Card -->
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
                                    {{ msg.offer.status|upper if msg.offer else 'OFFER' }}
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

                            <div class="pt-1 flex items-center gap-2">
                                <button type="button" onclick="openClientOfferPreviewModal({{ msg.offer.id if msg.offer else (msg.offer_id or 0) }})"
                                        class="flex-1 py-2 px-3 rounded-xl bg-black dark:bg-white text-white dark:text-black font-black text-xs hover:opacity-90 transition text-center shadow-xs">
                                    View Program Details
                                </button>
                                {% if msg.offer and msg.offer.status in ['sent', 'viewed', 'accepted'] %}
                                <a href="{{ url_for('client.checkout_program_offer', offer_id=msg.offer.id) }}"
                                   class="py-2 px-3 rounded-xl bg-[#00a884] hover:bg-[#008f6f] text-white font-black text-xs shadow-xs transition">
                                    Pay Now
                                </a>
                                {% endif %}
                            </div>
                        </div>
                        {% elif msg.message_type == 'program' or msg.program_id or (msg.message and '🎯' in msg.message and 'Program' in msg.message) %}"""

if '<!-- Structured Custom Program Offer Card -->' not in client_chat:
    client_chat = client_chat.replace(
        "{% if msg.message_type == 'program' or msg.program_id or (msg.message and '🎯' in msg.message and 'Program' in msg.message) %}",
        offer_card_template
    )

# Add Client Offer Preview Modal & JS at end of client/chat.html
client_preview_modal = """
<!-- Client Program Offer Preview Modal -->
<div id="clientOfferPreviewModal" class="hidden fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="bg-white dark:bg-gray-900 rounded-3xl max-w-lg w-full p-6 border border-gray-200 dark:border-gray-800 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between pb-3 border-b border-gray-100 dark:border-gray-800 mb-4">
            <div>
                <span class="text-[9px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400">Coaching Program Proposal</span>
                <h3 id="prevOfferTitle" class="text-base font-black text-gray-900 dark:text-gray-100"></h3>
            </div>
            <button onclick="document.getElementById('clientOfferPreviewModal').classList.add('hidden')" class="p-1 rounded-xl text-gray-400 hover:text-black dark:hover:text-white">✕</button>
        </div>

        <div class="space-y-4 text-xs">
            <!-- Summary Grid -->
            <div class="grid grid-cols-3 gap-2 bg-gray-50 dark:bg-gray-800/60 p-3 rounded-2xl">
                <div>
                    <span class="text-[9px] text-gray-400 uppercase font-bold">Coach</span>
                    <p id="prevOfferCoach" class="font-bold text-gray-900 dark:text-gray-100"></p>
                </div>
                <div>
                    <span class="text-[9px] text-gray-400 uppercase font-bold">Duration</span>
                    <p id="prevOfferDuration" class="font-bold text-gray-900 dark:text-gray-100"></p>
                </div>
                <div>
                    <span class="text-[9px] text-gray-400 uppercase font-bold">Price</span>
                    <p id="prevOfferPrice" class="font-black text-emerald-600 dark:text-emerald-400"></p>
                </div>
            </div>

            <div>
                <h4 class="text-[10px] font-black uppercase text-gray-400 tracking-wider mb-1">Description</h4>
                <p id="prevOfferDesc" class="text-gray-700 dark:text-gray-300 leading-relaxed"></p>
            </div>

            <div id="prevOfferGoalsBox">
                <h4 class="text-[10px] font-black uppercase text-gray-400 tracking-wider mb-1">Target Goals &amp; Instructions</h4>
                <p id="prevOfferGoals" class="text-gray-700 dark:text-gray-300 leading-relaxed"></p>
            </div>

            <!-- Workouts Breakdown -->
            <div>
                <h4 class="text-[10px] font-black uppercase text-gray-400 tracking-wider mb-2">Program Workout Structure</h4>
                <div id="prevOfferWorkouts" class="space-y-2 max-h-48 overflow-y-auto pr-1"></div>
            </div>

            <!-- Actions: Accept / Decline -->
            <div id="prevOfferActions" class="pt-4 border-t border-gray-100 dark:border-gray-800 flex items-center gap-3">
                <button type="button" onclick="declineOfferAction()" class="flex-1 py-2.5 rounded-xl border border-red-200 dark:border-red-900/60 text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 font-bold transition">
                    Decline Offer
                </button>
                <button type="button" onclick="acceptOfferAction()" class="flex-1 py-2.5 rounded-xl bg-[#00a884] hover:bg-[#008f6f] text-white font-black shadow-sm transition">
                    Accept &amp; Continue to Payment →
                </button>
            </div>
            <div id="prevOfferStatusNotice" class="hidden text-center py-2 text-xs font-bold"></div>
        </div>
    </div>
</div>

<script>
var currentViewingOfferId = null;

function openClientOfferPreviewModal(offerId) {
    if (!offerId) return;
    currentViewingOfferId = offerId;
    fetch('/client/marketplace/offer/' + offerId + '/preview')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.ok) {
                alert(data.error || 'Failed to load offer preview');
                return;
            }
            var o = data.offer;
            document.getElementById('prevOfferTitle').textContent = o.title;
            document.getElementById('prevOfferCoach').textContent = o.coach_name;
            document.getElementById('prevOfferDuration').textContent = o.duration_weeks + ' Weeks';
            document.getElementById('prevOfferPrice').textContent = o.currency + ' ' + parseFloat(o.amount).toFixed(2);
            document.getElementById('prevOfferDesc').textContent = o.description || 'Custom tailored workout program.';
            document.getElementById('prevOfferGoals').textContent = (o.goals || '') + (o.instructions ? ' • ' + o.instructions : '');

            var wContainer = document.getElementById('prevOfferWorkouts');
            wContainer.innerHTML = '';
            if (o.workouts && o.workouts.length > 0) {
                o.workouts.forEach(function(w) {
                    var el = document.createElement('div');
                    el.className = 'p-2.5 rounded-xl bg-gray-50 dark:bg-gray-800/80 border border-gray-100 dark:border-gray-800';
                    var exList = w.exercises && w.exercises.length > 0 ? w.exercises.map(function(e) { return e.name + ' (' + e.sets + 'x' + e.reps + ')'; }).join(', ') : 'Routine planned';
                    el.innerHTML = '<div class=\"font-bold text-gray-900 dark:text-gray-100\">' + (w.workout_name || 'Workout') + ' <span class=\"text-[10px] text-gray-400 font-normal\">(' + (w.day_name || '') + ')</span></div><div class=\"text-[10px] text-gray-500 mt-0.5\">' + exList + '</div>';
                    wContainer.appendChild(el);
                });
            } else {
                wContainer.innerHTML = '<p class=\"text-gray-400 italic\">Full workout exercises will be unlocked in your dashboard upon payment.</p>';
            }

            var actions = document.getElementById('prevOfferActions');
            var notice = document.getElementById('prevOfferStatusNotice');
            if (o.status === 'paid') {
                actions.classList.add('hidden');
                notice.classList.remove('hidden');
                notice.className = 'text-center py-2 text-xs font-bold text-emerald-600';
                notice.textContent = '✓ This program offer has been paid and is active in your dashboard.';
            } else if (o.status === 'declined') {
                actions.classList.add('hidden');
                notice.classList.remove('hidden');
                notice.className = 'text-center py-2 text-xs font-bold text-red-500';
                notice.textContent = '✕ This program offer was declined.';
            } else {
                actions.classList.remove('hidden');
                notice.classList.add('hidden');
            }

            document.getElementById('clientOfferPreviewModal').classList.remove('hidden');
        })
        .catch(function(err) {
            console.error('Error loading offer:', err);
        });
}

function acceptOfferAction() {
    if (!currentViewingOfferId) return;
    fetch('/client/marketplace/offer/' + currentViewingOfferId + '/accept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.ok && data.checkout_url) {
            window.location.href = data.checkout_url;
        } else {
            alert(data.error || 'Failed to accept offer');
        }
    });
}

function declineOfferAction() {
    if (!currentViewingOfferId || !confirm('Are you sure you want to decline this custom program offer?')) return;
    fetch('/client/marketplace/offer/' + currentViewingOfferId + '/decline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.ok) {
            document.getElementById('clientOfferPreviewModal').classList.add('hidden');
            window.location.reload();
        } else {
            alert(data.error || 'Failed to decline offer');
        }
    });
}
</script>
"""

if 'id="clientOfferPreviewModal"' not in client_chat:
    client_chat += client_preview_modal

with open('app/templates/client/chat.html', 'w', encoding='utf-8') as f:
    f.write(client_chat)

print("Updated app/templates/client/chat.html with offer cards, preview modal, and support modal")
