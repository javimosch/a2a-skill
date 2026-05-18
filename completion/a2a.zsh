#!/bin/zsh
# Zsh completion script for a2a CLI

_a2a() {
    local context state state_descr line
    local -a args
    local -A opt_args

    args=(
        '1: :(init register send recv peek list status wait clear project unregister search stats thread)'
        '*::arg:->args'
    )

    _arguments "${args[@]}" && return

    case "${state}" in
        args)
            case "${words[2]}" in
                send)
                    # Recipient agent
                    _values "recipient" "all" "*" "broadcast"
                    ;;
                status)
                    # Status value
                    _values "status" "active" "idle" "done" "blocked"
                    ;;
                project)
                    # Project name
                    _values "project" "default" "production" "development" "test"
                    ;;
                recv|wait|peek)
                    # Global options
                    _arguments \
                        '--limit[limit messages]:num:' \
                        '--wait[wait seconds]:seconds:' \
                        '--json[output JSON]' \
                        '--include-self[include own messages]' \
                        '--unread[unread only]' \
                        '--as[agent ID]:agent:' \
                        '--project[project name]:project:'
                    ;;
                *)
                    # Generic options for any command
                    _arguments \
                        '--project[project name]:project:' \
                        '--json[output JSON]' \
                        '--help[show help]' \
                        '--version[show version]'
                    ;;
            esac
            ;;
    esac
}

_a2a "$@"
