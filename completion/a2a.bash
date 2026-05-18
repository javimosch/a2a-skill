#!/bin/bash
# Bash completion script for a2a CLI

_a2a_completion() {
    local cur prev words cword
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    words=("${COMP_WORDS[@]}")
    cword="${COMP_CWORD}"

    # Main commands
    local commands="init register send recv peek list status wait clear project unregister search stats thread"

    # Subcommands that require arguments
    case "${prev}" in
        send)
            # Suggest recipient agents
            local agents=$($0 list 2>/dev/null | awk '{print $1}' | tr '\n' ' ')
            COMPREPLY=($(compgen -W "all ${agents}" -- "${cur}"))
            return 0
            ;;
        status)
            # Suggest status values
            COMPREPLY=($(compgen -W "active idle done blocked" -- "${cur}"))
            return 0
            ;;
        project)
            # Show common projects
            COMPREPLY=($(compgen -W "default production development test" -- "${cur}"))
            return 0
            ;;
        --from|--as)
            # Suggest agents
            local agents=$($0 list 2>/dev/null | awk '{print $1}' | tr '\n' ' ')
            COMPREPLY=($(compgen -W "${agents}" -- "${cur}"))
            return 0
            ;;
    esac

    # Handle options
    if [[ ${cur} == -* ]]; then
        local options="--project --json --limit --wait --include-self --from --as --help"
        COMPREPLY=($(compgen -W "${options}" -- "${cur}"))
        return 0
    fi

    # Default to commands
    COMPREPLY=($(compgen -W "${commands}" -- "${cur}"))
}

complete -o bashdefault -o default -o nospace -F _a2a_completion a2a
