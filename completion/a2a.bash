#!/bin/bash
# Bash completion script for a2a CLI

_a2a_completion() {
    local cur prev words cword
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    words=("${COMP_WORDS[@]}")
    cword="${COMP_CWORD}"

    local commands="init register send recv peek list status wait clear project unregister search stats thread"

    # Handle flag values
    case "${prev}" in
        --as|--from)
            local agents=$(a2a list 2>/dev/null | awk 'NR>1{print $1}' | tr '\n' ' ')
            COMPREPLY=($(compgen -W "${agents}" -- "${cur}"))
            return 0
            ;;
        --role)
            COMPREPLY=($(compgen -W "architect reviewer fixer analyst manager" -- "${cur}"))
            return 0
            ;;
        --cli)
            COMPREPLY=($(compgen -W "claude opencode pi gemini" -- "${cur}"))
            return 0
            ;;
        --project)
            COMPREPLY=($(compgen -W "default production development test" -- "${cur}"))
            return 0
            ;;
    esac

    # Identify the current command (always the first positional arg)
    local command=""
    if [[ $cword -ge 1 ]] && [[ "${words[1]}" != -* ]]; then
        command="${words[1]}"
    fi

    # Handle command-specific positional argument completion
    case "${command}" in
        send)
            if [[ $cword -eq 2 ]] && [[ "${prev}" != -* ]]; then
                local agents=$(a2a list 2>/dev/null | awk 'NR>1{print $1}' | tr '\n' ' ')
                COMPREPLY=($(compgen -W "all ${agents}" -- "${cur}"))
                return 0
            fi
            ;;
        status)
            if [[ $cword -eq 2 ]] && [[ "${prev}" != -* ]]; then
                COMPREPLY=($(compgen -W "active idle done blocked" -- "${cur}"))
                return 0
            fi
            ;;
        project)
            if [[ $cword -eq 2 ]] && [[ "${prev}" != -* ]]; then
                COMPREPLY=($(compgen -W "default production development test" -- "${cur}"))
                return 0
            fi
            ;;
        unregister)
            if [[ $cword -eq 2 ]] && [[ "${prev}" != -* ]]; then
                local agents=$(a2a list 2>/dev/null | awk 'NR>1{print $1}' | tr '\n' ' ')
                COMPREPLY=($(compgen -W "${agents}" -- "${cur}"))
                return 0
            fi
            ;;
    esac

    # Handle flag completion per command
    if [[ ${cur} == -* ]]; then
        local options=""
        case "${command}" in
            recv)     options="--as --wait --limit --since --all --include-self --peek --json" ;;
            send)     options="--from --thread --ttl --json" ;;
            register) options="--role --prompt --cli --pid --upsert" ;;
            search)   options="--limit --json --fts" ;;
            list)     options="--json" ;;
            status)   options="--as --json" ;;
            wait)     options="--as --count --timeout --since" ;;
            peek)     options="--limit --json" ;;
            clear)    options="--yes" ;;
            stats)    options="--json" ;;
            thread)   options="--json" ;;
            init|project|unregister) options="" ;;
            *)        options="--project --help" ;;
        esac
        COMPREPLY=($(compgen -W "${options}" -- "${cur}"))
        return 0
    fi

    # Default to command completion for the first word
    COMPREPLY=($(compgen -W "${commands}" -- "${cur}"))
}

complete -o bashdefault -o default -o nospace -F _a2a_completion a2a
