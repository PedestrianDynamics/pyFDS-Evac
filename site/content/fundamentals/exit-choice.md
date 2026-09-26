---
title: "Exit choice and familiarity"
weight: 10
---

Which exit an occupant heads for is not decided by distance alone. The studies
below find that occupants tend to leave the way they know, are influenced by
what other people do, and respond to smoke, lighting and crowding at the
exits. There is no single published law for exit choice; there are
observations and calibrated statistical models.

## Movement to the familiar

Sime (1985) studied the direction of escape in a fire in a large room with an
entrance and an emergency exit in opposite corners. He contrasted the
"affiliative" model, in which people under threat of entrapment move towards
familiar persons and places, with design assumptions that the physical
availability and proximity of an exit determine its use. Proximity mattered,
but so did affiliation: staff generally left by the fire exit, whereas members
of the public who were separated from their group moved towards, and left by,
the entrance. Sime argued that place affiliation is not addressed
sufficiently in escape-route design.

Kinateder, Comunale and Warren (2018) tested this in an ambulatory virtual
museum. Participants entered through one door and, when an alarm sounded,
were significantly more likely to leave through that familiar door than
through a second exit. The effect grew when virtual neighbours also left by
the familiar door, shrank when they left by the other door, and the social
influence was stronger with two neighbours than with one.

## Discrete-choice models

Lovreglio, Borri, dell'Olio and Ibeas (2014) introduced a random-utility
discrete-choice model for exit choice in emergency evacuations. Lovreglio,
Fonzone and dell'Olio (2016) calibrated a mixed logit model on an online
stated-preference survey with non-immersive virtual reality and 1503
participants. Smoke, emergency lighting, exit distance, the number of
evacuees near the exits and near the decision-maker, and the flow of evacuees
through the exits all affected local exit choice significantly, with a high
degree of behavioural uncertainty.

Haghani and Sarvi (2017) compared stated choices (4958 observations from
face-to-face interviews in three public places) with revealed choices (3015
exit choices extracted from video of evacuation trials in which participants
competed in a real crowd). The four data sets gave fairly similar patterns of
parameter estimates, and the stated-choice models predicted choices
reasonably similar to the revealed-choice model, despite significant
differences in parameter scale. Their review of empirical methods in crowd
research (Haghani and Sarvi 2018) surveys more than 160 studies.

## Known limits

Apart from incident studies such as Sime's, the evidence above comes from
hypothetical choices, virtual reality and evacuation trials, none of which
carries the threat of a real fire. Whether parameters calibrated in one
geometry and population transfer to another is an open question; Haghani and
Sarvi (2017) set out to test exactly this context-dependence. The guide to FDS+Evac, the evacuation module of the Fire Dynamics
Simulator (FDS),
notes, citing the socio-psychological literature, that familiarity of
exit routes is an essential factor in evacuees' decisions and that emergency
exits are rarely used in many real evacuations because they are unfamiliar
(Korhonen 2021, §3.5).

## Sources

- J. D. Sime (1985). Movement toward the familiar: person and place
  affiliation in a fire entrapment setting. *Environment and Behavior*
  17(6):697–724.
  [doi:10.1177/0013916585176003](https://doi.org/10.1177/0013916585176003)
- M. Kinateder, B. Comunale and W. H. Warren (2018). Exit choice in an
  emergency evacuation scenario is influenced by exit familiarity and
  neighbor behavior. *Safety Science* 106:170–175.
  [doi:10.1016/j.ssci.2018.03.015](https://doi.org/10.1016/j.ssci.2018.03.015)
- R. Lovreglio, D. Borri, L. dell'Olio and A. Ibeas (2014). A discrete choice
  model based on random utilities for exit choice in emergency evacuations.
  *Safety Science* 62:418–426.
  [doi:10.1016/j.ssci.2013.10.004](https://doi.org/10.1016/j.ssci.2013.10.004)
- R. Lovreglio, A. Fonzone and L. dell'Olio (2016). A mixed logit model for
  predicting exit choice during building evacuations. *Transportation
  Research Part A* 92:59–75.
  [doi:10.1016/j.tra.2016.06.018](https://doi.org/10.1016/j.tra.2016.06.018)
- M. Haghani and M. Sarvi (2017). Stated and revealed exit choices of
  pedestrian crowd evacuees. *Transportation Research Part B* 95:238–259.
  [doi:10.1016/j.trb.2016.10.019](https://doi.org/10.1016/j.trb.2016.10.019)
- M. Haghani and M. Sarvi (2018). Crowd behaviour and motion: empirical
  methods. *Transportation Research Part B* 107:253–294.
  [doi:10.1016/j.trb.2017.06.017](https://doi.org/10.1016/j.trb.2017.06.017)
- T. Korhonen (2021). *FDS+Evac Technical Reference and User's Guide*, §3.5.
  VTT Technical Research Centre of Finland. Secondary source.

How pyFDS-Evac uses this: see [route rerouting](/models/routing.md) and
[visibility and cognitive maps](/models/visibility.md).
