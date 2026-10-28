/**
 * zalo.js - Interactive Client Logic for Zalo Web
 * Handles Authentication, Real-time Chat Sync, Voice Note Recording,
 * Image Upload, Code Snippet Display, Profile Updates, Contacts, Tasks,
 * In-chat Search, Conversation Info Panel, Emoji Picker, and Dark Mode.
 */

// Global Application State
const state = {
  currentUser: null,
  conversations: [],
  currentConversationId: null,
  currentConversation: null,
  messages: [],
  lastMessageId: 0,
  syncTimer: null,
  mediaRecorder: null,
  audioChunks: [],
  recordStartTime: null,
  recordTimerInterval: null,
  isRecording: false,
  activeFilter: 'all',       // 'all', 'groups', 'direct', 'unread'
  activeSubTab: 'priority',  // 'priority', 'other'
  activeMainTab: 'messages', // 'messages', 'contacts', 'tasks'
  soundEnabled: true,
  darkMode: false,
  replyingTo: null,          // Message object currently being replied to
  pinnedMessageId: null,     // Currently pinned message ID in active conversation

  // WebSocket & WebRTC Call State (Phase 3: LTM Core)
  chatSocket: null,
  isWsConnected: false,
  typingTimer: null,
  isTypingSent: false,
  localStream: null,
  peerConnection: null,
  callTimerInterval: null,
  callStartTime: null,
  isMicMuted: false,
  isCamOff: false,
  peerMicMuted: false,
  peerCamOff: false,
  isVirtualCam: false,
  isSwappedVideo: false,
  virtualAnimFrame: null,
  iceCandidatesQueue: [],
  callInitiatorId: null,
  callConnected: false,
  currentCallType: 'video', // 'voice' or 'video'
  pendingIncomingSignal: null,
  rtcConfig: {
    iceServers: [
      { urls: 'stun:stun.l.google.com:19302' },
      { urls: 'stun:stun1.l.google.com:19302' }
    ]
  },

  // Phase 4: UI/UX & Network Indicator Additions
  pingInterval: null,
  currentRtt: null,
  activeContextMsgId: null,
  forwardingMsg: null,
  selectedForwardConvIds: new Set(),
  pastedImageFile: null
};

// Emoji Data Library
const EMOJIS = {
  faces: ['😀', '😃', '😄', '😁', '😆', '😅', '🤣', '😂', '🙂', '🙃', '😉', '😊', '😇', '🥰', '😍', '🤩', '😘', '😗', '😋', '😛', '😜', '🤪', '😝', '🤗', '🤭', '🤫', '🤔', '🤐', '🤨', '😐', '😑', '😶', '😏', '😒', '🙄', '😬', '🤥', '😌', '😔', '😪', '🤤', '😴', '😷', '🤒', '🤕'],
  gestures: ['👍', '👎', '👌', '✌️', '🤞', '🤟', '🤘', '🤙', '👈', '👉', '👆', '👇', '☝️', '✋', '🤚', '🖐️', '🖖', '👋', '👏', '🙌', '👐', '🤲', '🤝', '🙏', '💪', '🦾', '👂', '👀', '✍️'],
  hearts: ['❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '🤎', '💔', '❣️', '💕', '💞', '💓', '💗', '💖', '💘', '💝', '💟', '💌'],
  fun: ['🔥', '⭐', '✨', '💥', '💯', '🎉', '🎊', '🚀', '💡', '☕', '💻', '📱', '📚', '🏆', '🥇', '🎯', '🔔', '📌', '💬', '📢', '🎧', '⚡', '🌈', '🍀', '🎓']
};

// ==============================================================================
// UTILITY FUNCTIONS & SOUND & CSRF
// ==============================================================================

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function showToast(message) {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'zalo-toast';
  toast.innerHTML = `<span>💬</span> <span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add('active');
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove('active');
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Gentle Web Audio API Notification Sound
function playNotificationSound() {
  if (!state.soundEnabled) return;
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = 'sine';
    osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
    osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.12); // A5

    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + 0.25);
  } catch (e) {
    // Audio context may be restricted by autoplay policy
  }
}

// ==============================================================================
// 1. AUTHENTICATION & PROFILE
// ==============================================================================

async function checkCurrentUser() {
  try {
    const res = await fetch('/api/me/');
    const data = await res.json();
    if (data.authenticated && data.user) {
      state.currentUser = data.user;
      updateUserUI();
      await loadConversations();
    } else {
      // Auto login as default demo user 'quan' for seamless experience
      await quickLogin('quan', false);
    }
  } catch (err) {
    console.error("Lỗi kiểm tra phiên đăng nhập:", err);
  }
}

function updateUserUI() {
  if (!state.currentUser) return;

  const avatarImg = document.getElementById('railUserAvatarImg');
  if (avatarImg && state.currentUser.avatar_url) {
    avatarImg.src = state.currentUser.avatar_url;
  }
  const modalAvatar = document.getElementById('profileModalAvatar');
  if (modalAvatar && state.currentUser.avatar_url) {
    modalAvatar.src = state.currentUser.avatar_url;
  }
  const popoverAvatar = document.getElementById('popoverUserAvatar');
  if (popoverAvatar && state.currentUser.avatar_url) {
    popoverAvatar.src = state.currentUser.avatar_url;
  }

  const popoverName = document.getElementById('popoverUserName');
  if (popoverName) popoverName.innerText = state.currentUser.display_name;

  const popoverPhone = document.getElementById('popoverUserPhone');
  if (popoverPhone) popoverPhone.innerText = state.currentUser.phone || `@${state.currentUser.username}`;

  // Populate profile form fields
  const profName = document.getElementById('profDisplayName');
  if (profName) profName.value = state.currentUser.display_name || '';

  const profBio = document.getElementById('profBio');
  if (profBio) profBio.value = state.currentUser.bio || '';

  const profPhone = document.getElementById('profPhone');
  if (profPhone) profPhone.value = state.currentUser.phone || '';

  const profGender = document.getElementById('profGender');
  if (profGender) profGender.value = state.currentUser.gender || 'nam';
}

async function quickLogin(username, notify = true) {
  try {
    const res = await fetch('/api/login/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ username: username, password: '123456' })
    });
    const data = await res.json();
    if (res.ok) {
      state.currentUser = data.user;
      updateUserUI();
      closeModal('authModal');
      const popover = document.getElementById('userAccountPopover');
      if (popover) popover.style.display = 'none';

      if (notify) showToast(`Đã chuyển sang tài khoản: ${data.user.display_name}`);
      await loadConversations();
    } else {
      if (notify) showToast(data.error || 'Đăng nhập thất bại!');
    }
  } catch (err) {
    console.error("Lỗi quickLogin:", err);
  }
}

async function handleLogout() {
  try {
    await fetch('/api/logout/', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') }
    });
    state.currentUser = null;
    state.currentConversationId = null;
    state.messages = [];
    if (state.syncTimer) clearInterval(state.syncTimer);
    showToast("Đã đăng xuất tài khoản!");
    openModal('authModal');
  } catch (err) {
    console.error("Lỗi logout:", err);
  }
}

function switchAuthTab(tab) {
  const btnLogin = document.getElementById('authTabLogin');
  const btnReg = document.getElementById('authTabRegister');
  const extra = document.getElementById('registerExtraFields');
  const btnSubmit = document.getElementById('btnSubmitAuth');
  const title = document.getElementById('authModalTitle');

  if (tab === 'register') {
    if (btnLogin) btnLogin.classList.remove('active');
    if (btnReg) btnReg.classList.add('active');
    if (extra) extra.style.display = 'flex';
    if (btnSubmit) btnSubmit.innerText = 'Đăng ký tài khoản';
    if (title) title.innerText = 'Đăng ký Zalo';
  } else {
    if (btnReg) btnReg.classList.remove('active');
    if (btnLogin) btnLogin.classList.add('active');
    if (extra) extra.style.display = 'none';
    if (btnSubmit) btnSubmit.innerText = 'Đăng nhập';
    if (title) title.innerText = 'Đăng nhập Zalo';
  }
}

async function handleAuthSubmit() {
  const isRegister = document.getElementById('authTabRegister')?.classList.contains('active');
  const username = document.getElementById('authUsername')?.value.trim();
  const password = document.getElementById('authPassword')?.value.trim();

  if (!username || !password) {
    showToast("Vui lòng điền đầy đủ tên đăng nhập và mật khẩu!");
    return;
  }

  if (isRegister) {
    const displayName = document.getElementById('regDisplayName')?.value.trim() || username;
    const phone = document.getElementById('regPhone')?.value.trim() || '';
    const avatarInput = document.getElementById('regAvatarInput');

    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    formData.append('display_name', displayName);
    formData.append('phone', phone);
    if (avatarInput && avatarInput.files.length > 0) {
      formData.append('avatar', avatarInput.files[0]);
    }

    try {
      const res = await fetch('/api/register/', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') },
        body: formData
      });
      const data = await res.json();
      if (res.ok) {
        state.currentUser = data.user;
        updateUserUI();
        closeModal('authModal');
        showToast("Đăng ký tài khoản thành công!");
        loadConversations();
      } else {
        showToast(data.error || "Đăng ký thất bại!");
      }
    } catch (err) {
      showToast("Lỗi kết nối máy chủ khi đăng ký!");
    }
  } else {
    try {
      const res = await fetch('/api/login/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      if (res.ok) {
        state.currentUser = data.user;
        updateUserUI();
        closeModal('authModal');
        showToast(`Đăng nhập thành công: ${data.user.display_name}`);
        loadConversations();
      } else {
        showToast(data.error || "Sai tên đăng nhập hoặc mật khẩu!");
      }
    } catch (err) {
      showToast("Lỗi kết nối máy chủ khi đăng nhập!");
    }
  }
}

async function saveProfile() {
  const formData = new FormData();
  formData.append('display_name', document.getElementById('profDisplayName')?.value.trim() || '');
  formData.append('bio', document.getElementById('profBio')?.value.trim() || '');
  formData.append('phone', document.getElementById('profPhone')?.value.trim() || '');
  formData.append('gender', document.getElementById('profGender')?.value || 'nam');

  const avatarInput = document.getElementById('modalAvatarInput');
  if (avatarInput && avatarInput.files.length > 0) {
    formData.append('avatar', avatarInput.files[0]);
  }

  try {
    const res = await fetch('/api/profile/update/', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
      body: formData
    });
    const data = await res.json();
    if (res.ok) {
      state.currentUser = data.user;
      updateUserUI();
      closeModal('profileModal');
      showToast("Đã cập nhật hồ sơ và ảnh đại diện thành công!");
      loadConversations();
    } else {
      showToast("Lỗi cập nhật hồ sơ!");
    }
  } catch (err) {
    showToast("Không thể kết nối cập nhật hồ sơ!");
  }
}

// ==============================================================================
// 2. CONVERSATIONS MANAGEMENT & FILTERS
// ==============================================================================

async function loadConversations(searchQuery = '') {
  try {
    let url = '/api/conversations/';
    if (searchQuery) url += `?q=${encodeURIComponent(searchQuery)}`;
    const res = await fetch(url);
    const data = await res.json();
    state.conversations = data;
    renderConversationsList();

    if (data.length > 0) {
      if (!state.currentConversationId) {
        const defaultConv = data.find(c => c.title.includes('Cloud')) || data[0];
        selectConversation(defaultConv.id);
      } else {
        const exists = data.find(c => c.id === state.currentConversationId);
        if (exists) selectConversation(exists.id);
      }
    } else {
      // Nếu chưa có hội thoại nào, mở Cloud của tôi
      openMyCloud();
    }
  } catch (err) {
    console.error("Lỗi tải danh sách hội thoại:", err);
  }
}

function renderConversationsList() {
  const container = document.getElementById('conversationsContainer');
  if (!container) return;
  container.innerHTML = '';

  let list = [...state.conversations];

  // Nếu người dùng vừa mở một cuộc hội thoại mới (từ Danh bạ/Tìm kiếm) chưa có trong danh sách
  if (state.currentConversation && !list.some(c => c.id === state.currentConversation.id)) {
    list.unshift({
      id: state.currentConversation.id,
      title: state.currentConversation.title,
      avatar_url: state.currentConversation.avatar_url,
      is_group: state.currentConversation.is_group,
      last_message: { preview: 'Bắt đầu cuộc trò chuyện' },
      time_label: 'Mới',
      unread_count: 0
    });
  }

  // Apply Filter Dropdown
  if (state.activeFilter === 'groups') {
    list = list.filter(c => c.is_group);
  } else if (state.activeFilter === 'direct') {
    list = list.filter(c => !c.is_group && !c.title.includes('Cloud'));
  } else if (state.activeFilter === 'unread') {
    list = list.filter(c => c.unread_count > 0);
  }

  // Apply SubTab Filter (Ưu tiên / Khác)
  if (state.activeSubTab === 'other') {
    list = list.filter(c => c.is_priority === false);
  } else {
    list = list.filter(c => c.is_priority !== false);
  }

  if (list.length === 0) {
    const isOtherTab = state.activeSubTab === 'other';
    const emptyIcon = isOtherTab ? '📁' : '💬';
    const emptyTitle = isOtherTab ? 'Mục "Khác" đang trống' : 'Chưa có cuộc trò chuyện nào';
    const emptyDesc = isOtherTab
      ? 'Bạn có thể chuyển các hội thoại từ người lạ hoặc ít quan trọng vào mục Khác.'
      : 'Vào mục <b>Danh bạ</b> hoặc tìm kiếm bạn bè để bắt đầu nhắn tin!';

    container.innerHTML = `
      <div style="padding: 36px 16px; text-align: center; color: var(--zalo-text-muted); font-size: 13px;">
        <div style="font-size: 28px; margin-bottom: 8px;">${emptyIcon}</div>
        <div style="font-weight: 600; margin-bottom: 4px; color: var(--zalo-text-main);">${emptyTitle}</div>
        <div>${emptyDesc}</div>
      </div>
    `;
    return;
  }

  list.forEach(conv => {
    const isActive = conv.id === state.currentConversationId;
    const isPinned = conv.is_pinned === true;
    const isMuted = conv.is_muted === true;
    const pinBadge = isPinned ? `<span class="pinned-badge-icon" title="Đã ghim">📌</span>` : '';
    const muteBadge = isMuted ? `<span class="muted-badge-icon" title="Đã tắt chuông">🔕</span>` : '';

    const item = document.createElement('div');
    item.className = `conversation-item ${isActive ? 'active' : ''} ${isPinned ? 'is-pinned' : ''}`;
    item.onclick = () => selectConversation(conv.id);

    const snippetText = conv.last_message ? conv.last_message.preview : 'Bắt đầu cuộc trò chuyện';
    const unreadHtml = conv.unread_count > 0 ? `<div class="unread-badge">${conv.unread_count}</div>` : '';
    const groupBadge = conv.is_group ? `<span class="group-badge-icon">👥</span>` : '';

    item.innerHTML = `
      <div class="item-avatar-wrapper">
        <img src="${conv.avatar_url}" alt="Avatar">
        ${groupBadge}
      </div>
      <div class="item-details">
        <div class="item-top-row">
          <div class="item-name" title="${escapeHtml(conv.title)}">${escapeHtml(conv.title)}${pinBadge}${muteBadge}</div>
          <div class="item-time">${conv.time_label || ''}</div>
        </div>
        <div class="item-bottom-row">
          <div class="item-snippet" title="${escapeHtml(snippetText)}">${escapeHtml(snippetText)}</div>
          ${unreadHtml}
        </div>
      </div>
    `;
    container.appendChild(item);
  });
}

async function selectConversation(convId) {
  state.currentConversationId = convId;
  cancelReply();
  renderConversationsList();

  try {
    const res = await fetch(`/api/conversations/${convId}/`);
    const conv = await res.json();
    state.currentConversation = conv;

    // Update Header
    const chatTitle = document.getElementById('currentChatTitle');
    if (chatTitle) chatTitle.innerText = conv.title;

    const chatAvatar = document.getElementById('currentChatAvatar');
    if (chatAvatar) chatAvatar.src = conv.avatar_url;

    const chatSubtitle = document.getElementById('currentChatSubtitle');
    if (chatSubtitle) {
      chatSubtitle.innerHTML = conv.is_group
        ? `<span class="online-indicator"></span> ${conv.member_count} thành viên`
        : `<span class="online-indicator"></span> Đang hoạt động`;
    }

    const chatInput = document.getElementById('chatInputText');
    if (chatInput) chatInput.placeholder = `Nhập @, tin nhắn tới ${conv.title}`;

    // Update Pinned Message Banner
    updatePinnedMessageBanner(conv.pinned_message);

    // Update Right Info Sidebar if open
    updateConversationInfoPanel(conv);

    await loadMessages(convId);
    connectWebSocket(convId);
    startSync();
  } catch (err) {
    console.error("Lỗi khi chọn hội thoại:", err);
  }
}

// Update the Conversation Information Right Drawer
function updateConversationInfoPanel(conv) {
  const panel = document.getElementById('chatInfoSidebar');
  if (!panel) return;

  const panelAvatar = document.getElementById('infoPanelAvatar');
  if (panelAvatar) panelAvatar.src = conv.avatar_url;

  const panelTitle = document.getElementById('infoPanelTitle');
  if (panelTitle) panelTitle.innerText = conv.title;

  const panelSub = document.getElementById('infoPanelSubtitle');
  if (panelSub) {
    panelSub.innerText = conv.is_group ? `${conv.member_count} thành viên` : 'Hội thoại trực tiếp 1-1';
  }

  // Members
  const memberCountSpan = document.getElementById('infoMemberCount');
  if (memberCountSpan) memberCountSpan.innerText = conv.members ? conv.members.length : 0;

  const membersContainer = document.getElementById('infoMembersContainer');
  if (membersContainer && conv.members) {
    membersContainer.innerHTML = '';
    conv.members.forEach(m => {
      const row = document.createElement('div');
      row.className = 'info-member-row';
      const roleLabel = m.role === 'admin' ? '<span class="info-role-badge">Trưởng nhóm</span>' : '';
      row.innerHTML = `
        <div class="info-member-left">
          <img src="${m.avatar_url}" alt="${escapeHtml(m.display_name)}">
          <span class="info-member-name">${escapeHtml(m.display_name)}</span>
        </div>
        ${roleLabel}
      `;
      membersContainer.appendChild(row);
    });
  }

  // Media
  const mediaCountSpan = document.getElementById('infoMediaCount');
  if (mediaCountSpan) mediaCountSpan.innerText = conv.shared_media ? conv.shared_media.length : 0;

  const mediaContainer = document.getElementById('infoMediaContainer');
  if (mediaContainer && conv.shared_media) {
    mediaContainer.innerHTML = '';
    conv.shared_media.forEach(m => {
      if (m.type === 'image' && m.url) {
        const img = document.createElement('img');
        img.className = 'info-media-thumb';
        img.src = m.url;
        img.onclick = () => openLightbox(m.url);
        mediaContainer.appendChild(img);
      }
    });
  }

  // Files
  const filesCountSpan = document.getElementById('infoFilesCount');
  if (filesCountSpan) filesCountSpan.innerText = conv.shared_files ? conv.shared_files.length : 0;

  const filesContainer = document.getElementById('infoFilesContainer');
  if (filesContainer && conv.shared_files) {
    filesContainer.innerHTML = '';
    conv.shared_files.forEach(f => {
      const a = document.createElement('a');
      a.className = 'info-file-item';
      a.href = f.url || '#';
      a.target = '_blank';
      a.download = f.name;
      a.innerHTML = `
        <span>📄</span>
        <div style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
          <div>${escapeHtml(f.name)}</div>
          <div style="font-size:11px; color:var(--zalo-text-muted);">${f.size || ''}</div>
        </div>
      `;
      filesContainer.appendChild(a);
    });
  }

  // Update quick action buttons state (Pin, Mute, Priority, Add Member)
  const btnPin = document.getElementById('btnPinChat');
  const pinIcon = document.getElementById('pinActionIcon');
  const pinText = document.getElementById('pinActionText');
  if (btnPin) {
    if (conv.is_pinned) {
      btnPin.classList.add('active');
      if (pinText) pinText.innerText = 'Bỏ ghim';
    } else {
      btnPin.classList.remove('active');
      if (pinText) pinText.innerText = 'Ghim';
    }
  }

  const btnMute = document.getElementById('btnMuteNotif');
  const muteIcon = document.getElementById('muteActionIcon');
  const muteText = document.getElementById('muteActionText');
  if (btnMute) {
    if (conv.is_muted) {
      btnMute.classList.add('active');
      if (muteIcon) muteIcon.innerText = '🔕';
      if (muteText) muteText.innerText = 'Bật chuông';
    } else {
      btnMute.classList.remove('active');
      if (muteIcon) muteIcon.innerText = '🔔';
      if (muteText) muteText.innerText = 'Thông báo';
    }
  }

  const btnPriority = document.getElementById('btnTogglePriority');
  const priorityIcon = document.getElementById('priorityActionIcon');
  const priorityText = document.getElementById('priorityActionText');
  if (btnPriority) {
    if (conv.is_priority !== false) {
      btnPriority.classList.add('active');
      if (priorityIcon) priorityIcon.innerText = '⭐';
      if (priorityText) priorityText.innerText = 'Ưu tiên';
    } else {
      btnPriority.classList.remove('active');
      if (priorityIcon) priorityIcon.innerText = '📁';
      if (priorityText) priorityText.innerText = 'Khác';
    }
  }

  const btnAddMember = document.getElementById('btnAddMemberBtn');
  if (btnAddMember) {
    if (!conv.is_group) {
      btnAddMember.style.opacity = '0.4';
      btnAddMember.title = 'Chỉ nhóm chat mới có thể thêm thành viên';
    } else {
      btnAddMember.style.opacity = '1';
      btnAddMember.title = 'Thêm thành viên vào nhóm';
    }
  }
}

// ==============================================================================
// 2.1 CONVERSATION ACTIONS (PIN, MUTE, PRIORITY, ADD MEMBER)
// ==============================================================================

async function togglePinConversation() {
  if (!state.currentConversationId) return;
  try {
    const res = await fetch(`/api/conversations/${state.currentConversationId}/toggle_pin/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') }
    });
    const data = await res.json();
    if (res.ok) {
      if (state.currentConversation) state.currentConversation.is_pinned = data.is_pinned;
      showToast(data.message);
      updateConversationInfoPanel(state.currentConversation);
      await loadConversations();
    }
  } catch (err) {
    showToast("Lỗi khi ghim cuộc trò chuyện!");
  }
}

async function toggleMuteConversation() {
  if (!state.currentConversationId) return;
  try {
    const res = await fetch(`/api/conversations/${state.currentConversationId}/toggle_mute/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') }
    });
    const data = await res.json();
    if (res.ok) {
      if (state.currentConversation) state.currentConversation.is_muted = data.is_muted;
      showToast(data.message);
      updateConversationInfoPanel(state.currentConversation);
      await loadConversations();
    }
  } catch (err) {
    showToast("Lỗi khi thay đổi trạng thái thông báo!");
  }
}

async function togglePriorityConversation() {
  if (!state.currentConversationId) return;
  try {
    const res = await fetch(`/api/conversations/${state.currentConversationId}/toggle_priority/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') }
    });
    const data = await res.json();
    if (res.ok) {
      if (state.currentConversation) state.currentConversation.is_priority = data.is_priority;
      showToast(data.message);
      updateConversationInfoPanel(state.currentConversation);
      await loadConversations();
    }
  } catch (err) {
    showToast("Lỗi khi phân loại hội thoại!");
  }
}

async function openAddMemberModal() {
  if (!state.currentConversation) {
    showToast("Vui lòng chọn một cuộc trò chuyện nhóm trước!");
    return;
  }
  if (!state.currentConversation.is_group) {
    showToast("Tính năng này chỉ áp dụng cho nhóm trò chuyện!");
    return;
  }
  const title = document.getElementById('addMemberModalTitle');
  if (title) title.innerText = `Thêm thành viên vào "${state.currentConversation.title}"`;
  openModal('addMemberModal');
  loadUsersForAddMember();
}

async function loadUsersForAddMember(query = '') {
  const container = document.getElementById('addMemberListContainer');
  if (!container) return;
  container.innerHTML = '<div style="padding:16px; text-align:center; color:var(--zalo-text-muted);">Đang tải danh sách bạn bè...</div>';

  try {
    const url = query ? `/api/users/search/?q=${encodeURIComponent(query)}` : '/api/users/search/';
    const res = await fetch(url);
    const users = await res.json();
    container.innerHTML = '';

    const currentMemberIds = new Set(
      (state.currentConversation?.members || []).map(m => m.id)
    );

    const availableUsers = users.filter(u => !currentMemberIds.has(u.id));

    if (availableUsers.length === 0) {
      container.innerHTML = `
        <div style="padding:24px 16px; text-align:center; color:var(--zalo-text-muted);">
          <div style="font-size:24px; margin-bottom:6px;">👥</div>
          <div>Tất cả bạn bè đã tham gia nhóm này rồi!</div>
        </div>
      `;
      return;
    }

    availableUsers.forEach(u => {
      const card = document.createElement('div');
      card.className = 'contact-item-card';
      card.innerHTML = `
        <div class="contact-item-left">
          <div class="contact-avatar-wrapper">
            <img src="${u.avatar_url}" alt="${escapeHtml(u.display_name)}">
            ${u.is_online ? '<div class="contact-online-dot"></div>' : ''}
          </div>
          <div class="contact-info-text">
            <div class="contact-name">${escapeHtml(u.display_name)}</div>
            <div class="contact-sub">${u.phone || `@${u.username}`}</div>
          </div>
        </div>
        <button class="btn-primary" style="padding: 5px 14px; font-size: 12.5px;">Thêm</button>
      `;
      const btn = card.querySelector('button');
      btn.onclick = async () => {
        btn.disabled = true;
        btn.innerText = 'Đang thêm...';
        await addMemberToCurrentGroup(u.id, u.display_name);
      };
      container.appendChild(card);
    });
  } catch (err) {
    container.innerHTML = '<div style="padding:12px; color:#d32f2f;">Lỗi khi tải danh sách người dùng!</div>';
  }
}

async function addMemberToCurrentGroup(userId, displayName) {
  try {
    const res = await fetch(`/api/conversations/${state.currentConversationId}/add_member/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ user_id: userId })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message || `Đã thêm ${displayName} vào nhóm!`);
      await selectConversation(state.currentConversationId);
      loadUsersForAddMember();
    } else {
      showToast(data.error || "Thêm thành viên thất bại!");
    }
  } catch (err) {
    showToast("Lỗi kết nối khi thêm thành viên!");
  }
}

// 3. MESSAGES HISTORY & RENDERING
// ==============================================================================

function renderSkeletonTimeline() {
  const timeline = document.getElementById('chatTimeline');
  if (!timeline) return;
  timeline.innerHTML = `
    <div class="skeleton-timeline">
      <div class="skeleton-msg-row other">
        <div class="skeleton-shimmer skeleton-avatar"></div>
        <div class="skeleton-shimmer skeleton-bubble w-med"></div>
      </div>
      <div class="skeleton-msg-row me">
        <div class="skeleton-shimmer skeleton-bubble w-short"></div>
      </div>
      <div class="skeleton-msg-row other">
        <div class="skeleton-shimmer skeleton-avatar"></div>
        <div class="skeleton-shimmer skeleton-bubble w-long"></div>
      </div>
      <div class="skeleton-msg-row me">
        <div class="skeleton-shimmer skeleton-bubble w-med"></div>
      </div>
      <div class="skeleton-msg-row other">
        <div class="skeleton-shimmer skeleton-avatar"></div>
        <div class="skeleton-shimmer skeleton-bubble w-short"></div>
      </div>
    </div>
  `;
}

async function loadMessages(convId) {
  renderSkeletonTimeline();
  try {
    const res = await fetch(`/api/conversations/${convId}/messages/`);
    const data = await res.json();
    state.messages = data;
    if (data.length > 0) {
      state.lastMessageId = data[data.length - 1].id;
    } else {
      state.lastMessageId = 0;
    }
    renderTimeline();
    scrollChatToBottom();
    if (state.lastMessageId) {
      sendMarkRead(state.lastMessageId);
    }
  } catch (err) {
    console.error("Lỗi tải tin nhắn:", err);
  }
}

function getMessageDateKey(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

function formatDateLabel(dateStr) {
  if (!dateStr) return 'Gần đây';
  const d = new Date(dateStr);
  const now = new Date();

  const isToday = d.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = d.toDateString() === yesterday.toDateString();

  if (isToday) return 'Hôm nay';
  if (isYesterday) return 'Hôm qua';

  const dayNames = ['Chủ Nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];
  const dayName = dayNames[d.getDay()];
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yyyy = d.getFullYear();
  return `${dayName}, ${dd}/${mm}/${yyyy}`;
}

function renderTimeline() {
  const timeline = document.getElementById('chatTimeline');
  if (!timeline) return;

  if (state.messages.length === 0) {
    const convTitle = state.currentConversation?.title || 'Cuộc trò chuyện';
    const convAvatar = state.currentConversation?.avatar_url || 'https://ui-avatars.com/api/?name=Chat&background=0068ff&color=ffffff';
    timeline.innerHTML = `
      <div class="empty-chat-state" style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; text-align:center; padding:32px 16px; color:var(--zalo-text-muted);">
        <img src="${convAvatar}" style="width:72px; height:72px; border-radius:50%; object-fit:cover; margin-bottom:14px; box-shadow:0 4px 12px rgba(0,0,0,0.08);">
        <h4 style="margin:0 0 6px 0; color:var(--zalo-text-main); font-size:16px; font-weight:600;">${escapeHtml(convTitle)}</h4>
        <p style="margin:0; font-size:13px; max-width:320px; line-height:1.5;">Chưa có tin nhắn nào trong cuộc trò chuyện này.<br>Hãy gửi lời chào hoặc nhập tin nhắn bên dưới để bắt đầu!</p>
      </div>
    `;
    return;
  }

  timeline.innerHTML = '';
  let lastDateKey = null;

  state.messages.forEach(msg => {
    const msgDateKey = getMessageDateKey(msg.created_at);
    if (msgDateKey && msgDateKey !== lastDateKey) {
      lastDateKey = msgDateKey;
      const dateDivider = document.createElement('div');
      dateDivider.className = 'date-divider';
      dateDivider.innerHTML = `<span class="date-pill">${formatDateLabel(msg.created_at)}</span>`;
      timeline.appendChild(dateDivider);
    }

    // System Message (Notification of group events)
    if (msg.message_type === 'system') {
      const sysDiv = document.createElement('div');
      sysDiv.className = 'system-message-row';
      sysDiv.style.cssText = 'display:flex; justify-content:center; margin:8px 0;';
      sysDiv.innerHTML = `<span style="background:rgba(0,0,0,0.06); color:var(--zalo-text-muted); font-size:12px; padding:3px 12px; border-radius:12px;">${escapeHtml(msg.content)}</span>`;
      timeline.appendChild(sysDiv);
      return;
    }

    const isMe = msg.is_me;
    const isRecalled = msg.is_recalled;
    const row = document.createElement('div');
    row.className = `message-row ${isMe ? 'me' : 'other'} ${isRecalled ? 'recalled' : ''}`;
    row.dataset.msgId = msg.id;

    let bodyHtml = '';

    if (isRecalled) {
      bodyHtml = `
        <div class="msg-recalled-text">
          <svg viewBox="0 0 24 24" style="width:14px;height:14px;fill:currentColor;"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8 0-1.85.63-3.55 1.69-4.9L16.9 18.31C15.55 19.37 13.85 20 12 20zm6.31-3.1L7.1 5.69C8.45 4.63 10.15 4 12 4c4.42 0 8 3.58 8 8 0 1.85-.63 3.55-1.69 4.9z"/></svg>
          <span>Tin nhắn đã được thu hồi</span>
        </div>
      `;
    } else if (msg.message_type === 'code') {
      bodyHtml = `
        <div class="code-snippet-box">
          <div class="code-header-bar">
            <span class="code-language-tag">${escapeHtml(msg.code_language || 'CODE')}</span>
            <button class="copy-code-btn" onclick="copyCode(this)">Sao chép mã</button>
          </div>
          <pre><code>${escapeHtml(msg.content)}</code></pre>
        </div>
      `;
    } else if (msg.message_type === 'image') {
      const imgUrl = msg.attachment_url || '';
      bodyHtml = `
        <div class="msg-image-card" onclick="openLightbox('${imgUrl}')">
          <img src="${imgUrl}" alt="Hình ảnh">
        </div>
        ${msg.content && msg.content !== msg.attachment_name ? `<div style="margin-top:4px;">${escapeHtml(msg.content)}</div>` : ''}
      `;
    } else if (msg.message_type === 'audio') {
      const audioUrl = msg.attachment_url || '';
      bodyHtml = `
        <div class="msg-audio-card">
          <button class="audio-play-btn" onclick="togglePlayAudio(this, '${audioUrl}')">▶</button>
          <div class="audio-waveform-canvas">
            <div class="wave-bar"></div>
            <div class="wave-bar" style="height:14px;"></div>
            <div class="wave-bar" style="height:10px;"></div>
            <div class="wave-bar" style="height:18px;"></div>
            <div class="wave-bar" style="height:12px;"></div>
            <div class="wave-bar" style="height:16px;"></div>
            <div class="wave-bar" style="height:8px;"></div>
          </div>
          <span class="audio-duration-label">0:15</span>
        </div>
      `;
    } else if (msg.message_type === 'file') {
      const fileUrl = msg.attachment_url || '#';
      bodyHtml = `
        <a class="msg-file-card" href="${fileUrl}" target="_blank" download="${escapeHtml(msg.attachment_name || 'file')}">
          <div class="file-icon-box">📄</div>
          <div class="file-details">
            <div class="file-name-text">${escapeHtml(msg.attachment_name || 'Tệp đính kèm')}</div>
            <div class="file-size-text">${escapeHtml(msg.attachment_size || 'Tải về')}</div>
          </div>
        </a>
      `;
    } else if (msg.message_type === 'call') {
      const isCallVideo = msg.code_language === 'video';
      const status = msg.call_status || 'completed';
      let callTitle = '';
      let callSubtitle = '';

      if (status === 'completed') {
        callTitle = isMe 
          ? (isCallVideo ? "Cuộc gọi video đi" : "Cuộc gọi thoại đi")
          : (isCallVideo ? "Cuộc gọi video đến" : "Cuộc gọi thoại đến");
        callSubtitle = msg.formatted_duration ? `Thời gian: ${msg.formatted_duration}` : (msg.content || 'Đã kết nối');
      } else if (status === 'missed') {
        callTitle = isMe ? "Cuộc gọi không nhấc máy" : "Cuộc gọi nhỡ";
        callSubtitle = isMe ? "Đối phương không trả lời" : `Bạn đã bỏ lỡ cuộc gọi ${isCallVideo ? 'video' : 'thoại'}`;
      } else if (status === 'rejected') {
        callTitle = isMe ? "Cuộc gọi bị từ chối" : "Đã từ chối cuộc gọi";
        callSubtitle = "Máy bận";
      } else {
        callTitle = isCallVideo ? "Cuộc gọi video" : "Cuộc gọi thoại";
        callSubtitle = msg.content || "Đã kết thúc";
      }

      const iconSvg = isCallVideo
        ? `<svg viewBox="0 0 24 24"><path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/></svg>`
        : `<svg viewBox="0 0 24 24"><path d="M20.01 15.38c-1.23 0-2.42-.2-3.53-.56-.35-.12-.74-.03-1.01.24l-1.57 1.97c-2.83-1.35-5.48-3.9-6.89-6.83l1.95-1.66c.27-.28.35-.67.24-1.02-.37-1.11-.56-2.3-.56-3.53 0-.54-.45-.99-.99-.99H4.19C3.65 3 3 3.24 3 3.99 3 13.28 10.73 21 20.01 21c.71 0 .99-.63.99-1.18v-3.45c0-.54-.45-.99-.99-.99z"/></svg>`;

      bodyHtml = `
        <div class="msg-call-card ${status === 'missed' ? 'is-missed' : ''}">
          <div class="call-card-icon-box ${status === 'missed' ? 'missed' : (isMe ? 'outgoing' : 'incoming')}">
            ${iconSvg}
          </div>
          <div class="call-card-info">
            <div class="call-card-title">${escapeHtml(callTitle)}</div>
            <div class="call-card-subtitle">${escapeHtml(callSubtitle)}</div>
          </div>
          <button class="call-card-retry-btn" onclick="startWebRTCCall('${isCallVideo ? 'video' : 'voice'}')" title="Gọi lại">
            Gọi lại
          </button>
        </div>
      `;
    } else {
      bodyHtml = `<div>${escapeHtml(msg.content)}</div>`;
    }

    // Quoted reply card if replying to a message
    let quoteHtml = '';
    if (msg.reply_to_details && !isRecalled) {
      const qSender = escapeHtml(msg.reply_to_details.sender_name || 'Người dùng');
      let qSnippet = msg.reply_to_details.content || '';
      if (msg.reply_to_details.message_type === 'image') qSnippet = '[Hình ảnh]';
      else if (msg.reply_to_details.message_type === 'file') qSnippet = '[Tệp tin]';
      else if (msg.reply_to_details.message_type === 'audio') qSnippet = '[Tin nhắn thoại]';
      else if (msg.reply_to_details.message_type === 'code') qSnippet = '[Đoạn mã code]';

      quoteHtml = `
        <div class="msg-quote-card" onclick="scrollToMessage(${msg.reply_to_details.id})" title="Nhấp để cuộn tới tin nhắn được trích dẫn">
          <div class="quote-body">
            <div class="quote-sender">${qSender}</div>
            <div class="quote-snippet">${escapeHtml(qSnippet)}</div>
          </div>
        </div>
      `;
    }

    // Reaction pills underneath the bubble
    let reactionsHtml = '';
    if (msg.reactions && msg.reactions.length > 0) {
      const currentUsername = state.currentUser ? state.currentUser.username : '';
      const pills = msg.reactions.map(r => {
        const isMine = r.users && r.users.includes(currentUsername);
        const usersTooltip = escapeHtml(r.users.join(', '));
        return `
          <span class="reaction-pill ${isMine ? 'reacted-by-me' : ''}" 
                title="${usersTooltip}" 
                onclick="toggleReaction(${msg.id}, '${r.emoji}')">
            ${r.emoji} <span class="react-count">${r.count}</span>
          </span>
        `;
      }).join('');
      reactionsHtml = `<div class="msg-reactions-row">${pills}</div>`;
    }

    // Floating actions toolbar on message hover
    const actionsToolbarHtml = `
      <div class="msg-actions-toolbar">
        <div class="quick-reactions">
          <button type="button" class="react-btn" onclick="toggleReaction(${msg.id}, '❤️')" title="Yêu thích">❤️</button>
          <button type="button" class="react-btn" onclick="toggleReaction(${msg.id}, '👍')" title="Thích">👍</button>
          <button type="button" class="react-btn" onclick="toggleReaction(${msg.id}, '😂')" title="Haha">😂</button>
          <button type="button" class="react-btn" onclick="toggleReaction(${msg.id}, '😮')" title="Wow">😮</button>
          <button type="button" class="react-btn" onclick="toggleReaction(${msg.id}, '😢')" title="Buồn">😢</button>
          <button type="button" class="react-btn" onclick="toggleReaction(${msg.id}, '😡')" title="Phẫn nộ">😡</button>
        </div>
        <div class="action-divider"></div>
        <button type="button" class="msg-action-icon-btn" onclick="startReplyMessage(${msg.id})" title="Trả lời">
          <svg viewBox="0 0 24 24"><path d="M10 9V5l-7 7 7 7v-4.1c5 0 8.5 1.6 11 5.1-1-5-4-10-11-11z"/></svg>
        </button>
        <button type="button" class="msg-action-icon-btn" onclick="pinConversationMessage(${msg.id})" title="Ghim tin nhắn">
          <svg viewBox="0 0 24 24"><path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"/></svg>
        </button>
        <div class="msg-more-dropdown-container">
          <button type="button" class="msg-action-icon-btn btn-more" onclick="toggleMsgMoreMenu(event, ${msg.id})" title="Thao tác khác">
            <svg viewBox="0 0 24 24"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>
          </button>
          <div class="msg-more-menu" id="msgMoreMenu_${msg.id}">
            <div class="msg-more-item" onclick="openForwardModal(${msg.id})"><span>↗️ Chuyển tiếp</span></div>
            ${isMe && !isRecalled ? `<div class="msg-more-item text-danger" onclick="recallMessage(${msg.id})"><span>🚫 Thu hồi</span></div>` : ''}
            <div class="msg-more-item" onclick="deleteMessageForMe(${msg.id})"><span>🗑️ Xóa ở phía tôi</span></div>
            <div class="msg-more-item" onclick="copyMessageContent(${msg.id})"><span>📋 Sao chép tin nhắn</span></div>
          </div>
        </div>
      </div>
    `;

    // Compute delivery & read receipt status
    let statusHtml = '';
    if (isMe && !isRecalled) {
      const members = state.currentConversation?.members || [];
      const otherMembers = members.filter(m => m.id !== (state.currentUser ? state.currentUser.id : null));

      if (state.currentConversation?.is_group) {
        const readers = otherMembers.filter(m => (m.last_read_message_id || 0) >= msg.id);
        if (readers.length > 0) {
          const names = readers.map(r => r.display_name).join(', ');
          const avatarImgs = readers.slice(0, 3).map(r => `<img src="${r.avatar_url}" title="${escapeHtml(r.display_name)} đã xem" />`).join('');
          const moreCount = readers.length > 3 ? `<span style="font-size:10px; margin-left:2px; font-weight:700;">+${readers.length - 3}</span>` : '';
          statusHtml = `
            <div class="msg-status-indicator seen" title="${escapeHtml(names)} đã xem">
              <span class="msg-status-text">Đã xem</span>
              <div class="seen-avatars-cluster">${avatarImgs}${moreCount}</div>
            </div>
          `;
        } else {
          statusHtml = `
            <div class="msg-status-indicator delivered" title="Đã nhận">
              <span class="msg-status-text">Đã nhận</span>
              <span>✓✓</span>
            </div>
          `;
        }
      } else {
        const other = otherMembers[0];
        if (other && (other.last_read_message_id || 0) >= msg.id) {
          statusHtml = `
            <div class="msg-status-indicator seen" title="${escapeHtml(other.display_name)} đã xem">
              <span class="msg-status-text">Đã xem</span>
              <img class="seen-mini-avatar" src="${other.avatar_url}" alt="${escapeHtml(other.display_name)}">
            </div>
          `;
        } else {
          statusHtml = `
            <div class="msg-status-indicator delivered" title="Đã nhận">
              <span class="msg-status-text">Đã nhận</span>
              <span>✓✓</span>
            </div>
          `;
        }
      }
    }

    row.innerHTML = `
      ${actionsToolbarHtml}
      <img class="msg-avatar" src="${msg.sender_avatar}" alt="${escapeHtml(msg.sender_name)}">
      <div class="msg-content-wrapper">
        <span class="msg-sender-name">${escapeHtml(msg.sender_name)}</span>
        <div class="msg-bubble">
          ${quoteHtml}
          ${bodyHtml}
          <div class="msg-meta-row">
            <span>${msg.formatted_time || ''}</span>
            ${statusHtml}
          </div>
        </div>
        ${reactionsHtml}
      </div>
    `;

    timeline.appendChild(row);
  });
}

// --------------------------------------------------------------------------
// PHASE 2 ACTIONS: Reply, Reaction, Pin, Recall, Delete
// --------------------------------------------------------------------------

function startReplyMessage(msgId) {
  const msg = state.messages.find(m => m.id === msgId);
  if (!msg) return;
  state.replyingTo = msg;
  const bar = document.getElementById('replyPreviewBar');
  const senderSpan = document.getElementById('replyQuoteSender');
  const snippetSpan = document.getElementById('replyQuoteSnippet');
  if (bar && senderSpan && snippetSpan) {
    senderSpan.innerText = msg.sender_name;
    let snippet = msg.content;
    if (msg.is_recalled) snippet = 'Tin nhắn đã được thu hồi';
    else if (msg.message_type === 'image') snippet = '[Hình ảnh]';
    else if (msg.message_type === 'file') snippet = `[Tệp tin] ${msg.attachment_name || ''}`;
    else if (msg.message_type === 'audio') snippet = '[Tin nhắn thoại]';
    else if (msg.message_type === 'code') snippet = `[Đoạn mã ${msg.code_language || 'Code'}]`;
    snippetSpan.innerText = snippet;
    bar.style.display = 'flex';
  }
  const chatInput = document.getElementById('chatInputText');
  if (chatInput) chatInput.focus();
}

function cancelReply() {
  state.replyingTo = null;
  const bar = document.getElementById('replyPreviewBar');
  if (bar) bar.style.display = 'none';
}

function scrollToMessage(msgId) {
  if (!msgId) return;
  const row = document.querySelector(`.message-row[data-msg-id="${msgId}"]`);
  if (row) {
    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const bubble = row.querySelector('.msg-bubble');
    if (bubble) {
      bubble.classList.add('highlight-flash');
      setTimeout(() => bubble.classList.remove('highlight-flash'), 2000);
    }
  } else {
    showToast("Tin nhắn không nằm trong các tin nhắn gần đây.");
  }
}

// Floating reaction burst animation
function triggerFloatingReaction(msgId, emoji) {
  if (!emoji) return;
  const row = document.querySelector(`.message-row[data-msg-id="${msgId}"]`);
  if (!row) return;

  const bubble = row.querySelector('.msg-bubble');
  if (!bubble) return;

  const floating = document.createElement('div');
  floating.className = 'floating-reaction-bubble';
  floating.innerText = emoji;

  const rect = bubble.getBoundingClientRect();
  floating.style.position = 'fixed';
  floating.style.left = `${rect.left + rect.width / 2 - 13}px`;
  floating.style.top = `${rect.top - 12}px`;

  document.body.appendChild(floating);
  setTimeout(() => floating.remove(), 900);
}

// Mark as read (Read receipts)
function sendMarkRead(messageId) {
  if (!messageId || !state.currentConversationId) return;

  // Send via WebSocket (0ms)
  if (state.chatSocket && state.chatSocket.readyState === WebSocket.OPEN) {
    state.chatSocket.send(JSON.stringify({
      type: 'mark_read',
      last_message_id: messageId
    }));
  }

  // Also call API
  fetch(`/api/conversations/${state.currentConversationId}/mark_read/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify({ last_message_id: messageId })
  }).catch(() => {});
}

// Update read statuses in timeline dynamically
function updateTimelineReadStatuses() {
  const members = state.currentConversation?.members || [];
  const otherMembers = members.filter(m => m.id !== (state.currentUser ? state.currentUser.id : null));

  document.querySelectorAll('.message-row.me').forEach(row => {
    const msgId = parseInt(row.dataset.msgId);
    if (!msgId) return;

    const metaRow = row.querySelector('.msg-meta-row');
    if (!metaRow) return;

    let isRead = false;
    let readers = [];
    if (state.currentConversation?.is_group) {
      readers = otherMembers.filter(m => (m.last_read_message_id || 0) >= msgId);
      isRead = readers.length > 0;
    } else {
      const other = otherMembers[0];
      isRead = other && (other.last_read_message_id || 0) >= msgId;
      if (other && isRead) readers = [other];
    }

    if (isRead) {
      const names = readers.map(r => r.display_name).join(', ');
      let newHtml = '';
      if (state.currentConversation?.is_group) {
        const avatarImgs = readers.slice(0, 3).map(r => `<img src="${r.avatar_url}" title="${escapeHtml(r.display_name)} đã xem" />`).join('');
        const moreCount = readers.length > 3 ? `<span style="font-size:10px; margin-left:2px; font-weight:700;">+${readers.length - 3}</span>` : '';
        newHtml = `
          <div class="msg-status-indicator seen" title="${escapeHtml(names)} đã xem">
            <span class="msg-status-text">Đã xem</span>
            <div class="seen-avatars-cluster">${avatarImgs}${moreCount}</div>
          </div>
        `;
      } else {
        const other = readers[0];
        newHtml = `
          <div class="msg-status-indicator seen" title="${escapeHtml(other.display_name)} đã xem">
            <span class="msg-status-text">Đã xem</span>
            <img class="seen-mini-avatar" src="${other.avatar_url}" alt="${escapeHtml(other.display_name)}">
          </div>
        `;
      }

      const existing = metaRow.querySelector('.msg-status-indicator');
      if (existing) {
        existing.outerHTML = newHtml;
      } else {
        metaRow.insertAdjacentHTML('beforeend', newHtml);
      }
    }
  });
}

async function toggleReaction(msgId, emoji) {
  if (!state.currentConversationId) return;
  triggerFloatingReaction(msgId, emoji);
  try {
    const res = await fetch(`/api/messages/${msgId}/react/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ emoji: emoji })
    });
    const data = await res.json();
    if (res.ok) {
      const msg = state.messages.find(m => m.id === msgId);
      if (msg) {
        msg.reactions = data.reactions;
        renderTimeline();
      }
    } else {
      showToast(data.error || 'Lỗi khi thả biểu cảm!');
    }
  } catch (err) {
    console.error("Lỗi thả cảm xúc:", err);
  }
}

async function recallMessage(msgId) {
  if (!confirm("Bạn có chắc chắn muốn thu hồi tin nhắn này? Tin nhắn sẽ được thu hồi với tất cả thành viên trong cuộc trò chuyện.")) {
    return;
  }
  try {
    const res = await fetch(`/api/messages/${msgId}/recall/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      }
    });
    const data = await res.json();
    if (res.ok) {
      const msg = state.messages.find(m => m.id === msgId);
      if (msg) {
        msg.is_recalled = true;
        msg.content = 'Tin nhắn đã được thu hồi';
      }
      if (state.currentConversation?.pinned_message?.id === msgId) {
        state.currentConversation.pinned_message.snippet = 'Tin nhắn đã được thu hồi';
        updatePinnedMessageBanner(state.currentConversation.pinned_message);
      }
      renderTimeline();
      showToast(data.message || 'Đã thu hồi tin nhắn thành công!');
    } else {
      showToast(data.error || 'Không thể thu hồi tin nhắn này!');
    }
  } catch (err) {
    console.error("Lỗi thu hồi tin nhắn:", err);
  }
}

async function deleteMessageForMe(msgId) {
  if (!confirm("Tin nhắn này sẽ bị xóa chỉ ở phía bạn. Bạn có muốn tiếp tục?")) {
    return;
  }
  try {
    const res = await fetch(`/api/messages/${msgId}/delete/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      }
    });
    const data = await res.json();
    if (res.ok) {
      state.messages = state.messages.filter(m => m.id !== msgId);
      renderTimeline();
      showToast(data.message || 'Đã xóa tin nhắn ở phía bạn.');
    } else {
      showToast(data.error || 'Không thể xóa tin nhắn!');
    }
  } catch (err) {
    console.error("Lỗi xóa tin nhắn:", err);
  }
}

async function pinConversationMessage(msgId) {
  if (!state.currentConversationId) return;
  try {
    const res = await fetch(`/api/conversations/${state.currentConversationId}/pin_message/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ message_id: msgId })
    });
    const data = await res.json();
    if (res.ok) {
      if (state.currentConversation) {
        state.currentConversation.pinned_message = data.pinned_message;
      }
      updatePinnedMessageBanner(data.pinned_message);
      showToast(data.message || 'Đã ghim tin nhắn lên đầu hội thoại!');
    } else {
      showToast(data.error || 'Không thể ghim tin nhắn!');
    }
  } catch (err) {
    console.error("Lỗi ghim tin nhắn:", err);
  }
}

async function unpinConversationMessage() {
  if (!state.currentConversationId) return;
  try {
    const res = await fetch(`/api/conversations/${state.currentConversationId}/pin_message/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ message_id: null })
    });
    const data = await res.json();
    if (res.ok) {
      if (state.currentConversation) {
        state.currentConversation.pinned_message = null;
      }
      updatePinnedMessageBanner(null);
      showToast('Đã bỏ ghim tin nhắn.');
    }
  } catch (err) {
    console.error("Lỗi bỏ ghim tin nhắn:", err);
  }
}

function updatePinnedMessageBanner(pinnedMsg) {
  const banner = document.getElementById('pinnedMessageBanner');
  const senderSpan = document.getElementById('pinnedMessageSender');
  const textSpan = document.getElementById('pinnedMessageText');
  if (!banner) return;

  if (pinnedMsg) {
    state.pinnedMessageId = pinnedMsg.id;
    if (senderSpan) senderSpan.innerText = pinnedMsg.sender_name + ': ';
    if (textSpan) textSpan.innerText = pinnedMsg.snippet;
    banner.style.display = 'flex';
  } else {
    state.pinnedMessageId = null;
    banner.style.display = 'none';
  }
}

function toggleMsgMoreMenu(e, msgId) {
  e.stopPropagation();
  const menu = document.getElementById(`msgMoreMenu_${msgId}`);
  if (!menu) return;
  const isShown = menu.classList.contains('show');
  document.querySelectorAll('.msg-more-menu.show').forEach(m => m.classList.remove('show'));
  if (!isShown) {
    menu.classList.add('show');
  }
}

function copyMessageContent(msgId) {
  const msg = state.messages.find(m => m.id === msgId);
  if (!msg) return;
  const textToCopy = msg.is_recalled ? 'Tin nhắn đã được thu hồi' : (msg.content || '');
  if (textToCopy) {
    navigator.clipboard.writeText(textToCopy).then(() => {
      showToast('Đã sao chép tin nhắn vào bộ nhớ tạm!');
    });
  }
}

function scrollChatToBottom() {
  const timeline = document.getElementById('chatTimeline');
  if (timeline) {
    timeline.scrollTop = timeline.scrollHeight;
  }
}

function copyCode(btn) {
  const pre = btn.closest('.code-snippet-box')?.querySelector('code');
  if (pre) {
    navigator.clipboard.writeText(pre.innerText).then(() => {
      const original = btn.innerText;
      btn.innerText = 'Đã chép!';
      setTimeout(() => btn.innerText = original, 2000);
    });
  }
}

function openLightbox(url) {
  const modal = document.getElementById('imageLightboxModal');
  const img = document.getElementById('lightboxImg');
  const download = document.getElementById('lightboxDownloadBtn');
  if (img) img.src = url;
  if (download) download.href = url;
  if (modal) modal.classList.add('active');
}

function togglePlayAudio(btn, url) {
  let audio = btn._audioInstance;
  const bars = btn.closest('.msg-audio-card')?.querySelectorAll('.wave-bar') || [];

  if (!audio) {
    audio = new Audio(url);
    btn._audioInstance = audio;
    audio.onended = () => {
      btn.innerHTML = '▶';
      bars.forEach(b => b.classList.remove('active'));
    };
  }

  if (audio.paused) {
    audio.play();
    btn.innerHTML = '⏸';
    bars.forEach(b => b.classList.add('active'));
  } else {
    audio.pause();
    btn.innerHTML = '▶';
    bars.forEach(b => b.classList.remove('active'));
  }
}

// ==============================================================================
// 4. SENDING MESSAGES (Text, Image, Audio, Code)
// ==============================================================================

async function sendTextMessage() {
  const input = document.getElementById('chatInputText');
  const content = input?.value.trim();
  if (!content || !state.currentConversationId) return;

  input.value = '';
  input.style.height = 'auto';

  const replyToId = state.replyingTo ? state.replyingTo.id : null;
  cancelReply();

  // Reset typing state
  if (state.isTypingSent && state.chatSocket && state.chatSocket.readyState === WebSocket.OPEN) {
    state.isTypingSent = false;
    state.chatSocket.send(JSON.stringify({ type: 'typing', is_typing: false }));
  }

  // Ưu tiên gửi trực tiếp qua WebSocket (độ trễ 0ms)
  if (state.chatSocket && state.chatSocket.readyState === WebSocket.OPEN) {
    state.chatSocket.send(JSON.stringify({
      type: 'chat_message',
      content: content,
      reply_to_id: replyToId,
      message_type: 'text'
    }));
    return;
  }

  try {
    const res = await fetch(`/api/conversations/${state.currentConversationId}/send/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({
        message_type: 'text',
        content: content,
        reply_to_id: replyToId
      })
    });
    const newMsg = await res.json();
    if (res.ok) {
      state.messages.push(newMsg);
      state.lastMessageId = newMsg.id;
      renderTimeline();
      scrollChatToBottom();
      playNotificationSound();
      loadConversations();
    } else {
      showToast(newMsg.error || "Gửi tin nhắn thất bại!");
    }
  } catch (err) {
    console.error("Lỗi gửi tin nhắn:", err);
  }
}

async function uploadImageMessage(file) {
  if (!file || !state.currentConversationId) return;

  const formData = new FormData();
  formData.append('message_type', 'image');
  formData.append('attachment', file);
  formData.append('content', file.name);

  if (state.replyingTo) {
    formData.append('reply_to_id', state.replyingTo.id);
    cancelReply();
  }

  showToast("Đang tải ảnh lên...");
  try {
    const res = await fetch(`/api/conversations/${state.currentConversationId}/send/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
      body: formData
    });
    const newMsg = await res.json();
    if (res.ok) {
      state.messages.push(newMsg);
      state.lastMessageId = newMsg.id;
      renderTimeline();
      scrollChatToBottom();
      playNotificationSound();
      loadConversations();
      showToast("Đã gửi ảnh thành công!");
    }
  } catch (err) {
    showToast("Lỗi gửi tệp ảnh!");
  }
}

async function uploadDocFile(file) {
  if (!file || !state.currentConversationId) return;

  const formData = new FormData();
  formData.append('message_type', 'file');
  formData.append('attachment', file);
  formData.append('content', file.name);

  if (state.replyingTo) {
    formData.append('reply_to_id', state.replyingTo.id);
    cancelReply();
  }

  showToast("Đang tải tệp tin lên...");
  try {
    const res = await fetch(`/api/conversations/${state.currentConversationId}/send/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
      body: formData
    });
    const newMsg = await res.json();
    if (res.ok) {
      state.messages.push(newMsg);
      state.lastMessageId = newMsg.id;
      renderTimeline();
      scrollChatToBottom();
      playNotificationSound();
      loadConversations();
      showToast("Đã gửi tệp tin thành công!");
    }
  } catch (err) {
    showToast("Lỗi gửi tệp!");
  }
}

async function sendCodeSnippet() {
  const language = document.getElementById('codeLanguageSelect')?.value || 'java';
  const code = document.getElementById('codeSnippetText')?.value.trim();

  if (!code || !state.currentConversationId) {
    showToast("Vui lòng nhập nội dung đoạn mã!");
    return;
  }

  const replyToId = state.replyingTo ? state.replyingTo.id : null;
  cancelReply();

  try {
    const res = await fetch(`/api/conversations/${state.currentConversationId}/send/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({
        message_type: 'code',
        content: code,
        code_language: language,
        reply_to_id: replyToId
      })
    });
    const newMsg = await res.json();
    if (res.ok) {
      state.messages.push(newMsg);
      state.lastMessageId = newMsg.id;
      renderTimeline();
      scrollChatToBottom();
      closeModal('codeSnippetModal');
      document.getElementById('codeSnippetText').value = '';
      playNotificationSound();
      loadConversations();
      showToast("Đã gửi đoạn mã thành công!");
    }
  } catch (err) {
    showToast("Lỗi gửi đoạn mã!");
  }
}

// ==============================================================================
// 5. VOICE NOTE AUDIO RECORDING (MediaRecorder)
// ==============================================================================

async function startVoiceRecording() {
  if (state.isRecording) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.mediaRecorder = new MediaRecorder(stream);
    state.audioChunks = [];

    state.mediaRecorder.ondataavailable = e => {
      if (e.data.size > 0) state.audioChunks.push(e.data);
    };

    state.mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(track => track.stop());
    };

    state.mediaRecorder.start();
    state.isRecording = true;
    state.recordStartTime = Date.now();

    const bar = document.getElementById('voiceRecordingBar');
    if (bar) bar.classList.add('active');

    state.recordTimerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - state.recordStartTime) / 1000);
      const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
      const secs = String(elapsed % 60).padStart(2, '0');
      const timer = document.getElementById('recordTimer');
      if (timer) timer.innerText = `${mins}:${secs}`;
    }, 1000);

  } catch (err) {
    showToast("Không thể truy cập Microphone! Vui lòng cấp quyền ghi âm.");
  }
}

function cancelVoiceRecording() {
  if (!state.isRecording || !state.mediaRecorder) return;
  clearInterval(state.recordTimerInterval);
  state.isRecording = false;
  state.mediaRecorder.stop();
  const bar = document.getElementById('voiceRecordingBar');
  if (bar) bar.classList.remove('active');
  showToast("Đã hủy ghi âm.");
}

async function stopAndSendVoiceRecording() {
  if (!state.isRecording || !state.mediaRecorder) return;
  clearInterval(state.recordTimerInterval);
  state.isRecording = false;
  const bar = document.getElementById('voiceRecordingBar');
  if (bar) bar.classList.remove('active');

  state.mediaRecorder.onstop = async () => {
    const audioBlob = new Blob(state.audioChunks, { type: 'audio/webm' });
    const file = new File([audioBlob], `voice_${Date.now()}.webm`, { type: 'audio/webm' });

    const formData = new FormData();
    formData.append('message_type', 'audio');
    formData.append('attachment', file);
    formData.append('content', 'Tin nhắn thoại ghi âm');

    if (state.replyingTo) {
      formData.append('reply_to_id', state.replyingTo.id);
      cancelReply();
    }

    showToast("Đang gửi tin nhắn thoại...");
    try {
      const res = await fetch(`/api/conversations/${state.currentConversationId}/send/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') },
        body: formData
      });
      const newMsg = await res.json();
      if (res.ok) {
        state.messages.push(newMsg);
        state.lastMessageId = newMsg.id;
        renderTimeline();
        scrollChatToBottom();
        playNotificationSound();
        loadConversations();
        showToast("Đã gửi tin nhắn thoại thành công!");
      }
    } catch (err) {
      showToast("Lỗi khi gửi bản ghi âm!");
    }
  };

  state.mediaRecorder.stop();
}

// ==============================================================================
// 6. REAL-TIME SYNCHRONIZATION (Polling every 1.5s)
// ==============================================================================

function startSync() {
  if (state.syncTimer) clearInterval(state.syncTimer);

  state.syncTimer = setInterval(async () => {
    if (!state.currentConversationId || !state.currentUser) return;

    // Khi WebSocket đang kết nối, tin nhắn được đẩy theo thời gian thực (0ms)
    // Ngưng gửi request HTTP polling liên tục
    if (state.isWsConnected) {
      return;
    }

    try {
      const res = await fetch(`/api/conversations/${state.currentConversationId}/sync/?after_id=${state.lastMessageId}`);
      if (res.status === 401 || res.status === 403 || res.status === 404) {
        clearInterval(state.syncTimer);
        state.currentConversationId = null;
        loadConversations();
        return;
      }
      if (res.ok) {
        const newMsgs = await res.json();
        if (newMsgs && newMsgs.length > 0) {
          state.messages.push(...newMsgs);
          state.lastMessageId = newMsgs[newMsgs.length - 1].id;
          renderTimeline();
          scrollChatToBottom();
          playNotificationSound();
          loadConversations();
        }
      }
    } catch (err) {
      // Silent catch
    }
  }, 1500);
}

// ==============================================================================
// 7. CONTACTS (DANH BẠ) & MY CLOUD (CLOUD CỦA TÔI)
// ==============================================================================

async function loadContacts() {
  const container = document.getElementById('contactsContainer');
  if (!container) return;
  container.innerHTML = '<div style="padding:16px; text-align:center; color:var(--zalo-text-muted);">Đang tải danh bạ...</div>';

  try {
    const res = await fetch('/api/contacts/');
    const data = await res.json();
    container.innerHTML = '';

    // Quick Add Friend By Phone Banner
    const addFriendBanner = document.createElement('div');
    addFriendBanner.className = 'contact-add-friend-banner';
    addFriendBanner.innerHTML = `
      <div class="banner-left">
        <div class="banner-icon">📱</div>
        <div class="banner-text">
          <div class="banner-title">Thêm bạn mới</div>
          <div class="banner-sub">Tìm kiếm bạn bè bằng số điện thoại</div>
        </div>
      </div>
      <button class="banner-action-btn">Tìm kiếm</button>
    `;
    addFriendBanner.onclick = openNewChatModal;
    container.appendChild(addFriendBanner);

    // Groups Section
    if (data.groups && data.groups.length > 0) {
      const grpHeading = document.createElement('div');
      grpHeading.className = 'contacts-section-heading';
      grpHeading.innerText = `Nhóm đã tham gia (${data.groups.length})`;
      container.appendChild(grpHeading);

      data.groups.forEach(g => {
        const card = document.createElement('div');
        card.className = 'contact-item-card';
        card.innerHTML = `
          <div class="contact-item-left">
            <div class="contact-avatar-wrapper">
              <img src="${g.avatar_url}" alt="${escapeHtml(g.name)}">
            </div>
            <div class="contact-info-text">
              <div class="contact-name">${escapeHtml(g.name)}</div>
              <div class="contact-sub">${g.member_count} thành viên</div>
            </div>
          </div>
          <button class="contact-chat-btn">Vào nhóm</button>
        `;
        card.onclick = () => {
          switchMainTab('messages');
          selectConversation(g.id);
        };
        container.appendChild(card);
      });
    }

    // Friends Section
    if (data.contacts && data.contacts.length > 0) {
      const friendHeading = document.createElement('div');
      friendHeading.className = 'contacts-section-heading';
      friendHeading.innerText = `Danh sách bạn bè (${data.contacts.length})`;
      container.appendChild(friendHeading);

      data.contacts.forEach(u => {
        const card = document.createElement('div');
        card.className = 'contact-item-card';
        const onlineDot = u.is_online ? '<div class="contact-online-dot"></div>' : '';
        card.innerHTML = `
          <div class="contact-item-left">
            <div class="contact-avatar-wrapper">
              <img src="${u.avatar_url}" alt="${escapeHtml(u.display_name)}">
              ${onlineDot}
            </div>
            <div class="contact-info-text">
              <div class="contact-name">${escapeHtml(u.display_name)}</div>
              <div class="contact-sub">${u.phone ? u.phone : `@${u.username}`}</div>
            </div>
          </div>
          <button class="contact-chat-btn">Nhắn tin</button>
        `;
        card.onclick = () => startDirectChatWithUser(u.id);
        container.appendChild(card);
      });
    }
  } catch (err) {
    container.innerHTML = '<div style="padding:16px; color:#d32f2f;">Lỗi khi tải danh bạ!</div>';
  }
}

async function openCloudConversation() {
  try {
    const res = await fetch('/api/cloud/');
    const data = await res.json();
    switchMainTab('messages');
    await loadConversations();
    selectConversation(data.id);
    showToast("Đã mở Cloud của tôi - Không gian lưu trữ cá nhân.");
  } catch (err) {
    showToast("Không thể mở Cloud của tôi!");
  }
}

// Start 1-1 chat with a user ID
async function startDirectChatWithUser(userId) {
  try {
    const res = await fetch('/api/conversations/create/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ is_group: false, user_id: userId })
    });
    const conv = await res.json();
    switchMainTab('messages');
    closeModal('newChatModal');
    await loadConversations();
    selectConversation(conv.id);
  } catch (err) {
    showToast("Lỗi khi mở cuộc trò chuyện 1-1!");
  }
}

// ==============================================================================
// 8. TO-DO & TASKS MANAGEMENT
// ==============================================================================

async function loadTasks() {
  const container = document.getElementById('tasksBoardContainer');
  if (!container) return;
  container.innerHTML = '<div style="padding:16px; text-align:center;">Đang tải danh sách công việc...</div>';

  try {
    const res = await fetch('/api/tasks/');
    const tasks = await res.json();
    renderTasksList(tasks);
  } catch (err) {
    container.innerHTML = '<div style="color:#d32f2f;">Lỗi tải công việc!</div>';
  }
}

function renderTasksList(tasks) {
  const container = document.getElementById('tasksBoardContainer');
  if (!container) return;
  container.innerHTML = '';

  const total = tasks.length;
  const done = tasks.filter(t => t.done).length;
  const pending = total - done;

  const statTotal = document.getElementById('statTotalTasks');
  if (statTotal) statTotal.innerText = total;

  const statPending = document.getElementById('statPendingTasks');
  if (statPending) statPending.innerText = pending;

  const statDone = document.getElementById('statDoneTasks');
  if (statDone) statDone.innerText = done;

  tasks.forEach(t => {
    const card = document.createElement('div');
    card.className = `task-item-card ${t.done ? 'done' : ''}`;
    const priorityClass = t.priority === 'high' ? 'priority-high' : (t.priority === 'medium' ? 'priority-medium' : 'priority-normal');
    const priorityText = t.priority === 'high' ? 'Cao' : (t.priority === 'medium' ? 'Trung bình' : 'Thường');

    card.innerHTML = `
      <div class="task-left">
        <input type="checkbox" class="task-checkbox" ${t.done ? 'checked' : ''} onchange="toggleTaskDone(${t.id})">
        <div>
          <div class="task-title">${escapeHtml(t.title)}</div>
          <div class="task-due">⏰ Hạn chót: ${escapeHtml(t.due)}</div>
        </div>
      </div>
      <div style="display:flex; align-items:center; gap:10px;">
        <span class="task-priority-badge ${priorityClass}">${priorityText}</span>
        <button class="task-delete-btn" onclick="deleteTask(${t.id})" title="Xóa công việc">&times;</button>
      </div>
    `;
    container.appendChild(card);
  });
}

async function toggleTaskDone(taskId) {
  try {
    const res = await fetch('/api/tasks/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ action: 'toggle', id: taskId })
    });
    const tasks = await res.json();
    renderTasksList(tasks);
  } catch (err) {
    showToast("Lỗi cập nhật công việc!");
  }
}

async function deleteTask(taskId) {
  try {
    const res = await fetch('/api/tasks/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ action: 'delete', id: taskId })
    });
    const tasks = await res.json();
    renderTasksList(tasks);
    showToast("Đã xóa công việc.");
  } catch (err) {
    showToast("Lỗi xóa công việc!");
  }
}

async function submitCreateTask() {
  const title = document.getElementById('newTaskTitle')?.value.trim();
  const due = document.getElementById('newTaskDue')?.value.trim() || 'Sắp tới';
  const priority = document.getElementById('newTaskPriority')?.value || 'medium';

  if (!title) {
    showToast("Vui lòng nhập nội dung công việc!");
    return;
  }

  try {
    const res = await fetch('/api/tasks/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ action: 'create', title, due, priority })
    });
    const tasks = await res.json();
    renderTasksList(tasks);
    closeModal('createTaskModal');
    document.getElementById('newTaskTitle').value = '';
    showToast("Đã thêm công việc mới!");
  } catch (err) {
    showToast("Lỗi tạo công việc!");
  }
}

// ==============================================================================
// 9. NEW 1-1 CHAT & GROUP CREATION MODALS
// ==============================================================================

// --------------------------------------------------------------------------
// 9. ADD FRIEND & SEARCH BY PHONE NUMBER (Zalo Web Style)
// --------------------------------------------------------------------------

function handleAddFriendRequest(userId, displayName) {
  showToast(`Đã gửi lời mời kết bạn đến ${displayName}!`);
}

async function searchFriendByPhone(phoneQuery) {
  const input = document.getElementById('friendSearchPhoneInput');
  const resultArea = document.getElementById('friendSearchResultArea');
  if (!resultArea) return;

  const phone = (phoneQuery !== undefined ? phoneQuery : (input ? input.value : '')).trim();
  if (!phone) {
    showToast("Vui lòng nhập số điện thoại cần tìm!");
    if (input) input.focus();
    return;
  }

  // Hiển thị vòng xoay đang tìm kiếm
  resultArea.innerHTML = `
    <div class="phone-search-loading">
      <div class="mini-spinner"></div>
      <span>Đang tìm kiếm thông tin người dùng...</span>
    </div>
  `;

  try {
    const res = await fetch(`/api/users/search_by_phone/?phone=${encodeURIComponent(phone)}`);
    const data = await res.json();

    if (data.status === 'found') {
      const u = data.user;
      const onlineDot = u.is_online ? '<div class="contact-online-dot"></div>' : '';
      resultArea.innerHTML = `
        <div class="found-user-card">
          <div class="user-card-cover"></div>
          <div class="user-card-body">
            <div class="user-card-avatar-wrapper">
              <img src="${u.avatar_url}" alt="${escapeHtml(u.display_name)}">
              ${onlineDot}
            </div>
            <div class="user-card-name">${escapeHtml(u.display_name)}</div>
            <div class="user-card-sub">
              <span class="user-phone-tag">📞 ${escapeHtml(u.phone || phone)}</span>
              <span class="user-username-tag">@${escapeHtml(u.username)}</span>
            </div>
            ${u.bio ? `<div class="user-card-bio">"${escapeHtml(u.bio)}"</div>` : ''}
            <div class="user-card-actions">
              <button class="btn-card-action primary" onclick="startDirectChatWithUser(${u.id})">
                <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0-2-.9-2-2V4c0-1.1-.9-2-2-2zm0 14H5.2L4 17.2V4h16v12z"/></svg>
                Nhắn tin
              </button>
              <button class="btn-card-action secondary" onclick="handleAddFriendRequest(${u.id}, '${escapeHtml(u.display_name)}')">
                <svg viewBox="0 0 24 24"><path d="M15 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm-9-2V7H4v3H1v2h3v3h2v-3h3v-2H6zm9 4c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
                Kết bạn
              </button>
            </div>
          </div>
        </div>
      `;
    } else if (data.status === 'self') {
      const u = data.user;
      resultArea.innerHTML = `
        <div class="friend-search-alert self">
          <div class="alert-icon">👤</div>
          <div class="alert-text">
            <strong>Số điện thoại của chính bạn</strong>
            <div>Tài khoản: <b>${escapeHtml(u.display_name)}</b> (${escapeHtml(u.phone)})</div>
          </div>
        </div>
      `;
    } else {
      // not_found or error
      resultArea.innerHTML = `
        <div class="friend-search-alert not-found">
          <div class="alert-icon">🔍</div>
          <div class="alert-text">
            <strong>Không tìm thấy người dùng</strong>
            <div>Số điện thoại <b>${escapeHtml(phone)}</b> chưa đăng ký tài khoản Zalo hoặc không cho phép tìm kiếm.</div>
          </div>
        </div>
      `;
    }
  } catch (err) {
    resultArea.innerHTML = `
      <div class="friend-search-alert not-found">
        <div class="alert-icon">⚠️</div>
        <div class="alert-text">
          <strong>Lỗi kết nối máy chủ</strong>
          <div>Không thể tra cứu thông tin số điện thoại vào lúc này.</div>
        </div>
      </div>
    `;
  }
}

async function openNewChatModal() {
  openModal('newChatModal');
  const input = document.getElementById('friendSearchPhoneInput');
  const clearBtn = document.getElementById('btnClearPhoneInput');
  const resultArea = document.getElementById('friendSearchResultArea');
  if (input) {
    input.value = '';
    setTimeout(() => input.focus(), 150);
  }
  if (clearBtn) clearBtn.style.display = 'none';
  if (resultArea) {
    resultArea.innerHTML = `
      <div class="phone-search-tip">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
        <span>Nhập số điện thoại để tìm kiếm bạn bè trên Zalo</span>
      </div>
    `;
  }
  loadUsersForNewChat();
}

async function loadUsersForNewChat(query = '') {
  const container = document.getElementById('newChatUsersList');
  if (!container) return;
  container.innerHTML = '<div style="padding:12px; text-align:center;">Đang tải danh sách người dùng...</div>';

  try {
    const url = query ? `/api/users/search/?q=${encodeURIComponent(query)}` : '/api/users/search/';
    const res = await fetch(url);
    const users = await res.json();
    container.innerHTML = '';

    if (users.length === 0) {
      container.innerHTML = '<div style="padding:12px; text-align:center; color:#888;">Không tìm thấy người dùng phù hợp.</div>';
      return;
    }

    users.forEach(u => {
      const row = document.createElement('div');
      row.className = 'contact-item-card';
      row.innerHTML = `
        <div class="contact-item-left">
          <div class="contact-avatar-wrapper">
            <img src="${u.avatar_url}" alt="${escapeHtml(u.display_name)}">
            ${u.is_online ? '<div class="contact-online-dot"></div>' : ''}
          </div>
          <div class="contact-info-text">
            <div class="contact-name">${escapeHtml(u.display_name)}</div>
            <div class="contact-sub">${u.phone || `@${u.username}`}</div>
          </div>
        </div>
        <button class="contact-chat-btn">Nhắn tin</button>
      `;
      row.onclick = () => startDirectChatWithUser(u.id);
      container.appendChild(row);
    });
  } catch (err) {
    container.innerHTML = '<div style="padding:12px; color:#d32f2f;">Lỗi tìm kiếm người dùng!</div>';
  }
}

async function openCreateGroupModal() {
  const container = document.getElementById('groupMembersList');
  if (!container) return;
  container.innerHTML = 'Đang tải người dùng...';
  openModal('createGroupModal');

  try {
    const res = await fetch('/api/users/search/');
    const users = await res.json();
    container.innerHTML = '';
    users.forEach(u => {
      const row = document.createElement('label');
      row.style.display = 'flex';
      row.style.alignItems = 'center';
      row.style.gap = '8px';
      row.style.cursor = 'pointer';
      row.style.padding = '4px 0';
      row.innerHTML = `
        <input type="checkbox" value="${u.id}" class="member-checkbox">
        <img src="${u.avatar_url}" style="width:30px;height:30px;border-radius:50%;object-fit:cover;">
        <span style="font-size:13.5px; font-weight:500;">${escapeHtml(u.display_name)} (@${escapeHtml(u.username)})</span>
      `;
      container.appendChild(row);
    });
  } catch (err) {
    container.innerHTML = 'Không thể tải danh sách người dùng!';
  }
}

async function submitCreateGroup() {
  const name = document.getElementById('newGroupNameInput')?.value.trim();
  if (!name) {
    showToast("Vui lòng đặt tên nhóm!");
    return;
  }
  const checkboxes = document.querySelectorAll('.member-checkbox:checked');
  const memberIds = Array.from(checkboxes).map(cb => parseInt(cb.value));

  try {
    const res = await fetch('/api/conversations/create/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({
        is_group: true,
        name: name,
        members: memberIds
      })
    });
    const data = await res.json();
    if (res.ok) {
      closeModal('createGroupModal');
      showToast(`Đã tạo nhóm: ${name}`);
      await loadConversations();
      selectConversation(data.id);
    }
  } catch (err) {
    showToast("Lỗi khi tạo nhóm!");
  }
}

// ==============================================================================
// 10. EMOJI PICKER POPOVER & IN-CHAT SEARCH
// ==============================================================================

function renderEmojiCategory(cat) {
  const grid = document.getElementById('emojiPickerGrid');
  if (!grid) return;
  grid.innerHTML = '';

  const list = EMOJIS[cat] || EMOJIS.faces;
  const input = document.getElementById('chatInputText');

  list.forEach(emoji => {
    const btn = document.createElement('button');
    btn.className = 'emoji-grid-btn';
    btn.innerText = emoji;
    btn.onclick = (e) => {
      e.stopPropagation();
      if (input) {
        input.value += emoji;
        input.focus();
      }
    };
    grid.appendChild(btn);
  });
}

function initEmojiPicker() {
  renderEmojiCategory('faces');

  document.querySelectorAll('.emoji-cat-btn').forEach(btn => {
    btn.onclick = (e) => {
      e.stopPropagation();
      document.querySelectorAll('.emoji-cat-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderEmojiCategory(btn.dataset.cat);
    };
  });
}

// In-chat Search Logic
async function handleInChatSearch(query) {
  const countSpan = document.getElementById('searchResultCount');
  if (!query || !state.currentConversationId) {
    if (countSpan) countSpan.innerText = '';
    document.querySelectorAll('.message-row').forEach(row => row.style.display = 'flex');
    return;
  }

  try {
    const res = await fetch(`/api/conversations/${state.currentConversationId}/search/?q=${encodeURIComponent(query)}`);
    const results = await res.json();
    if (countSpan) countSpan.innerText = `${results.length} kết quả`;

    const matchedIds = new Set(results.map(r => String(r.id)));
    document.querySelectorAll('.message-row').forEach(row => {
      if (matchedIds.has(row.dataset.msgId)) {
        row.style.display = 'flex';
        row.style.backgroundColor = 'rgba(255, 235, 59, 0.2)';
      } else {
        row.style.display = 'none';
        row.style.backgroundColor = 'transparent';
      }
    });
  } catch (err) {
    console.error("Lỗi tìm kiếm tin nhắn:", err);
  }
}

// ==============================================================================
// 11. TAB NAVIGATION (Messages, Contacts, Tasks)
// ==============================================================================

function switchMainTab(tab) {
  state.activeMainTab = tab;

  // Update Rail items active state
  document.querySelectorAll('.rail-item').forEach(item => item.classList.remove('active'));
  if (tab === 'messages') document.getElementById('tabMessages')?.classList.add('active');
  if (tab === 'contacts') document.getElementById('tabContacts')?.classList.add('active');
  if (tab === 'tasks') document.getElementById('tabTasks')?.classList.add('active');

  const convContainer = document.getElementById('conversationsContainer');
  const contactsContainer = document.getElementById('contactsContainer');
  const chatMain = document.getElementById('chatMainArea');
  const tasksMain = document.getElementById('tasksMainView');
  const filterRow = document.getElementById('sidebarFilterRow');

  if (tab === 'messages') {
    if (convContainer) convContainer.style.display = 'block';
    if (contactsContainer) contactsContainer.style.display = 'none';
    if (chatMain) chatMain.style.display = 'flex';
    if (tasksMain) tasksMain.style.display = 'none';
    if (filterRow) filterRow.style.display = 'flex';
  } else if (tab === 'contacts') {
    if (convContainer) convContainer.style.display = 'none';
    if (contactsContainer) contactsContainer.style.display = 'flex';
    if (chatMain) chatMain.style.display = 'flex';
    if (tasksMain) tasksMain.style.display = 'none';
    if (filterRow) filterRow.style.display = 'none';
    loadContacts();
  } else if (tab === 'tasks') {
    if (chatMain) chatMain.style.display = 'none';
    if (tasksMain) tasksMain.style.display = 'flex';
    loadTasks();
  }
}

// ==============================================================================
// 10.1 WEBSOCKET PING / PONG & NETWORK LATENCY INDICATOR (LTM Core)
// ==============================================================================

function updateLatencyBadge(rtt) {
  const badge = document.getElementById('networkLatencyBadge');
  const text = document.getElementById('latencyText');
  if (!badge || !text) return;

  if (rtt === null || rtt === undefined) {
    badge.className = 'network-latency-badge';
    badge.title = 'Chưa kết nối WebSocket';
    text.innerText = '-- ms';
    return;
  }

  badge.className = 'network-latency-badge';
  if (rtt < 60) {
    badge.classList.add('latency-fast');
    badge.title = `WebSocket (RFC 6455) - Độ trễ RTT: ${rtt}ms (Rất tốt)`;
  } else if (rtt < 150) {
    badge.classList.add('latency-medium');
    badge.title = `WebSocket (RFC 6455) - Độ trễ RTT: ${rtt}ms (Bình thường)`;
  } else {
    badge.classList.add('latency-slow');
    badge.title = `WebSocket (RFC 6455) - Độ trễ RTT: ${rtt}ms (Đường truyền chậm)`;
  }
  text.innerText = `${rtt}ms`;
}

function startWebSocketPing() {
  stopWebSocketPing();
  if (state.chatSocket && state.chatSocket.readyState === WebSocket.OPEN) {
    state.chatSocket.send(JSON.stringify({
      type: 'ping',
      client_timestamp: Date.now()
    }));
  }
  state.pingInterval = setInterval(() => {
    if (state.chatSocket && state.chatSocket.readyState === WebSocket.OPEN) {
      state.chatSocket.send(JSON.stringify({
        type: 'ping',
        client_timestamp: Date.now()
      }));
    }
  }, 4500);
}

function stopWebSocketPing() {
  if (state.pingInterval) {
    clearInterval(state.pingInterval);
    state.pingInterval = null;
  }
}

function handleIncomingReadReceipt(data) {
  if (!state.currentConversation) return;

  const member = (state.currentConversation.members || []).find(m => m.id === data.user_id);
  if (member) {
    member.last_read_message_id = Math.max(member.last_read_message_id || 0, data.last_read_message_id);
  } else if (state.currentConversation.members) {
    state.currentConversation.members.push({
      id: data.user_id,
      username: data.username,
      display_name: data.display_name,
      avatar_url: data.avatar_url,
      last_read_message_id: data.last_read_message_id
    });
  }

  updateTimelineReadStatuses();
}

// ==============================================================================
// 10.2 CONTEXT MENU, CLIPBOARD PASTE IMAGE & FORWARD MODAL
// ==============================================================================

function initContextMenu() {
  const timeline = document.getElementById('chatTimeline');
  const menu = document.getElementById('zaloContextMenu');
  if (!timeline || !menu) return;

  timeline.addEventListener('contextmenu', (e) => {
    const row = e.target.closest('.message-row');
    if (!row) return;

    e.preventDefault();
    const msgId = parseInt(row.dataset.msgId);
    if (!msgId) return;

    state.activeContextMsgId = msgId;
    const msg = state.messages.find(m => m.id === msgId);
    if (!msg) return;

    const isMe = msg.is_me;
    const isRecalled = msg.is_recalled;

    const ctxRecall = document.getElementById('ctxRecall');
    if (ctxRecall) {
      ctxRecall.style.display = (isMe && !isRecalled) ? 'flex' : 'none';
    }

    const ctxPinText = document.getElementById('ctxPinText');
    if (ctxPinText) {
      const isPinned = state.currentConversation?.pinned_message?.id === msgId;
      ctxPinText.innerText = isPinned ? 'Bỏ ghim tin nhắn' : 'Ghim tin nhắn';
    }

    menu.style.display = 'block';
    const menuWidth = 210;
    const menuHeight = menu.offsetHeight || 220;

    let posX = e.clientX;
    let posY = e.clientY;

    if (posX + menuWidth > window.innerWidth - 10) {
      posX = window.innerWidth - menuWidth - 12;
    }
    if (posY + menuHeight > window.innerHeight - 10) {
      posY = window.innerHeight - menuHeight - 12;
    }

    menu.style.left = `${posX}px`;
    menu.style.top = `${posY}px`;
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('#zaloContextMenu')) {
      closeContextMenu();
    }
  });

  timeline.addEventListener('scroll', () => {
    closeContextMenu();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeContextMenu();
    }
  });

  document.getElementById('ctxReply')?.addEventListener('click', () => {
    const id = state.activeContextMsgId;
    closeContextMenu();
    if (id) startReplyMessage(id);
  });

  document.getElementById('ctxForward')?.addEventListener('click', () => {
    const id = state.activeContextMsgId;
    closeContextMenu();
    if (id) openForwardModal(id);
  });

  document.getElementById('ctxCopy')?.addEventListener('click', () => {
    const id = state.activeContextMsgId;
    closeContextMenu();
    if (id) copyMessageContent(id);
  });

  document.getElementById('ctxPin')?.addEventListener('click', () => {
    const id = state.activeContextMsgId;
    closeContextMenu();
    if (id) pinConversationMessage(id);
  });

  document.getElementById('ctxDelete')?.addEventListener('click', () => {
    const id = state.activeContextMsgId;
    closeContextMenu();
    if (id) deleteMessageForMe(id);
  });

  document.getElementById('ctxRecall')?.addEventListener('click', () => {
    const id = state.activeContextMsgId;
    closeContextMenu();
    if (id) recallMessage(id);
  });
}

function closeContextMenu() {
  const menu = document.getElementById('zaloContextMenu');
  if (menu) menu.style.display = 'none';
  state.activeContextMsgId = null;
}

function openForwardModal(msgId) {
  const msg = state.messages.find(m => m.id === msgId);
  if (!msg) return;

  state.forwardingMsg = msg;
  state.selectedForwardConvIds.clear();

  const snippetBox = document.getElementById('forwardPreviewSnippet');
  if (snippetBox) {
    let snippet = msg.content;
    if (msg.message_type === 'image') snippet = '🖼️ [Hình ảnh]';
    else if (msg.message_type === 'audio') snippet = '🎙️ [Tin nhắn thoại]';
    else if (msg.message_type === 'file') snippet = `📄 [Tệp tin] ${msg.attachment_name || ''}`;
    else if (msg.message_type === 'code') snippet = `💻 [Đoạn mã ${msg.code_language || 'Code'}]`;
    snippetBox.innerHTML = `<strong>${escapeHtml(msg.sender_name)}:</strong> ${escapeHtml(snippet)}`;
  }

  renderForwardTargets('');

  const searchInput = document.getElementById('forwardSearchInput');
  if (searchInput) {
    searchInput.value = '';
    searchInput.oninput = (e) => renderForwardTargets(e.target.value);
  }

  const btnConfirm = document.getElementById('btnConfirmForward');
  if (btnConfirm) {
    btnConfirm.disabled = true;
    btnConfirm.innerText = 'Chuyển tiếp';
  }

  openModal('forwardMsgModal');
}

function renderForwardTargets(searchQuery = '') {
  const container = document.getElementById('forwardTargetsList');
  if (!container) return;
  container.innerHTML = '';

  const q = searchQuery.toLowerCase().trim();
  const list = (state.conversations || []).filter(c => {
    if (!q) return true;
    return c.title.toLowerCase().includes(q);
  });

  if (list.length === 0) {
    container.innerHTML = '<div style="padding:16px; text-align:center; color:var(--zalo-text-muted); font-size:13px;">Không tìm thấy cuộc trò chuyện nào</div>';
    return;
  }

  list.forEach(conv => {
    const isSelected = state.selectedForwardConvIds.has(conv.id);
    const item = document.createElement('div');
    item.className = `forward-target-item ${isSelected ? 'selected' : ''}`;
    item.innerHTML = `
      <div class="forward-target-left">
        <img class="forward-target-avatar" src="${conv.avatar_url}" alt="Avatar">
        <div>
          <div class="forward-target-name">${escapeHtml(conv.title)}</div>
          <div class="forward-target-sub">${conv.is_group ? `${conv.member_count} thành viên` : 'Trò chuyện 1-1'}</div>
        </div>
      </div>
      <input type="checkbox" class="forward-target-checkbox" ${isSelected ? 'checked' : ''}>
    `;

    item.onclick = () => {
      if (state.selectedForwardConvIds.has(conv.id)) {
        state.selectedForwardConvIds.delete(conv.id);
        item.classList.remove('selected');
        item.querySelector('.forward-target-checkbox').checked = false;
      } else {
        state.selectedForwardConvIds.add(conv.id);
        item.classList.add('selected');
        item.querySelector('.forward-target-checkbox').checked = true;
      }
      const btnConfirm = document.getElementById('btnConfirmForward');
      if (btnConfirm) {
        btnConfirm.disabled = state.selectedForwardConvIds.size === 0;
        btnConfirm.innerText = state.selectedForwardConvIds.size > 0 
          ? `Chuyển tiếp (${state.selectedForwardConvIds.size})`
          : 'Chuyển tiếp';
      }
    };
    container.appendChild(item);
  });
}

async function confirmForwardMessage() {
  if (!state.forwardingMsg || state.selectedForwardConvIds.size === 0) return;
  const btn = document.getElementById('btnConfirmForward');
  if (btn) {
    btn.disabled = true;
    btn.innerText = 'Đang gửi...';
  }

  try {
    const res = await fetch(`/api/messages/${state.forwardingMsg.id}/forward/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
      },
      body: JSON.stringify({
        conversation_ids: Array.from(state.selectedForwardConvIds)
      })
    });
    const data = await res.json();
    if (res.ok) {
      closeModal('forwardMsgModal');
      showToast(data.message || 'Đã chuyển tiếp tin nhắn thành công!');
      loadConversations();
      if (state.selectedForwardConvIds.has(state.currentConversationId)) {
        loadMessages(state.currentConversationId);
      }
    } else {
      showToast(data.error || 'Chuyển tiếp tin nhắn thất bại!');
    }
  } catch (err) {
    showToast('Lỗi kết nối khi chuyển tiếp tin nhắn!');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = 'Chuyển tiếp';
    }
  }
}

function initClipboardPaste() {
  document.addEventListener('paste', handleClipboardPaste);

  document.getElementById('btnSendPasteImage')?.addEventListener('click', sendPastedImage);
  document.getElementById('pasteImageCaptionInput')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      sendPastedImage();
    }
  });
}

function handleClipboardPaste(e) {
  const items = (e.clipboardData || window.clipboardData)?.items;
  if (!items) return;

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.type && item.type.indexOf('image') !== -1) {
      e.preventDefault();
      const file = item.getAsFile();
      if (!file) continue;

      state.pastedImageFile = file;

      const reader = new FileReader();
      reader.onload = (event) => {
        const previewImg = document.getElementById('pastePreviewImg');
        if (previewImg) previewImg.src = event.target.result;

        const sizeKb = Math.round(file.size / 1024);
        const metaText = document.getElementById('pasteImageMeta');
        if (metaText) {
          metaText.innerText = `Đã chụp từ bộ nhớ tạm • ${sizeKb > 1024 ? (sizeKb / 1024).toFixed(1) + ' MB' : sizeKb + ' KB'}`;
        }

        const captionInput = document.getElementById('pasteImageCaptionInput');
        if (captionInput) {
          captionInput.value = '';
          setTimeout(() => captionInput.focus(), 150);
        }

        openModal('pasteImagePreviewModal');
      };
      reader.readAsDataURL(file);
      break;
    }
  }
}

async function sendPastedImage() {
  if (!state.pastedImageFile || !state.currentConversationId) {
    showToast('Vui lòng chọn cuộc trò chuyện trước khi gửi ảnh!');
    return;
  }

  const captionInput = document.getElementById('pasteImageCaptionInput');
  const caption = captionInput ? captionInput.value.trim() : '';

  const btn = document.getElementById('btnSendPasteImage');
  if (btn) {
    btn.disabled = true;
    btn.innerText = 'Đang gửi ảnh...';
  }

  const formData = new FormData();
  formData.append('message_type', 'image');
  formData.append('attachment', state.pastedImageFile);
  formData.append('content', caption || 'Hình ảnh');

  try {
    const res = await fetch(`/api/conversations/${state.currentConversationId}/send/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
      body: formData
    });
    const newMsg = await res.json();
    if (res.ok) {
      closeModal('pasteImagePreviewModal');
      state.pastedImageFile = null;
      state.messages.push(newMsg);
      state.lastMessageId = newMsg.id;
      renderTimeline();
      scrollChatToBottom();
      playNotificationSound();
      loadConversations();
      showToast('Đã gửi hình ảnh thành công!');
    } else {
      showToast(newMsg.error || 'Gửi ảnh thất bại!');
    }
  } catch (err) {
    showToast('Lỗi kết nối khi gửi ảnh!');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerText = 'Gửi ảnh';
    }
  }
}

// ==============================================================================
// 11. WEBSOCKET REAL-TIME CHAT & WEBRTC P2P VOICE/VIDEO CALLS (Phase 3: LTM Core)
// ==============================================================================

function connectWebSocket(convId) {
  if (state.chatSocket) {
    try {
      state.chatSocket.close();
    } catch (e) {}
    state.chatSocket = null;
  }
  stopWebSocketPing();

  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProto}//${window.location.host}/ws/chat/${convId}/`;

  try {
    const socket = new WebSocket(wsUrl);
    state.chatSocket = socket;

    socket.onopen = () => {
      state.isWsConnected = true;
      console.log(`[WebSocket] Đã kết nối kênh chat ws:// cho hội thoại #${convId}`);
      startWebSocketPing();
      if (state.lastMessageId) {
        sendMarkRead(state.lastMessageId);
      }
      const subtitle = document.getElementById('currentChatSubtitle');
      if (subtitle) {
        const dot = subtitle.querySelector('.online-indicator');
        if (dot) dot.style.backgroundColor = '#10b981';
      }
    };

    socket.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        handleWebSocketMessage(data);
      } catch (err) {
        console.error("[WebSocket] Lỗi xử lý gói tin:", err);
      }
    };

    socket.onclose = (e) => {
      state.isWsConnected = false;
      stopWebSocketPing();
      updateLatencyBadge(null);
      console.log("[WebSocket] Đã đóng kết nối (code:", e.code, ")");
    };

    socket.onerror = (err) => {
      console.warn("[WebSocket] Gặp sự cố kết nối, tự động dự phòng qua HTTP Sync:", err);
      state.isWsConnected = false;
      stopWebSocketPing();
      updateLatencyBadge(null);
    };
  } catch (err) {
    console.warn("[WebSocket] Không thể khởi tạo kết nối socket:", err);
    state.isWsConnected = false;
    stopWebSocketPing();
    updateLatencyBadge(null);
  }
}

function handleWebSocketMessage(data) {
  const type = data.type;

  if (type === 'chat_message') {
    const newMsg = data.message;
    if (!state.messages.some(m => m.id === newMsg.id)) {
      state.messages.push(newMsg);
      state.lastMessageId = newMsg.id;
      renderTimeline();
      scrollChatToBottom();
      playNotificationSound();
      loadConversations();
      if (!newMsg.is_me) {
        sendMarkRead(newMsg.id);
      }
    }
  } else if (type === 'pong') {
    const now = Date.now();
    const rtt = Math.max(1, now - (data.client_timestamp || now));
    state.currentRtt = rtt;
    updateLatencyBadge(rtt);
  } else if (type === 'read_receipt') {
    handleIncomingReadReceipt(data);
  } else if (type === 'typing') {
    const bar = document.getElementById('typingIndicatorBar');
    const text = document.getElementById('typingIndicatorText');
    if (bar && text) {
      if (data.is_typing) {
        text.innerText = `${data.display_name || data.username} đang soạn tin nhắn...`;
        bar.style.display = 'flex';
        scrollChatToBottom();
      } else {
        bar.style.display = 'none';
      }
    }
  } else if (type === 'reaction_update') {
    const msg = state.messages.find(m => m.id === data.message_id);
    if (msg) {
      msg.reactions = data.reactions;
      renderTimeline();
      if (data.reactions && data.reactions.length > 0) {
        const lastReact = data.reactions[data.reactions.length - 1];
        triggerFloatingReaction(data.message_id, lastReact.emoji);
      }
    }
  } else if (type === 'message_recalled') {
    const msg = state.messages.find(m => m.id === data.message_id);
    if (msg) {
      msg.is_recalled = true;
      msg.content = data.content || "Tin nhắn đã được thu hồi";
      renderTimeline();
    }
  } else if (type === 'message_pinned') {
    if (state.currentConversation) {
      state.currentConversation.pinned_message = data.pinned_message;
    }
    updatePinnedMessageBanner(data.pinned_message);
  } else if (type === 'user_status') {
    console.log(`[Presence] Người dùng ${data.display_name} hiện đang ${data.status}`);
  } else if (type === 'webrtc_signal') {
    handleWebRTCSignalMessage(data);
  }
}

function handleTypingInput() {
  if (!state.chatSocket || state.chatSocket.readyState !== WebSocket.OPEN) return;
  if (!state.isTypingSent) {
    state.isTypingSent = true;
    state.chatSocket.send(JSON.stringify({ type: 'typing', is_typing: true }));
  }
  if (state.typingTimer) clearTimeout(state.typingTimer);
  state.typingTimer = setTimeout(() => {
    state.isTypingSent = false;
    if (state.chatSocket && state.chatSocket.readyState === WebSocket.OPEN) {
      state.chatSocket.send(JSON.stringify({ type: 'typing', is_typing: false }));
    }
  }, 2000);
}

// --------------------------------------------------------------------------
// WEBRTC P2P VOICE & VIDEO CALL IMPLEMENTATION
// --------------------------------------------------------------------------

let ringtoneAudioCtx = null;
let ringtoneOsc = null;

function playIncomingRingtone() {
  if (!state.soundEnabled) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    ringtoneAudioCtx = ctx;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(440, ctx.currentTime);
    osc.frequency.setValueAtTime(480, ctx.currentTime + 0.4);
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    ringtoneOsc = osc;
  } catch (e) {}
}

function stopIncomingRingtone() {
  try {
    if (ringtoneOsc) {
      ringtoneOsc.stop();
      ringtoneOsc.disconnect();
      ringtoneOsc = null;
    }
    if (ringtoneAudioCtx) {
      ringtoneAudioCtx.close();
      ringtoneAudioCtx = null;
    }
  } catch (e) {}
}

// ==============================================================================
// 11. WEBRTC P2P VOICE & VIDEO CALL CORE (LTM ADVANCED ARCHITECTURE)
// ==============================================================================

// Creates a virtual video stream from a canvas if physical webcam is busy on the machine
function createVirtualVideoStream(avatarUrl, displayName) {
  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = 480;
  const ctx = canvas.getContext('2d');

  const avatarImg = new Image();
  avatarImg.crossOrigin = 'anonymous';
  avatarImg.src = avatarUrl || 'https://ui-avatars.com/api/?name=User&background=0068ff&color=ffffff';

  let wave = 0;
  function renderFrame() {
    wave += 0.04;
    // Dark modern gradient background
    const grad = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
    grad.addColorStop(0, '#0f172a');
    grad.addColorStop(1, '#1e293b');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2 - 20;
    const radius = 70;

    // Pulse radar rings
    for (let i = 1; i <= 3; i++) {
      ctx.beginPath();
      const r = radius + ((wave * 25 + i * 28) % 65);
      const alpha = Math.max(0, 1 - (r - radius) / 65) * 0.45;
      ctx.arc(centerX, centerY, r, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(0, 104, 255, ${alpha})`;
      ctx.lineWidth = 2.5;
      ctx.stroke();
    }

    // Avatar circle
    ctx.save();
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.closePath();
    ctx.clip();
    if (avatarImg.complete && avatarImg.naturalWidth > 0) {
      ctx.drawImage(avatarImg, centerX - radius, centerY - radius, radius * 2, radius * 2);
    } else {
      ctx.fillStyle = '#0068ff';
      ctx.fillRect(centerX - radius, centerY - radius, radius * 2, radius * 2);
    }
    ctx.restore();

    // Border around avatar
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.strokeStyle = '#0068ff';
    ctx.lineWidth = 3.5;
    ctx.stroke();

    // Display Name
    ctx.fillStyle = '#f8fafc';
    ctx.font = 'bold 20px "Segoe UI", sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(displayName || 'Người dùng', centerX, centerY + radius + 40);

    // Virtual badge
    ctx.fillStyle = '#38bdf8';
    ctx.font = '13px "Segoe UI", sans-serif';
    ctx.fillText('Camera Mô Phỏng (1 Máy)', centerX, centerY + radius + 65);

    state.virtualAnimFrame = requestAnimationFrame(renderFrame);
  }
  renderFrame();

  return canvas.captureStream(25);
}

// Robust Media Stream Acquirer: Falls back gracefully if physical webcam is locked by another tab on same PC
async function acquireMediaStream(isVideo, user) {
  let stream = null;
  state.isVirtualCam = false;

  if (isVideo) {
    try {
      // 1. Try real physical camera & microphone
      stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: { width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      return stream;
    } catch (camErr) {
      console.warn("[WebRTC] Không thể mở webcam thực tế (có thể do đang mở ở tab khác trên cùng 1 máy tính):", camErr);
      showToast("Webcam đang bận (trên cùng 1 máy tính). Hệ thống tự kích hoạt Camera Mô Phỏng để cuộc gọi tiếp tục!");

      // 2. Fall back to real mic + virtual video stream from canvas
      let audioTrack = null;
      try {
        const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        audioTrack = audioStream.getAudioTracks()[0];
      } catch (micErr) {
        console.warn("[WebRTC] Mic cũng không truy cập được:", micErr);
      }

      const virtualStream = createVirtualVideoStream(user?.avatar_url, user?.display_name);
      state.isVirtualCam = true;

      const combinedTracks = [...virtualStream.getVideoTracks()];
      if (audioTrack) combinedTracks.push(audioTrack);

      stream = new MediaStream(combinedTracks);
      return stream;
    }
  } else {
    // Voice-only call
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    } catch (e) {
      console.error("[WebRTC] Lỗi mic cho voice call:", e);
      throw e;
    }
    return stream;
  }
}

function updateCallStageUI(peerName, peerAvatar, statusText, isRinging = false) {
  const nameEl = document.getElementById('callPeerName');
  const avatarEl = document.getElementById('callPeerAvatar');
  const stageName = document.getElementById('callStagePeerName');
  const stageAvatar = document.getElementById('callStageAvatar');
  const stageStatus = document.getElementById('callStageStatusText');
  const durationText = document.getElementById('callDurationText');
  const liveDot = document.getElementById('callLiveDot');
  const avatarStage = document.getElementById('callAvatarStage');
  const remoteVideo = document.getElementById('remoteVideo');

  if (nameEl) nameEl.innerText = peerName || "Đối phương";
  if (avatarEl && peerAvatar) avatarEl.src = peerAvatar;
  if (stageName) stageName.innerText = peerName || "Đối phương";
  if (stageAvatar && peerAvatar) stageAvatar.src = peerAvatar;
  if (stageStatus) stageStatus.innerText = statusText || "";

  if (isRinging) {
    if (durationText) durationText.innerText = "Đang đổ chuông...";
    if (liveDot) liveDot.style.display = 'none';
    if (avatarStage) avatarStage.style.display = 'flex';
    if (remoteVideo) remoteVideo.style.display = 'none';
  }
}

async function logCallRecord(callType, callStatus, duration, callerId) {
  if (!state.currentConversationId) return;
  const payload = {
    call_type: callType || 'voice',
    call_status: callStatus || 'completed',
    duration: duration || 0,
    caller_id: callerId || state.currentUser?.id
  };

  // 1. Send via WebSocket for instant 0ms broadcast to both clients
  if (state.chatSocket && state.chatSocket.readyState === WebSocket.OPEN) {
    state.chatSocket.send(JSON.stringify({
      type: 'call_log',
      ...payload
    }));
  } else {
    // 2. Fallback to REST API
    try {
      await fetch(`/api/conversations/${state.currentConversationId}/log_call/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify(payload)
      });
      await loadConversations();
    } catch (e) {
      console.error("Lỗi log cuộc gọi:", e);
    }
  }
}

async function startWebRTCCall(callType) {
  if (!state.currentConversationId) {
    showToast("Vui lòng chọn một cuộc trò chuyện để bắt đầu cuộc gọi!");
    return;
  }
  if (!state.chatSocket || state.chatSocket.readyState !== WebSocket.OPEN) {
    showToast("Đang kết nối lại kênh thời gian thực... Vui lòng thử lại sau giây lát.");
    return;
  }

  state.currentCallType = callType;
  state.peerMicMuted = false;
  state.peerCamOff = false;
  state.isSwappedVideo = false;
  state.callConnected = false;
  state.callInitiatorId = state.currentUser?.id;
  const isVideo = callType === 'video';

  const modal = document.getElementById('activeCallModal');
  const typeBadge = document.getElementById('callTypeBadge');
  const localPip = document.getElementById('localVideoPip');

  if (typeBadge) typeBadge.innerText = isVideo ? "Cuộc gọi video P2P" : "Cuộc gọi thoại P2P";
  if (localPip) localPip.style.display = isVideo ? 'block' : 'none';
  if (modal) modal.style.display = 'flex';

  const peerName = state.currentConversation?.title || "Đối phương";
  const peerAvatar = state.currentConversation?.avatar_url || "https://ui-avatars.com/api/?name=User&background=0068ff&color=ffffff";
  updateCallStageUI(peerName, peerAvatar, "Đang đổ chuông...", true);

  try {
    const stream = await acquireMediaStream(isVideo, state.currentUser);
    state.localStream = stream;
    const localVideo = document.getElementById('localVideo');
    if (localVideo) localVideo.srcObject = stream;

    // Gửi yêu cầu gọi qua WebSocket tới peer
    state.chatSocket.send(JSON.stringify({
      type: 'webrtc_signal',
      action: 'call_request',
      call_type: callType,
      sender_id: state.currentUser?.id,
      sender_name: state.currentUser?.display_name || "Bạn bè Zalo",
      sender_avatar: state.currentUser?.avatar_url || ""
    }));
    playIncomingRingtone();
  } catch (err) {
    console.error("Lỗi khởi tạo cuộc gọi:", err);
    showToast("Không thể truy cập Microphone hoặc Camera! Vui lòng kiểm tra quyền trình duyệt.");
    endWebRTCCall(false);
  }
}

function handleIncomingCallSignal(signal) {
  state.pendingIncomingSignal = signal;
  const modal = document.getElementById('incomingCallModal');
  const callerName = document.getElementById('incomingCallerName');
  const callerAvatar = document.getElementById('incomingCallerAvatar');
  const callSub = document.getElementById('incomingCallSub');

  if (callerName) callerName.innerText = signal.sender_name || "Bạn bè Zalo";
  if (callerAvatar && signal.sender_avatar) callerAvatar.src = signal.sender_avatar;
  if (callSub) callSub.innerText = signal.call_type === 'video' ? "Cuộc gọi video WebRTC P2P đến..." : "Cuộc gọi thoại WebRTC P2P đến...";

  if (modal) modal.style.display = 'flex';
  playIncomingRingtone();
}

async function acceptIncomingCall() {
  stopIncomingRingtone();
  const modal = document.getElementById('incomingCallModal');
  if (modal) modal.style.display = 'none';

  const signal = state.pendingIncomingSignal;
  if (!signal) return;

  const isVideo = signal.call_type === 'video';
  state.currentCallType = signal.call_type;
  state.peerMicMuted = false;
  state.peerCamOff = false;
  state.isSwappedVideo = false;
  state.callConnected = true;
  state.callInitiatorId = signal.sender_id;

  const callModal = document.getElementById('activeCallModal');
  const typeBadge = document.getElementById('callTypeBadge');
  const localPip = document.getElementById('localVideoPip');

  if (typeBadge) typeBadge.innerText = isVideo ? "Cuộc gọi video P2P" : "Cuộc gọi thoại P2P";
  if (localPip) localPip.style.display = isVideo ? 'block' : 'none';
  if (callModal) callModal.style.display = 'flex';

  const callerName = signal.sender_name || "Đối phương";
  const callerAvatar = signal.sender_avatar || "https://ui-avatars.com/api/?name=User&background=0068ff&color=ffffff";
  updateCallStageUI(callerName, callerAvatar, "Đang kết nối P2P...", false);

  try {
    const stream = await acquireMediaStream(isVideo, state.currentUser);
    state.localStream = stream;
    const localVideo = document.getElementById('localVideo');
    if (localVideo) localVideo.srcObject = stream;

    // Gửi tín hiệu chấp nhận cuộc gọi
    state.chatSocket.send(JSON.stringify({
      type: 'webrtc_signal',
      action: 'call_accept'
    }));

    startCallTimer();
  } catch (err) {
    console.error("Lỗi thiết bị media khi nhận cuộc gọi:", err);
    showToast("Không thể khởi động thiết bị Microphone / Camera!");
    declineIncomingCall();
  }
}

function declineIncomingCall() {
  stopIncomingRingtone();
  const modal = document.getElementById('incomingCallModal');
  if (modal) modal.style.display = 'none';

  const signal = state.pendingIncomingSignal;
  const callType = signal?.call_type || state.currentCallType || 'voice';
  const callerId = signal?.sender_id || state.callInitiatorId;

  if (state.chatSocket && state.chatSocket.readyState === WebSocket.OPEN) {
    state.chatSocket.send(JSON.stringify({
      type: 'webrtc_signal',
      action: 'call_reject'
    }));
  }

  // Lưu lịch sử cuộc gọi bị từ chối
  logCallRecord(callType, 'rejected', 0, callerId);

  state.pendingIncomingSignal = null;
}

function createPeerConnection() {
  if (state.peerConnection) return state.peerConnection;

  const pc = new RTCPeerConnection(state.rtcConfig);
  state.peerConnection = pc;

  if (state.localStream) {
    state.localStream.getTracks().forEach(track => {
      pc.addTrack(track, state.localStream);
    });
  }

  pc.ontrack = (event) => {
    console.log("[WebRTC] Đã nhận remote stream track:", event.track.kind);
    const remoteVideo = document.getElementById('remoteVideo');
    const avatarStage = document.getElementById('callAvatarStage');

    if (remoteVideo) {
      if (event.streams && event.streams[0]) {
        remoteVideo.srcObject = event.streams[0];
      } else {
        if (!remoteVideo.srcObject) remoteVideo.srcObject = new MediaStream();
        remoteVideo.srcObject.addTrack(event.track);
      }

      remoteVideo.play().catch(e => console.warn("[WebRTC] Autoplay remoteVideo bị hạn chế:", e));

      if (event.track.kind === 'video' && state.currentCallType === 'video' && !state.peerCamOff) {
        remoteVideo.style.display = 'block';
        if (avatarStage) avatarStage.style.display = 'none';
      }
    }
  };

  pc.onicecandidate = (event) => {
    if (event.candidate && state.chatSocket && state.chatSocket.readyState === WebSocket.OPEN) {
      state.chatSocket.send(JSON.stringify({
        type: 'webrtc_signal',
        action: 'ice_candidate',
        candidate: event.candidate
      }));
    }
  };

  pc.onconnectionstatechange = () => {
    console.log("[WebRTC] Trạng thái kết nối:", pc.connectionState);
    const liveDot = document.getElementById('callLiveDot');
    const stageStatus = document.getElementById('callStageStatusText');

    if (pc.connectionState === 'connected') {
      stopIncomingRingtone();
      if (liveDot) liveDot.style.display = 'inline-block';
      if (stageStatus) stageStatus.innerText = "Đang đàm thoại WebRTC P2P";
    } else if (pc.connectionState === 'disconnected' || pc.connectionState === 'failed') {
      endWebRTCCall(false);
    }
  };

  return pc;
}

async function addIceCandidateSafely(candidate) {
  if (!state.peerConnection) return;
  if (state.peerConnection.remoteDescription && state.peerConnection.remoteDescription.type) {
    try {
      await state.peerConnection.addIceCandidate(new RTCIceCandidate(candidate));
    } catch (e) {
      console.warn("[WebRTC] Lỗi addIceCandidate:", e);
    }
  } else {
    state.iceCandidatesQueue.push(candidate);
  }
}

async function flushIceCandidatesQueue() {
  if (!state.peerConnection || !state.peerConnection.remoteDescription) return;
  while (state.iceCandidatesQueue.length > 0) {
    const cand = state.iceCandidatesQueue.shift();
    try {
      await state.peerConnection.addIceCandidate(new RTCIceCandidate(cand));
    } catch (e) {
      console.warn("[WebRTC] Lỗi flush candidate:", e);
    }
  }
}

async function handleWebRTCSignalMessage(data) {
  const action = data.action;

  if (action === 'call_request') {
    handleIncomingCallSignal(data);
  } else if (action === 'call_accept') {
    state.callConnected = true;
    stopIncomingRingtone();
    const stageStatus = document.getElementById('callStageStatusText');
    if (stageStatus) stageStatus.innerText = "Đối phương đã nhận lời, đang thiết lập kênh P2P...";

    const pc = createPeerConnection();
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    state.chatSocket.send(JSON.stringify({
      type: 'webrtc_signal',
      action: 'offer',
      sdp: pc.localDescription
    }));
    startCallTimer();
  } else if (action === 'call_reject') {
    stopIncomingRingtone();
    showToast("Đối phương đã từ chối cuộc gọi.");
    endWebRTCCall(false);
  } else if (action === 'offer') {
    const pc = createPeerConnection();
    await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
    await flushIceCandidatesQueue();

    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    state.chatSocket.send(JSON.stringify({
      type: 'webrtc_signal',
      action: 'answer',
      sdp: pc.localDescription
    }));
  } else if (action === 'answer') {
    if (state.peerConnection) {
      await state.peerConnection.setRemoteDescription(new RTCSessionDescription(data.sdp));
      await flushIceCandidatesQueue();
    }
  } else if (action === 'ice_candidate') {
    if (data.candidate) {
      await addIceCandidateSafely(data.candidate);
    }
  } else if (action === 'peer_mic_toggle') {
    state.peerMicMuted = data.is_muted;
    const badge = document.getElementById('callPeerMicBadge');
    if (badge) badge.style.display = state.peerMicMuted ? 'flex' : 'none';
    showToast(`Đối phương đã ${state.peerMicMuted ? 'tắt' : 'bật'} mic.`);
  } else if (action === 'peer_cam_toggle') {
    state.peerCamOff = data.is_cam_off;
    const remoteVideo = document.getElementById('remoteVideo');
    const avatarStage = document.getElementById('callAvatarStage');
    const stageStatus = document.getElementById('callStageStatusText');

    if (state.peerCamOff) {
      if (remoteVideo) remoteVideo.style.display = 'none';
      if (avatarStage) avatarStage.style.display = 'flex';
      if (stageStatus) stageStatus.innerText = "Đối phương đã tắt camera";
    } else {
      if (remoteVideo) remoteVideo.style.display = 'block';
      if (avatarStage) avatarStage.style.display = 'none';
    }
    showToast(`Đối phương đã ${state.peerCamOff ? 'tắt' : 'bật'} camera.`);
  } else if (action === 'call_end') {
    showToast("Cuộc gọi đã kết thúc.");
    endWebRTCCall(false);
  }
}

function startCallTimer() {
  state.callStartTime = Date.now();
  if (state.callTimerInterval) clearInterval(state.callTimerInterval);
  const liveDot = document.getElementById('callLiveDot');
  if (liveDot) liveDot.style.display = 'inline-block';

  state.callTimerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - state.callStartTime) / 1000);
    const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const secs = String(elapsed % 60).padStart(2, '0');
    const timerText = document.getElementById('callDurationText');
    if (timerText) timerText.innerText = `${mins}:${secs}`;
  }, 1000);
}

function toggleCallMic() {
  state.isMicMuted = !state.isMicMuted;

  // 1. Mute/unmute all local audio tracks
  if (state.localStream) {
    state.localStream.getAudioTracks().forEach(track => {
      track.enabled = !state.isMicMuted;
    });
  }

  // 2. Mute/unmute all RTCRtpSender tracks
  if (state.peerConnection) {
    state.peerConnection.getSenders().forEach(sender => {
      if (sender.track && sender.track.kind === 'audio') {
        sender.track.enabled = !state.isMicMuted;
      }
    });
  }

  // 3. Update Mic Button UI
  const btn = document.getElementById('btnToggleMic');
  const iconOn = document.getElementById('micIconOn');
  const iconOff = document.getElementById('micIconOff');
  const pipBadge = document.getElementById('pipMicBadge');

  if (btn) btn.classList.toggle('off', state.isMicMuted);
  if (iconOn) iconOn.style.display = state.isMicMuted ? 'none' : 'block';
  if (iconOff) iconOff.style.display = state.isMicMuted ? 'block' : 'none';
  if (pipBadge) pipBadge.style.display = state.isMicMuted ? 'inline' : 'none';

  // 4. Notify peer through WebSocket signaling
  if (state.chatSocket && state.chatSocket.readyState === WebSocket.OPEN) {
    state.chatSocket.send(JSON.stringify({
      type: 'webrtc_signal',
      action: 'peer_mic_toggle',
      is_muted: state.isMicMuted
    }));
  }

  if (state.isMicMuted) {
    showToast("Đã tắt mic của bạn. (Lưu ý: Nếu đang thử 2 tab trên cùng 1 máy tính, hãy tắt mic cả 2 tab để tránh micro tab kia thu tiếng)");
  } else {
    showToast("Đã bật mic của bạn.");
  }
}

function toggleCallCam() {
  state.isCamOff = !state.isCamOff;

  // 1. Mute/unmute all local video tracks
  if (state.localStream) {
    state.localStream.getVideoTracks().forEach(track => {
      track.enabled = !state.isCamOff;
    });
  }

  // 2. Mute/unmute all RTCRtpSender video tracks
  if (state.peerConnection) {
    state.peerConnection.getSenders().forEach(sender => {
      if (sender.track && sender.track.kind === 'video') {
        sender.track.enabled = !state.isCamOff;
      }
    });
  }

  // 3. Update Cam Button UI
  const btn = document.getElementById('btnToggleCam');
  const iconOn = document.getElementById('camIconOn');
  const iconOff = document.getElementById('camIconOff');
  const localPip = document.getElementById('localVideoPip');

  if (btn) btn.classList.toggle('off', state.isCamOff);
  if (iconOn) iconOn.style.display = state.isCamOff ? 'none' : 'block';
  if (iconOff) iconOff.style.display = state.isCamOff ? 'block' : 'none';
  if (localPip) localPip.style.opacity = state.isCamOff ? '0.4' : '1';

  // 4. Notify peer through WebSocket signaling
  if (state.chatSocket && state.chatSocket.readyState === WebSocket.OPEN) {
    state.chatSocket.send(JSON.stringify({
      type: 'webrtc_signal',
      action: 'peer_cam_toggle',
      is_cam_off: state.isCamOff
    }));
  }

  showToast(state.isCamOff ? "Đã tắt camera của bạn." : "Đã bật camera của bạn.");
}

function toggleSwapVideo() {
  const remoteVideo = document.getElementById('remoteVideo');
  const localVideo = document.getElementById('localVideo');
  const labelText = document.getElementById('pipLabelText');
  if (!remoteVideo || !localVideo) return;

  state.isSwappedVideo = !state.isSwappedVideo;
  const temp = remoteVideo.srcObject;
  remoteVideo.srcObject = localVideo.srcObject;
  localVideo.srcObject = temp;

  remoteVideo.play().catch(e => {});
  localVideo.play().catch(e => {});

  if (labelText) {
    labelText.innerText = state.isSwappedVideo ? (state.currentConversation?.title || "Đối phương") : "Bạn";
  }
}

function toggleFullscreenCall() {
  const card = document.getElementById('callWindowCard');
  if (!card) return;
  card.classList.toggle('fullscreen');
}

function endWebRTCCall(sendSignal = true) {
  stopIncomingRingtone();
  clearInterval(state.callTimerInterval);
  state.callTimerInterval = null;

  if (state.virtualAnimFrame) {
    cancelAnimationFrame(state.virtualAnimFrame);
    state.virtualAnimFrame = null;
  }

  // Tính thời gian đàm thoại và lưu lịch sử cuộc gọi
  let duration = 0;
  if (state.callStartTime && state.callConnected) {
    duration = Math.max(1, Math.floor((Date.now() - state.callStartTime) / 1000));
  }
  const callStatus = state.callConnected ? 'completed' : 'missed';

  if (sendSignal) {
    if (state.chatSocket && state.chatSocket.readyState === WebSocket.OPEN) {
      state.chatSocket.send(JSON.stringify({
        type: 'webrtc_signal',
        action: 'call_end'
      }));
    }
    // Ghi nhận lịch sử cuộc gọi vào hội thoại
    logCallRecord(
      state.currentCallType || 'voice',
      callStatus,
      duration,
      state.callInitiatorId || state.currentUser?.id
    );
  }

  state.callStartTime = null;
  state.callConnected = false;

  if (state.peerConnection) {
    state.peerConnection.close();
    state.peerConnection = null;
  }

  if (state.localStream) {
    state.localStream.getTracks().forEach(t => t.stop());
    state.localStream = null;
  }

  const remoteVideo = document.getElementById('remoteVideo');
  if (remoteVideo) remoteVideo.srcObject = null;
  const localVideo = document.getElementById('localVideo');
  if (localVideo) localVideo.srcObject = null;

  const modal = document.getElementById('activeCallModal');
  if (modal) modal.style.display = 'none';

  // Reset controls state
  state.isMicMuted = false;
  state.isCamOff = false;
  state.peerMicMuted = false;
  state.peerCamOff = false;
  state.isVirtualCam = false;
  state.isSwappedVideo = false;
  state.iceCandidatesQueue = [];

  const btnMic = document.getElementById('btnToggleMic');
  if (btnMic) btnMic.classList.remove('off');
  const micOn = document.getElementById('micIconOn');
  const micOff = document.getElementById('micIconOff');
  if (micOn) micOn.style.display = 'block';
  if (micOff) micOff.style.display = 'none';

  const btnCam = document.getElementById('btnToggleCam');
  if (btnCam) btnCam.classList.remove('off');
  const camOn = document.getElementById('camIconOn');
  const camOff = document.getElementById('camIconOff');
  if (camOn) camOn.style.display = 'block';
  if (camOff) camOff.style.display = 'none';

  const pipBadge = document.getElementById('pipMicBadge');
  if (pipBadge) pipBadge.style.display = 'none';
  const peerMicBadge = document.getElementById('callPeerMicBadge');
  if (peerMicBadge) peerMicBadge.style.display = 'none';

  const card = document.getElementById('callWindowCard');
  if (card) card.classList.remove('fullscreen');
}

// ==============================================================================
// 12. EVENT LISTENERS INITIALIZATION
// ==============================================================================

document.addEventListener('DOMContentLoaded', () => {
  // Theme check
  const savedTheme = localStorage.getItem('zalo_dark_mode');
  if (savedTheme === 'true') {
    document.body.classList.add('dark-theme');
    state.darkMode = true;
    const darkToggle = document.getElementById('toggleDarkMode');
    if (darkToggle) darkToggle.checked = true;
  }

  // Dark mode toggle listener
  const darkToggle = document.getElementById('toggleDarkMode');
  if (darkToggle) {
    darkToggle.onchange = (e) => {
      state.darkMode = e.target.checked;
      document.body.classList.toggle('dark-theme', state.darkMode);
      localStorage.setItem('zalo_dark_mode', state.darkMode ? 'true' : 'false');
    };
  }

  // Sound toggle listener
  const soundToggle = document.getElementById('toggleSound');
  if (soundToggle) {
    soundToggle.onchange = (e) => {
      state.soundEnabled = e.target.checked;
    };
  }

  // Check user session
  checkCurrentUser();

  // Rail Navigation Items
  document.getElementById('tabMessages')?.addEventListener('click', () => switchMainTab('messages'));
  document.getElementById('tabContacts')?.addEventListener('click', () => switchMainTab('contacts'));
  document.getElementById('tabTasks')?.addEventListener('click', () => switchMainTab('tasks'));
  document.getElementById('tabCloud')?.addEventListener('click', openCloudConversation);

  // Rail Avatar click -> opens Profile modal
  document.getElementById('railUserAvatarBtn')?.addEventListener('click', () => {
    updateUserUI();
    openModal('profileModal');
  });

  // Rail Auth click -> toggles User Account Popover
  document.getElementById('railAuthBtn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    const popover = document.getElementById('userAccountPopover');
    if (popover) {
      popover.style.display = popover.style.display === 'none' ? 'block' : 'none';
    }
  });

  // Account Popover items
  document.getElementById('popoverBtnProfile')?.addEventListener('click', () => {
    document.getElementById('userAccountPopover').style.display = 'none';
    openModal('profileModal');
  });
  document.getElementById('popoverBtnSettings')?.addEventListener('click', () => {
    document.getElementById('userAccountPopover').style.display = 'none';
    openModal('settingsModal');
  });
  document.getElementById('popoverBtnLogout')?.addEventListener('click', () => {
    document.getElementById('userAccountPopover').style.display = 'none';
    handleLogout();
  });

  // Rail Settings click
  document.getElementById('railSettingsBtn')?.addEventListener('click', () => {
    openModal('settingsModal');
  });

  // Close Popovers when clicking outside
  document.addEventListener('click', (e) => {
    const popover = document.getElementById('userAccountPopover');
    if (popover && !popover.contains(e.target) && !document.getElementById('railAuthBtn')?.contains(e.target)) {
      popover.style.display = 'none';
    }

    const emojiPopover = document.getElementById('emojiPickerPopover');
    if (emojiPopover && !emojiPopover.contains(e.target) && !document.getElementById('btnEmojiTool')?.contains(e.target)) {
      emojiPopover.style.display = 'none';
    }

    const filterMenu = document.getElementById('filterDropdownMenu');
    if (filterMenu && !filterMenu.contains(e.target) && !document.getElementById('btnFilterDropdown')?.contains(e.target)) {
      filterMenu.style.display = 'none';
    }
  });

  // Filter Dropdown
  const btnFilter = document.getElementById('btnFilterDropdown');
  const filterMenu = document.getElementById('filterDropdownMenu');
  if (btnFilter && filterMenu) {
    btnFilter.addEventListener('click', (e) => {
      e.stopPropagation();
      filterMenu.style.display = filterMenu.style.display === 'none' ? 'block' : 'none';
    });

    document.querySelectorAll('.filter-menu-item').forEach(item => {
      item.addEventListener('click', () => {
        document.querySelectorAll('.filter-menu-item').forEach(i => i.classList.remove('active'));
        item.classList.add('active');
        state.activeFilter = item.dataset.filter;
        document.getElementById('filterLabelText').innerText = item.innerText;
        filterMenu.style.display = 'none';
        renderConversationsList();
      });
    });
  }

  // Priority vs Other Tabs
  document.getElementById('tabPriority')?.addEventListener('click', () => {
    document.getElementById('tabPriority').classList.add('active');
    document.getElementById('tabOther')?.classList.remove('active');
    state.activeSubTab = 'priority';
    renderConversationsList();
  });
  document.getElementById('tabOther')?.addEventListener('click', () => {
    document.getElementById('tabOther').classList.add('active');
    document.getElementById('tabPriority')?.classList.remove('active');
    state.activeSubTab = 'other';
    renderConversationsList();
  });

  // In-Chat Search
  document.getElementById('btnSearchMessages')?.addEventListener('click', () => {
    const searchBar = document.getElementById('inChatSearchBar');
    if (searchBar) {
      searchBar.style.display = searchBar.style.display === 'none' ? 'flex' : 'none';
      if (searchBar.style.display === 'flex') {
        document.getElementById('inChatSearchInput')?.focus();
      }
    }
  });

  document.getElementById('btnCloseSearch')?.addEventListener('click', () => {
    const searchBar = document.getElementById('inChatSearchBar');
    if (searchBar) searchBar.style.display = 'none';
    document.getElementById('inChatSearchInput').value = '';
    handleInChatSearch('');
  });

  document.getElementById('inChatSearchInput')?.addEventListener('input', (e) => {
    handleInChatSearch(e.target.value.trim());
  });

  // Conversation Info Drawer Toggle
  document.getElementById('btnToggleInfo')?.addEventListener('click', () => {
    const sidebar = document.getElementById('chatInfoSidebar');
    if (sidebar) {
      sidebar.style.display = sidebar.style.display === 'none' ? 'flex' : 'none';
    }
  });

  document.getElementById('btnCloseInfoSidebar')?.addEventListener('click', () => {
    const sidebar = document.getElementById('chatInfoSidebar');
    if (sidebar) sidebar.style.display = 'none';
  });

  // Emoji Popover Toggle & Setup
  initEmojiPicker();
  document.getElementById('btnEmojiTool')?.addEventListener('click', (e) => {
    e.stopPropagation();
    const popover = document.getElementById('emojiPickerPopover');
    if (popover) {
      popover.style.display = popover.style.display === 'none' ? 'block' : 'none';
    }
  });

  // New Chat & Friend Search Modal
  document.getElementById('btnNewChat')?.addEventListener('click', openNewChatModal);
  document.getElementById('newChatSearchInput')?.addEventListener('input', (e) => {
    loadUsersForNewChat(e.target.value.trim());
  });

  const phoneInput = document.getElementById('friendSearchPhoneInput');
  const btnSearchPhone = document.getElementById('btnSearchFriendByPhone');
  const btnClearPhone = document.getElementById('btnClearPhoneInput');

  if (phoneInput) {
    phoneInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        searchFriendByPhone();
      }
    });
    phoneInput.addEventListener('input', (e) => {
      if (btnClearPhone) {
        btnClearPhone.style.display = e.target.value.trim() ? 'block' : 'none';
      }
    });
  }

  if (btnClearPhone) {
    btnClearPhone.addEventListener('click', () => {
      if (phoneInput) {
        phoneInput.value = '';
        phoneInput.focus();
      }
      btnClearPhone.style.display = 'none';
      const resultArea = document.getElementById('friendSearchResultArea');
      if (resultArea) {
        resultArea.innerHTML = `
          <div class="phone-search-tip">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
            <span>Nhập số điện thoại để tìm kiếm bạn bè trên Zalo</span>
          </div>
        `;
      }
    });
  }

  if (btnSearchPhone) {
    btnSearchPhone.addEventListener('click', () => searchFriendByPhone());
  }

  // Quick sample phone chips in modal
  document.querySelectorAll('.quick-phone-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const p = chip.dataset.phone;
      if (phoneInput) {
        phoneInput.value = p;
        if (btnClearPhone) btnClearPhone.style.display = 'block';
      }
      searchFriendByPhone(p);
    });
  });

  // Save Profile & Auth
  document.getElementById('btnSaveProfile')?.addEventListener('click', saveProfile);
  document.getElementById('btnSubmitAuth')?.addEventListener('click', handleAuthSubmit);

  // Avatar Preview
  document.getElementById('modalAvatarInput')?.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      const reader = new FileReader();
      reader.onload = ev => {
        document.getElementById('profileModalAvatar').src = ev.target.result;
      };
      reader.readAsDataURL(e.target.files[0]);
    }
  });

  // Conversation Search input
  document.getElementById('conversationSearchInput')?.addEventListener('input', (e) => {
    loadConversations(e.target.value.trim());
  });

  // Chat input Enter to send & Ctrl+V Paste Images
  const chatInput = document.getElementById('chatInputText');
  if (chatInput) {
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendTextMessage();
      }
    });

    // Paste image from Clipboard (Ctrl + V / Snipping Tool)
    chatInput.addEventListener('paste', (e) => {
      const clipboardData = e.clipboardData || window.clipboardData;
      if (!clipboardData) return;
      const items = clipboardData.items;
      for (let i = 0; i < items.length; i++) {
        if (items[i].type && items[i].type.startsWith('image/')) {
          const file = items[i].getAsFile();
          if (file) {
            e.preventDefault();
            uploadImageMessage(file);
            return;
          }
        }
      }
    });
  }

  // Drag & Drop Files and Images onto Chat Area
  const chatMainArea = document.getElementById('chatMainArea');
  const dragOverlay = document.getElementById('chatDragOverlay');
  let dragCounter = 0;

  if (chatMainArea) {
    chatMainArea.addEventListener('dragenter', (e) => {
      e.preventDefault();
      dragCounter++;
      if (dragOverlay) dragOverlay.style.display = 'flex';
    });

    chatMainArea.addEventListener('dragover', (e) => {
      e.preventDefault();
    });

    chatMainArea.addEventListener('dragleave', (e) => {
      e.preventDefault();
      dragCounter--;
      if (dragCounter <= 0) {
        dragCounter = 0;
        if (dragOverlay) dragOverlay.style.display = 'none';
      }
    });

    chatMainArea.addEventListener('drop', (e) => {
      e.preventDefault();
      dragCounter = 0;
      if (dragOverlay) dragOverlay.style.display = 'none';

      if (!state.currentConversationId) {
        showToast("Vui lòng chọn một cuộc trò chuyện để gửi tệp tin!");
        return;
      }

      const files = e.dataTransfer?.files;
      if (files && files.length > 0) {
        for (let i = 0; i < files.length; i++) {
          const file = files[i];
          if (file.type && file.type.startsWith('image/')) {
            uploadImageMessage(file);
          } else {
            uploadDocFile(file);
          }
        }
      }
    });
  }

  document.getElementById('btnSendMessage')?.addEventListener('click', sendTextMessage);

  // Attachments
  document.getElementById('imageFileInput')?.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      uploadImageMessage(e.target.files[0]);
      e.target.value = '';
    }
  });

  document.getElementById('docFileInput')?.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      uploadDocFile(e.target.files[0]);
      e.target.value = '';
    }
  });

  // Voice Note Recording
  document.getElementById('btnRecordVoice')?.addEventListener('click', startVoiceRecording);
  document.getElementById('btnCancelRecord')?.addEventListener('click', cancelVoiceRecording);
  document.getElementById('btnSendRecord')?.addEventListener('click', stopAndSendVoiceRecording);

  // Code Snippet
  document.getElementById('btnOpenCodeModal')?.addEventListener('click', () => openModal('codeSnippetModal'));
  document.getElementById('btnSendCodeSnippet')?.addEventListener('click', sendCodeSnippet);

  // Group Creation
  document.getElementById('btnNewGroup')?.addEventListener('click', openCreateGroupModal);
  document.getElementById('btnSubmitCreateGroup')?.addEventListener('click', submitCreateGroup);
  
  // Add Member to Group
  document.getElementById('btnAddMemberBtn')?.addEventListener('click', openAddMemberModal);
  document.getElementById('addMemberSearchInput')?.addEventListener('input', (e) => {
    loadUsersForAddMember(e.target.value.trim());
  });

  // Pin & Mute & Priority Actions (Database Persisted)
  document.getElementById('btnPinChat')?.addEventListener('click', togglePinConversation);
  document.getElementById('btnMuteNotif')?.addEventListener('click', toggleMuteConversation);
  document.getElementById('btnTogglePriority')?.addEventListener('click', togglePriorityConversation);

  // Tasks / Reminders
  document.getElementById('btnReminder')?.addEventListener('click', () => openModal('createTaskModal'));
  document.getElementById('btnOpenCreateTask')?.addEventListener('click', () => openModal('createTaskModal'));
  document.getElementById('btnSubmitCreateTask')?.addEventListener('click', submitCreateTask);

  // Phase 3: Typing Indicator Listener
  document.getElementById('chatInputText')?.addEventListener('input', handleTypingInput);

  // Phase 3: WebRTC Voice & Video Call Buttons
  document.getElementById('btnCallVoice')?.addEventListener('click', () => startWebRTCCall('voice'));
  document.getElementById('btnCallVideo')?.addEventListener('click', () => startWebRTCCall('video'));

  // WebRTC Active Call Modal Controls
  document.getElementById('btnToggleMic')?.addEventListener('click', toggleCallMic);
  document.getElementById('btnToggleCam')?.addEventListener('click', toggleCallCam);
  document.getElementById('btnEndCall')?.addEventListener('click', () => endWebRTCCall(true));
  document.getElementById('btnMinimizeCall')?.addEventListener('click', () => {
    document.getElementById('activeCallModal').style.display = 'none';
  });
  document.getElementById('btnSwapVideo')?.addEventListener('click', toggleSwapVideo);
  document.getElementById('btnToggleFullscreen')?.addEventListener('click', toggleFullscreenCall);

  // WebRTC Incoming Call Modal Controls
  document.getElementById('btnAcceptCall')?.addEventListener('click', acceptIncomingCall);
  document.getElementById('btnDeclineCall')?.addEventListener('click', declineIncomingCall);

  // Phase 2: Reply & Pinned Message Banner Events
  document.getElementById('btnCancelReply')?.addEventListener('click', cancelReply);
  document.getElementById('btnJumpToPinned')?.addEventListener('click', () => scrollToMessage(state.pinnedMessageId));
  document.getElementById('pinnedMessageContent')?.addEventListener('click', () => scrollToMessage(state.pinnedMessageId));
  document.getElementById('btnUnpinMessage')?.addEventListener('click', unpinConversationMessage);

  // Close message more menu on outside click
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.msg-more-dropdown-container')) {
      document.querySelectorAll('.msg-more-menu.show').forEach(m => m.classList.remove('show'));
    }
  });

  // Phase 4: Custom Context Menu, Clipboard Paste Image, Forward Modal
  initContextMenu();
  initClipboardPaste();
  document.getElementById('btnConfirmForward')?.addEventListener('click', confirmForwardMessage);
});


