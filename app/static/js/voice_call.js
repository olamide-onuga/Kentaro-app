// Real-time Voice & Video Call using WebRTC, Socket.IO & SimplePeer
(function() {
    'use strict';
    const socket = window.socket;
    if (!socket) { console.error('[voice_call] window.socket not found'); return; }

    // ── State ──────────────────────────────────────────────────────────────
    let peer = null;
    let localStream = null;
    let remoteStreamStore = null;
    let cameraTrack = null;
    let screenStream = null;
    let currentVideoTrack = null;
    let callTimerInterval = null;
    let callSeconds = 0;
    let isAudioMuted = false;
    let isVideoOff = false;
    let isSharingScreen = false;
    let pendingCandidates = [];   // buffer ICE candidates before peer ready
    let peerReady = false;        // true once peer object exists

    // ── Element refs ───────────────────────────────────────────────────────
    const localVideo        = document.getElementById('localVideo');
    const remoteVideo       = document.getElementById('remoteVideo');
    const remotePlaceholder = document.getElementById('remotePlaceholder');
    const localPlaceholder  = document.getElementById('localPlaceholder');
    const startBtn          = document.getElementById('startBtn');
    const endBtn            = document.getElementById('endBtn');
    const muteBtn           = document.getElementById('muteBtn');
    const muteIcon          = document.getElementById('muteIcon');
    const videoBtn          = document.getElementById('videoBtn');
    const videoIcon         = document.getElementById('videoIcon');
    const screenBtn         = document.getElementById('screenBtn');
    const screenIcon        = document.getElementById('screenIcon');
    const callStatus        = document.getElementById('callStatus');
    const callTimer         = document.getElementById('callTimer');
    const remoteMuteBadge   = document.getElementById('remoteMuteBadge');
    const remoteMuteText    = document.getElementById('remoteMuteText');
    const remoteScreenBadge = document.getElementById('remoteScreenBadge');
    const remoteScreenText  = document.getElementById('remoteScreenText');
    const remoteCameraNotice= document.getElementById('remoteCameraNotice');
    const remoteStatusDot   = document.getElementById('remoteStatusDot');
    const chatDrawer        = document.getElementById('inCallChatDrawer');
    const chatToggleBtn     = document.getElementById('inCallChatBtn');
    const chatForm          = document.getElementById('inCallChatForm');
    const chatList          = document.getElementById('inCallChatList');
    const chatBadge         = document.getElementById('chatUnreadBadge');
    const castOverlay       = document.getElementById('castOverlay');
    const castVideo         = document.getElementById('castVideo');
    const castTitle         = document.getElementById('castExerciseTitle');
    const closeCastBtn      = document.getElementById('closeCastBtn');

    // ── ICE servers ────────────────────────────────────────────────────────
    const iceServers = [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' },
        { urls: 'stun:stun2.l.google.com:19302' },
        { urls: 'stun:stun3.l.google.com:19302' },
    ];

    // ── Helpers ────────────────────────────────────────────────────────────
    function getPartnerId()   { return window.partnerId || null; }
    function getPartnerName() { return window.partnerName || 'Participant'; }

    function setStatus(text, colorClass) {
        if (callStatus) {
            callStatus.textContent = text;
            callStatus.className = 'text-xs font-semibold px-3 py-1 rounded-full ' +
                (colorClass || 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300');
        }
        if (remoteStatusDot) {
            if (text === 'Connected') {
                remoteStatusDot.className = 'w-4 h-4 rounded-full bg-green-500 border-2 border-black absolute -bottom-1 -right-1';
            } else if (text.includes('Calling') || text.includes('Connecting')) {
                remoteStatusDot.className = 'w-4 h-4 rounded-full bg-amber-500 border-2 border-black absolute -bottom-1 -right-1 animate-ping';
            } else {
                remoteStatusDot.className = 'w-4 h-4 rounded-full bg-gray-500 border-2 border-black absolute -bottom-1 -right-1';
            }
        }
    }

    function startTimer() {
        callSeconds = 0;
        if (callTimer) { callTimer.classList.remove('hidden'); callTimer.textContent = '00:00'; }
        clearInterval(callTimerInterval);
        callTimerInterval = setInterval(() => {
            callSeconds++;
            const m = String(Math.floor(callSeconds / 60)).padStart(2, '0');
            const s = String(callSeconds % 60).padStart(2, '0');
            if (callTimer) callTimer.textContent = `${m}:${s}`;
        }, 1000);
    }

    function stopTimer() {
        clearInterval(callTimerInterval);
        if (callTimer) callTimer.classList.add('hidden');
    }

    function broadcastPeerState() {
        const t = getPartnerId();
        if (!t || !socket) return;
        socket.emit('call_peer_state', {
            target_user_id: t,
            is_muted: isAudioMuted,
            is_video_off: isVideoOff,
            is_sharing_screen: isSharingScreen
        });
    }

    // ── Media acquisition ──────────────────────────────────────────────────
    function initMedia() {
        if (localStream) return Promise.resolve(localStream);
        return navigator.mediaDevices.getUserMedia({ audio: true, video: { width: { ideal: 1280 }, height: { ideal: 720 } } })
            .catch(err => {
                console.warn('[voice_call] getUserMedia HD failed, retrying standard audio/video:', err);
                return navigator.mediaDevices.getUserMedia({ audio: true, video: true });
            })
            .catch(err => {
                console.warn('[voice_call] getUserMedia audio/video failed, retrying audio only:', err);
                return navigator.mediaDevices.getUserMedia({ audio: true, video: false });
            })
            .then(stream => {
                localStream = stream;
                window.localStream = stream;
                const vt = stream.getVideoTracks();
                if (vt.length) { cameraTrack = vt[0]; currentVideoTrack = cameraTrack; }
                if (localVideo) {
                    localVideo.srcObject = stream;
                    localVideo.muted = true;
                    localVideo.play().catch(() => {});
                }
                const floatingLocalVideo = document.getElementById('floatingLocalVideo');
                if (floatingLocalVideo) {
                    floatingLocalVideo.srcObject = stream;
                    floatingLocalVideo.muted = true;
                    floatingLocalVideo.play().catch(() => {});
                }
                if (!cameraTrack && localPlaceholder) localPlaceholder.classList.remove('hidden');
                return stream;
            })
            .catch(err => {
                console.error('[voice_call] getUserMedia all fallbacks failed:', err);
                setStatus('Camera/mic permission denied', 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300');
                throw err;
            });
    }

    let pendingOffer = null;

    // ── Peer factory ───────────────────────────────────────────────────────
    function createPeer(stream, initiator) {
        if (peer) { try { peer.destroy(); } catch(e) {} peer = null; }
        peerReady = false;

        const PeerCtor = window.SimplePeer || (typeof SimplePeer !== 'undefined' ? SimplePeer : null);
        if (!PeerCtor) {
            console.error('[voice_call] SimplePeer library not found!');
            alert('Video call library failed to load. Please refresh the page.');
            return null;
        }

        const p = new PeerCtor({
            initiator: initiator,
            trickle: true,
            stream: stream,
            config: { iceServers: iceServers }
        });

        p.on('signal', signal => {
            console.log('[voice_call] peer signal →', signal.type || 'candidate');
            socket.emit('voice_signal', { target_user_id: getPartnerId(), signal: signal });
        });

        p.on('stream', remoteStream => {
            console.log('[voice_call] got remote stream!');
            attachRemoteStream(remoteStream);
        });

        p.on('connect', () => {
            console.log('[voice_call] peer data-channel connected');
        });

        p.on('close', () => {
            console.log('[voice_call] peer closed');
            cleanup();
        });

        p.on('error', err => {
            console.error('[voice_call] peer error:', err);
        });

        peerReady = true;

        // Apply pending SDP offer/answer first
        if (pendingOffer) {
            console.log('[voice_call] applying pending SDP offer/answer:', pendingOffer.type);
            const offer = pendingOffer;
            pendingOffer = null;
            try { p.signal(offer); } catch(e) { console.warn('[voice_call] Error applying pending offer:', e); }
        }

        // Flush any buffered ICE candidates AFTER SDP offer is set
        if (pendingCandidates.length) {
            console.log('[voice_call] flushing', pendingCandidates.length, 'buffered candidates');
            const candidates = pendingCandidates.splice(0);
            candidates.forEach(sig => { try { p.signal(sig); } catch(e) { console.warn('[voice_call] candidate error:', e); } });
        }
        return p;
    }

    function attachRemoteStream(remoteStream) {
        console.log('[voice_call] attachRemoteStream triggered with stream:', remoteStream);
        remoteStreamStore = remoteStream;
        window.remoteStreamStore = remoteStream;
        if (typeof window.stopRinging === 'function') window.stopRinging();
        if (remoteVideo) {
            remoteVideo.srcObject = remoteStream;
            remoteVideo.muted = false;
            remoteVideo.volume = 1.0;
            const playPromise = remoteVideo.play();
            if (playPromise !== undefined) {
                playPromise.catch(e => {
                    console.warn('[voice_call] Autoplay prevented, muting video to allow playback:', e);
                    remoteVideo.muted = true;
                    remoteVideo.play().catch(err => console.error('[voice_call] remote video play failed:', err));
                });
            }
        }

        // Attach remoteStream to floating mini video player if present
        const floatingRemoteVideo = document.getElementById('floatingRemoteVideo');
        if (floatingRemoteVideo) {
            floatingRemoteVideo.srcObject = remoteStream;
            floatingRemoteVideo.play().catch(() => {});
        }

        // Strip auto_answer or auto_join query parameters from URL so F5 refresh won't re-trigger
        if (window.history && window.history.replaceState) {
            window.history.replaceState({}, document.title, window.location.pathname);
        }

        if (remotePlaceholder) remotePlaceholder.classList.add('hidden');
        setStatus('Connected', 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300');
        startTimer();
        try {
            localStorage.setItem('kentaro_active_call', JSON.stringify({
                isActive: true, partnerName: getPartnerName(),
                partnerId: getPartnerId(),
                callUrl: window.location.href, startTime: Date.now()
            }));
        } catch(e) {}
        broadcastPeerState();
        socket.emit('request_history', { target_user_id: getPartnerId() });
    }

    // ── Call initiation ────────────────────────────────────────────────────
    function startCall() {
        if (peer) return;
        if (typeof window.stopRinging === 'function') window.stopRinging();
        const targetId = getPartnerId();
        if (!targetId) { alert('Partner not found – make sure you are on the correct call page.'); return; }

        setStatus(`Calling ${getPartnerName()}…`, 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300');
        if (startBtn) startBtn.classList.add('hidden');
        if (endBtn)   endBtn.classList.remove('hidden');

        initMedia().then(() => {
            console.log('[voice_call] emitting call_invite to', targetId);
            socket.emit('call_invite', { target_user_id: targetId });
        }).catch(() => cleanup());
    }

    function answerCall() {
        if (peer) return;
        if (typeof window.stopRinging === 'function') window.stopRinging();
        const targetId = getPartnerId();
        if (!targetId) return;

        setStatus(`Connecting with ${getPartnerName()}…`, 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300');
        if (startBtn) startBtn.classList.add('hidden');
        if (endBtn)   endBtn.classList.remove('hidden');

        initMedia().then(stream => {
            console.log('[voice_call] Callee media initialized, creating non-initiator peer & emitting call_accepted to', targetId);
            if (!peer) {
                peer = createPeer(stream, false);
            }
            socket.emit('call_accepted', { target_user_id: targetId });
        }).catch(() => cleanup());
    }

    // ── Socket signaling ───────────────────────────────────────────────────

    // ── Incoming call modal refs ───────────────────────────────────────────
    const incomingCallModal  = document.getElementById('incomingCallModal');
    const incomingCallerName = document.getElementById('incomingCallerName');
    const acceptCallBtn      = document.getElementById('acceptCallBtn');
    const declineCallBtn     = document.getElementById('declineCallBtn');

    let pendingCallerId = null;  // user id of the caller, needed to decline

    function showIncomingModal(callerName, callerUserId) {
        pendingCallerId = callerUserId;
        if (incomingCallerName) incomingCallerName.textContent = callerName;
        if (incomingCallModal)  incomingCallModal.classList.remove('hidden');
    }

    function hideIncomingModal() {
        if (incomingCallModal) incomingCallModal.classList.add('hidden');
        pendingCallerId = null;
    }

    if (acceptCallBtn) {
        acceptCallBtn.addEventListener('click', () => {
            hideIncomingModal();
            answerCall();
        });
    }

    if (declineCallBtn) {
        declineCallBtn.addEventListener('click', () => {
            const targetId = pendingCallerId || getPartnerId();
            hideIncomingModal();
            if (targetId && socket) socket.emit('call_declined', { target_user_id: targetId });
            setStatus('Call declined', 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300');
        });
    }

    // Callee: incoming call → status update (base.html handles the modal & ringing)
    socket.on('call_invite', data => {
        const name = data.caller_name || 'Someone';
        setStatus(`Incoming call from ${name}…`, 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300');
    });

    // Caller: callee accepted → NOW create initiator peer (camera starts here for caller)
    socket.on('call_accepted', data => {
        const name = (data && data.from_name) || getPartnerName();
        setStatus(`Connecting to ${name}…`, 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300');
        initMedia().then(stream => {
            peer = createPeer(stream, true);  // initiator = true
        }).catch(() => cleanup());
    });

    // Both sides: exchange SDP offers/answers and ICE candidates
    socket.on('voice_signal', data => {
        const sig = data.signal;
        if (!sig) return;
        console.log('[voice_call] received voice_signal', sig.type || 'candidate');

        if (peer && peerReady) {
            try { peer.signal(sig); } catch(e) { console.warn('[voice_call] signal error:', e); }
        } else {
            // Buffer until peer is created
            if (sig.type === 'offer' || sig.type === 'answer') {
                pendingOffer = sig;
            } else if (sig.candidate) {
                pendingCandidates.push(sig);
            }

            // If this is an offer and we have no peer yet, create non-initiator peer
            if (sig.type === 'offer' && !peer) {
                initMedia().then(stream => {
                    peer = createPeer(stream, false);
                }).catch(() => cleanup());
            }
        }
    });

    // Call ended by remote
    socket.on('voice_call_end', data => {
        const name = (data && data.from_name) || getPartnerName();
        cleanup();
        setStatus(`Call ended by ${name}`, 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300');
    });

    // Call declined
    socket.on('call_declined', data => {
        const name = (data && data.from_name) || getPartnerName();
        cleanup();
        setStatus(`${name} declined the call`, 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300');
    });

    // Remote peer state (mute / camera / screen)
    socket.on('call_peer_state', data => {
        const name = (data && data.from_name) || getPartnerName();
        if (remoteMuteBadge) {
            if (data.is_muted) {
                remoteMuteBadge.classList.remove('hidden');
                if (remoteMuteText) remoteMuteText.textContent = `${name} is muted`;
            } else {
                remoteMuteBadge.classList.add('hidden');
            }
        }
        if (data.is_video_off) {
            if (remotePlaceholder) remotePlaceholder.classList.remove('hidden');
            if (remoteCameraNotice) { remoteCameraNotice.classList.remove('hidden'); remoteCameraNotice.textContent = `📷 ${name}'s camera is off`; }
        } else {
            if (remoteCameraNotice) remoteCameraNotice.classList.add('hidden');
            if (remoteVideo && remoteVideo.srcObject && remotePlaceholder) remotePlaceholder.classList.add('hidden');
        }
        if (remoteScreenBadge) {
            if (data.is_sharing_screen) {
                remoteScreenBadge.classList.remove('hidden');
                if (remoteScreenText) remoteScreenText.textContent = `${name} is sharing screen`;
            } else {
                remoteScreenBadge.classList.add('hidden');
            }
        }
    });

    // ── Media controls ─────────────────────────────────────────────────────
    function toggleAudio() {
        if (!localStream) return;
        const tracks = localStream.getAudioTracks();
        if (!tracks.length) return;
        isAudioMuted = !isAudioMuted;
        tracks[0].enabled = !isAudioMuted;
        if (muteBtn) {
            muteBtn.classList.toggle('bg-red-600', isAudioMuted);
            muteBtn.classList.toggle('hover:bg-red-700', isAudioMuted);
            muteBtn.classList.toggle('bg-white/10', !isAudioMuted);
            muteBtn.classList.toggle('hover:bg-white/20', !isAudioMuted);
            if (muteIcon) muteIcon.textContent = isAudioMuted ? '🔇' : '🎙️';
            muteBtn.title = isAudioMuted ? 'Unmute' : 'Mute';
        }
        broadcastPeerState();
    }

    function toggleVideo() {
        if (!localStream) return;
        const tracks = localStream.getVideoTracks();
        if (!tracks.length) return;
        isVideoOff = !isVideoOff;
        tracks[0].enabled = !isVideoOff;
        if (localPlaceholder) localPlaceholder.classList.toggle('hidden', !isVideoOff);
        if (videoBtn) {
            videoBtn.classList.toggle('bg-red-600', isVideoOff);
            videoBtn.classList.toggle('hover:bg-red-700', isVideoOff);
            videoBtn.classList.toggle('bg-white/10', !isVideoOff);
            videoBtn.classList.toggle('hover:bg-white/20', !isVideoOff);
            if (videoIcon) videoIcon.textContent = isVideoOff ? '📷' : '📹';
            videoBtn.title = isVideoOff ? 'Turn camera on' : 'Turn camera off';
        }
        broadcastPeerState();
    }

    function toggleScreenShare() {
        if (isSharingScreen) {
            stopScreenSharing();
        } else {
            navigator.mediaDevices.getDisplayMedia({ video: true, audio: false })
                .then(screen => {
                    screenStream = screen;
                    const screenTrack = screen.getVideoTracks()[0];
                    if (peer && cameraTrack) peer.replaceTrack(currentVideoTrack, screenTrack, localStream);
                    currentVideoTrack = screenTrack;
                    if (localVideo) localVideo.srcObject = screen;
                    isSharingScreen = true;
                    screenTrack.onended = stopScreenSharing;
                    if (screenBtn) {
                        screenBtn.classList.remove('bg-white/10', 'hover:bg-white/20');
                        screenBtn.classList.add('bg-green-600', 'hover:bg-green-700');
                        if (screenIcon) screenIcon.textContent = '🖥️';
                        screenBtn.title = 'Stop sharing';
                    }
                    broadcastPeerState();
                })
                .catch(err => console.log('Screen share cancelled:', err));
        }
    }

    function stopScreenSharing() {
        if (!isSharingScreen) return;
        if (screenStream) { screenStream.getTracks().forEach(t => t.stop()); screenStream = null; }
        if (peer && cameraTrack) { peer.replaceTrack(currentVideoTrack, cameraTrack, localStream); currentVideoTrack = cameraTrack; }
        if (localVideo && localStream) localVideo.srcObject = localStream;
        isSharingScreen = false;
        if (screenBtn) {
            screenBtn.classList.remove('bg-green-600', 'hover:bg-green-700');
            screenBtn.classList.add('bg-white/10', 'hover:bg-white/20');
            if (screenIcon) screenIcon.textContent = '🖥️';
            screenBtn.title = 'Share screen';
        }
        broadcastPeerState();
    }

    // ── End / Cleanup ──────────────────────────────────────────────────────
    function endCall() {
        const t = getPartnerId();
        if (t && socket) socket.emit('voice_call_end', { target_user_id: t });
        cleanup();
        setStatus('Call ended', 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300');
    }

    function cleanup() {
        stopTimer();
        stopScreenSharing();
        hideIncomingModal();   // dismiss incoming call modal if still showing
        try { localStorage.removeItem('kentaro_active_call'); } catch(e) {}

        // Strip auto_answer or auto_join query parameters from URL so F5 refresh won't re-trigger
        if (window.history && window.history.replaceState) {
            window.history.replaceState({}, document.title, window.location.pathname);
        }

        pendingCandidates = [];
        pendingOffer = null;
        peerReady = false;
        remoteStreamStore = null;
        window.remoteStreamStore = null;
        window.localStream = null;
        if (typeof window.stopRinging === 'function') window.stopRinging();
        if (peer) { try { peer.destroy(); } catch(e) {} peer = null; }
        if (localStream) { localStream.getTracks().forEach(t => t.stop()); localStream = null; }
        cameraTrack = null; currentVideoTrack = null;
        if (localVideo) localVideo.srcObject = null;
        if (remoteVideo) remoteVideo.srcObject = null;

        const floatingRemote = document.getElementById('floatingRemoteVideo');
        if (floatingRemote) floatingRemote.srcObject = null;
        const floatingLocal = document.getElementById('floatingLocalVideo');
        if (floatingLocal) floatingLocal.srcObject = null;

        const floatingWidget = document.getElementById('activeCallFloatingWidget');
        if (floatingWidget) floatingWidget.classList.add('hidden');
        const activeBanner = document.getElementById('activeCallBanner');
        if (activeBanner) activeBanner.classList.add('hidden');

        if (remotePlaceholder) remotePlaceholder.classList.remove('hidden');
        if (remoteCameraNotice) remoteCameraNotice.classList.add('hidden');
        if (remoteMuteBadge) remoteMuteBadge.classList.add('hidden');
        if (remoteScreenBadge) remoteScreenBadge.classList.add('hidden');

        const curStartBtn = document.getElementById('startBtn') || startBtn;
        const curEndBtn   = document.getElementById('endBtn') || endBtn;
        if (curStartBtn) curStartBtn.classList.remove('hidden');
        if (curEndBtn)   curEndBtn.classList.add('hidden');

        isAudioMuted = false; isVideoOff = false;
        if (muteBtn) { muteBtn.classList.remove('bg-red-600','hover:bg-red-700'); muteBtn.classList.add('bg-white/10','hover:bg-white/20'); if (muteIcon) muteIcon.textContent = '🎙️'; }
        if (videoBtn) { videoBtn.classList.remove('bg-red-600','hover:bg-red-700'); videoBtn.classList.add('bg-white/10','hover:bg-white/20'); if (videoIcon) videoIcon.textContent = '📹'; }
        setStatus('Ready', 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300');

        if (typeof window.syncActiveCallBanner === 'function') {
            window.syncActiveCallBanner();
        }
    }

    // ── In-call Chat ───────────────────────────────────────────────────────
    socket.on('chat_history', data => {
        if (!chatList || !Array.isArray(data.messages)) return;
        chatList.innerHTML = '';
        data.messages.forEach(appendChatMessage);
    });

    socket.on('chat_message', msg => {
        appendChatMessage(msg);
        if (chatDrawer && chatDrawer.classList.contains('hidden') && chatBadge) {
            chatBadge.classList.remove('hidden');
        }
    });

    function appendChatMessage(msg) {
        if (!chatList) return;
        const div = document.createElement('div');
        const isMe = (msg.from_user_id && String(msg.from_user_id) === String(window.currentUserId));
        div.className = `flex ${isMe ? 'justify-end' : 'justify-start'} mb-2`;
        const time = new Date(msg.timestamp || Date.now()).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
        div.innerHTML = `<div class="max-w-[75%] px-3 py-2 rounded-2xl text-xs ${isMe ? 'bg-black text-white dark:bg-white dark:text-black rounded-br-sm' : 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-bl-sm'}">
            ${!isMe ? `<span class="block font-semibold text-[10px] mb-0.5 opacity-60">${msg.from_name || 'Partner'}</span>` : ''}
            <span>${msg.content}</span>
            <span class="block text-[10px] opacity-50 mt-0.5 text-right">${time}</span>
        </div>`;
        chatList.appendChild(div);
        chatList.scrollTop = chatList.scrollHeight;
    }

    if (chatForm) {
        chatForm.addEventListener('submit', e => {
            e.preventDefault();
            const input = document.getElementById('inCallChatInput');
            const content = input?.value.trim();
            if (!content) return;
            socket.emit('chat_message', { target_user_id: getPartnerId(), content });
            input.value = '';
        });
    }
    if (chatToggleBtn) {
        chatToggleBtn.addEventListener('click', () => {
            if (chatDrawer) chatDrawer.classList.toggle('hidden');
            if (chatBadge) chatBadge.classList.add('hidden');
        });
    }
    const closeChatBtn = document.getElementById('closeChatBtn');
    if (closeChatBtn) closeChatBtn.addEventListener('click', () => { if (chatDrawer) chatDrawer.classList.add('hidden'); });

    // ── Cast overlay ───────────────────────────────────────────────────────
    socket.on('cast_form_check', data => {
        if (!castOverlay) return;
        if (castVideo) castVideo.src = data.video_url || '';
        if (castTitle) castTitle.textContent = data.title || '';
        castOverlay.classList.remove('hidden');
        if (castVideo) castVideo.play().catch(() => {});
    });
    socket.on('stop_cast_form_check', () => {
        if (castOverlay) castOverlay.classList.add('hidden');
        if (castVideo) { castVideo.pause(); castVideo.currentTime = 0; }
    });
    window.castFormVideo = function(videoUrl, title, notes) {
        socket.emit('cast_form_check', { target_user_id: getPartnerId(), video_url: videoUrl, title, notes: notes || '' });
    };
    if (closeCastBtn) {
        closeCastBtn.addEventListener('click', () => {
            socket.emit('stop_cast_form_check', { target_user_id: getPartnerId() });
            if (castOverlay) castOverlay.classList.add('hidden');
            if (castVideo) { castVideo.pause(); castVideo.currentTime = 0; }
        });
    }

    // ── Button event listeners ─────────────────────────────────────────────
    if (startBtn)   startBtn.addEventListener('click', startCall);
    if (endBtn)     endBtn.addEventListener('click', endCall);
    if (muteBtn)    muteBtn.addEventListener('click', toggleAudio);
    if (videoBtn)   videoBtn.addEventListener('click', toggleVideo);
    if (screenBtn)  screenBtn.addEventListener('click', toggleScreenShare);

    const castFormBtn = document.getElementById('castFormBtn');
    if (castFormBtn) {
        castFormBtn.addEventListener('click', () => {
            const drawer = document.getElementById('formChecksDrawer');
            if (drawer) drawer.classList.toggle('hidden');
        });
    }

    function rebindCallUI() {
        if (window.location.pathname.indexOf('/voice-call') === -1) return;
        console.log('[voice_call] rebindCallUI triggered');
        const rVideo = document.getElementById('remoteVideo');
        const lVideo = document.getElementById('localVideo');
        const sBtn   = document.getElementById('startBtn');
        const eBtn   = document.getElementById('endBtn');
        const rPlace = document.getElementById('remotePlaceholder');
        const lPlace = document.getElementById('localPlaceholder');
        const widget = document.getElementById('activeCallFloatingWidget');
        const banner = document.getElementById('activeCallBanner');

        if (widget) widget.classList.add('hidden');
        if (banner) banner.classList.add('hidden');

        let activeCallInfo = null;
        try { activeCallInfo = JSON.parse(localStorage.getItem('kentaro_active_call') || 'null'); } catch(e) {}
        const isCallActive = !!(peer || localStream || remoteStreamStore || (activeCallInfo && activeCallInfo.isActive));

        if (isCallActive) {
            if (sBtn) sBtn.classList.add('hidden');
            if (eBtn) eBtn.classList.remove('hidden');
            setStatus('Connected', 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300');
        } else {
            if (sBtn) sBtn.classList.remove('hidden');
            if (eBtn) eBtn.classList.add('hidden');
            setStatus('Ready', 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300');
        }

        if (localStream && lVideo) {
            lVideo.srcObject = localStream;
            lVideo.muted = true;
            lVideo.play().catch(() => {});
            if (lPlace && cameraTrack) lPlace.classList.add('hidden');
        }

        if (remoteStreamStore && rVideo) {
            rVideo.srcObject = remoteStreamStore;
            rVideo.muted = false;
            rVideo.volume = 1.0;
            rVideo.play().catch(() => {});
            if (rPlace) rPlace.classList.add('hidden');
        }

        const nStartBtn = document.getElementById('startBtn');
        const nEndBtn   = document.getElementById('endBtn');
        const nMuteBtn  = document.getElementById('muteBtn');
        const nVideoBtn = document.getElementById('videoBtn');
        const nScreenBtn= document.getElementById('screenBtn');

        if (nStartBtn)  nStartBtn.onclick  = startCall;
        if (nEndBtn)    nEndBtn.onclick    = endCall;
        if (nMuteBtn)   nMuteBtn.onclick   = toggleAudio;
        if (nVideoBtn)  nVideoBtn.onclick  = toggleVideo;
        if (nScreenBtn) nScreenBtn.onclick = toggleScreenShare;
    }

    // ── Expose globals ─────────────────────────────────────────────────────
    window.startCall = startCall;
    window.answerCall = answerCall;
    window.cleanup = cleanup;
    window.rebindCallUI = rebindCallUI;

    let initCallInfo = null;
    try { initCallInfo = JSON.parse(localStorage.getItem('kentaro_active_call') || 'null'); } catch(e) {}
    if (initCallInfo && initCallInfo.isActive) {
        if (startBtn) startBtn.classList.add('hidden');
        if (endBtn)   endBtn.classList.remove('hidden');
        rebindCallUI();
    } else {
        if (startBtn) startBtn.classList.remove('hidden');
        if (endBtn)   endBtn.classList.add('hidden');
    }

    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('auto_answer') === 'true' || urlParams.get('auto_join') === 'true') {
        setTimeout(answerCall, 800);
    }

    // ── Auto Picture-in-Picture on Tab Switch ─────────────────────────────
    document.addEventListener('visibilitychange', () => {
        if (document.hidden && remoteVideo && remoteVideo.srcObject && !document.pictureInPictureElement) {
            try { remoteVideo.requestPictureInPicture().catch(() => {}); } catch(e) {}
        }
    });

    console.log('[voice_call] initialized. partnerId=', getPartnerId());
})();
