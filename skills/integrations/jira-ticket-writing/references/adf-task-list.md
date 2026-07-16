# Jira ADF Task Lists

Use Atlassian Document Format task nodes when a Jira field supports rich-text task checkboxes:

```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {
      "type": "taskList",
      "attrs": { "localId": "ticket-ac" },
      "content": [
        {
          "type": "taskItem",
          "attrs": { "localId": "ticket-ac-1", "state": "TODO" },
          "content": [{ "type": "text", "text": "Criterion text." }]
        }
      ]
    }
  ]
}
```

Use stable, unique `localId` values for the list and each item. If the configured Jira field does not support ADF task nodes, return a draft and report the capability limitation rather than silently degrading to Markdown checkbox text.
