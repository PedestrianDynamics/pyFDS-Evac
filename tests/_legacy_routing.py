"""Frozen copy of the rerouting decision code at 7a3617d, for issue #187.

Stage 1 of #187 restructures ``evaluate_route``, ``rank_routes``,
``_must_flee_rejection``, ``_anchor_allows``, ``_adoptable`` and
``evaluate_and_reroute`` without changing a single result.
``test_routing_refactor_equivalence.py`` runs this copy and the live module on
the same inputs and requires exactly equal outputs.

The six functions below are verbatim copies. The only edit is that the two
in-function imports from ``.cognitive_map`` are absolute, because this module
is not inside the package. Everything they call that the refactor does
not touch is imported from the live module, so the copy and the live code
share their primitives. The six names resolve to one another inside this
module, never to the live module. Delete this file when stage 1 is complete.
"""

from __future__ import annotations

from dataclasses import replace

from pyfds_evac.core.route_graph import (
    _PATH_IMPROVEMENT_THRESHOLD,
    AgentRouteState,
    ExtinctionSampler,
    FedRateSampler,
    RerouteConfig,
    RouteCost,
    RouteCostConfig,
    RouteSwitch,
    SegmentCacheKey,
    SegmentCost,
    StageGraph,
    _arrival_time,
    _polyline_stats,
    _position_aware_length,
    _reconstruct_committed_path,
    _walkable_waypoints,
    evaluate_segment,
    reroute_agent,
)


def evaluate_route(
    graph: StageGraph,
    path: list[str],
    time_s: float,
    current_fed: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
    *,
    cached_segments: dict[SegmentCacheKey, SegmentCost] | None = None,
    exit_counts: dict[str, int] | None = None,
    current_exit: str | None = None,
    agent_position: tuple[float, float] | None = None,
    current_target: str | None = None,
) -> RouteCost:
    """Evaluate the composite cost for a full route (list of stage IDs).

    When ``agent_position`` is given, the distance is measured from where the
    agent actually is (Haensel 2014 "path-integrated distance") instead of from
    the route's first graph node, so an agent 1 m from one exit is not priced as
    if standing at the far upstream junction. Every route is measured the same
    way, whatever the agent is currently heading for -- see
    ``_position_aware_length``. The smoke and FED terms are credited over the
    same stretch as the distance, so exposure already incurred on the traversed
    part -- and already carried in ``current_fed`` -- is not charged a second
    time.

    ``current_target`` is accepted and ignored; it is kept so callers that
    already thread it through do not have to change, and so the parameter is
    available if a future rule needs the agent's heading.
    """
    segments: list[SegmentCost] = []
    walked = 0.0
    for i in range(len(path) - 1):
        cache_key = (path[i], path[i + 1])
        # With anticipation an edge costs what it costs *when you get there*,
        # so the same edge on two routes is two different questions and the
        # cache has to key on both. Bucketed to the second: finer than the
        # reroute interval, coarser than nothing, and well under the interval
        # FDS writes slices at.
        t_arrive = _arrival_time(time_s, walked, config)
        if config.anticipate:
            cache_key = (path[i], path[i + 1], round(t_arrive))
        if cached_segments is not None and cache_key in cached_segments:
            seg = cached_segments[cache_key]
        else:
            seg = evaluate_segment(
                graph,
                path[i],
                path[i + 1],
                time_s,
                extinction_sampler,
                fed_rate_sampler,
                config,
                arrival_time_s=t_arrive,
            )
            if cached_segments is not None:
                cached_segments[cache_key] = seg
        segments.append(seg)
        walked += seg.length_m

    path_length = sum(s.length_m for s in segments)

    # Position-aware distance (Haensel path-integrated). Default: the geometric
    # node-to-node path_length (used everywhere agent_position is absent).
    effective_length = path_length
    first_share = 1.0
    # The walk from the agent to the next node, through the walkable area. It
    # measures the first leg here and is resampled for smoke below.
    first_waypoints = None
    if agent_position is not None and len(path) >= 2:
        next_node = graph.nodes.get(path[1])
        if next_node is not None:
            first_waypoints = _walkable_waypoints(
                graph.routing_engine,
                agent_position,
                (next_node.centroid_x, next_node.centroid_y),
            )
        effective_length, first_share = _position_aware_length(
            graph,
            path,
            agent_position,
            path_length,
            segments[0].length_m,
            first_waypoints,
        )

    # Exposure is accumulated over the same stretch the distance term charges:
    # the smoke and FED the agent already took on the traversed part of the first
    # segment are in current_fed, so charging the full segment would count them
    # twice and inflate the FED and smoke terms of a route it is midway along.
    shares = [first_share] + [1.0] * (len(segments) - 1)
    weighted = list(zip(shares, segments))
    exposure_length = sum(w * s.length_m for w, s in weighted)
    total_k_samples = sum(w * s.k_avg * s.length_m for w, s in weighted)
    k_ave = total_k_samples / exposure_length if exposure_length > 1e-9 else 0.0
    travel_time = sum(w * s.travel_time_s for w, s in weighted)
    # The share is capped at 1, so an agent behind the route's origin node
    # would be timed over the node legs alone and not the walk to the origin.
    # That stretch is timed at the route's mean pace, the same assumption
    # tau = K_ave * effective_length makes about its extinction. Only ever a
    # stretch, never a shrink, so an impassable route stays infinite.
    if effective_length > exposure_length > 1e-9:
        travel_time *= effective_length / exposure_length
    fed_growth = sum(w * s.fed_growth for w, s in weighted)
    fed_max = current_fed + fed_growth
    # The worst point on the route, not its average: a route is refused because
    # of the wall of smoke in it, and a mean over 30 clear metres and 3 blind
    # ones reports a walk anyone would take.
    #
    # The first segment is resampled from where the agent stands, because the
    # rest of it is behind them. Taking the whole segment would gate every route
    # through that node on smoke already walked through -- and only the agent's
    # *current* route has a partly-traversed first leg, so the error falls on
    # the committed route alone and pushes the agent off it. Deliberately not
    # written to cached_segments: those entries are shared between agents in one
    # pass and this stretch belongs to one agent's position.
    first_k_max = segments[0].k_max if segments else 0.0
    first_k_avg = segments[0].k_avg if segments else 0.0
    # Resampled for every route, not only the one the agent is walking. The
    # share is clamped at 1.0, so a route the agent has diverged from is
    # otherwise charged its whole first leg including the stretch behind the
    # agent -- and with a binary clean test that asymmetry decided membership:
    # an agent past a smoke blob read its committed route as clean and every
    # rival as dirty, on smoke none of them would walk through.
    #
    # Sampled along the walk itself, around walls, at sampling_step_m over its
    # real length -- which, behind the origin node, is longer than the capped
    # first_share of the segment.
    if first_waypoints is not None:
        first_k_avg, first_k_max = _polyline_stats(
            first_waypoints,
            segments[0].arrival_time_s,
            extinction_sampler,
            config.sampling_step_m,
        )
    k_max = max(
        [first_k_max] + [s.k_max for _, s in weighted[1:]],
        default=0.0,
    )
    # The smokiest *leg* of the route, each leg taken as its own mean. Not the
    # route mean: that dilutes a smoky stretch with however much clear corridor
    # follows it, so a long route can look cleaner than a short one by being
    # long -- the mirror of the length penalty this model was built to remove.
    # Not the worst *sample* either, which is the step function that made the
    # sighting distance jump between ticks. FDS+Evac applies its 0.03 /m to
    # K_ave_Door, a per-door average, for the same reason.
    k_leg_max = max(
        [first_k_avg] + [s.k_avg for _, s in weighted[1:]],
        default=0.0,
    )
    # Route optical depth: the soot column still to be walked through, and the
    # whole of the smoke criterion. tau = K_ave * L is the integral of
    # extinction along the path, not the sighting distance it grew out of --
    # Jin's S = c/K measures contrast along a straight unobstructed line to a
    # sign, and integrating K around two corners measures exposure instead. The
    # two coincide only on a straight corridor.
    #
    # The mean rather than the worst sample: a maximum over sampled cells is a
    # step function of where the agent stands, and the same 28.9 m route
    # reported 91 m of sight, then 8 m, then 91 m again on consecutive seconds,
    # taking the ordering with it. k_max_route is still reported and still
    # orders the all-refused fallback, where the question is which walk is
    # survivable rather than which is cleanest.
    tau_route = k_ave * effective_length

    # Composite cost: effective_length * (1 + w_smoke * K_ave) + w_fed * FED_max
    # Under "gate" this is reported but does not rank: see rank_routes.
    composite = (
        effective_length * (1.0 + config.w_smoke * k_ave) + config.w_fed * fed_max
    )

    # Queue cost: convert queue delay to distance-equivalent units.
    queue_time = 0.0
    if exit_counts is not None and config.w_queue > 0 and path:
        _exit_id = path[-1]
        n_exit = exit_counts.get(_exit_id, 0)
        exit_node = graph.nodes.get(_exit_id)
        capacity = (
            exit_node.capacity_agents_per_s
            if exit_node is not None and exit_node.capacity_agents_per_s is not None
            else config.default_exit_capacity
        )
        if capacity > 0:
            queue_time = n_exit / capacity
            queue_distance = config.base_speed_m_per_s * queue_time
            composite += config.w_queue * queue_distance

    # Asymmetric FED rejection (deadband). The agent's current exit keeps the
    # full threshold so it always flees the instant dose crosses incapacitation.
    # A different exit is held to the stricter fed_return_margin fraction, so the
    # agent only switches onto it once its dose is clearly safe — this stops the
    # flip-flop when a marginal route's predicted dose wobbles around 1.0.
    # current_exit=None (e.g. initial choice, or a direct evaluate_route call)
    # falls back to the plain threshold for every route.
    exit_id = path[-1] if path else ""
    is_current = current_exit is not None and exit_id == current_exit
    fed_threshold = config.fed_rejection_threshold
    if not is_current and current_exit is not None:
        fed_threshold *= config.fed_return_margin

    rejected = False
    reason = None
    if fed_max > fed_threshold:
        rejected = True
        reason = f"FED_max {fed_max:.3f} > {fed_threshold:.3f}"

    # Sight gate: FDS+Evac's rule that a door is only a candidate while the
    # agent can see a useful fraction of the way to it (evac.f90,
    # Change_Target_Door). Being relative to distance is what lets the same
    # smoke allow a near exit and refuse a far one.
    #
    # The gate: refuse a route whose optical depth exceeds the budget. A rival
    # exit is held to a stricter budget than the one the agent already walks
    # to, so a route sitting near tau_max does not toggle in and out of the
    # feasible set and take the crowd with it.
    feasible = not rejected
    if config.cost_model == "gate":
        budget = config.tau_max
        if not is_current and current_exit is not None:
            budget *= config.tau_return_margin
        if tau_route > budget:
            feasible = False
            rejected = True
            reason = (
                f"tau {tau_route:.2f} > {budget:.2f} "
                f"(K_ave {k_ave:.3f} x {effective_length:.1f} m)"
            )

    if config.cost_model == "gate":
        # Queue delay is time, so it belongs beside travel time rather than in
        # the composite the gate ignores -- otherwise opting into congestion-
        # aware routing (w_queue) would silently do nothing.
        # One currency: the quantity that refuses a route also ranks it and is
        # what the anchor compares. Ranking on tau while anchoring on time left
        # the two disagreeing, and a separate "clearly cleaner" bypass fired
        # every time the field flickered -- 109 returns to abandoned exits on
        # l_corridor.
        #
        # rank_cost stays a time. tau orders the routes (see rank_routes), but
        # it is zero in clear air, so using it for the anchor's ratio test would
        # make every comparison 0 < 0 -- no agent could ever switch, and a
        # congestion weight would count for nothing exactly where decks
        # calibrate one.
        rank_cost = travel_time + queue_time * config.w_queue
    else:
        rank_cost = composite

    # Tier 1. The exit the agent is already heading for keeps its place in the
    # clean set a little past the criterion, so membership does not flicker.
    clean_limit = config.clean_extinction_threshold
    if is_current:
        clean_limit /= max(config.clean_exit_margin, 1e-9)
    # A zero threshold turns the tier off rather than declaring clear air
    # clean, which would make every route tier 0 and change nothing anyway --
    # but the explicit form says which is meant.
    clean = clean_limit > 0.0 and k_leg_max <= clean_limit

    return RouteCost(
        exit_id=exit_id,
        path=path,
        path_length_m=path_length,
        k_ave_route=k_ave,
        travel_time_s=travel_time,
        fed_max_route=fed_max,
        composite_cost=composite,
        segments=segments,
        rejected=rejected,
        rejection_reason=reason,
        queue_time_s=queue_time,
        k_max_route=k_max,
        tau_route=tau_route,
        feasible=feasible,
        rank_cost=rank_cost,
        k_leg_max=k_leg_max,
        clean=clean,
    )


def rank_routes(
    graph: StageGraph,
    source: str,
    time_s: float,
    current_fed: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RouteCostConfig,
    *,
    cached_segments: dict[SegmentCacheKey, SegmentCost] | None = None,
    exit_counts: dict[str, int] | None = None,
    cognitive_map=None,
    agent_position: tuple[float, float] | None = None,
    current_exit: str | None = None,
    current_target: str | None = None,
) -> list[RouteCost]:
    """Evaluate and rank all routes from *source* to reachable exits.

    Computes dynamic edge weights from current smoke/FED conditions,
    then runs Dijkstra with those weights so pathfinding picks the
    cheapest path under current conditions (not just the geometrically
    shortest).

    Returns routes sorted by composite cost (lowest first).
    Rejected routes are sorted to the end.
    If all routes are rejected, the least-bad route is un-rejected
    as a fallback.
    """
    # Restrict graph to agent's known subgraph (discovery mode).
    if cognitive_map is not None:
        from pyfds_evac.core.cognitive_map import cognitive_subgraph

        graph = cognitive_subgraph(cognitive_map, graph)

    # Phase 1: evaluate all edges to get dynamic costs.
    dynamic_weights: dict[tuple[str, str], float] = {}
    for src_id, edges in graph.edges.items():
        for edge in edges:
            cache_key = (edge.source, edge.target)
            if cached_segments is not None and cache_key in cached_segments:
                seg = cached_segments[cache_key]
            else:
                seg = evaluate_segment(
                    graph,
                    edge.source,
                    edge.target,
                    time_s,
                    extinction_sampler,
                    fed_rate_sampler,
                    config,
                )
                if cached_segments is not None:
                    cached_segments[cache_key] = seg
            # Per-edge cost. Under "gate" this is the edge's own optical
            # depth, the same quantity the routes are ranked and refused on, so
            # the path chosen to reach an exit and the choice between exits are
            # finally one objective. Before this, Dijkstra minimised the
            # additive composite and the exit was then judged on tau, which
            # meant a gate could refuse an exit on a smoky path while a longer
            # passable path to the same exit existed and was never offered.
            #
            # A floor on length keeps a clear-air graph from collapsing to
            # all-zero weights, where every path ties and Dijkstra returns an
            # arbitrary one.
            if config.cost_model == "gate":
                dynamic_weights[cache_key] = seg.k_avg * seg.length_m + 1e-6 * (
                    seg.length_m
                )
            else:
                # Additive decomposition of the composite formula. current_fed
                # is constant across routes for one agent, so omitting it from
                # edge costs does not affect ranking.
                dynamic_weights[cache_key] = (
                    seg.length_m * (1.0 + config.w_smoke * seg.k_avg)
                    + config.w_fed * seg.fed_growth
                )

    # Phase 2: Dijkstra with dynamic weights.
    all_paths = graph.shortest_paths_to_exits(source, dynamic_weights=dynamic_weights)
    if not all_paths:
        return []

    # Phase 3: evaluate full routes (reusing cached segments).
    costs: list[RouteCost] = []
    for exit_id, (_dist, path) in all_paths.items():
        rc = evaluate_route(
            graph,
            path,
            time_s,
            current_fed,
            extinction_sampler,
            fed_rate_sampler,
            config,
            cached_segments=cached_segments,
            exit_counts=exit_counts,
            current_exit=current_exit,
            agent_position=agent_position,
            current_target=current_target,
        )
        costs.append(rc)

    # Sign legibility is not consulted here.  It decides what enters the
    # agent's cognitive map (see cognitive_map.expand_from_visibility), and the
    # map decides what Dijkstra can see -- so an unknown exit is absent from
    # the graph rather than present-and-vetoed.  Checking it again here
    # double-gated the same criterion, blocked agents who already knew the
    # building, and forbade an agent from using an exit it had legitimately
    # learned once the sign went out of view.
    # K_vis fallback: reject routes where all segments are non-visible,
    # but only if at least one other route has visibility.
    #
    # Additive only. Under the gate this was a *second* smoke criterion on top
    # of the sight test, and a bare threshold on K with no hysteresis, so a
    # route sitting near it toggled every tick: measured on world100, a 9 m
    # route with a 2 s travel time was struck out and reinstated repeatedly
    # while the agent bounced to a 27 m rival and back. It also set `rejected`
    # without clearing `feasible`, leaving the two fields disagreeing. The
    # plan retired it under the gate; this is that retirement.
    any_visible = config.cost_model != "gate" and any(
        any(s.visible for s in rc.segments) for rc in costs if not rc.rejected
    )
    if any_visible:
        updated = []
        for rc in costs:
            if not rc.rejected and not any(s.visible for s in rc.segments):
                rc = replace(
                    rc,
                    rejected=True,
                    rejection_reason="all segments non-visible",
                )
            updated.append(rc)
        costs = updated

    # Ordering. Under "additive" the composite decides, as it always has.
    # Under "gate" distance decides among routes that are still available, and
    # a route a whole visibility band clearer wins first: smoke says which
    # exits exist, not how much each metre of them is worth.
    # Ordering. Under "additive" the composite decides, as it always has.
    # Under "gate" the route's optical depth decides and travel time breaks
    # ties: tau = K_ave * L already contains the distance, so two routes
    # through equally thin haze order by length and in clear air every tau is
    # zero and time decides alone. A cleaner route wins only by enough less
    # smoke to pay for its extra metres -- which is the property a visibility
    # band could not have, since a band compared cleanliness with no reference
    # to how far the agent had to carry it.
    order_by_tau = config.cost_model == "gate"

    def tau_of(rc: RouteCost) -> float:
        # The exit the agent already walks to has its optical depth discounted,
        # so it keeps its place unless a rival is clearly cleaner rather than
        # momentarily cleaner. This is FDS+Evac's FAC_DOOR_OLD2 = 0.9
        # (evac.f90:1507), applied at :16467 inside the IF that ranks doors --
        # the same position, not a separate veto afterwards. Hysteresis belongs in the ordering: bolted on after
        # it, the ordering and the veto disagree and the agent oscillates
        # between what each of them prefers.
        if current_exit is not None and rc.exit_id == current_exit:
            return rc.tau_route * config.current_exit_discount
        return rc.tau_route

    prefer_clean = order_by_tau and config.clean_extinction_threshold > 0.0

    def sort_key(rc: RouteCost) -> tuple[int, int, float, float, int]:
        tier = 0 if (rc.clean or not prefer_clean) else 1
        return (
            1 if rc.rejected else 0,
            tier,
            tau_of(rc) if order_by_tau else 0.0,
            rc.rank_cost,
            len(rc.path),
        )

    costs.sort(key=sort_key)

    # Fallback: with every route refused the agent still has to go somewhere,
    # and the least bad one is the one whose worst stretch is least bad -- the
    # question is surviving the walk, not averaging it.
    #
    # Refusal is never remembered: the sight criterion is measured against the
    # distance *still to walk*, so it relaxes as the agent closes on an exit and
    # the smoke that refused a door at 40 m accepts it at 2 m. Recomputing every
    # tick is what lets that happen. The price is that in a fire smoky enough to
    # refuse everything -- which is most of a real run, see
    # docs/gate-model-review-notes.md -- the ordering follows the field, so the
    # current exit is held unless a rival's worst stretch is clearly milder.
    #
    # Ordered by optical depth here too, not by the worst sample: ordering
    # refused routes by k_max alone once put a 51 m route ahead of a 22 m one
    # on 2.0 m of sight against 1.8 m -- two tenths of a metre of visibility,
    # neither usable, deciding a 29 m detour. tau carries the distance with it,
    # so the least-bad walk is the one with least smoke to walk through.
    if costs and all(rc.rejected for rc in costs):
        costs.sort(key=lambda rc: (rc.tau_route, rc.rank_cost))
        current = next((rc for rc in costs if rc.exit_id == current_exit), None)
        if current is not None and costs[0].exit_id != current.exit_id:
            margin = 1.0 - config.fallback_switch_margin
            if costs[0].k_max_route > current.k_max_route * margin:
                costs = [current] + [rc for rc in costs if rc is not current]
        best = costs[0]
        costs[0] = replace(
            best,
            rejected=False,
            rejection_reason=f"fallback: {best.rejection_reason}",
        )

    return costs


def _must_flee_rejection(rc: RouteCost, cost_config: RouteCostConfig) -> bool:
    """Whether the agent must abandon its current exit regardless of hysteresis.

    Only genuine hazards bypass the exit-switch anchor:

    * **FED-lethal** — predicted dose incapacitates the agent. Always flee.
    * **Impassably dense smoke** — the route's average extinction exceeds
      ``impassable_extinction_threshold`` (visibility of order a metre). Flee.

    A *mild* visibility rejection (``all segments non-visible`` from light haze,
    or ``next_node_not_visible`` from an unreadable sign) is NOT a hazard: the
    smoke is already in the route cost via ``w_smoke * k_ave``, so also letting
    the rejection bypass the anchor double-counts it and flips the agent off its
    cheaper committed exit onto a costlier one, then back next tick. Those stay
    subject to the anchor. The demo's flip-flop was exactly this — mild smoke
    (k_ave ~0.5-0.9) tripping the binary 0.5 visibility threshold every tick.

    Two hazards this does **not** catch, both by construction:

    * **Heat.** The convective heat dose is tracked per agent and can
      incapacitate on its own (``TenabilityConfig.heat_fed_threshold``), but it
      reaches no part of route choice -- ``rank_routes`` is given the gas dose
      and a gas-only rate sampler. An agent can therefore walk into a route
      that will incapacitate it thermally, and nothing here will reject it.
    * **A FED-lethal route that is also smoke-choked.** Under
      ``cost_model="gate"`` the tau test overwrites ``rejection_reason`` after
      the dose test sets it, so such a route reports ``tau ...`` and no longer
      matches the ``FED`` prefix below. The bypass is lost exactly where both
      hazards are present.
    """
    if not rc.rejected:
        return False
    reason = (rc.rejection_reason or "").removeprefix("fallback: ")
    if reason.startswith("FED"):
        return True
    if "visible" in reason:  # smoke-obscured path or unreadable sign
        return rc.k_ave_route > cost_config.impassable_extinction_threshold
    return False


def _anchor_allows(
    candidate: RouteCost,
    old_rc: RouteCost | None,
    config: RerouteConfig,
) -> bool:
    """Whether the exit-switch anchor lets the agent leave *old_rc* for *candidate*.

    The single statement of that rule. It was once written twice -- here, to
    skip past a promoted route the anchor would refuse, and inline at the
    decision -- and the two drifted, so the copy waved through switches the
    anchor then vetoed.

    Anchoring is bypassed when the old exit is a hazard the agent must flee,
    and when the candidate is clean where the old one is not. Otherwise the
    comparison is a deadband on optical depth, falling through to time only
    when the two routes are within it.
    """
    if old_rc is None:
        return True
    if _must_flee_rejection(old_rc, config.cost_config):
        return True
    cost_config = config.cost_config
    if cost_config.cost_model != "gate":
        return candidate.rank_cost < old_rc.rank_cost * config.exit_switch_anchor

    if candidate.clean and not old_rc.clean:
        return True
    if not candidate.feasible:
        return candidate.rank_cost < old_rc.rank_cost * config.exit_switch_anchor

    # A deadband on the quantity the routes are ordered by, symmetric. Clearly
    # cleaner is adopted, clearly dirtier is refused, and only a tie falls
    # through to time and queue.
    #
    # The refusal half was missing, and its absence was the oscillation:
    # leaving an exit had to clear a margin in tau, while returning went
    # straight to the time comparison, which the nearer exit wins
    # unconditionally and permanently. Departure cost a margin and the return
    # was free. Same shape as the clean tier's failure one level up --
    # hysteresis applied to one side of a disjunction is not hysteresis.
    #
    # Absolute rather than a ratio: tau is zero in clear air, where a ratio
    # reads 0 < 0, no agent could switch at all, and a congestion weight would
    # count for nothing exactly where decks calibrate one.
    margin = cost_config.tau_max * cost_config.tau_deadband
    delta = old_rc.tau_route - candidate.tau_route
    if delta > margin:
        return True
    if delta < -margin:
        return False
    return candidate.rank_cost < old_rc.rank_cost * config.exit_switch_anchor


def _adoptable(
    candidate: RouteCost,
    ranked: list[RouteCost],
    route_state: AgentRouteState,
    config: RerouteConfig,
) -> bool:
    """Whether the agent could switch to *candidate* if the ordering offered it."""
    old_exit = route_state.current_exit
    if old_exit is None or candidate.exit_id == old_exit:
        return True
    old_rc = next((rc for rc in ranked if rc.exit_id == old_exit), None)
    return _anchor_allows(candidate, old_rc, config)


def evaluate_and_reroute(
    agent_id: int,
    wait_info: dict,
    route_state: AgentRouteState,
    graph: StageGraph,
    current_time_s: float,
    current_fed: float,
    extinction_sampler: ExtinctionSampler,
    fed_rate_sampler: FedRateSampler | None,
    config: RerouteConfig,
    cached_segments: dict[SegmentCacheKey, SegmentCost] | None = None,
    *,
    exit_counts: dict[str, int] | None = None,
    cognitive_map=None,
    agent_position: tuple[float, float] | None = None,
) -> RouteSwitch | None:
    """Evaluate routes and reroute the agent if a better exit is found.

    Returns a RouteSwitch record if the agent switched, else None.
    """
    # Determine the source node for ranking.  Prefer current_origin
    # (where the agent is coming from) because current_target_stage may
    # be an exit with no outgoing edges.
    source = wait_info.get("current_origin") or wait_info.get("current_target_stage")
    if source is None or source not in graph.nodes:
        return None

    # The node the agent is currently walking toward, so position-aware costs can
    # credit progress along that leg and penalize routes that diverge from it.
    current_target = wait_info.get("current_target_stage")

    ranked = rank_routes(
        graph,
        source,
        current_time_s,
        current_fed,
        extinction_sampler,
        fed_rate_sampler,
        config.cost_config,
        cached_segments=cached_segments,
        exit_counts=exit_counts,
        cognitive_map=cognitive_map,
        agent_position=agent_position,
        current_exit=route_state.current_exit,
        current_target=current_target,
    )
    if not ranked:
        # No exit reachable in the agent's known subgraph (typically a
        # discovery agent that hasn't found the way out yet). Rather than
        # standing still, head toward the nearest known-but-unexplored node
        # so the cognitive map keeps growing until an exit is found.
        route_state.last_eval_time_s = current_time_s
        if cognitive_map is None:
            return None
        from pyfds_evac.core.cognitive_map import nearest_frontier_target, wander_target

        idle = wait_info.get("state") == "idle"
        reason = "explore"
        frontier = nearest_frontier_target(cognitive_map, graph, source, agent_position)
        if frontier is None:
            # Knowledge exhausted: every known node is visited and none of it
            # leads to an exit. Patrol the known nodes instead of standing --
            # perception runs from the agent's position, so a walked leg can
            # make a sign readable that never was from any node it stood on.
            if idle and route_state.current_path:
                # The previous patrol leg was completed; move on to the next
                # stop, or a single-candidate rotation would re-offer the node
                # the agent is standing on the way to.
                route_state.wander_step += 1
            frontier = wander_target(
                cognitive_map, graph, source, route_state.wander_step
            )
            reason = "wander"
        if frontier is None:
            return None
        target_node, path = frontier
        # Already committed to this target: the agent's current target is an
        # intermediate hop of the committed path, not the destination itself,
        # so comparing against current_target_stage alone re-fires the same
        # switch on every reevaluation until arrival. An idle agent is never
        # suppressed -- it is standing with no onward plan and must be routed.
        committed = route_state.current_path
        if not idle and (
            wait_info.get("current_target_stage") == target_node
            or (
                committed
                and committed[-1] == target_node
                and wait_info.get("current_target_stage") in committed
            )
        ):
            return None
        stage_configs = wait_info.get("stage_configs", {})
        changed = reroute_agent(wait_info, path, stage_configs)
        if not changed:
            return None
        route_state.current_path = path
        # old_exit is left None on purpose: exploring toward a frontier node
        # does not abandon any exit commitment, so this switch must not drive
        # the caller's exit_counts bookkeeping (new_exit is a checkpoint, not
        # an exit). route_state.current_exit is deliberately unchanged.
        return RouteSwitch(
            time_s=current_time_s,
            agent_id=agent_id,
            old_exit=None,
            new_exit=target_node,
            old_cost=None,
            new_cost=0.0,
            reason=reason,
        )

    best = ranked[0]
    # A route the ordering promoted but the agent cannot adopt must not hide
    # the rest of the list. Tier 1 can put a clean exit first that the anchor
    # then refuses on time; before this, the agent returned None and never saw
    # the rival at rank 2 it would have switched to -- so adding the tier could
    # suppress a switch the model made without it, which is strictly worse than
    # having no tier at all. Candidates are tried in rank order and the first
    # adoptable one wins; if none is, nothing changes, as before.
    current_exit_now = route_state.current_exit
    if (
        current_exit_now is not None
        and config.cost_config.cost_model == "gate"
        and best.exit_id != current_exit_now
    ):
        for candidate in ranked:
            if candidate.exit_id == current_exit_now:
                break  # the agent's own exit outranks the rest: stay
            if _adoptable(candidate, ranked, route_state, config):
                best = candidate
                break

    if (
        best.rejected
        and best.rejection_reason
        and not best.rejection_reason.startswith("fallback")
    ):
        return None

    old_exit = route_state.current_exit
    old_rc = None
    old_cost = None
    if old_exit and old_exit != best.exit_id:
        # Find the old exit's route: its cost, its band and whether it is
        # clean all feed _anchor_allows, which also decides whether it is a
        # hazard the agent must flee.
        for rc in ranked:
            if rc.exit_id == old_exit:
                old_rc = rc
                old_cost = rc.rank_cost
                break

    route_state.last_eval_time_s = current_time_s

    # An idle agent stands on a node with no onward plan, so there is no
    # committed path to compare against and no churn to protect it from. It must
    # be routed even when the best exit is the one it was nominally assigned at
    # spawn -- an assignment made by straight-line distance before routing ran,
    # over an exit the agent had not yet discovered. Without this, an explorer
    # whose assigned exit happens to be the one it finds is never routed to it
    # and stands at the doorway for the rest of the run.
    if old_exit == best.exit_id and wait_info.get("state") != "idle":
        # Same exit — only reroute if the newly ranked path to it is
        # meaningfully cheaper than the path the agent is actually walking
        # right now (not just whatever was last recorded as "best").
        committed_path = _reconstruct_committed_path(wait_info)
        if (
            committed_path
            and committed_path[-1] == best.exit_id
            and all(n in graph.nodes for n in committed_path)
        ):
            committed = evaluate_route(
                graph,
                committed_path,
                current_time_s,
                current_fed,
                extinction_sampler,
                fed_rate_sampler,
                config.cost_config,
                cached_segments=cached_segments,
                exit_counts=exit_counts,
                agent_position=agent_position,
                current_target=current_target,
            )
            committed_cost = committed.rank_cost
            # A rejected walked path is left for a feasible one whatever the
            # time saving: the 10 % rule damps churn between acceptable
            # paths, it must not hold an agent on one that failed a limit.
            leaves_rejected = committed.rejected and best.feasible and not best.rejected
            if (
                leaves_rejected
                or best.rank_cost < committed_cost * _PATH_IMPROVEMENT_THRESHOLD
            ):
                stage_configs = wait_info.get("stage_configs", {})
                changed = reroute_agent(wait_info, best.path, stage_configs)
                if changed:
                    route_state.current_path = best.path
                    return RouteSwitch(
                        time_s=current_time_s,
                        agent_id=agent_id,
                        old_exit=old_exit,
                        new_exit=best.exit_id,
                        old_cost=committed_cost,
                        new_cost=best.rank_cost,
                        reason="better_path",
                    )
        route_state.current_path = best.path
        return None

    # Anchoring / hysteresis: don't abandon the current exit for a *different*
    # one unless the new exit is meaningfully better. Without this, near-tied
    # exits flip-flop on every reevaluation -- worst at short reroute intervals.
    # Anchoring does not apply to the initial choice (old_exit is None) or when
    # the old exit is no longer reachable and so was never priced. Everything
    # else is _anchor_allows, which is also what chose `best` above.
    if (
        old_exit is not None
        and old_cost is not None
        and not _anchor_allows(best, old_rc, config)
    ):
        return None

    # Reroute.
    stage_configs = wait_info.get("stage_configs", {})
    changed = reroute_agent(wait_info, best.path, stage_configs)
    if not changed:
        return None

    reason = "initial" if old_exit is None else "smoke_reroute"
    if best.rejection_reason and best.rejection_reason.startswith("fallback"):
        reason = "fallback"

    route_state.current_exit = best.exit_id
    route_state.current_path = best.path

    return RouteSwitch(
        time_s=current_time_s,
        agent_id=agent_id,
        old_exit=old_exit,
        new_exit=best.exit_id,
        old_cost=old_cost,
        new_cost=best.rank_cost,
        reason=reason,
    )
