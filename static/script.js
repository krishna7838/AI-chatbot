let currentChat = null;

// Load all sessions
async function loadSessions() {
    const res = await fetch("/sessions");
    const chats = await res.json();
    const list = document.getElementById("session-list");
    list.innerHTML = "";

    chats.forEach(c => {
        const li = document.createElement("li");
        li.setAttribute("data-id", c.session_id);
        li.style.display = "flex";
        li.style.justifyContent = "space-between";
        li.style.alignItems = "center"; // align icon vertically
        li.style.padding = "5px 0";

        const span = document.createElement("span");
        span.style.cursor = "pointer";
        span.innerText = `${c.description} (${c.mode})`;
        span.onclick = () => selectChat(c.session_id);

        const btn = document.createElement("button");
        btn.className = "delete-btn";
        btn.innerHTML = '<i class="fa-solid fa-trash"></i>'; // recycle bin icon
        btn.style.width = "40px"; // fixed width
        btn.onclick = () => deleteChat(c.session_id);

        li.appendChild(span);
        li.appendChild(btn);
        list.appendChild(li);
    });
}

// Load uploaded documents
async function loadDocuments(sessionId) {
    if (!sessionId) return;

    const res = await fetch("/documents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId })
    });
    const docs = await res.json();

    const docSection = document.getElementById("document-list");
    const docList = document.getElementById("docs");
    docList.innerHTML = "";

    if (docs.length > 0) {
        docSection.style.display = "block";
        docs.forEach(d => {
            const li = document.createElement("li");
            li.style.display = "flex";
            li.style.justifyContent = "space-between";
            li.style.alignItems = "center";
            li.style.padding = "3px 0";

            const fileSpan = document.createElement("span");
            fileSpan.innerText = d.filename;

            const delBtn = document.createElement("button");
            delBtn.className = "delete-btn";
            delBtn.innerHTML = '<i class="fa-solid fa-trash"></i>'; // recycle bin icon
            delBtn.style.width = "40px";
            delBtn.onclick = async () => {
                await fetch(`/delete_document/${d.file_id}`, { method: "DELETE" });
                loadDocuments(sessionId);
            };

            li.appendChild(fileSpan);
            li.appendChild(delBtn);
            docList.appendChild(li);
        });
    } else {
        
        docList.innerHTML = "<li>No documents uploaded yet.</li>";
    }
}

// Upload documents
document.getElementById("upload-btn").onclick = async () => {
    const files = document.getElementById("file-input").files;
    if (!files.length || !currentChat) return alert("Select chat and files!");

    const formData = new FormData();
    formData.append("session_id", currentChat);
    for (let f of files) formData.append("files", f);

    const res = await fetch("/upload", { method: "POST", body: formData });
    const data = await res.json();

    document.getElementById("upload-status").innerText =
        data.files && data.files.length > 0
            ? "✅ Uploaded: " + data.files.map(f => f.filename).join(", ")
            : "No files uploaded.";

    await loadDocuments(currentChat);
    document.getElementById("file-input").value = "";
};

// Start new chat
async function startChat() {
    const description = prompt("Enter chat description:");
    if (!description) return;

    const res = await fetch("/start_session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description, mode: "2" })
    });

    const data = await res.json();
    currentChat = data.session_id;
    document.getElementById("upload-section").style.display = "block";
    loadSessions();
}

// Select a chat
async function selectChat(id) {
    currentChat = id;

    // Highlight selected chat
    document.querySelectorAll("#session-list li").forEach(li => li.style.backgroundColor = "");
    const selected = document.querySelector(`#session-list li[data-id='${id}']`);
    if (selected) selected.style.backgroundColor = "lightblue";

    document.getElementById("upload-section").scrollIntoView({ behavior: "smooth" });

    // Load history
    const chatWindow = document.getElementById("chat-window");
    chatWindow.innerHTML = "";
    const res = await fetch("/history", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: id })
    });
    const history = await res.json();

    history.forEach(h => {
        appendMessage(h.question, "user");
        appendMessage(h.answer, "bot");
    });
    document.getElementById("upload-section").style.display = "block";
    //auto scroller
    chatWindow.scrollTop = chatWindow.scrollHeight;

    // Load documents
    await loadDocuments(id);
}

// Send message
async function sendMessage() {
    const input = document.getElementById("message");
    const text = input.value;
    if (!text || !currentChat) return alert("Select a chat first!");

    appendMessage(text, "user");
    input.value = "";

    const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: currentChat, message: text })
    });
    const data = await res.json();

    appendMessage(data.bot, "bot");
}

// Append messages to chat window
function appendMessage(message, sender = "bot") {
    const chatWindow = document.getElementById("chat-window");

    const msgDiv = document.createElement("div");
    msgDiv.classList.add("chat-message");

    if (sender === "user") msgDiv.classList.add("user-message-bubble");
    else msgDiv.classList.add("bot-message-bubble");

    msgDiv.textContent = message;
    chatWindow.appendChild(msgDiv);

    chatWindow.scrollTop = chatWindow.scrollHeight;
}

// Delete chat
async function deleteChat(id) {
    if (!confirm("Are you sure you want to delete this chat?")) return;
    await fetch(`/delete_session/${id}`, { method: "DELETE" });

    if (currentChat === id) {
        currentChat = null;
        document.getElementById("chat-window").innerHTML = "";
        document.getElementById("upload-section").style.display = "none";
        document.getElementById("document-list").style.display = "none";
    }

    loadSessions();
}

// Switch mode
// async function switchMode(mode) {
//     if (!currentChat) return alert("Select a chat first!");
//     await fetch("/switch_mode", {
//         method: "POST",
//         headers: { "Content-Type": "application/json" },
//         body: JSON.stringify({ session_id: currentChat, mode })
//     });
// }

async function switchMode(mode) {
    if (!currentChat) return alert("Select a chat first!");
    const res = await fetch("/switch_mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: currentChat, mode })
    });
    const data = await res.json();
    // Update the span for current chat
    const li = document.querySelector(`#session-list li[data-id='${currentChat}'] span`);
    if (li) li.innerText = `${li.innerText.split('(')[0].trim()} (${data.new_mode})`;
}


// Initialize
window.onload = loadSessions;
