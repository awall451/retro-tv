# Sleep timer (see docker/README.md, "Sleep timer"): the "idle" key of
# /config.json, {"timeoutMin": N, "promptSec": N}, from
#
#   IDLE_TIMEOUT_MIN=90   minutes without a key press before "Are you still
#                         watching?" (asked when the programme on then ends);
#                         0 or empty: never (the default)
#   IDLE_PROMPT_SEC=60    how long the question waits for a key before the
#                         viewer stops playing
#
# A bad value is ignored with a warning. Both left at their defaults: no key
# at all, and the app uses its own defaults. Sourced by ../config.envsh.

# A whole number in decimal, leading zeros dropped ("0090" -> "90", "0" stays
# "0"), so the shell's arithmetic never reads it as octal. Empty when it is
# not one, or has more than $2 digits.
_idle_num() {
  _idle_n=$1
  case $_idle_n in '' | *[!0-9]*) _idle_n=; return 0 ;; esac
  while :; do
    case $_idle_n in 0?*) _idle_n=${_idle_n#0} ;; *) break ;; esac
  done
  if [ "${#_idle_n}" -gt "$2" ]; then _idle_n=; fi
  return 0
}

_idle_num "${IDLE_TIMEOUT_MIN:-0}" 5
_idle_min=$_idle_n
if [ -z "$_idle_min" ]; then
  echo "idle: ignored IDLE_TIMEOUT_MIN \"${IDLE_TIMEOUT_MIN:-}\": not a whole number of minutes; the sleep timer is off" >&2
  _idle_min=0
fi
_idle_num "${IDLE_PROMPT_SEC:-60}" 4
_idle_sec=$_idle_n
if [ -z "$_idle_sec" ] || [ "$_idle_sec" -lt 5 ]; then
  echo "idle: ignored IDLE_PROMPT_SEC \"${IDLE_PROMPT_SEC:-}\": not a whole number of seconds (5 or more); using 60" >&2
  _idle_sec=60
fi
if [ "$_idle_min" -gt 0 ]; then
  echo "idle: asks \"Are you still watching?\" after ${_idle_min} min without input" >&2
fi
if [ "$_idle_min" -gt 0 ] || [ "$_idle_sec" -ne 60 ]; then
  config_set idle "{\"timeoutMin\": $_idle_min, \"promptSec\": $_idle_sec}"
fi
unset _idle_n _idle_min _idle_sec
unset -f _idle_num
