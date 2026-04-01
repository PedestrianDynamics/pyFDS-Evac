The thesis "A knowledge-based routing framework for pedestrian dynamics simulation" by David Haensel (2014) focuses on developing a modular wayfinding framework that emulates individual human cognition and perception within agent-based simulations. The work moves beyond simple shortest-path heuristics by implementing a **cognitive map** for each agent to support decision-making based on varying levels of building knowledge.

### 1. The Knowledge Representation: Navigation Graphs
The core of the wayfinding framework is the **Navigation Graph**, a directed weighted graph where architectural sub-rooms are identified as vertices and doors or intersections are identified as edges. This structure provides several algorithmic advantages for high-fidelity modeling:
*   **Directional Information:** It allows storing different information for different edge directions (e.g., leaving a room toward a corridor is rated better than entering a room from a corridor).
*   **Knowledge Hierarchies:** Spatial knowledge is classified into **First-order** (the existence of rooms and doors) and **Second-order** (dynamic properties such as smoke density or crowd pressure).
*   **Memory of Used Routes:** A secondary component of the cognitive map stores every chosen edge in order, allowing the agent to reconstruct its path and avoid immediate backward oscillations.

### 2. Wayfinding Algorithms
The framework distinguishes between agents with complete building knowledge and those who must explore the environment locally.

#### **A. Global Wayfinding (Modified Dijkstra)**
For agents with sufficient knowledge to find a complete exit route, the model utilizes a **modified Dijkstra algorithm**.
*   **Path-Integrated Distance Logic:** Traditional algorithms often underestimate or overestimate distances. Haensel’s algorithm calculates the exact distance an agent travels by considering its expected entry position from the preceding sub-room.
*   **Edge-Based Discovery:** To account for varying entry points and multiple connections between rooms, the algorithm discovers **new edges** instead of vertices. It calculates the cheapest path from a vertex to a set of exit edges ($EE$).
*   **Composite Edge Weights:** The weight ($w_i$) of an edge is the product of its physical length ($x_i$) and an accumulated edge-factor ($f(i)$) derived from environmental stressors.

#### **B. Local Wayfinding (Discovery Mode)**
When no global route to an exit is known, agents revert to a local algorithm that relies on visible intersections of the current sub-room.
*   **Factor-Based Screening:** The agent first compares the "accumulated edge factors" (e.g., smoke status, congestion) of all known intersecting edges.
*   **Distance Optimization:** After identifying a set of edges with favorable factors (using an upper bound of double the smallest factor), the agent selects the one with the shortest distance to pursue.

### 3. Sensor-Driven Environmental Coupling
Information gathering is managed by an event-driven **SensorManager**, which couples physical fire phenomena with cognitive decision-making.
*   **`SmokeSensor`:** Dynamically raises the edge-factors of paths heading into smoked sub-rooms, encouraging agents to seek detours.
*   **`DensitySensor`:** Measures crowd density in front of doors to avoid jams, significantly reducing total evacuation time in bottleneck scenarios like T-junctions.
*   **`RoomToCorridorSensor`:** Implements a cognitive heuristic where agents prioritize corridors over normal rooms as likely paths to safety.

### 4. Principal Findings
*   **Cognitive Realism vs. Shortest Path:** The research finds that purely shortest-path routers (global) result in unrealistic congestions at corners and doors, whereas knowledge-based agents distribute themselves more effectively based on perceived conditions.
*   **Mandatory Discovery Heuristics:** In simulations with "empty" cognitive maps, the `LastDestinationsSensor` and `DiscoverDoorsSensor` are technically mandatory to prevent agents from oscillating at doors or remaining stationary.
*   **Calibration Complexity:** A key finding is that as the number of sensors increases, calibration becomes exponentially difficult because the user must decide which environmental stressor (e.g., smoke vs. congestion) takes precedence in the composite weight.
*   **The Information Sharing Gap:** Haensel identifies that current models often miss the unrealistic nature of agents not sharing information; in reality, a single agent's discovery of a smoked room should propagate through a group to avoid redundant individual discoveries.
