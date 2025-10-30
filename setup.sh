#!/bin/bash
set -e

echo "============================================"
echo "Setting Up Dotfiles"
echo "============================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Change to dotfiles directory
cd "$(dirname "$0")"

echo "Step 1: Configuring git to ignore local changes to .zshrc..."
git update-index --assume-unchanged zsh/.zshrc
echo -e "${GREEN}✓${NC} Git will ignore local .zshrc modifications"
echo "  (Tools can now auto-append configs without polluting git)"
echo ""

echo "Step 2: Creating .zsh-secrets file if needed..."
if [ ! -f "zsh/.zsh-secrets" ]; then
    cp zsh/.zsh-secrets.example zsh/.zsh-secrets
    echo -e "${GREEN}✓${NC} Created zsh/.zsh-secrets from template"
    echo -e "  ${YELLOW}→${NC} Edit this file to add your sensitive environment variables"
else
    echo -e "${BLUE}ℹ${NC} zsh/.zsh-secrets already exists, skipping"
fi
echo ""

echo "============================================"
echo -e "${GREEN}Setup Complete!${NC}"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Run 'stow zsh' to symlink zsh configs to your home directory"
echo "  2. Edit ~/.zsh-secrets to add your sensitive environment variables"
echo "  3. Restart your terminal or run 'source ~/.zshrc'"
echo ""
echo "Your zsh configuration structure:"
echo "  • ~/.zshrc          → Loader (tools will auto-append here)"
echo "  • ~/.zsh-settings   → Your curated config (version controlled)"
echo "  • ~/.zsh-secrets    → Your secrets (gitignored)"
echo ""
