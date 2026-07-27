(function () {
  "use strict";

  class VoicePreviewController {
    constructor(audio, onChange) {
      this.audio = audio;
      this.onChange = onChange || function () {};
      this.state = "idle";
      this.activeVoice = null;
      this.audio.preload = "none";
      this.audio.addEventListener("ended", () => this.stop("Prévia concluída."));
      this.audio.addEventListener("error", () => this.fail("Não foi possível abrir a prévia. Verifique o arquivo e o dispositivo de áudio."));
      this.audio.addEventListener("playing", () => this.setState("playing"));
      this.audio.addEventListener("pause", () => {
        if (this.state === "playing") this.setState("paused");
      });
    }

    snapshot(message) {
      return { state: this.state, activeVoiceId: this.activeVoice ? this.activeVoice.voice_id : null, message: message || "" };
    }

    setState(state, message) {
      this.state = state;
      this.onChange(this.snapshot(message));
    }

    async play(voice) {
      if (!voice || !voice.mp3_path) {
        this.fail("Esta voz não possui uma prévia local válida.");
        return;
      }
      if (this.activeVoice && this.activeVoice.voice_id !== voice.voice_id) this.stop();
      this.activeVoice = voice;
      if (this.audio.getAttribute("src") !== voice.mp3_path) {
        this.audio.src = voice.mp3_path;
        this.audio.load();
      }
      this.setState("loading", `Carregando ${voice.voice_id}...`);
      try {
        await this.audio.play();
        this.setState("playing", `Tocando ${voice.voice_id}.`);
      } catch (error) {
        this.fail("Não foi possível reproduzir a prévia. Verifique o dispositivo de áudio.");
      }
    }

    async pauseResume() {
      if (!this.activeVoice) return;
      if (this.state === "playing") {
        this.audio.pause();
        this.setState("paused", `Prévia de ${this.activeVoice.voice_id} pausada.`);
        return;
      }
      if (this.state === "paused") {
        try {
          await this.audio.play();
          this.setState("playing", `Tocando ${this.activeVoice.voice_id}.`);
        } catch (error) {
          this.fail("Não foi possível retomar a prévia.");
        }
      }
    }

    async restart() {
      if (!this.activeVoice) return;
      this.audio.currentTime = 0;
      try {
        await this.audio.play();
        this.setState("playing", `Reiniciando ${this.activeVoice.voice_id}.`);
      } catch (error) {
        this.fail("Não foi possível reiniciar a prévia.");
      }
    }

    stop(message) {
      this.audio.pause();
      try { this.audio.currentTime = 0; } catch (error) {}
      this.audio.removeAttribute("src");
      this.audio.load();
      this.activeVoice = null;
      this.setState("idle", message || "Prévia parada.");
    }

    fail(message) {
      this.audio.pause();
      this.activeVoice = null;
      this.setState("error", message);
    }
  }

  window.VoicePreviewController = VoicePreviewController;
})();

