"""
Profile manager for loading and resolving model profiles.
"""

from __future__ import annotations

import pathlib as _pathlib

import brynhild.profiles.types as types


class ProfileManager:
    """
    Manager for loading and resolving model profiles.

    Profiles are resolved by matching model identifiers in this order:
    1. Exact match by profile name
    2. Family match (model name prefix)
    3. Default profile

    Profile loading priority (later sources override earlier):
    1. Builtin profiles (from brynhild.profiles.builtin)
    2. Plugin profiles (from plugin profiles/ directories)
    3. User profiles (from ~/.config/brynhild/profiles/)
    """

    def __init__(
        self,
        config_dir: _pathlib.Path | None = None,
        load_user_profiles: bool = True,
        load_plugin_profiles: bool = True,
    ) -> None:
        """
        Initialize the profile manager.

        Args:
            config_dir: Directory for user profiles. Defaults to ~/.config/brynhild.
            load_user_profiles: Whether to load user-defined profiles from config_dir.
            load_plugin_profiles: Whether to load profiles from discovered plugins.
        """
        self._config_dir = config_dir or _pathlib.Path.home() / ".config" / "brynhild"
        self._profiles: dict[str, types.ModelProfile] = {}

        # Load in priority order (later sources override earlier)
        # 1. Builtin profiles (lowest priority)
        self._load_builtin_profiles()

        # 2. Plugin profiles (can override builtins)
        if load_plugin_profiles:
            self._load_plugin_profiles()

        # 3. User profiles (highest priority)
        if load_user_profiles:
            self._load_user_profiles()

    def _load_builtin_profiles(self) -> None:
        """Load builtin profiles from the profiles.builtin module."""
        import brynhild.profiles.builtin as builtin

        for profile in builtin.get_all_profiles():
            self._profiles[profile.name] = profile

    def _load_plugin_profiles(self) -> None:
        """Load profiles from discovered plugin directories."""
        try:
            import brynhild.plugins.profiles as plugin_profiles

            loaded = plugin_profiles.load_all_plugin_profiles()
            self._profiles.update(loaded)
        except ImportError:
            # Plugin system not available (minimal install)
            pass
        except Exception:
            # Don't fail profile manager if plugin loading fails
            pass

    def _load_user_profiles(self) -> None:
        """Load user-defined profiles from YAML files."""
        profiles_dir = self._config_dir / "profiles"
        if not profiles_dir.exists():
            return

        import yaml as _yaml

        for yaml_file in profiles_dir.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    data = _yaml.safe_load(f)
                if data and isinstance(data, dict):
                    profile = types.ModelProfile.from_dict(data)
                    self._profiles[profile.name] = profile
            except Exception:
                # Skip invalid profile files
                pass

    def resolve(
        self,
        model: str,
        provider: str | None = None,
    ) -> types.ModelProfile:
        """
        Resolve the best matching profile for a model.

        Args:
            model: Model identifier (e.g., 'openai/gpt-oss-120b', 'gpt-oss-120b').
            provider: Optional provider name for provider-specific matching.

        Returns:
            The best matching ModelProfile, or default if no match.
        """
        # Normalize model name for matching
        normalized = self._normalize_model_name(model)

        # 1. Exact match by profile name
        if normalized in self._profiles:
            return self._profiles[normalized]

        # 2. Try with provider prefix
        if provider:
            provider_key = f"{provider}/{normalized}"
            if provider_key in self._profiles:
                return self._profiles[provider_key]

        # 3. Family match - find profile where model starts with family
        for profile in self._profiles.values():
            if profile.family and normalized.startswith(profile.family):
                return profile

        # 4. Default profile
        if "default" in self._profiles:
            return self._profiles["default"]

        # 5. Return a minimal default profile
        return types.ModelProfile(name="default", description="Default profile")

    def _normalize_model_name(self, model: str) -> str:
        """
        Normalize a model name for matching.

        Handles variations like:
        - 'openai/gpt-oss-120b' -> 'gpt-oss-120b'
        - 'gpt-oss:120b' -> 'gpt-oss-120b' (legacy Ollama format)
        """
        # Remove provider prefix if present
        if "/" in model:
            model = model.split("/")[-1]

        # Replace colons with dashes
        model = model.replace(":", "-")

        return model.lower()

    def get_profile(self, name: str) -> types.ModelProfile | None:
        """Get a profile by exact name."""
        return self._profiles.get(name)

    def list_profiles(self) -> list[types.ModelProfile]:
        """List all available profiles."""
        return list(self._profiles.values())

    def register_profile(self, profile: types.ModelProfile) -> None:
        """Register a profile (for testing or dynamic registration)."""
        self._profiles[profile.name] = profile


# Global instance for convenience
_default_manager: ProfileManager | None = None


def get_manager() -> ProfileManager:
    """Get the default profile manager instance."""
    global _default_manager
    if _default_manager is None:
        _default_manager = ProfileManager()
    return _default_manager


def resolve_profile(
    model: str,
    provider: str | None = None,
) -> types.ModelProfile:
    """
    Convenience function to resolve a profile using the default manager.

    Args:
        model: Model identifier.
        provider: Optional provider name.

    Returns:
        The best matching ModelProfile.
    """
    return get_manager().resolve(model, provider)

