
function playDemo(targetId, messages) {
    const box = document.getElementById(targetId);
    box.innerHTML = ""; // clear previous

    messages.forEach((msg, index) => {
        setTimeout(() => {
            const div = document.createElement("div");
            div.className = "demo-msg";
            div.innerText = msg;
            box.appendChild(div);
        }, index * 900);
    });
}

// DEMO CONTENT (three different sets)
const demo1 = [
    "Hello! 👋 Need help today?",
    "I'm here to support you.",
    "Ask me anything about your account."
];

const demo2 = [
    "Hi! 🤖 I'm your AI assistant.",
    "I can help you write, learn, or explore ideas.",
    "Tell me what you’d like to do!"
];

const demo3 = [
    "Welcome! 💼 Looking for product info?",
    "I can show pricing, features, and comparisons.",
    "Ready to explore our catalog?"
];

// Play animations automatically when page loads
window.onload = function() {
    playDemo("demo1", demo1);
    playDemo("demo2", demo2);
    playDemo("demo3", demo3);

    // Optional: replay every 8 seconds
    setInterval(() => {
        playDemo("demo1", demo1);
        playDemo("demo2", demo2);
        playDemo("demo3", demo3);
    }, 8000);
};

