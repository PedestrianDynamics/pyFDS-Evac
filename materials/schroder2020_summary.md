The paper "A map representation of the ASET-RSET concept" by Schröder et al. (2020) provides a technical advancement in performance-based fire safety design by transitioning from traditional punctual (single-point) analysis to a high-fidelity **spatial and temporal map representation**,. 

### **1. Principal Findings**
The authors identify that traditional ASET-RSET assessments, which evaluate safety criteria at only a few selected locations, are prone to **incompleteness and misinterpretation**. Key findings include:
*   **Identification of Distributed Hazards:** ASET and RSET are inherently distributed values; single-point evaluations fail to ensure that the safety margin (ASET minus RSET) is positive at every location in a building,.
*   **Visualization of Critical Regions:** The introduction of **Difference Maps** allows for the immediate identification of "hot spots" where the ASET-RSET constraint is violated, showing both where and for how long occupants were exposed to unacceptable conditions,.
*   **Complexity Reduction for Risk Analysis:** The paper demonstrates that a high-information spatial analysis can be reduced to a single **scalar measure of consequences ($C$)**, facilitating the comparison and ranking of thousands of scenario combinations in multivariate studies,.
*   **Independence of Coupling:** The methodology allows for the analysis of independent fire and evacuation model outputs in a post-processing stage, removing the absolute requirement for "online" bidirectional coupling during execution,.

### **2. Algorithmic Framework**
The core innovation lies in the formal mathematical discretisation of the building floor plan into map elements ($M$), enabling the following algorithmic steps:

#### **A. ASET Map Generation**
The algorithm identifies the first point in time at each map element when fire effects reach a critical threshold:
*   **Criterion:** For each map element at $(x_m, y_m)$, it samples a set of data points $X_m$ from CFD results (e.g., FDS slices).
*   **Calculation:** The available time for that element is the minimum time across all thresholds $i$ reached in that specific area:
    $$ASET_m = \min \left( \bigcup Tm,i \right)$$
    This results in a "fingerprint" of the fire scenario across the entire domain,.

#### **B. RSET Map Generation**
This process transforms agent-based movement data into a space-related interpretation of required time:
*   **Trajectory Analysis:** Every individual agent trajectory $p_i(t)$ is evaluated.
*   **Calculation:** A map element is assigned the maximum time point of all trajectories that passed through its area:
    $$RSET_m = \max \left( \bigcup Tm,i \right)$$
    This maps the "required" time to every point on the floor plan traversed by occupants.

#### **C. Difference Maps and Safety Margin**
The spatial safety margin is computed via element-wise subtraction:
$$DIFF_m = ASET_m - RSET_m$$
Negative values in this matrix indicate areas where the limiting state was exceeded (occupants were present in untenable conditions).

#### **D. Consequence Quantification Algorithm ($C$)**
To characterize the severity of a scenario, the authors propose a metric inspired by the **Earth Mover’s Distance (EMD)** or Wasserstein metric:
*   **Histogram Transformation:** The distribution of $ASET-RSET$ values is converted into a histogram.
*   **The $C$ Measure:** The total consequence is the sum of the products of bin centers ($t_k$) and their corresponding areas ($a_k$) for all negative values:
    $$C = \sum_{k|t_k<0} t_k \cdot a_k$$
    This scalar provides a robust measure that combines the **spatial extent** and **temporal duration** of a safety violation into a single value for risk assessment,.
