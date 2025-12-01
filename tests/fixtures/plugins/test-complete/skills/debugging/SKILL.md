---
name: debugging
description: Systematic approach to debugging Python code - use when user encounters errors or unexpected behavior
license: MIT
allowed-tools:
  - bash
  - read_file
  - grep
metadata:
  difficulty: intermediate
  language: python
---

# Debugging Skill

[TEST-PLUGIN-SKILL: debugging]

## When to Use This Skill

Use this skill when:
- User reports an error or exception
- Code produces unexpected output
- Tests are failing
- Performance issues need investigation

## Systematic Debugging Process

1. **Reproduce the Issue**
   - Get exact error message
   - Identify minimal reproduction steps

2. **Gather Information**
   - Check stack trace
   - Review recent changes
   - Check logs

3. **Form Hypothesis**
   - What could cause this behavior?
   - What assumptions might be wrong?

4. **Test Hypothesis**
   - Add logging/print statements
   - Use debugger breakpoints
   - Write minimal test case

5. **Fix and Verify**
   - Make minimal change
   - Run tests
   - Confirm fix doesn't break other things

