   - Optional: open a page in a real browser with the `agent-browser` CLI, only to try an interactive element or follow the navigation like a visitor.
     - Use your own session: `agent-browser --session <your run id> ...`.
${page_addresses}     - Screenshot, scroll and click. Never dump the page source.
     - Save screenshots only to `${panel_dir}/scratch/<your run id>/`, using absolute paths. That folder exists already.
     - Run each `agent-browser` command on its own. Any other shell command (`mkdir`, `ls`, `sleep`) can be refused, and a line that chains one to an `agent-browser` command is then refused whole.
     - Close your session when done.
