# Work with Jira issues

Create, update, search, and manage Jira issues using the atlassian-cli.

## Instructions

You are working with Jira issues. The `jira` CLI handles all operations.

### Search for issues

```bash
jira issue search "project = PROJ AND status = 'To Do'" --max 20
```

Use JQL (Jira Query Language) for searches. Common filters:
- `project = KEY` — filter by project
- `status = 'In Progress'` — filter by status
- `labels = 'label-name'` — filter by label
- `assignee = currentUser()` — your issues
- `updated >= -7d` — recently updated

### Get issue details

```bash
jira issue get PROJ-123
```

Use `--json` for machine-readable output.

### Create an issue

```bash
jira issue create PROJECT_KEY "Task" "Issue summary" \
  --description "Detailed description" \
  --labels "label1" --labels "label2" \
  --assignee "user@email.com"
```

For subtasks, add `--parent PROJ-123`.

### Update an issue

```bash
jira issue update PROJ-123 --summary "New title" --description "New desc"
jira issue update PROJ-123 --labels "new-label"
jira issue update PROJ-123 --fields '{"priority": {"name": "High"}}'
```

### Transition (change status)

```bash
jira issue transition PROJ-123 "In Progress"
jira issue transition PROJ-123 "Done"
```

### Comments

```bash
jira issue comment PROJ-123 "This is a comment"
jira issue comments PROJ-123    # list comments
```

### Tips

- All commands accept `--json` for structured output
- Descriptions use ADF format internally — plain text strings are auto-wrapped
- For complex descriptions, use the `atlassian_cli.adf` module to build ADF nodes
- Labels are added cumulatively with `--labels`
