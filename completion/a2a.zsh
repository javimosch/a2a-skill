#!/bin/zsh
# Zsh completion script for a2a CLI

_a2a_agents() {
    local -a agents
    agents=(${(f)"$(a2a list 2>/dev/null | awk 'NR>1{print $1}')"})
    _describe 'agent' agents
}

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
                    _arguments \
                        '--from[agent ID]:agent:->agents' \
                        '--thread[thread ID]:thread:' \
                        '--ttl[TTL seconds]:seconds:' \
                        '--json[output JSON]' \
                        '1:recipient:->agents_or_all' \
                        '2:message body:'
                    ;;
                recv)
                    _arguments \
                        '--as[agent ID]:agent:->agents' \
                        '--wait[wait seconds]:seconds:' \
                        '--limit[message limit]:limit:' \
                        '--since[unix timestamp]:timestamp:' \
                        '--all[include already-read messages]' \
                        '--include-self[include own messages]' \
                        '--peek[do not mark as read]' \
                        '--json[output JSON]'
                    ;;
                register)
                    _arguments \
                        '--role[agent role]:role:' \
                        '--prompt[system prompt]:prompt:' \
                        '--cli[CLI type]:cli:->cli_types' \
                        '--pid[process ID]:pid:' \
                        '--upsert[update if exists]' \
                        '1:agent id:'
                    ;;
                search)
                    _arguments \
                        '--limit[result limit]:limit:' \
                        '--json[output JSON]' \
                        '--fts[force FTS5 full-text search]' \
                        '1:query:'
                    ;;
                list)
                    _arguments \
                        '--json[output JSON]'
                    ;;
                status)
                    _arguments \
                        '--as[agent ID]:agent:->agents' \
                        '--json[output JSON]' \
                        '1:status:(active idle done blocked)'
                    ;;
                wait)
                    _arguments \
                        '--as[agent ID]:agent:->agents' \
                        '--count[message count]:count:' \
                        '--timeout[timeout seconds]:timeout:' \
                        '--since[unix timestamp]:timestamp:'
                    ;;
                peek)
                    _arguments \
                        '--limit[message limit]:limit:' \
                        '--json[output JSON]'
                    ;;
                clear)
                    _arguments \
                        '--yes[skip confirmation]'
                    ;;
                stats)
                    _arguments \
                        '--json[output JSON]'
                    ;;
                thread)
                    _arguments \
                        '--json[output JSON]' \
                        '1:thread id:'
                    ;;
                init|project|unregister)
                    :
                    ;;
                *)
                    _arguments \
                        '--project[project name]:project:' \
                        '--help[show help]'
                    ;;
            esac
            ;;
    esac

    case "${state}" in
        agents)
            _a2a_agents
            ;;
        agents_or_all)
            local -a alist
            alist=("all" ${(f)"$(a2a list 2>/dev/null | awk 'NR>1{print $1}')"})
            _describe 'recipient' alist
            ;;
        cli_types)
            _values 'cli' 'claude' 'opencode' 'pi' 'gemini'
            ;;
    esac
}

_a2a "$@"
