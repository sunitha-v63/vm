let conversationId = localStorage.getItem("chat_conversation_id") || null;
let pendingDeleteId = null;
let renameTargetId = null;
let singleDeleteMode = false;
let messageToDelete = null;

function getLang() {
    return localStorage.getItem("chat_lang") || "en";
}


function getCookie(name) {
    let value = null;
    document.cookie.split(";").forEach(cookie => {
        const c = cookie.trim();
        if (c.startsWith(name + "=")) {
            value = decodeURIComponent(c.substring(name.length + 1));
        }
    });
    return value;
}

function toggleSidebar() {
    document.getElementById("sidebarPanel").classList.toggle("show");
    document.getElementById("overlay").classList.toggle("show");
}

const overlay = document.getElementById("overlay");

if (overlay) {
    overlay.addEventListener("click", () => {
        document.getElementById("sidebarPanel").classList.remove("show");
        overlay.classList.remove("show");
    });
}

async function loadConversationList() {

    const langSelect = document.getElementById("langSelect");
    const lang = langSelect ? langSelect.value : (localStorage.getItem("chat_lang") || "en");

    localStorage.setItem("chat_lang", lang);

    const resp = await fetch(`/api/conversations/?lang=${lang}`);
    const convos = await resp.json();

    const pinnedList = document.getElementById("pinnedList");
    const convList = document.getElementById("convList");

    pinnedList.innerHTML = "";
    convList.innerHTML = "";

    convos.forEach(c => {
        const item = document.createElement("div");
        item.className = "conv-item";
        item.setAttribute("data-convo", c.id);

        item.innerHTML = `
            <div class="conv-top">
                <span class="conv-title">${c.title}</span>
                <div class="conv-actions">
                    <span onclick="event.stopPropagation(); renameConv(${c.id})">✏️</span>
                    <span onclick="event.stopPropagation(); pinConv(${c.id})">${c.pinned ? "📍" : "📌"}</span>
                    <span onclick="event.stopPropagation(); deleteConversation(${c.id})">🗑️</span>
                </div>
            </div>
            <div class="conv-preview">${c.preview || "No messages yet"}</div>
        `;

        item.onclick = () => loadConversation(c.id);

        if (c.pinned) pinnedList.appendChild(item);
        else convList.appendChild(item);
    });

    const pinnedTitle = document.getElementById("pinnedTitle");
    pinnedTitle.style.display = pinnedList.children.length ? "block" : "none";
}

async function loadConversation(cid) {
    conversationId = cid;
    localStorage.setItem("chat_conversation_id", cid);

    if (window.innerWidth <= 992) {
        document.getElementById("sidebarPanel").classList.remove("show");
        document.getElementById("overlay").classList.remove("show");
    }

    const lang = getLang();

    const resp = await fetch(`/api/messages/${cid}/?lang=${lang}`);
    const msgs = await resp.json();

    const box = document.getElementById("chatBox");
    box.innerHTML = "";

    msgs.forEach(m =>
        addMessage(
            m.content,
            m.sender,
            m.id || m.message_id || m.pk,
            false
        )
    );
}


function showPinned() {
    document.getElementById("pinnedList").style.display = "block";
    document.getElementById("convList").style.display = "none";

    document.getElementById("pinnedTitle").classList.add("active");
    document.getElementById("allTitle").classList.remove("active");
}

function showAll() {
    document.getElementById("pinnedList").style.display = "none";
    document.getElementById("convList").style.display = "block";

    document.getElementById("allTitle").classList.add("active");
    document.getElementById("pinnedTitle").classList.remove("active");
}

function closeChat() {
    window.history.back();  
}
async function sendMessage() {
    const input = document.getElementById("messageInput");
    const msg = input.value.trim();
    if (!msg) return;

    addMessage(msg, "user");
    input.value = "";
    showTyping();

    const lang = getLang();

    const resp = await fetch("/api/chat/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken")
        },
        body: JSON.stringify({
            query: msg,
            conversation_id: conversationId,
            lang: lang
        })
    });

    const data = await resp.json();
    hideTyping();

    addMessage(data.response, "bot", data.message_id, true);

    conversationId = data.conversation_id;
    localStorage.setItem("chat_conversation_id", conversationId);

    loadConversationList();
}


function deleteConversation(cid) {
    pendingDeleteId = cid;
    document.getElementById("confirmPopup").style.display = "flex";
}

function cancelDelete() {
    pendingDeleteId = null;
    document.getElementById("confirmPopup").style.display = "none";
}

async function confirmDelete() {
    const cid = pendingDeleteId;
    pendingDeleteId = null;

    document.getElementById("confirmPopup").style.display = "none";

    window.speechSynthesis.cancel();

    const resp = await fetch(`/api/delete/${cid}/`, {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") }
    });

    if (conversationId == cid) {
        conversationId = null;
        localStorage.removeItem("chat_conversation_id");
        document.getElementById("chatBox").innerHTML = ""; 
    }

    showUndoToast(cid);

    loadConversationList();
}

function showUndoToast(cid) {
    const root = document.getElementById("toastRoot");
    const toast = document.createElement("div");

    toast.className = "toast";
    toast.innerHTML = `
        Conversation deleted.
        <button onclick="undoDelete(${cid}, this)" class="btn btn-success btn-sm">Undo</button>
    `;

    root.appendChild(toast);
    setTimeout(() => toast.remove(), 6000);
}

async function undoDelete(cid, btn) {
    btn.disabled = true;

    const resp = await fetch(`/api/restore/${cid}/`, {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") }
    });

    loadConversationList();
}

function renameConv(id) {
    renameTargetId = id;
    document.getElementById("renameModal").style.display = "flex";
}

function closeRenameModal() {
    document.getElementById("renameModal").style.display = "none";
}

async function submitRename() {
    const newTitle = document.getElementById("renameInput").value.trim();
    if (!newTitle) return;

    await fetch(`/api/rename/${renameTargetId}/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken")
        },
        body: JSON.stringify({ title: newTitle })
    });

    closeRenameModal();
    loadConversationList();
}

async function pinConv(id) {
    const resp = await fetch(`/api/pin/${id}/`, {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") }
    });

    const data = await resp.json();
    loadConversationList();
}

function addMessage(text, role, messageId = null, speak = false) {
    const box = document.getElementById("chatBox");

    const msg = document.createElement("div");
    msg.className = `msg ${role}`;

    if (messageId) {
        msg.setAttribute("data-id", messageId);
    }

    const avatar = document.createElement("img");
    avatar.className = "avatar";
    avatar.src = role === "user"
        ? "/static/images/user.png"
        : "/static/images/bot.jpg";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = text;

    if (role === "bot") {
        bubble.style.cursor = "pointer";

        bubble.addEventListener("click", () => {
            if (voiceEnabled) {
                speakText(bubble.innerText || bubble.textContent);
            }
        });
    }

    if (role === "bot") {
        msg.appendChild(avatar);
        msg.appendChild(bubble);

        if (speak && voiceEnabled) {
            speakText(text);
        }

    } else {
        msg.appendChild(bubble);
        msg.appendChild(avatar);
    }

    box.appendChild(msg);
    box.scrollTop = box.scrollHeight;
}

function getSelectedLanguage() {
    return document.getElementById("langSelect")?.value || "en";
}


function speakText(message) {
    if (!window.speechSynthesis || !voiceEnabled) return;

    const lang = getSelectedLanguage();
    const utter = new SpeechSynthesisUtterance(message);

    if (lang === "hi") {
        utter.lang = "hi-IN";
    }
    else if (lang === "ta") {
        utter.lang = "en-US";  
    }
    else if (lang === "ml") {
        utter.lang = "en-US";   
    }
    else {
        utter.lang = "en-US";
    }

    utter.pitch = 1;
    utter.rate = 1;

    window.speechSynthesis.speak(utter);
}

function showTyping() {
    const box = document.getElementById("chatBox");
    const t = document.createElement("div");

    t.id = "typing";
    t.className = "typing-indicator";
    t.innerHTML = `
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
    `;
    box.appendChild(t);
}

function hideTyping() {
    const t = document.getElementById("typing");
    if (t) t.remove();
}

loadConversationList();
if (conversationId) loadConversation(conversationId);

function filterChats() {
    const q = document.getElementById("sidebarSearch").value.toLowerCase();
    const items = document.querySelectorAll(".conv-item");
    let visibleCount = 0;

    if (q.trim() === "") {
        items.forEach(item => item.style.display = "");
        const noResultBox = document.getElementById("noResults");
        if (noResultBox) noResultBox.style.display = "none";
        return;
    }

    items.forEach(item => {
        const text = item.innerText.toLowerCase();
        if (text.includes(q)) {
            item.style.display = "";
            visibleCount++;
        } else {
            item.style.display = "none";
        }
    });

    const noResultBox = document.getElementById("noResults");
    if (noResultBox) {
        noResultBox.style.display = (visibleCount === 0) ? "block" : "none";
    }
}

function newChat() {
    conversationId = null;
    localStorage.removeItem("chat_conversation_id");
    document.getElementById("chatBox").innerHTML = "";

    if (window.innerWidth <= 992) {
        document.getElementById("sidebarPanel").classList.remove('show');
        document.getElementById('overlay').classList.remove('show');
    }

    loadConversationList();
}
function enableSingleDeleteMode() {
    singleDeleteMode = true;
}


function deleteCurrentChat() {
    if (!conversationId) {
        showMessage("No chat selected to delete");
        return;
    }
    deleteConversation(conversationId);
}


document.addEventListener("click", function (event) {
    if (!singleDeleteMode) return;

    const msgDiv = event.target.closest(".msg");
    if (!msgDiv) return;

    const messageId = msgDiv.getAttribute("data-id");
    if (!messageId) {
        singleDeleteMode = false;
        return;
    }

    // Store message waiting to delete
    messageToDelete = { id: messageId, element: msgDiv };

    // Show modal
    document.getElementById("singleDeleteModal").style.display = "flex";

    singleDeleteMode = false;
});

async function confirmSingleDelete() {
    if (!messageToDelete) return;

    const { id, element } = messageToDelete;

     window.speechSynthesis.cancel();

    await fetch(`/api/delete-message/${id}/`, {
        method: "POST",
        headers: { "X-CSRFToken": getCookie("csrftoken") }
    });

    element.remove();

    loadConversationList();

    messageToDelete = null;

    document.getElementById("singleDeleteModal").style.display = "none";
}

function cancelSingleDelete() {
    messageToDelete = null;
    document.getElementById("singleDeleteModal").style.display = "none";
}


let recognition;
let isListening = false;

if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;

    recognition.onresult = function (event) {
        const spokenText = event.results[0][0].transcript;
        document.getElementById("messageInput").value = spokenText;
        sendMessage();
    };

    recognition.onerror = function (e) {
        console.log("Speech recognition error:", e);
        isListening = false;
        updateMicUI();
    };

    recognition.onend = function () {
        isListening = false;
        updateMicUI();
    };
}

document.getElementById("micBtn").addEventListener("click", () => {
    if (!recognition) {
        alert("Your browser does not support Speech Recognition.");
        return;
    }

    if (!isListening) {
        recognition.start();
        isListening = true;
    } else {
        recognition.stop();
        isListening = false;
    }

    updateMicUI();
});

function updateMicUI() {
    const micBtn = document.getElementById("micBtn");
    if (isListening) {
        micBtn.style.backgroundColor = "#ff3b3b";
        micBtn.innerText = "🎙 Listening...";
    } else {
        micBtn.style.backgroundColor = "";
        micBtn.innerText = "🎤";
    }
}

window.addEventListener("DOMContentLoaded", () => {

    document.getElementById("attachBtn").addEventListener("click", () => {
        document.getElementById("fileInput").click();
    });

    document.getElementById("fileInput").addEventListener("change", async function () {
        const file = this.files[0];
        if (!file) return;

        let icon = "📎";
        if (file.type.startsWith("image/")) icon = "🖼️";
        if (file.type.startsWith("video/")) icon = "🎬";
        if (file.type.startsWith("audio/")) icon = "🎵";
        if (file.type.includes("pdf")) icon = "📄";
        if (file.type.includes("zip") || file.type.includes("rar")) icon = "🗂️";

        if (!file.type.startsWith("image/")) {
            addMessage(`${icon} ${file.name}`, "user");
        }

        let formData = new FormData();
        formData.append("file", file);
        formData.append("conversation_id", conversationId || "");

        const resp = await fetch("/api/upload-file/", {
            method: "POST",
            headers: { "X-CSRFToken": getCookie("csrftoken") },
            body: formData
        });

        const data = await resp.json();

        if (data.image_html) {
            addMessage(data.image_html, "user", data.message_id);
        }
        addMessage(data.response, "bot", data.bot_message_id || data.message_id);

        loadConversationList();
    });


    const langSelect = document.getElementById("langSelect");
    if (langSelect) {
        langSelect.addEventListener("change", () => {
            const lang = getLang();
            localStorage.setItem("chat_lang", lang);

            loadConversationList();

            if (conversationId) {
                loadConversation(conversationId);
            }
        });
    }

});

let voiceEnabled = true;  
const voiceBtn = document.getElementById("voiceToggleBtn");
const audioPlayer = document.getElementById("voicePlayer");

voiceBtn.addEventListener("click", () => {
    voiceEnabled = !voiceEnabled;

    if (!voiceEnabled) {
        window.speechSynthesis.cancel();  
        voiceBtn.textContent = "🔇";
    } else {
        voiceBtn.textContent = "🔊";
    }
});
