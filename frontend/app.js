const form = document.getElementById("cut-form");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const resultVideo = document.getElementById("result-video");
const downloadLink = document.getElementById("download-link");
const clipsField = document.getElementById("clips-field");
const aiFields = document.getElementById("ai-fields");
const modeRadios = document.querySelectorAll('input[name="mode"]');

function currentMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

function syncFieldsToMode() {
  const isAi = currentMode() === "ai";
  clipsField.classList.toggle("hidden", isAi);
  aiFields.classList.toggle("hidden", !isAi);
  document.getElementById("clips").required = !isAi;
}

modeRadios.forEach((radio) => radio.addEventListener("change", syncFieldsToMode));
syncFieldsToMode();

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const musicFile = document.getElementById("music").files[0];
  const isAi = currentMode() === "ai";

  if (!musicFile) {
    statusEl.textContent = "Choose a music file.";
    return;
  }

  const formData = new FormData();
  formData.append("music", musicFile);

  let endpoint;
  if (isAi) {
    const prompt = document.getElementById("prompt").value.trim();
    if (!prompt) {
      statusEl.textContent = "Enter a scene prompt.";
      return;
    }
    formData.append("prompt", prompt);
    formData.append("num_scenes", document.getElementById("num-scenes").value);
    endpoint = "/api/cut-ai";
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
  statusEl.textContent = isAi
    ? "Generating AI scenes and cutting to the beat... this can take a few minutes."
    : "Detecting beats and cutting clips... this can take a minute.";

  try {
    const res = await fetch(endpoint, { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Request failed (${res.status})`);
    }
    const data = await res.json();

    statusEl.textContent = `Done — ${data.num_beats} beats detected at ~${Math.round(data.tempo)} BPM.`;
    resultVideo.src = data.download_url;
    downloadLink.href = data.download_url;
    resultEl.classList.remove("hidden");
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  } finally {
    submitBtn.disabled = false;
  }
});
