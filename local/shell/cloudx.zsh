# Cloudx minimal shell integration.
# `codex` is deliberately left as the official executable.

unset -f codex 2>/dev/null || true
if [ -n "${CODEXX_USER_HOME:-}" ]; then
  export HOME="$CODEXX_USER_HOME"
fi
unset OPENAI_API_KEY OPENAI_BASE_URL OPENAI_API_BASE

codexx() {
  local bin="${CLOUDX_CODEXX_BIN:-$HOME/.local/bin/codexx}"
  local command="${1:-}"
  case "$command" in
    add|login|status|logout|list|current|remove|rename|import|--help|-h|'')
      "$bin" "$@"
      ;;
    exit)
      eval "$("$bin" _mode exit --shell-pid "$$")"
      ;;
    use)
      if [ "$#" -ne 2 ]; then
        echo 'codexx: use requires exactly one account name' >&2
        return 2
      fi
      eval "$("$bin" _mode account "$2" --shell-pid "$$")"
      ;;
    cloud)
      if [ "$#" -eq 1 ]; then
        eval "$("$bin" _mode cloud --shell-pid "$$")"
      elif [ "${2:-}" = "import" ]; then
        "$bin" "$@"
      else
        echo 'codexx: cloud supports mode selection or cloud import <source>' >&2
        return 2
      fi
      ;;
    *)
      if [ "$#" -ne 1 ]; then
        echo 'codexx: account selection accepts exactly one account name' >&2
        return 2
      fi
      eval "$("$bin" _mode account "$command" --shell-pid "$$")"
      ;;
  esac
}

hash -r 2>/dev/null || true
