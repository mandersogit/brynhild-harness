---
name: testing
description: Best practices for writing Python tests - use when creating or improving test coverage
license: MIT
allowed-tools:
  - bash
  - read_file
  - write_file
metadata:
  framework: pytest
---

# Testing Skill

[TEST-PLUGIN-SKILL: testing]

## When to Use This Skill

Use this skill when:
- Writing new tests
- Improving test coverage
- Refactoring test code
- Setting up test infrastructure

## Test Structure

```python
class TestFeatureName:
    """Tests for specific feature."""
    
    def test_specific_behavior(self) -> None:
        """One test, one assertion pattern."""
        # Arrange
        input_data = create_test_data()
        
        # Act
        result = function_under_test(input_data)
        
        # Assert
        assert result == expected_value
```

## Best Practices

1. **Naming**: `test_<behavior>_<condition>_<expected>`
2. **Isolation**: Each test independent, use fixtures
3. **Coverage**: Test happy path, edge cases, errors
4. **Speed**: Keep unit tests fast (<100ms each)

