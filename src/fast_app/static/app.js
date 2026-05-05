const ws = null;
let statusCheckInterval = null;
let currentJobId = null;

const submissionForm = document.getElementById('submission-form');
const progressArea = document.getElementById('progress-area');
const questionModal = document.getElementById('question-modal');
const results = document.getElementById('results');
const errorBox = document.getElementById('error-box');

const submitBtn = document.getElementById('submit-btn');
const skipBtn = document.getElementById('skip-btn');
const submitAnswerBtn = document.getElementById('submit-answer-btn');
const retryBtn = document.getElementById('retry-btn');
const newJobBtn = document.getElementById('new-job-btn');
const cancelBtns = document.querySelectorAll('#cancel-btn');

const jobUrlInput = document.getElementById('job-url');
const jobDescriptionInput = document.getElementById('job-description');
const forceCheckbox = document.getElementById('force');
const debugCheckbox = document.getElementById('debug');
const overwriteCheckbox = document.getElementById('overwrite');
const skipQuestionsCheckbox = document.getElementById('skip-questions');
const skipCoverCheckbox = document.getElementById('skip-cover');

const progressFill = document.getElementById('progress-fill');
const statusText = document.getElementById('status-text');
const logOutput = document.getElementById('log-output');

const questionText = document.getElementById('question-text');
const qNum = document.getElementById('q-num');
const qTotal = document.getElementById('q-total');
const answerInput = document.getElementById('answer-input');

const resumeLink = document.getElementById('resume-link');
const coverLetterLink = document.getElementById('cover-letter-link');
const errorMessage = document.getElementById('error-message');
const errorTrace = document.getElementById('error-trace');

function updateSubmitButton() {
    const hasUrl = jobUrlInput.value.trim().length > 0;
    const hasDesc = jobDescriptionInput.value.trim().length > 0;
    submitBtn.disabled = !(hasUrl || hasDesc);
}

jobUrlInput.addEventListener('input', updateSubmitButton);
jobDescriptionInput.addEventListener('input', updateSubmitButton);
updateSubmitButton();

let activeWs = null;

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    activeWs = new WebSocket(wsUrl);

    activeWs.onopen = () => {
        console.log('WebSocket connected');
    };

    activeWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleMessage(data);
    };

    activeWs.onclose = () => {
        console.log('WebSocket disconnected, reconnecting...');
        setTimeout(connectWebSocket, 1000);
    };

    activeWs.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

function handleMessage(data) {
    switch (data.type) {
        case 'log':
            appendLog(data.emoji, data.message, data.level);
            break;
        case 'state_change':
            handleStateChange(data.new_state);
            break;
        case 'progress':
            updateProgress(data.step, data.value);
            break;
        case 'complete':
            showResults(data.resume_url, data.cover_letter_url);
            break;
        case 'error':
            showError(data.message, data.traceback);
            break;
        case 'pong':
            break;
    }
}

async function checkInitialState() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();

        if (status.state === 'processing' || status.state === 'waiting_questions') {
            currentJobId = status.job_id;
            showProgress();
            startStatusPolling();

            if (status.state === 'waiting_questions') {
                showQuestion();
            }
        } else if (status.state === 'complete') {
            showResults(status.resume_url, status.cover_letter_url);
        } else if (status.state === 'error') {
            showError(status.error);
        }
    } catch (error) {
        console.error('Failed to check initial state:', error);
    }
}

submitBtn.addEventListener('click', async () => {
    const url = jobUrlInput.value.trim();
    const description = jobDescriptionInput.value.trim();

    if (!url && !description) {
        alert('Please enter a job URL or paste a job description.');
        return;
    }

    const flags = {
        force: forceCheckbox.checked,
        debug: debugCheckbox.checked,
        overwrite_resume: overwriteCheckbox.checked,
        skip_questions: skipQuestionsCheckbox.checked,
        skip_cover_letter: skipCoverCheckbox.checked
    };

    let payload;
    if (description) {
        const firstLine = description.split('\n').find(l => l.trim()) || '';
        const title = firstLine.length > 100
            ? firstLine.substring(0, 97) + '...'
            : firstLine;
        payload = {
            title,
            content: description,
            job_url: url || undefined,
            flags
        };
    } else {
        payload = { url, flags };
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Starting...';

    try {
        const response = await fetch('/api/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to start job');
        }

        currentJobId = data.job_id;
        showProgress();
        startStatusPolling();
    } catch (error) {
        alert(`Error: ${error.message}`);
        submitBtn.disabled = false;
        submitBtn.textContent = 'Generate Resume';
        updateSubmitButton();
    }
});

function startStatusPolling() {
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
    }

    statusCheckInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/status');
            const status = await response.json();

            updateProgress(status.current_step, status.progress);

            if (status.state === 'waiting_questions') {
                showQuestion();
            } else if (status.state === 'complete') {
                showResults(status.resume_url, status.cover_letter_url);
                stopStatusPolling();
            } else if (status.state === 'error') {
                showError(status.error);
                stopStatusPolling();
            }
        } catch (error) {
            console.error('Status poll failed:', error);
        }
    }, 1000);
}

function stopStatusPolling() {
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
        statusCheckInterval = null;
    }
}

function showProgress() {
    submissionForm.hidden = true;
    progressArea.hidden = false;
    results.hidden = true;
    errorBox.hidden = true;
    logOutput.innerHTML = '';
}

function updateProgress(step, progress) {
    statusText.textContent = step;
    progressFill.style.width = `${progress * 100}%`;
}

function appendLog(emoji, message, level) {
    const logLine = document.createElement('div');
    logLine.className = `log-line ${level}`;
    logLine.textContent = `${emoji} ${message}`;
    logOutput.appendChild(logLine);
    logOutput.scrollTop = logOutput.scrollHeight;
}

function handleStateChange(newState) {
    console.log('State changed to:', newState);
}

async function showQuestion() {
    try {
        const response = await fetch('/api/question');
        const data = await response.json();

        if (data.error) {
            console.error('Failed to get question:', data.error);
            return;
        }

        stopStatusPolling();

        qNum.textContent = data.index + 1;
        qTotal.textContent = data.total;
        questionText.textContent = data.question;
        answerInput.value = '';
        questionModal.hidden = false;
        answerInput.focus();
    } catch (error) {
        console.error('Failed to show question:', error);
    }
}

submitAnswerBtn.addEventListener('click', async () => {
    const answer = answerInput.value.trim();

    try {
        const response = await fetch('/api/answer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_id: currentJobId,
                question_index: parseInt(qNum.textContent) - 1,
                answer
            })
        });

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        if (data.next_state === 'processing') {
            questionModal.hidden = true;
            showProgress();
            startStatusPolling();
        } else {
            questionModal.hidden = true;
            startStatusPolling();
        }
    } catch (error) {
        alert(`Error submitting answer: ${error.message}`);
    }
});

skipBtn.addEventListener('click', async () => {
    answerInput.value = '';
    submitAnswerBtn.click();
});

function showResults(resumeUrl, coverLetterUrl) {
    stopStatusPolling();

    submissionForm.hidden = true;
    progressArea.hidden = true;
    questionModal.hidden = true;
    errorBox.hidden = true;
    results.hidden = false;

    resumeLink.href = resumeUrl;

    if (coverLetterUrl) {
        coverLetterLink.href = coverLetterUrl;
        coverLetterLink.hidden = false;
    } else {
        coverLetterLink.hidden = true;
    }
}

function showError(message, traceback = null) {
    stopStatusPolling();

    submissionForm.hidden = true;
    progressArea.hidden = true;
    questionModal.hidden = true;
    results.hidden = true;
    errorBox.hidden = false;

    errorMessage.textContent = message;

    if (traceback) {
        errorTrace.textContent = traceback;
        errorTrace.hidden = false;
    } else {
        errorTrace.hidden = true;
    }

    submitBtn.disabled = false;
    submitBtn.textContent = 'Generate Resume';
    updateSubmitButton();
}

retryBtn.addEventListener('click', () => {
    errorBox.hidden = true;
    submissionForm.hidden = false;
    submitBtn.disabled = false;
    submitBtn.textContent = 'Generate Resume';
    updateSubmitButton();
});

newJobBtn.addEventListener('click', async () => {
    try {
        await fetch('/api/reset', { method: 'POST' });
        location.reload();
    } catch (error) {
        console.error('Failed to reset:', error);
    }
});

cancelBtns.forEach(btn => {
    btn.addEventListener('click', async () => {
        if (!confirm('Are you sure you want to cancel? This will return to the main menu and clear the current job.')) {
            return;
        }

        try {
            stopStatusPolling();

            await fetch('/api/reset', { method: 'POST' });

            submissionForm.hidden = false;
            progressArea.hidden = true;
            questionModal.hidden = true;
            results.hidden = true;
            errorBox.hidden = true;

            submitBtn.disabled = false;
            submitBtn.textContent = 'Generate Resume';
            logOutput.innerHTML = '';
            answerInput.value = '';
            jobUrlInput.value = '';
            jobDescriptionInput.value = '';
            updateSubmitButton();
        } catch (error) {
            console.error('Failed to cancel:', error);
            alert('Failed to cancel. Please try refreshing the page.');
        }
    });
});

answerInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submitAnswerBtn.click();
    }
});

document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    checkInitialState();
    updateSubmitButton();
});