"""
sapt.execution.multi_source
Multi-resource download and installation system with intelligent fallback.

Features:
- Multiple resource providers for each package
- Automatic fallback between resources
- User feedback on resource switching
- Resource preference ordering
- Cache-aware resource selection
"""

import time
from typing import Optional
from dataclasses import dataclass

from sapt.ui.display import Display


@dataclass
class ResourceProvider:
    """Represents a resource provider for downloading and installing packages."""
    
    name: str  # "apt", "snap", "flatpak", "github", etc.
    priority: int  # Lower number = higher priority
    supports_install: bool = True
    supports_uninstall: bool = True
    requires_sudo: bool = False
    api_available: bool = True
    description: str = ""
    
    # GitHub-specific fields
    github_owner: Optional[str] = None
    github_repo: Optional[str] = None
    github_asset_pattern: Optional[str] = None
    
    # Snap/Flatpak specific
    snap_name: Optional[str] = None
    flatpak_name: Optional[str] = None


class ResourceManager:
    """Manages multiple resource providers with intelligent fallback."""
    
    # Default priority ordering for resources
    DEFAULT_PRIORITIES = {
        "apt": 1,
        "snap": 2,
        "flatpak": 2,
        "ppa": 3,
        "github": 4,
    }
    
    def __init__(self, display: Optional[Display] = None):
        self.display = display
        self._providers: dict[str, ResourceProvider] = {}
        self._packages_resources: dict[str, list[ResourceProvider]] = {}  # Cache of which resources support which packages
        
    def register_provider(self, provider: ResourceProvider) -> None:
        """Register a resource provider."""
        self._providers[provider.name] = provider
    
    def get_provider(self, name: str) -> Optional[ResourceProvider]:
        """Get a registered provider by name."""
        return self._providers.get(name)
    
    def get_all_providers(self) -> list[ResourceProvider]:
        """Get all registered providers sorted by priority."""
        return sorted(self._providers.values(), key=lambda p: p.priority)
    
    def discover_resources_for_package(
        self, 
        package: str, 
        context: Optional[dict] = None
    ) -> list[ResourceProvider]:
        """Discover all resources that can provide a package."""
        resources = []
        
        # Check if we have cached discovery results
        cache_key = f"discovery_{package}"
        cached = self._get_discovery_cache(cache_key)
        if cached:
            for name, priority in cached:
                provider = self._providers.get(name)
                if provider:
                    resources.append(provider)
            return resources
        
        # Discover resources by checking each provider
        for provider in self._providers.values():
            if self._check_package_availability(package, provider, context):
                resources.append(provider)
        
        # Cache the discovery for 1 hour
        if resources:
            cache_data = [(r.name, r.priority) for r in resources]
            self._set_discovery_cache(cache_key, cache_data, ttl=3600)
        
        return resources
    
    def _check_package_availability(
        self, 
        package: str, 
        provider: ResourceProvider,
        context: Optional[dict] = None
    ) -> bool:
        """Check if a package is available on a specific provider."""
        try:
            if provider.name == "apt":
                # Check via apt-cache
                result = self._run_command(["apt-cache", "show", package], timeout=10)
                return result.returncode == 0
                
            elif provider.name == "snap":
                # Check via snap info
                result = self._run_command(["snap", "info", package], timeout=10)
                return result.returncode == 0
                
            elif provider.name == "flatpak":
                # Check via flatpak search
                result = self._run_command(
                    ["flatpak", "remote-list", "--app"], 
                    timeout=10
                )
                return package in result.stdout
                
            elif provider.name == "github":
                # Check GitHub API for releases
                if provider.github_owner and provider.github_repo:
                    import requests
                    try:
                        url = f"https://api.github.com/repos/{provider.github_owner}/{provider.github_repo}/releases/latest"
                        response = requests.get(url, timeout=10)
                        return response.status_code == 200
                    except Exception:
                        return False
                return False
                
            elif provider.name == "ppa":
                # Check if PPA repo is configured
                import os
                ppa_dir = "/etc/apt/sources.list.d"
                if os.path.exists(ppa_dir):
                    for filename in os.listdir(ppa_dir):
                        if package in filename:
                            return True
                return False
                
        except Exception:
            return False
        
        return False
    
    def _run_command(
        self, 
        cmd: list[str], 
        timeout: int = 30,
        sudo: bool = False
    ):
        """Run a command with timeout."""
        import subprocess
        if sudo:
            cmd = ["sudo", "-n"] + cmd
        
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            result = subprocess.CompletedProcess(cmd, 1, "", "Command timed out")
            result.returncode = 1
            return result
    
    def _get_discovery_cache(self, key: str) -> Optional[list]:
        """Get cached discovery results."""
        cache_file = self._get_cache_dir() / f"discovery_{key}.json"
        if cache_file.exists():
            import json
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                if time.time() - data.get("timestamp", 0) < data.get("ttl", 3600):
                    return data.get("data")
            except Exception:
                pass
        return None
    
    def _set_discovery_cache(
        self, 
        key: str, 
        data: list, 
        ttl: int = 3600
    ) -> None:
        """Cache discovery results."""
        cache_file = self._get_cache_dir() / f"discovery_{key}.json"
        import json
        import os
        os.makedirs(cache_file.parent, exist_ok=True)
        
        cache_data = {
            "data": data,
            "timestamp": time.time(),
            "ttl": ttl
        }
        with open(cache_file, "w") as f:
            json.dump(cache_data, f)
    
    def _get_cache_dir(self):
        """Get cache directory."""
        from pathlib import Path
        import os
        cache_dir = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser() / "sapt"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir
    
    def select_best_resource(
        self,
        package: str,
        context: Optional[dict] = None,
        preferred_resources: Optional[list[str]] = None,
        force_resource: Optional[str] = None
    ) -> tuple[ResourceProvider | None, str]:
        """Select the best resource for a package considering user preferences and context."""
        # import json not needed here as it's imported locally in _get_discovery_cache and _set_discovery_cache
        
        # If specific resource requested, use it
        if force_resource:
            provider = self._providers.get(force_resource)
            if provider:
                return provider, f"Using explicitly requested resource: {force_resource}"
            return None, f"Requested resource '{force_resource}' not available"

        # Get available resources
        
        # Get available resources
        resources = self.discover_resources_for_package(package, context)
        
        if not resources:
            return None, f"No resources found for package '{package}'"
        
        # Apply resource preferences
        if preferred_resources:
            # Reorder resources based on preference
            resource_names = [r.name for r in resources]
            sorted_resources = []
            
            for pref in preferred_resources:
                if pref in resource_names:
                    idx = resource_names.index(pref)
                    sorted_resources.append(resources[idx])
            
            # Add remaining resources
            for r in resources:
                if r not in sorted_resources:
                    sorted_resources.append(r)
            
            resources = sorted_resources
        
        # Select best resource
        best = resources[0]
        
        # Build explanation
        explanation = f"Selected '{best.name}' resource"
        
        if len(resources) > 1:
            alternatives = [r.name for r in resources[1:5]]
            explanation += f" (alternatives: {', '.join(alternatives)})"
        
        if context and context.get("programming_languages"):
            lang_info = f" [programming: {', '.join(context['programming_languages'])}]"
            explanation += lang_info
        
        return best, explanation
    
    def install_with_fallback(
        self,
        package: str,
        resources: Optional[list[ResourceProvider]] = None,
        context: Optional[dict] = None,
        display: Optional[Display] = None,
        **kwargs
    ) -> tuple[bool, str, list[dict]]:
        """Try to install a package trying multiple resources with fallback."""
        if not display:
            display = self.display
        if not display:
            from sapt.ui.display import Display
            display = Display(no_color=False, quiet=False)
        
        # Get resources if not provided
        if not resources:
            resources = self.discover_resources_for_package(package, context)
        
        if not resources:
            return False, f"No resources available for '{package}'", []
        
        results = []
        success = False
        last_error = ""
        
        display.info(f"Attempting to install '{package}'")
        display.console.print()
        
        for i, provider in enumerate(resources, 1):
            display.console.print(f"[dim]Resource {i}/{len(resources)}: [{provider.name}][/]")
            
            result = self._try_install_resource(package, provider, context, display, **kwargs)
            results.append(result)
            
            if result["success"]:
                success = True
                display.success(f"Successfully installed '{package}' from {provider.name}!")
                break
            else:
                last_error = result.get("error", "Unknown error")
                display.warning(f"Failed from {provider.name}: {last_error[:100]}...")
                display.console.print()
        
        if not success:
            display.error(f"Failed to install '{package}'")
            if len(results) > 1:
                display.info("Tried multiple resources. Consider installing manually.")
            display.console.print()
            display.console.print("[dim]Resources tried:[/]")
            for result in results:
                status = "✓" if result["success"] else "✗"
                display.console.print(f"  {status} {result.get('resource', 'unknown')}: {result.get('error', 'success')[:80]}")
        
        return success, last_error, results
    
    def _try_install_resource(
        self,
        package: str,
        provider: ResourceProvider,
        context: Optional[dict],
        display: Display,
        **kwargs
    ) -> dict:
        """Try to install from a specific resource."""
        result = {
            "resource": provider.name,
            "success": False,
            "error": "",
            "command": ""
        }
        
        try:
            if provider.name == "apt":
                from sapt.execution.apt import AptBackend
                apt = AptBackend()
                result["command"] = f"sudo apt install -y {package}"
                apt.install(package)
                result["success"] = apt.is_installed(package)
                
            elif provider.name == "snap":
                from sapt.execution.snap import SnapBackend  # We'll create this
                snap = SnapBackend()
                result["command"] = f"snap install {package}"
                snap.install(package)
                result["success"] = True
                
            elif provider.name == "flatpak":
                from sapt.execution.flatpak import FlatpakBackend  # We'll create this
                flatpak = FlatpakBackend()
                result["command"] = f"flatpak install -y {package}"
                flatpak.install(package)
                result["success"] = True
                
            elif provider.name == "github":
                from sapt.execution.github import GitHubBackend
                github = GitHubBackend()
                
                # Get GitHub-specific details from context or provider
                owner = provider.github_owner or (context or {}).get("github_owner")
                repo = provider.github_repo or (context or {}).get("github_repo")
                
                if not owner or not repo:
                    result["error"] = "GitHub package requires owner/repo information"
                    return result
                
                result["command"] = f"GitHub: {owner}/{repo}"
                release = github.install(owner, repo, package, **kwargs)
                result["success"] = bool(release)
                
            else:
                result["error"] = f"Unsupported resource type: {provider.name}"
                
        except Exception as e:
            result["error"] = str(e)
        
        return result


def get_resource_for_package(
    package: str,
    context: Optional[dict] = None
) -> tuple[Optional[str], str]:
    """Convenience function to get the best resource for a package.
    
    Returns:
        Tuple of (resource_name, explanation)
    """
    from sapt.ui.display import Display
    
    manager = ResourceManager()
    
    # Register default providers
    manager.register_provider(ResourceProvider(
        name="apt",
        priority=1,
        description="Official APT repositories"
    ))
    
    manager.register_provider(ResourceProvider(
        name="snap",
        priority=2,
        description="Snap packages"
    ))
    
    manager.register_provider(ResourceProvider(
        name="flatpak",
        priority=2,
        description="Flatpak packages"
    ))
    
    manager.register_provider(ResourceProvider(
        name="github",
        priority=4,
        description="GitHub releases"
    ))
    
    # Add GitHub-specific packages to context
    if context is None:
        context = {}
    
    # Add common GitHub patterns
    github_packages = {
        "git": ("git", "git"),
        "docker": ("docker", "docker-ce"),
        "node": ("nodejs", "node"),
        "python": ("python", "cpython"),
        "rust": ("rust-lang", "rust"),
        "go": ("golang", "go"),
        "postgresql": ("postgres", "postgres"),
        "redis": ("redis", "redis"),
        "nginx": ("nginx", "nginx"),
        "mysql": ("mysql", "mysql-server"),
    }
    
    if package in github_packages:
        owner, repo = github_packages[package]
        context["github_owner"] = owner
        context["github_repo"] = repo
    
    resource, explanation = manager.select_best_resource(
        package, 
        context=context
    )
    
    if resource:
        return resource.name, explanation
    return None, explanation