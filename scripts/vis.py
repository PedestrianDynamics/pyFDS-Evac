from jupedsim.internal.notebook_utils import animate, read_sqlite_file

import sys

trajectory_file = sys.argv[1]
traj, walkable_area = read_sqlite_file(trajectory_file)

animate(traj, walkable_area, every_nth_frame=5).show()
