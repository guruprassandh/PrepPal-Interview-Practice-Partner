// Voice recognition and synthesis
let recognition = null;
let isRecording = false;
let speechSynthesis = window.speechSynthesis;

function initializeVoice() {
    // Check if Web Speech API is available
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';

        recognition.onstart = () => {
            isRecording = true;
            const voiceBtn = document.getElementById('voiceBtn');
            const voiceStatus = document.getElementById('voiceStatus');
            
            voiceBtn.classList.add('recording');
            voiceBtn.textContent = '🔴 Recording...';
            voiceStatus.textContent = 'Listening...';
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            document.getElementById('answerInput').value = transcript;
            
            const voiceStatus = document.getElementById('voiceStatus');
            voiceStatus.textContent = 'Got it!';
            
            setTimeout(() => {
                voiceStatus.textContent = '';
            }, 2000);
        };

        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            const voiceStatus = document.getElementById('voiceStatus');
            
            if (event.error === 'no-speech') {
                voiceStatus.textContent = 'No speech detected. Try again.';
            } else if (event.error === 'not-allowed') {
                voiceStatus.textContent = 'Microphone access denied.';
            } else {
                voiceStatus.textContent = `Error: ${event.error}`;
            }
            
            resetVoiceButton();
        };

        recognition.onend = () => {
            resetVoiceButton();
        };

        // Setup voice button
        const voiceBtn = document.getElementById('voiceBtn');
        voiceBtn.addEventListener('click', toggleRecording);
        voiceBtn.disabled = false;
    } else {
        // Voice not supported
        const voiceBtn = document.getElementById('voiceBtn');
        voiceBtn.textContent = '🎤 Voice Not Supported';
        voiceBtn.disabled = true;
        
        const voiceStatus = document.getElementById('voiceStatus');
        voiceStatus.textContent = 'Web Speech API not available in this browser';
    }
}

function toggleRecording() {
    if (!recognition) return;

    if (isRecording) {
        recognition.stop();
    } else {
        recognition.start();
    }
}

function resetVoiceButton() {
    isRecording = false;
    const voiceBtn = document.getElementById('voiceBtn');
    voiceBtn.classList.remove('recording');
    voiceBtn.textContent = '🎤 Voice Answer';
}

function speakText(text) {
    // Stop any ongoing speech
    speechSynthesis.cancel();
    
    // Create utterance
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-US';
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    
    // Find a good voice (prefer English voices)
    const voices = speechSynthesis.getVoices();
    const englishVoice = voices.find(voice => voice.lang.startsWith('en'));
    if (englishVoice) {
        utterance.voice = englishVoice;
    }
    
    speechSynthesis.speak(utterance);
}

// Load voices (they load asynchronously)
if (speechSynthesis) {
    speechSynthesis.onvoiceschanged = () => {
        speechSynthesis.getVoices();
    };
}