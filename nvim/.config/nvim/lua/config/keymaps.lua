-- Keymaps are automatically loaded on the VeryLazy event
-- Default keymaps that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/keymaps.lua
-- Add any additional keymaps here

-- Tmux integration keymaps (using <leader>t prefix to avoid conflicts)
vim.keymap.set("n", "<leader>tw", "<cmd>silent !tmux choose-window<CR>", { desc = "Tmux: Choose window" })
vim.keymap.set("n", "<leader>ts", "<cmd>silent !tmux choose-session<CR>", { desc = "Tmux: Choose session" })
vim.keymap.set("n", "<leader>tc", "<cmd>silent !tmux new-window<CR>", { desc = "Tmux: New window" })
vim.keymap.set("n", "<leader>tx", "<cmd>silent !tmux kill-window<CR>", { desc = "Tmux: Kill current window" })
vim.keymap.set("n", "<leader>tn", "<cmd>silent !tmux next-window<CR>", { desc = "Tmux: Next window" })
vim.keymap.set("n", "<leader>tp", "<cmd>silent !tmux previous-window<CR>", { desc = "Tmux: Previous window" })
vim.keymap.set("n", "<leader>tr", "<cmd>!tmux command-prompt 'rename-window %%'<CR>", { desc = "Tmux: Rename window" })
vim.keymap.set("n", "<leader>td", "<cmd>silent !tmux detach-client<CR>", { desc = "Tmux: Detach session" })
