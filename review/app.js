(function () {
  "use strict";

  const voices = window.V2_VOICE_PREVIEW_CATALOG || [];
  const list = document.getElementById("voice-list");
  const status = document.getElementById("preview-status");
  const nowPlaying = document.getElementById("now-playing");
  const selectedVoice = document.getElementById("selected-voice");
  const audio = document.getElementById("preview-audio");
  const pauseButton = document.getElementById("pause-resume");
  const restartButton = document.getElementById("restart-preview");
  const stopButton = document.getElementById("stop-preview");
  let selectedVoiceId = null;

  function updateUi(snapshot) {
    document.querySelectorAll(".voice-row").forEach((row) => {
      row.classList.toggle("is-playing", snapshot.state === "playing" && row.dataset.voiceId === snapshot.activeVoiceId);
      row.classList.toggle("is-paused", snapshot.state === "paused" && row.dataset.voiceId === snapshot.activeVoiceId);
      const play = row.querySelector(".preview-button");
      play.textContent = row.classList.contains("is-playing") ? "■" : "▶";
      play.title = row.classList.contains("is-playing") ? "Parar prévia" : "Ouvir prévia";
      play.setAttribute("aria-label", `${play.title}: ${row.dataset.voiceId}`);
    });
    const hasActive = Boolean(snapshot.activeVoiceId);
    pauseButton.disabled = !hasActive;
    restartButton.disabled = !hasActive;
    stopButton.disabled = !hasActive;
    pauseButton.textContent = snapshot.state === "paused" ? "▶" : "⏸";
    pauseButton.title = snapshot.state === "paused" ? "Retomar" : "Pausar";
    nowPlaying.textContent = snapshot.activeVoiceId || "Nenhuma voz tocando";
    status.textContent = snapshot.message || "Escolha o botão de prévia ao lado de uma voz.";
    status.dataset.state = snapshot.state;
  }

  const controller = new window.VoicePreviewController(audio, updateUi);

  function renderVoice(voice) {
    const row = document.createElement("div");
    row.className = "voice-row";
    row.dataset.voiceId = voice.voice_id;

    const select = document.createElement("button");
    select.type = "button";
    select.className = "select-button";
    select.innerHTML = `<strong>${voice.voice_id}</strong><span>${voice.locale.replace("_", "-")} · grade ${voice.official_grade} · ${voice.duration_seconds.toFixed(2)} s</span>`;
    select.addEventListener("click", () => {
      selectedVoiceId = voice.voice_id;
      document.querySelectorAll(".voice-row").forEach((item) => item.classList.toggle("is-selected", item.dataset.voiceId === selectedVoiceId));
      selectedVoice.textContent = voice.voice_id;
      status.textContent = `${voice.voice_id} selecionada. A prévia não foi iniciada.`;
    });

    const preview = document.createElement("button");
    preview.type = "button";
    preview.className = "icon-button preview-button";
    preview.textContent = "▶";
    preview.title = "Ouvir prévia";
    preview.setAttribute("aria-label", `Ouvir prévia: ${voice.voice_id}`);
    preview.addEventListener("click", () => {
      if (controller.activeVoice && controller.activeVoice.voice_id === voice.voice_id) controller.stop();
      else controller.play(voice);
    });

    row.append(select, preview);
    list.appendChild(row);
  }

  voices.forEach(renderVoice);
  document.getElementById("voice-count").textContent = `${voices.length} vozes locais`;
  pauseButton.addEventListener("click", () => controller.pauseResume());
  restartButton.addEventListener("click", () => controller.restart());
  stopButton.addEventListener("click", () => controller.stop());
  document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => {
    document.querySelectorAll("[data-mode]").forEach((item) => item.classList.toggle("is-active", item === button));
    controller.stop("Modo alterado. A prévia foi parada.");
  }));
  window.addEventListener("vts:generation-start", () => controller.stop("Geração iniciada. A prévia foi parada."));
  window.addEventListener("vts:mode-change", () => controller.stop("Modo alterado. A prévia foi parada."));
  window.addEventListener("pagehide", () => controller.stop());
  window.addEventListener("beforeunload", () => controller.stop());
  window.v2Preview = { controller, voices, getSelectedVoiceId: () => selectedVoiceId };
  updateUi(controller.snapshot("Pronto. Ouvir uma prévia não seleciona a voz."));
})();

