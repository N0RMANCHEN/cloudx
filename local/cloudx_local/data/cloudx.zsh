# Cloudx minimal shell integration.
unset -f codex 2>/dev/null || true
if [ -n "${CODEXX_USER_HOME:-}" ]; then
  export HOME="$CODEXX_USER_HOME"
fi
unset OPENAI_API_KEY OPENAI_BASE_URL OPENAI_API_BASE
codexx() {
  local bin="${CLOUDX_CODEXX_BIN:-$HOME/.local/bin/codexx}"
  local command="${1:-}"
  case "$command" in
    add|login|status|logout|list|current|--help|-h|'') "$bin" "$@" ;;
    exit) eval "$("$bin" exit)" ;;
    use)
      if [ "$#" -ne 2 ]; then
        echo 'codexx: use requires exactly one account name' >&2
        return 2
      fi
      eval "$("$bin" use "$2")"
      ;;
    *)
      if [ "$#" -ne 1 ]; then
        echo 'codexx: account selection accepts exactly one account name' >&2
        return 2
      fi
      eval "$("$bin" "$command")"
      ;;
  esac
}
hash -r 2>/dev/null || true
