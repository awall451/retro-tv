// Sleep timer: "Are you still watching?"
//
// Every channel is a live transcode on the server, and a television left on
// all night keeps one running. So after IDLE_TIMEOUT_MIN minutes without a
// key, remote, controller, mouse or touch, the viewer asks; nobody answers,
// and it stops.
//
// It never cuts into a programme: once the time is up, it waits for the end
// of what is on (the listing's stop time, given by the app as boundary()),
// then shows the question with a countdown. A key keeps watching. No key:
// the stream is stopped (the server ends its transcode once the player stops
// asking for segments) and a dim standby screen stays up until a key resumes
// the same channel. A listing that runs more than three hours on, or no
// listing at all, gets the question at once.
//
// The server sets the time in /idle.json (IDLE_TIMEOUT_MIN, 0 = off; the
// countdown IDLE_PROMPT_SEC); each device can override it in Settings. For
// trying it out: ?idle=<minutes> (fractions allowed) and ?idleprompt=<seconds>.

const CONFIG_URL = '/idle.json';
export const CAP_MS = 3 * 60 * 60 * 1000;   // a boundary further away than this is not waited for
const DEFAULT_PROMPT_S = 60;
const DRIFT_MS = 60 * 1000;                 // the standby card moves this often (no burn-in)

// {timeoutMin, promptSec} from the server; off when it says nothing.
export async function loadIdleConfig() {
  try {
    const res = await fetch(CONFIG_URL, { cache: 'no-store' });
    if (!res.ok) return { timeoutMin: 0, promptSec: DEFAULT_PROMPT_S };
    const cfg = await res.json();
    return {
      timeoutMin: Number.isFinite(cfg.timeoutMin) && cfg.timeoutMin > 0 ? cfg.timeoutMin : 0,
      promptSec: Number.isFinite(cfg.promptSec) && cfg.promptSec > 0 ? cfg.promptSec : DEFAULT_PROMPT_S,
    };
  } catch {
    return { timeoutMin: 0, promptSec: DEFAULT_PROMPT_S };
  }
}

// When to ask, for a viewer idle since idleAt with the programme on then
// ending at `end` (ms, or NaN/null when unknown): at the end, if it is
// still ahead and within CAP_MS; otherwise at once.
export function promptTime(idleAt, end, cap = CAP_MS) {
  return Number.isFinite(end) && end > idleAt && end - idleAt <= cap ? end : idleAt;
}

const clockFmt = new Intl.DateTimeFormat([], { hour: 'numeric', minute: '2-digit' });

export class Idle {
  // playing(): something is streaming (or showing) that the timer should stop.
  // boundary(t): when the programme on at instant t ends (ms), or NaN.
  // stop(reason): stop all playback ('idle', 'hidden', 'tv-off').
  // resume(): start the channel again (a key on the standby screen).
  constructor({ playing, boundary, stop, resume }) {
    Object.assign(this, { playing, boundary, stopFn: stop, resumeFn: resume });
    this.timeoutMs = 0;
    this.promptMs = DEFAULT_PROMPT_S * 1000;
    this.last = Date.now();         // the last input
    this.state = 'watching';        // watching | waiting | prompt | standby
    this.promptAt = 0;              // waiting: when the question goes up
    this.promptEnd = 0;             // prompt: when the countdown runs out
    this.reason = '';               // standby: why ('idle', 'hidden', 'tv-off')
    this.#build();
    setInterval(() => this.tick(), 1000);
  }

  #build() {
    const box = this.box = document.createElement('div');
    box.id = 'idle';
    box.hidden = true;
    box.innerHTML = '<div id="idleAsk"><div class="idleBar"></div>'
      + '<div class="idleQ">Are you still watching?</div>'
      + '<div class="idleCount"><span id="idleSecs"></span></div>'
      + '<div class="idleHint">Press any key</div><div class="idleBar"></div></div>'
      + '<div id="idleStandby"><div class="idleCard">'
      + '<div class="idleWord">Standby</div><div id="idleClock"></div>'
      + '<div class="idleHint">Press any key to resume</div></div></div>';
    document.body.append(box);
    this.ask = box.querySelector('#idleAsk');
    this.secs = box.querySelector('#idleSecs');
    this.standbyBox = box.querySelector('#idleStandby');
    this.card = box.querySelector('.idleCard');
    this.clock = box.querySelector('#idleClock');
    this.driftAt = 0;
    this.ask.hidden = this.standbyBox.hidden = true;
  }

  // The sleep time in minutes (0 = off) and the countdown in seconds.
  configure(timeoutMin, promptSec) {
    this.timeoutMs = Math.max(0, timeoutMin) * 60000;
    if (promptSec > 0) this.promptMs = promptSec * 1000;
    if (!this.timeoutMs && (this.state === 'waiting' || this.state === 'prompt')) this.#show('watching');
  }

  // Any key, button, click or touch. True when it was used up here (it
  // answered the question or woke the standby screen) and must not also
  // steer the viewer.
  input() {
    this.last = Date.now();
    switch (this.state) {
      case 'prompt':
        this.#show('watching');
        return true;
      case 'standby':
        this.#show('watching');
        this.resumeFn();
        return true;
      case 'waiting':
        this.state = 'watching';
        return false;
    }
    return false;
  }

  // A mouse moved: someone is there, but a bumped mouse alone does not
  // wake the standby screen (a key or a click does).
  nudge() {
    if (this.state !== 'standby') this.input();
  }

  // Stop now, without asking (a hidden tab, the TV switched off).
  standby(reason) {
    if (this.state === 'standby') return;
    this.reason = reason;
    this.stopFn(reason);
    this.#show('standby');
  }

  get asleep() { return this.state === 'standby'; }

  tick(now = Date.now()) {
    switch (this.state) {
      case 'watching': {
        if (!this.timeoutMs || !this.playing() || now - this.last < this.timeoutMs) return;
        const idleAt = this.last + this.timeoutMs;
        this.promptAt = promptTime(idleAt, this.boundary(idleAt));
        this.state = 'waiting';
        return this.tick(now);
      }
      case 'waiting':
        if (!this.playing()) { this.state = 'watching'; return; }
        if (now < this.promptAt) return;
        this.promptEnd = now + this.promptMs;
        this.#show('prompt');
        return this.#count(now);
      case 'prompt':
        if (now >= this.promptEnd) return this.standby('idle');
        return this.#count(now);
      case 'standby':
        return this.#clock(now);
    }
  }

  #count(now) {
    this.secs.textContent = String(Math.max(0, Math.ceil((this.promptEnd - now) / 1000)));
  }

  #clock(now) {
    this.clock.textContent = clockFmt.format(now);
    if (now - this.driftAt < DRIFT_MS) return;
    // Wander a little, so nothing sits on one spot of the tube all night.
    this.driftAt = now;
    this.card.style.left = `${25 + Math.random() * 50}%`;
    this.card.style.top = `${25 + Math.random() * 50}%`;
  }

  #show(state) {
    this.state = state;
    this.box.hidden = state !== 'prompt' && state !== 'standby';
    this.ask.hidden = state !== 'prompt';
    this.standbyBox.hidden = state !== 'standby';
    document.body.classList.toggle('asleep', state === 'standby');
    if (state === 'standby') { this.driftAt = 0; this.#clock(Date.now()); }
  }
}
