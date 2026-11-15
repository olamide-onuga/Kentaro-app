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
    let callTimeoutTimer = null;
    let callSeconds = 0;
    let isAudioMuted = false;
    let isVideoOff = false;
    let isSharingScreen = false;
    let currentFacingMode = 'user'; // 'user' (front) or 'environment' (back)
    let pendingCandidates = [];   // buffer ICE candidates before peer ready
    let pendingOffer = null;
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
    const flipCameraBtn     = document.getElementById('flipCameraBtn');
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

    // ── ICE servers (STUN + optional TURN from environment) ───────────────────
    const defaultIceServers = [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' },
        { urls: 'stun:stun2.l.google.com:19302' },
        { urls: 'stun:stun3.l.google.com:19302' }
    ];
    const iceServers = [...defaultIceServers];
    if (window.turnConfig && window.turnConfig.urls) {
        iceServers.push(window.turnConfig);
    }

    // ── Helpers ────────────────────────────────────────────────────────────
    function getPartnerId()   { return window.partnerId || null; }
    function getPartnerName() { return window.partnerName || 'Participant'; }

    function setStatus(text, colorClass) {
        if (callStatus) {
            callStatus.innerHTML = `<span class="w-2 h-2 rounded-full ${text === 'Connected' ? 'bg-green-500' : (text.includes('Calling') || text.includes('Connecting') ? 'bg-amber-500 animate-ping' : 'bg-gray-400')}"></span><span>${text}</span>`;
            callStatus.className = 'text-xs font-semibold px-3 py-1 rounded-full flex items-center gap-1.5 ' +
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

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            setStatus('WebRTC not supported', 'bg-red-900 text-red-100');
            alert('Your browser does not support WebRTC audio/video calls.');
            return Promise.reject(new Error('getUserMedia not supported'));
        }

        const hdConstraints = {
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
            video: { facingMode: currentFacingMode, width: { ideal: 1280 }, height: { ideal: 720 } }
        };

        return navigator.mediaDevices.getUserMedia(hdConstraints)
            .catch(err => {
                console.warn('[voice_call] HD video failed, retrying standard audio/video:', err);
                return navigator.mediaDevices.getUserMedia({
                    audio: true,
                    video: { facingMode: currentFacingMode }
                });
            })
            .catch(err => {
                console.warn('[voice_call] Video failed, retrying audio only:', err);
                return navigator.mediaDevices.getUserMedia({ audio: true, video: false });
            })
            .then(stream => {
                localStream = stream;
                window.localStream = stream;
                const vt = stream.getVideoTracks();
                if (vt.length) {
                    cameraTrack = vt[0];
                    currentVideoTrack = cameraTrack;
                    if (localPlaceholder) localPlaceholder.classList.add('hidden');
                } else {
                    cameraTrack = null;
                    currentVideoTrack = null;
                    if (localPlaceholder) localPlaceholder.classList.remove('hidden');
                }

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
                return stream;
            })
            .catch(err => {
                console.error('[voice_call] getUserMedia all fallbacks failed:', err);
                if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                    setStatus('Camera/Mic permission blocked', 'bg-red-950 text-red-300');
                    alert('Camera or microphone permission was blocked. Please allow permissions in your browser address bar and refresh.');
                } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                    setStatus('No camera/mic found', 'bg-amber-950 text-amber-300');
                } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
                    setStatus('Camera in use by other app', 'bg-red-950 text-red-300');
                    alert('Your camera or microphone is in use by another application.');
                } else {
                    setStatus('Media error: ' + err.name, 'bg-red-950 text-red-300');
                }
                throw err;
            });
    }

    // ── Switch Camera (Front/Rear on mobile) ─────────────────────────────────
    function switchCamera() {
        if (!localStream) return;
        currentFacingMode = (currentFacingMode === 'user') ? 'environment' : 'user';
        navigator.mediaDevices.getUserMedia({
            audio: false,
            video: { facingMode: currentFacingMode, width: { ideal: 1280 }, height: { ideal: 720 } }
        }).then(newStream => {
            const newTrack = newStream.getVideoTracks()[0];
            if (!newTrack) return;

            if (peer && currentVideoTrack) {
                try {
                    peer.replaceTrack(currentVideoTrack, newTrack, localStream);
                } catch(e) {
                    console.warn('[voice_call] peer.replaceTrack error:', e);
                }
            }

            if (cameraTrack) {
                try { cameraTrack.stop(); } catch(e) {}
            }
            cameraTrack = newTrack;
            currentVideoTrack = newTrack;

            // Update local stream tracks
            const oldTracks = localStream.getVideoTracks();
            oldTracks.forEach(t => localStream.removeTrack(t));
            localStream.addTrack(newTrack);

            if (localVideo) {
                localVideo.srcObject = localStream;
                localVideo.play().catch(() => {});
            }
            console.log('[voice_call] Switched camera to facingMode:', currentFacingMode);
        }).catch(err => {
            console.warn('[voice_call] switchCamera failed:', err);
        });
    }

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
            socket.emit('voice_signal', { target_user_id: getPartnerId(), signal: signal });
        });

        p.on('stream', remoteStream => {
            console.log('[voice_call] got remote stream!');
            attachRemoteStream(remoteStream);
        });

        p.on('connect', () => {
            console.log('[voice_call] peer connected');
            setStatus('Connected', 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300');
        });

        p.on('close', () => {
            console.log('[voice_call] peer closed');
            cleanup();
        });

        p.on('error', err => {
            console.error('[voice_call] peer error:', err);
            if (err.code === 'ERR_CONNECTION_FAILURE' || String(err).includes('Connection failed')) {
                setStatus('Connection failed', 'bg-red-950 text-red-300');
            }
        });

        // ICE Connection State Monitoring
        if (p._pc) {
            p._pc.oniceconnectionstatechange = () => {
                const state = p._pc.iceConnectionState;
                console.log('[voice_call] ICE state:', state);
                if (state === 'connected' || state === 'completed') {
                    setStatus('Connected', 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300');
                } else if (state === 'disconnected') {
                    setStatus('Reconnecting…', 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300');
                } else if (state === 'failed') {
                    setStatus('Connection failed', 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300');
                }
            };
        }

        peerReady = true;

        // Apply pending SDP offer/answer first
        if (pendingOffer) {
            const offer = pendingOffer;
            pendingOffer = null;
            try { p.signal(offer); } catch(e) { console.warn('[voice_call] Error applying pending offer:', e); }
        }

        // Flush any buffered ICE candidates AFTER SDP offer is set
        if (pendingCandidates.length) {
            const candidates = pendingCandidates.splice(0);
            candidates.forEach(sig => { try { p.signal(sig); } catch(e) { console.warn('[voice_call] candidate error:', e); } });
        }
        return p;
    }

    function attachRemoteStream(remoteStream) {
        remoteStreamStore = remoteStream;
        window.remoteStreamStore = remoteStream;
        if (callTimeoutTimer) { clearTimeout(callTimeoutTimer); callTimeoutTimer = null; }
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

        const floatingRemoteVideo = document.getElementById('floatingRemoteVideo');
        if (floatingRemoteVideo) {
            floatingRemoteVideo.srcObject = remoteStream;
            floatingRemoteVideo.play().catch(() => {});
        }

        // Strip auto_answer from URL so F5 won't re-trigger
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
        if (!targetId) { alert('Calling partner not identified.'); return; }

        setStatus(`Calling ${getPartnerName()}…`, 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300');
        if (startBtn) startBtn.classList.add('hidden');
        if (endBtn)   endBtn.classList.remove('hidden');

        // 35s call timeout
        if (callTimeoutTimer) clearTimeout(callTimeoutTimer);
        callTimeoutTimer = setTimeout(() => {
            if (!remoteStreamStore) {
                console.warn('[voice_call] Outgoing call timed out');
                setStatus('No answer from partner', 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300');
                endCall();
            }
        }, 35000);

        initMedia().then(() => {
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
            if (!peer) {
                peer = createPeer(stream, false);
            }
            socket.emit('call_accepted', { target_user_id: targetId });
        }).catch(() => cleanup());
    }

    // ── Socket signaling ───────────────────────────────────────────────────
    socket.on('call_invite', data => {
        const name = data.caller_name || 'Someone';
        setStatus(`Incoming call from ${name}…`, 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300');
    });

    socket.on('call_accepted', data => {
        const name = (data && data.from_name) || getPartnerName();
        setStatus(`Connecting to ${name}…`, 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300');
        if (callTimeoutTimer) { clearTimeout(callTimeoutTimer); callTimeoutTimer = null; }
        initMedia().then(stream => {
            peer = createPeer(stream, true); // initiator = true
        }).catch(() => cleanup());
    });

    socket.on('voice_signal', data => {
        const sig = data.signal;
        if (!sig) return;

        if (peer && peerReady) {
            try { peer.signal(sig); } catch(e) { console.warn('[voice_call] signal error:', e); }
        } else {
            if (sig.type === 'offer' || sig.type === 'answer') {
                pendingOffer = sig;
            } else if (sig.candidate) {
                pendingCandidates.push(sig);
            }

            if (sig.type === 'offer' && !peer) {
                initMedia().then(stream => {
                    peer = createPeer(stream, false);
                }).catch(() => cleanup());
            }
        }
    });

    socket.on('voice_call_end', data => {
        const name = (data && data.from_name) || getPartnerName();
        cleanup();
        setStatus(`Call ended by ${name}`, 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300');
    });

    socket.on('call_declined', data => {
        const name = (data && data.from_name) || getPartnerName();
        cleanup();
        setStatus(`${name} unavailable`, 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300');
    });

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
            if (remoteCameraNotice) {
                remoteCameraNotice.classList.remove('hidden');
                remoteCameraNotice.textContent = `📷 ${name}'s camera is off`;
            }
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
        const localMuteTag = document.getElementById('localMuteTag');
        if (localMuteTag) localMuteTag.classList.toggle('hidden', !isAudioMuted);
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
        if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
            alert('Screen sharing is not supported on your browser or mobile device.');
            return;
        }
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
                        screenBtn.title = 'Stop sharing';
                    }
                    broadcastPeerState();
                })
                .catch(err => console.log('Screen share cancelled:', err));
        }
    }

    function stopScreenSharing() {
        if (!isSharingScreen) return;
        if (screenStream) {
            screenStream.getTracks().forEach(t => { try { t.stop(); } catch(e) {} });
            screenStream = null;
        }
        if (peer && cameraTrack) {
            peer.replaceTrack(currentVideoTrack, cameraTrack, localStream);
            currentVideoTrack = cameraTrack;
        }
        if (localVideo && localStream) localVideo.srcObject = localStream;
        isSharingScreen = false;
        if (screenBtn) {
            screenBtn.classList.remove('bg-green-600', 'hover:bg-green-700');
            screenBtn.classList.add('bg-white/10', 'hover:bg-white/20');
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
        if (callTimeoutTimer) { clearTimeout(callTimeoutTimer); callTimeoutTimer = null; }
        try { localStorage.removeItem('kentaro_active_call'); } catch(e) {}

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

        // Hard stop all tracks so camera hardware light turns off
        if (localStream) {
            localStream.getTracks().forEach(t => { try { t.stop(); } catch(e) {} });
            localStream = null;
        }
        cameraTrack = null;
        currentVideoTrack = null;

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

        isAudioMuted = false;
        isVideoOff = false;
        if (muteBtn) {
            muteBtn.classList.remove('bg-red-600','hover:bg-red-700');
            muteBtn.classList.add('bg-white/10','hover:bg-white/20');
            if (muteIcon) muteIcon.textContent = '🎙️';
        }
        if (videoBtn) {
            videoBtn.classList.remove('bg-red-600','hover:bg-red-700');
            videoBtn.classList.add('bg-white/10','hover:bg-white/20');
            if (videoIcon) videoIcon.textContent = '📹';
        }
        setStatus('Ready', 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300');

        if (typeof window.syncActiveCallBanner === 'function') {
            window.syncActiveCallBanner();
        }
    }

    // Window unload cleanup (never leave mic/camera active)
    window.addEventListener('beforeunload', () => {
        if (peer || localStream) {
            const t = getPartnerId();
            if (t && socket) socket.emit('voice_call_end', { target_user_id: t });
            cleanup();
        }
    });
    window.addEventListener('pagehide', () => {
        if (peer || localStream) {
            const t = getPartnerId();
            if (t && socket) socket.emit('voice_call_end', { target_user_id: t });
            cleanup();
        }
    });

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
        div.innerHTML = `<div class="max-w-[80%] px-3 py-2 rounded-2xl text-xs ${isMe ? 'bg-black text-white dark:bg-white dark:text-black rounded-br-xs' : 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-bl-xs'}">
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
    if (startBtn)      startBtn.addEventListener('click', startCall);
    if (endBtn)        endBtn.addEventListener('click', endCall);
    if (muteBtn)       muteBtn.addEventListener('click', toggleAudio);
    if (videoBtn)      videoBtn.addEventListener('click', toggleVideo);
    if (flipCameraBtn) flipCameraBtn.addEventListener('click', switchCamera);
    if (screenBtn)     screenBtn.addEventListener('click', toggleScreenShare);

    const castFormBtn = document.getElementById('castFormBtn');
    if (castFormBtn) {
        castFormBtn.addEventListener('click', () => {
            const drawer = document.getElementById('formChecksDrawer');
            if (drawer) drawer.classList.toggle('hidden');
        });
    }

    // ── Expose globals ─────────────────────────────────────────────────────
    window.startCall = startCall;
    window.answerCall = answerCall;
    window.cleanup = cleanup;
    window.switchCamera = switchCamera;

    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('auto_answer') === 'true' || urlParams.get('auto_join') === 'true') {
        setTimeout(answerCall, 600);
    }

    // Auto Picture-in-Picture on Tab Switch
    document.addEventListener('visibilitychange', () => {
        if (document.hidden && remoteVideo && remoteVideo.srcObject && !document.pictureInPictureElement) {
            try { remoteVideo.requestPictureInPicture().catch(() => {}); } catch(e) {}
        }
    });

    console.log('[voice_call] initialized. partnerId=', getPartnerId());
})();
