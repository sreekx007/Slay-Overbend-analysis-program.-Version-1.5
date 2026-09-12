"""slay.scene -- Where things are: stinger arc, roller stations, deck, ILS placement.

Converts the ILS-local definition into a world/arc-length frame and
places the roller stations it will travel over. Placement only -- this
layer computes no nodes and no elements.

Workflow: none -- pure transforms.
"""

from slay.scene.path import LayPath
from slay.scene.rollers import (
    Station,
    StationRole,
    contact_stations,
    fixed_station,
    load_station,
    roller_stations,
)
from slay.scene.scene import Scene, build_scene

__all__ = [
    'LayPath', 'Station', 'StationRole', 'Scene', 'build_scene',
    'roller_stations', 'contact_stations', 'fixed_station', 'load_station',
]
