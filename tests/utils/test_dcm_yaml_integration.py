"""
Tests for !delete and !replace YAML tags integration with DeepChainMap layers.

These tests verify that DELETE and ReplaceMarker from YAML source layers
are correctly honored during DCM merge operations.

Test coverage:
- DELETE in front/middle/back layers
- DELETE on nested keys at various depths
- REPLACE in front/middle/back layers
- REPLACE on nested dicts/lists
- Interactions between DELETE and REPLACE
- Complex multi-layer scenarios
"""

import yaml as _yaml

import brynhild.utils.deep_chain_map as dcm

# =============================================================================
# Helpers
# =============================================================================


def load_layer(yaml_str: str) -> dict:
    """Load YAML string using DcmLoader."""
    return _yaml.load(yaml_str, Loader=dcm.DcmLoader)


def make_dcm(*yaml_strings: str) -> dcm.DeepChainMap:
    """Create DCM from YAML strings (first = highest priority)."""
    layers = [load_layer(s) for s in yaml_strings]
    return dcm.DeepChainMap(*layers)


# =============================================================================
# DELETE in Different Layer Positions
# =============================================================================


class TestDeleteFrontLayer:
    """DELETE in the highest priority layer."""

    def test_delete_removes_key_from_lower_layer(self) -> None:
        """DELETE in front layer removes key that exists in back layer."""
        front = "removed_key: !delete"
        back = """
        removed_key: should_disappear
        other_key: still_here
        """
        result = make_dcm(front, back)

        assert "removed_key" not in result
        assert result["other_key"] == "still_here"

    def test_delete_removes_nested_dict_from_lower_layer(self) -> None:
        """DELETE removes entire nested structure."""
        front = """
        settings:
          debug: !delete
        """
        back = """
        settings:
          debug:
            level: verbose
            file: /var/log/debug.log
          production: true
        """
        result = make_dcm(front, back)

        assert "debug" not in result["settings"]
        assert result["settings"]["production"] is True

    def test_delete_deeply_nested_key(self) -> None:
        """DELETE works at arbitrary nesting depth."""
        front = """
        a:
          b:
            c:
              d: !delete
        """
        back = """
        a:
          b:
            c:
              d: deep_value
              e: sibling_value
            f: uncle_value
        """
        result = make_dcm(front, back)

        assert "d" not in result["a"]["b"]["c"]
        assert result["a"]["b"]["c"]["e"] == "sibling_value"
        assert result["a"]["b"]["f"] == "uncle_value"


class TestDeleteMiddleLayer:
    """DELETE in a middle priority layer."""

    def test_delete_in_middle_removes_from_back(self) -> None:
        """DELETE in middle layer removes key from back layer."""
        front = """
        unrelated: front_value
        """
        middle = """
        removed: !delete
        """
        back = """
        removed: back_value
        other: back_other
        """
        result = make_dcm(front, middle, back)

        assert "removed" not in result
        assert result["other"] == "back_other"
        assert result["unrelated"] == "front_value"

    def test_front_can_restore_key_deleted_in_middle(self) -> None:
        """Front layer can provide value for key deleted in middle."""
        front = """
        restored: front_restored_value
        """
        middle = """
        restored: !delete
        """
        back = """
        restored: back_value
        """
        result = make_dcm(front, middle, back)

        # Front layer value should appear (it's higher priority than the delete)
        assert result["restored"] == "front_restored_value"

    def test_delete_in_middle_nested(self) -> None:
        """DELETE in middle layer affects nested keys."""
        front = """
        config:
          added_by_front: "yes"
        """
        middle = """
        config:
          removed_section: !delete
        """
        back = """
        config:
          removed_section:
            setting1: value1
            setting2: value2
          kept_section:
            data: preserved
        """
        result = make_dcm(front, middle, back)

        assert "removed_section" not in result["config"]
        assert result["config"]["kept_section"]["data"] == "preserved"
        assert result["config"]["added_by_front"] == "yes"


class TestDeleteBackLayer:
    """DELETE in the lowest priority layer (edge case)."""

    def test_delete_in_back_has_no_effect_on_key_from_front(self) -> None:
        """DELETE in back layer doesn't affect key set in front layer."""
        front = """
        key: front_value
        """
        back = """
        key: !delete
        """
        result = make_dcm(front, back)

        # Front layer wins, delete in back is irrelevant
        assert result["key"] == "front_value"

    def test_delete_in_back_layer_alone_removes_nothing(self) -> None:
        """DELETE in back layer with no other layers just means key absent."""
        layer = """
        present: value
        absent: !delete
        """
        result = make_dcm(layer)

        assert result["present"] == "value"
        assert "absent" not in result

    def test_delete_in_back_for_key_not_in_any_layer(self) -> None:
        """DELETE for key that doesn't exist elsewhere is benign."""
        front = """
        existing: value
        """
        back = """
        phantom: !delete
        """
        result = make_dcm(front, back)

        assert result["existing"] == "value"
        assert "phantom" not in result


# =============================================================================
# REPLACE in Different Layer Positions
# =============================================================================


class TestReplaceFrontLayer:
    """REPLACE in the highest priority layer."""

    def test_replace_dict_prevents_deep_merge(self) -> None:
        """!replace dict completely replaces, no deep merge."""
        front = """
        settings: !replace
          only: this
        """
        back = """
        settings:
          merged: normally
          deep:
            nested: value
        """
        result = make_dcm(front, back)

        # Back layer settings should be completely replaced
        assert result["settings"] == {"only": "this"}
        assert "merged" not in result["settings"]
        assert "deep" not in result["settings"]

    def test_replace_nested_dict(self) -> None:
        """!replace on nested dict replaces just that branch."""
        front = """
        outer:
          inner: !replace
            replaced: "yes"
        """
        back = """
        outer:
          inner:
            original: data
            more: stuff
          sibling: preserved
        """
        result = make_dcm(front, back)

        assert result["outer"]["inner"] == {"replaced": "yes"}
        assert result["outer"]["sibling"] == "preserved"

    def test_replace_list_explicit(self) -> None:
        """!replace list is explicit replacement (lists already replace by default)."""
        front = """
        items: !replace [a, b, c]
        """
        back = """
        items: [x, y, z]
        """
        result = make_dcm(front, back)

        # Lists already replace, but !replace makes intent explicit
        assert list(result["items"]) == ["a", "b", "c"]

    def test_replace_deeply_nested(self) -> None:
        """!replace works at arbitrary depth."""
        front = """
        level1:
          level2:
            level3: !replace
              fresh: start
        """
        back = """
        level1:
          level2:
            level3:
              old: data
              complex:
                nested: structure
            level3_sibling: kept
          level2_sibling: also_kept
        """
        result = make_dcm(front, back)

        assert result["level1"]["level2"]["level3"] == {"fresh": "start"}
        assert result["level1"]["level2"]["level3_sibling"] == "kept"
        assert result["level1"]["level2_sibling"] == "also_kept"


class TestReplaceMiddleLayer:
    """REPLACE in a middle priority layer."""

    def test_replace_in_middle_replaces_back(self) -> None:
        """!replace in middle replaces back layer value."""
        front = """
        other: front
        """
        middle = """
        config: !replace
          middle_only: true
        """
        back = """
        config:
          back_data: value
          nested:
            deep: structure
        """
        result = make_dcm(front, middle, back)

        # Middle's replace should have wiped back's config
        assert result["config"] == {"middle_only": True}

    def test_front_can_merge_onto_replaced_middle(self) -> None:
        """Front layer deep-merges onto middle's replaced dict."""
        front = """
        config:
          from_front: added
        """
        middle = """
        config: !replace
          base: middle
        """
        back = """
        config:
          from_back: ignored
        """
        result = make_dcm(front, middle, back)

        # Middle replaces back, then front merges onto that
        assert result["config"]["base"] == "middle"
        assert result["config"]["from_front"] == "added"
        assert "from_back" not in result["config"]

    def test_replace_in_middle_nested(self) -> None:
        """!replace in middle on nested key."""
        front = """
        root:
          branch:
            leaf: front_leaf
        """
        middle = """
        root:
          branch: !replace
            clean: slate
        """
        back = """
        root:
          branch:
            old: data
            deep:
              nested: stuff
        """
        result = make_dcm(front, middle, back)

        # Middle replaces branch, front merges leaf into it
        assert result["root"]["branch"]["clean"] == "slate"
        assert result["root"]["branch"]["leaf"] == "front_leaf"
        assert "old" not in result["root"]["branch"]
        assert "deep" not in result["root"]["branch"]


class TestReplaceBackLayer:
    """REPLACE in the lowest priority layer."""

    def test_replace_in_back_still_allows_merge_from_front(self) -> None:
        """!replace in back just sets the base, front still merges."""
        front = """
        data:
          added: by_front
        """
        back = """
        data: !replace
          base: value
        """
        result = make_dcm(front, back)

        # Back's replace sets base, front merges on top
        assert result["data"]["base"] == "value"
        assert result["data"]["added"] == "by_front"

    def test_replace_in_back_alone(self) -> None:
        """!replace in single layer just unwraps the value."""
        layer = """
        config: !replace
          setting: value
        """
        result = make_dcm(layer)

        assert result["config"] == {"setting": "value"}


# =============================================================================
# DELETE and REPLACE Interactions
# =============================================================================


class TestDeleteReplaceInteractions:
    """Interactions between DELETE and REPLACE markers."""

    def test_delete_key_that_was_replaced_below(self) -> None:
        """DELETE can remove a key that was !replace'd in a lower layer."""
        front = """
        removed: !delete
        """
        back = """
        removed: !replace
          complex: structure
          should: disappear
        """
        result = make_dcm(front, back)

        assert "removed" not in result

    def test_replace_key_that_was_deleted_below(self) -> None:
        """!replace can provide value for key deleted in lower layer."""
        front = """
        restored: !replace
          new: value
        """
        back = """
        restored: !delete
        """
        result = make_dcm(front, back)

        # Front's replace wins over back's delete
        assert result["restored"] == {"new": "value"}

    def test_mixed_delete_and_replace_in_same_dict(self) -> None:
        """Same layer can have both DELETE and REPLACE on different keys."""
        front = """
        removed: !delete
        replaced: !replace
          only: this
        normal: value
        """
        back = """
        removed: should_go
        replaced:
          should: be_replaced
          entirely: gone
        normal: back_normal
        extra: back_extra
        """
        result = make_dcm(front, back)

        assert "removed" not in result
        assert result["replaced"] == {"only": "this"}
        assert result["normal"] == "value"
        assert result["extra"] == "back_extra"

    def test_replace_then_delete_nested(self) -> None:
        """!replace in one branch, !delete in another at same level."""
        front = """
        settings:
          logging: !delete
          database: !replace
            host: localhost
        """
        back = """
        settings:
          logging:
            level: debug
            file: /var/log/app.log
          database:
            host: production.db
            port: 5432
            credentials:
              user: admin
          cache:
            enabled: true
        """
        result = make_dcm(front, back)

        assert "logging" not in result["settings"]
        assert result["settings"]["database"] == {"host": "localhost"}
        assert result["settings"]["cache"]["enabled"] is True


# =============================================================================
# Complex Multi-Layer Scenarios
# =============================================================================


class TestComplexScenarios:
    """Complex real-world-like scenarios with multiple layers."""

    def test_three_layer_override_chain(self) -> None:
        """Builtin -> User -> Project override chain with markers."""
        builtin = """
        model:
          name: default-model
          parameters:
            temperature: 0.7
            max_tokens: 1000
        tools:
          - read
          - write
        debug: false
        """
        user = """
        model:
          name: user-preferred-model
          parameters:
            max_tokens: 2000
        features:
          experimental: !delete
        """
        project = """
        model:
          parameters: !replace
            temperature: 0.0
            deterministic: true
        tools: !replace [read]
        features:
          experimental: true
        debug: true
        """
        # Priority: project > user > builtin
        result = make_dcm(project, user, builtin)

        # Model name from user (project didn't set it)
        assert result["model"]["name"] == "user-preferred-model"
        # Parameters completely replaced by project
        assert result["model"]["parameters"] == {"temperature": 0.0, "deterministic": True}
        assert "max_tokens" not in result["model"]["parameters"]
        # Tools replaced
        assert list(result["tools"]) == ["read"]
        # experimental: user deleted, but project (higher priority) sets it
        assert result["features"]["experimental"] is True
        # debug from project
        assert result["debug"] is True

    def test_profile_inheritance_simulation(self) -> None:
        """Simulate profile inheritance with modes."""
        base_mode = """
        system_prompt: |
          You are a helpful assistant.
        max_tokens: 4096
        api_params:
          temperature: 0.7
        patterns:
          - persistence
          - clarity
        """
        storytelling_mode = """
        system_prompt: !replace |
          You are a creative storyteller.
        api_params:
          temperature: 1.2
          top_p: 0.95
        patterns: !replace
          - creativity
          - narrative_flow
        """
        model_specific = """
        max_tokens: 8192
        api_params:
          model_quirk: enabled
        patterns:
          - +model_specific_pattern
        """
        # model_specific > storytelling_mode > base_mode
        result = make_dcm(model_specific, storytelling_mode, base_mode)

        # System prompt replaced by storytelling
        assert "creative storyteller" in result["system_prompt"]
        # max_tokens from model_specific
        assert result["max_tokens"] == 8192
        # api_params merges: model_specific + storytelling (storytelling replaced base)
        assert result["api_params"]["temperature"] == 1.2
        assert result["api_params"]["top_p"] == 0.95
        assert result["api_params"]["model_quirk"] == "enabled"
        # patterns replaced by storytelling, then model-specific can't add (lists replace)
        # Note: with current list semantics, model_specific's patterns would replace
        # This test documents current behavior; we might want different list semantics
        assert "+model_specific_pattern" in list(result["patterns"])

    def test_delete_entire_section_restore_partially(self) -> None:
        """Delete entire section then selectively restore parts."""
        base = """
        features:
          alpha:
            enabled: true
            config:
              level: 1
          beta:
            enabled: true
            config:
              level: 2
          gamma:
            enabled: true
        """
        middle = """
        features: !delete
        """
        top = """
        features:
          alpha:
            enabled: true
            config:
              level: 10
        """
        result = make_dcm(top, middle, base)

        # Middle deleted all features, top restored only alpha
        assert result["features"]["alpha"]["enabled"] is True
        assert result["features"]["alpha"]["config"]["level"] == 10
        assert "beta" not in result["features"]
        assert "gamma" not in result["features"]

    def test_surgical_nested_operations(self) -> None:
        """Precise surgical operations at different nesting levels."""
        layer1 = """
        database:
          primary:
            host: prod.db
            port: 5432
            credentials:
              user: admin
              password: secret
          replica:
            host: replica.db
            port: 5432
        cache:
          redis:
            host: cache.local
            port: 6379
        """
        layer2 = """
        database:
          primary:
            credentials: !delete
          replica: !replace
            host: new-replica.db
        cache:
          redis:
            ttl: 3600
        """
        result = make_dcm(layer2, layer1)

        # Primary host/port preserved, credentials deleted
        assert result["database"]["primary"]["host"] == "prod.db"
        assert result["database"]["primary"]["port"] == 5432
        assert "credentials" not in result["database"]["primary"]

        # Replica entirely replaced
        assert result["database"]["replica"] == {"host": "new-replica.db"}
        assert "port" not in result["database"]["replica"]

        # Cache merged normally
        assert result["cache"]["redis"]["host"] == "cache.local"
        assert result["cache"]["redis"]["port"] == 6379
        assert result["cache"]["redis"]["ttl"] == 3600


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_delete_nonexistent_key_benign(self) -> None:
        """DELETE for key that doesn't exist anywhere is fine."""
        front = """
        ghost: !delete
        """
        back = """
        real: value
        """
        result = make_dcm(front, back)

        assert result["real"] == "value"
        assert "ghost" not in result

    def test_replace_with_empty_dict(self) -> None:
        """!replace with empty dict is valid."""
        front = """
        config: !replace {}
        """
        back = """
        config:
          lots: of
          nested: data
        """
        result = make_dcm(front, back)

        assert result["config"] == {}

    def test_replace_with_empty_list(self) -> None:
        """!replace with empty list is valid."""
        front = """
        items: !replace []
        """
        back = """
        items: [a, b, c, d, e]
        """
        result = make_dcm(front, back)

        assert list(result["items"]) == []

    def test_replace_with_null(self) -> None:
        """!replace with null sets the value to None."""
        front = """
        value: !replace ~
        """
        back = """
        value:
          complex: data
        """
        result = make_dcm(front, back)

        # The value should be None (null)
        assert result["value"] is None

    def test_delete_at_root_level(self) -> None:
        """DELETE can remove top-level keys."""
        front = """
        keep: "yes"
        remove: !delete
        """
        back = """
        keep: back
        remove: back_remove
        also_keep: back_also
        """
        result = make_dcm(front, back)

        assert result["keep"] == "yes"
        assert "remove" not in result
        assert result["also_keep"] == "back_also"

    def test_replace_scalar_with_dict(self) -> None:
        """!replace can change type from scalar to dict."""
        front = """
        setting: !replace
          now_a: dict
        """
        back = """
        setting: was_a_string
        """
        result = make_dcm(front, back)

        assert result["setting"] == {"now_a": "dict"}

    def test_replace_dict_with_scalar(self) -> None:
        """!replace can change type from dict to scalar."""
        front = """
        setting: !replace simple_string
        """
        back = """
        setting:
          was: a_dict
        """
        result = make_dcm(front, back)

        assert result["setting"] == "simple_string"

    def test_many_layers_with_markers(self) -> None:
        """Multiple layers all with markers."""
        layer1 = "a: l1"
        layer2 = "a: !delete"
        layer3 = "a: l3"
        layer4 = """
        a: !replace
          from: l4
        """
        layer5 = "a: l5"

        # Priority: layer1 > layer2 > layer3 > layer4 > layer5
        result = make_dcm(layer1, layer2, layer3, layer4, layer5)

        # layer1 wins with "l1"
        assert result["a"] == "l1"

    def test_only_deletes(self) -> None:
        """Layers that only delete things."""
        front = """
        removed1: !delete
        """
        middle = """
        removed2: !delete
        """
        back = """
        removed1: value1
        removed2: value2
        kept: value3
        """
        result = make_dcm(front, middle, back)

        assert "removed1" not in result
        assert "removed2" not in result
        assert result["kept"] == "value3"

    def test_only_replaces(self) -> None:
        """Layers that only replace things."""
        front = """
        data: !replace
          front_only: true
        """
        back = """
        data:
          back: data
          nested:
            deep: structure
        """
        result = make_dcm(front, back)

        assert result["data"] == {"front_only": True}


class TestReplaceContainingDelete:
    """Tests for REPLACE values that contain DELETE markers inside."""

    def test_replace_dict_with_delete_inside(self) -> None:
        """REPLACE dict containing !delete - delete is preserved inside."""
        front = """
        settings: !replace
          enabled: true
          legacy_option: !delete
        """
        back = """
        settings:
          enabled: false
          legacy_option: old_value
          other: data
        """
        result = make_dcm(front, back)

        # REPLACE means no merge with back
        assert result["settings"]["enabled"] is True
        # DELETE inside REPLACE removes the key from the replaced dict
        assert "legacy_option" not in result["settings"]
        # "other" from back is NOT merged (REPLACE prevents merge)
        assert "other" not in result["settings"]

    def test_replace_nested_with_delete(self) -> None:
        """Nested REPLACE with DELETE inside."""
        front = """
        config:
          database: !replace
            host: newhost
            credentials: !delete
        """
        back = """
        config:
          database:
            host: oldhost
            port: 5432
            credentials:
              user: admin
              pass: secret
        """
        result = make_dcm(front, back)

        # database is replaced entirely
        db = result["config"]["database"]
        assert db["host"] == "newhost"
        assert "credentials" not in db  # DELETE inside REPLACE
        assert "port" not in db  # REPLACE prevents merge

    def test_delete_inside_replace_affects_iteration(self) -> None:
        """DELETE inside REPLACE affects iteration of the replaced value."""
        front = """
        items: !replace
          a: 1
          b: !delete
          c: 3
        """
        result = make_dcm(front)

        items = result["items"]
        keys = list(items.keys())
        assert sorted(keys) == ["a", "c"]
        assert "b" not in items


class TestProvenanceWithDcmMapping:
    """Tests for provenance tracking with DcmMapping layers."""

    def test_provenance_with_dcm_mapping_layers(self) -> None:
        """Provenance works with DcmMapping source layers."""
        import brynhild.utils.deep_chain_map as dcm

        layer0 = dcm.load("""
        model:
          name: from_layer_0
        """)
        layer1 = dcm.load("""
        model:
          name: from_layer_1
          extra: data
        """)

        chain = dcm.DeepChainMap(layer0, layer1, track_provenance=True)
        value, provenance = chain.get_with_provenance("model")

        # name comes from layer 0 (higher priority)
        assert value["name"] == "from_layer_0"
        assert provenance.get("name") == 0

        # extra comes from layer 1, but provenance only tracks at the top dict level
        assert value["extra"] == "data"
        # The dict itself has provenance 1 (first found in layer 1), name override is tracked
        assert provenance.get(".") == 1

    def test_provenance_with_delete_in_layer(self) -> None:
        """Provenance handles DELETE in source layers."""
        import brynhild.utils.deep_chain_map as dcm

        layer0 = dcm.load("""
        config:
          removed: !delete
          kept: from_front
        """)
        layer1 = dcm.load("""
        config:
          removed: was_here
          kept: from_back
          extra: value
        """)

        chain = dcm.DeepChainMap(layer0, layer1, track_provenance=True)
        value, provenance = chain.get_with_provenance("config")

        # removed is deleted
        assert "removed" not in value
        # kept comes from layer 0
        assert value["kept"] == "from_front"
        # extra comes from layer 1
        assert value["extra"] == "value"


class TestDcmDeleteSetCyclesIntegration:
    """Tests for delete/set cycles through DCM (not just DcmMapping)."""

    def test_dcm_delete_then_set_cycle(self) -> None:
        """Delete then set through DCM works correctly."""
        import brynhild.utils.deep_chain_map as dcm

        source = {"key": "original"}
        chain = dcm.DeepChainMap(source)

        # Delete
        del chain["key"]
        assert "key" not in chain

        # Set
        chain["key"] = "restored"
        assert chain["key"] == "restored"

    def test_dcm_multiple_cycles(self) -> None:
        """Multiple delete/set cycles through DCM."""
        import brynhild.utils.deep_chain_map as dcm

        source = {"key": "v0"}
        chain = dcm.DeepChainMap(source)

        for i in range(1, 5):
            del chain["key"]
            assert "key" not in chain

            chain["key"] = f"v{i}"
            assert chain["key"] == f"v{i}"

        assert chain["key"] == "v4"

    def test_dcm_nested_delete_set_cycle(self) -> None:
        """Delete/set cycles on nested keys."""
        import brynhild.utils.deep_chain_map as dcm

        source = {"outer": {"inner": "original"}}
        chain = dcm.DeepChainMap(source)

        # Delete nested
        del chain["outer"]["inner"]
        assert "inner" not in chain["outer"]

        # Set nested
        chain["outer"]["inner"] = "restored"
        assert chain["outer"]["inner"] == "restored"

        # Delete again
        del chain["outer"]["inner"]
        assert "inner" not in chain["outer"]

