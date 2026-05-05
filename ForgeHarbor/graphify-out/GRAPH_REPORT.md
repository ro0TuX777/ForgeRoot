# Graph Report - .  (2026-05-04)

## Corpus Check
- Corpus is ~12,315 words - fits in a single context window. You may not need a graph.

## Summary
- 336 nodes · 839 edges · 9 communities detected
- Extraction: 32% EXTRACTED · 53% INFERRED · 0% AMBIGUOUS · INFERRED: 448 edges (avg confidence: 0.54)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]

## God Nodes (most connected - your core abstractions)
1. `EnvironmentStatus` - 71 edges
2. `EnvironmentSpec` - 50 edges
3. `PoolManager` - 49 edges
4. `DockerProvider` - 46 edges
5. `MockProvider` - 43 edges
6. `ExecutionEnvironment` - 40 edges
7. `ForgeHarborDaemon` - 37 edges
8. `EnvironmentProvider` - 34 edges
9. `HealthStatus` - 30 edges
10. `ConnectionInfo` - 30 edges

## Surprising Connections (you probably didn't know these)
- `Check if Docker is available for integration tests.` --uses--> `DockerProvider`  [INFERRED]
  tests\test_integration.py → docker_provider.py
- `setUpClass()` --calls--> `DockerProvider`  [INFERRED]
  tests\test_integration.py → docker_provider.py
- `Test ASSIGNED stays ASSIGNED when blocking intents exist` --uses--> `EnvironmentStatus`  [INFERRED]
  tests\test_lifecycle_engine.py → forgeharbor_types.py
- `ForgeHarborDaemon` --uses--> `PoolManager`  [INFERRED]
  daemon.py → pool_manager.py
- `ForgeHarborDaemon` --uses--> `HeartbeatMonitor`  [INFERRED]
  daemon.py → heartbeat_monitor.py

## Hyperedges (group relationships)
- **ForgeHarbor Runtime Components** — forge_harbor_daemon_class, pool_manager_class, lifecycle_state_machine, heartbeat_monitor_class, environment_provider_contract [1.0]
- **EnvironmentProvider Implementations** — environment_provider_contract, docker_provider_class, mock_provider_class [1.0]
- **ForgeHarbor QA Surface** — test_lifecycle_engine, test_pool_manager, test_heartbeat_monitor, test_daemon, test_docker_provider, test_integration [1.0]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.09
Nodes (39): ABC, EnvironmentProvider, DockerProvider, Docker implementation of EnvironmentProvider using Docker SDK., Provision a new Docker container for the environment., Check the health of the Docker container., Stop and remove the Docker container., Get connection information for the container. (+31 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (44): ExecutionEnvironment, assign(), begin_drain(), can_transition(), _create_error(), get_blocking_intents(), on_drain_complete(), on_provision_failure() (+36 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (40): Handle shutdown signals., Background pool reconciliation loop., Request an execution environment for a session., Signal that a session is done with an environment., Main daemon process for ForgeHarbor warm pool management., Query current status of a specific environment., Start the daemon with background loops., Graceful shutdown: drain environments, terminate containers, clean exit. (+32 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (62): ForgeHarbor AI Developer Briefing, assign, begin_drain, can_transition, CONCORD Integration, ForgeHarbor Environment Configuration, ConnectionInfo, ForgeHarbor Core Specification (+54 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (20): ForgeHarborDaemon, get_pool_status returns pool information., health() returns daemon health., Shutdown stops background loops., Daemon starts, initializes pool, starts loops., Shutdown terminates all containers., request_environment works through daemon., release_environment works through daemon. (+12 more)

### Community 5 - "Community 5"
Cohesion: 0.33
Nodes (6): docker_provider.py, Docker Socket Deployment, heartbeat_monitor.py, ForgeHarbor Implementation Plan, lifecycle_engine.py, pool_manager.py

### Community 6 - "Community 6"
Cohesion: 0.7
Nodes (4): Enum, EnvironmentClass, IsolationLevel, ProvisioningStatus

### Community 9 - "Community 9"
Cohesion: 1.0
Nodes (1): ForgeHarborDaemon.get_environment_status

### Community 10 - "Community 10"
Cohesion: 1.0
Nodes (1): provider.py

## Knowledge Gaps
- **5 isolated node(s):** `Specification for provisioning an execution environment.`, `Start a new environment. Returns when container is running (not necessarily read`, `Check if the environment's container is running and responsive.`, `Stop and remove the environment's container.`, `Return how to reach the environment (e.g., container ID, IP, mount paths).`
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 9`** (1 nodes): `ForgeHarborDaemon.get_environment_status`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 10`** (1 nodes): `provider.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `EnvironmentStatus` connect `Community 2` to `Community 1`, `Community 4`, `Community 6`?**
  _High betweenness centrality (0.212) - this node is a cross-community bridge._
- **Why does `ForgeHarborDaemon` connect `Community 4` to `Community 0`, `Community 2`?**
  _High betweenness centrality (0.115) - this node is a cross-community bridge._
- **Why does `EnvironmentSpec` connect `Community 0` to `Community 1`, `Community 2`?**
  _High betweenness centrality (0.106) - this node is a cross-community bridge._
- **Are the 69 inferred relationships involving `EnvironmentStatus` (e.g. with `HeartbeatMonitor` and `Mock - sets status to UNHEALTHY`) actually correct?**
  _`EnvironmentStatus` has 69 INFERRED edges - model-reasoned connections that need verification._
- **Are the 48 inferred relationships involving `EnvironmentSpec` (e.g. with `DockerProvider` and `Docker implementation of EnvironmentProvider using Docker SDK.`) actually correct?**
  _`EnvironmentSpec` has 48 INFERRED edges - model-reasoned connections that need verification._
- **Are the 41 inferred relationships involving `PoolManager` (e.g. with `ForgeHarborDaemon` and `Main daemon process for ForgeHarbor warm pool management.`) actually correct?**
  _`PoolManager` has 41 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `DockerProvider` (e.g. with `ForgeHarborDaemon` and `Main daemon process for ForgeHarbor warm pool management.`) actually correct?**
  _`DockerProvider` has 38 INFERRED edges - model-reasoned connections that need verification._