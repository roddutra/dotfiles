---
description: Create timestamped session documentation for handoff
allowed-tools: TodoWrite, Read, Write, Bash(date:*), Bash(mkdir:*)
---

## CRITICAL: THIS IS A FILE CREATION TASK

!`mkdir -p docs/temp/sessions`
!`date +"%Y-%m-%d_%H-%M-%S"`

**YOUR PRIMARY TASK**: You MUST create and save a documentation file. DO NOT just respond with the content - you MUST use the Write tool to save it.

### STEP 1: Generate Documentation Content

Create comprehensive session documentation that includes ALL of the following sections so that a new agent without any prior context can pick up where you left off with all the information they would need:

1. **Session Overview**
   - Current date/time (use the output from the date command above)
   - Brief summary of the main task/objective
   - Current status of the work

2. **Todo List Status**
   - Current todo list with status of each item (if TodoWrite was used) so it can be recreated
   - Completed tasks
   - In-progress tasks
   - Pending tasks

3. **Context and Background**
   - Original requirements/request
   - Key decisions made and their rationale
   - Important constraints or considerations discovered

4. **Technical Details**
   - What has been implemented/changed
   - Key files modified or created
   - Technologies, libraries, or frameworks used
   - Code patterns or approaches adopted

5. **Learning and Discovery**
   - What we've learned during this session
   - Key insights or discoveries
   - Understanding of the codebase structure

6. **What Worked**
   - Successful approaches or solutions
   - Effective tools or techniques used
   - Validated assumptions

7. **What Didn't Work**
   - Failed attempts and why they failed
   - Approaches that were abandoned
   - Common pitfalls to avoid

8. **What's Missing/Next Steps**
   - Remaining tasks or requirements
   - Known issues or bugs to address
   - Suggested next steps for continuation

9. **Resources and References**
   - Links to documentation consulted
   - External resources that influenced decisions
   - Relevant code examples or patterns referenced
   - Any MCP tools or services used

10. **Handoff Notes**
    - Specific things the next agent should know
    - Current working directory and environment state
    - Any commands that need to be run regularly
    - Potential gotchas or things to watch out for

### STEP 2: SAVE THE FILE (MANDATORY)

**YOU MUST USE THE Write TOOL** to save the documentation with:
- **Path**: `docs/temp/sessions/session_<timestamp>.md` (use the timestamp from the date command output above - create the `docs/temp/sessions` directory if it doesn't already exist)
  - eg. `docs/temp/sessions/session_2025-10-30_15-55-54.md`
- **Content**: The comprehensive documentation you generated in Step 1

### STEP 3: REVIEW & UPDATE `.gitignore` (MANDATORY)

- Check if either the `docs/temp/` or `docs/temp/sessions/` directory is already in `.gitignore`
- If it is not, add `docs/temp/sessions/` to gitignore to prevent it from being committed

### IMPORTANT REMINDERS:
- ⚠️ DO NOT just output the documentation as a response
- ⚠️ YOU MUST use the Write tool to create the file
- ⚠️ The file MUST be saved in the `docs/temp/sessions/` directory
- ⚠️ Use the exact timestamp from the date command for the filename
- 📝 Note: The `sessions` folder is likely git-ignored in most projects, which is intentional to keep session docs local
  - ⚠️ Ensure that either the `sessions` directory or its parent `temp` directory is in `.gitignore` as per [STEP 3](#step-3-review--update-gitignore-mandatory)

After saving the file, confirm to the user that the session documentation has been saved and provide the relative path to the session file (eg. `docs/temp/sessions/session_2025-10-30_15-55-54.md`).

## ADDITIONAL INSTRUCTIONS

$ARGUMENTS