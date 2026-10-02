# Bash completion for the `karen` command.
#
# Install it where the bash-completion lazy loader finds it:
#   sudo install -m 644 libraries/completion.bash \
#       /usr/share/bash-completion/completions/karen
# The loader ships in the `bash-completion` package (sourced by /etc/bash.bashrc when
# present) and picks this up on first TAB of `karen`. This is a DATA file, not a module.
#
# Position 1 completes the subcommand list. `version` completes the part
# (major/minor/patch) then its flags; `commit` takes nothing. Everything else falls
# back to nothing.

_karen_complete() {
    local cur prev words cword
    # _get_comp_words_by_ref is provided by bash-completion; fall back to the raw
    # arrays if it is not loaded, so the completion still works on a bare system.
    if declare -F _get_comp_words_by_ref >/dev/null 2>&1; then
        _get_comp_words_by_ref cur prev words cword
    else
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
        words=("${COMP_WORDS[@]}")
        cword="$COMP_CWORD"
    fi

    local subcommands="commit version help"

    # Position 1: the subcommand itself.
    if [ "$cword" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$subcommands" -- "$cur") )
        return 0
    fi

    local sub="${words[1]}"
    case "$sub" in
        version)
            # First positional = the semver part; after that, flags.
            if [ "$cword" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "major minor patch" -- "$cur") )
            elif [ "$prev" = "--file" ]; then
                COMPREPLY=( $(compgen -f -- "$cur") )           # --file takes a path
            else
                COMPREPLY=( $(compgen -W "--file" -- "$cur") )
            fi
            return 0
            ;;
        *)
            # commit / help take no positional we can complete.
            return 0
            ;;
    esac
}

complete -F _karen_complete karen
