#!/usr/bin/env bash
# update-linear-mcp-configs.sh — inject the Linear bot access token from
# macOS Keychain into both Codex and Claude Code MCP configs as an
# `Authorization: Bearer ...` header. Run this:
#
#   1. After initial bot setup (bot-identity.md runbook Step C).
#   2. After every Linear token rotation (re-run linear-oauth-bootstrap.sh
#      to mint a fresh token; then this script to push it into the configs).
#
# The token never appears in argv, env, or stdout — read directly from
# Keychain inside a single Python process and written to the on-disk
# configs.
#
# Files updated:
#   ~/.codex/config.toml         [mcp_servers.linear].http_headers.Authorization
#   ~/.claude.json               mcpServers.linear.headers.Authorization
#                                projects.<path>.mcpServers.linear.headers.Authorization
#
# Requires: bash, python3, security (all on macOS by default).
# Requires: ai-skills.linear-bot.access-token in Keychain.
#
# Usage:
#   bash update-linear-mcp-configs.sh
#
# After running, restart Codex and Claude Code for the new MCP config to
# take effect.

set -euo pipefail

python3 <<'PYEOF'
import json
import os
import re
import subprocess
import sys

USER = os.environ['USER']

# Pull the bot access token from Keychain. Never logged or echoed.
try:
    token = subprocess.run(
        ['security', 'find-generic-password',
         '-s', 'ai-skills.linear-bot.access-token',
         '-a', USER, '-w'],
        capture_output=True, text=True, check=True
    ).stdout.strip()
except subprocess.CalledProcessError:
    print('Missing Keychain entry: ai-skills.linear-bot.access-token', file=sys.stderr)
    print('Run linear-oauth-bootstrap.sh first to mint and store the token.', file=sys.stderr)
    sys.exit(1)

if not token:
    print('Keychain returned empty token.', file=sys.stderr)
    sys.exit(2)

updates = 0

# === Codex ~/.codex/config.toml ===
codex_path = os.path.expanduser('~/.codex/config.toml')
if os.path.exists(codex_path):
    with open(codex_path) as f:
        codex_content = f.read()

    linear_section_marker = '[mcp_servers.linear]'
    linear_url_line = 'url = "https://mcp.linear.app/mcp"'
    http_headers_line = f'http_headers = {{ Authorization = "Bearer {token}" }}'

    if linear_section_marker not in codex_content:
        print(f'Codex: no [mcp_servers.linear] section found in {codex_path}; skipping.')
    elif 'http_headers' in codex_content and linear_section_marker in codex_content:
        # Replace existing http_headers under [mcp_servers.linear].
        pattern = r'(\[mcp_servers\.linear\][^\[]*?)http_headers\s*=\s*\{[^}]*\}'
        new_content = re.sub(pattern, r'\1' + http_headers_line, codex_content, flags=re.DOTALL)
        if new_content != codex_content:
            with open(codex_path, 'w') as f:
                f.write(new_content)
            print(f'Codex: replaced http_headers in {codex_path}')
            updates += 1
        else:
            print(f'Codex: http_headers already up-to-date (no-op).')
    else:
        # Add http_headers immediately after the URL line.
        target = f'{linear_section_marker}\n{linear_url_line}'
        if target not in codex_content:
            print(f'Codex: could not find expected URL line under {linear_section_marker} in {codex_path}', file=sys.stderr)
            print(f'       Add http_headers = {{ Authorization = "Bearer <token>" }} manually.', file=sys.stderr)
            sys.exit(3)
        replacement = f'{linear_section_marker}\n{linear_url_line}\n{http_headers_line}'
        new_content = codex_content.replace(target, replacement)
        with open(codex_path, 'w') as f:
            f.write(new_content)
        print(f'Codex: added http_headers under {linear_section_marker} in {codex_path}')
        updates += 1
else:
    print(f'Codex: {codex_path} does not exist; skipping.')

# === Claude Code ~/.claude.json ===
claude_path = os.path.expanduser('~/.claude.json')
if os.path.exists(claude_path):
    with open(claude_path) as f:
        claude_config = json.load(f)

    # Global mcpServers.linear
    if 'mcpServers' in claude_config and 'linear' in claude_config['mcpServers']:
        existing = claude_config['mcpServers']['linear'].get('headers', {}).get('Authorization')
        new_value = f'Bearer {token}'
        if existing != new_value:
            claude_config['mcpServers']['linear']['headers'] = {'Authorization': new_value}
            print(f'Claude: updated global mcpServers.linear.headers')
            updates += 1
        else:
            print(f'Claude: global mcpServers.linear.headers already up-to-date (no-op).')

    # Project-level mcpServers.linear (if any)
    if 'projects' in claude_config:
        for proj_path, proj in claude_config['projects'].items():
            if isinstance(proj, dict) and 'mcpServers' in proj and 'linear' in proj['mcpServers']:
                existing = proj['mcpServers']['linear'].get('headers', {}).get('Authorization')
                new_value = f'Bearer {token}'
                if existing != new_value:
                    proj['mcpServers']['linear']['headers'] = {'Authorization': new_value}
                    print(f'Claude: updated projects[{proj_path}].mcpServers.linear.headers')
                    updates += 1
                else:
                    print(f'Claude: projects[{proj_path}].mcpServers.linear.headers already up-to-date (no-op).')

    with open(claude_path, 'w') as f:
        json.dump(claude_config, f, indent=2)
else:
    print(f'Claude: {claude_path} does not exist; skipping.')

print()
if updates > 0:
    print(f'Done — {updates} config entries updated.')
    print('RESTART Codex and Claude Code for the new MCP config to take effect.')
else:
    print('Done — all configs already up-to-date. No restart needed.')
PYEOF
