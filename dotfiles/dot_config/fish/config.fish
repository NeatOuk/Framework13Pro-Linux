# ~/.config/fish/config.fish — managed by chezmoi
set -g fish_greeting
if type -q mise; mise activate fish | source; end
if type -q starship; starship init fish | source; end
alias ll 'ls -lah --color=auto'
if type -q fzf; fzf --fish | source; end
