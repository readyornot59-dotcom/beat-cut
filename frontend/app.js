const form = document.getElementById("cut-form");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const resultVideo = document.getElementById("result-video");
const downloadLink = document.getElementById("download-link");
const clipsField = document.getElementById("clips-field");
const aiFields = document.getElementById("ai-fields");
const visualizerFields = document.getElementById("visualizer-fields");
const modeRadios = document.querySelectorAll('input[name="mode"]');
const progressEl = document.getElementById("progress");
const progressStageEl = document.getElementById("progress-stage");
const progressTimerEl = document.getElementById("progress-timer");
const progressBarFillEl = document.getElementById("progress-bar-fill");

const STAGE_LABELS = {
  starting: "Starting...",
  detecting_beats: "Detecting beats...",
  submitting_scenes: "Submitting scene requests...",
  generating_scenes: "Generating AI scenes",
  rendering_styles: "Rendering visual styles",
  cutting_segments: "Cutting segments to the beat",
  concatenating: "Combining segments...",
  muxing_audio: "Adding audio track...",
  done: "Done",
};

let pollHandle = null;
let timerHandle = null;
let startTime = null;

function currentMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

function syncFieldsToMode() {
  const mode = currentMode();
  clipsField.classList.toggle("hidden", mode !== "upload");
  aiFields.classList.toggle("hidden", mode !== "ai");
  visualizerFields.classList.toggle("hidden", mode !== "visualizer");
  document.getElementById("clips").required = mode === "upload";
}

modeRadios.forEach((radio) => radio.addEventListener("change", syncFieldsToMode));
syncFieldsToMode();

function formatElapsed(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function updateProgressDisplay(job) {
  const label = STAGE_LABELS[job.stage] || job.stage;
  if (job.total > 0) {
    progressStageEl.textContent = `${label} (${job.current}/${job.total})`;
    progressBarFillEl.classList.remove("indeterminate");
    progressBarFillEl.style.width = `${Math.round((job.current / job.total) * 100)}%`;
  } else {
    progressStageEl.textContent = label;
    progressBarFillEl.classList.add("indeterminate");
  }
}

function stopTracking() {
  if (pollHandle) clearInterval(pollHandle);
  if (timerHandle) clearInterval(timerHandle);
  pollHandle = null;
  timerHandle = null;
}

function trackJob(jobId) {
  startTime = Date.now();
  progressEl.classList.remove("hidden");
  progressTimerEl.textContent = "0:00";
  progressBarFillEl.style.width = "0%";
  progressBarFillEl.classList.add("indeterminate");
  progressStageEl.textContent = STAGE_LABELS.starting;

  timerHandle = setInterval(() => {
    progressTimerEl.textContent = formatElapsed(Date.now() - startTime);
  }, 1000);

  pollHandle = setInterval(async () => {
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) return;
      const job = await res.json();

      if (job.status === "running") {
        updateProgressDisplay(job);
        return;
      }

      stopTracking();
      progressEl.classList.add("hidden");
      submitBtn.disabled = false;

      if (job.status === "done") {
        statusEl.textContent = `Done — ${job.num_beats} beats detected at ~${Math.round(job.tempo)} BPM.`;
        resultVideo.src = job.download_url;
        downloadLink.href = job.download_url;
        resultEl.classList.remove("hidden");
      } else {
        statusEl.textContent = `Error: ${job.detail || "job failed"}`;
      }
    } catch (err) {
      stopTracking();
      progressEl.classList.add("hidden");
      submitBtn.disabled = false;
      statusEl.textContent = `Error: ${err.message}`;
    }
  }, 1000);
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const musicFile = document.getElementById("music").files[0];
  const mode = currentMode();

  if (!musicFile) {
    statusEl.textContent = "Choose a music file.";
    return;
  }

  const formData = new FormData();
  formData.append("music", musicFile);

  let endpoint;
  if (mode === "ai") {
    const prompt = document.getElementById("prompt").value.trim();
    if (!prompt) {
      statusEl.textContent = "Enter a scene prompt.";
      return;
    }
    formData.append("prompt", prompt);
    formData.append("num_scenes", document.getElementById("num-scenes").value);
    endpoint = "/api/cut-ai";
  } else if (mode === "visualizer") {
    formData.append("num_styles", document.getElementById("num-styles").value);
    endpoint = "/api/cut-visualizer";
  } else {
    const clipFiles = document.getElementById("clips").files;
    if (clipFiles.length === 0) {
      statusEl.textContent = "Choose at least one video clip.";
      return;
    }
    for (const clip of clipFiles) {
      formData.append("clips", clip);
    }
    endpoint = "/api/cut";
  }

  submitBtn.disabled = true;
  resultEl.classList.add("hidden");
  statusEl.textContent = "";

  try {
    const res = await fetch(endpoint, { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed (${res.status})`);
    }
    const data = await res.json();
    trackJob(data.job_id);
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
    submitBtn.disabled = false;
  }
});
