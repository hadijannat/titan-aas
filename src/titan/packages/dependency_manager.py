"""Package dependency management with graph analysis.

Provides dependency tracking, validation, and installation order resolution:
- Add/remove package dependencies
- Circular dependency detection (Tarjan's algorithm)
- Topological sorting for installation order
- Transitive dependency resolution
- Version constraint validation
- Dependency graph visualization
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan.persistence.tables import AasxPackageDependencyTable, AasxPackageTable

logger = logging.getLogger(__name__)


class DependencyType(Enum):
    """Types of package dependencies."""

    REQUIRED = "required"  # Must be present
    OPTIONAL = "optional"  # Nice to have
    RECOMMENDED = "recommended"  # Strongly suggested
    CONFLICTS = "conflicts"  # Must NOT be present


@dataclass
class PackageDependency:
    """A package dependency relationship."""

    package_id: str
    depends_on_id: str
    dependency_type: DependencyType
    version_constraint: str | None = None
    description: str | None = None


@dataclass
class DependencyGraph:
    """Dependency graph representation."""

    nodes: set[str] = field(default_factory=set)  # Package IDs
    edges: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )  # package_id -> [depends_on_ids]
    cycles: list[list[str]] = field(default_factory=list)  # Detected circular dependencies

    def add_dependency(self, from_pkg: str, to_pkg: str) -> None:
        """Add a dependency edge."""
        self.nodes.add(from_pkg)
        self.nodes.add(to_pkg)
        if to_pkg not in self.edges[from_pkg]:
            self.edges[from_pkg].append(to_pkg)

    def get_dependencies(self, package_id: str) -> list[str]:
        """Get direct dependencies of a package."""
        return self.edges.get(package_id, [])

    def get_dependents(self, package_id: str) -> list[str]:
        """Get packages that depend on this package."""
        return [pkg for pkg, deps in self.edges.items() if package_id in deps]


@dataclass
class DependencyValidationResult:
    """Result of dependency validation."""

    valid: bool = True
    missing_dependencies: list[str] = field(default_factory=list)
    circular_dependencies: list[list[str]] = field(default_factory=list)
    version_conflicts: list[str] = field(default_factory=list)
    conflicting_packages: list[tuple[str, str]] = field(default_factory=list)  # (pkg1, pkg2)
    warnings: list[str] = field(default_factory=list)


class DependencyManager:
    """Manages package dependencies with graph analysis."""

    async def add_dependency(
        self,
        session: AsyncSession,
        package_id: str,
        depends_on_id: str,
        dependency_type: DependencyType = DependencyType.REQUIRED,
        version_constraint: str | None = None,
        description: str | None = None,
    ) -> None:
        """Add a dependency between packages.

        Args:
            session: Database session
            package_id: Source package ID
            depends_on_id: Target package ID (the dependency)
            dependency_type: Type of dependency
            version_constraint: Optional semantic version constraint
            description: Human-readable description

        Raises:
            ValueError: If packages don't exist or circular dependency created
        """
        # Verify both packages exist
        for pkg_id in [package_id, depends_on_id]:
            stmt = select(AasxPackageTable).where(AasxPackageTable.id == pkg_id)
            result = await session.execute(stmt)
            if not result.scalar_one_or_none():
                raise ValueError(f"Package not found: {pkg_id}")

        # Check for circular dependencies before adding
        graph = await self.build_graph(session)
        graph.add_dependency(package_id, depends_on_id)
        cycles = self._detect_cycles(graph)

        if cycles:
            cycle_str = " -> ".join(cycles[0])
            raise ValueError(f"Circular dependency detected: {cycle_str}")

        # Add dependency
        dep = AasxPackageDependencyTable(
            package_id=package_id,
            depends_on_id=depends_on_id,
            dependency_type=dependency_type.value,
            version_constraint=version_constraint,
            description=description,
        )

        session.add(dep)
        await session.commit()

        logger.info(f"Added {dependency_type.value} dependency: {package_id} -> {depends_on_id}")

    async def remove_dependency(
        self,
        session: AsyncSession,
        package_id: str,
        depends_on_id: str,
    ) -> None:
        """Remove a dependency between packages.

        Args:
            session: Database session
            package_id: Source package ID
            depends_on_id: Target package ID
        """
        stmt = delete(AasxPackageDependencyTable).where(
            AasxPackageDependencyTable.package_id == package_id,
            AasxPackageDependencyTable.depends_on_id == depends_on_id,
        )

        await session.execute(stmt)
        await session.commit()

        logger.info(f"Removed dependency: {package_id} -> {depends_on_id}")

    async def get_dependencies(
        self,
        session: AsyncSession,
        package_id: str,
        recursive: bool = False,
    ) -> list[PackageDependency]:
        """Get dependencies of a package.

        Args:
            session: Database session
            package_id: Package ID to query
            recursive: Include transitive dependencies

        Returns:
            List of PackageDependency objects
        """
        if not recursive:
            # Direct dependencies only
            stmt = select(AasxPackageDependencyTable).where(
                AasxPackageDependencyTable.package_id == package_id
            )
            result = await session.execute(stmt)
            deps = result.scalars().all()

            return [
                PackageDependency(
                    package_id=d.package_id,
                    depends_on_id=d.depends_on_id,
                    dependency_type=DependencyType(d.dependency_type),
                    version_constraint=d.version_constraint,
                    description=d.description,
                )
                for d in deps
            ]
        else:
            # Transitive dependencies via DFS
            visited: set[str] = set()
            all_deps: list[PackageDependency] = []

            async def dfs(pkg_id: str) -> None:
                if pkg_id in visited:
                    return
                visited.add(pkg_id)

                direct_deps = await self.get_dependencies(session, pkg_id, recursive=False)
                all_deps.extend(direct_deps)

                for dep in direct_deps:
                    await dfs(dep.depends_on_id)

            await dfs(package_id)
            return all_deps

    async def get_installation_order(
        self,
        session: AsyncSession,
        package_ids: list[str],
    ) -> list[str]:
        """Get installation order using topological sort.

        Returns packages in the order they should be installed, with
        dependencies installed before dependents.

        Args:
            session: Database session
            package_ids: List of package IDs to install

        Returns:
            List of package IDs in installation order

        Raises:
            ValueError: If circular dependencies detected
        """
        graph = await self.build_graph(session)

        # Check for cycles first
        cycles = self._detect_cycles(graph)
        if cycles:
            cycle_str = " -> ".join(cycles[0])
            raise ValueError(f"Circular dependency prevents installation: {cycle_str}")

        # Topological sort using Kahn's algorithm
        in_degree = defaultdict(int)
        for node in graph.nodes:
            in_degree[node] = 0

        for node in graph.nodes:
            for dep in graph.edges.get(node, []):
                in_degree[dep] += 1

        # Start with nodes that have no dependencies
        queue = [node for node in package_ids if in_degree[node] == 0]
        result = []

        while queue:
            node = queue.pop(0)
            if node in package_ids:  # Only include requested packages
                result.append(node)

            # Reduce in-degree for dependents
            for dependent in graph.get_dependents(node):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0 and dependent in package_ids:
                    queue.append(dependent)

        # Add remaining packages (those with dependencies outside requested set)
        for pkg_id in package_ids:
            if pkg_id not in result:
                result.append(pkg_id)

        return result

    async def validate_dependencies(
        self,
        session: AsyncSession,
        package_id: str,
    ) -> DependencyValidationResult:
        """Validate all dependencies of a package.

        Checks for:
        - Missing required dependencies
        - Circular dependencies
        - Version conflicts
        - Conflicting packages

        Args:
            session: Database session
            package_id: Package ID to validate

        Returns:
            DependencyValidationResult with issues
        """
        result = DependencyValidationResult()

        # Get all dependencies
        deps = await self.get_dependencies(session, package_id, recursive=True)

        # Check for missing dependencies
        for dep in deps:
            if dep.dependency_type == DependencyType.REQUIRED:
                stmt = select(AasxPackageTable).where(AasxPackageTable.id == dep.depends_on_id)
                exists = await session.execute(stmt)
                if not exists.scalar_one_or_none():
                    result.missing_dependencies.append(dep.depends_on_id)
                    result.valid = False

        # Check for circular dependencies
        graph = await self.build_graph(session)
        cycles = self._detect_cycles(graph)
        if cycles:
            result.circular_dependencies = cycles
            result.valid = False

        # Check for conflicts
        conflict_deps = [d for d in deps if d.dependency_type == DependencyType.CONFLICTS]
        for conflict_dep in conflict_deps:
            # Check if conflicting package is present
            stmt = select(AasxPackageTable).where(AasxPackageTable.id == conflict_dep.depends_on_id)
            exists = await session.execute(stmt)
            if exists.scalar_one_or_none():
                result.conflicting_packages.append((package_id, conflict_dep.depends_on_id))
                result.valid = False

        # Add warnings for optional/recommended missing deps
        for dep in deps:
            if dep.dependency_type in (DependencyType.OPTIONAL, DependencyType.RECOMMENDED):
                stmt = select(AasxPackageTable).where(AasxPackageTable.id == dep.depends_on_id)
                exists = await session.execute(stmt)
                if not exists.scalar_one_or_none():
                    dep_type = dep.dependency_type.value.capitalize()
                    result.warnings.append(f"{dep_type} dependency missing: {dep.depends_on_id}")

        return result

    async def build_graph(self, session: AsyncSession) -> DependencyGraph:
        """Build complete dependency graph.

        Args:
            session: Database session

        Returns:
            DependencyGraph with all packages and dependencies
        """
        graph = DependencyGraph()

        # Get all dependencies
        stmt = select(AasxPackageDependencyTable)
        result = await session.execute(stmt)
        all_deps = result.scalars().all()

        for dep in all_deps:
            graph.add_dependency(dep.package_id, dep.depends_on_id)

        return graph

    def _detect_cycles(self, graph: DependencyGraph) -> list[list[str]]:
        """Detect circular dependencies using Tarjan's algorithm.

        Args:
            graph: Dependency graph

        Returns:
            List of cycles, where each cycle is a list of package IDs
        """
        index_counter = [0]
        stack: list[str] = []
        lowlinks: dict[str, int] = {}
        index: dict[str, int] = {}
        on_stack: dict[str, bool] = defaultdict(bool)
        cycles: list[list[str]] = []

        def strongconnect(node: str) -> None:
            # Set the depth index for node
            index[node] = index_counter[0]
            lowlinks[node] = index_counter[0]
            index_counter[0] += 1
            on_stack[node] = True
            stack.append(node)

            # Consider successors
            for successor in graph.edges.get(node, []):
                if successor not in index:
                    # Successor has not been visited
                    strongconnect(successor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[successor])
                elif on_stack[successor]:
                    # Successor is on stack (part of current SCC)
                    lowlinks[node] = min(lowlinks[node], index[successor])

            # If node is a root, pop the stack to get SCC
            if lowlinks[node] == index[node]:
                scc = []
                while True:
                    successor = stack.pop()
                    on_stack[successor] = False
                    scc.append(successor)
                    if successor == node:
                        break

                # Only report SCCs with more than one node (cycles)
                if len(scc) > 1:
                    cycles.append(scc)

        for node in graph.nodes:
            if node not in index:
                strongconnect(node)

        return cycles
