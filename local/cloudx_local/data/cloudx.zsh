# Cloudx minimal shell integration.
# `codex` is deliberately left as the official executable.

unset -f codex 2>/dev/null || true
if [ -n "${CODEXX_USER_HOME:-}" ]; then
  export HOME="$CODEXX_USER_HOME"
fi

# Cloudx selection changes CODEX_HOME only; discard codex-plus account shims.
if [ -n "${ZSH_VERSION:-}" ]; then
  typeset -a __cloudx_kept_path
  __cloudx_kept_path=()
  __cloudx_accounts_root="$HOME/.codex-accounts"
  for __cloudx_path_entry in "${path[@]}"; do
    case "$__cloudx_path_entry" in
      "$__cloudx_accounts_root"/*/.local/bin) ;;
      *) __cloudx_kept_path+=("$__cloudx_path_entry") ;;
    esac
  done
  path=("${__cloudx_kept_path[@]}")
  export PATH
  unset __cloudx_kept_path __cloudx_accounts_root __cloudx_path_entry
fi

unset OPENAI_API_KEY OPENAI_BASE_URL OPENAI_API_BASE

__cloudx_account_badge() {
  local account="${CODEXX_ACTIVE_ACCOUNT:-}"
  if [ -n "$account" ] && [ "$account" != "native" ]; then
    printf '[cx:%s]' "$account"
  fi
}

__cloudx_prompt_segment() {
  if [ -z "${ZSH_VERSION:-}" ]; then
    return 0
  fi
  local badge
  badge="$(__cloudx_account_badge)"
  if [ -n "$badge" ]; then
    printf ' %s' "$badge"
  fi
}

__cloudx_strip_prompt_suffix() {
  local prompt="$1"
  local suffix="$2"
  local prompt_len suffix_len trim_start tail
  suffix_len=${#suffix}
  if [ "$suffix_len" -eq 0 ]; then
    printf '%s' "$prompt"
    return 0
  fi
  prompt_len=${#prompt}
  if [ "$prompt_len" -lt "$suffix_len" ]; then
    printf '%s' "$prompt"
    return 0
  fi
  trim_start=$((prompt_len - suffix_len))
  tail="${prompt:$trim_start}"
  if [ "$tail" = "$suffix" ]; then
    printf '%s' "${prompt:0:$trim_start}"
  else
    printf '%s' "$prompt"
  fi
}

__cloudx_prompt_base() {
  local prompt="$1"
  local previous="${CLOUDX_LAST_PROMPT_SEGMENT-}"
  local current
  current="$(__cloudx_prompt_segment)"
  prompt="$(__cloudx_strip_prompt_suffix "$prompt" "$previous")"
  prompt="$(__cloudx_strip_prompt_suffix "$prompt" "$current")"
  printf '%s' "$prompt"
}

__cloudx_refresh_prompt() {
  if [ -z "${ZSH_VERSION:-}" ]; then
    return 0
  fi
  local segment base
  segment="$(__cloudx_prompt_segment)"
  base="$(__cloudx_prompt_base "${RPROMPT-}")"
  CLOUDX_LAST_PROMPT_SEGMENT="$segment"
  RPROMPT="$base$segment"
}

__cloudx_apply_mode() {
  local bin="$1"
  shift
  local shell_code
  shell_code="$("$bin" "$@")" || return $?
  eval "$shell_code" || return $?
  __cloudx_refresh_prompt
}

codexx() {
  local bin="${CLOUDX_CODEXX_BIN:-$HOME/.local/bin/codexx}"
  local command="${1:-}"
  case "$command" in
    add|login|status|logout|list|current|remove|rename|import|diagnose|upgrade|--help|-h|'')
      "$bin" "$@"
      ;;
    exit)
      __cloudx_apply_mode "$bin" _mode exit --shell-pid "$$"
      ;;
    use)
      if [ "$#" -ne 2 ]; then
        echo 'codexx: use requires exactly one account name' >&2
        return 2
      fi
      __cloudx_apply_mode "$bin" _mode account "$2" --shell-pid "$$"
      ;;
    cloud)
      if [ "$#" -eq 1 ]; then
        __cloudx_apply_mode "$bin" _mode cloud --shell-pid "$$"
      elif [ "${2:-}" = "import" ] || [ "${2:-}" = "diagnose" ] || [ "${2:-}" = "upgrade" ]; then
        "$bin" "$@"
      else
        echo 'codexx: cloud supports mode selection, import, diagnose, or upgrade' >&2
        return 2
      fi
      ;;
    api|cpa)
      if [ "$#" -eq 1 ]; then
        __cloudx_apply_mode "$bin" _mode account "$command" --shell-pid "$$"
      elif [ "$#" -eq 2 ] && [ "${2:-}" = "diagnose" ]; then
        "$bin" "$@"
      elif [ "$#" -eq 3 ] && [ "${2:-}" = "diagnose" ] && [ "${3:-}" = "--json" ]; then
        "$bin" "$@"
      elif [ "${2:-}" = "refresh" ] || [ "${2:-}" = "restore" ]; then
        "$bin" "$@"
      else
        echo "codexx: $command supports mode selection, diagnose, refresh, or restore" >&2
        return 2
      fi
      ;;
    *)
      if [ "$#" -ne 1 ]; then
        echo 'codexx: account selection accepts exactly one account name' >&2
        return 2
      fi
      __cloudx_apply_mode "$bin" _mode account "$command" --shell-pid "$$"
      ;;
  esac
}

if [ -n "${ZSH_VERSION:-}" ]; then
  case " ${precmd_functions[*]-} " in
    *" __cloudx_refresh_prompt "*) ;;
    *) precmd_functions+=(__cloudx_refresh_prompt) ;;
  esac
  __cloudx_refresh_prompt
fi

hash -r 2>/dev/null || true
