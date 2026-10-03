"""Terminal UI of pyFDS-Evac (``pyfds-evac-tui``, #485).

Needs the ``tui`` extra (Textual). :mod:`.model` (form state, scenarios,
run snapshots) and :mod:`.runner` (the run in a child process) import
neither Textual nor the simulation stack; :mod:`.app` holds the screens.
"""
