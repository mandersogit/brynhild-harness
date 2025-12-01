---
name: greet
description: A test greeting command
aliases:
  - hi
  - hello
args: "[name]"
---

# Greet Command

Say hello to the user. Arguments: {{args}}

Current directory: {{cwd}}

Environment user: {{env.USER}}

