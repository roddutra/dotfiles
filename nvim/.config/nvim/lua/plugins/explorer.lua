return {
  -- Make the snacks.nvim file explorer show hidden dotfiles by default
  -- (e.g. .claude, .github, .githooks)
  {
    "folke/snacks.nvim",
    opts = {
      picker = {
        sources = {
          explorer = {
            hidden = true, -- show dotfiles (.claude, .github, etc.)
            ignored = true, -- also show gitignored files/folders
          },
        },
      },
    },
  },
}
