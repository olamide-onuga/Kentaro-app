with open('app/templates/client/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

target = '<!-- Pending Custom Negotiated Offers -->'

termination_card = '''            <!-- Contract Termination Approval Request Card -->
            {% set pending_termination = none %}
            {% if profile and profile.contracts %}
              {% for c in profile.contracts %}
                {% if c.status == 'active' and c.termination_status == 'pending_client_approval' %}
                  {% set pending_termination = c %}
                {% endif %}
              {% endfor %}
            {% endif %}

            {% if pending_termination %}
            <div class="rounded-3xl bg-gradient-to-r from-red-500/10 via-orange-500/10 to-red-600/10 border-2 border-red-500/40 p-6 shadow-md space-y-3">
                <div class="flex items-center gap-2">
                    <span class="text-xl">⚠️</span>
                    <h3 class="text-lg font-black text-gray-900 dark:text-gray-100">Contract Termination Request</h3>
                </div>
                <p class="text-sm text-gray-600 dark:text-gray-400">Your coach has requested to end your coaching contract.</p>
                {% if pending_termination.termination_reason %}
                <p class="text-sm text-gray-800 dark:text-gray-200"><strong>Reason:</strong> {{ pending_termination.termination_reason }}</p>
                {% endif %}
                <div class="flex gap-3 pt-1">
                    <form method="POST" action="{{ url_for('client.approve_contract_termination') }}">
                        <button type="submit" class="px-5 py-2.5 rounded-xl bg-red-600 hover:bg-red-500 text-white font-bold text-xs transition shadow-sm">
                            Approve Termination
                        </button>
                    </form>
                    <form method="POST" action="{{ url_for('client.decline_contract_termination') }}">
                        <button type="submit" class="px-5 py-2.5 rounded-xl bg-gray-200 dark:bg-gray-800 text-gray-800 dark:text-gray-200 font-bold text-xs hover:bg-gray-300 dark:hover:bg-gray-700 transition">
                            Decline
                        </button>
                    </form>
                </div>
            </div>
            {% endif %}

            '''

if target in content:
    content = content.replace(target, termination_card + target)
    with open('app/templates/client/dashboard.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Termination card added to client/dashboard.html successfully!")
else:
    print("target not found")
